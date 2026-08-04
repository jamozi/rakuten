-- ST-0002 / INT-DEC-003
-- Phase: CONTRACT PREPARE
-- Requires:
--   * canonical writers deployed
--   * 202607300003_job_state_migrate_batch.sql repeated to remaining_rows=0
--   * both canonical revision indexes valid and definition-exact
--
-- This short transaction adds canonical constraints as NOT VALID alongside
-- the Expand constraints. At commit, legacy writers are intentionally cut off.

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
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0002 requires PostgreSQL 18 or later';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM ops.job
         WHERE status IN ('PENDING', 'READY', 'FAILED')
            OR job_version IS NULL
    ) THEN
        RAISE EXCEPTION 'ST-0002 Contract prepare blocked by legacy state or NULL job_version';
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
        RAISE EXCEPTION 'ST-0002 Contract prepare requires all five Expand constraints';
    END IF;
    IF EXISTS (
        SELECT 1
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
    ) THEN
        RAISE EXCEPTION 'ST-0002 Contract constraints already exist; inspect migration history';
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
    ADD CONSTRAINT ck_ops_job_status CHECK (
        status IN (
            'REQUESTED',
            'QUEUED',
            'RUNNING',
            'SUCCEEDED',
            'FAILED_RETRYABLE',
            'RETRY_SCHEDULED',
            'FAILED_TERMINAL',
            'QUARANTINED',
            'CANCELLED',
            'EXPIRED'
        )
    ) NOT VALID,
    ADD CONSTRAINT ck_ops_job_completion CHECK (
        status NOT IN (
            'SUCCEEDED',
            'FAILED_TERMINAL',
            'QUARANTINED',
            'CANCELLED',
            'EXPIRED'
        )
        OR completed_at IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ops_job_version_positive CHECK (
        job_version >= 1
    ) NOT VALID,
    ADD CONSTRAINT ck_ops_job_deadline_order CHECK (
        deadline_at IS NULL OR deadline_at > created_at
    ) NOT VALID,
    ADD CONSTRAINT ck_ops_job_cancel_request CHECK (
        cancel_requested_at IS NULL OR status <> 'SUCCEEDED'
    ) NOT VALID,
    ADD CONSTRAINT ck_ops_job_version_not_null CHECK (
        job_version IS NOT NULL
    ) NOT VALID;

COMMIT;
