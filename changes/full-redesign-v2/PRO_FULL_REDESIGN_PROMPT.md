# RAOS V2 full-redesign request for ChatGPT Pro

Use this prompt with `RAOS_FULL_REDESIGN_AUDIT_PACKET_v1.tar.gz`. The archive is
evidence for design work, not implementation authority. Its repository and public
observations are a time-bounded snapshot and must be rechecked when facts can change.

---

あなたは、日本市場のデジタルメディア戦略、楽天アフィリエイト、SEO、編集設計、UX、データ分析、WordPress／Webアーキテクチャに精通した、最高責任者レベルのプロダクト設計者です。

既存案への助言や未決事項の穴埋めではなく、楽天アフィリエイトメディア「RAOS／暮らしのしるべ」を全面的に再設計してください。

最終成果物は、別の Codex が追加判断なしで段階的な実装を開始できる、decision-complete な設計書一式と実装プロンプトです。コードは実装せず、読み取り・調査・設計・実装計画の作成までを行ってください。

# 1. 最終目的

`https://kurashinoshirube.com` を、読者価値、信頼性、検索上のカテゴリ権威、楽天送客、月次確定貢献利益、運営効率を総合した「国内トップ級の楽天購買支援メディア」へ育てるための後継設計を作成してください。

「日本一」は広告コピーではなく、測定可能な事業目標です。

- 客観的な第三者根拠がない限り、公開面で「日本一」「No.1」と表示しない
- 最初から総合メディア全体で首位を狙うのではなく、勝てる狭い領域でカテゴリ首位級の価値を作り、数値ゲートに基づいて拡大する
- 記事数やAI生成量を成功指標にしない
- 読者の意思決定を改善し、その結果として確定成果報酬と貢献利益を得る
- 法令、楽天規約、広告表示、著作権、検索品質、プライバシー、安全性は収益で相殺できないガードレールとする

# 2. ユーザーが確定した方針

次は固定条件です。

1. 維持するのは `kurashinoshirube.com` ドメインだけ
2. 「暮らしのしるべ」という名称、ブランド、カテゴリ、記事群、WordPress、Yoast、テーマ、情報設計、RAOSアーキテクチャはすべて再評価可能
3. 一括置換ではなく、現行サイトを保護した段階移行を採用
4. 主目的は、読者価値・信頼・検索評価・確定貢献利益を統合した総合成果
5. 運営は原則1人・最小固定費
6. 新しい有料サービス、外注、商品購入、設備投資は既定で採用しない
7. 有料投資を提案する場合は、任意案として費用、期待効果、損益分岐、撤退条件を示す
8. 商品の購入・レンタル・実機試験は基本戦略に含めない
9. 商品に関する公開事実は、メーカー、行政、航空会社、楽天の許可されたデータなど、適格な一次情報に限定
10. 実機を使っていない場合は、使用体験、実測、耐久性、使い勝手を経験したかのように書かない
11. 競合サイトは市場・UX研究には利用できるが、商品主張の根拠や文章生成元にはしない
12. 楽天アフィリエイトを主収益源とする
13. 日本語、日本市場、JPY、JST、モバイル優先を前提とする

# 3. 現状認識

添付監査パケットとライブの公開面を自分で確認し、次の記述を鵜呑みにせず更新してください。

現時点の概況は以下です。

- リポジトリは `/home/minami/rakuten` のRAOS monorepo
- `docs/canonical/**` はchecksumで保護された不変のv1ベースライン
- 後継設計はcanonicalを直接変更せず、外部のsuccessor specification／overlayとして作る必要がある
- 現在の公開ブランド候補は「暮らしのしるべ」
- 公開基盤候補はself-hosted WordPress
- 「移動・家事・備え」と5記事のeditorial pilotが設計・実装されている
- 比較、根拠、AI統制、公開承認、分析、セキュリティ、運用のコード・契約・テストが広範囲に存在する
- 一方、公開読者価値や収益学習より内部基盤が先行している可能性がある
- recorded fixture、disabled adapter、local candidate、formal CI、live validation、公開済み状態を混同してはならない
- 作業ツリーには進行中の変更が存在し得るため、未コミット変更を完成済み設計や安全な削除対象とみなさない

既存システムを「全部残す」または「全部捨てる」のどちらにも偏らず、各資産を次に分類してください。

- KEEP：そのまま維持
- REWORK：目的を保って簡素化・再実装
- MIGRATE：後継方式へ段階移行
- RETIRE：価値より維持費が大きいため廃止
- DEFER：現在の成長段階では不要

