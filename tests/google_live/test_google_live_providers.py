from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from uuid import UUID, uuid4

import pytest

from raos.adapters.google_live import (
    FixedOwnerPrivateAnalyticsSiteBindings,
    LiveGa4AdminProvider,
    LiveGa4DataProvider,
    LiveSearchConsoleProvider,
    LiveSearchConsoleUrlInspectionProvider,
)
from raos.application.analytics.google_live_import import LiveGoogleAnalyticsImport
from raos.domain.analytics.google_live import (
    AnalyticsSiteBinding,
    GA4_ARTICLE_ID_DIMENSION,
    GA4_BASELINE_DIMENSIONS,
    GA4_BASELINE_METRICS,
    GA4_EVENT_PARAMETER_NAMES,
    GA4_READONLY_SCOPE,
    GSC_READONLY_SCOPE,
    Ga4LiveQuery,
    GoogleImportCommitResult,
    GoogleImportExecutionContext,
    GoogleProviderFailure,
    GoogleProviderFailureCode,
    SearchConsoleLiveQuery,
    SearchConsoleUrlInspectionQuery,
)
from raos.ports.google_live import GoogleJsonResponse


NOW = datetime(2026, 8, 30, 1, 2, 3, tzinfo=timezone.utc)
SITE_ID = UUID("11111111-1111-4111-8111-111111111111")


def custom_dimensions_response() -> dict[str, object]:
    return {
        "customDimensions": [
            {
                "name": f"properties/12345/customDimensions/{position}",
                "parameterName": parameter,
                "scope": "EVENT",
            }
            for position, parameter in enumerate(GA4_EVENT_PARAMETER_NAMES, start=1)
        ]
    }


class FakeClock:
    def now(self) -> datetime:
        return NOW


class FakeSleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)


class QueueTransport:
    def __init__(self, responses: list[GoogleJsonResponse | Exception]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, Mapping[str, object] | None]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        body: Mapping[str, object] | None,
    ) -> GoogleJsonResponse:
        self.requests.append((method, url, body))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def response(
    document: object,
    *,
    status: int = 200,
    headers: tuple[tuple[str, str], ...] = (),
) -> GoogleJsonResponse:
    return GoogleJsonResponse(status=status, headers=headers, document=document)


def inspection_urls(origin: str = "https://example.com") -> tuple[str, ...]:
    return (f"{origin}/", *(f"{origin}/surface-{index}/" for index in range(1, 14)))


def inspection_response(
    *,
    verdict: str = "PASS",
    indexing_state: str = "INDEXING_ALLOWED",
    last_crawl_time: str | None = "2026-08-29T00:00:00Z",
) -> GoogleJsonResponse:
    index_status: dict[str, object] = {
        "verdict": verdict,
        "indexingState": indexing_state,
    }
    if last_crawl_time is not None:
        index_status["lastCrawlTime"] = last_crawl_time
    return response({"inspectionResult": {"indexStatusResult": index_status}})


def test_search_console_paginates_hashes_requests_and_preserves_three_letter_country() -> (
    None
):
    transport = QueueTransport(
        [
            response(
                {
                    "rows": [
                        {
                            "keys": [
                                "2026-08-28",
                                "query one",
                                "https://example.com/a",
                                "jpn",
                                "MOBILE",
                            ],
                            "clicks": 1,
                            "impressions": 10,
                            "ctr": 0.1,
                            "position": 2.5,
                        },
                        {
                            "keys": [
                                "2026-08-28",
                                "query two",
                                "https://example.com/b",
                                "usa",
                                "DESKTOP",
                            ],
                            "clicks": 0,
                            "impressions": 4,
                            "ctr": 0.0,
                            "position": 7.0,
                        },
                    ]
                }
            ),
            response({"rows": []}),
        ]
    )
    provider = LiveSearchConsoleProvider(
        transport=transport, clock=FakeClock(), sleeper=FakeSleeper()
    )

    batch = provider.query(
        SearchConsoleLiveQuery(
            site_id=SITE_ID,
            site_url="sc-domain:example.com",
            date_from=date(2026, 8, 28),
            date_to=date(2026, 8, 28),
            row_limit=2,
        )
    )

    assert batch.provider_row_count == 2
    assert [row.country_code for row in batch.rows] == ["jpn", "usa"]
    assert len(batch.page_request_sha256s) == 2
    assert batch.page_request_sha256s[0] != batch.page_request_sha256s[1]
    assert transport.requests[0][1].endswith(
        "sites/sc-domain%3Aexample.com/searchAnalytics/query"
    )
    assert transport.requests[0][2]["startRow"] == 0
    assert transport.requests[1][2]["startRow"] == 2
    assert transport.requests[0][2]["type"] == "web"
    assert "searchType" not in transport.requests[0][2]
    assert "query one" not in repr(batch.rows[0])


