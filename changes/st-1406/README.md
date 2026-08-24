# ST-1406 recorded incident command seam

Local code status: `LOCAL_CODE_COMPLETE_MAX_SAFE`

Canonical Story status remains `NOT_STARTED`. Formal `TST-012` and `TST-028`
remain `NOT_EXECUTED`. This Story slice implements only a reversible,
provider-neutral DEV/CI incident model and process-local command seam. It
creates no HTTP, durable-storage, notification, provider, staging, release,
publication, or Production authority.

## Implemented safe boundary

- The closed severity vocabulary is `SEV1`, `SEV2`, `SEV3`, and `SEV4`.
  Lifecycle changes follow exactly
  `DECLARED -> CONTAINING -> CONTAINED -> RECOVERING -> MONITORING -> CLOSED`
  and `CLOSED -> REOPENED -> CONTAINING`. A direct jump, closure without a
  root-cause flag and evidence reference, timestamp regression, or mutation of
  a closed incident fails before local state changes. Each status and status
  timeline entry also enforces its minimum reachable aggregate generation.
- Every declaration requires explicit non-nil declarer, owner, and incident
  commander principal identifiers. Title, summary, and timeline note values are
  bounded and have redacted representations. Title rejects C0, DEL, and C1
  controls; summary and timeline note permit line feed and tab but reject all
  other C0 controls plus DEL and C1 controls.
- The provider-neutral timeline vocabulary is the closed local set `NOTE`,
  `STATUS_CHANGE`, `CONTAINMENT`, `DECISION`, `RECOVERY`, `EVIDENCE`, and
  `ACTION_ITEM`. An `EVIDENCE` entry requires at least one reference.
- Evidence is reference-only: an artifact UUID plus its exact lowercase SHA-256
  digest. The model has no arbitrary mapping or raw evidence, provider response,
  credential, personal-data, exception-text, or attachment-body field.
- Every command carries an expected aggregate generation. The adapter performs
  one same-process compare-and-swap under one lock, requires an exact current
  match whenever the caller supplies observed state, refuses generation
  overflow, and never evicts state, timeline entries, idempotency receipts, or
  event intents at capacity. Optional seeded input is either a state-only
  snapshot or a complete contiguous generation-one-through-current timeline
  whose terminal status, milestones, and update time reproduce that state.
- The application service also requires an explicit capacity from 1 through
  10,000 and bounds its cumulative incident generation/observation maps. The
  port resolves an exact historical replay before fresh admission. At capacity,
  an unobserved replay is returned without expanding those maps, while a fresh
  unobserved mutation is rejected before adapter state changes.
- The adapter stores only a bounded idempotency-key fingerprint. The same key
  and exact command returns the original result without a duplicate entry or
  intent. The same key with changed command bytes fails closed. A historical
  replay validates its result and current-state chain but never advances or
  binds the application service's observation maps.
- The application reconstructs a validated command snapshot, sends a separate
  deep copy to the store, and checks after the call that both caller-owned
  command/key inputs and the sent command, fingerprints, and observed-state
  copy still match their pre-call snapshots. The adapter likewise owns its
  stored fingerprints and aggregate values and returns newly copied receipts.
  Collaborator mutation therefore fails as sanitized `STORE_FAILURE` without
  binding service observation state or poisoning a later replay.
- Local declaration, timeline, and closure event IDs and referenced source
  kill-switch event IDs form disjoint global sets. Seed input and every
  deterministic generated ID fail closed on a cross-set collision.
- Declaration and closure create immutable in-memory event intents compatible
  with the already installed `jp.raos.ops.incident_declared.v1` and
  `jp.raos.ops.incident_closed.v1` models. These intents are retained for local
  inspection only; the adapter has no publisher, outbox, send, delivery, retry,
  or notification method.
- `RecordedIncidentAdapter` accepts only exact `ENV-DEV` and `ENV-CI`, uses
  bounded memory, and performs no file, database, process, network, provider,
  or background I/O.

## Dependency and authority boundary

- ST-1405 supplies only an already-created `KillSwitchEventIntent`. ST-1406
  accepts an exact disengaged-to-engaged intent for the same incident and
  records a `CONTAINMENT` timeline reference. It does not import a kill-switch
  runtime, construct a kill-switch change command, engage or release a switch,
  or deliver the source intent.
- ST-0405 provides a local audit-recording seam, but that seam explicitly does
  not make an incident mutation and audit record durable or atomic. The current
  IAM vocabulary also does not establish a Production incident permission.
  Calling that seam before or after the process-local incident mutation would
  create a split-brain success/failure window, so this maximum-safe boundary
  deliberately stops at the typed incident port. It does not fabricate an
  `AuditService`, commit token, authorization mapping, durable audit event, or
  business-plus-audit transaction. Those governed integration elements remain
  unavailable rather than being represented as a local pass.

## Provisional provider-neutral mappings

The imported design surfaces do not yet define one authoritative translation
between all incident vocabularies. This local slice therefore stores no such
translation:

- Canonical operations use `SEV1` through `SEV4`, while an upstream database
  design names `P0/P1/P2/P3`. No equivalence, persistence mapping, or migration
  between those values is asserted here.
- The imported HTTP `IncidentEventRequest` vocabulary differs from the
  provider-neutral local timeline vocabulary. No route, request converter,
  database enum, or authoritative mapping is introduced.

Both translations remain deferred until a Canonical owner source resolves the
contract boundary. The local taxonomy is non-authoritative outside this bounded
service seam.

## Local verification

After the pinned environment has already been hydrated, run the Story suite in
an isolated pytest process:

```bash
UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads pytest -p no:cacheprovider -q tests/st1406
```

Focused Ruff format/lint and strict mypy cover the four source modules and the
isolated test directory. Dependency regressions run in separate pytest
processes for ST-0405 and ST-1405. Canonical import verification, workspace
drift verification, scoped secret scanning, and `git diff --check` are local
implementation-candidate checks only.

## Explicitly deferred and unexecuted

- incident HTTP/API routes, `IncidentEventRequest` conversion, Problem Details,
  browser/admin UI, database schema, migration, durable query/write,
  multi-process concurrency, crash recovery, durable idempotency, and retention;
- Production authorization/IAM mapping, step-up authentication, business-plus-
  audit atomicity, durable immutable audit, notification/channel selection under
  OD-011, outbox/broker delivery, provider calls, and external writes;
- kill-switch invocation or release, publication or unpublication, credentials,
  live data, staging, formal `TST-012`/`TST-028`, hosted CI evidence, release,
  deployment, and Production.

Local parse, type, lint, and pytest passes do not establish `VALIDATED`, satisfy
formal TST evidence, or prove live/provider, staging, release, publication, or
Production readiness.
