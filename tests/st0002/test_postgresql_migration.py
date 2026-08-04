from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import time
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DATABASE_DIR = REPO_ROOT / "changes" / "st-0002" / "database"
EXPAND_SQL = DATABASE_DIR / "202607300001_job_state_expand.sql"
EXPAND_VALIDATE_SQL = DATABASE_DIR / "202607300002_job_state_expand_validate.sql"
MIGRATE_BATCH_SQL = DATABASE_DIR / "202607300003_job_state_migrate_batch.sql"
CONTRACT_PREPARE_SQL = DATABASE_DIR / "202607300004_job_state_contract_prepare.sql"
CONTRACT_SQL = DATABASE_DIR / "202607300005_job_state_contract.sql"
DOWNGRADE_SQL = DATABASE_DIR / "202607300006_job_state_guarded_downgrade.sql"

EXPECTED_UPGRADED_STATES = {
    "ST0002-CANCELLED": "CANCELLED",
    "ST0002-FAILED": "FAILED_TERMINAL",
    "ST0002-PENDING": "REQUESTED",
    "ST0002-QUARANTINED": "QUARANTINED",
    "ST0002-READY": "QUEUED",
    "ST0002-RUNNING": "RUNNING",
    "ST0002-SUCCEEDED": "SUCCEEDED",
}
EXPECTED_BASELINE_STATES = {
    "ST0002-CANCELLED": "CANCELLED",
    "ST0002-FAILED": "FAILED",
    "ST0002-PENDING": "PENDING",
    "ST0002-QUARANTINED": "QUARANTINED",
    "ST0002-READY": "READY",
    "ST0002-RUNNING": "RUNNING",
    "ST0002-SUCCEEDED": "SUCCEEDED",
}
CANONICAL_STATES = (
    "REQUESTED",
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED_RETRYABLE",
    "RETRY_SCHEDULED",
    "FAILED_TERMINAL",
    "QUARANTINED",
    "CANCELLED",
    "EXPIRED",
)
TERMINAL_STATES = {
    "SUCCEEDED",
    "FAILED_TERMINAL",
    "QUARANTINED",
    "CANCELLED",
    "EXPIRED",
}


def _sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _apply(cluster: Any, database: str, *paths: Path) -> None:
    for path in paths:
        cluster.psql(database, _sql(path))


