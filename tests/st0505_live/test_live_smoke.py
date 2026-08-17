"""No-network executable-boundary tests for the ST-0505 live smoke."""

from __future__ import annotations

from datetime import timedelta
from email.message import Message
import json
from urllib.request import ProxyHandler, Request

import pytest

from raos.adapters.rakuten_live_smoke import (
    MAX_RESPONSE_BYTES,
    RAKUTEN_ACCESS_KEY_ALIAS,
    RAKUTEN_API_DOCUMENTATION_RETRIEVED_ON,
    RAKUTEN_API_DOCUMENTATION_URL,
    RAKUTEN_API_ORIGIN,
    RAKUTEN_APPLICATION_ID_ALIAS,
    RAKUTEN_ITEM_SEARCH_PATH,
    RateObservation,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeFailureCode,
    RakutenLiveSmokeGrant,
    RakutenLiveSmokeRequest,
    RakutenLiveSmokeRunner,
    SecretText,
    UrllibRakutenLiveSmokeTransport,
)
from raos.adapters import rakuten_live_smoke as live_smoke_module

from conftest import (
    ACCESS_KEY,
    APP_ID,
    BODY,
    EXECUTION_APPROVAL_SHA256,
    NOW,
    OPERATIONS_EVIDENCE_SHA256,
    FakeCredentials,
    FakeTransport,
    FixedClock,
    grant,
    request,
    response,
)


def _runner(
    credentials: FakeCredentials,
    transport: FakeTransport,
) -> RakutenLiveSmokeRunner:
    return RakutenLiveSmokeRunner(
        credentials=credentials,
        transport=transport,
        clock=FixedClock(),
    )


def _assert_failure(
    expected: RakutenLiveSmokeFailureCode,
    *,
    exact_request: RakutenLiveSmokeRequest | None = None,
    exact_grant: RakutenLiveSmokeGrant | None = None,
    credentials: FakeCredentials | None = None,
    transport: FakeTransport | None = None,
) -> tuple[FakeCredentials, FakeTransport]:
    req = request() if exact_request is None else exact_request
    bound_grant = grant(bound_request=req) if exact_grant is None else exact_grant
    source = FakeCredentials() if credentials is None else credentials
    fake = FakeTransport(response()) if transport is None else transport
    with pytest.raises(RakutenLiveSmokeFailure) as captured:
        _runner(source, fake).run(request=req, grant=bound_grant)
    assert captured.value.code is expected
    assert str(captured.value) == expected.value
    return source, fake


def test_success_is_one_request_one_page_no_retry_and_safe_receipt() -> None:
    credentials = FakeCredentials()
    transport = FakeTransport(response())
    exact_request = request()

    receipt = _runner(credentials, transport).run(
        request=exact_request,
        grant=grant(bound_request=exact_request),
    )

    assert credentials.reads == [
        RAKUTEN_APPLICATION_ID_ALIAS,
        RAKUTEN_ACCESS_KEY_ALIAS,
    ]
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["origin"] == RAKUTEN_API_ORIGIN
    assert call["path"] == RAKUTEN_ITEM_SEARCH_PATH
    query = dict(call["query"])
    headers = dict(call["headers"])
    assert query["applicationId"] == APP_ID
    assert "accessKey" not in query
    assert "affiliateId" not in query
    assert query["formatVersion"] == "2"
    assert query["page"] == "1"
    assert query["hits"] == "1"
    assert headers["accessKey"] == ACCESS_KEY
    assert headers["Accept-Encoding"] == "identity"

    assert receipt.network_request_count == 1
    assert receipt.retry_count == 0
    assert receipt.pagination_count == 0
    assert receipt.storage_write_count == 0
    assert receipt.persistence_write_count == 0
    assert receipt.publication_count == 0
    assert receipt.request_sha256 == exact_request.fingerprint
    assert receipt.response_bytes == len(BODY)
    assert receipt.http_status == 200
    assert receipt.rate_observation is RateObservation.COMPLETE_HEADER_METADATA
    assert receipt.rate_limit == 100
    assert receipt.rate_remaining == 99
    assert receipt.returned_item_count == 1

    serialized = json.loads(receipt.canonical_json)
    text = receipt.canonical_json.decode("ascii")
    assert serialized["request_sha256"] == exact_request.fingerprint
    assert APP_ID not in text
    assert ACCESS_KEY not in text
    assert "synthetic suitcase" not in text
    assert "Synthetic suitcase" not in text


