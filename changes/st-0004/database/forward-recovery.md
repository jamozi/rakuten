# ST-0004 database forward recovery

ST-0004 uses the inherited six-phase ABI: Expand (`013`), online validation
and indexes (`014`), repeatable Migrate (`015`), Contract prepare (`016`),
Contract finalize (`017`), and guarded downgrade (`018`). The SQL proposal
`RAOS_06_001_data_alignment_patch_v0.1.sql` is design input only. Never execute
it, copy it into migration history, or edit an already applied migration.

The formal overlay has four canonical `editorial.article_version` bindings:
Content Schema Version, Article Type Version, Article Template Version, and
same-article SEO Metadata Version. The legacy integer
`content_schema_version` is not evidence for any UUID binding.

The final four bindings are `NOT NULL`. New Article Version and SEO Metadata
Version rows therefore use preallocated UUIDs and one transaction; their two
foreign keys are `DEFERRABLE INITIALLY DEFERRED`, so either insert order is
valid and the same-article pair is enforced at commit. Do not force either
constraint immediate between those inserts.

## Recovery rule

Recover forward with the same reviewed SQL whenever persisted ST-0004 data
exists. `018` is only a pre-data escape hatch: it acquires exclusive locks and
refuses to run if any ST-0004 table or any of the four binding columns contains
data. Do not disable that guard, use `CASCADE`, null bindings, or delete content
to force a downgrade. A required data transformation belongs in a new change
with its own backup, review, checkpoint, and rollback contract.

Run every file with PostgreSQL 18 and `ON_ERROR_STOP` enabled. Do not wrap
`014` in an outer transaction because `CREATE INDEX CONCURRENTLY` requires
autocommit.

```bash
psql --set=ON_ERROR_STOP=1 --file=changes/st-0004/database/202607300013_content_expand.sql
psql --set=ON_ERROR_STOP=1 --file=changes/st-0004/database/202607300014_content_expand_validate.sql
psql --set=ON_ERROR_STOP=1 --file=changes/st-0004/database/202607300015_content_migrate_batch.sql
psql --set=ON_ERROR_STOP=1 --file=changes/st-0004/database/202607300016_content_contract_prepare.sql
psql --set=ON_ERROR_STOP=1 --file=changes/st-0004/database/202607300017_content_contract.sql
```

## Failure checkpoints

### `013` Expand

`013` is one transaction. Any error rolls the whole phase back. Confirm that
all eleven ST-0004 tables and all four UUID binding columns are absent, correct
the predecessor drift, and rerun `013`. If any owned object remains, stop and
investigate migration history instead of dropping an object by name alone.

### `014` online indexes

The four foreign keys validate in the first transaction. Each concurrent index
then commits independently, so an interruption can leave valid earlier indexes
or an invalid current index. The file deliberately refuses partial state.
Inventory only ST-0004-owned candidates first:

```sql
SELECT index_ns.nspname AS index_schema,
       index_class.relname AS index_name,
       index_data.indisvalid,
       index_data.indisready,
       pg_get_indexdef(index_data.indexrelid) AS definition
  FROM pg_index AS index_data
  JOIN pg_class AS index_class
    ON index_class.oid = index_data.indexrelid
  JOIN pg_namespace AS index_ns
    ON index_ns.oid = index_class.relnamespace
 WHERE index_ns.nspname IN ('editorial', 'evidence')
   AND index_class.relname LIKE '%\_st0004' ESCAPE '\\'
 ORDER BY 1, 2;
```

Compare every definition with `014`. After review, drop only the verified
ST-0004-owned partial indexes, using `DROP INDEX CONCURRENTLY` one at a time and
outside a transaction. Then rerun the whole `014`; it revalidates already-valid
foreign keys safely and reconstructs all 29 indexes.

### `015` Migrate

`015` intentionally changes zero production rows. Its checkpoint explains why
each missing binding requires operator evidence and reports both per-binding
counts and distinct `remaining_rows`. Bind exact reviewed UUIDs through the
canonical application path, preserving template-to-type and SEO-to-article
identity. Rerun `015` until `automatic_remaining_rows = 0` and
`remaining_rows = 0`. Never derive a UUID from the legacy integer or select an
arbitrary active version.

### `016` Contract prepare

`016` is one transaction. A readiness failure or DDL error rolls back all four
NOT VALID guards. Fix the reported data, artifact/hash, human provenance,
cross-binding, index, trigger, or ACL drift and rerun it. Once committed, the
guards prevent new NULL bindings while deferring the historical scans to
`017`.

### `017` Contract finalize

`017` first validates the four guards and commits. Its second, short metadata
transaction sets all four columns `NOT NULL`, removes the helper guards, and
renames foreign keys and 29 indexes to the canonical ABI atomically. If the
second transaction fails, the validated guards remain; rerunning `017` accepts
that all-validated checkpoint and safely retries finalization. A mix of
validated and unvalidated guards is treated as drift and must be investigated.

### After final Contract

For an empty, never-used deployment, `018` restores finalized ST-0003 in one
transaction. For every deployment with ST-0004 data, ship a new forward fix.
Verify the live catalog, checkpoint output, application compatibility, and an
audited backup before the new migration; do not amend `013` through `018`.
