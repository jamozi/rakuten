# Content, SEO and Editorial System

## 1. Editorial operating principle

RAOS V2は「文章生成」ではなく、`query → intent → decision → article → claim → source → product/offer`の検証可能な関係を生成・更新する。公開文章はそのrenderingであり、sourceのない断定、scope外の一般化、offer情報の恒久化、AIによる穴埋めを許可しない。

## 2. Content model

### 2.1 Entity relationships

```text
QueryFamily 1 ── 1 PrimaryIntent ── 1 ArticleDefinition ── n ContentBlocks
                                     │          │
                                     │          ├── n EditorialDecision ── n InputClaim
                                     │          │
                                     │          ├── n Claim ── n SourceRecord
                                     │          │
                                     │          ├── n ProductModel ── n ProductVariant
                                     │          │                         │
                                     │          │                         └── n OfferObservation
                                     │          │
                                     │          └── 1 PublicationPackage ── 1 TargetRoute
                                     │
                                     └── 1 ParentHub / n RelatedIntent edges
```

### 2.2 Required relations

| Entity | Required identity | Required relations | Forbidden shortcut |
| --- | --- | --- | --- |
| QueryFamily | intent_id + normalized question | primary article, parent hub, overlap record | keyword variantごとの自動page生成 |
| ArticleDefinition | article_id + stable route | template, intent, claims, decisions, source freshness, review | WordPress post IDだけを正本にする |
| Claim | claim_id + subject/predicate | type, source/logic, checked/next review, risk | 文章全体を1 claimにする |
| SourceRecord | source_id + canonical URL | publisher, class, capture, effective date, status | URLだけ保存し確認日/内容を省略 |
| ProductModel | manufacturer + model number + generation | official sources, variants, identity state | 楽天titleをmanufacturer factへ昇格 |
| OfferObservation | provider itemCode + observed_at | product binding, shop, affiliate/image refs, state | price/stockを記事本文の固定事実にする |
| EditorialDecision | decision_id + logic version | input claims, output, fit/non-fit, reviewer | AIの自由文scoreだけで推薦 |

### 2.3 Claim types and public labels

| Type | Meaning | Allowed evidence | Public rendering | Initial V2 status |
| --- | --- | --- | --- | --- |
| A — 公式仕様/ルール | manufacturer、airline、government、permitted Rakuten dataが直接示す値 | allowed primary source + capture provenance | 「公式情報」＋source＋確認日 | ALLOWED |
| B — 第三者実測 | 再現可能な外部測定 | bound measurement protocol/record | 測定者・方法・日付 | FORBIDDEN until separate contract |
| C — 利用者の傾向 | 複数のusage recordsに反復するpattern | permitted, sampled, privacy/copyright-safe evidence | scope/sample/限界 | FORBIDDEN until separate contract |
| D — 編集部の判断 | A factsとreader conditionから導くbounded recommendation | explicit inputs + logic version + human reviewer | 「編集判断」＋理由＋向かない条件 | ALLOWED |
| UNKNOWN — 未確認 | adequate evidenceがない/条件不足 | none or unresolved source state | 「未確認」＋確認方法/影響 | REQUIRED instead of filling |

`B`と`C`はschema enumに入れず、別successor designが承認されるまでvalidatorで拒否する。A specificationはtest resultにならず、D recommendationはproduct factにならない。

## 3. Source policy

### 3.1 Allowlist

| Class | Use | Conditions | Freshness default |
| --- | --- | --- | --- |
| Manufacturer primary | model、寸法、重量、容量、機能、保証、対応条件 | exact model/generation/variant、official domain、checked/captured | 90 days; high-risk 30 |
| Airline primary | 手荷物寸法、個数、重量、運賃/機材/路線差 | effective date、journey scope、official link | 30 days |
| Government/industry primary | 危険物、液体、表示、privacy/accessibility | current official publication、jurisdiction | 30–180 days by risk |
| Rakuten permitted API data | itemCode、shop、current offer、affiliate URL/image | current API/version/guideline、exact identity、observed_at | 24 hours for volatile offer |
| Owner-created diagram/calculation | rule visualisation、dimension illustration | does not depict a product inaccurately; source logic linked | when inputs change |

