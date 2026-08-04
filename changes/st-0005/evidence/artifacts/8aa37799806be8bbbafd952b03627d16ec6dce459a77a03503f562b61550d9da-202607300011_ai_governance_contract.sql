-- ST-0003 / INT-DEC-004
-- Phase: CONTRACT VALIDATE AND FINALIZE
-- Requires: 202607300010_ai_governance_contract_prepare.sql
--
-- Full-table validation commits separately. The final NOT NULL/default,
-- constraint-name, and index-name swap is one short metadata transaction.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '15min';

DO $$
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0003 requires PostgreSQL 18 or later';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM ai.ai_job
         WHERE status IN ('PENDING', 'FAILED', 'BLOCKED')
            OR request_config IS NULL
            OR budget_reserved_jpy IS NULL
            OR lock_version IS NULL
            OR updated_at IS NULL
    ) OR EXISTS (
        SELECT 1
          FROM ai.ai_attempt
         WHERE requested_model_id IS NULL
            OR resolved_model_id IS NULL
            OR request_config IS NULL
            OR validation_status IS NULL
            OR repair_attempt_no IS NULL
    ) OR EXISTS (
        SELECT 1
          FROM ai.prompt_version
         WHERE status = 'REJECTED'
            OR author_principal_id IS NULL
            OR locale IS NULL
            OR policy_test_status IS NULL
            OR lock_version IS NULL
            OR updated_at IS NULL
    ) OR EXISTS (
        SELECT 1
          FROM ai.model_definition
         WHERE provider_metadata IS NULL
    ) OR EXISTS (
        SELECT 1
          FROM ai.model_route_version
         WHERE lock_version IS NULL OR updated_at IS NULL
    ) THEN
        RAISE EXCEPTION 'ST-0003 Contract validation backlog is nonzero';
    END IF;
END
$$;

ALTER TABLE ai.ai_job VALIDATE CONSTRAINT ck_ai_job_status;
ALTER TABLE ai.ai_job VALIDATE CONSTRAINT ck_ai_job_complete;
ALTER TABLE ai.ai_job
    VALIDATE CONSTRAINT ck_ai_job_request_config_not_null;
ALTER TABLE ai.ai_job
    VALIDATE CONSTRAINT ck_ai_job_budget_reserved_not_null;
ALTER TABLE ai.ai_job
    VALIDATE CONSTRAINT ck_ai_job_lock_version_not_null;
ALTER TABLE ai.ai_job VALIDATE CONSTRAINT ck_ai_job_updated_at_not_null;

ALTER TABLE ai.ai_attempt
    VALIDATE CONSTRAINT ck_ai_attempt_requested_model_not_null;
ALTER TABLE ai.ai_attempt
    VALIDATE CONSTRAINT ck_ai_attempt_resolved_model_not_null;
ALTER TABLE ai.ai_attempt
    VALIDATE CONSTRAINT ck_ai_attempt_request_config_not_null;
ALTER TABLE ai.ai_attempt
    VALIDATE CONSTRAINT ck_ai_attempt_validation_not_null;
ALTER TABLE ai.ai_attempt
    VALIDATE CONSTRAINT ck_ai_attempt_repair_not_null;

ALTER TABLE ai.prompt_version VALIDATE CONSTRAINT ck_ai_prompt_status;
ALTER TABLE ai.prompt_version
    VALIDATE CONSTRAINT ck_ai_prompt_locale_not_null;
ALTER TABLE ai.prompt_version
    VALIDATE CONSTRAINT ck_ai_prompt_author_not_null;
ALTER TABLE ai.prompt_version
    VALIDATE CONSTRAINT ck_ai_prompt_policy_test_not_null;
ALTER TABLE ai.prompt_version
    VALIDATE CONSTRAINT ck_ai_prompt_lock_version_not_null;
ALTER TABLE ai.prompt_version
    VALIDATE CONSTRAINT ck_ai_prompt_updated_at_not_null;

ALTER TABLE ai.model_definition
    VALIDATE CONSTRAINT ck_ai_model_metadata_not_null;

