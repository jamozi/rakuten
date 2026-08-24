# ST-1704 affiliate-learning V2 local completion record

This record will contain local implementation checks only. It cannot establish
formal ST-1704, TST-018, TST-020, TST-032, staging, release, or Production status.

## Implemented boundary

- Generated five-slot measurement contract and immutable predecessor hashes.
- Additive owner-private V2 hash-chain ledger in the existing ST-1704 trust directory.
- Typed search, article, affiliate, outcome, direct reward, unattributed reward,
  work/cost, broken-link, cohort-maturity, and attribution observations.
- Deterministic derived metrics with explicit `UNAVAILABLE` reasons.
- Proposal-only learning report with all editorial/publication mutations disabled.

## Local verification

Exact base: `ed9e3befe225feec26b7f7c3287b68df9028ee44`.

- V2 generator write plus no-write check: pass.
- Existing self-hosted editorial runtime-manifest no-write check after the runbook
  correction: pass.
- Focused V2 tests: `22 passed` (positive calculations, every unavailable state,
  identity/program/unknown-field tamper, replay/conflict/hash-chain tamper, strict
  JSON, owner-private filesystem boundaries, and immutable V1 sentinel).
- Ruff lint and format check: pass for all seven changed Python/test sources.
- Mypy `--strict --explicit-package-bases`: pass for all seven sources.
- In-memory compile check: pass for all seven sources.
- Workspace bootstrap no-write check: pass with zero changes.
- Maintained-file secret-scanner core over the 18 owned files: zero findings.
- `git diff --check` and an explicit no-diff check for tracked
  `operations/measurement-ledger.v1.json`: pass.
- Runtime launcher `doctor` verified its generated manifest and source hashes, then
  returned the expected read-only `STORE_NOT_INITIALIZED`; it created no private
  store and performed no external action.

The affected `tests/st1704` run reached `365 passed, 8 failed`. Every failure is a
`FileNotFoundError` for this linked worktree's intentionally absent physical
`.venv/bin/python`; the failures are limited to predecessor stage-zero/subprocess
tests that construct that exact worktree-local path. The integration owner must rerun
the affected suite and the official worktree secret scan after applying this commit
to a normal checkout with its physical locked `.venv`. The official scanner itself
also rejects linked-worktree `.git` pointer files as `unsafe-git-metadata`; the owned
file scan above used the same scanner rules and safe reader without elevating it to
formal evidence. These are environment verification items, not introduced runtime
or contract debt.

## Remaining external/formal work

- Real provider report/schema proof (OD-003), analytics/privacy activation (OD-012),
  formal suites, staging/browser/live evidence, publication, release, and Production.
