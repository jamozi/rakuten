"""Inward ports for synthetic route eligibility and atomic local controls."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from raos.domain.ai.routing import (
    BudgetCommit,
    BudgetRelease,
    BudgetReservation,
    ReservationIntent,
    RouteIdentity,
    SyntheticRouteCertification,
)


@runtime_checkable
class SyntheticRouteEligibilityPort(Protocol):
    """Return only explicitly injected local certification fixtures."""

    def candidates_for(
        self, *, task_code: str
    ) -> tuple[SyntheticRouteCertification, ...]:
        """Return a closed deterministic candidate set for one exact task."""

        ...


@runtime_checkable
class DevelopmentAiControlPort(Protocol):
    """Atomically enforce a synthetic cap and one-way route circuit."""

    def reserve(self, *, intent: ReservationIntent, now: datetime) -> BudgetReservation:
        """Reserve the exact quoted amount at most once."""

        ...

    def commit(
        self,
        *,
        reservation: BudgetReservation,
        committed_jpy: int,
        now: datetime,
    ) -> BudgetCommit:
        """Commit one active reservation at most once."""

        ...

    def release(
        self, *, reservation: BudgetReservation, now: datetime
    ) -> BudgetRelease:
        """Release one active reservation at most once."""

        ...

    def trip_open(self, *, identity: RouteIdentity, now: datetime) -> None:
        """Irreversibly open the process-local circuit for one route."""

        ...


__all__ = ["DevelopmentAiControlPort", "SyntheticRouteEligibilityPort"]
