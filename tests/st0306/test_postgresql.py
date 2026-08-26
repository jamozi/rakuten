"""Exact PostgreSQL 18.4 runtime acceptance for ST-0306."""

from __future__ import annotations

import hashlib

import psycopg
import pytest
from psycopg import sql

from .support import REPOSITORY_ROOT
from raos.migrations import catalog, runner
from scripts import build_st0306_database_roles as generator
from tests.postgresql18 import PostgreSQLCluster


def _runner(cluster: PostgreSQLCluster, database: str) -> runner.MigrationRunner:
    return runner.MigrationRunner(REPOSITORY_ROOT, cluster.target(database))


def _set_role(connection: psycopg.Connection[object], role: str) -> None:
    connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))


def _execute_generated_validation(
    connection: psycopg.Connection[object], owner: str
) -> list[tuple[object, ...]]:
    validation = (REPOSITORY_ROOT / generator.VALIDATION_PATH).read_text(
        encoding="utf-8"
    )
    _set_role(connection, owner)
    try:
        with connection.cursor() as cursor:
            cursor.execute(validation)
            rows: list[tuple[object, ...]] = []
            while True:
                if cursor.description is not None:
                    rows = cursor.fetchall()
                if cursor.nextset() is None:
                    return rows
    finally:
        connection.execute("RESET ROLE")


def _assert_default_function_public_deny(
    connection: psycopg.Connection[object], owner: str
) -> None:
    assert connection.execute(
        """
        SELECT defaults.defaclobjtype::text,
               pg_catalog.pg_get_userbyid(defaults.defaclrole),
               COALESCE(grantee.rolname, 'PUBLIC'), acl.privilege_type,
               acl.is_grantable
        FROM pg_catalog.pg_default_acl AS defaults
        CROSS JOIN LATERAL pg_catalog.aclexplode(defaults.defaclacl) AS acl
        LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = acl.grantee
        WHERE defaults.defaclnamespace = 0
        ORDER BY defaults.defaclobjtype, grantee.rolname NULLS FIRST,
                 acl.privilege_type
        """
    ).fetchall() == [("f", owner, owner, "EXECUTE", False)]


def _assert_future_function_is_not_public(
    connection: psycopg.Connection[object], owner: str
) -> None:
    _set_role(connection, owner)
    connection.execute(
        """
        CREATE FUNCTION ops.st0306_default_acl_probe()
        RETURNS integer
        LANGUAGE sql
        SET search_path = pg_catalog
        AS 'SELECT 1'
        """
    )
    connection.execute("RESET ROLE")
    assert connection.execute(
        """
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_proc AS routine
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(routine.proacl, pg_catalog.acldefault('f', routine.proowner))
        ) AS acl
        WHERE routine.oid = 'ops.st0306_default_acl_probe()'::pg_catalog.regprocedure
          AND acl.grantee = 0
        """
    ).fetchone() == (0,)
    _set_role(connection, owner)
    connection.execute("DROP FUNCTION ops.st0306_default_acl_probe()")
    connection.execute("RESET ROLE")


def _insert_immutable_fact_fixtures(
    connection: psycopg.Connection[object],
) -> None:
    connection.execute("SET session_replication_role = replica")
    connection.execute(
        """
        INSERT INTO publishing.review_decision (
            id, display_id, review_assignment_id, article_version_id,
            decision, summary, decided_by_principal_id, decided_at
        ) VALUES (
            '00000000-0000-0000-0000-000000000101', 'RVD-ST0306-FIXTURE',
            '00000000-0000-0000-0000-000000000102',
            '00000000-0000-0000-0000-000000000103', 'APPROVE',
            'ST0306 immutable approval fixture',
            '00000000-0000-0000-0000-000000000104', pg_catalog.now()
        );
        INSERT INTO finance.commission_event (
            id, commission_id, source_import_row_id, event_sequence,
            event_type, to_status, recorded_at, event_sha256
        ) VALUES (
            '00000000-0000-0000-0000-000000000201',
            '00000000-0000-0000-0000-000000000202',
            '00000000-0000-0000-0000-000000000203', 1, 'GENERATED',
            'GENERATED', pg_catalog.now(), repeat('a', 64)
        );
        INSERT INTO catalog.price_observation (
            id, offer_id, price_jpy, shipping_condition, observed_at,
            ingested_at, source_snapshot_id, validation_status, confidence
        ) VALUES (
            '00000000-0000-0000-0000-000000000301',
            '00000000-0000-0000-0000-000000000302', 1, 'FREE',
            pg_catalog.now(), pg_catalog.now(),
            '00000000-0000-0000-0000-000000000303', 'VALID', 1
        )
        """
    )
    connection.execute("SET session_replication_role = origin")


