# ST-1401 — provisional freshness evaluator and explicit-due selector

Classification:
`PROVISIONAL_CANONICAL_SAFE_DEFAULT_DISABLED_RECORDED_FRESHNESS_INTERFACE`

This is the locally complete, DEV/CI-only, non-persistent, non-attesting
implementation of the maximum safe ST-1401 interface boundary while OD-007 is
unresolved. It satisfies the local scheduler/state deliverables with the
installed conservative provisional policy, but it does not change the
Canonical Story status, activate a freshness policy, resolve a category SLA,
or provide formal TST-005/TST-028 evidence. The current integration audit is
`LOCAL-INTEGRATION-CLOSURE-20260825-v1.yaml`; the earlier
`LOCAL-IMPLEMENTATION-COMPLETION-20260824-v1.yaml` remains immutable historical
local evidence.

## Authority and source binding

The implementation uses the installed cumulative contract snapshot only:

- policy `RAOS-CONTENT-FRESH-001`, document version `0.1`, policy version
  `1.0.0`;
- policy path
  `contracts/raos-v0.4/contracts/content/RAOS_06_freshness_update_policy_v0.1.yaml`,
  5,428 bytes, SHA-256
  `a4d490d2a54b3def63c9c240b09d34a759ebd3924e60cfcca438ee979334cea2`;
- matrix path
  `contracts/raos-v0.4/contracts/content/RAOS_06_content_test_matrix_v0.1.csv`,
  142,924 bytes, SHA-256
  `9be140d6f7015bf8c464993a34d127b2e8c118fd0ed49d20d113fb399ed8a564`;
- exact ordered freshness rows `CT-0791` through `CT-0886` (12 classes by
  8 scenarios).

Every result binds authority `PROVISIONAL_CANONICAL_SAFE_DEFAULT` and
activation `DISABLED_UNRESOLVED_OD_007`. `OD-007` remains
`HUMAN_DECISION_REQUIRED`, blocking, and inactive. Category/provider
overrides remain unapplied. The unapproved ST-1701 image-30d candidate is not
an input and is not referenced by the implementation.

## Evaluation boundary

The caller supplies the evaluation time and any observation time explicitly.
Both must be timezone-aware; the implementation reads no clock. Instants are
normalized at value construction into owned, built-in UTC datetimes with
`fold=0` before comparison, so a JST/UTC representation difference or a valid
DST `fold=1` instant does not change the result. Revalidation builds a separate
canonical snapshot and never repairs or otherwise mutates caller inputs.

For a validated, non-future observation, age is evaluated at exact microsecond
boundaries:

- age less than `warning_after_hours`: `FRESH` / `DISPLAY`;
- age greater than or equal to warning and less than blocking: `WARNING` /
  `DISPLAY_WITH_WARNING_QUEUE`;
- age greater than or equal to `blocking_after_hours`: `CRITICAL` /
  `SAFE_DEGRADE`.

Consequently `FRESH-010` (`0` warning / `0` blocking) is immediately
`CRITICAL` at age zero. Its abstract matrix rows remain source inventory, but
the evaluator does not fabricate an impossible valid non-future pre-warning
window.

Missing observations, fetch failures, future observations, and unvalidated
recovery are `UNKNOWN`, `stale: true`, `latest: false`, with
`KEEP_LAST_WITH_STALE_STATE_NOT_LATEST`. Only a validated, noncritical recovery
emits `RESTORE_FIELD_AFTER_VALIDATION`. Recommendation impact can emit only a
`CREATE_REVIEW_CANDIDATE` marker. Automatic recommendation reordering is
always `FORBIDDEN`.

Evaluation does not hide/render a field, update a snapshot, pause an article,
change a CTA, publish, approve, attest, or persist anything. Those policy
effects remain downstream and inactive.

## Explicit-due selector boundary

The selector consumes immutable schedule metadata with a caller-supplied
`next_due_at`; it never derives or updates cadence. It selects only `ACTIVE`
entries due at or before the supplied evaluation time, ordered exactly by:

1. `next_due_at` ascending by UTC instant;
2. `priority` descending;
3. `schedule_id` ascending.

