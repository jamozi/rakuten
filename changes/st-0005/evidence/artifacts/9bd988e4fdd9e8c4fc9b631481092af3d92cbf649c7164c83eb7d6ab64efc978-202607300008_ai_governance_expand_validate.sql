-- ST-0003 / INT-DEC-004
-- Phase: EXPAND VALIDATE AND INDEX
-- Requires: 202607300007_ai_governance_expand.sql
--
-- Validation commits before concurrent index creation. This avoids retaining
-- the Expand metadata locks during scans and makes every index an independently
-- inspectable recovery point.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '15min';

DO $$
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0003 requires PostgreSQL 18 or later';
    END IF;
    IF (
        SELECT count(*)
          FROM information_schema.tables
         WHERE table_schema = 'ai'
           AND table_name IN (
               'evaluation_suite',
               'evaluation_dataset_version',
               'evaluation_case',
               'evaluation_run',
               'evaluation_case_result',
               'human_evaluation',
               'judge_calibration',
               'release_decision',
               'release_approval'
           )
    ) <> 9 THEN
        RAISE EXCEPTION 'ST-0003 validation requires all nine governance tables';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE (conrelid, conname) IN (
             ('ai.ai_job'::regclass, 'ck_ai_job_status'),
             ('ai.ai_job'::regclass, 'ck_ai_job_complete'),
             ('ai.prompt_version'::regclass, 'ck_ai_prompt_status'),
             ('ai.model_route_version'::regclass, 'ck_ai_route_status')
         )
    ) THEN
        RAISE EXCEPTION 'ST-0003 validation found a blocking predecessor constraint';
    END IF;
END
$$;

ALTER TABLE ai.ai_job
    VALIDATE CONSTRAINT ck_ai_job_status_st0003_expand;
ALTER TABLE ai.ai_job
    VALIDATE CONSTRAINT ck_ai_job_complete_st0003_expand;
ALTER TABLE ai.ai_job
    VALIDATE CONSTRAINT ck_ai_job_request_config_st0003_expand;
ALTER TABLE ai.ai_job
    VALIDATE CONSTRAINT ck_ai_job_manifest_sha_st0003_expand;
ALTER TABLE ai.ai_job
    VALIDATE CONSTRAINT ck_ai_job_budget_reserved_st0003_expand;
ALTER TABLE ai.ai_job
    VALIDATE CONSTRAINT ck_ai_job_lock_version_st0003_expand;
ALTER TABLE ai.ai_job
    VALIDATE CONSTRAINT fk_ai_job_policy_bundle_st0003_expand;
ALTER TABLE ai.ai_job
    VALIDATE CONSTRAINT fk_ai_job_release_decision_st0003_expand;

ALTER TABLE ai.ai_attempt
    VALIDATE CONSTRAINT ck_ai_attempt_requested_model_st0003_expand;
ALTER TABLE ai.ai_attempt
    VALIDATE CONSTRAINT ck_ai_attempt_resolved_model_st0003_expand;
ALTER TABLE ai.ai_attempt
    VALIDATE CONSTRAINT ck_ai_attempt_fingerprint_st0003_expand;
ALTER TABLE ai.ai_attempt
    VALIDATE CONSTRAINT ck_ai_attempt_region_st0003_expand;
ALTER TABLE ai.ai_attempt
    VALIDATE CONSTRAINT ck_ai_attempt_request_config_st0003_expand;
ALTER TABLE ai.ai_attempt
    VALIDATE CONSTRAINT ck_ai_attempt_validation_st0003_expand;
ALTER TABLE ai.ai_attempt
    VALIDATE CONSTRAINT ck_ai_attempt_safety_hash_st0003_expand;
ALTER TABLE ai.ai_attempt
    VALIDATE CONSTRAINT ck_ai_attempt_repair_st0003_expand;

ALTER TABLE ai.prompt_version
    VALIDATE CONSTRAINT ck_ai_prompt_status_st0003_expand;
ALTER TABLE ai.prompt_version
    VALIDATE CONSTRAINT ck_ai_prompt_locale_st0003_expand;
ALTER TABLE ai.prompt_version
    VALIDATE CONSTRAINT ck_ai_prompt_compiler_st0003_expand;
ALTER TABLE ai.prompt_version
    VALIDATE CONSTRAINT ck_ai_prompt_input_hash_st0003_expand;
ALTER TABLE ai.prompt_version
    VALIDATE CONSTRAINT ck_ai_prompt_policy_test_st0003_expand;
ALTER TABLE ai.prompt_version
    VALIDATE CONSTRAINT ck_ai_prompt_lock_version_st0003_expand;
ALTER TABLE ai.prompt_version
    VALIDATE CONSTRAINT fk_ai_prompt_author_st0003_expand;

ALTER TABLE ai.model_definition
    VALIDATE CONSTRAINT ck_ai_model_context_st0003_expand;
ALTER TABLE ai.model_definition
    VALIDATE CONSTRAINT ck_ai_model_output_st0003_expand;
ALTER TABLE ai.model_definition
    VALIDATE CONSTRAINT ck_ai_model_metadata_st0003_expand;

ALTER TABLE ai.model_route_version
    VALIDATE CONSTRAINT ck_ai_route_status_st0003_expand;
ALTER TABLE ai.model_route_version
    VALIDATE CONSTRAINT ck_ai_route_lock_version_st0003_expand;

ALTER TABLE ai.evaluation_result
    VALIDATE CONSTRAINT ck_ai_eval_result_run_st0003_expand;
ALTER TABLE ai.evaluation_result
    VALIDATE CONSTRAINT ck_ai_eval_result_threshold_st0003_expand;
ALTER TABLE ai.evaluation_result
    VALIDATE CONSTRAINT ck_ai_eval_result_grader_st0003_expand;
