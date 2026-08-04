-- RAOS-API-001 contract alignment patch v0.1
-- Purpose: align ops.job persistence with RAOS-ARCH-001 canonical Job Message/state model.
-- Apply as an Expand-Migrate-Contract migration after RAOS-DATA-001 MIG-002 tests.
-- This file is a proposed migration contract; Codex must convert it into the repository migration framework.

BEGIN;

ALTER TABLE ops.job
    ADD COLUMN IF NOT EXISTS job_version smallint NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS deadline_at timestamptz,
    ADD COLUMN IF NOT EXISTS cancel_requested_at timestamptz;

ALTER TABLE ops.job
    DROP CONSTRAINT IF EXISTS ck_ops_job_status;

UPDATE ops.job
SET status = CASE status
    WHEN 'PENDING' THEN 'REQUESTED'
    WHEN 'READY' THEN 'QUEUED'
    WHEN 'FAILED' THEN 'FAILED_TERMINAL'
    ELSE status
END
WHERE status IN ('PENDING','READY','FAILED');

ALTER TABLE ops.job
    ADD CONSTRAINT ck_ops_job_status CHECK (
        status IN (
            'REQUESTED','QUEUED','RUNNING','SUCCEEDED','FAILED_RETRYABLE',
            'RETRY_SCHEDULED','FAILED_TERMINAL','QUARANTINED','CANCELLED','EXPIRED'
        )
    );

ALTER TABLE ops.job
    DROP CONSTRAINT IF EXISTS ck_ops_job_terminal_time;
ALTER TABLE ops.job
    ADD CONSTRAINT ck_ops_job_terminal_time CHECK (
        status NOT IN ('SUCCEEDED','FAILED_TERMINAL','QUARANTINED','CANCELLED','EXPIRED')
        OR completed_at IS NOT NULL
    );

ALTER TABLE ops.job
    ADD CONSTRAINT ck_ops_job_version_positive CHECK (job_version >= 1),
    ADD CONSTRAINT ck_ops_job_deadline_order CHECK (deadline_at IS NULL OR deadline_at > created_at),
    ADD CONSTRAINT ck_ops_job_cancel_request CHECK (cancel_requested_at IS NULL OR status <> 'SUCCEEDED');

DROP INDEX IF EXISTS ops.ix_ops_job_ready;
CREATE INDEX ix_ops_job_ready
    ON ops.job (queue_name, priority, available_at)
    WHERE status IN ('REQUESTED','QUEUED','RETRY_SCHEDULED');

CREATE INDEX IF NOT EXISTS ix_ops_job_deadline_active
    ON ops.job (deadline_at)
    WHERE deadline_at IS NOT NULL
      AND status IN ('REQUESTED','QUEUED','RUNNING','FAILED_RETRYABLE','RETRY_SCHEDULED');

COMMIT;
