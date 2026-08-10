# ST-1203 recorded Search Console import reference seam

Classification:
`MAXIMUM_SAFE_LOCAL_RECORDED_NON_PERSISTENT_SEARCH_CONSOLE_IMPORT_REFERENCE_SEAM`.

This implementation-first runtime slice consumes caller-supplied bytes for one
of the three existing synthetic ST-1203 recordings. It validates their exact
source-bound request, response, canonical-row, pagination, and caveat values
through one credential-free inward exchange. It is partial, non-authoritative,
local-only, non-persistent, and runtime-ineligible.

## Frozen fixture checkpoint

The existing owner generator, contract, fixture files, and manifest remain the
authority for fixture bytes. This runtime slice does not regenerate or edit
them.

| Recording | Fixture SHA-256 | Bytes | Request SHA-256 |
| --- | --- | ---: | --- |
| `baseline` | `de421fe75e633d47a02f0aa579f36f746d5ee191eb034dbd28a6c5dfd26dd3a9` | 3503 | `b062bbe5000e83471fe3f1557f04c01a1b311d312055a74083df19fa7d5bd0be` |
| `late-revised` | `f703edb673b3cc8b3686a9d983ab7940f7c3148a4eb7ac192da5761f0b0b96a0` | 3507 | `b062bbe5000e83471fe3f1557f04c01a1b311d312055a74083df19fa7d5bd0be` |
| `start-beyond-data` | `1b50f12e0a904db7202771adb39157071ec959c0f4d4d0e815e67a9e6f45557c` | 1398 | `603738ab94f0c2cdd7c474ba0418ebd36d66215d125e180acdaefed5e84a0788` |

The exact synthetic profile is `sc-domain:example.invalid`, site UUID
`00000000-0000-4000-8000-000000001203`, dates `2026-07-01` through
`2026-07-02`, ordered dimensions `date`, `query`, `page`, `country`, `device`,
search type `web`, aggregation `auto`, data state `final`, empty filter groups,
and response aggregation `byPage`. The outbound request uses `type`; deprecated
`searchType` is rejected. Request hashes use sorted-key compact UTF-8 JSON while
preserving array order and explicitly representing defaults.

## Closed behavior

- The adapter receives bytes from its caller. Runtime source never opens a
  fixture path or discovers a recording from the filesystem.
- Length and SHA-256 are checked before UTF-8 or JSON parsing. JSON duplicate
  members, non-finite numbers, unknown or missing members, and type drift fail
  closed with stable redacted errors.
- Every canonical row remains bound to the synthetic site, request hash,
  ordered dimensions, fixed date range, recorded UTC timestamp, and exact
  fixture metrics. Query and page values are inert synthetic text.
- The adapter consumes its one exact command once. It has no fallback, replay,
  pagination loop, retry, provider discovery, or mutable recording history.
- `baseline` and `late-revised` share a request but preserve their distinct
  recorded timestamps and metric values. Comparison can report only
  `RECORDED_METRICS_DIFFER`; supersession remains `NOT_DEFINED`.
- `start-beyond-data` represents only a recorded page containing zero rows.
  It does not establish complete retrieval, zero traffic, or zero analytics.
- Successful projection is `RECORDED_FIXTURE_ONLY`; provider execution,
  persistence, audit, outbox, and formal TST-030 execution remain
  `NOT_EXECUTED`. Credentials are `NOT_USED`, no import run is created, and the
  decision remains `NOT_READY`.

## Explicitly unavailable

There is no Google or other live-provider call, credential lookup, HTTP client,
pagination worker, retry, queue, job, repository, unit of work, database,
filesystem access, artifact storage, audit/outbox write, supersession policy,
status mutation, external action, staging, release, or Production behavior.
OD-015 remains unresolved and its recorded-fixture-only safe default is
preserved.

The existing fixture drift check remains:

```text
uv run --locked --no-sync --no-env-file python \
  scripts/build_st1203_search_console_recorded_adapter.py --check
```

Local unit, lint, and type evidence cannot satisfy formal TST-030, provider or
credential validation, persistence, hosted CI, staging, release, Production,
or canonical Story acceptance. All of those boundaries remain unexecuted.
