# ST-1604 performance/load reference plan

Classification:
`SOURCE_DERIVED_NON_EXECUTABLE_PERFORMANCE_LOAD_REFERENCE_PLAN`.

This implementation-first slice creates a deterministic, reviewable inventory
for the canonical performance/load Story. It does not contain a load runner,
browser script, endpoint, workload, deployment, credential, staging target,
resource budget, cost authorization, telemetry connection, or test result.

## Closed boundary

- The owner contract pins the exact ST-1604 Story, TST-027, 14-row SLO catalog,
  disabled provider-neutral ST-1505 admission reference, and bounded local
  ST-1601 telemetry interface.
- TST-027 is projected exactly, including candidate-tool order, staging
  environment, owner, release-blocking flag, and unexecuted statuses. No tool,
  runner, version, executor, or environment is selected.
- The ordered target surfaces are `PUBLIC`, `ADMIN`, `API`, and `WORKER`.
  Endpoints, protocols, authentication, scenarios, mixes, fixtures, artifacts,
  and deployments are null or empty and remain `NOT_CONFIGURED`.
- All 14 canonical SLO rows are copied exactly as provisional, unimplemented,
  and unmeasured context. No SLO is selected, evaluated, met, or converted into
  a capacity claim.
- P95, P99, errors, queue age, DB connections, and cost are requirements only.
  No metric, telemetry, formula, sample, or evidence is emitted.
- Workload inputs and resource, cost, currency, stop, and scale caps remain
  null or empty. Because caps are unset, execution is not permitted. Null is
  not interpreted as zero.
- The load report is `NOT_EXECUTED` with null/empty result fields. Empty fields
  mean no evidence was collected, not zero latency, errors, cost, incidents,
  saturation, or capacity.
- ST-1505 remains disabled, inert, zero-action, ineligible, and unconfigured.
  AWS Tokyo remains the current Canonical Reference Architecture; Canonical
  AWS-specific Story deliverables remain preserved and are not erased,
  replaced, or completed by this portable overlay. Non-AWS and owner-managed
  profiles are additional portable implementation paths only. AWS is never a
  default, fallback, selected binding, eligibility shortcut, admission
  requirement, or evidence substitute. ST-1601 remains a bounded local
  interface that is available but not connected; no backend or exporter is
  introduced.

Activation is false. Load, browser, network, credential, provider, external,
staging, release, and Production actions are forbidden and all action counts
are exact built-in integer zero. Approval is null, decision is `NOT_READY`,
Story acceptance and Production eligibility are false, and canonical status is
unchanged.

Generated files are owned exclusively by:

```text
python scripts/build_st1604_performance_load_reference_plan.py
python scripts/build_st1604_performance_load_reference_plan.py --check
```

Local generation and tests are deterministic implementation evidence only.
Actual load execution, browser/RUM work, formal TST-027, telemetry/backend
integration, staging, provider access, release, and Production remain
`NOT_EXECUTED`.

## V2 maximum-safe local evaluator

The additive V2 slice implements the Story's reversible local computation and
durability boundary without weakening the V1 non-execution plan. It accepts
only caller-supplied `SYNTHETIC_RECORDED_FIXTURE` or `RECORDED_CAPTURE`
samples. It has no workload runner, endpoint, browser, process, network,
credential, provider, staging, release, or Production capability.

- `PUBLIC`, `ADMIN`, `API`, and `WORKER` each have one explicit versioned local
  budget. Those values are classified as
  `LOCAL_RECORDED_BUDGET_NOT_CANONICAL_SLO`; they do not select or satisfy any
  of the 14 provisional Canonical SLOs.
- The evaluator calculates integer nearest-rank P95/P99, exact error
  numerator/denominator, integer throughput, peak DB connections, and worker
  queue-age P95. It uses neither float arithmetic nor ambient telemetry.
- A missing surface is `UNAVAILABLE` and makes the report `DATA_BLOCKED`; it is
  never converted to zero or PASS. Cost is always `UNAVAILABLE` because no
  cost budget or measurement authority is selected.
- A complete passing fixture produces only
  `LOCAL_CAPACITY_DOCUMENTED`, with each capacity explicitly labeled
  `SYNTHETIC_LOCAL_ONLY_NOT_PRODUCTION_CAPACITY` or
  `RECORDED_LOCAL_ONLY_NOT_PRODUCTION_CAPACITY`. Canonical SLO evaluation and
  formal TST-027 remain `NOT_EXECUTED`.
- The application service makes one append attempt to an inward journal port.
  The owner-private SQLite adapter is 0700/0600, append-only, exact-schema,
  hash-chained, idempotent by `run_id`, conflict rejecting, restart safe,
  concurrent-writer safe, and recoverable after an ambiguous committed write.
  It exposes no query, export, delete, retention, or lifecycle method.
- Every external action count is the built-in integer zero. Financial values,
  affiliate reward, commission rate, EPC, RPM, or profit do not enter a
  budget, evaluation, capacity, or ordering decision.

The committed synthetic fixture and its deterministic local report are owned
by:

```text
python scripts/build_st1604_local_performance_load.py
python scripts/build_st1604_local_performance_load.py --check
```

This is local implementation evidence, not formal TST-027, staging evidence,
an observed SLO, a real capacity test, release eligibility, or Production
readiness. Actual load/RUM execution remains behind the existing human and
environment gates.
