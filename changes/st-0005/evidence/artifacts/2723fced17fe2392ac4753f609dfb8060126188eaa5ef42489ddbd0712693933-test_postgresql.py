"""Exact PostgreSQL 18.4 runtime acceptance tests for the ST-0303 slice."""

from __future__ import annotations

import psycopg
import pytest
from psycopg import sql

from conftest import REPOSITORY_ROOT
from raos.migrations import MigrationError
from raos.migrations import runner
from scripts import build_st0303_iam_ops as generator
from tests.postgresql18 import PostgreSQLCluster


IAM_OPS_REVISION = "202608030003"
FOUNDATION_REVISION = "202608030002"
_UNLISTED_OBJECT_STATEMENTS = (
    "CREATE VIEW iam.st0303_drift_view AS SELECT 1 AS value",
    "CREATE SEQUENCE ops.st0303_drift_sequence",
    "CREATE POLICY st0303_drift_policy ON ops.job USING (true)",
)
_INDIRECT_CATALOG_DRIFT_STATEMENTS = (
    "CREATE CAST (ops.job AS text) WITH INOUT AS ASSIGNMENT",
    "CREATE PUBLICATION st0303_schema_publication FOR TABLES IN SCHEMA ops",
    "CREATE PUBLICATION st0303_all_publication FOR ALL TABLES",
)
_TYPE_PROPERTY_DRIFT_STATEMENTS = (
    "COMMENT ON TYPE ops.job IS 'drift type comment'",
    "GRANT USAGE ON TYPE ops.job TO PUBLIC",
)
_CURRENT_HEAD_UNMANAGED_STATEMENTS = (
    "CREATE SCHEMA st0303_unmanaged",
    "CREATE TABLE public.st0303_unmanaged (id integer)",
    (
        "CREATE FUNCTION public.st0303_unmanaged() RETURNS integer "
        "LANGUAGE sql AS 'SELECT 1'"
    ),
    "CREATE TYPE public.st0303_unmanaged_enum AS ENUM ('A')",
)
_PUBLIC_DEFAULT_ACL_DRIFT_STATEMENT = (
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO PUBLIC"
)
_PUBLIC_METADATA_ACL_DRIFT_STATEMENTS = (
    ("GRANT SELECT (story_id) ON public.raos_migration_history TO PUBLIC"),
    "GRANT USAGE ON TYPE public.raos_migration_history TO PUBLIC",
)
_SCHEMA_VALIDATION_DRIFT_STATEMENTS = (
    "COMMENT ON SCHEMA ops IS 'drift comment'",
    "GRANT USAGE ON SCHEMA iam TO PUBLIC",
    "REVOKE CREATE ON SCHEMA iam FROM CURRENT_USER",
)


def _migration_runner(
    cluster: PostgreSQLCluster, database: str
) -> runner.MigrationRunner:
    return runner.MigrationRunner(REPOSITORY_ROOT, cluster.target(database))


def _owned_tables(connection: psycopg.Connection[object]) -> list[str]:
    return [
        f"{schema}.{table}"
        for schema, table in connection.execute(
            """
            SELECT n.nspname, c.relname
            FROM pg_catalog.pg_class AS c
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname IN ('iam', 'ops')
              AND c.relkind = 'r'
            ORDER BY n.nspname, c.relname
            """
        ).fetchall()
    ]


