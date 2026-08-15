# ST-0805 — pure local editorial policy evaluator

Classification:
`PURE_DETERMINISTIC_LOCAL_EDITORIAL_POLICY_EVALUATOR`.

This Story implements the approved in-memory evaluation boundary for the
editorial policy catalog. It accepts one complete set of strict, pre-resolved
policy, quality-axis, zero-tolerance, gate, and predecessor assessments. It
does not inspect article text, derive detector outcomes, read a catalog at
runtime, persist a Finding, allocate an authoritative lifecycle ID, expose an
API, run a job, emit an event, authorize publication, or perform rollback or
pause.

## Exact catalog boundary

- The evaluator pins all 40 policies from `RAOS-CONTENT-POLICY-001` version
  `0.1`, including exact rule text, severity, stage, code, and enforcement.
  The installed source SHA-256 is
  `d68a584c9ef23de379fdad3f28a087b55e604d33d8d88756e32aeab04ef3220a`.
- It pins all eight quality axes, their weights and blocking floors, the exact
  score threshold `85`, all 13 zero-tolerance labels, and all 12 quality gates
  from `RAOS-CONTENT-QG-001` version `0.1` / quality model `1.0.0`. The
  installed source SHA-256 is
  `90ab554aa55dda335ba69bbb306772306494e2e4ba899c3d22af4a9d9a030efb`.
- The review checklist is bound as `RAOS-CONTENT-REVIEW-001` version `1.0.0`,
  SHA-256
  `8373dbd354c751c699d02bc8c49b18074ae2e10a2ed0573ebd77d99103d3ea63`.
  The content test matrix is bound by SHA-256
  `9be140d6f7015bf8c464993a34d127b2e8c118fd0ed49d20d113fb399ed8a564`.
- A full run requires each policy, axis, signal, gate, and required predecessor
  coordinate exactly once. Unknown, duplicate, missing, cross-article,
  wrong-stage, wrong-version, wrong-source, or malformed coordinates fail
  closed as `INVALID_INPUT`.
- Catalog stage remains an exact bound coordinate. The evaluator does not
  infer applicability, precedence, ownership, derivation, or
  not-applicable semantics.

## Finding and waiver boundary

`INVALID_INPUT`, `NOT_EVALUATED`, and an explicit semantic `FAIL` are separate
states. Missing, unavailable, unproven, or `NOT_EVALUATED` input makes local
eligibility false without manufacturing a policy violation. Only a valid
explicit policy `FAIL` returns an immutable local Finding. That Finding binds
the policy ID/version/source hash/severity, article version, exact catalog
stage, one closed target reference, closed evidence and detector
reference/hash pairs, the caller-supplied UTC evaluation time, `FAIL`, and
`UNRESOLVED`.

The closed target vocabulary is exactly `ARTICLE_VERSION`, `BLOCK`, `CLAIM`,
`PRODUCT`, `OFFER`, `LINK`, and `SOURCE_PACKET`. No raw target or Finding text
is accepted or returned.

- A `BLOCKER` failure is returned as blocking. Every structurally valid
  blocker waiver attempt is `DENIED_BLOCKER`.
- A `MAJOR` failure remains `MAJOR`, nonblocking in canonical classification,
  and unresolved. Its valid structural waiver request may return only
  `PENDING_HUMAN_AUTHORITY`.
- Every waiver is non-effecting. It never becomes approved, resolves or
  suppresses a Finding, changes a score or gate, or makes the result eligible.
  Reason, evidence, approver, and audit inputs are closed reference/hash pairs.
- Only article-version scope and the caller's exact article version are
  structurally eligible in this local seam. Cross-policy, cross-scope,
  malformed, missing-proof, duplicate, and falsely authoritative inputs fail
  closed. The evaluator performs no expiry calculation and invents no request,
  approval, duration, or 30-day anchor.

## Quality, signal, and gate boundary

