# Technical, Data and Analytics Architecture

## 1. Architecture decision

| Option | Architecture | Decision | Build TCO | Operating TCO | Control | Reason | Residual risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | WordPress public + Git V2 control plane | SELECT | Low | Low–medium | High | Existing URL protection, deterministic evidence and human gate at lowest TCO. | WordPress/Git drift is controlled by sealed packages. |
| B | WordPress-only source of truth | REJECT | Low initially | Medium | Medium-low | Simple editing but weak claim/source reproducibility and AI governance. | Would turn structured review into manual work. |
| C | Headless WordPress + Next.js | REJECT | High | High | Medium-high | Two renderers/auth/preview/cache/deploy surfaces for one operator. | No measured WordPress limitation justifies it. |
| D | Next.js/static full migration | REJECT | High | High | Medium-high | Large URL/theme/operations cutover and rollback risk. | Premature before wedge economics. |
| E | Finish all current RAOS platform surfaces | REJECT | Very high | High | Potentially high | Sunk code is not a retention reason; public learning is lagging. | Keep invariants, shrink surface. |

### Selected target

```text
Approved primary sources / recorded provider evidence
          │
          ▼
Git V2 successor overlay
  product spec / route / source / claim / rule / product / article / review
          │
          ├── deterministic validators & decision engines
          ├── local renderer / browser preview
          ├── SEO/structured-data generator
          ├── event semantic markup (sender OFF)
          └── hash-bound PublicationPackage
                         │
                         │ separate human approval / external action
                         ▼
                   WordPress draft
                         │ human publish
                         ▼
                kurashinoshirube.com
                         │ read-only verify
                         ├── public integrity/freshness/link checks
                         ├── Search Console observations
                         ├── approved first-party events
                         └── owner-private Rakuten mature outcome import
                                      │
                                      ▼
                          QDS / AOC / EPC / RPM / contribution reports
                                      └── never product recommendation input
```

The architecture is intentionally asymmetric: Git can create a sealed successor package; WordPress cannot silently change editorial truth. A public edit is observed as drift and requires import/review or rollback, not automatic reverse synchronization.

## 2. Repository placement and ownership

### 2.1 Successor overlay paths

The first implementation uses only these new/narrow locations, subject to live `AGENTS.md` and generator owner discovery:

```text
changes/raos-v2/**
contracts/raos-v2/**
python/raos/domain/decision_support_v2/**
python/raos/application/decision_support_v2/**
python/raos/ports/decision_support_v2/**
python/raos/adapters/decision_support_v2/**
packages/web-ui/src/decision-support-v2/**
tests/raos_v2/**
scripts/build_raos_v2_successor.py
scripts/validate_raos_v2_successor.py
docs/runbooks/raos-v2/**
```

This design does **not** authorize these paths blindly. Codex must read root/nearest `AGENTS.md`, inspect current source layout and register generated outputs through the actual owner generator. If a listed path conflicts with live rules or existing ownership, stop before changes and escalate with the smallest exact conflict; do not choose a replacement architecture.

### 2.2 Prohibited paths and operations

- No changes under `docs/canonical/**`, `docs/upstream/**`, `zip/**`.
- No reset, clean, checkout-overwrite, deletion or staging of unrelated dirty paths.
- No secrets, credentials, private provider rows, personal/production data, raw prompts.
- No production URL, WordPress, analytics, Rakuten, deployment or release write in the first PR.
- No destructive retirement in first PR; only ledger/deprecation markers and unused-by-V2 boundaries.

### 2.3 Generator ownership

- Semantic input lives in versioned V2 contracts/change inputs.
- Generated files are never edited directly.
- The active `BuildSpec`/manifest owner is discovered live, then a `raos_v2_successor` owner is added with dependencies, outputs and focused tests.
- `make generate` updates affected outputs; `make check` detects drift.
- Input digest binding is used for immutable canonical/provider response/runtime integrity, not as a human approval token for ordinary source files.

## 3. Source-of-truth matrix

