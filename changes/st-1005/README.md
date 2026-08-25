# ST-1005 — disabled headless SEO route-policy candidate

This file documents the preserved V1 headless boundary. The additive,
locally executable fail-closed runtime is documented in `README-v2.md`.

## Result and authority

This Story slice adds one strict, dependency-free TypeScript candidate named
`UNREGISTERED_DISABLED_HEADLESS_ST1005_SEO_ROUTE_POLICY_CANDIDATE`. It records
only the fixed local semantic boundary for canonical/noindex/sitemap policy on
canonical public screen `PUB-003` and route template `/articles/{slug}`.

The candidate is unregistered, disabled, headless, noninteractive, and
ineligible. It creates no route, sitemap file or entry, robots response, URL,
DOM, React/Next component, SSR path, API/read-model request, database/network
access, browser behavior, publication action, or external effect. Canonical
Story status remains `NOT_STARTED`; verification remains `NOT_EXECUTED`. Local
evidence grants no policy activation, approval, publication, staging, release,
or Production authority.

## Fixed local policy and fail-closed aggregation

The candidate records only consequences fixed by approved policy:

- Draft and Facet require `noindex` and cannot enter a sitemap candidate;
- Preview requires `noindex,nofollow` and cannot enter a sitemap candidate;
- a Public Article cannot become indexable or sitemap-eligible locally; its
  runtime index state remains `NOT_EVALUATED`; and
- future sitemap eligibility requires every caller-resolved fact: published,
  HTTP 200, `index_state = index`, self canonical, not paused, not a redirect
  source, and the current Publication Snapshot.

No sitemap entry or serialized document is emitted. The robots document is
null and never applied. Canonical self-reference and one unique canonical are
recorded only as requirements: current route, canonical route/ref, absolute
canonical URL, route existence/equality, graph acyclicity, and uniqueness are
null or `NOT_EVALUATED`. Publication Snapshot currency, current publication,
HTTP 200, runtime indexability, and pause/redirect-source state are also
`NOT_EVALUATED`. Conditional local eligibility is therefore always false.

This local semantic coverage is not formal execution of content-matrix rows
CT-0911/0912/0913, CT-0923/0924/0925, or CT-0935/0936/0937. Canonical graph,
actual sitemap inclusion, runtime robots/index behavior, route status, and
publication state remain downstream integration and browser evidence.

## Origin and synthetic-input boundary

Input contains only exact `PUB-003`/`/articles/{slug}` metadata, one explicitly
synthetic coordinate whose two caller-supplied lowercase SHA-256 strings must
be equal, and a closed origin mode.

`ROUTE_ONLY` is the default and requires no origin. `CALLER_SUPPLIED_ORIGIN`
accepts only the same normalized HTTPS authority shape as ST-0807: no userinfo,
path, query, fragment, uppercase host, implicit port 443, or unsafe port. The
value is retained solely as `CALLER_SUPPLIED_UNAPPROVED` input. It never selects
a domain, authorizes an origin, constructs or activates an absolute canonical,
or changes eligibility. `OD-002` remains unresolved; no site name, domain,
operator identity, environment fallback, DNS lookup, persistence, or allowlist
selection is introduced.

Inputs and candidate validation reject unknown shapes, subclasses, accessors,
symbols, cycles, unreadable or throwing proxy surfaces, malformed/mismatched
hashes, origin-mode disagreement, copy/HTML/payload/URL injection, internal
fields, effects, policy drift, and authority escalation. Errors contain only
closed stable codes and never echo hostile values. Successful values are
detached, deterministic, JSON-safe, and deeply frozen.

## Why runtime SEO routes remain closed

Merged ST-1002 supplies no renderer, route, public-read-model input, or
authoritative projection. ST-0903 and ST-0904 are non-executable reference
plans: there is no authoritative current Publication Snapshot, exact public
allowlist/projector, current publication, or current route selection. ST-0807
correctly treats canonical graph, route existence, HTTP 200, runtime
indexability, pause/redirect-source state, and snapshot currency as external
assessments and leaves unavailable evidence `NOT_EVALUATED`.

A value-bearing or runtime implementation therefore requires separately
approved, canonically reconciled authority for current snapshot/publication and
route selection, public projection, site configuration, canonical graph and
uniqueness, facet/redirect policy, sitemap ownership/publication, and robots
delivery. It may not resolve `OD-002` by choosing a site origin or domain.

## Owned files and checks

The exact owned paths are:

```text
packages/web-ui/src/seo-route-policy.ts
packages/web-ui/src/index.ts
tests/st1005/seo-route-policy-contract.test.ts
tests/st1005/seo-route-policy-model.test.ts
tests/st1005/seo-route-policy-negative.test.ts
tests/st1005/seo-route-policy-boundaries.test.ts
changes/st-1005/README.md
```

Focused local tests cover the strict contract and critical negative paths.
Affected ST-1001 through ST-1004, dependency ST-0807, TypeScript, ESLint,
Prettier, workspace and canonical no-write checks, sensitive-data scanning, and
`git diff --check` are the local implementation checks. They do not satisfy
formal `TST-020` content/runtime or `TST-022` browser E2E evidence.

## Explicitly out of scope

Actual routes/slugs/facets/redirects, route registration, site configuration,
origin/domain selection, canonical route/ref/URL activation, canonical graph or
corpus validation, sitemap entries/XML/lastmod/publication, robots response or
runtime behavior, current snapshot/publication/route facts, HTML/DOM/React/
Next/CSS/SSR, API/read model/database/network/browser, analytics/tracking,
formal TST evidence, approval, publication, live, staging, release, and
Production remain unimplemented, unavailable, unauthorized, or
`NOT_EXECUTED`.

The canonical, generated, and status artifacts are not edited by this local
candidate.
