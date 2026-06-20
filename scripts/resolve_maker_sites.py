# -*- coding: utf-8 -*-
"""母集団79メーカーの公式サイトURLを解決する（トークンゼロ・検証付き）。

なぜ:
  pffta_members.csv は会社名・住所のみで公式URLが無い。製品ファクト抽出
  (extract_product_facts.py --site) を79社へ回すには各社の公式URLが要る。

方針（docs/02・03 と整合 / LLM API 不使用 = トークン課金ゼロ）:
  ① Bing をスクレイプして候補URLを得る（病院 job_search_bing.py と同じ手法）。
  ②【最重要】候補を実際に取得し、会社名（法人格を除いたコア）がページ本文に
     現れるか検証。検証できたものだけ official_url に採用する。
     → 検索が誤爆しても "捏造URL" は CSV に入らない（出典必須の担保）。
  ③ 検証できない社は needs_review=yes として残し、人手で確定する。

出力: data/maker_sites.csv
"""
from __future__ import annotations

import base64
import re
import sys
import time
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from catfood_common import (
    DATA_DIR,
    DEFAULT_HEADERS,
    log_line,
    polite_get,
    safe_print,
    today_stamp,
    write_csv,
)

MEMBERS_CSV = DATA_DIR / "pffta_members.csv"
OUT_CSV = DATA_DIR / "maker_sites.csv"

FIELDNAMES = [
    "company_name",
    "official_url",
    "domain",
    "matched",          # yes/no : 会社名コアがページ本文に出たか
    "match_token",      # 何の文字列で一致したか（監査用）
    "method",           # どのクエリ/手段で解決したか
    "http_status",
    "candidate_hint",   # 未検証時の最有力候補（人手確定の手がかり）
    "needs_review",     # yes/no
    "source_url",       # 母集団の出典
    "fetched_at",
]

# 公式ドメインではないノイズ（EC・SNS・名鑑・税務解説・百科事典・求人など）
NOISE_DOMAINS = (
    "bing.com", "microsoft.com", "google.", "duckduckgo",
    "wikipedia.org", "wikiwand", "weblio",
    "rakuten.co.jp", "rakuten.com", "amazon.co.jp", "amazon.com",
    "yahoo.co.jp", "yahoo.com", "shopping.yahoo", "paypaymall", "lohaco",
    "kakaku.com", "monotaro", "askul", "mercari", "aupay", "au.com",
    "facebook.com", "instagram.com", "twitter.com", "x.com", "youtube.com",
    "tiktok.com", "line.me", "lin.ee", "pinterest",
    "note.com", "ameblo.jp", "hatena", "fc2.com", "livedoor",
    "navitime", "mapion", "its-mo", "mapfan", "goo.ne.jp/map",
    "baseconnect", "find-a", "alarmbox", "houjin.jp", "houjin-bangou",
    "nta.go.jp", "go.jp", "freee.co.jp", "ht-tax", "mizuhobank", "nabutan",
    "indeed", "en-gage", "mynavi", "doda", "rikunabi", "hellowork",
    "shigoto", "townwork", "baitoru", "job-",
    "prtimes.jp", "atpress", "value-press",
    "chiebukuro", "detail.chiebukuro", "oshiete.goo",
    "linkedin.com", "pixiv", "dic.nicovideo",
)

# 既知メーカーの公式URL候補（人の知識）。必ず取得＋会社名一致で検証してから採用するので
# 推測が外れても捏造にはならない（外れURLは fetch_fail / 名前不一致で弾かれ Bing にフォールバック）。
CURATED: dict[str, str] = {
    "アイシア株式会社": "https://www.aixia.jp/",
    "いなばペットフード株式会社": "https://www.inaba-petfood.co.jp/",
    "日本ペットフード株式会社": "https://www.npf.co.jp/",
    "ユニ・チャーム株式会社": "https://www.unicharm.co.jp/",
    "日本ヒルズ・コルゲート株式会社": "https://www.hills.co.jp/",
    "ロイヤルカナンジャポン合同会社": "https://www.royalcanin.com/jp",
    "マース・ジャパン・リミテッド": "https://www.mars.com/ja-jp",
    "ネスレ日本株式会社　ネスレピュリナペットケア": "https://nestle.jp/brand/purina",
    "ペットライン株式会社": "https://www.petline.co.jp/",
    "デビフペット株式会社": "https://www.dbfpet.co.jp/",
    "ドギーマンハヤシ株式会社": "https://www.doggyman.com/",
    "アース・ペット株式会社": "https://www.earth-pet.co.jp/",
    "ジェックス株式会社": "https://www.gex-fp.co.jp/",
    "ライオンペット株式会社": "https://www.lion-pet.jp/",
    "株式会社森乳サンワールド": "https://www.sunworld.co.jp/",
    "株式会社ペティオ": "https://www.petio.com/",
    "はごろもフーズ株式会社": "https://www.hagoromofoods.co.jp/",
    "マルトモ株式会社": "https://www.marutomo.co.jp/",
    "アイリスオーヤマ株式会社": "https://www.irisohyama.co.jp/",
    "日本アムウエイ合同会社": "https://www.amway.co.jp/",
    "株式会社ビルバックジャパン": "https://jp.virbac.com/",
    "イースター株式会社": "https://www.easter-petfood.co.jp/",
    "ペットライブラリー株式会社": "https://www.petlibrary.jp/",
    "ママクック株式会社": "https://www.mamacook.jp/",
    "株式会社レティシアン": "https://www.laetitienne.co.jp/",
}

