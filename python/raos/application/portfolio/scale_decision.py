"""Application service for one process-local ST-1805 evaluation."""

from __future__ import annotations

from typing import final

from raos.domain.portfolio.scale_decision import (
    PortfolioDecisionCommand,
    PortfolioDecisionEvidence,
    PortfolioDecisionFailure,
    PortfolioDecisionFailureCode,
    PortfolioDecisionReport,
    build_portfolio_decision_report,
    canonical_input_digest,
    fail_portfolio_decision,
)
from raos.ports.scale_decision import RecordedPortfolioDecisionExchange


@final
class RecordedPortfolioDecisionJob:
    __slots__ = ("_exchange",)

    def __init__(self, *, exchange: RecordedPortfolioDecisionExchange) -> None:
        if not callable(getattr(exchange, "read", None)):
            fail_portfolio_decision()
        self._exchange = exchange

    def evaluate(self, command: PortfolioDecisionCommand) -> PortfolioDecisionReport:
        if type(command) is not PortfolioDecisionCommand:
            fail_portfolio_decision()
        observed: object = None
        try:
            observed = self._exchange.read(command)
        except PortfolioDecisionFailure:
            raise
        except Exception:
            fail_portfolio_decision(
                PortfolioDecisionFailureCode.RECORDED_EXCHANGE_UNAVAILABLE
            )
        if type(observed) is not PortfolioDecisionEvidence:
            fail_portfolio_decision(
                PortfolioDecisionFailureCode.RECORDED_RESULT_MISMATCH
            )
        if (
            observed.recording_id != command.recording_id
            or observed.fixture_digest != command.fixture_digest
            or observed.fixture_length != command.fixture_length
            or observed.contract_digest != command.contract_digest
            or observed.input_digest != command.expected_input_digest
            or observed.source_pack_digest != command.expected_source_pack_digest
            or observed.program_id != command.program_id
            or canonical_input_digest(observed) != observed.input_digest
        ):
            fail_portfolio_decision(
                PortfolioDecisionFailureCode.RECORDED_RESULT_MISMATCH
            )
        return build_portfolio_decision_report(observed)


__all__ = ["RecordedPortfolioDecisionJob"]
