"""Narrow process-local ports for the ST-0805 policy runtime V2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.editorial.ids import ArticleVersionId
from raos.domain.editorial.policy_engine_v2 import (
    PolicyEvaluationEnvelopeV2,
    PolicyEvaluationRecordReceiptV2,
    PolicyEvaluationReportV2,
)


@runtime_checkable
class PolicyEvaluationSnapshotReader(Protocol):
    def get_snapshot(
        self,
        article_version_id: ArticleVersionId,
    ) -> PolicyEvaluationEnvelopeV2 | None: ...


@runtime_checkable
class PolicyEvaluationReportAppender(Protocol):
    def append_report(
        self,
        snapshot: PolicyEvaluationEnvelopeV2,
        report: PolicyEvaluationReportV2,
    ) -> PolicyEvaluationRecordReceiptV2: ...


__all__ = [
    "PolicyEvaluationReportAppender",
    "PolicyEvaluationSnapshotReader",
]
