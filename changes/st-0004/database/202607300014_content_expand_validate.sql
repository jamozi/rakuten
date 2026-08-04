-- ST-0004 / INT-DEC-005 / INT-DEC-006
-- Phase: EXPAND VALIDATE / ONLINE INDEXES
-- Run with autocommit enabled. Concurrent index creation must not be wrapped
-- by an outer transaction.

SET TIME ZONE 'UTC';
SET lock_timeout = '5s';
SET statement_timeout = '30min';

BEGIN;

DO $$
DECLARE
    binding_column text;
    index_name text;
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0004 requires PostgreSQL 18 or later';
    END IF;

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
           AND NOT convalidated
    ) <> 4 THEN
        RAISE EXCEPTION
            'ST-0004 online-index phase requires the exact unvalidated Expand bindings';
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

    FOREACH index_name IN ARRAY ARRAY[
        'editorial.uq_editorial_content_schema_active_st0004',
        'editorial.uq_editorial_article_type_active_st0004',
        'editorial.uq_editorial_methodology_active_st0004',
        'editorial.ix_editorial_media_asset_status_st0004',
        'evidence.ix_evidence_first_hand_product_st0004',
        'editorial.ix_editorial_article_version_content_schema_st0004',
        'editorial.ix_editorial_article_version_article_type_st0004',
        'editorial.ix_editorial_article_version_article_template_st0004',
        'editorial.ix_editorial_article_version_seo_st0004',
        'editorial.ix_editorial_content_schema_artifact_st0004',
        'editorial.ix_editorial_content_schema_approver_st0004',
        'editorial.ix_editorial_article_type_approver_st0004',
        'editorial.ix_editorial_article_template_approver_st0004',
        'editorial.ix_editorial_methodology_article_type_st0004',
        'editorial.ix_editorial_methodology_approver_st0004',
        'editorial.ix_editorial_article_methodology_version_st0004',
        'editorial.ix_editorial_article_methodology_candidate_st0004',
        'editorial.ix_editorial_article_methodology_binder_st0004',
        'editorial.ix_editorial_seo_approver_st0004',
        'editorial.ix_editorial_structured_data_seo_st0004',
        'editorial.ix_editorial_structured_data_jsonld_st0004',
        'editorial.ix_editorial_media_asset_source_st0004',
        'editorial.ix_editorial_media_asset_raw_st0004',
        'editorial.ix_editorial_media_asset_long_description_st0004',
        'editorial.ix_editorial_media_asset_approver_st0004',
        'evidence.ix_evidence_first_hand_tester_st0004',
        'evidence.ix_evidence_first_hand_reviewer_st0004',
        'evidence.ix_evidence_first_hand_asset_artifact_st0004',
        'editorial.ix_editorial_article_disclosure_reviewer_st0004'
    ]
    LOOP
        IF to_regclass(index_name) IS NOT NULL THEN
            RAISE EXCEPTION
                'ST-0004 online-index phase found partial/drifted index %; inspect before retry',
                index_name;
        END IF;
    END LOOP;
END
$$;

ALTER TABLE editorial.article_version VALIDATE CONSTRAINT
    fk_editorial_article_version_content_schema_st0004_expand;
ALTER TABLE editorial.article_version VALIDATE CONSTRAINT
    fk_editorial_article_version_article_type_st0004_expand;
ALTER TABLE editorial.article_version VALIDATE CONSTRAINT
    fk_editorial_article_version_article_template_st0004_expand;
ALTER TABLE editorial.article_version VALIDATE CONSTRAINT
    fk_editorial_article_version_seo_st0004_expand;

COMMIT;

-- CREATE INDEX CONCURRENTLY semantics; uniqueness enforces active singleton.
CREATE UNIQUE INDEX CONCURRENTLY uq_editorial_content_schema_active_st0004
    ON editorial.content_schema_version (schema_code)
    WHERE status = 'ACTIVE';