# 取り除く法人格（コア抽出用）
LEGAL = [
    "特定非営利活動法人", "一般財団法人", "一般社団法人", "公益財団法人",
    "公益社団法人", "株式会社", "有限会社", "合同会社", "合名会社", "合資会社",
    "NPO法人", "（株）", "(株)", "（有）", "(有)",
]


def normalize(s: str) -> str:
    """空白・記号を除去して比較しやすくする。"""
    return re.sub(r"[\s　・,，.．/／\-―ー]+", "", s or "")


def core_name(name: str) -> str:
    """会社名から法人格を除いたコアを返す（一致判定用）。"""
    s = name
    for w in LEGAL:
        s = s.replace(w, "")
    # 全角空白や記号で割れた最初の塊（例:「ネスレ日本 ネスレピュリナ…」）も保持
    return normalize(s)


def decode_bing(href: str) -> str:
    """Bing /ck/a リダイレクトを実URLへ（u=a1<base64>）。"""
    if "bing.com/ck/a" not in href:
        return href
    u = parse_qs(urlparse(href).query).get("u", [""])[0]
    if u.startswith("a1"):
        b = u[2:] + "=" * (-len(u[2:]) % 4)
        try:
            return base64.urlsafe_b64decode(b).decode("utf-8", "replace")
        except Exception:
            return href
    return href


def host_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def is_noise(url: str) -> bool:
    h = host_of(url)
    return (not h) or any(n in h for n in NOISE_DOMAINS)


def bing_search(query: str, *, count: int = 12) -> list[str]:
    """Bing 検索結果の実URL一覧（リダイレクト解決済み・ノイズ除去済み）。"""
    try:
        r = requests.get(
            "https://www.bing.com/search",
            params={"q": query, "count": count, "setlang": "ja", "mkt": "ja-JP"},
            headers=DEFAULT_HEADERS,
            timeout=30,
        )
    except requests.RequestException as exc:
        safe_print(f"   [bing-fail] {type(exc).__name__}")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    urls: list[str] = []
    seen_hosts: set[str] = set()
    for li in soup.select("li.b_algo"):
        h2 = li.find("h2")
        a = h2.find("a") if h2 else None
        if not a:
            continue
        real = decode_bing(a.get("href", ""))
        if is_noise(real):
            continue
        hh = host_of(real)
        if hh in seen_hosts:
            continue
        seen_hosts.add(hh)
        urls.append(real)
    return urls


def root_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/"


def page_text(resp) -> str:
    return BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)


def verify_candidate(url: str, core: str, full_norm: str):
    """候補URLを取得し、会社名コア/正式名が本文にあるか検証。

    returns: (matched: bool, match_token: str, status: str, official: str)
    """
    resp = polite_get(url, retries=1, sleep=0.6, timeout=(8, 15))
    if resp is None:
        return False, "", "fetch_fail", ""
    body = normalize(page_text(resp))
    official = root_url(resp.url if hasattr(resp, "url") else url)
    # 正式名（正規化）一致が最強。次にコア（3文字以上）一致。
    if full_norm and full_norm in body:
        return True, "full", "200", official
    if len(core) >= 3 and core in body:
        return True, core, "200", official
    if len(core) == 2 and core in body:
        # 2文字コアは誤爆しやすいので弱一致扱い（matched=yes だが review 推奨は呼び出し側）
        return True, core + "(weak)", "200", official
    return False, "", "200_nomatch", official


