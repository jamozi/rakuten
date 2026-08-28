# RAOS V2 Executive Decisions

## 結論

RAOS V2は、kurashinoshirube.comを維持しつつ「公式ルールと製品仕様を照合し、条件に合う候補だけを残す」購買支援へ再構築する。初期wedgeは機内持ち込み条件と短期旅行荷物に限定し、WordPress公開面とGit上の根拠・編集制御を段階接続する。最初の実装はchecker、基本guide、既存比較記事のoffline vertical sliceで、自動公開・live楽天API・認証情報・支出・production変更を含めない。記事量ではなくQDS、送客、成熟した確定報酬、貢献利益、重大欠陥ゼロ、更新時間で12/24/36か月の成否を判定する。

## 成果物manifest

| File | Purpose |
| --- | --- |
| 00_EXECUTIVE_DECISIONS.md | 最終提案、勝ち筋、KPI、全34 decision。 |
| 01_CURRENT_STATE_AND_RESEARCH.md | repository/public/official/competitor監査とfact/observation/inference/hypothesis。 |
| 02_PRODUCT_BRAND_CATEGORY_STRATEGY.md | audience/JTBD/brand/wedge/category score/25-asset portfolio/gates。 |
| 03_CONTENT_SEO_EDITORIAL_SYSTEM.md | content model、templates、source/AI/recommendation/freshness/SEO/migration。 |
| 04_UX_DESIGN_SYSTEM.md | IA、wireframe、tokens、components、responsive、a11y、performance。 |
| 05_TECHNICAL_DATA_ANALYTICS_ARCHITECTURE.md | architecture、data/interfaces、Rakuten、publication、analytics、ops、asset disposition。 |
| 06_MIGRATION_ROADMAP_AND_BACKLOG.md | Phase 0〜6、49 backlog、dependency、rollback、cost/exit gate。 |
| 07_DECISION_TRACEABILITY.yaml | 34 decisions→36 requirements→49 backlog→51 testsの双方向trace。 |
| 08_TEST_AND_ACCEPTANCE_PLAN.md | unit/contract/integration/browser/visual/a11y/SEO/security/migration/analytics/UAT。 |
| CODEX_MASTER_IMPLEMENTATION_PROMPT.md | 現在のrepositoryへ安全に実装するcopy-ready prompt。 |
| 09_EVIDENCE_AND_SOURCE_REGISTER.yaml | packet source hash、公式URL、競合surface。 |
| 10_INTERFACE_CONTRACTS.yaml | entity、port、state transition、overlay pathの固定契約。 |
| 11_EXTERNAL_ACTIONS_REGISTER.yaml | 人間承認が必要な14 action。全てNOT_EXECUTED。 |
| 12_INDEPENDENT_QUALITY_REVIEW.md | quality gateに対する独立批判と修正結果。 |
| CONTROL/* / MANIFEST.sha256 | 実装契約、機械検証、package完全性。 |

## 推奨target state

**Public brand:** 暮らしのしるべ  
**Internal system name:** RAOS V2  
**Domain:** `https://kurashinoshirube.com`  
**Positioning:** 公式ルールと製品仕様を照合し、あなたの条件で買える候補だけを残す。  
**Initial wedge:** 旅の機内持ち込み条件と荷物選び  
**Public renderer:** self-hosted WordPress  
**Editorial/evidence source of truth:** Git上のV2 successor overlay  
**Publication authority:** 人間のみ  
**Primary revenue:** 楽天アフィリエイト  
**Recommendation ordering:** 非財務のeligibility/fitだけ  
**Default external spend:** ¥0  
**Operating model:** 1人、mobile-first、JPY/JST、日本市場

### 勝ち筋

1. 航空会社のeffective-date付きルールとメーカー外寸・重量・variantを正規化する。
2. 読者が便・航空会社・荷物条件を入力すると、適合／非適合／未確定と理由を返す。
3. 「買うべき商品」だけでなく、買わずに荷物を減らす、拡張しない、預ける等の代替案を示す。
4. 型番・世代・セット・アクセサリ誤同定を防ぎ、楽天へのCTAはexact identity時だけ有効化する。
5. 1記事単位でsource freshness、public integrity、QDS、送客、成熟した確定成果、制作/更新費を測り、数値gate前の量産を禁止する。

## 「国内トップ級」の測定定義

これは公開広告表現ではなく、内部の事業目標である。市場benchmarksが未取得のため、次の絶対値は**planning hypothesis**であり、Day 30とDay 90にbaselineから再設定する。再設定は履歴を消さず、変更理由・source・owner・effective monthを残す。

| Horizon | Scope | Non-brand organic | Qualified Decision Sessions | Affiliate outbound CTR | Confirmed unit economics | Monthly confirmed economic contribution profit | Brand | Quality guardrails | Operating efficiency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 12か月 | 24〜25 assets（tool 1以上） | 月5,000 non-brand organic sessions | 月1,500 QDS / QDS率30%以上 | 6%以上 | Confirmed EPC ¥30以上 / Confirmed RPM ¥1,800以上 | 月次確定経済貢献利益 ¥60,000以上を成熟3か月 | 直接＋再訪8%以上 | 重大事実欠陥0、期限超過high-risk claim 0、訂正率1%未満 | 新規記事中央値8h以下、更新1.5h/page/月以下、回収9か月以内 |
| 24か月 | 45〜50 assets（隣接cluster最大1） | 月25,000 non-brand organic sessions | 月8,000 QDS / QDS率32%以上 | 7%以上 | Confirmed EPC ¥40以上 / Confirmed RPM ¥2,800以上 | 月次確定経済貢献利益 ¥250,000以上を成熟3か月 | 12%以上 | 重大事実欠陥0、苦情72h一次対応100%、古い情報露出0.5%未満 | 新規6h以下、更新1h/page/月以下、回収6か月以内 |
| 36か月 | 75〜85 assets（validated wedge最大3） | 月75,000 non-brand organic sessions | 月25,000 QDS / QDS率33%以上 | 8%以上 | Confirmed EPC ¥50以上 / Confirmed RPM ¥4,000以上 | 月次確定経済貢献利益 ¥700,000以上を成熟6か月 | 18%以上 | 重大事実欠陥0、訂正率0.5%未満、期限超過公開claim 0 | 新規5h以下、更新0.75h/page/月以下、回収5か月以内 |

### 指標定義

- **Qualified Decision Session (QDS):** 同一30分session内で、(a) tool resultを表示、または (b) comparison/evidenceを閲覧した後にofficial source openまたはaffiliate outbound activationを行ったsession。滞在時間だけではQDSにしない。
- **Affiliate Outbound CTR (AOC):** `verified affiliate outbound activations / affiliate-eligible article sessions`。CTAが無い、identity unresolved、consent/measurement unavailableのsessionは分母定義を明示する。
- **Confirmed EPC:** `mature confirmed reward JPY / attributable verified outbound clicks`。DIRECT_PROVIDERまたは事前定義したCLICK_COHORTのみ。分母0/attribution不能はUNAVAILABLE。
- **Confirmed RPM:** `mature confirmed reward JPY / eligible sessions × 1,000`。program totalをarticleへ按分しない。
- **Cash contribution profit:** `mature confirmed reward - direct variable external cost`。
- **Economic contribution profit:** `cash contribution profit - human production/update hours × internal labor rate`。初期仮説は¥3,000/h、owner実績で更新。
- **Payback period:** `article total economic production cost / trailing mature monthly economic contribution`。mature monthly contribution≤0は未回収。
- **Critical fact defect:** 航空規則、寸法、重量、identity、広告表示、CTA destination等が読者判断を誤らせ得る重大欠陥。1件でもgrowth gateを停止する。

## 最重要10 decision

### D-V2-004 — 初期wedgeを「旅の機内持ち込み条件と荷物選び」に限定する。

- **Decision:** 初期wedgeを「旅の機内持ち込み条件と荷物選び」に限定する。
- **Evidence:** AUD-009, AUD-015, AUD-023, WEB-016, WEB-017, WEB-018, WEB-019
- **Rationale:** 意思決定が難しく、航空会社一次情報と製品外寸を組み合わせる固有価値が高く、実機なしでも誠実に適合判定できる。
- **Rejected alternatives:** 移動・家事・備えを同時展開 / ポータブル電源 / 食洗機/ロボット掃除機 / 価格中心のスーツケース総合ランキング
- **Consequences:** home、nav、article portfolio、source freshnessをこのwedgeへ集中する。
- **Migration:** 公開スーツケース記事を核にWave 1の6 assetsを先行。既存4 draftは保管してDEFER。
- **Acceptance:** Day 90 gateまでwedge外の記事を新規公開せず、6 assetsでQDSとclick learningを取得する。
- **Confidence:** HIGH
- **Assumption／Unknown:** 検索需要・楽天商品厚みの定量値はPhase 0で仮説検証。
### D-V2-003 — 価値提案を「公式ルールと製品仕様を照合し、あなたの条件で買える候補だけを残す。」に固定する。

- **Decision:** 価値提案を「公式ルールと製品仕様を照合し、あなたの条件で買える候補だけを残す。」に固定する。
- **Evidence:** AUD-020, AUD-024, WEB-006, WEB-007
- **Rationale:** 実機試験なしでも一次情報から独自のdecision supportを作れ、競合のtest/rankingと正面衝突しない。
- **Rejected alternatives:** 総合おすすめランキング / AIで大量の商品紹介 / 生活情報全般
- **Consequences:** 全記事は条件、official fact、判断、非適合条件、未確認を中心に構成する。
- **Migration:** home hero、article intro、policy、CTAをこのpromiseへ合わせる。
- **Acceptance:** 5秒テストで対象読者が「条件適合を公式根拠で確認するサイト」と説明できる。
- **Confidence:** HIGH
- **Assumption／Unknown:** 5秒テストはPhase 2 UATで実施。
### D-V2-007 — 公開rendererはself-hosted WordPressを維持し、GitのV2 successor overlayを編集・根拠・検証のsource of truthにする。

- **Decision:** 公開rendererはself-hosted WordPressを維持し、GitのV2 successor overlayを編集・根拠・検証のsource of truthにする。
- **Evidence:** AUD-002, AUD-026, AUD-028, AUD-030
- **Rationale:** 既存URL/Yoast/公開運用を守りながら、structured evidenceと再現可能なdraft packageを実現する最小TCO案。
- **Rejected alternatives:** WordPressのみSoT / Headless WordPress+Next.js / Next.js全面移行 / 現行RAOS全機能完成
- **Consequences:** Git→sealed package→WordPress draftの一方向flowを採用し、public edit driftを検出する。
- **Migration:** Phase 1/2はlocal previewのみ、Phase 3から人間操作で1 URLずつ移行。
- **Acceptance:** 同一inputから同一render digestを生成し、production書込みなしでpreviewできる。
- **Confidence:** HIGH
- **Assumption／Unknown:** live plugin/theme/versionはPhase 0再確認。
### D-V2-011 — 公開claimをA=公式事実、B=第三者実測、C=利用者傾向、D=編集判断、UNKNOWN=未確認に型付けし、初期V2はA/D/UNKNOWNだけを許可する。

- **Decision:** 公開claimをA=公式事実、B=第三者実測、C=利用者傾向、D=編集判断、UNKNOWN=未確認に型付けし、初期V2はA/D/UNKNOWNだけを許可する。
- **Evidence:** AUD-020, AUD-018, WEB-006
- **Rationale:** 商品事実と判断を分離し、実機やreview evidenceのないB/Cを誤用しない。
- **Rejected alternatives:** 全文章を同じ事実扱い / AI confidence score / 競合記事をB/C根拠にする
- **Consequences:** claim-source binding、表示label、validatorが必須。
- **Migration:** 既存記事の各文をclaim unitへ変換する。
- **Acceptance:** 公開claim 100%がtype、source/logic、checked_at、freshnessを持つ。
- **Confidence:** HIGH
- **Assumption／Unknown:** 将来B/C導入は別evidence contract。
### D-V2-014 — 推薦はhard eligibility後に非財務fit scoreで並べ、公開面では点数を見せず条件別結論を示す。

- **Decision:** 推薦はhard eligibility後に非財務fit scoreで並べ、公開面では点数を見せず条件別結論を示す。
- **Evidence:** AUD-020, AUD-025, WEB-006
- **Rationale:** 適合しない商品を高得点化せず、推薦理由を説明可能にする。
- **Rejected alternatives:** 総合1位 / commission/EPC順 / 人気順 / AI主観点数
- **Consequences:** hard filter=identity/evidence/rule/availability、fit weightsをversion管理する。
- **Migration:** 既存3モデル記事を条件別pickへ再計算。
- **Acceptance:** 財務入力を変えても推薦順が不変、同一入力で決定的。
- **Confidence:** HIGH
- **Assumption／Unknown:** fit weightはDay 30 interviewで再校正可能。
### D-V2-018 — 公開workflowはDRAFT→EVIDENCE_COMPLETE→HUMAN_REVIEWED→PACKAGE_SEALED→WP_DRAFT_CREATED→HUMAN_PUBLISHED→PUBLIC_VERIFIEDとし、publish capabilityは人間だけに残す。

- **Decision:** 公開workflowはDRAFT→EVIDENCE_COMPLETE→HUMAN_REVIEWED→PACKAGE_SEALED→WP_DRAFT_CREATED→HUMAN_PUBLISHED→PUBLIC_VERIFIEDとし、publish capabilityは人間だけに残す。
- **Evidence:** AUD-016, AUD-026, AUD-003
- **Rationale:** 既存の安全なpublication boundaryを維持しつつ段階移行できる。
- **Rejected alternatives:** 自動公開 / 部分自動公開 / WordPress live editを即正本化
- **Consequences:** 各transitionにhash、actor、timestamp、precondition、rollbackを持つ。
- **Migration:** publication operator概念をV2 schemaへ縮小。
- **Acceptance:** Codex/local testにpublish/schedule/delete/network write pathがない。
- **Confidence:** HIGH
- **Assumption／Unknown:** WordPress draft creationも別承認までNOT_EXECUTED。
### D-V2-021 — 計測はSearch Console、privacy-minimized first-party event、成熟した楽天成果reportを採用し、新しいthird-party senderは既定OFFとする。

- **Decision:** 計測はSearch Console、privacy-minimized first-party event、成熟した楽天成果reportを採用し、新しいthird-party senderは既定OFFとする。
- **Evidence:** AUD-017, AUD-027, WEB-014
- **Rationale:** 流入・判断・送客・確定成果を最小dataでつなぎ、1人運営のTCOを抑える。
- **Rejected alternatives:** GA4だけ / cookieなしの過剰fingerprinting / 初期からCDP/dashboard SaaS
- **Consequences:** event allowlist、retention、consent/policy gate、UNAVAILABLE処理が必要。
- **Migration:** 既存Site Kit/GA4は30日parallel observation後にretain/remove判断、勝手に変更しない。
- **Acceptance:** 禁止属性がcollectorへ送られず、production activationはprivacy approvalなしでOFF。
- **Confidence:** MEDIUM_HIGH
- **Assumption／Unknown:** 現行analytics設定と履歴はPhase 0で確認。
### D-V2-026 — 情報設計は`/carry-on/`をwedge hubとし、`/guides/`、`/comparisons/`、`/differences/`、`/tools/`、`/policy/`へ役割分離する。

- **Decision:** 情報設計は`/carry-on/`をwedge hubとし、`/guides/`、`/comparisons/`、`/differences/`、`/tools/`、`/policy/`へ役割分離する。
- **Evidence:** AUD-008, AUD-010, AUD-021, WEB-009
- **Rationale:** 検索intentとreader journeyを明確にし、homeの空カテゴリを解消する。
- **Rejected alternatives:** 移動/家事/備えの空カテゴリ / date archive中心 / タグの無制限index
- **Consequences:** breadcrumbと内部link graphが必須。
- **Migration:** 既存記事URLは維持、空taxonomyはnavから除外しinventory別にnoindex/redirect。
- **Acceptance:** 全indexable pageがhubから3 click以内、orphan 0、empty indexable archive 0。
- **Confidence:** HIGH
- **Assumption／Unknown:** 既存WordPress taxonomyのlive inventory。
### D-V2-033 — 最初のintegration PRはPhase 0〜2のoffline vertical sliceとPhase 3以降のdisabled contract/runbookだけに限定する。

- **Decision:** 最初のintegration PRはPhase 0〜2のoffline vertical sliceとPhase 3以降のdisabled contract/runbookだけに限定する。
- **Evidence:** AUD-002, AUD-003, AUD-028
- **Rationale:** 読者が使えるchecker+guide+比較previewを先に完成し、巨大基盤追加とexternal riskを避ける。
- **Rejected alternatives:** 全Phase一括実装 / architectureだけのPR / production migration同梱
- **Consequences:** isolated worktree、allowed path、one PR、no destructive deletion。
- **Migration:** live HEADからbranchを作り、current dirty pathを触らない。
- **Acceptance:** local preview、contract/unit/browser/a11y/SEO/security/rollback testがgreen、external register全NOT_EXECUTED。
- **Confidence:** HIGH
- **Assumption／Unknown:** 実装開始時HEAD/branch/path availability。
### D-V2-034 — 公開、deployment、credential、live provider request/write、規約同意、支出、production migration、不可逆削除は設計/ローカル実装から分離し人間承認必須とする。

- **Decision:** 公開、deployment、credential、live provider request/write、規約同意、支出、production migration、不可逆削除は設計/ローカル実装から分離し人間承認必須とする。
- **Evidence:** AUD-001, AUD-003, AUD-016, AUD-026
- **Rationale:** ユーザー要求とrepository安全境界を維持する。
- **Rejected alternatives:** 暗黙承認 / 設計packageを実行権限とみなす / local evidenceをproduction evidenceと呼ぶ
- **Consequences:** external actions register、approval record、NOT_EXECUTED reportingが必要。
- **Migration:** 各Phase exit reportでexternal未実行を明示。
- **Acceptance:** package/初回PRにsecret値、external write、publish/deploy、費用発生がない。
- **Confidence:** HIGH
- **Assumption／Unknown:** なし。


## 最初のintegration PR

**Branch proposal:** `codex/raos-v2-vertical-slice`  
**Worktree proposal:** `/home/minami/rakuten-raos-v2`  
**Base:** 実装開始時のlive `HEAD`。監査packetの`83cfa17f91dddbee2bcd4e781545fd2bb4a5bcc4`をcurrent baseと仮定しない。  
**Scope:** Phase 0〜2のoffline vertical slice、Phase 3以降のdisabled contract/runbook。  
**Reader-visible local result:** carry-on checker、基本rule guide、既存comparisonのV2 local preview、policy page、home/hub preview。  
**Excluded:** WordPress write/publish、deploy、credential、Rakuten live request、analytics transmission、provider export、支出、destructive deletion。

### 完了条件

- `make setup`, affected `make generate`, `make check`, `make fast`, `make final`がrepository規則どおり成功する。
- 51 testのうちPhase 0〜2対象がgreen。formal CI、staging、Production evidenceとは呼ばない。
- 390/768/1440、200% zoom、keyboard、no-JS、reduced motion、forced colorsでcritical defect 0。
- 財務fixture変更で推薦順/render hashが変わらない。
- network denied、secret scan、immutable path、publication-disabled、rollback simulationがgreen。
- external action registerは全て`NOT_EXECUTED`。

## 非交渉guardrails

- 一次情報で確認できない商品事実はUNKNOWNと表示し、推測で埋めない。
- 実機を使っていない場合、操作性・耐久性・静音性・使い勝手を経験したように書かない。
- 楽天の報酬、料率、EPC、在庫、価格、人気を推薦順へ入力しない。
- 広告表示は常時見える短文をfirst view近くに置き、policy detailを別linkで補う。
- 商品画像・affiliate URLはexact product identityと許可されたprovenanceが無ければ無効。
- 公開、deployment、credentials、規約同意、支出、live provider write、不可逆migrationは人間承認まで実行しない。
- existing dirty pathsを保持し、reset/clean/checkout/deleteで消さない。
- `docs/canonical/**`, `docs/upstream/**`, `zip/**`を変更しない。
- local evidenceをformal CI、staging、release、Production evidenceと呼ばない。
- 記事量をKPIにせず、reader decision、quality、confirmed economics、update costで拡大を決める。

## 全decision register

以下34件は選択済みであり、実装者に代替案選択を残さない。残る情報不足は`Assumption／Unknown`のsafe defaultに従う。

### D-V2-001 — kurashinoshirube.comだけを固定し、現行公開面を保護したURL単位の段階移行を採用する。

- **Decision:** kurashinoshirube.comだけを固定し、現行公開面を保護したURL単位の段階移行を採用する。
- **Evidence:** AUD-001, AUD-002, AUD-008, AUD-009, AUD-010
- **Rationale:** ドメイン履歴と唯一の公開記事を保持しつつ、名称以外の設計をゼロベースで置換できる。
- **Rejected alternatives:** 一括リプレース / 新ドメイン移転 / 現状凍結
- **Consequences:** 旧URL inventory・redirect map・rollback snapshotがPhase 0の必須成果物になる。
- **Migration:** 現行URLをbaseline化し、1 URLずつV2 templateへ置換する。
- **Acceptance:** 公開URLのcanonical/status/indexabilityが移行前後でintentional mapと一致し、404増加がない。
- **Confidence:** HIGH
- **Assumption／Unknown:** production構成はPhase 0でlive read-only再確認。
### D-V2-002 — 公開ブランド名は「暮らしのしるべ」を維持し、RAOSは内部システム名に限定する。

- **Decision:** 公開ブランド名は「暮らしのしるべ」を維持し、RAOSは内部システム名に限定する。
- **Evidence:** AUD-008, AUD-009, AUD-020, AUD-023
- **Rationale:** 名称は落ち着いた購買支援に適合し、変更による学習損失よりpositioning明確化の利益が大きい。
- **Rejected alternatives:** RAOSを公開ブランド化 / スーツケース専用名へ改名 / 完全匿名の一般名
- **Consequences:** ロゴ・copy・taxonomyは刷新するが、運営者・広告方針との整合を保つ。
- **Migration:** header/footer/policy/metadataを同一brand contractへ統合。
- **Acceptance:** 全公開面で名称・価値提案・運営主体・広告表示が矛盾しない。
- **Confidence:** MEDIUM_HIGH
- **Assumption／Unknown:** brand recallは現時点で未計測。
### D-V2-003 — 価値提案を「公式ルールと製品仕様を照合し、あなたの条件で買える候補だけを残す。」に固定する。

- **Decision:** 価値提案を「公式ルールと製品仕様を照合し、あなたの条件で買える候補だけを残す。」に固定する。
- **Evidence:** AUD-020, AUD-024, WEB-006, WEB-007
- **Rationale:** 実機試験なしでも一次情報から独自のdecision supportを作れ、競合のtest/rankingと正面衝突しない。
- **Rejected alternatives:** 総合おすすめランキング / AIで大量の商品紹介 / 生活情報全般
- **Consequences:** 全記事は条件、official fact、判断、非適合条件、未確認を中心に構成する。
- **Migration:** home hero、article intro、policy、CTAをこのpromiseへ合わせる。
- **Acceptance:** 5秒テストで対象読者が「条件適合を公式根拠で確認するサイト」と説明できる。
- **Confidence:** HIGH
- **Assumption／Unknown:** 5秒テストはPhase 2 UATで実施。
### D-V2-004 — 初期wedgeを「旅の機内持ち込み条件と荷物選び」に限定する。

- **Decision:** 初期wedgeを「旅の機内持ち込み条件と荷物選び」に限定する。
- **Evidence:** AUD-009, AUD-015, AUD-023, WEB-016, WEB-017, WEB-018, WEB-019
- **Rationale:** 意思決定が難しく、航空会社一次情報と製品外寸を組み合わせる固有価値が高く、実機なしでも誠実に適合判定できる。
- **Rejected alternatives:** 移動・家事・備えを同時展開 / ポータブル電源 / 食洗機/ロボット掃除機 / 価格中心のスーツケース総合ランキング
- **Consequences:** home、nav、article portfolio、source freshnessをこのwedgeへ集中する。
- **Migration:** 公開スーツケース記事を核にWave 1の6 assetsを先行。既存4 draftは保管してDEFER。
- **Acceptance:** Day 90 gateまでwedge外の記事を新規公開せず、6 assetsでQDSとclick learningを取得する。
- **Confidence:** HIGH
- **Assumption／Unknown:** 検索需要・楽天商品厚みの定量値はPhase 0で仮説検証。
### D-V2-005 — 最初のportfolioは25 assets、Wave 1は6 assetsに固定し、残りは数値gateで解放する。

- **Decision:** 最初のportfolioは25 assets、Wave 1は6 assetsに固定し、残りは数値gateで解放する。
- **Evidence:** AUD-015, AUD-017, AUD-025, WEB-006, WEB-007
- **Rationale:** 25本のauthority mapを設計しつつ、実装・公開を一括量産せず学習単位を小さくできる。
- **Rejected alternatives:** 最初から30〜45本公開 / 1記事だけで終了 / query variantごとの大量ページ
- **Consequences:** portfolio itemごとにrole、route、intent、wave、source SLAを持つ。
- **Migration:** Wave 1→Day 30→Day 90の順で次Waveを判定。
- **Acceptance:** Wave 2以降はexit gateを満たすまでstatus=PLANNED_LOCKED。
- **Confidence:** HIGH
- **Assumption／Unknown:** 実際のquery幅はGSC取得後に統合/追加を判断。
### D-V2-006 — 「国内トップ級」を12/24/36か月の読者判断・検索・送客・確定利益・品質・運営費KPIで定義し、公開コピーには使わない。

- **Decision:** 「国内トップ級」を12/24/36か月の読者判断・検索・送客・確定利益・品質・運営費KPIで定義し、公開コピーには使わない。
- **Evidence:** AUD-017, AUD-025, WEB-006, WEB-013
- **Rationale:** 記事数や主観でなく、取得可能な複数指標とguardrailで事業目標を管理できる。
- **Rejected alternatives:** 検索順位1位だけ / 記事数/生成量 / 売上だけ / 根拠のないNo.1表示
- **Consequences:** KPIはinternal planning hypothesisで、Day 30/90に再設定履歴を残す。
- **Migration:** Phase 0でmetric dictionaryとbaselineを作り、Phase 4以降にmature cohort評価。
- **Acceptance:** 全KPIにformula、source、maturity、unavailable handling、ownerがある。
- **Confidence:** MEDIUM
- **Assumption／Unknown:** 初期baseline不在のため絶対値は仮説。
### D-V2-007 — 公開rendererはself-hosted WordPressを維持し、GitのV2 successor overlayを編集・根拠・検証のsource of truthにする。

- **Decision:** 公開rendererはself-hosted WordPressを維持し、GitのV2 successor overlayを編集・根拠・検証のsource of truthにする。
- **Evidence:** AUD-002, AUD-026, AUD-028, AUD-030
- **Rationale:** 既存URL/Yoast/公開運用を守りながら、structured evidenceと再現可能なdraft packageを実現する最小TCO案。
- **Rejected alternatives:** WordPressのみSoT / Headless WordPress+Next.js / Next.js全面移行 / 現行RAOS全機能完成
- **Consequences:** Git→sealed package→WordPress draftの一方向flowを採用し、public edit driftを検出する。
- **Migration:** Phase 1/2はlocal previewのみ、Phase 3から人間操作で1 URLずつ移行。
- **Acceptance:** 同一inputから同一render digestを生成し、production書込みなしでpreviewできる。
- **Confidence:** HIGH
- **Assumption／Unknown:** live plugin/theme/versionはPhase 0再確認。
### D-V2-008 — V2 successor specificationは`changes/raos-v2/**`と`contracts/raos-v2/**`を正とし、`docs/canonical/**`を変更しない。

- **Decision:** V2 successor specificationは`changes/raos-v2/**`と`contracts/raos-v2/**`を正とし、`docs/canonical/**`を変更しない。
- **Evidence:** AUD-003, AUD-005, AUD-006, AUD-028
- **Rationale:** checksum保護されたv1 authorityを保持しながら、後継設計を独立進化できる。
- **Rejected alternatives:** canonical直接改訂 / 非構造化Markdownだけ / 既存ST-1704出力をそのまま正本化
- **Consequences:** generator ownershipとschema versionが必要。
- **Migration:** V1はread-only reference、V2はexplicit import/adapterを通す。
- **Acceptance:** 禁止path diff 0、V2 manifestで全generated ownerを解決。
- **Confidence:** HIGH
- **Assumption／Unknown:** live repositoryのowner registryはCodex開始時に再確認。
### D-V2-009 — WordPress productionはpublic content、URL、redirect、Yoast metadataのdelivery surfaceに限定し、編集判断の正本にしない。

- **Decision:** WordPress productionはpublic content、URL、redirect、Yoast metadataのdelivery surfaceに限定し、編集判断の正本にしない。
- **Evidence:** AUD-008, AUD-009, AUD-010, AUD-026
- **Rationale:** 手編集driftと根拠切断を防ぎながら既存配信を利用できる。
- **Rejected alternatives:** WordPress画面で全編集 / 自動同期で双方向SoT / production DBを直接読む設計
- **Consequences:** sealed package hashとpublic verification snapshotを保持する。
- **Migration:** 既存記事は一度V2へimportし、人間review後にsuccessor draftを作る。
- **Acceptance:** 公開HTMLのcontent fingerprintがapproved packageと一致、またはDRIFT_BLOCKED。
- **Confidence:** HIGH
- **Assumption／Unknown:** WordPress REST capabilityは別read-only調査。
### D-V2-010 — Next.js/headless public migrationとcustom admin UIはPhase 6までDEFERする。

- **Decision:** Next.js/headless public migrationとcustom admin UIはPhase 6までDEFERする。
- **Evidence:** AUD-030, AUD-023, AUD-028
- **Rationale:** 1人運営の初期規模で二重renderer、auth、cache、preview、deployを保有する利益がない。
- **Rejected alternatives:** 今すぐNext.js化 / 完全headless / 管理画面先行
- **Consequences:** 既存web codeはpreview/reference用途に限定し、public authorityを持たせない。
- **Migration:** WordPress限界を計測し、50 pagesまたは週4h超のadmin friction等で再評価。
- **Acceptance:** Phase 0〜5にpublic Next deploy taskが存在しない。
- **Confidence:** HIGH
- **Assumption／Unknown:** 将来のtraffic/運用負荷。
### D-V2-011 — 公開claimをA=公式事実、B=第三者実測、C=利用者傾向、D=編集判断、UNKNOWN=未確認に型付けし、初期V2はA/D/UNKNOWNだけを許可する。

- **Decision:** 公開claimをA=公式事実、B=第三者実測、C=利用者傾向、D=編集判断、UNKNOWN=未確認に型付けし、初期V2はA/D/UNKNOWNだけを許可する。
- **Evidence:** AUD-020, AUD-018, WEB-006
- **Rationale:** 商品事実と判断を分離し、実機やreview evidenceのないB/Cを誤用しない。
- **Rejected alternatives:** 全文章を同じ事実扱い / AI confidence score / 競合記事をB/C根拠にする
- **Consequences:** claim-source binding、表示label、validatorが必須。
- **Migration:** 既存記事の各文をclaim unitへ変換する。
- **Acceptance:** 公開claim 100%がtype、source/logic、checked_at、freshnessを持つ。
- **Confidence:** HIGH
- **Assumption／Unknown:** 将来B/C導入は別evidence contract。
### D-V2-012 — 商品事実の根拠はメーカー・行政・航空会社・許可された楽天data等の一次情報に限定し、競合はUX研究だけに使う。

- **Decision:** 商品事実の根拠はメーカー・行政・航空会社・許可された楽天data等の一次情報に限定し、競合はUX研究だけに使う。
- **Evidence:** AUD-018, AUD-024, WEB-001, WEB-005
- **Rationale:** 一次情報だけで成立するwedgeを選んだため、二次情報依存を避けられる。
- **Rejected alternatives:** 競合claimの再利用 / marketplace titleだけで仕様確定 / review本文の収集
- **Consequences:** source allowlist、robots/terms確認、snapshot policyが必要。
- **Migration:** source registryへtier、publisher、effective date、capture hashを追加。
- **Acceptance:** A claimに許可外source 0、競合URLがproduct claim relationに出現しない。
- **Confidence:** HIGH
- **Assumption／Unknown:** メーカーpageの保存許容はsource別policyで確認。
### D-V2-013 — 実機試験・所有・使用体験を基本戦略に含めず、未実施を結論前に明示する。

- **Decision:** 実機試験・所有・使用体験を基本戦略に含めず、未実施を結論前に明示する。
- **Evidence:** AUD-020, AUD-024
- **Rationale:** ユーザー固定条件を守り、操作性・耐久性・静音性等を経験したように書かない。
- **Rejected alternatives:** 擬似体験文 / 第三者reviewを自分の体験として要約 / 実機購入を前提化
- **Consequences:** recommendationはcompatibility/declared specs/trade-offに限定。
- **Migration:** templateとlintでhands-on languageをblock。
- **Acceptance:** 禁止語/意味検査とhuman reviewでfalse experience claim 0。
- **Confidence:** HIGH
- **Assumption／Unknown:** なし。
### D-V2-014 — 推薦はhard eligibility後に非財務fit scoreで並べ、公開面では点数を見せず条件別結論を示す。

- **Decision:** 推薦はhard eligibility後に非財務fit scoreで並べ、公開面では点数を見せず条件別結論を示す。
- **Evidence:** AUD-020, AUD-025, WEB-006
- **Rationale:** 適合しない商品を高得点化せず、推薦理由を説明可能にする。
- **Rejected alternatives:** 総合1位 / commission/EPC順 / 人気順 / AI主観点数
- **Consequences:** hard filter=identity/evidence/rule/availability、fit weightsをversion管理する。
- **Migration:** 既存3モデル記事を条件別pickへ再計算。
- **Acceptance:** 財務入力を変えても推薦順が不変、同一入力で決定的。
- **Confidence:** HIGH
- **Assumption／Unknown:** fit weightはDay 30 interviewで再校正可能。
### D-V2-015 — business scoreは記事投資判断だけに使い、商品推薦score/順序へ接続しない。

- **Decision:** business scoreは記事投資判断だけに使い、商品推薦score/順序へ接続しない。
- **Evidence:** AUD-017, AUD-025
- **Rationale:** 収益学習は必要だが読者推薦の独立性を守る。
- **Rejected alternatives:** 高料率商品を上位 / EPCをproduct scoreへ加算 / 収益データを公開ranking化
- **Consequences:** コード・schema・testでdataflowを分離。
- **Migration:** 既存finance_signal_policyをV2 invariantへ。
- **Acceptance:** finance fixtureを変更してもarticle product order/hashが不変。
- **Confidence:** HIGH
- **Assumption／Unknown:** なし。
### D-V2-016 — page typeをhome/category/hub、guide、comparison、difference、tool、policyに固定し、各templateの必須block順を定義する。

- **Decision:** page typeをhome/category/hub、guide、comparison、difference、tool、policyに固定し、各templateの必須block順を定義する。
- **Evidence:** AUD-021, AUD-024, WEB-009
- **Rationale:** query intentごとの役割を明確にし、重複・thin affiliate・カニバリを防ぐ。
- **Rejected alternatives:** 全記事同じtemplate / 自由構成のみ / 商品カードの羅列
- **Consequences:** content modelとrenderer contractが増えるがreviewが短縮される。
- **Migration:** 既存記事をcomparison templateへmapping。
- **Acceptance:** 全routeが1 primary intent、1 template、1 parent hub、重複判定を持つ。
- **Confidence:** HIGH
- **Assumption／Unknown:** なし。
### D-V2-017 — AIはsource extraction候補、構造化、差分検出、draft補助に限定し、source採否・事実確定・推薦・公開承認を行わない。

- **Decision:** AIはsource extraction候補、構造化、差分検出、draft補助に限定し、source採否・事実確定・推薦・公開承認を行わない。
- **Evidence:** AUD-020, WEB-008, WEB-007
- **Rationale:** 効率化しつつhallucinationとscaled contentを抑える。
- **Rejected alternatives:** AI自動公開 / AIだけでsource判定 / 記事量KPI
- **Consequences:** provenance、human reviewer、AI correction rate、fail-closed validatorが必要。
- **Migration:** 既存AI統制をwedge最小schemaへ再実装。
- **Acceptance:** 人間review IDなしではPACKAGE_SEALEDへ遷移しない。
- **Confidence:** HIGH
- **Assumption／Unknown:** AI provider/modelはimplementation時に固定せずinterface化。
### D-V2-018 — 公開workflowはDRAFT→EVIDENCE_COMPLETE→HUMAN_REVIEWED→PACKAGE_SEALED→WP_DRAFT_CREATED→HUMAN_PUBLISHED→PUBLIC_VERIFIEDとし、publish capabilityは人間だけに残す。

- **Decision:** 公開workflowはDRAFT→EVIDENCE_COMPLETE→HUMAN_REVIEWED→PACKAGE_SEALED→WP_DRAFT_CREATED→HUMAN_PUBLISHED→PUBLIC_VERIFIEDとし、publish capabilityは人間だけに残す。
- **Evidence:** AUD-016, AUD-026, AUD-003
- **Rationale:** 既存の安全なpublication boundaryを維持しつつ段階移行できる。
- **Rejected alternatives:** 自動公開 / 部分自動公開 / WordPress live editを即正本化
- **Consequences:** 各transitionにhash、actor、timestamp、precondition、rollbackを持つ。
- **Migration:** publication operator概念をV2 schemaへ縮小。
- **Acceptance:** Codex/local testにpublish/schedule/delete/network write pathがない。
- **Confidence:** HIGH
- **Assumption／Unknown:** WordPress draft creationも別承認までNOT_EXECUTED。
### D-V2-019 — Rakuten adapterは2026-07-01 versioned contract、recorded fixture first、live disabled default、credential-free local testとする。

- **Decision:** Rakuten adapterは2026-07-01 versioned contract、recorded fixture first、live disabled default、credential-free local testとする。
- **Evidence:** AUD-019, WEB-005, AUD-003
- **Rationale:** current API contractへ追随しつつprovider requestとsecretを設計から分離する。
- **Rejected alternatives:** 画面scraping / legacy API固定 / liveをCIで実行
- **Consequences:** applicationId/accessKey/affiliateIdはowner-only secret boundary、response provenanceとrate handlingが必要。
- **Migration:** 既存adapterをREWORKしexact version/fields/error taxonomyを追加。
- **Acceptance:** 資格情報なしでcontract suite合格、live flag false、network deniedで成功。
- **Confidence:** HIGH
- **Assumption／Unknown:** live quota/responseは別TSTで確認。
### D-V2-020 — 商品identityはmanufacturer model numberを主キーとし、JAN/itemCode/variant/title tokenを補助証拠にする。

- **Decision:** 商品identityはmanufacturer model numberを主キーとし、JAN/itemCode/variant/title tokenを補助証拠にする。
- **Evidence:** AUD-018, AUD-019, WEB-005
- **Rationale:** 商品・ケース・部品・旧世代・セットの誤同定を防ぐ。
- **Rejected alternatives:** 楽天title完全一致だけ / 商品名のfuzzy matchだけ / shop単位の信頼で代替
- **Consequences:** match resultはEXACT/AMBIGUOUS/REJECTED/UNRESOLVED。AMBIGUOUS以下はCTA不可。
- **Migration:** 既存media registryのrequired/forbidden tokenを一般化。
- **Acceptance:** negative fixtureでアクセサリ・旧型・容量variantをfail closed。
- **Confidence:** HIGH
- **Assumption／Unknown:** JAN非公開商品はmanufacturer model+itemCode+human review。
### D-V2-021 — 計測はSearch Console、privacy-minimized first-party event、成熟した楽天成果reportを採用し、新しいthird-party senderは既定OFFとする。

- **Decision:** 計測はSearch Console、privacy-minimized first-party event、成熟した楽天成果reportを採用し、新しいthird-party senderは既定OFFとする。
- **Evidence:** AUD-017, AUD-027, WEB-014
- **Rationale:** 流入・判断・送客・確定成果を最小dataでつなぎ、1人運営のTCOを抑える。
- **Rejected alternatives:** GA4だけ / cookieなしの過剰fingerprinting / 初期からCDP/dashboard SaaS
- **Consequences:** event allowlist、retention、consent/policy gate、UNAVAILABLE処理が必要。
- **Migration:** 既存Site Kit/GA4は30日parallel observation後にretain/remove判断、勝手に変更しない。
- **Acceptance:** 禁止属性がcollectorへ送られず、production activationはprivacy approvalなしでOFF。
- **Confidence:** MEDIUM_HIGH
- **Assumption／Unknown:** 現行analytics設定と履歴はPhase 0で確認。
### D-V2-022 — Qualified Decision Sessionは「tool result」または「比較/根拠の閲覧後にofficial source・affiliate actionへ進んだsession」と定義する。

- **Decision:** Qualified Decision Sessionは「tool result」または「比較/根拠の閲覧後にofficial source・affiliate actionへ進んだsession」と定義する。
- **Evidence:** AUD-017, AUD-024
- **Rationale:** 単なるpageviewでなく意思決定進捗を測り、記事タイプ間で共通化できる。
- **Rejected alternatives:** 滞在時間だけ / scrollだけ / affiliate clickだけ
- **Consequences:** event sequenceとsession windowを定義。
- **Migration:** semantic markupをevent catalogへ拡張。
- **Acceptance:** synthetic sequenceでQDS=true/falseが決定的、重複排除が再現可能。
- **Confidence:** MEDIUM
- **Assumption／Unknown:** Day 30 UATで閾値を再確認。
### D-V2-023 — 成果帰属はDIRECT_PROVIDER、CLICK_COHORT、UNATTRIBUTED_PROGRAMの3分類とし、provider keyがない記事別確定報酬を発明しない。

- **Decision:** 成果帰属はDIRECT_PROVIDER、CLICK_COHORT、UNATTRIBUTED_PROGRAMの3分類とし、provider keyがない記事別確定報酬を発明しない。
- **Evidence:** AUD-025, AUD-027
- **Rationale:** 楽天reportの粒度に応じて正確さを保ち、誤った記事別EPCを防ぐ。
- **Rejected alternatives:** last-clickを自前推定 / program totalを記事へ按分 / 発生報酬を確定扱い
- **Consequences:** maturity date、currency、source hash、row count、provider total reconciliationが必要。
- **Migration:** owner-private import interfaceをV2 schemaへ。
- **Acceptance:** unattributed totalがarticle metricに流入しないcontract test。
- **Confidence:** HIGH
- **Assumption／Unknown:** 現行provider exportのdirect key可否。
### D-V2-024 — 月次確定貢献利益をcash版とeconomic版に分け、economic版は確定報酬−変動費−人間時間×内部時給で計算する。

- **Decision:** 月次確定貢献利益をcash版とeconomic版に分け、economic版は確定報酬−変動費−人間時間×内部時給で計算する。
- **Evidence:** AUD-025
- **Rationale:** 1人運営の機会費用を含む持続性と現金採算を混同しない。
- **Rejected alternatives:** 発生報酬ベース / 売上/クリックだけ / 人件費を常に0
- **Consequences:** 初期内部時給は仮説¥3,000/h、owner実績で再設定。
- **Migration:** production time ledgerとmonthly reportを作る。
- **Acceptance:** pending/immature outcomeを除外し、formula/version/sourceが監査可能。
- **Confidence:** MEDIUM
- **Assumption／Unknown:** ownerの実際の時間価値。
### D-V2-025 — 実験は30日、90日、12か月のgateとし、一度に1変数、既存記事改善を新規記事より優先する条件を定義する。

- **Decision:** 実験は30日、90日、12か月のgateとし、一度に1変数、既存記事改善を新規記事より優先する条件を定義する。
- **Evidence:** AUD-025, WEB-006
- **Rationale:** 小標本で因果を誤認せず、制作量より学習速度と利益を最大化する。
- **Rejected alternatives:** 毎週全面改稿 / 同時多変量 / クリックがないだけで即撤退
- **Consequences:** sample不足はUNAVAILABLE/EXTEND、zero扱いしない。
- **Migration:** experiment registryへpre-register。
- **Acceptance:** 実験ごとにhypothesis、primary metric、guardrail、sample/maturity、keep/rollback ruleがある。
- **Confidence:** HIGH
- **Assumption／Unknown:** 初期trafficによる期間延長。
### D-V2-026 — 情報設計は`/carry-on/`をwedge hubとし、`/guides/`、`/comparisons/`、`/differences/`、`/tools/`、`/policy/`へ役割分離する。

- **Decision:** 情報設計は`/carry-on/`をwedge hubとし、`/guides/`、`/comparisons/`、`/differences/`、`/tools/`、`/policy/`へ役割分離する。
- **Evidence:** AUD-008, AUD-010, AUD-021, WEB-009
- **Rationale:** 検索intentとreader journeyを明確にし、homeの空カテゴリを解消する。
- **Rejected alternatives:** 移動/家事/備えの空カテゴリ / date archive中心 / タグの無制限index
- **Consequences:** breadcrumbと内部link graphが必須。
- **Migration:** 既存記事URLは維持、空taxonomyはnavから除外しinventory別にnoindex/redirect。
- **Acceptance:** 全indexable pageがhubから3 click以内、orphan 0、empty indexable archive 0。
- **Confidence:** HIGH
- **Assumption／Unknown:** 既存WordPress taxonomyのlive inventory。
### D-V2-027 — デザインはpaper/indigo/warm accentを維持しつつ、system font、読書幅720px、wide 1120px、mobile-first component hierarchyへ再定義する。

- **Decision:** デザインはpaper/indigo/warm accentを維持しつつ、system font、読書幅720px、wide 1120px、mobile-first component hierarchyへ再定義する。
- **Evidence:** AUD-011, AUD-012, AUD-013, AUD-014, AUD-021, AUD-022
- **Rationale:** ブランド資産を残し、現行の過大な空白・小さい本文・cookie banner占有・比較可読性を改善する。
- **Rejected alternatives:** 競合copy/CSS模倣 / 画像主体hero / 装飾優先の雑誌layout
- **Consequences:** token contractとvisual regressionが必要。
- **Migration:** 新child theme/blocksをroute単位で適用。
- **Acceptance:** 390/768/1440、200% zoom、long text、no imageで情報階層と機能が保たれる。
- **Confidence:** HIGH
- **Assumption／Unknown:** 実機端末のfont renderingはUAT。
### D-V2-028 — WCAG 2.2 AAを目標とし、CWV p75と厳格なpage budgetを受入条件にする。

- **Decision:** WCAG 2.2 AAを目標とし、CWV p75と厳格なpage budgetを受入条件にする。
- **Evidence:** AUD-021, AUD-022, WEB-012, WEB-015
- **Rationale:** モバイル購買支援の利用性と検索品質を同時に担保する。
- **Rejected alternatives:** desktop優先 / 画像/JS無制限 / 自動auditだけでconformance宣言
- **Consequences:** keyboard、screen reader smoke、focus、reflow、contrast、no-JS、field dataを分離評価。
- **Migration:** Phase 2 local budget、Phase 3/4 field validation。
- **Acceptance:** LCP≤2.5s、INP≤200ms、CLS≤0.1 p75を目標、article JS≤60KB gzip、CSS≤40KB gzip、page≤1.2MB。
- **Confidence:** HIGH
- **Assumption／Unknown:** field CWVは公開後のみ取得可能。
### D-V2-029 — 画像は許可された楽天API画像または自作の非商品diagramのみ。商品画像不足時は捏造せずneutral placeholderで公開可否を明示する。

- **Decision:** 画像は許可された楽天API画像または自作の非商品diagramのみ。商品画像不足時は捏造せずneutral placeholderで公開可否を明示する。
- **Evidence:** AUD-019, WEB-001, WEB-005
- **Rationale:** 著作権・規約・商品identityを守り、画像不足を虚偽で埋めない。
- **Rejected alternatives:** メーカー画像転載 / 競合画像 / 生成AIで商品外観を再現 / 無断crop/overlay
- **Consequences:** provenance、exact product binding、no modification、alt、expiryが必要。
- **Migration:** 現行PENDING mediaはpublication blockerのまま。
- **Acceptance:** 商品画像はsource URL/itemCode/hash/check timeを持ち、identity unresolvedならCTAもblock。
- **Confidence:** HIGH
- **Assumption／Unknown:** 各provider image保存・cache条件はrelease時再確認。
### D-V2-030 — freshness SLAは航空ルール30日、高risk安全情報30日、商品仕様90日、offer/在庫24時間、一般編集判断180日とする。

- **Decision:** freshness SLAは航空ルール30日、高risk安全情報30日、商品仕様90日、offer/在庫24時間、一般編集判断180日とする。
- **Evidence:** AUD-018, AUD-019, WEB-016, WEB-017, WEB-018, WEB-019
- **Rationale:** 変更コストと誤認リスクに応じて更新頻度を変える。
- **Rejected alternatives:** 全情報を毎日 / 公開日だけ表示 / 期限切れでも無表示
- **Consequences:** claim単位next_review_at、stale state、public banner/CTA blockが必要。
- **Migration:** 既存source checked dateをnormalize。
- **Acceptance:** 期限超過high-risk claimは公開buildをfail、offer staleは価格非表示/CTA再確認へ。
- **Confidence:** MEDIUM_HIGH
- **Assumption／Unknown:** 実際のchange frequencyで90日後に調整。
### D-V2-031 — URL移行はkeep/redirect/noindex/removeをinventory単位で決め、既存`/carry-on-suitcase-comparison/`を維持する。

- **Decision:** URL移行はkeep/redirect/noindex/removeをinventory単位で決め、既存`/carry-on-suitcase-comparison/`を維持する。
- **Evidence:** AUD-009, AUD-010, WEB-009
- **Rationale:** 唯一の公開記事とcanonical equityを守り、空/thin archiveを整理する。
- **Rejected alternatives:** slug一括変更 / 全旧URLをhomeへredirect / 無計画404
- **Consequences:** redirect chain/loop、canonical、sitemap、internal link testが必要。
- **Migration:** Phase 0 map→local simulation→human production apply→public verify→rollback。
- **Acceptance:** redirect hop≤1、loop 0、canonical self/target一致、sitemapにindexable final URLのみ。
- **Confidence:** HIGH
- **Assumption／Unknown:** live URL inventoryは再取得。
### D-V2-032 — 既存資産をKEEP/REWORK/MIGRATE/RETIRE/DEFERへ分類し、security/publication/evidence/rollback invariantをKEEPする。

- **Decision:** 既存資産をKEEP/REWORK/MIGRATE/RETIRE/DEFERへ分類し、security/publication/evidence/rollback invariantをKEEPする。
- **Evidence:** AUD-003, AUD-005, AUD-026, AUD-027, AUD-028
- **Rationale:** sunk costで全維持せず、検証済み安全境界も捨てない。
- **Rejected alternatives:** 全部残す / 全部捨てる
- **Consequences:** deprecation ledgerと二release observationが必要。
- **Migration:** 初回PRは削除なし、wrapper/deprecation noticeのみ。
- **Acceptance:** 各対象にowner、replacement、usage evidence、removal gate、rollbackがある。
- **Confidence:** HIGH
- **Assumption／Unknown:** live code usageはCodex Phase 0で再計測。
### D-V2-033 — 最初のintegration PRはPhase 0〜2のoffline vertical sliceとPhase 3以降のdisabled contract/runbookだけに限定する。

- **Decision:** 最初のintegration PRはPhase 0〜2のoffline vertical sliceとPhase 3以降のdisabled contract/runbookだけに限定する。
- **Evidence:** AUD-002, AUD-003, AUD-028
- **Rationale:** 読者が使えるchecker+guide+比較previewを先に完成し、巨大基盤追加とexternal riskを避ける。
- **Rejected alternatives:** 全Phase一括実装 / architectureだけのPR / production migration同梱
- **Consequences:** isolated worktree、allowed path、one PR、no destructive deletion。
- **Migration:** live HEADからbranchを作り、current dirty pathを触らない。
- **Acceptance:** local preview、contract/unit/browser/a11y/SEO/security/rollback testがgreen、external register全NOT_EXECUTED。
- **Confidence:** HIGH
- **Assumption／Unknown:** 実装開始時HEAD/branch/path availability。
### D-V2-034 — 公開、deployment、credential、live provider request/write、規約同意、支出、production migration、不可逆削除は設計/ローカル実装から分離し人間承認必須とする。

- **Decision:** 公開、deployment、credential、live provider request/write、規約同意、支出、production migration、不可逆削除は設計/ローカル実装から分離し人間承認必須とする。
- **Evidence:** AUD-001, AUD-003, AUD-016, AUD-026
- **Rationale:** ユーザー要求とrepository安全境界を維持する。
- **Rejected alternatives:** 暗黙承認 / 設計packageを実行権限とみなす / local evidenceをproduction evidenceと呼ぶ
- **Consequences:** external actions register、approval record、NOT_EXECUTED reportingが必要。
- **Migration:** 各Phase exit reportでexternal未実行を明示。
- **Acceptance:** package/初回PRにsecret値、external write、publish/deploy、費用発生がない。
- **Confidence:** HIGH
- **Assumption／Unknown:** なし。
