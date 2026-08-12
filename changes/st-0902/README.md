# ST-0902 final-approval reference plan

This slice installs a deterministic, source-derived reference plan for the
approved ST-0902 Final approval Story. It pins and projects the exact Story,
FR-009 trace variants, PUBADM-005/PUBADM-006 shapes, Approval API/DB/event
constraints, the current database guard, and the relevant predecessor bounds.

It is deliberately non-executable. It is not an approval command, rejection
command, revocation command, API handler, database repository, policy engine,
authorization rule, audit writer, event producer, publication gate, or runtime
reader. Story acceptance remains false and readiness remains `NOT_READY`.

## Design-assistance boundary

No captured proposal or response content is used. The tracked artifacts retain
only `PRO_UNAVAILABLE`, authority `NONE`, `proposal_captured: false`, and
`content_used: false`. They contain no private execution identity or transport
detail and derive no design authority from the unavailable assistance.

## Exact authority projection

- ST-0902 requires an approval command binding all gates/hashes, self-approval
  separation, and rejection on blocking Findings. This plan implements none of
  those outcomes.
- The Story names TST-012/TST-021. Master FR-009 traceability additionally
  names TST-011/TST-020, while acceptance traceability additionally names
  TST-022. The divergence is preserved and not resolved.
- PUBADM-005 and PUBADM-006 are projected as contract text only, including
  scope, idempotency, response, and audit-action metadata. No request is
  accepted and no result is returned.
- The API admits `APPROVED` and `REJECTED`; the database also admits `REVOKED`
  and the `FACT` approval type. Those vocabularies are descriptive and create
  no authority here.
- The current physical guard applies only to `FINAL` plus `APPROVED`, and its
  other-decision branch returns the row unchanged. This plan records that fact
  without using it as authorization for a rejection write.
- The granted/revoked event schemas are projected without producing an event.
  There is no installed rejected-event contract, and the installed events do
  not bind the complete actor/gate/hash decision context.

## Hard-gate boundary

The plan keeps these concerns separate and unresolved: active-human identity,
role/resource scope, MFA, the step-up conflict and freshness, separation of
duties and the self/solo comparator, effective ST-0901 decisions, the
pre-approval checklist/gate/hash manifest, Finding/waiver truth, authoritative
quality/source/policy/freshness evidence, transactional idempotency/audit/unit
of work/outbox behavior, and approval/revocation/supersession/effectiveness/
publication lifecycle.

The safe default is no executable approval or rejection authority. A positive
or negative executable slice requires its own owner-approved
`DESIGN_HANDOFF_V1`; this reference plan cannot serve as that handoff.

## Empty-record semantics

Approval commands, requests, results, and records are empty and
`NOT_EXECUTED`/`NOT_EVALUATED`. The same is true for rejection, revocation,
events, audits, and idempotency. An empty rejection list means
`NO_COMMAND_OR_EVIDENCE_NOT_ZERO_REJECTED`; it never proves that zero requests
were rejected. Both `APPROVED` and `REJECTED` authority are absent.

No runtime filesystem reader, network, ambient clock, database, API, job,
event, audit, idempotency, approval, rejection, revocation, publication, or
external action is implemented. ST-0605 remains non-executable, ST-0805 remains
non-authoritative for publication, and ST-0901 supplies no effective positive
decision.

## Generation and verification boundary

Generated files are owned only by:

```text
uv run --locked --no-sync python scripts/build_st0902_final_approval_reference_plan.py
uv run --locked --no-sync python scripts/build_st0902_final_approval_reference_plan.py --check
```

Focused tests validate exact source hashes and semantics, deterministic output,
strict schema/path/symlink handling, sanitized failures, and the closed
authority boundary. They are local reference-plan checks only. Formal TST-011,
TST-012, TST-020, TST-021, TST-022, live, staging, release, publication, and
production work remain `NOT_EXECUTED`.

## Local evidence environment and limitations

- The dedicated worktree has no hydrated `.venv`. The exact pinned
  `/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run --locked --no-sync
  python scripts/build_st0902_final_approval_reference_plan.py --check`
  attempt created only an empty environment and then failed with
  `ModuleNotFoundError: No module named 'yaml'`. That empty environment was
  removed; no install, sync, or network access was performed.
- Ambient `/snap/bin/uv` reports `uv 0.12.3`, which does not satisfy the pinned
  `uv 0.12.1` contract and was not used as verification evidence.
- Local generation and focused checks instead used the already hydrated owner
  checkout interpreter at `/home/minami/rakuten/.venv/bin/python`, with the
  dedicated worktree as both the current directory and `PYTHONPATH`. This is
  local implementation evidence only; it is not a pinned-worktree
  `contract-gate`, formal TST, CI, live, staging, release, publication, or
  production result.
