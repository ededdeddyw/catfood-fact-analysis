# -*- coding: utf-8 -*-
"""大手メーカーの成分を「楽天商品検索の商品説明(itemCaption)」から取得する（ハック経路）。

なぜ:
  公式サイトがJS描画/別ブランドサイトに分散していて静的取得できない大手
  （ヒルズ/ネスレ ピュリナ/マース/ユニチャーム/はごろも/スペクトラム 等）でも、
  楽天の商品説明には公式の保証分析値が転記されていることが多い。既存の
  catfood_nutrition_patterns.extract_nutrition() がそのままパースできる。

出典の正直さ（重要・docs/03の精神を守る）:
  これは公式ページからの一次取得では**ない**。出典＝楽天商品ページ＝出品者による
  「公式の保証分析値の転記」であり**公式未確認**。よって本スクリプトの出力には
  source="rakuten" を必ず付け、サイト上で「公式未確認（楽天転記）」と明示する。
  公式が後で取れたら公式優先で差し替える（build_consult_sheet がマージ時に優先）。

認証は fetch_product_images.py と同じ（新Rakuten API・applicationId+accessKey+Referer/Origin、
鍵は gitignore 済み .env）。LLM不使用・bounded timeout・再開可能（既存出力に追記）。

使い方:
  PYTHONUTF8=1 python scripts/harvest_rakuten_majors.py            # 既定の大手を取得
  PYTHONUTF8=1 python scripts/harvest_rakuten_majors.py ヒルズ ネスレ  # 会社名部分一致で限定
出力: data/product_facts_rakuten.csv（product_facts_raw と同スキーマ + source 列）
"""
from __future__ import annotations

import csv
import re
import sys
import time
import unicodedata

import requests

from catfood_common import DATA_DIR, safe_print, today_stamp
import catfood_nutrition_patterns as N
import fetch_product_images as IMG  # 認証・エンドポイント・clean_item_url を再利用

OUT = DATA_DIR / "product_facts_rakuten.csv"
RAW_COLS = ["maker", "product_name", "url", "species", "fields_found",
            "has_analysis_section", "is_therapeutic",
            "disclosed_crude_protein", "disclosed_crude_fat", "disclosed_crude_fiber",
            "disclosed_crude_ash", "disclosed_moisture", "disclosed_calorie",
            "disclosed_phosphorus", "disclosed_ingredients",
            "crude_protein_value", "crude_fat_value", "crude_fiber_value",
            "crude_ash_value", "moisture_value", "calorie_kcal", "calorie_basis",
            "phosphorus_value", "calcium_value", "sodium_value", "magnesium_value",
            "ingredients_snippet", "fetched_at", "source"]

# 取得対象の大手。company は maker_sites.csv の company_name と完全一致させること
# （メーカー別ページ・カバレッジに正しく紐づくため）。brands は (検索語, 必須トークン)。
# 必須トークンが itemName に無い候補は捨てる（別ブランド混入を防ぐ）。
MAJORS = [
    {"company": "日本ヒルズ・コルゲート株式会社", "brands": [
        ("サイエンスダイエット 猫 ドライ", "サイエンスダイエット"),
        ("サイエンスダイエット 猫 室内猫", "サイエンスダイエット"),
        ("サイエンスダイエット 猫 避妊", "サイエンスダイエット"),
        ("サイエンスダイエット 猫 シニア", "サイエンスダイエット"),
    ]},
    {"company": "ネスレ日本株式会社　ネスレピュリナペットケア", "brands": [
        ("モンプチ クリスピーキッス ドライ", "モンプチ"),
        ("ピュリナワン 猫 ドライ", "ピュリナワン"),
        ("ピュリナ プロプラン 猫 ドライ", "プロプラン"),
        ("フィリックス 猫 ドライ", "フィリックス"),
        ("モンプチ バッグ ドライ 猫", "モンプチ"),
    ]},
    {"company": "マース・ジャパン・リミテッド", "brands": [
        ("カルカン 猫 ドライ", "カルカン"),
        ("ニュートロ シュプレモ 猫 ドライ", "ニュートロ"),
        ("ニュートロ ナチュラルチョイス 猫", "ニュートロ"),
        ("シーバ ドライ 猫", "シーバ"),
    ]},
    {"company": "ユニ・チャーム株式会社", "brands": [
        ("銀のスプーン 猫 ドライ", "銀のスプーン"),
        ("銀のスプーン 三ツ星グルメ 猫", "銀のスプーン"),
        ("AllWell 猫 ドライ", "allwell"),
    ]},
    {"company": "はごろもフーズ株式会社", "brands": [
        ("無一物 猫 パウチ", "無一物"),
        ("無一物 ねこまんま 猫", "無一物"),
    ]},
    # 注: ブランド帰属が確実なメーカーだけを入れること（誤帰属は出典の信頼を損なう）。
    # スペクトラム ブランズ ジャパンは公式が 8in1 のみで、ナチュラルバランス/アイムスは
    # 扱っていないため除外（2026-06-24 公式サイトで確認）。マースは現状 caption に成分が
    # 出ず0件（ウェット中心）だが、ブランド帰属自体は正しいので設定だけ残す。
]


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "")).lower()