def _remaining_rows(cluster: Any, database: str) -> int:
    return int(
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM ops.job
             WHERE job_version IS NULL
                OR status IN ('PENDING', 'READY', 'FAILED');
            """,
        )
    )


def _migrate_all_batches(cluster: Any, database: str) -> int:
    completed_batches = 0
    while True:
        before = _remaining_rows(cluster, database)
        if before == 0:
            return completed_batches
        _apply(cluster, database, MIGRATE_BATCH_SQL)
        after = _remaining_rows(cluster, database)
        assert 0 <= before - after <= 1000
        assert after < before
        completed_batches += 1
        assert completed_batches < 10_000


def _upgrade(cluster: Any, database: str) -> None:
    _apply(cluster, database, EXPAND_SQL, EXPAND_VALIDATE_SQL)
    _migrate_all_batches(cluster, database)
    _apply(cluster, database, CONTRACT_PREPARE_SQL, CONTRACT_SQL)


def _wait_for_query_marker(cluster: Any, database: str, marker: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        active = cluster.query(
            database,
            f"""
            SELECT count(*)
              FROM pg_stat_activity
             WHERE datname = current_database()
               AND state = 'active'
               AND query LIKE '%{marker}%';
            """,
        )
        if active != "0":
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for PostgreSQL query marker {marker}")


def _assert_background_success(future: Future[Any]) -> None:
    result = future.result(timeout=15)
    assert result.returncode == 0


def _seed_legacy_jobs(cluster: Any, database: str) -> None:
    cluster.psql(
        database,
        """
        INSERT INTO ops.job (
            display_id,
            job_type,
            queue_name,
            status,
            completed_at,
            created_by_actor_type
        )
        VALUES
            ('ST0002-PENDING', 'ops.st0002_test.v1', 'st0002', 'PENDING', NULL, 'SYSTEM'),
            ('ST0002-READY', 'ops.st0002_test.v1', 'st0002', 'READY', NULL, 'SYSTEM'),
            ('ST0002-RUNNING', 'ops.st0002_test.v1', 'st0002', 'RUNNING', NULL, 'SYSTEM'),
            ('ST0002-SUCCEEDED', 'ops.st0002_test.v1', 'st0002', 'SUCCEEDED', clock_timestamp(), 'SYSTEM'),
            ('ST0002-FAILED', 'ops.st0002_test.v1', 'st0002', 'FAILED', clock_timestamp(), 'SYSTEM'),
            ('ST0002-CANCELLED', 'ops.st0002_test.v1', 'st0002', 'CANCELLED', clock_timestamp(), 'SYSTEM'),
            ('ST0002-QUARANTINED', 'ops.st0002_test.v1', 'st0002', 'QUARANTINED', clock_timestamp(), 'SYSTEM');
        """,
    )


def _state_map(cluster: Any, database: str) -> dict[str, str]:
    output = cluster.query(
        database,
        """
        SELECT display_id, status
          FROM ops.job
         WHERE job_type = 'ops.st0002_test.v1'
         ORDER BY display_id;
        """,
    )
    return dict(line.split("\t", 1) for line in output.splitlines() if line)


def _upgrade_row_signature(cluster: Any, database: str) -> str:
    return cluster.query(
        database,
        """
        SELECT
            display_id,
            status,
            job_version,
            COALESCE(deadline_at::text, '<NULL>'),
            COALESCE(cancel_requested_at::text, '<NULL>')
          FROM ops.job
         WHERE job_type = 'ops.st0002_test.v1'
         ORDER BY display_id;
        """,
    )


def _schema_signature(cluster: Any, database: str) -> str:
    return cluster.query(
        database,
        """
        SELECT 'column',
               ordinal_position::text,
               column_name,
               COALESCE(column_default, '<NULL>'),
               is_nullable
          FROM information_schema.columns
         WHERE table_schema = 'ops'
           AND table_name = 'job'
        UNION ALL
        SELECT 'constraint',
               '0',
               conname,
               pg_get_constraintdef(oid),
               convalidated::text
          FROM pg_constraint
         WHERE conrelid = 'ops.job'::regclass
        UNION ALL
        SELECT 'index',
               '0',
               indexname,
               indexdef,
               ''
          FROM pg_indexes
         WHERE schemaname = 'ops'
           AND tablename = 'job'
         ORDER BY 1, 2, 3, 4, 5;
        """,
    )


def _assert_failed_constraint(
    cluster: Any,
    database: str,
    sql: str,
    constraint_name: str,
) -> None:
    result = cluster.psql(database, sql, check=False)
    assert result.returncode != 0, result.stdout
    assert constraint_name in result.stderr


def test_immutable_baseline_fixture_is_postgresql_18(
    postgresql_cluster: Any,
) -> None:
    cluster = postgresql_cluster
    database = cluster.clone_database("baseline")

    assert cluster.server_version_num >= 180000
    assert (
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM information_schema.tables
             WHERE table_schema IN (
                 'ops', 'iam', 'portfolio', 'catalog', 'evidence', 'editorial',
                 'ai', 'policy', 'publishing', 'freshness', 'analytics',
                 'finance', 'readmodel'
             )
               AND table_type = 'BASE TABLE';
            """,
        )
        == "130"
    )
    assert (
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM pg_constraint AS c
              JOIN pg_namespace AS n
                ON n.oid = c.connamespace
             WHERE n.nspname IN (
                 'ops', 'iam', 'portfolio', 'catalog', 'evidence', 'editorial',
                 'ai', 'policy', 'publishing', 'freshness', 'analytics',
                 'finance', 'readmodel'
             )
               AND c.contype = 'f';
            """,
        )
        == "357"
    )

    baseline_columns = cluster.query(
        database,
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = 'ops'
           AND table_name = 'job'
           AND column_name IN (
               'job_version', 'deadline_at', 'cancel_requested_at'
           );
        """,
    )
    assert baseline_columns == ""
    status_default = cluster.query(
        database,
        """
        SELECT column_default
          FROM information_schema.columns
         WHERE table_schema = 'ops'
           AND table_name = 'job'
           AND column_name = 'status';
        """,
    )
    assert status_default == "'PENDING'::text"


