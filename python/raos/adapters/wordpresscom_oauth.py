"""Fixed WordPress.com OAuth2 Authorization Code setup infrastructure."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import StrEnum
import hmac
import http.client
import json
import math
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import stat
import subprocess
import time
from typing import (
    Any,
    NoReturn,
    Protocol,
    SupportsIndex,
    cast,
    final,
    runtime_checkable,
)
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from raos.adapters.wordpresscom_review_draft_https import (
    WORDPRESSCOM_ACCESS_TOKEN_ALIAS,
    WordPressComBearerToken,
    require_clean_wordpresscom_tls_environment,
)
from raos.domain.editorial.wordpresscom_review_draft import (
    WORDPRESSCOM_REVIEW_DRAFT_TARGET,
    WordPressComReviewDraftFailure,
    WordPressComReviewDraftFailureCode,
    fail_wordpresscom_review_draft,
)


WORDPRESSCOM_CLIENT_ID_ALIAS = "wordpresscom_oauth_client_id"
WORDPRESSCOM_CLIENT_SECRET_ALIAS = "wordpresscom_oauth_client_secret"
WORDPRESSCOM_OAUTH_SECRET_ROOT = Path(".secrets/wordpresscom-review-draft")
WORDPRESSCOM_OAUTH_AUTHORIZATION_ENDPOINT = (
    "https://public-api.wordpress.com/oauth2/authorize"
)
_POWERSHELL_PATH = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
_POWERSHELL_COMMAND = "$url = [Console]::In.ReadToEnd(); Start-Process -FilePath $url"
_BROWSER_OPEN_TIMEOUT_SECONDS = 10
_MAX_EMPTY_LOOPBACK_PRECONNECTS = 3
_WSL_INTEROP_NAME = re.compile(r"[1-9][0-9]*_interop\Z", re.ASCII)
_WSL_INTEROP_ROOT = Path("/run/WSL")
WORDPRESSCOM_OAUTH_TOKEN_HOST = "public-api.wordpress.com"
WORDPRESSCOM_OAUTH_TOKEN_PATH = "/oauth2/token"
WORDPRESSCOM_OAUTH_REDIRECT_URI = "http://127.0.0.1:18703/oauth/wordpresscom/callback"
WORDPRESSCOM_OAUTH_SCOPE = "posts"
WORDPRESSCOM_OAUTH_BLOG = "kurashierabinote.wordpress.com"
_CALLBACK_HOST = "127.0.0.1"
_CALLBACK_PORT = 18703
_CALLBACK_PATH = "/oauth/wordpresscom/callback"
_CALLBACK_TIMEOUT_SECONDS = 300
_CONNECT_TIMEOUT_SECONDS = 5
_READ_TIMEOUT_SECONDS = 20
_MAX_SECRET_BYTES = 4096
_MAX_CALLBACK_BYTES = 16384
_MAX_TOKEN_RESPONSE_BYTES = 65536
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 10000
_STATE = re.compile(r"[A-Za-z0-9_-]{43}\Z", re.ASCII)
_OPAQUE_VALUE = re.compile(r"[\x21-\x7e]{1,4096}\Z", re.ASCII)
_AUTHORIZATION_CODE = re.compile(r"[\x20-\x7e]{1,2048}\Z", re.ASCII)
_CONTENT_TYPE = re.compile(
    r"application/json(?:\s*;\s*charset=(?:utf-8|UTF-8))?\Z", re.ASCII
)
_PERCENT_INVALID = re.compile(r"%(?![0-9A-Fa-f]{2})", re.ASCII)
_HTTP_HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z", re.ASCII)
_WORDPRESSCOM_TOKEN_BLOG_HTTP_METADATA = f"http://{WORDPRESSCOM_OAUTH_BLOG}"


def _fail(code: WordPressComReviewDraftFailureCode) -> NoReturn:
    fail_wordpresscom_review_draft(code)


class WordPressComOAuthCallbackDiagnosticCode(StrEnum):
    """Closed, value-free category for one failed owner callback."""

    TRANSPORT_EMPTY = "OAUTH_CALLBACK_TRANSPORT_EMPTY"
    TRANSPORT_TRUNCATED = "OAUTH_CALLBACK_TRANSPORT_TRUNCATED"
    REQUEST_SHAPE_INVALID = "OAUTH_CALLBACK_REQUEST_SHAPE_INVALID"
    METHOD_INVALID = "OAUTH_CALLBACK_METHOD_INVALID"
    HOST_INVALID = "OAUTH_CALLBACK_HOST_INVALID"
    LOCAL_INVALID = "OAUTH_CALLBACK_LOCAL_INVALID"
    PATH_INVALID = "OAUTH_CALLBACK_PATH_INVALID"
    QUERY_INVALID = "OAUTH_CALLBACK_QUERY_INVALID"
    QUERY_DUPLICATE = "OAUTH_CALLBACK_QUERY_DUPLICATE"
    PROVIDER_ERROR = "OAUTH_CALLBACK_PROVIDER_ERROR"
    CODE_MISSING = "OAUTH_CALLBACK_CODE_MISSING"
    STATE_MISSING = "OAUTH_CALLBACK_STATE_MISSING"
    STATE_MISMATCH = "OAUTH_CALLBACK_STATE_MISMATCH"
    CODE_SHAPE_INVALID = "OAUTH_CALLBACK_CODE_SHAPE_INVALID"


class WordPressComOAuthCallbackFailure(WordPressComReviewDraftFailure):
    """Generic callback refusal plus one closed non-sensitive category."""

    __slots__ = ("diagnostic_code",)

    def __init__(
        self, diagnostic_code: WordPressComOAuthCallbackDiagnosticCode
    ) -> None:
        if type(diagnostic_code) is not WordPressComOAuthCallbackDiagnosticCode:
            fail_wordpresscom_review_draft(
                WordPressComReviewDraftFailureCode.OAUTH_CALLBACK_INVALID
            )
        self.diagnostic_code = diagnostic_code
        super().__init__(WordPressComReviewDraftFailureCode.OAUTH_CALLBACK_INVALID)


def _fail_callback(code: WordPressComOAuthCallbackDiagnosticCode) -> NoReturn:
    raise WordPressComOAuthCallbackFailure(code) from None


class WordPressComOAuthTokenDiagnosticCode(StrEnum):
    """Closed, value-free category for one failed token exchange."""

    TLS_ENVIRONMENT_INVALID = "OAUTH_TOKEN_TLS_ENVIRONMENT_INVALID"
    TLS_CONTEXT_INVALID = "OAUTH_TOKEN_TLS_CONTEXT_INVALID"
    REQUEST_SETUP_INVALID = "OAUTH_TOKEN_REQUEST_SETUP_INVALID"
    CONNECTION_FAILED = "OAUTH_TOKEN_CONNECTION_FAILED"
    REQUEST_AMBIGUOUS = "OAUTH_TOKEN_REQUEST_AMBIGUOUS"
    RESPONSE_SHAPE_INVALID = "OAUTH_TOKEN_RESPONSE_SHAPE_INVALID"
    HTTP_STATUS_INVALID = "OAUTH_TOKEN_HTTP_STATUS_INVALID"
    CONTENT_TYPE_INVALID = "OAUTH_TOKEN_CONTENT_TYPE_INVALID"
    BODY_SIZE_INVALID = "OAUTH_TOKEN_BODY_SIZE_INVALID"
    JSON_ENCODING_INVALID = "OAUTH_TOKEN_JSON_ENCODING_INVALID"
    JSON_PARSE_INVALID = "OAUTH_TOKEN_JSON_PARSE_INVALID"
    JSON_DUPLICATE_KEY = "OAUTH_TOKEN_JSON_DUPLICATE_KEY"
    JSON_NONFINITE = "OAUTH_TOKEN_JSON_NONFINITE"
    JSON_TREE_INVALID = "OAUTH_TOKEN_JSON_TREE_INVALID"
    PROVIDER_INVALID_CLIENT = "OAUTH_TOKEN_PROVIDER_INVALID_CLIENT"
    PROVIDER_INVALID_GRANT = "OAUTH_TOKEN_PROVIDER_INVALID_GRANT"
    PROVIDER_OTHER_ERROR = "OAUTH_TOKEN_PROVIDER_OTHER_ERROR"
    ACCESS_TOKEN_MISSING = "OAUTH_TOKEN_ACCESS_TOKEN_MISSING"
    ACCESS_TOKEN_SHAPE_INVALID = "OAUTH_TOKEN_ACCESS_TOKEN_SHAPE_INVALID"
    TOKEN_TYPE_INVALID = "OAUTH_TOKEN_TYPE_INVALID"
    BLOG_URL_TYPE_INVALID = "OAUTH_TOKEN_BLOG_URL_TYPE_INVALID"
    BLOG_URL_PARSE_INVALID = "OAUTH_TOKEN_BLOG_URL_PARSE_INVALID"
    BLOG_URL_SCHEME_INVALID = "OAUTH_TOKEN_BLOG_URL_SCHEME_INVALID"
    BLOG_URL_HOST_INVALID = "OAUTH_TOKEN_BLOG_URL_HOST_INVALID"
    BLOG_URL_AUTHORITY_INVALID = "OAUTH_TOKEN_BLOG_URL_AUTHORITY_INVALID"
    BLOG_URL_PATH_INVALID = "OAUTH_TOKEN_BLOG_URL_PATH_INVALID"
    BLOG_URL_QUERY_FRAGMENT_INVALID = "OAUTH_TOKEN_BLOG_URL_QUERY_FRAGMENT_INVALID"
    BLOG_ID_INVALID = "OAUTH_TOKEN_BLOG_ID_INVALID"
    SCOPE_INVALID = "OAUTH_TOKEN_SCOPE_INVALID"


class WordPressComOAuthTokenFailure(WordPressComReviewDraftFailure):
    """Generic token refusal plus one closed non-sensitive category."""

    __slots__ = ("diagnostic_code",)

    def __init__(self, diagnostic_code: WordPressComOAuthTokenDiagnosticCode) -> None:
        if type(diagnostic_code) is not WordPressComOAuthTokenDiagnosticCode:
            fail_wordpresscom_review_draft(
                WordPressComReviewDraftFailureCode.OAUTH_TOKEN_EXCHANGE_INVALID
            )
        self.diagnostic_code = diagnostic_code
        super().__init__(
            WordPressComReviewDraftFailureCode.OAUTH_TOKEN_EXCHANGE_INVALID
        )


def _fail_token(code: WordPressComOAuthTokenDiagnosticCode) -> NoReturn:
    raise WordPressComOAuthTokenFailure(code) from None


class _RedactedOAuthValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-wordpresscom-oauth>)"

    def __str__(self) -> str:
        return "<redacted-wordpresscom-oauth>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("WordPress.com OAuth value serialization is disabled")


@dataclass(frozen=True, slots=True, repr=False)
class WordPressComOAuthClientId(_RedactedOAuthValue):
    _value: bytes

    def __post_init__(self) -> None:
        _validate_opaque_bytes(self._value)

    def _form_value(self) -> str:
        return _decode_opaque(self._value)


@dataclass(frozen=True, slots=True, repr=False)
class WordPressComOAuthClientSecret(_RedactedOAuthValue):
    _value: bytes

    def __post_init__(self) -> None:
        if type(self._value) is not bytes or len(self._value) < 16:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
        _validate_opaque_bytes(self._value)

    def _form_value(self) -> str:
        return _decode_opaque(self._value)


@dataclass(frozen=True, slots=True, repr=False)
class WordPressComOAuthState(_RedactedOAuthValue):
    _value: str

    def __post_init__(self) -> None:
        if type(self._value) is not str or _STATE.fullmatch(self._value) is None:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_AUTHORIZATION_INVALID)

    @classmethod
    def from_entropy(cls, value: object) -> WordPressComOAuthState:
        if type(value) is not bytes or len(value) != 32:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_AUTHORIZATION_INVALID)
        encoded = base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
        return cls(encoded)

    def _query_value(self) -> str:
        return self._value


@dataclass(frozen=True, slots=True, repr=False)
class WordPressComAuthorizationCode(_RedactedOAuthValue):
    _value: str

    def __post_init__(self) -> None:
        if (
            type(self._value) is not str
            or _AUTHORIZATION_CODE.fullmatch(self._value) is None
        ):
            _fail(WordPressComReviewDraftFailureCode.OAUTH_CALLBACK_INVALID)

    def _form_value(self) -> str:
        return self._value


@dataclass(frozen=True, slots=True, repr=False)
class WordPressComLoopbackCallback(_RedactedOAuthValue):
    method: str
    request_target: str
    host_header: str
    local_host: str
    local_port: int

    def __post_init__(self) -> None:
        if (
            type(self.method) is not str
            or type(self.request_target) is not str
            or type(self.host_header) is not str
            or type(self.local_host) is not str
            or type(self.local_port) is not int
        ):
            _fail(WordPressComReviewDraftFailureCode.OAUTH_CALLBACK_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class WordPressComOAuthHttpResponse(_RedactedOAuthValue):
    status: int
    content_type: str
    body: bytes

    def __post_init__(self) -> None:
        if (
            type(self.status) is not int
            or type(self.content_type) is not str
            or type(self.body) is not bytes
        ):
            _fail_token(WordPressComOAuthTokenDiagnosticCode.RESPONSE_SHAPE_INVALID)
        if len(self.body) > _MAX_TOKEN_RESPONSE_BYTES:
            _fail_token(WordPressComOAuthTokenDiagnosticCode.BODY_SIZE_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class WordPressComOAuthSetupReceipt(_RedactedOAuthValue):
    target_origin: str
    scope: str
    access_token_alias: str
    access_token_stored: bool
    publication_authorized: bool

    def __post_init__(self) -> None:
        if (
            self.target_origin != WORDPRESSCOM_REVIEW_DRAFT_TARGET
            or self.scope != WORDPRESSCOM_OAUTH_SCOPE
            or self.access_token_alias != WORDPRESSCOM_ACCESS_TOKEN_ALIAS
            or self.access_token_stored is not True
            or self.publication_authorized is not False
        ):
            _fail(WordPressComReviewDraftFailureCode.OAUTH_TOKEN_EXCHANGE_INVALID)


def _decode_opaque(value: bytes) -> str:
    try:
        return value.decode("ascii", errors="strict")
    except UnicodeError:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)


def _validate_opaque_bytes(value: object) -> None:
    if type(value) is not bytes or not 1 <= len(value) <= _MAX_SECRET_BYTES:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    decoded = _decode_opaque(value)
    if _OPAQUE_VALUE.fullmatch(decoded) is None:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)


def _physical_absolute(path: Path) -> Path:
    if not isinstance(path, Path):
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    return Path(os.path.abspath(path))


def _require_no_symlink_ancestors(path: Path) -> None:
    current = path
    while True:
        try:
            metadata = current.lstat()
        except OSError:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
        if stat.S_ISLNK(metadata.st_mode):
            _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
        if current.parent == current:
            break
        current = current.parent


def _require_private_root(path: Path) -> None:
    _require_no_symlink_ancestors(path)
    try:
        metadata = path.lstat()
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)


def _open_private_regular(path: Path, flags: int, mode: int = 0o600) -> int:
    try:
        descriptor = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), mode)
        metadata = os.fstat(descriptor)
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        os.close(descriptor)
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    return descriptor


def _read_private_value(path: Path) -> bytes:
    _require_no_symlink_ancestors(path.parent)
    descriptor = _open_private_regular(path, os.O_RDONLY)
    try:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_SECRET_BYTES + 1:
                _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
            chunks.append(chunk)
    except WordPressComReviewDraftFailure:
        raise
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    finally:
        os.close(descriptor)
    value = b"".join(chunks)
    if value.endswith(b"\n"):
        value = value[:-1]
    if not value or b"\n" in value or b"\r" in value or b"\x00" in value:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    _validate_opaque_bytes(value)
    return value


@final
class WordPressComOAuthSecretStore:
    """Fixed owner-private files for exactly three approved aliases."""

    __slots__ = ("_root",)

    def __init__(self, *, repository_root: Path) -> None:
        repository = _physical_absolute(repository_root)
        root = repository / WORDPRESSCOM_OAUTH_SECRET_ROOT
        _require_private_root(root)
        self._root = root

    def __repr__(self) -> str:
        return "WordPressComOAuthSecretStore(<redacted-wordpresscom-oauth>)"

    def _path(self, alias: str) -> Path:
        if alias not in {
            WORDPRESSCOM_CLIENT_ID_ALIAS,
            WORDPRESSCOM_CLIENT_SECRET_ALIAS,
            WORDPRESSCOM_ACCESS_TOKEN_ALIAS,
        }:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
        _require_private_root(self._root)
        return self._root / alias

    def read_client_id(self) -> WordPressComOAuthClientId:
        return WordPressComOAuthClientId(
            _read_private_value(self._path(WORDPRESSCOM_CLIENT_ID_ALIAS))
        )

    def read_client_secret(self) -> WordPressComOAuthClientSecret:
        return WordPressComOAuthClientSecret(
            _read_private_value(self._path(WORDPRESSCOM_CLIENT_SECRET_ALIAS))
        )

    def read(self, alias: str) -> WordPressComBearerToken:
        if alias != WORDPRESSCOM_ACCESS_TOKEN_ALIAS:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
        return WordPressComBearerToken(_read_private_value(self._path(alias)))

    def require_access_token_absent(self) -> None:
        path = self._path(WORDPRESSCOM_ACCESS_TOKEN_ALIAS)
        try:
            path.lstat()
        except FileNotFoundError:
            return
        except OSError:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
        _fail(WordPressComReviewDraftFailureCode.OAUTH_TOKEN_EXISTS)

    def store_access_token(self, token: WordPressComBearerToken) -> None:
        if type(token) is not WordPressComBearerToken:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_TOKEN_EXCHANGE_INVALID)
        path = self._path(WORDPRESSCOM_ACCESS_TOKEN_ALIAS)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            descriptor = _open_private_regular(path, flags)
        except WordPressComReviewDraftFailure as error:
            try:
                path.lstat()
            except OSError:
                raise error
            _fail(WordPressComReviewDraftFailureCode.OAUTH_TOKEN_EXISTS)
        data = token._value + b"\n"
        try:
            offset = 0
            while offset < len(data):
                count = os.write(descriptor, data[offset:])
                if count <= 0:
                    _fail(
                        WordPressComReviewDraftFailureCode.OAUTH_TOKEN_EXCHANGE_INVALID
                    )
                offset += count
            os.fsync(descriptor)
        except WordPressComReviewDraftFailure:
            raise
        except OSError:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_TOKEN_EXCHANGE_INVALID)
        finally:
            os.close(descriptor)
        try:
            directory_descriptor = os.open(
                self._root,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except OSError:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_TOKEN_EXCHANGE_INVALID)


@runtime_checkable
class WordPressComEntropySource(Protocol):
    def token_bytes(self, count: int) -> bytes: ...


@runtime_checkable
class WordPressComBrowserOpener(Protocol):
    def open(self, authorization_url: str) -> bool: ...


@runtime_checkable
class WordPressComLoopbackListener(Protocol):
    def authorize(
        self,
        *,
        authorization_url: str,
        opener: WordPressComBrowserOpener,
        expected_state: WordPressComOAuthState,
        host: str,
        port: int,
        path: str,
        timeout_seconds: int,
    ) -> WordPressComLoopbackCallback: ...


@runtime_checkable
class WordPressComOAuthTokenTransport(Protocol):
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
    ) -> WordPressComOAuthHttpResponse: ...


@final
class SystemWordPressComEntropySource:
    __slots__ = ()

    def token_bytes(self, count: int) -> bytes:
        if count != 32:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_AUTHORIZATION_INVALID)
        return secrets.token_bytes(count)


def _validated_wsl_interop(value: object) -> str:
    if type(value) is not str:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_AUTHORIZATION_INVALID)
    path = Path(value)
    try:
        metadata = path.lstat()
        physical = Path(os.path.realpath(path))
        ancestor_metadata = [
            ancestor.lstat()
            for ancestor in (Path("/"), Path("/run"), _WSL_INTEROP_ROOT)
        ]
    except BaseException:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_AUTHORIZATION_INVALID)
    if (
        path.parent != _WSL_INTEROP_ROOT
        or _WSL_INTEROP_NAME.fullmatch(path.name) is None
        or os.fspath(path) != value
        or physical != path
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISSOCK(metadata.st_mode)
        or metadata.st_uid != 0
        or any(
            stat.S_ISLNK(ancestor.st_mode)
            or not stat.S_ISDIR(ancestor.st_mode)
            or ancestor.st_uid != 0
            or ancestor.st_mode & 0o022 != 0
            for ancestor in ancestor_metadata
        )
    ):
        _fail(WordPressComReviewDraftFailureCode.OAUTH_AUTHORIZATION_INVALID)
    return value


@final
class SystemWordPressComBrowserOpener:
    __slots__ = ()

    def open(self, authorization_url: str) -> bool:
        if type(authorization_url) is not str:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_AUTHORIZATION_INVALID)
        try:
            parsed = urlsplit(authorization_url)
            executable = _POWERSHELL_PATH
            executable_metadata = executable.lstat()
            executable_physical = Path(os.path.realpath(executable))
            interop = _validated_wsl_interop(os.environ.get("WSL_INTEROP"))
            query_pairs = parse_qsl(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
                encoding="ascii",
                errors="strict",
            )
        except BaseException:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_AUTHORIZATION_INVALID)
        if (
            not authorization_url.startswith(
                WORDPRESSCOM_OAUTH_AUTHORIZATION_ENDPOINT + "?"
            )
            or parsed.scheme != "https"
            or parsed.hostname != "public-api.wordpress.com"
            or parsed.port not in {None, 443}
            or parsed.path != "/oauth2/authorize"
            or not parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
            or [key for key, _ in query_pairs]
            != ["blog", "client_id", "redirect_uri", "response_type", "scope", "state"]
            or query_pairs[0][1] != WORDPRESSCOM_OAUTH_BLOG
            or _OPAQUE_VALUE.fullmatch(query_pairs[1][1]) is None
            or query_pairs[2][1] != WORDPRESSCOM_OAUTH_REDIRECT_URI
            or query_pairs[3][1] != "code"
            or query_pairs[4][1] != WORDPRESSCOM_OAUTH_SCOPE
            or re.fullmatch(r"[A-Za-z0-9_-]{43}", query_pairs[5][1], re.ASCII) is None
            or authorization_url
            != WORDPRESSCOM_OAUTH_AUTHORIZATION_ENDPOINT
            + "?"
            + urlencode(
                query_pairs,
                doseq=False,
                safe="",
                encoding="ascii",
                errors="strict",
                quote_via=quote,
            )
            or executable_physical != executable
            or stat.S_ISLNK(executable_metadata.st_mode)
            or not stat.S_ISREG(executable_metadata.st_mode)
            or executable_metadata.st_uid != os.geteuid()
            or executable_metadata.st_mode & 0o111 == 0
        ):
            _fail(WordPressComReviewDraftFailureCode.OAUTH_AUTHORIZATION_INVALID)
        try:
            completed = subprocess.run(
                [
                    os.fspath(executable),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    _POWERSHELL_COMMAND,
                ],
                input=authorization_url.encode("ascii", errors="strict"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin", "WSL_INTEROP": interop},
                close_fds=True,
                timeout=_BROWSER_OPEN_TIMEOUT_SECONDS,
                check=False,
            )
            return completed.returncode == 0
        except BaseException:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_AUTHORIZATION_INVALID)


def _send_loopback_result(connection: socket.socket, *, success: bool) -> None:
    message = (
        "Authorization received. Return to the terminal."
        if success
        else "Invalid callback."
    )
    body = message.encode("ascii")
    status = b"200 OK" if success else b"400 Bad Request"
    response = (
        b"HTTP/1.1 "
        + status
        + b"\r\nContent-Type: text/plain; charset=utf-8\r\nConnection: close\r\n"
        + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        + body
    )
    try:
        connection.sendall(response)
    except OSError:
        pass


def _parse_loopback_request(
    raw: bytes, *, local_host: str, local_port: int
) -> WordPressComLoopbackCallback:
    if type(raw) is not bytes or not raw:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.TRANSPORT_EMPTY)
    if not 4 <= len(raw) <= _MAX_CALLBACK_BYTES or not raw.endswith(b"\r\n\r\n"):
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.TRANSPORT_TRUNCATED)
    if type(local_host) is not str or type(local_port) is not int:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.LOCAL_INVALID)
    try:
        lines = raw[:-4].decode("ascii", errors="strict").split("\r\n")
    except UnicodeError:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.REQUEST_SHAPE_INVALID)
    request_line = lines[0].split(" ") if lines else []
    if len(request_line) != 3 or request_line[2] != "HTTP/1.1":
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.REQUEST_SHAPE_INVALID)
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            _fail_callback(
                WordPressComOAuthCallbackDiagnosticCode.REQUEST_SHAPE_INVALID
            )
        name, value = line.split(":", 1)
        lowered = name.lower()
        stripped = value.strip(" \t")
        if (
            _HTTP_HEADER_NAME.fullmatch(name) is None
            or lowered in headers
            or not stripped
            or any(ord(character) < 32 and character != "\t" for character in value)
            or any(ord(character) == 127 for character in value)
        ):
            _fail_callback(
                WordPressComOAuthCallbackDiagnosticCode.REQUEST_SHAPE_INVALID
            )
        headers[lowered] = stripped
    if (
        "host" not in headers
        or "transfer-encoding" in headers
        or ("content-length" in headers and headers["content-length"] != "0")
    ):
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.REQUEST_SHAPE_INVALID)
    return WordPressComLoopbackCallback(
        method=request_line[0],
        request_target=request_line[1],
        host_header=headers["host"],
        local_host=local_host,
        local_port=local_port,
    )


@final
class SystemWordPressComLoopbackListener:
    """Bind only the approved IPv4 loopback callback and receive one GET."""

    __slots__ = ()

    def authorize(
        self,
        *,
        authorization_url: str,
        opener: WordPressComBrowserOpener,
        expected_state: WordPressComOAuthState,
        host: str,
        port: int,
        path: str,
        timeout_seconds: int,
    ) -> WordPressComLoopbackCallback:
        if (
            host != _CALLBACK_HOST
            or port != _CALLBACK_PORT
            or path != _CALLBACK_PATH
            or timeout_seconds != _CALLBACK_TIMEOUT_SECONDS
            or not isinstance(opener, WordPressComBrowserOpener)
            or type(expected_state) is not WordPressComOAuthState
        ):
            _fail(WordPressComReviewDraftFailureCode.OAUTH_CALLBACK_INVALID)
        server: socket.socket | None = None
        connection: socket.socket | None = None
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.bind((host, port))
            server.listen(1)
            deadline = time.monotonic() + timeout_seconds
            if opener.open(authorization_url) is not True:
                _fail(WordPressComReviewDraftFailureCode.OAUTH_AUTHORIZATION_INVALID)
            empty_preconnects = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _fail(WordPressComReviewDraftFailureCode.OAUTH_CALLBACK_INVALID)
                server.settimeout(remaining)
                connection, peer = server.accept()
                success = False
                try:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        _fail(WordPressComReviewDraftFailureCode.OAUTH_CALLBACK_INVALID)
                    connection.settimeout(remaining)
                    local = connection.getsockname()
                    if (
                        type(peer) is not tuple
                        or len(peer) < 2
                        or type(peer[0]) is not str
                        or not peer[0]
                        or type(peer[1]) is not int
                        or not 1 <= peer[1] <= 65535
                        or type(local) is not tuple
                        or len(local) < 2
                        or local[0] != host
                        or local[1] != port
                    ):
                        _fail_callback(
                            WordPressComOAuthCallbackDiagnosticCode.LOCAL_INVALID
                        )
                    raw = bytearray()
                    while b"\r\n\r\n" not in raw:
                        chunk = connection.recv(2048)
                        if not chunk:
                            break
                        raw.extend(chunk)
                        if len(raw) > _MAX_CALLBACK_BYTES:
                            _fail(
                                WordPressComReviewDraftFailureCode.OAUTH_CALLBACK_INVALID
                            )
                    if not raw:
                        empty_preconnects += 1
                        if empty_preconnects > _MAX_EMPTY_LOOPBACK_PRECONNECTS:
                            _fail_callback(
                                WordPressComOAuthCallbackDiagnosticCode.TRANSPORT_EMPTY
                            )
                        continue
                    callback = _parse_loopback_request(
                        bytes(raw),
                        local_host=local[0],
                        local_port=local[1],
                    )
                    _callback_code(callback, expected_state)
                    success = True
                    return callback
                finally:
                    _send_loopback_result(connection, success=success)
                    try:
                        connection.close()
                    except OSError:
                        pass
                    connection = None
        except WordPressComReviewDraftFailure:
            raise
        except BaseException:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_CALLBACK_INVALID)
        finally:
            if connection is not None:
                _send_loopback_result(connection, success=False)
                try:
                    connection.close()
                except OSError:
                    pass
            if server is not None:
                try:
                    server.close()
                except OSError:
                    pass


@final
class SystemWordPressComOAuthTokenTransport:
    """One direct stdlib TLS POST with no proxy, redirect, fallback, or retry."""

    __slots__ = ()

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
        if (
            host != WORDPRESSCOM_OAUTH_TOKEN_HOST
            or port != 443
            or path != WORDPRESSCOM_OAUTH_TOKEN_PATH
            or connect_timeout_seconds != _CONNECT_TIMEOUT_SECONDS
            or read_timeout_seconds != _READ_TIMEOUT_SECONDS
            or type(body) is not bytes
            or not 1 <= len(body) <= 16384
            or headers
            != {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            or type(tls_context) is not ssl.SSLContext
            or tls_context.verify_mode != ssl.CERT_REQUIRED
            or not tls_context.check_hostname
        ):
            _fail_token(WordPressComOAuthTokenDiagnosticCode.REQUEST_SETUP_INVALID)
        connection: http.client.HTTPSConnection | None = None
        request_attempted = False
        try:
            connection = http.client.HTTPSConnection(
                host=host,
                port=port,
                timeout=connect_timeout_seconds,
                context=tls_context,
            )
            connection.connect()
            if connection.sock is None:
                _fail_token(WordPressComOAuthTokenDiagnosticCode.CONNECTION_FAILED)
            connection.sock.settimeout(read_timeout_seconds)
            request_attempted = True
            connection.request("POST", path, body=body, headers=headers)
            response = connection.getresponse()
            response_body = response.read(_MAX_TOKEN_RESPONSE_BYTES + 1)
            if len(response_body) > _MAX_TOKEN_RESPONSE_BYTES:
                _fail_token(WordPressComOAuthTokenDiagnosticCode.BODY_SIZE_INVALID)
            return WordPressComOAuthHttpResponse(
                status=response.status,
                content_type=response.getheader("Content-Type", ""),
                body=response_body,
            )
        except WordPressComOAuthTokenFailure:
            raise
        except BaseException:
            _fail_token(
                WordPressComOAuthTokenDiagnosticCode.REQUEST_AMBIGUOUS
                if request_attempted
                else WordPressComOAuthTokenDiagnosticCode.CONNECTION_FAILED
            )
        finally:
            if connection is not None:
                try:
                    connection.close()
                except BaseException:
                    pass


def _authorization_url(
    client_id: WordPressComOAuthClientId, state: WordPressComOAuthState
) -> str:
    query = urlencode(
        [
            ("blog", WORDPRESSCOM_OAUTH_BLOG),
            ("client_id", client_id._form_value()),
            ("redirect_uri", WORDPRESSCOM_OAUTH_REDIRECT_URI),
            ("response_type", "code"),
            ("scope", WORDPRESSCOM_OAUTH_SCOPE),
            ("state", state._query_value()),
        ],
        doseq=False,
        safe="",
        encoding="ascii",
        errors="strict",
        quote_via=quote,
    )
    return f"{WORDPRESSCOM_OAUTH_AUTHORIZATION_ENDPOINT}?{query}"


def _callback_code(
    callback: object, expected_state: WordPressComOAuthState
) -> WordPressComAuthorizationCode:
    if type(callback) is not WordPressComLoopbackCallback:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.REQUEST_SHAPE_INVALID)
    if callback.method != "GET":
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.METHOD_INVALID)
    if callback.host_header != f"{_CALLBACK_HOST}:{_CALLBACK_PORT}":
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.HOST_INVALID)
    if callback.local_host != _CALLBACK_HOST or callback.local_port != _CALLBACK_PORT:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.LOCAL_INVALID)
    if (
        len(callback.request_target) > _MAX_CALLBACK_BYTES
        or "#" in callback.request_target
        or _PERCENT_INVALID.search(callback.request_target) is not None
    ):
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.QUERY_INVALID)
    try:
        parsed = urlsplit(callback.request_target)
    except ValueError:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.QUERY_INVALID)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.PATH_INVALID)
    if parsed.path != _CALLBACK_PATH:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.PATH_INVALID)
    if not parsed.query:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.QUERY_INVALID)
    try:
        pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            separator="&",
            encoding="ascii",
            errors="strict",
        )
    except UnicodeError, ValueError:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.QUERY_INVALID)
    members: dict[str, str] = {}
    for key, value in pairs:
        if key in members:
            _fail_callback(WordPressComOAuthCallbackDiagnosticCode.QUERY_DUPLICATE)
        members[key] = value
    if "error" in members:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.PROVIDER_ERROR)
    if "code" not in members:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.CODE_MISSING)
    if "state" not in members:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.STATE_MISSING)
    if set(members) != {"code", "state"}:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.QUERY_INVALID)
    if not hmac.compare_digest(members["state"], expected_state._query_value()):
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.STATE_MISMATCH)
    if _AUTHORIZATION_CODE.fullmatch(members["code"]) is None:
        _fail_callback(WordPressComOAuthCallbackDiagnosticCode.CODE_SHAPE_INVALID)
    return WordPressComAuthorizationCode(members["code"])


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail_token(WordPressComOAuthTokenDiagnosticCode.JSON_DUPLICATE_KEY)
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _fail_token(WordPressComOAuthTokenDiagnosticCode.JSON_NONFINITE)


def _validate_json_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            _fail_token(WordPressComOAuthTokenDiagnosticCode.JSON_TREE_INVALID)
        if current is None or type(current) in {str, bool, int}:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                _fail_token(WordPressComOAuthTokenDiagnosticCode.JSON_NONFINITE)
            continue
        if type(current) is list:
            pending.extend((item, depth + 1) for item in cast(list[object], current))
            continue
        if type(current) is dict:
            pending.extend(
                (item, depth + 1) for item in cast(dict[str, object], current).values()
            )
            continue
        _fail_token(WordPressComOAuthTokenDiagnosticCode.JSON_TREE_INVALID)


def _require_exact_token_blog_url(value: object) -> None:
    if type(value) is not str or not 1 <= len(value) <= 2048:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.BLOG_URL_TYPE_INVALID)
    if value in {
        WORDPRESSCOM_REVIEW_DRAFT_TARGET,
        f"{WORDPRESSCOM_REVIEW_DRAFT_TARGET}/",
        _WORDPRESSCOM_TOKEN_BLOG_HTTP_METADATA,
        f"{_WORDPRESSCOM_TOKEN_BLOG_HTTP_METADATA}/",
    }:
        return
    if "\\" in value:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.BLOG_URL_PARSE_INVALID)
    try:
        parsed = urlsplit(value)
        parsed_port = parsed.port
    except ValueError:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.BLOG_URL_PARSE_INVALID)
    if parsed.scheme not in {"http", "https"} or not value.startswith(
        ("http://", "https://")
    ):
        _fail_token(WordPressComOAuthTokenDiagnosticCode.BLOG_URL_SCHEME_INVALID)
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed_port is not None
    ):
        _fail_token(WordPressComOAuthTokenDiagnosticCode.BLOG_URL_AUTHORITY_INVALID)
    if (
        parsed.hostname != WORDPRESSCOM_OAUTH_BLOG
        or parsed.netloc != WORDPRESSCOM_OAUTH_BLOG
    ):
        _fail_token(WordPressComOAuthTokenDiagnosticCode.BLOG_URL_HOST_INVALID)
    if "?" in value or "#" in value or parsed.query or parsed.fragment:
        _fail_token(
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_QUERY_FRAGMENT_INVALID
        )
    if parsed.path not in {"", "/"}:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.BLOG_URL_PATH_INVALID)
    _fail_token(WordPressComOAuthTokenDiagnosticCode.BLOG_URL_PARSE_INVALID)


def _token_from_response(response: object) -> WordPressComBearerToken:
    if type(response) is not WordPressComOAuthHttpResponse:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.RESPONSE_SHAPE_INVALID)
    if _CONTENT_TYPE.fullmatch(response.content_type) is None:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.CONTENT_TYPE_INVALID)
    if not 2 <= len(response.body) <= _MAX_TOKEN_RESPONSE_BYTES:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.BODY_SIZE_INVALID)
    try:
        decoded = response.body.decode("utf-8", errors="strict")
    except UnicodeError:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.JSON_ENCODING_INVALID)
    try:
        payload = json.loads(
            decoded,
            object_pairs_hook=_json_pairs,
            parse_constant=_reject_constant,
        )
    except WordPressComOAuthTokenFailure:
        raise
    except RecursionError:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.JSON_TREE_INVALID)
    except ValueError:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.JSON_PARSE_INVALID)
    if type(payload) is not dict:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.JSON_TREE_INVALID)
    _validate_json_tree(payload)
    mapping = cast(dict[str, object], payload)
    if "error" in mapping:
        provider_error = mapping["error"]
        if provider_error == "invalid_client":
            _fail_token(WordPressComOAuthTokenDiagnosticCode.PROVIDER_INVALID_CLIENT)
        if provider_error == "invalid_grant":
            _fail_token(WordPressComOAuthTokenDiagnosticCode.PROVIDER_INVALID_GRANT)
        _fail_token(WordPressComOAuthTokenDiagnosticCode.PROVIDER_OTHER_ERROR)
    if response.status != 200:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.HTTP_STATUS_INVALID)
    if "access_token" not in mapping:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.ACCESS_TOKEN_MISSING)
    token = mapping.get("access_token")
    blog_id = mapping.get("blog_id")
    scope = mapping.get("scope")
    valid_blog_id = bool(
        (type(blog_id) is int and 1 <= blog_id <= (1 << 63) - 1)
        or (
            type(blog_id) is str
            and re.fullmatch(r"[1-9][0-9]{0,18}", blog_id, re.ASCII) is not None
            and int(blog_id) <= (1 << 63) - 1
        )
    )
    if (
        type(token) is not str
        or _OPAQUE_VALUE.fullmatch(token) is None
        or len(token) < 16
    ):
        _fail_token(WordPressComOAuthTokenDiagnosticCode.ACCESS_TOKEN_SHAPE_INVALID)
    if mapping.get("token_type") != "bearer":
        _fail_token(WordPressComOAuthTokenDiagnosticCode.TOKEN_TYPE_INVALID)
    _require_exact_token_blog_url(mapping.get("blog_url"))
    if not valid_blog_id:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.BLOG_ID_INVALID)
    if scope is not None and scope != WORDPRESSCOM_OAUTH_SCOPE:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.SCOPE_INVALID)
    return WordPressComBearerToken(token.encode("ascii", errors="strict"))


def _require_clean_token_tls_environment() -> None:
    try:
        require_clean_wordpresscom_tls_environment()
    except BaseException:
        _fail_token(WordPressComOAuthTokenDiagnosticCode.TLS_ENVIRONMENT_INVALID)


@final
class WordPressComOAuthSetup:
    """Run one fixed Authorization Code setup and exclusively persist its token."""

    __slots__ = ("_entropy", "_listener", "_opener", "_store", "_transport")

    def __init__(
        self,
        *,
        store: WordPressComOAuthSecretStore,
        entropy: WordPressComEntropySource,
        opener: WordPressComBrowserOpener,
        listener: WordPressComLoopbackListener,
        transport: WordPressComOAuthTokenTransport,
    ) -> None:
        if (
            type(store) is not WordPressComOAuthSecretStore
            or not isinstance(entropy, WordPressComEntropySource)
            or not isinstance(opener, WordPressComBrowserOpener)
            or not isinstance(listener, WordPressComLoopbackListener)
            or not isinstance(transport, WordPressComOAuthTokenTransport)
        ):
            _fail(WordPressComReviewDraftFailureCode.OAUTH_AUTHORIZATION_INVALID)
        self._store = store
        self._entropy = entropy
        self._opener = opener
        self._listener = listener
        self._transport = transport

    def __repr__(self) -> str:
        return "WordPressComOAuthSetup(<redacted-wordpresscom-oauth>)"

    def setup(self) -> WordPressComOAuthSetupReceipt:
        _require_clean_token_tls_environment()
        self._store.require_access_token_absent()
        client_id = self._store.read_client_id()
        client_secret = self._store.read_client_secret()
        try:
            state = WordPressComOAuthState.from_entropy(self._entropy.token_bytes(32))
        except WordPressComReviewDraftFailure:
            raise
        except BaseException:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_AUTHORIZATION_INVALID)
        authorization_url = _authorization_url(client_id, state)
        try:
            callback = self._listener.authorize(
                authorization_url=authorization_url,
                opener=self._opener,
                expected_state=state,
                host=_CALLBACK_HOST,
                port=_CALLBACK_PORT,
                path=_CALLBACK_PATH,
                timeout_seconds=_CALLBACK_TIMEOUT_SECONDS,
            )
        except WordPressComReviewDraftFailure:
            raise
        except BaseException:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_CALLBACK_INVALID)
        code = _callback_code(callback, state)
        try:
            form_body = urlencode(
                [
                    ("client_id", client_id._form_value()),
                    ("client_secret", client_secret._form_value()),
                    ("code", code._form_value()),
                    ("grant_type", "authorization_code"),
                    ("redirect_uri", WORDPRESSCOM_OAUTH_REDIRECT_URI),
                ],
                doseq=False,
                safe="",
                encoding="ascii",
                errors="strict",
                quote_via=quote,
            ).encode("ascii")
        except WordPressComReviewDraftFailure:
            raise
        except BaseException:
            _fail_token(WordPressComOAuthTokenDiagnosticCode.REQUEST_SETUP_INVALID)
        _require_clean_token_tls_environment()
        try:
            context = ssl.create_default_context()
            if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
                _fail_token(WordPressComOAuthTokenDiagnosticCode.TLS_CONTEXT_INVALID)
        except WordPressComOAuthTokenFailure:
            raise
        except BaseException:
            _fail_token(WordPressComOAuthTokenDiagnosticCode.TLS_CONTEXT_INVALID)
        try:
            response = self._transport.post(
                host=WORDPRESSCOM_OAUTH_TOKEN_HOST,
                port=443,
                path=WORDPRESSCOM_OAUTH_TOKEN_PATH,
                body=form_body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                connect_timeout_seconds=_CONNECT_TIMEOUT_SECONDS,
                read_timeout_seconds=_READ_TIMEOUT_SECONDS,
                tls_context=context,
            )
        except WordPressComOAuthTokenFailure:
            raise
        except BaseException:
            _fail_token(WordPressComOAuthTokenDiagnosticCode.REQUEST_AMBIGUOUS)
        token = _token_from_response(response)
        self._store.store_access_token(token)
        return WordPressComOAuthSetupReceipt(
            target_origin=WORDPRESSCOM_REVIEW_DRAFT_TARGET,
            scope=WORDPRESSCOM_OAUTH_SCOPE,
            access_token_alias=WORDPRESSCOM_ACCESS_TOKEN_ALIAS,
            access_token_stored=True,
            publication_authorized=False,
        )


__all__ = [
    "SystemWordPressComBrowserOpener",
    "SystemWordPressComEntropySource",
    "SystemWordPressComLoopbackListener",
    "SystemWordPressComOAuthTokenTransport",
    "WORDPRESSCOM_ACCESS_TOKEN_ALIAS",
    "WORDPRESSCOM_CLIENT_ID_ALIAS",
    "WORDPRESSCOM_CLIENT_SECRET_ALIAS",
    "WORDPRESSCOM_OAUTH_AUTHORIZATION_ENDPOINT",
    "WORDPRESSCOM_OAUTH_BLOG",
    "WORDPRESSCOM_OAUTH_REDIRECT_URI",
    "WORDPRESSCOM_OAUTH_SCOPE",
    "WORDPRESSCOM_OAUTH_SECRET_ROOT",
    "WORDPRESSCOM_OAUTH_TOKEN_HOST",
    "WORDPRESSCOM_OAUTH_TOKEN_PATH",
    "WordPressComAuthorizationCode",
    "WordPressComBrowserOpener",
    "WordPressComEntropySource",
    "WordPressComLoopbackCallback",
    "WordPressComLoopbackListener",
    "WordPressComOAuthClientId",
    "WordPressComOAuthClientSecret",
    "WordPressComOAuthCallbackDiagnosticCode",
    "WordPressComOAuthCallbackFailure",
    "WordPressComOAuthHttpResponse",
    "WordPressComOAuthSecretStore",
    "WordPressComOAuthSetup",
    "WordPressComOAuthSetupReceipt",
    "WordPressComOAuthState",
    "WordPressComOAuthTokenDiagnosticCode",
    "WordPressComOAuthTokenFailure",
    "WordPressComOAuthTokenTransport",
]
