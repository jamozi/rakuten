-- ST-0304 physical translation fragment 03 of 11.
-- Source: approved RAOS data catalog plus finalized ST-0003/ST-0004 semantics.
-- Capture: PostgreSQL 18.4 pg_dump --schema-only --no-owner --no-privileges
--          --no-security-labels --quote-all-identifiers for the six owned schemas.
-- Schema creation/comments are rendered once by the ST-0304 generator. The 22
-- role-bound CREATE POLICY objects remain ST-0306-owned. ENABLE/FORCE RLS remains.

--
-- Name: guard_release_decision_evidence(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_release_decision_evidence"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai', 'policy'
    AS $$
DECLARE
    run_status text;
    run_completed_at timestamptz;
    run_suite_id uuid;
    run_baseline_id uuid;
    run_task_id uuid;
    run_prompt_id uuid;
    run_route_id uuid;
    run_schema_id uuid;
    run_policy_id uuid;
    run_dataset_id uuid;
    run_model_id uuid;
    run_code_sha text;
    suite_status_value text;
    suite_risk text;
    task_status_value text;
    suite_task_risk text;
    suite_config_value jsonb;
    dataset_status text;
    prompt_status_value text;
    route_status_value text;
    schema_status_value text;
    policy_status_value text;
    model_status_value text;
    route_config_value jsonb;
    route_canary_cap integer;
    approval_release_id uuid;
    approval_phase text;
    approval_manifest text;
    approval_primary_id uuid;
    approval_second_id uuid;
    approval_signed_at timestamptz;
    target_status text;
    target_task_id uuid;
    target_signed_at timestamptz;
    target_task_status text;
    target_prompt_status text;
    target_route_status text;
    target_schema_status text;
    target_model_status text;
    target_policy_status text;
    model_judge_count bigint;
    model_judge_calibration_count bigint;
    model_judge_scope_matches boolean;
    calibration_status text;
    calibration_expiry timestamptz;
    champion_release_id uuid;
    champion_baseline_valid boolean;
BEGIN
    IF TG_OP <> 'UPDATE' THEN
        RETURN NEW;
    END IF;

    IF OLD.status <> 'DRAFT'
       AND ROW(
            NEW.judge_calibration_id,
            NEW.rollback_strategy,
            NEW.rollback_release_decision_id,
            NEW.rollback_runbook_artifact_id,
            NEW.rollback_runbook_sha256,
            NEW.canary_monitoring_artifact_id,
            NEW.canary_monitoring_sha256
       ) IS DISTINCT FROM ROW(
            OLD.judge_calibration_id,
            OLD.rollback_strategy,
            OLD.rollback_release_decision_id,
            OLD.rollback_runbook_artifact_id,
            OLD.rollback_runbook_sha256,
            OLD.canary_monitoring_artifact_id,
            OLD.canary_monitoring_sha256
       ) THEN
        RAISE EXCEPTION 'release evidence bindings are frozen after DRAFT'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.canary_approval_id IS NOT NULL
       AND NEW.canary_approval_id IS DISTINCT FROM OLD.canary_approval_id THEN
        RAISE EXCEPTION 'canary approval binding is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.active_approval_id IS NOT NULL
       AND NEW.active_approval_id IS DISTINCT FROM OLD.active_approval_id THEN
        RAISE EXCEPTION 'active approval binding is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.canary_started_at IS NOT NULL
       AND ROW(
            NEW.canary_started_at,
            NEW.canary_started_txid
       ) IS DISTINCT FROM ROW(
            OLD.canary_started_at,
            OLD.canary_started_txid
       ) THEN
        RAISE EXCEPTION 'canary start time/transaction is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.canary_evidence_artifact_id IS NOT NULL
       AND ROW(
            NEW.canary_evidence_artifact_id,
            NEW.canary_evidence_sha256,
            NEW.canary_started_at,
            NEW.canary_completed_at,
            NEW.canary_started_txid,
            NEW.canary_completed_txid
       ) IS DISTINCT FROM ROW(
            OLD.canary_evidence_artifact_id,
            OLD.canary_evidence_sha256,
            OLD.canary_started_at,
            OLD.canary_completed_at,
            OLD.canary_started_txid,
            OLD.canary_completed_txid
       ) THEN
        RAISE EXCEPTION 'canary evidence is immutable once recorded'
            USING ERRCODE = '55000';
    END IF;

    IF OLD.status = 'APPROVED_CANARY'
       AND NEW.status = 'APPROVED_CANARY'
       AND OLD.canary_evidence_artifact_id IS NULL
       AND NEW.canary_evidence_artifact_id IS NOT NULL THEN
        PERFORM 1
          FROM ai.evaluation_run AS run
          JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
          JOIN ai.task_definition AS task
            ON task.id = NEW.task_definition_id
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
          JOIN ai.evaluation_dataset_version AS dataset
            ON dataset.id = NEW.dataset_version_id
         WHERE run.id = NEW.evaluation_run_id
           AND suite.status = 'ACTIVE'
           AND task.status = 'ACTIVE'
           AND prompt.status IN ('CERTIFIED', 'ACTIVE')
           AND route.status = 'CANARY'
           AND output_schema.status = 'ACTIVE'
           AND bundle.status = 'ACTIVE'
           AND model.status IN ('EVALUATION', 'ACTIVE')
           AND dataset.status IN ('LOCKED', 'ACTIVE')
         FOR SHARE OF run, suite, task, prompt, route, output_schema,
             bundle, model, dataset;
        IF NOT FOUND
           OR NEW.canary_started_at IS DISTINCT FROM OLD.canary_started_at
           OR NEW.canary_started_txid IS DISTINCT FROM OLD.canary_started_txid
           OR NEW.canary_completed_at <= OLD.canary_started_at
           OR NEW.canary_completed_at > statement_timestamp()
           OR OLD.canary_started_txid = txid_current()
           OR NEW.canary_evidence_sha256 IS NULL
           OR NOT ai.artifact_matches_immutable_hash(
                NEW.canary_evidence_artifact_id,
                NEW.canary_evidence_sha256
           ) THEN
            RAISE EXCEPTION 'canary evidence/time/hash is invalid'
                USING ERRCODE = '23514';
        END IF;
        NEW.canary_completed_txid := txid_current();
        RETURN NEW;
    END IF;

    IF OLD.status = NEW.status
       OR NEW.status NOT IN (
            'READY_FOR_REVIEW', 'APPROVED_CANARY', 'APPROVED_ACTIVE'
       ) THEN
        RETURN NEW;
    END IF;

    SELECT run.status,
           run.completed_at,
           run.suite_id,
           run.baseline_evaluation_run_id,
           suite.task_definition_id,
           run.prompt_version_id,
           run.model_route_version_id,
           run.output_schema_version_id,
           run.policy_bundle_version_id,
           run.dataset_version_id,
           run.resolved_model_id,
           run.code_git_sha,
           suite.status,
           suite.risk_level,
           task.status,
           task.risk_level,
           suite.suite_config,
           dataset.status,
           prompt.status,
           route.status,
           output_schema.status,
           bundle.status,
           model.status,
           route.route_config
      INTO run_status,
           run_completed_at,
           run_suite_id,
           run_baseline_id,
           run_task_id,
           run_prompt_id,
           run_route_id,
           run_schema_id,
           run_policy_id,
           run_dataset_id,
           run_model_id,
           run_code_sha,
           suite_status_value,
           suite_risk,
           task_status_value,
           suite_task_risk,
           suite_config_value,
           dataset_status,
           prompt_status_value,
           route_status_value,
           schema_status_value,
           policy_status_value,
           model_status_value,
           route_config_value
      FROM ai.evaluation_run AS run
      JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
      JOIN ai.task_definition AS task ON task.id = suite.task_definition_id
      JOIN ai.evaluation_dataset_version AS dataset
        ON dataset.id = run.dataset_version_id
      JOIN ai.prompt_version AS prompt
        ON prompt.id = run.prompt_version_id
      JOIN ai.model_route_version AS route
        ON route.id = run.model_route_version_id
      JOIN ai.output_schema_version AS output_schema
        ON output_schema.id = run.output_schema_version_id
      JOIN policy.policy_bundle AS bundle
        ON bundle.id = run.policy_bundle_version_id
      JOIN ai.model_definition AS model
        ON model.id = run.resolved_model_id
     WHERE run.id = NEW.evaluation_run_id
     FOR SHARE OF run, suite, task, dataset, prompt, route,
         output_schema, bundle, model;
    IF run_status IS NULL THEN
        RAISE EXCEPTION 'release decision contains a missing run binding'
            USING ERRCODE = '23503';
    END IF;
    IF run_status <> 'COMPLETED'
       OR suite_status_value <> 'ACTIVE'
       OR task_status_value <> 'ACTIVE'
       OR dataset_status NOT IN ('LOCKED', 'ACTIVE')
       OR prompt_status_value NOT IN ('CERTIFIED', 'ACTIVE')
       OR schema_status_value <> 'ACTIVE'
       OR policy_status_value <> 'ACTIVE'
       OR model_status_value NOT IN ('EVALUATION', 'ACTIVE')
       OR suite_risk <> suite_task_risk
       OR NEW.task_definition_id <> run_task_id
       OR NEW.prompt_version_id <> run_prompt_id
       OR NEW.model_route_version_id <> run_route_id
       OR NEW.output_schema_version_id <> run_schema_id
       OR NEW.policy_bundle_version_id <> run_policy_id
       OR NEW.dataset_version_id <> run_dataset_id
       OR NEW.resolved_model_id <> run_model_id
       OR NEW.code_git_sha <> run_code_sha THEN
        RAISE EXCEPTION 'release decision does not match a complete eligible run'
            USING ERRCODE = '23514';
    END IF;
    IF (
        NEW.status IN ('READY_FOR_REVIEW', 'APPROVED_CANARY')
        AND route_status_value <> 'CERTIFIED'
    ) OR (
        NEW.status = 'APPROVED_ACTIVE'
        AND route_status_value <> 'CANARY'
    ) THEN
        RAISE EXCEPTION
            'release decision route is not eligible for the requested phase'
            USING ERRCODE = '23514';
    END IF;

    SELECT champion.id,
           (
                baseline.status = 'COMPLETED'
                AND baseline.suite_id = run_suite_id
                AND baseline.dataset_version_id = run_dataset_id
                AND champion.prompt_version_id = baseline.prompt_version_id
                AND champion.model_route_version_id =
                    baseline.model_route_version_id
                AND champion.output_schema_version_id =
                    baseline.output_schema_version_id
                AND champion.resolved_model_id = baseline.resolved_model_id
                AND champion.policy_bundle_version_id =
                    baseline.policy_bundle_version_id
                AND champion.code_git_sha = baseline.code_git_sha
           )
      INTO champion_release_id,
           champion_baseline_valid
      FROM ai.release_decision AS champion
      JOIN ai.release_approval AS champion_approval
        ON champion_approval.id = champion.active_approval_id
      LEFT JOIN ai.evaluation_run AS baseline
        ON baseline.id = run_baseline_id
     WHERE champion.task_definition_id = run_task_id
       AND champion.status = 'APPROVED_ACTIVE'
     ORDER BY champion_approval.signed_at DESC, champion.id DESC
     LIMIT 1
     FOR SHARE OF champion, champion_approval;
    IF champion_release_id IS NULL THEN
        IF run_baseline_id IS NOT NULL THEN
            RAISE EXCEPTION
                'bootstrap release cannot bind a baseline when no champion exists'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        IF run_baseline_id IS NULL
           OR champion_baseline_valid IS DISTINCT FROM true THEN
            RAISE EXCEPTION
                'evaluation baseline is not a same-suite/dataset rerun of the current champion'
                USING ERRCODE = '23514';
        END IF;
        PERFORM ai.assert_regression_against_baseline(
            NEW.evaluation_run_id,
            run_baseline_id
        );
    END IF;
    PERFORM ai.assert_evaluation_run_evidence(NEW.evaluation_run_id, true);

    SELECT count(*),
           count(DISTINCT result.judge_calibration_id),
           COALESCE(bool_and(
               result.judge_calibration_id = NEW.judge_calibration_id
           ), true)
      INTO model_judge_count,
           model_judge_calibration_count,
           model_judge_scope_matches
      FROM ai.evaluation_result AS result
     WHERE result.evaluation_run_id = NEW.evaluation_run_id
       AND result.grader_code = 'grader.model_judge.v1';
    IF model_judge_count = 0 AND NEW.judge_calibration_id IS NOT NULL THEN
        RAISE EXCEPTION 'judge calibration must be null when no model judge ran'
            USING ERRCODE = '23514';
    END IF;
    IF model_judge_count > 0 THEN
        SELECT status, expires_at
          INTO calibration_status, calibration_expiry
          FROM ai.judge_calibration
         WHERE id = NEW.judge_calibration_id
         FOR SHARE;
        IF NEW.judge_calibration_id IS NULL
           OR model_judge_calibration_count <> 1
           OR NOT model_judge_scope_matches
           OR calibration_status IS NULL
           OR calibration_status <> 'PASSED'
           OR calibration_expiry <= statement_timestamp() THEN
            RAISE EXCEPTION 'release model judge calibration is missing/stale'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.rollback_strategy = 'DISABLE_ROUTE' THEN
        IF NOT ai.artifact_matches_immutable_hash(
            NEW.rollback_runbook_artifact_id,
            NEW.rollback_runbook_sha256
        ) THEN
            RAISE EXCEPTION 'DISABLE_ROUTE requires immutable rollback runbook'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        SELECT target.status,
               target.task_definition_id,
               target_approval.signed_at,
               target_task.status,
               target_prompt.status,
               target_route.status,
               target_schema.status,
               target_model.status,
               target_policy.status
          INTO target_status,
               target_task_id,
               target_signed_at,
               target_task_status,
               target_prompt_status,
               target_route_status,
               target_schema_status,
               target_model_status,
               target_policy_status
          FROM ai.release_decision AS target
          JOIN ai.release_approval AS target_approval
            ON target_approval.id = target.active_approval_id
          JOIN ai.task_definition AS target_task
            ON target_task.id = target.task_definition_id
          JOIN ai.prompt_version AS target_prompt
            ON target_prompt.id = target.prompt_version_id
          JOIN ai.model_route_version AS target_route
            ON target_route.id = target.model_route_version_id
          JOIN ai.output_schema_version AS target_schema
            ON target_schema.id = target.output_schema_version_id
          JOIN ai.model_definition AS target_model
            ON target_model.id = target.resolved_model_id
          JOIN policy.policy_bundle AS target_policy
            ON target_policy.id = target.policy_bundle_version_id
         WHERE target.id = NEW.rollback_release_decision_id
         FOR SHARE OF target, target_approval, target_task, target_prompt,
             target_route, target_schema, target_model, target_policy;
        IF target_status IS NULL
           OR target_status <> 'APPROVED_ACTIVE'
           OR target_task_id <> NEW.task_definition_id
           OR target_signed_at IS NULL
           OR target_task_status <> 'ACTIVE'
           OR target_prompt_status <> 'ACTIVE'
           OR target_route_status <> 'ACTIVE'
           OR target_schema_status <> 'ACTIVE'
           OR target_model_status <> 'ACTIVE'
           OR target_policy_status <> 'ACTIVE'
           OR champion_release_id IS DISTINCT FROM
                NEW.rollback_release_decision_id THEN
            RAISE EXCEPTION
                'rollback target is not a prior safe same-task active release'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.status = 'READY_FOR_REVIEW' THEN
        IF NEW.canary_approval_id IS NOT NULL
           OR NEW.active_approval_id IS NOT NULL
           OR NEW.approved_by_principal_id IS NOT NULL
           OR NEW.second_approver_principal_id IS NOT NULL
           OR NEW.approved_at IS NOT NULL
           OR NEW.canary_evidence_artifact_id IS NOT NULL THEN
            RAISE EXCEPTION 'review-ready release cannot contain approval/evidence'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.status = 'APPROVED_CANARY' THEN
        SELECT approval.release_decision_id,
               approval.phase,
               approval.decision_manifest_sha256,
               approval.primary_approver_principal_id,
               approval.second_approver_principal_id,
               approval.signed_at
          INTO approval_release_id,
               approval_phase,
               approval_manifest,
               approval_primary_id,
               approval_second_id,
               approval_signed_at
          FROM ai.release_approval AS approval
         WHERE approval.id = NEW.canary_approval_id
         FOR SHARE;
        route_canary_cap :=
            (route_config_value ->> 'canary_max_percent')::integer;
        IF approval_release_id IS NULL
           OR approval_release_id <> NEW.id
           OR approval_phase <> 'CANARY'
           OR approval_manifest <> NEW.decision_manifest_sha256
           OR approval_primary_id <> NEW.approved_by_principal_id
           OR approval_second_id <> NEW.second_approver_principal_id
           OR approval_signed_at <> NEW.approved_at
           OR approval_signed_at < run_completed_at
           OR (
                NEW.rollback_strategy = 'PREVIOUS_RELEASE'
                AND target_signed_at >= approval_signed_at
           )
           OR NEW.release_scope <> 'CANARY'
           OR NEW.maximum_canary_percent < 1
           OR NEW.maximum_canary_percent > route_canary_cap
           OR (
                suite_risk = 'CRITICAL'
                AND NEW.maximum_canary_percent > 1
           )
           OR EXISTS (
                SELECT 1
                  FROM ai.release_decision AS other_canary
                 WHERE other_canary.task_definition_id =
                        NEW.task_definition_id
                   AND other_canary.id <> NEW.id
                   AND other_canary.status = 'APPROVED_CANARY'
           )
           OR NEW.active_approval_id IS NOT NULL
           OR NEW.canary_evidence_artifact_id IS NOT NULL
           OR NEW.canary_monitoring_artifact_id IS NULL
           OR NEW.canary_monitoring_sha256 IS NULL
           OR NOT ai.artifact_matches_immutable_hash(
                NEW.canary_monitoring_artifact_id,
                NEW.canary_monitoring_sha256
           ) THEN
            RAISE EXCEPTION 'canary approval bundle/cap/monitoring is invalid'
                USING ERRCODE = '23514';
        END IF;
        NEW.canary_started_at := statement_timestamp();
        NEW.canary_started_txid := txid_current();
        NEW.canary_completed_at := NULL;
        NEW.canary_completed_txid := NULL;
        RETURN NEW;
    END IF;

    SELECT approval.release_decision_id,
           approval.phase,
           approval.decision_manifest_sha256,
           approval.primary_approver_principal_id,
           approval.second_approver_principal_id,
           approval.signed_at
      INTO approval_release_id,
           approval_phase,
           approval_manifest,
           approval_primary_id,
           approval_second_id,
           approval_signed_at
      FROM ai.release_approval AS approval
     WHERE approval.id = NEW.active_approval_id
     FOR SHARE;
    IF approval_release_id IS NULL
       OR approval_release_id <> NEW.id
       OR approval_phase <> 'ACTIVE'
       OR approval_manifest <> NEW.decision_manifest_sha256
       OR approval_manifest = OLD.decision_manifest_sha256
       OR approval_primary_id <> NEW.approved_by_principal_id
       OR approval_second_id <> NEW.second_approver_principal_id
       OR approval_signed_at <> NEW.approved_at
       OR approval_signed_at < NEW.canary_completed_at
       OR NEW.release_scope <> 'ACTIVE'
       OR NEW.maximum_canary_percent <> 0
       OR NEW.canary_approval_id IS DISTINCT FROM OLD.canary_approval_id
       OR NEW.canary_evidence_artifact_id IS NULL
       OR NEW.canary_evidence_sha256 IS NULL
       OR NEW.canary_completed_at IS NULL
       OR NEW.canary_completed_txid IS NULL
       OR NEW.canary_started_txid = txid_current()
       OR NEW.canary_completed_txid = txid_current()
       OR NOT ai.artifact_matches_immutable_hash(
            NEW.canary_evidence_artifact_id,
            NEW.canary_evidence_sha256
       ) THEN
        RAISE EXCEPTION 'active approval lacks new signatures/canary evidence'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_release_decision_mutation(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_release_decision_mutation"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
DECLARE
    run_status text;
    run_task_definition_id uuid;
    run_prompt_version_id uuid;
    run_route_version_id uuid;
    run_schema_version_id uuid;
    run_policy_version_id uuid;
    run_dataset_version_id uuid;
    run_code_git_sha text;
    run_resolved_model_id uuid;
    route_primary_model_id uuid;
    route_fallback_model_id uuid;
    task_risk_level text;
    zero_tolerance_failures bigint;
    nonpassing_result_count bigint;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'release decision must be created in DRAFT'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'non-draft release decision % is immutable', OLD.id
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;
    IF ROW(
        NEW.id,
        NEW.display_id,
        NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.id,
        OLD.display_id,
        OLD.created_at
    ) THEN
        RAISE EXCEPTION 'release decision identity is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.status <> 'DRAFT'
       AND ROW(
           NEW.task_definition_id,
           NEW.prompt_version_id,
           NEW.model_route_version_id,
           NEW.output_schema_version_id,
           NEW.resolved_model_id,
           NEW.policy_bundle_version_id,
           NEW.dataset_version_id,
           NEW.evaluation_run_id,
           NEW.code_git_sha,
           NEW.rollback_release_decision_id
       ) IS DISTINCT FROM ROW(
           OLD.task_definition_id,
           OLD.prompt_version_id,
           OLD.model_route_version_id,
           OLD.output_schema_version_id,
           OLD.resolved_model_id,
           OLD.policy_bundle_version_id,
           OLD.dataset_version_id,
           OLD.evaluation_run_id,
           OLD.code_git_sha,
           OLD.rollback_release_decision_id
       ) THEN
        RAISE EXCEPTION 'release decision version bindings are frozen after DRAFT'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.status <> 'DRAFT'
       AND NOT (
           OLD.status = 'APPROVED_CANARY'
           AND NEW.status = 'APPROVED_ACTIVE'
       )
       AND ROW(
           NEW.release_scope,
           NEW.maximum_canary_percent,
           NEW.decision_manifest_sha256
       ) IS DISTINCT FROM ROW(
           OLD.release_scope,
           OLD.maximum_canary_percent,
           OLD.decision_manifest_sha256
       ) THEN
        RAISE EXCEPTION
            'release lifecycle rollout scope/manifest are frozen for this transition'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.status IN ('APPROVED_CANARY', 'APPROVED_ACTIVE')
       AND NOT (
           OLD.status = 'APPROVED_CANARY'
           AND NEW.status = 'APPROVED_ACTIVE'
       ) THEN
        IF NEW.approved_by_principal_id IS DISTINCT
               FROM OLD.approved_by_principal_id
           OR (
               OLD.second_approver_principal_id IS NOT NULL
               AND NEW.second_approver_principal_id IS DISTINCT
                   FROM OLD.second_approver_principal_id
           )
           OR NEW.approved_at < OLD.approved_at THEN
            RAISE EXCEPTION 'approved release decision evidence cannot be replaced'
                USING ERRCODE = '55000';
        END IF;
        IF ROW(
               NEW.second_approver_principal_id,
               NEW.approved_at
           ) IS DISTINCT FROM ROW(
               OLD.second_approver_principal_id,
               OLD.approved_at
           ) THEN
            RAISE EXCEPTION
                'additional approval evidence is allowed only for canary to active'
                USING ERRCODE = '55000';
        END IF;
    END IF;
    IF OLD.status IN ('REJECTED', 'REVOKED') THEN
        RAISE EXCEPTION 'terminal release decision % is immutable', OLD.id
            USING ERRCODE = '55000';
    END IF;
    IF (OLD.status = 'DRAFT'
            AND NEW.status NOT IN (
                'DRAFT', 'READY_FOR_REVIEW', 'REJECTED'
            ))
       OR (OLD.status = 'READY_FOR_REVIEW'
            AND NEW.status NOT IN (
                'READY_FOR_REVIEW', 'APPROVED_CANARY', 'REJECTED'
            ))
       OR (OLD.status = 'APPROVED_CANARY'
            AND NEW.status NOT IN (
                'APPROVED_CANARY', 'APPROVED_ACTIVE', 'REVOKED'
            ))
       OR (OLD.status = 'APPROVED_ACTIVE'
            AND NEW.status NOT IN ('APPROVED_ACTIVE', 'REVOKED')) THEN
        RAISE EXCEPTION
            'release decision lifecycle cannot move from % to %',
            OLD.status,
            NEW.status
            USING ERRCODE = '23514';
    END IF;
    IF OLD.status <> NEW.status
       AND NEW.status IN ('APPROVED_CANARY', 'APPROVED_ACTIVE') THEN
        SELECT run.status,
               suite.task_definition_id,
               run.prompt_version_id,
               run.model_route_version_id,
               run.output_schema_version_id,
               run.policy_bundle_version_id,
               run.dataset_version_id,
               run.code_git_sha,
               run.resolved_model_id,
               route.primary_model_id,
               route.fallback_model_id,
               task.risk_level
          INTO run_status,
               run_task_definition_id,
               run_prompt_version_id,
               run_route_version_id,
               run_schema_version_id,
               run_policy_version_id,
               run_dataset_version_id,
               run_code_git_sha,
               run_resolved_model_id,
               route_primary_model_id,
               route_fallback_model_id,
               task_risk_level
          FROM ai.evaluation_run AS run
          JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
          JOIN ai.model_route_version AS route
            ON route.id = run.model_route_version_id
          JOIN ai.task_definition AS task
            ON task.id = suite.task_definition_id
         WHERE run.id = NEW.evaluation_run_id
         FOR SHARE OF run, suite, route, task;

        IF run_status IS NULL THEN
            RAISE EXCEPTION
                'release decision evaluation run % does not exist',
                NEW.evaluation_run_id
                USING ERRCODE = '23503';
        END IF;
        IF run_status <> 'COMPLETED' THEN
            RAISE EXCEPTION
                'release approval requires COMPLETED evaluation run; got %',
                run_status
                USING ERRCODE = '23514';
        END IF;
        IF NEW.task_definition_id <> run_task_definition_id
           OR NEW.prompt_version_id <> run_prompt_version_id
           OR NEW.model_route_version_id <> run_route_version_id
           OR NEW.output_schema_version_id <> run_schema_version_id
           OR NEW.policy_bundle_version_id IS DISTINCT
               FROM run_policy_version_id
           OR NEW.dataset_version_id <> run_dataset_version_id
           OR NEW.code_git_sha <> run_code_git_sha
           OR NEW.resolved_model_id <> run_resolved_model_id THEN
            RAISE EXCEPTION
                'release decision bindings do not match evaluation run/route'
                USING ERRCODE = '23514';
        END IF;
        SELECT COALESCE(sum(zero_tolerance_failure_count), 0),
               count(*) FILTER (WHERE status <> 'PASSED')
          INTO zero_tolerance_failures, nonpassing_result_count
          FROM ai.evaluation_case_result
         WHERE evaluation_run_id = NEW.evaluation_run_id;
        IF zero_tolerance_failures <> 0 THEN
            RAISE EXCEPTION
                'release approval blocked by % zero-tolerance failures',
                zero_tolerance_failures
                USING ERRCODE = '23514';
        END IF;
        IF nonpassing_result_count <> 0 THEN
            RAISE EXCEPTION
                'release approval blocked by % non-passing case results',
                nonpassing_result_count
                USING ERRCODE = '23514';
        END IF;
        IF NOT EXISTS (
            SELECT 1
              FROM iam.principal
             WHERE id = NEW.approved_by_principal_id
               AND principal_type = 'USER'
               AND status = 'ACTIVE'
        ) OR (
            NEW.second_approver_principal_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1
                  FROM iam.principal
                 WHERE id = NEW.second_approver_principal_id
                   AND principal_type = 'USER'
                   AND status = 'ACTIVE'
            )
        ) THEN
            RAISE EXCEPTION
                'release approval requires ACTIVE USER approver principals'
                USING ERRCODE = '23514';
        END IF;
        IF task_risk_level = 'CRITICAL'
           AND (
               NEW.second_approver_principal_id IS NULL
               OR NEW.second_approver_principal_id
                   = NEW.approved_by_principal_id
           ) THEN
            RAISE EXCEPTION
                'CRITICAL release approval requires two distinct approvers'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.status = 'APPROVED_CANARY'
           AND (
               NEW.release_scope <> 'CANARY'
               OR NEW.maximum_canary_percent NOT BETWEEN 1 AND 100
           ) THEN
            RAISE EXCEPTION
                'canary approval requires CANARY scope and a positive cap'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.status = 'APPROVED_ACTIVE'
           AND (
               OLD.status <> 'APPROVED_CANARY'
               OR NEW.release_scope <> 'ACTIVE'
               OR NEW.maximum_canary_percent <> 0
               OR NEW.decision_manifest_sha256
                   = OLD.decision_manifest_sha256
           ) THEN
            RAISE EXCEPTION
                'active approval requires prior canary and new active manifest'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    IF OLD.status <> 'REVOKED' AND NEW.status = 'REVOKED' THEN
        PERFORM 1
          FROM ai.release_decision AS dependent
         WHERE dependent.rollback_strategy = 'PREVIOUS_RELEASE'
           AND dependent.rollback_release_decision_id = OLD.id
           AND dependent.status IN (
                'READY_FOR_REVIEW',
                'APPROVED_CANARY',
                'APPROVED_ACTIVE'
           )
         FOR SHARE;
        IF FOUND THEN
            RAISE EXCEPTION
                'release remains the frozen rollback target of a live decision; revoke the dependent or select DISABLE_ROUTE first'
                USING ERRCODE = '23514';
        END IF;
        IF NOT EXISTS (
            SELECT 1
              FROM iam.principal
             WHERE id = NEW.revoked_by_principal_id
               AND principal_type = 'USER'
               AND status = 'ACTIVE'
        ) THEN
            RAISE EXCEPTION
                'release revocation requires an ACTIVE USER principal'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_release_task_serialization(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_release_task_serialization"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.status <> NEW.status
       AND NEW.status IN (
            'READY_FOR_REVIEW',
            'APPROVED_CANARY',
            'APPROVED_ACTIVE',
            'REVOKED'
       )
       AND NOT pg_try_advisory_xact_lock(
            72004,
            hashtext(NEW.task_definition_id::text)
       ) THEN
        RAISE EXCEPTION
            'concurrent release transition for task %; retry',
            NEW.task_definition_id
            USING ERRCODE = '40001';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_task_definition_lifecycle(); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."guard_task_definition_lifecycle"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'PAUSED' THEN
            RAISE EXCEPTION 'task definition must be created PAUSED'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'task definitions are not deletable'
            USING ERRCODE = '55000';
    END IF;
    IF ROW(NEW.id, NEW.task_code, NEW.created_at) IS DISTINCT FROM
       ROW(OLD.id, OLD.task_code, OLD.created_at) THEN
        RAISE EXCEPTION 'task identity is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF ROW(
        NEW.name,
        NEW.description,
        NEW.risk_level,
        NEW.output_schema_code,
        NEW.default_max_tokens,
        NEW.default_max_cost_jpy,
        NEW.human_review_required
    ) IS DISTINCT FROM ROW(
        OLD.name,
        OLD.description,
        OLD.risk_level,
        OLD.output_schema_code,
        OLD.default_max_tokens,
        OLD.default_max_cost_jpy,
        OLD.human_review_required
    ) AND (
        OLD.status <> 'PAUSED'
        OR EXISTS (
            SELECT 1 FROM ai.evaluation_suite
             WHERE task_definition_id = OLD.id
        )
        OR EXISTS (
            SELECT 1 FROM ai.release_decision
             WHERE task_definition_id = OLD.id
        )
    ) THEN
        RAISE EXCEPTION 'referenced/non-paused task definition is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.status = 'RETIRED' AND NEW.status <> 'RETIRED'
       OR OLD.status = 'ACTIVE' AND NEW.status NOT IN (
            'ACTIVE', 'PAUSED', 'RETIRED'
       )
       OR OLD.status = 'PAUSED' AND NEW.status NOT IN (
            'PAUSED', 'ACTIVE', 'RETIRED'
       ) THEN
        RAISE EXCEPTION 'task lifecycle cannot move from % to %',
            OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    IF OLD.status <> 'ACTIVE' AND NEW.status = 'ACTIVE'
       AND (
            ai.canonical_suite_risk(NEW.task_code) IS NULL
            OR NEW.risk_level <>
                ai.canonical_suite_risk(NEW.task_code)
       ) THEN
        RAISE EXCEPTION 'task does not match the frozen task catalog'
            USING ERRCODE = '23514';
    END IF;
    IF OLD.status = 'ACTIVE'
       AND NEW.status <> 'ACTIVE'
       AND ai.has_live_rollback_dependents('TASK', OLD.id) THEN
        RAISE EXCEPTION 'task % is a live rollback component', OLD.id
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: has_live_rollback_dependents("text", "uuid"); Type: FUNCTION; Schema: ai; Owner: -
--

CREATE FUNCTION "ai"."has_live_rollback_dependents"("p_component" "text", "p_component_id" "uuid") RETURNS boolean
    LANGUAGE "sql" STABLE STRICT
    SET "search_path" TO 'pg_catalog', 'ai'
    AS $$
    SELECT EXISTS (
        SELECT 1
          FROM ai.release_decision AS dependent
          JOIN ai.release_decision AS target
            ON target.id = dependent.rollback_release_decision_id
         WHERE dependent.rollback_strategy = 'PREVIOUS_RELEASE'
           AND dependent.status IN (
                'READY_FOR_REVIEW',
                'APPROVED_CANARY',
                'APPROVED_ACTIVE'
           )
           AND CASE p_component
                WHEN 'TASK' THEN target.task_definition_id = p_component_id
                WHEN 'PROMPT' THEN target.prompt_version_id = p_component_id
                WHEN 'ROUTE' THEN
                    target.model_route_version_id = p_component_id
                WHEN 'SCHEMA' THEN
                    target.output_schema_version_id = p_component_id
                WHEN 'MODEL' THEN target.resolved_model_id = p_component_id
                WHEN 'POLICY' THEN
                    target.policy_bundle_version_id = p_component_id
                ELSE false
           END
    )
$$;

--
-- Name: content_artifact_matches_immutable_hash("uuid", "text"); Type: FUNCTION; Schema: editorial; Owner: -
--

CREATE FUNCTION "editorial"."content_artifact_matches_immutable_hash"("p_artifact_id" "uuid", "p_sha256" "text") RETURNS boolean
    LANGUAGE "sql" STABLE STRICT
    SET "search_path" TO 'pg_catalog', 'ops'
    AS $$
    SELECT EXISTS (
        SELECT 1
          FROM ops.object_artifact
         WHERE id = p_artifact_id
           AND is_immutable
           AND sha256 = p_sha256
    )
$$;

--
-- Name: guard_article_content_bindings(); Type: FUNCTION; Schema: editorial; Owner: -
--

CREATE FUNCTION "editorial"."guard_article_content_bindings"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'editorial'
    AS $$
DECLARE
    schema_status text;
    type_status text;
    template_status text;
    template_type_id uuid;
    seo_status text;
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.status IN ('APPROVED', 'SUPERSEDED')
       AND (
            NEW.content_schema_version_id IS DISTINCT FROM
                OLD.content_schema_version_id
            OR NEW.article_type_version_id IS DISTINCT FROM
                OLD.article_type_version_id
            OR NEW.article_template_version_id IS DISTINCT FROM
                OLD.article_template_version_id
            OR NEW.seo_metadata_version_id IS DISTINCT FROM
                OLD.seo_metadata_version_id
       ) THEN
        RAISE EXCEPTION 'approved article content bindings are immutable'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.content_schema_version_id IS NOT NULL THEN
        SELECT status INTO schema_status
          FROM editorial.content_schema_version
         WHERE id = NEW.content_schema_version_id;
    END IF;
    IF NEW.article_type_version_id IS NOT NULL THEN
        SELECT status INTO type_status
          FROM editorial.article_type_version
         WHERE id = NEW.article_type_version_id;
    END IF;
    IF NEW.article_template_version_id IS NOT NULL THEN
        SELECT status, article_type_version_id
          INTO template_status, template_type_id
          FROM editorial.article_template_version
         WHERE id = NEW.article_template_version_id;
    END IF;
    IF NEW.article_type_version_id IS NOT NULL
       AND NEW.article_template_version_id IS NOT NULL
       AND template_type_id IS DISTINCT FROM NEW.article_type_version_id THEN
        RAISE EXCEPTION
            'Article Template Version must belong to the bound Article Type Version'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.seo_metadata_version_id IS NOT NULL THEN
        SELECT status INTO seo_status
          FROM editorial.seo_metadata_version
         WHERE id = NEW.seo_metadata_version_id
           AND article_version_id = NEW.id;
    END IF;

    IF NEW.status = 'APPROVED'
       AND (
            NEW.content_schema_version_id IS NULL
            OR NEW.article_type_version_id IS NULL
            OR NEW.article_template_version_id IS NULL
            OR NEW.seo_metadata_version_id IS NULL
            OR schema_status IS DISTINCT FROM 'ACTIVE'
            OR type_status IS DISTINCT FROM 'ACTIVE'
            OR template_status IS DISTINCT FROM 'ACTIVE'
            OR seo_status IS DISTINCT FROM 'APPROVED'
            OR NOT EXISTS (
                SELECT 1
                  FROM editorial.article_methodology_binding AS binding
                  JOIN editorial.editorial_methodology_version AS methodology
                    ON methodology.id = binding.methodology_version_id
                 WHERE binding.article_version_id = NEW.id
                   AND methodology.status = 'ACTIVE'
                   AND methodology.article_type_version_id =
                        NEW.article_type_version_id
            )
       ) THEN
        RAISE EXCEPTION
            'article approval requires ACTIVE schema/type/template/methodology and APPROVED SEO bindings'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_article_methodology_binding(); Type: FUNCTION; Schema: editorial; Owner: -
--

CREATE FUNCTION "editorial"."guard_article_methodology_binding"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'editorial'
    AS $$
DECLARE
    article_type_id uuid;
    methodology_type_id uuid;
    methodology_status text;
BEGIN
    IF NOT editorial.is_active_human_principal(
            NEW.bound_by_principal_id
       ) THEN
        RAISE EXCEPTION 'methodology binding actor must be an ACTIVE USER'
            USING ERRCODE = '23514';
    END IF;
    SELECT article_type_version_id
      INTO article_type_id
      FROM editorial.article_version
     WHERE id = NEW.article_version_id;
    SELECT article_type_version_id, status
      INTO methodology_type_id, methodology_status
      FROM editorial.editorial_methodology_version
     WHERE id = NEW.methodology_version_id;
    IF article_type_id IS NULL
       OR methodology_type_id IS DISTINCT FROM article_type_id
       OR methodology_status <> 'ACTIVE' THEN
        RAISE EXCEPTION
            'article methodology must bind the article ACTIVE Article Type Version'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_content_artifact_binding(); Type: FUNCTION; Schema: editorial; Owner: -
--

CREATE FUNCTION "editorial"."guard_content_artifact_binding"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'editorial'
    AS $$
DECLARE
    artifact_id_value uuid;
    hash_value text;
BEGIN
    CASE TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
        WHEN 'editorial.content_schema_version' THEN
            artifact_id_value := NEW.artifact_id;
            hash_value := NEW.schema_sha256;
        WHEN 'editorial.article_methodology_binding' THEN
            artifact_id_value := NEW.candidate_universe_artifact_id;
            hash_value := NEW.candidate_universe_sha256;
        WHEN 'editorial.structured_data_manifest' THEN
            artifact_id_value := NEW.jsonld_artifact_id;
            hash_value := NEW.jsonld_sha256;
        WHEN 'editorial.media_asset' THEN
            artifact_id_value := NEW.raw_artifact_id;
            hash_value := NEW.asset_sha256;
            IF NEW.long_description_artifact_id IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1
                      FROM ops.object_artifact
                     WHERE id = NEW.long_description_artifact_id
                       AND is_immutable
               ) THEN
                RAISE EXCEPTION
                    'media long description requires an immutable artifact'
                    USING ERRCODE = '23514';
            END IF;
        WHEN 'evidence.first_hand_experience_asset' THEN
            artifact_id_value := NEW.artifact_id;
            hash_value := NEW.artifact_sha256;
        ELSE
            RAISE EXCEPTION 'unsupported content artifact trigger target %',
                TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME;
    END CASE;

    IF artifact_id_value IS NOT NULL
       AND NOT editorial.content_artifact_matches_immutable_hash(
            artifact_id_value,
            hash_value
       ) THEN
        RAISE EXCEPTION
            '% requires an immutable exact-hash artifact',
            TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_disclosure_context_mutation(); Type: FUNCTION; Schema: editorial; Owner: -