def test_zero_database_reaches_exact_head_and_validation_sql_passes(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)

    assert instance.status().current_revision == "base"
    result = instance.upgrade()
    assert result.current_revision == IAM_OPS_REVISION
    assert result.changed is True
    assert instance.upgrade().changed is False
    assert instance.status().current_revision == IAM_OPS_REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.raos_migration_version"
        ).fetchone() == (IAM_OPS_REVISION,)
        assert connection.execute(
            """
            SELECT revision_id, story_id, direction, status, runner_version
            FROM public.raos_migration_history
            ORDER BY event_id
            """
        ).fetchall() == [
            ("202608030001", "ST-0301", "UPGRADE", "SUCCEEDED", "1.0.0"),
            (FOUNDATION_REVISION, "ST-0302", "UPGRADE", "STARTED", "1.1.0"),
            (FOUNDATION_REVISION, "ST-0302", "UPGRADE", "SUCCEEDED", "1.1.0"),
            (IAM_OPS_REVISION, "ST-0303", "UPGRADE", "STARTED", "1.2.0"),
            (IAM_OPS_REVISION, "ST-0303", "UPGRADE", "SUCCEEDED", "1.2.0"),
        ]

        validation = (
            REPOSITORY_ROOT / "changes/st-0303/generated/iam-ops-validation.v1.sql"
        ).read_text(encoding="utf-8")
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")
            cursor.execute("SET search_path = pg_catalog")
            cursor.execute(
                sql.SQL("SET ROLE {}").format(
                    sql.Identifier(postgresql_cluster.migration_user)
                )
            )
            cursor.execute(validation)
            assert cursor.nextset() is True
            assert cursor.fetchall() == [("PASS", 17, 219, 20, 2)]
            assert cursor.nextset() is None


def test_status_rejects_history_independent_column_catalog_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(
            "COMMENT ON COLUMN ops.job.priority IS 'tampered column comment'"
        )

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


@pytest.mark.parametrize(
    "statement",
    _UNLISTED_OBJECT_STATEMENTS,
)
def test_status_rejects_unlisted_schema_object_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statement: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(statement)

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


@pytest.mark.parametrize("statement", _INDIRECT_CATALOG_DRIFT_STATEMENTS)
def test_status_rejects_indirect_catalog_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statement: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    # These global catalog objects require elevated fixture ownership. Runtime
    # validation still reconnects as the migration owner and must reject them.
    with postgresql_cluster.connect(empty_database) as administrator:
        administrator.execute(statement)

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


@pytest.mark.parametrize(
    "statement",
    (
        "COMMENT ON INDEX ops.ix_ops_job_ready IS 'drift comment'",
        ("COMMENT ON CONSTRAINT ck_ops_job_priority ON ops.job IS 'drift comment'"),
        "COMMENT ON INDEX ops.pk_ops_job IS 'drift comment'",
    ),
)
def test_status_rejects_constraint_or_index_comment_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statement: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(statement)

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


@pytest.mark.parametrize("statement", _TYPE_PROPERTY_DRIFT_STATEMENTS)
def test_status_rejects_type_property_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statement: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(statement)

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


@pytest.mark.parametrize("statement", _CURRENT_HEAD_UNMANAGED_STATEMENTS)
def test_status_rejects_current_head_unmanaged_boundary_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statement: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(statement)

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


@pytest.mark.parametrize(
    "statement",
    (
        "COMMENT ON TABLE public.raos_migration_history IS 'drift comment'",
        (
            "CREATE INDEX ix_st0303_history_drift "
            "ON public.raos_migration_history (story_id)"
        ),
    ),
)
def test_status_rejects_history_metadata_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statement: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(statement)

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


def test_status_rejects_history_trigger_function_owner_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    drift_owner = "st0303_history_owner_drift"

    with postgresql_cluster.connect(empty_database) as administrator:
        administrator.execute(
            sql.SQL("CREATE ROLE {}").format(sql.Identifier(drift_owner))
        )
        administrator.execute(
            sql.SQL(
                "ALTER FUNCTION "
                "public.raos_reject_migration_history_mutation_st0301() "
                "OWNER TO {}"
            ).format(sql.Identifier(drift_owner))
        )
    try:
        with pytest.raises(MigrationError) as raised:
            instance.status()
        assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID
    finally:
        with postgresql_cluster.connect(empty_database) as administrator:
            administrator.execute(
                sql.SQL(
                    "ALTER FUNCTION "
                    "public.raos_reject_migration_history_mutation_st0301() "
                    "OWNER TO {}"
                ).format(sql.Identifier(postgresql_cluster.migration_user))
            )
            administrator.execute(
                sql.SQL("DROP ROLE {}").format(sql.Identifier(drift_owner))
            )


@pytest.mark.parametrize("statement", _PUBLIC_METADATA_ACL_DRIFT_STATEMENTS)
def test_status_rejects_public_metadata_acl_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statement: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(statement)

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


