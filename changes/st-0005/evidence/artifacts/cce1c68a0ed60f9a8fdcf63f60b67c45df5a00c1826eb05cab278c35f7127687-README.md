# ST-0706 recorded AI job orchestration seam

Status: `LOCAL_IMPLEMENTATION_CANDIDATE`

This Story implements the maximum reversible local portion of approved
ST-0706 for exact `RuntimeEnvironment.ENV_DEV` only. It accepts an already
authorized ST-0704 route reservation and performs at most one metadata-only,
pre-scripted provider observation. It is not a durable worker, queue consumer,
provider integration, validator runtime, or release artifact.

The ordinary advisory Pro run `20260811T123818Z-1c2c93ad11ff` ended as
`PRO_UNAVAILABLE_FALLBACK` with sanitized reason
`RESPONSE_NOT_IDENTIFIABLE`. No response was resent and no Pro approval or new
design authority is claimed. Implementation proceeds only from the approved
canonical Story, the owner-approved implementation-first ExecPlan, installed
contracts, and committed predecessor semantics.

## Implemented local boundary

- Closed immutable domain values bind operation/idempotency identity, exact AI
  and operations job UUIDs, task and target identity, source packet, ST-0704
  authorization, input artifact UUID/SHA-256, explicit deadline, attempt
  counts, coherent cancellation state, and the exact ST-0705 plan identity and
  hash. Their canonical fingerprint contains metadata only.
- Domain values require exact built-in types, exact UUID objects, the explicit
  UTC singleton, bounded safe tokens, lowercase SHA-256, bounded integers, and
  exact enum members. Displays are redacted and generic pickling is denied.
- Provider request/outcome records retain only identifiers, hashes, token
  counts, stable closed classifications, an optional opaque provider request
  identifier, and cost. They contain no raw input or output.
- A success requires one well-formed provider success, one exact recorded
  ST-0705 `PASS`, exact actual-cost budget commit not exceeding the reservation,
  and append of the succeeded observation. Every other terminal/deferred path
  emits only the requested and failed metadata observations when the sink is
  available.
- Idempotent replay returns the exact stored result without another provider,
  validation, budget, or event side effect. A changed fingerprint or conflicting
  AI/operations job binding fails closed before those collaborators.
- Deadline and cancellation are checked before provider execution and release
  the exact active fixture reservation when possible. Provider invocation is
  never retried or rerouted. A retryable recorded failure can return only
  `RETRY_DEFERRED` when the explicit attempt remains below the explicit maximum;
  no retry is scheduled or performed.
- Known incurred cost is committed even when validation fails. Unknown cost
  after a malformed or throwing provider burns the full reservation and trips
  the exact route circuit. Refusal, timeout, validation failure/unavailability,
  budget mismatch, and event failure remain explicit fail-closed results.
- The recorded adapter is process-local, guarded by an `RLock`, constructed
  with an explicit positive capacity, consumes provider and validation scripts
  in exact order, and retains append-only metadata snapshots. It has no
  eviction, delete, clear, export, flush, retry, replay, release-from-quarantine,
  or background behavior.

The ST-0705 reference plan remains non-executable. A scripted `PASS` is
`TEST_ONLY` observation data and cannot establish content validity, Story
acceptance, release eligibility, or formal test evidence. Quarantined or
blocked output has no approval or release method in this slice.

## Explicit exclusions

The owned implementation contains no provider SDK or OpenAI call, queue or
broker, worker loop, ST-1404 dependency, repository/database/UoW/SQL, migration,
artifact bytes, filesystem access, environment or credential lookup, HTTP or
socket access, logging or telemetry, clock/random/UUID generation, subprocess,
thread/task creation, deployment, staging, live operation, release, or
Production configuration. It does not choose or authorize a task, route,
provider, model, prompt, output schema, price, budget, retry policy, fallback,
or business decision.

## Local verification

Use the pinned repository Python toolchain in locked, offline, no-cache,
no-sync, no-env-file, and no-python-download mode:

```bash
UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python "$UV" run \
  --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads pytest -p no:cacheprovider -q tests/st0706

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python "$UV" run \
  --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads ruff check \
  python/raos/domain/ai/job_orchestration.py \
  python/raos/ports/ai_job_orchestration.py \
  python/raos/application/ai/job_orchestration.py \
  python/raos/adapters/recorded_ai_job_orchestration.py tests/st0706

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python "$UV" run \
  --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads mypy --strict \
  python/raos/domain/ai/job_orchestration.py \
  python/raos/ports/ai_job_orchestration.py \
  python/raos/application/ai/job_orchestration.py \
  python/raos/adapters/recorded_ai_job_orchestration.py tests/st0706
```

## Remaining governed work

Formal `TST-013` and `TST-017`, hosted CI, durable idempotency/inbox/outbox and
lease semantics, queue/DLQ/retry scheduling, persistent job/artifact/event
storage, executable output validation, real provider/account/credential and
cost verification, operational telemetry and runbooks, integration review,
staging, release, deployment, and Production remain `NOT_EXECUTED`. Canonical
Story status, generated status/evidence artifacts, shared exports, owner
manifests, and the implementation-first debt ledger remain unchanged.
