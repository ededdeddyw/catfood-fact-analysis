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
        # カルカンは公式(kalkan.jp)で一次取得済み(harvest_mars.py)なので楽天からは取らない（重複回避）。
        # ニュートロは公式がJSで取れないため楽天転記で補完（公式未確認）。
        ("ニュートロ シュプレモ 猫 ドライ", "ニュートロ"),
        ("ニュートロ ナチュラルチョイス 猫", "ニュートロ"),
    ]},
    {"company": "ユニ・チャーム株式会社", "brands": [
        ("銀のスプーン 猫", "銀のスプーン"),
        ("銀のスプーン 三ツ星グルメ 猫", "銀のスプーン"),
        ("ねこ元気 猫", "ねこ元気"),
        ("AllWell 猫 ドライ", "allwell"),
    ]},
    {"company": "はごろもフーズ株式会社", "brands": [
        ("無一物 猫 パウチ", "無一物"),
        ("無一物 ねこまんま 猫", "無一物"),
    ]},
    {"company": "デビフペット株式会社", "brands": [
        ("デビフ 猫", "デビフ"),
        ("デビフ 猫 缶", "デビフ"),
    ]},
    {"company": "株式会社ペティオ", "brands": [
        ("ペティオ 猫 総合栄養食", "ペティオ"),
        ("ペティオ プラクト 猫", "ペティオ"),
    ]},
    {"company": "ライオンペット株式会社", "brands": [
        ("ペットキッス PETKISS 猫 歯みがき", "petkiss"),  # 1キーワードに集約（重複抑制）
    ]},
    # 注: ブランド帰属が確実なメーカーだけを入れること（誤帰属は出典の信頼を損なう）。除外した社（2026-06-24 楽天プローブで確認）：
    #  - マース・ジャパン: カルカン/シーバ/アイムス/ニュートロ いずれも caption に保証成分が無く取得0（公式はJS別サイト）。
    #  - ウェルペット(ウェルネス)/マルカン(サンライズ)/アース・ペット/QIX(ペティエンス)/兼松: 取得0。
    #  - スペクトラム ブランズ: 公式は 8in1 のみ（ナチュラルバランス/アイムスは扱わない）。
    #  - イオン トップバリュ: PB のため楽天に流通せず取得不可。カラーズ: 帰属が不確実なため保留。
]


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "")).lower()


# 末尾から剥がす検索語エコー/一般語（form・生体ステージ等は別表示なので落として安全）
_TAIL = {"猫", "猫用", "ねこ", "ネコ", "ドライ", "ウェット", "パウチ", "フード", "キャットフード",
         "用", "総合栄養食", "国産", "無添加", "ヒルズ", "ネスレ", "マース", "ユニチャーム",
         "はごろも", "ピュリナ", "ネスレ日本", "ドライフード", "ウェットフード", "家族品質",
         "子猫", "成猫", "高齢猫", "シニア猫", "幼猫",
         "インドアキャット", "キャット", "スナック", "間食", "間", "歯", "おやつ", "贅沢おやつ",
         "ごほうび", "無香料", "大袋", "スティック", "プチ", "魚", "シーフード", "鶏", "バラエティ",
         "アソート"}
# 途中に出たらそこでSEO詰め込みが始まる合図（手前を採用）
_SEO_CUT = re.compile(r"[◆●▼★/]|ネスレ日本|送料無料|まとめ買い|大容量")


def clean_title(name: str, brand: str = "") -> str:
    """楽天の出品名から商品名を整える（販促/数量/容量/SEO詰め込みを除去）。
    ブランド名が分かる場合は、その手前（販促）を落とす。"""
    t = unicodedata.normalize("NFKC", name or "")     # ｜→| 等も正規化
    t = t.split("|")[0]                                # ｜以降のSEOキーワード列を切る
    t = re.sub(r"[【\[「][^】\]」]*[】\]」]", " ", t)   # 【送料無料】[ ]「」
    if brand:                                          # ブランド名の手前（=販促）を捨てる
        i = t.lower().find(brand.lower())
        if i > 0:
            t = t[i:]
    t = re.sub(r"[（(][^）)]*[）)]", " ", t)            # (60g*24袋) 等
    m = _SEO_CUT.search(t, 4)                           # 途中のSEO詰め込み境界で切る（頭は除く）
    if m:
        t = t[:m.start()]
    t = re.sub(r"(キャットフード|ペットフード|送料無料|お買い得|まとめ買い|ケース販売|"
               r"ポイント\d*倍|限定|当選確率|あす楽|関東当日便|翌日配達|最大\d+%?|\d+等|"
               r"\d+分の\d+|％?OFF|お試し)", " ", t)
    t = re.sub(r"\d+(\.\d+)?\s*(kg|g|袋|缶|個|本|箱|p|ml)\b", " ", t, flags=re.I)
    t = re.sub(r"[×x*]\s*\d+\s*(袋|缶|個|本|箱|セット|ケース)?", " ", t)
    t = re.sub(r"\s[×xX*](\s|$)", " ", t)              # 孤立した×を除去
    t = re.sub(r"\s+", " ", t).strip()
    toks = t.split()
    dedup = []                                          # 連続重複語を畳む
    for w in toks:
        if not dedup or dedup[-1] != w:
            dedup.append(w)
    toks = dedup
    # 末尾の一般語／生体ステージ／カタカナSEO読み（MPCKバラエテイ…）／出品者コードを剥がす
    def junk_tail(w):
        return (w in _TAIL
                or re.fullmatch(r"(?=.*\d)[a-z0-9\-]{3,8}", w.lower())  # kzj-1 / xp10n
                or re.fullmatch(r"[A-Za-z]{2,}[ァ-ヶー\-]{4,}", w)       # MPCKバラエテイ…
                or re.fullmatch(r"[ァ-ヶ]{12,}", w))                     # 長い全カタカナ＝SEO読み（ハゴロモムイチモツ…）
    while len(toks) > 2 and junk_tail(toks[-1]):
        toks.pop()
    t = " ".join(toks).strip(" 　・-/|!！")
    if len(t) > 64:                                     # 語境界で切り詰め（語の途中で切らない）
        cut = t[:64].rsplit(" ", 1)[0]
        t = cut if len(cut) >= 20 else t[:64]
    return t


# 重複の元になる多パック/詰め合わせ出品（単品は別途拾えるので除外）
_BUNDLE = re.compile(r"(セット|ケース|まとめ|詰め合わせ|大容量|個セット|種類セット)")


# dedup キーから落とすノイズ語（味＝まぐろ/チキン等は残すので別商品は分かれる）
_DEDUP_NOISE = ["パック", "正規品", "キャット", "猫用", "子猫用", "成猫用", "高齢猫用", "シニア猫用",
                "猫", "子猫", "成猫", "高齢猫", "おやつ", "ごはん", "ご飯", "総合栄養食",
                "とろリッチ", "にっぽんselect", "にゃんspoon", "アソート", "各", "入", "用"]


def dedup_key(maker: str, cleaned_name: str) -> str:
    """同一商品の重複（出品者違い・容量違い・販促語違い）をまとめるキー。整形済み名を渡すこと。
    味の語は残すので、別フレーバーは別商品として分かれる。"""
    t = norm(cleaned_name)
    t = re.sub(r"〔[^〕]*〕|お一人様\d+点限り|\+.*$", "", t)   # 出品者コード/おまけ併売を除去
    for w in _DEDUP_NOISE:
        t = t.replace(norm(w), "")
    t = re.sub(r"[\s　・/|,.。、&＆!！~〜ー]+", "", t)
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
