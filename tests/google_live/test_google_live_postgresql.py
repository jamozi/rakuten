from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
from pathlib import Path
from uuid import UUID

import pytest
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL

from raos.adapters.persistence.sqlalchemy.google_live import (
    SqlAlchemyAnalyticsImportRepository,
)
from raos.adapters.persistence.sqlalchemy.identity import WorkloadProfile
from raos.adapters.persistence.sqlalchemy.provider import SqlAlchemyEngineProvider
from raos.domain.analytics.google_live import (
    GA4_BASELINE_DIMENSIONS,
    GA4_BASELINE_METRICS,
    Ga4ImportBatch,
    Ga4Observation,
    Ga4PropertyConfigSnapshot,
    GoogleImportExecutionContext,
    SearchConsoleImportBatch,
    SearchConsoleObservation,
    canonical_json_bytes,
    sha256_hex,
)
from raos.migrations import MigrationError, catalog, runner
from tests.postgresql18 import PostgreSQLCluster


pytestmark = [pytest.mark.database, pytest.mark.serial]
ROOT = Path(__file__).resolve().parents[2]
SITE_ID = UUID("0198f8c4-1000-7000-8000-000000000001")
GSC_JOB_IDS = (
    UUID("0198f8c4-1000-7000-8000-000000000011"),
    UUID("0198f8c4-1000-7000-8000-000000000012"),
    UUID("0198f8c4-1000-7000-8000-000000000013"),
)
GA4_JOB_ID = UUID("0198f8c4-1000-7000-8000-000000000014")
NOW = datetime(2026, 8, 30, 4, 0, tzinfo=timezone.utc)


def _upgrade(cluster: PostgreSQLCluster, database: str) -> None:
    result = runner.MigrationRunner(ROOT, cluster.target(database)).upgrade()
    assert result.current_revision == catalog.GOOGLE_ANALYTICS_LIVE_REVISION


def _worker_engine(cluster: PostgreSQLCluster, database: str) -> Engine:
    digest = hashlib.sha256(database.encode("utf-8")).hexdigest()[:16]
    login = f"google_worker_{digest}"
    with cluster.connect(database) as connection:
        connection.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN INHERIT NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOREPLICATION NOBYPASSRLS"
            ).format(sql.Identifier(login))
        )
        connection.execute(
            sql.SQL("GRANT raos_worker_rw TO {} WITH INHERIT TRUE, SET FALSE").format(
                sql.Identifier(login)
            )
        )
    hba_path = cluster.data_directory / "pg_hba.conf"
    current = hba_path.read_text(encoding="utf-8")
    hba_path.write_text(f"local {database} {login} trust\n{current}", encoding="utf-8")
    cluster.run("pg_ctl", ["--pgdata", str(cluster.data_directory), "reload"])
    engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username=login,
            host=str(cluster.socket_directory),
            port=cluster.port,
            database=database,
        ),
        pool_size=2,
        max_overflow=0,
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT current_user")).scalar_one() == login
    return engine


