# ST-1504 local completion evidence v2

## Claim boundary

- Story: `ST-1504` only.
- Base integration commit:
  `d8941c590cc8ba3a5d379659a41d6f9419694fb3`.
- Proposed local state: `MAXIMUM_SAFE_LOCAL_CODE_COMPLETE`.
- Formal `TST-026`, hosted GitHub OIDC, target-provider federation, credential
  issuance, assume-role, staging, deployment, release, and Production:
  `NOT_EXECUTED`.
- Canonical Story/status-registry transition: unchanged. This record is local
  evidence, not authentication, `VALIDATED`, hosted, provider, release, staging,
  or Production evidence.

## Implemented boundary

The Story now owns a deterministic, provider-neutral offline trust evaluator.
It accepts only closed, decoded, token-free recorded documents and binds exact
synthetic repository, repository IDs, ref, workflow, workflow SHA, environment,
audience, subject, actor, event, run, visibility, and empty pull-request/reusable
caller context. All values use explicit fixture identities or the reserved
`.invalid` namespace. Unknown fields, templates, wildcards, forks,
`pull_request`, `pull_request_target`, reusable-caller ambiguity, broad or
cross-environment bindings, and malformed claim shapes fail closed.

A successful comparison is explicitly `OFFLINE_POLICY_MATCH_ONLY_NOT_AUTHENTICATION`.
The implementation has no JWT parser, signature verifier, authentication
authority, provider SDK, network client, token exchange, credential issuance,
assume-role, deployment, release, or Production capability.

The recorded trust policy requires a 300–900 second session, the sole
`deployment-fixture:evaluate` permission, least privilege, distinct protected
human approval, signed provenance, immutable audit, revocation, rollback, and
evidence retention. It forbids role chaining, privilege escalation, static or
human credentials, cross-environment reuse, self-approval, and bypass.

The generated workflow fixture is syntactically parseable but stored under
`infra/terraform/deployment-identity/`, never `.github/workflows/`. It exposes
only a manual trigger shape, has root permissions `{}`, gives one permanently
disabled job `contents: read` and `id-token: write`, has no `uses` steps, and
contains a fail sentinel. The strict activation port and its only adapter always
return `DISABLED`, zero actions, and no credential material. The receipt type
itself rejects forged enabled, credential-issued, nonzero-action, and alternate
reason values before any downstream consumer can observe them.

## Local checks

| Gate | Result |
| --- | --- |
| `pytest -q tests/st1504` | `PASS`; `385 passed` |
| ST-1504 owner regeneration and `--check` | `PASS`; deterministic five-output generation and no-write check |
| `pytest -q tests/st1501` | `PASS`; `175 passed` |
| ST-1501 owner `--check` | `PASS` |
| Ruff format and lint over all ST-1504-owned Python | `PASS` |
| strict mypy over the owner, runtime, and Story tests | `PASS`; 10 source files |
| pinned strict Pyright over the three runtime modules | `PASS`; zero diagnostics |
| Python compile/import with bytecode redirected outside the repository | `PASS` |
| focused maintained secret scan under a denied-network namespace | `PASS`; 21 exact Story-owned files, zero findings |
| `git diff --check` | `PASS` |

Hostile tests include JWT/token/header/signature/authentication field injection;
unknown claim and policy fields; wildcard, template, fork, PR, PR-target,
reusable-caller, subject, ref, workflow, environment, and audience drift;
session-duration and permission broadening; role chaining; privilege escalation;
static and human credentials; cross-environment reuse; missing approval and
lifecycle controls; nonzero or boolean actions; activation enablement; credential
material; forged activation receipts; source and generated-byte drift; symlink
escape; and sanitized error behavior.

## Predecessor regression note

ST-0107's owner `--check` and suite were executed but are not green on the base
integration commit. They fail on one inherited pinned-source drift:
`.github/workflows/ci.yml` currently hashes to
`8fb768a883432d15a1f86390cd16bfd23092030c6483cf283a64a41e21dfb3fb`,
while ST-0107 still pins
`790af484fea8aaa38f040de7bd51dbb729bd643d255847a23310aaa37462510f`.
The isolated suite result is `7 failed, 22 passed, 64 errors`, all rooted in
that pin mismatch. ST-1504 did not edit any active workflow or ST-0107-owned
artifact. This inherited integration debt is reported for its owner and is not
weakened or concealed here.

## Remaining external and formal debt

The repository-local clauses of `DEBT-W1-030` are closed by the executable
offline evaluator, exact synthetic fixture, repository-inert workflow fixture,
disabled activation adapter, deterministic provenance, no-write generator, and
hostile coverage. The central append-only debt ledger is intentionally not
edited in this isolated Story scope.

The following remain external or formal and are not converted into local
success:

- real repository/account/issuer/audience/role and provider trust selection;
- hosted GitHub environment protection and distinct human approval evidence;
- signed OIDC token verification, target federation, bounded live session,
  revocation, provider audit, and rollback evidence;
- credential issuance, assume-role, deployment, staging, release, and
  Production writes;
- formal `TST-026`, hosted CI, and Canonical status transition;
- OD-009, OD-011, OD-013, and OD-015 decisions and their external evidence.