ALTER TABLE ai.model_route_version VALIDATE CONSTRAINT ck_ai_route_status;
ALTER TABLE ai.model_route_version
    VALIDATE CONSTRAINT ck_ai_route_lock_version_not_null;
ALTER TABLE ai.model_route_version
    VALIDATE CONSTRAINT ck_ai_route_updated_at_not_null;

COMMIT;

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM ai.ai_job
         WHERE status IN ('PENDING', 'FAILED', 'BLOCKED')
            OR request_config IS NULL
            OR budget_reserved_jpy IS NULL
            OR lock_version IS NULL
            OR updated_at IS NULL
    ) OR EXISTS (
        SELECT 1
          FROM ai.ai_attempt
         WHERE requested_model_id IS NULL
            OR resolved_model_id IS NULL
            OR request_config IS NULL
            OR validation_status IS NULL
            OR repair_attempt_no IS NULL
    ) OR EXISTS (
        SELECT 1
          FROM ai.prompt_version
         WHERE status = 'REJECTED'
            OR author_principal_id IS NULL
            OR locale IS NULL
            OR policy_test_status IS NULL
            OR lock_version IS NULL
            OR updated_at IS NULL
    ) OR EXISTS (
        SELECT 1
          FROM ai.model_definition
         WHERE provider_metadata IS NULL
    ) OR EXISTS (
        SELECT 1
          FROM ai.model_route_version
         WHERE lock_version IS NULL OR updated_at IS NULL
    ) THEN
        RAISE EXCEPTION 'ST-0003 Contract finalization backlog is nonzero';
    END IF;
    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE (conrelid, conname) IN (
             ('ai.ai_job'::regclass, 'ck_ai_job_status'),
             ('ai.ai_job'::regclass, 'ck_ai_job_complete'),
             ('ai.ai_job'::regclass, 'ck_ai_job_request_config_not_null'),
             ('ai.ai_job'::regclass, 'ck_ai_job_budget_reserved_not_null'),
             ('ai.ai_job'::regclass, 'ck_ai_job_lock_version_not_null'),
             ('ai.ai_job'::regclass, 'ck_ai_job_updated_at_not_null'),
             ('ai.ai_attempt'::regclass, 'ck_ai_attempt_requested_model_not_null'),
             ('ai.ai_attempt'::regclass, 'ck_ai_attempt_resolved_model_not_null'),
             ('ai.ai_attempt'::regclass, 'ck_ai_attempt_request_config_not_null'),
             ('ai.ai_attempt'::regclass, 'ck_ai_attempt_validation_not_null'),
             ('ai.ai_attempt'::regclass, 'ck_ai_attempt_repair_not_null'),
             ('ai.prompt_version'::regclass, 'ck_ai_prompt_status'),
             ('ai.prompt_version'::regclass, 'ck_ai_prompt_locale_not_null'),
             ('ai.prompt_version'::regclass, 'ck_ai_prompt_author_not_null'),
             ('ai.prompt_version'::regclass, 'ck_ai_prompt_policy_test_not_null'),
             ('ai.prompt_version'::regclass, 'ck_ai_prompt_lock_version_not_null'),
             ('ai.prompt_version'::regclass, 'ck_ai_prompt_updated_at_not_null'),
             ('ai.model_definition'::regclass, 'ck_ai_model_metadata_not_null'),
             ('ai.model_route_version'::regclass, 'ck_ai_route_status'),
             ('ai.model_route_version'::regclass, 'ck_ai_route_lock_version_not_null'),
             ('ai.model_route_version'::regclass, 'ck_ai_route_updated_at_not_null')
         )
           AND convalidated
    ) <> 21 THEN
        RAISE EXCEPTION
            'ST-0003 Contract finalization requires 21 validated constraints';
    END IF;
    IF (
        SELECT count(*)
          FROM pg_index
         WHERE indexrelid IN (
             to_regclass('ai.uq_ai_prompt_task_locale_active_st0003'),
             to_regclass('ai.ix_ai_eval_case_task_split_st0003'),
             to_regclass('ai.ix_ai_eval_run_suite_status_st0003'),
             to_regclass('ai.ix_ai_eval_case_result_run_status_st0003'),
             to_regclass('ai.ix_ai_eval_case_result_zero_tolerance_artifact_st0003'),
             to_regclass('ai.ix_ai_human_eval_result_st0003'),
             to_regclass('ai.ix_ai_release_task_status_st0003')
         )
           AND indisvalid
           AND indisready
    ) <> 7 THEN
        RAISE EXCEPTION 'ST-0003 finalization indexes are not valid/ready';
    END IF;
