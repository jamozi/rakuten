-- RAOS-AI-001 contract-alignment proposal v0.1
-- Date: 2026-07-30
-- IMPORTANT: This is a design input, not a production-ready migration.
-- Adapt it to the repository migration framework and test against PostgreSQL 18.x.

BEGIN;

-- Extend attempt/job metadata required for reproducibility and provider controls.
ALTER TABLE ai.ai_job
    ADD COLUMN IF NOT EXISTS policy_bundle_version_id uuid,
    ADD COLUMN IF NOT EXISTS release_decision_id uuid,
    ADD COLUMN IF NOT EXISTS request_config jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS input_manifest_sha256 text,
    ADD COLUMN IF NOT EXISTS budget_reserved_jpy bigint NOT NULL DEFAULT 0;

ALTER TABLE ai.ai_attempt
    ADD COLUMN IF NOT EXISTS requested_model_id text,
    ADD COLUMN IF NOT EXISTS resolved_model_id text,
    ADD COLUMN IF NOT EXISTS response_fingerprint text,
    ADD COLUMN IF NOT EXISTS provider_region text,
    ADD COLUMN IF NOT EXISTS request_config jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS validation_status text,
    ADD COLUMN IF NOT EXISTS safety_identifier_hash text,
    ADD COLUMN IF NOT EXISTS repair_attempt_no smallint NOT NULL DEFAULT 0;

ALTER TABLE ai.prompt_version
    ADD COLUMN IF NOT EXISTS locale text NOT NULL DEFAULT 'ja-JP',
    ADD COLUMN IF NOT EXISTS compiler_version text,
    ADD COLUMN IF NOT EXISTS input_contract_sha256 text,
    ADD COLUMN IF NOT EXISTS policy_test_status text;

ALTER TABLE ai.model_definition
    ADD COLUMN IF NOT EXISTS context_window_tokens integer,
    ADD COLUMN IF NOT EXISTS max_output_tokens integer,
    ADD COLUMN IF NOT EXISTS knowledge_cutoff date,
    ADD COLUMN IF NOT EXISTS metadata_observed_at timestamptz,
    ADD COLUMN IF NOT EXISTS provider_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

