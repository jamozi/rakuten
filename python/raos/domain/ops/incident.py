"""Immutable provider-neutral values for the bounded ST-1406 incident seam.

This module intentionally models neither HTTP nor persistence.  Incident text
is retained only in explicit redacted value objects, evidence is represented by
identifier and digest references, and no value exposes a provider, publisher,
notification, credential, or kill-switch command surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
import hashlib
import re
from typing import NoReturn, SupportsIndex, TypeAlias, cast, final
from uuid import UUID

from raos.domain.ops.kill_switch import (
    KillSwitchEventIntent,
    KillSwitchKey,
    KillSwitchReasonCode,
)


MAX_INCIDENT_GENERATION = (1 << 63) - 1
MAX_INCIDENT_EVIDENCE_REFERENCES = 32
MAX_INCIDENT_TIMELINE_ENTRIES = 10_000

_DISPLAY_ID = re.compile(r"INC-[A-Z0-9][A-Z0-9-]{0,126}\Z", re.ASCII)
_FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{7,127}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REDACTED = "<redacted-incident-value>"


class IncidentSeverity(str, Enum):
    """Canonical operations severity labels for the local domain seam."""

    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"
    SEV4 = "SEV4"


class IncidentStatus(str, Enum):
    """Exact lifecycle states from ``SM-INCIDENT``."""

    DECLARED = "DECLARED"
    CONTAINING = "CONTAINING"
    CONTAINED = "CONTAINED"
    RECOVERING = "RECOVERING"
    MONITORING = "MONITORING"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"


_STATUS_MINIMUM_GENERATION = {
    IncidentStatus.DECLARED: 0,
    IncidentStatus.CONTAINING: 1,
    IncidentStatus.CONTAINED: 2,
    IncidentStatus.RECOVERING: 3,
    IncidentStatus.MONITORING: 4,
    IncidentStatus.CLOSED: 5,
    IncidentStatus.REOPENED: 6,
}


class IncidentTimelineType(str, Enum):
    """Closed provider-neutral timeline taxonomy for this local slice.

    These names follow the append-only incident-event data design.  They do not
    claim a mapping to the conflicting v0.4 HTTP request enum.
    """

    NOTE = "NOTE"
    STATUS_CHANGE = "STATUS_CHANGE"
    CONTAINMENT = "CONTAINMENT"
    DECISION = "DECISION"
    RECOVERY = "RECOVERY"
    EVIDENCE = "EVIDENCE"
    ACTION_ITEM = "ACTION_ITEM"


class IncidentFailureCode(str, Enum):
    """Stable, value-free failure classifications."""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    STATE_MISSING = "STATE_MISSING"
    STATE_CONFLICT = "STATE_CONFLICT"
    GENERATION_CONFLICT = "GENERATION_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    CAPACITY_EXCEEDED = "CAPACITY_EXCEEDED"
    KILL_SWITCH_INTENT_INVALID = "KILL_SWITCH_INTENT_INVALID"
    STORE_FAILURE = "STORE_FAILURE"


@final
class IncidentFailure(RuntimeError):
    """Immutable sanitized failure which retains no rejected collaborator data."""

    __slots__ = ("_code",)
    _code: IncidentFailureCode

    def __init__(self, code: IncidentFailureCode) -> None:
        if type(code) is not IncidentFailureCode:
            raise TypeError("code must be an exact IncidentFailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)

    @property
    def code(self) -> IncidentFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        if name == "__traceback__":
            super().__setattr__(name, value)
            return
        del name, value
        raise AttributeError("IncidentFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("IncidentFailure is immutable")

    def __repr__(self) -> str:
        return f"IncidentFailure(code={self.code!r})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("incident failure serialization is not supported")


def fail_incident(code: IncidentFailureCode) -> NoReturn:
    """Raise one sanitized incident failure without an active exception cause."""

    raise IncidentFailure(code) from None


def require_incident_uuid(value: object) -> UUID:
    """Require an exact, non-nil UUID."""

    if type(value) is not UUID or value.int == 0:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return value


def require_incident_utc(value: object) -> datetime:
    """Require an exact aware UTC timestamp; never infer or convert a zone."""

    if type(value) is not datetime or value.tzinfo is not UTC:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return value


def require_incident_generation(value: object) -> int:
    """Require one exact non-negative signed-bigint generation."""

    if type(value) is not int or not 0 <= value <= MAX_INCIDENT_GENERATION:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return value


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("incident value serialization is not supported")


class _BoundedText(_RedactedValue):
    __slots__ = ("_value",)
    _value: str
    _maximum_length = 8_000
    _allow_newline = True

    def __init__(self, value: str) -> None:
        if (
            type(value) is not str
            or not 1 <= len(value) <= self._maximum_length
            or value != value.strip()
            or "\x00" in value
            or any(
                (
                    ord(character) < 0x20
                    and not (self._allow_newline and character in {"\n", "\t"})
                )
                or 0x7F <= ord(character) <= 0x9F
                for character in value
            )
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        try:
            value.encode("utf-8")
        except UnicodeError:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        object.__setattr__(self, "_value", value)

    @property
    def value(self) -> str:
        """Expose text only at an explicit domain or contract boundary."""

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
class IncidentTitle(_BoundedText):
    __slots__ = ()
    _maximum_length = 200
    _allow_newline = False


@final
class IncidentSummary(_BoundedText):
    __slots__ = ()
    _maximum_length = 8_000


@final
class IncidentTimelineNote(_BoundedText):
    __slots__ = ()
    _maximum_length = 8_000


@final
class IncidentDisplayId(_RedactedValue):
    """An immutable application display identifier with the ``INC-`` prefix."""

    __slots__ = ("_value",)
    _value: str

    def __init__(self, value: str) -> None:
        if type(value) is not str or _DISPLAY_ID.fullmatch(value) is None:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        object.__setattr__(self, "_value", value)

    @property
    def value(self) -> str:
        return self._value

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("IncidentDisplayId is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("IncidentDisplayId is immutable")

    def __eq__(self, other: object) -> bool:
        return type(other) is IncidentDisplayId and self._value == other._value

    def __hash__(self) -> int:
        return hash((IncidentDisplayId, self._value))


@final
class IncidentFingerprint(_RedactedValue):
    """A SHA-256 fingerprint, never the command or key bytes."""

    __slots__ = ("_value",)
    _value: str

    def __init__(self, value: str) -> None:
        if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        object.__setattr__(self, "_value", value)

    @property
    def value(self) -> str:
        return self._value

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("IncidentFingerprint is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("IncidentFingerprint is immutable")

    def __eq__(self, other: object) -> bool:
        return type(other) is IncidentFingerprint and self._value == other._value

    def __hash__(self) -> int:
        return hash((IncidentFingerprint, self._value))


@final
class IncidentIdempotencyKey(_RedactedValue):
    """A bounded opaque key retained only through its fingerprint."""

    __slots__ = ("_value",)
    _value: str

    def __init__(self, value: str) -> None:
        if type(value) is not str or _IDEMPOTENCY_KEY.fullmatch(value) is None:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        object.__setattr__(self, "_value", value)

    def fingerprint(self) -> IncidentFingerprint:
        return IncidentFingerprint(
            hashlib.sha256(self._value.encode("ascii")).hexdigest()
        )

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("IncidentIdempotencyKey is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("IncidentIdempotencyKey is immutable")


@final
@dataclass(frozen=True, slots=True, repr=False)
class IncidentEvidenceReference(_RedactedValue):
    """An evidence identifier and immutable digest, never evidence content."""

    artifact_id: UUID
    artifact_sha256: str

    def __post_init__(self) -> None:
        require_incident_uuid(self.artifact_id)
        if (
            type(self.artifact_sha256) is not str
            or _SHA256.fullmatch(self.artifact_sha256) is None
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)


def require_evidence_references(
    value: object,
) -> tuple[IncidentEvidenceReference, ...]:
    if type(value) is not tuple:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    untyped_references = cast(tuple[object, ...], value)
    if len(untyped_references) > MAX_INCIDENT_EVIDENCE_REFERENCES or any(
        type(item) is not IncidentEvidenceReference for item in untyped_references
    ):
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    references = cast(
        tuple[IncidentEvidenceReference, ...],
        untyped_references,
    )
    if len({item.artifact_id for item in references}) != len(references):
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return references


def incident_status_minimum_generation(value: object) -> int:
    """Return the first generation at which one exact status can exist."""

    if type(value) is not IncidentStatus:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return _STATUS_MINIMUM_GENERATION[value]


_ALLOWED_TRANSITIONS = frozenset(
    {
        (IncidentStatus.DECLARED, IncidentStatus.CONTAINING),
        (IncidentStatus.CONTAINING, IncidentStatus.CONTAINED),
        (IncidentStatus.CONTAINED, IncidentStatus.RECOVERING),
        (IncidentStatus.RECOVERING, IncidentStatus.MONITORING),
        (IncidentStatus.MONITORING, IncidentStatus.CLOSED),
        (IncidentStatus.CLOSED, IncidentStatus.REOPENED),
        (IncidentStatus.REOPENED, IncidentStatus.CONTAINING),
    }
)


def require_incident_transition(
    previous: object, target: object
) -> tuple[IncidentStatus, IncidentStatus]:
    if (
        type(previous) is not IncidentStatus
        or type(target) is not IncidentStatus
        or (previous, target) not in _ALLOWED_TRANSITIONS
    ):
        fail_incident(IncidentFailureCode.STATE_CONFLICT)
    return previous, target


@final
@dataclass(frozen=True, slots=True, repr=False)
class IncidentState(_RedactedValue):
    """One immutable incident aggregate projection."""

    incident_id: UUID
    display_id: IncidentDisplayId
    severity: IncidentSeverity
    status: IncidentStatus
    title: IncidentTitle
    summary: IncidentSummary
    declared_by_principal_id: UUID
    owner_principal_id: UUID
    commander_principal_id: UUID
    declared_at: datetime
    updated_at: datetime
    generation: int
    contained_at: datetime | None = None
    recovered_at: datetime | None = None
    closed_at: datetime | None = None
    root_cause_recorded: bool = False

    def __post_init__(self) -> None:
        require_incident_uuid(self.incident_id)
        if (
            type(self.display_id) is not IncidentDisplayId
            or type(self.severity) is not IncidentSeverity
            or type(self.status) is not IncidentStatus
            or type(self.title) is not IncidentTitle
            or type(self.summary) is not IncidentSummary
            or type(self.root_cause_recorded) is not bool
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        require_incident_uuid(self.declared_by_principal_id)
        require_incident_uuid(self.owner_principal_id)
        require_incident_uuid(self.commander_principal_id)
        declared_at = require_incident_utc(self.declared_at)
        updated_at = require_incident_utc(self.updated_at)
        generation = require_incident_generation(self.generation)
        if generation < incident_status_minimum_generation(self.status):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if updated_at < declared_at:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if generation == 0 and (
            self.status is not IncidentStatus.DECLARED or updated_at != declared_at
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        for timestamp in (self.contained_at, self.recovered_at, self.closed_at):
            if timestamp is not None and require_incident_utc(timestamp) < declared_at:
                fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if self.contained_at is not None and self.contained_at > updated_at:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if self.recovered_at is not None and (
            self.contained_at is None
            or self.recovered_at < self.contained_at
            or self.recovered_at > updated_at
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if self.closed_at is not None and (
            self.recovered_at is None
            or self.closed_at < self.recovered_at
            or self.closed_at > updated_at
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if self.status in {
            IncidentStatus.DECLARED,
            IncidentStatus.CONTAINING,
            IncidentStatus.REOPENED,
        } and any(
            timestamp is not None
            for timestamp in (self.contained_at, self.recovered_at, self.closed_at)
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if self.status in {IncidentStatus.CONTAINED, IncidentStatus.RECOVERING} and (
            self.contained_at is None
            or self.recovered_at is not None
            or self.closed_at is not None
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if self.status is IncidentStatus.MONITORING and (
            self.contained_at is None
            or self.recovered_at is None
            or self.closed_at is not None
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if self.status is IncidentStatus.CLOSED and (
            self.contained_at is None
            or self.recovered_at is None
            or self.closed_at is None
            or not self.root_cause_recorded
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if self.status is not IncidentStatus.CLOSED and self.root_cause_recorded:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)


@final
@dataclass(frozen=True, slots=True, repr=False)
class IncidentTimelineEntry(_RedactedValue):
    """One append-only, content-redacted local timeline entry."""

    event_id: UUID
    incident_id: UUID
    generation: int
    event_type: IncidentTimelineType
    note: IncidentTimelineNote
    actor_principal_id: UUID
    correlation_id: UUID
    occurred_at: datetime
    evidence_references: tuple[IncidentEvidenceReference, ...]
    previous_status: IncidentStatus | None = None
    new_status: IncidentStatus | None = None
    source_kill_switch_event_id: UUID | None = None
    source_kill_switch_id: UUID | None = None
    source_kill_switch_generation: int | None = None

    def __post_init__(self) -> None:
        require_incident_uuid(self.event_id)
        require_incident_uuid(self.incident_id)
        generation = require_incident_generation(self.generation)
        if generation == 0:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if (
            type(self.event_type) is not IncidentTimelineType
            or type(self.note) is not IncidentTimelineNote
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        require_incident_uuid(self.actor_principal_id)
        require_incident_uuid(self.correlation_id)
        require_incident_utc(self.occurred_at)
        references = require_evidence_references(self.evidence_references)
        if self.event_type is IncidentTimelineType.EVIDENCE and not references:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if self.event_type is IncidentTimelineType.STATUS_CHANGE:
            previous_status, new_status = require_incident_transition(
                self.previous_status, self.new_status
            )
            if (
                generation - 1 < incident_status_minimum_generation(previous_status)
                or generation < incident_status_minimum_generation(new_status)
                or (new_status is IncidentStatus.CLOSED and not references)
            ):
                fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        elif self.previous_status is not None or self.new_status is not None:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        kill_values = (
            self.source_kill_switch_event_id,
            self.source_kill_switch_id,
            self.source_kill_switch_generation,
        )
        if any(value is not None for value in kill_values):
            if self.event_type is not IncidentTimelineType.CONTAINMENT or any(
                value is None for value in kill_values
            ):
                fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
            require_incident_uuid(self.source_kill_switch_event_id)
            require_incident_uuid(self.source_kill_switch_id)
            generation = require_incident_generation(self.source_kill_switch_generation)
            if generation == 0 or self.event_id == self.source_kill_switch_event_id:
                fail_incident(IncidentFailureCode.INVALID_ARGUMENT)


@final
@dataclass(frozen=True, slots=True, repr=False)
class DeclareIncidentCommand(_RedactedValue):
    incident_id: UUID
    display_id: IncidentDisplayId
    severity: IncidentSeverity
    title: IncidentTitle
    summary: IncidentSummary
    declared_by_principal_id: UUID
    owner_principal_id: UUID
    commander_principal_id: UUID
    correlation_id: UUID
    declared_at: datetime

    def __post_init__(self) -> None:
        require_incident_uuid(self.incident_id)
        if (
            type(self.display_id) is not IncidentDisplayId
            or type(self.severity) is not IncidentSeverity
            or type(self.title) is not IncidentTitle
            or type(self.summary) is not IncidentSummary
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        require_incident_uuid(self.declared_by_principal_id)
        require_incident_uuid(self.owner_principal_id)
        require_incident_uuid(self.commander_principal_id)
        require_incident_uuid(self.correlation_id)
        require_incident_utc(self.declared_at)

    def fingerprint(self) -> IncidentFingerprint:
        return _command_fingerprint(
            (
                "DECLARE",
                str(self.incident_id),
                self.display_id.value,
                self.severity.value,
                self.title.value,
                self.summary.value,
                str(self.declared_by_principal_id),
                str(self.owner_principal_id),
                str(self.commander_principal_id),
                str(self.correlation_id),
                _rfc3339(self.declared_at),
            )
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class AppendIncidentTimelineCommand(_RedactedValue):
    incident_id: UUID
    expected_generation: int
    event_type: IncidentTimelineType
    note: IncidentTimelineNote
    actor_principal_id: UUID
    correlation_id: UUID
    occurred_at: datetime
    evidence_references: tuple[IncidentEvidenceReference, ...] = ()

    def __post_init__(self) -> None:
        require_incident_uuid(self.incident_id)
        require_incident_generation(self.expected_generation)
        if (
            type(self.event_type) is not IncidentTimelineType
            or self.event_type is IncidentTimelineType.STATUS_CHANGE
            or type(self.note) is not IncidentTimelineNote
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        require_incident_uuid(self.actor_principal_id)
        require_incident_uuid(self.correlation_id)
        require_incident_utc(self.occurred_at)
        references = require_evidence_references(self.evidence_references)
        if self.event_type is IncidentTimelineType.EVIDENCE and not references:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)

    def fingerprint(self) -> IncidentFingerprint:
        return _command_fingerprint(
            (
                "APPEND_TIMELINE",
                str(self.incident_id),
                str(self.expected_generation),
                self.event_type.value,
                self.note.value,
                str(self.actor_principal_id),
                str(self.correlation_id),
                _rfc3339(self.occurred_at),
                *_evidence_material(self.evidence_references),
            )
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class TransitionIncidentCommand(_RedactedValue):
    incident_id: UUID
    expected_generation: int
    target_status: IncidentStatus
    note: IncidentTimelineNote
    actor_principal_id: UUID
    correlation_id: UUID
    occurred_at: datetime
    evidence_references: tuple[IncidentEvidenceReference, ...] = ()
    root_cause_recorded: bool = False

    def __post_init__(self) -> None:
        require_incident_uuid(self.incident_id)
        require_incident_generation(self.expected_generation)
        if (
            type(self.target_status) is not IncidentStatus
            or type(self.note) is not IncidentTimelineNote
            or type(self.root_cause_recorded) is not bool
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        require_incident_uuid(self.actor_principal_id)
        require_incident_uuid(self.correlation_id)
        require_incident_utc(self.occurred_at)
        references = require_evidence_references(self.evidence_references)
        if self.target_status is IncidentStatus.CLOSED:
            if not self.root_cause_recorded or not references:
                fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        elif self.root_cause_recorded:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)

    def fingerprint(self) -> IncidentFingerprint:
        return _command_fingerprint(
            (
                "TRANSITION",
                str(self.incident_id),
                str(self.expected_generation),
                self.target_status.value,
                self.note.value,
                str(self.actor_principal_id),
                str(self.correlation_id),
                _rfc3339(self.occurred_at),
                "1" if self.root_cause_recorded else "0",
                *_evidence_material(self.evidence_references),
            )
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordKillSwitchIntentCommand(_RedactedValue):
    """Record an already-created engaged ST-1405 intent; never invoke a switch."""

    incident_id: UUID
    expected_generation: int
    intent: KillSwitchEventIntent

    def __post_init__(self) -> None:
        require_incident_uuid(self.incident_id)
        require_incident_generation(self.expected_generation)
        if type(self.intent) is not KillSwitchEventIntent:
            fail_incident(IncidentFailureCode.KILL_SWITCH_INTENT_INVALID)
        try:
            invalid = (
                self.intent.incident_id != self.incident_id
                or self.intent.new_engaged is not True
                or self.intent.previous_engaged is not False
                or self.intent.new_generation != self.intent.previous_generation + 1
            )
        except Exception:
            invalid = True
        if invalid:
            fail_incident(IncidentFailureCode.KILL_SWITCH_INTENT_INVALID)

    def fingerprint(self) -> IncidentFingerprint:
        intent = self.intent
        return _command_fingerprint(
            (
                "RECORD_KILL_SWITCH_INTENT",
                str(self.incident_id),
                str(self.expected_generation),
                str(intent.event_id),
                str(intent.switch_id),
                intent.key.scope_type.value,
                str(intent.key.scope_id) if intent.key.scope_id is not None else "",
                intent.key.switch_type.value,
                str(intent.previous_generation),
                str(intent.new_generation),
                intent.reason.event_value(),
                str(intent.actor_principal_id),
                str(intent.correlation_id),
                _rfc3339(intent.occurred_at),
            )
        )


IncidentCommand: TypeAlias = (
    DeclareIncidentCommand
    | AppendIncidentTimelineCommand
    | TransitionIncidentCommand
    | RecordKillSwitchIntentCommand
)


def _copy_uuid(value: object) -> UUID:
    if type(value) is not UUID:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return UUID(int=value.int)


def _copy_optional_uuid(value: object) -> UUID | None:
    return None if value is None else _copy_uuid(value)


def _copy_utc(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is not UTC:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        value.second,
        value.microsecond,
        tzinfo=UTC,
        fold=value.fold,
    )


def _copy_evidence_references(
    values: object,
) -> tuple[IncidentEvidenceReference, ...]:
    if type(values) is not tuple:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    untyped_references = cast(tuple[object, ...], values)
    if any(
        type(value) is not IncidentEvidenceReference for value in untyped_references
    ):
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    references = cast(
        tuple[IncidentEvidenceReference, ...],
        untyped_references,
    )
    return tuple(
        IncidentEvidenceReference(
            artifact_id=_copy_uuid(value.artifact_id),
            artifact_sha256=value.artifact_sha256,
        )
        for value in references
    )


def _copy_kill_switch_intent(value: object) -> KillSwitchEventIntent:
    if type(value) is not KillSwitchEventIntent:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    key = value.key
    reason = value.reason
    if type(key) is not KillSwitchKey or type(reason) is not KillSwitchReasonCode:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    try:
        return KillSwitchEventIntent(
            event_id=_copy_uuid(value.event_id),
            switch_id=_copy_uuid(value.switch_id),
            key=KillSwitchKey(
                scope_type=key.scope_type,
                scope_id=_copy_optional_uuid(key.scope_id),
                switch_type=key.switch_type,
            ),
            previous_engaged=value.previous_engaged,
            new_engaged=value.new_engaged,
            previous_generation=value.previous_generation,
            new_generation=value.new_generation,
            reason=KillSwitchReasonCode(reason.event_value()),
            actor_principal_id=_copy_uuid(value.actor_principal_id),
            correlation_id=_copy_uuid(value.correlation_id),
            occurred_at=_copy_utc(value.occurred_at),
            incident_id=_copy_optional_uuid(value.incident_id),
        )
    except IncidentFailure:
        raise
    except Exception:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)


def copy_incident_command(value: object) -> IncidentCommand:
    """Reconstruct one command without retaining caller-owned object aliases."""

    try:
        if type(value) is DeclareIncidentCommand:
            return DeclareIncidentCommand(
                incident_id=_copy_uuid(value.incident_id),
                display_id=IncidentDisplayId(value.display_id.value),
                severity=value.severity,
                title=IncidentTitle(value.title.value),
                summary=IncidentSummary(value.summary.value),
                declared_by_principal_id=_copy_uuid(value.declared_by_principal_id),
                owner_principal_id=_copy_uuid(value.owner_principal_id),
                commander_principal_id=_copy_uuid(value.commander_principal_id),
                correlation_id=_copy_uuid(value.correlation_id),
                declared_at=_copy_utc(value.declared_at),
            )
        if type(value) is AppendIncidentTimelineCommand:
            return AppendIncidentTimelineCommand(
                incident_id=_copy_uuid(value.incident_id),
                expected_generation=value.expected_generation,
                event_type=value.event_type,
                note=IncidentTimelineNote(value.note.value),
                actor_principal_id=_copy_uuid(value.actor_principal_id),
                correlation_id=_copy_uuid(value.correlation_id),
                occurred_at=_copy_utc(value.occurred_at),
                evidence_references=_copy_evidence_references(
                    value.evidence_references
                ),
            )
        if type(value) is TransitionIncidentCommand:
            return TransitionIncidentCommand(
                incident_id=_copy_uuid(value.incident_id),
                expected_generation=value.expected_generation,
                target_status=value.target_status,
                note=IncidentTimelineNote(value.note.value),
                actor_principal_id=_copy_uuid(value.actor_principal_id),
                correlation_id=_copy_uuid(value.correlation_id),
                occurred_at=_copy_utc(value.occurred_at),
                evidence_references=_copy_evidence_references(
                    value.evidence_references
                ),
                root_cause_recorded=value.root_cause_recorded,
            )
        if type(value) is RecordKillSwitchIntentCommand:
            return RecordKillSwitchIntentCommand(
                incident_id=_copy_uuid(value.incident_id),
                expected_generation=value.expected_generation,
                intent=_copy_kill_switch_intent(value.intent),
            )
    except IncidentFailure:
        raise
    except Exception:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    fail_incident(IncidentFailureCode.INVALID_ARGUMENT)


def _command_fingerprint(parts: tuple[str, ...]) -> IncidentFingerprint:
    try:
        material = "\x00".join(("RAOS-INCIDENT-COMMAND-V1", *parts)).encode("utf-8")
    except UnicodeError:
        fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
    return IncidentFingerprint(hashlib.sha256(material).hexdigest())


def _evidence_material(
    references: tuple[IncidentEvidenceReference, ...],
) -> tuple[str, ...]:
    return tuple(
        f"{reference.artifact_id}:{reference.artifact_sha256}"
        for reference in references
    )


def _rfc3339(value: datetime) -> str:
    return require_incident_utc(value).isoformat().replace("+00:00", "Z")


@final
@dataclass(frozen=True, slots=True, repr=False)
class IncidentDeclaredEventIntent(_RedactedValue):
    """In-memory declaration intent compatible with the installed v1 event."""

    event_id: UUID
    state: IncidentState
    actor_principal_id: UUID
    correlation_id: UUID

    EVENT_TYPE = "jp.raos.ops.incident_declared.v1"
    DATASCHEMA = (
        "https://schemas.raos.local/events/jp-raos-ops-incident-declared-v1.schema.json"
    )

    def __post_init__(self) -> None:
        require_incident_uuid(self.event_id)
        if (
            type(self.state) is not IncidentState
            or self.state.status is not IncidentStatus.DECLARED
            or self.state.generation != 0
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        require_incident_uuid(self.actor_principal_id)
        require_incident_uuid(self.correlation_id)
        if self.actor_principal_id != self.state.declared_by_principal_id:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)

    def contract_envelope(self) -> dict[str, object]:
        state = self.state
        return {
            "specversion": "1.0",
            "id": str(self.event_id),
            "source": "urn:raos:ops",
            "type": self.EVENT_TYPE,
            "subject": f"urn:raos:incident:{state.incident_id}",
            "time": _rfc3339(state.declared_at),
            "datacontenttype": "application/json",
            "dataschema": self.DATASCHEMA,
            "event_version": 1,
            "producer": "ops",
            "aggregate": {
                "type": "incident",
                "id": str(state.incident_id),
                "version": state.generation,
            },
            "correlation_id": str(self.correlation_id),
            "actor": {
                "actor_type": "USER",
                "actor_id": str(self.actor_principal_id),
                "service_name": None,
            },
            "classification": "RESTRICTED",
            "partition_key": str(state.incident_id),
            "data": {
                "incident_id": str(state.incident_id),
                "severity": state.severity.value,
                "title": state.title.value,
                "declared_at": _rfc3339(state.declared_at),
            },
        }


@final
@dataclass(frozen=True, slots=True, repr=False)
class IncidentClosedEventIntent(_RedactedValue):
    """In-memory closure intent compatible with the installed v1 event."""

    event_id: UUID
    state: IncidentState
    actor_principal_id: UUID
    correlation_id: UUID

    EVENT_TYPE = "jp.raos.ops.incident_closed.v1"
    DATASCHEMA = (
        "https://schemas.raos.local/events/jp-raos-ops-incident-closed-v1.schema.json"
    )

    def __post_init__(self) -> None:
        require_incident_uuid(self.event_id)
        if (
            type(self.state) is not IncidentState
            or self.state.status is not IncidentStatus.CLOSED
            or self.state.closed_at is None
            or not self.state.root_cause_recorded
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        require_incident_uuid(self.actor_principal_id)
        require_incident_uuid(self.correlation_id)

    def contract_envelope(self) -> dict[str, object]:
        state = self.state
        closed_at = state.closed_at
        if closed_at is None:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        return {
            "specversion": "1.0",
            "id": str(self.event_id),
            "source": "urn:raos:ops",
            "type": self.EVENT_TYPE,
            "subject": f"urn:raos:incident:{state.incident_id}",
            "time": _rfc3339(closed_at),
            "datacontenttype": "application/json",
            "dataschema": self.DATASCHEMA,
            "event_version": 1,
            "producer": "ops",
            "aggregate": {
                "type": "incident",
                "id": str(state.incident_id),
                "version": state.generation,
            },
            "correlation_id": str(self.correlation_id),
            "actor": {
                "actor_type": "USER",
                "actor_id": str(self.actor_principal_id),
                "service_name": None,
            },
            "classification": "RESTRICTED",
            "partition_key": str(state.incident_id),
            "data": {
                "incident_id": str(state.incident_id),
                "closed_at": _rfc3339(closed_at),
                "root_cause_recorded": state.root_cause_recorded,
            },
        }


IncidentContractIntent: TypeAlias = (
    IncidentDeclaredEventIntent | IncidentClosedEventIntent
)


@final
@dataclass(frozen=True, slots=True, repr=False)
class IncidentMutationResult(_RedactedValue):
    """One exact aggregate result plus its local timeline/contract intents."""

    state: IncidentState
    timeline_entry: IncidentTimelineEntry | None
    contract_intent: IncidentContractIntent | None

    def __post_init__(self) -> None:
        if type(self.state) is not IncidentState:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if self.timeline_entry is not None:
            if (
                type(self.timeline_entry) is not IncidentTimelineEntry
                or self.timeline_entry.incident_id != self.state.incident_id
                or self.timeline_entry.generation != self.state.generation
                or self.timeline_entry.occurred_at != self.state.updated_at
            ):
                fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if self.contract_intent is not None and type(self.contract_intent) not in {
            IncidentDeclaredEventIntent,
            IncidentClosedEventIntent,
        }:
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if type(self.contract_intent) is IncidentDeclaredEventIntent:
            if (
                self.timeline_entry is not None
                or self.contract_intent.state != self.state
            ):
                fail_incident(IncidentFailureCode.INVALID_ARGUMENT)
        if type(self.contract_intent) is IncidentClosedEventIntent and (
            self.timeline_entry is None
            or self.contract_intent.state != self.state
            or self.contract_intent.event_id == self.timeline_entry.event_id
        ):
            fail_incident(IncidentFailureCode.INVALID_ARGUMENT)


__all__ = [
    "AppendIncidentTimelineCommand",
    "DeclareIncidentCommand",
    "IncidentClosedEventIntent",
    "IncidentCommand",
    "IncidentContractIntent",
    "IncidentDeclaredEventIntent",
    "IncidentDisplayId",
    "IncidentEvidenceReference",
    "IncidentFailure",
    "IncidentFailureCode",
    "IncidentFingerprint",
    "IncidentIdempotencyKey",
    "IncidentMutationResult",
    "IncidentSeverity",
    "IncidentState",
    "IncidentStatus",
    "IncidentSummary",
    "IncidentTimelineEntry",
    "IncidentTimelineNote",
    "IncidentTimelineType",
    "IncidentTitle",
    "MAX_INCIDENT_EVIDENCE_REFERENCES",
    "MAX_INCIDENT_GENERATION",
    "MAX_INCIDENT_TIMELINE_ENTRIES",
    "RecordKillSwitchIntentCommand",
    "TransitionIncidentCommand",
    "copy_incident_command",
    "fail_incident",
    "incident_status_minimum_generation",
    "require_evidence_references",
    "require_incident_generation",
    "require_incident_transition",
    "require_incident_utc",
    "require_incident_uuid",
]
