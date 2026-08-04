-- ST-0004 / INT-DEC-005 / INT-DEC-006
-- Phase: MIGRATE REPEATABLE BATCH
-- Requires: 202607300014_content_expand_validate.sql
--
-- The legacy integer content_schema_version does not identify any of the new
-- immutable UUID version rows.  Likewise, legacy rows have no evidence-safe
-- Article Type, Article Template, or SEO version mapping.  This migration must
-- never invent those bindings.  It therefore reports a repeatable checkpoint
-- with zero automatic changes and exact operator-required remaining rows.

BEGIN ISOLATION LEVEL REPEATABLE READ;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $$
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
           AND convalidated
    ) <> 4
       OR to_regclass(
            'editorial.uq_editorial_content_schema_active_st0004'
          ) IS NULL
       OR to_regclass(
            'editorial.uq_editorial_article_type_active_st0004'
          ) IS NULL
       OR to_regclass(
            'editorial.uq_editorial_methodology_active_st0004'
          ) IS NULL
       OR to_regclass(
            'editorial.ix_editorial_media_asset_status_st0004'
          ) IS NULL
       OR to_regclass(
            'evidence.ix_evidence_first_hand_product_st0004'
          ) IS NULL THEN
        RAISE EXCEPTION
            'ST-0004 Migrate requires the exact validated Expand state';
    END IF;
END
$$;

CREATE TEMPORARY TABLE st0004_batch_budget (
    remaining integer NOT NULL CHECK (remaining BETWEEN 0 AND 1000)
) ON COMMIT DROP;
INSERT INTO st0004_batch_budget (remaining) VALUES (1000);

CREATE TEMPORARY TABLE st0004_batch_checkpoint (
    entity text PRIMARY KEY,
    row_count bigint NOT NULL CHECK (row_count >= 0),
    detail jsonb NOT NULL
) ON COMMIT DROP;

INSERT INTO st0004_batch_checkpoint (entity, row_count, detail)
SELECT 'editorial.article_version.content_schema_version_id',
       0,
       jsonb_build_object(
            'operator_required_rows', count(*),
            'reason',
            'legacy integer schema version has no evidence-safe UUID mapping'
       )
  FROM editorial.article_version
 WHERE content_schema_version_id IS NULL
UNION ALL
SELECT 'editorial.article_version.article_type_version_id',
       0,
       jsonb_build_object(
            'operator_required_rows', count(*),
            'reason',
            'legacy article rows do not identify an immutable Article Type Version'
       )
  FROM editorial.article_version
 WHERE article_type_version_id IS NULL
UNION ALL
SELECT 'editorial.article_version.article_template_version_id',
       0,
       jsonb_build_object(
            'operator_required_rows', count(*),
            'reason',
            'legacy article rows do not identify an immutable Article Template Version'
       )
  FROM editorial.article_version
 WHERE article_template_version_id IS NULL
UNION ALL
SELECT 'editorial.article_version.seo_metadata_version_id',
       0,
       jsonb_build_object(
            'operator_required_rows', count(*),
            'reason',
            'legacy article rows do not identify approved same-article SEO metadata'
       )
  FROM editorial.article_version
 WHERE seo_metadata_version_id IS NULL;

DO $$
DECLARE
    changed_rows bigint;
BEGIN
    SELECT COALESCE(sum(row_count), 0)
      INTO changed_rows
      FROM st0004_batch_checkpoint;
    IF changed_rows > 1000 THEN
        RAISE EXCEPTION
            'ST-0004 internal error: batch changed % rows, limit is 1000',
            changed_rows;
    END IF;
END
$$;

SELECT entity, row_count, detail
  FROM st0004_batch_checkpoint
 ORDER BY entity;

SELECT 1000 - remaining AS changed_rows,
       remaining AS unused_batch_capacity
  FROM st0004_batch_budget;

COMMIT;

WITH counts AS (
    SELECT 0::bigint AS automatic_remaining_rows,
           count(*) FILTER (
               WHERE content_schema_version_id IS NULL
           )::bigint AS unbound_content_schema_rows,
           count(*) FILTER (
               WHERE article_type_version_id IS NULL
           )::bigint AS unbound_article_type_rows,
           count(*) FILTER (
               WHERE article_template_version_id IS NULL
           )::bigint AS unbound_article_template_rows,
           count(*) FILTER (
               WHERE seo_metadata_version_id IS NULL
           )::bigint AS unbound_seo_metadata_rows,
           count(*) FILTER (
               WHERE content_schema_version_id IS NULL
                  OR article_type_version_id IS NULL
                  OR article_template_version_id IS NULL
                  OR seo_metadata_version_id IS NULL
           )::bigint AS operator_binding_rows
      FROM editorial.article_version
)
SELECT automatic_remaining_rows,
       operator_binding_rows,
       automatic_remaining_rows + operator_binding_rows AS remaining_rows,
       unbound_content_schema_rows,
       unbound_article_type_rows,
       unbound_article_template_rows,
       unbound_seo_metadata_rows
  FROM counts;
