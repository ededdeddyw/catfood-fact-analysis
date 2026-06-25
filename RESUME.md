# 作業履歴・引き継ぎ（catfood-fact-analysis）

最終更新 2026-06-25。新しいセッションはこれを読めば再開できる。詳細思想は `docs/01-07`、自動メモリも参照。

> **🟢 引き継ぎ状態（このセッション終了時点 2026-06-25）**：4本(動線統合/目的別提案/分布ヒストグラム/読みもの3本+開示率文脈)を実装・実機検証・commit・**master へ push 済＝本番Pagesデプロイ済(run success 21s)・中断中の作業なし**。作業ブランチ `claude/angry-cartwright-3d5c12`。
> 運用は毎回 `git push origin HEAD` ＋ `git push origin HEAD:master` の2本立て＝master push が Pages 自動デプロイ。**ただし master 直 push はオートモードのクラシファイアにブロックされる**ので、Claude自走時はブランチpushまで→ユーザーが手動で `git push origin <branch>:master`（または settings に許可ルール追加）。詳細は自動メモリ [[deploy-master-push-blocked]]。
> 到達点＝サイト全機能 live: フードDB(**掲載634商品**)/目的マッチ/成分5角形/**重ね比較**/**成分ツール**/**メーカー別24社ページ**/体重記録+Supabaseログイン/読みもの12本/**商品画像86%(楽天→自前ホスト)**/**★気になる(localStorage+ログイン同期+目的別の類似提案)**/**「うちの子」ハブ(mypage)**/**calc分布ヒストグラム**。
> 直近セッション(6/24-25)の主な追加: メーカー別ページ・ナビ5系統化・重ね比較・**大手取り込み**(楽天転記=ヒルズ/ネスレ/はごろも/ユニチャーム/デビフ/ペティオ/ライオン=公式未確認バッジ付き、**マース カルカンは公式kalkan.jp直取り**)・商品画像・SEO(og:image/JSON-LD)・モバイル表スクロール・**★気になるリスト**・**ログイン同期(watch_items適用済)**・**成分が近い提案**・**mypageハブ**。
> 続けるなら「次の一手候補」(§9) から。Supabase: `watch_items` 適用済・実機往復同期テスト済。テストユーザー nekogohan.watchtest@gmail.com 等は本番前に要削除。

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
- `compare` 重ねて比較（2〜3商品を選んで5角形を1枚に重ね、主要値を並べる。順位は付けない。`build_compare`/`COMPARE_JS`）。`watch`からURLハンドオフで自動プリ選択。
- `watch` 気になるフード＝**継続価値/リテンションの仕掛け**（2026-06-25）。全商品サーフェスの☆で端末内localStorage(`nekogohan_watch_v1`)に保存・ログイン不要。`WATCH_JS`を`<body>`直後に注入し`window.wbtn/NWatch`を描画前に定義、再描画ごとに同期。ヘッダーに件数バッジ。watch.htmlは一覧＋削除＋「リストの成分傾向」＋ワンクリック重ね比較＋**「成分が近い未保存商品」提案(centroid k-NN・育つほど精度↑)**＋**ログイン同期**(`watch_items`/`WATCH_SYNC_JS`)。
- `mypage` **「うちの子」ハブ**（2026-06-25・`build_mypage`/`MYPAGE_JS`）＝体重記録(record)と気になる(watch)を同じSupabaseログインで束ねる。各猫の最新体重＋増減トレンド、気になる件数/平均、体重増→カロリー密度の低い順→★比較への橋渡し。logout時ローカル/login時クラウド。**プラットフォーム構想「共有プロフィール基盤」の入口**。
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
- スキーマ `supabase/schema.sql`（cats / weight_entries + **watch_items**(2026-06-25適用済) + RLS）
- `record.html`: 未ログイン=端末内(localStorage) / ログイン=クラウド同期(メール+パスワード)。SVGグラフ・目標体重・端末→クラウド移行。**実機で往復テスト済**
- `watch.html`(気になる): 同じSupabase認証でログイン時クラウド同期(`watch_items`・union統合)。**2026-06-25 実機で往復同期テスト済**(★保存→ログイン→localStorage消去→再読込でクラウドから復活)。★自体は全ページlocalStorage。
- **Confirm email は現在OFF**（MVP。本番集客前に独自SMTP入れて再ON推奨）。テストユーザー(nekotest…/nekogohan.test…/**nekogohan.watchtest@gmail.com**)は要削除

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

## 8.8 リテンション/継続価値の仕掛け（2026-06-25・全て live）
- **★気になるリスト**（`WATCH_JS`を全ページ`<body>`直後・`window.wbtn/NWatch`・localStorage `nekogohan_watch_v1`）。全商品サーフェスに☆、ヘッダー件数バッジ、`watch.html`=一覧/削除/成分傾向/重ね比較ハンドオフ。
- **ログイン同期**（`watch.html`の`WATCH_SYNC_JS`・Supabase `watch_items`(RLS・適用済)）。★はlocalStorageのまま、watch.htmlでログイン時union統合＝端末越え。**実機往復テスト済**。
- **成分が近い提案**（`watch.html`・`suggestW()`：保存品の乾物量5マクロ平均にcentroid k-NN・順位ではない・育つほど精度↑。`build_watch(products)`が`macro_items`を埋め込み）。
- **「うちの子」ハブ**（`mypage.html`・`MYPAGE_JS`）＝体重(record)+気になる(watch)を同ログインで統合・体重増→フード選びの橋渡し。プラットフォーム構想の入口。
- スキーマは `supabase/schema.sql`（watch_items 追記済）。

## 8.9 既存の磨き込み（2026-06-25・全て live）
4本まとめて実装・実機検証済（calcヒストグラム5本描画／watch提案モード昇降順／#weight自動選択／コンソールエラー無）。
- **動線統合**：record.html と watch.html の冒頭に「← 『うちの子』ハブにもどる」btn-row を追加（mypageを起点ハブ化）。
- **目的別の提案**（`WATCHPAGE_JS suggestW`）：成分が近い候補プール(上位18)の中だけを `near`(平均に近い順) / `weight`(カロリー密度の低い順) / `protein`(たんぱく質の高い順) で並べ替え＝母集団全体の順位ではない。提案ボックス上部にモード切替の `fbtn`、提案カードにカロリー密度も表示。`macro_items` に `cal`(個包装は空) を追加。`location.hash==='#weight'/'#protein'` で初期モードを自動選択。mypageの体重増バナーから `watch.html#weight` へ直結。
- **成分分布ヒストグラム**（`CALC_JS histo()`）：calc計算結果の表に各マクロの掲載DB分布を縦棒で描画、入力値を `▼`(accent縦線)でマーク。pctBelowの「位置」と並ぶ非評価の可視化。CSS `.histo/.histocell/.histotable`。
- **読みもの3本追加**（計12本）：`blog-carbohydrate`(炭水化物/NFE 中央値27.2%) ／ `blog-ash`(灰分=ミネラル総量) ／ `blog-phosphorus-by-maker`(リン開示はメーカー方針差＝80%↑が2社/20%↓が7社で二極化・中央値27%)。`cat_stats` に nfe/ash分位点＋`_maker_disclosure()` を追加。
- **メーカーページに開示率の文脈**（`build_maker_page`）：その社のリン開示率を全社中央値(約27%)と比較し「多く/少なく開示する方針」と明記＋品質ではない旨＋`blog-phosphorus-by-maker` へ誘導。中央値は `maker_groups` で算出し各 g に `p_rate_med`。

## 9. 次の一手候補
- 残る大手は楽天/公式とも取得困難確定（シーバ=非掲載・マース他JS・ウェルペット/マルカン/アース/QIX/兼松/スペクトラム=静的成分なし）。新規取得より既存の磨き込みが高ROI
- 成分分布ヒストグラムを shape/find にも展開／記事さらに量産（多頭・シニア・子猫など）／PWA化／mypageに「気になるの成分傾向」も統合表示
- Pet-ER 公開 → 共有プロフィール基盤(mypageが芽) → Daily Lens 着手
- 本番集客前: Confirm email を再ON＋独自SMTP／テストユーザー削除（§5）
- 抽出のさらなる精緻化（per-site Playwrightで未取得32社・ヒルズ）