def test_upgrade_maps_all_legacy_states_and_enforces_contract(
    postgresql_cluster: Any,
) -> None:
    cluster = postgresql_cluster
    database = cluster.clone_database("upgrade_contract")
    _seed_legacy_jobs(cluster, database)

    _upgrade(cluster, database)

    assert _state_map(cluster, database) == EXPECTED_UPGRADED_STATES
    assert (
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM ops.job
             WHERE job_type = 'ops.st0002_test.v1'
               AND job_version = 1;
            """,
        )
        == "7"
    )

    column_contract = cluster.query(
        database,
        """
        SELECT column_name, column_default, is_nullable
          FROM information_schema.columns
         WHERE table_schema = 'ops'
           AND table_name = 'job'
           AND column_name IN (
               'status', 'job_version', 'deadline_at', 'cancel_requested_at'
           )
         ORDER BY column_name;
        """,
    )
    assert column_contract.splitlines() == [
        "cancel_requested_at\t\tYES",
        "deadline_at\t\tYES",
        "job_version\t1\tNO",
        "status\t'REQUESTED'::text\tNO",
    ]

    cluster.psql(
        database,
        """
        INSERT INTO ops.job (
            display_id, job_type, queue_name, created_by_actor_type
        )
        VALUES (
            'ST0002-DEFAULTS', 'ops.st0002_default.v1', 'st0002', 'SYSTEM'
        );
        """,
    )
    assert (
        cluster.query(
            database,
            """
            SELECT status, job_version
              FROM ops.job
             WHERE display_id = 'ST0002-DEFAULTS';
            """,
        )
        == "REQUESTED\t1"
    )

    constraint_rows = cluster.query(
        database,
        """
        SELECT conname, pg_get_constraintdef(oid), convalidated
          FROM pg_constraint
         WHERE conrelid = 'ops.job'::regclass
         ORDER BY conname;
        """,
    ).splitlines()
    constraints = {
        row.split("\t", 2)[0]: row.split("\t", 2)[1:] for row in constraint_rows
    }
    expected_constraints = {
        "ck_ops_job_status",
        "ck_ops_job_completion",
        "ck_ops_job_version_positive",
        "ck_ops_job_deadline_order",
        "ck_ops_job_cancel_request",
    }
    assert expected_constraints <= constraints.keys()
    assert all(
        values[1] == "t"
        for name, values in constraints.items()
        if name in expected_constraints
    )
    assert not any(name.endswith("_expand") for name in constraints)
    for state in CANONICAL_STATES:
        assert state in constraints["ck_ops_job_status"][0]
    for state in ("PENDING", "READY", "FAILED"):
        assert f"'{state}'" not in constraints["ck_ops_job_status"][0]
    assert constraints["ck_ops_job_version"][0] == "CHECK ((lock_version >= 0))"
    assert constraints["ck_ops_job_version_positive"][0] == (
        "CHECK ((job_version >= 1))"
    )

    permission_matrix = cluster.query(
        database,
        """
        SELECT role_name,
               has_schema_privilege(role_name, 'ops', 'USAGE'),
               has_table_privilege(role_name, 'ops.job', 'SELECT'),
               has_table_privilege(role_name, 'ops.job', 'INSERT'),
               has_table_privilege(role_name, 'ops.job', 'UPDATE'),
               has_table_privilege(role_name, 'ops.job', 'DELETE')
          FROM unnest(
              ARRAY[
                  'raos_api_rw',
                  'raos_worker_rw',
                  'raos_dispatcher_rw',
                  'raos_projection_rw',
                  'raos_public_ro',
                  'raos_reporting_ro',
                  'raos_auditor_ro'
              ]
          ) AS role_name
         ORDER BY role_name;
        """,
    )
    assert permission_matrix.splitlines() == [
        "raos_api_rw\tt\tt\tt\tt\tf",
        "raos_auditor_ro\tt\tf\tf\tf\tf",
        "raos_dispatcher_rw\tt\tt\tf\tt\tf",
        "raos_projection_rw\tt\tt\tf\tf\tf",
        "raos_public_ro\tf\tf\tf\tf\tf",
        "raos_reporting_ro\tf\tf\tf\tf\tf",
        "raos_worker_rw\tt\tt\tt\tt\tf",
    ]

    index_rows = cluster.query(
        database,
        """
        SELECT indexname, indexdef
          FROM pg_indexes
         WHERE schemaname = 'ops'
           AND tablename = 'job'
         ORDER BY indexname;
        """,
    ).splitlines()
    indexes = {row.split("\t", 1)[0]: row.split("\t", 1)[1] for row in index_rows}
    assert "ix_ops_job_ready_st0002" not in indexes
    assert "ix_ops_job_deadline_st0002" not in indexes
    assert "ix_ops_job_ready" in indexes
    assert "ix_ops_job_deadline_active" in indexes
    ready_index = indexes["ix_ops_job_ready"]
    for state in ("REQUESTED", "QUEUED", "RETRY_SCHEDULED"):
        assert f"'{state}'::text" in ready_index
    assert "'PENDING'::text" not in ready_index
    assert "'READY'::text" not in ready_index
    deadline_index = indexes["ix_ops_job_deadline_active"]
    for state in (
        "REQUESTED",
        "QUEUED",
        "RUNNING",
        "FAILED_RETRYABLE",
        "RETRY_SCHEDULED",
    ):
        assert f"'{state}'::text" in deadline_index

    for state in CANONICAL_STATES:
        completed_at = "clock_timestamp()" if state in TERMINAL_STATES else "NULL"
        cluster.psql(
            database,
            f"""
            INSERT INTO ops.job (
                display_id,
                job_type,
                queue_name,
                status,
                completed_at,
                created_by_actor_type
            )
            VALUES (
                'ST0002-CANONICAL-{state}',
                'ops.st0002_canonical.v1',
                'st0002',
                '{state}',
                {completed_at},
                'SYSTEM'
            );
            """,
        )

    for state in ("PENDING", "READY", "FAILED", "UNKNOWN"):
        _assert_failed_constraint(
            cluster,
            database,
            f"""
            INSERT INTO ops.job (
                display_id,
                job_type,
                queue_name,
                status,
                completed_at,
                created_by_actor_type
            )
            VALUES (
                'ST0002-REJECT-{state}',
                'ops.st0002_rejected.v1',
                'st0002',
                '{state}',
                clock_timestamp(),
                'SYSTEM'
            );
            """,
            "ck_ops_job_status",
        )

    _assert_failed_constraint(
        cluster,
        database,
        """
        INSERT INTO ops.job (
            display_id, job_type, queue_name, job_version,
            created_by_actor_type
        )
        VALUES (
            'ST0002-BAD-VERSION', 'ops.st0002_invalid.v1',
            'st0002', 0, 'SYSTEM'
        );
        """,
        "ck_ops_job_version_positive",
    )
    _assert_failed_constraint(
        cluster,
        database,
        """
        INSERT INTO ops.job (
            display_id, job_type, queue_name, created_at, deadline_at,
            created_by_actor_type
        )
        VALUES (
            'ST0002-BAD-DEADLINE', 'ops.st0002_invalid.v1', 'st0002',
            TIMESTAMPTZ '2026-07-31 00:00:00+00',
            TIMESTAMPTZ '2026-07-31 00:00:00+00',
            'SYSTEM'
        );
        """,
        "ck_ops_job_deadline_order",
    )
    _assert_failed_constraint(
        cluster,
        database,
        """
        INSERT INTO ops.job (
            display_id, job_type, queue_name, status, completed_at,
            cancel_requested_at, created_by_actor_type
        )
        VALUES (
            'ST0002-BAD-CANCEL', 'ops.st0002_invalid.v1', 'st0002',
            'SUCCEEDED', clock_timestamp(), clock_timestamp(), 'SYSTEM'
        );
        """,
        "ck_ops_job_cancel_request",
    )
    _assert_failed_constraint(
        cluster,
        database,
        """
        INSERT INTO ops.job (
            display_id, job_type, queue_name, status, created_by_actor_type
        )
        VALUES (
            'ST0002-BAD-COMPLETION', 'ops.st0002_invalid.v1',
            'st0002', 'EXPIRED', 'SYSTEM'
        );
        """,
        "ck_ops_job_completion",
    )


def test_migrate_failure_rolls_back_then_original_migration_recovers(
    postgresql_cluster: Any,
) -> None:
    cluster = postgresql_cluster
    database = cluster.clone_database("migrate_rollback")
    _seed_legacy_jobs(cluster, database)
    _apply(cluster, database, EXPAND_SQL, EXPAND_VALIDATE_SQL)
    before = _upgrade_row_signature(cluster, database)

    migrate_sql = _sql(MIGRATE_BATCH_SQL)
    body, commit, suffix = migrate_sql.rpartition("COMMIT;")
    assert commit == "COMMIT;"
    injected_failure_sql = (
        body
        + "\n-- Test-only failure after this batch, before transaction commit.\n"
        + "SELECT 1 / 0;\n"
        + commit
        + suffix
    )
    result = cluster.psql(database, injected_failure_sql, check=False)
    assert result.returncode != 0
    assert "division by zero" in result.stderr

    assert _upgrade_row_signature(cluster, database) == before
    assert cluster.query(
        database,
        """
            SELECT string_agg(conname, ',' ORDER BY conname)
              FROM pg_constraint
             WHERE conrelid = 'ops.job'::regclass
               AND conname LIKE 'ck_ops_job_%_expand';
            """,
    ) == (
        "ck_ops_job_cancel_request_expand,"
        "ck_ops_job_completion_expand,"
        "ck_ops_job_deadline_expand,"
        "ck_ops_job_status_expand,"
        "ck_ops_job_version_expand"
    )
    assert (
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM pg_index
             WHERE indexrelid IN (
                 'ops.ix_ops_job_ready_st0002'::regclass,
                 'ops.ix_ops_job_deadline_st0002'::regclass
             )
               AND indisvalid
               AND indisready;
            """,
        )
        == "2"
    )

    assert _migrate_all_batches(cluster, database) == 1
    _apply(cluster, database, CONTRACT_PREPARE_SQL, CONTRACT_SQL)
    assert _state_map(cluster, database) == EXPECTED_UPGRADED_STATES
    assert (
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM ops.job
             WHERE job_type = 'ops.st0002_test.v1'
               AND job_version = 1;
            """,
        )
        == "7"
    )


def test_repeatable_migrate_commits_at_most_one_thousand_rows_per_batch(
    postgresql_cluster: Any,
) -> None:
    cluster = postgresql_cluster
    database = cluster.clone_database("bounded_batches")
    cluster.psql(
        database,
        """
        INSERT INTO ops.job (
            display_id,
            job_type,
            queue_name,
            status,
            created_by_actor_type
        )
        SELECT
            'ST0002-BATCH-' || lpad(value::text, 4, '0'),
            'ops.st0002_batch.v1',
            'st0002',
            'PENDING',
            'SYSTEM'
          FROM generate_series(1, 1001) AS value;
        """,
    )
    _apply(cluster, database, EXPAND_SQL, EXPAND_VALIDATE_SQL)

    assert _remaining_rows(cluster, database) == 1001
    _apply(cluster, database, MIGRATE_BATCH_SQL)
    assert _remaining_rows(cluster, database) == 1
    assert (
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM ops.job
             WHERE job_type = 'ops.st0002_batch.v1'
               AND status = 'REQUESTED'
               AND job_version = 1;
            """,
        )
        == "1000"
    )

    assert _migrate_all_batches(cluster, database) == 1
    _apply(cluster, database, CONTRACT_PREPARE_SQL, CONTRACT_SQL)
    assert (
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM ops.job
             WHERE job_type = 'ops.st0002_batch.v1'
               AND status = 'REQUESTED'
               AND job_version = 1;
            """,
        )
        == "1001"
    )


def test_migrate_revisits_a_row_skipped_by_a_competing_lock(
    postgresql_cluster: Any,
) -> None:
    cluster = postgresql_cluster
    database = cluster.clone_database("skip_locked_revisit")
    _seed_legacy_jobs(cluster, database)
    _apply(cluster, database, EXPAND_SQL, EXPAND_VALIDATE_SQL)

    locked_row_sql = """
        BEGIN;
        SELECT id
          FROM ops.job
         WHERE display_id = 'ST0002-PENDING'
         FOR UPDATE;
        SELECT pg_sleep(2) /* st0002_locked_row_probe */;
        COMMIT;
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        locked_row = executor.submit(cluster.psql, database, locked_row_sql)
        _wait_for_query_marker(cluster, database, "st0002_locked_row_probe")
        _apply(cluster, database, MIGRATE_BATCH_SQL)

        assert _remaining_rows(cluster, database) == 1
        assert (
            cluster.query(
                database,
                """
                SELECT status, COALESCE(job_version::text, '<NULL>')
                  FROM ops.job
                 WHERE display_id = 'ST0002-PENDING';
                """,
            )
            == "PENDING\t<NULL>"
        )
        _assert_background_success(locked_row)

    assert _migrate_all_batches(cluster, database) == 1
    _apply(cluster, database, CONTRACT_PREPARE_SQL, CONTRACT_SQL)
    assert _state_map(cluster, database) == EXPECTED_UPGRADED_STATES


def test_constraint_validation_does_not_retain_access_exclusive_lock(
    postgresql_cluster: Any,
) -> None:
    cluster = postgresql_cluster
    database = cluster.clone_database("online_validation")
    _seed_legacy_jobs(cluster, database)
    _apply(cluster, database, EXPAND_SQL)

    expand_validation = _sql(EXPAND_VALIDATE_SQL).replace(
        "\nCOMMIT;\n\n-- These indexes",
        (
            "\nSELECT pg_sleep(2) "
            "/* st0002_expand_validation_lock_probe */;\n"
            "COMMIT;\n\n-- These indexes"
        ),
        1,
    )
    assert "st0002_expand_validation_lock_probe" in expand_validation
    with ThreadPoolExecutor(max_workers=1) as executor:
        validation = executor.submit(cluster.psql, database, expand_validation)
        _wait_for_query_marker(
            cluster,
            database,
            "st0002_expand_validation_lock_probe",
        )
        cluster.psql(
            database,
            """
            SET lock_timeout = '500ms';
            INSERT INTO ops.job (
                display_id, job_type, queue_name, status, created_by_actor_type
            )
            VALUES (
                'ST0002-DURING-EXPAND-VALIDATE',
                'ops.st0002_online.v1',
                'st0002',
                'PENDING',
                'SYSTEM'
            );
            """,
        )
        _assert_background_success(validation)

    _migrate_all_batches(cluster, database)
    _apply(cluster, database, CONTRACT_PREPARE_SQL)
    contract_validation = _sql(CONTRACT_SQL).replace(
        "\nCOMMIT;\n\nBEGIN;",
        (
            "\nSELECT pg_sleep(2) "
            "/* st0002_contract_validation_lock_probe */;\n"
            "COMMIT;\n\nBEGIN;"
        ),
        1,
    )
    assert "st0002_contract_validation_lock_probe" in contract_validation
    with ThreadPoolExecutor(max_workers=1) as executor:
        validation = executor.submit(cluster.psql, database, contract_validation)
        _wait_for_query_marker(
            cluster,
            database,
            "st0002_contract_validation_lock_probe",
        )
        cluster.psql(
            database,
            """
            SET lock_timeout = '500ms';
            INSERT INTO ops.job (
                display_id,
                job_type,
                queue_name,
                status,
                job_version,
                created_by_actor_type
            )
            VALUES (
                'ST0002-DURING-CONTRACT-VALIDATE',
                'ops.st0002_online.v1',
                'st0002',
                'REQUESTED',
                1,
                'SYSTEM'
            );
            """,
        )
        _assert_background_success(validation)

    assert (
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM ops.job
             WHERE job_type = 'ops.st0002_online.v1'
               AND status = 'REQUESTED'
               AND job_version = 1;
            """,
        )
        == "2"
    )


def test_contract_prepare_rejects_a_valid_same_name_wrong_index(
    postgresql_cluster: Any,
) -> None:
    cluster = postgresql_cluster
    database = cluster.clone_database("wrong_revision_index")
    _seed_legacy_jobs(cluster, database)
    _apply(cluster, database, EXPAND_SQL, EXPAND_VALIDATE_SQL)
    _migrate_all_batches(cluster, database)
    cluster.psql(
        database,
        """
        DROP INDEX ops.ix_ops_job_ready_st0002;
        CREATE INDEX ix_ops_job_ready_st0002 ON ops.job (id);
        """,
    )

    schema_before = _schema_signature(cluster, database)
    result = cluster.psql(database, _sql(CONTRACT_PREPARE_SQL), check=False)

    assert result.returncode != 0
    assert "wrong definition" in result.stderr
    assert _schema_signature(cluster, database) == schema_before
    assert (
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM pg_constraint
             WHERE conrelid = 'ops.job'::regclass
               AND conname = 'ck_ops_job_status';
            """,
        )
        == "0"
    )

    cluster.psql(
        database,
        """
        DROP INDEX ops.ix_ops_job_ready_st0002;
        CREATE INDEX ix_ops_job_ready_st0002
            ON ops.job (queue_name, priority, available_at)
            WHERE status IN ('REQUESTED', 'QUEUED', 'RETRY_SCHEDULED');
        """,
    )
    _apply(cluster, database, CONTRACT_PREPARE_SQL, CONTRACT_SQL)
    assert _state_map(cluster, database) == EXPECTED_UPGRADED_STATES


