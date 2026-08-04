-- ST-0004 / INT-DEC-005 / INT-DEC-006
-- Guarded downgrade: finalized ST-0004 Contract -> exact finalized ST-0003.
--
-- This downgrade is intentionally available only while every ST-0004-owned
-- table is empty and no Article Version carries any of the four bindings.
-- Once content exists, use forward-recovery.md and a new reviewed migration;
-- never bypass this data-loss guard.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '15min';

LOCK TABLE
    editorial.article_version,
    editorial.content_schema_version,
    editorial.article_type_version,
    editorial.article_template_version,
    editorial.editorial_methodology_version,
    editorial.article_methodology_binding,
    editorial.seo_metadata_version,
    editorial.structured_data_manifest,
    editorial.media_asset,
    editorial.article_disclosure_context,
    evidence.first_hand_experience_record,
    evidence.first_hand_experience_asset
IN ACCESS EXCLUSIVE MODE;

DO $$
DECLARE
    binding_column text;
    canonical_index text;
    content_relation text;
    relation_has_data boolean;
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0004 requires PostgreSQL 18 or later';
    END IF;

    FOREACH content_relation IN ARRAY ARRAY[
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
        IF to_regclass(content_relation) IS NULL THEN
            RAISE EXCEPTION
                'ST-0004 downgrade requires exact finalized relation %',
                content_relation;
        END IF;
        IF NOT EXISTS (
            SELECT 1
              FROM pg_class AS relation
             WHERE relation.oid = to_regclass(content_relation)
               AND relation.relrowsecurity
               AND relation.relforcerowsecurity
        ) THEN
            RAISE EXCEPTION
                'ST-0004 downgrade requires forced RLS on %',
                content_relation;
        END IF;
        EXECUTE format(
            'SELECT EXISTS (SELECT 1 FROM %s)',
            content_relation
        ) INTO relation_has_data;
        IF relation_has_data THEN
            RAISE EXCEPTION
                'ST-0004 downgrade refused: % contains data; use forward recovery',
                content_relation
                USING ERRCODE = '55000';
        END IF;
    END LOOP;

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
               AND is_nullable = 'NO'
        ) THEN
            RAISE EXCEPTION
                'ST-0004 downgrade requires canonical NOT NULL binding %',
                binding_column;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1
          FROM editorial.article_version
         WHERE content_schema_version_id IS NOT NULL
            OR article_type_version_id IS NOT NULL
            OR article_template_version_id IS NOT NULL
            OR seo_metadata_version_id IS NOT NULL
    ) THEN
        RAISE EXCEPTION
            'ST-0004 downgrade refused: Article Version bindings contain data; use forward recovery'
            USING ERRCODE = '55000';
    END IF;

    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE conrelid = 'editorial.article_version'::regclass
           AND conname IN (
                'fk_editorial_article_version_content_schema',
                'fk_editorial_article_version_article_type',
                'fk_editorial_article_version_article_template',
                'fk_editorial_article_version_seo'
           )
           AND contype = 'f'
           AND convalidated
    ) <> 4 THEN
        RAISE EXCEPTION
            'ST-0004 downgrade requires the exact canonical foreign-key ABI';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'editorial.article_version'::regclass
           AND conname = 'fk_editorial_article_version_seo'
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
            'ST-0004 downgrade requires the deferred SEO/article cycle';
    END IF;

    FOREACH canonical_index IN ARRAY ARRAY[
        'editorial.uq_editorial_content_schema_active',
        'editorial.uq_editorial_article_type_active',
        'editorial.uq_editorial_methodology_active',
        'editorial.ix_editorial_media_asset_status',
        'evidence.ix_evidence_first_hand_product',
        'editorial.ix_editorial_article_version_content_schema',
        'editorial.ix_editorial_article_version_article_type',
        'editorial.ix_editorial_article_version_article_template',
        'editorial.ix_editorial_article_version_seo',
        'editorial.ix_editorial_content_schema_artifact',
        'editorial.ix_editorial_content_schema_approver',
        'editorial.ix_editorial_article_type_approver',
        'editorial.ix_editorial_article_template_approver',
        'editorial.ix_editorial_methodology_article_type',
        'editorial.ix_editorial_methodology_approver',
        'editorial.ix_editorial_article_methodology_version',
        'editorial.ix_editorial_article_methodology_candidate',
        'editorial.ix_editorial_article_methodology_binder',
        'editorial.ix_editorial_seo_approver',
        'editorial.ix_editorial_structured_data_seo',
        'editorial.ix_editorial_structured_data_jsonld',
        'editorial.ix_editorial_media_asset_source',
        'editorial.ix_editorial_media_asset_raw',
        'editorial.ix_editorial_media_asset_long_description',
        'editorial.ix_editorial_media_asset_approver',
        'evidence.ix_evidence_first_hand_tester',
        'evidence.ix_evidence_first_hand_reviewer',
        'evidence.ix_evidence_first_hand_asset_artifact',
        'editorial.ix_editorial_article_disclosure_reviewer'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1
              FROM pg_index
             WHERE indexrelid = to_regclass(canonical_index)
               AND indisvalid
               AND indisready
        ) OR to_regclass(canonical_index || '_st0004') IS NOT NULL THEN
            RAISE EXCEPTION
                'ST-0004 downgrade index preflight failed at %',
                canonical_index;
        END IF;
    END LOOP;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_trigger
         WHERE tgrelid = 'editorial.article_version'::regclass
           AND tgname = 'trg_editorial_article_content_bindings'
           AND tgfoid =
               'editorial.guard_article_content_bindings()'::regprocedure
           AND tgtype = 23
           AND tgenabled = 'O'
           AND NOT tgisinternal
    ) OR to_regprocedure(
        'editorial.content_artifact_matches_immutable_hash(uuid,text)'
    ) IS NULL OR to_regprocedure(
        'editorial.is_active_human_principal(uuid)'
    ) IS NULL THEN
        RAISE EXCEPTION
            'ST-0004 downgrade requires the exact trigger/helper ABI';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'ai.ai_job'::regclass
           AND conname = 'ck_ai_job_status'
           AND convalidated
    ) OR to_regclass(
        'ai.ix_ai_eval_case_result_zero_tolerance_artifact'
    ) IS NULL OR to_regprocedure(
        'ops.reject_immutable_mutation()'
    ) IS NULL THEN
        RAISE EXCEPTION
            'ST-0004 downgrade requires the exact finalized ST-0003 predecessor';
    END IF;
