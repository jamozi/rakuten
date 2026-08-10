"""Hostile trust-boundary tests for the ST-1301 synthetic revenue seam."""

from __future__ import annotations

import ast
from dataclasses import replace
from uuid import UUID

import pytest

from conftest import (
    HEADER,
    REPOSITORY_ROOT,
    ROW_GENERATED,
    SYNTHETIC_CSV,
    intake_result,
    parse_command,
    service_for,
)
from raos.adapters.recorded_revenue_import import (
    RecordedRevenueFixture,
    RecordedRevenueParserAdapter,
)
from raos.application.finance.revenue_import import RevenueImportService
from raos.domain.finance.revenue_import import (
    RevenueImportFailure,
    RevenueImportFailureCode,
    RevenueRowCode,
    RevenueRowParseStatus,
)
from raos.domain.ops.object_intake import (
    CsvInspectionRecord,
    DuplicateStatus,
    InspectionStatus,
    IntakeDescriptor,
    IntakePrivacyClass,
    ObjectIntakeKind,
    ObjectInspectionReport,
    SafeLeafName,
    Sha256Digest,
)


def _payload(*rows: bytes, header: bytes = HEADER) -> bytes:
    return b"\n".join((header, *rows, b""))


@pytest.mark.parametrize(
    "payload",
    [
        SYNTHETIC_CSV[:-1],
        b"\xef\xbb\xbf" + SYNTHETIC_CSV,
        SYNTHETIC_CSV.replace(b"\n", b"\r\n"),
        SYNTHETIC_CSV.replace(b"JPY", b"JP\x00", 1),
        SYNTHETIC_CSV.replace(b"100,", b"=100,", 1),
        SYNTHETIC_CSV.replace(b"100,", b"+100,", 1),
        SYNTHETIC_CSV.replace(b"100,", b"-100,", 1),
        SYNTHETIC_CSV.replace(b"100,", b"@100,", 1),
        SYNTHETIC_CSV.replace(b"\n", b"\n\n", 1),
        _payload(ROW_GENERATED, header=HEADER + b",extra"),
    ],
)
def test_document_level_drift_fails_closed_without_partial_result(
    payload: bytes,
) -> None:
    intake = intake_result(payload)
    with pytest.raises(RevenueImportFailure) as caught:
        service_for(intake, payload).dry_run(intake)
    assert caught.value.code is RevenueImportFailureCode.PARSER_UNAVAILABLE


@pytest.mark.parametrize(
    "row",
    [
        ROW_GENERATED.replace(b"RAOS_ST1301_SYNTHETIC_V1", b"OTHER"),
        ROW_GENERATED.replace(b"RAKUTEN_AFFILIATE", b"OTHER"),
        ROW_GENERATED.replace(b"synthetic-event-0001", b"event-0001"),
        ROW_GENERATED.replace(b"GENERATED", b"UNKNOWN"),
        ROW_GENERATED.replace(b"2026-08-01T00:00:00Z", b"2026-08-01T00:00:00+00:00"),
        ROW_GENERATED.replace(b"2026-08-01T00:00:00Z", b"2026-02-30T00:00:00Z"),
        ROW_GENERATED.replace(b"JPY", b"USD"),
        ROW_GENERATED.replace(b",100,", b",01,"),
        ROW_GENERATED.replace(b",100,", b",9223372036854775808,"),
        ROW_GENERATED + b",extra",
        ROW_GENERATED.replace(b"100", b'"100"'),
    ],
)
def test_invalid_synthetic_row_is_redacted_rejected(row: bytes) -> None:
    payload = _payload(row)
    intake = intake_result(payload)
    result = service_for(intake, payload).dry_run(intake)
    assert result.row_count == 1
    assert result.accepted_count == 0
    assert result.rejected_count == 1
    assert result.previews[0].status is RevenueRowParseStatus.REJECTED
    assert result.previews[0].code is RevenueRowCode.INVALID_ROW
    assert row.decode("utf-8") not in repr(result)


@pytest.mark.parametrize(
    ("kind", "privacy", "leaf"),
    [
        (ObjectIntakeKind.SOURCE_DOCUMENT, IntakePrivacyClass.SYNTHETIC, "fixture.csv"),
        (
            ObjectIntakeKind.REVENUE_REPORT,
            IntakePrivacyClass.APPROVED_ANONYMIZED,
            "fixture.csv",
        ),
        (ObjectIntakeKind.REVENUE_REPORT, IntakePrivacyClass.SYNTHETIC, "fixture.txt"),
    ],
)
def test_ineligible_intake_is_rejected_before_parser_call(
    kind: ObjectIntakeKind,
    privacy: IntakePrivacyClass,
    leaf: str,
) -> None:
    original = intake_result()
    descriptor = IntakeDescriptor(
        intake_id=original.descriptor.intake_id,
        site_id=original.descriptor.site_id,
        kind=kind,
        leaf_name=SafeLeafName(leaf),
        media_type=original.descriptor.media_type,
        declared_size=original.descriptor.declared_size,
        declared_sha256=original.descriptor.declared_sha256,
        privacy_class=privacy,
    )
    privacy_record = replace(original.inspection.privacy, privacy_class=privacy)
    drifted = replace(
        original,
        descriptor=descriptor,
        inspection=replace(original.inspection, privacy=privacy_record),
    )
    parser = _NoCallParser()
    service = RevenueImportService(parser=parser)  # type: ignore[arg-type]
    with pytest.raises(RevenueImportFailure):
        service.dry_run(drifted)
    assert parser.calls == 0


class _NoCallParser:
    def __init__(self) -> None:
        self.calls = 0

    def parse(self, command: object) -> object:
        del command
        self.calls += 1
        raise AssertionError("unexpected parser call")