def test_contract_prepare_writer_race_recovers_before_finalization(
    postgresql_cluster: Any,
) -> None:
    cluster = postgresql_cluster
    database = cluster.clone_database("contract_prepare_race")
    _seed_legacy_jobs(cluster, database)
    _apply(cluster, database, EXPAND_SQL, EXPAND_VALIDATE_SQL)
    _migrate_all_batches(cluster, database)

    contract_prepare = _sql(CONTRACT_PREPARE_SQL).replace(
        "\nALTER TABLE ops.job\n    ADD CONSTRAINT",
        (
            "\nSELECT pg_sleep(2) "
            "/* st0002_contract_prepare_race_probe */;\n\n"
            "ALTER TABLE ops.job\n    ADD CONSTRAINT"
        ),
        1,
    )
    assert "st0002_contract_prepare_race_probe" in contract_prepare
    with ThreadPoolExecutor(max_workers=1) as executor:
        prepare = executor.submit(cluster.psql, database, contract_prepare)
        _wait_for_query_marker(
            cluster,
            database,
            "st0002_contract_prepare_race_probe",
        )
        cluster.psql(
            database,
            """
            INSERT INTO ops.job (
                display_id, job_type, queue_name, status, created_by_actor_type
            )
            VALUES (
                'ST0002-PREPARE-RACE',
                'ops.st0002_prepare_race.v1',
                'st0002',
                'PENDING',
                'SYSTEM'
            );
            """,
        )
        _assert_background_success(prepare)

    assert _remaining_rows(cluster, database) == 1
    failed_contract = cluster.psql(database, _sql(CONTRACT_SQL), check=False)
    assert failed_contract.returncode != 0
    assert "blocked by legacy state or NULL job_version" in failed_contract.stderr

    assert _migrate_all_batches(cluster, database) == 1
    _apply(cluster, database, CONTRACT_SQL)
    assert (
        cluster.query(
            database,
            """
            SELECT status, job_version
              FROM ops.job
             WHERE display_id = 'ST0002-PREPARE-RACE';
            """,
        )
        == "REQUESTED\t1"
    )


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        (
            """
            UPDATE ops.job
               SET status = 'FAILED_RETRYABLE'
             WHERE display_id = 'ST0002-PENDING';
            """,
            "canonical-only Job states exist",
        ),
        (
            """
            UPDATE ops.job
               SET job_version = 2
             WHERE display_id = 'ST0002-PENDING';
            """,
            "canonical Job fields contain non-baseline meaning",
        ),
        (
            """
            UPDATE ops.job
               SET deadline_at = created_at + interval '1 day'
             WHERE display_id = 'ST0002-PENDING';
            """,
            "canonical Job fields contain non-baseline meaning",
        ),
        (
            """
            UPDATE ops.job
               SET cancel_requested_at = created_at + interval '1 second'
             WHERE display_id = 'ST0002-PENDING';
            """,
            "canonical Job fields contain non-baseline meaning",
        ),
    ),
    ids=("canonical-only-state", "job-version", "deadline", "cancel-request"),
)
def test_guarded_downgrade_refuses_loss_and_is_atomic(
    postgresql_cluster: Any,
    mutation: str,
    expected_error: str,
) -> None:
    cluster = postgresql_cluster
    database = cluster.clone_database("downgrade_refusal")
    _seed_legacy_jobs(cluster, database)
    _upgrade(cluster, database)
    cluster.psql(database, mutation)
    rows_before = _upgrade_row_signature(cluster, database)
    schema_before = _schema_signature(cluster, database)
    downgrade_sql = _sql(DOWNGRADE_SQL)
    assert "LOCK TABLE ops.job IN ACCESS EXCLUSIVE MODE;" in downgrade_sql

    result = cluster.psql(database, downgrade_sql, check=False)

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert _upgrade_row_signature(cluster, database) == rows_before
    assert _schema_signature(cluster, database) == schema_before


