"""Offline tests for the fixed WordPress.com OAuth2 setup infrastructure."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import ssl
import stat
from urllib.parse import parse_qsl, urlencode, urlsplit

import pytest

import raos.adapters.wordpresscom_oauth as oauth_module
from raos.adapters.wordpresscom_oauth import (
    SystemWordPressComOAuthTokenTransport,
    WORDPRESSCOM_ACCESS_TOKEN_ALIAS,
    WORDPRESSCOM_CLIENT_ID_ALIAS,
    WORDPRESSCOM_CLIENT_SECRET_ALIAS,
    WORDPRESSCOM_OAUTH_AUTHORIZATION_ENDPOINT,
    WORDPRESSCOM_OAUTH_BLOG,
    WORDPRESSCOM_OAUTH_REDIRECT_URI,
    WORDPRESSCOM_OAUTH_SCOPE,
    WORDPRESSCOM_OAUTH_SECRET_ROOT,
    WORDPRESSCOM_OAUTH_TOKEN_HOST,
    WORDPRESSCOM_OAUTH_TOKEN_PATH,
    WordPressComLoopbackCallback,
    WordPressComOAuthHttpResponse,
    WordPressComOAuthSecretStore,
    WordPressComOAuthSetup,
    WordPressComOAuthTokenDiagnosticCode,
    WordPressComOAuthTokenFailure,
)
from raos.adapters.wordpresscom_review_draft_https import WordPressComBearerToken
from raos.domain.editorial.wordpresscom_review_draft import (
    WORDPRESSCOM_REVIEW_DRAFT_TARGET,
    WordPressComReviewDraftFailure,
)


CLIENT_ID = b"client-id-not-real-1703"
CLIENT_SECRET = b"client-secret-not-real-1703-xxxxxxxx"
ACCESS_TOKEN = "access-token-not-real-1703-xxxxxxxx"
AUTHORIZATION_CODE = "authorization-code-not-real-1703"


def _write_private(path: Path, value: bytes, *, mode: int = 0o600) -> None:
    path.write_bytes(value + b"\n")
    path.chmod(mode)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    secret_root = root / WORDPRESSCOM_OAUTH_SECRET_ROOT
    secret_root.mkdir(parents=True, mode=0o700)
    secret_root.chmod(0o700)
    _write_private(secret_root / WORDPRESSCOM_CLIENT_ID_ALIAS, CLIENT_ID)
    _write_private(secret_root / WORDPRESSCOM_CLIENT_SECRET_ALIAS, CLIENT_SECRET)
    return root


class FakeEntropy:
    def __init__(self, value: bytes = bytes(range(32))) -> None:
        self.value = value
        self.counts: list[int] = []

    def token_bytes(self, count: int) -> bytes:
        self.counts.append(count)
        return self.value


class FakeOpener:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.urls: list[str] = []

    def open(self, authorization_url: str) -> bool:
        self.urls.append(authorization_url)
        return self.result


class FakeListener:
    def __init__(
        self,
        *,
        method: str = "GET",
        path: str = "/oauth/wordpresscom/callback",
        host_header: str = "127.0.0.1:18703",
        local_host: str = "127.0.0.1",
        local_port: int = 18703,
        query: str | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.method = method
        self.path = path
        self.host_header = host_header
        self.local_host = local_host
        self.local_port = local_port
        self.query = query
        self.error = error
        self.calls: list[dict[str, object]] = []

    def authorize(
        self,
        *,
        authorization_url: str,
        opener: FakeOpener,
        expected_state: object,
        host: str,
        port: int,
        path: str,
        timeout_seconds: int,
    ) -> WordPressComLoopbackCallback:
        self.calls.append(
            {
                "authorization_url": authorization_url,
                "expected_state": expected_state,
                "host": host,
                "path": path,
                "port": port,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.error is not None:
            raise self.error
        assert opener.open(authorization_url) is True
        state = dict(parse_qsl(urlsplit(authorization_url).query))["state"]
        assert type(expected_state) is oauth_module.WordPressComOAuthState
        assert expected_state.query_value() == state
        query = self.query or urlencode(
            [("code", AUTHORIZATION_CODE), ("state", state)]
        )
        return WordPressComLoopbackCallback(
            method=self.method,
            request_target=f"{self.path}?{query}",
            host_header=self.host_header,
            local_host=self.local_host,
            local_port=self.local_port,
        )


class FakeTokenTransport:
    def __init__(
        self,
        *,
        response: WordPressComOAuthHttpResponse | None = None,
        error: BaseException | None = None,
    ) -> None:
        payload = {
            "access_token": ACCESS_TOKEN,
            "blog_id": "1703",
            "blog_url": WORDPRESSCOM_REVIEW_DRAFT_TARGET,
            "scope": WORDPRESSCOM_OAUTH_SCOPE,
            "token_type": "bearer",
        }
        self.response = response or WordPressComOAuthHttpResponse(
            status=200,
            content_type="application/json; charset=UTF-8",
            body=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        )
        self.error = error
        self.calls: list[dict[str, object]] = []

    def post(
        self,
        *,
        host: str,
        port: int,
        path: str,
        body: bytes,
        headers: dict[str, str],
        connect_timeout_seconds: int,
        read_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> WordPressComOAuthHttpResponse:
        self.calls.append(
            {
                "body": body,
                "connect_timeout_seconds": connect_timeout_seconds,
                "headers": dict(headers),
                "host": host,
                "path": path,
                "port": port,
                "read_timeout_seconds": read_timeout_seconds,
                "tls_context": tls_context,
            }
        )
        if self.error is not None:
            raise self.error
        return self.response


def _setup(
    repository: Path,
    *,
    entropy: FakeEntropy | None = None,
    opener: FakeOpener | None = None,
    listener: FakeListener | None = None,
    transport: FakeTokenTransport | None = None,
) -> tuple[
    WordPressComOAuthSetup,
    WordPressComOAuthSecretStore,
    FakeEntropy,
    FakeOpener,
    FakeListener,
    FakeTokenTransport,
]:
    store = WordPressComOAuthSecretStore(repository_root=repository)
    entropy_value = entropy or FakeEntropy()
    opener_value = opener or FakeOpener()
    listener_value = listener or FakeListener()
    transport_value = transport or FakeTokenTransport()
    return (
        WordPressComOAuthSetup(
            store=store,
            entropy=entropy_value,
            opener=opener_value,
            listener=listener_value,
            transport=transport_value,
        ),
        store,
        entropy_value,
        opener_value,
        listener_value,
        transport_value,
    )


def test_fixed_private_store_and_redacted_values(repository: Path) -> None:
    store = WordPressComOAuthSecretStore(repository_root=repository)
    client_id = store.read_client_id()
    client_secret = store.read_client_secret()
    secret_root = repository / WORDPRESSCOM_OAUTH_SECRET_ROOT

    assert WORDPRESSCOM_OAUTH_SECRET_ROOT == Path(".secrets/wordpresscom-review-draft")
    assert stat.S_IMODE(secret_root.stat().st_mode) == 0o700
    assert (
        stat.S_IMODE((secret_root / WORDPRESSCOM_CLIENT_ID_ALIAS).stat().st_mode)
        == 0o600
    )
    assert (
        stat.S_IMODE((secret_root / WORDPRESSCOM_CLIENT_SECRET_ALIAS).stat().st_mode)
        == 0o600
    )
    rendered = " ".join(
        (
            repr(store),
            repr(client_id),
            str(client_id),
            repr(client_secret),
            str(client_secret),
        )
    )
    assert CLIENT_ID.decode() not in rendered
    assert CLIENT_SECRET.decode() not in rendered


def _system_authorization_url() -> str:
    return (
        WORDPRESSCOM_OAUTH_AUTHORIZATION_ENDPOINT
        + "?"
        + urlencode(
            [
                ("blog", WORDPRESSCOM_OAUTH_BLOG),
                ("client_id", CLIENT_ID.decode()),
                ("redirect_uri", WORDPRESSCOM_OAUTH_REDIRECT_URI),
                ("response_type", "code"),
                ("scope", WORDPRESSCOM_OAUTH_SCOPE),
                ("state", "A" * 43),
            ]
        )
    )


@pytest.mark.parametrize("returncode", [0, 1, 97])
def test_system_browser_opener_passes_url_only_on_stdin_and_checks_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
) -> None:
    executable = tmp_path / "powershell.exe"
    executable.write_bytes(b"synthetic executable")
    executable.chmod(0o700)
    monkeypatch.setattr(oauth_module, "_POWERSHELL_PATH", executable)
    monkeypatch.setattr(
        oauth_module,
        "_validated_wsl_interop",
        lambda value: "/run/WSL/1703_interop",
    )
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(arguments: list[str], **kwargs: object) -> object:
        calls.append((arguments, kwargs))
        return type("Completed", (), {"returncode": returncode})()

    monkeypatch.setattr(oauth_module.subprocess, "run", fake_run)
    authorization_url = _system_authorization_url()

    opened = oauth_module.SystemWordPressComBrowserOpener().open(authorization_url)

    assert opened is (returncode == 0)
    assert len(calls) == 1
    arguments, kwargs = calls[0]
    assert arguments == [
        str(executable),
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "$url = [Console]::In.ReadToEnd(); Start-Process -FilePath $url",
    ]
    assert authorization_url not in " ".join(arguments)
    assert kwargs["input"] == authorization_url.encode("ascii")
    assert kwargs["stdout"] is oauth_module.subprocess.DEVNULL
    assert kwargs["stderr"] is oauth_module.subprocess.DEVNULL
    assert kwargs["env"] == {
        "PATH": "/usr/bin:/bin",
        "WSL_INTEROP": "/run/WSL/1703_interop",
    }
    assert kwargs["close_fds"] is True
    assert kwargs["timeout"] == 10
    assert kwargs["check"] is False


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("timeout detail"), OSError("process detail")],
)
def test_system_browser_opener_failure_is_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    executable = tmp_path / "powershell.exe"
    executable.write_bytes(b"synthetic executable")
    executable.chmod(0o700)
    monkeypatch.setattr(oauth_module, "_POWERSHELL_PATH", executable)
    monkeypatch.setattr(
        oauth_module,
        "_validated_wsl_interop",
        lambda value: "/run/WSL/1703_interop",
    )

    def fail_run(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise failure

    monkeypatch.setattr(oauth_module.subprocess, "run", fail_run)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        oauth_module.SystemWordPressComBrowserOpener().open(_system_authorization_url())

    rendered = " ".join((str(caught.value), repr(caught.value)))
    assert str(caught.value) == "REVIEW_DRAFT_OAUTH_AUTHORIZATION_INVALID"
    assert "detail" not in rendered
    assert "state=" not in rendered


@pytest.mark.parametrize(
    "value",
    [
        "/run/WSL/../../tmp/attacker-socket",
        "/run/WSL/0_interop",
        "/run/WSL/not-decimal_interop",
        "/run/WSL/1703_interop/child",
        "run/WSL/1703_interop",
    ],
)
def test_wsl_interop_rejects_noncanonical_paths(value: str) -> None:
    with pytest.raises(WordPressComReviewDraftFailure):
        oauth_module._validated_wsl_interop(value)


@pytest.mark.parametrize("kind", ["regular", "symlink"])
def test_wsl_interop_rejects_non_socket_or_symlink(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    value = "/run/WSL/1703_interop"
    socket_mode = stat.S_IFREG | 0o600 if kind == "regular" else stat.S_IFLNK | 0o777

    def fake_lstat(path: Path) -> os.stat_result:
        raw = os.fspath(path)
        if raw == value:
            return os.stat_result((socket_mode, 0, 0, 1, 0, 0, 0, 0, 0, 0))
        return os.stat_result((stat.S_IFDIR | 0o755, 0, 0, 1, 0, 0, 0, 0, 0, 0))

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    monkeypatch.setattr(oauth_module.os.path, "realpath", lambda path: value)

    with pytest.raises(WordPressComReviewDraftFailure):
        oauth_module._validated_wsl_interop(value)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda url: url.replace("client-id-not-real-1703", "%0A"),
        lambda url: url.replace("client-id-not-real-1703", "client%2did-not-real-1703"),
        lambda url: url.replace("scope=posts", "scope=%70osts"),
        lambda url: url + "&state=" + "B" * 43,
    ],
)
def test_system_browser_opener_rejects_noncanonical_url_before_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: object,
) -> None:
    executable = tmp_path / "powershell.exe"
    executable.write_bytes(b"synthetic executable")
    executable.chmod(0o700)
    monkeypatch.setattr(oauth_module, "_POWERSHELL_PATH", executable)
    monkeypatch.setattr(
        oauth_module,
        "_validated_wsl_interop",
        lambda value: "/run/WSL/1703_interop",
    )
    monkeypatch.setattr(
        oauth_module.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("invalid URL reached process boundary"),
    )

    with pytest.raises(WordPressComReviewDraftFailure):
        oauth_module.SystemWordPressComBrowserOpener().open(
            mutation(_system_authorization_url())  # type: ignore[operator]
        )


def test_exact_authorization_callback_exchange_and_exclusive_token_store(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        oauth_module.socket,
        "socket",
        lambda *args, **kwargs: pytest.fail("real socket used"),
    )
    monkeypatch.setattr(
        oauth_module.http.client,
        "HTTPSConnection",
        lambda *args, **kwargs: pytest.fail("real HTTPS used"),
    )
    setup, store, entropy, opener, listener, transport = _setup(repository)

    receipt = setup.setup()

    assert entropy.counts == [32]
    assert len(opener.urls) == len(listener.calls) == len(transport.calls) == 1
    authorization = urlsplit(opener.urls[0])
    assert f"{authorization.scheme}://{authorization.netloc}{authorization.path}" == (
        WORDPRESSCOM_OAUTH_AUTHORIZATION_ENDPOINT
    )
    authorization_pairs = parse_qsl(authorization.query, keep_blank_values=True)
    assert [key for key, _ in authorization_pairs] == [
        "blog",
        "client_id",
        "redirect_uri",
        "response_type",
        "scope",
        "state",
    ]
    authorization_query = dict(authorization_pairs)
    assert authorization_query == {
        "blog": WORDPRESSCOM_OAUTH_BLOG,
        "client_id": CLIENT_ID.decode(),
        "redirect_uri": WORDPRESSCOM_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "posts",
        "state": authorization_query["state"],
    }
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", authorization_query["state"])
    listener_call = listener.calls[0]
    expected_state = listener_call.pop("expected_state")
    assert type(expected_state) is oauth_module.WordPressComOAuthState
    assert expected_state.query_value() == authorization_query["state"]
    assert listener_call == {
        "authorization_url": opener.urls[0],
        "host": "127.0.0.1",
        "path": "/oauth/wordpresscom/callback",
        "port": 18703,
        "timeout_seconds": 300,
    }
    token_call = transport.calls[0]
    assert token_call["host"] == WORDPRESSCOM_OAUTH_TOKEN_HOST
    assert token_call["port"] == 443
    assert token_call["path"] == WORDPRESSCOM_OAUTH_TOKEN_PATH
    assert token_call["connect_timeout_seconds"] == 5
    assert token_call["read_timeout_seconds"] == 20
    context = token_call["tls_context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    form_pairs = parse_qsl(
        token_call["body"].decode("ascii"),
        keep_blank_values=True,  # type: ignore[union-attr]
    )
    assert [key for key, _ in form_pairs] == [
        "client_id",
        "client_secret",
        "code",
        "grant_type",
        "redirect_uri",
    ]
    assert dict(form_pairs) == {
        "client_id": CLIENT_ID.decode(),
        "client_secret": CLIENT_SECRET.decode(),
        "code": AUTHORIZATION_CODE,
        "grant_type": "authorization_code",
        "redirect_uri": WORDPRESSCOM_OAUTH_REDIRECT_URI,
    }
    forbidden = {"password", "username", "code_challenge", "media", "global"}
    assert forbidden.isdisjoint(dict(authorization_pairs))
    assert forbidden.isdisjoint(dict(form_pairs))
    token_path = (
        repository / WORDPRESSCOM_OAUTH_SECRET_ROOT / WORDPRESSCOM_ACCESS_TOKEN_ALIAS
    )
    assert token_path.read_bytes() == ACCESS_TOKEN.encode() + b"\n"
    assert stat.S_IMODE(token_path.stat().st_mode) == 0o600
    assert (
        store.read(WORDPRESSCOM_ACCESS_TOKEN_ALIAS).storage_bytes()
        == ACCESS_TOKEN.encode()
    )
    assert receipt.target_origin == WORDPRESSCOM_REVIEW_DRAFT_TARGET
    assert receipt.scope == "posts"
    assert receipt.publication_authorized is False
    assert ACCESS_TOKEN not in repr(receipt)


@pytest.mark.parametrize(
    "listener",
    [
        FakeListener(method="POST"),
        FakeListener(path="/wrong"),
        FakeListener(host_header="localhost:18703"),
        FakeListener(local_host="0.0.0.0"),
        FakeListener(local_port=8080),
        FakeListener(query=f"code={AUTHORIZATION_CODE}&state=wrong-state"),
        FakeListener(query=f"code={AUTHORIZATION_CODE}&state=one&state=two"),
        FakeListener(query="error=access_denied"),
        FakeListener(error=TimeoutError("callback-timeout-detail")),
    ],
)
def test_callback_refusals_stop_before_token_exchange_and_store(
    repository: Path, listener: FakeListener
) -> None:
    setup, _, _, _, _, transport = _setup(repository, listener=listener)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        setup.setup()

    assert str(caught.value) == "REVIEW_DRAFT_OAUTH_CALLBACK_INVALID"
    assert "callback-timeout-detail" not in repr(caught.value)
    assert transport.calls == []
    assert not (
        repository / WORDPRESSCOM_OAUTH_SECRET_ROOT / WORDPRESSCOM_ACCESS_TOKEN_ALIAS
    ).exists()


def test_state_comparison_uses_constant_time_primitive(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    comparisons: list[tuple[str, str]] = []
    original = oauth_module.hmac.compare_digest

    def compare(left: str, right: str) -> bool:
        comparisons.append((left, right))
        return original(left, right)

    monkeypatch.setattr(oauth_module.hmac, "compare_digest", compare)
    setup, _, _, _, _, _ = _setup(repository)

    setup.setup()

    assert len(comparisons) == 1
    assert comparisons[0][0] == comparisons[0][1]
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", comparisons[0][0])


@pytest.mark.parametrize("value", ["x", "x" * 15, "with space"])
def test_authorization_code_accepts_rfc_vschar_bounds(value: str) -> None:
    code = oauth_module.WordPressComAuthorizationCode(value)

    assert code.form_value() == value


@pytest.mark.parametrize("value", ["", "\x1f", "\x7f", "é", "x" * 2049])
def test_authorization_code_rejects_empty_control_nonascii_and_overmax(
    value: str,
) -> None:
    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        oauth_module.WordPressComAuthorizationCode(value)

    assert str(caught.value) == "REVIEW_DRAFT_OAUTH_CALLBACK_INVALID"


def test_existing_token_blocks_before_entropy_browser_listener_or_transport(
    repository: Path,
) -> None:
    token_path = (
        repository / WORDPRESSCOM_OAUTH_SECRET_ROOT / WORDPRESSCOM_ACCESS_TOKEN_ALIAS
    )
    _write_private(token_path, ACCESS_TOKEN.encode())
    setup, _, entropy, opener, listener, transport = _setup(repository)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        setup.setup()

    assert str(caught.value) == "REVIEW_DRAFT_OAUTH_TOKEN_EXISTS"
    assert entropy.counts == []
    assert opener.urls == []
    assert listener.calls == []
    assert transport.calls == []
    assert token_path.read_bytes() == ACCESS_TOKEN.encode() + b"\n"


@pytest.mark.parametrize(
    "environment_name",
    ["SSL_CERT_FILE", "SSL_CERT_DIR", "SSLKEYLOGFILE"],
)
def test_tls_override_stops_before_secret_store_or_transport(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
) -> None:
    for name in {"SSL_CERT_FILE", "SSL_CERT_DIR", "SSLKEYLOGFILE"}:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(environment_name, "/untrusted/not-used")
    setup, _, entropy, opener, listener, transport = _setup(repository)

    def must_not_touch_store(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("TLS override must stop before secret-store access")

    for method in {
        "read_client_id",
        "read_client_secret",
        "require_access_token_absent",
        "store_access_token",
    }:
        monkeypatch.setattr(
            WordPressComOAuthSecretStore,
            method,
            must_not_touch_store,
        )

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        setup.setup()

    assert type(caught.value) is WordPressComOAuthTokenFailure
    assert (
        caught.value.diagnostic_code
        is WordPressComOAuthTokenDiagnosticCode.TLS_ENVIRONMENT_INVALID
    )
    assert entropy.counts == []
    assert opener.urls == []
    assert listener.calls == []
    assert transport.calls == []
    assert not (
        repository / WORDPRESSCOM_OAUTH_SECRET_ROOT / WORDPRESSCOM_ACCESS_TOKEN_ALIAS
    ).exists()


def test_setup_exposes_no_publish_update_or_generic_oauth_action() -> None:
    public = {name for name in vars(WordPressComOAuthSetup) if not name.startswith("_")}
    assert public == {"setup"}


def test_loopback_parser_admits_inert_complete_browser_headers() -> None:
    raw = (
        f"GET /oauth/wordpresscom/callback?code={AUTHORIZATION_CODE}&state="
        + "A" * 43
        + " HTTP/1.1\r\n"
        "Host: 127.0.0.1:18703\r\n"
        "Accept: text/html,application/xhtml+xml\r\n"
        "Accept-Language: ja,en-US;q=0.9\r\n"
        "Sec-Fetch-Dest: document\r\n"
        "Sec-Fetch-Mode: navigate\r\n"
        "Sec-Fetch-Site: cross-site\r\n"
        'sec-ch-ua: "Chromium";v="140"\r\n'
        "Upgrade-Insecure-Requests: 1\r\n"
        "User-Agent: synthetic-browser\r\n"
        "Content-Length: 0\r\n\r\n"
    ).encode("ascii")

    callback = oauth_module._parse_loopback_request(
        raw, local_host="127.0.0.1", local_port=18703
    )

    assert callback.method == "GET"
    assert callback.host_header == "127.0.0.1:18703"
    assert callback.local_host == "127.0.0.1"
    assert callback.local_port == 18703


@pytest.mark.parametrize(
    "blog_id",
    [0, -1, True, "0", "-1", "not-digits", "99999999999999999999"],
)
def test_token_response_requires_positive_non_bool_blog_id(
    repository: Path, blog_id: object
) -> None:
    payload = {
        "access_token": ACCESS_TOKEN,
        "blog_id": blog_id,
        "blog_url": WORDPRESSCOM_REVIEW_DRAFT_TARGET,
        "scope": "posts",
        "token_type": "bearer",
    }
    response = WordPressComOAuthHttpResponse(
        status=200,
        content_type="application/json",
        body=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
    )
    transport = FakeTokenTransport(response=response)
    setup, _, _, _, _, _ = _setup(repository, transport=transport)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        setup.setup()

    assert str(caught.value) == "REVIEW_DRAFT_OAUTH_TOKEN_EXCHANGE_INVALID"
    assert type(caught.value) is WordPressComOAuthTokenFailure
    assert (
        caught.value.diagnostic_code
        is WordPressComOAuthTokenDiagnosticCode.BLOG_ID_INVALID
    )
    assert len(transport.calls) == 1


def test_token_response_accepts_positive_integer_blog_id(repository: Path) -> None:
    payload = {
        "access_token": ACCESS_TOKEN,
        "blog_id": 1703,
        "blog_url": WORDPRESSCOM_REVIEW_DRAFT_TARGET,
        "scope": "posts",
        "token_type": "bearer",
    }
    response = WordPressComOAuthHttpResponse(
        status=200,
        content_type="application/json",
        body=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
    )
    transport = FakeTokenTransport(response=response)
    setup, _, _, _, _, _ = _setup(repository, transport=transport)

    receipt = setup.setup()

    assert receipt.access_token_stored is True
    assert len(transport.calls) == 1


def test_secret_store_rejects_wrong_root_mode(repository: Path) -> None:
    secret_root = repository / WORDPRESSCOM_OAUTH_SECRET_ROOT
    secret_root.chmod(0o755)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        WordPressComOAuthSecretStore(repository_root=repository)

    assert str(caught.value) == "REVIEW_DRAFT_OAUTH_SECRET_STORE_INVALID"


def test_secret_store_rejects_root_and_ancestor_symlinks(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    secrets_parent = repository / ".secrets"
    secrets_parent.mkdir()
    real_root = tmp_path / "real-secret-root"
    real_root.mkdir(mode=0o700)
    (secrets_parent / "wordpresscom-review-draft").symlink_to(
        real_root, target_is_directory=True
    )

    with pytest.raises(WordPressComReviewDraftFailure):
        WordPressComOAuthSecretStore(repository_root=repository)

    real_repository = tmp_path / "real-repository"
    root = real_repository / WORDPRESSCOM_OAUTH_SECRET_ROOT
    root.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    linked_repository = tmp_path / "linked-repository"
    linked_repository.symlink_to(real_repository, target_is_directory=True)
    with pytest.raises(WordPressComReviewDraftFailure):
        WordPressComOAuthSecretStore(repository_root=linked_repository)


@pytest.mark.parametrize("kind", ["symlink", "directory", "wrong_mode", "oversized"])
def test_secret_store_rejects_non_private_client_files(
    repository: Path, tmp_path: Path, kind: str
) -> None:
    secret_root = repository / WORDPRESSCOM_OAUTH_SECRET_ROOT
    path = secret_root / WORDPRESSCOM_CLIENT_ID_ALIAS
    path.unlink()
    if kind == "symlink":
        target = tmp_path / "outside-client-id"
        _write_private(target, CLIENT_ID)
        path.symlink_to(target)
    elif kind == "directory":
        path.mkdir(mode=0o600)
    elif kind == "wrong_mode":
        _write_private(path, CLIENT_ID, mode=0o644)
    else:
        _write_private(path, b"x" * 4097)
    store = WordPressComOAuthSecretStore(repository_root=repository)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        store.read_client_id()

    assert str(caught.value) == "REVIEW_DRAFT_OAUTH_SECRET_STORE_INVALID"


def test_secret_store_rechecks_current_owner(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = WordPressComOAuthSecretStore(repository_root=repository)
    real_euid = os.geteuid()
    monkeypatch.setattr(oauth_module.os, "geteuid", lambda: real_euid + 1)

    with pytest.raises(WordPressComReviewDraftFailure):
        store.read_client_id()


def test_secret_store_accepts_only_exact_alias_and_never_overwrites_token(
    repository: Path,
) -> None:
    store = WordPressComOAuthSecretStore(repository_root=repository)
    token = WordPressComBearerToken(ACCESS_TOKEN.encode())

    with pytest.raises(WordPressComReviewDraftFailure):
        store.read("access_token")
    store.store_access_token(token)
    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        store.store_access_token(
            WordPressComBearerToken(b"different-not-real-token-1703")
        )

    assert str(caught.value) == "REVIEW_DRAFT_OAUTH_TOKEN_EXISTS"
    token_path = (
        repository / WORDPRESSCOM_OAUTH_SECRET_ROOT / WORDPRESSCOM_ACCESS_TOKEN_ALIAS
    )
    assert token_path.read_bytes() == ACCESS_TOKEN.encode() + b"\n"


@pytest.mark.parametrize(
    ("status", "content_type", "payload", "diagnostic"),
    [
        (
            302,
            "application/json",
            {},
            WordPressComOAuthTokenDiagnosticCode.HTTP_STATUS_INVALID,
        ),
        (
            307,
            "application/json",
            {},
            WordPressComOAuthTokenDiagnosticCode.HTTP_STATUS_INVALID,
        ),
        (
            200,
            "text/html",
            {},
            WordPressComOAuthTokenDiagnosticCode.CONTENT_TYPE_INVALID,
        ),
        (
            200,
            "application/json",
            {
                "access_token": ACCESS_TOKEN,
                "blog_id": "1703",
                "blog_url": WORDPRESSCOM_REVIEW_DRAFT_TARGET,
                "scope": "media",
                "token_type": "bearer",
            },
            WordPressComOAuthTokenDiagnosticCode.SCOPE_INVALID,
        ),
        (
            200,
            "application/json",
            {
                "access_token": ACCESS_TOKEN,
                "blog_id": "1703",
                "blog_url": WORDPRESSCOM_REVIEW_DRAFT_TARGET,
                "scope": "global",
                "token_type": "bearer",
            },
            WordPressComOAuthTokenDiagnosticCode.SCOPE_INVALID,
        ),
        (
            200,
            "application/json",
            {
                "access_token": ACCESS_TOKEN,
                "blog_id": "1703",
                "blog_url": WORDPRESSCOM_REVIEW_DRAFT_TARGET,
                "scope": "posts",
                "token_type": "Bearer",
            },
            WordPressComOAuthTokenDiagnosticCode.TOKEN_TYPE_INVALID,
        ),
        (
            200,
            "application/json",
            {
                "access_token": "short",
                "blog_id": "1703",
                "blog_url": WORDPRESSCOM_REVIEW_DRAFT_TARGET,
                "scope": "posts",
                "token_type": "bearer",
            },
            WordPressComOAuthTokenDiagnosticCode.ACCESS_TOKEN_SHAPE_INVALID,
        ),
        (
            200,
            "application/json",
            {
                "blog_id": "1703",
                "blog_url": WORDPRESSCOM_REVIEW_DRAFT_TARGET,
                "scope": "posts",
                "token_type": "bearer",
            },
            WordPressComOAuthTokenDiagnosticCode.ACCESS_TOKEN_MISSING,
        ),
    ],
)
def test_token_status_redirect_type_blog_and_scope_fail_closed_without_store(
    repository: Path,
    status: int,
    content_type: str,
    payload: object,
    diagnostic: WordPressComOAuthTokenDiagnosticCode,
) -> None:
    response = WordPressComOAuthHttpResponse(
        status=status,
        content_type=content_type,
        body=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
    )
    transport = FakeTokenTransport(response=response)
    setup, _, _, _, _, _ = _setup(repository, transport=transport)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        setup.setup()

    assert str(caught.value) == "REVIEW_DRAFT_OAUTH_TOKEN_EXCHANGE_INVALID"
    assert type(caught.value) is WordPressComOAuthTokenFailure
    assert caught.value.diagnostic_code is diagnostic
    assert len(transport.calls) == 1
    assert not (
        repository / WORDPRESSCOM_OAUTH_SECRET_ROOT / WORDPRESSCOM_ACCESS_TOKEN_ALIAS
    ).exists()


@pytest.mark.parametrize(
    "blog_url",
    [
        WORDPRESSCOM_REVIEW_DRAFT_TARGET,
        WORDPRESSCOM_REVIEW_DRAFT_TARGET + "/",
        "http://kurashierabinote.wordpress.com",
        "http://kurashierabinote.wordpress.com/",
    ],
)
def test_token_response_accepts_only_four_exact_target_metadata_literals(
    repository: Path, blog_url: str
) -> None:
    payload = {
        "access_token": ACCESS_TOKEN,
        "blog_id": "1703",
        "blog_url": blog_url,
        "scope": "posts",
        "token_type": "bearer",
    }
    response = WordPressComOAuthHttpResponse(
        status=200,
        content_type="application/json",
        body=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
    )
    transport = FakeTokenTransport(response=response)
    setup, _, _, _, _, _ = _setup(
        repository,
        transport=transport,
    )

    receipt = setup.setup()

    assert receipt.target_origin == WORDPRESSCOM_REVIEW_DRAFT_TARGET
    assert receipt.target_origin.startswith("https://")
    assert len(transport.calls) == 1
    token_call = transport.calls[0]
    assert token_call["host"] == WORDPRESSCOM_OAUTH_TOKEN_HOST
    assert token_call["port"] == 443
    assert token_call["path"] == WORDPRESSCOM_OAUTH_TOKEN_PATH
    assert isinstance(token_call["tls_context"], ssl.SSLContext)
    token_body = token_call["body"]
    assert type(token_body) is bytes
    assert b"http://" not in token_body
    assert "http://" not in repr(receipt)


def test_http_blog_metadata_never_selects_an_http_transport(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "access_token": ACCESS_TOKEN,
        "blog_id": "1703",
        "blog_url": "http://kurashierabinote.wordpress.com/",
        "token_type": "bearer",
    }
    response_body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    connections: list[dict[str, object]] = []

    class FakeSocket:
        def settimeout(self, timeout_seconds: int) -> None:
            assert timeout_seconds == 20

    class FakeResponse:
        status = 200

        def read(self, size: int) -> bytes:
            assert size == 65537
            return response_body

        def getheader(self, name: str, default: str = "") -> str:
            assert name == "Content-Type"
            del default
            return "application/json"

    class FakeHttpsConnection:
        def __init__(self, **kwargs: object) -> None:
            connections.append(dict(kwargs))
            self.sock: FakeSocket | None = FakeSocket()

        def connect(self) -> None:
            return None

        def request(
            self,
            method: str,
            path: str,
            *,
            body: bytes,
            headers: dict[str, str],
        ) -> None:
            assert method == "POST"
            assert path == WORDPRESSCOM_OAUTH_TOKEN_PATH
            assert b"http://" not in body
            assert headers["Content-Type"] == "application/x-www-form-urlencoded"

        def getresponse(self) -> FakeResponse:
            return FakeResponse()

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        oauth_module.http.client,
        "HTTPConnection",
        lambda *args, **kwargs: pytest.fail("HTTP transport became constructible"),
    )
    monkeypatch.setattr(
        oauth_module.http.client,
        "HTTPSConnection",
        FakeHttpsConnection,
    )
    setup = WordPressComOAuthSetup(
        store=WordPressComOAuthSecretStore(repository_root=repository),
        entropy=FakeEntropy(),
        opener=FakeOpener(),
        listener=FakeListener(),
        transport=SystemWordPressComOAuthTokenTransport(),
    )

    receipt = setup.setup()

    assert receipt.target_origin == WORDPRESSCOM_REVIEW_DRAFT_TARGET
    assert connections == [
        {
            "host": WORDPRESSCOM_OAUTH_TOKEN_HOST,
            "port": 443,
            "timeout": 5,
            "context": connections[0]["context"],
        }
    ]
    assert isinstance(connections[0]["context"], ssl.SSLContext)


@pytest.mark.parametrize(
    ("blog_url", "diagnostic"),
    [
        (None, WordPressComOAuthTokenDiagnosticCode.BLOG_URL_TYPE_INVALID),
        (1703, WordPressComOAuthTokenDiagnosticCode.BLOG_URL_TYPE_INVALID),
        (
            "https:\\kurashierabinote.wordpress.com",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_PARSE_INVALID,
        ),
        (
            "https://[kurashierabinote.wordpress.com",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_PARSE_INVALID,
        ),
        (
            "ftp://kurashierabinote.wordpress.com",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_SCHEME_INVALID,
        ),
        (
            "HTTPS://kurashierabinote.wordpress.com",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_SCHEME_INVALID,
        ),
        (
            "https://other.wordpress.com",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_HOST_INVALID,
        ),
        (
            "http://other.wordpress.com",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_HOST_INVALID,
        ),
        (
            "https://Kurashierabinote.wordpress.com",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_HOST_INVALID,
        ),
        (
            "https://user@kurashierabinote.wordpress.com",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_AUTHORITY_INVALID,
        ),
        (
            "https://kurashierabinote.wordpress.com:443",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_AUTHORITY_INVALID,
        ),
        (
            "http://kurashierabinote.wordpress.com:80",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_AUTHORITY_INVALID,
        ),
        (
            "https://kurashierabinote.wordpress.com/path",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_PATH_INVALID,
        ),
        (
            "http://kurashierabinote.wordpress.com/path",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_PATH_INVALID,
        ),
        (
            "https://kurashierabinote.wordpress.com/\u2603",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_PATH_INVALID,
        ),
        (
            "https://kurashierabinote.wordpress.com?query=1",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_QUERY_FRAGMENT_INVALID,
        ),
        (
            "http://kurashierabinote.wordpress.com?query=1",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_QUERY_FRAGMENT_INVALID,
        ),
        (
            "https://kurashierabinote.wordpress.com#fragment",
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_QUERY_FRAGMENT_INVALID,
        ),
    ],
)
def test_token_response_rejects_every_nonexact_target_url_without_store(
    repository: Path,
    blog_url: object,
    diagnostic: WordPressComOAuthTokenDiagnosticCode,
) -> None:
    payload = {
        "access_token": ACCESS_TOKEN,
        "blog_id": "1703",
        "blog_url": blog_url,
        "scope": "posts",
        "token_type": "bearer",
    }
    response = WordPressComOAuthHttpResponse(
        status=200,
        content_type="application/json",
        body=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
    )
    setup, _, _, _, _, _ = _setup(
        repository, transport=FakeTokenTransport(response=response)
    )

    with pytest.raises(WordPressComOAuthTokenFailure) as caught:
        setup.setup()

    assert caught.value.diagnostic_code is diagnostic
    if type(blog_url) is str:
        assert blog_url not in str(caught.value)
    assert not (
        repository / WORDPRESSCOM_OAUTH_SECRET_ROOT / WORDPRESSCOM_ACCESS_TOKEN_ALIAS
    ).exists()


def test_duplicate_blog_url_key_stops_at_json_boundary(repository: Path) -> None:
    body = (
        b'{"access_token":"access-token-not-real-1703-xxxxxxxx",'
        b'"blog_id":"1703",'
        b'"blog_url":"https://kurashierabinote.wordpress.com",'
        b'"blog_url":"https://other.wordpress.com",'
        b'"token_type":"bearer"}'
    )
    response = WordPressComOAuthHttpResponse(
        status=200,
        content_type="application/json",
        body=body,
    )
    setup, _, _, _, _, _ = _setup(
        repository, transport=FakeTokenTransport(response=response)
    )

    with pytest.raises(WordPressComOAuthTokenFailure) as caught:
        setup.setup()

    assert (
        caught.value.diagnostic_code
        is WordPressComOAuthTokenDiagnosticCode.JSON_DUPLICATE_KEY
    )


@pytest.mark.parametrize(
    ("body", "diagnostic"),
    [
        (
            b'{"access_token":"one","access_token":"two"}',
            WordPressComOAuthTokenDiagnosticCode.JSON_DUPLICATE_KEY,
        ),
        (
            b'{"access_token":NaN}',
            WordPressComOAuthTokenDiagnosticCode.JSON_NONFINITE,
        ),
        (b"not-json", WordPressComOAuthTokenDiagnosticCode.JSON_PARSE_INVALID),
        (b"\xff\xff", WordPressComOAuthTokenDiagnosticCode.JSON_ENCODING_INVALID),
        (b"[]", WordPressComOAuthTokenDiagnosticCode.JSON_TREE_INVALID),
        (
            b'{"error":"synthetic-provider-error"}',
            WordPressComOAuthTokenDiagnosticCode.PROVIDER_OTHER_ERROR,
        ),
    ],
)
def test_token_json_duplicate_nonfinite_and_malformed_fail_closed(
    repository: Path,
    body: bytes,
    diagnostic: WordPressComOAuthTokenDiagnosticCode,
) -> None:
    response = WordPressComOAuthHttpResponse(
        status=200, content_type="application/json", body=body
    )
    transport = FakeTokenTransport(response=response)
    setup, _, _, _, _, _ = _setup(repository, transport=transport)

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        setup.setup()

    assert type(caught.value) is WordPressComOAuthTokenFailure
    assert caught.value.diagnostic_code is diagnostic
    assert len(transport.calls) == 1
    assert not (
        repository / WORDPRESSCOM_OAUTH_SECRET_ROOT / WORDPRESSCOM_ACCESS_TOKEN_ALIAS
    ).exists()


@pytest.mark.parametrize(
    ("status", "body", "diagnostic"),
    [
        (
            400,
            b'{"error":"invalid_client","error_description":"not-rendered"}',
            WordPressComOAuthTokenDiagnosticCode.PROVIDER_INVALID_CLIENT,
        ),
        (
            400,
            b'{"error":"invalid_grant","error_description":"not-rendered"}',
            WordPressComOAuthTokenDiagnosticCode.PROVIDER_INVALID_GRANT,
        ),
        (
            400,
            b'{"error":"unexpected-provider-value"}',
            WordPressComOAuthTokenDiagnosticCode.PROVIDER_OTHER_ERROR,
        ),
        (
            400,
            b"{}",
            WordPressComOAuthTokenDiagnosticCode.HTTP_STATUS_INVALID,
        ),
        (
            400,
            b'{"error":"one","error":"two"}',
            WordPressComOAuthTokenDiagnosticCode.JSON_DUPLICATE_KEY,
        ),
        (
            400,
            b'{"error":NaN}',
            WordPressComOAuthTokenDiagnosticCode.JSON_NONFINITE,
        ),
        (
            400,
            b"not-json",
            WordPressComOAuthTokenDiagnosticCode.JSON_PARSE_INVALID,
        ),
    ],
)
def test_non_200_token_response_has_value_free_deterministic_diagnostic(
    repository: Path,
    status: int,
    body: bytes,
    diagnostic: WordPressComOAuthTokenDiagnosticCode,
) -> None:
    response = WordPressComOAuthHttpResponse(
        status=status,
        content_type="application/json",
        body=body,
    )
    transport = FakeTokenTransport(response=response)
    setup, _, _, _, _, _ = _setup(repository, transport=transport)

    with pytest.raises(WordPressComOAuthTokenFailure) as caught:
        setup.setup()

    assert caught.value.diagnostic_code is diagnostic
    rendered = " ".join((str(caught.value), repr(caught.value)))
    assert "not-rendered" not in rendered
    assert "unexpected-provider-value" not in rendered
    assert str(status) not in rendered
    assert not (
        repository / WORDPRESSCOM_OAUTH_SECRET_ROOT / WORDPRESSCOM_ACCESS_TOKEN_ALIAS
    ).exists()


def test_token_json_depth_and_node_limits_fail_closed(repository: Path) -> None:
    deep: object = "leaf"
    for _ in range(40):
        deep = [deep]
    base = {
        "access_token": ACCESS_TOKEN,
        "blog_id": "1703",
        "blog_url": WORDPRESSCOM_REVIEW_DRAFT_TARGET,
        "scope": "posts",
        "token_type": "bearer",
    }
    payloads = [base | {"extra": deep}, base | {"extra": [None] * 10001}]
    for payload in payloads:
        response = WordPressComOAuthHttpResponse(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        )
        setup, _, _, _, _, transport = _setup(
            repository, transport=FakeTokenTransport(response=response)
        )
        with pytest.raises(WordPressComReviewDraftFailure) as caught:
            setup.setup()
        assert type(caught.value) is WordPressComOAuthTokenFailure
        assert (
            caught.value.diagnostic_code
            is WordPressComOAuthTokenDiagnosticCode.JSON_TREE_INVALID
        )
        assert len(transport.calls) == 1


@pytest.mark.parametrize("body", [b"", b"x"])
def test_token_response_body_size_diagnostic_is_closed(body: bytes) -> None:
    response = WordPressComOAuthHttpResponse(
        status=200,
        content_type="application/json",
        body=body,
    )

    with pytest.raises(WordPressComOAuthTokenFailure) as caught:
        oauth_module._token_from_response(response)

    assert (
        caught.value.diagnostic_code
        is WordPressComOAuthTokenDiagnosticCode.BODY_SIZE_INVALID
    )


def test_oversized_token_response_is_classified_without_retaining_body() -> None:
    with pytest.raises(WordPressComOAuthTokenFailure) as caught:
        WordPressComOAuthHttpResponse(
            status=200,
            content_type="application/json",
            body=b"x" * 65537,
        )

    assert (
        caught.value.diagnostic_code
        is WordPressComOAuthTokenDiagnosticCode.BODY_SIZE_INVALID
    )


def test_token_response_shape_is_classified_without_observed_value() -> None:
    with pytest.raises(WordPressComOAuthTokenFailure) as caught:
        oauth_module._token_from_response(object())

    assert (
        caught.value.diagnostic_code
        is WordPressComOAuthTokenDiagnosticCode.RESPONSE_SHAPE_INVALID
    )
    assert "object" not in str(caught.value)


@pytest.mark.parametrize(
    ("failure_stage", "diagnostic"),
    [
        ("connect", WordPressComOAuthTokenDiagnosticCode.CONNECTION_FAILED),
        ("request", WordPressComOAuthTokenDiagnosticCode.REQUEST_AMBIGUOUS),
        ("response", WordPressComOAuthTokenDiagnosticCode.REQUEST_AMBIGUOUS),
    ],
)
def test_system_token_transport_distinguishes_pre_request_and_ambiguous_failure(
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
    diagnostic: WordPressComOAuthTokenDiagnosticCode,
) -> None:
    secret_detail = "synthetic-transport-secret-detail"

    class FakeSocket:
        def settimeout(self, timeout_seconds: int) -> None:
            assert timeout_seconds == 20

    class FakeConnection:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["host"] == WORDPRESSCOM_OAUTH_TOKEN_HOST
            self.sock: FakeSocket | None = FakeSocket()

        def connect(self) -> None:
            if failure_stage == "connect":
                raise OSError(secret_detail)

        def request(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            if failure_stage == "request":
                raise OSError(secret_detail)

        def getresponse(self) -> object:
            if failure_stage == "response":
                raise TimeoutError(secret_detail)
            pytest.fail("this parameter set must fail before a response")

        def close(self) -> None:
            return None

    monkeypatch.setattr(oauth_module.http.client, "HTTPSConnection", FakeConnection)
    context = ssl.create_default_context()

    with pytest.raises(WordPressComOAuthTokenFailure) as caught:
        SystemWordPressComOAuthTokenTransport().post(
            host=WORDPRESSCOM_OAUTH_TOKEN_HOST,
            port=443,
            path=WORDPRESSCOM_OAUTH_TOKEN_PATH,
            body=b"synthetic-form-body",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            connect_timeout_seconds=5,
            read_timeout_seconds=20,
            tls_context=context,
        )

    assert caught.value.diagnostic_code is diagnostic
    assert secret_detail not in str(caught.value)
    assert secret_detail not in repr(caught.value)


def test_tls_context_failure_has_closed_diagnostic_and_no_transport(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup, _, _, _, _, transport = _setup(repository)
    monkeypatch.setattr(
        oauth_module.ssl,
        "create_default_context",
        lambda: (_ for _ in ()).throw(OSError("synthetic-tls-secret-detail")),
    )

    with pytest.raises(WordPressComOAuthTokenFailure) as caught:
        setup.setup()

    assert (
        caught.value.diagnostic_code
        is WordPressComOAuthTokenDiagnosticCode.TLS_CONTEXT_INVALID
    )
    assert "synthetic-tls-secret-detail" not in repr(caught.value)
    assert transport.calls == []


def test_token_response_without_scope_remains_single_blog_posts_authorization(
    repository: Path,
) -> None:
    payload = {
        "access_token": ACCESS_TOKEN,
        "blog_id": "1703",
        "blog_url": WORDPRESSCOM_REVIEW_DRAFT_TARGET,
        "token_type": "bearer",
    }
    response = WordPressComOAuthHttpResponse(
        status=200,
        content_type="application/json",
        body=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
    )
    setup, _, _, _, _, _ = _setup(
        repository, transport=FakeTokenTransport(response=response)
    )

    receipt = setup.setup()

    assert receipt.scope == "posts"


def test_entropy_opener_listener_and_transport_failures_are_sanitized(
    repository: Path,
) -> None:
    cases = [
        _setup(repository, entropy=FakeEntropy(b"too-short"))[0],
        _setup(repository, opener=FakeOpener(False))[0],
        _setup(
            repository,
            transport=FakeTokenTransport(error=TimeoutError("transport-secret-detail")),
        )[0],
    ]
    for setup in cases:
        with pytest.raises(WordPressComReviewDraftFailure) as caught:
            setup.setup()
        rendered = " ".join((str(caught.value), repr(caught.value), repr(setup)))
        assert "transport-secret-detail" not in rendered
        assert CLIENT_SECRET.decode() not in rendered


@pytest.mark.parametrize(
    "raw",
    [
        (
            f"GET /oauth/wordpresscom/callback?code={AUTHORIZATION_CODE}&state="
            + "A" * 43
            + " HTTP/1.1\r\nHost: 127.0.0.1:18703\r\n"
            "Host: 127.0.0.1:18703\r\n\r\n"
        ).encode(),
        (
            f"GET /oauth/wordpresscom/callback?code={AUTHORIZATION_CODE}&state="
            + "A" * 43
            + " HTTP/1.1\r\nHost: 127.0.0.1:18703\r\n"
            "Transfer-Encoding: chunked\r\n\r\n"
        ).encode(),
        (
            f"GET /oauth/wordpresscom/callback?code={AUTHORIZATION_CODE}&state="
            + "A" * 43
            + " HTTP/1.1\r\nHost: 127.0.0.1:18703\r\n"
            "Content-Length: 1\r\n\r\nx"
        ).encode(),
    ],
)
def test_loopback_parser_rejects_duplicate_host_transfer_and_request_body(
    raw: bytes,
) -> None:
    with pytest.raises(WordPressComReviewDraftFailure):
        oauth_module._parse_loopback_request(
            raw, local_host="127.0.0.1", local_port=18703
        )


def test_token_response_byte_limit_is_closed() -> None:
    with pytest.raises(WordPressComReviewDraftFailure):
        WordPressComOAuthHttpResponse(
            status=200,
            content_type="application/json",
            body=b"x" * 65537,
        )


def test_system_listener_admits_forwarded_ipv4_peer_but_keeps_local_bind_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oauth_module.time, "monotonic", lambda: 1_703.0)
    state = "A" * 43
    raw = (
        f"GET /oauth/wordpresscom/callback?code={AUTHORIZATION_CODE}&state={state} "
        "HTTP/1.1\r\nHost: 127.0.0.1:18703\r\n\r\n"
    ).encode()

    class FakeAcceptedSocket:
        def __init__(self) -> None:
            self.closed = False

        def settimeout(self, timeout: int) -> None:
            assert timeout == 300

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 18703)

        def recv(self, size: int) -> bytes:
            assert size == 2048
            result = raw if not self.closed else b""
            self.closed = True
            return result

        def sendall(self, response: bytes) -> None:
            assert response.startswith(b"HTTP/1.1 200 OK")

        def close(self) -> None:
            pass

    class FakeServerSocket:
        def settimeout(self, timeout: int) -> None:
            assert timeout == 300

        def bind(self, address: tuple[str, int]) -> None:
            assert address == ("127.0.0.1", 18703)

        def listen(self, backlog: int) -> None:
            assert backlog == 1

        def accept(self) -> tuple[FakeAcceptedSocket, tuple[str, int]]:
            return FakeAcceptedSocket(), ("172.24.224.1", 54321)

        def close(self) -> None:
            pass

    monkeypatch.setattr(oauth_module.socket, "socket", lambda *args: FakeServerSocket())
    listener = oauth_module.SystemWordPressComLoopbackListener()
    opener = FakeOpener()

    callback = listener.authorize(
        authorization_url=f"{WORDPRESSCOM_OAUTH_AUTHORIZATION_ENDPOINT}?state={state}",
        opener=opener,
        expected_state=oauth_module.WordPressComOAuthState(state),
        host="127.0.0.1",
        port=18703,
        path="/oauth/wordpresscom/callback",
        timeout_seconds=300,
    )

    assert callback.local_host == "127.0.0.1"
    assert callback.local_port == 18703
    assert callback.host_header == "127.0.0.1:18703"


def test_system_listener_ignores_only_bounded_empty_preconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oauth_module.time, "monotonic", lambda: 1_703.0)
    state = "A" * 43
    valid_raw = (
        f"GET /oauth/wordpresscom/callback?code={AUTHORIZATION_CODE}&state={state} "
        "HTTP/1.1\r\nHost: 127.0.0.1:18703\r\n\r\n"
    ).encode()
    responses: list[bytes] = []

    class FakeAcceptedSocket:
        def __init__(self, raw: bytes) -> None:
            self.raw = raw
            self.read = False

        def settimeout(self, timeout: float) -> None:
            assert timeout == 300

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 18703)

        def recv(self, size: int) -> bytes:
            assert size == 2048
            if self.read:
                return b""
            self.read = True
            return self.raw

        def sendall(self, response: bytes) -> None:
            responses.append(response)

        def close(self) -> None:
            pass

    class FakeServerSocket:
        def __init__(self) -> None:
            self.connections = [
                FakeAcceptedSocket(b""),
                FakeAcceptedSocket(valid_raw),
            ]

        def settimeout(self, timeout: float) -> None:
            assert timeout == 300

        def bind(self, address: tuple[str, int]) -> None:
            assert address == ("127.0.0.1", 18703)

        def listen(self, backlog: int) -> None:
            assert backlog == 1

        def accept(self) -> tuple[FakeAcceptedSocket, tuple[str, int]]:
            return self.connections.pop(0), ("172.24.224.1", 54321)

        def close(self) -> None:
            pass

    server = FakeServerSocket()
    monkeypatch.setattr(oauth_module.socket, "socket", lambda *args: server)
    listener = oauth_module.SystemWordPressComLoopbackListener()
    opener = FakeOpener()

    callback = listener.authorize(
        authorization_url=f"{WORDPRESSCOM_OAUTH_AUTHORIZATION_ENDPOINT}?state={state}",
        opener=opener,
        expected_state=oauth_module.WordPressComOAuthState(state),
        host="127.0.0.1",
        port=18703,
        path="/oauth/wordpresscom/callback",
        timeout_seconds=300,
    )

    assert callback.request_target.endswith(f"state={state}")
    assert len(opener.urls) == 1
    assert len(responses) == 2
    assert responses[0].startswith(b"HTTP/1.1 400 Bad Request")
    assert responses[1].startswith(b"HTTP/1.1 200 OK")


@pytest.mark.parametrize(
    ("raw", "diagnostic"),
    [
        (
            (
                f"POST /oauth/wordpresscom/callback?code={AUTHORIZATION_CODE}&state="
                + "A" * 43
                + " HTTP/1.1\r\nHost: 127.0.0.1:18703\r\n\r\n"
            ).encode(),
            "OAUTH_CALLBACK_METHOD_INVALID",
        ),
        (
            (
                f"GET /wrong?code={AUTHORIZATION_CODE}&state="
                + "A" * 43
                + " HTTP/1.1\r\nHost: 127.0.0.1:18703\r\n\r\n"
            ).encode(),
            "OAUTH_CALLBACK_PATH_INVALID",
        ),
        (
            (
                f"GET /oauth/wordpresscom/callback?code={AUTHORIZATION_CODE}&state="
                + "A" * 43
                + " HTTP/1.1\r\nHost: localhost:18703\r\n\r\n"
            ).encode(),
            "OAUTH_CALLBACK_HOST_INVALID",
        ),
        (
            (
                f"GET /oauth/wordpresscom/callback?code={AUTHORIZATION_CODE}&state="
                + "B" * 43
                + " HTTP/1.1\r\nHost: 127.0.0.1:18703\r\n\r\n"
            ).encode(),
            "OAUTH_CALLBACK_STATE_MISMATCH",
        ),
        (
            (
                "GET /oauth/wordpresscom/callback?error=access_denied&state="
                + "A" * 43
                + " HTTP/1.1\r\nHost: 127.0.0.1:18703\r\n\r\n"
            ).encode(),
            "OAUTH_CALLBACK_PROVIDER_ERROR",
        ),
    ],
)
def test_system_listener_rejects_complete_wrong_callback_once_with_400(
    monkeypatch: pytest.MonkeyPatch,
    raw: bytes,
    diagnostic: str,
) -> None:
    monkeypatch.setattr(oauth_module.time, "monotonic", lambda: 1_703.0)
    responses: list[bytes] = []

    class FakeAcceptedSocket:
        read = False

        def settimeout(self, timeout: float) -> None:
            assert timeout == 300

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 18703)

        def recv(self, size: int) -> bytes:
            assert size == 2048
            if self.read:
                return b""
            self.read = True
            return raw

        def sendall(self, response: bytes) -> None:
            responses.append(response)

        def close(self) -> None:
            pass

    class FakeServerSocket:
        accepts = 0

        def settimeout(self, timeout: float) -> None:
            assert timeout == 300

        def bind(self, address: tuple[str, int]) -> None:
            assert address == ("127.0.0.1", 18703)

        def listen(self, backlog: int) -> None:
            assert backlog == 1

        def accept(self) -> tuple[FakeAcceptedSocket, tuple[str, int]]:
            self.accepts += 1
            if self.accepts != 1:
                pytest.fail("complete invalid callback must not be retried")
            return FakeAcceptedSocket(), ("172.24.224.1", 54321)

        def close(self) -> None:
            pass

    server = FakeServerSocket()
    monkeypatch.setattr(oauth_module.socket, "socket", lambda *args: server)

    with pytest.raises(oauth_module.WordPressComOAuthCallbackFailure) as caught:
        oauth_module.SystemWordPressComLoopbackListener().authorize(
            authorization_url=(
                f"{WORDPRESSCOM_OAUTH_AUTHORIZATION_ENDPOINT}?state={'A' * 43}"
            ),
            opener=FakeOpener(),
            expected_state=oauth_module.WordPressComOAuthState("A" * 43),
            host="127.0.0.1",
            port=18703,
            path="/oauth/wordpresscom/callback",
            timeout_seconds=300,
        )

    assert caught.value.diagnostic_code.value == diagnostic
    assert server.accepts == 1
    assert len(responses) == 1
    assert responses[0].startswith(b"HTTP/1.1 400 Bad Request")
