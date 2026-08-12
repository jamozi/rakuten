# ST-1002 — disabled headless public article renderer candidate

## Result and authority

This Story slice adds one dependency-free strict TypeScript candidate named
`UNREGISTERED_DISABLED_HEADLESS_PUBLIC_ARTICLE_RENDERER_CANDIDATE`. It records
the safe interface boundary for canonical screen `PUB-003` and route template
`/articles/{slug}`. It does not render an article and does not satisfy ST-1002
acceptance.

The route is unregistered, noninteractive, and nonfocusable. Metadata is
route-only, carries no title, description, canonical URL, or site identity, and
is fixed to `noindex,nofollow`. No React/Next component, DOM, SSR path, browser
behavior, API request, network access, database/read-model access, event,
tracking call, publication action, or external effect is introduced.

Canonical Story status remains `NOT_STARTED`; verification remains
`NOT_EXECUTED`. Formal `TST-021`, `TST-022`, and `TST-023`, browser,
accessibility, live, staging, publication, release, and production work remain
`NOT_EXECUTED` or unauthorized. No local result grants approval, publication,
release, or production authority.

## Why content rendering remains closed

Merged dependency ST-0904 is an expressly non-executable, non-authoritative
Public Read Model reference plan. It supplies no projector, public rows, exact
confidential-snapshot-to-public allowlist, current snapshot/route selection, or
runtime public-isolation proof. Its ST-0903 predecessor likewise supplies no
authoritative snapshot instance or executable builder.

Installed Publication Snapshot, Content AST, and Public OpenAPI surfaces are
not reconciled into one authoritative render input. In particular, the two AST
shapes differ and the Public API permits open payload/HTML shapes that this
slice cannot safely treat as public. A real renderer therefore requires an
owner-approved, canonically reconciled `DESIGN_HANDOFF_V1` with no open
decisions. It must define AST precedence, the exact public allowlist/redaction
mapping, closed public block payloads, HTML/sanitizer policy, snapshot and
projection hash semantics, and current route-selection behavior.

## Implemented safe boundary

The candidate accepts only a strict plain JSON tree containing:

- the exact `PUB-003` screen and `/articles/{slug}` route template;
- one explicitly synthetic public-projection coordinate;
- equal caller-supplied lower-case SHA-256 strings; and
- zero or more ordered metadata-only block slots.

Hashes are opaque caller coordinates. The candidate compares them for exact
equality but does not recompute, canonicalize, attest, or call them a verified
snapshot or projection. An empty slot list means no renderable material or
evidence, not a successful projection.

Slots may use only generic non-downstream block labels and expose no copy,
HTML, or payload. Comparison tables and product cards remain ST-1003; affiliate
disclosure and CTA remain ST-1004; freshness and safe degradation remain
downstream work. The candidate emits none of those surfaces and no structured
data, links, internal article/publication/approval IDs, claims, evidence,
finance, AI raw data, or source packets.

Validation rejects unknown shapes, non-null content/HTML/payload, active markup
or schemes, downstream and internal fields, wrong or mismatched hashes, route
or position drift, duplicate block keys, subclasses, accessors, symbols,
cycles, hostile proxies, and execution or authority escalation. Failures use
closed codes and do not echo hostile values. Successful values are detached,
deterministic, JSON-safe, and deeply frozen.

## Owned files and local checks

The exact owned files are:

```text
packages/web-ui/src/public-article-renderer.ts
packages/web-ui/src/index.ts
tests/st1002/public-article-renderer-contract.test.ts
tests/st1002/public-article-renderer-model.test.ts
tests/st1002/public-article-renderer-boundaries.test.ts
tests/st1002/public-article-renderer-negative.test.ts
changes/st-1002/README.md
```

Focused local checks cover the strict contract and critical negative paths.
They remain local unit/static evidence only and are not formal TST or runtime
evidence.

## Explicitly out of scope

Actual article copy, HTML, payload mapping, sanitization, React/Next, DOM, SSR,
runtime route registration, slug resolution, API/adapter/database/read-model
access, snapshot/projector implementation, comparison/product/disclosure/CTA,
SEO structured data, freshness, analytics/RUM, brand/domain/operator/privacy
copy, browser and assistive-technology execution, approval, publication,
staging, release, and production are not implemented.
