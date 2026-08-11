# RAOS Pro branch integration — 2026-08-11

## Scope and authority

This worklog records the owner-approved mechanical reconciliation performed in
the isolated worktree
`/home/minami/rakuten/.worktrees/pro-consolidation-20260811` on branch
`codex/pro-consolidation-20260811`. It implements the consolidation slice in
`docs/execplans/RAOS-IMPLEMENTATION-FIRST.md`; it is not new design authority,
formal CI evidence, release authority, or permission for live, staging, or
Production activity.

The integration branch started clean at exact `origin/main`
`48a807672caa845df8e0251782f00bce8040663b`. The branch was then fast-forwarded
with `git merge --ff-only` to local Goal head
`7b57c9b69c903cf40c426fe73eaf597fa97437c3`. Git confirmed that the main SHA is
an ancestor of the Goal SHA and that the range contains exactly 95 commits.
The Goal history was not flattened, rebased, or duplicated.

## Source refs and decisions

| Source | Exact ref | Classification | Result and reason |
|---|---|---|---|
| Main baseline | `48a807672caa845df8e0251782f00bce8040663b` | baseline | Superseded only by the approved fast-forward to Goal. |
| Goal | `7b57c9b69c903cf40c426fe73eaf597fa97437c3` | adopted baseline | Preserved all 95 descendant commits and all approved Story history. |
| Current Pro line base | `2ab6a136748aa6af8fce3e108d52382996160315` | comparison base | Used only to classify the 63 paths in the current-line delta. |
| Current Pro line | `d7b2252c40006d36be6ae29228ca7c285c57d976` | adopted and reconciled | Its delta was classified as 42 d7b-only paths and 21 Goal-overlap paths. |
| Current ST-0705 | `a9be3c28c8221ec200879b9f9e98e91dfb8e5219` | excluded duplicate | All nine changed paths were byte-identical to Goal; replay would duplicate no behavior. |
| Final ST-0703 line | `2599bef21a17bcd3bc785af3bcf9885c94a077f5` | source-test correction only | Adopted only the four mixed-case forbidden-canary replacements in `tests/st0703/test_generation.py`; its manifest was not copied. |
| Switchboard line | `b12741172aa85bfbb622df444ed8deef2af82f4e` | excluded | No approved switchboard design was part of this slice. No switchboard package, CLI, or profiles were imported. |
| Materialize/export/source branches | not imported | excluded | No `.github` or branch-materialization content was copied, per owner direction. |

No `.github/**` path and no `python/raos/strategy_switchboard/**` path differs
from the Goal baseline on this integration branch.

## Current-line path classification

The exact 42 paths changed only by `d7b2252` were:

```text
AGENTS.md
changes/st-0101/README.md
changes/st-0101/design-handoff.advanced-button-priority.v1.yaml
changes/st-0101/design-handoff.bound-response-action-diagnostics.v1.yaml
changes/st-0101/design-handoff.bound-response-closed-diagnostics.v1.yaml
changes/st-0101/design-handoff.bound-response-heading-attributes.v1.yaml
changes/st-0101/design-handoff.bound-response-heading-diagnostics.v1.yaml
changes/st-0101/design-handoff.bound-response-precontent-actions.v1.yaml
changes/st-0101/design-handoff.bound-response-precontent-container-shape-diagnostics.v1.yaml
changes/st-0101/design-handoff.bound-response-precontent-context-diagnostics.v1.yaml
changes/st-0101/design-handoff.bound-response-precontent-invalid-diagnostics.v1.yaml
changes/st-0101/design-handoff.bound-response-precontent-ref-free-content.v1.yaml
changes/st-0101/design-handoff.bound-response-recovery.v1.yaml
changes/st-0101/design-handoff.bound-response-ref-free-entry-diagnostics.v1.yaml
changes/st-0101/design-handoff.bound-response-ref-free-fallback-diagnostics.v1.yaml
changes/st-0101/design-handoff.bound-response-ref-free-silent-presentation-wrapper.v1.yaml
changes/st-0101/design-handoff.closed-selector-diagnostics.v1.yaml
changes/st-0101/design-handoff.hybrid-summary-priority.v1.yaml
changes/st-0101/design-handoff.resilient-pro-review.v1.yaml
changes/st-0101/design-handoff.role-scoped-summary-correction.v1.yaml
changes/st-0101/design-handoff.semantic-summary-evidence.v1.yaml
changes/st-0101/design-handoff.summary-verified-pro-answer.v1.yaml
docs/worklogs/ST-0101.md
scripts/chatgpt_pro_mcp.sh
scripts/chatgpt_pro_mcp_runtime/expected-runtime-inventory.v1.json
scripts/chatgpt_pro_mcp_runtime/package-lock.json
scripts/chatgpt_pro_mcp_runtime/package.json
scripts/chatgpt_pro_mcp_runtime/verify_runtime.py
scripts/chatgpt_pro_orchestrator.py
scripts/chatgpt_pro_workflow.py
tests/st0101/test_chatgpt_pro_bound_response_recovery.py
tests/st0101/test_chatgpt_pro_browser_selection.py
tests/st0101/test_chatgpt_pro_current_response.py
tests/st0101/test_chatgpt_pro_current_ui.py
tests/st0101/test_chatgpt_pro_initial_ui_settle.py
tests/st0101/test_chatgpt_pro_interactive_auth_wait.py
tests/st0101/test_chatgpt_pro_orchestrator.py
tests/st0101/test_chatgpt_pro_private_runtime.py
tests/st0101/test_chatgpt_pro_resilient_review.py
tests/st0101/test_chatgpt_pro_response_wait.py
tests/st0101/test_chatgpt_pro_workflow.py
tests/st0102/test_toolchain_contract.py
```

