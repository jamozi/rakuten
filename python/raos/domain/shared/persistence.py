"""Versions, ETags, and lossless pending-event state for ST-0308."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import re
from typing import Generic, NoReturn, Protocol, TypeVar, runtime_checkable
import unicodedata
from uuid import UUID

from raos.domain.shared.identity import EntityId
from raos.domain.shared.json_values import FrozenJsonObject, canonical_json_bytes


_MAX_VERSION = (1 << 63) - 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_GIT_COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)
_EMAIL = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+\Z",
    re.ASCII,
)
_RFC3339_DATE_TIME = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})[Tt]"
    r"(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d):"
    r"(?P<second>[0-5]\d)(?:\.\d+)?"
    r"(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)\Z",
    re.ASCII,
)


def _invalid(code: str = "INVALID_PERSISTENCE_VALUE") -> NoReturn:
    raise ValueError(code) from None


def require_rfc3339_date_time(value: object) -> str:
    """Return one exact RFC 3339 date-time string or fail closed.

    Python's ISO parser intentionally accepts basic dates, ISO week dates, and
    offsets with seconds that the hash-bound JSON Schema ``date-time`` format
    does not admit.  The lexical gate therefore runs before calendar validity
    is checked and performs no normalization.
    """

    if type(value) is not str:
        _invalid()
    match = _RFC3339_DATE_TIME.fullmatch(value)
    if match is None:
        _invalid()
    try:
        date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError:
        _invalid()
    return value


@dataclass(frozen=True, slots=True)
class AggregateVersion:
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 0 <= self.value <= _MAX_VERSION:
            _invalid()


PersistedVersion = AggregateVersion


@dataclass(frozen=True, slots=True, repr=False)
class AwareUtcDateTime:
    value: datetime

    def __post_init__(self) -> None:
        if (
            type(self.value) is not datetime
            or self.value.tzinfo is not timezone.utc
            or self.value.fold
        ):
            _invalid()

    def __repr__(self) -> str:
        return "AwareUtcDateTime(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            _invalid()

    def __repr__(self) -> str:
        return "Sha256Digest(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class GitCommitDigest:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _GIT_COMMIT.fullmatch(self.value) is None:
            _invalid()

    def __repr__(self) -> str:
        return "GitCommitDigest(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class YenMinor:
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 0 <= self.value <= _MAX_VERSION:
            _invalid()

    def __repr__(self) -> str:
        return "YenMinor(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EmailAddress:
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or len(self.value) > 320
            or self.value != self.value.strip()
            or unicodedata.normalize("NFC", self.value) != self.value
            or _EMAIL.fullmatch(self.value) is None
        ):
            _invalid()

    def __repr__(self) -> str:
        return "EmailAddress(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class UriReference:
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or not 1 <= len(self.value) <= 2048
            or self.value != self.value.strip()
            or unicodedata.normalize("NFC", self.value) != self.value
            or ":" not in self.value
            or any(character.isspace() for character in self.value)
            or any(
                unicodedata.category(character).startswith("C")
                for character in self.value
            )
        ):
            _invalid()

    def __repr__(self) -> str:
        return "UriReference(<redacted>)"


@dataclass(frozen=True, slots=True)
class StrongEtag:
    value: str

    @classmethod
    def for_aggregate(
        cls,
        *,
        aggregate_type: str,
        aggregate_id: EntityId,
        version: AggregateVersion,
    ) -> StrongEtag:
        if (
            type(aggregate_type) is not str
            or not aggregate_type
            or type(aggregate_id) is EntityId
            or not isinstance(aggregate_id, EntityId)
            or type(version) is not AggregateVersion
        ):
            _invalid()
        material = FrozenJsonObject.from_mapping(
            {
                "aggregate_id": str(aggregate_id.value),
                "aggregate_type": aggregate_type,
                "version": version.value,
            }
        )
        digest = hashlib.sha256(canonical_json_bytes(material)).hexdigest()[:32]
        return cls(f'"v{version.value}-{digest}"')

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or len(self.value) > 96
            or not self.value.startswith('"v')
            or not self.value.endswith('"')
        ):
            _invalid()


@runtime_checkable
class EventIdentity(Protocol):
    @property
    def event_id(self) -> UUID: ...


EventT = TypeVar("EventT", bound=EventIdentity)


class PendingEventBuffer(Generic[EventT]):
    """Mutable lifecycle component held privately by an aggregate root.

    Aggregate public APIs delegate only ``pending_events`` and
    ``acknowledge_events``.  The adapter calls the underscore methods after a
    known rollback/commit; an unknown commit discards the UoW and its objects.
    """

    __slots__ = ("_acknowledged", "_pending")

    def __init__(self, events: Iterable[EventT] = ()) -> None:
        pending = tuple(events)
        ids = tuple(event.event_id for event in pending)
        if len(ids) != len(set(ids)):
            _invalid()
        self._pending = pending
        self._acknowledged: tuple[EventT, ...] = ()

    def pending_events(self) -> tuple[EventT, ...]:
        return self._pending

    def record(self, event: EventT) -> None:
        if not isinstance(event, EventIdentity) or self._acknowledged:
            _invalid("EVENT_RECORDING_CONFLICT")
        if event.event_id in {candidate.event_id for candidate in self._pending}:
            _invalid("EVENT_RECORDING_CONFLICT")
        self._pending += (event,)

    def acknowledge_events(self, event_ids: tuple[UUID, ...]) -> None:
        if type(event_ids) is not tuple or not event_ids or self._acknowledged:
            _invalid("EVENT_ACKNOWLEDGEMENT_CONFLICT")
        expected = tuple(event.event_id for event in self._pending)
        if event_ids != expected:
            _invalid("EVENT_ACKNOWLEDGEMENT_CONFLICT")
        self._acknowledged = self._pending
        self._pending = ()

    def _restore_acknowledged(self) -> None:
        if self._acknowledged:
            self._pending = self._acknowledged + self._pending
            self._acknowledged = ()

    def _finish_acknowledged(self) -> None:
        self._acknowledged = ()


__all__ = [
    "AggregateVersion",
    "AwareUtcDateTime",
    "EmailAddress",
    "EventIdentity",
    "GitCommitDigest",
    "PendingEventBuffer",
    "PersistedVersion",
    "Sha256Digest",
    "StrongEtag",
    "UriReference",
    "YenMinor",
    "require_rfc3339_date_time",
]
