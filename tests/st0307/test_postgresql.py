from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from typing import Any

import pytest
from psycopg import sql

from .support import HistoricalDatabaseFactory, REPO_ROOT, apply_fixture, run_psql
from raos.migrations import catalog, runner
from scripts import build_st0305_publication_analytics_finance as st0305_generator
from scripts import build_st0307_migration_fixtures as generator
from tests.postgresql18 import PostgreSQLCluster


CHECKPOINTS = {spec.revision: spec for spec in catalog.CHECKPOINT_SPECS}
ST0002_FORWARD = catalog.FORWARD_PLAN[:5]
ST0003_FORWARD = catalog.FORWARD_PLAN[5:10]
ST0004_FORWARD = catalog.FORWARD_PLAN[10:]
HISTORICAL_SCHEMAS = (
    "iam",
    "ops",
    "portfolio",
    "catalog",
    "evidence",
    "editorial",
    "ai",
    "policy",
)
ST0305_SCHEMAS = tuple(st0305_generator.SCHEMAS)


def _checkpoint_bytes(revision: str) -> bytes:
    spec = CHECKPOINTS[revision]
    content = (REPO_ROOT / spec.relative_path).read_bytes()
    assert hashlib.sha256(content).hexdigest() == spec.sha256
    return content


def _apply_checkpoint(
    cluster: PostgreSQLCluster,
    database: str,
    revision: str,
    *,
    check: bool = True,
):
    """Apply exactly one hash-bound checkpoint in one independent psql call."""

    return run_psql(
        cluster,
        database,
        _checkpoint_bytes(revision).decode("utf-8"),
        check=check,
    )


def _apply_forward(
    cluster: PostgreSQLCluster,
    database: str,
    revisions: Iterable[str],
) -> None:
    for revision in revisions:
        _apply_checkpoint(cluster, database, revision)


def _injected_failure(content: bytes) -> str:
    text = content.decode("utf-8")
    body, marker, suffix = text.rpartition("COMMIT;")
    assert marker == "COMMIT;"
    return (
        body
        + "\n-- ST-0307 test-only failure before the checkpoint commit.\n"
        + "SELECT 1 / 0;\n"
        + marker
        + suffix
    )


def _rows(
    cluster: PostgreSQLCluster,
    database: str,
    statement: str,
    parameters: Sequence[object] = (),
) -> list[tuple[Any, ...]]:
    with cluster.connect(database) as connection:
        if parameters:
            result = connection.execute(statement, parameters)
        else:
            result = connection.execute(statement)
        return list(result.fetchall())


def _value(
    cluster: PostgreSQLCluster,
    database: str,
    statement: str,
    parameters: Sequence[object] = (),
) -> Any:
    rows = _rows(cluster, database, statement, parameters)
    assert len(rows) == 1 and len(rows[0]) == 1
    return rows[0][0]


def _schema_inventory(
    cluster: PostgreSQLCluster,
    database: str,
    schemas: Sequence[str],
) -> str:
    """Stable object/constraint/index/row-count signature for atomicity checks."""

    with cluster.connect(database) as connection:
        relation_rows = connection.execute(
            """
            SELECT namespace.nspname, relation.relname, relation.relkind,
                   relation.relpersistence
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = ANY(%s)
            ORDER BY 1, 2, 3
            """,
            (list(schemas),),
        ).fetchall()
        column_rows = connection.execute(
            """
            SELECT table_schema, table_name, column_name, data_type,
                   is_nullable, COALESCE(column_default, '')
            FROM information_schema.columns
            WHERE table_schema = ANY(%s)
            ORDER BY 1, 2, 3
            """,
            (list(schemas),),
        ).fetchall()
        constraint_rows = connection.execute(
            """
            SELECT namespace.nspname, relation.relname, constraint_record.conname,
                   constraint_record.contype,
                   pg_get_constraintdef(constraint_record.oid, true),
                   constraint_record.convalidated
            FROM pg_catalog.pg_constraint AS constraint_record
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = constraint_record.conrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = ANY(%s)
            ORDER BY 1, 2, 3
            """,
            (list(schemas),),
        ).fetchall()
        index_rows = connection.execute(
            """
            SELECT namespace.nspname, relation.relname, index_record.relname,
                   pg_get_indexdef(index_record.oid)
            FROM pg_catalog.pg_index AS index_metadata
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = index_metadata.indrelid
            JOIN pg_catalog.pg_class AS index_record
              ON index_record.oid = index_metadata.indexrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = ANY(%s)
            ORDER BY 1, 2, 3
            """,
            (list(schemas),),
        ).fetchall()
        function_rows = connection.execute(
            """
            SELECT namespace.nspname, routine.proname,
                   pg_get_function_identity_arguments(routine.oid),
                   pg_get_functiondef(routine.oid)
            FROM pg_catalog.pg_proc AS routine
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = routine.pronamespace
            WHERE namespace.nspname = ANY(%s)
            ORDER BY 1, 2, 3
            """,
            (list(schemas),),
        ).fetchall()
        trigger_rows = connection.execute(
            """
            SELECT namespace.nspname, relation.relname, trigger_record.tgname,
                   pg_get_triggerdef(trigger_record.oid, true)
            FROM pg_catalog.pg_trigger AS trigger_record
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = trigger_record.tgrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = ANY(%s)
              AND trigger_record.tgisinternal IS FALSE
            ORDER BY 1, 2, 3
            """,
            (list(schemas),),
        ).fetchall()
        table_names = connection.execute(
            """
            SELECT namespace.nspname, relation.relname
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = ANY(%s)
              AND relation.relkind IN ('r', 'p')
            ORDER BY 1, 2
            """,
            (list(schemas),),
        ).fetchall()
        row_counts = []
        for schema_name, table_name in table_names:
            count = connection.execute(
                sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(schema_name), sql.Identifier(table_name)
                )
            ).fetchone()
            assert count is not None
            row_counts.append((schema_name, table_name, count[0]))
    return json.dumps(
        {
            "relations": relation_rows,
            "columns": column_rows,
            "constraints": constraint_rows,
            "indexes": index_rows,
            "functions": function_rows,
            "triggers": trigger_rows,
            "row_counts": row_counts,
        },
        default=str,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _upgrade_st0002_empty(cluster: PostgreSQLCluster, database: str) -> None:
    _apply_forward(cluster, database, ST0002_FORWARD)


def _upgrade_st0003_empty(cluster: PostgreSQLCluster, database: str) -> None:
    _upgrade_st0002_empty(cluster, database)
    _apply_forward(cluster, database, ST0003_FORWARD)


def _upgrade_st0004_empty(cluster: PostgreSQLCluster, database: str) -> None:
    _upgrade_st0003_empty(cluster, database)
    _apply_forward(cluster, database, ST0004_FORWARD)


def _job_state_map(cluster: PostgreSQLCluster, database: str) -> dict[str, str]:
    return dict(
        _rows(
            cluster,
            database,
            """
            SELECT display_id, status
            FROM ops.job
            WHERE job_type = 'ops.st0307_job_alignment.v1'
            ORDER BY display_id
            """,
        )
    )


def _classify_ai_fixture(cluster: PostgreSQLCluster, database: str) -> None:
    run_psql(
        cluster,
        database,
        """
        UPDATE ai.ai_job
           SET status = 'QUARANTINED', updated_at = clock_timestamp()
         WHERE display_id = 'AIJ-ST0307-BLOCKED';
        UPDATE ai.prompt_version
           SET status = 'RETIRED',
               author_principal_id = '00000000-0000-7000-8000-000000000307',
               updated_at = clock_timestamp()
         WHERE display_id = 'PRM-ST0307-REJECTED';
        """,
    )


def test_job_fixture_maps_all_seven_legacy_states(
    postgresql_cluster: PostgreSQLCluster,
    historical_database_factory: HistoricalDatabaseFactory,
) -> None:
    database = historical_database_factory.clone("job_forward")
    apply_fixture(postgresql_cluster, database, generator.JOB_FIXTURE_PATH)
    _apply_forward(postgresql_cluster, database, ST0002_FORWARD)
    assert _job_state_map(postgresql_cluster, database) == {
        "ST0307-JOB-CANCELLED": "CANCELLED",
        "ST0307-JOB-FAILED": "FAILED_TERMINAL",
        "ST0307-JOB-PENDING": "REQUESTED",
        "ST0307-JOB-QUARANTINED": "QUARANTINED",
        "ST0307-JOB-READY": "QUEUED",
        "ST0307-JOB-RUNNING": "RUNNING",
        "ST0307-JOB-SUCCEEDED": "SUCCEEDED",
    }
    assert (
        _value(
            postgresql_cluster,
            database,
            "SELECT count(*) FROM ops.job WHERE job_type = 'ops.st0307_job_alignment.v1' AND job_version = 1",
        )
        == 7
    )


def test_job_batch_failure_rolls_back_then_two_bounded_batches_resume(
    postgresql_cluster: PostgreSQLCluster,
    historical_database_factory: HistoricalDatabaseFactory,
) -> None:
    database = historical_database_factory.clone("job_batch")
    run_psql(
        postgresql_cluster,
        database,
        """
        INSERT INTO ops.job (
            display_id, job_type, queue_name, status, created_by_actor_type
        )
        SELECT 'ST0307-JOB-BATCH-' || lpad(value::text, 5, '0'),
               'ops.st0307_batch.v1', 'st0307', 'PENDING', 'SYSTEM'
        FROM generate_series(1, 1001) AS value;
        """,
    )
    _apply_checkpoint(postgresql_cluster, database, ST0002_FORWARD[0])
    _apply_checkpoint(postgresql_cluster, database, ST0002_FORWARD[1])
    before = _rows(
        postgresql_cluster,
        database,
        "SELECT status, count(*) FROM ops.job WHERE job_type = 'ops.st0307_batch.v1' GROUP BY status ORDER BY status",
    )
    failed = run_psql(
        postgresql_cluster,
        database,
        _injected_failure(_checkpoint_bytes(ST0002_FORWARD[2])),
        check=False,
    )
    assert failed.returncode != 0
    assert "division by zero" in failed.stderr
    assert (
        _rows(
            postgresql_cluster,
            database,
            "SELECT status, count(*) FROM ops.job WHERE job_type = 'ops.st0307_batch.v1' GROUP BY status ORDER BY status",
        )
        == before
    )
    _apply_checkpoint(postgresql_cluster, database, ST0002_FORWARD[2])
    assert _rows(
        postgresql_cluster,
        database,
        "SELECT status, count(*) FROM ops.job WHERE job_type = 'ops.st0307_batch.v1' GROUP BY status ORDER BY status",
    ) == [("PENDING", 1), ("REQUESTED", 1000)]
    _apply_checkpoint(postgresql_cluster, database, ST0002_FORWARD[2])
    assert _rows(
        postgresql_cluster,
        database,
        "SELECT status, count(*) FROM ops.job WHERE job_type = 'ops.st0307_batch.v1' GROUP BY status ORDER BY status",
    ) == [("REQUESTED", 1001)]


def test_job_guarded_loss_refusal_is_atomic_then_representable_roundtrip_passes(
    postgresql_cluster: PostgreSQLCluster,
    historical_database_factory: HistoricalDatabaseFactory,
) -> None:
    database = historical_database_factory.clone("job_guard")
    apply_fixture(postgresql_cluster, database, generator.JOB_FIXTURE_PATH)
    _apply_forward(postgresql_cluster, database, ST0002_FORWARD)
    run_psql(
        postgresql_cluster,
        database,
        "UPDATE ops.job SET job_version = 2 WHERE display_id = 'ST0307-JOB-PENDING';",
    )
    before_inventory = _schema_inventory(
        postgresql_cluster, database, HISTORICAL_SCHEMAS
    )
    before_rows = _rows(
        postgresql_cluster,
        database,
        "SELECT display_id, status, job_version, deadline_at, cancel_requested_at FROM ops.job WHERE job_type = 'ops.st0307_job_alignment.v1' ORDER BY display_id",
    )
    refused = _apply_checkpoint(
        postgresql_cluster, database, "202607300006", check=False
    )
    assert refused.returncode != 0
    assert "canonical Job fields contain non-baseline meaning" in refused.stderr
    assert (
        _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS)
        == before_inventory
    )
    assert (
        _rows(
            postgresql_cluster,
            database,
            "SELECT display_id, status, job_version, deadline_at, cancel_requested_at FROM ops.job WHERE job_type = 'ops.st0307_job_alignment.v1' ORDER BY display_id",
        )
        == before_rows
    )
    run_psql(
        postgresql_cluster,
        database,
        "UPDATE ops.job SET job_version = 1 WHERE display_id = 'ST0307-JOB-PENDING';",
    )
    _apply_checkpoint(postgresql_cluster, database, "202607300006")
    assert set(_job_state_map(postgresql_cluster, database).values()) == {
        "PENDING",
        "READY",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "QUARANTINED",
    }
    _apply_forward(postgresql_cluster, database, ST0002_FORWARD)
    assert set(_job_state_map(postgresql_cluster, database).values()) == {
        "REQUESTED",
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED_TERMINAL",
        "CANCELLED",
        "QUARANTINED",
    }


