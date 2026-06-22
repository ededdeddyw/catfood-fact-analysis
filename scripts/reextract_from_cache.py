# -*- coding: utf-8 -*-
"""キャッシュHTMLから product_facts_raw.csv を再生成（ネット不要・一瞬）。

抽出ロジック（catfood_nutrition_patterns.py）を変えたら、これを回すだけで
全件再抽出できる。再取得しないので trickle ハングが起きない＝取得と抽出の分離。

対象URLの取り方:
  * 既存 product_facts_raw.csv の (url, maker) を土台にする（maker対応のため）。
  * その url がキャッシュにあれば再抽出して上書き、無ければ既存行を温存。
LLM不使用。
"""
from __future__ import annotations

import argparse
import csv

import html_cache
from catfood_common import DATA_DIR, safe_print, today_stamp
from catfood_nutrition_patterns import EXTRACT_FIELDS, extract_nutrition
from extract_product_facts import _page_text, PAGE_TEXT_MIN_FIELDS

FACTS = DATA_DIR / "product_facts_raw.csv"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-fields", type=int, default=PAGE_TEXT_MIN_FIELDS)
    args = ap.parse_args()

    if not FACTS.exists():
        safe_print("product_facts_raw.csv が無い。先にハーベストしてキャッシュを作ってください。")
        return
    old = list(csv.DictReader(FACTS.open(encoding="utf-8-sig", newline="")))
    stamp = today_stamp()
    new_rows, reextracted, kept, dropped = [], 0, 0, 0

    for r in old:
        url = r.get("url", "")
        maker = r.get("maker", "")
        html = html_cache.read_cache(url) if url else None
        if html is None:
            new_rows.append(r)  # キャッシュ無し→温存
            kept += 1
            continue
        title, text = _page_text(html)
        data = extract_nutrition(text, url=url, name=title)
        if data["fields_found"] < args.min_fields:
            dropped += 1  # 再抽出で成分が消えた→落とす
            continue
        new_rows.append({"maker": maker, "product_name": title[:80], "url": url,
                         "fetched_at": r.get("fetched_at") or stamp, **data})
        reextracted += 1

    with FACTS.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=EXTRACT_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(new_rows)

    cached_n = sum(1 for r in old if r.get("url") and html_cache.is_cached(r["url"]))
    safe_print(f"[reextract] 再抽出 {reextracted} / 温存(未キャッシュ) {kept} / 脱落 {dropped}")
    safe_print(f"[reextract] 既存{len(old)}行中 キャッシュ有り {cached_n}行 -> {FACTS}")


if __name__ == "__main__":
    main()
