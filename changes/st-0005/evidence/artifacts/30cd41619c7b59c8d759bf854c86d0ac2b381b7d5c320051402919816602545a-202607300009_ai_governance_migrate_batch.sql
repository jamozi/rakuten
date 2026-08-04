-- ST-0003 / INT-DEC-004
-- Phase: MIGRATE REPEATABLE BATCH
-- Requires: 202607300008_ai_governance_expand_validate.sql
-- Execution: repeat until automatic_remaining_rows is zero, explicitly
-- classify operator_classification_rows, then require remaining_rows zero
-- Batch size: at most 1,000 rows total across all affected tables
-- Recovery: only the current batch rolls back; committed batches are idempotent
--
-- BLOCKED AI Jobs, REJECTED Prompts, and legacy Prompt author provenance are
-- intentionally not guessed by this migration. They remain in remaining_rows
-- until an operator records an evidence-based classification/binding. ST-0701
-- owns task registry loading.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $$
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0003 requires PostgreSQL 18 or later';
    END IF;
    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE (conrelid, conname) IN (
             ('ai.ai_job'::regclass, 'ck_ai_job_status_st0003_expand'),
             ('ai.prompt_version'::regclass, 'ck_ai_prompt_status_st0003_expand'),
             ('ai.model_route_version'::regclass, 'ck_ai_route_status_st0003_expand')
         )
    ) <> 3 THEN
        RAISE EXCEPTION 'ST-0003 Migrate requires the Expand lifecycle state';
    END IF;
END
$$;

CREATE TEMPORARY TABLE st0003_batch_budget (
    remaining integer NOT NULL CHECK (remaining BETWEEN 0 AND 1000)
) ON COMMIT DROP;
INSERT INTO st0003_batch_budget (remaining) VALUES (1000);

CREATE TEMPORARY TABLE st0003_batch_checkpoint (
    entity text NOT NULL,
    old_status text,
    new_status text,
    row_count bigint NOT NULL CHECK (row_count >= 0),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb
) ON COMMIT DROP;

WITH batch AS MATERIALIZED (
    SELECT job.id,
           job.status AS old_status,
           job.request_config IS NULL AS request_config_backfilled,
           job.budget_reserved_jpy IS NULL AS budget_backfilled,
           job.lock_version IS NULL AS lock_version_backfilled,
           job.updated_at IS NULL AS updated_at_backfilled
      FROM ai.ai_job AS job
     WHERE job.status IN ('PENDING', 'FAILED')
        OR job.request_config IS NULL
        OR job.budget_reserved_jpy IS NULL
        OR job.lock_version IS NULL
        OR job.updated_at IS NULL
     ORDER BY job.id
     LIMIT LEAST(1000, (SELECT remaining FROM st0003_batch_budget))
     FOR UPDATE SKIP LOCKED
),
updated AS (
    UPDATE ai.ai_job AS job
       SET status = CASE job.status
               WHEN 'PENDING' THEN 'REQUESTED'
               WHEN 'FAILED' THEN 'FAILED_TERMINAL'
               ELSE job.status
           END,
           request_config = COALESCE(job.request_config, '{}'::jsonb),
           budget_reserved_jpy = COALESCE(job.budget_reserved_jpy, 0),
           lock_version = COALESCE(job.lock_version, 0),
           updated_at = COALESCE(job.updated_at, job.created_at)
      FROM batch
     WHERE job.id = batch.id
    RETURNING
        batch.old_status,
        job.status AS new_status,
        batch.request_config_backfilled,
        batch.budget_backfilled,
        batch.lock_version_backfilled,
        batch.updated_at_backfilled
),
logged AS (
    INSERT INTO st0003_batch_checkpoint (
        entity,
        old_status,
        new_status,
        row_count,
        detail
    )
    SELECT 'ai.ai_job',
           old_status,
           new_status,
           count(*)::bigint,
           jsonb_build_object(
               'request_config_backfilled',
               count(*) FILTER (WHERE request_config_backfilled),
               'budget_backfilled',
               count(*) FILTER (WHERE budget_backfilled),
               'lock_version_backfilled',
               count(*) FILTER (WHERE lock_version_backfilled),
               'updated_at_backfilled',
               count(*) FILTER (WHERE updated_at_backfilled)
           )
      FROM updated
     GROUP BY old_status, new_status
    RETURNING row_count
)
UPDATE st0003_batch_budget
   SET remaining = remaining - COALESCE(
       (SELECT sum(row_count)::integer FROM logged),
       0
   );

