from __future__ import annotations

import hashlib
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from raos.migrations import catalog


ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_REVISION = (
    ROOT
    / "migrations"
    / "versions"
    / "202608300001_google_analytics_live_persistence.py"
)


def test_successor_migration_covers_live_identity_hashes_and_late_revisions() -> None:
    sql = ALEMBIC_REVISION.read_text(encoding="utf-8")
    assert "ALTER COLUMN country_code TYPE pg_catalog.varchar(3)" in sql
    assert "ADD COLUMN property_id pg_catalog.text" in sql
    assert "ADD COLUMN request_sha256 pg_catalog.text" in sql
    assert "ADD COLUMN page_request_sha256s pg_catalog.jsonb" in sql
    assert "CREATE TABLE analytics.ga4_property_config_snapshot" in sql
    assert "ADD COLUMN ga4_configuration_snapshot_id pg_catalog.uuid" in sql
    assert sql.count("ADD COLUMN observation_revision pg_catalog.int8") == 2
    assert sql.count("ADD COLUMN supersedes_observation_id pg_catalog.uuid") == 2
    assert sql.count("WHERE is_current") == 2
    assert "DROP INDEX analytics.ux_analytics_gsc_grain" in sql
    assert "DROP INDEX analytics.ux_analytics_ga4_grain" in sql
    assert "private_key" not in sql.lower()
    assert "client_email" not in sql.lower()


def test_downgrade_is_transactional_guarded_and_never_cascades() -> None:
    sql = ALEMBIC_REVISION.read_text(encoding="utf-8")
    assert "DOWNGRADE_STATEMENTS" in sql
    assert "RAISE EXCEPTION" in sql
    assert "ACCESS EXCLUSIVE" in sql
    assert " CASCADE" not in sql.upper()
    assert sql.count("WHERE live_contract_version = 1") == 3
    assert "SELECT 1 FROM analytics.ga4_property_config_snapshot" in sql


def test_real_successor_is_checksum_registered_as_the_single_alembic_head() -> None:
    source = ALEMBIC_REVISION.read_bytes()
    spec = catalog.REVISION_SPECS[-1]
    configuration = Config()
    configuration.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(configuration)

    assert spec.revision == catalog.GOOGLE_ANALYTICS_LIVE_REVISION == "202608300001"
    assert spec.down_revision == catalog.DATABASE_ROLES_REVISION
    assert spec.relative_path == ALEMBIC_REVISION.relative_to(ROOT)
    assert spec.sha256 == hashlib.sha256(source).hexdigest()
    assert spec.runner_version == catalog.RUNNER_VERSION == "1.6.0"
    assert catalog.HEAD_REVISION == spec.revision
    assert script.get_heads() == [spec.revision]


def test_real_successor_removes_raw_query_and_persists_reproducible_results() -> None:
    source = ALEMBIC_REVISION.read_text(encoding="utf-8")
    assert "pg_catalog.sha256" in source
    assert "RENAME COLUMN query_text TO query_material_forbidden" in source
    assert "query_material_forbidden IS NULL" in source
    assert "ADD COLUMN unchanged_count" in source
    assert "ADD COLUMN superseded_count" in source
    assert "ADD COLUMN batch_sha256" in source
    assert "ga4_property_config_snapshot" in source
    assert "property_response_sha256" in source
    assert "reporting_identity_response_sha256" in source
    assert "ux_analytics_gsc_current_grain_live" in source
    assert "ux_analytics_ga4_current_grain_live" in source
    assert "live Google analytics state exists; use forward recovery" in source
    assert " CASCADE" not in source.upper()
