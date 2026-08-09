# ST-1501 Terraform foundation interface-only candidate

This Story-owned slice defines a strict, source-derived foundation boundary
that later ST-1502 and ST-1503 work can extend. It is deliberately not a
Terraform module, native Terraform plan, AWS account configuration, remote
state backend, or Production deployment.

## Status boundary

- Canonical design: `APPROVED_FOR_IMPLEMENTATION`
- Local deliverable: `INTERFACE_ONLY_PARTIAL_LOCAL_CODE`
- Effective canonical implementation status: unchanged (`NOT_STARTED`)
- Required formal TST-026: `NOT_EXECUTED`
- Terraform/OpenTofu validation: `NOT_EXECUTED`
- AWS/provider/runtime validation: `NOT_EXECUTED`
- Staging, release, infrastructure apply, and Production: `NOT_EXECUTED`

ST-0106 is present as a local dependency, but its formal CI evidence and this
Story's full definition-of-ready boundary remain unmet. Local contract and
pytest results therefore cannot make ST-1501 Done or `VALIDATED`.

## Safe default

`INT-DEC-007` and RAOS-ARCH-001 name AWS `ap-northeast-1` only as reference
architecture metadata and require a portable core. `OD-013` remains
`HUMAN_DECISION_REQUIRED`; its safe default forbids Production apply.

The contract consequently keeps every real selection unset:

- cloud provider and Production/backup regions;
- Development and Production account identifiers;
- Terraform/OpenTofu and provider-plugin versions;
- remote-state backend and credential source;
- network CIDRs, availability zones, KMS reference, and budget;
- every resource definition.

Activation is disabled, every native operation is forbidden, and the
reference-only action counts are exactly zero for create, update, and delete.
Rejected contract values are reported only by stable error code and fixed
field name; values are never included in diagnostics.

## Source and generated artifacts

Do not hand-edit generated artifacts. Change the source contract or builder,
then regenerate.

| Classification | Path | Role |
| --- | --- | --- |
| Story source | `changes/st-1501/contracts/terraform-foundation.v1.yaml` | Closed desired-state and safety boundary |
| Implementation source | `scripts/build_st1501_terraform_foundation.py` | Strict loader, validator, domain model, and deterministic owner builder |
| Test source | `tests/st1501/*.py` | Positive, hostile, exact-type, generation, and no-write checks |
| Generated reference plan | `infra/terraform/foundation/terraform-foundation.reference-plan.v1.json` | Non-executable successor input with no selected provider, account, backend, credential, or resources |
| Generated inventory | `changes/st-1501/manifest.yaml` | Source and generated-output hashes |

The generated plan carries its source and generation command and is classified
`SOURCE_DERIVED_REFERENCE_STATE_PLAN`. It is not an `terraform plan` payload
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
and recoverable; use separate Development and Production accounts; detect
drift; and make Production changes through reviewed IaC with explicit human
approval. Those requirements are recorded, but none is claimed configured.

ST-1502 and ST-1503 may consume the generated reference-plan document as a
read-only predecessor. Resource payloads require their own approved Story
contract and generator revision; this ST-1501 loader rejects them.

## Completion boundary

This commit may support only a local partial implementation checkpoint.
Native Terraform validation, provider/version provenance, remote-state tests,
AWS account/network/security review, formal TST-026, hosted CI, live provider,
staging, release, deployment, and Production remain separately unexecuted.
