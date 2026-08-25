"""ENV-DEV/CI-only ST-0805 deterministic policy application services."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.ids import ArticleVersionId
from raos.domain.editorial.policy_engine_v2 import (
    PolicyEvaluationEnvelopeV2,
    PolicyEvaluationRecordReceiptV2,
    PolicyEvaluationReportV2,
    evaluate_editorial_policy_v2,
    unavailable_policy_report,
)
from raos.ports.editorial.policy_engine import (
    PolicyEvaluationReportAppender,
    PolicyEvaluationSnapshotReader,
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
class EvaluatePolicyService:
    __slots__ = ("_reader",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        reader: PolicyEvaluationSnapshotReader,
    ) -> None:
        if not _local_environment(environment) or not _implements(
            cast(object, reader), PolicyEvaluationSnapshotReader
        ):
            raise ValueError("INVALID_POLICY_EVALUATION_SERVICE") from None
        self._reader = reader

    def evaluate(
        self, article_version_id: ArticleVersionId
    ) -> PolicyEvaluationReportV2:
        if type(article_version_id) is not ArticleVersionId:
            raise ValueError("INVALID_POLICY_EVALUATION_REQUEST") from None
        try:
            envelope = self._reader.get_snapshot(article_version_id)
        except Exception:
            return unavailable_policy_report()
        if type(envelope) is not PolicyEvaluationEnvelopeV2:
            return unavailable_policy_report()
        try:
            observed = ArticleVersionId(envelope.draft.snapshot.version_id)
        except Exception:
            return evaluate_editorial_policy_v2(envelope)
        if observed != article_version_id:
            return unavailable_policy_report()
        return evaluate_editorial_policy_v2(envelope)


@final
class RecordPolicyReportService:
    __slots__ = ("_appender", "_reader")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        reader: PolicyEvaluationSnapshotReader,
        appender: PolicyEvaluationReportAppender,
    ) -> None:
        if (
            not _local_environment(environment)
            or not _implements(cast(object, reader), PolicyEvaluationSnapshotReader)
            or not _implements(cast(object, appender), PolicyEvaluationReportAppender)
        ):
            raise ValueError("INVALID_POLICY_EVALUATION_SERVICE") from None
        self._reader = reader
        self._appender = appender

    def record(
        self,
        article_version_id: ArticleVersionId,
        report: PolicyEvaluationReportV2,
    ) -> PolicyEvaluationRecordReceiptV2:
        if (
            type(article_version_id) is not ArticleVersionId
            or type(report) is not PolicyEvaluationReportV2
        ):
            raise ValueError("INVALID_POLICY_EVALUATION_REPORT") from None
        report.require_valid()
        try:
            snapshot = self._reader.get_snapshot(article_version_id)
        except Exception:
            raise ValueError("POLICY_EVALUATION_RECORD_UNAVAILABLE") from None
        if type(snapshot) is not PolicyEvaluationEnvelopeV2:
            raise ValueError("POLICY_EVALUATION_RECORD_UNAVAILABLE") from None
        expected = evaluate_editorial_policy_v2(snapshot)
        expected.require_valid()
        if expected.canonical_bytes() != report.canonical_bytes():
            raise ValueError("POLICY_EVALUATION_RECORD_MISMATCH") from None
        try:
            receipt = self._appender.append_report(snapshot, report)
        except Exception:
            raise ValueError("POLICY_EVALUATION_RECORD_UNAVAILABLE") from None
        if (
            type(receipt) is not PolicyEvaluationRecordReceiptV2
            or receipt.report_sha256 != report.report_sha256
        ):
            raise ValueError("POLICY_EVALUATION_RECORD_MISMATCH") from None
        receipt.require_valid()
        return receipt


__all__ = ["EvaluatePolicyService", "RecordPolicyReportService"]
