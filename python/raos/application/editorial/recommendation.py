"""ENV-DEV/CI-only ST-0804 deterministic evaluation and recording services."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.ids import ArticleVersionId
from raos.domain.editorial.recommendation_v2 import (
    RecommendationEnvelopeV2,
    RecommendationRecordReceipt,
    RecommendationReportV2,
    evaluate_recommendations_v2,
    unavailable_recommendation_report,
)
from raos.ports.editorial.recommendation import (
    RecommendationReportAppender,
    RecommendationSnapshotReader,
)


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except Exception:
        return False


@final
class EvaluateRecommendationService:
    """Read exactly one bound envelope and run the pure evaluator."""

    __slots__ = ("_reader",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        reader: RecommendationSnapshotReader,
    ) -> None:
        if not _local_environment(environment) or not _implements(
            cast(object, reader), RecommendationSnapshotReader
        ):
            raise ValueError("INVALID_RECOMMENDATION_SERVICE") from None
        self._reader = reader

    def evaluate(self, article_version_id: ArticleVersionId) -> RecommendationReportV2:
        if type(article_version_id) is not ArticleVersionId:
            raise ValueError("INVALID_RECOMMENDATION_REQUEST") from None
        try:
            envelope = self._reader.get_snapshot(article_version_id)
        except Exception:
            return unavailable_recommendation_report(article_version_id)
        if envelope is None:
            return unavailable_recommendation_report(article_version_id)
        try:
            observed = envelope.comparison.comparison.article.article_version_id
        except Exception:
            return evaluate_recommendations_v2(envelope)
        if observed != article_version_id:
            return unavailable_recommendation_report(article_version_id)
        return evaluate_recommendations_v2(envelope)


@final
class RecordRecommendationService:
    """Re-resolve trusted input and append only its exact derived report."""

    __slots__ = ("_appender", "_reader")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        reader: RecommendationSnapshotReader,
        appender: RecommendationReportAppender,
    ) -> None:
        if (
            not _local_environment(environment)
            or not _implements(cast(object, reader), RecommendationSnapshotReader)
            or not _implements(cast(object, appender), RecommendationReportAppender)
        ):
            raise ValueError("INVALID_RECOMMENDATION_SERVICE") from None
        self._reader = reader
        self._appender = appender

    def record(
        self,
        article_version_id: ArticleVersionId,
        report: RecommendationReportV2,
    ) -> RecommendationRecordReceipt:
        if (
            type(article_version_id) is not ArticleVersionId
            or type(report) is not RecommendationReportV2
        ):
            raise ValueError("INVALID_RECOMMENDATION_REPORT") from None
        report.require_valid()
        try:
            envelope = self._reader.get_snapshot(article_version_id)
        except Exception:
            raise ValueError("RECOMMENDATION_RECORD_UNAVAILABLE") from None
        if type(envelope) is not RecommendationEnvelopeV2:
            raise ValueError("RECOMMENDATION_RECORD_UNAVAILABLE") from None
        try:
            observed = envelope.comparison.comparison.article.article_version_id
        except Exception:
            raise ValueError("RECOMMENDATION_RECORD_UNAVAILABLE") from None
        if observed != article_version_id:
            raise ValueError("RECOMMENDATION_RECORD_UNAVAILABLE") from None
        expected = evaluate_recommendations_v2(envelope)
        expected.require_valid()
        if expected.canonical_bytes() != report.canonical_bytes():
            raise ValueError("RECOMMENDATION_RECORD_MISMATCH") from None
        try:
            receipt = self._appender.append_report(envelope, report)
        except Exception:
            raise ValueError("RECOMMENDATION_RECORD_UNAVAILABLE") from None
        if (
            type(receipt) is not RecommendationRecordReceipt
            or receipt.report_sha256 != report.report_sha256
        ):
            raise ValueError("RECOMMENDATION_RECORD_MISMATCH") from None
        receipt.require_valid()
        return receipt


__all__ = [
    "EvaluateRecommendationService",
    "RecordRecommendationService",
]
