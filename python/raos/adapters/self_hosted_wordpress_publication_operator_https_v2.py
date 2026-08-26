"""One-attempt fixed-origin HTTPS adapter for publication operator v2."""

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
    WordPressOperatorFailure,
)
from raos.domain.operations.self_hosted_wordpress_publication_operator_v2 import (
    PUBLICATION_OPERATOR_NAMESPACE,
    PUBLICATION_OPERATOR_RESULT_CODE,
    PUBLICATION_OPERATOR_VERSION,
    PublicationApplyReceipt,
    PublicationOperatorFailure,
    PublicationOperatorFailureCode,
    PublicationOperatorOperation,
    PublicationOperatorStatus,
    PublicationProposal,
    PublicationProposalReceipt,
    PublicationProposalState,
    fail_publication_operator,
    require_sha256,
)


PUBLICATION_OPERATOR_HOST: Final = "kurashinoshirube.com"
PUBLICATION_OPERATOR_PORT: Final = 443
CONNECT_TIMEOUT_SECONDS: Final = 5
READ_TIMEOUT_SECONDS: Final = 20
MAX_RESPONSE_BYTES: Final = 256 * 1024

_STATUS_PATH: Final = f"{PUBLICATION_OPERATOR_NAMESPACE}/status"
_PROPOSAL_PATH: Final = f"{PUBLICATION_OPERATOR_NAMESPACE}/proposals"
_PROPOSAL_SCHEMA: Final = "RAOS_ST1704_PUBLICATION_OPERATOR_PROPOSAL_V2"
_APPLY_SCHEMA: Final = "RAOS_ST1704_PUBLICATION_OPERATOR_APPLY_V2"
_STATUS_SCHEMA: Final = "RAOS_ST1704_PUBLICATION_OPERATOR_STATUS_V2"
_CONTENT_TYPE = re.compile(
    r"application/json(?:\s*;\s*charset=(?:utf-8|UTF-8))?\Z", re.ASCII
)
_CONTENT_LENGTH = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)
_ERROR_MESSAGE: Final = "The ST-1704 publication operator rejected the request."
_NOT_CREATED_AT: Final = "1970-01-01T00:00:00Z"
_NOT_CREATED_EXPIRES_AT: Final = "1970-01-01T00:15:00Z"
_DETERMINISTIC_CREATE_REJECTIONS: Final = frozenset(
    {
        ("raos_st1704_content_type_invalid", 400),
        ("raos_st1704_proposal_invalid", 400),
        ("raos_st1704_article_not_bound", 409),
        ("raos_st1704_before_state_invalid", 409),
        ("raos_st1704_capacity_check_failed", 500),
        ("raos_st1704_category_not_exact", 409),
        ("raos_st1704_draft_not_exact", 409),
        ("raos_st1704_meta_state_invalid", 409),
        ("raos_st1704_meta_state_unreadable", 409),
        ("raos_st1704_public_slug_not_unique", 409),
        ("raos_st1704_publication_busy", 409),
        ("raos_st1704_publication_lock_lost", 500),
        ("raos_st1704_proposal_lookup_failed", 500),
        ("raos_st1704_request_not_bound", 409),
        ("raos_st1704_runtime_origin_invalid", 409),
        ("raos_st1704_snapshot_not_bound", 409),
        ("raos_st1704_state_hash_failed", 500),
        ("raos_st1704_taxonomy_state_invalid", 409),
        ("raos_st1704_taxonomy_state_unreadable", 409),
        ("raos_st1704_unresolved_proposal_exists", 409),
        ("raos_st1704_transaction_unavailable", 500),
        ("raos_st1704_proposal_capacity_reached", 429),
        ("raos_st1704_writes_disabled", 503),
    }
)
_UNTRUSTED_ENVIRONMENT: Final = frozenset(
    {"SSL_CERT_DIR", "SSL_CERT_FILE", "SSLKEYLOGFILE"}
)