ALTER TABLE ai.evaluation_result
    VALIDATE CONSTRAINT ck_ai_eval_result_slice_st0003_expand;
ALTER TABLE ai.evaluation_result
    VALIDATE CONSTRAINT fk_ai_eval_result_run_st0003_expand;
ALTER TABLE ai.evaluation_result
    VALIDATE CONSTRAINT fk_ai_eval_result_case_st0003_expand;
ALTER TABLE ai.evaluation_result
    VALIDATE CONSTRAINT ck_ai_eval_result_judge_provenance_st0003_expand;
ALTER TABLE ai.evaluation_result
    VALIDATE CONSTRAINT fk_ai_eval_result_judge_cal_st0003_expand;
ALTER TABLE ai.evaluation_result
    VALIDATE CONSTRAINT fk_ai_eval_result_judge_route_st0003_expand;
ALTER TABLE ai.evaluation_result
    VALIDATE CONSTRAINT fk_ai_eval_result_judge_prompt_st0003_expand;
ALTER TABLE ai.evaluation_result
    VALIDATE CONSTRAINT fk_ai_eval_result_judge_rubric_st0003_expand;
ALTER TABLE ai.evaluation_result
    VALIDATE CONSTRAINT fk_ai_eval_result_judge_model_st0003_expand;

ALTER TABLE ai.evaluation_suite
    VALIDATE CONSTRAINT fk_ai_eval_suite_task;
ALTER TABLE ai.evaluation_suite
    VALIDATE CONSTRAINT fk_ai_eval_suite_rubric;
ALTER TABLE ai.evaluation_suite
    VALIDATE CONSTRAINT fk_ai_eval_suite_approver;

ALTER TABLE ai.evaluation_dataset_version
    VALIDATE CONSTRAINT fk_ai_eval_dataset_artifact;
ALTER TABLE ai.evaluation_dataset_version
    VALIDATE CONSTRAINT fk_ai_eval_dataset_locker;

ALTER TABLE ai.evaluation_case
    VALIDATE CONSTRAINT fk_ai_eval_case_dataset;
ALTER TABLE ai.evaluation_case
    VALIDATE CONSTRAINT fk_ai_eval_case_task;
ALTER TABLE ai.evaluation_case
    VALIDATE CONSTRAINT fk_ai_eval_case_input;
ALTER TABLE ai.evaluation_case
    VALIDATE CONSTRAINT fk_ai_eval_case_gold;

ALTER TABLE ai.evaluation_run
    VALIDATE CONSTRAINT fk_ai_eval_run_suite;
ALTER TABLE ai.evaluation_run
    VALIDATE CONSTRAINT fk_ai_eval_run_dataset;
ALTER TABLE ai.evaluation_run
    VALIDATE CONSTRAINT fk_ai_eval_run_prompt;
ALTER TABLE ai.evaluation_run
    VALIDATE CONSTRAINT fk_ai_eval_run_route;
ALTER TABLE ai.evaluation_run
    VALIDATE CONSTRAINT fk_ai_eval_run_schema;
ALTER TABLE ai.evaluation_run
    VALIDATE CONSTRAINT fk_ai_eval_run_policy;
ALTER TABLE ai.evaluation_run
    VALIDATE CONSTRAINT fk_ai_eval_run_manifest;
ALTER TABLE ai.evaluation_run
    VALIDATE CONSTRAINT fk_ai_eval_run_creator;
ALTER TABLE ai.evaluation_run
    VALIDATE CONSTRAINT fk_ai_eval_run_resolved_model_st0003_expand;
ALTER TABLE ai.evaluation_run
    VALIDATE CONSTRAINT fk_ai_eval_run_baseline_st0003_expand;
ALTER TABLE ai.evaluation_result
    VALIDATE CONSTRAINT ck_ai_eval_result_proportion_counts_st0003_expand;

ALTER TABLE ai.evaluation_case_result
    VALIDATE CONSTRAINT fk_ai_eval_case_result_run;
ALTER TABLE ai.evaluation_case_result
    VALIDATE CONSTRAINT fk_ai_eval_case_result_case;
ALTER TABLE ai.evaluation_case_result
    VALIDATE CONSTRAINT fk_ai_eval_case_result_attempt;
ALTER TABLE ai.evaluation_case_result
    VALIDATE CONSTRAINT fk_ai_eval_case_result_output;

ALTER TABLE ai.human_evaluation
    VALIDATE CONSTRAINT fk_ai_human_eval_result;
ALTER TABLE ai.human_evaluation
    VALIDATE CONSTRAINT fk_ai_human_eval_reviewer;
ALTER TABLE ai.human_evaluation
    VALIDATE CONSTRAINT fk_ai_human_eval_notes;

ALTER TABLE ai.judge_calibration
    VALIDATE CONSTRAINT fk_ai_judge_cal_route;
ALTER TABLE ai.judge_calibration
    VALIDATE CONSTRAINT fk_ai_judge_cal_prompt;
ALTER TABLE ai.judge_calibration
    VALIDATE CONSTRAINT fk_ai_judge_cal_dataset;
ALTER TABLE ai.judge_calibration
    VALIDATE CONSTRAINT fk_ai_judge_cal_report;
ALTER TABLE ai.judge_calibration
    VALIDATE CONSTRAINT fk_ai_judge_cal_approver;
ALTER TABLE ai.judge_calibration
    VALIDATE CONSTRAINT ck_ai_judge_cal_rubric_sha_st0003_expand;
ALTER TABLE ai.judge_calibration
    VALIDATE CONSTRAINT ck_ai_judge_cal_grader_version_st0003_expand;
ALTER TABLE ai.judge_calibration
    VALIDATE CONSTRAINT fk_ai_judge_cal_task_st0003_expand;
