-- ST-0003 / INT-DEC-004
-- Guarded downgrade to the post-ST-0002 / RAOS-DATA-001@0.1 AI shape.
--
-- This is not a general reverse transform. It aborts before mutation unless
-- every ST-0003 value is provably baseline-equivalent. BLOCKED AI Jobs and
-- REJECTED Prompts were deliberately never auto-mapped, so any operator
-- classification that cannot be proven reversible also causes refusal.
-- Forward recovery is the default once canonical writers are enabled.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '15min';

LOCK TABLE
    ai.task_definition,
    ai.ai_job,
    ai.ai_attempt,
    ai.prompt_version,
    ai.output_schema_version,
    ai.model_definition,
    ai.model_route_version,
    ai.evaluation_result,
    ai.evaluation_suite,
    ai.evaluation_dataset_version,
    ai.evaluation_case,
    ai.evaluation_run,
    ai.evaluation_case_result,
    ai.human_evaluation,
    ai.judge_calibration,
    ai.release_decision,
    ai.release_approval,
    policy.policy_bundle
IN ACCESS EXCLUSIVE MODE;

DO $$
DECLARE
    required_name text;
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0003 requires PostgreSQL 18 or later';
    END IF;
    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE (conrelid, conname) IN (
             ('ai.ai_job'::regclass, 'ck_ai_job_status'),
             ('ai.ai_job'::regclass, 'ck_ai_job_complete'),
             ('ai.prompt_version'::regclass, 'ck_ai_prompt_status'),
             ('ai.model_route_version'::regclass, 'ck_ai_route_status')
         )
           AND convalidated
    ) <> 4 THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: finalized Contract shape is absent';
    END IF;

    FOREACH required_name IN ARRAY ARRAY[
        'ai.evaluation_suite',
        'ai.evaluation_dataset_version',
        'ai.evaluation_case',
        'ai.evaluation_run',
        'ai.evaluation_case_result',
        'ai.human_evaluation',
        'ai.judge_calibration',
        'ai.release_decision',
        'ai.release_approval'
    ]
    LOOP
        IF to_regclass(required_name) IS NULL THEN
            RAISE EXCEPTION
                'ST-0003 downgrade refused: required table % is absent',
                required_name;
        END IF;
    END LOOP;

    FOREACH required_name IN ARRAY ARRAY[
        'ai.guard_evaluation_suite_mutation()',
        'ai.guard_judge_calibration_mutation()',
        'ai.guard_locked_evaluation_dataset()',
        'ai.guard_evaluation_case_mutation()',
        'ai.guard_evaluation_run_mutation()',
        'ai.guard_open_evaluation_run_result()',
        'ai.guard_evaluated_attempt_immutability()',
        'ai.guard_evaluated_job_binding()',
        'ai.guard_governance_component_dependency()',
        'policy.guard_rule_version_immutability()',
        'policy.guard_bundle_rule_append_only()',
        'ai.guard_open_human_evaluation()',
        'ai.guard_evaluation_metric_mutation()',
        'ai.guard_release_decision_mutation()',
        'ai.guard_release_task_serialization()',
        'ai.canonical_suite_risk(text)',
        'ai.canonical_suite_config(text)',
        'ai.canonical_grader_output_metrics(text)',
        'ai.canonical_metric_unit(text)',
        'ai.canonical_metric_direction(text)',
        'ai.canonical_regression_margin(text)',
        'ai.guard_canonical_suite_config()',
        'ai.guard_evaluation_run_start_integrity()',
        'ai.guard_judge_calibration_scope()',
        'ai.guard_release_approval_mutation()',
        'ai.assert_evaluation_run_evidence(uuid,boolean)',
        'ai.assert_regression_against_baseline(uuid,uuid)',
        'ai.guard_evaluation_run_completion_evidence()',
        'ai.artifact_matches_immutable_hash(uuid,text)',
        'ai.has_live_rollback_dependents(text,uuid)',
        'ai.guard_release_decision_evidence()',
        'ai.guard_task_definition_lifecycle()',
        'ai.guard_prompt_version_lifecycle()',
        'ai.guard_model_route_lifecycle()',
        'ai.guard_output_schema_lifecycle()',
        'ai.guard_model_definition_lifecycle()',
        'policy.guard_policy_bundle_lifecycle()'
    ]
    LOOP
        IF to_regprocedure(required_name) IS NULL THEN
            RAISE EXCEPTION
                'ST-0003 downgrade refused: required helper % is absent',
                required_name;
        END IF;
    END LOOP;

    IF (
        SELECT count(*)
          FROM information_schema.columns
         WHERE (table_schema, table_name, column_name) IN (
            ('ai', 'prompt_version', 'author_principal_id'),
            ('ai', 'evaluation_result', 'judge_calibration_id'),
            ('ai', 'evaluation_result', 'judge_route_version_id'),
            ('ai', 'evaluation_result', 'judge_prompt_version_id'),
            ('ai', 'evaluation_result', 'judge_rubric_artifact_id'),
            ('ai', 'evaluation_result', 'judge_resolved_model_id'),
            ('ai', 'evaluation_result', 'judge_grader_version'),
            ('ai', 'evaluation_result', 'proportion_numerator_count'),
            ('ai', 'evaluation_result', 'proportion_denominator_count')
         )
    ) <> 9 THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: hardened existing-table columns are incomplete';
    END IF;

    IF EXISTS (SELECT 1 FROM ai.release_approval) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: release_approval is not empty';
    END IF;
    IF EXISTS (SELECT 1 FROM ai.release_decision) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: release_decision is not empty';
    END IF;
    IF EXISTS (SELECT 1 FROM ai.human_evaluation) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: human_evaluation is not empty';
    END IF;
    IF EXISTS (SELECT 1 FROM ai.judge_calibration) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: judge_calibration is not empty';
    END IF;
    IF EXISTS (SELECT 1 FROM ai.evaluation_case_result) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: evaluation_case_result is not empty';
    END IF;
    IF EXISTS (SELECT 1 FROM ai.evaluation_run) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: evaluation_run is not empty';
    END IF;
    IF EXISTS (SELECT 1 FROM ai.evaluation_case) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: evaluation_case is not empty';
    END IF;
    IF EXISTS (SELECT 1 FROM ai.evaluation_dataset_version) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: evaluation_dataset_version is not empty';
    END IF;
    IF EXISTS (SELECT 1 FROM ai.evaluation_suite) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: evaluation_suite is not empty';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM ai.ai_job
         WHERE status NOT IN (
             'REQUESTED',
             'RUNNING',
             'SUCCEEDED',
             'FAILED_TERMINAL',
             'CANCELLED'
         )
    ) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: canonical-only AI Job state exists (VALIDATING_INPUT, QUEUED, VALIDATING_OUTPUT, AWAITING_HUMAN, FAILED_RETRYABLE, RETRY_SCHEDULED, QUARANTINED, EXPIRED)';
    END IF;
    IF EXISTS (
        SELECT 1
         FROM ai.ai_job
         WHERE policy_bundle_version_id IS NOT NULL
            OR release_decision_id IS NOT NULL
            OR request_config IS DISTINCT FROM '{}'::jsonb
            OR input_manifest_sha256 IS NOT NULL
            OR budget_reserved_jpy IS DISTINCT FROM 0
            OR lock_version IS DISTINCT FROM 0
            OR updated_at IS DISTINCT FROM created_at
    ) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: AI Job fields contain canonical meaning';
    END IF;

    IF EXISTS (
        SELECT 1
         FROM ai.ai_attempt AS attempt
          JOIN ai.model_definition AS model ON model.id = attempt.model_id
         WHERE attempt.requested_model_id IS DISTINCT FROM model.provider_model_id
            OR attempt.resolved_model_id IS DISTINCT FROM model.provider_model_id
            OR attempt.response_fingerprint IS NOT NULL
            OR attempt.provider_region IS NOT NULL
            OR attempt.request_config IS DISTINCT FROM '{}'::jsonb
            OR attempt.validation_status IS DISTINCT FROM CASE attempt.status
                WHEN 'RUNNING' THEN 'PENDING'
                WHEN 'SUCCEEDED' THEN 'PASSED'
                ELSE 'FAILED'
            END
            OR attempt.safety_identifier_hash IS NOT NULL
            OR attempt.repair_attempt_no IS DISTINCT FROM 0
    ) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: AI Attempt fields contain non-baseline meaning';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM ai.prompt_version
         WHERE status NOT IN ('DRAFT', 'ACTIVE')
    ) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: Prompt state is canonical-only or RETIRED is ambiguous with an explicitly classified REJECTED Prompt';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM ai.prompt_version
         WHERE locale IS DISTINCT FROM 'ja-JP'
            OR compiler_version IS NOT NULL
            OR input_contract_sha256 IS NOT NULL
            OR policy_test_status IS DISTINCT FROM 'NOT_EXECUTED'
            OR lock_version IS DISTINCT FROM 0
            OR updated_at IS DISTINCT FROM created_at
            OR author_principal_id IS NOT NULL
    ) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: Prompt fields contain canonical meaning';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM ai.prompt_version
         WHERE status = 'ACTIVE'
         GROUP BY prompt_code
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: locale-aware Prompt actives violate baseline uniqueness';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM ai.model_definition
         WHERE context_window_tokens IS NOT NULL
            OR max_output_tokens IS NOT NULL
            OR knowledge_cutoff IS NOT NULL
            OR metadata_observed_at IS NOT NULL
            OR provider_metadata IS DISTINCT FROM '{}'::jsonb
    ) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: Model fields contain canonical meaning';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM ai.model_route_version
         WHERE status NOT IN ('DRAFT', 'ACTIVE', 'PAUSED', 'RETIRED')
            OR lock_version IS DISTINCT FROM 0
            OR updated_at IS DISTINCT FROM created_at
    ) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: Model Route has canonical-only state or fields (EVALUATING, CERTIFIED, CANARY, ROLLED_BACK)';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM ai.evaluation_result
         WHERE evaluation_run_id IS NOT NULL
            OR evaluation_case_id IS NOT NULL
            OR grader_code IS NOT NULL
            OR slice_key IS NOT NULL
            OR threshold_operator IS NOT NULL
            OR threshold_value IS NOT NULL
            OR proportion_numerator_count IS NOT NULL
            OR proportion_denominator_count IS NOT NULL
            OR judge_calibration_id IS NOT NULL
            OR judge_route_version_id IS NOT NULL
            OR judge_prompt_version_id IS NOT NULL
            OR judge_rubric_artifact_id IS NOT NULL
            OR judge_resolved_model_id IS NOT NULL
            OR judge_grader_version IS NOT NULL
    ) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade refused: Evaluation Result fields contain canonical meaning';
    END IF;
