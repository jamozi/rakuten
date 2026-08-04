-- ST-0003 / INT-DEC-004
-- Phase: CONTRACT PREPARE
-- Requires:
--   * canonical writers deployed
--   * 202607300009_ai_governance_migrate_batch.sql repeated until
--     automatic_remaining_rows = 0
--   * every BLOCKED AI Job and REJECTED Prompt explicitly classified
--   * every legacy Prompt bound to a verified human author principal
--   * all ST-0003 revision indexes valid and definition-exact
--
-- This short transaction installs canonical NOT VALID constraints. At commit,
-- legacy lifecycle writers and NULL writes to newly required fields are cut
-- off, while table scans remain deferred to 011.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $$
DECLARE
    isolated_role text;
    governance_table text;
    authority_relation text;
    helper regprocedure;
    expected record;
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0003 requires PostgreSQL 18 or later';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM pg_trigger AS trigger
         WHERE trigger.tgrelid = 'ops.object_artifact'::regclass
           AND trigger.tgname = 'trg_ops_object_artifact_immutable'
           AND trigger.tgfoid =
                'ops.reject_immutable_mutation()'::regprocedure
           AND trigger.tgtype = 27
           AND trigger.tgenabled = 'O'
           AND NOT trigger.tgisinternal
    ) THEN
        RAISE EXCEPTION
            'ST-0003 Contract prepare requires immutable object-artifact registry';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM ai.ai_job
         WHERE status IN ('PENDING', 'FAILED', 'BLOCKED')
            OR request_config IS NULL
            OR budget_reserved_jpy IS NULL
            OR lock_version IS NULL
            OR updated_at IS NULL
    ) THEN
        RAISE EXCEPTION
            'ST-0003 Contract prepare blocked by backlog, BLOCKED AI Job, or REJECTED Prompt';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM ai.ai_attempt
         WHERE requested_model_id IS NULL
            OR resolved_model_id IS NULL
            OR request_config IS NULL
            OR validation_status IS NULL
            OR repair_attempt_no IS NULL
    ) THEN
        RAISE EXCEPTION 'ST-0003 Contract prepare blocked by AI Attempt backlog';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM ai.prompt_version
         WHERE status = 'REJECTED'
            OR author_principal_id IS NULL
            OR locale IS NULL
            OR policy_test_status IS NULL
            OR lock_version IS NULL
            OR updated_at IS NULL
    ) THEN
        RAISE EXCEPTION
            'ST-0003 Contract prepare blocked by backlog or REJECTED Prompt';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM ai.model_definition
         WHERE provider_metadata IS NULL
    ) THEN
        RAISE EXCEPTION 'ST-0003 Contract prepare blocked by Model backlog';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM ai.model_route_version
         WHERE lock_version IS NULL OR updated_at IS NULL
    ) THEN
        RAISE EXCEPTION 'ST-0003 Contract prepare blocked by Route backlog';
    END IF;
    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE (conrelid, conname) IN (
             ('ai.ai_job'::regclass, 'ck_ai_job_status_st0003_expand'),
             ('ai.ai_job'::regclass, 'ck_ai_job_complete_st0003_expand'),
             ('ai.prompt_version'::regclass, 'ck_ai_prompt_status_st0003_expand'),
             ('ai.model_route_version'::regclass, 'ck_ai_route_status_st0003_expand')
         )
           AND convalidated
    ) <> 4 THEN
        RAISE EXCEPTION 'ST-0003 Contract prepare requires validated Expand constraints';
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
        RAISE EXCEPTION 'ST-0003 canonical constraints already exist';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM pg_index
         WHERE indexrelid =
                   to_regclass('ai.uq_ai_prompt_task_locale_active_st0003')
           AND indisunique
           AND indisvalid
           AND indisready
           AND pg_get_indexdef(indexrelid) =
               'CREATE UNIQUE INDEX uq_ai_prompt_task_locale_active_st0003 ON ai.prompt_version USING btree (task_definition_id, locale) WHERE (status = ''ACTIVE''::text)'
    ) THEN
        RAISE EXCEPTION
            'ST-0003 active Prompt index is missing or definition-drifted';
    END IF;
    FOR expected IN
        SELECT *
          FROM (VALUES
            ('ai.ix_ai_eval_case_task_split_st0003',
             'CREATE INDEX ix_ai_eval_case_task_split_st0003 ON ai.evaluation_case USING btree (task_definition_id, split, risk_level)'),
            ('ai.ix_ai_eval_run_suite_status_st0003',
             'CREATE INDEX ix_ai_eval_run_suite_status_st0003 ON ai.evaluation_run USING btree (suite_id, status, created_at DESC)'),
            ('ai.ix_ai_eval_case_result_run_status_st0003',
             'CREATE INDEX ix_ai_eval_case_result_run_status_st0003 ON ai.evaluation_case_result USING btree (evaluation_run_id, status)'),
            ('ai.ix_ai_eval_case_result_zero_tolerance_artifact_st0003',
             'CREATE INDEX ix_ai_eval_case_result_zero_tolerance_artifact_st0003 ON ai.evaluation_case_result USING btree (zero_tolerance_evidence_artifact_id)'),
            ('ai.uq_ai_eval_result_run_case_metric_st0003',
             'CREATE UNIQUE INDEX uq_ai_eval_result_run_case_metric_st0003 ON ai.evaluation_result USING btree (evaluation_run_id, evaluation_case_id, metric_code)'),
            ('ai.ix_ai_human_eval_result_st0003',
             'CREATE INDEX ix_ai_human_eval_result_st0003 ON ai.human_evaluation USING btree (evaluation_case_result_id, created_at)'),
            ('ai.ix_ai_release_task_status_st0003',
             'CREATE INDEX ix_ai_release_task_status_st0003 ON ai.release_decision USING btree (task_definition_id, status, approved_at DESC)'),
            ('ai.ix_ai_release_model_st0003',
             'CREATE INDEX ix_ai_release_model_st0003 ON ai.release_decision USING btree (resolved_model_id)'),
            ('ai.ix_ai_release_policy_st0003',
             'CREATE INDEX ix_ai_release_policy_st0003 ON ai.release_decision USING btree (policy_bundle_version_id)'),
            ('ai.ix_ai_release_dataset_st0003',
             'CREATE INDEX ix_ai_release_dataset_st0003 ON ai.release_decision USING btree (dataset_version_id)')
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
                'ST-0003 required index % is missing or definition-drifted',
                expected.index_name;
        END IF;
    END LOOP;

    FOREACH isolated_role IN ARRAY ARRAY[
        'raos_public_ro',
        'raos_reporting_ro',
        'raos_auditor_ro'
    ]
    LOOP
        IF has_schema_privilege(isolated_role, 'ai', 'USAGE') THEN
            RAISE EXCEPTION
                'ST-0003 isolation drift: role % has AI schema usage',
                isolated_role;
        END IF;
        FOREACH governance_table IN ARRAY ARRAY[
            'evaluation_suite',
            'evaluation_dataset_version',
            'evaluation_case',
            'evaluation_run',
            'evaluation_case_result',
            'human_evaluation',
            'judge_calibration',
            'release_decision',
            'release_approval'
        ]
        LOOP
            IF EXISTS (
                SELECT 1
                  FROM pg_class AS relation
                  CROSS JOIN LATERAL aclexplode(
                      COALESCE(
                          relation.relacl,
                          acldefault('r', relation.relowner)
                      )
                  ) AS privilege
                 WHERE relation.oid =
                    format('ai.%I', governance_table)::regclass
                   AND privilege.grantee = 0
                   AND privilege.privilege_type IN (
                        'SELECT', 'INSERT', 'UPDATE', 'DELETE'
                   )
            ) THEN
                RAISE EXCEPTION
                    'ST-0003 isolation drift: PUBLIC has privilege on ai.%',
                    governance_table;
            END IF;
            IF has_table_privilege(
                   isolated_role,
                   format('ai.%I', governance_table),
                   'SELECT'
               )
               OR has_table_privilege(
                   isolated_role,
                   format('ai.%I', governance_table),
                   'INSERT'
               )
               OR has_table_privilege(
                   isolated_role,
                   format('ai.%I', governance_table),
                   'UPDATE'
               )
               OR has_table_privilege(
                   isolated_role,
                   format('ai.%I', governance_table),
                   'DELETE'
               ) THEN
                RAISE EXCEPTION
                    'ST-0003 isolation drift: role % has privilege on ai.%',
                    isolated_role,
                    governance_table;
            END IF;
        END LOOP;
    END LOOP;

    FOREACH governance_table IN ARRAY ARRAY[
        'human_evaluation',
        'judge_calibration',
        'release_decision',
        'release_approval'
    ]
    LOOP
        IF has_table_privilege(
               'raos_worker_rw',
               format('ai.%I', governance_table),
               'INSERT'
           )
           OR has_table_privilege(
               'raos_worker_rw',
               format('ai.%I', governance_table),
               'UPDATE'
           )
           OR has_table_privilege(
               'raos_worker_rw',
               format('ai.%I', governance_table),
               'DELETE'
           ) THEN
            RAISE EXCEPTION
                'ST-0003 authority drift: worker can mutate human evidence ai.%',
                governance_table;
        END IF;
    END LOOP;

    FOREACH authority_relation IN ARRAY ARRAY[
        'ai.task_definition',
        'ai.prompt_version',
        'ai.output_schema_version',
        'ai.model_definition',
        'ai.model_route_version',
        'policy.policy_bundle',
        'policy.rule_version',
        'policy.bundle_rule',
        'policy.waiver',
        'policy.gate_decision'
    ]
    LOOP
        IF has_table_privilege(
               'raos_worker_rw', authority_relation, 'INSERT'
           )
           OR has_table_privilege(
               'raos_worker_rw', authority_relation, 'UPDATE'
           )
           OR has_table_privilege(
               'raos_worker_rw', authority_relation, 'DELETE'
           ) THEN
            RAISE EXCEPTION
                'ST-0003 authority drift: worker can mutate %',
                authority_relation;
        END IF;
    END LOOP;

    IF NOT has_column_privilege(
           'raos_worker_rw', 'policy.finding', 'finding_code', 'INSERT'
       )
       OR has_column_privilege(
           'raos_worker_rw', 'policy.finding', 'status', 'INSERT'
       )
       OR has_column_privilege(
           'raos_worker_rw', 'policy.finding', 'resolved_at', 'INSERT'
       )
       OR has_column_privilege(
           'raos_worker_rw', 'policy.finding',
           'resolved_by_principal_id', 'INSERT'
       )
       OR has_table_privilege(
           'raos_worker_rw', 'policy.finding', 'UPDATE'
       )
       OR has_table_privilege(
           'raos_worker_rw', 'policy.finding', 'DELETE'
       ) THEN
        RAISE EXCEPTION
            'ST-0003 authority drift: worker Finding privileges are not append-only OPEN data';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM policy.policy_bundle AS bundle
          JOIN policy.bundle_rule AS binding
            ON binding.policy_bundle_id = bundle.id
          JOIN policy.rule_version AS rule
            ON rule.id = binding.rule_version_id
         WHERE bundle.status = 'ACTIVE'
           AND rule.status <> 'ACTIVE'
    ) THEN
        RAISE EXCEPTION
            'ST-0003 policy drift: ACTIVE bundle contains non-ACTIVE rule version';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'ai'
           AND table_name = 'evaluation_result'
           AND column_name = 'passed'
           AND is_nullable = 'YES'
    ) THEN
        RAISE EXCEPTION
            'ST-0003 evaluation_result.passed must support report-only metrics';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'ai'
           AND table_name = 'evaluation_case_result'
           AND column_name = 'zero_tolerance_failure_count'
           AND is_generated = 'ALWAYS'
           AND is_nullable = 'NO'
    ) OR (
        SELECT count(*)
          FROM information_schema.columns
         WHERE table_schema = 'ai'
           AND table_name = 'evaluation_case_result'
           AND column_name IN (
                'zero_tolerance_evidence',
                'zero_tolerance_evidence_artifact_id',
                'zero_tolerance_evidence_sha256'
           )
           AND is_nullable = 'NO'
    ) <> 3 OR EXISTS (
        SELECT required.constraint_name
          FROM (VALUES
            ('ck_ai_eval_case_result_zero_tolerance_evidence'),
            ('ck_ai_eval_case_result_zero_tolerance_sha'),
            ('ck_ai_eval_case_result_passed_zero_tolerance'),
            ('fk_ai_eval_case_result_zero_tolerance_artifact')
          ) AS required(constraint_name)
         WHERE NOT EXISTS (
            SELECT 1
              FROM pg_constraint AS constraint_record
             WHERE constraint_record.conrelid =
                    'ai.evaluation_case_result'::regclass
               AND constraint_record.conname = required.constraint_name
               AND constraint_record.convalidated
         )
    ) THEN
        RAISE EXCEPTION
            'ST-0003 zero-tolerance evidence shape/generation is incomplete';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_trigger
         WHERE tgrelid = 'policy.rule_version'::regclass
           AND tgname = 'trg_policy_rule_version_immutable'
           AND tgenabled = 'O'
           AND NOT tgisinternal
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_trigger
         WHERE tgrelid = 'policy.bundle_rule'::regclass
           AND tgname = 'trg_policy_bundle_rule_append_only'
           AND tgenabled = 'O'
           AND NOT tgisinternal
    ) THEN
        RAISE EXCEPTION
            'ST-0003 policy drift: immutable policy child graph guards are absent';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM (VALUES
            (
                'ai.guard_evaluation_run_mutation()'::regprocedure,
                ARRAY['search_path=pg_catalog, ai, pg_temp']::text[]
            ),
            (
                'ai.guard_evaluation_run_start_integrity()'::regprocedure,
                ARRAY['search_path=pg_catalog, ai, policy, pg_temp']::text[]
            ),
            (
                'ai.guard_evaluation_run_completion_evidence()'::regprocedure,
                ARRAY['search_path=pg_catalog, ai, pg_temp']::text[]
            )
          ) AS guard_expectation(function_oid, expected_config)
          JOIN pg_proc AS proc
            ON proc.oid = guard_expectation.function_oid
         WHERE NOT proc.prosecdef
            OR proc.proconfig IS DISTINCT FROM
                guard_expectation.expected_config
            OR proc.proowner <> (
                SELECT relation.relowner
                  FROM pg_class AS relation
                 WHERE relation.oid = 'ai.evaluation_run'::regclass
            )
            OR has_function_privilege(
                'raos_worker_rw',
                guard_expectation.function_oid,
                'EXECUTE'
            )
    ) THEN
        RAISE EXCEPTION
            'ST-0003 evaluation-run SECURITY DEFINER boundary drifted';
    END IF;

    FOREACH helper IN ARRAY ARRAY[
        'ai.guard_evaluation_suite_mutation()'::regprocedure,
        'ai.guard_judge_calibration_mutation()'::regprocedure,
        'ai.guard_locked_evaluation_dataset()'::regprocedure,
        'ai.guard_evaluation_case_mutation()'::regprocedure,
        'ai.guard_evaluation_run_mutation()'::regprocedure,
        'ai.guard_open_evaluation_run_result()'::regprocedure,
        'ai.guard_evaluated_attempt_immutability()'::regprocedure,
        'ai.guard_evaluated_job_binding()'::regprocedure,
        'ai.guard_governance_component_dependency()'::regprocedure,
        'policy.guard_rule_version_immutability()'::regprocedure,
        'policy.guard_bundle_rule_append_only()'::regprocedure,
        'ai.guard_open_human_evaluation()'::regprocedure,
        'ai.guard_evaluation_metric_mutation()'::regprocedure,
        'ai.guard_release_decision_mutation()'::regprocedure,
        'ai.guard_release_task_serialization()'::regprocedure,
        'ai.guard_canonical_suite_config()'::regprocedure,
        'ai.guard_evaluation_run_start_integrity()'::regprocedure,
        'ai.guard_judge_calibration_scope()'::regprocedure,
        'ai.guard_release_approval_mutation()'::regprocedure,
        'ai.guard_evaluation_run_completion_evidence()'::regprocedure,
        'ai.guard_release_decision_evidence()'::regprocedure,
        'ai.guard_task_definition_lifecycle()'::regprocedure,
        'ai.guard_prompt_version_lifecycle()'::regprocedure,
        'ai.guard_model_route_lifecycle()'::regprocedure,
        'ai.guard_output_schema_lifecycle()'::regprocedure,
        'ai.guard_model_definition_lifecycle()'::regprocedure,
        'policy.guard_policy_bundle_lifecycle()'::regprocedure,
        'ai.canonical_suite_risk(text)'::regprocedure,
        'ai.canonical_suite_config(text)'::regprocedure,
        'ai.canonical_grader_output_metrics(text)'::regprocedure,
        'ai.canonical_metric_unit(text)'::regprocedure,
        'ai.canonical_metric_direction(text)'::regprocedure,
        'ai.canonical_regression_margin(text)'::regprocedure,
        'ai.assert_evaluation_run_evidence(uuid,boolean)'::regprocedure,
        'ai.assert_regression_against_baseline(uuid,uuid)'::regprocedure,
        'ai.artifact_matches_immutable_hash(uuid,text)'::regprocedure,
        'ai.has_live_rollback_dependents(text,uuid)'::regprocedure
    ]
    LOOP
        IF EXISTS (
            SELECT 1
              FROM pg_proc AS proc
              CROSS JOIN LATERAL aclexplode(
                  COALESCE(
                      proc.proacl,
                      acldefault('f', proc.proowner)
                  )
              ) AS privilege
             WHERE proc.oid = helper
               AND privilege.grantee = 0
               AND privilege.privilege_type = 'EXECUTE'
        ) THEN
            RAISE EXCEPTION
                'ST-0003 trigger helper % is directly executable by PUBLIC',
                helper;
        END IF;
    END LOOP;

    IF NOT has_function_privilege(
           'raos_api_rw',
           'ai.canonical_suite_risk(text)',
           'EXECUTE'
       )
       OR NOT has_function_privilege(
           'raos_api_rw',
           'ai.canonical_suite_config(text)',
           'EXECUTE'
       )
       OR NOT has_function_privilege(
           'raos_api_rw',
           'ai.canonical_grader_output_metrics(text)',
           'EXECUTE'
       )
       OR NOT has_function_privilege(
           'raos_api_rw',
           'ai.canonical_metric_unit(text)',
           'EXECUTE'
       )
       OR NOT has_function_privilege(
           'raos_api_rw',
           'ai.canonical_metric_direction(text)',
           'EXECUTE'
       )
       OR NOT has_function_privilege(
           'raos_api_rw',
           'ai.canonical_regression_margin(text)',
           'EXECUTE'
       )
       OR NOT has_function_privilege(
           'raos_api_rw',
           'ai.assert_evaluation_run_evidence(uuid,boolean)',
           'EXECUTE'
       )
       OR NOT has_function_privilege(
           'raos_api_rw',
           'ai.assert_regression_against_baseline(uuid,uuid)',
           'EXECUTE'
       )
       OR NOT has_function_privilege(
           'raos_api_rw',
           'ai.artifact_matches_immutable_hash(uuid,text)',
           'EXECUTE'
       )
       OR NOT has_function_privilege(
           'raos_api_rw',
           'ai.has_live_rollback_dependents(text,uuid)',
           'EXECUTE'
       )
       OR NOT has_function_privilege(
           'raos_worker_rw',
           'ai.canonical_suite_risk(text)',
           'EXECUTE'
       )
       OR NOT has_function_privilege(
           'raos_worker_rw',
           'ai.canonical_suite_config(text)',
           'EXECUTE'
       )
       OR NOT has_function_privilege(
           'raos_worker_rw',
           'ai.canonical_grader_output_metrics(text)',
           'EXECUTE'
       )
       OR NOT has_function_privilege(
           'raos_worker_rw',
           'ai.canonical_metric_unit(text)',
           'EXECUTE'
       )
       OR has_function_privilege(
           'raos_worker_rw',
           'ai.assert_evaluation_run_evidence(uuid,boolean)',
           'EXECUTE'
       )
       OR has_function_privilege(
           'raos_worker_rw',
           'ai.canonical_metric_direction(text)',
           'EXECUTE'
       )
       OR has_function_privilege(
           'raos_worker_rw',
           'ai.canonical_regression_margin(text)',
           'EXECUTE'
       )
       OR has_function_privilege(
           'raos_worker_rw',
           'ai.assert_regression_against_baseline(uuid,uuid)',
           'EXECUTE'
       )
       OR has_function_privilege(
           'raos_worker_rw',
           'ai.artifact_matches_immutable_hash(uuid,text)',
           'EXECUTE'
       )
       OR has_function_privilege(
           'raos_worker_rw',
           'ai.has_live_rollback_dependents(text,uuid)',
           'EXECUTE'
       ) THEN
        RAISE EXCEPTION
            'ST-0003 helper execution grants do not match API/worker least privilege';
    END IF;
