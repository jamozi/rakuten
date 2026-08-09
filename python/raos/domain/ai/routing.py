"""Immutable provider-neutral values for synthetic development AI routing.

ST-0704 deliberately models only authorization and process-local cost control.
These values carry no prompt, source content, credential, provider account,
production price, or provider SDK type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, final


_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SYNTHETIC_PREFIX = "synthetic."
_MAX_SIGNED_BIGINT = (1 << 63) - 1
_REDACTED = "<redacted-synthetic-ai-routing>"


class RoutingFailureCode(str, Enum):
    """Stable sanitized classifications for the local routing boundary."""

    INVALID_REQUEST = "INVALID_REQUEST"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    UNKNOWN_TASK = "UNKNOWN_TASK"
    UNKNOWN_ROUTE = "UNKNOWN_ROUTE"
    UNKNOWN_ROUTE_VERSION = "UNKNOWN_ROUTE_VERSION"
    UNKNOWN_MODEL = "UNKNOWN_MODEL"
    INELIGIBLE_CANDIDATE = "INELIGIBLE_CANDIDATE"
    REGISTRY_UNAVAILABLE = "REGISTRY_UNAVAILABLE"
    ELIGIBILITY_UNAVAILABLE = "ELIGIBILITY_UNAVAILABLE"
    QUOTE_MISMATCH = "QUOTE_MISMATCH"
    QUOTE_NOT_YET_VALID = "QUOTE_NOT_YET_VALID"
    QUOTE_EXPIRED = "QUOTE_EXPIRED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    RESERVATION_UNKNOWN = "RESERVATION_UNKNOWN"
    RESERVATION_MISMATCH = "RESERVATION_MISMATCH"
    RESERVATION_REPLAY = "RESERVATION_REPLAY"
    RESERVATION_NOT_YET_VALID = "RESERVATION_NOT_YET_VALID"
    RESERVATION_EXPIRED = "RESERVATION_EXPIRED"
    CONTROL_FAILURE = "CONTROL_FAILURE"
    FALLBACK_PROHIBITED = "FALLBACK_PROHIBITED"


@final
class RoutingFailure(RuntimeError):
    """Immutable routing failure that retains no rejected input or raw error."""

    __slots__ = ("_code", "_sealed")
    _code: RoutingFailureCode
    _sealed: bool

    def __init__(self, code: RoutingFailureCode) -> None:
        if type(code) is not RoutingFailureCode:
            raise TypeError("code must be an exact RoutingFailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)
        object.__setattr__(self, "_sealed", True)

    @property
    def code(self) -> RoutingFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        if name == "__traceback__":
            BaseException.__setattr__(self, name, value)
            return
        del value
        raise AttributeError("RoutingFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("RoutingFailure is immutable")

    def __repr__(self) -> str:
        return f"RoutingFailure(code={self.code!r})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("routing failure serialization is not supported")


def fail_routing(code: RoutingFailureCode) -> NoReturn:
    """Raise one stable failure without chaining an untrusted exception."""

    raise RoutingFailure(code) from None


def require_routing_utc(value: object) -> datetime:
    """Accept only an exact datetime using the explicit UTC singleton."""

    if type(value) is not datetime or value.tzinfo is not UTC:
        fail_routing(RoutingFailureCode.INVALID_REQUEST)
    return value


def _require_identifier(value: object) -> str:
    if type(value) is not str or _SAFE_IDENTIFIER.fullmatch(value) is None:
        fail_routing(RoutingFailureCode.INVALID_REQUEST)
    return value


def _require_synthetic_identifier(value: object) -> str:
    identifier = _require_identifier(value)
    if not identifier.startswith(_SYNTHETIC_PREFIX):
        fail_routing(RoutingFailureCode.INVALID_REQUEST)
    return identifier


def _require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_routing(RoutingFailureCode.INVALID_REQUEST)
    return value


def _require_jpy(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_SIGNED_BIGINT:
        fail_routing(RoutingFailureCode.INVALID_REQUEST)
    return value


def _canonical_sha256(value: dict[str, object]) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        fail_routing(RoutingFailureCode.INVALID_REQUEST)
    return hashlib.sha256(encoded).hexdigest()


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("synthetic routing value serialization is not supported")


@final
@dataclass(frozen=True, slots=True, repr=False)
class RouteIdentity(_RedactedValue):
    """One exact synthetic model choice bound to a canonical task route."""

    task_code: str
    route_code: str
    route_version: str
    model_id: str

    def __post_init__(self) -> None:
        _require_identifier(self.task_code)
        _require_identifier(self.route_code)
        _require_synthetic_identifier(self.route_version)
        _require_synthetic_identifier(self.model_id)


@final
@dataclass(frozen=True, slots=True, repr=False)
class SyntheticRouteCertification(_RedactedValue):
    """Explicit local eligibility fixture; never a production certification."""

    identity: RouteIdentity
    certification_id: str
    task_binding_sha256: str
    route_sha256: str
    eligible: bool
    valid_from: datetime
    expires_at: datetime
    selection_rank: int = 0

    def __post_init__(self) -> None:
        if type(self.identity) is not RouteIdentity:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        _require_synthetic_identifier(self.certification_id)
        _require_sha256(self.task_binding_sha256)
        _require_sha256(self.route_sha256)
        if type(self.eligible) is not bool:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        valid_from = require_routing_utc(self.valid_from)
        expires_at = require_routing_utc(self.expires_at)
        if expires_at <= valid_from:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        if (
            type(self.selection_rank) is not int
            or not 0 <= self.selection_rank <= _MAX_SIGNED_BIGINT
        ):
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        object.__setattr__(self, "valid_from", valid_from)
        object.__setattr__(self, "expires_at", expires_at)


@final
@dataclass(frozen=True, slots=True, repr=False)
class SyntheticRouteQuote(_RedactedValue):
    """Direct-JPY synthetic reservation quote with an explicit validity window."""

    identity: RouteIdentity
    certification_id: str
    quote_id: str
    estimated_cost_jpy: int
    valid_from: datetime
    expires_at: datetime
    quote_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.identity) is not RouteIdentity:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        _require_synthetic_identifier(self.certification_id)
        _require_synthetic_identifier(self.quote_id)
        _require_jpy(self.estimated_cost_jpy)
        valid_from = require_routing_utc(self.valid_from)
        expires_at = require_routing_utc(self.expires_at)
        if expires_at <= valid_from:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        object.__setattr__(self, "valid_from", valid_from)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(
            self,
            "quote_sha256",
            _canonical_sha256(
                {
                    "kind": "SYNTHETIC_TEST_ONLY",
                    "task_code": self.identity.task_code,
                    "route_code": self.identity.route_code,
                    "route_version": self.identity.route_version,
                    "model_id": self.identity.model_id,
                    "certification_id": self.certification_id,
                    "quote_id": self.quote_id,
                    "estimated_cost_jpy": self.estimated_cost_jpy,
                    "valid_from": valid_from.isoformat(),
                    "expires_at": expires_at.isoformat(),
                }
            ),
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RouteReservationRequest(_RedactedValue):
    """One replay-protected request to authorize and reserve a synthetic route."""

    operation_id: str
    task_code: str
    quote: SyntheticRouteQuote
    reservation_expires_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.operation_id)
        _require_identifier(self.task_code)
        if type(self.quote) is not SyntheticRouteQuote:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        expires_at = require_routing_utc(self.reservation_expires_at)
        object.__setattr__(self, "reservation_expires_at", expires_at)


@final
@dataclass(frozen=True, slots=True, repr=False)
class ReservationIntent(_RedactedValue):
    """Exact application-authorized material submitted to the atomic port."""

    operation_id: str
    identity: RouteIdentity
    task_binding_sha256: str
    route_sha256: str
    certification_id: str
    quote_sha256: str
    reserved_jpy: int
    authorized_at: datetime
    expires_at: datetime
    fingerprint_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.operation_id)
        if type(self.identity) is not RouteIdentity:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        _require_sha256(self.task_binding_sha256)
        _require_sha256(self.route_sha256)
        _require_synthetic_identifier(self.certification_id)
        _require_sha256(self.quote_sha256)
        _require_jpy(self.reserved_jpy)
        authorized_at = require_routing_utc(self.authorized_at)
        expires_at = require_routing_utc(self.expires_at)
        if expires_at <= authorized_at:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        object.__setattr__(self, "authorized_at", authorized_at)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(
            self,
            "fingerprint_sha256",
            _canonical_sha256(
                {
                    "kind": "SYNTHETIC_TEST_ONLY",
                    "operation_id": self.operation_id,
                    "task_code": self.identity.task_code,
                    "route_code": self.identity.route_code,
                    "route_version": self.identity.route_version,
                    "model_id": self.identity.model_id,
                    "task_binding_sha256": self.task_binding_sha256,
                    "route_sha256": self.route_sha256,
                    "certification_id": self.certification_id,
                    "quote_sha256": self.quote_sha256,
                    "reserved_jpy": self.reserved_jpy,
                    "authorized_at": authorized_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                }
            ),
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class BudgetReservation(_RedactedValue):
    """Opaque process-local reservation handle returned by the control port."""

    reservation_id: str
    operation_id: str
    intent_sha256: str
    identity: RouteIdentity
    quote_sha256: str
    reserved_jpy: int
    reserved_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_sha256(self.reservation_id)
        _require_identifier(self.operation_id)
        _require_sha256(self.intent_sha256)
        if type(self.identity) is not RouteIdentity:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        _require_sha256(self.quote_sha256)
        _require_jpy(self.reserved_jpy)
        reserved_at = require_routing_utc(self.reserved_at)
        expires_at = require_routing_utc(self.expires_at)
        if expires_at <= reserved_at:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        object.__setattr__(self, "reserved_at", reserved_at)
        object.__setattr__(self, "expires_at", expires_at)

    @classmethod
    def from_intent(cls, intent: ReservationIntent) -> BudgetReservation:
        if type(intent) is not ReservationIntent:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        reservation_id = hashlib.sha256(
            b"ST-0704\x00" + intent.fingerprint_sha256.encode("ascii")
        ).hexdigest()
        return cls(
            reservation_id=reservation_id,
            operation_id=intent.operation_id,
            intent_sha256=intent.fingerprint_sha256,
            identity=intent.identity,
            quote_sha256=intent.quote_sha256,
            reserved_jpy=intent.reserved_jpy,
            reserved_at=intent.authorized_at,
            expires_at=intent.expires_at,
        )

    def matches_intent(self, intent: ReservationIntent) -> bool:
        return (
            type(intent) is ReservationIntent
            and self.operation_id == intent.operation_id
            and self.intent_sha256 == intent.fingerprint_sha256
            and self.identity == intent.identity
            and self.quote_sha256 == intent.quote_sha256
            and self.reserved_jpy == intent.reserved_jpy
            and self.reserved_at == intent.authorized_at
            and self.expires_at == intent.expires_at
            and self == BudgetReservation.from_intent(intent)
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class BudgetCommit(_RedactedValue):
    """Immutable receipt for one terminal synthetic reservation commit."""

    reservation_id: str
    intent_sha256: str
    committed_jpy: int
    committed_at: datetime

    def __post_init__(self) -> None:
        _require_sha256(self.reservation_id)
        _require_sha256(self.intent_sha256)
        _require_jpy(self.committed_jpy)
        object.__setattr__(self, "committed_at", require_routing_utc(self.committed_at))


@final
@dataclass(frozen=True, slots=True, repr=False)
class BudgetRelease(_RedactedValue):
    """Immutable receipt for one terminal synthetic reservation release."""

    reservation_id: str
    intent_sha256: str
    released_jpy: int
    released_at: datetime

    def __post_init__(self) -> None:
        _require_sha256(self.reservation_id)
        _require_sha256(self.intent_sha256)
        _require_jpy(self.released_jpy)
        object.__setattr__(self, "released_at", require_routing_utc(self.released_at))


class FallbackPolicy(str, Enum):
    """The only fallback policy authorized by this safe local slice."""

    DENY_ALL = "DENY_ALL"


@final
@dataclass(frozen=True, slots=True, repr=False)
class AuthorizedRouteReservation(_RedactedValue):
    """Synthetic route authorization bound to one process-local reservation."""

    identity: RouteIdentity
    certification_id: str
    task_binding_sha256: str
    route_sha256: str
    reservation: BudgetReservation

    def __post_init__(self) -> None:
        if type(self.identity) is not RouteIdentity:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        _require_synthetic_identifier(self.certification_id)
        _require_sha256(self.task_binding_sha256)
        _require_sha256(self.route_sha256)
        if type(self.reservation) is not BudgetReservation:
            fail_routing(RoutingFailureCode.INVALID_REQUEST)
        if self.reservation.identity != self.identity:
            fail_routing(RoutingFailureCode.RESERVATION_MISMATCH)
        bound_intent = ReservationIntent(
            operation_id=self.reservation.operation_id,
            identity=self.identity,
            task_binding_sha256=self.task_binding_sha256,
            route_sha256=self.route_sha256,
            certification_id=self.certification_id,
            quote_sha256=self.reservation.quote_sha256,
            reserved_jpy=self.reservation.reserved_jpy,
            authorized_at=self.reservation.reserved_at,
            expires_at=self.reservation.expires_at,
        )
        if not self.reservation.matches_intent(bound_intent):
            fail_routing(RoutingFailureCode.RESERVATION_MISMATCH)

    @property
    def fallback_policy(self) -> FallbackPolicy:
        return FallbackPolicy.DENY_ALL

    @property
    def max_fallbacks(self) -> int:
        return 0


__all__ = [
    "AuthorizedRouteReservation",
    "BudgetCommit",
    "BudgetRelease",
    "BudgetReservation",
    "FallbackPolicy",
    "ReservationIntent",
    "RouteIdentity",
    "RouteReservationRequest",
    "RoutingFailure",
    "RoutingFailureCode",
    "SyntheticRouteCertification",
    "SyntheticRouteQuote",
    "fail_routing",
    "require_routing_utc",
]
