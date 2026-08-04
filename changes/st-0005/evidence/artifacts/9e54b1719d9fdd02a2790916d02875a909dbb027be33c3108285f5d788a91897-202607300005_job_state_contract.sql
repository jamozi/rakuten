-- ST-0002 / INT-DEC-003
-- Phase: CONTRACT VALIDATE AND FINALIZE
-- Requires: 202607300004_job_state_contract_prepare.sql
--
-- Full-table validation runs in its own transaction without a preceding
-- ACCESS EXCLUSIVE ALTER. The final metadata/index swap is a separate short
-- transaction and performs no intentional full-table scan.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '15min';

DO $$
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0002 requires PostgreSQL 18 or later';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM ops.job
         WHERE status IN ('PENDING', 'READY', 'FAILED')
            OR job_version IS NULL
    ) THEN
        RAISE EXCEPTION 'ST-0002 Contract validation blocked by legacy state or NULL job_version';
    END IF;
    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE conrelid = 'ops.job'::regclass
           AND conname IN (
               'ck_ops_job_status',
               'ck_ops_job_completion',
               'ck_ops_job_version_positive',
               'ck_ops_job_deadline_order',
               'ck_ops_job_cancel_request',
               'ck_ops_job_version_not_null'
           )
    ) <> 6 THEN
        RAISE EXCEPTION 'ST-0002 Contract validation requires all six canonical constraints';
    END IF;
END
$$;

ALTER TABLE ops.job VALIDATE CONSTRAINT ck_ops_job_status;
ALTER TABLE ops.job VALIDATE CONSTRAINT ck_ops_job_completion;
ALTER TABLE ops.job VALIDATE CONSTRAINT ck_ops_job_version_positive;
ALTER TABLE ops.job VALIDATE CONSTRAINT ck_ops_job_deadline_order;
ALTER TABLE ops.job VALIDATE CONSTRAINT ck_ops_job_cancel_request;
ALTER TABLE ops.job VALIDATE CONSTRAINT ck_ops_job_version_not_null;

COMMIT;

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $$
DECLARE
    ready_definition constant text :=
        'CREATE INDEX ix_ops_job_ready_st0002 ON ops.job USING btree (queue_name, priority, available_at) WHERE (status = ANY (ARRAY[''REQUESTED''::text, ''QUEUED''::text, ''RETRY_SCHEDULED''::text]))';
    deadline_definition constant text :=
        'CREATE INDEX ix_ops_job_deadline_st0002 ON ops.job USING btree (deadline_at) WHERE ((deadline_at IS NOT NULL) AND (status = ANY (ARRAY[''REQUESTED''::text, ''QUEUED''::text, ''RUNNING''::text, ''FAILED_RETRYABLE''::text, ''RETRY_SCHEDULED''::text])))';
BEGIN
    IF EXISTS (
        SELECT 1
          FROM ops.job
         WHERE status IN ('PENDING', 'READY', 'FAILED')
            OR job_version IS NULL
    ) THEN
        RAISE EXCEPTION 'ST-0002 Contract finalization blocked by legacy state or NULL job_version';
    END IF;
    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE conrelid = 'ops.job'::regclass
           AND conname IN (
               'ck_ops_job_status',
               'ck_ops_job_completion',
               'ck_ops_job_version_positive',
               'ck_ops_job_deadline_order',
               'ck_ops_job_cancel_request',
               'ck_ops_job_version_not_null'
           )
           AND convalidated
    ) <> 6 THEN
        RAISE EXCEPTION 'ST-0002 Contract finalization requires six validated canonical constraints';
    END IF;
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

ALTER TABLE ops.job
    DROP CONSTRAINT ck_ops_job_status_expand,
    DROP CONSTRAINT ck_ops_job_completion_expand,
    DROP CONSTRAINT ck_ops_job_version_expand,
    DROP CONSTRAINT ck_ops_job_deadline_expand,
    DROP CONSTRAINT ck_ops_job_cancel_request_expand,
    ALTER COLUMN status SET DEFAULT 'REQUESTED',
    ALTER COLUMN job_version SET DEFAULT 1,
    ALTER COLUMN job_version SET NOT NULL;

ALTER TABLE ops.job DROP CONSTRAINT ck_ops_job_version_not_null;

DROP INDEX ops.ix_ops_job_ready;
ALTER INDEX ops.ix_ops_job_ready_st0002 RENAME TO ix_ops_job_ready;
ALTER INDEX ops.ix_ops_job_deadline_st0002 RENAME TO ix_ops_job_deadline_active;

COMMIT;
