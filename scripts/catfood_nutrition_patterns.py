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

# --- 全角→半角正規化（「４０%」→「40%」等） ---
_FW = str.maketrans("０１２３４５６７８９％．：／（）ｇｍｋｃａｌ", "0123456789%.:/()gmkcal")


def normalize_text(s: str) -> str:
    return s.translate(_FW) if s else s


# --- 保証成分ブロックの切り出し（ページ全文の誤検出を防ぐ） ---
# 優先度順（強い見出しほど先）。bare「成分」は最後の保険。
_BLOCK_KEYS = ["保証分析値", "保証成分値", "保証成分", "標準成分値", "標準成分",
               "栄養成分", "成分値", "分析値", "成分"]
_BLOCK_WINDOW = 700  # 見出しから何文字を分析対象にするか


def analysis_block(text: str) -> tuple[str, bool]:
    """保証成分の見出しを見つけ、その近傍ウィンドウだけを返す。

    見つからなければ ("", False)。呼び出し側は False のとき全文にフォールバックする。
    """
    best = None
    for kw in _BLOCK_KEYS:
        i = text.find(kw)
        if i != -1 and (best is None or i < best):
            best = i
    if best is None:
        return "", False
    return text[best:best + _BLOCK_WINDOW], True

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

# カロリー / 代謝エネルギー（kcal）。単位（/100g・/kg・/個・/本…）も拾う
CALORIE_PATTERN = re.compile(
    r"(?:カロリー|代謝エネルギー|エネルギー|ME|ＭＥ)\s*[（(]?[^0-9\n]{0,18}?[:：]?\s*[約]?\s*"
    rf"{_NUM}\s*(?:kcal|kcal|キロカロリー)"
    r"\s*(?:/?\s*(100\s*g|1\s*?kg|kg|g|個|本|袋|包|粒|缶|食|パック|スティック))?",
    re.IGNORECASE,
)

# 1個あたり等（個包装おやつ）= カロリー密度に使えない単位
_PER_PIECE = ("個", "本", "袋", "包", "粒", "缶", "食", "パック", "スティック")


def _calorie_basis(unit: str) -> str:
    u = (unit or "").replace(" ", "")
    if not u:
        return "unknown"
    if u in ("100g",):
        return "per_100g"
    if u in ("1kg", "kg"):
        return "per_kg"
    if u == "g":
        return "per_g"
    if any(p in u for p in _PER_PIECE):
        return "per_piece"
    return "unknown"

# 原材料（先頭120文字程度をスニペットとして保持）
INGREDIENTS_PATTERN = re.compile(r"原材料(?:名)?\s*[:：]?\s*(.{5,160})")

# 「保証分析値」「成分」セクションが存在するか（ページ判定用）
HAS_ANALYSIS_KEYWORDS = ["保証分析値", "成分値", "成分", "栄養成分", "標準成分"]

# 療法食フラグ
THERAPEUTIC_KEYWORDS = ["療法食", "食事療法", "獣医師の指導", "獣医師の指示", "療養食"]

# 犬猫判定（URL/商品名/本文の語から）
_CAT_KW = ("猫", "キャット", "ねこ", "cat", "feline")
_DOG_KW = ("犬", "ドッグ", "いぬ", "dog", "canine")


def detect_species(*sources: str) -> str:
    """url / 商品名 / 本文先頭 などから cat / dog / both / unknown を判定。"""
    blob = " ".join(s for s in sources if s).lower()
    has_cat = any(k.lower() in blob for k in _CAT_KW)
    has_dog = any(k.lower() in blob for k in _DOG_KW)
    if has_cat and not has_dog:
        return "cat"
    if has_dog and not has_cat:
        return "dog"
    if has_cat and has_dog:
        return "both"
    return "unknown"


def _scan_fields(scope: str) -> tuple[dict, dict]:
    out, disclosed = {}, {}
    for field, pat in PCT_PATTERNS.items():
        m = pat.search(scope)
        val = None
        if m:
            val = m.group(1) + "%"
        elif field in ("phosphorus", "calcium", "sodium", "magnesium"):
            m2 = MG_PATTERNS[field].search(scope)
            if m2:
                val = m2.group(1) + "mg"
        out[f"{field}_value"] = val or ""
        disclosed[field] = bool(val)
    return out, disclosed


def extract_nutrition(text: str, url: str = "", name: str = "") -> dict:
    """本文テキストから保証分析値等を抽出して dict で返す。

    精緻化:
      * 全角→半角正規化（４０% → 40%）
      * 栄養値は「保証成分ブロック」に限定して誤検出を防ぐ（取れない時は全文にフォールバック）
      * カロリーは単位（/100g・/個 等）と basis（per_100g/per_piece…）を保持
      * species（cat/dog/both/unknown）を付与
    """
    text = normalize_text(text)
    out: dict = {}

    # 栄養値: まず保証成分ブロック、収量が乏しければ全文
    block, has_block = analysis_block(text)
    vals, disclosed = _scan_fields(block) if has_block else ({}, {})
    if sum(disclosed.values()) < 3:  # ブロックが薄い→全文で取り直し（recall保護）
        vals, disclosed = _scan_fields(text)
    out.update(vals)

    # カロリー（ブロック優先→全文）
    cal = CALORIE_PATTERN.search(block) if has_block else None
    if not cal:
        cal = CALORIE_PATTERN.search(text)
    if cal:
        unit = (cal.group(2) or "").replace(" ", "")
        out["calorie_kcal"] = cal.group(1) + ("kcal/" + unit if unit else "kcal")
        out["calorie_basis"] = _calorie_basis(unit)
    else:
        out["calorie_kcal"] = ""
        out["calorie_basis"] = ""
    disclosed["calorie"] = bool(cal)

    ing = INGREDIENTS_PATTERN.search(text)
    out["ingredients_snippet"] = (ing.group(1).strip() if ing else "")
    disclosed["ingredients"] = bool(ing)

    out["is_therapeutic"] = any(k in text for k in THERAPEUTIC_KEYWORDS)
    out["has_analysis_section"] = any(k in text for k in HAS_ANALYSIS_KEYWORDS)
    # species は url / 商品名を優先（本文はナビに犬猫混在しがちなので先頭のみ補助）
    out["species"] = detect_species(url, name) if (url or name) else detect_species(text[:300])

    for k, v in disclosed.items():
        out[f"disclosed_{k}"] = "yes" if v else "no"
    out["fields_found"] = sum(1 for v in disclosed.values() if v)
    return out


# 抽出CSVの列（02 オーディットのスキーマに対応）
EXTRACT_FIELDS = [
    "maker",
    "product_name",
    "url",
    "species",
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
    "calorie_basis",
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
