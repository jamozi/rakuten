"""Exact PostgreSQL 18.4 ST-0302 foundation runtime acceptance tests."""

from __future__ import annotations

import psycopg
import pytest
from psycopg import sql

from conftest import REPOSITORY_ROOT
from raos.migrations import MigrationError
from raos.migrations import catalog
from raos.migrations import runner
from tests.postgresql18 import PostgreSQLCluster


_CUMULATIVE_REVISION_SPECS = catalog.REVISION_SPECS
_CUMULATIVE_HEAD_REVISION = catalog.HEAD_REVISION


@pytest.fixture(autouse=True)
def _use_historical_foundation_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise ST-0302 against its frozen two-revision graph snapshot."""

    historical_specs = _CUMULATIVE_REVISION_SPECS[:2]
    assert _CUMULATIVE_HEAD_REVISION == _CUMULATIVE_REVISION_SPECS[-1].revision
    assert historical_specs[-1].revision == catalog.FOUNDATION_REVISION
    monkeypatch.setattr(catalog, "REVISION_SPECS", historical_specs)
    monkeypatch.setattr(catalog, "HEAD_REVISION", catalog.FOUNDATION_REVISION)
    monkeypatch.setattr(runner, "REVISION_SPECS", historical_specs)
    monkeypatch.setattr(runner, "HEAD_REVISION", catalog.FOUNDATION_REVISION)


def _migration_runner(
    cluster: PostgreSQLCluster, database: str
) -> runner.MigrationRunner:
    return runner.MigrationRunner(REPOSITORY_ROOT, cluster.target(database))


def test_empty_database_reaches_exact_foundation_and_validation_sql_passes(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)

    assert instance.status().current_revision == "base"
    assert instance.upgrade().current_revision == catalog.FOUNDATION_REVISION
    assert instance.upgrade().changed is False
    assert instance.status().current_revision == catalog.FOUNDATION_REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        schemas = connection.execute(
            """
            SELECT n.nspname,
                   pg_catalog.pg_get_userbyid(n.nspowner),
                   pg_catalog.obj_description(n.oid, 'pg_namespace'),
                   (
                       SELECT COALESCE(
                           array_agg(
                               acl.privilege_type
                               ORDER BY acl.privilege_type
                           ),
                           ARRAY[]::text[]
                       )
                       FROM pg_catalog.aclexplode(
                           COALESCE(
                               n.nspacl,
                               pg_catalog.acldefault('n', n.nspowner)
                           )
                       ) AS acl
                       WHERE acl.grantee = n.nspowner
                   ),
                   (
                       SELECT count(*)
                       FROM pg_catalog.aclexplode(
                           COALESCE(
                               n.nspacl,
                               pg_catalog.acldefault('n', n.nspowner)
                           )
                       ) AS acl
                           WHERE acl.grantee <> n.nspowner
                   )
            FROM pg_catalog.pg_namespace AS n
            WHERE n.nspname IN ('iam', 'ops')
            ORDER BY n.nspname
            """
        ).fetchall()
        assert schemas == [
            (
                "iam",
                postgresql_cluster.migration_user,
                "OIDC主体、アプリケーションRole、権限、緊急アクセス",
                ["CREATE", "USAGE"],
                0,
            ),
            (
                "ops",
                postgresql_cluster.migration_user,
                "ジョブ、原本レジストリ、監査、障害、Kill Switch、実行時設定",
                ["CREATE", "USAGE"],
                0,
            ),
        ]
        assert connection.execute(
            """
            SELECT
                (SELECT count(*)
                 FROM pg_catalog.pg_class AS c
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname IN ('iam', 'ops'))
                +
                (SELECT count(*)
                 FROM pg_catalog.pg_proc AS p
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                 WHERE n.nspname IN ('iam', 'ops'))
                +
                (SELECT count(*)
                 FROM pg_catalog.pg_type AS t
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = t.typnamespace
                 WHERE n.nspname IN ('iam', 'ops'))
            """
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT extname FROM pg_catalog.pg_extension ORDER BY extname"
        ).fetchall() == [("plpgsql",)]
        assert connection.execute(
            """
            WITH sample AS (SELECT pg_catalog.uuidv7() AS value)
            SELECT pg_catalog.pg_typeof(value)::text,
                   pg_catalog.uuid_extract_version(value),
                   pg_catalog.uuid_extract_timestamp(value) IS NOT NULL,
                   pg_catalog.to_regprocedure('pg_catalog.uuidv7()') IS NOT NULL,
                   pg_catalog.to_regprocedure(
                       'pg_catalog.uuidv7(interval)'
                   ) IS NOT NULL
            FROM sample
            """
        ).fetchone() == ("uuid", 7, True, True, True)
        history = connection.execute(
            """
            SELECT revision_id, direction, status
            FROM public.raos_migration_history
            ORDER BY event_id
            """
        ).fetchall()
        assert history == [
            (catalog.ANCHOR_REVISION, "UPGRADE", "SUCCEEDED"),
            (catalog.FOUNDATION_REVISION, "UPGRADE", "STARTED"),
            (catalog.FOUNDATION_REVISION, "UPGRADE", "SUCCEEDED"),
        ]

        validation = (
            REPOSITORY_ROOT
            / "changes/st-0302/generated/foundation-baseline-validation.v1.sql"
        ).read_text(encoding="utf-8")
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")
            cursor.execute(
                sql.SQL("SET ROLE {}").format(
                    sql.Identifier(postgresql_cluster.migration_user)
                )
            )
            cursor.execute(validation)
            assert cursor.nextset() is True
            assert cursor.fetchall() == [("PASS", 180004, 2, 0, 7)]
            assert cursor.nextset() is None


@pytest.mark.parametrize(
    ("default_privilege_clause", "object_type"),
    (
        ("GRANT SELECT ON TABLES TO PUBLIC", "r"),
        ("GRANT USAGE ON SEQUENCES TO PUBLIC", "S"),
        ("REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC", "f"),
        ("REVOKE USAGE ON TYPES FROM PUBLIC", "T"),
        ("GRANT USAGE ON SCHEMAS TO PUBLIC", "n"),
        ("GRANT SELECT ON LARGE OBJECTS TO PUBLIC", "L"),
    ),
)
def test_base_database_global_default_acl_is_unmanaged_for_every_object_class(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    default_privilege_clause: str,
    object_type: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} ").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
            + sql.SQL(default_privilege_clause)
        )
        assert connection.execute(
            """
            SELECT defaults.defaclnamespace, defaults.defaclobjtype
            FROM pg_catalog.pg_default_acl AS defaults
            """
        ).fetchall() == [(0, object_type)]

    for operation in (instance.status, instance.upgrade):
        with pytest.raises(MigrationError) as raised:
            operation()
        assert raised.value.code is runner.MigrationErrorCode.UNMANAGED_DATABASE

    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            """
            SELECT pg_catalog.to_regclass('public.raos_migration_version'),
                   pg_catalog.to_regclass('public.raos_migration_history'),
                   EXISTS (
                       SELECT 1
                       FROM pg_catalog.pg_namespace
                       WHERE nspname IN ('ops', 'iam')
                   )
            """
        ).fetchone() == (None, None, False)


def test_non_utc_database_and_role_defaults_are_normalized_by_runner(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    validation = (
        REPOSITORY_ROOT
        / "changes/st-0302/generated/foundation-baseline-validation.v1.sql"
    ).read_text(encoding="utf-8")

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("ALTER DATABASE {} SET TimeZone TO 'Asia/Tokyo'").format(
                sql.Identifier(empty_database)
            )
        )
        connection.execute(
            sql.SQL("ALTER ROLE {} IN DATABASE {} SET TimeZone TO 'Asia/Tokyo'").format(
                sql.Identifier(postgresql_cluster.migration_user),
                sql.Identifier(empty_database),
            )
        )

    engine = runner._default_engine_factory(postgresql_cluster.target(empty_database))
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SHOW TimeZone").scalar_one() == "UTC"
    finally:
        engine.dispose()
    assert instance.status().current_revision == catalog.FOUNDATION_REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute("SHOW TimeZone").fetchone() == ("Asia/Tokyo",)
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SET ROLE {}").format(
                    sql.Identifier(postgresql_cluster.migration_user)
                )
            )
            with pytest.raises(psycopg.errors.RaiseException) as raised:
                cursor.execute(validation)
            assert "ST0302_TIMEZONE_MISMATCH" in str(raised.value)


def test_official_one_step_downgrade_and_reupgrade_preserve_atomic_history(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    assert instance.upgrade().current_revision == catalog.FOUNDATION_REVISION

    result = instance.downgrade()
    assert result.command == "downgrade"
    assert result.changed is True
    assert result.current_revision == catalog.ANCHOR_REVISION
    assert instance.status().current_revision == catalog.ANCHOR_REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        assert (
            connection.execute(
                """
            SELECT nspname
            FROM pg_catalog.pg_namespace
            WHERE nspname IN ('iam', 'ops')
            ORDER BY nspname
            """
            ).fetchall()
            == []
        )
        rows = connection.execute(
            """
            SELECT revision_id, direction, status, transaction_id, xmin::text
            FROM public.raos_migration_history
            ORDER BY event_id
            """
        ).fetchall()
        assert [(row[0], row[1], row[2]) for row in rows] == [
            (catalog.ANCHOR_REVISION, "UPGRADE", "SUCCEEDED"),
            (catalog.FOUNDATION_REVISION, "UPGRADE", "STARTED"),
            (catalog.FOUNDATION_REVISION, "UPGRADE", "SUCCEEDED"),
            (catalog.FOUNDATION_REVISION, "DOWNGRADE", "STARTED"),
            (catalog.FOUNDATION_REVISION, "DOWNGRADE", "SUCCEEDED"),
        ]
        version = connection.execute(
            "SELECT version_num, xmin::text FROM public.raos_migration_version"
        ).fetchone()
        assert version == (catalog.ANCHOR_REVISION, rows[-1][4])
        assert rows[-1][3] == rows[-1][4]
        assert rows[-2][3] != rows[-1][3]

    with pytest.raises(MigrationError) as raised:
        instance.downgrade()
    assert raised.value.code is runner.MigrationErrorCode.DOWNGRADE_FORBIDDEN

    assert instance.upgrade().current_revision == catalog.FOUNDATION_REVISION
    assert instance.upgrade().changed is False
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            """
            SELECT direction, status
            FROM public.raos_migration_history
            WHERE revision_id = %s
            ORDER BY event_id
            """,
            (catalog.FOUNDATION_REVISION,),
        ).fetchall() == [
            ("UPGRADE", "STARTED"),
            ("UPGRADE", "SUCCEEDED"),
            ("DOWNGRADE", "STARTED"),
            ("DOWNGRADE", "SUCCEEDED"),
            ("UPGRADE", "STARTED"),
            ("UPGRADE", "SUCCEEDED"),
        ]


def test_nonempty_schema_downgrade_fails_atomically_then_recovers(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute("CREATE TABLE ops.st0302_downgrade_probe (id integer)")

    with pytest.raises(MigrationError) as raised:
        instance.downgrade()
    assert raised.value.code is runner.MigrationErrorCode.MIGRATION_FAILED
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.raos_migration_version"
        ).fetchone() == (catalog.FOUNDATION_REVISION,)
        assert connection.execute(
            "SELECT to_regclass('ops.st0302_downgrade_probe')"
        ).fetchone() == ("ops.st0302_downgrade_probe",)
        assert connection.execute(
            """
            SELECT direction, status, error_code
            FROM public.raos_migration_history
            WHERE revision_id = %s
            ORDER BY event_id DESC
            LIMIT 2
            """,
            (catalog.FOUNDATION_REVISION,),
        ).fetchall() == [
            ("DOWNGRADE", "FAILED", "MIGRATION_FAILED"),
            ("DOWNGRADE", "STARTED", None),
        ]
        connection.execute("DROP TABLE ops.st0302_downgrade_probe")

    assert instance.downgrade().current_revision == catalog.ANCHOR_REVISION
    assert instance.upgrade().current_revision == catalog.FOUNDATION_REVISION


def test_upgrade_closes_interrupted_nonempty_downgrade_before_strict_recovery(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute("CREATE TABLE ops.st0302_interrupted_probe (id integer)")

    attempt_id = "00000000-0000-4000-8000-000000000302"
    engine = runner._default_engine_factory(postgresql_cluster.target(empty_database))
    try:
        with engine.connect() as connection:
            runner._append_attempt_event(
                connection,
                attempt_id=attempt_id,
                revision_index=1,
                direction="DOWNGRADE",
                status="STARTED",
                error_code=None,
            )
    finally:
        engine.dispose()

    with pytest.raises(MigrationError) as raised:
        instance.upgrade()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            """
            SELECT attempt_id::text, direction, status, error_code
            FROM public.raos_migration_history
            WHERE attempt_id = %s
            ORDER BY event_id
            """,
            (attempt_id,),
        ).fetchall() == [
            (attempt_id, "DOWNGRADE", "STARTED", None),
            (
                attempt_id,
                "DOWNGRADE",
                "FAILED",
                "INTERRUPTED_BEFORE_TERMINAL",
            ),
        ]
        connection.execute("DROP TABLE ops.st0302_interrupted_probe")

    assert instance.upgrade().changed is False
    assert instance.status().current_revision == catalog.FOUNDATION_REVISION


@pytest.mark.parametrize(
    "statements",
    (
        ("COMMENT ON SCHEMA ops IS 'tampered'",),
        ("GRANT USAGE ON SCHEMA iam TO PUBLIC",),
        ("ALTER SCHEMA ops OWNER TO raos_admin",),
        (
            "CREATE ROLE st0302_unexpected_reader NOLOGIN",
            "GRANT USAGE ON SCHEMA ops TO st0302_unexpected_reader",
        ),
        ("ALTER DEFAULT PRIVILEGES IN SCHEMA ops GRANT SELECT ON TABLES TO PUBLIC",),
    ),
)
def test_schema_metadata_tampering_fails_closed(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statements: tuple[str, ...],
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        for statement in statements:
            connection.execute(statement)

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


def test_owner_role_global_default_acl_fails_runner_and_validation(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    validation = (
        REPOSITORY_ROOT
        / "changes/st-0302/generated/foundation-baseline-validation.v1.sql"
    ).read_text(encoding="utf-8")

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} GRANT SELECT ON TABLES TO PUBLIC"
            ).format(sql.Identifier(postgresql_cluster.migration_user))
        )
        assert connection.execute(
            """
            SELECT defaults.defaclnamespace,
                   defaults.defaclobjtype,
                   pg_catalog.pg_get_userbyid(defaults.defaclrole)
            FROM pg_catalog.pg_default_acl AS defaults
            WHERE defaults.defaclrole = (
                SELECT role.oid
                FROM pg_catalog.pg_roles AS role
                WHERE role.rolname = %s
            )
            """,
            (postgresql_cluster.migration_user,),
        ).fetchall() == [(0, "r", postgresql_cluster.migration_user)]

        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SET ROLE {}").format(
                    sql.Identifier(postgresql_cluster.migration_user)
                )
            )
            cursor.execute(
                "CREATE TABLE ops.st0302_global_default_acl_probe (id integer)"
            )
            cursor.execute("RESET ROLE")
        assert connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_catalog.pg_class AS relation
                CROSS JOIN LATERAL pg_catalog.aclexplode(relation.relacl) AS acl
                WHERE relation.oid =
                      'ops.st0302_global_default_acl_probe'::regclass
                  AND acl.grantee = 0
                  AND acl.privilege_type = 'SELECT'
            )
            """
        ).fetchone() == (True,)
        connection.execute("DROP TABLE ops.st0302_global_default_acl_probe")

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID

    with postgresql_cluster.connect(empty_database) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")
            cursor.execute(
                sql.SQL("SET ROLE {}").format(
                    sql.Identifier(postgresql_cluster.migration_user)
                )
            )
            with pytest.raises(psycopg.errors.RaiseException) as sql_error:
                cursor.execute(validation)
            assert "ST0302_FOUNDATION_DEFAULT_PRIVILEGE" in str(sql_error.value)


