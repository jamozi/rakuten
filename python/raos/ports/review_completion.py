"""Narrow recorded-local ports for ST-0901 review completion V2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.publishing.review_completion_v2 import (
    RecordedReviewCompletionAuthorizationV2,
    ReviewCompletionRequestV2,
    ReviewCompletionResultV2,
)


@runtime_checkable
class RecordedReviewCompletionAuthorizationSource(Protocol):
    def issue_authorization(
        self,
        request: ReviewCompletionRequestV2,
    ) -> RecordedReviewCompletionAuthorizationV2: ...


@runtime_checkable
class ReviewCompletionExchange(Protocol):
    def exchange(
        self,
        authorization: RecordedReviewCompletionAuthorizationV2,
        request: ReviewCompletionRequestV2,
    ) -> ReviewCompletionResultV2: ...


__all__ = (
    "RecordedReviewCompletionAuthorizationSource",
    "ReviewCompletionExchange",
)
