# ST-1506 Production deployment reference boundary

This Story-owned slice records the maximum-safe local reference for a future
Production deployment. It is a closed, source-derived, non-executable
definition and reference plan. It creates no workflow, Terraform/HCL,
infrastructure, repository binding, credential, migration task, deployment,
traffic change, canary, smoke request, rollback, release, status change, or
other external state.

## Status boundary

- Canonical design: `APPROVED_FOR_IMPLEMENTATION`
- Local deliverable: `INTERFACE_ONLY_PARTIAL_LOCAL_CODE`
- Environment label: inert canonical `PRODUCTION`; configuration remains
  `NOT_CONFIGURED`
- Activation: `DISABLED`
- Runtime, live, and formal TST-032 verification: `NOT_EXECUTED`
- Every create/update/delete/promote/deploy/migrate/traffic/canary/rollback/
  release/status action count: exact integer `0`
- Effective canonical implementation/verification status: unchanged
- Provider admission: `NOT_EVALUATED`; eligible `false`
- Selected, default, and fallback Production profiles: all unset

This local reference does not make ST-1506 Story Done, `VALIDATED`, deployed,
release-ready, or Production-ready.

## Provider-neutral Production admission

Full RAOS Production admission does not require AWS or any other named
infrastructure provider. The direct-owner
`DESIGN_HANDOFF_V1_ST1506_PROVIDER_NEUTRAL_PRODUCTION.yaml` is hash-pinned as
an authority input and defines a strict capability contract. A future profile
may identify AWS, another cloud, or owner-managed infrastructure only after it
maps exactly one implementation to every required capability and supplies the
same security, operations, release, backup/restore, and residency evidence.

The closed required capability inventory covers:

- portable web, API, worker, and scheduler workload runtime;
- PostgreSQL-compatible relational persistence and migration controls;
- S3-compatible versioned and immutable object storage where an owning data
  contract requires it;
- at-least-once queue delivery, DLQ behavior, and idempotent consumers;
- public edge DNS, TLS, WAF, and public/admin/internal isolation;
- least-privilege workload identity and auditable secret delivery;
- telemetry, release markers, alerts, and notification routing;
- backup, restore, PITR/snapshot, and integrity drill evidence;
- immutable promotion, migration, canary, observation, rollback, and human
  release controls; and
- explicit primary/backup location and data-residency evidence.

Missing, unknown, duplicate, implicit, partial, or provider-label-only
mappings fail closed. No profile is currently selected or eligible. This slice
defines provider-neutral admission; it does not implement a non-AWS deployment
profile or make the full deployment chain runnable.

INT-DEC-007's AWS Tokyo record and `ap-northeast-1` remain visible only as
optional historical reference metadata. They are never a default, implicit
fallback, selected binding, admission prerequisite, eligibility shortcut, or
evidence substitute.

## Predecessor boundary

The owner builder byte-binds and semantically validates both the ST-1505
source contract and its generated reference plan. It also requires every exact
ST-1505 transitive predecessor binding for ST-1502, ST-1503, and ST-1504 in
the original order. Rebinding a digest cannot make semantic drift acceptable.

ST-1505 and its AWS-specific predecessors remain immutable history/reference.
They must remain non-executable and disabled, with all
selected values unset, provider calls and external actions forbidden, every
action count exactly zero, and formal TST-009/TST-022 unexecuted. These local
artifacts supply requirements to bind; they supply no infrastructure,
identity, staging, Production, deployment, or release authority.

Their AWS service labels do not become mandatory ST-1506 provider semantics
and cannot satisfy capability admission or evidence. Replacing those
predecessor implementations with a concrete alternate profile is later,
separately owned work.

## Open-decision safe defaults

ST-1506 does not resolve OD-009, OD-011, OD-013, or OD-015 and selects no
business or live value:

- OD-009: Production remains disabled; no budget or acceptable-loss value is
  selected.
- OD-011: notification is local logging only; no channel or escalation contact
  is selected and Production notification is unavailable.
- OD-013: `ap-northeast-1` is reference metadata only, never an apply target;
  no Production or backup region is selected.
- OD-015: recorded fixtures only; no live provider account, permission,
  credential, or secret exists.

## Human-controlled gates

Four distinct future immutable human-controlled artifacts are required:
`release_decision`, `gate_report`, `security_approval`, and
`operations_approval`. All four slots remain unpopulated. An automated result,
self-approval, synthesized or forged approval, shared artifact, bypass, or
override cannot satisfy any gate.

Every actual repository, ref, workflow, role, credential, artifact, endpoint,
reviewer, migration, canary, traffic, smoke, rollback, notification, and
Production value remains null or empty. Immutable artifact digest, SBOM,
provenance, protected-environment binding, exact repository/ref/workflow,
telemetry, error budget, alerts, migration compatibility, and rollback
readiness are `REQUIRED_NOT_CONFIGURED`.

## Logical phases and execution boundary

`CANARY`, `OBSERVE`, and `ROLLBACK` are logical requirement records only.
Every phase is disabled, `NOT_EXECUTED`, externally forbidden, and has an exact
zero action count. Auto-advance is forbidden. The reference cannot call
GitHub, AWS or another infrastructure provider, IAM or another identity
system, a network, a credential store, a deployment or release system, or any
other external service.

## Owned source and generated artifacts

Do not hand-edit generated artifacts. Change the contract or builder and run
the owner command.

| Classification | Path | Role |
| --- | --- | --- |
| Story decision source | `changes/st-1506/DESIGN_HANDOFF_V1_ST1506_PROVIDER_NEUTRAL_PRODUCTION.yaml` | Direct-owner durable decision defining provider-neutral capability admission while preserving unresolved external decisions |
| Story source | `changes/st-1506/contracts/production-deployment-definition.v1.yaml` | Closed Production safety, approval, admission, canary, observation, rollback, and disabled-execution requirements |
| Owner builder | `scripts/build_st1506_production_deployment.py` | Strict deterministic validator and renderer |
| Test source | `tests/st1506/*.py` | Positive, hostile, provenance, path-safety, no-write, and static-boundary coverage |
| Generated reference | `infra/terraform/deployment-production/production-deployment.reference-plan.v1.json` | Source-derived non-executable reference plan |
| Generated inventory | `changes/st-1506/manifest.yaml` | Exact authority, predecessor, source, output, and boundary hashes |

Generate both declared outputs:

```bash
uv run --locked --no-sync python scripts/build_st1506_production_deployment.py
```

Verify source pins and committed output bytes without writing:

```bash
uv run --locked --no-sync python scripts/build_st1506_production_deployment.py --check
```

The CLI accepts only optional exact `--check`. The builder reads no ambient
environment or credential, imports no provider, browser, network, process, or
deployment SDK, invokes no subprocess or native tool, and performs no external
write.

## Explicitly unexecuted work

Formal TST-009, TST-022, and TST-032; hosted CI; staging; a migration database;
HTTP or browser smoke; telemetry and alert configuration; canary traffic;
rollback exercise; provider/account/role/credential use; GitHub environment or
workflow configuration; Production deployment; release; and status transition
remain `NOT_EXECUTED`. Each requires its separately authorized owner,
environment, immutable evidence, approvals, and resolved decisions.
