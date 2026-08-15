# ST-0901 PR2 — recorded review-assignment application seam

Classification: `ST0901_PR2_RECORDED_LOCAL_V1`.

This PR2 slice adds one internal, pure/recorded `ENV-DEV`/`ENV-CI` seam for
`PUBADM-001` through `PUBADM-003` on top of the immutable ST-0901 PR1 review
workflow. It is synthetic local evidence only. It does not implement an HTTP
API, authenticate a person, select a canonical authorization resource, persist
an assignment or audit event, append a review decision, approve an article, or
perform an external action.

## Authority and safe subset

The implementation was bounded by the repository precedence and implementation
protocol, then by the following exact installed sources:

| Authority | PR2 use |
| --- | --- |
| `docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md` and `docs/canonical/08_codex/AGENTS.md` | canonical precedence, one-Story boundary, inward ports, closed external gates |
| `docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml` | ST-0901 and dependencies ST-0403/ST-0805; downstream ST-0902 remains excluded |
| `docs/canonical/00_master/RAOS_master_traceability_v1.0.csv` | FR-009 human approval remains required and unfulfilled by this seam |
| `changes/st-0004/contracts/openapi-admin.v0.4.yaml` | operation IDs, permission strings, idempotency/concurrency coordinates, and exact audit-action names for PUBADM-001..004 |
| `docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml`, `RAOS_10_security_control_catalog_v1.0.yaml`, and `RAOS_10_security_privacy_design_v1.0.md` | deny-by-default authorization, role/scope separation, immutable audit and sensitive-data boundaries |
| `docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml`, `RAOS_11_test_environment_matrix_v1.0.yaml`, and `RAOS_11_acceptance_traceability_v1.0.csv` | local tests must not be promoted to TST-011/012/020/021/022 or live evidence |
| `python/raos/domain/iam/authorization.py` and the ST-0403 application/port/recorded patterns | exact existing `AuthorizationGrant` and opaque `AuthorizationTarget` revalidation |
| `python/raos/domain/publishing/review_workflow.py` and `changes/st-0901/README.md` | PR1 assignment creation, four-state-transition oracle, immutable creation coordinates, and unresolved approval boundary |
| ST-0805 implementation/tests | eligibility remains a non-authoritative dependency and is never treated as approval authority |

The broader HTTP contract is intentionally not claimed. The reconciled local
safe subset is:

| Operation | Implemented recorded-local behavior | Deliberately absent |
| --- | --- | --- |
| `PUBADM-001` | exact read grant and local permission binding; deterministic filtered, ordered assignment snapshots; no mutation | idempotency key, audit artifact/receipt, repository query, pagination transport, HTTP response |
| `PUBADM-002` | exact assign grant; adapter-bound active `HUMAN` actor and reviewer; `assigned_by=actor`, `assigned_to=reviewer`; explicit IDs/time; priority 0..100; local create audit artifact and hash-only replay receipt | real identity, durable write, transaction, database uniqueness, public schema/route |
| `PUBADM-003` | status-transition-only use of all four PR1 transitions; exact strong local If-Match/lock binding; exact `+1` next lock and local ETag; preserved creation coordinates; local update audit artifact and hash-only replay receipt | the broader PATCH mutations for `priority`, `due_at`, and `instructions`; reassignment; a general HTTP ETag implementation |
| `PUBADM-004` | nothing | decision append, effective-decision selection, approval, supersession, Finding mutation or translation |

The status-only `PUBADM-003` cut is a safe implementation-local subset. The
broader PATCH schema is `NOT_IMPLEMENTED` and `NOT_EXECUTED`, not partially
fulfilled by silently inventing mutation semantics.

## Recorded authorization boundary

`RecordedReviewerAuthorizationV1` is produced only by the recorded adapter
through a module-private construction permit. The application exposes one
public `execute(request=...)` path and accepts no caller-supplied actor,
reviewer, grant, authorization record, or substitution path. Before the
exchange, it revalidates the exact operation, request SHA-256, correlation ID,
opaque target, existing ST-0403 `AuthorizationGrant`, local permission string,
actor projection, reviewer projection when applicable, and separate
assignment/article coordinates.

The existing `AuthorizationTarget` is intentionally opaque. PR2 requires exact
object-coordinate equality across the request, adapter-produced authorization
record, and grant. It does not interpret the target kind/resource/state, infer
a hierarchy, or map it to an assignment or article version. A canonical
operation-to-resource mapping is absent and deferred. Assignment and article
coordinates remain separate hash-bound fields.

