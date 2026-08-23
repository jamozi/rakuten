"""Shared inward Outbox insert-only capability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from raos.domain.shared.events import DomainEvent, require_allowed_event


@dataclass(frozen=True, slots=True)
class ValidatedOutboxEvent:
    event: DomainEvent

    def __post_init__(self) -> None:
        try:
            require_allowed_event(self.event)
        except ValueError:
            raise ValueError("invalid outbox event") from None


@runtime_checkable
class OutboxEventAppender(Protocol):
    def append_many(self, events: tuple[ValidatedOutboxEvent, ...]) -> None: ...


__all__ = ["OutboxEventAppender", "ValidatedOutboxEvent"]
