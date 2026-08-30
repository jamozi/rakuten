# Editorial V3 portfolio and owner-private economics

`editorial-portfolio.v3.json` is an additive, generated successor to Editorial
V2. It covers the current ten articles and thirty-two products without changing
the historical V2 contract. `generated/navigation.v3.json` is the single
machine-readable home/related-article source.

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

GA4 must first have the separately approved event-scoped `article_id` custom
dimension. The Data API field `customEvent:article_id` is normalized to the
private `article_id` field; an absent or unapproved custom dimension fails
closed instead of silently attributing events.

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
the GA4 `article_view` event. Every observation binds its timestamp, request
hash, and response hash. After owner attestation, `establish-t0` selects the
earliest successful observation for each component and records the maximum of
those three timestamps—the earliest moment when every component had succeeded.

```sh
.venv/bin/python scripts/raos_editorial_economics_v3.py t0-template \
  --output production-readbacks.json
# Fill and attest production-readbacks.json, retaining mode 0600.
.venv/bin/python scripts/raos_editorial_economics_v3.py establish-t0 \
  --observation production-readbacks.json --output t0-receipt.json
.venv/bin/python scripts/raos_editorial_economics_v3.py baseline \
  --rakuten-commit rakuten-commit.json --cost-input costs.json \
  --gsc-input gsc.json --ga4-input ga4.json --t0-receipt t0-receipt.json \
  --json-output baseline.json --html-output baseline.html
```

`evaluate-followups` marks Day 30 and Day 90 as `NOT_DUE` or
`HUMAN_REVIEW_REQUIRED`; it never emits an automatic pass or publication. The
Rakua mini color/mini Plus candidate remains `NOT_ELIGIBLE` unless actual data
covers at least 28 days after T0, the source article has at least 200 GSC
impressions and one click, and a positive reconciled Direct confirmed result.
Even when all conditions hold, the result is only
`ELIGIBLE_FOR_HUMAN_PROPOSAL`; article creation and publication stay disabled.
