# Migration Roadmap and Backlog

## 1. Migration strategy

The migration is **reversible, URL-by-URL and evidence-gated**. P0–P2 can be completed without touching production. P3 is the first external/public phase and migrates exactly one URL. P4 expands only through Wave gates. P5 decides economics after mature provider outcomes. P6 permits at most one adjacent category.

### Critical path

```text
P0 current state / URL / metrics / rollback
  -> P1 V2 contracts / design system / data model
    -> P2 offline vertical slice + first integration PR
      -> P3 human one-URL migration + public verify + rollback proof
        -> P4 Wave 1 / Day30 / Day90 gated portfolio
          -> P5 mature outcomes / economics / continuation
            -> P6 maximum-one adjacent category
```

No later phase may be declared complete because code exists. Each phase requires its own evidence class and exit gate. Missing provider data produces `UNAVAILABLE` or extends observation; it does not create a positive or negative market conclusion.

## 2. Phase plans

## P0 — 現状・計測・バックアップ・URL inventory固定

- **Outcome:** 変化させずに現在地と回復点を確定する。
- **In scope:** live repository read-only preflight、packet integrity、public URL/canonical/robots/sitemap、metric dictionary、asset disposition、backup/rollback runbook。
- **Out of scope:** code feature、production backup実行、credentials、analytics export、WordPress変更。
- **Dependencies:** none
- **Affected subsystems:** Git/worktree、WordPress public capture、Yoast metadata、analytics definitions、governance。
- **Acceptance criteria:** R-V2-001〜004、035、036のP0部分。URLにunknownを残す場合はowner/due/safe defaultを付ける。
- **Automated tests:** T-V2-001〜007、T-V2-051。
- **Visual／accessibility checks:** 既存home/articleを390/768/1440でbaseline capture。accessibility conformanceは未主張。
- **Analytics evidence:** 現在取得可能なproviderを列挙。値未取得はUNAVAILABLE。
- **Failure／rollback behavior:** read-onlyのため変更なし。worktree作成前矛盾は停止。
- **Cost ceiling:** 16 human-equivalent hours、external spend ¥0。
- **Exit gate:** URL・metric・asset・rollback inventoryがcompleteかunknown owner付き。
- **Codex-allowed local actions:** read、hash、parse、local report、isolated worktree。
- **Human/external boundary:** production export、Search Console/analytics/Rakuten report取得は人間。
## P1 — 後継product specificationとdesign system

- **Outcome:** V2のdata、route、template、token、state、interfaceをmachine-readableに固定する。
- **In scope:** successor overlay、schemas、generator ownership、design tokens、IA、claim/source/product/rule/article contracts。
- **Out of scope:** public rendering変更、live provider、production write。
- **Dependencies:** P0 exit。
- **Affected subsystems:** contracts、changes/raos-v2、generator、domain models、design system。
- **Acceptance criteria:** R-V2-005〜012、017のcontract部分。実装者にA/B選択を残さない。
- **Automated tests:** T-V2-007〜019。
- **Visual／accessibility checks:** wireframe/token review、contrast計算、component state inventory。
- **Analytics evidence:** event namesとmetric relationだけを定義し送信しない。
- **Failure／rollback behavior:** overlay directoryを未参照に戻せばv1/publicに影響なし。
- **Cost ceiling:** 40 hours ceiling、external spend ¥0。
- **Exit gate:** schema/traceability/drift test green、design review critical issue 0。
- **Codex-allowed local actions:** schema/generator/docs/testsのlocal implementation。
- **Human/external boundary:** none required。
## P2 — 1カテゴリ・数記事のvertical slice

