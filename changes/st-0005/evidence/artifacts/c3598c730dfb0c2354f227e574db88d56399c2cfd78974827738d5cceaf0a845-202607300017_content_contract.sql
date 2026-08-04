-- ST-0004 / INT-DEC-005 / INT-DEC-006
-- Phase: CONTRACT VALIDATE AND FINALIZE
-- Requires: 202607300016_content_contract_prepare.sql
--
-- Full-table validation commits separately.  The final four-column NOT NULL,
-- foreign-key name, and index name swap is one short metadata transaction.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '15min';

DO $$
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0004 requires PostgreSQL 18 or later';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM editorial.article_version
         WHERE content_schema_version_id IS NULL
            OR article_type_version_id IS NULL
            OR article_template_version_id IS NULL
            OR seo_metadata_version_id IS NULL
    ) THEN
        RAISE EXCEPTION 'ST-0004 Contract validation backlog is nonzero';
    END IF;
    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE conrelid = 'editorial.article_version'::regclass
           AND conname IN (
                'ck_editorial_article_version_content_schema_not_null_st0004',
                'ck_editorial_article_version_article_type_not_null_st0004',
                'ck_editorial_article_version_article_template_not_null_st0004',
                'ck_editorial_article_version_seo_not_null_st0004'
           )
           AND contype = 'c'
    ) <> 4 THEN
        RAISE EXCEPTION
            'ST-0004 Contract validation requires four complete guards';
    END IF;
    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE conrelid = 'editorial.article_version'::regclass
           AND conname IN (
                'ck_editorial_article_version_content_schema_not_null_st0004',
                'ck_editorial_article_version_article_type_not_null_st0004',
                'ck_editorial_article_version_article_template_not_null_st0004',
                'ck_editorial_article_version_seo_not_null_st0004'
           )
           AND convalidated
    ) NOT IN (0, 4) THEN
        RAISE EXCEPTION
            'ST-0004 Contract validation found partially validated guards';
    END IF;
END
$$;

ALTER TABLE editorial.article_version VALIDATE CONSTRAINT
    ck_editorial_article_version_content_schema_not_null_st0004;
ALTER TABLE editorial.article_version VALIDATE CONSTRAINT
    ck_editorial_article_version_article_type_not_null_st0004;
ALTER TABLE editorial.article_version VALIDATE CONSTRAINT
    ck_editorial_article_version_article_template_not_null_st0004;
ALTER TABLE editorial.article_version VALIDATE CONSTRAINT
    ck_editorial_article_version_seo_not_null_st0004;

COMMIT;

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $$
DECLARE
    old_index text;
    canonical_index text;
BEGIN
    IF EXISTS (
        SELECT 1
          FROM editorial.article_version
         WHERE content_schema_version_id IS NULL
            OR article_type_version_id IS NULL
            OR article_template_version_id IS NULL
            OR seo_metadata_version_id IS NULL
    ) THEN
        RAISE EXCEPTION 'ST-0004 Contract finalization backlog is nonzero';
    END IF;
    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE conrelid = 'editorial.article_version'::regclass
           AND conname IN (
                'ck_editorial_article_version_content_schema_not_null_st0004',
                'ck_editorial_article_version_article_type_not_null_st0004',
                'ck_editorial_article_version_article_template_not_null_st0004',
                'ck_editorial_article_version_seo_not_null_st0004'
           )
           AND contype = 'c'
           AND convalidated
    ) <> 4 OR (
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
            'ST-0004 Contract finalization requires eight validated constraints';
    END IF;

    FOREACH old_index IN ARRAY ARRAY[
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
        canonical_index := regexp_replace(old_index, '_st0004$', '');
        IF NOT EXISTS (
            SELECT 1
              FROM pg_index
             WHERE indexrelid = to_regclass(old_index)
               AND indisvalid
               AND indisready
        ) OR to_regclass(canonical_index) IS NOT NULL THEN
            RAISE EXCEPTION
                'ST-0004 index rename preflight failed for % -> %',
                old_index,
                canonical_index;
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
                'fk_editorial_article_version_seo'
           )
    ) THEN
        RAISE EXCEPTION 'ST-0004 canonical foreign-key names already exist';
    END IF;