WITH batch AS MATERIALIZED (
    SELECT attempt.id,
           attempt.status AS old_status,
           model.provider_model_id,
           attempt.requested_model_id IS NULL AS requested_model_backfilled,
           attempt.resolved_model_id IS NULL AS resolved_model_backfilled,
           attempt.request_config IS NULL AS request_config_backfilled,
           attempt.validation_status IS NULL AS validation_backfilled,
           attempt.repair_attempt_no IS NULL AS repair_backfilled
      FROM ai.ai_attempt AS attempt
      JOIN ai.model_definition AS model ON model.id = attempt.model_id
     WHERE attempt.requested_model_id IS NULL
        OR attempt.resolved_model_id IS NULL
        OR attempt.request_config IS NULL
        OR attempt.validation_status IS NULL
        OR attempt.repair_attempt_no IS NULL
     ORDER BY attempt.id
     LIMIT LEAST(1000, (SELECT remaining FROM st0003_batch_budget))
     FOR UPDATE OF attempt SKIP LOCKED
),
updated AS (
    UPDATE ai.ai_attempt AS attempt
       SET requested_model_id = COALESCE(
               attempt.requested_model_id,
               batch.provider_model_id
           ),
           resolved_model_id = COALESCE(
               attempt.resolved_model_id,
               batch.provider_model_id
           ),
           request_config = COALESCE(attempt.request_config, '{}'::jsonb),
           validation_status = COALESCE(
               attempt.validation_status,
               CASE attempt.status
                   WHEN 'RUNNING' THEN 'PENDING'
                   WHEN 'SUCCEEDED' THEN 'PASSED'
                   ELSE 'FAILED'
               END
           ),
           repair_attempt_no = COALESCE(attempt.repair_attempt_no, 0)
      FROM batch
     WHERE attempt.id = batch.id
    RETURNING
        batch.old_status,
        attempt.status AS new_status,
        batch.requested_model_backfilled,
        batch.resolved_model_backfilled,
        batch.request_config_backfilled,
        batch.validation_backfilled,
        batch.repair_backfilled
),
logged AS (
    INSERT INTO st0003_batch_checkpoint (
        entity,
        old_status,
        new_status,
        row_count,
        detail
    )
    SELECT 'ai.ai_attempt',
           old_status,
           new_status,
           count(*)::bigint,
           jsonb_build_object(
               'requested_model_backfilled',
               count(*) FILTER (WHERE requested_model_backfilled),
               'resolved_model_backfilled',
               count(*) FILTER (WHERE resolved_model_backfilled),
               'request_config_backfilled',
               count(*) FILTER (WHERE request_config_backfilled),
               'validation_backfilled',
               count(*) FILTER (WHERE validation_backfilled),
               'repair_backfilled',
               count(*) FILTER (WHERE repair_backfilled)
           )
      FROM updated
     GROUP BY old_status, new_status
    RETURNING row_count
)
UPDATE st0003_batch_budget
   SET remaining = remaining - COALESCE(
       (SELECT sum(row_count)::integer FROM logged),
       0
   );

WITH batch AS MATERIALIZED (
    SELECT prompt.id,
           prompt.status AS old_status,
           prompt.locale IS NULL AS locale_backfilled,
           prompt.policy_test_status IS NULL AS policy_test_backfilled,
           prompt.lock_version IS NULL AS lock_version_backfilled,
           prompt.updated_at IS NULL AS updated_at_backfilled
      FROM ai.prompt_version AS prompt
     WHERE prompt.locale IS NULL
        OR prompt.policy_test_status IS NULL
        OR prompt.lock_version IS NULL
        OR prompt.updated_at IS NULL
     ORDER BY prompt.id
     LIMIT LEAST(1000, (SELECT remaining FROM st0003_batch_budget))
     FOR UPDATE SKIP LOCKED
),
updated AS (
    UPDATE ai.prompt_version AS prompt
       SET locale = COALESCE(prompt.locale, 'ja-JP'),
           policy_test_status = COALESCE(
               prompt.policy_test_status,
               'NOT_EXECUTED'
           ),
           lock_version = COALESCE(prompt.lock_version, 0),
           updated_at = COALESCE(prompt.updated_at, prompt.created_at)
      FROM batch
     WHERE prompt.id = batch.id
    RETURNING
        batch.old_status,
        prompt.status AS new_status,
        batch.locale_backfilled,
        batch.policy_test_backfilled,
        batch.lock_version_backfilled,
        batch.updated_at_backfilled
),
logged AS (
    INSERT INTO st0003_batch_checkpoint (
        entity,
        old_status,
        new_status,
        row_count,
        detail
    )
    SELECT 'ai.prompt_version',
           old_status,
           new_status,
           count(*)::bigint,
           jsonb_build_object(
               'locale_backfilled',
               count(*) FILTER (WHERE locale_backfilled),
               'policy_test_backfilled',
               count(*) FILTER (WHERE policy_test_backfilled),
               'lock_version_backfilled',
               count(*) FILTER (WHERE lock_version_backfilled),
               'updated_at_backfilled',
               count(*) FILTER (WHERE updated_at_backfilled)
           )
      FROM updated
     GROUP BY old_status, new_status
    RETURNING row_count
)
UPDATE st0003_batch_budget
   SET remaining = remaining - COALESCE(
       (SELECT sum(row_count)::integer FROM logged),
       0
   );