END
$$;

ALTER TABLE ai.ai_job
    ADD CONSTRAINT ck_ai_job_status CHECK (
        status IN (
            'REQUESTED',
            'VALIDATING_INPUT',
            'QUEUED',
            'RUNNING',
            'VALIDATING_OUTPUT',
            'AWAITING_HUMAN',
            'SUCCEEDED',
            'FAILED_RETRYABLE',
            'RETRY_SCHEDULED',
            'FAILED_TERMINAL',
            'QUARANTINED',
            'CANCELLED',
            'EXPIRED'
        )
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_job_complete CHECK (
        status NOT IN (
            'SUCCEEDED',
            'FAILED_TERMINAL',
            'QUARANTINED',
            'CANCELLED',
            'EXPIRED'
        )
        OR completed_at IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_job_request_config_not_null CHECK (
        request_config IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_job_budget_reserved_not_null CHECK (
        budget_reserved_jpy IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_job_lock_version_not_null CHECK (
        lock_version IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_job_updated_at_not_null CHECK (
        updated_at IS NOT NULL
    ) NOT VALID;

ALTER TABLE ai.ai_attempt
    ADD CONSTRAINT ck_ai_attempt_requested_model_not_null CHECK (
        requested_model_id IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_attempt_resolved_model_not_null CHECK (
        resolved_model_id IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_attempt_request_config_not_null CHECK (
        request_config IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_attempt_validation_not_null CHECK (
        validation_status IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_attempt_repair_not_null CHECK (
        repair_attempt_no IS NOT NULL
    ) NOT VALID;

ALTER TABLE ai.prompt_version
    ADD CONSTRAINT ck_ai_prompt_status CHECK (
        status IN (
            'DRAFT',
            'IN_REVIEW',
            'EVALUATING',
            'CERTIFIED',
            'ACTIVE',
            'SUSPENDED',
            'RETIRED'
        )
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_prompt_locale_not_null CHECK (
        locale IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_prompt_author_not_null CHECK (
        author_principal_id IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_prompt_policy_test_not_null CHECK (
        policy_test_status IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_prompt_lock_version_not_null CHECK (
        lock_version IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_prompt_updated_at_not_null CHECK (
        updated_at IS NOT NULL
    ) NOT VALID;

ALTER TABLE ai.model_definition
    ADD CONSTRAINT ck_ai_model_metadata_not_null CHECK (
        provider_metadata IS NOT NULL
    ) NOT VALID;

ALTER TABLE ai.model_route_version
    ADD CONSTRAINT ck_ai_route_status CHECK (
        status IN (
            'DRAFT',
            'EVALUATING',
            'CERTIFIED',
            'CANARY',
            'ACTIVE',
            'PAUSED',
            'ROLLED_BACK',
            'RETIRED'
        )
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_route_lock_version_not_null CHECK (
        lock_version IS NOT NULL
    ) NOT VALID,
    ADD CONSTRAINT ck_ai_route_updated_at_not_null CHECK (
        updated_at IS NOT NULL
    ) NOT VALID;

COMMIT;