END
$$;

ALTER TABLE editorial.article_version
    ALTER COLUMN content_schema_version_id SET NOT NULL,
    ALTER COLUMN article_type_version_id SET NOT NULL,
    ALTER COLUMN article_template_version_id SET NOT NULL,
    ALTER COLUMN seo_metadata_version_id SET NOT NULL,
    DROP CONSTRAINT ck_editorial_article_version_content_schema_not_null_st0004,
    DROP CONSTRAINT ck_editorial_article_version_article_type_not_null_st0004,
    DROP CONSTRAINT ck_editorial_article_version_article_template_not_null_st0004,
    DROP CONSTRAINT ck_editorial_article_version_seo_not_null_st0004;

ALTER TABLE editorial.article_version RENAME CONSTRAINT
    fk_editorial_article_version_content_schema_st0004_expand
    TO fk_editorial_article_version_content_schema;
ALTER TABLE editorial.article_version RENAME CONSTRAINT
    fk_editorial_article_version_article_type_st0004_expand
    TO fk_editorial_article_version_article_type;
ALTER TABLE editorial.article_version RENAME CONSTRAINT
    fk_editorial_article_version_article_template_st0004_expand
    TO fk_editorial_article_version_article_template;
ALTER TABLE editorial.article_version RENAME CONSTRAINT
    fk_editorial_article_version_seo_st0004_expand
    TO fk_editorial_article_version_seo;

ALTER INDEX editorial.uq_editorial_content_schema_active_st0004
    RENAME TO uq_editorial_content_schema_active;
ALTER INDEX editorial.uq_editorial_article_type_active_st0004
    RENAME TO uq_editorial_article_type_active;
ALTER INDEX editorial.uq_editorial_methodology_active_st0004
    RENAME TO uq_editorial_methodology_active;
ALTER INDEX editorial.ix_editorial_media_asset_status_st0004
    RENAME TO ix_editorial_media_asset_status;
ALTER INDEX evidence.ix_evidence_first_hand_product_st0004
    RENAME TO ix_evidence_first_hand_product;
ALTER INDEX editorial.ix_editorial_article_version_content_schema_st0004
    RENAME TO ix_editorial_article_version_content_schema;
ALTER INDEX editorial.ix_editorial_article_version_article_type_st0004
    RENAME TO ix_editorial_article_version_article_type;
ALTER INDEX editorial.ix_editorial_article_version_article_template_st0004
    RENAME TO ix_editorial_article_version_article_template;
ALTER INDEX editorial.ix_editorial_article_version_seo_st0004
    RENAME TO ix_editorial_article_version_seo;
ALTER INDEX editorial.ix_editorial_content_schema_artifact_st0004
    RENAME TO ix_editorial_content_schema_artifact;
ALTER INDEX editorial.ix_editorial_content_schema_approver_st0004
    RENAME TO ix_editorial_content_schema_approver;
ALTER INDEX editorial.ix_editorial_article_type_approver_st0004
    RENAME TO ix_editorial_article_type_approver;
ALTER INDEX editorial.ix_editorial_article_template_approver_st0004
    RENAME TO ix_editorial_article_template_approver;
ALTER INDEX editorial.ix_editorial_methodology_article_type_st0004
    RENAME TO ix_editorial_methodology_article_type;
ALTER INDEX editorial.ix_editorial_methodology_approver_st0004
    RENAME TO ix_editorial_methodology_approver;
ALTER INDEX editorial.ix_editorial_article_methodology_version_st0004
    RENAME TO ix_editorial_article_methodology_version;
ALTER INDEX editorial.ix_editorial_article_methodology_candidate_st0004
    RENAME TO ix_editorial_article_methodology_candidate;
ALTER INDEX editorial.ix_editorial_article_methodology_binder_st0004
    RENAME TO ix_editorial_article_methodology_binder;
ALTER INDEX editorial.ix_editorial_seo_approver_st0004
    RENAME TO ix_editorial_seo_approver;
