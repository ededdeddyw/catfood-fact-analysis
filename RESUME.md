# 作業履歴・引き継ぎ（catfood-fact-analysis）

最終更新 2026-06-23。新しいセッションはこれを読めば再開できる。詳細思想は `docs/01-07`、自動メモリも参照。

> **🟢 引き継ぎ状態（このセッション終了時点）**：作業はすべて commit/push 済み・中断中の作業なし。
> このファイルが再開の入口。ここまでの到達点＝サイト全機能（フードDB/目的マッチ/成分5角形/成分ツール/重ね比較/メーカー別ページ/体重記録+Supabaseログイン/読みもの9本）。
> ⚠️ **2026-06-23 追加分（メーカー別ページ・ナビ整理・重ね比較）は branch `claude/amazing-bose-df109f` に push 済みだが master 未マージ＝まだ本番未反映**。デプロイは master への site/** push のみ（`.github/workflows/pages.yml`）。本番反映するには **このブランチを master にマージ**すればよい（PR or fast-forward）。
> 続けるなら「次の一手候補」(§9) から選ぶ。

## 0. 一行
広告やランキングでなく**成分・出典のファクト**で選ぶキャットフードのサイト。さらに体重記録（ログイン同期）と読みもの（データ駆動ブログ）を持つ。将来は ER／フード／健康管理 の3サービス＋共有プロフィール基盤の構想。

## 1. 公開・リポジトリ・環境
- リポジトリ: https://github.com/ededdeddyw/catfood-fact-analysis （**public**）
- 公開サイト: https://ededdeddyw.github.io/catfood-fact-analysis/ （GitHub Actions Pages = `.github/workflows/pages.yml`。`site/**` を push すると自動デプロイ）
- 2026-06-20 に `pet-hospital-launch`（Pet-ER）から分離。思想だけ横展開（4状態・出典必須・非診断・段階主義・LLMコストゼロ）
- **venv は repo に無い。`../pet-hospital-launch/.venv/Scripts/python.exe` を流用**（requests/bs4/playwright入り）
- **全工程トークンゼロ（LLM不使用）**。Windows: `PYTHONUTF8=1` を付ける。日本語はインラインでなく .py に書く（cp932対策）

## 2. 主要コマンド
```bash
PY="../pet-hospital-launch/.venv/Scripts/python.exe"
PYTHONUTF8=1 $PY -u scripts/summarize_disclosure.py     # 開示率を再集計
PYTHONUTF8=1 $PY -u scripts/build_consult_sheet.py       # data/consult_sheet_cat.csv（サイトのデータ源）を生成
PYTHONUTF8=1 $PY -u scripts/build_site.py                # site/ を生成（→ push でデプロイ）
PYTHONUTF8=1 $PY -u scripts/reextract_from_cache.py      # 抽出ロジック変更時：キャッシュから再抽出(ネット不要・31秒)
```
ワークフロー：抽出を直す → reextract_from_cache → summarize_disclosure → build_consult_sheet → build_site → commit/push。

## 3. データパイプライン
- **母集団**: ペットフード公正取引協議会 正会員79社 → `data/pffta_members.csv`（`crawl_pffta_members.py`）
- **公式URL解決**: `resolve_maker_sites.py`(Bing+会社名一致検証) / `verify_proposed_sites.py` / `reconcile_maker_sites.py` / `merge_human_urls.py` → `data/maker_sites.csv`。**ユーザーが79社を目検済**（Human列）。確定58社、未取得32社=JS-SPA(Playwright要)
- **取得**: `harvest_sitemap_products.py`(大手 sitemap・gz対応) / `harvest_seed_sites.py`(中小 BFS) / `extract_product_facts.py` / `extract_product_facts_pw.py`(Playwright)
- **★HTMLキャッシュ**: `html_cache.py` + `populate_cache.py` + `reextract_from_cache.py`。取得と抽出を分離 → **抽出変更時に再取得不要**（trickleハング回避の本丸）
- **抽出**: `catfood_nutrition_patterns.py`（正規表現・乾物量換算・全角半角・保証成分ブロック限定・「コリン」のリン誤マッチ修正・妥当範囲チェック・species犬猫・カロリー単位/basis）
- **出力**: `data/product_facts_raw.csv`(約465猫商品+一部犬) / `data/disclosure_matrix.csv` / `data/consult_sheet_cat.csv`(乾物量DM・NFE込み=サイトの源)
- 監査結果(docs/04): リン開示 約38-42%（メーカー方針で二極化:日本PF93%/RC55%/いなば4%）、カロリー94%、原材料98%。腎臓シートは「縮小版GO」。

### 取得のハマりどころ（重要）
- trickle応答(細切れHTTP)で**3回ハング**(21h/5h/12h)。対策＝per-maker subprocess + 出力DEVNULL + **子プロセスに75秒自爆タイマー(threading.Timer→os._exit)** + 妥当範囲チェック。`harvest_seed_sites.py` 参照
- それでも完走に固執せず「主力大手が取れていればOK」で打ち切る判断

## 4. サイト（静的・`scripts/build_site.py` → `site/`）
ブラウン基調 + 猫イラスト(自作SVG) + 実写4枚(`site/img/`, Wikimedia PD/CC0/CC-BY, クレジットはabout)。SEO: meta/OGP/canonical/sitemap/robots/.nojekyll、ブログにArticle JSON-LD。
- `index` ランディング(全幅マルチセクション、wrap=False)
- `find` 目的から選ぶ（透明な条件マッチ=GOALS。体重/高たんぱく/水分/グレインフリー/繊維=生活、尿路/腎臓=健康・獣医併記）
- `shape` 成分5角形レーダー一覧（乾物量、点数化しない）
- `compare` 重ねて比較（2〜3商品を選んで5角形を1枚に重ね、主要値を並べる。順位は付けない。`build_compare`/`COMPARE_JS`）
- `makers` メーカー一覧 + `maker-<slug>.html` 社別ページ（19社。スラッグはドメイン由来=SEO。収録数順=網羅の事実であり評価ではない。`maker_groups`/`build_maker_page`）
- `calc` 成分ツール（袋の数値→乾物量換算+分布上の位置+成分が近い商品k近傍。DBに無い袋でも使える＝主役ハック）
- `record` 体重記録（§5）
- `weight`/`kidney` フードビュー、`coverage` 網羅性(②③)、`about` この調べ方+写真クレジット+**全データJSON公開**(`site/data/cat_products.json`)
- `blog` 読みもの + 記事9本（§6）
- `build_consult_sheet.py` は `prototype/consult/`(内部DBビュー) も生成

### 思想（docs/01-03,07・厳守）
評価せず・順位を付けず・母集団宣言・出典必須・4状態・乾物量換算・非診断・アフィリ遮断（手数料を表示順に使わない・購入リンク全商品平等）。**docs/07 = 「ファクトだけは弱い」→「透明な条件マッチ」へ進化（スコア化はしない）**。

## 5. ログイン・体重記録（Supabase）
- プロジェクト `nekogohan` / URL `https://yjfogfsgwylzrkksremm.supabase.co` / anon公開キーは `build_site.py` の `SUPABASE_ANON`（RLSで保護＝公開リポでも安全。service_role/DBパスは扱わない）
- スキーマ `supabase/schema.sql`（cats / weight_entries + RLS）適用済
- `record.html`: 未ログイン=端末内(localStorage) / ログイン=クラウド同期(メール+パスワード)。SVGグラフ・目標体重・端末→クラウド移行。**実機で往復テスト済**
- **Confirm email は現在OFF**（MVP。本番集客前に独自SMTP入れて再ON推奨）。テストユーザー(nekotest…/nekogohan.test…@gmail.com)は要削除

## 6. 読みもの（データ駆動ブログ・SEO）
- 普通のAI量産はしない。**核心数字を `cat_stats()` で465商品DBから集計**（薄い量産を避け一次データで差別化）
- 記事9本（リン/ウェット対ドライたんぱく質/グレインフリー/カロリー密度/尿路Mg/水分/高たんぱく/療法食の違い/保証分析値の読み方）
- 各記事: 出典・非診断・Article JSON-LD・calc/find/recordへ回遊。療法食記事はYMYL配慮で獣医前提を強調
- レンジは外れ値対策で10-90パーセンタイル使用
- **増やし方**: `blog_pages()` の `arts` にタプル追加するだけ

## 7. プラットフォーム構想（合意済・未着手）
- **3サービス（ER / フード / 健康管理=Daily Lens）＋裏の共有「うちの子」プロフィール基盤 = 4構成**
- 体重"記録"は健康管理へ、体重→フードの"選択"はフードに残し、体重トレンドで連結
- 収益: 健康管理(日次=継続課金/情緒課金)とPet-ER(送客)が稼ぎ頭、フードは信頼/SEOの正面玄関。中立を汚さず黒字化
- **かかりつけ医 ↔ Pet-ER 病院マスタ参照**でプロフィールが"動く"
- スキーマ叩き台 `supabase/platform_schema_draft.sql`（profiles/pets/health_events・**未適用**）。順序は Pet-ER公開 → 基盤 → Daily Lens
- 将来 docs/05: ドッグフード横展開（犬データは捨てない）・オーダーメイドフード接続

## 8. 既知の注意
- プレビューの screenshot がこの環境でタイムアウト → `preview_eval`(computed style/getBBox) と Read(画像)で検証する
- ~~ナビが10項目で過密~~ → **解決済(2026-06-23)**。`NAV`(build_site.py)を5系統にグループ化（ホーム/選ぶ/健康・記録/読みもの/サイトについて）。ドロップダウンはJS不要の`<details>`、`NAV_JS`で兄弟自動クローズ+外側クリック閉じ。ナビ項目を増やすときは`NAV`のタプルを足すだけ
- いなば/アイシアのsitemapは犬猫混在 → product_facts に犬製品も含む（猫サイトは species!=dog で除外、犬は将来用に保持）
- 起動中の preview サーバが**別worktreeのsite/を配信していて404**になることがある → `preview_stop`→`preview_start`で貼り直す

## 8.5 商品画像（楽天API→自前ホスト）— 取得完了（2026-06-24）
- `scripts/fetch_product_images.py`：**新 Rakuten Developers API(2026-04-01)** 対応。エンドポイント `openapi.rakuten.co.jp/ichibams/.../20260401`、認証＝`applicationId`(UUID)＋`accessKey`(pk_…)＋**`Referer`/`Origin` 必須**（登録URL一致。無いと403）。鍵は env か **gitignore済 `.env`**（`RAKUTEN_APP_ID`/`RAKUTEN_ACCESS_KEY`、任意で `RAKUTEN_REFERER`）から読む＝リポに残さない。
- マッチングは保守的：識別トークン2つ以上＋**犬用除外**(`is_dog_only`)＋スコア2の弱マッチは会社名/サブブランド(`SUB_BRANDS`: CIAO/MiawMiaw/コンボ等)一致必須。出典URLから rafcid 等アフィリ追跡を除去(`clean_item_url`)。429/5xxリトライ・再開可能。
- **結果：465商品中 390点を採用(84%)**。誤マッチ11点(犬用7・別ブランド/汎用サプリ4)は除外。画像は `site/img/products/`(11MB・自前ホスト＝閲覧時に楽天へ通信させない)、対応表 `data/product_images.csv`。
- `build_site.py`：`product_images.csv`→各商品 `img`。商品テーブル/find/重ね比較/成分のかたち/メーカーカードにサムネ(`.pthumb`/`.mthumb`)。画像無し75商品はテキストのみ。about「商品画像について」節。
- **再取得/追加**：`.env` に2鍵→ `PYTHONUTF8=1 $PY scripts/fetch_product_images.py`(再開) or `--refresh`(全件)。プルーニング基準は `accept()`。

## 8.7 精緻化（2026-06-24）
- **掲載634商品**（公式476＋楽天158）。**商品画像86%**（`fetch_product_images` を新規大手にも再実行＋画像マッチャ `SUB_BRANDS` に大手ブランド追加→マース画像2→27/55）。
- 楽天転記名のクリーンアップ強化（`harvest_rakuten_majors.clean_title`：SEO境界◆/で切る・連続重複畳み・カタカナSEO読み除去・語境界切り詰め。dedupキーは味を残しノイズ語で畳む）。カルカンは公式取得済みのため楽天MAJORSから除外。
- モバイル: データ表を `.tablewrap` で横スクロール化（ページは溢れない）。
- SEO: 全ページ og:image(hero)＋`summary_large_image`＋og:locale、トップに Organization/WebSite の JSON-LD。
- ゴミ商品名フィルタ（`build_consult_sheet._is_junk_name`：製品詳細/商品紹介/OEM等を除外）。
- **マース＝カルカンのみ公式取得可**（kalkan.jp・静的・`harvest_mars.py`）。シーバは成分が**サイト非掲載**で取得不可確定（Playwrightでも無理）。他31社のブラウザヘッダ再チェックでも新規クリーン公式社なし。

## 8.6 大手メーカーの取り込み（楽天転記・公式未確認）— 実装済み（2026-06-24）
- 公式がJS描画で取れない大手は **楽天商品検索の itemCaption に転記された保証分析値**を抽出（`scripts/harvest_rakuten_majors.py`→`data/product_facts_rakuten.csv`, source=rakuten）。既存 `extract_nutrition()` がそのままパース。
- **ブランド帰属が確実な4社のみ**: 日本ヒルズ(サイエンスダイエット)/ネスレ ピュリナ(モンプチ/ピュリナワン/プロプラン/フィリックス)/はごろも(無一物)/ユニチャーム(銀のスプーン)=**約85商品**。スペクトラムは公式が8in1のみと判明し除外、マースはwet中心で0件（設定だけ残置）。追加は `MAJORS` にブランド確実な社だけ足して再ハーベスト。
- `build_consult_sheet.py` が公式＋楽天を `source` 列付きでマージ（**同一商品は公式優先**）。`build_site.py` が全ビューに **「公式未確認」バッジ**＋出典「楽天」表記、メーカーページに注意バナー、網羅性に独立セクション、aboutに説明。**公式が取れ次第 公式優先で差し替わる**設計。
- 偵察ツール `scripts/probe_maker_coverage.py`（sitemap/静的成分の有無を粗く調べる。NUTRI判定が宣伝文に誤反応する点に注意）。

## 9. 次の一手候補
- ~~ナビ整理／2-3商品の重ね比較／メーカー別ページ~~ ← **2026-06-23 実装済(本ブランチ)**
- **商品画像の本取得**（§8.5・鍵待ち）
- 記事をさらに量産（同方式）／成分分布グラフ（ヒストグラム）／メーカー別ページに開示率の文脈解説／PWA化
- Pet-ER 公開を仕上げる → 共有プロフィール基盤を流す → Daily Lens 着手
- 抽出のさらなる精緻化（per-site Playwrightで未取得32社・ヒルズ）