def test_provider_retries_429_with_bounded_retry_after() -> None:
    sleeper = FakeSleeper()
    transport = QueueTransport(
        [
            response({}, status=429, headers=(("retry-after", "99"),)),
            response({"rows": []}),
        ]
    )
    provider = LiveSearchConsoleProvider(
        transport=transport, clock=FakeClock(), sleeper=sleeper
    )

    batch = provider.query(
        SearchConsoleLiveQuery(
            site_id=SITE_ID,
            site_url="sc-domain:example.com",
            date_from=date(2026, 8, 28),
            date_to=date(2026, 8, 28),
        )
    )

    assert batch.rows == ()
    assert sleeper.delays == [60.0]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, GoogleProviderFailureCode.AUTHENTICATION_FAILED),
        (403, GoogleProviderFailureCode.AUTHORIZATION_FAILED),
        (404, GoogleProviderFailureCode.RESOURCE_NOT_FOUND),
    ],
)
def test_provider_normalizes_non_retryable_http_failures(
    status: int, expected: GoogleProviderFailureCode
) -> None:
    provider = LiveSearchConsoleProvider(
        transport=QueueTransport([response({}, status=status)]),
        clock=FakeClock(),
        sleeper=FakeSleeper(),
    )
    with pytest.raises(GoogleProviderFailure) as observed:
        provider.query(
            SearchConsoleLiveQuery(
                site_id=SITE_ID,
                site_url="sc-domain:example.com",
                date_from=date(2026, 8, 28),
                date_to=date(2026, 8, 28),
            )
        )
    assert observed.value.code is expected
    assert str(observed.value) == expected.value


def test_url_inspection_fetches_exact_inventory_sequentially_and_normalizes() -> None:
    urls = inspection_urls()
    transport = QueueTransport(
        [
            inspection_response(last_crawl_time="2026-08-29T00:00:00.123456789Z"),
            inspection_response(verdict="FAIL", indexing_state="BLOCKED_BY_META_TAG"),
            inspection_response(
                verdict="NEUTRAL",
                indexing_state="INDEXING_ALLOWED",
                last_crawl_time=None,
            ),
            *[inspection_response(last_crawl_time=None) for _ in range(11)],
        ]
    )
    batch = LiveSearchConsoleUrlInspectionProvider(
        transport=transport,
        clock=FakeClock(),
        sleeper=FakeSleeper(),
    ).inspect(
        SearchConsoleUrlInspectionQuery(
            site_id=SITE_ID,
            site_url="sc-domain:example.com",
            inspection_urls=urls,
        )
    )

    assert len(batch.results) == len(transport.requests) == 14
    assert [result.state for result in batch.results[:3]] == [
        "INDEXED",
        "BLOCKED",
        "NOT_INDEXED",
    ]
    assert batch.results[0].last_crawl_at == "2026-08-29T00:00:00.123456789Z"
    assert batch.results[2].last_crawl_at is None
    assert len({result.source_request_sha256 for result in batch.results}) == 14
    assert all(
        method == "POST"
        and url == "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
        and body
        == {
            "inspectionUrl": urls[position],
            "languageCode": "ja-JP",
            "siteUrl": "sc-domain:example.com",
        }
        for position, (method, url, body) in enumerate(transport.requests)
    )
    assert "credential" not in repr(batch).lower()


@pytest.mark.parametrize(
    ("status", "expected", "response_count"),
    [
        (403, GoogleProviderFailureCode.AUTHORIZATION_FAILED, 1),
        (404, GoogleProviderFailureCode.RESOURCE_NOT_FOUND, 1),
        (429, GoogleProviderFailureCode.RATE_LIMITED, 4),
        (500, GoogleProviderFailureCode.PROVIDER_UNAVAILABLE, 4),
    ],
)
def test_url_inspection_http_failures_are_fail_closed(
    status: int,
    expected: GoogleProviderFailureCode,
    response_count: int,
) -> None:
    sleeper = FakeSleeper()
    transport = QueueTransport([response({}, status=status)] * response_count)
    provider = LiveSearchConsoleUrlInspectionProvider(
        transport=transport,
        clock=FakeClock(),
        sleeper=sleeper,
    )

    with pytest.raises(GoogleProviderFailure) as observed:
        provider.inspect(
            SearchConsoleUrlInspectionQuery(
                site_id=SITE_ID,
                site_url="sc-domain:example.com",
                inspection_urls=inspection_urls(),
            )
        )

    assert observed.value.code is expected
    assert len(transport.requests) == response_count
    assert sleeper.delays == ([] if response_count == 1 else [1.0, 2.0, 4.0])


