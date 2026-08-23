# ST-1703 ambiguous draft recovery worklog

Scope: `ST-1703 / SELF_HOSTED_AMBIGUOUS_DRAFT_RECOVERY_V1` only.

## Preflight

1. Story and objective: add one explicit human-invoked recovery command for
   the exact self-hosted `CREATE_DRAFT` pending journal without enabling an
   automatic retry, publication, or a generic WordPress client.
2. Read inputs: Canonical integration priority and publication boundary,
   Canonical decisions/open decisions, the ST-1703 backlog entry,
   TST-021/TST-022/TST-032, relevant secret/audit controls, the existing
   self-hosted DESIGN_HANDOFF, content loader, pure REST values, credential
   store, HTTPS adapter, durable journal, CLI/launcher/Make runtime binding,
   runbook, and focused tests.
3. Ambiguities: no Canonical publication or provider decision is resolved.
   The local amendment uses the documented no-blind-retry safe boundary: one
   strict official REST collection read precedes either zero POSTs or one final
   existing create request. Live execution remains a separate owner action.
4. Planned files: one new DESIGN_HANDOFF, self-hosted domain/port/REST/HTTPS/
   journal source, CLI/launcher/Make allowlists, runtime-manifest generator and
   generated bindings, Story README/runbook, and isolated fake-only tests.
   No migration or public contract is added.
5. Planned checks: focused recovery/journal/HTTPS/REST/CLI/runtime tests,
   existing create no-retry regression, parse/import, Ruff, type checks, shell
   syntax, runtime-manifest no-write check, sensitive-data scan, and
   `git diff --check`.
6. Out of scope: `.secrets` inspection or repair, credential entry, network or
   live WordPress calls, browser automation, role changes, draft publication,
   update/delete/media/theme/plugin/taxonomy/publicize, hosted CI, staging,
   release, Production, and ST-1704.

## Implementation notes

Implemented one separate `recover-create-draft` state machine. The existing
`create-draft` adapter and its pending-journal no-retry decision remain intact.
Recovery requires the exact current pending create, durably publishes an
origin-hash/candidate-hash/journal-integrity-bound private intent before the
credential value or network can be reached, and then consumes the path for all
terminal, refusal, mismatch, ambiguous, and interrupted outcomes.

The recovery transport has one method and one request shape: an authenticated
fixed-origin Posts collection GET. Its exact empty proof permits one call to
the existing create adapter; one exact draft instead reconciles locally with
zero POSTs. No response body, raw request path, origin URL, title, slug,
content, credential, Authorization header, or private pathname enters the
sidecar or CLI output. No publish/update/delete/media/theme/plugin/taxonomy/
publicize capability was added, and `doctor` does not call recovery.

## Local evidence

- Focused recovery/HTTPS/journal/CLI/REST tests: `195 passed, 1 skipped`. The
  skip is the existing exact-root launcher check reserved for post-integration
  execution; all fake recovery tests ran.
- Complete isolated `tests/st1703` suite: `1232 passed, 1 skipped` for the same
  exact-root reason.
- Runtime identity suite: `79 passed`.
- Ruff lint and format checks passed for all changed Python source and tests.
- Strict mypy passed for the seven changed runtime/generator source files;
  project Pyright reported `0 errors, 0 warnings`.
- Bash and BusyBox shell syntax checks passed.
- The runtime manifest was regenerated through its owner generator; the
  subsequent no-write check passed.
- Theme source, workspace drift, Canonical import verification, YAML parse,
  and `git diff --check` passed.
- The project scanner engine reported zero findings across the exact changed
  files under this slice.

## Deferred verification ledger

- Command: project worktree/history secret scan with the reviewed-findings
  ledger. Observed result: closed refusal `unsafe-git-metadata` in the linked
  worktree. Affected owner artifact: repository Git metadata boundary.
  Introduced by: not introduced by ST-1703; this is the known linked-worktree
  scan limitation. Closure: integration owner reruns the standard scan from a
  supported physical/exact-root checkout. Safe impact: the same scanner engine
  completed the exact changed-file scan with zero findings, and no live action
  is authorized by this local evidence.
- Exact-root launcher/doctor evidence remains for the integration owner after
  the commit is integrated into the clean physical repository. No credential
  read, network/provider call, browser action, draft write, publication,
  formal TST, hosted CI, staging, release, or Production operation was run.

These local results are implementation evidence only and are not promoted to
formal TST, live-provider, publication, staging, release, or Production
evidence.
