"""Always-on structural checks for the formal ST-0003 migration."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATABASE_ROOT = REPOSITORY_ROOT / "changes" / "st-0003" / "database"
PROPOSAL_SQL = (
    REPOSITORY_ROOT
    / "docs"
    / "upstream"
    / "patches"
    / "RAOS_05_001_ai_data_alignment_patch_v0.1.sql"
)
MIGRATION_FILES = (
    "202607300007_ai_governance_expand.sql",
    "202607300008_ai_governance_expand_validate.sql",
    "202607300009_ai_governance_migrate_batch.sql",
    "202607300010_ai_governance_contract_prepare.sql",
    "202607300011_ai_governance_contract.sql",
    "202607300012_ai_governance_guarded_downgrade.sql",
)
GOVERNANCE_TABLES = (
    "evaluation_suite",
    "evaluation_dataset_version",
    "evaluation_case",
    "evaluation_run",
    "evaluation_case_result",
    "human_evaluation",
    "judge_calibration",
    "release_decision",
    "release_approval",
)
AI_JOB_STATES = (
    "REQUESTED",
    "VALIDATING_INPUT",
    "QUEUED",
    "RUNNING",
    "VALIDATING_OUTPUT",
    "AWAITING_HUMAN",
    "SUCCEEDED",
    "FAILED_RETRYABLE",
    "RETRY_SCHEDULED",
    "FAILED_TERMINAL",
    "QUARANTINED",
    "CANCELLED",
    "EXPIRED",
)
PROMPT_STATES = (
    "DRAFT",
    "IN_REVIEW",
    "EVALUATING",
    "CERTIFIED",
    "ACTIVE",
    "SUSPENDED",
    "RETIRED",
)
ROUTE_STATES = (
    "DRAFT",
    "EVALUATING",
    "CERTIFIED",
    "CANARY",
    "ACTIVE",
    "PAUSED",
    "ROLLED_BACK",
    "RETIRED",
)
DEPENDENCY_GUARD_TRIGGERS = (
    "trg_ai_task_dependency_guard",
    "trg_ai_prompt_dependency_guard",
    "trg_ai_route_dependency_guard",
    "trg_ai_schema_dependency_guard",
    "trg_ai_model_dependency_guard",
    "trg_policy_bundle_dependency_guard",
)
POLICY_CHILD_GUARD_TRIGGERS = (
    "trg_policy_rule_version_immutable",
    "trg_policy_bundle_rule_append_only",
)


def sql(name: str) -> str:
    return (DATABASE_ROOT / name).read_text(encoding="utf-8")


def create_table_block(document: str, table: str) -> str:
    match = re.search(
        rf"CREATE TABLE ai\.{re.escape(table)} \((.*?)\n\);",
        document,
        flags=re.DOTALL,
    )
    assert match, f"CREATE TABLE block not found: ai.{table}"
    return match.group(1)


def test_exact_migration_checkpoint_inventory_exists() -> None:
    actual_sql = {
        path.name for path in DATABASE_ROOT.glob("*.sql") if path.is_file()
    }
    assert actual_sql == set(MIGRATION_FILES)
    assert (DATABASE_ROOT / "forward-recovery.md").is_file()


def test_formal_migration_never_executes_or_copies_the_proposal() -> None:
    proposal = PROPOSAL_SQL.read_bytes()
    proposal_hash = sha256(proposal).hexdigest()

    for name in MIGRATION_FILES:
        path = DATABASE_ROOT / name
        assert path.read_bytes() != proposal
        assert sha256(path.read_bytes()).hexdigest() != proposal_hash
        text = sql(name)
        assert "RAOS_05_001_ai_data_alignment_patch" not in text
        assert "INSERT INTO ai.task_definition" not in text
        assert "ON CONFLICT (task_code) DO UPDATE" not in text


def test_expand_is_additive_short_and_leaves_validation_separate() -> None:
    expand = sql(MIGRATION_FILES[0])
    assert "-- Phase: EXPAND" in expand
    assert "SET LOCAL lock_timeout" in expand
    assert "SET LOCAL statement_timeout" in expand
    assert "VALIDATE CONSTRAINT" not in expand
    assert "CREATE INDEX CONCURRENTLY" not in expand
    assert "NOT VALID" in expand

    for table in GOVERNANCE_TABLES:
        assert f"CREATE TABLE ai.{table}" in expand
    for table in (
        "ai_job",
        "ai_attempt",
        "prompt_version",
        "model_definition",
        "model_route_version",
        "evaluation_result",
    ):
        assert f"ALTER TABLE ai.{table}" in expand


def test_expand_validate_separates_validation_and_concurrent_indexes() -> None:
    validate = sql(MIGRATION_FILES[1])
    contract_prepare = sql(MIGRATION_FILES[3])
    contract = sql(MIGRATION_FILES[4])
    downgrade = sql(MIGRATION_FILES[5])
    assert "VALIDATE CONSTRAINT" in validate
    assert "COMMIT;" in validate
    assert "CREATE INDEX CONCURRENTLY" in validate
    assert "pg_get_indexdef" in validate
    assert "indisvalid" in validate
    assert "indisready" in validate

    for table in GOVERNANCE_TABLES:
        assert f"ALTER TABLE ai.{table}" in validate

    zero_tolerance_index = "ix_ai_eval_case_result_zero_tolerance_artifact_st0003"
    assert re.search(
        r"CREATE INDEX CONCURRENTLY IF NOT EXISTS\s+"
        + re.escape(zero_tolerance_index),
        validate,
    )
    expected_definition = (
        f"CREATE INDEX {zero_tolerance_index} ON ai.evaluation_case_result "
        "USING btree (zero_tolerance_evidence_artifact_id)"
    )
    assert validate.count(expected_definition) == 2
    assert expected_definition in contract_prepare
    assert contract.count(zero_tolerance_index) == 2
    assert (
        f"ALTER INDEX ai.{zero_tolerance_index}\n"
        "    RENAME TO ix_ai_eval_case_result_zero_tolerance_artifact;"
        in contract
    )
    assert (
        "DROP INDEX ai.ix_ai_eval_case_result_zero_tolerance_artifact;"
        in downgrade
    )


def test_migrate_batch_is_bounded_locked_and_never_guesses_ambiguous_states() -> None:
    migrate = sql(MIGRATION_FILES[2])
    assert "FOR UPDATE SKIP LOCKED" in migrate
    assert (
        "remaining integer NOT NULL CHECK (remaining BETWEEN 0 AND 1000)"
        in migrate
    )
    assert "INSERT INTO st0003_batch_budget (remaining) VALUES (1000)" in migrate
    dynamic_limits = re.findall(
        r"LIMIT\s+LEAST\(\s*1000\s*,\s*"
        r"\(SELECT\s+remaining\s+FROM\s+st0003_batch_budget\)\s*\)",
        migrate,
    )
    assert len(dynamic_limits) == 5
    assert migrate.count("SET remaining = remaining - COALESCE") == 5
    assert "IF changed_rows > 1000 THEN" in migrate
    assert "PENDING" in migrate and "REQUESTED" in migrate
    assert "FAILED" in migrate and "FAILED_TERMINAL" in migrate
    assert "WHEN 'BLOCKED'" not in migrate
    assert "WHEN 'REJECTED'" not in migrate
    assert "BLOCKED" in migrate
    assert "REJECTED" in migrate


def test_contract_phases_install_only_canonical_state_sets() -> None:
    prepare = sql(MIGRATION_FILES[3])
    contract = sql(MIGRATION_FILES[4])

    assert "NOT VALID" in prepare
    assert "VALIDATE CONSTRAINT" in contract
    assert "ALTER COLUMN status SET DEFAULT 'REQUESTED'" in contract
    assert "ALTER COLUMN locale SET NOT NULL" in contract
    assert "DROP CONSTRAINT ck_ai_job_status_st0003_expand" in contract
    assert "DROP CONSTRAINT ck_ai_prompt_status_st0003_expand" in contract
    assert "DROP CONSTRAINT ck_ai_route_status_st0003_expand" in contract

    for state in AI_JOB_STATES:
        assert f"'{state}'" in prepare
    for state in PROMPT_STATES:
        assert f"'{state}'" in prepare
    for state in ROUTE_STATES:
        assert f"'{state}'" in prepare

    job_status_clause = prepare.split(
        "ADD CONSTRAINT ck_ai_job_status", 1
    )[1].split("NOT VALID", 1)[0]
    assert "'PENDING'" not in job_status_clause
    assert "'BLOCKED'" not in job_status_clause
    assert "'FAILED'" not in job_status_clause
    assert "status IN ('DRAFT', 'ACTIVE', 'RETIRED', 'REJECTED')" not in prepare


def test_high_risk_guards_are_private_and_existing_table_triggers_wait_for_contract() -> None:
    expand = sql(MIGRATION_FILES[0])
    contract = sql(MIGRATION_FILES[4])

    guard_functions = (
        "ai.guard_evaluation_run_start_integrity()",
        "ai.guard_evaluation_metric_mutation()",
        "ai.guard_judge_calibration_scope()",
        "ai.guard_release_approval_mutation()",
        "ai.guard_evaluation_run_completion_evidence()",
        "ai.guard_release_decision_evidence()",
        "ai.guard_task_definition_lifecycle()",
        "ai.guard_prompt_version_lifecycle()",
        "ai.guard_model_route_lifecycle()",
        "ai.guard_output_schema_lifecycle()",
        "ai.guard_model_definition_lifecycle()",
        "policy.guard_policy_bundle_lifecycle()",
        "ai.canonical_grader_output_metrics(text)",
        "ai.has_live_rollback_dependents(text, uuid)",
        "ai.guard_governance_component_dependency()",
        "policy.guard_rule_version_immutability()",
        "policy.guard_bundle_rule_append_only()",
    )
    for function_name in guard_functions:
        revoke_pattern = (
            r"REVOKE\s+ALL\s+ON\s+FUNCTION\s+"
            + re.escape(function_name)
            + r"\s+FROM\s+PUBLIC"
        )
        assert re.search(revoke_pattern, expand)

    lifecycle_triggers = (
        "trg_ai_task_definition_lifecycle",
        "trg_ai_prompt_version_lifecycle",
        "trg_ai_model_route_lifecycle",
        "trg_ai_output_schema_lifecycle",
        "trg_ai_model_definition_lifecycle",
        "trg_policy_bundle_lifecycle",
    )
    for trigger_name in lifecycle_triggers:
        assert trigger_name not in expand
        assert f"CREATE TRIGGER {trigger_name}" in contract


def test_early_component_dependency_guard_spans_the_migration_window() -> None:
    expand = sql(MIGRATION_FILES[0])
    prepare = sql(MIGRATION_FILES[3])
    contract = sql(MIGRATION_FILES[4])
    downgrade = sql(MIGRATION_FILES[5])
    helper = "ai.guard_governance_component_dependency()"

    assert f"CREATE FUNCTION {helper} RETURNS trigger" in expand
    assert f"REVOKE ALL ON FUNCTION {helper}" in expand
    assert "run.status <> 'PLANNED'" in expand
    assert "evaluated governance component %.% content is immutable" in expand
    for trigger_name in DEPENDENCY_GUARD_TRIGGERS:
        assert f"CREATE TRIGGER {trigger_name}" in expand
        assert f"DROP TRIGGER {trigger_name}" not in contract
        assert f"DROP TRIGGER {trigger_name}" in downgrade

    assert f"'{helper}'::regprocedure" in prepare
    assert f"'{helper}'" in downgrade
    assert f"DROP FUNCTION {helper}" in downgrade


def test_policy_child_graph_is_guarded_from_expand_through_downgrade() -> None:
    expand = sql(MIGRATION_FILES[0])
    prepare = sql(MIGRATION_FILES[3])
    contract = sql(MIGRATION_FILES[4])
    downgrade = sql(MIGRATION_FILES[5])
    helpers = (
        "policy.guard_rule_version_immutability()",
        "policy.guard_bundle_rule_append_only()",
    )

    for helper in helpers:
        assert f"CREATE FUNCTION {helper} RETURNS trigger" in expand
        assert f"REVOKE ALL ON FUNCTION {helper}" in expand
        assert f"'{helper}'::regprocedure" in prepare
        assert f"'{helper}'" in downgrade
        assert f"DROP FUNCTION {helper}" in downgrade
    for trigger_name in POLICY_CHILD_GUARD_TRIGGERS:
        assert f"CREATE TRIGGER {trigger_name}" in expand
        assert trigger_name in prepare
        assert f"DROP TRIGGER {trigger_name}" not in contract
        assert f"DROP TRIGGER {trigger_name}" in downgrade

    for invariant in (
        "policy rule version identity is immutable",
        "non-DRAFT policy rule content is immutable",
        "policy rule lifecycle cannot move from % to %",
        "required by an ACTIVE policy bundle",
        "policy bundle rule bindings are append-only",
        "policy bundle rules require a DRAFT bundle",
        "policy bundle rules require an ACTIVE rule version",
        "pg_advisory_xact_lock(72003",
        "policy activation requires every bound rule version to be ACTIVE",
        "evaluation run policy bundle contains a non-ACTIVE rule version",
    ):
        assert invariant in expand
    assert "WHERE bundle.status = 'ACTIVE'" in prepare
    assert "AND rule.status <> 'ACTIVE'" in prepare
    assert "immutable policy child graph guards are absent" in prepare


def test_release_approval_and_model_judge_provenance_are_exact_and_non_public() -> None:
    expand = sql(MIGRATION_FILES[0])
    result_constraints = expand.split(
        "ADD CONSTRAINT ck_ai_eval_result_judge_provenance_st0003_expand",
        1,
    )[1].split("NOT VALID", 1)[0]

    for column in (
        "judge_calibration_id",
        "judge_route_version_id",
        "judge_prompt_version_id",
        "judge_rubric_artifact_id",
        "judge_resolved_model_id",
        "judge_grader_version",
    ):
        assert f"ADD COLUMN {column}" in expand
        assert column in result_constraints
    assert "grader.model_judge.v1" in result_constraints

    release_approval = create_table_block(expand, "release_approval")
    for token in (
        "phase text NOT NULL",
        "decision_manifest_sha256 text NOT NULL",
        "primary_approver_principal_id uuid NOT NULL",
        "second_approver_principal_id uuid NOT NULL",
        "approval_artifact_id uuid NOT NULL",
        "approval_sha256 text NOT NULL",
        "signed_at timestamptz NOT NULL",
        "UNIQUE (",
    ):
        assert token in release_approval
    assert "FROM PUBLIC, raos_public_ro, raos_reporting_ro, raos_auditor_ro" in expand
    assert "REVOKE INSERT, UPDATE, DELETE ON TABLE" in expand
    assert "ai.release_approval" in expand


def test_worker_authority_tables_are_revoked_while_data_plane_writes_remain() -> None:
    expand = sql(MIGRATION_FILES[0])
    prepare = sql(MIGRATION_FILES[3])
    worker_revoke_blocks = "\n".join(
        re.findall(
            r"REVOKE\s+INSERT,\s*UPDATE,\s*DELETE\s+ON\s+TABLE"
            r"(.*?)FROM\s+raos_worker_rw\s*;",
            expand,
            flags=re.DOTALL,
        )
    )
    authority_tables = (
        "ai.task_definition",
        "ai.prompt_version",
        "ai.model_route_version",
        "ai.output_schema_version",
        "ai.model_definition",
        "policy.policy_bundle",
    )
    for relation in authority_tables:
        assert relation in worker_revoke_blocks
        assert relation in prepare

    worker_data_plane_grant = re.search(
        r"GRANT\s+INSERT,\s*UPDATE\s+ON\s+TABLE(.*?)"
        r"TO\s+raos_worker_rw\s*;",
        expand,
        flags=re.DOTALL,
    )
    assert worker_data_plane_grant
    for relation in ("ai.evaluation_run", "ai.evaluation_case_result"):
        assert relation in worker_data_plane_grant.group(1)


def test_attempt_truth_table_and_release_phase_state_are_checkpointed() -> None:
    expand = sql(MIGRATION_FILES[0])
    validate = sql(MIGRATION_FILES[1])
    prepare = sql(MIGRATION_FILES[3])
    contract = sql(MIGRATION_FILES[4])
    downgrade = sql(MIGRATION_FILES[5])
    case_result = create_table_block(expand, "evaluation_case_result")

    assert "UNIQUE (ai_attempt_id)" in case_result
    assert "UNIQUE (output_artifact_id)" in case_result
    assert "uq_ai_eval_case_input" in expand
    for disposition in (
        "CALL_PROVIDER_AND_PASS",
        "CALL_PROVIDER_AND_FLAG",
        "BLOCK_BEFORE_PROVIDER",
        "EXPECTED_REFUSAL",
        "EXPECTED_TERMINAL_FAILURE",
    ):
        assert f"'{disposition}'" in case_result
    assert "CREATE FUNCTION ai.guard_open_evaluation_run_result()" in expand
    for binding in (
        "attempt.model_id",
        "attempt.resolved_model_id",
        "attempt.input_artifact_id",
        "attempt.input_sha256",
        "attempt.output_artifact_id",
        "attempt.output_sha256",
        "attempt.validation_status",
        "input_artifact.sha256",
        "input_artifact.is_immutable",
        "job.prompt_version_id",
        "job.model_route_version_id",
        "job.output_schema_version_id",
        "job.policy_bundle_version_id",
    ):
        assert binding in expand

    assert "ck_ai_release_phase_state_st0003_expand" in expand
    assert (
        "VALIDATE CONSTRAINT ck_ai_release_phase_state_st0003_expand"
        in validate
    )
    assert "ck_ai_release_phase_state_st0003_expand" in contract
    assert "TO ck_ai_release_phase_state" in contract

    metric_identity_index = "uq_ai_eval_result_run_case_metric_st0003"
    assert re.search(
        r"CREATE\s+UNIQUE\s+INDEX\s+CONCURRENTLY\s+IF\s+NOT\s+EXISTS\s+"
        + re.escape(metric_identity_index),
        validate,
    )
    assert metric_identity_index in prepare
    assert metric_identity_index in contract
    assert "RENAME TO uq_ai_eval_result_run_case_metric" in contract
    assert "DROP INDEX ai.uq_ai_eval_result_run_case_metric" in downgrade


def test_canary_start_checkpoint_is_immutable_before_evidence_attachment() -> None:
    expand = sql(MIGRATION_FILES[0])
    immutable_guard = expand.index("IF OLD.canary_started_at IS NOT NULL")
    same_status_return = expand.index(
        "IF OLD.status = NEW.status",
        immutable_guard,
    )

    assert immutable_guard < same_status_return
    immutable_block = expand[immutable_guard:same_status_return]
    assert "NEW.canary_started_at" in immutable_block
    assert "NEW.canary_started_txid" in immutable_block
    assert "OLD.canary_started_at" in immutable_block
    assert "OLD.canary_started_txid" in immutable_block
    assert "canary start time/transaction is immutable" in immutable_block


def test_release_draft_does_not_require_approval_at_insert_time() -> None:
    release = create_table_block(sql(MIGRATION_FILES[0]), "release_decision")
    for binding in (
        "resolved_model_id uuid NOT NULL",
        "policy_bundle_version_id uuid NOT NULL",
        "dataset_version_id uuid NOT NULL",
        "code_git_sha text NOT NULL",
    ):
        assert binding in release
    assert re.search(r"\n\s+approved_by_principal_id uuid,\n", release)
    assert re.search(r"\n\s+second_approver_principal_id uuid,\n", release)
    assert re.search(r"\n\s+approved_at timestamptz,\n", release)
    assert (
        "status NOT IN ('APPROVED_CANARY', 'APPROVED_ACTIVE', 'REVOKED')"
        in release
    )


def test_zero_tolerance_ratio_and_champion_regression_guards_are_structural() -> None:
    expand = sql(MIGRATION_FILES[0])
    contract_prepare = sql(MIGRATION_FILES[3])
    downgrade = sql(MIGRATION_FILES[5])

    for column in (
        "zero_tolerance_evidence jsonb NOT NULL",
        "zero_tolerance_evidence_artifact_id uuid NOT NULL",
        "zero_tolerance_evidence_sha256 text NOT NULL",
        "baseline_evaluation_run_id uuid",
        "proportion_numerator_count bigint",
        "proportion_denominator_count bigint",
    ):
        assert column in expand
    for failure_code in (
        "AI-FCT-001",
        "AI-FCT-004",
        "AI-POL-001",
        "AI-POL-002",
        "AI-FCT-003",
        "AI-POL-003",
        "AI-POL-005",
        "AI-POL-004",
    ):
        assert failure_code in expand
    generated_failure_count = re.search(
        r"zero_tolerance_failure_count integer GENERATED ALWAYS AS\s*"
        r"\((?P<expression>.*?)\)\s*STORED NOT NULL,",
        expand,
        flags=re.DOTALL,
    )
    assert generated_failure_count
    for failure_code in (
        "AI-FCT-001",
        "AI-FCT-004",
        "AI-POL-001",
        "AI-POL-002",
        "AI-FCT-003",
        "AI-POL-003",
        "AI-POL-005",
        "AI-POL-004",
    ):
        assert failure_code in generated_failure_count.group("expression")
    assert re.search(
        r"column_name = 'zero_tolerance_failure_count'\s*"
        r"AND is_generated = 'ALWAYS'\s*AND is_nullable = 'NO'",
        contract_prepare,
    )
    for metric_code in (
        "unsupported_critical_fact_rate",
        "fabricated_experience_rate",
        "rakuten_review_body_leakage_rate",
        "affiliate_bias_violation_rate",
        "product_identity_accuracy",
        "prompt_injection_follow_rate",
    ):
        assert metric_code in expand

    for helper in (
        "ai.canonical_metric_unit(text)",
        "ai.canonical_metric_direction(text)",
        "ai.canonical_regression_margin(text)",
        "ai.assert_regression_against_baseline(uuid, uuid)",
    ):
        assert f"REVOKE ALL ON FUNCTION {helper}" in expand
    for aggregate_contract in (
        "sum(proportion_numerator_count)::numeric",
        "/ sum(proportion_denominator_count)::numeric",
        "percentile_cont(0.95) WITHIN GROUP",
        "'HOLDOUT'), ('ADVERSARIAL'), ('REGRESSION')",
        "'CATEGORY'::text",
    ):
        assert aggregate_contract in expand
    for safety_contract in (
        "policy activation requires at least one bound rule version",
        "('latency_p95_ms')",
        "('cost_jpy_p95')",
        "grader.cost_latency.v1",
        "suite_risk = 'CRITICAL'",
        "NEW.maximum_canary_percent > 1",
        "other_canary.status = 'APPROVED_CANARY'",
        "pg_try_advisory_xact_lock(",
        "72004",
        "concurrent release transition for task %; retry",
    ):
        assert safety_contract in expand
    assert "ALTER COLUMN passed DROP NOT NULL" in expand
    for hardened_guard, search_path in (
        (
            "ai.guard_evaluation_run_mutation()",
            "SET search_path = pg_catalog, ai, pg_temp",
        ),
        (
            "ai.guard_evaluation_run_start_integrity()",
            "SET search_path = pg_catalog, ai, policy, pg_temp",
        ),
        (
            "ai.guard_evaluation_run_completion_evidence()",
            "SET search_path = pg_catalog, ai, pg_temp",
        ),
    ):
        guard_block = expand.split(
            f"CREATE FUNCTION {hardened_guard} RETURNS trigger",
            1,
        )[1].split("$$;", 1)[0]
        assert "SECURITY DEFINER" in guard_block
        assert search_path in guard_block
        assert f"REVOKE ALL ON FUNCTION {hardened_guard}" in expand

    for hardened_guard, expected_config in (
        (
            "ai.guard_evaluation_run_mutation()",
            "search_path=pg_catalog, ai, pg_temp",
        ),
        (
            "ai.guard_evaluation_run_start_integrity()",
            "search_path=pg_catalog, ai, policy, pg_temp",
        ),
        (
            "ai.guard_evaluation_run_completion_evidence()",
            "search_path=pg_catalog, ai, pg_temp",
        ),
    ):
        assert re.search(
            rf"'{re.escape(hardened_guard)}'::regprocedure,\s*"
            rf"ARRAY\['{re.escape(expected_config)}'\]::text\[\]",
            contract_prepare,
        )
    for live_catalog_guard in (
        "WHERE NOT proc.prosecdef",
        "proc.proowner <> (",
        "WHERE relation.oid = 'ai.evaluation_run'::regclass",
    ):
        assert live_catalog_guard in contract_prepare
    assert re.search(
        r"proc\.proconfig IS DISTINCT FROM\s+"
        r"guard_expectation\.expected_config",
        contract_prepare,
    )
    assert re.search(
        r"has_function_privilege\(\s*'raos_worker_rw',\s*"
        r"guard_expectation\.function_oid,\s*'EXECUTE'\s*\)",
        contract_prepare,
    )
    assert "ALTER COLUMN passed SET NOT NULL" in downgrade

    assert downgrade.index(
        "DROP FUNCTION ai.assert_regression_against_baseline(uuid, uuid)"
    ) < downgrade.index("DROP FUNCTION ai.canonical_metric_unit(text)")


def test_downgrade_is_guarded_and_forward_recovery_is_documented() -> None:
    downgrade = sql(MIGRATION_FILES[5])
    recovery = (DATABASE_ROOT / "forward-recovery.md").read_text(encoding="utf-8")

    assert "downgrade refused" in downgrade.lower()
    for table in GOVERNANCE_TABLES:
        assert table in downgrade
    for token in (
        "BLOCKED",
        "REJECTED",
        "AWAITING_HUMAN",
        "FAILED_RETRYABLE",
        "ROLLED_BACK",
    ):
        assert token in downgrade
    assert "forward" in recovery.lower()
    assert "2026073000" in recovery
