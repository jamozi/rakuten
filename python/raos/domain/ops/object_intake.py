"""Closed, redacted values for TEST_ONLY secure object intake."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import NoReturn, SupportsIndex
from uuid import UUID


_LEAF = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?\Z")
_MIME = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REDACTED = "<redacted-object-intake>"
_MAX_EXACT_INTEGER = (1 << 63) - 1


class ObjectIntakeKind(str, Enum):
    """The only initial object classes accepted by the intake seam."""

    SOURCE_DOCUMENT = "SOURCE_DOCUMENT"
    MEDIA_ASSET = "MEDIA_ASSET"
    REVENUE_REPORT = "REVENUE_REPORT"


class IntakePrivacyClass(str, Enum):
    """Non-production data classes admitted by an explicit policy."""

    SYNTHETIC = "SYNTHETIC"
    APPROVED_ANONYMIZED = "APPROVED_ANONYMIZED"


class CsvEncoding(str, Enum):
    """The only encoding classified as safe by this local contract."""

    UTF_8 = "UTF_8"


class QuarantineStatus(str, Enum):
    OPEN = "OPEN"
    SEALED = "SEALED"
    DISPOSITION_RECORDED = "DISPOSITION_RECORDED"


class QuarantineDisposition(str, Enum):
    CLEAN_QUARANTINED = "CLEAN_QUARANTINED"
    REJECTED = "REJECTED"


class InspectionStatus(str, Enum):
    SAFE = "SAFE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    MALFORMED = "MALFORMED"


class MalwareStatus(str, Enum):
    CLEAN = "CLEAN"
    MALICIOUS = "MALICIOUS"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    MALFORMED = "MALFORMED"


class DuplicateStatus(str, Enum):
    NEW = "NEW"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    MALFORMED = "MALFORMED"


class IntakeOutcome(str, Enum):
    CLEAN_QUARANTINED = "CLEAN_QUARANTINED"


class ObjectIntakeFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    SOURCE_FAILED = "SOURCE_FAILED"
    STREAM_LIMIT_EXCEEDED = "STREAM_LIMIT_EXCEEDED"
    CONTENT_MISMATCH = "CONTENT_MISMATCH"
    QUARANTINE_FAILED = "QUARANTINE_FAILED"
    INSPECTION_FAILED = "INSPECTION_FAILED"
    MALWARE_REJECTED = "MALWARE_REJECTED"
    DUPLICATE_CHECK_FAILED = "DUPLICATE_CHECK_FAILED"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("object intake serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class ObjectIntakeFailure(ValueError):
    """Sanitized failure that cannot retain or print rejected material."""

    code: ObjectIntakeFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not ObjectIntakeFailureCode:
            raise TypeError("code must be an exact ObjectIntakeFailureCode")
        ValueError.__init__(self, self.code.value)

    def __repr__(self) -> str:
        return f"ObjectIntakeFailure(code={self.code.value})"

    def __str__(self) -> str:
        return self.code.value

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("object intake failure serialization is not supported")


def fail_object_intake(
    code: ObjectIntakeFailureCode = ObjectIntakeFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise ObjectIntakeFailure(code) from None


def _positive_exact_int(value: object) -> int:
    if type(value) is not int or not 0 < value <= _MAX_EXACT_INTEGER:
        fail_object_intake()
    return value


def _nonnegative_exact_int(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_EXACT_INTEGER:
        fail_object_intake()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class SafeLeafName(_RedactedValue):
    """A single portable leaf, never a path."""

    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or _LEAF.fullmatch(self.value) is None
            or ".." in self.value
            or "/" in self.value
            or "\\" in self.value
        ):
            fail_object_intake()


@dataclass(frozen=True, slots=True, repr=False)
class MediaType(_RedactedValue):
    """Lower-case, parameter-free MIME media type."""

    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or not 3 <= len(self.value) <= 127
            or _MIME.fullmatch(self.value) is None
        ):
            fail_object_intake()


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_object_intake()


@dataclass(frozen=True, slots=True, repr=False)
class IntakeDescriptor(_RedactedValue):
    intake_id: UUID
    site_id: UUID
    kind: ObjectIntakeKind
    leaf_name: SafeLeafName
    media_type: MediaType
    declared_size: int
    declared_sha256: Sha256Digest
    privacy_class: IntakePrivacyClass

    def __post_init__(self) -> None:
        if (
            type(self.intake_id) is not UUID
            or type(self.site_id) is not UUID
            or type(self.kind) is not ObjectIntakeKind
            or type(self.leaf_name) is not SafeLeafName
            or type(self.media_type) is not MediaType
            or type(self.declared_sha256) is not Sha256Digest
            or type(self.privacy_class) is not IntakePrivacyClass
            or self.intake_id.int == 0
            or self.site_id.int == 0
        ):
            fail_object_intake()
        _positive_exact_int(self.declared_size)


@dataclass(frozen=True, slots=True, repr=False)
class IntakePolicy(_RedactedValue):
    """Explicit TEST_ONLY bounds; no production or retention setting exists."""

    environment: str
    max_object_bytes: int
    max_chunk_bytes: int
    max_chunk_count: int
    max_archive_entries: int
    max_archive_uncompressed_bytes: int
    max_archive_ratio: int
    max_csv_rows: int
    max_csv_columns: int
    max_csv_cell_bytes: int
    allowed_media_types: tuple[MediaType, ...]
    allowed_privacy_classes: tuple[IntakePrivacyClass, ...]

    def __post_init__(self) -> None:
        if type(self.environment) is not str or self.environment != "TEST_ONLY":
            fail_object_intake()
        for value in (
            self.max_object_bytes,
            self.max_chunk_bytes,
            self.max_chunk_count,
            self.max_archive_entries,
            self.max_archive_uncompressed_bytes,
            self.max_archive_ratio,
            self.max_csv_rows,
            self.max_csv_columns,
            self.max_csv_cell_bytes,
        ):
            _positive_exact_int(value)
        if (
            self.max_chunk_bytes > self.max_object_bytes
            or self.max_archive_uncompressed_bytes < self.max_object_bytes
        ):
            fail_object_intake()
        if (
            type(self.allowed_media_types) is not tuple
            or not self.allowed_media_types
            or any(type(value) is not MediaType for value in self.allowed_media_types)
            or len(set(self.allowed_media_types)) != len(self.allowed_media_types)
            or self.allowed_media_types
            != tuple(sorted(self.allowed_media_types, key=lambda value: value.value))
            or type(self.allowed_privacy_classes) is not tuple
            or not self.allowed_privacy_classes
            or any(
                type(value) is not IntakePrivacyClass
                for value in self.allowed_privacy_classes
            )
            or len(set(self.allowed_privacy_classes))
            != len(self.allowed_privacy_classes)
            or self.allowed_privacy_classes
            != tuple(
                sorted(self.allowed_privacy_classes, key=lambda value: value.value)
            )
        ):
            fail_object_intake()


@dataclass(frozen=True, slots=True, repr=False)
class QuarantineRecord(_RedactedValue):
    intake_id: UUID
    quarantine_id: UUID
    status: QuarantineStatus
    received_bytes: int
    chunk_count: int
    sealed_sha256: Sha256Digest | None
    disposition: QuarantineDisposition | None

    def __post_init__(self) -> None:
        if (
            type(self.intake_id) is not UUID
            or type(self.quarantine_id) is not UUID
            or self.intake_id.int == 0
            or self.quarantine_id.int == 0
            or type(self.status) is not QuarantineStatus
            or (
                self.sealed_sha256 is not None
                and type(self.sealed_sha256) is not Sha256Digest
            )
            or (
                self.disposition is not None
                and type(self.disposition) is not QuarantineDisposition
            )
        ):
            fail_object_intake()
        _nonnegative_exact_int(self.received_bytes)
        _nonnegative_exact_int(self.chunk_count)
        if self.status is QuarantineStatus.OPEN and (
            self.sealed_sha256 is not None or self.disposition is not None
        ):
            fail_object_intake()
        if self.status is QuarantineStatus.SEALED and (
            type(self.sealed_sha256) is not Sha256Digest or self.disposition is not None
        ):
            fail_object_intake()
        if self.status is QuarantineStatus.DISPOSITION_RECORDED and (
            type(self.disposition) is not QuarantineDisposition
            or (
                self.disposition is QuarantineDisposition.CLEAN_QUARANTINED
                and type(self.sealed_sha256) is not Sha256Digest
            )
        ):
            fail_object_intake()


@dataclass(frozen=True, slots=True, repr=False)
class MagicInspectionRecord(_RedactedValue):
    status: InspectionStatus
    declared_media_type: MediaType
    detected_media_type: MediaType | None
    extension_consistent: bool

    def __post_init__(self) -> None:
        if (
            type(self.status) is not InspectionStatus
            or type(self.declared_media_type) is not MediaType
            or type(self.extension_consistent) is not bool
            or (
                self.detected_media_type is not None
                and type(self.detected_media_type) is not MediaType
            )
        ):
            fail_object_intake()
        if self.status is InspectionStatus.SAFE:
            if (
                self.detected_media_type != self.declared_media_type
                or not self.extension_consistent
            ):
                fail_object_intake()
        elif self.detected_media_type is not None or self.extension_consistent:
            fail_object_intake()


@dataclass(frozen=True, slots=True, repr=False)
class MalwareInspectionRecord(_RedactedValue):
    status: MalwareStatus

    def __post_init__(self) -> None:
        if type(self.status) is not MalwareStatus:
            fail_object_intake()


@dataclass(frozen=True, slots=True, repr=False)
class DuplicateInspectionRecord(_RedactedValue):
    status: DuplicateStatus
    existing_intake_id: UUID | None

    def __post_init__(self) -> None:
        if (
            type(self.status) is not DuplicateStatus
            or (
                self.existing_intake_id is not None
                and type(self.existing_intake_id) is not UUID
            )
            or (
                type(self.existing_intake_id) is UUID
                and self.existing_intake_id.int == 0
            )
        ):
            fail_object_intake()
        if (self.status is DuplicateStatus.EXACT_DUPLICATE) != (
            type(self.existing_intake_id) is UUID
        ):
            fail_object_intake()


@dataclass(frozen=True, slots=True, repr=False)
class ArchiveInspectionRecord(_RedactedValue):
    status: InspectionStatus
    entry_count: int
    uncompressed_bytes: int

    def __post_init__(self) -> None:
        if type(self.status) is not InspectionStatus:
            fail_object_intake()
        _nonnegative_exact_int(self.entry_count)
        _nonnegative_exact_int(self.uncompressed_bytes)
        if self.status is not InspectionStatus.SAFE and (
            self.entry_count != 0 or self.uncompressed_bytes != 0
        ):
            fail_object_intake()


@dataclass(frozen=True, slots=True, repr=False)
class CsvInspectionRecord(_RedactedValue):
    status: InspectionStatus
    encoding: CsvEncoding | None
    row_count: int
    column_count: int
    max_cell_bytes: int
    formula_prefix_detected: bool

    def __post_init__(self) -> None:
        if (
            type(self.status) is not InspectionStatus
            or (self.encoding is not None and type(self.encoding) is not CsvEncoding)
            or type(self.formula_prefix_detected) is not bool
        ):
            fail_object_intake()
        _nonnegative_exact_int(self.row_count)
        _nonnegative_exact_int(self.column_count)
        _nonnegative_exact_int(self.max_cell_bytes)
        if self.status is InspectionStatus.SAFE and (
            self.encoding is not CsvEncoding.UTF_8
            or self.row_count == 0
            or self.column_count == 0
            or self.formula_prefix_detected
        ):
            fail_object_intake()
        if self.status not in {InspectionStatus.SAFE, InspectionStatus.REJECTED} and (
            self.encoding is not None
            or self.row_count != 0
            or self.column_count != 0
            or self.max_cell_bytes != 0
            or self.formula_prefix_detected
        ):
            fail_object_intake()


@dataclass(frozen=True, slots=True, repr=False)
class PrivacyInspectionRecord(_RedactedValue):
    status: InspectionStatus
    privacy_class: IntakePrivacyClass

    def __post_init__(self) -> None:
        if (
            type(self.status) is not InspectionStatus
            or type(self.privacy_class) is not IntakePrivacyClass
        ):
            fail_object_intake()


@dataclass(frozen=True, slots=True, repr=False)
class ObjectInspectionReport(_RedactedValue):
    magic: MagicInspectionRecord
    archive: ArchiveInspectionRecord
    csv: CsvInspectionRecord
    privacy: PrivacyInspectionRecord

    def __post_init__(self) -> None:
        if (
            type(self.magic) is not MagicInspectionRecord
            or type(self.archive) is not ArchiveInspectionRecord
            or type(self.csv) is not CsvInspectionRecord
            or type(self.privacy) is not PrivacyInspectionRecord
        ):
            fail_object_intake()


@dataclass(frozen=True, slots=True, repr=False)
class ObjectIntakeResult(_RedactedValue):
    descriptor: IntakeDescriptor
    quarantine: QuarantineRecord
    inspection: ObjectInspectionReport
    malware: MalwareInspectionRecord
    duplicate: DuplicateInspectionRecord
    outcome: IntakeOutcome

    def __post_init__(self) -> None:
        if (
            type(self.descriptor) is not IntakeDescriptor
            or type(self.quarantine) is not QuarantineRecord
            or type(self.inspection) is not ObjectInspectionReport
            or type(self.malware) is not MalwareInspectionRecord
            or type(self.duplicate) is not DuplicateInspectionRecord
            or type(self.outcome) is not IntakeOutcome
            or self.quarantine.intake_id != self.descriptor.intake_id
            or self.quarantine.received_bytes != self.descriptor.declared_size
            or self.quarantine.sealed_sha256 != self.descriptor.declared_sha256
            or self.quarantine.status is not QuarantineStatus.DISPOSITION_RECORDED
            or self.quarantine.disposition
            is not QuarantineDisposition.CLEAN_QUARANTINED
            or self.malware.status is not MalwareStatus.CLEAN
            or self.duplicate.status
            not in {DuplicateStatus.NEW, DuplicateStatus.EXACT_DUPLICATE}
            or self.inspection.magic.status is not InspectionStatus.SAFE
            or self.inspection.magic.declared_media_type != self.descriptor.media_type
            or self.inspection.archive.status
            not in {InspectionStatus.SAFE, InspectionStatus.NOT_APPLICABLE}
            or self.inspection.csv.status
            not in {InspectionStatus.SAFE, InspectionStatus.NOT_APPLICABLE}
            or self.inspection.privacy.status is not InspectionStatus.SAFE
            or self.inspection.privacy.privacy_class
            is not self.descriptor.privacy_class
            or self.outcome is not IntakeOutcome.CLEAN_QUARANTINED
        ):
            fail_object_intake()


__all__ = [
    "ArchiveInspectionRecord",
    "CsvEncoding",
    "CsvInspectionRecord",
    "DuplicateInspectionRecord",
    "DuplicateStatus",
    "InspectionStatus",
    "IntakeDescriptor",
    "IntakeOutcome",
    "IntakePolicy",
    "IntakePrivacyClass",
    "MagicInspectionRecord",
    "MalwareInspectionRecord",
    "MalwareStatus",
    "MediaType",
    "ObjectInspectionReport",
    "ObjectIntakeFailure",
    "ObjectIntakeFailureCode",
    "ObjectIntakeKind",
    "ObjectIntakeResult",
    "PrivacyInspectionRecord",
    "QuarantineDisposition",
    "QuarantineRecord",
    "QuarantineStatus",
    "SafeLeafName",
    "Sha256Digest",
    "fail_object_intake",
]
