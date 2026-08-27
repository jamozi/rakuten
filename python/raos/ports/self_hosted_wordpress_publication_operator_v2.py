"""Narrow ports for the ST-1704 publication operator v2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.operations.self_hosted_wordpress_draft_revision_operator_v2 import (
    DraftRevisionApplyReceipt,
    DraftRevisionOperatorStatus,
    DraftRevisionProposal,
    DraftRevisionRecoveryReceipt,
    DraftRevisionVerifyReceipt,
)
from raos.domain.operations.self_hosted_wordpress_publication_operator_v2 import (
    CommittedReviewDraftBinding,
    PublicationApplyReceipt,
    PublicationOperatorStatus,
    PublicationProposal,
    PublicationProposalReceipt,
)


@runtime_checkable
class CommittedReviewDraftBindingPort(Protocol):
    """Read one exact COMMITTED review-draft binding without network access."""

    def load(self, article_id: str) -> CommittedReviewDraftBinding: ...


@runtime_checkable
class SelfHostedWordPressPublicationOperatorV2Port(Protocol):
    """Complete fixed-origin network surface for the publication operation."""

    def status(self) -> PublicationOperatorStatus: ...

    def propose(self, proposal: PublicationProposal) -> PublicationProposalReceipt: ...

    def recover_proposal(
        self, proposal: PublicationProposal
    ) -> PublicationProposalReceipt: ...

    def apply(self, proposal_id: str) -> PublicationApplyReceipt: ...

    def propose_revision(
        self, proposal: DraftRevisionProposal
    ) -> PublicationProposalReceipt: ...

    def revision_status(self) -> DraftRevisionOperatorStatus: ...

    def recover_revision_proposal(
        self, proposal: DraftRevisionProposal
    ) -> PublicationProposalReceipt: ...

    def apply_revision(self, proposal_id: str) -> DraftRevisionApplyReceipt: ...

    def recover_revision_state(
        self, proposal_id: str
    ) -> DraftRevisionRecoveryReceipt: ...

    def verify_revision(self, proposal_id: str) -> DraftRevisionVerifyReceipt: ...


__all__ = [
    "CommittedReviewDraftBindingPort",
    "SelfHostedWordPressPublicationOperatorV2Port",
]