ALTER TABLE ai.judge_calibration
    VALIDATE CONSTRAINT fk_ai_judge_cal_model_st0003_expand;
ALTER TABLE ai.judge_calibration
    VALIDATE CONSTRAINT fk_ai_judge_cal_rubric_st0003_expand;

ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_task;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_prompt;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_route;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_schema;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_model;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_policy;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_dataset;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_run;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_rollback;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_approver;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_second_approver;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_revoker;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT ck_ai_release_rollback_strategy_st0003_expand;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT ck_ai_release_rollback_binding_st0003_expand;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT ck_ai_release_monitoring_sha_st0003_expand;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT ck_ai_release_evidence_sha_st0003_expand;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT ck_ai_release_canary_time_st0003_expand;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT ck_ai_release_phase_state_st0003_expand;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_judge_cal_st0003_expand;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_rollback_runbook_st0003_expand;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_canary_monitor_st0003_expand;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_canary_evidence_st0003_expand;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_canary_approval_st0003_expand;
ALTER TABLE ai.release_decision
    VALIDATE CONSTRAINT fk_ai_release_active_approval_st0003_expand;

ALTER TABLE ai.release_approval
    VALIDATE CONSTRAINT fk_ai_release_approval_release;
ALTER TABLE ai.release_approval
    VALIDATE CONSTRAINT fk_ai_release_approval_primary;
ALTER TABLE ai.release_approval
    VALIDATE CONSTRAINT fk_ai_release_approval_second;
ALTER TABLE ai.release_approval
    VALIDATE CONSTRAINT fk_ai_release_approval_artifact;

COMMIT;

-- Same-name indexes may be reused only when they are already valid, ready, and
-- definition-exact. This preflight prevents IF NOT EXISTS from masking drift.
SET lock_timeout = '5s';
SET statement_timeout = '15min';

DO $$
DECLARE
    expected record;