| Data | Authoritative source | Boundary |
| --- | --- | --- |
| Product/wedge/portfolio/route/template contracts | Git V2 overlay | WordPress/admin may not override |
| Claims/sources/product models/airline rules | Git V2 overlay + permitted source provenance | Public HTML is a projection |
| Offer observations/affiliate refs | Owner-approved Rakuten evidence store/import; repository stores sanitized contract/fixture only | No credential/private provider data |
| Editorial decisions/review binding | Git V2 overlay | Human reviewer is authority |
| Rendered public draft package | Generated sealed package | Rebuild from source, do not hand-edit |
| Public URL/content | WordPress production | Must be verified against sealed package; drift becomes state |
| Search metrics | Search Console owner export/API evidence | UNAVAILABLE without provenance |
| Behavior events | Approved first-party collector | Default OFF production |
| Outcome/reward | Rakuten provider report owner-private import | Provider total/maturity authority |
| Unit economics | Generated from reconciled source + time ledger | Never recommendation input |

## 4. Domain and data contracts

The exact machine-readable contract is in `10_INTERFACE_CONTRACTS.yaml`. Implementation must preserve the following closed concepts.

### 4.1 Core entities

- `QueryIntent`: one query family, one primary page role, parent hub, overlap status.
- `SourceRecord`: publisher/class/URL/checked/effective/next review/provenance/status.
- `Claim`: A/D/UNKNOWN, subject/predicate/value/unit/source or logic/risk/freshness.
- `AirlineRuleSet`: carrier, journey scope, effective period and variants by aircraft/fare/route.
- `ProductModel/ProductVariant`: manufacturer model identity, generation, normal/expanded dimensions, mass, capacity, declared features, unknowns.
- `OfferObservation`: Rakuten item/shop/affiliate/image observation; never overwrites product facts.
- `EditorialDecision`: explicit inputs, logic version, fit/non-fit, reviewer; no finance fields.
- `ArticleDefinition`: route/template/intent/claims/blocks/disclosure/review state.
- `PublicationPackage`: all input hashes, render/source/review/migration binding and state.
- `AnalyticsEvent`: allowlisted event and fields only.
- `ProviderOutcomeImport`: source hash, period, currency, row totals, maturity, attribution.
- `FreshnessAssessment`: FRESH/DUE/SOFT_STALE/HARD_STALE/UNKNOWN and required action.

### 4.2 State machines

**Editorial/publication**

```text
DRAFT -> EVIDENCE_COMPLETE -> HUMAN_REVIEWED -> PACKAGE_SEALED
PACKAGE_SEALED -> WP_DRAFT_CREATED        [external]
WP_DRAFT_CREATED -> HUMAN_PUBLISHED       [external]
HUMAN_PUBLISHED -> PUBLIC_VERIFIED        [read-only verification]
any pre-public state -> BLOCKED / REVIEW_REQUIRED
verification failure -> human rollback -> ROLLED_BACK
```

**Product identity**

```text
UNRESOLVED -> EXACT | AMBIGUOUS | REJECTED
AMBIGUOUS -> EXACT only with new bound evidence + human review
EXACT -> REVIEW_REQUIRED on model/source drift
```

**Freshness**

```text
FRESH -> DUE -> SOFT_STALE -> HARD_STALE
new verified source -> FRESH
source unavailable/contradiction -> UNKNOWN or BLOCKED by risk
```

### 4.3 Invariants

1. An A claim without an allowed source cannot render.
2. A D judgement cannot be serialized as product fact.
3. An unresolved/ambiguous product cannot get an affiliate CTA.
4. Finance/business score cannot enter eligibility, fit, order or render digest.
5. Semantic input drift invalidates a seal.
6. A high-risk HARD_STALE claim blocks a successor package.
7. Production sender/adapters are disabled without separate approval/config.
8. External actions cannot be represented by a local success state.

## 5. Decision engine

### 5.1 Carry-on compatibility

Input:

```text
carrier (required; no default)
journey date/time JST
origin/destination and connection carriers if known
aircraft/seat-count or UNKNOWN
fare/baggage option or UNKNOWN
bag count + personal item count
external height/width/depth cm including appendages
normal or expanded state
combined weight kg
```

