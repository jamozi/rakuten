# ST-0308 corrected-handoff canonical reconciliation

Status: `MATERIAL_CONFLICT_REQUIRES_REAPPROVAL`

Authority: `INFORMATIONAL_RECONCILIATION_EVIDENCE_ONLY`

Observed at: `2026-08-05T05:30:41Z`

This append-only record evaluates the exact repository-owner-approved handoff
at `/mnt/c/Users/naoki/Downloads/DESIGN_HANDOFF_V1.yaml`. It does not modify
or supersede the approved bytes, does not resolve a design decision, and does
not itself authorize implementation.

## Input and approval identity

- Exact handoff SHA-256:
  `33a9078095bfa7fd0f2517eba4ee941b9c9584222692e1069d35252a2b04a510`
- Exact owner-approval statement SHA-256:
  `7e47c77d220418b935e618c4f10ec6b54ccd20aa74cb6af897043fcf0868aeb5`
- YAML parse and mandatory-field validation: `PASS`
- `open_decisions`: `[]`
- Path-bound handoff SHA-256 checks: `34/34 PASS`
- Inventory: `103 tables + 1 view`, normalized SHA-256
  `0d674dd248c2d4aa3717b2e881dba2e67e506557eb473899d3df59192080a7ee`
- Owner approval is recognized for these exact bytes. Activation nevertheless
  fails because the handoff's second condition requires conflict-free canonical
  reconciliation.

## Independent audit routing

The final read-only audit was executed in a new `gpt-5.6-luna` process with
reasoning effort `max`. Hooks, plugins, apps, browser/computer use, and
multi-agent operation were explicitly disabled; repository MCP transports were
disabled; the sandbox was read-only. No port-37700 listener or related worker
was present before, during, or after the audit.

- Luna final-output SHA-256:
  `ab842e0e93acfb5a85a9ee711e141e9bb22b78eebcf447d1a5500e235c3d51cb`
- Luna event-log SHA-256:
  `6aa5361b2bae3b9aa457d62906def0341982bc8693425caeec25a2a65986913c`
- Luna verdict: `BLOCK`
- Separate D1/D3 audit: `PASS`
- Separate D2/D4/D5 audit: `BLOCK`

These are local design-authority audits, not TST-005, TST-008, CI, human code
review, staging, or production evidence.

## Reconciliation result

| Area | Result | Finding |
|---|---|---|
| D1 inventory and ownership | `PASS` | The 103-table/one-view inventory, eight excluded advisory-only OPS relations, twenty current-only overlay relations, and object hashes match current pinned bytes. |
| D2 concurrency | `FAIL_MATERIAL` | Eight physical AI relations with `lock_version` are omitted from `LOCK_VERSION_CAS`; four are expressly placed in `STATE_CAS_WITHOUT_LOCK_VERSION`. This conflicts with the physical contract and AC-14. |
| D2 Domain Ports | `FAIL_INCOMPLETE` | Repository signatures name Domain aggregates and values that do not exist and whose fields, invariants, ownership, and mapper targets are not specified. Multiple incompatible Domain models remain possible. |
| D3 generation | `PASS` | Source hashes, physical fragments, catalog digests, generator authority, and two-way parity dimensions reconcile. Actual ST-0308 generation remains unexecuted. |
| D4 lifecycle | `PASS_CONCEPTUALLY` | One synchronous Session, outer-only commit, rollback, no savepoints, and retry ownership are coherent. |
| D4 public UoW contract | `FAIL_INCOMPLETE` | `ModuleUnitOfWork` and `JoinedModuleUnitOfWork` are return annotations without exact Protocol methods or per-module property surfaces. |
| D5 shared infrastructure | `FAIL_CONTRADICTORY` | Audit, Outbox, and Idempotency Protocols are OPS-owned while every module UoW must expose them and cross-module Repository imports/table operations are forbidden. |
| D5 idempotency | `FAIL_INCOMPLETE` | Completion requires ID/status/request-hash CAS, but the exact method signatures provide no expected hash or claim capability. Expired replacement reuses the same ID, so reading the current hash is unsafe. |
| D5 Outbox versions | `FAIL_INCOMPLETE` | Canonical events require aggregate version, but no authoritative version source is selected for event-producing state-CAS roots without a persisted version, including `policy.finding`. |
| D5 state predicates | `FAIL_INCOMPLETE` | Waiver transitions refer to "relevant existing timestamps" while AC-16 claims exact predicates. |
| D5 expired claim SQL | `NEEDS_EXACT_MECHANISM` | With savepoints forbidden, a plain uniqueness exception cannot be followed by `SELECT FOR UPDATE` in the same PostgreSQL transaction. A non-aborting `ON CONFLICT ... DO NOTHING RETURNING` path or another exact mechanism must be selected. |
| D6 identity boundary | `PASS_CONDITIONAL` | The injected-provider and role/identity boundaries reconcile; ST-0306 remains candidate evidence and not an ST-0308 dependency. |

## Exact lock-version conflict

The current ST-0304 physical contract contains `lock_version` on all of these
relations, but the handoff does not classify all of them under
`LOCK_VERSION_CAS`:

```text
ai.ai_job
ai.evaluation_dataset_version
ai.evaluation_run
ai.evaluation_suite
ai.judge_calibration
ai.model_route_version
ai.prompt_version
ai.release_decision
```

The current handoff additionally states that `ai.ai_job`, `ai.evaluation_run`,
`ai.judge_calibration`, and `ai.release_decision` have no lock version. That is
a direct contradiction of the hash-pinned physical inputs rather than ordinary
implementation discretion.

## Activation result

The repository owner approved the exact input, but canonical reconciliation is
not conflict-free. Therefore:

```text
canonical_reconciliation: MATERIAL_CONFLICT_REQUIRES_REAPPROVAL
implementation_authority: BLOCKED
luna_implementation_started: false
```

A complete replacement `DESIGN_HANDOFF_V1` must resolve every material finding
above, retain all mandatory fields with `open_decisions: []`, and receive a new
exact repository-owner approval before implementation may be delegated to Luna
max.
