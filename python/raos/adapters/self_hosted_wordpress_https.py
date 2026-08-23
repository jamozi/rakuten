"""Fixed-origin one-attempt HTTPS adapter for self-hosted WordPress drafts."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
import hashlib
import http.client
import os
from pathlib import Path
import re
import signal
import ssl
import threading
from typing import NoReturn, Protocol, cast, final, runtime_checkable

from raos.adapters.self_hosted_wordpress_credentials import (
    OwnerPrivateSelfHostedWordPressCredentialStore,
)
from raos.adapters.self_hosted_wordpress_rest import (
    SelfHostedWordPressRecoveryRequestBuilder,
    SelfHostedWordPressRestRequestBuilder,
)
from raos.domain.editorial.market_learning_pilot import MarketLearningPilotFailure
from raos.domain.editorial.self_hosted_wordpress import (
    SelfHostedWordPressDisposition,
    SelfHostedWordPressDraft,
    SelfHostedWordPressDraftReceipt,
    SelfHostedWordPressFailure,
    SelfHostedWordPressFailureCode,
    SelfHostedWordPressOperation,
    SelfHostedWordPressRecoveryObservation,
    fail_self_hosted_wordpress,
)


SELF_HOSTED_WORDPRESS_HOST = "kurashinoshirube.com"
SELF_HOSTED_WORDPRESS_PORT = 443
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 20
MAX_RESPONSE_BYTES = 4_000_000

_CONTENT_TYPE = re.compile(
    r"application/json(?:\s*;\s*charset=(?:utf-8|UTF-8))?\Z", re.ASCII
)
_UNTRUSTED_ENVIRONMENT = frozenset(
    {
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
)


def _fail(code: SelfHostedWordPressFailureCode) -> NoReturn:
    fail_self_hosted_wordpress(code)


def require_clean_self_hosted_wordpress_environment() -> None:
    if any(name in os.environ for name in _UNTRUSTED_ENVIRONMENT):
        _fail(SelfHostedWordPressFailureCode.TRANSPORT_REFUSED)


class _RequestDeadlineExpired(TimeoutError):
    pass


def _request_deadline_supported() -> None:
    try:
        current_handler = signal.getsignal(signal.SIGALRM)
        current_timer = signal.getitimer(signal.ITIMER_REAL)
    except BaseException:
        _fail(SelfHostedWordPressFailureCode.TRANSPORT_REFUSED)
    if (
        threading.current_thread() is not threading.main_thread()
        or current_handler not in {signal.SIG_DFL, signal.SIG_IGN}
        or current_timer != (0.0, 0.0)
    ):
        _fail(SelfHostedWordPressFailureCode.TRANSPORT_REFUSED)


@contextmanager
def _wall_clock_deadline(seconds: float) -> Generator[None]:
    _request_deadline_supported()
    if type(seconds) not in {int, float} or not 0 < seconds <= 60:
        _fail(SelfHostedWordPressFailureCode.TRANSPORT_REFUSED)
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


@contextmanager
def _connect_deadline() -> Generator[None]:
    """Bound DNS, TCP connect, and TLS negotiation before any request."""

    with _wall_clock_deadline(CONNECT_TIMEOUT_SECONDS):
        yield


@contextmanager
def _request_deadline() -> Generator[None]:
    """Bound the complete request/header/body exchange, including slow drip."""

    with _wall_clock_deadline(READ_TIMEOUT_SECONDS):
        yield


@runtime_checkable
class SelfHostedWordPressHttpsResponse(Protocol):
    status: int

    def getheader(self, name: str, default: str | None = None) -> str | None: ...

    def read(self, amount: int = -1) -> bytes: ...


@runtime_checkable
class SelfHostedWordPressHttpsConnection(Protocol):
    def connect(self) -> None: ...

    def set_read_timeout(self, seconds: int) -> None: ...

    def request(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: dict[str, str],
    ) -> None: ...

    def getresponse(self) -> SelfHostedWordPressHttpsResponse: ...

    def close(self) -> None: ...


@runtime_checkable
class SelfHostedWordPressHttpsConnectionFactory(Protocol):
    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> SelfHostedWordPressHttpsConnection: ...


@final
class _SystemConnection:
    __slots__ = ("_connection",)

    def __init__(self, connection: http.client.HTTPSConnection) -> None:
        self._connection = connection

    def connect(self) -> None:
        self._connection.connect()

    def set_read_timeout(self, seconds: int) -> None:
        if self._connection.sock is None:
            raise OSError("TLS socket unavailable")
        self._connection.sock.settimeout(seconds)

    def request(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: dict[str, str],
    ) -> None:
        self._connection.request(method, path, body=body, headers=headers)

    def getresponse(self) -> SelfHostedWordPressHttpsResponse:
        return cast(SelfHostedWordPressHttpsResponse, self._connection.getresponse())

    def close(self) -> None:
        self._connection.close()


@final
class SystemSelfHostedWordPressHttpsConnectionFactory:
    __slots__ = ()

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> SelfHostedWordPressHttpsConnection:
        if (
            host != SELF_HOSTED_WORDPRESS_HOST
            or port != SELF_HOSTED_WORDPRESS_PORT
            or connect_timeout_seconds != CONNECT_TIMEOUT_SECONDS
            or type(tls_context) is not ssl.SSLContext
            or tls_context.verify_mode != ssl.CERT_REQUIRED
            or not tls_context.check_hostname
        ):
            _fail(SelfHostedWordPressFailureCode.TRANSPORT_REFUSED)
        return _SystemConnection(
            http.client.HTTPSConnection(
                host=host,
                port=port,
                timeout=connect_timeout_seconds,
                context=tls_context,
            )
        )


def _bounded_body(
    response: SelfHostedWordPressHttpsResponse,
    *,
    failure_code: SelfHostedWordPressFailureCode = (
        SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS
    ),
) -> bytes:
    content_encoding = response.getheader("Content-Encoding")
    content_length = response.getheader("Content-Length")
    transfer_encoding = response.getheader("Transfer-Encoding")
    if content_encoding not in {None, "identity"}:
        _fail(failure_code)
    if transfer_encoding not in {None, "chunked"} or (
        transfer_encoding is not None and content_length is not None
    ):
        _fail(failure_code)
    if content_length is not None:
        if re.fullmatch(r"(?:0|[1-9][0-9]*)", content_length, re.ASCII) is None:
            _fail(failure_code)
        if int(content_length) > MAX_RESPONSE_BYTES:
            _fail(failure_code)
    payload = response.read(MAX_RESPONSE_BYTES + 1)
    if type(payload) is not bytes or not 2 <= len(payload) <= MAX_RESPONSE_BYTES:
        _fail(failure_code)
    if content_length is not None and len(payload) != int(content_length):
        _fail(failure_code)
    return payload


def _recovery_collection_headers(
    response: SelfHostedWordPressHttpsResponse,
    *,
    result_count: int,
) -> None:
    total = response.getheader("X-WP-Total")
    pages = response.getheader("X-WP-TotalPages")
    if (
        type(result_count) is not int
        or result_count not in {0, 1}
        or type(total) is not str
        or type(pages) is not str
        or re.fullmatch(r"(?:0|[1-9][0-9]*)", total, re.ASCII) is None
        or re.fullmatch(r"(?:0|[1-9][0-9]*)", pages, re.ASCII) is None
        or int(total) != result_count
        or int(pages) != (0 if result_count == 0 else 1)
        or response.getheader("Location") is not None
        or response.getheader("Link") is not None
    ):
        _fail(SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN)


@final
class OfficialSelfHostedWordPressRecoveryProbeAdapter:
    """Perform one authenticated fixed collection GET and no mutation."""

    __slots__ = (
        "_attempt_lock",
        "_attempted",
        "connection_factory",
        "repository_root",
    )

    def __init__(
        self,
        repository_root: object,
        connection_factory: object = (
            SystemSelfHostedWordPressHttpsConnectionFactory()
        ),
    ) -> None:
        if (
            not isinstance(repository_root, Path)
            or not repository_root.is_absolute()
            or not isinstance(
                connection_factory, SelfHostedWordPressHttpsConnectionFactory
            )
        ):
            _fail(SelfHostedWordPressFailureCode.RECOVERY_NOT_AVAILABLE)
        self.repository_root = repository_root
        self.connection_factory = connection_factory
        self._attempt_lock = threading.Lock()
        self._attempted = False

    def __repr__(self) -> str:
        return "OfficialSelfHostedWordPressRecoveryProbeAdapter(<redacted>)"

    def observe(
        self, candidate: SelfHostedWordPressDraft
    ) -> SelfHostedWordPressRecoveryObservation:
        if (
            type(candidate) is not SelfHostedWordPressDraft
            or candidate.operation is not SelfHostedWordPressOperation.CREATE_DRAFT
        ):
            _fail(SelfHostedWordPressFailureCode.RECOVERY_NOT_AVAILABLE)
        with self._attempt_lock:
            if self._attempted:
                _fail(SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED)
            self._attempted = True
        require_clean_self_hosted_wordpress_environment()
        _request_deadline_supported()
        builder = SelfHostedWordPressRecoveryRequestBuilder()
        path = builder.build_path(candidate)
        credentials = OwnerPrivateSelfHostedWordPressCredentialStore(
            self.repository_root
        ).read()
        try:
            context = ssl.create_default_context()
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
                _fail(SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN)
            connection = self.connection_factory.open(
                host=SELF_HOSTED_WORDPRESS_HOST,
                port=SELF_HOSTED_WORDPRESS_PORT,
                connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
                tls_context=context,
            )
        except SelfHostedWordPressFailure:
            raise
        except BaseException:
            _fail(SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN)
        try:
            with _connect_deadline():
                connection.connect()
            with _request_deadline():
                connection.set_read_timeout(READ_TIMEOUT_SECONDS)
                connection.request(
                    "GET",
                    path,
                    b"",
                    {
                        "Accept": "application/json",
                        "Authorization": credentials.authorization_header(),
                        "Connection": "close",
                        "Content-Length": "0",
                        "Host": SELF_HOSTED_WORDPRESS_HOST,
                        "User-Agent": "RAOS-ST-1703-owner-local-recovery/1",
                    },
                )
                response = connection.getresponse()
                content_type = response.getheader("Content-Type")
                if (
                    type(response.status) is not int
                    or response.status != 200
                    or type(content_type) is not str
                    or _CONTENT_TYPE.fullmatch(content_type) is None
                ):
                    _fail(SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN)
                response_body = _bounded_body(
                    response,
                    failure_code=(
                        SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN
                    ),
                )
                observation = builder.validate_response(
                    candidate=candidate,
                    path=path,
                    body=response_body,
                )
                result_count = 0 if observation.draft_id is None else 1
                _recovery_collection_headers(response, result_count=result_count)
                return observation
        except SelfHostedWordPressFailure:
            raise
        except BaseException:
            _fail(SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN)
        finally:
            try:
                connection.close()
            except BaseException:
                pass


@final
class OfficialSelfHostedWordPressDraftAdapter:
    """Use Basic auth for exactly one fixed-origin draft POST attempt."""

    __slots__ = (
        "_attempt_lock",
        "_attempted",
        "connection_factory",
        "repository_root",
    )

    def __init__(
        self,
        repository_root: object,
        connection_factory: object = (
            SystemSelfHostedWordPressHttpsConnectionFactory()
        ),
    ) -> None:
        if (
            not isinstance(repository_root, Path)
            or not repository_root.is_absolute()
            or not isinstance(
                connection_factory, SelfHostedWordPressHttpsConnectionFactory
            )
        ):
            _fail(SelfHostedWordPressFailureCode.REQUEST_INVALID)
        self.repository_root = repository_root
        self.connection_factory = connection_factory
        self._attempt_lock = threading.Lock()
        self._attempted = False

    def __repr__(self) -> str:
        return "OfficialSelfHostedWordPressDraftAdapter(<redacted>)"

    def attempt(
        self, candidate: SelfHostedWordPressDraft
    ) -> SelfHostedWordPressDraftReceipt:
        if type(candidate) is not SelfHostedWordPressDraft:
            _fail(SelfHostedWordPressFailureCode.REQUEST_INVALID)
        if candidate.operation is not SelfHostedWordPressOperation.CREATE_DRAFT:
            _fail(SelfHostedWordPressFailureCode.OPERATION_NOT_ALLOWED)
        with self._attempt_lock:
            if self._attempted:
                _fail(SelfHostedWordPressFailureCode.OPERATION_NOT_ALLOWED)
            self._attempted = True
        require_clean_self_hosted_wordpress_environment()
        _request_deadline_supported()
        try:
            builder = SelfHostedWordPressRestRequestBuilder()
            request = builder.build_create(
                candidate=candidate,
                credential_secret_alias="wordpress_application_password",
            )
        except SelfHostedWordPressFailure:
            raise
        except MarketLearningPilotFailure:
            _fail(SelfHostedWordPressFailureCode.REQUEST_INVALID)
        credentials = OwnerPrivateSelfHostedWordPressCredentialStore(
            self.repository_root
        ).read()
        try:
            body = request.body_json.encode("utf-8", errors="strict")
            context = ssl.create_default_context()
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
                _fail(SelfHostedWordPressFailureCode.TRANSPORT_REFUSED)
            connection = self.connection_factory.open(
                host=SELF_HOSTED_WORDPRESS_HOST,
                port=SELF_HOSTED_WORDPRESS_PORT,
                connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
                tls_context=context,
            )
        except SelfHostedWordPressFailure:
            raise
        except BaseException:
            _fail(SelfHostedWordPressFailureCode.TRANSPORT_REFUSED)
        attempted = False
        try:
            with _connect_deadline():
                connection.connect()
            attempted = True
            with _request_deadline():
                connection.set_read_timeout(READ_TIMEOUT_SECONDS)
                connection.request(
                    request.method,
                    request.path,
                    body,
                    {
                        "Accept": "application/json",
                        "Authorization": credentials.authorization_header(),
                        "Connection": "close",
                        "Content-Length": str(len(body)),
                        "Content-Type": "application/json",
                        "Host": SELF_HOSTED_WORDPRESS_HOST,
                        "User-Agent": "RAOS-ST-1703-owner-local/1",
                    },
                )
                response = connection.getresponse()
                content_type = response.getheader("Content-Type")
                if (
                    type(response.status) is not int
                    or response.status != request.expected_http_status
                    or type(content_type) is not str
                    or _CONTENT_TYPE.fullmatch(content_type) is None
                ):
                    _fail(SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS)
                response_body = _bounded_body(response)
                try:
                    metadata = builder.validate_response(
                        request=request,
                        http_status=response.status,
                        body=response_body,
                    )
                except MarketLearningPilotFailure:
                    _fail(SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS)
                return SelfHostedWordPressDraftReceipt(
                    draft_id=metadata.draft_id,
                    operation=candidate.operation,
                    disposition=SelfHostedWordPressDisposition.CREATED,
                    status=metadata.status,
                    content_sha256=candidate.content_sha256,
                    operation_sha256=candidate.operation_sha256,
                    response_sha256=hashlib.sha256(response_body).hexdigest(),
                )
        except SelfHostedWordPressFailure:
            raise
        except BaseException:
            _fail(
                SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS
                if attempted
                else SelfHostedWordPressFailureCode.TRANSPORT_REFUSED
            )
        finally:
            try:
                connection.close()
            except BaseException:
                pass


__all__ = [
    "CONNECT_TIMEOUT_SECONDS",
    "MAX_RESPONSE_BYTES",
    "OfficialSelfHostedWordPressDraftAdapter",
    "OfficialSelfHostedWordPressRecoveryProbeAdapter",
    "READ_TIMEOUT_SECONDS",
    "SELF_HOSTED_WORDPRESS_HOST",
    "SELF_HOSTED_WORDPRESS_PORT",
    "SelfHostedWordPressHttpsConnection",
    "SelfHostedWordPressHttpsConnectionFactory",
    "SelfHostedWordPressHttpsResponse",
    "SystemSelfHostedWordPressHttpsConnectionFactory",
    "require_clean_self_hosted_wordpress_environment",
]
