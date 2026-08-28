# RAOS V2 Phase 0-2 offline vertical slice

## Design authority

- Successor package SHA-256: `7ea856e74d73589ae37d1248e08e685e5d022b90bfc45c9bf1d6cb414b5fc42a`
- Immutable source layer: `changes/raos-v2/source-package/2.0.0-design/**`
- The package prompt was excluded and never executed.
- Clarifications are recorded only in `changes/raos-v2/clarifications.v1.yaml`.

## Decision corrections

- `C-V2-002`: the machine contract has seven templates: HOME, HUB, GUIDE,
  COMPARISON, DIFFERENCE, TOOL and POLICY; source prose referring to six is
  superseded.
- `C-V2-003`: Phase 0 owns T-V2-001..006, T-V2-040 and T-V2-051;
  T-V2-007 starts in Phase 1.
- `C-V2-004`: the effective planning ceilings are P0=16h, P1=40h and P2=80h;
  backlog row estimates are reconciliation data, not additive gates.
- `C-V2-005` + `C-V2-010`: B-V2-009 closes over B-V2-001..008, and the
  corrected Phase 2 exit dependencies are closed before B-V2-034.
- `C-V2-007` + `C-V2-008`: real Phase 0-2 content remains unreviewed and
  unsealed; only synthetic fixtures may seal, and the disabled WordPress
  adapter belongs to Phase 2.

## Delivered

- Phase 0: clean dedicated-worktree baseline, public read-only URL inventory,
  metric/deprecation/rollback contracts and nine required artifacts.
- Phase 1: one carry-on wedge, 25-asset portfolio, seven templates, route/design
  contracts, ten entity schemas and disabled-by-default ports.
- Phase 2: recorded official sources/adapters, deterministic checker and product
  selection, local preview, content/review/media/event contracts, publication
  candidate, migration simulation and evidence bundle.

Evidence bundle SHA-256: `c69a4ac6a857d898ea43d5d69581337188514cb2c4f4bf23baafb052e4310c60`. Recorded local test status is
`PASSED_LOCAL`, browser/a11y evidence is `PASSED_LOCAL`, and independent
manual visual review is `PASSED_LOCAL_MANUAL_VISUAL_REVIEW`. The generator
does not execute either gate; required repository CI remains the merge gate and
is not claimed by this generated body.

## Safety and rollback

The public site and existing URL are unchanged. The real content package is
`EVIDENCE_COMPLETE`, not sealed or published. WordPress is
`DISABLED_DRY_RUN`, Rakuten is `RECORDED_ONLY`, analytics is `LOCAL_SINK_ONLY`,
and normal runtime/test network is denied. Route/canonical/robots rollback was
round-tripped locally against its captured hash binding.

## External/live actions

Publication, deployment, credentials, spending, live provider/WordPress writes,
production migration, policy activation and irreversible deletion:
`NOT_EXECUTED`.