def test_status_rejects_public_metadata_comment_fingerprint_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    comment_cases = (
        (
            "COMMENT ON TABLE public.raos_migration_version IS 'drift comment'",
            "COMMENT ON TABLE public.raos_migration_version IS NULL",
        ),
        (
            "COMMENT ON SEQUENCE public.raos_migration_history_event_id_seq "
            "IS 'drift comment'",
            "COMMENT ON SEQUENCE public.raos_migration_history_event_id_seq IS NULL",
        ),
        (
            "COMMENT ON COLUMN public.raos_migration_history.story_id "
            "IS 'drift comment'",
            "COMMENT ON COLUMN public.raos_migration_history.story_id IS NULL",
        ),
        (
            "COMMENT ON CONSTRAINT pk_raos_migration_history "
            "ON public.raos_migration_history IS 'drift comment'",
            "COMMENT ON CONSTRAINT pk_raos_migration_history "
            "ON public.raos_migration_history IS NULL",
        ),
        (
            "COMMENT ON INDEX public.pk_raos_migration_history IS 'drift comment'",
            "COMMENT ON INDEX public.pk_raos_migration_history IS NULL",
        ),
        (
            "COMMENT ON FUNCTION "
            "public.raos_reject_migration_history_mutation_st0301() "
            "IS 'drift comment'",
            "COMMENT ON FUNCTION "
            "public.raos_reject_migration_history_mutation_st0301() IS NULL",
        ),
        (
            "COMMENT ON TRIGGER trg_raos_migration_history_append_only "
            "ON public.raos_migration_history IS 'drift comment'",
            "COMMENT ON TRIGGER trg_raos_migration_history_append_only "
            "ON public.raos_migration_history IS NULL",
        ),
        (
            "COMMENT ON TYPE public.raos_migration_history IS 'drift comment'",
            "COMMENT ON TYPE public.raos_migration_history IS NULL",
        ),
    )

    for mutation, cleanup in comment_cases:
        with postgresql_cluster.connect(empty_database) as connection:
            connection.execute(
                sql.SQL("SET ROLE {}").format(
                    sql.Identifier(postgresql_cluster.migration_user)
                )
            )
            connection.execute(mutation)
        with pytest.raises(MigrationError) as raised:
            instance.status()
        assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID
        with postgresql_cluster.connect(empty_database) as connection:
            connection.execute(
                sql.SQL("SET ROLE {}").format(
                    sql.Identifier(postgresql_cluster.migration_user)
                )
            )
            connection.execute(cleanup)
        assert instance.status().current_revision == IAM_OPS_REVISION


