# ST-0901 PR1 — pure review-workflow domain

Classification: `PURE_DETERMINISTIC_LOCAL_REVIEW_WORKFLOW_DOMAIN`.

This PR1 slice implements only immutable publishing-domain values, the exact
installed human-review checklist catalog, the canonical review-assignment
state machine, and structural review-decision validation. It does not expose
an application command, authorize a principal, persist or append a decision,
execute a PUBADM operation, mutate a Finding, approve publication, or perform
any external action.

## Exact checklist boundary

- The catalog is the exact installed `RAOS-CONTENT-REVIEW-001` version
  `1.0.0`, with all 75 records `REV-001` through `REV-075` in canonical order.
  Its installed source SHA-256 is
  `8373dbd354c751c699d02bc8c49b18074ae2e10a2ed0573ebd77d99103d3ea63`.
- Each catalog item retains only its installed ID, section, check text, response
  vocabulary, and installed evidence-or-comment rule. This slice does not
  infer severity, blocker status, applicability, or review-type ownership.
- A decision draft must bind the exact checklist version and hash and contain
  every installed item exactly once. Input order is irrelevant; validated
  output is always in canonical catalog order. Unknown, malformed, missing,
  and duplicate IDs fail closed.
- Checklist statuses are exactly `PASS`, `FAIL`, and
  `NOT_APPLICABLE_WITH_REASON`. A `FAIL` requires at least one immutable
  evidence reference or one nonempty human comment. Every not-applicable input
  fails closed as `CHECKLIST_APPLICABILITY_UNRESOLVED`; PR1 provides no positive
  applicability decision.
- Evidence uses strict UUIDv7 identity and lower-case SHA-256 coordinates bound
  to the same assignment and article version. Duplicate evidence IDs and
  cross-assignment or cross-article evidence fail closed. Nested evidence and
  complete results are rebuilt and deterministically ordered.

## Assignment state machine

Creation fixes the assignment ID, article-version ID, review type, assigning
principal, assigned principal, priority, and creation time. These creation
coordinates remain unchanged through every transition. Priority is an exact
plain integer in the inclusive range 0 through 100; booleans and subclasses
are rejected.

The only transitions are:

```text
ASSIGNED -> IN_PROGRESS
ASSIGNED -> CANCELLED
IN_PROGRESS -> COMPLETED
IN_PROGRESS -> CANCELLED
```

All other transitions, including direct `ASSIGNED -> COMPLETED`, fail closed.
State-specific timestamps and lock versions are structurally exact. Completion
requires an immutable decision reference whose assignment and article-version
coordinates exactly match the assignment. That reference has no persistence,
history, supersession, or effective-decision semantics. `PUBADM-004` is not an
assignment transition and is not implemented here.

## Decision boundary

The decision vocabulary is exactly uppercase `APPROVE`,
`CHANGES_REQUESTED`, and `REJECT`. Lowercase, unknown, near-match, and imported
ED-030 vocabulary are rejected without translation. `CHANGES_REQUESTED` and
`REJECT` can pass structural validation. Every `APPROVE` attempt fails closed
as `APPROVE_GATE_UNRESOLVED`; this slice contains no positive approval
eligibility path and does not use ST-0805 local eligibility as proof.

Human summaries and comments are bounded, nonempty, edge-trimmed UTF-8 text
without control characters. Their contents, evidence locators, opaque IDs, and
timestamps are never included in repr or exceptions. Closed failures expose
only stable codes. Invalid enum and invalid UTF-8 paths retain no caller value
in args, repr, cause, or context chains. Domain records are frozen, slotted,
non-pickleable, and reject mutable collection inputs and runtime subclasses at
strict seams.

## Purity and excluded behavior

Import and evaluation do not read files, YAML, environment variables, clocks,
randomness, UUID generators, networks, databases, or providers. Callers supply
all identifiers and timestamps. No FastAPI route, repository, database,
migration, unit of work, transaction, durable idempotency, event, outbox, job,
queue, notification, adapter, publication, approval record, waiver, live
identity, secret, or production behavior is present.

## Local test coverage

The isolated tests independently hash and load the installed checklist and
verify its exact version, count, IDs, fields, and mutation sensitivity. They
also cover:

- complete `PASS` and justified `FAIL` checklists, plus missing justification;
- duplicate, missing, unknown, malformed, lowercase, and mutable inputs;
- every positive and forbidden assignment-state pair, timestamp/state shapes,
  lock versions, completion binding, and priority boundaries 0 and 100;
- all decision vocabulary, permanent PR1 refusal of N/A and approval, and
  structural `CHANGES_REQUESTED`/`REJECT` validation;
- cross-assignment and cross-article evidence and completion references;
- exact scalar types, booleans, subclasses, frozen coordinates, nested tamper
  revalidation, rebuilt value detachment, and deterministic permutation output;
- exception-chain redaction, non-pickleability, and import/evaluation
  side-effect tripwires.