def test_url_inspection_rejects_cross_origin_or_non_exact_inventory() -> None:
    with pytest.raises(GoogleProviderFailure):
        SearchConsoleUrlInspectionQuery(
            site_id=SITE_ID,
            site_url="sc-domain:example.com",
            inspection_urls=inspection_urls()[:-1],
        )
    with pytest.raises(GoogleProviderFailure):
        SearchConsoleUrlInspectionQuery(
            site_id=SITE_ID,
            site_url="sc-domain:example.com",
            inspection_urls=(*inspection_urls()[:-1], "https://other.example/final/"),
        )
    with pytest.raises(GoogleProviderFailure):
        SearchConsoleUrlInspectionQuery(
            site_id=SITE_ID,
            site_url="https://example.com/owned/",
            inspection_urls=inspection_urls(),
        )


def test_url_inspection_rejects_incomplete_success_response() -> None:
    provider = LiveSearchConsoleUrlInspectionProvider(
        transport=QueueTransport([response({"inspectionResult": {}})]),
        clock=FakeClock(),
        sleeper=FakeSleeper(),
    )
    with pytest.raises(GoogleProviderFailure) as observed:
        provider.inspect(
            SearchConsoleUrlInspectionQuery(
                site_id=SITE_ID,
                site_url="sc-domain:example.com",
                inspection_urls=inspection_urls(),
            )
        )
    assert observed.value.code is GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID


def test_ga4_captures_property_config_then_paginates_report() -> None:
    admin_transport = QueueTransport(
        [
            response(
                {
                    "name": "properties/12345",
                    "displayName": "Example",
                    "timeZone": "Asia/Tokyo",
                    "currencyCode": "JPY",
                }
            ),
            response(
                {
                    "name": "properties/12345/reportingIdentitySettings",
                    "reportingIdentity": "DEVICE_BASED",
                }
            ),
            response(custom_dimensions_response()),
        ]
    )
    config = LiveGa4AdminProvider(
        transport=admin_transport, sleeper=FakeSleeper()
    ).get_property_configuration(property_id="12345", retrieved_at=NOW)

    data_transport = QueueTransport(
        [
            response(
                {
                    "dimensionHeaders": [{"name": "date"}, {"name": "eventName"}],
                    "metricHeaders": [{"name": "eventCount"}],
                    "rowCount": 2,
                    "metadata": {"subjectToThresholding": False},
                    "rows": [
                        {
                            "dimensionValues": [
                                {"value": "20260828"},
                                {"value": "article_view"},
                            ],
                            "metricValues": [{"value": "9"}],
                        }
                    ],
                }
            ),
            response(
                {
                    "dimensionHeaders": [{"name": "date"}, {"name": "eventName"}],
                    "metricHeaders": [{"name": "eventCount"}],
                    "rowCount": "2",
                    "metadata": {
                        "subjectToThresholding": True,
                        "dataLossFromOtherRow": True,
                    },
                    "rows": [
                        {
                            "dimensionValues": [
                                {"value": "20260829"},
                                {"value": "affiliate_click"},
                            ],
                            "metricValues": [{"value": "3"}],
                        }
                    ],
                }
            ),
        ]
    )
    query = Ga4LiveQuery(
        site_id=SITE_ID,
        property_id="12345",
        date_from=date(2026, 8, 28),
        date_to=date(2026, 8, 29),
        dimensions=("date", "eventName"),
        metrics=("eventCount",),
        page_limit=1,
    )
    batch = LiveGa4DataProvider(
        transport=data_transport, clock=FakeClock(), sleeper=FakeSleeper()
    ).run_report(query, configuration=config)

    assert batch.configuration.snapshot_sha256 == config.snapshot_sha256
    assert batch.provider_row_count == 2
    assert batch.subject_to_thresholding is True
    assert batch.data_loss_from_other_row is True
    assert data_transport.requests[0][2]["offset"] == "0"
    assert data_transport.requests[1][2]["offset"] == "1"
    assert len(batch.page_request_sha256s) == 2