--

CREATE FUNCTION "editorial"."guard_disclosure_context_mutation"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'editorial'
    AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.reviewed_at IS NOT NULL THEN
            RAISE EXCEPTION 'reviewed disclosure context is immutable'
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE'
       AND OLD.reviewed_at IS NOT NULL
       AND to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
        RAISE EXCEPTION 'reviewed disclosure context is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.reviewed_by_principal_id IS NOT NULL
       AND NOT editorial.is_active_human_principal(
            NEW.reviewed_by_principal_id
       ) THEN
        RAISE EXCEPTION 'disclosure review requires an ACTIVE USER principal'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_media_asset_mutation(); Type: FUNCTION; Schema: editorial; Owner: -
--

CREATE FUNCTION "editorial"."guard_media_asset_mutation"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'editorial'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT'
           OR NEW.approved_by_principal_id IS NOT NULL
           OR NEW.approved_at IS NOT NULL THEN
            RAISE EXCEPTION 'media asset must be created in unapproved DRAFT'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'reviewed media asset is immutable'
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;
    IF NOT (
        NEW.status = OLD.status
        OR (OLD.status = 'DRAFT'
            AND NEW.status IN ('APPROVED', 'BLOCKED', 'RETIRED'))
        OR (OLD.status = 'APPROVED'
            AND NEW.status IN ('BLOCKED', 'RETIRED'))
        OR (OLD.status = 'BLOCKED' AND NEW.status = 'RETIRED')
    ) THEN
        RAISE EXCEPTION 'invalid media lifecycle transition % -> %',
            OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    IF OLD.status <> 'DRAFT'
       AND to_jsonb(OLD) - 'status'
           IS DISTINCT FROM to_jsonb(NEW) - 'status' THEN
        RAISE EXCEPTION 'reviewed media asset payload is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.status = 'APPROVED'
       AND NOT editorial.is_active_human_principal(
            NEW.approved_by_principal_id
       ) THEN
        RAISE EXCEPTION 'media approval requires an ACTIVE USER principal'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_seo_metadata_mutation(); Type: FUNCTION; Schema: editorial; Owner: -
