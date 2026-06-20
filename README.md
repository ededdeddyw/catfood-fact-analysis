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

# ③ 母集団79社の公式サイトURLを解決（Bing＋会社名一致検証・トークンゼロ）
.\.venv\Scripts\python.exe scripts\resolve_maker_sites.py        # → data/maker_sites.csv（再開可）
.\.venv\Scripts\python.exe scripts\verify_proposed_sites.py      # 人手候補(data/maker_url_proposals.csv)を取得検証
.\.venv\Scripts\python.exe scripts\reconcile_maker_sites.py      # 検証結果で確定/降格を反映

# ④ 開示率オーディットを自動実行（確定URL群を巡回→項目別開示率＋リン撤退ライン判定）
.\.venv\Scripts\python.exe scripts\run_disclosure_audit.py --fresh --max-pages 20
#   → data/disclosure_matrix.csv（メーカー別）/ data/product_facts_raw.csv（生データ）

# ⑤ JS描画ページの抽出（大手向け・Playwright・トークンゼロ）
.\.venv\Scripts\python.exe scripts\extract_product_facts_pw.py --site https://www.example.co.jp/ --maker 例社

# 単発の製品ファクト抽出（site/seed モード）
.\.venv\Scripts\python.exe scripts\extract_product_facts.py --site https://example.co.jp/ --maker 例社 --max-pages 30
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

## 現状と次の一手（引き継ぎ — 2026-06-20 更新）

> 詳細な実測結果は **[docs/04_acquisition_audit_results.md](docs/04_acquisition_audit_results.md)**。

**できたこと**
- ✅ 母集団：公正取引協議会 正会員79社 → `data/pffta_members.csv`
- ✅ 抽出エンジン（`catfood_nutrition_patterns.py`）：自己テスト9項目正抽出
- ✅ **公式URL解決パイプライン**（`resolve_maker_sites.py` ほか）：Bing＋会社名一致検証で
  **79社中29社を出典付きで確定**（主要大手を網羅）。残50社は要確認として `data/maker_sites.csv` に明記
- ✅ **開示率オーディットを自動実行**（`run_disclosure_audit.py`）：確定29社を巡回し実測

**実測した開示率（02オーディットの自動版・取得12ページ）**
- 原材料100% / 水分83% / たんぱく質・脂肪・カロリー等75% / **リン 8%（1/12）**
- → リン < 20% ＝ **腎臓シートは見送り。体重管理（カロリー密度）を第1ローンチの看板に**（02の撤退ライン）
- ⚠️ ただし **29社中23社（主要大手すべて）は静的HTMLで成分0件**。上の母数は中小tail偏重なので**暫定**
- ⚠️ Playwrightでもアイシアはトップ巡回では0件（製品詳細がサイト内検索アプリの奥）。**大手はサイト個別対応が要る**

**次の一手（おすすめ順 / 詳細は docs/04 §4）**
1. **体重管理を第1ローンチに確定**（リン依存の腎臓は後回し）
2. **大手はサイト個別のPlaywrightアダプタ**（アイシア・いなば・日本ペットフード／`extract_product_facts_pw.py` を拡張）
3. **要確認50社のURL確定**（人手 or 楽天API実需上位 → `verify_proposed_sites.py` で取得検証）
4. **大手＋療法食が入った母数でリンを再評価**（療法食はリン開示が高いはず → 02判定を引き直す）
