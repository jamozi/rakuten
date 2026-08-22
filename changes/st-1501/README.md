# ST-1501 provider-neutral Terraform foundation interface-only candidate

This Story-owned slice defines a strict, source-derived foundation boundary
that later ST-1502 and ST-1503 work can extend. It is deliberately not a
Terraform module, native Terraform plan, provider account or project
configuration, remote state backend, or Production deployment.

## Status boundary

- Canonical design: `APPROVED_FOR_IMPLEMENTATION`
- Local deliverable: `INTERFACE_ONLY_PARTIAL_LOCAL_CODE`
- Effective canonical implementation status: unchanged (`NOT_STARTED`)
- Required formal TST-026: `NOT_EXECUTED`
- Terraform/OpenTofu validation: `NOT_EXECUTED`
- Provider/runtime validation: `NOT_EXECUTED`
- Staging, release, infrastructure apply, and Production: `NOT_EXECUTED`

ST-0106 is present as a local dependency, but its formal CI evidence and this
Story's full definition-of-ready boundary remain unmet. Local contract and
pytest results therefore cannot make ST-1501 Done or `VALIDATED`.

## Safe default

The direct-owner
`DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml` records the durable
ST-1501 decision governing this revision. `INT-DEC-007` and RAOS-ARCH-001 name
AWS `ap-northeast-1` only as optional historical reference architecture
metadata and require a portable core. The AWS reference is never a default,
implicit fallback, selected binding, eligibility shortcut, admission
requirement, or evidence substitute. `OD-013` remains
`HUMAN_DECISION_REQUIRED`; its safe default forbids Production apply.

The contract consequently keeps every real selection unset:

- cloud provider and Production/backup regions;
- Development and Production account identifiers;
- Terraform/OpenTofu and provider-plugin versions;
- remote-state backend and credential source;
- network CIDRs, availability zones, KMS reference, and budget;
- every resource definition.

Activation is disabled; network and credential access, provider calls,
external writes, deploy, release, Production action, and every native operation
are forbidden. The reference-only action counts are exactly zero for create,
update, and delete.
Rejected contract values are reported only by stable error code and fixed
field name; values are never included in diagnostics.

## Provider-neutral foundation admission

No provider is currently selected or eligible. A future AWS, other-cloud, or
owner-managed profile must explicitly map exactly one implementation to every
closed capability below:

- IaC toolchain and provider-plugin provenance;
- remote-state integrity, locking, audit, backup, restore, and recovery;
- Development and Production account, project, tenant, or equivalent isolation;
- public/admin/internal/data-plane network and traffic controls;
- workload identity and secret boundaries;
- telemetry, control-plane audit, alerts, and drift detection;
- infrastructure configuration backup, restore drill, and recovery;
- attributable cost, budget alert, and bounded stop controls;
- approved primary/backup region, cross-border, and residency evidence;
- human-approved IaC change, promotion, rollback, and recovery.

Missing, unknown, duplicate, reordered, partial, implicit, defaulted, fallback,
provider-label-only, or reference-only mappings fail closed. Provider,
account/project, region, plugin, and state-backend bindings remain selected,
default, and fallback `null`. Every provider kind must supply identical
security, operations, release, backup/restore, and residency evidence.

This contract is an admission boundary, not a concrete alternate-provider
implementation. No AWS or non-AWS Terraform payload, account, project, network,
plugin, backend, credential, provider call, deployment, or Production action is
created by this slice.

## Source and generated artifacts

Do not hand-edit generated artifacts. Change the source contract or builder,
then regenerate.

| Classification | Path | Role |
| --- | --- | --- |
| Durable Story decision | `changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml` | Provider-neutral admission decision and retained gates |
| Story source | `changes/st-1501/contracts/terraform-foundation.v1.yaml` | Closed desired-state and safety boundary |
| Implementation source | `scripts/build_st1501_terraform_foundation.py` | Strict loader, validator, domain model, and deterministic owner builder |
| Test source | `tests/st1501/*.py` | Positive, hostile, exact-type, generation, and no-write checks |
| Generated reference plan | `infra/terraform/foundation/terraform-foundation.reference-plan.v1.json` | Non-executable successor input with no selected provider, account, backend, credential, or resources |
| Generated inventory | `changes/st-1501/manifest.yaml` | Source and generated-output hashes |

The generated plan carries its source and generation command and is classified
`SOURCE_DERIVED_REFERENCE_STATE_PLAN`. It is not a `terraform plan` payload
and contains no HCL, provider lock, provider cache, backend value, or resource.

## Local commands

Generate the two ST-1501-owned outputs:

```bash
uv run --locked --no-sync python scripts/build_st1501_terraform_foundation.py
```

Verify source pins, strict semantics, and committed output bytes without
writing:

```bash
uv run --locked --no-sync python scripts/build_st1501_terraform_foundation.py --check
```

The builder exposes no provider, backend, account, credential, resource,
activation, or operation argument. It does not invoke Terraform/OpenTofu,
download plugins, access the network, read ambient credentials, run a provider
discovery, or execute init/plan/apply/destroy/import/refresh.

## Future-state requirements

A later approved revision must keep remote state encrypted, locked, audited,
and recoverable; isolate Development and Production through accounts, projects,
tenants, or an equivalent reviewed boundary; detect drift; and make Production
changes through reviewed IaC with explicit human approval. Those requirements
are recorded, but none is claimed configured.

ST-1502 and ST-1503 may consume the generated reference-plan document as a
read-only predecessor. Resource payloads require their own approved Story
contract and generator revision; this ST-1501 loader rejects them.

## Completion boundary

This commit may support only a local partial implementation checkpoint.
Native Terraform validation, provider/version provenance, remote-state tests,
provider account/project/network/security review, formal TST-026, hosted CI,
live provider, staging, release, deployment, and Production remain separately
unexecuted.