Resolution:

1. Select rule set whose effective period includes journey date.
2. Resolve the most specific variant with known carrier/aircraft/fare/route inputs.
3. For connections, evaluate each segment and return the strict intersection; if a required segment is unknown, final state UNKNOWN.
4. Match dimensions against allowed orientation permutations only. Do not use three-edge sum as a substitute for per-edge maxima.
5. Evaluate count, personal item, total weight and any explicit storage/handling condition.
6. Return `PASS`, `FAIL`, or `UNKNOWN` with a list of each criterion, source ID, effective date and checked date.
7. Never claim boarding guarantee; link to resolved official source.

Boundary behavior:

- Exact equality passes when source says “以内”.
- Numeric parsing rejects negative, zero where impossible, NaN, locale ambiguity and omitted units.
- Rounding is not used to convert an over-limit value to pass. Store decimal inputs and compare in centimeters/kilograms using exact decimal semantics.
- If manufacturer dimension order is unclear, do not rotate unless source/data contract declares orientation-independent external edges.

### 5.2 Product selection

1. Resolve exact ProductVariant.
2. Run compatibility for the article condition.
3. Apply article-specific hard constraints (e.g., mass ceiling, front-open required) declared before candidate data.
4. Exclude unresolved/stale/safety-blocked variants.
5. Calculate fit score from non-financial components.
6. Deterministic tie-break: compatibility, freshness, stable product ID.
7. Render condition-specific outcomes, not a universal rank.

## 6. Rakuten adapter

### 6.1 Contract

- API: Ichiba Item Search `version: 2026-07-01`.
- Endpoint/version and required request fields are explicit in adapter configuration.
- Secret names are interfaces only; no values in code, fixture, log, package or prompt.
- Local/default mode: `RECORDED_ONLY` with exact response envelope and source SHA-256.
- Live mode: absent/disabled in first PR. A later owner-approved task must bind applicationId, accessKey and affiliateId safely, recheck current official terms, network policy and rate behavior.

### 6.2 Request behavior for a later live slice

- Exact model-number-first query; broad keyword discovery is separate and cannot create identity automatically.
- Bounded page count/result count/timeout/retry budget; no unbounded pagination.
- Backoff for provider errors, but no repeated identical URL storm.
- User agent/credit/display behavior follows current official requirements at execution time.
- Raw response is owner-private/runtime evidence where required; repository receives sanitized recorded fixture only if permitted.

### 6.3 Response normalization

Persist/reference:

- API version, request semantic hash, response hash, retrieved_at, itemCode, shopCode/name, itemName, itemUrl/affiliateUrl references, itemPrice/availability as volatile observation, image URLs and sizes, JAN if provided, provider fields used for identity.
- Unknown fields are rejected or ignored according to closed schema; silently accepting a renamed required field is forbidden.
- HTML/provider strings are untrusted data and escaped/sanitized before any rendering.

### 6.4 Identity protocol

Exact identity requires:

- manufacturer/brand/model number/generation tokens;
- product-kind token;
- no forbidden accessory/replacement/case/old-generation token;
- variant capacity/dimensions/color/set relation understood;
- itemCode and evidence stored;
- human review for first binding or ambiguous cases.

`EXACT`, `AMBIGUOUS`, `REJECTED`, `UNRESOLVED` are the only states. Fuzzy score alone never produces `EXACT`.

### 6.5 Image/link policy

- Only allowed API-provided product image/affiliate link with current provenance.
- No crop, overlay, aspect-ratio distortion, upscale or generated reproduction of product appearance.
- `object-fit: contain`, intrinsic dimensions, verified alt.
- Missing/unresolved identity blocks image and affiliate CTA. The editorial article may render a neutral text placeholder and official-source link.

## 7. Rendering and WordPress delivery

### 7.1 Renderer

Inputs: versioned `ArticleDefinition`, claims, decisions, source states, product/offer/media bindings, design tokens.  
Outputs: deterministic HTML fragment/page, metadata, JSON-LD, semantic event attributes, asset manifest, render hash, browser fixture.

