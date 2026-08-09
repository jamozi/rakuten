# ST-0405 local audit recording seam

Status: `LOCAL_IMPLEMENTATION_CANDIDATE` (partial)

This Story implements the maximum-safe local portion of the approved ST-0405
audit event service. It binds critical action, target, and correlation fields
to an exact committed ST-0403 `AuthorizationGrant`, obtains actor/event/time
metadata from an explicit inward context source, constructs one fixed-field
redacted event, and requires one exact append receipt before returning an
immutable commit token.

## Implemented local boundary

- The event mirrors the canonical fixed `ops.audit_event` fields needed by this
  slice: exact event/actor/target/correlation UUIDs, strict UTC occurrence time,
  closed actor/outcome/severity enums, bounded ASCII action/target/reason/request
  codes, and optional lowercase SHA-256 before/after hashes.
- User, service, and schedule actors require an identifier. System and
  anonymous actors forbid one. No caller can supply or override the action,
  target type, target id, or correlation id derived from the grant.
- There is no arbitrary `details` mapping and no raw prompt/source/provider
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

The service performs no business callback or mutation. A caller must not claim
business success without the returned audit commit token, but the token proves
only that this configured appender accepted the event. It does **not** make a
business mutation and audit event atomic. ST-0308/durable unit-of-work/database
integration is required before any such transaction guarantee can be made.

## Local verification

The owned isolated suite, Ruff, strict mypy, compile/import, focused sensitive
data scan, canonical import verification, workspace check, ST-0403 regression,
and scoped diff checks are the local implementation-candidate gates. They are
run with pinned uv 0.12.1 using frozen/locked, offline, no-cache, no-sync, and
no-env-file options.

## Deferred and unexecuted

This slice is process-local only. It adds no database/migration/role/grant,
durable writer, durable query, database immutability proof, multi-process or
crash guarantee, business-plus-audit transaction, retention, export, HTTP or
framework integration, file/network/provider access, live identity, or
Production behavior. The adapter snapshot exists only for focused tests and is
not the canonical query deliverable.

Formal `TST-011` and `TST-012`, database runtime/immutability/authorization,
durable writer/query and atomic transaction verification, hosted CI, live or
staging validation, release, deployment, publication, and Production remain
`NOT_EXECUTED`. Local passes do not establish `VALIDATED` or Production-ready
status.
