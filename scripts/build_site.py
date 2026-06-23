# -*- coding: utf-8 -*-
"""公開フロント（静的サイト）を実データから生成（DBビューとは分離）。

設計: docs/01-03・06 に忠実。評価せず・順位を付けず・母集団を宣言し、
出典付きファクト＋乾物量換算＋4状態＋非診断＋アフィリ遮断。段階リリース
（体重管理＝第2段 / 腎臓相談シート＝第3段）。LLM不使用・静的HTML。

入力: data/consult_sheet_cat.csv（乾物量換算済み）, data/maker_sites.csv（カバレッジ）
出力: site/ 配下（index/weight/kidney/coverage/about + style.css）
"""
from __future__ import annotations

import csv
import json

from catfood_common import DATA_DIR, ROOT, safe_print, today_stamp

SITE = ROOT / "site"
CONSULT = DATA_DIR / "consult_sheet_cat.csv"
MAKERS = DATA_DIR / "maker_sites.csv"

# 公開先URL（GitHub Pages のプロジェクトページ既定。独自ドメイン時はここを変える）
BASE_URL = "https://ededdeddyw.github.io/catfood-fact-analysis"
SITE_NAME = "ねこごはんファクト"
# 絵文字favicon（外部ファイル不要のSVGデータURI）
FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
           "viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%90%BE%3C/text%3E%3C/svg%3E")

CSS = """
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Hiragino Kaku Gothic ProN",Meiryo,sans-serif;
 margin:0;color:#1f2937;background:#f7f7f5;line-height:1.65}
a{color:#1565c0}
.wrap{max-width:1040px;margin:0 auto;padding:0 18px}
header.site{background:#fff;border-bottom:1px solid #e5e7eb;position:sticky;top:0;z-index:5}
header.site .wrap{display:flex;align-items:center;gap:18px;height:56px}
.brand{font-weight:800;font-size:17px;color:#b1442f;text-decoration:none;white-space:nowrap}
nav.main{display:flex;gap:14px;flex-wrap:wrap;font-size:14px}
nav.main a{color:#374151;text-decoration:none;padding:4px 2px;border-bottom:2px solid transparent}
nav.main a.active{color:#b1442f;border-bottom-color:#b1442f;font-weight:700}
h1{font-size:26px;margin:24px 0 6px}
h2{font-size:19px;margin:26px 0 8px;border-left:4px solid #b1442f;padding-left:10px}
.lead{font-size:15px;color:#4b5563;margin:0 0 8px}
.tag{display:inline-block;background:#eef2ff;color:#3730a3;border-radius:999px;padding:2px 10px;font-size:12px;margin:2px 6px 2px 0}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px 18px;margin:14px 0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.disclaimer{background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:12px 14px;font-size:13.5px;margin:14px 0}
.controls{margin:12px 0;font-size:14px;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.controls button{border:1px solid #cfd8dc;background:#fff;border-radius:6px;padding:5px 10px;cursor:pointer}
table{border-collapse:collapse;width:100%;background:#fff;font-size:13.5px;border:1px solid #e5e7eb}
th,td{border-bottom:1px solid #eef0f2;padding:7px 9px;text-align:left;vertical-align:top}
th{background:#fafafa;cursor:pointer;white-space:nowrap;position:sticky;top:56px}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.na{color:#9aa0a6;font-size:12px}
.ther{color:#b71c1c;font-weight:700;font-size:12px}
.buy a{display:inline-block;margin:0 3px 2px 0;padding:1px 6px;border:1px solid #cfd8dc;border-radius:4px;
 color:#37474f;text-decoration:none;font-size:11px}
.mk{color:#9aa0a6;font-size:11.5px}
footer.site{margin-top:40px;background:#fff;border-top:1px solid #e5e7eb;font-size:12.5px;color:#6b7280}
footer.site .wrap{padding:18px}
.big{font-size:30px;font-weight:800;color:#b1442f}
@media print{header.site,nav.main,.controls,.buy,footer.site nav,.noprint{display:none}
 body{background:#fff} th{position:static} .disclaimer{border:1px solid #999;background:#fff}}
"""