def test_request_and_secret_displays_are_redacted() -> None:
    exact_request = request()
    secret = SecretText(ACCESS_KEY)
    assert "synthetic suitcase" not in repr(exact_request)
    assert "synthetic suitcase" not in str(exact_request)
    assert ACCESS_KEY not in repr(secret)
    assert ACCESS_KEY not in str(secret)


def test_official_contract_pin_is_exact() -> None:
    assert RAKUTEN_API_DOCUMENTATION_URL == (
        "https://webservice.rakuten.co.jp/documentation/ichiba-item-search"
    )
    assert RAKUTEN_API_DOCUMENTATION_RETRIEVED_ON == "2026-08-18"
    assert RAKUTEN_ITEM_SEARCH_PATH.endswith("/20260701")


def test_runner_consumes_a_valid_grant_before_any_retry() -> None:
    credentials = FakeCredentials()
    transport = FakeTransport(response())
    runner = _runner(credentials, transport)
    exact_request = request()
    exact_grant = grant(bound_request=exact_request)

    runner.run(request=exact_request, grant=exact_grant)
    with pytest.raises(RakutenLiveSmokeFailure) as captured:
        runner.run(request=exact_request, grant=exact_grant)

    assert captured.value.code is RakutenLiveSmokeFailureCode.NOT_AUTHORIZED
    assert len(transport.calls) == 1
    assert credentials.reads == [
        RAKUTEN_APPLICATION_ID_ALIAS,
        RAKUTEN_ACCESS_KEY_ALIAS,
    ]


def test_raw_http_response_display_and_pickle_boundary_are_redacted() -> None:
    raw = response()
    assert "Synthetic suitcase" not in repr(raw)
    assert "Synthetic suitcase" not in str(raw)
    assert not hasattr(raw, "body")
    with pytest.raises(TypeError):
        raw.__reduce_ex__(5)


def test_default_transport_builds_no_proxy_no_redirect_one_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = Message()
    headers["Content-Type"] = "application/json"

    class RawResponse:
        status = 200

        def __init__(self) -> None:
            self.headers = headers
            self.read_count = 0
            self.closed = False
            self.expected_url = ""

        def geturl(self) -> str:
            return self.expected_url

        def read(self, amount: int) -> bytes:
            assert amount == MAX_RESPONSE_BYTES + 1
            self.read_count += 1
            return BODY

        def close(self) -> None:
            self.closed = True

    raw_response = RawResponse()

    class FakeOpener:
        def __init__(self) -> None:
            self.calls: list[tuple[Request, float]] = []

        def open(self, exact_request: Request, timeout: float) -> RawResponse:
            self.calls.append((exact_request, timeout))
            raw_response.expected_url = exact_request.full_url
            return raw_response

    fake_opener = FakeOpener()
    captured_handlers: list[object] = []

    def fake_build_opener(*handlers: object) -> FakeOpener:
        captured_handlers.extend(handlers)
        return fake_opener

    monkeypatch.setattr(live_smoke_module, "build_opener", fake_build_opener)
    result = UrllibRakutenLiveSmokeTransport().get(
        origin=RAKUTEN_API_ORIGIN,
        path=RAKUTEN_ITEM_SEARCH_PATH,
        query=(("applicationId", APP_ID), ("keyword", "synthetic suitcase")),
        headers=(("accessKey", ACCESS_KEY),),
        timeout_seconds=5.0,
        max_body_bytes=MAX_RESPONSE_BYTES,
    )

    assert len(fake_opener.calls) == 1
    sent_request, timeout = fake_opener.calls[0]
    assert sent_request.get_method() == "GET"
    assert timeout == 5.0
    assert raw_response.read_count == 1
    assert raw_response.closed is True
    assert result.status == 200
    proxy_handlers = [
        handler for handler in captured_handlers if isinstance(handler, ProxyHandler)
    ]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}
    assert any(
        type(handler).__name__ == "_NoRedirectHandler"
        for handler in captured_handlers
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (301, RakutenLiveSmokeFailureCode.REDIRECT_FORBIDDEN),
        (302, RakutenLiveSmokeFailureCode.REDIRECT_FORBIDDEN),
        (401, RakutenLiveSmokeFailureCode.AUTH_REJECTED),
        (403, RakutenLiveSmokeFailureCode.AUTH_REJECTED),
        (429, RakutenLiveSmokeFailureCode.RATE_LIMITED),
        (400, RakutenLiveSmokeFailureCode.REQUEST_REJECTED),
        (404, RakutenLiveSmokeFailureCode.REQUEST_REJECTED),
        (500, RakutenLiveSmokeFailureCode.PROVIDER_UNAVAILABLE),
        (503, RakutenLiveSmokeFailureCode.PROVIDER_UNAVAILABLE),
        (418, RakutenLiveSmokeFailureCode.PROVIDER_REJECTED),
    ],
)
def test_http_failure_never_retries(
    status: int,
    expected: RakutenLiveSmokeFailureCode,
) -> None:
    transport = FakeTransport(response(status=status, body=b""))
    _, used = _assert_failure(expected, transport=transport)
    assert len(used.calls) == 1