--

CREATE FUNCTION "editorial"."guard_seo_metadata_mutation"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'editorial'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT'
           OR NEW.validated_at IS NOT NULL
           OR NEW.approved_by_principal_id IS NOT NULL
           OR NEW.approved_at IS NOT NULL THEN
            RAISE EXCEPTION 'SEO metadata must be created in unvalidated DRAFT'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'validated SEO metadata is immutable'
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;
    IF NOT (
        NEW.status = OLD.status
        OR (OLD.status = 'DRAFT'
            AND NEW.status IN ('VALIDATED', 'REJECTED'))
        OR (OLD.status = 'VALIDATED'
            AND NEW.status IN ('APPROVED', 'REJECTED'))
    ) THEN
        RAISE EXCEPTION 'invalid SEO lifecycle transition % -> %',
            OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    IF OLD.status = 'VALIDATED' AND NEW.status = 'APPROVED' THEN
        IF to_jsonb(OLD)
               - ARRAY['status', 'approved_by_principal_id', 'approved_at']
           IS DISTINCT FROM
           to_jsonb(NEW)
               - ARRAY['status', 'approved_by_principal_id', 'approved_at'] THEN
            RAISE EXCEPTION 'validated SEO metadata payload is immutable'
                USING ERRCODE = '55000';
        END IF;
    ELSIF OLD.status <> 'DRAFT'
       AND to_jsonb(OLD) - 'status'
           IS DISTINCT FROM to_jsonb(NEW) - 'status' THEN
        RAISE EXCEPTION 'validated SEO metadata payload is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.status <> 'DRAFT' AND NEW.validated_at IS NULL THEN
        RAISE EXCEPTION 'validated SEO metadata requires validated_at'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.status <> 'APPROVED'
       AND (NEW.approved_by_principal_id IS NOT NULL
            OR NEW.approved_at IS NOT NULL) THEN
        RAISE EXCEPTION 'only APPROVED SEO metadata may carry approval evidence'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.status = 'APPROVED'
       AND NOT editorial.is_active_human_principal(
            NEW.approved_by_principal_id
       ) THEN
        RAISE EXCEPTION 'SEO approval requires an ACTIVE USER principal'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_versioned_content_mutation(); Type: FUNCTION; Schema: editorial; Owner: -