- **Outcome:** checker、rule guide、既存comparison V2 preview、sealed packageをofflineで利用・検証できる。
- **In scope:** recorded sources、decision engine、templates、local preview、Rakuten recorded adapter、quality/freshness/SEO/event semantic markup、tests。
- **Out of scope:** WordPress write/publish、live Rakuten、analytics transmission、production deploy。
- **Dependencies:** P1 exit。
- **Affected subsystems:** domain/application/ports/adapters、web UI、rendering、SEO、publication package、tests。
- **Acceptance criteria:** R-V2-013〜029、033〜036のP2部分。first integration PR scope。
- **Automated tests:** T-V2-020〜051、make generate/check/fast/final。
- **Visual／accessibility checks:** 390/768/1440、200% zoom、keyboard、forced colors、reduced motion、screen reader smoke、no-JS。
- **Analytics evidence:** local sinkだけ。QDS synthetic event evidence。
- **Failure／rollback behavior:** overlay/feature flag OFF、public unchanged。
- **Cost ceiling:** 80 hours ceiling、external spend ¥0。
- **Exit gate:** local vertical slice and all focused/final tests green; external register全NOT_EXECUTED。
- **Codex-allowed local actions:** code/test/fixture/local browser/PR。
- **Human/external boundary:** publish/deploy/credential/provider requestは不可。
## P3 — 既存URLを守った公開面移行

- **Outcome:** 人間承認で1 URLだけV2へ移行し、public verify/rollbackを実証する。
- **In scope:** deployable child theme/block artifact、sealed draft payload、human backup/deploy/draft/publish、public verification。
- **Out of scope:** 一括移行、auto publication、wedge外URL。
- **Dependencies:** P2 integration green、owner approval、backup、privacy/legal gate。
- **Affected subsystems:** WordPress/theme/Yoast/publication/redirect/analytics consent。
- **Acceptance criteria:** R-V2-024/025/028/029/033/034/036のproduction gate。
- **Automated tests:** T-V2-035〜046 + production smoke read-only。
- **Visual／accessibility checks:** 実public 390/768/1440、keyboard、mobile consent banner、field CWV collection開始。
- **Analytics evidence:** approved event only。未承認ならOFFで公開しmetric UNAVAILABLE。
- **Failure／rollback behavior:** 事前export、old content hash/theme version/redirect mapへ復元。trigger=critical defect、canonical/index error、CTA binding error。
- **Cost ceiling:** 20 hours + external spend ¥0 default。
- **Exit gate:** 1 URL PUBLIC_VERIFIED、critical 0、rollback rehearsal evidence、7日安定。
- **Codex-allowed local actions:** artifact/dry-run/reportのみ。
- **Human/external boundary:** backup/deploy/WP write/publish/redirect/analytics activationは人間。
## P4 — 20〜30記事と検索・送客の検証

- **Outcome:** Wave 1を公開し、gate通過分だけ最大25 assetsへ拡大する。
- **In scope:** Wave 1〜4 gated packages、GSC/event monitoring、freshness/link monitor、existing page improvement。
- **Out of scope:** 別wedge、YouTube/SNS大量展開、paid provider。
- **Dependencies:** P3 7-day stable。
- **Affected subsystems:** content operations、search analytics、affiliate click、freshness。
- **Acceptance criteria:** 重大欠陥0、broken affiliate link 0、source freshness、QDS/AOC取得可能性、Day30/90 gate。
- **Automated tests:** T-V2-014、024〜026、033〜036、044〜046、050〜051を各release。
- **Visual／accessibility checks:** 全template representative page regression、field CWV p75。
- **Analytics evidence:** GSC + approved first-party。rewardはまだmaturity分類。
- **Failure／rollback behavior:** article単位のprevious sealed packageへ戻す。低performanceだけで即削除しない。
- **Cost ceiling:** 120 hours ceiling until Day90、external spend ¥0。
- **Exit gate:** Day90 CONTINUE/REPAIR/RETREAT decision。25本一括は不可。
- **Codex-allowed local actions:** successor package、tests、analysis。
- **Human/external boundary:** 各public actionは人間。
## P5 — 収益・更新費・カテゴリ継続判断

- **Outcome:** 成熟した確定成果と人間時間を使い、wedgeの採算と継続方式を決める。
- **In scope:** owner-private Rakuten import、reconciliation、EPC/RPM/profit/payback、update cost、12mo gate。
- **Out of scope:** 収益によるproduct rank変更、未成熟成果の確定扱い。
- **Dependencies:** mature provider period、P4 measurement integrity。
- **Affected subsystems:** finance/attribution/operations。
- **Acceptance criteria:** R-V2-030〜032、036。DIRECT/COHORT/UNATTRIBUTEDを分離。
- **Automated tests:** T-V2-047〜051。
- **Visual／accessibility checks:** public UI変更なし。
- **Analytics evidence:** confirmed mature only。
- **Failure／rollback behavior:** finance importはimmutable source hashとrebuild可能。誤importはsuperseding record。
- **Cost ceiling:** 16 hours/report cycle、external spend ¥0。
- **Exit gate:** CONTINUE/IMPROVE/CONSOLIDATE/RETIREの1決定と根拠。
- **Codex-allowed local actions:** sanitized owner-private import/test/report。
- **Human/external boundary:** provider exportは人間、秘密/個人dataはrepoへ入れない。
## P6 — 数値gate通過後のみ拡大

