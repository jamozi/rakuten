"""Single inward exchange port for the disabled ST-1201 local seam."""

from __future__ import annotations

from typing import Protocol

from raos.domain.analytics.event_collector import (
    EventDigest,
    RecordedStoreOutcome,
    ValidatedEvent,
)


class EventCollectionExchange(Protocol):
    """Compare one validated synthetic event with one recorded script step."""

    def exchange(
        self,
        event: ValidatedEvent,
        digest: EventDigest,
    ) -> RecordedStoreOutcome:
        """Return one pre-recorded outcome without storing event content."""

        ...


__all__ = ["EventCollectionExchange"]