END
$$;

ALTER TABLE ai.ai_job
    DROP CONSTRAINT ck_ai_job_status_st0003_expand,
    DROP CONSTRAINT ck_ai_job_complete_st0003_expand,
    ALTER COLUMN status SET DEFAULT 'REQUESTED',
    ALTER COLUMN request_config SET DEFAULT '{}'::jsonb,
    ALTER COLUMN request_config SET NOT NULL,
    ALTER COLUMN budget_reserved_jpy SET DEFAULT 0,
    ALTER COLUMN budget_reserved_jpy SET NOT NULL,
    ALTER COLUMN lock_version SET DEFAULT 0,
    ALTER COLUMN lock_version SET NOT NULL,
    ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP,
    ALTER COLUMN updated_at SET NOT NULL,
    DROP CONSTRAINT ck_ai_job_request_config_not_null,
    DROP CONSTRAINT ck_ai_job_budget_reserved_not_null,
    DROP CONSTRAINT ck_ai_job_lock_version_not_null,
    DROP CONSTRAINT ck_ai_job_updated_at_not_null;

ALTER TABLE ai.ai_job RENAME CONSTRAINT
    ck_ai_job_request_config_st0003_expand TO ck_ai_job_request_config;
ALTER TABLE ai.ai_job RENAME CONSTRAINT
    ck_ai_job_manifest_sha_st0003_expand TO ck_ai_job_manifest_sha;
ALTER TABLE ai.ai_job RENAME CONSTRAINT
    ck_ai_job_budget_reserved_st0003_expand TO ck_ai_job_budget_reserved;
ALTER TABLE ai.ai_job RENAME CONSTRAINT
    ck_ai_job_lock_version_st0003_expand TO ck_ai_job_lock_version;
ALTER TABLE ai.ai_job RENAME CONSTRAINT
    fk_ai_job_policy_bundle_st0003_expand TO fk_ai_job_policy_bundle;
ALTER TABLE ai.ai_job RENAME CONSTRAINT
    fk_ai_job_release_decision_st0003_expand TO fk_ai_job_release_decision;

ALTER TABLE ai.ai_attempt
    ALTER COLUMN requested_model_id SET NOT NULL,
    ALTER COLUMN resolved_model_id SET NOT NULL,
    ALTER COLUMN request_config SET DEFAULT '{}'::jsonb,
    ALTER COLUMN request_config SET NOT NULL,
    ALTER COLUMN validation_status SET NOT NULL,
    ALTER COLUMN repair_attempt_no SET DEFAULT 0,
    ALTER COLUMN repair_attempt_no SET NOT NULL,
    DROP CONSTRAINT ck_ai_attempt_requested_model_not_null,
    DROP CONSTRAINT ck_ai_attempt_resolved_model_not_null,
    DROP CONSTRAINT ck_ai_attempt_request_config_not_null,
    DROP CONSTRAINT ck_ai_attempt_validation_not_null,
    DROP CONSTRAINT ck_ai_attempt_repair_not_null;

ALTER TABLE ai.ai_attempt RENAME CONSTRAINT
    ck_ai_attempt_requested_model_st0003_expand
    TO ck_ai_attempt_requested_model;
ALTER TABLE ai.ai_attempt RENAME CONSTRAINT
    ck_ai_attempt_resolved_model_st0003_expand
    TO ck_ai_attempt_resolved_model;
