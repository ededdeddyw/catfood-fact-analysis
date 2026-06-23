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

# 肉球マスク（h2見出しのアクセント用・単色）
_PAW_MASK = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
             "%3Cg fill='black'%3E%3Cellipse cx='22' cy='20' rx='6' ry='8'/%3E%3Cellipse cx='42' cy='20' rx='6' ry='8'/%3E"
             "%3Cellipse cx='10' cy='34' rx='5.5' ry='7'/%3E%3Cellipse cx='54' cy='34' rx='5.5' ry='7'/%3E"
             "%3Cpath d='M32 28c9 0 16 7 16 15 0 6-7 8-16 8s-16-2-16-8c0-8 7-15 16-15z'/%3E%3C/g%3E%3C/svg%3E")

# ヘッダーのブランド猫（顔）
BRAND_CAT = ('<svg viewBox="0 0 48 48" aria-hidden="true">'
             '<g fill="#8a5a3c"><path d="M14 14 L11 3 L24 12 Z"/><path d="M34 14 L37 3 L24 12 Z"/>'
             '<circle cx="24" cy="27" r="16"/></g>'
             '<circle cx="18" cy="25" r="2.4" fill="#fffaf3"/><circle cx="30" cy="25" r="2.4" fill="#fffaf3"/>'
             '<path d="M21 31 l3 3 l3 -3 z" fill="#d98c7a"/></svg>')

# トップのヒーロー（座り猫＋ごはん茶碗）
HERO_ART = ('<svg class="art" viewBox="0 0 200 150" aria-hidden="true">'
            '<g class="catsil">'
            '<path d="M78 50 C58 50 48 78 48 100 C48 120 64 126 78 126 C92 126 108 120 108 100 C108 78 98 50 78 50Z"/>'
            '<path d="M107 116 C133 114 133 78 113 72 C124 83 116 102 102 103Z"/>'
            '<circle cx="78" cy="34" r="22"/><path d="M63 20 L59 0 L78 16 Z"/><path d="M93 20 L97 0 L78 16 Z"/></g>'
            '<circle cx="70" cy="32" r="3" fill="#fffaf3"/><circle cx="86" cy="32" r="3" fill="#fffaf3"/>'
            '<path d="M75 40 l3 3 l3 -3 z" fill="#d98c7a"/>'
            '<path class="bowl-body" d="M118 104 a32 10 0 0 0 64 0 l-6 26 a26 7 0 0 1 -52 0 z"/>'
            '<ellipse class="bowl-food" cx="150" cy="104" rx="34" ry="10"/>'
            '<circle cx="142" cy="101" r="3" fill="#a87544"/><circle cx="156" cy="103" r="3" fill="#a87544"/>'
            '<circle cx="150" cy="98" r="3" fill="#a87544"/></svg>')

# フッターの座り猫
FOOTER_CAT = ('<svg class="fcat" viewBox="0 0 120 130" aria-hidden="true"><g class="catsil">'
              '<path d="M60 56 C42 56 33 80 33 100 C33 118 47 123 60 123 C73 123 87 118 87 100 C87 80 78 56 60 56Z"/>'
              '<path d="M86 112 C110 110 110 78 92 72 C103 83 95 102 82 103Z"/>'
              '<circle cx="60" cy="42" r="22"/><path d="M45 28 L41 6 L60 23 Z"/><path d="M75 28 L79 6 L60 23 Z"/>'
              '</g></svg>')

# 公開先URL（GitHub Pages のプロジェクトページ既定。独自ドメイン時はここを変える）
BASE_URL = "https://ededdeddyw.github.io/catfood-fact-analysis"
SITE_NAME = "ねこごはんファクト"
# Supabase（体重記録のクラウド保存）。anonは公開キーで RLS が守るため公開リポジトリでも安全。
SUPABASE_URL = "https://yjfogfsgwylzrkksremm.supabase.co"
SUPABASE_ANON = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                 "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlqZm9nZnNnd3lsenJra3NyZW1tIiwicm9sZSI6ImFub24i"
                 "LCJpYXQiOjE3ODIxNzM3NjYsImV4cCI6MjA5Nzc0OTc2Nn0."
                 "qxxpf2Gmzntz6XefggwLItjX_odCWqE3r1ZsYgNdd6k")
# 絵文字favicon（外部ファイル不要のSVGデータURI）
FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
           "viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%90%BE%3C/text%3E%3C/svg%3E")

# ブラウン基調 + 猫イラスト(SVG)で温かみのある配色
_PAW_BG = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80' "
           "viewBox='0 0 80 80'%3E%3Cg fill='%23b89a78' fill-opacity='0.18'%3E"
           "%3Cellipse cx='30' cy='34' rx='5' ry='7'/%3E%3Cellipse cx='50' cy='34' rx='5' ry='7'/%3E"
           "%3Cellipse cx='20' cy='44' rx='4.5' ry='6'/%3E%3Cellipse cx='60' cy='44' rx='4.5' ry='6'/%3E"
           "%3Cpath d='M40 42c7 0 13 6 13 12 0 5-6 6-13 6s-13-1-13-6c0-6 6-12 13-12z'/%3E%3C/g%3E%3C/svg%3E")