--

CREATE FUNCTION "editorial"."guard_versioned_content_mutation"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'editorial'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT'
           OR NEW.approved_by_principal_id IS NOT NULL
           OR NEW.approved_at IS NOT NULL THEN
            RAISE EXCEPTION '% must be created in unapproved DRAFT', TG_TABLE_NAME
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'DRAFT' THEN
            RAISE EXCEPTION '% non-DRAFT versions are immutable', TG_TABLE_NAME
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;

    IF NOT (
        NEW.status = OLD.status
        OR (OLD.status = 'DRAFT' AND NEW.status IN ('ACTIVE', 'RETIRED'))
        OR (OLD.status = 'ACTIVE' AND NEW.status IN ('DEPRECATED', 'RETIRED'))
        OR (OLD.status = 'DEPRECATED' AND NEW.status = 'RETIRED')
    ) THEN
        RAISE EXCEPTION 'invalid % lifecycle transition % -> %',
            TG_TABLE_NAME, OLD.status, NEW.status
            USING ERRCODE = '23514';
    END IF;

    IF OLD.status <> 'DRAFT'
       AND (to_jsonb(OLD) - ARRAY['status', 'effective_to'])
           IS DISTINCT FROM
           (to_jsonb(NEW) - ARRAY['status', 'effective_to']) THEN
        RAISE EXCEPTION '% activated payload and approval history are immutable',
            TG_TABLE_NAME USING ERRCODE = '55000';
    END IF;

    IF NEW.status = 'DRAFT'
       AND (NEW.approved_by_principal_id IS NOT NULL
            OR NEW.approved_at IS NOT NULL) THEN
        RAISE EXCEPTION 'DRAFT % cannot carry approval evidence', TG_TABLE_NAME
            USING ERRCODE = '23514';
    END IF;

    IF NEW.status = 'ACTIVE'
       AND NOT editorial.is_active_human_principal(
            NEW.approved_by_principal_id
       ) THEN
        RAISE EXCEPTION '% activation requires an ACTIVE USER principal',
            TG_TABLE_NAME USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: is_active_human_principal("uuid"); Type: FUNCTION; Schema: editorial; Owner: -
