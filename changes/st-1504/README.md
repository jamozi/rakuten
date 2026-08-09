# ST-1504 GitHub OIDC deployment reference boundary

This Story-owned slice records the maximum safe local interface for a future
GitHub Actions OIDC to short-lived AWS workload session. It creates no workflow,
IAM trust policy, GitHub environment, repository binding, AWS role, credential,
deployment, or external resource. The generated plan is non-executable.

## Status boundary

- Local artifact: `INTERFACE_ONLY_PARTIAL_LOCAL_CODE`
- Activation: `DISABLED`
- Planned create/update/delete actions: `0` / `0` / `0`
- Credential material and issuance capability: `ABSENT`
- Formal TST-026, hosted GitHub/AWS, live OIDC, staging, deployment, release,
  and Production: `NOT_EXECUTED`
- Effective canonical implementation/verification status: unchanged

This is not Story Done, `VALIDATED`, deployed, or Production-ready evidence.

## Owned source and generated artifacts

Do not hand-edit generated artifacts. Change the contract or builder, then run
the owner command.

| Classification | Path | Role |
| --- | --- | --- |
| Story source | `changes/st-1504/contracts/github-oidc-deployment.v1.yaml` | Closed logical identity, trust, permission, approval, and disabled-execution requirements |
| Owner builder | `scripts/build_st1504_github_oidc.py` | Strict deterministic validator and renderer with no environment, network, subprocess, provider SDK, or credential surface |
| Test source | `tests/st1504/*.py` | Positive, hostile, provenance, atomic-write, no-write, and sanitized-diagnostic coverage |
| Generated reference | `infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json` | Non-executable source-derived reference plan |
| Generated inventory | `changes/st-1504/manifest.yaml` | Exact authority, predecessor, source, output, and boundary hashes |

The builder binds the installed ST-0107 governance contract and ruleset desired
state byte-for-byte and semantically. That desired state protects pull requests,
has no bypass actor, is not remotely applied, and exposes no remote mutation
path. The builder also binds ST-1501's contract and reference plan with
activation disabled, native/provider/external operations forbidden, and all
planned action counts at zero.

## Local commands

Generate both declared outputs:

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
environment, account, role, policy, action version, credential, token, secret,
apply, deploy, or provider argument.

## Required future trust and credential boundary

A future separately approved implementation must bind the exact repository,
trusted ref, workflow identity, GitHub environment, audience, and subject with
no wildcard or broad organization/repository/ref subject. Fork or untrusted
pull requests, `pull_request_target` credential paths, untrusted refs or
environments, and unbounded reusable-workflow callers must never receive a
cloud credential.

Long-lived cloud keys and repository-secret cloud credentials are forbidden.
Any future OIDC session must be short-lived and least-privilege, without role
chaining or privilege escalation. This repository slice records no secret name,
secret value, token, credential value, or trust/permission policy payload.

## Workflow and Production approval intent

`id-token: write` may exist only on a future exact approved deployment job;
minimum read-only contents permission is required. Write-all, administrative or
secret access, mutable external-action references, and an unbounded caller are
forbidden. No workflow file or external action is selected here.

Production requires a distinct human approval, a protected environment, and
exact allowed refs. Self-approval, bypass, and deployment without approval are
forbidden. The actual environment, reviewers, refs, repository, workflow,
account, role, session properties, thumbprints, and policy payloads remain
unset.

## Explicitly unexecuted work

Executable workflow and IAM/provider definitions, exact action/provider/tool
versions, repository and AWS binding, native policy validation, credential
exchange, trust-policy simulation, hosted security review, TST-026, live OIDC,
staging, deployment, release, and Production require separate owners,
credentials, external-state authority, review, and evidence. None is simulated
or activated by this local reference plan.
