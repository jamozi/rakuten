# Editorial V3 portfolio and owner-private economics

`editorial-portfolio.v3.json` is an additive, generated successor to Editorial
V2. It covers the current ten articles and thirty-one products without changing
the historical V2 contract. `generated/navigation.v3.json` is the single
machine-readable home/related-article source.

`editorial-identities.v1.json` also classifies every existing article as a
category guide, brand/model-family comparison, constraint shortlist, feature
shortlist, or two-product comparison. The generated navigation carries the
reader-facing Japanese role label, the exact comparison scope, and a broader
article route for narrow comparisons so a narrow article cannot silently pose
as a market-wide ranking. It also owns the primary query intent: intents must
be unique within an intent group and the browser audit requires the visible
`記事分類` and `この記事で答えること` values to match this contract exactly.

`market-candidate-audit.v1.json` is the named-candidate negative-space audit.
It records all seven selection axes, concrete current or recently excluded
models, lifecycle evidence, exclusion reasons, and scope separation for all ten
articles. Each article declares non-empty hard filters and official category
sources. Each named candidate binds an exact model and variant scope, use role,
separate model/variant lifecycle, reader-visible and embedded lifecycle
observations, and an `EXCLUDED` or `DEFERRED` disposition. Products already in
the portfolio reuse their product identity through a `REFERENCE_ONLY` binding
to the article that actually includes them; they are never duplicated as
`EXT-*` candidates. The selected product list is the included disposition. The
reader-visible lifecycle governs the effective state; an embedded mismatch is
recorded as `CONFLICT`. `RESTOCK_NOTIFICATION_ONLY` records the narrower case
where the visible store offers only a restock notice and no cart action; it is
kept distinct from an explicit `SOLD_OUT` statement. Generic unnamed alternatives,
audits containing only already-selected products, decision-critical unknowns,
missing reader-visible exclusions, and price/reward/Rakuten weighting are
rejected by the V3 generator.

Article-wide guidance does not establish product-specific due diligence. The
market audit therefore mirrors the current V2 selection audit: safety/recall,
Japan-region warranty/support, and maintenance/repair/consumables remain
`SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED` until every selected product
is bound to locator-backed official evidence. Each incomplete axis has a
recheck date, is excluded from recommendation rationale, and blocks strict
publication. The generator rejects an article-level official link being
promoted to product-level completion.

The tracked Rakuten parser boundary is intentionally disabled. It contains no
guessed live column names or status values. A parser can be enabled only inside
`.secrets/editorial-portfolio-v3/` after a sanitized real export sample is
detected, mapped, owner-attested, and shown to echo one of the V3 measurement
IDs. The private directory must be mode `0700`; every input and output file must
be mode `0600`.

## Deterministic generation

```sh
.venv/bin/python scripts/build_editorial_portfolio_v3.py
.venv/bin/python scripts/build_editorial_portfolio_v3.py --check
```

## Private Rakuten workflow

Editorial V2 owns the full ten-article, thirty-one-product and seventy-four-CTA
capture contract. Development preview may render a clearly labelled manufacturer
link together with the visible non-image state `商品画像未確認・購入導線停止`,
but that incomplete fallback is never a successful completion or production
candidate. Article-level or neutral visuals are never reused as product images.
The strict gate requires every product identity registered by the current V2 owner contract,
all 37 product-card image occurrences and all 74 CTA occurrences to be
`verified`; it also requires zero neutral images and zero manufacturer-link
fallbacks. Measurement collection remains disabled by default.

Run the URL-free readiness diagnostic after capture:

```sh
.venv/bin/python scripts/raos_editorial_portfolio_v2.py validate-readiness
.venv/bin/python scripts/raos_editorial_portfolio_v2.py materialize-local \
  --require-complete
.venv/bin/python scripts/raos_editorial_portfolio_v2.py materialize-production
```

The current tracked registry intentionally leaves these thirteen owner-verification
inputs unset; no value may be guessed:

