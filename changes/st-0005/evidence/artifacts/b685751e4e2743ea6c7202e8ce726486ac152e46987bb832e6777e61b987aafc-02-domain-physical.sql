-- ST-0304 physical translation fragment 02 of 11.
-- Source: approved RAOS data catalog plus finalized ST-0003/ST-0004 semantics.
-- Capture: PostgreSQL 18.4 pg_dump --schema-only --no-owner --no-privileges
--          --no-security-labels --quote-all-identifiers for the six owned schemas.
-- Schema creation/comments are rendered once by the ST-0304 generator. The 22
-- role-bound CREATE POLICY objects remain ST-0306-owned. ENABLE/FORCE RLS remains.

--
-- Name: guard_evaluation_run_start_integrity(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_evaluation_run_start_integrity"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'pg_catalog', 'ai', 'policy', 'pg_temp'
    AS $$
DECLARE
    suite_status text;
    suite_risk text;
    suite_config_value jsonb;
    suite_rubric_id uuid;
    task_id uuid;
    task_code_value text;
    task_risk text;
    task_status text;
    task_schema_code text;
    dataset_status text;
    dataset_declared_count integer;
    prompt_task_id uuid;
    prompt_status text;
    prompt_author_id uuid;
    route_task_id uuid;
    route_primary_id uuid;
    route_fallback_id uuid;
    route_status text;
    route_config_value jsonb;
    schema_code_value text;
    schema_status text;
    policy_status text;
    model_status text;
    creator_status text;
    actual_case_count bigint;
    wrong_task_count bigint;
    missing_split_count bigint;
    baseline_status text;
    baseline_suite_id uuid;
    baseline_dataset_id uuid;
BEGIN
    IF TG_OP = 'UPDATE'
       AND ROW(
            NEW.resolved_model_id,
            NEW.baseline_evaluation_run_id
       ) IS DISTINCT FROM ROW(
            OLD.resolved_model_id,
            OLD.baseline_evaluation_run_id
       ) THEN
        RAISE EXCEPTION
            'evaluation run resolved-model/baseline bindings are immutable'
            USING ERRCODE = '55000';
    END IF;
    IF NOT (
        (TG_OP = 'INSERT' AND NEW.status = 'RUNNING')
        OR (
            TG_OP = 'UPDATE'
            AND OLD.status = 'PLANNED'
            AND NEW.status = 'RUNNING'
        )
    ) THEN
        RETURN NEW;
    END IF;

    SELECT suite.status,
           suite.risk_level,
           suite.suite_config,
           suite.rubric_artifact_id,
           task.id,
           task.task_code,
           task.risk_level,
           task.status,
           task.output_schema_code,
           dataset.status,
           dataset.case_count,
           prompt.task_definition_id,
           prompt.status,
           prompt.author_principal_id,
           route.task_definition_id,
           route.primary_model_id,
           route.fallback_model_id,
           route.status,
           route.route_config,
           output_schema.schema_code,
           output_schema.status,
           bundle.status,
           model.status,
           creator.status
      INTO suite_status,
           suite_risk,
           suite_config_value,
           suite_rubric_id,
           task_id,
           task_code_value,
           task_risk,
           task_status,
           task_schema_code,
           dataset_status,
           dataset_declared_count,
           prompt_task_id,
           prompt_status,
           prompt_author_id,
           route_task_id,
           route_primary_id,
           route_fallback_id,
           route_status,
           route_config_value,
           schema_code_value,
           schema_status,
           policy_status,
           model_status,
           creator_status
      FROM ai.evaluation_suite AS suite
      JOIN ai.task_definition AS task
        ON task.id = suite.task_definition_id
      JOIN ai.evaluation_dataset_version AS dataset
        ON dataset.id = NEW.dataset_version_id
      JOIN ai.prompt_version AS prompt
        ON prompt.id = NEW.prompt_version_id
      JOIN ai.model_route_version AS route
        ON route.id = NEW.model_route_version_id
      JOIN ai.output_schema_version AS output_schema
        ON output_schema.id = NEW.output_schema_version_id
      JOIN policy.policy_bundle AS bundle
        ON bundle.id = NEW.policy_bundle_version_id
      JOIN ai.model_definition AS model
        ON model.id = NEW.resolved_model_id
      JOIN iam.principal AS creator
        ON creator.id = NEW.created_by_principal_id
     WHERE suite.id = NEW.suite_id
     FOR SHARE OF suite, task, dataset, prompt, route,
         output_schema, bundle, model, creator;

    IF task_id IS NULL THEN
        RAISE EXCEPTION 'evaluation run contains a missing version binding'
            USING ERRCODE = '23503';
    END IF;
    IF suite_status <> 'ACTIVE'
       OR task_status <> 'ACTIVE'
       OR dataset_status NOT IN ('LOCKED', 'ACTIVE')
       OR prompt_status NOT IN ('EVALUATING', 'CERTIFIED', 'ACTIVE')
       OR route_status NOT IN ('EVALUATING', 'CERTIFIED', 'CANARY', 'ACTIVE')
       OR schema_status <> 'ACTIVE'
       OR policy_status <> 'ACTIVE'
       OR model_status NOT IN ('EVALUATION', 'ACTIVE')
       OR creator_status <> 'ACTIVE' THEN
        RAISE EXCEPTION
            'evaluation run start requires eligible active/candidate bindings'
            USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM policy.bundle_rule AS binding
         WHERE binding.policy_bundle_id = NEW.policy_bundle_version_id
    ) THEN
        RAISE EXCEPTION
            'evaluation run policy bundle contains no rule versions'
            USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM policy.bundle_rule AS binding
          JOIN policy.rule_version AS rule
            ON rule.id = binding.rule_version_id
         WHERE binding.policy_bundle_id = NEW.policy_bundle_version_id
           AND rule.status <> 'ACTIVE'
    ) THEN
        RAISE EXCEPTION
            'evaluation run policy bundle contains a non-ACTIVE rule version'
            USING ERRCODE = '23514';
    END IF;
    IF suite_risk IS DISTINCT FROM task_risk
       OR suite_risk IS DISTINCT FROM ai.canonical_suite_risk(task_code_value)
       OR suite_config_value IS DISTINCT FROM
            ai.canonical_suite_config(task_code_value)
       OR prompt_task_id <> task_id
       OR route_task_id <> task_id
       OR task_schema_code <> schema_code_value
       OR NEW.resolved_model_id NOT IN (
            route_primary_id,
            COALESCE(route_fallback_id, route_primary_id)
       ) THEN
        RAISE EXCEPTION 'evaluation run bindings disagree on task/schema/model'
            USING ERRCODE = '23514';
    END IF;
    IF suite_rubric_id IS NULL OR prompt_author_id IS NULL THEN
        RAISE EXCEPTION
            'evaluation run requires rubric and prompt-author provenance'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.baseline_evaluation_run_id IS NOT NULL THEN
        SELECT baseline.status,
               baseline.suite_id,
               baseline.dataset_version_id
          INTO baseline_status,
               baseline_suite_id,
               baseline_dataset_id
          FROM ai.evaluation_run AS baseline
         WHERE baseline.id = NEW.baseline_evaluation_run_id
         FOR SHARE;
        IF baseline_status IS NULL
           OR baseline_status <> 'COMPLETED'
           OR baseline_suite_id <> NEW.suite_id
           OR baseline_dataset_id <> NEW.dataset_version_id
           OR NEW.baseline_evaluation_run_id = NEW.id THEN
            RAISE EXCEPTION
                'evaluation baseline must be a distinct COMPLETED same-suite/dataset run'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    IF jsonb_typeof(route_config_value -> 'canary_max_percent')
            IS DISTINCT FROM 'number'
       OR (route_config_value ->> 'canary_max_percent')::numeric < 0
       OR (route_config_value ->> 'canary_max_percent')::numeric > 100
       OR mod(
            (route_config_value ->> 'canary_max_percent')::numeric,
            1
       ) <> 0 THEN
        RAISE EXCEPTION 'route canary_max_percent is missing or invalid'
            USING ERRCODE = '23514';
    END IF;

    SELECT count(*),
           count(*) FILTER (WHERE task_definition_id <> task_id)
      INTO actual_case_count, wrong_task_count
      FROM ai.evaluation_case
     WHERE dataset_version_id = NEW.dataset_version_id;
    SELECT count(*)
      INTO missing_split_count
      FROM jsonb_array_elements_text(
            suite_config_value -> 'required_splits'
      ) AS required(split_name)
     WHERE NOT EXISTS (
        SELECT 1
          FROM ai.evaluation_case AS candidate
         WHERE candidate.dataset_version_id = NEW.dataset_version_id
           AND candidate.split = required.split_name
     );
    IF actual_case_count <> dataset_declared_count
       OR actual_case_count <
            (suite_config_value ->> 'minimum_adjudicated_cases')::integer
       OR wrong_task_count <> 0
       OR missing_split_count <> 0 THEN
        RAISE EXCEPTION
            'evaluation dataset does not meet canonical count/task/split requirements'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_evaluation_suite_mutation(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_evaluation_suite_mutation"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'evaluation suite must be created in DRAFT'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'non-draft evaluation suite % is immutable', OLD.id
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;
    IF ROW(
        NEW.id,
        NEW.suite_code,
        NEW.version_no,
        NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.id,
        OLD.suite_code,
        OLD.version_no,
        OLD.created_at
    ) THEN
        RAISE EXCEPTION 'evaluation suite identity is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.status IN ('LOCKED', 'ACTIVE', 'RETIRED')
       AND ROW(
           NEW.task_definition_id,
           NEW.risk_level,
           NEW.rubric_artifact_id,
           NEW.suite_config
       ) IS DISTINCT FROM ROW(
           OLD.task_definition_id,
           OLD.risk_level,
           OLD.rubric_artifact_id,
           OLD.suite_config
       ) THEN
        RAISE EXCEPTION 'LOCKED evaluation suite definition is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF (OLD.status = 'DRAFT'
            AND NEW.status NOT IN ('DRAFT', 'LOCKED', 'RETIRED'))
       OR (OLD.status = 'LOCKED'
            AND NEW.status NOT IN ('LOCKED', 'ACTIVE', 'RETIRED'))
       OR (OLD.status = 'ACTIVE'
            AND NEW.status NOT IN ('ACTIVE', 'RETIRED'))
       OR (OLD.status = 'RETIRED' AND NEW.status <> 'RETIRED') THEN
        RAISE EXCEPTION
            'evaluation suite lifecycle cannot move from % to %',
            OLD.status,
            NEW.status
            USING ERRCODE = '23514';
    END IF;
    IF OLD.status <> 'ACTIVE' AND NEW.status = 'ACTIVE' THEN
        IF NOT EXISTS (
            SELECT 1
              FROM iam.principal
             WHERE id = NEW.approved_by_principal_id
               AND principal_type = 'USER'
               AND status = 'ACTIVE'
        ) THEN
            RAISE EXCEPTION
                'ACTIVE evaluation suite requires an ACTIVE USER approver'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    IF OLD.status IN ('ACTIVE', 'RETIRED')
       AND ROW(
           NEW.approved_by_principal_id,
           NEW.approved_at
       ) IS DISTINCT FROM ROW(
           OLD.approved_by_principal_id,
           OLD.approved_at
       ) THEN
        RAISE EXCEPTION 'evaluation suite approval evidence is immutable'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_governance_component_dependency(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_governance_component_dependency"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
DECLARE
    component text;
    bound_rule_id uuid;
    has_recorded_evaluation boolean;
    mutable_lifecycle_keys text[];
BEGIN
    component := CASE TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
        WHEN 'ai.task_definition' THEN 'TASK'
        WHEN 'ai.prompt_version' THEN 'PROMPT'
        WHEN 'ai.model_route_version' THEN 'ROUTE'
        WHEN 'ai.output_schema_version' THEN 'SCHEMA'
        WHEN 'ai.model_definition' THEN 'MODEL'
        WHEN 'policy.policy_bundle' THEN 'POLICY'
        ELSE NULL
    END;
    IF component IS NULL THEN
        RAISE EXCEPTION 'unsupported governance dependency table %.%',
            TG_TABLE_SCHEMA, TG_TABLE_NAME USING ERRCODE = '55000';
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF component = 'POLICY'
           AND OLD.status <> 'ACTIVE'
           AND NEW.status = 'ACTIVE' THEN
            IF NOT EXISTS (
                SELECT 1
                  FROM policy.bundle_rule AS binding
                 WHERE binding.policy_bundle_id = NEW.id
            ) THEN
                RAISE EXCEPTION
                    'policy activation requires at least one bound rule version'
                    USING ERRCODE = '23514';
            END IF;
            FOR bound_rule_id IN
                SELECT binding.rule_version_id
                  FROM policy.bundle_rule AS binding
                 WHERE binding.policy_bundle_id = NEW.id
                 ORDER BY binding.rule_version_id
            LOOP
                PERFORM pg_advisory_xact_lock(
                    72003,
                    hashtext(bound_rule_id::text)
                );
            END LOOP;
            IF EXISTS (
                SELECT 1
                  FROM policy.bundle_rule AS binding
                  JOIN policy.rule_version AS rule
                    ON rule.id = binding.rule_version_id
                 WHERE binding.policy_bundle_id = NEW.id
                   AND rule.status <> 'ACTIVE'
            ) THEN
                RAISE EXCEPTION
                    'policy activation requires every bound rule version to be ACTIVE'
                    USING ERRCODE = '23514';
            END IF;
        END IF;
    END IF;

    SELECT EXISTS (
        SELECT 1
          FROM ai.evaluation_run AS run
          JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
         WHERE run.status <> 'PLANNED'
           AND CASE component
                WHEN 'TASK' THEN suite.task_definition_id = OLD.id
                WHEN 'PROMPT' THEN run.prompt_version_id = OLD.id
                WHEN 'ROUTE' THEN run.model_route_version_id = OLD.id
                WHEN 'SCHEMA' THEN run.output_schema_version_id = OLD.id
                WHEN 'MODEL' THEN run.resolved_model_id = OLD.id
                WHEN 'POLICY' THEN run.policy_bundle_version_id = OLD.id
                ELSE false
           END
    ) INTO has_recorded_evaluation;

    IF TG_OP = 'DELETE' THEN
        IF has_recorded_evaluation
           OR ai.has_live_rollback_dependents(component, OLD.id) THEN
            RAISE EXCEPTION
                'governance component %.% is frozen by evaluation/rollback evidence',
                TG_TABLE_SCHEMA, OLD.id USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;

    IF OLD.status = 'ACTIVE'
       AND NEW.status <> 'ACTIVE'
       AND ai.has_live_rollback_dependents(component, OLD.id) THEN
        RAISE EXCEPTION
            'governance component %.% is required by a live rollback target',
            TG_TABLE_SCHEMA, OLD.id USING ERRCODE = '23514';
    END IF;

    IF has_recorded_evaluation THEN
        mutable_lifecycle_keys := CASE component
            WHEN 'TASK' THEN ARRAY['status']
            WHEN 'PROMPT' THEN ARRAY[
                'status', 'effective_from', 'effective_to',
                'approved_by_principal_id', 'approved_at',
                'updated_at', 'lock_version'
            ]
            WHEN 'ROUTE' THEN ARRAY[
                'status', 'effective_from', 'effective_to',
                'approved_by_principal_id', 'updated_at', 'lock_version'
            ]
            WHEN 'SCHEMA' THEN ARRAY[
                'status', 'effective_from', 'effective_to'
            ]
            WHEN 'MODEL' THEN ARRAY['status']
            WHEN 'POLICY' THEN ARRAY[
                'status', 'effective_from', 'effective_to',
                'approved_by_principal_id', 'approved_at'
            ]
        END;
        IF (to_jsonb(NEW) - mutable_lifecycle_keys)
           IS DISTINCT FROM (to_jsonb(OLD) - mutable_lifecycle_keys) THEN
            RAISE EXCEPTION
                'evaluated governance component %.% content is immutable',
                TG_TABLE_SCHEMA, OLD.id USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_judge_calibration_mutation(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_judge_calibration_mutation"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'judge calibration must be created in DRAFT'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'non-draft judge calibration % is immutable', OLD.id
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;
    IF ROW(
        NEW.id,
        NEW.display_id,
        NEW.judge_route_version_id,
        NEW.judge_prompt_version_id,
        NEW.dataset_version_id,
        NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.id,
        OLD.display_id,
        OLD.judge_route_version_id,
        OLD.judge_prompt_version_id,
        OLD.dataset_version_id,
        OLD.created_at
    ) THEN
        RAISE EXCEPTION 'judge calibration bindings are immutable'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.status <> 'DRAFT'
       AND ROW(
           NEW.weighted_kappa,
           NEW.zero_tolerance_false_pass_rate,
           NEW.zero_tolerance_false_fail_rate,
           NEW.case_count,
           NEW.report_artifact_id,
           NEW.approved_by_principal_id,
           NEW.approved_at,
           NEW.expires_at
       ) IS DISTINCT FROM ROW(
           OLD.weighted_kappa,
           OLD.zero_tolerance_false_pass_rate,
           OLD.zero_tolerance_false_fail_rate,
           OLD.case_count,
           OLD.report_artifact_id,
           OLD.approved_by_principal_id,
           OLD.approved_at,
           OLD.expires_at
       ) THEN
        RAISE EXCEPTION 'judge calibration evidence is immutable after DRAFT'
            USING ERRCODE = '55000';
    END IF;
    IF (OLD.status = 'DRAFT'
            AND NEW.status NOT IN (
                'DRAFT', 'PASSED', 'FAILED', 'RETIRED'
            ))
       OR (OLD.status = 'PASSED'
            AND NEW.status NOT IN ('PASSED', 'EXPIRED', 'RETIRED'))
       OR (OLD.status = 'FAILED'
            AND NEW.status NOT IN ('FAILED', 'RETIRED'))
       OR (OLD.status = 'EXPIRED'
            AND NEW.status NOT IN ('EXPIRED', 'RETIRED'))
       OR (OLD.status = 'RETIRED' AND NEW.status <> 'RETIRED') THEN
        RAISE EXCEPTION
            'judge calibration lifecycle cannot move from % to %',
            OLD.status,
            NEW.status
            USING ERRCODE = '23514';
    END IF;
    IF OLD.status <> 'PASSED' AND NEW.status = 'PASSED' THEN
        IF NOT EXISTS (
            SELECT 1
              FROM iam.principal
             WHERE id = NEW.approved_by_principal_id
               AND principal_type = 'USER'
               AND status = 'ACTIVE'
        ) THEN
            RAISE EXCEPTION
                'PASSED judge calibration requires an ACTIVE USER approver'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_judge_calibration_scope(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_judge_calibration_scope"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
DECLARE
    route_task_id uuid;
    route_primary_id uuid;
    route_fallback_id uuid;
    route_status text;
    prompt_task_id uuid;
    prompt_status text;
    evaluated_task_status text;
    dataset_status text;
    dataset_declared_count integer;
    actual_case_count bigint;
    wrong_task_count bigint;
    rubric_hash text;
    rubric_kind_value text;
    rubric_immutable boolean;
    report_kind_value text;
    report_immutable boolean;
    model_status text;
    approver_is_active_user boolean;
BEGIN
    IF TG_OP = 'UPDATE' AND ROW(
        NEW.evaluated_task_definition_id,
        NEW.resolved_judge_model_id,
        NEW.rubric_artifact_id,
        NEW.rubric_sha256,
        NEW.grader_version
    ) IS DISTINCT FROM ROW(
        OLD.evaluated_task_definition_id,
        OLD.resolved_judge_model_id,
        OLD.rubric_artifact_id,
        OLD.rubric_sha256,
        OLD.grader_version
    ) THEN
        RAISE EXCEPTION 'judge calibration scope is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP <> 'UPDATE'
       OR OLD.status = 'PASSED'
       OR NEW.status <> 'PASSED' THEN
        RETURN NEW;
    END IF;

    SELECT route.task_definition_id,
           route.primary_model_id,
           route.fallback_model_id,
           route.status,
           prompt.task_definition_id,
           prompt.status,
           evaluated_task.status,
           dataset.status,
           dataset.case_count,
           rubric.sha256,
           rubric.artifact_kind,
           rubric.is_immutable,
           report.artifact_kind,
           report.is_immutable,
           model.status,
           (
               approver.principal_type = 'USER'
               AND approver.status = 'ACTIVE'
           )
      INTO route_task_id,
           route_primary_id,
           route_fallback_id,
           route_status,
           prompt_task_id,
           prompt_status,
           evaluated_task_status,
           dataset_status,
           dataset_declared_count,
           rubric_hash,
           rubric_kind_value,
           rubric_immutable,
           report_kind_value,
           report_immutable,
           model_status,
           approver_is_active_user
      FROM ai.model_route_version AS route
      JOIN ai.prompt_version AS prompt
        ON prompt.id = NEW.judge_prompt_version_id
      JOIN ai.task_definition AS evaluated_task
        ON evaluated_task.id = NEW.evaluated_task_definition_id
      JOIN ai.evaluation_dataset_version AS dataset
        ON dataset.id = NEW.dataset_version_id
      JOIN ops.object_artifact AS rubric
        ON rubric.id = NEW.rubric_artifact_id
      JOIN ops.object_artifact AS report
        ON report.id = NEW.report_artifact_id
      JOIN ai.model_definition AS model
        ON model.id = NEW.resolved_judge_model_id
      JOIN iam.principal AS approver
        ON approver.id = NEW.approved_by_principal_id
     WHERE route.id = NEW.judge_route_version_id
     FOR SHARE OF route, prompt, evaluated_task, dataset,
         rubric, report, model, approver;

    IF route_task_id IS NULL THEN
        RAISE EXCEPTION 'judge calibration contains a missing scope binding'
            USING ERRCODE = '23503';
    END IF;
    SELECT count(*),
           count(*) FILTER (
               WHERE task_definition_id <>
                    NEW.evaluated_task_definition_id
           )
      INTO actual_case_count, wrong_task_count
      FROM ai.evaluation_case
     WHERE dataset_version_id = NEW.dataset_version_id;
    IF route_task_id <> prompt_task_id
       OR NEW.resolved_judge_model_id NOT IN (
            route_primary_id,
            COALESCE(route_fallback_id, route_primary_id)
       )
       OR route_status NOT IN ('EVALUATING', 'CERTIFIED', 'ACTIVE')
       OR prompt_status NOT IN ('EVALUATING', 'CERTIFIED', 'ACTIVE')
       OR evaluated_task_status <> 'ACTIVE'
       OR dataset_status NOT IN ('LOCKED', 'ACTIVE')
       OR dataset_declared_count < 200
       OR actual_case_count <> dataset_declared_count
       OR actual_case_count < 200
       OR wrong_task_count <> 0
       OR model_status NOT IN ('EVALUATION', 'ACTIVE')
       OR NOT rubric_immutable
       OR rubric_kind_value NOT IN (
            'quality_report',
            'diff',
            'import_report',
            'audit_export',
            'other'
       )
       OR rubric_hash <> NEW.rubric_sha256
       OR NOT report_immutable
       OR report_kind_value NOT IN (
            'quality_report',
            'diff',
            'import_report',
            'audit_export',
            'other'
       )
       OR NOT approver_is_active_user
       OR NEW.approved_at > statement_timestamp()
       OR NEW.expires_at <= statement_timestamp() THEN
        RAISE EXCEPTION
            'judge calibration does not satisfy canonical scope/evidence gates'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_locked_evaluation_dataset(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_locked_evaluation_dataset"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
DECLARE
    actual_case_count bigint;
    invalid_case_artifact_count bigint;
    dataset_artifact_sha text;
    dataset_artifact_immutable boolean;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'evaluation dataset must be created in DRAFT'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.status NOT IN ('DRAFT', 'CURATING') THEN
            RAISE EXCEPTION
                'evaluation dataset % cannot be deleted after %',
                OLD.id,
                OLD.status
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;
    IF (OLD.status = 'DRAFT'
            AND NEW.status NOT IN ('DRAFT', 'CURATING', 'RETIRED'))
       OR (OLD.status = 'CURATING'
            AND NEW.status NOT IN ('CURATING', 'LOCKED', 'RETIRED'))
       OR (OLD.status = 'LOCKED'
            AND NEW.status NOT IN (
                'LOCKED', 'ACTIVE', 'COMPROMISED', 'RETIRED'
            ))
       OR (OLD.status = 'ACTIVE'
            AND NEW.status NOT IN ('ACTIVE', 'COMPROMISED', 'RETIRED'))
       OR (OLD.status = 'COMPROMISED'
            AND NEW.status NOT IN ('COMPROMISED', 'RETIRED'))
       OR (OLD.status = 'RETIRED' AND NEW.status <> 'RETIRED') THEN
        RAISE EXCEPTION
            'evaluation dataset lifecycle cannot move from % to %',
            OLD.status,
            NEW.status
            USING ERRCODE = '23514';
    END IF;
    IF OLD.status IN ('DRAFT', 'CURATING')
       AND NEW.status = 'LOCKED' THEN
        SELECT artifact.sha256, artifact.is_immutable
          INTO dataset_artifact_sha, dataset_artifact_immutable
          FROM ops.object_artifact AS artifact
         WHERE artifact.id = NEW.dataset_artifact_id
         FOR SHARE;
        SELECT count(*),
               count(*) FILTER (
                   WHERE input_artifact.id IS NULL
                      OR NOT input_artifact.is_immutable
                      OR (
                           candidate.gold_artifact_id IS NOT NULL
                           AND (
                               gold_artifact.id IS NULL
                               OR NOT gold_artifact.is_immutable
                           )
                      )
               )
          INTO actual_case_count, invalid_case_artifact_count
          FROM ai.evaluation_case AS candidate
          LEFT JOIN ops.object_artifact AS input_artifact
            ON input_artifact.id = candidate.input_artifact_id
          LEFT JOIN ops.object_artifact AS gold_artifact
            ON gold_artifact.id = candidate.gold_artifact_id
         WHERE candidate.dataset_version_id = OLD.id;
        IF actual_case_count = 0
           OR actual_case_count <> NEW.case_count THEN
            RAISE EXCEPTION
                'evaluation dataset % declares % cases but contains %',
                OLD.id,
                NEW.case_count,
                actual_case_count
                USING ERRCODE = '23514';
        END IF;
        IF dataset_artifact_immutable IS DISTINCT FROM true
           OR dataset_artifact_sha IS DISTINCT FROM NEW.dataset_sha256
           OR invalid_case_artifact_count <> 0 THEN
            RAISE EXCEPTION
                'evaluation dataset requires hash-matched immutable dataset/case artifacts'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    IF OLD.status IN ('LOCKED', 'ACTIVE', 'COMPROMISED', 'RETIRED') THEN
        IF ROW(
            NEW.id,
            NEW.display_id,
            NEW.dataset_code,
            NEW.version_no,
            NEW.purpose,
            NEW.split_policy,
            NEW.dataset_artifact_id,
            NEW.dataset_sha256,
            NEW.case_count,
            NEW.locked_by_principal_id,
            NEW.locked_at,
            NEW.created_at
        ) IS DISTINCT FROM ROW(
            OLD.id,
            OLD.display_id,
            OLD.dataset_code,
            OLD.version_no,
            OLD.purpose,
            OLD.split_policy,
            OLD.dataset_artifact_id,
            OLD.dataset_sha256,
            OLD.case_count,
            OLD.locked_by_principal_id,
            OLD.locked_at,
            OLD.created_at
        ) THEN
            RAISE EXCEPTION 'LOCKED evaluation dataset content is immutable'
                USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_model_definition_lifecycle(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_model_definition_lifecycle"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'EVALUATION' THEN
            RAISE EXCEPTION 'model definition must be created in EVALUATION'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'model definitions are not deletable'
            USING ERRCODE = '55000';
    END IF;
    IF ROW(
        NEW.id, NEW.provider_code, NEW.provider_model_id, NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.id, OLD.provider_code, OLD.provider_model_id, OLD.created_at
    ) THEN
        RAISE EXCEPTION 'model identity is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF ROW(
        NEW.display_name,
        NEW.capabilities,
        NEW.input_price_per_million,
        NEW.cached_input_price_per_million,
        NEW.output_price_per_million,
        NEW.pricing_currency,
        NEW.pricing_observed_at,
        NEW.context_window_tokens,
        NEW.max_output_tokens,
        NEW.knowledge_cutoff,
        NEW.metadata_observed_at,
        NEW.provider_metadata
    ) IS DISTINCT FROM ROW(
        OLD.display_name,
        OLD.capabilities,
        OLD.input_price_per_million,
        OLD.cached_input_price_per_million,
        OLD.output_price_per_million,
        OLD.pricing_currency,
        OLD.pricing_observed_at,
        OLD.context_window_tokens,
        OLD.max_output_tokens,
        OLD.knowledge_cutoff,
        OLD.metadata_observed_at,
        OLD.provider_metadata
    ) AND EXISTS (
        SELECT 1 FROM ai.model_route_version
         WHERE primary_model_id = OLD.id OR fallback_model_id = OLD.id
    ) THEN
        RAISE EXCEPTION 'referenced provider model snapshot is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF (OLD.status = 'EVALUATION' AND NEW.status NOT IN (
            'EVALUATION', 'ACTIVE', 'PAUSED', 'BLOCKED', 'RETIRED'
       ))
       OR (OLD.status = 'ACTIVE' AND NEW.status NOT IN (
            'ACTIVE', 'PAUSED', 'BLOCKED', 'RETIRED'
       ))
       OR (OLD.status = 'PAUSED' AND NEW.status NOT IN (
            'PAUSED', 'ACTIVE', 'BLOCKED', 'RETIRED'
       ))
       OR (OLD.status = 'BLOCKED' AND NEW.status NOT IN (
            'BLOCKED', 'EVALUATION', 'RETIRED'
       ))
       OR (OLD.status = 'RETIRED' AND NEW.status <> 'RETIRED') THEN
        RAISE EXCEPTION 'model lifecycle cannot move from % to %',
            OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    IF OLD.status = 'ACTIVE'
       AND NEW.status <> 'ACTIVE'
       AND ai.has_live_rollback_dependents('MODEL', OLD.id) THEN
        RAISE EXCEPTION 'model % is a live rollback component', OLD.id
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_model_route_lifecycle(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_model_route_lifecycle"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'model route version must be created in DRAFT'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'model route versions are not deletable'
            USING ERRCODE = '55000';
    END IF;
    IF ROW(
        NEW.id, NEW.route_code, NEW.version_no, NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.id, OLD.route_code, OLD.version_no, OLD.created_at
    ) THEN
        RAISE EXCEPTION 'model route identity is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.status <> 'DRAFT' AND ROW(
        NEW.task_definition_id,
        NEW.primary_model_id,
        NEW.fallback_model_id,
        NEW.route_config,
        NEW.monthly_budget_jpy,
        NEW.per_job_budget_jpy
    ) IS DISTINCT FROM ROW(
        OLD.task_definition_id,
        OLD.primary_model_id,
        OLD.fallback_model_id,
        OLD.route_config,
        OLD.monthly_budget_jpy,
        OLD.per_job_budget_jpy
    ) THEN
        RAISE EXCEPTION 'evaluated model route content is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF (OLD.status = 'DRAFT' AND NEW.status NOT IN ('DRAFT', 'EVALUATING'))
       OR (OLD.status = 'EVALUATING' AND NEW.status NOT IN (
            'EVALUATING', 'CERTIFIED', 'RETIRED'
       ))
       OR (OLD.status = 'CERTIFIED' AND NEW.status NOT IN (
            'CERTIFIED', 'CANARY', 'PAUSED', 'RETIRED'
       ))
       OR (OLD.status = 'CANARY' AND NEW.status NOT IN (
            'CANARY', 'ACTIVE', 'PAUSED', 'ROLLED_BACK', 'RETIRED'
       ))
       OR (OLD.status = 'ACTIVE' AND NEW.status NOT IN (
            'ACTIVE', 'PAUSED', 'ROLLED_BACK', 'RETIRED'
       ))
       OR (OLD.status = 'PAUSED' AND NEW.status NOT IN (
            'PAUSED', 'CANARY', 'ACTIVE', 'ROLLED_BACK', 'RETIRED'
       ))
       OR (OLD.status IN ('ROLLED_BACK', 'RETIRED')
            AND NEW.status <> OLD.status) THEN
        RAISE EXCEPTION 'route lifecycle cannot move from % to %',
            OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    IF OLD.status = 'DRAFT' AND NEW.status = 'EVALUATING'
       AND (
            jsonb_typeof(NEW.route_config -> 'canary_max_percent')
                IS DISTINCT FROM 'number'
            OR (NEW.route_config ->> 'canary_max_percent')::numeric < 0
            OR (NEW.route_config ->> 'canary_max_percent')::numeric > 100
            OR mod(
                (NEW.route_config ->> 'canary_max_percent')::numeric,
                1
            ) <> 0
       ) THEN
        RAISE EXCEPTION 'route requires integer canary_max_percent 0..100'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.status IN ('CANARY', 'ACTIVE')
       AND NOT EXISTS (
            SELECT 1 FROM ai.release_decision
             WHERE model_route_version_id = NEW.id
               AND status = CASE NEW.status
                    WHEN 'CANARY' THEN 'APPROVED_CANARY'
                    ELSE 'APPROVED_ACTIVE'
               END
       ) THEN
        RAISE EXCEPTION '% route requires matching release decision', NEW.status
            USING ERRCODE = '23514';
    END IF;
    IF OLD.status = 'ACTIVE'
       AND NEW.status <> 'ACTIVE'
       AND ai.has_live_rollback_dependents('ROUTE', OLD.id) THEN
        RAISE EXCEPTION 'route % is a live rollback component', OLD.id
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_open_evaluation_run_result(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_open_evaluation_run_result"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
DECLARE
    run_status text;
    run_dataset_id uuid;
    run_task_definition_id uuid;
    run_prompt_version_id uuid;
    run_model_route_version_id uuid;
    run_resolved_model_id uuid;
    run_output_schema_version_id uuid;
    run_policy_bundle_version_id uuid;
    case_dataset_id uuid;
    case_task_definition_id uuid;
    case_input_artifact_id uuid;
    case_expected_disposition text;
    attempt_status text;
    attempt_model_id uuid;
    attempt_resolved_model_id text;
    attempt_input_artifact_id uuid;
    attempt_input_sha256 text;
    attempt_output_artifact_id uuid;
    attempt_output_sha256 text;
    attempt_provider_request_id text;
    attempt_refusal_code text;
    attempt_error_class text;
    attempt_error_code text;
    attempt_validation_status text;
    job_task_definition_id uuid;
    job_prompt_version_id uuid;
    job_model_route_version_id uuid;
    job_output_schema_version_id uuid;
    job_policy_bundle_version_id uuid;
    job_release_decision_id uuid;
    model_provider_model_id text;
    output_artifact_immutable boolean;
    output_artifact_kind text;
    output_artifact_sha256 text;
    input_artifact_immutable boolean;
    input_artifact_sha256 text;
    zero_tolerance_artifact_immutable boolean;
    zero_tolerance_artifact_sha256 text;
BEGIN
    SELECT run.status,
           run.dataset_version_id,
           suite.task_definition_id,
           run.prompt_version_id,
           run.model_route_version_id,
           run.resolved_model_id,
           run.output_schema_version_id,
           run.policy_bundle_version_id
      INTO run_status,
           run_dataset_id,
           run_task_definition_id,
           run_prompt_version_id,
           run_model_route_version_id,
           run_resolved_model_id,
           run_output_schema_version_id,
           run_policy_bundle_version_id
      FROM ai.evaluation_run AS run
      JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
     WHERE run.id = NEW.evaluation_run_id
     FOR SHARE OF run, suite;
    IF run_status IS NULL THEN
        RAISE EXCEPTION 'evaluation run % does not exist', NEW.evaluation_run_id
            USING ERRCODE = '23503';
    END IF;
    IF run_status NOT IN ('RUNNING', 'GRADING', 'HUMAN_REVIEW') THEN
        RAISE EXCEPTION
            'evaluation result cannot be appended while run % is %',
            NEW.evaluation_run_id,
            run_status
            USING ERRCODE = '55000';
    END IF;
    SELECT dataset_version_id,
           task_definition_id,
           input_artifact_id,
           expected_disposition
      INTO case_dataset_id,
           case_task_definition_id,
           case_input_artifact_id,
           case_expected_disposition
      FROM ai.evaluation_case
     WHERE id = NEW.evaluation_case_id
     FOR SHARE;
    IF case_dataset_id IS NULL THEN
        RAISE EXCEPTION
            'evaluation case % does not exist',
            NEW.evaluation_case_id
            USING ERRCODE = '23503';
    END IF;
    IF case_dataset_id <> run_dataset_id
       OR case_task_definition_id <> run_task_definition_id THEN
        RAISE EXCEPTION
            'evaluation case % does not match run dataset/task binding',
            NEW.evaluation_case_id
            USING ERRCODE = '23514';
    END IF;
    IF NEW.status = 'PASSED'
       AND NEW.disposition <> case_expected_disposition THEN
        RAISE EXCEPTION
            'passing evaluation result disposition % does not match expected %',
            NEW.disposition,
            case_expected_disposition
            USING ERRCODE = '23514';
    END IF;
    SELECT artifact.sha256, artifact.is_immutable
      INTO zero_tolerance_artifact_sha256,
           zero_tolerance_artifact_immutable
      FROM ops.object_artifact AS artifact
     WHERE artifact.id = NEW.zero_tolerance_evidence_artifact_id
     FOR SHARE;
    IF zero_tolerance_artifact_sha256 IS DISTINCT FROM
            NEW.zero_tolerance_evidence_sha256
       OR zero_tolerance_artifact_immutable IS DISTINCT FROM true THEN
        RAISE EXCEPTION
            'zero-tolerance evidence must bind an immutable exact-hash artifact'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.disposition = 'BLOCK_BEFORE_PROVIDER' THEN
        IF NEW.ai_attempt_id IS NOT NULL
           OR NEW.output_artifact_id IS NOT NULL THEN
            RAISE EXCEPTION
                'pre-provider block cannot contain attempt/output evidence'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.ai_attempt_id IS NULL THEN
        RAISE EXCEPTION
            'provider disposition requires an exact AI attempt'
            USING ERRCODE = '23514';
    END IF;

    SELECT attempt.status,
           attempt.model_id,
           attempt.resolved_model_id,
           attempt.input_artifact_id,
           attempt.input_sha256,
           attempt.output_artifact_id,
           attempt.output_sha256,
           attempt.provider_request_id,
           attempt.refusal_code,
           attempt.error_class,
           attempt.error_code,
           attempt.validation_status,
           job.task_definition_id,
           job.prompt_version_id,
           job.model_route_version_id,
           job.output_schema_version_id,
           job.policy_bundle_version_id,
           job.release_decision_id,
           model.provider_model_id,
           input_artifact.sha256,
           input_artifact.is_immutable
      INTO attempt_status,
           attempt_model_id,
           attempt_resolved_model_id,
           attempt_input_artifact_id,
           attempt_input_sha256,
           attempt_output_artifact_id,
           attempt_output_sha256,
           attempt_provider_request_id,
           attempt_refusal_code,
           attempt_error_class,
           attempt_error_code,
           attempt_validation_status,
           job_task_definition_id,
           job_prompt_version_id,
           job_model_route_version_id,
           job_output_schema_version_id,
           job_policy_bundle_version_id,
           job_release_decision_id,
           model_provider_model_id,
           input_artifact_sha256,
           input_artifact_immutable
      FROM ai.ai_attempt AS attempt
      JOIN ai.ai_job AS job ON job.id = attempt.ai_job_id
      JOIN ai.model_definition AS model ON model.id = attempt.model_id
      JOIN ops.object_artifact AS input_artifact
        ON input_artifact.id = attempt.input_artifact_id
     WHERE attempt.id = NEW.ai_attempt_id
     FOR SHARE OF attempt, job, model, input_artifact;
    IF attempt_status IS NULL THEN
        RAISE EXCEPTION 'AI attempt % does not exist', NEW.ai_attempt_id
            USING ERRCODE = '23503';
    END IF;
    IF attempt_model_id IS DISTINCT FROM run_resolved_model_id
       OR attempt_resolved_model_id IS DISTINCT FROM model_provider_model_id
       OR attempt_input_artifact_id IS DISTINCT FROM case_input_artifact_id
       OR attempt_input_sha256 IS DISTINCT FROM input_artifact_sha256
       OR input_artifact_immutable IS DISTINCT FROM true
       OR job_task_definition_id IS DISTINCT FROM run_task_definition_id
       OR job_prompt_version_id IS DISTINCT FROM run_prompt_version_id
       OR job_model_route_version_id IS DISTINCT FROM
            run_model_route_version_id
       OR job_output_schema_version_id IS DISTINCT FROM
            run_output_schema_version_id
       OR job_policy_bundle_version_id IS DISTINCT FROM
            run_policy_bundle_version_id
       OR job_release_decision_id IS NOT NULL THEN
        RAISE EXCEPTION
            'AI attempt/job provenance does not match the evaluation case/run'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.disposition IN (
            'CALL_PROVIDER_AND_PASS', 'CALL_PROVIDER_AND_FLAG'
       ) THEN
        IF attempt_status <> 'SUCCEEDED'
           OR attempt_validation_status IS DISTINCT FROM 'PASSED'
           OR attempt_provider_request_id IS NULL
           OR btrim(attempt_provider_request_id) = ''
           OR attempt_refusal_code IS NOT NULL
           OR attempt_error_class IS NOT NULL
           OR attempt_error_code IS NOT NULL
           OR attempt_output_artifact_id IS NULL
           OR NEW.output_artifact_id IS DISTINCT FROM
                attempt_output_artifact_id
           OR attempt_output_sha256 IS NULL THEN
            RAISE EXCEPTION
                'successful provider disposition lacks exact successful attempt evidence'
                USING ERRCODE = '23514';
        END IF;
        SELECT artifact_kind, sha256, is_immutable
          INTO output_artifact_kind,
               output_artifact_sha256,
               output_artifact_immutable
          FROM ops.object_artifact
         WHERE id = NEW.output_artifact_id
         FOR SHARE;
        IF output_artifact_kind IS DISTINCT FROM 'ai_output'
           OR output_artifact_sha256 IS DISTINCT FROM attempt_output_sha256
           OR output_artifact_immutable IS DISTINCT FROM true THEN
            RAISE EXCEPTION
                'evaluation output must be the immutable hashed AI-attempt output'
                USING ERRCODE = '23514';
        END IF;
    ELSIF NEW.disposition = 'EXPECTED_REFUSAL' THEN
        IF attempt_status <> 'REFUSED'
           OR attempt_validation_status IS DISTINCT FROM 'FAILED'
           OR attempt_provider_request_id IS NULL
           OR btrim(attempt_provider_request_id) = ''
           OR attempt_refusal_code IS NULL
           OR btrim(attempt_refusal_code) = ''
           OR attempt_output_artifact_id IS NOT NULL
           OR attempt_output_sha256 IS NOT NULL
           OR NEW.output_artifact_id IS NOT NULL
           OR attempt_error_class IS NOT NULL
           OR attempt_error_code IS NOT NULL THEN
            RAISE EXCEPTION
                'expected refusal lacks exact refusal attempt evidence'
                USING ERRCODE = '23514';
        END IF;
    ELSIF NEW.disposition = 'EXPECTED_TERMINAL_FAILURE' THEN
        IF attempt_status NOT IN ('FAILED', 'TIMED_OUT', 'CANCELLED')
           OR attempt_validation_status IS DISTINCT FROM 'FAILED'
           OR attempt_refusal_code IS NOT NULL
           OR attempt_output_artifact_id IS NOT NULL
           OR attempt_output_sha256 IS NOT NULL
           OR NEW.output_artifact_id IS NOT NULL
           OR attempt_error_class IS NULL
           OR btrim(attempt_error_class) = ''
           OR attempt_error_code IS NULL
           OR btrim(attempt_error_code) = '' THEN
            RAISE EXCEPTION
                'expected terminal failure lacks exact terminal attempt evidence'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        RAISE EXCEPTION 'unknown evaluation disposition %', NEW.disposition
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_open_human_evaluation(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_open_human_evaluation"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
DECLARE
    run_status text;
    prompt_author_id uuid;
    notes_artifact_immutable boolean;
BEGIN
    SELECT run.status, prompt.author_principal_id
      INTO run_status, prompt_author_id
      FROM ai.evaluation_case_result AS result
      JOIN ai.evaluation_run AS run ON run.id = result.evaluation_run_id
      JOIN ai.prompt_version AS prompt ON prompt.id = run.prompt_version_id
     WHERE result.id = NEW.evaluation_case_result_id
     FOR SHARE OF result, run, prompt;
    IF run_status IS NULL THEN
        RAISE EXCEPTION
            'evaluation case result % does not exist',
            NEW.evaluation_case_result_id
            USING ERRCODE = '23503';
    END IF;
    IF run_status <> 'HUMAN_REVIEW' THEN
        RAISE EXCEPTION
            'human evaluation requires HUMAN_REVIEW run; got %',
            run_status
            USING ERRCODE = '55000';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM iam.principal
         WHERE id = NEW.reviewer_principal_id
           AND principal_type = 'USER'
           AND status = 'ACTIVE'
    ) THEN
        RAISE EXCEPTION
            'human evaluation reviewer must be an ACTIVE USER principal'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.is_adjudication
       AND NEW.reviewer_principal_id = prompt_author_id THEN
        RAISE EXCEPTION
            'prompt author cannot adjudicate the same release evaluation'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.notes_artifact_id IS NOT NULL THEN
        SELECT is_immutable
          INTO notes_artifact_immutable
          FROM ops.object_artifact
         WHERE id = NEW.notes_artifact_id
         FOR SHARE;
        IF notes_artifact_immutable IS DISTINCT FROM true THEN
            RAISE EXCEPTION
                'human evaluation notes artifact must be immutable'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_output_schema_lifecycle(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_output_schema_lifecycle"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'output schema version must be created in DRAFT'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'output schema versions are not deletable'
            USING ERRCODE = '55000';
    END IF;
    IF ROW(
        NEW.id, NEW.schema_code, NEW.version_no, NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.id, OLD.schema_code, OLD.version_no, OLD.created_at
    ) THEN
        RAISE EXCEPTION 'output schema identity is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.status <> 'DRAFT' AND ROW(
        NEW.git_path, NEW.git_commit_sha, NEW.schema_sha256
    ) IS DISTINCT FROM ROW(
        OLD.git_path, OLD.git_commit_sha, OLD.schema_sha256
    ) THEN
        RAISE EXCEPTION 'active output schema content hash is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF (OLD.status = 'DRAFT' AND NEW.status NOT IN (
            'DRAFT', 'ACTIVE', 'RETIRED'
       ))
       OR (OLD.status = 'ACTIVE' AND NEW.status NOT IN (
            'ACTIVE', 'RETIRED'
       ))
       OR (OLD.status = 'RETIRED' AND NEW.status <> 'RETIRED') THEN
       RAISE EXCEPTION 'output schema lifecycle cannot move from % to %',
            OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    IF OLD.status = 'ACTIVE'
       AND NEW.status <> 'ACTIVE'
       AND ai.has_live_rollback_dependents('SCHEMA', OLD.id) THEN
        RAISE EXCEPTION 'output schema % is a live rollback component', OLD.id
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_prompt_version_lifecycle(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_prompt_version_lifecycle"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT' OR NEW.author_principal_id IS NULL THEN
            RAISE EXCEPTION 'prompt version must be human-authored in DRAFT'
                USING ERRCODE = '23514';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM iam.principal
             WHERE id = NEW.author_principal_id
               AND principal_type = 'USER'
               AND status = 'ACTIVE'
        ) THEN
            RAISE EXCEPTION 'prompt author must be an ACTIVE USER'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'prompt versions are not deletable'
            USING ERRCODE = '55000';
    END IF;
    IF ROW(
        NEW.id,
        NEW.display_id,
        NEW.task_definition_id,
        NEW.prompt_code,
        NEW.version_no,
        NEW.created_at,
        NEW.author_principal_id
    ) IS DISTINCT FROM ROW(
        OLD.id,
        OLD.display_id,
        OLD.task_definition_id,
        OLD.prompt_code,
        OLD.version_no,
        OLD.created_at,
        OLD.author_principal_id
    ) THEN
        RAISE EXCEPTION 'prompt identity/author provenance is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.status <> 'DRAFT' AND ROW(
        NEW.git_path,
        NEW.git_commit_sha,
        NEW.template_sha256,
        NEW.locale,
        NEW.compiler_version,
        NEW.input_contract_sha256,
        NEW.policy_test_status
    ) IS DISTINCT FROM ROW(
        OLD.git_path,
        OLD.git_commit_sha,
        OLD.template_sha256,
        OLD.locale,
        OLD.compiler_version,
        OLD.input_contract_sha256,
        OLD.policy_test_status
    ) THEN
        RAISE EXCEPTION 'reviewed prompt content hashes are immutable'
            USING ERRCODE = '55000';
    END IF;
    IF (OLD.status = 'DRAFT' AND NEW.status NOT IN ('DRAFT', 'IN_REVIEW'))
       OR (OLD.status = 'IN_REVIEW' AND NEW.status NOT IN (
            'IN_REVIEW', 'EVALUATING', 'RETIRED'
       ))
       OR (OLD.status = 'EVALUATING' AND NEW.status NOT IN (
            'EVALUATING', 'CERTIFIED', 'RETIRED'
       ))
       OR (OLD.status = 'CERTIFIED' AND NEW.status NOT IN (
            'CERTIFIED', 'ACTIVE', 'SUSPENDED', 'RETIRED'
       ))
       OR (OLD.status = 'ACTIVE' AND NEW.status NOT IN (
            'ACTIVE', 'SUSPENDED', 'RETIRED'
       ))
       OR (OLD.status = 'SUSPENDED' AND NEW.status NOT IN (
            'SUSPENDED', 'ACTIVE', 'RETIRED'
       ))
       OR (OLD.status IN ('RETIRED', 'REJECTED')
            AND NEW.status <> OLD.status) THEN
        RAISE EXCEPTION 'prompt lifecycle cannot move from % to %',
            OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    IF OLD.status <> 'CERTIFIED' AND NEW.status = 'CERTIFIED'
       AND NOT EXISTS (
            SELECT 1 FROM iam.principal
             WHERE id = NEW.approved_by_principal_id
               AND principal_type = 'USER'
               AND status = 'ACTIVE'
               AND id <> NEW.author_principal_id
       ) THEN
        RAISE EXCEPTION 'prompt certification requires a distinct ACTIVE USER'
            USING ERRCODE = '23514';
    END IF;
    IF OLD.status <> 'ACTIVE' AND NEW.status = 'ACTIVE'
       AND NOT EXISTS (
            SELECT 1 FROM ai.release_decision
             WHERE prompt_version_id = NEW.id
               AND status = 'APPROVED_ACTIVE'
       ) THEN
        RAISE EXCEPTION 'ACTIVE prompt requires an active release decision'
            USING ERRCODE = '23514';
    END IF;
    IF OLD.status = 'ACTIVE'
       AND NEW.status <> 'ACTIVE'
       AND ai.has_live_rollback_dependents('PROMPT', OLD.id) THEN
        RAISE EXCEPTION 'prompt % is a live rollback component', OLD.id
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_release_approval_mutation(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_release_approval_mutation"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
DECLARE
    release_status text;
    release_manifest text;
    release_prompt_id uuid;
    release_run_id uuid;
    release_canary_completed_at timestamptz;
    release_canary_txid bigint;
    release_canary_completed_txid bigint;
    run_completed_at timestamptz;
    suite_status_value text;
    task_status_value text;
    prompt_status_value text;
    route_status_value text;
    schema_status_value text;
    policy_status_value text;
    model_status_value text;
    dataset_status_value text;
    prompt_author_id uuid;
    primary_is_active_user boolean;
    second_is_active_user boolean;
    artifact_hash text;
    artifact_kind_value text;
    artifact_immutable boolean;
    existing_canary_manifest text;
    existing_canary_artifact_id uuid;
    existing_canary_artifact_sha text;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        RAISE EXCEPTION 'release approval bundles are append-only'
            USING ERRCODE = '55000';
    END IF;
    SELECT release.status,
           release.decision_manifest_sha256,
           release.prompt_version_id,
           release.evaluation_run_id,
           release.canary_completed_at,
           release.canary_started_txid,
           release.canary_completed_txid,
           run.completed_at,
           suite.status,
           task.status,
           prompt.status,
           route.status,
           output_schema.status,
           bundle.status,
           model.status,
           dataset.status,
           prompt.author_principal_id,
           (
               primary_principal.principal_type = 'USER'
               AND primary_principal.status = 'ACTIVE'
           ),
           (
               second_principal.principal_type = 'USER'
               AND second_principal.status = 'ACTIVE'
           ),
           artifact.sha256,
           artifact.artifact_kind,
           artifact.is_immutable
      INTO release_status,
           release_manifest,
           release_prompt_id,
           release_run_id,
           release_canary_completed_at,
           release_canary_txid,
           release_canary_completed_txid,
           run_completed_at,
           suite_status_value,
           task_status_value,
           prompt_status_value,
           route_status_value,
           schema_status_value,
           policy_status_value,
           model_status_value,
           dataset_status_value,
           prompt_author_id,
           primary_is_active_user,
           second_is_active_user,
           artifact_hash,
           artifact_kind_value,
           artifact_immutable
      FROM ai.release_decision AS release
      JOIN ai.evaluation_run AS run ON run.id = release.evaluation_run_id
      JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
      JOIN ai.task_definition AS task
        ON task.id = release.task_definition_id
      JOIN ai.prompt_version AS prompt ON prompt.id = release.prompt_version_id
      JOIN ai.model_route_version AS route
        ON route.id = release.model_route_version_id
      JOIN ai.output_schema_version AS output_schema
        ON output_schema.id = release.output_schema_version_id
      JOIN policy.policy_bundle AS bundle
        ON bundle.id = release.policy_bundle_version_id
      JOIN ai.model_definition AS model
        ON model.id = release.resolved_model_id
      JOIN ai.evaluation_dataset_version AS dataset
        ON dataset.id = release.dataset_version_id
      JOIN iam.principal AS primary_principal
        ON primary_principal.id = NEW.primary_approver_principal_id
      JOIN iam.principal AS second_principal
        ON second_principal.id = NEW.second_approver_principal_id
      JOIN ops.object_artifact AS artifact
        ON artifact.id = NEW.approval_artifact_id
     WHERE release.id = NEW.release_decision_id
     FOR SHARE OF release, run, suite, task, prompt, route, output_schema,
         bundle, model, dataset,
         primary_principal, second_principal, artifact;
    IF release_status IS NULL THEN
        RAISE EXCEPTION 'release approval contains a missing binding'
            USING ERRCODE = '23503';
    END IF;
    IF NOT primary_is_active_user
       OR NOT second_is_active_user
       OR prompt_author_id IS NULL
       OR prompt_author_id IN (
            NEW.primary_approver_principal_id,
            NEW.second_approver_principal_id
       )
       OR suite_status_value <> 'ACTIVE'
       OR task_status_value <> 'ACTIVE'
       OR prompt_status_value NOT IN ('CERTIFIED', 'ACTIVE')
       OR schema_status_value <> 'ACTIVE'
       OR policy_status_value <> 'ACTIVE'
       OR model_status_value NOT IN ('EVALUATION', 'ACTIVE')
       OR dataset_status_value NOT IN ('LOCKED', 'ACTIVE')
       OR NOT artifact_immutable
       OR artifact_kind_value NOT IN (
            'quality_report',
            'diff',
            'import_report',
            'audit_export',
            'other'
       )
       OR artifact_hash <> NEW.approval_sha256
       OR NEW.signed_at < run_completed_at
       OR NEW.signed_at > statement_timestamp() THEN
        RAISE EXCEPTION 'release approval authority/evidence is invalid'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.phase = 'CANARY' THEN
        IF release_status <> 'READY_FOR_REVIEW'
           OR route_status_value <> 'CERTIFIED'
           OR NEW.decision_manifest_sha256 <> release_manifest THEN
            RAISE EXCEPTION
                'CANARY approval must bind the review-ready manifest'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        SELECT decision_manifest_sha256,
               approval_artifact_id,
               approval_sha256
          INTO existing_canary_manifest,
               existing_canary_artifact_id,
               existing_canary_artifact_sha
          FROM ai.release_approval
         WHERE release_decision_id = NEW.release_decision_id
           AND phase = 'CANARY'
         FOR SHARE;
        IF release_status <> 'APPROVED_CANARY'
           OR route_status_value <> 'CANARY'
           OR existing_canary_manifest IS NULL
           OR NEW.decision_manifest_sha256 = existing_canary_manifest
           OR NEW.approval_artifact_id = existing_canary_artifact_id
           OR NEW.approval_sha256 = existing_canary_artifact_sha
           OR release_canary_completed_at IS NULL
           OR NEW.signed_at < release_canary_completed_at
           OR release_canary_txid IS NULL
           OR release_canary_txid = txid_current()
           OR release_canary_completed_txid IS NULL
           OR release_canary_completed_txid = txid_current() THEN
            RAISE EXCEPTION
                'ACTIVE approval requires prior canary evidence and a new transaction/manifest'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END
$$;