The adapter reconstructs an exact detached ST-0403 grant from the complete
underlying `AuthorizationDecision` shape. It requires a sealed
`ALLOW`/`RULE_MATCH` decision and revalidates correlation, effect, reason,
policy revision/fingerprint, entitlement revision, matched rule, action, and
opaque target. The authorization record's versioned SHA-256 binds all of those
normalized decision coordinates plus every other serialized local field. A
digest retained when each recorded step is constructed makes later valid-shape
grant/decision substitution fail before exchange as well.

This proves deterministic self-consistency inside one recorded adapter only.
It does not prove that a policy or entitlement was correct, current, or
canonically selected. It is not authentication, identity attestation, a
signature, canonical authorization policy evidence, an audit record, Story
acceptance, or a resolution of OD-005. The local action, permission, target
use, identity projection, serializer/digest, ETag, and audit shapes are all
explicitly `ST0901_PR2_RECORDED_LOCAL_V1` fixture bindings.

## Determinism, replay, and audit artifacts

All identifiers, timestamps, prior snapshots, next snapshots, ETags, grants,
and identity projections are explicit fixture inputs. Runtime clock, UUID,
randomness, filesystem, environment, network, database, event, and publication
sources are not used.

For `PUBADM-002` and `PUBADM-003`, the recorded adapter retains a successful
result under the process-local identity `(operation, SHA256(Idempotency-Key))`.
The exact same request returns the same retained immutable result and
byte-identical canonical bytes without consuming another script step. Reusing
that operation/key with a different request hash fails closed and preserves the
later valid step. Because actor selection belongs to the authorization source
and the public request contains no actor, this key identity is deliberately
process-global rather than actor-scoped. That conservative narrowing also
prevents a later scripted actor from silently reusing the same operation/key.
It is not a canonical or durable idempotency contract.

Create/update results include immutable local artifacts named with the exact
contract actions `review_assignment_create` and `review_assignment_update`,
bound to correlation/request/authorization and before/after coordinates. They
are synthetic values, not appended or durable audit evidence. `PUBADM-001`
returns neither an audit artifact nor an idempotency receipt and does not
populate replay state. Filter, limit, deterministic-order, and result-shape
validation completes before the adapter advances its script index, so an
invalid local LIST outcome remains unconsumed and can be corrected in place.

Every result reports `execution=RECORDED_ONLY` and `readiness=NOT_READY`, and
closes persistence, transaction, unit of work, database enforcement,
cross-operation/audit atomicity, events, outbox, delivery, formal verification,
live, staging, release, production, and publication as `NOT_EXECUTED`.

## Failure and purity coverage

The isolated tests cover positive list/create/update behavior and deterministic
replay plus closed failures for malformed/missing-equivalent/weak/stale local
If-Match values, wrong lock versions, changed idempotent requests, internally
valid receipts bound to the wrong key, wrong
action/permission/opaque target/correlation/request hash, malformed, unsealed,
non-ALLOW, wrong-reason, and valid-shape grant-decision substitution,
actor/reviewer mismatch, inactive/non-human/substitute identity,
duplicate trust paths, changed creation coordinates, forbidden transitions,
undefined field mutation, runtime subclasses, authorization tamper/direct
construction, lowercase/unknown/PUBADM-004/ED-030 vocabulary, secret-text
retention, exception chains, pickling, and ambient side effects.

PR1's fail-closed not-applicable and `APPROVE` behavior remains untouched.
ST-0902 final approval, real identity, Finding mutation/translation, ST-0805
eligibility-as-authority, ED-030 translation, PUBADM-004, publishing, release,
and production are outside this slice.

## Exact owned files

```text
python/raos/domain/publishing/review_assignment_operations.py
python/raos/ports/review_assignment.py
python/raos/application/publishing/review_assignment.py
python/raos/adapters/recorded_review_assignment.py
tests/st0901_pr2/conftest.py
tests/st0901_pr2/test_pubadm001_list.py
tests/st0901_pr2/test_pubadm002_create.py
tests/st0901_pr2/test_pubadm003_update.py
tests/st0901_pr2/test_authorization_idempotency.py
tests/st0901_pr2/test_boundaries.py
changes/st-0901/README_PR2.md
```

No PR1 source/test, package export, generated artifact, canonical document,
contract, route, schema, migration, database code, manifest, lockfile, workflow,
or workspace-layout file is changed.

## Local verification

Environment: Linux linked worktree at
`/home/minami/rakuten/.worktrees/st-0901-pr2`, CPython 3.14.6, pytest 9.1.1,
Ruff 0.16.1, mypy 2.3.0, and uv 0.12.1. The exact linked worktree is not to be
hydrated by this slice; Python checks use the repository-pinned environment at
`/home/minami/rakuten/.venv` with this worktree's `python` directory on
`PYTHONPATH`. Story suites run in separate pytest processes.

