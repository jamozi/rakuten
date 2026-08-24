# ST-1405 recorded kill-switch runtime seam

Local code status: `LOCAL_CODE_COMPLETE_MAX_SAFE`

Canonical Story status remains `NOT_STARTED`; formal `TST-012`, `TST-022`, and
`TST-028` remain `NOT_EXECUTED`. This Story slice implements only the
reversible, provider-neutral DEV/CI runtime needed to review the FR-019 and
SEC-OPS-007 behavior. It creates no publication, provider, staging, release,
or Production authority.

## Implemented safe boundary

- The only switch types are `PUBLICATION` and `AFFILIATE_LINK`. They are
  evaluated independently at the closed `GLOBAL`, `SITE`, `CATEGORY`, and
  `ARTICLE` scopes. Guard evaluation requires the complete site/category/article
  context so a caller cannot omit a narrower applicable scope.
- Every change carries an explicit expected generation and uses one atomic
  process-local compare-and-swap. A lower or conflicting generation cannot
  replace a newer state, a no-state-change command is rejected, and every
  generation is bounded to the non-negative signed-bigint range.
- The adapter stores only the fingerprint of a bounded idempotency key. The
  same key and canonical command returns the original result; the same key and
  a different command fails closed without changing state or adding an intent.
  The canonical command includes its correlation identifier, so a retry must
  preserve that workflow binding. Under the adapter's one lock, an exact replay
  is resolved before freshness fencing; a fresh command must satisfy the full
  observed state and generation floor before mutation. The immutable receipt
  distinguishes replay from mutation and includes the current aggregate state,
  so a historical result never lowers the service's cache fence. The caller
  supplies one exact adapter capacity from 1 through 10,000. At capacity,
  replay lookup remains first while a fresh command fails without eviction or
  state, intent, or idempotency mutation.
- The command service composes the existing ST-0402 `StepUpGuard` before the
  store is called. This does not supply a Production identity or MFA mapping.
- Missing, malformed, unavailable, incomplete, expired, scope-incomplete, or
  generation-downgraded cache observations deny the relevant action. A
  publication cache failure does not alter affiliate eligibility, and an
  affiliate cache failure does not alter publication-command eligibility. A
  cache snapshot is limited to 10,000 entries and oversized exact or forged
  snapshots are rejected before entry copying or identity-set construction. A
  runtime service likewise retains at most 10,000 cumulative observed keys and
  aggregate IDs. A disjoint snapshot that would exceed that union is denied
  before any partial binding; an exact command replay at the same limit still
  returns its original result while a fresh unknown-key command is fenced at
  the atomic adapter boundary.
  successful command also advances the service's generation floor, including
  when the store and cache ports have separate implementations. The service
  binds each accepted generation to its complete immutable state; contradictory
  same-generation bytes, aggregate replacement, timestamp regression, duplicate
  aggregate IDs within a snapshot, and aggregate-ID reuse across observed keys
  deny.
- Time is always an explicit exact aware UTC value. Cache freshness honors the
  declared deadline but is additionally capped at five minutes from load, the
  architecture catalog's affiliate kill-switch target; the same conservative
  cap protects publication. No ambient clock or default TTL is read. A change
  cannot backdate the current state; an equal timestamp remains valid because
  the generation supplies the ordering fence.
- `expires_at` remains unsupported and any non-null value is rejected. Time
  passage cannot silently disengage or release a switch.
- A successful CAS creates one immutable in-memory event intent whose explicit
  envelope is compatible with
  `jp.raos.ops.kill_switch_changed.v1`. The adapter has no publisher, queue,
  outbox, send, or delivery method, so that intent cannot leave the process.
- Reasons are bounded non-narrative codes with redacted display. Failures and
  eligibility diagnostics contain only closed codes; rejected values and
  exception text are not retained.
- `RecordedKillSwitchAdapter` accepts only exact `ENV-DEV` and `ENV-CI`, uses
  in-memory state plus same-process locking, and performs no I/O.
- The event actor UUID is synthetic command metadata in this slice. No mapping
  from the ST-0402 issuer/subject pair to a Production principal or formal audit
  identity is implemented or claimed.

## Dependency boundary

- ST-0402 supplies the provider-neutral step-up guard used before a command.
- ST-0905 now supplies a DEV/CI-only, process-local publication-command
  runtime. This slice remains its independent guard: every ST-0905 command
  must still pass the applicable publication kill-switch decision before any
  future integration may invoke it. ST-1405 does not accept, enqueue, invoke,
  or execute an ST-0905 command and grants no public-write authority.
- ST-1404 remains a recorded one-step Job runtime without durable outbox or
  broker authority. ST-1405 therefore retains an event intent in memory and
  does not import or invoke the Job runtime.

The installed API and data designs include broader switch values and an
optional expiry. This bounded Story implementation intentionally follows the
approved common subset: `PUBLICATION`/`AFFILIATE_LINK`, the four named scopes,
and no expiry. No installed or Canonical contract is edited by this slice.

## Local verification

After the pinned environment has already been hydrated, run the Story suites
in isolated processes:

```bash
UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads pytest -p no:cacheprovider -q tests/st1405
```

Focused Ruff format/lint and strict mypy cover the four source modules and the
isolated test directory. Dependency regressions are run in separate pytest
processes for ST-0402, ST-0905, and ST-1404; the ST-0905 owner generator is
checked with `--check` rather than regenerated.

## Explicitly unexecuted and out of scope

- API routes, HTTP Problem Details, browser/admin UI, ETag transport, durable
  idempotency, PostgreSQL tables/migrations, multi-process locking, durable
  audit, outbox/inbox, broker, cache service, synthetic browser checks, and
  incident service;
- publish, unpublish, rollback, renderer mutation, CTA rendering, cache
  invalidation, database/queue/provider calls, browser use, or external writes;
- real credentials, provider identity/MFA, staging, formal TST execution,
  release, kill-switch changes in a live environment, and Production.

Local pytest/static results are implementation evidence only. They do not
change Canonical Story status, satisfy formal `TST-012`/`TST-022`/`TST-028`,
or establish runtime, staging, release, publication, or Production readiness.
