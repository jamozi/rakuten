# ST-0901 PR3: recorded-local negative review decisions

This PR adds only an internal pure/recorded ENV-DEV/CI seam for the safe
negative-decision subset of PUBADM-004. It builds on the merged PR1 review
workflow without modifying it, and follows the merged PR2 recorded-local
authorization/idempotency pattern without modifying or extending PR2's closed
PUBADM-001..003 types.

The implementation profile is exactly `ST0901_PR3_RECORDED_LOCAL_V1`. Every
artifact carrying that profile proves only deterministic self-consistency for
synthetic recorded input. It is not authentication, identity attestation, a
signature, canonical authorization policy, durable or atomic audit evidence,
formal Story acceptance, a public API response, or production readiness.
OD-005 remains unresolved.

## Authority and safe subset

| Authority or contract | PR3 behavior |
| --- | --- |
| ST-0901 / FR-009 | Records immutable human-review decisions only inside the local adapter. |
| PR1 `validate_review_decision` | Remains the structural oracle at request and returned-result boundaries. |
| PUBADM-004 | Uses implementation-local equality fixtures for operation `PUBADM-004`, permission/action `publishing:review:decide`, and audit action `review_decision_record`. No HTTP route or public contract is implemented. |
| ST-0403 | Reconstructs and detaches the complete exposed ALLOW/RULE_MATCH decision behind the exact existing `AuthorizationGrant`; this remains recorded self-consistency, not real authorization. |
| ST-0805 | Finding/local-eligibility provenance is optional and deliberately omitted. No Finding type, authority, translation, mutation, resolution, or waiver surface is added. |
| ST-0902 | Final approval, approval separation, publication eligibility, and blocking-Finding resolution remain outside this PR. |
| Physical review-decision contract | Preserves the append-only direction locally. Database enforcement, persistence, generated schema behavior, and transactions are not executed. |

Only `CHANGES_REQUESTED` and `REJECT` can produce a record. `APPROVE` always
retains PR1's `APPROVE_GATE_UNRESOLVED` failure. Any checklist
`NOT_APPLICABLE_WITH_REASON` retains PR1's
`CHECKLIST_APPLICABILITY_UNRESOLVED` failure. Those PR1 checks run before the
authorization source or exchange is called; raw, lowercase, ED-030, and other
PUBADM vocabulary is never translated.

The implementation does not complete or otherwise mutate the assignment.
Assignment ID, article version, review type, assigner, assignee, priority,
status, timestamps, lock version, and decision reference are detached,
hash-bound, and returned unchanged. A later assignment completion remains a
separate PUBADM-003 artifact boundary.

## Single recorded authorization path

`RecordedReviewDecisionAuthorizationV1` is a PR3-owned final value because
PR2's sealed record is intentionally closed to PUBADM-001..003. A module-private
permit and factory allow only the recorded adapter to construct it. The public
application service exposes only:

```text
execute(*, request)
```

There is no caller-supplied actor, reviewer, grant, authorization context,
Finding, completion, or approval argument. The authorization source is called
once before exchange. Its one immutable record binds all serialized local
fields, including:

- operation and request SHA-256;
- correlation and the exact opaque `AuthorizationTarget` coordinate;
- every exposed coordinate of the fully reconstructed ST-0403 decision/grant;
- implementation-local permission equality;
- one synthetic ACTIVE/HUMAN actor equal to the assignment assignee;
- assignment, article-version, assignment-snapshot, and decision-content
  coordinates; and
- the versioned local profile and authorization SHA-256.

The target is never interpreted as an assignment, article, or article-version
scope. PR3 does not infer a hierarchy, resource mapping, or canonical policy
binding from its kind, resource, or state fields.

## Immutable append history and supersession

`RecordedReviewDecisionV1` retains one detached structurally validated
negative decision, explicit UUIDv7 decision ID, explicit UTC decision time,
recorded actor, unchanged assignment digest, and optional prior binding.
Human summary, checklist comments, and evidence remain in the immutable PR1
decision value, while replay/audit/idempotency envelopes retain their digest
rather than raw human text.

`RecordedReviewDecisionHistoryV1` is an append-ordered tuple for one exact
assignment/article pair. Decision IDs are unique. When `supersedes_decision_id`
is present, it must identify an earlier retained record for that same pair and
the new record must bind that earlier record's exact canonical digest. A
missing, self/forward, duplicate, cross-assignment, cross-article, reordered,
removed, or byte-tampered prior fails closed.

Canonical authority does not define a tail, branch winner, latest decision, or
effective-decision algorithm. PR3 therefore does not infer one. A later record
may omit supersession, and multiple records may refer to the same earlier
record; they remain recorded facts only. There is no latest/effective/tail
query or mutation API.

The adapter retains exact step-construction bytes for the request,
authorization, prior history, and result. Before any index/history/replay state
change, it revalidates every nested value and full grant decision. Replay also
rebinds the current in-memory history and history bytes to the exact consumed
script prefix, so post-construction or retained-state tamper cannot replay.

## Deterministic local idempotency and artifacts

Idempotency is process-local and conservative. Its identity is the global
pair `(PUBADM-004, SHA256(Idempotency-Key))`; it is not actor-scoped because
the request intentionally has no trusted actor input. The raw key is never
retained in a result, audit artifact, canonical replay envelope, or failure.

- Same operation, key, exact request hash, and exact request return the same
  retained result object and byte-identical canonical result without advancing
  script or history state.
- Reusing the same operation/key with a changed request hash fails closed
  before later script/history consumption.
- A different synthetic actor cannot silently reuse a retained key.

