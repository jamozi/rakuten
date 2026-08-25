# ST-1206 — disabled keyword/rank import extension

Classification:
`MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_KEYWORD_RANK_EVALUATION_V1`.

This Post-MVP Story now has a provider-neutral inward source port, an exact
caller-bytes manual-CSV adapter, a deterministic process-local evaluation harness,
and a default-disabled feature scope. The only non-disabled scope is named
`RECORDED_SYNTHETIC_EVALUATION_ONLY`; it evaluates six synthetic canonical rows but
does not import, persist, publish, track, or change a KPI read model.

## Preflight and authority

- Story: ST-1206, “承認ProviderまたはCSVを追加”.
- Read: Canonical ST-1206 and dependency ST-1205, integration precedence,
  analytics/attribution design, TST-030, keyword-rank/import job schemas,
  security/privacy design, SEC-APP-008, THR-005/006, and OD-004.
- Open decision: OD-004 remains `HUMAN_DECISION_REQUIRED` and non-blocking. This
  implementation does not select or describe a rank provider. Its safe default is
  preserved as Search Console plus manual CSV only.
- Files: additive domain/application/port/recorded adapter modules, a versioned
  contract and synthetic CSV, owner generator and generated evidence, tests, and
  this record.
- Tests: strict parsing and gate negatives, deterministic evaluation, source and
  Canonical bindings, owner generation/no-write/drift/symlink checks, Ruff,
  formatting, mypy, isolated ST-1206 and direct ST-1205 suites, diff and secret
  checks.
- Out of scope: provider choice/SDK/API, URL or arbitrary HTTP, SERP scraping,
  credentials, filesystem discovery at runtime, uploads, database/queue/job/event,
  tracking activation, KPI mutation, UI, staging, release, and Production.

## Closed feature boundary

`DEFAULT_KEYWORD_RANK_SCOPE` is exactly `DISABLED`. The feature vocabulary has no
live-enabled state:

1. `DISABLED` fails before the inward port is called.
2. `RECORDED_SYNTHETIC_EVALUATION_ONLY` permits one command-bound read from the
   caller-created recorded adapter and returns a redacted immutable summary.

There is no activation/configuration interface and no environment-variable lookup.
The port exchanges RAOS domain values only, so a future approved adapter cannot
leak SDK types inward. The current adapter accepts one exact synthetic CSV as
caller-supplied bytes, once; it never opens a path or contacts a network.

## CSV and privacy boundary

The profile is strict UTF-8/ASCII data, LF-only with one terminal newline, exact
10-column header, at most 1 MiB / 10,000 rows / 256 bytes per cell, with quoting,
blank records, controls, BOM, CRLF, unexpected columns, noncanonical numbers and
formula prefixes `=`, `+`, `-`, `@` rejected fail-closed. A failure contains only a
closed code and never chains rejected data.

Rows contain `keyword_id` UUIDs, never raw queries or keyword text. The returned
snapshot contains only counts, period bounds, fixed enums and hashes; normalized
observations remain process-local. Duplicate canonical observation identities and
out-of-period rows reject the entire evaluation. No partial result is returned.

## Recorded evidence and status

The fixed synthetic fixture reproduces 6 rows, 2 keyword UUIDs, and 2 observations
for each of `POSITION`, `SEARCH_VOLUME`, and `DIFFICULTY`. Its evaluation records
`SERP scrape=FORBIDDEN`, provider/network/persistence/KPI writes/TST-030 as
`NOT_EXECUTED`, credentials as `NOT_USED`, and recommendation/tracking as
`DISABLED`.

Canonical ST-1206 remains `DEFERRED_POST_MVP` / `NOT_EXECUTED`. Formal TST-030,
approved manual-file operations, provider selection and live validation, database
materialization, hosted CI, staging, release and Production remain unexecuted.
Local evidence does not constitute `VALIDATED` or Story acceptance.

Generate and verify the owner artifacts with the pinned repository environment:

```text
python scripts/build_st1206_keyword_rank_import.py
python scripts/build_st1206_keyword_rank_import.py --check
```

Only that builder owns
`changes/st-1206/generated/keyword-rank-evaluation.v1.json` and
`changes/st-1206/manifest.yaml`.
