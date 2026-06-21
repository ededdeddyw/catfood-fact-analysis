# -*- coding: utf-8 -*-
"""人手(目検)で確定したキャットフードURLとメモを maker_sites.csv に統合。

入力:
  data/maker_url_todo.csv の Human 列（ユーザーが目検で確認したキャットフードURL）
  + 下記 MEMO（複数ブランド・商社・無し判定など、todo に収まらない補足）
処理:
  - Human/メモのURLを軽く取得検証（到達性＋成分/猫キーワード。会社一致は人が済ませたので緩め）
  - maker_sites.csv を method=human / human_memo / excluded_no_catfood で更新（note列付き）
出力: data/maker_sites.csv（note列を追加して書き戻し）
"""
from __future__ import annotations

import csv

from bs4 import BeautifulSoup

from catfood_common import DATA_DIR, polite_get, safe_print, today_stamp

CSV = DATA_DIR / "maker_sites.csv"
TODO = DATA_DIR / "maker_url_todo.csv"
FIELDS = ["company_name", "official_url", "domain", "matched", "match_token",
          "method", "http_status", "candidate_hint", "needs_review",
          "source_url", "fetched_at", "note"]

# todo に収まらない補足（ユーザーメモ 2026-06-21）。
# status: confirmed / excluded_no_catfood / maybe_none
MEMO: dict[str, dict] = {
    "株式会社カラーズ": {"status": "confirmed",
        "url": "https://yumyumyum.jp/cat/products",
        "note": "3ブランド該当: yumyumyum.jp/cat/products / bioliob.com/lineup / green-dog.com/shop/category/cat"},
    "グローバルワン株式会社": {"status": "confirmed",
        "url": "https://natures-taste.jp/?mode=srh&cid=&keyword=",
        "note": "会社別サイトに転送。natures-taste.jp が該当"},
    "住商アグロインターナショナル株式会社": {"status": "confirmed",
        "url": "https://hartz.jp/",
        "note": "Hartz商品を扱う商社。hartz.jp"},
    "エヌピーエフジャパン株式会社": {"status": "excluded_no_catfood",
        "note": "ニップン子会社っぽい。HPなしかも"},
    "特定非営利活動法人cambio": {"status": "excluded_no_catfood",
        "note": "npo-cambio.org/tashika/ に転送されるが商品一覧404→無視"},
    "株式会社クキ・イーアンドティー": {"status": "excluded_no_catfood",
        "note": "ペット関係なし"},
    "ナッシュ株式会社": {"status": "excluded_no_catfood",
        "note": "キャットフード無いかも。nosh.jp/dog/menu はドッグ"},
    "キョーリンフード工業株式会社": {"status": "maybe_none",
        "url": "https://www.kyorin-net.co.jp/animal/",
        "note": "kyorin-net.co.jp/animal/ だがキャットフード無いかも"},
    "株式会社黒龍堂": {"status": "maybe_none", "note": "キャットフード無いかも"},
    "シーズイシハラ株式会社": {"status": "maybe_none", "note": "キャットフード無いかも"},
    "ドギーマンハヤシ株式会社": {"status": "note_only",
        "note": "注意: /newitem?ca1=猫 は新商品だけ。/product/ を使う"},
}

NUT_KW = ["成分", "保証", "たんぱく", "粗", "リン", "分析"]
CAT_KW = ["猫", "キャット", "cat", "ねこ"]


def load_human() -> dict[str, str]:
    out: dict[str, str] = {}
    with TODO.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            h = (r.get("Human") or r.get("human") or "").strip()
            if h:
                out[r["company_name"].strip()] = h
    return out


def check(url: str) -> dict:
    r = polite_get(url, retries=1, sleep=0.5, timeout=(8, 18))
    if r is None:
        return {"status": "dead", "nut": False, "cat": False}
    s = BeautifulSoup(r.text, "html.parser")
    for t in s(["script", "style", "noscript"]):
        t.decompose()
    txt = s.get_text(" ", strip=True)
    return {"status": str(r.status_code),
            "nut": any(k in txt for k in NUT_KW),
            "cat": any(k in txt for k in CAT_KW)}


def host_of(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc.lower()


def main() -> None:
    human = load_human()
    rows = list(csv.DictReader(CSV.open(encoding="utf-8-sig", newline="")))
    by = {r["company_name"].strip(): r for r in rows}
    stamp = today_stamp()
    n_conf = n_excl = n_maybe = 0

    # 対象 = Human 記入 ∪ MEMO
    targets = set(human) | set(MEMO)
    for name in sorted(targets):
        r = by.get(name)
        if r is None:
            continue
        memo = MEMO.get(name, {})
        status = memo.get("status", "confirmed")
        note = memo.get("note", "")

        if status in ("excluded_no_catfood",):
            r.update(official_url="", domain="", matched="no", match_token="",
                     method="excluded_no_catfood", http_status="",
                     needs_review="no", note=note, fetched_at=stamp)
            n_excl += 1
            safe_print(f"[EXCL ] {name}  ({note})")
            continue
        if status == "maybe_none":
            url = memo.get("url", "")
            r.update(official_url="", domain=host_of(url) if url else "",
                     matched="no", method="maybe_none",
                     candidate_hint=url, needs_review="yes",
                     note=note, fetched_at=stamp)
            n_maybe += 1
            safe_print(f"[MAYBE] {name}  ({note})")
            continue
        if status == "note_only":
            # 既存の確定はそのまま、note だけ付与
            r["note"] = note
            safe_print(f"[NOTE ] {name}  ({note})")
            continue

        # confirmed: Human URL 優先、無ければ memo url
        url = human.get(name) or memo.get("url", "")
        chk = check(url)
        live = chk["status"].startswith("2") or chk["status"] == "dead" and False
        full_note = note
        flags = []
        if chk["nut"]:
            flags.append("成分あり")
        if chk["cat"]:
            flags.append("猫あり")
        if chk["status"] == "dead":
            flags.append("取得失敗")
        if flags:
            full_note = (note + " | " if note else "") + "/".join(flags)
        r.update(official_url=url, domain=host_of(url),
                 matched="yes", match_token="human",
                 method="human" if name in human else "human_memo",
                 http_status=chk["status"],
                 needs_review="no" if chk["status"].startswith("2") else "yes",
                 candidate_hint="", note=full_note, fetched_at=stamp)
        n_conf += 1
        safe_print(f"[CONF ] {name}  {url}  [{chk['status']}] {('/'.join(flags)) or ''}")

    # note 列を持たない既存行に空noteを補完
    for r in rows:
        r.setdefault("note", "")

    with CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    ok = sum(1 for r in rows if r["matched"] == "yes" and r["needs_review"] == "no")
    safe_print(f"\n[merge] 確定追加 {n_conf} / 除外 {n_excl} / 不明 {n_maybe}")
    safe_print(f"[merge] 全体: 確定 {ok} / 計 {len(rows)}  -> {CSV}")


if __name__ == "__main__":
    main()
