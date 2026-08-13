# ST-1305 finance reconciliation reference plan

Classification:
`SOURCE_DERIVED_NONEXECUTABLE_FINANCE_RECONCILIATION_REFERENCE_PLAN`.

This directory defines a deterministic, source-derived inventory of the
canonical finance reconciliation vocabulary and every selection that remains
unavailable for a future executable report. It is not a provider-report or CSV
intake, parser, security scanner, dry run, canonical commit, reconciliation
engine, attribution or cost calculation, exception workflow, evidence
publisher, approval or audit workflow, SQL query, migration, job, event,
repository, API, UI, or executable runtime.

The current ST-1304 dependency is itself non-executable. It contains no source
reports, revenue batches, provider facts, attribution allocations, cost facts,
cost allocations, unit-economics snapshots, or read-model rows. Its counts and
totals remain unavailable. It therefore supplies only inert vocabulary, not
values that can be reconciled.

The canonical reconciliation dimensions are retained without evaluation: file
hash uniqueness, row count, generated/confirmed/cancelled amount totals,
currency, period, duplicate provider rows, and dry-run-to-commit hash equality.
The related data-quality constraints also remain unevaluated. No numeric
tolerance, total basis, rounding, correction, exception, approval, audit,
evidence, persistence, identity, or retention policy is selected.

OD-003, OD-005, OD-009, and OD-014 remain inherited safety constraints even
though ST-1305 declares no Story-local Open Decision. No real Rakuten report or
column mapping is available, labor and contribution profit remain `UNKNOWN`,
Production is disabled, and retention is unselected. No provider, finance,
identity, or report value is inferred. Empty collections are never interpreted
as zero or as a successful reconciliation.

Generate and check only with the pinned repository environment:

```text
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1305_finance_reconciliation_reference_plan.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --frozen --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1305_finance_reconciliation_reference_plan.py --check
```

Only that builder owns the generated JSON and manifest. Local generation and
tests do not satisfy Story acceptance or formal TST-030. Provider, CSV, file,
database, audit, browser, CI, live, staging, release, and Production work
remains `NOT_EXECUTED` and unauthorized.
