# RAOS-DATA-001 Migration Playbook

Version `0.1` / `2026-07-30`

## 1. Purpose

Codexおよび人間開発者が、PostgreSQL変更を安全・可逆・監査可能に実施するための手順を定義する。Baseline SQLは参照正本であり、実装RepositoryではAlembic revisionへWave単位で分割する。

## 2. Non-negotiable rules

1. Production DBへ手動DDLを直接投入しない。緊急変更もincident IDとfollow-up migrationを必須にする。
2. Migration PRはApplicationの旧版・新版の両方と互換なExpand stateから開始する。
3. Destructive changeはBackfill、Read cutover、観測期間、Contract approval後にのみ実施する。
4. Table rewrite、長時間AccessExclusive lock、replica lag、WAL爆発の可能性を事前評価する。
5. `lock_timeout`を短く設定し、待ち続けるMigrationではなく安全に失敗するMigrationにする。
6. Migration実行中に外部API、LLM、Object Storage処理を呼ばない。
7. DDL、data migration、projection rebuildを必要に応じて別Revision/Jobへ分離する。

## 3. Revision naming

`YYYYMMDDHHMM_<wave>_<imperative_description>.py`。例: `202608010900_mig003_create_catalog_observations.py`。Revision metadataへRequirement IDs、Architecture slice、risk class、estimated lock、backfill job、rollback categoryを記載する。

## 4. Change classes

| Class | Example | Default procedure | Rollback |
|---|---|---|---|
| A — additive | nullable column, new table, new nonunique index | expand | schema downgrade usually allowed |
| B — validated additive | NOT NULL, FK, CHECK, unique | add unvalidated/index, backfill, validate | remove new constraint after app rollback |
| C — semantic | enum/status meaning, calculation version | dual support and versioned data | forward correction preferred |
| D — destructive | drop/rename/type rewrite | expand/migrate/contract across releases | restore/forward fix; no instant downgrade assumption |
| E — privacy/retention | delete/anonymize | dry run + approval + legal hold check | generally irreversible; backup/hold required |

## 5. Expand–migrate–contract

### 5.1 Add a required column to a large table

1. Add nullable column without volatile default.
2. Deploy application dual-write with telemetry.
3. Backfill in bounded primary-key/time windows with pause/resume checkpoint.
4. Verify zero NULL and semantic reconciliation.
5. Add CHECK `column IS NOT NULL` as `NOT VALID` when appropriate; validate separately.
6. Convert to `SET NOT NULL` using the validated proof where supported.
7. Remove old write path only after one full release observation window.

### 5.2 Add a foreign key

1. Create the referencing index, `CONCURRENTLY` in production if table is large.
2. Detect/repair orphan rows.
3. `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY ... NOT VALID`.
4. `VALIDATE CONSTRAINT` in a controlled window.
5. Add permission/integration tests and update generated catalog.

### 5.3 Add uniqueness

1. Query and remediate duplicates with an auditable plan.
2. Create unique index concurrently.
3. Attach as a constraint using the existing index where a named constraint is required.
4. Never add a large blocking UNIQUE constraint without a lock/replica impact rehearsal.

### 5.4 Rename or split a column

Add new column → dual-write → backfill → compare → read-new fallback-old → read-new only → stop old write → contract later. Direct rename is limited to private, single-release, demonstrably unused columns.

### 5.5 Change data type

Avoid in-place rewrite on large tables. Add new typed column, batch convert with error quarantine, dual-write, validate, cut over, then drop old in a later release.

### 5.6 Introduce partitioning

Create partitioned successor, copy by closed time ranges, dual-write or logical replication, reconcile count/hash, cut over through view/name swap in controlled downtime, retain old table read-only until acceptance. Prove partition pruning and FK/unique behavior first.

## 6. Migration waves

### MIG-001 — Foundation schemas and shared operations

- Schemas: ops, iam
- Depends on previous wave: no
- Architecture slices: SLICE-003, SLICE-004, SLICE-005, SLICE-007
- Exit: upgrade/downgrade test, generated catalog drift=0, permission tests, representative fixtures, post-deploy SQL pass.

### MIG-002 — Portfolio planning

- Schemas: portfolio
- Depends on previous wave: yes
- Architecture slices: SLICE-006
- Exit: upgrade/downgrade test, generated catalog drift=0, permission tests, representative fixtures, post-deploy SQL pass.

### MIG-003 — Rakuten catalog and observations

