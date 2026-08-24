# ST-1403 — deterministic refresh proposal and impact boundary

Local classification:
`RECORDED_SYNTHETIC_REFRESH_PROPOSAL_V2`.

This Story provides a deterministic, immutable refresh-proposal boundary for
`FR-016`. It turns exact freshness and editorial-policy evidence plus an
ordered set of content diffs into an impact assessment, action candidates,
and the exact reapproval scope. It cannot execute an action, persist a record,
publish, delete content, reorder a recommendation, or promote local evidence
to formal evidence.

## Canonical scope and dependency binding

The implementation preserves the Canonical freshness and editorial rules:

- price, availability, and link projections do not manufacture an article
  version;
- body, recommendation, comparison-axis, methodology, product-set, and major
  specification changes require article-version, editorial-review, and
  publication-snapshot reapproval;
- a recommendation-rank change additionally requires explicit
  `RECOMMENDATION_ORDER` approval;
- every candidate remains a proposal with `can_change_state=false`.

The application binds complete current dependency values, not caller-asserted
digests:

1. The ST-1401 `FreshnessEvaluationRequest` is rerun through
   `evaluate_freshness`; the complete result must match. Its inherited
   `OD-007` state remains `HUMAN_DECISION_REQUIRED`, policy activation remains
   `DISABLED_UNRESOLVED_OD_007`, recommendation ordering is `FORBIDDEN`,
   persistence is `NOT_EXECUTED`, attestation is `NOT_ATTESTED`, and live
   eligibility is false.
2. The current ST-0805 V2 `PolicyEvaluationEnvelopeV2` is rerun through
   `evaluate_editorial_policy_v2`; the complete canonical report bytes must
   match. The exact ST-0802 draft AST, ST-0605 coverage receipt, ST-0804
   recommendation receipt, evaluator profile, findings, waivers, gates, and
   authority fields therefore remain in the owner chain. Only a finding-free
   `LOCAL_EVALUATED` result is accepted. Approval, waiver apply, merge,
   recommendation/ranking override, publication, activation, and Production
   authority all remain false; formal, live, staging, release, publication,
   and Production statuses remain `NOT_EXECUTED`.

The candidate article-version identifier must equal the policy report's exact
canonical UUIDv7 article-version identifier. Result-only or legacy V1 evidence,
self-consistent substituted digests, mismatched requests/results, malformed
values, ineligible policy results, and authority escalation all fail before
the proposal port is called.

## Diff, impact, and priority model

Each diff contains only closed identifiers, before/after SHA-256 bindings,
affected Claim identifiers, and closed classifications. Raw Fact values,
article text, prompts, URLs, credentials, review bodies, affiliate rates,
commission, revenue, and profit inputs are absent.

The closed diff kinds are `ADDED`, `REMOVED`, `CHANGED`, `BECAME_STALE`, and
`RESOLVED_CONFLICT`. The action-candidate labels are `CREATE`, `UPDATE`,
`MERGE`, and `DELETE`; `DELETE` is only an unapproved label and exposes no
delete operation. A changed/resolved record binds different bytes, while a
stale transition may bind unchanged bytes because age can change freshness.

The caller supplies impact classifications and an exact contiguous priority
rank. The implementation validates and preserves them; it does not score,
sort, infer business priority, inspect analytics, use AI, or resolve ties.
Each output owns immutable snapshots and a deterministic fingerprint. Every
action candidate remains `PROPOSED`, `UNAPPROVED_PROPOSAL`,
`HUMAN_APPROVAL_REQUIRED`, `can_change_state=false`, and `NOT_EXECUTED`.

The ST-1401 recommendation-basis review marker and ST-1403 recommendation
surface must agree. A recommendation rank-change flag without the
recommendation surface is invalid. A projection-only change may reuse prior
article approval, but that does not approve or execute its action candidate or
authorize a public projection write.

## Runtime and generated-record boundary

The runtime surface is limited to `ENV-DEV` and `CI`. Integration, staging,
recovery, and Production construction fail closed. The port exposes only
`propose`. A collaborator is called once with an immutable snapshot and must
return the exact locally rebuilt proposal. Exceptions, mutation, unknown
requests, duplicate request bindings, and different-but-shape-valid proposals
fail with redacted closed errors.

Two local test seams are retained:

- immutable in-memory fixtures for historical focused coverage; and
- owner-generated request/proposal fingerprint bindings for the current V2
  recorded fixture.

The recorded loader accepts only bounded UTF-8 JSON with exact fields, exact
classification/time/environment, complete dependency SHA-256 bindings,
proposal-only authority, and all formal/external statuses `NOT_EXECUTED`.
Duplicate keys, BOM, non-finite constants, unknown fields, numeric/string
coercion, duplicate bindings, authority escalation, and malformed hashes fail
closed. Values are redacted and non-pickleable.

The deterministic owner generator reads the versioned contract, verifies all
13 current Canonical/dependency source hashes, loads and reevaluates the exact
ST-0805 V2 recorded fixture, reruns ST-1401, and atomically writes:

- `generated/refresh-proposal-recorded.v2.json`; and
- `runtime-manifest.v2.json`.

The generated record stores only fingerprints, dependency bindings, closed
authority fields, and `NOT_EXECUTED` statuses. It contains no raw article,
Fact, review, prompt, credential, finance, or publication payload. The shared
secure publication helper provides foreign-preserving, no-clobber generated
file replacement; `--check` is no-write and detects drift.

## Owned files and checks

Owned implementation and evidence:

- `python/raos/domain/freshness/refresh_proposal.py`
- `python/raos/application/freshness/refresh_proposal.py`
- `python/raos/ports/refresh_proposal.py`
- `python/raos/adapters/recorded_refresh_proposal.py`
- `scripts/build_st1403_refresh_proposal_runtime.py`
- `tests/st1403/`
- `changes/st-1403/`
- `docs/execplans/ST-1403.md`
- `docs/worklogs/ST-1403.md`

Generate or verify the recorded artifacts:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  .venv/bin/python scripts/build_st1403_refresh_proposal_runtime.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  .venv/bin/python scripts/build_st1403_refresh_proposal_runtime.py --check
```

Run Story and dependency suites in separate pytest processes because the
historical suites use directory-local top-level `conftest` modules:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. .venv/bin/pytest -q tests/st1403
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. .venv/bin/pytest -q tests/st1401
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. .venv/bin/pytest -q tests/st0805_runtime
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. .venv/bin/pytest -q tests/st0805
```

## Completion boundary

The local status may be recorded only as `LOCAL_IMPLEMENTATION_COMPLETE`.
Canonical implementation/verification status is unchanged. Formal TST-020 and
TST-021, hosted CI, real Content AST/publication-snapshot E2E behavior,
persistence, database, queue, API, human review UI/workflow, renderer/public
projection effects, live/provider inputs, publication, staging, release, and
Production remain `NOT_EXECUTED`.

No new Open Decision was created or resolved. `OD-007` remains a Canonical
human decision and disabled safe-default boundary. Nothing in this Story is
formal validation, publication approval, release approval, runtime
attestation, or Production readiness.

`PRO_NOT_INVOKED`: the selected Canonical Story, current dependency contracts,
and existing repository patterns fully determined this reversible local
implementation; no external advisory workflow was needed.
