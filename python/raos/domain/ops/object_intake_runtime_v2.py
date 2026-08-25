"""Closed values for the durable, recorded-only ST-0406 intake runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import NoReturn, SupportsIndex
from uuid import UUID

from raos.domain.ops.object_intake import (
    DuplicateStatus,
    IntakeDescriptor,
    IntakePrivacyClass,
    ObjectIntakeKind,
    Sha256Digest,
)


_TOKEN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._:-]{0,126}[A-Za-z0-9])?\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_INTEGER = (1 << 63) - 1
_REDACTED = "<redacted-secure-intake-v2>"


class IntakeRuntimeMode(str, Enum):
    """Only local recorded execution and a fail-closed disabled mode exist."""

    RECORDED_LOCAL = "RECORDED_LOCAL"
    DISABLED = "DISABLED"


class IntakeFormat(str, Enum):
    CSV = "CSV"
    ZIP = "ZIP"
    TAR = "TAR"
    TAR_GZIP = "TAR_GZIP"
    PNG = "PNG"
    JPEG = "JPEG"
    WEBP = "WEBP"
    PDF = "PDF"


class DurableIntakeState(str, Enum):
    OPEN = "OPEN"
    SEALED = "SEALED"
    CLEAN_QUARANTINED = "CLEAN_QUARANTINED"
    REJECTED = "REJECTED"


class RecordedMalwareVerdict(str, Enum):
    CLEAN = "CLEAN"
    MALICIOUS = "MALICIOUS"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


class RecordedPrivacyVerdict(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


class ObjectIntakeRuntimeFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    AUTHORIZATION_NOT_DURABLE = "AUTHORIZATION_NOT_DURABLE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    SOURCE_FAILED = "SOURCE_FAILED"
    STREAM_LIMIT_EXCEEDED = "STREAM_LIMIT_EXCEEDED"
    CONTENT_MISMATCH = "CONTENT_MISMATCH"
    FORMAT_REJECTED = "FORMAT_REJECTED"
    PRIVACY_REJECTED = "PRIVACY_REJECTED"
    MALWARE_REJECTED = "MALWARE_REJECTED"
    MALWARE_DISABLED = "MALWARE_DISABLED"
    CONCURRENT_MODIFICATION = "CONCURRENT_MODIFICATION"
    STORAGE_FAILED = "STORAGE_FAILED"
    STORAGE_COMMIT_UNKNOWN = "STORAGE_COMMIT_UNKNOWN"
    RECOVERY_NOT_FOUND = "RECOVERY_NOT_FOUND"
    TAMPER_DETECTED = "TAMPER_DETECTED"
    SCHEMA_DRIFT = "SCHEMA_DRIFT"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("secure intake runtime values cannot be serialized")


class ObjectIntakeRuntimeFailure(RuntimeError):
    """One closed failure that never retains rejected bytes or collaborator text."""

    __slots__ = ("_code",)

    def __init__(self, code: ObjectIntakeRuntimeFailureCode) -> None:
        if type(code) is not ObjectIntakeRuntimeFailureCode:
            raise TypeError("code must be an exact ObjectIntakeRuntimeFailureCode")
        super().__init__(code.value)
        self._code = code

    @property
    def code(self) -> ObjectIntakeRuntimeFailureCode:
        return self._code

    def __repr__(self) -> str:
        return f"ObjectIntakeRuntimeFailure(code={self.code.value})"

    def __str__(self) -> str:
        return self.code.value

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("secure intake runtime failures cannot be serialized")


def fail_intake_runtime(
    code: ObjectIntakeRuntimeFailureCode = ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise ObjectIntakeRuntimeFailure(code) from None


def _positive(value: object) -> int:
    if type(value) is not int or not 0 < value <= _MAX_INTEGER:
        fail_intake_runtime()
    return value


def _nonnegative(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_INTEGER:
        fail_intake_runtime()
    return value


def _digest(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_intake_runtime()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class IntakeCommandId(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _TOKEN.fullmatch(self.value) is None:
            fail_intake_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class DurableIntakeDescriptorV2(_RedactedValue):
    """The base descriptor plus the exact canonical authorization resource."""

    descriptor: IntakeDescriptor
    authorization_resource_id: UUID

    def __post_init__(self) -> None:
        if (
            type(self.descriptor) is not IntakeDescriptor
            or type(self.authorization_resource_id) is not UUID
            or self.authorization_resource_id.int == 0
        ):
            fail_intake_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class IntakeRuntimePolicyV2(_RedactedValue):
    """Explicit local limits; it deliberately contains no retention setting."""

    mode: IntakeRuntimeMode
    max_object_bytes: int
    max_chunk_bytes: int
    max_chunk_count: int
    max_archive_entries: int
    max_archive_uncompressed_bytes: int
    max_archive_ratio: int
    max_archive_nesting: int
    max_csv_rows: int
    max_csv_columns: int
    max_csv_cell_bytes: int
    allowed_media_types: tuple[str, ...]
    allowed_privacy_classes: tuple[IntakePrivacyClass, ...]

    def __post_init__(self) -> None:
        if type(self.mode) is not IntakeRuntimeMode:
            fail_intake_runtime()
        for value in (
            self.max_object_bytes,
            self.max_chunk_bytes,
            self.max_chunk_count,
            self.max_archive_entries,
            self.max_archive_uncompressed_bytes,
            self.max_archive_ratio,
            self.max_archive_nesting,
            self.max_csv_rows,
            self.max_csv_columns,
            self.max_csv_cell_bytes,
        ):
            _positive(value)
        if (
            self.max_chunk_bytes > self.max_object_bytes
            or self.max_archive_uncompressed_bytes < self.max_object_bytes
            or self.max_archive_nesting != 1
            or type(self.allowed_media_types) is not tuple
            or not self.allowed_media_types
            or any(
                type(value) is not str
                or not value
                or value != value.lower()
                or ";" in value
                for value in self.allowed_media_types
            )
            or self.allowed_media_types != tuple(sorted(set(self.allowed_media_types)))
            or type(self.allowed_privacy_classes) is not tuple
            or not self.allowed_privacy_classes
            or any(
                type(value) is not IntakePrivacyClass
                for value in self.allowed_privacy_classes
            )
            or self.allowed_privacy_classes
            != tuple(
                sorted(set(self.allowed_privacy_classes), key=lambda row: row.value)
            )
        ):
            fail_intake_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class ContentInspectionSummaryV2(_RedactedValue):
    format: IntakeFormat
    archive_entry_count: int
    archive_uncompressed_bytes: int
    csv_row_count: int
    csv_column_count: int
    csv_max_cell_bytes: int
    formula_prefix_safe: bool

    def __post_init__(self) -> None:
        if (
            type(self.format) is not IntakeFormat
            or type(self.formula_prefix_safe) is not bool
        ):
            fail_intake_runtime()
        for value in (
            self.archive_entry_count,
            self.archive_uncompressed_bytes,
            self.csv_row_count,
            self.csv_column_count,
            self.csv_max_cell_bytes,
        ):
            _nonnegative(value)
        if self.format is IntakeFormat.CSV:
            if (
                self.csv_row_count == 0
                or self.csv_column_count == 0
                or not self.formula_prefix_safe
                or self.archive_entry_count != 0
                or self.archive_uncompressed_bytes != 0
            ):
                fail_intake_runtime()
        elif any(
            value != 0
            for value in (
                self.csv_row_count,
                self.csv_column_count,
                self.csv_max_cell_bytes,
            )
        ):
            fail_intake_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class MalwareScanReceiptV2(_RedactedValue):
    verdict: RecordedMalwareVerdict
    engine_revision: str

    def __post_init__(self) -> None:
        if (
            type(self.verdict) is not RecordedMalwareVerdict
            or type(self.engine_revision) is not str
            or _TOKEN.fullmatch(self.engine_revision) is None
        ):
            fail_intake_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class PrivacyClassificationReceiptV2(_RedactedValue):
    verdict: RecordedPrivacyVerdict
    classified_as: IntakePrivacyClass | None
    classifier_revision: str

    def __post_init__(self) -> None:
        if (
            type(self.verdict) is not RecordedPrivacyVerdict
            or (
                self.classified_as is not None
                and type(self.classified_as) is not IntakePrivacyClass
            )
            or type(self.classifier_revision) is not str
            or _TOKEN.fullmatch(self.classifier_revision) is None
        ):
            fail_intake_runtime()
        if (self.verdict is RecordedPrivacyVerdict.MATCH) != (
            type(self.classified_as) is IntakePrivacyClass
        ):
            fail_intake_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class DurableQuarantineReceiptV2(_RedactedValue):
    command_id: IntakeCommandId
    intake_id: UUID
    quarantine_id: UUID
    site_id: UUID
    authorization_resource_id: UUID
    kind: ObjectIntakeKind
    state: DurableIntakeState
    version: int
    received_bytes: int
    chunk_count: int
    sha256: Sha256Digest
    duplicate_status: DuplicateStatus
    duplicate_of_intake_id: UUID | None
    inspection: ContentInspectionSummaryV2
    privacy: PrivacyClassificationReceiptV2
    malware: MalwareScanReceiptV2
    journal_head_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.command_id) is not IntakeCommandId
            or type(self.intake_id) is not UUID
            or self.intake_id.int == 0
            or type(self.quarantine_id) is not UUID
            or self.quarantine_id.int == 0
            or type(self.site_id) is not UUID
            or self.site_id.int == 0
            or type(self.authorization_resource_id) is not UUID
            or self.authorization_resource_id.int == 0
            or type(self.kind) is not ObjectIntakeKind
            or self.state is not DurableIntakeState.CLEAN_QUARANTINED
            or type(self.sha256) is not Sha256Digest
            or type(self.duplicate_status) is not DuplicateStatus
            or self.duplicate_status
            not in {DuplicateStatus.NEW, DuplicateStatus.EXACT_DUPLICATE}
            or (
                self.duplicate_of_intake_id is not None
                and (
                    type(self.duplicate_of_intake_id) is not UUID
                    or self.duplicate_of_intake_id.int == 0
                )
            )
            or (self.duplicate_status is DuplicateStatus.EXACT_DUPLICATE)
            != (type(self.duplicate_of_intake_id) is UUID)
            or type(self.inspection) is not ContentInspectionSummaryV2
            or type(self.privacy) is not PrivacyClassificationReceiptV2
            or self.privacy.verdict is not RecordedPrivacyVerdict.MATCH
            or type(self.malware) is not MalwareScanReceiptV2
            or self.malware.verdict is not RecordedMalwareVerdict.CLEAN
        ):
            fail_intake_runtime()
        _positive(self.version)
        _positive(self.received_bytes)
        _positive(self.chunk_count)
        _digest(self.journal_head_sha256)


@dataclass(frozen=True, slots=True, repr=False)
class RejectedQuarantineReceiptV2(_RedactedValue):
    command_id: IntakeCommandId
    intake_id: UUID
    quarantine_id: UUID
    state: DurableIntakeState
    version: int
    failure_code: ObjectIntakeRuntimeFailureCode
    journal_head_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.command_id) is not IntakeCommandId
            or type(self.intake_id) is not UUID
            or self.intake_id.int == 0
            or type(self.quarantine_id) is not UUID
            or self.quarantine_id.int == 0
            or self.state is not DurableIntakeState.REJECTED
            or type(self.failure_code) is not ObjectIntakeRuntimeFailureCode
            or self.failure_code
            in {
                ObjectIntakeRuntimeFailureCode.AUTHORIZATION_REQUIRED,
                ObjectIntakeRuntimeFailureCode.AUTHORIZATION_NOT_DURABLE,
                ObjectIntakeRuntimeFailureCode.IDEMPOTENCY_CONFLICT,
                ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION,
                ObjectIntakeRuntimeFailureCode.STORAGE_FAILED,
                ObjectIntakeRuntimeFailureCode.STORAGE_COMMIT_UNKNOWN,
                ObjectIntakeRuntimeFailureCode.RECOVERY_NOT_FOUND,
                ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED,
                ObjectIntakeRuntimeFailureCode.SCHEMA_DRIFT,
            }
        ):
            fail_intake_runtime()
        _positive(self.version)
        _digest(self.journal_head_sha256)


@dataclass(frozen=True, slots=True, repr=False)
class RecoveredIntakeOutcomeV2(_RedactedValue):
    request_digest: str
    descriptor_digest: str
    authorization_digest: str
    accepted: DurableQuarantineReceiptV2 | None
    rejected: RejectedQuarantineReceiptV2 | None

    def __post_init__(self) -> None:
        _digest(self.request_digest)
        _digest(self.descriptor_digest)
        _digest(self.authorization_digest)
        if (type(self.accepted) is DurableQuarantineReceiptV2) == (
            type(self.rejected) is RejectedQuarantineReceiptV2
        ):
            fail_intake_runtime()


def require_descriptor(value: object) -> DurableIntakeDescriptorV2:
    if type(value) is not DurableIntakeDescriptorV2:
        fail_intake_runtime()
    return value


__all__ = [
    "ContentInspectionSummaryV2",
    "DurableIntakeState",
    "DurableIntakeDescriptorV2",
    "DurableQuarantineReceiptV2",
    "IntakeCommandId",
    "IntakeFormat",
    "IntakeRuntimeMode",
    "IntakeRuntimePolicyV2",
    "MalwareScanReceiptV2",
    "ObjectIntakeRuntimeFailure",
    "ObjectIntakeRuntimeFailureCode",
    "PrivacyClassificationReceiptV2",
    "RecordedMalwareVerdict",
    "RecordedPrivacyVerdict",
    "RecoveredIntakeOutcomeV2",
    "RejectedQuarantineReceiptV2",
    "fail_intake_runtime",
    "require_descriptor",
]