--

CREATE FUNCTION "editorial"."is_active_human_principal"("p_principal_id" "uuid") RETURNS boolean
    LANGUAGE "sql" STABLE STRICT
    SET "search_path" TO 'pg_catalog', 'iam'
    AS $$
    SELECT EXISTS (
        SELECT 1
          FROM iam.principal
         WHERE id = p_principal_id
           AND principal_type = 'USER'
           AND status = 'ACTIVE'
    )
$$;

--
-- Name: guard_first_hand_experience_mutation(); Type: FUNCTION; Schema: evidence; Owner: -
--

CREATE FUNCTION "evidence"."guard_first_hand_experience_mutation"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'evidence', 'editorial'
    AS $$
BEGIN
    IF TG_OP IN ('INSERT', 'UPDATE')
       AND NOT editorial.is_active_human_principal(
            NEW.tester_principal_id
       ) THEN
        RAISE EXCEPTION 'first-hand experience tester must be an ACTIVE USER'
            USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.review_status <> 'DRAFT'
           OR NEW.reviewed_by_principal_id IS NOT NULL
           OR NEW.reviewed_at IS NOT NULL THEN
            RAISE EXCEPTION 'experience record must be created in DRAFT'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.review_status <> 'DRAFT' THEN
            RAISE EXCEPTION 'reviewed experience record is immutable'
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;
    IF NOT (
        NEW.review_status = OLD.review_status
        OR (OLD.review_status = 'DRAFT'
            AND NEW.review_status IN ('REVIEWED', 'REJECTED'))
        OR (OLD.review_status = 'REVIEWED'
            AND NEW.review_status IN ('APPROVED', 'REJECTED'))
    ) THEN
        RAISE EXCEPTION 'invalid experience lifecycle transition % -> %',
            OLD.review_status, NEW.review_status USING ERRCODE = '23514';
    END IF;
    IF OLD.review_status <> 'DRAFT'
       AND to_jsonb(OLD) - 'review_status'
           IS DISTINCT FROM to_jsonb(NEW) - 'review_status' THEN
        RAISE EXCEPTION 'reviewed experience payload is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.review_status <> 'DRAFT'
       AND NOT editorial.is_active_human_principal(
            NEW.reviewed_by_principal_id
       ) THEN
        RAISE EXCEPTION 'experience review requires an ACTIVE USER principal'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.review_status IN ('REVIEWED', 'APPROVED')
       AND NEW.reviewed_by_principal_id = NEW.tester_principal_id THEN
        RAISE EXCEPTION 'experience reviewer must differ from tester'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_bundle_rule_append_only(); Type: FUNCTION; Schema: policy; Owner: -
