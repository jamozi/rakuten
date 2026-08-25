# ST-1504 provider-neutral deployment identity boundary

This Story-owned slice implements the maximum safe repository-local boundary
for a future GitHub Actions OIDC deployment identity: a deterministic offline
trust evaluator, exact synthetic recorded fixtures, a repository-inert workflow
fixture, and a strict disabled activation port. GitHub Actions and GitHub remain
the approved CI/OIDC source and initial external review connector. They do not
select a target cloud. AWS, another cloud, or owner-managed infrastructure can
become a future target only after the same closed capability admission and
evidence requirements are satisfied.

The direct-owner
`DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml` governs
this new decision together with Canonical sources and the provider-neutral
ST-1501 predecessor. The earlier Pro-derived advisory slice is predecessor
context, not sole authority for this revision, and it does not demote or
supersede the current Canonical AWS Reference Architecture.

AWS Tokyo and the AWS IAM OIDC provider, AWS IAM role, AWS account, AWS region,
and AWS audience mappings remain the current Canonical Reference Architecture
inherited from INT-DEC-007 and RAOS-ARCH-001. This overlay does not erase,
replace, or complete the Canonical AWS-specific ST-1504 objective or
workflow/IAM trust deliverable. Non-AWS and owner-managed target profiles are
additional portable implementation paths only. Canonical reference status is
never a default, implicit fallback, selected binding, eligibility shortcut,
admission requirement, or evidence substitute. No alternate provider is
selected.

## Status boundary

- Local artifact: `MAXIMUM_SAFE_LOCAL_CODE_COMPLETE`
- Offline recorded policy evaluation: `EXECUTED_LOCAL_RECORDED_NOT_FORMAL`
- Authentication and signature verification: `NOT_PERFORMED`
- Admission: `NOT_EVALUATED`; eligible: `false`
- Selected/default/fallback target profile and every target binding: unset
- Activation: `DISABLED`
- Planned create/update/delete actions: `0` / `0` / `0`
- Network, credential, provider, write, issuance, deploy, release, and
  Production actions: `FORBIDDEN`
- Credential material and issuance capability: `ABSENT`
- Formal TST-026, hosted GitHub/provider, live federation, staging, deployment,
  release, and Production: `NOT_EXECUTED`
- Effective Canonical implementation/verification status: unchanged

This is not Story Done, `VALIDATED`, deployed, released, or Production-ready
evidence.

## Offline evaluator and inert workflow

The evaluator under `python/raos/domain/deployment_identity.py` accepts only a
closed recorded claim envelope and a closed recorded trust policy. It evaluates
exact policy matching without parsing a JWT, verifying a signature,
authenticating a workload, issuing a credential, contacting a provider, or
granting deploy authority. The fixtures use only explicit synthetic identifiers
and `.invalid` issuer/audience values.

The workflow fixture is stored under `infra/terraform/deployment-identity/`,
outside GitHub's active `.github/workflows/` path. Its sole job has an
always-false condition, zero deployment actions, no reusable action, and a fail
sentinel. The port in `python/raos/ports/deployment_identity.py` and adapter in
`python/raos/adapters/disabled_deployment_identity.py` reject enablement,
nonzero actions, credential material, and forged permissive receipts and always
remain disabled.

## Closed target-profile admission

Every future target profile must provide exactly one explicit mapping for each
required capability:

1. exact repository, ref, workflow, environment, audience, and subject binding;
2. short-lived federation without static cloud secrets or human credentials;
3. exact target environment and audience binding;
4. least-privilege session scope and duration limits;
5. protected-environment distinct human approval;
6. provenance, audit, revocation, alert ownership, and rollback;
7. provider account, project, tenant, environment, region, and residency isolation;
8. equivalent security, operations, and release evidence.

Missing, unknown, duplicate, reordered, partial, implicit, defaulted, fallback,
provider-label-only, AWS-label-only, GitHub-source-label-only, and reference-only
mappings fail closed. A provider or service label cannot satisfy evidence.

## GitHub source, trust, and credential boundary

