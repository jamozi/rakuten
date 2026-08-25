# ST-1303 V2 local completion record

This file records local implementation evidence only. It cannot change the
Canonical registry or establish formal TST, live, staging, release or Production
status.

## Implemented boundary

- Executable recorded/synthetic Direct / Estimated / Unattributed engine.
- Exact integral-Decimal JPY conservation and deterministic remainder policy.
- Versioned five-slot measurement contract and explicit unavailable semantics.
- Process-local idempotent run port/adapter with conflict rejection.
- Single-output deterministic owner generator and hostile/tamper tests.
- Finance/editorial/publication separation encoded as immutable false authority.

## Local verification

Source freeze verification was refreshed from the isolated ST-1303 worktree on
2026-08-25 (JST). These are local results and are not formal TST evidence.

- `python -m py_compile` over the four runtime modules, generator and focused
  tests: PASS.
- `ruff check` over the four runtime modules, both owner generators and both
  ST-1303 test directories:
  PASS (`All checks passed!`).
- `ruff format --check` over the same owned Python inventory: PASS.
- strict `mypy --explicit-package-bases` over the same owned Python inventory:
  PASS (`Success: no issues found in 15 source files`).
- project-wide Pyright over `python/raos`: PASS (`0 errors, 0 warnings, 0
  informations`).
- Both `build_st1303_attribution_engine_reference_plan.py --check` and
  `build_st1303_attribution_engine.py --check`: PASS. Each check was repeated
  after generation and did not write its generated artifact.
- `pytest -q tests/st1303`: PASS (`368 passed`) and the same suite under the
  repository network-denied wrapper: PASS (`368 passed`).
- `pytest -q tests/st1303_v2`: PASS (`74 passed`) and the same suite under the
  repository network-denied wrapper: PASS (`74 passed`). These include
  deterministic generation/replay, hostile fixture, tamper, conservation,
  unavailable-state, exact-JPY and authority-boundary coverage.
- `pytest -q tests/st1202_v2`: PASS (`5 passed`).
- `pytest -q tests/st1302`: PASS (`254 passed`).
- `python scripts/build_st1202_public_event_instrumentation.py --check`: PASS.
- `python scripts/build_st1302_provider_fact_commit_recorded.py --check`: PASS
  (`ST-1302 recorded provider-fact projection checked`).
- `/usr/bin/python3 -I scripts/scan_secrets.py --worktree` over an isolated copy
  of the complete ST-1303 changed-file inventory: PASS (zero findings). The
  repository-wide scanner was not promoted as evidence because its intentional
  `.git`-directory requirement rejects a linked-worktree `.git` file.
- `git diff --check`: PASS.

The frozen synthetic run binds contract SHA-256
`34adb2a67246888ec0773a20ab4ed4c71912fc3a3df653bca559d04f48dda78c`,
input SHA-256
`2fabd6f400c973ef7c7ba20482363b05af1c29bdfd960ad65620a9c5d1052448`
and result SHA-256
`1f7a657452e18a978c496be6a15f133eaa8132c8f9ff990825ed3545a1523054`.
The provider total is exactly JPY 300: Direct 120, Estimated 101 and
Unattributed 79, with difference 0.

Introduced deferred verification debt: none. The formal/live items below are
pre-existing Canonical gates and remain deliberately unclaimed.

The historical non-executable V1 reference owner was rebound to the exact
current ST-1302 artifact bytes, ST-0308 reference projection and shared owner
helper. Both the V1 owner and executable V2 owner now pass generate and
no-write `--check`; V1 remains inert with no activation or authority.

## Remaining formal/live work

`OD-003`, real report/schema/key verification, real attribution calibration,
database/event integration, TST-007/TST-030 formal evidence, provider/network,
live, staging, release and Production remain `NOT_EXECUTED`.
