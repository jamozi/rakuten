"""Inward-only ports for the durable ST-0406 quarantine runtime."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ops.object_intake import IntakeDescriptor, Sha256Digest
from raos.domain.ops.object_intake_runtime_v2 import (
    ContentInspectionSummaryV2,
    DurableIntakeDescriptorV2,
    DurableQuarantineReceiptV2,
    IntakeCommandId,
    IntakeRuntimePolicyV2,
    MalwareScanReceiptV2,
    ObjectIntakeRuntimeFailureCode,
    PrivacyClassificationReceiptV2,
    RecoveredIntakeOutcomeV2,
    RejectedQuarantineReceiptV2,
)


@runtime_checkable
class BoundedIntakeSourceV2(Protocol):
    def read_chunk(self, *, maximum_bytes: int) -> bytes: ...


@runtime_checkable
class ContentInspectorV2(Protocol):
    def inspect(
        self,
        *,
        descriptor: IntakeDescriptor,
        content: bytes,
        policy: IntakeRuntimePolicyV2,
    ) -> ContentInspectionSummaryV2: ...


@runtime_checkable
class PrivacyClassifierV2(Protocol):
    def classify(
        self, *, descriptor: IntakeDescriptor, sha256: Sha256Digest
    ) -> PrivacyClassificationReceiptV2: ...


@runtime_checkable
class MalwareScannerV2(Protocol):
    def scan(
        self, *, descriptor: IntakeDescriptor, sha256: Sha256Digest
    ) -> MalwareScanReceiptV2: ...


@runtime_checkable
class IntakeRuntimeUnitOfWorkV2(Protocol):
    def existing(self) -> RecoveredIntakeOutcomeV2 | None: ...

    def append(self, *, expected_version: int, chunk: bytes) -> int: ...

    def seal(
        self,
        *,
        expected_version: int,
        sha256: Sha256Digest,
        received_bytes: int,
        chunk_count: int,
    ) -> int: ...

    def reject(
        self,
        *,
        expected_version: int,
        failure_code: ObjectIntakeRuntimeFailureCode,
    ) -> RejectedQuarantineReceiptV2: ...

    def accept(
        self,
        *,
        expected_version: int,
        inspection: ContentInspectionSummaryV2,
        privacy: PrivacyClassificationReceiptV2,
        malware: MalwareScanReceiptV2,
    ) -> DurableQuarantineReceiptV2: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@runtime_checkable
class IntakeRuntimeRepositoryV2(Protocol):
    def begin(
        self,
        *,
        command_id: IntakeCommandId,
        request_digest: str,
        descriptor_digest: str,
        authorization_digest: str,
        descriptor: DurableIntakeDescriptorV2,
    ) -> IntakeRuntimeUnitOfWorkV2: ...

    def recover(
        self, *, command_id: IntakeCommandId, request_digest: str
    ) -> RecoveredIntakeOutcomeV2: ...


__all__ = [
    "BoundedIntakeSourceV2",
    "ContentInspectorV2",
    "IntakeRuntimeRepositoryV2",
    "IntakeRuntimeUnitOfWorkV2",
    "MalwareScannerV2",
    "PrivacyClassifierV2",
]