def test_guarded_downgrade_success_then_reupgrade(
    postgresql_cluster: Any,
) -> None:
    cluster = postgresql_cluster
    database = cluster.clone_database("downgrade_reupgrade")
    _seed_legacy_jobs(cluster, database)
    _upgrade(cluster, database)

    _apply(cluster, database, DOWNGRADE_SQL)

    assert _state_map(cluster, database) == EXPECTED_BASELINE_STATES
    assert (
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM information_schema.columns
             WHERE table_schema = 'ops'
               AND table_name = 'job'
               AND column_name IN (
                   'job_version', 'deadline_at', 'cancel_requested_at'
               );
            """,
        )
        == "0"
    )
    assert (
        cluster.query(
            database,
            """
            SELECT column_default
              FROM information_schema.columns
             WHERE table_schema = 'ops'
               AND table_name = 'job'
               AND column_name = 'status';
            """,
        )
        == "'PENDING'::text"
    )
    baseline_constraint_names = cluster.query(
        database,
        """
        SELECT conname
          FROM pg_constraint
         WHERE conrelid = 'ops.job'::regclass
           AND conname IN ('ck_ops_job_status', 'ck_ops_job_completion')
         ORDER BY conname;
        """,
    )
    assert baseline_constraint_names.splitlines() == [
        "ck_ops_job_completion",
        "ck_ops_job_status",
    ]
    assert (
        cluster.query(
            database,
            """
            SELECT pg_get_constraintdef(oid)
              FROM pg_constraint
             WHERE conrelid = 'ops.job'::regclass
               AND conname = 'ck_ops_job_version';
            """,
        )
        == "CHECK ((lock_version >= 0))"
    )
    ready_index = cluster.query(
        database,
        """
        SELECT indexdef
          FROM pg_indexes
         WHERE schemaname = 'ops'
           AND tablename = 'job'
           AND indexname = 'ix_ops_job_ready';
        """,
    )
    assert "'PENDING'::text" in ready_index
    assert "'READY'::text" in ready_index

    _upgrade(cluster, database)

    assert _state_map(cluster, database) == EXPECTED_UPGRADED_STATES
    assert (
        cluster.query(
            database,
            """
            SELECT column_default
              FROM information_schema.columns
             WHERE table_schema = 'ops'
               AND table_name = 'job'
               AND column_name = 'status';
            """,
        )
        == "'REQUESTED'::text"
    )
    assert (
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM ops.job
             WHERE job_type = 'ops.st0002_test.v1'
               AND job_version = 1;
            """,
        )
        == "7"
    )