Final local results:

| Check | Exact local result |
| --- | --- |
| isolated `tests/st0901_pr2` | PASS — 58 passed in 0.20s |
| isolated PR1 `tests/st0901` | PASS — 87 passed in 0.17s |
| isolated predecessor `tests/st0403` | PASS — 37 passed in 0.07s |
| isolated predecessor `tests/st0805` | PASS — 361 passed in 1.12s |
| exact ten Python files, Ruff check | PASS — All checks passed |
| exact ten Python files, Ruff format check | PASS — 10 files already formatted |
| exact ten Python files, strict mypy | PASS — no issues in 10 source files |
| exact four production files, compile/import/signature smoke | PASS |
| `make check-workspace` | PASS — no drift; 42 directories checked |
| canonical import verification | PASS — 105 imported files, 104 package checksums, read order PASS |
| linked-worktree scanner | OPERATIONAL ERROR — exit 2, `unsafe-git-metadata` before content scan |
| complete-snapshot scanner fallback | PASS — exit 0, no findings or output |
| contract-gate hydration prerequisite | ABSENT — worktree `.venv` and `node_modules` do not exist; gate `NOT_EXECUTED` and no install attempted |

The Story suites were run as separate processes using:

```text
env -u VIRTUAL_ENV -u PYTEST_ADDOPTS -u PYTEST_PLUGINS \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  /home/minami/rakuten/.venv/bin/python -m pytest \
  -p no:cacheprovider -q <one exact Story suite>
```

The exact-file checks used:

```text
/home/minami/rakuten/.venv/bin/ruff check --no-cache \
  <exact four PR2 production files and six PR2 test files>
/home/minami/rakuten/.venv/bin/ruff format --check --no-cache \
  <same exact ten Python files>

MYPYPATH=python:tests/st0901_pr2 \
  /home/minami/rakuten/.venv/bin/mypy --strict \
  --explicit-package-bases --cache-dir=/dev/null \
  <same exact ten Python files>

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  /home/minami/rakuten/.venv/bin/python -m py_compile \
  <exact four PR2 production files>
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  /home/minami/rakuten/.venv/bin/python -c \
  '<import exact four modules; assert execute signature is self, request>'

env -u MAKEFLAGS -u MAKEFILES \
  make --no-builtin-rules --no-builtin-variables check-workspace
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 \
  python3 scripts/import_raos_design.py verify
```

`python3 scripts/scan_secrets.py --worktree` rejects a linked worktree because
its `.git` is a file rather than a directory, before scanning content. The
approved fallback created a complete temporary non-git snapshot from
`git archive HEAD`, overlaid only the exact 11 owned files, and ran the
unchanged scanner in deterministic fallback-walk mode. It exited 0 with no
findings or output; the temporary snapshot was moved to trash recoverably.

The read-only hydration probe found the contract repository input and local
validation resources but no worktree `.venv`, `.venv/bin/python`, or
`node_modules`. Per the approved boundary, `contract-gate` was not invoked,
nothing was installed or synchronized, and no contract result is claimed.

## Strict Pyright closure follow-up — 2026-08-15

The recorded adapter now uses the explicit non-underscored
`build_recorded_reviewer_authorization` domain bridge instead of importing a
private cross-module name. The bridge and constructor permit remain excluded
from `__all__`; neither is a consumer API or a second application trust path.
The bridge still accepts only the complete revalidated request, detached grant,
exact permission, actor, and optional reviewer needed to build one immutable
`ST0901_PR2_RECORDED_LOCAL_V1` self-consistency record. It grants no
authentication or approval authority, and the application still exposes only
`execute(request=...)` with no caller-supplied authorization path.

Identity serialization now stays in a revalidating module-private helper that
returns a fresh scalar-only mapping for canonical hashing; the identity exposes
no payload API. Script steps expose their retained authorization digest through
a getter-only property. Hostile boundary coverage proves bridge and private
permit exclusion, direct-constructor refusal, absence of a public identity
payload, and rejection of writes to the read-only step property. Canonical
bytes, digests, replay identity, error precedence, and result authority flags
remain unchanged. The isolated PR2 suite remained 58 passed.

Formal TST-011, TST-012, TST-020, TST-021, and TST-022 remain
`NOT_EXECUTED`. HTTP/API behavior, real authentication/authorization, database
guards, durable idempotency, durable/atomic audit, live human review, staging,
release, publication, and production remain `NOT_EXECUTED`. No local result
grants approval, publication, release, or production authority.
