"""Adapter-private SQLAlchemy transaction state for ST-0308."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from time import monotonic_ns
from typing import NoReturn
from uuid import RFC_4122, UUID

from sqlalchemy.orm import Session

from raos.domain.shared.events import DomainEvent
from raos.domain.shared.persistence import AwareUtcDateTime, PendingEventBuffer
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


Uuid7Factory = Callable[[], UUID]


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


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
    """Immutable factory-owned local budget; absence means no deadline."""

    timeout_ns: int | None = None

    def __post_init__(self) -> None:
        if self.timeout_ns is not None and (
            type(self.timeout_ns) is not int or self.timeout_ns < 0
        ):
            raise ValueError("INVALID_EXECUTION_BUDGET") from None


class _ExecutionState:
    """One mutable cancellation/deadline state shared by joined scopes."""

    __slots__ = ("_cancelled", "_deadline_ns", "_observed_points")

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
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self._observed_points.append(point)
        # Canonical precedence is cancellation, then deadline.
        if self._cancelled:
            _fail(PersistenceErrorCode.CANCELLED)
        deadline_ns = self._deadline_ns
        if deadline_ns is not None and monotonic_ns() >= deadline_ns:
            _fail(PersistenceErrorCode.DEADLINE_EXCEEDED)

    def observe_known_driver_return(self) -> None:
        self._observed_points.append(_ExecutionPoint.POST_KNOWN_DRIVER_RETURN)

    def _observations(self) -> tuple[_ExecutionPoint, ...]:
        return tuple(self._observed_points)


class _ExecutionStateFactory:
    __slots__ = ("_budget",)

    def __init__(self, budget: _ExecutionBudget | None = None) -> None:
        if budget is not None and type(budget) is not _ExecutionBudget:
            raise ValueError("INVALID_EXECUTION_BUDGET") from None
        self._budget = _ExecutionBudget() if budget is None else budget

    def new_outer_state(self) -> _ExecutionState:
        return _ExecutionState(self._budget)


@dataclass(slots=True)
class _SqlAlchemyTransaction:
    """Private journal shared by one outer UoW and all of its joins."""

    transaction_id: UUID
    context: PersistenceContext
    timestamp: AwareUtcDateTime
    session: Session
    execution_state: _ExecutionState
    active: bool = True
    rollback_only: bool = False
    successful_dml_count: int = 0
    joined_count: int = 0
    acknowledged_buffers: list[PendingEventBuffer[DomainEvent]] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        if (
            type(self.transaction_id) is not UUID
            or self.transaction_id.version != 7
            or self.transaction_id.variant != RFC_4122
            or type(self.context) is not PersistenceContext
            or type(self.timestamp) is not AwareUtcDateTime
            or not isinstance(self.session, Session)
            or type(self.execution_state) is not _ExecutionState
            or type(self.successful_dml_count) is not int
            or self.successful_dml_count < 0
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def require_active(self) -> None:
        if not self.active:
            _fail(PersistenceErrorCode.TRANSACTION_CLOSED)

    def require_operation(self) -> None:
        self.require_active()
        if self.rollback_only:
            _fail(PersistenceErrorCode.TRANSACTION_ROLLBACK_ONLY)
        self.execution_state.require_allowed(
            _ExecutionPoint.PRE_REPOSITORY_QUERY_OR_DML
        )

    def poison(self) -> None:
        """Fail the transaction closed after a known pre-commit operation error."""

        self.require_active()
        self.rollback_only = True
        try:
            self.restore_acknowledged()
        except Exception:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def record_successful_dml(self) -> None:
        self.require_active()
        self.successful_dml_count += 1

    def acknowledge(self, buffer: PendingEventBuffer[DomainEvent]) -> None:
        self.require_active()
        if type(buffer) is not PendingEventBuffer:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self.acknowledged_buffers.append(buffer)

    def restore_acknowledged(self) -> None:
        for buffer in reversed(self.acknowledged_buffers):
            buffer._restore_acknowledged()
        self.acknowledged_buffers.clear()

    def finish_acknowledged(self) -> None:
        for buffer in self.acknowledged_buffers:
            buffer._finish_acknowledged()
        self.acknowledged_buffers.clear()


def require_uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


__all__: list[str] = []
