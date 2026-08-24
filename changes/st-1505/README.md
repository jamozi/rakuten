# ST-1505 provider-neutral staging admission boundary

This Story-owned slice records both the fail-closed reference for a future
staging deployment and the maximum-safe executable local admission simulator.
The direct owner
`DESIGN_HANDOFF_V1_ST1505_PROVIDER_NEUTRAL_STAGING.yaml`, the Canonical Story,
and the current provider-neutral ST-1501 through ST-1504 inputs govern this
decision. Earlier Pro-derived advisory artifacts remain predecessor context,
not the sole authority for this staging policy. This overlay does not demote or
supersede the current Canonical AWS Reference Architecture.

The future-live generated plan remains closed, deterministic, and
non-executable. The separate local runtime validates only synthetic and
recorded fixtures. It creates no active workflow, infrastructure, credential,
database migration, deployment, network request, browser run, rollback,
release, or external state. Its sole durable effect is an explicit
owner-private local SQLite journal containing canonical synthetic result bytes.

## Provider-neutral admission

Full RAOS staging does not assume or require AWS. AWS Tokyo, Terraform AWS,
RDS, S3, SQS, Secrets Manager/KMS, ECS/Fargate, CloudFront/WAF/Route53/ACM,
and IAM/OIDC remain the current Canonical Reference Architecture mappings
inherited from INT-DEC-007 and RAOS-ARCH-001. The Canonical AWS-specific
ST-1505 objective and staging pipeline deliverable remain authoritative and
NOT_STARTED/NOT_EXECUTED; this portability overlay does not erase, replace,
or complete them. An AWS label or mapping is never a default, fallback,
selected binding, dependency shortcut, admission requirement, eligibility
shortcut, or evidence substitute.

A future non-AWS or owner-managed target is an additional portable
implementation path, and any future target, including AWS, is admitted only
after it explicitly satisfies the same closed contract:

- all ST-1501 foundation, ST-1502 data-services, ST-1503 compute-edge, and
  ST-1504 deployment-identity provider-neutral admissions;
- an immutable build digest, SBOM, vulnerability result, signed provenance,
  and promotion without rebuild;
- Expand-Migrate-Contract compatibility, migration dry-run and lock evidence,
  an assigned migration owner, and independent migration approval;
- exact repository/ref/workflow/environment/audience/subject binding and an
  independent protected-environment human approval;
- smoke, security, runtime, browser, health, and Public/Admin/Internal
  isolation evidence;
- authenticated encrypted, peer-verified, downgrade-resistant transport for
  every staging artifact, identity, deployment, migration, runtime,
  telemetry/alert, rollback/restore, and target-adapter network flow;
- traces, metrics, redacted logs, release markers, SLOs, alert routes, and
  notification evidence;
- rollback, restore rehearsal, restored integrity, isolation, region,
  residency, retention, budget, and automatic-stop evidence; and
- an explicit provider-neutral target adapter with equivalent security,
  operations, release, audit, and revocation evidence.

Every required dependency and capability has exactly one closed inventory row.
Missing, unknown, duplicate, reordered, partial, implicit, label-only,
predecessor-only, default, fallback, or reference-only attempts fail closed.
No concrete alternate provider is selected by this slice.

## Current safe state

- Canonical design: `APPROVED_FOR_IMPLEMENTATION`
- Future-live interface deliverable: `INTERFACE_ONLY_PARTIAL_LOCAL_CODE`
- Local simulator proposal: `MAXIMUM_SAFE_LOCAL_CODE_COMPLETE_PROPOSAL`
- Admission: `NOT_EVALUATED`; eligible: `false`
- Selected/default/fallback profile: `null`
- Provider, account/project/tenant, region, backend, identity, adapter, plugin,
  resource, artifact, endpoint, alert, budget, and rollback bindings: unset
- Environment label: inert `STAGING`; configuration: `NOT_CONFIGURED`
- Activation: `DISABLED`
- Credential, provider, network, write, deployment, migration, staging,
  rollback, release, and Production actions: `FORBIDDEN`
- Every action count: `0`
- Local fixture pipeline: repository-inert, default-disabled, no trigger,
  command, active workflow path, selected target, provider client, or network
  client
- Local admission: immutable synthetic digest, recorded SBOM/vulnerability/
  provenance binding, in-memory Expand-Migrate-Contract plan and dry-run,
  recorded loopback Public/Admin/Internal health, in-memory rollback/restore
  integrity, and owner-private durable recovery
- Runtime, hosted, formal, live-provider, staging, release, and Production
  evidence: `NOT_EXECUTED`

OD-002, OD-009, OD-010, OD-011, OD-013, OD-014, and OD-015 remain unresolved
with their safe defaults. Security, operations, release, migration-owner,
protected-environment, and independent human approval gates remain mandatory.
Local regeneration or tests cannot replace those gates or live evidence.

## Exact predecessor evidence

The owner builder binds the raw hash and semantic hash of each ST-1501 through
ST-1504 design handoff, contract, and generated reference plan. It also raw-hash
pins every imported predecessor owner generator and the ST-1504 governance
validation inputs before invoking those owner validators and renderers. The
committed plan bytes must match full semantic validation plus deterministic
owner regeneration. Rebinding raw and semantic digests cannot make a weakened
or formatting-only divergent predecessor acceptable.

ST-1501 and ST-1502 now expose provider-free local validation, while ST-1503
and ST-1504 remain disabled for activation. None provides a selected target,
credential, infrastructure deployment, or staging authority. ST-1505 also
pins the hardened ST-1504 manifest, deployment-identity domain/port/disabled
adapter, and recorded evaluation fixture before trusting the exact disabled
receipt.

## Owned source and generated artifacts

Generated files must never be hand-edited. Change the owner source and run the
builder.

| Classification | Path | Role |
| --- | --- | --- |
| Design authority | `changes/st-1505/DESIGN_HANDOFF_V1_ST1505_PROVIDER_NEUTRAL_STAGING.yaml` | Durable provider-neutral staging decision and gates |
| Story contract | `changes/st-1505/contracts/staging-deployment.v1.yaml` | Closed dependency, capability, intent, selection, execution, and evidence boundary |
| Local runtime contract | `changes/st-1505/contracts/local-staging-admission-runtime.v2.yaml` | Closed synthetic artifact, migration, health, rollback, journal, zero-action, and evidence boundary |
| Owner builder | `scripts/build_st1505_staging_deployment.py` | Strict validator and deterministic renderer |
| Local runtime | `python/raos/domain/ops/staging_admission.py`, `python/raos/application/ops/staging_admission.py`, `python/raos/ports/staging_admission.py`, `python/raos/adapters/recorded_staging_admission.py`, `python/raos/staging_admission_runner.py` | Pure admission, disabled identity coordination, owner-private persistence, and explicit runner |
| Test source | `tests/st1505/*.py` | Positive, hostile, provenance, path-safety, and no-write evidence |
| Generated reference | `infra/terraform/staging/staging-deployment.reference-plan.v1.json` | Non-executable source-derived reference plan |
| Generated inert fixture | `infra/terraform/staging/local-staging-admission.pipeline.disabled.v2.yaml` | Default-disabled local phase description outside active workflows |
| Generated recorded result | `infra/terraform/staging/local-staging-admission.result.recorded.v2.json` | Deterministic local result; explicitly not staging evidence |
| Generated inventory | `changes/st-1505/manifest.yaml` | Exact authority, predecessor, source, output, semantic, and status provenance |

Generate all declared outputs:

```bash
uv run --locked --no-sync python scripts/build_st1505_staging_deployment.py
```

Verify committed bytes without writing:

```bash
uv run --locked --no-sync python scripts/build_st1505_staging_deployment.py --check
```

The CLI accepts only `--check`. It reads no ambient credential or provider
configuration, calls no provider or browser, performs no network request, and
invokes no deployment tool. No active ST-1505 deployment workflow exists or is
added by this slice.

The explicit local runner requires a caller-created absolute directory with
mode `0700`, a closed `st1505-run-*` identifier, and a non-secret
`st1505-key-*` replay key. It hashes the replay key before persistence and
writes only the fixed `st1505-local-admission.sqlite3` file with mode `0600`:

```bash
PYTHONPATH=python:. python -m raos.staging_admission_runner \
  --private-root /absolute/owner-private-local-directory \
  --run-id st1505-run-local-001 \
  --idempotency-key st1505-key-local-001
```

This command still performs zero provider, credential, network, database
migration, smoke-request, browser, staging, deployment, release, rollback, or
Production action.

## Explicitly unexecuted work

Formal TST-009 and TST-022, real migration database execution and independent
review, HTTP/Playwright execution, protected-environment approval, hosted CI,
target adapter runtime,
provider/account/credential use, staging configuration and deployment, smoke,
rollback/restore exercise, release, and Production remain `NOT_EXECUTED` and
require their separately authorized owners, environments, approvals, and
evidence. This local result does not make ST-1505 Story Done, `VALIDATED`,
deployed, or release/Production ready.