BEGIN
    FOR expected IN
        SELECT *
          FROM (VALUES
            ('ai.ix_ai_job_policy_bundle_st0003',
             'CREATE INDEX ix_ai_job_policy_bundle_st0003 ON ai.ai_job USING btree (policy_bundle_version_id)'),
            ('ai.ix_ai_job_release_decision_st0003',
             'CREATE INDEX ix_ai_job_release_decision_st0003 ON ai.ai_job USING btree (release_decision_id)'),
            ('ai.ix_ai_eval_result_run_st0003',
             'CREATE INDEX ix_ai_eval_result_run_st0003 ON ai.evaluation_result USING btree (evaluation_run_id)'),
            ('ai.ix_ai_eval_result_case_st0003',
             'CREATE INDEX ix_ai_eval_result_case_st0003 ON ai.evaluation_result USING btree (evaluation_case_id)'),
            ('ai.uq_ai_eval_result_run_case_metric_st0003',
             'CREATE UNIQUE INDEX uq_ai_eval_result_run_case_metric_st0003 ON ai.evaluation_result USING btree (evaluation_run_id, evaluation_case_id, metric_code)'),
            ('ai.ix_ai_eval_suite_task_st0003',
             'CREATE INDEX ix_ai_eval_suite_task_st0003 ON ai.evaluation_suite USING btree (task_definition_id)'),
            ('ai.ix_ai_eval_suite_rubric_st0003',
             'CREATE INDEX ix_ai_eval_suite_rubric_st0003 ON ai.evaluation_suite USING btree (rubric_artifact_id)'),
            ('ai.ix_ai_eval_suite_approver_st0003',
             'CREATE INDEX ix_ai_eval_suite_approver_st0003 ON ai.evaluation_suite USING btree (approved_by_principal_id)'),
            ('ai.ix_ai_eval_dataset_artifact_st0003',
             'CREATE INDEX ix_ai_eval_dataset_artifact_st0003 ON ai.evaluation_dataset_version USING btree (dataset_artifact_id)'),
            ('ai.ix_ai_eval_dataset_locker_st0003',
             'CREATE INDEX ix_ai_eval_dataset_locker_st0003 ON ai.evaluation_dataset_version USING btree (locked_by_principal_id)'),
            ('ai.ix_ai_eval_case_task_split_st0003',
             'CREATE INDEX ix_ai_eval_case_task_split_st0003 ON ai.evaluation_case USING btree (task_definition_id, split, risk_level)'),
            ('ai.ix_ai_eval_case_input_st0003',
             'CREATE INDEX ix_ai_eval_case_input_st0003 ON ai.evaluation_case USING btree (input_artifact_id)'),
            ('ai.ix_ai_eval_case_gold_st0003',
             'CREATE INDEX ix_ai_eval_case_gold_st0003 ON ai.evaluation_case USING btree (gold_artifact_id)'),
            ('ai.ix_ai_eval_run_suite_status_st0003',
             'CREATE INDEX ix_ai_eval_run_suite_status_st0003 ON ai.evaluation_run USING btree (suite_id, status, created_at DESC)'),
            ('ai.ix_ai_eval_run_dataset_st0003',
             'CREATE INDEX ix_ai_eval_run_dataset_st0003 ON ai.evaluation_run USING btree (dataset_version_id)'),
            ('ai.ix_ai_eval_run_baseline_st0003',
             'CREATE INDEX ix_ai_eval_run_baseline_st0003 ON ai.evaluation_run USING btree (baseline_evaluation_run_id)'),
            ('ai.ix_ai_eval_run_prompt_st0003',
             'CREATE INDEX ix_ai_eval_run_prompt_st0003 ON ai.evaluation_run USING btree (prompt_version_id)'),
            ('ai.ix_ai_eval_run_route_st0003',
             'CREATE INDEX ix_ai_eval_run_route_st0003 ON ai.evaluation_run USING btree (model_route_version_id)'),
            ('ai.ix_ai_eval_run_schema_st0003',
             'CREATE INDEX ix_ai_eval_run_schema_st0003 ON ai.evaluation_run USING btree (output_schema_version_id)'),
            ('ai.ix_ai_eval_run_policy_st0003',
             'CREATE INDEX ix_ai_eval_run_policy_st0003 ON ai.evaluation_run USING btree (policy_bundle_version_id)'),
            ('ai.ix_ai_eval_run_manifest_st0003',
             'CREATE INDEX ix_ai_eval_run_manifest_st0003 ON ai.evaluation_run USING btree (run_manifest_artifact_id)'),
            ('ai.ix_ai_eval_run_creator_st0003',
             'CREATE INDEX ix_ai_eval_run_creator_st0003 ON ai.evaluation_run USING btree (created_by_principal_id)'),
            ('ai.ix_ai_eval_case_result_run_status_st0003',
             'CREATE INDEX ix_ai_eval_case_result_run_status_st0003 ON ai.evaluation_case_result USING btree (evaluation_run_id, status)'),
            ('ai.ix_ai_eval_case_result_case_st0003',
             'CREATE INDEX ix_ai_eval_case_result_case_st0003 ON ai.evaluation_case_result USING btree (evaluation_case_id)'),
            ('ai.ix_ai_eval_case_result_attempt_st0003',
             'CREATE INDEX ix_ai_eval_case_result_attempt_st0003 ON ai.evaluation_case_result USING btree (ai_attempt_id)'),
            ('ai.ix_ai_eval_case_result_output_st0003',
             'CREATE INDEX ix_ai_eval_case_result_output_st0003 ON ai.evaluation_case_result USING btree (output_artifact_id)'),
            ('ai.ix_ai_eval_case_result_zero_tolerance_artifact_st0003',
             'CREATE INDEX ix_ai_eval_case_result_zero_tolerance_artifact_st0003 ON ai.evaluation_case_result USING btree (zero_tolerance_evidence_artifact_id)'),
            ('ai.ix_ai_human_eval_result_st0003',
             'CREATE INDEX ix_ai_human_eval_result_st0003 ON ai.human_evaluation USING btree (evaluation_case_result_id, created_at)'),
            ('ai.ix_ai_human_eval_reviewer_st0003',
             'CREATE INDEX ix_ai_human_eval_reviewer_st0003 ON ai.human_evaluation USING btree (reviewer_principal_id)'),
            ('ai.ix_ai_human_eval_notes_st0003',
             'CREATE INDEX ix_ai_human_eval_notes_st0003 ON ai.human_evaluation USING btree (notes_artifact_id)'),
            ('ai.ix_ai_judge_cal_route_st0003',
             'CREATE INDEX ix_ai_judge_cal_route_st0003 ON ai.judge_calibration USING btree (judge_route_version_id)'),
            ('ai.ix_ai_judge_cal_prompt_st0003',
             'CREATE INDEX ix_ai_judge_cal_prompt_st0003 ON ai.judge_calibration USING btree (judge_prompt_version_id)'),
            ('ai.ix_ai_judge_cal_dataset_st0003',
             'CREATE INDEX ix_ai_judge_cal_dataset_st0003 ON ai.judge_calibration USING btree (dataset_version_id)'),
            ('ai.ix_ai_judge_cal_report_st0003',
             'CREATE INDEX ix_ai_judge_cal_report_st0003 ON ai.judge_calibration USING btree (report_artifact_id)'),
            ('ai.ix_ai_judge_cal_approver_st0003',
             'CREATE INDEX ix_ai_judge_cal_approver_st0003 ON ai.judge_calibration USING btree (approved_by_principal_id)'),
            ('ai.ix_ai_release_task_status_st0003',
             'CREATE INDEX ix_ai_release_task_status_st0003 ON ai.release_decision USING btree (task_definition_id, status, approved_at DESC)'),
            ('ai.ix_ai_release_prompt_st0003',
             'CREATE INDEX ix_ai_release_prompt_st0003 ON ai.release_decision USING btree (prompt_version_id)'),
            ('ai.ix_ai_release_route_st0003',
             'CREATE INDEX ix_ai_release_route_st0003 ON ai.release_decision USING btree (model_route_version_id)'),
            ('ai.ix_ai_release_schema_st0003',
             'CREATE INDEX ix_ai_release_schema_st0003 ON ai.release_decision USING btree (output_schema_version_id)'),
            ('ai.ix_ai_release_model_st0003',
             'CREATE INDEX ix_ai_release_model_st0003 ON ai.release_decision USING btree (resolved_model_id)'),
            ('ai.ix_ai_release_policy_st0003',
             'CREATE INDEX ix_ai_release_policy_st0003 ON ai.release_decision USING btree (policy_bundle_version_id)'),
            ('ai.ix_ai_release_dataset_st0003',
             'CREATE INDEX ix_ai_release_dataset_st0003 ON ai.release_decision USING btree (dataset_version_id)'),
            ('ai.ix_ai_release_run_st0003',
             'CREATE INDEX ix_ai_release_run_st0003 ON ai.release_decision USING btree (evaluation_run_id)'),
            ('ai.ix_ai_release_rollback_st0003',
             'CREATE INDEX ix_ai_release_rollback_st0003 ON ai.release_decision USING btree (rollback_release_decision_id)'),
            ('ai.ix_ai_release_approver_st0003',
             'CREATE INDEX ix_ai_release_approver_st0003 ON ai.release_decision USING btree (approved_by_principal_id)'),
            ('ai.ix_ai_release_second_approver_st0003',
             'CREATE INDEX ix_ai_release_second_approver_st0003 ON ai.release_decision USING btree (second_approver_principal_id)'),
            ('ai.ix_ai_release_revoker_st0003',
             'CREATE INDEX ix_ai_release_revoker_st0003 ON ai.release_decision USING btree (revoked_by_principal_id)'),
            ('ai.ix_ai_prompt_author_st0003',
             'CREATE INDEX ix_ai_prompt_author_st0003 ON ai.prompt_version USING btree (author_principal_id)'),
            ('ai.ix_ai_eval_run_resolved_model_st0003',
             'CREATE INDEX ix_ai_eval_run_resolved_model_st0003 ON ai.evaluation_run USING btree (resolved_model_id)'),
            ('ai.ix_ai_eval_result_judge_cal_st0003',
             'CREATE INDEX ix_ai_eval_result_judge_cal_st0003 ON ai.evaluation_result USING btree (judge_calibration_id)'),
            ('ai.ix_ai_judge_cal_task_st0003',
             'CREATE INDEX ix_ai_judge_cal_task_st0003 ON ai.judge_calibration USING btree (evaluated_task_definition_id)'),
            ('ai.ix_ai_judge_cal_model_st0003',
             'CREATE INDEX ix_ai_judge_cal_model_st0003 ON ai.judge_calibration USING btree (resolved_judge_model_id)'),
            ('ai.ix_ai_judge_cal_rubric_st0003',
             'CREATE INDEX ix_ai_judge_cal_rubric_st0003 ON ai.judge_calibration USING btree (rubric_artifact_id)'),
            ('ai.ix_ai_release_judge_cal_st0003',
             'CREATE INDEX ix_ai_release_judge_cal_st0003 ON ai.release_decision USING btree (judge_calibration_id)'),
            ('ai.ix_ai_release_runbook_st0003',
             'CREATE INDEX ix_ai_release_runbook_st0003 ON ai.release_decision USING btree (rollback_runbook_artifact_id)'),
            ('ai.ix_ai_release_monitor_st0003',
             'CREATE INDEX ix_ai_release_monitor_st0003 ON ai.release_decision USING btree (canary_monitoring_artifact_id)'),
            ('ai.ix_ai_release_evidence_st0003',
             'CREATE INDEX ix_ai_release_evidence_st0003 ON ai.release_decision USING btree (canary_evidence_artifact_id)'),
            ('ai.ix_ai_release_canary_approval_st0003',
             'CREATE INDEX ix_ai_release_canary_approval_st0003 ON ai.release_decision USING btree (canary_approval_id)'),
            ('ai.ix_ai_release_active_approval_st0003',
             'CREATE INDEX ix_ai_release_active_approval_st0003 ON ai.release_decision USING btree (active_approval_id)'),
            ('ai.ix_ai_release_approval_primary_st0003',
             'CREATE INDEX ix_ai_release_approval_primary_st0003 ON ai.release_approval USING btree (primary_approver_principal_id)'),
            ('ai.ix_ai_release_approval_second_st0003',
             'CREATE INDEX ix_ai_release_approval_second_st0003 ON ai.release_approval USING btree (second_approver_principal_id)'),
            ('ai.ix_ai_release_approval_artifact_st0003',
             'CREATE INDEX ix_ai_release_approval_artifact_st0003 ON ai.release_approval USING btree (approval_artifact_id)'),
            ('ai.uq_ai_prompt_task_locale_active_st0003',
             'CREATE UNIQUE INDEX uq_ai_prompt_task_locale_active_st0003 ON ai.prompt_version USING btree (task_definition_id, locale) WHERE (status = ''ACTIVE''::text)')
          ) AS definitions(index_name, definition)
    LOOP
        IF to_regclass(expected.index_name) IS NOT NULL
           AND NOT EXISTS (
               SELECT 1
                 FROM pg_index
                WHERE indexrelid = to_regclass(expected.index_name)
                  AND indisvalid
                  AND indisready
                  AND pg_get_indexdef(indexrelid) = expected.definition
           ) THEN
            RAISE EXCEPTION
                'ST-0003 index % exists but is invalid or definition-drifted',
                expected.index_name;
        END IF;
    END LOOP;
