from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
from uuid import UUID

import pytest
from sqlalchemy import Uuid, create_engine, literal, select
from sqlalchemy.pool import NullPool

from raos.adapters.persistence.sqlalchemy.google_live import (
    SqlAlchemyAnalyticsImportRepository,
    _INSERT_GSC_SQL,
    _lock_scope,
    _prepare_ga4,
    _prepare_gsc,
)
from raos.adapters.persistence.sqlalchemy.identity import WorkloadProfile
from raos.adapters.persistence.sqlalchemy.provider import SqlAlchemyEngineProvider
from raos.domain.analytics.google_live import (
    GA4_BASELINE_DIMENSIONS,
    GA4_BASELINE_METRICS,
    GA4_EVENT_PARAMETER_NAMES,
    GA4_IMPORT_JOB_TYPE,
    GOOGLE_ANALYTICS_JOB_QUEUE,
    GSC_IMPORT_JOB_TYPE,
    Ga4ImportBatch,
    Ga4Observation,
    Ga4PropertyConfigSnapshot,
    GoogleProviderFailure,
    GoogleProviderFailureCode,
    GoogleImportExecutionContext,
    SearchConsoleImportBatch,
    SearchConsoleObservation,
    canonical_json_bytes,
    sha256_hex,
)
from raos.ports.google_live import AnalyticsImportRepository


SITE_ID = UUID("0198f8c4-0000-7000-8000-000000000001")
NOW = datetime(2026, 8, 30, 3, 0, tzinfo=timezone.utc)


