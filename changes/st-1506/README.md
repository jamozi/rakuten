# ST-1506 Production deployment and WordPress signed-delivery boundary

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

This local reference does not make ST-1506 Story Done, `VALIDATED`, deployed,
release-ready, or Production-ready.

## Exact implementation authority

This additive `1.1.0` revision is authorized only by the immutable handoff and
detached repository-owner approval below. The builder verifies their exact
regular-file bytes, sizes, SHA-256 values, parsed semantics, approved Story,
base literals, owned path cut, and empty implementation `open_decisions` before
accepting the source contract.

| Authority input | Bytes | SHA-256 |
| --- | ---: | --- |
| `changes/st-1506/DESIGN_HANDOFF_V1_ST1506_WORDPRESS_SIGNED_DELIVERY_INTERFACE_V1.yaml` | 30,568 | `7973f7d4dca452da3325ecbfbd78d34faf6acdcd7d931de6d314ee2ef4a1acb3` |
| `changes/st-1506/DESIGN-HANDOFF-APPROVAL-WORDPRESS-SIGNED-DELIVERY-INTERFACE-v1.yaml` | 2,298 | `89a8d77ca319a51d38bf7662c4d7a38763b13f66e5a33176ecaf93e598fd25bb` |

The handoff's proposal-era embedded status remains byte-immutable. The
detached approval binds those exact bytes to
`APPROVED_FOR_IMPLEMENTATION` for this one non-executable ST-1506 slice. It
does not approve a later runtime or release.

## WordPress signed-delivery interface

`wordpress_signed_delivery_interface` is a closed, generated-projection data
interface. It records only future requirements for:

- manual owner-gated bootstrap with an offline Ed25519 root that signs only a
  versioned keyring;
- two distinct active release-signing purposes over one RFC 8785 canonical
  release-set envelope;
- atomic coupled child-theme/companion-plugin release sets, strict package
  admission, exact inventory, and archive traversal/collision rejection;
- monotonic keyring and release high-water marks, durable pre-mutation journal,
  stopped ambiguity states, and no blind retry;
- same-filesystem staging requirements without assuming WordPress filesystem
  atomicity;
- bounded health verification and at most one restore from the immediately
  previous locally verified release set;
- separate least-privilege WordPress update/content identities, sanitized
  tamper-evident receipts, and separate deployment/publication control planes.

The interface is `executable: false`, `DISABLED`, `NOT_CONFIGURED`, and
`NOT_EXECUTED`. Automatic and manual delivery authority are both `NONE`,
external and credential access are `FORBIDDEN`, and its action count is the
exact integer `0`. The existing Production action inventory also remains all
zero.

No update-service origin, public key, release key, WordPress identity,
Application Password reference or value, filesystem method, compatibility
bound, package limit, runtime endpoint, scheduler, provider, repository,
workflow, role, credential, or Production endpoint is selected. The approved
read-only target observation is not copied into the contract as a Production
binding.

## Predecessor boundary

The owner builder byte-binds and semantically validates both the ST-1505
source contract and its generated reference plan. It also requires every exact
ST-1505 transitive predecessor binding for ST-1502, ST-1503, and ST-1504 in
the original order. Rebinding a digest cannot make semantic drift acceptable.

ST-1505 and its predecessors must remain non-executable and disabled, with all
selected values unset, provider calls and external actions forbidden, every
action count exactly zero, and formal TST-009/TST-022 unexecuted. These local
artifacts supply requirements to bind; they supply no infrastructure,
identity, staging, Production, deployment, or release authority.

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
GitHub, AWS, IAM, a provider, a network, a credential store, a deployment or
release system, or any other external service.

## Owned source and generated artifacts

Do not hand-edit generated artifacts. Change the contract or builder and run
the owner command.

| Classification | Path | Role |
| --- | --- | --- |
| Exact authority | `changes/st-1506/DESIGN_HANDOFF_V1_ST1506_WORDPRESS_SIGNED_DELIVERY_INTERFACE_V1.yaml` and detached approval | Hash-bound authority and approved path/safety boundary |
| Story source | `changes/st-1506/contracts/production-deployment-definition.v1.yaml` | Closed Production safety plus signed-delivery trust, admission, replay, restore, authorization, receipt, separation, and disabled-execution requirements |
| Owner builder | `scripts/build_st1506_production_deployment.py` | Strict deterministic validator and renderer |
| Test source | `tests/st1506/*.py` | Positive, hostile, provenance, path-safety, no-write, and static-boundary coverage |
| Work log | `docs/worklogs/ST-1506.md` | Local preflight, implementation, verification, and unexecuted-gate ledger |
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
workflow configuration; PHP or JavaScript updater/loader code; cryptographic
signing or verification; key generation or use; package build/upload/install;
Application Password use; WordPress route, mutation, filesystem switch, health
probe, restore, or scheduler execution; Production deployment; publication;
release; and status transition remain `NOT_EXECUTED` or `NOT_AUTHORIZED`.
Each requires its separately authorized owner, environment, immutable evidence,
approvals, and resolved decisions.