def test_ai_fixture_preserves_ambiguous_rows_until_explicit_classification(
    postgresql_cluster: PostgreSQLCluster,
    historical_database_factory: HistoricalDatabaseFactory,
) -> None:
    database = historical_database_factory.clone("ai_no_guess")
    _upgrade_st0002_empty(postgresql_cluster, database)
    apply_fixture(postgresql_cluster, database, generator.AI_FIXTURE_PATH)
    _apply_forward(postgresql_cluster, database, ST0003_FORWARD[:3])
    assert dict(
        _rows(
            postgresql_cluster,
            database,
            "SELECT display_id, status FROM ai.ai_job WHERE display_id LIKE 'AIJ-ST0307-%' ORDER BY display_id",
        )
    ) == {
        "AIJ-ST0307-BLOCKED": "BLOCKED",
        "AIJ-ST0307-FAILED": "FAILED_TERMINAL",
        "AIJ-ST0307-PENDING": "REQUESTED",
    }
    assert _rows(
        postgresql_cluster,
        database,
        "SELECT status, author_principal_id FROM ai.prompt_version WHERE display_id = 'PRM-ST0307-REJECTED'",
    ) == [("REJECTED", None)]
    before = _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS)
    refused = _apply_checkpoint(
        postgresql_cluster, database, ST0003_FORWARD[3], check=False
    )
    assert refused.returncode != 0
    assert (
        "Contract prepare blocked by backlog, BLOCKED AI Job, or REJECTED Prompt"
        in (refused.stderr)
    )
    assert _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS) == before
    _classify_ai_fixture(postgresql_cluster, database)
    _apply_checkpoint(postgresql_cluster, database, ST0003_FORWARD[3])
    _apply_checkpoint(postgresql_cluster, database, ST0003_FORWARD[4])
    assert _rows(
        postgresql_cluster,
        database,
        "SELECT display_id, status FROM ai.ai_job WHERE display_id IN ('AIJ-ST0307-BLOCKED', 'AIJ-ST0307-FAILED', 'AIJ-ST0307-PENDING') ORDER BY display_id",
    ) == [
        ("AIJ-ST0307-BLOCKED", "QUARANTINED"),
        ("AIJ-ST0307-FAILED", "FAILED_TERMINAL"),
        ("AIJ-ST0307-PENDING", "REQUESTED"),
    ]
    refused_down = _apply_checkpoint(
        postgresql_cluster, database, "202607300012", check=False
    )
    assert refused_down.returncode != 0
    assert "downgrade refused" in refused_down.stderr


