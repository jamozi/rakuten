# ST-1304 cost and unit-economics reference plan

Classification:
`SOURCE_DERIVED_NONEXECUTABLE_COST_UNIT_ECONOMICS_REFERENCE_PLAN`.

This directory defines a deterministic, source-derived inventory of the
canonical cost and unit-economics vocabulary and every selection that remains
unavailable for a future executable implementation. It is not a cost intake,
pricing engine, allocation algorithm, KPI calculator, SQL query, job, event
emitter, read model, repository, unit of work, transaction, dashboard, public
projection, or executable runtime.

The current ST-0706 dependency is a development-only recorded orchestration
seam. Its caller-scripted token and JPY values are process-local metadata, not
durable or independently verified cost facts. The current ST-1205 dependency
projects all 30 canonical KPI definitions but performs zero calculations and
creates no read-model rows. The current ST-1303 dependency creates no events,
provider facts, attribution allocations, or runs, and all of its counts and
totals remain unavailable.

OD-005 and OD-009 remain blocking Business Owner decisions. No reviewer,
backup, hourly labor rate, cloud or provider budget, threshold, or automatic
stop is selected. Missing labor cost is `UNKNOWN` and is never converted to
zero; contribution profit therefore remains unavailable. Production remains
disabled.

Canonical table, job, event, and KPI definitions are retained as inert
vocabulary only. Every cost source, pricing rule, currency conversion,
allocation basis, calculation version, period, source watermark, denominator,
rounding rule, correction policy, persistence choice, and approval remains
null or `NOT_EVALUATED`. Input, cost, candidate, allocation, snapshot,
read-model, emitted-event, and write collections remain empty. Counts and
totals remain null, not zero, and no empty collection can produce a vacuous
pass.

Generate and check only with the pinned repository environment:

```text
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1304_cost_unit_economics_reference_plan.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1304_cost_unit_economics_reference_plan.py --check
```

Only that builder owns the generated JSON and manifest. Local generation and
tests do not satisfy Story acceptance or formal TST-030. Database, provider,
browser, CI, live, staging, release, and Production work remains
`NOT_EXECUTED` and unauthorized.
