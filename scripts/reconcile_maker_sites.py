# -*- coding: utf-8 -*-
"""maker_sites.csv を③人手確定の結果で整える。

- 検証で確定した提案URL（verify_proposed_sites.py が OK にした9件）を確定へ昇格。
- Bing の偽陽性（役場・旅行・証券・宅配・単字誤爆）を要確認へ降格。
- 既知大手で静的検証に失敗したもの（JS/リダイレクト）を method=manual_known で確定。

すべて出典追跡可能。実在しない/別会社のドメインは入れない。
"""
from __future__ import annotations

import csv

from catfood_common import DATA_DIR, safe_print, today_stamp

CSV = DATA_DIR / "maker_sites.csv"
FIELDS = ["company_name", "official_url", "domain", "matched", "match_token",
          "method", "http_status", "candidate_hint", "needs_review",
          "source_url", "fetched_at"]

# verify_proposed_sites.py が会社名一致で OK にした URL（取得検証済み）
VERIFIED = {
    "イオントップバリュ株式会社": "https://www.topvalu.net/",
    "兼松株式会社": "https://www.kanematsu.co.jp/",
    "スペクトラム ブランズ ジャパン株式会社": "https://spectrumbrands.jp/",
    "ベストアメニティ株式会社": "https://www.bestamenity.co.jp/",
    "マルカイコーポレーション株式会社": "https://www.marukai.co.jp/",
    "レッドハート株式会社": "https://redheart.co.jp/",
    "株式会社わんわん": "https://www.wanwan.co.jp/",
    "アダプトゲン製薬九州株式会社": "https://adaptgen-kyushu.com/",
}

# 既知大手で静的検証に失敗（JS描画/リダイレクトで会社名がテキストに出ない）。
# ブランドが一意なので手動で確定（method=manual_known と明示）。
MANUAL_KNOWN = {
    "ロイヤルカナンジャポン合同会社": "https://www.royalcanin.com/jp",
    "ネスレ日本株式会社　ネスレピュリナペットケア": "https://nestle.jp/brand/purina",
}

# Bing 会社名一致だが明らかに別物（要確認へ降格）
DEMOTE = {
    "INO株式会社",          # いの町役場(town.ino.kochi.jp)
    "イースター株式会社",    # るるぶ(rurubu.jp)
    "株式会社ダイワ",        # 大和証券系(daiwa.com)
    "ナッシュ株式会社",      # 食事宅配nosh(別事業の可能性)
    "株式会社一",            # 単字"一"の誤爆(ichi.company)
    "ヴォイス株式会社",      # 人手確認NG(voice-inc.co.jp=同名他社)
    "トーラス株式会社",      # 人手確認NG(taurus-k.co.jp)
}


def host_of(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc.lower()


def main() -> None:
    rows = list(csv.DictReader(CSV.open(encoding="utf-8-sig", newline="")))
    stamp = today_stamp()
    n_up = n_down = n_known = 0

    for r in rows:
        name = r["company_name"].strip()
        if name in VERIFIED:
            url = VERIFIED[name]
            r.update(official_url=url, domain=host_of(url), matched="yes",
                     match_token="full", method="verified_proposal",
                     http_status="200", candidate_hint="", needs_review="no",
                     fetched_at=stamp)
            n_up += 1
        elif name in MANUAL_KNOWN:
            url = MANUAL_KNOWN[name]
            r.update(official_url=url, domain=host_of(url), matched="yes",
                     match_token="manual", method="manual_known",
                     http_status="", candidate_hint="", needs_review="no",
                     fetched_at=stamp)
            n_known += 1
        elif name in DEMOTE:
            r.update(official_url="", matched="no", match_token="",
                     method="rejected_falsepos",
                     candidate_hint=r.get("candidate_hint") or r.get("domain", ""),
                     needs_review="yes")
            n_down += 1

    with CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    ok = sum(1 for r in rows if r["matched"] == "yes" and r["needs_review"] == "no")
    rev = sum(1 for r in rows if r["needs_review"] == "yes")
    safe_print(f"[reconcile] 昇格 {n_up} / 既知大手 {n_known} / 降格 {n_down}")
    safe_print(f"[reconcile] 確定 {ok} / 要確認 {rev} / 計 {len(rows)}")
    safe_print("=== 確定一覧 ===")
    for r in rows:
        if r["matched"] == "yes" and r["needs_review"] == "no":
            safe_print(f"  {r['company_name']:30} {r['official_url']}  ({r['method']})")


if __name__ == "__main__":
    main()
