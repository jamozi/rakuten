"""Exact PostgreSQL 18.4 runtime acceptance for ST-0305."""

from __future__ import annotations

import psycopg
import pytest
from psycopg import sql

from conftest import REPOSITORY_ROOT
from raos.migrations import catalog, runner
from scripts import build_st0305_publication_analytics_finance as generator
from tests.postgresql18 import PostgreSQLCluster


DOMAIN_REVISION = "202608030004"
PUBLICATION_ANALYTICS_FINANCE_REVISION = "202608030005"
DATABASE_ROLES_REVISION = "202608030006"
_CUMULATIVE_REVISION_SPECS = catalog.REVISION_SPECS
_CUMULATIVE_HEAD_REVISION = catalog.HEAD_REVISION


@pytest.fixture(autouse=True)
def _use_historical_publication_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise ST-0305 semantics against its frozen five-revision graph."""

    historical_specs = _CUMULATIVE_REVISION_SPECS[:5]
    assert historical_specs[-1].revision == PUBLICATION_ANALYTICS_FINANCE_REVISION
    monkeypatch.setattr(catalog, "REVISION_SPECS", historical_specs)
    monkeypatch.setattr(
        catalog, "HEAD_REVISION", PUBLICATION_ANALYTICS_FINANCE_REVISION
    )
    monkeypatch.setattr(runner, "REVISION_SPECS", historical_specs)
    monkeypatch.setattr(runner, "HEAD_REVISION", PUBLICATION_ANALYTICS_FINANCE_REVISION)


def _use_cumulative_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalog, "REVISION_SPECS", _CUMULATIVE_REVISION_SPECS)
    monkeypatch.setattr(catalog, "HEAD_REVISION", _CUMULATIVE_HEAD_REVISION)
    monkeypatch.setattr(runner, "REVISION_SPECS", _CUMULATIVE_REVISION_SPECS)
    monkeypatch.setattr(runner, "HEAD_REVISION", _CUMULATIVE_HEAD_REVISION)


def _migration_runner(
    cluster: PostgreSQLCluster, database: str
) -> runner.MigrationRunner:
    return runner.MigrationRunner(REPOSITORY_ROOT, cluster.target(database))


def _execute_validation(
    connection: psycopg.Connection[object], cluster: PostgreSQLCluster
) -> list[tuple[object, ...]]:
    validation = generator.render_outputs()[generator.VALIDATION_PATH].decode("utf-8")
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("SET ROLE {}").format(sql.Identifier(cluster.migration_user))
        )
        cursor.execute(validation)
        rows: list[tuple[object, ...]] = []
        while True:
            if cursor.description is not None:
                rows = cursor.fetchall()
            if cursor.nextset() is None:
                break
    return rows


def test_zero_database_reaches_exact_cumulative_head_with_st0305_history(
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
            WHERE revision_id IN (%s, %s)
            ORDER BY event_id
            """,
            (PUBLICATION_ANALYTICS_FINANCE_REVISION, DATABASE_ROLES_REVISION),
        ).fetchall() == [
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


def _insert_valid_publication_fixture(
    connection: psycopg.Connection[object],
) -> None:
    """Insert a complete, trigger-valid ST-0305 publication lineage."""
    connection.execute(
        """
        INSERT INTO iam.principal (
            id, display_id, principal_type, status, display_name
        ) VALUES (
            '00000000-0000-0000-0000-000000000001',
            'PRN-ST0305-FIXTURE', 'USER', 'ACTIVE', 'ST0305 Fixture User'
        );
        INSERT INTO portfolio.site (
            id, display_id, site_code, name, primary_domain, brand_name
        ) VALUES (
            '00000000-0000-0000-0000-000000000010',
            'STE-ST0305-FIXTURE', 'st0305-fixture', 'ST0305 Fixture',
            'fixture.invalid', 'Fixture'
        );
        INSERT INTO portfolio.category (
            id, display_id, site_id, category_code, name, risk_class, stage
        ) VALUES (
            '00000000-0000-0000-0000-000000000011',
            'CAT-ST0305-FIXTURE', '00000000-0000-0000-0000-000000000010',
            'fixture', 'Fixture', 'LOW', 'CANDIDATE'
        );
        INSERT INTO portfolio.intent_cluster (
            id, display_id, category_id, cluster_code, name, description,
            intent_type
        ) VALUES (
            '00000000-0000-0000-0000-000000000012',
            'ITC-ST0305-FIXTURE', '00000000-0000-0000-0000-000000000011',
            'fixture', 'Fixture', 'Fixture intent', 'SELECTION_GUIDE'
        );
        INSERT INTO portfolio.keyword (
            id, display_id, site_id, display_text, normalized_text
        ) VALUES (
            '00000000-0000-0000-0000-000000000013',
            'KWD-ST0305-FIXTURE', '00000000-0000-0000-0000-000000000010',
            'fixture keyword', 'fixture keyword'
        );
        INSERT INTO editorial.article_plan (
            id, display_id, site_id, category_id, intent_cluster_id,
            primary_keyword_id, article_type, working_title, objective,
            status, created_by_principal_id
        ) VALUES (
            '00000000-0000-0000-0000-000000000014',
            'APL-ST0305-FIXTURE', '00000000-0000-0000-0000-000000000010',
            '00000000-0000-0000-0000-000000000011',
            '00000000-0000-0000-0000-000000000012',
            '00000000-0000-0000-0000-000000000013', 'SELECTION_GUIDE',
            'Fixture title', 'Exercise publication guards', 'IDEA',
            '00000000-0000-0000-0000-000000000001'
        );
        INSERT INTO evidence.source_packet (
            id, display_id, article_plan_id, packet_type, status,
            current_version_no
        ) VALUES (
            '00000000-0000-0000-0000-000000000020',
            'SPK-ST0305-FIXTURE', '00000000-0000-0000-0000-000000000014',
            'ARTICLE_DRAFT', 'APPROVED', 1
        );
        INSERT INTO ops.object_artifact (
            id, display_id, artifact_kind, bucket_name, object_key,
            content_type, byte_size, sha256, encryption_state,
            retention_class, source_system
        ) VALUES (
            '00000000-0000-0000-0000-000000000021',
            'ART-ST0305-SOURCE', 'source_packet', 'fixture',
            'source/packet.json', 'application/json', 2, repeat('a', 64),
            'LOCAL_DEV', 'TEST', 'ST0305_FIXTURE'
        );
        INSERT INTO evidence.source_packet_version (
            id, display_id, source_packet_id, version_no, artifact_id,
            content_sha256, schema_version, status, reviewed_by_principal_id,
            reviewed_at
        ) VALUES (
            '00000000-0000-0000-0000-000000000022',
            'SPV-ST0305-FIXTURE', '00000000-0000-0000-0000-000000000020',
            1, '00000000-0000-0000-0000-000000000021', repeat('a', 64), 1,
            'APPROVED', '00000000-0000-0000-0000-000000000001',
            TIMESTAMPTZ '2026-08-05 00:00:00+00'
        );
        INSERT INTO editorial.content_schema_version (
            id, schema_code, semantic_version, artifact_id, schema_sha256,
            status, effective_from
        ) VALUES (
            '00000000-0000-0000-0000-000000000023', 'st0305.fixture',
            '1.0.0', '00000000-0000-0000-0000-000000000021',
            repeat('a', 64), 'DRAFT', TIMESTAMPTZ '2026-08-05 00:00:00+00'
        );
        INSERT INTO editorial.article_type_version (
            id, article_type_code, semantic_version, contract,
            contract_sha256, status
        ) VALUES (
            '00000000-0000-0000-0000-000000000024', 'selection_guide',
            '1.0.0', '{}'::jsonb, repeat('b', 64), 'DRAFT'
        );
        INSERT INTO editorial.article_template_version (
            id, article_type_version_id, semantic_version, template,
            template_sha256, status
        ) VALUES (
            '00000000-0000-0000-0000-000000000025',
            '00000000-0000-0000-0000-000000000024', '1.0.0', '{}'::jsonb,
            repeat('c', 64), 'DRAFT'
        );
        INSERT INTO editorial.article (
            id, display_id, site_id, article_plan_id, article_type, status
        ) VALUES (
            '00000000-0000-0000-0000-000000000030',
            'ARL-ST0305-FIXTURE', '00000000-0000-0000-0000-000000000010',
            '00000000-0000-0000-0000-000000000014', 'SELECTION_GUIDE',
            'DRAFT'
        );
        INSERT INTO editorial.article_version (
            id, display_id, article_id, version_no, content_schema_version,
            title, body_sha256, status, source_packet_version_id,
            created_by_actor_type, created_by_actor_id,
            content_schema_version_id, article_type_version_id,
            article_template_version_id, seo_metadata_version_id
        ) VALUES (
            '00000000-0000-0000-0000-000000000031',
            'ARV-ST0305-FIXTURE', '00000000-0000-0000-0000-000000000030',
            1, 1, 'Fixture article', repeat('b', 64), 'DRAFT',
            '00000000-0000-0000-0000-000000000022', 'USER',
            '00000000-0000-0000-0000-000000000001',
            '00000000-0000-0000-0000-000000000023',
            '00000000-0000-0000-0000-000000000024',
            '00000000-0000-0000-0000-000000000025',
            '00000000-0000-0000-0000-000000000026'
        );
        INSERT INTO editorial.seo_metadata_version (
            id, article_version_id, semantic_version, metadata,
            metadata_sha256, status
        ) VALUES (
            '00000000-0000-0000-0000-000000000026',
            '00000000-0000-0000-0000-000000000031', '1.0.0', '{}'::jsonb,
            repeat('d', 64), 'DRAFT'
        );
        INSERT INTO policy.policy_bundle (
            id, display_id, bundle_code, version_no, status, git_commit_sha,
            bundle_sha256
        ) VALUES (
            '00000000-0000-0000-0000-000000000040',
            'PBL-ST0305-FIXTURE', 'st0305-fixture', 1, 'DRAFT',
            repeat('c', 40), repeat('d', 64)
        );
        INSERT INTO policy.quality_check_run (
            id, display_id, article_version_id, source_packet_version_id,
            policy_bundle_id, status, triggered_by_actor_type,
            triggered_by_actor_id, started_at, completed_at, total_score,
            blocking_finding_count
        ) VALUES (
            '00000000-0000-0000-0000-000000000041',
            'QCR-ST0305-FIXTURE', '00000000-0000-0000-0000-000000000031',
            '00000000-0000-0000-0000-000000000022',
            '00000000-0000-0000-0000-000000000040', 'PASSED', 'USER',
            '00000000-0000-0000-0000-000000000001',
            TIMESTAMPTZ '2026-08-05 00:00:00+00',
            TIMESTAMPTZ '2026-08-05 00:01:00+00', 100, 0
        );
        INSERT INTO policy.quality_score (
            id, quality_check_run_id, score_version, total_score, pass_score,
            factual_accuracy_score, disclosure_policy_score, passed
        ) VALUES (
            '00000000-0000-0000-0000-000000000042',
            '00000000-0000-0000-0000-000000000041', 'fixture-v1', 100, 80,
            20, 5, true
        );
        """
    )
    connection.execute(
        """
        INSERT INTO publishing.approval (
            id, display_id, article_version_id, approval_type, decision,
            quality_check_run_id, policy_bundle_id, decision_reason,
            approved_by_principal_id, approved_at, valid_until
        ) VALUES (
            '00000000-0000-0000-0000-000000000050',
            'APV-ST0305-FIXTURE', '00000000-0000-0000-0000-000000000031',
            'FINAL', 'APPROVED', '00000000-0000-0000-0000-000000000041',
            '00000000-0000-0000-0000-000000000040',
            'Fixture final approval', '00000000-0000-0000-0000-000000000001',
            TIMESTAMPTZ '2026-08-05 00:02:00+00',
            TIMESTAMPTZ '2099-01-01 00:00:00+00'
        );
        INSERT INTO publishing.publication_candidate (
            id, display_id, site_id, article_version_id, final_approval_id,
            quality_check_run_id, requested_by_principal_id,
            request_idempotency_key, status, requested_at
        ) VALUES (
            '00000000-0000-0000-0000-000000000051',
            'PCD-ST0305-FIXTURE', '00000000-0000-0000-0000-000000000010',
            '00000000-0000-0000-0000-000000000031',
            '00000000-0000-0000-0000-000000000050',
            '00000000-0000-0000-0000-000000000041',
            '00000000-0000-0000-0000-000000000001', 'st0305-fixture',
            'REQUESTED', TIMESTAMPTZ '2026-08-05 00:03:00+00'
        );
        INSERT INTO ops.job (
            id, display_id, job_type, queue_name, status,
            created_by_actor_type
        ) VALUES (
            '00000000-0000-0000-0000-000000000052',
            'JOB-ST0305-FIXTURE', 'BUILD_PUBLICATION_SNAPSHOT', 'fixture',
            'REQUESTED', 'SYSTEM'
        );
        INSERT INTO ops.object_artifact (
            id, display_id, artifact_kind, bucket_name, object_key,
            content_type, byte_size, sha256, encryption_state,
            retention_class, source_system
        ) VALUES (
            '00000000-0000-0000-0000-000000000053',
            'ART-ST0305-SNAPSHOT', 'publication_snapshot', 'fixture',
            'publication/snapshot.json', 'application/json', 2,
            repeat('e', 64), 'LOCAL_DEV', 'TEST', 'ST0305_FIXTURE'
        );
        INSERT INTO publishing.publication_snapshot (
            id, display_id, site_id, article_id, article_version_id,
            publication_candidate_id, artifact_id, schema_version,
            content_sha256, source_packet_version_id, policy_bundle_id,
            quality_check_run_id, final_approval_id, canonical_path, title,
            disclosure_text, built_by_job_id, built_at
        ) VALUES (
            '00000000-0000-0000-0000-000000000054',
            'PSN-ST0305-FIXTURE', '00000000-0000-0000-0000-000000000010',
            '00000000-0000-0000-0000-000000000030',
            '00000000-0000-0000-0000-000000000031',
            '00000000-0000-0000-0000-000000000051',
            '00000000-0000-0000-0000-000000000053', 1, repeat('e', 64),
            '00000000-0000-0000-0000-000000000022',
            '00000000-0000-0000-0000-000000000040',
            '00000000-0000-0000-0000-000000000041',
            '00000000-0000-0000-0000-000000000050', '/st0305-fixture',
            'Fixture article', 'Fixture disclosure',
            '00000000-0000-0000-0000-000000000052',
            TIMESTAMPTZ '2026-08-05 00:04:00+00'
        );
        UPDATE publishing.publication_candidate
        SET publication_snapshot_id = '00000000-0000-0000-0000-000000000054',
            snapshot_build_job_id = '00000000-0000-0000-0000-000000000052',
            status = 'SNAPSHOT_READY',
            completed_at = TIMESTAMPTZ '2026-08-05 00:04:00+00'
        WHERE id = '00000000-0000-0000-0000-000000000051';
        INSERT INTO publishing.publication (
            id, display_id, site_id, article_id, channel, state,
            current_snapshot_id
        ) VALUES (
            '00000000-0000-0000-0000-000000000055',
            'PUB-ST0305-FIXTURE', '00000000-0000-0000-0000-000000000010',
            '00000000-0000-0000-0000-000000000030', 'WEB', 'UNPUBLISHED',
            '00000000-0000-0000-0000-000000000054'
        );
        """
    )


def _set_migration_role(
    connection: psycopg.Connection[object], cluster: PostgreSQLCluster
) -> None:
    connection.execute(
        sql.SQL("SET ROLE {}").format(sql.Identifier(cluster.migration_user))
    )
    assert connection.execute("SELECT current_user").fetchone() == (
        cluster.migration_user,
    )


def _create_test_kill_switch_surface(
    connection: psycopg.Connection[object],
) -> None:
    connection.execute(
        """
        CREATE TABLE ops.kill_switch (
            switch_type text NOT NULL,
            scope_type text NOT NULL,
            scope_id uuid,
            is_engaged boolean NOT NULL,
            expires_at timestamptz
        )
        """
    )


def _publish_fixture(connection: psycopg.Connection[object]) -> str:
    row = connection.execute(
        """
        UPDATE publishing.publication
        SET state = 'PUBLISHED'
        WHERE id = '00000000-0000-0000-0000-000000000055'
        RETURNING state
        """
    ).fetchone()
    assert row is not None
    return str(row[0])


def _insert_fixture_approval_revocation(
    connection: psycopg.Connection[object],
) -> None:
    connection.execute(
        """
        INSERT INTO publishing.approval (
            id, display_id, article_version_id, approval_type, decision,
            quality_check_run_id, policy_bundle_id, decision_reason,
            approved_by_principal_id, approved_at, revoked_at,
            revoked_by_principal_id, revocation_reason,
            supersedes_approval_id
        ) VALUES (
            '00000000-0000-0000-0000-000000000056',
            'APV-ST0305-REVOKED', '00000000-0000-0000-0000-000000000031',
            'FINAL', 'REVOKED', '00000000-0000-0000-0000-000000000041',
            '00000000-0000-0000-0000-000000000040',
            'Fixture revocation', '00000000-0000-0000-0000-000000000001',
            TIMESTAMPTZ '2026-08-05 00:05:00+00',
            TIMESTAMPTZ '2026-08-05 00:06:00+00',
            '00000000-0000-0000-0000-000000000001',
            'Fixture approval revoked',
            '00000000-0000-0000-0000-000000000050'
        )
        """
    )


def test_publication_fails_closed_when_kill_switch_surface_is_absent(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    assert instance.upgrade().current_revision == catalog.HEAD_REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        # ST-0306 owns RLS policies; the ST-0304 binding tables are FORCE RLS
        # with no policies by design, so the exact fixture is seeded by the
        # isolated cluster superuser while all normal triggers remain enabled.
        _insert_valid_publication_fixture(connection)
        _set_migration_role(connection, postgresql_cluster)
        with pytest.raises(
            psycopg.errors.ObjectNotInPrerequisiteState,
            match="ST0305_KILL_SWITCH_UNAVAILABLE",
        ) as raised:
            connection.execute(
                """
                UPDATE publishing.publication
                SET state = 'PUBLISHED'
                WHERE id = '00000000-0000-0000-0000-000000000055'
                """
            )
        assert raised.value.sqlstate == "55000"


@pytest.mark.parametrize(
    "seed_sql",
    (
        None,
        """
        INSERT INTO ops.kill_switch
            (switch_type, scope_type, scope_id, is_engaged, expires_at)
        VALUES ('PUBLICATION', 'GLOBAL', NULL, false, NULL)
        """,
        """
        INSERT INTO ops.kill_switch
            (switch_type, scope_type, scope_id, is_engaged, expires_at)
        VALUES (
            'PUBLICATION', 'GLOBAL', NULL, true,
            TIMESTAMPTZ '2000-01-01 00:00:00+00'
        )
        """,
        """
        INSERT INTO ops.kill_switch
            (switch_type, scope_type, scope_id, is_engaged, expires_at)
        VALUES (
            'PUBLICATION', 'SITE',
            '00000000-0000-0000-0000-000000000099', true, NULL
        )
        """,
    ),
    ids=("empty", "false", "expired", "nonmatching"),
)
def test_publication_allows_only_non_engaged_kill_switch_states(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    seed_sql: str | None,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    assert instance.upgrade().current_revision == catalog.HEAD_REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        _insert_valid_publication_fixture(connection)
        _set_migration_role(connection, postgresql_cluster)
        _create_test_kill_switch_surface(connection)
        if seed_sql is not None:
            connection.execute(seed_sql)
        assert _publish_fixture(connection) == "PUBLISHED"
        connection.execute("DROP TABLE ops.kill_switch")

    assert instance.status().current_revision == catalog.HEAD_REVISION


@pytest.mark.parametrize(
    ("scope_type", "scope_id"),
    (
        ("GLOBAL", None),
        ("SITE", "00000000-0000-0000-0000-000000000010"),
        ("CATEGORY", "00000000-0000-0000-0000-000000000011"),
        ("ARTICLE", "00000000-0000-0000-0000-000000000030"),
    ),
    ids=("global", "site", "category", "article"),
)
def test_publication_rejects_every_matching_engaged_kill_switch_scope(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    scope_type: str,
    scope_id: str | None,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    assert instance.upgrade().current_revision == catalog.HEAD_REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        _insert_valid_publication_fixture(connection)
        _set_migration_role(connection, postgresql_cluster)
        _create_test_kill_switch_surface(connection)
        connection.execute(
            """
            INSERT INTO ops.kill_switch (
                switch_type, scope_type, scope_id, is_engaged, expires_at
            ) VALUES ('PUBLICATION', %s, %s, true, NULL)
            """,
            (scope_type, scope_id),
        )
        with connection.transaction():
            with pytest.raises(
                psycopg.errors.ObjectNotInPrerequisiteState,
                match="ST0305_PUBLICATION_KILL_SWITCH_ENGAGED",
            ) as raised:
                _publish_fixture(connection)
            assert raised.value.sqlstate == "55000"
        connection.execute("DROP TABLE ops.kill_switch")

    assert instance.status().current_revision == catalog.HEAD_REVISION


def test_publication_guard_ignores_hostile_session_search_path(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    assert instance.upgrade().current_revision == catalog.HEAD_REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        _insert_valid_publication_fixture(connection)
        connection.execute("CREATE SCHEMA st0305_hostile")
        connection.execute(
            """
            CREATE FUNCTION st0305_hostile.statement_timestamp()
            RETURNS timestamptz
            LANGUAGE sql IMMUTABLE
            AS $$ SELECT TIMESTAMPTZ '1900-01-01 00:00:00+00' $$
            """
        )
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA st0305_hostile TO {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(
            sql.SQL(
                "GRANT EXECUTE ON FUNCTION st0305_hostile.statement_timestamp() TO {}"
            ).format(sql.Identifier(postgresql_cluster.migration_user))
        )
        _set_migration_role(connection, postgresql_cluster)
        _create_test_kill_switch_surface(connection)
        connection.execute("SET search_path = st0305_hostile, pg_catalog, public")
        assert connection.execute(
            "SELECT statement_timestamp() = TIMESTAMPTZ '1900-01-01 00:00:00+00'"
        ).fetchone() == (True,)
        assert _publish_fixture(connection) == "PUBLISHED"
        connection.execute("DROP TABLE ops.kill_switch")
        connection.execute("RESET ROLE")
        connection.execute("DROP SCHEMA st0305_hostile CASCADE")

    assert instance.status().current_revision == catalog.HEAD_REVISION


def test_final_approval_requires_an_active_user_at_write_time(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        _insert_valid_publication_fixture(connection)
        _set_migration_role(connection, postgresql_cluster)
        connection.execute(
            """
            UPDATE iam.principal
            SET status = 'SUSPENDED'
            WHERE id = '00000000-0000-0000-0000-000000000001'
            """
        )
        with connection.transaction():
            with pytest.raises(
                psycopg.errors.CheckViolation,
                match="ST0305_FINAL_APPROVAL_REQUIRES_ACTIVE_USER",
            ) as raised:
                connection.execute(
                    """
                    INSERT INTO publishing.approval (
                        id, display_id, article_version_id, approval_type,
                        decision, quality_check_run_id, policy_bundle_id,
                        decision_reason, approved_by_principal_id, approved_at,
                        valid_until
                    ) VALUES (
                        '00000000-0000-0000-0000-000000000057',
                        'APV-ST0305-INACTIVE',
                        '00000000-0000-0000-0000-000000000031',
                        'FINAL', 'APPROVED',
                        '00000000-0000-0000-0000-000000000041',
                        '00000000-0000-0000-0000-000000000040',
                        'Must reject inactive approver',
                        '00000000-0000-0000-0000-000000000001',
                        TIMESTAMPTZ '2026-08-05 00:07:00+00',
                        TIMESTAMPTZ '2099-01-01 00:00:00+00'
                    )
                    """
                )
            assert raised.value.sqlstate == "23514"
        connection.execute(
            """
            UPDATE iam.principal
            SET status = 'ACTIVE'
            WHERE id = '00000000-0000-0000-0000-000000000001'
            """
        )


def test_revocation_is_rechecked_by_candidate_and_publication_guards(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        _insert_valid_publication_fixture(connection)
        _set_migration_role(connection, postgresql_cluster)
        _insert_fixture_approval_revocation(connection)

        with connection.transaction():
            with pytest.raises(
                psycopg.errors.CheckViolation,
                match="ST0305_PUBLICATION_CANDIDATE_NOT_APPROVED",
            ) as candidate_error:
                connection.execute(
                    """
                    UPDATE publishing.publication_candidate
                    SET status = 'VALIDATING'
                    WHERE id = '00000000-0000-0000-0000-000000000051'
                    """
                )
            assert candidate_error.value.sqlstate == "23514"

        _create_test_kill_switch_surface(connection)
        with connection.transaction():
            with pytest.raises(
                psycopg.errors.CheckViolation,
                match="ST0305_PUBLICATION_SNAPSHOT_NOT_APPROVED",
            ) as publication_error:
                _publish_fixture(connection)
            assert publication_error.value.sqlstate == "23514"
        connection.execute("DROP TABLE ops.kill_switch")


@pytest.mark.parametrize(
    "mutation",
    (
        """
        UPDATE policy.quality_score
        SET total_score = 0, passed = false
        WHERE id = '00000000-0000-0000-0000-000000000042'
        """,
        """
        UPDATE policy.quality_check_run
        SET status = 'FAILED'
        WHERE id = '00000000-0000-0000-0000-000000000041'
        """,
        """
        UPDATE policy.quality_check_run
        SET blocking_finding_count = 1
        WHERE id = '00000000-0000-0000-0000-000000000041'
        """,
        """
        UPDATE evidence.source_packet_version
        SET status = 'REJECTED'
        WHERE id = '00000000-0000-0000-0000-000000000022'
        """,
        """
        UPDATE iam.principal
        SET status = 'SUSPENDED'
        WHERE id = '00000000-0000-0000-0000-000000000001'
        """,
        """
        UPDATE publishing.approval
        SET decision = 'REJECTED'
        WHERE id = '00000000-0000-0000-0000-000000000050'
        """,
        """
        UPDATE publishing.publication_candidate
        SET status = 'BLOCKED', blocked_reason_code = 'TEST_INVALIDATION'
        WHERE id = '00000000-0000-0000-0000-000000000051'
        """,
        """
        INSERT INTO portfolio.site (
            id, display_id, site_code, name, primary_domain, brand_name
        ) VALUES (
            '00000000-0000-0000-0000-000000000099',
            'STE-ST0305-OTHER', 'st0305-other', 'ST0305 Other',
            'other.invalid', 'Other'
        );
        UPDATE editorial.article
        SET site_id = '00000000-0000-0000-0000-000000000099'
        WHERE id = '00000000-0000-0000-0000-000000000030'
        """,
        """
        INSERT INTO policy.rule_version (
            id, rule_code, version_no, rule_category, severity, is_blocking,
            implementation_type, definition, definition_sha256, status,
            created_by_principal_id
        ) VALUES (
            '00000000-0000-0000-0000-000000000043', 'st0305_fixture_rule',
            1, 'QUALITY', 'HIGH', true, 'JSON_SCHEMA', '{}'::jsonb,
            repeat('f', 64), 'DRAFT',
            '00000000-0000-0000-0000-000000000001'
        );
        INSERT INTO policy.finding (
            id, quality_check_run_id, rule_version_id, finding_code,
            severity, is_blocking, entity_type, entity_id, message, status
        ) VALUES (
            '00000000-0000-0000-0000-000000000044',
            '00000000-0000-0000-0000-000000000041',
            '00000000-0000-0000-0000-000000000043', 'ST0305_FIXTURE',
            'HIGH', true, 'ARTICLE_VERSION',
            '00000000-0000-0000-0000-000000000031',
            'Fixture open blocking finding', 'OPEN'
        )
        """,
    ),
    ids=(
        "quality-score-failed",
        "quality-run-failed",
        "blocking-count",
        "source-packet-rejected",
        "approver-inactive",
        "approval-rejected",
        "candidate-blocked",
        "article-site-lineage",
        "open-blocking-finding",
    ),
)
def test_publication_rechecks_all_approval_quality_and_lineage_inputs(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    mutation: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        _insert_valid_publication_fixture(connection)
        _set_migration_role(connection, postgresql_cluster)
        connection.execute(mutation)
        _create_test_kill_switch_surface(connection)
        with connection.transaction():
            with pytest.raises(
                psycopg.errors.CheckViolation,
                match="ST0305_PUBLICATION_SNAPSHOT_NOT_APPROVED",
            ) as raised:
                _publish_fixture(connection)
            assert raised.value.sqlstate == "23514"
        connection.execute("DROP TABLE ops.kill_switch")


def test_schema_boundaries_exclude_public_finance_and_raw_identifiers(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        assert (
            connection.execute(
                """
            SELECT table_schema, table_name, column_name
            FROM information_schema.columns
            WHERE table_schema IN ('readmodel', 'editorial')
              AND lower(column_name) ~
                  '(affiliate_rate|commission|revenue|profit|epc|rpm|attribution)'
            ORDER BY table_schema, table_name, ordinal_position
            """
            ).fetchall()
            == []
        )
        assert (
            connection.execute(
                """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'analytics'
              AND table_name IN ('anonymous_event', 'affiliate_click_event')
              AND lower(column_name) = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
                (
                    [
                        "ip",
                        "raw_ip",
                        "ip_address",
                        "remote_addr",
                        "user_agent",
                        "full_user_agent",
                        "email",
                        "email_address",
                        "query",
                        "query_id",
                        "raw_search_query",
                        "url_query",
                        "free_form_identifier",
                        "user_id",
                        "account_id",
                        "cookie",
                        "cookie_id",
                        "device_id",
                    ],
                ),
            ).fetchall()
            == []
        )
        assert connection.execute(
            """
            SELECT count(*) FILTER (WHERE relation.relrowsecurity),
                   count(*) FILTER (WHERE relation.relforcerowsecurity)
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = ANY(%s)
              AND relation.relkind = 'r'
            """,
            (list(generator.SCHEMAS),),
        ).fetchone() == (0, 0)
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_policy AS policy
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = policy.polrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = ANY(%s)
            """,
            (list(generator.SCHEMAS),),
        ).fetchone() == (0,)
        assert connection.execute(
            """
            SELECT count(*)
            FROM information_schema.table_privileges
            WHERE table_schema = ANY(%s)
              AND grantee = 'PUBLIC'
            """,
            (list(generator.SCHEMAS),),
        ).fetchone() == (0,)
        assert connection.execute(
            """
            SELECT count(*)
            FROM information_schema.routine_privileges
            WHERE specific_schema = ANY(%s)
              AND grantee = 'PUBLIC'
            """,
            (list(generator.SCHEMAS),),
        ).fetchone() == (0,)


def test_touch_and_immutable_triggers_enforce_runtime_behavior(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        _insert_valid_publication_fixture(connection)
        _set_migration_role(connection, postgresql_cluster)
        initial_updated_at, initial_lock_version = connection.execute(
            """
            SELECT updated_at, lock_version
            FROM publishing.publication
            WHERE id = '00000000-0000-0000-0000-000000000055'
            """
        ).fetchone()
        updated_at, lock_version = connection.execute(
            """
            UPDATE publishing.publication
            SET display_id = 'PUB-ST0305-TOUCHED'
            WHERE id = '00000000-0000-0000-0000-000000000055'
            RETURNING updated_at, lock_version
            """
        ).fetchone()
        assert lock_version == initial_lock_version + 1
        assert updated_at >= initial_updated_at

        with connection.transaction():
            with pytest.raises(
                psycopg.errors.ObjectNotInPrerequisiteState,
                match="RAOS immutable table mutation is forbidden",
            ) as raised:
                connection.execute(
                    """
                    UPDATE publishing.publication_snapshot
                    SET title = 'Forbidden mutation'
                    WHERE id = '00000000-0000-0000-0000-000000000054'
                    """
                )
            assert raised.value.sqlstate == "55000"


def test_finance_check_constraints_reject_invalid_values_and_profit_formula(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _migration_runner(postgresql_cluster, empty_database).upgrade()

    with postgresql_cluster.connect(empty_database) as connection:
        _insert_valid_publication_fixture(connection)
        _set_migration_role(connection, postgresql_cluster)
        with connection.transaction():
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    """
                    INSERT INTO finance.external_cost (
                        display_id, site_id, cost_type, vendor_code,
                        occurred_on, amount_original, currency_original,
                        fx_rate_to_jpy, amount_jpy, source_record_key,
                        recorded_by_actor_type
                    ) VALUES (
                        'EXT-ST0305-NEGATIVE',
                        '00000000-0000-0000-0000-000000000010',
                        'LLM', 'fixture', DATE '2026-08-01', -1, 'JPY', 1,
                        -1, 'negative', 'IMPORT'
                    )
                    """
                )

        with connection.transaction():
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    """
                    INSERT INTO finance.unit_economics_snapshot (
                        display_id, site_id, scope_type, scope_id,
                        period_month, calculation_version, status,
                        confirmed_commission_jpy, generated_commission_jpy,
                        external_cost_jpy, human_cost_jpy,
                        contribution_profit_jpy, eligible_sessions,
                        affiliate_clicks, confirmed_orders, source_watermark,
                        report_artifact_id, calculated_by_job_id, calculated_at
                    ) VALUES (
                        'UES-ST0305-BAD-FORMULA',
                        '00000000-0000-0000-0000-000000000010', 'SITE',
                        '00000000-0000-0000-0000-000000000010',
                        DATE '2026-08-01', 'fixture-v1', 'DRAFT',
                        100, 100, 10, 20, 71, 10, 2, 1, 'fixture',
                        '00000000-0000-0000-0000-000000000053',
                        '00000000-0000-0000-0000-000000000052',
                        TIMESTAMPTZ '2026-08-05 00:08:00+00'
                    )
                    """
                )


def test_nonempty_downgrade_is_atomic_then_supports_full_roundtrip(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    assert instance.upgrade().current_revision == catalog.HEAD_REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            """
            INSERT INTO ops.object_artifact (
                id, display_id, artifact_kind, bucket_name, object_key,
                content_type, byte_size, sha256, encryption_state,
                retention_class, source_system
            ) VALUES (
                '00000000-0000-0000-0000-000000000060',
                'ART-ST0305-PARSER', 'other', 'fixture',
                'finance/parser.json', 'application/json', 2,
                repeat('6', 64), 'LOCAL_DEV', 'TEST', 'ST0305_FIXTURE'
            );
            INSERT INTO finance.parser_version (
                id, provider_code, format_code, version, code_sha256,
                schema_artifact_id, status, released_at
            ) VALUES (
                '00000000-0000-0000-0000-000000000061', 'fixture', 'csv',
                '1.0.0', repeat('7', 64),
                '00000000-0000-0000-0000-000000000060', 'ACTIVE',
                TIMESTAMPTZ '2026-08-05 00:00:00+00'
            )
            """
        )

    with pytest.raises(runner.MigrationError) as raised:
        instance.downgrade()
    assert raised.value.code is runner.MigrationErrorCode.MIGRATION_FAILED

    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.raos_migration_version"
        ).fetchone() == (catalog.HEAD_REVISION,)
        assert connection.execute(
            "SELECT count(*) FROM finance.parser_version"
        ).fetchone() == (1,)
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = ANY(%s)
              AND relation.relkind = 'r'
            """,
            (list(generator.SCHEMAS),),
        ).fetchone() == (39,)
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_proc AS routine
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = routine.pronamespace
            WHERE namespace.nspname = ANY(%s)
            """,
            (list(generator.SCHEMAS),),
        ).fetchone() == (3,)
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_trigger AS trigger_record
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = trigger_record.tgrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = ANY(%s)
              AND trigger_record.tgisinternal IS FALSE
            """,
            (list(generator.SCHEMAS),),
        ).fetchone() == (17,)
        connection.execute("DELETE FROM finance.parser_version")

    assert instance.downgrade().current_revision == catalog.DOMAIN_REVISION
    assert instance.upgrade().current_revision == catalog.HEAD_REVISION
    assert instance.status().current_revision == catalog.HEAD_REVISION


def test_fresh_upgrade_reaches_st0305_and_derives_exact_catalog_fingerprints(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)

    result = instance.upgrade()
    assert result.current_revision == catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION
    assert result.revision_source_count == 5
    assert instance.status().current_revision == catalog.HEAD_REVISION

    engine = runner._default_engine_factory(postgresql_cluster.target(empty_database))
    try:
        with engine.connect() as connection:
            fingerprints = runner._selected_domain_catalog_digests(
                connection, runner.ST0305_SCHEMAS
            )
    finally:
        engine.dispose()

    assert fingerprints == {
        kind: (int(value["count"]), str(value["digest"]))
        for kind, value in generator.CATALOG_FINGERPRINTS.items()
    }
    with postgresql_cluster.connect(empty_database) as connection:
        assert _execute_validation(connection, postgresql_cluster) == [
            ("PASS", 39, 629, 150, 17)
        ]


def test_predecessor_upgrade_and_exact_foreign_key_boundaries(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    assert instance.upgrade().current_revision == catalog.HEAD_REVISION
    assert instance.downgrade().current_revision == catalog.DOMAIN_REVISION

    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT to_regnamespace('publishing'), to_regnamespace('finance')"
        ).fetchone() == (None, None)

    result = instance.upgrade()
    assert result.current_revision == catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION
    with postgresql_cluster.connect(empty_database) as connection:
        constraint_shape = connection.execute(
            """
            SELECT count(*) FILTER (WHERE constraint_record.contype = 'f'),
                   count(*) FILTER (
                       WHERE constraint_record.contype = 'f'
                         AND constraint_record.condeferrable IS TRUE
                         AND constraint_record.condeferred IS TRUE
                   )
            FROM pg_catalog.pg_constraint AS constraint_record
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = constraint_record.connamespace
            WHERE namespace.nspname = ANY(%s)
            """,
            (list(generator.SCHEMAS),),
        ).fetchone()
        assert constraint_shape == (150, 4)
        assert (
            connection.execute(
                """
            SELECT conname
            FROM pg_catalog.pg_constraint
            WHERE conname = ANY(%s)
            ORDER BY conname
            """,
                (sorted(generator.DEFERRED_FOREIGN_KEYS),),
            ).fetchall()
            == []
        )
        assert connection.execute(
            """
            SELECT conname
            FROM pg_catalog.pg_constraint
            WHERE conname = ANY(%s)
              AND condeferrable IS TRUE AND condeferred IS TRUE
            ORDER BY conname
            """,
            (sorted(generator.CYCLIC_FOREIGN_KEYS),),
        ).fetchall() == [(name,) for name in sorted(generator.CYCLIC_FOREIGN_KEYS)]
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_trigger AS trigger_record
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = trigger_record.tgrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname IN ('iam', 'ops')
              AND trigger_record.tgisinternal IS TRUE
            """
        ).fetchone() == (300,)
        assert _execute_validation(connection, postgresql_cluster) == [
            ("PASS", 39, 629, 150, 17)
        ]


@pytest.mark.parametrize(
    "mutation",
    (
        """
        ALTER TABLE finance.commission
        DROP CONSTRAINT ck_finance_commission_status;
        ALTER TABLE finance.commission
        ADD CONSTRAINT ck_finance_commission_status CHECK (status IS NOT NULL)
        """,
        """
        ALTER TABLE freshness.refresh_schedule
        DROP CONSTRAINT fk_freshness_refresh_schedule_freshness_policy_id;
        ALTER TABLE freshness.refresh_schedule
        ADD CONSTRAINT fk_freshness_refresh_schedule_freshness_policy_id
        FOREIGN KEY (freshness_policy_id)
        REFERENCES freshness.freshness_policy(id) ON DELETE CASCADE
        """,
        """
        DROP INDEX freshness.ix_freshness_schedule_due;
        CREATE INDEX ix_freshness_schedule_due
        ON freshness.refresh_schedule USING btree (next_due_at)
        WHERE status = 'ACTIVE'
        """,
        """
        CREATE OR REPLACE FUNCTION publishing.guard_final_approval()
        RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
        SET search_path TO pg_catalog
        AS $drift$ BEGIN RETURN NEW; END $drift$
        """,
        "ALTER TABLE finance.commission SET (fillfactor = 80)",
        "COMMENT ON COLUMN finance.commission.status IS 'semantic drift'",
        """
        DROP TRIGGER trg_publishing_review_assignment_touch
        ON publishing.review_assignment;
        CREATE TRIGGER trg_publishing_review_assignment_touch
        BEFORE DELETE OR UPDATE ON publishing.review_assignment
        FOR EACH ROW EXECUTE FUNCTION ops.touch_mutable_row()
        """,
    ),
    ids=(
        "check",
        "foreign-key",
        "index",
        "function",
        "relation",
        "column",
        "trigger",
    ),
)
def test_catalog_fingerprints_reject_semantic_definition_drift(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    mutation: str,
) -> None:
    instance = _migration_runner(postgresql_cluster, empty_database)
    instance.upgrade()
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            sql.SQL("SET ROLE {}").format(
                sql.Identifier(postgresql_cluster.migration_user)
            )
        )
        connection.execute(mutation)
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="ST0305_CATALOG_FINGERPRINT_MISMATCH",
        ):
            _execute_validation(connection, postgresql_cluster)

    with pytest.raises(runner.MigrationError) as raised:
        instance.status()
    assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID
