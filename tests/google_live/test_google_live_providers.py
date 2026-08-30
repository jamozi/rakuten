from __future__ import annotations

from collections.abc import Mapping
import dataclasses
from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pickle
import tempfile
from uuid import UUID, uuid4

import pytest

import raos.adapters.google_live as google_live_adapter
from raos.adapters.google_live import (
    FixedOwnerPrivateAnalyticsSiteBindings,
    GoogleServiceAccountAuthorizedTransport,
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
    canonical_json_bytes,
)
from raos.ports.google_live import GoogleJsonResponse
from scripts.raos_google_owner_private_v1 import (
    GA4_ADMIN_READBACK_SCHEMA,
    GSC_ADMIN_READBACK_SCHEMA,
    GSC_RESOURCE,
    LOCAL_SCOPE_SCHEMA,
    SITE_ORIGIN,
    materialize_bindings,
)


NOW = datetime(2026, 8, 30, 1, 2, 3, tzinfo=timezone.utc)
SITE_ID = UUID("11111111-1111-4111-8111-111111111111")
_PRIVATE_KEY_BEGIN = "-----BEGIN PRIVATE " + "KEY-----\n"
_PRIVATE_KEY_END = "-----END PRIVATE " + "KEY-----\n"


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


def _owner_private_credential(*, email: str) -> dict[str, object]:
    return {
        "client_email": email,
        "private_key": f"{_PRIVATE_KEY_BEGIN}fixture\n{_PRIVATE_KEY_END}",
        "project_id": "owner-loader-123",
        "token_uri": "https://oauth2.googleapis.com/token",
        "type": "service_account",
    }


def _write_owner_private_tree(root: Path, *, same_account: bool = False) -> None:
    gsc = root / "google" / "gsc"
    ga4 = root / "google" / "ga4"
    for directory in (root, root / "google", gsc, ga4):
        directory.mkdir(exist_ok=True)
        os.chmod(directory, 0o700)
    gsc_email = "gsc@owner-loader-123.iam.gserviceaccount.com"
    ga4_email = "ga4@owner-loader-123.iam.gserviceaccount.com"

    def write(directory: Path, name: str, value: object) -> None:
        path = directory / name
        path.write_text(json.dumps(value), encoding="utf-8")
        os.chmod(path, 0o600)

    if same_account:
        write(ga4, "service-account.json", _owner_private_credential(email=gsc_email))
        return
    write(gsc, "service-account.json", _owner_private_credential(email=gsc_email))
    write(ga4, "service-account.json", _owner_private_credential(email=ga4_email))
    write(
        root / "google",
        "local-scope.v1.json",
        {
            "database_revision": "202608300001",
            "ga4_ops_job_id": "33333333-3333-4333-8333-333333333333",
            "gsc_ops_job_id": "22222222-2222-4222-8222-222222222222",
            "schema_version": LOCAL_SCOPE_SCHEMA,
            "scope_initialized": True,
            "site_id": str(SITE_ID),
        },
    )
    write(
        gsc,
        "admin-readback.v1.json",
        {
            "captured_at": "2026-08-30T12:34:56Z",
            "is_owner": False,
            "permission": "RESTRICTED",
            "resource": GSC_RESOURCE,
            "row_count": 1,
            "schema": GSC_ADMIN_READBACK_SCHEMA,
            "service_account_readback": True,
        },
    )
    write(
        ga4,
        "admin-readback.v1.json",
        {
            "account_id": "54321",
            "captured_at": "2026-08-30T12:35:56Z",
            "currency_code": "JPY",
            "custom_dimensions": [
                {
                    "display_name": parameter,
                    "event_scope_readback": True,
                    "parameter_name": parameter,
                    "row_count": 1,
                    "scope": "EVENT",
                }
                for parameter in GA4_EVENT_PARAMETER_NAMES
            ],
            "property_display_name": "Fixture property",
            "property_id": "12345",
            "property_resource": "properties/12345",
            "schema": GA4_ADMIN_READBACK_SCHEMA,
            "stream_origin": SITE_ORIGIN,
            "viewer_is_administrator": False,
            "viewer_service_account_readback": True,
        },
    )
    materialize_bindings(private_root=root)


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


