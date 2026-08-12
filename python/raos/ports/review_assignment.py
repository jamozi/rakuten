"""Inward protocols for the ST-0901 PR2 recorded-local seam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.publishing.review_assignment_operations import (
    RecordedReviewerAuthorizationV1,
    ReviewAssignmentRequest,
    ReviewAssignmentResult,
)


@runtime_checkable
class RecordedReviewerAuthorizationSource(Protocol):
    """Issue the single adapter-produced recorded authorization argument."""

    def issue_authorization(
        self, request: ReviewAssignmentRequest
    ) -> RecordedReviewerAuthorizationV1:
        """Bind one exact scripted request without ambient identity lookup."""

        ...


@runtime_checkable
class ReviewAssignmentExchange(Protocol):
    """Exchange one exact authorized request for one recorded-local result."""

    def exchange(
        self,
        authorization: RecordedReviewerAuthorizationV1,
        request: ReviewAssignmentRequest,
    ) -> ReviewAssignmentResult:
        """Return one scripted result or exact retained idempotent replay."""

        ...


__all__ = ["RecordedReviewerAuthorizationSource", "ReviewAssignmentExchange"]
