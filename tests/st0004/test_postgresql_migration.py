"""Live baseline -> ST-0002 -> ST-0003 -> ST-0004 PostgreSQL proofs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import apply_sql, upgrade_st0002


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ST0003_ROOT = REPOSITORY_ROOT / "changes" / "st-0003" / "database"
ST0004_ROOT = REPOSITORY_ROOT / "changes" / "st-0004" / "database"
ST0003_FORWARD = tuple(
    ST0003_ROOT / name
    for name in (
        "202607300007_ai_governance_expand.sql",
        "202607300008_ai_governance_expand_validate.sql",
        "202607300009_ai_governance_migrate_batch.sql",
        "202607300010_ai_governance_contract_prepare.sql",
        "202607300011_ai_governance_contract.sql",
    )
)
ST0004_FORWARD = tuple(
    ST0004_ROOT / name
    for name in (
        "202607300013_content_expand.sql",
        "202607300014_content_expand_validate.sql",
        "202607300015_content_migrate_batch.sql",
        "202607300016_content_contract_prepare.sql",
        "202607300017_content_contract.sql",
    )
)
ST0004_DOWNGRADE = ST0004_ROOT / "202607300018_content_guarded_downgrade.sql"
CONTENT_TABLES = (
    "editorial.content_schema_version",
    "editorial.article_type_version",
    "editorial.article_template_version",
    "editorial.editorial_methodology_version",
    "editorial.article_methodology_binding",
    "editorial.seo_metadata_version",
    "editorial.structured_data_manifest",
    "editorial.media_asset",
    "evidence.first_hand_experience_record",
    "evidence.first_hand_experience_asset",
    "editorial.article_disclosure_context",
)


def upgrade_st0003(cluster: Any, database: str) -> None:
    apply_sql(cluster, database, *ST0003_FORWARD[:2])
    apply_sql(cluster, database, ST0003_FORWARD[2])
    apply_sql(cluster, database, *ST0003_FORWARD[3:])


def upgrade_st0004(cluster: Any, database: str) -> None:
    apply_sql(cluster, database, *ST0004_FORWARD[:2])
    apply_sql(cluster, database, ST0004_FORWARD[2])
    apply_sql(cluster, database, *ST0004_FORWARD[3:])


def relation_exists(cluster: Any, database: str, relation: str) -> bool:
    return cluster.query(
        database,
        f"SELECT to_regclass('{relation}') IS NOT NULL;",
    ) == "t"


def assert_psql_fails(
    cluster: Any,
    database: str,
    statement: str,
    *,
    expected: str,
) -> None:
    result = cluster.psql(database, statement, check=False)
    assert result.returncode != 0, "statement unexpectedly succeeded"
    assert expected.casefold() in result.stderr.casefold(), result.stderr


def test_full_predecessor_chain_then_st0004_creates_exact_content_lifecycle(
    st0004_postgresql_cluster: Any, st0004_database: str
) -> None:
    cluster = st0004_postgresql_cluster
    database = st0004_database
    assert not relation_exists(cluster, database, "ai.evaluation_run")
    assert not relation_exists(cluster, database, CONTENT_TABLES[0])
    upgrade_st0002(cluster, database)
    assert relation_exists(cluster, database, "ops.job")
    assert not relation_exists(cluster, database, "ai.evaluation_run")
    upgrade_st0003(cluster, database)
    assert relation_exists(cluster, database, "ai.evaluation_run")
    assert not relation_exists(cluster, database, CONTENT_TABLES[0])
    upgrade_st0004(cluster, database)
    assert all(relation_exists(cluster, database, table) for table in CONTENT_TABLES)
    assert cluster.query(
        database,
        """
        SELECT count(*)
          FROM information_schema.columns
         WHERE table_schema = 'editorial'
           AND table_name = 'article_version'
           AND column_name IN (
             'content_schema_version_id', 'article_type_version_id',
             'article_template_version_id', 'seo_metadata_version_id'
           );
        """,
    ) == "4"


def test_live_constraints_encode_version_approval_hash_and_immutability_rules(
    st0004_postgresql_cluster: Any, st0004_database: str
) -> None:
    cluster = st0004_postgresql_cluster
    database = st0004_database
    upgrade_st0002(cluster, database)
    upgrade_st0003(cluster, database)
    upgrade_st0004(cluster, database)
    assert cluster.query(
        database,
        """
        SELECT count(*)
          FROM information_schema.columns
         WHERE (table_schema, table_name, column_name) IN (
            ('editorial', 'media_asset', 'source_id'),
            ('editorial', 'media_asset', 'raw_artifact_id'),
            ('editorial', 'article_methodology_binding', 'bound_by_principal_id')
         )
           AND is_nullable = 'NO';
        """,
    ) == "3"
    constraint_text = cluster.query(
        database,
        """
        SELECT string_agg(pg_get_constraintdef(c.oid), E'\n' ORDER BY c.conname)
          FROM pg_constraint c
          JOIN pg_class r ON r.oid = c.conrelid
          JOIN pg_namespace n ON n.oid = r.relnamespace
         WHERE (n.nspname, r.relname) IN (
           ('editorial', 'content_schema_version'),
           ('editorial', 'article_type_version'),
           ('editorial', 'article_template_version'),
           ('editorial', 'editorial_methodology_version'),
           ('editorial', 'seo_metadata_version')
         );
        """,
    ).lower()
    assert "approved_by_principal_id" in constraint_text
    assert "approved_at" in constraint_text
    assert "active" in constraint_text
    assert "sha256" in constraint_text
    trigger_count = int(
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM pg_trigger t
              JOIN pg_class r ON r.oid = t.tgrelid
              JOIN pg_namespace n ON n.oid = r.relnamespace
             WHERE NOT t.tgisinternal
               AND n.nspname IN ('editorial', 'evidence')
               AND (t.tgname ILIKE '%immutable%' OR t.tgname ILIKE '%guard%');
            """,
        )
    )
    assert trigger_count >= 1

    human = "00000000-0000-7000-8000-000000000401"
    active_type = "00000000-0000-7000-8000-000000000402"
    second_type = "00000000-0000-7000-8000-000000000403"
    service = "00000000-0000-7000-8000-000000000404"
    site = "00000000-0000-7000-8000-000000000405"
    category = "00000000-0000-7000-8000-000000000406"
    product = "00000000-0000-7000-8000-000000000407"
    reviewer = "00000000-0000-7000-8000-000000000408"
    source = "00000000-0000-7000-8000-000000000409"
    raw_artifact = "00000000-0000-7000-8000-000000000410"
    experience = "00000000-0000-7000-8000-000000000411"
    cluster.psql(
        database,
        f"""
        INSERT INTO iam.principal (
            id, display_id, principal_type, status, display_name
        ) VALUES (
            '{human}', 'PRN-ST0004-HUMAN', 'USER', 'ACTIVE',
            'ST-0004 human approver'
        ), (
            '{service}', 'PRN-ST0004-SERVICE', 'SERVICE', 'ACTIVE',
            'ST-0004 service principal'
        ), (
            '{reviewer}', 'PRN-ST0004-REVIEWER', 'USER', 'ACTIVE',
            'ST-0004 distinct reviewer'
        );
        INSERT INTO portfolio.site (
            id, display_id, site_code, name, primary_domain, brand_name
        ) VALUES (
            '{site}', 'SITE-ST0004', 'st0004', 'ST-0004 site',
            'st0004.example', 'ST-0004'
        );
        INSERT INTO portfolio.category (
            id, display_id, site_id, category_code, name, risk_class
        ) VALUES (
            '{category}', 'CAT-ST0004', '{site}', 'st0004',
            'ST-0004 category', 'LOW'
        );
        INSERT INTO catalog.canonical_product (
            id, display_id, category_id, canonical_name, product_type,
            identity_confidence
        ) VALUES (
            '{product}', 'PRD-ST0004', '{category}', 'ST-0004 product',
            'TEST_PRODUCT', 1.0
        );
        INSERT INTO evidence.source (
            id, display_id, source_type, name, authority_level, permitted_use
        ) VALUES (
            '{source}', 'SRC-ST0004', 'MANUAL_VERIFIED', 'ST-0004 source',
            'PRIMARY', 'Synthetic migration verification only'
        );
        INSERT INTO ops.object_artifact (
            id, display_id, artifact_kind, bucket_name, object_key,
            content_type, byte_size, sha256, encryption_state,
            retention_class, source_system
        ) VALUES (
            '{raw_artifact}', 'OBJ-ST0004-MEDIA', 'other', 'st0004-test',
            'media/source.bin', 'application/octet-stream', 1,
            repeat('e', 64), 'LOCAL_DEV', 'TEST', 'ST0004_TEST'
        );
        """,
    )

    assert_psql_fails(
        cluster,
        database,
        """
        SET ROLE raos_api_rw;
        INSERT INTO editorial.media_asset (
            display_id, asset_class, asset_sha256, license_status,
            modification_policy, alt_text, width, height,
            captured_or_observed_at
        ) VALUES (
            'MEDIA-ST0004-NO-PROVENANCE', 'IMAGE', repeat('e', 64), 'PENDING',
            'unaltered test capture', 'Missing provenance', 1, 1,
            CURRENT_TIMESTAMP
        );
        """,
        expected="null value",
    )

    cluster.psql(
        database,
        f"""
        SET ROLE raos_api_rw;
        INSERT INTO editorial.media_asset (
            display_id, asset_class, source_id, raw_artifact_id,
            asset_sha256, license_status,
            modification_policy, alt_text, width, height,
            captured_or_observed_at
        ) VALUES (
            'MEDIA-ST0004', 'IMAGE', '{source}', '{raw_artifact}',
            repeat('e', 64), 'PENDING',
            'unaltered test capture', 'ST-0004 media asset', 1, 1,
            CURRENT_TIMESTAMP
        );
        INSERT INTO evidence.first_hand_experience_record (
            id, display_id, product_id, product_variant_identity,
            tester_principal_id, procedure_version, started_at, ended_at,
            environment, limitations
        ) VALUES (
            '{experience}', 'FHE-ST0004-HUMAN', '{product}', '{{}}'::jsonb, '{human}',
            '1.0.0', CURRENT_TIMESTAMP - interval '1 hour', CURRENT_TIMESTAMP,
            '{{}}'::jsonb, 'Synthetic lifecycle test only'
        );
        RESET ROLE;
        """,
    )
    assert_psql_fails(
        cluster,
        database,
        f"""
        SET ROLE raos_api_rw;
        INSERT INTO evidence.first_hand_experience_record (
            display_id, product_id, product_variant_identity,
            tester_principal_id, procedure_version, started_at, ended_at,
            environment, limitations
        ) VALUES (
            'FHE-ST0004-SERVICE', '{product}', '{{}}'::jsonb, '{service}',
            '1.0.0', CURRENT_TIMESTAMP - interval '1 hour', CURRENT_TIMESTAMP,
            '{{}}'::jsonb, 'Synthetic invalid tester case'
        );
        """,
        expected="first-hand experience tester must be an ACTIVE USER",
    )
    assert_psql_fails(
        cluster,
        database,
        f"""
        SET ROLE raos_api_rw;
        INSERT INTO editorial.article_methodology_binding (
            article_version_id, methodology_version_id,
            candidate_universe_artifact_id, candidate_universe_sha256,
            bound_by_principal_id
        ) VALUES (
            '00000000-0000-7000-8000-000000000412',
            '00000000-0000-7000-8000-000000000413',
            '{raw_artifact}', repeat('e', 64), '{service}'
        );
        """,
        expected="methodology binding actor must be an ACTIVE USER",
    )
    assert_psql_fails(
        cluster,
        database,
        f"""
        SET ROLE raos_api_rw;
        UPDATE evidence.first_hand_experience_record
           SET review_status = 'REVIEWED',
               reviewed_by_principal_id = '{human}',
               reviewed_at = CURRENT_TIMESTAMP
         WHERE id = '{experience}';
        """,
        expected="experience reviewer must differ from tester",
    )
    cluster.psql(
        database,
        f"""
        SET ROLE raos_api_rw;
        UPDATE evidence.first_hand_experience_record
           SET review_status = 'REVIEWED',
               reviewed_by_principal_id = '{reviewer}',
               reviewed_at = CURRENT_TIMESTAMP
         WHERE id = '{experience}';
        UPDATE evidence.first_hand_experience_record
           SET review_status = 'APPROVED'
         WHERE id = '{experience}';
        RESET ROLE;
        """,
    )

    for signature in (
        "editorial.is_active_human_principal(uuid)",
        "editorial.content_artifact_matches_immutable_hash(uuid,text)",
    ):
        assert cluster.query(
            database,
            f"SELECT has_function_privilege('raos_api_rw', '{signature}', 'EXECUTE');",
        ) == "t"
        assert cluster.query(
            database,
            f"SELECT has_function_privilege('raos_worker_rw', '{signature}', 'EXECUTE');",
        ) == "f"

    cluster.psql(
        database,
        f"""
        SET ROLE raos_api_rw;
        INSERT INTO editorial.article_type_version (
            id, article_type_code, semantic_version, contract,
            contract_sha256
        ) VALUES (
            '{active_type}', 'comparison', '1.0.0', '{{}}'::jsonb,
            repeat('a', 64)
        );
        RESET ROLE;
        """,
    )
    assert_psql_fails(
        cluster,
        database,
        """
        SET ROLE raos_worker_rw;
        INSERT INTO editorial.article_type_version (
            article_type_code, semantic_version, contract, contract_sha256
        ) VALUES ('worker_denied', '1.0.0', '{}'::jsonb, repeat('b', 64));
        """,
        expected="permission denied",
    )
    assert_psql_fails(
        cluster,
        database,
        f"""
        SET ROLE raos_api_rw;
        INSERT INTO editorial.article_type_version (
            article_type_code, semantic_version, contract, contract_sha256,
            status, approved_by_principal_id, approved_at
        ) VALUES (
            'direct_active', '1.0.0', '{{}}'::jsonb, repeat('c', 64),
            'ACTIVE', '{human}', clock_timestamp()
        );
        """,
        expected="must be created in unapproved DRAFT",
    )
    cluster.psql(
        database,
        f"""
        SET ROLE raos_api_rw;
        UPDATE editorial.article_type_version
           SET status = 'ACTIVE',
               approved_by_principal_id = '{human}',
               approved_at = clock_timestamp()
         WHERE id = '{active_type}';
        RESET ROLE;
        """,
    )
    assert_psql_fails(
        cluster,
        database,
        f"""
        SET ROLE raos_api_rw;
        UPDATE editorial.article_type_version
           SET contract = '{{"mutated": true}}'::jsonb
         WHERE id = '{active_type}';
        """,
        expected="activated payload and approval history are immutable",
    )
    cluster.psql(
        database,
        f"""
        SET ROLE raos_api_rw;
        INSERT INTO editorial.article_type_version (
            id, article_type_code, semantic_version, contract,
            contract_sha256
        ) VALUES (
            '{second_type}', 'comparison', '2.0.0', '{{}}'::jsonb,
            repeat('d', 64)
        );
        RESET ROLE;
        """,
    )
    assert_psql_fails(
        cluster,
        database,
        f"""
        SET ROLE raos_api_rw;
        UPDATE editorial.article_type_version
           SET status = 'ACTIVE',
               approved_by_principal_id = '{human}',
               approved_at = clock_timestamp()
         WHERE id = '{second_type}';
        """,
        expected="uq_editorial_article_type_active",
    )

    assert cluster.query(
        database,
        """
        SELECT count(*)
          FROM pg_constraint
         WHERE conname IN (
           'fk_editorial_seo_article',
           'fk_editorial_article_version_seo'
         )
           AND condeferrable
           AND condeferred;
        """,
    ) == "2"
    with pytest.raises(AssertionError, match="downgrade refused"):
        apply_sql(cluster, database, ST0004_DOWNGRADE)
    assert cluster.query(
        database,
        "SELECT count(*) FROM editorial.article_type_version;",
    ) == "2"


