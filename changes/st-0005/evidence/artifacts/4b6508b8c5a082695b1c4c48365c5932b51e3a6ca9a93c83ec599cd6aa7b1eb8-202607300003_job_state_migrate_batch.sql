-- ST-0002 / INT-DEC-003
-- Phase: MIGRATE REPEATABLE BATCH
-- Requires: 202607300002_job_state_expand_validate.sql
-- Execution: repeat this entire payload until remaining_rows is zero
-- Batch size: at most 1,000 rows ordered by UUIDv7 primary key
-- Recovery: only the current batch rolls back; committed batches are idempotent
--
-- The future ST-0301 runner must persist each result as an auditable checkpoint
-- and must not mark the data migration complete while remaining_rows is nonzero.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $$
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0002 requires PostgreSQL 18 or later';
    END IF;
    IF (
        SELECT count(*)
          FROM information_schema.columns
         WHERE table_schema = 'ops'
           AND table_name = 'job'
           AND column_name IN ('job_version', 'deadline_at', 'cancel_requested_at')
    ) <> 3 THEN
        RAISE EXCEPTION 'ST-0002 migrate batch requires all three revision columns';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'ops.job'::regclass
           AND conname IN ('ck_ops_job_status_expand', 'ck_ops_job_status')
    ) THEN
        RAISE EXCEPTION 'ST-0002 migrate batch requires an Expand or prepared Contract state';
    END IF;
END
$$;

WITH batch AS MATERIALIZED (
    SELECT id,
           status AS old_status,
           job_version AS old_job_version
      FROM ops.job
     WHERE job_version IS NULL
        OR status IN ('PENDING', 'READY', 'FAILED')
     ORDER BY id
     LIMIT 1000
     FOR UPDATE SKIP LOCKED
),
updated AS (
    UPDATE ops.job AS job
       SET job_version = COALESCE(job.job_version, 1),
           status = CASE job.status
               WHEN 'PENDING' THEN 'REQUESTED'
               WHEN 'READY' THEN 'QUEUED'
               WHEN 'FAILED' THEN 'FAILED_TERMINAL'
               ELSE job.status
           END
      FROM batch
     WHERE job.id = batch.id
    RETURNING
        batch.old_status,
        job.status AS new_status,
        batch.old_job_version IS NULL AS version_backfilled
)
SELECT old_status,
       new_status,
       count(*)::bigint AS row_count,
       count(*) FILTER (WHERE version_backfilled)::bigint AS versions_backfilled
  FROM updated
 GROUP BY old_status, new_status
 ORDER BY old_status, new_status;

COMMIT;

SELECT count(*)::bigint AS remaining_rows
  FROM ops.job
 WHERE job_version IS NULL
    OR status IN ('PENDING', 'READY', 'FAILED');
