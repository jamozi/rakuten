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

- Root `Makefile` routes the isolated ST-1704 suite and runtime-manifest check
  through Base CI. The final check now uses a fixed `env -i` environment and
  the exact `.venv/bin/python` launcher because uv 0.12.1 resolves the command
  name `python` to `.venv/bin/python3`, which the strict verifier correctly
  rejects. ST-0106 and ST-1704 contract tests pin this launcher boundary.
- The final `Makefile` and workflow-test hashes were reconciled with only the
  existing owner generators. Dependency order was ST-0107, cumulative
  ST-0202, ST-0203, ST-0204, ST-0205, ST-0305, ST-0306, ST-0307, ST-0701,
  ST-0801, then ST-0703. Reviewed predecessor pins and derived contract hashes
  changed only where a generator requires exact predecessor binding.
- `docker-compose.yml`, the ST-0204 runtime schema, ST-0205 fixture payloads,
  ST-0305/ST-0306 migration and validation payloads, ST-0307 SQL fixtures, the
  ST-0701 registry payload, and all ST-0801 semantic bindings remained
  byte-identical. The ST-0307 catalog and ST-0703 registry changed only their
  generated source-hash provenance fields.
- Exact uv 0.12.1 offline `ci-repository-policy` passed after the dependency
  cascade. Isolated local suites passed: ST-0106 375; ST-0107 93; ST-0201 139
  with one Docker-dependent skip; ST-0202 329; ST-0203 55; ST-0204 178;
  ST-0205 112; ST-0701 117; ST-0703 363; ST-0801 283; and ST-1704 104.
  ST-0301 through ST-0307 also passed their non-runtime assertions with 93,
  22, 26, 41, 6, 6, and 14 passes respectively; their 30, 25, 50, 16, 35,
  13, and 10 PostgreSQL-dependent skips keep exact PostgreSQL 18.4 runtime and
  formal migration evidence explicitly unexecuted.
- This mechanical reconciliation does not alter runtime behavior, activate a
  provider, publish content, or establish formal TST, release, or Production
  evidence.