def test_acl_has_no_public_table_grants_and_roles_receive_explicit_least_privilege(
    st0004_postgresql_cluster: Any, st0004_database: str
) -> None:
    cluster = st0004_postgresql_cluster
    database = st0004_database
    upgrade_st0002(cluster, database)
    upgrade_st0003(cluster, database)
    upgrade_st0004(cluster, database)
    assert cluster.query(
        database,
        """
        SELECT count(*)
          FROM information_schema.role_table_grants
         WHERE table_schema IN ('editorial', 'evidence')
           AND table_name IN (
             'content_schema_version', 'article_type_version',
             'article_template_version', 'editorial_methodology_version',
             'article_methodology_binding', 'seo_metadata_version',
             'structured_data_manifest', 'media_asset',
             'first_hand_experience_record', 'first_hand_experience_asset',
             'article_disclosure_context'
           )
           AND grantee = 'PUBLIC';
        """,
    ) == "0"
    grants = int(
        cluster.query(
            database,
            """
            SELECT count(*)
              FROM information_schema.role_table_grants
             WHERE table_schema IN ('editorial', 'evidence')
               AND grantee IN ('raos_api_rw', 'raos_worker_rw', 'raos_reporting_ro')
               AND table_name IN (
                 'content_schema_version', 'article_type_version',
                 'article_template_version', 'editorial_methodology_version',
                 'article_methodology_binding', 'seo_metadata_version',
                 'structured_data_manifest', 'media_asset',
                 'first_hand_experience_record', 'first_hand_experience_asset',
                 'article_disclosure_context'
               );
            """,
        )
    )
    assert grants > 0
    assert cluster.query(
        database,
        """
        SELECT bool_and(c.relrowsecurity AND c.relforcerowsecurity)
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname IN ('editorial', 'evidence')
           AND c.relname IN (
             'content_schema_version', 'article_type_version',
             'article_template_version', 'editorial_methodology_version',
             'article_methodology_binding', 'seo_metadata_version',
             'structured_data_manifest', 'media_asset',
             'first_hand_experience_record', 'first_hand_experience_asset',
             'article_disclosure_context'
           );
        """,
    ) == "t"