GitHub Actions OIDC is the fixed source system. The exact repository, trusted
ref, workflow, environment, audience, and subject values remain unset until a
separately reviewed future implementation. Wildcards, fork or untrusted pull
requests, `pull_request_target` credential paths, untrusted refs or
environments, broad subjects or audiences, and unbounded reusable callers are
forbidden.

Long-lived or static provider credentials, repository-secret cloud
credentials, and human cloud credentials are forbidden. Any future federated
session must be short-lived, least-privilege, bounded in scope and duration,
auditable, and revocable, with no role chaining, privilege escalation, or
cross-environment identity reuse.

Production requires a distinct human approval in a protected environment with
exact allowed refs. Self-approval, bypass, cross-environment target reuse, and
deployment without approval are forbidden. Signed provenance, immutable audit,
revocation, alert/runbook ownership, evidence retention, rollback, and the
kill-switch boundary remain required but unconfigured.

## Open Decisions and unexecuted work

OD-009 budget, OD-011 notification channels, OD-013 region/data residency, and
OD-015 Production provider credentials remain unresolved with their safe
defaults. No provider, profile, account, project, tenant, region, audience,
role, session, plugin, adapter, policy payload, or physical resource is
selected. Local generation does not resolve these decisions or substitute for
formal, hosted, provider, staging, release, or Production evidence.

## Owned source and generated artifacts

Do not hand-edit generated artifacts. Change the handoff, contract, builder, or
tests, then run the owner command.

| Classification | Path | Role |
| --- | --- | --- |
| Direct design authority | `changes/st-1504/DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml` | Durable provider-neutral deployment-identity decision |
| Story source | `changes/st-1504/contracts/github-oidc-deployment.v1.yaml` | Closed source, admission, trust, credential, approval, lifecycle, and execution contract |
| Owner builder | `scripts/build_st1504_github_oidc.py` | Strict deterministic validator and renderer without environment, network, subprocess, provider SDK, or credential surface |
| Test source | `tests/st1504/*.py` | Positive, hostile, provenance, predecessor, filesystem, atomic-write, no-write, and sanitized-diagnostic coverage |
| Runtime source | `python/raos/domain/deployment_identity.py` | Closed offline policy-match evaluator with no authentication or provider authority |
| Activation source | `python/raos/ports/deployment_identity.py`, `python/raos/adapters/disabled_deployment_identity.py` | Strict zero-action activation port and disabled adapter |
| Generated reference | `infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json` | Non-executable source-derived reference plan |
| Generated fixtures | `infra/terraform/deployment-identity/github-oidc.{claims,trust-policy,evaluation}.recorded.v1.json` | Exact synthetic claims, trust policy, and policy-match-only evidence |
| Inert workflow fixture | `infra/terraform/deployment-identity/github-oidc-deploy.disabled.workflow.yml` | Syntactically valid, always-disabled fixture outside the active GitHub workflow path |
| Local implementation record | `changes/st-1504/IMPLEMENTATION_RECORD_V2_ST1504_OFFLINE_OIDC.yaml` | Reversible repository-local detail and authority boundary |
| Local completion evidence | `changes/st-1504/LOCAL_COMPLETION_EVIDENCE_V2.md` | Check results and explicit residual external/formal debt |
| Generated inventory | `changes/st-1504/manifest.yaml` | Exact authority, predecessor, source, output, and fail-closed boundary hashes |

The builder raw-hash and semantically binds the direct handoff, Canonical
sources, root GitHub connector policy, ST-0107 governance, and ST-1501 handoff
and contract. It reconstructs the ST-1501 plan deterministically and compares
its exact committed bytes.

## Local commands

Generate all declared outputs:

```bash
uv run --locked --no-sync python scripts/build_st1504_github_oidc.py
```

Verify source pins and committed output bytes without writing:

```bash
uv run --locked --no-sync python scripts/build_st1504_github_oidc.py --check
```

Run the isolated focused suite:

```bash
uv run --locked --no-sync pytest -q tests/st1504
```

The CLI accepts only `--check`. It has no repository, issuer, audience, ref,
environment, provider, account, project, tenant, region, role, policy,
credential, token, secret, plan, apply, deploy, release, or Production argument.