Failure policy:

- No partial product card with an unbound CTA.
- No “last good” source silently used beyond SLA.
- Unknown values display `未確認`, not blank/zero.
- Any required schema/claim/identity/SEO error prevents `PACKAGE_SEALED`.

### 7.2 Publication package

A sealed package contains:

```text
package_id / schema_version / target_origin / target_route / article_id
source input IDs and hashes
claim/product/rule/article/review versions
render HTML and normalized text hash
metadata/JSON-LD/asset hashes
link and media bindings
migration before/after map
rollback artifact reference
human reviewer binding
created_at and expiration/freshness state
```

Seal verification runs again immediately before any external draft action. A difference produces `REVIEW_REQUIRED`; it never updates WordPress automatically.

### 7.3 WordPress adapter

- Default `DISABLED_DRY_RUN`.
- Dry run outputs exact target, create/update intent, before/after normalized diff, comments/pings/status fields and idempotency key.
- The first PR includes no credential access or network request.
- Later external action may create exactly one unpublished draft from one valid seal. Publish/schedule/delete is a different human action.
- WordPress response is recorded as external receipt outside source truth; public verification checks exact canonical/content markers.

## 8. Analytics and attribution

### 8.1 Minimal event catalog

| Event | Allowed semantic attributes | Use | Explicitly excluded |
| --- | --- | --- | --- |
| tool_result_view | article_id/tool_id,result_state,rule_set_id,source_checked_date | QDS candidate | no entered dimensions/weight payload |
| comparison_view | article_id,placement,comparison_id | QDS candidate | no scroll percentage required |
| evidence_link_open | article_id,claim_id,source_class,placement | trust/decision completion | do not send full destination URL if not needed |
| official_source_open | article_id,source_id,placement | QDS completion signal | external navigation only |
| affiliate_outbound_activate | article_id,product_id,offer_id,placement,identity_version | AOC/attribution cohort | no price/commission/personal ID |
| article_complete | article_id,completion_method | supporting signal | not QDS alone |
| error_state_view | surface_id,error_code | quality guardrail | no raw exception/PII |

Session handling:

- Browser generates a random ephemeral token in `sessionStorage`.
- Rotate after 30 minutes of inactivity; no durable cookie or cross-device identifier for V2 events.
- Server stores only an HMAC/derived token with rotation/version, not the raw token.
- Do not collect raw IP, raw user agent, full referrer, query string, email, name, address or provider order ID in the product event table.
- Infrastructure logs may exist under hosting policy; they are not joined to content analytics by this design.
- Event sender is production OFF until owner/privacy approval and public policy alignment. Local sink validates semantics without transmission.

### 8.2 Metrics

```text
QDS rate = qualified decision sessions / eligible sessions
AOC = verified affiliate outbound activations / affiliate-eligible sessions
Confirmed EPC = mature confirmed reward / attributable verified outbound activations
Confirmed RPM = mature confirmed reward / eligible sessions * 1000
Cash contribution = mature confirmed reward - direct variable external cost
Economic contribution = cash contribution - human hours * internal labor rate
Payback months = production economic cost / trailing mature monthly economic contribution
```

All formulas carry JPY, JST period, attribution class, maturity and formula version. No data yields `UNAVAILABLE`, never fabricated zero.

### 8.3 Attribution classes

- `DIRECT_PROVIDER`: provider supplies a verifiable article/placement key.
- `CLICK_COHORT`: aggregated cohort can be matched under a predeclared, non-personal method; label confidence and do not claim order-level causation.
- `UNATTRIBUTED_PROGRAM`: only program total. It informs business health but never article EPC/profit.

### 8.4 Outcome import

Owner supplies a minimal sanitized export through owner-private boundary. Import checks source SHA-256, period, currency, row count, status mapping, duplicates and provider total. Pending/immature/cancelled outcomes remain separate. A corrected import supersedes prior data; no in-place undocumented edit.

### 8.5 Search Console

