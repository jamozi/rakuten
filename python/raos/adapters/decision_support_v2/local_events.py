"""Bounded in-memory analytics sink; production sender is absent."""

from __future__ import annotations

from raos.domain.decision_support_v2.events import AnalyticsEvent


class LocalEventSink:
    mode = "LOCAL_SINK_ONLY"
    external_action_count = 0

    __slots__ = ("_events", "_limit")

    def __init__(self, *, limit: int = 1000) -> None:
        if limit < 1 or limit > 100_000:
            raise ValueError("invalid local event limit")
        self._events: list[AnalyticsEvent] = []
        self._limit = limit

    def collect(self, event: AnalyticsEvent) -> str:
        if len(self._events) >= self._limit:
            raise OverflowError("local event sink is full")
        self._events.append(event)
        return f"LOCAL:{len(self._events):06d}"

    def events(self) -> tuple[AnalyticsEvent, ...]:
        return tuple(self._events)


__all__ = ["LocalEventSink"]