def test_csv_not_applicable_is_denied_before_parser() -> None:
    original = intake_result()
    csv = CsvInspectionRecord(
        status=InspectionStatus.NOT_APPLICABLE,
        encoding=None,
        row_count=0,
        column_count=0,
        max_cell_bytes=0,
        formula_prefix_detected=False,
    )
    inspection = ObjectInspectionReport(
        magic=original.inspection.magic,
        archive=original.inspection.archive,
        csv=csv,
        privacy=original.inspection.privacy,
    )
    drifted = replace(original, inspection=inspection)
    parser = _NoCallParser()
    with pytest.raises(RevenueImportFailure):
        RevenueImportService(parser=parser).dry_run(drifted)  # type: ignore[arg-type]
    assert parser.calls == 0


def test_exact_duplicate_failure_never_echoes_rejected_material() -> None:
    canary = "SECRET-CANARY-ST1301"
    duplicate = intake_result(duplicate_status=DuplicateStatus.EXACT_DUPLICATE)
    with pytest.raises(RevenueImportFailure) as caught:
        service_for(intake_result()).dry_run(duplicate)
    assert caught.value.code is RevenueImportFailureCode.SOURCE_DUPLICATE_REJECTED
    assert canary not in str(caught.value)
    assert canary not in repr(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_command_mismatch_is_one_shot_and_sanitized() -> None:
    command = parse_command(intake_result())
    adapter = RecordedRevenueParserAdapter(
        RecordedRevenueFixture(command=command, payload=SYNTHETIC_CSV)
    )
    mismatch = replace(command, source_size=command.source_size + 1)
    with pytest.raises(RevenueImportFailure) as caught:
        adapter.parse(mismatch)
    assert caught.value.code is RevenueImportFailureCode.PARSER_REJECTED
    with pytest.raises(RevenueImportFailure):
        adapter.parse(command)


def test_payload_hash_drift_is_sanitized_without_partial_fallback() -> None:
    intake = intake_result()
    command = parse_command(intake)
    drifted = SYNTHETIC_CSV.replace(b"100,80", b"100,81")
    adapter = RecordedRevenueParserAdapter(
        RecordedRevenueFixture(command=command, payload=drifted)
    )
    with pytest.raises(RevenueImportFailure) as caught:
        RevenueImportService(parser=adapter).dry_run(intake)
    assert caught.value.code is RevenueImportFailureCode.PARSER_UNAVAILABLE
    assert "100,81" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


class _ScriptedParser:
    def __init__(self, result: object = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def parse(self, command: object) -> object:
        del command
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def test_malformed_parser_result_is_sanitized() -> None:
    parser = _ScriptedParser(result=object())
    with pytest.raises(RevenueImportFailure) as caught:
        RevenueImportService(parser=parser).dry_run(intake_result())  # type: ignore[arg-type]
    assert caught.value.code is RevenueImportFailureCode.PARSER_RESULT_INVALID
    assert parser.calls == 1


def test_parser_exception_does_not_echo_or_chain_sensitive_material() -> None:
    canary = "SECRET-CANARY-ST1301-PARSER"
    parser = _ScriptedParser(error=RuntimeError(canary))
    with pytest.raises(RevenueImportFailure) as caught:
        RevenueImportService(parser=parser).dry_run(intake_result())  # type: ignore[arg-type]
    assert caught.value.code is RevenueImportFailureCode.PARSER_UNAVAILABLE
    assert canary not in str(caught.value)
    assert canary not in repr(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("intake_id", UUID("018f3e90-7b00-7000-8000-000000009901")),
        ("site_id", UUID("018f3e90-7b00-7000-8000-000000009902")),
        ("source_sha256", Sha256Digest("9" * 64)),
        ("source_size", len(SYNTHETIC_CSV) + 1),
    ],
)
def test_parser_source_binding_drift_is_rejected(field: str, value: object) -> None:
    intake = intake_result()
    valid = service_for(intake).dry_run(intake)
    drifted_source = replace(valid.source, **{field: value})  # type: ignore[arg-type]
    drifted = replace(valid, source=drifted_source)
    parser = _ScriptedParser(result=drifted)
    with pytest.raises(RevenueImportFailure) as caught:
        RevenueImportService(parser=parser).dry_run(intake)  # type: ignore[arg-type]
    assert caught.value.code is RevenueImportFailureCode.PARSER_RESULT_INVALID
    assert parser.calls == 1


def test_runtime_modules_have_no_external_or_persistence_surface() -> None:
    paths = (
        "python/raos/domain/finance/revenue_import.py",
        "python/raos/ports/revenue_import.py",
        "python/raos/application/finance/revenue_import.py",
        "python/raos/adapters/recorded_revenue_import.py",
    )
    forbidden_import_roots = {
        "boto3",
        "botocore",
        "fastapi",
        "httpx",
        "os",
        "pathlib",
        "requests",
        "socket",
        "sqlalchemy",
        "subprocess",
        "urllib",
    }
    forbidden_names = {
        "open",
        "Path",
        "getenv",
        "environ",
        "connect",
        "request",
        "execute",
        "commit",
        "save",
        "delete",
        "publish",
        "confirm",
        "retry",
        "sleep",
    }
    for relative in paths:
        tree = ast.parse((REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not (
                    {alias.name.split(".")[0] for alias in node.names}
                    & forbidden_import_roots
                )
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_import_roots
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in forbidden_names
                elif isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in forbidden_names


def test_port_exposes_only_one_parse_method() -> None:
    path = REPOSITORY_ROOT / "python/raos/ports/revenue_import.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    protocol = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RecordedRevenueParser"
    )
    assert [
        node.name for node in protocol.body if isinstance(node, ast.FunctionDef)
    ] == ["parse"]
