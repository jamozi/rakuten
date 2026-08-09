# ST-1404 recorded one-step Job runtime seam

Status: `LOCAL_IMPLEMENTATION_CANDIDATE`

This Story implements the maximum reversible local portion of the approved
ST-1404 boundary: one synchronous dispatcher observation or one synchronous
worker observation per call, backed by an exact-development/CI in-memory store
and the existing provider-neutral QueuePort. It makes no database, broker,
crash-recovery, multi-process, staging, or Production claim.

The older full-runtime preflight in this directory remains authoritative for
durable PostgreSQL/broker design and unresolved recovery semantics. The later
owner-approved implementation-first ExecPlan authorizes this narrower recorded
interface/fake slice while preserving those hard boundaries.

## Implemented safe boundary

- Immutable redacted Job, Attempt, Outbox, Inbox, transition, message, claim,
  result, and step-observation values use exact canonical states, UUIDs, strict
  UTC timestamps, explicit versions/leases, and content-free fingerprints.
- `dispatch_once(now=...)` deterministically claims at most one due recorded
  Outbox item, sends one stable logical QueueMessage, and records publication
  with `REQUESTED -> QUEUED`. An ambiguous send uses an explicitly injected
  finite retry schedule and preserves the complete message body and identity
  across intervening Job changes.
- `work_once(queue_name, now=...)` receives at most one occurrence, validates
  the queue lease, deduplicates the exact Inbox identity, claims
  `QUEUED -> RUNNING`, invokes one metadata-only recorded handler, rechecks
  receipt/lease/deadline/cancellation, commits the local terminal or retry
  state, and only then acknowledges.
- A previously `PROCESSED` or `IGNORED` Inbox occurrence is acknowledged
  without invoking the handler. A `PROCESSING` occurrence is never taken over.
  Acknowledgement failure leaves the local terminal result intact so redelivery
  cannot re-execute the handler.
- Retryable failure follows only the installed
  `RUNNING -> FAILED_RETRYABLE -> RETRY_SCHEDULED -> QUEUED` edges with an
  explicit schedule. Queue delivery attempt, Job attempt count, Attempt number,
  and Outbox publish attempts remain independent counters.
- Cancellation/deadline checks occur before handler invocation and before
  success commit. Lease/version/tampered-claim mismatches fail closed.
- `RecordedJobRuntimeAdapter` accepts only exact
  `RuntimeEnvironment.ENV_DEV` or `.CI` and uses a process-local lock for its
  explicitly limited atomicity. It retains no raw payload, result, exception,
  SQL, provider response, credential, or worker identity.

There is no loop, spawned task/thread, sleep, filesystem, ambient environment,
network, provider/broker SDK, database, SQLAlchemy/Alembic, migration,
external-service operation, telemetry implementation, deployment, release, or
Production activation in this slice.

## Local commands

After the locked Python environment has been hydrated, run the isolated Story
suite through the pinned repository uv in offline/no-sync mode:

```bash
UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads pytest -p no:cacheprovider -q tests/st1404
```

Focused Ruff lint/format and strict mypy use the same uv prefix over the six
owned source modules and `tests/st1404`. Shared exports, worker entrypoints,
Make routing, manifests, generated evidence, and status application are
deferred to Wave integration.

## Evidence and deferred boundaries

This local candidate does not implement a PostgreSQL Repository/UoW, atomic
database Outbox/Inbox transaction, real queue topology, broker adapter,
multi-worker fence, crash/orphan recovery, process lifecycle, provider retry
policy, quarantine release, or retry-state expiry transition. A failed recorded
Inbox identity is reopened only for the provisional local case where its Job is
explicitly due in `RETRY_SCHEDULED`; this is not a durable design decision.

Local pytest/static results are not formal `TST-013` or `TST-028` evidence and
do not represent hosted CI, PostgreSQL/broker runtime, staging, deployment,
release, or Production readiness. Current ST-0203 manifest drift and the
remaining durable/recovery boundaries are tracked as `DEBT-W1-016` through
`DEBT-W1-019` in the implementation-first ledger.
