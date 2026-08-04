"""Deterministic in-memory fake for the at-least-once queue port."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Generic, TypeVar

from raos.ports.queue import (
    InvalidQueueMessage,
    QueueDelivery,
    QueueMessage,
    QueuePort,
    StaleReceiptHandle,
    UnknownReceiptHandle,
    require_aware_datetime,
    require_duration,
    require_token,
)


MessageT = TypeVar("MessageT")


def _runtime_value(value: object) -> object:
    """Erase static narrowing before validating a runtime trust boundary."""

    return value


@dataclass(slots=True)
class _Pending(Generic[MessageT]):
    instance_id: int
    message: QueueMessage[MessageT]
    attempts: int
    available_at: datetime
    sequence: int


@dataclass(slots=True)
class _InFlight(Generic[MessageT]):
    pending: _Pending[MessageT]
    receipt_handle: str
    leased_until: datetime


@dataclass(frozen=True, slots=True)
class DeadLetter(Generic[MessageT]):
    """Inspectable terminal record emitted by the fake."""

    message: QueueMessage[MessageT]
    delivery_attempt: int
    failed_at: datetime
    reason: str


class QueueFake(Generic[MessageT], QueuePort[MessageT]):
    """Manual-clock queue fake with explicit failure-order injection.

    The fake never starts a thread, sleeps, opens a socket, or imports a
    provider SDK. Every time-dependent state transition is driven by
    :meth:`advance` or another public operation at the current virtual time.
    """

    def __init__(self, *, start_at: datetime) -> None:
        require_aware_datetime(start_at, field="start_at")
        self._now = start_at
        self._pending: dict[str, list[_Pending[MessageT]]] = defaultdict(list)
        self._inflight: dict[str, _InFlight[MessageT]] = {}
        self._known_messages: dict[str, QueueMessage[MessageT]] = {}
        self._dead_letters: dict[str, list[DeadLetter[MessageT]]] = defaultdict(list)
        self._issued_receipts: set[str] = set()
        self._closed_receipts: set[str] = set()
        self._next_instance_id = 1
        self._next_sequence = 1
        self._next_receipt = 1

    @property
    def now(self) -> datetime:
        """Return the current virtual time."""

        return self._now

    def send(self, message: QueueMessage[MessageT]) -> None:
        message_candidate = _runtime_value(message)
        if not isinstance(message_candidate, QueueMessage):
            raise InvalidQueueMessage("message must be a QueueMessage")
        existing = self._known_messages.get(message.message_id)
        if existing is not None and existing != message:
            raise InvalidQueueMessage(
                "message_id cannot identify different message content"
            )
        self._known_messages[message.message_id] = message
        self._enqueue(message, attempts=0, available_at=message.available_at)

    def receive(
        self, queue_name: str, *, lease: timedelta
    ) -> QueueDelivery[MessageT] | None:
        require_token(queue_name, field="queue_name")
        require_duration(lease, field="lease")
        self._expire_leases()
        candidates = [
            pending
            for pending in self._pending.get(queue_name, [])
            if pending.available_at <= self._now
        ]
        if not candidates:
            return None
        selected = min(candidates, key=lambda item: item.sequence)
        leased_until = self._checked_add(self._now, lease, field="lease")
        self._pending[queue_name].remove(selected)
        selected.attempts += 1
        receipt = f"queue-fake-{self._next_receipt:016x}"
        self._next_receipt += 1
        inflight = _InFlight(
            pending=selected,
            receipt_handle=receipt,
            leased_until=leased_until,
        )
        self._inflight[receipt] = inflight
        self._issued_receipts.add(receipt)
        return self._delivery(inflight)

    def acknowledge(self, receipt_handle: str) -> None:
        inflight = self._active_receipt(receipt_handle)
        self._close_receipt(inflight.receipt_handle)

    def retry(self, receipt_handle: str, *, delay: timedelta = timedelta(0)) -> None:
        require_duration(delay, field="delay", allow_zero=True)
        inflight = self._active_receipt(receipt_handle)
        pending = inflight.pending
        if pending.attempts >= pending.message.max_attempts:
            self._close_receipt(inflight.receipt_handle)
            self._dead_letter(pending, reason="MAX_ATTEMPTS_EXHAUSTED")
            return
        available_at = self._checked_add(self._now, delay, field="delay")
        self._close_receipt(inflight.receipt_handle)
        pending.available_at = available_at
        pending.sequence = self._take_sequence()
        self._pending[pending.message.queue_name].append(pending)

    def extend_lease(
        self, receipt_handle: str, *, lease: timedelta
    ) -> QueueDelivery[MessageT]:
        require_duration(lease, field="lease")
        inflight = self._active_receipt(receipt_handle)
        leased_until = self._checked_add(self._now, lease, field="lease")
        inflight.leased_until = leased_until
        return self._delivery(inflight)

    def advance(self, duration: timedelta) -> None:
        """Move virtual time forward and apply every expired lease."""

        require_duration(duration, field="duration", allow_zero=True)
        self._now = self._checked_add(self._now, duration, field="duration")
        self._expire_leases()

    def inject_duplicate(self, message_id: str, *, copies: int = 1) -> None:
        """Add exact duplicate occurrences for a previously sent message."""

        require_token(message_id, field="message_id")
        copies_candidate = _runtime_value(copies)
        if (
            isinstance(copies_candidate, bool)
            or not isinstance(copies_candidate, int)
            or not 1 <= copies_candidate <= 100
        ):
            raise InvalidQueueMessage("copies must be an integer between 1 and 100")
        try:
            message = self._known_messages[message_id]
        except KeyError as exc:
            raise InvalidQueueMessage("cannot duplicate an unknown message_id") from exc
        for _ in range(copies):
            self._enqueue(
                message,
                attempts=0,
                available_at=max(self._now, message.available_at),
            )

    def inject_out_of_order(
        self, queue_name: str, *, message_ids: Sequence[str]
    ) -> None:
        """Replace pending FIFO order with an exact reviewed occurrence order."""

        require_token(queue_name, field="queue_name")
        if isinstance(message_ids, (str, bytes)) or not message_ids:
            raise InvalidQueueMessage("message_ids must be a non-empty sequence")
        desired = list(message_ids)
        for message_id in desired:
            require_token(message_id, field="message_ids[]")
        pending = list(self._pending.get(queue_name, []))
        actual_ids = [item.message.message_id for item in pending]
        if Counter(desired) != Counter(actual_ids):
            raise InvalidQueueMessage(
                "out-of-order injection must name every pending occurrence exactly once"
            )
        buckets: dict[str, list[_Pending[MessageT]]] = defaultdict(list)
        for item in sorted(pending, key=lambda value: value.sequence):
            buckets[item.message.message_id].append(item)
        reordered: list[_Pending[MessageT]] = []
        for message_id in desired:
            item = buckets[message_id].pop(0)
            item.sequence = self._take_sequence()
            reordered.append(item)
        self._pending[queue_name] = reordered

    def pending_message_ids(self, queue_name: str) -> tuple[str, ...]:
        """Return pending occurrence identities in deterministic delivery order."""

        require_token(queue_name, field="queue_name")
        self._expire_leases()
        return tuple(
            item.message.message_id
            for item in sorted(
                self._pending.get(queue_name, []),
                key=lambda value: value.sequence,
            )
        )

    def dead_letters(self, queue_name: str) -> tuple[DeadLetter[MessageT], ...]:
        """Return immutable DLQ observations without mutating queue state."""

        require_token(queue_name, field="queue_name")
        self._expire_leases()
        return tuple(self._dead_letters.get(queue_name, ()))

    def inflight_count(self, queue_name: str) -> int:
        """Return active delivery occurrence count for one queue."""

        require_token(queue_name, field="queue_name")
        self._expire_leases()
        return sum(
            inflight.pending.message.queue_name == queue_name
            for inflight in self._inflight.values()
        )

    def _enqueue(
        self,
        message: QueueMessage[MessageT],
        *,
        attempts: int,
        available_at: datetime,
    ) -> None:
        pending = _Pending(
            instance_id=self._next_instance_id,
            message=message,
            attempts=attempts,
            available_at=available_at,
            sequence=self._take_sequence(),
        )
        self._next_instance_id += 1
        self._pending[message.queue_name].append(pending)

    def _take_sequence(self) -> int:
        sequence = self._next_sequence
        self._next_sequence += 1
        return sequence

    @staticmethod
    def _checked_add(when: datetime, duration: timedelta, *, field: str) -> datetime:
        try:
            return when + duration
        except OverflowError as exc:
            raise InvalidQueueMessage(
                f"{field} exceeds the supported datetime range"
            ) from exc

    def _delivery(self, inflight: _InFlight[MessageT]) -> QueueDelivery[MessageT]:
        return QueueDelivery(
            message=inflight.pending.message,
            receipt_handle=inflight.receipt_handle,
            delivery_attempt=inflight.pending.attempts,
            leased_until=inflight.leased_until,
        )

    def _active_receipt(self, receipt_handle: str) -> _InFlight[MessageT]:
        require_token(receipt_handle, field="receipt_handle")
        self._expire_leases()
        active = self._inflight.get(receipt_handle)
        if active is not None:
            return active
        if (
            receipt_handle in self._issued_receipts
            or receipt_handle in self._closed_receipts
        ):
            raise StaleReceiptHandle("receipt handle is no longer active")
        raise UnknownReceiptHandle("receipt handle was not issued by this queue")

    def _close_receipt(self, receipt_handle: str) -> None:
        del self._inflight[receipt_handle]
        self._closed_receipts.add(receipt_handle)

    def _expire_leases(self) -> None:
        expired = sorted(
            (
                inflight
                for inflight in self._inflight.values()
                if inflight.leased_until <= self._now
            ),
            key=lambda value: (value.leased_until, value.receipt_handle),
        )
        for inflight in expired:
            self._close_receipt(inflight.receipt_handle)
            pending = inflight.pending
            if pending.attempts >= pending.message.max_attempts:
                self._dead_letter(pending, reason="LEASE_EXPIRED_MAX_ATTEMPTS")
                continue
            pending.available_at = self._now
            pending.sequence = self._take_sequence()
            self._pending[pending.message.queue_name].append(pending)

    def _dead_letter(self, pending: _Pending[MessageT], *, reason: str) -> None:
        self._dead_letters[pending.message.queue_name].append(
            DeadLetter(
                message=pending.message,
                delivery_attempt=pending.attempts,
                failed_at=self._now,
                reason=reason,
            )
        )