### 3.2 Conditional sources

- Manufacturer PDF is allowed when official and model-specific; preserve URL, document version/page, checked time and capture hash where permitted.
- Airline help center page is allowed if official; record that help page may change without stable revision ID.
- Official retailer operated by manufacturer may support model specs only when the manufacturer identifies it as official and model scope is exact.
- Search snippets may locate a source but never support a published claim.

### 3.3 Prohibited sources for product claims

- Competitor media, ranking, copied comparison table, review text, score, test result.
- Unverified marketplace title/description, seller-created image/text, Q&A/review.
- AI answer, raw search result snippet, social post, anonymous forum.
- Affiliate economics, popularity badge, points, inventory scarcity.
- Private provider data, credentialed screen, raw prompt, personal data.

### 3.4 Capture and evidence rules

Each A claim must bind:

1. canonical source URL and publisher;
2. exact subject/model/variant;
3. extracted value and unit;
4. page section or document page/anchor where possible;
5. checked_at in JST and source effective date if provided;
6. source/capture hash or immutable provider response hash where permitted;
7. next_review_at and risk class;
8. contradiction status and resolver if another primary source differs.

No design requires copying a full copyrighted page. Store the minimum permitted extract/normalized fact plus provenance. If storage terms are uncertain, store URL, metadata, hash of owner-held capture and re-fetch instruction rather than repository bytes.

## 4. Article types and exact templates

All templates begin with skip link/header and end with correction/source/policy/related context. No template may hide the affiliate disclosure behind interaction.

### 4.1 HOME

1. Compact masthead and visible disclosure link.
2. Hero: concrete job, one CTA to checker, secondary link to wedge hub.
3. “今すぐ確認”: checker form preview or three condition paths.
4. Latest verified guides: only real published assets; no fallback fake popularity.
5. Decision paths: airline rule / weight/packing / product shortlist.
6. Trust strip: official facts, editorial judgement, checked dates.
7. Editorial method and correction link.
8. Footer policies.

### 4.2 HUB / CATEGORY (`/carry-on/`)

1. H1 and exact scope.
2. 30-second decision map.
3. Tool entry.
4. Airline-specific rule cards with checked dates.
5. Task guides.
6. Product comparisons/differences.
7. Unknown/edge cases.
8. Method/freshness/correction.
9. Related/expansion links only when published.

### 4.3 GUIDE

1. Affiliate/AI/no-hands-on disclosure where relevant.
2. Reader problem and exact scope.
3. 30-second conclusion.
4. Conditions/questions to collect before deciding.
5. Official rules/specs, one claim per evidence unit.
6. Worked examples using clearly labelled hypothetical values.
7. Exceptions/UNKNOWN and final authority link.
8. Buy-nothing/alternative path.
9. Conditional next step and, only if appropriate, comparison link.
10. Sources, checked date, change log, correction.

### 4.4 COMPARISON

1. Disclosure, exact compared models, no-hands-on statement.
2. “30秒で選ぶ” conditional conclusions; no overall winner.
3. Who this comparison helps / does not help.
4. Method: hard eligibility, official fields, judgement boundaries.
5. Semantic comparison table (desktop) + equivalent `dl` cards (mobile).
6. Product cards in fixed order: image state → condition → model → D benefit → A facts → fits → non-fits → caution/UNKNOWN → checked date → official source → CTA context → exact affiliate CTA.
7. Difference explanations by decision criterion.
8. Conditions where none should be bought.
9. Source list/change log/correction.
10. Related guide/difference links.

### 4.5 DIFFERENCE

1. Exact models/ways compared and why comparison page is not duplicated.
2. Three or fewer decisive differences.
3. Fact table.
4. Conditional branch: if X choose A, if Y choose B, if unknown verify Z.
5. Common non-fit and alternatives.
6. Official sources/checked date.
7. Link to full comparison or checker; CTAs only when exact identity exists.

### 4.6 TOOL

1. Purpose, limitation, privacy/no-transmission statement.
2. Inputs with units and examples; no preselected carrier default.
3. Validation before calculation.
4. Result: PASS / FAIL / UNKNOWN, reason per failed/unknown condition.
5. Resolved official rule, effective date, checked date and source.
6. What result does not guarantee.
7. Next action: official confirmation, packing guide, eligible comparison.
8. Reset/copy result locally; no account/profile.
9. No affiliate CTA inside a failing/unknown result unless it explains an alternative and identity is exact.