END
$$;

-- Remove dependencies on new governance tables/columns while all writers are
-- frozen and after every losslessness guard has passed.
DROP TRIGGER trg_policy_rule_version_immutable ON policy.rule_version;
DROP TRIGGER trg_policy_bundle_rule_append_only ON policy.bundle_rule;
DROP TRIGGER trg_ai_task_dependency_guard ON ai.task_definition;
DROP TRIGGER trg_ai_prompt_dependency_guard ON ai.prompt_version;
DROP TRIGGER trg_ai_route_dependency_guard ON ai.model_route_version;
DROP TRIGGER trg_ai_schema_dependency_guard ON ai.output_schema_version;
DROP TRIGGER trg_ai_model_dependency_guard ON ai.model_definition;
DROP TRIGGER trg_policy_bundle_dependency_guard ON policy.policy_bundle;
DROP TRIGGER trg_ai_task_definition_lifecycle ON ai.task_definition;
DROP TRIGGER trg_ai_prompt_version_lifecycle ON ai.prompt_version;
DROP TRIGGER trg_ai_model_route_lifecycle ON ai.model_route_version;
DROP TRIGGER trg_ai_output_schema_lifecycle ON ai.output_schema_version;
DROP TRIGGER trg_ai_model_definition_lifecycle ON ai.model_definition;
DROP TRIGGER trg_policy_bundle_lifecycle ON policy.policy_bundle;
DROP TRIGGER trg_ai_evaluated_attempt_immutable ON ai.ai_attempt;
DROP TRIGGER trg_ai_evaluated_job_binding ON ai.ai_job;
DROP TRIGGER trg_ai_eval_metric_mutation ON ai.evaluation_result;