def test_upgrade_installs_exact_roles_public_boundary_and_policies(
    postgresql_cluster: PostgreSQLCluster, empty_database: str
) -> None:
    instance = _runner(postgresql_cluster, empty_database)
    assert instance.upgrade().current_revision == generator.REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        revision_sha256 = hashlib.sha256(
            (REPOSITORY_ROOT / generator.REVISION_PATH).read_bytes()
        ).hexdigest()
        assert _execute_generated_validation(
            connection, postgresql_cluster.migration_user
        ) == [(generator.REVISION, revision_sha256, 8, 22)]
        roles = connection.execute(
            """
            SELECT rolname, rolcanlogin, rolsuper, rolinherit, rolcreatedb,
                   rolcreaterole, rolreplication, rolbypassrls
            FROM pg_catalog.pg_roles
            WHERE rolname = ANY(%s)
            ORDER BY rolname
            """,
            (list(generator.ROLES),),
        ).fetchall()
        assert roles == [
            (role, False, False, True, False, False, False, False)
            for role in sorted(generator.ROLES)
        ]
        assert connection.execute(
            """
            SELECT granted_role.rolname, member_role.rolname,
                   membership.admin_option, membership.inherit_option,
                   membership.set_option
            FROM pg_catalog.pg_auth_members AS membership
            JOIN pg_catalog.pg_roles AS granted_role
              ON granted_role.oid = membership.roleid
            JOIN pg_catalog.pg_roles AS member_role
              ON member_role.oid = membership.member
            WHERE granted_role.rolname = ANY(%s)
            ORDER BY granted_role.rolname
            """,
            (list(generator.ROLES),),
        ).fetchall() == [
            (role, postgresql_cluster.migration_user, True, False, False)
            for role in sorted(generator.ROLES)
        ]
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_auth_members AS membership
            JOIN pg_catalog.pg_roles AS member_role
              ON member_role.oid = membership.member
            WHERE member_role.rolname = ANY(%s)
            """,
            (list(generator.ROLES),),
        ).fetchone() == (0,)
        assert connection.execute(
            """
            SELECT pg_catalog.pg_get_userbyid(datdba)
            FROM pg_catalog.pg_database
            WHERE datname = pg_catalog.current_database()
            """
        ).fetchone() == (postgresql_cluster.migration_user,)
        assert postgresql_cluster.migration_user not in generator.ROLES
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_policy AS p
            JOIN pg_catalog.pg_class AS c ON c.oid = p.polrelid
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname || '.' || c.relname = ANY(%s)
            """,
            (list(generator.RLS_TABLES),),
        ).fetchone() == (22,)
        _assert_default_function_public_deny(
            connection, postgresql_cluster.migration_user
        )
        assert connection.execute(
            """
            SELECT pg_catalog.count(*)
            FROM pg_catalog.pg_proc AS routine
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = routine.pronamespace
            CROSS JOIN LATERAL pg_catalog.aclexplode(
                COALESCE(
                    routine.proacl,
                    pg_catalog.acldefault('f', routine.proowner)
                )
            ) AS acl
            WHERE namespace.nspname = ANY(%s)
              AND acl.grantee = 0
            """,
            (list(generator.SCHEMAS),),
        ).fetchone() == (0,)

        _set_role(connection, "raos_public_ro")
        assert connection.execute(
            "SELECT count(*) FROM readmodel.public_article"
        ).fetchone() == (0,)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("SELECT count(*) FROM editorial.article")
        connection.execute("ROLLBACK")


def test_default_function_deny_applies_to_future_managed_function(
    postgresql_cluster: PostgreSQLCluster, empty_database: str
) -> None:
    _runner(postgresql_cluster, empty_database).upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        _assert_future_function_is_not_public(
            connection, postgresql_cluster.migration_user
        )