def _fail(code: PublicationOperatorFailureCode) -> NoReturn:
    fail_publication_operator(code)


def require_clean_publication_operator_environment() -> None:
    if any(bool(os.environ.get(name)) for name in _UNTRUSTED_ENVIRONMENT):
        _fail(PublicationOperatorFailureCode.TRANSPORT_REFUSED)


class _RequestDeadlineExpired(TimeoutError):
    pass


def _request_deadline_supported() -> None:
    try:
        current_handler = signal.getsignal(signal.SIGALRM)
        current_timer = signal.getitimer(signal.ITIMER_REAL)
    except BaseException:
        _fail(PublicationOperatorFailureCode.TRANSPORT_REFUSED)
    if (
        threading.current_thread() is not threading.main_thread()
        or current_handler not in {signal.SIG_DFL, signal.SIG_IGN}
        or current_timer != (0.0, 0.0)
    ):
        _fail(PublicationOperatorFailureCode.TRANSPORT_REFUSED)


@contextmanager
def _wall_clock_deadline(seconds: int) -> Generator[None]:
    _request_deadline_supported()
    if type(seconds) is not int or not 1 <= seconds <= 60:
        _fail(PublicationOperatorFailureCode.TRANSPORT_REFUSED)
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
class PublicationOperatorHttpsResponse(Protocol):
    status: int

    def getheader(self, name: str, default: str | None = None) -> str | None: ...

    def read(self, amount: int = -1) -> bytes: ...


@runtime_checkable
class PublicationOperatorHttpsConnection(Protocol):
    def connect(self) -> None: ...

    def set_read_timeout(self, seconds: int) -> None: ...

    def request(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> None: ...

    def getresponse(self) -> PublicationOperatorHttpsResponse: ...

    def close(self) -> None: ...


@runtime_checkable
class PublicationOperatorHttpsConnectionFactory(Protocol):
    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> PublicationOperatorHttpsConnection: ...


@final
class _SystemConnection:
    __slots__ = ("_connection",)

    def __init__(self, connection: http.client.HTTPSConnection) -> None:
        self._connection = connection
        self._disable_debug_logging()

    def _disable_debug_logging(self) -> None:
        self._connection.set_debuglevel(0)
        if type(self._connection.debuglevel) is not int or self._connection.debuglevel:
            _fail(PublicationOperatorFailureCode.TRANSPORT_REFUSED)

    def connect(self) -> None:
        self._connection.connect()

    def set_read_timeout(self, seconds: int) -> None:
        if self._connection.sock is None:
            raise OSError("TLS socket unavailable")
        self._connection.sock.settimeout(seconds)

    def request(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> None:
        self._disable_debug_logging()
        self._connection.request(method, path, body=body, headers=headers)

    def getresponse(self) -> PublicationOperatorHttpsResponse:
        return cast(PublicationOperatorHttpsResponse, self._connection.getresponse())

    def close(self) -> None:
        self._connection.close()


@final
class SystemPublicationOperatorHttpsConnectionFactory:
    __slots__ = ()

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> PublicationOperatorHttpsConnection:
        if (
            host != PUBLICATION_OPERATOR_HOST
            or port != PUBLICATION_OPERATOR_PORT
            or connect_timeout_seconds != CONNECT_TIMEOUT_SECONDS
            or type(tls_context) is not ssl.SSLContext
            or tls_context.verify_mode != ssl.CERT_REQUIRED
            or not tls_context.check_hostname
        ):
            _fail(PublicationOperatorFailureCode.TRANSPORT_REFUSED)
        connection = http.client.HTTPSConnection(
            host=PUBLICATION_OPERATOR_HOST,
            port=PUBLICATION_OPERATOR_PORT,
            timeout=CONNECT_TIMEOUT_SECONDS,
            context=tls_context,
        )
        connection.set_debuglevel(0)
        if type(connection.debuglevel) is not int or connection.debuglevel:
            _fail(PublicationOperatorFailureCode.TRANSPORT_REFUSED)
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


def _bounded_body(response: PublicationOperatorHttpsResponse) -> bytes:
    content_encoding = response.getheader("Content-Encoding")
    content_length = response.getheader("Content-Length")
    transfer_encoding = response.getheader("Transfer-Encoding")
    if (
        content_encoding not in {None, "identity"}
        or transfer_encoding not in {None, "chunked"}
        or (transfer_encoding is not None and content_length is not None)
        or response.getheader("Location") is not None
    ):
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    if content_length is not None:
        if _CONTENT_LENGTH.fullmatch(content_length) is None:
            _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
        if int(content_length) > MAX_RESPONSE_BYTES:
            _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    payload = response.read(MAX_RESPONSE_BYTES + 1)
    if type(payload) is not bytes or not 2 <= len(payload) <= MAX_RESPONSE_BYTES:
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    if content_length is not None and len(payload) != int(content_length):
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    return payload


def _decode_json(payload: bytes) -> dict[str, object]:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    if type(value) is not dict:
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    return cast(dict[str, object], value)


def _error_code(value: dict[str, object], status: int) -> str:
    data_value = value.get("data")
    if type(data_value) is not dict:
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    data = cast(dict[object, object], data_value)
    if (
        set(value) != {"code", "data", "message"}
        or type(value.get("code")) is not str
        or value.get("message") != _ERROR_MESSAGE
        or set(data) != {"status"}
        or type(data.get("status")) is not int
        or data.get("status") != status
    ):
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    return cast(str, value["code"])


def _not_created_result(proposal_id: str) -> dict[str, object]:
    return {
        "created_at": _NOT_CREATED_AT,
        "expires_at": _NOT_CREATED_EXPIRES_AT,
        "operation": PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE.value,
        "proposal_id": require_sha256(proposal_id),
        "replayed": True,
        "schema": _PROPOSAL_SCHEMA,
        "state": PublicationProposalState.FAILED.value,
    }


def _operation(value: object) -> PublicationOperatorOperation:
    if type(value) is not str:
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    try:
        return PublicationOperatorOperation(value)
    except TypeError, ValueError:
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)


def _state(value: object) -> PublicationProposalState:
    if type(value) is not str:
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    try:
        return PublicationProposalState(value)
    except TypeError, ValueError:
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)


