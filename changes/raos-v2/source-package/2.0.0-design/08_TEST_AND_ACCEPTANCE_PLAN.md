# Test and Acceptance Plan

## 1. Test strategy

The test system proves three distinct things without conflation:

1. **Design/contract correctness:** entities, states, algorithms and traceability are closed and deterministic.
2. **Local implementation quality:** recorded inputs render a usable vertical slice with no network/secret/publication capability.
3. **External/public correctness:** only after human action, read-only verification shows the intended WordPress/public state and rollback evidence.

A local pass is never called staging/Production evidence. Automated accessibility checks are not WCAG conformance. A recorded Rakuten fixture is not a live provider validation. A WordPress payload preview is not a draft/publication receipt.

## 2. Evidence naming and retention

Each test run emits a run ID such as `RAOSV2-<UTC timestamp>-<short commit>` and records:

- commit/tree/dirty status and environment class;
- tool versions and dependency lock result;
- test IDs, result, duration, failure code;
- fixture/source/schema versions and semantic hashes;
- generated output drift;
- browser/version/viewport/media preferences;
- screenshots/DOM/accessibility tree/network log where applicable;
- secret scan summary without matched secret bytes;
- external actions executed/not executed;
- evidence classification: `LOCAL`, `CI`, `OWNER_PRIVATE`, `PUBLIC_READ_ONLY`, `STAGING`, `PRODUCTION`.

Repository evidence may not include credentials, raw private exports, personal data, raw prompts or prohibited provider material. Owner-private data is referenced by source hash/receipt, not committed.

## 3. Test layers

### Unit

Pure rules: dimension/weight/count comparison, effective-date resolution, identity normalization/rejection, fit score, freshness boundaries, QDS, attribution/profit formula. Use fixed decimal semantics, frozen clocks and property/boundary tests.

### Contract

YAML/JSON schemas, closed enums, required/unknown key policy, generator ownership, interface request/response envelopes, state transitions, event allowlist, publication seal.

### Integration

Source→claim→decision→article→render→SEO/package; recorded Rakuten→identity→offer/media→CTA; events→QDS; provider import→attribution→profit. Network remains denied in P0–P2.

### Browser/visual

Chromium at 390×844, 768×1024, 1440×900 plus 360 regression; 200% text zoom; 320px/reflow equivalent; no-JS; long model/source text; missing image/offer/related; PASS/FAIL/UNKNOWN/STALE/ERROR; consent states.

### Accessibility

Automated axe-equivalent, HTML semantics, keyboard path, focus visibility/not obscured, screen-reader smoke/accessibility tree, live regions, form labels/errors, table/mobile parity, contrast, forced colors, reduced motion. Human review required.

### SEO

Status/route/canonical/robots/sitemap/lastmod, one H1 and heading order, metadata uniqueness, link graph/orphans, redirect chain/loop, JSON-LD-visible-content match, no empty indexable archive.

### Security

Immutable/dirty path, secret scan, denied network, URL allowlist, sanitization, no publish capability, no PII event fields, local/public/internal/finance separation, dependency/lock checks.

### Migration/rollback

Before/after inventory, one-hop redirect, package/public hash, rollback manifest round-trip, WordPress dry-run diff, public verification and human rollback rehearsal in P3.

### Analytics/finance

Event allowlist, QDS deterministic sequence, no personal identifiers, attribution classes, maturity, provider total reconciliation, pending exclusion, cash/economic formulas, non-interference with recommendations.

### UAT

Reader can answer the declared JTBD, understand evidence/unknown/trade-off, operate on mobile/keyboard, reach official source and exact affiliate destination without pressure. Owner confirms Japanese naturalness and publication scope.

## 4. Exact acceptance catalog