def test_empty_head_downgrades_to_physical_predecessor_and_reupgrades(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    assert instance.upgrade().current_revision == IAM_OPS_REVISION

    downgraded = instance.downgrade()
    assert downgraded.changed is True
    assert downgraded.current_revision == FOUNDATION_REVISION
    assert instance.status().current_revision == FOUNDATION_REVISION
    with postgresql_cluster.connect(empty_database) as connection:
        assert _owned_tables(connection) == []
        assert connection.execute(
            """
            SELECT nspname
            FROM pg_catalog.pg_namespace
            WHERE nspname IN ('iam', 'ops')
            ORDER BY nspname
            """
        ).fetchall() == [("iam",), ("ops",)]

    reupgraded = instance.upgrade()
    assert reupgraded.changed is True
    assert reupgraded.current_revision == IAM_OPS_REVISION
    assert instance.status().current_revision == IAM_OPS_REVISION
    with postgresql_cluster.connect(empty_database) as connection:
        history = connection.execute(
            """
            SELECT direction, status, runner_version
            FROM public.raos_migration_history
            WHERE revision_id = %s
            ORDER BY event_id
            """,
            (IAM_OPS_REVISION,),
        ).fetchall()
        assert history == [
            ("UPGRADE", "STARTED", "1.2.0"),
            ("UPGRADE", "SUCCEEDED", "1.2.0"),
            ("DOWNGRADE", "STARTED", "1.2.0"),
            ("DOWNGRADE", "SUCCEEDED", "1.2.0"),
            ("UPGRADE", "STARTED", "1.2.0"),
            ("UPGRADE", "SUCCEEDED", "1.2.0"),
        ]


def test_nonempty_downgrade_fails_atomically_before_any_table_drop(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            """
            INSERT INTO ops.job (
                display_id, job_type, queue_name, created_by_actor_type
            ) VALUES ('JOB-DOWNGRADE-BLOCK', 'TEST', 'test', 'SYSTEM')
            """
        )
        before = _owned_tables(connection)
        assert len(before) == 17

    with pytest.raises(MigrationError) as raised:
        instance.downgrade()
    assert raised.value.code is runner.MigrationErrorCode.MIGRATION_FAILED

    with postgresql_cluster.connect(empty_database) as connection:
        assert _owned_tables(connection) == before
        assert connection.execute(
            "SELECT version_num FROM public.raos_migration_version"
        ).fetchone() == (IAM_OPS_REVISION,)
        assert connection.execute("SELECT count(*) FROM ops.job").fetchone() == (1,)
        connection.execute("DELETE FROM ops.job")

    assert instance.downgrade().current_revision == FOUNDATION_REVISION


def test_installed_catalog_is_exact_for_tables_columns_defaults_and_comments(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    iam_ops_contract: dict[str, object],
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    expected_columns = []
    for table in iam_ops_contract["tables"]:  # type: ignore[index]
        schema, table_name = table["fully_qualified_name"].split(".")
        for position, column in enumerate(table["columns"], start=1):
            expected_columns.append(
                (
                    schema,
                    table_name,
                    position,
                    column["name"],
                    generator.CATALOG_TYPES[column["type"]],
                    not column["nullable"],
                    generator._catalog_default(column),
                    column["description"],
                )
            )

    with postgresql_cluster.connect(empty_database) as connection:
        tables = connection.execute(
            """
            SELECT n.nspname, c.relname, pg_catalog.pg_get_userbyid(c.relowner),
                   pg_catalog.obj_description(c.oid, 'pg_class')
            FROM pg_catalog.pg_class AS c
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname IN ('iam', 'ops') AND c.relkind = 'r'
            ORDER BY n.nspname, c.relname
            """
        ).fetchall()
        assert [(row[0], row[1]) for row in tables] == sorted(
            tuple(table["fully_qualified_name"].split("."))
            for table in iam_ops_contract["tables"]  # type: ignore[index]
        )
        expected_comments = {
            tuple(table["fully_qualified_name"].split(".")): table["purpose"]
            for table in iam_ops_contract["tables"]  # type: ignore[index]
        }
        assert all(row[2] == postgresql_cluster.migration_user for row in tables)
        assert {(row[0], row[1]): row[3] for row in tables} == expected_comments

        columns = connection.execute(
            """
            SELECT n.nspname, c.relname, a.attnum, a.attname,
                   pg_catalog.format_type(a.atttypid, a.atttypmod),
                   a.attnotnull,
                   COALESCE(
                       pg_catalog.pg_get_expr(d.adbin, d.adrelid, false), ''
                   ),
                   pg_catalog.col_description(c.oid, a.attnum)
            FROM pg_catalog.pg_attribute AS a
            JOIN pg_catalog.pg_class AS c ON c.oid = a.attrelid
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            LEFT JOIN pg_catalog.pg_attrdef AS d
              ON d.adrelid = c.oid AND d.adnum = a.attnum
            WHERE n.nspname IN ('iam', 'ops')
              AND c.relkind = 'r'
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY n.nspname, c.relname, a.attnum
            """
        ).fetchall()
        assert columns == sorted(expected_columns)


def test_exact_constraint_index_function_trigger_and_deferred_fk_inventory(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    iam_ops_contract: dict[str, object],
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()
    expected = iam_ops_contract["expected_inventory"]  # type: ignore[index]

    with postgresql_cluster.connect(empty_database) as connection:
        inventory = connection.execute(
            """
            SELECT
                (SELECT count(*)
                 FROM pg_catalog.pg_class AS c
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname IN ('iam', 'ops') AND c.relkind = 'r'),
                (SELECT count(*)
                 FROM pg_catalog.pg_attribute AS a
                 JOIN pg_catalog.pg_class AS c ON c.oid = a.attrelid
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname IN ('iam', 'ops') AND c.relkind = 'r'
                   AND a.attnum > 0 AND NOT a.attisdropped),
                (SELECT count(*)
                 FROM pg_catalog.pg_constraint AS k
                 JOIN pg_catalog.pg_class AS c ON c.oid = k.conrelid
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname IN ('iam', 'ops') AND k.contype = 'p'),
                (SELECT count(*)
                 FROM pg_catalog.pg_constraint AS k
                 JOIN pg_catalog.pg_class AS c ON c.oid = k.conrelid
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname IN ('iam', 'ops') AND k.contype = 'u'),
                (SELECT count(*)
                 FROM pg_catalog.pg_constraint AS k
                 JOIN pg_catalog.pg_class AS c ON c.oid = k.conrelid
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname IN ('iam', 'ops') AND k.contype = 'c'),
                (SELECT count(*)
                 FROM pg_catalog.pg_index AS i
                 JOIN pg_catalog.pg_class AS c ON c.oid = i.indrelid
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname IN ('iam', 'ops')
                   AND NOT EXISTS (
                       SELECT 1 FROM pg_catalog.pg_constraint AS k
                       WHERE k.conindid = i.indexrelid
                   )),
                (SELECT count(*)
                 FROM pg_catalog.pg_constraint AS k
                 JOIN pg_catalog.pg_class AS c ON c.oid = k.conrelid
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname IN ('iam', 'ops') AND k.contype = 'f'),
                (SELECT count(*)
                 FROM pg_catalog.pg_proc AS p
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'ops'
                   AND p.proname IN (
                       'touch_mutable_row', 'reject_immutable_mutation'
                   )),
                (SELECT count(*)
                 FROM pg_catalog.pg_trigger AS t
                 JOIN pg_catalog.pg_class AS c ON c.oid = t.tgrelid
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname IN ('iam', 'ops') AND NOT t.tgisinternal)
            """
        ).fetchone()
        assert inventory == (
            expected["tables"],
            expected["columns"],
            expected["primary_keys"],
            expected["named_unique_constraints"],
            expected["check_constraints"],
            expected["standalone_indexes"],
            expected["immediate_foreign_keys"],
            expected["functions"],
            expected["triggers"],
        )
        assert connection.execute(
            """
            SELECT pg_catalog.to_regclass('portfolio.site'),
                   pg_catalog.to_regclass('ops.incident'),
                   EXISTS (
                       SELECT 1 FROM pg_catalog.pg_constraint
                       WHERE conname IN (
                           'fk_ops_job_site_id',
                           'fk_iam_break_glass_record_incident_id'
                       )
                   ),
                   pg_catalog.to_regclass('ops.job') IS NOT NULL,
                   pg_catalog.to_regclass('iam.break_glass_record') IS NOT NULL,
                   pg_catalog.to_regclass('ops.ix_ops_job_site_id') IS NOT NULL,
                   pg_catalog.to_regclass(
                       'iam.ix_iam_break_glass_record_incident_id'
                   ) IS NOT NULL
            """
        ).fetchone() == (None, None, False, True, True, True, True)


def test_owner_acl_default_acl_search_path_and_out_of_scope_boundary(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    iam_ops_contract: dict[str, object],
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    engine = runner._default_engine_factory(postgresql_cluster.target(empty_database))
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SHOW search_path").scalar_one() == (
                "pg_catalog"
            )
            assert connection.exec_driver_sql("SHOW TimeZone").scalar_one() == "UTC"
    finally:
        engine.dispose()

    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_class AS c
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            CROSS JOIN LATERAL pg_catalog.aclexplode(
                COALESCE(c.relacl, pg_catalog.acldefault('r', c.relowner))
            ) AS acl
            WHERE n.nspname IN ('iam', 'ops')
              AND c.relkind IN ('r', 'i')
              AND acl.grantee <> c.relowner
            """
        ).fetchone() == (0,)
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_proc AS p
            JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
            CROSS JOIN LATERAL pg_catalog.aclexplode(
                COALESCE(p.proacl, pg_catalog.acldefault('f', p.proowner))
            ) AS acl
            WHERE n.nspname = 'ops'
              AND p.proname IN (
                  'touch_mutable_row', 'reject_immutable_mutation'
              )
              AND acl.grantee <> p.proowner
            """
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM pg_catalog.pg_default_acl"
        ).fetchone() == (0,)
        assert connection.execute(
            """
            SELECT rolname
            FROM pg_catalog.pg_roles
            WHERE rolname !~ '^pg_'
            ORDER BY rolname
            """
        ).fetchall() == [
            (postgresql_cluster.user,),
            (postgresql_cluster.migration_user,),
        ]
        assert connection.execute(
            "SELECT extname FROM pg_catalog.pg_extension ORDER BY extname"
        ).fetchall() == [("plpgsql",)]

        out_of_scope = iam_ops_contract["out_of_scope"]  # type: ignore[index]
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_class AS c
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname IN ('iam', 'ops')
              AND c.relkind = 'r'
              AND c.relname = ANY (%s)
            """,
            (out_of_scope,),
        ).fetchone() == (0,)


def test_job_constraint_and_index_identity_is_exact(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    iam_ops_tables: dict[str, dict[str, object]],
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()
    job = iam_ops_tables["ops.job"]
    expected_constraints = {
        job["primary_key_name"],
        *(item["name"] for item in job["unique_constraints"]),
        *(item["name"] for item in job["check_constraints"]),
        *(item["name"] for item in job["foreign_keys"]),
    }
    expected_job_not_null = {
        (f"job_{column['name']}_not_null", f"NOT NULL {column['name']}")
        for column in job["columns"]
        if column["nullable"] is False
    }
    expected_not_null_inventory = {
        (
            fully_qualified_name.split(".", 1)[0],
            fully_qualified_name.split(".", 1)[1],
            f"{fully_qualified_name.split('.', 1)[1]}_{column['name']}_not_null",
            f"NOT NULL {column['name']}",
        )
        for fully_qualified_name, table in iam_ops_tables.items()
        for column in table["columns"]
        if column["nullable"] is False
    }
    expected_indexes = {item["name"] for item in job["indexes"]}

    with postgresql_cluster.connect(empty_database) as connection:
        assert {
            row[0]
            for row in connection.execute(
                """
                SELECT conname
                FROM pg_catalog.pg_constraint
                WHERE conrelid = 'ops.job'::pg_catalog.regclass
                  AND contype IN ('p', 'u', 'c', 'f')
                """
            ).fetchall()
        } == expected_constraints
        assert {
            tuple(row)
            for row in connection.execute(
                """
                SELECT conname,
                       pg_catalog.pg_get_constraintdef(oid, false)
                FROM pg_catalog.pg_constraint
                WHERE conrelid = 'ops.job'::pg_catalog.regclass
                  AND contype = 'n'
                """
            ).fetchall()
        } == expected_job_not_null
        assert len(expected_job_not_null) == 16
        assert {
            tuple(row)
            for row in connection.execute(
                """
                SELECT n.nspname, c.relname, k.conname,
                       pg_catalog.pg_get_constraintdef(k.oid, false)
                FROM pg_catalog.pg_constraint AS k
                JOIN pg_catalog.pg_class AS c ON c.oid = k.conrelid
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname IN ('iam', 'ops')
                  AND c.relkind = 'r'
                  AND k.contype = 'n'
                """
            ).fetchall()
        } == expected_not_null_inventory
        assert len(expected_not_null_inventory) == 151
        assert {
            row[0]
            for row in connection.execute(
                """
                SELECT c.relname
                FROM pg_catalog.pg_index AS i
                JOIN pg_catalog.pg_class AS c ON c.oid = i.indexrelid
                WHERE i.indrelid = 'ops.job'::pg_catalog.regclass
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_catalog.pg_constraint AS k
                      WHERE k.conindid = i.indexrelid
                  )
                """
            ).fetchall()
        } == expected_indexes
        assert len(job["check_constraints"]) == 11
        assert len(job["indexes"]) == 9


def _validation_sql() -> str:
    return (
        REPOSITORY_ROOT / "changes/st-0303/generated/iam-ops-validation.v1.sql"
    ).read_text(encoding="utf-8")


def _assert_validation_rejects(
    connection: psycopg.Connection[object], marker: str
) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SET TIME ZONE 'UTC'")
        cursor.execute("SET search_path = pg_catalog")
        with pytest.raises(psycopg.errors.RaiseException) as raised:
            cursor.execute(_validation_sql())
        assert marker in str(raised.value)


@pytest.mark.parametrize("statement", _TYPE_PROPERTY_DRIFT_STATEMENTS)
def test_validation_rejects_type_property_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statement: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(statement)
        _assert_validation_rejects(connection, "ST0303_UNEXPECTED_OBJECT")


def test_constraint_backing_index_rename_is_rejected_by_validation_and_status(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute("ALTER INDEX ops.pk_ops_job RENAME TO pk_ops_job_drift")
        _assert_validation_rejects(connection, "ST0303_CONSTRAINT_CATALOG_MISMATCH")

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


def test_internal_ri_trigger_comment_is_rejected_by_validation_and_status(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        trigger = connection.execute(
            """
            SELECT namespace.nspname, relation.relname,
                   trigger_record.tgname
            FROM pg_catalog.pg_trigger AS trigger_record
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = trigger_record.tgrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname IN ('iam', 'ops')
              AND trigger_record.tgisinternal IS TRUE
              AND trigger_record.tgconstraint <> 0
            ORDER BY namespace.nspname, relation.relname,
                     trigger_record.tgname
            LIMIT 1
            """
        ).fetchone()
        assert trigger is not None
        trigger_schema, trigger_table, trigger_name = trigger
        connection.execute(
            sql.SQL("COMMENT ON TRIGGER {} ON {}.{} IS 'drift comment'").format(
                sql.Identifier(trigger_name),
                sql.Identifier(trigger_schema),
                sql.Identifier(trigger_table),
            )
        )
        _assert_validation_rejects(connection, "ST0303_UNEXPECTED_OBJECT")

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


def test_public_default_acl_is_rejected_by_validation_and_status(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(_PUBLIC_DEFAULT_ACL_DRIFT_STATEMENT)
        _assert_validation_rejects(connection, "ST0303_DEFAULT_ACL_PRESENT")

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


def test_dropped_column_tombstone_is_rejected_by_validation_and_status(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(
            "ALTER TABLE ops.job ADD COLUMN st0303_dropped_column integer"
        )
        connection.execute("ALTER TABLE ops.job DROP COLUMN st0303_dropped_column")
        _assert_validation_rejects(connection, "ST0303_COLUMN_CATALOG_MISMATCH")

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


@pytest.mark.parametrize("statement", _SCHEMA_VALIDATION_DRIFT_STATEMENTS)
def test_validation_rejects_predecessor_schema_metadata_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statement: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(statement)
        _assert_validation_rejects(connection, "ST0303_SCHEMA_OWNER_OR_ACL_MISMATCH")


def test_public_identity_sequence_static_shape_drift_is_rejected_cross_path(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(
            "ALTER SEQUENCE public.raos_migration_history_event_id_seq INCREMENT BY 2"
        )
        _assert_validation_rejects(
            connection, "ST0303_PUBLIC_SEQUENCE_CATALOG_MISMATCH"
        )

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


def test_replica_identity_drift_is_rejected_cross_path(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute("ALTER TABLE ops.job REPLICA IDENTITY FULL")
        _assert_validation_rejects(connection, "ST0303_TABLE_CATALOG_MISMATCH")

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


@pytest.mark.parametrize("statement", _UNLISTED_OBJECT_STATEMENTS)
def test_validation_rejects_unlisted_schema_object_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statement: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(statement)
        _assert_validation_rejects(connection, "ST0303_UNEXPECTED_OBJECT")


def test_validation_rejects_constraint_backing_index_comment_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute("COMMENT ON INDEX ops.pk_ops_job IS 'drift comment'")
        _assert_validation_rejects(connection, "ST0303_CONSTRAINT_CATALOG_MISMATCH")


def test_validation_rejects_same_named_check_with_modified_expression(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute("ALTER TABLE ops.job DROP CONSTRAINT ck_ops_job_priority")
        connection.execute(
            """
            ALTER TABLE ops.job
            ADD CONSTRAINT ck_ops_job_priority
            CHECK (priority BETWEEN 0 AND 101)
            """
        )
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_constraint AS k
            JOIN pg_catalog.pg_class AS c ON c.oid = k.conrelid
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname IN ('iam', 'ops') AND k.contype = 'c'
            """
        ).fetchone() == (66,)
        _assert_validation_rejects(connection, "ST0303_CONSTRAINT_CATALOG_MISMATCH")


