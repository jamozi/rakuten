"""Hostile failure isolation for the ST-0406 quarantine boundary."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest

from .support import (
    CONTENT,
    DIGEST,
    INTAKE_A,
    authorization_grant,
    clean_inspection,
    intake_descriptor,
    intake_policy,
    make_recorded_adapter,
    service_for,
    synthetic_source,
)
from raos.adapters.recorded_object_intake import RecordedObjectIntakeAdapter
from raos.application.ops.object_intake import ObjectIntakeService
from raos.domain.ops.object_intake import (
    ArchiveInspectionRecord,
    CsvEncoding,
    CsvInspectionRecord,
    DuplicateInspectionRecord,
    DuplicateStatus,
    InspectionStatus,
    IntakePrivacyClass,
    MagicInspectionRecord,
    MalwareInspectionRecord,
    MalwareStatus,
    ObjectInspectionReport,
    ObjectIntakeFailure,
    ObjectIntakeFailureCode,
    PrivacyInspectionRecord,
    QuarantineDisposition,
    Sha256Digest,
)


def _assert_rejected(adapter: RecordedObjectIntakeAdapter) -> None:
    assert (
        adapter.quarantine_snapshot()[-1].disposition is QuarantineDisposition.REJECTED
    )
    assert adapter.duplicate_snapshot() == ()


def _unsafe_inspections() -> tuple[ObjectInspectionReport, ...]:
    clean = clean_inspection()
    return (
        replace(
            clean,
            magic=MagicInspectionRecord(
                status=InspectionStatus.UNKNOWN,
                declared_media_type=clean.magic.declared_media_type,
                detected_media_type=None,
                extension_consistent=False,
            ),
        ),
        replace(
            clean,
            archive=ArchiveInspectionRecord(
                status=InspectionStatus.SAFE,
                entry_count=intake_policy().max_archive_entries + 1,
                uncompressed_bytes=len(CONTENT),
            ),
        ),
        replace(
            clean,
            csv=CsvInspectionRecord(
                status=InspectionStatus.REJECTED,
                encoding=CsvEncoding.UTF_8,
                row_count=2,
                column_count=2,
                max_cell_bytes=5,
                formula_prefix_detected=True,
            ),
        ),
        replace(
            clean,
            csv=CsvInspectionRecord(
                status=InspectionStatus.SAFE,
                encoding=CsvEncoding.UTF_8,
                row_count=2,
                column_count=2,
                max_cell_bytes=intake_policy().max_csv_cell_bytes + 1,
                formula_prefix_detected=False,
            ),
        ),
        replace(
            clean,
            privacy=PrivacyInspectionRecord(
                status=InspectionStatus.SAFE,
                privacy_class=IntakePrivacyClass.APPROVED_ANONYMIZED,
            ),
        ),
    )


@pytest.mark.parametrize(
    "inspection",
    _unsafe_inspections(),
    ids=(
        "magic-unknown",
        "archive-entry-limit",
        "csv-formula-prefix",
        "csv-cell-limit",
        "privacy-mismatch",
    ),
)
def test_unsafe_inspection_is_rejected_and_never_registered_clean(
    inspection: ObjectInspectionReport,
) -> None:
    adapter = make_recorded_adapter(inspection=inspection)

    with pytest.raises(ObjectIntakeFailure) as caught:
        service_for(adapter).intake(
            grant=authorization_grant(),
            descriptor=intake_descriptor(),
            source=synthetic_source(),
        )

    assert caught.value.code is ObjectIntakeFailureCode.INSPECTION_FAILED
    _assert_rejected(adapter)


@pytest.mark.parametrize(
    "status",
    (
        MalwareStatus.MALICIOUS,
        MalwareStatus.UNKNOWN,
        MalwareStatus.UNAVAILABLE,
        MalwareStatus.MALFORMED,
    ),
)
def test_every_non_clean_malware_result_fails_closed(status: MalwareStatus) -> None:
    adapter = make_recorded_adapter(malware=MalwareInspectionRecord(status=status))

    with pytest.raises(ObjectIntakeFailure) as caught:
        service_for(adapter).intake(
            grant=authorization_grant(),
            descriptor=intake_descriptor(),
            source=synthetic_source(),
        )

    assert caught.value.code is ObjectIntakeFailureCode.MALWARE_REJECTED
    _assert_rejected(adapter)


def test_declared_hash_mismatch_is_sanitized_and_quarantined_rejected() -> None:
    rejected_content = b"name,value\nEVIL,1\n"
    assert len(rejected_content) == len(CONTENT)
    adapter = make_recorded_adapter()

    with pytest.raises(ObjectIntakeFailure) as caught:
        service_for(adapter).intake(
            grant=authorization_grant(),
            descriptor=intake_descriptor(),
            source=synthetic_source(rejected_content),
        )

    assert caught.value.code is ObjectIntakeFailureCode.CONTENT_MISMATCH
    assert "EVIL" not in str(caught.value)
    assert "EVIL" not in repr(caught.value)
    _assert_rejected(adapter)


class _RaisingSource:
    def __init__(self) -> None:
        self.calls = 0

    def read_chunk(self, *, maximum_bytes: int) -> bytes:
        del maximum_bytes
        self.calls += 1
        raise RuntimeError("SECRET_CANARY_SOURCE")


def test_source_exception_is_not_echoed_or_retried() -> None:
    adapter = make_recorded_adapter()
    source = _RaisingSource()

    with pytest.raises(ObjectIntakeFailure) as caught:
        service_for(adapter).intake(
            grant=authorization_grant(),
            descriptor=intake_descriptor(),
            source=source,
        )

    assert caught.value.code is ObjectIntakeFailureCode.SOURCE_FAILED
    assert source.calls == 1
    assert "SECRET_CANARY_SOURCE" not in str(caught.value)
    assert "SECRET_CANARY_SOURCE" not in repr(caught.value)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    _assert_rejected(adapter)


class _MalformedSource:
    def __init__(self, value: object) -> None:
        self.calls = 0
        self._value = value

    def read_chunk(self, *, maximum_bytes: int) -> bytes:
        del maximum_bytes
        self.calls += 1
        return self._value  # type: ignore[return-value]


@pytest.mark.parametrize("value", (bytearray(b"unsafe"), "SECRET_CANARY_CHUNK"))
def test_non_exact_bytes_chunk_is_rejected_once_without_echo(value: object) -> None:
    adapter = make_recorded_adapter()
    source = _MalformedSource(value)

    with pytest.raises(ObjectIntakeFailure) as caught:
        service_for(adapter).intake(
            grant=authorization_grant(),
            descriptor=intake_descriptor(),
            source=source,
        )

    assert caught.value.code is ObjectIntakeFailureCode.SOURCE_FAILED
    assert source.calls == 1
    assert "SECRET_CANARY" not in repr(caught.value)
    _assert_rejected(adapter)


class _UnknownDuplicateRegistry:
    def __init__(self) -> None:
        self.lookup_calls = 0
        self.record_calls = 0

    def lookup(self, sha256: Sha256Digest) -> DuplicateInspectionRecord:
        del sha256
        self.lookup_calls += 1
        return DuplicateInspectionRecord(
            status=DuplicateStatus.UNKNOWN,
            existing_intake_id=None,
        )

    def record_clean(
        self,
        descriptor: object,
        sha256: Sha256Digest,
    ) -> DuplicateInspectionRecord:
        del descriptor, sha256
        self.record_calls += 1
        raise AssertionError("must not record an unknown duplicate result")


def test_unknown_duplicate_result_fails_before_inspection_and_registration() -> None:
    adapter = make_recorded_adapter()
    registry = _UnknownDuplicateRegistry()
    service = ObjectIntakeService(
        policy=intake_policy(),
        quarantine=adapter,
        inspector=adapter,
        malware=adapter,
        duplicate_registry=registry,
    )

    with pytest.raises(ObjectIntakeFailure) as caught:
        service.intake(
            grant=authorization_grant(),
            descriptor=intake_descriptor(),
            source=synthetic_source(),
        )

    assert caught.value.code is ObjectIntakeFailureCode.DUPLICATE_CHECK_FAILED
    assert registry.lookup_calls == 1
    assert registry.record_calls == 0
    _assert_rejected(adapter)


def test_exact_duplicate_is_still_scanned_and_malicious_result_wins() -> None:
    adapter = make_recorded_adapter(
        malware=MalwareInspectionRecord(status=MalwareStatus.MALICIOUS)
    )
    existing = intake_descriptor()
    assert adapter.record_clean(existing, DIGEST).status is DuplicateStatus.NEW
    duplicate = intake_descriptor(
        intake_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    )

    with pytest.raises(ObjectIntakeFailure) as caught:
        service_for(adapter).intake(
            grant=authorization_grant(),
            descriptor=duplicate,
            source=synthetic_source(),
        )

    assert caught.value.code is ObjectIntakeFailureCode.MALWARE_REJECTED
    assert adapter.duplicate_snapshot()[0].intake_id == INTAKE_A
    assert (
        adapter.quarantine_snapshot()[-1].disposition is QuarantineDisposition.REJECTED
    )


def test_append_capacity_exhaustion_never_evicts_existing_events() -> None:
    adapter = make_recorded_adapter(event_capacity=2)

    with pytest.raises(ObjectIntakeFailure) as caught:
        service_for(adapter).intake(
            grant=authorization_grant(),
            descriptor=intake_descriptor(),
            source=synthetic_source(),
        )

    assert caught.value.code is ObjectIntakeFailureCode.QUARANTINE_FAILED
    snapshot = adapter.quarantine_snapshot()
    assert len(snapshot) == 2
    assert snapshot[0].received_bytes == 0
    assert snapshot[1].received_bytes == intake_policy().max_chunk_bytes


def test_scripted_digest_miss_fails_closed_without_fallback() -> None:
    missing_digest = Sha256Digest("f" * 64)
    adapter = make_recorded_adapter(digest=missing_digest)

    with pytest.raises(ObjectIntakeFailure) as caught:
        service_for(adapter).intake(
            grant=authorization_grant(),
            descriptor=intake_descriptor(),
            source=synthetic_source(),
        )

    assert caught.value.code is ObjectIntakeFailureCode.INSPECTION_FAILED
    _assert_rejected(adapter)