CSS = """
*{box-sizing:border-box}
:root{--accent:#8a5a3c;--accent-d:#5e3b22;--cream:#f5ede2;--card:#fffdf9;
 --line:#e7dcca;--ink:#3b2f26;--muted:#90806d}
body{font-family:system-ui,-apple-system,"Hiragino Maru Gothic ProN","Hiragino Kaku Gothic ProN",Meiryo,sans-serif;
 margin:0;color:var(--ink);background:var(--cream);line-height:1.7}
a{color:var(--accent)}
.wrap{max-width:1040px;margin:0 auto;padding:0 18px}
header.site{background:#fffaf3;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5;
 box-shadow:0 1px 0 rgba(94,59,34,.04)}
header.site .wrap{display:flex;align-items:center;gap:18px;height:60px}
.brand{font-weight:800;font-size:18px;color:var(--accent-d);text-decoration:none;white-space:nowrap;
 display:flex;align-items:center;gap:7px}
.brand svg{width:26px;height:26px;flex:none}
nav.main{display:flex;gap:14px;flex-wrap:wrap;font-size:14px}
nav.main a{color:#5b4a3a;text-decoration:none;padding:4px 2px;border-bottom:2px solid transparent}
nav.main a:hover{color:var(--accent)}
nav.main a.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:700}
h1{font-size:27px;margin:22px 0 8px;color:var(--accent-d);letter-spacing:.01em}
h2{font-size:19px;margin:26px 0 8px;padding-left:30px;position:relative;color:var(--accent-d)}
h2::before{content:"";position:absolute;left:0;top:3px;width:20px;height:20px;
 background:var(--accent);-webkit-mask:url("PAWMASK") center/contain no-repeat;mask:url("PAWMASK") center/contain no-repeat;opacity:.85}
.lead{font-size:15px;color:#5b4a3a;margin:0 0 8px}
.tag{display:inline-block;background:#efe4d4;color:#6b4324;border-radius:999px;padding:3px 11px;font-size:12px;margin:2px 6px 2px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:14px 0;
 box-shadow:0 2px 10px rgba(94,59,34,.05)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.disclaimer{background:#fbf1df;border:1px solid #e6c79a;border-radius:10px;padding:12px 14px;font-size:13.5px;margin:14px 0;color:#5a4326}
.controls{margin:12px 0;font-size:14px;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.controls button{border:1px solid var(--line);background:#fffaf3;color:#5b4a3a;border-radius:8px;padding:5px 11px;cursor:pointer}
.controls button:hover{background:#f0e6d6}
table{border-collapse:collapse;width:100%;background:var(--card);font-size:13.5px;border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{border-bottom:1px solid #efe7d8;padding:8px 10px;text-align:left;vertical-align:top}
th{background:#f3e9da;cursor:pointer;white-space:nowrap;position:sticky;top:60px;color:#6b4324}
tr:hover td{background:#fdf8f0}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.na{color:#a99a86;font-size:12px}
.ther{color:#a8421f;font-weight:700;font-size:12px}
.buy a{display:inline-block;margin:0 3px 2px 0;padding:1px 6px;border:1px solid var(--line);border-radius:4px;
 color:#6b4324;text-decoration:none;font-size:11px;background:#fffaf3}
.mk{color:#a3917c;font-size:11.5px}
.hero{display:flex;align-items:center;gap:22px;flex-wrap:wrap;background:
 linear-gradient(180deg,#fbf3e7,#f5ebdc);border:1px solid var(--line);border-radius:18px;
 padding:22px 24px;margin:18px 0;background-image:url("PAWBG"),linear-gradient(180deg,#fbf3e7,#f5ebdc);background-size:90px,auto}
.hero .art{flex:none;width:170px;max-width:38vw}
.hero .txt{flex:1;min-width:230px}
.hero-photo{flex:none;width:250px;max-width:44vw;aspect-ratio:4/3;object-fit:cover;border-radius:16px;
 box-shadow:0 5px 16px rgba(94,59,34,.16);border:3px solid #fffaf3}
.pagephoto{width:100%;height:170px;object-fit:cover;border-radius:14px;margin:10px 0;
 box-shadow:0 3px 12px rgba(94,59,34,.10)}
.photo-accent{float:right;width:200px;max-width:40vw;aspect-ratio:4/3;object-fit:cover;border-radius:14px;
 margin:0 0 12px 16px;box-shadow:0 3px 12px rgba(94,59,34,.10)}
.credits{font-size:12px;color:#8a7866}.credits li{margin:3px 0}
.pagehero{display:flex;align-items:center;gap:14px;margin-top:8px}
.pagehero svg{width:54px;height:54px;flex:none}
.catsil{fill:var(--accent)}
.bowl-food{fill:#c99a66}.bowl-body{fill:#7b4f2e}.bowl-rim{fill:#9c6b43}
footer.site{margin-top:44px;background:#fffaf3;border-top:1px solid var(--line);font-size:12.5px;color:#7a6957}
footer.site .wrap{padding:18px;display:flex;gap:14px;align-items:flex-start}
footer.site .fcat{width:40px;flex:none;opacity:.8}
.big{font-size:32px;font-weight:800;color:var(--accent)}
@media print{header.site,nav.main,.controls,.buy,footer.site nav,.noprint,.hero .art,.pagehero svg{display:none}
 body{background:#fff} th{position:static} .disclaimer{border:1px solid #999;background:#fff}}

/* ===== リッチなランディング用コンポーネント ===== */
.btn{display:inline-block;border-radius:999px;padding:11px 22px;font-weight:700;font-size:15px;
 text-decoration:none;cursor:pointer;border:2px solid transparent;transition:transform .08s,box-shadow .2s}
.btn:hover{transform:translateY(-1px)}
.btn-primary{background:var(--accent);color:#fff;box-shadow:0 6px 16px rgba(138,90,60,.28)}
.btn-primary:hover{background:var(--accent-d)}
.btn-ghost{background:#fff;color:var(--accent-d);border-color:var(--line)}
.btn-row{display:flex;gap:12px;flex-wrap:wrap;margin-top:16px}
.section{padding:46px 0}
.section.alt{background:#fbf3e8;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.section.tint{background:linear-gradient(180deg,#fff6ec,#f7ecdc)}
.sec-head{text-align:center;max-width:680px;margin:0 auto 26px}
.eyebrow{display:inline-block;letter-spacing:.14em;font-size:12px;font-weight:800;color:#b07a4e;
 background:#f1e3d2;border-radius:999px;padding:5px 14px;margin-bottom:12px}
.sec-head h2{font-size:clamp(21px,3.4vw,30px);border:none;padding:0;margin:0 0 8px;display:block}
.sec-head h2::before{display:none}
.sec-head p{color:#6b5a48;font-size:15px;margin:0}
.bighero{background:radial-gradient(120% 120% at 80% 0,#fdf3e6 0,#f3e6d2 60%,#efe0cb 100%);
 border-bottom:1px solid var(--line)}
.bighero .wrap{display:flex;align-items:center;gap:40px;flex-wrap:wrap;padding:54px 18px 50px}
.bighero .htxt{flex:1 1 340px}
.bighero h1{font-size:clamp(27px,4.6vw,44px);line-height:1.25;margin:12px 0 12px}
.bighero .sub{font-size:clamp(15px,2vw,18px);color:#5b4a3a;margin:0;max-width:30em}
.bighero .himg{flex:1 1 320px;display:flex;justify-content:center}
.bighero .himg img{width:100%;max-width:440px;aspect-ratio:4/3;object-fit:cover;border-radius:22px;
 box-shadow:0 14px 36px rgba(94,59,34,.22);border:5px solid #fffaf3}
.features{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px}
.feature{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;
 box-shadow:0 2px 10px rgba(94,59,34,.05)}
.feature .ic{width:46px;height:46px;border-radius:13px;background:#f3e6d4;display:flex;align-items:center;
 justify-content:center;font-size:24px;margin-bottom:12px}
.feature h3{margin:0 0 6px;font-size:17px;color:var(--accent-d)}
.feature p{margin:0;font-size:14px;color:#6b5a48;line-height:1.7}
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px;counter-reset:s}
.step{position:relative;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px 20px 20px}
.step::before{counter-increment:s;content:counter(s);position:absolute;top:-16px;left:20px;width:36px;height:36px;
 background:var(--accent);color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;
 box-shadow:0 4px 10px rgba(138,90,60,.3)}
.step h3{margin:8px 0 6px;font-size:16px;color:var(--accent-d)}
.step p{margin:0;font-size:14px;color:#6b5a48}
.split{display:flex;gap:34px;align-items:center;flex-wrap:wrap}
.split>div{flex:1 1 300px}
.split img{width:100%;border-radius:18px;object-fit:cover;aspect-ratio:5/4;
 box-shadow:0 8px 24px rgba(94,59,34,.16);border:4px solid #fffaf3}
.split.rev{flex-direction:row-reverse}
.compare{display:grid;grid-template-columns:1fr 1fr;gap:16px;max-width:760px;margin:0 auto}
.compare .col{border-radius:16px;padding:20px;border:1px solid var(--line)}
.compare .them{background:#f4efe9;color:#7a6a59}
.compare .us{background:#fff;border:2px solid var(--accent);box-shadow:0 6px 18px rgba(138,90,60,.12)}
.compare h3{margin:0 0 10px;font-size:16px}
.compare ul{margin:0;padding-left:18px;font-size:14px;line-height:1.85}
.compare .us h3{color:var(--accent-d)}
.statband{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px;text-align:center}
.statband .s{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 10px}
.statband .s b{display:block;font-size:30px;color:var(--accent);font-weight:800;line-height:1.1}
.statband .s span{font-size:12.5px;color:#7a6a59}
.goalchips{display:flex;gap:9px;flex-wrap:wrap;margin:6px 0}
.goalchips a{background:#fff;border:1px solid var(--line);border-radius:999px;padding:7px 15px;
 text-decoration:none;color:#6b4324;font-size:14px;font-weight:600}
.goalchips a:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
.pagehead{background:linear-gradient(180deg,#fdf4e7,#f6ead8);border-bottom:1px solid var(--line);
 margin:0 -18px;padding:30px 18px 26px}
.pagehead h1{margin:6px 0 8px}
.pagehead .lead{max-width:42em}
@media(max-width:560px){.compare{grid-template-columns:1fr}.bighero .wrap{gap:24px;padding:34px 18px}}

/* ===== 体重記録トラッカー ===== */
.tracker{display:grid;grid-template-columns:300px 1fr;gap:20px;align-items:start}
@media(max-width:720px){.tracker{grid-template-columns:1fr}}
.panel{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 2px 10px rgba(94,59,34,.05)}
.field{margin:10px 0}
.field label{display:block;font-size:12.5px;color:#7a6a59;margin-bottom:4px;font-weight:700}
.field input,.field select{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:9px;font-size:15px;background:#fffaf3}
.row2{display:flex;gap:10px}.row2>*{flex:1}
.trend{font-size:14px;margin:6px 0 0}
.trend .up{color:#a8421f;font-weight:700}.trend .down{color:#1b7a3d;font-weight:700}.trend .flat{color:#7a6a59;font-weight:700}
.chartwrap{width:100%;overflow:hidden}
.chartwrap svg{width:100%;height:auto}
.chartwrap .ln{fill:none;stroke:var(--accent);stroke-width:2.5}
.chartwrap .dot{fill:#fff;stroke:var(--accent);stroke-width:2}
.chartwrap .tgt{stroke:#caa46f;stroke-dasharray:5 4;stroke-width:1.5}
.chartwrap .ax{stroke:#e7dcca}.chartwrap .axt{fill:#a3917c;font-size:11px}
.elist{width:100%;border-collapse:collapse;margin-top:10px;font-size:14px}
.elist td,.elist th{border-bottom:1px solid #efe7d8;padding:6px 8px;text-align:left}
.elist .del{color:#a8421f;cursor:pointer;border:none;background:none;font-size:13px}
.savednote{font-size:12px;color:#a3917c;margin-top:8px}

/* ===== 成分レーダー（5角形）一覧 ===== */
.fbar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:12px 0}
.fbtn{border:1px solid var(--line);background:#fffaf3;border-radius:999px;padding:5px 14px;cursor:pointer;font-size:13px;color:#6b4324}
.fbtn.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.shapegrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(212px,1fr));gap:16px;margin-top:12px}
.shapecard{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;text-align:center;box-shadow:0 2px 10px rgba(94,59,34,.05)}
.shapecard .rname{font-size:13px;font-weight:700;line-height:1.4;min-height:54px;display:flex;flex-direction:column;justify-content:center}
.radar{width:168px;height:168px;margin:2px auto;display:block}
.rnums{font-size:11.5px;color:#6b5a48;margin:8px 0 6px;font-variant-numeric:tabular-nums}
.rsrc{font-size:11px}.rsrc .buy a{margin-left:2px}
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


# 観点（透明な条件マッチ）: docs/07。基準を明示し、合致商品＋実値を見せる（スコア化しない）。
GOALS = [
    {"key": "weight", "label": "体重を管理したい", "tier": "life",
     "metric": "カロリー密度", "unit": "kcal/100g", "field": "calorie_density_100g",
     "dir": "asc", "need": ["calorie_density_100g"],
     "criterion": "カロリー密度が低い順",
     "why": "1日の総カロリーを抑えやすい商品です。適正量・運動でも変わるので給与量は獣医へ。"},
    {"key": "protein", "label": "高たんぱくにしたい", "tier": "life",
     "metric": "たんぱく質(乾物量)", "unit": "%", "field": "protein_dm",
     "dir": "desc", "need": ["protein_dm"],
     "criterion": "たんぱく質(乾物量)が高い順",
     "why": "筋肉維持を重視する方向け。腎臓に懸念がある場合は高たんぱくが適さないこともあるため獣医へ。"},
    {"key": "moisture", "label": "水分を摂らせたい", "tier": "life",
     "metric": "水分", "unit": "%", "field": "moisture_pct",
     "dir": "desc", "need": ["moisture_pct"], "onlyForm": "ウェット",
     "criterion": "ウェット（高水分）",
     "why": "あまり水を飲まない子の水分補給に。ウェットを中心に表示しています。"},
    {"key": "grainfree", "label": "穀物を避けたい", "tier": "life",
     "metric": "穀物表記", "unit": "", "field": None, "flag": "grain_free", "flagval": "yes",
     "criterion": "原材料の主要部に穀物表記なし（参考）",
     "why": "原材料表示に基づく参考判定です（表示の主要部に米・小麦・とうもろこし等が無い商品）。"},
    {"key": "fiber", "label": "毛玉・繊維を増やしたい", "tier": "life",
     "metric": "粗繊維", "unit": "%", "field": "fiber_pct",
     "dir": "desc", "need": ["fiber_pct"],
     "criterion": "粗繊維が高い順",
     "why": "毛玉・便通対策で繊維を増やしたい方向け。"},
    {"key": "urinary", "label": "尿路が気になる", "tier": "health",
     "metric": "マグネシウム", "unit": "%", "field": "magnesium_pct",
     "dir": "asc", "need": ["magnesium_pct"],
     "criterion": "マグネシウムが低い順（公式開示の商品のみ）",
     "why": "ストルバイト尿石で見られる指標です。数値の良し悪しは判断しません。診断・療法食は獣医の指示が前提です。",
     "vet": True},
    {"key": "kidney", "label": "腎臓が気になる", "tier": "health",
     "metric": "リン(乾物量)", "unit": "%", "field": "phosphorus_dm",
     "dir": "asc", "need": ["phosphorus_dm"], "flag": "phosphorus_disclosed", "flagval": "yes",
     "criterion": "リン(乾物量)が低い順（公式開示の商品のみ）",
     "why": "腎臓の食事管理で獣医が見る値です。良し悪しは当サイトでは判断しません。この結果を獣医にお見せください。",
     "vet": True},
]


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


def page(active: str, title: str, body: str, desc: str = "", path: str = "index.html",
         wrap: bool = True) -> str:
    nav = [("index", "ホーム", "index.html"), ("find", "目的から選ぶ", "find.html"),
           ("shape", "成分のかたち", "shape.html"), ("calc", "成分ツール", "calc.html"),
           ("record", "体重記録", "record.html"),
           ("weight", "体重管理", "weight.html"), ("kidney", "腎臓シート", "kidney.html"),
           ("blog", "読みもの", "blog.html"),
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
 <a class="brand" href="index.html">{BRAND_CAT}ねこごはんファクト</a>
 <nav class="main">{navhtml}</nav>
</div></header>
<main class="{'wrap' if wrap else ''}">{body}</main>
<footer class="site"><div class="wrap">
 {FOOTER_CAT}
 <div>当サイトは総合順位・おすすめ度を付けません。目的ごとに見る指標と条件を明示し、公式表示を転記・乾物量換算した
 出典付きファクトと実値で示します。購入リンクから手数料を得る場合がありますが、掲載順・内容には一切影響しません。<br>
 ※医療上の判断は必ずかかりつけの獣医師にご相談ください。本サイトは診断・治療の助言を行いません。
 <br>最終更新 {today_stamp()}</div>
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


def pagehead(eyebrow: str, title: str) -> str:
    return f'<div class="pagehead"><span class="eyebrow">{eyebrow}</span><h1>{title}</h1></div>'


def build_index(cov: dict) -> str:
    g_chips = "".join(f'<a href="find.html">{x["label"]}</a>'
                      for x in GOALS if x["tier"] == "life")
    return f"""
