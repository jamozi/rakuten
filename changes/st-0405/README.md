# ST-0405 local audit recording seam

Status: `LOCAL_CODE_COMPLETE` / `LOCAL_INTEGRATION_CANDIDATE`

The original process-local V1 seam remains intact.  V2 completes the
maximum-safe local Story boundary by recovering an exact durable ST-0403
authorization command before any audit-store open, constructing the same
fixed-field event, and committing an owner-private SQLite audit row plus a
synthetic atomicity marker in one transaction.

## Durable V2 boundary

- Direct `AuthorizationGrant` construction is not accepted by V2.  The writer
  requires the exact `DurableAuthorizationService`, rechecks the active
  session through `recover_admin`, and accepts only the service-recorded
  `edit_article_draft` / `ARTICLE_VERSION` / `DRAFT` decision.  Command,
  request, session, and ST-0403 authorization-audit hashes are persisted.
- The audit database is opened lazily only after authorization succeeds. The
  owner-private 0700 root is opened descriptor-relatively, and the 0600,
  single-link database is created with `O_EXCL`. A pre-existing empty,
  partial, or foreign database is rejected unchanged; ST-0405 never adopts or
  initializes it. DEV/CI recorded environments are the only admitted modes.
- A database created by the predecessor's less strict local schema is also
  rejected unchanged. This Story adds no implicit migration, copy, deletion,
  or legacy-data authority; local callers must select a fresh owner-private
  path for the hardened schema and preserve any predecessor file separately.
- The root path/device/inode and database device/inode are pinned. Named-file
  replacement fails closed. A process-wide count/head/prior-prefix anchor also
  rejects a valid older same-inode snapshot after that process has observed a
  newer prefix. A fresh process has no independent external durable rollback
  anchor, so cross-restart rollback detection is deliberately not claimed.
- Each authorization command is idempotent.  Reuse with a different audit
  request is rejected; exact replay returns the existing immutable row without
  consuming a new context.
- Every open validates the exact SQLite application/user versions, connection
  PRAGMAs, `STRICT` tables, `table_xinfo`, indexes, triggers, foreign keys,
  integrity, and the complete canonical event/marker/metadata hash chain.
  Event and marker rows are protected by update/delete triggers; metadata may
  advance only by one event whose previous/head hashes match.
- Appends use an immediate transaction plus count/head/record-hash CAS,
  deterministic SHA-256 chaining, redundant source bindings, full readback,
  verified read snapshots, and a process-wide lock; SQLite locking serializes
  separate local processes. A commit exception while the transaction remains
  open is a known rollback. Once SQLite reports the transaction closed, the
  result stays `STORAGE_COMMIT_UNKNOWN` until exact candidate recovery; there
  is no blind retry. Marker-before-event and before/after-commit fault points
  exercise the closed classifications.
- V2 reconstructs authorization, context, candidate, persisted record, and
  receipt values at their trust boundaries. Its recorded context, store,
  factory, writer, and disabled query surfaces expose exact integer
  `external_action_count == 0`; mutable, non-integer, or nonzero collaborator
  counters fail closed before and after calls.
- The store has no update, delete, retention, export, network, provider,
  credential, or background-job capability.  The atomic marker is explicitly
  synthetic local evidence and is not represented as a real business change.
- A bounded internal correlation query exists for integrity verification.
  The outward query service always returns
  `QUERY_AUTHORIZATION_UNAVAILABLE` before opening the store because the
  Canonical ST-0403 `OPS-012` / `view_audit` binding remains blocked by
  `SITE_SCOPE_CONFLICT`.  No permission is inferred to close that conflict.

## Preserved V1 compatibility boundary

- The event mirrors the canonical fixed `ops.audit_event` fields needed by this
  slice: exact event/actor/target/correlation UUIDs, strict UTC occurrence time,
  closed actor/outcome/severity enums, bounded ASCII action/target/reason/request
  codes, and optional lowercase SHA-256 before/after hashes.
- User, service, and schedule actors require an identifier. System and
  anonymous actors forbid one. No caller can supply or override the action,
  target type, target id, or correlation id derived from the grant.
- V1 has no arbitrary `details` mapping and no raw prompt/source/provider
  body, secret, token, cookie, header, IP address, personal data, exception
  message, stack, SQL, affiliate URL, environment read, file, network, logging,
  or background-work surface.
- Ordinary malformed collaborator output or exception fails closed as the sole
  stable `REQUIRED_RECORD_NOT_COMMITTED` failure. The context source and
  appender are each called at most once; there is no retry or error
  stringification. `BaseException` is not intercepted.
- The recorded adapter is exact `ENV-DEV` only, has explicit positive bounded
  capacity and an explicit synthetic context script, uses an `RLock`, and
  retains an ordered immutable tuple. Full capacity, duplicate event ids, and
  digest tampering fail without eviction.

The V1 service performs no business callback or mutation. A caller must not
claim business success without the returned audit commit token, but the token
proves only that this configured appender accepted the event. It does **not**
make a business mutation and audit event atomic. ST-0308/durable
unit-of-work/database integration is required before any such transaction
guarantee can be made.

## Local verification

The owned isolated suite, repeated hostile concurrency/recovery checks, Ruff,
strict mypy, targeted Pyright, compile/import, denied-network execution,
focused sensitive-data scan, canonical import verification, workspace check,
read-only downstream regressions, and scoped diff checks are the local
implementation-candidate gates.

## Deferred and unexecuted

This Story remains local/recorded only.  It adds no PostgreSQL execution,
Production role/grant, live identity, outward audit query, retention, deletion,
export, HTTP/framework integration, file/network/provider access, or
Production behavior.  OD-014 remains unresolved, so automatic retention and
deletion stay absent.  The synthetic atomicity marker does not claim a real
business-plus-audit transaction.

Formal PostgreSQL `TST-011`, hosted HTTP `TST-012`, hosted CI, live or staging
validation, release, deployment, publication, and Production remain
`NOT_EXECUTED`.  The local SQLite hostile suite is development evidence only;
it does not establish Canonical `VALIDATED` or Production-ready status.