`limit` is an exact integer from 1 through 10,000. Output is a tuple of
metadata-only check intents and deterministic SHA-256 fingerprints. It creates
no queue item, Job, Outbox event, retry, repository row, database transaction,
API request, provider call, or write.

The selector computes the full request fingerprint once per selection and
reuses it for every intent and the selection envelope; it does not repeat a
full schedule hash for each due item. Retained schedule and intent UUIDs,
datetimes, nested entries, and nested outputs are owned snapshots rather than
aliases to caller objects.

The reversible local interface assumptions are a nonzero UUID schedule ID, a
unique SHA-256 subject/target reference, `ACTIVE`/`PAUSED`/`DISABLED` status,
and a nonnegative signed 32-bit technical priority. Duplicate schedule IDs or
subject targets fail closed. `PAUSED` and `DISABLED` entries are inert. These
assumptions do not define a business cadence, SLA, category override, or
provider override and remain subject to Wave-end review.

## Trust and execution boundary

- The inward port exposes only `evaluate` and `select_due`.
- Application and recorded adapter construction accept exactly `ENV-DEV` or
  `ENV-CI`; Integration, staging, recovery, and Production fail closed.
- Recorded fixtures are bounded to 10,000 top-level combined fixture bindings;
  aggregate nested schedule entries across schedule fixtures are independently
  capped at 10,000 before binding or fingerprint work. They are redacted and
  bound at adapter construction into adapter-owned immutable request/result
  fingerprints. Later mutation of caller-owned fixture objects cannot change
  adapter behavior. Failed construction publishes no partial binding state.
  Fixtures contain no raw Fact/Offer/article data.
- Each collaborator is called once. Exceptions are replaced with a closed
  failure code. The expected result is fixed before the call; the collaborator
  receives a separate defensive request snapshot, which must remain unchanged.
  Returned values, nested policy bindings, schedule entries, and intents are
  revalidated against the fixed deterministic reconstruction before any result
  is returned.
- Values and failures are non-pickleable. No filesystem, environment, network,
  provider, database, random source, clock, or state lifecycle is used.

The implementation does not add an API, schema, migration, repository,
provider adapter, generated runtime artifact, Canonical status transition, or
formal evidence record. Its human-readable local completion record has no
runtime or governance authority.
ST-0503 and ST-0605 remain dependency inputs with only their separately
recorded local candidate evidence; this slice does not promote their Canonical
status.

## Focused local checks

Run Story suites in separate pytest processes:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/minami/rakuten/.venv/bin/pytest -q tests/st1401
PYTHONDONTWRITEBYTECODE=1 /home/minami/rakuten/.venv/bin/pytest -q tests/st0503
PYTHONDONTWRITEBYTECODE=1 /home/minami/rakuten/.venv/bin/pytest -q tests/st0605
```

Static checks for the owned sources use the pinned repository environment:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/minami/rakuten/.venv/bin/ruff check \
  python/raos/domain/freshness/freshness.py \
  python/raos/ports/freshness.py \
  python/raos/application/freshness/freshness.py \
  python/raos/adapters/recorded_freshness.py tests/st1401
PYTHONDONTWRITEBYTECODE=1 /home/minami/rakuten/.venv/bin/ruff format --check \
  python/raos/domain/freshness/freshness.py \
  python/raos/ports/freshness.py \
  python/raos/application/freshness/freshness.py \
  python/raos/adapters/recorded_freshness.py tests/st1401
PYTHONDONTWRITEBYTECODE=1 MYPYPATH=python \
  /home/minami/rakuten/.venv/bin/mypy --strict \
  python/raos/domain/freshness/freshness.py \
  python/raos/ports/freshness.py \
  python/raos/application/freshness/freshness.py \
  python/raos/adapters/recorded_freshness.py
```

## Remaining governed and external work

Formal/hosted TST-005, staging reliability TST-028, runtime integration,
category SLA approval, policy activation, provider/live tests, database and
queue integration, renderer/safe-degradation effects, human review workflow,
publication, staging deployment, release, and Production all remain
`NOT_EXECUTED`. Story acceptance and `VALIDATED` status remain false.
