# ST-1305 V2 — recorded/synthetic finance reconciliation report

This additive V2 replaces the V1 reference-only limitation with a maximum-safe
local report runtime. It accepts only tracked synthetic inputs in `ENV-DEV` or
`CI` and does not resolve `OD-003`, `OD-005`, `OD-009` or `OD-014`.

The report recalculates the integrated ST-1303 attribution and ST-1304
unit-economics results. It then reconciles confirmed Provider, Direct,
Estimated and Unattributed reward; measurement/cost work minutes and
incremental cost; period, currency, duplicate identities and measurement
readiness. Every amount basis remains visible and Unattributed reward is never
allocated to an article.

Because no real Rakuten report is available, provider file hash/row count,
generated/cancelled totals and dry-run-to-commit equality are explicitly
`UNAVAILABLE` and appear as typed external exceptions. They are never treated
as zero or a successful reconciliation. This is a synthetic report, not formal
TST-030 or provider evidence.

The learning report returns review candidates only. Candidate rules accept a
closed type containing search impressions/clicks, article views, affiliate
clicks, broken-link count and the immutable article intent binding. Reward,
commission, outcome, work, cost, EPC, RPM and profit fields cannot enter that
type. Candidate order is the fixed integrity/rule/slot order, never a product
or recommendation ranking. No candidate changes article HTML, CTA, product
selection, recommendation order or a publication snapshot.

Candidates are emitted only when all five measurement metrics are calculable
from the same program and period, verified attribution, and mature five-slot
cohorts. Missing or unverified inputs, a zero denominator, an immature cohort,
or a mixed period/program makes the learning report `UNAVAILABLE`; it never
converts the condition to zero or a low-priority ranking signal.

Generate or check the deterministic projection with:

```text
.venv/bin/python scripts/build_st1305_finance_reconciliation.py
.venv/bin/python scripts/build_st1305_finance_reconciliation.py --check
```

The historical V1 owner remains non-executable and separately reproducible.
Neither owner grants provider, network, credential, database, persistence,
public projection, publication, approval, staging, release or Production
authority. Formal TST-030, real provider/report input, live, staging, release
and Production remain `NOT_EXECUTED`.

Normal generation verifies the prior synthetic fixture's authored runtime
hash, requires unchanged article IDs, slots, slugs and intent classifications,
and replays current unit-economics inputs before refreshing only dependency and
calculated input/result hashes. The request and its timestamp remain unchanged;
no measurement, verification state or live evidence is created. `--check` and
runtime loading stay strict and read-only. Inconsistent references fail closed,
and ordinary binding-write failures roll back prior replacements.
