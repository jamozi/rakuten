# ST-1403 — immutable refresh proposal and impact boundary

Classification:
`PURE_DETERMINISTIC_RECORDED_DEV_CI_UNAPPROVED_REFRESH_PROPOSAL`.

This Story implements a local, immutable proposal boundary for deterministic
freshness diffs, impact assessment, caller-ranked action candidates, and the
exact article reapproval scope. It does not execute an action, mutate state,
publish, reorder recommendations, persist a record, or promote local evidence
to formal TST-020/TST-021 evidence.

## Canonical and predecessor binding

The implementation follows the approved ST-1403 Story (`FR-016`, deliverables
`proposal` and `impact`, acceptance `rank change requires approval`) and the
Canonical content freshness rules:

- dynamic price, availability, and link projections can be refreshed without
  manufacturing a new article version;
- article body, recommendation, comparison-axis, methodology, product-set, or
  major-specification changes require a new article version, editorial review,
  and a new publication snapshot;
- no stale or changed recommendation basis can silently reorder a
  recommendation;
- a proposal has `can_change_state=false` and cannot mutate publication.

The application requires the complete ST-0805 `PolicyEvaluationInput` together
with its exact eligible local result. It deterministically reruns the ST-0805
owner evaluator and compares the complete result, including canonical compact
JSON bytes, SHA-256 digest, all request-derived internal coordinates, and
non-authority fields. A self-consistent result-only JSON/digest pair is not an
evidence binding. A request/result mismatch, policy-ineligible result, or
malformed result fails before the proposal port is called. This does not turn
ST-0805 local eligibility into publication approval: the policy result still has
`publication_authorized=false`, `production_eligible=false`, and every
formal/live/staging/release/Production status `NOT_EXECUTED`.

The application separately requires the complete ST-1401
`FreshnessEvaluationRequest`, reruns `evaluate_freshness`, and accepts only the
complete matching result. This binds the derived request fingerprint, state,
age, projection action, review action, and all safe-default authority fields;
an arbitrary request fingerprint or impossible state/age pair fails closed.
Its policy binding remains
`PROVISIONAL_CANONICAL_SAFE_DEFAULT` /
`DISABLED_UNRESOLVED_OD_007`; `OD-007` remains
`HUMAN_DECISION_REQUIRED`, inactive, and unresolved. Recommendation ordering
remains `FORBIDDEN`, persistence remains `NOT_EXECUTED`, attestation remains
`NOT_ATTESTED`, and live eligibility remains false. ST-1403 does not add an
SLA, category/provider override, policy activation, or freshness threshold.

## Deterministic diff and impact model

Each diff contains only closed identifiers, before/after SHA-256 bindings,
affected Claim identifiers, and closed classifications. Raw Fact values,
article text, review bodies, prompts, URLs, credentials, affiliate rates,
commission, revenue, and profit inputs are absent.

The closed diff kinds match the installed refresh-diff task vocabulary:
`ADDED`, `REMOVED`, `CHANGED`, `BECAME_STALE`, and `RESOLVED_CONFLICT`.
Impact coordinates retain the installed freshness vocabulary for change type,
changed entity type, impact level, and required action. A stale transition may
bind equal fact bytes because age alone can change freshness; a `CHANGED` or
`RESOLVED_CONFLICT` record must bind different before/after bytes.

Impact classification is caller-supplied deterministic input. Each candidate
and returned proposal owns newly constructed immutable diff snapshots, so later
caller mutation cannot change a proposal or its fingerprint. The builder does
not invent facts, infer a business priority, read analytics, call AI, or change
an impact level. It projects each diff to an immutable impact assessment and
produces a closed union of overall impact and required actions.

## Priority and action-candidate boundary

The four FR-016 action types in this seam are `CREATE`, `UPDATE`, `MERGE`, and
`DELETE`. `DELETE` is only an unapproved action-candidate label; it cannot
delete an article, database row, artifact, snapshot, or public route.

The caller supplies an exact contiguous deterministic rank from 1 through the
number of diffs, and supplies diffs in that same order. The implementation
preserves the order and rank byte-for-byte. It does not score, sort, break
ties, explain, override, or reprioritize. Every returned action candidate is
`PROPOSED`, `UNAPPROVED_PROPOSAL`, `HUMAN_APPROVAL_REQUIRED`,
`can_change_state=false`, and `NOT_EXECUTED`.