END
$$;

DROP INDEX
    editorial.uq_editorial_content_schema_active,
    editorial.uq_editorial_article_type_active,
    editorial.uq_editorial_methodology_active,
    editorial.ix_editorial_media_asset_status,
    evidence.ix_evidence_first_hand_product,
    editorial.ix_editorial_article_version_content_schema,
    editorial.ix_editorial_article_version_article_type,
    editorial.ix_editorial_article_version_article_template,
    editorial.ix_editorial_article_version_seo,
    editorial.ix_editorial_content_schema_artifact,
    editorial.ix_editorial_content_schema_approver,
    editorial.ix_editorial_article_type_approver,
    editorial.ix_editorial_article_template_approver,
    editorial.ix_editorial_methodology_article_type,
    editorial.ix_editorial_methodology_approver,
    editorial.ix_editorial_article_methodology_version,
    editorial.ix_editorial_article_methodology_candidate,
    editorial.ix_editorial_article_methodology_binder,
    editorial.ix_editorial_seo_approver,
    editorial.ix_editorial_structured_data_seo,
    editorial.ix_editorial_structured_data_jsonld,
    editorial.ix_editorial_media_asset_source,
    editorial.ix_editorial_media_asset_raw,
    editorial.ix_editorial_media_asset_long_description,
    editorial.ix_editorial_media_asset_approver,
    evidence.ix_evidence_first_hand_tester,
    evidence.ix_evidence_first_hand_reviewer,
    evidence.ix_evidence_first_hand_asset_artifact,
    editorial.ix_editorial_article_disclosure_reviewer;

DROP TRIGGER trg_editorial_article_content_bindings
    ON editorial.article_version;

