"""Synthetic builders for the isolated ST-1301 suite."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_revenue_import import (  # noqa: E402
    RecordedRevenueFixture,
    RecordedRevenueParserAdapter,
)
from raos.application.finance.revenue_import import RevenueImportService  # noqa: E402
from raos.domain.finance.revenue_import import (  # noqa: E402
    SyntheticRevenueParseCommand,
    SyntheticRevenueProfile,
)
from raos.domain.ops.object_intake import (  # noqa: E402
    ArchiveInspectionRecord,
    CsvEncoding,
    CsvInspectionRecord,
    DuplicateInspectionRecord,
    DuplicateStatus,
    InspectionStatus,
    IntakeDescriptor,
    IntakeOutcome,
    IntakePrivacyClass,
    MagicInspectionRecord,
    MalwareInspectionRecord,
    MalwareStatus,
    MediaType,
    ObjectInspectionReport,
    ObjectIntakeKind,
    ObjectIntakeResult,
    PrivacyInspectionRecord,
    QuarantineDisposition,
    QuarantineRecord,
    QuarantineStatus,
    SafeLeafName,
    Sha256Digest,
)


SITE_ID = UUID("018f3e90-7b00-7000-8000-000000001301")
INTAKE_ID = UUID("018f3e90-7b00-7000-8000-000000001302")
QUARANTINE_ID = UUID("018f3e90-7b00-7000-8000-000000001303")
EXISTING_INTAKE_ID = UUID("018f3e90-7b00-7000-8000-000000001304")
HEADER = (
    b"synthetic_fixture,provider_code,provider_event_key,event_type,event_at,"
    b"currency,generated_commission_jpy,confirmed_commission_jpy"
)
ROW_GENERATED = (
    b"RAOS_ST1301_SYNTHETIC_V1,RAKUTEN_AFFILIATE,synthetic-event-0001,"
    b"GENERATED,2026-08-01T00:00:00Z,JPY,100,"
)
ROW_CONFIRMED = (
    b"RAOS_ST1301_SYNTHETIC_V1,RAKUTEN_AFFILIATE,synthetic-event-0002,"
    b"CONFIRMED,2026-08-02T00:00:00Z,JPY,100,80"
)
ROW_CONFLICT = (
    b"RAOS_ST1301_SYNTHETIC_V1,RAKUTEN_AFFILIATE,synthetic-event-0002,"
    b"ADJUSTED,2026-08-03T00:00:00Z,JPY,10,10"
)
SYNTHETIC_CSV = b"\n".join(
    (HEADER, ROW_GENERATED, ROW_CONFIRMED, ROW_GENERATED, ROW_CONFLICT, b"")
)


def csv_shape(payload: bytes) -> tuple[int, int, int]:
    lines = payload[:-1].split(b"\n")
    cells = tuple(cell for line in lines for cell in line.split(b","))
    return len(lines), 8, max(len(cell) for cell in cells)


def intake_result(
    payload: bytes = SYNTHETIC_CSV,
    *,
    duplicate_status: DuplicateStatus = DuplicateStatus.NEW,
) -> ObjectIntakeResult:
    digest = Sha256Digest(hashlib.sha256(payload).hexdigest())
    row_count, column_count, max_cell_bytes = csv_shape(payload)
    media_type = MediaType("text/csv")
    descriptor = IntakeDescriptor(
        intake_id=INTAKE_ID,
        site_id=SITE_ID,
        kind=ObjectIntakeKind.REVENUE_REPORT,
        leaf_name=SafeLeafName("st1301-synthetic.csv"),
        media_type=media_type,
        declared_size=len(payload),
        declared_sha256=digest,
        privacy_class=IntakePrivacyClass.SYNTHETIC,
    )
    return ObjectIntakeResult(
        descriptor=descriptor,
        quarantine=QuarantineRecord(
            intake_id=INTAKE_ID,
            quarantine_id=QUARANTINE_ID,
            status=QuarantineStatus.DISPOSITION_RECORDED,
            received_bytes=len(payload),
            chunk_count=1,
            sealed_sha256=digest,
            disposition=QuarantineDisposition.CLEAN_QUARANTINED,
        ),
        inspection=ObjectInspectionReport(
            magic=MagicInspectionRecord(
                status=InspectionStatus.SAFE,
                declared_media_type=media_type,
                detected_media_type=media_type,
                extension_consistent=True,
            ),
            archive=ArchiveInspectionRecord(
                status=InspectionStatus.NOT_APPLICABLE,
                entry_count=0,
                uncompressed_bytes=0,
            ),
            csv=CsvInspectionRecord(
                status=InspectionStatus.SAFE,
                encoding=CsvEncoding.UTF_8,
                row_count=row_count,
                column_count=column_count,
                max_cell_bytes=max_cell_bytes,
                formula_prefix_detected=False,
            ),
            privacy=PrivacyInspectionRecord(
                status=InspectionStatus.SAFE,
                privacy_class=IntakePrivacyClass.SYNTHETIC,
            ),
        ),
        malware=MalwareInspectionRecord(status=MalwareStatus.CLEAN),
        duplicate=DuplicateInspectionRecord(
            status=duplicate_status,
            existing_intake_id=(
                EXISTING_INTAKE_ID
                if duplicate_status is DuplicateStatus.EXACT_DUPLICATE
                else None
            ),
        ),
        outcome=IntakeOutcome.CLEAN_QUARANTINED,
    )


def parse_command(intake: ObjectIntakeResult) -> SyntheticRevenueParseCommand:
    return SyntheticRevenueParseCommand(
        intake_id=intake.descriptor.intake_id,
        site_id=intake.descriptor.site_id,
        source_sha256=intake.descriptor.declared_sha256,
        source_size=intake.descriptor.declared_size,
        profile=SyntheticRevenueProfile.RAOS_ST1301_SYNTHETIC_V1,
        expected_row_count=intake.inspection.csv.row_count,
        expected_column_count=intake.inspection.csv.column_count,
        expected_max_cell_bytes=intake.inspection.csv.max_cell_bytes,
    )


def service_for(
    intake: ObjectIntakeResult,
    payload: bytes = SYNTHETIC_CSV,
) -> RevenueImportService:
    adapter = RecordedRevenueParserAdapter(
        RecordedRevenueFixture(command=parse_command(intake), payload=payload)
    )
    return RevenueImportService(parser=adapter)