Store monthly/page/query aggregates with export/source metadata. Avoid repository storage of owner-private full exports. Search query strings are provider analytics data, not browser event fields. Use them for intent ownership and content investment, not product recommendation.

## 9. Freshness jobs

Initial scheduling contract:

- Daily local/CI deterministic clock test; no live fetch in ordinary CI.
- Owner-triggered source refresh queue: airline/high-risk every 30 days, product specs 90 days, policy 180 days.
- Approved Rakuten live observation, if later enabled: on-demand before publication and scheduled link/offer checks subject to provider rules; no broad scrape.
- Public link/status read-only monitor: daily/weekly according to cost, with bounded requests and owner-approved production observation.
- A change produces an impact report; it does not directly edit/publish.

Job output fields: job ID, mode (RECORDED/READ_ONLY_LIVE), inputs, source versions, changed claim IDs, affected article IDs, severity, recommended action, errors, started/ended time, local/formal/external evidence class.

## 10. Security and authentication

### Invariants

- Secret/credential values never in repository, fixture, CLI args, logs or package.
- Live provider and WordPress ports require explicit owner-only secret store and disabled feature flag; not part of first PR.
- Denied-network local/CI tests must pass for recorded vertical slice.
- External HTML/provider strings are untrusted; sanitize/escape and reject unknown schemes.
- Affiliate and official outbound URLs accept `https` and exact allowed hosts/provenance; no open redirects.
- WordPress/admin/auth endpoints are not exposed by preview app.
- Public/internal/finance data types remain separated.
- Logs use IDs/error codes, not source text or sensitive values.
- Existing repository secret scan and security aggregate remain required.

## 11. Environment boundaries

| Environment | Allowed evidence/actions | Forbidden/meaning |
| --- | --- | --- |
| Local worktree | recorded fixtures, pure decision/rendering, browser preview, local sink, migration simulation | not formal CI/staging/Production; no provider/public write |
| Repository CI | locked dependencies, generators, contract/unit/browser/security with network denied | no live provider/credential; result is CI only |
| Owner-private validation | sanitized exports, optional gated provider/read-only verification | not repository-public evidence; secrets stay owner store |
| Staging | only if separately designed/approved; deploy and credentials gated | not implied by this package |
| Production | WordPress public, approved event collector, public verification | all writes/deploys/publication human-gated |

## 12. Backup and restore

P0 defines but does not execute:

- WordPress database/content/media/theme/plugin/version export method and owner.
- Current public URL, canonical, robots, sitemap, content hash and screenshot baseline.
- Theme/plugin artifact/version and rollback steps.
- Redirect/canonical before/after map.
- Sealed package and public verification receipt.
- Recovery objectives for one-page migration: rollback start within 30 minutes of critical detection; previous public state restored and verified within 2 hours, subject to provider/host availability. These are operating targets, not guarantees.

P3 trigger examples: wrong model/CTA, hidden disclosure, broken canonical/indexability, critical accessibility regression, publication state mismatch. Rollback is a human production action.

## 13. Observability

- Structured local logs: run ID, component, event/error code, object IDs, timing, evidence class; no sensitive payload.
- Build report: generator inputs/outputs, hashes, changed requirements/tests.
- Public verification: status, canonical, robots, H1, disclosure marker, package marker, links, screenshot references.
- Freshness dashboard can be a generated Markdown/JSON report; no paid dashboard required.
- Alerts initially owner-readable files/GitHub checks; external notification service deferred.
- SLO-like guardrails: critical public defect 0, broken affiliate link 0, hard-stale high-risk claim 0. Missing monitoring data is UNKNOWN.

## 14. Existing asset disposition

