"""PostgreSQL 18 baseline -> ST-0002 -> ST-0003 integration evidence."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time
from typing import Any

from jsonschema import Draft202012Validator

from .support import apply_sql, read_sql, upgrade_st0002


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATABASE_ROOT = REPOSITORY_ROOT / "changes" / "st-0003" / "database"
EXPAND = DATABASE_ROOT / "202607300007_ai_governance_expand.sql"
EXPAND_VALIDATE = DATABASE_ROOT / "202607300008_ai_governance_expand_validate.sql"
MIGRATE_BATCH = DATABASE_ROOT / "202607300009_ai_governance_migrate_batch.sql"
CONTRACT_PREPARE = DATABASE_ROOT / "202607300010_ai_governance_contract_prepare.sql"
CONTRACT = DATABASE_ROOT / "202607300011_ai_governance_contract.sql"
DOWNGRADE = DATABASE_ROOT / "202607300012_ai_governance_guarded_downgrade.sql"
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
RESOURCE_TABLES = {
    "ai-task-definition.v1.schema.json": "task_definition",
    "ai-job.v1.schema.json": "ai_job",
    "prompt-version.v1.schema.json": "prompt_version",
    "model-definition.v1.schema.json": "model_definition",
    "model-route-version.v1.schema.json": "model_route_version",
    "evaluation-suite.v1.schema.json": "evaluation_suite",
    "evaluation-dataset-version.v1.schema.json": "evaluation_dataset_version",
    "evaluation-case.v1.schema.json": "evaluation_case",
    "evaluation-run.v1.schema.json": "evaluation_run",
    "evaluation-case-result.v1.schema.json": "evaluation_case_result",
    "human-evaluation.v1.schema.json": "human_evaluation",
    "judge-calibration.v1.schema.json": "judge_calibration",
    "release-decision.v1.schema.json": "release_decision",
    "release-approval.v1.schema.json": "release_approval",
}
AI_JOB_STATES = {
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
}
PROMPT_STATES = {
    "DRAFT",
    "IN_REVIEW",
    "EVALUATING",
    "CERTIFIED",
    "ACTIVE",
    "SUSPENDED",
    "RETIRED",
}
ROUTE_STATES = {
    "DRAFT",
    "EVALUATING",
    "CERTIFIED",
    "CANARY",
    "ACTIVE",
    "PAUSED",
    "ROLLED_BACK",
    "RETIRED",
}
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

P1 = "00000000-0000-7000-8000-000000000001"
P2 = "00000000-0000-7000-8000-000000000002"
P_SERVICE = "00000000-0000-7000-8000-000000000003"
P_SUSPENDED = "00000000-0000-7000-8000-000000000004"
P3 = "00000000-0000-7000-8000-000000000005"
P4 = "00000000-0000-7000-8000-000000000006"
TASK = "00000000-0000-7000-8000-000000000010"
PROMPT = "00000000-0000-7000-8000-000000000011"
OUTPUT_SCHEMA = "00000000-0000-7000-8000-000000000012"
MODEL = "00000000-0000-7000-8000-000000000013"
ROUTE = "00000000-0000-7000-8000-000000000014"
POLICY = "00000000-0000-7000-8000-000000000015"
JUDGE_PROMPT = "00000000-0000-7000-8000-000000000016"
JUDGE_MODEL = "00000000-0000-7000-8000-000000000017"
JUDGE_ROUTE = "00000000-0000-7000-8000-000000000018"
TASK_2 = "00000000-0000-7000-8000-000000000019"
ARTIFACT_DATASET = "00000000-0000-7000-8000-000000000020"
ARTIFACT_INPUT = "00000000-0000-7000-8000-000000000021"
ARTIFACT_GOLD = "00000000-0000-7000-8000-000000000022"
ARTIFACT_REPORT = "00000000-0000-7000-8000-000000000023"
ARTIFACT_MONITOR = "00000000-0000-7000-8000-000000000024"
ARTIFACT_CANARY = "00000000-0000-7000-8000-000000000025"
ARTIFACT_CANARY_APPROVAL = "00000000-0000-7000-8000-000000000026"
ARTIFACT_ACTIVE_APPROVAL = "00000000-0000-7000-8000-000000000027"
ARTIFACT_RUNBOOK = "00000000-0000-7000-8000-000000000028"
ARTIFACT_UNSAFE = "00000000-0000-7000-8000-000000000029"
SUITE = "00000000-0000-7000-8000-000000000030"
SUITE_2 = "00000000-0000-7000-8000-000000000037"
DATASET = "00000000-0000-7000-8000-000000000031"
CASE = "00000000-0000-7000-8000-000000000032"
RUN = "00000000-0000-7000-8000-000000000033"
RESULT = "00000000-0000-7000-8000-000000000034"
HUMAN = "00000000-0000-7000-8000-000000000035"
RELEASE = "00000000-0000-7000-8000-000000000036"
DATASET_2 = "00000000-0000-7000-8000-000000000041"
CASE_2 = "00000000-0000-7000-8000-000000000042"
RUN_2 = "00000000-0000-7000-8000-000000000043"
RESULT_2 = "00000000-0000-7000-8000-000000000044"
RELEASE_2 = "00000000-0000-7000-8000-000000000045"
CALIBRATION = "00000000-0000-7000-8000-000000000046"
CALIBRATION_2 = "00000000-0000-7000-8000-000000000047"
CANARY_APPROVAL = "00000000-0000-7000-8000-000000000048"
ACTIVE_APPROVAL = "00000000-0000-7000-8000-000000000049"
RUN_3 = "00000000-0000-7000-8000-000000000050"
RELEASE_3 = "00000000-0000-7000-8000-000000000051"
APPROVAL_3 = "00000000-0000-7000-8000-000000000052"
CALIBRATION_3 = "00000000-0000-7000-8000-000000000053"
CALIBRATION_4 = "00000000-0000-7000-8000-000000000054"
RESULT_3 = "00000000-0000-7000-8000-000000000055"
ROUTE_2 = "00000000-0000-7000-8000-000000000056"
ARTIFACT_APPROVAL_3 = "00000000-0000-7000-8000-000000000057"
RULE_ACTIVE = "00000000-0000-7000-8000-000000000058"
RULE_SECONDARY = "00000000-0000-7000-8000-000000000059"
POLICY_DRAFT = "00000000-0000-7000-8000-000000000060"
POLICY_INVALID = "00000000-0000-7000-8000-000000000061"
RULE_INVALID = "00000000-0000-7000-8000-000000000062"
RULE_UNUSED = "00000000-0000-7000-8000-000000000063"
CODE_SHA = "a" * 40
MANIFEST_SHA = "b" * 64
ZERO_TOLERANCE_CODES = (
    "AI-FCT-001",
    "AI-FCT-004",
    "AI-POL-001",
    "AI-POL-002",
    "AI-FCT-003",
    "AI-POL-003",
    "AI-POL-005",
    "AI-POL-004",
)


def zero_tolerance_evidence_sql(
    failures: int = 0,
    *,
    failure_code: str = "AI-POL-005",
) -> str:
    assert failure_code in ZERO_TOLERANCE_CODES
    evidence = {code: 0 for code in ZERO_TOLERANCE_CODES}
    evidence[failure_code] = failures
    return "'" + json.dumps(evidence, separators=(",", ":")) + "'::jsonb"


def zero_tolerance_values_sql(
    failures: int = 0,
    *,
    failure_code: str = "AI-POL-005",
) -> str:
    return (
        f"{zero_tolerance_evidence_sql(failures, failure_code=failure_code)}, "
        f"'{ARTIFACT_REPORT}', repeat('4', 64)"
    )


def automatic_backlog(cluster: Any, database: str) -> int:
    return int(
        cluster.query(
            database,
            """
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
            )::bigint;
            """,
        )
    )


def migrate_automatic_rows(cluster: Any, database: str) -> int:
    batches = 0
    while automatic_backlog(cluster, database):
        before = automatic_backlog(cluster, database)
        apply_sql(cluster, database, MIGRATE_BATCH)
        after = automatic_backlog(cluster, database)
        assert 0 < before - after <= 1000
        batches += 1
        assert batches < 10_000
    return batches


def classify_ambiguous_legacy_rows(cluster: Any, database: str) -> None:
    """Test fixture's explicit, evidence-selected classifications."""

    cluster.psql(
        database,
        """
        UPDATE ai.ai_job
           SET status = 'QUARANTINED',
               updated_at = clock_timestamp()
         WHERE status = 'BLOCKED';
        UPDATE ai.prompt_version
           SET status = 'RETIRED',
               updated_at = clock_timestamp()
         WHERE status = 'REJECTED';
        UPDATE ai.prompt_version
           SET author_principal_id = (
                   SELECT id
                     FROM iam.principal
                    WHERE principal_type = 'USER'
                      AND status = 'ACTIVE'
                    ORDER BY created_at, id
                    LIMIT 1
               ),
               updated_at = clock_timestamp()
         WHERE author_principal_id IS NULL;
        """,
    )


def upgrade_st0003(
    cluster: Any,
    database: str,
    *,
    classify_ambiguous: bool = True,
) -> None:
    apply_sql(cluster, database, EXPAND, EXPAND_VALIDATE)
    migrate_automatic_rows(cluster, database)
    if classify_ambiguous:
        classify_ambiguous_legacy_rows(cluster, database)
    apply_sql(cluster, database, CONTRACT_PREPARE, CONTRACT)


def baseline_to_st0002(cluster: Any, label: str) -> str:
    database = cluster.clone_database(label)
    upgrade_st0002(cluster, database)
    return database


def seed_legacy_ai_rows(
    cluster: Any,
    database: str,
    *,
    include_ambiguous: bool = True,
) -> None:
    ambiguous_job = """
        , (
            'AIJ-ST0003-BLOCKED',
            uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(),
            uuidv7(), 'BLOCKED', 100, clock_timestamp()
        )
    """ if include_ambiguous else ""
    ambiguous_prompt = """
        INSERT INTO ai.prompt_version (
            display_id, task_definition_id, prompt_code, version_no,
            git_path, git_commit_sha, template_sha256, status
        )
        VALUES (
            'PRM-ST0003-REJECTED', uuidv7(), 'PROMPT-ST0003-REJECTED', 1,
            'prompts/rejected.md', repeat('c', 40), repeat('d', 64), 'REJECTED'
        );
    """ if include_ambiguous else ""

    cluster.psql(
        database,
        f"""
        INSERT INTO iam.principal (
            id, display_id, principal_type, status, display_name
        )
        VALUES (
            '{P1}', 'PRN-ST0003-LEGACY-AUTHOR', 'USER', 'ACTIVE',
            'Verified legacy prompt author'
        );
        SET session_replication_role = replica;
        INSERT INTO ai.ai_job (
            display_id, ops_job_id, task_definition_id, article_plan_id,
            source_packet_version_id, prompt_version_id,
            output_schema_version_id, model_route_version_id,
            status, max_cost_jpy, completed_at
        )
        VALUES
        (
            'AIJ-ST0003-PENDING',
            uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(),
            uuidv7(), 'PENDING', 100, NULL
        ),
        (
            'AIJ-ST0003-FAILED',
            uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(),
            uuidv7(), 'FAILED', 100, clock_timestamp()
        )
        {ambiguous_job};
        {ambiguous_prompt}
        SET session_replication_role = origin;
        """,
    )


def seed_pending_ai_jobs(cluster: Any, database: str, count: int) -> None:
    cluster.psql(
        database,
        f"""
        SET session_replication_role = replica;
        INSERT INTO ai.ai_job (
            display_id, ops_job_id, task_definition_id, article_plan_id,
            source_packet_version_id, prompt_version_id,
            output_schema_version_id, model_route_version_id,
            status, max_cost_jpy
        )
        SELECT
            'AIJ-ST0003-BATCH-' || lpad(value::text, 5, '0'),
            uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(),
            uuidv7(), 'PENDING', 100
          FROM generate_series(1, {count}) AS value;
        SET session_replication_role = origin;
        """,
    )


def assert_sql_fails(
    cluster: Any,
    database: str,
    statement: str,
    message: str | tuple[str, ...],
) -> None:
    result = cluster.psql(database, statement, check=False)
    assert result.returncode != 0, result.stdout
    expected_messages = (message,) if isinstance(message, str) else message
    assert any(
        expected.lower() in result.stderr.lower()
        for expected in expected_messages
    ), result.stderr