@pytest.mark.parametrize(
    "mutation",
    [
        "incomplete_receipt",
        "binding_generation",
        "readback_generation",
        "receipt_hash",
        "readback_semantics",
    ],
)
def test_owner_private_loader_rejects_incomplete_mixed_or_tampered_generation(
    mutation: str,
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        root = Path(temporary) / "owner-private"
        _write_owner_private_tree(root)
        if mutation in {"incomplete_receipt", "receipt_hash"}:
            target = root / "google/binding-receipt.v1.json"
        elif mutation == "binding_generation":
            target = root / "google/gsc/binding.v1.json"
        else:
            target = root / "google/gsc/admin-readback.v1.json"
        document = json.loads(target.read_text())
        if mutation == "incomplete_receipt":
            document["state"] = "OWNER_PRIVATE_BINDINGS_MATERIALIZING"
        elif mutation == "binding_generation":
            document["site_id"] = "44444444-4444-4444-8444-444444444444"
        elif mutation == "readback_generation":
            document["captured_at"] = "2026-08-30T12:34:57Z"
        elif mutation == "receipt_hash":
            document["binding_canonical_sha256s"]["GSC"] = "0" * 64
        else:
            document["permission"] = "FULL"
        target.write_text(json.dumps(document), encoding="utf-8")
        os.chmod(target, 0o600)

        with pytest.raises(GoogleProviderFailure) as rejected:
            FixedOwnerPrivateAnalyticsSiteBindings(root)
        assert (
            rejected.value.code
            is GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID
        )


def test_owner_private_loader_rejects_hard_link_and_path_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        case_root = Path(temporary)
        hard_link_root = case_root / "hard-link-owner-private"
        _write_owner_private_tree(hard_link_root)
        receipt = hard_link_root / "google/binding-receipt.v1.json"
        os.link(receipt, case_root / "receipt-hard-link.json")
        with pytest.raises(GoogleProviderFailure):
            FixedOwnerPrivateAnalyticsSiteBindings(hard_link_root)

        replacement_root = case_root / "replacement-owner-private"
        _write_owner_private_tree(replacement_root)
        credential = replacement_root / "google/gsc/service-account.json"
        credential_value = credential.read_bytes()
        original_read = google_live_adapter.os.read
        replaced = False

        def replacing_read(descriptor: int, amount: int) -> bytes:
            nonlocal replaced
            payload = original_read(descriptor, amount)
            if not replaced:
                replaced = True
                credential.rename(case_root / "credential-opened.json")
                credential.write_bytes(credential_value)
                os.chmod(credential, 0o600)
            return payload

        monkeypatch.setattr(google_live_adapter.os, "read", replacing_read)
        with pytest.raises(GoogleProviderFailure):
            FixedOwnerPrivateAnalyticsSiteBindings(replacement_root)
        assert replaced is True


def test_pinned_tree_atomic_replace_and_materializing_validation() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        root = Path(temporary) / "owner-private"
        _write_owner_private_tree(root)
        receipt_path = root / "google/binding-receipt.v1.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["state"] = "OWNER_PRIVATE_BINDINGS_MATERIALIZING"
        content = canonical_json_bytes(receipt)
        with google_live_adapter._PinnedOwnerPrivateGoogleTree(root) as tree:
            before = tree.entry_identity("google", "binding-receipt.v1.json")
            after = tree.atomic_replace(
                "google",
                "binding-receipt.v1.json",
                content,
                expected=before,
            )
            assert after != before
        with pytest.raises(GoogleProviderFailure):
            FixedOwnerPrivateAnalyticsSiteBindings(root)
        materializing = FixedOwnerPrivateAnalyticsSiteBindings._for_generation_state(
            root,
            expected_state="OWNER_PRIVATE_BINDINGS_MATERIALIZING",
        )
        assert type(materializing.gsc()) is AnalyticsSiteBinding
        assert type(materializing.ga4()) is AnalyticsSiteBinding
        assert materializing.gsc().site_id == SITE_ID


def test_transport_rejects_materializing_binding_before_credential_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        root = Path(temporary) / "owner-private"
        _write_owner_private_tree(root)
        receipt_path = root / "google/binding-receipt.v1.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["state"] = "OWNER_PRIVATE_BINDINGS_MATERIALIZING"
        receipt_path.write_bytes(canonical_json_bytes(receipt))
        os.chmod(receipt_path, 0o600)
        materializing = FixedOwnerPrivateAnalyticsSiteBindings._for_generation_state(
            root,
            expected_state="OWNER_PRIVATE_BINDINGS_MATERIALIZING",
        )

        def reject_import(_: str) -> object:
            raise AssertionError("credential modules must not be imported")

        monkeypatch.setattr(
            google_live_adapter.importlib,
            "import_module",
            reject_import,
        )
        with pytest.raises(GoogleProviderFailure) as rejected:
            GoogleServiceAccountAuthorizedTransport(binding=materializing.gsc())
        assert (
            rejected.value.code
            is GoogleProviderFailureCode.INVALID_ARGUMENT
        )


def test_materializing_binding_has_no_credential_capability_under_introspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        root = Path(temporary) / "owner-private"
        _write_owner_private_tree(root)
        receipt_path = root / "google/binding-receipt.v1.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["state"] = "OWNER_PRIVATE_BINDINGS_MATERIALIZING"
        receipt_path.write_bytes(canonical_json_bytes(receipt))
        os.chmod(receipt_path, 0o600)
        materializing_binding = (
            FixedOwnerPrivateAnalyticsSiteBindings._for_generation_state(
                root,
                expected_state="OWNER_PRIVATE_BINDINGS_MATERIALIZING",
            ).gsc()
        )
        assert type(materializing_binding) is AnalyticsSiteBinding
        assert not hasattr(materializing_binding, "authorize_transport")
        for hidden_name in (
            "_GuardedAnalyticsSiteBinding__credential_snapshot",
            "_GuardedAnalyticsSiteBinding__generation_seal",
            "_GuardedAnalyticsSiteBinding__instance_nonce",
        ):
            with pytest.raises(AttributeError):
                object.__getattribute__(materializing_binding, hidden_name)
            with pytest.raises(AttributeError):
                object.__setattr__(materializing_binding, hidden_name, object())

        def reject_import(_: str) -> object:
            raise AssertionError("credential modules must not be imported")

        monkeypatch.setattr(
            google_live_adapter.importlib,
            "import_module",
            reject_import,
        )
        with pytest.raises(GoogleProviderFailure) as rejected:
            GoogleServiceAccountAuthorizedTransport(binding=materializing_binding)
        assert (
            rejected.value.code
            is GoogleProviderFailureCode.INVALID_ARGUMENT
        )


@pytest.mark.parametrize("ancestor", ["root", "google", "provider"])
def test_owner_private_loader_rejects_ancestor_directory_replacement(
    monkeypatch: pytest.MonkeyPatch, ancestor: str
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        case_root = Path(temporary)
        root = case_root / "owner-private"
        _write_owner_private_tree(root)
        if ancestor == "root":
            original = root
            moved = case_root / "owner-private-opened"
        elif ancestor == "google":
            original = root / "google"
            moved = root / "google-opened"
        else:
            original = root / "google/gsc"
            moved = root / "google/gsc-opened"
        original_read = google_live_adapter.os.read
        replaced = False

        def replacing_read(descriptor: int, amount: int) -> bytes:
            nonlocal replaced
            payload = original_read(descriptor, amount)
            if not replaced:
                replaced = True
                original.rename(moved)
                original.symlink_to(moved, target_is_directory=True)
            return payload

        monkeypatch.setattr(google_live_adapter.os, "read", replacing_read)
        with pytest.raises(GoogleProviderFailure) as rejected:
            FixedOwnerPrivateAnalyticsSiteBindings(root)
        assert (
            rejected.value.code
            is GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID
        )
        assert replaced is True


def test_transport_uses_loader_credential_snapshot_without_path_reread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        root = Path(temporary) / "owner-private"
        _write_owner_private_tree(root)
        bindings = FixedOwnerPrivateAnalyticsSiteBindings(root)
        binding = bindings.gsc()
        credential_path = root / "google/gsc/service-account.json"
        original_info = json.loads(credential_path.read_text())
        expected_hash = hashlib.sha256(canonical_json_bytes(original_info)).hexdigest()
        replacement_info = dict(original_info)
        replacement_info["private_key"] = (
            f"{_PRIVATE_KEY_BEGIN}replacement\n{_PRIVATE_KEY_END}"
        )
        credential_path.write_text(json.dumps(replacement_info), encoding="utf-8")
        os.chmod(credential_path, 0o600)
        received_hashes: list[str] = []

        class FakeCredentialsValue:
            valid = True
            token = "fixture-token"
            service_account_email = original_info["client_email"]

        class FakeCredentialsFactory:
            @staticmethod
            def from_service_account_info(
                info: dict[str, object], *, scopes: list[str]
            ) -> FakeCredentialsValue:
                assert scopes == list(binding.scopes)
                received_hashes.append(
                    hashlib.sha256(canonical_json_bytes(info)).hexdigest()
                )
                return FakeCredentialsValue()

            @staticmethod
            def from_service_account_file(*_: object, **__: object) -> object:
                raise AssertionError("credential path must not be reopened")

        class FakeServiceAccountModule:
            Credentials = FakeCredentialsFactory

        class FakeGoogleRequestsModule:
            class Request:
                pass

        class FakeRequestsModule:
            class Session:
                pass

        modules = {
            "google.oauth2.service_account": FakeServiceAccountModule,
            "google.auth.transport.requests": FakeGoogleRequestsModule,
            "requests": FakeRequestsModule,
        }
        monkeypatch.setattr(
            google_live_adapter.importlib,
            "import_module",
            lambda name: modules[name],
        )

        GoogleServiceAccountAuthorizedTransport(binding=binding)
        assert received_hashes == [expected_hash]
        assert "fixture" not in repr(binding)
        assert "private_key" not in repr(binding)


def test_guarded_binding_hides_credential_capability_from_standard_walkers() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        root = Path(temporary) / "owner-private"
        _write_owner_private_tree(root)
        binding = FixedOwnerPrivateAnalyticsSiteBindings(root).gsc()
        expected_fields = {
            "credential_path",
            "provider",
            "resource",
            "scopes",
            "service_account_email_sha256",
            "site_id",
        }
        assert {item.name for item in dataclasses.fields(binding)} == expected_fields
        assert set(dataclasses.asdict(binding)) == expected_fields
        assert not hasattr(binding, "credential_snapshot")
        assert not hasattr(binding, "generation_seal")
        assert repr(binding) == "_GuardedAnalyticsSiteBinding(<redacted>)"
        with pytest.raises(TypeError):
            pickle.dumps(binding)

        snapshot = object.__getattribute__(
            binding,
            "_GuardedAnalyticsSiteBinding__credential_snapshot",
        )
        assert dataclasses.is_dataclass(snapshot) is False
        assert not hasattr(snapshot, "canonical_json")
        assert not hasattr(snapshot, "canonical_sha256")
        assert repr(snapshot) == "_CredentialSnapshot(<redacted>)"
        with pytest.raises(TypeError):
            vars(snapshot)
        for walker_name in ("asdict", "fields"):
            walker = vars(dataclasses)[walker_name]
            with pytest.raises(TypeError):
                walker(snapshot)
        with pytest.raises(TypeError):
            pickle.dumps(snapshot)
        with pytest.raises(AttributeError):
            setattr(snapshot, "canonical_json", b"")

        consume = getattr(snapshot, "consume")
        with pytest.raises(GoogleProviderFailure) as unauthorized:
            consume(issuer=object())
        assert (
            unauthorized.value.code
            is GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID
        )


def test_transport_rejects_unsealed_binding_before_credential_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        google_live_adapter.importlib,
        "import_module",
        lambda _: (_ for _ in ()).throw(AssertionError("must not import")),
    )
    binding = AnalyticsSiteBinding(
        provider="GSC",
        site_id=SITE_ID,
        resource=GSC_RESOURCE,
        credential_path="/owner/gsc/service-account.json",
        service_account_email_sha256="1" * 64,
        scopes=(GSC_READONLY_SCOPE,),
    )
    with pytest.raises(GoogleProviderFailure) as rejected:
        GoogleServiceAccountAuthorizedTransport(binding=binding)
    assert rejected.value.code is GoogleProviderFailureCode.INVALID_ARGUMENT


@pytest.mark.parametrize(
    "mutation",
    [
        "resource",
        "site_id",
        "credential_path",
        "service_account_email_sha256",
    ],
)
def test_guarded_binding_rejects_dataclass_replace_of_base_fields(
    mutation: str,
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        root = Path(temporary) / "owner-private"
        _write_owner_private_tree(root)
        binding = FixedOwnerPrivateAnalyticsSiteBindings(root).gsc()
        with pytest.raises(TypeError):
            if mutation == "resource":
                replace(
                    binding,
                    resource="sc-domain:mutated.example",
                )
            elif mutation == "site_id":
                replace(
                    binding,
                    site_id=UUID("55555555-5555-4555-8555-555555555555"),
                )
            elif mutation == "credential_path":
                replace(
                    binding,
                    credential_path="/owner/alternate/service-account.json",
                )
            else:
                replace(
                    binding,
                    service_account_email_sha256="3" * 64,
                )


def test_transport_revalidates_seal_after_low_level_binding_field_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        root = Path(temporary) / "owner-private"
        _write_owner_private_tree(root)
        binding = FixedOwnerPrivateAnalyticsSiteBindings(root).gsc()
        object.__setattr__(binding, "resource", "sc-domain:mutated.example")

        def reject_import(_: str) -> object:
            raise AssertionError("credential modules must not be imported")

        monkeypatch.setattr(
            google_live_adapter.importlib,
            "import_module",
            reject_import,
        )
        with pytest.raises(GoogleProviderFailure) as rejected:
            GoogleServiceAccountAuthorizedTransport(binding=binding)
        assert (
            rejected.value.code
            is GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID
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