def test_transport_exception_never_retries_or_leaks_original_message() -> None:
    transport = FakeTransport(
        response(),
        error=TimeoutError(f"do not leak {APP_ID} {ACCESS_KEY}"),
    )
    with pytest.raises(RakutenLiveSmokeFailure) as captured:
        _runner(FakeCredentials(), transport).run(
            request=request(),
            grant=grant(),
        )
    assert captured.value.code is RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE
    assert len(transport.calls) == 1
    assert APP_ID not in str(captured.value)
    assert ACCESS_KEY not in str(captured.value)
    assert captured.value.__cause__ is None


def test_missing_second_credential_prevents_network() -> None:
    credentials = FakeCredentials(fail_alias=RAKUTEN_ACCESS_KEY_ALIAS)
    transport = FakeTransport(response())
    source, used = _assert_failure(
        RakutenLiveSmokeFailureCode.CREDENTIAL_UNAVAILABLE,
        credentials=credentials,
        transport=transport,
    )
    assert source.reads == [
        RAKUTEN_APPLICATION_ID_ALIAS,
        RAKUTEN_ACCESS_KEY_ALIAS,
    ]
    assert used.calls == []


def test_expired_or_wrong_request_grant_prevents_credential_read_and_network() -> None:
    credentials = FakeCredentials()
    transport = FakeTransport(response())
    expired = grant(
        issued_at=NOW - timedelta(minutes=2),
        expires_at=NOW - timedelta(minutes=1),
    )
    _assert_failure(
        RakutenLiveSmokeFailureCode.NOT_AUTHORIZED,
        exact_grant=expired,
        credentials=credentials,
        transport=transport,
    )
    assert credentials.reads == []
    assert transport.calls == []

    other = RakutenLiveSmokeRequest(keyword="another synthetic query")
    wrong = grant(bound_request=other)
    _assert_failure(
        RakutenLiveSmokeFailureCode.NOT_AUTHORIZED,
        exact_grant=wrong,
        credentials=credentials,
        transport=transport,
    )
    assert credentials.reads == []
    assert transport.calls == []


def test_grant_rejects_production_and_lifetime_over_fifteen_minutes() -> None:
    exact_request = request()
    with pytest.raises(RakutenLiveSmokeFailure):
        RakutenLiveSmokeGrant(
            environment="ENV-PRODUCTION",
            request_sha256=exact_request.fingerprint,
            operations_evidence_sha256=OPERATIONS_EVIDENCE_SHA256,
            execution_approval_sha256=EXECUTION_APPROVAL_SHA256,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=1),
        )
    with pytest.raises(RakutenLiveSmokeFailure):
        RakutenLiveSmokeGrant(
            environment="ENV-STAGING",
            request_sha256=exact_request.fingerprint,
            operations_evidence_sha256=OPERATIONS_EVIDENCE_SHA256,
            execution_approval_sha256=EXECUTION_APPROVAL_SHA256,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=16),
        )


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b"\xff\xfe", RakutenLiveSmokeFailureCode.RESPONSE_INVALID),
        (b"{", RakutenLiveSmokeFailureCode.RESPONSE_INVALID),
        (b'{"count":1,"count":1}', RakutenLiveSmokeFailureCode.RESPONSE_INVALID),
        (b'{"value":NaN}', RakutenLiveSmokeFailureCode.RESPONSE_INVALID),
        (b"[]", RakutenLiveSmokeFailureCode.RESPONSE_INVALID),
        (
            b"x" * (MAX_RESPONSE_BYTES + 1),
            RakutenLiveSmokeFailureCode.RESPONSE_TOO_LARGE,
        ),
    ],
)
def test_malformed_or_oversized_body_never_retries(
    body: bytes,
    expected: RakutenLiveSmokeFailureCode,
) -> None:
    transport = FakeTransport(response(body=body))
    _, used = _assert_failure(expected, transport=transport)
    assert len(used.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"count": 1, "page": 2, "hits": 1, "pageCount": 1, "items": []},
        {"count": 1, "page": 1, "hits": 2, "pageCount": 1, "items": []},
        {"count": 1, "page": 1, "hits": 1, "pageCount": 1, "items": [], "unknown": 1},
        {"count": 1, "page": 1, "hits": 1, "pageCount": 1},
        {"count": 0, "page": 1, "hits": 0, "pageCount": 1, "items": []},
        {
            "count": 1,
            "page": 1,
            "hits": 1,
            "pageCount": 1,
            "items": [
                {
                    "itemCode": "test-shop:item-1",
                    "itemName": "Synthetic",
                    "itemPrice": 1,
                    "itemUrl": "http://example.invalid/item",
                    "shopCode": "test-shop",
                }
            ],
        },
    ],
)
def test_schema_drift_never_retries(payload: dict[str, object]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    transport = FakeTransport(response(body=body))
    _, used = _assert_failure(
        RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH,
        transport=transport,
    )
    assert len(used.calls) == 1


def test_missing_or_unsafe_content_headers_fail_closed() -> None:
    for headers in (
        (),
        (("Content-Type", "text/html"),),
        (("Content-Type", "application/json"), ("Content-Encoding", "gzip")),
        (("Content-Type", "application/json"), ("Content-Type", "application/json")),
    ):
        transport = FakeTransport(response(headers=headers))
        _, used = _assert_failure(
            RakutenLiveSmokeFailureCode.RESPONSE_INVALID,
            transport=transport,
        )
        assert len(used.calls) == 1


def test_partial_or_absent_rate_metadata_is_observed_without_invention() -> None:
    exact_request = request()
    for headers, expected in (
        (
            (("Content-Type", "application/json"),),
            RateObservation.NOT_EXPOSED,
        ),
        (
            (
                ("Content-Type", "application/json"),
                ("X-RateLimit-Remaining", "9"),
            ),
            RateObservation.PARTIAL_HEADER_METADATA,
        ),
    ):
        receipt = _runner(
            FakeCredentials(),
            FakeTransport(response(headers=headers)),
        ).run(request=exact_request, grant=grant(bound_request=exact_request))
        assert receipt.rate_observation is expected


def test_nested_json_depth_limit_is_enforced_without_retry() -> None:
    nested: object = 0
    for _ in range(40):
        nested = [nested]
    body = json.dumps(
        {"count": 0, "page": 1, "hits": 0, "pageCount": 0, "items": nested}
    ).encode()
    transport = FakeTransport(response(body=body))
    _, used = _assert_failure(
        RakutenLiveSmokeFailureCode.RESPONSE_INVALID,
        transport=transport,
    )
    assert len(used.calls) == 1