- Schemas: catalog
- Depends on previous wave: yes
- Architecture slices: SLICE-008, SLICE-009
- Exit: upgrade/downgrade test, generated catalog drift=0, permission tests, representative fixtures, post-deploy SQL pass.

### MIG-004 — Evidence lineage

- Schemas: evidence
- Depends on previous wave: yes
- Architecture slices: SLICE-010
- Exit: upgrade/downgrade test, generated catalog drift=0, permission tests, representative fixtures, post-deploy SQL pass.

### MIG-005 — AI and structured editorial

- Schemas: ai, editorial
- Depends on previous wave: yes
- Architecture slices: SLICE-011, SLICE-012
- Exit: upgrade/downgrade test, generated catalog drift=0, permission tests, representative fixtures, post-deploy SQL pass.

### MIG-006 — Policy, human approval, and publication

- Schemas: policy, publishing
- Depends on previous wave: yes
- Architecture slices: SLICE-013, SLICE-014, SLICE-015
- Exit: upgrade/downgrade test, generated catalog drift=0, permission tests, representative fixtures, post-deploy SQL pass.

### MIG-007 — Public projection and freshness

- Schemas: readmodel, freshness
- Depends on previous wave: yes
- Architecture slices: SLICE-016, SLICE-018, SLICE-022
- Exit: upgrade/downgrade test, generated catalog drift=0, permission tests, representative fixtures, post-deploy SQL pass.

### MIG-008 — Analytics and finance

- Schemas: analytics, finance
- Depends on previous wave: yes
- Architecture slices: SLICE-017, SLICE-019, SLICE-020, SLICE-021
- Exit: upgrade/downgrade test, generated catalog drift=0, permission tests, representative fixtures, post-deploy SQL pass.

### MIG-009 — Operational hardening and validation

- Schemas: ops, iam, portfolio, catalog, evidence, editorial, ai, policy, publishing, freshness, analytics, finance, readmodel
- Depends on previous wave: yes
- Architecture slices: SLICE-023, SLICE-024, SLICE-025
- Exit: upgrade/downgrade test, generated catalog drift=0, permission tests, representative fixtures, post-deploy SQL pass.

## 7. Production execution checklist

### Before

- Approved PR, release/incident ID, owner, observer, rollback decision point.
- Fresh backup/PITR confirmed; restore procedure and object artifact availability checked.
- `pg_stat_activity`, long transactions, replica lag, table/index size, bloat, lock graph captured.
- Query and job load window selected; autoscaling/connection pool limits reviewed.
- Estimated rows, WAL, runtime, lock type, statement/lock timeout documented.

### During

- Run with dedicated migrator identity and captured stdout/stderr.
- Monitor locks, blocked sessions, replica lag, CPU, storage, IOPS, WAL, error rate.
- Abort at predefined threshold; do not improvise destructive remediation.
- Batch backfill uses idempotent checkpoints and commits small windows.

### After

- Run `RAOS_03_004_post_deploy_validation_v0.1.sql`.
- Compare schema digest, row counts, DQ rules, business reconciliation, query plans.
- Deploy/read both versions as planned; observe at least one normal workload cycle.
- Record release and migration revision in `ops.release`; attach validation artifact.

## 8. Rollback philosophy

- Additive schema rollback is allowed only if no newer writer depends on it.
- Data corrections and append-only events use compensating forward records rather than history deletion.
- Published content rollback switches immutable Snapshot pointer; it never edits the previous Snapshot.
- Finance import rollback marks/reverses canonical events with correction lineage; source artifact remains.
- Irreversible privacy deletion requires restore escrow/hold decision before execution, not after.

## 9. Codex acceptance prompt fragment

```text
Implement only the assigned MIG wave. Read RAOS-REQ-001, RAOS-ARCH-001, RAOS-DATA-001, the YAML catalog, and migration playbook first.
Do not change table semantics or weaken constraints to make tests pass. Do not add secrets, review bodies, affiliate-rate fields to editorial/readmodel, or public access to internal schemas.
Produce Alembic upgrade/downgrade, SQLAlchemy models, unit/integration/permission tests, fixture factories, generated-catalog drift test, and a migration risk note.
Run fresh-install, upgrade-from-previous, downgrade where supported, duplicate-delivery, concurrency, and post-deploy validation tests. Stop after one PR-sized wave.
```

## 10. Required production rehearsal

Baseline package was statically generated and validated in this environment; a live PostgreSQL server was not available here. Before merge, CI must execute all SQL against PostgreSQL 18.4, and before production, the same migration must be rehearsed on a recent production-size snapshot with masked/restricted data handling.