def test_ai_batch_failure_rolls_back_then_bounded_batches_resume(
    postgresql_cluster: PostgreSQLCluster,
    historical_database_factory: HistoricalDatabaseFactory,
) -> None:
    database = historical_database_factory.clone("ai_batch")
    _upgrade_st0002_empty(postgresql_cluster, database)
    run_psql(
        postgresql_cluster,
        database,
        """
        BEGIN;
        SET LOCAL session_replication_role = replica;
        INSERT INTO ai.ai_job (
            display_id, ops_job_id, task_definition_id, article_plan_id,
            source_packet_version_id, prompt_version_id,
            output_schema_version_id, model_route_version_id,
            status, max_cost_jpy, completed_at
        )
        SELECT 'AIJ-ST0307-BATCH-' || lpad(value::text, 5, '0'),
               uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(),
               uuidv7(), 'PENDING', 100, NULL
        FROM generate_series(1, 1001) AS value;
        SET LOCAL session_replication_role = origin;
        COMMIT;
        """,
    )
    _apply_checkpoint(postgresql_cluster, database, ST0003_FORWARD[0])
    _apply_checkpoint(postgresql_cluster, database, ST0003_FORWARD[1])
    before = _rows(
        postgresql_cluster,
        database,
        "SELECT status, count(*) FROM ai.ai_job WHERE display_id LIKE 'AIJ-ST0307-BATCH-%' GROUP BY status ORDER BY status",
    )
    failed = run_psql(
        postgresql_cluster,
        database,
        _injected_failure(_checkpoint_bytes(ST0003_FORWARD[2])),
        check=False,
    )
    assert failed.returncode != 0
    assert "division by zero" in failed.stderr
    assert (
        _rows(
            postgresql_cluster,
            database,
            "SELECT status, count(*) FROM ai.ai_job WHERE display_id LIKE 'AIJ-ST0307-BATCH-%' GROUP BY status ORDER BY status",
        )
        == before
    )
    _apply_checkpoint(postgresql_cluster, database, ST0003_FORWARD[2])
    assert _rows(
        postgresql_cluster,
        database,
        "SELECT status, count(*) FROM ai.ai_job WHERE display_id LIKE 'AIJ-ST0307-BATCH-%' GROUP BY status ORDER BY status",
    ) == [("PENDING", 1), ("REQUESTED", 1000)]
    _apply_checkpoint(postgresql_cluster, database, ST0003_FORWARD[2])
    assert _rows(
        postgresql_cluster,
        database,
        "SELECT status, count(*) FROM ai.ai_job WHERE display_id LIKE 'AIJ-ST0307-BATCH-%' GROUP BY status ORDER BY status",
    ) == [("REQUESTED", 1001)]