# 4. 調査要件

設計前に、現在時点の読み取り調査を行ってください。

## 4.1 リポジトリ監査

最低限、次を確認してください。

- root `AGENTS.md`、`README.md`、Makefile、主要manifest
- canonicalの目的、UI、分析、セキュリティ、テスト、運用、backlog
- 現行の実装状況、生成物ownership、テスト構成
- ST-1704のブランド、UI、記事、WordPress、公開、収益学習関連資料
- 公開アプリ、WordPress theme/plugin、記事renderer、evidence、analytics、publication境界
- gitの現在のbranch、HEAD、status、diffstat
- 現在の公開サイトと主要URL
- 既存5記事候補とその公開・下書き・404・redirect状態

秘密情報、credential、個人情報、raw prompt、非公開provider dataは読まないでください。

## 4.2 最新の外部調査

公開日・確認日・URLを記録し、現在有効な一次情報を優先してください。

- 楽天アフィリエイトの規約、ガイドライン、広告表示、画像、リンク、禁止行為
- 楽天Web Serviceの現行API、利用条件、クレジット、保存・表示制約
- Google Searchのpeople-first content、scaled content abuse、affiliate content、構造化データ、Core Web Vitals
- 日本のステルスマーケティング規制、景品表示、広告表示、プライバシー・外部送信に関係する公式資料
- 候補カテゴリに関係するメーカー・行政・業界団体等の一次情報
- 日本の主要な比較・購買支援メディア10～15サイトの公開面
- `kurashinoshirube.com` のデスクトップ／モバイル表示、indexability、情報設計、信頼表示、記事導線

許可のないSERPスクレイピング、競合コンテンツのコピー、レビュー本文の収集は行わないでください。

# 5. 必ず決定すること

単なる選択肢一覧ではなく、各項目について推奨案を1つ選び、理由、反対案を棄却した理由、移行方法、成功判定を記載してください。

## 5.1 「日本一」の測定定義

12か月、24か月、36か月の目標を設計してください。最低限、次を含めます。

- 読者の意思決定完了を表す指標
- Qualified Decision Sessions
- 非ブランド自然検索の表示・流入・クエリ幅
- Affiliate Outbound CTR
- Confirmed EPC／RPM
- 月次確定貢献利益
- 記事・カテゴリ別の回収期間
- 直接訪問・再訪などブランド指標
- 訂正率、重大事実欠陥、苦情、古い情報の露出
- 1記事当たりの人間作業時間と更新費

根拠のない市場数値を発明しないでください。外部ベンチマークが取得できなければ、仮説値、検証方法、再設定時点を明示してください。

## 5.2 勝てる市場の入口

既存の「移動・家事・備え」やスーツケースを前提にせず、候補カテゴリを比較してください。

評価には次を含めます。

- 購買意思決定の難しさ
- 一次情報だけで十分な独自価値を作れるか
- 実機試験なしでも誠実に推薦可能か
- 楽天内の商品・ショップの厚み
- ロングテール検索意図の広さ
- 競合の強さと差別化余地
- 商品同一性判定の難しさ
- 価格・在庫・仕様の更新負荷
- 法令・安全・誤認リスク
- 記事制作・更新コスト
- 12か月の収益仮説
- 内部リンクでトピカルオーソリティを形成できるか

1つの初期wedge、3つ以上の検索意図クラスター、最初の20～30本のポートフォリオ、拡大候補、撤退条件を決定してください。

検索量等の有効な数値がない場合は推測値を確定値として扱わず、低コストで検証する方法を設計してください。

## 5.3 独自価値

実機試験や大量記事に依存せず、一次情報からどのような独自価値を作るか決定してください。候補には次を含めて評価します。

- 条件入力型の選定フロー
- 型番・容量・セット・世代差の正規化
- 用途別の比較ロジック
- 独自計算機
- 仕様差分の可視化
- 「向く人／向かない人／買わない方がよい条件」
- 根拠レベル・確認日時・未確認事項の可視化
- 商品終了・リンク切れ・仕様変更の継続更新
- 編集判断と商品事実の明確な分離

## 5.4 ブランドと体験

ドメインだけを固定し、次を決定してください。