Decision IDs, audit event IDs, decision/audit timestamps, and prior histories
are explicit script inputs. No runtime clock, UUID/random generator,
environment read, filesystem, network, database, event bus, audit service, or
publication call supplies them.

Each successful result returns only immutable local artifacts:

- the unchanged detached assignment;
- the new decision record;
- its append-ordered history snapshot;
- a local `review_decision_record` audit artifact binding actor, correlation,
  request, authorization, assignment/article, decision, and prior coordinates;
- a hash-only local idempotency receipt rebuilt by the application from the
  exact request key, request hash, and immutable output digest; and
- explicit `execution=RECORDED_ONLY` and `readiness=NOT_READY` status.

Authentication, identity attestation, persistence, database enforcement,
transaction, unit of work, durable idempotency, durable/atomic audit, assignment
or Finding mutation, approval, HTTP, events, outbox, delivery, formal
verification, live, staging, release, publication, and production status all
remain `NOT_EXECUTED`.

## Owned files

This PR owns exactly eleven new hand-maintained files:

```text
python/raos/domain/publishing/review_decision_operations.py
python/raos/ports/review_decision.py
python/raos/application/publishing/review_decision.py
python/raos/adapters/recorded_review_decision.py
tests/st0901_pr3/conftest.py
tests/st0901_pr3/test_pubadm004_record.py
tests/st0901_pr3/test_history_supersession.py
tests/st0901_pr3/test_authorization_idempotency.py
tests/st0901_pr3/test_boundaries.py
tests/st0901_pr3/test_failure_isolation.py
changes/st-0901/README_PR3.md
```

No PR1/PR2 source or test, package export, canonical/upstream/ZIP artifact,
contract, generated output, API route, schema, migration, database code, event,
manifest, status overlay, lockfile, workflow, or workspace-layout file is
changed.

## Local verification

Environment: WSL2 Linux linked worktree at
`/home/minami/rakuten/.worktrees/st-0901-pr3`, CPython 3.14.6, pytest 9.1.1,
Ruff 0.16.1, and mypy 2.3.0. The exact linked worktree is not hydrated by this
slice; Python checks use the repository-pinned environment at
`/home/minami/rakuten/.venv` with this worktree's `python` directory on
`PYTHONPATH`. Story suites run in separate pytest processes because repository
Story suites intentionally reuse module names.

Final local results:

| Check | Exact local result |
| --- | --- |
| isolated `tests/st0901_pr3` | PASS — 61 passed in 5.87s |
| independent read-only audit | PASS — no Critical/High/Medium/Low findings; auditor independently reproduced 61 passed in 5.94s |
| isolated PR1 `tests/st0901` | PASS — 87 passed in 0.15s |
| isolated PR2 `tests/st0901_pr2` | PASS — 58 passed in 0.18s |
| isolated predecessor `tests/st0403` | PASS — 37 passed in 0.06s |
| isolated predecessor `tests/st0805` | PASS — 361 passed in 1.02s |
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
  <exact four PR3 production files and six PR3 test files>
/home/minami/rakuten/.venv/bin/ruff format --check --no-cache \
  <same exact ten Python files>

MYPYPATH=python:tests/st0901_pr3 \
  /home/minami/rakuten/.venv/bin/mypy --strict \
  --explicit-package-bases --cache-dir=/dev/null \
  <same exact ten Python files>

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  /home/minami/rakuten/.venv/bin/python -m py_compile \
  <exact four PR3 production files>
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
`git archive HEAD`, overlaid only the exact eleven owned files, and ran the
unchanged scanner in deterministic fallback-walk mode. It exited 0 with no
findings or output; the temporary snapshot was moved to trash recoverably.

The read-only hydration probe found the contract repository input and local
validation resources but no worktree `.venv`, `.venv/bin/python`, or
`node_modules`. Per the approved boundary, `contract-gate` was not invoked,
nothing was installed or synchronized, and no contract result is claimed.

## Strict Pyright closure follow-up — 2026-08-15

The recorded adapter now uses the explicit non-underscored
`build_recorded_review_decision_authorization` domain bridge instead of a
private cross-module name. The bridge and constructor permit remain excluded
from `__all__`; neither is a consumer API or a second application trust path.
The bridge only rebuilds one fully revalidated, immutable
`ST0901_PR3_RECORDED_LOCAL_V1` self-consistency record. The application keeps
its sole `execute(request=...)` trust path and accepts no caller-provided
authorization, actor, grant, Finding, completion, or approval value.

Identity serialization stays in the same revalidating module-private,
fresh-mapping boundary as PR2, with no public payload method. A scripted step
now exposes only getter-only views of its retained authorization digest,
immutable result, and immutable prior-history/result bytes; it exposes no
setter or mutable payload. The test fixture consumes the result accessor, and
hostile tests reject writes to every accessor while retaining bridge and
permit exclusion plus direct-constructor, subclass, and tamper refusals.
Canonical serialization and hash bytes, history/replay binding, validation and
error precedence, append ordering, immutability, and approval semantics remain
unchanged. The isolated PR3 suite remained 61 passed.

Formal TST-011, TST-012, TST-020, TST-021, and TST-022 remain
`NOT_EXECUTED`. Full PUBADM-004 HTTP/public response mapping (including
`display_id`, `created_at`, and decision-artifact mapping), real identity and
authorization, database append-only enforcement, persistence, durable
idempotency, durable/atomic audit, events/outbox/delivery, live human review,
ST-0902 approval, assignment completion, publication eligibility, staging,
release, publication, and production remain `NOT_EXECUTED`. No local result
grants approval, publication, release, or production authority.
