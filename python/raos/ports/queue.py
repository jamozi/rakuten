"""Provider-neutral at-least-once queue port.

The port models delivery mechanics only. Consumer idempotency, job state
transitions, persistence, and provider-specific configuration belong to later
Stories.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Generic, Protocol, TypeVar, runtime_checkable


MessageT = TypeVar("MessageT")


class QueueError(RuntimeError):
    """Base error for queue contract violations."""


class InvalidQueueMessage(QueueError, ValueError):
    """A queue message or operation argument violates the port contract."""


class ReceiptHandleError(QueueError):
    """A receipt handle cannot be used for the requested operation."""


class UnknownReceiptHandle(ReceiptHandleError):
    """The receipt handle was never issued by this queue instance."""


class StaleReceiptHandle(ReceiptHandleError):
    """The receipt handle was issued but is no longer active."""


def _runtime_value(value: object) -> object:
    """Erase static narrowing before validating a runtime trust boundary."""

    return value


def require_aware_datetime(value: object, *, field: str) -> None:
    """Reject naive timestamps at the queue trust boundary."""

    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InvalidQueueMessage(f"{field} must be a timezone-aware datetime")
    if value.utcoffset() is None:
        raise InvalidQueueMessage(f"{field} must have a defined UTC offset")


def require_duration(value: object, *, field: str, allow_zero: bool = False) -> None:
    """Validate a finite, non-negative or positive duration."""

    if not isinstance(value, timedelta):
        raise InvalidQueueMessage(f"{field} must be a timedelta")
    seconds = value.total_seconds()
    if seconds < 0 or (seconds == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise InvalidQueueMessage(f"{field} must be {qualifier}")


def require_token(value: object, *, field: str) -> None:
    """Require a bounded, printable token without provider assumptions."""

    if not isinstance(value, str):
        raise InvalidQueueMessage(f"{field} must be a string")
    if not value or value != value.strip() or len(value) > 200:
        raise InvalidQueueMessage(
            f"{field} must be a non-empty trimmed token of at most 200 characters"
        )
    if any(character.isspace() or not character.isprintable() for character in value):
        raise InvalidQueueMessage(f"{field} cannot contain whitespace or controls")


@dataclass(frozen=True, slots=True)
class QueueMessage(Generic[MessageT]):
    """One logical message whose identity survives duplicate delivery."""

    message_id: str
    queue_name: str
    idempotency_key: str
    payload: MessageT
    available_at: datetime
    max_attempts: int = 3

    def __post_init__(self) -> None:
        require_token(self.message_id, field="message_id")
        require_token(self.queue_name, field="queue_name")
        require_token(self.idempotency_key, field="idempotency_key")
        require_aware_datetime(self.available_at, field="available_at")
        max_attempts = _runtime_value(self.max_attempts)
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
            raise InvalidQueueMessage("max_attempts must be an integer")
        if not 1 <= self.max_attempts <= 50:
            raise InvalidQueueMessage("max_attempts must be between 1 and 50")


@dataclass(frozen=True, slots=True)
class QueueDelivery(Generic[MessageT]):
    """A leased delivery occurrence for a logical queue message."""

    message: QueueMessage[MessageT]
    receipt_handle: str
    delivery_attempt: int
    leased_until: datetime

    def __post_init__(self) -> None:
        message = _runtime_value(self.message)
        if not isinstance(message, QueueMessage):
            raise InvalidQueueMessage("message must be a QueueMessage")
        require_token(self.receipt_handle, field="receipt_handle")
        delivery_attempt = _runtime_value(self.delivery_attempt)
        if (
            isinstance(delivery_attempt, bool)
            or not isinstance(delivery_attempt, int)
            or delivery_attempt < 1
        ):
            raise InvalidQueueMessage("delivery_attempt must be a positive integer")
        require_aware_datetime(self.leased_until, field="leased_until")


@runtime_checkable
class QueuePort(Protocol[MessageT]):
    """Minimal delivery port implemented by local and provider adapters."""

    def send(self, message: QueueMessage[MessageT]) -> None:
        """Enqueue one delivery occurrence."""

        ...

    def receive(
        self, queue_name: str, *, lease: timedelta
    ) -> QueueDelivery[MessageT] | None:
        """Lease the next currently available occurrence, if one exists."""

        ...

    def acknowledge(self, receipt_handle: str) -> None:
        """Permanently complete one leased delivery occurrence."""

        ...

    def retry(self, receipt_handle: str, *, delay: timedelta = timedelta(0)) -> None:
        """Release an occurrence for retry or dead-letter it at its budget."""

        ...

    def extend_lease(
        self, receipt_handle: str, *, lease: timedelta
    ) -> QueueDelivery[MessageT]:
        """Renew ownership of an active delivery occurrence."""

        ...