### 4.7 POLICY

1. What RAOS compares and does not compare.
2. Source classes and claim labels.
3. No-hands-on policy.
4. AI assistance and human responsibility.
5. Recommendation/business separation.
6. Affiliate disclosure and CTA rules.
7. Freshness/corrections/change history.
8. Privacy/measurement link.

## 5. Recommendation protocol

### 5.1 Hard eligibility

A ProductVariant is eligible only when all are true:

1. `identity_status == EXACT`.
2. Required official dimensions/weight fields are verified or the article explicitly does not require that field.
3. The variant is compatible with the resolved airline rule for the stated use condition; missing journey/rule input yields UNKNOWN, not eligible PASS.
4. Expanded and normal states are not conflated.
5. Source is not HARD_STALE.
6. CTA offer, if rendered, is current enough and bound to the exact product; product can remain in editorial text without CTA if offer unavailable.
7. No safety/legal publication blocker.

### 5.2 Fit score

The score is internal and never published as “87点”. It orders eligible candidates inside one declared condition.

```text
fit_score =
  compatibility_confidence * 0.30
+ declared_constraint_fit   * 0.25
+ verified_spec_fit         * 0.20
+ tradeoff_clarity          * 0.15
+ evidence_freshness        * 0.10
```

Each component is an integer 0–100 from closed rules:

- compatibility confidence: all required rule fields resolved=100; permitted caveat=50; unresolved=hard-ineligible.
- declared constraint fit: article-specific binary/ordinal conditions defined before product data.
- verified spec fit: normalized fields only; no inferred test qualities.
- trade-off clarity: required downside/non-fit/UNKNOWN completeness, not product goodness.
- evidence freshness: FRESH=100, DUE=70, SOFT_STALE=30, HARD_STALE=ineligible.

Tie-break order: higher compatibility, newer source checked_at, lexical stable `product_id`. Never price, commission, popularity, inventory count or points.

### 5.3 Public recommendation language

- `［条件］なら［model］が候補です。［A facts］のため、［D judgement］。一方、［non-fit/trade-off］には向きません。`
- Avoid “最強”, “絶対”, “間違いない”, “最安”, “人気No.1”, “売り切れる前に”, universal winner.
- If all products are ineligible, render “今回確認した候補には該当なし” and a buy-nothing/official check path.

## 6. Business score

Business score decides **which article/query to invest in**, never product order.

```text
business_score =
  verified_demand_signal       * 0.35
+ decision_value_learnability  * 0.20
+ mature_confirmed_economics   * 0.20
+ inverse_update_cost          * 0.15
+ evidence_availability        * 0.10
```

- Demand is Search Console/query evidence, not a guessed keyword volume.
- Economics is unavailable until mature confirmed outcomes and attribution class are valid.
- Unavailable is not 0; score confidence falls and expansion stays locked.
- Product IDs, order and renderers accept no business score fields. T-V2-030 proves non-interference.

## 7. AI operating contract

### Allowed

- Create extraction candidates from approved primary sources.
- Normalize units and propose model/variant differences for deterministic validation.
- Draft reader-led copy from verified claim objects.
- Flag contradictions, stale evidence, missing fields, duplicate intent and unnatural Japanese.
- Generate test fixtures from synthetic/non-secret values.

### Forbidden

- Select or approve sources, infer missing facts, decide product identity, create B/C evidence.
- Claim use/ownership/test, convert product specification into measured performance.
- Rank by revenue, commission or popularity.
- Scrape competitor review text or rewrite competitor content.
- Publish, schedule, update production, enter credentials, call live provider by default.
- Mark its own output HUMAN_REVIEWED.

### Required provenance

For each AI-originated block: provider/model family if policy permits, generation timestamp, input claim IDs, prompt-template version (not raw private prompt), output hash, validator result, human reviewer, review version, material edit numerator/denominator. Raw prompts and private provider content are prohibited repository data.

### AI correction rate

`materially edited AI-originated sentences / reviewed AI-originated sentences × 100`.

