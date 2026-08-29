from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATABASE = ROOT / "changes" / "analytics-google-live-v1" / "database"
EXPAND = DATABASE / "202608300001_google_analytics_live_expand.sql"
DOWNGRADE = DATABASE / "202608300001_google_analytics_live_guarded_downgrade.sql"


def test_successor_migration_covers_live_identity_hashes_and_late_revisions() -> None:
    sql = EXPAND.read_text(encoding="utf-8")
    assert "ALTER COLUMN country_code TYPE varchar(3)" in sql
    assert "ADD COLUMN property_id text" in sql
    assert "ADD COLUMN request_sha256 text" in sql
    assert "ADD COLUMN request_page_sha256s jsonb" in sql
    assert "ADD COLUMN configuration_snapshot jsonb" in sql
    assert "ADD COLUMN configuration_snapshot_sha256 text" in sql
    assert sql.count("ADD COLUMN observation_revision bigint") == 2
    assert sql.count("ADD COLUMN supersedes_observation_id uuid") == 2
    assert sql.count("WHERE is_current") == 2
    assert "DROP INDEX analytics.ux_analytics_gsc_grain" in sql
    assert "DROP INDEX analytics.ux_analytics_ga4_grain" in sql
    assert "private_key" not in sql.lower()
    assert "client_email" not in sql.lower()


def test_downgrade_is_transactional_guarded_and_never_cascades() -> None:
    sql = DOWNGRADE.read_text(encoding="utf-8")
    assert sql.startswith("-- Guarded rollback")
    assert "BEGIN;" in sql and "COMMIT;" in sql
    assert "RAISE EXCEPTION" in sql
    assert "ACCESS EXCLUSIVE" in sql
    assert " CASCADE" not in sql.upper()
    assert "observation_revision <> 1" in sql
    assert "length(country_code) > 2" in sql
