"""Non-attesting, source-bound artifact registry reference values for ST-0601."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MIME = re.compile(
    r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}\Z",
    re.ASCII,
)
_OPAQUE_VERSION = re.compile(r"[!-~]{1,256}\Z", re.ASCII)
_SOURCE = re.compile(r"[A-Z0-9][A-Z0-9._:-]{0,127}\Z", re.ASCII)
_REDACTED = "<redacted-artifact-registry>"
_MAX_SYNTHETIC_BYTES = 8 * 1024 * 1024


class ArtifactKind(str, Enum):
    RAW_PROVIDER_RESPONSE = "raw_provider_response"
    RAW_PRIMARY_SOURCE = "raw_primary_source"
    SOURCE_SNAPSHOT = "source_snapshot"
    SOURCE_PACKET = "source_packet"
    AI_INPUT = "ai_input"
    AI_OUTPUT = "ai_output"
    PUBLICATION_SNAPSHOT = "publication_snapshot"
    REVENUE_ORIGINAL = "revenue_original"
    REVENUE_REJECTS = "revenue_rejects"
    AUDIT_EXPORT = "audit_export"
    QUALITY_REPORT = "quality_report"
    DIFF = "diff"
    IMPORT_REPORT = "import_report"
    OTHER = "other"


class RegistryIntent(str, Enum):
    REFERENCE_PLAN_ONLY = "REFERENCE_PLAN_ONLY"


class RegistryMode(str, Enum):
    RECORDED_TEST_ONLY = "RECORDED_TEST_ONLY"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class RegistryDecision(str, Enum):
    NOT_READY = "NOT_READY"
    REJECTED = "REJECTED"


class IntegrityDecision(str, Enum):
    RECORDED_MATCH = "RECORDED_MATCH"
    TAMPER_DETECTED = "TAMPER_DETECTED"


class RegistryBlocker(str, Enum):
    RETENTION_UNRESOLVED = "RETENTION_UNRESOLVED"
    OBJECT_STORAGE_NOT_EXECUTED = "OBJECT_STORAGE_NOT_EXECUTED"
    IMMUTABILITY_NOT_ATTESTED = "IMMUTABILITY_NOT_ATTESTED"
    PERSISTENCE_BOUNDARY_UNAVAILABLE = "PERSISTENCE_BOUNDARY_UNAVAILABLE"
    TAMPER_DETECTED = "TAMPER_DETECTED"


MATCHING_BLOCKERS: tuple[RegistryBlocker, ...] = (
    RegistryBlocker.RETENTION_UNRESOLVED,
    RegistryBlocker.OBJECT_STORAGE_NOT_EXECUTED,
    RegistryBlocker.IMMUTABILITY_NOT_ATTESTED,
    RegistryBlocker.PERSISTENCE_BOUNDARY_UNAVAILABLE,
)


class ArtifactRegistryFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    OBSERVATION_UNAVAILABLE = "OBSERVATION_UNAVAILABLE"
    OBSERVATION_MISMATCH = "OBSERVATION_MISMATCH"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("artifact registry serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class ArtifactRegistryFailure(RuntimeError):
    code: ArtifactRegistryFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not ArtifactRegistryFailureCode:
            raise TypeError("invalid artifact registry failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ArtifactRegistryFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("artifact registry failure serialization is not supported")


def fail_artifact_registry(
    code: ArtifactRegistryFailureCode = ArtifactRegistryFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise ArtifactRegistryFailure(code) from None


def _exact_size(value: object) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_SYNTHETIC_BYTES:
        fail_artifact_registry()
    return value


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_artifact_registry()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_artifact_registry()

    @classmethod
    def of(cls, content: bytes) -> Sha256Digest:
        if type(content) is not bytes:
            fail_artifact_registry()
        _exact_size(len(content))
        return cls(hashlib.sha256(content).hexdigest())


def _safe_object_key(value: object) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 1024
        or value.startswith("/")
        or value.endswith("/")
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        fail_artifact_registry()
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        fail_artifact_registry()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class ObjectLocationCandidate(_RedactedValue):
    scheme: str
    bucket: str
    object_key: str
    version_id: str

    def __post_init__(self) -> None:
        if (
            type(self.scheme) is not str
            or self.scheme != "s3"
            or type(self.bucket) is not str
            or self.bucket != "raos-raw"
            or type(self.version_id) is not str
            or _OPAQUE_VERSION.fullmatch(self.version_id) is None
        ):
            fail_artifact_registry()
        _safe_object_key(self.object_key)

    @property
    def canonical_key(self) -> tuple[str, str, str, str]:
        return (self.scheme, self.bucket, self.object_key, self.version_id)


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True, slots=True, repr=False)
class ArtifactProvenance(_RedactedValue):
    kind: ArtifactKind
    source: str
    acquired_at: datetime
    content_type: str
    byte_size: int
    digest: Sha256Digest
    location: ObjectLocationCandidate
    intent: RegistryIntent

    def __post_init__(self) -> None:
        if (
            type(self.kind) is not ArtifactKind
            or type(self.source) is not str
            or _SOURCE.fullmatch(self.source) is None
            or type(self.content_type) is not str
            or _MIME.fullmatch(self.content_type) is None
            or type(self.digest) is not Sha256Digest
            or type(self.location) is not ObjectLocationCandidate
            or self.intent is not RegistryIntent.REFERENCE_PLAN_ONLY
        ):
            fail_artifact_registry()
        _utc(self.acquired_at)
        _exact_size(self.byte_size)

    @property
    def canonical_json(self) -> bytes:
        return _canonical_bytes(
            {
                "acquired_at": self.acquired_at.isoformat().replace("+00:00", "Z"),
                "bucket": self.location.bucket,
                "byte_size": self.byte_size,
                "content_type": self.content_type,
                "digest": self.digest.value,
                "intent": self.intent.value,
                "kind": self.kind.value,
                "object_key": self.location.object_key,
                "scheme": self.location.scheme,
                "source": self.source,
                "version_id": self.location.version_id,
            }
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class ArtifactObservation(_RedactedValue):
    candidate_fingerprint: str
    kind: ArtifactKind
    source: str
    acquired_at: datetime
    content_type: str
    byte_size: int
    digest: Sha256Digest
    location: ObjectLocationCandidate
    storage_execution: ExecutionStatus
    read_execution: ExecutionStatus
    write_execution: ExecutionStatus
    roundtrip_execution: ExecutionStatus
    attestation_execution: ExecutionStatus

    def __post_init__(self) -> None:
        if (
            type(self.candidate_fingerprint) is not str
            or _SHA256.fullmatch(self.candidate_fingerprint) is None
            or type(self.kind) is not ArtifactKind
            or type(self.source) is not str
            or _SOURCE.fullmatch(self.source) is None
            or type(self.content_type) is not str
            or _MIME.fullmatch(self.content_type) is None
            or type(self.digest) is not Sha256Digest
            or type(self.location) is not ObjectLocationCandidate
            or any(
                status is not ExecutionStatus.NOT_EXECUTED
                for status in (
                    self.storage_execution,
                    self.read_execution,
                    self.write_execution,
                    self.roundtrip_execution,
                    self.attestation_execution,
                )
            )
        ):
            fail_artifact_registry()
        _utc(self.acquired_at)
        _exact_size(self.byte_size)

    @classmethod
    def from_synthetic(
        cls,
        *,
        candidate: ArtifactProvenance,
        content: bytes,
    ) -> ArtifactObservation:
        if type(candidate) is not ArtifactProvenance or type(content) is not bytes:
            fail_artifact_registry()
        digest = Sha256Digest.of(content)
        return cls(
            candidate_fingerprint=candidate.fingerprint,
            kind=candidate.kind,
            source=candidate.source,
            acquired_at=candidate.acquired_at,
            content_type=candidate.content_type,
            byte_size=len(content),
            digest=digest,
            location=candidate.location,
            storage_execution=ExecutionStatus.NOT_EXECUTED,
            read_execution=ExecutionStatus.NOT_EXECUTED,
            write_execution=ExecutionStatus.NOT_EXECUTED,
            roundtrip_execution=ExecutionStatus.NOT_EXECUTED,
            attestation_execution=ExecutionStatus.NOT_EXECUTED,
        )

    @property
    def canonical_json(self) -> bytes:
        return _canonical_bytes(
            {
                "acquired_at": self.acquired_at.isoformat().replace("+00:00", "Z"),
                "attestation_execution": self.attestation_execution.value,
                "bucket": self.location.bucket,
                "byte_size": self.byte_size,
                "candidate_fingerprint": self.candidate_fingerprint,
                "content_type": self.content_type,
                "digest": self.digest.value,
                "kind": self.kind.value,
                "object_key": self.location.object_key,
                "read_execution": self.read_execution.value,
                "roundtrip_execution": self.roundtrip_execution.value,
                "scheme": self.location.scheme,
                "source": self.source,
                "storage_execution": self.storage_execution.value,
                "version_id": self.location.version_id,
                "write_execution": self.write_execution.value,
            }
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class ArtifactRegistryReferencePlan(_RedactedValue):
    classification: str
    decision: RegistryDecision
    integrity: IntegrityDecision
    candidate_fingerprint: str
    observation_fingerprint: str
    artifact_id: None
    artifact_ref: None
    retention: None
    storage_execution: ExecutionStatus
    read_execution: ExecutionStatus
    write_execution: ExecutionStatus
    roundtrip_execution: ExecutionStatus
    attestation_execution: ExecutionStatus
    persistence_execution: ExecutionStatus
    actions: tuple[()]
    blockers: tuple[RegistryBlocker, ...]

    def __post_init__(self) -> None:
        if (
            type(self.classification) is not str
            or self.classification
            != "SOURCE_BOUND_RECORDED_NON_ATTESTING_ARTIFACT_REGISTRY_REFERENCE_PLAN"
            or type(self.decision) is not RegistryDecision
            or type(self.integrity) is not IntegrityDecision
            or type(self.candidate_fingerprint) is not str
            or _SHA256.fullmatch(self.candidate_fingerprint) is None
            or type(self.observation_fingerprint) is not str
            or _SHA256.fullmatch(self.observation_fingerprint) is None
            or self.artifact_id is not None
            or self.artifact_ref is not None
            or self.retention is not None
            or any(
                status is not ExecutionStatus.NOT_EXECUTED
                for status in (
                    self.storage_execution,
                    self.read_execution,
                    self.write_execution,
                    self.roundtrip_execution,
                    self.attestation_execution,
                    self.persistence_execution,
                )
            )
            or type(self.actions) is not tuple
            or self.actions
            or type(self.blockers) is not tuple
        ):
            fail_artifact_registry()
        matching = (
            self.decision is RegistryDecision.NOT_READY
            and self.integrity is IntegrityDecision.RECORDED_MATCH
            and self.blockers == MATCHING_BLOCKERS
        )
        rejected = (
            self.decision is RegistryDecision.REJECTED
            and self.integrity is IntegrityDecision.TAMPER_DETECTED
            and self.blockers == (RegistryBlocker.TAMPER_DETECTED,)
        )
        if not (matching or rejected):
            fail_artifact_registry()


__all__ = [
    "ArtifactKind",
    "ArtifactObservation",
    "ArtifactProvenance",
    "ArtifactRegistryFailure",
    "ArtifactRegistryFailureCode",
    "ArtifactRegistryReferencePlan",
    "ExecutionStatus",
    "IntegrityDecision",
    "MATCHING_BLOCKERS",
    "ObjectLocationCandidate",
    "RegistryBlocker",
    "RegistryDecision",
    "RegistryIntent",
    "RegistryMode",
    "Sha256Digest",
    "fail_artifact_registry",
]