DROP TRIGGER trg_ai_eval_suite_canonical_config ON ai.evaluation_suite;
DROP TRIGGER trg_ai_eval_suite_mutation ON ai.evaluation_suite;
DROP TRIGGER trg_ai_eval_dataset_locked ON ai.evaluation_dataset_version;
DROP TRIGGER trg_ai_eval_case_mutation ON ai.evaluation_case;
DROP TRIGGER trg_ai_eval_run_start_integrity ON ai.evaluation_run;
DROP TRIGGER trg_ai_eval_run_completion_evidence ON ai.evaluation_run;
DROP TRIGGER trg_ai_eval_run_mutation ON ai.evaluation_run;
DROP TRIGGER trg_ai_eval_case_result_open_run ON ai.evaluation_case_result;
DROP TRIGGER trg_ai_eval_case_result_immutable ON ai.evaluation_case_result;
DROP TRIGGER trg_ai_human_eval_open_run ON ai.human_evaluation;
DROP TRIGGER trg_ai_human_eval_immutable ON ai.human_evaluation;
DROP TRIGGER trg_ai_judge_cal_scope ON ai.judge_calibration;
DROP TRIGGER trg_ai_judge_cal_mutation ON ai.judge_calibration;
DROP TRIGGER trg_ai_release_decision_evidence ON ai.release_decision;
DROP TRIGGER trg_ai_00_release_task_serialization ON ai.release_decision;
DROP TRIGGER trg_ai_release_decision_mutation ON ai.release_decision;
DROP TRIGGER trg_ai_release_approval_immutable ON ai.release_approval;

