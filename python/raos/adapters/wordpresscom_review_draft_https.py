"""Fixed-authority HTTPS adapter for the approved WordPress.com review copy."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import http.client
import json
import math
import os
import re
import ssl
from typing import (
    Any,
    NoReturn,
    Protocol,
    SupportsIndex,
    cast,
    final,
    runtime_checkable,
)
from urllib.parse import quote_plus, urlencode, urlsplit

from raos.domain.editorial.wordpresscom_review_draft import (
    ReviewDraftDisposition,
    WORDPRESSCOM_REVIEW_DRAFT_API_PATH,
    WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY,
    WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS,
    WORDPRESSCOM_REVIEW_DRAFT_NUMERIC_SITE_ID,
    WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA,
    WORDPRESSCOM_REVIEW_DRAFT_STATUS,
    WORDPRESSCOM_REVIEW_DRAFT_TARGET,
    WordPressComReviewDraft,
    WordPressComReviewDraftFailure,
    WordPressComReviewDraftFailureCode,
    WordPressComReviewDraftReceipt,
    fail_wordpresscom_review_draft,
    require_exact_wordpresscom_review_draft,
)
from raos.ports.wordpresscom_review_draft_journal import (
    WordPressComReviewDraftAttemptPort,
)


WORDPRESSCOM_ACCESS_TOKEN_ALIAS = "wordpresscom_oauth_access_token"
_HOST = "public-api.wordpress.com"
_TARGET_HOST = "kurashierabinote.wordpress.com"
_PORT = 443
_PREFLIGHT_PATH = "/rest/v1.1/sites/256699520/posts?context=edit&number=1&fields=ID"
_SITE_ID_DECIMAL = "256699520"
_CONNECT_TIMEOUT_SECONDS = 5
_READ_TIMEOUT_SECONDS = 20
_MAX_REQUEST_BYTES = 1_100_000
_MAX_RESPONSE_BYTES = 4_000_000
_MAX_PREFLIGHT_RESPONSE_BYTES = 65_536
_MAX_JSON_DEPTH = 64
_MAX_JSON_NODES = 100_000
_MAX_TOKEN_BYTES = 4096
_CONTENT_TYPE = re.compile(
    r"application/json(?:[ \t]*;[ \t]*charset=(?:utf-8|UTF-8))?\Z", re.ASCII
)
_TLS_OVERRIDE_ENVIRONMENT = frozenset(
    {"SSL_CERT_DIR", "SSL_CERT_FILE", "SSLKEYLOGFILE"}
)


def _fail(code: WordPressComReviewDraftFailureCode) -> NoReturn:
    fail_wordpresscom_review_draft(code)


def require_clean_wordpresscom_tls_environment() -> None:
    """Reject ambient OpenSSL trust and TLS-key logging overrides."""

    if any(name in os.environ for name in _TLS_OVERRIDE_ENVIRONMENT):
        _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)


class _RedactedHttpsValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-wordpresscom-https>)"

    def __str__(self) -> str:
        return "<redacted-wordpresscom-https>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("WordPress.com HTTPS value serialization is disabled")


@dataclass(frozen=True, slots=True, repr=False)
class WordPressComBearerToken(_RedactedHttpsValue):
    """Opaque token returned only by the owner-private secret reader."""

    _value: bytes

    def __post_init__(self) -> None:
        if (
            type(self._value) is not bytes
            or not 16 <= len(self._value) <= _MAX_TOKEN_BYTES
            or any(byte < 0x21 or byte > 0x7E for byte in self._value)
        ):
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)

    def _authorization_header(self) -> str:
        try:
            return "Bearer " + self._value.decode("ascii", errors="strict")
        except UnicodeError:
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)


@runtime_checkable
class WordPressComAccessTokenReader(Protocol):
    """Read one fixed secret alias without accepting token values as arguments."""

    def read(self, alias: str) -> WordPressComBearerToken: ...


@runtime_checkable
class WordPressComHttpsResponse(Protocol):
    status: int

    def getheader(self, name: str, default: str | None = None) -> str | None: ...

    def read(self, amount: int | None = None) -> bytes: ...


@runtime_checkable
class WordPressComHttpsConnection(Protocol):
    def connect(self) -> None: ...

    def set_read_timeout(self, seconds: int) -> None: ...

    def request(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: dict[str, str],
    ) -> None: ...

    def getresponse(self) -> WordPressComHttpsResponse: ...

    def close(self) -> None: ...


@runtime_checkable
class WordPressComHttpsConnectionFactory(Protocol):
    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> WordPressComHttpsConnection: ...


@final
class _SystemHttpsConnection:
    __slots__ = ("_connection",)

    def __init__(self, connection: http.client.HTTPSConnection) -> None:
        self._connection = connection

    def connect(self) -> None:
        self._connection.connect()

    def set_read_timeout(self, seconds: int) -> None:
        sock = self._connection.sock
        if sock is None:
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
        sock.settimeout(seconds)

    def request(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: dict[str, str],
    ) -> None:
        self._connection.request(method, path, body=body, headers=headers)

    def getresponse(self) -> WordPressComHttpsResponse:
        return cast(WordPressComHttpsResponse, self._connection.getresponse())

    def close(self) -> None:
        self._connection.close()


@final
class SystemWordPressComHttpsConnectionFactory:
    """Create one direct stdlib TLS connection; proxy discovery is absent."""

    __slots__ = ()

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> WordPressComHttpsConnection:
        if (
            host != _HOST
            or port != _PORT
            or connect_timeout_seconds != _CONNECT_TIMEOUT_SECONDS
            or type(tls_context) is not ssl.SSLContext
            or tls_context.verify_mode != ssl.CERT_REQUIRED
            or not tls_context.check_hostname
        ):
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
        return _SystemHttpsConnection(
            http.client.HTTPSConnection(
                host=host,
                port=port,
                timeout=connect_timeout_seconds,
                context=tls_context,
            )
        )


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)


def _preflight_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
        result[key] = value
    return result


def _reject_preflight_constant(value: str) -> NoReturn:
    del value
    _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)


def _validate_json_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
        if current is None or type(current) in {str, bool, int}:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
            continue
        if type(current) is list:
            pending.extend((item, depth + 1) for item in cast(list[object], current))
            continue
        if type(current) is dict:
            pending.extend(
                (item, depth + 1) for item in cast(dict[str, object], current).values()
            )
            continue
        _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)


def _validate_preflight_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
        if current is None or type(current) in {str, bool, int}:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
            continue
        if type(current) is list:
            pending.extend((item, depth + 1) for item in cast(list[object], current))
            continue
        if type(current) is dict:
            pending.extend(
                (item, depth + 1) for item in cast(dict[str, object], current).values()
            )
            continue
        _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)


def _validate_edit_context_preflight(value: object) -> None:
    if type(value) is not dict:
        _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
    mapping = cast(dict[str, object], value)
    if set(mapping) != {"found", "meta", "posts"}:
        _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
    found = mapping["found"]
    meta = mapping["meta"]
    posts = mapping["posts"]
    if (
        type(found) is not int
        or found < 0
        or type(meta) is not dict
        or type(posts) is not list
        or len(posts) > 1
    ):
        _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
    for item in cast(list[object], posts):
        if type(item) is not dict or set(cast(dict[str, object], item)) != {"ID"}:
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
        draft_id = cast(dict[str, object], item)["ID"]
        if type(draft_id) is not int or not 1 <= draft_id <= (1 << 63) - 1:
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)


def _read_bounded(
    response: WordPressComHttpsResponse,
    *,
    limit: int,
    failure_code: WordPressComReviewDraftFailureCode,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(65536, limit + 1 - total))
        if type(chunk) is not bytes:
            _fail(failure_code)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            _fail(failure_code)
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_link(value: object) -> None:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 4096
        or not value.isascii()
        or any(ord(character) <= 32 or ord(character) == 127 for character in value)
    ):
        _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
    if (
        parsed.scheme != "https"
        or parsed.hostname != _TARGET_HOST
        or parsed.netloc != _TARGET_HOST
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/")
        or "#" in value
        or "\\" in value
        or not value.startswith(f"https://{_TARGET_HOST}/")
    ):
        _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)


def _is_exact_site_id(value: object) -> bool:
    return (
        type(value) is int and value == WORDPRESSCOM_REVIEW_DRAFT_NUMERIC_SITE_ID
    ) or (type(value) is str and value == _SITE_ID_DECIMAL)


@final
class OfficialWordPressComReviewDraftAdapter:
    """Execute one fixed v1.1 POST for one immutable review-draft candidate."""

    __slots__ = ("_connection_factory", "_token_reader")

    def __init__(
        self,
        *,
        token_reader: WordPressComAccessTokenReader,
        connection_factory: WordPressComHttpsConnectionFactory,
    ) -> None:
        if not isinstance(
            token_reader, WordPressComAccessTokenReader
        ) or not isinstance(connection_factory, WordPressComHttpsConnectionFactory):
            _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)
        self._token_reader = token_reader
        self._connection_factory = connection_factory

    def __repr__(self) -> str:
        return "OfficialWordPressComReviewDraftAdapter(<redacted-wordpresscom-https>)"

    def require_create_capability(self, candidate: WordPressComReviewDraft) -> None:
        """Verify the exact v1.1 create capability without mutating WordPress."""

        require_exact_wordpresscom_review_draft(candidate)
        require_clean_wordpresscom_tls_environment()
        try:
            token = self._token_reader.read(WORDPRESSCOM_ACCESS_TOKEN_ALIAS)
        except BaseException:
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
        if type(token) is not WordPressComBearerToken:
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
        context = ssl.create_default_context()
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
        connection: WordPressComHttpsConnection | None = None
        try:
            connection = self._connection_factory.open(
                host=_HOST,
                port=_PORT,
                connect_timeout_seconds=_CONNECT_TIMEOUT_SECONDS,
                tls_context=context,
            )
            if not isinstance(connection, WordPressComHttpsConnection):
                _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
            connection.connect()
            connection.set_read_timeout(_READ_TIMEOUT_SECONDS)
            connection.request(
                "GET",
                _PREFLIGHT_PATH,
                b"",
                {
                    "Accept": "application/json",
                    "Authorization": token._authorization_header(),
                },
            )
            response = connection.getresponse()
            if not isinstance(response, WordPressComHttpsResponse):
                _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
            body = _read_bounded(
                response,
                limit=_MAX_PREFLIGHT_RESPONSE_BYTES,
                failure_code=WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID,
            )
            content_type = response.getheader("Content-Type")
            if (
                type(response.status) is not int
                or response.status != 200
                or type(body) is not bytes
                or not 2 <= len(body) <= _MAX_PREFLIGHT_RESPONSE_BYTES
                or type(content_type) is not str
                or _CONTENT_TYPE.fullmatch(content_type) is None
            ):
                _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
            try:
                payload = json.loads(
                    body.decode("utf-8", errors="strict"),
                    object_pairs_hook=_preflight_json_pairs,
                    parse_constant=_reject_preflight_constant,
                )
            except UnicodeError, ValueError, RecursionError:
                _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
            _validate_preflight_tree(payload)
            _validate_edit_context_preflight(payload)
        except WordPressComReviewDraftFailure:
            raise
        except BaseException:
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
        finally:
            if connection is not None:
                try:
                    connection.close()
                except BaseException:
                    pass

    def attempt_create_review_draft(
        self, candidate: WordPressComReviewDraft
    ) -> WordPressComReviewDraftReceipt:
        require_exact_wordpresscom_review_draft(candidate)
        require_clean_wordpresscom_tls_environment()
        try:
            body = urlencode(
                (
                    ("title", candidate.title),
                    ("content", candidate.rendered_content),
                    ("status", WORDPRESSCOM_REVIEW_DRAFT_STATUS),
                    ("publicize", "false"),
                ),
                doseq=False,
                safe="",
                encoding="utf-8",
                errors="strict",
                quote_via=quote_plus,
            ).encode("ascii", errors="strict")
        except TypeError, ValueError, UnicodeError:
            _fail(WordPressComReviewDraftFailureCode.CANDIDATE_INVALID)
        if not 2 <= len(body) <= _MAX_REQUEST_BYTES:
            _fail(WordPressComReviewDraftFailureCode.CANDIDATE_INVALID)

        try:
            token = self._token_reader.read(WORDPRESSCOM_ACCESS_TOKEN_ALIAS)
        except BaseException:
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
        if type(token) is not WordPressComBearerToken:
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
        headers = {
            "Accept": "application/json",
            "Authorization": token._authorization_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        context = ssl.create_default_context()
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)

        connection: WordPressComHttpsConnection | None = None
        draft_id: int
        post_attempted = False
        response_body: bytes
        try:
            connection = self._connection_factory.open(
                host=_HOST,
                port=_PORT,
                connect_timeout_seconds=_CONNECT_TIMEOUT_SECONDS,
                tls_context=context,
            )
            if not isinstance(connection, WordPressComHttpsConnection):
                _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
            connection.connect()
            connection.set_read_timeout(_READ_TIMEOUT_SECONDS)
            post_attempted = True
            connection.request(
                "POST", WORDPRESSCOM_REVIEW_DRAFT_API_PATH, body, headers
            )
            response = connection.getresponse()
            if not isinstance(response, WordPressComHttpsResponse):
                _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
            response_body = _read_bounded(
                response,
                limit=_MAX_RESPONSE_BYTES,
                failure_code=WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS,
            )
            content_type = response.getheader("Content-Type")
            if (
                type(response.status) is not int
                or response.status != 200
                or type(content_type) is not str
                or _CONTENT_TYPE.fullmatch(content_type) is None
                or not 2 <= len(response_body) <= _MAX_RESPONSE_BYTES
            ):
                _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
            try:
                payload = json.loads(
                    response_body.decode("utf-8", errors="strict"),
                    object_pairs_hook=_json_pairs,
                    parse_constant=_reject_constant,
                )
            except UnicodeError, ValueError, RecursionError:
                _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
            if type(payload) is not dict:
                _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
            _validate_json_tree(payload)
            mapping = cast(dict[str, object], payload)
            draft_id_value = mapping.get("ID")
            if (
                type(draft_id_value) is not int
                or not 1 <= draft_id_value <= (1 << 63) - 1
                or not _is_exact_site_id(mapping.get("site_ID"))
                or mapping.get("status") != WORDPRESSCOM_REVIEW_DRAFT_STATUS
                or mapping.get("type") != "post"
                or (
                    "publicize_URLs" in mapping
                    and (
                        type(mapping["publicize_URLs"]) is not list
                        or mapping["publicize_URLs"] != []
                    )
                )
            ):
                _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
            draft_id = draft_id_value
            _validate_link(mapping.get("URL"))
        except WordPressComReviewDraftFailure:
            raise
        except BaseException:
            _fail(
                WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS
                if post_attempted
                else WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID
            )
        finally:
            if connection is not None:
                try:
                    connection.close()
                except BaseException:
                    pass

        return WordPressComReviewDraftReceipt(
            schema=WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA,
            authority=WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY,
            network_status=WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS,
            target_origin=WORDPRESSCOM_REVIEW_DRAFT_TARGET,
            draft_id=draft_id,
            status=WORDPRESSCOM_REVIEW_DRAFT_STATUS,
            operation_binding_sha256=candidate.operation_binding_sha256,
            content_sha256=candidate.content_sha256,
            response_body_sha256=hashlib.sha256(response_body).hexdigest(),
            disposition=ReviewDraftDisposition.CREATED,
            publication_authorized=False,
            production_eligible=False,
        )


__all__ = [
    "OfficialWordPressComReviewDraftAdapter",
    "SystemWordPressComHttpsConnectionFactory",
    "WORDPRESSCOM_ACCESS_TOKEN_ALIAS",
    "WordPressComAccessTokenReader",
    "WordPressComBearerToken",
    "WordPressComHttpsConnection",
    "WordPressComHttpsConnectionFactory",
    "WordPressComHttpsResponse",
    "WordPressComReviewDraftAttemptPort",
    "require_clean_wordpresscom_tls_environment",
]