ALTER TABLE ai.ai_attempt RENAME CONSTRAINT
    ck_ai_attempt_fingerprint_st0003_expand TO ck_ai_attempt_fingerprint;
ALTER TABLE ai.ai_attempt RENAME CONSTRAINT
    ck_ai_attempt_region_st0003_expand TO ck_ai_attempt_region;
ALTER TABLE ai.ai_attempt RENAME CONSTRAINT
    ck_ai_attempt_request_config_st0003_expand
    TO ck_ai_attempt_request_config;
ALTER TABLE ai.ai_attempt RENAME CONSTRAINT
    ck_ai_attempt_validation_st0003_expand TO ck_ai_attempt_validation;
ALTER TABLE ai.ai_attempt RENAME CONSTRAINT
    ck_ai_attempt_safety_hash_st0003_expand TO ck_ai_attempt_safety_hash;
ALTER TABLE ai.ai_attempt RENAME CONSTRAINT
    ck_ai_attempt_repair_st0003_expand TO ck_ai_attempt_repair;

ALTER TABLE ai.prompt_version
    DROP CONSTRAINT ck_ai_prompt_status_st0003_expand,
    ALTER COLUMN locale SET DEFAULT 'ja-JP',
    ALTER COLUMN locale SET NOT NULL,
    ALTER COLUMN author_principal_id SET NOT NULL,
    ALTER COLUMN policy_test_status SET DEFAULT 'NOT_EXECUTED',
    ALTER COLUMN policy_test_status SET NOT NULL,
    ALTER COLUMN lock_version SET DEFAULT 0,
    ALTER COLUMN lock_version SET NOT NULL,
    ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP,
    ALTER COLUMN updated_at SET NOT NULL,
    DROP CONSTRAINT ck_ai_prompt_locale_not_null,
    DROP CONSTRAINT ck_ai_prompt_author_not_null,
    DROP CONSTRAINT ck_ai_prompt_policy_test_not_null,
    DROP CONSTRAINT ck_ai_prompt_lock_version_not_null,
    DROP CONSTRAINT ck_ai_prompt_updated_at_not_null;

ALTER TABLE ai.prompt_version RENAME CONSTRAINT
    ck_ai_prompt_locale_st0003_expand TO ck_ai_prompt_locale;
ALTER TABLE ai.prompt_version RENAME CONSTRAINT
    ck_ai_prompt_compiler_st0003_expand TO ck_ai_prompt_compiler;
ALTER TABLE ai.prompt_version RENAME CONSTRAINT
    ck_ai_prompt_input_hash_st0003_expand TO ck_ai_prompt_input_hash;
ALTER TABLE ai.prompt_version RENAME CONSTRAINT
    ck_ai_prompt_policy_test_st0003_expand TO ck_ai_prompt_policy_test;
ALTER TABLE ai.prompt_version RENAME CONSTRAINT
    ck_ai_prompt_lock_version_st0003_expand TO ck_ai_prompt_lock_version;
ALTER TABLE ai.prompt_version RENAME CONSTRAINT
    fk_ai_prompt_author_st0003_expand TO fk_ai_prompt_author;

ALTER TABLE ai.model_definition
    ALTER COLUMN provider_metadata SET DEFAULT '{}'::jsonb,
    ALTER COLUMN provider_metadata SET NOT NULL,
    DROP CONSTRAINT ck_ai_model_metadata_not_null;

ALTER TABLE ai.model_definition RENAME CONSTRAINT
    ck_ai_model_context_st0003_expand TO ck_ai_model_context;
ALTER TABLE ai.model_definition RENAME CONSTRAINT
    ck_ai_model_output_st0003_expand TO ck_ai_model_output;
ALTER TABLE ai.model_definition RENAME CONSTRAINT
    ck_ai_model_metadata_st0003_expand TO ck_ai_model_metadata;

