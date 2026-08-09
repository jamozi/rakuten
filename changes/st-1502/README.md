# ST-1502 data services interface-only candidate

This Story-owned slice records the maximum-safe logical data-service intent
that can be derived from the approved RAOS design without selecting an AWS
account, physical resource, provider/toolchain, credential, network, region,
retention period, or destructive behavior. It is not executable Terraform,
an AWS configuration, a native plan, or a deployment.

## Status boundary

- Canonical design: `APPROVED_FOR_IMPLEMENTATION`
- Local deliverable: `INTERFACE_ONLY_PARTIAL_LOCAL_CODE`
- Effective canonical implementation status: unchanged (`NOT_STARTED`)
- Required formal TST-026 and TST-029: `NOT_EXECUTED`
- Native Terraform/OpenTofu and AWS/provider validation: `NOT_EXECUTED`
- Restore, hosted CI, staging, release, apply, and Production: `NOT_EXECUTED`

ST-1501 exists only as a disabled, local reference/interface predecessor. Its
contract and generated reference-plan bytes and fail-closed semantics are
bound by the ST-1502 builder. They do not establish a native IaC toolchain or
make ST-1502 dependency-ready for formal delivery.

## Logical intent and safe defaults

The source contract contains logical intent only:

- a PostgreSQL service that must stay private and requires encryption,
  backup/PITR, deletion protection, a final snapshot, and restore testing;
- five logical object-storage roles (`raw`, `publication`,
  `uploads_quarantine`, `exports`, and `audit_logs`) that require public-access
  blocking, encryption, and versioning;
- seven canonical queue classes (`ingestion`, `ai`, `quality`, `publication`,
  `freshness`, `analytics`, and `notification`), each requiring a DLQ and
  separated producer, consumer, and redrive permissions;
- Secrets Manager metadata intent with no secret values, names, or ARNs; and
- KMS encryption, rotation, audit, and least-privilege intent with no key
  identifier, alias, policy, or deletion window.

Every engine version, instance/storage choice, subnet, endpoint, DB identity,
password reference, port, Multi-AZ choice, backup/retention value, physical
bucket/queue/secret/key identifier, policy document, and lifecycle rule stays
unset. OD-014 remains `HUMAN_DECISION_REQUIRED`, so lifecycle and automatic
deletion are forbidden. OD-013 reference metadata does not select a Production
or backup region. Key deletion, force destroy, native commands, provider calls,
and external writes are forbidden; activation is disabled and create/update/
delete counts are all zero.

## Source and generated artifacts

Do not hand-edit generated artifacts. Change the Story contract or builder and
regenerate.

| Classification | Path | Role |
| --- | --- | --- |
| Story source | `changes/st-1502/contracts/data-services-foundation.v1.yaml` | Closed logical intent and safety boundary |
| Implementation source | `scripts/build_st1502_data_services.py` | Strict validator and deterministic owner builder |
| Test source | `tests/st1502/*.py` | Positive, hostile, exact-type, provenance, and no-write checks |
| Generated reference plan | `infra/terraform/data-services/data-services.reference-plan.v1.json` | Non-executable logical data-services successor plan |
| Generated inventory | `changes/st-1502/manifest.yaml` | Source, predecessor, authority, and generated-output hashes |

Generate the two ST-1502-owned outputs:

```bash
uv run --locked --no-sync python scripts/build_st1502_data_services.py
```

Verify strict source/predecessor bindings and committed output bytes without
writing:

```bash
uv run --locked --no-sync python scripts/build_st1502_data_services.py --check
```

The builder has no resource/provider/backend/credential/network/retention
arguments. It does not read ambient or environment credentials, import an AWS
SDK, invoke subprocesses or native IaC, access the network, or perform external
writes.

## Completion boundary

This slice may support only a local partial implementation checkpoint. Exact
Terraform/OpenTofu and AWS-provider provenance, HCL/resources, account/network/
IAM review, real backups/restores, formal TST-026/TST-029, hosted CI, AWS,
staging, release, deployment, and Production remain separately unexecuted.
