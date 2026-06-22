# -*- coding: utf-8 -*-
"""sitemap から製品詳細URLを列挙し、静的取得で保証成分を抽出（トークンゼロ）。

大手は製品詳細ページに保証成分が**静的HTMLで**載っている（実証済み・docs/04 追記）。
監査が0件だったのはトップからのBFSが詳細URLに到達しなかっただけ。sitemap には
詳細URLが列挙されているので、そこから直接叩けば Playwright すら不要で取れる。

対応: sitemap インデックスの再帰、.gz 解凍、URL パターン絞り込み。
出力: data/product_facts_raw.csv（--append 既存に追記）。LLM 不使用。
"""
from __future__ import annotations

import argparse
import csv
import gzip
import re

from bs4 import BeautifulSoup

from catfood_common import DATA_DIR, log_line, polite_get, safe_print, today_stamp
from catfood_nutrition_patterns import EXTRACT_FIELDS, extract_nutrition
from extract_product_facts import PAGE_TEXT_MIN_FIELDS, _page_text

OUT = DATA_DIR / "product_facts_raw.csv"

# メーカー別の sitemap 起点と詳細URLパターン（sitemap 調査で確定済み）
SOURCES: dict[str, dict] = {
    "アイシア株式会社": {
        "sitemaps": ["https://www.aixia.jp/sitemap-externals.xml"],
        "pattern": r"/product/detail",
    },
    "いなばペットフード株式会社": {
        "sitemaps": ["https://www.inaba-petfood.co.jp/sitemap.xml"],
        "pattern": r"/product/detail",
    },
    "日本ペットフード株式会社": {
        "sitemaps": ["https://www.npf.co.jp/cms/sitemap/www/Sitemap_2_Article_catfood_1.xml.gz"],
        "pattern": r"cat-detail",
    },
    # 療法食/プレミアム大手。RC は専用 sitemap-products.xml に猫製品が並ぶ（静的で保証成分取得可）。
    "ロイヤルカナンジャポン合同会社": {
        "sitemaps": ["https://www.royalcanin.com/jp/ja-jp/sitemap/sitemap-products.xml"],
        "pattern": r"/jp/cats/products/",
    },
    # ヒルズは製品一覧がJS描画で sitemap に個別製品が無い → 別途Playwright/API対応が必要（保留）。
}

LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


def fetch_xml(url: str) -> str:
    r = polite_get(url, retries=2, sleep=0.4, timeout=(8, 20))
    if r is None:
        return ""
    if url.endswith(".gz"):
        try:
            return gzip.decompress(r.content).decode("utf-8", "replace")
        except Exception as exc:
            safe_print(f"   [gz fail] {type(exc).__name__} {url}")
            return ""
    return r.text


def harvest_urls(sitemaps: list[str], pattern: str, *, max_depth: int = 2) -> list[str]:
    """sitemap（インデックス再帰・gz対応）から pattern 一致URLを集める。"""
    pat = re.compile(pattern)
    seen: set[str] = set()
    out: list[str] = []
    queue = [(s, 0) for s in sitemaps]
    while queue:
        sm, depth = queue.pop(0)
        locs = LOC_RE.findall(fetch_xml(sm))
        children = [u for u in locs if u.endswith(".xml") or u.endswith(".xml.gz")]
        details = [u for u in locs if pat.search(u)]
        for u in details:
            if u not in seen:
                seen.add(u)
                out.append(u)
        if not details and children and depth < max_depth:
            queue.extend((c, depth + 1) for c in children)
    return out


def extract_url(url: str, maker: str, stamp: str) -> dict | None:
    r = polite_get(url, retries=1, sleep=0.8, timeout=(8, 20))
    if r is None:
        return None
    title, text = _page_text(r.text)
    data = extract_nutrition(text, url=url, name=title)
    if data["fields_found"] < PAGE_TEXT_MIN_FIELDS:
        return None
    return {"maker": maker, "product_name": title[:80], "url": url,
            "fetched_at": stamp, **data}


def append_rows(rows: list[dict]) -> None:
    new = not OUT.exists()
    with OUT.open("a", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=EXTRACT_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--maker", help="SOURCES のキー1社のみ。未指定なら全社")
    ap.add_argument("--limit", type=int, default=0, help="社あたり詳細ページ数の上限（0=全件）")
    ap.add_argument("--list", action="store_true", help="URL列挙のみ（取得しない）")
    args = ap.parse_args()

    makers = [args.maker] if args.maker else list(SOURCES)
    stamp = today_stamp()
    grand = 0
    for maker in makers:
        cfg = SOURCES[maker]
        urls = harvest_urls(cfg["sitemaps"], cfg["pattern"])
        if args.limit:
            urls = urls[: args.limit]
        safe_print(f"\n[{maker}] 詳細URL {len(urls)} 件")
        if args.list:
            for u in urls[:5]:
                safe_print(f"   {u}")
            continue
        rows: list[dict] = []
        for i, u in enumerate(urls, 1):
            row = extract_url(u, maker, stamp)
            if row:
                rows.append(row)
            if i % 20 == 0:
                safe_print(f"   ...{i}/{len(urls)}  抽出 {len(rows)}")
        append_rows(rows)
        p = sum(1 for r in rows if r.get("disclosed_phosphorus") == "yes")
        safe_print(f"[{maker}] 成分ページ {len(rows)}/{len(urls)} / リン開示 {p}")
        log_line("harvest_sitemap_products", f"{maker} urls={len(urls)} hits={len(rows)} P={p}")
        grand += len(rows)
    safe_print(f"\n[done] 追記 {grand} ページ -> {OUT}")


if __name__ == "__main__":
    main()