- **Outcome:** 隣接カテゴリ最大1つを同じdecision systemで検証するか、wedge深掘りを選ぶ。
- **In scope:** candidate rescoring、portfolio overlap、TCO、source/safety review、deprecation removal proposal。
- **Out of scope:** 総合メディア化、複数カテゴリ同時、auto publication、irreversible deletion。
- **Dependencies:** P5 gate通過、12mo品質guardrail。
- **Affected subsystems:** strategy、content graph、architecture/deprecation。
- **Acceptance criteria:** 選択1案、rejected alternatives、budget、rollback、success/exit gate。
- **Automated tests:** traceability、route/cannibalization、security regression、T-V2-051。
- **Visual／accessibility checks:** new category componentsを既存system内で検証。
- **Analytics evidence:** incremental category cohortを別集計。
- **Failure／rollback behavior:** new category nav/indexをfeature flagで戻せる。asset deletionは二release後別承認。
- **Cost ceiling:** planning 16h、実装は別approved ceiling。
- **Exit gate:** 次successor design decision。
- **Codex-allowed local actions:** research/design/local prototype。
- **Human/external boundary:** publication/spend/removalは人間。


## 3. First integration PR boundary

### Included

- P0 live preflight/inventory/reporting.
- P1 versioned V2 successor contracts and generator ownership.
- P2 recorded-source carry-on checker, basic rules guide, existing comparison migration preview, method/policy, deterministic selection, recorded Rakuten adapter, media/SEO/freshness/publication package/event semantic contracts.
- Full local tests, browser/visual/a11y/security/rollback simulation.
- P3–P6 contracts/runbooks only, disabled by default.
- Deprecation ledger with no removals.

### Excluded

- WordPress API/browser write, draft creation, theme deployment, publish/schedule/update/delete.
- Credentials or secret store access.
- Live Rakuten API, live analytics sender, Search Console/Rakuten export access.
- Production redirect/canonical/sitemap changes.
- Any new paid service or expenditure.
- Destructive file/data deletion, irreversible migration or automatic/partial publication.

### Proposed repository workflow

1. At `/home/minami/rakuten`, read current root/nearest `AGENTS.md` and record current branch/HEAD/status/diffstat.
2. Verify the proposed branch/worktree do not already exist. If they do, stop before changes and report exact collision.
3. From current live HEAD, create isolated worktree `/home/minami/rakuten-raos-v2` on `codex/raos-v2-vertical-slice` without altering the original dirty worktree.
4. Implement dependency order B-V2-001 through B-V2-034 only.
5. Use generator owner for all generated outputs.
6. Run focused tests during development and repository-standard `make setup/generate/check/fast/final` at required gates.
7. Checkpoint on the dedicated branch, then create/update one integration PR containing all related RAOS V2 work. Do not split by Story ID.
8. PR report names related decisions/requirements, local evidence, rollback, residual assumptions and all external/live actions as NOT_EXECUTED.

This is an implementation workflow, not authority to merge/deploy/publish beyond current repository rules. The implementation prompt directs Codex to obey the live `AGENTS.md` if it has changed.

## 4. Requirement catalog

