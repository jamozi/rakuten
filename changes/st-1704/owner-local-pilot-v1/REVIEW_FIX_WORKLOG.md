# ST-1704 owner-local pilot review/fix worklog

## Initial implementation

- Exact base: `ea79430136b3d3384e0b1208eadf3097cece6d3c`.
- Scope: `ST1704_OWNER_LOCAL_PILOT_LEDGER_V1` only.
- Publication/runtime facts are intentionally absent from tracked artifacts.
- Formal TST, browser, provider, analytics activation, release, and Production remain unexecuted.

## Independent review

- The checkpoint review identified launcher/runtime binding, field-aware metric,
  temporal, filesystem transaction, generator transaction, finance-separation,
  verified-root binding, and exact sequence-type gaps.
- The frozen final diff closed every listed P1/P2 finding. An independent
  read-only closure pass reported no remaining P1/P2 among those exact items;
  `tests/st1704` passed with 104 tests and `git diff --check` passed.
- This is local implementation review evidence only. Formal ST-1704 and
  TST-018/TST-020/TST-032 remain NOT_STARTED/NOT_EXECUTED.

## Derived cumulative manifest reconciliation

- Root `Makefile` now routes the isolated ST-1704 suite and runtime-manifest
  check through Base CI. Its associated workflow-contract test also changed.
- `scripts/build_local_compose.py` treats both files as cumulative ST-0202
  provenance inputs, so the pinned uv 0.12.1 generator updated only their byte
  counts and SHA-256 values in `changes/st-0202/manifest.yaml`.
- `docker-compose.yml` was byte-identical and was not changed. This derived
  provenance refresh does not alter ST-0201/ST-0202 runtime behavior or claim
  formal database/storage evidence.
- Local reconciliation checks passed: cumulative generator `--check`, 139
  ST-0201 tests with one Docker-dependent skip, 329 ST-0202 tests, 104 ST-1704
  tests, and 374 ST-0106 workflow-contract tests. The Docker skip keeps formal
  ST-0201 runtime/TST-008 evidence explicitly unexecuted.