def _row(name, official, domain, matched, tok, method, status, hint, review):
    return {
        "company_name": name,
        "official_url": official,
        "domain": domain,
        "matched": matched,
        "match_token": tok,
        "method": method,
        "http_status": status,
        "candidate_hint": hint,
        "needs_review": review,
        "source_url": "https://pffta.org/about/members/",
        "fetched_at": today_stamp(),
    }


def resolve_one(name: str) -> dict:
    core = core_name(name)
    full_norm = normalize(name)

    # ① 既知ドメインを最優先で検証（速い・確実）。一致したら採用。
    if name in CURATED:
        matched, tok, status, official = verify_candidate(CURATED[name], core, full_norm)
        if matched:
            weak = tok.endswith("(weak)")
            return _row(name, official, host_of(official), "yes", tok, "curated",
                        status, "", "yes" if weak else "no")

    # ② Bing 検索＋検証へフォールバック
    queries = [
        f"{name} キャットフード 公式",
        f"{name} 公式サイト",
        f"{name} ペットフード",
    ]
    first_hint = ""
    tried_hosts: set[str] = set()
    for qi, q in enumerate(queries, 1):
        cands = bing_search(q)
        time.sleep(1.0)
        for url in cands[:4]:
            hh = host_of(url)
            if hh in tried_hosts:
                continue
            tried_hosts.add(hh)
            if not first_hint:
                first_hint = url
            matched, tok, status, official = verify_candidate(url, core, full_norm)
            if matched:
                weak = tok.endswith("(weak)")
                return _row(name, official, host_of(official), "yes", tok,
                            f"bing_q{qi}", status, "", "yes" if weak else "no")
    # どのクエリでも検証できず
    return _row(name, "", host_of(first_hint), "no", "", "unresolved",
                "", first_hint, "yes")


def load_makers() -> list[str]:
    import csv
    makers: list[str] = []
    with MEMBERS_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("member_type") == "正会員":
                makers.append(row["company_name"].strip())
    return makers


def load_done() -> set[str]:
    """既存 maker_sites.csv に解決済みの社名（再開用）。"""
    import csv
    done: set[str] = set()
    if OUT_CSV.exists():
        with OUT_CSV.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("company_name"):
                    done.add(r["company_name"].strip())
    return done


def append_row(row: dict, *, write_header: bool) -> None:
    """1社ぶんを即追記（途中で落ちても進捗が残る）。"""
    import csv
    new = not OUT_CSV.exists()
    with OUT_CSV.open("a", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDNAMES, extrasaction="ignore")
        if new or write_header:
            w.writeheader()
        w.writerow(row)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="先頭N社だけ（試走用）")
    ap.add_argument("--start", type=int, default=0, help="N社目から開始")
    ap.add_argument("--fresh", action="store_true", help="既存CSVを無視して最初から")
    args = ap.parse_args()

    makers = load_makers()
    if args.start:
        makers = makers[args.start:]
    if args.limit:
        makers = makers[: args.limit]

    if args.fresh and OUT_CSV.exists():
        OUT_CSV.unlink()
    done = set() if args.fresh else load_done()
    todo = [m for m in makers if m not in done]
    safe_print(f"[resolve] 対象 {len(makers)} 社 / 済 {len(makers) - len(todo)} / 残 {len(todo)}")

    header_needed = not OUT_CSV.exists()
    for i, name in enumerate(todo, 1):
        safe_print(f"  ({i}/{len(todo)}) {name}")
        try:
            row = resolve_one(name)
        except Exception as exc:  # 1社の失敗で全体を止めない
            safe_print(f"      !! {type(exc).__name__}: {exc}")
            row = _row(name, "", "", "no", "", f"error:{type(exc).__name__}", "", "", "yes")
        flag = "OK " if row["matched"] == "yes" and row["needs_review"] == "no" else "REVIEW"
        safe_print(f"      -> [{flag}] {row['official_url'] or row['candidate_hint'] or '(none)'}")
        append_row(row, write_header=header_needed)
        header_needed = False

    # 集計（CSV全体を読み直す）
    import csv
    allrows = list(csv.DictReader(OUT_CSV.open(encoding="utf-8-sig", newline="")))
    ok = sum(1 for r in allrows if r["matched"] == "yes" and r["needs_review"] == "no")
    rev = sum(1 for r in allrows if r["needs_review"] == "yes")
    log_line("resolve_maker_sites", f"DONE total={len(allrows)} resolved={ok} review={rev}")
    safe_print(f"\n[done] 確定 {ok} / 要確認 {rev} / 計 {len(allrows)}  -> {OUT_CSV}")


if __name__ == "__main__":
    main()
