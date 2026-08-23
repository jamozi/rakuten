"""Exact PostgreSQL 18.4 acceptance for the ST-0308 SQLAlchemy runtime."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from threading import Barrier

from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL

from raos.adapters.persistence.sqlalchemy.identity import WorkloadProfile
from raos.adapters.persistence.sqlalchemy.provider import SqlAlchemyEngineProvider
from raos.adapters.persistence.sqlalchemy.unit_of_work import (
    SqlAlchemyIamUnitOfWorkFactory,
    SqlAlchemyIdempotentPortfolioUnitOfWorkFactory,
    SqlAlchemyOpsUnitOfWorkFactory,
    SqlAlchemyPortfolioUnitOfWorkFactory,
)
from raos.domain.iam.aggregates import Principal, PrincipalState, ServicePrincipal
from raos.domain.iam.enums import (
    PrincipalPrincipalType,
    PrincipalStatus,
    ServicePrincipalAllowedEnvironment,
)
from raos.domain.iam.ids import PrincipalId
from raos.domain.ops.aggregates import Job, JobState
from raos.domain.ops.enums import JobStatus
from raos.domain.ops.events import OpsJobRequested
from raos.domain.ops.values import JobPayloadJson
from raos.domain.portfolio.aggregates import Site, SiteState
from raos.domain.portfolio.enums import SiteStatus
from raos.domain.portfolio.ids import SiteId
from raos.domain.portfolio.values import SitePublicSettingsJson
from raos.domain.shared.idempotency import (
    ActorFingerprint,
    ClaimGranted,
    IdempotencyClaim,
    IdempotencyIdentity,
    IdempotencyKey,
    IdempotencyOutcome,
    ReplaySucceeded,
    RequestHash,
    RouteKey,
)
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import AggregateVersion, AwareUtcDateTime
from raos.domain.shared.identity import CausationId, CorrelationId
from raos.migrations import runner
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from tests.postgresql18 import PostgreSQLCluster
from tests.st0308_persistence.support import (
    FIXED_TIME,
    make_audit,
    make_context,
    make_event,
    make_runtime_setting,
    stable_uuid,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _upgrade(cluster: PostgreSQLCluster, database: str) -> None:
    result = runner.MigrationRunner(
        REPOSITORY_ROOT,
        cluster.target(database),
    ).upgrade()
    assert result.current_revision is not None


def _api_engine(cluster: PostgreSQLCluster, database: str) -> Engine:
    digest = hashlib.sha256(database.encode("utf-8")).hexdigest()[:16]
    login = f"st0308_api_{digest}"
    with cluster.connect(database) as connection:
        connection.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN INHERIT NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOREPLICATION NOBYPASSRLS"
            ).format(sql.Identifier(login))
        )
        connection.execute(
            sql.SQL("GRANT raos_api_rw TO {} WITH INHERIT TRUE, SET FALSE").format(
                sql.Identifier(login)
            )
        )

    hba_path = cluster.data_directory / "pg_hba.conf"
    current = hba_path.read_text(encoding="utf-8")
    hba_path.write_text(
        f"local {database} {login} trust\n{current}",
        encoding="utf-8",
    )
    cluster.run(
        "pg_ctl",
        ["--pgdata", str(cluster.data_directory), "reload"],
    )
    engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username=login,
            host=str(cluster.socket_directory),
            port=cluster.port,
            database=database,
        ),
        pool_size=4,
        max_overflow=0,
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT SESSION_USER, CURRENT_USER")).one() == (
            login,
            login,
        )
        timestamp = connection.execute(
            text("SELECT transaction_timestamp()")
        ).scalar_one()
        assert type(timestamp) is datetime
        assert timestamp.utcoffset() is not None
        assert timestamp.fold == 0
    return engine


def _principal() -> Principal:
    principal_id = PrincipalId(stable_uuid("principal:creator"))
    timestamp = AwareUtcDateTime(FIXED_TIME)
    return Principal(
        state=PrincipalState(
            id=principal_id,
            display_id="SP-ST0308",
            principal_type=PrincipalPrincipalType.SERVICE,
            status=PrincipalStatus.ACTIVE,
            display_name="ST-0308 local runtime",
            deactivated_at=None,
            deactivation_reason=None,
            created_at=timestamp,
            updated_at=timestamp,
            lock_version=AggregateVersion(0),
        ),
        service_principal=ServicePrincipal(
            principal_id=principal_id,
            service_code="st0308-local-runtime",
            workload_identity="local-postgresql-18.4-fixture",
            allowed_environment=ServicePrincipalAllowedEnvironment.CI,
            credential_rotated_at=None,
            last_used_at=None,
            created_at=timestamp,
        ),
    )


def _site(*, suffix: str, name: str, version: int = 0) -> Site:
    timestamp = AwareUtcDateTime(FIXED_TIME)
    return Site(
        SiteState(
            id=SiteId(stable_uuid(f"postgresql-site:{suffix}")),
            display_id=f"SITE-{suffix.upper()}",
            site_code=f"st0308-{suffix}",
            name=name,
            primary_domain=f"{suffix}.example.test",
            brand_name="暮らしのしるべ",
            locale="ja-JP",
            timezone="Asia/Tokyo",
            currency="JPY",
            status=SiteStatus.ACTIVE,
            public_settings=SitePublicSettingsJson(
                FrozenJsonObject.from_mapping({"affiliate_disclosure": True})
            ),
            created_at=timestamp,
            updated_at=timestamp,
            lock_version=AggregateVersion(version),
        )
    )


def _job_with_event(*, suffix: str) -> tuple[Job, OpsJobRequested]:
    event = make_event(suffix=suffix)
    timestamp = AwareUtcDateTime(FIXED_TIME)
    job = Job(
        JobState(
            id=event.aggregate_id,
            display_id=f"JOB-{suffix.upper()}",
            job_type="TEST",
            queue_name="local",
            status=JobStatus.REQUESTED,
            priority=0,
            idempotency_key=None,
            site_id=None,
            aggregate_type=None,
            aggregate_id=None,
            payload=JobPayloadJson(FrozenJsonObject.from_mapping({"fixture": suffix})),
            payload_artifact_id=None,
            scheduled_at=None,
            available_at=timestamp,
            started_at=None,
            completed_at=None,
            max_attempts=3,
            attempt_count=0,
            lease_owner=None,
            lease_expires_at=None,
            correlation_id=CorrelationId(stable_uuid(f"job-correlation:{suffix}")),
            causation_id=CausationId(stable_uuid(f"job-causation:{suffix}")),
            parent_job_id=None,
            budget_jpy=None,
            created_by_actor_type="USER",
            created_by_actor_id=None,
            last_error_class=None,
            last_error_code=None,
            last_error_message=None,
            created_at=timestamp,
            updated_at=timestamp,
            lock_version=AggregateVersion(0),
            job_version=1,
            deadline_at=None,
            cancel_requested_at=None,
        )
    )
    job._record_event(event)
    return job, event


def _seed_principal(provider: SqlAlchemyEngineProvider) -> None:
    with SqlAlchemyIamUnitOfWorkFactory(provider).begin(
        make_context(suffix="seed-principal")
    ) as unit:
        assert unit.principals.add(_principal()) == AggregateVersion(0)
        unit.commit()


def test_uow_identity_atomic_commit_cas_rollback_and_idempotency(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    engine = _api_engine(postgresql_cluster, empty_database)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)
    portfolio = SqlAlchemyPortfolioUnitOfWorkFactory(provider)
    ops = SqlAlchemyOpsUnitOfWorkFactory(provider)
    committed = _site(suffix="committed", name="最初の名称")
    rolled_back = _site(suffix="rolled-back", name="保存されない名称")
    try:
        with portfolio.begin(make_context(suffix="portfolio-create")) as unit:
            assert unit.sites.add(committed) == AggregateVersion(0)
            unit.audit.append_many((make_audit(suffix="901"),))
            unit.commit()

        changed = Site(replace(committed.state, name="更新後の名称"))
        with portfolio.begin(make_context(suffix="portfolio-update")) as unit:
            assert unit.sites.save(changed, AggregateVersion(0)) == AggregateVersion(1)
            unit.commit()

        with portfolio.begin(make_context(suffix="portfolio-stale")) as unit:
            try:
                unit.sites.save(changed, AggregateVersion(0))
            except PersistenceError as error:
                assert error.code is PersistenceErrorCode.CONCURRENCY_CONFLICT
            else:  # pragma: no cover - exact negative-path assertion
                raise AssertionError("stale CAS was accepted")

        with portfolio.begin(make_context(suffix="portfolio-rollback")) as unit:
            unit.sites.add(rolled_back)

        committed_job, committed_event = _job_with_event(suffix="901")
        with ops.begin(make_context(suffix="job-commit")) as unit:
            assert unit.jobs.add(committed_job) == AggregateVersion(0)
            assert committed_job.pending_events() == ()
            unit.commit()
        assert committed_job.pending_events() == ()

        rolled_back_job, rolled_back_event = _job_with_event(suffix="902")
        with ops.begin(make_context(suffix="job-rollback")) as unit:
            assert unit.jobs.add(rolled_back_job) == AggregateVersion(0)
            assert rolled_back_job.pending_events() == ()
        assert rolled_back_job.pending_events() == (rolled_back_event,)

        identity = IdempotencyIdentity(
            actor_fingerprint=ActorFingerprint("1" * 64),
            route_key=RouteKey("portfolio.site.create"),
            idempotency_key=IdempotencyKey("st0308-postgresql-runtime"),
        )
        request_hash = RequestHash("2" * 64)
        idempotent = SqlAlchemyIdempotentPortfolioUnitOfWorkFactory(provider)
        with idempotent.begin_idempotent(
            make_context(suffix="idempotency-claim")
        ) as unit:
            decision = unit.idempotency.claim(
                IdempotencyClaim(
                    identity=identity,
                    request_hash=request_hash,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
            assert type(decision) is ClaimGranted
            unit.idempotency.complete_success(
                decision.handle,
                IdempotencyOutcome(
                    response_status=201,
                    response_body=FrozenJsonObject.from_mapping({"created": True}),
                ),
            )
            unit.commit()

        with idempotent.begin_idempotent(
            make_context(suffix="idempotency-replay")
        ) as unit:
            replay = unit.idempotency.lookup(identity, request_hash)
            assert type(replay) is ReplaySucceeded
            assert replay.outcome.response_status == 201
            unit.commit()

        with postgresql_cluster.connect(empty_database) as connection:
            assert connection.execute(
                "SELECT name, lock_version FROM portfolio.site WHERE id = %s",
                (committed.state.id.value,),
            ).fetchone() == ("更新後の名称", 1)
            assert connection.execute(
                "SELECT count(*) FROM portfolio.site WHERE id = %s",
                (rolled_back.state.id.value,),
            ).fetchone() == (0,)
            assert connection.execute(
                "SELECT count(*) FROM ops.audit_event"
            ).fetchone() == (1,)
            assert connection.execute(
                "SELECT event_type, aggregate_id, aggregate_version "
                "FROM ops.outbox_event"
            ).fetchone() == (
                "jp.raos.ops.job_requested.v1",
                committed_event.aggregate_id.value,
                0,
            )
            assert connection.execute(
                "SELECT count(*) FROM ops.job WHERE id = %s",
                (rolled_back_job.state.id.value,),
            ).fetchone() == (0,)
            assert connection.execute(
                "SELECT status, response_status FROM ops.idempotency_record"
            ).fetchone() == ("COMPLETED", 201)
    finally:
        engine.dispose()


def test_global_runtime_setting_series_is_serialized_across_connections(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    engine = _api_engine(postgresql_cluster, empty_database)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)
    _seed_principal(provider)
    barrier = Barrier(2)
    setting_key = "feature.st0308-global-race"

    def contender(label: str) -> str:
        candidate = make_runtime_setting(suffix=f"race-{label}")
        candidate = type(candidate)(replace(candidate.state, setting_key=setting_key))
        factory = SqlAlchemyOpsUnitOfWorkFactory(provider)
        barrier.wait(timeout=10)
        try:
            with factory.begin(make_context(suffix=f"race-{label}")) as unit:
                unit.runtime_settings.append_version(candidate, None)
                unit.commit()
            return "COMMITTED"
        except PersistenceError as error:
            assert error.code is PersistenceErrorCode.CONCURRENCY_CONFLICT
            return error.code.value

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = sorted(pool.map(contender, ("a", "b")))
        assert outcomes == ["COMMITTED", "CONCURRENCY_CONFLICT"]
        with postgresql_cluster.connect(empty_database) as connection:
            assert connection.execute(
                """
                SELECT count(*), min(version_no), max(version_no)
                  FROM ops.runtime_setting_version
                 WHERE setting_key = %s AND scope_type = 'GLOBAL'
                   AND scope_id IS NULL
                """,
                (setting_key,),
            ).fetchone() == (1, 1, 1)
    finally:
        engine.dispose()