def test_validation_rejects_same_named_partial_index_with_modified_predicate(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute("DROP INDEX ops.ix_ops_job_ready")
        connection.execute(
            """
            CREATE INDEX ix_ops_job_ready
            ON ops.job USING btree (queue_name, priority, available_at)
            WHERE status IN ('REQUESTED', 'QUEUED')
            """
        )
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_index AS i
            JOIN pg_catalog.pg_class AS c ON c.oid = i.indrelid
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname IN ('iam', 'ops')
              AND NOT EXISTS (
                  SELECT 1 FROM pg_catalog.pg_constraint AS k
                  WHERE k.conindid = i.indexrelid
              )
            """
        ).fetchone() == (48,)
        _assert_validation_rejects(connection, "ST0303_INDEX_CATALOG_MISMATCH")


@pytest.mark.parametrize(
    "reference_actions",
    (
        "MATCH SIMPLE ON UPDATE CASCADE ON DELETE RESTRICT",
        "MATCH FULL ON UPDATE NO ACTION ON DELETE RESTRICT",
    ),
)
def test_validation_rejects_same_named_fk_with_modified_update_or_match_action(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    reference_actions: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(
            """
            ALTER TABLE ops.job
            DROP CONSTRAINT fk_ops_job_payload_artifact_id
            """
        )
        connection.execute(
            """
            ALTER TABLE ops.job
            ADD CONSTRAINT fk_ops_job_payload_artifact_id
            FOREIGN KEY (payload_artifact_id)
            REFERENCES ops.object_artifact (id)
            """
            + reference_actions
            + " NOT DEFERRABLE"
        )
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_constraint AS k
            JOIN pg_catalog.pg_class AS c ON c.oid = k.conrelid
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname IN ('iam', 'ops') AND k.contype = 'f'
            """
        ).fetchone() == (20,)
        _assert_validation_rejects(connection, "ST0303_CONSTRAINT_CATALOG_MISMATCH")


