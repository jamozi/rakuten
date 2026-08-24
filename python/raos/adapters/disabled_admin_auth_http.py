"""Disabled Admin HTTP projection and loopback-only recorded ST-0401 harness.

No framework route is registered by this module.  ``dispatch_external`` always
returns an RFC 9457 refusal.  The separate ``dispatch_recorded`` method accepts
one closed JSON-like request shape at an exact IPv4 loopback origin and returns
only non-secret response bodies.  Callback and session handles are carried in
an explicitly non-serializable result object for local tests, so this module
does not choose cookie, bearer, browser storage, or Production delivery policy.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import NoReturn, Protocol, SupportsIndex, cast, final, runtime_checkable
from urllib.parse import urlsplit

from raos.application.iam.authentication import AuthenticationService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import (
    AuthenticationFailure,
    AuthenticationFailureCode,
    AuthorizationCallback,
    AuthorizationCode,
    AuthorizationRequest,
    AuthorizationState,
    RedirectUri,
    SessionId,
    require_utc,
)


_RECORDED_TARGET = "/__recorded__/st-0401/admin-auth"
_REQUEST_KEYS = frozenset({"method", "target", "origin", "content_type", "body"})
_COMMON_HEADERS = (
    ("Cache-Control", "no-store"),
    ("Pragma", "no-cache"),
    ("X-Content-Type-Options", "nosniff"),
)
_SUCCESS_HEADERS = (("Content-Type", "application/json"), *_COMMON_HEADERS)
_PROBLEM_HEADERS = (("Content-Type", "application/problem+json"), *_COMMON_HEADERS)


JsonScalar = str | int | bool | None


def _raise(code: AuthenticationFailureCode) -> NoReturn:
    raise AuthenticationFailure(code) from None


def _require_development(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment is not RuntimeEnvironment.ENV_DEV
    ):
        _raise(AuthenticationFailureCode.DEVELOPMENT_ONLY)
    return environment


def _exact_mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _raise(AuthenticationFailureCode.MALFORMED_INPUT)
    mapping = cast(dict[object, object], value)
    if frozenset(mapping) != keys or any(type(key) is not str for key in mapping):
        _raise(AuthenticationFailureCode.MALFORMED_INPUT)
    return cast(dict[str, object], mapping)


def _exact_string(value: object, *, maximum: int = 2048) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(ord(character) < 0x20 or ord(character) > 0x7E for character in value)
    ):
        _raise(AuthenticationFailureCode.MALFORMED_INPUT)
    return value


def _response_body(value: object) -> dict[str, JsonScalar]:
    if not isinstance(value, Mapping):
        raise ValueError("INVALID_ST0401_HTTP_RESPONSE") from None
    mapping = cast(Mapping[object, object], value)
    if any(
        type(key) is not str or type(item) not in {str, int, bool, type(None)}
        for key, item in mapping.items()
    ):
        raise ValueError("INVALID_ST0401_HTTP_RESPONSE") from None
    return cast(dict[str, JsonScalar], dict(mapping))


class RecordedAdminAuthAction(str, Enum):
    BEGIN = "BEGIN"
    CALLBACK = "CALLBACK"
    REQUIRE = "REQUIRE"
    ROTATE = "ROTATE"
    RECOVER_ROTATION = "RECOVER_ROTATION"
    REVOKE = "REVOKE"


@dataclass(frozen=True, slots=True, repr=False)
class RecordedLoopbackOrigin:
    """Canonical HTTP IPv4-loopback origin with one explicit unprivileged port."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        value = _exact_string(self.value)
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except TypeError, ValueError:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or port is None
            or not 1024 <= port <= 65535
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or value != f"http://127.0.0.1:{port}"
        ):
            _raise(AuthenticationFailureCode.DEVELOPMENT_ONLY)

    def callback_uri(self) -> RedirectUri:
        return RedirectUri(f"{self.value}{_RECORDED_TARGET}")

    def __repr__(self) -> str:
        return "RecordedLoopbackOrigin(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAdminAuthHttpRequest:
    action: RecordedAdminAuthAction
    origin: RecordedLoopbackOrigin
    callback: AuthorizationCallback | None = field(default=None, repr=False)
    session_id: SessionId | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.action) is not RecordedAdminAuthAction
            or type(self.origin) is not RecordedLoopbackOrigin
        ):
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        callback_required = self.action is RecordedAdminAuthAction.CALLBACK
        session_required = self.action in {
            RecordedAdminAuthAction.REQUIRE,
            RecordedAdminAuthAction.ROTATE,
            RecordedAdminAuthAction.RECOVER_ROTATION,
            RecordedAdminAuthAction.REVOKE,
        }
        if (
            (callback_required and type(self.callback) is not AuthorizationCallback)
            or (not callback_required and self.callback is not None)
            or (session_required and type(self.session_id) is not SessionId)
            or (not session_required and self.session_id is not None)
        ):
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)

    @classmethod
    def from_document(cls, document: object) -> RecordedAdminAuthHttpRequest:
        request = _exact_mapping(document, _REQUEST_KEYS)
        method = _exact_string(request["method"], maximum=4)
        target = _exact_string(request["target"])
        content_type = _exact_string(request["content_type"], maximum=64)
        if (
            method != "POST"
            or target != _RECORDED_TARGET
            or content_type != "application/json"
        ):
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        origin = RecordedLoopbackOrigin(_exact_string(request["origin"]))
        body_value = request["body"]
        if type(body_value) is not dict:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        untyped_body = cast(dict[object, object], body_value)
        if any(type(key) is not str for key in untyped_body):
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        body = cast(dict[str, object], untyped_body)
        try:
            action = RecordedAdminAuthAction(
                _exact_string(body.get("action"), maximum=32)
            )
        except ValueError:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if action is RecordedAdminAuthAction.BEGIN:
            _exact_mapping(body, frozenset({"action"}))
            return cls(action=action, origin=origin)
        if action is RecordedAdminAuthAction.CALLBACK:
            callback_body = _exact_mapping(body, frozenset({"action", "state", "code"}))
            callback = AuthorizationCallback(
                state=AuthorizationState(_exact_string(callback_body["state"])),
                code=AuthorizationCode(
                    _exact_string(callback_body["code"], maximum=512)
                ),
            )
            return cls(action=action, origin=origin, callback=callback)
        session_body = _exact_mapping(body, frozenset({"action", "session_id"}))
        return cls(
            action=action,
            origin=origin,
            session_id=SessionId(_exact_string(session_body["session_id"])),
        )

    def __repr__(self) -> str:
        return "RecordedAdminAuthHttpRequest(<redacted>)"