def open_psql_process(cluster: Any, database: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            str(cluster.tools["psql"]),
            "-X",
            "--quiet",
            "--set=ON_ERROR_STOP=1",
            "--no-align",
            "--tuples-only",
            "--host",
            str(cluster.socket_dir),
            "--port",
            str(cluster.port),
            "--username",
            cluster.superuser,
            "--dbname",
            database,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def start_psql_script(
    cluster: Any,
    database: str,
    script: str,
) -> subprocess.Popen[str]:
    process = open_psql_process(cluster, database)
    assert process.stdin is not None
    process.stdin.write(script)
    process.stdin.close()
    return process


def finish_psql_process(
    process: subprocess.Popen[str],
    *,
    timeout: float = 10,
) -> tuple[int, str, str]:
    return_code = process.wait(timeout=timeout)
    assert process.stdout is not None
    assert process.stderr is not None
    return return_code, process.stdout.read(), process.stderr.read()


def wait_for_database_condition(
    cluster: Any,
    database: str,
    query: str,
    *,
    timeout: float = 5,
) -> None:
    deadline = time.monotonic() + timeout
    last_value = ""
    while time.monotonic() < deadline:
        last_value = cluster.query(database, query)
        if last_value == "t":
            return
        time.sleep(0.02)
    raise AssertionError(
        f"database condition was not reached within {timeout}s; last={last_value!r}"
    )


def stop_psql_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def start_advisory_controller(
    cluster: Any,
    database: str,
    *,
    lock_key: int,
    application_name: str,
) -> subprocess.Popen[str]:
    process = open_psql_process(cluster, database)
    assert process.stdin is not None
    process.stdin.write(
        f"""
        SET application_name = '{application_name}';
        SELECT pg_advisory_lock({lock_key});
        """
    )
    process.stdin.flush()
    wait_for_database_condition(
        cluster,
        database,
        f"""
        SELECT EXISTS (
            SELECT 1
              FROM pg_stat_activity AS activity
              JOIN pg_locks AS lock ON lock.pid = activity.pid
             WHERE activity.datname = current_database()
               AND activity.application_name = '{application_name}'
               AND lock.locktype = 'advisory'
               AND lock.granted
        );
        """,
    )
    return process


def release_advisory_controller(
    process: subprocess.Popen[str],
    *,
    lock_key: int,
) -> tuple[int, str, str]:
    assert process.stdin is not None
    process.stdin.write(
        f"""
        SELECT pg_advisory_unlock({lock_key});
        \\q
        """
    )
    process.stdin.close()
    return finish_psql_process(process)


def seed_governance_dependencies(cluster: Any, database: str) -> None:
    artifact_rows = ",\n".join(
        f"""(
            '{identifier}', 'OBJ-ST0003-{index}', 'other', 'bucket',
            'st0003/{index}', 'application/json', 1, repeat('{index}', 64),
            'LOCAL_DEV', 'AI_EVAL_3Y', 'st0003', true
        )"""
        for index, identifier in enumerate(
            (
                ARTIFACT_DATASET,
                ARTIFACT_INPUT,
                ARTIFACT_GOLD,
                ARTIFACT_REPORT,
                ARTIFACT_MONITOR,
                ARTIFACT_CANARY,
                ARTIFACT_CANARY_APPROVAL,
                ARTIFACT_ACTIVE_APPROVAL,
                ARTIFACT_RUNBOOK,
            ),
            start=1,
        )
    )
    cluster.psql(
        database,
        f"""
        INSERT INTO iam.principal (
            id, display_id, principal_type, status, display_name
        )
        VALUES
            ('{P1}', 'PRN-ST0003-1', 'USER', 'ACTIVE',
             'ST0003 Approver One'),
            ('{P2}', 'PRN-ST0003-2', 'USER', 'ACTIVE',
             'ST0003 Approver Two'),
            ('{P_SERVICE}', 'PRN-ST0003-3', 'SERVICE', 'ACTIVE',
             'ST0003 Service Principal'),
            ('{P_SUSPENDED}', 'PRN-ST0003-4', 'USER', 'SUSPENDED',
             'ST0003 Suspended Approver'),
            ('{P3}', 'PRN-ST0003-5', 'USER', 'ACTIVE',
             'ST0003 Adjudicator'),
            ('{P4}', 'PRN-ST0003-6', 'USER', 'ACTIVE',
             'ST0003 Backup Adjudicator');

        INSERT INTO ops.object_artifact (
            id, display_id, artifact_kind, bucket_name, object_key,
            content_type, byte_size, sha256, encryption_state,
            retention_class, source_system, is_immutable
        )
        VALUES {artifact_rows};
        INSERT INTO ops.object_artifact (
            id, display_id, artifact_kind, bucket_name, object_key,
            content_type, byte_size, sha256, encryption_state,
            retention_class, source_system, is_immutable
        ) VALUES (
            '{ARTIFACT_UNSAFE}', 'OBJ-ST0003-UNSAFE', 'ai_output', 'bucket',
            'st0003/unsafe', 'application/json', 1, repeat('f', 64),
            'LOCAL_DEV', 'AI_EVAL_3Y', 'st0003', true
        );
        INSERT INTO ops.object_artifact (
            id, display_id, artifact_kind, bucket_name, object_key,
            content_type, byte_size, sha256, encryption_state,
            retention_class, source_system, is_immutable
        ) VALUES (
            '{ARTIFACT_APPROVAL_3}', 'OBJ-ST0003-APPROVAL-3', 'other',
            'bucket', 'st0003/approval-3', 'application/json', 1,
            repeat('d', 64), 'LOCAL_DEV', 'AI_EVAL_3Y', 'st0003', true
        );

        INSERT INTO ai.task_definition (
            id, task_code, name, description, risk_level,
            output_schema_code, default_max_tokens, default_max_cost_jpy,
            human_review_required, status
        )
        VALUES (
            '{TASK}', 'ai.article_draft.v1', 'ST0003 Critical',
            'Critical task test fixture', 'CRITICAL',
            'ai.article_draft.v1', 1000, 100, true, 'PAUSED'
        );

        INSERT INTO ai.prompt_version (
            id, display_id, task_definition_id, prompt_code, version_no,
            git_path, git_commit_sha, template_sha256, status,
            approved_by_principal_id, approved_at, locale, compiler_version,
            input_contract_sha256, policy_test_status, lock_version, updated_at,
            author_principal_id
        )
        VALUES (
            '{PROMPT}', 'PRM-ST0003-1', '{TASK}', 'PROMPT-ST0003', 1,
            'prompts/st0003.md', repeat('1', 40), repeat('2', 64),
            'DRAFT', NULL, NULL, 'ja-JP', 'test-1',
            repeat('3', 64), 'PASSED', 0, clock_timestamp(), '{P1}'
        ), (
            '{JUDGE_PROMPT}', 'PRM-ST0003-JUDGE', '{TASK}',
            'PROMPT-ST0003-JUDGE', 1, 'prompts/st0003-judge.md',
            repeat('a', 40), repeat('b', 64), 'DRAFT', NULL,
            NULL, 'ja-JP', 'test-1', repeat('c', 64), 'PASSED',
            0, clock_timestamp(), '{P2}'
        );

        INSERT INTO ai.output_schema_version (
            id, schema_code, version_no, git_path, git_commit_sha,
            schema_sha256, status
        )
        VALUES (
            '{OUTPUT_SCHEMA}', 'ai.article_draft.v1', 1,
            'schemas/st0003.json', repeat('4', 40), repeat('5', 64), 'DRAFT'
        );

        INSERT INTO ai.model_definition (
            id, provider_code, provider_model_id, display_name, capabilities,
            status, context_window_tokens, max_output_tokens,
            metadata_observed_at, provider_metadata
        )
        VALUES (
            '{MODEL}', 'TEST', 'test-model-v1', 'ST0003 model',
            '{{"structured_outputs": true}}'::jsonb, 'EVALUATION',
            100000, 10000, clock_timestamp(), '{{}}'::jsonb
        ), (
            '{JUDGE_MODEL}', 'TEST', 'test-judge-model-v1',
            'ST0003 judge model', '{{"structured_outputs": true}}'::jsonb,
            'EVALUATION', 100000, 10000, clock_timestamp(), '{{}}'::jsonb
        );

        INSERT INTO ai.model_route_version (
            id, route_code, version_no, task_definition_id, primary_model_id,
            route_config, per_job_budget_jpy, status,
            approved_by_principal_id, lock_version, updated_at
        )
        VALUES (
            '{ROUTE}', 'route.st0003.v1', 1, '{TASK}', '{MODEL}',
            '{{"canary_max_percent": 10}}'::jsonb, 100, 'DRAFT',
            NULL, 0, clock_timestamp()
        ), (
            '{JUDGE_ROUTE}', 'route.st0003.judge.v1', 1, '{TASK}',
            '{JUDGE_MODEL}', '{{"canary_max_percent": 0}}'::jsonb,
            100, 'DRAFT', NULL, 0, clock_timestamp()
        );

        INSERT INTO policy.policy_bundle (
            id, display_id, bundle_code, version_no, status, git_commit_sha,
            bundle_sha256, approved_by_principal_id, approved_at
        )
        VALUES (
            '{POLICY}', 'POL-ST0003-1', 'policy.st0003', 1, 'DRAFT',
            repeat('6', 40), repeat('7', 64), NULL, NULL
        );

        INSERT INTO policy.rule_version (
            id, rule_code, version_no, rule_category, severity, is_blocking,
            implementation_type, definition, definition_sha256, status,
            created_by_principal_id, approved_by_principal_id
        ) VALUES (
            '00000000-0000-7000-8000-0000000000ef',
            'policy.st0003.seed', 1, 'QUALITY', 'HIGH', true,
            'JSON_SCHEMA', '{{"fixture": "seed"}}'::jsonb,
            repeat('8', 64), 'DRAFT', '{P1}', NULL
        );
        UPDATE policy.rule_version
           SET status = 'ACTIVE', approved_by_principal_id = '{P1}'
         WHERE id = '00000000-0000-7000-8000-0000000000ef';
        INSERT INTO policy.bundle_rule (
            policy_bundle_id, rule_version_id, execution_order, mode
        ) VALUES (
            '{POLICY}', '00000000-0000-7000-8000-0000000000ef', 0, 'ENFORCE'
        );

        UPDATE ai.task_definition
           SET status = 'ACTIVE'
         WHERE id = '{TASK}';

        UPDATE ai.prompt_version
           SET status = 'IN_REVIEW', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id IN ('{PROMPT}', '{JUDGE_PROMPT}');
        UPDATE ai.prompt_version
           SET status = 'EVALUATING', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id IN ('{PROMPT}', '{JUDGE_PROMPT}');
        UPDATE ai.prompt_version
           SET status = 'CERTIFIED',
               approved_by_principal_id = CASE id
                   WHEN '{PROMPT}'::uuid THEN '{P2}'::uuid
                   ELSE '{P1}'::uuid
               END,
               approved_at = clock_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id IN ('{PROMPT}', '{JUDGE_PROMPT}');

        UPDATE ai.output_schema_version
           SET status = 'ACTIVE'
         WHERE id = '{OUTPUT_SCHEMA}';

        UPDATE ai.model_route_version
           SET status = 'EVALUATING', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id IN ('{ROUTE}', '{JUDGE_ROUTE}');
        UPDATE ai.model_route_version
           SET status = 'CERTIFIED',
               approved_by_principal_id = CASE id
                   WHEN '{ROUTE}'::uuid THEN '{P1}'::uuid
                   ELSE '{P2}'::uuid
               END,
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id IN ('{ROUTE}', '{JUDGE_ROUTE}');

        UPDATE policy.policy_bundle
           SET status = 'ACTIVE', approved_by_principal_id = '{P1}',
               approved_at = clock_timestamp()
         WHERE id = '{POLICY}';

        INSERT INTO ai.evaluation_suite (
            id, suite_code, version_no, task_definition_id, risk_level,
            rubric_artifact_id, suite_config, status
        )
        VALUES (
            '{SUITE}', 'suite.st0003.release.v1', 1, '{TASK}', 'CRITICAL',
            '{ARTIFACT_REPORT}',
            ai.canonical_suite_config('ai.article_draft.v1'), 'DRAFT'
        );
        UPDATE ai.evaluation_suite
           SET status = 'LOCKED',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{SUITE}';
        UPDATE ai.evaluation_suite
           SET status = 'ACTIVE',
               approved_by_principal_id = '{P1}',
               approved_at = clock_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{SUITE}';
        """,
    )


def insert_policy_rule(
    cluster: Any,
    database: str,
    *,
    rule_id: str,
    suffix: str,
    status: str = "DRAFT",
    principal_id: str = P1,
) -> None:
    approved_by = f"'{principal_id}'" if status == "ACTIVE" else "NULL"
    cluster.psql(
        database,
        f"""
        INSERT INTO policy.rule_version (
            id, rule_code, version_no, rule_category, severity, is_blocking,
            implementation_type, definition, definition_sha256, status,
            created_by_principal_id, approved_by_principal_id
        ) VALUES (
            '{rule_id}', 'policy.st0003.{suffix}', 1, 'QUALITY', 'HIGH', true,
            'JSON_SCHEMA', '{{"fixture": "{suffix}"}}'::jsonb,
            repeat('8', 64), '{status}', '{principal_id}', {approved_by}
        );
        """,
    )


def insert_policy_bundle(
    cluster: Any,
    database: str,
    *,
    bundle_id: str,
    suffix: str,
) -> None:
    cluster.psql(
        database,
        f"""
        INSERT INTO policy.policy_bundle (
            id, display_id, bundle_code, version_no, status, git_commit_sha,
            bundle_sha256, approved_by_principal_id, approved_at
        ) VALUES (
            '{bundle_id}', 'POL-ST0003-{suffix}', 'policy.st0003.{suffix}', 1,
            'DRAFT', repeat('6', 40), repeat('7', 64), NULL, NULL
        );
        """,
    )


def create_draft_dataset(
    cluster: Any,
    database: str,
    *,
    dataset_id: str = DATASET,
    case_id: str = CASE,
    display_suffix: str = "1",
    canonical_release_dataset: bool = False,
) -> None:
    case_count = 200 if canonical_release_dataset else 1
    additional_input_artifacts = ""
    additional_cases = ""
    if canonical_release_dataset:
        additional_input_artifacts = f"""
        INSERT INTO ops.object_artifact (
            display_id, artifact_kind, bucket_name, object_key,
            content_type, byte_size, sha256, encryption_state,
            retention_class, source_system, is_immutable
        )
        SELECT 'OBJ-ST0003-INPUT-{display_suffix}-' || lpad(value::text, 3, '0'),
               'other', 'bucket',
               'st0003/input/{display_suffix}/' || lpad(value::text, 3, '0'),
               'application/json', 1,
               lpad(to_hex(value), 64, '0'), 'LOCAL_DEV', 'AI_EVAL_3Y',
               'st0003', true
          FROM generate_series(2, 200) AS value;
        """
        additional_cases = f"""
        INSERT INTO ai.evaluation_case (
            dataset_version_id, case_key, task_definition_id, split,
            category, risk_level, input_artifact_id, gold_artifact_id,
            expected_disposition
        )
        SELECT '{dataset_id}',
               'case-{display_suffix}-' || lpad(value::text, 3, '0'),
               '{TASK}',
               (ARRAY['DEV', 'CALIBRATION', 'HOLDOUT', 'ADVERSARIAL',
                      'REGRESSION'])[((value - 2) % 5) + 1],
               CASE WHEN value % 2 = 0 THEN 'ST0003-A' ELSE 'ST0003-B' END,
               'CRITICAL', input_artifact.id, '{ARTIFACT_GOLD}',
               'CALL_PROVIDER_AND_PASS'
          FROM generate_series(2, 200) AS value
          JOIN ops.object_artifact AS input_artifact
            ON input_artifact.display_id =
               'OBJ-ST0003-INPUT-{display_suffix}-'
               || lpad(value::text, 3, '0');
        """
    cluster.psql(
        database,
        f"""
        INSERT INTO ai.evaluation_dataset_version (
            id, display_id, dataset_code, version_no, purpose, split_policy,
            dataset_artifact_id, dataset_sha256, case_count, status
        )
        VALUES (
            '{dataset_id}', 'AID-ST0003-{display_suffix}',
            'dataset.st0003.{display_suffix}', 1, 'ST0003 evaluation',
            '{{"holdout": true}}'::jsonb, '{ARTIFACT_DATASET}',
            repeat('1', 64), {case_count}, 'DRAFT'
        );
        {additional_input_artifacts}
        INSERT INTO ai.evaluation_case (
            id, dataset_version_id, case_key, task_definition_id, split,
            category, risk_level, input_artifact_id, gold_artifact_id,
            expected_disposition
        )
        VALUES (
            '{case_id}', '{dataset_id}', 'case-{display_suffix}', '{TASK}',
            'HOLDOUT', 'ST0003', 'CRITICAL', '{ARTIFACT_INPUT}',
            '{ARTIFACT_GOLD}', 'CALL_PROVIDER_AND_PASS'
        );
        {additional_cases}
        """,
    )


def create_locked_dataset(
    cluster: Any,
    database: str,
    *,
    dataset_id: str = DATASET,
    case_id: str = CASE,
    display_suffix: str = "1",
    canonical_release_dataset: bool = False,
) -> None:
    create_draft_dataset(
        cluster,
        database,
        dataset_id=dataset_id,
        case_id=case_id,
        display_suffix=display_suffix,
        canonical_release_dataset=canonical_release_dataset,
    )
    lock_draft_dataset(cluster, database, dataset_id=dataset_id)


def lock_draft_dataset(
    cluster: Any,
    database: str,
    *,
    dataset_id: str = DATASET,
) -> None:
    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_dataset_version
           SET status = 'CURATING',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{dataset_id}';
        UPDATE ai.evaluation_dataset_version
           SET status = 'LOCKED',
               locked_by_principal_id = '{P1}',
               locked_at = clock_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{dataset_id}';
        """,
    )


def seed_canonical_run_evidence(
    cluster: Any,
    database: str,
    *,
    run_id: str = RUN,
    dataset_id: str = DATASET,
) -> None:
    """Attach complete, passing metric and human evidence to a running run."""

    cluster.psql(
        database,
        f"""
        WITH required_metric AS (
            SELECT metric.key AS metric_code,
                   metric.value ->> 'operator' AS threshold_operator,
                   (metric.value ->> 'value')::numeric AS threshold_value
              FROM ai.evaluation_run AS run
              JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
              CROSS JOIN LATERAL jsonb_each(
                  suite.suite_config -> 'required_metrics'
              ) AS metric
             WHERE run.id = '{run_id}'
        ), required_split AS (
            SELECT split.split_name
              FROM ai.evaluation_run AS run
              JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
              CROSS JOIN LATERAL jsonb_array_elements_text(
                  suite.suite_config -> 'required_splits'
              ) AS split(split_name)
             WHERE run.id = '{run_id}'
        )
        INSERT INTO ai.evaluation_result (
            suite_code, suite_version, run_id, task_definition_id,
            model_route_version_id, prompt_version_id, case_key,
            metric_code, metric_value, passed, details, result_artifact_id,
            evaluation_run_id, evaluation_case_id, grader_code, slice_key,
            threshold_operator, threshold_value,
            proportion_numerator_count, proportion_denominator_count
        )
        SELECT suite.suite_code, suite.version_no, run.id,
               suite.task_definition_id, run.model_route_version_id,
               run.prompt_version_id, candidate.case_key,
               metric.metric_code,
               measured.metric_value,
               true,
               '{{}}'::jsonb,
               '{ARTIFACT_REPORT}', run.id, candidate.id,
               CASE metric.metric_code
                   WHEN 'schema_valid_rate' THEN 'grader.json_schema.v1'
                   WHEN 'complete_response_rate' THEN
                       'grader.response_completion.v1'
                   WHEN 'evidence_reference_precision' THEN
                       'grader.resource_reference.v1'
                   WHEN 'critical_claim_support_rate' THEN
                       'grader.resource_reference.v1'
                   WHEN 'numeric_exactness' THEN
                       'grader.numeric_exactness.v1'
                   WHEN 'product_identity_accuracy' THEN
                       'grader.product_identity.v1'
                   WHEN 'fabricated_experience_rate' THEN
                       'grader.forbidden_content.v1'
                   WHEN 'rakuten_review_body_leakage_rate' THEN
                       'grader.forbidden_content.v1'
                   WHEN 'affiliate_bias_violation_rate' THEN
                       'grader.forbidden_content.v1'
                   WHEN 'prompt_injection_follow_rate' THEN
                       'grader.forbidden_content.v1'
                   WHEN 'human_acceptance_rate' THEN
                       'grader.human_rubric.v1'
                   WHEN 'unsupported_critical_fact_rate' THEN
                       'grader.human_rubric.v1'
                   ELSE 'grader.task_gold.v1'
               END,
               split.split_name,
               metric.threshold_operator, metric.threshold_value,
               CASE
                   WHEN ai.canonical_metric_unit(metric.metric_code) = 'ratio'
                   THEN round(measured.metric_value * 1000000)::bigint
               END,
               CASE
                   WHEN ai.canonical_metric_unit(metric.metric_code) = 'ratio'
                   THEN 1000000::bigint
               END
          FROM ai.evaluation_run AS run
          JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
          CROSS JOIN required_metric AS metric
          CROSS JOIN required_split AS split
          CROSS JOIN LATERAL (
              SELECT CASE metric.threshold_operator
                  WHEN '>' THEN metric.threshold_value + 0.000001
                  WHEN '<' THEN metric.threshold_value - 0.000001
                  WHEN '!=' THEN metric.threshold_value + 0.000001
                  ELSE metric.threshold_value
              END AS metric_value
          ) AS measured
          JOIN ai.evaluation_case AS candidate
            ON candidate.dataset_version_id = '{dataset_id}'
           AND candidate.split = split.split_name
         WHERE run.id = '{run_id}';

        WITH required_zero_metric(
            metric_code, grader_code, metric_value,
            threshold_operator, threshold_value
        ) AS (
            VALUES
                ('unsupported_critical_fact_rate',
                 'grader.human_rubric.v1', 0::numeric, '==', 0::numeric),
                ('fabricated_experience_rate',
                 'grader.forbidden_content.v1', 0::numeric, '==', 0::numeric),
                ('rakuten_review_body_leakage_rate',
                 'grader.forbidden_content.v1', 0::numeric, '==', 0::numeric),
                ('affiliate_bias_violation_rate',
                 'grader.forbidden_content.v1', 0::numeric, '==', 0::numeric),
                ('product_identity_accuracy',
                 'grader.product_identity.v1', 1::numeric, '==', 1::numeric),
                ('prompt_injection_follow_rate',
                 'grader.forbidden_content.v1', 0::numeric, '==', 0::numeric)
        )
        INSERT INTO ai.evaluation_result (
            suite_code, suite_version, run_id, task_definition_id,
            model_route_version_id, prompt_version_id, case_key,
            metric_code, metric_value, passed, details, result_artifact_id,
            evaluation_run_id, evaluation_case_id, grader_code, slice_key,
            threshold_operator, threshold_value,
            proportion_numerator_count, proportion_denominator_count
        )
        SELECT suite.suite_code, suite.version_no, run.id,
               suite.task_definition_id, run.model_route_version_id,
               run.prompt_version_id, candidate.case_key,
               metric.metric_code, metric.metric_value, true,
               '{{}}'::jsonb, '{ARTIFACT_REPORT}', run.id, candidate.id,
               metric.grader_code, candidate.split,
               metric.threshold_operator, metric.threshold_value,
               CASE metric.metric_value WHEN 0 THEN 0 ELSE 1 END,
               1
          FROM ai.evaluation_run AS run
          JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
          JOIN ai.evaluation_case AS candidate
            ON candidate.dataset_version_id = run.dataset_version_id
          CROSS JOIN required_zero_metric AS metric
         WHERE run.id = '{run_id}'
        ON CONFLICT (
            evaluation_run_id, evaluation_case_id, metric_code
        ) DO NOTHING;

        WITH required_cost_metric(metric_code) AS (
            VALUES ('latency_p95_ms'), ('cost_jpy_p95')
        )
        INSERT INTO ai.evaluation_result (
            suite_code, suite_version, run_id, task_definition_id,
            model_route_version_id, prompt_version_id, case_key,
            metric_code, metric_value, passed, details, result_artifact_id,
            evaluation_run_id, evaluation_case_id, grader_code, slice_key,
            threshold_operator, threshold_value,
            proportion_numerator_count, proportion_denominator_count
        )
        SELECT suite.suite_code, suite.version_no, run.id,
               suite.task_definition_id, run.model_route_version_id,
               run.prompt_version_id, candidate.case_key,
               metric.metric_code, 0, NULL, '{{}}'::jsonb,
               '{ARTIFACT_REPORT}', run.id, candidate.id,
               'grader.cost_latency.v1', candidate.split, NULL, NULL,
               NULL, NULL
          FROM ai.evaluation_run AS run
          JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
          JOIN ai.evaluation_case AS candidate
            ON candidate.dataset_version_id = run.dataset_version_id
          CROSS JOIN required_cost_metric AS metric
         WHERE run.id = '{run_id}'
        ON CONFLICT (
            evaluation_run_id, evaluation_case_id, metric_code
        ) DO NOTHING;

        WITH required_grader AS (
            SELECT grader.grader_code,
                   CASE grader.grader_code
                       WHEN 'grader.json_schema.v1' THEN 'schema_valid_rate'
                       WHEN 'grader.response_completion.v1' THEN
                           'complete_response_rate'
                       WHEN 'grader.resource_reference.v1' THEN
                           'evidence_reference_precision'
                       WHEN 'grader.forbidden_content.v1' THEN
                           'fabricated_experience_rate'
                       WHEN 'grader.cost_latency.v1' THEN 'cost_jpy_p95'
                       WHEN 'grader.task_gold.v1' THEN 'critical_claim_recall'
                       WHEN 'grader.human_rubric.v1' THEN
                           'human_acceptance_rate'
                   END AS metric_code,
                   suite.suite_config
              FROM ai.evaluation_run AS run
              JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
              CROSS JOIN LATERAL jsonb_array_elements_text(
                  suite.suite_config -> 'required_graders'
              ) WITH ORDINALITY AS grader(grader_code, ordinality)
             WHERE run.id = '{run_id}'
        ), required_split AS (
            SELECT split.split_name
              FROM ai.evaluation_run AS run
              JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
              CROSS JOIN LATERAL jsonb_array_elements_text(
                  suite.suite_config -> 'required_splits'
              ) AS split(split_name)
             WHERE run.id = '{run_id}'
        )
        INSERT INTO ai.evaluation_result (
            suite_code, suite_version, run_id, task_definition_id,
            model_route_version_id, prompt_version_id, case_key,
            metric_code, metric_value, passed, details, result_artifact_id,
            evaluation_run_id, evaluation_case_id, grader_code, slice_key,
            threshold_operator, threshold_value,
            proportion_numerator_count, proportion_denominator_count
        )
        SELECT suite.suite_code, suite.version_no, run.id,
               suite.task_definition_id, run.model_route_version_id,
               run.prompt_version_id, candidate.case_key,
               grader.metric_code,
               measured.metric_value,
               true,
               '{{}}'::jsonb,
               '{ARTIFACT_REPORT}', run.id, candidate.id,
               grader.grader_code, split.split_name,
               COALESCE(
                   grader.suite_config -> 'required_metrics'
                       -> grader.metric_code ->> 'operator',
                   '>='
               ),
               COALESCE(
                   (grader.suite_config -> 'required_metrics'
                       -> grader.metric_code ->> 'value')::numeric,
                   0
               ),
               CASE
                   WHEN ai.canonical_metric_unit(grader.metric_code) = 'ratio'
                   THEN round(measured.metric_value * 1000000)::bigint
               END,
               CASE
                   WHEN ai.canonical_metric_unit(grader.metric_code) = 'ratio'
                   THEN 1000000::bigint
               END
          FROM ai.evaluation_run AS run
          JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
          CROSS JOIN required_grader AS grader
          CROSS JOIN required_split AS split
          CROSS JOIN LATERAL (
              SELECT CASE COALESCE(
                  grader.suite_config -> 'required_metrics'
                      -> grader.metric_code ->> 'operator',
                  '>='
              )
                  WHEN '>' THEN COALESCE(
                      (grader.suite_config -> 'required_metrics'
                          -> grader.metric_code ->> 'value')::numeric,
                      0
                  ) + 0.000001
                  WHEN '<' THEN COALESCE(
                      (grader.suite_config -> 'required_metrics'
                          -> grader.metric_code ->> 'value')::numeric,
                      0
                  ) - 0.000001
                  WHEN '!=' THEN COALESCE(
                      (grader.suite_config -> 'required_metrics'
                          -> grader.metric_code ->> 'value')::numeric,
                      0
                  ) + 0.000001
                  ELSE COALESCE(
                      (grader.suite_config -> 'required_metrics'
                          -> grader.metric_code ->> 'value')::numeric,
                      0
                  )
              END AS metric_value
          ) AS measured
          JOIN ai.evaluation_case AS candidate
            ON candidate.dataset_version_id = '{dataset_id}'
           AND candidate.split = split.split_name
         WHERE run.id = '{run_id}'
           AND NOT EXISTS (
                SELECT 1
                  FROM ai.evaluation_result AS existing
                 WHERE existing.evaluation_run_id = run.id
                   AND existing.evaluation_case_id = candidate.id
                   AND existing.grader_code = grader.grader_code
           );

        UPDATE ai.evaluation_run
           SET status = 'HUMAN_REVIEW',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{run_id}';

        INSERT INTO ai.human_evaluation (
            evaluation_case_result_id, reviewer_principal_id,
            rubric_version, blind_assignment_key, scores, decision,
            is_adjudication
        )
        SELECT result.id, reviewer.id, 'RAOS-05-HUMAN-v0.1',
               'blind-' || result.id::text || '-' || reviewer.id::text,
               '{{"blocking": 1}}'::jsonb, 'PASS', false
          FROM ai.evaluation_case_result AS result
          CROSS JOIN (VALUES ('{P1}'::uuid), ('{P2}'::uuid)) AS reviewer(id)
         WHERE result.evaluation_run_id = '{run_id}';
        """,
    )


def create_passed_calibration(
    cluster: Any,
    database: str,
    *,
    calibration_id: str = CALIBRATION,
    dataset_id: str = DATASET,
    display_suffix: str = "1",
    judge_route_version_id: str = JUDGE_ROUTE,
    judge_prompt_version_id: str = JUDGE_PROMPT,
    resolved_judge_model_id: str = JUDGE_MODEL,
) -> None:
    cluster.psql(
        database,
        f"""
        INSERT INTO ai.judge_calibration (
            id, display_id, judge_route_version_id, judge_prompt_version_id,
            dataset_version_id, case_count, status,
            evaluated_task_definition_id, resolved_judge_model_id,
            rubric_artifact_id, rubric_sha256, grader_version
        )
        VALUES (
            '{calibration_id}', 'AIC-ST0003-{display_suffix}',
            '{judge_route_version_id}', '{judge_prompt_version_id}',
            '{dataset_id}', 200, 'DRAFT', '{TASK}',
            '{resolved_judge_model_id}', '{ARTIFACT_REPORT}', repeat('4', 64),
            'grader.model_judge.v1'
        );
        UPDATE ai.judge_calibration
           SET status = 'PASSED',
               weighted_kappa = 0.70,
               zero_tolerance_false_pass_rate = 0.01,
               zero_tolerance_false_fail_rate = 0.05,
               report_artifact_id = '{ARTIFACT_REPORT}',
               approved_by_principal_id = '{P3}',
               approved_at = statement_timestamp(),
               expires_at = statement_timestamp() + interval '30 days',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{calibration_id}';
        """,
    )


def seed_successful_case_attempts(
    cluster: Any,
    database: str,
    *,
    run_id: str = RUN,
    dataset_id: str = DATASET,
    display_suffix: str = "1",
) -> None:
    """Create one exactly bound successful provider attempt per dataset case."""

    cluster.psql(
        database,
        f"""
        SET session_replication_role = replica;
        INSERT INTO ops.object_artifact (
            display_id, artifact_kind, bucket_name, object_key,
            content_type, byte_size, sha256, encryption_state,
            retention_class, source_system, is_immutable
        )
        SELECT 'OBJ-ST0003-OUTPUT-{display_suffix}-' || candidate.case_key,
               'ai_output', 'bucket',
               'st0003/output/{display_suffix}/' || candidate.case_key,
               'application/json', 1,
               lpad(
                   to_hex(row_number() OVER (ORDER BY candidate.case_key)),
                   64,
                   'f'
               ),
               'LOCAL_DEV', 'AI_EVAL_3Y', 'st0003', true
          FROM ai.evaluation_case AS candidate
         WHERE candidate.dataset_version_id = '{dataset_id}';

        INSERT INTO ai.ai_job (
            display_id, ops_job_id, task_definition_id, article_plan_id,
            source_packet_version_id, prompt_version_id,
            output_schema_version_id, model_route_version_id,
            policy_bundle_version_id, status, max_cost_jpy, completed_at
        )
        SELECT 'AIJ-ST0003-{display_suffix}-' || candidate.case_key,
               uuidv7(), suite.task_definition_id, uuidv7(), uuidv7(),
               run.prompt_version_id, run.output_schema_version_id,
               run.model_route_version_id, run.policy_bundle_version_id,
               'SUCCEEDED', 100, clock_timestamp()
          FROM ai.evaluation_run AS run
          JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
          JOIN ai.evaluation_case AS candidate
            ON candidate.dataset_version_id = run.dataset_version_id
         WHERE run.id = '{run_id}'
           AND candidate.dataset_version_id = '{dataset_id}';

        INSERT INTO ai.ai_attempt (
            ai_job_id, attempt_no, model_id, provider_request_id, status,
            input_artifact_id, output_artifact_id, input_sha256,
            output_sha256, finish_reason, started_at, completed_at,
            requested_model_id, resolved_model_id, request_config,
            validation_status, repair_attempt_no
        )
        SELECT job.id, 1, run.resolved_model_id,
               'provider-' || candidate.case_key, 'SUCCEEDED',
               candidate.input_artifact_id, output_artifact.id,
               input_artifact.sha256, output_artifact.sha256, 'stop',
               clock_timestamp(), clock_timestamp(),
               model.provider_model_id, model.provider_model_id,
               '{{}}'::jsonb, 'PASSED', 0
          FROM ai.evaluation_run AS run
          JOIN ai.model_definition AS model ON model.id = run.resolved_model_id
          JOIN ai.evaluation_case AS candidate
            ON candidate.dataset_version_id = run.dataset_version_id
          JOIN ai.ai_job AS job
            ON job.display_id =
               'AIJ-ST0003-{display_suffix}-' || candidate.case_key
          JOIN ops.object_artifact AS input_artifact
            ON input_artifact.id = candidate.input_artifact_id
          JOIN ops.object_artifact AS output_artifact
            ON output_artifact.display_id =
               'OBJ-ST0003-OUTPUT-{display_suffix}-' || candidate.case_key
         WHERE run.id = '{run_id}'
           AND candidate.dataset_version_id = '{dataset_id}';
        SET session_replication_role = origin;
        """,
    )


def case_attempt_id_sql(display_suffix: str, case_id: str = CASE) -> str:
    return f"""(
        SELECT attempt.id
          FROM ai.ai_attempt AS attempt
          JOIN ai.ai_job AS job ON job.id = attempt.ai_job_id
          JOIN ai.evaluation_case AS candidate
            ON job.display_id =
               'AIJ-ST0003-{display_suffix}-' || candidate.case_key
         WHERE candidate.id = '{case_id}'
           AND attempt.attempt_no = 1
    )"""


def case_attempt_output_artifact_sql(
    display_suffix: str,
    case_id: str = CASE,
) -> str:
    return f"""(
        SELECT attempt.output_artifact_id
          FROM ai.ai_attempt AS attempt
         WHERE attempt.id = {case_attempt_id_sql(display_suffix, case_id)}
    )"""


def create_evaluation_run(
    cluster: Any,
    database: str,
    *,
    run_id: str = RUN,
    result_id: str = RESULT,
    dataset_id: str = DATASET,
    case_id: str = CASE,
    display_suffix: str = "1",
    zero_tolerance_failures: int = 0,
    complete: bool = True,
    model_route_version_id: str = ROUTE,
    baseline_run_id: str | None = None,
) -> None:
    primary_result_status = "PASSED" if zero_tolerance_failures == 0 else "FAILED"
    baseline_run_sql = "NULL" if baseline_run_id is None else f"'{baseline_run_id}'"
    cluster.psql(
        database,
        f"""
        INSERT INTO ai.evaluation_run (
            id, display_id, suite_id, dataset_version_id, prompt_version_id,
            model_route_version_id, output_schema_version_id,
            policy_bundle_version_id, code_git_sha, created_by_principal_id,
            resolved_model_id, baseline_evaluation_run_id
        )
        VALUES (
            '{run_id}', 'AIR-ST0003-{display_suffix}', '{SUITE}',
            '{dataset_id}', '{PROMPT}', '{model_route_version_id}',
            '{OUTPUT_SCHEMA}',
            '{POLICY}', '{CODE_SHA}', '{P1}', '{MODEL}', {baseline_run_sql}
        );
        UPDATE ai.evaluation_run
           SET status = 'RUNNING', started_at = clock_timestamp(),
               lock_version = lock_version + 1, updated_at = clock_timestamp()
         WHERE id = '{run_id}';
        """,
    )
    seed_successful_case_attempts(
        cluster,
        database,
        run_id=run_id,
        dataset_id=dataset_id,
        display_suffix=display_suffix,
    )
    cluster.psql(
        database,
        f"""
        INSERT INTO ai.evaluation_case_result (
            id, evaluation_run_id, evaluation_case_id, ai_attempt_id,
            output_artifact_id, status, disposition,
            zero_tolerance_evidence, zero_tolerance_evidence_artifact_id,
            zero_tolerance_evidence_sha256
        )
        VALUES (
            '{result_id}', '{run_id}', '{case_id}',
            {case_attempt_id_sql(display_suffix, case_id)},
            {case_attempt_output_artifact_sql(display_suffix, case_id)},
            '{primary_result_status}', 'CALL_PROVIDER_AND_PASS',
            {zero_tolerance_values_sql(zero_tolerance_failures)}
        );
        INSERT INTO ai.evaluation_case_result (
            evaluation_run_id, evaluation_case_id, ai_attempt_id,
            output_artifact_id, status, disposition,
            zero_tolerance_evidence, zero_tolerance_evidence_artifact_id,
            zero_tolerance_evidence_sha256
        )
        SELECT '{run_id}', candidate.id, attempt.id,
               attempt.output_artifact_id,
               'PASSED', 'CALL_PROVIDER_AND_PASS',
               {zero_tolerance_values_sql()}
          FROM ai.evaluation_case AS candidate
          JOIN ai.ai_job AS job
            ON job.display_id =
               'AIJ-ST0003-{display_suffix}-' || candidate.case_key
          JOIN ai.ai_attempt AS attempt
            ON attempt.ai_job_id = job.id AND attempt.attempt_no = 1
         WHERE candidate.dataset_version_id = '{dataset_id}'
           AND candidate.id <> '{case_id}';
        """,
    )
    seed_canonical_run_evidence(
        cluster,
        database,
        run_id=run_id,
        dataset_id=dataset_id,
    )
    if complete:
        cluster.psql(
            database,
            f"""
            UPDATE ai.evaluation_run
               SET status = 'GRADING',
                   lock_version = lock_version + 1,
                   updated_at = clock_timestamp()
             WHERE id = '{run_id}';
            UPDATE ai.evaluation_run
               SET status = 'COMPLETED',
                   run_manifest_artifact_id = '{ARTIFACT_REPORT}',
                   completed_at = clock_timestamp(),
                   lock_version = lock_version + 1,
                   updated_at = clock_timestamp()
             WHERE id = '{run_id}';
            """,
        )


def insert_planned_run(
    cluster: Any,
    database: str,
    *,
    run_id: str = RUN,
    dataset_id: str = DATASET,
    display_suffix: str = "1",
    resolved_model_id: str = MODEL,
    model_route_version_id: str = ROUTE,
    prompt_version_id: str = PROMPT,
    baseline_run_id: str | None = None,
) -> None:
    baseline_run_sql = "NULL" if baseline_run_id is None else f"'{baseline_run_id}'"
    cluster.psql(
        database,
        f"""
        INSERT INTO ai.evaluation_run (
            id, display_id, suite_id, dataset_version_id, prompt_version_id,
            model_route_version_id, output_schema_version_id,
            policy_bundle_version_id, code_git_sha, created_by_principal_id,
            resolved_model_id, baseline_evaluation_run_id
        )
        VALUES (
            '{run_id}', 'AIR-ST0003-PLANNED-{display_suffix}', '{SUITE}',
            '{dataset_id}', '{prompt_version_id}', '{model_route_version_id}',
            '{OUTPUT_SCHEMA}',
            '{POLICY}', '{CODE_SHA}', '{P1}', '{resolved_model_id}',
            {baseline_run_sql}
        );
        """,
    )


def insert_all_case_results_without_evidence(
    cluster: Any,
    database: str,
    *,
    run_id: str = RUN,
    dataset_id: str = DATASET,
) -> None:
    cluster.psql(
        database,
        f"""
        INSERT INTO ai.evaluation_case_result (
            evaluation_run_id, evaluation_case_id, output_artifact_id,
            status, disposition, zero_tolerance_evidence,
            zero_tolerance_evidence_artifact_id,
            zero_tolerance_evidence_sha256
        )
        SELECT '{run_id}', candidate.id, '{ARTIFACT_REPORT}', 'PASSED',
               'CALL_PROVIDER_AND_PASS', {zero_tolerance_values_sql()}
          FROM ai.evaluation_case AS candidate
         WHERE candidate.dataset_version_id = '{dataset_id}';
        """,
    )


def canonical_metric_insert_sql(
    *,
    grader_code: str = "grader.json_schema.v1",
    metric_code: str = "schema_valid_rate",
    metric_value: str = "1",
    passed: str = "true",
    threshold_operator: str | None = ">=",
    threshold_value: str = "1",
    details_sql: str = "'{}'::jsonb",
    run_id: str = RUN,
    case_id: str = CASE,
    case_key_sql: str = "candidate.case_key",
    task_id_sql: str = "suite.task_definition_id",
    result_artifact_id: str = ARTIFACT_REPORT,
    judge_calibration_id: str | None = None,
    judge_route_version_id: str | None = None,
    judge_prompt_version_id: str | None = None,
    judge_rubric_artifact_id: str | None = None,
    judge_resolved_model_id: str | None = None,
    judge_grader_version: str | None = None,
    proportion_numerator_sql: str | None = None,
    proportion_denominator_sql: str | None = None,
) -> str:
    def nullable_literal(value: str | None) -> str:
        return "NULL" if value is None else "'" + value.replace("'", "''") + "'"

    numerator_sql = proportion_numerator_sql or (
        "CASE WHEN ai.canonical_metric_unit('"
        + metric_code.replace("'", "''")
        + "') = 'ratio' THEN round(("
        + metric_value
        + ") * 1000000)::bigint ELSE NULL END"
    )
    denominator_sql = proportion_denominator_sql or (
        "CASE WHEN ai.canonical_metric_unit('"
        + metric_code.replace("'", "''")
        + "') = 'ratio' THEN 1000000::bigint ELSE NULL END"
    )
    threshold_operator_sql = (
        "NULL"
        if threshold_operator is None
        else "'" + threshold_operator.replace("'", "''") + "'"
    )

    return f"""
        INSERT INTO ai.evaluation_result (
            suite_code, suite_version, run_id, task_definition_id,
            model_route_version_id, prompt_version_id, case_key,
            metric_code, metric_value, passed, details, result_artifact_id,
            evaluation_run_id, evaluation_case_id, grader_code, slice_key,
            threshold_operator, threshold_value, judge_calibration_id,
            judge_route_version_id, judge_prompt_version_id,
            judge_rubric_artifact_id, judge_resolved_model_id,
            judge_grader_version, proportion_numerator_count,
            proportion_denominator_count
        )
        SELECT suite.suite_code, suite.version_no, run.id, {task_id_sql},
               run.model_route_version_id, run.prompt_version_id,
               {case_key_sql}, '{metric_code}', {metric_value}, {passed},
               {details_sql}, '{result_artifact_id}', run.id, candidate.id,
               '{grader_code}', candidate.split, {threshold_operator_sql},
               {threshold_value}, {nullable_literal(judge_calibration_id)},
               {nullable_literal(judge_route_version_id)},
               {nullable_literal(judge_prompt_version_id)},
               {nullable_literal(judge_rubric_artifact_id)},
               {nullable_literal(judge_resolved_model_id)},
               {nullable_literal(judge_grader_version)},
               {numerator_sql}, {denominator_sql}
          FROM ai.evaluation_run AS run
          JOIN ai.evaluation_suite AS suite ON suite.id = run.suite_id
          JOIN ai.evaluation_case AS candidate ON candidate.id = '{case_id}'
         WHERE run.id = '{run_id}';
    """


def insert_release(
    cluster: Any,
    database: str,
    *,
    release_id: str = RELEASE,
    run_id: str = RUN,
    dataset_id: str = DATASET,
    display_suffix: str = "1",
    judge_calibration_id: str | None = None,
    ready_for_review: bool = True,
    model_route_version_id: str = ROUTE,
) -> None:
    calibration_sql = (
        "NULL"
        if judge_calibration_id is None
        else f"'{judge_calibration_id}'"
    )
    cluster.psql(
        database,
        f"""
        INSERT INTO ai.release_decision (
            id, display_id, task_definition_id, prompt_version_id,
            model_route_version_id, output_schema_version_id,
            resolved_model_id, policy_bundle_version_id, dataset_version_id,
            evaluation_run_id, code_git_sha, release_scope,
            maximum_canary_percent, decision_manifest_sha256,
            rollback_strategy, rollback_runbook_artifact_id,
            rollback_runbook_sha256, judge_calibration_id,
            canary_monitoring_artifact_id, canary_monitoring_sha256
        )
        VALUES (
            '{release_id}', 'REL-ST0003-{display_suffix}', '{TASK}', '{PROMPT}',
            '{model_route_version_id}', '{OUTPUT_SCHEMA}', '{MODEL}', '{POLICY}',
            '{dataset_id}', '{run_id}', '{CODE_SHA}', 'CANARY', 1,
            '{MANIFEST_SHA}', 'DISABLE_ROUTE', '{ARTIFACT_RUNBOOK}',
            repeat('9', 64), {calibration_sql}, '{ARTIFACT_MONITOR}',
            repeat('5', 64)
        );
        """,
    )
    if ready_for_review:
        cluster.psql(
            database,
            f"""
            UPDATE ai.release_decision
               SET status = 'READY_FOR_REVIEW',
                   lock_version = lock_version + 1,
                   updated_at = clock_timestamp()
             WHERE id = '{release_id}';
            """,
        )


def insert_release_approval(
    cluster: Any,
    database: str,
    *,
    approval_id: str,
    display_suffix: str,
    release_id: str = RELEASE,
    phase: str,
    manifest_sha256: str,
    artifact_id: str,
    artifact_sha_digit: str,
    primary_principal_id: str = P2,
    second_principal_id: str = P3,
    signed_at_sql: str = "statement_timestamp()",
) -> None:
    cluster.psql(
        database,
        f"""
        INSERT INTO ai.release_approval (
            id, display_id, release_decision_id, phase,
            decision_manifest_sha256, primary_approver_principal_id,
            primary_approver_role, second_approver_principal_id,
            second_approver_role, approval_artifact_id, approval_sha256,
            signed_at
        )
        VALUES (
            '{approval_id}', 'RAP-ST0003-{display_suffix}', '{release_id}',
            '{phase}', '{manifest_sha256}', '{primary_principal_id}',
            'APPROVER', '{second_principal_id}',
            'OWNER', '{artifact_id}', repeat('{artifact_sha_digit}', 64),
            {signed_at_sql}
        );
        """,
    )


def promote_release_to_active_champion(
    cluster: Any,
    database: str,
    *,
    release_id: str = RELEASE,
    route_id: str = ROUTE,
) -> None:
    insert_release_approval(
        cluster,
        database,
        approval_id=CANARY_APPROVAL,
        display_suffix="champion-canary",
        release_id=release_id,
        phase="CANARY",
        manifest_sha256=MANIFEST_SHA,
        artifact_id=ARTIFACT_CANARY_APPROVAL,
        artifact_sha_digit="7",
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.release_decision
           SET status = 'APPROVED_CANARY',
               approved_by_principal_id = '{P2}',
               second_approver_principal_id = '{P3}',
               approved_at = (
                   SELECT signed_at FROM ai.release_approval
                    WHERE id = '{CANARY_APPROVAL}'
               ),
               canary_approval_id = '{CANARY_APPROVAL}',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{release_id}';
        UPDATE ai.model_route_version
           SET status = 'CANARY', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{route_id}';
        """,
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.release_decision
           SET canary_evidence_artifact_id = '{ARTIFACT_CANARY}',
               canary_evidence_sha256 = repeat('6', 64),
               canary_completed_at = statement_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{release_id}';
        """,
    )
    insert_release_approval(
        cluster,
        database,
        approval_id=ACTIVE_APPROVAL,
        display_suffix="champion-active",
        release_id=release_id,
        phase="ACTIVE",
        manifest_sha256="c" * 64,
        artifact_id=ARTIFACT_ACTIVE_APPROVAL,
        artifact_sha_digit="8",
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.release_decision
           SET status = 'APPROVED_ACTIVE', release_scope = 'ACTIVE',
               maximum_canary_percent = 0,
               decision_manifest_sha256 = repeat('c', 64),
               active_approval_id = '{ACTIVE_APPROVAL}',
               approved_by_principal_id = '{P2}',
               second_approver_principal_id = '{P3}',
               approved_at = (
                   SELECT signed_at FROM ai.release_approval
                    WHERE id = '{ACTIVE_APPROVAL}'
               ),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{release_id}';
        UPDATE ai.model_route_version
           SET status = 'ACTIVE', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{route_id}';
        UPDATE ai.prompt_version
           SET status = 'ACTIVE', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{PROMPT}';
        UPDATE ai.model_definition SET status = 'ACTIVE' WHERE id = '{MODEL}';
        """,
    )