## SECURITY

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-001 | immutable paths remain byte-identical | R-V2-001 | git diff path assertion |
| T-V2-002 | dirty/unrelated paths are not edited or staged | R-V2-001, R-V2-002 | pre/post status comparison |
## CONTRACT

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-003 | live preflight records AGENTS/HEAD/branch/status/generator owner | R-V2-002 | preflight JSON schema |
| T-V2-007 | product spec contains one wedge and locked portfolio waves | R-V2-005 | schema + invariant |
| T-V2-009 | every route has one primary intent/template/parent hub | R-V2-007 | route registry validation |
| T-V2-011 | claim enum permits A/D/UNKNOWN only in initial V2 | R-V2-008 | schema negative cases |
## DATA

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-004 | URL inventory parses sitemap, canonical, robots and status | R-V2-003 | inventory fixture diff |
| T-V2-015 | product model dimensions include units and external/expanded states | R-V2-010 | schema test |
| T-V2-016 | ambiguous model/variant/accessory identity is rejected | R-V2-010, R-V2-027 | negative identity matrix |
## MIGRATION

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-005 | redirect map rejects loops, chains >1 and many-to-home | R-V2-003, R-V2-025 | negative redirect fixtures |
| T-V2-025 | existing comparison retains exact public slug and one H1 | R-V2-015 | route/render test |
| T-V2-040 | rollback manifest restores previous content/route metadata in simulation | R-V2-025 | round-trip test |
## ANALYTICS

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-006 | metric dictionary rejects missing source/maturity/unavailable rule | R-V2-004 | schema validation |
| T-V2-045 | event collector rejects raw IP/UA/referrer/query/email and unknown attributes | R-V2-029 | allowlist tests |
| T-V2-046 | QDS sequence, 30-minute rotation and dedupe are deterministic | R-V2-029 | event sequence tests |
## VISUAL

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-008 | design token contrast pairs meet declared AA thresholds | R-V2-006 | contrast report |
## SEO

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-010 | no orphan or empty indexable taxonomy route | R-V2-007, R-V2-022 | link graph report |
| T-V2-035 | title/description/canonical/robots/sitemap are internally consistent | R-V2-022 | SEO contract suite |
| T-V2-036 | JSON-LD matches visible Article/Breadcrumb/Organization/WebSite only | R-V2-022 | structured data snapshot |
## EDITORIAL

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-012 | A claim without allowed primary source fails | R-V2-008, R-V2-009 | unsupported claim fixture |
| T-V2-013 | B/C claim and false hands-on language fail | R-V2-008, R-V2-020 | language/claim fixtures |
| T-V2-019 | each article template enforces required block order | R-V2-012 | template contract tests |
| T-V2-024 | guide contains disclosure, 30-second conclusion, unknowns and official links | R-V2-014, R-V2-020 | render DOM assertions |
| T-V2-026 | comparison names exact 3-model scope and no universal winner | R-V2-015, R-V2-020 | copy contract |
| T-V2-027 | difference page rejects query overlap with comparison above threshold | R-V2-016 | intent similarity fixture |
| T-V2-033 | quality gate rejects missing fit/non-fit/trade-off/unknown/disclosure | R-V2-020 | negative packet fixtures |
## FRESHNESS

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-014 | hard-stale high-risk claim blocks package seal | R-V2-009, R-V2-021 | clock-controlled test |
| T-V2-034 | SLA classification is deterministic at exact boundaries | R-V2-021 | frozen clock matrix |
## RULE

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-017 | airline rule effective date and fare/aircraft variant resolve deterministically | R-V2-011 | rule fixtures |
| T-V2-018 | missing route/aircraft/fare information returns UNKNOWN not PASS | R-V2-011, R-V2-013 | unknown case fixtures |
## TOOL

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-020 | checker returns PASS for exact compatible fixture with cited rule | R-V2-013 | unit snapshot |
| T-V2-021 | checker returns FAIL for any single-edge violation | R-V2-013 | boundary-value matrix |
| T-V2-022 | checker handles orientation by all permitted permutations only when rule allows | R-V2-013 | dimension permutation tests |
## PRIVACY

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-023 | checker makes no network request and stores no input persistently | R-V2-013, R-V2-034 | browser network/storage assertion |
## RECOMMENDATION

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-028 | hard-ineligible product can never be ranked | R-V2-017 | property test |
| T-V2-029 | fit score is deterministic and tie-break is model ID | R-V2-017 | property/snapshot test |
## FINANCE

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-030 | finance input changes do not change product order or render hash | R-V2-018 | non-interference test |
| T-V2-048 | pending/immature outcomes excluded from EPC/RPM/profit | R-V2-030, R-V2-031 | maturity fixture |
| T-V2-049 | cash/economic profit and payback formulas preserve JPY/JST/version | R-V2-031 | formula test |
## AI_GOV

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-031 | AI-originated text lacks seal without human reviewer/version | R-V2-019 | state transition negative test |
| T-V2-032 | correction rate numerator/denominator is reproducible | R-V2-019 | calculation test |
## PUBLICATION

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-037 | package digest changes for any semantic input drift | R-V2-023 | tamper test |
| T-V2-038 | sealed package rejects missing review/source/target binding | R-V2-023 | negative schema cases |
## NETWORK

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-039 | WordPress adapter defaults disabled and dry-run emits no request | R-V2-024, R-V2-034 | network denial test |
## RAKUTEN

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-041 | 2026-07-01 recorded response parses without credentials | R-V2-026 | contract fixture |
| T-V2-042 | unknown/missing response fields fail or become UNKNOWN per schema | R-V2-026 | mutation test |
## IDENTITY

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-043 | case/spacing alone normalize but model generation/accessory never normalize | R-V2-027 | identity mutation matrix |
## ATTRIBUTION

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-047 | unattributed program reward cannot populate article confirmed reward | R-V2-030 | reconciliation test |
## GATE

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-050 | experiment report blocks multi-variable or insufficient-maturity decision | R-V2-032 | gate negative cases |
## UAT

