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

**実測した開示率（2026-06-23 誤抽出是正後・521成分ページ／23社）**
- 原材料98% / 脂肪・繊維・水分97% / たんぱく質・灰分95% / **カロリー94%** / **リン 38%**
- 精緻化（保証成分ブロック限定・全角半角・カロリー単位）＋**リン誤抽出是正**（「コリン」の"リン"誤マッチ・リン酸除外・妥当範囲チェック）で値が締まった
- **リン開示はメーカー方針で二極化**：日本PF 93% / RC 56% / アイシア 53% / いなば 4%
- → **縮小版＝リン開示メーカーに絞れば腎臓シート成立**（母体268ページ）。体重管理はカロリー94%・原材料98%で盤石
- ⚠️ 6/20の「リン8%→見送り」はtail偏重の誤り。経緯と詳細は [docs/04](docs/04_acquisition_audit_results.md) 冒頭の追記

**公開フロント（実プロダクトUI・実データから静的生成）**
- [site/index.html](site/index.html)：多ページ公開サイト（`scripts/build_site.py`）。
  ホーム＋**体重管理ビュー**＋**腎臓相談シート**（乾物量換算・印刷/PDF・リン開示フィルタ）＋
  **網羅性ページ**（母集団79社／確定・取得・未取得・対象外を正直に開示＝②③）＋**この調べ方**（4状態・乾物量換算・アフィリ遮断）
- 評価せず・順位を付けず・出典付き・非診断。設計は [docs/06](docs/06_mvp_design.md)

**内部DBビュー（点検用・公開UIとは分離）**
- [prototype/consult/index.html](prototype/consult/index.html)：猫465商品の生比較テーブル（`scripts/build_consult_sheet.py`）

**次の一手**
1. ~~データ0の32社＋ヒルズをPlaywright対応~~ → **検証の結果、汎用Playwright BFSでは不可と判明**（ヒルズ＝ドッグ一覧へ迷走、カラーズ＝SPAで詳細に到達せず）。JS-SPA社は**1社ずつのper-siteアダプタ or EC(楽天)フォールバック**が必要で費用対効果が低いため**保留**。リン開示の主力大手は取得済みなので事業判断には不要
2. ✅ **MVP肉付け 済**：購入リンク（全商品平等・複数チャネル・手数料を表示順に使わない）、印刷/PDF、カバレッジ表示
3. **MVP本実装**：公開フロント（DBビューと分離）。母集団カバレッジの自動差し込み、ライフステージ機能
4. 将来：ドッグフード横展開・オーダーメイド接続（[docs/05](docs/05_future_directions.md)）

> カバレッジの現実: 確定58社中データ取得26社→精緻化後23社。リン開示の大手(日本PF/RC/アイシア)は網羅。
> 残りはJS-SPA(自動化困難)か小規模社。**「宣言した母集団へのカバー率＋未取得リスト」で正直に開示**する設計(②)なので、全網羅は不要。

> ハーベスト堅牢化の経緯: trickle応答で3回ハング(21h/5h/12h)。対策＝per-maker subprocess＋出力DEVNULL＋子75秒自爆タイマー＋妥当範囲チェック。
