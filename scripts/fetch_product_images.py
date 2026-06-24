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
# 新 Rakuten Developers API（2026-04-01）。認証は applicationId(UUID)＋accessKey(pk_…)の2つ。
API = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260401"

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


# 会社名に出てこないサブブランド（CIAO/MiawMiaw/コンボ等）。スコア2の弱マッチを
# 「ちゃんとそのメーカーの商品か」で絞るための辞書。会社名一致 or これらで brand_ok。
SUB_BRANDS = {
    "アイシア株式会社": ["miawmiaw", "ミャウミャウ", "健康缶", "黒缶", "金缶", "純缶", "旨缶"],
    "日本ペットフード株式会社": ["コンボ", "combo", "ラシーネ", "ミオ", "mio", "ビューティープロ", "金のスープ"],
    "いなばペットフード株式会社": ["ciao", "チャオ", "ちゃお", "ちゅーる", "ちゅ〜る", "ちゅ~る",
                                   "ちゅるビ", "前浜", "焼かつお", "焼ささみ", "金のだし", "とろみ"],
    "ロイヤルカナンジャポン合同会社": ["royalcanin", "royal canin"],
    "ペットライン株式会社": ["メディファス", "キャネット", "medyfas"],
}


def is_dog_only(text: str) -> bool:
    """候補が明らかに犬用（猫の表記が無い）なら True。猫DBに対する誤マッチを弾く。"""
    t = norm(text)
    return ("犬" in (text or "")) and not any(k in (text or "") for k in ("猫", "キャット", "ｷｬｯﾄ")) and ("cat" not in t)


def brand_ok(maker: str, cand: str) -> bool:
    """候補に会社名核 or サブブランド名が含まれるか（弱マッチの裏取り）。"""
    c = norm(cand)
    if norm(brand_token(maker)) in c:
        return True
    return any(norm(a) in c for a in SUB_BRANDS.get(maker, []))


def accept(prod_name: str, maker: str, item_name: str, shop: str) -> bool:
    """採用判定。犬用は除外。識別トークン2つ以上。スコア2の弱マッチは
    会社名/サブブランド一致を必須にして誤画像（別ブランド・汎用サプリ）を弾く。"""
    cand = f"{item_name} {shop}"
    if is_dog_only(cand):
        return False
    sc = score_item(prod_name, brand_token(maker), item_name, shop)
    if sc < 2:
        return False
    if sc == 2 and not brand_ok(maker, cand):
        return False
    return True


def img_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def upscale(img_url: str) -> str:
    """楽天サムネのサイズ指定(_ex=128x128)を少し大きめに。"""
    return re.sub(r"_ex=\d+x\d+", "_ex=300x300", img_url)


def clean_item_url(item_url: str) -> str:
    """itemUrl からクエリ（rafcid 等のアフィリ/トラッキングID）を除去して素のURLにする。
    出典は素の商品ページだけ残す＝アフィリ遮断の方針に沿う。"""
    return (item_url or "").split("?", 1)[0]


def read_env_value(name: str) -> str:
    """env優先、無ければ gitignore 済みの .env から name の値を読む（鍵をリポに残さない）。"""
    v = os.environ.get(name, "").strip()
    if v:
        return v
    from pathlib import Path
    cands = [ROOT / ".env"] + [p / ".env" for p in ROOT.parents[:3]] + [Path.cwd() / ".env"]
    for envf in cands:
        if envf.exists():
            # utf-8-sig で BOM を除去（PowerShell の -Encoding utf8 が付けても読めるように）
            for line in envf.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                line = line.strip().lstrip("﻿")
                if line.startswith(name) and "=" in line:
                    k, val = line.split("=", 1)
                    if k.strip() == name:
                        return val.strip().strip('"').strip("'")
    return ""


def read_app_id() -> str:
    return read_env_value("RAKUTEN_APP_ID")


def read_access_key() -> str:
    return read_env_value("RAKUTEN_ACCESS_KEY")


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
    access_key = read_access_key()
    if not app_id or not access_key:
        safe_print("[STOP] 認証情報が不足しています（新 Rakuten Developers API は2つ必要）。")
        safe_print(f"  RAKUTEN_APP_ID     : {'OK' if app_id else '未設定'}（Application ID = UUID）")
        safe_print(f"  RAKUTEN_ACCESS_KEY : {'OK' if access_key else '未設定'}（Access Key = pk_…）")
        safe_print("  リポジトリ直下の .env に2行とも書くか、環境変数で設定して再実行してください。")
        safe_print("  （.env は .gitignore 済み＝公開リポジトリには残りません）")
        sys.exit(2)

    products = list(csv.DictReader(CONSULT.open(encoding="utf-8-sig", newline="")))
    if args.limit:
        products = products[:args.limit]
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    done = {} if args.refresh else load_map()

    # 新APIは登録済み「許可されたWebサイト」と一致する Referer ＋ Origin が必須（無いと403）。
    # 既定はアプリ登録URL。別アプリなら .env の RAKUTEN_REFERER で上書き可能。
    referer = read_env_value("RAKUTEN_REFERER") or "https://spontaneous-cupcake-03e95a.netlify.app/"
    m = re.match(r"(https?://[^/]+)", referer)
    origin = m.group(1) if m else referer.rstrip("/")

    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "CatFoodFactBot/0.1 (research; self-hosted thumbnails)",
        "Referer": referer, "Origin": origin,
    })

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
        data, http_err = {}, False
        for attempt in range(2):  # 429/5xx は一度だけ長め sleep でリトライ
            try:
                r = sess.get(API, params={
                    "applicationId": app_id, "accessKey": access_key,
                    "keyword": keyword, "hits": 10,
                    "format": "json", "formatVersion": 2,
                }, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    break
                if r.status_code in (429, 500, 502, 503) and attempt == 0:
                    time.sleep(3.0)
                    continue
                http_err = True
                safe_print(f"[HTTP {r.status_code}] {name[:28]}")
                break
            except (requests.RequestException, ValueError) as exc:
                http_err = True
                safe_print(f"[FAIL] {name[:30]} ({type(exc).__name__})")
                break
        if http_err:  # 通信失敗は記録しない＝再実行(--refreshなし)で再挑戦できる
            time.sleep(1.1)
            continue
        # 新APIは items(小文字)。旧形式 Items も一応見る。
        items = (data.get("items") or data.get("Items") or []) if isinstance(data, dict) else []

        best, best_sc = None, 1  # しきい値未満は不採用（=画像なし）
        for it in items:
            sc = score_item(name, brand, it.get("itemName", ""), it.get("shopName", ""))
            if sc > best_sc:
                best, best_sc = it, sc
        if best and accept(name, p.get("maker", ""), best.get("itemName", ""), best.get("shopName", "")):
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
                                    "source_item_url": clean_item_url(best.get("itemUrl", "")),
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