ALTER TABLE ai.model_route_version
    DROP CONSTRAINT ck_ai_route_status_st0003_expand,
    ALTER COLUMN lock_version SET DEFAULT 0,
    ALTER COLUMN lock_version SET NOT NULL,
    ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP,
    ALTER COLUMN updated_at SET NOT NULL,
    DROP CONSTRAINT ck_ai_route_lock_version_not_null,
    DROP CONSTRAINT ck_ai_route_updated_at_not_null;

ALTER TABLE ai.model_route_version RENAME CONSTRAINT
    ck_ai_route_lock_version_st0003_expand TO ck_ai_route_lock_version;

ALTER TABLE ai.evaluation_result RENAME CONSTRAINT
    ck_ai_eval_result_run_st0003_expand TO ck_ai_eval_result_run_binding;
ALTER TABLE ai.evaluation_result RENAME CONSTRAINT
    ck_ai_eval_result_threshold_st0003_expand TO ck_ai_eval_result_threshold;
ALTER TABLE ai.evaluation_result RENAME CONSTRAINT
    ck_ai_eval_result_grader_st0003_expand TO ck_ai_eval_result_grader;
ALTER TABLE ai.evaluation_result RENAME CONSTRAINT
    ck_ai_eval_result_slice_st0003_expand TO ck_ai_eval_result_slice;
ALTER TABLE ai.evaluation_result RENAME CONSTRAINT
    fk_ai_eval_result_run_st0003_expand TO fk_ai_eval_result_run;
ALTER TABLE ai.evaluation_result RENAME CONSTRAINT
    fk_ai_eval_result_case_st0003_expand TO fk_ai_eval_result_case;
ALTER TABLE ai.evaluation_result RENAME CONSTRAINT
    ck_ai_eval_result_judge_provenance_st0003_expand
    TO ck_ai_eval_result_judge_provenance;
ALTER TABLE ai.evaluation_result RENAME CONSTRAINT
    fk_ai_eval_result_judge_cal_st0003_expand
    TO fk_ai_eval_result_judge_cal;
ALTER TABLE ai.evaluation_result RENAME CONSTRAINT
    fk_ai_eval_result_judge_route_st0003_expand
    TO fk_ai_eval_result_judge_route;
ALTER TABLE ai.evaluation_result RENAME CONSTRAINT
    fk_ai_eval_result_judge_prompt_st0003_expand
    TO fk_ai_eval_result_judge_prompt;
ALTER TABLE ai.evaluation_result RENAME CONSTRAINT
    fk_ai_eval_result_judge_rubric_st0003_expand
    TO fk_ai_eval_result_judge_rubric;
ALTER TABLE ai.evaluation_result RENAME CONSTRAINT
    fk_ai_eval_result_judge_model_st0003_expand
    TO fk_ai_eval_result_judge_model;
ALTER TABLE ai.evaluation_run RENAME CONSTRAINT
    fk_ai_eval_run_resolved_model_st0003_expand
    TO fk_ai_eval_run_resolved_model;
ALTER TABLE ai.evaluation_run RENAME CONSTRAINT
    fk_ai_eval_run_baseline_st0003_expand
    TO fk_ai_eval_run_baseline;
ALTER TABLE ai.evaluation_result RENAME CONSTRAINT
    ck_ai_eval_result_proportion_counts_st0003_expand
    TO ck_ai_eval_result_proportion_counts;
ALTER TABLE ai.judge_calibration RENAME CONSTRAINT
    ck_ai_judge_cal_rubric_sha_st0003_expand
    TO ck_ai_judge_cal_rubric_sha;
ALTER TABLE ai.judge_calibration RENAME CONSTRAINT
    ck_ai_judge_cal_grader_version_st0003_expand
    TO ck_ai_judge_cal_grader_version;
ALTER TABLE ai.judge_calibration RENAME CONSTRAINT
    fk_ai_judge_cal_task_st0003_expand TO fk_ai_judge_cal_task;
ALTER TABLE ai.judge_calibration RENAME CONSTRAINT
    fk_ai_judge_cal_model_st0003_expand TO fk_ai_judge_cal_model;