<section class="bighero"><div class="wrap">
 <div class="htxt">
  <span class="eyebrow">出典つきファクト・非診断</span>
  <h1>『あなたが大切』だから、<br>成分で選ぶ。</h1>
  <p class="sub">おすすめ度や総合順位という曖昧な点数は付けません。目的ごとに<b>見る指標と条件を明示</b>し、
  合う商品を<b>実際の数値つき</b>で。「なぜ合うか」が数字で見える——それがランキングサイトとの違いです。</p>
  <div class="btn-row">
   <a class="btn btn-primary" href="find.html">🎯 目的から選ぶ</a>
   <a class="btn btn-ghost" href="about.html">この調べ方を見る</a>
  </div>
 </div>
 <div class="himg"><img src="img/hero.jpg" alt="キャットフードの皿を前にした猫" loading="eager"></div>
</div></section>

<section class="section"><div class="wrap">
 <div class="sec-head"><span class="eyebrow">3つの約束</span>
  <h2>広告でもランキングでもなく、ファクトで。</h2>
  <p>口コミや推測スコアは出しません。判断材料を、出典つきで、淡々と。</p></div>
 <div class="features">
  <div class="feature"><div class="ic">🏷️</div><h3>評価・順位を付けない</h3>
   <p>総合○位やおすすめ度という曖昧な点数を作りません。基準を全部見せ、数値で比べられる状態にします。</p></div>
  <div class="feature"><div class="ic">📑</div><h3>全数値に公式出典＋取得日</h3>
   <p>各メーカー公式の保証成分を転記。日付のない数値は載せません。水分を除いた乾物量換算で公平に比較。</p></div>
  <div class="feature"><div class="ic">🩺</div><h3>判断は獣医師へ（非診断）</h3>
   <p>「この病気にはこれ」とは言いません。健康に関わる観点は指標を示し、印刷して獣医師に渡せる形に。</p></div>
 </div>
</div></section>

<section class="section alt"><div class="wrap">
 <div class="sec-head"><span class="eyebrow">使い方</span><h2>3ステップで選べます</h2></div>
 <div class="steps">
  <div class="step"><h3>目的を選ぶ</h3><p>体重管理・高たんぱく・腎臓が気になる…「こうしたい」を選びます。</p></div>
  <div class="step"><h3>指標と条件が出る</h3><p>その目的で見るべき客観指標と絞り込み条件を明示します（隠しません）。</p></div>
  <div class="step"><h3>数値で比べて相談</h3><p>合う商品を実値つきで表示。印刷して獣医師に相談できます。</p></div>
 </div>
</div></section>

<section class="section"><div class="wrap">
 <div class="split">
  <div><img src="img/eating.jpg" alt="ごはんを食べる猫"></div>
  <div>
   <span class="eyebrow">目的から選ぶ</span>
   <h2 style="border:none;padding:0">「こうなりたい」に、<br>合う一皿を。</h2>
   <p class="lead">生活の目的（体重・たんぱく・水分・穀物・毛玉）から、健康に関わる観点（尿路・腎臓）まで。
   後者は獣医相談を必ず併記します。</p>
   <div class="goalchips">{g_chips}</div>
   <div class="btn-row"><a class="btn btn-primary" href="find.html">目的から選ぶ →</a></div>
  </div>
 </div>
</div></section>

<section class="section alt"><div class="wrap">
 <div class="split rev">
  <div><img src="img/kitten.jpg" alt="くつろぐ仔猫"></div>
  <div>
   <span class="eyebrow">うちの子の管理</span>
   <h2 style="border:none;padding:0">体重を記録して、<br>変化に早く気づく。</h2>
   <p class="lead">猫の体重を記録するとグラフで増減の傾向が見えます。増え気味なら、そのまま
   カロリー密度の低いフード探しへ。記録は端末内に保存（ログイン同期は近日）。</p>
   <div class="btn-row"><a class="btn btn-primary" href="record.html">体重を記録する →</a></div>
  </div>
 </div>
</div></section>

<section class="section tint"><div class="wrap">
 <div class="sec-head"><span class="eyebrow">ふつうのサイトとの違い</span><h2>ランキングではなく、根拠を。</h2></div>
 <div class="compare">
  <div class="col them"><h3>よくある比較サイト</h3>
   <ul><li>総合○位・おすすめ度（基準は不透明）</li><li>紹介手数料の高い順に並びがち</li>
   <li>口コミ・主観の星評価</li><li>出典・取得日があいまい</li></ul></div>
  <div class="col us"><h3>ねこごはんファクト</h3>
   <ul><li>順位を付けない。見る指標と条件を明示</li><li>手数料は表示順に一切使わない</li>
   <li>公式の保証成分＋乾物量換算の実値</li><li>全数値に出典URL＋取得日／非診断</li></ul></div>
 </div>
</div></section>

<section class="section alt"><div class="wrap">
 <div class="sec-head"><span class="eyebrow">網羅性</span><h2>掲載範囲を、正直に。</h2>
  <p>「全部載せています」とは言いません。宣言した母集団へのカバー率と未掲載を開示します。</p></div>
 <div class="statband">
  <div class="s"><b>{cov['pop']}</b><span>対象母集団（協議会 正会員）</span></div>
  <div class="s"><b>{len(cov['confirmed'])}</b><span>公式サイト確定</span></div>
  <div class="s"><b>{len(cov['with_data'])}</b><span>成分データ取得</span></div>
  <div class="s"><b>{cov['products']}</b><span>掲載商品</span></div>
  <div class="s"><b>{cov['p_open']}</b><span>リン開示商品</span></div>
 </div>
 <div class="btn-row" style="justify-content:center;margin-top:18px"><a class="btn btn-ghost" href="coverage.html">網羅性ページを見る →</a></div>
</div></section>

<section class="section"><div class="wrap">
 <div class="cards">
  <div class="card"><h2 style="margin-top:4px">成分のかたち</h2>
   <p class="lead">主要成分を乾物量の5角形レーダーで一覧。点数ではなく構成を見る。</p>
   <a class="btn btn-ghost" href="shape.html">成分のかたち →</a></div>
  <div class="card"><h2 style="margin-top:4px">成分ツール（袋の数値）</h2>
   <p class="lead">手元のフードの数値を入れると、乾物量の形＋成分が近い商品が分かる。</p>
   <a class="btn btn-ghost" href="calc.html">成分ツール →</a></div>
  <div class="card"><h2 style="margin-top:4px">体重管理ビュー</h2>
   <p class="lead">カロリー密度の低い順。「太った猫向け」とは言いません。</p>
   <a class="btn btn-ghost" href="weight.html">体重管理 →</a></div>
  <div class="card"><h2 style="margin-top:4px">腎臓相談シート</h2>
   <p class="lead">リン開示商品を乾物量換算で。印刷して獣医師にご相談ください。</p>
   <a class="btn btn-ghost" href="kidney.html">腎臓相談シート →</a></div>
 </div>
 <div class="disclaimer" style="margin-top:18px">⚠️「記載なし」は「含まれない」ではなく「メーカーが公開していない」という意味です。
 数値の良し悪しは当サイトでは判断しません。療法食は獣医師の指示なく切り替えないでください。</div>