ALTER INDEX editorial.ix_editorial_structured_data_seo_st0004
    RENAME TO ix_editorial_structured_data_seo;
ALTER INDEX editorial.ix_editorial_structured_data_jsonld_st0004
    RENAME TO ix_editorial_structured_data_jsonld;
ALTER INDEX editorial.ix_editorial_media_asset_source_st0004
    RENAME TO ix_editorial_media_asset_source;
ALTER INDEX editorial.ix_editorial_media_asset_raw_st0004
    RENAME TO ix_editorial_media_asset_raw;
ALTER INDEX editorial.ix_editorial_media_asset_long_description_st0004
    RENAME TO ix_editorial_media_asset_long_description;
ALTER INDEX editorial.ix_editorial_media_asset_approver_st0004
    RENAME TO ix_editorial_media_asset_approver;
ALTER INDEX evidence.ix_evidence_first_hand_tester_st0004
    RENAME TO ix_evidence_first_hand_tester;
ALTER INDEX evidence.ix_evidence_first_hand_reviewer_st0004
    RENAME TO ix_evidence_first_hand_reviewer;
ALTER INDEX evidence.ix_evidence_first_hand_asset_artifact_st0004
    RENAME TO ix_evidence_first_hand_asset_artifact;
ALTER INDEX editorial.ix_editorial_article_disclosure_reviewer_st0004
    RENAME TO ix_editorial_article_disclosure_reviewer;

DO $$
DECLARE
    binding_column text;
    canonical_index text;
    content_table text;
BEGIN
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
                'ST-0004 canonical binding column % is missing or nullable',
                binding_column;
        END IF;
    END LOOP;

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
        RAISE EXCEPTION 'ST-0004 canonical foreign-key ABI is incomplete';
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
            'ST-0004 canonical SEO/article cycle is not initially deferred';
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
                'ST-0004 canonical index ABI is incomplete at %',
                canonical_index;
        END IF;
    END LOOP;

    IF pg_get_indexdef(
           'editorial.uq_editorial_content_schema_active'::regclass
       ) <> 'CREATE UNIQUE INDEX uq_editorial_content_schema_active ON editorial.content_schema_version USING btree (schema_code) WHERE (status = ''ACTIVE''::text)'
       OR pg_get_indexdef(
           'editorial.uq_editorial_article_type_active'::regclass
       ) <> 'CREATE UNIQUE INDEX uq_editorial_article_type_active ON editorial.article_type_version USING btree (article_type_code) WHERE (status = ''ACTIVE''::text)'
       OR pg_get_indexdef(
           'editorial.uq_editorial_methodology_active'::regclass
       ) <> 'CREATE UNIQUE INDEX uq_editorial_methodology_active ON editorial.editorial_methodology_version USING btree (methodology_code) WHERE (status = ''ACTIVE''::text)' THEN
        RAISE EXCEPTION 'ST-0004 canonical active-singleton indexes drifted';
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
        IF has_table_privilege('raos_worker_rw', content_table, 'INSERT')
           OR has_table_privilege('raos_worker_rw', content_table, 'UPDATE')
           OR has_table_privilege('raos_worker_rw', content_table, 'DELETE')
           OR has_table_privilege('raos_public_ro', content_table, 'SELECT')
           OR NOT EXISTS (
                SELECT 1
                  FROM pg_class AS relation
                 WHERE relation.oid = to_regclass(content_table)
                   AND relation.relrowsecurity
                   AND relation.relforcerowsecurity
           ) THEN
            RAISE EXCEPTION
                'ST-0004 final ACL/RLS authority drift on %', content_table;
        END IF;
    END LOOP;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'ai.ai_job'::regclass
           AND conname = 'ck_ai_job_status'
           AND convalidated
    ) OR to_regclass(
        'ai.ix_ai_eval_case_result_zero_tolerance_artifact'
    ) IS NULL THEN
        RAISE EXCEPTION 'ST-0004 finalization disturbed the ST-0003 ABI';
    END IF;
END
$$;

COMMIT;
