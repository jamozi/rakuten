-- ST-0002 / INT-DEC-003
-- Guarded downgrade to the RAOS-DATA-001@0.1 Job shape.
--
-- This downgrade intentionally aborts before mutation when a reverse mapping
-- would lose canonical-only state or new-column meaning. Forward recovery is
-- the default operational response after canonical writers are enabled.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '15min';

-- Freeze writers before evaluating the losslessness guards. Without this lock,
-- a canonical writer could commit new-only state or field meaning after the
-- guard query but before the destructive column drops.
LOCK TABLE ops.job IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM ops.job
         WHERE status IN ('FAILED_RETRYABLE', 'RETRY_SCHEDULED', 'EXPIRED')
    ) THEN
        RAISE EXCEPTION 'ST-0002 downgrade refused: canonical-only Job states exist';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM ops.job
         WHERE job_version <> 1
            OR deadline_at IS NOT NULL
            OR cancel_requested_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'ST-0002 downgrade refused: canonical Job fields contain non-baseline meaning';
    END IF;
END
$$;

ALTER TABLE ops.job
    DROP CONSTRAINT ck_ops_job_status,
    DROP CONSTRAINT ck_ops_job_completion,
    DROP CONSTRAINT ck_ops_job_version_positive,
    DROP CONSTRAINT ck_ops_job_deadline_order,
    DROP CONSTRAINT ck_ops_job_cancel_request,
    ALTER COLUMN status SET DEFAULT 'PENDING';

DROP INDEX ops.ix_ops_job_deadline_active;
DROP INDEX ops.ix_ops_job_ready;

UPDATE ops.job
   SET status = CASE status
       WHEN 'REQUESTED' THEN 'PENDING'
       WHEN 'QUEUED' THEN 'READY'
       WHEN 'FAILED_TERMINAL' THEN 'FAILED'
       ELSE status
   END
 WHERE status IN ('REQUESTED', 'QUEUED', 'FAILED_TERMINAL');

ALTER TABLE ops.job
    DROP COLUMN job_version,
    DROP COLUMN deadline_at,
    DROP COLUMN cancel_requested_at,
    ADD CONSTRAINT ck_ops_job_status CHECK (
        status IN (
            'PENDING',
            'READY',
            'RUNNING',
            'SUCCEEDED',
            'FAILED',
            'CANCELLED',
            'QUARANTINED'
        )
    ),
    ADD CONSTRAINT ck_ops_job_completion CHECK (
        status NOT IN ('SUCCEEDED', 'FAILED', 'CANCELLED', 'QUARANTINED')
        OR completed_at IS NOT NULL
    );

CREATE INDEX ix_ops_job_ready
    ON ops.job (queue_name, priority, available_at)
    WHERE status IN ('PENDING', 'READY');

COMMIT;
