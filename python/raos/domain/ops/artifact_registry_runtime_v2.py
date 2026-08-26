"""Recorded-local durable raw artifact values for ST-0601 V2.

The values in this module bind one exact ST-0502 raw archive receipt to an
immutable, versioned local object record.  They carry no provider, credential,
retention, deletion, publication, or external storage authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex
from uuid import UUID

from raos.domain.ops.enums import ObjectArtifactArtifactKind
from raos.domain.ops.ids import ObjectArtifactId
from raos.domain.shared.identity import deterministic_uuid7


ARTIFACT_REGISTRY_SCHEMA_VERSION_V2 = "ST0601_RECORDED_ARTIFACT_REGISTRY_V2"
ARTIFACT_REGISTRY_GENESIS_SHA256_V2 = "0" * 64
ARTIFACT_REGISTRY_BUCKET_V2 = "raos-raw"
ARTIFACT_REGISTRY_SOURCE_SYSTEM_V2 = "RAKUTEN_ITEM_SEARCH_20260701"
ARTIFACT_REGISTRY_CONTENT_TYPE_V2 = "application/json"
ARTIFACT_REGISTRY_MAX_BYTES_V2 = 2 * 1024 * 1024
ARTIFACT_REGISTRY_EXTERNAL_ACTION_COUNT_V2 = 0
ARTIFACT_REGISTRY_PROVIDER_ACTION_COUNT_V2 = 0
ARTIFACT_REGISTRY_PUBLICATION_ACTION_COUNT_V2 = 0

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SOURCE_LOGICAL_KEY = re.compile(r"sha256/[0-9a-f]{2}/[0-9a-f]{64}\Z", re.ASCII)
_REGISTRY_LOGICAL_KEY = re.compile(
    r"raw/rakuten-item-search/[0-9a-f]{2}/[0-9a-f]{64}/page-[0-9]{3}\.json\Z",
    re.ASCII,
)
_MAX_VERSION = (1 << 63) - 1
_ARTIFACT_ID_NAMESPACE = UUID("9f438c5e-8e8f-4f49-91ec-e52280911467")
_REDACTED = "<redacted-artifact-registry-runtime-v2>"


class ArtifactRegistryRuntimeFailureCodeV2(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_INTEGRITY = "SOURCE_INTEGRITY"
    STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
    SCHEMA_DRIFT = "SCHEMA_DRIFT"
    TAMPER_DETECTED = "TAMPER_DETECTED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    COMMIT_KNOWN_ROLLBACK = "COMMIT_KNOWN_ROLLBACK"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"
    RECOVERY_NOT_FOUND = "RECOVERY_NOT_FOUND"


class ArtifactRegistryRuntimeModeV2(str, Enum):
    RECORDED_LOCAL = "RECORDED_LOCAL"


class ArtifactRegistryRetentionStateV2(str, Enum):
    OD_014_UNRESOLVED = "OD_014_UNRESOLVED"


class ArtifactRegistryStorageProviderV2(str, Enum):
    RECORDED_LOCAL_SQLITE = "RECORDED_LOCAL_SQLITE"


class _RedactedValue:
    __slots__ = ()

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("artifact registry runtime values cannot be serialized")


class ArtifactRegistryRuntimeFailureV2(RuntimeError):
    """Closed failure that remains compatible with traceback assignment."""

    __slots__ = ("_code",)

    def __init__(self, code: ArtifactRegistryRuntimeFailureCodeV2) -> None:
        if type(code) is not ArtifactRegistryRuntimeFailureCodeV2:
            raise TypeError("invalid artifact registry runtime failure code")
        super().__init__(code.value)
        self._code = code

    @property
    def code(self) -> ArtifactRegistryRuntimeFailureCodeV2:
        return self._code

    def __repr__(self) -> str:
        return f"ArtifactRegistryRuntimeFailureV2(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("artifact registry runtime failures cannot be serialized")


def fail_artifact_registry_runtime_v2(
    code: ArtifactRegistryRuntimeFailureCodeV2 = (
        ArtifactRegistryRuntimeFailureCodeV2.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise ArtifactRegistryRuntimeFailureV2(code) from None


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_artifact_registry_runtime_v2()
    return value


def _positive_integer(value: object, *, maximum: int = _MAX_VERSION) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        fail_artifact_registry_runtime_v2()
    return value


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_artifact_registry_runtime_v2()
    return value


def utc_text_v2(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_json_bytes_v2(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except TypeError, ValueError, UnicodeError:
        fail_artifact_registry_runtime_v2()


def canonical_sha256_v2(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes_v2(value)).hexdigest()


def registry_logical_key_v2(*, request_fingerprint: str, page: int) -> str:
    digest = _sha256(request_fingerprint)
    page_number = _positive_integer(page, maximum=100)
    return f"raw/rakuten-item-search/{digest[:2]}/{digest}/page-{page_number:03d}.json"


@dataclass(frozen=True, slots=True, repr=False)
class ArtifactSourceProvenanceV2(_RedactedValue):
    source_system: str
    source_receipt_id: UUID
    source_artifact_sha256: str
    source_artifact_version: int
    source_logical_key: str
    source_request_fingerprint: str
    source_page: int
    acquired_at: datetime

    def __post_init__(self) -> None:
        digest = _sha256(self.source_artifact_sha256)
        if (
            self.source_system != ARTIFACT_REGISTRY_SOURCE_SYSTEM_V2
            or type(self.source_receipt_id) is not UUID
            or self.source_receipt_id.int == 0
            or type(self.source_logical_key) is not str
            or _SOURCE_LOGICAL_KEY.fullmatch(self.source_logical_key) is None
            or self.source_logical_key != f"sha256/{digest[:2]}/{digest}"
        ):
            fail_artifact_registry_runtime_v2()
        _positive_integer(self.source_artifact_version)
        _sha256(self.source_request_fingerprint)
        _positive_integer(self.source_page, maximum=100)
        _utc(self.acquired_at)

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "acquired_at": utc_text_v2(self.acquired_at),
            "source_artifact_sha256": self.source_artifact_sha256,
            "source_artifact_version": self.source_artifact_version,
            "source_logical_key": self.source_logical_key,
            "source_page": self.source_page,
            "source_receipt_id": str(self.source_receipt_id),
            "source_request_fingerprint": self.source_request_fingerprint,
            "source_system": self.source_system,
        }

    @property
    def fingerprint(self) -> str:
        return canonical_sha256_v2(self.canonical_material)

    def __repr__(self) -> str:
        return f"ArtifactSourceProvenanceV2({_REDACTED})"


@dataclass(frozen=True, slots=True, repr=False)
class ArtifactPutCandidateV2(_RedactedValue):
    artifact_kind: ObjectArtifactArtifactKind
    logical_key: str
    content_type: str
    byte_size: int
    sha256: str
    provenance: ArtifactSourceProvenanceV2

    def __post_init__(self) -> None:
        if (
            self.artifact_kind is not ObjectArtifactArtifactKind.RAW_PROVIDER_RESPONSE
            or self.content_type != ARTIFACT_REGISTRY_CONTENT_TYPE_V2
            or type(self.logical_key) is not str
            or _REGISTRY_LOGICAL_KEY.fullmatch(self.logical_key) is None
            or type(self.provenance) is not ArtifactSourceProvenanceV2
        ):
            fail_artifact_registry_runtime_v2()
        if self.logical_key != registry_logical_key_v2(
            request_fingerprint=self.provenance.source_request_fingerprint,
            page=self.provenance.source_page,
        ):
            fail_artifact_registry_runtime_v2()
        _positive_integer(self.byte_size, maximum=ARTIFACT_REGISTRY_MAX_BYTES_V2)
        digest = _sha256(self.sha256)
        if digest != self.provenance.source_artifact_sha256:
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.SOURCE_INTEGRITY
            )

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "artifact_kind": self.artifact_kind.value,
            "byte_size": self.byte_size,
            "content_type": self.content_type,
            "logical_key": self.logical_key,
            "provenance": self.provenance.canonical_material,
            "sha256": self.sha256,
        }

    @property
    def fingerprint(self) -> str:
        return canonical_sha256_v2(self.canonical_material)

    def __repr__(self) -> str:
        return f"ArtifactPutCandidateV2({_REDACTED})"


@dataclass(frozen=True, slots=True, repr=False)
class ArtifactPutCommandV2(_RedactedValue):
    operation_id: UUID
    candidate: ArtifactPutCandidateV2
    expected_latest_version: int | None

    def __post_init__(self) -> None:
        if (
            type(self.operation_id) is not UUID
            or self.operation_id.int == 0
            or type(self.candidate) is not ArtifactPutCandidateV2
        ):
            fail_artifact_registry_runtime_v2()
        if self.expected_latest_version is not None:
            _positive_integer(self.expected_latest_version)

    @property
    def request_sha256(self) -> str:
        return canonical_sha256_v2(
            {
                "candidate": self.candidate.canonical_material,
                "expected_latest_version": self.expected_latest_version,
            }
        )

    def __repr__(self) -> str:
        return f"ArtifactPutCommandV2({_REDACTED})"


def artifact_id_v2(
    *, candidate: ArtifactPutCandidateV2, artifact_version: int
) -> ObjectArtifactId:
    if type(candidate) is not ArtifactPutCandidateV2:
        fail_artifact_registry_runtime_v2()
    version = _positive_integer(artifact_version)
    material = canonical_json_bytes_v2(
        {
            "candidate": candidate.canonical_material,
            "artifact_version": version,
            "namespace": ARTIFACT_REGISTRY_SCHEMA_VERSION_V2,
        }
    )
    return ObjectArtifactId(deterministic_uuid7(_ARTIFACT_ID_NAMESPACE, material))


@dataclass(frozen=True, slots=True, repr=False)
class RecordedLocalArtifactRefV2(_RedactedValue):
    artifact_id: ObjectArtifactId
    storage_provider: ArtifactRegistryStorageProviderV2
    bucket_name: str
    object_key: str
    object_version: int
    sha256: str
    ref_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.artifact_id) is not ObjectArtifactId
            or self.storage_provider
            is not ArtifactRegistryStorageProviderV2.RECORDED_LOCAL_SQLITE
            or self.bucket_name != ARTIFACT_REGISTRY_BUCKET_V2
            or type(self.object_key) is not str
            or _REGISTRY_LOGICAL_KEY.fullmatch(self.object_key) is None
        ):
            fail_artifact_registry_runtime_v2()
        _positive_integer(self.object_version)
        _sha256(self.sha256)
        if _sha256(self.ref_sha256) != self.calculate_ref_sha256():
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED
            )

    def calculate_ref_sha256(self) -> str:
        return canonical_sha256_v2(
            {
                "artifact_id": str(self.artifact_id.value),
                "bucket_name": self.bucket_name,
                "object_key": self.object_key,
                "object_version": self.object_version,
                "sha256": self.sha256,
                "storage_provider": self.storage_provider.value,
            }
        )

    @classmethod
    def issue(
        cls,
        *,
        artifact_id: ObjectArtifactId,
        object_key: str,
        object_version: int,
        sha256: str,
    ) -> RecordedLocalArtifactRefV2:
        provisional = {
            "artifact_id": str(artifact_id.value),
            "bucket_name": ARTIFACT_REGISTRY_BUCKET_V2,
            "object_key": object_key,
            "object_version": object_version,
            "sha256": sha256,
            "storage_provider": (
                ArtifactRegistryStorageProviderV2.RECORDED_LOCAL_SQLITE.value
            ),
        }
        return cls(
            artifact_id=artifact_id,
            storage_provider=ArtifactRegistryStorageProviderV2.RECORDED_LOCAL_SQLITE,
            bucket_name=ARTIFACT_REGISTRY_BUCKET_V2,
            object_key=object_key,
            object_version=object_version,
            sha256=sha256,
            ref_sha256=canonical_sha256_v2(provisional),
        )

    def __repr__(self) -> str:
        return f"RecordedLocalArtifactRefV2({_REDACTED})"


def artifact_entry_sha256_v2(
    *,
    candidate: ArtifactPutCandidateV2,
    artifact_id: ObjectArtifactId,
    display_id: str,
    artifact_ref: RecordedLocalArtifactRefV2,
    sequence: int,
    previous_entry_sha256: str,
) -> str:
    if (
        type(candidate) is not ArtifactPutCandidateV2
        or type(artifact_id) is not ObjectArtifactId
        or type(display_id) is not str
        or type(artifact_ref) is not RecordedLocalArtifactRefV2
    ):
        fail_artifact_registry_runtime_v2()
    _positive_integer(sequence)
    _sha256(previous_entry_sha256)
    return canonical_sha256_v2(
        {
            "artifact_id": str(artifact_id.value),
            "artifact_ref_sha256": artifact_ref.ref_sha256,
            "candidate": candidate.canonical_material,
            "display_id": display_id,
            "previous_entry_sha256": previous_entry_sha256,
            "sequence": sequence,
        }
    )


def artifact_record_sha256_v2(
    *,
    candidate: ArtifactPutCandidateV2,
    artifact_id: ObjectArtifactId,
    display_id: str,
    artifact_ref: RecordedLocalArtifactRefV2,
    sequence: int,
    entry_sha256: str,
) -> str:
    if (
        type(candidate) is not ArtifactPutCandidateV2
        or type(artifact_id) is not ObjectArtifactId
        or type(display_id) is not str
        or type(artifact_ref) is not RecordedLocalArtifactRefV2
    ):
        fail_artifact_registry_runtime_v2()
    _positive_integer(sequence)
    _sha256(entry_sha256)
    return canonical_sha256_v2(
        {
            "artifact_id": str(artifact_id.value),
            "artifact_ref_sha256": artifact_ref.ref_sha256,
            "candidate_fingerprint": candidate.fingerprint,
            "display_id": display_id,
            "entry_sha256": entry_sha256,
            "record_type": "ST0601_PERSISTED_ARTIFACT_V2",
            "sequence": sequence,
        }
    )


@dataclass(frozen=True, slots=True, repr=False)
class PersistedArtifactV2(_RedactedValue):
    candidate: ArtifactPutCandidateV2
    artifact_id: ObjectArtifactId
    display_id: str
    artifact_ref: RecordedLocalArtifactRefV2
    sequence: int
    previous_entry_sha256: str
    entry_sha256: str
    record_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.candidate) is not ArtifactPutCandidateV2
            or type(self.artifact_id) is not ObjectArtifactId
            or type(self.display_id) is not str
            or self.display_id != f"OBJ-{self.artifact_id.value.hex[:20].upper()}"
            or type(self.artifact_ref) is not RecordedLocalArtifactRefV2
            or self.artifact_ref.artifact_id != self.artifact_id
            or self.artifact_ref.object_key != self.candidate.logical_key
            or self.artifact_ref.sha256 != self.candidate.sha256
        ):
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        _positive_integer(self.sequence)
        _sha256(self.previous_entry_sha256)
        if (
            _sha256(self.entry_sha256) != self.calculate_entry_sha256()
            or _sha256(self.record_sha256) != self.calculate_record_sha256()
        ):
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED
            )

    @property
    def artifact_version(self) -> int:
        return self.artifact_ref.object_version

    @property
    def retention_state(self) -> ArtifactRegistryRetentionStateV2:
        return ArtifactRegistryRetentionStateV2.OD_014_UNRESOLVED

    @property
    def retention_class(self) -> None:
        return None

    @property
    def retention_period(self) -> None:
        return None

    @property
    def object_storage_attestation(self) -> str:
        return "NOT_CLAIMED"

    def calculate_entry_sha256(self) -> str:
        return artifact_entry_sha256_v2(
            candidate=self.candidate,
            artifact_id=self.artifact_id,
            display_id=self.display_id,
            artifact_ref=self.artifact_ref,
            sequence=self.sequence,
            previous_entry_sha256=self.previous_entry_sha256,
        )

    def calculate_record_sha256(self) -> str:
        return artifact_record_sha256_v2(
            candidate=self.candidate,
            artifact_id=self.artifact_id,
            display_id=self.display_id,
            artifact_ref=self.artifact_ref,
            sequence=self.sequence,
            entry_sha256=self.entry_sha256,
        )

    def __repr__(self) -> str:
        return f"PersistedArtifactV2({_REDACTED})"


@dataclass(frozen=True, slots=True, repr=False)
class ArtifactPutReceiptV2(_RedactedValue):
    operation_id: UUID
    request_sha256: str
    artifact_id: ObjectArtifactId
    artifact_ref: RecordedLocalArtifactRefV2
    sequence: int
    entry_sha256: str
    replayed: bool

    def __post_init__(self) -> None:
        if (
            type(self.operation_id) is not UUID
            or self.operation_id.int == 0
            or type(self.artifact_id) is not ObjectArtifactId
            or type(self.artifact_ref) is not RecordedLocalArtifactRefV2
            or self.artifact_ref.artifact_id != self.artifact_id
            or type(self.replayed) is not bool
        ):
            fail_artifact_registry_runtime_v2()
        _sha256(self.request_sha256)
        _positive_integer(self.sequence)
        _sha256(self.entry_sha256)

    def __repr__(self) -> str:
        return f"ArtifactPutReceiptV2({_REDACTED})"


@dataclass(frozen=True, slots=True, repr=False)
class ArtifactReadbackV2(_RedactedValue):
    record: PersistedArtifactV2
    content: bytes

    def __post_init__(self) -> None:
        if (
            type(self.record) is not PersistedArtifactV2
            or type(self.content) is not bytes
        ):
            fail_artifact_registry_runtime_v2()
        if (
            len(self.content) != self.record.candidate.byte_size
            or hashlib.sha256(self.content).hexdigest() != self.record.candidate.sha256
        ):
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED
            )

    def __repr__(self) -> str:
        return f"ArtifactReadbackV2({_REDACTED})"


@dataclass(frozen=True, slots=True, repr=False)
class ArtifactRegistryCommitV2(_RedactedValue):
    record: PersistedArtifactV2
    receipt: ArtifactPutReceiptV2
    recovered_after_commit_ambiguity: bool

    def __post_init__(self) -> None:
        if (
            type(self.record) is not PersistedArtifactV2
            or type(self.receipt) is not ArtifactPutReceiptV2
            or type(self.recovered_after_commit_ambiguity) is not bool
            or self.record.artifact_id != self.receipt.artifact_id
            or self.record.artifact_ref != self.receipt.artifact_ref
            or self.record.sequence != self.receipt.sequence
            or self.record.entry_sha256 != self.receipt.entry_sha256
        ):
            fail_artifact_registry_runtime_v2(
                ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED
            )

    @property
    def external_action_count(self) -> int:
        return ARTIFACT_REGISTRY_EXTERNAL_ACTION_COUNT_V2

    @property
    def provider_action_count(self) -> int:
        return ARTIFACT_REGISTRY_PROVIDER_ACTION_COUNT_V2

    @property
    def publication_action_count(self) -> int:
        return ARTIFACT_REGISTRY_PUBLICATION_ACTION_COUNT_V2

    def __repr__(self) -> str:
        return f"ArtifactRegistryCommitV2({_REDACTED})"


__all__ = [
    "ARTIFACT_REGISTRY_BUCKET_V2",
    "ARTIFACT_REGISTRY_CONTENT_TYPE_V2",
    "ARTIFACT_REGISTRY_EXTERNAL_ACTION_COUNT_V2",
    "ARTIFACT_REGISTRY_GENESIS_SHA256_V2",
    "ARTIFACT_REGISTRY_MAX_BYTES_V2",
    "ARTIFACT_REGISTRY_PROVIDER_ACTION_COUNT_V2",
    "ARTIFACT_REGISTRY_PUBLICATION_ACTION_COUNT_V2",
    "ARTIFACT_REGISTRY_SCHEMA_VERSION_V2",
    "ARTIFACT_REGISTRY_SOURCE_SYSTEM_V2",
    "ArtifactPutCandidateV2",
    "ArtifactPutCommandV2",
    "ArtifactPutReceiptV2",
    "ArtifactReadbackV2",
    "ArtifactRegistryCommitV2",
    "ArtifactRegistryRetentionStateV2",
    "ArtifactRegistryRuntimeFailureCodeV2",
    "ArtifactRegistryRuntimeFailureV2",
    "ArtifactRegistryRuntimeModeV2",
    "ArtifactRegistryStorageProviderV2",
    "ArtifactSourceProvenanceV2",
    "PersistedArtifactV2",
    "RecordedLocalArtifactRefV2",
    "artifact_entry_sha256_v2",
    "artifact_id_v2",
    "artifact_record_sha256_v2",
    "canonical_json_bytes_v2",
    "canonical_sha256_v2",
    "fail_artifact_registry_runtime_v2",
    "registry_logical_key_v2",
    "utc_text_v2",
]