- `PRD-PROTECA-TRI-AIR-01541`
- `PRD-ANKER-SOLIX-C800`
- `PRD-JACKERY-1000-NEW-V3`
- `PRD-DJI-POWER-1000-V2`
- `PRD-THANKO-RAKUA-MINI-TK-MDW22W`
- `PRD-TOSHIBA-DWS-33B-W`
- `PRD-EUFY-AUTOEMPTY-C10-T2292`
- `PRD-ECOVACS-DEEBOT-MINI2`
- `PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171`
- `PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002`
- `PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549`
- `PRD-BERMAS-INTER-CITY-III-60570`
- `PRD-SIROCA-SS-M171`

After all product evidence is complete, generate the 74-row Money Link mapping
template without credentials or live calls. The template is deliberately
invalid for activation (`destination_url` is null and the copied flag is false)
until the owner copies every exact Money Link from Rakuten administration:

```sh
.venv/bin/python scripts/raos_rakuten_measurement_activation_v3.py \
  --private-root "$PWD/.secrets/editorial-portfolio-v3" \
  money-link-template --output money-links.json
```

After filling all 74 distinct URLs and setting only
`urls_copied_from_rakuten_admin` to true, validate the mapping and generate the
hash-bound administrator/CSV receipt template:

```sh
.venv/bin/python scripts/raos_rakuten_measurement_activation_v3.py \
  --private-root "$PWD/.secrets/editorial-portfolio-v3" \
  admin-receipt-template --money-link-mapping money-links.json \
  --output admin-receipt.json
```

The owner must then copy the CSV-echoed measurement ID and representative model
for every row, perform the two identity checks, set the verification booleans
and attestation, and retain `production_publication_authorized: false`. Activation
validates the exact 74-row set, unique HTTPS Money Link URLs, product/model
identity receipt, mapping hash, 24-hour product evidence and 15-minute V2
materialization window before writing URL-free receipts and private overlays:

```sh
.venv/bin/python scripts/raos_rakuten_measurement_activation_v3.py \
  --private-root "$PWD/.secrets/editorial-portfolio-v3" activate \
  --money-link-mapping money-links.json --admin-receipt admin-receipt.json \
  --dry-run-output rakuten-activation-dry-run.json
```

No command in this sequence authorizes publication or enables measurement.

Place a sanitized real sample in the private directory, then run:

```sh
.venv/bin/python scripts/raos_editorial_economics_v3.py rakuten-detect \
  --sample rakuten-sample.csv --encoding cp932 --delimiter comma \
  --output rakuten-detection.json
.venv/bin/python scripts/raos_editorial_economics_v3.py rakuten-binding-template \
  --detection rakuten-detection.json --output rakuten-binding.json
```

Edit only the private binding file: select exact headers, exact observed status
values, amount/date formats, set both verification booleans to `true`, and keep
it mode `0600`. Bind and dry-run the full export:

```sh
.venv/bin/python scripts/raos_editorial_economics_v3.py rakuten-bind-profile \
  --sample rakuten-sample.csv --detection rakuten-detection.json \
  --binding rakuten-binding.json --output rakuten-profile.json
.venv/bin/python scripts/raos_editorial_economics_v3.py rakuten-dry-run \
  --report rakuten-report.csv --profile rakuten-profile.json \
  --output rakuten-dry-run.json
```

Commit requires the displayed Rakuten row count and pending/confirmed/cancelled
totals, plus the exact dry-run source hash. A changed file, duplicate row,
unknown status, formula-like cell, header drift, or total mismatch fails closed.
Only exact V3 measurement IDs are Direct; unmatched IDs remain Unattributed and
the provider import never creates Estimated attribution.

## Cost and baseline inputs

`cost-template` creates all ten owner-private rows. The owner must fill the
period, approved hourly cost, actual editorial minutes, actual variable cost,
and set `owner_attested` to `true`. Missing or unverified cost keeps contribution
profit `UNAVAILABLE`; an explicit attested zero remains zero.

The optional GSC/GA4 files use the live Google adapter source-record boundary:
`schema_version: 1`, `source`, `site_id`, `date_from`, `date_to`, `retrieved_at`,
`request_sha256`, `row_count`, and `rows`. GA4 additionally includes
`configuration`. GA4 dimensions/metrics serialize as arrays of
`{"name": ..., "value": ...}`. Raw GSC queries remain private and are never
copied into the JSON/HTML baseline report.