def test_ai_empty_guarded_downgrade_and_reupgrade_roundtrip(
    postgresql_cluster: PostgreSQLCluster,
    historical_database_factory: HistoricalDatabaseFactory,
) -> None:
    database = historical_database_factory.clone("ai_roundtrip")
    _upgrade_st0002_empty(postgresql_cluster, database)
    predecessor = _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS)
    _apply_forward(postgresql_cluster, database, ST0003_FORWARD)
    final = _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS)
    _apply_checkpoint(postgresql_cluster, database, "202607300012")
    assert (
        _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS)
        == predecessor
    )
    _apply_forward(postgresql_cluster, database, ST0003_FORWARD)
    assert _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS) == final


def test_content_fixture_reports_all_four_operator_bindings_and_refuses_contract(
    postgresql_cluster: PostgreSQLCluster,
    historical_database_factory: HistoricalDatabaseFactory,
) -> None:
    database = historical_database_factory.clone("content_no_guess")
    _upgrade_st0003_empty(postgresql_cluster, database)
    apply_fixture(postgresql_cluster, database, generator.CONTENT_FIXTURE_PATH)
    _apply_forward(postgresql_cluster, database, ST0004_FORWARD[:3])
    assert _rows(
        postgresql_cluster,
        database,
        """
        SELECT content_schema_version_id, article_type_version_id,
               article_template_version_id, seo_metadata_version_id
        FROM editorial.article_version
        WHERE display_id = 'ARV-ST0307-NO-GUESS'
        """,
    ) == [(None, None, None, None)]
    assert (
        _value(
            postgresql_cluster,
            database,
            """
        SELECT count(*)
        FROM editorial.article_version
        WHERE display_id = 'ARV-ST0307-NO-GUESS'
          AND content_schema_version_id IS NULL
          AND article_type_version_id IS NULL
          AND article_template_version_id IS NULL
          AND seo_metadata_version_id IS NULL
        """,
        )
        == 1
    )
    before = _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS)
    refused = _apply_checkpoint(
        postgresql_cluster, database, ST0004_FORWARD[3], check=False
    )
    assert refused.returncode != 0
    assert "four-column operator binding backlog remains" in refused.stderr
    assert _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS) == before