TABLE_JS = """
let DATA=__DATA__, COLS=__COLS__, sortKey=__SORT__, asc=__ASC__, ponly=__PONLY__;
function cell(v,u){return (v===''||v==null)?'<span class=\"na\">記載なし（要確認）</span>':v+(u||'');}
function buy(r){var q=encodeURIComponent(((r.maker||'')+' '+(r.product_name||'')).trim());
 return [['楽天','https://search.rakuten.co.jp/search/mall/'+q+'/'],['Amazon','https://www.amazon.co.jp/s?k='+q],
 ['Yahoo','https://shopping.yahoo.co.jp/search?p='+q]].map(c=>'<a href=\"'+c[1]+'\" target=\"_blank\" rel=\"noopener nofollow\">'+c[0]+'</a>').join('');}
function val(r,k){if(k==='calorie_density_100g'&&r.calorie_basis==='per_piece')return '';return r[k];}
function sortBy(k){asc=(sortKey===k)?!asc:true;sortKey=k;draw();}
function draw(){let rows=DATA.slice();
 if(ponly)rows=rows.filter(r=>r.phosphorus_disclosed==='yes');
 rows.sort((a,b)=>{let x=val(a,sortKey),y=val(b,sortKey);
  let xn=(x===''?null:Number(x)),yn=(y===''?null:Number(y));
  if(xn!=null&&yn!=null&&!isNaN(xn)&&!isNaN(yn))return asc?xn-yn:yn-xn;
  x=(x||'').toString();y=(y||'').toString();return asc?x.localeCompare(y,'ja'):y.localeCompare(x,'ja');});
 let h='<tr>'+COLS.map(c=>'<th onclick=\"sortBy(\\''+c.k+'\\')\">'+c.t+'</th>').join('')+'</tr>';
 let b=rows.map(r=>{return '<tr>'+COLS.map(c=>{
   if(c.type==='name')return '<td>'+(r.product_name||'(無題)')+'<br><span class=\"mk\">'+r.maker+'</span></td>';
   if(c.type==='cal'){return '<td class=\"num\">'+(r.calorie_basis==='per_piece'?'<span class=\"na\">個包装・密度比較不可</span>':cell(r.calorie_density_100g))+'</td>';}
   if(c.type==='ther')return '<td>'+(r.is_therapeutic==='True'?'<span class=\"ther\">療法食</span>':'—')+'</td>';
   if(c.type==='src')return '<td><a href=\"'+r.url+'\" target=\"_blank\" rel=\"noopener\">公式</a> <span class=\"na\">'+r.fetched_at+'</span></td>';
   if(c.type==='buy')return '<td class=\"buy\">'+buy(r)+'</td>';
   return '<td class=\"num\">'+cell(r[c.k])+'</td>';
 }).join('')+'</tr>';}).join('');
 document.getElementById('thead').innerHTML=h;
 document.getElementById('tbody').innerHTML=b;
 document.getElementById('cnt').textContent=rows.length;
}
draw();
"""


def load_products() -> list[dict]:
    return list(csv.DictReader(CONSULT.open(encoding="utf-8-sig", newline="")))


def coverage() -> dict:
    rows = list(csv.DictReader(MAKERS.open(encoding="utf-8-sig", newline="")))
    seisei = 79
    confirmed = [r for r in rows if r.get("matched") == "yes" and r.get("needs_review") == "no"]
    excluded = [r for r in rows if r.get("method") == "excluded_no_catfood"]
    prods = load_products()
    with_data = sorted(set(r["maker"] for r in prods))
    confirmed_names = set(r["company_name"] for r in confirmed)
    no_data = sorted(confirmed_names - set(with_data))
    return {"pop": seisei, "confirmed": confirmed, "excluded": excluded,
            "with_data": with_data, "no_data": no_data,
            "products": len(prods),
            "p_open": sum(1 for r in prods if r.get("phosphorus_disclosed") == "yes")}


