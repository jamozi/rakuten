# ST-0502 — maximum-safe local Item Search runtime V2

Classification: `MAXIMUM_SAFE_LOCAL_ITEM_SEARCH_RUNTIME`

Local implementation status: `LOCAL_CODE_COMPLETE`

Canonical status: `UNCHANGED`

The additive V2 runtime closes the maximum-safe local code gaps identified by
`DEBT-W2-013`. It does not grant live-provider, credential, hosted, release, or
Production authority and does not claim formal Story validation.

## Closed local boundary

- The deterministic request is bound to the official Item Search documentation
  captured on `2026-08-24T16:43:55Z`, API version `2026-07-01`, format version
  `2`, origin and path, an exact conservative parameter/element allowlist, and
  RFC 3986 UTF-8 query encoding. The official raw HTML and response are not
  committed; only the URL, fetch time, raw-response SHA-256, and sanitized facts
  are retained.
- Future authentication is represented only by three closed secret names.
  `accessKey` is header-only; `applicationId` and optional `affiliateId` are
  query secret-name bindings. No credential value can enter a URL, log, result,
  archive, fixture, or generated projection.
- The application consumes at most one exact recorded observation and one page
  per command. Cursor, maximum-page, rate-limit, retry-delay, circuit-open, and
  terminal decisions are explicit typed state. It contains no sleep, automatic
  loop, worker activation, or network call.
- Every provider/store property, call, argument, and returned value is treated
  as a hostile collaborator boundary. Arguments are reconstructed into boundary
  copies, zero action count is checked before and after every call, and copies
  are revalidated after normal and exceptional returns. Arbitrary exceptions
  are reduced to fixed non-echoing failure codes, commit ambiguity remains
  recoverable, and exact domain values are reconstructed before cross-field
  consistency is accepted.
- Duplicate keys, malformed UTF-8, non-finite values, oversized/deep/large JSON,
  unknown output fields, cursor drift, repeated request/response/item identity,
  unsafe URLs, and hostile provider text fail closed. Provider text remains
  `UNTRUSTED_DATA` and is redacted from representations and failures.
- The owner-private SQLite schema V2 stores raw response bytes as
  content-addressed BLOBs and hash-binds artifact metadata, receipt, rate
  metadata, command, result, session before/after state, and an append-only
  mutation chain. Only the `dirfd` + `O_CREAT|O_EXCL` winner initializes;
  preexisting empty, partial, foreign, linked, or incorrectly permissioned
  files are rejected without repair. Created file and directory entries are
  synchronously flushed.
- Artifact, receipt, page metadata, command, journal, and history tables deny
  `UPDATE` and `DELETE`; session CAS remains mutable but is bound to history.
  Every open recomputes canonical JSON bytes, lower-case UUIDs, exact UTC
  RFC3339 values, redundant columns, foreign keys, hashes, chain prefix,
  `foreign_key_check`, `quick_check`, and `integrity_check`. Device/inode and a
  process-local monotonic mutation count/head/prefix are pinned across connect,
  transaction, commit, and rollback boundaries. This detects replacement and
  same-inode old-byte rollback in the active process. There is deliberately no
  claim of rollback detection across restart without an external anchor.
- Exact `COMMITTED` recovery is returned only after all related material is
  recomputed. Missing, ambiguous, deleted, or corrupt journal material fails
  closed; a process-local committed operation is never projected as
  `NOT_COMMITTED`. Known-before, unknown-before, and unknown-after commit faults
  remain deterministic local fixtures.
- Recorded synthetic pages exercise the same parser, state transition, archive,
  and replay path. The disabled future HTTP activation port accepts no client,
  credential reader, URL, headers, or ambient environment and always performs
  zero external actions.
- `reviewCount`, `reviewAverage`, `affiliateRate`, commission, EPC, RPM, and
  profit are excluded from the request and recommendation boundaries. Provider-
  derived recommendation inputs are an empty tuple.
- The Product Search offline boundary and predecessor Item Search contracts are
  unchanged. ST-0202, ST-0308, and ST-1404 remain read-only dependencies; this
  Story neither edits their owners nor enables ST-1404 workers.

The contract, sanitized source facts, synthetic fixture, generated projection,
and manifest live under `changes/st-0502/`. The owner generator is
`scripts/build_st0502_item_search_runtime.py`; `--check` is deterministic and
no-write.

Formal TST-014/TST-015, real Rakuten credentials or calls, object cloud storage,
hosted CI, staging, release, and Production remain `NOT_EXECUTED`.

## Focused local check

```bash
.venv/bin/pytest -q -p no:cacheprovider tests/st0502
python scripts/build_st0502_item_search_runtime.py --check
```