END
$$;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_job_policy_bundle_st0003
    ON ai.ai_job (policy_bundle_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_job_release_decision_st0003
    ON ai.ai_job (release_decision_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_result_run_st0003
    ON ai.evaluation_result (evaluation_run_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_result_case_st0003
    ON ai.evaluation_result (evaluation_case_id);
CREATE UNIQUE INDEX CONCURRENTLY
    IF NOT EXISTS uq_ai_eval_result_run_case_metric_st0003
    ON ai.evaluation_result (
        evaluation_run_id,
        evaluation_case_id,
        metric_code
    );

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_suite_task_st0003
    ON ai.evaluation_suite (task_definition_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_suite_rubric_st0003
    ON ai.evaluation_suite (rubric_artifact_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_suite_approver_st0003
    ON ai.evaluation_suite (approved_by_principal_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_dataset_artifact_st0003
    ON ai.evaluation_dataset_version (dataset_artifact_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_dataset_locker_st0003
    ON ai.evaluation_dataset_version (locked_by_principal_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_case_task_split_st0003
    ON ai.evaluation_case (task_definition_id, split, risk_level);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_case_input_st0003
    ON ai.evaluation_case (input_artifact_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_case_gold_st0003
    ON ai.evaluation_case (gold_artifact_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_run_suite_status_st0003
    ON ai.evaluation_run (suite_id, status, created_at DESC);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_run_dataset_st0003
    ON ai.evaluation_run (dataset_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_run_baseline_st0003
    ON ai.evaluation_run (baseline_evaluation_run_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_run_prompt_st0003
    ON ai.evaluation_run (prompt_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_run_route_st0003
    ON ai.evaluation_run (model_route_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_run_schema_st0003
    ON ai.evaluation_run (output_schema_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_run_policy_st0003
    ON ai.evaluation_run (policy_bundle_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_run_manifest_st0003
    ON ai.evaluation_run (run_manifest_artifact_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_run_creator_st0003
    ON ai.evaluation_run (created_by_principal_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_case_result_run_status_st0003
    ON ai.evaluation_case_result (evaluation_run_id, status);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_case_result_case_st0003
    ON ai.evaluation_case_result (evaluation_case_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_case_result_attempt_st0003
    ON ai.evaluation_case_result (ai_attempt_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_case_result_output_st0003
    ON ai.evaluation_case_result (output_artifact_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_case_result_zero_tolerance_artifact_st0003
    ON ai.evaluation_case_result (zero_tolerance_evidence_artifact_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_human_eval_result_st0003
    ON ai.human_evaluation (evaluation_case_result_id, created_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_human_eval_reviewer_st0003
    ON ai.human_evaluation (reviewer_principal_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_human_eval_notes_st0003
    ON ai.human_evaluation (notes_artifact_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_judge_cal_route_st0003
    ON ai.judge_calibration (judge_route_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_judge_cal_prompt_st0003
    ON ai.judge_calibration (judge_prompt_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_judge_cal_dataset_st0003
    ON ai.judge_calibration (dataset_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_judge_cal_report_st0003
    ON ai.judge_calibration (report_artifact_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_judge_cal_approver_st0003
    ON ai.judge_calibration (approved_by_principal_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_task_status_st0003
    ON ai.release_decision (task_definition_id, status, approved_at DESC);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_prompt_st0003
    ON ai.release_decision (prompt_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_route_st0003
    ON ai.release_decision (model_route_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_schema_st0003
    ON ai.release_decision (output_schema_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_model_st0003
    ON ai.release_decision (resolved_model_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_policy_st0003
    ON ai.release_decision (policy_bundle_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_dataset_st0003
    ON ai.release_decision (dataset_version_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_run_st0003
    ON ai.release_decision (evaluation_run_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_rollback_st0003
    ON ai.release_decision (rollback_release_decision_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_approver_st0003
    ON ai.release_decision (approved_by_principal_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_second_approver_st0003
    ON ai.release_decision (second_approver_principal_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_revoker_st0003
    ON ai.release_decision (revoked_by_principal_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_prompt_author_st0003
    ON ai.prompt_version (author_principal_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_run_resolved_model_st0003
    ON ai.evaluation_run (resolved_model_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_eval_result_judge_cal_st0003
    ON ai.evaluation_result (judge_calibration_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_judge_cal_task_st0003
    ON ai.judge_calibration (evaluated_task_definition_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_judge_cal_model_st0003
    ON ai.judge_calibration (resolved_judge_model_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_judge_cal_rubric_st0003
    ON ai.judge_calibration (rubric_artifact_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_judge_cal_st0003
    ON ai.release_decision (judge_calibration_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_runbook_st0003
    ON ai.release_decision (rollback_runbook_artifact_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_monitor_st0003
    ON ai.release_decision (canary_monitoring_artifact_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_evidence_st0003
    ON ai.release_decision (canary_evidence_artifact_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_canary_approval_st0003
    ON ai.release_decision (canary_approval_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_active_approval_st0003
    ON ai.release_decision (active_approval_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_approval_primary_st0003
    ON ai.release_approval (primary_approver_principal_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_approval_second_st0003
    ON ai.release_approval (second_approver_principal_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ai_release_approval_artifact_st0003
    ON ai.release_approval (approval_artifact_id);

CREATE UNIQUE INDEX CONCURRENTLY
    IF NOT EXISTS uq_ai_prompt_task_locale_active_st0003
    ON ai.prompt_version (task_definition_id, locale)
    WHERE status = 'ACTIVE';

DO $$
DECLARE
    expected record;
BEGIN
    FOR expected IN
        SELECT *
          FROM (VALUES
            ('ai.ix_ai_job_policy_bundle_st0003',
             'CREATE INDEX ix_ai_job_policy_bundle_st0003 ON ai.ai_job USING btree (policy_bundle_version_id)'),
            ('ai.ix_ai_job_release_decision_st0003',
             'CREATE INDEX ix_ai_job_release_decision_st0003 ON ai.ai_job USING btree (release_decision_id)'),
            ('ai.ix_ai_eval_result_run_st0003',
             'CREATE INDEX ix_ai_eval_result_run_st0003 ON ai.evaluation_result USING btree (evaluation_run_id)'),
            ('ai.ix_ai_eval_result_case_st0003',
             'CREATE INDEX ix_ai_eval_result_case_st0003 ON ai.evaluation_result USING btree (evaluation_case_id)'),
            ('ai.uq_ai_eval_result_run_case_metric_st0003',
             'CREATE UNIQUE INDEX uq_ai_eval_result_run_case_metric_st0003 ON ai.evaluation_result USING btree (evaluation_run_id, evaluation_case_id, metric_code)'),
            ('ai.ix_ai_eval_suite_task_st0003',
             'CREATE INDEX ix_ai_eval_suite_task_st0003 ON ai.evaluation_suite USING btree (task_definition_id)'),
            ('ai.ix_ai_eval_suite_rubric_st0003',
             'CREATE INDEX ix_ai_eval_suite_rubric_st0003 ON ai.evaluation_suite USING btree (rubric_artifact_id)'),
            ('ai.ix_ai_eval_suite_approver_st0003',
             'CREATE INDEX ix_ai_eval_suite_approver_st0003 ON ai.evaluation_suite USING btree (approved_by_principal_id)'),
            ('ai.ix_ai_eval_dataset_artifact_st0003',
             'CREATE INDEX ix_ai_eval_dataset_artifact_st0003 ON ai.evaluation_dataset_version USING btree (dataset_artifact_id)'),
            ('ai.ix_ai_eval_dataset_locker_st0003',
             'CREATE INDEX ix_ai_eval_dataset_locker_st0003 ON ai.evaluation_dataset_version USING btree (locked_by_principal_id)'),
            ('ai.ix_ai_eval_case_task_split_st0003',
             'CREATE INDEX ix_ai_eval_case_task_split_st0003 ON ai.evaluation_case USING btree (task_definition_id, split, risk_level)'),
            ('ai.ix_ai_eval_case_input_st0003',
             'CREATE INDEX ix_ai_eval_case_input_st0003 ON ai.evaluation_case USING btree (input_artifact_id)'),
            ('ai.ix_ai_eval_case_gold_st0003',
             'CREATE INDEX ix_ai_eval_case_gold_st0003 ON ai.evaluation_case USING btree (gold_artifact_id)'),
            ('ai.ix_ai_eval_run_suite_status_st0003',
             'CREATE INDEX ix_ai_eval_run_suite_status_st0003 ON ai.evaluation_run USING btree (suite_id, status, created_at DESC)'),
            ('ai.ix_ai_eval_run_dataset_st0003',
             'CREATE INDEX ix_ai_eval_run_dataset_st0003 ON ai.evaluation_run USING btree (dataset_version_id)'),
            ('ai.ix_ai_eval_run_baseline_st0003',
             'CREATE INDEX ix_ai_eval_run_baseline_st0003 ON ai.evaluation_run USING btree (baseline_evaluation_run_id)'),
            ('ai.ix_ai_eval_run_prompt_st0003',
             'CREATE INDEX ix_ai_eval_run_prompt_st0003 ON ai.evaluation_run USING btree (prompt_version_id)'),
            ('ai.ix_ai_eval_run_route_st0003',
             'CREATE INDEX ix_ai_eval_run_route_st0003 ON ai.evaluation_run USING btree (model_route_version_id)'),
            ('ai.ix_ai_eval_run_schema_st0003',
             'CREATE INDEX ix_ai_eval_run_schema_st0003 ON ai.evaluation_run USING btree (output_schema_version_id)'),
            ('ai.ix_ai_eval_run_policy_st0003',
             'CREATE INDEX ix_ai_eval_run_policy_st0003 ON ai.evaluation_run USING btree (policy_bundle_version_id)'),
            ('ai.ix_ai_eval_run_manifest_st0003',
             'CREATE INDEX ix_ai_eval_run_manifest_st0003 ON ai.evaluation_run USING btree (run_manifest_artifact_id)'),
            ('ai.ix_ai_eval_run_creator_st0003',
             'CREATE INDEX ix_ai_eval_run_creator_st0003 ON ai.evaluation_run USING btree (created_by_principal_id)'),
            ('ai.ix_ai_eval_case_result_run_status_st0003',
             'CREATE INDEX ix_ai_eval_case_result_run_status_st0003 ON ai.evaluation_case_result USING btree (evaluation_run_id, status)'),
            ('ai.ix_ai_eval_case_result_case_st0003',
             'CREATE INDEX ix_ai_eval_case_result_case_st0003 ON ai.evaluation_case_result USING btree (evaluation_case_id)'),
            ('ai.ix_ai_eval_case_result_attempt_st0003',
             'CREATE INDEX ix_ai_eval_case_result_attempt_st0003 ON ai.evaluation_case_result USING btree (ai_attempt_id)'),
            ('ai.ix_ai_eval_case_result_output_st0003',
             'CREATE INDEX ix_ai_eval_case_result_output_st0003 ON ai.evaluation_case_result USING btree (output_artifact_id)'),
            ('ai.ix_ai_eval_case_result_zero_tolerance_artifact_st0003',
             'CREATE INDEX ix_ai_eval_case_result_zero_tolerance_artifact_st0003 ON ai.evaluation_case_result USING btree (zero_tolerance_evidence_artifact_id)'),
            ('ai.ix_ai_human_eval_result_st0003',
             'CREATE INDEX ix_ai_human_eval_result_st0003 ON ai.human_evaluation USING btree (evaluation_case_result_id, created_at)'),
            ('ai.ix_ai_human_eval_reviewer_st0003',
             'CREATE INDEX ix_ai_human_eval_reviewer_st0003 ON ai.human_evaluation USING btree (reviewer_principal_id)'),
            ('ai.ix_ai_human_eval_notes_st0003',
             'CREATE INDEX ix_ai_human_eval_notes_st0003 ON ai.human_evaluation USING btree (notes_artifact_id)'),
            ('ai.ix_ai_judge_cal_route_st0003',
             'CREATE INDEX ix_ai_judge_cal_route_st0003 ON ai.judge_calibration USING btree (judge_route_version_id)'),
            ('ai.ix_ai_judge_cal_prompt_st0003',
             'CREATE INDEX ix_ai_judge_cal_prompt_st0003 ON ai.judge_calibration USING btree (judge_prompt_version_id)'),
            ('ai.ix_ai_judge_cal_dataset_st0003',
             'CREATE INDEX ix_ai_judge_cal_dataset_st0003 ON ai.judge_calibration USING btree (dataset_version_id)'),
            ('ai.ix_ai_judge_cal_report_st0003',
             'CREATE INDEX ix_ai_judge_cal_report_st0003 ON ai.judge_calibration USING btree (report_artifact_id)'),
            ('ai.ix_ai_judge_cal_approver_st0003',
             'CREATE INDEX ix_ai_judge_cal_approver_st0003 ON ai.judge_calibration USING btree (approved_by_principal_id)'),
            ('ai.ix_ai_release_task_status_st0003',
             'CREATE INDEX ix_ai_release_task_status_st0003 ON ai.release_decision USING btree (task_definition_id, status, approved_at DESC)'),
            ('ai.ix_ai_release_prompt_st0003',
             'CREATE INDEX ix_ai_release_prompt_st0003 ON ai.release_decision USING btree (prompt_version_id)'),
            ('ai.ix_ai_release_route_st0003',
             'CREATE INDEX ix_ai_release_route_st0003 ON ai.release_decision USING btree (model_route_version_id)'),
            ('ai.ix_ai_release_schema_st0003',
             'CREATE INDEX ix_ai_release_schema_st0003 ON ai.release_decision USING btree (output_schema_version_id)'),
            ('ai.ix_ai_release_model_st0003',
             'CREATE INDEX ix_ai_release_model_st0003 ON ai.release_decision USING btree (resolved_model_id)'),
            ('ai.ix_ai_release_policy_st0003',
             'CREATE INDEX ix_ai_release_policy_st0003 ON ai.release_decision USING btree (policy_bundle_version_id)'),
            ('ai.ix_ai_release_dataset_st0003',
             'CREATE INDEX ix_ai_release_dataset_st0003 ON ai.release_decision USING btree (dataset_version_id)'),
            ('ai.ix_ai_release_run_st0003',
             'CREATE INDEX ix_ai_release_run_st0003 ON ai.release_decision USING btree (evaluation_run_id)'),
            ('ai.ix_ai_release_rollback_st0003',
             'CREATE INDEX ix_ai_release_rollback_st0003 ON ai.release_decision USING btree (rollback_release_decision_id)'),
            ('ai.ix_ai_release_approver_st0003',
             'CREATE INDEX ix_ai_release_approver_st0003 ON ai.release_decision USING btree (approved_by_principal_id)'),
            ('ai.ix_ai_release_second_approver_st0003',
             'CREATE INDEX ix_ai_release_second_approver_st0003 ON ai.release_decision USING btree (second_approver_principal_id)'),
            ('ai.ix_ai_release_revoker_st0003',
             'CREATE INDEX ix_ai_release_revoker_st0003 ON ai.release_decision USING btree (revoked_by_principal_id)'),
            ('ai.ix_ai_prompt_author_st0003',
             'CREATE INDEX ix_ai_prompt_author_st0003 ON ai.prompt_version USING btree (author_principal_id)'),
            ('ai.ix_ai_eval_run_resolved_model_st0003',
             'CREATE INDEX ix_ai_eval_run_resolved_model_st0003 ON ai.evaluation_run USING btree (resolved_model_id)'),
            ('ai.ix_ai_eval_result_judge_cal_st0003',
             'CREATE INDEX ix_ai_eval_result_judge_cal_st0003 ON ai.evaluation_result USING btree (judge_calibration_id)'),
            ('ai.ix_ai_judge_cal_task_st0003',
             'CREATE INDEX ix_ai_judge_cal_task_st0003 ON ai.judge_calibration USING btree (evaluated_task_definition_id)'),
            ('ai.ix_ai_judge_cal_model_st0003',
             'CREATE INDEX ix_ai_judge_cal_model_st0003 ON ai.judge_calibration USING btree (resolved_judge_model_id)'),
            ('ai.ix_ai_judge_cal_rubric_st0003',
             'CREATE INDEX ix_ai_judge_cal_rubric_st0003 ON ai.judge_calibration USING btree (rubric_artifact_id)'),
            ('ai.ix_ai_release_judge_cal_st0003',
             'CREATE INDEX ix_ai_release_judge_cal_st0003 ON ai.release_decision USING btree (judge_calibration_id)'),
            ('ai.ix_ai_release_runbook_st0003',
             'CREATE INDEX ix_ai_release_runbook_st0003 ON ai.release_decision USING btree (rollback_runbook_artifact_id)'),
            ('ai.ix_ai_release_monitor_st0003',
             'CREATE INDEX ix_ai_release_monitor_st0003 ON ai.release_decision USING btree (canary_monitoring_artifact_id)'),
            ('ai.ix_ai_release_evidence_st0003',
             'CREATE INDEX ix_ai_release_evidence_st0003 ON ai.release_decision USING btree (canary_evidence_artifact_id)'),
            ('ai.ix_ai_release_canary_approval_st0003',
             'CREATE INDEX ix_ai_release_canary_approval_st0003 ON ai.release_decision USING btree (canary_approval_id)'),
            ('ai.ix_ai_release_active_approval_st0003',
             'CREATE INDEX ix_ai_release_active_approval_st0003 ON ai.release_decision USING btree (active_approval_id)'),
            ('ai.ix_ai_release_approval_primary_st0003',
             'CREATE INDEX ix_ai_release_approval_primary_st0003 ON ai.release_approval USING btree (primary_approver_principal_id)'),
            ('ai.ix_ai_release_approval_second_st0003',
             'CREATE INDEX ix_ai_release_approval_second_st0003 ON ai.release_approval USING btree (second_approver_principal_id)'),
            ('ai.ix_ai_release_approval_artifact_st0003',
             'CREATE INDEX ix_ai_release_approval_artifact_st0003 ON ai.release_approval USING btree (approval_artifact_id)'),
            ('ai.uq_ai_prompt_task_locale_active_st0003',
             'CREATE UNIQUE INDEX uq_ai_prompt_task_locale_active_st0003 ON ai.prompt_version USING btree (task_definition_id, locale) WHERE (status = ''ACTIVE''::text)')
          ) AS definitions(index_name, definition)
    LOOP
        IF NOT EXISTS (
            SELECT 1
              FROM pg_index
             WHERE indexrelid = to_regclass(expected.index_name)
               AND indisvalid
               AND indisready
               AND pg_get_indexdef(indexrelid) = expected.definition
        ) THEN
            RAISE EXCEPTION
                'ST-0003 index % is missing, invalid, or definition-drifted',
                expected.index_name;
        END IF;
    END LOOP;
END
$$;

RESET lock_timeout;
RESET statement_timeout;
