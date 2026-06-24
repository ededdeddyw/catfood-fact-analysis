# -*- coding: utf-8 -*-
"""商品サムネイルを楽天商品検索APIから取得し、自前ホスト用にダウンロードする。

方針（このサイトの哲学に合わせる）:
  * アフィリ感の最小化＝公開サイトから楽天への通信を発生させない。画像は**ビルド時にDLして
    site/img/products/ に保存**し、配信は自前から。掲載順・内容に手数料は一切影響しない。
  * 出典必須＝どの楽天商品ページから取った画像かを data/product_images.csv に必ず残す（監査可能）。
  * 誤った商品画像を出さない＝**保守的マッチング**。一致度が低い候補は画像なしで通す
    （「記載なし」と同じ正直さ）。ユーザー合意済の方針。
  * LLM不使用（トークンゼロ）。requests のみ。礼儀正しく sleep + bounded timeout + 再開可能。

鍵: 環境変数 RAKUTEN_APP_ID（楽天デベロッパーの applicationId）。公開リポジトリには絶対に
    コミットしない。スクリプトは env から読むだけ。

使い方:
  RAKUTEN_APP_ID=xxxx PYTHONUTF8=1 python scripts/fetch_product_images.py            # 全件（再開可）
  RAKUTEN_APP_ID=xxxx PYTHONUTF8=1 python scripts/fetch_product_images.py --limit 10 # お試し
  ... --refresh   # 既存の判定を無視して取り直す
出力: data/product_images.csv（url→画像/出典）, site/img/products/<id>.jpg
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
import time
import unicodedata

import requests

from catfood_common import DATA_DIR, ROOT, safe_print, today_stamp, write_csv

CONSULT = DATA_DIR / "consult_sheet_cat.csv"
MAP_CSV = DATA_DIR / "product_images.csv"
IMG_DIR = ROOT / "site" / "img" / "products"
API = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"

MAP_FIELDS = ["product_url", "image_file", "source_item_url", "source_shop",
              "matched_name", "score", "fetched_at"]

# マッチ判定で無視する一般語（これらが一致しても加点しない）
_STOP = {"猫", "ねこ", "ネコ", "キャット", "cat", "用", "総合栄養食", "ペットフード",
         "フード", "キャットフード", "g", "kg", "袋", "本", "個", "缶", "パック", "入",
         "国産", "全年齢", "成猫", "子猫", "シニア", "高齢", "など", "その他"}


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "")).lower()


def sig_tokens(name: str) -> list[str]:
    """商品名から識別力のあるトークン（長さ2以上・一般語以外）を抽出。"""
    parts = re.split(r"[\s　・/／\|｜（）()【】\[\]、,。.　]+", name or "")
    out = []
    for p in parts:
        p = p.strip()
        if len(p) >= 2 and p not in _STOP and norm(p) not in {norm(x) for x in _STOP}:
            out.append(p)
    return out


def brand_token(maker: str) -> str:
    """会社名→検索・照合用のブランド核（法人格/ジャポン等を除く）。"""
    t = maker or ""
    for suf in ["株式会社", "合同会社", "有限会社", "（株）", "(株)", "ジャポン"]:
        t = t.replace(suf, "")
    return t.strip()


def score_item(prod_name: str, brand: str, item_name: str, shop: str) -> int:
    """候補商品名との一致度。識別トークンの含有数＋ブランド一致ボーナス。"""
    cand = norm(item_name) + " " + norm(shop)
    toks = sig_tokens(prod_name)
    hit = sum(1 for t in toks if norm(t) in cand)
    if brand and norm(brand) in cand:
        hit += 1
    return hit


def accept(prod_name: str, brand: str, item_name: str, shop: str) -> bool:
    """保守的に採用判定：識別トークン2つ以上一致（ブランド一致を含めて可）。"""
    return score_item(prod_name, brand, item_name, shop) >= 2


def img_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def upscale(img_url: str) -> str:
    """楽天サムネのサイズ指定(_ex=128x128)を少し大きめに。"""
    return re.sub(r"_ex=\d+x\d+", "_ex=300x300", img_url)


def read_app_id() -> str:
    """env優先、無ければ gitignore 済みの .env から RAKUTEN_APP_ID を読む（鍵をリポに残さない）。"""
    v = os.environ.get("RAKUTEN_APP_ID", "").strip()
    if v:
        return v
    from pathlib import Path
    cands = [ROOT / ".env"] + [p / ".env" for p in ROOT.parents[:3]] + [Path.cwd() / ".env"]
    for envf in cands:
        if envf.exists():
            for line in envf.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith("RAKUTEN_APP_ID") and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def load_map() -> dict[str, dict]:
    if not MAP_CSV.exists():
        return {}
    return {r["product_url"]: r
            for r in csv.DictReader(MAP_CSV.open(encoding="utf-8-sig", newline=""))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="先頭N件だけ（お試し）")
    ap.add_argument("--refresh", action="store_true", help="既存判定を無視して取り直す")
    args = ap.parse_args()

    app_id = read_app_id()
    if not app_id:
        safe_print("[STOP] RAKUTEN_APP_ID が見つかりません（環境変数 / リポジトリ直下の .env のどちらか）。")
        safe_print("  楽天デベロッパー(https://webservice.rakuten.co.jp/)で applicationId を取得し、")
        safe_print("  リポジトリ直下に .env を作り `RAKUTEN_APP_ID=xxxx` と書くか、環境変数で設定して再実行してください。")
        safe_print("  （.env は .gitignore 済み＝公開リポジトリには残りません）")
        sys.exit(2)

    products = list(csv.DictReader(CONSULT.open(encoding="utf-8-sig", newline="")))
    if args.limit:
        products = products[:args.limit]
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    done = {} if args.refresh else load_map()

    sess = requests.Session()
    sess.headers.update({"User-Agent": "CatFoodFactBot/0.1 (research; self-hosted thumbnails)"})

    n_new = n_img = n_skip = n_nomatch = 0
    for i, p in enumerate(products, 1):
        url = p["url"]
        name = p.get("product_name", "")
        if url in done and not args.refresh:
            n_skip += 1
            continue
        brand = brand_token(p.get("maker", ""))
        keyword = (name or brand).strip()[:128]
        rec = {"product_url": url, "image_file": "", "source_item_url": "",
               "source_shop": "", "matched_name": "", "score": "0",
               "fetched_at": today_stamp()}
        try:
            r = sess.get(API, params={
                "applicationId": app_id, "keyword": keyword, "hits": 10,
                "imageFlag": 1, "format": "json", "formatVersion": 2,
                "elements": "itemName,itemUrl,shopName,mediumImageUrls,smallImageUrls",
            }, timeout=15)
            data = r.json() if r.status_code == 200 else {}
        except (requests.RequestException, ValueError) as exc:
            safe_print(f"[FAIL] {name[:30]} ({type(exc).__name__})")
            data = {}
        items = data.get("Items", []) if isinstance(data, dict) else []

        best, best_sc = None, 1  # しきい値未満は不採用（=画像なし）
        for it in items:
            sc = score_item(name, brand, it.get("itemName", ""), it.get("shopName", ""))
            if sc > best_sc:
                best, best_sc = it, sc
        if best and accept(name, brand, best.get("itemName", ""), best.get("shopName", "")):
            imgs = best.get("mediumImageUrls") or best.get("smallImageUrls") or []
            img_url = ""
            if imgs:
                first = imgs[0]
                img_url = first.get("imageUrl", "") if isinstance(first, dict) else str(first)
            img_url = upscale(img_url)
            if img_url:
                fname = f"{img_id(url)}.jpg"
                try:
                    ir = sess.get(img_url, timeout=15)
                    if ir.status_code == 200 and ir.content:
                        (IMG_DIR / fname).write_bytes(ir.content)
                        rec.update({"image_file": f"img/products/{fname}",
                                    "source_item_url": best.get("itemUrl", ""),
                                    "source_shop": best.get("shopName", ""),
                                    "matched_name": best.get("itemName", "")[:120],
                                    "score": str(best_sc)})
                        n_img += 1
                except requests.RequestException:
                    safe_print(f"[IMG-FAIL] {name[:30]}")
                time.sleep(0.4)
        if not rec["image_file"]:
            n_nomatch += 1
        done[url] = rec
        n_new += 1
        if i % 25 == 0:
            safe_print(f"  ...{i}/{len(products)}  画像{n_img} 未マッチ{n_nomatch} スキップ{n_skip}")
            # 途中保存（オーファン耐性）
            write_csv(MAP_CSV, list(done.values()), MAP_FIELDS)
        time.sleep(1.1)  # 楽天APIのレート配慮（~1req/s）

    write_csv(MAP_CSV, list(done.values()), MAP_FIELDS)
    safe_print(f"[done] 取得{n_new} 画像{n_img} 未マッチ{n_nomatch} 既存スキップ{n_skip} → {MAP_CSV}")
    safe_print(f"  画像: {IMG_DIR}（自前ホスト・要コミット）")


if __name__ == "__main__":
    main()
