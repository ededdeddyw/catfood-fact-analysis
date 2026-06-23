# -*- coding: utf-8 -*-
"""相談シートMVPの素データ＋静的プレビューを生成（docs/06）。

product_facts_raw.csv（精緻化抽出済み）から:
  - 猫のみ（species != dog）・成分ページのみ
  - 乾物量換算（DM）列を計算（水分があるもの）
  - カロリー密度（per_100g のみ）。per_piece は密度比較不可フラグ
出力:
  data/consult_sheet_cat.csv
  prototype/consult/data.json
  prototype/consult/index.html （ランキング無し・4状態・出典・DM・固定注記。そのまま獣医に見せる用）
LLM不使用。
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from catfood_common import DATA_DIR, ROOT, safe_print, today_stamp

FACTS = DATA_DIR / "product_facts_raw.csv"
OUT_CSV = DATA_DIR / "consult_sheet_cat.csv"
PROTO = ROOT / "prototype" / "consult"

SHEET_COLS = ["maker", "product_name", "url", "form", "moisture_pct",
              "protein_asfed", "protein_dm", "fat_dm",
              "phosphorus_asfed", "phosphorus_dm",
              "fiber_dm", "ash_dm", "nfe_dm",
              "fiber_pct", "ash_pct", "magnesium_pct", "magnesium_disclosed",
              "calorie_density_100g", "calorie_basis",
              "grain_free", "ingredients",
              "is_therapeutic", "phosphorus_disclosed", "fetched_at"]

# 穀物の語（原材料スニペットの主要部にこれが無ければ grain-free 候補・参考）
_GRAIN = ("米", "玄米", "白米", "小麦", "大麦", "麦", "とうもろこし", "コーン",
          "トウモロコシ", "オーツ", "ライ麦", "雑穀", "コーングルテン", "小麦粉")


def grain_free(ingredients: str) -> str:
    """原材料スニペットの主要部に穀物表記が無ければ yes（参考）。空なら unknown。"""
    if not ingredients:
        return "unknown"
    return "no" if any(g in ingredients for g in _GRAIN) else "yes"


def num(s: str):
    """'0.7%' '90mg' '40.0%' → float（数値部）。取れなければ None。"""
    if not s:
        return None
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def is_pct(s: str) -> bool:
    return bool(s) and "%" in s


def dm(asfed, moisture):
    """乾物量換算 %。水分がなければ None。"""
    if asfed is None or moisture is None or moisture >= 100:
        return None
    return round(asfed / (100 - moisture) * 100, 1)


def clean_name(title: str) -> str:
    """ページタイトルから商品名を整形（「｜商品詳細｜商品を探す…」等を除去）。"""
    if not title:
        return ""
    # 全角/半角の縦棒・ダッシュ・中黒区切りの先頭セグメントを採用
    for sep in ("｜", "|", " - ", "—", "／"):
        if sep in title:
            title = title.split(sep)[0]
    return title.strip().strip("・-　 ") or ""


def form_of(moisture):
    if moisture is None:
        return "不明"
    if moisture >= 60:
        return "ウェット"
    if moisture <= 20:
        return "ドライ"
    return "セミモイスト"


def calorie_density(kcal_str, basis):
    """kcal/100g に正規化（per_100g/per_kg のみ）。それ以外は None。"""
    v = num(kcal_str)
    if v is None:
        return None
    if basis == "per_100g":
        return round(v, 1)
    if basis == "per_kg":
        return round(v / 10, 1)
    return None  # per_piece / per_g / unknown は密度比較不可


def build_rows() -> list[dict]:
    rows = list(csv.DictReader(FACTS.open(encoding="utf-8-sig", newline="")))
    out = []
    for r in rows:
        if r.get("species") == "dog":
            continue
        moisture = num(r.get("moisture_value"))
        prot = num(r.get("crude_protein_value")) if is_pct(r.get("crude_protein_value")) else None
        fat = num(r.get("crude_fat_value")) if is_pct(r.get("crude_fat_value")) else None
        p_pct = is_pct(r.get("phosphorus_value"))
        phos = num(r.get("phosphorus_value")) if p_pct else None
        fiber = num(r.get("crude_fiber_value")) if is_pct(r.get("crude_fiber_value")) else None
        ash = num(r.get("crude_ash_value")) if is_pct(r.get("crude_ash_value")) else None
        mg = num(r.get("magnesium_value")) if is_pct(r.get("magnesium_value")) else None
        ingredients = r.get("ingredients_snippet", "")
        # 乾物量換算（DM）と炭水化物(NFE=差分)。レーダー表示用。
        pdm = dm(prot, moisture) if prot is not None else None
        fdm = dm(fat, moisture) if fat is not None else None
        fbdm = dm(fiber, moisture) if fiber is not None else None
        adm = dm(ash, moisture) if ash is not None else None
        nfe = None
        if None not in (pdm, fdm, fbdm, adm):
            rest = round(100 - (pdm + fdm + fbdm + adm), 1)
            nfe = rest if rest >= 0 else 0.0
        out.append({
            "maker": r.get("maker", ""),
            "product_name": clean_name(r.get("product_name", "")),
            "url": r.get("url", ""),
            "form": form_of(moisture),
            "moisture_pct": moisture if moisture is not None else "",
            "protein_asfed": prot if prot is not None else "",
            "protein_dm": pdm if pdm is not None else "",
            "fat_dm": fdm if fdm is not None else "",
            "phosphorus_asfed": r.get("phosphorus_value", ""),
            "phosphorus_dm": dm(phos, moisture) if phos is not None else "",
            "fiber_dm": fbdm if fbdm is not None else "",
            "ash_dm": adm if adm is not None else "",
            "nfe_dm": nfe if nfe is not None else "",
            "fiber_pct": fiber if fiber is not None else "",
            "ash_pct": ash if ash is not None else "",
            "magnesium_pct": mg if mg is not None else "",
            "magnesium_disclosed": "yes" if mg is not None else "no",
            "calorie_density_100g": calorie_density(r.get("calorie_kcal"), r.get("calorie_basis")) or "",
            "calorie_basis": r.get("calorie_basis", ""),
            "grain_free": grain_free(ingredients),
            "ingredients": ingredients[:90],
            "is_therapeutic": r.get("is_therapeutic", ""),
            "phosphorus_disclosed": r.get("disclosed_phosphorus", "no"),
            "fetched_at": r.get("fetched_at", ""),
        })
    return out


HTML_TMPL = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>キャットフード 比較メモ（出典付きファクト・非診断）</title>
<style>
 body{font-family:system-ui,"Hiragino Kaku Gothic ProN",Meiryo,sans-serif;margin:0;color:#222;background:#fafafa}
 header{background:#fff;border-bottom:3px solid #d9534f;padding:14px 18px}
 h1{font-size:18px;margin:0 0 6px}
 .warn{background:#fff8e1;border:1px solid #ffe082;border-radius:6px;padding:10px 12px;margin:10px 18px;font-size:13px;line-height:1.6}
 .controls{margin:10px 18px;font-size:13px}
 .controls button,.controls label{margin-right:10px}
 table{border-collapse:collapse;width:calc(100% - 36px);margin:12px 18px;background:#fff;font-size:13px}
 th,td{border:1px solid #e0e0e0;padding:6px 8px;text-align:left;vertical-align:top}
 th{background:#f5f5f5;cursor:pointer;white-space:nowrap}
 td.num{text-align:right;font-variant-numeric:tabular-nums}
 .na{color:#999;font-size:12px}
 .ther{color:#b71c1c;font-weight:600}
 .src a{color:#1565c0;text-decoration:none}
 footer{margin:16px 18px 40px;font-size:12px;color:#555;line-height:1.7}
 .note{font-size:12px;color:#666;margin:4px 18px}
 .buy a{display:inline-block;margin:0 4px 2px 0;padding:1px 6px;border:1px solid #cfd8dc;border-radius:4px;color:#37474f;text-decoration:none;font-size:11px}
 .buy a:hover{background:#eceff1}
 @media print{
   .controls,.buy{display:none}
   .warn{border:1px solid #999;background:#fff}
   th{cursor:default}
   body{background:#fff}
   table{font-size:11px}
 }
</style></head><body>
<header>
 <h1>🐾 キャットフード 比較メモ（出典付きファクト）</h1>
 <div class="note">当サービスは評価・順位付け・おすすめを行いません。公式表示を転記・乾物量換算したファクトのみを並べています。</div>
</header>
<div class="warn">
 ⚠️ このシートは「おすすめ」ではありません。当サービスは診断・治療の助言を行いません。
 数値は各メーカー公式の表示を転記・換算したファクトです。<br>
 「記載なし」は「含まれない」ではなく「メーカーが公開していない」という意味です。
 与えてよいか・療法食が必要かは、必ずかかりつけの獣医師にご相談ください。
</div>
<div class="controls">
 並べ替え:
 <button onclick="sortBy('product_name')">商品名</button>
 <button onclick="sortBy('calorie_density_100g')">カロリー密度</button>
 <button onclick="sortBy('phosphorus_dm')">リン(乾物量)</button>
 <label><input type="checkbox" id="ponly" onchange="render()"> リンを開示している商品だけ（腎臓ビュー）</label>
 <button onclick="window.print()">🖨 印刷 / PDF保存</button>
</div>
<table id="t"><thead><tr>
 <th onclick="sortBy('product_name')">商品 / メーカー</th>
 <th onclick="sortBy('form')">種別</th>
 <th onclick="sortBy('moisture_pct')">水分%</th>
 <th onclick="sortBy('protein_dm')">たんぱく質%(乾物量)</th>
 <th onclick="sortBy('phosphorus_dm')">リン%(乾物量)</th>
 <th onclick="sortBy('calorie_density_100g')">カロリー密度<br>kcal/100g</th>
 <th>療法食</th>
 <th>出典</th>
 <th>購入先（比較）</th>
</tr></thead><tbody id="b"></tbody></table>
<footer id="cov"></footer>
<script>
const DATA = __DATA__;
const COV = __COV__;
let sortKey='product_name', asc=true;
function cell(v,unit){ if(v===''||v===null||v===undefined) return '<span class="na">記載なし（要確認）</span>'; return v+(unit||''); }
function sortBy(k){ asc = (sortKey===k)? !asc : true; sortKey=k; render(); }
function render(){
 let rows=DATA.slice();
 if(document.getElementById('ponly').checked) rows=rows.filter(r=>r.phosphorus_disclosed==='yes');
 rows.sort((a,b)=>{let x=a[sortKey],y=b[sortKey];
   const xn=(x===''?null:Number(x)), yn=(y===''?null:Number(y));
   if(xn!==null&&yn!==null&&!isNaN(xn)&&!isNaN(yn)){return asc?xn-yn:yn-xn;}
   x=(x||'').toString();y=(y||'').toString();return asc?x.localeCompare(y,'ja'):y.localeCompare(x,'ja');});
 const b=document.getElementById('b'); b.innerHTML='';
 for(const r of rows){
   const tr=document.createElement('tr');
   const cal = r.calorie_basis==='per_piece' ? '<span class="na">個包装のため密度比較不可</span>' : cell(r.calorie_density_100g);
   tr.innerHTML=`<td>${r.product_name||'(無題)'}<br><span class="na">${r.maker}</span></td>`+
     `<td>${r.form}</td>`+
     `<td class="num">${cell(r.moisture_pct)}</td>`+
     `<td class="num">${cell(r.protein_dm)}</td>`+
     `<td class="num">${cell(r.phosphorus_dm)}</td>`+
     `<td class="num">${cal}</td>`+
     `<td>${r.is_therapeutic==='True'?'<span class="ther">療法食</span>':'—'}</td>`+
     `<td class="src"><a href="${r.url}" target="_blank" rel="noopener">公式</a> <span class="na">${r.fetched_at}</span></td>`+
     `<td class="buy">${buyLinks(r)}</td>`;
   b.appendChild(tr);
 }
 document.getElementById('cov').innerHTML =
  `掲載 ${rows.length} 商品（全${DATA.length}）。対象母集団＝ペットフード公正取引協議会 正会員${COV.makers}社／`+
  `公式に成分を開示している商品を掲載（確定メーカー${COV.confirmed}・データ取得${COV.with_data}社）。`+
  `<br>※療法食は獣医師の指示なく与えないでください。リン等の数値の解釈は症例ごとに異なります。この表を獣医師にお見せください。`+
  `<br>※乾物量換算＝水分を除いた基準。ウェットとドライを公平に比較するためのものです。`+
  `<br>※購入先リンクは全商品に等しく付与した比較ユーティリティです。当サイトは手数料を得る場合がありますが、<b>掲載順・内容には一切影響しません</b>。評価・ランキングは行いません。`;
}
// 購入先: 全商品に等しく・複数チャネル・手数料を表示順の入力にしない（docs/03 アフィリ遮断）
function buyLinks(r){
 const q=encodeURIComponent(((r.maker||'')+' '+(r.product_name||'')).trim());
 const ch=[['楽天','https://search.rakuten.co.jp/search/mall/'+q+'/'],
           ['Amazon','https://www.amazon.co.jp/s?k='+q],
           ['Yahoo','https://shopping.yahoo.co.jp/search?p='+q]];
 return ch.map(c=>`<a href="${c[1]}" target="_blank" rel="noopener nofollow">${c[0]}</a>`).join('');
}
render();
</script></body></html>"""


def main() -> None:
    rows = build_rows()
    PROTO.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SHEET_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    (PROTO / "data.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    # カバレッジ数値
    cov = {"makers": 79, "confirmed": _count_confirmed(), "with_data": len(set(r["maker"] for r in rows))}
    html = HTML_TMPL.replace("__DATA__", json.dumps(rows, ensure_ascii=False)).replace("__COV__", json.dumps(cov, ensure_ascii=False))
    (PROTO / "index.html").write_text(html, encoding="utf-8")

    p_open = sum(1 for r in rows if r["phosphorus_disclosed"] == "yes")
    safe_print(f"[consult] {len(rows)} 商品 / リン開示 {p_open} / {cov['with_data']}社")
    safe_print(f"  -> {OUT_CSV}")
    safe_print(f"  -> {PROTO / 'index.html'}（ブラウザで開く）")


def _count_confirmed() -> int:
    p = DATA_DIR / "maker_sites.csv"
    if not p.exists():
        return 0
    return sum(1 for r in csv.DictReader(p.open(encoding="utf-8-sig"))
               if r.get("matched") == "yes" and r.get("needs_review") == "no")


if __name__ == "__main__":
    main()