Axis values are finite exact `Decimal` inputs, bounded by the catalog weight.
The raw eight-axis sum is retained independently from threshold, per-axis
floor, and aggregate local-eligibility results. Summation uses a fixed local
decimal context and is independent of the caller's ambient precision or
rounding. A score of 100 cannot override a Finding, a triggered or unavailable
zero-tolerance signal, an unavailable predecessor, or a failed/unavailable
gate.

All 13 zero-tolerance signals require explicit state and closed provenance.
They are not mapped to policy IDs. `TRIGGERED` and `NOT_EVALUATED` both make
local eligibility false, while `NOT_EVALUATED` creates no Finding.

All 12 gates are caller-supplied, pre-resolved `PASS`, `FAIL`, or
`NOT_EVALUATED` assessments. There is no local `BLOCKED` state or gate
precedence. A valid explicit `QG-CONT-012` failure may expose only the catalog
symbol `ROLLBACK_OR_PAUSE`; the evaluator never performs either action.

## Deterministic local result

The result uses the versioned implementation-local profile
`ST0805_LOCAL_RESULT_V1` and exposes `local_result_digest`. This serialization
is not a canonical cross-component contract, audit record, formal test result,
or release artifact. It uses sorted keys and compact ASCII-safe JSON, exact
normalized decimals, UTC timestamps with six fractional digits and `Z`,
explicit nulls, stable catalog ordering, and stable ordering of nested
reference/hash evidence. Top-level and nested input permutations therefore
produce byte-identical local JSON and SHA-256. All authority-relevant closed
coordinates are included; raw article, review, prompt, secret, or finance text
is not.

Every evaluated or invalid result unconditionally retains
`publication_authorized=false`, `production_eligible=false`, and
formal-test/live/staging/release/production status `NOT_EXECUTED`.

## Local test coverage

The isolated suite covers every one of the 40 policies across six local runner
behavior classes: compliant pass, explicit failure, Finding traceability,
waiver disposition/non-effect, non-authoritative publication-time
re-evaluation, and byte-identical regression rerun. It also covers:

- raw scores 84, 85, and 100, plus every axis floor;
- every triggered and `NOT_EVALUATED` zero-tolerance signal;
- all 12 gates in failure and unavailable states, including the non-actioning
  `QG-CONT-012` symbol;
- invalid, missing, duplicate, unknown, cross-stage, cross-article, and
  predecessor-binding inputs;
- `PASS`/`FAIL` without proof and malformed `NOT_EVALUATED` shapes;
- blocker denial and Major pending-human, always-ineffective waiver behavior;
- nested/top-level permutations, hostile ambient Decimal contexts, and digest
  sensitivity across every policy, axis, signal, gate, predecessor, waiver,
  timestamp, target, and article binding that admits a valid alternate value;
- finance-, review-body-, prompt-, secret-, and raw-content-like reference
  rejection with closed redacted errors/results;
- mutable collections, runtime subclasses, tampered exact wrappers, and proof
  that evaluation performs no file, environment, clock, network, database,
  adapter, event, job, publication, rollback, or pause side effect.

These are synthetic fixture paths over caller-supplied detector results. They
do not implement or prove any real detector's coverage and do not execute
formal TST-019 or TST-020.

## Local verification

Environment: Linux linked worktree, CPython 3.14.6, pinned uv 0.12.1, pytest
9.1.1, Ruff 0.16.1, and mypy 2.3.0. Checks were executed from exact working
directory `/home/minami/rakuten/.worktrees/st-0805`, with each Story suite in a
separate pytest process:

```text
env -u VIRTUAL_ENV PYTHONDONTWRITEBYTECODE=1 \
  /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv \
  run --locked --no-sync --no-env-file \
  pytest -p no:cacheprovider -q tests/st0805
  PASS — 361 passed

same pinned command, tests/st0605
  PASS — 61 passed
same pinned command, tests/st0802
  PASS — 59 passed
same pinned command, tests/st0804
  PASS — 75 passed

same pinned command, ruff check --no-cache <exact ST-0805 Python files>
  PASS — All checks passed
same pinned command, ruff format --check --no-cache \
  <exact ST-0805 Python files>
  PASS — 6 files already formatted

env -u VIRTUAL_ENV PYTHONDONTWRITEBYTECODE=1 \
  MYPYPATH=python:tests/st0805 \
  /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv \
  run --locked --no-sync --no-env-file \
  mypy --strict --explicit-package-bases --cache-dir=/dev/null \
  python/raos/domain/editorial/policy_engine.py \
  tests/st0805/conftest.py \
  tests/st0805/test_catalog.py \
  tests/st0805/test_policy_engine.py \
  tests/st0805/test_boundaries.py \
  tests/st0805/test_negative_cases.py
  PASS — no issues in 6 source files

env -u MAKEFLAGS -u MAKEFILES \
  make --no-builtin-rules --no-builtin-variables check-workspace
  PASS — no workspace drift; 42 directories checked

scripts/python_toolchain.sh \
  --uv /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv \
  contract-gate
  PASS — reconstruction 306 artifacts; verifier PASS; isolated ST-0104
  166 passed in 223.32s

python3 scripts/scan_secrets.py --worktree
  OPERATIONAL ERROR in linked worktree — exit 2,
  ERROR code=unsafe-git-metadata source="."
same scanner --worktree on a non-git fallback snapshot from git archive HEAD,
overlaid with the exact seven ST-0805 files
  PASS — exit 0, no findings or output

git diff --check and git diff --cached --check
  PASS — no output
```

The secret scanner requires `.git` to be a directory before using Git
enumeration, so the linked-worktree `.git` file is rejected before content is
scanned. The approved fallback uses a complete temporary snapshot of tracked
`HEAD`, overlays only the seven owned files, and invokes the same scanner in
its deterministic non-git walk mode. No scanner rule or repository file is
changed.

### Strict Pyright closure follow-up — 2026-08-15

The bound-reference collection validator now gives tuple members the static
type `object` only after the existing exact runtime-type guard accepts the
container. The post-check cast is a runtime no-op: it does not coerce, copy,
filter, or reorder a value, and it does not assume a member is a
`BoundReference` before the existing validator and exact-type assertion prove
that fact. Collection rejection, member-validation and error precedence,
duplicate detection, prohibited-reference detection, serialized bytes,
digest, public API, and authority boundaries therefore remain unchanged. No
`Any`, ignore directive, Pyright configuration change, or relaxed diagnostic
is used.

With Node 24.18.1, Pyright 1.1.411, and CPython 3.14.6, exact file-level
diagnostics fell from three to zero and the same whole-project invocation fell
from 78 to the 75 diagnostics owned by other Stories. The isolated ST-0805
suite remained 361 passed; strict mypy, Ruff check, and Ruff format-check also
remained clean. Dependency suites ST-0605, ST-0802, and ST-0804 passed 61, 59,
and 75 tests, and the ST-0807 consumer passed 145 tests.

The approved ST-1703 handoff intentionally remains byte-bound to the prior
ST-0805 source. Its full suite reached 754 passed and failed closed in 23
source-binding/runtime-manifest CLI cases after this source hash changed. This
Story does not rewrite that approved handoff, weaken its binding, or claim the
ST-1703 runtime has been reapproved; a separately authorized rebind remains
required before those commands can execute again.

The exact owned files are:

```text
python/raos/domain/editorial/policy_engine.py
tests/st0805/conftest.py
tests/st0805/test_catalog.py
tests/st0805/test_policy_engine.py
tests/st0805/test_boundaries.py
tests/st0805/test_negative_cases.py
changes/st-0805/README.md
```

Formal TST-019/TST-020, real detector coverage, hosted CI, runtime/persistence,
API/adapter/job/event integration, human waiver or approval, live validation,
staging, release, publication, rollback/pause execution, and production remain
`NOT_EXECUTED`. No local result or command above grants publication or release
authority.