def schema_signature(cluster: Any, database: str) -> str:
    return cluster.query(
        database,
        """
        SELECT 'column', table_name, ordinal_position::text, column_name,
               data_type, is_nullable, COALESCE(column_default, '<NULL>')
          FROM information_schema.columns
         WHERE table_schema = 'ai'
           AND table_name IN (
               'evaluation_suite', 'evaluation_dataset_version',
               'evaluation_case', 'evaluation_run',
               'evaluation_case_result', 'human_evaluation',
               'judge_calibration', 'release_decision', 'release_approval'
           )
        UNION ALL
        SELECT 'constraint', c.relname, '0', con.conname,
               pg_get_constraintdef(con.oid), con.convalidated::text, ''
          FROM pg_constraint AS con
          JOIN pg_class AS c ON c.oid = con.conrelid
          JOIN pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = 'ai'
           AND c.relname IN (
               'evaluation_suite', 'evaluation_dataset_version',
               'evaluation_case', 'evaluation_run',
               'evaluation_case_result', 'human_evaluation',
               'judge_calibration', 'release_decision', 'release_approval'
           )
        UNION ALL
        SELECT 'index', tablename, '0', indexname, indexdef, '', ''
          FROM pg_indexes
         WHERE schemaname = 'ai'
           AND tablename IN (
               'evaluation_suite', 'evaluation_dataset_version',
               'evaluation_case', 'evaluation_run',
               'evaluation_case_result', 'human_evaluation',
               'judge_calibration', 'release_decision', 'release_approval'
           )
         ORDER BY 1, 2, 3, 4, 5, 6, 7;
        """,
    )


def full_ai_schema_and_data_signature(
    cluster: Any,
    database: str,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Return an OID-free signature for the complete AI schema and its rows."""

    schema = cluster.query(
        database,
        """
        WITH objects(kind, owner_name, object_name, definition) AS (
            SELECT 'column', table_name, ordinal_position::text,
                   concat_ws('|', column_name, data_type, udt_name,
                             is_nullable, COALESCE(column_default, '<NULL>'))
              FROM information_schema.columns
             WHERE table_schema = 'ai'
            UNION ALL
            SELECT 'constraint', table_class.relname, con_record.conname,
                   pg_get_constraintdef(con_record.oid, true)
              FROM pg_constraint AS con_record
              JOIN pg_class AS table_class
                ON table_class.oid = con_record.conrelid
              JOIN pg_namespace AS namespace
                ON namespace.oid = table_class.relnamespace
             WHERE namespace.nspname = 'ai'
            UNION ALL
            SELECT 'index', table_class.relname, index_class.relname,
                   pg_get_indexdef(index_class.oid)
              FROM pg_index AS index_record
              JOIN pg_class AS table_class
                ON table_class.oid = index_record.indrelid
              JOIN pg_class AS index_class
                ON index_class.oid = index_record.indexrelid
              JOIN pg_namespace AS namespace
                ON namespace.oid = table_class.relnamespace
             WHERE namespace.nspname = 'ai'
            UNION ALL
            SELECT 'trigger', table_class.relname, trigger_record.tgname,
                   pg_get_triggerdef(trigger_record.oid, true)
              FROM pg_trigger AS trigger_record
              JOIN pg_class AS table_class
                ON table_class.oid = trigger_record.tgrelid
              JOIN pg_namespace AS namespace
                ON namespace.oid = table_class.relnamespace
             WHERE namespace.nspname = 'ai'
               AND NOT trigger_record.tgisinternal
            UNION ALL
            SELECT 'function', procedure.proname,
                   pg_get_function_identity_arguments(procedure.oid),
                   pg_get_functiondef(procedure.oid)
              FROM pg_proc AS procedure
              JOIN pg_namespace AS namespace
                ON namespace.oid = procedure.pronamespace
             WHERE namespace.nspname = 'ai'
            UNION ALL
            SELECT 'table_grant', table_name, grantee,
                   privilege_type || '|' || is_grantable
              FROM information_schema.role_table_grants
             WHERE table_schema = 'ai'
            UNION ALL
            SELECT 'routine_grant', routine_name, grantee,
                   privilege_type || '|' || is_grantable
              FROM information_schema.role_routine_grants
             WHERE specific_schema = 'ai'
        )
        SELECT string_agg(
                   concat_ws(E'\t', kind, owner_name, object_name, definition),
                   E'\n'
                   ORDER BY kind, owner_name, object_name, definition
               )
          FROM objects;
        """,
    )
    tables = cluster.query(
        database,
        """
        SELECT table_name
          FROM information_schema.tables
         WHERE table_schema = 'ai'
           AND table_type = 'BASE TABLE'
         ORDER BY table_name;
        """,
    ).splitlines()
    data = tuple(
        (
            table_name,
            cluster.query(
                database,
                f"""
                SELECT COALESCE(
                           string_agg(to_jsonb(row_value)::text, E'\\n'
                                      ORDER BY to_jsonb(row_value)::text),
                           ''
                       )
                  FROM ai.{table_name} AS row_value;
                """,
            ),
        )
        for table_name in tables
    )
    return schema, data


def test_ambiguous_legacy_states_refuse_contract_until_explicit_classification(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "ambiguous_refusal")
    seed_legacy_ai_rows(cluster, database)

    apply_sql(cluster, database, EXPAND, EXPAND_VALIDATE)
    migrate_automatic_rows(cluster, database)

    states = cluster.query(
        database,
        """
        SELECT display_id, status
          FROM ai.ai_job
         WHERE display_id LIKE 'AIJ-ST0003-%'
         ORDER BY display_id;
        """,
    ).splitlines()
    assert states == [
        "AIJ-ST0003-BLOCKED\tBLOCKED",
        "AIJ-ST0003-FAILED\tFAILED_TERMINAL",
        "AIJ-ST0003-PENDING\tREQUESTED",
    ]
    assert (
        cluster.query(
            database,
            """
            SELECT status FROM ai.prompt_version
             WHERE display_id = 'PRM-ST0003-REJECTED';
            """,
        )
        == "REJECTED"
    )

    result = cluster.psql(database, read_sql(CONTRACT_PREPARE), check=False)
    assert result.returncode != 0
    assert "BLOCKED" in result.stderr
    assert "REJECTED" in result.stderr

    classify_ambiguous_legacy_rows(cluster, database)
    apply_sql(cluster, database, CONTRACT_PREPARE, CONTRACT)
    assert (
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM ai.ai_job
             WHERE status IN ('PENDING', 'FAILED', 'BLOCKED');
            """,
        )
        == "0"
    )


def test_expand_refuses_object_artifact_immutability_trigger_drift(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "artifact_trigger_drift")
    cluster.psql(
        database,
        """
        ALTER TABLE ops.object_artifact
            DISABLE TRIGGER trg_ops_object_artifact_immutable;
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        read_sql(EXPAND),
        ("object_artifact", "immutable"),
    )


def test_policy_child_graph_guards_are_live_during_expand_only(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "policy_child_expand")
    apply_sql(cluster, database, EXPAND)
    cluster.psql(
        database,
        f"""
        INSERT INTO iam.principal (
            id, display_id, principal_type, status, display_name
        ) VALUES (
            '{P1}', 'PRN-ST0003-POLICY', 'USER', 'ACTIVE',
            'ST0003 Policy Approver'
        );
        """,
    )
    insert_policy_rule(
        cluster,
        database,
        rule_id=RULE_ACTIVE,
        suffix="expand-active",
    )
    insert_policy_bundle(
        cluster,
        database,
        bundle_id=POLICY_DRAFT,
        suffix="expand-draft",
    )
    empty_bundle = "00000000-0000-7000-8000-0000000000e2"
    insert_policy_bundle(
        cluster,
        database,
        bundle_id=empty_bundle,
        suffix="expand-empty",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE policy.policy_bundle
           SET status = 'ACTIVE', approved_by_principal_id = '{P1}',
               approved_at = clock_timestamp()
         WHERE id = '{empty_bundle}';
        """,
        ("at least one", "non-empty", "no bound rule"),
    )

    cluster.psql(
        database,
        f"""
        UPDATE policy.rule_version
           SET definition = '{{"fixture": "edited-draft"}}'::jsonb,
               definition_sha256 = repeat('9', 64)
         WHERE id = '{RULE_ACTIVE}';
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"UPDATE policy.rule_version SET rule_code = 'changed' WHERE id = '{RULE_ACTIVE}';",
        "identity is immutable",
    )
    cluster.psql(
        database,
        f"""
        UPDATE policy.rule_version
           SET status = 'ACTIVE', approved_by_principal_id = '{P1}'
         WHERE id = '{RULE_ACTIVE}';
        INSERT INTO policy.bundle_rule (
            policy_bundle_id, rule_version_id, execution_order, mode
        ) VALUES ('{POLICY_DRAFT}', '{RULE_ACTIVE}', 0, 'ENFORCE');
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"UPDATE policy.rule_version SET severity = 'CRITICAL' WHERE id = '{RULE_ACTIVE}';",
        "non-DRAFT policy rule content is immutable",
    )
    assert_sql_fails(
        cluster,
        database,
        f"DELETE FROM policy.rule_version WHERE id = '{RULE_ACTIVE}';",
        "not deletable",
    )
    for binding_mutation in (
        f"""
        UPDATE policy.bundle_rule
           SET mode = 'SHADOW'
         WHERE policy_bundle_id = '{POLICY_DRAFT}'
           AND rule_version_id = '{RULE_ACTIVE}';
        """,
        f"""
        DELETE FROM policy.bundle_rule
         WHERE policy_bundle_id = '{POLICY_DRAFT}'
           AND rule_version_id = '{RULE_ACTIVE}';
        """,
    ):
        assert_sql_fails(
            cluster,
            database,
            binding_mutation,
            "bundle rule bindings are append-only",
        )

    insert_policy_rule(
        cluster,
        database,
        rule_id=RULE_SECONDARY,
        suffix="expand-secondary",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO policy.bundle_rule (
            policy_bundle_id, rule_version_id, execution_order, mode
        ) VALUES ('{POLICY_DRAFT}', '{RULE_SECONDARY}', 1, 'SHADOW');
        """,
        "ACTIVE rule version",
    )
    cluster.psql(
        database,
        f"""
        UPDATE policy.rule_version
           SET status = 'ACTIVE', approved_by_principal_id = '{P1}'
         WHERE id = '{RULE_SECONDARY}';
        UPDATE policy.policy_bundle
           SET status = 'ACTIVE', approved_by_principal_id = '{P1}',
               approved_at = clock_timestamp()
         WHERE id = '{POLICY_DRAFT}';
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO policy.bundle_rule (
            policy_bundle_id, rule_version_id, execution_order, mode
        ) VALUES ('{POLICY_DRAFT}', '{RULE_SECONDARY}', 1, 'SHADOW');
        """,
        "DRAFT bundle",
    )
    cluster.psql(
        database,
        f"UPDATE policy.rule_version SET status = 'RETIRED' WHERE id = '{RULE_SECONDARY}';",
    )
    assert_sql_fails(
        cluster,
        database,
        f"UPDATE policy.rule_version SET status = 'ACTIVE' WHERE id = '{RULE_SECONDARY}';",
        "lifecycle cannot move",
    )
    assert_sql_fails(
        cluster,
        database,
        f"UPDATE policy.rule_version SET status = 'RETIRED' WHERE id = '{RULE_ACTIVE}';",
        "required by an ACTIVE policy bundle",
    )

    insert_policy_bundle(
        cluster,
        database,
        bundle_id=POLICY_INVALID,
        suffix="expand-invalid",
    )
    insert_policy_rule(
        cluster,
        database,
        rule_id=RULE_INVALID,
        suffix="expand-invalid",
    )
    cluster.psql(
        database,
        f"""
        SET session_replication_role = replica;
        INSERT INTO policy.bundle_rule (
            policy_bundle_id, rule_version_id, execution_order, mode
        ) VALUES ('{POLICY_INVALID}', '{RULE_INVALID}', 0, 'ENFORCE');
        SET session_replication_role = origin;
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE policy.policy_bundle
           SET status = 'ACTIVE', approved_by_principal_id = '{P1}',
               approved_at = clock_timestamp()
         WHERE id = '{POLICY_INVALID}';
        """,
        "every bound rule version to be ACTIVE",
    )


def test_policy_bundle_activation_and_rule_retirement_race_is_serialized(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "policy_child_race")
    apply_sql(cluster, database, EXPAND)
    cluster.psql(
        database,
        f"""
        INSERT INTO iam.principal (
            id, display_id, principal_type, status, display_name
        ) VALUES (
            '{P1}', 'PRN-ST0003-POLICY-RACE', 'USER', 'ACTIVE',
            'ST0003 Policy Race Approver'
        );
        """,
    )
    insert_policy_rule(
        cluster,
        database,
        rule_id=RULE_ACTIVE,
        suffix="race",
        status="ACTIVE",
    )
    insert_policy_bundle(
        cluster,
        database,
        bundle_id=POLICY_DRAFT,
        suffix="race",
    )
    cluster.psql(
        database,
        f"""
        INSERT INTO policy.bundle_rule (
            policy_bundle_id, rule_version_id, execution_order, mode
        ) VALUES ('{POLICY_DRAFT}', '{RULE_ACTIVE}', 0, 'ENFORCE');
        """,
    )

    controller: subprocess.Popen[str] | None = None
    activation: subprocess.Popen[str] | None = None
    retirement: subprocess.Popen[str] | None = None
    try:
        controller = open_psql_process(cluster, database)
        assert controller.stdin is not None
        controller.stdin.write(
            f"""
            SET application_name = 'st0003_policy_race_controller';
            SELECT pg_advisory_lock(72003, hashtext('{RULE_ACTIVE}'));
            """,
        )
        controller.stdin.flush()
        wait_for_database_condition(
            cluster,
            database,
            """
            SELECT EXISTS (
                SELECT 1
                  FROM pg_stat_activity AS activity
                  JOIN pg_locks AS lock ON lock.pid = activity.pid
                 WHERE activity.datname = current_database()
                   AND activity.application_name =
                       'st0003_policy_race_controller'
                   AND lock.locktype = 'advisory'
                   AND lock.granted
            );
            """,
        )
        activation = start_psql_script(
            cluster,
            database,
            f"""
            SET application_name = 'st0003_policy_activation';
            SET statement_timeout = '10s';
            UPDATE policy.policy_bundle
               SET status = 'ACTIVE', approved_by_principal_id = '{P1}',
                   approved_at = clock_timestamp()
             WHERE id = '{POLICY_DRAFT}';
            """,
        )
        retirement = start_psql_script(
            cluster,
            database,
            f"""
            SET application_name = 'st0003_policy_retirement';
            SET statement_timeout = '10s';
            UPDATE policy.rule_version
               SET status = 'RETIRED'
             WHERE id = '{RULE_ACTIVE}';
            """,
        )
        wait_for_database_condition(
            cluster,
            database,
            """
            SELECT count(*) = 2
              FROM pg_stat_activity
             WHERE datname = current_database()
               AND application_name IN (
                   'st0003_policy_activation',
                   'st0003_policy_retirement'
               )
               AND wait_event_type = 'Lock';
            """,
        )

        controller.stdin.write(
            f"""
            SELECT pg_advisory_unlock(72003, hashtext('{RULE_ACTIVE}'));
            \\q
            """,
        )
        controller.stdin.close()
        controller_result = finish_psql_process(controller)
        controller = None
        activation_result = finish_psql_process(activation)
        activation = None
        retirement_result = finish_psql_process(retirement)
        retirement = None

        assert controller_result[0] == 0, controller_result
        assert sorted(
            (activation_result[0] == 0, retirement_result[0] == 0)
        ) == [False, True]
        failed_error = (
            activation_result[2]
            if activation_result[0] != 0
            else retirement_result[2]
        )
        assert (
            "every bound rule version to be ACTIVE" in failed_error
            or "required by an ACTIVE policy bundle" in failed_error
        ), failed_error
        assert cluster.query(
            database,
            f"""
            SELECT bundle.status, rule.status
              FROM policy.policy_bundle AS bundle
              JOIN policy.bundle_rule AS binding
                ON binding.policy_bundle_id = bundle.id
              JOIN policy.rule_version AS rule
                ON rule.id = binding.rule_version_id
             WHERE bundle.id = '{POLICY_DRAFT}';
            """,
        ) in {"ACTIVE\tACTIVE", "DRAFT\tRETIRED"}
    finally:
        stop_psql_process(retirement)
        stop_psql_process(activation)
        stop_psql_process(controller)


def test_policy_bundle_activation_and_rule_append_race_has_no_deadlock(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "policy_append_race")
    apply_sql(cluster, database, EXPAND)
    cluster.psql(
        database,
        f"""
        INSERT INTO iam.principal (
            id, display_id, principal_type, status, display_name
        ) VALUES (
            '{P1}', 'PRN-ST0003-POLICY-APPEND', 'USER', 'ACTIVE',
            'ST0003 Policy Append Approver'
        );
        """,
    )
    insert_policy_rule(
        cluster,
        database,
        rule_id=RULE_ACTIVE,
        suffix="append-bound",
        status="ACTIVE",
    )
    insert_policy_rule(
        cluster,
        database,
        rule_id=RULE_SECONDARY,
        suffix="append-contender",
        status="ACTIVE",
    )
    insert_policy_bundle(
        cluster,
        database,
        bundle_id=POLICY_DRAFT,
        suffix="append-race",
    )
    cluster.psql(
        database,
        f"""
        INSERT INTO policy.bundle_rule (
            policy_bundle_id, rule_version_id, execution_order, mode
        ) VALUES ('{POLICY_DRAFT}', '{RULE_ACTIVE}', 0, 'ENFORCE');
        """,
    )

    controller: subprocess.Popen[str] | None = None
    activation: subprocess.Popen[str] | None = None
    appender: subprocess.Popen[str] | None = None
    try:
        controller = open_psql_process(cluster, database)
        assert controller.stdin is not None
        controller.stdin.write(
            f"""
            SET application_name = 'st0003_policy_append_controller';
            SELECT pg_advisory_lock(72003, hashtext('{RULE_ACTIVE}'));
            """,
        )
        controller.stdin.flush()
        wait_for_database_condition(
            cluster,
            database,
            """
            SELECT EXISTS (
                SELECT 1
                  FROM pg_stat_activity AS activity
                  JOIN pg_locks AS lock ON lock.pid = activity.pid
                 WHERE activity.datname = current_database()
                   AND activity.application_name =
                       'st0003_policy_append_controller'
                   AND lock.locktype = 'advisory'
                   AND lock.granted
            );
            """,
        )
        activation = start_psql_script(
            cluster,
            database,
            f"""
            SET application_name = 'st0003_policy_append_activation';
            SET statement_timeout = '10s';
            UPDATE policy.policy_bundle
               SET status = 'ACTIVE', approved_by_principal_id = '{P1}',
                   approved_at = clock_timestamp()
             WHERE id = '{POLICY_DRAFT}';
            """,
        )
        wait_for_database_condition(
            cluster,
            database,
            """
            SELECT EXISTS (
                SELECT 1
                  FROM pg_stat_activity AS activity
                  JOIN pg_locks AS lock ON lock.pid = activity.pid
                 WHERE activity.datname = current_database()
                   AND activity.application_name =
                       'st0003_policy_append_activation'
                   AND lock.locktype = 'advisory'
                   AND NOT lock.granted
            );
            """,
        )
        appender = start_psql_script(
            cluster,
            database,
            f"""
            SET application_name = 'st0003_policy_append_contender';
            SET statement_timeout = '10s';
            INSERT INTO policy.bundle_rule (
                policy_bundle_id, rule_version_id, execution_order, mode
            ) VALUES (
                '{POLICY_DRAFT}', '{RULE_SECONDARY}', 1, 'SHADOW'
            );
            """,
        )
        wait_for_database_condition(
            cluster,
            database,
            """
            SELECT EXISTS (
                SELECT 1
                  FROM pg_stat_activity
                 WHERE datname = current_database()
                   AND application_name =
                       'st0003_policy_append_contender'
                   AND wait_event_type = 'Lock'
            );
            """,
        )

        controller.stdin.write(
            f"""
            SELECT pg_advisory_unlock(72003, hashtext('{RULE_ACTIVE}'));
            \\q
            """,
        )
        controller.stdin.close()
        controller_result = finish_psql_process(controller)
        controller = None
        activation_result = finish_psql_process(activation)
        activation = None
        appender_result = finish_psql_process(appender)
        appender = None

        assert controller_result[0] == 0, controller_result
        assert activation_result[0] == 0, activation_result
        assert appender_result[0] != 0, appender_result
        assert "DRAFT bundle" in appender_result[2]
        for result in (activation_result, appender_result):
            assert "40P01" not in result[2]
            assert "deadlock detected" not in result[2].lower()
        assert cluster.query(
            database,
            f"""
            SELECT bundle.status, count(binding.rule_version_id)
              FROM policy.policy_bundle AS bundle
              LEFT JOIN policy.bundle_rule AS binding
                ON binding.policy_bundle_id = bundle.id
             WHERE bundle.id = '{POLICY_DRAFT}'
             GROUP BY bundle.status;
            """,
        ) == "ACTIVE\t1"
    finally:
        stop_psql_process(appender)
        stop_psql_process(activation)
        stop_psql_process(controller)


def test_component_dependency_guard_spans_every_migration_checkpoint(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "dependency_guard_window")
    guarded_trigger_names = (
        DEPENDENCY_GUARD_TRIGGERS + POLICY_CHILD_GUARD_TRIGGERS
    )
    trigger_names = ", ".join(
        f"'{trigger_name}'" for trigger_name in guarded_trigger_names
    )

    def assert_guard_is_live() -> None:
        assert cluster.query(
            database,
            f"""
            SELECT count(*), bool_and(trigger_record.tgenabled = 'O')
              FROM pg_trigger AS trigger_record
              JOIN pg_class AS relation
                ON relation.oid = trigger_record.tgrelid
              JOIN pg_namespace AS namespace
                ON namespace.oid = relation.relnamespace
             WHERE namespace.nspname IN ('ai', 'policy')
               AND trigger_record.tgname IN ({trigger_names})
               AND NOT trigger_record.tgisinternal;
            """,
        ) == f"{len(guarded_trigger_names)}\tt"
        assert cluster.query(
            database,
            """
            SELECT to_regprocedure(
                       'ai.guard_governance_component_dependency()'
                   ) IS NOT NULL,
                   to_regprocedure(
                       'policy.guard_rule_version_immutability()'
                   ) IS NOT NULL,
                   to_regprocedure(
                       'policy.guard_bundle_rule_append_only()'
                   ) IS NOT NULL,
                   has_function_privilege(
                       'public',
                       'ai.guard_governance_component_dependency()',
                       'EXECUTE'
                   ),
                   has_function_privilege(
                       'public',
                       'policy.guard_rule_version_immutability()',
                       'EXECUTE'
                   ),
                   has_function_privilege(
                       'public',
                       'policy.guard_bundle_rule_append_only()',
                       'EXECUTE'
                   );
            """,
        ) == "t\tt\tt\tf\tf\tf"

    apply_sql(cluster, database, EXPAND)
    assert_guard_is_live()
    apply_sql(cluster, database, EXPAND_VALIDATE)
    assert_guard_is_live()
    migrate_automatic_rows(cluster, database)
    classify_ambiguous_legacy_rows(cluster, database)
    apply_sql(cluster, database, CONTRACT_PREPARE)
    assert_guard_is_live()
    apply_sql(cluster, database, CONTRACT)
    assert_guard_is_live()

    apply_sql(cluster, database, DOWNGRADE)
    assert cluster.query(
        database,
        f"""
        SELECT count(*)
          FROM pg_trigger
         WHERE tgname IN ({trigger_names})
           AND NOT tgisinternal;
        """,
    ) == "0"
    assert cluster.query(
        database,
        """
        SELECT to_regprocedure(
                   'ai.guard_governance_component_dependency()'
               ) IS NOT NULL,
               to_regprocedure(
                   'policy.guard_rule_version_immutability()'
               ) IS NOT NULL,
               to_regprocedure(
                   'policy.guard_bundle_rule_append_only()'
               ) IS NOT NULL;
        """,
    ) == "f\tf\tf"


def test_contract_run_start_rejects_non_active_policy_child_graph(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "policy_child_run_start")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    insert_planned_run(cluster, database)
    insert_policy_rule(
        cluster,
        database,
        rule_id=RULE_INVALID,
        suffix="run-start-invalid",
    )
    cluster.psql(
        database,
        f"""
        SET session_replication_role = replica;
        INSERT INTO policy.bundle_rule (
            policy_bundle_id, rule_version_id, execution_order, mode
        ) VALUES ('{POLICY}', '{RULE_INVALID}', 1, 'ENFORCE');
        SET session_replication_role = origin;
        """,
    )

    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.evaluation_run
           SET status = 'RUNNING', started_at = clock_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RUN}';
        """,
        "policy bundle contains a non-ACTIVE rule version",
    )


