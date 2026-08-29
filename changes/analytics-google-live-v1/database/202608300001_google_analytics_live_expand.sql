-- Successor migration for owner-authorized read-only GSC/GA4 imports.
-- This is additive over the immutable ST-0305 physical contract.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

LOCK TABLE analytics.import_run,
           analytics.gsc_observation,
           analytics.ga4_observation
    IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE analytics.import_run
    ADD COLUMN provider_resource text,
    ADD COLUMN request_sha256 text,
    ADD COLUMN request_page_sha256s jsonb DEFAULT '[]'::jsonb NOT NULL,
    ADD COLUMN configuration_snapshot jsonb,
    ADD COLUMN configuration_snapshot_sha256 text,
    ADD COLUMN predecessor_import_run_id uuid,
    ADD COLUMN import_revision bigint DEFAULT 1 NOT NULL;

ALTER TABLE analytics.import_run
    ADD CONSTRAINT ck_analytics_import_request_sha256_live
        CHECK (request_sha256 IS NULL OR request_sha256 ~ '^[0-9a-f]{64}$')
        NOT VALID,
    ADD CONSTRAINT ck_analytics_import_page_hashes_live
        CHECK (
            jsonb_typeof(request_page_sha256s) = 'array'
        ) NOT VALID,
    ADD CONSTRAINT ck_analytics_import_config_snapshot_live
        CHECK (
            (configuration_snapshot IS NULL
             AND configuration_snapshot_sha256 IS NULL)
            OR
            (jsonb_typeof(configuration_snapshot) = 'object'
             AND configuration_snapshot_sha256 ~ '^[0-9a-f]{64}$')
        ) NOT VALID,
    ADD CONSTRAINT ck_analytics_import_revision_live
        CHECK (import_revision > 0) NOT VALID,
    ADD CONSTRAINT fk_analytics_import_predecessor_live
        FOREIGN KEY (predecessor_import_run_id)
        REFERENCES analytics.import_run(id)
        ON DELETE RESTRICT
        NOT VALID;

ALTER TABLE analytics.gsc_observation
    ALTER COLUMN country_code TYPE varchar(3)
        USING rtrim(country_code)::varchar(3),
    ADD COLUMN source_request_sha256 text,
    ADD COLUMN provider_data_state text DEFAULT 'final' NOT NULL,
    ADD COLUMN observation_revision bigint DEFAULT 1 NOT NULL,
    ADD COLUMN supersedes_observation_id uuid,
    ADD COLUMN is_current boolean DEFAULT true NOT NULL;

ALTER TABLE analytics.gsc_observation
    ADD CONSTRAINT ck_analytics_gsc_country_live
        CHECK (country_code IS NULL OR country_code ~ '^[a-z]{2,3}$') NOT VALID,
    ADD CONSTRAINT ck_analytics_gsc_request_sha256_live
        CHECK (
            source_request_sha256 IS NULL
            OR source_request_sha256 ~ '^[0-9a-f]{64}$'
        ) NOT VALID,
    ADD CONSTRAINT ck_analytics_gsc_data_state_live
        CHECK (provider_data_state IN ('all', 'final')) NOT VALID,
    ADD CONSTRAINT ck_analytics_gsc_revision_live
        CHECK (observation_revision > 0) NOT VALID,
    ADD CONSTRAINT ck_analytics_gsc_supersession_live
        CHECK (
            (observation_revision = 1 AND supersedes_observation_id IS NULL)
            OR
            (observation_revision > 1 AND supersedes_observation_id IS NOT NULL)
        ) NOT VALID,
    ADD CONSTRAINT fk_analytics_gsc_supersedes_live
        FOREIGN KEY (supersedes_observation_id)
        REFERENCES analytics.gsc_observation(id)
        ON DELETE RESTRICT
        NOT VALID;

ALTER TABLE analytics.ga4_observation
    ADD COLUMN property_id text,
    ADD COLUMN source_request_sha256 text,
    ADD COLUMN configuration_snapshot_sha256 text,
    ADD COLUMN observation_revision bigint DEFAULT 1 NOT NULL,
    ADD COLUMN supersedes_observation_id uuid,
    ADD COLUMN is_current boolean DEFAULT true NOT NULL;

