# ST-0107 pull-request governance candidate

This directory contains the source contract and generated local desired state
for ST-0107. It does not prove that a GitHub repository, team, default branch,
required check, or ruleset exists. The generator has no remote GitHub mutation
path and keeps `generator_remote_mutation: FORBIDDEN`. Any separately reviewed
operator has its own contract and cannot promote this local generation evidence.

## Status labels

- Source contract: `LOCAL_DESIRED_STATE`
- Team bindings: `UNVERIFIED_PLACEHOLDERS`
- Ruleset candidate: `DESIRED_STATE_NOT_API_PAYLOAD`
- Remote application: `NOT_EXECUTED`
- Authenticated read-back and live PR probes: `NOT_EXECUTED`
- Formal TST-001: `NOT_EXECUTED`
- Effective canonical status: unchanged
- ST-0005 authoritative `APPLY` gate: not activated

`desired_enforcement: active` describes the intended state after a future
approved activation. It is not a statement about the current repository.

## Source and generated artifacts

Do not hand-edit generated artifacts. Change the source contract or generator
and regenerate.

| Classification           | Path                                                                 | Role                                                                                 |
| ------------------------ | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Story source             | `changes/st-0107/contracts/pr-governance.v1.yaml`                    | Versioned semantic owner map, PR policy, desired rules, and activation prerequisites |
| Implementation source    | `scripts/build_st0107_pr_governance.py`                              | Strict deterministic validator/renderer with no remote mutation path                 |
| Operator contract        | `changes/st-0107/contracts/github-ruleset-operator.v1.json`          | Fixed host/repository/API, record modes, invariants, and mutation boundary           |
| Operator source          | `scripts/github_ruleset_operator.py`                                 | Hash-bound status/plan/apply/rollback interface; live use remains separately gated   |
| Official-source snapshot | `docs/architecture/ST-0107-github-governance-snapshot.yaml`          | GitHub behavior checked on 2026-08-02; REST API version `2026-03-10`                 |
| Test source              | `tests/st0107/*.py`                                                  | Isolated source/output, negative, determinism, and no-write checks                   |
| Maintained documentation | `docs/execplans/ST-0107.md`, `docs/worklogs/ST-0107.md`, this README | Plan, evidence ledger, and operator boundary                                         |
| Generated candidate      | `.github/CODEOWNERS`                                                 | Path-to-placeholder owner mapping                                                    |
| Generated candidate      | `.github/PULL_REQUEST_TEMPLATE.md`                                   | Short Story/slice, risk, checks, owner-review, and deferred-evidence record          |
| Generated desired state  | `changes/st-0107/ruleset-policy.v1.json`                             | Symbolic review document; explicitly not a GitHub API payload                        |
| Generated inventory      | `changes/st-0107/manifest.yaml`                                      | Pinned source/output hashes and generation metadata                                  |

The immutable canonical examples under `docs/canonical/**` are pinned inputs,
not files to edit. The generator manifest identifies the exact inputs used.

## Local commands

Generate the declared outputs:

```bash
uv run --locked --no-sync python scripts/build_st0107_pr_governance.py
```

Verify exact source pins, output bytes, and hashes without writing:

```bash
uv run --locked --no-sync python scripts/build_st0107_pr_governance.py --check
```

The generator does not accept a repository, token, team ID, check integration
ID, or API endpoint. It must not make network calls or run `gh`, `curl`,
GitHub MCP/App writes, or another remote client. The ruleset JSON deliberately
lacks live numeric bindings and may not be submitted as-is.

The bounded operator is fixed to `https://api.github.com`, `jamozi/rakuten`,
`main`, and REST API version `2026-03-10`. Its credential input is only the
owner-mode-`0600` regular file named by
`RAOS_GITHUB_RULESET_TOKEN_FILE`; the value is never a command argument or
record field. These commands are live GitHub operations and were not executed
for this implementation:

```bash
make github-ruleset-status
make github-ruleset-plan
make github-ruleset-apply \
  GITHUB_RULESET_RUN_ID=<run-id> \
  GITHUB_RULESET_PLAN_SHA256=<plan-sha256>
make github-ruleset-rollback GITHUB_RULESET_RUN_ID=<run-id>
```

