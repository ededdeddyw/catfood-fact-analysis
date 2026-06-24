# -*- coding: utf-8 -*-
"""未取得メーカーの「本当に取れないか」調査ツール（取得はしない・偵察のみ）。

各メーカーについて:
  1. robots.txt と sitemap.xml / sitemap_index.xml を探索（gz対応・index再帰）
  2. sitemap 内の URL 数と「商品詳細っぽい」URL 数を数える
  3. 詳細候補ページを少数だけ取得し、静的HTMLに保証成分(たんぱく質等)があるか判定
  4. 公式トップ自体も取得し、成分の有無＋リンク数（JSシェルかの目安）を見る

判定:
  STATIC-OK  … sitemapに詳細があり静的HTMLに成分あり → harvest_sitemap_products で取れる見込み
  SITEMAP    … sitemapに詳細URLはあるが成分は静的に出ない → 個別確認/Playwright
  JS/NONE    … sitemapが無い/商品が拾えない → Playwright or 別ソース(楽天等)

LLM不使用。bounded timeout。出力は表示のみ（ファイルは書かない）。
"""
from __future__ import annotations

import csv
import gzip
import re
import sys
from urllib.parse import urljoin, urlparse

import requests

from catfood_common import DATA_DIR, safe_print

MAKERS_CSV = DATA_DIR / "maker_sites.csv"
HDR = {"User-Agent": "Mozilla/5.0 (compatible; CatFoodFactBot/0.1; coverage-probe)"}
NUTRI = re.compile(r"(粗?たんぱく質|粗蛋白|保証分析|成分値|粗脂肪)")
DETAIL_HINT = re.compile(r"(product|products|item|items|detail|lineup|goods|catalog|/cat|food)", re.I)


def get(url: str, timeout: int = 10, binary: bool = False):
    try:
        r = requests.get(url, headers=HDR, timeout=timeout)
        if r.status_code != 200:
            return None
        if binary:
            return r.content
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding
        return r.text
    except requests.RequestException:
        return None


def sitemap_locs(base: str, cap: int = 3000) -> list[str]:
    """robots + 既定の sitemap 位置から <loc> を集める（gz・index再帰対応）。"""
    seen_maps, locs = set(), []
    queue = []
    robots = get(urljoin(base, "/robots.txt"))
    if robots:
        for line in robots.splitlines():
            if line.lower().startswith("sitemap:"):
                queue.append(line.split(":", 1)[1].strip())
    queue += [urljoin(base, "/sitemap.xml"), urljoin(base, "/sitemap_index.xml"),
              urljoin(base, "/sitemap-index.xml"), urljoin(base, "/wp-sitemap.xml")]
    while queue and len(locs) < cap:
        sm = queue.pop(0)
        if sm in seen_maps:
            continue
        seen_maps.add(sm)
        raw = get(sm, binary=sm.endswith(".gz"))
        if raw is None:
            continue
        if isinstance(raw, bytes):
            try:
                raw = gzip.decompress(raw).decode("utf-8", "replace")
            except OSError:
                continue
        found = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", raw)
        if "<sitemapindex" in raw.lower():
            queue += found  # ネストした sitemap
        else:
            locs += found
    return locs


def probe(name: str, url: str) -> dict:
    parsed = urlparse(url)
    base = f"{parsed.scheme or 'https'}://{parsed.netloc}"
    res = {"name": name, "base": base, "verdict": "JS/NONE",
           "n_locs": 0, "n_detail": 0, "static_hit": 0, "checked": 0, "home_nutri": False}
    home = get(url) or get(base)
    if home:
        res["home_nutri"] = bool(NUTRI.search(home))
        res["home_links"] = len(re.findall(r"<a\s", home, re.I))
    locs = sitemap_locs(base)
    res["n_locs"] = len(locs)
    details = [u for u in locs if DETAIL_HINT.search(urlparse(u).path)]
    # ざっくり leaf 寄り（末尾が長い・数字や品番っぽい）を優先
    details.sort(key=lambda u: (-len(urlparse(u).path), u))
    res["n_detail"] = len(details)
    for u in details[:4]:
        html = get(u)
        res["checked"] += 1
        if html and NUTRI.search(html):
            res["static_hit"] += 1
    if res["static_hit"] > 0:
        res["verdict"] = "STATIC-OK"
    elif res["n_detail"] > 0:
        res["verdict"] = "SITEMAP"
    elif res["home_nutri"]:
        res["verdict"] = "HOME-NUTRI?"
    return res


def main() -> None:
    targets = sys.argv[1:]  # 会社名（部分一致）。無ければ全未取得。
    sites = {r["company_name"]: r for r in csv.DictReader(MAKERS_CSV.open(encoding="utf-8-sig", newline=""))}
    prods = set(r["maker"] for r in csv.DictReader((DATA_DIR / "consult_sheet_cat.csv").open(encoding="utf-8-sig", newline="")))
    confirmed = [r for r in sites.values() if r.get("matched") == "yes" and r.get("needs_review") == "no"]
    no_data = [r for r in confirmed if r["company_name"] not in prods and r.get("official_url")]
    if targets:
        no_data = [r for r in no_data if any(t in r["company_name"] for t in targets)]
    safe_print(f"=== probe {len(no_data)} makers ===")
    safe_print(f"{'verdict':<12}{'detail':>7}{'static':>7}{'locs':>7}  name / base")
    for r in no_data:
        res = probe(r["company_name"], r["official_url"])
        safe_print(f"{res['verdict']:<12}{res['n_detail']:>7}"
                   f"{res['static_hit']}/{res['checked']:>3}{res['n_locs']:>7}  "
                   f"{res['name'][:20]} | {res['base']}")


if __name__ == "__main__":
    main()