</div></section>
"""


def build_weight(products: list[dict]) -> str:
    cols = [{"k": "product_name", "t": "商品 / メーカー", "type": "name"},
            {"k": "form", "t": "種別"},
            {"k": "calorie_density_100g", "t": "カロリー密度 kcal/100g", "type": "cal"},
            {"k": "fat_dm", "t": "脂肪%(乾物量)"},
            {"k": "moisture_pct", "t": "水分%"},
            {"k": "url", "t": "出典", "type": "src"},
            {"k": "buy", "t": "購入先（比較）", "type": "buy"}]
    body = f"""
{pagehead("体重管理 / 第2段", "体重管理ビュー")}
<img class="photo-accent" src="img/tabby.jpg" alt="くつろぐ茶トラ猫" loading="lazy">
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
    body = f"""
{pagehead("腎臓 / 第3段（健康・獣医併記）", "腎臓相談シート")}
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
{pagehead("網羅性 / ②③", "宣言した母集団へのカバー率")}
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


FIND_JS = """
let DATA=__DATA__, GOALS=__GOALS__, g=GOALS[0];
function cell(v,u){return (v===''||v==null)?'<span class=\"na\">記載なし（要確認）</span>':v+(u||'');}
function buy(r){var q=encodeURIComponent(((r.maker||'')+' '+(r.product_name||'')).trim());
 return [['楽天','https://search.rakuten.co.jp/search/mall/'+q+'/'],['Amazon','https://www.amazon.co.jp/s?k='+q],
 ['Yahoo','https://shopping.yahoo.co.jp/search?p='+q]].map(c=>'<a href=\"'+c[1]+'\" target=\"_blank\" rel=\"noopener nofollow\">'+c[0]+'</a>').join('');}
function matchOk(r){
 if(g.need)for(const f of g.need){if(r[f]===''||r[f]==null)return false;}
 if(g.onlyForm&&r.form!==g.onlyForm)return false;
 if(g.flag&&r[g.flag]!==g.flagval)return false;
 return true;}
function pick(k){g=GOALS.find(x=>x.key===k);draw();}
function draw(){
 let btns=GOALS.map(x=>'<button class=\"goal'+(x.key===g.key?' on':'')+'\" onclick=\"pick(\\''+x.key+'\\')\">'+x.label+(x.tier==='health'?' ⚕':'')+'</button>').join('');
 document.getElementById('goals').innerHTML=btns;
 let rows=DATA.filter(matchOk);
 if(g.field)rows.sort((a,b)=>{let x=Number(a[g.field]),y=Number(b[g.field]);return g.dir==='asc'?x-y:y-x;});
 let vet=g.vet?'<div class=\"disclaimer\">⚕ これは健康に関わる観点です。数値の良し悪しは判断しません。'+
  '療法食は獣医師の指示なく与えないでください。気になる症状は受診し、この結果を獣医師にご相談ください。</div>':'';
 document.getElementById('banner').innerHTML=
  '<div class=\"card\"><b>選んだ目的：'+g.label+'</b><br>'+
  '見る指標 → <b>'+g.metric+'</b>　／　条件 → <b>'+g.criterion+'</b><br>'+
  '<span class=\"mk\">'+g.why+'</span></div>'+vet;
 let head=g.field
  ? '<tr><th>商品 / メーカー</th><th>'+g.metric+(g.unit?'('+g.unit+')':'')+'<br><span class=\"mk\">なぜ合うか＝この値</span></th><th>種別</th><th>出典</th><th>購入先</th></tr>'
  : '<tr><th>商品 / メーカー</th><th>判定</th><th>種別</th><th>原材料(先頭)</th><th>出典</th><th>購入先</th></tr>';
 let body=rows.map(r=>{
  let why=g.field?'<td class=\"num\"><b>'+cell(r[g.field],g.unit)+'</b></td>'
                 :'<td><b style=\"color:#1b7a3d\">条件に合致</b></td>';
  let extra=g.field?'':'<td><span class=\"mk\">'+(r.ingredients||'')+'</span></td>';
  return '<tr><td>'+(r.product_name||'(無題)')+'<br><span class=\"mk\">'+r.maker+'</span></td>'+
   why+'<td>'+r.form+'</td>'+extra+
   '<td><a href=\"'+r.url+'\" target=\"_blank\" rel=\"noopener\">公式</a> <span class=\"na\">'+r.fetched_at+'</span></td>'+
   '<td class=\"buy\">'+buy(r)+'</td></tr>';}).join('');
 document.getElementById('thead').innerHTML=head;
 document.getElementById('tbody').innerHTML=body;
 document.getElementById('cnt').textContent=rows.length;
}
draw();
"""


def build_find(products: list[dict]) -> str:
    js = (FIND_JS
          .replace("__DATA__", json.dumps(products, ensure_ascii=False))
          .replace("__GOALS__", json.dumps(GOALS, ensure_ascii=False)))
    return """