def test_validation_rejects_same_named_trigger_with_update_of_semantic_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute("DROP TRIGGER trg_ops_job_touch ON ops.job")
        connection.execute(
            """
            CREATE TRIGGER trg_ops_job_touch
            BEFORE UPDATE OF status ON ops.job
            FOR EACH ROW
            EXECUTE FUNCTION ops.touch_mutable_row()
            """
        )
        connection.execute(
            """
            COMMENT ON TRIGGER trg_ops_job_touch ON ops.job IS
            'Maintain ops.job updated_at and lock_version for changed rows.'
            """
        )
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_trigger AS t
            JOIN pg_catalog.pg_class AS c ON c.oid = t.tgrelid
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname IN ('iam', 'ops') AND NOT t.tgisinternal
            """
        ).fetchone() == (4,)
        assert connection.execute(
            """
            SELECT a.attname
            FROM pg_catalog.pg_trigger AS t
            CROSS JOIN LATERAL pg_catalog.unnest(t.tgattr)
                 AS trigger_column(attribute_number)
            JOIN pg_catalog.pg_attribute AS a
              ON a.attrelid = t.tgrelid
             AND a.attnum = trigger_column.attribute_number
            WHERE t.tgrelid = 'ops.job'::pg_catalog.regclass
              AND t.tgname = 'trg_ops_job_touch'
            """
        ).fetchall() == [("status",)]
        _assert_validation_rejects(connection, "ST0303_TRIGGER_CATALOG_MISMATCH")