def page(active: str, title: str, body: str, desc: str = "", path: str = "index.html") -> str:
    nav = [("index", "ホーム", "index.html"), ("weight", "体重管理", "weight.html"),
           ("kidney", "腎臓相談シート", "kidney.html"),
           ("coverage", "網羅性", "coverage.html"), ("about", "この調べ方", "about.html")]
    navhtml = "".join(
        f'<a class="{"active" if active==k else ""}" href="{href}">{label}</a>'
        for k, label, href in nav)
    desc = desc or "キャットフードを広告やランキングではなく、公式の保証成分・出典・乾物量換算のファクトで比較。評価せず順位を付けず、判断は獣医師へ。"
    canonical = f"{BASE_URL}/{path}"
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}｜{SITE_NAME}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{canonical}">
<link rel="icon" href="{FAVICON}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{title}｜{SITE_NAME}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary">
<link rel="stylesheet" href="style.css"></head><body>
<header class="site"><div class="wrap">
 <a class="brand" href="index.html">🐾 ねこごはんファクト</a>
 <nav class="main">{navhtml}</nav>
</div></header>
<main class="wrap">{body}</main>
<footer class="site"><div class="wrap">
 当サイトは評価・順位付け・おすすめを行いません。公式表示を転記・乾物量換算した出典付きファクトのみを掲載しています。
 購入リンクから手数料を得る場合がありますが、掲載順・内容には一切影響しません。<br>
 ※医療上の判断は必ずかかりつけの獣医師にご相談ください。本サイトは診断・治療の助言を行いません。
 <br>最終更新 {today_stamp()}
</div></footer></body></html>"""


def table_block(products: list[dict], cols: list[dict], sort_key: str,
                asc: bool, ponly: bool) -> str:
    js = (TABLE_JS
          .replace("__DATA__", json.dumps(products, ensure_ascii=False))
          .replace("__COLS__", json.dumps(cols, ensure_ascii=False))
          .replace("__SORT__", json.dumps(sort_key))
          .replace("__ASC__", "true" if asc else "false")
          .replace("__PONLY__", "true" if ponly else "false"))
    return ('<table><thead id="thead"></thead><tbody id="tbody"></tbody></table>'
            f'<script>{js}</script>')


def build_index(cov: dict) -> str:
    return f"""
<h1>キャットフードを、広告ではなく<br>成分・出典のファクトで。</h1>
<p class="lead">ランキングも、おすすめ度も出しません。各メーカー公式の保証成分を転記し、
水分を除いた<b>乾物量換算</b>で公平に並べ替えられるようにしただけのサイトです。
判断するのではなく、<b>あなたと獣医師が判断できる状態</b>を準備します。</p>
<div>
 <span class="tag">評価・順位なし</span><span class="tag">全数値に公式出典＋取得日</span>
 <span class="tag">乾物量換算</span><span class="tag">4状態（記載なしを「無し」と断定しない）</span>
 <span class="tag">非診断</span>
</div>
<div class="cards">
 <div class="card"><h2 style="margin-top:4px">体重管理で見る</h2>
  <p class="lead">カロリー密度（kcal/100g）の低い順に並べ替え。「太った猫向け」とは言いません。</p>
  <a href="weight.html">→ 体重管理ビュー</a></div>
 <div class="card"><h2 style="margin-top:4px">腎臓が気になる方へ</h2>
  <p class="lead">リンを公式開示している商品だけを、乾物量換算で比較。印刷して獣医師にご相談ください。</p>
  <a href="kidney.html">→ 腎臓相談シート</a></div>
</div>
<div class="disclaimer">
 ⚠️ 「記載なし」は「含まれない」ではなく「メーカーが公開していない」という意味です。
 数値の良し悪しは当サイトでは判断しません。療法食は獣医師の指示なく切り替えないでください。
</div>
<h2>いま掲載している範囲</h2>
<p class="lead">対象母集団＝ペットフード公正取引協議会 正会員<b>{cov['pop']}社</b>。
そのうち公式に成分を開示している商品を掲載しています。
データ取得 <b>{len(cov['with_data'])}社・{cov['products']}商品</b>（リン開示 {cov['p_open']}商品）。
範囲とその限界は <a href="coverage.html">網羅性ページ</a> で正直に開示しています。</p>
"""


def build_weight(products: list[dict]) -> str:
    cols = [{"k": "product_name", "t": "商品 / メーカー", "type": "name"},
            {"k": "form", "t": "種別"},
            {"k": "calorie_density_100g", "t": "カロリー密度 kcal/100g", "type": "cal"},
            {"k": "fat_dm", "t": "脂肪%(乾物量)"},
            {"k": "moisture_pct", "t": "水分%"},
            {"k": "url", "t": "出典", "type": "src"},
            {"k": "buy", "t": "購入先（比較）", "type": "buy"}]
    body = """