def _status_result(value: dict[str, object]) -> PublicationOperatorStatus:
    expected_keys = {
        "master_writes_enabled",
        "operator_version",
        "proposal_counts",
        "publication_writes_enabled",
        "schema",
        "supported_operations",
        "writes_enabled",
    }
    expected_operations = [PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE.value]
    if (
        set(value) != expected_keys
        or value["schema"] != _STATUS_SCHEMA
        or value["operator_version"] != PUBLICATION_OPERATOR_VERSION
        or value["supported_operations"] != expected_operations
        or type(value["master_writes_enabled"]) is not bool
        or type(value["publication_writes_enabled"]) is not bool
        or type(value["writes_enabled"]) is not bool
        or type(value["proposal_counts"]) is not dict
    ):
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    raw_counts = cast(dict[object, object], value["proposal_counts"])
    expected_states = tuple(PublicationProposalState)
    if set(raw_counts) != {state.value for state in expected_states}:
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    return PublicationOperatorStatus(
        master_writes_enabled=value["master_writes_enabled"],
        publication_writes_enabled=value["publication_writes_enabled"],
        writes_enabled=value["writes_enabled"],
        proposal_counts=tuple(
            (state, cast(int, raw_counts[state.value])) for state in expected_states
        ),
    )


def _proposal_result(
    value: dict[str, object],
    expected: PublicationProposal,
    *,
    recovery: bool,
) -> PublicationProposalReceipt:
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
        or value["schema"] != _PROPOSAL_SCHEMA
    ):
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    receipt = PublicationProposalReceipt(
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
        or (recovery and receipt.replayed is not True)
    ):
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    return receipt