All 42 path selections were applied during reconciliation. Two mechanical
integration corrections were then made against the cumulative Goal baseline:

- In `scripts/chatgpt_pro_orchestrator.py`, a generic local variable named
  `token` was renamed to `attribute_token` so the maintained-file secret scan
  does not misclassify code syntax. Behavior and parser boundaries are
  unchanged.
- The d7b-only deletion of the two `openai==2.52.0` expectations in
  `tests/st0102/test_toolchain_contract.py` was incompatible with the approved
  Goal ST-0703 runtime dependency. The exact cumulative OpenAI expectations
  were restored, and the pinned Python wrapper suite passed all 48 ST-0102
  tests. The final file therefore intentionally matches Goal for those two
  lines rather than preserving a failing fork-only expectation.

The exact 21 paths changed on both d7b and Goal were:

```text
Makefile
README.md
changes/st-0107/manifest.yaml
changes/st-0202/README.md
changes/st-0202/manifest.yaml
changes/st-0204/README.md
changes/st-0204/manifest.yaml
changes/st-0701/manifest.yaml
changes/st-0703/README.md
changes/st-0703/contracts/openai-responses-adapter.v1.yaml
changes/st-0703/generated/recorded-fixture-registry.v1.json
changes/st-0703/manifest.yaml
changes/st-0801/manifest.yaml
scripts/build_st0703_recorded_adapter.py
scripts/object_storage_service.sh
scripts/run_network_denied.sh
tests/st0106/test_network_isolation.py
tests/st0106/test_workflow_contract.py
tests/st0202/test_fixture.py
tests/st0202/test_wrapper.py
tests/st0703/test_generation.py
```

Eighteen of those paths were already byte-identical at the two source refs and
were retained once. The three different paths were reconciled as follows:

- `Makefile`: retained Goal OIDC targets and added the d7b Pro runtime-install
  and displayed-response-import targets and variables.
- `changes/st-0703/manifest.yaml` and `changes/st-0801/manifest.yaml`: neither
  candidate byte sequence was copied; each was regenerated by its owner from
  the frozen final sources.

The following seven generated candidates were never copied from d7b or the
final ST-0703 ref:

```text
changes/st-0107/manifest.yaml
changes/st-0202/manifest.yaml
changes/st-0204/manifest.yaml
changes/st-0701/manifest.yaml
changes/st-0703/generated/recorded-fixture-registry.v1.json
changes/st-0703/manifest.yaml
changes/st-0801/manifest.yaml
```

## Source freeze and owner regeneration

After the final source/test freeze, owner generators were run in dependency
order and then rerun in no-write mode:

1. ST-0107 PR governance;
2. cumulative ST-0202 local Compose;
3. ST-0203 local queue and ST-0205 synthetic data;
4. ST-0204 runtime configuration;
5. ST-0306 cumulative migration metadata and ST-0307 migration fixtures;
6. ST-0701 AI registry and ST-0801 content AST;
7. ST-0703 recorded adapter registry and installed-artifact check.

This closed the owner-supported predecessor hash fan-out through ST-0202,
ST-0203, ST-0204, ST-0205, ST-0306, ST-0307, ST-0701, ST-0703, and ST-0801.
The ST-0703 contract retained its approved recorded-only semantics while its
predecessor hashes, semantic projection guard, source contract hash, registry,
and manifest were mechanically rebound. No recorded fixture payload or runtime
schema changed.

The legacy ST-0305 CLI intentionally delegates to the cumulative ST-0306
owner. Its direct historical `render_outputs()` assertion still observes the
pre-existing predecessor-owned manifest drift recorded in the implementation
debt ledger. The integration did not bypass that owner entrypoint or hand-edit
the historical generated file.

## Local commits

- `86cd3c6` — `Reconcile current ST-0101 Pro tooling`
- `c587839` — `Reconcile ST-0703 provenance canaries`
- `10dd666` — `Refresh reconciled owner provenance`
- `ccc33e4` — `Close transitive owner provenance`

