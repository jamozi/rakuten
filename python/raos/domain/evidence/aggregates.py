"""Explicit EVIDENCE relation states and aggregate compositions for ST-0308."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
import re
from typing import ClassVar, NoReturn
from uuid import UUID

from raos.domain.ai.ids import (
    AiAttemptId,
)
from raos.domain.catalog.ids import (
    CanonicalProductId,
    OfferId,
    ProviderEndpointId,
)
from raos.domain.editorial.ids import (
    ArticleBlockId,
    ArticlePlanId,
    ArticleVersionId,
)
from raos.domain.evidence.enums import (
    ClaimClaimType,
    ClaimCriticality,
    ClaimEvidenceLinkSupportType,
    ClaimSupportStatus,
    FactDerivationDerivationRole,
    FactFactKind,
    FactSubjectType,
    FirstHandExperienceAssetRole,
    FirstHandExperienceStatus,
    SourceAuthorityLevel,
    SourcePacketFactUsageRole,
    SourcePacketPacketType,
    SourcePacketProductProductRole,
    SourcePacketStatus,
    SourcePacketVersionStatus,
    SourceSnapshotValidationStatus,
    SourceSourceType,
    SourceStatus,
)
from raos.domain.evidence.ids import (
    ClaimId,
    FactId,
    FirstHandExperienceRecordId,
    SourceId,
    SourcePacketId,
    SourcePacketVersionId,
    SourceSnapshotId,
)
from raos.domain.evidence.values import (
    FactLocatorJson,
    FactValueJsonJson,
    FirstHandExperienceRecordEnvironmentJson,
    FirstHandExperienceRecordProductVariantIdentityJson,
    SourceMetadataJson,
)
from raos.domain.iam.ids import (
    PrincipalId,
)
from raos.domain.ops.ids import (
    JobId,
    ObjectArtifactId,
)
from raos.domain.shared.identity import (
    SubjectId,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    Sha256Digest,
    UriReference,
)
from raos.domain.shared.events import DomainEvent
from raos.domain.shared.identity import EntityId
from raos.domain.shared.persistence import PendingEventBuffer


_MAX_BIGINT = (1 << 63) - 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_GIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)


def _invalid() -> NoReturn:
    raise ValueError("INVALID_EVIDENCE_PERSISTENCE_VALUE") from None


def _order_value(value: object) -> object:
    if isinstance(value, EntityId):
        return value.value.int
    if isinstance(value, Enum):
        return value.value
    if type(value) is AwareUtcDateTime:
        return value.value
    return value


@dataclass(frozen=True, slots=True, repr=False)
class ClaimState:
    """Exact scalar state for relation evidence.claim."""

    RELATION: ClassVar[str] = "evidence.claim"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_evidence_claim_criticality",
        "ck_evidence_claim_support",
        "ck_evidence_claim_type",
    )
    id: ClaimId
    display_id: str
    article_version_id: ArticleVersionId
    block_id: ArticleBlockId | None
    claim_key: str
    claim_type: ClaimClaimType
    claim_text: str
    criticality: ClaimCriticality
    support_status: ClaimSupportStatus
    generated_by_ai_attempt_id: AiAttemptId | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ClaimId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.article_version_id) is not ArticleVersionId:
            _invalid()
        if self.block_id is not None and (type(self.block_id) is not ArticleBlockId):
            _invalid()
        if type(self.claim_key) is not str:
            _invalid()
        if type(self.claim_type) is not ClaimClaimType:
            _invalid()
        if type(self.claim_text) is not str:
            _invalid()
        if type(self.criticality) is not ClaimCriticality:
            _invalid()
        if type(self.support_status) is not ClaimSupportStatus:
            _invalid()
        if self.generated_by_ai_attempt_id is not None and (
            type(self.generated_by_ai_attempt_id) is not AiAttemptId
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "ClaimState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ClaimEvidenceLink:
    """Exact scalar state for relation evidence.claim_evidence_link."""

    RELATION: ClassVar[str] = "evidence.claim_evidence_link"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_evidence_claim_link_strength",
        "ck_evidence_claim_link_type",
    )
    claim_id: ClaimId
    fact_id: FactId
    support_type: ClaimEvidenceLinkSupportType
    support_strength: Decimal
    note: str | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.claim_id) is not ClaimId:
            _invalid()
        if type(self.fact_id) is not FactId:
            _invalid()
        if type(self.support_type) is not ClaimEvidenceLinkSupportType:
            _invalid()
        if (
            type(self.support_strength) is not Decimal
            or not self.support_strength.is_finite()
        ):
            _invalid()
        if self.note is not None and (type(self.note) is not str):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.support_strength < 0:
            _invalid()

    def __repr__(self) -> str:
        return "ClaimEvidenceLink(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class FactState:
    """Exact scalar state for relation evidence.fact."""

    RELATION: ClassVar[str] = "evidence.fact"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_evidence_fact_conf",
        "ck_evidence_fact_kind",
        "ck_evidence_fact_locator",
        "ck_evidence_fact_one_value",
        "ck_evidence_fact_subject",
        "ck_evidence_fact_value_json",
        "ck_evidence_fact_window",
    )
    id: FactId
    display_id: str
    source_snapshot_id: SourceSnapshotId
    subject_type: FactSubjectType
    subject_id: SubjectId
    predicate: str
    value_text: str | None
    value_numeric: Decimal | None
    value_boolean: bool | None
    value_date: date | None
    value_timestamp: AwareUtcDateTime | None
    value_json: FactValueJsonJson | None
    unit_code: str | None
    locale: str | None
    fact_kind: FactFactKind
    confidence: Decimal
    valid_from: AwareUtcDateTime | None
    valid_to: AwareUtcDateTime | None
    locator: FactLocatorJson
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not FactId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.source_snapshot_id) is not SourceSnapshotId:
            _invalid()
        if type(self.subject_type) is not FactSubjectType:
            _invalid()
        if type(self.subject_id) is not SubjectId:
            _invalid()
        if type(self.predicate) is not str:
            _invalid()
        if self.value_text is not None and (type(self.value_text) is not str):
            _invalid()
        if self.value_numeric is not None and (
            type(self.value_numeric) is not Decimal
            or not self.value_numeric.is_finite()
        ):
            _invalid()
        if self.value_boolean is not None and (type(self.value_boolean) is not bool):
            _invalid()
        if self.value_date is not None and (type(self.value_date) is not date):
            _invalid()
        if self.value_timestamp is not None and (
            type(self.value_timestamp) is not AwareUtcDateTime
        ):
            _invalid()
        if self.value_json is not None and (
            type(self.value_json) is not FactValueJsonJson
        ):
            _invalid()
        if self.unit_code is not None and (type(self.unit_code) is not str):
            _invalid()
        if self.locale is not None and (type(self.locale) is not str):
            _invalid()
        if type(self.fact_kind) is not FactFactKind:
            _invalid()
        if type(self.confidence) is not Decimal or not self.confidence.is_finite():
            _invalid()
        if self.valid_from is not None and (
            type(self.valid_from) is not AwareUtcDateTime
        ):
            _invalid()
        if self.valid_to is not None and (type(self.valid_to) is not AwareUtcDateTime):
            _invalid()
        if type(self.locator) is not FactLocatorJson:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if (
            sum(
                value is not None
                for value in (
                    self.value_text,
                    self.value_numeric,
                    self.value_boolean,
                    self.value_date,
                    self.value_timestamp,
                    self.value_json,
                )
            )
            != 1
        ):
            _invalid()
        if self.confidence < 0:
            _invalid()
        if (
            self.valid_to is not None
            and self.valid_from is not None
            and (not self.valid_to.value > self.valid_from.value)
        ):
            _invalid()

    def __repr__(self) -> str:
        return "FactState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class FactDerivation:
    """Exact scalar state for relation evidence.fact_derivation."""

    RELATION: ClassVar[str] = "evidence.fact_derivation"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_evidence_derivation_role",
        "ck_evidence_derivation_self",
    )
    derived_fact_id: FactId
    input_fact_id: FactId
    derivation_role: FactDerivationDerivationRole
    algorithm_version: str
    formula_description: str | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.derived_fact_id) is not FactId:
            _invalid()
        if type(self.input_fact_id) is not FactId:
            _invalid()
        if type(self.derivation_role) is not FactDerivationDerivationRole:
            _invalid()
        if type(self.algorithm_version) is not str:
            _invalid()
        if self.formula_description is not None and (
            type(self.formula_description) is not str
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.derived_fact_id == self.input_fact_id:
            _invalid()

    def __repr__(self) -> str:
        return "FactDerivation(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class FirstHandExperienceAsset:
    """Exact scalar state for relation evidence.first_hand_experience_asset."""

    RELATION: ClassVar[str] = "evidence.first_hand_experience_asset"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_evidence_first_hand_asset_role",
        "ck_evidence_first_hand_asset_sha",
    )
    experience_record_id: FirstHandExperienceRecordId
    artifact_id: ObjectArtifactId
    role: FirstHandExperienceAssetRole
    artifact_sha256: Sha256Digest
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.experience_record_id) is not FirstHandExperienceRecordId:
            _invalid()
        if type(self.artifact_id) is not ObjectArtifactId:
            _invalid()
        if type(self.role) is not FirstHandExperienceAssetRole:
            _invalid()
        if type(self.artifact_sha256) is not Sha256Digest:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "FirstHandExperienceAsset(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class FirstHandExperienceRecordState:
    """Exact scalar state for relation evidence.first_hand_experience_record."""

    RELATION: ClassVar[str] = "evidence.first_hand_experience_record"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_evidence_first_hand_environment",
        "ck_evidence_first_hand_limitations",
        "ck_evidence_first_hand_procedure",
        "ck_evidence_first_hand_review_pair",
        "ck_evidence_first_hand_review_required",
        "ck_evidence_first_hand_status",
        "ck_evidence_first_hand_variant",
        "ck_evidence_first_hand_window",
    )
    id: FirstHandExperienceRecordId
    display_id: str
    product_id: CanonicalProductId
    product_variant_identity: FirstHandExperienceRecordProductVariantIdentityJson
    tester_principal_id: PrincipalId
    procedure_version: str
    started_at: AwareUtcDateTime
    ended_at: AwareUtcDateTime
    environment: FirstHandExperienceRecordEnvironmentJson
    limitations: str
    review_status: FirstHandExperienceStatus
    reviewed_by_principal_id: PrincipalId | None
    reviewed_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not FirstHandExperienceRecordId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.product_id) is not CanonicalProductId:
            _invalid()
        if (
            type(self.product_variant_identity)
            is not FirstHandExperienceRecordProductVariantIdentityJson
        ):
            _invalid()
        if type(self.tester_principal_id) is not PrincipalId:
            _invalid()
        if type(self.procedure_version) is not str:
            _invalid()
        if type(self.started_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.ended_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.environment) is not FirstHandExperienceRecordEnvironmentJson:
            _invalid()
        if type(self.limitations) is not str:
            _invalid()
        if type(self.review_status) is not FirstHandExperienceStatus:
            _invalid()
        if self.reviewed_by_principal_id is not None and (
            type(self.reviewed_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.reviewed_at is not None and (
            type(self.reviewed_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if (self.reviewed_by_principal_id is None) != (self.reviewed_at is None):
            _invalid()
        if not self.ended_at.value >= self.started_at.value:
            _invalid()

    def __repr__(self) -> str:
        return "FirstHandExperienceRecordState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SourceState:
    """Exact scalar state for relation evidence.source."""

    RELATION: ClassVar[str] = "evidence.source"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_evidence_source_authority",
        "ck_evidence_source_meta",
        "ck_evidence_source_status",
        "ck_evidence_source_type",
        "ck_evidence_source_url",
        "ck_evidence_source_version",
    )
    id: SourceId
    display_id: str
    source_type: SourceSourceType
    provider_endpoint_id: ProviderEndpointId | None
    name: str
    base_url: UriReference | None
    authority_level: SourceAuthorityLevel
    permitted_use: str
    terms_checked_at: AwareUtcDateTime | None
    terms_checked_by_principal_id: PrincipalId | None
    status: SourceStatus
    metadata: SourceMetadataJson
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not SourceId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.source_type) is not SourceSourceType:
            _invalid()
        if self.provider_endpoint_id is not None and (
            type(self.provider_endpoint_id) is not ProviderEndpointId
        ):
            _invalid()
        if type(self.name) is not str:
            _invalid()
        if self.base_url is not None and (type(self.base_url) is not UriReference):
            _invalid()
        if type(self.authority_level) is not SourceAuthorityLevel:
            _invalid()
        if type(self.permitted_use) is not str:
            _invalid()
        if self.terms_checked_at is not None and (
            type(self.terms_checked_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.terms_checked_by_principal_id is not None and (
            type(self.terms_checked_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if type(self.status) is not SourceStatus:
            _invalid()
        if type(self.metadata) is not SourceMetadataJson:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()

    def __repr__(self) -> str:
        return "SourceState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SourcePacketState:
    """Exact scalar state for relation evidence.source_packet."""

    RELATION: ClassVar[str] = "evidence.source_packet"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_evidence_packet_lock",
        "ck_evidence_packet_status",
        "ck_evidence_packet_type",
        "ck_evidence_packet_version_no",
    )
    id: SourcePacketId
    display_id: str
    article_plan_id: ArticlePlanId
    packet_type: SourcePacketPacketType
    status: SourcePacketStatus
    current_version_no: int
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not SourcePacketId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.article_plan_id) is not ArticlePlanId:
            _invalid()
        if type(self.packet_type) is not SourcePacketPacketType:
            _invalid()
        if type(self.status) is not SourcePacketStatus:
            _invalid()
        if (
            type(self.current_version_no) is not int
            or not -_MAX_BIGINT <= self.current_version_no <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()
        if self.current_version_no < 0:
            _invalid()
        if self.lock_version.value < 0:
            _invalid()

    def __repr__(self) -> str:
        return "SourcePacketState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SourcePacketFact:
    """Exact scalar state for relation evidence.source_packet_fact."""

    RELATION: ClassVar[str] = "evidence.source_packet_fact"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_evidence_packet_fact_order",
        "ck_evidence_packet_fact_role",
    )
    source_packet_version_id: SourcePacketVersionId
    fact_id: FactId
    usage_role: SourcePacketFactUsageRole
    display_order: int
    is_required: bool
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.source_packet_version_id) is not SourcePacketVersionId:
            _invalid()
        if type(self.fact_id) is not FactId:
            _invalid()
        if type(self.usage_role) is not SourcePacketFactUsageRole:
            _invalid()
        if (
            type(self.display_order) is not int
            or not -_MAX_BIGINT <= self.display_order <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.is_required) is not bool:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.display_order < 0:
            _invalid()

    def __repr__(self) -> str:
        return "SourcePacketFact(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SourcePacketProduct:
    """Exact scalar state for relation evidence.source_packet_product."""

    RELATION: ClassVar[str] = "evidence.source_packet_product"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_evidence_packet_product_order",
        "ck_evidence_packet_product_role",
    )
    source_packet_version_id: SourcePacketVersionId
    product_id: CanonicalProductId
    offer_id: OfferId | None
    product_role: SourcePacketProductProductRole
    display_order: int
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.source_packet_version_id) is not SourcePacketVersionId:
            _invalid()
        if type(self.product_id) is not CanonicalProductId:
            _invalid()
        if self.offer_id is not None and (type(self.offer_id) is not OfferId):
            _invalid()
        if type(self.product_role) is not SourcePacketProductProductRole:
            _invalid()
        if (
            type(self.display_order) is not int
            or not -_MAX_BIGINT <= self.display_order <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.display_order < 0:
            _invalid()

    def __repr__(self) -> str:
        return "SourcePacketProduct(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SourcePacketVersionState:
    """Exact scalar state for relation evidence.source_packet_version."""

    RELATION: ClassVar[str] = "evidence.source_packet_version"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_evidence_packet_version_hash",
        "ck_evidence_packet_version_num",
        "ck_evidence_packet_version_review",
        "ck_evidence_packet_version_status",
    )
    id: SourcePacketVersionId
    display_id: str
    source_packet_id: SourcePacketId
    version_no: int
    artifact_id: ObjectArtifactId
    content_sha256: Sha256Digest
    schema_version: int
    status: SourcePacketVersionStatus
    built_by_job_id: JobId | None
    reviewed_by_principal_id: PrincipalId | None
    reviewed_at: AwareUtcDateTime | None
    review_note: str | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not SourcePacketVersionId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.source_packet_id) is not SourcePacketId:
            _invalid()
        if (
            type(self.version_no) is not int
            or not -_MAX_BIGINT <= self.version_no <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.artifact_id) is not ObjectArtifactId:
            _invalid()
        if type(self.content_sha256) is not Sha256Digest:
            _invalid()
        if (
            type(self.schema_version) is not int
            or not -_MAX_BIGINT <= self.schema_version <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.status) is not SourcePacketVersionStatus:
            _invalid()
        if self.built_by_job_id is not None and (
            type(self.built_by_job_id) is not JobId
        ):
            _invalid()
        if self.reviewed_by_principal_id is not None and (
            type(self.reviewed_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.reviewed_at is not None and (
            type(self.reviewed_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.review_note is not None and (type(self.review_note) is not str):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "SourcePacketVersionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SourceSnapshot:
    """Exact scalar state for relation evidence.source_snapshot."""

    RELATION: ClassVar[str] = "evidence.source_snapshot"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_evidence_snapshot_expiry",
        "ck_evidence_snapshot_hash",
        "ck_evidence_snapshot_status",
    )
    id: SourceSnapshotId
    display_id: str
    source_id: SourceId
    artifact_id: ObjectArtifactId
    external_reference: str | None
    acquired_at: AwareUtcDateTime
    effective_at: AwareUtcDateTime | None
    expires_at: AwareUtcDateTime | None
    content_sha256: Sha256Digest
    parser_version: str
    validation_status: SourceSnapshotValidationStatus
    validation_message: str | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not SourceSnapshotId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.source_id) is not SourceId:
            _invalid()
        if type(self.artifact_id) is not ObjectArtifactId:
            _invalid()
        if self.external_reference is not None and (
            type(self.external_reference) is not str
        ):
            _invalid()
        if type(self.acquired_at) is not AwareUtcDateTime:
            _invalid()
        if self.effective_at is not None and (
            type(self.effective_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.expires_at is not None and (
            type(self.expires_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.content_sha256) is not Sha256Digest:
            _invalid()
        if type(self.parser_version) is not str:
            _invalid()
        if type(self.validation_status) is not SourceSnapshotValidationStatus:
            _invalid()
        if self.validation_message is not None and (
            type(self.validation_message) is not str
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "SourceSnapshot(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Claim:
    state: ClaimState
    claim_evidence_link_rows: tuple[ClaimEvidenceLink, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not ClaimState:
            _invalid()
        if type(self.claim_evidence_link_rows) is not tuple or any(
            type(item) is not ClaimEvidenceLink
            for item in self.claim_evidence_link_rows
        ):
            _invalid()
        if self.claim_evidence_link_rows != tuple(
            sorted(
                self.claim_evidence_link_rows,
                key=lambda item: (
                    _order_value(item.claim_id),
                    _order_value(item.fact_id),
                    _order_value(item.support_type),
                ),
            )
        ):
            _invalid()

    def __repr__(self) -> str:
        return "Claim(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Fact:
    state: FactState
    fact_derivation_rows: tuple[FactDerivation, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not FactState:
            _invalid()
        if type(self.fact_derivation_rows) is not tuple or any(
            type(item) is not FactDerivation for item in self.fact_derivation_rows
        ):
            _invalid()
        if self.fact_derivation_rows != tuple(
            sorted(
                self.fact_derivation_rows,
                key=lambda item: (
                    _order_value(item.derived_fact_id),
                    _order_value(item.input_fact_id),
                    _order_value(item.derivation_role),
                ),
            )
        ):
            _invalid()

    def __repr__(self) -> str:
        return "Fact(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class FirstHandExperienceRecord:
    state: FirstHandExperienceRecordState
    first_hand_experience_asset_rows: tuple[FirstHandExperienceAsset, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not FirstHandExperienceRecordState:
            _invalid()
        if type(self.first_hand_experience_asset_rows) is not tuple or any(
            type(item) is not FirstHandExperienceAsset
            for item in self.first_hand_experience_asset_rows
        ):
            _invalid()
        if self.first_hand_experience_asset_rows != tuple(
            sorted(
                self.first_hand_experience_asset_rows,
                key=lambda item: (
                    _order_value(item.experience_record_id),
                    _order_value(item.artifact_id),
                    _order_value(item.role),
                ),
            )
        ):
            _invalid()

    def __repr__(self) -> str:
        return "FirstHandExperienceRecord(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Source:
    state: SourceState
    _events: PendingEventBuffer[DomainEvent] = field(
        default_factory=PendingEventBuffer[DomainEvent], repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if type(self.state) is not SourceState:
            _invalid()
        if type(self._events) is not PendingEventBuffer:
            _invalid()

    def pending_events(self) -> tuple[DomainEvent, ...]:
        return self._events.pending_events()

    def acknowledge_events(self, event_ids: tuple[UUID, ...]) -> None:
        self._events.acknowledge_events(event_ids)

    def _record_event(self, event: DomainEvent) -> None:
        self._events.record(event)

    def _restore_acknowledged_events(self) -> None:
        self._events.restore_acknowledged()

    def _finish_acknowledged_events(self) -> None:
        self._events.finish_acknowledged()

    def __repr__(self) -> str:
        return "Source(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SourcePacket:
    state: SourcePacketState
    source_packet_version_rows: tuple[SourcePacketVersionState, ...] = ()
    source_packet_fact_rows: tuple[SourcePacketFact, ...] = ()
    source_packet_product_rows: tuple[SourcePacketProduct, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not SourcePacketState:
            _invalid()
        if type(self.source_packet_version_rows) is not tuple or any(
            type(item) is not SourcePacketVersionState
            for item in self.source_packet_version_rows
        ):
            _invalid()
        if self.source_packet_version_rows != tuple(
            sorted(
                self.source_packet_version_rows,
                key=lambda item: (_order_value(item.id),),
            )
        ):
            _invalid()
        if type(self.source_packet_fact_rows) is not tuple or any(
            type(item) is not SourcePacketFact for item in self.source_packet_fact_rows
        ):
            _invalid()
        if self.source_packet_fact_rows != tuple(
            sorted(
                self.source_packet_fact_rows,
                key=lambda item: (
                    _order_value(item.source_packet_version_id),
                    _order_value(item.fact_id),
                ),
            )
        ):
            _invalid()
        if type(self.source_packet_product_rows) is not tuple or any(
            type(item) is not SourcePacketProduct
            for item in self.source_packet_product_rows
        ):
            _invalid()
        if self.source_packet_product_rows != tuple(
            sorted(
                self.source_packet_product_rows,
                key=lambda item: (
                    _order_value(item.source_packet_version_id),
                    _order_value(item.product_id),
                    _order_value(item.product_role),
                ),
            )
        ):
            _invalid()

    def __repr__(self) -> str:
        return "SourcePacket(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SourcePacketVersion:
    state: SourcePacketVersionState
    source_packet_fact_rows: tuple[SourcePacketFact, ...] = ()
    source_packet_product_rows: tuple[SourcePacketProduct, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not SourcePacketVersionState:
            _invalid()
        if type(self.source_packet_fact_rows) is not tuple or any(
            type(item) is not SourcePacketFact for item in self.source_packet_fact_rows
        ):
            _invalid()
        if self.source_packet_fact_rows != tuple(
            sorted(
                self.source_packet_fact_rows,
                key=lambda item: (
                    _order_value(item.source_packet_version_id),
                    _order_value(item.fact_id),
                ),
            )
        ):
            _invalid()
        if type(self.source_packet_product_rows) is not tuple or any(
            type(item) is not SourcePacketProduct
            for item in self.source_packet_product_rows
        ):
            _invalid()
        if self.source_packet_product_rows != tuple(
            sorted(
                self.source_packet_product_rows,
                key=lambda item: (
                    _order_value(item.source_packet_version_id),
                    _order_value(item.product_id),
                    _order_value(item.product_role),
                ),
            )
        ):
            _invalid()

    def __repr__(self) -> str:
        return "SourcePacketVersion(<redacted>)"


__all__ = [
    "Claim",
    "ClaimEvidenceLink",
    "ClaimState",
    "Fact",
    "FactDerivation",
    "FactState",
    "FirstHandExperienceAsset",
    "FirstHandExperienceRecord",
    "FirstHandExperienceRecordState",
    "Source",
    "SourcePacket",
    "SourcePacketFact",
    "SourcePacketProduct",
    "SourcePacketState",
    "SourcePacketVersion",
    "SourcePacketVersionState",
    "SourceSnapshot",
    "SourceState",
]
