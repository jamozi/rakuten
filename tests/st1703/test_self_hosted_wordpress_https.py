"""One-attempt fixed-origin HTTPS tests for self-hosted WordPress."""

from __future__ import annotations

import json
from pathlib import Path
import signal
import ssl
import time

import pytest

from raos.adapters.self_hosted_wordpress_credentials import (
    OwnerPrivateSelfHostedWordPressCredentialStore,
    SelfHostedWordPressCredentials,
)
from raos.adapters.self_hosted_wordpress_https import (
    CONNECT_TIMEOUT_SECONDS,
    MAX_RESPONSE_BYTES,
    OfficialSelfHostedWordPressDraftAdapter,
    SELF_HOSTED_WORDPRESS_HOST,
    SELF_HOSTED_WORDPRESS_PORT,
)
import raos.adapters.self_hosted_wordpress_https as https_module
from raos.adapters.self_hosted_wordpress_journal import (
    DurableSelfHostedWordPressDraftAdapter,
)
from raos.application.editorial.self_hosted_minimum_start import (
    FIRST_ARTICLE_SLUG,
    FIRST_ARTICLE_THEME_SHORTCODE,
    load_first_article_candidate,
)
from raos.domain.editorial.self_hosted_wordpress import (
    SelfHostedWordPressDisposition,
    SelfHostedWordPressDraft,
    SelfHostedWordPressFailure,
    SelfHostedWordPressFailureCode,
    SelfHostedWordPressOperation,
)