| Requirement | Phase | Title | Decision links | Acceptance |
| --- | --- | --- | --- | --- |
| R-V2-001 | P0 | immutable pathと既存dirty変更を保護する | D-V2-001, D-V2-008, D-V2-033, D-V2-034 | `docs/canonical/**`,`docs/upstream/**`,`zip/**` diff 0。reset/clean/delete 0。 |
| R-V2-002 | P0 | 実装開始時にroot AGENTS、HEAD、branch、status、generator ownershipをlive再確認する | D-V2-008, D-V2-033 | 監査snapshotとの差を記録し、矛盾時は変更前にescalate。 |
| R-V2-003 | P0 | public URL/canonical/robots/sitemap/status inventoryとrollback snapshotを固定する | D-V2-001, D-V2-031 | 全URLにkeep/redirect/noindex/remove/unknownと証拠時刻がある。 |
| R-V2-004 | P0 | metric dictionary、data source、maturity、baseline/unavailableを定義する | D-V2-006, D-V2-021, D-V2-022, D-V2-023, D-V2-024 | 全KPIが計算可能またはUNAVAILABLE理由を返す。 |
| R-V2-005 | P1 | V2 successor product specificationをversioned schemaで管理する | D-V2-002, D-V2-003, D-V2-004, D-V2-005, D-V2-008 | wedge、audience、JTBD、portfolio、gateがmachine-readable。 |
| R-V2-006 | P1 | design token、layout、responsive、state contractを固定する | D-V2-027, D-V2-028 | token schemaとcomponent state matrixがvalidation可能。 |
| R-V2-007 | P1 | IA、route role、taxonomy、breadcrumb、internal link contractを固定する | D-V2-016, D-V2-026, D-V2-031 | indexable routeにprimary intent/parent hub/templateがある。 |
| R-V2-008 | P1 | Claim schemaとA/D/UNKNOWN validatorを実装する | D-V2-011, D-V2-012, D-V2-013 | unsupported claim、期限切れhigh-risk、B/Cをfail closed。 |
| R-V2-009 | P1 | Source registryにtier、publisher、URL、effective/checked/next review、capture provenanceを持たせる | D-V2-012, D-V2-030 | A claimから一次sourceへ一意に追跡可能。 |
| R-V2-010 | P1 | Product model/variant/identity schemaを固定する | D-V2-019, D-V2-020, D-V2-029 | model number、dimensions、weight、state、identity evidenceが型検証。 |
| R-V2-011 | P1 | Airline rule setをeffective date・route/aircraft/fare variant付きで表現する | D-V2-004, D-V2-030 | 曖昧なruleはUNKNOWNを返し、一般化しない。 |
| R-V2-012 | P1 | Article definitionと6 templateのrequired block orderを固定する | D-V2-016, D-V2-017 | 各articleがtemplate contractを満たす。 |
| R-V2-013 | P2 | carry-on size checkerをclient-side/no personal transmissionで実装する | D-V2-003, D-V2-004, D-V2-022, D-V2-028 | 入力→PASS/FAIL/UNKNOWNと根拠、checked date、official linkを返す。 |
| R-V2-014 | P2 | basic rule guideをreader-first templateで実装する | D-V2-003, D-V2-016 | 問題→30秒結論→rule→例→unknown→source→next action。 |
| R-V2-015 | P2 | 既存comparison URLをV2 templateへlocal migrationする | D-V2-014, D-V2-016, D-V2-031 | URL維持、3 model scope、fit/non-fit/unknown、no hands-on。 |
| R-V2-016 | P2 | difference templateをcomparisonと重複しないquery roleで実装する | D-V2-016 | 対象差分と選択分岐だけを扱う。 |
| R-V2-017 | P2 | hard eligibilityとfit scoreを決定的に実装する | D-V2-014, D-V2-020 | 非適合/identity unresolvedを除外し、同一inputで同一order。 |
| R-V2-018 | P2 | business scoreを推薦dataflowから物理的に分離する | D-V2-015 | finance input変更でrender/recommendation hash不変。 |
| R-V2-019 | P2 | AI draft provenanceとhuman review bindingを実装する | D-V2-017, D-V2-018 | reviewer/version/correction countなしでseal不可。 |
| R-V2-020 | P2 | content quality gateを実装する | D-V2-011, D-V2-012, D-V2-013, D-V2-016, D-V2-017 | source、scope、disclosure、trade-off、unknown、no false experienceを検証。 |
| R-V2-021 | P2 | freshness stateとSLA job contractを実装する | D-V2-030 | FRESH/DUE/SOFT_STALE/HARD_STALE/UNKNOWNを決定。 |
| R-V2-022 | P2 | SEO metadata、canonical、robots、sitemap、structured data contractを実装する | D-V2-016, D-V2-026, D-V2-031 | visible contentとmetadata/JSON-LD一致、unsupported schema 0。 |
| R-V2-023 | P2 | hash-bound publication packageを生成する | D-V2-007, D-V2-009, D-V2-018 | input/output/source/review hashとtarget routeをseal。 |
| R-V2-024 | P2/P3 | WordPress draft adapterをdisabled defaultで定義する | D-V2-009, D-V2-018, D-V2-034 | localではpayload previewのみ、network/write capabilityなし。 |
| R-V2-025 | P2/P3 | migration/rollback manifestを生成する | D-V2-001, D-V2-031 | before/after URL、content hash、restore step、failure conditionを持つ。 |
| R-V2-026 | P2 | Rakuten 2026-07-01 recorded fixture adapterを実装する | D-V2-019 | credential/networkなしでcurrent schemaをparse。 |
| R-V2-027 | P2 | exact product identity matchingとnegative casesを実装する | D-V2-020 | accessory/old generation/set/variant ambiguityをreject。 |
| R-V2-028 | P2/P3 | media provenance registryとfail-closed display policyを実装する | D-V2-029 | source/itemCode/hash/alt/checked_atなしの商品画像をblock。 |
| R-V2-029 | P2/P3 | privacy-minimized event catalogとcollector contractを実装する | D-V2-021, D-V2-022 | allowlist外attribute送信不可、production default OFF。 |
| R-V2-030 | P4/P5 | provider outcome import/reconciliationをowner-private境界で実装する | D-V2-023 | source hash/period/currency/rows/provider total/maturityを検証。 |
| R-V2-031 | P5 | cash/economic contribution profit calculationを実装する | D-V2-024 | pending除外、internal rate version、article/category/program scopeを分離。 |
| R-V2-032 | P4/P5 | 30/90/12mo experiment and gate reportを生成する | D-V2-005, D-V2-006, D-V2-025 | one-variable、sample/maturity、keep/rollback/extendが明示。 |
| R-V2-033 | P2/P3 | browser/visual/a11y/performance matrixを実装する | D-V2-027, D-V2-028 | 390/768/1440、200% zoom、keyboard、screen reader smoke、budgetを検証。 |
| R-V2-034 | P0-P3 | security/auth/network/publication invariantを継承する | D-V2-018, D-V2-019, D-V2-034 | secret 0、denied network、publish capability 0、public/internal isolation。 |
| R-V2-035 | P0-P6 | deprecation ledgerを作り初回PRでは削除しない | D-V2-010, D-V2-032, D-V2-033 | 各assetにdisposition/replacement/usage/removal gate/rollback。 |
| R-V2-036 | P0-P6 | 各Phaseのevidence reportとexternal NOT_EXECUTEDを出力する | D-V2-006, D-V2-033, D-V2-034 | local/formal/staging/prodを混同せず、exit/rollback/gapを報告。 |