def _gsc_batch(
    *, query_text: str = "機内持ち込み バッテリー", clicks: int = 3
) -> SearchConsoleImportBatch:
    metric_date = date(2026, 8, 29)
    page_url = "https://example.test/guide/?private=not-persisted"
    dimension_key = sha256_hex(
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
    page_request = "1" * 64
    observation = SearchConsoleObservation(
        metric_date=metric_date,
        query_text=query_text,
        page_url=page_url,
        country_code="jpn",
        device="MOBILE",
        clicks=clicks,
        impressions=10,
        ctr=float(clicks / 10),
        average_position=2.5,
        dimension_key_sha256=dimension_key,
        source_request_sha256=page_request,
    )
    return SearchConsoleImportBatch(
        site_id=SITE_ID,
        site_url="sc-domain:example.test",
        date_from=metric_date,
        date_to=metric_date,
        request_sha256="2" * 64,
        page_request_sha256s=(page_request,),
        rows=(observation,),
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
    page_request = "3" * 64
    configuration = Ga4PropertyConfigSnapshot(
        property_id="123456",
        property_resource="properties/123456",
        display_name="Test property",
        time_zone="Asia/Tokyo",
        currency_code="JPY",
        reporting_identity="BLENDED",
        retrieved_at=NOW,
        property_response_sha256="4" * 64,
        reporting_identity_response_sha256="5" * 64,
        snapshot_sha256=sha256_hex(
            canonical_json_bytes(
                {
                    "currency_code": "JPY",
                    "display_name": "Test property",
                    "property_resource": "properties/123456",
                    "required_event_custom_dimensions": list(GA4_EVENT_PARAMETER_NAMES),
                    "reporting_identity": "BLENDED",
                    "time_zone": "Asia/Tokyo",
                }
            )
        ),
    )
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


def test_constructor_requires_the_exact_worker_command_engine_profile() -> None:
    engine = create_engine(
        "postgresql+psycopg://unused@localhost/unused", poolclass=NullPool
    )
    try:
        repository = SqlAlchemyAnalyticsImportRepository(
            SqlAlchemyEngineProvider(engine, WorkloadProfile.WORKER_COMMAND)
        )
        assert isinstance(repository, AnalyticsImportRepository)
        with pytest.raises(
            ValueError, match="INVALID_GOOGLE_ANALYTICS_IMPORT_REPOSITORY"
        ):
            SqlAlchemyAnalyticsImportRepository(
                SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)
            )
    finally:
        engine.dispose()


def test_gsc_preparation_hashes_query_and_full_url_but_persists_no_query_string() -> (
    None
):
    batch = _gsc_batch()
    prepared, rows = _prepare_gsc(batch)

    assert len(rows) == 1
    assert not hasattr(rows[0], "query_text")
    assert (
        rows[0].query_sha256
        == hashlib.sha256(batch.rows[0].query_text.encode("utf-8")).hexdigest()
    )
    assert rows[0].page_path == "/guide/"
    assert "secret" not in rows[0].page_path
    assert (
        rows[0].page_url_sha256
        == hashlib.sha256(batch.rows[0].page_url.encode("utf-8")).hexdigest()
    )
    assert len(prepared.batch_sha256) == 64
    insert_sql = str(_INSERT_GSC_SQL)
    assert "query_text" not in insert_sql
    assert ":page_url," not in insert_sql
    assert "page_url_sha256" in insert_sql


def test_batch_fingerprint_changes_when_normalized_provider_content_changes() -> None:
    original, _ = _prepare_gsc(_gsc_batch(clicks=3))
    revised, _ = _prepare_gsc(_gsc_batch(clicks=4))
    assert original.batch_sha256 != revised.batch_sha256


def test_duplicate_grains_fail_before_any_database_checkout() -> None:
    batch = _gsc_batch()
    duplicate = SearchConsoleImportBatch(
        site_id=batch.site_id,
        site_url=batch.site_url,
        date_from=batch.date_from,
        date_to=batch.date_to,
        request_sha256=batch.request_sha256,
        page_request_sha256s=batch.page_request_sha256s,
        rows=(batch.rows[0], batch.rows[0]),
        retrieved_at=batch.retrieved_at,
        provider_row_count=2,
    )
    with pytest.raises(GoogleProviderFailure) as raised:
        _prepare_gsc(duplicate)
    assert raised.value.code is GoogleProviderFailureCode.PERSISTENCE_FAILED


def test_ga4_batch_fingerprint_binds_exact_property_configuration_hashes() -> None:
    batch = _ga4_batch()
    prepared, rows = _prepare_ga4(batch)
    assert len(rows) == 1
    assert len(rows[0].content_sha256) == 64
    assert len(prepared.batch_sha256) == 64
    assert (
        prepared.provider_resource_sha256
        == hashlib.sha256(b"properties/123456").hexdigest()
    )


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _MappingResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def mappings(self) -> _MappingResult:
        return self

    def one_or_none(self) -> object:
        return self._value


class _ScopeSession:
    def __init__(self, job: object) -> None:
        self._results = [_ScalarResult(SITE_ID), _MappingResult(job)]

    def execute(self, *_args: object, **_kwargs: object) -> object:
        return self._results.pop(0)


def _scope_row(*, job_type: str, queue_name: str = "analytics") -> object:
    engine = create_engine("sqlite://")
    try:
        with engine.connect() as connection:
            return (
                connection.execute(
                    select(
                        literal(SITE_ID, type_=Uuid(as_uuid=True)).label("site_id"),
                        literal(job_type).label("job_type"),
                        literal(queue_name).label("queue_name"),
                    )
                )
                .mappings()
                .one()
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        (GSC_IMPORT_JOB_TYPE, GSC_IMPORT_JOB_TYPE),
        (GA4_IMPORT_JOB_TYPE, GA4_IMPORT_JOB_TYPE),
    ],
)
def test_scope_lock_accepts_only_the_matching_source_job_type(
    expected: str, actual: str
) -> None:
    _lock_scope(
        _ScopeSession(_scope_row(job_type=actual)),  # type: ignore[arg-type]
        GoogleImportExecutionContext(
            display_id="AIR-SCOPE-TEST",
            site_id=SITE_ID,
            ops_job_id=UUID("0198f8c4-0000-7000-8000-000000000099"),
            started_at=NOW,
        ),
        expected_job_type=expected,
    )


@pytest.mark.parametrize(
    ("expected", "actual", "queue"),
    [
        (GSC_IMPORT_JOB_TYPE, GA4_IMPORT_JOB_TYPE, GOOGLE_ANALYTICS_JOB_QUEUE),
        (GA4_IMPORT_JOB_TYPE, GSC_IMPORT_JOB_TYPE, GOOGLE_ANALYTICS_JOB_QUEUE),
        (GSC_IMPORT_JOB_TYPE, GSC_IMPORT_JOB_TYPE, "wrong"),
    ],
)
def test_scope_lock_rejects_cross_source_or_non_analytics_job(
    expected: str, actual: str, queue: str
) -> None:
    with pytest.raises(GoogleProviderFailure) as raised:
        _lock_scope(
            _ScopeSession(  # type: ignore[arg-type]
                _scope_row(job_type=actual, queue_name=queue)
            ),
            GoogleImportExecutionContext(
                display_id="AIR-SCOPE-TEST",
                site_id=SITE_ID,
                ops_job_id=UUID("0198f8c4-0000-7000-8000-000000000099"),
                started_at=NOW,
            ),
            expected_job_type=expected,
        )
    assert raised.value.code is GoogleProviderFailureCode.PERSISTENCE_FAILED
