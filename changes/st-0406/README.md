# ST-0406 secure object-intake seam

Status: `LOCAL_IMPLEMENTATION_CANDIDATE` (partial, TEST_ONLY)

This Story implements the maximum-safe process-local portion of the approved
ST-0406 secure object/file-intake boundary. It accepts only an exact committed
ST-0403 `AuthorizationGrant` for `artifact:upload` at the descriptor's exact
site, streams bounded synthetic bytes into an append-only quarantine, seals the
declared size and SHA-256, and returns only after all closed inspection results
are safe. The sole success outcome is `CLEAN_QUARANTINED`; it is not a release,
promotion, publication, import, or proof of durable storage.

## Implemented local boundary

- Descriptors require nonzero exact UUIDs, a closed object kind and privacy
  class, a portable leaf name, lowercase parameter-free MIME, a positive exact
  byte count, and lowercase SHA-256. Booleans cannot pass integer checks.
- `IntakePolicy` is immutable, has no defaults, is explicitly `TEST_ONLY`, and
  requires positive stream, archive expansion, CSV row/column/cell, media-type,
  and privacy allowlist bounds.
- Authorization, matching site, MIME/privacy admission, declared size, and the
  bounded reader shape are checked before any source or quarantine I/O.
- Each source chunk is exact `bytes`, bounded, read once, appended once, and
  included in the size/hash calculation. Exceptions and malformed values fail
  closed without retry, exception chaining, or rejected-value echo.
- Quarantine is sealed before duplicate, magic/MIME/extension, archive, CSV
  encoding/formula/shape, privacy, and malware results can be accepted.
  `UNKNOWN`, `UNAVAILABLE`, `MALFORMED`, rejected inspection, and every
  non-clean malware state fail closed. An exact duplicate is still inspected
  and malware-scanned.
- Domain and result records are closed, immutable, redacted, and non-pickleable;
  no arbitrary mapping or raw-byte field exists on a public record.
- The recorded adapter is limited to exact `ENV-DEV` or `ENV-CI`, uses explicit
  positive capacities and digest-scripted inspection results, and stores an
  append-only tuple under `RLock` with no eviction. Public snapshots contain
  metadata only; synthetic/quarantined bytes have no read or export surface.

The inward ports deliberately expose no quarantine read, download, export,
release, promotion, deletion, purge, lifecycle, restore, or cleanup operation.
There is no file, object-store, database, network, provider SDK, credential,
subprocess, native scanner, HTTP endpoint, or framework integration in this
slice.

## Local verification boundary

The owned isolated tests include success, pre-I/O authorization denial,
malicious and indeterminate scanner results, digest/size/stream tamper, archive
and CSV limits, formula injection, privacy mismatch, duplicate scanning,
capacity exhaustion, redaction/non-pickle behavior, and static architecture and
forbidden-capability checks. Ruff, strict mypy, compile/import, focused
sensitive-data scanning, ST-0403 regression, and read-only predecessor checks
are local implementation-candidate gates, run with the pinned uv 0.12.1
toolchain in locked, offline, no-cache, no-sync, and no-env-file mode.

## Deferred and unexecuted

ST-0202 object storage is not called or reconfigured. OD-014 remains unresolved:
this slice chooses no retention period, lifecycle policy, default retention, or
automatic deletion behavior, and exposes no deletion operation. It also does
not choose or activate a real file source, quarantine bucket, object key,
malware engine, magic/archive/CSV parser, credential, account, region, endpoint,
database record, asynchronous worker, HTTP upload endpoint, or Production
policy.

Real object-storage integrity/version behavior, durable quarantine isolation,
native malware and file-format inspection, operational failure recovery,
Security/Privacy owner review, hosted CI, staging, release, deployment, and
Production remain separately unexecuted. Formal `TST-014`, `TST-026`, and
`TST-031` remain `NOT_EXECUTED`; local passes do not establish `VALIDATED`,
recoverability, release eligibility, or Production readiness.
