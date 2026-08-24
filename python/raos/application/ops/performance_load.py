"""Application boundary for recorded/synthetic ST-1604 evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from raos.domain.ops.performance_load import (
    PerformanceLoadFailure,
    PerformanceLoadFailureCode,
    PerformanceLoadReport,
    PerformanceLoadRequest,
    evaluate_performance_load,
    fail_performance_load,
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
        report = evaluate_performance_load(request)
        try:
            receipt = self.journal.append(report)
        except Exception as error:
            if isinstance(error, PerformanceLoadFailure):
                raise
            fail_performance_load(PerformanceLoadFailureCode.STORAGE_FAILED)
        if (
            type(receipt) is not PerformanceLoadReceipt
            or receipt.run_id != report.run_id
            or receipt.report_sha256 != report.report_sha256
            or type(receipt.sequence) is not int
            or receipt.sequence < 1
            or type(receipt.previous_record_sha256) is not str
            or len(receipt.previous_record_sha256) != 64
            or type(receipt.record_sha256) is not str
            or len(receipt.record_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in (
                    receipt.report_sha256
                    + receipt.previous_record_sha256
                    + receipt.record_sha256
                )
            )
            or type(receipt.disposition) is not PerformanceLoadWriteDisposition
        ):
            fail_performance_load(PerformanceLoadFailureCode.JOURNAL_MISMATCH)
        return report


__all__ = ["PerformanceLoadEvaluationService"]
