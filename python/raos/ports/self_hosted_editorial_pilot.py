"""Narrow ports for the ST-1704 owner-gated review-draft runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailureCode,
    PublicVerification,
    ReviewDraftReceipt,
    ReviewDraftRequest,
    canonical_sha256,
    fail_editorial_pilot,
    require_sha256,
)


class ReviewDraftRevisionDisposition(StrEnum):
    """Closed outcomes for one fixed-ID review-draft revision observation."""

    OWNER_LIVE_APPLIED = "OWNER_LIVE_APPLIED"
    OWNER_LIVE_RECOVERED_APPLIED = "OWNER_LIVE_RECOVERED_APPLIED"
    OWNER_LIVE_RECOVERED_PREDECESSOR = "OWNER_LIVE_RECOVERED_PREDECESSOR"
    OWNER_LIVE_VERIFIED = "OWNER_LIVE_VERIFIED"


@dataclass(frozen=True, slots=True, repr=False)
class ReviewDraftRevisionBinding:
    """One successor request bound to an existing Draft ID and predecessor."""

    predecessor: ReviewDraftRequest
    successor: ReviewDraftRequest
    draft_id: int
    generation: int
    operation_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.predecessor) is not ReviewDraftRequest
            or type(self.successor) is not ReviewDraftRequest
            or self.predecessor.article_id != self.successor.article_id
            or self.predecessor.article_id == "st1703-first-suitcase-comparison"
            or self.predecessor.public_slug != self.successor.public_slug
            or self.predecessor.request_sha256 == self.successor.request_sha256
            or self.predecessor.packet_sha256 == self.successor.packet_sha256
            or type(self.draft_id) is not int
            or not 1 <= self.draft_id <= (1 << 63) - 1
            or type(self.generation) is not int
            or not 2 <= self.generation <= 32
            or require_sha256(self.operation_sha256)
            != canonical_sha256(self.operation_material())
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.JOURNAL_MISMATCH)

    def operation_material(self) -> dict[str, object]:
        return {
            "article_id": self.successor.article_id,
            "draft_id": self.draft_id,
            "generation": self.generation,
            "predecessor": {
                "content_sha256": (
                    self.predecessor.snapshot.payload.visible_content_sha256
                ),
                "packet_sha256": self.predecessor.packet_sha256,
                "payload_sha256": self.predecessor.snapshot.payload_sha256,
                "request_sha256": self.predecessor.request_sha256,
                "review_slug": self.predecessor.slug,
            },
            "schema": "RAOS_ST1704_REVIEW_DRAFT_REVISION_OPERATION_V1",
            "successor": {
                "content_sha256": self.successor.snapshot.payload.visible_content_sha256,
                "packet_sha256": self.successor.packet_sha256,
                "payload_sha256": self.successor.snapshot.payload_sha256,
                "request_sha256": self.successor.request_sha256,
                "review_slug": self.successor.slug,
            },
        }

    @classmethod
    def bind(
        cls,
        *,
        predecessor: ReviewDraftRequest,
        successor: ReviewDraftRequest,
        draft_id: int,
        generation: int,
    ) -> "ReviewDraftRevisionBinding":
        candidate = cls.__new__(cls)
        object.__setattr__(candidate, "predecessor", predecessor)
        object.__setattr__(candidate, "successor", successor)
        object.__setattr__(candidate, "draft_id", draft_id)
        object.__setattr__(candidate, "generation", generation)
        object.__setattr__(candidate, "operation_sha256", "0" * 64)
        operation_sha256 = canonical_sha256(candidate.operation_material())
        return cls(
            predecessor=predecessor,
            successor=successor,
            draft_id=draft_id,
            generation=generation,
            operation_sha256=operation_sha256,
        )


@dataclass(frozen=True, slots=True, repr=False)
class ReviewDraftRevisionObservation:
    """Sanitized result of applying, recovering, or verifying one revision."""

    operation_sha256: str
    response_sha256: str
    draft_id: int
    disposition: ReviewDraftRevisionDisposition

    def __post_init__(self) -> None:
        require_sha256(self.operation_sha256)
        require_sha256(self.response_sha256)
        if (
            type(self.draft_id) is not int
            or not 1 <= self.draft_id <= (1 << 63) - 1
            or type(self.disposition) is not ReviewDraftRevisionDisposition
        ):
            fail_editorial_pilot(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)


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
    "ReviewDraftRevisionBinding",
    "ReviewDraftRevisionDisposition",
    "ReviewDraftRevisionObservation",
    "ReviewDraftJournalPort",
]