## 5. Dependency-complete backlog

| Backlog | Phase | Task | Depends on | Requirements | Exact output | Hours ceiling |
| --- | --- | --- | --- | --- | --- | --- |
| B-V2-001 | P0 | live repository preflightとisolated worktree safety check | none | R-V2-001, R-V2-002, R-V2-034 | preflight-report.json | 2 |
| B-V2-002 | P0 | audit packet integrity/source inventory再検証 | B-V2-001 | R-V2-002 | source-audit-report.json | 2 |
| B-V2-003 | P0 | public URL/canonical/status inventory | B-V2-001 | R-V2-003 | public-url-inventory.yaml | 4 |
| B-V2-004 | P0 | WordPress/Yoast/theme/plugin read-only inventory plan | B-V2-003 | R-V2-003, R-V2-024 | production-observation-plan.md | 2 |
| B-V2-005 | P0 | analytics/GSC/Rakuten metric dictionary and unavailable policy | B-V2-001 | R-V2-004 | metric-dictionary.yaml | 4 |
| B-V2-006 | P0 | existing asset KEEP/REWORK/MIGRATE/RETIRE/DEFER ledger | B-V2-001 | R-V2-035 | deprecation-ledger.yaml | 4 |
| B-V2-007 | P0 | existing five-article pilot import/status reconciliation | B-V2-002 | R-V2-003, R-V2-035 | pilot-reconciliation.yaml | 3 |
| B-V2-008 | P0 | backup/restore/redirect simulation contract | B-V2-003 | R-V2-025 | rollback-contract.yaml | 3 |
| B-V2-009 | P0 | Phase 0 evidence and owner external-action packet | B-V2-003, B-V2-005, B-V2-006, B-V2-008 | R-V2-036 | phase-0-report.md | 2 |
| B-V2-010 | P1 | V2 product specification schema/generator registration | B-V2-009 | R-V2-005, R-V2-001 | product-spec.v2.yaml + generator owner | 6 |
| B-V2-011 | P1 | IA/route/taxonomy/internal-link contract | B-V2-010 | R-V2-007 | route-registry.v2.yaml | 5 |
| B-V2-012 | P1 | design token and component-state contracts | B-V2-010 | R-V2-006 | design-tokens.v2.json + component-states.yaml | 6 |
| B-V2-013 | P1 | claim/source schema and validators | B-V2-010 | R-V2-008, R-V2-009 | claim/source contracts | 8 |
| B-V2-014 | P1 | product/variant/identity schema | B-V2-010 | R-V2-010 | product-model contract | 6 |
| B-V2-015 | P1 | airline rule-set/effective-date schema | B-V2-013 | R-V2-011 | airline-rule-set contract | 6 |
| B-V2-016 | P1 | article/template schema and block-order contracts | B-V2-011, B-V2-013 | R-V2-012 | article-definition contract | 6 |
| B-V2-017 | P1 | publication/analytics/freshness interface contracts | B-V2-013, B-V2-016 | R-V2-021, R-V2-023, R-V2-029 | interface contracts | 6 |
| B-V2-018 | P1 | Phase 1 generated design review and drift check | B-V2-012, B-V2-014, B-V2-015, B-V2-016, B-V2-017 | R-V2-036 | phase-1-report.md | 3 |
| B-V2-019 | P2 | recorded official airline rule fixtures | B-V2-015 | R-V2-009, R-V2-011 | recorded source fixtures | 6 |
| B-V2-020 | P2 | carry-on checker decision engine | B-V2-019 | R-V2-013 | pure decision engine | 10 |
| B-V2-021 | P2 | checker UI and no-transmission client behavior | B-V2-020, B-V2-012 | R-V2-013, R-V2-033 | local checker page | 10 |
| B-V2-022 | P2 | basic carry-on rules guide content packet | B-V2-019, B-V2-016 | R-V2-014, R-V2-020 | guide packet | 8 |
| B-V2-023 | P2 | existing public comparison import and claim decomposition | B-V2-007, B-V2-013, B-V2-014 | R-V2-015, R-V2-020 | comparison source packet | 8 |
| B-V2-024 | P2 | hard eligibility and fit scoring engine | B-V2-014, B-V2-015 | R-V2-017 | selection engine | 8 |
| B-V2-025 | P2 | business score isolated module and non-interference proof | B-V2-024 | R-V2-018 | business score module | 5 |
| B-V2-026 | P2 | V2 comparison renderer and product cards | B-V2-023, B-V2-024, B-V2-012 | R-V2-015, R-V2-033 | comparison local preview | 12 |
| B-V2-027 | P2 | difference template skeleton and duplication guard | B-V2-016 | R-V2-016, R-V2-022 | difference preview fixture | 5 |
| B-V2-028 | P2 | AI provenance/human review/content quality gate | B-V2-013, B-V2-016 | R-V2-019, R-V2-020 | review packet + validators | 8 |
| B-V2-029 | P2 | Rakuten 2026-07-01 recorded adapter and identity matcher | B-V2-014 | R-V2-026, R-V2-027 | recorded adapter + negative fixtures | 10 |
| B-V2-030 | P2 | media registry and neutral placeholder policy | B-V2-029, B-V2-012 | R-V2-028 | media contract/preview states | 5 |
| B-V2-031 | P2 | SEO/structured data/freshness/publication package generators | B-V2-021, B-V2-022, B-V2-026, B-V2-028 | R-V2-021, R-V2-022, R-V2-023, R-V2-025 | sealed local vertical slice | 12 |
| B-V2-032 | P2 | event catalog semantic instrumentation with sender OFF | B-V2-017, B-V2-021, B-V2-026 | R-V2-029 | event catalog + local sink | 6 |
| B-V2-033 | P2 | browser/visual/a11y/performance/security test matrix | B-V2-031, B-V2-032 | R-V2-033, R-V2-034 | local evidence bundle | 10 |
| B-V2-034 | P2 | Phase 2 UAT and first integration PR report | B-V2-033 | R-V2-036 | phase-2-report + PR body | 4 |
| B-V2-035 | P3 | production backup/export human runbook | none | R-V2-003, R-V2-025, R-V2-036 | human runbook only | 2 |
| B-V2-036 | P3 | WordPress child theme/block migration package | B-V2-034 | R-V2-006, R-V2-024, R-V2-033 | deployable artifact; no deploy | 12 |
| B-V2-037 | P3 | exact sealed WP draft payload and dry-run diff | B-V2-034 | R-V2-023, R-V2-024 | draft payload preview | 5 |
| B-V2-038 | P3 | production redirect/canonical/sitemap change plan | B-V2-035, B-V2-037 | R-V2-003, R-V2-022, R-V2-025 | human action plan | 5 |
| B-V2-039 | P3 | privacy/legal review packet for event activation | B-V2-032 | R-V2-029, R-V2-036 | owner/counsel review packet | 3 |
| B-V2-040 | P3 | one-URL human migration, public verification and rollback evidence | B-V2-036, B-V2-037, B-V2-038, B-V2-039 | R-V2-024, R-V2-025, R-V2-033, R-V2-034 | external gated evidence | 8 |
| B-V2-041 | P4 | Wave 1 remaining guide/tool publication packages | B-V2-040 | R-V2-014, R-V2-023 | five successor packages | 20 |
| B-V2-042 | P4 | GSC and first-party day-30 observation import | B-V2-040 | R-V2-004, R-V2-029, R-V2-032 | day-30 evidence | 5 |
| B-V2-043 | P4 | broken link/freshness/public defect monitor | B-V2-040 | R-V2-021, R-V2-036 | monitor reports | 8 |
| B-V2-044 | P4 | Wave 2/3 content only after gate | B-V2-041, B-V2-042, B-V2-043 | R-V2-005, R-V2-032 | gated content packages | 40 |
| B-V2-045 | P4 | Day-90 wedge continuation/repair/retreat decision | B-V2-044 | R-V2-032 | day-90 decision record | 4 |
| B-V2-046 | P5 | owner-private Rakuten outcome import and reconciliation | B-V2-045 | R-V2-030 | mature provider evidence | 6 |
| B-V2-047 | P5 | confirmed EPC/RPM/cash/economic contribution report | B-V2-046 | R-V2-031 | monthly unit economics report | 5 |
| B-V2-048 | P5 | article/category payback and 12-month gate | B-V2-047 | R-V2-032 | continue/improve/consolidate/retire decision | 5 |
| B-V2-049 | P6 | adjacent category scoring and maximum-one expansion plan | B-V2-048 | R-V2-005, R-V2-032, R-V2-035 | expansion decision package | 6 |

