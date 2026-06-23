# -*- coding: utf-8 -*-
"""製品ファクト抽出（Playwright版）= JS描画ページ対応・トークンゼロ。

requests 版 extract_product_facts.crawl_site が大手で 0件だった原因は JS 描画。
ヘッドレス Chromium でレンダリング後の DOM から同じ extract_nutrition を回す。
LLM は一切使わない（= トークン課金ゼロ）。病院プロジェクトと同じ Playwright 採用。

使い方:
  python extract_product_facts_pw.py --site https://www.aixia.jp/ --maker アイシア株式会社 --max-pages 12
  python extract_product_facts_pw.py --from-confirmed --only 大手  # maker_sites.csv の確定社へ
出力: data/product_facts_pw.csv（requests 版と同じ EXTRACT_FIELDS）
"""
from __future__ import annotations

import argparse
import csv
from collections import deque
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import html_cache
from catfood_common import DATA_DIR, log_line, safe_print, today_stamp
from catfood_nutrition_patterns import EXTRACT_FIELDS, extract_nutrition
from extract_product_facts import LINK_KEYWORDS, PAGE_TEXT_MIN_FIELDS, _link_score, _page_text

OUT = DATA_DIR / "product_facts_pw.csv"


def _same_domain(seed: str, url: str) -> bool:
    return urlparse(seed).netloc == urlparse(url).netloc


def crawl_site_pw(start: str, maker: str, max_pages: int, *, nav_timeout: int = 20000,
                  settle_ms: int = 1500) -> list[dict]:
    from playwright.sync_api import sync_playwright

    visited: set[str] = set()
    frontier: deque[str] = deque([start])
    found: list[dict] = []
    pages = 0
    stamp = today_stamp()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (compatible; CatFoodFactBot/0.1; research)",
            locale="ja-JP",
        )
        page = ctx.new_page()
        while frontier and pages < max_pages:
            url = frontier.popleft()
            if url in visited:
                continue
            visited.add(url)
            pages += 1
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout)
                try:
                    page.wait_for_load_state("networkidle", timeout=settle_ms)
                except Exception:
                    pass  # networkidle に達しなくても描画済みDOMで続行
                html = page.content()
            except Exception as exc:
                safe_print(f"   [skip] {type(exc).__name__} {url[:70]}")
                continue

            html_cache.write_cache(url, html)  # レンダリング済みHTMLもキャッシュ（再抽出・再開用）
            title, text = _page_text(html)
            data = extract_nutrition(text, url=url, name=title)
            if data["fields_found"] >= PAGE_TEXT_MIN_FIELDS:
                found.append({"maker": maker, "product_name": title[:80],
                              "url": url, "fetched_at": stamp, **data})
                safe_print(f"  [HIT {data['fields_found']}項目] {title[:36]} {url[:60]}")

            soup = BeautifulSoup(html, "html.parser")
            scored = []
            for a in soup.find_all("a", href=True):
                nxt = urljoin(url, a["href"]).split("#")[0]
                if not nxt.startswith("http") or not _same_domain(start, nxt):
                    continue
                if nxt in visited:
                    continue
                scored.append((_link_score(a.get_text(" ", strip=True), a["href"]), nxt))
            for _, nxt in sorted(scored, key=lambda x: -x[0]):
                if nxt not in frontier:
                    frontier.append(nxt)
        browser.close()

    safe_print(f"  巡回 {pages} ページ / 成分ページ {len(found)} 件（{maker}）[Playwright]")
    log_line("extract_product_facts_pw", f"site={start} maker={maker} pages={pages} hits={len(found)}")
    return found


def append_out(rows: list[dict]) -> None:
    new = not OUT.exists()
    with OUT.open("a", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=EXTRACT_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site")
    ap.add_argument("--maker", default="")
    ap.add_argument("--max-pages", type=int, default=12)
    args = ap.parse_args()
    if not args.site:
        ap.error("--site が必要です")
    rows = crawl_site_pw(args.site, args.maker or urlparse(args.site).netloc, args.max_pages)
    if rows:
        append_out(rows)
    n = len(rows)
    if n:
        p = sum(1 for r in rows if r.get("disclosed_phosphorus") == "yes")
        c = sum(1 for r in rows if r.get("disclosed_calorie") == "yes")
        safe_print(f"  -> リン開示 {p}/{n} / カロリー開示 {c}/{n}  ({OUT})")


if __name__ == "__main__":
    main()
