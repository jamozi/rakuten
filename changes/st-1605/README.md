# ST-1605 deterministic local failure-injection drill

Classification: `LOCAL_SYNTHETIC_NON_ATTESTING`.

This implementation-first Story slice renders five fixed DEV/CI tabletop
references and executes one in-process ST-1405 behavior observation for review.
It does not execute a provider request, database or queue operation,
notification, publication, rollback, browser action, staging drill, release,
or Production action.

For every one of the six scenarios it also records a deterministic local
safe-degradation selection and a synthetic engineering-responder selection.
Those records use a fixed timestamp, `LOCAL_LOG_ONLY`, no real owner identity,
no notification, no command authority, and zero external effects. They are
maximum-safe local acceptance coverage only: a recorded synthetic response is
not an actual owner response, alert delivery, runbook execution, or operational
evidence.

In exact evidence terms, a recorded synthetic response is not an actual owner response.

## Implemented local boundary

The owner generator preserves these exact scenarios from fixed inputs:

1. Rakuten provider unavailability is a static safe-degradation tabletop
   reference. It does not contact Rakuten or observe provider behavior.
2. OpenAI unavailability is a static route-disablement and quarantine tabletop
   reference. It does not contact OpenAI or observe provider behavior.
3. Database unavailability is a static frozen-write and last-safe-snapshot
   tabletop reference. It does not open a database connection or observe
   database behavior.
4. Queue failure is a static producer-pause and future idempotent-replay
   tabletop reference. It does not connect to a queue or observe queue behavior.
5. A real ST-1405 `RecordedKillSwitchAdapter` and
   `KillSwitchRuntimeService` target the adapter's `ENV-CI` boundary. The inert
   authentication and step-up guard fixture is necessarily development-only
   and is constructed separately in `ENV-DEV`; the overall process context is
   `LOCAL_SYNTHETIC`. A fixed engaged generation is read and publication
   commands are denied. No command is issued, no adapter-owned kill-switch
   state changes, and no event intent is created or delivered.
6. Rollback is a static tabletop reference. It performs no rollback, deploy,
   migration, smoke test, or environment action and observes no rollback
   behavior.

Every scenario uses a fixed timestamp and UUID inventory. Before importing the
FI-005 runtime, the generator descriptor-reads and checksum-validates the exact
closed FI-005 transitive repository module inventory. At the `raos.adapters`
and `raos.ports` package boundaries it creates explicitly allowlisted
source-free namespace packages, so unrelated package exports, provider SDKs,
and downstream dependencies are not imported. A temporary
closed RAOS finder/loader then compiles and executes the captured module bytes
in memory; it never reopens a source path, rejects every preloaded RAOS module
and unlisted RAOS dependency, and removes only the exact module objects created
by its own loaders afterward. A foreign RAOS module inserted during the scope,
including a replacement at an expected name, causes failure but is never
deleted as if it were loader-owned. The fresh-process regression also denies a
synthetic provider credential-environment read and proves that neither an
unrelated provider SDK nor the synthetic value is retained. All other inputs
are likewise checksum-pinned. Before any ST-1506 helper bytes are read or
executed, a local descriptor-relative bootstrap rejects a preloaded
helper-module name without replacing it. It then rejects symlinked ancestors
and leaves, reads a bounded regular file, and executes only the same exact
hash-pinned helper bytes it verified. The generator has no
network/provider/credential action surface and writes only its two Story-owned
generated artifacts through that helper. All external action counts are exact
integer zero.

## Dependency and authority boundary

- ST-1602 remains a non-attesting reference plan. OD-011 is unresolved, so
  notifications remain disabled and routing remains `LOCAL_LOG_ONLY`.
- ST-1405 remains a process-local DEV/CI runtime candidate. This Story uses
  only its read/evaluation seam and does not change a kill switch.
- Canonical runbook rows are inert review references. Their commands and
  minimum steps are not executed or validated by this generator.
- Canonical security controls and threat rows remain formally unverified.

The generated artifact may establish only the local deterministic FI-005
read/evaluation behavior observation. FI-001 through FI-004 and FI-006 remain
static tabletop references for the failed systems, not provider/database/queue
or rollback behavior observations. The generator does execute six closed local
safe-response evaluations and records six synthetic responder selections, but
the artifact is not operational evidence and cannot attest that a provider,
database, queue, notification route, runbook, owner, rollback path, or staging
environment behaved correctly.

## Generated ownership

Do not edit generated artifacts by hand. Change the source contract or owner
generator, then run:

```bash
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python -I -B scripts/build_st1605_failure_injection_drill.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python -I -B scripts/build_st1605_failure_injection_drill.py --check
```

The CLI refuses to render, generate, or check unless both Python isolated mode
and no-bytecode mode are active before any non-builtin import. `-I` prevents an
ambient `PYTHONPATH` or user site from selecting an unpinned dependency, while
`-B` prevents source imports from creating `__pycache__` or `.pyc` outside the
two-file output allowlist. The in-memory RAOS loader independently prevents
validation-to-import path drift.

Owned outputs:

- `changes/st-1605/generated/failure-injection-drill.local-synthetic-evidence.v1.json`
- `changes/st-1605/manifest.yaml`

## Explicitly unexecuted

Formal `TST-028`, a fault proxy, real timeout/retry behavior, provider calls,
database and queue integration, alert delivery, notification routing, owner
response, runbook validation, a staging drill, rollback execution, hosted CI,
release, and Production remain `NOT_EXECUTED` or `NOT_AUTHORIZED`. Story
acceptance remains false and effective Canonical status remains unchanged.

In exact status terms: owner response is `NOT_EXECUTED`, runbook validation is
`NOT_EXECUTED`, staging drill is `NOT_EXECUTED`, and Story acceptance remains false.