def test_content_zero_change_batch_failure_rolls_back_then_resumes_without_guessing(
    postgresql_cluster: PostgreSQLCluster,
    historical_database_factory: HistoricalDatabaseFactory,
) -> None:
    database = historical_database_factory.clone("content_batch")
    _upgrade_st0003_empty(postgresql_cluster, database)
    apply_fixture(postgresql_cluster, database, generator.CONTENT_FIXTURE_PATH)
    _apply_checkpoint(postgresql_cluster, database, ST0004_FORWARD[0])
    _apply_checkpoint(postgresql_cluster, database, ST0004_FORWARD[1])
    before_inventory = _schema_inventory(
        postgresql_cluster, database, HISTORICAL_SCHEMAS
    )
    before_row = _rows(
        postgresql_cluster,
        database,
        "SELECT * FROM editorial.article_version WHERE display_id = 'ARV-ST0307-NO-GUESS'",
    )
    failed = run_psql(
        postgresql_cluster,
        database,
        _injected_failure(_checkpoint_bytes(ST0004_FORWARD[2])),
        check=False,
    )
    assert failed.returncode != 0
    assert "division by zero" in failed.stderr
    assert (
        _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS)
        == before_inventory
    )
    assert (
        _rows(
            postgresql_cluster,
            database,
            "SELECT * FROM editorial.article_version WHERE display_id = 'ARV-ST0307-NO-GUESS'",
        )
        == before_row
    )
    completed = _apply_checkpoint(postgresql_cluster, database, ST0004_FORWARD[2])
    assert "operator_required_rows" in completed.stdout
    assert completed.stdout.count('"operator_required_rows": 1') == 4
    assert "0\t1000" in completed.stdout
    assert "0\t1\t1\t1\t1\t1\t1" in completed.stdout
    assert _rows(
        postgresql_cluster,
        database,
        """
        SELECT content_schema_version_id, article_type_version_id,
               article_template_version_id, seo_metadata_version_id
        FROM editorial.article_version
        WHERE display_id = 'ARV-ST0307-NO-GUESS'
        """,
    ) == [(None, None, None, None)]


def test_content_guarded_nonempty_refusal_then_empty_roundtrip(
    postgresql_cluster: PostgreSQLCluster,
    historical_database_factory: HistoricalDatabaseFactory,
) -> None:
    database = historical_database_factory.clone("content_guard")
    _upgrade_st0003_empty(postgresql_cluster, database)
    predecessor = _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS)
    _apply_forward(postgresql_cluster, database, ST0004_FORWARD)
    final = _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS)
    run_psql(
        postgresql_cluster,
        database,
        """
        INSERT INTO editorial.article_type_version (
            article_type_code, semantic_version, contract, contract_sha256
        ) VALUES ('st0307_fixture', '1.0.0', '{}'::jsonb, repeat('b', 64));
        """,
    )
    before_refusal = _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS)
    refused = _apply_checkpoint(
        postgresql_cluster, database, "202607300018", check=False
    )
    assert refused.returncode != 0
    assert "downgrade refused" in refused.stderr
    assert (
        _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS)
        == before_refusal
    )
    run_psql(
        postgresql_cluster,
        database,
        "DELETE FROM editorial.article_type_version WHERE article_type_code = 'st0307_fixture';",
    )
    assert _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS) == final
    _apply_checkpoint(postgresql_cluster, database, "202607300018")
    assert (
        _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS)
        == predecessor
    )
    _apply_forward(postgresql_cluster, database, ST0004_FORWARD)
    assert _schema_inventory(postgresql_cluster, database, HISTORICAL_SCHEMAS) == final


def _migration_runner(
    cluster: PostgreSQLCluster,
    database: str,
) -> runner.MigrationRunner:
    return runner.MigrationRunner(REPO_ROOT, cluster.target(database))


def _artifact_signature(cluster: PostgreSQLCluster, database: str) -> tuple[Any, ...]:
    rows = _rows(
        cluster,
        database,
        """
        SELECT id::text, display_id, artifact_kind, storage_provider,
               bucket_name, object_key, object_version, content_type,
               byte_size, sha256, encryption_state, retention_class,
               is_immutable, source_system, metadata::text
        FROM ops.object_artifact
        WHERE id = '00000000-0000-0000-0000-000000000060'
        """,
    )
    assert len(rows) == 1
    return rows[0]


