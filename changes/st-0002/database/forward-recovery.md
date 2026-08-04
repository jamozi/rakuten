# ST-0002 forward recovery

Forward recovery is preferred once a canonical writer may have observed or
written the v0.2 Job model. Never collapse `FAILED_RETRYABLE`,
`RETRY_SCHEDULED`, or `EXPIRED` into a legacy state merely to make a downgrade
complete.

Each numbered SQL file is a separately recorded checkpoint. Do not mark a
checkpoint complete unless its entire payload succeeds.

## 001 Expand DDL failed

The metadata-only table transaction rolls back as a unit. Correct the
predecessor or lock-timeout cause and rerun 001. If only some revision columns
or constraints exist, stop and inspect migration history rather than using
`IF NOT EXISTS` to hide a partial shape.

## 002 Expand validation/index failed

The validation transaction is separate from the Expand DDL and does not retain
its `ACCESS EXCLUSIVE` lock. A validation failure leaves the dual-compatible
NOT VALID constraints, which still enforce new rows. Correct invalid legacy
data and rerun 002.

Concurrent indexes may be absent independently. Inspect `pg_index.indisvalid`,
`pg_index.indisready`, and `pg_get_indexdef`. Drop only a wrong or invalid
`*_st0002` revision index, then rerun 002. The payload refuses a valid same-name
index with the wrong access method, key order, or predicate.

## 003 Migrate batch failed or was interrupted

Each invocation locks and changes at most 1,000 rows in one transaction. A
failing invocation rolls back only that batch; earlier checkpoint batches
remain committed and are safe to revisit. Persist its per-state result, then
repeat 003 until the final `remaining_rows` result is zero.

`SKIP LOCKED` rows are not treated as complete: they remain in
`remaining_rows` and must be revisited after the competing transaction ends.
Do not continue to 004 while a legacy state or NULL `job_version` remains.

## 004 Contract prepare failed

The short transaction either adds all six canonical NOT VALID constraints or
none. Correct the cause and rerun 004. Once 004 commits, the canonical status
constraint rejects new writes from legacy writers; application rollback must
therefore use a canonical-compatible writer.

If a concurrent legacy write raced the precondition, 005 validation will fail.
Run repeatable batch 003 until `remaining_rows=0`, then rerun 005. Do not rerun
an already recorded 004 revision merely because a later checkpoint failed.

## 005 Contract validate/finalize failed

Constraint validation commits separately from the final metadata/index swap.
A validation failure leaves both Expand and canonical constraints in place;
run 003 if needed and rerun 005.

The final default, NOT NULL, Expand-constraint removal, and index rename are one
short transaction. A failure rolls that whole final transaction back, leaving
the validated canonical constraints and revision indexes safe for a 005 retry.

## Application rollback

Before 004, roll application code back to a version that understands the
dual-compatible Expand state. Keep the v0.2 columns and union constraint until
observation proves that no canonical-only state or field is in use.

After 004, legacy-state writers are no longer compatible. Prefer forward
recovery. `202607300006_job_state_guarded_downgrade.sql` is only for a verified
pre-canonical dataset and freezes writers before its losslessness checks.

## Required evidence before production

- approved release and migration/checkpoint IDs;
- PostgreSQL 18.4 CI and staging results;
- recent backup and tested restore;
- per-batch row/state reconciliation and final `remaining_rows=0`;
- lock, WAL, replica-lag, and runtime estimates;
- old/new writer observation window;
- human approval for Contract and any guarded downgrade.
