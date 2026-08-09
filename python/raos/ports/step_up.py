"""Inward factor-neutral source port for verified step-up assurance."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from raos.domain.iam.authentication import Session
from raos.domain.iam.step_up import StepUpGrant, StepUpVerificationOutcome


@runtime_checkable
class StepUpVerifier(Protocol):
    """Return normalized assurance without exposing provider or factor types."""

    def verify(
        self, *, session: Session, now: datetime
    ) -> StepUpGrant | StepUpVerificationOutcome | None:
        """Return a grant, explicit rejection, or absence for one session."""

        ...


__all__ = ["StepUpVerifier"]