These are local implementation tests over synthetic caller-supplied values.
They are not formal TST evidence and prove no real authorization, persistence,
detector, database, API, review, approval, or publication path.

## Local verification

Environment: Linux linked worktree at
`/home/minami/rakuten/.worktrees/st-0901`, CPython 3.14.6, pytest 9.1.1,
Ruff 0.16.1, mypy 2.3.0, and uv 0.12.1. The exact linked worktree was not
hydrated; local Python checks used the repository-pinned environment at
`/home/minami/rakuten/.venv` with the linked worktree's `python` directory on
`PYTHONPATH`. Story suites were run in separate pytest processes.

```text
env -u VIRTUAL_ENV -u PYTEST_ADDOPTS -u PYTEST_PLUGINS \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  /home/minami/rakuten/.venv/bin/python -m pytest \
  -p no:cacheprovider -q tests/st0901
  PASS — 87 passed

same isolated command, tests/st0403
  PASS — 37 passed
same isolated command, tests/st0805
  PASS — 361 passed

/home/minami/rakuten/.venv/bin/ruff check --no-cache \
  <exact ST-0901 source and six test files>
  PASS — All checks passed
/home/minami/rakuten/.venv/bin/ruff format --check --no-cache \
  <exact ST-0901 source and six test files>
  PASS — 7 files already formatted

MYPYPATH=python:tests/st0901 \
  /home/minami/rakuten/.venv/bin/mypy --strict \
  --explicit-package-bases --cache-dir=/tmp/st0901-mypy-cache-final \
  <exact ST-0901 source and six test files>
  PASS — no issues in 7 source files

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  /home/minami/rakuten/.venv/bin/python -c \
  '<compile exact source; import module; assert catalog count/version/hash>'
  PASS — compile/import smoke

env -u MAKEFLAGS -u MAKEFILES \
  make --no-builtin-rules --no-builtin-variables check-workspace
  PASS — no workspace drift; 42 directories checked

env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 \
  python3 scripts/import_raos_design.py verify
  PASS — 105 imported files; 104 package checksums; read order PASS

python3 scripts/scan_secrets.py --worktree
  OPERATIONAL ERROR in linked worktree — exit 2,
  ERROR code=unsafe-git-metadata source="."
same scanner --worktree on a non-git fallback snapshot from git archive HEAD,
overlaid with the exact eight ST-0901 files
  PASS — exit 0, no findings or output

git diff --check and git diff --cached --check
  PASS — no output
```

The secret scanner requires `.git` to be a directory before Git enumeration,
so the linked-worktree `.git` file is rejected before content scanning. The
fallback uses a complete temporary snapshot of tracked `HEAD`, overlays only
the eight owned files, and runs the unchanged scanner in deterministic non-git
walk mode. No scanner rule or repository file is changed.

The linked-worktree `contract-gate` was initially `NOT_EXECUTED`: its pinned
environment was not hydrated, and hydration was outside this slice. A read-only
prerequisite probe with
`scripts/python_toolchain.sh --uv /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv contract-check`
could not load the verifier's installed `yaml` dependency. The uv invocation
ended before a contract check with exit 1 and
`ModuleNotFoundError: No module named 'yaml'`. It transiently created an
otherwise empty 108 KiB `.venv`; that directory was moved to trash
recoverably, and this worktree has no `.venv`. Per the integration-owner
boundary, that linked-worktree probe was not rerun or hydrated. This was an
environment limitation, not a test failure or contract result.

The parent then created a disposable full checkout at the committed PR1 head,
verified its commit and tree, copied the existing repository-pinned `.venv`
without syncing or retrieving packages, and ran the unchanged trusted wrapper:

```text
env -u MAKEFLAGS -u GNUMAKEFLAGS -u MAKEFILES -u MFLAGS -u MAKEOVERRIDES \
  scripts/python_toolchain.sh \
  --uv /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv \
  contract-gate
  PASS — reconstruction check: 306 artifacts
  PASS — offline contract verifier
  PASS — isolated ST-0104: 166 passed in 228.03s

python3 scripts/scan_secrets.py --worktree
  PASS — exit 0, no findings or output, regular .git directory checkout
```

This disposable-checkout result is local contract/static evidence. It is not
hosted CI or formal ST-0901 suite evidence.

The exact owned files are:

```text
python/raos/domain/publishing/review_workflow.py
tests/st0901/conftest.py
tests/st0901/test_catalog.py
tests/st0901/test_checklist_validation.py
tests/st0901/test_assignment_state_machine.py
tests/st0901/test_boundaries.py
tests/st0901/test_failure_isolation.py
changes/st-0901/README.md
```

Formal TST-011/TST-012/TST-020/TST-021/TST-022, predecessor TST-019,
HTTP/API behavior, real authentication and authorization, database guards,
durable idempotency, audit artifacts, live review, staging, release,
publication, and production remain `NOT_EXECUTED`. No local result grants
approval, publication, release, or production authority.
