"""Bounded process-local TEST_ONLY object-intake adapters."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from threading import RLock
from typing import NoReturn, SupportsIndex, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.object_intake import (
    DuplicateInspectionRecord,
    DuplicateStatus,
    IntakeDescriptor,
    MalwareInspectionRecord,
    ObjectInspectionReport,
    ObjectIntakeFailureCode,
    QuarantineDisposition,
    QuarantineRecord,
    QuarantineStatus,
    Sha256Digest,
    fail_object_intake,
)


_MAX_CAPACITY = 100_000


def _positive_capacity(value: object) -> int:
    if type(value) is not int or not 0 < value <= _MAX_CAPACITY:
        fail_object_intake()
    return value


def _environment(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }:
        fail_object_intake()
    return value


@final
class SyntheticChunkReader:
    """One bounded in-memory synthetic source with no content snapshot."""

    __slots__ = ("_content", "_environment", "_offset")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        byte_capacity: int,
        content: bytes,
    ) -> None:
        self._environment = _environment(environment)
        capacity = _positive_capacity(byte_capacity)
        if type(content) is not bytes or not content or len(content) > capacity:
            fail_object_intake()
        self._content = content
        self._offset = 0

    @property
    def remaining_bytes(self) -> int:
        return len(self._content) - self._offset

    def __repr__(self) -> str:
        return "SyntheticChunkReader(<redacted-object-intake>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("synthetic source serialization is not supported")

    def read_chunk(self, *, maximum_bytes: int) -> bytes:
        limit = _positive_capacity(maximum_bytes)
        if self._offset == len(self._content):
            return b""
        end = min(self._offset + limit, len(self._content))
        chunk = self._content[self._offset : end]
        self._offset = end
        return chunk


@dataclass(frozen=True, slots=True, repr=False)
class _QuarantineEvent:
    record: QuarantineRecord
    chunk: bytes | None

    def __repr__(self) -> str:
        return "_QuarantineEvent(<redacted-object-intake>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("quarantine event serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class RecordedDuplicateMetadata:
    sha256: str
    intake_id: UUID

    def __repr__(self) -> str:
        return "RecordedDuplicateMetadata(<redacted-object-intake>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("duplicate metadata serialization is not supported")


@final
class RecordedObjectIntakeAdapter:
    """Digest-scripted inspector/scanner and append-only quarantine registry."""

    __slots__ = (
        "_byte_capacity",
        "_duplicate_capacity",
        "_duplicates",
        "_environment",
        "_event_capacity",
        "_events",
        "_inspection_scripts",
        "_lock",
        "_malware_scripts",
        "_script_capacity",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        event_capacity: int,
        byte_capacity: int,
        script_capacity: int,
        duplicate_capacity: int,
        inspection_scripts: tuple[tuple[Sha256Digest, ObjectInspectionReport], ...],
        malware_scripts: tuple[tuple[Sha256Digest, MalwareInspectionRecord], ...],
    ) -> None:
        self._environment = _environment(environment)
        self._event_capacity = _positive_capacity(event_capacity)
        self._byte_capacity = _positive_capacity(byte_capacity)
        self._script_capacity = _positive_capacity(script_capacity)
        self._duplicate_capacity = _positive_capacity(duplicate_capacity)
        if (
            type(inspection_scripts) is not tuple
            or type(malware_scripts) is not tuple
            or len(inspection_scripts) > self._script_capacity
            or len(malware_scripts) > self._script_capacity
            or any(
                type(row) is not tuple
                or len(row) != 2
                or type(row[0]) is not Sha256Digest
                or type(row[1]) is not ObjectInspectionReport
                for row in inspection_scripts
            )
            or any(
                type(row) is not tuple
                or len(row) != 2
                or type(row[0]) is not Sha256Digest
                or type(row[1]) is not MalwareInspectionRecord
                for row in malware_scripts
            )
            or len({row[0] for row in inspection_scripts}) != len(inspection_scripts)
            or len({row[0] for row in malware_scripts}) != len(malware_scripts)
        ):
            fail_object_intake()
        self._inspection_scripts = inspection_scripts
        self._malware_scripts = malware_scripts
        self._events: tuple[_QuarantineEvent, ...] = ()
        self._duplicates: tuple[tuple[Sha256Digest, UUID], ...] = ()
        self._lock = RLock()

    @property
    def environment(self) -> RuntimeEnvironment:
        return self._environment

    def _latest(self, quarantine_id: UUID) -> QuarantineRecord | None:
        for event in reversed(self._events):
            if event.record.quarantine_id == quarantine_id:
                return event.record
        return None

    def _append_event(self, event: _QuarantineEvent) -> None:
        if len(self._events) >= self._event_capacity:
            fail_object_intake(ObjectIntakeFailureCode.QUARANTINE_FAILED)
        stored_bytes = sum(
            len(existing.chunk)
            for existing in self._events
            if existing.chunk is not None
        )
        added = 0 if event.chunk is None else len(event.chunk)
        if stored_bytes + added > self._byte_capacity:
            fail_object_intake(ObjectIntakeFailureCode.QUARANTINE_FAILED)
        self._events = (*self._events, event)

    def begin(self, descriptor: IntakeDescriptor) -> QuarantineRecord:
        if type(descriptor) is not IntakeDescriptor:
            fail_object_intake()
        quarantine_id = UUID(int=(descriptor.intake_id.int ^ 1) or 1)
        record = QuarantineRecord(
            intake_id=descriptor.intake_id,
            quarantine_id=quarantine_id,
            status=QuarantineStatus.OPEN,
            received_bytes=0,
            chunk_count=0,
            sealed_sha256=None,
            disposition=None,
        )
        with self._lock:
            if self._latest(quarantine_id) is not None:
                fail_object_intake(ObjectIntakeFailureCode.QUARANTINE_FAILED)
            self._append_event(_QuarantineEvent(record=record, chunk=None))
        return record

    def append(self, record: QuarantineRecord, chunk: bytes) -> QuarantineRecord:
        if (
            type(record) is not QuarantineRecord
            or record.status is not QuarantineStatus.OPEN
            or type(chunk) is not bytes
            or not chunk
        ):
            fail_object_intake()
        with self._lock:
            if self._latest(record.quarantine_id) != record:
                fail_object_intake(ObjectIntakeFailureCode.QUARANTINE_FAILED)
            appended = QuarantineRecord(
                intake_id=record.intake_id,
                quarantine_id=record.quarantine_id,
                status=QuarantineStatus.OPEN,
                received_bytes=record.received_bytes + len(chunk),
                chunk_count=record.chunk_count + 1,
                sealed_sha256=None,
                disposition=None,
            )
            self._append_event(_QuarantineEvent(record=appended, chunk=chunk))
            return appended

    def seal(
        self,
        record: QuarantineRecord,
        *,
        sha256: Sha256Digest,
        size: int,
    ) -> QuarantineRecord:
        if (
            type(record) is not QuarantineRecord
            or record.status is not QuarantineStatus.OPEN
            or type(sha256) is not Sha256Digest
            or type(size) is not int
            or size <= 0
            or size != record.received_bytes
            or record.chunk_count <= 0
        ):
            fail_object_intake()
        with self._lock:
            if self._latest(record.quarantine_id) != record:
                fail_object_intake(ObjectIntakeFailureCode.QUARANTINE_FAILED)
            digest = hashlib.sha256()
            for event in self._events:
                if event.record.quarantine_id == record.quarantine_id and event.chunk:
                    digest.update(event.chunk)
            if digest.hexdigest() != sha256.value:
                fail_object_intake(ObjectIntakeFailureCode.CONTENT_MISMATCH)
            sealed = QuarantineRecord(
                intake_id=record.intake_id,
                quarantine_id=record.quarantine_id,
                status=QuarantineStatus.SEALED,
                received_bytes=record.received_bytes,
                chunk_count=record.chunk_count,
                sealed_sha256=sha256,
                disposition=None,
            )
            self._append_event(_QuarantineEvent(record=sealed, chunk=None))
            return sealed

    def record_disposition(
        self,
        record: QuarantineRecord,
        *,
        disposition: QuarantineDisposition,
    ) -> QuarantineRecord:
        if (
            type(record) is not QuarantineRecord
            or type(disposition) is not QuarantineDisposition
            or record.status not in {QuarantineStatus.OPEN, QuarantineStatus.SEALED}
        ):
            fail_object_intake()
        if (
            disposition is QuarantineDisposition.CLEAN_QUARANTINED
            and record.status is not QuarantineStatus.SEALED
        ):
            fail_object_intake()
        with self._lock:
            if self._latest(record.quarantine_id) != record:
                fail_object_intake(ObjectIntakeFailureCode.QUARANTINE_FAILED)
            classified = QuarantineRecord(
                intake_id=record.intake_id,
                quarantine_id=record.quarantine_id,
                status=QuarantineStatus.DISPOSITION_RECORDED,
                received_bytes=record.received_bytes,
                chunk_count=record.chunk_count,
                sealed_sha256=record.sealed_sha256,
                disposition=disposition,
            )
            self._append_event(_QuarantineEvent(record=classified, chunk=None))
            return classified

    def _sealed_digest(self, quarantine: QuarantineRecord) -> Sha256Digest:
        if (
            type(quarantine) is not QuarantineRecord
            or quarantine.status is not QuarantineStatus.SEALED
            or type(quarantine.sealed_sha256) is not Sha256Digest
        ):
            fail_object_intake()
        with self._lock:
            if self._latest(quarantine.quarantine_id) != quarantine:
                fail_object_intake(ObjectIntakeFailureCode.QUARANTINE_FAILED)
        return quarantine.sealed_sha256

    def inspect(
        self,
        descriptor: IntakeDescriptor,
        quarantine: QuarantineRecord,
    ) -> ObjectInspectionReport:
        if type(descriptor) is not IntakeDescriptor:
            fail_object_intake()
        if quarantine.intake_id != descriptor.intake_id:
            fail_object_intake()
        digest = self._sealed_digest(quarantine)
        for scripted_digest, report in self._inspection_scripts:
            if scripted_digest == digest:
                return report
        fail_object_intake(ObjectIntakeFailureCode.INSPECTION_FAILED)

    def scan(
        self,
        descriptor: IntakeDescriptor,
        quarantine: QuarantineRecord,
    ) -> MalwareInspectionRecord:
        if type(descriptor) is not IntakeDescriptor:
            fail_object_intake()
        if quarantine.intake_id != descriptor.intake_id:
            fail_object_intake()
        digest = self._sealed_digest(quarantine)
        for scripted_digest, report in self._malware_scripts:
            if scripted_digest == digest:
                return report
        fail_object_intake(ObjectIntakeFailureCode.MALWARE_REJECTED)

    def lookup(self, sha256: Sha256Digest) -> DuplicateInspectionRecord:
        if type(sha256) is not Sha256Digest:
            fail_object_intake()
        with self._lock:
            for digest, intake_id in self._duplicates:
                if digest == sha256:
                    return DuplicateInspectionRecord(
                        status=DuplicateStatus.EXACT_DUPLICATE,
                        existing_intake_id=intake_id,
                    )
        return DuplicateInspectionRecord(
            status=DuplicateStatus.NEW, existing_intake_id=None
        )

    def record_clean(
        self,
        descriptor: IntakeDescriptor,
        sha256: Sha256Digest,
    ) -> DuplicateInspectionRecord:
        if (
            type(descriptor) is not IntakeDescriptor
            or type(sha256) is not Sha256Digest
            or descriptor.declared_sha256 != sha256
        ):
            fail_object_intake()
        with self._lock:
            for digest, intake_id in self._duplicates:
                if digest == sha256:
                    return DuplicateInspectionRecord(
                        status=DuplicateStatus.EXACT_DUPLICATE,
                        existing_intake_id=intake_id,
                    )
            if len(self._duplicates) >= self._duplicate_capacity:
                fail_object_intake(ObjectIntakeFailureCode.DUPLICATE_CHECK_FAILED)
            self._duplicates = (*self._duplicates, (sha256, descriptor.intake_id))
        return DuplicateInspectionRecord(
            status=DuplicateStatus.NEW, existing_intake_id=None
        )

    def quarantine_snapshot(self) -> tuple[QuarantineRecord, ...]:
        """Return metadata records only; stored synthetic bytes remain inaccessible."""

        with self._lock:
            return tuple(event.record for event in self._events)

    def duplicate_snapshot(self) -> tuple[RecordedDuplicateMetadata, ...]:
        with self._lock:
            return tuple(
                RecordedDuplicateMetadata(sha256=digest.value, intake_id=intake_id)
                for digest, intake_id in self._duplicates
            )


__all__ = [
    "RecordedDuplicateMetadata",
    "RecordedObjectIntakeAdapter",
    "SyntheticChunkReader",
]