- ブランド名を維持するか変更するか
- ポジショニングと一文の価値提案
- ブランドvoice、信頼の根拠、運営者の見せ方
- home、category、guide、comparison、difference、tool、policyページの役割
- URL・taxonomy・breadcrumb・内部リンク
- homepageと主要記事の情報設計
- モバイルファーストのwireframe
- design tokens、typography、color、spacing、component hierarchy
- 比較表、商品カード、根拠、CTA、広告表示
- WCAG 2.2 AAを目標とするアクセシビリティ
- 画像が不足する場合の誠実な視覚設計
- 空のカテゴリや根拠のない人気表示を作らない規則

競合のコード、構成、コピー、画像を模倣しないでください。

## 5.5 編集・SEO・根拠

次を具体化してください。

- article typeと各template
- query／intent／article／product／claim／sourceのデータ関係
- 一次情報の許可・禁止source policy
- 事実、推論、編集判断、未確認の表示規則
- AIができること、できないこと
- 人間レビューと公開承認
- recommendation scoreとbusiness scoreの分離
- content quality gate
- freshness SLA
- 更新、統合、redirect、noindex、削除候補の判断
- thin affiliate contentやカニバリゼーションの防止
- title、description、canonical、robots、sitemap、structured data
- 既存URLを守る移行・redirect方針

## 5.6 収益・計測・学習

楽天アフィリエイトを中心に、次を設計してください。

- CTA placementと表示原則
- 記事、商品、placement単位のクリック計測
- 楽天成果レポートと記事帰属
- 発生報酬と確定報酬の分離
- Confirmed EPC／RPM／Contribution Profit
- Search Console、最小限のfirst-party analytics
- プライバシーを守るevent catalog
- 30日、90日、12か月の実験計画
- 継続、改善、統合、撤退の数値ゲート
- 新規記事より既存記事改善を優先する条件

料率や収益性を、記事内の商品推薦順位へ流入させないでください。

## 5.7 技術アーキテクチャ

WordPress維持、WordPress簡素化、headless、Next.js主体、その他の候補を、1人運営の総保有コストと移行リスクで比較し、1案を決定してください。

最低限、次を決定します。

- public rendering
- editorial source of truth
- product・source・claim・articleデータ
- Rakuten adapter
- AI draft／validation
- publication workflow
- analytics／attribution
- freshness jobs
- admin／review UI
- backup／restore
- security／auth
- observability
- local／CI／staging／production境界
- 既存RAOSコードのKEEP／REWORK／MIGRATE／RETIRE／DEFER
- 過剰設計を減らすための削除候補
- 残すべきsecurity、publication、evidence、rollback invariant

「既に大量のコードがある」ことを維持理由にしない一方、検証済みの安全境界を安易に捨てないでください。

# 6. 移行ロードマップ

段階移行を次の形で設計してください。

- Phase 0：現状・計測・バックアップ・URL inventoryの固定
- Phase 1：後継product specificationとdesign system
- Phase 2：1カテゴリ・数記事のvertical slice
- Phase 3：既存URLを守った公開面移行
- Phase 4：20～30記事と検索・送客の検証
- Phase 5：収益・更新費・カテゴリ継続判断
- Phase 6：数値ゲート通過後のみ拡大

各Phaseに次を付けてください。

- outcome
- in／out of scope
- dependencies
- affected subsystems
- acceptance criteria
- automated tests
- visual／accessibility checks
- analytics evidence
- failure／rollback behavior
- cost ceiling
- exit gate
- Codexが実行してよいlocal action
- 人間承認やexternal actionが必要な境界

公開、deployment、credential入力、規約同意、支出、不可逆migration、production変更は設計・ローカル実装と分離してください。

# 7. 成果物

可能なら、次のファイルを含むUTF-8のダウンロード可能な `RAOS_V2_DESIGN_PACKAGE.zip` を作成してください。ファイル生成ができない場合は、同じ内容を見出しとファイル名で区切った単一回答として、省略せず返してください。

1. `00_EXECUTIVE_DECISIONS.md`
   - 最終提案、勝ち筋、日本一の定義、最重要な10決定
2. `01_CURRENT_STATE_AND_RESEARCH.md`
   - リポジトリ・公開サイト・競合・公式資料の監査
   - 事実、観測、推論、仮説の区別
   - URL、確認日、信頼度
3. `02_PRODUCT_BRAND_CATEGORY_STRATEGY.md`
   - audience、JTBD、positioning、brand、初期wedge、カテゴリscore、記事portfolio、成長gate
4. `03_CONTENT_SEO_EDITORIAL_SYSTEM.md`
   - content model、記事template、一次情報policy、推薦、品質、鮮度、SEO、内部リンク、URL移行
