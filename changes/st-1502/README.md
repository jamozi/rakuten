# ST-1502 provider-schema-free data-services module

This Story-owned slice implements the maximum-safe local part of the Canonical
ST-1502 data-services infrastructure objective. The owner generator emits a
deterministic, executable Terraform HCL module containing a closed logical
resource graph for the Canonical AWS-reference capabilities: relational
persistence, immutable object storage, queues and DLQs, secret metadata,
purpose-separated encryption keys, recovery declarations, and least-privilege
permission sets.

The HCL is executable only as a provider-free validation module. It contains no
provider requirement, provider, backend, cloud, module, data, resource,
provisioner, credential, account, region, network, remote state, or physical
resource binding. It therefore cannot materialize infrastructure or produce a
provider-backed plan. This distinction is deliberate: OD-013, OD-014, and
OD-015 do not authorize the missing Production choices, and no provider schema
may be invented from Canonical reference metadata.

AWS Tokyo and the RDS, S3, SQS, Secrets Manager, and KMS names remain the
Canonical Reference Architecture inherited from INT-DEC-007 and RAOS-ARCH-001.
They are not a selected provider, default, implicit fallback, admission
shortcut, or evidence substitute. A successor revision must use the closed
activation port and provide every required external and formal gate before it
can add a provider schema or physical resource graph.

## Logical graph and invariants

The generated module and no-apply fixture contain 37 logical nodes and explicit
relationships:

- one private PostgreSQL-compatible relational database declaration;
- five private, encrypted, immutable/versioned object-storage roles;
- seven primary queues paired one-to-one with seven DLQs and redrive edges;
- one secret-metadata boundary containing no secret value;
- four purpose-separated encryption-key declarations with rotation;
- three recovery declarations for relational PITR, object versions, and
  configuration/secret reconstruction;
- nine separated, wildcard-free IAM permission sets;
- encryption, protection, redrive, reconstruction, and authorization edges.

Every node denies public access. Persisted data requires encryption at rest;
network interactions require transport encryption. Database backup and
deletion protection, object immutability, queue DLQs, key rotation, separated
producer/consumer/redrive roles, and wildcard-free permissions are mandatory.
All create, update, delete, migrate, backup, restore, redrive, and rotate action
counts are zero.

The HCL uses only `terraform`, `variable`, `locals`, `check`, and `output`
blocks. Variables are closed safe-default assertions rather than activation
inputs. The checks reject activation, Production authorization, selected
provider/account/region/backend/credential/network/retention values, provider
evidence, public exposure, disabled encryption, missing backup/immutability/DLQ
declarations, wildcard permissions, and nonzero actions.

## Successor activation port

The current revision keeps all physical selections null or empty and marks
provider binding, resource materialization, plan, and apply as forbidden. A
new reviewed successor contract is required before any binding. That contract
must provide, at minimum:

1. resolved OD-013 region/residency and OD-014 retention/deletion decisions;
2. OD-015 provider/account/credential evidence;
3. formal TST-026 security and TST-029 isolated-restore evidence;
4. exact provider schema, plugin, and distribution provenance;
5. private network/account isolation and least-privilege policy review;
6. backup, restore, key-recovery, and rollback evidence;
7. a separate human-approved release path.

None of those gates is supplied or inferred by this local implementation.

## Source and generated artifacts

Do not hand-edit generated artifacts. Change a Story-owned source and run the
owner generator.

| Classification | Path | Role |
| --- | --- | --- |
| Direct design authority | `changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml` | Scope, decisions, invariants, and external gates |
| Story contract | `changes/st-1502/contracts/data-services-foundation.v1.yaml` | Closed logical and successor-activation contract |
| Implementation record | `changes/st-1502/IMPLEMENTATION_RECORD_V2_ST1502_LOGICAL_HCL.yaml` | Local implementation and authority boundary |
| Local evidence | `changes/st-1502/LOCAL_COMPLETION_EVIDENCE_V2.md` | Verification and debt reconciliation |
| Owner source | `scripts/build_st1502_data_services.py` | Strict validation and deterministic rendering |
| Test source | `tests/st1502/*.py` | Positive, hostile, provenance, and no-write checks |
| Reference plan | `infra/terraform/data-services/data-services.reference-plan.v1.json` | Safe-boundary summary and logical intents |
| Logical plan | `infra/terraform/data-services/data-services.logical-plan.v1.json` | Deterministic no-apply graph fixture |
| Toolchain lock | `infra/terraform/data-services/terraform-validation-toolchain.lock.v1.json` | Exact inherited ST-1501 validation boundary |
| HCL module | `infra/terraform/data-services/{versions,variables,locals,checks,outputs}.tf` | Provider-free executable logical module |
| Generated inventory | `changes/st-1502/manifest.yaml` | Source, authority, predecessor, and output hashes |

Generate all ST-1502 outputs:

```bash
uv run --locked --no-sync python scripts/build_st1502_data_services.py
```

Verify exact source pins and committed output bytes without writing:

```bash
uv run --locked --no-sync python scripts/build_st1502_data_services.py --check
```

An explicit native check is available only with the exact Terraform 1.15.9
Linux amd64 binary pinned by ST-1501:

```bash
uv run --locked --no-sync python scripts/build_st1502_data_services.py \
  --native-check --terraform /absolute/path/to/terraform
```

The native path verifies the binary digest, enters a new user/network
namespace, supplies a closed environment, and permits only `version -json`,
`fmt -check -recursive`, and `validate -json`. It does not run `init`, discover
or install providers, call a provider, read credentials, write repository
files, or run `plan`, `apply`, `destroy`, `import`, or `refresh`.

## Completion and evidence boundary

- Local deliverable: `MAXIMUM_SAFE_LOCAL_CODE_COMPLETE`.
- Effective Canonical status: unchanged.
- Provider/account/region/backend/credential/network/retention selections:
  unset.
- Activation and physical resource materialization: forbidden.
- Local provider-free native format/semantic validation:
  `EXECUTED_LOCAL_NOT_FORMAL`.
- Formal TST-026/TST-029, provider/AWS validation, actual backup/restore,
  hosted CI, staging, release, deployment, and Production: `NOT_EXECUTED`.

Local evidence must never be promoted to `VALIDATED`, provider, recovery,
staging, release, or Production evidence.
