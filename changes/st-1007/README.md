# ST-1007 — disabled accessibility evidence-requirements candidate

## Result and authority

This Story slice adds one strict, dependency-free TypeScript candidate named
`UNREGISTERED_DISABLED_HEADLESS_ST1007_ACCESSIBILITY_EVIDENCE_REQUIREMENTS_CANDIDATE`.
It is only a deterministic reference plan for the approved public accessibility
checklist and its required evidence environments.

The candidate is unregistered, disabled, headless, noninteractive, and
ineligible. It creates no route, renderer, DOM, HTML, React/Next component, CSS,
browser session, axe/Playwright run, keyboard interaction, zoom observation,
screen-reader session, API/read-model request, database/network access, event,
action, publication, or other external effect. Canonical Story status remains
`NOT_STARTED`; verification and formal `TST-023`/`TST-024` remain
`NOT_EXECUTED`.

No local value is an accessibility result. The candidate does not claim WCAG
2.2 AA conformance, checklist PASS, browser behavior, approval, publication,
staging, release, or Production authority.

## Exact checklist and UI boundary

The candidate retains the exact 30 canonical rows `A11Y-001` through
`A11Y-030`, including their requirement, reference, verification method, and
unchanged `NOT_STARTED`/`NOT_EXECUTED` states. It maps the canonical method
vocabulary only to the required suite IDs:

- `automated` requires `TST-023`;
- `automated+manual` requires `TST-023` and `TST-024`; and
- `manual` and `screen-reader` require `TST-024`.

Every item remains `applicability = NOT_EVALUATED`,
`executionStatus = NOT_EXECUTED`, and `verificationResult = NOT_VERIFIED`, with
no evidence reference, environment, evaluator, or execution time. The model
does not accept caller-claimed evidence, PASS, N/A, or conformance input.

The catalog projection retains all ten canonical public screens `PUB-001`
through `PUB-010` only as unchanged metadata. It retains exactly the eight
components already represented by safe dependency or transitive-dependency
candidates: `UI-C002` PublicHeader, `UI-C003` PublicFooter, `UI-C004`
Breadcrumbs, `UI-C031` DisclosureBanner, `UI-C032` ProductCard, `UI-C033`
ComparisonTable, `UI-C034` AffiliateCTA, and `UI-C036` UnknownValue. This is not
an applicability assignment. No ownership or coverage is inferred for other
public/shared components.

## Dependency and evidence boundary

Merged ST-1003, ST-1004, and ST-1005 are deliberately disabled, unregistered,
headless candidates. They provide no DOM, route, browser, keyboard, zoom,
screen-reader, responsive, or acceptance evidence. Their fixed component
metadata and safe semantics therefore cannot satisfy ST-1007.

The candidate retains the exact required suite environments without executing
them:

- `TST-023` is release-blocking automated accessibility in CI, owned by
  Engineering, with axe-core and Playwright as candidate tools; and
- `TST-024` is release-blocking manual accessibility in staging, owned by
  QA/Accessibility, with Keyboard, Zoom, Screen reader, cognitive checks, and
  NVDA/VoiceOver plus the manual checklist.

Real acceptance requires an actual public runtime/DOM and the complete formal
evidence above. Automated checks alone cannot establish conformance. Until both
suites and every applicable checklist item have valid evidence, aggregate P0
PASS, all-items verified, conditional local eligibility, formal evidence, and
accessibility conformance remain false.

## Public isolation and strict input

The input contains only `ST-1007` and an explicitly synthetic coordinate whose
two caller-supplied lower-case SHA-256 strings must be equal. The hashes are
opaque coordinates: they are not recomputed, canonicalized, attested, or
treated as UI, browser, accessibility, audit, or formal evidence.

Validation rejects unknown shapes, malformed or mismatched hashes, subclasses,
accessors, symbols, cycles, hostile proxies, content/markup, internal editorial,
evidence, finance or AI fields, claimed evidence/execution, effects, and
authority escalation. Errors expose only closed codes and never echo hostile
values. Successful candidates are detached, deterministic, JSON-safe, and
deeply frozen. Public Web isolation remains closed: no Editorial, Evidence,
Finance, or AI raw artifact is queried or projected.

## Frontend design influence

The frontend design guidance is applied as an operational evidence register:
orientation, current evidence state, and blockers take precedence over visual
decoration or marketing copy. Because no DOM is authorized, this slice selects
no layout, card treatment, color, typography, motion, interaction, or responsive
presentation and makes no visual-quality claim.

## Owned files and local checks

The exact owned paths are:

```text
packages/web-ui/src/public-accessibility-acceptance.ts
packages/web-ui/src/index.ts
tests/st1007/public-accessibility-contract.test.ts
tests/st1007/public-accessibility-model.test.ts
tests/st1007/public-accessibility-boundaries.test.ts
tests/st1007/public-accessibility-negative.test.ts
changes/st-1007/README.md
```

Focused tests cover exact catalogs, suite mapping, deterministic immutability,
zero-side-effect boundaries, and critical negative paths. Affected predecessor
suites, TypeScript, ESLint, Prettier, workspace and canonical no-write checks,
sensitive-data scanning, and `git diff --check` are local implementation checks
only. They do not constitute TST-023, TST-024, browser, assistive-technology,
staging, release, or Production evidence.

## Explicitly out of scope

Actual HTML/DOM/React/Next/CSS, route registration, renderer integration,
accessibility remediation, checklist applicability decisions, exception/N/A
policy, browser automation, axe execution, Keyboard, Focus, 200% Zoom, 320 CSS
px responsive behavior, NVDA/VoiceOver or equivalent Screen reader execution,
cognitive review, real evidence ingestion or persistence, CI/staging execution,
WCAG conformance, approval, publication, live, release, and Production remain
unimplemented, unavailable, unauthorized, `NOT_EVALUATED`, `NOT_VERIFIED`, or
`NOT_EXECUTED`.

Canonical, upstream, generated, status, lock, and workflow artifacts are not
edited by this local candidate.
