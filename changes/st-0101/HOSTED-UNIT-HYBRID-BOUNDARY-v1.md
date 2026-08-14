# ST-0101 hosted Unit hybrid boundary — approval handoff

This document explains the inert proposal in
`DESIGN_HANDOFF_V1_ST0101_HOSTED_UNIT_HYBRID_BOUNDARY_V1.yaml`.
It is not an approval record, implementation artifact, CI waiver, release
decision, or authority source.

## Sole approval target

- Path: `changes/st-0101/DESIGN_HANDOFF_V1_ST0101_HOSTED_UNIT_HYBRID_BOUNDARY_V1.yaml`
- Bytes: `22392`
- SHA-256: `d3a644d67e5e96723c10da4cbf9f60323aa4394a89e4edbcd6fc41ed1972a88d`
- Base commit: `3c637fe7fca2905f9036c52371a4c1b2b142f3d0`
- Base tree: `d82b37121326dae67f0172cb174e14156a5a8126`

The Markdown bytes are deliberately not referenced by the YAML. This one-way
relationship prevents an approval cycle. Any YAML byte change creates a new
approval target and requires this document to be updated.

## Why the current hosted Unit job fails

GitHub Actions run `31778682444`, Unit job `94699490419`, terminated with
`23 failed, 1847 passed, 9 skipped` at exact PR head
`d3198fc396e1f2fcb5e557b20fd0025aee9ed64c` over base
`3c637fe7fca2905f9036c52371a4c1b2b142f3d0`.

The failures are not one class:

1. Sixteen behavior/security cases are portable. They currently encounter the
   production physical-root or wrapper guard before reaching their test-owned
   fake transport and assertions.
2. Seven cases are genuinely owner-private. Six verify the untracked
   `raos-ask-pro` Skill or its metadata, and one executes the production launcher
   at physical `/home/minami/rakuten`.
3. Nine existing network-sandbox skips are unrelated. They remain governed by
   `ci-network-assert` and are not added to the owner-private inventory.

## Approved design direction

The repository owner selected option A, the hybrid boundary:

- production root, wrapper, runtime, WSLg, browser, origin, private-file, and
  approval guards stay unchanged;
- hosted CI executes all sixteen portable failures through automatically
  restored test-only substitution or in-process CLI invocation;
- exactly seven irreducible tests use `raos_owner_private`;
- a tracked contract records the full seven node IDs;
- a non-private guard test proves collection and marker equality;
- hosted `ci-unit` excludes only that marker for `tests/st0101`;
- `pro-owner-private-test` executes the exact private selection at the physical
  owner repository and fails when its prerequisites are unavailable.

No Skill, runtime installation, browser profile, secret, prompt, response,
credential, cookie, or session artifact is copied into GitHub Actions.

## Closed implementation slice after exact approval

The YAML authorizes changes to exactly fourteen mutable paths:

1. `Makefile`
2. `pyproject.toml`
3. `changes/st-0101/README.md`
4. `changes/st-0101/hosted-unit-hybrid-boundary.v1.yaml`
5. `docs/execplans/ST-0101.md`
6. `docs/worklogs/ST-0101.md`
7. `tests/st0101/test_chatgpt_pro_browser_selection.py`
8. `tests/st0101/test_chatgpt_pro_initial_ui_settle.py`
9. `tests/st0101/test_chatgpt_pro_interactive_auth_wait.py`
10. `tests/st0101/test_chatgpt_pro_orchestrator.py`
11. `tests/st0101/test_chatgpt_pro_private_runtime.py`
12. `tests/st0101/test_chatgpt_pro_response_wait.py`
13. `tests/st0101/test_chatgpt_pro_wslg_display.py`
14. `tests/st0101/test_hosted_unit_hybrid_boundary.py`

After exact approval, one detached approval record may be added at:

`changes/st-0101/DESIGN-HANDOFF-APPROVAL-HOSTED-UNIT-HYBRID-BOUNDARY-v1.yaml`

The proposal YAML and this Markdown then become immutable inputs. No other path
may change. In particular, the production orchestrator, wrappers, private MCP
runtime, `.codex/config.toml`, `AGENTS.md`, workflows, canonical/status files,
and owner-private Skill tree are protected.

## PR #43 sequencing

PR #43 remains a separate draft at exact head
`3d335574a70aa029cafa32a00712262361d02786`. It has three overlap paths with
this proposal: the ST-0101 README, worklog, and orchestrator tests. It also owns
production typed-composer behavior that this proposal explicitly protects.

The required order is:

1. implement and merge the hosted hybrid-boundary slice;
2. rebase PR #43 onto the resulting `main`;
3. reconcile only the three overlaps without changing either approval scope;
4. rerun PR #43 exact-head, scope, local, and hosted CI audits.

This proposal does not import, cherry-pick, merge, amend, close, or approve PR
#43.

## Evidence boundary

The proposal has no implementation authority until the exact YAML SHA is
approved. Even after implementation, local tests are not formal TST-001,
release, staging, browser/provider, publication, or Production evidence. Push,
PR creation/update, merge, status promotion, and release remain separately
controlled.

## Exact approval statement

To authorize implementation of this exact handoff, reply with:

> SHA-256 d3a644d67e5e96723c10da4cbf9f60323aa4394a89e4edbcd6fc41ed1972a88d の ST0101_HOSTED_UNIT_HYBRID_BOUNDARY_V1 handoff を承認します。