--

CREATE FUNCTION "policy"."guard_bundle_rule_append_only"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'policy'
    AS $$
DECLARE
    bundle_status text;
    rule_status text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'policy bundle rule bindings are append-only'
            USING ERRCODE = '55000';
    END IF;

    SELECT bundle.status
      INTO bundle_status
      FROM policy.policy_bundle AS bundle
     WHERE bundle.id = NEW.policy_bundle_id
     FOR SHARE;
    IF bundle_status IS NULL THEN
        RAISE EXCEPTION 'policy bundle rule references a missing bundle'
            USING ERRCODE = '23503';
    END IF;
    IF bundle_status <> 'DRAFT' THEN
        RAISE EXCEPTION
            'policy bundle rules require a DRAFT bundle'
            USING ERRCODE = '23514';
    END IF;

    PERFORM pg_advisory_xact_lock(72003, hashtext(NEW.rule_version_id::text));
    SELECT rule.status
      INTO rule_status
      FROM policy.rule_version AS rule
     WHERE rule.id = NEW.rule_version_id;
    IF rule_status IS NULL THEN
        RAISE EXCEPTION 'policy bundle rule references a missing rule version'
            USING ERRCODE = '23503';
    END IF;
    IF rule_status <> 'ACTIVE' THEN
        RAISE EXCEPTION 'policy bundle rules require an ACTIVE rule version'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_policy_bundle_lifecycle(); Type: FUNCTION; Schema: policy; Owner: -
