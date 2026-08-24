"""Application service for one process-local ST-1803 recorded observation."""

from __future__ import annotations

from typing import final

from raos.domain.analytics.gate2_observation import (
    Gate2ObservationReport,
    ObservationCommand,
    ObservationFailure,
    ObservationFailureCode,
    RecordedObservationBatch,
    build_gate2_observation_report,
    canonical_input_digest,
    fail_observation,
)
from raos.ports.gate2_observation import RecordedGate2ObservationExchange


@final
class RecordedGate2ObservationJob:
    """Read once and return an immutable, non-persisted improvement report."""

    __slots__ = ("_exchange",)

    def __init__(self, *, exchange: RecordedGate2ObservationExchange) -> None:
        if not callable(getattr(exchange, "read", None)):
            fail_observation()
        self._exchange = exchange

    def observe(self, command: ObservationCommand) -> Gate2ObservationReport:
        if type(command) is not ObservationCommand:
            fail_observation()
        observed: object = None
        try:
            observed = self._exchange.read(command)
        except ObservationFailure:
            raise
        except Exception:
            fail_observation(ObservationFailureCode.RECORDED_EXCHANGE_UNAVAILABLE)
        if type(observed) is not RecordedObservationBatch:
            fail_observation(ObservationFailureCode.RECORDED_RESULT_MISMATCH)
        if (
            observed.recording_id != command.recording_id
            or observed.fixture_digest != command.fixture_digest
            or observed.fixture_length != command.fixture_length
            or observed.contract_digest != command.contract_digest
            or observed.context_period != command.period
            or observed.program_id != command.program_id
            or observed.input_digest != command.expected_input_digest
            or canonical_input_digest(observed.articles, observed.program_observation)
            != observed.input_digest
        ):
            fail_observation(ObservationFailureCode.RECORDED_RESULT_MISMATCH)
        return build_gate2_observation_report(observed)


__all__ = ["RecordedGate2ObservationJob"]
