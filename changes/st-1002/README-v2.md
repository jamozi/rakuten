# ST-1002 V2 — recorded public article SSR

## Local result

This additive V2 implementation registers one Next.js App Router server route,
`/articles/synthetic-recorded-policy-seo`, for local DEV/CI preview. It consumes
only the exact owner-generated ST-0904 V2 recorded fixture. The owner generator
pins both the fixture SHA-256 and its independently recomputed public projection
SHA-256, strips public-record identifiers, and emits a closed TypeScript source.
The runtime mapper accepts no other source tree and no other slug.

The existing disabled V1 headless candidate and its hostile-input protections
remain available. V2 carries those protections forward: strict plain trees,
no accessors/subclasses/symbols/cycles/proxies, exact source equality, closed
errors, detached values, and deep immutability.

## Rendered boundary

The route server-renders escaped text with Japanese semantic structure: skip
link, header/navigation, visible breadcrumb, main/article, one H1, explicit
advertising disclosure, local-preview and unknown-freshness notices, and six
source-backed sections. The empty ST-0904 comparison block and empty source
summary are omitted. ST-1002 does not create or render product cards, offers,
CTA, comparison data, JSON-LD, canonical URL, images, article/publication IDs,
operator identity, site/domain values, or unrecorded facts.

Metadata and the exact article-path response are `noindex,nofollow` with
noarchive/nosnippet/noimageindex, CSP `script-src 'none'`, no-store caching,
and defensive isolation headers. The implementation has no client component,
raw HTML, DB/API/provider/network call, cookies, storage, analytics, tracking,
event, persistence, or external write. An unknown or malformed slug returns a
non-reflecting 404.

## Authority

This is local reversible implementation evidence only. The source projection's
route remains inactive and `public_read_served` remains false. Publication,
staging, release, Production, live provider activity, and Status Registry APPLY
are not authorized or executed. Formal TST-021/TST-022/TST-023 remain
`NOT_EXECUTED`; local Node/Next/browser/axe checks are not promoted to those
formal suites.

Owner generation:

```text
.venv/bin/python scripts/build_st1002_public_article_renderer.py
.venv/bin/python scripts/build_st1002_public_article_renderer.py --check
```