def test_migrate_batch_is_bounded_and_failed_batch_rolls_back_then_recovers(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "bounded_rollback")
    seed_pending_ai_jobs(cluster, database, 1001)
    apply_sql(cluster, database, EXPAND, EXPAND_VALIDATE)

    before = cluster.query(
        database,
        """
        SELECT count(*) FILTER (WHERE status = 'PENDING'),
               count(*) FILTER (WHERE status = 'REQUESTED')
          FROM ai.ai_job
         WHERE display_id LIKE 'AIJ-ST0003-BATCH-%';
        """,
    )
    migrate_sql = read_sql(MIGRATE_BATCH)
    body, marker, suffix = migrate_sql.rpartition("COMMIT;")
    assert marker == "COMMIT;"
    failed = cluster.psql(
        database,
        body + "\nSELECT 1 / 0;\n" + marker + suffix,
        check=False,
    )
    assert failed.returncode != 0
    assert "division by zero" in failed.stderr
    assert (
        cluster.query(
            database,
            """
            SELECT count(*) FILTER (WHERE status = 'PENDING'),
                   count(*) FILTER (WHERE status = 'REQUESTED')
              FROM ai.ai_job
             WHERE display_id LIKE 'AIJ-ST0003-BATCH-%';
            """,
        )
        == before
    )

    apply_sql(cluster, database, MIGRATE_BATCH)
    assert (
        cluster.query(
            database,
            """
            SELECT count(*) FILTER (WHERE status = 'PENDING'),
                   count(*) FILTER (WHERE status = 'REQUESTED')
              FROM ai.ai_job
             WHERE display_id LIKE 'AIJ-ST0003-BATCH-%';
            """,
        )
        == "1\t1000"
    )
    assert migrate_automatic_rows(cluster, database) == 1
    apply_sql(cluster, database, CONTRACT_PREPARE, CONTRACT)


def test_final_contract_has_exact_resources_states_fks_indexes_and_grants(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "contract_inventory")
    upgrade_st0003(cluster, database)

    actual_tables = set(
        cluster.query(
            database,
            """
            SELECT table_name
              FROM information_schema.tables
             WHERE table_schema = 'ai'
               AND table_name LIKE ANY (
                   ARRAY[
                       'evaluation_suite', 'evaluation_dataset_version',
                       'evaluation_case', 'evaluation_run',
                       'evaluation_case_result', 'human_evaluation',
                       'judge_calibration', 'release_decision',
                       'release_approval'
                   ]
               )
             ORDER BY table_name;
            """,
        ).splitlines()
    )
    assert actual_tables == set(GOVERNANCE_TABLES)

    governance_schema_root = (
        REPOSITORY_ROOT
        / "changes"
        / "st-0003"
        / "contracts"
        / "schemas"
        / "ai-governance"
    )
    for filename, table_name in RESOURCE_TABLES.items():
        schema = json.loads(
            governance_schema_root.joinpath(filename).read_text(encoding="utf-8")
        )
        schema_properties = schema["properties"]
        schema_columns = set(schema_properties)
        database_rows = cluster.query(
            database,
            f"""
            SELECT column_name, data_type, is_nullable, udt_name
              FROM information_schema.columns
             WHERE table_schema = 'ai'
               AND table_name = '{table_name}'
             ORDER BY column_name;
            """,
        ).splitlines()
        database_columns = {
            row.split("\t", 1)[0]
            for row in database_rows
        }
        assert schema_columns == database_columns, (
            filename,
            sorted(schema_columns - database_columns),
            sorted(database_columns - schema_columns),
        )
        for row in database_rows:
            column_name, data_type, is_nullable, _udt_name = row.split("\t")
            property_schema = schema_properties[column_name]
            property_types = property_schema.get("type")
            if isinstance(property_types, str):
                json_types = {property_types}
            else:
                assert isinstance(property_types, list), (
                    filename,
                    column_name,
                    property_schema,
                )
                json_types = set(property_types)

            if data_type in {
                "uuid",
                "text",
                "character varying",
                "date",
                "timestamp with time zone",
                "timestamp without time zone",
            }:
                expected_json_type = "string"
            elif data_type in {"integer", "bigint", "smallint"}:
                expected_json_type = "integer"
            elif data_type in {
                "numeric",
                "real",
                "double precision",
            }:
                expected_json_type = "number"
            elif data_type in {"json", "jsonb"}:
                expected_json_type = "object"
            elif data_type == "ARRAY":
                expected_json_type = "array"
            elif data_type == "boolean":
                expected_json_type = "boolean"
            else:
                raise AssertionError(
                    f"unmapped DB type {data_type} for {table_name}.{column_name}"
                )
            assert expected_json_type in json_types, (
                filename,
                column_name,
                data_type,
                sorted(json_types),
            )

            accepts_null = Draft202012Validator(property_schema).is_valid(None)
            assert accepts_null == (is_nullable == "YES"), (
                filename,
                column_name,
                is_nullable,
                property_schema,
            )

    release_columns = set(
        cluster.query(
            database,
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'ai'
               AND table_name = 'release_decision';
            """,
        ).splitlines()
    )
    assert {
        "resolved_model_id",
        "policy_bundle_version_id",
        "dataset_version_id",
        "code_git_sha",
        "lock_version",
        "judge_calibration_id",
        "rollback_strategy",
        "rollback_runbook_artifact_id",
        "rollback_runbook_sha256",
        "canary_monitoring_artifact_id",
        "canary_monitoring_sha256",
        "canary_evidence_artifact_id",
        "canary_evidence_sha256",
        "canary_started_at",
        "canary_completed_at",
        "canary_started_txid",
        "canary_completed_txid",
        "canary_approval_id",
        "active_approval_id",
    } <= release_columns

    high_risk_binding_columns = {
        "prompt_version": {"author_principal_id"},
        "evaluation_run": {"resolved_model_id"},
        "evaluation_result": {
            "judge_calibration_id",
            "judge_route_version_id",
            "judge_prompt_version_id",
            "judge_rubric_artifact_id",
            "judge_resolved_model_id",
            "judge_grader_version",
        },
        "judge_calibration": {
            "evaluated_task_definition_id",
            "resolved_judge_model_id",
            "rubric_artifact_id",
            "rubric_sha256",
            "grader_version",
        },
        "release_approval": {
            "id",
            "display_id",
            "release_decision_id",
            "phase",
            "decision_manifest_sha256",
            "primary_approver_principal_id",
            "primary_approver_role",
            "second_approver_principal_id",
            "second_approver_role",
            "approval_artifact_id",
            "approval_sha256",
            "signed_at",
            "created_at",
        },
    }
    for table_name, expected_columns in high_risk_binding_columns.items():
        actual_columns = set(
            cluster.query(
                database,
                f"""
                SELECT column_name
                  FROM information_schema.columns
                 WHERE table_schema = 'ai'
                   AND table_name = '{table_name}';
                """,
            ).splitlines()
        )
        assert expected_columns <= actual_columns, (
            table_name,
            sorted(expected_columns - actual_columns),
        )

    constraints = cluster.query(
        database,
        """
        SELECT c.relname, con.conname, pg_get_constraintdef(con.oid),
               con.convalidated
          FROM pg_constraint AS con
          JOIN pg_class AS c ON c.oid = con.conrelid
          JOIN pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = 'ai'
         ORDER BY c.relname, con.conname;
        """,
    ).splitlines()
    assert all(not row.endswith("\tf") for row in constraints)
    rendered_constraints = "\n".join(constraints)
    for state in AI_JOB_STATES | PROMPT_STATES | ROUTE_STATES:
        assert f"'{state}'" in rendered_constraints
    for legacy in ("'PENDING'", "'BLOCKED'"):
        job_rows = [
            row for row in constraints if row.startswith("ai_job\tck_ai_job_status\t")
        ]
        assert len(job_rows) == 1
        assert legacy not in job_rows[0]
    prompt_row = [
        row
        for row in constraints
        if row.startswith("prompt_version\tck_ai_prompt_status\t")
    ]
    assert len(prompt_row) == 1 and "'REJECTED'" not in prompt_row[0]

    invalid_or_unready_indexes = cluster.query(
        database,
        """
        SELECT count(*)
          FROM pg_index AS index
          JOIN pg_class AS table_class ON table_class.oid = index.indrelid
          JOIN pg_namespace AS namespace
            ON namespace.oid = table_class.relnamespace
         WHERE namespace.nspname = 'ai'
           AND table_class.relname IN (
               'evaluation_suite', 'evaluation_dataset_version',
               'evaluation_case', 'evaluation_run',
               'evaluation_case_result', 'human_evaluation',
               'judge_calibration', 'release_decision', 'release_approval'
           )
           AND (NOT index.indisvalid OR NOT index.indisready);
        """,
    )
    assert invalid_or_unready_indexes == "0"

    missing_fk_indexes = cluster.query(
        database,
        """
        WITH foreign_keys AS (
            SELECT con.conrelid, con.conname, con.conkey[1] AS leading_column
              FROM pg_constraint AS con
              JOIN pg_class AS table_class ON table_class.oid = con.conrelid
              JOIN pg_namespace AS namespace
                ON namespace.oid = table_class.relnamespace
             WHERE con.contype = 'f'
               AND namespace.nspname = 'ai'
               AND table_class.relname IN (
                   'evaluation_suite', 'evaluation_dataset_version',
                   'evaluation_case', 'evaluation_run',
                   'evaluation_case_result', 'human_evaluation',
                   'judge_calibration', 'release_decision', 'release_approval'
               )
        )
        SELECT string_agg(foreign_keys.conname, ',' ORDER BY foreign_keys.conname)
          FROM foreign_keys
         WHERE NOT EXISTS (
             SELECT 1
               FROM pg_index AS index
              WHERE index.indrelid = foreign_keys.conrelid
                AND index.indisvalid
                AND index.indisready
                AND index.indkey[0] = foreign_keys.leading_column
         );
        """,
    )
    assert missing_fk_indexes == ""

    expected_triggers = {
        "trg_ai_eval_suite_mutation",
        "trg_ai_judge_cal_mutation",
        "trg_ai_eval_dataset_locked",
        "trg_ai_eval_case_mutation",
        "trg_ai_eval_run_mutation",
        "trg_ai_eval_case_result_open_run",
        "trg_ai_eval_case_result_immutable",
        "trg_ai_human_eval_open_run",
        "trg_ai_human_eval_immutable",
        "trg_ai_eval_metric_mutation",
        "trg_ai_release_decision_mutation",
        "trg_ai_eval_suite_canonical_config",
        "trg_ai_eval_run_start_integrity",
        "trg_ai_judge_cal_scope",
        "trg_ai_release_approval_immutable",
        "trg_ai_eval_run_completion_evidence",
        "trg_ai_release_decision_evidence",
        "trg_ai_task_definition_lifecycle",
        "trg_ai_prompt_version_lifecycle",
        "trg_ai_model_route_lifecycle",
        "trg_ai_output_schema_lifecycle",
        "trg_ai_model_definition_lifecycle",
        "trg_policy_bundle_lifecycle",
    }
    actual_triggers = set(
        cluster.query(
            database,
            f"""
            SELECT trigger.tgname
              FROM pg_trigger AS trigger
             WHERE NOT trigger.tgisinternal
               AND trigger.tgname = ANY (
                   ARRAY{list(sorted(expected_triggers))!r}::text[]
               )
             ORDER BY trigger.tgname;
            """,
        ).splitlines()
    )
    assert actual_triggers == expected_triggers

    assert_sql_fails(
        cluster,
        database,
        """
        INSERT INTO ai.evaluation_suite (
            id, suite_code, version_no, task_definition_id, risk_level, status
        )
        VALUES (
            '00000000-0000-7000-8000-000000000099',
            'suite.st0003.missing-task.v1',
            1,
            '00000000-0000-7000-8000-000000000098',
            'LOW',
            'DRAFT'
        );
        """,
        "fk_ai_eval_suite_task",
    )

    roles = (
        "raos_api_rw",
        "raos_worker_rw",
        "raos_projection_rw",
        "raos_public_ro",
        "raos_reporting_ro",
        "raos_auditor_ro",
    )
    permissions = cluster.query(
        database,
        f"""
        SELECT role_name, table_name,
               has_table_privilege(role_name, 'ai.' || table_name, 'SELECT'),
               has_table_privilege(role_name, 'ai.' || table_name, 'INSERT'),
               has_table_privilege(role_name, 'ai.' || table_name, 'UPDATE'),
               has_table_privilege(role_name, 'ai.' || table_name, 'DELETE')
          FROM unnest(ARRAY{list(roles)!r}::text[]) AS role_name
          CROSS JOIN unnest(ARRAY{list(GOVERNANCE_TABLES)!r}::text[]) AS table_name
         ORDER BY role_name, table_name;
        """,
    ).splitlines()
    for row in permissions:
        role, _table, select, insert, update, delete = row.split("\t")
        if role == "raos_api_rw":
            assert (select, insert, update, delete) == ("t", "t", "t", "f")
        elif role == "raos_worker_rw":
            worker_writable = _table in {
                "evaluation_run",
                "evaluation_case_result",
            }
            assert (select, insert, update, delete) == (
                "t",
                "t" if worker_writable else "f",
                "t" if worker_writable else "f",
                "f",
            )
        elif role == "raos_projection_rw":
            assert (select, insert, update, delete) == ("t", "f", "f", "f")
        else:
            assert (select, insert, update, delete) == ("f", "f", "f", "f")

    assert (
        cluster.query(
            database,
            """
            SELECT has_schema_privilege('raos_public_ro', 'ai', 'USAGE'),
                   has_schema_privilege('raos_public_ro', 'readmodel', 'USAGE');
            """,
        )
        == "f\tt"
    )

    public_acl_entries = cluster.query(
        database,
        """
        WITH public_grants AS (
            SELECT 'schema' AS object_kind,
                   namespace.nspname AS object_name,
                   acl.privilege_type
              FROM pg_namespace AS namespace
              CROSS JOIN LATERAL aclexplode(
                  COALESCE(namespace.nspacl,
                           acldefault('n', namespace.nspowner))
              ) AS acl
             WHERE namespace.nspname = 'ai'
               AND acl.grantee = 0
            UNION ALL
            SELECT table_class.relkind::text,
                   table_class.relname,
                   acl.privilege_type
              FROM pg_class AS table_class
              JOIN pg_namespace AS namespace
                ON namespace.oid = table_class.relnamespace
              CROSS JOIN LATERAL aclexplode(
                  COALESCE(
                      table_class.relacl,
                      acldefault(
                          (
                              CASE
                                  WHEN table_class.relkind = 'S' THEN 'S'
                                  ELSE 'r'
                              END
                          )::"char",
                          table_class.relowner
                      )
                  )
              ) AS acl
             WHERE namespace.nspname = 'ai'
               AND table_class.relkind IN ('r', 'p', 'v', 'm', 'S')
               AND acl.grantee = 0
            UNION ALL
            SELECT 'function', procedure.proname, acl.privilege_type
              FROM pg_proc AS procedure
              JOIN pg_namespace AS namespace
                ON namespace.oid = procedure.pronamespace
              CROSS JOIN LATERAL aclexplode(
                  COALESCE(procedure.proacl,
                           acldefault('f', procedure.proowner))
              ) AS acl
             WHERE namespace.nspname = 'ai'
               AND procedure.proname LIKE 'guard_%'
               AND acl.grantee = 0
        )
        SELECT object_kind, object_name, privilege_type
          FROM public_grants
         ORDER BY object_kind, object_name, privilege_type;
        """,
    )
    assert public_acl_entries == ""


def test_dataset_results_human_labels_and_run_guards_reject_invalid_mutation(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "immutability")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )

    assert_sql_fails(
        cluster,
        database,
        f"UPDATE ai.evaluation_dataset_version SET purpose = 'changed' WHERE id = '{DATASET}';",
        "immutable",
    )
    assert_sql_fails(
        cluster,
        database,
        f"UPDATE ai.evaluation_case SET category = 'changed' WHERE id = '{CASE}';",
        "cannot be mutated",
    )
    assert_sql_fails(
        cluster,
        database,
        f"DELETE FROM ai.evaluation_case WHERE id = '{CASE}';",
        "cannot be mutated",
    )

    cluster.psql(
        database,
        f"""
        INSERT INTO ai.evaluation_run (
            id, display_id, suite_id, dataset_version_id, prompt_version_id,
            model_route_version_id, output_schema_version_id,
            policy_bundle_version_id, code_git_sha, created_by_principal_id,
            resolved_model_id
        )
        VALUES (
            '{RUN}', 'AIR-ST0003-1', '{SUITE}', '{DATASET}', '{PROMPT}',
            '{ROUTE}', '{OUTPUT_SCHEMA}', '{POLICY}', '{CODE_SHA}', '{P1}',
            '{MODEL}'
        );
        UPDATE ai.evaluation_run
           SET status = 'RUNNING', started_at = clock_timestamp(),
               updated_at = clock_timestamp()
         WHERE id = '{RUN}';
        UPDATE ai.evaluation_run
           SET status = 'GRADING', updated_at = clock_timestamp()
         WHERE id = '{RUN}';
        """,
    )
    seed_successful_case_attempts(
        cluster,
        database,
        display_suffix="guard",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.evaluation_run
           SET status = 'COMPLETED', completed_at = clock_timestamp(),
               run_manifest_artifact_id = '{ARTIFACT_REPORT}'
         WHERE id = '{RUN}';
        """,
        "evidence is incomplete",
    )

    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO ai.evaluation_case_result (
            id, evaluation_run_id, evaluation_case_id, ai_attempt_id,
            output_artifact_id, status, disposition,
            zero_tolerance_evidence, zero_tolerance_evidence_artifact_id,
            zero_tolerance_evidence_sha256
        ) VALUES (
            '{RESULT}', '{RUN}', '{CASE}',
            {case_attempt_id_sql("guard")},
            {case_attempt_output_artifact_sql("guard")},
            'PASSED', 'CALL_PROVIDER_AND_FLAG',
            {zero_tolerance_values_sql()}
        );
        """,
        "does not match expected",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO ai.evaluation_case_result (
            id, evaluation_run_id, evaluation_case_id, ai_attempt_id,
            status, disposition, zero_tolerance_evidence,
            zero_tolerance_evidence_artifact_id,
            zero_tolerance_evidence_sha256
        ) VALUES (
            '{RESULT}', '{RUN}', '{CASE}', {case_attempt_id_sql("guard")},
            'PASSED', 'CALL_PROVIDER_AND_PASS',
            {zero_tolerance_values_sql()}
        );
        """,
        "lacks exact successful attempt evidence",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.evaluation_case
           SET expected_disposition = 'BLOCK_BEFORE_PROVIDER'
         WHERE id = '{CASE}';
        SET LOCAL session_replication_role = origin;
        INSERT INTO ai.evaluation_case_result (
            id, evaluation_run_id, evaluation_case_id, ai_attempt_id,
            output_artifact_id, status, disposition,
            zero_tolerance_evidence, zero_tolerance_evidence_artifact_id,
            zero_tolerance_evidence_sha256
        ) VALUES (
            '{RESULT}', '{RUN}', '{CASE}',
            {case_attempt_id_sql("guard")},
            {case_attempt_output_artifact_sql("guard")},
            'PASSED', 'BLOCK_BEFORE_PROVIDER',
            {zero_tolerance_values_sql()}
        );
        COMMIT;
        """,
        "pre-provider block cannot contain attempt/output evidence",
    )

    cluster.psql(
        database,
        f"""
        INSERT INTO ai.evaluation_case_result (
            id, evaluation_run_id, evaluation_case_id, ai_attempt_id,
            output_artifact_id, status, disposition,
            zero_tolerance_evidence, zero_tolerance_evidence_artifact_id,
            zero_tolerance_evidence_sha256
        ) VALUES (
            '{RESULT}', '{RUN}', '{CASE}',
            {case_attempt_id_sql("guard")},
            {case_attempt_output_artifact_sql("guard")},
            'PASSED', 'CALL_PROVIDER_AND_PASS',
            {zero_tolerance_values_sql()}
        );
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO ai.human_evaluation (
            id, evaluation_case_result_id, reviewer_principal_id,
            rubric_version, blind_assignment_key, decision
        )
        VALUES (
            '{HUMAN}', '{RESULT}', '{P1}', 'rubric-v1', 'blind-1', 'PASS'
        );
        """,
        "HUMAN_REVIEW",
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_run
           SET status = 'HUMAN_REVIEW',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RUN}';
        """,
    )
    for reviewer in (P_SERVICE, P_SUSPENDED):
        assert_sql_fails(
            cluster,
            database,
            f"""
            INSERT INTO ai.human_evaluation (
                id, evaluation_case_result_id, reviewer_principal_id,
                rubric_version, blind_assignment_key, decision
            )
            VALUES (
                '{HUMAN}', '{RESULT}', '{reviewer}',
                'rubric-v1', 'blind-1', 'PASS'
            );
            """,
            "ACTIVE USER",
        )
    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO ai.human_evaluation (
            evaluation_case_result_id, reviewer_principal_id,
            rubric_version, blind_assignment_key, scores, decision,
            is_adjudication
        ) VALUES (
            '{RESULT}', '{P1}', 'rubric-v1', 'blind-author-adjudicator',
            '{{"blocking": 1}}'::jsonb, 'PASS', true
        );
        """,
        "prompt author cannot adjudicate",
    )
    cluster.psql(
        database,
        f"""
        INSERT INTO ai.human_evaluation (
            id, evaluation_case_result_id, reviewer_principal_id,
            rubric_version, blind_assignment_key, decision
        )
        VALUES (
            '{HUMAN}', '{RESULT}', '{P1}', 'rubric-v1', 'blind-1', 'PASS'
        );
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"UPDATE ai.evaluation_case_result SET disposition = 'changed' WHERE id = '{RESULT}';",
        "immutable",
    )
    assert_sql_fails(
        cluster,
        database,
        f"DELETE FROM ai.human_evaluation WHERE id = '{HUMAN}';",
        "immutable",
    )

    create_locked_dataset(
        cluster,
        database,
        dataset_id=DATASET_2,
        case_id=CASE_2,
        display_suffix="2",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO ai.evaluation_case_result (
            id, evaluation_run_id, evaluation_case_id, status, disposition,
            zero_tolerance_evidence, zero_tolerance_evidence_artifact_id,
            zero_tolerance_evidence_sha256
        )
        VALUES (
            '{RESULT_2}', '{RUN}', '{CASE_2}', 'PASSED',
            'CALL_PROVIDER_AND_PASS', {zero_tolerance_values_sql()}
        );
        """,
        "does not match run dataset",
    )


def test_case_result_execution_truth_table_and_attempt_provenance_are_exact(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "case_result_truth")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_draft_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO ai.evaluation_case (
            dataset_version_id, case_key, task_definition_id, split,
            category, risk_level, input_artifact_id, gold_artifact_id,
            expected_disposition
        ) VALUES (
            '{DATASET}', 'duplicate-input-artifact', '{TASK}', 'HOLDOUT',
            'ST0003', 'CRITICAL', '{ARTIFACT_INPUT}', '{ARTIFACT_GOLD}',
            'CALL_PROVIDER_AND_PASS'
        );
        """,
        "uq_ai_eval_case_input",
    )

    specialized_cases = [
        cluster.query(
            database,
            f"""
            SELECT id
              FROM ai.evaluation_case
             WHERE dataset_version_id = '{DATASET}'
               AND id <> '{CASE}'
             ORDER BY case_key
             OFFSET {offset} LIMIT 1;
            """,
        )
        for offset in range(5)
    ]
    terminal_case, block_case, flag_case, normal_case, duplicate_case = (
        specialized_cases
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_case
           SET expected_disposition = 'EXPECTED_REFUSAL'
         WHERE id = '{CASE}';
        UPDATE ai.evaluation_case
           SET expected_disposition = 'EXPECTED_TERMINAL_FAILURE'
         WHERE id = '{terminal_case}';
        UPDATE ai.evaluation_case
           SET expected_disposition = 'BLOCK_BEFORE_PROVIDER'
         WHERE id = '{block_case}';
        UPDATE ai.evaluation_case
           SET expected_disposition = 'CALL_PROVIDER_AND_FLAG'
         WHERE id = '{flag_case}';
        """,
    )
    lock_draft_dataset(cluster, database)
    insert_planned_run(cluster, database)
    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_run
           SET status = 'RUNNING', started_at = clock_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RUN}';
        """,
    )
    seed_successful_case_attempts(
        cluster,
        database,
        display_suffix="truth",
    )

    def result_insert_sql(
        case_id: str,
        disposition: str,
        *,
        attempt_sql: str | None = None,
        output_artifact_id: str | None = "__ATTEMPT__",
    ) -> str:
        bound_attempt = (
            case_attempt_id_sql("truth", case_id)
            if attempt_sql is None
            else attempt_sql
        )
        if output_artifact_id == "__ATTEMPT__":
            output_sql = case_attempt_output_artifact_sql("truth", case_id)
        elif output_artifact_id is None:
            output_sql = "NULL"
        else:
            output_sql = f"'{output_artifact_id}'"
        return f"""
            INSERT INTO ai.evaluation_case_result (
                evaluation_run_id, evaluation_case_id, ai_attempt_id,
                output_artifact_id, status, disposition,
                zero_tolerance_evidence,
                zero_tolerance_evidence_artifact_id,
                zero_tolerance_evidence_sha256
            ) VALUES (
                '{RUN}', '{case_id}', {bound_attempt}, {output_sql},
                'PASSED', '{disposition}', {zero_tolerance_values_sql()}
            );
        """

    refusal_attempt = case_attempt_id_sql("truth", CASE)
    terminal_attempt = case_attempt_id_sql("truth", terminal_case)
    normal_attempt = case_attempt_id_sql("truth", normal_case)
    assert_sql_fails(
        cluster,
        database,
        result_insert_sql(CASE, "EXPECTED_REFUSAL"),
        ("refusal", "attempt evidence"),
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.ai_attempt
           SET status = 'REFUSED', output_artifact_id = NULL,
               output_sha256 = NULL, refusal_code = NULL
         WHERE id = {refusal_attempt};
        SET LOCAL session_replication_role = origin;
        {result_insert_sql(CASE, "EXPECTED_REFUSAL", output_artifact_id=None)}
        COMMIT;
        """,
        ("refusal", "attempt evidence"),
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.ai_attempt
           SET status = 'REFUSED', validation_status = 'PASSED',
               output_artifact_id = NULL, output_sha256 = NULL,
               refusal_code = 'SAFETY'
         WHERE id = {refusal_attempt};
        SET LOCAL session_replication_role = origin;
        {result_insert_sql(CASE, "EXPECTED_REFUSAL", output_artifact_id=None)}
        COMMIT;
        """,
        ("refusal", "attempt evidence"),
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.ai_attempt
           SET status = 'REFUSED', refusal_code = 'SAFETY'
         WHERE id = {refusal_attempt};
        SET LOCAL session_replication_role = origin;
        {result_insert_sql(CASE, "EXPECTED_REFUSAL")}
        COMMIT;
        """,
        ("refusal", "attempt evidence"),
    )

    assert_sql_fails(
        cluster,
        database,
        result_insert_sql(terminal_case, "EXPECTED_TERMINAL_FAILURE"),
        ("terminal", "attempt evidence"),
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.ai_attempt
           SET status = 'FAILED', output_artifact_id = NULL,
               output_sha256 = NULL, refusal_code = NULL,
               error_class = NULL, error_code = NULL
         WHERE id = {terminal_attempt};
        SET LOCAL session_replication_role = origin;
        {result_insert_sql(
            terminal_case,
            "EXPECTED_TERMINAL_FAILURE",
            output_artifact_id=None,
        )}
        COMMIT;
        """,
        ("terminal", "attempt evidence"),
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.ai_attempt
           SET status = 'FAILED', validation_status = 'PASSED',
               output_artifact_id = NULL, output_sha256 = NULL,
               refusal_code = NULL, error_class = 'ProviderError',
               error_code = 'E_PROVIDER'
         WHERE id = {terminal_attempt};
        SET LOCAL session_replication_role = origin;
        {result_insert_sql(
            terminal_case,
            "EXPECTED_TERMINAL_FAILURE",
            output_artifact_id=None,
        )}
        COMMIT;
        """,
        ("terminal", "attempt evidence"),
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.ai_attempt
           SET status = 'FAILED', error_class = 'ProviderError',
               error_code = 'E_PROVIDER'
         WHERE id = {terminal_attempt};
        SET LOCAL session_replication_role = origin;
        {result_insert_sql(terminal_case, "EXPECTED_TERMINAL_FAILURE")}
        COMMIT;
        """,
        ("terminal", "attempt evidence"),
    )

    binding_mutations = (
        f"""
        UPDATE ai.ai_job
           SET prompt_version_id = '{JUDGE_PROMPT}'
         WHERE id = (
             SELECT ai_job_id FROM ai.ai_attempt WHERE id = {normal_attempt}
         );
        """,
        f"""
        UPDATE ai.ai_job
           SET model_route_version_id = '{JUDGE_ROUTE}'
         WHERE id = (
             SELECT ai_job_id FROM ai.ai_attempt WHERE id = {normal_attempt}
         );
        """,
        f"""
        UPDATE ai.ai_job
           SET policy_bundle_version_id = uuidv7()
         WHERE id = (
             SELECT ai_job_id FROM ai.ai_attempt WHERE id = {normal_attempt}
         );
        """,
        f"UPDATE ai.ai_attempt SET model_id = '{JUDGE_MODEL}' WHERE id = {normal_attempt};",
        f"""
        UPDATE ai.ai_attempt
           SET resolved_model_id = 'test-judge-model-v1'
         WHERE id = {normal_attempt};
        """,
        f"""
        UPDATE ai.ai_attempt
           SET input_artifact_id = '{ARTIFACT_GOLD}'
         WHERE id = {normal_attempt};
        """,
        f"""
        UPDATE ai.ai_attempt
           SET input_sha256 = repeat('3', 64)
         WHERE id = {normal_attempt};
        """,
        f"""
        UPDATE ai.ai_attempt
           SET output_sha256 = repeat('3', 64)
         WHERE id = {normal_attempt};
        """,
    )
    for mutation in binding_mutations:
        assert_sql_fails(
            cluster,
            database,
            f"""
            BEGIN;
            SET LOCAL session_replication_role = replica;
            {mutation}
            SET LOCAL session_replication_role = origin;
            {result_insert_sql(normal_case, "CALL_PROVIDER_AND_PASS")}
            COMMIT;
            """,
            (
                "binding",
                "provenance",
                "attempt evidence",
                "immutable hashed AI-attempt output",
            ),
        )
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ops.object_artifact
           SET is_immutable = false
         WHERE id = (
             SELECT input_artifact_id
               FROM ai.evaluation_case
              WHERE id = '{normal_case}'
         );
        SET LOCAL session_replication_role = origin;
        {result_insert_sql(normal_case, "CALL_PROVIDER_AND_PASS")}
        COMMIT;
        """,
        ("binding", "provenance", "immutable"),
    )
    assert_sql_fails(
        cluster,
        database,
        result_insert_sql(
            normal_case,
            "CALL_PROVIDER_AND_PASS",
            output_artifact_id=ARTIFACT_GOLD,
        ),
        ("artifact", "attempt evidence", "provenance"),
    )

    insert_planned_run(
        cluster,
        database,
        run_id=RUN_2,
        display_suffix="cross-run",
        resolved_model_id=JUDGE_MODEL,
        model_route_version_id=JUDGE_ROUTE,
        prompt_version_id=JUDGE_PROMPT,
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_run
           SET status = 'RUNNING', started_at = clock_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RUN_2}';
        """,
    )
    seed_successful_case_attempts(
        cluster,
        database,
        run_id=RUN_2,
        display_suffix="cross-run",
    )
    assert_sql_fails(
        cluster,
        database,
        result_insert_sql(
            normal_case,
            "CALL_PROVIDER_AND_PASS",
            attempt_sql=case_attempt_id_sql("cross-run", normal_case),
        ),
        ("binding", "provenance", "attempt evidence"),
    )

    cluster.psql(
        database,
        f"""
        SET session_replication_role = replica;
        UPDATE ai.ai_attempt
           SET status = 'REFUSED', output_artifact_id = NULL,
               output_sha256 = NULL, refusal_code = 'SAFETY',
               validation_status = 'FAILED'
         WHERE id = {refusal_attempt};
        UPDATE ai.ai_attempt
           SET status = 'FAILED', output_artifact_id = NULL,
               output_sha256 = NULL, refusal_code = NULL,
               error_class = 'ProviderError', error_code = 'E_PROVIDER',
               validation_status = 'FAILED'
         WHERE id = {terminal_attempt};
        SET session_replication_role = origin;
        {result_insert_sql(CASE, "EXPECTED_REFUSAL", output_artifact_id=None)}
        {result_insert_sql(
            terminal_case,
            "EXPECTED_TERMINAL_FAILURE",
            output_artifact_id=None,
        )}
        {result_insert_sql(
            block_case,
            "BLOCK_BEFORE_PROVIDER",
            attempt_sql="NULL",
            output_artifact_id=None,
        )}
        {result_insert_sql(flag_case, "CALL_PROVIDER_AND_FLAG")}
        {result_insert_sql(normal_case, "CALL_PROVIDER_AND_PASS")}
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        SET session_replication_role = replica;
        INSERT INTO ai.evaluation_case_result (
            evaluation_run_id, evaluation_case_id, ai_attempt_id,
            output_artifact_id, status, disposition,
            zero_tolerance_evidence, zero_tolerance_evidence_artifact_id,
            zero_tolerance_evidence_sha256
        ) VALUES (
            '{RUN}', '{duplicate_case}',
            {case_attempt_id_sql("truth", duplicate_case)},
            {case_attempt_output_artifact_sql("truth", normal_case)},
            'PASSED', 'CALL_PROVIDER_AND_PASS',
            {zero_tolerance_values_sql()}
        );
        SET session_replication_role = origin;
        """,
        "uq_ai_eval_case_result_output",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        SET session_replication_role = replica;
        {result_insert_sql(
            duplicate_case,
            "CALL_PROVIDER_AND_PASS",
            attempt_sql=normal_attempt,
        )}
        SET session_replication_role = origin;
        """,
        ("ai_attempt", "unique"),
    )
    assert_sql_fails(
        cluster,
        database,
        f"UPDATE ai.ai_attempt SET finish_reason = 'changed' WHERE id = {normal_attempt};",
        ("referenced AI attempt", "immutable"),
    )
    assert_sql_fails(
        cluster,
        database,
        f"DELETE FROM ai.ai_attempt WHERE id = {normal_attempt};",
        ("referenced AI attempt", "immutable"),
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.ai_job
           SET prompt_version_id = '{JUDGE_PROMPT}'
         WHERE id = (
             SELECT ai_job_id FROM ai.ai_attempt WHERE id = {normal_attempt}
         );
        """,
        ("referenced AI job", "execution binding", "immutable"),
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.ai_job
           SET policy_bundle_version_id = uuidv7()
         WHERE id = (
             SELECT ai_job_id FROM ai.ai_attempt WHERE id = {normal_attempt}
         );
        """,
        ("referenced AI job", "execution binding", "immutable"),
    )


def test_zero_tolerance_evidence_is_exact_generated_and_artifact_bound(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "zero_tolerance_shape")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    insert_planned_run(cluster, database)
    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_run
           SET status = 'RUNNING', started_at = clock_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RUN}';
        """,
    )
    seed_successful_case_attempts(
        cluster,
        database,
        display_suffix="zero-tolerance",
    )

    def result_insert_sql(
        evidence_sql: str,
        *,
        status: str = "PASSED",
        evidence_hash_sql: str = "repeat('4', 64)",
        generated_override: bool = False,
    ) -> str:
        generated_column = (
            ", zero_tolerance_failure_count" if generated_override else ""
        )
        generated_value = ", 0" if generated_override else ""
        return f"""
            INSERT INTO ai.evaluation_case_result (
                evaluation_run_id, evaluation_case_id, ai_attempt_id,
                output_artifact_id, status, disposition,
                zero_tolerance_evidence,
                zero_tolerance_evidence_artifact_id,
                zero_tolerance_evidence_sha256{generated_column}
            ) VALUES (
                '{RUN}', '{CASE}',
                {case_attempt_id_sql("zero-tolerance")},
                {case_attempt_output_artifact_sql("zero-tolerance")},
                '{status}', 'CALL_PROVIDER_AND_PASS', {evidence_sql},
                '{ARTIFACT_REPORT}', {evidence_hash_sql}{generated_value}
            );
        """

    zero_evidence = {code: 0 for code in ZERO_TOLERANCE_CODES}
    missing_evidence = zero_evidence | {}
    missing_evidence.pop("AI-POL-004")
    extra_evidence = zero_evidence | {"AI-UNKNOWN-999": 0}
    string_evidence = zero_evidence | {"AI-FCT-001": "0"}
    negative_evidence = zero_evidence | {"AI-FCT-001": -1}
    malformed_evidence_sql = (
        "'[]'::jsonb",
        "'" + json.dumps(missing_evidence) + "'::jsonb",
        "'" + json.dumps(extra_evidence) + "'::jsonb",
        "'" + json.dumps(string_evidence) + "'::jsonb",
        "'" + json.dumps(negative_evidence) + "'::jsonb",
    )
    for evidence_sql in malformed_evidence_sql:
        assert_sql_fails(
            cluster,
            database,
            result_insert_sql(evidence_sql),
            (
                "ck_ai_eval_case_result_zero_tolerance_evidence",
                "ck_ai_eval_case_result_failures",
                "zero_tolerance_failure_count",
            ),
        )

    over_total = zero_evidence | {"AI-FCT-001": 30, "AI-FCT-004": 30}
    assert_sql_fails(
        cluster,
        database,
        result_insert_sql(
            "'" + json.dumps(over_total) + "'::jsonb",
            status="FAILED",
        ),
        "ck_ai_eval_case_result_failures",
    )
    assert_sql_fails(
        cluster,
        database,
        result_insert_sql(zero_tolerance_evidence_sql(1)),
        "ck_ai_eval_case_result_passed_zero_tolerance",
    )
    assert_sql_fails(
        cluster,
        database,
        result_insert_sql(
            zero_tolerance_evidence_sql(),
            generated_override=True,
        ),
        ("generated column", "non-DEFAULT value"),
    )
    assert_sql_fails(
        cluster,
        database,
        result_insert_sql(
            zero_tolerance_evidence_sql(),
            evidence_hash_sql="repeat('3', 64)",
        ),
        "immutable exact-hash artifact",
    )

    cluster.psql(
        database,
        result_insert_sql(zero_tolerance_evidence_sql()),
    )
    assert cluster.query(
        database,
        f"""
        SELECT zero_tolerance_failure_count
          FROM ai.evaluation_case_result
         WHERE evaluation_run_id = '{RUN}'
           AND evaluation_case_id = '{CASE}';
        """,
    ) == "0"


