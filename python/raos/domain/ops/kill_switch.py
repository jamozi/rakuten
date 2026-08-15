"""Immutable, provider-neutral values for the ST-1405 kill-switch seam.

The module deliberately models neither persistence nor delivery.  It carries
only bounded identifiers, generation/state metadata, redacted reason codes,
and one in-memory event intent compatible with the installed v1 contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
import hashlib
import re
from typing import NoReturn, SupportsIndex, final
from uuid import UUID


_FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z")
_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{7,127}\Z")
_REASON_CODE = re.compile(r"[A-Z][A-Z0-9_]{9,63}\Z")
_REDACTED = "<redacted-kill-switch-value>"
MAX_KILL_SWITCH_CACHE_ENTRIES = 10_000
MAX_KILL_SWITCH_GENERATION = (1 << 63) - 1


class KillSwitchKind(str, Enum):
    """The two independent emergency controls owned by ST-1405."""

    PUBLICATION = "PUBLICATION"
    AFFILIATE_LINK = "AFFILIATE_LINK"


class KillSwitchScopeType(str, Enum):
    """The closed provider-neutral scope hierarchy implemented by this slice."""

    GLOBAL = "GLOBAL"
    SITE = "SITE"
    CATEGORY = "CATEGORY"
    ARTICLE = "ARTICLE"


class KillSwitchFailureCode(str, Enum):
    """Stable value-free command and adapter failure classifications."""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    EXPIRES_AT_UNSUPPORTED = "EXPIRES_AT_UNSUPPORTED"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    STEP_UP_REQUIRED = "STEP_UP_REQUIRED"
    STATE_MISSING = "STATE_MISSING"
    STATE_CONFLICT = "STATE_CONFLICT"
    GENERATION_CONFLICT = "GENERATION_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    STORE_FAILURE = "STORE_FAILURE"


class KillSwitchEligibilityCode(str, Enum):
    """Closed eligibility outcomes; every non-eligible outcome fails safe."""

    ELIGIBLE = "ELIGIBLE"
    ENGAGED = "ENGAGED"
    CACHE_UNAVAILABLE = "CACHE_UNAVAILABLE"
    CACHE_MALFORMED = "CACHE_MALFORMED"
    CACHE_INCOMPLETE = "CACHE_INCOMPLETE"
    CACHE_STALE = "CACHE_STALE"
    CACHE_ENTRY_MISSING = "CACHE_ENTRY_MISSING"
    CACHE_DOWNGRADED = "CACHE_DOWNGRADED"


@final
class KillSwitchFailure(RuntimeError):
    """Immutable failure that retains no rejected value or exception text."""

    __slots__ = ("_code",)
    _code: KillSwitchFailureCode

    def __init__(self, code: KillSwitchFailureCode) -> None:
        if type(code) is not KillSwitchFailureCode:
            raise TypeError("code must be an exact KillSwitchFailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)

    @property
    def code(self) -> KillSwitchFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        if name == "__traceback__":
            super().__setattr__(name, value)
            return
        del name, value
        raise AttributeError("KillSwitchFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("KillSwitchFailure is immutable")

    def __repr__(self) -> str:
        return f"KillSwitchFailure(code={self.code!r})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("kill-switch failure serialization is not supported")


def fail_kill_switch(code: KillSwitchFailureCode) -> NoReturn:
    """Raise one sanitized failure without chaining an active exception."""

    raise KillSwitchFailure(code) from None


def require_kill_switch_utc(value: object) -> datetime:
    """Require an exact aware UTC timestamp; never infer or convert a zone."""

    if type(value) is not datetime or value.tzinfo is not UTC:
        fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
    return value


def _require_uuid(value: object) -> UUID:
    if type(value) is not UUID:
        fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
    return value


def require_kill_switch_generation(value: object) -> int:
    """Require one exact non-negative signed-bigint generation value."""

    if type(value) is not int or value < 0 or value > MAX_KILL_SWITCH_GENERATION:
        fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
    return value


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("kill-switch value serialization is not supported")


@final
class KillSwitchFingerprint(_RedactedValue):
    """A SHA-256 fingerprint, never the command or idempotency-key bytes."""

    __slots__ = ("_value",)
    _value: str

    def __init__(self, value: str) -> None:
        if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        object.__setattr__(self, "_value", value)

    @property
    def value(self) -> str:
        return self._value

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("KillSwitchFingerprint is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("KillSwitchFingerprint is immutable")

    def __eq__(self, other: object) -> bool:
        return type(other) is KillSwitchFingerprint and self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)


@final
class KillSwitchIdempotencyKey(_RedactedValue):
    """A bounded opaque command key whose display is always redacted."""

    __slots__ = ("_value",)
    _value: str

    def __init__(self, value: str) -> None:
        if type(value) is not str or _IDEMPOTENCY_KEY.fullmatch(value) is None:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        object.__setattr__(self, "_value", value)

    def fingerprint(self) -> KillSwitchFingerprint:
        return KillSwitchFingerprint(
            hashlib.sha256(self._value.encode("ascii")).hexdigest()
        )

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("KillSwitchIdempotencyKey is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("KillSwitchIdempotencyKey is immutable")


@final
class KillSwitchReasonCode(_RedactedValue):
    """A stable non-narrative reason code safe for the recorded event intent."""

    __slots__ = ("_value",)
    _value: str

    def __init__(self, value: str) -> None:
        if type(value) is not str or _REASON_CODE.fullmatch(value) is None:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        object.__setattr__(self, "_value", value)

    def event_value(self) -> str:
        """Expose the bounded code only at the explicit event-contract boundary."""

        return self._value

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("KillSwitchReasonCode is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("KillSwitchReasonCode is immutable")

    def __eq__(self, other: object) -> bool:
        return type(other) is KillSwitchReasonCode and self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)


@dataclass(frozen=True, slots=True, repr=False)
class KillSwitchKey(_RedactedValue):
    """Unique switch identity within the scope/type key space."""

    scope_type: KillSwitchScopeType
    scope_id: UUID | None
    switch_type: KillSwitchKind

    def __post_init__(self) -> None:
        if (
            type(self.scope_type) is not KillSwitchScopeType
            or type(self.switch_type) is not KillSwitchKind
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        if self.scope_type is KillSwitchScopeType.GLOBAL:
            if self.scope_id is not None:
                fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        else:
            _require_uuid(self.scope_id)


@dataclass(frozen=True, slots=True, repr=False)
class KillSwitchChangeCommand(_RedactedValue):
    """One exact compare-and-swap request with no implicit generation or TTL."""

    key: KillSwitchKey
    engage: bool
    expected_generation: int
    reason: KillSwitchReasonCode
    actor_principal_id: UUID
    correlation_id: UUID
    incident_id: UUID | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if (
            type(self.key) is not KillSwitchKey
            or type(self.engage) is not bool
            or type(self.reason) is not KillSwitchReasonCode
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        require_kill_switch_generation(self.expected_generation)
        _require_uuid(self.actor_principal_id)
        _require_uuid(self.correlation_id)
        if self.incident_id is not None:
            _require_uuid(self.incident_id)
        if self.expires_at is not None:
            fail_kill_switch(KillSwitchFailureCode.EXPIRES_AT_UNSUPPORTED)

    def fingerprint(self) -> KillSwitchFingerprint:
        """Fingerprint the canonical command, excluding only transport time."""

        material = "\x00".join(
            (
                "RAOS-KILL-SWITCH-COMMAND-V1",
                self.key.scope_type.value,
                str(self.key.scope_id) if self.key.scope_id is not None else "",
                self.key.switch_type.value,
                "1" if self.engage else "0",
                str(self.expected_generation),
                self.reason.event_value(),
                str(self.actor_principal_id),
                str(self.correlation_id),
                str(self.incident_id) if self.incident_id is not None else "",
            )
        ).encode("ascii")
        return KillSwitchFingerprint(hashlib.sha256(material).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class KillSwitchState(_RedactedValue):
    """One immutable process-local switch projection."""

    switch_id: UUID
    key: KillSwitchKey
    engaged: bool
    generation: int
    reason: KillSwitchReasonCode
    changed_at: datetime
    incident_id: UUID | None = None

    def __post_init__(self) -> None:
        _require_uuid(self.switch_id)
        if (
            type(self.key) is not KillSwitchKey
            or type(self.engaged) is not bool
            or type(self.reason) is not KillSwitchReasonCode
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        require_kill_switch_generation(self.generation)
        require_kill_switch_utc(self.changed_at)
        if self.incident_id is not None:
            _require_uuid(self.incident_id)


def _rfc3339(value: datetime) -> str:
    return require_kill_switch_utc(value).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True, repr=False)
class KillSwitchEventIntent(_RedactedValue):
    """An in-memory intent; no publisher or delivery authority is attached."""

    event_id: UUID
    switch_id: UUID
    key: KillSwitchKey
    previous_engaged: bool
    new_engaged: bool
    previous_generation: int
    new_generation: int
    reason: KillSwitchReasonCode
    actor_principal_id: UUID
    correlation_id: UUID
    occurred_at: datetime
    incident_id: UUID | None = None

    EVENT_TYPE = "jp.raos.ops.kill_switch_changed.v1"
    PRODUCER = "ops"
    DATASCHEMA = (
        "https://schemas.raos.local/events/"
        "jp-raos-ops-kill-switch-changed-v1.schema.json"
    )

    def __post_init__(self) -> None:
        _require_uuid(self.event_id)
        _require_uuid(self.switch_id)
        if (
            type(self.key) is not KillSwitchKey
            or type(self.previous_engaged) is not bool
            or type(self.new_engaged) is not bool
            or type(self.reason) is not KillSwitchReasonCode
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        require_kill_switch_generation(self.previous_generation)
        require_kill_switch_generation(self.new_generation)
        if (
            self.new_generation != self.previous_generation + 1
            or self.new_engaged is self.previous_engaged
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        _require_uuid(self.actor_principal_id)
        _require_uuid(self.correlation_id)
        require_kill_switch_utc(self.occurred_at)
        if self.incident_id is not None:
            _require_uuid(self.incident_id)

    def contract_envelope(self) -> dict[str, object]:
        """Project the intent explicitly to the installed v1 event envelope."""

        data: dict[str, object] = {
            "kill_switch_id": str(self.switch_id),
            "scope_type": self.key.scope_type.value,
            "scope_id": str(self.key.scope_id)
            if self.key.scope_id is not None
            else None,
            "switch_type": self.key.switch_type.value,
            "previous_engaged": self.previous_engaged,
            "new_engaged": self.new_engaged,
            "previous_generation": self.previous_generation,
            "new_generation": self.new_generation,
            "reason": self.reason.event_value(),
            "incident_id": str(self.incident_id)
            if self.incident_id is not None
            else None,
        }
        return {
            "specversion": "1.0",
            "id": str(self.event_id),
            "source": "urn:raos:ops",
            "type": self.EVENT_TYPE,
            "subject": f"urn:raos:kill_switch:{self.switch_id}",
            "time": _rfc3339(self.occurred_at),
            "datacontenttype": "application/json",
            "dataschema": self.DATASCHEMA,
            "event_version": 1,
            "producer": self.PRODUCER,
            "aggregate": {
                "type": "kill_switch",
                "id": str(self.switch_id),
                "version": self.new_generation,
            },
            "correlation_id": str(self.correlation_id),
            "actor": {
                "actor_type": "USER",
                "actor_id": str(self.actor_principal_id),
                "service_name": None,
            },
            "classification": "RESTRICTED",
            "partition_key": str(self.switch_id),
            "data": data,
        }


@dataclass(frozen=True, slots=True, repr=False)
class KillSwitchChangeResult(_RedactedValue):
    """The state and sole unpublishable event intent created by one CAS."""

    state: KillSwitchState
    event_intent: KillSwitchEventIntent

    def __post_init__(self) -> None:
        if (
            type(self.state) is not KillSwitchState
            or type(self.event_intent) is not KillSwitchEventIntent
            or self.state.switch_id != self.event_intent.switch_id
            or self.state.key != self.event_intent.key
            or self.state.engaged is not self.event_intent.new_engaged
            or self.state.generation != self.event_intent.new_generation
            or self.state.reason != self.event_intent.reason
            or self.state.changed_at != self.event_intent.occurred_at
            or self.state.incident_id != self.event_intent.incident_id
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class KillSwitchCacheEntry(_RedactedValue):
    """A cached state plus its externally established generation floor."""

    state: KillSwitchState
    minimum_generation: int

    def __post_init__(self) -> None:
        if type(self.state) is not KillSwitchState:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        require_kill_switch_generation(self.minimum_generation)


@dataclass(frozen=True, slots=True, repr=False)
class KillSwitchCacheSnapshot(_RedactedValue):
    """One kind-specific bounded cache observation with explicit freshness."""

    switch_type: KillSwitchKind
    entries: tuple[KillSwitchCacheEntry, ...]
    loaded_at: datetime
    fresh_until: datetime
    complete: bool

    def __post_init__(self) -> None:
        if (
            type(self.switch_type) is not KillSwitchKind
            or type(self.entries) is not tuple
            or type(self.complete) is not bool
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        if len(self.entries) > MAX_KILL_SWITCH_CACHE_ENTRIES:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        if any(type(entry) is not KillSwitchCacheEntry for entry in self.entries):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        require_kill_switch_utc(self.loaded_at)
        require_kill_switch_utc(self.fresh_until)
        if self.loaded_at >= self.fresh_until:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        keys = tuple(entry.state.key for entry in self.entries)
        switch_ids = tuple(entry.state.switch_id for entry in self.entries)
        if (
            len(keys) != len(set(keys))
            or len(switch_ids) != len(set(switch_ids))
            or any(key.switch_type is not self.switch_type for key in keys)
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        if any(entry.state.changed_at > self.loaded_at for entry in self.entries):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)


@dataclass(frozen=True, slots=True, repr=False)
class KillSwitchContext(_RedactedValue):
    """The complete article scope chain evaluated for one guarded action."""

    site_id: UUID
    category_id: UUID
    article_id: UUID

    def __post_init__(self) -> None:
        _require_uuid(self.site_id)
        _require_uuid(self.category_id)
        _require_uuid(self.article_id)

    def required_keys(self, switch_type: KillSwitchKind) -> tuple[KillSwitchKey, ...]:
        if type(switch_type) is not KillSwitchKind:
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)
        keys = [
            KillSwitchKey(KillSwitchScopeType.GLOBAL, None, switch_type),
            KillSwitchKey(KillSwitchScopeType.SITE, self.site_id, switch_type),
            KillSwitchKey(
                KillSwitchScopeType.CATEGORY,
                self.category_id,
                switch_type,
            ),
            KillSwitchKey(
                KillSwitchScopeType.ARTICLE,
                self.article_id,
                switch_type,
            ),
        ]
        return tuple(keys)


@dataclass(frozen=True, slots=True, repr=False)
class KillSwitchEligibility(_RedactedValue):
    """A value-free eligibility decision; only ELIGIBLE can be allowed."""

    allowed: bool
    code: KillSwitchEligibilityCode

    def __post_init__(self) -> None:
        if (
            type(self.allowed) is not bool
            or type(self.code) is not KillSwitchEligibilityCode
            or self.allowed is not (self.code is KillSwitchEligibilityCode.ELIGIBLE)
        ):
            fail_kill_switch(KillSwitchFailureCode.INVALID_ARGUMENT)


__all__ = [
    "KillSwitchCacheEntry",
    "KillSwitchCacheSnapshot",
    "KillSwitchChangeCommand",
    "KillSwitchChangeResult",
    "KillSwitchContext",
    "KillSwitchEligibility",
    "KillSwitchEligibilityCode",
    "KillSwitchEventIntent",
    "KillSwitchFailure",
    "KillSwitchFailureCode",
    "KillSwitchFingerprint",
    "KillSwitchIdempotencyKey",
    "KillSwitchKey",
    "KillSwitchKind",
    "MAX_KILL_SWITCH_CACHE_ENTRIES",
    "MAX_KILL_SWITCH_GENERATION",
    "KillSwitchReasonCode",
    "KillSwitchScopeType",
    "KillSwitchState",
    "fail_kill_switch",
    "require_kill_switch_generation",
    "require_kill_switch_utc",
]
