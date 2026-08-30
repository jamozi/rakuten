"""Exact PostgreSQL 18.4 runtime acceptance for the ST-0304 domain slice."""

from __future__ import annotations

import json

import psycopg
import pytest
from psycopg import sql

from .support import REPOSITORY_ROOT
from raos.migrations import MigrationError
from raos.migrations import catalog
from raos.migrations import runner
from scripts import build_st0304_domain_schemas as generator
from tests.postgresql18 import PostgreSQLCluster


DOMAIN_REVISION = "202608030004"
IAM_OPS_REVISION = "202608030003"
FOUNDATION_REVISION = "202608030002"
PUBLICATION_ANALYTICS_FINANCE_REVISION = "202608030005"
DATABASE_ROLES_REVISION = "202608030006"
_CUMULATIVE_REVISION_SPECS = catalog.REVISION_SPECS[:6]
_CUMULATIVE_HEAD_REVISION = DATABASE_ROLES_REVISION
SELECTED_SCHEMAS = ("portfolio", "catalog", "evidence", "editorial", "ai", "policy")


@pytest.fixture(autouse=True)
def _use_historical_domain_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise ST-0304 semantics against its frozen four-revision graph."""

    historical_specs = _CUMULATIVE_REVISION_SPECS[:4]
    assert historical_specs[-1].revision == DOMAIN_REVISION
    monkeypatch.setattr(catalog, "REVISION_SPECS", historical_specs)
    monkeypatch.setattr(catalog, "HEAD_REVISION", DOMAIN_REVISION)
    monkeypatch.setattr(runner, "REVISION_SPECS", historical_specs)
    monkeypatch.setattr(runner, "HEAD_REVISION", DOMAIN_REVISION)


def _use_cumulative_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalog, "REVISION_SPECS", _CUMULATIVE_REVISION_SPECS)
    monkeypatch.setattr(catalog, "HEAD_REVISION", _CUMULATIVE_HEAD_REVISION)
    monkeypatch.setattr(runner, "REVISION_SPECS", _CUMULATIVE_REVISION_SPECS)
    monkeypatch.setattr(runner, "HEAD_REVISION", _CUMULATIVE_HEAD_REVISION)


def _migration_runner(
    cluster: PostgreSQLCluster, database: str
) -> runner.MigrationRunner:
    return runner.MigrationRunner(REPOSITORY_ROOT, cluster.target(database))


def _set_migration_role(
    connection: psycopg.Connection[object], cluster: PostgreSQLCluster
) -> None:
    connection.execute(
        sql.SQL("SET ROLE {}").format(sql.Identifier(cluster.migration_user))
    )


def _selected_relations(connection: psycopg.Connection[object]) -> list[str]:
    return [
        f"{schema_name}.{relation_name}"
        for schema_name, relation_name in connection.execute(
            """
            SELECT namespace.nspname, relation.relname
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = ANY(%s)
              AND relation.relkind IN ('r', 'v')
            ORDER BY namespace.nspname, relation.relname
            """,
            (list(SELECTED_SCHEMAS),),
        ).fetchall()
    ]


def _execute_validation(
    connection: psycopg.Connection[object],
    cluster: PostgreSQLCluster,
    validation: str | None = None,
) -> list[tuple[object, ...]]:
    if validation is None:
        validation = (REPOSITORY_ROOT / generator.VALIDATION_PATH).read_text(
            encoding="utf-8"
        )
    with connection.cursor() as cursor:
        cursor.execute("SET TIME ZONE 'UTC'")
        cursor.execute("SET search_path = pg_catalog")
        cursor.execute(
            sql.SQL("SET ROLE {}").format(sql.Identifier(cluster.migration_user))
        )
        cursor.execute(validation)
        assert cursor.nextset() is True
        rows = cursor.fetchall()
        assert cursor.nextset() is None
    return rows


def test_zero_database_reaches_exact_cumulative_head_with_st0304_history(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_cumulative_graph(monkeypatch)
    instance = _migration_runner(postgresql_cluster, empty_database)

    assert catalog.HEAD_REVISION == DATABASE_ROLES_REVISION
    assert instance.status().current_revision == "base"
    result = instance.upgrade()
    assert result.current_revision == DATABASE_ROLES_REVISION
    assert result.revision_source_count == len(_CUMULATIVE_REVISION_SPECS) == 6
    assert result.changed is True
    assert instance.upgrade().changed is False
    assert instance.status().current_revision == DATABASE_ROLES_REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.raos_migration_version"
        ).fetchone() == (DATABASE_ROLES_REVISION,)
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
            (DOMAIN_REVISION, "ST-0304", "UPGRADE", "STARTED", "1.3.0"),
            (DOMAIN_REVISION, "ST-0304", "UPGRADE", "SUCCEEDED", "1.3.0"),
            (
                PUBLICATION_ANALYTICS_FINANCE_REVISION,
                "ST-0305",
                "UPGRADE",
                "STARTED",
                "1.4.0",
            ),
            (
                PUBLICATION_ANALYTICS_FINANCE_REVISION,
                "ST-0305",
                "UPGRADE",
                "SUCCEEDED",
                "1.4.0",
            ),
            (
                DATABASE_ROLES_REVISION,
                "ST-0306",
                "UPGRADE",
                "STARTED",
                "1.5.0",
            ),
            (
                DATABASE_ROLES_REVISION,
                "ST-0306",
                "UPGRADE",
                "SUCCEEDED",
                "1.5.0",
            ),
        ]


def test_cross_role_default_acl_is_rejected_and_cleanup_restores_validation(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    validation = generator.render_outputs()[generator.VALIDATION_PATH].decode("utf-8")
    role_name = f"st0304_acl_{empty_database}"[:63]
    role_created = False
    try:
        with postgresql_cluster.connect(empty_database) as connection:
            connection.execute(
                sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role_name))
            )
            role_created = True
            connection.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA portfolio "
                    "GRANT SELECT ON TABLES TO PUBLIC"
                ).format(sql.Identifier(role_name))
            )

        with postgresql_cluster.connect(empty_database) as connection:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="ST0304_PUBLIC_OR_DEFAULT_ACL_MISMATCH",
            ):
                _execute_validation(connection, postgresql_cluster, validation)
        with pytest.raises(MigrationError) as raised:
            instance.status()
        assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID
    finally:
        if role_created:
            with postgresql_cluster.connect(empty_database) as connection:
                connection.execute(
                    sql.SQL(
                        "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA portfolio "
                        "REVOKE SELECT ON TABLES FROM PUBLIC"
                    ).format(sql.Identifier(role_name))
                )
                connection.execute(
                    sql.SQL("DROP ROLE {}").format(sql.Identifier(role_name))
                )

    with postgresql_cluster.connect(empty_database) as connection:
        assert _execute_validation(connection, postgresql_cluster, validation) == [
            ("PASS", 86, 1141, 265, 11, 0)
        ]
    assert instance.status().current_revision == DOMAIN_REVISION


def test_rendered_baseline_metadata_exactly_matches_postgresql_comments(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    catalog_document = json.loads(
        generator.render_outputs()[generator.CATALOG_PATH].decode("utf-8")
    )
    baseline = catalog_document["baseline_metadata"]
    expected_tables = {
        (schema["id"], table["name"]): table["purpose"]
        for schema in baseline["schemas"]
        for table in schema["tables"]
    }
    expected_columns = {
        (schema["id"], table["name"], column["name"]): column["description"]
        for schema in baseline["schemas"]
        for table in schema["tables"]
        for column in table["columns"]
    }
    assert baseline["schema_count"] == 6
    assert baseline["table_count"] == len(expected_tables) == 66
    assert baseline["column_count"] == len(expected_columns) == 821

    _migration_runner(postgresql_cluster, empty_database).upgrade()
    table_identities = [".".join(identity) for identity in expected_tables]
    column_identities = [".".join(identity) for identity in expected_columns]
    with postgresql_cluster.connect(empty_database) as connection:
        observed_tables = {
            (schema_name, table_name): description
            for schema_name, table_name, description in connection.execute(
                """
                SELECT namespace.nspname,
                       relation.relname,
                       pg_catalog.obj_description(relation.oid, 'pg_class')
                FROM pg_catalog.pg_class AS relation
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                WHERE relation.relkind = 'r'
                  AND namespace.nspname || '.' || relation.relname = ANY(%s)
                ORDER BY namespace.nspname, relation.relname
                """,
                (table_identities,),
            ).fetchall()
        }
        observed_columns = {
            (schema_name, table_name, column_name): description
            for schema_name, table_name, column_name, description in connection.execute(
                """
                SELECT namespace.nspname,
                       relation.relname,
                       attribute.attname,
                       pg_catalog.col_description(relation.oid, attribute.attnum)
                FROM pg_catalog.pg_attribute AS attribute
                JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = attribute.attrelid
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                WHERE relation.relkind = 'r'
                  AND attribute.attnum > 0
                  AND attribute.attisdropped IS FALSE
                  AND namespace.nspname || '.' || relation.relname || '.'
                      || attribute.attname = ANY(%s)
                ORDER BY namespace.nspname, relation.relname, attribute.attnum
                """,
                (column_identities,),
            ).fetchall()
        }

    assert observed_tables.keys() == expected_tables.keys()
    assert observed_columns.keys() == expected_columns.keys()
    assert observed_tables == expected_tables
    assert observed_columns == expected_columns


def test_exact_cached_postgresql_18_4_fresh_chain_and_validation_sql(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    with postgresql_cluster.connect(empty_database) as connection:
        before_roles = connection.execute(
            "SELECT rolname FROM pg_catalog.pg_roles ORDER BY rolname"
        ).fetchall()
        assert connection.execute("SHOW server_version_num").fetchone() == ("180004",)

    instance = _migration_runner(postgresql_cluster, empty_database)
    assert instance.status().current_revision == "base"
    upgraded = instance.upgrade()
    assert upgraded.changed is True
    assert upgraded.current_revision == catalog.HEAD_REVISION == DOMAIN_REVISION
    assert upgraded.revision_source_count == 4
    assert instance.upgrade().changed is False

    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.raos_migration_version"
        ).fetchone() == (DOMAIN_REVISION,)
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
            (DOMAIN_REVISION, "ST-0304", "UPGRADE", "STARTED", "1.3.0"),
            (DOMAIN_REVISION, "ST-0304", "UPGRADE", "SUCCEEDED", "1.3.0"),
        ]
        assert _execute_validation(connection, postgresql_cluster) == [
            ("PASS", 86, 1141, 265, 11, 0)
        ]
        connection.execute("RESET ROLE")
        after_roles = connection.execute(
            "SELECT rolname FROM pg_catalog.pg_roles ORDER BY rolname"
        ).fetchall()
        assert after_roles == before_roles


def test_exact_catalog_inventory_acl_rls_and_out_of_scope_boundary(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        inventory_row = connection.execute(
            """
                WITH selected AS (
                    SELECT oid
                    FROM pg_catalog.pg_namespace
                    WHERE nspname = ANY(%s)
                )
                SELECT
                    (SELECT count(*) FROM pg_catalog.pg_class
                     WHERE relnamespace IN (SELECT oid FROM selected)
                       AND relkind = 'r'),
                    (SELECT count(*) FROM pg_catalog.pg_class
                     WHERE relnamespace IN (SELECT oid FROM selected)
                       AND relkind = 'v'),
                    (SELECT count(*) FROM pg_catalog.pg_attribute AS attribute
                     JOIN pg_catalog.pg_class AS relation
                       ON relation.oid = attribute.attrelid
                     WHERE relation.relnamespace IN (SELECT oid FROM selected)
                       AND relation.relkind = 'r'
                       AND attribute.attnum > 0
                       AND attribute.attisdropped IS FALSE),
                    (SELECT count(*) FROM pg_catalog.pg_attribute AS attribute
                     JOIN pg_catalog.pg_class AS relation
                       ON relation.oid = attribute.attrelid
                     WHERE relation.relnamespace IN (SELECT oid FROM selected)
                       AND relation.relkind = 'r'
                       AND attribute.attnum > 0
                       AND attribute.attisdropped IS FALSE
                       AND attribute.attnotnull IS TRUE),
                    (SELECT count(*) FROM pg_catalog.pg_constraint
                     WHERE connamespace IN (SELECT oid FROM selected)
                       AND contype IN ('p', 'u')),
                    (SELECT count(*) FROM pg_catalog.pg_constraint
                     WHERE connamespace IN (SELECT oid FROM selected)
                       AND contype = 'c'),
                    (SELECT count(*) FROM pg_catalog.pg_constraint
                     WHERE connamespace IN (SELECT oid FROM selected)
                       AND contype = 'f'),
                    (SELECT count(*) FROM pg_catalog.pg_index AS index_record
                     JOIN pg_catalog.pg_class AS relation
                       ON relation.oid = index_record.indrelid
                     WHERE relation.relnamespace IN (SELECT oid FROM selected)
                       AND NOT EXISTS (
                           SELECT 1 FROM pg_catalog.pg_constraint
                           WHERE conindid = index_record.indexrelid
                       )),
                    (SELECT count(*) FROM pg_catalog.pg_index AS index_record
                     JOIN pg_catalog.pg_class AS relation
                       ON relation.oid = index_record.indrelid
                     WHERE relation.relnamespace IN (SELECT oid FROM selected)),
                    (SELECT count(*) FROM pg_catalog.pg_proc
                     WHERE pronamespace IN (SELECT oid FROM selected)
                       AND prokind = 'f'),
                    (SELECT count(*) FROM pg_catalog.pg_trigger AS trigger_record
                     JOIN pg_catalog.pg_class AS relation
                       ON relation.oid = trigger_record.tgrelid
                     WHERE relation.relnamespace IN (SELECT oid FROM selected)
                       AND trigger_record.tgisinternal IS FALSE)
                """,
            (list(SELECTED_SCHEMAS),),
        ).fetchone()
        assert inventory_row is not None
        inventory = tuple(inventory_row)
        assert inventory == (86, 1, 1141, 861, 179, 453, 264, 274, 453, 48, 81)

        scope_foreign_keys = connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_constraint AS constraint_record
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = constraint_record.connamespace
            WHERE constraint_record.contype = 'f'
              AND (
                  namespace.nspname = ANY(%s)
                  OR constraint_record.conname = 'fk_ops_job_site_id'
              )
            """,
            (list(SELECTED_SCHEMAS),),
        ).fetchone()
        assert scope_foreign_keys == (265,)
        rls_shape = connection.execute(
            """
            SELECT count(*) FILTER (WHERE relation.relrowsecurity),
                   count(*) FILTER (WHERE relation.relforcerowsecurity),
                   (SELECT count(*)
                    FROM pg_catalog.pg_policy AS policy_record
                    JOIN pg_catalog.pg_class AS policy_relation
                      ON policy_relation.oid = policy_record.polrelid
                    WHERE policy_relation.relnamespace = ANY(
                        SELECT oid FROM pg_catalog.pg_namespace
                        WHERE nspname = ANY(%s)
                    ))
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = ANY(%s)
              AND relation.relkind = 'r'
            """,
            (list(SELECTED_SCHEMAS), list(SELECTED_SCHEMAS)),
        ).fetchone()
        assert rls_shape == (11, 11, 0)

        assert (
            connection.execute(
                """
            SELECT nspname
            FROM pg_catalog.pg_namespace
            WHERE nspname IN (
                'publishing', 'readmodel', 'freshness',
                'analytics', 'finance'
            )
            ORDER BY nspname
            """
            ).fetchall()
            == []
        )
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_constraint
            WHERE conname = 'fk_iam_break_glass_record_incident_id'
            """
        ).fetchone() == (0,)

    verification = runner.verify_repository(REPOSITORY_ROOT)
    engine = instance._open_engine(verification)
    try:
        with engine.connect() as connection:
            assert runner._st0304_catalog_digests(connection) == {
                key: (value["count"], value["md5"])
                for key, value in json.loads(
                    (REPOSITORY_ROOT / generator.CATALOG_PATH).read_text(
                        encoding="utf-8"
                    )
                )["postgresql_18_4_catalog_digests"].items()
                if key in runner._ST0304_CATALOG_DIGESTS
            }
            runner._validate_st0304_shape(connection, DOMAIN_REVISION)
    finally:
        engine.dispose()

    assert instance.status().current_revision == DOMAIN_REVISION


def test_empty_head_downgrades_to_physical_st0303_and_reupgrades(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    assert instance.upgrade().current_revision == DOMAIN_REVISION

    downgraded = instance.downgrade()
    assert downgraded.changed is True
    assert downgraded.current_revision == IAM_OPS_REVISION
    with postgresql_cluster.connect(empty_database) as connection:
        assert _selected_relations(connection) == []
        assert connection.execute(
            "SELECT to_regclass('ops.job'), to_regclass('iam.principal')"
        ).fetchone() == ("ops.job", "iam.principal")
        assert connection.execute(
            """
            SELECT count(*) FROM pg_catalog.pg_constraint
            WHERE conname = 'fk_ops_job_site_id'
            """
        ).fetchone() == (0,)

    assert instance.status().current_revision == IAM_OPS_REVISION
    assert instance.upgrade().current_revision == DOMAIN_REVISION
    assert instance.status().current_revision == DOMAIN_REVISION


def test_orphan_preflight_failed_upgrade_rolls_back_then_fk_is_enforced(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    assert instance.downgrade().current_revision == IAM_OPS_REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        _set_migration_role(connection, postgresql_cluster)
        orphan_site = connection.execute("SELECT pg_catalog.uuidv7()").fetchone()[0]
        connection.execute(
            """
            INSERT INTO ops.job (
                display_id, job_type, queue_name, site_id,
                created_by_actor_type
            ) VALUES ('JOB-ST0304-ORPHAN', 'TEST', 'test', %s, 'SYSTEM')
            """,
            (orphan_site,),
        )

    with pytest.raises(MigrationError) as raised:
        instance.upgrade()
    assert raised.value.code is runner.MigrationErrorCode.MIGRATION_FAILED

    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.raos_migration_version"
        ).fetchone() == (IAM_OPS_REVISION,)
        assert _selected_relations(connection) == []
        assert connection.execute(
            "SELECT count(*) FROM ops.job WHERE display_id = 'JOB-ST0304-ORPHAN'"
        ).fetchone() == (1,)
        _set_migration_role(connection, postgresql_cluster)
        connection.execute("DELETE FROM ops.job WHERE display_id = 'JOB-ST0304-ORPHAN'")

    assert instance.upgrade().current_revision == DOMAIN_REVISION
    with postgresql_cluster.connect(empty_database) as connection:
        _set_migration_role(connection, postgresql_cluster)
        orphan_site = connection.execute("SELECT pg_catalog.uuidv7()").fetchone()[0]
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            connection.execute(
                """
                INSERT INTO ops.job (
                    display_id, job_type, queue_name, site_id,
                    created_by_actor_type
                ) VALUES ('JOB-ST0304-FK', 'TEST', 'test', %s, 'SYSTEM')
                """,
                (orphan_site,),
            )


def test_nonempty_downgrade_failure_is_atomic_and_restores_forced_rls(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        _set_migration_role(connection, postgresql_cluster)
        connection.execute(
            """
            INSERT INTO portfolio.site (
                display_id, site_code, name, primary_domain, brand_name
            ) VALUES (
                'SITE-ST0304-DOWN', 'st0304-down', 'Downgrade guard',
                'st0304.example', 'RAOS'
            )
            """
        )

    with pytest.raises(MigrationError) as raised:
        instance.downgrade()
    assert raised.value.code is runner.MigrationErrorCode.MIGRATION_FAILED

    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.raos_migration_version"
        ).fetchone() == (DOMAIN_REVISION,)
        assert connection.execute("SELECT count(*) FROM portfolio.site").fetchone() == (
            1,
        )
        assert connection.execute(
            """
            SELECT count(*) FILTER (WHERE relrowsecurity),
                   count(*) FILTER (WHERE relforcerowsecurity)
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = ANY(%s)
              AND relation.relkind = 'r'
            """,
            (list(SELECTED_SCHEMAS),),
        ).fetchone() == (11, 11)
        _set_migration_role(connection, postgresql_cluster)
        connection.execute("DELETE FROM portfolio.site")

    assert instance.downgrade().current_revision == IAM_OPS_REVISION


@pytest.mark.parametrize(
    ("schema_name", "statement"),
    (
        (
            "portfolio",
            """INSERT INTO portfolio.site (
                   display_id, site_code, name, primary_domain, brand_name, status
               ) VALUES ('SITE-BAD', 'bad', 'bad', 'bad.example', 'bad', 'INVALID')""",
        ),
        (
            "catalog",
            """INSERT INTO catalog.provider_endpoint (
                   provider_code, provider_name, api_name, api_version,
                   base_host, status, contract_sha256, effective_from
               ) VALUES (
                   'bad', 'bad', 'bad', 'v1', 'bad.example', 'INVALID',
                   repeat('0', 64), CURRENT_TIMESTAMP
               )""",
        ),
        (
            "evidence",
            """INSERT INTO evidence.source (
                   display_id, source_type, name, authority_level, permitted_use
               ) VALUES ('SRC-BAD', 'INVALID', 'bad', 'PRIMARY', 'INTERNAL')""",
        ),
        (
            "editorial",
            """INSERT INTO editorial.article (
                   display_id, site_id, article_plan_id, article_type
               ) VALUES (
                   'ART-BAD', pg_catalog.uuidv7(), pg_catalog.uuidv7(), 'INVALID'
               )""",
        ),
        (
            "ai",
            """INSERT INTO ai.task_definition (
                   task_code, name, description, risk_level,
                   output_schema_code, default_max_tokens,
                   default_max_cost_jpy
               ) VALUES ('bad', 'bad', 'bad', 'INVALID', 'bad', 100, 0)""",
        ),
        (
            "policy",
            """INSERT INTO policy.policy_bundle (
                   display_id, bundle_code, version_no, status,
                   git_commit_sha, bundle_sha256
               ) VALUES (
                   'POL-BAD', 'bad', 0, 'DRAFT', repeat('0', 40), repeat('0', 64)
               )""",
        ),
    ),
)
def test_representative_data_constraints_reject_invalid_rows_in_every_schema(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    schema_name: str,
    statement: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        _set_migration_role(connection, postgresql_cluster)
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(statement)
        assert connection.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(schema_name),
                sql.Identifier(
                    {
                        "portfolio": "site",
                        "catalog": "provider_endpoint",
                        "evidence": "source",
                        "editorial": "article",
                        "ai": "task_definition",
                        "policy": "policy_bundle",
                    }[schema_name]
                ),
            )
        ).fetchone() == (0,)


def test_fk_touch_trigger_and_st0304_immutability_trigger_are_enforced(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        _set_migration_role(connection, postgresql_cluster)
        site_id, initial_updated_at, initial_lock_version = connection.execute(
            """
            INSERT INTO portfolio.site (
                display_id, site_code, name, primary_domain, brand_name
            ) VALUES (
                'SITE-ST0304-LIVE', 'st0304-live', 'Live site',
                'live.example', 'RAOS'
            ) RETURNING id, updated_at, lock_version
            """
        ).fetchone()
        updated_at, lock_version = connection.execute(
            """
            UPDATE portfolio.site
            SET name = 'Live site updated'
            WHERE id = %s
            RETURNING updated_at, lock_version
            """,
            (site_id,),
        ).fetchone()
        assert initial_lock_version == 0
        assert lock_version == 1
        assert updated_at >= initial_updated_at

        connection.execute(
            """
            INSERT INTO ops.job (
                display_id, job_type, queue_name, site_id,
                created_by_actor_type
            ) VALUES (
                'JOB-ST0304-SITE', 'TEST', 'test', %s, 'SYSTEM'
            )
            """,
            (site_id,),
        )
        with pytest.raises(psycopg.errors.RestrictViolation):
            connection.execute("DELETE FROM portfolio.site WHERE id = %s", (site_id,))

        artifact_id = connection.execute(
            """
            INSERT INTO ops.object_artifact (
                display_id, artifact_kind, bucket_name, object_key,
                content_type, byte_size, sha256, encryption_state,
                retention_class, source_system
            ) VALUES (
                'OBJ-ST0304-SNAPSHOT', 'source_snapshot', 'raos-raw',
                'st0304/source.json', 'application/json', 2, repeat('a', 64),
                'LOCAL_DEV', 'TEST', 'ST0304'
            ) RETURNING id
            """
        ).fetchone()[0]
        source_id = connection.execute(
            """
            INSERT INTO evidence.source (
                display_id, source_type, name, authority_level, permitted_use
            ) VALUES (
                'SRC-ST0304-SNAPSHOT', 'OFFICIAL_DOCUMENT', 'ST0304 source',
                'OFFICIAL', 'INTERNAL'
            ) RETURNING id
            """
        ).fetchone()[0]
        snapshot_id = connection.execute(
            """
            INSERT INTO evidence.source_snapshot (
                display_id, source_id, artifact_id, acquired_at,
                content_sha256, parser_version, validation_status
            ) VALUES (
                'SSN-ST0304', %s, %s, CURRENT_TIMESTAMP,
                repeat('a', 64), '1.0.0', 'VALID'
            ) RETURNING id
            """,
            (source_id, artifact_id),
        ).fetchone()[0]
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                "UPDATE evidence.source_snapshot SET parser_version = '1.0.1' "
                "WHERE id = %s",
                (snapshot_id,),
            )


def test_status_rejects_unlisted_domain_object_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute("CREATE TABLE portfolio.st0304_drift (id integer)")

    with pytest.raises(MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute("DROP TABLE portfolio.st0304_drift")
    assert instance.status().current_revision == DOMAIN_REVISION
