-- ST-0002 / INT-DEC-003
-- Phase: EXPAND DDL
-- Predecessor: RAOS-DATA-001@0.1 ops.job (MIG-001 foundation)
-- Risk class: C (semantic) with additive class A/B changes
-- Estimated lock: short ACCESS EXCLUSIVE for metadata-only ALTER TABLE
-- Rollback category: additive rollback only before a canonical writer depends on it
--
-- This is a formal translation of the accepted design delta. It is not the
-- proposal-only RAOS_04_001_contract_alignment_patch_v0.1.sql.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $$
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0002 requires PostgreSQL 18 or later';
    END IF;
    IF to_regclass('ops.job') IS NULL THEN
        RAISE EXCEPTION 'ST-0002 predecessor ops.job is missing';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'ops.job'::regclass
           AND conname = 'ck_ops_job_status'
    ) THEN
        RAISE EXCEPTION 'ST-0002 expected baseline constraint ck_ops_job_status';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'ops.job'::regclass
           AND conname = 'ck_ops_job_completion'
    ) THEN
        RAISE EXCEPTION 'ST-0002 expected baseline constraint ck_ops_job_completion';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'ops'
           AND table_name = 'job'
           AND column_name IN ('job_version', 'deadline_at', 'cancel_requested_at')
    ) THEN
        RAISE EXCEPTION 'ST-0002 expand columns already exist; inspect migration history before retry';
    END IF;
END
$$;

ALTER TABLE ops.job
    ADD COLUMN job_version smallint,
    ADD COLUMN deadline_at timestamptz,
    ADD COLUMN cancel_requested_at timestamptz;

ALTER TABLE ops.job
    DROP CONSTRAINT ck_ops_job_status,
    DROP CONSTRAINT ck_ops_job_completion,
    ADD CONSTRAINT ck_ops_job_status_expand CHECK (
        status IN (
            'PENDING',
            'READY',
            'FAILED',
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
    ADD CONSTRAINT ck_ops_job_completion_expand CHECK (
        status NOT IN (
            'SUCCEEDED',
            'FAILED',
            'FAILED_TERMINAL',
            'QUARANTINED',
            'CANCELLED',
            'EXPIRED'
        )
        OR completed_at IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ops_job_version_expand CHECK (
        job_version IS NULL OR job_version >= 1
    ) NOT VALID,
    ADD CONSTRAINT ck_ops_job_deadline_expand CHECK (
        deadline_at IS NULL OR deadline_at > created_at
    ) NOT VALID,
    ADD CONSTRAINT ck_ops_job_cancel_request_expand CHECK (
        cancel_requested_at IS NULL OR status <> 'SUCCEEDED'
    ) NOT VALID;

COMMENT ON COLUMN ops.job.job_version IS
    'Version of the Job message/payload contract; distinct from lock_version.';
COMMENT ON COLUMN ops.job.deadline_at IS
    'Deadline after which an eligible active Job may expire.';
COMMENT ON COLUMN ops.job.cancel_requested_at IS
    'Timestamp of a cooperative cancellation request.';

COMMIT;
