# ST-0807 — recorded SEO render boundary V2

Local status: `LOCAL_IMPLEMENTATION_COMPLETE`.

The existing V1 pure renderer remains byte-compatible. This additive V2 owner
path proves that it can consume the current ST-0802/ST-0805 local dependency
chain without inventing any external fact. The generator loads the recorded
synthetic ST-0805 fixture, validates its immutable ST-0802 DRAFT binding,
recomputes the complete ST-0805 policy report, and binds that report hash to the
single evaluated external assessment.

The recorded request is deliberately `PREVIEW`, `noindex`, `nofollow`, and
`ROUTE_ONLY`. It has no selected origin, site identity, or production domain.
The V1-required date fields use a recorded synthetic preview input explicitly
labelled `NOT_PUBLICATION_FACT`; the bound ST-0802 DRAFT has no published
timestamp, and V2 does not claim one.
ST-0805 policy eligibility is the only `PASS`; title corpus, canonical graph,
browser equality, HTTP/route state, publication snapshot, image, cache, CTA,
affiliate-link, and redirect checks remain `NOT_EVALUATED`. Missing or
unverified evidence is never promoted to PASS.

JSON-LD is rendered exclusively by the deterministic V1 allowlist. The
recorded graph contains one `Article` whose visible title, author, dates, and
content hash are bound through the renderer ledger. `Product`, `Offer`,
`Review`, `AggregateRating`, and `FAQPage` remain recursively prohibited.
Arbitrary HTML and LLM-authored JSON-LD are not accepted.

Generate and verify the owner artifacts with the exact locked command:

```bash
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run --locked --offline --no-cache --no-sync --no-env-file --no-python-downloads python scripts/build_st0807_seo_render_runtime.py
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run --locked --offline --no-cache --no-sync --no-env-file --no-python-downloads python scripts/build_st0807_seo_render_runtime.py --check
```

The owner uses the hash-bound shared publication transaction. It preserves
foreign files, rejects symlink/hardlink destinations, detects source identity
changes, and fails closed on drift. The generated result grants no approval,
policy-apply, article-mutation, domain, publication, release, or Production
authority.

Formal TST-020/TST-022, hosted CI, browser/DOM/HTTP validation, live checks,
site/domain selection, staging, publication, release, and Production remain
`NOT_EXECUTED`.
