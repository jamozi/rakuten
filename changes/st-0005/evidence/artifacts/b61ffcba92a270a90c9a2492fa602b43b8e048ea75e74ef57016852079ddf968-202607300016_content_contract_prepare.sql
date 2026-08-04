-- ST-0004 / INT-DEC-005 / INT-DEC-006
-- Phase: CONTRACT PREPARE
-- Requires canonical writers, operator-reviewed four-column bindings, and
-- 202607300015_content_migrate_batch.sql reporting remaining_rows = 0.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '10min';

DO $$
DECLARE
    binding_column text;
    content_table text;
    expected record;
    relation_name text;
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0004 requires PostgreSQL 18 or later';
    END IF;

    FOREACH relation_name IN ARRAY ARRAY[
        'editorial.content_schema_version',
        'editorial.article_type_version',
        'editorial.article_template_version',
        'editorial.editorial_methodology_version',
        'editorial.article_methodology_binding',
        'editorial.seo_metadata_version',
        'editorial.structured_data_manifest',
        'editorial.media_asset',
        'evidence.first_hand_experience_record',
        'evidence.first_hand_experience_asset',
        'editorial.article_disclosure_context'
    ]
    LOOP
        IF to_regclass(relation_name) IS NULL THEN
            RAISE EXCEPTION 'ST-0004 required relation % is missing',
                relation_name;
        END IF;
    END LOOP;

    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE conrelid = 'editorial.article_version'::regclass
           AND conname IN (
                'fk_editorial_article_version_content_schema_st0004_expand',
                'fk_editorial_article_version_article_type_st0004_expand',
                'fk_editorial_article_version_article_template_st0004_expand',
                'fk_editorial_article_version_seo_st0004_expand'
           )
           AND contype = 'f'
           AND convalidated
    ) <> 4 THEN
        RAISE EXCEPTION
            'ST-0004 Contract prepare requires four validated Expand foreign keys';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'editorial.article_version'::regclass
           AND conname =
               'fk_editorial_article_version_seo_st0004_expand'
           AND condeferrable
           AND condeferred
    ) OR NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'editorial.seo_metadata_version'::regclass
           AND conname = 'fk_editorial_seo_article'
           AND condeferrable
           AND condeferred
    ) THEN
        RAISE EXCEPTION
            'ST-0004 SEO/article cycle must remain initially deferred';
    END IF;

    FOREACH binding_column IN ARRAY ARRAY[
        'content_schema_version_id',
        'article_type_version_id',
        'article_template_version_id',
        'seo_metadata_version_id'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = 'editorial'
               AND table_name = 'article_version'
               AND column_name = binding_column
               AND data_type = 'uuid'
               AND is_nullable = 'YES'
        ) THEN
            RAISE EXCEPTION 'ST-0004 binding column % is missing or drifted',
                binding_column;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1
          FROM editorial.article_version
         WHERE content_schema_version_id IS NULL
            OR article_type_version_id IS NULL
            OR article_template_version_id IS NULL
            OR seo_metadata_version_id IS NULL
    ) THEN
        RAISE EXCEPTION
            'ST-0004 Contract prepare blocked: four-column operator binding backlog remains';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM editorial.article_version AS article
          JOIN editorial.article_template_version AS template
            ON template.id = article.article_template_version_id
         WHERE template.article_type_version_id IS DISTINCT FROM
               article.article_type_version_id
    ) OR EXISTS (
        SELECT 1
          FROM editorial.article_methodology_binding AS binding
          JOIN editorial.article_version AS article
            ON article.id = binding.article_version_id
          JOIN editorial.editorial_methodology_version AS methodology
            ON methodology.id = binding.methodology_version_id
         WHERE methodology.article_type_version_id IS DISTINCT FROM
               article.article_type_version_id
    ) OR EXISTS (
        SELECT 1
          FROM editorial.article_version AS article
          JOIN editorial.content_schema_version AS schema_version
            ON schema_version.id = article.content_schema_version_id
          JOIN editorial.article_type_version AS article_type
            ON article_type.id = article.article_type_version_id
          JOIN editorial.article_template_version AS template
            ON template.id = article.article_template_version_id
          JOIN editorial.seo_metadata_version AS seo
            ON seo.id = article.seo_metadata_version_id
           AND seo.article_version_id = article.id
         WHERE article.status = 'APPROVED'
           AND (
                schema_version.status <> 'ACTIVE'
                OR article_type.status <> 'ACTIVE'
                OR template.status <> 'ACTIVE'
                OR seo.status <> 'APPROVED'
                OR NOT EXISTS (
                    SELECT 1
                      FROM editorial.article_methodology_binding AS binding
                      JOIN editorial.editorial_methodology_version AS methodology
                        ON methodology.id = binding.methodology_version_id
                     WHERE binding.article_version_id = article.id
                       AND methodology.status = 'ACTIVE'
                       AND methodology.article_type_version_id = article.article_type_version_id
                )
           )
    ) THEN
        RAISE EXCEPTION
            'ST-0004 cross-binding or approved-article readiness drift detected';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM editorial.content_schema_version
         WHERE editorial.content_artifact_matches_immutable_hash(
                   artifact_id, schema_sha256
               ) IS DISTINCT FROM true
    ) OR EXISTS (
        SELECT 1
          FROM editorial.article_methodology_binding
         WHERE editorial.content_artifact_matches_immutable_hash(
                   candidate_universe_artifact_id,
                   candidate_universe_sha256
               ) IS DISTINCT FROM true
    ) OR EXISTS (
        SELECT 1
          FROM editorial.structured_data_manifest
         WHERE editorial.content_artifact_matches_immutable_hash(
                   jsonld_artifact_id, jsonld_sha256
               ) IS DISTINCT FROM true
    ) OR EXISTS (
        SELECT 1
          FROM editorial.media_asset
         WHERE raw_artifact_id IS NOT NULL
           AND editorial.content_artifact_matches_immutable_hash(
                   raw_artifact_id, asset_sha256
               ) IS DISTINCT FROM true
    ) OR EXISTS (
        SELECT 1
          FROM editorial.media_asset AS media
         WHERE long_description_artifact_id IS NOT NULL
           AND NOT EXISTS (
                SELECT 1
                  FROM ops.object_artifact AS artifact
                 WHERE artifact.id = media.long_description_artifact_id
                   AND artifact.is_immutable
           )
    ) OR EXISTS (
        SELECT 1
          FROM evidence.first_hand_experience_asset
         WHERE editorial.content_artifact_matches_immutable_hash(
                   artifact_id, artifact_sha256
               ) IS DISTINCT FROM true
    ) THEN
        RAISE EXCEPTION
            'ST-0004 immutable artifact/hash readiness drift detected';
    END IF;

    IF EXISTS (
        SELECT approved_by_principal_id
          FROM editorial.content_schema_version WHERE status = 'ACTIVE'
        UNION ALL
        SELECT approved_by_principal_id
          FROM editorial.article_type_version WHERE status = 'ACTIVE'
        UNION ALL
        SELECT approved_by_principal_id
          FROM editorial.article_template_version WHERE status = 'ACTIVE'
        UNION ALL
        SELECT approved_by_principal_id
          FROM editorial.editorial_methodology_version WHERE status = 'ACTIVE'
        UNION ALL
        SELECT approved_by_principal_id
          FROM editorial.seo_metadata_version WHERE status = 'APPROVED'
        UNION ALL
        SELECT approved_by_principal_id
          FROM editorial.media_asset WHERE status = 'APPROVED'
    ) AND EXISTS (
        SELECT 1
          FROM (
            SELECT approved_by_principal_id AS principal_id
              FROM editorial.content_schema_version WHERE status = 'ACTIVE'
            UNION ALL
            SELECT approved_by_principal_id
              FROM editorial.article_type_version WHERE status = 'ACTIVE'
            UNION ALL
            SELECT approved_by_principal_id
              FROM editorial.article_template_version WHERE status = 'ACTIVE'
            UNION ALL
            SELECT approved_by_principal_id
              FROM editorial.editorial_methodology_version WHERE status = 'ACTIVE'
            UNION ALL
            SELECT approved_by_principal_id
              FROM editorial.seo_metadata_version WHERE status = 'APPROVED'
            UNION ALL
            SELECT approved_by_principal_id
              FROM editorial.media_asset WHERE status = 'APPROVED'
          ) AS approval
         WHERE editorial.is_active_human_principal(approval.principal_id)
               IS DISTINCT FROM true
    ) THEN
        RAISE EXCEPTION
            'ST-0004 active/approved content lacks an ACTIVE USER approval';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM evidence.first_hand_experience_record AS experience
         WHERE editorial.is_active_human_principal(
                   experience.tester_principal_id
               ) IS DISTINCT FROM true
            OR (
                experience.review_status <> 'DRAFT'
                AND editorial.is_active_human_principal(
                    experience.reviewed_by_principal_id
                ) IS DISTINCT FROM true
            )
            OR (
                experience.review_status IN ('REVIEWED', 'APPROVED')
                AND experience.reviewed_by_principal_id
                    = experience.tester_principal_id
            )
    ) OR EXISTS (
        SELECT 1
          FROM editorial.article_disclosure_context AS disclosure
         WHERE disclosure.reviewed_by_principal_id IS NOT NULL
           AND editorial.is_active_human_principal(
                   disclosure.reviewed_by_principal_id
               ) IS DISTINCT FROM true
    ) OR EXISTS (
        SELECT 1
          FROM editorial.article_methodology_binding AS binding
         WHERE editorial.is_active_human_principal(
                   binding.bound_by_principal_id
               ) IS DISTINCT FROM true
    ) THEN
        RAISE EXCEPTION 'ST-0004 human provenance readiness drift detected';
    END IF;

    FOR expected IN
        SELECT *
          FROM (VALUES
            ('editorial.content_schema_version', 'trg_editorial_content_schema_lifecycle', 'editorial.guard_versioned_content_mutation()', 31),
            ('editorial.article_type_version', 'trg_editorial_article_type_lifecycle', 'editorial.guard_versioned_content_mutation()', 31),
            ('editorial.article_template_version', 'trg_editorial_article_template_lifecycle', 'editorial.guard_versioned_content_mutation()', 31),
            ('editorial.editorial_methodology_version', 'trg_editorial_methodology_lifecycle', 'editorial.guard_versioned_content_mutation()', 31),
            ('editorial.seo_metadata_version', 'trg_editorial_seo_metadata_lifecycle', 'editorial.guard_seo_metadata_mutation()', 31),
            ('editorial.media_asset', 'trg_editorial_media_asset_lifecycle', 'editorial.guard_media_asset_mutation()', 31),
            ('evidence.first_hand_experience_record', 'trg_evidence_first_hand_lifecycle', 'evidence.guard_first_hand_experience_mutation()', 31),
            ('editorial.article_disclosure_context', 'trg_editorial_disclosure_lifecycle', 'editorial.guard_disclosure_context_mutation()', 31),
            ('editorial.content_schema_version', 'trg_editorial_content_schema_artifact', 'editorial.guard_content_artifact_binding()', 23),
            ('editorial.article_methodology_binding', 'trg_editorial_article_methodology_artifact', 'editorial.guard_content_artifact_binding()', 23),
            ('editorial.structured_data_manifest', 'trg_editorial_structured_data_artifact', 'editorial.guard_content_artifact_binding()', 23),
            ('editorial.media_asset', 'trg_editorial_media_asset_artifact', 'editorial.guard_content_artifact_binding()', 23),
            ('evidence.first_hand_experience_asset', 'trg_evidence_first_hand_asset_artifact', 'editorial.guard_content_artifact_binding()', 23),
            ('editorial.article_methodology_binding', 'trg_editorial_article_methodology_cross_binding', 'editorial.guard_article_methodology_binding()', 23),
            ('editorial.article_version', 'trg_editorial_article_content_bindings', 'editorial.guard_article_content_bindings()', 23),
            ('editorial.article_methodology_binding', 'trg_editorial_article_methodology_immutable', 'ops.reject_immutable_mutation()', 27),
            ('editorial.structured_data_manifest', 'trg_editorial_structured_data_immutable', 'ops.reject_immutable_mutation()', 27),
            ('evidence.first_hand_experience_asset', 'trg_evidence_first_hand_asset_immutable', 'ops.reject_immutable_mutation()', 27)
          ) AS value(
            table_name,
            trigger_name,
            function_name,
            trigger_type
          )
    LOOP
        IF NOT EXISTS (
            SELECT 1
              FROM pg_trigger
             WHERE tgrelid = to_regclass(expected.table_name)
               AND tgname = expected.trigger_name
               AND tgfoid = to_regprocedure(expected.function_name)
               AND tgtype = expected.trigger_type
               AND tgenabled = 'O'
               AND NOT tgisinternal
        ) THEN
            RAISE EXCEPTION 'ST-0004 trigger % is missing or drifted',
                expected.trigger_name;
        END IF;
    END LOOP;

    IF to_regprocedure('editorial.is_active_human_principal(uuid)') IS NULL
       OR to_regprocedure(
            'editorial.content_artifact_matches_immutable_hash(uuid,text)'
          ) IS NULL THEN
        RAISE EXCEPTION 'ST-0004 required integrity helpers are missing';
    END IF;
    IF NOT has_function_privilege(
           'raos_api_rw',
           'editorial.is_active_human_principal(uuid)',
           'EXECUTE'
       ) OR NOT has_function_privilege(
           'raos_api_rw',
           'editorial.content_artifact_matches_immutable_hash(uuid,text)',
           'EXECUTE'
       ) OR has_function_privilege(
           'raos_worker_rw',
           'editorial.is_active_human_principal(uuid)',
           'EXECUTE'
       ) OR has_function_privilege(
           'raos_worker_rw',
           'editorial.content_artifact_matches_immutable_hash(uuid,text)',
           'EXECUTE'
       ) THEN
        RAISE EXCEPTION
            'ST-0004 integrity helper execution grants are drifted';
    END IF;

    IF (
        SELECT count(*)
          FROM pg_class AS index_class
          JOIN pg_namespace AS namespace
            ON namespace.oid = index_class.relnamespace
          JOIN pg_index AS index_data
            ON index_data.indexrelid = index_class.oid
         WHERE namespace.nspname IN ('editorial', 'evidence')
           AND index_class.relname LIKE '%\_st0004' ESCAPE '\'
           AND index_data.indisvalid
           AND index_data.indisready
    ) <> 29 THEN
        RAISE EXCEPTION
            'ST-0004 requires exactly 29 valid, ready Expand indexes';
    END IF;

    FOR expected IN
        SELECT *
          FROM (VALUES
            ('editorial.uq_editorial_content_schema_active_st0004', 'CREATE UNIQUE INDEX uq_editorial_content_schema_active_st0004 ON editorial.content_schema_version USING btree (schema_code) WHERE (status = ''ACTIVE''::text)'),
            ('editorial.uq_editorial_article_type_active_st0004', 'CREATE UNIQUE INDEX uq_editorial_article_type_active_st0004 ON editorial.article_type_version USING btree (article_type_code) WHERE (status = ''ACTIVE''::text)'),
            ('editorial.uq_editorial_methodology_active_st0004', 'CREATE UNIQUE INDEX uq_editorial_methodology_active_st0004 ON editorial.editorial_methodology_version USING btree (methodology_code) WHERE (status = ''ACTIVE''::text)'),
            ('editorial.ix_editorial_media_asset_status_st0004', 'CREATE INDEX ix_editorial_media_asset_status_st0004 ON editorial.media_asset USING btree (status, created_at DESC)'),
            ('evidence.ix_evidence_first_hand_product_st0004', 'CREATE INDEX ix_evidence_first_hand_product_st0004 ON evidence.first_hand_experience_record USING btree (product_id, ended_at DESC)')
          ) AS value(index_name, definition)
    LOOP
        IF NOT EXISTS (
            SELECT 1
              FROM pg_index
             WHERE indexrelid = to_regclass(expected.index_name)
               AND indisvalid
               AND indisready
               AND pg_get_indexdef(indexrelid) = expected.definition
        ) THEN
            RAISE EXCEPTION
                'ST-0004 core index % is missing or definition-drifted',
                expected.index_name;
        END IF;
    END LOOP;

    FOR expected IN
        SELECT *
          FROM (VALUES
            ('editorial.article_version', 'fk_editorial_article_version_content_schema_st0004_expand', 'editorial.ix_editorial_article_version_content_schema_st0004'),
            ('editorial.article_version', 'fk_editorial_article_version_article_type_st0004_expand', 'editorial.ix_editorial_article_version_article_type_st0004'),
            ('editorial.article_version', 'fk_editorial_article_version_article_template_st0004_expand', 'editorial.ix_editorial_article_version_article_template_st0004'),
            ('editorial.article_version', 'fk_editorial_article_version_seo_st0004_expand', 'editorial.ix_editorial_article_version_seo_st0004'),
            ('editorial.content_schema_version', 'fk_editorial_content_schema_artifact', 'editorial.ix_editorial_content_schema_artifact_st0004'),
            ('editorial.content_schema_version', 'fk_editorial_content_schema_approver', 'editorial.ix_editorial_content_schema_approver_st0004'),
            ('editorial.article_type_version', 'fk_editorial_article_type_approver', 'editorial.ix_editorial_article_type_approver_st0004'),
            ('editorial.article_template_version', 'fk_editorial_article_template_approver', 'editorial.ix_editorial_article_template_approver_st0004'),
            ('editorial.editorial_methodology_version', 'fk_editorial_methodology_article_type', 'editorial.ix_editorial_methodology_article_type_st0004'),
            ('editorial.editorial_methodology_version', 'fk_editorial_methodology_approver', 'editorial.ix_editorial_methodology_approver_st0004'),
            ('editorial.article_methodology_binding', 'fk_editorial_article_methodology_version', 'editorial.ix_editorial_article_methodology_version_st0004'),
            ('editorial.article_methodology_binding', 'fk_editorial_article_methodology_candidate', 'editorial.ix_editorial_article_methodology_candidate_st0004'),
            ('editorial.article_methodology_binding', 'fk_editorial_article_methodology_binder', 'editorial.ix_editorial_article_methodology_binder_st0004'),
            ('editorial.seo_metadata_version', 'fk_editorial_seo_approver', 'editorial.ix_editorial_seo_approver_st0004'),
            ('editorial.structured_data_manifest', 'fk_editorial_structured_data_seo_article', 'editorial.ix_editorial_structured_data_seo_st0004'),
            ('editorial.structured_data_manifest', 'fk_editorial_structured_data_jsonld_artifact', 'editorial.ix_editorial_structured_data_jsonld_st0004'),
            ('editorial.media_asset', 'fk_editorial_media_asset_source', 'editorial.ix_editorial_media_asset_source_st0004'),
            ('editorial.media_asset', 'fk_editorial_media_asset_raw', 'editorial.ix_editorial_media_asset_raw_st0004'),
            ('editorial.media_asset', 'fk_editorial_media_asset_long_description', 'editorial.ix_editorial_media_asset_long_description_st0004'),
            ('editorial.media_asset', 'fk_editorial_media_asset_approver', 'editorial.ix_editorial_media_asset_approver_st0004'),
            ('evidence.first_hand_experience_record', 'fk_evidence_first_hand_product', 'evidence.ix_evidence_first_hand_product_st0004'),
            ('evidence.first_hand_experience_record', 'fk_evidence_first_hand_tester', 'evidence.ix_evidence_first_hand_tester_st0004'),
            ('evidence.first_hand_experience_record', 'fk_evidence_first_hand_reviewer', 'evidence.ix_evidence_first_hand_reviewer_st0004'),
            ('evidence.first_hand_experience_asset', 'fk_evidence_first_hand_asset_artifact', 'evidence.ix_evidence_first_hand_asset_artifact_st0004'),
            ('editorial.article_disclosure_context', 'fk_editorial_article_disclosure_reviewer', 'editorial.ix_editorial_article_disclosure_reviewer_st0004')
          ) AS value(table_name, constraint_name, index_name)
    LOOP
        IF NOT EXISTS (
            SELECT 1
              FROM pg_constraint AS constraint_data
              JOIN pg_index AS index_data
                ON index_data.indexrelid = to_regclass(expected.index_name)
             WHERE constraint_data.conrelid = to_regclass(expected.table_name)
               AND constraint_data.conname = expected.constraint_name
               AND constraint_data.contype = 'f'
               AND index_data.indrelid = constraint_data.conrelid
               AND index_data.indisvalid
               AND index_data.indisready
               AND NOT index_data.indisunique
               AND index_data.indpred IS NULL
               AND index_data.indnkeyatts >= cardinality(constraint_data.conkey)
               AND ARRAY(
                    SELECT key.attnum
                      FROM unnest(index_data.indkey::smallint[])
                           WITH ORDINALITY AS key(attnum, position)
                     WHERE key.position <= cardinality(constraint_data.conkey)
                     ORDER BY key.position
               ) = constraint_data.conkey
        ) THEN
            RAISE EXCEPTION
                'ST-0004 FK index % is missing, invalid, or leading-key drifted',
                expected.index_name;
        END IF;
    END LOOP;

    IF EXISTS (
        WITH target_relation(relation_id) AS (
            VALUES
              ('editorial.content_schema_version'::regclass),
              ('editorial.article_type_version'::regclass),
              ('editorial.article_template_version'::regclass),
              ('editorial.editorial_methodology_version'::regclass),
              ('editorial.article_methodology_binding'::regclass),
              ('editorial.seo_metadata_version'::regclass),
              ('editorial.structured_data_manifest'::regclass),
              ('editorial.media_asset'::regclass),
              ('evidence.first_hand_experience_record'::regclass),
              ('evidence.first_hand_experience_asset'::regclass),
              ('editorial.article_disclosure_context'::regclass)
        ),
        target_fk AS (
            SELECT constraint_data.*
              FROM pg_constraint AS constraint_data
             WHERE constraint_data.contype = 'f'
               AND (
                    constraint_data.conrelid IN (
                        SELECT relation_id FROM target_relation
                    )
                    OR (
                        constraint_data.conrelid =
                            'editorial.article_version'::regclass
                        AND constraint_data.conname LIKE
                            'fk_editorial_article_version_%_st0004_expand'
                    )
               )
        )
        SELECT 1
          FROM target_fk
         WHERE NOT EXISTS (
            SELECT 1
              FROM pg_index AS index_data
             WHERE index_data.indrelid = target_fk.conrelid
               AND index_data.indisvalid
               AND index_data.indisready
               AND index_data.indpred IS NULL
               AND index_data.indnkeyatts >= cardinality(target_fk.conkey)
               AND ARRAY(
                    SELECT key.attnum
                      FROM unnest(index_data.indkey::smallint[])
                           WITH ORDINALITY AS key(attnum, position)
                     WHERE key.position <= cardinality(target_fk.conkey)
                     ORDER BY key.position
               ) = target_fk.conkey
         )
    ) THEN
        RAISE EXCEPTION 'ST-0004 has a foreign key without a leading index';
    END IF;

    FOREACH content_table IN ARRAY ARRAY[
        'editorial.content_schema_version',
        'editorial.article_type_version',
        'editorial.article_template_version',
        'editorial.editorial_methodology_version',
        'editorial.article_methodology_binding',
        'editorial.seo_metadata_version',
        'editorial.structured_data_manifest',
        'editorial.media_asset',
        'evidence.first_hand_experience_record',
        'evidence.first_hand_experience_asset',
        'editorial.article_disclosure_context'
    ]
    LOOP
        IF has_table_privilege('raos_public_ro', content_table, 'SELECT')
           OR has_table_privilege('raos_public_ro', content_table, 'INSERT')
           OR has_table_privilege('raos_public_ro', content_table, 'UPDATE')
           OR has_table_privilege('raos_public_ro', content_table, 'DELETE')
           OR has_table_privilege('raos_worker_rw', content_table, 'INSERT')
           OR has_table_privilege('raos_worker_rw', content_table, 'UPDATE')
           OR has_table_privilege('raos_worker_rw', content_table, 'DELETE')
           OR NOT has_table_privilege('raos_api_rw', content_table, 'SELECT')
           OR NOT has_table_privilege('raos_api_rw', content_table, 'INSERT')
           OR NOT has_table_privilege('raos_api_rw', content_table, 'UPDATE')
           OR has_table_privilege('raos_api_rw', content_table, 'DELETE') THEN
            RAISE EXCEPTION
                'ST-0004 ACL/authority drift on %', content_table;
        END IF;
        IF NOT EXISTS (
            SELECT 1
              FROM pg_class AS relation
             WHERE relation.oid = to_regclass(content_table)
               AND relation.relrowsecurity
               AND relation.relforcerowsecurity
        ) OR NOT EXISTS (
            SELECT 1
              FROM pg_policy AS policy
             WHERE policy.polrelid = to_regclass(content_table)
               AND policy.polcmd = '*'
               AND (
                    SELECT oid FROM pg_roles WHERE rolname = 'raos_api_rw'
               ) = ANY(policy.polroles)
        ) OR NOT EXISTS (
            SELECT 1
              FROM pg_policy AS policy
             WHERE policy.polrelid = to_regclass(content_table)
               AND policy.polcmd = 'r'
               AND (
                    SELECT oid FROM pg_roles WHERE rolname = 'raos_worker_rw'
               ) = ANY(policy.polroles)
        ) THEN
            RAISE EXCEPTION 'ST-0004 RLS/policy drift on %', content_table;
        END IF;
        IF EXISTS (
            SELECT 1
              FROM pg_class AS relation
              CROSS JOIN LATERAL aclexplode(
                COALESCE(relation.relacl, acldefault('r', relation.relowner))
              ) AS privilege
             WHERE relation.oid = to_regclass(content_table)
               AND privilege.grantee = 0
               AND privilege.privilege_type IN (
                    'SELECT', 'INSERT', 'UPDATE', 'DELETE'
               )
        ) THEN
            RAISE EXCEPTION 'ST-0004 PUBLIC privilege drift on %',
                content_table;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'editorial.article_version'::regclass
           AND conname IN (
                'fk_editorial_article_version_content_schema',
                'fk_editorial_article_version_article_type',
                'fk_editorial_article_version_article_template',
                'fk_editorial_article_version_seo',
                'ck_editorial_article_version_content_schema_not_null_st0004',
                'ck_editorial_article_version_article_type_not_null_st0004',
                'ck_editorial_article_version_article_template_not_null_st0004',
                'ck_editorial_article_version_seo_not_null_st0004'
           )
    ) THEN
        RAISE EXCEPTION
            'ST-0004 Contract prepare found canonical or partial guard constraints';
    END IF;
END
$$;

ALTER TABLE editorial.article_version
    ADD CONSTRAINT ck_editorial_article_version_content_schema_not_null_st0004
        CHECK (content_schema_version_id IS NOT NULL) NOT VALID,
    ADD CONSTRAINT ck_editorial_article_version_article_type_not_null_st0004
        CHECK (article_type_version_id IS NOT NULL) NOT VALID,
    ADD CONSTRAINT ck_editorial_article_version_article_template_not_null_st0004
        CHECK (article_template_version_id IS NOT NULL) NOT VALID,
    ADD CONSTRAINT ck_editorial_article_version_seo_not_null_st0004
        CHECK (seo_metadata_version_id IS NOT NULL) NOT VALID;

COMMIT;
