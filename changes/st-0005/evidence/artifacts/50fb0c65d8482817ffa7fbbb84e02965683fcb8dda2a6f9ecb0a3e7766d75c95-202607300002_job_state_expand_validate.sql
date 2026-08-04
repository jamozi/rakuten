-- ST-0002 / INT-DEC-003
-- Phase: EXPAND VALIDATE AND INDEX
-- Requires: 202607300001_job_state_expand.sql
--
-- Constraint scans run after the metadata ALTER committed, so they acquire
-- PostgreSQL's validation lock rather than retaining ACCESS EXCLUSIVE.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '15min';

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
        RAISE EXCEPTION 'ST-0002 expand validation requires all three revision columns';
    END IF;
    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE conrelid = 'ops.job'::regclass
           AND conname IN (
               'ck_ops_job_status_expand',
               'ck_ops_job_completion_expand',
               'ck_ops_job_version_expand',
               'ck_ops_job_deadline_expand',
               'ck_ops_job_cancel_request_expand'
           )
    ) <> 5 THEN
        RAISE EXCEPTION 'ST-0002 expand validation requires all five Expand constraints';
    END IF;
END
$$;

ALTER TABLE ops.job VALIDATE CONSTRAINT ck_ops_job_status_expand;
ALTER TABLE ops.job VALIDATE CONSTRAINT ck_ops_job_completion_expand;
ALTER TABLE ops.job VALIDATE CONSTRAINT ck_ops_job_version_expand;
ALTER TABLE ops.job VALIDATE CONSTRAINT ck_ops_job_deadline_expand;
ALTER TABLE ops.job VALIDATE CONSTRAINT ck_ops_job_cancel_request_expand;

COMMIT;

-- These indexes coexist with the legacy ready index during the observation
-- window. They intentionally run outside every transaction.
SET lock_timeout = '5s';
SET statement_timeout = '15min';

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ops_job_ready_st0002
    ON ops.job (queue_name, priority, available_at)
    WHERE status IN ('REQUESTED', 'QUEUED', 'RETRY_SCHEDULED');

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ops_job_deadline_st0002
    ON ops.job (deadline_at)
    WHERE deadline_at IS NOT NULL
      AND status IN (
          'REQUESTED',
          'QUEUED',
          'RUNNING',
          'FAILED_RETRYABLE',
          'RETRY_SCHEDULED'
      );

DO $$
DECLARE
    ready_definition constant text :=
        'CREATE INDEX ix_ops_job_ready_st0002 ON ops.job USING btree (queue_name, priority, available_at) WHERE (status = ANY (ARRAY[''REQUESTED''::text, ''QUEUED''::text, ''RETRY_SCHEDULED''::text]))';
    deadline_definition constant text :=
        'CREATE INDEX ix_ops_job_deadline_st0002 ON ops.job USING btree (deadline_at) WHERE ((deadline_at IS NOT NULL) AND (status = ANY (ARRAY[''REQUESTED''::text, ''QUEUED''::text, ''RUNNING''::text, ''FAILED_RETRYABLE''::text, ''RETRY_SCHEDULED''::text])))';
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_index
         WHERE indexrelid = to_regclass('ops.ix_ops_job_ready_st0002')
           AND indrelid = 'ops.job'::regclass
           AND indisvalid
           AND indisready
           AND pg_get_indexdef(indexrelid) = ready_definition
    ) THEN
        RAISE EXCEPTION 'ST-0002 ready revision index is missing, invalid, or has the wrong definition';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM pg_index
         WHERE indexrelid = to_regclass('ops.ix_ops_job_deadline_st0002')
           AND indrelid = 'ops.job'::regclass
           AND indisvalid
           AND indisready
           AND pg_get_indexdef(indexrelid) = deadline_definition
    ) THEN
        RAISE EXCEPTION 'ST-0002 deadline revision index is missing, invalid, or has the wrong definition';
    END IF;
END
$$;

RESET lock_timeout;
RESET statement_timeout;