ALTER TABLE ai.judge_calibration RENAME CONSTRAINT
    fk_ai_judge_cal_rubric_st0003_expand TO fk_ai_judge_cal_rubric;
ALTER TABLE ai.release_decision RENAME CONSTRAINT
    ck_ai_release_rollback_strategy_st0003_expand
    TO ck_ai_release_rollback_strategy;
ALTER TABLE ai.release_decision RENAME CONSTRAINT
    ck_ai_release_rollback_binding_st0003_expand
    TO ck_ai_release_rollback_binding;
ALTER TABLE ai.release_decision RENAME CONSTRAINT
    ck_ai_release_monitoring_sha_st0003_expand
    TO ck_ai_release_monitoring_sha;
ALTER TABLE ai.release_decision RENAME CONSTRAINT
    ck_ai_release_evidence_sha_st0003_expand
    TO ck_ai_release_evidence_sha;
ALTER TABLE ai.release_decision RENAME CONSTRAINT
    ck_ai_release_canary_time_st0003_expand
    TO ck_ai_release_canary_time;
ALTER TABLE ai.release_decision RENAME CONSTRAINT
    ck_ai_release_phase_state_st0003_expand
    TO ck_ai_release_phase_state;
ALTER TABLE ai.release_decision RENAME CONSTRAINT
    fk_ai_release_judge_cal_st0003_expand TO fk_ai_release_judge_cal;
ALTER TABLE ai.release_decision RENAME CONSTRAINT
    fk_ai_release_rollback_runbook_st0003_expand
    TO fk_ai_release_rollback_runbook;
ALTER TABLE ai.release_decision RENAME CONSTRAINT
    fk_ai_release_canary_monitor_st0003_expand
    TO fk_ai_release_canary_monitor;
ALTER TABLE ai.release_decision RENAME CONSTRAINT
    fk_ai_release_canary_evidence_st0003_expand
    TO fk_ai_release_canary_evidence;
ALTER TABLE ai.release_decision RENAME CONSTRAINT
    fk_ai_release_canary_approval_st0003_expand
    TO fk_ai_release_canary_approval;
ALTER TABLE ai.release_decision RENAME CONSTRAINT
    fk_ai_release_active_approval_st0003_expand
    TO fk_ai_release_active_approval;

-- The predecessor uniqueness prevented the same prompt code from being active
-- in multiple locales. The canonical task+locale index replaces it.
DROP INDEX ai.uq_ai_prompt_active;
ALTER INDEX ai.uq_ai_prompt_task_locale_active_st0003
    RENAME TO uq_ai_prompt_task_locale_active;

ALTER INDEX ai.ix_ai_job_policy_bundle_st0003
    RENAME TO ix_ai_job_policy_bundle;
ALTER INDEX ai.ix_ai_job_release_decision_st0003
    RENAME TO ix_ai_job_release_decision;
ALTER INDEX ai.ix_ai_eval_result_run_st0003
    RENAME TO ix_ai_eval_result_run_id;
ALTER INDEX ai.ix_ai_eval_result_case_st0003
    RENAME TO ix_ai_eval_result_case_id;
ALTER INDEX ai.uq_ai_eval_result_run_case_metric_st0003
    RENAME TO uq_ai_eval_result_run_case_metric;

ALTER INDEX ai.ix_ai_eval_suite_task_st0003
    RENAME TO ix_ai_eval_suite_task;
ALTER INDEX ai.ix_ai_eval_suite_rubric_st0003
    RENAME TO ix_ai_eval_suite_rubric;
ALTER INDEX ai.ix_ai_eval_suite_approver_st0003
    RENAME TO ix_ai_eval_suite_approver;
ALTER INDEX ai.ix_ai_eval_dataset_artifact_st0003
    RENAME TO ix_ai_eval_dataset_artifact;
ALTER INDEX ai.ix_ai_eval_dataset_locker_st0003
    RENAME TO ix_ai_eval_dataset_locker;