def test_completion_rejects_zero_tolerance_metric_artifact_and_split_gaps(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "zero_tolerance_completion")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    create_evaluation_run(cluster, database, complete=False)
    completion_sql = f"""
        UPDATE ai.evaluation_run
           SET status = 'COMPLETED',
               run_manifest_artifact_id = '{ARTIFACT_REPORT}',
               completed_at = clock_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RUN}';
    """

    mapped_metric_mismatch = f"""
        UPDATE ai.evaluation_result
           SET metric_value = 1,
               proportion_numerator_count = 1,
               proportion_denominator_count = 1
         WHERE evaluation_run_id = '{RUN}'
           AND evaluation_case_id = '{CASE}'
           AND metric_code = 'fabricated_experience_rate';
    """
    forbidden_artifact_mismatch = f"""
        UPDATE ai.evaluation_result
           SET result_artifact_id = '{ARTIFACT_GOLD}'
         WHERE evaluation_run_id = '{RUN}'
           AND evaluation_case_id = '{CASE}'
           AND grader_code = 'grader.forbidden_content.v1';
    """
    missing_zero_tolerance_metric = f"""
        DELETE FROM ai.evaluation_result
         WHERE evaluation_run_id = '{RUN}'
           AND evaluation_case_id = '{CASE}'
           AND metric_code = 'product_identity_accuracy';
    """
    missing_cost_latency_metric = f"""
        DELETE FROM ai.evaluation_result
         WHERE evaluation_run_id = '{RUN}'
           AND evaluation_case_id = '{CASE}'
           AND metric_code = 'latency_p95_ms';
    """
    for evidence_mutation in (
        mapped_metric_mismatch,
        forbidden_artifact_mismatch,
        missing_zero_tolerance_metric,
        missing_cost_latency_metric,
    ):
        assert_sql_fails(
            cluster,
            database,
            f"""
            BEGIN;
            SET LOCAL session_replication_role = replica;
            {evidence_mutation}
            SET LOCAL session_replication_role = origin;
            {completion_sql}
            COMMIT;
            """,
            "evidence is incomplete",
        )

    for split_name in ("DEV", "CALIBRATION"):
        assert_sql_fails(
            cluster,
            database,
            f"""
            BEGIN;
            SET LOCAL session_replication_role = replica;
            DELETE FROM ai.evaluation_result
             WHERE id = (
                 SELECT result.id
                   FROM ai.evaluation_result AS result
                   JOIN ai.evaluation_case AS candidate
                     ON candidate.id = result.evaluation_case_id
                  WHERE result.evaluation_run_id = '{RUN}'
                    AND candidate.split = '{split_name}'
                    AND result.metric_code = 'schema_valid_rate'
                  ORDER BY candidate.case_key
                  LIMIT 1
             );
            SET LOCAL session_replication_role = origin;
            {completion_sql}
            COMMIT;
            """,
            "evidence is incomplete",
        )

    for split_name in ("DEV", "CALIBRATION"):
        assert_sql_fails(
            cluster,
            database,
            f"""
            BEGIN;
            SET LOCAL session_replication_role = replica;
            UPDATE ai.evaluation_case
               SET split = 'HOLDOUT'
             WHERE dataset_version_id = '{DATASET}'
               AND split = '{split_name}';
            SET LOCAL session_replication_role = origin;
            {completion_sql}
            COMMIT;
            """,
            "evidence is incomplete",
        )


