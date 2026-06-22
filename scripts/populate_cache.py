# -*- coding: utf-8 -*-
"""既存 product_facts_raw.csv の URL を HTML キャッシュへ充填する。

これを一度通せば、以後 reextract_from_cache.py で**ネット不要・無ハング**に再抽出できる。
キャッシュ優先なので、途中で固まって kill しても再実行すれば既取得分は即スキップ＝再開可能。
LLM不使用。
"""
from __future__ import annotations

import csv

import html_cache
from catfood_common import DATA_DIR, safe_print

FACTS = DATA_DIR / "product_facts_raw.csv"


def main() -> None:
    urls = []
    seen = set()
    with FACTS.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            u = (r.get("url") or "").strip()
            if u and u not in seen:
                seen.add(u)
                urls.append(u)
    todo = [u for u in urls if not html_cache.is_cached(u)]
    safe_print(f"[populate] 全{len(urls)}URL / 未キャッシュ {len(todo)}")
    done = 0
    for i, u in enumerate(todo, 1):
        html, from_cache = html_cache.fetch(u, retries=1, sleep=0.5, timeout=(8, 15))
        if html is not None:
            done += 1
        if i % 25 == 0:
            safe_print(f"   {i}/{len(todo)}  cached={done}")
    cached_total = sum(1 for u in urls if html_cache.is_cached(u))
    safe_print(f"[populate] 完了 今回{done} / 累計キャッシュ {cached_total}/{len(urls)}")


if __name__ == "__main__":
    main()