ALTER TABLE editorial.article_version
    DROP CONSTRAINT fk_editorial_article_version_content_schema,
    DROP CONSTRAINT fk_editorial_article_version_article_type,
    DROP CONSTRAINT fk_editorial_article_version_article_template,
    DROP CONSTRAINT fk_editorial_article_version_seo,
    DROP COLUMN content_schema_version_id,
    DROP COLUMN article_type_version_id,
    DROP COLUMN article_template_version_id,
    DROP COLUMN seo_metadata_version_id;

DROP TABLE editorial.structured_data_manifest;
DROP TABLE editorial.article_disclosure_context;
DROP TABLE editorial.article_methodology_binding;
DROP TABLE evidence.first_hand_experience_asset;
DROP TABLE evidence.first_hand_experience_record;
DROP TABLE editorial.media_asset;
DROP TABLE editorial.seo_metadata_version;
DROP TABLE editorial.editorial_methodology_version;
DROP TABLE editorial.article_template_version;
DROP TABLE editorial.article_type_version;
DROP TABLE editorial.content_schema_version;

DROP FUNCTION editorial.guard_article_content_bindings();
DROP FUNCTION editorial.guard_article_methodology_binding();
DROP FUNCTION editorial.guard_content_artifact_binding();
DROP FUNCTION editorial.guard_disclosure_context_mutation();
DROP FUNCTION evidence.guard_first_hand_experience_mutation();
DROP FUNCTION editorial.guard_media_asset_mutation();
DROP FUNCTION editorial.guard_seo_metadata_mutation();
DROP FUNCTION editorial.guard_versioned_content_mutation();
DROP FUNCTION editorial.content_artifact_matches_immutable_hash(uuid, text);
DROP FUNCTION editorial.is_active_human_principal(uuid);

DO $$
DECLARE
    removed_name text;
BEGIN
    FOREACH removed_name IN ARRAY ARRAY[
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
        'editorial.article_disclosure_context',
        'editorial.uq_editorial_content_schema_active',
        'editorial.uq_editorial_article_type_active',
        'editorial.uq_editorial_methodology_active',
        'editorial.ix_editorial_article_version_content_schema',
        'editorial.ix_editorial_article_version_article_type',
        'editorial.ix_editorial_article_version_article_template',
        'editorial.ix_editorial_article_version_seo'
    ]
    LOOP
        IF to_regclass(removed_name) IS NOT NULL THEN
            RAISE EXCEPTION
                'ST-0004 downgrade left relation/index % behind',
                removed_name;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'editorial'
           AND table_name = 'article_version'
           AND column_name IN (
                'content_schema_version_id',
                'article_type_version_id',
                'article_template_version_id',
                'seo_metadata_version_id'
           )
    ) OR to_regprocedure(
        'editorial.guard_article_content_bindings()'
    ) IS NOT NULL OR to_regprocedure(
        'editorial.content_artifact_matches_immutable_hash(uuid,text)'
    ) IS NOT NULL THEN
        RAISE EXCEPTION 'ST-0004 downgrade left owned ABI objects behind';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'editorial'
           AND table_name = 'article_version'
           AND column_name = 'content_schema_version'
           AND data_type = 'integer'
           AND is_nullable = 'NO'
    ) OR (
        SELECT count(*)
          FROM pg_constraint
         WHERE (conrelid, conname) IN (
            ('ai.ai_job'::regclass, 'ck_ai_job_status'),
            ('ai.ai_job'::regclass, 'ck_ai_job_complete'),
            ('ai.prompt_version'::regclass, 'ck_ai_prompt_status'),
            ('ai.model_route_version'::regclass, 'ck_ai_route_status')
         )
           AND convalidated
    ) <> 4 OR to_regclass(
        'ai.ix_ai_eval_case_result_zero_tolerance_artifact'
    ) IS NULL OR to_regprocedure(
        'ai.artifact_matches_immutable_hash(uuid,text)'
    ) IS NULL THEN
        RAISE EXCEPTION
            'ST-0004 downgrade did not restore the exact finalized ST-0003 ABI';
    END IF;
END
$$;

COMMIT;
