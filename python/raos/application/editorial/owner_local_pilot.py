"""Application service for the ST-1704 owner-local pilot ledger."""

from __future__ import annotations

from typing import final

from raos.domain.editorial.owner_local_pilot import build_report
from raos.ports.owner_local_pilot import (
    PilotAppendResult,
    PilotLedgerStore,
    PilotObservationInput,
)


@final
class OwnerLocalPilotService:
    __slots__ = ("_input", "_store")

    def __init__(
        self,
        *,
        store: PilotLedgerStore,
        observation_input: PilotObservationInput,
    ) -> None:
        if (
            not callable(getattr(store, "initialize", None))
            or not callable(getattr(store, "read", None))
            or not callable(getattr(store, "append", None))
            or not callable(getattr(observation_input, "read_observation", None))
        ):
            raise TypeError("OWNER_LOCAL_PILOT_SERVICE_INVALID")
        self._store = store
        self._input = observation_input

    def doctor(self) -> dict[str, object]:
        ledger = self._store.read()
        return {
            "event_count": len(ledger.events),
            "head_sha256": ledger.head_sha256,
            "network_requests": 0,
            "publication_actions": 0,
            "schema": "ST1704_OWNER_LOCAL_PILOT_DOCTOR_V1",
            "status": "LOCAL_READY",
            "tracking_activation": "DISABLED_OD_012",
            "writes": 0,
        }

    def initialize(self) -> dict[str, object]:
        ledger, created = self._store.initialize()
        return {
            "created": created,
            "event_count": len(ledger.events),
            "head_sha256": ledger.head_sha256,
            "network_requests": 0,
            "publication_actions": 0,
            "schema": "ST1704_OWNER_LOCAL_PILOT_INIT_V1",
            "status": "INITIALIZED" if created else "ALREADY_INITIALIZED",
            "tracking_activation": "DISABLED_OD_012",
        }

    def record(self) -> dict[str, object]:
        observation = self._input.read_observation()
        result: PilotAppendResult = self._store.append(observation)
        return {
            "disposition": result.disposition.value,
            "event_count": len(result.ledger.events),
            "event_sha256": result.event_sha256,
            "head_sha256": result.ledger.head_sha256,
            "network_requests": 0,
            "publication_actions": 0,
            "schema": "ST1704_OWNER_LOCAL_PILOT_RECORD_V1",
            "tracking_activation": "DISABLED_OD_012",
        }

    def report(self) -> dict[str, object]:
        return build_report(self._store.read())


__all__ = ["OwnerLocalPilotService"]
