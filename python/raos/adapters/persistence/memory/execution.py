"""Adapter-private cancellation/deadline state owned by UoW factories."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from time import monotonic_ns
from typing import TypeAlias

from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


class _ExecutionPoint(str, Enum):
    PRE_CHECKOUT = "PRE_CHECKOUT"
    POST_CHECKOUT = "POST_CHECKOUT"
    POST_IDENTITY = "POST_IDENTITY"
    PRE_SESSION_BEGIN = "PRE_SESSION_BEGIN"
    PRE_EXPOSURE = "PRE_EXPOSURE"
    PRE_REPOSITORY_QUERY_OR_DML = "PRE_REPOSITORY_QUERY_OR_DML"
    PRE_FLUSH = "PRE_FLUSH"
    PRE_COMMIT = "PRE_COMMIT"
    POST_KNOWN_DRIVER_RETURN = "POST_KNOWN_DRIVER_RETURN"


@dataclass(frozen=True, slots=True)
class _ExecutionBudget:
    """Immutable composition budget; absence means no local deadline."""

    timeout_ns: int | None = None

    def __post_init__(self) -> None:
        if self.timeout_ns is not None and (
            type(self.timeout_ns) is not int or self.timeout_ns < 0
        ):
            raise ValueError("INVALID_EXECUTION_BUDGET") from None


class _ExecutionState:
    """One mutable state per outer UoW; joined scopes reuse this identity."""

    __slots__ = (
        "_cancelled",
        "_deadline_ns",
        "_observed_points",
    )

    def __init__(self, budget: _ExecutionBudget) -> None:
        if type(budget) is not _ExecutionBudget:
            raise ValueError("INVALID_EXECUTION_BUDGET") from None
        started_ns = monotonic_ns()
        self._deadline_ns = (
            None if budget.timeout_ns is None else started_ns + budget.timeout_ns
        )
        self._cancelled = False
        self._observed_points: list[_ExecutionPoint] = []

    def _cancel(self) -> None:
        self._cancelled = True

    def require_allowed(self, point: _ExecutionPoint) -> None:
        if type(point) is not _ExecutionPoint:
            raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None
        self._observed_points.append(point)
        if self._cancelled:
            raise PersistenceError(PersistenceErrorCode.CANCELLED) from None
        deadline_ns = self._deadline_ns
        if deadline_ns is not None and monotonic_ns() >= deadline_ns:
            raise PersistenceError(PersistenceErrorCode.DEADLINE_EXCEEDED) from None

    def observe_known_driver_return(self) -> None:
        """Record the lifecycle point without reclassifying a known DB result."""

        self._observed_points.append(_ExecutionPoint.POST_KNOWN_DRIVER_RETURN)

    def _observations(self) -> tuple[_ExecutionPoint, ...]:
        return tuple(self._observed_points)


class _ExecutionStateFactory:
    """Concrete factory-private owner; it accepts no arbitrary callback."""

    __slots__ = ("_budget",)

    def __init__(self, budget: _ExecutionBudget | None = None) -> None:
        if budget is not None and type(budget) is not _ExecutionBudget:
            raise ValueError("INVALID_EXECUTION_BUDGET") from None
        self._budget = _ExecutionBudget() if budget is None else budget

    def new_outer_state(self) -> _ExecutionState:
        return _ExecutionState(self._budget)


ExecutionPoint: TypeAlias = _ExecutionPoint
ExecutionState: TypeAlias = _ExecutionState
ExecutionStateFactory: TypeAlias = _ExecutionStateFactory


__all__: list[str] = []