def test_guarded_empty_downgrade_removes_only_st0004_then_forward_recovers(
    st0004_postgresql_cluster: Any, st0004_database: str
) -> None:
    cluster = st0004_postgresql_cluster
    database = st0004_database
    upgrade_st0002(cluster, database)
    upgrade_st0003(cluster, database)
    upgrade_st0004(cluster, database)
    apply_sql(cluster, database, ST0004_DOWNGRADE)
    assert all(not relation_exists(cluster, database, table) for table in CONTENT_TABLES)
    assert relation_exists(cluster, database, "ai.evaluation_run")
    assert relation_exists(cluster, database, "ops.job")
    assert cluster.query(
        database,
        """
        SELECT count(*)
          FROM information_schema.columns
         WHERE table_schema = 'editorial'
           AND table_name = 'article_version'
           AND column_name IN (
             'content_schema_version_id', 'article_type_version_id',
             'article_template_version_id', 'seo_metadata_version_id'
           );
        """,
    ) == "0"
    upgrade_st0004(cluster, database)
    assert all(relation_exists(cluster, database, table) for table in CONTENT_TABLES)


def test_expand_checkpoint_replay_is_rejected_instead_of_silently_skipped(
    st0004_postgresql_cluster: Any, st0004_database: str
) -> None:
    cluster = st0004_postgresql_cluster
    database = st0004_database
    upgrade_st0002(cluster, database)
    upgrade_st0003(cluster, database)
    apply_sql(cluster, database, ST0004_FORWARD[0])
    with pytest.raises(Exception, match="already exists|duplicate|checkpoint|migration"):
        apply_sql(cluster, database, ST0004_FORWARD[0])