<h1>体重管理ビュー</h1>
<p class="lead">カロリー密度の低い順に並べ替えられる一覧です。順位やおすすめではありません。
個包装おやつ（1個あたり表示）は密度比較ができないため「比較不可」と明示します。</p>
<div class="disclaimer">体重管理は総摂取カロリーと運動・個体差で決まります。数値は選ぶための材料で、
適正体重・給与量は獣医師にご相談ください。</div>
<div class="controls">表示 <b id="cnt">0</b> 商品｜並べ替えは列見出しをクリック</div>
"""
    return body + table_block(products, cols, "calorie_density_100g", True, False)


def build_kidney(products: list[dict]) -> str:
    cols = [{"k": "product_name", "t": "商品 / メーカー", "type": "name"},
            {"k": "form", "t": "種別"},
            {"k": "phosphorus_dm", "t": "リン%(乾物量)"},
            {"k": "protein_dm", "t": "たんぱく質%(乾物量)"},
            {"k": "moisture_pct", "t": "水分%"},
            {"k": "calorie_density_100g", "t": "カロリー密度", "type": "cal"},
            {"k": "is_therapeutic", "t": "療法食", "type": "ther"},
            {"k": "url", "t": "出典", "type": "src"},
            {"k": "buy", "t": "購入先（比較）", "type": "buy"}]
    body = """
<h1>腎臓の健康が気になる方向け・比較メモ</h1>
<div class="disclaimer">
 ⚠️ このシートは「おすすめ」ではありません。当サービスは診断・治療の助言を行いません。
 数値は各メーカー公式の表示を転記・乾物量換算したファクトです。
 <b>リン等の数値の解釈は症例ごとに異なります。良し悪しは判断せず、この表を獣医師にお見せください。</b><br>
 療法食は<b>獣医師の指示なく与えないでください</b>。「記載なし」は「含まれない」という意味ではありません。
</div>
<p class="lead">リンを公式に開示している商品だけを表示しています（開示そのものを信頼性の目安にしています）。
低タンパク・低リンが良いか否かは現代獣医学で議論があり、当サイトは立場を取りません。</p>
<div class="controls">
 表示 <b id="cnt">0</b> 商品
 <button onclick="ponly=!ponly;draw()">リン開示のみ ⇔ 全件</button>
 <button onclick="window.print()">🖨 印刷 / PDF保存</button>
</div>
"""
    return body + table_block(products, cols, "phosphorus_dm", True, True)


def _maker_address(name: str) -> str:
    return ""


def build_coverage(cov: dict) -> str:
    # 取得済み / 未取得(確定だがデータ無) / 対象外(キャットフード無し)
    got = "".join(f"<li>{m}</li>" for m in cov["with_data"])
    nodata = "".join(f"<li>{m}</li>" for m in cov["no_data"])
    excl = "".join(f"<li>{r['company_name']}<span class='na'>（{r.get('note','')}）</span></li>"
                   for r in cov["excluded"])
    return f"""
<h1>網羅性 — 「宣言した母集団へのカバー率」</h1>
<p class="lead">「日本のキャットフードを網羅」とは言いません（全商品の公的リストが存在しないため）。
代わりに<b>収録範囲を宣言し、その中のカバー率と未取得を正直に報告</b>します。これが当サイトの網羅性の定義です。</p>
<div class="cards">
 <div class="card"><div class="big">{cov['pop']}</div>対象母集団（公正取引協議会 正会員）</div>
 <div class="card"><div class="big">{len(cov['confirmed'])}</div>公式サイト確定メーカー</div>
 <div class="card"><div class="big">{len(cov['with_data'])}</div>成分データ取得メーカー</div>
 <div class="card"><div class="big">{cov['products']}</div>掲載商品（うちリン開示 {cov['p_open']}）</div>
