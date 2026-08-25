"""Application service for owner-private ST-1704 affiliate learning."""

from __future__ import annotations

from typing import final

from raos.domain.editorial.affiliate_learning import (
    MeasurementContract,
    build_learning_report,
)
from raos.ports.affiliate_learning import (
    AffiliateLearningAppendResult,
    AffiliateLearningLedgerStore,
    AffiliateLearningObservationInput,
)


@final
class AffiliateLearningService:
    __slots__ = ("_contract", "_input", "_store")

    def __init__(
        self,
        *,
        contract: MeasurementContract,
        store: AffiliateLearningLedgerStore,
        observation_input: AffiliateLearningObservationInput,
    ) -> None:
        if (
            type(contract) is not MeasurementContract
            or not callable(getattr(store, "initialize", None))
            or not callable(getattr(store, "read", None))
            or not callable(getattr(store, "append", None))
            or not callable(getattr(observation_input, "read_observation", None))
        ):
            raise TypeError("AFFILIATE_LEARNING_SERVICE_INVALID")
        self._contract = contract
        self._store = store
        self._input = observation_input

    def doctor(self) -> dict[str, object]:
        ledger = self._store.read()
        return {
            "contract_sha256": self._contract.sha256,
            "event_count": len(ledger.events),
            "head_sha256": ledger.head_sha256,
            "network_requests": 0,
            "publication_actions": 0,
            "schema": "ST1704_AFFILIATE_LEARNING_DOCTOR_V2",
            "status": "LOCAL_READY",
            "tracking_activation": "DISABLED_OD_012",
            "writes": 0,
        }

    def initialize(self) -> dict[str, object]:
        ledger, created = self._store.initialize()
        return {
            "contract_sha256": self._contract.sha256,
            "created": created,
            "event_count": len(ledger.events),
            "head_sha256": ledger.head_sha256,
            "network_requests": 0,
            "publication_actions": 0,
            "schema": "ST1704_AFFILIATE_LEARNING_INIT_V2",
            "status": "INITIALIZED" if created else "ALREADY_INITIALIZED",
            "tracking_activation": "DISABLED_OD_012",
        }

    def record(self) -> dict[str, object]:
        observation = self._input.read_observation()
        result: AffiliateLearningAppendResult = self._store.append(observation)
        return {
            "contract_sha256": self._contract.sha256,
            "disposition": result.disposition.value,
            "event_count": len(result.ledger.events),
            "event_sha256": result.event_sha256,
            "head_sha256": result.ledger.head_sha256,
            "network_requests": 0,
            "publication_actions": 0,
            "schema": "ST1704_AFFILIATE_LEARNING_RECORD_V2",
            "tracking_activation": "DISABLED_OD_012",
        }

    def report(self) -> dict[str, object]:
        return build_learning_report(self._store.read(), contract=self._contract)


__all__ = ["AffiliateLearningService"]