def test_production_predecessor_to_head_preserves_data_history_and_atomic_guards(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    historical_specs = catalog.REVISION_SPECS[:-1]
    assert (
        historical_specs[-1].revision == catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION
    )
    with monkeypatch.context() as historical:
        historical.setattr(catalog, "REVISION_SPECS", historical_specs)
        historical.setattr(
            catalog,
            "HEAD_REVISION",
            catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION,
        )
        historical.setattr(runner, "REVISION_SPECS", historical_specs)
        historical.setattr(
            runner,
            "HEAD_REVISION",
            catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION,
        )
        predecessor_runner = _migration_runner(postgresql_cluster, empty_database)
        assert (
            predecessor_runner.upgrade().current_revision
            == catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION
        )

    apply_fixture(
        postgresql_cluster,
        empty_database,
        generator.PREDECESSOR_FIXTURE_PATH,
    )
    predecessor_signature = _artifact_signature(postgresql_cluster, empty_database)
    current_runner = _migration_runner(postgresql_cluster, empty_database)
    upgraded = current_runner.upgrade()
    assert upgraded.current_revision == catalog.HEAD_REVISION
    assert upgraded.changed is True
    assert (
        _artifact_signature(postgresql_cluster, empty_database) == predecessor_signature
    )
    noop = current_runner.upgrade()
    assert noop.current_revision == catalog.HEAD_REVISION
    assert noop.changed is False
    run_psql(
        postgresql_cluster,
        empty_database,
        """
        INSERT INTO finance.parser_version (
            id, provider_code, format_code, version, code_sha256,
            schema_artifact_id, status, released_at
        ) VALUES (
            '00000000-0000-0000-0000-000000000061', 'fixture', 'csv',
            '1.0.0', repeat('7', 64),
            '00000000-0000-0000-0000-000000000060', 'ACTIVE',
            TIMESTAMPTZ '2026-08-05 00:00:00+00'
        );
        """,
    )
    head_downgrade = current_runner.downgrade()
    assert (
        head_downgrade.current_revision
        == catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION
    )
    assert (
        _artifact_signature(postgresql_cluster, empty_database) == predecessor_signature
    )
    assert (
        _value(
            postgresql_cluster,
            empty_database,
            "SELECT count(*) FROM finance.parser_version",
        )
        == 1
    )
    before_refusal = _schema_inventory(
        postgresql_cluster, empty_database, ST0305_SCHEMAS
    )
    with pytest.raises(runner.MigrationError) as raised:
        current_runner.downgrade()
    assert raised.value.code is runner.MigrationErrorCode.MIGRATION_FAILED
    assert (
        _schema_inventory(postgresql_cluster, empty_database, ST0305_SCHEMAS)
        == before_refusal
    )
    assert (
        _value(
            postgresql_cluster,
            empty_database,
            "SELECT version_num FROM public.raos_migration_version",
        )
        == catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION
    )
    assert (
        _value(
            postgresql_cluster,
            empty_database,
            "SELECT count(*) FROM finance.parser_version",
        )
        == 1
    )
    run_psql(
        postgresql_cluster,
        empty_database,
        "DELETE FROM finance.parser_version WHERE id = '00000000-0000-0000-0000-000000000061';",
    )
    downgraded = current_runner.downgrade()
    assert downgraded.current_revision == catalog.DOMAIN_REVISION
    assert (
        _artifact_signature(postgresql_cluster, empty_database) == predecessor_signature
    )
    assert (
        _value(
            postgresql_cluster,
            empty_database,
            "SELECT count(*) FROM information_schema.schemata WHERE schema_name = ANY(%s)",
            (list(ST0305_SCHEMAS),),
        )
        == 0
    )
    reupgraded = current_runner.upgrade()
    assert reupgraded.current_revision == catalog.HEAD_REVISION
    assert (
        _artifact_signature(postgresql_cluster, empty_database) == predecessor_signature
    )
    history = _rows(
        postgresql_cluster,
        empty_database,
        """
        SELECT direction, status
        FROM public.raos_migration_history
        WHERE revision_id = %s
        ORDER BY event_id
        """,
        (catalog.HEAD_REVISION,),
    )
    assert history.count(("UPGRADE", "SUCCEEDED")) == 2
    assert history.count(("DOWNGRADE", "SUCCEEDED")) == 1
    predecessor_history = _rows(
        postgresql_cluster,
        empty_database,
        """
        SELECT direction, status
        FROM public.raos_migration_history
        WHERE revision_id = %s
        ORDER BY event_id
        """,
        (catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION,),
    )
    assert predecessor_history.count(("UPGRADE", "SUCCEEDED")) == 2
    assert predecessor_history.count(("DOWNGRADE", "SUCCEEDED")) == 1
    assert ("DOWNGRADE", "FAILED") in predecessor_history
