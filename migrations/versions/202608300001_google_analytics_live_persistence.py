"""Persist replay-safe live GSC and GA4 imports without raw GSC queries.

Revision ID: 202608300001
Revises: 202608030006
Create Date: 2026-08-30

RAOS metadata:
- story: ST-0305
- requirement IDs: FR-013, FR-015
- architecture: owner-authorized Google analytics persistence successor
- runner version: 1.6.0
- server version: 180004
- risk class: B (analytics table expansion and privacy-erasing query contraction)
- estimated lock: bounded ACCESS EXCLUSIVE DDL locks plus one legacy-row normalization
- backfill job: in-transaction legacy query hashing and page/country normalization
- rollback category: guarded structural rollback; erased raw queries are never restored
- transaction: one PostgreSQL transaction for the complete successor revision
- rollback: refused after any live-contract import or GA4 configuration snapshot
"""

from __future__ import annotations

from alembic import op


revision: str = "202608300001"
down_revision: str | None = "202608030006"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None
runner_version: str = "1.6.0"
story_id: str = "ST-0305"
server_version_num: int = 180004


UPGRADE_STATEMENTS: tuple[str, ...] = (
    "SET LOCAL lock_timeout = '5s'",
    "SET LOCAL statement_timeout = '60s'",
    """
    LOCK TABLE analytics.import_run,
               analytics.gsc_observation,
               analytics.ga4_observation
        IN ACCESS EXCLUSIVE MODE
    """,
    """
    UPDATE analytics.gsc_observation
       SET query_sha256 = pg_catalog.encode(
               pg_catalog.sha256(
                   pg_catalog.convert_to(query_text, 'UTF8')
               ),
               'hex'
           )
     WHERE query_text IS NOT NULL
    """,
    """
    UPDATE analytics.gsc_observation
       SET query_text = NULL
     WHERE query_text IS NOT NULL
    """,
    """
    UPDATE analytics.gsc_observation
       SET page_path = pg_catalog.split_part(
               pg_catalog.split_part(page_path, '?', 1), '#', 1
           )
     WHERE page_path IS NOT NULL
    """,
    """
    UPDATE analytics.gsc_observation
       SET country_code = pg_catalog.lower(
               pg_catalog.rtrim(country_code)
           )::pg_catalog.bpchar
     WHERE country_code IS NOT NULL
    """,
    """
    ALTER TABLE analytics.import_run
        ADD COLUMN live_contract_version pg_catalog.int2 DEFAULT 0 NOT NULL,
        ADD COLUMN request_sha256 pg_catalog.text,
        ADD COLUMN page_request_sha256s pg_catalog.jsonb
            DEFAULT '[]'::pg_catalog.jsonb NOT NULL,
        ADD COLUMN provider_resource_sha256 pg_catalog.text,
        ADD COLUMN provider_property_id pg_catalog.text,
        ADD COLUMN batch_sha256 pg_catalog.text,
        ADD COLUMN provider_retrieved_at pg_catalog.timestamptz,
        ADD COLUMN ga4_configuration_snapshot_id pg_catalog.uuid,
        ADD COLUMN provider_row_count pg_catalog.int8 DEFAULT 0 NOT NULL,
        ADD COLUMN unchanged_count pg_catalog.int8 DEFAULT 0 NOT NULL,
        ADD COLUMN superseded_count pg_catalog.int8 DEFAULT 0 NOT NULL
    """,
    """
    CREATE TABLE analytics.ga4_property_config_snapshot (
        id pg_catalog.uuid DEFAULT pg_catalog.uuidv7() NOT NULL,
        site_id pg_catalog.uuid NOT NULL,
        property_id pg_catalog.text NOT NULL,
        property_resource pg_catalog.text NOT NULL,
        display_name pg_catalog.text NOT NULL,
        time_zone pg_catalog.text NOT NULL,
        currency_code pg_catalog.text NOT NULL,
        reporting_identity pg_catalog.text NOT NULL,
        retrieved_at pg_catalog.timestamptz NOT NULL,
        property_response_sha256 pg_catalog.text NOT NULL,
        reporting_identity_response_sha256 pg_catalog.text NOT NULL,
        snapshot_sha256 pg_catalog.text NOT NULL,
        created_at pg_catalog.timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
        CONSTRAINT pk_analytics_ga4_property_config_snapshot PRIMARY KEY (id),
        CONSTRAINT fk_analytics_ga4_config_snapshot_site_id
            FOREIGN KEY (site_id) REFERENCES portfolio.site(id)
            ON DELETE RESTRICT,
        CONSTRAINT uq_analytics_ga4_config_snapshot_responses UNIQUE (
            site_id,
            property_id,
            property_response_sha256,
            reporting_identity_response_sha256
        ),
        CONSTRAINT ck_analytics_ga4_config_property_id CHECK (
            property_id ~ '^[1-9][0-9]{0,19}$'
        ),
        CONSTRAINT ck_analytics_ga4_config_property_resource CHECK (
            property_resource = 'properties/' || property_id
        ),
        CONSTRAINT ck_analytics_ga4_config_text CHECK (
            pg_catalog.length(display_name) BETWEEN 1 AND 256
            AND pg_catalog.length(time_zone) BETWEEN 1 AND 64
        ),
        CONSTRAINT ck_analytics_ga4_config_currency CHECK (
            currency_code ~ '^[A-Z]{3}$'
        ),
        CONSTRAINT ck_analytics_ga4_config_identity CHECK (
            reporting_identity IN ('DEVICE_BASED', 'BLENDED', 'OBSERVED')
        ),
        CONSTRAINT ck_analytics_ga4_config_hashes CHECK (
            property_response_sha256 ~ '^[0-9a-f]{64}$'
            AND reporting_identity_response_sha256 ~ '^[0-9a-f]{64}$'
            AND snapshot_sha256 ~ '^[0-9a-f]{64}$'
        )
    )
    """,
    """
    CREATE INDEX ix_analytics_ga4_config_snapshot_site
        ON analytics.ga4_property_config_snapshot (site_id, property_id)
    """,
    """
    CREATE TRIGGER trg_analytics_ga4_config_snapshot_immutable
        BEFORE UPDATE OR DELETE
        ON analytics.ga4_property_config_snapshot
        FOR EACH ROW EXECUTE FUNCTION ops.reject_immutable_mutation()
    """,
    """
    ALTER TABLE analytics.import_run
        ADD CONSTRAINT fk_analytics_import_ga4_config_snapshot_live
            FOREIGN KEY (ga4_configuration_snapshot_id)
            REFERENCES analytics.ga4_property_config_snapshot(id)
            ON DELETE RESTRICT,
        ADD CONSTRAINT ck_analytics_import_live_version CHECK (
            live_contract_version IN (0, 1)
        ),
        ADD CONSTRAINT ck_analytics_import_live_hashes CHECK (
            live_contract_version = 0 OR (
                request_sha256 ~ '^[0-9a-f]{64}$'
                AND provider_resource_sha256 ~ '^[0-9a-f]{64}$'
                AND batch_sha256 ~ '^[0-9a-f]{64}$'
            )
        ),
        ADD CONSTRAINT ck_analytics_import_live_page_hashes CHECK (
            pg_catalog.jsonb_typeof(page_request_sha256s) = 'array'
            AND (
                live_contract_version = 0
                OR pg_catalog.jsonb_array_length(page_request_sha256s) > 0
            )
        ),
        ADD CONSTRAINT ck_analytics_import_live_counts CHECK (
            provider_row_count >= 0
            AND unchanged_count >= 0
            AND superseded_count >= 0
            AND (
                live_contract_version = 0
                OR status <> 'SUCCEEDED'
                OR (
                    rejected_count = 0
                    AND provider_row_count = row_count
                    AND row_count = inserted_count + unchanged_count
                    AND superseded_count <= inserted_count
                )
            )
        ),
        ADD CONSTRAINT ck_analytics_import_live_source_binding CHECK (
            live_contract_version = 0 OR (
                provider_retrieved_at IS NOT NULL
                AND (
                    (
                        source_type = 'GSC'
                        AND provider_property_id IS NULL
                        AND ga4_configuration_snapshot_id IS NULL
                    )
                    OR (
                        source_type = 'GA4'
                        AND provider_property_id ~ '^[1-9][0-9]{0,19}$'
                        AND ga4_configuration_snapshot_id IS NOT NULL
                    )
                )
            )
        )
    """,
    """
    CREATE INDEX ix_analytics_import_ga4_config_snapshot_live
        ON analytics.import_run (ga4_configuration_snapshot_id)
        WHERE ga4_configuration_snapshot_id IS NOT NULL
    """,
    """
    ALTER TABLE analytics.gsc_observation
        RENAME COLUMN query_text TO query_material_forbidden
    """,
    """
    ALTER TABLE analytics.gsc_observation
        ALTER COLUMN country_code TYPE pg_catalog.varchar(3)
            USING pg_catalog.rtrim(country_code)::pg_catalog.varchar(3),
        ADD COLUMN page_url_sha256 pg_catalog.text,
        ADD COLUMN source_request_sha256 pg_catalog.text,
        ADD COLUMN content_sha256 pg_catalog.text,
        ADD COLUMN observation_revision pg_catalog.int8 DEFAULT 1 NOT NULL,
        ADD COLUMN supersedes_observation_id pg_catalog.uuid,
        ADD COLUMN is_current pg_catalog.bool DEFAULT true NOT NULL,
        ADD COLUMN superseded_by_import_run_id pg_catalog.uuid,
        ADD COLUMN superseded_at pg_catalog.timestamptz,
        ADD COLUMN live_contract_version pg_catalog.int2 DEFAULT 0 NOT NULL
    """,
    "DROP INDEX analytics.ux_analytics_gsc_grain",
    """
    ALTER TABLE analytics.gsc_observation
        ADD CONSTRAINT fk_analytics_gsc_supersedes_live
            FOREIGN KEY (supersedes_observation_id)
            REFERENCES analytics.gsc_observation(id) ON DELETE RESTRICT,
        ADD CONSTRAINT fk_analytics_gsc_superseded_by_import_live
            FOREIGN KEY (superseded_by_import_run_id)
            REFERENCES analytics.import_run(id) ON DELETE RESTRICT,
        ADD CONSTRAINT ck_analytics_gsc_live_version CHECK (
            live_contract_version IN (0, 1)
        ),
        ADD CONSTRAINT ck_analytics_gsc_query_material_forbidden CHECK (
            query_material_forbidden IS NULL
        ),
        ADD CONSTRAINT ck_analytics_gsc_country_live CHECK (
            country_code IS NULL OR country_code ~ '^[a-z]{2,3}$'
        ),
        ADD CONSTRAINT ck_analytics_gsc_revision_live CHECK (
            observation_revision > 0
            AND (
                (observation_revision = 1 AND supersedes_observation_id IS NULL)
                OR (
                    observation_revision > 1
                    AND supersedes_observation_id IS NOT NULL
                )
            )
        ),
        ADD CONSTRAINT ck_analytics_gsc_current_live CHECK (
            (
                is_current
                AND superseded_by_import_run_id IS NULL
                AND superseded_at IS NULL
            ) OR (
                NOT is_current
                AND superseded_by_import_run_id IS NOT NULL
                AND superseded_at IS NOT NULL
            )
        ),
        ADD CONSTRAINT ck_analytics_gsc_live_shape CHECK (
            live_contract_version = 0 OR (
                query_sha256 ~ '^[0-9a-f]{64}$'
                AND page_url_sha256 ~ '^[0-9a-f]{64}$'
                AND country_code ~ '^[a-z]{3}$'
                AND device IN ('MOBILE', 'DESKTOP', 'TABLET')
                AND source_request_sha256 ~ '^[0-9a-f]{64}$'
                AND content_sha256 ~ '^[0-9a-f]{64}$'
            )
        )
    """,
    """
    CREATE UNIQUE INDEX ux_analytics_gsc_current_grain_live
        ON analytics.gsc_observation (
            site_id, metric_date, dimension_key_sha256
        ) WHERE is_current
    """,
    """
    CREATE UNIQUE INDEX ux_analytics_gsc_grain_revision_live
        ON analytics.gsc_observation (
            site_id,
            metric_date,
            dimension_key_sha256,
            observation_revision
        )
    """,
    """
    CREATE INDEX ix_analytics_gsc_supersedes_live
        ON analytics.gsc_observation (supersedes_observation_id)
        WHERE supersedes_observation_id IS NOT NULL
    """,
    """
    CREATE INDEX ix_analytics_gsc_superseded_by_import_live
        ON analytics.gsc_observation (superseded_by_import_run_id)
        WHERE superseded_by_import_run_id IS NOT NULL
    """,
    """
    ALTER TABLE analytics.ga4_observation
        ADD COLUMN property_id pg_catalog.text,
        ADD COLUMN source_request_sha256 pg_catalog.text,
        ADD COLUMN content_sha256 pg_catalog.text,
        ADD COLUMN observation_revision pg_catalog.int8 DEFAULT 1 NOT NULL,
        ADD COLUMN supersedes_observation_id pg_catalog.uuid,
        ADD COLUMN is_current pg_catalog.bool DEFAULT true NOT NULL,
        ADD COLUMN superseded_by_import_run_id pg_catalog.uuid,
        ADD COLUMN superseded_at pg_catalog.timestamptz,
        ADD COLUMN live_contract_version pg_catalog.int2 DEFAULT 0 NOT NULL
    """,
    "DROP INDEX analytics.ux_analytics_ga4_grain",
    """
    ALTER TABLE analytics.ga4_observation
        ADD CONSTRAINT fk_analytics_ga4_supersedes_live
            FOREIGN KEY (supersedes_observation_id)
            REFERENCES analytics.ga4_observation(id) ON DELETE RESTRICT,
        ADD CONSTRAINT fk_analytics_ga4_superseded_by_import_live
            FOREIGN KEY (superseded_by_import_run_id)
            REFERENCES analytics.import_run(id) ON DELETE RESTRICT,
        ADD CONSTRAINT ck_analytics_ga4_live_version CHECK (
            live_contract_version IN (0, 1)
        ),
        ADD CONSTRAINT ck_analytics_ga4_revision_live CHECK (
            observation_revision > 0
            AND (
                (observation_revision = 1 AND supersedes_observation_id IS NULL)
                OR (
                    observation_revision > 1
                    AND supersedes_observation_id IS NOT NULL
                )
            )
        ),
        ADD CONSTRAINT ck_analytics_ga4_current_live CHECK (
            (
                is_current
                AND superseded_by_import_run_id IS NULL
                AND superseded_at IS NULL
            ) OR (
                NOT is_current
                AND superseded_by_import_run_id IS NOT NULL
                AND superseded_at IS NOT NULL
            )
        ),
        ADD CONSTRAINT ck_analytics_ga4_live_shape CHECK (
            live_contract_version = 0 OR (
                property_id ~ '^[1-9][0-9]{0,19}$'
                AND source_request_sha256 ~ '^[0-9a-f]{64}$'
                AND content_sha256 ~ '^[0-9a-f]{64}$'
            )
        )
    """,
    """
    CREATE UNIQUE INDEX ux_analytics_ga4_current_grain_live
        ON analytics.ga4_observation (
            site_id, metric_date, grain_key_sha256
        ) WHERE is_current
    """,
    """
    CREATE UNIQUE INDEX ux_analytics_ga4_grain_revision_live
        ON analytics.ga4_observation (
            site_id,
            metric_date,
            grain_key_sha256,
            observation_revision
        )
    """,
    """
    CREATE INDEX ix_analytics_ga4_supersedes_live
        ON analytics.ga4_observation (supersedes_observation_id)
        WHERE supersedes_observation_id IS NOT NULL
    """,
    """
    CREATE INDEX ix_analytics_ga4_superseded_by_import_live
        ON analytics.ga4_observation (superseded_by_import_run_id)
        WHERE superseded_by_import_run_id IS NOT NULL
    """,
    """
    REVOKE ALL ON TABLE analytics.ga4_property_config_snapshot
        FROM PUBLIC,
             raos_api_rw,
             raos_worker_rw,
             raos_dispatcher_rw,
             raos_projection_rw,
             raos_public_ro,
             raos_reporting_ro,
             raos_auditor_ro
    """,
    """
    GRANT SELECT, INSERT
        ON TABLE analytics.ga4_property_config_snapshot
        TO raos_worker_rw
    """,
    """
    GRANT SELECT
        ON TABLE analytics.ga4_property_config_snapshot
        TO raos_api_rw,
           raos_projection_rw,
           raos_reporting_ro,
           raos_auditor_ro
    """,
    """
    ALTER TABLE analytics.gsc_observation
        ALTER COLUMN live_contract_version SET DEFAULT 1
    """,
    """
    ALTER TABLE analytics.ga4_observation
        ALTER COLUMN live_contract_version SET DEFAULT 1
    """,
    """
    COMMENT ON TABLE analytics.ga4_property_config_snapshot IS
        'Immutable GA4 property and reporting-identity response snapshot.'
    """,
    """
    COMMENT ON COLUMN analytics.import_run.batch_sha256 IS
        'Canonical normalized batch fingerprint used for exact replay.'
    """,
    """
    COMMENT ON COLUMN analytics.import_run.unchanged_count IS
        'Rows whose current persisted content hash was unchanged.'
    """,
    """
    COMMENT ON COLUMN analytics.import_run.superseded_count IS
        'Prior current rows superseded by rows inserted by this import.'
    """,
)


DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    "SET LOCAL lock_timeout = '5s'",
    "SET LOCAL statement_timeout = '60s'",
    """
    LOCK TABLE analytics.import_run,
               analytics.gsc_observation,
               analytics.ga4_observation,
               analytics.ga4_property_config_snapshot
        IN ACCESS EXCLUSIVE MODE
    """,
    """
    DO $raos_google_live_downgrade$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM analytics.import_run
             WHERE live_contract_version = 1
        ) OR EXISTS (
            SELECT 1 FROM analytics.gsc_observation
             WHERE live_contract_version = 1
        ) OR EXISTS (
            SELECT 1 FROM analytics.ga4_observation
             WHERE live_contract_version = 1
        ) OR EXISTS (
            SELECT 1 FROM analytics.ga4_property_config_snapshot
        ) THEN
            RAISE EXCEPTION USING
                ERRCODE = '55000',
                MESSAGE =
                    'live Google analytics state exists; use forward recovery';
        END IF;
    END
    $raos_google_live_downgrade$
    """,
    "DROP INDEX analytics.ix_analytics_ga4_superseded_by_import_live",
    "DROP INDEX analytics.ix_analytics_ga4_supersedes_live",
    "DROP INDEX analytics.ux_analytics_ga4_grain_revision_live",
    "DROP INDEX analytics.ux_analytics_ga4_current_grain_live",
    """
    ALTER TABLE analytics.ga4_observation
        DROP CONSTRAINT ck_analytics_ga4_live_shape,
        DROP CONSTRAINT ck_analytics_ga4_current_live,
        DROP CONSTRAINT ck_analytics_ga4_revision_live,
        DROP CONSTRAINT ck_analytics_ga4_live_version,
        DROP CONSTRAINT fk_analytics_ga4_superseded_by_import_live,
        DROP CONSTRAINT fk_analytics_ga4_supersedes_live,
        DROP COLUMN live_contract_version,
        DROP COLUMN superseded_at,
        DROP COLUMN superseded_by_import_run_id,
        DROP COLUMN is_current,
        DROP COLUMN supersedes_observation_id,
        DROP COLUMN observation_revision,
        DROP COLUMN content_sha256,
        DROP COLUMN source_request_sha256,
        DROP COLUMN property_id
    """,
    """
    CREATE UNIQUE INDEX ux_analytics_ga4_grain
        ON analytics.ga4_observation (
            site_id, metric_date, grain_key_sha256
        )
    """,
    "DROP INDEX analytics.ix_analytics_gsc_superseded_by_import_live",
    "DROP INDEX analytics.ix_analytics_gsc_supersedes_live",
    "DROP INDEX analytics.ux_analytics_gsc_grain_revision_live",
    "DROP INDEX analytics.ux_analytics_gsc_current_grain_live",
    """
    ALTER TABLE analytics.gsc_observation
        DROP CONSTRAINT ck_analytics_gsc_live_shape,
        DROP CONSTRAINT ck_analytics_gsc_current_live,
        DROP CONSTRAINT ck_analytics_gsc_revision_live,
        DROP CONSTRAINT ck_analytics_gsc_country_live,
        DROP CONSTRAINT ck_analytics_gsc_query_material_forbidden,
        DROP CONSTRAINT ck_analytics_gsc_live_version,
        DROP CONSTRAINT fk_analytics_gsc_superseded_by_import_live,
        DROP CONSTRAINT fk_analytics_gsc_supersedes_live,
        DROP COLUMN live_contract_version,
        DROP COLUMN superseded_at,
        DROP COLUMN superseded_by_import_run_id,
        DROP COLUMN is_current,
        DROP COLUMN supersedes_observation_id,
        DROP COLUMN observation_revision,
        DROP COLUMN content_sha256,
        DROP COLUMN source_request_sha256,
        DROP COLUMN page_url_sha256,
        ALTER COLUMN country_code TYPE pg_catalog.bpchar(2)
            USING country_code::pg_catalog.bpchar(2)
    """,
    """
    ALTER TABLE analytics.gsc_observation
        RENAME COLUMN query_material_forbidden TO query_text
    """,
    """
    CREATE UNIQUE INDEX ux_analytics_gsc_grain
        ON analytics.gsc_observation (
            site_id, metric_date, dimension_key_sha256
        )
    """,
    "DROP INDEX analytics.ix_analytics_import_ga4_config_snapshot_live",
    """
    ALTER TABLE analytics.import_run
        DROP CONSTRAINT ck_analytics_import_live_source_binding,
        DROP CONSTRAINT ck_analytics_import_live_counts,
        DROP CONSTRAINT ck_analytics_import_live_page_hashes,
        DROP CONSTRAINT ck_analytics_import_live_hashes,
        DROP CONSTRAINT ck_analytics_import_live_version,
        DROP CONSTRAINT fk_analytics_import_ga4_config_snapshot_live,
        DROP COLUMN superseded_count,
        DROP COLUMN unchanged_count,
        DROP COLUMN provider_row_count,
        DROP COLUMN ga4_configuration_snapshot_id,
        DROP COLUMN provider_retrieved_at,
        DROP COLUMN batch_sha256,
        DROP COLUMN provider_property_id,
        DROP COLUMN provider_resource_sha256,
        DROP COLUMN page_request_sha256s,
        DROP COLUMN request_sha256,
        DROP COLUMN live_contract_version
    """,
    "DROP TABLE analytics.ga4_property_config_snapshot RESTRICT",
)


def _execute(statements: tuple[str, ...]) -> None:
    connection = op.get_bind().execution_options(no_parameters=True)
    for statement in statements:
        connection.exec_driver_sql(statement)


def upgrade() -> None:
    _execute(UPGRADE_STATEMENTS)


def downgrade() -> None:
    _execute(DOWNGRADE_STATEMENTS)
