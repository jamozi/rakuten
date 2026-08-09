"""Ordered, process-local recorded exchange for ST-0501."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import NoReturn, SupportsIndex, final, get_args

from raos.config.runtime import RuntimeEnvironment
from raos.domain.portfolio.workflow import (
    PortfolioOperation,
    PortfolioWorkflowFailureCode,
    fail_portfolio_workflow,
)
from raos.ports.portfolio_workflow import (
    PortfolioWorkflowOutcome,
    PortfolioWorkflowRequest,
)


_MAX_SCRIPT_CAPACITY = 100_000
_REQUEST_TYPES = get_args(PortfolioWorkflowRequest)
_OUTCOME_TYPES = get_args(PortfolioWorkflowOutcome)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedWorkflowStep:
    request: PortfolioWorkflowRequest
    outcome: PortfolioWorkflowOutcome

    def __post_init__(self) -> None:
        request_operation = getattr(self.request, "operation", None)
        outcome_operation = getattr(self.outcome, "operation", None)
        if (
            type(self.request) not in _REQUEST_TYPES
            or type(self.outcome) not in _OUTCOME_TYPES
            or type(request_operation) is not PortfolioOperation
            or type(outcome_operation) is not PortfolioOperation
            or request_operation is not outcome_operation
        ):
            fail_portfolio_workflow()

    def __repr__(self) -> str:
        return "RecordedWorkflowStep(<redacted-portfolio-workflow>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded workflow serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class RecordedWorkflowMetadata:
    sequence: int
    operation: PortfolioOperation

    def __post_init__(self) -> None:
        if (
            type(self.sequence) is not int
            or self.sequence < 1
            or type(self.operation) is not PortfolioOperation
        ):
            fail_portfolio_workflow()

    def __repr__(self) -> str:
        return "RecordedWorkflowMetadata(<redacted-portfolio-workflow>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded workflow metadata serialization is not supported")


@final
class RecordedPortfolioWorkflowExchange:
    """Consume one exact pre-scripted request at a time, without persistence."""

    __slots__ = ("_history", "_index", "_lock", "_scripts")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        script_capacity: int,
        scripts: tuple[RecordedWorkflowStep, ...],
    ) -> None:
        if (
            environment is not RuntimeEnvironment.ENV_DEV
            or type(script_capacity) is not int
            or not 0 < script_capacity <= _MAX_SCRIPT_CAPACITY
            or type(scripts) is not tuple
            or not scripts
            or len(scripts) > script_capacity
            or any(type(step) is not RecordedWorkflowStep for step in scripts)
            or any(
                left.request == right.request
                for index, left in enumerate(scripts)
                for right in scripts[index + 1 :]
            )
        ):
            fail_portfolio_workflow()
        self._scripts = scripts
        self._index = 0
        self._history: tuple[RecordedWorkflowMetadata, ...] = ()
        self._lock = RLock()

    @property
    def history(self) -> tuple[RecordedWorkflowMetadata, ...]:
        with self._lock:
            return self._history

    @property
    def remaining(self) -> int:
        with self._lock:
            return len(self._scripts) - self._index

    def __repr__(self) -> str:
        return "RecordedPortfolioWorkflowExchange(<redacted-portfolio-workflow>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded workflow exchange serialization is not supported")

    def exchange(
        self,
        request: PortfolioWorkflowRequest,
    ) -> PortfolioWorkflowOutcome:
        with self._lock:
            if self._index >= len(self._scripts):
                fail_portfolio_workflow(
                    PortfolioWorkflowFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            step = self._scripts[self._index]
            if type(request) is not type(step.request) or request != step.request:
                fail_portfolio_workflow(
                    PortfolioWorkflowFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            self._index += 1
            self._history = (
                *self._history,
                RecordedWorkflowMetadata(
                    sequence=self._index,
                    operation=step.request.operation,
                ),
            )
            return step.outcome


__all__ = [
    "RecordedPortfolioWorkflowExchange",
    "RecordedWorkflowMetadata",
    "RecordedWorkflowStep",
]
