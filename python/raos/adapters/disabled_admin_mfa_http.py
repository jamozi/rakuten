"""Disabled ``/admin/mfa`` projection and loopback-only ST-0402 harness.

This module registers no framework route.  External dispatch always returns a
sanitized RFC 9457 refusal.  The separate recorded dispatcher accepts one
closed JSON-like shape at an exact IPv4 loopback origin and carries lifecycle
handles only inside a non-serializable Python result.  It therefore selects no
Cookie, Bearer, browser-storage, MFA factor, or Production delivery policy.
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

from raos.application.iam.step_up import DurableStepUpService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import AuthenticationFailure, SessionId
from raos.domain.iam.step_up import (
    BoundStepUpGrantId,
    CriticalStepUpAction,
    StepUpChallengeId,
    StepUpCommandId,
    StepUpCommandResult,
    StepUpFailure,
    StepUpFailureCode,
    StepUpResourceType,
    StepUpVerificationReceiptId,
    fail_step_up,
    require_step_up_utc,
)


_EXTERNAL_TARGET = "/admin/mfa"
_RECORDED_TARGET = "/__recorded__/st-0402/admin-mfa"
_REQUEST_KEYS = frozenset({"method", "target", "origin", "content_type", "body"})
_COMMON_HEADERS = (
    ("Cache-Control", "no-store"),
    ("Pragma", "no-cache"),
    ("X-Content-Type-Options", "nosniff"),
)
_SUCCESS_HEADERS = (("Content-Type", "application/json"), *_COMMON_HEADERS)
_PROBLEM_HEADERS = (("Content-Type", "application/problem+json"), *_COMMON_HEADERS)


JsonScalar = str | int | bool | None


def _fail(code: StepUpFailureCode) -> NoReturn:
    fail_step_up(code)


def _require_development(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment is not RuntimeEnvironment.ENV_DEV
    ):
        _fail(StepUpFailureCode.DEVELOPMENT_ONLY)
    return environment


def _string(value: object, *, maximum: int = 2048) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(ord(character) < 0x20 or ord(character) > 0x7E for character in value)
    ):
        _fail(StepUpFailureCode.CLAIM_MALFORMED)
    return value


def _mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _fail(StepUpFailureCode.CLAIM_MALFORMED)
    untyped = cast(dict[object, object], value)
    if frozenset(untyped) != keys or any(type(key) is not str for key in untyped):
        _fail(StepUpFailureCode.CLAIM_MALFORMED)
    return cast(dict[str, object], untyped)


def _instant(value: object) -> datetime:
    text = _string(value, maximum=40)
    try:
        parsed = datetime.fromisoformat(text.removesuffix("Z") + "+00:00")
    except ValueError:
        _fail(StepUpFailureCode.CLAIM_MALFORMED)
    normalized = require_step_up_utc(parsed)
    if normalized.isoformat(timespec="microseconds").replace("+00:00", "Z") != text:
        _fail(StepUpFailureCode.CLAIM_MALFORMED)
    return normalized


def _response_body(value: object) -> dict[str, JsonScalar]:
    if not isinstance(value, Mapping):
        raise ValueError("INVALID_ST0402_HTTP_RESPONSE") from None
    mapping = cast(Mapping[object, object], value)
    if any(
        type(key) is not str or type(item) not in {str, int, bool, type(None)}
        for key, item in mapping.items()
    ):
        raise ValueError("INVALID_ST0402_HTTP_RESPONSE") from None
    return cast(dict[str, JsonScalar], dict(mapping))


class RecordedAdminMfaAction(str, Enum):
    BEGIN = "BEGIN"
    VERIFY = "VERIFY"
    ISSUE = "ISSUE"
    CONSUME = "CONSUME"
    REVOKE = "REVOKE"
    RECOVER = "RECOVER"


@dataclass(frozen=True, slots=True, repr=False)
class RecordedMfaLoopbackOrigin:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        value = _string(self.value)
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except TypeError, ValueError:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
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
            _fail(StepUpFailureCode.DEVELOPMENT_ONLY)

    def __repr__(self) -> str:
        return "RecordedMfaLoopbackOrigin(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAdminMfaHttpRequest:
    action: RecordedAdminMfaAction
    origin: RecordedMfaLoopbackOrigin
    command_id: StepUpCommandId
    session_id: SessionId | None = field(default=None, repr=False)
    challenge_id: StepUpChallengeId | None = field(default=None, repr=False)
    receipt_id: StepUpVerificationReceiptId | None = field(default=None, repr=False)
    grant_id: BoundStepUpGrantId | None = field(default=None, repr=False)
    critical_action: CriticalStepUpAction | None = field(default=None, repr=False)
    resource_type: StepUpResourceType | None = field(default=None, repr=False)
    resource_id: UUID | None = field(default=None, repr=False)
    expires_at: datetime | None = field(default=None, repr=False)

    @classmethod
    def from_document(cls, document: object) -> RecordedAdminMfaHttpRequest:
        request = _mapping(document, _REQUEST_KEYS)
        if (
            _string(request["method"], maximum=4) != "POST"
            or _string(request["target"]) != _RECORDED_TARGET
            or _string(request["content_type"], maximum=64) != "application/json"
        ):
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        origin = RecordedMfaLoopbackOrigin(_string(request["origin"]))
        if type(request["body"]) is not dict:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        untyped = cast(dict[object, object], request["body"])
        if any(type(key) is not str for key in untyped):
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        body = cast(dict[str, object], untyped)
        try:
            action = RecordedAdminMfaAction(_string(body.get("action"), maximum=16))
        except ValueError:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        if action is RecordedAdminMfaAction.RECOVER:
            value = _mapping(body, frozenset({"action", "command_id"}))
            return cls(
                action=action,
                origin=origin,
                command_id=StepUpCommandId(_string(value["command_id"], maximum=43)),
            )
        if action is RecordedAdminMfaAction.BEGIN:
            value = _mapping(
                body,
                frozenset(
                    {
                        "action",
                        "command_id",
                        "session_id",
                        "critical_action",
                        "resource_type",
                        "resource_id",
                        "expires_at",
                    }
                ),
            )
            try:
                critical_action = CriticalStepUpAction(
                    _string(value["critical_action"], maximum=64)
                )
                resource_type = StepUpResourceType(
                    _string(value["resource_type"], maximum=64)
                )
                resource_id = UUID(_string(value["resource_id"], maximum=36))
            except ValueError:
                _fail(StepUpFailureCode.CLAIM_MALFORMED)
            return cls(
                action=action,
                origin=origin,
                command_id=StepUpCommandId(_string(value["command_id"], maximum=43)),
                session_id=SessionId(_string(value["session_id"], maximum=43)),
                critical_action=critical_action,
                resource_type=resource_type,
                resource_id=resource_id,
                expires_at=_instant(value["expires_at"]),
            )
        if action in {RecordedAdminMfaAction.VERIFY, RecordedAdminMfaAction.ISSUE}:
            identifier_name = (
                "challenge_id"
                if action is RecordedAdminMfaAction.VERIFY
                else "receipt_id"
            )
            value = _mapping(
                body,
                frozenset(
                    {
                        "action",
                        "command_id",
                        "session_id",
                        identifier_name,
                        "expires_at",
                    }
                ),
            )
            command_id = StepUpCommandId(_string(value["command_id"], maximum=43))
            session_id = SessionId(_string(value["session_id"], maximum=43))
            expires_at = _instant(value["expires_at"])
            if action is RecordedAdminMfaAction.VERIFY:
                return cls(
                    action=action,
                    origin=origin,
                    command_id=command_id,
                    session_id=session_id,
                    challenge_id=StepUpChallengeId(
                        _string(value["challenge_id"], maximum=43)
                    ),
                    expires_at=expires_at,
                )
            return cls(
                action=action,
                origin=origin,
                command_id=command_id,
                session_id=session_id,
                receipt_id=StepUpVerificationReceiptId(
                    _string(value["receipt_id"], maximum=43)
                ),
                expires_at=expires_at,
            )
        value = _mapping(
            body,
            frozenset(
                {
                    "action",
                    "command_id",
                    "session_id",
                    "grant_id",
                    "critical_action",
                    "resource_type",
                    "resource_id",
                }
            ),
        )
        try:
            critical_action = CriticalStepUpAction(
                _string(value["critical_action"], maximum=64)
            )
            resource_type = StepUpResourceType(
                _string(value["resource_type"], maximum=64)
            )
            resource_id = UUID(_string(value["resource_id"], maximum=36))
        except ValueError:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        return cls(
            action=action,
            origin=origin,
            command_id=StepUpCommandId(_string(value["command_id"], maximum=43)),
            session_id=SessionId(_string(value["session_id"], maximum=43)),
            grant_id=BoundStepUpGrantId(_string(value["grant_id"], maximum=43)),
            critical_action=critical_action,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    def __repr__(self) -> str:
        return "RecordedAdminMfaHttpRequest(<redacted>)"


@dataclass(frozen=True, slots=True)
class Rfc9457MfaProblem:
    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str

    def __post_init__(self) -> None:
        if (
            type(self.type) is not str
            or not self.type.startswith("urn:raos:problem:st-0402:")
            or type(self.title) is not str
            or not self.title
            or type(self.status) is not int
            or self.status not in {400, 401, 404, 409, 410, 503}
            or type(self.detail) is not str
            or not self.detail
            or self.instance != "urn:raos:recorded:st-0402"
            or type(self.code) is not str
            or not self.code
        ):
            raise ValueError("INVALID_ST0402_PROBLEM") from None

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
class AdminMfaHttpResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: Mapping[str, JsonScalar]

    def __post_init__(self) -> None:
        body = _response_body(self.body)
        header_names = tuple(name.lower() for name, _value in self.headers)
        if (
            type(self.status) is not int
            or self.status not in {200, 201, 202, 400, 401, 404, 409, 410, 503}
            or type(self.headers) is not tuple
            or any(
                type(row) is not tuple
                or len(row) != 2
                or any(type(item) is not str or not item for item in row)
                for row in self.headers
            )
            or len(set(header_names)) != len(header_names)
            or any(
                name in {"set-cookie", "authorization", "location"}
                for name in header_names
            )
        ):
            raise ValueError("INVALID_ST0402_HTTP_RESPONSE") from None
        object.__setattr__(self, "body", MappingProxyType(body))


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAdminMfaDispatch:
    response: AdminMfaHttpResponse
    result: StepUpCommandResult | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        return "RecordedAdminMfaDispatch(<redacted>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded MFA dispatch is not serializable")


def _success(result: StepUpCommandResult) -> AdminMfaHttpResponse:
    outcomes = {
        "BEGIN_CHALLENGE": (202, "RECORDED_CHALLENGE_CREATED"),
        "VERIFY_CHALLENGE": (200, "RECORDED_MFA_VERIFIED"),
        "ISSUE_GRANT": (201, "RECORDED_SINGLE_USE_GRANT_ISSUED"),
        "CONSUME_GRANT": (200, "RECORDED_SINGLE_USE_GRANT_CONSUMED"),
        "REVOKE_GRANT": (200, "RECORDED_SINGLE_USE_GRANT_REVOKED"),
    }
    status, outcome = outcomes[result.operation.value]
    return AdminMfaHttpResponse(
        status=status,
        headers=_SUCCESS_HEADERS,
        body=MappingProxyType(
            {
                "outcome": outcome,
                "audit_sequence": result.audit.sequence,
                "audit_digest": result.audit.digest,
                "delivery": "UNSELECTED_NOT_DELIVERED",
                "route_registered": False,
                "external_authority": False,
            }
        ),
    )


def _problem(code: str) -> AdminMfaHttpResponse:
    if code == "MFA_ROUTE_DISABLED":
        status = 503
        title = "Admin MFA route is disabled"
        detail = f"No external {_EXTERNAL_TARGET} route is registered."
    elif code == "AUTHENTICATION_REJECTED":
        status = 401
        title = "Step-up request rejected"
        detail = "The active Admin session requirement was not satisfied."
    else:
        try:
            failure = StepUpFailureCode(code)
        except ValueError:
            failure = StepUpFailureCode.STORAGE_FAILURE
        if failure in {
            StepUpFailureCode.CLAIM_MALFORMED,
            StepUpFailureCode.ACTION_RESOURCE_MISMATCH,
            StepUpFailureCode.ENTROPY_FAILURE,
        }:
            status = 400
        elif failure in {
            StepUpFailureCode.CHALLENGE_UNKNOWN,
            StepUpFailureCode.RECEIPT_UNKNOWN,
            StepUpFailureCode.GRANT_UNKNOWN,
            StepUpFailureCode.COMMAND_UNKNOWN,
        }:
            status = 404
        elif failure in {
            StepUpFailureCode.CHALLENGE_EXPIRED,
            StepUpFailureCode.RECEIPT_EXPIRED,
            StepUpFailureCode.GRANT_EXPIRED,
            StepUpFailureCode.GRANT_REVOKED,
        }:
            status = 410
        elif failure in {
            StepUpFailureCode.COMMAND_CONFLICT,
            StepUpFailureCode.CHALLENGE_REPLAY,
            StepUpFailureCode.CHALLENGE_MISMATCH,
            StepUpFailureCode.RECEIPT_REPLAY,
            StepUpFailureCode.RECEIPT_MISMATCH,
            StepUpFailureCode.GRANT_REPLAY,
            StepUpFailureCode.GRANT_MISMATCH,
            StepUpFailureCode.SESSION_MISMATCH,
            StepUpFailureCode.PRINCIPAL_MISMATCH,
        }:
            status = 409
        elif failure in {
            StepUpFailureCode.STORAGE_FAILURE,
            StepUpFailureCode.STORAGE_COMMIT_UNKNOWN,
            StepUpFailureCode.DEVELOPMENT_ONLY,
            StepUpFailureCode.ROUTE_DISABLED,
            StepUpFailureCode.VERIFIER_FAILURE,
        }:
            status = 503
        else:
            status = 401
        title = "Step-up request rejected"
        detail = "The recorded MFA step-up request failed closed."
        code = failure.value
    problem = Rfc9457MfaProblem(
        type=f"urn:raos:problem:st-0402:{code.lower().replace('_', '-')}",
        title=title,
        status=status,
        detail=detail,
        instance="urn:raos:recorded:st-0402",
        code=code,
    )
    return AdminMfaHttpResponse(
        status=status,
        headers=_PROBLEM_HEADERS,
        body=problem.as_mapping(),
    )


class DisabledAdminMfaHttpAdapter:
    """No-authority MFA projection plus a strict recorded-only dispatcher."""

    def __init__(
        self, *, environment: RuntimeEnvironment, service: DurableStepUpService
    ) -> None:
        self._environment = _require_development(environment)
        if type(service) is not DurableStepUpService:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        self._service = service

    def dispatch_external(self, document: object) -> RecordedAdminMfaDispatch:
        del document
        return RecordedAdminMfaDispatch(response=_problem("MFA_ROUTE_DISABLED"))

    def dispatch_recorded(
        self, document: object, *, now: datetime
    ) -> RecordedAdminMfaDispatch:
        _require_development(self._environment)
        try:
            observed_at = require_step_up_utc(now)
            request = RecordedAdminMfaHttpRequest.from_document(document)
            if request.action is RecordedAdminMfaAction.RECOVER:
                result = self._service.recover(command_id=request.command_id)
            else:
                if request.session_id is None:
                    _fail(StepUpFailureCode.CLAIM_MALFORMED)
                if request.action is RecordedAdminMfaAction.BEGIN:
                    if (
                        request.critical_action is None
                        or request.resource_type is None
                        or request.resource_id is None
                        or request.expires_at is None
                    ):
                        _fail(StepUpFailureCode.CLAIM_MALFORMED)
                    result = self._service.begin_challenge(
                        command_id=request.command_id,
                        session_id=request.session_id,
                        action=request.critical_action,
                        resource_type=request.resource_type,
                        resource_id=request.resource_id,
                        now=observed_at,
                        expires_at=request.expires_at,
                    )
                elif request.action is RecordedAdminMfaAction.VERIFY:
                    if request.challenge_id is None or request.expires_at is None:
                        _fail(StepUpFailureCode.CLAIM_MALFORMED)
                    result = self._service.verify_challenge(
                        command_id=request.command_id,
                        session_id=request.session_id,
                        challenge_id=request.challenge_id,
                        now=observed_at,
                        expires_at=request.expires_at,
                    )
                elif request.action is RecordedAdminMfaAction.ISSUE:
                    if request.receipt_id is None or request.expires_at is None:
                        _fail(StepUpFailureCode.CLAIM_MALFORMED)
                    result = self._service.issue_grant(
                        command_id=request.command_id,
                        session_id=request.session_id,
                        receipt_id=request.receipt_id,
                        now=observed_at,
                        expires_at=request.expires_at,
                    )
                else:
                    if (
                        request.grant_id is None
                        or request.critical_action is None
                        or request.resource_type is None
                        or request.resource_id is None
                    ):
                        _fail(StepUpFailureCode.CLAIM_MALFORMED)
                    operation = (
                        self._service.consume_grant
                        if request.action is RecordedAdminMfaAction.CONSUME
                        else self._service.revoke_grant
                    )
                    result = operation(
                        command_id=request.command_id,
                        session_id=request.session_id,
                        grant_id=request.grant_id,
                        action=request.critical_action,
                        resource_type=request.resource_type,
                        resource_id=request.resource_id,
                        now=observed_at,
                    )
            return RecordedAdminMfaDispatch(response=_success(result), result=result)
        except AuthenticationFailure:
            return RecordedAdminMfaDispatch(
                response=_problem("AUTHENTICATION_REJECTED")
            )
        except StepUpFailure as error:
            return RecordedAdminMfaDispatch(response=_problem(error.code.value))
        except Exception:
            return RecordedAdminMfaDispatch(
                response=_problem(StepUpFailureCode.STORAGE_FAILURE.value)
            )

    def __repr__(self) -> str:
        return "DisabledAdminMfaHttpAdapter(route_registered=false, state=<redacted>)"


__all__ = [
    "AdminMfaHttpResponse",
    "DisabledAdminMfaHttpAdapter",
    "RecordedAdminMfaAction",
    "RecordedAdminMfaDispatch",
    "RecordedAdminMfaHttpRequest",
    "RecordedMfaLoopbackOrigin",
    "Rfc9457MfaProblem",
]
