"""One-attempt, fixed-origin HTTPS adapter for the WordPress operator bridge."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
import http.client
import json
import os
from pathlib import Path
import re
import signal
import ssl
import threading
from typing import Any, Final, NoReturn, Protocol, cast, final, runtime_checkable

from raos.adapters.self_hosted_wordpress_operator_credentials import (
    OwnerPrivateWordPressOperatorCredentialStore,
)
from raos.domain.operations.self_hosted_wordpress_operator import (
    ApplyReceipt,
    OperatorProposal,
    OperatorStatus,
    OperatorThemeStatus,
    ProposalReceipt,
    ThemePackage,
    WORDPRESS_OPERATOR_NAMESPACE,
    WORDPRESS_OPERATOR_YOAST_ARCHIVE_BYTES,
    WORDPRESS_OPERATOR_YOAST_ARCHIVE_SHA256,
    WORDPRESS_OPERATOR_YOAST_VERSION,
    WordPressOperatorChecksumStatus,
    WordPressOperatorFailure,
    WordPressOperatorFailureCode,
    WordPressOperatorOperation,
    WordPressOperatorProposalState,
    WordPressOperatorThemeStateCode,
    WordPressOperatorYoastProfileCode,
    YoastChecksumResult,
    fail_wordpress_operator,
    require_sha256,
)


WORDPRESS_OPERATOR_HOST: Final = "kurashinoshirube.com"
WORDPRESS_OPERATOR_PORT: Final = 443
CONNECT_TIMEOUT_SECONDS: Final = 5
READ_TIMEOUT_SECONDS: Final = 20
MAX_RESPONSE_BYTES: Final = 256 * 1024

_STATUS_PATH: Final = f"{WORDPRESS_OPERATOR_NAMESPACE}/status"
_CHECKSUM_PATH: Final = f"{WORDPRESS_OPERATOR_NAMESPACE}/yoast-checksum"
_PROPOSAL_PATH: Final = f"{WORDPRESS_OPERATOR_NAMESPACE}/proposals"
_CONTENT_TYPE = re.compile(
    r"application/json(?:\s*;\s*charset=(?:utf-8|UTF-8))?\Z", re.ASCII
)
_CONTENT_LENGTH = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)
_UNTRUSTED_ENVIRONMENT: Final = frozenset(
    {
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SSLKEYLOGFILE",
    }
)


def _fail(code: WordPressOperatorFailureCode) -> NoReturn:
    fail_wordpress_operator(code)


def require_clean_wordpress_operator_environment() -> None:
    # http.client does not consume proxy environment variables. Empty TLS
    # variables are inert; reject only values ssl can consume.
    if any(bool(os.environ.get(name)) for name in _UNTRUSTED_ENVIRONMENT):
        _fail(WordPressOperatorFailureCode.TRANSPORT_REFUSED)


class _RequestDeadlineExpired(TimeoutError):
    pass


def _request_deadline_supported() -> None:
    try:
        current_handler = signal.getsignal(signal.SIGALRM)
        current_timer = signal.getitimer(signal.ITIMER_REAL)
    except BaseException:
        _fail(WordPressOperatorFailureCode.TRANSPORT_REFUSED)
    if (
        threading.current_thread() is not threading.main_thread()
        or current_handler not in {signal.SIG_DFL, signal.SIG_IGN}
        or current_timer != (0.0, 0.0)
    ):
        _fail(WordPressOperatorFailureCode.TRANSPORT_REFUSED)


@contextmanager
def _wall_clock_deadline(seconds: int) -> Generator[None]:
    _request_deadline_supported()
    if type(seconds) is not int or not 1 <= seconds <= 60:
        _fail(WordPressOperatorFailureCode.TRANSPORT_REFUSED)
    previous_handler = signal.getsignal(signal.SIGALRM)

    def expire(signum: int, frame: object) -> NoReturn:
        del signum, frame
        raise _RequestDeadlineExpired from None

    try:
        signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)


@runtime_checkable
class WordPressOperatorHttpsResponse(Protocol):
    status: int

    def getheader(self, name: str, default: str | None = None) -> str | None: ...

    def read(self, amount: int = -1) -> bytes: ...


@runtime_checkable
class WordPressOperatorHttpsConnection(Protocol):
    def connect(self) -> None: ...

    def set_read_timeout(self, seconds: int) -> None: ...

    def request(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: dict[str, str],
    ) -> None: ...

    def getresponse(self) -> WordPressOperatorHttpsResponse: ...

    def close(self) -> None: ...


@runtime_checkable
class WordPressOperatorHttpsConnectionFactory(Protocol):
    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> WordPressOperatorHttpsConnection: ...


@final
class _SystemConnection:
    __slots__ = ("_connection",)

    def __init__(self, connection: http.client.HTTPSConnection) -> None:
        self._connection = connection
        self._force_debug_logging_disabled()

    def _force_debug_logging_disabled(self) -> None:
        self._connection.set_debuglevel(0)
        if (
            type(self._connection.debuglevel) is not int
            or self._connection.debuglevel != 0
        ):
            _fail(WordPressOperatorFailureCode.TRANSPORT_REFUSED)

    def connect(self) -> None:
        self._connection.connect()

    def set_read_timeout(self, seconds: int) -> None:
        if self._connection.sock is None:
            raise OSError("TLS socket unavailable")
        self._connection.sock.settimeout(seconds)

    def request(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> None:
        self._force_debug_logging_disabled()
        self._connection.request(method, path, body=body, headers=headers)

    def getresponse(self) -> WordPressOperatorHttpsResponse:
        return cast(WordPressOperatorHttpsResponse, self._connection.getresponse())

    def close(self) -> None:
        self._connection.close()


@final
class SystemWordPressOperatorHttpsConnectionFactory:
    __slots__ = ()

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> WordPressOperatorHttpsConnection:
        if (
            host != WORDPRESS_OPERATOR_HOST
            or port != WORDPRESS_OPERATOR_PORT
            or connect_timeout_seconds != CONNECT_TIMEOUT_SECONDS
            or type(tls_context) is not ssl.SSLContext
            or tls_context.verify_mode != ssl.CERT_REQUIRED
            or not tls_context.check_hostname
        ):
            _fail(WordPressOperatorFailureCode.TRANSPORT_REFUSED)
        connection = http.client.HTTPSConnection(
            host=WORDPRESS_OPERATOR_HOST,
            port=WORDPRESS_OPERATOR_PORT,
            timeout=CONNECT_TIMEOUT_SECONDS,
            context=tls_context,
        )
        connection.set_debuglevel(0)
        if type(connection.debuglevel) is not int or connection.debuglevel != 0:
            _fail(WordPressOperatorFailureCode.TRANSPORT_REFUSED)
        return _SystemConnection(connection)


class _DuplicateKey(ValueError):
    pass


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise _DuplicateKey
        result[key] = value
    return result


def _bounded_body(response: WordPressOperatorHttpsResponse) -> bytes:
    content_encoding = response.getheader("Content-Encoding")
    content_length = response.getheader("Content-Length")
    transfer_encoding = response.getheader("Transfer-Encoding")
    if (
        content_encoding not in {None, "identity"}
        or transfer_encoding not in {None, "chunked"}
        or (transfer_encoding is not None and content_length is not None)
        or response.getheader("Location") is not None
    ):
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    if content_length is not None:
        if _CONTENT_LENGTH.fullmatch(content_length) is None:
            _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
        if int(content_length) > MAX_RESPONSE_BYTES:
            _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    payload = response.read(MAX_RESPONSE_BYTES + 1)
    if type(payload) is not bytes or not 2 <= len(payload) <= MAX_RESPONSE_BYTES:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    if content_length is not None and len(payload) != int(content_length):
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    return payload


def _decode_json(payload: bytes) -> dict[str, object]:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    if type(value) is not dict:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    return cast(dict[str, object], value)


def _operation(value: object) -> WordPressOperatorOperation:
    if type(value) is not str:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    try:
        return WordPressOperatorOperation(value)
    except TypeError, ValueError:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)


def _state(value: object) -> WordPressOperatorProposalState:
    if type(value) is not str:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    try:
        return WordPressOperatorProposalState(value)
    except TypeError, ValueError:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)


def _status_result(value: dict[str, object]) -> OperatorStatus:
    expected_keys = {
        "operator_version",
        "proposal_counts",
        "schema",
        "supported_operations",
        "theme",
        "writes_enabled",
        "yoast_profile_code",
    }
    expected_operations = [item.value for item in WordPressOperatorOperation]
    if (
        set(value) != expected_keys
        or value["schema"] != "RAOS_OPERATOR_STATUS_V1"
        or value["operator_version"] != "1.0.0"
        or value["supported_operations"] != expected_operations
        or type(value["writes_enabled"]) is not bool
        or type(value["proposal_counts"]) is not dict
        or type(value["theme"]) is not dict
        or type(value["yoast_profile_code"]) is not str
    ):
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    raw_counts = cast(dict[object, object], value["proposal_counts"])
    expected_states = tuple(WordPressOperatorProposalState)
    if set(raw_counts) != {state.value for state in expected_states}:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    raw_theme = cast(dict[object, object], value["theme"])
    if (
        set(raw_theme)
        != {
            "active",
            "file_count",
            "installed_version",
            "slug",
            "state_code",
            "tree_sha256",
        }
        or type(raw_theme["state_code"]) is not str
    ):
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    try:
        yoast_profile_code = WordPressOperatorYoastProfileCode(
            value["yoast_profile_code"]
        )
        theme_state_code = WordPressOperatorThemeStateCode(raw_theme["state_code"])
    except TypeError, ValueError:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    return OperatorStatus(
        writes_enabled=value["writes_enabled"],
        yoast_profile_code=yoast_profile_code,
        theme=OperatorThemeStatus(
            slug=cast(str, raw_theme["slug"]),
            installed_version=cast(str | None, raw_theme["installed_version"]),
            active=cast(bool, raw_theme["active"]),
            state_code=theme_state_code,
            file_count=cast(int, raw_theme["file_count"]),
            tree_sha256=cast(str | None, raw_theme["tree_sha256"]),
        ),
        proposal_counts=tuple(
            (state, cast(int, raw_counts[state.value])) for state in expected_states
        ),
    )


def _checksum_result(value: dict[str, object]) -> YoastChecksumResult:
    expected_keys = {
        "checked_file_count",
        "code",
        "expected_archive",
        "mismatch_count",
        "schema",
        "status",
    }
    if (
        set(value) != expected_keys
        or value["schema"] != "RAOS_OPERATOR_CHECKSUM_V1"
        or type(value["expected_archive"]) is not dict
    ):
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    archive = cast(dict[object, object], value["expected_archive"])
    if archive != {
        "byte_length": WORDPRESS_OPERATOR_YOAST_ARCHIVE_BYTES,
        "sha256": WORDPRESS_OPERATOR_YOAST_ARCHIVE_SHA256,
        "version": WORDPRESS_OPERATOR_YOAST_VERSION,
    }:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    if type(value["status"]) is not str:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    try:
        status = WordPressOperatorChecksumStatus(value["status"])
    except TypeError, ValueError:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    return YoastChecksumResult(
        status=status,
        code=cast(str, value["code"]),
        checked_file_count=cast(int, value["checked_file_count"]),
        mismatch_count=cast(int, value["mismatch_count"]),
    )


def _proposal_result(
    value: dict[str, object], expected: OperatorProposal
) -> ProposalReceipt:
    if (
        set(value)
        != {
            "created_at",
            "expires_at",
            "operation",
            "proposal_id",
            "replayed",
            "schema",
            "state",
        }
        or value["schema"] != "RAOS_OPERATOR_PROPOSAL_V1"
    ):
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    receipt = ProposalReceipt(
        proposal_id=cast(str, value["proposal_id"]),
        operation=_operation(value["operation"]),
        state=_state(value["state"]),
        created_at=cast(str, value["created_at"]),
        expires_at=cast(str, value["expires_at"]),
        replayed=cast(bool, value["replayed"]),
    )
    if (
        receipt.proposal_id != expected.proposal_id
        or receipt.operation is not expected.operation
    ):
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    return receipt


def _apply_result(
    value: dict[str, object], *, proposal_id: str, operation: WordPressOperatorOperation
) -> ApplyReceipt:
    if (
        set(value)
        != {
            "operation",
            "proposal_id",
            "replayed",
            "result_code",
            "schema",
            "state",
        }
        or value["schema"] != "RAOS_OPERATOR_APPLY_V1"
    ):
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    receipt = ApplyReceipt(
        proposal_id=cast(str, value["proposal_id"]),
        operation=_operation(value["operation"]),
        state=_state(value["state"]),
        result_code=cast(str, value["result_code"]),
        replayed=cast(bool, value["replayed"]),
    )
    if receipt.proposal_id != proposal_id or receipt.operation is not operation:
        _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
    return receipt


@final
class OfficialSelfHostedWordPressOperatorAdapter:
    """Expose only six fixed operations against one exact HTTPS origin."""

    __slots__ = (
        "_attempt_lock",
        "_attempted",
        "connection_factory",
        "repository_root",
    )

    def __init__(
        self,
        repository_root: object,
        connection_factory: object = SystemWordPressOperatorHttpsConnectionFactory(),
    ) -> None:
        if (
            not isinstance(repository_root, Path)
            or not repository_root.is_absolute()
            or not isinstance(
                connection_factory, WordPressOperatorHttpsConnectionFactory
            )
        ):
            _fail(WordPressOperatorFailureCode.REQUEST_INVALID)
        self.repository_root = repository_root
        self.connection_factory = connection_factory
        self._attempt_lock = threading.Lock()
        self._attempted = False

    def __repr__(self) -> str:
        return "OfficialSelfHostedWordPressOperatorAdapter(<redacted>)"

    def _claim_attempt(self) -> None:
        with self._attempt_lock:
            if self._attempted:
                _fail(WordPressOperatorFailureCode.OPERATION_NOT_ALLOWED)
            self._attempted = True

    def _execute(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        expected_status: int,
        content_type: str | None,
        mutating: bool,
        proposal_id: str | None = None,
        expected_response_etag: str | None = None,
    ) -> dict[str, object]:
        self._claim_attempt()
        require_clean_wordpress_operator_environment()
        _request_deadline_supported()
        credentials = OwnerPrivateWordPressOperatorCredentialStore(
            self.repository_root
        ).read()
        try:
            context = ssl.create_default_context()
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
                _fail(WordPressOperatorFailureCode.TRANSPORT_REFUSED)
            connection = self.connection_factory.open(
                host=WORDPRESS_OPERATOR_HOST,
                port=WORDPRESS_OPERATOR_PORT,
                connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
                tls_context=context,
            )
        except WordPressOperatorFailure:
            raise
        except BaseException:
            _fail(WordPressOperatorFailureCode.TRANSPORT_REFUSED)
        attempted = False
        try:
            with _wall_clock_deadline(CONNECT_TIMEOUT_SECONDS):
                connection.connect()
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Authorization": credentials.authorization_header(),
                "Connection": "close",
                "Content-Length": str(len(body)),
                "Host": WORDPRESS_OPERATOR_HOST,
                "User-Agent": "RAOS-ST-1506-wordpress-operator/1",
            }
            if content_type is not None:
                headers["Content-Type"] = content_type
            if proposal_id is not None:
                require_sha256(proposal_id)
                headers["Idempotency-Key"] = proposal_id
                headers["If-Match"] = f'"{proposal_id}"'
            attempted = True
            with _wall_clock_deadline(READ_TIMEOUT_SECONDS):
                connection.set_read_timeout(READ_TIMEOUT_SECONDS)
                connection.request(method, path, body, headers)
                response = connection.getresponse()
                response_type = response.getheader("Content-Type")
                if (
                    type(response.status) is not int
                    or response.status != expected_status
                    or type(response_type) is not str
                    or _CONTENT_TYPE.fullmatch(response_type) is None
                ):
                    _fail(
                        WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS
                        if mutating
                        else WordPressOperatorFailureCode.RESPONSE_INVALID
                    )
                if (
                    expected_response_etag is not None
                    and response.getheader("ETag")
                    != f'"{require_sha256(expected_response_etag)}"'
                ):
                    _fail(WordPressOperatorFailureCode.RESPONSE_INVALID)
                return _decode_json(_bounded_body(response))
        except WordPressOperatorFailure as failure:
            if (
                attempted
                and mutating
                and failure.code is WordPressOperatorFailureCode.RESPONSE_INVALID
            ):
                _fail(WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS)
            raise
        except BaseException:
            _fail(
                WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS
                if attempted and mutating
                else WordPressOperatorFailureCode.TRANSPORT_REFUSED
            )
        finally:
            try:
                connection.close()
            except BaseException:
                pass

    def status(self) -> OperatorStatus:
        return _status_result(
            self._execute(
                method="GET",
                path=_STATUS_PATH,
                body=b"",
                expected_status=200,
                content_type=None,
                mutating=False,
            )
        )

    def verify_yoast_checksums(self) -> YoastChecksumResult:
        return _checksum_result(
            self._execute(
                method="POST",
                path=_CHECKSUM_PATH,
                body=b"{}",
                expected_status=200,
                content_type="application/json",
                mutating=False,
            )
        )

    def propose(self, proposal: OperatorProposal) -> ProposalReceipt:
        if type(proposal) is not OperatorProposal:
            _fail(WordPressOperatorFailureCode.REQUEST_INVALID)
        response = self._execute(
            method="POST",
            path=_PROPOSAL_PATH,
            body=proposal.canonical_bytes(),
            expected_status=201,
            content_type="application/json",
            mutating=True,
            expected_response_etag=proposal.proposal_id,
        )
        try:
            return _proposal_result(response, proposal)
        except WordPressOperatorFailure:
            _fail(WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS)

    def apply_yoast_profile(self, proposal_id: str) -> ApplyReceipt:
        proposal_id = require_sha256(proposal_id)
        response = self._execute(
            method="POST",
            path=f"{_PROPOSAL_PATH}/{proposal_id}/apply",
            body=b"{}",
            expected_status=200,
            content_type="application/json",
            mutating=True,
            proposal_id=proposal_id,
            expected_response_etag=proposal_id,
        )
        try:
            return _apply_result(
                response,
                proposal_id=proposal_id,
                operation=WordPressOperatorOperation.APPLY_YOAST_PROFILE,
            )
        except WordPressOperatorFailure:
            _fail(WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS)

    def apply_theme_update(self, proposal_id: str, theme: ThemePackage) -> ApplyReceipt:
        proposal_id = require_sha256(proposal_id)
        if type(theme) is not ThemePackage:
            _fail(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
        response = self._execute(
            method="POST",
            path=f"{_PROPOSAL_PATH}/{proposal_id}/apply",
            body=theme.package_bytes,
            expected_status=200,
            content_type="application/zip",
            mutating=True,
            proposal_id=proposal_id,
            expected_response_etag=proposal_id,
        )
        try:
            return _apply_result(
                response,
                proposal_id=proposal_id,
                operation=WordPressOperatorOperation.UPDATE_CHILD_THEME,
            )
        except WordPressOperatorFailure:
            _fail(WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS)


__all__ = [
    "CONNECT_TIMEOUT_SECONDS",
    "MAX_RESPONSE_BYTES",
    "OfficialSelfHostedWordPressOperatorAdapter",
    "READ_TIMEOUT_SECONDS",
    "SystemWordPressOperatorHttpsConnectionFactory",
    "WORDPRESS_OPERATOR_HOST",
    "WORDPRESS_OPERATOR_PORT",
    "WordPressOperatorHttpsConnection",
    "WordPressOperatorHttpsConnectionFactory",
    "WordPressOperatorHttpsResponse",
    "require_clean_wordpress_operator_environment",
]