A material edit changes fact, judgement boundary, recommendation, trade-off, Japanese naturalness or CTA meaning. Punctuation/format-only edits are excluded. The metric is process quality, not a public author claim.

## 8. Human review and publication approval

### Roles for one-person operation

- **Editor/Owner:** source acceptance, model identity, article scope, recommendation, copy review, legal/policy escalation, publication decision.
- **Codex:** local implementation, deterministic validation, preview/evidence packaging, GitHub development within repository rules.
- **External authority:** airline/manufacturer/Rakuten/current law/provider reports remain authoritative for their facts.

### Review sequence

1. Scope/query review.
2. Source and effective-date review.
3. Product identity/variant review.
4. Claim type and contradiction review.
5. Recommendation fit/non-fit/non-purchase review.
6. Natural Japanese/read-aloud review.
7. Ad/AI/no-hands-on/unknown visibility review.
8. Mobile/keyboard/a11y/SEO/CTA destination review.
9. Seal exact package hash.
10. Separate human external action for WordPress draft/publish.

The same person may perform roles in a solo operation, but each transition must be recorded separately; an automated job cannot impersonate the human state.

## 9. Content quality gate

A package fails closed if any condition is false:

| Gate | Pass condition | Failure action |
| --- | --- | --- |
| Scope | title/H1/intro name exact category/models/journey scope | BLOCK; narrow scope or source more evidence |
| Unique decision value | page owns one job and adds calculation/normalization/conditional logic | MERGE/REWORK; no thin page |
| Evidence | all A claims allowed source; D logic bound; UNKNOWN explicit | BLOCK unsupported claim |
| Identity | model/generation/variant exact; accessory/set/old model excluded | BLOCK product/CTA |
| No false experience | no implied use/test/measurement | BLOCK and human rewrite |
| Trade-off | every recommendation has fit, non-fit, limitation/unknown | BLOCK |
| Disclosure | affiliate + finance independence visible; AI/no-hands-on when relevant | BLOCK |
| Freshness | high-risk not hard-stale; offer state handled | BLOCK/suppress volatile data |
| Japanese | read-aloud natural, no repetitive spec dump, terms defined | HUMAN_REVIEW_REQUIRED |
| SEO | one H1, unique metadata, canonical/robots/sitemap/JSON-LD valid | BLOCK publication package |
| UX/a11y | mobile parity, keyboard, focus, zoom, contrast, no overflow | BLOCK critical/major |
| CTA | exact target, context, no pressure, no sticky/pop-up/forced click | BLOCK CTA or page |

## 10. Freshness SLA and update workflow

| Subject | SLA | State at breach | Public behavior | Owner action |
| --- | --- | --- | --- | --- |
| Airline baggage rule | 30 days | HARD_STALE after due + grace 0 for high-risk | block successor seal; existing public page displays review due banner and disables definitive tool result if material | recheck official source |
| Battery/liquid/safety/government | 30 days | HARD_STALE | block definitive claim/CTA | human safety review |
| Manufacturer dimensions/spec | 90 days | SOFT_STALE then HARD_STALE at 120 | show checked date; block new seal at hard stale | recheck exact model |
| Rakuten price/stock/points/offer | 24 hours | STALE | do not render fixed value; CTA says current info at Rakuten or disables if identity unavailable | refresh owner-approved provider evidence |
| Affiliate image/link provenance | 30 days or provider term change | DUE/HARD_STALE | disable image/link if binding uncertain | revalidate guideline/API |
| Editorial judgement | 180 days or input change | DUE | retain only if inputs fresh; otherwise REVIEW_REQUIRED | re-run logic + human review |
| Policy/about/privacy | 180 days or system/provider change | DUE | policy review marker | owner review |

Update algorithm:

1. Detect source effective-date/page hash/status change.
2. Resolve affected claims via reverse graph.
3. Classify semantic delta: none / wording / value / applicability / contradiction / source unavailable.
4. Re-run selection, article renderer, SEO, visual snapshots and package hash.
5. Require human review for any public semantic delta.
6. Create successor sealed package; never edit published text silently.
7. Human applies external update; verify public and preserve previous package for rollback.

## 11. SEO system