def test_ga4_admin_refuses_missing_event_custom_dimension() -> None:
    dimensions = custom_dimensions_response()
    cast_rows = list(dimensions["customDimensions"])  # type: ignore[arg-type]
    dimensions["customDimensions"] = cast_rows[:-1]
    provider = LiveGa4AdminProvider(
        transport=QueueTransport(
            [
                response(
                    {
                        "name": "properties/12345",
                        "displayName": "Example",
                        "timeZone": "Asia/Tokyo",
                        "currencyCode": "JPY",
                    }
                ),
                response(
                    {
                        "name": "properties/12345/reportingIdentitySettings",
                        "reportingIdentity": "DEVICE_BASED",
                    }
                ),
                response(dimensions),
            ]
        ),
        sleeper=FakeSleeper(),
    )

    with pytest.raises(GoogleProviderFailure) as observed:
        provider.get_property_configuration(
            property_id="12345",
            retrieved_at=NOW,
        )
    assert observed.value.code is GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID


def _binding_document(
    *, provider: str, resource: str, scope: str, email: str
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "provider": provider,
        "site_id": str(SITE_ID),
        "resource": resource,
        "credential_file": "service-account.json",
        "service_account_email_sha256": hashlib.sha256(email.encode()).hexdigest(),
        "scopes": [scope],
    }


def _write_owner_private_tree(root: Path, *, same_account: bool = False) -> None:
    gsc = root / "google" / "gsc"
    ga4 = root / "google" / "ga4"
    for directory in (root, root / "google", gsc, ga4):
        directory.mkdir(exist_ok=True)
        os.chmod(directory, 0o700)
    ga4_email = "gsc@example.invalid" if same_account else "ga4@example.invalid"
    fixtures = (
        (
            gsc,
            _binding_document(
                provider="GSC",
                resource="sc-domain:example.com",
                scope=GSC_READONLY_SCOPE,
                email="gsc@example.invalid",
            ),
        ),
        (
            ga4,
            _binding_document(
                provider="GA4",
                resource="properties/12345",
                scope=GA4_READONLY_SCOPE,
                email=ga4_email,
            ),
        ),
    )
    for directory, binding in fixtures:
        credential = directory / "service-account.json"
        credential.write_text("{}", encoding="utf-8")
        binding_path = directory / "binding.v1.json"
        binding_path.write_text(json.dumps(binding), encoding="utf-8")
        os.chmod(credential, 0o600)
        os.chmod(binding_path, 0o600)


def test_owner_private_binding_requires_fixed_modes_scopes_and_distinct_accounts() -> (
    None
):
    # The repository temp root may be on drvfs, which cannot prove POSIX 0600/0700.
    # Owner-private bindings are intentionally accepted only on a POSIX filesystem.
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        root = Path(temporary) / "owner-private"
        _write_owner_private_tree(root)

        bindings = FixedOwnerPrivateAnalyticsSiteBindings(root)
        assert bindings.gsc().scopes == (GSC_READONLY_SCOPE,)
        assert bindings.ga4().scopes == (GA4_READONLY_SCOPE,)
        assert bindings.ga4().property_id == "12345"

        os.chmod(root / "google" / "gsc" / "binding.v1.json", 0o644)
        with pytest.raises(GoogleProviderFailure) as insecure:
            FixedOwnerPrivateAnalyticsSiteBindings(root)
        assert (
            insecure.value.code
            is GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID
        )

        os.chmod(root / "google" / "gsc" / "binding.v1.json", 0o600)
        _write_owner_private_tree(root, same_account=True)
        with pytest.raises(GoogleProviderFailure) as reused:
            FixedOwnerPrivateAnalyticsSiteBindings(root)
        assert (
            reused.value.code is GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID
        )


class FakeBindings:
    def __init__(self) -> None:
        self._gsc = AnalyticsSiteBinding(
            provider="GSC",
            site_id=SITE_ID,
            resource="sc-domain:example.com",
            credential_path="/owner/gsc/service-account.json",
            service_account_email_sha256="1" * 64,
            scopes=(GSC_READONLY_SCOPE,),
        )
        self._ga4 = AnalyticsSiteBinding(
            provider="GA4",
            site_id=SITE_ID,
            resource="properties/12345",
            credential_path="/owner/ga4/service-account.json",
            service_account_email_sha256="2" * 64,
            scopes=(GA4_READONLY_SCOPE,),
        )

    def gsc(self) -> AnalyticsSiteBinding:
        return self._gsc

    def ga4(self) -> AnalyticsSiteBinding:
        return self._ga4