The final full commit IDs are reported by the integration handoff because the
last worklog commit cannot safely embed its own recursively changing SHA.

## Verification

All claims below are local WSL/Linux evidence only.

### Passing checks

- Focused ST-0101/current-response/recovery/private-runtime plus ST-0703 canary
  selection: `141 passed`.
- Final affected Story suites:
  - ST-0102 pinned-wrapper suite: `48 passed`;
  - ST-0106: `307 passed`;
  - ST-0107: `93 passed`;
  - ST-0202: `156 passed`;
  - ST-0203: `55 passed`;
  - ST-0204: `178 passed`;
  - ST-0205: `112 passed`;
  - ST-0701: `117 passed`;
  - ST-0703: `363 passed`;
  - ST-0801: `283 passed`;
  - ST-0301: `93 passed, 30 skipped`;
  - ST-0302: `22 passed, 25 skipped`;
  - ST-0303: `26 passed, 50 skipped`;
  - ST-0304: `41 passed, 16 skipped`;
  - ST-0306: `6 passed, 13 skipped`;
  - ST-0307 without its PostgreSQL module: `14 passed`.
- PostgreSQL skips require the exact local PostgreSQL 18.4 runtime through
  `RAOS_PG_BIN`; no live database claim is made.
- Pinned Python gate through
  `/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv`: exact uv 0.12.1,
  CPython 3.14.6, Ruff 0.16.1, mypy 2.3.0, repository Ruff lint, formatter
  check over 182 files, strict configured mypy over 110 source files, and the
  48-test ST-0102 suite all passed.
- ST-0703 strict static gate: Ruff lint/format and strict mypy over 11 owned
  source/test files passed.
- Changed Python imports and shell syntax checks passed.
- `make ci-repository-policy` passed after the final dependency-order
  regeneration. It included canonical import verification (`105` imported
  files and `104` verified package checksums), ST-0002 through ST-0005 checks,
  the expected ST-0006 decision evaluation, ST-0107, and all active owner
  no-write gates listed above.
- `make check-workspace` passed with `changed: []` and 42 workspace
  directories.
- Direct Node 24.18.1 syntax checks passed for `eslint.config.mjs`,
  `prettier.config.mjs`, and `scripts/node_inventory.mjs`.
- `git diff --check` and the final ref/path scope review passed.

### Environment and inherited limitations

- The complete ST-0101 suite reported `1877 passed, 2 failed`. Both failures
  are linked-worktree path constraints, not behavior failures:
  `test_make_config_agents_and_skill_retain_approved_policy` sees the owner
  config pinned to `/home/minami/rakuten`, and
  `test_make_pro_launcher_ignores_wrong_ambient_uv_and_setup_uses_it` correctly
  rejects a launcher outside the physical owner repository. The integration
  owner should rerun these two checks in the main checkout.
- The ST-0305 suite reported `3 passed, 35 skipped, 1 failed` at
  `test_rendered_catalog_and_committed_outputs_have_exact_inventory` because
  of the already-recorded historical ST-0305 manifest drift. Its public CLI
  delegates to ST-0306; no unsupported legacy write was performed.
- Exact direct version observations were Node `v24.18.1` and npm `11.16.0`
  using
  `/home/minami/.local/share/raos-toolchains/npm/11.16.0/node_modules/npm/bin/npm-cli.js`.
  The repository Node wrapper exited `69` because it requires npm to be
  bundled beneath the selected Node prefix, while that Node installation's
  bundled npm is 12.0.2. `node_modules` was absent, so ESLint, TypeScript,
  Pyright, and Vitest wrapper evidence was not claimed. The wrapper was not
  weakened and npm 12.0.2 was not used as validation evidence.
- The official `scripts/scan_secrets.py --worktree` command exited `2` with
  `ERROR code=unsafe-git-metadata source="."` because this is a linked
  worktree. A scanner-equivalent maintained-file pass over the 66 changed
  paths found zero findings. A full fallback maintained-file scan inspected
  3,429 paths and found only two unchanged Goal-baseline generic-code
  classifications at `scripts/validate_st0308_design_handoff.py:1632` and
  `tests/st0308/conftest.py:647`.

## Debt and completion boundary

No new implementation debt was introduced by this reconciliation, so
`docs/worklogs/RAOS-IMPLEMENTATION-DEBT.md` was not appended or otherwise
modified. The linked-worktree scanner limitation remains inherited
`DEBT-W0-003`; the ledger already records the predecessor-owned ST-0305 drift.

No formal CI, live Pro/browser run, provider call, PostgreSQL runtime,
publication, staging, release, or Production action was performed. Canonical
status truth and generated status output were not changed. This worklog claims
only a locally reconciled integration branch with owner-supported generated
artifacts current at its source freeze.
