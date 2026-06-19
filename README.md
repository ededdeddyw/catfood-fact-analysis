# キャットフード ファクトベース分析サービス

キャットフードを、広告やランキングではなく **成分・原材料・栄養基準・価格・リスク情報のファクト**から分析する。
口コミ・推測スコアは出さない。判断材料と「次の行動」まで整理する。

> このプロジェクトは 2026-06-20 に `pet-hospital-launch`（pet-er.jp／病院ファクトDB）から**独立**させた別事業です。
> 病院プロジェクトで確立した思想（**4状態ラベル・出典必須・非診断・段階主義・LLMコストゼロ抽出**）だけを横展開しています。

---

## フォルダ構成

```
catfood-fact-analysis/
  docs/        構想ドキュメント（README=索引 / 01 腎臓相談シート / 02 データ検証 / 03 網羅性・アフィリ遮断）
  scripts/     クローラ・抽出エンジン（LLM不使用・requests+bs4+正規表現）
  data/        出力CSV（母集団・製品ファクト）
  logs/        取得履歴・失敗ログ
```

詳しい企画は **[docs/README.md](docs/README.md)** から。

---

## セットアップ

```powershell
cd C:\Users\今枝龍之介\Pets\catfood-fact-analysis
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

（暫定で病院プロジェクトの venv を流用する場合は
`..\pet-hospital-launch\.venv\Scripts\python.exe` を絶対パスで呼んでもよい）

## 実行

```powershell
# ① 母集団（フード版「行政名簿」）= ペットフード公正取引協議会 会員一覧
.\.venv\Scripts\python.exe scripts\crawl_pffta_members.py
#   → data/pffta_members.csv（正会員=メーカー / 準会員=検査機関）

# ② 抽出エンジンの自己テスト（正規表現の動作確認）
.\.venv\Scripts\python.exe scripts\catfood_nutrition_patterns.py

# ③ 製品ファクト抽出（保証分析値・カロリー・リン・原材料）
#    site モード: メーカーサイトを浅く巡回して成分ページを自動発見
.\.venv\Scripts\python.exe scripts\extract_product_facts.py --site https://example.co.jp/ --maker 例社 --max-pages 30
#    seed モード: 既知の製品URL一覧（maker,product_name,url）から抽出
.\.venv\Scripts\python.exe scripts\extract_product_facts.py --seed data\seed_product_urls.csv
```

---

## 設計の確定事項（壁打ち①②③）

| 論点 | 結論 | 参照 |
|------|------|------|
| ① 悩み別適合度 | スコア化しない。客観指標＋4状態に分解、出力は**獣医相談シート** | docs/01 |
| ② 網羅性 | 全網羅でなく**「宣言した母集団へのカバー率＋未掲載レポート」** | docs/03 |
| ③ アフィリ遮断 | **ランキングを作らない**・表示順は手数料無関係・コードで分離 | docs/03 |

製品人格：**評価せず・順位を付けず・母集団を宣言し、出典付きファクトと相談シートで判断を支援する。**

---

## 現状と次の一手（引き継ぎ — 2026-06-20）

**できたこと**
- ✅ 母集団クロール成功：公正取引協議会 **83社**（正会員79=メーカー／準会員4=検査機関）→ `data/pffta_members.csv`
  - ②の母集団＝**正会員79社**（準会員は分析機関なので対象外）
- ✅ 保証分析値の抽出エンジン（`catfood_nutrition_patterns.py`）：自己テストで9項目すべて正抽出
- ✅ 巡回型の製品ファクト抽出（`extract_product_facts.py`）：礼儀正しい同一ドメインBFS・成分ページ自動発見

**重要な実測所見（＝02オーディットの「現実を見る」段階）**
- ⚠️ **大手メーカー（アイシア・いなば・日本ペットフード）の製品ページは静的HTMLに保証分析値が無い**
  - アイシアは商品詳細がJS描画。いなば/日本ペットフードは詳細ページにも成分テキストが出ない
  - → **requests だけのトークンゼロ静的クロールでは大手の栄養データは取れない**ことが判明

**次に決めること（製品の栄養データをどう取るか）**
1. **Playwright（ヘッドレスブラウザ）** — JS描画ページを取得。LLM不使用＝トークンゼロ。重いが確実（病院プロジェクトも採用実績あり）
2. **楽天市場 商品検索API** — 商品説明が静的HTMLで成分・原材料を含むことが多い。無料appIDで合法・トークンゼロ。②の「実需カバレッジ」にも有効
3. **静的HTMLで成分を出す中小・プレミアムブランドの手動シードURL** — 02オーディットが想定した手作業50件
4. 上記の組み合わせ

→ おすすめは **2（楽天API）で実需カバレッジを取りつつ、1（Playwright）で公式の保証分析値を補完**。