_UNTRUSTED_ENVIRONMENT = {
    "ALL_PROXY",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "SSLKEYLOGFILE",
    "all_proxy",
    "https_proxy",
    "http_proxy",
    "no_proxy",
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SYNTHETIC_SLUG = "synthetic-draft"
_SYNTHETIC_RESPONSE_BODY = b'{"id":1703,"slug":"synthetic-draft","status":"draft"}'


def _candidate(
    operation: SelfHostedWordPressOperation = SelfHostedWordPressOperation.CREATE_DRAFT,
    draft_id: int | None = None,
) -> SelfHostedWordPressDraft:
    return SelfHostedWordPressDraft.bind(
        operation=operation,
        title="Synthetic draft",
        slug=_SYNTHETIC_SLUG,
        content_html="<p>Bound content.</p>",
        existing_draft_id=draft_id,
    )


def _install(tmp_path: Path) -> SelfHostedWordPressCredentials:
    credentials = SelfHostedWordPressCredentials(
        username="owner-editor",
        _application_password="synthetic-" + "credential",
    )
    OwnerPrivateSelfHostedWordPressCredentialStore(tmp_path).install(credentials)
    return credentials


class FakeResponse:
    def __init__(
        self,
        *,
        status: int = 201,
        body: bytes = _SYNTHETIC_RESPONSE_BODY,
        content_type: str = "application/json; charset=UTF-8",
        content_length: str | None = None,
        content_encoding: str | None = None,
        transfer_encoding: str | None = None,
    ) -> None:
        self.status = status
        self.body = body
        self.content_type = content_type
        self.content_length = content_length
        self.content_encoding = content_encoding
        self.transfer_encoding = transfer_encoding
        self.read_amounts: list[int] = []

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return {
            "Content-Type": self.content_type,
            "Content-Length": self.content_length,
            "Content-Encoding": self.content_encoding,
            "Transfer-Encoding": self.transfer_encoding,
        }.get(name, default)

    def read(self, amount: int = -1) -> bytes:
        self.read_amounts.append(amount)
        return self.body


class FakeConnection:
    def __init__(
        self,
        response: FakeResponse,
        *,
        connect_error: BaseException | None = None,
        request_error: BaseException | None = None,
    ) -> None:
        self.response = response
        self.connect_error = connect_error
        self.request_error = request_error
        self.connect_count = 0
        self.request_count = 0
        self.closed = 0
        self.read_timeout: int | None = None
        self.observed_request: tuple[str, str, bytes, dict[str, str]] | None = None

    def connect(self) -> None:
        self.connect_count += 1
        if self.connect_error is not None:
            raise self.connect_error

    def set_read_timeout(self, seconds: int) -> None:
        self.read_timeout = seconds

    def request(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> None:
        self.request_count += 1
        self.observed_request = (method, path, body, headers)
        if self.request_error is not None:
            raise self.request_error

    def getresponse(self) -> FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed += 1


class FakeFactory:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.open_count = 0

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> FakeConnection:
        self.open_count += 1
        assert host == SELF_HOSTED_WORDPRESS_HOST
        assert port == SELF_HOSTED_WORDPRESS_PORT
        assert connect_timeout_seconds == CONNECT_TIMEOUT_SECONDS
        assert tls_context.verify_mode == ssl.CERT_REQUIRED
        assert tls_context.check_hostname
        return self.connection


def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _UNTRUSTED_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


def test_create_uses_exact_path_basic_auth_draft_body_and_one_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clean_environment(monkeypatch)
    credentials = _install(tmp_path)
    response = FakeResponse(content_length=str(len(_SYNTHETIC_RESPONSE_BODY)))
    connection = FakeConnection(response)
    factory = FakeFactory(connection)

    receipt = OfficialSelfHostedWordPressDraftAdapter(
        tmp_path, connection_factory=factory
    ).attempt(_candidate())

    assert receipt.draft_id == 1703
    assert receipt.disposition is SelfHostedWordPressDisposition.CREATED
    assert (
        factory.open_count == connection.connect_count == connection.request_count == 1
    )
    assert connection.closed == 1
    assert connection.observed_request is not None
    method, path, body, headers = connection.observed_request
    assert method == "POST"
    assert path == "/wp-json/wp/v2/posts"
    assert json.loads(body) == {
        "content": "<p>Bound content.</p>",
        "slug": _SYNTHETIC_SLUG,
        "status": "draft",
        "title": "Synthetic draft",
    }
    assert headers["Authorization"] == credentials.authorization_header()
    assert headers["Host"] == "kurashinoshirube.com"
    assert response.read_amounts == [MAX_RESPONSE_BYTES + 1]


def test_first_article_request_body_equals_reviewed_generated_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clean_environment(monkeypatch)
    _install(tmp_path)
    candidate = load_first_article_candidate(
        REPOSITORY_ROOT,
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
    )
    response_body = json.dumps(
        {"id": 1703, "slug": FIRST_ARTICLE_SLUG, "status": "draft"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    connection = FakeConnection(
        FakeResponse(body=response_body, content_length=str(len(response_body)))
    )

    OfficialSelfHostedWordPressDraftAdapter(
        tmp_path, connection_factory=FakeFactory(connection)
    ).attempt(candidate)

    assert connection.observed_request is not None
    _method, _path, body, _headers = connection.observed_request
    payload = json.loads(body)
    assert payload == {
        "content": candidate.content_html,
        "slug": FIRST_ARTICLE_SLUG,
        "status": "draft",
        "title": candidate.title,
    }
    assert payload["content"].count(FIRST_ARTICLE_THEME_SHORTCODE) == 1
    assert payload["content"].startswith(f"{FIRST_ARTICLE_THEME_SHORTCODE}\n")
    assert "<img" not in payload["content"]
    assert "featured_media" not in payload


@pytest.mark.parametrize(
    "response_body",
    [
        b'{"id":1703,"status":"draft"}',
        b'{"id":1703,"slug":"different-post","status":"draft"}',
        b'{"id":1703,"slug":"synthetic-draft","slug":"different-post","status":"draft"}',
    ],
    ids=("missing-slug", "wrong-slug", "duplicate-slug"),
)
def test_create_rejects_missing_wrong_or_duplicate_response_slug_after_one_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, response_body: bytes
) -> None:
    _clean_environment(monkeypatch)
    _install(tmp_path)
    connection = FakeConnection(FakeResponse(body=response_body))

    with pytest.raises(SelfHostedWordPressFailure) as failure:
        OfficialSelfHostedWordPressDraftAdapter(
            tmp_path, connection_factory=FakeFactory(connection)
        ).attempt(_candidate())
    assert failure.value.code is SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS
    assert connection.request_count == 1


def test_response_slug_mismatch_leaves_durable_intent_and_never_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clean_environment(monkeypatch)
    _install(tmp_path)
    response_body = b'{"id":1703,"slug":"different-post","status":"draft"}'
    connection = FakeConnection(FakeResponse(body=response_body))
    durable = DurableSelfHostedWordPressDraftAdapter(
        repository_root=tmp_path,
        attempt_port=OfficialSelfHostedWordPressDraftAdapter(
            tmp_path, connection_factory=FakeFactory(connection)
        ),
    )
    candidate = _candidate()

    with pytest.raises(SelfHostedWordPressFailure) as first:
        durable.apply(candidate)
    assert first.value.code is SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS
    journal = json.loads(
        (
            tmp_path / ".secrets/wordpress-owner-local/state/draft-journal.v1.json"
        ).read_text(encoding="ascii")
    )
    assert journal["pending"]["operation_sha256"] == candidate.operation_sha256
    assert journal["committed"] is None

    with pytest.raises(SelfHostedWordPressFailure) as repeated:
        durable.apply(candidate)
    assert repeated.value.code is SelfHostedWordPressFailureCode.JOURNAL_AMBIGUOUS
    assert connection.request_count == 1


def test_update_is_interface_only_and_rejected_before_credential_or_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clean_environment(monkeypatch)
    connection = FakeConnection(FakeResponse())
    factory = FakeFactory(connection)
    monkeypatch.setattr(
        OwnerPrivateSelfHostedWordPressCredentialStore,
        "read",
        lambda ignored: (_ for _ in ()).throw(
            AssertionError("update read credential values")
        ),
    )
    with pytest.raises(SelfHostedWordPressFailure) as failure:
        OfficialSelfHostedWordPressDraftAdapter(
            tmp_path, connection_factory=factory
        ).attempt(_candidate(SelfHostedWordPressOperation.UPDATE_DRAFT, 9))
    assert failure.value.code is SelfHostedWordPressFailureCode.OPERATION_NOT_ALLOWED
    assert factory.open_count == 0
    assert connection.connect_count == connection.request_count == 0


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(status=302),
        FakeResponse(status=500),
        FakeResponse(content_type="text/html"),
        FakeResponse(body=b"{"),
        FakeResponse(body=b"x" * (MAX_RESPONSE_BYTES + 1)),
        FakeResponse(content_encoding="gzip"),
        FakeResponse(transfer_encoding="gzip"),
        FakeResponse(
            content_length=str(len(_SYNTHETIC_RESPONSE_BODY)),
            transfer_encoding="chunked",
        ),
    ],
)
def test_redirect_status_media_json_oversize_and_encoding_fail_after_one_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, response: FakeResponse
) -> None:
    _clean_environment(monkeypatch)
    _install(tmp_path)
    connection = FakeConnection(response)
    with pytest.raises(SelfHostedWordPressFailure) as failure:
        OfficialSelfHostedWordPressDraftAdapter(
            tmp_path, connection_factory=FakeFactory(connection)
        ).attempt(_candidate())

    assert failure.value.code is SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS
    assert connection.request_count == 1


