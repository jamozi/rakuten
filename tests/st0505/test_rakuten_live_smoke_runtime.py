"""Offline runtime and trust-boundary evidence for ST-0505."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import socket
import ssl
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest

from raos.adapters.rakuten_live_smoke import (
    CONNECT_TIMEOUT_SECONDS,
    READ_TIMEOUT_SECONDS,
    DirectRakutenLiveSmokeTransport,
    OwnerPrivateRakutenLiveSmokeCredentialReader,
    OwnerPrivateRakutenLiveSmokeReportWriter,
    SystemRakutenLiveSmokeHttpsConnectionFactory,
)
import raos.adapters.rakuten_live_smoke as live_adapter
from raos.application.catalog.rakuten_live_smoke import RakutenLiveSmokeService
from raos.domain.catalog.rakuten_live_smoke import (
    RAKUTEN_LIVE_SMOKE_ACCESS_HEADER,
    RAKUTEN_LIVE_SMOKE_ACCEPT,
    RAKUTEN_LIVE_SMOKE_HOST,
    RAKUTEN_LIVE_SMOKE_PATH,
    RAKUTEN_LIVE_SMOKE_USER_AGENT,
    RakutenLiveSmokeCredentials,
    RakutenLiveSmokeDiagnosticCode,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeHttpResponse,
    RakutenLiveSmokeReport,
    exact_report_mapping,
    fail_rakuten_live_smoke,
    fixed_rakuten_live_smoke_policy,
)
from scripts.rakuten_live_smoke import (
    DOCTOR_NOT_READY,
    DOCTOR_READY,
    LIVE_PASS,
    doctor,
    run_live_smoke,
)


APPLICATION_ID = "app-value-7Qx"
WIRE_HEADER_PROOF = "fixture-wire-header-proof"
AFFILIATE_ID = "affiliate-value-9Sz"
_ACCESS_FIELD = "access" + "_key"
SUCCESS = json.dumps(
    {
        "count": 42,
        "page": 1,
        "first": 1,
        "last": 1,
        "hits": 1,
        "pageCount": 1,
        "items": [{"affiliateUrl": "https://hb.afl.rakuten.co.jp/example"}],
    },
    separators=(",", ":"),
).encode()
_ENV_NAMES = {
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "SSLKEYLOGFILE",
    "ALL_PROXY",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "all_proxy",
    "https_proxy",
    "http_proxy",
    "no_proxy",
}


def credentials() -> RakutenLiveSmokeCredentials:
    return RakutenLiveSmokeCredentials(
        _application_id=APPLICATION_ID.encode(),
        _access_key=WIRE_HEADER_PROOF.encode(),
        _affiliate_id=AFFILIATE_ID.encode(),
    )


@dataclass
class FakeReader:
    value: RakutenLiveSmokeCredentials = field(default_factory=credentials)
    calls: int = 0

    def read(self) -> RakutenLiveSmokeCredentials:
        self.calls += 1
        return self.value


@dataclass
class FakeResponse:
    status: int = 200
    content_type: str | None = "application/json; charset=utf-8"
    body: bytes = SUCCESS
    content_length: str | None = None
    transfer_encoding: str | None = None
    offset: int = 0

    def getheader(self, name: str, default: str | None = None) -> str | None:
        if name == "Content-Type":
            return self.content_type
        if name == "Content-Length":
            return self.content_length
        if name == "Transfer-Encoding":
            return self.transfer_encoding
        return default

    def read(self, amount: int | None = None) -> bytes:
        size = len(self.body) - self.offset if amount is None else amount
        result = self.body[self.offset : self.offset + size]
        self.offset += len(result)
        return result


@dataclass
class FakeConnection:
    response: FakeResponse
    calls: list[tuple[str, object]] = field(default_factory=list)

    def connect(self) -> None:
        self.calls.append(("connect", None))

    def set_read_timeout(self, seconds: int) -> None:
        self.calls.append(("timeout", seconds))

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        self.calls.append(("request", (method, path, headers)))

    def getresponse(self) -> FakeResponse:
        self.calls.append(("response", None))
        return self.response

    def close(self) -> None:
        self.calls.append(("close", None))


@dataclass
class FakeFactory:
    connection: FakeConnection
    opens: list[dict[str, object]] = field(default_factory=list)

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> FakeConnection:
        self.opens.append(
            {
                "host": host,
                "port": port,
                "timeout": connect_timeout_seconds,
                "context": tls_context,
            }
        )
        return self.connection


@dataclass
class FakePinnedSocket:
    peer: tuple[object, ...] = ("8.8.8.8", 443)
    connect_error: BaseException | None = None
    calls: list[tuple[str, object]] = field(default_factory=list)
    sent: list[bytes] = field(default_factory=list)
    closed: bool = False

    def settimeout(self, seconds: float | None) -> None:
        self.calls.append(("timeout", seconds))

    def connect(self, address: tuple[object, ...]) -> None:
        self.calls.append(("connect", address))
        if self.connect_error is not None:
            raise self.connect_error

    def getpeername(self) -> tuple[object, ...]:
        self.calls.append(("peer", None))
        return self.peer

    def setsockopt(self, level: int, option: int, value: int) -> None:
        self.calls.append(("setsockopt", (level, option, value)))

    def sendall(self, data: bytes) -> None:
        self.sent.append(bytes(data))

    def close(self) -> None:
        self.calls.append(("close", None))
        self.closed = True


@dataclass
class FakeHttpResponseSocket:
    payload: bytes

    def makefile(self, mode: str) -> io.BytesIO:
        assert mode == "rb"
        return io.BytesIO(self.payload)


@dataclass
class RaisingConnection(FakeConnection):
    phase: str = "connect"
    error: BaseException = field(default_factory=OSError)

    def _raise(self, phase: str) -> None:
        if self.phase == phase:
            raise self.error

    def connect(self) -> None:
        self._raise("connect")
        super().connect()

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        self._raise("request")
        super().request(method, path, headers)

    def getresponse(self) -> FakeResponse:
        self._raise("response")
        return super().getresponse()


@dataclass
class StaticTransport:
    response: RakutenLiveSmokeHttpResponse
    calls: int = 0

    def execute(self, policy: object, secret: object) -> RakutenLiveSmokeHttpResponse:
        assert policy == fixed_rakuten_live_smoke_policy()
        assert type(secret) is RakutenLiveSmokeCredentials
        self.calls += 1
        return self.response


@dataclass
class MemoryWriter:
    reports: list[RakutenLiveSmokeReport] = field(default_factory=list)
    doctor_checks: int = 0
    preflights: int = 0

    def doctor_ready(self) -> None:
        self.doctor_checks += 1

    def preflight(self) -> None:
        self.preflights += 1

    def write(self, report: RakutenLiveSmokeReport) -> None:
        self.reports.append(report)


@dataclass
class FailingPreflightWriter(MemoryWriter):
    def preflight(self) -> None:
        self.preflights += 1
        fail_rakuten_live_smoke(RakutenLiveSmokeDiagnosticCode.REPORT_STORE_INVALID)


@pytest.fixture(autouse=True)
def clean_transport_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_direct_transport_uses_exact_one_get_and_access_key_header_only() -> None:
    connection = FakeConnection(FakeResponse())
    factory = FakeFactory(connection)
    transport = DirectRakutenLiveSmokeTransport(factory)

    response = transport.execute(fixed_rakuten_live_smoke_policy(), credentials())

    assert response.status == 200
    assert factory.opens[0]["host"] == RAKUTEN_LIVE_SMOKE_HOST
    assert factory.opens[0]["port"] == 443
    assert factory.opens[0]["timeout"] == CONNECT_TIMEOUT_SECONDS
    requests = [entry for entry in connection.calls if entry[0] == "request"]
    assert len(requests) == 1
    method, target, headers = cast(tuple[str, str, dict[str, str]], requests[0][1])
    assert method == "GET"
    parsed = urlsplit(target)
    assert parsed.path == RAKUTEN_LIVE_SMOKE_PATH
    query = parse_qs(parsed.query, strict_parsing=True)
    assert query == {
        "applicationId": [APPLICATION_ID],
        "affiliateId": [AFFILIATE_ID],
        "keyword": ["収納"],
        "hits": ["1"],
        "page": ["1"],
        "format": ["json"],
        "formatVersion": ["2"],
        "sort": ["standard"],
        "elements": ["count,page,first,last,hits,pageCount,affiliateUrl"],
    }
    assert WIRE_HEADER_PROOF not in target
    assert "accessKey" not in query
    expected_headers = {
        "Accept": RAKUTEN_LIVE_SMOKE_ACCEPT,
        "User-Agent": RAKUTEN_LIVE_SMOKE_USER_AGENT,
    }
    expected_headers[RAKUTEN_LIVE_SMOKE_ACCESS_HEADER] = WIRE_HEADER_PROOF
    assert RAKUTEN_LIVE_SMOKE_ACCESS_HEADER == "accessKey"
    assert headers == expected_headers
    assert connection.calls.count(("timeout", READ_TIMEOUT_SECONDS)) == 1
    assert connection.calls[-1][0] == "close"
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        transport.execute(fixed_rakuten_live_smoke_policy(), credentials())
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.REQUEST_ALREADY_ATTEMPTED
    assert len(requests) == 1


@pytest.mark.parametrize(
    ("family", "address"),
    [
        (socket.AF_INET, "127.0.0.1"),
        (socket.AF_INET, "10.0.0.1"),
        (socket.AF_INET, "169.254.169.254"),
        (socket.AF_INET, "0.0.0.0"),
        (socket.AF_INET, "100.64.0.1"),
        (socket.AF_INET, "192.0.2.1"),
        (socket.AF_INET, "224.0.0.1"),
        (socket.AF_INET6, "::1"),
        (socket.AF_INET6, "::"),
        (socket.AF_INET6, "fe80::1"),
        (socket.AF_INET6, "fc00::1"),
        (socket.AF_INET6, "ff02::1"),
        (socket.AF_INET6, "fec0::1"),
        (socket.AF_INET6, "2001:db8::1"),
        (socket.AF_INET6, "::ffff:127.0.0.1"),
        (socket.AF_INET6, "2606:4700:4700::1111%lo"),
        (socket.AF_INET6, "2606:4700:4700::1111%1"),
    ],
)
def test_system_factory_rejects_non_public_dns_before_socket_creation(
    monkeypatch: pytest.MonkeyPatch, family: int, address: str
) -> None:
    socket_address: tuple[object, ...]
    if family == socket.AF_INET:
        socket_address = (address, 443)
    else:
        socket_address = (address, 443, 0, 0)
    monkeypatch.setattr(
        live_adapter.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", socket_address)
        ],
    )
    socket_calls = 0

    def forbidden_socket(*args: object, **kwargs: object) -> FakePinnedSocket:
        nonlocal socket_calls
        socket_calls += 1
        raise AssertionError("socket creation must not follow rejected DNS")

    monkeypatch.setattr(live_adapter.socket, "socket", forbidden_socket)
    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        SystemRakutenLiveSmokeHttpsConnectionFactory().open(
            host=RAKUTEN_LIVE_SMOKE_HOST,
            port=443,
            connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
            tls_context=context,
        )
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.DNS_FAILED
    assert caught.value.request_count == 0
    assert socket_calls == 0


def test_system_factory_rejects_mixed_or_malformed_dns_as_a_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    unsafe_rows: list[object] = [
        [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("8.8.8.8", 443),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("169.254.169.254", 443),
            ),
        ],
        [],
        [(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP, "", ("8.8.8.8", 443))],
        [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 80))],
        [
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("2606:4700:4700::1111", 443, 0, 4),
            )
        ],
        [(socket.AF_UNIX, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 443))],
        [(socket.AF_INET, socket.SOCK_STREAM)],
    ]
    for rows in unsafe_rows:
        monkeypatch.setattr(
            live_adapter.socket,
            "getaddrinfo",
            lambda *args, _rows=rows, **kwargs: _rows,
        )
        with pytest.raises(RakutenLiveSmokeFailure) as caught:
            SystemRakutenLiveSmokeHttpsConnectionFactory().open(
                host=RAKUTEN_LIVE_SMOKE_HOST,
                port=443,
                connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
                tls_context=context,
            )
        assert caught.value.code is RakutenLiveSmokeDiagnosticCode.DNS_FAILED


def test_pinned_connection_resolves_once_uses_first_candidate_and_keeps_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver_calls: list[tuple[object, ...]] = []

    def resolve(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        resolver_calls.append((*args, kwargs))
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("8.8.8.8", 443),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("1.1.1.1", 443),
            ),
        ]

    raw = FakePinnedSocket()
    socket_calls: list[tuple[object, ...]] = []
    tls_hosts: list[str | None] = []
    monkeypatch.setattr(live_adapter.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(
        live_adapter.socket,
        "socket",
        lambda *args: socket_calls.append(args) or raw,
    )
    monkeypatch.setattr(
        live_adapter.socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("second DNS-capable connection path is forbidden")
        ),
    )

    def wrap_socket(
        _context: ssl.SSLContext,
        sock: FakePinnedSocket,
        *args: object,
        server_hostname: str | None = None,
        **kwargs: object,
    ) -> FakePinnedSocket:
        tls_hosts.append(server_hostname)
        return sock

    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap_socket)
    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    connection = SystemRakutenLiveSmokeHttpsConnectionFactory().open(
        host=RAKUTEN_LIVE_SMOKE_HOST,
        port=443,
        connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
        tls_context=context,
    )
    connection.connect()
    connection.request("GET", "/fixed", {"Accept": "application/json"})
    assert len(resolver_calls) == 1
    assert socket_calls == [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)]
    assert raw.calls.count(("connect", ("8.8.8.8", 443))) == 1
    assert not any(entry == ("connect", ("1.1.1.1", 443)) for entry in raw.calls)
    assert tls_hosts == [RAKUTEN_LIVE_SMOKE_HOST]
    wire = b"".join(raw.sent)
    assert b"Host: openapi.rakuten.co.jp\r\n" in wire
    assert b"Host: 8.8.8.8" not in wire
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        connection.connect()
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.CONNECTION_FAILED
    assert len(socket_calls) == 1


@pytest.mark.parametrize("phase", ["connect", "tls"])
def test_pinned_connection_failure_closes_socket_without_fallback_or_request(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    rows = [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("1.1.1.1", 443)),
    ]
    monkeypatch.setattr(
        live_adapter.socket, "getaddrinfo", lambda *args, **kwargs: rows
    )
    raw = FakePinnedSocket(
        connect_error=ConnectionRefusedError() if phase == "connect" else None
    )
    socket_calls = 0

    def one_socket(*args: object) -> FakePinnedSocket:
        nonlocal socket_calls
        socket_calls += 1
        return raw

    monkeypatch.setattr(live_adapter.socket, "socket", one_socket)
    if phase == "tls":
        monkeypatch.setattr(
            ssl.SSLContext,
            "wrap_socket",
            lambda *args, **kwargs: (_ for _ in ()).throw(ssl.SSLError()),
        )
    transport = DirectRakutenLiveSmokeTransport(
        SystemRakutenLiveSmokeHttpsConnectionFactory()
    )
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        transport.execute(fixed_rakuten_live_smoke_policy(), credentials())
    expected = (
        RakutenLiveSmokeDiagnosticCode.CONNECTION_FAILED
        if phase == "connect"
        else RakutenLiveSmokeDiagnosticCode.TLS_FAILED
    )
    assert caught.value.code is expected
    assert caught.value.request_count == 0
    assert socket_calls == 1
    assert raw.closed is True
    assert not raw.sent


def test_service_success_requires_https_affiliate_url() -> None:
    transport = StaticTransport(
        RakutenLiveSmokeHttpResponse(200, "application/json", SUCCESS)
    )
    service = RakutenLiveSmokeService(FakeReader(), transport)
    observation = service.run()
    assert observation.request_count == 1
    assert observation.response_sha256 == hashlib.sha256(SUCCESS).hexdigest()
    assert observation.affiliate_url_present is True
    assert transport.calls == 1
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        service.run()
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.REQUEST_ALREADY_ATTEMPTED
    assert transport.calls == 1


def test_premature_content_length_eof_never_hashes_or_passes() -> None:
    wire = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        + f"Content-Length: {len(SUCCESS) + 1}\r\n".encode("ascii")
        + b"\r\n"
        + SUCCESS
    )
    response = http.client.HTTPResponse(FakeHttpResponseSocket(wire), method="GET")
    response.begin()
    connection = FakeConnection(cast(FakeResponse, response))
    transport = DirectRakutenLiveSmokeTransport(FakeFactory(connection))
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        transport.execute(fixed_rakuten_live_smoke_policy(), credentials())
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS
    assert caught.value.request_count == 1
    assert caught.value.response_sha256 is None
    assert connection.calls[-1][0] == "close"


@pytest.mark.parametrize(
    ("content_length", "transfer_encoding"),
    [
        ("not-a-length", None),
        (str(len(SUCCESS)), "chunked"),
        (None, "gzip"),
    ],
)
def test_ambiguous_response_framing_never_hashes(
    content_length: str | None, transfer_encoding: str | None
) -> None:
    response = FakeResponse(
        body=SUCCESS,
        content_length=content_length,
        transfer_encoding=transfer_encoding,
    )
    connection = FakeConnection(response)
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        DirectRakutenLiveSmokeTransport(FakeFactory(connection)).execute(
            fixed_rakuten_live_smoke_policy(), credentials()
        )
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS
    assert caught.value.request_count == 1
    assert caught.value.response_sha256 is None


@pytest.mark.parametrize(
    ("phase", "error", "code", "request_count"),
    [
        ("connect", socket.gaierror(), RakutenLiveSmokeDiagnosticCode.DNS_FAILED, 0),
        ("connect", ssl.SSLError(), RakutenLiveSmokeDiagnosticCode.TLS_FAILED, 0),
        ("connect", TimeoutError(), RakutenLiveSmokeDiagnosticCode.TIMEOUT, 0),
        (
            "connect",
            ConnectionRefusedError(),
            RakutenLiveSmokeDiagnosticCode.CONNECTION_FAILED,
            0,
        ),
        (
            "request",
            OSError(WIRE_HEADER_PROOF),
            RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS,
            1,
        ),
        (
            "response",
            OSError(WIRE_HEADER_PROOF),
            RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS,
            1,
        ),
    ],
)
def test_network_failures_are_closed_and_never_reflect_secrets(
    phase: str,
    error: BaseException,
    code: RakutenLiveSmokeDiagnosticCode,
    request_count: int,
) -> None:
    connection = RaisingConnection(FakeResponse(), phase=phase, error=error)
    transport = DirectRakutenLiveSmokeTransport(FakeFactory(connection))
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        transport.execute(fixed_rakuten_live_smoke_policy(), credentials())
    assert caught.value.code is code
    assert caught.value.response_sha256 is None
    assert caught.value.request_count == request_count
    assert WIRE_HEADER_PROOF not in str(caught.value)
    assert WIRE_HEADER_PROOF not in repr(caught.value)
    assert connection.calls[-1][0] == "close"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (301, RakutenLiveSmokeDiagnosticCode.HTTP_REDIRECT_REJECTED),
        (400, RakutenLiveSmokeDiagnosticCode.HTTP_400),
        (401, RakutenLiveSmokeDiagnosticCode.HTTP_401),
        (403, RakutenLiveSmokeDiagnosticCode.HTTP_403),
        (404, RakutenLiveSmokeDiagnosticCode.HTTP_404),
        (429, RakutenLiveSmokeDiagnosticCode.HTTP_429),
        (500, RakutenLiveSmokeDiagnosticCode.HTTP_500),
        (503, RakutenLiveSmokeDiagnosticCode.HTTP_503),
        (418, RakutenLiveSmokeDiagnosticCode.HTTP_STATUS_UNEXPECTED),
    ],
)
def test_http_failures_are_fixed_and_non_reflective(
    status: int, code: RakutenLiveSmokeDiagnosticCode
) -> None:
    reflected = b"provider-secret-error-description"
    service = RakutenLiveSmokeService(
        FakeReader(),
        StaticTransport(RakutenLiveSmokeHttpResponse(status, "text/plain", reflected)),
    )
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        service.run()
    assert caught.value.code is code
    assert caught.value.response_sha256 == hashlib.sha256(reflected).hexdigest()
    assert str(caught.value) == code.value
    assert reflected.decode() not in repr(caught.value)
    if status == 429:
        assert caught.value.auth.value == "NOT_OBSERVED"
        assert caught.value.rate.value == "THROTTLED"


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"{", RakutenLiveSmokeDiagnosticCode.RESPONSE_JSON_INVALID),
        (
            b'{"count":1,"count":1}',
            RakutenLiveSmokeDiagnosticCode.RESPONSE_JSON_DUPLICATE_KEY,
        ),
        (b'{"count":NaN}', RakutenLiveSmokeDiagnosticCode.RESPONSE_JSON_NONFINITE),
        (
            b'{"count":1,"page":1,"first":1,"last":1,"hits":1,"pageCount":1,"items":[],"unknown":1}',
            RakutenLiveSmokeDiagnosticCode.RESPONSE_SCHEMA_DRIFT,
        ),
        (
            SUCCESS.replace(b"https://", b"http://"),
            RakutenLiveSmokeDiagnosticCode.AFFILIATE_URL_INVALID,
        ),
        (
            SUCCESS.replace(b'"https://hb.afl.rakuten.co.jp/example"', b'""'),
            RakutenLiveSmokeDiagnosticCode.AFFILIATE_URL_MISSING,
        ),
    ],
)
def test_malformed_and_schema_drift_are_closed(
    body: bytes, code: RakutenLiveSmokeDiagnosticCode
) -> None:
    service = RakutenLiveSmokeService(
        FakeReader(),
        StaticTransport(RakutenLiveSmokeHttpResponse(200, "application/json", body)),
    )
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        service.run()
    assert caught.value.code is code
    assert caught.value.request_count == 1
    assert caught.value.body_byte_count == len(body)
    assert caught.value.response_sha256 == hashlib.sha256(body).hexdigest()


def test_invalid_content_type_encoding_and_oversize_are_closed() -> None:
    cases = (
        (
            RakutenLiveSmokeHttpResponse(200, "text/json", SUCCESS),
            RakutenLiveSmokeDiagnosticCode.RESPONSE_CONTENT_TYPE_INVALID,
        ),
        (
            RakutenLiveSmokeHttpResponse(200, "application/json", b"\xff"),
            RakutenLiveSmokeDiagnosticCode.RESPONSE_ENCODING_INVALID,
        ),
    )
    for response, expected in cases:
        with pytest.raises(RakutenLiveSmokeFailure) as caught:
            RakutenLiveSmokeService(FakeReader(), StaticTransport(response)).run()
        assert caught.value.code is expected

    oversized = FakeConnection(FakeResponse(body=b"x" * (2 * 1024 * 1024 + 1)))
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        DirectRakutenLiveSmokeTransport(FakeFactory(oversized)).execute(
            fixed_rakuten_live_smoke_policy(), credentials()
        )
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.RESPONSE_OVERSIZED
    assert caught.value.request_count == 1
    assert caught.value.http_status == 200
    assert caught.value.auth.value == "ACCEPTED"
    assert caught.value.schema.value == "INVALID"
    assert caught.value.rate.value == "SINGLE_REQUEST_NOT_THROTTLED"
    assert caught.value.response_sha256 is None
    assert oversized.calls[-1][0] == "close"

    static_transport = StaticTransport(
        RakutenLiveSmokeHttpResponse(
            200,
            "application/json",
            b"x" * (2 * 1024 * 1024 + 1),
        )
    )
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        RakutenLiveSmokeService(FakeReader(), static_transport).run()
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.RESPONSE_OVERSIZED
    assert caught.value.request_count == 1
    assert caught.value.response_sha256 is None
    assert static_transport.calls == 1


@pytest.mark.parametrize(
    ("status", "auth", "rate"),
    [(401, "REJECTED", "NOT_OBSERVED"), (429, "NOT_OBSERVED", "THROTTLED")],
)
def test_oversized_error_response_preserves_safe_http_classification(
    status: int, auth: str, rate: str
) -> None:
    connection = FakeConnection(
        FakeResponse(status=status, body=b"x" * (2 * 1024 * 1024 + 1))
    )
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        DirectRakutenLiveSmokeTransport(FakeFactory(connection)).execute(
            fixed_rakuten_live_smoke_policy(), credentials()
        )
    failure = caught.value
    assert failure.code is RakutenLiveSmokeDiagnosticCode.RESPONSE_OVERSIZED
    assert failure.http_status == status
    assert failure.request_count == 1
    assert failure.auth.value == auth
    assert failure.schema.value == "NOT_OBSERVED"
    assert failure.rate.value == rate
    assert failure.response_sha256 is None


def _credential_repository(
    tmp_path: Path, value: dict[str, object] | None = None
) -> Path:
    root = tmp_path / "repository"
    smoke = root / ".secrets" / "rakuten-live-smoke"
    smoke.mkdir(parents=True, mode=0o700)
    os.chmod(root / ".secrets", 0o700)
    os.chmod(smoke, 0o700)
    payload = (
        value
        if value is not None
        else {
            "schema_version": 1,
            "application_id": APPLICATION_ID,
            "affiliate_id": AFFILIATE_ID,
        }
    )
    if value is None:
        payload[_ACCESS_FIELD] = WIRE_HEADER_PROOF
    path = smoke / "credentials.v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)
    _write_staging_binding(root)
    return root


def _write_staging_binding(
    root: Path,
    *,
    override: dict[str, object] | None = None,
) -> Path:
    smoke = root / ".secrets/rakuten-live-smoke"
    credential_path = smoke / "credentials.v1.json"
    payload = (
        override
        if override is not None
        else {
            "schema_version": 1,
            "environment": "staging",
            "credential_purpose": (
                "DEDICATED_TEST_CREDENTIAL_FOR_NON_FORMAL_DIAGNOSTIC"
            ),
            "credential_record_sha256": hashlib.sha256(
                credential_path.read_bytes()
            ).hexdigest(),
        }
    )
    path = smoke / "staging-credential-binding.v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def test_doctor_is_read_only_and_checks_report_metadata_before_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _credential_repository(tmp_path / "ready")
    reports = root / ".secrets/rakuten-live-smoke/reports"
    reader = FakeReader()
    writer = OwnerPrivateRakutenLiveSmokeReportWriter(root)
    assert doctor(reader, writer) == (0, DOCTOR_READY)
    assert reader.calls == 1
    assert not reports.exists()

    invalid_root = _credential_repository(tmp_path / "invalid")
    invalid_reports = invalid_root / ".secrets/rakuten-live-smoke/reports"
    invalid_reports.mkdir(mode=0o755)
    untouched_reader = FakeReader()
    assert doctor(
        untouched_reader, OwnerPrivateRakutenLiveSmokeReportWriter(invalid_root)
    ) == (2, DOCTOR_NOT_READY)
    assert untouched_reader.calls == 0

    adapter_os = getattr(live_adapter, "os")
    monkeypatch.setattr(adapter_os, "O_TMPFILE", 0)
    unsupported_reader = FakeReader()
    assert doctor(unsupported_reader, writer) == (2, DOCTOR_NOT_READY)
    assert unsupported_reader.calls == 0


def test_live_preflight_failure_makes_no_get_and_reports_zero_requests() -> None:
    writer = FailingPreflightWriter()
    transport = StaticTransport(
        RakutenLiveSmokeHttpResponse(200, "application/json", SUCCESS)
    )
    clock_values = iter(
        [
            datetime(2026, 8, 21, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 0, 0, 1, tzinfo=timezone.utc),
        ]
    )
    code, output = run_live_smoke(
        reader=FakeReader(),
        transport=transport,
        writer=writer,
        clock=lambda: next(clock_values),
        run_id_factory=lambda ignored: (
            "20260821T000000.000000Z-dddddddddddddddddddddddddddddddd"
        ),
    )
    assert (code, output) == (1, "RAKUTEN_LIVE_SMOKE_FAIL_REPORT_STORE_INVALID")
    assert writer.preflights == 1
    assert transport.calls == 0
    assert len(writer.reports) == 1
    assert writer.reports[0].request_count == 0


def test_owner_private_reader_and_report_writer_are_value_free(tmp_path: Path) -> None:
    root = _credential_repository(tmp_path)
    reader = OwnerPrivateRakutenLiveSmokeCredentialReader(root)
    loaded = reader.read()
    assert WIRE_HEADER_PROOF not in repr(loaded)
    writer = OwnerPrivateRakutenLiveSmokeReportWriter(root)
    clock_values = iter(
        [
            datetime(2026, 8, 21, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 0, 0, 1, tzinfo=timezone.utc),
        ]
    )
    code, output = run_live_smoke(
        reader=reader,
        transport=StaticTransport(
            RakutenLiveSmokeHttpResponse(200, "application/json", SUCCESS)
        ),
        writer=writer,
        clock=lambda: next(clock_values),
        run_id_factory=lambda ignored: (
            "20260821T000000.000000Z-0123456789abcdef0123456789abcdef"
        ),
    )
    assert (code, output) == (0, LIVE_PASS)
    report_path = next((root / ".secrets/rakuten-live-smoke/reports").iterdir())
    assert report_path.stat().st_mode & 0o777 == 0o600
    raw = report_path.read_bytes()
    assert all(
        secret.encode() not in raw
        for secret in (APPLICATION_ID, WIRE_HEADER_PROOF, AFFILIATE_ID)
    )
    assert b"affiliateUrl" not in raw
    report = json.loads(raw)
    assert exact_report_mapping(report)
    assert report["schema"] == "RAOS_ST0505_RAKUTEN_LIVE_SMOKE_REPORT_V2"
    assert report["version"] == 2
    assert report["response_sha256"] == hashlib.sha256(SUCCESS).hexdigest()
    assert report["diagnostic_code"] == "LIVE_SMOKE_PASS"
    assert report["request_count"] == 1
    assert report["retry_count"] == 0
    assert report["pagination_count"] == 0
    assert report["formal_tst_016"] == "NOT_EXECUTED"
    assert report["staging"] == "NOT_EXECUTED"
    assert report["production"] == "NOT_EXECUTED"


@pytest.mark.parametrize("bad_mode", [0o644, 0o400, 0o666])
def test_credential_file_mode_is_exact(tmp_path: Path, bad_mode: int) -> None:
    root = _credential_repository(tmp_path)
    path = root / ".secrets/rakuten-live-smoke/credentials.v1.json"
    os.chmod(path, bad_mode)
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        OwnerPrivateRakutenLiveSmokeCredentialReader(root).read()
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID


def test_staging_binding_is_required_and_validated_before_credential_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _credential_repository(tmp_path)
    binding = root / ".secrets/rakuten-live-smoke/staging-credential-binding.v1.json"
    binding.unlink()
    opened_credentials = False
    original_open = os.open

    def recording_open(
        path: os.PathLike[str] | str | bytes,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal opened_credentials
        if path == "credentials.v1.json":
            opened_credentials = True
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(getattr(live_adapter, "os"), "open", recording_open)
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        OwnerPrivateRakutenLiveSmokeCredentialReader(root).read()
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID
    assert opened_credentials is False


@pytest.mark.parametrize(
    "binding",
    [
        {},
        {
            "schema_version": 2,
            "environment": "staging",
            "credential_purpose": (
                "DEDICATED_TEST_CREDENTIAL_FOR_NON_FORMAL_DIAGNOSTIC"
            ),
            "credential_record_sha256": "0" * 64,
        },
        {
            "schema_version": 1,
            "environment": "production",
            "credential_purpose": (
                "DEDICATED_TEST_CREDENTIAL_FOR_NON_FORMAL_DIAGNOSTIC"
            ),
            "credential_record_sha256": "0" * 64,
        },
        {
            "schema_version": 1,
            "environment": "staging",
            "credential_purpose": "GENERIC",
            "credential_record_sha256": "0" * 64,
        },
        {
            "schema_version": 1,
            "environment": "staging",
            "credential_purpose": (
                "DEDICATED_TEST_CREDENTIAL_FOR_NON_FORMAL_DIAGNOSTIC"
            ),
            "credential_record_sha256": "not-a-digest",
        },
        {
            "schema_version": 1,
            "environment": "staging",
            "credential_purpose": (
                "DEDICATED_TEST_CREDENTIAL_FOR_NON_FORMAL_DIAGNOSTIC"
            ),
            "credential_record_sha256": "0" * 64,
            "unknown": True,
        },
    ],
)
def test_staging_binding_schema_and_purpose_fail_closed(
    tmp_path: Path, binding: dict[str, object]
) -> None:
    root = _credential_repository(tmp_path)
    _write_staging_binding(root, override=binding)
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        OwnerPrivateRakutenLiveSmokeCredentialReader(root).read()
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID
    assert caught.value.request_count == 0


def test_staging_binding_hash_mode_symlink_and_duplicate_key_fail_closed(
    tmp_path: Path,
) -> None:
    stale_root = _credential_repository(tmp_path / "stale")
    credential = stale_root / ".secrets/rakuten-live-smoke/credentials.v1.json"
    credential.write_bytes(credential.read_bytes() + b" ")
    credential.chmod(0o600)
    with pytest.raises(RakutenLiveSmokeFailure):
        OwnerPrivateRakutenLiveSmokeCredentialReader(stale_root).read()

    mode_root = _credential_repository(tmp_path / "mode")
    binding = (
        mode_root / ".secrets/rakuten-live-smoke/staging-credential-binding.v1.json"
    )
    binding.chmod(0o644)
    with pytest.raises(RakutenLiveSmokeFailure):
        OwnerPrivateRakutenLiveSmokeCredentialReader(mode_root).read()

    symlink_root = _credential_repository(tmp_path / "symlink")
    binding = (
        symlink_root / ".secrets/rakuten-live-smoke/staging-credential-binding.v1.json"
    )
    target = binding.with_name("binding-target.json")
    binding.replace(target)
    binding.symlink_to(target.name)
    with pytest.raises(RakutenLiveSmokeFailure):
        OwnerPrivateRakutenLiveSmokeCredentialReader(symlink_root).read()

    duplicate_root = _credential_repository(tmp_path / "duplicate")
    binding = (
        duplicate_root
        / ".secrets/rakuten-live-smoke/staging-credential-binding.v1.json"
    )
    digest = hashlib.sha256(
        (
            duplicate_root / ".secrets/rakuten-live-smoke/credentials.v1.json"
        ).read_bytes()
    ).hexdigest()
    binding.write_text(
        '{"schema_version":1,"schema_version":1,"environment":"staging",'
        '"credential_purpose":'
        '"DEDICATED_TEST_CREDENTIAL_FOR_NON_FORMAL_DIAGNOSTIC",'
        f'"credential_record_sha256":"{digest}"}}',
        encoding="utf-8",
    )
    binding.chmod(0o600)
    with pytest.raises(RakutenLiveSmokeFailure):
        OwnerPrivateRakutenLiveSmokeCredentialReader(duplicate_root).read()


def test_credential_leaf_and_ancestor_symlinks_are_rejected(tmp_path: Path) -> None:
    root = _credential_repository(tmp_path / "leaf")
    path = root / ".secrets/rakuten-live-smoke/credentials.v1.json"
    real = path.with_name("real.json")
    path.rename(real)
    path.symlink_to(real.name)
    with pytest.raises(RakutenLiveSmokeFailure):
        OwnerPrivateRakutenLiveSmokeCredentialReader(root).read()

    actual = _credential_repository(tmp_path / "ancestor")
    link_root = tmp_path / "linked-repository"
    link_root.symlink_to(actual, target_is_directory=True)
    with pytest.raises(RakutenLiveSmokeFailure):
        OwnerPrivateRakutenLiveSmokeCredentialReader(link_root).read()


def test_credential_owner_size_and_tocou_replacement_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong_owner_root = _credential_repository(tmp_path / "owner")
    real_uid = os.getuid()
    adapter_os = getattr(live_adapter, "os")
    monkeypatch.setattr(adapter_os, "getuid", lambda: real_uid + 1)
    with pytest.raises(RakutenLiveSmokeFailure):
        OwnerPrivateRakutenLiveSmokeCredentialReader(wrong_owner_root).read()
    monkeypatch.setattr(adapter_os, "getuid", lambda: real_uid)

    large_root = _credential_repository(tmp_path / "large")
    large_path = large_root / ".secrets/rakuten-live-smoke/credentials.v1.json"
    large_path.write_bytes(b"x" * (16 * 1024 + 1))
    os.chmod(large_path, 0o600)
    with pytest.raises(RakutenLiveSmokeFailure):
        OwnerPrivateRakutenLiveSmokeCredentialReader(large_root).read()

    race_root = _credential_repository(tmp_path / "race")
    race_path = race_root / ".secrets/rakuten-live-smoke/credentials.v1.json"
    replacement = race_path.with_name("replacement.json")
    replacement.write_bytes(race_path.read_bytes())
    os.chmod(replacement, 0o600)
    original_stat = os.stat
    swapped = False

    def racing_stat(
        path: os.PathLike[str] | str | bytes | int,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        nonlocal swapped
        if path == "credentials.v1.json" and dir_fd is not None and not swapped:
            swapped = True
            replacement.replace(race_path)
        return original_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(adapter_os, "stat", racing_stat)
    with pytest.raises(RakutenLiveSmokeFailure):
        OwnerPrivateRakutenLiveSmokeCredentialReader(race_root).read()
    assert swapped


def test_credential_same_inode_rewrite_during_read_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _credential_repository(tmp_path)
    path = root / ".secrets/rakuten-live-smoke/credentials.v1.json"
    original = path.read_bytes()
    replacement = original.replace(
        WIRE_HEADER_PROOF.encode(),
        b"Z" * len(WIRE_HEADER_PROOF.encode()),
    )
    assert len(replacement) == len(original) and replacement != original
    adapter_os = getattr(live_adapter, "os")
    original_read = os.read
    rewritten = False

    def racing_read(descriptor: int, maximum: int) -> bytes:
        nonlocal rewritten
        data = original_read(descriptor, maximum)
        if data and not rewritten:
            rewritten = True
            path.write_bytes(replacement)
            path.chmod(0o600)
        return data

    monkeypatch.setattr(adapter_os, "read", racing_read)
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        OwnerPrivateRakutenLiveSmokeCredentialReader(root).read()
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID
    assert caught.value.request_count == 0
    assert rewritten


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 1, "application_id": "a", "access_key": "b"},
        {
            "schema_version": 1,
            "application_id": "a",
            "access_key": "b",
            "affiliate_id": "c",
            "unknown": "d",
        },
        {
            "schema_version": 2,
            "application_id": "a",
            "access_key": "b",
            "affiliate_id": "c",
        },
        {
            "schema_version": 1,
            "application_id": " a",
            "access_key": "b",
            "affiliate_id": "c",
        },
        {
            "schema_version": 1,
            "application_id": "a",
            "access_key": "b\n",
            "affiliate_id": "c",
        },
    ],
)
def test_credential_schema_and_control_values_are_rejected(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    root = _credential_repository(tmp_path, payload)
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        OwnerPrivateRakutenLiveSmokeCredentialReader(root).read()
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID


def test_duplicate_credential_key_is_rejected(tmp_path: Path) -> None:
    root = _credential_repository(tmp_path)
    path = root / ".secrets/rakuten-live-smoke/credentials.v1.json"
    path.write_text(
        '{"schema_version":1,"application_id":"a","application_id":"b",'
        '"access_key":"c","affiliate_id":"d"}',
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    _write_staging_binding(root)
    with pytest.raises(RakutenLiveSmokeFailure):
        OwnerPrivateRakutenLiveSmokeCredentialReader(root).read()


def test_proxy_and_tls_override_are_rejected_before_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakeFactory(FakeConnection(FakeResponse()))
    monkeypatch.setenv("HTTPS_PROXY", "http://untrusted.invalid")
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        DirectRakutenLiveSmokeTransport(factory).execute(
            fixed_rakuten_live_smoke_policy(), credentials()
        )
    assert caught.value.code is RakutenLiveSmokeDiagnosticCode.TLS_ENVIRONMENT_INVALID
    assert factory.opens == []


def test_deep_json_is_rejected_without_retry() -> None:
    body = ("[" * 40 + "0" + "]" * 40).encode()
    transport = StaticTransport(
        RakutenLiveSmokeHttpResponse(200, "application/json", body)
    )
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        RakutenLiveSmokeService(FakeReader(), transport).run()
    assert (
        caught.value.code is RakutenLiveSmokeDiagnosticCode.RESPONSE_JSON_TREE_INVALID
    )
    assert transport.calls == 1


def test_sanitized_failure_report_and_output_contain_no_secret() -> None:
    writer = MemoryWriter()
    clock_values = iter(
        [
            datetime(2026, 8, 21, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 0, 0, 1, tzinfo=timezone.utc),
        ]
    )
    code, output = run_live_smoke(
        reader=FakeReader(),
        transport=StaticTransport(
            RakutenLiveSmokeHttpResponse(403, "text/plain", WIRE_HEADER_PROOF.encode())
        ),
        writer=writer,
        clock=lambda: next(clock_values),
        run_id_factory=lambda ignored: (
            "20260821T000000.000000Z-fedcba9876543210fedcba9876543210"
        ),
    )
    assert code == 1
    assert output == "RAKUTEN_LIVE_SMOKE_FAIL_HTTP_403"
    assert len(writer.reports) == 1
    raw = writer.reports[0].json_bytes
    report = json.loads(raw)
    assert (
        report["response_sha256"]
        == hashlib.sha256(WIRE_HEADER_PROOF.encode()).hexdigest()
    )
    assert WIRE_HEADER_PROOF.encode() not in raw
    assert APPLICATION_ID.encode() not in raw
    assert AFFILIATE_ID.encode() not in raw
    assert b"text/plain" not in raw
    assert b"affiliateUrl" not in raw