def _apply_result(
    value: dict[str, object], *, proposal_id: str
) -> PublicationApplyReceipt:
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
        or value["schema"] != _APPLY_SCHEMA
    ):
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    receipt = PublicationApplyReceipt(
        proposal_id=cast(str, value["proposal_id"]),
        operation=_operation(value["operation"]),
        state=_state(value["state"]),
        result_code=cast(str, value["result_code"]),
        replayed=cast(bool, value["replayed"]),
    )
    if (
        receipt.proposal_id != proposal_id
        or receipt.result_code != PUBLICATION_OPERATOR_RESULT_CODE
    ):
        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
    return receipt


@final
class OfficialSelfHostedWordPressPublicationOperatorV2Adapter:
    """Expose only status, exact proposal recovery, propose, and apply."""

    __slots__ = (
        "_attempt_lock",
        "_attempted",
        "connection_factory",
        "repository_root",
    )

    def __init__(
        self,
        repository_root: object,
        connection_factory: object = SystemPublicationOperatorHttpsConnectionFactory(),
    ) -> None:
        if (
            not isinstance(repository_root, Path)
            or not repository_root.is_absolute()
            or not isinstance(
                connection_factory, PublicationOperatorHttpsConnectionFactory
            )
        ):
            _fail(PublicationOperatorFailureCode.REQUEST_INVALID)
        self.repository_root = repository_root
        self.connection_factory = connection_factory
        self._attempt_lock = threading.Lock()
        self._attempted = False

    def __repr__(self) -> str:
        return "OfficialSelfHostedWordPressPublicationOperatorV2Adapter(<redacted>)"

    def _claim_attempt(self) -> None:
        with self._attempt_lock:
            if self._attempted:
                _fail(PublicationOperatorFailureCode.OPERATION_NOT_ALLOWED)
            self._attempted = True

    def _credentials_header(self) -> str:
        try:
            return (
                OwnerPrivateWordPressOperatorCredentialStore(self.repository_root)
                .read()
                .authorization_header()
            )
        except WordPressOperatorFailure:
            _fail(PublicationOperatorFailureCode.CREDENTIAL_STORE_INVALID)

    def _execute(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        expected_status: int,
        mutating: bool,
        content_type: str | None = None,
        proposal_id: str | None = None,
    ) -> dict[str, object]:
        self._claim_attempt()
        require_clean_publication_operator_environment()
        _request_deadline_supported()
        authorization = self._credentials_header()
        try:
            context = ssl.create_default_context()
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
                _fail(PublicationOperatorFailureCode.TRANSPORT_REFUSED)
            connection = self.connection_factory.open(
                host=PUBLICATION_OPERATOR_HOST,
                port=PUBLICATION_OPERATOR_PORT,
                connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
                tls_context=context,
            )
        except PublicationOperatorFailure:
            raise
        except BaseException:
            _fail(PublicationOperatorFailureCode.TRANSPORT_REFUSED)
        attempted = False
        try:
            with _wall_clock_deadline(CONNECT_TIMEOUT_SECONDS):
                connection.connect()
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Authorization": authorization,
                "Connection": "close",
                "Content-Length": str(len(body)),
                "Host": PUBLICATION_OPERATOR_HOST,
                "User-Agent": "RAOS-ST-1704-publication-operator/2",
            }
            if content_type is not None:
                headers["Content-Type"] = content_type
            if proposal_id is not None and method == "POST" and path.endswith("/apply"):
                proposal_id = require_sha256(proposal_id)
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
                    or type(response_type) is not str
                    or _CONTENT_TYPE.fullmatch(response_type) is None
                ):
                    _fail(
                        PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS
                        if mutating
                        else PublicationOperatorFailureCode.RESPONSE_INVALID
                    )
                if response.status != expected_status:
                    if response.getheader("ETag") is not None:
                        _fail(PublicationOperatorFailureCode.RESPONSE_INVALID)
                    error = _decode_json(_bounded_body(response))
                    code = _error_code(error, response.status)
                    if (
                        method == "POST"
                        and path == _PROPOSAL_PATH
                        and (code, response.status) in _DETERMINISTIC_CREATE_REJECTIONS
                    ):
                        _fail(PublicationOperatorFailureCode.PROPOSAL_NOT_CREATED)
                    if (
                        method == "GET"
                        and proposal_id is not None
                        and path == f"{_PROPOSAL_PATH}/{proposal_id}"
                        and response.status == 404
                        and code == "raos_st1704_proposal_not_found"
                    ):
                        return _not_created_result(proposal_id)
                    _fail(
                        PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS
                        if mutating
                        else PublicationOperatorFailureCode.RESPONSE_INVALID
                    )
                if proposal_id is not None and response.getheader("ETag") != (
                    f'"{require_sha256(proposal_id)}"'
                ):
                    _fail(
                        PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS
                        if mutating
                        else PublicationOperatorFailureCode.RESPONSE_INVALID
                    )
                return _decode_json(_bounded_body(response))
        except PublicationOperatorFailure as failure:
            if (
                attempted
                and mutating
                and failure.code
                in {
                    PublicationOperatorFailureCode.INVALID_ARGUMENT,
                    PublicationOperatorFailureCode.RESPONSE_INVALID,
                }
            ):
                _fail(PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS)
            raise
        except BaseException:
            _fail(
                PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS
                if attempted and mutating
                else PublicationOperatorFailureCode.TRANSPORT_REFUSED
            )
        finally:
            try:
                connection.close()
            except BaseException:
                pass

    def status(self) -> PublicationOperatorStatus:
        return _status_result(
            self._execute(
                method="GET",
                path=_STATUS_PATH,
                body=b"",
                expected_status=200,
                mutating=False,
            )
        )

    def propose(self, proposal: PublicationProposal) -> PublicationProposalReceipt:
        if type(proposal) is not PublicationProposal:
            _fail(PublicationOperatorFailureCode.REQUEST_INVALID)
        response = self._execute(
            method="POST",
            path=_PROPOSAL_PATH,
            body=proposal.canonical_bytes(),
            expected_status=201,
            mutating=True,
            content_type="application/json",
            proposal_id=proposal.proposal_id,
        )
        try:
            return _proposal_result(response, proposal, recovery=False)
        except PublicationOperatorFailure:
            _fail(PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS)

    def recover_proposal(
        self, proposal: PublicationProposal
    ) -> PublicationProposalReceipt:
        if type(proposal) is not PublicationProposal:
            _fail(PublicationOperatorFailureCode.REQUEST_INVALID)
        response = self._execute(
            method="GET",
            path=f"{_PROPOSAL_PATH}/{proposal.proposal_id}",
            body=b"",
            expected_status=200,
            mutating=False,
            proposal_id=proposal.proposal_id,
        )
        return _proposal_result(response, proposal, recovery=True)

    def apply(self, proposal_id: str) -> PublicationApplyReceipt:
        proposal_id = require_sha256(proposal_id)
        response = self._execute(
            method="POST",
            path=f"{_PROPOSAL_PATH}/{proposal_id}/apply",
            body=b"{}",
            expected_status=200,
            mutating=True,
            content_type="application/json",
            proposal_id=proposal_id,
        )
        try:
            return _apply_result(response, proposal_id=proposal_id)
        except PublicationOperatorFailure:
            _fail(PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS)


__all__ = [
    "CONNECT_TIMEOUT_SECONDS",
    "MAX_RESPONSE_BYTES",
    "OfficialSelfHostedWordPressPublicationOperatorV2Adapter",
    "PUBLICATION_OPERATOR_HOST",
    "PUBLICATION_OPERATOR_PORT",
    "PublicationOperatorHttpsConnection",
    "PublicationOperatorHttpsConnectionFactory",
    "PublicationOperatorHttpsResponse",
    "READ_TIMEOUT_SECONDS",
    "SystemPublicationOperatorHttpsConnectionFactory",
    "require_clean_publication_operator_environment",
]