-- Every non-constraint index introduced by 008/renamed by 011 is removed by
-- name.  Constraint-owned primary/unique indexes disappear with their table.
DROP INDEX ai.uq_ai_prompt_task_locale_active;
DROP INDEX ai.ix_ai_job_policy_bundle;
DROP INDEX ai.ix_ai_job_release_decision;
DROP INDEX ai.ix_ai_eval_result_run_id;
DROP INDEX ai.ix_ai_eval_result_case_id;
DROP INDEX ai.uq_ai_eval_result_run_case_metric;
DROP INDEX ai.ix_ai_prompt_author;
DROP INDEX ai.ix_ai_eval_result_judge_cal;

DROP INDEX ai.ix_ai_eval_suite_task;
DROP INDEX ai.ix_ai_eval_suite_rubric;
DROP INDEX ai.ix_ai_eval_suite_approver;
DROP INDEX ai.ix_ai_eval_dataset_artifact;
DROP INDEX ai.ix_ai_eval_dataset_locker;
DROP INDEX ai.ix_ai_eval_case_task_split;
DROP INDEX ai.ix_ai_eval_case_input;
DROP INDEX ai.ix_ai_eval_case_gold;
DROP INDEX ai.ix_ai_eval_run_suite_status;
DROP INDEX ai.ix_ai_eval_run_dataset;
DROP INDEX ai.ix_ai_eval_run_baseline;
DROP INDEX ai.ix_ai_eval_run_prompt;
DROP INDEX ai.ix_ai_eval_run_route;
DROP INDEX ai.ix_ai_eval_run_schema;
DROP INDEX ai.ix_ai_eval_run_policy;
DROP INDEX ai.ix_ai_eval_run_manifest;
DROP INDEX ai.ix_ai_eval_run_creator;
DROP INDEX ai.ix_ai_eval_run_resolved_model;
DROP INDEX ai.ix_ai_eval_case_result_run_status;
DROP INDEX ai.ix_ai_eval_case_result_case;
DROP INDEX ai.ix_ai_eval_case_result_attempt;
DROP INDEX ai.ix_ai_eval_case_result_output;
DROP INDEX ai.ix_ai_eval_case_result_zero_tolerance_artifact;
DROP INDEX ai.ix_ai_human_eval_result;
DROP INDEX ai.ix_ai_human_eval_reviewer;
DROP INDEX ai.ix_ai_human_eval_notes;
DROP INDEX ai.ix_ai_judge_cal_route;
DROP INDEX ai.ix_ai_judge_cal_prompt;
DROP INDEX ai.ix_ai_judge_cal_dataset;
DROP INDEX ai.ix_ai_judge_cal_report;
DROP INDEX ai.ix_ai_judge_cal_approver;
DROP INDEX ai.ix_ai_judge_cal_task;
DROP INDEX ai.ix_ai_judge_cal_model;
DROP INDEX ai.ix_ai_judge_cal_rubric;
DROP INDEX ai.ix_ai_release_task_status;
DROP INDEX ai.ix_ai_release_prompt;
DROP INDEX ai.ix_ai_release_route;
DROP INDEX ai.ix_ai_release_schema;
DROP INDEX ai.ix_ai_release_model;
DROP INDEX ai.ix_ai_release_policy;
DROP INDEX ai.ix_ai_release_dataset;
DROP INDEX ai.ix_ai_release_run;
DROP INDEX ai.ix_ai_release_rollback;
DROP INDEX ai.ix_ai_release_approver;
DROP INDEX ai.ix_ai_release_second_approver;
DROP INDEX ai.ix_ai_release_revoker;
DROP INDEX ai.ix_ai_release_judge_cal;
DROP INDEX ai.ix_ai_release_runbook;
DROP INDEX ai.ix_ai_release_monitor;
DROP INDEX ai.ix_ai_release_evidence;
DROP INDEX ai.ix_ai_release_canary_approval;
DROP INDEX ai.ix_ai_release_active_approval;
DROP INDEX ai.ix_ai_release_approval_primary;
DROP INDEX ai.ix_ai_release_approval_second;
DROP INDEX ai.ix_ai_release_approval_artifact;

