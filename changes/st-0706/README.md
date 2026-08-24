# ST-0706 recorded AI job orchestration

Status: `LOCAL_IMPLEMENTATION_COMPLETE`

ST-0706 now contains two versioned, compatible local seams. The original V1
one-attempt process-local orchestration interface is preserved byte-for-byte.
V2 closes the Story-local durability gap with an AI-specific canonical state
document and transition service backed by a caller-owned atomic CAS port. It
does not implement the generic dispatcher, lease runner, retry scheduler, or
DLQ runtime owned by ST-1404.

Both versions are recorded/synthetic development artifacts. They grant no
provider, credential, publication, staging, release, or Production authority.
V2 activation defaults to disabled and accepts explicit `ENV-DEV` or `ENV-CI`
fixture activation only.

## Preserved V1 interface

The existing modules remain unchanged:

- `raos.domain.ai.job_orchestration`
- `raos.ports.ai_job_orchestration`
- `raos.application.ai.job_orchestration`
- `raos.adapters.recorded_ai_job_orchestration`

V1 still executes at most one pre-scripted metadata-only provider observation,
performs the existing recorded ST-0705 validation and ST-0704 budget-control
exchange, and retains process-local state. Existing callers and historical
tests therefore keep their original behavior.

## V2 durable-state boundary

The V2 domain encodes one strict canonical JSON state document. The bytes bind
the exact queue ID, schema version, recorded policy ID, and storage revision.
Unknown fields, alternate JSON bytes, oversized state, mismatched revision,
duplicate identities, invalid nested commands, and broken hashes fail closed.
The document is bounded to 32 AI jobs, 128 outbox intents, 1 MiB, three attempts,
and three completion receipts per job.

The persistence port exposes only:

1. `load(queue_id) -> bytes + revision + derived SHA-256`
2. `compare_and_swap(queue_id, expected revision, expected state SHA-256,
   replacement canonical bytes)`

The caller owns the actual atomic persistence implementation. ST-0706 chooses
no database, broker, filesystem format, migration, or transaction runtime. The
recorded adapter executes this contract under an `RLock`, can export exact
bytes/revision, can rehydrate them into a separate adapter/service instance,
and can simulate a commit whose result becomes uncertain after the state was
atomically applied.

## Deterministic transitions

- Enqueue binds the V1 command fingerprint, idempotency key, AI job UUID, and
  operations job UUID. An exact replay performs no write and creates no second
  event intent. A changed binding fails closed.
- Claim selects one due AI job deterministically and records an explicit lease
  token hash plus monotonically increasing job-local epoch. Completion requires
  the exact worker, token, epoch, attempt, job, and command fingerprint.
- Completion receipts make a post-commit crash/reload replay idempotent. The
  same lease with a changed outcome is rejected, as are stale writers and stale
  or expired leases.
- Retry eligibility is a pure decision. The exact recorded delays after
  attempts one and two are 7 and 31 seconds. They are persisted timestamps;
  there is no sleep, loop, jitter selection, automatic scheduling, fallback,
  or redrive.
- Retry is permitted only for the contract allowlist, within the command and
  policy attempt cap, before the deadline, and with remaining reserved cost.
  Exhaustion enters non-redrivable `DEAD_LETTERED` state.
- Unknown cost, cost overrun, indeterminate outcome, and ambiguous expired
  lease enter `QUARANTINED`. A known total never exceeds the exact ST-0704 job
  reservation. Deadline and cancellation enter closed terminal states.
- Requested/succeeded/failed event records are transactionally stored as
  metadata-hash-only `RECORDED_PENDING` outbox intents. No payload or dispatch,
  publication, delete, acknowledgement, or approval method exists.

The delay values and fixture cost boundary are implementation data for local
tests only. They do not resolve OD-009 or define a live retry/cost policy.

## Owner contract and generator

`contracts/durable-ai-job-queue.v2.yaml` pins every Canonical, dependency,
schema, failure-taxonomy, and V1 compatibility source by exact SHA-256. The V2
domain pins that owner contract hash. The owner generator validates the closed
contract and bindings, then writes only:

- `generated/durable-ai-job-queue.v2.json`
- `manifest.yaml`

Its writer is exactly hash-bound to the shared hardened publication primitive:
existing targets use descriptor-relative `renameat2(RENAME_EXCHANGE)` with
displaced identity and reverse verification; missing targets use hardlink
no-clobber installation. Foreign files are preserved across target/parent
swaps and rollback. `--check` is no-write and verifies exact bytes and mode.

## Local verification

Use the pinned repository toolchain:

```bash
UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python TMPDIR=/tmp "$UV" run \
  --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads python scripts/build_st0706_durable_ai_job_queue.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python TMPDIR=/tmp "$UV" run \
  --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads python scripts/build_st0706_durable_ai_job_queue.py --check

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python TMPDIR=/tmp "$UV" run \
  --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads pytest -p no:cacheprovider -q tests/st0706
```

Ruff format/check, strict mypy for the V1/V2 runtime, dependency/historical
suites, changed-file secret scanning, generator no-write evidence, and
`git diff --check` are recorded in the local completion evidence.

## Remaining governed work

Generic queue polling, dispatcher ownership, database/broker adapters, lease
renewal, operational retry scheduling, DLQ storage/redrive, executable
ST-0705 content validation, budget settlement across a crash, live provider and
account cost verification, telemetry/runbooks, formal `TST-013`/`TST-017`,
hosted CI, integration status application, staging, publication, release,
deployment, and Production remain `NOT_EXECUTED`. The recorded adapter is crash
and restart evidence, not production persistence evidence.