### Backlog execution rules

- Dependencies are hard unless a task explicitly creates an independent read-only report. Do not parallelize tasks that would force a schema choice before its dependency.
- `hours ceiling` is a planning stop/escalation threshold, not permission to weaken tests. At 80% consumption with unresolved scope, report the exact cause and reduce nonessential polish, not safety/content value.
- A generated output requires its owner generator and drift test in the same change.
- Each backlog item must end in one of: COMPLETE_LOCAL, BLOCKED_EXTERNAL, BLOCKED_DESIGN_CONTRADICTION, DEFERRED_BY_GATE. Do not use vague “mostly done”.
- External block does not block local contract/test/runbook work, but it blocks public/external state claims.

## 6. Cost ceilings

| Phase | Human-equivalent ceiling | Incremental external spend | Cost control |
| --- | --- | --- | --- |
| P0 | 16h | ¥0 | read-only inventory; no paid crawl/SEO tools |
| P1 | 40h | ¥0 | reuse generator/schema stack; no admin UI |
| P2 | 80h | ¥0 | one vertical slice, recorded fixtures, no general persistence |
| P3 | 20h local preparation + owner action time | ¥0 default | one URL; reuse WordPress; backup/rollback first |
| P4 | 120h to Day90 | ¥0 | Wave gates; improve existing before new |
| P5 | 16h per mature monthly/quarterly cycle | ¥0 | sanitized owner-private imports; generated reports |
| P6 | 16h decision design; implementation separately capped | ¥0 unless optional approved proposal | maximum-one category |

