"""保証分析値・原材料・カロリー・リンの正規表現抽出（フード版 factor_label_policy）

LLM を使わず、ページ本文テキストから保証分析値などを機械抽出する。
4状態の考え方（docs/catfood_concept/01）:
  * 値が取れた          → 肯定（公式記載）= disclosed
  * 取れない            → 不明・要確認 = not disclosed（「含まれない」とは断定しない）

抽出対象（キャットフードの保証分析値・典型表記）:
  粗たんぱく質 / 粗脂肪 / 粗繊維 / 粗灰分 / 水分 / カロリー(代謝エネルギー) / リン / 原材料
"""
from __future__ import annotations

import re

# 数値（27, 27.0 など）
_NUM = r"(\d+(?:\.\d+)?)"
# パーセント記号（半角/全角）
_PCT = r"\s*[%％]"

# 各栄養素のラベル別名（| で連結して正規表現化）
FIELD_LABELS: dict[str, list[str]] = {
    "crude_protein": ["粗たんぱく質", "粗タンパク質", "粗蛋白質", "たんぱく質", "蛋白質", "粗蛋白"],
    "crude_fat": ["粗脂肪", "脂質"],
    "crude_fiber": ["粗繊維", "粗せんい", "食物繊維"],
    "crude_ash": ["粗灰分", "灰分"],
    "moisture": ["水分"],
    "phosphorus": ["リン", "りん", "燐"],
    "calcium": ["カルシウム"],
    "sodium": ["ナトリウム", "食塩相当量"],
    "magnesium": ["マグネシウム"],
}

# %値（ラベル → 近接する数値%）。ラベルと値の間に「：」「含有量」等が挟まるのを許容
def _pct_pattern(labels: list[str]) -> re.Pattern:
    lab = "|".join(re.escape(x) for x in labels)
    return re.compile(rf"(?:{lab})\s*[:：]?\s*[^0-9%％\n]{{0,12}}?{_NUM}{_PCT}")


# リン等は mg 表記もある（例: リン 90mg/100g）。% が無い場合の補助
def _mg_pattern(labels: list[str]) -> re.Pattern:
    lab = "|".join(re.escape(x) for x in labels)
    return re.compile(rf"(?:{lab})\s*[:：]?\s*[^0-9\n]{{0,12}}?{_NUM}\s*mg")


PCT_PATTERNS = {f: _pct_pattern(ls) for f, ls in FIELD_LABELS.items()}
MG_PATTERNS = {f: _mg_pattern(ls) for f, ls in FIELD_LABELS.items()}

# カロリー / 代謝エネルギー（kcal）。/100g や /kg は単位フラグとして拾う
CALORIE_PATTERN = re.compile(
    r"(?:カロリー|代謝エネルギー|エネルギー|ME)\s*[:：]?\s*[約]?\s*"
    rf"{_NUM}\s*(?:kcal|kCal|キロカロリー)"
    r"\s*(?:/?\s*(100\s*g|1\s*kg|kg|100g))?",
    re.IGNORECASE,
)

# 原材料（先頭120文字程度をスニペットとして保持）
INGREDIENTS_PATTERN = re.compile(r"原材料(?:名)?\s*[:：]?\s*(.{5,160})")

# 「保証分析値」「成分」セクションが存在するか（ページ判定用）
HAS_ANALYSIS_KEYWORDS = ["保証分析値", "成分値", "成分", "栄養成分", "標準成分"]

# 療法食フラグ
THERAPEUTIC_KEYWORDS = ["療法食", "食事療法", "獣医師の指導", "獣医師の指示", "療養食"]


def extract_nutrition(text: str) -> dict:
    """本文テキストから保証分析値等を抽出して dict で返す。

    返り値: 各 *_pct / calorie_kcal / ingredients / is_therapeutic と
            disclosed_* (bool) を含む。
    """
    out: dict = {}
    disclosed = {}

    for field, pat in PCT_PATTERNS.items():
        m = pat.search(text)
        val = None
        if m:
            val = m.group(1) + "%"
        elif field in ("phosphorus", "calcium", "sodium", "magnesium"):
            m2 = MG_PATTERNS[field].search(text)
            if m2:
                val = m2.group(1) + "mg"
        out[f"{field}_value"] = val or ""
        disclosed[field] = bool(val)

    cal = CALORIE_PATTERN.search(text)
    if cal:
        unit = (cal.group(2) or "").replace(" ", "")
        out["calorie_kcal"] = cal.group(1) + ("kcal/" + unit if unit else "kcal")
    else:
        out["calorie_kcal"] = ""
    disclosed["calorie"] = bool(cal)

    ing = INGREDIENTS_PATTERN.search(text)
    out["ingredients_snippet"] = (ing.group(1).strip() if ing else "")
    disclosed["ingredients"] = bool(ing)

    out["is_therapeutic"] = any(k in text for k in THERAPEUTIC_KEYWORDS)
    out["has_analysis_section"] = any(k in text for k in HAS_ANALYSIS_KEYWORDS)

    for k, v in disclosed.items():
        out[f"disclosed_{k}"] = "yes" if v else "no"

    # いくつ取れたか（ページ採否の目安）
    out["fields_found"] = sum(1 for v in disclosed.values() if v)
    return out


# 抽出CSVの列（02 オーディットのスキーマに対応）
EXTRACT_FIELDS = [
    "maker",
    "product_name",
    "url",
    "fields_found",
    "has_analysis_section",
    "is_therapeutic",
    "disclosed_crude_protein",
    "disclosed_crude_fat",
    "disclosed_crude_fiber",
    "disclosed_crude_ash",
    "disclosed_moisture",
    "disclosed_calorie",
    "disclosed_phosphorus",
    "disclosed_ingredients",
    "crude_protein_value",
    "crude_fat_value",
    "crude_fiber_value",
    "crude_ash_value",
    "moisture_value",
    "calorie_kcal",
    "phosphorus_value",
    "calcium_value",
    "sodium_value",
    "magnesium_value",
    "ingredients_snippet",
    "fetched_at",
]


if __name__ == "__main__":
    # 自己テスト: 典型的な保証分析値ブロックで regex を検証
    sample = (
        "成分 保証分析値 粗たんぱく質 27.0％以上 粗脂肪 12.5％以上 "
        "粗繊維 4.0％以下 粗灰分 8.0％以下 水分 10.0％以下 "
        "リン 0.9％以上 カルシウム 1.1% カロリー 約350kcal/100g "
        "原材料名 鶏肉、米、とうもろこし、動物性油脂、ビタミン類 "
        "本品は療法食です。獣医師の指示に従ってください。"
    )
    res = extract_nutrition(sample)
    for k in EXTRACT_FIELDS:
        if k in res:
            print(f"{k:28} {res[k]}")
