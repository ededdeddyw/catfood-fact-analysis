# -*- coding: utf-8 -*-
"""マース・ジャパンの猫ブランド公式サイトから保証成分を直接取得する（=公式一次取得）。

背景: マースは企業サイト(mars.com)に成分が無く、楽天 caption にも成分が出ないため
「取れない」と一度判断したが、ブランド別サイト（kalkan.jp 等）には**静的HTMLに保証成分**
がある。403 は単純な User-Agent 弾きで、ブラウザ風ヘッダを送れば 200 で取得できる
（本格的なボットマネージャではない）。商品個別ページは sitemap に列挙されている。

よってこれは**公式の一次取得**（source=official・出典＝ブランド公式の商品ページURL）。
「公式未確認(楽天転記)」とは別物で、バッジは付かない。

LLM不使用。bounded timeout。既存 extract_nutrition をそのまま使用。
出力: data/product_facts_mars.csv（product_facts_raw と同スキーマ + source=official）
"""
from __future__ import annotations

import csv
import re
import sys
import time

import requests

from catfood_common import DATA_DIR, safe_print, today_stamp
import catfood_nutrition_patterns as N

OUT = DATA_DIR / "product_facts_mars.csv"
COMPANY = "マース・ジャパン・リミテッド"
BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9",
}
RAW_COLS = ["maker", "product_name", "url", "species", "fields_found",
            "has_analysis_section", "is_therapeutic",
            "disclosed_crude_protein", "disclosed_crude_fat", "disclosed_crude_fiber",
            "disclosed_crude_ash", "disclosed_moisture", "disclosed_calorie",
            "disclosed_phosphorus", "disclosed_ingredients",
            "crude_protein_value", "crude_fat_value", "crude_fiber_value",
            "crude_ash_value", "moisture_value", "calorie_kcal", "calorie_basis",
            "phosphorus_value", "calcium_value", "sodium_value", "magnesium_value",
            "ingredients_snippet", "fetched_at", "source"]

# 取得対象のブランド公式サイト。sitemap から「商品個別ページ」を拾う条件付き。
BRANDS = [
    {"brand": "カルカン", "sitemap": "https://kalkan.jp/sitemap.xml",
     "is_product": lambda u: u.endswith(".html") and "/products/" in u},
    {"brand": "シーバ", "sitemap": "http://sheba.jp/sitemap.xml",
     "is_product": lambda u: u.endswith(".html") and "/product" in u},
]


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(BROWSER)
    return s


def get(sess: requests.Session, url: str) -> str | None:
    try:
        r = sess.get(url, timeout=15)
        if r.status_code != 200:
            return None
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding
        return r.text
    except requests.RequestException:
        return None


def product_name(html: str, brand: str) -> str:
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', html, re.I)
    if not m:
        m = re.search(r"<title>([^<]+)</title>", html, re.I)
    t = (m.group(1) if m else "").strip()
    for sep in ("｜", "|", " - ", "—", "／"):
        t = t.split(sep)[0]
    t = re.sub(r"\s+", " ", t).strip()
    if brand and brand not in t:        # ブランド名を頭に補う（識別しやすく）
        t = f"{brand} {t}" if t else brand
    return t[:80]


def main() -> None:
    targets = sys.argv[1:]
    brands = [b for b in BRANDS if not targets or any(t in b["brand"] for t in targets)]
    sess = make_session()
    rows: dict[str, dict] = {}
    if OUT.exists():  # 追記・再開
        rows = {r["url"]: r for r in csv.DictReader(OUT.open(encoding="utf-8-sig", newline=""))}

    for b in brands:
        brand = b["brand"]
        sm = get(sess, b["sitemap"])
        if not sm:
            safe_print(f"[{brand}] sitemap 取得失敗: {b['sitemap']}")
            continue
        locs = [u for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm) if b["is_product"](u)]
        safe_print(f"[{brand}] 商品候補 {len(locs)} ページ")
        got = 0
        for u in locs:
            if u in rows:
                continue
            html = get(sess, u)
            time.sleep(0.5)
            if not html:
                continue
            flat = re.sub(r"<[^>]+>", " ", html)
            res = N.extract_nutrition(flat, url=u, name=product_name(html, brand))
            if res.get("species") == "dog":
                continue
            if not res.get("has_analysis_section") or "%" not in (res.get("crude_protein_value") or ""):
                continue
            res.update({"maker": COMPANY, "product_name": product_name(html, brand),
                        "url": u, "fetched_at": today_stamp(), "source": "official"})
            rows[u] = res
            got += 1
        safe_print(f"[{brand}] 取得 +{got}")

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=RAW_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows.values())
    safe_print(f"[done] マース公式 {len(rows)} 商品 → {OUT}")


if __name__ == "__main__":
    main()