class FakeRepository:
    def __init__(self) -> None:
        self.gsc_batch: object | None = None
        self.ga4_batch: object | None = None

    def commit_gsc(self, *, context: object, batch: object) -> GoogleImportCommitResult:
        self.gsc_batch = batch
        return GoogleImportCommitResult(uuid4(), 0, 0, 0, NOW)

    def commit_ga4(self, *, context: object, batch: object) -> GoogleImportCommitResult:
        self.ga4_batch = batch
        return GoogleImportCommitResult(uuid4(), 0, 0, 0, NOW)


class UnusedGa4Data:
    def run_report(self, query: object, *, configuration: object) -> object:
        raise AssertionError("unused")


class UnusedGa4Admin:
    def get_property_configuration(
        self, *, property_id: str, retrieved_at: datetime
    ) -> object:
        raise AssertionError("unused")


def test_application_commits_complete_batch_and_rejects_site_binding_mismatch() -> None:
    repository = FakeRepository()
    service = LiveGoogleAnalyticsImport(
        bindings=FakeBindings(),
        search_console=LiveSearchConsoleProvider(
            transport=QueueTransport([response({"rows": []})]),
            clock=FakeClock(),
            sleeper=FakeSleeper(),
        ),
        ga4_data=UnusedGa4Data(),
        ga4_admin=UnusedGa4Admin(),
        repository=repository,
        clock=FakeClock(),
    )
    context = GoogleImportExecutionContext(
        display_id="AIR-GSC-20260830",
        site_id=SITE_ID,
        ops_job_id=uuid4(),
        started_at=NOW,
    )
    result = service.import_search_console(
        context=context,
        date_from=date(2026, 8, 28),
        date_to=date(2026, 8, 29),
    )
    assert result.inserted_count == 0
    assert repository.gsc_batch is not None

    wrong = GoogleImportExecutionContext(
        display_id="AIR-GSC-WRONG",
        site_id=uuid4(),
        ops_job_id=uuid4(),
        started_at=NOW,
    )
    with pytest.raises(GoogleProviderFailure) as mismatch:
        service.import_search_console(
            context=wrong,
            date_from=date(2026, 8, 28),
            date_to=date(2026, 8, 29),
        )
    assert mismatch.value.code is GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID


def test_application_returns_committed_ga4_batch_with_article_dimension() -> None:
    repository = FakeRepository()
    admin = LiveGa4AdminProvider(
        transport=QueueTransport(
            [
                response(
                    {
                        "name": "properties/12345",
                        "displayName": "Example",
                        "timeZone": "Asia/Tokyo",
                        "currencyCode": "JPY",
                    }
                ),
                response(
                    {
                        "name": "properties/12345/reportingIdentitySettings",
                        "reportingIdentity": "DEVICE_BASED",
                    }
                ),
                response(custom_dimensions_response()),
            ]
        ),
        sleeper=FakeSleeper(),
    )
    data = LiveGa4DataProvider(
        transport=QueueTransport(
            [
                response(
                    {
                        "dimensionHeaders": [
                            {"name": name} for name in GA4_BASELINE_DIMENSIONS
                        ],
                        "metricHeaders": [
                            {"name": name} for name in GA4_BASELINE_METRICS
                        ],
                        "rowCount": 0,
                        "metadata": {"subjectToThresholding": False},
                        "rows": [],
                    }
                )
            ]
        ),
        clock=FakeClock(),
        sleeper=FakeSleeper(),
    )
    service = LiveGoogleAnalyticsImport(
        bindings=FakeBindings(),
        search_console=LiveSearchConsoleProvider(
            transport=QueueTransport([]),
            clock=FakeClock(),
            sleeper=FakeSleeper(),
        ),
        ga4_data=data,
        ga4_admin=admin,
        repository=repository,
        clock=FakeClock(),
    )
    batch, result = service.import_ga4_with_batch(
        context=GoogleImportExecutionContext(
            display_id="AIR-GA4-20260830",
            site_id=SITE_ID,
            ops_job_id=uuid4(),
            started_at=NOW,
        ),
        date_from=date(2026, 8, 28),
        date_to=date(2026, 8, 29),
    )

    assert result.inserted_count == 0
    assert repository.ga4_batch is batch
    assert GA4_ARTICLE_ID_DIMENSION in batch.dimensions
