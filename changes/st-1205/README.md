# ST-1205 KPI read-model reference plan

Classification:
`SOURCE_DERIVED_NON_EXECUTABLE_NON_ATTESTING_KPI_READ_MODEL_REFERENCE_PLAN`.

This directory contains an authored boundary contract and its deterministic owner
projection. The projection reproduces the exact ordered canonical KPI-001 through
KPI-030 definitions and all nine source fields. Formula strings remain inert source
text. They are not parsed, evaluated, translated to SQL, or used to calculate a
metric.

The slice binds the current committed bytes and closed semantics of:

- ST-1201 at `db19e538ed5a8c7e208ded7c3319a15c5e809492`: tracking disabled,
  recorded-only/nonpersistent behavior, no measurement evidence;
- ST-1203 at `bdb97355eb27100d92787b6bbd3b5608b729250e`: top-row-only Search
  Console fixtures, incomplete-row caveats, an empty page that is not proof of zero,
  and undefined supersession;
- ST-1204 at `73b7782502f249f91eafd3d0bc9d229fb770d7c6`: two returned rows
  while provider `rowCount` is three, no pagination or numeric aggregation, metric
  values preserved as strings, and undefined supersession.

The result is an inventory/reference projection, not a KPI engine or read model.
Calculation versions, source mappings, watermarks, periods, inputs, SQL, tables, job
payloads, persisted rows, results, and evidence remain null or empty.
Empty means unavailable or not executed; it never asserts a zero-valued KPI.

No formula engine, job, database, repository, tracking activation, public
projection, recommendation input, provider, network, live, staging, release, or
Production action is present. Definitions are projected 30/30, while calculations
remain 0/30 and verified calculations remain 0/30. The decision is `NOT_READY`,
Story acceptance is false, approval is null, and formal TST-030 is `NOT_EXECUTED`.

Generate and check only with the pinned repository environment:

```text
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1205_kpi_read_model_reference_plan.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1205_kpi_read_model_reference_plan.py --check
```

Only that builder owns the generated JSON and manifest. Local generation and tests
do not constitute formal, runtime, staging, release, or Production evidence.
