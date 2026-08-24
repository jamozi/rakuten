"""Inward durable recorded-event port for ST-1201 V2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.analytics.event_collector import EventDigest, ValidatedEvent
from raos.domain.analytics.event_collector_runtime_v2 import DurableEventReceiptV2


@runtime_checkable
class DurableEventStoreV2(Protocol):
    @property
    def mode(self) -> str: ...

    @property
    def action_count(self) -> int: ...

    def exchange_durable(
        self, event: ValidatedEvent, digest: EventDigest
    ) -> DurableEventReceiptV2: ...


__all__ = ["DurableEventStoreV2"]
