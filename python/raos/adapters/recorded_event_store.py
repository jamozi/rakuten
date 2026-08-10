"""Body-free ordered recorded event exchange for ST-1201 tests."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import NoReturn, SupportsIndex, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.analytics.event_collector import (
    EventCollectorFailureCode,
    EventCollectorMode,
    EventDigest,
    RecordedStoreDisposition,
    RecordedStoreOutcome,
    ValidatedEvent,
    fail_event_collector,
)


_MAX_SCRIPT_CAPACITY = 100_000


@dataclass(frozen=True, slots=True, repr=False)
class RecordedEventStep:
    event_id: UUID
    digest: EventDigest
    outcome: RecordedStoreOutcome

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not UUID
            or type(self.digest) is not EventDigest
            or type(self.outcome) is not RecordedStoreOutcome
            or self.outcome.event_id != self.event_id
            or self.outcome.digest != self.digest
        ):
            fail_event_collector()

    def __repr__(self) -> str:
        return "RecordedEventStep(<redacted-event-collector>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded event step serialization is not supported")


@final
class RecordedEventCollectionExchange:
    """Consume only exact scripted event-id and digest pairs."""

    __slots__ = ("_index", "_lock", "_scripts")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        mode: EventCollectorMode,
        script_capacity: int,
        scripts: tuple[RecordedEventStep, ...],
    ) -> None:
        if (
            environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or mode is not EventCollectorMode.RECORDED_TEST_ONLY
            or type(script_capacity) is not int
            or not 0 < script_capacity <= _MAX_SCRIPT_CAPACITY
            or type(scripts) is not tuple
            or not scripts
            or len(scripts) > script_capacity
            or any(type(step) is not RecordedEventStep for step in scripts)
        ):
            fail_event_collector()
        for index, step in enumerate(scripts):
            prior = scripts[:index]
            matching = tuple(item for item in prior if item.event_id == step.event_id)
            if matching:
                if (
                    any(item.digest != step.digest for item in matching)
                    or step.outcome.disposition
                    is not RecordedStoreDisposition.RECORDED_DUPLICATE
                ):
                    fail_event_collector()
            elif (
                step.outcome.disposition
                is not RecordedStoreDisposition.RECORDED_ACCEPTED
            ):
                fail_event_collector()
        self._scripts = scripts
        self._index = 0
        self._lock = RLock()

    def __repr__(self) -> str:
        return "RecordedEventCollectionExchange(<redacted-event-collector>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded event exchange serialization is not supported")

    def exchange(
        self,
        event: ValidatedEvent,
        digest: EventDigest,
    ) -> RecordedStoreOutcome:
        if type(event) is not ValidatedEvent or type(digest) is not EventDigest:
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        if EventDigest.of(event) != digest:
            fail_event_collector(EventCollectorFailureCode.EVENT_ID_CONFLICT)
        with self._lock:
            if self._index >= len(self._scripts):
                fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED)
            step = self._scripts[self._index]
            if event.envelope.event_id == step.event_id and digest != step.digest:
                fail_event_collector(EventCollectorFailureCode.EVENT_ID_CONFLICT)
            if event.envelope.event_id != step.event_id or digest != step.digest:
                fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
            self._index += 1
            return step.outcome


__all__ = [
    "RecordedEventCollectionExchange",
    "RecordedEventStep",
]