`refresh-baseline` is the single live, repeatable owner workflow. It uses two
different read-only service accounts from `google/gsc/` and `google/ga4/`,
commits normalized batches and revision/supersession state atomically to
PostgreSQL, writes the GSC/GA4 projections as mode `0600`, and rebuilds the
baseline. It accepts no DSN or password environment variable: the database is
limited to loopback or a local Unix socket and the password must be a relative
mode-`0600` file directly below the mode-`0700` private root. The supplied site
and worker job UUIDs must already exist in RAOS.

GA4 must first have the separately approved event-scoped custom dimensions
`article_id`, `snapshot_id`, `cta_id`, `offer_id`, `product_id`, and
`placement`. The Admin API snapshot verifies all six with `EVENT` scope before
the Data API report runs. Their `customEvent:*` fields are normalized to the
private names; any missing or unapproved dimension fails closed instead of
silently weakening article, CTA, product, or placement attribution.

```sh
.venv/bin/python scripts/raos_editorial_economics_v3.py \
  --private-root "$PWD/.secrets/editorial-portfolio-v3" refresh-baseline \
  --date-from 2026-08-01 --date-to 2026-08-31 \
  --site-id <existing-site-uuid> \
  --gsc-ops-job-id <existing-gsc-worker-job-uuid> \
  --ga4-ops-job-id <existing-ga4-worker-job-uuid> \
  --database-name raos --database-user raos_worker \
  --database-password postgres-password.txt \
  --gsc-output gsc.json --ga4-output ga4.json \
  --rakuten-commit rakuten-commit.json --cost-input costs.json \
  --t0-receipt t0-receipt.json \
  --json-output baseline.json --html-output baseline.html
```

The `baseline` command writes private JSON plus `noindex,nofollow` HTML. Program
profit includes reconciled Unattributed reward at program level; article profit
uses Direct reward only and never allocates the Unattributed total.

## Production readback, T0, and follow-ups

T0 is never accepted as a free-form CLI timestamp. Generate `t0-template`, then
fill it only from successful production readbacks for all 74 Rakuten measurement
IDs, the same-origin event collector (202 plus aggregate increment readback), and
the GA4 `article_view` event. The Rakuten readback must also bind the exact
owner-private activation dry-run and its ten-article materialized-set hash; an
older or reformatted activation receipt, a partial 74-ID set, or a different
published set is rejected. Every observation binds its timestamp, request hash,
and response hash. After owner attestation, `establish-t0` selects the
earliest successful observation for each component and records the maximum of
those three timestamps—the earliest moment when every component had succeeded.

```sh
.venv/bin/python scripts/raos_editorial_economics_v3.py t0-template \
  --output production-readbacks.json
# Fill and attest production-readbacks.json, retaining mode 0600.
.venv/bin/python scripts/raos_editorial_economics_v3.py establish-t0 \
  --observation production-readbacks.json \
  --rakuten-activation-dry-run rakuten-activation-dry-run.json \
  --output t0-receipt.json
.venv/bin/python scripts/raos_editorial_economics_v3.py baseline \
  --rakuten-commit rakuten-commit.json --cost-input costs.json \
  --gsc-input gsc.json --ga4-input ga4.json --t0-receipt t0-receipt.json \
  --json-output baseline.json --html-output baseline.html
```

`evaluate-followups` marks Day 30 and Day 90 as `NOT_DUE` or
`HUMAN_REVIEW_REQUIRED`; it never emits an automatic pass or publication. The
Rakua mini color/mini Plus candidate remains `NOT_ELIGIBLE` unless actual data
covers at least 28 days after T0, an independently defined owner-private GSC
query cluster has at least 200 impressions and one click, and the source article
has a positive reconciled Direct confirmed result. Article/page totals cannot be
reused as candidate demand. Generate and attest the query-cluster input before
evaluation:

```sh
.venv/bin/python scripts/raos_editorial_economics_v3.py candidate-query-template \
  --output candidate-query-demand.json
# Fill only from the exact private GSC query-cluster report; retain mode 0600.
.venv/bin/python scripts/raos_editorial_economics_v3.py evaluate-followups \
  --baseline baseline.json --as-of 2026-11-27 \
  --candidate-query-demand candidate-query-demand.json \
  --output followups.json
```

Even when all conditions hold, the result is only
`ELIGIBLE_FOR_HUMAN_PROPOSAL`; article creation and publication stay disabled.