-- CREATE INDEX CONCURRENTLY semantics; uniqueness enforces active singleton.
CREATE UNIQUE INDEX CONCURRENTLY uq_editorial_article_type_active_st0004
    ON editorial.article_type_version (article_type_code)
    WHERE status = 'ACTIVE';
-- CREATE INDEX CONCURRENTLY semantics; uniqueness enforces active singleton.
CREATE UNIQUE INDEX CONCURRENTLY uq_editorial_methodology_active_st0004
    ON editorial.editorial_methodology_version (methodology_code)
    WHERE status = 'ACTIVE';
CREATE INDEX CONCURRENTLY ix_editorial_media_asset_status_st0004
    ON editorial.media_asset (status, created_at DESC);
CREATE INDEX CONCURRENTLY ix_evidence_first_hand_product_st0004
    ON evidence.first_hand_experience_record (product_id, ended_at DESC);

CREATE INDEX CONCURRENTLY ix_editorial_article_version_content_schema_st0004
    ON editorial.article_version (content_schema_version_id);
CREATE INDEX CONCURRENTLY ix_editorial_article_version_article_type_st0004
    ON editorial.article_version (article_type_version_id);
CREATE INDEX CONCURRENTLY ix_editorial_article_version_article_template_st0004
    ON editorial.article_version (article_template_version_id);
CREATE INDEX CONCURRENTLY ix_editorial_article_version_seo_st0004
    ON editorial.article_version (seo_metadata_version_id, id);
CREATE INDEX CONCURRENTLY ix_editorial_content_schema_artifact_st0004
    ON editorial.content_schema_version (artifact_id);
CREATE INDEX CONCURRENTLY ix_editorial_content_schema_approver_st0004
    ON editorial.content_schema_version (approved_by_principal_id);
CREATE INDEX CONCURRENTLY ix_editorial_article_type_approver_st0004
    ON editorial.article_type_version (approved_by_principal_id);
CREATE INDEX CONCURRENTLY ix_editorial_article_template_approver_st0004
    ON editorial.article_template_version (approved_by_principal_id);
CREATE INDEX CONCURRENTLY ix_editorial_methodology_article_type_st0004
    ON editorial.editorial_methodology_version
        (article_type_version_id, article_type_code);
CREATE INDEX CONCURRENTLY ix_editorial_methodology_approver_st0004
    ON editorial.editorial_methodology_version (approved_by_principal_id);
CREATE INDEX CONCURRENTLY ix_editorial_article_methodology_version_st0004
    ON editorial.article_methodology_binding (methodology_version_id);
CREATE INDEX CONCURRENTLY ix_editorial_article_methodology_candidate_st0004
    ON editorial.article_methodology_binding (candidate_universe_artifact_id);
CREATE INDEX CONCURRENTLY ix_editorial_article_methodology_binder_st0004
    ON editorial.article_methodology_binding (bound_by_principal_id);
CREATE INDEX CONCURRENTLY ix_editorial_seo_approver_st0004
    ON editorial.seo_metadata_version (approved_by_principal_id);
CREATE INDEX CONCURRENTLY ix_editorial_structured_data_seo_st0004
    ON editorial.structured_data_manifest
        (seo_metadata_version_id, article_version_id);
CREATE INDEX CONCURRENTLY ix_editorial_structured_data_jsonld_st0004
    ON editorial.structured_data_manifest (jsonld_artifact_id);
CREATE INDEX CONCURRENTLY ix_editorial_media_asset_source_st0004
    ON editorial.media_asset (source_id);
CREATE INDEX CONCURRENTLY ix_editorial_media_asset_raw_st0004
    ON editorial.media_asset (raw_artifact_id);
CREATE INDEX CONCURRENTLY ix_editorial_media_asset_long_description_st0004
    ON editorial.media_asset (long_description_artifact_id);
CREATE INDEX CONCURRENTLY ix_editorial_media_asset_approver_st0004
    ON editorial.media_asset (approved_by_principal_id);
CREATE INDEX CONCURRENTLY ix_evidence_first_hand_tester_st0004
    ON evidence.first_hand_experience_record (tester_principal_id);
CREATE INDEX CONCURRENTLY ix_evidence_first_hand_reviewer_st0004
    ON evidence.first_hand_experience_record (reviewed_by_principal_id);
CREATE INDEX CONCURRENTLY ix_evidence_first_hand_asset_artifact_st0004
    ON evidence.first_hand_experience_asset (artifact_id);
CREATE INDEX CONCURRENTLY ix_editorial_article_disclosure_reviewer_st0004
    ON editorial.article_disclosure_context (reviewed_by_principal_id);

BEGIN;

DO $$
DECLARE
    expected record;
    actual record;
BEGIN
    FOR expected IN
        SELECT *
          FROM (VALUES
            ('editorial', 'uq_editorial_content_schema_active_st0004', 'editorial', 'content_schema_version', true, ARRAY['schema_code']::text[], '(status = ''ACTIVE''::text)'),
            ('editorial', 'uq_editorial_article_type_active_st0004', 'editorial', 'article_type_version', true, ARRAY['article_type_code']::text[], '(status = ''ACTIVE''::text)'),
            ('editorial', 'uq_editorial_methodology_active_st0004', 'editorial', 'editorial_methodology_version', true, ARRAY['methodology_code']::text[], '(status = ''ACTIVE''::text)'),
            ('editorial', 'ix_editorial_media_asset_status_st0004', 'editorial', 'media_asset', false, ARRAY['status', 'created_at']::text[], NULL),
            ('evidence', 'ix_evidence_first_hand_product_st0004', 'evidence', 'first_hand_experience_record', false, ARRAY['product_id', 'ended_at']::text[], NULL),
            ('editorial', 'ix_editorial_article_version_content_schema_st0004', 'editorial', 'article_version', false, ARRAY['content_schema_version_id']::text[], NULL),
            ('editorial', 'ix_editorial_article_version_article_type_st0004', 'editorial', 'article_version', false, ARRAY['article_type_version_id']::text[], NULL),
            ('editorial', 'ix_editorial_article_version_article_template_st0004', 'editorial', 'article_version', false, ARRAY['article_template_version_id']::text[], NULL),
            ('editorial', 'ix_editorial_article_version_seo_st0004', 'editorial', 'article_version', false, ARRAY['seo_metadata_version_id', 'id']::text[], NULL),
            ('editorial', 'ix_editorial_content_schema_artifact_st0004', 'editorial', 'content_schema_version', false, ARRAY['artifact_id']::text[], NULL),
            ('editorial', 'ix_editorial_content_schema_approver_st0004', 'editorial', 'content_schema_version', false, ARRAY['approved_by_principal_id']::text[], NULL),
            ('editorial', 'ix_editorial_article_type_approver_st0004', 'editorial', 'article_type_version', false, ARRAY['approved_by_principal_id']::text[], NULL),
            ('editorial', 'ix_editorial_article_template_approver_st0004', 'editorial', 'article_template_version', false, ARRAY['approved_by_principal_id']::text[], NULL),
            ('editorial', 'ix_editorial_methodology_article_type_st0004', 'editorial', 'editorial_methodology_version', false, ARRAY['article_type_version_id', 'article_type_code']::text[], NULL),
            ('editorial', 'ix_editorial_methodology_approver_st0004', 'editorial', 'editorial_methodology_version', false, ARRAY['approved_by_principal_id']::text[], NULL),
            ('editorial', 'ix_editorial_article_methodology_version_st0004', 'editorial', 'article_methodology_binding', false, ARRAY['methodology_version_id']::text[], NULL),
            ('editorial', 'ix_editorial_article_methodology_candidate_st0004', 'editorial', 'article_methodology_binding', false, ARRAY['candidate_universe_artifact_id']::text[], NULL),
            ('editorial', 'ix_editorial_article_methodology_binder_st0004', 'editorial', 'article_methodology_binding', false, ARRAY['bound_by_principal_id']::text[], NULL),
            ('editorial', 'ix_editorial_seo_approver_st0004', 'editorial', 'seo_metadata_version', false, ARRAY['approved_by_principal_id']::text[], NULL),
            ('editorial', 'ix_editorial_structured_data_seo_st0004', 'editorial', 'structured_data_manifest', false, ARRAY['seo_metadata_version_id', 'article_version_id']::text[], NULL),
            ('editorial', 'ix_editorial_structured_data_jsonld_st0004', 'editorial', 'structured_data_manifest', false, ARRAY['jsonld_artifact_id']::text[], NULL),
            ('editorial', 'ix_editorial_media_asset_source_st0004', 'editorial', 'media_asset', false, ARRAY['source_id']::text[], NULL),
            ('editorial', 'ix_editorial_media_asset_raw_st0004', 'editorial', 'media_asset', false, ARRAY['raw_artifact_id']::text[], NULL),
            ('editorial', 'ix_editorial_media_asset_long_description_st0004', 'editorial', 'media_asset', false, ARRAY['long_description_artifact_id']::text[], NULL),
            ('editorial', 'ix_editorial_media_asset_approver_st0004', 'editorial', 'media_asset', false, ARRAY['approved_by_principal_id']::text[], NULL),
            ('evidence', 'ix_evidence_first_hand_tester_st0004', 'evidence', 'first_hand_experience_record', false, ARRAY['tester_principal_id']::text[], NULL),
            ('evidence', 'ix_evidence_first_hand_reviewer_st0004', 'evidence', 'first_hand_experience_record', false, ARRAY['reviewed_by_principal_id']::text[], NULL),
            ('evidence', 'ix_evidence_first_hand_asset_artifact_st0004', 'evidence', 'first_hand_experience_asset', false, ARRAY['artifact_id']::text[], NULL),
            ('editorial', 'ix_editorial_article_disclosure_reviewer_st0004', 'editorial', 'article_disclosure_context', false, ARRAY['reviewed_by_principal_id']::text[], NULL)
          ) AS value(
            index_schema,
            index_name,
            table_schema,
            table_name,
            is_unique,
            key_columns,
            predicate
          )
    LOOP
        SELECT table_ns.nspname AS table_schema,
               table_class.relname AS table_name,
               index_data.indisunique AS is_unique,
               index_data.indisvalid AS is_valid,
               index_data.indisready AS is_ready,
               ARRAY(
                    SELECT pg_get_indexdef(
                        index_data.indexrelid,
                        key_number,
                        true
                    )
                      FROM generate_series(
                        1,
                        index_data.indnkeyatts
                      ) AS key_number
               ) AS key_columns,
               pg_get_expr(index_data.indpred, index_data.indrelid)
                   AS predicate
          INTO actual
          FROM pg_class AS index_class
          JOIN pg_namespace AS index_ns
            ON index_ns.oid = index_class.relnamespace
          JOIN pg_index AS index_data
            ON index_data.indexrelid = index_class.oid
          JOIN pg_class AS table_class
            ON table_class.oid = index_data.indrelid
          JOIN pg_namespace AS table_ns
            ON table_ns.oid = table_class.relnamespace
         WHERE index_ns.nspname = expected.index_schema
           AND index_class.relname = expected.index_name;

        IF NOT FOUND
           OR actual.table_schema IS DISTINCT FROM expected.table_schema
           OR actual.table_name IS DISTINCT FROM expected.table_name
           OR actual.is_unique IS DISTINCT FROM expected.is_unique
           OR NOT actual.is_valid
           OR NOT actual.is_ready
           OR actual.key_columns IS DISTINCT FROM expected.key_columns
           OR actual.predicate IS DISTINCT FROM expected.predicate THEN
            RAISE EXCEPTION
                'ST-0004 index % is absent, invalid, or definition-drifted',
                expected.index_schema || '.' || expected.index_name;
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
        RAISE EXCEPTION 'ST-0004 binding foreign keys did not validate';
    END IF;
END
$$;

COMMIT;