--

CREATE FUNCTION "policy"."guard_policy_bundle_lifecycle"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'policy'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'policy bundle must be created in DRAFT'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'policy bundle versions are not deletable'
            USING ERRCODE = '55000';
    END IF;
    IF ROW(
        NEW.id,
        NEW.display_id,
        NEW.bundle_code,
        NEW.version_no,
        NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.id,
        OLD.display_id,
        OLD.bundle_code,
        OLD.version_no,
        OLD.created_at
    ) THEN
        RAISE EXCEPTION 'policy bundle identity is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.status <> 'DRAFT' AND ROW(
        NEW.git_commit_sha, NEW.bundle_sha256
    ) IS DISTINCT FROM ROW(
        OLD.git_commit_sha, OLD.bundle_sha256
    ) THEN
        RAISE EXCEPTION 'approved policy bundle hashes are immutable'
            USING ERRCODE = '55000';
    END IF;
    IF (OLD.status = 'DRAFT' AND NEW.status NOT IN (
            'DRAFT', 'ACTIVE', 'REJECTED', 'RETIRED'
       ))
       OR (OLD.status = 'ACTIVE' AND NEW.status NOT IN (
            'ACTIVE', 'RETIRED'
       ))
       OR (OLD.status IN ('REJECTED', 'RETIRED')
            AND NEW.status <> OLD.status) THEN
        RAISE EXCEPTION 'policy bundle lifecycle cannot move from % to %',
            OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    IF OLD.status <> 'ACTIVE' AND NEW.status = 'ACTIVE'
       AND NOT EXISTS (
            SELECT 1 FROM iam.principal
             WHERE id = NEW.approved_by_principal_id
               AND principal_type = 'USER'
               AND status = 'ACTIVE'
       ) THEN
        RAISE EXCEPTION 'policy activation requires an ACTIVE USER approver'
            USING ERRCODE = '23514';
    END IF;
    IF OLD.status = 'ACTIVE'
       AND NEW.status <> 'ACTIVE'
       AND ai.has_live_rollback_dependents('POLICY', OLD.id) THEN
        RAISE EXCEPTION 'policy bundle % is a live rollback component', OLD.id
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

--
-- Name: guard_rule_version_immutability(); Type: FUNCTION; Schema: policy; Owner: -
--

CREATE FUNCTION "policy"."guard_rule_version_immutability"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'policy'
    AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'policy rule versions are not deletable'
            USING ERRCODE = '55000';
    END IF;
    PERFORM pg_advisory_xact_lock(72003, hashtext(OLD.id::text));
    IF ROW(
        NEW.id,
        NEW.rule_code,
        NEW.version_no,
        NEW.created_by_principal_id,
        NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.id,
        OLD.rule_code,
        OLD.version_no,
        OLD.created_by_principal_id,
        OLD.created_at
    ) THEN
        RAISE EXCEPTION 'policy rule version identity is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.status <> 'DRAFT' AND ROW(
        NEW.rule_category,
        NEW.severity,
        NEW.is_blocking,
        NEW.implementation_type,
        NEW.definition,
        NEW.definition_sha256,
        NEW.approved_by_principal_id
    ) IS DISTINCT FROM ROW(
        OLD.rule_category,
        OLD.severity,
        OLD.is_blocking,
        OLD.implementation_type,
        OLD.definition,
        OLD.definition_sha256,
        OLD.approved_by_principal_id
    ) THEN
        RAISE EXCEPTION 'non-DRAFT policy rule content is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF (OLD.status = 'DRAFT' AND NEW.status NOT IN (
            'DRAFT', 'ACTIVE', 'REJECTED', 'RETIRED'
       ))
       OR (OLD.status = 'ACTIVE' AND NEW.status NOT IN (
            'ACTIVE', 'RETIRED'
       ))
       OR (OLD.status IN ('REJECTED', 'RETIRED')
            AND NEW.status <> OLD.status) THEN
        RAISE EXCEPTION 'policy rule lifecycle cannot move from % to %',
            OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    IF OLD.status = 'ACTIVE'
       AND NEW.status = 'RETIRED'
       AND EXISTS (
            SELECT 1
              FROM policy.bundle_rule AS binding
              JOIN policy.policy_bundle AS bundle
                ON bundle.id = binding.policy_bundle_id
             WHERE binding.rule_version_id = OLD.id
               AND bundle.status = 'ACTIVE'
       ) THEN
        RAISE EXCEPTION
            'policy rule version is required by an ACTIVE policy bundle'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;


SET default_tablespace = '';

SET default_table_access_method = "heap";