The versioned operator contract currently hard-disables `apply` and `rollback`
before credential intake, API reads, or mutation. `UNVERIFIED_PLACEHOLDERS`
would independently fail the owner-binding guard. A future activation must add
a separately reviewed contract for real CODEOWNER identity/permission evidence,
HEAD/live-main binding, pagination, and durable single-attempt serialization.
Planning does not grant apply authority.

## Local candidate semantics

The generated CODEOWNERS candidate selectively covers contract, migration,
security, deployment infrastructure, the shared local Compose
generator, root Compose file, PostgreSQL wrapper, object-storage wrapper and
fixture, application, finance, canonical-document, and `.github/` paths
described by the source contract. All `@raos/*` handles remain placeholders.
GitHub requires an owner team to be visible and to have explicit write
permission; local syntax and generation cannot establish either fact.

There is deliberately no global `*` owner row. A path that matches none of the
declared rows is an ordinary path and does not require CODEOWNER approval.
Contract, migration, security, deployment, and governance paths retain their
specific routes.

Owners listed on one CODEOWNERS line are eligible alternatives. GitHub's code
owner rule does not require every listed team to approve. Before activation, a
matching CODEOWNER and live probes must confirm that contract, migration,
security, deployment, and governance paths receive the intended owner
coverage.

The PR template records the Story or named slice, risk classification,
`make dev-check`, exact-head hosted CI, independent automated review, high-risk
CODEOWNER review or an `N/A` rationale, and deferred formal/live work. Template
completion is evidence metadata; it is not itself an authorization or GitHub
enforcement control.

The ruleset desired state has no bypass actors, targets the symbolic default
branch, blocks deletion and force pushes, requires linear history, stale-review
dismissal, resolved threads, and code-owner review for matching paths. General
approving-review count is zero and last-push approval is disabled. The named
ST-0106, ST-0201 `Database`, ST-0202 `Storage`, and status checks remain
required. Each required check source remains unbound until its real GitHub
Actions integration identity is observed. The Database and Storage jobs' exact
digest-pinned image pulls and container execution are not covered by ST-0106's
denied-network repository-check boundary and remain hosted evidence to obtain.
No hosted Storage run or formal TST-014 result is claimed.

## Live activation runbook boundary

Remote enforcement is forbidden until all six prerequisites have immutable,
sanitized evidence and the matching governance CODEOWNER approves the
high-risk activation change:

1. identify the exact authenticated repository and its actual default branch;
2. resolve every role to a real visible GitHub team with explicit write access
   and review the stable numeric identities;
3. observe each required check succeeding in that repository and capture its
   exact context and expected GitHub Actions App/integration ID;
4. obtain an authenticated ruleset snapshot with parent rules included and
   enough permission to expose the complete bypass-actor state;
5. execute positive and negative probes for ordinary-path zero-approval,
   high-risk CODEOWNER coverage, required checks, stale reviews, unresolved
   threads, direct pushes, deletion, and force pushing; and
6. obtain matching governance CODEOWNER approval and verify by authenticated
   read-back that general approvals are zero, code-owner review is enabled, and
   last-push approval is disabled.

The bounded operator flow remains separate from this generator:

1. recheck the four official GitHub sources and REST API version;
2. bind the authenticated repository, default branch, team IDs, and check
   source IDs into a separately reviewed API payload;
3. compare the payload with repository and inherited rules, showing a
   human-readable diff and proving there are no bypass actors;
4. obtain the matching high-risk governance CODEOWNER review and explicit
   external-operation authorization before any POST or PUT;
5. apply once through the approved GitHub identity, immediately read back the
   effective rules, retain the prior state for rollback, and stop on any
   mismatch; and
6. run the live probes, capture PR/ref/check identifiers and commit SHAs, then
   obtain final human review before proposing formal validation.

Do not commit credentials, tokens, private team membership, or raw privileged
API responses. Store only sanitized evidence and hashes appropriate for review.
Creating a candidate or even activating GitHub rules does not modify
ST-0005's status policy. Enabling the authoritative ST-0005 `APPLY` path would
require its own reviewed policy change and evidence; it is explicitly outside
ST-0107.

## Completion boundary

Deterministic generation, local tests, protected-input checks, capture hashes,
and independent audit may support an `IMPLEMENTED_NOT_VALIDATED` proposal.
They cannot support `VALIDATED`, formal TST-001, or a claim of effective GitHub
enforcement. Those remain `NOT_EXECUTED` until the live activation runbook,
authenticated read-back, real PR probes, and matching high-risk CODEOWNER
review actually complete.