5. `04_UX_DESIGN_SYSTEM.md`
   - page architecture、wireframe、component、token、responsive、accessibility、CTA、trust design
6. `05_TECHNICAL_DATA_ANALYTICS_ARCHITECTURE.md`
   - 採用architecture、data flow、interfaces、WordPress判断、AI、Rakuten、analytics、attribution、ops
7. `06_MIGRATION_ROADMAP_AND_BACKLOG.md`
   - Phase 0～6、dependencies、epic、acceptance criteria、rollback、cost gate
8. `07_DECISION_TRACEABILITY.yaml`
   - 各decisionのID、状態、根拠、採用案、棄却案、影響範囲、requirement、test、migration phase
   - 未決事項がある場合はowner、期限、安全なdefaultを必須化
9. `08_TEST_AND_ACCEPTANCE_PLAN.md`
   - unit、contract、integration、browser、visual、a11y、SEO、security、migration、analytics、UAT
10. `CODEX_MASTER_IMPLEMENTATION_PROMPT.md`
    - この設計を現在のリポジトリへ段階実装するための、コピー可能な完全プロンプト

# 8. Codex実装プロンプトの必須条件

`CODEX_MASTER_IMPLEMENTATION_PROMPT.md` は、別のCodexが追加判断なしで開始できる内容にしてください。

必ず次を含めます。

- `/home/minami/rakuten` を対象にする
- 最初にroot `AGENTS.md` とライブのgit状態を確認
- 添付パケットや過去のstatusを最新状態として盲信しない
- ユーザーや他agentのdirty changesを保持し、reset／clean／checkout／削除しない
- `docs/canonical/**`、`docs/upstream/**`、`zip/**` を変更しない
- 後継設計は新しいsuccessor specification／overlayとして管理
- Phase 0からdependency順に実装
- 現行公開面を壊さない段階移行
- generator ownerから生成物を更新
- `make setup`、`make generate`、`make check`、`make fast`、`make final` を適切に使用
- focused test、contract test、browser test、visual review、accessibility、SEO、security、migration rollbackを検証
- 公開・deployment・credential・支出・live provider writeは別承認まで実行しない
- local evidenceをproduction evidenceと呼ばない
- 各Phaseで完了条件、rollback、残課題、外部未実行事項を報告
- 実装途中で設計上の矛盾を見つけた場合のdecision escalation
- 最終的に1本のintegration PRへまとめるrepository workflow
- コード変更だけでなく、不要資産の安全なdeprecation計画も含める
- 第一段階は巨大な基盤追加ではなく、読者が利用でき計測できる最小vertical sliceを完成させる

Codex向けプロンプトには、抽象的な「よいサイトにする」ではなく、具体的な対象、data flow、interface、状態遷移、失敗時挙動、テスト、受入条件を書いてください。

# 9. 品質ゲート

最終出力前に、自分の設計を独立に批判し、少なくとも次を検査してから修正版を提出してください。

- 「日本一」が測定不能な願望になっていないか
- 1人・低コストという条件に対して過剰設計でないか
- 実機試験なしで成立しないカテゴリを選んでいないか
- AI記事量産やthin affiliate contentへ流れていないか
- 商品事実と編集判断が混ざっていないか
- 収益が推薦順位へ混入していないか
- 既存URL、canonical、redirect、indexを壊さないか
- WordPress／新architectureの移行が可逆か
- セキュリティや公開承認を弱めていないか
- KPIを実際に取得できるdata flowがあるか
- 各主要decisionがbacklogとtestへ追跡できるか
- 実装者にA案／B案の選択を残していないか

重大な矛盾が残る場合は設計完了と宣言せず、矛盾、推奨解、影響を明記してください。ただし、単に「要検討」で終わらず、安全で低コストな推奨defaultを必ず提示してください。

# 10. 回答形式

最初に200～400字の結論を書き、その後に成果物manifestを示してください。

設計本文では、各重要判断に次を含めてください。

- Decision
- Evidence
- Rationale
- Rejected alternatives
- Consequences
- Migration
- Acceptance
- Confidence
- Assumption／Unknown

既存設計の要約だけ、一般的なSEOチェックリストだけ、未決事項一覧だけ、デザインの感想だけで終わらせないでください。

目標は「現状への助言」ではありません。現在の資産を証拠として利用しながら、kurashinoshirube.comの後継プロダクトをゼロベースで決定し、Codexが安全かつ段階的に実装できる設計契約を完成させることです。
