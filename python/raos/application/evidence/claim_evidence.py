"""Narrow local ST-0605 evaluation and append-only recording services."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.ids import ArticleVersionId
from raos.domain.evidence.claim_evidence import (
    ClaimEvidenceCoverageReport,
    ClaimEvidenceSnapshot,
    CoverageRecordReceipt,
    evaluate_claim_evidence,
    unavailable_claim_evidence_report,
)
from raos.ports.evidence.claim_evidence import (
    ClaimEvidenceCoverageAppender,
    ClaimEvidenceSnapshotReader,
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
class EvaluateClaimEvidenceCoverageService:
    """Read exactly one snapshot and run the pure evaluator."""

    __slots__ = ("_reader",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        reader: ClaimEvidenceSnapshotReader,
    ) -> None:
        if not _local_environment(environment) or not _implements(
            cast(object, reader), ClaimEvidenceSnapshotReader
        ):
            raise ValueError("INVALID_CLAIM_EVIDENCE_SERVICE") from None
        self._reader = reader

    def evaluate(
        self,
        article_version_id: ArticleVersionId,
    ) -> ClaimEvidenceCoverageReport:
        if type(article_version_id) is not ArticleVersionId:
            raise ValueError("INVALID_CLAIM_EVIDENCE_REQUEST") from None
        try:
            snapshot = self._reader.get_snapshot(article_version_id)
        except Exception:
            return unavailable_claim_evidence_report(article_version_id)
        if snapshot is None:
            return unavailable_claim_evidence_report(article_version_id)
        try:
            observed_id = snapshot.article.article_version_id
        except Exception:
            return evaluate_claim_evidence(snapshot)
        if observed_id != article_version_id:
            return unavailable_claim_evidence_report(article_version_id)
        return evaluate_claim_evidence(snapshot)


@final
class RecordClaimEvidenceCoverageService:
    """Resolve trusted input and append only its exact derived report."""

    __slots__ = ("_appender", "_reader")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        reader: ClaimEvidenceSnapshotReader,
        appender: ClaimEvidenceCoverageAppender,
    ) -> None:
        if (
            not _local_environment(environment)
            or not _implements(cast(object, reader), ClaimEvidenceSnapshotReader)
            or not _implements(cast(object, appender), ClaimEvidenceCoverageAppender)
        ):
            raise ValueError("INVALID_CLAIM_EVIDENCE_SERVICE") from None
        self._reader = reader
        self._appender = appender

    def record(
        self,
        article_version_id: ArticleVersionId,
        report: ClaimEvidenceCoverageReport,
    ) -> CoverageRecordReceipt:
        if (
            type(article_version_id) is not ArticleVersionId
            or type(report) is not ClaimEvidenceCoverageReport
        ):
            raise ValueError("INVALID_CLAIM_EVIDENCE_REPORT") from None
        report.require_valid()
        try:
            snapshot = self._reader.get_snapshot(article_version_id)
        except Exception:
            raise ValueError("CLAIM_EVIDENCE_RECORD_UNAVAILABLE") from None
        if type(snapshot) is not ClaimEvidenceSnapshot:
            raise ValueError("CLAIM_EVIDENCE_RECORD_UNAVAILABLE") from None
        try:
            observed_article_version_id = snapshot.article.article_version_id
        except Exception:
            raise ValueError("CLAIM_EVIDENCE_RECORD_UNAVAILABLE") from None
        if observed_article_version_id != article_version_id:
            raise ValueError("CLAIM_EVIDENCE_RECORD_UNAVAILABLE") from None
        expected = evaluate_claim_evidence(snapshot)
        expected.require_valid()
        if expected.canonical_bytes() != report.canonical_bytes():
            raise ValueError("CLAIM_EVIDENCE_RECORD_MISMATCH") from None
        try:
            receipt = self._appender.append_report(snapshot, report)
        except Exception:
            raise ValueError("CLAIM_EVIDENCE_RECORD_UNAVAILABLE") from None
        if (
            type(receipt) is not CoverageRecordReceipt
            or receipt.report_sha256 != report.report_sha256
        ):
            raise ValueError("CLAIM_EVIDENCE_RECORD_MISMATCH") from None
        receipt.require_valid()
        return receipt


__all__ = [
    "EvaluateClaimEvidenceCoverageService",
    "RecordClaimEvidenceCoverageService",
]