ALTER INDEX ai.ix_ai_eval_case_task_split_st0003
    RENAME TO ix_ai_eval_case_task_split;
ALTER INDEX ai.ix_ai_eval_case_input_st0003
    RENAME TO ix_ai_eval_case_input;
ALTER INDEX ai.ix_ai_eval_case_gold_st0003
    RENAME TO ix_ai_eval_case_gold;

ALTER INDEX ai.ix_ai_eval_run_suite_status_st0003
    RENAME TO ix_ai_eval_run_suite_status;
ALTER INDEX ai.ix_ai_eval_run_dataset_st0003
    RENAME TO ix_ai_eval_run_dataset;
ALTER INDEX ai.ix_ai_eval_run_baseline_st0003
    RENAME TO ix_ai_eval_run_baseline;
ALTER INDEX ai.ix_ai_eval_run_prompt_st0003
    RENAME TO ix_ai_eval_run_prompt;
ALTER INDEX ai.ix_ai_eval_run_route_st0003
    RENAME TO ix_ai_eval_run_route;
ALTER INDEX ai.ix_ai_eval_run_schema_st0003
    RENAME TO ix_ai_eval_run_schema;
ALTER INDEX ai.ix_ai_eval_run_policy_st0003
    RENAME TO ix_ai_eval_run_policy;
ALTER INDEX ai.ix_ai_eval_run_manifest_st0003
    RENAME TO ix_ai_eval_run_manifest;
ALTER INDEX ai.ix_ai_eval_run_creator_st0003
    RENAME TO ix_ai_eval_run_creator;

ALTER INDEX ai.ix_ai_eval_case_result_run_status_st0003
    RENAME TO ix_ai_eval_case_result_run_status;
ALTER INDEX ai.ix_ai_eval_case_result_case_st0003
    RENAME TO ix_ai_eval_case_result_case;
ALTER INDEX ai.ix_ai_eval_case_result_attempt_st0003
    RENAME TO ix_ai_eval_case_result_attempt;
ALTER INDEX ai.ix_ai_eval_case_result_output_st0003
    RENAME TO ix_ai_eval_case_result_output;
ALTER INDEX ai.ix_ai_eval_case_result_zero_tolerance_artifact_st0003
    RENAME TO ix_ai_eval_case_result_zero_tolerance_artifact;
ALTER INDEX ai.ix_ai_human_eval_result_st0003
    RENAME TO ix_ai_human_eval_result;
ALTER INDEX ai.ix_ai_human_eval_reviewer_st0003
    RENAME TO ix_ai_human_eval_reviewer;
ALTER INDEX ai.ix_ai_human_eval_notes_st0003
    RENAME TO ix_ai_human_eval_notes;

ALTER INDEX ai.ix_ai_judge_cal_route_st0003
    RENAME TO ix_ai_judge_cal_route;
ALTER INDEX ai.ix_ai_judge_cal_prompt_st0003
    RENAME TO ix_ai_judge_cal_prompt;
ALTER INDEX ai.ix_ai_judge_cal_dataset_st0003
    RENAME TO ix_ai_judge_cal_dataset;
ALTER INDEX ai.ix_ai_judge_cal_report_st0003
    RENAME TO ix_ai_judge_cal_report;
ALTER INDEX ai.ix_ai_judge_cal_approver_st0003
    RENAME TO ix_ai_judge_cal_approver;

ALTER INDEX ai.ix_ai_release_task_status_st0003
    RENAME TO ix_ai_release_task_status;
ALTER INDEX ai.ix_ai_release_prompt_st0003
    RENAME TO ix_ai_release_prompt;
ALTER INDEX ai.ix_ai_release_route_st0003
    RENAME TO ix_ai_release_route;
ALTER INDEX ai.ix_ai_release_schema_st0003
    RENAME TO ix_ai_release_schema;
ALTER INDEX ai.ix_ai_release_model_st0003
    RENAME TO ix_ai_release_model;
ALTER INDEX ai.ix_ai_release_policy_st0003
    RENAME TO ix_ai_release_policy;
