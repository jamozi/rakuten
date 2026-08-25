# ST-0904 V2 local public projection candidate

This Story now has an additive, deterministic V2 projector. It accepts only
the exact immutable ST-0903 V2 request/result pair and emits a closed,
public-read-only article document and route fixture for downstream ST-1002.
The fixture contains one article row, allowlisted text-only block rows, one
noindex article route, no product cards, and no offers.

The disclosure copy and `published_at` value are explicit recorded-synthetic
renderer inputs only: the former is not approved Production copy, and the
latter is the ST-0903 local build instant rather than a publication fact.
Freshness is the safe `UNKNOWN` default. Route activation and public serving
remain false, so these fields cannot be mistaken for live-publication evidence.

The omission of product and offer rows is intentional. ST-0903 has exact
product-selection references but no reconciled public product/offer row
source. Creating product UUIDs, prices, affiliate URLs, destination hosts,
images, badges, or comparison facts here would invent values. Heading levels
are also omitted as `null`. Projection generation is the common valid local
value `1`. The four legacy schema discrepancies remain recorded rather than
being silently reconciled.

Every public shape is checked against an explicit closed allowlist. Approval,
article-version, claim, recommendation, source-packet, evidence, AI-raw,
finance, commission, revenue, and secret fields are rejected. Raw HTML and
structured data are not emitted. The public role contract remains
`raos_public_ro` with `readmodel`-only `SELECT` access.

This is a process-local recorded/synthetic candidate, not an activated public
projection. No database, network, job, event, API route, public read, CMS,
publication, staging, release, or Production action is available. Formal
TST-011 and TST-021 remain `NOT_EXECUTED`.

Owner generation:

```text
.venv/bin/python scripts/build_st0904_public_projection_runtime_v2.py
.venv/bin/python scripts/build_st0904_public_projection_runtime_v2.py --check
```

The V1 reference plan remains non-executable and is retained for audit history.