WITH batch AS MATERIALIZED (
    SELECT model.id
      FROM ai.model_definition AS model
     WHERE model.provider_metadata IS NULL
     ORDER BY model.id
     LIMIT LEAST(1000, (SELECT remaining FROM st0003_batch_budget))
     FOR UPDATE SKIP LOCKED
),
updated AS (
    UPDATE ai.model_definition AS model
       SET provider_metadata = '{}'::jsonb
      FROM batch
     WHERE model.id = batch.id
    RETURNING model.id
),
logged AS (
    INSERT INTO st0003_batch_checkpoint (
        entity,
        row_count,
        detail
    )
    SELECT 'ai.model_definition',
           count(*)::bigint,
           jsonb_build_object('provider_metadata_backfilled', count(*))
      FROM updated
    HAVING count(*) > 0
    RETURNING row_count
)
UPDATE st0003_batch_budget
   SET remaining = remaining - COALESCE(
       (SELECT sum(row_count)::integer FROM logged),
       0
   );

WITH batch AS MATERIALIZED (
    SELECT route.id,
           route.status AS old_status,
           route.lock_version IS NULL AS lock_version_backfilled,
           route.updated_at IS NULL AS updated_at_backfilled
      FROM ai.model_route_version AS route
     WHERE route.lock_version IS NULL
        OR route.updated_at IS NULL
     ORDER BY route.id
     LIMIT LEAST(1000, (SELECT remaining FROM st0003_batch_budget))
     FOR UPDATE SKIP LOCKED
),
updated AS (
    UPDATE ai.model_route_version AS route
       SET lock_version = COALESCE(route.lock_version, 0),
           updated_at = COALESCE(route.updated_at, route.created_at)
      FROM batch
     WHERE route.id = batch.id
    RETURNING
        batch.old_status,
        route.status AS new_status,
        batch.lock_version_backfilled,
        batch.updated_at_backfilled
),
logged AS (
    INSERT INTO st0003_batch_checkpoint (
        entity,
        old_status,
        new_status,
        row_count,
        detail
    )
    SELECT 'ai.model_route_version',
           old_status,
           new_status,
           count(*)::bigint,
           jsonb_build_object(
               'lock_version_backfilled',
               count(*) FILTER (WHERE lock_version_backfilled),
               'updated_at_backfilled',
               count(*) FILTER (WHERE updated_at_backfilled)
           )
      FROM updated
     GROUP BY old_status, new_status
    RETURNING row_count
)
UPDATE st0003_batch_budget
   SET remaining = remaining - COALESCE(
       (SELECT sum(row_count)::integer FROM logged),
       0
   );

DO $$
DECLARE
    changed_rows bigint;
BEGIN
    SELECT COALESCE(sum(row_count), 0)
      INTO changed_rows
      FROM st0003_batch_checkpoint;
    IF changed_rows > 1000 THEN
        RAISE EXCEPTION
            'ST-0003 internal error: batch changed % rows, limit is 1000',
            changed_rows;
    END IF;
END
$$;

SELECT entity,
       old_status,
       new_status,
       row_count,
       detail
  FROM st0003_batch_checkpoint
 ORDER BY entity, old_status NULLS FIRST, new_status NULLS FIRST;

SELECT 1000 - remaining AS changed_rows,
       remaining AS unused_batch_capacity
  FROM st0003_batch_budget;

COMMIT;

WITH counts AS (
    SELECT (
            (SELECT count(*) FROM ai.ai_job
              WHERE status IN ('PENDING', 'FAILED')
                 OR request_config IS NULL
                 OR budget_reserved_jpy IS NULL
                 OR lock_version IS NULL
                 OR updated_at IS NULL)
          + (SELECT count(*) FROM ai.ai_attempt
              WHERE requested_model_id IS NULL
                 OR resolved_model_id IS NULL
                 OR request_config IS NULL
                 OR validation_status IS NULL
                 OR repair_attempt_no IS NULL)
          + (SELECT count(*) FROM ai.prompt_version
              WHERE locale IS NULL
                 OR policy_test_status IS NULL
                 OR lock_version IS NULL
                 OR updated_at IS NULL)
          + (SELECT count(*) FROM ai.model_definition
              WHERE provider_metadata IS NULL)
          + (SELECT count(*) FROM ai.model_route_version
              WHERE lock_version IS NULL OR updated_at IS NULL)
        )::bigint AS automatic_remaining_rows,
        (SELECT count(*)::bigint
           FROM ai.ai_job WHERE status = 'BLOCKED')
            AS unclassified_blocked_jobs,
        (SELECT count(*)::bigint
           FROM ai.prompt_version WHERE status = 'REJECTED')
            AS unclassified_rejected_prompts,
        (SELECT count(*)::bigint
           FROM ai.prompt_version WHERE author_principal_id IS NULL)
            AS unclassified_prompt_authors
)
SELECT automatic_remaining_rows,
       unclassified_blocked_jobs
           + unclassified_rejected_prompts
           + unclassified_prompt_authors
           AS operator_classification_rows,
       automatic_remaining_rows
           + unclassified_blocked_jobs
           + unclassified_rejected_prompts
           + unclassified_prompt_authors
           AS remaining_rows,
       unclassified_blocked_jobs,
       unclassified_rejected_prompts,
       unclassified_prompt_authors
  FROM counts;
