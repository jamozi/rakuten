"""Narrow ENV-DEV/CI ST-0803 V2 evaluation and recording services."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.comparison_validation_v2 import (
    ComparisonRecordReceipt,
    ComparisonValidationEnvelopeV2,
    ComparisonValidationReportV2,
    unavailable_comparison_report,
    validate_comparison_v2,
)
from raos.domain.editorial.ids import ArticleVersionId
from raos.ports.editorial.comparison_validation import (
    ComparisonValidationReportAppender,
    ComparisonValidationSnapshotReader,
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
class EvaluateComparisonValidationService:
    """Read exactly one envelope and run the pure evaluator."""

    __slots__ = ("_reader",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        reader: ComparisonValidationSnapshotReader,
    ) -> None:
        if not _local_environment(environment) or not _implements(
            cast(object, reader), ComparisonValidationSnapshotReader
        ):
            raise ValueError("INVALID_COMPARISON_VALIDATION_SERVICE") from None
        self._reader = reader

    def evaluate(
        self,
        article_version_id: ArticleVersionId,
    ) -> ComparisonValidationReportV2:
        if type(article_version_id) is not ArticleVersionId:
            raise ValueError("INVALID_COMPARISON_VALIDATION_REQUEST") from None
        try:
            envelope = self._reader.get_snapshot(article_version_id)
        except Exception:
            return unavailable_comparison_report(article_version_id)
        if envelope is None:
            return unavailable_comparison_report(article_version_id)
        try:
            observed = envelope.comparison.article.article_version_id
        except Exception:
            return validate_comparison_v2(envelope)
        if observed != article_version_id:
            return unavailable_comparison_report(article_version_id)
        return validate_comparison_v2(envelope)


@final
class RecordComparisonValidationService:
    """Re-resolve trusted input and append only its exact derived report."""

    __slots__ = ("_appender", "_reader")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        reader: ComparisonValidationSnapshotReader,
        appender: ComparisonValidationReportAppender,
    ) -> None:
        if (
            not _local_environment(environment)
            or not _implements(cast(object, reader), ComparisonValidationSnapshotReader)
            or not _implements(
                cast(object, appender), ComparisonValidationReportAppender
            )
        ):
            raise ValueError("INVALID_COMPARISON_VALIDATION_SERVICE") from None
        self._reader = reader
        self._appender = appender

    def record(
        self,
        article_version_id: ArticleVersionId,
        report: ComparisonValidationReportV2,
    ) -> ComparisonRecordReceipt:
        if (
            type(article_version_id) is not ArticleVersionId
            or type(report) is not ComparisonValidationReportV2
        ):
            raise ValueError("INVALID_COMPARISON_VALIDATION_REPORT") from None
        report.require_valid()
        try:
            envelope = self._reader.get_snapshot(article_version_id)
        except Exception:
            raise ValueError("COMPARISON_VALIDATION_RECORD_UNAVAILABLE") from None
        if type(envelope) is not ComparisonValidationEnvelopeV2:
            raise ValueError("COMPARISON_VALIDATION_RECORD_UNAVAILABLE") from None
        try:
            observed = envelope.comparison.article.article_version_id
        except Exception:
            raise ValueError("COMPARISON_VALIDATION_RECORD_UNAVAILABLE") from None
        if observed != article_version_id:
            raise ValueError("COMPARISON_VALIDATION_RECORD_UNAVAILABLE") from None
        expected = validate_comparison_v2(envelope)
        expected.require_valid()
        if expected.canonical_bytes() != report.canonical_bytes():
            raise ValueError("COMPARISON_VALIDATION_RECORD_MISMATCH") from None
        try:
            receipt = self._appender.append_report(envelope, report)
        except Exception:
            raise ValueError("COMPARISON_VALIDATION_RECORD_UNAVAILABLE") from None
        if (
            type(receipt) is not ComparisonRecordReceipt
            or receipt.report_sha256 != report.report_sha256
        ):
            raise ValueError("COMPARISON_VALIDATION_RECORD_MISMATCH") from None
        receipt.require_valid()
        return receipt


__all__ = [
    "EvaluateComparisonValidationService",
    "RecordComparisonValidationService",
]
