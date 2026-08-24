"""Read-only and append-only inward ports for ST-0803 V2 local validation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.editorial.comparison_validation_v2 import (
    ComparisonRecordReceipt,
    ComparisonValidationEnvelopeV2,
    ComparisonValidationReportV2,
)
from raos.domain.editorial.ids import ArticleVersionId


@runtime_checkable
class ComparisonValidationSnapshotReader(Protocol):
    """Return one immutable, pre-assembled comparison envelope."""

    def get_snapshot(
        self,
        article_version_id: ArticleVersionId,
    ) -> ComparisonValidationEnvelopeV2 | None: ...


@runtime_checkable
class ComparisonValidationReportAppender(Protocol):
    """Append metadata-only local evidence; no update/publication surface."""

    def append_report(
        self,
        snapshot: ComparisonValidationEnvelopeV2,
        report: ComparisonValidationReportV2,
    ) -> ComparisonRecordReceipt: ...


__all__ = [
    "ComparisonValidationReportAppender",
    "ComparisonValidationSnapshotReader",
]
