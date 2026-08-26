"""Narrow ports for the fixed self-hosted WordPress operator bridge."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.operations.self_hosted_wordpress_operator import (
    ApplyReceipt,
    OperatorProposal,
    OperatorStatus,
    ProposalReceipt,
    ThemePackage,
    YoastChecksumResult,
)


@runtime_checkable
class SelfHostedWordPressOperatorPort(Protocol):
    """The complete and deliberately closed operator command surface."""

    def status(self) -> OperatorStatus: ...

    def verify_yoast_checksums(self) -> YoastChecksumResult: ...

    def propose(self, proposal: OperatorProposal) -> ProposalReceipt: ...

    def apply_yoast_profile(self, proposal_id: str) -> ApplyReceipt: ...

    def apply_theme_update(
        self, proposal_id: str, theme: ThemePackage
    ) -> ApplyReceipt: ...


__all__ = ["SelfHostedWordPressOperatorPort"]