ALTER INDEX ai.ix_ai_release_dataset_st0003
    RENAME TO ix_ai_release_dataset;
ALTER INDEX ai.ix_ai_release_run_st0003
    RENAME TO ix_ai_release_run;
ALTER INDEX ai.ix_ai_release_rollback_st0003
    RENAME TO ix_ai_release_rollback;
ALTER INDEX ai.ix_ai_release_approver_st0003
    RENAME TO ix_ai_release_approver;
ALTER INDEX ai.ix_ai_release_second_approver_st0003
    RENAME TO ix_ai_release_second_approver;
ALTER INDEX ai.ix_ai_release_revoker_st0003
    RENAME TO ix_ai_release_revoker;
ALTER INDEX ai.ix_ai_prompt_author_st0003
    RENAME TO ix_ai_prompt_author;
ALTER INDEX ai.ix_ai_eval_run_resolved_model_st0003
    RENAME TO ix_ai_eval_run_resolved_model;
ALTER INDEX ai.ix_ai_eval_result_judge_cal_st0003
    RENAME TO ix_ai_eval_result_judge_cal;
ALTER INDEX ai.ix_ai_judge_cal_task_st0003
    RENAME TO ix_ai_judge_cal_task;
ALTER INDEX ai.ix_ai_judge_cal_model_st0003
    RENAME TO ix_ai_judge_cal_model;
ALTER INDEX ai.ix_ai_judge_cal_rubric_st0003
    RENAME TO ix_ai_judge_cal_rubric;
ALTER INDEX ai.ix_ai_release_judge_cal_st0003
    RENAME TO ix_ai_release_judge_cal;
ALTER INDEX ai.ix_ai_release_runbook_st0003
    RENAME TO ix_ai_release_runbook;
ALTER INDEX ai.ix_ai_release_monitor_st0003
    RENAME TO ix_ai_release_monitor;
ALTER INDEX ai.ix_ai_release_evidence_st0003
    RENAME TO ix_ai_release_evidence;
ALTER INDEX ai.ix_ai_release_canary_approval_st0003
    RENAME TO ix_ai_release_canary_approval;
ALTER INDEX ai.ix_ai_release_active_approval_st0003
    RENAME TO ix_ai_release_active_approval;
ALTER INDEX ai.ix_ai_release_approval_primary_st0003
    RENAME TO ix_ai_release_approval_primary;
ALTER INDEX ai.ix_ai_release_approval_second_st0003
    RENAME TO ix_ai_release_approval_second;
ALTER INDEX ai.ix_ai_release_approval_artifact_st0003
    RENAME TO ix_ai_release_approval_artifact;

-- Existing-table lifecycle enforcement is installed only at Contract, after
-- every legacy row has been explicitly classified.  Expand therefore remains
-- compatible with predecessor writers while canonical writers cannot create
-- ACTIVE/certified rows directly or mutate referenced hashes afterwards.
CREATE TRIGGER trg_ai_task_definition_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON ai.task_definition
FOR EACH ROW EXECUTE FUNCTION ai.guard_task_definition_lifecycle();

CREATE TRIGGER trg_ai_prompt_version_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON ai.prompt_version
FOR EACH ROW EXECUTE FUNCTION ai.guard_prompt_version_lifecycle();

CREATE TRIGGER trg_ai_model_route_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON ai.model_route_version
FOR EACH ROW EXECUTE FUNCTION ai.guard_model_route_lifecycle();

CREATE TRIGGER trg_ai_output_schema_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON ai.output_schema_version
FOR EACH ROW EXECUTE FUNCTION ai.guard_output_schema_lifecycle();

CREATE TRIGGER trg_ai_model_definition_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON ai.model_definition
FOR EACH ROW EXECUTE FUNCTION ai.guard_model_definition_lifecycle();

CREATE TRIGGER trg_policy_bundle_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON policy.policy_bundle
FOR EACH ROW EXECUTE FUNCTION policy.guard_policy_bundle_lifecycle();

COMMIT;