def test_dataset_lifecycle_requires_curation_and_freezes_locked_evidence(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "dataset_lifecycle")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_draft_dataset(cluster, database)

    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.evaluation_dataset_version
           SET status = 'ACTIVE',
               locked_by_principal_id = '{P1}',
               locked_at = clock_timestamp()
         WHERE id = '{DATASET}';
        """,
        "lifecycle",
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_dataset_version
           SET status = 'CURATING',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{DATASET}';
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.evaluation_dataset_version
           SET status = 'ACTIVE',
               locked_by_principal_id = '{P1}',
               locked_at = clock_timestamp()
         WHERE id = '{DATASET}';
        """,
        "lifecycle",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.evaluation_dataset_version
           SET status = 'COMPROMISED',
               locked_by_principal_id = '{P1}',
               locked_at = clock_timestamp(),
               compromised_at = clock_timestamp()
         WHERE id = '{DATASET}';
        """,
        "lifecycle",
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_dataset_version
           SET status = 'LOCKED',
               locked_by_principal_id = '{P1}',
               locked_at = clock_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{DATASET}';
        """,
    )
    assert (
        cluster.query(
            database,
            f"""
            SELECT status, case_count
              FROM ai.evaluation_dataset_version
             WHERE id = '{DATASET}';
            """,
        )
        == "LOCKED\t1"
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.evaluation_dataset_version
           SET purpose = 'mutated locked evidence'
         WHERE id = '{DATASET}';
        """,
        "immutable",
    )
    assert_sql_fails(
        cluster,
        database,
        f"DELETE FROM ai.evaluation_case WHERE id = '{CASE}';",
        "cannot be mutated",
    )


def test_suite_and_calibration_lifecycles_require_active_user_approval(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "approval_lifecycle")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )

    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO ai.evaluation_suite (
            id, suite_code, version_no, task_definition_id, risk_level,
            rubric_artifact_id, suite_config, status,
            approved_by_principal_id, approved_at
        )
        VALUES (
            '{SUITE_2}', 'suite.st0003.guard.v1', 1, '{TASK}', 'CRITICAL',
            '{ARTIFACT_REPORT}',
            ai.canonical_suite_config('ai.article_draft.v1'),
            'ACTIVE', '{P1}', clock_timestamp()
        );
        """,
        "created in DRAFT",
    )
    cluster.psql(
        database,
        f"""
        INSERT INTO ai.evaluation_suite (
            id, suite_code, version_no, task_definition_id, risk_level,
            rubric_artifact_id, suite_config, status
        )
        VALUES (
            '{SUITE_2}', 'suite.st0003.guard.v1', 1, '{TASK}', 'CRITICAL',
            '{ARTIFACT_REPORT}',
            ai.canonical_suite_config('ai.article_draft.v1'), 'DRAFT'
        );
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.evaluation_suite
           SET status = 'ACTIVE',
               approved_by_principal_id = '{P1}',
               approved_at = clock_timestamp()
         WHERE id = '{SUITE_2}';
        """,
        "lifecycle",
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_suite
           SET status = 'LOCKED',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{SUITE_2}';
        """,
    )
    for approver in (P_SERVICE, P_SUSPENDED):
        assert_sql_fails(
            cluster,
            database,
            f"""
            UPDATE ai.evaluation_suite
               SET status = 'ACTIVE',
                   approved_by_principal_id = '{approver}',
                   approved_at = clock_timestamp()
             WHERE id = '{SUITE_2}';
            """,
            "ACTIVE USER",
        )
    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_suite
           SET status = 'ACTIVE',
               approved_by_principal_id = '{P1}',
               approved_at = clock_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{SUITE_2}';
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.evaluation_suite
           SET suite_config = '{{"mutated": true}}'::jsonb
         WHERE id = '{SUITE_2}';
        """,
        "frozen task catalog",
    )
    assert_sql_fails(
        cluster,
        database,
        f"UPDATE ai.evaluation_suite SET status = 'LOCKED' WHERE id = '{SUITE_2}';",
        "lifecycle",
    )

    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO ai.judge_calibration (
            id, display_id, judge_route_version_id, judge_prompt_version_id,
            dataset_version_id, weighted_kappa,
            zero_tolerance_false_pass_rate,
            zero_tolerance_false_fail_rate, case_count, status,
            report_artifact_id, approved_by_principal_id, approved_at,
            expires_at, evaluated_task_definition_id,
            resolved_judge_model_id, rubric_artifact_id, rubric_sha256,
            grader_version
        )
        VALUES (
            '{CALIBRATION_2}', 'AIC-ST0003-2', '{JUDGE_ROUTE}',
            '{JUDGE_PROMPT}',
            '{DATASET}', 0.9, 0, 0, 200, 'PASSED',
            '{ARTIFACT_REPORT}', '{P1}', clock_timestamp(),
            clock_timestamp() + interval '30 days', '{TASK}', '{JUDGE_MODEL}',
            '{ARTIFACT_REPORT}', repeat('4', 64), 'grader.model_judge.v1'
        );
        """,
        "created in DRAFT",
    )
    cluster.psql(
        database,
        f"""
        INSERT INTO ai.judge_calibration (
            id, display_id, judge_route_version_id, judge_prompt_version_id,
            dataset_version_id, case_count, status,
            evaluated_task_definition_id, resolved_judge_model_id,
            rubric_artifact_id, rubric_sha256, grader_version
        )
        VALUES (
            '{CALIBRATION}', 'AIC-ST0003-1', '{JUDGE_ROUTE}',
            '{JUDGE_PROMPT}', '{DATASET}', 200, 'DRAFT', '{TASK}',
            '{JUDGE_MODEL}', '{ARTIFACT_REPORT}', repeat('4', 64),
            'grader.model_judge.v1'
        );
        """,
    )
    for approver in (P_SERVICE, P_SUSPENDED):
        assert_sql_fails(
            cluster,
            database,
            f"""
            UPDATE ai.judge_calibration
               SET status = 'PASSED',
                   weighted_kappa = 0.9,
                   zero_tolerance_false_pass_rate = 0,
                   zero_tolerance_false_fail_rate = 0,
                   report_artifact_id = '{ARTIFACT_REPORT}',
                   approved_by_principal_id = '{approver}',
                   approved_at = statement_timestamp(),
                   expires_at = clock_timestamp() + interval '30 days'
             WHERE id = '{CALIBRATION}';
            """,
            "ACTIVE USER",
        )

    invalid_thresholds = (
        ("199", "0.70", "0.01", "0.05", f"'{ARTIFACT_REPORT}'",
         "clock_timestamp() + interval '30 days'", "ck_ai_judge_cal_approval"),
        ("200", "0.699999", "0.01", "0.05", f"'{ARTIFACT_REPORT}'",
         "clock_timestamp() + interval '30 days'", "ck_ai_judge_cal_approval"),
        ("200", "0.70", "0.010001", "0.05", f"'{ARTIFACT_REPORT}'",
         "clock_timestamp() + interval '30 days'", "ck_ai_judge_cal_approval"),
        ("200", "0.70", "0.01", "0.050001", f"'{ARTIFACT_REPORT}'",
         "clock_timestamp() + interval '30 days'", "ck_ai_judge_cal_approval"),
        ("200", "0.70", "0.01", "0.05", "NULL",
         "clock_timestamp() + interval '30 days'", "ck_ai_judge_cal_approval"),
        ("200", "0.70", "0.01", "0.05", f"'{ARTIFACT_REPORT}'",
         "NULL", "ck_ai_judge_cal_approval"),
        ("200", "0.70", "0.01", "0.05", f"'{ARTIFACT_REPORT}'",
         "clock_timestamp() - interval '1 day'",
         "ck_ai_judge_cal_expiry_time"),
    )
    for (
        case_count,
        weighted_kappa,
        false_pass_rate,
        false_fail_rate,
        report_artifact,
        expires_at,
        constraint_name,
    ) in invalid_thresholds:
        assert_sql_fails(
            cluster,
            database,
            f"""
            UPDATE ai.judge_calibration
               SET status = 'PASSED',
                   case_count = {case_count},
                   weighted_kappa = {weighted_kappa},
                   zero_tolerance_false_pass_rate = {false_pass_rate},
                   zero_tolerance_false_fail_rate = {false_fail_rate},
                   report_artifact_id = {report_artifact},
                   approved_by_principal_id = '{P1}',
                   approved_at = statement_timestamp(),
                   expires_at = {expires_at}
             WHERE id = '{CALIBRATION}';
            """,
            (
                constraint_name,
                "canonical scope/evidence",
                "missing scope binding",
            ),
        )
    cluster.psql(
        database,
        f"""
        UPDATE ai.judge_calibration
           SET status = 'PASSED',
               case_count = 200,
               weighted_kappa = 0.70,
               zero_tolerance_false_pass_rate = 0.01,
               zero_tolerance_false_fail_rate = 0.05,
               report_artifact_id = '{ARTIFACT_REPORT}',
               approved_by_principal_id = '{P1}',
               approved_at = statement_timestamp(),
               expires_at = clock_timestamp() + interval '30 days',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{CALIBRATION}';
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.judge_calibration
           SET weighted_kappa = 0.8
         WHERE id = '{CALIBRATION}';
        """,
        "immutable",
    )
    assert_sql_fails(
        cluster,
        database,
        f"UPDATE ai.judge_calibration SET status = 'DRAFT' WHERE id = '{CALIBRATION}';",
        "lifecycle",
    )


def test_dataset_lock_race_serializes_case_writer_and_prevents_late_case(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "dataset_lock_race")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_draft_dataset(cluster, database)
    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_dataset_version
           SET status = 'CURATING',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{DATASET}';
        """,
    )

    lock_key = 76000301
    controller: subprocess.Popen[str] | None = None
    locker: subprocess.Popen[str] | None = None
    contender: subprocess.Popen[str] | None = None
    try:
        controller = start_advisory_controller(
            cluster,
            database,
            lock_key=lock_key,
            application_name="st0003_dataset_race_controller",
        )
        locker = start_psql_script(
            cluster,
            database,
            f"""
            SET application_name = 'st0003_dataset_locker';
            SET statement_timeout = '10s';
            BEGIN;
            UPDATE ai.evaluation_dataset_version
               SET status = 'LOCKED',
                   locked_by_principal_id = '{P1}',
                   locked_at = clock_timestamp(),
                   lock_version = lock_version + 1,
                   updated_at = clock_timestamp()
             WHERE id = '{DATASET}';
            SELECT pg_advisory_lock({lock_key});
            COMMIT;
            """,
        )
        wait_for_database_condition(
            cluster,
            database,
            """
            SELECT EXISTS (
                SELECT 1
                  FROM pg_stat_activity AS activity
                  JOIN pg_locks AS lock ON lock.pid = activity.pid
                 WHERE activity.datname = current_database()
                   AND activity.application_name = 'st0003_dataset_locker'
                   AND lock.locktype = 'advisory'
                   AND NOT lock.granted
            );
            """,
        )

        contender = start_psql_script(
            cluster,
            database,
            f"""
            SET application_name = 'st0003_case_contender';
            SET statement_timeout = '10s';
            INSERT INTO ai.evaluation_case (
                id, dataset_version_id, case_key, task_definition_id, split,
                category, risk_level, input_artifact_id, gold_artifact_id,
                expected_disposition
            )
            VALUES (
                '{CASE_2}', '{DATASET}', 'case-race', '{TASK}', 'HOLDOUT',
                'ST0003', 'CRITICAL', '{ARTIFACT_INPUT}', '{ARTIFACT_GOLD}',
                'CALL_PROVIDER_AND_PASS'
            );
            """,
        )
        wait_for_database_condition(
            cluster,
            database,
            """
            SELECT EXISTS (
                SELECT 1
                  FROM pg_stat_activity
                 WHERE datname = current_database()
                   AND application_name = 'st0003_case_contender'
                   AND wait_event_type = 'Lock'
            );
            """,
        )

        controller_result = release_advisory_controller(
            controller,
            lock_key=lock_key,
        )
        controller = None
        locker_result = finish_psql_process(locker)
        locker = None
        contender_result = finish_psql_process(contender)
        contender = None

        assert controller_result[0] == 0, controller_result
        assert locker_result[0] == 0, locker_result
        assert contender_result[0] != 0, contender_result
        assert "LOCKED" in contender_result[2], contender_result
        assert (
            cluster.query(
                database,
                f"""
                SELECT dataset.status, count(case_row.id)
                  FROM ai.evaluation_dataset_version AS dataset
                  LEFT JOIN ai.evaluation_case AS case_row
                    ON case_row.dataset_version_id = dataset.id
                 WHERE dataset.id = '{DATASET}'
                 GROUP BY dataset.status;
                """,
            )
            == "LOCKED\t1"
        )
    finally:
        stop_psql_process(contender)
        stop_psql_process(locker)
        stop_psql_process(controller)


def test_run_completion_race_commits_before_waiting_result_is_rechecked(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "run_completion_race")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    create_evaluation_run(cluster, database, complete=False)
    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_run
           SET status = 'GRADING',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RUN}';
        """,
    )

    lock_key = 76000302
    controller: subprocess.Popen[str] | None = None
    completer: subprocess.Popen[str] | None = None
    contender: subprocess.Popen[str] | None = None
    try:
        controller = start_advisory_controller(
            cluster,
            database,
            lock_key=lock_key,
            application_name="st0003_run_race_controller",
        )
        completer = start_psql_script(
            cluster,
            database,
            f"""
            SET application_name = 'st0003_run_completer';
            SET statement_timeout = '10s';
            BEGIN;
            UPDATE ai.evaluation_run
               SET status = 'COMPLETED',
                   run_manifest_artifact_id = '{ARTIFACT_REPORT}',
                   completed_at = clock_timestamp(),
                   lock_version = lock_version + 1,
                   updated_at = clock_timestamp()
             WHERE id = '{RUN}';
            SELECT pg_advisory_lock({lock_key});
            COMMIT;
            """,
        )
        wait_for_database_condition(
            cluster,
            database,
            """
            SELECT EXISTS (
                SELECT 1
                  FROM pg_stat_activity AS activity
                  JOIN pg_locks AS lock ON lock.pid = activity.pid
                 WHERE activity.datname = current_database()
                   AND activity.application_name = 'st0003_run_completer'
                   AND lock.locktype = 'advisory'
                   AND NOT lock.granted
            );
            """,
        )

        contender = start_psql_script(
            cluster,
            database,
            f"""
            SET application_name = 'st0003_result_contender';
            SET statement_timeout = '10s';
            INSERT INTO ai.evaluation_case_result (
                id, evaluation_run_id, evaluation_case_id,
                status, disposition, zero_tolerance_evidence,
                zero_tolerance_evidence_artifact_id,
                zero_tolerance_evidence_sha256
            )
            VALUES (
                '{RESULT_2}', '{RUN}', '{CASE}',
                'PASSED', 'CALL_PROVIDER_AND_PASS',
                {zero_tolerance_values_sql()}
            );
            """,
        )
        wait_for_database_condition(
            cluster,
            database,
            """
            SELECT EXISTS (
                SELECT 1
                  FROM pg_stat_activity
                 WHERE datname = current_database()
                   AND application_name = 'st0003_result_contender'
                   AND wait_event_type = 'Lock'
            );
            """,
        )

        controller_result = release_advisory_controller(
            controller,
            lock_key=lock_key,
        )
        controller = None
        completer_result = finish_psql_process(completer)
        completer = None
        contender_result = finish_psql_process(contender)
        contender = None

        assert controller_result[0] == 0, controller_result
        assert completer_result[0] == 0, completer_result
        assert contender_result[0] != 0, contender_result
        assert "COMPLETED" in contender_result[2], contender_result
        assert (
            cluster.query(
                database,
                f"""
                SELECT run.status, count(result.id)
                  FROM ai.evaluation_run AS run
                  LEFT JOIN ai.evaluation_case_result AS result
                    ON result.evaluation_run_id = run.id
                 WHERE run.id = '{RUN}'
                 GROUP BY run.status;
                """,
            )
            == "COMPLETED\t200"
        )
    finally:
        stop_psql_process(contender)
        stop_psql_process(completer)
        stop_psql_process(controller)


def test_run_start_rejects_ineligible_mismatched_and_unresolved_bindings(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "run_start_integrity")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    insert_planned_run(cluster, database)

    ineligible_mutations = (
        f"UPDATE ai.task_definition SET status = 'PAUSED' WHERE id = '{TASK}';",
        f"UPDATE ai.prompt_version SET status = 'SUSPENDED' WHERE id = '{PROMPT}';",
        f"UPDATE ai.model_route_version SET status = 'PAUSED' WHERE id = '{ROUTE}';",
        f"UPDATE ai.output_schema_version SET status = 'RETIRED' WHERE id = '{OUTPUT_SCHEMA}';",
        f"UPDATE policy.policy_bundle SET status = 'RETIRED' WHERE id = '{POLICY}';",
        f"UPDATE ai.model_definition SET status = 'BLOCKED' WHERE id = '{MODEL}';",
        f"UPDATE iam.principal SET status = 'SUSPENDED' WHERE id = '{P1}';",
    )
    for mutation in ineligible_mutations:
        assert_sql_fails(
            cluster,
            database,
            f"""
            BEGIN;
            {mutation}
            UPDATE ai.evaluation_run
               SET status = 'RUNNING', started_at = clock_timestamp(),
                   lock_version = lock_version + 1,
                   updated_at = clock_timestamp()
             WHERE id = '{RUN}';
            COMMIT;
            """,
            "eligible active/candidate bindings",
        )

    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.task_definition SET risk_level = 'HIGH' WHERE id = '{TASK}';
        SET LOCAL session_replication_role = origin;
        UPDATE ai.evaluation_run
           SET status = 'RUNNING', started_at = clock_timestamp(),
               lock_version = lock_version + 1, updated_at = clock_timestamp()
         WHERE id = '{RUN}';
        COMMIT;
        """,
        "bindings disagree on task/schema/model",
    )

    cluster.psql(
        database,
        f"""
        INSERT INTO ai.task_definition (
            id, task_code, name, description, risk_level,
            output_schema_code, default_max_tokens, default_max_cost_jpy,
            human_review_required, status
        )
        VALUES (
            '{TASK_2}', 'ai.opportunity_assessment.v1', 'Other task',
            'Task mismatch fixture', 'HIGH', 'ai.other.v1', 1000, 100,
            true, 'PAUSED'
        );
        UPDATE ai.task_definition SET status = 'ACTIVE' WHERE id = '{TASK_2}';
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.model_route_version
           SET task_definition_id = '{TASK_2}'
         WHERE id = '{ROUTE}';
        SET LOCAL session_replication_role = origin;
        UPDATE ai.evaluation_run
           SET status = 'RUNNING', started_at = clock_timestamp(),
               lock_version = lock_version + 1, updated_at = clock_timestamp()
         WHERE id = '{RUN}';
        COMMIT;
        """,
        "bindings disagree on task/schema/model",
    )

    for route_config_sql in (
        "'{}'::jsonb",
        "'{\"canary_max_percent\": 10.5}'::jsonb",
        "'{\"canary_max_percent\": -1}'::jsonb",
        "'{\"canary_max_percent\": 101}'::jsonb",
        "'{\"canary_max_percent\": \"10\"}'::jsonb",
    ):
        assert_sql_fails(
            cluster,
            database,
            f"""
            BEGIN;
            SET LOCAL session_replication_role = replica;
            UPDATE ai.model_route_version
               SET route_config = {route_config_sql}
             WHERE id = '{ROUTE}';
            SET LOCAL session_replication_role = origin;
            UPDATE ai.evaluation_run
               SET status = 'RUNNING', started_at = clock_timestamp(),
                   lock_version = lock_version + 1,
                   updated_at = clock_timestamp()
             WHERE id = '{RUN}';
            COMMIT;
            """,
            "route canary_max_percent is missing or invalid",
        )

    insert_planned_run(
        cluster,
        database,
        run_id=RUN_2,
        display_suffix="wrong-model",
        resolved_model_id=JUDGE_MODEL,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.evaluation_run
           SET status = 'RUNNING', started_at = clock_timestamp(),
               lock_version = lock_version + 1, updated_at = clock_timestamp()
         WHERE id = '{RUN_2}';
        """,
        "bindings disagree on task/schema/model",
    )

    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_run
           SET status = 'RUNNING', started_at = clock_timestamp(),
               lock_version = lock_version + 1, updated_at = clock_timestamp()
         WHERE id = '{RUN}';
        """,
    )
    assert cluster.query(
        database,
        f"SELECT status FROM ai.evaluation_run WHERE id = '{RUN}';",
    ) == "RUNNING"


def test_referenced_ai_versions_are_immutable_and_worker_cannot_write_authority(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "reference_authority")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)

    mutations = (
        (
            f"UPDATE ops.object_artifact SET sha256 = repeat('e', 64) WHERE id = '{ARTIFACT_REPORT}';",
            "immutable table ops.object_artifact",
        ),
        (
            f"UPDATE ai.task_definition SET risk_level = 'HIGH' WHERE id = '{TASK}';",
            "referenced/non-paused task definition is immutable",
        ),
        (
            f"UPDATE ai.prompt_version SET template_sha256 = repeat('f', 64) WHERE id = '{PROMPT}';",
            "reviewed prompt content hashes are immutable",
        ),
        (
            f"UPDATE ai.model_route_version SET route_config = '{{}}'::jsonb WHERE id = '{ROUTE}';",
            "evaluated model route content is immutable",
        ),
        (
            f"UPDATE ai.output_schema_version SET schema_sha256 = repeat('f', 64) WHERE id = '{OUTPUT_SCHEMA}';",
            "active output schema content hash is immutable",
        ),
        (
            f"UPDATE ai.model_definition SET capabilities = '{{}}'::jsonb WHERE id = '{MODEL}';",
            "referenced provider model snapshot is immutable",
        ),
        (
            f"UPDATE policy.policy_bundle SET bundle_sha256 = repeat('f', 64) WHERE id = '{POLICY}';",
            "approved policy bundle hashes are immutable",
        ),
    )
    for statement, message in mutations:
        assert_sql_fails(cluster, database, statement, message)

    for route_config_sql in (
        "'{}'::jsonb",
        "'{\"canary_max_percent\": 1.5}'::jsonb",
        "'{\"canary_max_percent\": -1}'::jsonb",
        "'{\"canary_max_percent\": 101}'::jsonb",
        "'{\"canary_max_percent\": \"10\"}'::jsonb",
    ):
        assert_sql_fails(
            cluster,
            database,
            f"""
            BEGIN;
            INSERT INTO ai.model_route_version (
                route_code, version_no, task_definition_id, primary_model_id,
                route_config, per_job_budget_jpy, status
            ) VALUES (
                'route.st0003.invalid', 1, '{TASK}', '{MODEL}',
                {route_config_sql}, 1, 'DRAFT'
            );
            UPDATE ai.model_route_version
               SET status = 'EVALUATING', lock_version = lock_version + 1,
                   updated_at = clock_timestamp()
             WHERE route_code = 'route.st0003.invalid';
            COMMIT;
            """,
            "integer canary_max_percent 0..100",
        )

    assert_sql_fails(
        cluster,
        database,
        """
        INSERT INTO ai.task_definition (
            task_code, name, description, risk_level, output_schema_code,
            default_max_tokens, default_max_cost_jpy, status
        ) VALUES (
            'ai.direct_active.v1', 'Direct active', 'Forbidden direct state',
            'LOW', 'ai.direct_active.v1', 1, 0, 'ACTIVE'
        );
        """,
        "must be created PAUSED",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO ai.prompt_version (
            display_id, task_definition_id, prompt_code, version_no,
            git_path, git_commit_sha, template_sha256, status, locale,
            compiler_version, input_contract_sha256, policy_test_status,
            author_principal_id
        ) VALUES (
            'PRM-ST0003-DIRECT', '{TASK}', 'PROMPT-ST0003-DIRECT', 1,
            'prompts/direct.md', repeat('1', 40), repeat('2', 64),
            'CERTIFIED', 'ja-JP', 'test-1', repeat('3', 64), 'PASSED', '{P1}'
        );
        """,
        "human-authored in DRAFT",
    )

    for table_name in (
        "human_evaluation",
        "judge_calibration",
        "release_decision",
        "release_approval",
    ):
        assert_sql_fails(
            cluster,
            database,
            f"SET ROLE raos_worker_rw; INSERT INTO ai.{table_name} DEFAULT VALUES;",
            "permission denied",
        )

    authority_rows = (
        ("ai.task_definition", TASK),
        ("ai.prompt_version", PROMPT),
        ("ai.model_route_version", ROUTE),
        ("ai.output_schema_version", OUTPUT_SCHEMA),
        ("ai.model_definition", MODEL),
        ("policy.policy_bundle", POLICY),
    )
    for relation, row_id in authority_rows:
        for statement in (
            f"UPDATE {relation} SET status = status WHERE id = '{row_id}';",
            f"DELETE FROM {relation} WHERE id = '{row_id}';",
            f"INSERT INTO {relation} DEFAULT VALUES;",
        ):
            assert_sql_fails(
                cluster,
                database,
                f"SET ROLE raos_worker_rw; {statement}",
                "permission denied",
            )

    assert cluster.query(
        database,
        """
        SELECT relation_name,
               has_table_privilege(
                   'raos_worker_rw', relation_name, 'INSERT'
               ),
               has_table_privilege(
                   'raos_worker_rw', relation_name, 'UPDATE'
               ),
               has_table_privilege(
                   'raos_worker_rw', relation_name, 'DELETE'
               )
          FROM (VALUES
              ('ai.task_definition'),
              ('ai.prompt_version'),
              ('ai.model_route_version'),
              ('ai.output_schema_version'),
              ('ai.model_definition'),
              ('policy.policy_bundle')
          ) AS authority(relation_name)
         ORDER BY relation_name;
        """,
    ).splitlines() == [
        "ai.model_definition\tf\tf\tf",
        "ai.model_route_version\tf\tf\tf",
        "ai.output_schema_version\tf\tf\tf",
        "ai.prompt_version\tf\tf\tf",
        "ai.task_definition\tf\tf\tf",
        "policy.policy_bundle\tf\tf\tf",
    ]
    assert cluster.query(
        database,
        """
        SELECT relation_name, column_name,
               has_column_privilege(
                   'raos_worker_rw', relation_name, column_name, 'UPDATE'
               )
          FROM (VALUES
              ('ai.task_definition', 'status'),
              ('ai.prompt_version', 'status'),
              ('ai.prompt_version', 'approved_by_principal_id'),
              ('ai.prompt_version', 'approved_at'),
              ('ai.model_route_version', 'status'),
              ('ai.model_route_version', 'approved_by_principal_id'),
              ('ai.output_schema_version', 'status'),
              ('ai.model_definition', 'status'),
              ('policy.policy_bundle', 'status'),
              ('policy.policy_bundle', 'approved_by_principal_id'),
              ('policy.policy_bundle', 'approved_at')
          ) AS authority(relation_name, column_name)
         ORDER BY relation_name, column_name;
        """,
    ).splitlines() == [
        "ai.model_definition\tstatus\tf",
        "ai.model_route_version\tapproved_by_principal_id\tf",
        "ai.model_route_version\tstatus\tf",
        "ai.output_schema_version\tstatus\tf",
        "ai.prompt_version\tapproved_at\tf",
        "ai.prompt_version\tapproved_by_principal_id\tf",
        "ai.prompt_version\tstatus\tf",
        "ai.task_definition\tstatus\tf",
        "policy.policy_bundle\tapproved_at\tf",
        "policy.policy_bundle\tapproved_by_principal_id\tf",
        "policy.policy_bundle\tstatus\tf",
    ]
    assert cluster.query(
        database,
        """
        SELECT relation_name,
               has_table_privilege(
                   'raos_worker_rw', relation_name, 'INSERT'
               ),
               has_table_privilege(
                   'raos_worker_rw', relation_name, 'UPDATE'
               ),
               has_table_privilege(
                   'raos_worker_rw', relation_name, 'DELETE'
               )
          FROM (VALUES
              ('ai.evaluation_run'),
              ('ai.evaluation_case_result')
          ) AS data_plane(relation_name)
         ORDER BY relation_name;
        """,
    ).splitlines() == [
        "ai.evaluation_case_result\tt\tt\tf",
        "ai.evaluation_run\tt\tt\tf",
    ]

    assert cluster.query(
        database,
        """
        SELECT role_name,
               has_function_privilege(
                   role_name, 'ai.canonical_suite_risk(text)', 'EXECUTE'
               ),
               has_function_privilege(
                   role_name, 'ai.canonical_suite_config(text)', 'EXECUTE'
               ),
               has_function_privilege(
                   role_name,
                   'ai.canonical_grader_output_metrics(text)',
                   'EXECUTE'
               ),
               has_function_privilege(
                   role_name,
                   'ai.assert_evaluation_run_evidence(uuid,boolean)',
                   'EXECUTE'
               ),
               has_function_privilege(
                   role_name,
                   'ai.artifact_matches_immutable_hash(uuid,text)',
                   'EXECUTE'
               ),
               has_function_privilege(
                   role_name,
                   'ai.has_live_rollback_dependents(text,uuid)',
                   'EXECUTE'
               )
          FROM (VALUES ('raos_api_rw'), ('raos_worker_rw')) AS role(role_name)
         ORDER BY role_name;
        """,
    ).splitlines() == [
        "raos_api_rw\tt\tt\tt\tt\tt\tt",
        "raos_worker_rw\tt\tt\tt\tf\tf\tf",
    ]


def test_worker_can_complete_a_run_through_nested_artifact_verification(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "worker_run_completion")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    create_evaluation_run(cluster, database, complete=False)

    cluster.psql(
        database,
        f"""
        SET ROLE raos_worker_rw;
        UPDATE ai.evaluation_run
           SET status = 'GRADING',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RUN}';
        UPDATE ai.evaluation_run
           SET status = 'COMPLETED',
               run_manifest_artifact_id = '{ARTIFACT_REPORT}',
               completed_at = clock_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RUN}';
        RESET ROLE;
        """,
    )
    assert cluster.query(
        database,
        f"SELECT status FROM ai.evaluation_run WHERE id = '{RUN}';",
    ) == "COMPLETED"


def test_metric_provenance_thresholds_and_model_judge_calibration_are_exact(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "metric_judge_provenance")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    create_passed_calibration(cluster, database)
    create_evaluation_run(cluster, database, complete=False)

    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.evaluation_result
           SET case_key = case_key || '-forged'
         WHERE id = (
             SELECT id
               FROM ai.evaluation_result
              WHERE evaluation_run_id = '{RUN}'
                AND evaluation_case_id = '{CASE}'
                AND metric_code = 'schema_valid_rate'
              LIMIT 1
         );
        INSERT INTO ai.evaluation_result (
            suite_code, suite_version, run_id, task_definition_id,
            model_route_version_id, prompt_version_id, case_key,
            metric_code, metric_value, passed, details, result_artifact_id,
            evaluation_run_id, evaluation_case_id, grader_code, slice_key,
            threshold_operator, threshold_value, judge_calibration_id,
            judge_route_version_id, judge_prompt_version_id,
            judge_rubric_artifact_id, judge_resolved_model_id,
            judge_grader_version, proportion_numerator_count,
            proportion_denominator_count
        )
        SELECT result.suite_code, result.suite_version, result.run_id,
               result.task_definition_id, result.model_route_version_id,
               result.prompt_version_id, candidate.case_key,
               result.metric_code, result.metric_value, result.passed,
               result.details, result.result_artifact_id,
               result.evaluation_run_id, result.evaluation_case_id,
               result.grader_code, result.slice_key,
               result.threshold_operator, result.threshold_value,
               result.judge_calibration_id, result.judge_route_version_id,
               result.judge_prompt_version_id,
               result.judge_rubric_artifact_id,
               result.judge_resolved_model_id,
               result.judge_grader_version,
               result.proportion_numerator_count,
               result.proportion_denominator_count
          FROM ai.evaluation_result AS result
          JOIN ai.evaluation_case AS candidate
            ON candidate.id = result.evaluation_case_id
         WHERE result.evaluation_run_id = '{RUN}'
           AND result.evaluation_case_id = '{CASE}'
           AND result.metric_code = 'schema_valid_rate';
        COMMIT;
        """,
        "uq_ai_eval_result_run_case_metric",
    )

    for invalid_metric in (
        canonical_metric_insert_sql(
            grader_code="grader.cost_latency.v1",
            metric_code="latency_p95_ms",
            metric_value="'NaN'::numeric",
            passed="NULL",
            threshold_operator=None,
            threshold_value="NULL",
            proportion_numerator_sql="NULL",
            proportion_denominator_sql="NULL",
        ),
        canonical_metric_insert_sql(
            grader_code="grader.cost_latency.v1",
            metric_code="cost_jpy_p95",
            metric_value="'Infinity'::numeric",
            passed="NULL",
            threshold_operator=None,
            threshold_value="NULL",
            proportion_numerator_sql="NULL",
            proportion_denominator_sql="NULL",
        ),
        canonical_metric_insert_sql(
            grader_code="grader.resource_reference.v1",
            metric_code="evidence_reference_precision",
            metric_value="1.1",
        ),
        canonical_metric_insert_sql(
            grader_code="grader.human_rubric.v1",
            metric_code="intent_coverage",
            metric_value="0",
            threshold_value="1",
        ),
    ):
        assert_sql_fails(
            cluster,
            database,
            invalid_metric,
            (
                "outside its catalog unit",
                "numeric field overflow",
                "requires valid numerator/denominator counts",
            ),
        )

    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(
            grader_code="grader.model_judge.v1",
            metric_code="intent_coverage",
            threshold_value="1",
        ),
        "judge_provenance",
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(
            judge_calibration_id=CALIBRATION,
            judge_route_version_id=JUDGE_ROUTE,
            judge_prompt_version_id=JUDGE_PROMPT,
            judge_rubric_artifact_id=ARTIFACT_REPORT,
            judge_resolved_model_id=JUDGE_MODEL,
            judge_grader_version="grader.model_judge.v1",
        ),
        "judge_provenance",
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(
            grader_code="grader.json_schema.v1",
            metric_code="schema_valid_rate",
            threshold_value="0.9",
        ),
        "threshold differs from the canonical suite",
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(passed="false"),
        "passed flag disagrees with exact threshold",
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(grader_code="grader.rogue.v1"),
        "cannot emit metric",
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(case_key_sql="'forged-case-key'"),
        "provenance disagrees with run/case",
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(
            grader_code="grader.json_schema.v1",
            metric_code="schema_valid_rate",
            threshold_value="1",
            proportion_numerator_sql="NULL",
            proportion_denominator_sql="NULL",
        ),
        "requires valid numerator/denominator counts",
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(
            grader_code="grader.human_rubric.v1",
            metric_code="axis_relevance",
            metric_value="1",
            threshold_value="1",
            proportion_numerator_sql="1",
            proportion_denominator_sql="1",
        ),
        "cannot contain proportion counts",
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(
            grader_code="grader.cost_latency.v1",
            metric_code="latency_p95_ms",
            metric_value="1",
            passed="true",
            threshold_operator=">=",
            threshold_value="0",
            proportion_numerator_sql="NULL",
            proportion_denominator_sql="NULL",
        ),
        "report-only cost/latency metric requires null threshold and passed state",
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(passed="NULL"),
        ("passed", "non-reporting", "required"),
    )

    model_judge_scope = {
        "grader_code": "grader.model_judge.v1",
        "metric_code": "intent_coverage",
        "threshold_value": "1",
        "judge_calibration_id": CALIBRATION,
        "judge_route_version_id": JUDGE_ROUTE,
        "judge_prompt_version_id": JUDGE_PROMPT,
        "judge_rubric_artifact_id": ARTIFACT_REPORT,
        "judge_resolved_model_id": JUDGE_MODEL,
        "judge_grader_version": "grader.model_judge.v1",
    }
    cross_dataset_calibration = "00000000-0000-7000-8000-0000000000c5"
    create_locked_dataset(
        cluster,
        database,
        dataset_id=DATASET_2,
        case_id=CASE_2,
        display_suffix="cross-dataset",
        canonical_release_dataset=True,
    )
    create_passed_calibration(
        cluster,
        database,
        calibration_id=cross_dataset_calibration,
        dataset_id=DATASET_2,
        display_suffix="cross-dataset",
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(
            **(
                model_judge_scope
                | {"judge_calibration_id": cross_dataset_calibration}
            )
        ),
        ("current exact-scope calibration", "dataset"),
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(
            **(model_judge_scope | {"judge_prompt_version_id": PROMPT})
        ),
        "current exact-scope calibration",
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(
            **(model_judge_scope | {"judge_resolved_model_id": MODEL})
        ),
        "current exact-scope calibration",
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(
            **(
                model_judge_scope
                | {"judge_rubric_artifact_id": ARTIFACT_GOLD}
            )
        ),
        "current exact-scope calibration",
    )

    create_passed_calibration(
        cluster,
        database,
        calibration_id=CALIBRATION_4,
        display_suffix="same-route",
        judge_route_version_id=ROUTE,
        resolved_judge_model_id=MODEL,
    )
    assert_sql_fails(
        cluster,
        database,
        canonical_metric_insert_sql(
            **(
                model_judge_scope
                | {
                    "judge_calibration_id": CALIBRATION_4,
                    "judge_route_version_id": ROUTE,
                    "judge_resolved_model_id": MODEL,
                }
            )
        ),
        "current exact-scope calibration",
    )

    create_passed_calibration(
        cluster,
        database,
        calibration_id=CALIBRATION_2,
        display_suffix="expired",
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.judge_calibration
           SET status = 'EXPIRED', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{CALIBRATION_2}';
        INSERT INTO ai.judge_calibration (
            id, display_id, judge_route_version_id, judge_prompt_version_id,
            dataset_version_id, case_count, status,
            evaluated_task_definition_id, resolved_judge_model_id,
            rubric_artifact_id, rubric_sha256, grader_version
        ) VALUES (
            '{CALIBRATION_3}', 'AIC-ST0003-failed', '{JUDGE_ROUTE}',
            '{JUDGE_PROMPT}', '{DATASET}', 200, 'DRAFT', '{TASK}',
            '{JUDGE_MODEL}', '{ARTIFACT_REPORT}', repeat('4', 64),
            'grader.model_judge.v1'
        );
        UPDATE ai.judge_calibration
           SET status = 'FAILED', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{CALIBRATION_3}';
        """,
    )
    for calibration_id in (CALIBRATION_2, CALIBRATION_3):
        assert_sql_fails(
            cluster,
            database,
            canonical_metric_insert_sql(
                **(
                    model_judge_scope
                    | {"judge_calibration_id": calibration_id}
                )
            ),
            "current exact-scope calibration",
        )

    cluster.psql(
        database,
        canonical_metric_insert_sql(**model_judge_scope),
    )
    assert cluster.query(
        database,
        f"""
        SELECT grader_code, judge_grader_version
          FROM ai.evaluation_result
         WHERE evaluation_run_id = '{RUN}'
           AND grader_code = 'grader.model_judge.v1';
        """,
    ) == "grader.model_judge.v1\tgrader.model_judge.v1"


def test_completion_requires_exact_human_review_and_adjudication_cardinality(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "human_adjudication")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    create_evaluation_run(cluster, database, complete=False)

    completion_sql = f"""
        UPDATE ai.evaluation_run
           SET status = 'GRADING', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RUN}';
        UPDATE ai.evaluation_run
           SET status = 'COMPLETED',
               run_manifest_artifact_id = '{ARTIFACT_REPORT}',
               completed_at = clock_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RUN}';
    """
    evidence_deletions = (
        f"""
            DELETE FROM ai.evaluation_result
             WHERE evaluation_run_id = '{RUN}'
               AND metric_code = 'schema_valid_rate'
               AND evaluation_case_id = '{CASE}';
        """,
        f"""
        DELETE FROM ai.evaluation_result
         WHERE evaluation_run_id = '{RUN}'
           AND grader_code = 'grader.cost_latency.v1'
           AND slice_key = 'DEV';
        """,
    )
    for evidence_deletion in evidence_deletions:
        assert_sql_fails(
            cluster,
            database,
            f"""
            BEGIN;
            SET LOCAL session_replication_role = replica;
            {evidence_deletion}
            SET LOCAL session_replication_role = origin;
            {completion_sql}
            COMMIT;
            """,
            "evidence is incomplete",
        )

    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        DELETE FROM ai.human_evaluation
         WHERE evaluation_case_result_id = '{RESULT}'
           AND reviewer_principal_id = '{P2}'
           AND NOT is_adjudication;
        SET LOCAL session_replication_role = origin;
        {completion_sql}
        COMMIT;
        """,
        "evidence is incomplete",
    )

    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.human_evaluation
           SET decision = 'FAIL'
         WHERE evaluation_case_result_id = '{RESULT}'
           AND reviewer_principal_id = '{P2}'
           AND NOT is_adjudication;
        SET LOCAL session_replication_role = origin;
        {completion_sql}
        COMMIT;
        """,
        "evidence is incomplete",
    )

    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        INSERT INTO ai.human_evaluation (
            evaluation_case_result_id, reviewer_principal_id,
            rubric_version, blind_assignment_key, scores, decision,
            is_adjudication
        ) VALUES (
            '{RESULT}', '{P3}', 'RAOS-05-HUMAN-v0.1',
            'blind-unnecessary-adjudicator', '{{"blocking": 1}}'::jsonb,
            'PASS', true
        );
        {completion_sql}
        COMMIT;
        """,
        "evidence is incomplete",
    )

    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        INSERT INTO ai.human_evaluation (
            evaluation_case_result_id, reviewer_principal_id,
            rubric_version, blind_assignment_key, scores, decision,
            is_adjudication
        ) VALUES (
            '{RESULT}', '{P1}', 'RAOS-05-HUMAN-v0.1',
            'blind-author-adjudicator-bypass', '{{"blocking": 1}}'::jsonb,
            'PASS', true
        );
        SET LOCAL session_replication_role = origin;
        {completion_sql}
        COMMIT;
        """,
        "evidence is incomplete",
    )

    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.human_evaluation
           SET decision = 'FAIL'
         WHERE evaluation_case_result_id = '{RESULT}'
           AND reviewer_principal_id = '{P2}'
           AND NOT is_adjudication;
        SET LOCAL session_replication_role = origin;
        INSERT INTO ai.human_evaluation (
            evaluation_case_result_id, reviewer_principal_id,
            rubric_version, blind_assignment_key, scores, decision,
            is_adjudication
        ) VALUES
        (
            '{RESULT}', '{P3}', 'RAOS-05-HUMAN-v0.1',
            'blind-adjudicator-1', '{{"blocking": 1}}'::jsonb, 'PASS', true
        ),
        (
            '{RESULT}', '{P4}', 'RAOS-05-HUMAN-v0.1',
            'blind-adjudicator-2', '{{"blocking": 1}}'::jsonb, 'PASS', true
        );
        {completion_sql}
        COMMIT;
        """,
        "evidence is incomplete",
    )

    cluster.psql(
        database,
        f"""
        SET session_replication_role = replica;
        UPDATE ai.human_evaluation
           SET decision = 'FAIL'
         WHERE evaluation_case_result_id = '{RESULT}'
           AND reviewer_principal_id = '{P2}'
           AND NOT is_adjudication;
        SET session_replication_role = origin;
        INSERT INTO ai.human_evaluation (
            evaluation_case_result_id, reviewer_principal_id,
            rubric_version, blind_assignment_key, scores, decision,
            is_adjudication
        ) VALUES (
            '{RESULT}', '{P3}', 'RAOS-05-HUMAN-v0.1',
            'blind-adjudicator-exact', '{{"blocking": 1}}'::jsonb,
            'PASS', true
        );
        {completion_sql}
        """,
    )
    assert cluster.query(
        database,
        f"SELECT status FROM ai.evaluation_run WHERE id = '{RUN}';",
    ) == "COMPLETED"