""" + pagehead("あなたの「こうしたい」から", "目的から選ぶ") + """
<img class="pagephoto" src="img/eating.jpg" alt="ボウルからウェットフードを食べる猫" loading="lazy">
<p class="lead">「こうしたい」を選ぶと、<b>見るべき客観指標と条件を明示</b>したうえで、
それに合う商品を<b>実際の数値つき</b>で並べます。おすすめ度や総合順位という曖昧な点数は付けません。
「なぜ合うか」がそのまま数字で見える状態にします。</p>
<style>
 #goals{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
 .goal{border:1px solid #cfd8dc;background:#fff;border-radius:999px;padding:6px 14px;cursor:pointer;font-size:14px}
 .goal.on{background:#b1442f;color:#fff;border-color:#b1442f;font-weight:700}
</style>
<div id="goals"></div>
<div id="banner"></div>
<div class="controls">合致 <b id="cnt">0</b> 商品｜⚕＝健康に関わる観点（獣医相談を併記）</div>
<table><thead id="thead"></thead><tbody id="tbody"></tbody></table>
""" + f"<script>{js}</script>"


RECORD_JS = r"""
import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm';
const SB = createClient('__SB_URL__','__SB_ANON__');
const KEY='nekogohan_weight_v1';
let state={cats:[],active:null}, session=null;
const cloud=()=>!!session;
const $=id=>document.getElementById(id);
function today(){var d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}
function uid(){return 'c'+Math.random().toString(36).slice(2,8);}
function gLoad(){try{return JSON.parse(localStorage.getItem(KEY))||{cats:[],active:null};}catch(e){return {cats:[],active:null};}}
function gSave(){localStorage.setItem(KEY,JSON.stringify(state));}
function cat(){return state.cats.find(c=>c.id===state.active)||null;}

async function loadState(){
 if(cloud()){
  const {data:cats}=await SB.from('cats').select('*').order('created_at');
  const {data:ents}=await SB.from('weight_entries').select('*');
  state.cats=(cats||[]).map(c=>({id:c.id,name:c.name,target:(c.target!=null?String(c.target):''),
   entries:(ents||[]).filter(e=>e.cat_id===c.id).map(e=>({date:e.entry_date,kg:Number(e.kg)})).sort((a,b)=>a.date<b.date?-1:1)}));
  if(!state.active||!state.cats.find(c=>c.id===state.active))state.active=state.cats[0]?state.cats[0].id:null;
 } else { state=gLoad(); }
}

window.addCat=async function(){var n=$('catname').value.trim();if(!n)return;
 if(cloud()){const {data,error}=await SB.from('cats').insert({name:n}).select().single();
  if(error)return alert('保存に失敗: '+error.message);state.cats.push({id:data.id,name:n,target:'',entries:[]});state.active=data.id;}
 else {var id=uid();state.cats.push({id,name:n,target:'',entries:[]});state.active=id;gSave();}
 $('catname').value='';render();};
window.selCat=function(){state.active=$('catsel').value;if(!cloud())gSave();render();};
window.setTarget=async function(){var c=cat();if(!c)return;var v=$('target').value;c.target=v;
 if(cloud()){await SB.from('cats').update({target:v===''?null:Number(v)}).eq('id',c.id);}else gSave();render();};
window.addEntry=async function(){var c=cat();if(!c)return alert('先に猫を登録してください');
 var d=$('edate').value||today();var kg=parseFloat($('ekg').value);if(!(kg>0))return alert('体重(kg)を入力してください');
 if(cloud()){const {error}=await SB.from('weight_entries').upsert({cat_id:c.id,entry_date:d,kg},{onConflict:'cat_id,entry_date'});
  if(error)return alert('保存に失敗: '+error.message);}
 c.entries=c.entries.filter(e=>e.date!==d);c.entries.push({date:d,kg});c.entries.sort((a,b)=>a.date<b.date?-1:1);
 if(!cloud())gSave();$('ekg').value='';render();};
window.delEntry=async function(d){var c=cat();if(!c)return;
 if(cloud()){await SB.from('weight_entries').delete().eq('cat_id',c.id).eq('entry_date',d);}
 c.entries=c.entries.filter(e=>e.date!==d);if(!cloud())gSave();render();};

window.signUp=async function(){const {data,error}=await SB.auth.signUp({email:$('email').value.trim(),password:$('pw').value});
 if(error)return alert('登録失敗: '+error.message);
 if(!data.session)alert('確認メールを送信しました。メール内のリンクを開くとログインできます。');};
window.signIn=async function(){const {error}=await SB.auth.signInWithPassword({email:$('email').value.trim(),password:$('pw').value});
 if(error)return alert('ログイン失敗: '+error.message);};
window.signOut=async function(){await SB.auth.signOut();};
window.migrateLocal=async function(){const g=gLoad();if(!g.cats||!g.cats.length)return alert('この端末に記録はありません');
 if(!confirm('この端末の記録をクラウドに移しますか？'))return;
 for(const lc of g.cats){const {data:nc,error}=await SB.from('cats').insert({name:lc.name,target:lc.target?Number(lc.target):null}).select().single();
  if(error){console.warn(error);continue;}
  if(lc.entries&&lc.entries.length)await SB.from('weight_entries').upsert(lc.entries.map(e=>({cat_id:nc.id,entry_date:e.date,kg:e.kg})),{onConflict:'cat_id,entry_date'});}
 localStorage.removeItem(KEY);await refresh();alert('クラウドへ移しました。');};

function renderAuth(){var bar=$('authbar');if(!bar)return;
 if(session){var g=gLoad();
  bar.innerHTML='<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">'+
   '<span>☁ クラウド保存中：<b>'+session.user.email+'</b></span>'+
   '<button class="btn btn-ghost" style="padding:6px 14px" onclick="signOut()">ログアウト</button>'+
   ((g.cats&&g.cats.length)?'<button class="btn btn-primary" style="padding:6px 14px" onclick="migrateLocal()">この端末の記録('+g.cats.length+'匹)をクラウドへ</button>':'')+'</div>';
 } else {
  bar.innerHTML='<div style="display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap">'+
   '<div class="field" style="margin:0;min-width:180px"><label>メール</label><input id="email" type="email" placeholder="you@example.com"></div>'+
   '<div class="field" style="margin:0;min-width:150px"><label>パスワード</label><input id="pw" type="password" placeholder="6文字以上"></div>'+
   '<button class="btn btn-primary" style="padding:9px 16px" onclick="signIn()">ログイン</button>'+
   '<button class="btn btn-ghost" style="padding:9px 16px" onclick="signUp()">新規登録</button>'+
   '<span class="mk" style="flex-basis:100%">ログインするとどの端末からでも見られます。ログインせず<b>この端末だけ</b>で使うこともできます（下で記録）。</span></div>';
 }}

async function refresh(){const {data}=await SB.auth.getSession();session=data.session;await loadState();render();}
window.addEventListener('DOMContentLoaded',()=>{refresh();SB.auth.onAuthStateChange((_e,s)=>{session=s;refresh();});});

function chartSVG(entries,target){
 if(!entries.length)return '<p class="na">まだ記録がありません。右上で体重を追加してください。</p>';
 var W=640,H=240,P=38;
 var xs=entries.map(e=>new Date(e.date).getTime());
 var ys=entries.map(e=>e.kg); if(target>0)ys=ys.concat([target]);
 var minx=Math.min.apply(null,xs),maxx=Math.max.apply(null,xs);
 var miny=Math.min.apply(null,ys),maxy=Math.max.apply(null,ys);
 var pad=(maxy-miny)||0.4; miny-=pad*0.2; maxy+=pad*0.2;
 function X(t){return maxx===minx?W/2:P+(W-2*P)*(t-minx)/(maxx-minx);}
 function Y(v){return H-P-(H-2*P)*(v-miny)/(maxy-miny);}
 var pts=entries.map(e=>X(new Date(e.date).getTime()).toFixed(1)+','+Y(e.kg).toFixed(1)).join(' ');
 var dots=entries.map(e=>'<circle class="dot" cx="'+X(new Date(e.date).getTime()).toFixed(1)+'" cy="'+Y(e.kg).toFixed(1)+'" r="4"/>').join('');
 var tgt=target>0?'<line class="tgt" x1="'+P+'" y1="'+Y(target).toFixed(1)+'" x2="'+(W-P)+'" y2="'+Y(target).toFixed(1)+'"/><text class="axt" x="'+(W-P)+'" y="'+(Y(target)-5).toFixed(1)+'" text-anchor="end">目標 '+target+'kg</text>':'';
 var line=entries.length>1?'<polyline class="ln" points="'+pts+'"/>':'';
 return '<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="体重の推移">'+
  '<line class="ax" x1="'+P+'" y1="'+(H-P)+'" x2="'+(W-P)+'" y2="'+(H-P)+'"/>'+
  '<text class="axt" x="'+P+'" y="'+(H-P+16)+'">'+entries[0].date+'</text>'+
  '<text class="axt" x="'+(W-P)+'" y="'+(H-P+16)+'" text-anchor="end">'+entries[entries.length-1].date+'</text>'+
  '<text class="axt" x="6" y="'+(P)+'">'+maxy.toFixed(1)+'kg</text>'+
  '<text class="axt" x="6" y="'+(H-P)+'">'+miny.toFixed(1)+'kg</text>'+
  tgt+line+dots+'</svg>';
}
function trendText(entries){
 if(entries.length<2)return '記録が2件以上たまると増減の傾向を表示します。';
 var a=entries[entries.length-2].kg,b=entries[entries.length-1].kg,diff=(b-a);
 var cls=diff>0.05?'up':(diff<-0.05?'down':'flat');
 var word=diff>0.05?'増加':(diff<-0.05?'減少':'横ばい');
 var sign=diff>0?'+':'';
 return '前回比 <span class="'+cls+'">'+sign+diff.toFixed(2)+'kg（'+word+'）</span>　最新 '+b+'kg / '+entries.length+'件';
}
function render(){
 renderAuth();
 var c=cat();
 var sel=$('catsel');
 sel.innerHTML=state.cats.map(x=>'<option value="'+x.id+'"'+(x.id===state.active?' selected':'')+'>'+x.name+'</option>').join('')||'<option>（未登録）</option>';
 $('target').value=c?c.target:'';
 $('edate').value=today();
 var entries=c?c.entries:[];
 $('chart').innerHTML=chartSVG(entries,c&&parseFloat(c.target)||0);
 $('trend').innerHTML=c?trendText(entries):'まず猫を登録してください。';
 $('elist').innerHTML=entries.length?
  ('<tr><th>日付</th><th>体重</th><th></th></tr>'+entries.slice().reverse().map(e=>
   '<tr><td>'+e.date+'</td><td>'+e.kg+' kg</td><td><button class="del" onclick="delEntry(\''+e.date+'\')">削除</button></td></tr>').join('')):'';
}
"""


def build_record() -> str:
    js = RECORD_JS.replace("__SB_URL__", SUPABASE_URL).replace("__SB_ANON__", SUPABASE_ANON)
    return ("""
""" + pagehead("うちの子の管理 / ログインでクラウド保存", "体重記録") + """
<p class="lead">猫の体重を記録して、増減の傾向をグラフで確認できます。体重が増え気味なら
<a href="weight.html">体重管理ビュー</a>でカロリー密度の低いフードを探せます。<b>適正体重・増減の評価は獣医師にご相談ください</b>（当サイトは診断を行いません）。</p>
<div class="panel" id="authbar" style="margin-bottom:14px"></div>
<div class="tracker">
 <div class="panel">
  <div class="field"><label>猫を選ぶ / 追加</label>
   <select id="catsel" onchange="selCat()"></select></div>
  <div class="row2">
   <div class="field" style="flex:2"><input id="catname" placeholder="新しい猫の名前"></div>
   <div class="field"><button class="btn btn-ghost" style="width:100%;padding:9px" onclick="addCat()">＋追加</button></div>
  </div>
  <div class="field"><label>目標体重（任意・kg）</label>
   <input id="target" type="number" step="0.1" placeholder="例 4.2" onchange="setTarget()"></div>
  <hr style="border:none;border-top:1px solid var(--line);margin:14px 0">
  <div class="field"><label>体重を記録</label>
   <div class="row2">
    <input id="edate" type="date">
    <input id="ekg" type="number" step="0.01" placeholder="kg">
   </div></div>
  <button class="btn btn-primary" style="width:100%" onclick="addEntry()">この日の体重を記録</button>
  <p class="savednote">🔒 未ログインのときはこの端末内だけに保存（外部送信なし）。ログインするとクラウドに保存され、どの端末からでも見られます。</p>
 </div>
 <div class="panel">
  <div class="chartwrap" id="chart"></div>
  <p class="trend" id="trend"></p>
  <table class="elist" id="elist"></table>
 </div>
</div>
""" + '<script type="module">' + js + "</script>")


SHAPE_JS = r"""
const DATA=__DATA__;
const AX=['たんぱく質','脂肪','繊維','灰分','炭水化物'], MAX=[70,45,15,15,50], N=5;
let filt='all';
function buy(r){var q=encodeURIComponent(((r.maker||'')+' '+(r.name||'')).trim());
 return [['楽天','https://search.rakuten.co.jp/search/mall/'+q+'/'],['Amazon','https://www.amazon.co.jp/s?k='+q]]
  .map(c=>'<a href="'+c[1]+'" target="_blank" rel="noopener nofollow">'+c[0]+'</a>').join('');}
function radar(v){
 var S=168,c=S/2,R=58,P=Math.PI/180,g='',ax='',lb='',vp=[];
 [0.5,1].forEach(function(f){var p=[];for(var i=0;i<N;i++){var a=(-90+i*72)*P;p.push((c+R*f*Math.cos(a)).toFixed(1)+','+(c+R*f*Math.sin(a)).toFixed(1));}g+='<polygon points="'+p.join(' ')+'" fill="none" stroke="var(--line)"/>';});
 for(var i=0;i<N;i++){var a=(-90+i*72)*P,ex=c+R*Math.cos(a),ey=c+R*Math.sin(a);
  ax+='<line x1="'+c+'" y1="'+c+'" x2="'+ex.toFixed(1)+'" y2="'+ey.toFixed(1)+'" stroke="var(--line)"/>';
  var lx=c+(R+13)*Math.cos(a),ly=c+(R+13)*Math.sin(a);
  lb+='<text x="'+lx.toFixed(1)+'" y="'+ly.toFixed(1)+'" font-size="9" fill="#8a7866" text-anchor="middle" dominant-baseline="middle">'+AX[i]+'</text>';
  var rr=R*Math.min(v[i]/MAX[i],1);vp.push((c+rr*Math.cos(a)).toFixed(1)+','+(c+rr*Math.sin(a)).toFixed(1));}
 return '<svg viewBox="0 0 '+S+' '+S+'" class="radar" role="img"><g>'+g+ax+
  '<polygon points="'+vp.join(' ')+'" fill="var(--accent)" fill-opacity="0.22" stroke="var(--accent)" stroke-width="2"/>'+lb+'</g></svg>';}
function render(){
 var rows=DATA.filter(r=>filt==='all'||r.form===filt);
 var lab=['P','脂','繊','灰','炭'];
 document.getElementById('grid').innerHTML=rows.map(function(r){
  var nums=r.v.map((x,i)=>lab[i]+' '+x+'%').join(' ・ ');
  return '<div class="shapecard"><div class="rname">'+(r.name||'(無題)')+'<span class="mk">'+r.maker+'・'+r.form+'</span></div>'+
   radar(r.v)+'<div class="rnums">'+nums+'</div>'+
   '<div class="rsrc"><a href="'+r.url+'" target="_blank" rel="noopener">公式</a> <span class="na">'+r.fetched_at+'</span> <span class="buy">'+buy(r)+'</span></div></div>';
 }).join('');
 document.getElementById('scount').textContent=rows.length;}
window.setFilt=function(f){filt=f;document.querySelectorAll('.fbtn').forEach(b=>b.classList.toggle('on',b.dataset.f===f));render();};
render();
"""


def macro_items(products: list[dict]) -> list[dict]:
    """5マクロ(乾物量)が揃った猫商品 → レーダー用の軽量リスト。"""
    keys = ["protein_dm", "fat_dm", "fiber_dm", "ash_dm", "nfe_dm"]
    items = []
    for r in products:
        if all(r.get(k) not in (None, "") for k in keys):
            items.append({"name": r.get("product_name", ""), "maker": r.get("maker", ""),
                          "url": r.get("url", ""), "fetched_at": r.get("fetched_at", ""),
                          "form": r.get("form", ""),
                          "v": [round(float(r[k]), 1) for k in keys]})
    return items


def build_shape(products: list[dict]) -> str:
    items = macro_items(products)
    js = SHAPE_JS.replace("__DATA__", json.dumps(items, ensure_ascii=False))
    body = pagehead("成分のかたち / 乾物量換算", "栄養成分を5角形で見る") + """
<p class="lead">各フードの主要成分（たんぱく質・脂肪・繊維・灰分・炭水化物）を<b>乾物量換算</b>で5角形にしました。
ウェットとドライを公平に比べられます。<b>これは"成分の構成（かたち）"の可視化で、良し悪しの点数ではありません</b>。
炭水化物は差分（100−他4つ）で算出。5成分すべてが公式開示されている商品のみ表示しています。</p>
<div class="disclaimer">各軸の最大目盛り＝たんぱく質70 / 脂肪45 / 繊維15 / 灰分15 / 炭水化物50（％・乾物量）。
数値の解釈・適否は獣医師にご相談ください。</div>
<div class="fbar">表示 <b id="scount">0</b> 商品：
 <button class="fbtn on" data-f="all" onclick="setFilt('all')">すべて</button>
 <button class="fbtn" data-f="ドライ" onclick="setFilt('ドライ')">ドライ</button>
 <button class="fbtn" data-f="ウェット" onclick="setFilt('ウェット')">ウェット</button>
</div>
<div id="grid" class="shapegrid"></div>
""" + '<script>' + js + '</script>'
    return body


CALC_JS = r"""
const DB=__DB__;
const AX=['たんぱく質','脂肪','繊維','灰分','炭水化物'], MAX=[70,45,15,15,50], N=5;
function radar(v,big){
 var S=big?200:150,c=S/2,R=big?72:52,P=Math.PI/180,g='',ax='',lb='',vp=[];
 [0.5,1].forEach(function(f){var p=[];for(var i=0;i<N;i++){var a=(-90+i*72)*P;p.push((c+R*f*Math.cos(a)).toFixed(1)+','+(c+R*f*Math.sin(a)).toFixed(1));}g+='<polygon points="'+p.join(' ')+'" fill="none" stroke="var(--line)"/>';});
 for(var i=0;i<N;i++){var a=(-90+i*72)*P,ex=c+R*Math.cos(a),ey=c+R*Math.sin(a);
  ax+='<line x1="'+c+'" y1="'+c+'" x2="'+ex.toFixed(1)+'" y2="'+ey.toFixed(1)+'" stroke="var(--line)"/>';
  var lx=c+(R+13)*Math.cos(a),ly=c+(R+13)*Math.sin(a);
  lb+='<text x="'+lx.toFixed(1)+'" y="'+ly.toFixed(1)+'" font-size="'+(big?10:9)+'" fill="#8a7866" text-anchor="middle" dominant-baseline="middle">'+AX[i]+'</text>';
  var rr=R*Math.min(v[i]/MAX[i],1);vp.push((c+rr*Math.cos(a)).toFixed(1)+','+(c+rr*Math.sin(a)).toFixed(1));}
 return '<svg viewBox="0 0 '+S+' '+S+'" class="radar" style="width:'+S+'px;height:'+S+'px" role="img"><g>'+g+ax+
  '<polygon points="'+vp.join(' ')+'" fill="var(--accent)" fill-opacity="0.22" stroke="var(--accent)" stroke-width="2"/>'+lb+'</g></svg>';}
function pctBelow(idx,x){var n=DB.filter(d=>d.v[idx]<=x).length;return Math.round(100*n/DB.length);}
function compute(){
 var g=id=>parseFloat(document.getElementById(id).value);
 var m=g('m'),asf=[g('p'),g('f'),g('fb'),g('a')];
 if(isNaN(m)||m>=100||asf.some(isNaN)){document.getElementById('out').innerHTML='<div class="disclaimer">たんぱく質・脂肪・繊維・灰分・水分（%）を入力してください。</div>';return;}
 var dm=asf.map(x=>Math.round(x/(100-m)*1000)/10);
 var nfe=Math.round((100-dm.reduce((s,x)=>s+x,0))*10)/10; if(nfe<0)nfe=0;
 var v=[dm[0],dm[1],dm[2],dm[3],nfe];
 var rowsT=v.map((x,i)=>'<tr><td>'+AX[i]+'</td><td class="num"><b>'+x+'%</b></td><td class="mk">掲載商品の中で下から '+pctBelow(i,x)+'%</td></tr>').join('');
 var kn=DB.map(d=>({d:d,dist:Math.sqrt(v.reduce((s,x,i)=>s+Math.pow((x-d.v[i])/MAX[i],2),0))})).sort((a,b)=>a.dist-b.dist).slice(0,6);
 var sim=kn.map(function(o){var r=o.d;var nums=r.v.map((x,i)=>['P','脂','繊','灰','炭'][i]+' '+x+'%').join(' ・ ');
  return '<div class="shapecard"><div class="rname">'+(r.name||'(無題)')+'<span class="mk">'+r.maker+'・'+r.form+'</span></div>'+
   radar(r.v)+'<div class="rnums">'+nums+'</div><div class="rsrc"><a href="'+r.url+'" target="_blank" rel="noopener">公式</a></div></div>';}).join('');
 document.getElementById('out').innerHTML=
  '<div class="split" style="gap:24px"><div style="flex:0 0 auto;text-align:center">'+radar(v,true)+'<div class="mk">乾物量換算した成分のかたち</div></div>'+
  '<div style="flex:1"><table class="elist"><tr><th>成分</th><th>乾物量</th><th>位置（非評価）</th></tr>'+rowsT+'</table>'+
  '<p class="mk" style="margin-top:8px">※水分'+m+'%を除いた基準。炭水化物＝100−（たんぱく+脂肪+繊維+灰分）。「位置」は良し悪しでなく分布上の場所です。</p></div></div>'+
  '<h2>成分が近い掲載商品</h2><p class="lead">入力した数値に<b>成分構成が近い</b>商品です（おすすめ順ではなく、近さ順）。</p><div class="shapegrid">'+sim+'</div>';
 document.getElementById('out').scrollIntoView({behavior:'smooth',block:'nearest'});}
window.compute=compute;
window.demo=function(){var s={p:'30',f:'15',fb:'3',a:'7',m:'10'};for(var k in s)document.getElementById(k).value=s[k];compute();};
"""


def build_calc(products: list[dict]) -> str:
    db = macro_items(products)
    js = CALC_JS.replace("__DB__", json.dumps(db, ensure_ascii=False))
    body = pagehead("乾物量ツール / どの袋でも", "お店の袋の数値を入れてみる") + """
<p class="lead">いま手元にある（お店で見ている）フードの<b>保証分析値</b>を入れると、水分を除いた
<b>本当の成分のかたち</b>と、掲載商品の中での位置、そして<b>成分が近い商品</b>が分かります。
DBに無いフードでも使えます。<b>これは成分の可視化で、良し悪しの評価ではありません</b>（非診断）。</p>
<div class="panel">
 <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px">
  <div class="field"><label>たんぱく質 %</label><input id="p" type="number" step="0.1" placeholder="例 30"></div>
  <div class="field"><label>脂肪 %</label><input id="f" type="number" step="0.1" placeholder="例 15"></div>
  <div class="field"><label>繊維 %</label><input id="fb" type="number" step="0.1" placeholder="例 3"></div>
  <div class="field"><label>灰分 %</label><input id="a" type="number" step="0.1" placeholder="例 7"></div>
  <div class="field"><label>水分 %</label><input id="m" type="number" step="0.1" placeholder="例 10"></div>
 </div>
 <div class="btn-row">
  <button class="btn btn-primary" onclick="compute()">成分のかたちを見る</button>
  <button class="btn btn-ghost" onclick="demo()">例を入れてみる</button>
 </div>
 <p class="mk">袋の「保証分析値（成分値）」に書いてある％をそのまま入力してください（as-fed）。</p>
</div>
<div id="out" style="margin-top:18px"></div>
""" + '<script>' + js + '</script>'
    return body


def _floats(products, key):
    out = []
    for r in products:
        v = r.get(key, "")
        if v not in (None, ""):
            try:
                out.append(float(v))
            except ValueError:
                pass
    return out


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return round(xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2, 1)


def _pctile(xs, q):
    """外れ値に強い分位点（最頻レンジの提示用）。"""
    xs = sorted(xs)
    if not xs:
        return None
    i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return round(xs[i], 1)


def _by_form(products, key, form):
    return [float(r[key]) for r in products
            if r.get("form") == form and r.get(key) not in (None, "")]


def cat_stats(products) -> dict:
    phos = _floats(products, "phosphorus_dm")
    cal = _floats(products, "calorie_density_100g")
    mg = _floats(products, "magnesium_pct")
    ash = _floats(products, "ash_dm")
    prot = _floats(products, "protein_dm")
    return {
        "n": len(products),
        "p_n": len(phos), "p_med": _median(phos),
        "p_min": round(min(phos), 2) if phos else None, "p_max": round(max(phos), 2) if phos else None,
        "prot_wet_med": _median(_by_form(products, "protein_dm", "ウェット")),
        "prot_dry_med": _median(_by_form(products, "protein_dm", "ドライ")),
        "prot_med": _median(prot),
        "prot_p10": _pctile(prot, 0.1), "prot_p90": _pctile(prot, 0.9),
        "cal_med": _median(cal), "cal_min": round(min(cal)) if cal else None,
        "cal_max": round(max(cal)) if cal else None,
        "gf_n": sum(1 for r in products if r.get("grain_free") == "yes"),
        "mg_n": len(mg), "mg_med": _median(mg),
        "ash_med": _median(ash),
        "moist_wet_med": _median(_by_form(products, "moisture_pct", "ウェット")),
        "moist_dry_med": _median(_by_form(products, "moisture_pct", "ドライ")),
        "ther_n": sum(1 for r in products if r.get("is_therapeutic") == "True"),
    }


_ARTICLE_RELATED = """
<h2>このサイトで試す</h2>
<div class="cards">
 <div class="card"><b>成分ツール</b><p class="lead">手元の袋の数値を入れて乾物量で見る・近い商品を探す。</p><a class="btn btn-ghost" href="calc.html">成分ツール →</a></div>
 <div class="card"><b>目的から選ぶ</b><p class="lead">体重・腎臓・尿路などの観点から、条件に合う商品を実値で。</p><a class="btn btn-ghost" href="find.html">目的から選ぶ →</a></div>
 <div class="card"><b>体重記録</b><p class="lead">うちの子の体重を記録して増減の傾向をグラフで。</p><a class="btn btn-ghost" href="record.html">体重記録 →</a></div>
</div>
"""
_ARTICLE_DISCLAIMER = """
<div class="disclaimer" style="margin-top:18px">本記事は当サイトの掲載データと公的な表示ルールをもとに編集部が整理したものです。
<b>獣医師による監修記事ではなく、診断・治療の助言でもありません</b>。数値の解釈や与え方は症例ごとに異なります。
気になる症状や食事の変更は、必ずかかりつけの獣医師にご相談ください。</div>
"""


def article(slug, title, date, desc, body_html, sources_html) -> str:
    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "Article", "headline": title,
        "datePublished": date, "dateModified": today_stamp(), "description": desc,
        "author": {"@type": "Organization", "name": SITE_NAME},
        "publisher": {"@type": "Organization", "name": SITE_NAME},
        "mainEntityOfPage": f"{BASE_URL}/{slug}.html",
    }, ensure_ascii=False)
    return (pagehead("猫の健康を、ファクトで", title)
            + f'<p class="mk">{date}・{SITE_NAME} 編集部（獣医監修ではありません／出典つき・非診断）</p>'
            + body_html
            + "<h2>出典</h2>" + sources_html
            + _ARTICLE_RELATED + _ARTICLE_DISCLAIMER
            + f'<script type="application/ld+json">{jsonld}</script>')


def blog_pages(products) -> dict:
    s = cat_stats(products)
    SRC_LABEL = ('<ul class="credits"><li>各メーカー公式サイトの保証分析値（本サイト掲載分・取得日つき）</li>'
                 '<li>ペットフード公正取引協議会／愛玩動物用飼料の表示ルール</li>'
                 f'<li>本記事の集計＝当サイト掲載 {s["n"]} 商品（猫・公式開示分）より</li></ul>')
    arts = []  # (slug, title, date, desc, body)

    # 1) リン（データ駆動）
    arts.append((
        "blog-phosphorus", "キャットフードの『リン』、実際どれくらい？掲載データで見る", "2026-06-23",
        "腎臓の食事管理で注目されるリン。公式に開示している商品の実値を、乾物量換算で集計しました。良し悪しは判断しません。",
        f"""
<p class="lead">腎臓の食事管理で獣医師がよく見る数値が「リン」です。ただし<b>保証分析値にリンを公式開示している商品は多くありません</b>。
当サイト掲載の猫用 {s['n']} 商品のうち、<b>リンを開示しているのは {s['p_n']} 商品</b>でした。</p>
<h2>開示されている商品のリン（乾物量換算）</h2>
<p class="lead">開示分を乾物量換算で集計すると、中央値は <b>{s['p_med']}%</b>、範囲は {s['p_min']}〜{s['p_max']}% でした。
ウェットとドライを公平に比べるため水分を除いた基準にしています。<b>数値が低い＝良い、とは限りません</b>（現代獣医学でも議論があり、当サイトは立場を取りません）。</p>
<p class="lead">「記載なし」は「含まれない」ではなく「メーカーが公開していない」という意味です。
リンを開示している商品だけを並べた <a href="kidney.html">腎臓相談シート</a> を、印刷して獣医師にお見せください。</p>
"""))

    # 2) ウェット vs ドライ たんぱく質（データ駆動）
    arts.append((
        "blog-wet-dry-protein", "ウェットとドライ、たんぱく質はどっちが高い？乾物量で比べる", "2026-06-23",
        "生の数字だとウェットは低く見えますが、水分を除く（乾物量換算）と印象が変わります。掲載データで比較しました。",
        f"""
<p class="lead">ウェット（水分80%前後）とドライ（水分10%前後）を、袋の表示そのままで比べると<b>ウェットのたんぱく質が低く見えます</b>。
でもそれは水分が多いだけ。水分を除いた<b>乾物量換算</b>で比べるのが公平です。</p>
<h2>掲載データでの中央値（乾物量換算）</h2>
<p class="lead">当サイト掲載の猫用フードで、たんぱく質（乾物量）の中央値は——
ウェット <b>{s['prot_wet_med']}%</b> / ドライ <b>{s['prot_dry_med']}%</b>。
生表示の印象とは別物になることが分かります。</p>
<p class="lead">手元のフードでも試せます：袋の数値を <a href="calc.html">成分ツール</a> に入れると、乾物量換算した成分の形と、成分が近い商品が見られます。
各商品の成分の形は <a href="shape.html">成分のかたち</a> で一覧できます。</p>
"""))

    # 3) グレインフリー（データ＋方法）
    arts.append((
        "blog-grain-free", "『グレインフリー』のキャットフード、原材料での見分け方", "2026-06-23",
        "グレインフリーは原材料表示で見分けます。何を探せばいいか、掲載データの傾向とあわせて整理しました。",
        f"""
<p class="lead">「グレインフリー」は栄養成分でなく<b>原材料</b>で決まります。原材料表示の主要部に
米・玄米・小麦・大麦・とうもろこし（コーン）・雑穀などの<b>穀物の表記が無いか</b>を見ます。</p>
<h2>掲載データの傾向</h2>
<p class="lead">当サイトでは原材料表示の主要部に穀物表記が無い商品を「グレインフリー（参考）」として扱っています。
掲載 {s['n']} 商品のうち <b>{s['gf_n']} 商品</b>が該当しました（あくまで表示に基づく参考判定です）。</p>
<p class="lead">グレインフリー＝健康に良い、と当サイトは評価しません。穀物にも役割があり、合う合わないは個体差です。
「穀物を避けたい」を選ぶと該当商品を実値つきで見られます： <a href="find.html">目的から選ぶ</a>。</p>
"""))

    # 4) カロリー密度 × 体重（日次健康への回遊）
    arts.append((
        "blog-calorie-density", "体重が気になる猫に『カロリー密度』をどう使う？", "2026-06-23",
        "体重管理はカロリー密度（kcal/100g）が手がかり。個包装おやつの落とし穴と、記録のすすめもあわせて。",
        f"""
<p class="lead">体重管理の手がかりのひとつが<b>カロリー密度（kcal/100g）</b>です。同じ量でもカロリー密度が低いほど、
総カロリーを抑えやすくなります。当サイト掲載商品では、カロリー密度の中央値は <b>{s['cal_med']} kcal/100g</b>（範囲 {s['cal_min']}〜{s['cal_max']}）でした。</p>
<h2>注意：個包装おやつの「1個◯kcal」</h2>
<p class="lead">ウェットやおやつでよくある「1個あたり◯kcal」は、kcal/100g とは別物です。<b>密度の比較には使えない</b>ので、
当サイトでは「個包装のため密度比較不可」と明示しています。</p>
<p class="lead">カロリー密度の低い順は <a href="weight.html">体重管理ビュー</a> で並べ替えられます。
そして大事なのは<b>続けて測ること</b>。<a href="record.html">体重記録</a>で毎週の増減をグラフにすると、フード選びの効果も見えてきます。
適正体重・給与量は獣医師にご相談ください。</p>
"""))

    # 5) 尿路ケアとマグネシウム（データ駆動・健康系=獣医併記）
    arts.append((
        "blog-urinary-magnesium", "猫の尿路ケアと『マグネシウム』、表示で見るには", "2026-06-23",
        "ストルバイト尿石で見られるマグネシウム。公式開示している商品の値と、見方の注意を整理しました。診断はしません。",
        f"""
<p class="lead">猫の下部尿路（ストルバイト尿石など）でしばしば話題になるのがマグネシウムです。ただし
<b>保証分析値にマグネシウムを開示している商品は限られます</b>。当サイト掲載 {s['n']} 商品のうち
公式開示は <b>{s['mg_n']} 商品</b>、その中央値は約 <b>{s['mg_med']}%</b>（公式表示値）でした。</p>
<h2>数値の見方の注意</h2>
<p class="lead">尿路の健康は、マグネシウム単独でなく水分摂取・尿pH・体質など複数の要因が関わります。
<b>「低い＝安心」と単純化はできません</b>。当サイトは良し悪しを判断しません。気になる症状（頻尿・血尿・トイレでうずくまる等）は
<b>緊急のこともあるため、すぐに動物病院へ</b>。</p>
<p class="lead">「尿路が気になる」を選ぶと、マグネシウムを開示している商品を低い順で（開示分のみ）見られます：
<a href="find.html">目的から選ぶ</a>。水分の摂らせ方は下の記事も参考に。</p>
"""))

    # 6) 水分（データ駆動）
    arts.append((
        "blog-water-intake", "猫に水分をどう摂らせる？ ウェットとドライの水分量", "2026-06-23",
        "猫はもともと水をあまり飲まない動物。フードの水分量はウェットとドライで大きく違います。掲載データで比較。",
        f"""
<p class="lead">猫は砂漠出身の名残で、もともと積極的に水を飲まない動物といわれます。だからこそ
<b>食事からの水分</b>も一つの手がかりになります。掲載データでの水分の中央値は——
ウェット <b>{s['moist_wet_med']}%</b> / ドライ <b>{s['moist_dry_med']}%</b>。差は歴然です。</p>
<h2>ウェットが万能というわけではない</h2>
<p class="lead">水分が多いウェットは水分補給に向く一方、同じ重さあたりの栄養・カロリーは薄くなります（だから
<a href="blog-wet-dry-protein.html">乾物量換算</a>で比べます）。コスト・歯みがき・嗜好性などトレードオフもあり、
当サイトは「どちらが良い」とは言いません。</p>
<p class="lead">ウェット中心で探したいときは「水分を摂らせたい」を： <a href="find.html">目的から選ぶ</a>。
飲水量や体調の変化が気になるときは獣医師にご相談ください。</p>
"""))

    # 7) 高たんぱく（データ駆動）
    arts.append((
        "blog-high-protein", "猫は高たんぱくが基本？ たんぱく質の見方", "2026-06-23",
        "猫は完全肉食動物。たんぱく質は重要ですが、数値の高さだけで決まりません。掲載データの分布で見ます。",
        f"""
<p class="lead">猫は完全肉食動物（obligate carnivore）で、犬より多くのたんぱく質を必要とするといわれます。
掲載データでたんぱく質（乾物量）の中央値は <b>{s['prot_med']}%</b>。多くの商品は <b>{s['prot_p10']}〜{s['prot_p90']}%</b> に収まり、
フリーズドライのトリーツなど一部はさらに高い値になります。</p>
<h2>「高いほど良い」ではない</h2>
<p class="lead">高たんぱくは筋肉維持などで重視される一方、<b>腎臓に懸念がある子では適さないこともあります</b>。
ライフステージや健康状態で適量は変わるため、当サイトは数値の良し悪しを判断しません。</p>
<p class="lead">高たんぱく順に見たいときは <a href="find.html">目的から選ぶ</a>、
各商品の成分バランスは <a href="shape.html">成分のかたち</a> の5角形で一目で比べられます。</p>
"""))

    # 8) 療法食と総合栄養食・一般食（YMYL・強い非診断）
    arts.append((
        "blog-therapeutic-vs-complete", "『療法食』『総合栄養食』『一般食』はどう違う？", "2026-06-23",
        "パッケージの区分表示の意味と、療法食の扱い方を整理。療法食は獣医師の指示が前提です。",
        f"""
<p class="lead">キャットフードの区分表示には主に次があります。</p>
<ul class="lead">
<li><b>総合栄養食</b>：それと水だけで必要な栄養がとれる基準を満たした主食用。</li>
<li><b>一般食・副食・おやつ</b>：主食ではなく、トッピングや嗜好目的。これだけで完結しない。</li>
<li><b>療法食</b>：特定の健康管理のために栄養を調整した食事。<b>獣医師の指導のもとで使うもの</b>。</li>
</ul>
<h2>療法食は自己判断で切り替えない</h2>
<p class="lead">療法食は「効きそうだから」と自己判断で与えたり止めたりすると、かえって健康を損なう恐れがあります。
<b>必ずかかりつけの獣医師の指示に従ってください</b>。当サイトは療法食を「この病気にはこれ」とは案内しません。
掲載データで療法食として表示が確認できた商品は {s['ther_n']} 件ありましたが、選択・中止はあくまで獣医師の判断が前提です。</p>
<p class="lead">獣医師に相談する際は、いま与えているフードの成分を整理しておくとスムーズです。
<a href="calc.html">成分ツール</a>で袋の数値を乾物量換算しておくと話が早くなります。</p>
"""))

    # 9) 保証分析値の読み方（エバーグリーン・calcへ）
    arts.append((
        "blog-how-to-read-labels", "保証分析値の読み方 — 袋の数字を正しく比べる", "2026-06-23",
        "粗たんぱく質・粗脂肪・粗繊維・粗灰分・水分。袋の数字の意味と、公平に比べるコツ（乾物量換算）。",
        f"""
<p class="lead">袋の「保証分析値（成分値）」には、粗たんぱく質・粗脂肪・粗繊維・粗灰分・水分などが並びます。
「粗（そ）」は分析方法上の呼び方で、品質が粗いという意味ではありません。「◯%以上／以下」は保証の範囲を示します。</p>
<h2>そのまま比べると不公平になる</h2>
<p class="lead">水分量が違うフード同士を生の数字で比べると、水分の多いウェットが軒並み低く見えます。
そこで<b>水分を除いた「乾物量（ドライマター）」</b>に換算してから比べるのが公平です：</p>
<p class="lead"><code>乾物量の値(%) = 表示値(%) ÷ (100 − 水分%) × 100</code></p>
<p class="lead">炭水化物は表示されないことが多いですが、<code>100 −（たんぱく質+脂肪+繊維+灰分+水分）</code>で概算できます。
これらを自動でやるのが <a href="calc.html">成分ツール</a> です。掲載 {s['n']} 商品はすべてこの方法で揃えています。</p>
"""))

    pages = {}
    # index
    cards = "".join(
        f'<div class="card"><span class="mk">{d}</span><h2 style="margin-top:2px">{t}</h2>'
        f'<p class="lead">{desc}</p><a class="btn btn-ghost" href="{slug}.html">読む →</a></div>'
        for (slug, t, d, desc, _b) in arts)
    idx_body = (pagehead("読みもの / データで見る猫の健康", "猫の健康を、ファクトで")
                + '<p class="lead">口コミや推測ではなく、当サイトの掲載データ（出典つき・乾物量換算）と公的な表示ルールをもとに整理した読みものです。'
                + '評価・順位は付けません。診断もしません。</p>'
                + f'<div class="cards">{cards}</div>')
    pages["blog.html"] = ("blog", "読みもの", idx_body,
                          "当サイトの掲載データ（出典つき）と公的ルールをもとに、猫の健康と栄養を整理した読みもの。非診断・評価なし。")
    for (slug, t, d, desc, body) in arts:
        pages[f"{slug}.html"] = ("blog", t, article(slug, t, d, desc, body, SRC_LABEL), desc)
    return pages


def build_about() -> str:
    return (pagehead("方法と原則", "この調べ方") + _ABOUT_BODY).replace("__CREDITS__", _credits_html())


_ABOUT_BODY = """
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
<h2>データを公開しています</h2>
<p class="lead">掲載キャットフードの成分データ（乾物量換算・出典付き）を、そのまま誰でも見られる形で公開します。
ファクトを名乗る以上、中身を隠しません。<a href="data/cat_products.json" download>📥 全データ（JSON）をダウンロード</a></p>
<h2>写真クレジット</h2>
<p class="lead">サイト内の写真は Wikimedia Commons のパブリックドメイン／CC0／CC BY 素材です（出典・作者・ライセンスを明記）。</p>
__CREDITS__
"""


def _credits_html() -> str:
    p = SITE / "img" / "credits.json"
    if not p.exists():
        return ""
    items = json.loads(p.read_text(encoding="utf-8"))
    lis = "".join(
        f'<li>{c["file"]}：「{c["title"]}」 / {c["license"]}'
        + (f' / {c["author"]}' if c.get("author") else "")
        + (f' / <a href="{c["source"]}" target="_blank" rel="noopener">出典</a>' if c.get("source") else "")
        + "</li>"
        for c in items)
    return f'<ul class="credits">{lis}</ul>'


def main() -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    css = CSS.replace("PAWMASK", _PAW_MASK).replace("PAWBG", _PAW_BG)
    (SITE / "style.css").write_text(css, encoding="utf-8")
    products = load_products()
    cov = coverage()
    pages = {
        "index.html": ("index", "ホーム", build_index(cov),
                       "キャットフードを広告やランキングではなく公式の保証成分・出典・乾物量換算のファクトで比較。目的から透明な条件で選べる。"),
        "find.html": ("find", "目的から選ぶ", build_find(products),
                      "「体重管理・高たんぱく・水分・穀物を避けたい・腎臓・尿路」など目的から、見る指標と条件を明示して合う商品を実値つきで表示。"),
        "shape.html": ("shape", "成分のかたち", build_shape(products),
                       "各キャットフードの主要成分(たんぱく質・脂肪・繊維・灰分・炭水化物)を乾物量換算の5角形レーダーで一覧。点数ではなく成分の構成。"),
        "calc.html": ("calc", "成分ツール", build_calc(products),
                      "手元のフードの保証分析値を入れると乾物量換算の成分5角形・掲載商品内での位置・成分が近い商品が分かる。DBに無いフードでも使える。"),
        "record.html": ("record", "体重記録", build_record(),
                        "猫の体重を記録して増減の傾向をグラフで確認。記録は端末内に保存。体重管理フードへ連動。非診断。"),
        "weight.html": ("weight", "体重管理ビュー", build_weight(products),
                        "キャットフードをカロリー密度(kcal/100g)で並べ替えられる出典付き一覧。おすすめ・順位は出しません。"),
        "kidney.html": ("kidney", "腎臓相談シート", build_kidney(products),
                        "リンを公式開示しているキャットフードを乾物量換算で比較。印刷して獣医師にご相談ください。非診断。"),
        "coverage.html": ("coverage", "網羅性", build_coverage(cov),
                          "対象母集団とカバー率・未取得・対象外を正直に開示。宣言した範囲への網羅性。"),
        "about.html": ("about", "この調べ方", build_about(),
                       "4状態ラベル・乾物量換算・出典必須・アフィリエイト遮断・非診断。データの作り方を公開。"),
    }
    pages.update(blog_pages(products))  # データ駆動の読みもの（SEO・回遊）
    for fname, (active, title, body, desc) in pages.items():
        (SITE / fname).write_text(
            page(active, title, body, desc, fname, wrap=(active != "index")),
            encoding="utf-8")

    # 全データの公開（ファクトDBとしての透明性）。誰でも監査・再利用できる。
    (SITE / "data").mkdir(parents=True, exist_ok=True)
    (SITE / "data" / "cat_products.json").write_text(
        json.dumps({"updated": today_stamp(), "count": len(products),
                    "note": "ねこごはんファクト 掲載キャットフードの成分データ（乾物量換算含む・出典付き）。評価・順位は含みません。",
                    "products": products}, ensure_ascii=False, indent=1),
        encoding="utf-8")

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
