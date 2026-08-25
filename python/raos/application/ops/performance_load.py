"""Application boundary for recorded/synthetic ST-1604 evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from raos.domain.ops.performance_load import (
    PerformanceLoadFailure,
    PerformanceLoadFailureCode,
    PerformanceLoadReport,
    PerformanceLoadRequest,
    evaluate_performance_load,
    fail_performance_load,
    performance_load_record_sha256,
    performance_load_report_sha256,
)
from raos.ports.performance_load import (
    PerformanceLoadJournalPort,
    PerformanceLoadReceipt,
    PerformanceLoadWriteDisposition,
)


@dataclass(frozen=True, slots=True)
class PerformanceLoadEvaluationService:
    journal: PerformanceLoadJournalPort

    @property
    def action_count(self) -> int:
        return 0

    def evaluate_and_record(
        self, request: PerformanceLoadRequest
    ) -> PerformanceLoadReport:
        if type(request) is not PerformanceLoadRequest:
            fail_performance_load(PerformanceLoadFailureCode.INVALID_ARGUMENT)
        request_bytes = request.canonical_bytes()
        request_sha256 = request.request_sha256
        report = evaluate_performance_load(request)
        report_bytes = report.canonical_bytes()
        report_sha256 = performance_load_report_sha256(report)
        self._require_zero_action_count()
        receipt: PerformanceLoadReceipt | None = None
        append_error: Exception | None = None
        try:
            receipt = self.journal.append(report)
        except Exception as error:
            append_error = error
        self._require_zero_action_count()
        if append_error is not None:
            if isinstance(append_error, PerformanceLoadFailure):
                raise append_error from None
            fail_performance_load(PerformanceLoadFailureCode.STORAGE_FAILED)
        if type(receipt) is not PerformanceLoadReceipt:
            fail_performance_load(PerformanceLoadFailureCode.JOURNAL_MISMATCH)
        try:
            report_unchanged = (
                request.canonical_bytes() == request_bytes
                and request.request_sha256 == request_sha256
                and report.canonical_bytes() == report_bytes
                and performance_load_report_sha256(report) == report_sha256
                and report.request_sha256 == request_sha256
            )
            expected_record_sha256 = performance_load_record_sha256(
                sequence=receipt.sequence,
                run_id=report.run_id,
                report_sha256=report_sha256,
                request_sha256=report.request_sha256,
                observed_at=report.observed_at,
                report_status=report.report_status,
                evidence_source=report.evidence_source,
                previous_record_sha256=receipt.previous_record_sha256,
            )
        except PerformanceLoadFailure:
            fail_performance_load(PerformanceLoadFailureCode.JOURNAL_MISMATCH)
        if (
            not report_unchanged
            or type(receipt.run_id) is not UUID
            or receipt.run_id != report.run_id
            or receipt.report_sha256 != report_sha256
            or type(receipt.sequence) is not int
            or receipt.sequence < 1
            or receipt.record_sha256 != expected_record_sha256
            or type(receipt.disposition) is not PerformanceLoadWriteDisposition
        ):
            fail_performance_load(PerformanceLoadFailureCode.JOURNAL_MISMATCH)
        return report

    def _require_zero_action_count(self) -> None:
        try:
            value = self.journal.action_count
        except Exception:
            fail_performance_load(PerformanceLoadFailureCode.JOURNAL_MISMATCH)
        if type(value) is not int or value != 0:
            fail_performance_load(PerformanceLoadFailureCode.JOURNAL_MISMATCH)


__all__ = ["PerformanceLoadEvaluationService"]
