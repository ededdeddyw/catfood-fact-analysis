"""製品ファクト抽出クローラ（保証分析値・カロリー・リン・原材料）

LLM 不使用。2モード:
  1) --site URL --maker NAME : メーカーサイトを浅く巡回し、保証分析値が載っている
                               ページを自動発見して抽出（病院 deep_crawl と同思想）
  2) --seed CSV              : 既知の製品URL一覧（列: maker,product_name,url）から抽出

出力: catfood/data/product_facts_raw.csv （02 オーディットのスキーマ）
礼儀: 同一ドメインのみ・sleep・max-pages 上限・失敗ログ。

使い方例:
  python extract_product_facts.py --site https://www.example.co.jp/ --maker 例社 --max-pages 30
  python extract_product_facts.py --seed ../data/seed_product_urls.csv
"""
from __future__ import annotations

import argparse
import csv
from collections import deque
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import html_cache
from catfood_common import DATA_DIR, log_line, polite_get, safe_print, today_stamp, write_csv
from catfood_nutrition_patterns import EXTRACT_FIELDS, extract_nutrition

# 製品/成分ページに繋がりやすいリンクの優先語
LINK_KEYWORDS = [
    "product", "item", "goods", "lineup", "brand", "catfood", "cat",
    "商品", "製品", "成分", "ラインアップ", "ラインナップ", "詳細",
]
PAGE_TEXT_MIN_FIELDS = 2  # この数以上の栄養項目が取れたら「成分ページ」として採用


def _same_domain(seed: str, url: str) -> bool:
    return urlparse(seed).netloc == urlparse(url).netloc


def _page_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title else ""
    # script/style 除去
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return title, soup.get_text(" ", strip=True)


def _link_score(text: str, href: str) -> int:
    blob = (text + " " + href).lower()
    return sum(1 for k in LINK_KEYWORDS if k.lower() in blob)


def crawl_site(start: str, maker: str, max_pages: int, sleep: float,
               timeout=(8, 15), retries: int = 1) -> list[dict]:
    visited: set[str] = set()
    frontier: deque[str] = deque([start])
    found: list[dict] = []
    pages = 0
    stamp = today_stamp()

    while frontier and pages < max_pages:
        url = frontier.popleft()
        if url in visited:
            continue
        visited.add(url)
        html, _from_cache = html_cache.fetch(url, sleep=sleep, timeout=timeout, retries=retries)
        pages += 1
        if html is None:
            continue
        title, text = _page_text(html)

        data = extract_nutrition(text, url=url, name=title)
        if data["fields_found"] >= PAGE_TEXT_MIN_FIELDS:
            row = {
                "maker": maker,
                "product_name": title[:80],
                "url": url,
                "fetched_at": stamp,
                **data,
            }
            found.append(row)
            safe_print(f"  [HIT {data['fields_found']}項目] {title[:40]} {url}")

        # 同一ドメインのリンクをスコア順に追加
        soup = BeautifulSoup(html, "html.parser")
        scored = []
        for a in soup.find_all("a", href=True):
            nxt = urljoin(url, a["href"]).split("#")[0]
            if not nxt.startswith("http") or not _same_domain(start, nxt):
                continue
            if nxt in visited:
                continue
            scored.append((_link_score(a.get_text(" ", strip=True), a["href"]), nxt))
        # スコア高い順に frontier へ
        for _, nxt in sorted(scored, key=lambda x: -x[0]):
            if nxt not in frontier:
                frontier.append(nxt)

    safe_print(f"  巡回 {pages} ページ / 成分ページ {len(found)} 件（{maker}）")
    log_line("extract_product_facts", f"site={start} maker={maker} pages={pages} hits={len(found)}")
    return found


def from_seed(seed_path: str, sleep: float) -> list[dict]:
    rows = list(csv.DictReader(open(seed_path, encoding="utf-8-sig")))
    out: list[dict] = []
    stamp = today_stamp()
    for r in rows:
        url = r.get("url", "").strip()
        if not url:
            continue
        resp = polite_get(url, sleep=sleep)
        if resp is None:
            continue
        title, text = _page_text(resp.text)
        data = extract_nutrition(text)
        out.append({
            "maker": r.get("maker", ""),
            "product_name": r.get("product_name") or title[:80],
            "url": url,
            "fetched_at": stamp,
            **data,
        })
        safe_print(f"  [{data['fields_found']}項目] {r.get('product_name') or title[:30]}")
    return out


def summarize(rows: list[dict]) -> None:
    if not rows:
        safe_print("（抽出0件）")
        return
    n = len(rows)
    safe_print(f"\n=== 開示率サマリ（{n}ページ）===")
    for f in ["crude_protein", "crude_fat", "crude_fiber", "crude_ash",
              "moisture", "calorie", "phosphorus", "ingredients"]:
        c = sum(1 for r in rows if r.get(f"disclosed_{f}") == "yes")
        safe_print(f"  {f:16} {c:3}/{n}  ({100*c//n}%)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", help="メーカーサイトのトップURL")
    ap.add_argument("--maker", default="", help="メーカー名（--site と併用）")
    ap.add_argument("--seed", help="製品URL一覧CSV（maker,product_name,url）")
    ap.add_argument("--max-pages", type=int, default=30)
    ap.add_argument("--sleep", type=float, default=1.5)
    ap.add_argument("--out", default=str(DATA_DIR / "product_facts_raw.csv"))
    ap.add_argument("--append", action="store_true", help="既存CSVに追記")
    args = ap.parse_args()

    rows: list[dict] = []
    if args.site:
        rows = crawl_site(args.site, args.maker or urlparse(args.site).netloc,
                          args.max_pages, args.sleep)
    elif args.seed:
        rows = from_seed(args.seed, args.sleep)
    else:
        ap.error("--site か --seed のどちらかが必要です")

    from pathlib import Path
    out = Path(args.out)
    if args.append and out.exists():
        existing = list(csv.DictReader(open(out, encoding="utf-8-sig")))
        rows = existing + rows
    write_csv(out, rows, EXTRACT_FIELDS)
    summarize(rows)


if __name__ == "__main__":
    main()