@dataclass(frozen=True, slots=True)
class Rfc9457Problem:
    """Closed problem projection with no rejected request material."""

    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str

    def __post_init__(self) -> None:
        if (
            type(self.type) is not str
            or not self.type.startswith("urn:raos:problem:st-0401:")
            or type(self.title) is not str
            or not self.title
            or type(self.status) is not int
            or self.status not in {400, 401, 409, 503}
            or type(self.detail) is not str
            or not self.detail
            or self.instance != "urn:raos:recorded:st-0401"
            or type(self.code) is not str
            or not self.code
        ):
            raise ValueError("INVALID_ST0401_PROBLEM") from None

    def as_mapping(self) -> Mapping[str, JsonScalar]:
        return MappingProxyType(
            {
                "type": self.type,
                "title": self.title,
                "status": self.status,
                "detail": self.detail,
                "instance": self.instance,
                "code": self.code,
            }
        )


@dataclass(frozen=True, slots=True)
class AdminAuthHttpResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: Mapping[str, JsonScalar]

    def __post_init__(self) -> None:
        normalized_body = _response_body(self.body)
        if (
            type(self.status) is not int
            or self.status not in {200, 202, 400, 401, 409, 503}
            or type(self.headers) is not tuple
            or any(
                type(row) is not tuple
                or len(row) != 2
                or any(type(value) is not str or not value for value in row)
                for row in self.headers
            )
        ):
            raise ValueError("INVALID_ST0401_HTTP_RESPONSE") from None
        header_names = tuple(name.lower() for name, _value in self.headers)
        if (
            len(set(header_names)) != len(header_names)
            or "set-cookie" in header_names
            or "authorization" in header_names
            or "location" in header_names
        ):
            raise ValueError("INVALID_ST0401_HTTP_RESPONSE") from None
        object.__setattr__(self, "body", MappingProxyType(normalized_body))


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAdminAuthDispatch:
    """Local harness result; protocol values are never serialized in HTTP output."""

    response: AdminAuthHttpResponse
    callback: AuthorizationCallback | None = field(default=None, repr=False)
    session_id: SessionId | None = field(default=None, repr=False)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded authentication dispatch is not serializable")

    def __repr__(self) -> str:
        return "RecordedAdminAuthDispatch(<redacted>)"


@runtime_checkable
class RecordedAuthorizationDriver(Protocol):
    def authorize(
        self, *, request: AuthorizationRequest, now: datetime
    ) -> AuthorizationCallback: ...


def _success(status: int, outcome: str) -> AdminAuthHttpResponse:
    return AdminAuthHttpResponse(
        status=status,
        headers=_SUCCESS_HEADERS,
        body=MappingProxyType(
            {
                "outcome": outcome,
                "delivery": "UNSELECTED_NOT_DELIVERED",
                "external_activation": False,
            }
        ),
    )