The 1,000-diff and 1,000-recorded-fixture bounds, uppercase closed reference
grammar, sorted unique Claim references, and closed surface ordering are
reversible local validation details following the nearest existing
recorded-domain pattern. They are not business cadence, ranking, retention, or
publication policy.

## Reapproval and rank-change boundary

For any substantive content surface, the output names the exact required
scope: `ARTICLE_VERSION`, `EDITORIAL_REVIEW`, and `PUBLICATION_SNAPSHOT`.
A recommendation rank change additionally and unconditionally includes
`RECOMMENDATION_ORDER`. A rank-change flag without a recommendation surface is
invalid.

The ST-1401 recommendation-basis review marker and the ST-1403 recommendation
impact surface must agree exactly. A review marker paired with a projection-only
diff cannot erase article reapproval, and a recommendation diff cannot omit the
matching predecessor review marker. This consistency check does not infer,
score, or change a caller-supplied recommendation rank.

Every proposal and action candidate requires human approval. In particular,
rank change always returns `HUMAN_APPROVAL_REQUIRED`; automatic reordering is
always false and the inherited recommendation-order action is always
`FORBIDDEN`. No proposal includes an approval command, decision endpoint,
publisher, renderer, snapshot writer, or state-transition capability.

A projection-only diff may state that prior *article* approval is reusable and
have an empty article reapproval area. This does not approve or execute its
action candidate, authorize a public projection update, or waive the proposal's
human-decision requirement.

## Trust and execution boundary

- The inward port exposes only `propose`.
- Application and recorded adapter construction accept exactly `ENV-DEV` or
  `ENV-CI`; Integration, staging, recovery, and Production fail closed.
- Recorded fixtures bind one exact request fingerprint to one exact
  deterministic proposal fingerprint. Duplicate or unbound requests fail
  closed.
- The collaborator is called once. It receives a defensive immutable request
  snapshot, cannot change the expected result, and cannot return a merely
  shape-valid different proposal.
- Collaborator exceptions and rejected material are replaced by closed failure
  codes. Values and fixtures are redacted and non-pickleable.
- The slice reads no clock, environment, filesystem, database, queue, provider,
  network, generated contract runtime, or external service.

The implementation adds no schema, generated output, migration, repository,
API, job, event, AI route, provider adapter, persistence, publication surface,
release workflow, or Production capability.

## Owned files and local checks

Owned implementation files:

- `python/raos/domain/freshness/refresh_proposal.py`
- `python/raos/application/freshness/refresh_proposal.py`
- `python/raos/ports/refresh_proposal.py`
- `python/raos/adapters/recorded_refresh_proposal.py`
- `tests/st1403/`
- `changes/st-1403/README.md`

Run Story and dependency suites in separate pytest processes:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  /home/minami/rakuten/.venv/bin/pytest -q tests/st1403
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  /home/minami/rakuten/.venv/bin/pytest -q tests/st1401
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  /home/minami/rakuten/.venv/bin/pytest -q tests/st0805
```

Static checks use the pinned repository environment and exact owned Python
paths:

```bash
/home/minami/rakuten/.venv/bin/ruff check <owned Python paths>
/home/minami/rakuten/.venv/bin/ruff format --check <owned Python paths>
MYPYPATH=python /home/minami/rakuten/.venv/bin/mypy --strict \
  <owned production Python paths>
PYTHONPYCACHEPREFIX=<private temporary directory> \
  /home/minami/rakuten/.venv/bin/python -m py_compile \
  <owned production Python paths>
```

## Remaining unexecuted work

Formal/hosted TST-020 and TST-021, real Content AST and publication-snapshot
E2E coverage, policy detectors, live/provider inputs, persistence, database,
queue, API, human review UI/workflow, renderer and public projection effects,
publication, staging, release, and Production all remain `NOT_EXECUTED`.
Nothing in this Story is formal validation, runtime attestation, publication
approval, release approval, or Production readiness.

`PRO_NOT_INVOKED`: implementation followed approved Canonical decisions and
existing repository patterns; no new design, policy, security, migration,
irreversible, external-cost, or Open Decision value was created.
