from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Event
from time import monotonic
import hashlib
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.google_live import (
    SqlAlchemyAnalyticsImportRepository,
    _configuration_snapshot_id,
)
from raos.adapters.persistence.sqlalchemy.identity import WorkloadProfile
from raos.adapters.persistence.sqlalchemy.provider import SqlAlchemyEngineProvider
from raos.domain.analytics.google_live import (
    GA4_IMPORT_JOB_TYPE,
    GA4_BASELINE_DIMENSIONS,
    GA4_BASELINE_METRICS,
    GA4_EVENT_PARAMETER_NAMES,
    GSC_IMPORT_JOB_TYPE,
    Ga4ImportBatch,
    Ga4Observation,
    Ga4PropertyConfigSnapshot,
    GoogleImportExecutionContext,
    GoogleProviderFailure,
    GoogleProviderFailureCode,
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
        jobs = tuple((job_id, GSC_IMPORT_JOB_TYPE) for job_id in GSC_JOB_IDS) + (
            (GA4_JOB_ID, GA4_IMPORT_JOB_TYPE),
        )
        for index, (job_id, job_type) in enumerate(jobs, start=1):
            connection.execute(
                """
                INSERT INTO ops.job (
                    id, display_id, job_type, queue_name, status, site_id,
                    created_by_actor_type
                ) VALUES (%s, %s, %s, 'analytics',
                          'REQUESTED', %s, 'SERVICE')
                """,
                (job_id, f"JOB-GOOGLE-{index}", job_type, SITE_ID),
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
    page_url = "https://google-live.example.test/guide/?private=never-store"
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


def _ga4_batch(*, display_name: str = "Production-like test") -> Ga4ImportBatch:
    metric_date = date(2026, 8, 29)
    dimensions = tuple(
        zip(
            GA4_BASELINE_DIMENSIONS,
            (
                "20260829",
                "/guide/",
                "affiliate_click",
                "article-001",
                "snapshot-001",
                "cta-001",
                "offer-001",
                "product-001",
                "product_card",
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
                "display_name": display_name,
                "property_resource": "properties/123456",
                "required_event_custom_dimensions": list(GA4_EVENT_PARAMETER_NAMES),
                "reporting_identity": "BLENDED",
                "time_zone": "Asia/Tokyo",
            }
        )
    )
    configuration = Ga4PropertyConfigSnapshot(
        property_id="123456",
        property_resource="properties/123456",
        display_name=display_name,
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


@pytest.mark.parametrize(
    "drift",
    (
        "ALTER TABLE analytics.import_run ALTER COLUMN error_summary SET DEFAULT 'drift'",
        "ALTER TABLE analytics.import_run ALTER COLUMN error_summary TYPE varchar(2000)",
        "ALTER TABLE analytics.import_run DROP COLUMN error_summary; "
        "ALTER TABLE analytics.import_run ADD COLUMN error_summary text",
        "COMMENT ON COLUMN analytics.import_run.error_summary IS 'drift'",
        "ALTER TABLE analytics.import_run ADD CONSTRAINT unexpected_check CHECK (row_count >= 0)",
        "GRANT DELETE ON analytics.import_run TO raos_worker_rw",
    ),
    ids=("default", "type", "column-order", "comment", "constraint", "acl"),
)
def test_downgraded_catalog_still_rejects_active_schema_drift(
    drift: str,
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    instance = runner.MigrationRunner(ROOT, postgresql_cluster.target(empty_database))
    assert instance.downgrade().current_revision == catalog.DATABASE_ROLES_REVISION
    with postgresql_cluster.connect(empty_database) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM pg_catalog.pg_attribute "
                "WHERE attrelid = 'analytics.import_run'::regclass AND attisdropped"
            ).fetchone()[0]
            > 0
        )
        before = connection.execute(
            "SELECT count(*) FROM public.raos_migration_history"
        ).fetchone()
        connection.execute(drift)
    for operation in (instance.status, instance.upgrade):
        with pytest.raises(MigrationError) as raised:
            operation()
        assert raised.value.code is runner.MigrationErrorCode.HISTORY_INVALID
    with postgresql_cluster.connect(empty_database) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.raos_migration_version"
        ).fetchone() == (catalog.DATABASE_ROLES_REVISION,)
        assert (
            connection.execute(
                "SELECT count(*) FROM public.raos_migration_history"
            ).fetchone()
            == before
        )


@pytest.mark.parametrize("outcome", ("commit", "rollback", "conflict"))
def test_concurrent_immutable_snapshot_insert_uses_worker_read_privileges(
    outcome: str,
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    """A conflicting insert must wait, then read the committed immutable winner."""
    _upgrade(postgresql_cluster, empty_database)
    _seed_scope(postgresql_cluster, empty_database)
    engine = _worker_engine(postgresql_cluster, empty_database)
    batch = _ga4_batch()
    competing_batch = (
        _ga4_batch(display_name="Conflict") if outcome == "conflict" else batch
    )
    started = Event()
    waiter_pid: list[int] = []

    def insert_competitor() -> UUID:
        with Session(engine) as session, session.begin():
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            waiter_pid.append(
                session.execute(text("SELECT pg_backend_pid()")).scalar_one()
            )
            started.set()
            return _configuration_snapshot_id(session, competing_batch)

    try:
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT has_table_privilege(current_user, "
                    "'analytics.ga4_property_config_snapshot', 'SELECT'), "
                    "has_table_privilege(current_user, "
                    "'analytics.ga4_property_config_snapshot', 'INSERT'), "
                    "has_table_privilege(current_user, "
                    "'analytics.ga4_property_config_snapshot', 'UPDATE'), "
                    "has_table_privilege(current_user, "
                    "'analytics.ga4_property_config_snapshot', 'DELETE'), "
                    "has_table_privilege(current_user, "
                    "'analytics.ga4_property_config_snapshot', 'TRUNCATE')"
                )
            ).one() == (True, True, False, False, False)

        with Session(engine) as first, ThreadPoolExecutor(max_workers=1) as pool:
            first.begin()
            try:
                first_pid = first.execute(text("SELECT pg_backend_pid()")).scalar_one()
                first_id = _configuration_snapshot_id(first, batch)
                pending = pool.submit(insert_competitor)
                assert started.wait(5), "competing transaction did not start"
                deadline = monotonic() + 5
                with postgresql_cluster.connect(empty_database) as observer:
                    while True:
                        blockers = observer.execute(
                            "SELECT pg_blocking_pids(%s)", (waiter_pid[0],)
                        ).fetchone()[0]
                        if first_pid in blockers:
                            break
                        assert monotonic() < deadline, (
                            "insert did not wait for its competitor"
                        )
                        assert not pending.done(), (
                            "competing insert finished before commit"
                        )
                        Event().wait(0.01)
                if outcome == "rollback":
                    first.rollback()
                else:
                    first.commit()
                if outcome == "conflict":
                    with pytest.raises(GoogleProviderFailure) as raised:
                        pending.result(timeout=5)
                    assert (
                        raised.value.code
                        is GoogleProviderFailureCode.PERSISTENCE_FAILED
                    )
                    expected_id = first_id
                else:
                    expected_id = pending.result(timeout=5)
                    assert (expected_id == first_id) is (outcome == "commit")
            finally:
                first.rollback()

        with postgresql_cluster.connect(empty_database) as connection:
            assert connection.execute(
                "SELECT id, display_name FROM analytics.ga4_property_config_snapshot"
            ).fetchall() == [(expected_id, batch.configuration.display_name)]
            for statement in (
                "UPDATE analytics.ga4_property_config_snapshot SET display_name = 'changed'",
                "DELETE FROM analytics.ga4_property_config_snapshot",
            ):
                with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
                    connection.execute(statement)
    finally:
        engine.dispose()


def test_cross_source_and_wrong_queue_jobs_fail_before_any_analytics_write(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    _seed_scope(postgresql_cluster, empty_database)
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            "UPDATE ops.job SET queue_name = 'wrong' WHERE id = %s",
            (GSC_JOB_IDS[1],),
        )
    engine = _worker_engine(postgresql_cluster, empty_database)
    repository = SqlAlchemyAnalyticsImportRepository(
        SqlAlchemyEngineProvider(engine, WorkloadProfile.WORKER_COMMAND)
    )
    try:
        calls = (
            lambda: repository.commit_gsc(
                context=GoogleImportExecutionContext(
                    display_id="AIR-GSC-WITH-GA4-JOB",
                    site_id=SITE_ID,
                    ops_job_id=GA4_JOB_ID,
                    started_at=NOW,
                ),
                batch=_gsc_batch(clicks=3),
            ),
            lambda: repository.commit_ga4(
                context=GoogleImportExecutionContext(
                    display_id="AIR-GA4-WITH-GSC-JOB",
                    site_id=SITE_ID,
                    ops_job_id=GSC_JOB_IDS[0],
                    started_at=NOW,
                ),
                batch=_ga4_batch(),
            ),
            lambda: repository.commit_gsc(
                context=GoogleImportExecutionContext(
                    display_id="AIR-GSC-WRONG-QUEUE",
                    site_id=SITE_ID,
                    ops_job_id=GSC_JOB_IDS[1],
                    started_at=NOW,
                ),
                batch=_gsc_batch(clicks=3),
            ),
        )
        for call in calls:
            with pytest.raises(GoogleProviderFailure) as raised:
                call()
            assert raised.value.code is GoogleProviderFailureCode.PERSISTENCE_FAILED

        with postgresql_cluster.connect(empty_database) as connection:
            assert connection.execute(
                """
                SELECT (SELECT count(*) FROM analytics.import_run),
                       (SELECT count(*) FROM analytics.gsc_observation),
                       (SELECT count(*) FROM analytics.ga4_observation),
                       (SELECT count(*) FROM analytics.ga4_property_config_snapshot)
                """
            ).fetchone() == (0, 0, 0, 0)
    finally:
        engine.dispose()


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
        assert (
            repository.commit_ga4(
                context=GoogleImportExecutionContext(
                    display_id="AIR-GA4-FIRST",
                    site_id=SITE_ID,
                    ops_job_id=GA4_JOB_ID,
                    started_at=NOW,
                ),
                batch=_ga4_batch(),
            )
            == ga4
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


def test_purchase_cli_uses_independent_registered_jobs_and_replays_both_reports(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    monkeypatch,
) -> None:
    from argparse import Namespace
    from dataclasses import replace
    from scripts import raos_editorial_economics_v3 as cli
    from raos.domain.analytics.google_live import (
        GA4_PURCHASE_DIMENSIONS_V2,
        GA4_PURCHASE_PAGE_VIEW_DIMENSIONS_V2,
    )

    _upgrade(postgresql_cluster, empty_database)
    _seed_scope(postgresql_cluster, empty_database)
    views_job_id = UUID("0198f8c4-1000-7000-8000-000000000015")
    with postgresql_cluster.connect(empty_database) as connection:
        connection.execute(
            "INSERT INTO ops.job (id,display_id,job_type,queue_name,status,site_id,created_by_actor_type) VALUES (%s,'JOB-GA4-VIEWS',%s,'analytics','REQUESTED',%s,'SERVICE')",
            (views_job_id, GA4_IMPORT_JOB_TYPE, SITE_ID),
        )
    engine = _worker_engine(postgresql_cluster, empty_database)
    repository = SqlAlchemyAnalyticsImportRepository(
        SqlAlchemyEngineProvider(engine, WorkloadProfile.WORKER_COMMAND)
    )
    original = _ga4_batch()

    def batch(dimensions):
        values = dict(original.rows[0].dimensions)
        values["customEvent:seller_id"] = "official"
        values["customEvent:snapshot_id"] = "ps-" + "a" * 32
        values["eventName"] = (
            "offer_click" if dimensions == GA4_PURCHASE_DIMENSIONS_V2 else "page_view"
        )
        pairs = tuple((name, values[name]) for name in dimensions)
        row = replace(
            original.rows[0],
            dimensions=pairs,
            grain_key_sha256=sha256_hex(
                canonical_json_bytes(
                    {"date": original.date_from.isoformat(), "dimensions": dict(pairs)}
                )
            ),
        )
        return replace(original, dimensions=dimensions, rows=(row,))

    commits = []

    class Service:
        def import_ga4_with_batch(self, **kwargs):
            result_batch = batch(kwargs["dimensions"])
            result = repository.commit_ga4(
                context=kwargs["context"], batch=result_batch
            )
            commits.append(result)
            return result_batch, result

    outputs = []
    monkeypatch.setattr(
        cli, "write_private_json", lambda *args: outputs.append(args[-1])
    )
    args = Namespace(
        profile="purchase-v2",
        date_from="2026-08-29",
        date_to="2026-08-29",
        ga4_output="purchase.json",
        ga4_views_job_id=str(views_job_id),
    )
    try:
        for _ in range(2):
            cli._import_ga4_profile(
                Service(), args, SITE_ID, GA4_JOB_ID, NOW, Path("unused")
            )
        assert len(outputs) == 2 and outputs[0] == outputs[1]
        assert commits[:2] == commits[2:]
        assert commits[0].import_run_id != commits[1].import_run_id
        assert outputs[0]["rows"][0]["metrics"] == [
            {"name": "eventCount", "value": "2"}
        ]
        assert outputs[0]["page_view_rows"]
        for invalid_job in (None, str(GA4_JOB_ID)):
            args.ga4_views_job_id = invalid_job
            with pytest.raises(cli.EditorialEconomicsV3Failure):
                cli._import_ga4_profile(
                    Service(), args, SITE_ID, GA4_JOB_ID, NOW, Path("unused")
                )
        assert len(commits) == 4
        # The repository continues to reject replay under a different query grain.
        with pytest.raises(GoogleProviderFailure):
            repository.commit_ga4(
                context=GoogleImportExecutionContext(
                    display_id="AIR-GA4-VIEWS-20260829-20260829",
                    site_id=SITE_ID,
                    ops_job_id=GA4_JOB_ID,
                    started_at=NOW,
                ),
                batch=batch(GA4_PURCHASE_PAGE_VIEW_DIMENSIONS_V2),
            )
        # An arbitrary UUID is not a registered scope and remains forbidden.
        with pytest.raises(GoogleProviderFailure):
            repository.commit_ga4(
                context=GoogleImportExecutionContext(
                    display_id="AIR-GA4-UNREGISTERED",
                    site_id=SITE_ID,
                    ops_job_id=UUID("0198f8c4-1000-7000-8000-000000000099"),
                    started_at=NOW,
                ),
                batch=batch(GA4_PURCHASE_PAGE_VIEW_DIMENSIONS_V2),
            )
    finally:
        engine.dispose()