def _problem_for_code(code: str) -> AdminAuthHttpResponse:
    if code == "AUTH_TRANSPORT_DISABLED":
        status = 503
        title = "Admin authentication transport is disabled"
        detail = "No external Admin authentication route is registered."
    else:
        try:
            failure = AuthenticationFailureCode(code)
        except ValueError:
            failure = AuthenticationFailureCode.STORAGE_FAILURE
        if failure in {
            AuthenticationFailureCode.MALFORMED_INPUT,
            AuthenticationFailureCode.ENTROPY_FAILURE,
            AuthenticationFailureCode.PKCE_UNSUPPORTED,
        }:
            status = 400
        elif failure in {
            AuthenticationFailureCode.SESSION_CONFLICT,
            AuthenticationFailureCode.AUTHORIZATION_COLLISION,
            AuthenticationFailureCode.SESSION_COLLISION,
        }:
            status = 409
        elif failure in {
            AuthenticationFailureCode.STORAGE_FAILURE,
            AuthenticationFailureCode.STORAGE_COMMIT_UNKNOWN,
            AuthenticationFailureCode.PROVIDER_FAILURE,
            AuthenticationFailureCode.DEVELOPMENT_ONLY,
        }:
            status = 503
        else:
            status = 401
        title = "Authentication request rejected"
        detail = "The recorded authentication request failed closed."
        code = failure.value
    problem = Rfc9457Problem(
        type=f"urn:raos:problem:st-0401:{code.lower().replace('_', '-')}",
        title=title,
        status=status,
        detail=detail,
        instance="urn:raos:recorded:st-0401",
        code=code,
    )
    return AdminAuthHttpResponse(
        status=status,
        headers=_PROBLEM_HEADERS,
        body=problem.as_mapping(),
    )


@final
class DisabledAdminAuthHttpAdapter:
    """No-authority HTTP projection plus an explicit recorded-only test seam."""

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        service: AuthenticationService,
        driver: RecordedAuthorizationDriver,
    ) -> None:
        self._environment = _require_development(environment)
        if type(service) is not AuthenticationService or not isinstance(
            cast(object, driver), RecordedAuthorizationDriver
        ):
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        self._service = service
        self._driver = driver

    def dispatch_external(self, document: object) -> RecordedAdminAuthDispatch:
        """Refuse every external delivery attempt without inspecting its values."""

        del document
        return RecordedAdminAuthDispatch(
            response=_problem_for_code("AUTH_TRANSPORT_DISABLED")
        )

    def dispatch_recorded(
        self, document: object, *, now: datetime
    ) -> RecordedAdminAuthDispatch:
        """Execute one no-network loopback recording through strict shapes."""

        _require_development(self._environment)
        try:
            observed_at = require_utc(now)
            request = RecordedAdminAuthHttpRequest.from_document(document)
            action = request.action
            if action is RecordedAdminAuthAction.BEGIN:
                authorization = self._service.begin_authorization(
                    redirect_uri=request.origin.callback_uri(),
                    now=observed_at,
                )
                callback = self._driver.authorize(
                    request=authorization,
                    now=observed_at,
                )
                return RecordedAdminAuthDispatch(
                    response=_success(202, "RECORDED_AUTHORIZATION_READY"),
                    callback=callback,
                )
            if action is RecordedAdminAuthAction.CALLBACK:
                received_callback = request.callback
                if received_callback is None:
                    _raise(AuthenticationFailureCode.MALFORMED_INPUT)
                session = self._service.complete_authorization(
                    callback=received_callback,
                    now=observed_at,
                )
                return RecordedAdminAuthDispatch(
                    response=_success(200, "SESSION_ESTABLISHED_NOT_DELIVERED"),
                    session_id=session.session_id,
                )
            session_id = request.session_id
            if session_id is None:
                _raise(AuthenticationFailureCode.MALFORMED_INPUT)
            if action is RecordedAdminAuthAction.REQUIRE:
                session = self._service.require_session(
                    session_id=session_id,
                    now=observed_at,
                )
                return RecordedAdminAuthDispatch(
                    response=_success(200, "RECORDED_SESSION_ACTIVE"),
                    session_id=session.session_id,
                )
            if action is RecordedAdminAuthAction.ROTATE:
                session = self._service.rotate_session(
                    session_id=session_id,
                    now=observed_at,
                )
                return RecordedAdminAuthDispatch(
                    response=_success(200, "RECORDED_SESSION_ROTATED"),
                    session_id=session.session_id,
                )
            if action is RecordedAdminAuthAction.RECOVER_ROTATION:
                session = self._service.recover_session_rotation(
                    predecessor_id=session_id,
                    now=observed_at,
                )
                return RecordedAdminAuthDispatch(
                    response=_success(200, "RECORDED_ROTATION_RECOVERED"),
                    session_id=session.session_id,
                )
            self._service.revoke_session(session_id=session_id, now=observed_at)
            return RecordedAdminAuthDispatch(
                response=_success(200, "RECORDED_SESSION_REVOKED")
            )
        except AuthenticationFailure as error:
            return RecordedAdminAuthDispatch(
                response=_problem_for_code(error.code.value)
            )
        except Exception:
            return RecordedAdminAuthDispatch(
                response=_problem_for_code(
                    AuthenticationFailureCode.STORAGE_FAILURE.value
                )
            )

    def __repr__(self) -> str:
        return "DisabledAdminAuthHttpAdapter(state=<redacted>, activation=false)"


__all__ = [
    "AdminAuthHttpResponse",
    "DisabledAdminAuthHttpAdapter",
    "RecordedAdminAuthAction",
    "RecordedAdminAuthDispatch",
    "RecordedAdminAuthHttpRequest",
    "RecordedAuthorizationDriver",
    "RecordedLoopbackOrigin",
    "Rfc9457Problem",
]
