# ST-0503 V2 local implementation preflight

- Story: `ST-0503` — deterministically normalize exact persisted ST-0502 V2
  pages into durable candidate, offer, source-snapshot, and observation records.
- Read inputs: Canonical integration priority and decisions, ST-0503 backlog row,
  FR-003/FR-004 traceability, TST-005/TST-007/TST-008 definitions, OD-006,
  RAOS-DATA-001 catalog tables and transaction rules, RAOS-SEC-001 and its
  data/control catalogs, ST-0308 persistence runtime boundary, the ST-0502 V2
  contract, domain values, ports, application service, and owner-private SQLite
  archive.
- Open decision: OD-006 remains blocking and unresolved. Every identity result
  is `HUMAN_REVIEW` / `NOT_READY`; no automatic product merge, split, canonical
  identity, confidence shortcut, or grouping proposal is implemented.
- Planned owned files: additive ST-0503 V2 Domain/Port/Application/Adapter,
  Story-local tests, a closed JSON contract and synthetic fixture, deterministic
  owner generator, generated projection, manifest, and local completion record.
- Local checks: V1+V2 ST-0503 suites, ST-0502 and ST-0308 affected regressions,
  owner `--check`, Ruff format/lint, strict mypy, pinned Pyright, compile/import,
  focused secret/static/denied-network checks, and `git diff --check`.
- Out of scope: PostgreSQL/formal TST execution, live Rakuten/provider or
  credential access, object-cloud storage, worker activation, identity approval,
  recommendation/ranking, publication, staging, release, and Production.