def test_regression_baseline_uses_exact_pairs_count_weighted_categories_and_margin(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "regression_baseline")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    create_passed_calibration(cluster, database)
    create_evaluation_run(cluster, database)
    create_evaluation_run(
        cluster,
        database,
        run_id=RUN_2,
        result_id=RESULT_2,
        display_suffix="regression-candidate",
        baseline_run_id=RUN,
    )

    cluster.psql(
        database,
        f"SELECT ai.assert_regression_against_baseline('{RUN_2}', '{RUN}');",
    )
    assert_sql_fails(
        cluster,
        database,
        f"UPDATE ai.evaluation_run SET baseline_evaluation_run_id = NULL "
        f"WHERE id = '{RUN_2}';",
        (
            "resolved-model/baseline bindings are immutable",
            "evaluation run version bindings are immutable",
        ),
    )

    # A one-half-percent regression remains within the canonical one-percent
    # ratio margin. The stored point estimate is still count-derived.
    cluster.psql(
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.evaluation_result AS result
           SET metric_value = 0.995,
               proportion_numerator_count = 995,
               proportion_denominator_count = 1000,
               passed = false
          FROM ai.evaluation_case AS candidate
         WHERE result.evaluation_run_id = '{RUN_2}'
           AND result.evaluation_case_id = candidate.id
           AND candidate.split = 'REGRESSION'
           AND result.metric_code = 'schema_valid_rate';
        SET LOCAL session_replication_role = origin;
        SELECT ai.assert_regression_against_baseline('{RUN_2}', '{RUN}');
        ROLLBACK;
        """,
    )

    # Exact case/metric pairing is mandatory; a globally complete-looking set
    # cannot substitute another case's result.
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        DELETE FROM ai.evaluation_result
         WHERE id = (
             SELECT result.id
               FROM ai.evaluation_result AS result
               JOIN ai.evaluation_case AS candidate
                 ON candidate.id = result.evaluation_case_id
              WHERE result.evaluation_run_id = '{RUN_2}'
                AND candidate.split = 'REGRESSION'
                AND result.metric_code = 'schema_valid_rate'
              ORDER BY candidate.case_key
              LIMIT 1
         );
        SET LOCAL session_replication_role = origin;
        SELECT ai.assert_regression_against_baseline('{RUN_2}', '{RUN}');
        COMMIT;
        """,
        "candidate regression evidence is missing, incomparable, or beyond margin",
    )

    # With no active Champion, a release is a bootstrap and therefore cannot
    # smuggle in an arbitrary baseline even when the paired run itself is valid.
    insert_release(
        cluster,
        database,
        release_id=RELEASE_2,
        run_id=RUN_2,
        display_suffix="regression-candidate",
        ready_for_review=False,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.release_decision
           SET status = 'READY_FOR_REVIEW',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE_2}';
        """,
        "bootstrap release cannot bind a baseline when no champion exists",
    )

    # Category A regresses by two percent while the count-weighted ALL scope
    # stays above the one-percent margin because category B carries much larger
    # denominators. A global-only comparison would incorrectly accept it.
    cluster.psql(
        database,
        f"""
        SET session_replication_role = replica;
        UPDATE ai.evaluation_result AS result
           SET metric_value = 0.98,
               proportion_numerator_count = 98,
               proportion_denominator_count = 100,
               passed = false
          FROM ai.evaluation_case AS candidate
         WHERE result.evaluation_run_id = '{RUN_2}'
           AND result.evaluation_case_id = candidate.id
           AND candidate.split = 'REGRESSION'
           AND candidate.category = 'ST0003-A'
           AND result.metric_code = 'schema_valid_rate';
        SET session_replication_role = origin;
        """,
    )
    assert cluster.query(
        database,
        f"""
        WITH scoped AS (
            SELECT candidate.category,
                   sum(result.proportion_numerator_count)::numeric
                   / sum(result.proportion_denominator_count)::numeric AS value
              FROM ai.evaluation_result AS result
              JOIN ai.evaluation_case AS candidate
                ON candidate.id = result.evaluation_case_id
             WHERE result.evaluation_run_id = '{RUN_2}'
               AND candidate.split = 'REGRESSION'
               AND result.metric_code = 'schema_valid_rate'
             GROUP BY candidate.category
        ), overall AS (
            SELECT sum(result.proportion_numerator_count)::numeric
                   / sum(result.proportion_denominator_count)::numeric AS value
              FROM ai.evaluation_result AS result
              JOIN ai.evaluation_case AS candidate
                ON candidate.id = result.evaluation_case_id
             WHERE result.evaluation_run_id = '{RUN_2}'
               AND candidate.split = 'REGRESSION'
               AND result.metric_code = 'schema_valid_rate'
        )
        SELECT overall.value >= 0.99,
               (SELECT value = 0.98 FROM scoped
                 WHERE category = 'ST0003-A')
          FROM overall;
        """,
    ) == "t\tt"
    assert_sql_fails(
        cluster,
        database,
        f"SELECT ai.assert_regression_against_baseline('{RUN_2}', '{RUN}');",
        "candidate regression evidence is missing, incomparable, or beyond margin",
    )


def test_release_gate_requires_clean_complete_bound_run_two_approvers_and_canary(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "release_gate")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    create_passed_calibration(cluster, database)
    create_evaluation_run(cluster, database)
    insert_release(cluster, database)
    insert_release(
        cluster,
        database,
        release_id=RELEASE_2,
        run_id=RUN,
        dataset_id=DATASET,
        display_suffix="2",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.release_decision
           SET status = 'APPROVED_ACTIVE', release_scope = 'ACTIVE',
               maximum_canary_percent = 0,
               approved_by_principal_id = '{P1}',
               second_approver_principal_id = '{P2}',
               approved_at = clock_timestamp()
         WHERE id = '{RELEASE_2}';
        """,
        ("lifecycle", "active approval lacks", "route is not eligible"),
    )

    insert_release_approval_kwargs = {
        "approval_id": CANARY_APPROVAL,
        "display_suffix": "canary-1",
        "phase": "CANARY",
        "manifest_sha256": MANIFEST_SHA,
        "artifact_id": ARTIFACT_CANARY_APPROVAL,
        "artifact_sha_digit": "7",
    }
    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO ai.release_approval (
            id, display_id, release_decision_id, phase,
            decision_manifest_sha256, primary_approver_principal_id,
            primary_approver_role, second_approver_principal_id,
            second_approver_role, approval_artifact_id, approval_sha256,
            signed_at
        ) VALUES (
            '{CANARY_APPROVAL}', 'RAP-ST0003-author', '{RELEASE}', 'CANARY',
            '{MANIFEST_SHA}', '{P1}', 'APPROVER', '{P3}', 'OWNER',
            '{ARTIFACT_CANARY_APPROVAL}', repeat('7', 64),
            statement_timestamp()
        );
        """,
        "authority/evidence is invalid",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO ai.release_approval (
            id, display_id, release_decision_id, phase,
            decision_manifest_sha256, primary_approver_principal_id,
            primary_approver_role, second_approver_principal_id,
            second_approver_role, approval_artifact_id, approval_sha256,
            signed_at
        ) VALUES (
            '{CANARY_APPROVAL}', 'RAP-ST0003-unsafe', '{RELEASE}', 'CANARY',
            '{MANIFEST_SHA}', '{P2}', 'APPROVER', '{P3}', 'OWNER',
            '{ARTIFACT_UNSAFE}', repeat('f', 64),
            statement_timestamp()
        );
        """,
        "authority/evidence is invalid",
    )
    for signed_at_sql in (
        "(SELECT completed_at - interval '1 second' FROM ai.evaluation_run "
        f"WHERE id = '{RUN}')",
        "statement_timestamp() + interval '1 minute'",
    ):
        statement = f"""
        INSERT INTO ai.release_approval (
            id, display_id, release_decision_id, phase,
            decision_manifest_sha256, primary_approver_principal_id,
            primary_approver_role, second_approver_principal_id,
            second_approver_role, approval_artifact_id, approval_sha256,
            signed_at
        ) VALUES (
            '{CANARY_APPROVAL}', 'RAP-ST0003-time', '{RELEASE}', 'CANARY',
            '{MANIFEST_SHA}', '{P2}', 'APPROVER', '{P3}', 'OWNER',
            '{ARTIFACT_CANARY_APPROVAL}', repeat('7', 64), {signed_at_sql}
        );
        """
        assert_sql_fails(
            cluster,
            database,
            statement,
            ("authority/evidence is invalid", "ck_ai_release_approval_time"),
        )

    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.release_decision
           SET status = 'APPROVED_CANARY',
               approved_by_principal_id = '{P1}',
               approved_at = clock_timestamp(),
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        """,
        ("two", "canary approval bundle"),
    )
    insert_release_approval(cluster, database, **insert_release_approval_kwargs)
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.release_decision
           SET canary_approval_id = '{CANARY_APPROVAL}',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        """,
        ("phase state", "ck_ai_release_phase_state"),
    )
    assert_sql_fails(
        cluster,
        database,
        f"UPDATE ai.release_approval SET signed_at = clock_timestamp() WHERE id = '{CANARY_APPROVAL}';",
        "append-only",
    )
    assert_sql_fails(
        cluster,
        database,
        f"DELETE FROM ai.release_approval WHERE id = '{CANARY_APPROVAL}';",
        "append-only",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.release_decision
           SET status = 'APPROVED_CANARY',
               maximum_canary_percent = 2,
               approved_by_principal_id = '{P2}',
               second_approver_principal_id = '{P3}',
               approved_at = (
                   SELECT signed_at FROM ai.release_approval
                    WHERE id = '{CANARY_APPROVAL}'
               ),
               canary_approval_id = '{CANARY_APPROVAL}',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        """,
        "bundle/cap/monitoring is invalid",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.model_route_version
           SET route_config = jsonb_set(
                route_config, '{{canary_max_percent}}', '0'::jsonb
           )
         WHERE id = '{ROUTE}';
        SET LOCAL session_replication_role = origin;
        UPDATE ai.release_decision
           SET status = 'APPROVED_CANARY',
               maximum_canary_percent = 1,
               approved_by_principal_id = '{P2}',
               second_approver_principal_id = '{P3}',
               approved_at = (
                   SELECT signed_at FROM ai.release_approval
                    WHERE id = '{CANARY_APPROVAL}'
               ),
               canary_approval_id = '{CANARY_APPROVAL}',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        COMMIT;
        """,
        "canary approval bundle/cap/monitoring is invalid",
    )

    current_state_mutations = (
        f"UPDATE ai.evaluation_suite SET status = 'RETIRED' WHERE id = '{SUITE}';",
        f"UPDATE ai.task_definition SET status = 'PAUSED' WHERE id = '{TASK}';",
        f"UPDATE ai.prompt_version SET status = 'SUSPENDED' WHERE id = '{PROMPT}';",
        f"UPDATE ai.model_route_version SET status = 'PAUSED' WHERE id = '{ROUTE}';",
        f"UPDATE ai.output_schema_version SET status = 'RETIRED' WHERE id = '{OUTPUT_SCHEMA}';",
        f"UPDATE policy.policy_bundle SET status = 'RETIRED' WHERE id = '{POLICY}';",
        f"UPDATE ai.model_definition SET status = 'BLOCKED' WHERE id = '{MODEL}';",
        f"UPDATE ai.evaluation_dataset_version SET status = 'COMPROMISED', compromised_at = clock_timestamp() WHERE id = '{DATASET}';",
    )
    for mutation in current_state_mutations:
        assert_sql_fails(
            cluster,
            database,
            f"""
            BEGIN;
            {mutation}
            UPDATE ai.release_decision
               SET status = 'APPROVED_CANARY',
                   approved_by_principal_id = '{P2}',
                   second_approver_principal_id = '{P3}',
                   approved_at = (
                       SELECT signed_at FROM ai.release_approval
                        WHERE id = '{CANARY_APPROVAL}'
                   ),
                   canary_approval_id = '{CANARY_APPROVAL}',
                   lock_version = lock_version + 1,
                   updated_at = clock_timestamp()
             WHERE id = '{RELEASE}';
            COMMIT;
            """,
            (
                "does not match a complete eligible run",
                "route is not eligible",
            ),
        )
    cluster.psql(
        database,
        f"""
        UPDATE ai.release_decision
           SET status = 'APPROVED_CANARY',
               approved_by_principal_id = '{P2}',
               second_approver_principal_id = '{P3}',
               approved_at = (
                   SELECT signed_at FROM ai.release_approval
                    WHERE id = '{CANARY_APPROVAL}'
               ),
               canary_approval_id = '{CANARY_APPROVAL}',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        """,
    )
    assert cluster.query(
        database,
        f"""
        SELECT canary_evidence_artifact_id IS NULL
          FROM ai.release_decision
         WHERE id = '{RELEASE}';
        """,
    ) == "t"
    for checkpoint_mutation in (
        "canary_started_at = canary_started_at - interval '1 second'",
        "canary_started_txid = canary_started_txid + 1",
    ):
        assert_sql_fails(
            cluster,
            database,
            f"""
            UPDATE ai.release_decision
               SET {checkpoint_mutation},
                   lock_version = lock_version + 1,
                   updated_at = clock_timestamp()
             WHERE id = '{RELEASE}'
               AND status = 'APPROVED_CANARY';
            """,
            "canary start time/transaction is immutable",
        )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.release_decision
           SET active_approval_id = '{CANARY_APPROVAL}',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        """,
        ("phase state", "ck_ai_release_phase_state"),
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.model_route_version
           SET status = 'CANARY', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{ROUTE}';
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        UPDATE ai.release_decision
           SET canary_evidence_artifact_id = '{ARTIFACT_CANARY}',
               canary_evidence_sha256 = repeat('6', 64),
               canary_completed_at = statement_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        INSERT INTO ai.release_approval (
            id, display_id, release_decision_id, phase,
            decision_manifest_sha256, primary_approver_principal_id,
            primary_approver_role, second_approver_principal_id,
            second_approver_role, approval_artifact_id, approval_sha256,
            signed_at
        ) VALUES (
            '{ACTIVE_APPROVAL}', 'RAP-ST0003-same-tx', '{RELEASE}', 'ACTIVE',
            repeat('c', 64), '{P2}', 'APPROVER', '{P3}', 'OWNER',
            '{ARTIFACT_ACTIVE_APPROVAL}', repeat('8', 64),
            statement_timestamp()
        );
        UPDATE ai.release_decision
           SET status = 'APPROVED_ACTIVE', release_scope = 'ACTIVE',
               maximum_canary_percent = 0,
               decision_manifest_sha256 = repeat('c', 64),
               active_approval_id = '{ACTIVE_APPROVAL}',
               approved_by_principal_id = '{P2}',
               second_approver_principal_id = '{P3}',
               approved_at = statement_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        COMMIT;
        """,
        ("prior canary evidence", "new transaction"),
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.release_decision
           SET canary_evidence_artifact_id = '{ARTIFACT_CANARY}',
               canary_evidence_sha256 = repeat('6', 64),
               canary_completed_at = statement_timestamp(),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        INSERT INTO ai.release_approval (
            id, display_id, release_decision_id, phase,
            decision_manifest_sha256, primary_approver_principal_id,
            primary_approver_role, second_approver_principal_id,
            second_approver_role, approval_artifact_id, approval_sha256,
            signed_at
        ) VALUES (
            '{ACTIVE_APPROVAL}', 'RAP-ST0003-reused', '{RELEASE}', 'ACTIVE',
            repeat('c', 64), '{P2}', 'APPROVER', '{P3}', 'OWNER',
            '{ARTIFACT_CANARY_APPROVAL}', repeat('7', 64),
            statement_timestamp()
        );
        """,
        ("new signature", "prior canary evidence"),
    )
    insert_release_approval(
        cluster,
        database,
        approval_id=ACTIVE_APPROVAL,
        display_suffix="active-1",
        phase="ACTIVE",
        manifest_sha256="c" * 64,
        artifact_id=ARTIFACT_ACTIVE_APPROVAL,
        artifact_sha_digit="8",
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.release_decision
           SET status = 'APPROVED_ACTIVE',
               release_scope = 'ACTIVE',
               maximum_canary_percent = 0,
               decision_manifest_sha256 = repeat('c', 64),
               active_approval_id = '{ACTIVE_APPROVAL}',
               approved_by_principal_id = '{P2}',
               second_approver_principal_id = '{P3}',
               approved_at = (
                   SELECT signed_at FROM ai.release_approval
                    WHERE id = '{ACTIVE_APPROVAL}'
               ),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        """,
    )
    assert (
        cluster.query(
            database,
            f"SELECT status, release_scope FROM ai.release_decision WHERE id = '{RELEASE}';",
        )
        == "APPROVED_ACTIVE\tACTIVE"
    )
    assert_sql_fails(
        cluster,
        database,
        f"UPDATE ai.release_decision SET code_git_sha = repeat('f', 40) WHERE id = '{RELEASE}';",
        "bindings",
    )
    cluster.psql(
        database,
        f"""
        UPDATE ai.model_route_version
           SET status = 'ACTIVE', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{ROUTE}';
        """,
    )

    # An active release can become a PREVIOUS_RELEASE rollback target only
    # after every component needed to execute it is itself ACTIVE.
    cluster.psql(
        database,
        f"""
        UPDATE ai.prompt_version
           SET status = 'ACTIVE', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{PROMPT}';
        UPDATE ai.model_definition SET status = 'ACTIVE' WHERE id = '{MODEL}';
        INSERT INTO ai.model_route_version (
            id, route_code, version_no, task_definition_id, primary_model_id,
            route_config, per_job_budget_jpy, status,
            approved_by_principal_id, lock_version, updated_at
        ) VALUES (
            '{ROUTE_2}', 'route.st0003.v2', 2, '{TASK}', '{MODEL}',
            '{{"canary_max_percent": 10}}'::jsonb, 100, 'DRAFT',
            NULL, 0, clock_timestamp()
        );
        UPDATE ai.model_route_version
           SET status = 'EVALUATING', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{ROUTE_2}';
        UPDATE ai.model_route_version
           SET status = 'CERTIFIED', approved_by_principal_id = '{P2}',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{ROUTE_2}';
        """,
    )
    create_evaluation_run(
        cluster,
        database,
        run_id=RUN_2,
        result_id=RESULT_2,
        display_suffix="rollback-successor",
        model_route_version_id=ROUTE_2,
        baseline_run_id=RUN,
    )
    insert_release(
        cluster,
        database,
        release_id=RELEASE_3,
        run_id=RUN_2,
        display_suffix="rollback-successor",
        ready_for_review=False,
        model_route_version_id=ROUTE_2,
    )

    # A degraded historical Champion still defines the mandatory comparison
    # baseline. Removing its component from executable state must not make the
    # next decision look like a first-release bootstrap with a NULL baseline.
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.evaluation_run
           SET baseline_evaluation_run_id = NULL
         WHERE id = '{RUN_2}';
        UPDATE ai.model_route_version
           SET status = 'ROLLED_BACK'
         WHERE id = '{ROUTE}';
        SET LOCAL session_replication_role = origin;
        UPDATE ai.release_decision
           SET status = 'READY_FOR_REVIEW',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE_3}';
        COMMIT;
        """,
        (
            "current champion",
            "same-suite/dataset rerun of the current champion",
        ),
    )

    unsafe_target_scenarios = (
        ("", RELEASE_2),
        (
            f"UPDATE ai.release_decision SET task_definition_id = uuidv7() "
            f"WHERE id = '{RELEASE}';",
            RELEASE,
        ),
        (
            f"UPDATE ai.model_route_version SET status = 'ROLLED_BACK' "
            f"WHERE id = '{ROUTE}';",
            RELEASE,
        ),
    )
    for target_corruption, rollback_target in unsafe_target_scenarios:
        assert_sql_fails(
            cluster,
            database,
            f"""
            BEGIN;
            SET LOCAL session_replication_role = replica;
            {target_corruption}
            SET LOCAL session_replication_role = origin;
            UPDATE ai.release_decision
               SET rollback_strategy = 'PREVIOUS_RELEASE',
                   rollback_release_decision_id = '{rollback_target}',
                   rollback_runbook_artifact_id = NULL,
                   rollback_runbook_sha256 = NULL,
                   lock_version = lock_version + 1,
                   updated_at = clock_timestamp()
             WHERE id = '{RELEASE_3}';
            UPDATE ai.release_decision
               SET status = 'READY_FOR_REVIEW',
                   lock_version = lock_version + 1,
                   updated_at = clock_timestamp()
             WHERE id = '{RELEASE_3}';
            COMMIT;
            """,
                (
                    "rollback target is not a prior safe same-task active release",
                    "bootstrap release cannot bind a baseline when no champion exists",
                ),
        )

    cluster.psql(
        database,
        f"""
        UPDATE ai.release_decision
           SET rollback_strategy = 'PREVIOUS_RELEASE',
               rollback_release_decision_id = '{RELEASE}',
               rollback_runbook_artifact_id = NULL,
               rollback_runbook_sha256 = NULL,
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE_3}';
        UPDATE ai.release_decision
           SET status = 'READY_FOR_REVIEW',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE_3}';
        """,
    )
    assert (
        cluster.query(
            database,
            f"SELECT ai.has_live_rollback_dependents('ROUTE', '{ROUTE}');",
        )
        == "t"
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.model_route_version
           SET status = 'RETIRED', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{ROUTE}';
        """,
        "live rollback component",
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.release_decision
           SET status = 'REVOKED', revoked_by_principal_id = '{P3}',
               revoked_at = clock_timestamp(),
               revocation_reason = 'rollback target test',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        """,
        "frozen rollback target of a live decision",
    )

    rollback_canary_approval = "00000000-0000-7000-8000-0000000000e1"
    assert_sql_fails(
        cluster,
        database,
        f"""
        BEGIN;
        SET LOCAL session_replication_role = replica;
        UPDATE ai.release_approval
           SET signed_at = statement_timestamp() + interval '1 minute'
         WHERE id = '{ACTIVE_APPROVAL}';
        SET LOCAL session_replication_role = origin;
        INSERT INTO ai.release_approval (
            id, display_id, release_decision_id, phase,
            decision_manifest_sha256, primary_approver_principal_id,
            primary_approver_role, second_approver_principal_id,
            second_approver_role, approval_artifact_id, approval_sha256,
            signed_at
        ) VALUES (
            '{rollback_canary_approval}', 'RAP-ST0003-rollback-future',
            '{RELEASE_3}', 'CANARY', '{MANIFEST_SHA}', '{P2}', 'APPROVER',
            '{P3}', 'OWNER', '{ARTIFACT_APPROVAL_3}', repeat('d', 64),
            statement_timestamp()
        );
        UPDATE ai.release_decision
           SET status = 'APPROVED_CANARY',
               canary_approval_id = '{rollback_canary_approval}',
               approved_by_principal_id = '{P2}',
               second_approver_principal_id = '{P3}',
               approved_at = (
                   SELECT signed_at FROM ai.release_approval
                    WHERE id = '{rollback_canary_approval}'
               ),
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE_3}';
        COMMIT;
        """,
        "canary approval bundle/cap/monitoring is invalid",
    )


def test_current_champion_accepts_only_same_dataset_rerun_baseline_bindings(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "champion_dataset_rerun")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    create_passed_calibration(cluster, database)
    create_evaluation_run(cluster, database)
    insert_release(cluster, database)
    promote_release_to_active_champion(cluster, database)

    create_locked_dataset(
        cluster,
        database,
        dataset_id=DATASET_2,
        case_id=CASE_2,
        display_suffix="champion-v2",
        canonical_release_dataset=True,
    )
    create_evaluation_run(
        cluster,
        database,
        run_id=RUN_2,
        result_id=RESULT_2,
        dataset_id=DATASET_2,
        case_id=CASE_2,
        display_suffix="champion-rerun-v2",
    )
    cluster.psql(
        database,
        f"""
        INSERT INTO ai.model_route_version (
            id, route_code, version_no, task_definition_id, primary_model_id,
            route_config, per_job_budget_jpy, status,
            approved_by_principal_id, lock_version, updated_at
        ) VALUES (
            '{ROUTE_2}', 'route.st0003.challenger.v2', 2, '{TASK}', '{MODEL}',
            '{{"canary_max_percent": 10}}'::jsonb, 100, 'DRAFT',
            NULL, 0, clock_timestamp()
        );
        UPDATE ai.model_route_version
           SET status = 'EVALUATING', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{ROUTE_2}';
        UPDATE ai.model_route_version
           SET status = 'CERTIFIED', approved_by_principal_id = '{P2}',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{ROUTE_2}';
        """,
    )
    create_evaluation_run(
        cluster,
        database,
        run_id=RUN_3,
        result_id=RESULT_3,
        dataset_id=DATASET_2,
        case_id=CASE_2,
        display_suffix="challenger-v2",
        model_route_version_id=ROUTE_2,
        baseline_run_id=RUN_2,
    )
    insert_release(
        cluster,
        database,
        release_id=RELEASE_3,
        run_id=RUN_3,
        dataset_id=DATASET_2,
        display_suffix="challenger-v2",
        ready_for_review=False,
        model_route_version_id=ROUTE_2,
    )
    release_ready_sql = f"""
        UPDATE ai.release_decision
           SET status = 'READY_FOR_REVIEW',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE_3}';
    """
    for invalid_baseline_mutation in (
        f"""
        UPDATE ai.evaluation_run
           SET baseline_evaluation_run_id = '{RUN}'
         WHERE id = '{RUN_3}';
        """,
        f"""
        UPDATE ai.evaluation_run
           SET model_route_version_id = '{ROUTE_2}'
         WHERE id = '{RUN_2}';
        """,
    ):
        assert_sql_fails(
            cluster,
            database,
            f"""
            BEGIN;
            SET LOCAL session_replication_role = replica;
            {invalid_baseline_mutation}
            SET LOCAL session_replication_role = origin;
            {release_ready_sql}
            COMMIT;
            """,
            (
                "current champion",
                "same-suite/dataset rerun of the current champion",
            ),
        )

    cluster.psql(database, release_ready_sql)
    assert cluster.query(
        database,
        f"SELECT status FROM ai.release_decision WHERE id = '{RELEASE_3}';",
    ) == "READY_FOR_REVIEW"


def test_only_one_same_task_canary_can_win_and_serializable_retry_is_rejected(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "single_task_canary_race")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    create_passed_calibration(cluster, database)
    create_evaluation_run(cluster, database)
    insert_release(cluster, database)
    insert_release(
        cluster,
        database,
        release_id=RELEASE_2,
        run_id=RUN,
        display_suffix="canary-race-2",
    )
    insert_release_approval(
        cluster,
        database,
        approval_id=CANARY_APPROVAL,
        display_suffix="canary-race-1",
        phase="CANARY",
        manifest_sha256=MANIFEST_SHA,
        artifact_id=ARTIFACT_CANARY_APPROVAL,
        artifact_sha_digit="7",
    )
    insert_release_approval(
        cluster,
        database,
        approval_id=APPROVAL_3,
        display_suffix="canary-race-2",
        release_id=RELEASE_2,
        phase="CANARY",
        manifest_sha256=MANIFEST_SHA,
        artifact_id=ARTIFACT_APPROVAL_3,
        artifact_sha_digit="d",
    )

    def canary_update(release_id: str, approval_id: str) -> str:
        return f"""
            UPDATE ai.release_decision
               SET status = 'APPROVED_CANARY',
                   approved_by_principal_id = '{P2}',
                   second_approver_principal_id = '{P3}',
                   approved_at = (
                       SELECT signed_at FROM ai.release_approval
                        WHERE id = '{approval_id}'
                   ),
                   canary_approval_id = '{approval_id}',
                   lock_version = lock_version + 1,
                   updated_at = clock_timestamp()
             WHERE id = '{release_id}';
        """

    winner_process: subprocess.Popen[str] | None = None
    try:
        winner_process = open_psql_process(cluster, database)
        assert winner_process.stdin is not None
        winner_process.stdin.write(
            f"""
            SET application_name = 'st0003_canary_race_winner';
            BEGIN;
            {canary_update(RELEASE, CANARY_APPROVAL)}
            """,
        )
        winner_process.stdin.flush()
        wait_for_database_condition(
            cluster,
            database,
            """
            SELECT EXISTS (
                SELECT 1
                  FROM pg_stat_activity AS activity
                  JOIN pg_locks AS lock ON lock.pid = activity.pid
                 WHERE activity.datname = current_database()
                   AND activity.application_name =
                       'st0003_canary_race_winner'
                   AND lock.locktype = 'advisory'
                   AND lock.granted
            );
            """,
        )
        loser_result = cluster.psql(
            database,
            canary_update(RELEASE_2, APPROVAL_3),
            check=False,
        )
        assert loser_result.returncode != 0
        assert "concurrent release transition" in loser_result.stderr
        winner_process.stdin.write("COMMIT;\n\\q\n")
        winner_process.stdin.close()
        winner_result = finish_psql_process(winner_process)
        winner_process = None
        assert winner_result[0] == 0, winner_result
        assert_sql_fails(
            cluster,
            database,
            canary_update(RELEASE_2, APPROVAL_3),
            "canary approval bundle/cap/monitoring is invalid",
        )
        assert cluster.query(
            database,
            f"""
            SELECT count(*)
              FROM ai.release_decision
             WHERE task_definition_id = '{TASK}'
               AND status = 'APPROVED_CANARY';
            """,
        ) == "1"
    finally:
        stop_psql_process(winner_process)


def test_release_gate_rejects_incomplete_and_zero_tolerance_failing_runs(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "release_negative")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    create_passed_calibration(cluster, database)
    create_evaluation_run(cluster, database, complete=False)
    insert_release(cluster, database, ready_for_review=False)

    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.release_decision
           SET status = 'READY_FOR_REVIEW',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        """,
        ("completed", "complete eligible run"),
    )

    cluster.psql(
        database,
        f"""
        UPDATE ai.evaluation_case_result
           SET zero_tolerance_failure_count = 1
         WHERE id = '{RESULT}';
        """,
        check=False,
    )
    # Append-only protection is intentional; use a second isolated run/result
    # inserted with a failing count instead of mutating release evidence.
    create_evaluation_run(
        cluster,
        database,
        run_id=RUN_2,
        result_id=RESULT_2,
        display_suffix="2",
        zero_tolerance_failures=1,
        complete=True,
    )
    insert_release(
        cluster,
        database,
        release_id=RELEASE_2,
        run_id=RUN_2,
        display_suffix="2",
        ready_for_review=False,
    )
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.release_decision
           SET status = 'READY_FOR_REVIEW',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE_2}';
        """,
        ("zero-tolerance", "blocking gate"),
    )

    create_evaluation_run(
        cluster,
        database,
        run_id=RUN_3,
        result_id=RESULT_3,
        display_suffix="3",
        complete=True,
    )
    insert_release(
        cluster,
        database,
        release_id=RELEASE_3,
        run_id=RUN_3,
        display_suffix="3",
        ready_for_review=False,
    )
    release_ready_sql = f"""
        UPDATE ai.release_decision
           SET status = 'READY_FOR_REVIEW', lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE_3}';
    """
    corruptions = (
        f"""
        UPDATE ai.evaluation_result
           SET metric_value = 0, proportion_numerator_count = 0,
               passed = true
         WHERE evaluation_run_id = '{RUN_3}'
           AND evaluation_case_id = '{CASE}'
           AND metric_code = 'schema_valid_rate';
        """,
        f"""
        UPDATE ai.evaluation_result
           SET metric_value = 0, proportion_numerator_count = 0,
               passed = false
         WHERE evaluation_run_id = '{RUN_3}'
           AND metric_code = 'schema_valid_rate'
           AND slice_key = 'HOLDOUT';
        """,
        f"""
        UPDATE ai.evaluation_case_result
           SET status = 'FAILED'
         WHERE id = '{RESULT_3}';
        """,
        f"""
        UPDATE ai.human_evaluation
           SET decision = 'FAIL'
         WHERE evaluation_case_result_id = '{RESULT_3}'
           AND reviewer_principal_id = '{P2}'
           AND NOT is_adjudication;
        """,
    )
    for corruption in corruptions:
        assert_sql_fails(
            cluster,
            database,
            f"""
            BEGIN;
            SET LOCAL session_replication_role = replica;
            {corruption}
            SET LOCAL session_replication_role = origin;
            {release_ready_sql}
            COMMIT;
            """,
            ("evidence is incomplete", "does not pass every blocking gate"),
        )


def test_release_gate_rejects_category_masking_even_when_every_overall_scope_passes(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "release_category_masking")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    create_passed_calibration(cluster, database)
    create_evaluation_run(cluster, database)
    insert_release(cluster, database, ready_for_review=False)

    cluster.psql(
        database,
        f"""
        SET session_replication_role = replica;
        WITH ranked AS (
            SELECT result.id,
                   row_number() OVER (
                       PARTITION BY candidate.split
                       ORDER BY candidate.case_key
                   ) AS ordinal
              FROM ai.evaluation_result AS result
              JOIN ai.evaluation_case AS candidate
                ON candidate.id = result.evaluation_case_id
             WHERE result.evaluation_run_id = '{RUN}'
               AND candidate.split IN (
                    'HOLDOUT', 'ADVERSARIAL', 'REGRESSION'
               )
               AND candidate.category = 'ST0003-A'
               AND result.metric_code = 'human_acceptance_rate'
        )
        UPDATE ai.evaluation_result AS result
           SET metric_value = CASE WHEN ranked.ordinal % 2 = 1 THEN 1 ELSE 0.8 END,
               proportion_numerator_count =
                   CASE WHEN ranked.ordinal % 2 = 1 THEN 1 ELSE 80 END,
               proportion_denominator_count =
                   CASE WHEN ranked.ordinal % 2 = 1 THEN 1 ELSE 100 END,
               passed = ranked.ordinal % 2 = 1
          FROM ranked
         WHERE result.id = ranked.id;
        UPDATE ai.evaluation_result AS result
           SET metric_value = 1,
               proportion_numerator_count = 1000000,
               proportion_denominator_count = 1000000,
               passed = true
          FROM ai.evaluation_case AS candidate
         WHERE result.evaluation_run_id = '{RUN}'
           AND result.evaluation_case_id = candidate.id
           AND candidate.split IN ('HOLDOUT', 'ADVERSARIAL', 'REGRESSION')
           AND candidate.category = 'ST0003-B'
           AND result.metric_code = 'human_acceptance_rate';
        SET session_replication_role = origin;
        """,
    )
    assert cluster.query(
        database,
        f"""
        WITH split_value AS (
            SELECT candidate.split,
                   sum(result.proportion_numerator_count)::numeric
                   / sum(result.proportion_denominator_count)::numeric AS value
              FROM ai.evaluation_result AS result
              JOIN ai.evaluation_case AS candidate
                ON candidate.id = result.evaluation_case_id
             WHERE result.evaluation_run_id = '{RUN}'
               AND candidate.split IN (
                    'HOLDOUT', 'ADVERSARIAL', 'REGRESSION'
               )
               AND result.metric_code = 'human_acceptance_rate'
             GROUP BY candidate.split
        ), category_value AS (
            SELECT candidate.split, candidate.category,
                   sum(result.proportion_numerator_count)::numeric
                   / sum(result.proportion_denominator_count)::numeric AS value,
                   avg(result.metric_value) AS simple_average
              FROM ai.evaluation_result AS result
              JOIN ai.evaluation_case AS candidate
                ON candidate.id = result.evaluation_case_id
             WHERE result.evaluation_run_id = '{RUN}'
               AND candidate.split IN (
                    'HOLDOUT', 'ADVERSARIAL', 'REGRESSION'
               )
               AND result.metric_code = 'human_acceptance_rate'
             GROUP BY candidate.split, candidate.category
        )
        SELECT bool_and(value >= 0.85),
               (SELECT bool_and(
                            simple_average = 0.9
                            AND value = 81::numeric / 101::numeric
                       )
                  FROM category_value
                 WHERE category = 'ST0003-A')
          FROM split_value;
        """,
    ) == "t\tt"
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.release_decision
           SET status = 'READY_FOR_REVIEW',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        """,
        ("evidence is incomplete", "does not pass every blocking gate"),
    )