def test_missing_owner_schema_privilege_fails_runner_and_validation(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    validation = (
        REPOSITORY_ROOT
        / "changes/st-0302/generated/foundation-baseline-validation.v1.sql"
    ).read_text(encoding="utf-8")
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("REVOKE CREATE ON SCHEMA ops FROM {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID

    with postgresql_cluster.connect(empty_database) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")
            cursor.execute(
                sql.SQL("SET ROLE {}").format(
                    sql.Identifier(postgresql_cluster.migration_user)
                )
            )
            with pytest.raises(psycopg.errors.RaiseException) as sql_error:
                cursor.execute(validation)
            assert "ST0302_SCHEMA_PRIVILEGE_MISMATCH" in str(sql_error.value)


@pytest.mark.parametrize(
    "statement",
    (
        'CREATE COLLATION ops.st0302_unexpected_collation FROM "C"',
        (
            "CREATE TEXT SEARCH CONFIGURATION iam.st0302_unexpected_search "
            "(COPY = pg_catalog.simple)"
        ),
    ),
)
def test_non_relation_schema_objects_fail_empty_foundation_attestation(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statement: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(statement)

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID


@pytest.mark.parametrize(
    ("statement", "error_marker"),
    (
        (
            "COMMENT ON SCHEMA iam IS 'tampered'",
            "ST0302_SCHEMA_METADATA_MISMATCH",
        ),
        (
            'CREATE COLLATION ops.st0302_validation_collation FROM "C"',
            "ST0302_FOUNDATION_NOT_EMPTY",
        ),
        (
            "ALTER DEFAULT PRIVILEGES IN SCHEMA iam GRANT SELECT ON TABLES TO PUBLIC",
            "ST0302_FOUNDATION_DEFAULT_PRIVILEGE",
        ),
    ),
)
def test_validation_sql_raises_on_schema_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    statement: str,
    error_marker: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    validation = (
        REPOSITORY_ROOT
        / "changes/st-0302/generated/foundation-baseline-validation.v1.sql"
    ).read_text(encoding="utf-8")
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(statement)
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")
            cursor.execute(
                sql.SQL("SET ROLE {}").format(
                    sql.Identifier(postgresql_cluster.migration_user)
                )
            )
            with pytest.raises(psycopg.errors.RaiseException) as raised:
                cursor.execute(validation)
            assert error_marker in str(raised.value)


@pytest.mark.parametrize("tamper", ("EXTRA_VERSION", "EXTRA_HISTORY"))
def test_validation_sql_requires_one_exact_clean_history_sequence(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    tamper: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    validation = (
        REPOSITORY_ROOT
        / "changes/st-0302/generated/foundation-baseline-validation.v1.sql"
    ).read_text(encoding="utf-8")
    with postgresql_cluster.connect(empty_database) as connection:
        if tamper == "EXTRA_VERSION":
            connection.execute(
                "INSERT INTO public.raos_migration_version (version_num) "
                "VALUES ('202608039999')"
            )
            marker = "ST0302_MIGRATION_VERSION_MISMATCH"
        else:
            foundation = catalog.REVISION_SPECS[1]
            connection.execute(
                """
                INSERT INTO public.raos_migration_history (
                    attempt_id, revision_id, story_id, direction, status,
                    source_sha256, runner_version, server_version_num,
                    error_code
                ) VALUES (
                    %s, %s, %s, 'UPGRADE', 'STARTED', %s, %s, %s, NULL
                )
                """,
                (
                    "00000000-0000-4000-8000-000000000399",
                    foundation.revision,
                    foundation.story_id,
                    foundation.sha256,
                    foundation.runner_version,
                    foundation.server_version_num,
                ),
            )
            marker = "ST0302_MIGRATION_HISTORY_MISMATCH"
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")
            cursor.execute(
                sql.SQL("SET ROLE {}").format(
                    sql.Identifier(postgresql_cluster.migration_user)
                )
            )
            with pytest.raises(psycopg.errors.RaiseException) as raised:
                cursor.execute(validation)
            assert marker in str(raised.value)
