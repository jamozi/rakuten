# ST-1003 — disabled headless comparison/product semantic candidate

## Result and authority

This Story slice adds one dependency-free strict TypeScript candidate named
`UNREGISTERED_DISABLED_HEADLESS_ST1003_SEMANTIC_METADATA_CANDIDATE`. It records
only the safe semantic boundary for canonical public components `UI-C032`
ProductCard, `UI-C033` ComparisonTable, and `UI-C036` UnknownValue on `PUB-003`.
The canonical Trade-off objective is represented only by three unavailable
semantic slots; no dedicated catalog component ID is invented.

The candidate is unregistered, disabled, headless, noninteractive, and
nonfocusable. It creates no DOM, React/Next component, responsive layout, route,
SSR path, API or read-model request, database/network access, event, tracking,
action, or external effect. Canonical Story status remains `NOT_STARTED` and
verification remains `NOT_EXECUTED`. Local evidence grants no accessibility,
approval, publication, staging, release, or Production authority.

## Safe input and semantic boundary

Input contains only exact `PUB-003`/`/articles/{slug}` metadata and one explicitly
synthetic coordinate whose two caller-supplied lowercase SHA-256 strings must be
equal. The hashes are opaque coordinates: they are not recomputed, canonicalized,
attested, or treated as a verified public projection or comparison.

The fixed candidate declares these requirements without rendering them:

- a comparison caption plus row/column header and `caption`/`headers`/`scope`
  association requirement, with DOM `NOT_IMPLEMENTED` and verification
  `NOT_VERIFIED`;
- preservation of the product/axis relationship on mobile, with no layout or
  presentation selected;
- Unknown must remain visible when eventually rendered and must never be
  imputed, converted to zero, or converted to an empty string; and
- Trade-off keeps separate benefit, cost-or-limitation, and applies-when slots.

All product identity, recommendation, display-policy, comparison table, axis,
selection, claim, and trade-off subject references are null. Product name,
verified facts, image, price, freshness, offers, CTA, comparison matrix, Unknown
value/reason/copy, and Trade-off copy are unavailable or null. No finance,
affiliate, disclosure, ranking, marketing claim, or user-facing copy is added.

Inputs and candidates reject unknown shapes, subclasses, accessors, symbols,
cycles, hostile proxies, content/reference/internal/active fields, malformed or
mismatched hashes, and semantic or authority escalation. Errors expose only
closed codes and never echo hostile values. Successful candidates are detached,
deterministic, JSON-safe, and deeply frozen.

## Why real rendering remains closed

Merged ST-1002 supplies no renderable copy, HTML, payload, DOM, route, or
authoritative projection. ST-0803 is a TEST_ONLY Python validator that supplies
no public matrix, identity, display name, coverage, recommendation, or
publication authority. The Public OpenAPI retains open payload/attribute shapes,
identity-like fields, freshness/offer/CTA data, and no Trade-off block enum.

A value-bearing renderer therefore still requires a canonically reconciled,
owner-approved `DESIGN_HANDOFF_V1` covering the closed public input, ST-0803 to
public mapping, product identity/display/fact authority, Unknown reason/copy,
Trade-off mapping, and exact responsive DOM strategy. Price/freshness,
recommendation, disclosure, and CTA remain separate gated/downstream concerns.

## Owned files and checks

The exact owned paths are:

```text
packages/web-ui/src/comparison-product-components.ts
packages/web-ui/src/index.ts
tests/st1003/comparison-product-components-contract.test.ts
tests/st1003/comparison-product-components-model.test.ts
tests/st1003/comparison-product-components-boundaries.test.ts
tests/st1003/comparison-product-components-negative.test.ts
changes/st-1003/README.md
```

Focused local tests cover the strict contract and critical negative paths.
Affected ST-1002 and ST-0803 suites, TypeScript, ESLint, Prettier, workspace and
canonical no-write checks, sensitive-data scanning, and `git diff --check` are
the local implementation checks. They do not satisfy formal `TST-022` browser
E2E or `TST-024` manual keyboard/zoom/screen-reader/cognitive acceptance.

## Explicitly out of scope

Actual product/comparison/trade-off/Unknown values or copy, product identity,
evidence/facts, price/availability/freshness, recommendation, image, offer,
affiliate CTA/link, disclosure, finance, responsive presentation choice, HTML,
DOM, React/Next, CSS, route registration, SSR, public API/read model, browser,
320 CSS px and assistive-technology execution, formal TST evidence, approval,
publication, live, staging, release, and Production remain unimplemented,
unavailable, unauthorized, or `NOT_EXECUTED`.
