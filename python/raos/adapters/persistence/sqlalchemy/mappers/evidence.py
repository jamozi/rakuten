"""Explicit fail-closed scalar mappers for the EVIDENCE ST-0308 slice."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from raos.adapters.persistence.sqlalchemy.physical_constraints import (
    install_mapper_physical_constraint_guards,
)
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
from raos.domain.evidence.aggregates import (
    ClaimEvidenceLink,
    ClaimState,
    FactDerivation,
    FactState,
    FirstHandExperienceAsset,
    FirstHandExperienceRecordState,
    SourcePacketFact,
    SourcePacketProduct,
    SourcePacketState,
    SourcePacketVersionState,
    SourceSnapshot,
    SourceState,
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
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


def _corrupt() -> PersistenceError:
    return PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION)


ClaimStateScalars = tuple[
    ClaimId,
    str,
    ArticleVersionId,
    ArticleBlockId | None,
    str,
    ClaimClaimType,
    str,
    ClaimCriticality,
    ClaimSupportStatus,
    AiAttemptId | None,
    AwareUtcDateTime,
]


def map_evidence_claim_from_row(
    *,
    id: ClaimId,
    display_id: str,
    article_version_id: ArticleVersionId,
    block_id: ArticleBlockId | None,
    claim_key: str,
    claim_type: ClaimClaimType,
    claim_text: str,
    criticality: ClaimCriticality,
    support_status: ClaimSupportStatus,
    generated_by_ai_attempt_id: AiAttemptId | None,
    created_at: AwareUtcDateTime,
) -> ClaimState:
    try:
        return ClaimState(
            id=id,
            display_id=display_id,
            article_version_id=article_version_id,
            block_id=block_id,
            claim_key=claim_key,
            claim_type=claim_type,
            claim_text=claim_text,
            criticality=criticality,
            support_status=support_status,
            generated_by_ai_attempt_id=generated_by_ai_attempt_id,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_evidence_claim_to_row(value: ClaimState) -> ClaimStateScalars:
    if type(value) is not ClaimState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.article_version_id,
        value.block_id,
        value.claim_key,
        value.claim_type,
        value.claim_text,
        value.criticality,
        value.support_status,
        value.generated_by_ai_attempt_id,
        value.created_at,
    )


ClaimEvidenceLinkScalars = tuple[
    ClaimId,
    FactId,
    ClaimEvidenceLinkSupportType,
    Decimal,
    str | None,
    AwareUtcDateTime,
]


def map_evidence_claim_evidence_link_from_row(
    *,
    claim_id: ClaimId,
    fact_id: FactId,
    support_type: ClaimEvidenceLinkSupportType,
    support_strength: Decimal,
    note: str | None,
    created_at: AwareUtcDateTime,
) -> ClaimEvidenceLink:
    try:
        return ClaimEvidenceLink(
            claim_id=claim_id,
            fact_id=fact_id,
            support_type=support_type,
            support_strength=support_strength,
            note=note,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_evidence_claim_evidence_link_to_row(
    value: ClaimEvidenceLink,
) -> ClaimEvidenceLinkScalars:
    if type(value) is not ClaimEvidenceLink:
        raise _corrupt() from None
    return (
        value.claim_id,
        value.fact_id,
        value.support_type,
        value.support_strength,
        value.note,
        value.created_at,
    )


FactStateScalars = tuple[
    FactId,
    str,
    SourceSnapshotId,
    FactSubjectType,
    SubjectId,
    str,
    str | None,
    Decimal | None,
    bool | None,
    date | None,
    AwareUtcDateTime | None,
    FactValueJsonJson | None,
    str | None,
    str | None,
    FactFactKind,
    Decimal,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    FactLocatorJson,
    AwareUtcDateTime,
]


def map_evidence_fact_from_row(
    *,
    id: FactId,
    display_id: str,
    source_snapshot_id: SourceSnapshotId,
    subject_type: FactSubjectType,
    subject_id: SubjectId,
    predicate: str,
    value_text: str | None,
    value_numeric: Decimal | None,
    value_boolean: bool | None,
    value_date: date | None,
    value_timestamp: AwareUtcDateTime | None,
    value_json: FactValueJsonJson | None,
    unit_code: str | None,
    locale: str | None,
    fact_kind: FactFactKind,
    confidence: Decimal,
    valid_from: AwareUtcDateTime | None,
    valid_to: AwareUtcDateTime | None,
    locator: FactLocatorJson,
    created_at: AwareUtcDateTime,
) -> FactState:
    try:
        return FactState(
            id=id,
            display_id=display_id,
            source_snapshot_id=source_snapshot_id,
            subject_type=subject_type,
            subject_id=subject_id,
            predicate=predicate,
            value_text=value_text,
            value_numeric=value_numeric,
            value_boolean=value_boolean,
            value_date=value_date,
            value_timestamp=value_timestamp,
            value_json=value_json,
            unit_code=unit_code,
            locale=locale,
            fact_kind=fact_kind,
            confidence=confidence,
            valid_from=valid_from,
            valid_to=valid_to,
            locator=locator,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_evidence_fact_to_row(value: FactState) -> FactStateScalars:
    if type(value) is not FactState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.source_snapshot_id,
        value.subject_type,
        value.subject_id,
        value.predicate,
        value.value_text,
        value.value_numeric,
        value.value_boolean,
        value.value_date,
        value.value_timestamp,
        value.value_json,
        value.unit_code,
        value.locale,
        value.fact_kind,
        value.confidence,
        value.valid_from,
        value.valid_to,
        value.locator,
        value.created_at,
    )


FactDerivationScalars = tuple[
    FactId,
    FactId,
    FactDerivationDerivationRole,
    str,
    str | None,
    AwareUtcDateTime,
]


def map_evidence_fact_derivation_from_row(
    *,
    derived_fact_id: FactId,
    input_fact_id: FactId,
    derivation_role: FactDerivationDerivationRole,
    algorithm_version: str,
    formula_description: str | None,
    created_at: AwareUtcDateTime,
) -> FactDerivation:
    try:
        return FactDerivation(
            derived_fact_id=derived_fact_id,
            input_fact_id=input_fact_id,
            derivation_role=derivation_role,
            algorithm_version=algorithm_version,
            formula_description=formula_description,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_evidence_fact_derivation_to_row(value: FactDerivation) -> FactDerivationScalars:
    if type(value) is not FactDerivation:
        raise _corrupt() from None
    return (
        value.derived_fact_id,
        value.input_fact_id,
        value.derivation_role,
        value.algorithm_version,
        value.formula_description,
        value.created_at,
    )


FirstHandExperienceAssetScalars = tuple[
    FirstHandExperienceRecordId,
    ObjectArtifactId,
    FirstHandExperienceAssetRole,
    Sha256Digest,
    AwareUtcDateTime,
]


def map_evidence_first_hand_experience_asset_from_row(
    *,
    experience_record_id: FirstHandExperienceRecordId,
    artifact_id: ObjectArtifactId,
    role: FirstHandExperienceAssetRole,
    artifact_sha256: Sha256Digest,
    created_at: AwareUtcDateTime,
) -> FirstHandExperienceAsset:
    try:
        return FirstHandExperienceAsset(
            experience_record_id=experience_record_id,
            artifact_id=artifact_id,
            role=role,
            artifact_sha256=artifact_sha256,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_evidence_first_hand_experience_asset_to_row(
    value: FirstHandExperienceAsset,
) -> FirstHandExperienceAssetScalars:
    if type(value) is not FirstHandExperienceAsset:
        raise _corrupt() from None
    return (
        value.experience_record_id,
        value.artifact_id,
        value.role,
        value.artifact_sha256,
        value.created_at,
    )


FirstHandExperienceRecordStateScalars = tuple[
    FirstHandExperienceRecordId,
    str,
    CanonicalProductId,
    FirstHandExperienceRecordProductVariantIdentityJson,
    PrincipalId,
    str,
    AwareUtcDateTime,
    AwareUtcDateTime,
    FirstHandExperienceRecordEnvironmentJson,
    str,
    FirstHandExperienceStatus,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_evidence_first_hand_experience_record_from_row(
    *,
    id: FirstHandExperienceRecordId,
    display_id: str,
    product_id: CanonicalProductId,
    product_variant_identity: FirstHandExperienceRecordProductVariantIdentityJson,
    tester_principal_id: PrincipalId,
    procedure_version: str,
    started_at: AwareUtcDateTime,
    ended_at: AwareUtcDateTime,
    environment: FirstHandExperienceRecordEnvironmentJson,
    limitations: str,
    review_status: FirstHandExperienceStatus,
    reviewed_by_principal_id: PrincipalId | None,
    reviewed_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> FirstHandExperienceRecordState:
    try:
        return FirstHandExperienceRecordState(
            id=id,
            display_id=display_id,
            product_id=product_id,
            product_variant_identity=product_variant_identity,
            tester_principal_id=tester_principal_id,
            procedure_version=procedure_version,
            started_at=started_at,
            ended_at=ended_at,
            environment=environment,
            limitations=limitations,
            review_status=review_status,
            reviewed_by_principal_id=reviewed_by_principal_id,
            reviewed_at=reviewed_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_evidence_first_hand_experience_record_to_row(
    value: FirstHandExperienceRecordState,
) -> FirstHandExperienceRecordStateScalars:
    if type(value) is not FirstHandExperienceRecordState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.product_id,
        value.product_variant_identity,
        value.tester_principal_id,
        value.procedure_version,
        value.started_at,
        value.ended_at,
        value.environment,
        value.limitations,
        value.review_status,
        value.reviewed_by_principal_id,
        value.reviewed_at,
        value.created_at,
    )


SourceStateScalars = tuple[
    SourceId,
    str,
    SourceSourceType,
    ProviderEndpointId | None,
    str,
    UriReference | None,
    SourceAuthorityLevel,
    str,
    AwareUtcDateTime | None,
    PrincipalId | None,
    SourceStatus,
    SourceMetadataJson,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_evidence_source_from_row(
    *,
    id: SourceId,
    display_id: str,
    source_type: SourceSourceType,
    provider_endpoint_id: ProviderEndpointId | None,
    name: str,
    base_url: UriReference | None,
    authority_level: SourceAuthorityLevel,
    permitted_use: str,
    terms_checked_at: AwareUtcDateTime | None,
    terms_checked_by_principal_id: PrincipalId | None,
    status: SourceStatus,
    metadata: SourceMetadataJson,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> SourceState:
    try:
        return SourceState(
            id=id,
            display_id=display_id,
            source_type=source_type,
            provider_endpoint_id=provider_endpoint_id,
            name=name,
            base_url=base_url,
            authority_level=authority_level,
            permitted_use=permitted_use,
            terms_checked_at=terms_checked_at,
            terms_checked_by_principal_id=terms_checked_by_principal_id,
            status=status,
            metadata=metadata,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_evidence_source_to_row(value: SourceState) -> SourceStateScalars:
    if type(value) is not SourceState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.source_type,
        value.provider_endpoint_id,
        value.name,
        value.base_url,
        value.authority_level,
        value.permitted_use,
        value.terms_checked_at,
        value.terms_checked_by_principal_id,
        value.status,
        value.metadata,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


SourcePacketStateScalars = tuple[
    SourcePacketId,
    str,
    ArticlePlanId,
    SourcePacketPacketType,
    SourcePacketStatus,
    int,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_evidence_source_packet_from_row(
    *,
    id: SourcePacketId,
    display_id: str,
    article_plan_id: ArticlePlanId,
    packet_type: SourcePacketPacketType,
    status: SourcePacketStatus,
    current_version_no: int,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> SourcePacketState:
    try:
        return SourcePacketState(
            id=id,
            display_id=display_id,
            article_plan_id=article_plan_id,
            packet_type=packet_type,
            status=status,
            current_version_no=current_version_no,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_evidence_source_packet_to_row(
    value: SourcePacketState,
) -> SourcePacketStateScalars:
    if type(value) is not SourcePacketState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.article_plan_id,
        value.packet_type,
        value.status,
        value.current_version_no,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


SourcePacketFactScalars = tuple[
    SourcePacketVersionId,
    FactId,
    SourcePacketFactUsageRole,
    int,
    bool,
    AwareUtcDateTime,
]


def map_evidence_source_packet_fact_from_row(
    *,
    source_packet_version_id: SourcePacketVersionId,
    fact_id: FactId,
    usage_role: SourcePacketFactUsageRole,
    display_order: int,
    is_required: bool,
    created_at: AwareUtcDateTime,
) -> SourcePacketFact:
    try:
        return SourcePacketFact(
            source_packet_version_id=source_packet_version_id,
            fact_id=fact_id,
            usage_role=usage_role,
            display_order=display_order,
            is_required=is_required,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_evidence_source_packet_fact_to_row(
    value: SourcePacketFact,
) -> SourcePacketFactScalars:
    if type(value) is not SourcePacketFact:
        raise _corrupt() from None
    return (
        value.source_packet_version_id,
        value.fact_id,
        value.usage_role,
        value.display_order,
        value.is_required,
        value.created_at,
    )


SourcePacketProductScalars = tuple[
    SourcePacketVersionId,
    CanonicalProductId,
    OfferId | None,
    SourcePacketProductProductRole,
    int,
    AwareUtcDateTime,
]


def map_evidence_source_packet_product_from_row(
    *,
    source_packet_version_id: SourcePacketVersionId,
    product_id: CanonicalProductId,
    offer_id: OfferId | None,
    product_role: SourcePacketProductProductRole,
    display_order: int,
    created_at: AwareUtcDateTime,
) -> SourcePacketProduct:
    try:
        return SourcePacketProduct(
            source_packet_version_id=source_packet_version_id,
            product_id=product_id,
            offer_id=offer_id,
            product_role=product_role,
            display_order=display_order,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_evidence_source_packet_product_to_row(
    value: SourcePacketProduct,
) -> SourcePacketProductScalars:
    if type(value) is not SourcePacketProduct:
        raise _corrupt() from None
    return (
        value.source_packet_version_id,
        value.product_id,
        value.offer_id,
        value.product_role,
        value.display_order,
        value.created_at,
    )


SourcePacketVersionStateScalars = tuple[
    SourcePacketVersionId,
    str,
    SourcePacketId,
    int,
    ObjectArtifactId,
    Sha256Digest,
    int,
    SourcePacketVersionStatus,
    JobId | None,
    PrincipalId | None,
    AwareUtcDateTime | None,
    str | None,
    AwareUtcDateTime,
]


def map_evidence_source_packet_version_from_row(
    *,
    id: SourcePacketVersionId,
    display_id: str,
    source_packet_id: SourcePacketId,
    version_no: int,
    artifact_id: ObjectArtifactId,
    content_sha256: Sha256Digest,
    schema_version: int,
    status: SourcePacketVersionStatus,
    built_by_job_id: JobId | None,
    reviewed_by_principal_id: PrincipalId | None,
    reviewed_at: AwareUtcDateTime | None,
    review_note: str | None,
    created_at: AwareUtcDateTime,
) -> SourcePacketVersionState:
    try:
        return SourcePacketVersionState(
            id=id,
            display_id=display_id,
            source_packet_id=source_packet_id,
            version_no=version_no,
            artifact_id=artifact_id,
            content_sha256=content_sha256,
            schema_version=schema_version,
            status=status,
            built_by_job_id=built_by_job_id,
            reviewed_by_principal_id=reviewed_by_principal_id,
            reviewed_at=reviewed_at,
            review_note=review_note,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_evidence_source_packet_version_to_row(
    value: SourcePacketVersionState,
) -> SourcePacketVersionStateScalars:
    if type(value) is not SourcePacketVersionState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.source_packet_id,
        value.version_no,
        value.artifact_id,
        value.content_sha256,
        value.schema_version,
        value.status,
        value.built_by_job_id,
        value.reviewed_by_principal_id,
        value.reviewed_at,
        value.review_note,
        value.created_at,
    )


SourceSnapshotScalars = tuple[
    SourceSnapshotId,
    str,
    SourceId,
    ObjectArtifactId,
    str | None,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    Sha256Digest,
    str,
    SourceSnapshotValidationStatus,
    str | None,
    AwareUtcDateTime,
]


def map_evidence_source_snapshot_from_row(
    *,
    id: SourceSnapshotId,
    display_id: str,
    source_id: SourceId,
    artifact_id: ObjectArtifactId,
    external_reference: str | None,
    acquired_at: AwareUtcDateTime,
    effective_at: AwareUtcDateTime | None,
    expires_at: AwareUtcDateTime | None,
    content_sha256: Sha256Digest,
    parser_version: str,
    validation_status: SourceSnapshotValidationStatus,
    validation_message: str | None,
    created_at: AwareUtcDateTime,
) -> SourceSnapshot:
    try:
        return SourceSnapshot(
            id=id,
            display_id=display_id,
            source_id=source_id,
            artifact_id=artifact_id,
            external_reference=external_reference,
            acquired_at=acquired_at,
            effective_at=effective_at,
            expires_at=expires_at,
            content_sha256=content_sha256,
            parser_version=parser_version,
            validation_status=validation_status,
            validation_message=validation_message,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_evidence_source_snapshot_to_row(value: SourceSnapshot) -> SourceSnapshotScalars:
    if type(value) is not SourceSnapshot:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.source_id,
        value.artifact_id,
        value.external_reference,
        value.acquired_at,
        value.effective_at,
        value.expires_at,
        value.content_sha256,
        value.parser_version,
        value.validation_status,
        value.validation_message,
        value.created_at,
    )


__all__ = [
    "map_evidence_claim_evidence_link_from_row",
    "map_evidence_claim_evidence_link_to_row",
    "map_evidence_claim_from_row",
    "map_evidence_claim_to_row",
    "map_evidence_fact_derivation_from_row",
    "map_evidence_fact_derivation_to_row",
    "map_evidence_fact_from_row",
    "map_evidence_fact_to_row",
    "map_evidence_first_hand_experience_asset_from_row",
    "map_evidence_first_hand_experience_asset_to_row",
    "map_evidence_first_hand_experience_record_from_row",
    "map_evidence_first_hand_experience_record_to_row",
    "map_evidence_source_from_row",
    "map_evidence_source_packet_fact_from_row",
    "map_evidence_source_packet_fact_to_row",
    "map_evidence_source_packet_from_row",
    "map_evidence_source_packet_product_from_row",
    "map_evidence_source_packet_product_to_row",
    "map_evidence_source_packet_to_row",
    "map_evidence_source_packet_version_from_row",
    "map_evidence_source_packet_version_to_row",
    "map_evidence_source_snapshot_from_row",
    "map_evidence_source_snapshot_to_row",
    "map_evidence_source_to_row",
]

install_mapper_physical_constraint_guards(globals())