ALTER TABLE ai.ai_job
    DROP CONSTRAINT ck_ai_job_status,
    DROP CONSTRAINT ck_ai_job_complete,
    DROP CONSTRAINT ck_ai_job_request_config,
    DROP CONSTRAINT ck_ai_job_manifest_sha,
    DROP CONSTRAINT ck_ai_job_budget_reserved,
    DROP CONSTRAINT ck_ai_job_lock_version,
    DROP CONSTRAINT fk_ai_job_policy_bundle,
    DROP CONSTRAINT fk_ai_job_release_decision;

ALTER TABLE ai.ai_attempt
    DROP CONSTRAINT ck_ai_attempt_requested_model,
    DROP CONSTRAINT ck_ai_attempt_resolved_model,
    DROP CONSTRAINT ck_ai_attempt_fingerprint,
    DROP CONSTRAINT ck_ai_attempt_region,
    DROP CONSTRAINT ck_ai_attempt_request_config,
    DROP CONSTRAINT ck_ai_attempt_validation,
    DROP CONSTRAINT ck_ai_attempt_safety_hash,
    DROP CONSTRAINT ck_ai_attempt_repair;

ALTER TABLE ai.prompt_version
    DROP CONSTRAINT ck_ai_prompt_status,
    DROP CONSTRAINT ck_ai_prompt_locale,
    DROP CONSTRAINT ck_ai_prompt_compiler,
    DROP CONSTRAINT ck_ai_prompt_input_hash,
    DROP CONSTRAINT ck_ai_prompt_policy_test,
    DROP CONSTRAINT ck_ai_prompt_lock_version,
    DROP CONSTRAINT fk_ai_prompt_author;

ALTER TABLE ai.model_definition
    DROP CONSTRAINT ck_ai_model_context,
    DROP CONSTRAINT ck_ai_model_output,
    DROP CONSTRAINT ck_ai_model_metadata;

ALTER TABLE ai.model_route_version
    DROP CONSTRAINT ck_ai_route_status,
    DROP CONSTRAINT ck_ai_route_lock_version;

ALTER TABLE ai.evaluation_result
    DROP CONSTRAINT ck_ai_eval_result_run_binding,
    DROP CONSTRAINT ck_ai_eval_result_threshold,
    DROP CONSTRAINT ck_ai_eval_result_grader,
    DROP CONSTRAINT ck_ai_eval_result_slice,
    DROP CONSTRAINT ck_ai_eval_result_proportion_counts,
    DROP CONSTRAINT fk_ai_eval_result_run,
    DROP CONSTRAINT fk_ai_eval_result_case,
    DROP CONSTRAINT ck_ai_eval_result_judge_provenance,
    DROP CONSTRAINT fk_ai_eval_result_judge_cal,
    DROP CONSTRAINT fk_ai_eval_result_judge_route,
    DROP CONSTRAINT fk_ai_eval_result_judge_prompt,
    DROP CONSTRAINT fk_ai_eval_result_judge_rubric,
    DROP CONSTRAINT fk_ai_eval_result_judge_model;

-- Break the release_decision <-> release_approval cycle explicitly.  No
-- CASCADE is used: any unlisted dependency makes the transaction fail closed.
ALTER TABLE ai.release_decision
    DROP CONSTRAINT fk_ai_release_canary_approval,
    DROP CONSTRAINT fk_ai_release_active_approval;
ALTER TABLE ai.release_approval
    DROP CONSTRAINT fk_ai_release_approval_release;

DROP FUNCTION ai.guard_release_task_serialization();
DROP FUNCTION ai.guard_release_decision_evidence();
DROP FUNCTION ai.assert_regression_against_baseline(uuid, uuid);