| Test ID | Acceptance test | Requirements | Evidence |
| --- | --- | --- | --- |
| T-V2-051 | phase exit report includes outcome, tests, rollback, cost, gaps and external NOT_EXECUTED | R-V2-033, R-V2-034, R-V2-035, R-V2-036 | UAT checklist and signed local evidence |


## 5. Browser scenario matrix

| Scenario | 390 | 768 | 1440 | Assertions |
| --- | --- | --- | --- | --- |
| Home with one guide | required | required | required | hero/CTA/proof order; no empty cards; disclosure visible |
| Home with zero/three guides | required | spot | required | omit empty; stable grid without fake content |
| Checker empty input | required | spot | required | no default carrier; labels/units/help; no request |
| Checker exact PASS | required | required | required | all criteria/source/effective date; no guarantee wording |
| Checker single-edge FAIL | required | spot | required | failed edge clear; alternatives; no buy-now CTA |
| Checker UNKNOWN | required | required | required | missing input resolution; no false pass |
| Checker HARD_STALE/error | required | spot | required | definitive result disabled; reset works |
| Guide long Japanese/source title | required | spot | required | wrap/reflow/heading/source chips |
| Comparison exact 3 models | required dl | breakpoint | required table | semantic parity; fit/non-fit/unknown/CTA |
| Comparison no image/no offer | required | spot | required | neutral state; no unbound CTA |
| Long model/unknown fields | required | spot | required | no overflow/misalignment |
| Consent rejected/accepted/unconfigured | required | spot | required | content/focus not obscured; event behavior |

## 6. Accessibility manual path

1. Load page with mouse unavailable.
2. First Tab focuses visible skip link; activate and confirm main focus.
3. Traverse header/menu/disclosure/tool fields/result/source/CTA/footer in reading order.
4. Submit empty form; focus moves to error summary and each field relation is announced.
5. Complete PASS/FAIL/UNKNOWN cases; result status announces once without stealing focus unexpectedly.
6. At 200% text and 320px equivalent, confirm no loss/overlap/page horizontal scroll.
7. Turn on forced colors and reduced motion; state/focus/content remain distinguishable.
8. Screen-reader smoke: landmarks/headings/table/dl/form/link purpose/alerts.
9. Verify consent surface does not hide current focus or the primary task and can be dismissed/configured.
10. Compare desktop table and mobile definitions for every normalized criterion/value/evidence/unknown.

## 7. Visual review

Visual regression snapshots are deterministic and exclude volatile price/stock. Baseline approval requires human review at P2. Pixel diff is supporting evidence; a small diff cannot overrule semantic/UX defects.

Severity:

- **Critical:** wrong/misleading decision, wrong CTA/model, hidden disclosure, inaccessible task, lost data, obscured focus/content.
- **Major:** serious readability/hierarchy/overflow/state inconsistency/performance budget failure.
- **Minor:** polish without decision impact.

P2/P3 exit: critical=0, major=0. Minor can remain only with exact issue, owner, phase and no contract violation.

## 8. Performance test

- Build-time bundle report enforces article JS≤60KB gzip, CSS≤40KB gzip.
- Test page transfer with fixture assets: article≤1.2MB, home/tool≤800KB initial.
- Lighthouse/lab results are diagnostic, not field CWV. Record device/network parameters.
- Public P4 uses field p75 when available: LCP≤2.5s, INP≤200ms, CLS≤0.1. Insufficient data is UNAVAILABLE and extends observation.
- Confirm images have intrinsic dimensions, no external font request, no third-party request before approval/consent.

## 9. SEO and migration acceptance

Before P3 human action:

- local target route equals inventory/migration manifest;
- preserved public slug exactly `/carry-on-suitcase-comparison/`;
- canonical target self; no accidental trailing/path variant;
- one H1; title/meta unique; Article/Breadcrumb visible-content parity;
- redirect simulation hop≤1, loop=0, no broad home redirect;
- previous public content/metadata/theme/URL hash and restore procedure available.

After P3 action, read-only public verify:

- expected HTTP status and canonical;
- robots and sitemap inclusion consistent;
- H1/disclosure/method/checked date markers present;
- official and affiliate links exact and valid enough for bounded check;
- package/public semantic fingerprint matches or a documented platform normalization explains only nonsemantic differences;
- mobile/desktop screenshots and critical a11y smoke pass;
- if any critical item fails, owner invokes rollback and records result.

## 10. Analytics acceptance

- Production event sender defaults OFF.
- Local browser network assertion shows zero event/provider request.
- Allowlisted event rejects unknown keys and forbidden raw IP/UA/referrer/query/email/name/address/order ID.
- Session token is ephemeral, random, sessionStorage-only, HMAC stored server-side, rotates after 30 minutes.
- QDS calculation is idempotent and deduplicated per session/article/qualified condition.
- Rejected/no consent produces no nonessential event; site and outbound links remain usable per approved policy.
- Provider outcome import reconciles exact provider total and distinguishes PENDING/IMMATURE/CONFIRMED/CANCELLED.
- `UNATTRIBUTED_PROGRAM` cannot produce article confirmed EPC/RPM/profit.
- Finance input mutation does not change recommendation/render hash.

## 11. Security negative tests

- Attempt to add output under immutable path.
- Attempt to read secret-like environment/fixture into log.
- Attempt live HTTP in recorded/default mode.
- `javascript:`, `data:`, non-HTTPS or unapproved outbound URL.
- Provider HTML/script injection in item name/source text.
- WordPress port invoked without disabled flag/valid seal/approval binding.
- Stale/tampered seal, mismatched target route, changed source/review hash.
- Product accessory/old generation/ambiguous variant receiving CTA.
- Event with personal identifier/unknown attribute.
- Public/internal finance object serialized into public article.

All fail closed without printing matched secret or sensitive bytes.

## 12. UAT scripts

### UAT-01 Existing bag check

Given an airline/date and bag dimensions/weight, the owner can obtain PASS/FAIL/UNKNOWN, understand each criterion and reach the final official rule. Pass requires no external event and no purchase CTA pressure.

### UAT-02 New product shortlist

Given “Peach、合計7kg、外寸制約、軽さ優先”, the owner can see only eligible exact variants, why each fits, what is lost, and how to verify the exact model at Rakuten. Any unresolved identity blocks CTA.

### UAT-03 No suitable product

A condition with no eligible candidate renders “該当なし”, alternatives and official confirmation. It does not force the least-bad product.

### UAT-04 Evidence trust

A reader can identify A fact, D judgement, UNKNOWN, checked date, source and no-hands-on disclosure before concluding.

### UAT-05 Mobile/keyboard

At 390px and keyboard-only, primary task, result, source and correction path are usable; consent does not obscure content/focus.

### UAT-06 Publication operator

Owner can inspect exact sealed diff/target/rollback and create at most one draft under separate approval. Codex cannot publish/schedule/delete.

### UAT-07 Economics integrity

Owner can import a sanitized mature provider report, reconcile totals and see which metrics are DIRECT/COHORT/UNATTRIBUTED; product order is unchanged.

## 13. Phase exit matrix

| Phase | Required tests | Evidence focus | Claim boundary |
| --- | --- | --- | --- |
| P0 | T-V2-001–007, 051 | read-only inventory, immutable/dirty safety, metrics schema, URL/redirect simulation | No production claim |
| P1 | T-V2-007–019, 051 | contracts, route, claim/source/product/rule/template/tokens | No public feature claim |
| P2 | T-V2-020–051 as applicable | decision engine, preview, SEO, browser, a11y, security, publication/analytics disabled | PASSED_LOCAL only |
| P3 | P2 regression + T-V2-035–046 + public read-only verification | one URL, exact seal, rollback, real viewport/public metadata | External human actions recorded separately |
| P4 | release regression + freshness/link/event/query checks + T-V2-050/051 | Wave gates and field evidence | Search/provider data may be UNAVAILABLE |
| P5 | T-V2-047–051 | mature outcome reconciliation and unit economics | Owner-private evidence; no recommendation effect |
| P6 | full security/SEO/route/traceability regression + T-V2-051 | new category cannot weaken invariants | Separate design/release decision |

## 14. Traceability quality gate

Machine validation before package/PR completion:

- exactly 34 decision IDs, 36 requirement IDs, 49 backlog IDs and 51 test IDs;
- IDs unique and all cross-references exist;
- every decision has at least one requirement;
- every requirement has at least one backlog and test;
- every backlog requirement exists and dependencies are acyclic;
- every test requirement exists;
- all external actions remain `NOT_EXECUTED` in this design package;
- no `TODO`, `TBD`, `choose A/B`, secret value or implementation source file in the design ZIP.