def test_normal_role_cannot_mutate_approval_or_provider_facts(
    postgresql_cluster: PostgreSQLCluster, empty_database: str
) -> None:
    _runner(postgresql_cluster, empty_database).upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        _insert_immutable_fact_fixtures(connection)
        _set_role(connection, "raos_api_rw")
        for statement in (
            "UPDATE publishing.review_decision SET summary = summary",
            "UPDATE finance.commission_event SET event_sequence = event_sequence",
            "UPDATE catalog.price_observation SET price_jpy = price_jpy",
        ):
            with pytest.raises(
                psycopg.errors.ObjectNotInPrerequisiteState,
                match="RAOS immutable table mutation is forbidden",
            ):
                connection.execute(statement)
        for statement in (
            "DELETE FROM publishing.review_decision",
            "DELETE FROM finance.commission_event",
            "DELETE FROM catalog.price_observation",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(statement)


def test_workload_grants_rls_and_immutable_guards_fail_closed(
    postgresql_cluster: PostgreSQLCluster, empty_database: str
) -> None:
    instance = _runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        _set_role(connection, "raos_worker_rw")
        assert connection.execute(
            "SELECT count(*) FROM editorial.content_schema_version"
        ).fetchone() == (0,)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "INSERT INTO editorial.content_schema_version "
                "(id, schema_code, semantic_version, artifact_id, schema_sha256, status, effective_from) "
                "VALUES (pg_catalog.uuidv7(), 'denied', '1', pg_catalog.uuidv7(), repeat('a',64), 'DRAFT', now())"
            )
        connection.execute("ROLLBACK")

        connection.execute(
            """
            INSERT INTO ops.audit_event (
                id, actor_type, action, target_type, outcome, severity,
                correlation_id, occurred_at
            ) VALUES (
                pg_catalog.uuidv7(), 'SYSTEM', 'ST0306_TEST', 'TEST',
                'SUCCESS', 'INFO', pg_catalog.uuidv7(), pg_catalog.now()
            )
            """
        )
        _set_role(connection, "raos_api_rw")
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute("UPDATE ops.audit_event SET action = 'ST0306_MUTATION'")
        connection.execute("ROLLBACK")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            _set_role(connection, "raos_api_rw")
            connection.execute("DELETE FROM ops.audit_event")
        connection.execute("ROLLBACK")


@pytest.mark.parametrize(
    ("drift_statement", "repair_statement"),
    (
        ("ALTER ROLE raos_public_ro LOGIN", "ALTER ROLE raos_public_ro NOLOGIN"),
        (
            "ALTER ROLE raos_public_ro SUPERUSER",
            "ALTER ROLE raos_public_ro NOSUPERUSER",
        ),
        (
            "ALTER ROLE raos_public_ro NOINHERIT",
            "ALTER ROLE raos_public_ro INHERIT",
        ),
        (
            "ALTER ROLE raos_public_ro CREATEDB",
            "ALTER ROLE raos_public_ro NOCREATEDB",
        ),
        (
            "ALTER ROLE raos_public_ro CREATEROLE",
            "ALTER ROLE raos_public_ro NOCREATEROLE",
        ),
        (
            "ALTER ROLE raos_public_ro REPLICATION",
            "ALTER ROLE raos_public_ro NOREPLICATION",
        ),
        (
            "ALTER ROLE raos_public_ro BYPASSRLS",
            "ALTER ROLE raos_public_ro NOBYPASSRLS",
        ),
        (
            "GRANT raos_reporting_ro TO raos_public_ro",
            "REVOKE raos_reporting_ro FROM raos_public_ro",
        ),
    ),
    ids=(
        "login",
        "superuser",
        "inherit",
        "createdb",
        "createrole",
        "replication",
        "bypassrls",
        "outbound-membership",
    ),
)
def test_role_attribute_drift_fails_without_advancing_revision(
    drift_statement: str,
    repair_statement: str,
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _runner(postgresql_cluster, empty_database)
    instance.upgrade()
    assert (
        instance.downgrade().current_revision
        == catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION
    )
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(drift_statement)
    try:
        with pytest.raises(runner.MigrationError) as raised:
            instance.upgrade()
        assert raised.value.code == runner.MigrationErrorCode.MIGRATION_FAILED
        with postgresql_cluster.connect(empty_database) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.raos_migration_version"
            ).fetchone() == (catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION,)
    finally:
        with postgresql_cluster.connect(empty_database) as connection:
            connection.execute(repair_statement)
    assert instance.upgrade().current_revision == generator.REVISION


def test_downgrade_revokes_database_authority_preserves_roles_and_recovers(
    postgresql_cluster: PostgreSQLCluster, empty_database: str
) -> None:
    instance = _runner(postgresql_cluster, empty_database)
    instance.upgrade()
    result = instance.downgrade()
    assert result.current_revision == catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT count(*) FROM pg_catalog.pg_roles WHERE rolname = ANY(%s)",
            (list(generator.ROLES),),
        ).fetchone() == (8,)
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_policy AS p
            JOIN pg_catalog.pg_class AS c ON c.oid = p.polrelid
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname || '.' || c.relname = ANY(%s)
            """,
            (list(generator.RLS_TABLES),),
        ).fetchone() == (0,)
        assert not connection.execute(
            "SELECT has_schema_privilege('raos_public_ro', 'readmodel', 'USAGE')"
        ).fetchone()[0]
        _assert_default_function_public_deny(
            connection, postgresql_cluster.migration_user
        )
        _assert_future_function_is_not_public(
            connection, postgresql_cluster.migration_user
        )

    assert instance.upgrade().current_revision == generator.REVISION