DROP TABLE ai.release_approval;
DROP TABLE ai.release_decision;
DROP TABLE ai.human_evaluation;
DROP TABLE ai.judge_calibration;
DROP TABLE ai.evaluation_case_result;
DROP TABLE ai.evaluation_run;
DROP TABLE ai.evaluation_case;
DROP TABLE ai.evaluation_dataset_version;
DROP TABLE ai.evaluation_suite;

DROP FUNCTION ai.guard_release_decision_mutation();
DROP FUNCTION ai.guard_judge_calibration_mutation();
DROP FUNCTION ai.guard_evaluation_suite_mutation();
DROP FUNCTION ai.guard_open_human_evaluation();
DROP FUNCTION ai.guard_open_evaluation_run_result();
DROP FUNCTION ai.guard_evaluated_attempt_immutability();
DROP FUNCTION ai.guard_evaluated_job_binding();
DROP FUNCTION ai.guard_evaluation_run_mutation();
DROP FUNCTION ai.guard_evaluation_case_mutation();
DROP FUNCTION ai.guard_locked_evaluation_dataset();
DROP FUNCTION ai.guard_evaluation_metric_mutation();
DROP FUNCTION ai.guard_canonical_suite_config();
DROP FUNCTION ai.guard_evaluation_run_start_integrity();
DROP FUNCTION ai.guard_judge_calibration_scope();
DROP FUNCTION ai.guard_release_approval_mutation();
DROP FUNCTION ai.guard_evaluation_run_completion_evidence();
DROP FUNCTION ai.guard_governance_component_dependency();
DROP FUNCTION policy.guard_rule_version_immutability();
DROP FUNCTION policy.guard_bundle_rule_append_only();
DROP FUNCTION ai.guard_task_definition_lifecycle();
DROP FUNCTION ai.guard_prompt_version_lifecycle();
DROP FUNCTION ai.guard_model_route_lifecycle();
DROP FUNCTION ai.guard_output_schema_lifecycle();
DROP FUNCTION ai.guard_model_definition_lifecycle();
DROP FUNCTION policy.guard_policy_bundle_lifecycle();
DROP FUNCTION ai.assert_evaluation_run_evidence(uuid, boolean);
DROP FUNCTION ai.canonical_regression_margin(text);
DROP FUNCTION ai.canonical_metric_direction(text);
DROP FUNCTION ai.canonical_metric_unit(text);
DROP FUNCTION ai.canonical_suite_risk(text);
DROP FUNCTION ai.canonical_suite_config(text);
DROP FUNCTION ai.canonical_grader_output_metrics(text);
DROP FUNCTION ai.artifact_matches_immutable_hash(uuid, text);
DROP FUNCTION ai.has_live_rollback_dependents(text, uuid);

UPDATE ai.ai_job
   SET status = CASE status
       WHEN 'REQUESTED' THEN 'PENDING'
       WHEN 'FAILED_TERMINAL' THEN 'FAILED'
       ELSE status
   END
 WHERE status IN ('REQUESTED', 'FAILED_TERMINAL');

ALTER TABLE ai.ai_job
    ALTER COLUMN status SET DEFAULT 'PENDING',
    DROP COLUMN policy_bundle_version_id,
    DROP COLUMN release_decision_id,
    DROP COLUMN request_config,
    DROP COLUMN input_manifest_sha256,
    DROP COLUMN budget_reserved_jpy,
    DROP COLUMN lock_version,
    DROP COLUMN updated_at,
    ADD CONSTRAINT ck_ai_job_status CHECK (
        status IN (
            'PENDING',
            'RUNNING',
            'SUCCEEDED',
            'FAILED',
            'BLOCKED',
            'CANCELLED'
        )
    ),
    ADD CONSTRAINT ck_ai_job_complete CHECK (
        status NOT IN ('SUCCEEDED', 'FAILED', 'BLOCKED', 'CANCELLED')
        OR completed_at IS NOT NULL
    );

ALTER TABLE ai.ai_attempt
    DROP COLUMN requested_model_id,
    DROP COLUMN resolved_model_id,
    DROP COLUMN response_fingerprint,
    DROP COLUMN provider_region,
    DROP COLUMN request_config,
    DROP COLUMN validation_status,
    DROP COLUMN safety_identifier_hash,
    DROP COLUMN repair_attempt_no;