--
-- Name: ai_attempt; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."ai_attempt" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "ai_job_id" "uuid" NOT NULL,
    "attempt_no" smallint NOT NULL,
    "model_id" "uuid" NOT NULL,
    "provider_request_id" "text",
    "status" "text" NOT NULL,
    "input_artifact_id" "uuid" NOT NULL,
    "output_artifact_id" "uuid",
    "input_sha256" "text" NOT NULL,
    "output_sha256" "text",
    "refusal_code" "text",
    "finish_reason" "text",
    "latency_ms" integer,
    "error_class" "text",
    "error_code" "text",
    "error_message" "text",
    "started_at" timestamp with time zone NOT NULL,
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "requested_model_id" "text" NOT NULL,
    "resolved_model_id" "text" NOT NULL,
    "response_fingerprint" "text",
    "provider_region" "text",
    "request_config" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "validation_status" "text" NOT NULL,
    "safety_identifier_hash" "text",
    "repair_attempt_no" smallint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_ai_attempt_complete" CHECK ((("status" = 'RUNNING'::"text") OR ("completed_at" IS NOT NULL))),
    CONSTRAINT "ck_ai_attempt_fingerprint" CHECK ((("response_fingerprint" IS NULL) OR ("btrim"("response_fingerprint") <> ''::"text"))),
    CONSTRAINT "ck_ai_attempt_input_hash" CHECK (("input_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_ai_attempt_latency" CHECK ((("latency_ms" IS NULL) OR ("latency_ms" >= 0))),
    CONSTRAINT "ck_ai_attempt_no" CHECK (("attempt_no" >= 1)),
    CONSTRAINT "ck_ai_attempt_output" CHECK ((("status" <> 'SUCCEEDED'::"text") OR (("output_artifact_id" IS NOT NULL) AND ("output_sha256" IS NOT NULL)))),
    CONSTRAINT "ck_ai_attempt_output_hash" CHECK ((("output_sha256" IS NULL) OR ("output_sha256" ~ '^[0-9a-f]{64}$'::"text"))),
    CONSTRAINT "ck_ai_attempt_region" CHECK ((("provider_region" IS NULL) OR ("btrim"("provider_region") <> ''::"text"))),
    CONSTRAINT "ck_ai_attempt_repair" CHECK ((("repair_attempt_no" IS NULL) OR (("repair_attempt_no" >= 0) AND ("repair_attempt_no" <= 1)))),
    CONSTRAINT "ck_ai_attempt_request_config" CHECK ((("request_config" IS NULL) OR ("jsonb_typeof"("request_config") = 'object'::"text"))),
    CONSTRAINT "ck_ai_attempt_requested_model" CHECK ((("requested_model_id" IS NULL) OR ("btrim"("requested_model_id") <> ''::"text"))),
    CONSTRAINT "ck_ai_attempt_resolved_model" CHECK ((("resolved_model_id" IS NULL) OR ("btrim"("resolved_model_id") <> ''::"text"))),
    CONSTRAINT "ck_ai_attempt_safety_hash" CHECK ((("safety_identifier_hash" IS NULL) OR ("safety_identifier_hash" ~ '^[0-9a-f]{64}$'::"text"))),
    CONSTRAINT "ck_ai_attempt_status" CHECK (("status" = ANY (ARRAY['RUNNING'::"text", 'SUCCEEDED'::"text", 'FAILED'::"text", 'REFUSED'::"text", 'TIMED_OUT'::"text", 'CANCELLED'::"text"]))),
    CONSTRAINT "ck_ai_attempt_validation" CHECK ((("validation_status" IS NULL) OR ("validation_status" = ANY (ARRAY['PENDING'::"text", 'PASSED'::"text", 'FAILED'::"text", 'QUARANTINED'::"text"]))))
);

--
-- Name: TABLE "ai_attempt"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."ai_attempt" IS 'Provider callごとの入力/出力Artifact、model、request ID、hash、Refusal、Latency、Errorを不変保存する。';

--
-- Name: COLUMN "ai_attempt"."id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "ai_attempt"."ai_job_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."ai_job_id" IS 'ai job id';

--
-- Name: COLUMN "ai_attempt"."attempt_no"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."attempt_no" IS 'attempt no';

--
-- Name: COLUMN "ai_attempt"."model_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."model_id" IS 'model id';

--
-- Name: COLUMN "ai_attempt"."provider_request_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."provider_request_id" IS 'provider request id';

--
-- Name: COLUMN "ai_attempt"."status"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "ai_attempt"."input_artifact_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."input_artifact_id" IS 'input artifact id';

--
-- Name: COLUMN "ai_attempt"."output_artifact_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."output_artifact_id" IS 'output artifact id';

--
-- Name: COLUMN "ai_attempt"."input_sha256"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."input_sha256" IS 'input sha256';

--
-- Name: COLUMN "ai_attempt"."output_sha256"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."output_sha256" IS 'output sha256';

--
-- Name: COLUMN "ai_attempt"."refusal_code"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."refusal_code" IS 'refusal code';

--
-- Name: COLUMN "ai_attempt"."finish_reason"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."finish_reason" IS 'finish reason';

--
-- Name: COLUMN "ai_attempt"."latency_ms"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."latency_ms" IS 'latency ms';

--
-- Name: COLUMN "ai_attempt"."error_class"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."error_class" IS 'error class';

--
-- Name: COLUMN "ai_attempt"."error_code"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."error_code" IS 'error code';

--
-- Name: COLUMN "ai_attempt"."error_message"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."error_message" IS 'error message';

--
-- Name: COLUMN "ai_attempt"."started_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."started_at" IS 'started at';

--
-- Name: COLUMN "ai_attempt"."completed_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."completed_at" IS 'completed at';

--
-- Name: COLUMN "ai_attempt"."created_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_attempt"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: ai_job; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."ai_job" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "ops_job_id" "uuid" NOT NULL,
    "task_definition_id" "uuid" NOT NULL,
    "article_plan_id" "uuid",
    "article_version_id" "uuid",
    "source_packet_version_id" "uuid" NOT NULL,
    "prompt_version_id" "uuid" NOT NULL,
    "output_schema_version_id" "uuid" NOT NULL,
    "model_route_version_id" "uuid" NOT NULL,
    "status" "text" DEFAULT 'REQUESTED'::"text" NOT NULL,
    "max_cost_jpy" bigint NOT NULL,
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "policy_bundle_version_id" "uuid",
    "release_decision_id" "uuid",
    "request_config" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "input_manifest_sha256" "text",
    "budget_reserved_jpy" bigint DEFAULT 0 NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_ai_job_budget_reserved" CHECK ((("budget_reserved_jpy" IS NULL) OR (("budget_reserved_jpy" >= 0) AND ("budget_reserved_jpy" <= "max_cost_jpy")))),
    CONSTRAINT "ck_ai_job_complete" CHECK ((("status" <> ALL (ARRAY['SUCCEEDED'::"text", 'FAILED_TERMINAL'::"text", 'QUARANTINED'::"text", 'CANCELLED'::"text", 'EXPIRED'::"text"])) OR ("completed_at" IS NOT NULL))),
    CONSTRAINT "ck_ai_job_cost" CHECK (("max_cost_jpy" >= 0)),
    CONSTRAINT "ck_ai_job_lock_version" CHECK ((("lock_version" IS NULL) OR ("lock_version" >= 0))),
    CONSTRAINT "ck_ai_job_manifest_sha" CHECK ((("input_manifest_sha256" IS NULL) OR ("input_manifest_sha256" ~ '^[0-9a-f]{64}$'::"text"))),
    CONSTRAINT "ck_ai_job_request_config" CHECK ((("request_config" IS NULL) OR ("jsonb_typeof"("request_config") = 'object'::"text"))),
    CONSTRAINT "ck_ai_job_status" CHECK (("status" = ANY (ARRAY['REQUESTED'::"text", 'VALIDATING_INPUT'::"text", 'QUEUED'::"text", 'RUNNING'::"text", 'VALIDATING_OUTPUT'::"text", 'AWAITING_HUMAN'::"text", 'SUCCEEDED'::"text", 'FAILED_RETRYABLE'::"text", 'RETRY_SCHEDULED'::"text", 'FAILED_TERMINAL'::"text", 'QUARANTINED'::"text", 'CANCELLED'::"text", 'EXPIRED'::"text"]))),
    CONSTRAINT "ck_ai_job_target" CHECK ((("article_plan_id" IS NOT NULL) OR ("article_version_id" IS NOT NULL)))
);

--
-- Name: TABLE "ai_job"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."ai_job" IS 'AI TaskのCanonical requestと各Version参照を固定し、Ops Jobと1対1で実行状態を管理する。';

--
-- Name: COLUMN "ai_job"."id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "ai_job"."display_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."display_id" IS 'AIJ-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "ai_job"."ops_job_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."ops_job_id" IS 'ops job id';

--
-- Name: COLUMN "ai_job"."task_definition_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."task_definition_id" IS 'task definition id';

--
-- Name: COLUMN "ai_job"."article_plan_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."article_plan_id" IS 'article plan id';
