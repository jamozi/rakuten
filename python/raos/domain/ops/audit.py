"""Closed, immutable audit values for the ST-0405 local recording seam.

This module models only the fixed fields owned by the canonical
``ops.audit_event`` contract.  It intentionally has no arbitrary details
mapping and no database, query, retention, transport, logging, or provider
behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import re
from typing import ClassVar, NoReturn, SupportsIndex, final
from uuid import UUID

from raos.domain.iam.authorization import (
    ActionCode,
    AuthorizationGrant,
    AuthorizationTarget,
    CorrelationId,
    ResourceScope,
    RuleId,
)


_TOKEN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._:/-]{0,126}[A-Za-z0-9])?\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REDACTED = "<redacted-audit-value>"
_INVALID = "invalid audit value"


def _invalid() -> NoReturn:
    raise ValueError(_INVALID) from None


def _require_uuid(value: object) -> UUID:
    if type(value) is not UUID or value.int == 0:
        _invalid()
    return value


def _require_utc(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is not timezone.utc:
        _invalid()
    return value


def _require_hash(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _invalid()
    return value


class AuditActorType(str, Enum):
    """Canonical actor taxonomy from ``ops.audit_event``."""

    USER = "USER"
    SERVICE = "SERVICE"
    SCHEDULE = "SCHEDULE"
    SYSTEM = "SYSTEM"
    ANONYMOUS = "ANONYMOUS"


class AuditOutcome(str, Enum):
    """Canonical audit outcomes from ``ops.audit_event``."""

    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    FAILED = "FAILED"
    NOOP = "NOOP"


class AuditSeverity(str, Enum):
    """Canonical audit severities from ``ops.audit_event``."""

    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("audit value serialization is not supported")


class _BoundedToken(_RedactedValue):
    __slots__ = ("_sealed", "_value")
    _value: str
    _sealed: bool
    _maximum_length: ClassVar[int] = 128

    def __init__(self, value: str) -> None:
        if (
            type(value) is not str
            or not 1 <= len(value) <= self._maximum_length
            or _TOKEN.fullmatch(value) is None
        ):
            _invalid()
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "_sealed", True)

    @property
    def value(self) -> str:
        return self._value

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and self._value == other._value

    def __hash__(self) -> int:
        return hash((type(self), self._value))


@final
class AuditAction(_BoundedToken):
    """One bounded ASCII action derived from an authorization grant."""

    __slots__ = ()


@final
class AuditTargetType(_BoundedToken):
    """One bounded ASCII target type derived from an authorization grant."""

    __slots__ = ()


@final
class AuditReasonCode(_BoundedToken):
    """One closed-shape, non-sensitive reason code, never a free-form message."""

    __slots__ = ()


@final
class AuditRequestId(_BoundedToken):
    """One optional bounded request identifier, never a header collection."""

    __slots__ = ()


@final
class AuditEventId(_RedactedValue):
    """One exact, non-nil UUID selected by an inward trusted context source."""

    __slots__ = ("_sealed", "_value")
    _value: UUID
    _sealed: bool

    def __init__(self, value: UUID) -> None:
        object.__setattr__(self, "_value", _require_uuid(value))
        object.__setattr__(self, "_sealed", True)

    @property
    def value(self) -> UUID:
        return self._value

    def require_valid(self) -> None:
        _require_uuid(self._value)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuditEventId is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AuditEventId is immutable")

    def __eq__(self, other: object) -> bool:
        return type(other) is AuditEventId and self._value == other._value

    def __hash__(self) -> int:
        return hash((AuditEventId, self._value))


@final
class AuditActor(_RedactedValue):
    """One canonical actor with explicit identifier-presence rules.

    User, service, and schedule actors require a non-nil UUID.  System and
    anonymous actors forbid an identifier.  This prevents an absent human or
    workload identity from being silently reclassified as a system action.
    """

    __slots__ = ("_actor_id", "_actor_type", "_sealed")
    _actor_type: AuditActorType
    _actor_id: UUID | None
    _sealed: bool

    def __init__(self, *, actor_type: AuditActorType, actor_id: UUID | None) -> None:
        identified = actor_type in {
            AuditActorType.USER,
            AuditActorType.SERVICE,
            AuditActorType.SCHEDULE,
        }
        unbound = actor_type in {AuditActorType.SYSTEM, AuditActorType.ANONYMOUS}
        if (
            type(actor_type) is not AuditActorType
            or (identified and (type(actor_id) is not UUID or actor_id.int == 0))
            or (unbound and actor_id is not None)
        ):
            _invalid()
        object.__setattr__(self, "_actor_type", actor_type)
        object.__setattr__(self, "_actor_id", actor_id)
        object.__setattr__(self, "_sealed", True)

    @property
    def actor_type(self) -> AuditActorType:
        return self._actor_type

    @property
    def actor_id(self) -> UUID | None:
        return self._actor_id

    def require_valid(self) -> None:
        AuditActor(actor_type=self._actor_type, actor_id=self._actor_id)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuditActor is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AuditActor is immutable")

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is AuditActor
            and self._actor_type is other._actor_type
            and self._actor_id == other._actor_id
        )

    def __hash__(self) -> int:
        return hash((self._actor_type, self._actor_id))


@final
class AuditGrantBinding(_RedactedValue):
    """Exact critical action, target, and correlation derived from one grant."""

    __slots__ = (
        "_action",
        "_correlation_id",
        "_sealed",
        "_target_id",
        "_target_type",
    )
    _action: AuditAction
    _target_type: AuditTargetType
    _target_id: UUID
    _correlation_id: UUID
    _sealed: bool

    def __init__(self, *, grant: AuthorizationGrant) -> None:
        if type(grant) is not AuthorizationGrant:
            _invalid()
        grant_failed = False
        action: object = None
        target: object = None
        correlation: object = None
        matched_rule: object = None
        try:
            action = grant.action
            target = grant.target
            correlation = grant.correlation_id
            matched_rule = grant.matched_rule_id
        except Exception:
            grant_failed = True
        if (
            grant_failed
            or type(action) is not ActionCode
            or type(target) is not AuthorizationTarget
            or type(target.scope) is not ResourceScope
            or type(correlation) is not CorrelationId
            or type(matched_rule) is not RuleId
        ):
            _invalid()
        target_id = _require_uuid(target.scope.resource_id)
        correlation_failed = False
        correlation_id: UUID | None = None
        try:
            correlation_id = UUID(correlation.value)
        except AttributeError, TypeError, ValueError:
            correlation_failed = True
        if (
            correlation_failed
            or correlation_id is None
            or str(correlation_id) != correlation.value
            or correlation_id.int == 0
        ):
            _invalid()
        object.__setattr__(self, "_action", AuditAction(action.value))
        object.__setattr__(
            self, "_target_type", AuditTargetType(target.scope.kind.value)
        )
        object.__setattr__(self, "_target_id", target_id)
        object.__setattr__(self, "_correlation_id", correlation_id)
        object.__setattr__(self, "_sealed", True)

    @property
    def action(self) -> AuditAction:
        return self._action

    @property
    def target_type(self) -> AuditTargetType:
        return self._target_type

    @property
    def target_id(self) -> UUID:
        return self._target_id

    @property
    def correlation_id(self) -> UUID:
        return self._correlation_id

    def require_valid(self) -> None:
        if (
            type(self._action) is not AuditAction
            or type(self._target_type) is not AuditTargetType
        ):
            _invalid()
        AuditAction(self._action.value)
        AuditTargetType(self._target_type.value)
        _require_uuid(self._target_id)
        _require_uuid(self._correlation_id)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuditGrantBinding is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AuditGrantBinding is immutable")

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is AuditGrantBinding
            and self._action == other._action
            and self._target_type == other._target_type
            and self._target_id == other._target_id
            and self._correlation_id == other._correlation_id
        )

    def __hash__(self) -> int:
        return hash(
            (
                self._action,
                self._target_type,
                self._target_id,
                self._correlation_id,
            )
        )


@final
class AuditContext(_RedactedValue):
    """Trusted synthetic context bound to one exact authorization grant."""

    __slots__ = (
        "_actor",
        "_binding",
        "_event_id",
        "_occurred_at",
        "_request_id",
        "_sealed",
    )
    _event_id: AuditEventId
    _actor: AuditActor
    _occurred_at: datetime
    _request_id: AuditRequestId | None
    _binding: AuditGrantBinding
    _sealed: bool

    def __init__(
        self,
        *,
        grant: AuthorizationGrant,
        event_id: AuditEventId,
        actor: AuditActor,
        occurred_at: datetime,
        request_id: AuditRequestId | None = None,
    ) -> None:
        if (
            type(event_id) is not AuditEventId
            or type(actor) is not AuditActor
            or (request_id is not None and type(request_id) is not AuditRequestId)
        ):
            _invalid()
        event_id.require_valid()
        actor.require_valid()
        object.__setattr__(self, "_event_id", event_id)
        object.__setattr__(self, "_actor", actor)
        object.__setattr__(self, "_occurred_at", _require_utc(occurred_at))
        object.__setattr__(self, "_request_id", request_id)
        object.__setattr__(self, "_binding", AuditGrantBinding(grant=grant))
        object.__setattr__(self, "_sealed", True)

    @property
    def event_id(self) -> AuditEventId:
        return self._event_id

    @property
    def actor(self) -> AuditActor:
        return self._actor

    @property
    def occurred_at(self) -> datetime:
        return self._occurred_at

    @property
    def request_id(self) -> AuditRequestId | None:
        return self._request_id

    @property
    def action(self) -> AuditAction:
        return self._binding.action

    @property
    def target_type(self) -> AuditTargetType:
        return self._binding.target_type

    @property
    def target_id(self) -> UUID:
        return self._binding.target_id

    @property
    def correlation_id(self) -> UUID:
        return self._binding.correlation_id

    def require_bound_to(self, grant: AuthorizationGrant) -> None:
        if (
            type(self._event_id) is not AuditEventId
            or type(self._actor) is not AuditActor
            or type(self._binding) is not AuditGrantBinding
            or (
                self._request_id is not None
                and type(self._request_id) is not AuditRequestId
            )
        ):
            _invalid()
        self._event_id.require_valid()
        self._actor.require_valid()
        _require_utc(self._occurred_at)
        self._binding.require_valid()
        if self._binding != AuditGrantBinding(grant=grant):
            _invalid()

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuditContext is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AuditContext is immutable")


@final
class AuditEvent(_RedactedValue):
    """One fixed-field, immutable audit event with a canonical SHA-256 digest."""

    __slots__ = (
        "_actor",
        "_after_hash",
        "_before_hash",
        "_binding",
        "_digest",
        "_event_id",
        "_occurred_at",
        "_outcome",
        "_reason_code",
        "_request_id",
        "_sealed",
        "_severity",
    )
    _event_id: AuditEventId
    _occurred_at: datetime
    _actor: AuditActor
    _binding: AuditGrantBinding
    _outcome: AuditOutcome
    _severity: AuditSeverity
    _reason_code: AuditReasonCode
    _request_id: AuditRequestId | None
    _before_hash: str | None
    _after_hash: str | None
    _digest: str
    _sealed: bool

    def __init__(
        self,
        *,
        grant: AuthorizationGrant,
        context: AuditContext,
        outcome: AuditOutcome,
        severity: AuditSeverity,
        reason_code: AuditReasonCode,
        before_hash: str | None = None,
        after_hash: str | None = None,
    ) -> None:
        if (
            type(context) is not AuditContext
            or type(outcome) is not AuditOutcome
            or type(severity) is not AuditSeverity
            or type(reason_code) is not AuditReasonCode
        ):
            _invalid()
        context.require_bound_to(grant)
        if before_hash is not None:
            _require_hash(before_hash)
        if after_hash is not None:
            _require_hash(after_hash)
        object.__setattr__(self, "_event_id", context.event_id)
        object.__setattr__(self, "_occurred_at", context.occurred_at)
        object.__setattr__(self, "_actor", context.actor)
        object.__setattr__(self, "_binding", AuditGrantBinding(grant=grant))
        object.__setattr__(self, "_outcome", outcome)
        object.__setattr__(self, "_severity", severity)
        object.__setattr__(self, "_reason_code", reason_code)
        object.__setattr__(self, "_request_id", context.request_id)
        object.__setattr__(self, "_before_hash", before_hash)
        object.__setattr__(self, "_after_hash", after_hash)
        object.__setattr__(self, "_digest", self._calculate_digest())
        object.__setattr__(self, "_sealed", True)

    @property
    def event_id(self) -> AuditEventId:
        return self._event_id

    @property
    def occurred_at(self) -> datetime:
        return self._occurred_at

    @property
    def actor(self) -> AuditActor:
        return self._actor

    @property
    def actor_type(self) -> AuditActorType:
        return self._actor.actor_type

    @property
    def actor_id(self) -> UUID | None:
        return self._actor.actor_id

    @property
    def action(self) -> AuditAction:
        return self._binding.action

    @property
    def target_type(self) -> AuditTargetType:
        return self._binding.target_type

    @property
    def target_id(self) -> UUID:
        return self._binding.target_id

    @property
    def outcome(self) -> AuditOutcome:
        return self._outcome

    @property
    def severity(self) -> AuditSeverity:
        return self._severity

    @property
    def correlation_id(self) -> UUID:
        return self._binding.correlation_id

    @property
    def request_id(self) -> AuditRequestId | None:
        return self._request_id

    @property
    def reason_code(self) -> AuditReasonCode:
        return self._reason_code

    @property
    def before_hash(self) -> str | None:
        return self._before_hash

    @property
    def after_hash(self) -> str | None:
        return self._after_hash

    @property
    def digest(self) -> str:
        return self._digest

    def _calculate_digest(self) -> str:
        parts = (
            "RAOS_AUDIT_EVENT_V1",
            self._event_id.value.hex,
            self._occurred_at.isoformat(timespec="microseconds"),
            self._actor.actor_type.value,
            "" if self._actor.actor_id is None else self._actor.actor_id.hex,
            self._binding.action.value,
            self._binding.target_type.value,
            self._binding.target_id.hex,
            self._outcome.value,
            self._severity.value,
            self._binding.correlation_id.hex,
            "" if self._request_id is None else self._request_id.value,
            self._reason_code.value,
            "" if self._before_hash is None else self._before_hash,
            "" if self._after_hash is None else self._after_hash,
        )
        return hashlib.sha256("\x1f".join(parts).encode("ascii")).hexdigest()

    def require_valid(self) -> None:
        if (
            type(self._event_id) is not AuditEventId
            or type(self._actor) is not AuditActor
            or type(self._binding) is not AuditGrantBinding
            or type(self._outcome) is not AuditOutcome
            or type(self._severity) is not AuditSeverity
            or type(self._reason_code) is not AuditReasonCode
            or (
                self._request_id is not None
                and type(self._request_id) is not AuditRequestId
            )
            or (self._before_hash is not None and type(self._before_hash) is not str)
            or (self._after_hash is not None and type(self._after_hash) is not str)
            or type(self._digest) is not str
        ):
            _invalid()
        self._event_id.require_valid()
        self._actor.require_valid()
        self._binding.require_valid()
        _require_utc(self._occurred_at)
        AuditReasonCode(self._reason_code.value)
        if self._before_hash is not None:
            _require_hash(self._before_hash)
        if self._after_hash is not None:
            _require_hash(self._after_hash)
        if (
            _SHA256.fullmatch(self._digest) is None
            or self._digest != self._calculate_digest()
        ):
            _invalid()

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuditEvent is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AuditEvent is immutable")


__all__ = [
    "AuditAction",
    "AuditActor",
    "AuditActorType",
    "AuditContext",
    "AuditEvent",
    "AuditEventId",
    "AuditGrantBinding",
    "AuditOutcome",
    "AuditReasonCode",
    "AuditRequestId",
    "AuditSeverity",
    "AuditTargetType",
]