ALTER TABLE ai.prompt_version
    ALTER COLUMN author_principal_id DROP NOT NULL;

ALTER TABLE ai.prompt_version
    DROP COLUMN locale,
    DROP COLUMN compiler_version,
    DROP COLUMN input_contract_sha256,
    DROP COLUMN policy_test_status,
    DROP COLUMN lock_version,
    DROP COLUMN updated_at,
    DROP COLUMN author_principal_id,
    ADD CONSTRAINT ck_ai_prompt_status CHECK (
        status IN ('DRAFT', 'ACTIVE', 'RETIRED', 'REJECTED')
    );

CREATE UNIQUE INDEX uq_ai_prompt_active
    ON ai.prompt_version (prompt_code)
    WHERE status = 'ACTIVE';

ALTER TABLE ai.model_definition
    DROP COLUMN context_window_tokens,
    DROP COLUMN max_output_tokens,
    DROP COLUMN knowledge_cutoff,
    DROP COLUMN metadata_observed_at,
    DROP COLUMN provider_metadata;

ALTER TABLE ai.model_route_version
    DROP COLUMN lock_version,
    DROP COLUMN updated_at,
    ADD CONSTRAINT ck_ai_route_status CHECK (
        status IN ('DRAFT', 'ACTIVE', 'PAUSED', 'RETIRED')
    );

ALTER TABLE ai.evaluation_result
    ALTER COLUMN passed SET NOT NULL,
    DROP COLUMN evaluation_run_id,
    DROP COLUMN evaluation_case_id,
    DROP COLUMN grader_code,
    DROP COLUMN slice_key,
    DROP COLUMN threshold_operator,
    DROP COLUMN threshold_value,
    DROP COLUMN proportion_numerator_count,
    DROP COLUMN proportion_denominator_count,
    DROP COLUMN judge_calibration_id,
    DROP COLUMN judge_route_version_id,
    DROP COLUMN judge_prompt_version_id,
    DROP COLUMN judge_rubric_artifact_id,
    DROP COLUMN judge_resolved_model_id,
    DROP COLUMN judge_grader_version;

-- Restore the exact predecessor worker ACL.  ST-0003 replaces the broad
-- authority-plane table grants with narrower runtime grants; a successful
-- downgrade must not leave that ST-0003 ACL shape behind.
REVOKE INSERT (
    id,
    quality_check_run_id,
    rule_version_id,
    finding_code,
    severity,
    is_blocking,
    entity_type,
    entity_id,
    article_block_id,
    claim_id,
    message,
    evidence,
    created_at
) ON policy.finding FROM raos_worker_rw;

GRANT INSERT, UPDATE ON TABLE
    ai.task_definition,
    ai.prompt_version,
    ai.output_schema_version,
    ai.model_definition,
    ai.model_route_version,
    policy.policy_bundle,
    policy.rule_version,
    policy.bundle_rule,
    policy.finding,
    policy.waiver,
    policy.gate_decision
TO raos_worker_rw;

DO $$
DECLARE
    forbidden_name text;
    restored_relation text;
