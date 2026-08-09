"""Inward ports for bounded, quarantine-only object intake."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ops.object_intake import (
    DuplicateInspectionRecord,
    IntakeDescriptor,
    MalwareInspectionRecord,
    ObjectInspectionReport,
    QuarantineDisposition,
    QuarantineRecord,
    Sha256Digest,
)


@runtime_checkable
class BoundedChunkReader(Protocol):
    """Read at most one explicitly bounded chunk; empty bytes means EOF."""

    def read_chunk(self, *, maximum_bytes: int) -> bytes: ...


@runtime_checkable
class AppendOnlyQuarantine(Protocol):
    """Write-only quarantine seam with no read/export/delete/release method."""

    def begin(self, descriptor: IntakeDescriptor) -> QuarantineRecord: ...

    def append(self, record: QuarantineRecord, chunk: bytes) -> QuarantineRecord: ...

    def seal(
        self,
        record: QuarantineRecord,
        *,
        sha256: Sha256Digest,
        size: int,
    ) -> QuarantineRecord: ...

    def record_disposition(
        self,
        record: QuarantineRecord,
        *,
        disposition: QuarantineDisposition,
    ) -> QuarantineRecord: ...


@runtime_checkable
class ObjectInspector(Protocol):
    def inspect(
        self,
        descriptor: IntakeDescriptor,
        quarantine: QuarantineRecord,
    ) -> ObjectInspectionReport: ...


@runtime_checkable
class MalwareScanner(Protocol):
    def scan(
        self,
        descriptor: IntakeDescriptor,
        quarantine: QuarantineRecord,
    ) -> MalwareInspectionRecord: ...


@runtime_checkable
class DuplicateRegistry(Protocol):
    def lookup(self, sha256: Sha256Digest) -> DuplicateInspectionRecord: ...

    def record_clean(
        self,
        descriptor: IntakeDescriptor,
        sha256: Sha256Digest,
    ) -> DuplicateInspectionRecord: ...


__all__ = [
    "AppendOnlyQuarantine",
    "BoundedChunkReader",
    "DuplicateRegistry",
    "MalwareScanner",
    "ObjectInspector",
]