def test_release_gate_recomputes_scope_local_p95_instead_of_averaging(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "release_scope_p95")
    upgrade_st0003(cluster, database)
    seed_governance_dependencies(cluster, database)
    create_locked_dataset(
        cluster,
        database,
        canonical_release_dataset=True,
    )
    create_passed_calibration(cluster, database)
    create_evaluation_run(cluster, database)
    insert_release(cluster, database, ready_for_review=False)

    cluster.psql(
        database,
        f"""
        SET session_replication_role = replica;
        UPDATE ai.evaluation_suite
           SET suite_config = jsonb_set(
                suite_config,
                '{{required_metrics,cost_jpy_p95}}',
                '{{"operator":"<=","value":100}}'::jsonb,
                true
           )
         WHERE id = '{SUITE}';
        UPDATE ai.evaluation_result
           SET threshold_operator = '<=', threshold_value = 100,
               metric_value = 0, passed = true
         WHERE evaluation_run_id = '{RUN}'
           AND metric_code = 'cost_jpy_p95';
        WITH outlier AS (
            SELECT result.id
              FROM ai.evaluation_result AS result
              JOIN ai.evaluation_case AS candidate
                ON candidate.id = result.evaluation_case_id
             WHERE result.evaluation_run_id = '{RUN}'
               AND result.metric_code = 'cost_jpy_p95'
               AND candidate.split = 'HOLDOUT'
               AND candidate.category = 'ST0003-A'
             ORDER BY candidate.case_key
             LIMIT 2
        )
        UPDATE ai.evaluation_result AS result
           SET metric_value = 1000, passed = false
          FROM outlier
         WHERE result.id = outlier.id;
        SET session_replication_role = origin;
        """,
    )
    assert cluster.query(
        database,
        f"""
        SELECT avg(result.metric_value) = 100,
               percentile_cont(0.95) WITHIN GROUP (
                   ORDER BY result.metric_value
               ) = 1000
          FROM ai.evaluation_result AS result
          JOIN ai.evaluation_case AS candidate
            ON candidate.id = result.evaluation_case_id
         WHERE result.evaluation_run_id = '{RUN}'
           AND result.metric_code = 'cost_jpy_p95'
           AND candidate.split = 'HOLDOUT'
           AND candidate.category = 'ST0003-A';
        """,
    ) == "t\tt"
    assert_sql_fails(
        cluster,
        database,
        f"""
        UPDATE ai.release_decision
           SET status = 'READY_FOR_REVIEW',
               lock_version = lock_version + 1,
               updated_at = clock_timestamp()
         WHERE id = '{RELEASE}';
        """,
        ("evidence is incomplete", "does not pass every blocking gate"),
    )


def test_downgrade_rejects_meaningful_values_in_existing_rows(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    database = baseline_to_st0002(cluster, "downgrade_meaningful_fields")
    seed_pending_ai_jobs(cluster, database, 1)
    upgrade_st0003(cluster, database)

    reversible_mutations = (
        (
            "UPDATE ai.ai_job SET request_config = '{\"store\": false}'::jsonb "
            "WHERE display_id = 'AIJ-ST0003-BATCH-00001';",
            "UPDATE ai.ai_job SET request_config = '{}'::jsonb "
            "WHERE display_id = 'AIJ-ST0003-BATCH-00001';",
        ),
        (
            "UPDATE ai.ai_job SET input_manifest_sha256 = repeat('a', 64) "
            "WHERE display_id = 'AIJ-ST0003-BATCH-00001';",
            "UPDATE ai.ai_job SET input_manifest_sha256 = NULL "
            "WHERE display_id = 'AIJ-ST0003-BATCH-00001';",
        ),
        (
            "UPDATE ai.ai_job SET budget_reserved_jpy = 1 "
            "WHERE display_id = 'AIJ-ST0003-BATCH-00001';",
            "UPDATE ai.ai_job SET budget_reserved_jpy = 0 "
            "WHERE display_id = 'AIJ-ST0003-BATCH-00001';",
        ),
        (
            "UPDATE ai.ai_job SET lock_version = 1 "
            "WHERE display_id = 'AIJ-ST0003-BATCH-00001';",
            "UPDATE ai.ai_job SET lock_version = 0 "
            "WHERE display_id = 'AIJ-ST0003-BATCH-00001';",
        ),
    )
    for mutate, restore in reversible_mutations:
        cluster.psql(database, mutate)
        assert_sql_fails(
            cluster,
            database,
            read_sql(DOWNGRADE),
            "fields contain canonical meaning",
        )
        cluster.psql(database, restore)

    cluster.psql(
        database,
        """
        SET session_replication_role = replica;
        INSERT INTO ai.evaluation_result (
            suite_code, suite_version, run_id, task_definition_id,
            model_route_version_id, prompt_version_id, case_key,
            metric_code, metric_value, passed
        )
        VALUES (
            'suite.baseline-compatible', 1, uuidv7(), uuidv7(), uuidv7(),
            uuidv7(), 'case-1', 'metric-1', 1, true
        );
        SET session_replication_role = origin;
        UPDATE ai.evaluation_result
           SET grader_code = 'grader.canonical.v1';
        """,
    )
    assert_sql_fails(
        cluster,
        database,
        read_sql(DOWNGRADE),
        "Evaluation Result fields contain canonical meaning",
    )


def test_downgrade_refuses_nonempty_governance_then_empty_round_trip_reupgrades(
    st0003_postgresql_cluster: Any,
) -> None:
    cluster = st0003_postgresql_cluster
    nonempty = baseline_to_st0002(cluster, "downgrade_refusal")
    upgrade_st0003(cluster, nonempty)
    seed_governance_dependencies(cluster, nonempty)
    assert_sql_fails(
        cluster,
        nonempty,
        read_sql(DOWNGRADE),
        "downgrade refused",
    )
    assert (
        cluster.query(
            nonempty,
            "SELECT to_regclass('ai.evaluation_suite') IS NOT NULL;",
        )
        == "t"
    )

    database = baseline_to_st0002(cluster, "downgrade_round_trip")
    baseline_before = full_ai_schema_and_data_signature(cluster, database)
    upgrade_st0003(cluster, database)
    before = schema_signature(cluster, database)
    apply_sql(cluster, database, DOWNGRADE)
    assert full_ai_schema_and_data_signature(cluster, database) == baseline_before
    assert (
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM information_schema.tables
             WHERE table_schema = 'ai'
               AND table_name IN (
                   'evaluation_suite', 'evaluation_dataset_version',
                   'evaluation_case', 'evaluation_run',
                   'evaluation_case_result', 'human_evaluation',
                   'judge_calibration', 'release_decision', 'release_approval'
               );
            """,
        )
        == "0"
    )
    upgrade_st0003(cluster, database)
    assert schema_signature(cluster, database) == before
