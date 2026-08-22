# ST-1502 provider-neutral data-services interface

This Story-owned slice records a disabled, non-executable data-services
contract for Full RAOS Production. The direct-owner
`DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml` is the durable
authority for this revision and is hash-pinned by the contract, generator, and
manifest. It makes no provider, account or project, region, service, plugin or
adapter, credential, network, retention, or physical-resource selection.

AWS Tokyo and the names RDS, S3, SQS, Secrets Manager, and KMS remain visible
only as optional historical reference mappings inherited from INT-DEC-007 and
RAOS-ARCH-001. They are never a default, implicit fallback, selected binding,
eligibility shortcut, admission requirement, or evidence substitute. No
alternate cloud or owner-managed platform is selected by this slice.

## Provider-neutral admission boundary

A future AWS, other-cloud, or owner-managed profile is eligible only after it
explicitly maps exactly one implementation to every required capability and
provides the same security, operations, release, recovery, migration,
isolation, and residency evidence:

1. PostgreSQL-compatible relational persistence and controlled migrations.
2. Private, encrypted, immutable/versioned object storage and integrity.
3. At-least-once queues, duplicate-safe consumers, DLQs, and controlled
   redrive.
4. Least-privilege, non-ambient workload secrets and key management.
5. Data-service backup, restore, and isolated recovery drills.
6. Telemetry, audit, alerts, and configuration-drift evidence.
7. Development/Production and private data-plane isolation.
8. Approved primary/backup region and data-residency evidence.
9. Human-approved IaC, migration, promotion, rollback, and recovery.

Transport encryption is required for every relational, object-storage, queue,
secrets, and key-management interaction; encryption at rest is required for
all persisted data. No provider kind receives an exception by name.

Missing, unknown, duplicate, reordered, partial, implicit, label-only, or
reference-only mappings fail closed. All mapping rows remain
`REQUIRED_NOT_CONFIGURED`, the configured count is zero, admission is
`NOT_EVALUATED`, and eligibility is false.

## Status and safe defaults

- Canonical design: `APPROVED_FOR_IMPLEMENTATION`
- Local deliverable: `INTERFACE_ONLY_PARTIAL_LOCAL_CODE`
- Effective Canonical implementation status: unchanged (`NOT_STARTED`)
- Provider profile, provider/account, region, service, adapter, credential,
  network, and physical resources: unset
- Activation: `DISABLED`
- Create/update/delete/migrate/backup/restore/redrive/rotate counts: zero
- Network, credential, provider, write, migration, backup, restore, redrive,
  destructive, deploy, release, and Production actions: `FORBIDDEN`
- Native IaC, provider, migration, queue, restore, formal TST-026/TST-029,
  staging, release, and Production evidence: `NOT_EXECUTED`

OD-013 (region/residency), OD-014 (retention/deletion), and OD-015
(Production credentials/provider evidence) remain unresolved. Accordingly,
regions and retention stay unset, automatic deletion remains forbidden,
credentials remain absent, recorded fixtures cannot substitute for live
evidence, and Production apply remains forbidden.

ST-1501 is a hash-bound provider-neutral predecessor. The ST-1502 generator
validates its complete normalized contract and reference-plan semantics and
reconstructs the expected predecessor plan relationship before accepting it.
ST-1501 does not select a provider or make ST-1502 eligible.

## Source and generated artifacts

Do not hand-edit generated artifacts. Change the Story-owned handoff, contract,
builder, README, or tests and regenerate with the owner command.

| Classification | Path | Role |
| --- | --- | --- |
| Direct design authority | `changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml` | Provider-neutral decision, capability inventory, gates, and open-decision state |
| Story contract | `changes/st-1502/contracts/data-services-foundation.v1.yaml` | Closed logical intent and admission boundary |
| Implementation source | `scripts/build_st1502_data_services.py` | Strict validator and deterministic owner builder |
| Test source | `tests/st1502/*.py` | Positive, hostile, provenance, and no-write checks |
| Generated reference plan | `infra/terraform/data-services/data-services.reference-plan.v1.json` | Non-executable provider-neutral logical plan |
| Generated inventory | `changes/st-1502/manifest.yaml` | Source, authority, predecessor, and output hashes |

Generate the two ST-1502-owned outputs:

```bash
uv run --locked --no-sync python scripts/build_st1502_data_services.py
```

Verify all pins and committed output bytes without writing:

```bash
uv run --locked --no-sync python scripts/build_st1502_data_services.py --check
```

The builder exposes no provider/account/region/service/credential/backend,
retention, apply, or destroy input. It imports no provider SDK, reads no
ambient credentials, invokes no subprocess or native IaC command, performs no
network access, and makes no external write.

This local slice is not executable IaC and does not claim hosted CI, formal
TST-026/TST-029, provider, migration, restore, staging, release, deployment, or
Production evidence.
