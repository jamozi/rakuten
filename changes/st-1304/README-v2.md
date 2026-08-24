# ST-1304 V2 — recorded/synthetic cost and unit economics

This additive V2 replaces the V1 reference-only limitation with a maximum-safe
local runtime. It accepts only tracked synthetic inputs in `ENV-DEV`/`CI` and
does not resolve `OD-005` or `OD-009`. Recorded labor rates and costs are test
data, not selected business rates, prices, budgets or stop thresholds.

The calculation consumes an exact recalculation of the integrated ST-1303 V2
attribution result. The fixed program, 14-day period, five article bindings,
verification state and mature cohort must agree across attribution, work and
cost inputs. Work minutes and incremental cost must equal their measurement
facts byte-for-byte, including source SHA-256. The seven actual-cost components
must sum exactly to incremental cost.

Provider, Direct, Estimated and Unattributed confirmed reward remain separate.
Provider total is visible as its own fact. Article/unit-economics metrics use
only verified Direct reward. Estimated and Unattributed amounts remain visible
in totals but are never assigned to an article or used in a calculation that
could imply Direct attribution.

Missing, unverified, zero-denominator, immature, mixed-period or mixed-program
inputs produce a typed `UNAVAILABLE` value, never an invented zero. A missing
labor rate makes contribution profit unavailable while independent metrics can
remain available. An explicit verified zero remains a real observed zero.

Generate or check the deterministic projection with:

```text
.venv/bin/python scripts/build_st1304_cost_unit_economics.py
.venv/bin/python scripts/build_st1304_cost_unit_economics.py --check
```

The historical V1 reference owner remains non-executable and separately
reproducible. Neither owner grants provider, network, credential, database,
persistence, public projection, publication, editorial, CTA, product,
recommendation, snapshot, staging, release or Production authority.

All finance values—including commission, cost, labor, EPC, RPM and profit—are
structurally excluded from article HTML, CTA, product selection,
recommendation-order and publication-snapshot mutation. Formal TST-030, real
cost/report inputs, live, staging, release and Production remain
`NOT_EXECUTED`.