Any paid proposal must include exact price, expected hours saved or mature contribution gained, break-even months and automatic cancel threshold. Without verified pricing/effect, default remains no purchase.

## 7. Phase exit evidence package

Every phase report includes:

```yaml
phase: Pn
source_head: <live commit>
worktree_status_before: <sanitized>
worktree_status_after: <sanitized>
outcome: <one sentence>
completed_backlog_ids: []
requirements_verified: []
tests:
  passed: []
  failed: []
  not_applicable: []
visual_a11y_evidence: []
analytics_evidence:
  status: AVAILABLE | UNAVAILABLE | NOT_APPLICABLE
  provenance: []
cost:
  human_hours: <number>
  external_spend_jpy: 0
rollback:
  trigger: []
  procedure: []
  rehearsal_status: NOT_EXECUTED | PASSED_LOCAL | PASSED_EXTERNAL
external_actions:
  executed: []
  not_executed: [EXT-*]
residual_assumptions: []
exit_gate: PASS | FAIL | EXTEND | BLOCKED_EXTERNAL
```

Local evidence must use `PASSED_LOCAL`; production/staging/formal CI wording is reserved for evidence actually obtained there.

## 8. Rollback design by change class

| Change class | Before state | Rollback artifact | Trigger | Verification |
| --- | --- | --- | --- | --- |
| V2 overlay code/contracts | current commit/worktree | Git revert/feature flag; no destructive clean | test/security regression | make generate/check/fast/final |
| Local article/content package | previous package/version | select prior immutable package | semantic/source/review error | render/SEO/browser digest |
| WordPress article migration | production export + old content/metadata hash | restore exact old post/theme/metadata | critical fact/CTA/canonical/a11y defect | public 200/canonical/H1/disclosure/link/screenshot |
| Redirect/canonical/sitemap | before map | restore map/config | loop/404/index mismatch | crawler simulation + public read-only |
| Analytics activation | previous config/policy | disable sender/restore config | PII/consent/policy/quality issue | network log + event store absence |
| Provider outcome import | source hash and prior immutable imports | superseding correction record | reconciliation mismatch | provider total and report rebuild |

