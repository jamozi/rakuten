"""Fake-connection tests for the numeric-site WordPress.com HTTPS adapter."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import ssl
from typing import Any
from urllib.parse import parse_qsl

import pytest

import raos.adapters.wordpresscom_review_draft_https as https_module
from raos.adapters.wordpresscom_review_draft_https import (
    OfficialWordPressComReviewDraftAdapter,
    SystemWordPressComHttpsConnectionFactory,
    WORDPRESSCOM_ACCESS_TOKEN_ALIAS,
    WordPressComBearerToken,
)
from raos.adapters.wordpresscom_review_draft_journal import (
    DurableWordPressComReviewDraftAdapter,
)
from raos.application.editorial.wordpresscom_review_draft import (
    build_bound_review_draft,
)
from raos.domain.editorial.wordpresscom_review_draft import (
    ReviewDraftDisposition,
    WORDPRESSCOM_REVIEW_DRAFT_API_PATH,
    WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY,
    WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS,
    WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA,
    WORDPRESSCOM_REVIEW_DRAFT_STATUS,
    WORDPRESSCOM_REVIEW_DRAFT_TARGET,
    WordPressComReviewDraft,
    WordPressComReviewDraftFailure,
    review_draft_operation_binding_sha256,
)
from raos.ports.wordpresscom_review_draft import WordPressComReviewDraftPort
from raos.ports.wordpresscom_review_draft_journal import (
    WordPressComReviewDraftAttemptPort,
)


ROOT = Path(__file__).resolve().parents[2]


def _candidate() -> WordPressComReviewDraft:
    return build_bound_review_draft(
        article_bytes=(
            ROOT / "changes/st-1703/first-article-review-draft.v1.md"
        ).read_bytes(),
        source_packet_bytes=(
            ROOT / "changes/st-1703/source-packet-candidate.first-article.v1.yaml"
        ).read_bytes(),
        base_handoff_bytes=(
            ROOT
            / "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2.yaml"
        ).read_bytes(),
        amendment_handoff_bytes=(
            ROOT
            / "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2A_NUMERIC_PROXY_ACTIVATION.yaml"
        ).read_bytes(),
        activation_handoff_bytes=(
            ROOT
            / "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2B_V1_1_ACTIVATION.yaml"
        ).read_bytes(),
    )


def _success_payload(candidate: WordPressComReviewDraft) -> dict[str, object]:
    return {
        "ID": 1703,
        "URL": "https://kurashierabinote.wordpress.com/?p=1703",
        "publicize_URLs": [],
        "site_ID": "256699520",
        "status": "draft",
        "type": "post",
    }


def _body(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


class FakeTokenReader:
    def __init__(self, *, fail: bool = False, wrong_type: bool = False) -> None:
        self.aliases: list[str] = []
        self.fail = fail
        self.wrong_type = wrong_type
        self.value = bytes(range(33, 65))

    def read(self, alias: str) -> WordPressComBearerToken:
        self.aliases.append(alias)
        if self.fail:
            raise OSError("secret-reader-detail")
        if self.wrong_type:
            return object()  # type: ignore[return-value]
        return WordPressComBearerToken(self.value)


class FakeResponse:
    def __init__(
        self,
        *,
        body: bytes,
        status: int = 200,
        content_type: str = "application/json; charset=UTF-8",
        fail_read: bool = False,
        maximum_chunk_size: int | None = None,
    ) -> None:
        self.status = status
        self.body = body
        self.content_type = content_type
        self.fail_read = fail_read
        self.maximum_chunk_size = maximum_chunk_size
        self.offset = 0
        self.reads = 0

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self.content_type if name == "Content-Type" else default

    def read(self, amount: int | None = None) -> bytes:
        self.reads += 1
        if self.fail_read:
            raise TimeoutError("read-detail")
        size = len(self.body) if amount is None else amount
        if self.maximum_chunk_size is not None:
            size = min(size, self.maximum_chunk_size)
        chunk = self.body[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


class FakeConnection:
    def __init__(
        self, response: FakeResponse, *, fail_stage: str | None = None
    ) -> None:
        self.response = response
        self.fail_stage = fail_stage
        self.connects = 0
        self.read_timeouts: list[int] = []
        self.requests: list[tuple[str, str, bytes, dict[str, str]]] = []
        self.response_calls = 0
        self.closes = 0

    def connect(self) -> None:
        self.connects += 1
        if self.fail_stage == "connect":
            raise OSError("connect-detail")

    def set_read_timeout(self, seconds: int) -> None:
        self.read_timeouts.append(seconds)
        if self.fail_stage == "timeout":
            raise OSError("timeout-detail")

    def request(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: dict[str, str],
    ) -> None:
        self.requests.append((method, path, body, dict(headers)))
        if self.fail_stage == "request":
            raise TimeoutError("request-detail")

    def getresponse(self) -> FakeResponse:
        self.response_calls += 1
        if self.fail_stage == "response":
            raise TimeoutError("response-detail")
        return self.response

    def close(self) -> None:
        self.closes += 1


class FakeFactory:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.opens: list[tuple[str, int, int, ssl.SSLContext]] = []

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> FakeConnection:
        self.opens.append((host, port, connect_timeout_seconds, tls_context))
        return self.connection


class SequenceFactory:
    def __init__(self, connections: list[FakeConnection]) -> None:
        self.connections = connections
        self.opens: list[tuple[str, int, int, ssl.SSLContext]] = []

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> FakeConnection:
        self.opens.append((host, port, connect_timeout_seconds, tls_context))
        return self.connections[len(self.opens) - 1]


def _adapter(
    candidate: WordPressComReviewDraft,
    *,
    payload: object | None = None,
    status: int = 200,
    content_type: str = "application/json; charset=UTF-8",
    fail_stage: str | None = None,
    fail_read: bool = False,
    token_reader: FakeTokenReader | None = None,
) -> tuple[OfficialWordPressComReviewDraftAdapter, FakeTokenReader, FakeFactory]:
    response = FakeResponse(
        body=_body(_success_payload(candidate) if payload is None else payload),
        status=status,
        content_type=content_type,
        fail_read=fail_read,
    )
    connection = FakeConnection(response, fail_stage=fail_stage)
    factory = FakeFactory(connection)
    reader = token_reader or FakeTokenReader()
    return (
        OfficialWordPressComReviewDraftAdapter(
            token_reader=reader, connection_factory=factory
        ),
        reader,
        factory,
    )


def test_exact_numeric_proxy_post_system_tls_and_sanitized_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate()
    monkeypatch.setenv("HTTPS_PROXY", "http://untrusted.invalid:8080")
    monkeypatch.setenv("ALL_PROXY", "http://untrusted.invalid:8081")
    adapter, reader, factory = _adapter(candidate)

    receipt = adapter.attempt_create_review_draft(candidate)
    connection = factory.connection

    assert reader.aliases == [WORDPRESSCOM_ACCESS_TOKEN_ALIAS]
    assert len(factory.opens) == 1
    host, port, connect_timeout, context = factory.opens[0]
    assert (host, port, connect_timeout) == ("public-api.wordpress.com", 443, 5)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert connection.connects == 1
    assert connection.read_timeouts == [20]
    assert connection.response_calls == 1
    assert connection.closes == 1
    assert len(connection.requests) == 1
    method, path, request_body, headers = connection.requests[0]
    assert (method, path) == (
        "POST",
        "/rest/v1.1/sites/256699520/posts/new",
    )
    assert request_body == (
        b"title=%5B%E3%83%AC%E3%83%93%E3%83%A5%E3%83%BC%E7%94%A8%E3%83%BB"
        b"%E6%9C%AA%E6%89%BF%E8%AA%8D%5D+%E6%A9%9F%E5%86%85%E6%8C%81%E3%81%A1"
        b"%E8%BE%BC%E3%81%BF%E5%AF%BE%E5%BF%9C%E3%82%B9%E3%83%BC%E3%83%84%E3%82%B1"
        b"%E3%83%BC%E3%82%B93%E3%83%A2%E3%83%87%E3%83%AB%E3%82%92%E6%9D%A1%E4%BB%B6"
        b"%E5%88%A5%E6%AF%94%E8%BC%83%EF%BD%9C%E8%BB%BD%E3%81%95%E3%83%BB%E5%AE%B9"
        b"%E9%87%8F%E3%83%BB%E9%96%8B%E3%81%8D%E6%96%B9%E3%81%A7%E9%81%B8%E3%81%B6"
        b"&content="
        + https_module.urlencode(
            (("content", candidate.rendered_content),),
            doseq=False,
            safe="",
            encoding="utf-8",
            errors="strict",
            quote_via=https_module.quote_plus,
        )
        .encode("ascii")
        .removeprefix(b"content=")
        + b"&status=draft&publicize=false"
    )
    assert parse_qsl(
        request_body.decode("ascii"),
        keep_blank_values=True,
        strict_parsing=True,
        encoding="utf-8",
        errors="strict",
    ) == [
        ("title", candidate.title),
        ("content", candidate.rendered_content),
        ("status", "draft"),
        ("publicize", "false"),
    ]
    assert len(request_body) == 26_168
    assert hashlib.sha256(request_body).hexdigest() == (
        "a111b07548326f8ea61888ea6cba0b402dca8bf94f56240c97118bf3701a0ef9"
    )
    assert set(headers) == {"Accept", "Authorization", "Content-Type"}
    assert headers["Accept"] == "application/json"
    assert headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert headers["Authorization"] == "Bearer " + reader.value.decode("ascii")
    assert dataclasses.asdict(receipt) == {
        "authority": WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY,
        "content_sha256": candidate.content_sha256,
        "disposition": ReviewDraftDisposition.CREATED,
        "draft_id": 1703,
        "network_status": WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS,
        "operation_binding_sha256": candidate.operation_binding_sha256,
        "production_eligible": False,
        "publication_authorized": False,
        "response_body_sha256": hashlib.sha256(
            _body(_success_payload(candidate))
        ).hexdigest(),
        "schema": WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA,
        "status": WORDPRESSCOM_REVIEW_DRAFT_STATUS,
        "target_origin": WORDPRESSCOM_REVIEW_DRAFT_TARGET,
    }


def test_raw_https_is_only_the_outward_attempt_port() -> None:
    candidate = _candidate()
    adapter, _, _ = _adapter(candidate)

    assert isinstance(adapter, WordPressComReviewDraftAttemptPort)
    assert not isinstance(adapter, WordPressComReviewDraftPort)
    assert not hasattr(adapter, "create_review_draft")


@pytest.mark.parametrize(
    ("host", "port"),
    [
        ("kurashierabinote.wordpress.com", 443),
        ("256699520.wordpress.com", 443),
        ("public-api.wordpress.com", 80),
        ("other.wordpress.com", 443),
    ],
)
def test_system_factory_rejects_every_nonexact_numeric_proxy_authority(
    monkeypatch: pytest.MonkeyPatch, host: str, port: int
) -> None:
    monkeypatch.setattr(
        https_module.http.client,
        "HTTPSConnection",
        lambda *args, **kwargs: pytest.fail("invalid authority reached TLS setup"),
    )

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        SystemWordPressComHttpsConnectionFactory().open(
            host=host,
            port=port,
            connect_timeout_seconds=5,
            tls_context=ssl.create_default_context(),
        )

    assert str(caught.value) == "REVIEW_DRAFT_HTTPS_SETUP_INVALID"


@pytest.mark.parametrize(
    "payload",
    [
        {"found": 0, "meta": {}, "posts": []},
        {
            "found": 1,
            "meta": {"next_page": None},
            "posts": [{"ID": 1703}],
        },
    ],
)
def test_authenticated_v1_1_preflight_uses_exact_edit_context_route(
    payload: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://untrusted.invalid:8080")
    monkeypatch.setenv("ALL_PROXY", "http://untrusted.invalid:8081")
    response = FakeResponse(body=_body(payload), status=200)
    connection = FakeConnection(response)
    factory = FakeFactory(connection)
    reader = FakeTokenReader()
    adapter = OfficialWordPressComReviewDraftAdapter(
        token_reader=reader,
        connection_factory=factory,
    )

    adapter.require_create_capability(_candidate())

    assert reader.aliases == [WORDPRESSCOM_ACCESS_TOKEN_ALIAS]
    assert len(factory.opens) == 1
    host, port, connect_timeout, context = factory.opens[0]
    assert (host, port, connect_timeout) == ("public-api.wordpress.com", 443, 5)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert connection.connects == 1
    assert connection.read_timeouts == [20]
    assert connection.response_calls == 1
    assert connection.closes == 1
    assert connection.requests == [
        (
            "GET",
            "/rest/v1.1/sites/256699520/posts?context=edit&number=1&fields=ID",
            b"",
            {
                "Accept": "application/json",
                "Authorization": "Bearer " + reader.value.decode("ascii"),
            },
        )
    ]


@pytest.mark.parametrize(
    ("body", "status", "content_type"),
    [
        (_body({}), 200, "application/json"),
        (
            _body({"found": 0, "meta": {}, "posts": [], "extra": 1}),
            200,
            "application/json",
        ),
        (_body({"found": -1, "meta": {}, "posts": []}), 200, "application/json"),
        (_body({"found": True, "meta": {}, "posts": []}), 200, "application/json"),
        (_body({"found": 0.0, "meta": {}, "posts": []}), 200, "application/json"),
        (_body({"found": 0, "meta": [], "posts": []}), 200, "application/json"),
        (_body({"found": 0, "meta": {}, "posts": {}}), 200, "application/json"),
        (
            _body({"found": 2, "meta": {}, "posts": [{"ID": 1}, {"ID": 2}]}),
            200,
            "application/json",
        ),
        (_body({"found": 1, "meta": {}, "posts": [{}]}), 200, "application/json"),
        (
            _body({"found": 1, "meta": {}, "posts": [{"id": 1}]}),
            200,
            "application/json",
        ),
        (
            _body({"found": 1, "meta": {}, "posts": [{"ID": 0}]}),
            200,
            "application/json",
        ),
        (
            _body({"found": 1, "meta": {}, "posts": [{"ID": True}]}),
            200,
            "application/json",
        ),
        (
            _body({"found": 1, "meta": {}, "posts": [{"ID": 1, "title": "forbidden"}]}),
            200,
            "application/json",
        ),
        (b'{"found":0,"found":1,"meta":{},"posts":[]}', 200, "application/json"),
        (b'{"found":NaN,"meta":{},"posts":[]}', 200, "application/json"),
        (b"not-json", 200, "application/json"),
        (_body({"found": 0, "meta": {}, "posts": []}), 401, "application/json"),
        (_body({"found": 0, "meta": {}, "posts": []}), 403, "application/json"),
        (_body({"found": 0, "meta": {}, "posts": []}), 301, "application/json"),
        (_body({"found": 0, "meta": {}, "posts": []}), 200, "text/html"),
        (_body({"found": 0, "meta": {}, "posts": []}), 200, "application/json\r\n"),
    ],
)
def test_v1_1_preflight_refuses_unavailable_or_untrusted_response(
    body: bytes, status: int, content_type: str
) -> None:
    response = FakeResponse(body=body, status=status, content_type=content_type)
    connection = FakeConnection(response)
    factory = FakeFactory(connection)
    adapter = OfficialWordPressComReviewDraftAdapter(
        token_reader=FakeTokenReader(),
        connection_factory=factory,
    )

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.require_create_capability(_candidate())

    assert str(caught.value) == "REVIEW_DRAFT_HTTPS_SETUP_INVALID"
    assert len(connection.requests) == 1
    assert connection.requests[0][0:2] == (
        "GET",
        "/rest/v1.1/sites/256699520/posts?context=edit&number=1&fields=ID",
    )
    assert all(request[0] != "POST" for request in connection.requests)


def test_preflight_bounded_reader_proves_eof_after_short_valid_prefix() -> None:
    valid = _body({"found": 0, "meta": {}, "posts": []})
    response = FakeResponse(
        body=valid + b" trailing-untrusted-bytes",
        status=200,
        maximum_chunk_size=len(valid),
    )
    connection = FakeConnection(response)
    adapter = OfficialWordPressComReviewDraftAdapter(
        token_reader=FakeTokenReader(),
        connection_factory=FakeFactory(connection),
    )

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.require_create_capability(_candidate())

    assert str(caught.value) == "REVIEW_DRAFT_HTTPS_SETUP_INVALID"
    assert response.reads >= 2
    assert len(connection.requests) == 1


def test_preflight_depth_and_response_byte_limits_are_closed() -> None:
    deep: object = "leaf"
    for _ in range(70):
        deep = {"next": deep}
    bodies = [
        _body({"found": 0, "meta": {"deep": deep}, "posts": []}),
        b"x" * 65_537,
    ]
    for body in bodies:
        connection = FakeConnection(FakeResponse(body=body, status=200))
        adapter = OfficialWordPressComReviewDraftAdapter(
            token_reader=FakeTokenReader(),
            connection_factory=FakeFactory(connection),
        )
        with pytest.raises(WordPressComReviewDraftFailure) as caught:
            adapter.require_create_capability(_candidate())
        assert str(caught.value) == "REVIEW_DRAFT_HTTPS_SETUP_INVALID"
        assert len(connection.requests) == 1


@pytest.mark.parametrize(
    ("fail_stage", "expected_code", "expected_posts"),
    [
        ("connect", "REVIEW_DRAFT_HTTPS_SETUP_INVALID", 0),
        ("timeout", "REVIEW_DRAFT_HTTPS_SETUP_INVALID", 0),
        ("request", "REVIEW_DRAFT_CREATE_AMBIGUOUS", 1),
        ("response", "REVIEW_DRAFT_CREATE_AMBIGUOUS", 1),
    ],
)
def test_transport_uncertainty_is_closed_and_never_retried(
    fail_stage: str, expected_code: str, expected_posts: int
) -> None:
    candidate = _candidate()
    adapter, reader, factory = _adapter(candidate, fail_stage=fail_stage)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.attempt_create_review_draft(candidate)

    assert str(caught.value) == expected_code
    assert len(factory.opens) == 1
    assert factory.connection.connects == 1
    assert len(factory.connection.requests) == expected_posts
    assert factory.connection.response_calls <= 1
    assert factory.connection.closes == 1
    assert fail_stage + "-detail" not in repr(caught.value)
    assert reader.value.decode("ascii") not in repr(caught.value)


def test_read_timeout_is_closed_and_never_retried() -> None:
    candidate = _candidate()
    adapter, _, factory = _adapter(candidate, fail_read=True)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.attempt_create_review_draft(candidate)

    assert str(caught.value) == "REVIEW_DRAFT_CREATE_AMBIGUOUS"
    assert len(factory.opens) == len(factory.connection.requests) == 1
    assert factory.connection.closes == 1


@pytest.mark.parametrize(
    ("status", "content_type"),
    [
        (201, "application/json"),
        (302, "application/json"),
        (307, "application/json"),
        (200, "text/html"),
        (200, "application/problem+json"),
        (200, "application/json\r\n"),
    ],
)
def test_status_redirect_and_media_type_refusals_do_not_fallback_or_retry(
    status: int, content_type: str
) -> None:
    candidate = _candidate()
    adapter, _, factory = _adapter(candidate, status=status, content_type=content_type)

    with pytest.raises(WordPressComReviewDraftFailure):
        adapter.attempt_create_review_draft(candidate)

    assert len(factory.opens) == len(factory.connection.requests) == 1
    assert factory.connection.requests[0][1] == WORDPRESSCOM_REVIEW_DRAFT_API_PATH


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("ID"),
        lambda value: value.pop("site_ID"),
        lambda value: value.pop("status"),
        lambda value: value.pop("type"),
        lambda value: value.pop("URL"),
        lambda value: value.update(ID=0),
        lambda value: value.update(ID=True),
        lambda value: value.update(site_ID=256699519),
        lambda value: value.update(site_ID=True),
        lambda value: value.update(status="publish"),
        lambda value: value.update(type="page"),
        lambda value: value.update(
            URL="https://public-api.wordpress.com/rest/v1.1/posts/1703"
        ),
        lambda value: value.update(URL="http://kurashierabinote.wordpress.com/?p=1703"),
        lambda value: value.update(
            URL="https://Kurashierabinote.wordpress.com/?p=1703"
        ),
        lambda value: value.update(
            URL="https://kurashierabinote.wordpress.com:443/?p=1703"
        ),
        lambda value: value.update(
            URL="https://kurashierabinote.wordpress.com/\r?p=1703"
        ),
        lambda value: value.update(
            URL="https://kurashierabinote.wordpress.com/\n?p=1703"
        ),
        lambda value: value.update(
            URL="https://kurashierabinote.wordpress.com/\t?p=1703"
        ),
        lambda value: value.update(URL="https://kurashierabinote.wordpress.com/記事"),
        lambda value: value.update(
            URL="https://kurashierabinote.wordpress.com/?p=1703#"
        ),
        lambda value: value.update(publicize_URLs=["https://example.invalid"]),
        lambda value: value.update(publicize_URLs=None),
        lambda value: value.update(publicize_URLs=False),
        lambda value: value.update(publicize_URLs=0),
        lambda value: value.update(publicize_URLs=""),
        lambda value: value.update(publicize_URLs={}),
    ],
)
def test_semantic_response_mismatch_is_ambiguous_and_single_attempt(
    mutation: Any,
) -> None:
    candidate = _candidate()
    payload = _success_payload(candidate)
    mutation(payload)
    adapter, _, factory = _adapter(candidate, payload=payload)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.attempt_create_review_draft(candidate)

    assert str(caught.value) == "REVIEW_DRAFT_CREATE_AMBIGUOUS"
    assert len(factory.opens) == len(factory.connection.requests) == 1


@pytest.mark.parametrize("include_publicize", [False, True])
def test_v1_1_response_accepts_only_absent_or_empty_publicize_urls(
    include_publicize: bool,
) -> None:
    candidate = _candidate()
    payload = _success_payload(candidate) | {"benign_provider_member": {"x": 1}}
    if not include_publicize:
        payload.pop("publicize_URLs")
    adapter, _, _ = _adapter(candidate, payload=payload)

    receipt = adapter.attempt_create_review_draft(candidate)

    assert receipt.draft_id == 1703


@pytest.mark.parametrize("site_id", [256699520, "256699520"])
def test_v1_1_response_accepts_exact_site_id_wire_representations(
    site_id: object,
) -> None:
    candidate = _candidate()
    payload = _success_payload(candidate) | {"site_ID": site_id}
    adapter, _, _ = _adapter(candidate, payload=payload)

    receipt = adapter.attempt_create_review_draft(candidate)

    assert receipt.draft_id == 1703


@pytest.mark.parametrize(
    "site_id",
    [
        256699519,
        True,
        256699520.0,
        None,
        [],
        {},
        "",
        "256699519",
        "0256699520",
        "+256699520",
        "-256699520",
        " 256699520",
        "256699520 ",
        "256699520\n",
        "256699520.0",
        "2.56699520e8",
        "２５６６９９５２０",
    ],
)
def test_v1_1_response_rejects_nonexact_site_id_wire_representations(
    site_id: object,
) -> None:
    candidate = _candidate()
    payload = _success_payload(candidate) | {"site_ID": site_id}
    adapter, _, factory = _adapter(candidate, payload=payload)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.attempt_create_review_draft(candidate)

    assert str(caught.value) == "REVIEW_DRAFT_CREATE_AMBIGUOUS"
    assert len(factory.opens) == len(factory.connection.requests) == 1


@pytest.mark.parametrize("key", ["site_id", "Site_ID", "SITE_ID"])
def test_v1_1_response_rejects_site_id_key_case_variants(key: str) -> None:
    candidate = _candidate()
    payload = _success_payload(candidate)
    site_id = payload.pop("site_ID")
    payload[key] = site_id
    adapter, _, factory = _adapter(candidate, payload=payload)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.attempt_create_review_draft(candidate)

    assert str(caught.value) == "REVIEW_DRAFT_CREATE_AMBIGUOUS"
    assert len(factory.opens) == len(factory.connection.requests) == 1


@pytest.mark.parametrize(
    "raw_body",
    [
        b"{}",
        b'{"ID":1703,"ID":1704}',
        b'{"ID":NaN}',
        b"not-json",
        b"\xff",
    ],
)
def test_malformed_duplicate_nonfinite_response_is_closed(raw_body: bytes) -> None:
    candidate = _candidate()
    response = FakeResponse(body=raw_body)
    factory = FakeFactory(FakeConnection(response))
    adapter = OfficialWordPressComReviewDraftAdapter(
        token_reader=FakeTokenReader(), connection_factory=factory
    )

    with pytest.raises(WordPressComReviewDraftFailure):
        adapter.attempt_create_review_draft(candidate)

    assert len(factory.opens) == len(factory.connection.requests) == 1


def test_depth_node_and_response_byte_limits_are_closed() -> None:
    candidate = _candidate()
    deep: object = "leaf"
    for _ in range(70):
        deep = [deep]
    payloads = [
        _success_payload(candidate) | {"extra": deep},
        _success_payload(candidate) | {"extra": [None] * 100_001},
    ]
    for payload in payloads:
        adapter, _, factory = _adapter(candidate, payload=payload)
        with pytest.raises(WordPressComReviewDraftFailure):
            adapter.attempt_create_review_draft(candidate)
        assert len(factory.connection.requests) == 1

    response = FakeResponse(body=b"x" * 4_000_001)
    factory = FakeFactory(FakeConnection(response))
    adapter = OfficialWordPressComReviewDraftAdapter(
        token_reader=FakeTokenReader(), connection_factory=factory
    )
    with pytest.raises(WordPressComReviewDraftFailure):
        adapter.attempt_create_review_draft(candidate)
    assert len(factory.connection.requests) == 1


@pytest.mark.parametrize(
    "reader", [FakeTokenReader(fail=True), FakeTokenReader(wrong_type=True)]
)
def test_secret_reader_failure_is_sanitized_and_opens_no_connection(
    reader: FakeTokenReader,
) -> None:
    candidate = _candidate()
    adapter, _, factory = _adapter(candidate, token_reader=reader)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.attempt_create_review_draft(candidate)

    assert str(caught.value) == "REVIEW_DRAFT_HTTPS_SETUP_INVALID"
    assert factory.opens == []
    assert "secret-reader-detail" not in repr(caught.value)


def test_invalid_local_input_reads_no_secret_and_opens_no_connection() -> None:
    candidate = _candidate()
    adapter, reader, factory = _adapter(candidate)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        adapter.attempt_create_review_draft(object())  # type: ignore[arg-type]

    assert str(caught.value) == "REVIEW_DRAFT_CANDIDATE_INVALID"
    assert reader.aliases == []
    assert factory.opens == []


def test_arbitrary_self_consistent_candidate_cannot_reach_secret_or_network() -> None:
    candidate = _candidate()
    adapter, reader, factory = _adapter(candidate)
    arbitrary_content = "<p>arbitrary but self-consistent</p>"
    arbitrary_sha256 = hashlib.sha256(arbitrary_content.encode()).hexdigest()

    with pytest.raises(WordPressComReviewDraftFailure):
        review_draft_operation_binding_sha256(
            title=candidate.title,
            content_sha256=arbitrary_sha256,
        )
    values = {
        field.name: getattr(candidate, field.name)
        for field in dataclasses.fields(candidate)
    }
    with pytest.raises(WordPressComReviewDraftFailure):
        WordPressComReviewDraft(
            **(
                values
                | {
                    "rendered_content": arbitrary_content,
                    "content_sha256": arbitrary_sha256,
                }
            )
        )

    assert reader.aliases == []
    assert factory.opens == []
    assert not hasattr(adapter, "create_review_draft")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("api_path", "/wp-json/wp/v2/posts"),
        ("api_path", "/wp/v2/sites/256699520/posts"),
        (
            "handoff_sha256",
            "5e69433222435305f8a2decef8840de4764565929d483f0e4d8b35fcd6ed7bf6",
        ),
        ("target_origin", "https://public-api.wordpress.com"),
        ("rendered_content", "<p>tampered</p>"),
    ],
)
@pytest.mark.parametrize("operation", ["preflight", "attempt"])
def test_mutated_exact_instance_is_rechecked_before_secret_or_network(
    field: str,
    value: str,
    operation: str,
) -> None:
    candidate = _candidate()
    adapter, reader, factory = _adapter(candidate)
    object.__setattr__(candidate, field, value)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        if operation == "preflight":
            adapter.require_create_capability(candidate)
        else:
            adapter.attempt_create_review_draft(candidate)

    assert str(caught.value) == "REVIEW_DRAFT_CANDIDATE_INVALID"
    assert reader.aliases == []
    assert factory.opens == []


@pytest.mark.parametrize(
    "variable_name", ["SSL_CERT_FILE", "SSL_CERT_DIR", "SSLKEYLOGFILE"]
)
@pytest.mark.parametrize("operation", ["preflight", "attempt"])
def test_tls_environment_overrides_stop_before_secret_or_network(
    monkeypatch: pytest.MonkeyPatch,
    variable_name: str,
    operation: str,
) -> None:
    candidate = _candidate()
    adapter, reader, factory = _adapter(candidate)
    monkeypatch.setenv(variable_name, "/untrusted/override")

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        if operation == "preflight":
            adapter.require_create_capability(candidate)
        else:
            adapter.attempt_create_review_draft(candidate)

    assert str(caught.value) == "REVIEW_DRAFT_HTTPS_SETUP_INVALID"
    assert reader.aliases == []
    assert factory.opens == []


def test_ambiguous_post_through_journal_is_never_automatically_sent_again(
    tmp_path: Path,
) -> None:
    candidate = _candidate()
    preflight_sentinel = 987_654_321
    preflight = FakeConnection(
        FakeResponse(
            body=_body(
                {
                    "found": preflight_sentinel,
                    "meta": {"sentinel": preflight_sentinel},
                    "posts": [{"ID": preflight_sentinel}],
                }
            ),
            status=200,
        )
    )
    attempted_post = FakeConnection(
        FakeResponse(body=_body(_success_payload(candidate)), status=302)
    )
    factory = SequenceFactory([preflight, attempted_post])
    adapter = OfficialWordPressComReviewDraftAdapter(
        token_reader=FakeTokenReader(), connection_factory=factory
    )
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    durable = DurableWordPressComReviewDraftAdapter(private_root=root, creator=adapter)

    with pytest.raises(WordPressComReviewDraftFailure) as first:
        durable.create_review_draft(candidate)
    with pytest.raises(WordPressComReviewDraftFailure) as second:
        durable.create_review_draft(candidate)

    assert str(first.value) == "REVIEW_DRAFT_CREATE_AMBIGUOUS"
    assert str(second.value) == "REVIEW_DRAFT_JOURNAL_AMBIGUOUS"
    assert len(factory.opens) == 2
    assert [
        request[0]
        for connection in factory.connections
        for request in connection.requests
    ] == [
        "GET",
        "POST",
    ]
    state_text = (root / "review-draft-state.v1.json").read_text(encoding="ascii")
    state = json.loads(state_text)
    assert state["state"] == "INTENT"
    assert str(preflight_sentinel) not in state_text


def test_token_and_adapter_representations_are_redacted() -> None:
    candidate = _candidate()
    reader = FakeTokenReader()
    adapter, _, _ = _adapter(candidate, token_reader=reader)
    token = WordPressComBearerToken(reader.value)

    rendered = " ".join((repr(token), str(token), repr(adapter)))
    assert reader.value.decode("ascii") not in rendered
    assert candidate.rendered_content not in rendered
    proxy = os.environ.get("HTTPS_PROXY")
    assert not proxy or proxy not in rendered
