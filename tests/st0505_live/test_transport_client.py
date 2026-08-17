"""Direct transport construction tests for the ST-0505 live smoke."""

from __future__ import annotations

from email.message import Message
from urllib.request import ProxyHandler, Request

import pytest

from raos.adapters import _rakuten_live_smoke_transport as transport_module
from raos.adapters.rakuten_live_smoke import (
    MAX_RESPONSE_BYTES,
    RAKUTEN_API_ORIGIN,
    RAKUTEN_ITEM_SEARCH_PATH,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeFailureCode,
    UrllibRakutenLiveSmokeTransport,
)

from conftest import (
    AUTHENTICATION_MATERIAL,
    BODY,
    transport_inputs,
)


def test_default_transport_builds_no_proxy_no_redirect_one_attempt_and_filters_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = Message()
    headers["Content-Type"] = "application/json"
    headers["Content-Length"] = str(len(BODY))
    headers["X-Untrusted-Provider-Text"] = "must-not-be-retained"

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

    monkeypatch.setattr(transport_module, "build_opener", fake_build_opener)
    query, request_headers = transport_inputs()
    result = UrllibRakutenLiveSmokeTransport().get(
        origin=RAKUTEN_API_ORIGIN,
        path=RAKUTEN_ITEM_SEARCH_PATH,
        query=query,
        headers=request_headers,
        timeout_seconds=5.0,
        max_body_bytes=MAX_RESPONSE_BYTES,
    )

    assert len(fake_opener.calls) == 1
    sent_request, timeout = fake_opener.calls[0]
    assert sent_request.get_method() == "GET"
    assert "accessKey=" not in sent_request.full_url
    assert "affiliateId=" not in sent_request.full_url
    assert timeout == 5.0
    assert raw_response.read_count == 1
    assert raw_response.closed is True
    assert result.status == 200
    assert all(
        name.lower() != "x-untrusted-provider-text"
        for name, _value in result._headers_for_smoke()
    )
    proxy_handlers = [
        handler for handler in captured_handlers if isinstance(handler, ProxyHandler)
    ]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}
    assert any(
        type(handler).__name__ == "_NoRedirectHandler"
        for handler in captured_handlers
    )


def test_default_transport_rejects_content_length_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = Message()
    headers["Content-Type"] = "application/json"
    headers["Content-Length"] = str(len(BODY) - 1)

    class RawResponse:
        status = 200

        def __init__(self) -> None:
            self.headers = headers
            self.expected_url = ""

        def geturl(self) -> str:
            return self.expected_url

        def read(self, amount: int) -> bytes:
            del amount
            return BODY

        def close(self) -> None:
            return None

    raw_response = RawResponse()

    class FakeOpener:
        def open(self, exact_request: Request, timeout: float) -> RawResponse:
            del timeout
            raw_response.expected_url = exact_request.full_url
            return raw_response

    monkeypatch.setattr(
        transport_module,
        "build_opener",
        lambda *handlers: FakeOpener(),
    )
    query, request_headers = transport_inputs()
    with pytest.raises(RakutenLiveSmokeFailure) as captured:
        UrllibRakutenLiveSmokeTransport().get(
            origin=RAKUTEN_API_ORIGIN,
            path=RAKUTEN_ITEM_SEARCH_PATH,
            query=query,
            headers=request_headers,
            timeout_seconds=5.0,
            max_body_bytes=MAX_RESPONSE_BYTES,
        )
    assert captured.value.code is RakutenLiveSmokeFailureCode.RESPONSE_INVALID


def test_direct_transport_rejects_access_key_or_affiliate_id_in_query() -> None:
    query, request_headers = transport_inputs()
    transport = UrllibRakutenLiveSmokeTransport()
    for unsafe_query in (
        query + (("accessKey", AUTHENTICATION_MATERIAL),),
        query + (("affiliateId", "fixture-affiliate"),),
    ):
        with pytest.raises(RakutenLiveSmokeFailure) as captured:
            transport.get(
                origin=RAKUTEN_API_ORIGIN,
                path=RAKUTEN_ITEM_SEARCH_PATH,
                query=unsafe_query,
                headers=request_headers,
                timeout_seconds=5.0,
                max_body_bytes=MAX_RESPONSE_BYTES,
            )
        assert captured.value.code is RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE


@pytest.mark.parametrize(
    ("query_override", "headers_override"),
    [
        (
            (("applicationId", object()),),
            None,
        ),
        (
            None,
            (("Accept", object()),),
        ),
    ],
)
def test_transport_rejects_non_string_query_or_header_values_without_coercion(
    query_override: tuple[tuple[str, object], ...] | None,
    headers_override: tuple[tuple[str, object], ...] | None,
) -> None:
    query, headers = transport_inputs()
    exact_query: object = query if query_override is None else query_override
    exact_headers: object = headers if headers_override is None else headers_override
    with pytest.raises(RakutenLiveSmokeFailure) as captured:
        UrllibRakutenLiveSmokeTransport().get(
            origin=RAKUTEN_API_ORIGIN,
            path=RAKUTEN_ITEM_SEARCH_PATH,
            query=exact_query,  # type: ignore[arg-type]
            headers=exact_headers,  # type: ignore[arg-type]
            timeout_seconds=5.0,
            max_body_bytes=MAX_RESPONSE_BYTES,
        )
    assert captured.value.code is RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE
