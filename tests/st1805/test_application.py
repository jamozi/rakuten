from __future__ import annotations

from collections.abc import Callable

import pytest

from raos.adapters.recorded_scale_decision import RecordedPortfolioDecisionAdapter
from raos.application.portfolio.scale_decision import RecordedPortfolioDecisionJob
from raos.domain.portfolio.scale_decision import (
    PortfolioDecisionCommand,
    PortfolioDecisionFailure,
    PortfolioDecisionFailureCode,
)


class _RaisingExchange:
    def read(self, command: PortfolioDecisionCommand) -> object:
        del command
        raise OSError("hostile adapter detail")


class _WrongResultExchange:
    def read(self, command: PortfolioDecisionCommand) -> object:
        del command
        return object()


def test_job_returns_report(
    fixture_bytes: bytes,
    command_factory: Callable[..., PortfolioDecisionCommand],
) -> None:
    report = RecordedPortfolioDecisionJob(
        exchange=RecordedPortfolioDecisionAdapter(fixture_bytes)
    ).evaluate(command_factory(fixture_bytes))
    assert report.payload()["overall"] == "BLOCKED"


def test_job_normalizes_hostile_adapter_failure(
    fixture_bytes: bytes,
    command_factory: Callable[..., PortfolioDecisionCommand],
) -> None:
    with pytest.raises(PortfolioDecisionFailure) as caught:
        RecordedPortfolioDecisionJob(exchange=_RaisingExchange()).evaluate(
            command_factory(fixture_bytes)
        )
    assert (
        caught.value.code is PortfolioDecisionFailureCode.RECORDED_EXCHANGE_UNAVAILABLE
    )
    assert "hostile" not in str(caught.value)


def test_job_rejects_wrong_result_type(
    fixture_bytes: bytes,
    command_factory: Callable[..., PortfolioDecisionCommand],
) -> None:
    with pytest.raises(PortfolioDecisionFailure) as caught:
        RecordedPortfolioDecisionJob(exchange=_WrongResultExchange()).evaluate(
            command_factory(fixture_bytes)
        )
    assert caught.value.code is PortfolioDecisionFailureCode.RECORDED_RESULT_MISMATCH


def test_job_rejects_invalid_command() -> None:
    job = RecordedPortfolioDecisionJob(exchange=_WrongResultExchange())
    with pytest.raises(PortfolioDecisionFailure) as caught:
        job.evaluate(object())  # type: ignore[arg-type]
    assert caught.value.code is PortfolioDecisionFailureCode.INVALID_ARGUMENT


def test_job_rejects_exchange_without_read() -> None:
    with pytest.raises(PortfolioDecisionFailure):
        RecordedPortfolioDecisionJob(exchange=object())  # type: ignore[arg-type]
