# ST-1404 recorded one-step Job runtime seam

Status: `LOCAL_CODE_COMPLETE` (formal/live verification remains `NOT_EXECUTED`)

This Story implements the maximum reversible local portion of the approved
ST-1404 boundary. The V2 seam adds an ST-0308-compatible explicit outer Unit of
Work, revision CAS, durable-shaped lease fences, process-restart snapshots,
commit-ambiguity recovery, orphan takeover, atomic handler-effect completion,
quarantine replay, and cancellation/deadline handling. It remains a recorded
DEV/CI adapter over the provider-neutral QueuePort: no live database, broker,
provider, worker activation, staging, or Production claim is made.

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
- `RecordedDurableJobRuntimeStore` is the V2 clone-on-write UoW fake. Every
  transaction starts from one immutable revision, commits with CAS, and can
  inject known-before, unknown-before, or unknown-after commit outcomes.
- Dispatcher queue I/O occurs only after an Outbox lease/fence commit and is
  finalized in a second UoW. Stable Event identity makes an ambiguous send an
  at-least-once duplicate, never a second logical message.
- Worker claim commits before handler execution. Job, Attempt, Inbox, handler
  effects, transition history, and terminal/retry outcome commit atomically;
  broker acknowledge/retry happens only afterward. Unknown completion is
  resolved by the durable Inbox on redelivery.
- Expired Outbox/Work leases are selected deterministically and recovered with
  fencing. Retry exhaustion and quarantine emit metadata-only local DLQ
  records. Quarantine replay is two-phase and requires a hash-only approval
  record; `QUARANTINED -> QUEUED` clears the current completion timestamp while
  immutable Attempt/transition history remains.
- Cancellation is immediate for REQUESTED/QUEUED and recorded for RUNNING or
  retry states. Deadline/cancellation in RETRY_SCHEDULED is explicitly held;
  no non-canonical expiry edge is invented.

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

Focused Ruff lint/format, strict mypy/Pyright, and the owner generator cover
the Story-owned V2 source and tests. Regenerate/check the contract projection:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads python scripts/build_st1404_durable_job_runtime.py --check
```

## Evidence and deferred boundaries

`DEBT-W1-016` and `DEBT-W1-017` are closed for local implementation by the V2
transaction/fence/commit-ambiguity and orphan/quarantine/retry-state behavior.
This does not close live-runtime evidence: PostgreSQL mapping/migration,
provider broker topology, multi-process execution, formal failure injection,
and operational thresholds remain external or deferred. Synthetic fixture
durations are versioned test inputs and are not operational defaults.

Local pytest/static results are not formal `TST-013` or `TST-028` evidence and
do not represent hosted CI, PostgreSQL/broker runtime, staging, deployment,
release, or Production readiness. `DEBT-W1-018` (ST-0203 owner drift) remains
outside this Story's ownership. `DEBT-W1-019` remains `NOT_EXECUTED` for live
database/broker, staging, provider, and Production evidence.
