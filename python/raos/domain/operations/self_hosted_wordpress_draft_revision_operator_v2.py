"""Closed values for hash-bound ST-1704 Review Draft revisions.

The operation can update only the four existing ST-1704 Review Drafts.  It
preserves the post id and Draft status and carries the complete successor body
as ASCII base64 so proposal canonicalization is identical in Python and PHP.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
from enum import StrEnum
from typing import Final

from raos.domain.operations.self_hosted_wordpress_publication_operator_v2 import (
    PUBLICATION_OPERATOR_CONTRACT_VERSION,
    PUBLICATION_OPERATOR_ORIGIN,
    PUBLICATION_OPERATOR_PROFILE_VERSION,
    PUBLICATION_OPERATOR_TTL_SECONDS,
    PublicationOperatorFailureCode,
    PublicationOperatorOperation,
    PublicationProposalState,
    canonical_json_bytes,
    fail_publication_operator,
    require_publish_article_id,
    require_sha256,
)
from raos.ports.self_hosted_editorial_pilot import ReviewDraftRevisionBinding


DRAFT_REVISION_RESULT_CODE: Final = "ST1704_DRAFT_REVISED"
DRAFT_REVISION_VERIFY_RESULT_CODE: Final = "ST1704_DRAFT_REVISION_VERIFIED"
DRAFT_REVISION_RECOVERY_RESULT_CODE: Final = "ST1704_DRAFT_REVISION_STATE_OBSERVED"
DRAFT_REVISION_OPERATOR_VERSION: Final = "2.1.0"


def _ascii_base64(value: str) -> str:
    if type(value) is not str:
        fail_publication_operator(PublicationOperatorFailureCode.REVIEW_BINDING_INVALID)
    try:
        payload = value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_publication_operator(PublicationOperatorFailureCode.REVIEW_BINDING_INVALID)
    return base64.b64encode(payload).decode("ascii", errors="strict")


@dataclass(frozen=True, slots=True, repr=False)
class DraftRevisionProposal:
    """One complete successor bound to an exact predecessor and Draft ID."""

    binding: ReviewDraftRevisionBinding
    request_token: str
    proposal_id: str
    operation: PublicationOperatorOperation = (
        PublicationOperatorOperation.REVISE_ST1704_DRAFT
    )
    ttl_seconds: int = PUBLICATION_OPERATOR_TTL_SECONDS

    def __post_init__(self) -> None:
        if (
            type(self.binding) is not ReviewDraftRevisionBinding
            or self.operation is not PublicationOperatorOperation.REVISE_ST1704_DRAFT
            or self.ttl_seconds != PUBLICATION_OPERATOR_TTL_SECONDS
        ):
            fail_publication_operator(PublicationOperatorFailureCode.REVIEW_BINDING_INVALID)
        require_publish_article_id(self.binding.successor.article_id)
        require_sha256(self.request_token)
        require_sha256(self.proposal_id)
        if self.proposal_id != hashlib.sha256(self.canonical_bytes()).hexdigest():
            fail_publication_operator(PublicationOperatorFailureCode.REVIEW_BINDING_INVALID)

    @classmethod
    def bind(
        cls, binding: ReviewDraftRevisionBinding, request_token: str
    ) -> "DraftRevisionProposal":
        if type(binding) is not ReviewDraftRevisionBinding:
            fail_publication_operator(PublicationOperatorFailureCode.REVIEW_BINDING_INVALID)
        request_token = require_sha256(request_token)
        payload = cls.payload_for(binding, request_token)
        return cls(
            binding=binding,
            request_token=request_token,
            proposal_id=hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
        )

    @staticmethod
    def payload_for(
        binding: ReviewDraftRevisionBinding, request_token: str
    ) -> dict[str, object]:
        if type(binding) is not ReviewDraftRevisionBinding:
            fail_publication_operator(PublicationOperatorFailureCode.REVIEW_BINDING_INVALID)
        request_token = require_sha256(request_token)
        require_publish_article_id(binding.successor.article_id)
        material = binding.operation_material()
        predecessor = material["predecessor"]
        successor_hashes = material["successor"]
        if type(predecessor) is not dict or type(successor_hashes) is not dict:
            fail_publication_operator(PublicationOperatorFailureCode.REVIEW_BINDING_INVALID)
        successor = binding.successor
        return {
            "article_id": successor.article_id,
            "draft_post_id": binding.draft_id,
            "generation": binding.generation,
            "operation": PublicationOperatorOperation.REVISE_ST1704_DRAFT.value,
            "operation_sha256": binding.operation_sha256,
            "operator_contract_version": PUBLICATION_OPERATOR_CONTRACT_VERSION,
            "predecessor": predecessor,
            "profile_version": PUBLICATION_OPERATOR_PROFILE_VERSION,
            "public_slug": successor.public_slug,
            "request_token": request_token,
            "site_origin": PUBLICATION_OPERATOR_ORIGIN,
            "successor": {
                **successor_hashes,
                "content_base64": _ascii_base64(successor.content),
                "excerpt_base64": _ascii_base64(successor.excerpt),
                "snapshot_base64": _ascii_base64(successor.snapshot.json_string()),
                "title_base64": _ascii_base64(successor.title),
            },
            "ttl_seconds": PUBLICATION_OPERATOR_TTL_SECONDS,
        }

    def payload(self) -> dict[str, object]:
        return self.payload_for(self.binding, self.request_token)

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.payload())


@dataclass(frozen=True, slots=True, repr=False)
class DraftRevisionApplyReceipt:
    proposal_id: str
    operation: PublicationOperatorOperation
    result_code: str
    replayed: bool
    state: PublicationProposalState = PublicationProposalState.APPLIED

    def __post_init__(self) -> None:
        require_sha256(self.proposal_id)
        if (
            self.operation is not PublicationOperatorOperation.REVISE_ST1704_DRAFT
            or self.state is not PublicationProposalState.APPLIED
            or self.result_code != DRAFT_REVISION_RESULT_CODE
            or type(self.replayed) is not bool
        ):
            fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)

    def public_payload(self) -> dict[str, object]:
        return {
            "operation": self.operation.value,
            "proposal_id": self.proposal_id,
            "replayed": self.replayed,
            "result_code": self.result_code,
            "state": self.state.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class DraftRevisionVerifyReceipt:
    proposal_id: str
    operation: PublicationOperatorOperation
    operation_sha256: str
    draft_post_id: int
    result_code: str = DRAFT_REVISION_VERIFY_RESULT_CODE
    state: PublicationProposalState = PublicationProposalState.APPLIED

    def __post_init__(self) -> None:
        require_sha256(self.proposal_id)
        require_sha256(self.operation_sha256)
        if (
            self.operation is not PublicationOperatorOperation.REVISE_ST1704_DRAFT
            or self.state is not PublicationProposalState.APPLIED
            or self.result_code != DRAFT_REVISION_VERIFY_RESULT_CODE
            or type(self.draft_post_id) is not int
            or not 1 <= self.draft_post_id <= (1 << 63) - 1
        ):
            fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)

    def public_payload(self) -> dict[str, object]:
        return {
            "draft_post_id": self.draft_post_id,
            "operation": self.operation.value,
            "operation_sha256": self.operation_sha256,
            "proposal_id": self.proposal_id,
            "result_code": self.result_code,
            "state": self.state.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class DraftRevisionOperatorStatus:
    master_writes_enabled: bool
    publication_writes_enabled: bool
    writes_enabled: bool
    operator_version: str = DRAFT_REVISION_OPERATOR_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.master_writes_enabled) is not bool
            or type(self.publication_writes_enabled) is not bool
            or type(self.writes_enabled) is not bool
            or self.writes_enabled
            is not (self.master_writes_enabled and self.publication_writes_enabled)
            or self.operator_version != DRAFT_REVISION_OPERATOR_VERSION
        ):
            fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)

    def public_payload(self) -> dict[str, object]:
        return {
            "master_writes_enabled": self.master_writes_enabled,
            "operator_version": self.operator_version,
            "publication_writes_enabled": self.publication_writes_enabled,
            "supported_operations": [
                PublicationOperatorOperation.REVISE_ST1704_DRAFT.value
            ],
            "writes_enabled": self.writes_enabled,
        }


class DraftRevisionRecoveryDisposition(StrEnum):
    PREDECESSOR = "PREDECESSOR"
    SUCCESSOR = "SUCCESSOR"


@dataclass(frozen=True, slots=True, repr=False)
class DraftRevisionRecoveryReceipt:
    proposal_id: str
    operation: PublicationOperatorOperation
    operation_sha256: str
    draft_post_id: int
    proposal_state: PublicationProposalState
    disposition: DraftRevisionRecoveryDisposition
    result_code: str = DRAFT_REVISION_RECOVERY_RESULT_CODE

    def __post_init__(self) -> None:
        require_sha256(self.proposal_id)
        require_sha256(self.operation_sha256)
        if (
            self.operation is not PublicationOperatorOperation.REVISE_ST1704_DRAFT
            or self.result_code != DRAFT_REVISION_RECOVERY_RESULT_CODE
            or type(self.proposal_state) is not PublicationProposalState
            or type(self.disposition) is not DraftRevisionRecoveryDisposition
            or type(self.draft_post_id) is not int
            or not 1 <= self.draft_post_id <= (1 << 63) - 1
            or (
                self.disposition is DraftRevisionRecoveryDisposition.SUCCESSOR
                and self.proposal_state
                not in {
                    PublicationProposalState.APPLIED,
                    PublicationProposalState.NEEDS_RECOVERY,
                }
            )
            or (
                self.disposition is DraftRevisionRecoveryDisposition.PREDECESSOR
                and self.proposal_state
                not in {
                    PublicationProposalState.PROPOSED,
                    PublicationProposalState.APPROVED,
                    PublicationProposalState.FAILED,
                    PublicationProposalState.NEEDS_RECOVERY,
                    PublicationProposalState.EXPIRED,
                }
            )
        ):
            fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)

    def public_payload(self) -> dict[str, object]:
        return {
            "disposition": self.disposition.value,
            "draft_post_id": self.draft_post_id,
            "operation": self.operation.value,
            "operation_sha256": self.operation_sha256,
            "proposal_id": self.proposal_id,
            "proposal_state": self.proposal_state.value,
            "result_code": self.result_code,
        }


__all__ = [
    "DRAFT_REVISION_RESULT_CODE",
    "DRAFT_REVISION_OPERATOR_VERSION",
    "DRAFT_REVISION_RECOVERY_RESULT_CODE",
    "DRAFT_REVISION_VERIFY_RESULT_CODE",
    "DraftRevisionApplyReceipt",
    "DraftRevisionOperatorStatus",
    "DraftRevisionRecoveryDisposition",
    "DraftRevisionRecoveryReceipt",
    "DraftRevisionProposal",
    "DraftRevisionVerifyReceipt",
]
