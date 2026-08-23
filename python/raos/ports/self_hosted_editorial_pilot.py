"""Narrow ports for the ST-1704 owner-gated review-draft runtime."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.editorial.self_hosted_editorial_pilot import (
    PublicVerification,
    ReviewDraftReceipt,
    ReviewDraftRequest,
)


@runtime_checkable
class RecordedReviewDraftPort(Protocol):
    """Consume one already-captured response without any network authority."""

    def create(
        self, request: ReviewDraftRequest, recorded_response: bytes
    ) -> ReviewDraftReceipt: ...

    def recover(
        self, request: ReviewDraftRequest, recorded_response: bytes
    ) -> ReviewDraftReceipt: ...


@runtime_checkable
class RecordedPublicReadPort(Protocol):
    """Verify one already-captured public response without fetching it."""

    def verify(
        self, request: ReviewDraftRequest, recorded_response: bytes
    ) -> PublicVerification: ...


@runtime_checkable
class OwnerOperatedWordPressPort(Protocol):
    """The fixed-origin, fixed-operation owner-gated live boundary."""

    def preflight(self, request: ReviewDraftRequest, command: str) -> None: ...

    def resolve_public_target(
        self, request: ReviewDraftRequest, command: str
    ) -> int | None: ...

    def create(self, request: ReviewDraftRequest) -> ReviewDraftReceipt: ...

    def recover(self, request: ReviewDraftRequest) -> ReviewDraftReceipt: ...

    def verify_public(
        self, request: ReviewDraftRequest, expected_public_post_id: int
    ) -> PublicVerification: ...


@runtime_checkable
class ReviewDraftJournalPort(Protocol):
    """Apply or reconcile one packet-digest-bound recorded operation."""

    def create(
        self, request: ReviewDraftRequest, recorded_response: bytes
    ) -> ReviewDraftReceipt: ...

    def recover(
        self, request: ReviewDraftRequest, recorded_response: bytes
    ) -> ReviewDraftReceipt: ...


__all__ = [
    "OwnerOperatedWordPressPort",
    "RecordedPublicReadPort",
    "RecordedReviewDraftPort",
    "ReviewDraftJournalPort",
]
