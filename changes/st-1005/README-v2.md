# ST-1005 V2 — fail-closed local SEO metadata routes

## Local result

The current Next.js local preview now serves deterministic `robots.txt` and
`sitemap.xml` metadata routes. The exact recorded article already has
`noindex,nofollow` metadata and response headers. V2 adds the matching global
safe default:

- `robots.txt` has one `User-agent: *` rule with `Disallow: /`;
- `sitemap.xml` is a valid empty URL set; and
- no canonical URL, origin, hostname, route alias, redirect, facet, or
  publication state is invented.

The implementation retains the strict V1 candidate unchanged. The V2 runtime
model binds the one exact recorded article path and records every sitemap
eligibility prerequisite as false because there is no approved current
publication, approved origin, indexable route, self-canonical URL, or live HTTP
evidence. A `noindex` page therefore cannot enter the sitemap.

## Authority boundary

`OD-002` remains unresolved, so the runtime reads no environment variable and
selects no domain. The local metadata routes contain no absolute URL and make
no network, database, provider, analytics, redirect, publication, staging,
release, or Production call. They are local DEV/CI behavior only.

Draft, preview, and facet values remain non-routes in this local app. Root and
article metadata are already `noindex,nofollow`; unknown article paths fail as
non-reflecting 404 responses. This implementation does not turn a missing
route into an indexable page.

Local Node, Next build, and HTTP checks are implementation evidence. Formal
TST-020/TST-022, deployed canonical-graph/uniqueness checks, live HTTP 200,
Search Console validation, staging, publication, release, and Production
remain `NOT_EXECUTED`.