-- Evaluation governance entities. evaluation_result remains the metric fact table.
CREATE TABLE IF NOT EXISTS ai.evaluation_suite (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    suite_code text NOT NULL,
    version_no integer NOT NULL,
    task_definition_id uuid NOT NULL REFERENCES ai.task_definition(id) ON DELETE RESTRICT,
    risk_level text NOT NULL,
    rubric_artifact_id uuid REFERENCES ops.object_artifact(id) ON DELETE RESTRICT,
    suite_config jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL,
    approved_by_principal_id uuid REFERENCES iam.principal(id) ON DELETE RESTRICT,
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_ai_eval_suite UNIQUE (suite_code, version_no),
    CONSTRAINT ck_ai_eval_suite_version CHECK (version_no >= 1),
    CONSTRAINT ck_ai_eval_suite_risk CHECK (risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    CONSTRAINT ck_ai_eval_suite_status CHECK (status IN ('DRAFT','LOCKED','ACTIVE','RETIRED')),
    CONSTRAINT ck_ai_eval_suite_config CHECK (jsonb_typeof(suite_config) = 'object')
);

CREATE TABLE IF NOT EXISTS ai.evaluation_dataset_version (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    display_id text NOT NULL UNIQUE,
    dataset_code text NOT NULL,
    version_no integer NOT NULL,
    purpose text NOT NULL,
    split_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
    dataset_artifact_id uuid NOT NULL REFERENCES ops.object_artifact(id) ON DELETE RESTRICT,
    dataset_sha256 text NOT NULL,
    case_count integer NOT NULL,
    status text NOT NULL,
    locked_by_principal_id uuid REFERENCES iam.principal(id) ON DELETE RESTRICT,
    locked_at timestamptz,
    compromised_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_ai_eval_dataset UNIQUE (dataset_code, version_no),
    CONSTRAINT ck_ai_eval_dataset_version CHECK (version_no >= 1),
    CONSTRAINT ck_ai_eval_dataset_count CHECK (case_count >= 0),
    CONSTRAINT ck_ai_eval_dataset_sha CHECK (dataset_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_ai_eval_dataset_status CHECK (status IN ('DRAFT','CURATING','LOCKED','ACTIVE','COMPROMISED','RETIRED')),
    CONSTRAINT ck_ai_eval_dataset_split CHECK (jsonb_typeof(split_policy) = 'object')
);

CREATE TABLE IF NOT EXISTS ai.evaluation_case (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    dataset_version_id uuid NOT NULL REFERENCES ai.evaluation_dataset_version(id) ON DELETE RESTRICT,
    case_key text NOT NULL,
    task_definition_id uuid NOT NULL REFERENCES ai.task_definition(id) ON DELETE RESTRICT,
    split text NOT NULL,
    category text NOT NULL,
    risk_level text NOT NULL,
    input_artifact_id uuid NOT NULL REFERENCES ops.object_artifact(id) ON DELETE RESTRICT,
    gold_artifact_id uuid REFERENCES ops.object_artifact(id) ON DELETE RESTRICT,
    expected_disposition text NOT NULL,
    tags text[] NOT NULL DEFAULT ARRAY[]::text[],
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_ai_eval_case UNIQUE (dataset_version_id, case_key),
    CONSTRAINT ck_ai_eval_case_split CHECK (split IN ('BOOTSTRAP','DEV','CALIBRATION','HOLDOUT','REGRESSION','ADVERSARIAL','PRODUCTION_SAMPLE')),
    CONSTRAINT ck_ai_eval_case_risk CHECK (risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    CONSTRAINT ck_ai_eval_case_meta CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE TABLE IF NOT EXISTS ai.evaluation_run (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    display_id text NOT NULL UNIQUE,
    suite_id uuid NOT NULL REFERENCES ai.evaluation_suite(id) ON DELETE RESTRICT,
    dataset_version_id uuid NOT NULL REFERENCES ai.evaluation_dataset_version(id) ON DELETE RESTRICT,
    prompt_version_id uuid NOT NULL REFERENCES ai.prompt_version(id) ON DELETE RESTRICT,
    model_route_version_id uuid NOT NULL REFERENCES ai.model_route_version(id) ON DELETE RESTRICT,
    output_schema_version_id uuid NOT NULL REFERENCES ai.output_schema_version(id) ON DELETE RESTRICT,
    policy_bundle_version_id uuid,
    code_git_sha text NOT NULL,
    status text NOT NULL,
    run_manifest_artifact_id uuid REFERENCES ops.object_artifact(id) ON DELETE RESTRICT,
    started_at timestamptz,
    completed_at timestamptz,
    created_by_principal_id uuid REFERENCES iam.principal(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_ai_eval_run_status CHECK (status IN ('PLANNED','RUNNING','GRADING','HUMAN_REVIEW','COMPLETED','FAILED','INVALIDATED')),
    CONSTRAINT ck_ai_eval_run_git CHECK (code_git_sha ~ '^[0-9a-f]{40,64}$')
);

CREATE TABLE IF NOT EXISTS ai.evaluation_case_result (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    evaluation_run_id uuid NOT NULL REFERENCES ai.evaluation_run(id) ON DELETE RESTRICT,
    evaluation_case_id uuid NOT NULL REFERENCES ai.evaluation_case(id) ON DELETE RESTRICT,
    ai_attempt_id uuid REFERENCES ai.ai_attempt(id) ON DELETE RESTRICT,
    output_artifact_id uuid REFERENCES ops.object_artifact(id) ON DELETE RESTRICT,
    status text NOT NULL,
    disposition text NOT NULL,
    zero_tolerance_failure_count integer NOT NULL DEFAULT 0,
    grader_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_ai_eval_case_result UNIQUE (evaluation_run_id, evaluation_case_id),
    CONSTRAINT ck_ai_eval_case_result_failures CHECK (zero_tolerance_failure_count >= 0),
    CONSTRAINT ck_ai_eval_case_result_summary CHECK (jsonb_typeof(grader_summary) = 'object')
);

CREATE TABLE IF NOT EXISTS ai.human_evaluation (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    evaluation_case_result_id uuid NOT NULL REFERENCES ai.evaluation_case_result(id) ON DELETE RESTRICT,
    reviewer_principal_id uuid NOT NULL REFERENCES iam.principal(id) ON DELETE RESTRICT,
    rubric_version text NOT NULL,
    blind_assignment_key text NOT NULL,
    scores jsonb NOT NULL DEFAULT '{}'::jsonb,
    decision text NOT NULL,
    notes_artifact_id uuid REFERENCES ops.object_artifact(id) ON DELETE RESTRICT,
    is_adjudication boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_ai_human_eval UNIQUE (evaluation_case_result_id, reviewer_principal_id, is_adjudication),
    CONSTRAINT ck_ai_human_eval_scores CHECK (jsonb_typeof(scores) = 'object'),
    CONSTRAINT ck_ai_human_eval_decision CHECK (decision IN ('PASS','FAIL','NEEDS_ADJUDICATION','INVALID'))
);

CREATE TABLE IF NOT EXISTS ai.judge_calibration (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    display_id text NOT NULL UNIQUE,
    judge_route_version_id uuid NOT NULL REFERENCES ai.model_route_version(id) ON DELETE RESTRICT,
    judge_prompt_version_id uuid NOT NULL REFERENCES ai.prompt_version(id) ON DELETE RESTRICT,
    dataset_version_id uuid NOT NULL REFERENCES ai.evaluation_dataset_version(id) ON DELETE RESTRICT,
    weighted_kappa numeric(8,6),
    zero_tolerance_false_pass_rate numeric(8,6),
    zero_tolerance_false_fail_rate numeric(8,6),
    case_count integer NOT NULL,
    status text NOT NULL,
    report_artifact_id uuid REFERENCES ops.object_artifact(id) ON DELETE RESTRICT,
    approved_by_principal_id uuid REFERENCES iam.principal(id) ON DELETE RESTRICT,
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_ai_judge_cal_count CHECK (case_count >= 0),
    CONSTRAINT ck_ai_judge_cal_status CHECK (status IN ('DRAFT','PASSED','FAILED','EXPIRED','RETIRED'))
);

CREATE TABLE IF NOT EXISTS ai.release_decision (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    display_id text NOT NULL UNIQUE,
    task_definition_id uuid NOT NULL REFERENCES ai.task_definition(id) ON DELETE RESTRICT,
    prompt_version_id uuid NOT NULL REFERENCES ai.prompt_version(id) ON DELETE RESTRICT,
    model_route_version_id uuid NOT NULL REFERENCES ai.model_route_version(id) ON DELETE RESTRICT,
    output_schema_version_id uuid NOT NULL REFERENCES ai.output_schema_version(id) ON DELETE RESTRICT,
    evaluation_run_id uuid NOT NULL REFERENCES ai.evaluation_run(id) ON DELETE RESTRICT,
    release_scope text NOT NULL,
    status text NOT NULL,
    maximum_canary_percent smallint NOT NULL DEFAULT 0,
    decision_manifest_sha256 text NOT NULL,
    rollback_release_decision_id uuid REFERENCES ai.release_decision(id) ON DELETE RESTRICT,
    approved_by_principal_id uuid NOT NULL REFERENCES iam.principal(id) ON DELETE RESTRICT,
    second_approver_principal_id uuid REFERENCES iam.principal(id) ON DELETE RESTRICT,
    approved_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_ai_release_scope CHECK (release_scope IN ('SHADOW','CANARY','ACTIVE')),
    CONSTRAINT ck_ai_release_status CHECK (status IN ('DRAFT','READY_FOR_REVIEW','APPROVED_CANARY','APPROVED_ACTIVE','REJECTED','REVOKED')),
    CONSTRAINT ck_ai_release_canary CHECK (maximum_canary_percent BETWEEN 0 AND 100),
    CONSTRAINT ck_ai_release_sha CHECK (decision_manifest_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_ai_release_approvers CHECK (second_approver_principal_id IS NULL OR second_approver_principal_id <> approved_by_principal_id)
);

ALTER TABLE ai.evaluation_result
    ADD COLUMN IF NOT EXISTS evaluation_run_id uuid REFERENCES ai.evaluation_run(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS evaluation_case_id uuid REFERENCES ai.evaluation_case(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS grader_code text,
    ADD COLUMN IF NOT EXISTS slice_key text,
    ADD COLUMN IF NOT EXISTS threshold_operator text,
    ADD COLUMN IF NOT EXISTS threshold_value numeric;

CREATE INDEX IF NOT EXISTS ix_ai_eval_case_task_split ON ai.evaluation_case(task_definition_id, split, risk_level);
CREATE INDEX IF NOT EXISTS ix_ai_eval_run_suite_status ON ai.evaluation_run(suite_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_eval_case_result_run_status ON ai.evaluation_case_result(evaluation_run_id, status);
CREATE INDEX IF NOT EXISTS ix_ai_human_eval_result ON ai.human_evaluation(evaluation_case_result_id, created_at);
CREATE INDEX IF NOT EXISTS ix_ai_release_task_status ON ai.release_decision(task_definition_id, status, approved_at DESC);

-- Registry alignment: the two explicit API Job contracts absent from the earlier task registry.
INSERT INTO ai.task_definition(task_code, name, description, risk_level, output_schema_code, default_max_tokens, default_max_cost_jpy, human_review_required, status)
VALUES
    ('ai.search_intent_classification.v1', 'Intent Analyst', 'Classify keyword intent and propose coherent clusters.', 'MEDIUM', 'ai.search_intent_classification.v1', 16000, 70, true, 'ACTIVE'),
    ('ai.policy_assist.v1', 'Policy Assistant', 'Return non-authoritative semantic policy finding candidates.', 'CRITICAL', 'ai.policy_assist.v1', 24000, 260, true, 'ACTIVE')
ON CONFLICT (task_code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    risk_level = EXCLUDED.risk_level,
    output_schema_code = EXCLUDED.output_schema_code,
    default_max_tokens = EXCLUDED.default_max_tokens,
    default_max_cost_jpy = EXCLUDED.default_max_cost_jpy,
    human_review_required = EXCLUDED.human_review_required;

COMMIT;
