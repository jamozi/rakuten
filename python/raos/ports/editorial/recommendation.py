"""Narrow process-local ports for the ST-0804 recommendation runtime V2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.editorial.ids import ArticleVersionId
from raos.domain.editorial.recommendation_v2 import (
    RecommendationEnvelopeV2,
    RecommendationRecordReceipt,
    RecommendationReportV2,
)


@runtime_checkable
class RecommendationSnapshotReader(Protocol):
    """Resolve one immutable, article-version-bound recommendation envelope."""

    def get_snapshot(
        self,
        article_version_id: ArticleVersionId,
    ) -> RecommendationEnvelopeV2 | None: ...


@runtime_checkable
class RecommendationReportAppender(Protocol):
    """Append only metadata for an exactly re-derived report."""

    def append_report(
        self,
        snapshot: RecommendationEnvelopeV2,
        report: RecommendationReportV2,
    ) -> RecommendationRecordReceipt: ...


__all__ = [
    "RecommendationReportAppender",
    "RecommendationSnapshotReader",
]