</div>
<h2>データ取得済みメーカー（{len(cov['with_data'])}社）</h2><ul>{got}</ul>
<h2>未取得メーカー（公式は確定したが成分が静的に取れない／{len(cov['no_data'])}社）</h2>
<p class="lead">製品一覧がJavaScript描画のため自動取得が困難な社です。順次対応します（未取得であることを隠しません）。</p>
<ul>{nodata}</ul>
<h2>母集団から除外（キャットフードの取り扱いなし）</h2><ul>{excl}</ul>
"""


def build_about() -> str:
    return """
<h1>この調べ方（方法と原則）</h1>
<h2>4つの状態で扱う</h2>
<p class="lead">肯定（公式に記載）／否定（公式に記載）／<b>不明・要確認</b>／矛盾。
「情報がない」を「含まれない」と混同しません。空欄は「メーカーが公開していない」という意味です。</p>
<h2>乾物量換算（dry matter basis）</h2>
<p class="lead">ウェット（水分80%前後）とドライ（水分10%前後）を生の数字で比べると不公平になります。
水分を除いた基準に揃えて比較します。<br>
<code>乾物量値(%) = 表示値(%) ÷ (100 − 水分%) × 100</code></p>
<h2>出典と鮮度</h2>
<p class="lead">全数値にメーカー公式の出典URLと取得日を付けています。フードは価格・成分が変わるため、
日付のない数値は載せません。</p>
<h2>順位を付けない・手数料で並べない（アフィリエイト遮断）</h2>
<p class="lead">「おすすめ度」「総合○位」を機能として持ちません。並び順はユーザーが選ぶ客観ソート
（商品名・価格・カロリー密度・リン量）だけで、<b>紹介手数料を表示順の入力に一切使いません</b>。
購入リンクは全商品・全チャネルに等しく付け、「どこで買えるか」の便益として提供します。</p>
<h2>非診断</h2>
<p class="lead">「この病気にはこのフード」とは言いません。療法食は獣医師の指示が前提です。
出力の頂点は、印刷して獣医師に持っていく<b>相談シート</b>です。</p>
"""


def main() -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "style.css").write_text(CSS, encoding="utf-8")
    products = load_products()
    cov = coverage()
    pages = {
        "index.html": ("index", "ホーム", build_index(cov),
                       "キャットフードを広告やランキングではなく公式の保証成分・出典・乾物量換算のファクトで比較。評価せず順位を付けず判断は獣医師へ。"),
        "weight.html": ("weight", "体重管理ビュー", build_weight(products),
                        "キャットフードをカロリー密度(kcal/100g)で並べ替えられる出典付き一覧。おすすめ・順位は出しません。"),
        "kidney.html": ("kidney", "腎臓相談シート", build_kidney(products),
                        "リンを公式開示しているキャットフードを乾物量換算で比較。印刷して獣医師にご相談ください。非診断。"),
        "coverage.html": ("coverage", "網羅性", build_coverage(cov),
                          "対象母集団とカバー率・未取得・対象外を正直に開示。宣言した範囲への網羅性。"),
        "about.html": ("about", "この調べ方", build_about(),
                       "4状態ラベル・乾物量換算・出典必須・アフィリエイト遮断・非診断。データの作り方を公開。"),
    }
    for fname, (active, title, body, desc) in pages.items():
        (SITE / fname).write_text(page(active, title, body, desc, fname), encoding="utf-8")

    # sitemap.xml / robots.txt
    locs = "".join(f"<url><loc>{BASE_URL}/{f}</loc><lastmod>{today_stamp()}</lastmod></url>"
                   for f in pages)
    (SITE / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>',
        encoding="utf-8")
    (SITE / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n", encoding="utf-8")
    # GitHub Pages: Jekyll処理を無効化（_や記号ファイルをそのまま配信）
    (SITE / ".nojekyll").write_text("", encoding="utf-8")

    safe_print(f"[site] {len(pages)}ページ + sitemap/robots 生成 / 掲載{cov['products']}商品 / 取得{len(cov['with_data'])}社")
    safe_print(f"  -> {SITE / 'index.html'}（ブラウザで開く）/ 公開先 {BASE_URL}/")


if __name__ == "__main__":
    main()
