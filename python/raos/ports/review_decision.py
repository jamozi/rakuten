"""Inward protocols for the ST-0901 PR3 recorded-local seam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.publishing.review_decision_operations import (
    RecordReviewDecisionRequest,
    RecordReviewDecisionResultV1,
    RecordedReviewDecisionAuthorizationV1,
)


@runtime_checkable
class RecordedReviewDecisionAuthorizationSource(Protocol):
    """Issue the sole adapter-produced recorded authorization record."""

    def issue_authorization(
        self,
        request: RecordReviewDecisionRequest,
    ) -> RecordedReviewDecisionAuthorizationV1:
        """Bind one exact scripted request without ambient identity lookup."""

        ...


@runtime_checkable
class ReviewDecisionExchange(Protocol):
    """Append one exact authorized negative decision in recorded-local state."""

    def exchange(
        self,
        authorization: RecordedReviewDecisionAuthorizationV1,
        request: RecordReviewDecisionRequest,
    ) -> RecordReviewDecisionResultV1:
        """Return one append result or exact retained idempotent replay."""

        ...


__all__ = [
    "RecordedReviewDecisionAuthorizationSource",
    "ReviewDecisionExchange",
]