## 9. Stop and escalation conditions

Codex continues through ordinary test failures by fixing them. It must stop **before making a change** when:

1. root/nearest live instructions conflict with this allowed path or workflow;
2. isolated worktree/branch collision cannot be resolved without touching another agent’s work;
3. current schema/owner makes the specified decision impossible without choosing a new architecture;
4. a required task needs credentials, live provider/public write, publication, deployment, spending or irreversible action;
5. secret/PII/private provider material would need to be read or committed;
6. an exact source fact required for a public claim is unavailable and safe `UNKNOWN` cannot satisfy the requirement;
7. a design contradiction leaves two incompatible accepted decisions.

Escalation output must state: conflicting IDs/paths, observed evidence, why safe default fails, smallest recommended correction, impacted requirements/tests/phases. It must not ask the owner to choose between broad A/B options when one safe recommendation can be made.

## 10. P4/P5 operational priorities

Existing page improvement precedes new article when any is true:

- critical/major defect, broken CTA/link, stale high-risk source, canonical/index issue;
- page has ≥200 impressions/28d but weak CTR with stable position and a predeclared metadata experiment;
- page has ≥500 eligible sessions and AOC below the current gate with verified measurement;
- two pages cannibalize the same query family;
- update queue exceeds 1.5h/page/month or 20% of source SLA is overdue;
- mature article payback is negative and a one-variable repair has not yet been tested.

New article is allowed only when current public assets meet quality/freshness guardrails and the new query owns a distinct decision job with complete primary sources.

## 11. Retirement/deprecation roadmap

- P0: inventory and disposition only.
- P1/P2: V2 stops depending on deferred/retired surfaces; add adapters/flags, no deletion.
- P3/P4: observe runtime/generator/reference use for two releases or 30 days.
- P5: compare maintenance cost and replacement completeness.
- P6 or separate owner-approved work: destructive removal proposal with exact file/data list, no-use evidence, rollback and migration test.

Automatic/partial publication is retired for V2 regardless of existing candidate code. It remains inert until a separate successor decision explicitly changes D-V2-018/D-V2-034.