BEGIN
    FOREACH forbidden_name IN ARRAY ARRAY[
        'ai.evaluation_suite',
        'ai.evaluation_dataset_version',
        'ai.evaluation_case',
        'ai.evaluation_run',
        'ai.evaluation_case_result',
        'ai.human_evaluation',
        'ai.judge_calibration',
        'ai.release_decision',
        'ai.release_approval'
    ]
    LOOP
        IF to_regclass(forbidden_name) IS NOT NULL THEN
            RAISE EXCEPTION
                'ST-0003 downgrade internal error: table % survived',
                forbidden_name;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE (table_schema, table_name, column_name) IN (
            ('ai', 'ai_job', 'policy_bundle_version_id'),
            ('ai', 'ai_job', 'release_decision_id'),
            ('ai', 'ai_job', 'request_config'),
            ('ai', 'ai_job', 'input_manifest_sha256'),
            ('ai', 'ai_job', 'budget_reserved_jpy'),
            ('ai', 'ai_job', 'lock_version'),
            ('ai', 'ai_job', 'updated_at'),
            ('ai', 'ai_attempt', 'requested_model_id'),
            ('ai', 'ai_attempt', 'resolved_model_id'),
            ('ai', 'ai_attempt', 'response_fingerprint'),
            ('ai', 'ai_attempt', 'provider_region'),
            ('ai', 'ai_attempt', 'request_config'),
            ('ai', 'ai_attempt', 'validation_status'),
            ('ai', 'ai_attempt', 'safety_identifier_hash'),
            ('ai', 'ai_attempt', 'repair_attempt_no'),
            ('ai', 'prompt_version', 'locale'),
            ('ai', 'prompt_version', 'compiler_version'),
            ('ai', 'prompt_version', 'input_contract_sha256'),
            ('ai', 'prompt_version', 'policy_test_status'),
            ('ai', 'prompt_version', 'lock_version'),
            ('ai', 'prompt_version', 'updated_at'),
            ('ai', 'prompt_version', 'author_principal_id'),
            ('ai', 'model_definition', 'context_window_tokens'),
            ('ai', 'model_definition', 'max_output_tokens'),
            ('ai', 'model_definition', 'knowledge_cutoff'),
            ('ai', 'model_definition', 'metadata_observed_at'),
            ('ai', 'model_definition', 'provider_metadata'),
            ('ai', 'model_route_version', 'lock_version'),
            ('ai', 'model_route_version', 'updated_at'),
            ('ai', 'evaluation_result', 'evaluation_run_id'),
            ('ai', 'evaluation_result', 'evaluation_case_id'),
            ('ai', 'evaluation_result', 'grader_code'),
            ('ai', 'evaluation_result', 'slice_key'),
            ('ai', 'evaluation_result', 'threshold_operator'),
            ('ai', 'evaluation_result', 'threshold_value'),
            ('ai', 'evaluation_result', 'proportion_numerator_count'),
            ('ai', 'evaluation_result', 'proportion_denominator_count'),
            ('ai', 'evaluation_result', 'judge_calibration_id'),
            ('ai', 'evaluation_result', 'judge_route_version_id'),
            ('ai', 'evaluation_result', 'judge_prompt_version_id'),
            ('ai', 'evaluation_result', 'judge_rubric_artifact_id'),
            ('ai', 'evaluation_result', 'judge_resolved_model_id'),
            ('ai', 'evaluation_result', 'judge_grader_version')
         )
    ) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade internal error: an added column survived';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'ai'
           AND table_name = 'evaluation_result'
           AND column_name = 'passed'
           AND is_nullable = 'NO'
    ) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade internal error: evaluation_result.passed nullability was not restored';
    END IF;

    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE (conrelid, conname) IN (
            ('ai.ai_job'::regclass, 'ck_ai_job_status'),
            ('ai.ai_job'::regclass, 'ck_ai_job_complete'),
            ('ai.prompt_version'::regclass, 'ck_ai_prompt_status'),
            ('ai.model_route_version'::regclass, 'ck_ai_route_status')
         )
           AND convalidated
    ) <> 4
       OR to_regclass('ai.uq_ai_prompt_active') IS NULL THEN
        RAISE EXCEPTION
            'ST-0003 downgrade internal error: ST-0002 constraints/index were not restored';
    END IF;

    FOREACH restored_relation IN ARRAY ARRAY[
        'ai.task_definition',
        'ai.prompt_version',
        'ai.output_schema_version',
        'ai.model_definition',
        'ai.model_route_version',
        'policy.policy_bundle',
        'policy.rule_version',
        'policy.bundle_rule',
        'policy.finding',
        'policy.waiver',
        'policy.gate_decision'
    ]
    LOOP
        IF NOT has_table_privilege(
               'raos_worker_rw', restored_relation, 'SELECT'
           )
           OR NOT has_table_privilege(
               'raos_worker_rw', restored_relation, 'INSERT'
           )
           OR NOT has_table_privilege(
               'raos_worker_rw', restored_relation, 'UPDATE'
           )
           OR has_table_privilege(
               'raos_worker_rw', restored_relation, 'DELETE'
           ) THEN
            RAISE EXCEPTION
                'ST-0003 downgrade internal error: predecessor worker ACL was not restored on %',
                restored_relation;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1
          FROM pg_attribute AS attribute
          CROSS JOIN LATERAL aclexplode(attribute.attacl) AS privilege
         WHERE attribute.attrelid = 'policy.finding'::regclass
           AND privilege.grantee =
                (SELECT oid FROM pg_roles WHERE rolname = 'raos_worker_rw')
    ) THEN
        RAISE EXCEPTION
            'ST-0003 downgrade internal error: worker column ACL survived on policy.finding';
    END IF;
END
$$;

COMMIT;