### 11.1 Metadata

- Title: primary question/outcome + scope/condition; brand suffix only when length/useful. No year unless page actually maintains year-specific data and update SLA.
- H1: natural Japanese answer scope; may differ from title but not intent.
- Meta description: decision value, exact scope, official source/checked nature; no unsupported superlative.
- Canonical: self for final indexable page; redirect targets canonical to themselves. Query/filter/tool result variants are not separately indexable.
- Robots: index,follow only for complete unique pages. Draft/search/filter/empty taxonomy/tool-state URLs are noindex or not routable.
- Sitemap: only final 200 indexable canonical URLs; lastmod reflects material content update, not build noise.
- Pagination/tag/date/author archives: disable/noindex unless they have explicit unique reader value and content inventory.

### 11.2 Structured data

Default allowed:

- `WebSite` on home.
- `Organization`/site operator information consistent with visible policy.
- `BreadcrumbList` on non-home pages.
- `Article` on editorial guide/comparison/difference/policy when visible author/date/headline match.

Default forbidden until exact eligibility and visible content exist:

- `Product`, `Offer`, `Review`, `AggregateRating`, `ItemList` ranking, `FAQPage`, `HowTo` rich-result markup.
- Any rating/test/review schema without actual permitted evidence.
- Hidden structured data not represented to readers.

### 11.3 Internal linking

- Every guide links upward to `/carry-on/`, sideways to at most 3 complementary pages and downward to a comparison/tool only when context fits.
- Product comparison links to rule guide and checker before/alongside affiliate CTA.
- Anchor text states the decision job, not generic “こちら”.
- Related links render only published, canonical, compatible pages; no empty boxes.
- Orphan check and click-depth test run on every generated sitemap.

## 12. URL migration and lifecycle

### Lifecycle decisions

| State | Criteria | Action | SEO behavior |
| --- | --- | --- | --- |
| KEEP | unique value, current evidence, target intent | update in place | same URL/canonical |
| MIGRATE | valuable URL but old template/data model | V2 successor at same URL | same canonical, public diff verified |
| REDIRECT | content fully superseded by one stronger page | 301 one hop after human approval | target self-canonical; source removed from sitemap |
| NOINDEX | utility state/search/filter/empty archive without unique landing value | noindex or remove route | not sitemap; links handled intentionally |
| CONSOLIDATE | cannibalized pages with same job | merge evidence/content, one redirect | preserve best URL by evidence, not arbitrary freshness |
| RETIRE/410 | harmful/obsolete and no suitable replacement | human removal after evidence/rollback | 410 only when intentional and approved |

### Existing URLs

- `/carry-on-suitcase-comparison/`: KEEP + MIGRATE in place.
- `/`, `/about-ad-policy/`, `/privacy-policy/`: KEEP routes, revise content/design under human P3 change.
- Unpublished pilot slugs: do not create redirects for URLs never public unless live inventory proves exposure.
- Empty category archives: inventory first. Remove nav exposure immediately in successor design; production noindex/redirect is P3 human action.

## 13. Editorial state machine

```text
DRAFT
  -> EVIDENCE_COMPLETE       [all required claims/identity/freshness valid]
  -> HUMAN_REVIEWED          [named human, exact version]
  -> PACKAGE_SEALED          [deterministic render + hashes + migration manifest]
  -> WP_DRAFT_CREATED        [external human-approved write]
  -> HUMAN_PUBLISHED         [external human action]
  -> PUBLIC_VERIFIED         [read-only checks match sealed package]

Any pre-public state -> BLOCKED / REVIEW_REQUIRED
Public verification failure -> human rollback -> ROLLED_BACK
Semantic input drift invalidates EVIDENCE_COMPLETE/HUMAN_REVIEWED/PACKAGE_SEALED.
```

## 14. Correction and complaint protocol

- Public correction link available on every article.
- Acknowledge potentially critical fact report within 72 hours; immediately disable affected CTA/tool result when harm is plausible.
- Record issue, affected claim/product/routes, severity, source, temporary action, resolution, reviewer, public change log.
- Never delete old evidence to hide error; supersede it.
- Critical defect count is a growth guardrail. One unresolved critical defect blocks Wave expansion.
