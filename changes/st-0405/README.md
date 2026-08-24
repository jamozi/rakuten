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
- The audit database is opened lazily only after authorization succeeds.  Its
  owner-private root and 0600 database file are revalidated without following
  symlinks.  DEV/CI recorded environments are the only admitted modes.
- Each authorization command is idempotent.  Reuse with a different audit
  request is rejected; exact replay returns the existing immutable row without
  consuming a new context.
- Rows use a deterministic SHA-256 chain, redundant source bindings, fixed
  schema/column validation, readback verification, restart recovery, CAS-like
  SQLite serialization, and exact recovery after a simulated ambiguous
  commit.  Marker-before-event fault injection proves both rows roll back.
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

The owned isolated suite, Ruff, strict mypy, compile/import, focused sensitive
data scan, canonical import verification, workspace check, ST-0403 regression,
and scoped diff checks are the local implementation-candidate gates. They are
run with pinned uv 0.12.1 using frozen/locked, offline, no-cache, no-sync, and
no-env-file options.

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