def test_connect_failure_is_not_sent_but_request_timeout_is_ambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clean_environment(monkeypatch)
    _install(tmp_path)
    connect_failure = FakeConnection(FakeResponse(), connect_error=TimeoutError())
    with pytest.raises(SelfHostedWordPressFailure) as before:
        OfficialSelfHostedWordPressDraftAdapter(
            tmp_path, connection_factory=FakeFactory(connect_failure)
        ).attempt(_candidate())
    assert before.value.code is SelfHostedWordPressFailureCode.TRANSPORT_REFUSED
    assert connect_failure.request_count == 0

    request_failure = FakeConnection(FakeResponse(), request_error=TimeoutError())
    with pytest.raises(SelfHostedWordPressFailure) as after:
        OfficialSelfHostedWordPressDraftAdapter(
            tmp_path, connection_factory=FakeFactory(request_failure)
        ).attempt(_candidate())
    assert after.value.code is SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS
    assert request_failure.request_count == 1


def test_adapter_object_is_one_shot_even_after_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clean_environment(monkeypatch)
    _install(tmp_path)
    connection = FakeConnection(
        FakeResponse(content_length=str(len(_SYNTHETIC_RESPONSE_BODY)))
    )
    adapter = OfficialSelfHostedWordPressDraftAdapter(
        tmp_path, connection_factory=FakeFactory(connection)
    )
    adapter.attempt(_candidate())
    with pytest.raises(SelfHostedWordPressFailure) as repeated:
        adapter.attempt(_candidate())
    assert repeated.value.code is SelfHostedWordPressFailureCode.OPERATION_NOT_ALLOWED
    assert connection.request_count == 1


