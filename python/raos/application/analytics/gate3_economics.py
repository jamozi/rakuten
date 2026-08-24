"""Application service for the process-local ST-1804 synthetic evaluator."""

from __future__ import annotations

from typing import final

from raos.domain.analytics.gate3_economics import (
    Gate3Command,
    Gate3EconomicsReport,
    Gate3Failure,
    Gate3FailureCode,
    RecordedEconomicsBatch,
    build_gate3_economics_report,
    canonical_input_digest,
    fail_gate3,
)
from raos.ports.gate3_economics import RecordedGate3EconomicsExchange


@final
class RecordedGate3EconomicsJob:
    __slots__ = ("_exchange",)

    def __init__(self, *, exchange: RecordedGate3EconomicsExchange) -> None:
        if not callable(getattr(exchange, "read", None)):
            fail_gate3()
        self._exchange = exchange

    def evaluate(self, command: Gate3Command) -> Gate3EconomicsReport:
        if type(command) is not Gate3Command:
            fail_gate3()
        observed: object = None
        try:
            observed = self._exchange.read(command)
        except Gate3Failure:
            raise
        except Exception:
            fail_gate3(Gate3FailureCode.RECORDED_EXCHANGE_UNAVAILABLE)
        if type(observed) is not RecordedEconomicsBatch:
            fail_gate3(Gate3FailureCode.RECORDED_RESULT_MISMATCH)
        if (
            observed.recording_id != command.recording_id
            or observed.fixture_digest != command.fixture_digest
            or observed.fixture_length != command.fixture_length
            or observed.contract_digest != command.contract_digest
            or observed.input_digest != command.expected_input_digest
            or observed.context_program != command.program_id
            or canonical_input_digest(observed.months) != observed.input_digest
        ):
            fail_gate3(Gate3FailureCode.RECORDED_RESULT_MISMATCH)
        return build_gate3_economics_report(observed)


__all__ = ["RecordedGate3EconomicsJob"]