ALTER TABLE analytics.ga4_observation
    ADD CONSTRAINT ck_analytics_ga4_property_live
        CHECK (property_id IS NULL OR property_id ~ '^[1-9][0-9]{0,19}$')
        NOT VALID,
    ADD CONSTRAINT ck_analytics_ga4_request_sha256_live
        CHECK (
            source_request_sha256 IS NULL
            OR source_request_sha256 ~ '^[0-9a-f]{64}$'
        ) NOT VALID,
    ADD CONSTRAINT ck_analytics_ga4_config_sha256_live
        CHECK (
            configuration_snapshot_sha256 IS NULL
            OR configuration_snapshot_sha256 ~ '^[0-9a-f]{64}$'
        ) NOT VALID,
    ADD CONSTRAINT ck_analytics_ga4_revision_live
        CHECK (observation_revision > 0) NOT VALID,
    ADD CONSTRAINT ck_analytics_ga4_supersession_live
        CHECK (
            (observation_revision = 1 AND supersedes_observation_id IS NULL)
            OR
            (observation_revision > 1 AND supersedes_observation_id IS NOT NULL)
        ) NOT VALID,
    ADD CONSTRAINT fk_analytics_ga4_supersedes_live
        FOREIGN KEY (supersedes_observation_id)
        REFERENCES analytics.ga4_observation(id)
        ON DELETE RESTRICT
        NOT VALID;

DROP INDEX analytics.ux_analytics_gsc_grain;
DROP INDEX analytics.ux_analytics_ga4_grain;

CREATE UNIQUE INDEX ux_analytics_gsc_current_grain_live
    ON analytics.gsc_observation (site_id, metric_date, dimension_key_sha256)
    WHERE is_current;
CREATE UNIQUE INDEX ux_analytics_gsc_grain_revision_live
    ON analytics.gsc_observation (
        site_id, metric_date, dimension_key_sha256, observation_revision
    );
CREATE UNIQUE INDEX ux_analytics_ga4_current_grain_live
    ON analytics.ga4_observation (site_id, metric_date, grain_key_sha256)
    WHERE is_current;
CREATE UNIQUE INDEX ux_analytics_ga4_grain_revision_live
    ON analytics.ga4_observation (
        site_id, metric_date, grain_key_sha256, observation_revision
    );
CREATE INDEX ix_analytics_import_predecessor_live
    ON analytics.import_run (predecessor_import_run_id);
CREATE INDEX ix_analytics_gsc_supersedes_live
    ON analytics.gsc_observation (supersedes_observation_id);
CREATE INDEX ix_analytics_ga4_supersedes_live
    ON analytics.ga4_observation (supersedes_observation_id);

ALTER TABLE analytics.import_run
    VALIDATE CONSTRAINT ck_analytics_import_request_sha256_live;
ALTER TABLE analytics.import_run
    VALIDATE CONSTRAINT ck_analytics_import_page_hashes_live;
ALTER TABLE analytics.import_run
    VALIDATE CONSTRAINT ck_analytics_import_config_snapshot_live;
ALTER TABLE analytics.import_run
    VALIDATE CONSTRAINT ck_analytics_import_revision_live;
ALTER TABLE analytics.import_run
    VALIDATE CONSTRAINT fk_analytics_import_predecessor_live;
ALTER TABLE analytics.gsc_observation
    VALIDATE CONSTRAINT ck_analytics_gsc_country_live;
ALTER TABLE analytics.gsc_observation
    VALIDATE CONSTRAINT ck_analytics_gsc_request_sha256_live;
ALTER TABLE analytics.gsc_observation
    VALIDATE CONSTRAINT ck_analytics_gsc_data_state_live;
ALTER TABLE analytics.gsc_observation
    VALIDATE CONSTRAINT ck_analytics_gsc_revision_live;
ALTER TABLE analytics.gsc_observation
    VALIDATE CONSTRAINT ck_analytics_gsc_supersession_live;
ALTER TABLE analytics.gsc_observation
    VALIDATE CONSTRAINT fk_analytics_gsc_supersedes_live;
ALTER TABLE analytics.ga4_observation
    VALIDATE CONSTRAINT ck_analytics_ga4_property_live;
ALTER TABLE analytics.ga4_observation
    VALIDATE CONSTRAINT ck_analytics_ga4_request_sha256_live;
ALTER TABLE analytics.ga4_observation
    VALIDATE CONSTRAINT ck_analytics_ga4_config_sha256_live;
ALTER TABLE analytics.ga4_observation
    VALIDATE CONSTRAINT ck_analytics_ga4_revision_live;
ALTER TABLE analytics.ga4_observation
    VALIDATE CONSTRAINT ck_analytics_ga4_supersession_live;
ALTER TABLE analytics.ga4_observation
    VALIDATE CONSTRAINT fk_analytics_ga4_supersedes_live;

COMMENT ON COLUMN analytics.import_run.provider_resource IS
    'Bound sc-domain URL or GA4 properties/{id}; credentials are never stored.';
COMMENT ON COLUMN analytics.import_run.request_sha256 IS
    'Canonical logical provider request hash excluding credentials and tokens.';
COMMENT ON COLUMN analytics.import_run.configuration_snapshot IS
    'GA4 property/reporting-identity snapshot captured with this import.';
COMMENT ON COLUMN analytics.gsc_observation.observation_revision IS
    'Append-only provider revision for one stable GSC grain.';
COMMENT ON COLUMN analytics.ga4_observation.observation_revision IS
    'Append-only provider revision for one stable GA4 grain.';

COMMIT;