| Asset | Disposition | Reason | Migration |
| --- | --- | --- | --- |
| root AGENTS.md / README / Makefile / generator ownership | KEEP | dirty保護、標準command、生成ownerは安全な実装基盤。 | live再確認しV2 generatorを追加。 |
| docs/canonical/** / docs/upstream/** / zip/** | KEEP_IMMUTABLE | v1 baseline/authorityを直接変更しない。 | V2 overlayからread-only参照。 |
| secret scan / denied-network / authz / public-internal isolation | KEEP | 検証済みsecurity invariantを弱めない。 | V2 testsへ継承。 |
| publication operator / journal / rollback concepts | REWORK | draft-only、human gate、hash bindingは高価値。 | V2の最小package/state schemaへ縮小。 |
| claim/evidence/editorial domain | REWORK | 目的は一致するが型・層が広い。 | A/D/UNKNOWNとwedge sourceに絞る。 |
| Rakuten adapter | REWORK | 2026-07-01/accessKey/exact identityへ更新が必要。 | recorded fixture first、live disabled。 |
| public WordPress theme/Yoast integration | MIGRATE | 公開URLを保護しつつUX/IAを更新。 | child theme/blockを1 URLずつ。 |
| 公開carry-on comparison article | MIGRATE | 唯一の公開検索/収益学習asset。 | slug維持でV2 comparisonへ。 |
| portable power / Anker differences / dishwasher / robot vacuum draft | DEFER | wedge外、media/evidence未解決、安全・実機品質の問題。 | archive保持、Phase 6で再score。 |
| 空の「家事」「備え」カテゴリUI | RETIRE | 実体のないnavigationは信頼とcrawlを損なう。 | navから除外しURL inventoryでnoindex/redirect。 |
| Next.js public app | DEFER | public renderer二重化。 | WordPress限界が計測で証明された場合だけ。 |
| custom admin/review UI | DEFER | 25 pages規模では維持費過大。 | 50 pagesまたは週4h超のadmin frictionで再評価。 |
| advanced causal attribution / rank provider / paid dashboard | DEFER | provider fact不足と固定費。 | GSC＋first-party＋monthly reportで開始。 |
| automatic/partial publication | RETIRE_FOR_V2 | 初期riskが利益を上回る。 | 別owner-approved successorまで無効。 |
| general Postgres/object storage persistence | DEFER | versioned JSON/YAMLで初期規模を処理可能。 | >10k records/latency/merge conflict実測後。 |

Removal policy:

1. First integration PR adds no destructive deletion.
2. Mark deprecated owner and replacement.
3. Prove no generated/runtime/reference use for two releases or equivalent 30-day period.
4. Confirm rollback does not depend on it.
5. Human explicitly approves destructive removal where required.

## 15. Cost architecture

- Incremental external spend default: ¥0.
- Reuse existing WordPress hosting, GitHub workflow, Python/Node toolchain and browser test setup where live-compatible.
- No new database/object store/admin/dashboard/search SaaS for initial 25 assets.
- JSON/YAML/Git is adequate until >10,000 active records, measurable query latency, repeated merge conflict or backup/recovery evidence justifies migration.
- Paid option proposals, if later needed, must state monthly/one-time cost, expected saved hours or incremental confirmed contribution, break-even and auto-cancel threshold.

## 16. Failure behavior matrix

| Failure | Safe state | User/public behavior | Operator action |
| --- | --- | --- | --- |
| source missing/contradictory | UNKNOWN/BLOCKED | show unknown or retain prior within SLA with date; no false pass | resolve primary source |
| product identity ambiguous | IDENTITY_BLOCKED | no product image/affiliate CTA | human exact match review |
| Rakuten unavailable | OFFER_UNAVAILABLE | article/official facts remain; no generic fallback CTA | retry only under bounded approved operation |
| analytics unavailable/rejected | UNAVAILABLE | site works; no dark pattern | record unavailable, do not infer zero |
| package drift | REVIEW_REQUIRED | no external draft/update | rebuild and human re-review |
| public mismatch | PUBLIC_VERIFY_FAILED | growth gate stops; potentially disable affected CTA | human rollback/correct |
| hard-stale high-risk rule | HARD_STALE | checker definitive result disabled / warning | urgent official recheck |
| test/performance/a11y critical | BLOCKED | no package seal | fix locally, rerun full affected suite |
| secret/PII finding | SECURITY_BLOCKED | no artifact/PR continuation with leaked data | remove safely, rotate via owner if real, run scan |