def test_total_request_deadline_interrupts_slow_exchange(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if signal.getsignal(signal.SIGALRM) not in {signal.SIG_DFL, signal.SIG_IGN}:
        pytest.skip("process already owns SIGALRM")
    monkeypatch.setattr(https_module, "READ_TIMEOUT_SECONDS", 0.01)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        with https_module._request_deadline():
            time.sleep(0.2)
    assert time.monotonic() - started < 0.15


def test_total_connect_deadline_interrupts_resolver_or_tls_stall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clean_environment(monkeypatch)
    _install(tmp_path)
    if signal.getsignal(signal.SIGALRM) not in {signal.SIG_DFL, signal.SIG_IGN}:
        pytest.skip("process already owns SIGALRM")

    connection = FakeConnection(FakeResponse())

    def stalled_connect() -> None:
        connection.connect_count += 1
        time.sleep(0.2)

    connection.connect = stalled_connect  # type: ignore[method-assign]
    monkeypatch.setattr(https_module, "CONNECT_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(SelfHostedWordPressFailure) as failure:
        OfficialSelfHostedWordPressDraftAdapter(
            tmp_path, connection_factory=FakeFactory(connection)
        ).attempt(_candidate())
    assert failure.value.code is SelfHostedWordPressFailureCode.TRANSPORT_REFUSED
    assert connection.request_count == 0


@pytest.mark.parametrize("name", ["HTTPS_PROXY", "http_proxy", "SSL_CERT_FILE"])
def test_proxy_and_tls_overrides_stop_before_credential_read_or_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    monkeypatch.setenv(name, "untrusted")
    factory = FakeFactory(FakeConnection(FakeResponse()))
    monkeypatch.setattr(
        OwnerPrivateSelfHostedWordPressCredentialStore,
        "read",
        lambda ignored: (_ for _ in ()).throw(AssertionError()),
    )

    with pytest.raises(SelfHostedWordPressFailure) as failure:
        OfficialSelfHostedWordPressDraftAdapter(
            tmp_path, connection_factory=factory
        ).attempt(_candidate())
    assert failure.value.code is SelfHostedWordPressFailureCode.TRANSPORT_REFUSED
    assert factory.open_count == 0


def test_adapter_and_credential_representations_never_expose_values(
    tmp_path: Path,
) -> None:
    credentials = _install(tmp_path)
    adapter = OfficialSelfHostedWordPressDraftAdapter(
        tmp_path, connection_factory=FakeFactory(FakeConnection(FakeResponse()))
    )
    for rendered in (repr(credentials), str(credentials), repr(adapter)):
        assert "synthetic" not in rendered
        assert "owner-editor" not in rendered
