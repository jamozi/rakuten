-- Guarded rollback for 202608300001. Refuses any imported live or revised state.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

LOCK TABLE analytics.import_run,
           analytics.gsc_observation,
           analytics.ga4_observation
    IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM analytics.import_run
         WHERE provider_resource IS NOT NULL
            OR request_sha256 IS NOT NULL
            OR request_page_sha256s <> '[]'::jsonb
            OR configuration_snapshot IS NOT NULL
            OR configuration_snapshot_sha256 IS NOT NULL
            OR predecessor_import_run_id IS NOT NULL
            OR import_revision <> 1
    ) OR EXISTS (
        SELECT 1
          FROM analytics.gsc_observation
         WHERE source_request_sha256 IS NOT NULL
            OR observation_revision <> 1
            OR supersedes_observation_id IS NOT NULL
            OR NOT is_current
            OR length(country_code) > 2
    ) OR EXISTS (
        SELECT 1
          FROM analytics.ga4_observation
         WHERE property_id IS NOT NULL
            OR source_request_sha256 IS NOT NULL
            OR configuration_snapshot_sha256 IS NOT NULL
            OR observation_revision <> 1
            OR supersedes_observation_id IS NOT NULL
            OR NOT is_current
    ) THEN
        RAISE EXCEPTION
            'google analytics live migration has imported or revised state; use forward recovery';
    END IF;
END;
$$;

DROP INDEX analytics.ix_analytics_ga4_supersedes_live;
DROP INDEX analytics.ix_analytics_gsc_supersedes_live;
DROP INDEX analytics.ix_analytics_import_predecessor_live;
DROP INDEX analytics.ux_analytics_ga4_grain_revision_live;
DROP INDEX analytics.ux_analytics_ga4_current_grain_live;
DROP INDEX analytics.ux_analytics_gsc_grain_revision_live;
DROP INDEX analytics.ux_analytics_gsc_current_grain_live;

ALTER TABLE analytics.ga4_observation
    DROP CONSTRAINT fk_analytics_ga4_supersedes_live,
    DROP CONSTRAINT ck_analytics_ga4_supersession_live,
    DROP CONSTRAINT ck_analytics_ga4_revision_live,
    DROP CONSTRAINT ck_analytics_ga4_config_sha256_live,
    DROP CONSTRAINT ck_analytics_ga4_request_sha256_live,
    DROP CONSTRAINT ck_analytics_ga4_property_live,
    DROP COLUMN is_current,
    DROP COLUMN supersedes_observation_id,
    DROP COLUMN observation_revision,
    DROP COLUMN configuration_snapshot_sha256,
    DROP COLUMN source_request_sha256,
    DROP COLUMN property_id;

ALTER TABLE analytics.gsc_observation
    DROP CONSTRAINT fk_analytics_gsc_supersedes_live,
    DROP CONSTRAINT ck_analytics_gsc_supersession_live,
    DROP CONSTRAINT ck_analytics_gsc_revision_live,
    DROP CONSTRAINT ck_analytics_gsc_data_state_live,
    DROP CONSTRAINT ck_analytics_gsc_request_sha256_live,
    DROP CONSTRAINT ck_analytics_gsc_country_live,
    DROP COLUMN is_current,
    DROP COLUMN supersedes_observation_id,
    DROP COLUMN observation_revision,
    DROP COLUMN provider_data_state,
    DROP COLUMN source_request_sha256,
    ALTER COLUMN country_code TYPE char(2)
        USING country_code::char(2);

ALTER TABLE analytics.import_run
    DROP CONSTRAINT fk_analytics_import_predecessor_live,
    DROP CONSTRAINT ck_analytics_import_revision_live,
    DROP CONSTRAINT ck_analytics_import_config_snapshot_live,
    DROP CONSTRAINT ck_analytics_import_page_hashes_live,
    DROP CONSTRAINT ck_analytics_import_request_sha256_live,
    DROP COLUMN import_revision,
    DROP COLUMN predecessor_import_run_id,
    DROP COLUMN configuration_snapshot_sha256,
    DROP COLUMN configuration_snapshot,
    DROP COLUMN request_page_sha256s,
    DROP COLUMN request_sha256,
    DROP COLUMN provider_resource;

CREATE UNIQUE INDEX ux_analytics_gsc_grain
    ON analytics.gsc_observation (site_id, metric_date, dimension_key_sha256);
CREATE UNIQUE INDEX ux_analytics_ga4_grain
    ON analytics.ga4_observation (site_id, metric_date, grain_key_sha256);

COMMIT;
