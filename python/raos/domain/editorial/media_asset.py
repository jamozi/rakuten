"""Closed, recorded-only media validation values for ST-0808."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Mapping, NoReturn, SupportsIndex, cast
from uuid import UUID

from raos.domain.editorial.article_lifecycle import (
    ArticleVersionState,
    BodySha256,
    SourcePacketVerification,
    VersionSnapshot,
)
from raos.domain.ops.object_intake import (
    IntakeOutcome,
    ObjectIntakeKind,
    ObjectIntakeResult,
    QuarantineDisposition,
    QuarantineStatus,
    Sha256Digest,
)


_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}", re.ASCII)


class MediaAssetFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    LOCAL_VALIDATION_UNAVAILABLE = "LOCAL_VALIDATION_UNAVAILABLE"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"


@dataclass(frozen=True, slots=True, repr=False)
class MediaAssetFailure(RuntimeError):
    """Stable failure that never retains rejected values or collaborators."""

    code: MediaAssetFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not MediaAssetFailureCode:
            raise TypeError("invalid media asset failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"MediaAssetFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("media asset failure serialization is not supported")


def fail_media_asset(
    code: MediaAssetFailureCode = MediaAssetFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise MediaAssetFailure(code) from None


def _fail(field: str) -> None:
    del field
    fail_media_asset()


def _exact_text(value: object, expected: str, field: str) -> str:
    if type(value) is not str or value != expected:
        _fail(field)
    return cast(str, value)


def _uuid(value: object, field: str) -> UUID:
    if type(value) is not UUID or value.int == 0:
        _fail(field)
    return cast(UUID, value)


def _positive_int(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        _fail(field)
    return cast(int, value)


def _digest(value: object, field: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _fail(field)
    return cast(str, value)


def _exact_identity(value: object, expected: object, field: str) -> None:
    if type(value) is not type(expected) or value is not expected:
        _fail(field)


def _none(value: object, field: str) -> None:
    if value is not None:
        _fail(field)


class RecordedRightsDisposition(StrEnum):
    """Closed synthetic fixture dispositions; not a legal-rights model."""

    UNKNOWN = "UNKNOWN"
    ADMIN_REFERENCE_ELIGIBLE = "ADMIN_REFERENCE_ELIGIBLE"
    FORBIDDEN = "FORBIDDEN"
    EXCEPTION_ONLY = "EXCEPTION_ONLY"


class MediaAssetVisibility(StrEnum):
    HIDDEN_UNKNOWN_RIGHTS = "HIDDEN_UNKNOWN_RIGHTS"
    HIDDEN_POLICY = "HIDDEN_POLICY"
    ADMIN_ONLY_REFERENCE = "ADMIN_ONLY_REFERENCE"


class MediaAssetDecision(StrEnum):
    NOT_READY = "NOT_READY"


class MediaAssetMode(StrEnum):
    RECORDED_TEST_ONLY = "RECORDED_TEST_ONLY"


class MediaAssetExecution(StrEnum):
    RECORDED_ONLY = "RECORDED_ONLY"
    NOT_EXECUTED = "NOT_EXECUTED"


@dataclass(frozen=True, slots=True)
class CleanQuarantinedMediaCandidate:
    """Lossless facts already observed by the committed intake boundary."""

    intake_id: UUID
    site_id: UUID
    object_kind: str
    quarantine_disposition: str
    declared_sha256: str
    sealed_sha256: str
    declared_size: int
    sealed_size: int

    def __post_init__(self) -> None:
        _uuid(self.intake_id, "intake_id")
        _uuid(self.site_id, "site_id")
        _exact_text(self.object_kind, "MEDIA_ASSET", "object_kind")
        _exact_text(
            self.quarantine_disposition,
            "CLEAN_QUARANTINED",
            "quarantine_disposition",
        )
        declared = _digest(self.declared_sha256, "declared_sha256")
        sealed = _digest(self.sealed_sha256, "sealed_sha256")
        if declared != sealed:
            _fail("sealed_sha256")
        declared_size = _positive_int(self.declared_size, "declared_size")
        sealed_size = _positive_int(self.sealed_size, "sealed_size")
        if declared_size != sealed_size:
            _fail("sealed_size")

    @property
    def fingerprint(self) -> str:
        payload = {
            "declared_sha256": self.declared_sha256,
            "declared_size": self.declared_size,
            "intake_id": str(self.intake_id),
            "object_kind": self.object_kind,
            "quarantine_disposition": self.quarantine_disposition,
            "sealed_sha256": self.sealed_sha256,
            "sealed_size": self.sealed_size,
            "site_id": str(self.site_id),
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class MediaValidationRequest:
    candidate: CleanQuarantinedMediaCandidate
    version_snapshot: VersionSnapshot
    rights_disposition: RecordedRightsDisposition | None

    def __post_init__(self) -> None:
        if type(self.candidate) is not CleanQuarantinedMediaCandidate:
            _fail("candidate")
        if type(self.version_snapshot) is not VersionSnapshot:
            _fail("version_snapshot")
        if (
            self.rights_disposition is not None
            and type(self.rights_disposition) is not RecordedRightsDisposition
        ):
            _fail("rights_disposition")


def candidate_from_intake(
    intake_result: ObjectIntakeResult,
) -> CleanQuarantinedMediaCandidate:
    """Project only the committed clean-quarantine facts; never content bytes."""

    if (
        type(intake_result) is not ObjectIntakeResult
        or intake_result.descriptor.kind is not ObjectIntakeKind.MEDIA_ASSET
        or intake_result.outcome is not IntakeOutcome.CLEAN_QUARANTINED
        or intake_result.quarantine.status is not QuarantineStatus.DISPOSITION_RECORDED
        or intake_result.quarantine.disposition
        is not QuarantineDisposition.CLEAN_QUARANTINED
        or intake_result.quarantine.intake_id != intake_result.descriptor.intake_id
        or intake_result.quarantine.received_bytes
        != intake_result.descriptor.declared_size
        or intake_result.quarantine.sealed_sha256
        != intake_result.descriptor.declared_sha256
    ):
        _fail("intake_result")
    sealed = intake_result.quarantine.sealed_sha256
    disposition = intake_result.quarantine.disposition
    if type(sealed) is not Sha256Digest:
        _fail("intake_result")
    if type(disposition) is not QuarantineDisposition:
        _fail("intake_result")
    return CleanQuarantinedMediaCandidate(
        intake_id=intake_result.descriptor.intake_id,
        site_id=intake_result.descriptor.site_id,
        object_kind=intake_result.descriptor.kind.value,
        quarantine_disposition=cast(QuarantineDisposition, disposition).value,
        declared_sha256=intake_result.descriptor.declared_sha256.value,
        sealed_sha256=cast(Sha256Digest, sealed).value,
        declared_size=intake_result.descriptor.declared_size,
        sealed_size=intake_result.quarantine.received_bytes,
    )


def validate_version_snapshot(value: VersionSnapshot) -> VersionSnapshot:
    if (
        type(value) is not VersionSnapshot
        or value.state is not ArticleVersionState.DRAFT
        or value.source_packet_verification is not SourcePacketVerification.NOT_VERIFIED
        or value.body_sha256 != BodySha256.of(value.content_ast)
        or value.submitted_at is not None
        or value.reviewed_at is not None
        or value.approved_at is not None
        or value.published_at is not None
    ):
        _fail("version_snapshot")
    return value


@dataclass(frozen=True, slots=True)
class MediaValidationCommand:
    mode: MediaAssetMode
    intake_result: ObjectIntakeResult
    version_snapshot: VersionSnapshot
    rights_disposition: RecordedRightsDisposition | None

    def __post_init__(self) -> None:
        _exact_identity(self.mode, MediaAssetMode.RECORDED_TEST_ONLY, "mode")
        candidate_from_intake(self.intake_result)
        validate_version_snapshot(self.version_snapshot)
        if (
            self.rights_disposition is not None
            and type(self.rights_disposition) is not RecordedRightsDisposition
        ):
            _fail("rights_disposition")

    @property
    def request(self) -> MediaValidationRequest:
        return MediaValidationRequest(
            candidate=candidate_from_intake(self.intake_result),
            version_snapshot=self.version_snapshot,
            rights_disposition=self.rights_disposition,
        )


@dataclass(frozen=True, slots=True)
class RecordedMediaValidationObservation:
    candidate_fingerprint: str
    rights_disposition: RecordedRightsDisposition | None
    visibility: MediaAssetVisibility
    asset_id: UUID | None

    def __post_init__(self) -> None:
        _digest(self.candidate_fingerprint, "candidate_fingerprint")
        if (
            self.rights_disposition is not None
            and type(self.rights_disposition) is not RecordedRightsDisposition
        ):
            _fail("rights_disposition")
        if type(self.visibility) is not MediaAssetVisibility:
            _fail("visibility")
        if self.visibility is MediaAssetVisibility.ADMIN_ONLY_REFERENCE:
            if (
                self.rights_disposition
                is not RecordedRightsDisposition.ADMIN_REFERENCE_ELIGIBLE
            ):
                _fail("visibility")
            _uuid(self.asset_id, "asset_id")
        elif self.asset_id is not None:
            _fail("asset_id")


@dataclass(frozen=True, slots=True)
class AdminOnlyMediaAssetReference:
    asset_id: UUID
    visibility: MediaAssetVisibility = MediaAssetVisibility.ADMIN_ONLY_REFERENCE

    def __post_init__(self) -> None:
        _uuid(self.asset_id, "asset_id")
        if self.visibility is not MediaAssetVisibility.ADMIN_ONLY_REFERENCE:
            _fail("visibility")


@dataclass(frozen=True, slots=True)
class MediaValidationResult:
    intake_result: ObjectIntakeResult
    candidate: CleanQuarantinedMediaCandidate
    version_snapshot: VersionSnapshot
    visibility: MediaAssetVisibility
    reference: AdminOnlyMediaAssetReference | None
    raw_artifact_ref: None
    decision: MediaAssetDecision
    validation: MediaAssetExecution
    public_rendering: bool
    renderer_input: None
    approval: None
    publication: None
    execution_markers: Mapping[str, str]

    def __post_init__(self) -> None:
        if (
            type(self.intake_result) is not ObjectIntakeResult
            or candidate_from_intake(self.intake_result) != self.candidate
            or type(self.candidate) is not CleanQuarantinedMediaCandidate
        ):
            _fail("candidate")
        if type(self.version_snapshot) is not VersionSnapshot:
            _fail("version_snapshot")
        if type(self.visibility) is not MediaAssetVisibility:
            _fail("visibility")
        if self.visibility is MediaAssetVisibility.ADMIN_ONLY_REFERENCE:
            if type(self.reference) is not AdminOnlyMediaAssetReference:
                _fail("reference")
        elif self.reference is not None:
            _fail("reference")
        _none(self.raw_artifact_ref, "raw_artifact_ref")
        _exact_identity(self.decision, MediaAssetDecision.NOT_READY, "decision")
        if self.validation is not MediaAssetExecution.RECORDED_ONLY:
            _fail("validation")
        if type(self.public_rendering) is not bool or self.public_rendering:
            _fail("public_rendering")
        _none(self.renderer_input, "renderer_input")
        _none(self.approval, "approval")
        _none(self.publication, "publication")
        if type(self.execution_markers) is not MappingProxyType:
            _fail("execution_markers")


def execution_markers() -> Mapping[str, str]:
    """Return immutable boundary markers; none assert execution or readiness."""

    return MappingProxyType(
        {
            "mode": "RECORDED_TEST_ONLY",
            "storage": "NOT_EXECUTED",
            "source_verification": "NOT_EXECUTED",
            "license_verification": "NOT_EXECUTED",
            "article_mutation": "NOT_EXECUTED",
            "formal_validation": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        }
    )
