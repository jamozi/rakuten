"""Disabled external authorization projection and loopback recorded harness.

No framework route is registered.  External dispatch always returns one
sanitized RFC 9457 refusal.  The separate exact-loopback harness accepts no
Cookie, Bearer, Authorization header, provider token, or network target and
returns authorization results only through a non-serializable in-process
handle.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import NoReturn, SupportsIndex, cast
from urllib.parse import urlsplit
from uuid import UUID

from raos.application.iam.authorization import DurableAuthorizationService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import AuthenticationFailure, SessionId
from raos.domain.iam.authorization import (
    AuthorizationCommandId,
    AuthorizationCommandResult,
    AuthorizationEvaluationCommand,
    AuthorizationFailure,
    AuthorizationRepositoryFailure,
    AuthorizationRepositoryFailureCode,
    AuthorizationTarget,
    CorrelationId,
    DecisionEffect,
    EntitlementRevision,
    OperationId,
    PolicyRevision,
    ResourceScope,
    ResourceScopeKind,
    ResourceState,
    deny_authorization,
    require_authorization_utc,
)
from raos.domain.iam.step_up import BoundStepUpGrantId, StepUpCommandId


_EXTERNAL_TARGET = "/admin/authorization"
_RECORDED_TARGET = "/__recorded__/st-0403/admin-authorization"
_REQUEST_KEYS = frozenset(
    {"method", "target", "origin", "content_type", "headers", "body"}
)
_EVALUATE_KEYS = frozenset(
    {
        "action",
        "session_id",
        "command_id",
        "operation_id",
        "correlation_id",
        "expected_policy_revision",
        "expected_entitlement_revision",
        "resource_kind",
        "site_id",
        "resource_id",
        "resource_state",
        "step_up_command_id",
        "step_up_grant_id",
        "independent_actor_evidence_id",
    }
)
_RECOVER_KEYS = frozenset({"action", "session_id", "command_id"})
_COMMON_HEADERS = (
    ("Cache-Control", "no-store"),
    ("Pragma", "no-cache"),
    ("X-Content-Type-Options", "nosniff"),
)
_SUCCESS_HEADERS = (("Content-Type", "application/json"), *_COMMON_HEADERS)
_PROBLEM_HEADERS = (("Content-Type", "application/problem+json"), *_COMMON_HEADERS)

JsonScalar = str | int | bool | None


def _deny() -> NoReturn:
    deny_authorization()


def _require_recorded(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }:
        _deny()
    return value


def _string(value: object, *, maximum: int = 2048) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(ord(character) < 0x20 or ord(character) > 0x7E for character in value)
    ):
        _deny()
    return value


def _mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _deny()
    untyped = cast(dict[object, object], value)
    if frozenset(untyped) != keys or any(type(key) is not str for key in untyped):
        _deny()
    return cast(dict[str, object], untyped)


def _optional_string(value: object, *, maximum: int = 2048) -> str | None:
    return None if value is None else _string(value, maximum=maximum)


def _uuid(value: object) -> UUID:
    text = _string(value, maximum=36)
    try:
        parsed = UUID(text)
    except ValueError:
        _deny()
    if parsed.int == 0 or str(parsed) != text:
        _deny()
    return parsed


def _optional_uuid(value: object) -> UUID | None:
    return None if value is None else _uuid(value)


def _response_body(value: object) -> dict[str, JsonScalar]:
    if not isinstance(value, Mapping):
        raise ValueError("INVALID_ST0403_HTTP_RESPONSE") from None
    mapping = cast(Mapping[object, object], value)
    if any(
        type(key) is not str or type(item) not in {str, int, bool, type(None)}
        for key, item in mapping.items()
    ):
        raise ValueError("INVALID_ST0403_HTTP_RESPONSE") from None
    return cast(dict[str, JsonScalar], dict(mapping))


class RecordedAuthorizationHttpAction(str, Enum):
    EVALUATE = "EVALUATE"
    RECOVER = "RECOVER"


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAuthorizationLoopbackOrigin:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        value = _string(self.value)
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except TypeError, ValueError:
            _deny()
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
            _deny()

    def __repr__(self) -> str:
        return "RecordedAuthorizationLoopbackOrigin(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAdminAuthorizationHttpRequest:
    action: RecordedAuthorizationHttpAction
    origin: RecordedAuthorizationLoopbackOrigin
    session_id: SessionId = field(repr=False)
    command_id: AuthorizationCommandId = field(repr=False)
    command: AuthorizationEvaluationCommand | None = field(default=None, repr=False)

    @classmethod
    def from_document(
        cls, document: object, *, now: datetime
    ) -> RecordedAdminAuthorizationHttpRequest:
        request = _mapping(document, _REQUEST_KEYS)
        if (
            _string(request["method"], maximum=4) != "POST"
            or _string(request["target"]) != _RECORDED_TARGET
            or _string(request["content_type"], maximum=64) != "application/json"
            or request["headers"] != {}
        ):
            _deny()
        origin = RecordedAuthorizationLoopbackOrigin(_string(request["origin"]))
        body_untyped = request["body"]
        if type(body_untyped) is not dict:
            _deny()
        body = cast(dict[str, object], body_untyped)
        try:
            action = RecordedAuthorizationHttpAction(
                _string(body.get("action"), maximum=16)
            )
        except ValueError:
            _deny()
        if action is RecordedAuthorizationHttpAction.RECOVER:
            values = _mapping(body, _RECOVER_KEYS)
            return cls(
                action=action,
                origin=origin,
                session_id=SessionId(_string(values["session_id"], maximum=43)),
                command_id=AuthorizationCommandId(
                    _string(values["command_id"], maximum=128)
                ),
            )
        values = _mapping(body, _EVALUATE_KEYS)
        try:
            resource_kind = ResourceScopeKind(
                _string(values["resource_kind"], maximum=64)
            )
        except ValueError:
            _deny()
        state = _optional_string(values["resource_state"], maximum=128)
        step_command = _optional_string(values["step_up_command_id"], maximum=43)
        step_grant = _optional_string(values["step_up_grant_id"], maximum=43)
        if (step_command is None) != (step_grant is None):
            _deny()
        command_id = AuthorizationCommandId(_string(values["command_id"], maximum=128))
        session_id = SessionId(_string(values["session_id"], maximum=43))
        command = AuthorizationEvaluationCommand(
            command_id=command_id,
            operation_id=OperationId(_string(values["operation_id"], maximum=128)),
            target=AuthorizationTarget(
                scope=ResourceScope(
                    kind=resource_kind,
                    site_id=_uuid(values["site_id"]),
                    resource_id=_uuid(values["resource_id"]),
                ),
                state=None if state is None else ResourceState(state),
            ),
            correlation_id=CorrelationId(
                _string(values["correlation_id"], maximum=128)
            ),
            expected_policy_revision=PolicyRevision(
                _string(values["expected_policy_revision"], maximum=128)
            ),
            expected_entitlement_revision=EntitlementRevision(
                _string(values["expected_entitlement_revision"], maximum=128)
            ),
            observed_at=require_authorization_utc(now),
            step_up_command_id=(
                None if step_command is None else StepUpCommandId(step_command)
            ),
            step_up_grant_id=(
                None if step_grant is None else BoundStepUpGrantId(step_grant)
            ),
            independent_actor_evidence_id=_optional_uuid(
                values["independent_actor_evidence_id"]
            ),
        )
        return cls(
            action=action,
            origin=origin,
            session_id=session_id,
            command_id=command_id,
            command=command,
        )

    def __repr__(self) -> str:
        return "RecordedAdminAuthorizationHttpRequest(<redacted>)"


@dataclass(frozen=True, slots=True)
class Rfc9457AuthorizationProblem:
    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str

    def __post_init__(self) -> None:
        if (
            type(self.type) is not str
            or not self.type.startswith("urn:raos:problem:st-0403:")
            or type(self.title) is not str
            or not self.title
            or type(self.status) is not int
            or self.status not in {400, 403, 404, 409, 503}
            or type(self.detail) is not str
            or not self.detail
            or self.instance != "urn:raos:recorded:st-0403"
            or type(self.code) is not str
            or not self.code
        ):
            raise ValueError("INVALID_ST0403_PROBLEM") from None

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
class AdminAuthorizationHttpResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: Mapping[str, JsonScalar]

    def __post_init__(self) -> None:
        body = _response_body(self.body)
        names = tuple(name.lower() for name, _value in self.headers)
        if (
            type(self.status) is not int
            or self.status not in {200, 400, 403, 404, 409, 503}
            or type(self.headers) is not tuple
            or any(
                type(row) is not tuple
                or len(row) != 2
                or any(type(value) is not str or not value for value in row)
                for row in self.headers
            )
            or len(set(names)) != len(names)
            or any(
                name in {"authorization", "location", "set-cookie"} for name in names
            )
        ):
            raise ValueError("INVALID_ST0403_HTTP_RESPONSE") from None
        object.__setattr__(self, "body", MappingProxyType(body))


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAdminAuthorizationDispatch:
    response: AdminAuthorizationHttpResponse
    result: AuthorizationCommandResult | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        return "RecordedAdminAuthorizationDispatch(<redacted>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded authorization dispatch is not serializable")


def _success(result: AuthorizationCommandResult) -> AdminAuthorizationHttpResponse:
    allowed = result.decision.effect is DecisionEffect.ALLOW
    if not allowed:
        return _problem("AUTHORIZATION_DENIED")
    return AdminAuthorizationHttpResponse(
        status=200,
        headers=_SUCCESS_HEADERS,
        body=MappingProxyType(
            {
                "outcome": "ALLOWED",
                "code": "RECORDED_AUTHORIZATION_ALLOWED",
                "audit_sequence": result.audit.sequence,
                "audit_digest": result.audit.digest,
                "route_registered": False,
                "business_action_executed": False,
                "external_authority": False,
            }
        ),
    )


def _problem(code: str) -> AdminAuthorizationHttpResponse:
    if code == "AUTHORIZATION_ROUTE_DISABLED":
        status = 503
        title = "Admin authorization route is disabled"
        detail = f"No external {_EXTERNAL_TARGET} route is registered."
    elif code == AuthorizationRepositoryFailureCode.COMMAND_UNKNOWN.value:
        status = 404
        title = "Authorization command was not found"
        detail = "The recorded authorization command could not be recovered."
    elif code in {
        AuthorizationRepositoryFailureCode.COMMAND_CONFLICT.value,
        AuthorizationRepositoryFailureCode.REVISION_CONFLICT.value,
    }:
        status = 409
        title = "Authorization request conflicted"
        detail = "The recorded authorization request failed a closed consistency check."
    elif code in {
        AuthorizationRepositoryFailureCode.STORAGE_FAILURE.value,
        AuthorizationRepositoryFailureCode.STORAGE_COMMIT_UNKNOWN.value,
        AuthorizationRepositoryFailureCode.TAMPER_DETECTED.value,
        AuthorizationRepositoryFailureCode.DEVELOPMENT_ONLY.value,
    }:
        status = 503
        title = "Authorization service unavailable"
        detail = "The recorded authorization store failed closed."
    else:
        status = 403
        title = "Authorization request denied"
        detail = "The authorization requirement was not satisfied."
        code = "AUTHORIZATION_DENIED"
    problem = Rfc9457AuthorizationProblem(
        type=f"urn:raos:problem:st-0403:{code.lower().replace('_', '-')}",
        title=title,
        status=status,
        detail=detail,
        instance="urn:raos:recorded:st-0403",
        code=code,
    )
    return AdminAuthorizationHttpResponse(
        status=status,
        headers=_PROBLEM_HEADERS,
        body=problem.as_mapping(),
    )


class DisabledAdminAuthorizationHttpAdapter:
    """No-authority HTTP projection plus strict in-process recorded dispatch."""

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        service: DurableAuthorizationService,
    ) -> None:
        self._environment = _require_recorded(environment)
        if type(service) is not DurableAuthorizationService:
            _deny()
        self._service = service

    def dispatch_external(self, document: object) -> RecordedAdminAuthorizationDispatch:
        del document
        return RecordedAdminAuthorizationDispatch(
            response=_problem("AUTHORIZATION_ROUTE_DISABLED")
        )

    def dispatch_recorded(
        self, document: object, *, now: datetime
    ) -> RecordedAdminAuthorizationDispatch:
        _require_recorded(self._environment)
        try:
            observed_at = require_authorization_utc(now)
            request = RecordedAdminAuthorizationHttpRequest.from_document(
                document, now=observed_at
            )
            if request.action is RecordedAuthorizationHttpAction.RECOVER:
                result = self._service.recover_admin(
                    command_id=request.command_id,
                    session_id=request.session_id,
                    now=observed_at,
                )
            else:
                if request.command is None:
                    _deny()
                result = self._service.evaluate_admin(
                    session_id=request.session_id,
                    command=request.command,
                )
            return RecordedAdminAuthorizationDispatch(
                response=_success(result), result=result
            )
        except AuthorizationRepositoryFailure as error:
            return RecordedAdminAuthorizationDispatch(
                response=_problem(error.code.value)
            )
        except AuthenticationFailure, AuthorizationFailure:
            return RecordedAdminAuthorizationDispatch(
                response=_problem("AUTHORIZATION_DENIED")
            )
        except Exception:
            return RecordedAdminAuthorizationDispatch(
                response=_problem(
                    AuthorizationRepositoryFailureCode.STORAGE_FAILURE.value
                )
            )

    def __repr__(self) -> str:
        return (
            "DisabledAdminAuthorizationHttpAdapter("
            "route_registered=false,state=<redacted>)"
        )


__all__ = [
    "AdminAuthorizationHttpResponse",
    "DisabledAdminAuthorizationHttpAdapter",
    "RecordedAdminAuthorizationDispatch",
    "RecordedAdminAuthorizationHttpRequest",
    "RecordedAuthorizationHttpAction",
    "RecordedAuthorizationLoopbackOrigin",
    "Rfc9457AuthorizationProblem",
]
