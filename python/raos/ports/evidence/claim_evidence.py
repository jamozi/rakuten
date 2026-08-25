"""Read-only and append-only inward ports for ST-0605 local evaluation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.editorial.ids import ArticleVersionId
from raos.domain.evidence.claim_evidence import (
    ClaimEvidenceCoverageReport,
    ClaimEvidenceSnapshot,
    CoverageRecordReceipt,
)


@runtime_checkable
class ClaimEvidenceSnapshotReader(Protocol):
    """Return one complete pre-assembled snapshot without mutating it."""

    def get_snapshot(
        self,
        article_version_id: ArticleVersionId,
    ) -> ClaimEvidenceSnapshot | None: ...


@runtime_checkable
class ClaimEvidenceCoverageAppender(Protocol):
    """Internal append-only result seam; no update/delete/publication surface."""

    def append_report(
        self,
        snapshot: ClaimEvidenceSnapshot,
        report: ClaimEvidenceCoverageReport,
    ) -> CoverageRecordReceipt: ...


__all__ = ["ClaimEvidenceCoverageAppender", "ClaimEvidenceSnapshotReader"]
