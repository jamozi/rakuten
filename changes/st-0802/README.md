# ST-0802 local recorded article-lifecycle seam

Classification:
`MAXIMUM_SAFE_LOCAL_RECORDED_NON_PERSISTENT_ARTICLE_LIFECYCLE_SEAM`.

This implementation-first slice projects the seven canonical reference
operations `ED-005` through `ED-011` through one exact, ordered, process-local
exchange.  It binds scripted Article and Article Version snapshots to the
ST-0501 ArticlePlan contract and to the ST-0801 deterministic Content AST
serialization and hash boundary.

The slice is source-derived, partial, non-authoritative, local-only, and
runtime-ineligible.  A recorded result is always `RECORDED_ONLY` and
`NOT_READY`.  Persistence, source-packet verification, and formal verification
remain `NOT_EXECUTED`.

## Closed behavior

- New scripted Article snapshots remain `IDEA`; Article Version snapshots
  remain `DRAFT`.
- Review, approval, scheduling, publication, archival, and every other state
  transition are disabled locally.
- Current and published version markers, archive/review/approval/publication
  markers, and all evidence-dependent timestamps remain null.
- Source-packet version identifiers are opaque UUID references with
  `NOT_VERIFIED` status.  The seam does not read or validate a Source Packet.
- IDs, timestamps, versions, and strong ETags are supplied only by an exact
  immutable script.  No algorithm for generating them is selected.
- Updates model only an exact recorded content/no-op/replay response.  They do
  not claim a durable write, optimistic-lock transaction, or replay store.
- Authorization uses only the canonical recorded TEST_ONLY article/version
  read/write action associated with each operation and is checked before the
  exchange.

## Explicitly absent

There is no repository, unit of work, transaction, database, file or object
storage, HTTP/API surface, provider, network call, environment lookup, clock,
UUID generator, retry, fallback, AI generation, review, approval, publication,
or external action in this slice.  The recorded adapter is not a fake business
repository and retains no business-state map or public history.

Local unit, lint, and type results are implementation evidence only.  They do
not satisfy formal TST-012/TST-020, runtime, persistence, hosted CI, staging,
release, or Production verification.  Canonical Story acceptance and release
eligibility therefore remain false.