def clean_title(name: str, brand: str = "") -> str:
    """楽天の出品名から商品名を整える（販促/数量/容量/SEO尾部を除去）。
    ブランド名が分かる場合は、その手前の販促文（当選確率2分の1！等）を丸ごと落とす。"""
    t = unicodedata.normalize("NFKC", name or "")  # ｜→| 等も正規化
    t = t.split("|")[0]                              # ｜以降のSEOキーワード列を切る
    t = re.sub(r"[【\[「][^】\]」]*[】\]」]", " ", t)  # 【送料無料】[ ]「」
    if brand:                                        # ブランド名の手前（=販促）を捨てる
        i = t.lower().find(brand.lower())
        if i > 0:
            t = t[i:]
    t = re.sub(r"[（(][^）)]*[）)]", " ", t)          # (60g*24袋) 等
    t = re.sub(r"(キャットフード|ペットフード|送料無料|お買い得|まとめ買い|ケース販売|"
               r"ポイント\d*倍|限定|当選確率|あす楽|関東当日便|翌日配達|最大\d+%?|\d+等|"
               r"\d+分の\d+|％?OFF|お試し)", " ", t)
    t = re.sub(r"\d+(\.\d+)?\s*(kg|g|袋|缶|個|本|箱|p|ml)\b", " ", t, flags=re.I)
    t = re.sub(r"[×x*]\s*\d+\s*(袋|缶|個|本|箱|セット|ケース)?", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s[×xX*](\s|$)", " ", t)            # 孤立した×を除去
    # 末尾の検索語エコー/一般語（猫 ドライ ヒルズ 等）を剥がす（form等は別表示なので安全）
    tail = {"猫", "猫用", "ねこ", "ドライ", "ウェット", "パウチ", "フード", "キャットフード",
            "用", "総合栄養食", "国産", "無添加", "ヒルズ", "ネスレ", "マース", "ユニチャーム",
            "はごろも", "ピュリナ"}
    toks = t.split()
    while len(toks) > 2 and toks[-1] in tail:
        toks.pop()
    t = " ".join(toks).strip(" 　・-/|!！")
    return t[:70]


# 重複の元になる多パック/詰め合わせ出品（単品は別途拾えるので除外）
_BUNDLE = re.compile(r"(セット|ケース|まとめ|詰め合わせ|大容量|個セット|種類セット)")


def dedup_key(maker: str, cleaned_name: str) -> str:
    """同一商品の重複（出品者違い・容量違い）をまとめるためのキー。整形済み名を渡すこと。"""
    t = re.sub(r"[\s　・/|,.。、]+", "", norm(cleaned_name))
    return f"{maker}|{t}"


def search(app: str, key: str, sess: requests.Session, keyword: str) -> list[dict]:
    try:
        r = sess.get(IMG.API, params={
            "applicationId": app, "accessKey": key, "keyword": keyword[:128],
            "hits": 30, "format": "json", "formatVersion": 2,
            "elements": "itemName,itemCaption,itemUrl,shopName",
        }, timeout=15)
        if r.status_code != 200:
            safe_print(f"  [HTTP {r.status_code}] {keyword}")
            return []
        d = r.json()
        return d.get("Items") or d.get("items") or []
    except (requests.RequestException, ValueError) as exc:
        safe_print(f"  [FAIL] {keyword} ({type(exc).__name__})")
        return []


def load_existing() -> dict[str, dict]:
    if not OUT.exists():
        return {}
    return {r["url"]: r for r in csv.DictReader(OUT.open(encoding="utf-8-sig", newline=""))}


def main() -> None:
    targets = sys.argv[1:]
    majors = [m for m in MAJORS if not targets or any(t in m["company"] for t in targets)]
    app, key = IMG.read_app_id(), IMG.read_access_key()
    if not app or not key:
        safe_print("[STOP] RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY が必要（.env か環境変数）。")
        sys.exit(2)
    referer = IMG.read_env_value("RAKUTEN_REFERER") or "https://spontaneous-cupcake-03e95a.netlify.app/"
    m = re.match(r"(https?://[^/]+)", referer)
    origin = m.group(1) if m else referer.rstrip("/")
    sess = requests.Session()
    sess.headers.update({"User-Agent": "CatFoodFactBot/0.1 (research)",
                         "Referer": referer, "Origin": origin})

    rows = load_existing()                 # url -> row（再開・追記）
    seen = {dedup_key(r["maker"], r["product_name"]) for r in rows.values()}
    kept = 0
    for mj in majors:
        maker = mj["company"]
        safe_print(f"== {maker} ==")
        for keyword, must in mj["brands"]:
            items = search(app, key, sess, keyword)
            time.sleep(1.1)
            n_kw = 0
            for it in items:
                iname = it.get("itemName", "")
                if norm(must) not in norm(iname):
                    continue                          # 別ブランド混入を排除
                if _BUNDLE.search(iname):
                    continue                          # 多パック/詰め合わせ出品は除外（単品で拾う）
                cap = it.get("itemCaption", "") or ""
                res = N.extract_nutrition(cap, name=iname)
                if res.get("species") == "dog":
                    continue
                if not res.get("has_analysis_section"):
                    continue
                # 最低限たんぱく質が%で取れていること（取れないものは出さない）
                if "%" not in (res.get("crude_protein_value") or ""):
                    continue
                disp = clean_title(iname, must)
                k = dedup_key(maker, disp)
                if k in seen:
                    continue
                seen.add(k)
                res.update({
                    "maker": maker,
                    "product_name": disp,
                    "url": IMG.clean_item_url(it.get("itemUrl", "")),
                    "fetched_at": today_stamp(),
                    "source": "rakuten",
                })
                rows[res["url"]] = res
                kept += 1
                n_kw += 1
            safe_print(f"   {keyword[:28]:<30} +{n_kw}")

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=RAW_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows.values())
    by_maker = {}
    for r in rows.values():
        by_maker[r["maker"]] = by_maker.get(r["maker"], 0) + 1
    safe_print(f"[done] 楽天転記 {len(rows)} 商品（今回 +{kept}） → {OUT}")
    for mk, n in sorted(by_maker.items(), key=lambda x: -x[1]):
        safe_print(f"   {n:>3}  {mk}")


if __name__ == "__main__":
    main()
