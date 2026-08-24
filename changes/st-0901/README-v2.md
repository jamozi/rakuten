# ST-0901 V2: policy-bound recorded human review completion

This additive runtime completes the maximum-safe local implementation of the
ST-0901 review domain without changing PR1, PR2, or PR3. It binds one exact
ST-0805 policy evaluation report and process-local receipt to every V2 review
decision, records the decision immutably, and returns the canonical
`IN_PROGRESS -> COMPLETED` assignment transition with the exact decision
reference.

The V2 implementation profile is
`ST0901_REVIEW_COMPLETION_RECORDED_LOCAL_V2`. It runs only in `ENV_DEV` and
`CI` with generated recorded-synthetic input. It performs no network,
credential, provider, database, event-bus, public API, staging, release,
publication, or Production operation.

## Human decision boundary

The application service exposes only `execute(request)`. The actor is not a
caller argument. A recorded authorization source must return an exact
hash-bound `ACTIVE` `HUMAN` identity equal to the assignment's assignee. The
service re-evaluates the expected result before accepting the adapter result.
This is deterministic local self-consistency and is not real authentication,
durable authorization, or formal RBAC evidence.

`CHANGES_REQUESTED` and `REJECT` remain available through the earlier PR3 seam
and may also be completed through V2 when an exact policy report/receipt is
bound. V2 permits the review-level `APPROVE` token only if:

- all 75 checklist entries are exactly `PASS`;
- the ST-0805 report and receipt are valid, hash-equal, and bound to the same
  article-version UUID;
- evaluation status is `LOCAL_EVALUATED` with no evaluation Finding, legacy
  policy Finding, or waiver evaluation;
- threshold, floors, rules, zero-tolerance, quality gates, predecessors, and
  local eligibility are all explicitly clear; and
- every authority flag carried by the policy evidence remains false.

The installed checklist does not identify blocker/applicability metadata.
Therefore `NOT_APPLICABLE_WITH_REASON` remains fail-closed as
`CHECKLIST_APPLICABILITY_UNRESOLVED`; V2 does not invent a Canonical decision.

## No ST-0902 authority

The immutable value `ReviewDecisionKind.APPROVE` is a human review decision,
not the separate ST-0902 final approval. Every V2 result explicitly keeps
`final_approval_authorized`, `publication_snapshot_authorized`,
`publication_authorized`, `release_authorized`, and `production_authorized`
false. Formal TST-011/TST-012/TST-020, hosted CI, live validation, staging,
release, publication, and Production remain `NOT_EXECUTED`.

## Determinism and provenance

The owner contract generates a bounded JSON fixture, an importable byte
constant, and a content-addressed runtime manifest. The fixture binds the
exact ST-0805 fixture/report/Finding hashes and uses explicit UUIDv7 values,
timestamps, reviewer identity, audit event, and idempotency key. The adapter
stores only a SHA-256 of the raw key in results, returns byte-identical replay,
and refuses same-key changed requests before consuming another scripted step.

The local audit artifact is immutable and hash-binds actor, assignment,
article version, decision, policy/Finding snapshot, request, authorization,
and record. It is not a durable or atomic audit claim; persistence and formal
DB/API enforcement remain outside this local completion boundary.