def _seed_scope(cluster: PostgreSQLCluster, database: str) -> None:
    with cluster.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO portfolio.site (
                id, display_id, site_code, name, primary_domain, brand_name,
                status
            ) VALUES (
                %s, 'SITE-GOOGLE-LIVE', 'google-live', 'Google live test',
                'google-live.example.test', 'Test', 'ACTIVE'
            )
            """,
            (SITE_ID,),
        )
        for index, job_id in enumerate((*GSC_JOB_IDS, GA4_JOB_ID), start=1):
            connection.execute(
                """
                INSERT INTO ops.job (
                    id, display_id, job_type, queue_name, status, site_id,
                    created_by_actor_type
                ) VALUES (%s, %s, 'GOOGLE_ANALYTICS_IMPORT', 'analytics',
                          'REQUESTED', %s, 'SERVICE')
                """,
                (job_id, f"JOB-GOOGLE-{index}", SITE_ID),
            )


def _context(job_index: int, display_id: str) -> GoogleImportExecutionContext:
    return GoogleImportExecutionContext(
        display_id=display_id,
        site_id=SITE_ID,
        ops_job_id=GSC_JOB_IDS[job_index],
        started_at=NOW,
    )


def _gsc_batch(*, clicks: int) -> SearchConsoleImportBatch:
    metric_date = date(2026, 8, 29)
    query_text = "比較対象の秘密クエリ"
    page_url = "https://google-live.example.test/guide/?token=never-store"
    page_request = "1" * 64
    grain = sha256_hex(
        canonical_json_bytes(
            {
                "country": "jpn",
                "date": metric_date.isoformat(),
                "device": "MOBILE",
                "page": page_url,
                "query": query_text,
            }
        )
    )
    return SearchConsoleImportBatch(
        site_id=SITE_ID,
        site_url="sc-domain:google-live.example.test",
        date_from=metric_date,
        date_to=metric_date,
        request_sha256="2" * 64,
        page_request_sha256s=(page_request,),
        rows=(
            SearchConsoleObservation(
                metric_date=metric_date,
                query_text=query_text,
                page_url=page_url,
                country_code="jpn",
                device="MOBILE",
                clicks=clicks,
                impressions=10,
                ctr=float(clicks / 10),
                average_position=2.5,
                dimension_key_sha256=grain,
                source_request_sha256=page_request,
            ),
        ),
        retrieved_at=NOW,
        provider_row_count=1,
    )


def _ga4_batch() -> Ga4ImportBatch:
    metric_date = date(2026, 8, 29)
    dimensions = tuple(
        zip(
            GA4_BASELINE_DIMENSIONS,
            (
                "20260829",
                "/guide/",
                "affiliate_click",
                "mobile",
                "article-001",
            ),
            strict=True,
        )
    )
    metrics = tuple(zip(GA4_BASELINE_METRICS, ("2", "1", "1"), strict=True))
    grain = sha256_hex(
        canonical_json_bytes(
            {"date": metric_date.isoformat(), "dimensions": dict(dimensions)}
        )
    )
    snapshot_sha256 = sha256_hex(
        canonical_json_bytes(
            {
                "currency_code": "JPY",
                "display_name": "Production-like test",
                "property_resource": "properties/123456",
                "reporting_identity": "BLENDED",
                "time_zone": "Asia/Tokyo",
            }
        )
    )
    configuration = Ga4PropertyConfigSnapshot(
        property_id="123456",
        property_resource="properties/123456",
        display_name="Production-like test",
        time_zone="Asia/Tokyo",
        currency_code="JPY",
        reporting_identity="BLENDED",
        retrieved_at=NOW,
        property_response_sha256="4" * 64,
        reporting_identity_response_sha256="5" * 64,
        snapshot_sha256=snapshot_sha256,
    )
    page_request = "3" * 64
    return Ga4ImportBatch(
        site_id=SITE_ID,
        property_id="123456",
        date_from=metric_date,
        date_to=metric_date,
        dimensions=GA4_BASELINE_DIMENSIONS,
        metrics=GA4_BASELINE_METRICS,
        request_sha256="6" * 64,
        page_request_sha256s=(page_request,),
        rows=(
            Ga4Observation(
                metric_date=metric_date,
                dimensions=dimensions,
                metrics=metrics,
                grain_key_sha256=grain,
                source_request_sha256=page_request,
                is_thresholded=False,
            ),
        ),
        configuration=configuration,
        retrieved_at=NOW,
        provider_row_count=1,
        subject_to_thresholding=False,
        data_loss_from_other_row=False,
    )


def test_empty_successor_downgrade_and_reupgrade_are_structurally_reversible(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    instance = runner.MigrationRunner(ROOT, postgresql_cluster.target(empty_database))
    downgraded = instance.downgrade()
    assert downgraded.current_revision == catalog.DATABASE_ROLES_REVISION
    upgraded = instance.upgrade()
    assert upgraded.current_revision == catalog.GOOGLE_ANALYTICS_LIVE_REVISION


def test_atomic_replay_unchanged_supersession_and_no_raw_query_persistence(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    _seed_scope(postgresql_cluster, empty_database)
    engine = _worker_engine(postgresql_cluster, empty_database)
    repository = SqlAlchemyAnalyticsImportRepository(
        SqlAlchemyEngineProvider(engine, WorkloadProfile.WORKER_COMMAND)
    )
    try:
        first_context = _context(0, "AIR-GSC-FIRST")
        first_batch = _gsc_batch(clicks=3)
        first = repository.commit_gsc(context=first_context, batch=first_batch)
        assert (
            first.inserted_count,
            first.unchanged_count,
            first.superseded_count,
        ) == (
            1,
            0,
            0,
        )
        assert repository.commit_gsc(context=first_context, batch=first_batch) == first

        unchanged = repository.commit_gsc(
            context=_context(1, "AIR-GSC-UNCHANGED"), batch=first_batch
        )
        assert (
            unchanged.inserted_count,
            unchanged.unchanged_count,
            unchanged.superseded_count,
        ) == (0, 1, 0)

        revised = repository.commit_gsc(
            context=_context(2, "AIR-GSC-REVISED"), batch=_gsc_batch(clicks=4)
        )
        assert (
            revised.inserted_count,
            revised.unchanged_count,
            revised.superseded_count,
        ) == (1, 0, 1)

        ga4 = repository.commit_ga4(
            context=GoogleImportExecutionContext(
                display_id="AIR-GA4-FIRST",
                site_id=SITE_ID,
                ops_job_id=GA4_JOB_ID,
                started_at=NOW,
            ),
            batch=_ga4_batch(),
        )
        assert (ga4.inserted_count, ga4.unchanged_count, ga4.superseded_count) == (
            1,
            0,
            0,
        )

        with postgresql_cluster.connect(empty_database) as connection:
            assert connection.execute(
                """
                SELECT count(*)
                  FROM information_schema.columns
                 WHERE table_schema = 'analytics'
                   AND table_name = 'gsc_observation'
                   AND column_name = 'query_text'
                """
            ).fetchone() == (0,)
            query_sha256 = hashlib.sha256(
                first_batch.rows[0].query_text.encode("utf-8")
            ).hexdigest()
            assert connection.execute(
                """
                SELECT query_sha256, page_path, observation_revision, is_current
                  FROM analytics.gsc_observation
                 ORDER BY observation_revision
                """
            ).fetchall() == [
                (query_sha256, "/guide/", 1, False),
                (query_sha256, "/guide/", 2, True),
            ]
            assert connection.execute(
                """
                SELECT display_id, inserted_count, unchanged_count,
                       superseded_count
                  FROM analytics.import_run
                 ORDER BY display_id
                """
            ).fetchall() == [
                ("AIR-GA4-FIRST", 1, 0, 0),
                ("AIR-GSC-FIRST", 1, 0, 0),
                ("AIR-GSC-REVISED", 1, 0, 1),
                ("AIR-GSC-UNCHANGED", 0, 1, 0),
            ]
            assert connection.execute(
                """
                SELECT property_id, property_response_sha256,
                       reporting_identity_response_sha256, snapshot_sha256
                  FROM analytics.ga4_property_config_snapshot
                """
            ).fetchone() == (
                "123456",
                "4" * 64,
                "5" * 64,
                _ga4_batch().configuration.snapshot_sha256,
            )
    finally:
        engine.dispose()
    instance = runner.MigrationRunner(ROOT, postgresql_cluster.target(empty_database))
    with pytest.raises(MigrationError) as raised:
        instance.downgrade()
    assert raised.value.code is runner.MigrationErrorCode.MIGRATION_FAILED
    assert instance.status().current_revision == catalog.GOOGLE_ANALYTICS_LIVE_REVISION
