# ST-1205 recorded KPI read model V2

Classification:
`MAXIMUM_SAFE_LOCAL_EXECUTABLE_RECORDED_KPI_READ_MODEL_V2`.

This Story now has a deterministic process-local formula engine, inward port,
caller-bytes recorded adapter, calculation job, immutable read-model snapshot,
versioned contract, and a synthetic golden fixture. All canonical KPI-001 through
KPI-030 definitions are executable and the golden fixture reproduces 30/30 values.
The former V1 0/30 projection is preserved as a superseded historical reference;
it is no longer the current implementation boundary.

## Preflight and authority

- Story: ST-1205, “30 KPIを定義Version付きで計算”.
- Read: Canonical ST-1205 and ST-1201/ST-1203/ST-1204 dependencies, analytics and
  attribution design, the 30-KPI catalog, TST-030, integration precedence, data
  classification, OD-012, and OD-015.
- Open decisions: OD-012 and OD-015 remain unresolved. Their safe defaults are
  preserved: tracking is disabled and only caller-supplied recorded synthetic bytes
  are accepted.
- Scope: domain/application/port/recorded adapter, V2 contract and fixture, owner
  generator, local tests, and documentation. No migration, database, provider, or
  public UI is introduced.

## Calculation boundary

Each definition carries typed input source and role, canonical formula, time grain,
cohort semantics, included/excluded traffic, attribution display basis, result unit,
Decimal quantization, `ROUND_HALF_EVEN`, verified-zero semantics, and an explicit
division-by-zero policy. Values are `decimal.Decimal` created from canonical decimal
strings; floats and non-finite values are rejected.

A KPI becomes `UNAVAILABLE`, never an implicit zero, when a required input is
missing, unverified, from the wrong source, from a different period or program, in
an immature cohort, attribution-unverified, attribution-basis mismatched, invalid,
or has a zero denominator. A verified numerator of zero with a positive verified
denominator remains a real zero.

All calculations bind one exact program,
`WORDPRESS_BLOG_RAKUTEN_AFFILIATE`, and one exact period. Provider totals,
direct/estimated attributed amounts, and unattributed amounts are distinct bases.
Unattributed or provider totals are never silently allocated to an article.

## Affiliate learning seam

The internal learning projection maps search CTR, affiliate click rate, confirmed
reward per click, and confirmation rate to KPI-014, KPI-006, KPI-003, and KPI-008.
Confirmed reward per content hour applies the same period, program, maturity, and
verified-attribution gates. Every learning row sets
`recommendation_order_effect=false`; the job cannot change article HTML, CTA,
product selection, publication snapshots, or recommendation order.

## Explicitly absent

There is no filesystem discovery in runtime code, provider SDK, credential or
environment lookup, HTTP/network call, database, SQL execution, repository, queue,
tracking activation, public projection, publication, staging, release, or
Production action. Results exist only in an immutable process-local snapshot. The
recorded adapter consumes one exact caller-supplied fixture once and returns stable
redacted failures.

DEBT-W2-054 is closed by the 30 executable definitions and formula reproduction.
DEBT-W2-062 is closed by current hash/semantic bindings for ST-1201, ST-1203, and
ST-1204. Formal TST-030, live-provider reconciliation, database materialization,
hosted CI, staging, release, and Production evidence remain explicitly unexecuted;
local results do not constitute Canonical Story acceptance or `VALIDATED` status.

Generate and check with the pinned repository environment:

```text
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1205_kpi_read_model_reference_plan.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1205_kpi_read_model_reference_plan.py --check
```

Only that builder owns `generated/kpi-read-model.v2.json` and `manifest.yaml`.
