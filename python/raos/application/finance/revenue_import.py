"""Fail-closed application boundary for the ST-1301 synthetic dry run."""

from __future__ import annotations

from typing import final

from raos.domain.finance.revenue_import import (
    RevenueImportFailureCode,
    SyntheticRevenueDryRun,
    SyntheticRevenueParseCommand,
    SyntheticRevenueProfile,
    SyntheticRevenueSourceReference,
    fail_revenue_import,
)
from raos.domain.ops.object_intake import (
    CsvEncoding,
    DuplicateStatus,
    InspectionStatus,
    IntakeOutcome,
    IntakePrivacyClass,
    MalwareStatus,
    ObjectIntakeKind,
    ObjectIntakeResult,
    QuarantineDisposition,
    QuarantineStatus,
)
from raos.ports.revenue_import import RecordedRevenueParser


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


@final
class RevenueImportService:
    """Authorize an already-quarantined synthetic CSV before one parser call."""

    __slots__ = ("_parser",)

    def __init__(self, *, parser: RecordedRevenueParser) -> None:
        if not _implements(parser, RecordedRevenueParser):
            fail_revenue_import()
        self._parser = parser

    @staticmethod
    def _command(intake: object) -> SyntheticRevenueParseCommand:
        if type(intake) is not ObjectIntakeResult:
            fail_revenue_import()
        descriptor = intake.descriptor
        report = intake.inspection
        if intake.duplicate.status is DuplicateStatus.EXACT_DUPLICATE:
            fail_revenue_import(RevenueImportFailureCode.SOURCE_DUPLICATE_REJECTED)
        if (
            descriptor.kind is not ObjectIntakeKind.REVENUE_REPORT
            or descriptor.privacy_class is not IntakePrivacyClass.SYNTHETIC
            or descriptor.media_type.value != "text/csv"
            or not descriptor.leaf_name.value.endswith(".csv")
            or intake.outcome is not IntakeOutcome.CLEAN_QUARANTINED
            or intake.quarantine.status is not QuarantineStatus.DISPOSITION_RECORDED
            or intake.quarantine.disposition
            is not QuarantineDisposition.CLEAN_QUARANTINED
            or intake.quarantine.received_bytes != descriptor.declared_size
            or intake.quarantine.sealed_sha256 != descriptor.declared_sha256
            or intake.malware.status is not MalwareStatus.CLEAN
            or intake.duplicate.status is not DuplicateStatus.NEW
            or report.magic.status is not InspectionStatus.SAFE
            or report.privacy.status is not InspectionStatus.SAFE
            or report.privacy.privacy_class is not IntakePrivacyClass.SYNTHETIC
            or report.csv.status is not InspectionStatus.SAFE
            or report.csv.encoding is not CsvEncoding.UTF_8
            or report.csv.formula_prefix_detected
        ):
            fail_revenue_import()
        return SyntheticRevenueParseCommand(
            intake_id=descriptor.intake_id,
            site_id=descriptor.site_id,
            source_sha256=descriptor.declared_sha256,
            source_size=descriptor.declared_size,
            profile=SyntheticRevenueProfile.RAOS_ST1301_SYNTHETIC_V1,
            expected_row_count=report.csv.row_count,
            expected_column_count=report.csv.column_count,
            expected_max_cell_bytes=report.csv.max_cell_bytes,
        )

    @staticmethod
    def _validate_result(
        result: object,
        command: SyntheticRevenueParseCommand,
    ) -> SyntheticRevenueDryRun:
        expected_source = SyntheticRevenueSourceReference(
            intake_id=command.intake_id,
            site_id=command.site_id,
            source_sha256=command.source_sha256,
            source_size=command.source_size,
            profile=command.profile,
            command_fingerprint=command.canonical_fingerprint,
            csv_row_count=command.expected_row_count,
            csv_column_count=command.expected_column_count,
            csv_max_cell_bytes=command.expected_max_cell_bytes,
            is_dry_run=True,
        )
        if (
            type(result) is not SyntheticRevenueDryRun
            or result.source != expected_source
        ):
            fail_revenue_import(RevenueImportFailureCode.PARSER_RESULT_INVALID)
        return result

    def dry_run(self, intake: ObjectIntakeResult) -> SyntheticRevenueDryRun:
        """Perform one local synthetic parse; no mutation or external action exists."""

        command = self._command(intake)
        result: object = None
        failed = False
        try:
            result = self._parser.parse(command)
        except Exception:
            failed = True
        if failed:
            fail_revenue_import(RevenueImportFailureCode.PARSER_UNAVAILABLE)
        return self._validate_result(result, command)


__all__ = ["RevenueImportService"]
