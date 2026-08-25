"""Explicit fail-closed scalar mappers for the ST-0308 CATALOG slice."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from raos.adapters.persistence.sqlalchemy.physical_constraints import (
    install_mapper_physical_constraint_guards,
)
from raos.domain.catalog.aggregates import (
    AffiliateLinkObservation,
    AttributeDefinitionState,
    AvailabilityObservation,
    CanonicalProductState,
    CategoryGenreMapping,
    GroupingDecisionState,
    IngestionRequestState,
    OfferCurrentProjection,
    OfferState,
    PriceObservation,
    ProductAttributeValue,
    ProductCandidateState,
    ProductGroupMembership,
    ProductRelation,
    ProviderEndpointState,
    RakutenGenreState,
    ReviewAggregateObservation,
    SafeOfferCurrent,
    ShopState,
)
from raos.domain.catalog.enums import (
    AffiliateLinkObservationValidationStatus,
    AttributeDefinitionDataType,
    AttributeDefinitionStatus,
    AvailabilityObservationAvailability,
    AvailabilityObservationValidationStatus,
    CanonicalProductLifecycleStatus,
    CategoryGenreMappingMappingRole,
    GroupingDecisionDecisionType,
    IngestionRequestStatus,
    OfferCurrentProjectionCurrentAvailability,
    OfferCurrentProjectionFreshnessStatus,
    OfferStatus,
    PriceObservationShippingCondition,
    PriceObservationValidationStatus,
    ProductCandidateListingStatus,
    ProductRelationRelationType,
    ProviderEndpointStatus,
    ShopStatus,
)
from raos.domain.catalog.ids import (
    AffiliateLinkObservationId,
    AttributeDefinitionId,
    AvailabilityObservationId,
    CanonicalProductId,
    CategoryGenreMappingId,
    GroupingDecisionId,
    IngestionRequestId,
    OfferId,
    PriceObservationId,
    ProductAttributeValueId,
    ProductCandidateId,
    ProductGroupMembershipId,
    ProductRelationId,
    ProviderEndpointId,
    RakutenGenreId,
    ReviewAggregateObservationId,
    ShopId,
)
from raos.domain.catalog.values import (
    CanonicalProductIdentityAttributesJson,
    GroupingDecisionReasonsJson,
    IngestionRequestRateLimitObservationJson,
    IngestionRequestRequestParametersJson,
    ProductCandidateImageSetJson,
    ProviderEndpointNonSecretConfigJson,
)
from raos.domain.evidence.ids import FactId, SourceSnapshotId
from raos.domain.iam.ids import (
    PrincipalId,
)
from raos.domain.ops.ids import (
    JobId,
    ObjectArtifactId,
)
from raos.domain.portfolio.ids import (
    CategoryId,
)
from raos.domain.shared.identity import (
    DecidedByActorId,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    Sha256Digest,
    UriReference,
    YenMinor,
)
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


def _corrupt() -> PersistenceError:
    return PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION)


AffiliateLinkObservationScalars = tuple[
    AffiliateLinkObservationId,
    OfferId,
    UriReference,
    Sha256Digest,
    str,
    bool,
    Decimal | None,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    SourceSnapshotId,
    AffiliateLinkObservationValidationStatus,
    str,
    AwareUtcDateTime,
]


def map_catalog_affiliate_link_observation_from_row(
    *,
    id: AffiliateLinkObservationId,
    offer_id: OfferId,
    affiliate_url: UriReference,
    url_sha256: Sha256Digest,
    destination_host: str,
    is_api_returned: bool,
    affiliate_rate: Decimal | None,
    observed_at: AwareUtcDateTime,
    valid_until: AwareUtcDateTime | None,
    source_snapshot_id: SourceSnapshotId,
    validation_status: AffiliateLinkObservationValidationStatus,
    link_contract_version: str,
    created_at: AwareUtcDateTime,
) -> AffiliateLinkObservation:
    try:
        return AffiliateLinkObservation(
            id=id,
            offer_id=offer_id,
            affiliate_url=affiliate_url,
            url_sha256=url_sha256,
            destination_host=destination_host,
            is_api_returned=is_api_returned,
            affiliate_rate=affiliate_rate,
            observed_at=observed_at,
            valid_until=valid_until,
            source_snapshot_id=source_snapshot_id,
            validation_status=validation_status,
            link_contract_version=link_contract_version,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_affiliate_link_observation_to_row(
    value: AffiliateLinkObservation,
) -> AffiliateLinkObservationScalars:
    if type(value) is not AffiliateLinkObservation:
        raise _corrupt() from None
    return (
        value.id,
        value.offer_id,
        value.affiliate_url,
        value.url_sha256,
        value.destination_host,
        value.is_api_returned,
        value.affiliate_rate,
        value.observed_at,
        value.valid_until,
        value.source_snapshot_id,
        value.validation_status,
        value.link_contract_version,
        value.created_at,
    )


AttributeDefinitionStateScalars = tuple[
    AttributeDefinitionId,
    CategoryId | None,
    str,
    str,
    AttributeDefinitionDataType,
    str | None,
    bool,
    bool,
    str,
    AttributeDefinitionStatus,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_catalog_attribute_definition_from_row(
    *,
    id: AttributeDefinitionId,
    category_id: CategoryId | None,
    attribute_code: str,
    name: str,
    data_type: AttributeDefinitionDataType,
    unit_family: str | None,
    is_comparable: bool,
    is_required: bool,
    normalization_rule_version: str,
    status: AttributeDefinitionStatus,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> AttributeDefinitionState:
    try:
        return AttributeDefinitionState(
            id=id,
            category_id=category_id,
            attribute_code=attribute_code,
            name=name,
            data_type=data_type,
            unit_family=unit_family,
            is_comparable=is_comparable,
            is_required=is_required,
            normalization_rule_version=normalization_rule_version,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_attribute_definition_to_row(
    value: AttributeDefinitionState,
) -> AttributeDefinitionStateScalars:
    if type(value) is not AttributeDefinitionState:
        raise _corrupt() from None
    return (
        value.id,
        value.category_id,
        value.attribute_code,
        value.name,
        value.data_type,
        value.unit_family,
        value.is_comparable,
        value.is_required,
        value.normalization_rule_version,
        value.status,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


AvailabilityObservationScalars = tuple[
    AvailabilityObservationId,
    OfferId,
    AvailabilityObservationAvailability,
    int | None,
    str | None,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    SourceSnapshotId,
    AvailabilityObservationValidationStatus,
    Decimal,
    AwareUtcDateTime,
]


def map_catalog_availability_observation_from_row(
    *,
    id: AvailabilityObservationId,
    offer_id: OfferId,
    availability: AvailabilityObservationAvailability,
    quantity: int | None,
    lead_time_text: str | None,
    observed_at: AwareUtcDateTime,
    ingested_at: AwareUtcDateTime,
    valid_until: AwareUtcDateTime | None,
    source_snapshot_id: SourceSnapshotId,
    validation_status: AvailabilityObservationValidationStatus,
    confidence: Decimal,
    created_at: AwareUtcDateTime,
) -> AvailabilityObservation:
    try:
        return AvailabilityObservation(
            id=id,
            offer_id=offer_id,
            availability=availability,
            quantity=quantity,
            lead_time_text=lead_time_text,
            observed_at=observed_at,
            ingested_at=ingested_at,
            valid_until=valid_until,
            source_snapshot_id=source_snapshot_id,
            validation_status=validation_status,
            confidence=confidence,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_availability_observation_to_row(
    value: AvailabilityObservation,
) -> AvailabilityObservationScalars:
    if type(value) is not AvailabilityObservation:
        raise _corrupt() from None
    return (
        value.id,
        value.offer_id,
        value.availability,
        value.quantity,
        value.lead_time_text,
        value.observed_at,
        value.ingested_at,
        value.valid_until,
        value.source_snapshot_id,
        value.validation_status,
        value.confidence,
        value.created_at,
    )


CanonicalProductStateScalars = tuple[
    CanonicalProductId,
    str,
    CategoryId,
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str,
    CanonicalProductLifecycleStatus,
    Decimal,
    CanonicalProductIdentityAttributesJson,
    CanonicalProductId | None,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_catalog_canonical_product_from_row(
    *,
    id: CanonicalProductId,
    display_id: str,
    category_id: CategoryId,
    canonical_name: str,
    brand_name: str | None,
    manufacturer_name: str | None,
    model_number: str | None,
    jan_code: str | None,
    product_type: str,
    lifecycle_status: CanonicalProductLifecycleStatus,
    identity_confidence: Decimal,
    identity_attributes: CanonicalProductIdentityAttributesJson,
    merged_into_product_id: CanonicalProductId | None,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> CanonicalProductState:
    try:
        return CanonicalProductState(
            id=id,
            display_id=display_id,
            category_id=category_id,
            canonical_name=canonical_name,
            brand_name=brand_name,
            manufacturer_name=manufacturer_name,
            model_number=model_number,
            jan_code=jan_code,
            product_type=product_type,
            lifecycle_status=lifecycle_status,
            identity_confidence=identity_confidence,
            identity_attributes=identity_attributes,
            merged_into_product_id=merged_into_product_id,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_canonical_product_to_row(
    value: CanonicalProductState,
) -> CanonicalProductStateScalars:
    if type(value) is not CanonicalProductState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.category_id,
        value.canonical_name,
        value.brand_name,
        value.manufacturer_name,
        value.model_number,
        value.jan_code,
        value.product_type,
        value.lifecycle_status,
        value.identity_confidence,
        value.identity_attributes,
        value.merged_into_product_id,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


CategoryGenreMappingScalars = tuple[
    CategoryGenreMappingId,
    CategoryId,
    RakutenGenreId,
    CategoryGenreMappingMappingRole,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    str,
    PrincipalId,
    AwareUtcDateTime,
]


def map_catalog_category_genre_mapping_from_row(
    *,
    id: CategoryGenreMappingId,
    category_id: CategoryId,
    rakuten_genre_id: RakutenGenreId,
    mapping_role: CategoryGenreMappingMappingRole,
    valid_from: AwareUtcDateTime,
    valid_to: AwareUtcDateTime | None,
    decision_reason: str,
    decided_by_principal_id: PrincipalId,
    created_at: AwareUtcDateTime,
) -> CategoryGenreMapping:
    try:
        return CategoryGenreMapping(
            id=id,
            category_id=category_id,
            rakuten_genre_id=rakuten_genre_id,
            mapping_role=mapping_role,
            valid_from=valid_from,
            valid_to=valid_to,
            decision_reason=decision_reason,
            decided_by_principal_id=decided_by_principal_id,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_category_genre_mapping_to_row(
    value: CategoryGenreMapping,
) -> CategoryGenreMappingScalars:
    if type(value) is not CategoryGenreMapping:
        raise _corrupt() from None
    return (
        value.id,
        value.category_id,
        value.rakuten_genre_id,
        value.mapping_role,
        value.valid_from,
        value.valid_to,
        value.decision_reason,
        value.decided_by_principal_id,
        value.created_at,
    )


GroupingDecisionStateScalars = tuple[
    GroupingDecisionId,
    ProductCandidateId,
    CanonicalProductId | None,
    GroupingDecisionDecisionType,
    Decimal | None,
    str,
    GroupingDecisionReasonsJson,
    str,
    DecidedByActorId | None,
    AwareUtcDateTime,
    GroupingDecisionId | None,
    AwareUtcDateTime,
]


def map_catalog_grouping_decision_from_row(
    *,
    id: GroupingDecisionId,
    product_candidate_id: ProductCandidateId,
    proposed_product_id: CanonicalProductId | None,
    decision_type: GroupingDecisionDecisionType,
    decision_score: Decimal | None,
    rule_version: str,
    reasons: GroupingDecisionReasonsJson,
    decided_by_actor_type: str,
    decided_by_actor_id: DecidedByActorId | None,
    decided_at: AwareUtcDateTime,
    supersedes_decision_id: GroupingDecisionId | None,
    created_at: AwareUtcDateTime,
) -> GroupingDecisionState:
    try:
        return GroupingDecisionState(
            id=id,
            product_candidate_id=product_candidate_id,
            proposed_product_id=proposed_product_id,
            decision_type=decision_type,
            decision_score=decision_score,
            rule_version=rule_version,
            reasons=reasons,
            decided_by_actor_type=decided_by_actor_type,
            decided_by_actor_id=decided_by_actor_id,
            decided_at=decided_at,
            supersedes_decision_id=supersedes_decision_id,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_grouping_decision_to_row(
    value: GroupingDecisionState,
) -> GroupingDecisionStateScalars:
    if type(value) is not GroupingDecisionState:
        raise _corrupt() from None
    return (
        value.id,
        value.product_candidate_id,
        value.proposed_product_id,
        value.decision_type,
        value.decision_score,
        value.rule_version,
        value.reasons,
        value.decided_by_actor_type,
        value.decided_by_actor_id,
        value.decided_at,
        value.supersedes_decision_id,
        value.created_at,
    )


IngestionRequestStateScalars = tuple[
    IngestionRequestId,
    str,
    ProviderEndpointId,
    JobId,
    str,
    IngestionRequestRequestParametersJson,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    int | None,
    IngestionRequestStatus,
    ObjectArtifactId | None,
    int | None,
    IngestionRequestRateLimitObservationJson,
    str | None,
    str | None,
    str | None,
    AwareUtcDateTime,
]


def map_catalog_ingestion_request_from_row(
    *,
    id: IngestionRequestId,
    display_id: str,
    provider_endpoint_id: ProviderEndpointId,
    job_id: JobId,
    request_fingerprint: str,
    request_parameters: IngestionRequestRequestParametersJson,
    requested_at: AwareUtcDateTime,
    responded_at: AwareUtcDateTime | None,
    http_status: int | None,
    status: IngestionRequestStatus,
    raw_response_artifact_id: ObjectArtifactId | None,
    item_count: int | None,
    rate_limit_observation: IngestionRequestRateLimitObservationJson,
    error_class: str | None,
    error_code: str | None,
    error_message: str | None,
    created_at: AwareUtcDateTime,
) -> IngestionRequestState:
    try:
        return IngestionRequestState(
            id=id,
            display_id=display_id,
            provider_endpoint_id=provider_endpoint_id,
            job_id=job_id,
            request_fingerprint=request_fingerprint,
            request_parameters=request_parameters,
            requested_at=requested_at,
            responded_at=responded_at,
            http_status=http_status,
            status=status,
            raw_response_artifact_id=raw_response_artifact_id,
            item_count=item_count,
            rate_limit_observation=rate_limit_observation,
            error_class=error_class,
            error_code=error_code,
            error_message=error_message,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_ingestion_request_to_row(
    value: IngestionRequestState,
) -> IngestionRequestStateScalars:
    if type(value) is not IngestionRequestState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.provider_endpoint_id,
        value.job_id,
        value.request_fingerprint,
        value.request_parameters,
        value.requested_at,
        value.responded_at,
        value.http_status,
        value.status,
        value.raw_response_artifact_id,
        value.item_count,
        value.rate_limit_observation,
        value.error_class,
        value.error_code,
        value.error_message,
        value.created_at,
    )


OfferStateScalars = tuple[
    OfferId,
    str,
    ProviderEndpointId,
    str,
    ProductCandidateId,
    CanonicalProductId | None,
    ShopId,
    UriReference,
    OfferStatus,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_catalog_offer_from_row(
    *,
    id: OfferId,
    display_id: str,
    provider_endpoint_id: ProviderEndpointId,
    external_offer_id: str,
    product_candidate_id: ProductCandidateId,
    product_id: CanonicalProductId | None,
    shop_id: ShopId,
    item_url: UriReference,
    status: OfferStatus,
    first_observed_at: AwareUtcDateTime,
    last_observed_at: AwareUtcDateTime,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> OfferState:
    try:
        return OfferState(
            id=id,
            display_id=display_id,
            provider_endpoint_id=provider_endpoint_id,
            external_offer_id=external_offer_id,
            product_candidate_id=product_candidate_id,
            product_id=product_id,
            shop_id=shop_id,
            item_url=item_url,
            status=status,
            first_observed_at=first_observed_at,
            last_observed_at=last_observed_at,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_offer_to_row(value: OfferState) -> OfferStateScalars:
    if type(value) is not OfferState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.provider_endpoint_id,
        value.external_offer_id,
        value.product_candidate_id,
        value.product_id,
        value.shop_id,
        value.item_url,
        value.status,
        value.first_observed_at,
        value.last_observed_at,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


OfferCurrentProjectionScalars = tuple[
    OfferId,
    CanonicalProductId | None,
    PriceObservationId | None,
    AvailabilityObservationId | None,
    ReviewAggregateObservationId | None,
    AffiliateLinkObservationId | None,
    YenMinor | None,
    YenMinor | None,
    OfferCurrentProjectionCurrentAvailability,
    int | None,
    Decimal | None,
    UriReference | None,
    str | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    OfferCurrentProjectionFreshnessStatus,
    int,
    AwareUtcDateTime,
]


def map_catalog_offer_current_projection_from_row(
    *,
    offer_id: OfferId,
    product_id: CanonicalProductId | None,
    price_observation_id: PriceObservationId | None,
    availability_observation_id: AvailabilityObservationId | None,
    review_observation_id: ReviewAggregateObservationId | None,
    affiliate_link_observation_id: AffiliateLinkObservationId | None,
    current_price_jpy: YenMinor | None,
    current_shipping_fee_jpy: YenMinor | None,
    current_availability: OfferCurrentProjectionCurrentAvailability,
    review_count: int | None,
    review_average: Decimal | None,
    affiliate_url: UriReference | None,
    destination_host: str | None,
    price_observed_at: AwareUtcDateTime | None,
    availability_observed_at: AwareUtcDateTime | None,
    link_observed_at: AwareUtcDateTime | None,
    freshness_status: OfferCurrentProjectionFreshnessStatus,
    projection_version: int,
    updated_at: AwareUtcDateTime,
) -> OfferCurrentProjection:
    try:
        return OfferCurrentProjection(
            offer_id=offer_id,
            product_id=product_id,
            price_observation_id=price_observation_id,
            availability_observation_id=availability_observation_id,
            review_observation_id=review_observation_id,
            affiliate_link_observation_id=affiliate_link_observation_id,
            current_price_jpy=current_price_jpy,
            current_shipping_fee_jpy=current_shipping_fee_jpy,
            current_availability=current_availability,
            review_count=review_count,
            review_average=review_average,
            affiliate_url=affiliate_url,
            destination_host=destination_host,
            price_observed_at=price_observed_at,
            availability_observed_at=availability_observed_at,
            link_observed_at=link_observed_at,
            freshness_status=freshness_status,
            projection_version=projection_version,
            updated_at=updated_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_offer_current_projection_to_row(
    value: OfferCurrentProjection,
) -> OfferCurrentProjectionScalars:
    if type(value) is not OfferCurrentProjection:
        raise _corrupt() from None
    return (
        value.offer_id,
        value.product_id,
        value.price_observation_id,
        value.availability_observation_id,
        value.review_observation_id,
        value.affiliate_link_observation_id,
        value.current_price_jpy,
        value.current_shipping_fee_jpy,
        value.current_availability,
        value.review_count,
        value.review_average,
        value.affiliate_url,
        value.destination_host,
        value.price_observed_at,
        value.availability_observed_at,
        value.link_observed_at,
        value.freshness_status,
        value.projection_version,
        value.updated_at,
    )


PriceObservationScalars = tuple[
    PriceObservationId,
    OfferId,
    YenMinor,
    bool,
    YenMinor | None,
    PriceObservationShippingCondition,
    Decimal | None,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    SourceSnapshotId,
    PriceObservationValidationStatus,
    Decimal,
    AwareUtcDateTime,
]


def map_catalog_price_observation_from_row(
    *,
    id: PriceObservationId,
    offer_id: OfferId,
    price_jpy: YenMinor,
    tax_included: bool,
    shipping_fee_jpy: YenMinor | None,
    shipping_condition: PriceObservationShippingCondition,
    points_rate: Decimal | None,
    observed_at: AwareUtcDateTime,
    ingested_at: AwareUtcDateTime,
    valid_until: AwareUtcDateTime | None,
    source_snapshot_id: SourceSnapshotId,
    validation_status: PriceObservationValidationStatus,
    confidence: Decimal,
    created_at: AwareUtcDateTime,
) -> PriceObservation:
    try:
        return PriceObservation(
            id=id,
            offer_id=offer_id,
            price_jpy=price_jpy,
            tax_included=tax_included,
            shipping_fee_jpy=shipping_fee_jpy,
            shipping_condition=shipping_condition,
            points_rate=points_rate,
            observed_at=observed_at,
            ingested_at=ingested_at,
            valid_until=valid_until,
            source_snapshot_id=source_snapshot_id,
            validation_status=validation_status,
            confidence=confidence,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_price_observation_to_row(
    value: PriceObservation,
) -> PriceObservationScalars:
    if type(value) is not PriceObservation:
        raise _corrupt() from None
    return (
        value.id,
        value.offer_id,
        value.price_jpy,
        value.tax_included,
        value.shipping_fee_jpy,
        value.shipping_condition,
        value.points_rate,
        value.observed_at,
        value.ingested_at,
        value.valid_until,
        value.source_snapshot_id,
        value.validation_status,
        value.confidence,
        value.created_at,
    )


ProductAttributeValueScalars = tuple[
    ProductAttributeValueId,
    CanonicalProductId,
    AttributeDefinitionId,
    str | None,
    Decimal | None,
    bool | None,
    date | None,
    str | None,
    str | None,
    FactId | None,
    Decimal,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_catalog_product_attribute_value_from_row(
    *,
    id: ProductAttributeValueId,
    product_id: CanonicalProductId,
    attribute_definition_id: AttributeDefinitionId,
    value_text: str | None,
    value_numeric: Decimal | None,
    value_boolean: bool | None,
    value_date: date | None,
    value_code: str | None,
    unit_code: str | None,
    source_fact_id: FactId | None,
    confidence: Decimal,
    valid_from: AwareUtcDateTime,
    valid_to: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> ProductAttributeValue:
    try:
        return ProductAttributeValue(
            id=id,
            product_id=product_id,
            attribute_definition_id=attribute_definition_id,
            value_text=value_text,
            value_numeric=value_numeric,
            value_boolean=value_boolean,
            value_date=value_date,
            value_code=value_code,
            unit_code=unit_code,
            source_fact_id=source_fact_id,
            confidence=confidence,
            valid_from=valid_from,
            valid_to=valid_to,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_product_attribute_value_to_row(
    value: ProductAttributeValue,
) -> ProductAttributeValueScalars:
    if type(value) is not ProductAttributeValue:
        raise _corrupt() from None
    return (
        value.id,
        value.product_id,
        value.attribute_definition_id,
        value.value_text,
        value.value_numeric,
        value.value_boolean,
        value.value_date,
        value.value_code,
        value.unit_code,
        value.source_fact_id,
        value.confidence,
        value.valid_from,
        value.valid_to,
        value.created_at,
    )


ProductCandidateStateScalars = tuple[
    ProductCandidateId,
    str,
    ProviderEndpointId,
    str,
    ShopId,
    RakutenGenreId | None,
    str,
    str,
    str | None,
    str | None,
    ProductCandidateImageSetJson,
    ProductCandidateListingStatus,
    AwareUtcDateTime,
    AwareUtcDateTime,
    SourceSnapshotId,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_catalog_product_candidate_from_row(
    *,
    id: ProductCandidateId,
    display_id: str,
    provider_endpoint_id: ProviderEndpointId,
    external_item_code: str,
    shop_id: ShopId,
    rakuten_genre_id: RakutenGenreId | None,
    item_name: str,
    normalized_item_name: str,
    model_number_candidate: str | None,
    jan_code_candidate: str | None,
    image_set: ProductCandidateImageSetJson,
    listing_status: ProductCandidateListingStatus,
    first_observed_at: AwareUtcDateTime,
    last_observed_at: AwareUtcDateTime,
    source_snapshot_id: SourceSnapshotId,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> ProductCandidateState:
    try:
        return ProductCandidateState(
            id=id,
            display_id=display_id,
            provider_endpoint_id=provider_endpoint_id,
            external_item_code=external_item_code,
            shop_id=shop_id,
            rakuten_genre_id=rakuten_genre_id,
            item_name=item_name,
            normalized_item_name=normalized_item_name,
            model_number_candidate=model_number_candidate,
            jan_code_candidate=jan_code_candidate,
            image_set=image_set,
            listing_status=listing_status,
            first_observed_at=first_observed_at,
            last_observed_at=last_observed_at,
            source_snapshot_id=source_snapshot_id,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_product_candidate_to_row(
    value: ProductCandidateState,
) -> ProductCandidateStateScalars:
    if type(value) is not ProductCandidateState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.provider_endpoint_id,
        value.external_item_code,
        value.shop_id,
        value.rakuten_genre_id,
        value.item_name,
        value.normalized_item_name,
        value.model_number_candidate,
        value.jan_code_candidate,
        value.image_set,
        value.listing_status,
        value.first_observed_at,
        value.last_observed_at,
        value.source_snapshot_id,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


ProductGroupMembershipScalars = tuple[
    ProductGroupMembershipId,
    CanonicalProductId,
    ProductCandidateId,
    GroupingDecisionId,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_catalog_product_group_membership_from_row(
    *,
    id: ProductGroupMembershipId,
    product_id: CanonicalProductId,
    product_candidate_id: ProductCandidateId,
    grouping_decision_id: GroupingDecisionId,
    valid_from: AwareUtcDateTime,
    valid_to: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> ProductGroupMembership:
    try:
        return ProductGroupMembership(
            id=id,
            product_id=product_id,
            product_candidate_id=product_candidate_id,
            grouping_decision_id=grouping_decision_id,
            valid_from=valid_from,
            valid_to=valid_to,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_product_group_membership_to_row(
    value: ProductGroupMembership,
) -> ProductGroupMembershipScalars:
    if type(value) is not ProductGroupMembership:
        raise _corrupt() from None
    return (
        value.id,
        value.product_id,
        value.product_candidate_id,
        value.grouping_decision_id,
        value.valid_from,
        value.valid_to,
        value.created_at,
    )


ProductRelationScalars = tuple[
    ProductRelationId,
    CanonicalProductId,
    CanonicalProductId,
    ProductRelationRelationType,
    Decimal,
    FactId | None,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_catalog_product_relation_from_row(
    *,
    id: ProductRelationId,
    from_product_id: CanonicalProductId,
    to_product_id: CanonicalProductId,
    relation_type: ProductRelationRelationType,
    confidence: Decimal,
    source_fact_id: FactId | None,
    valid_from: AwareUtcDateTime,
    valid_to: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> ProductRelation:
    try:
        return ProductRelation(
            id=id,
            from_product_id=from_product_id,
            to_product_id=to_product_id,
            relation_type=relation_type,
            confidence=confidence,
            source_fact_id=source_fact_id,
            valid_from=valid_from,
            valid_to=valid_to,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_product_relation_to_row(
    value: ProductRelation,
) -> ProductRelationScalars:
    if type(value) is not ProductRelation:
        raise _corrupt() from None
    return (
        value.id,
        value.from_product_id,
        value.to_product_id,
        value.relation_type,
        value.confidence,
        value.source_fact_id,
        value.valid_from,
        value.valid_to,
        value.created_at,
    )


ProviderEndpointStateScalars = tuple[
    ProviderEndpointId,
    str,
    str,
    str,
    str,
    str,
    ProviderEndpointStatus,
    Sha256Digest,
    UriReference | None,
    ProviderEndpointNonSecretConfigJson,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_catalog_provider_endpoint_from_row(
    *,
    id: ProviderEndpointId,
    provider_code: str,
    provider_name: str,
    api_name: str,
    api_version: str,
    base_host: str,
    status: ProviderEndpointStatus,
    contract_sha256: Sha256Digest,
    documentation_url: UriReference | None,
    non_secret_config: ProviderEndpointNonSecretConfigJson,
    effective_from: AwareUtcDateTime,
    effective_to: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> ProviderEndpointState:
    try:
        return ProviderEndpointState(
            id=id,
            provider_code=provider_code,
            provider_name=provider_name,
            api_name=api_name,
            api_version=api_version,
            base_host=base_host,
            status=status,
            contract_sha256=contract_sha256,
            documentation_url=documentation_url,
            non_secret_config=non_secret_config,
            effective_from=effective_from,
            effective_to=effective_to,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_provider_endpoint_to_row(
    value: ProviderEndpointState,
) -> ProviderEndpointStateScalars:
    if type(value) is not ProviderEndpointState:
        raise _corrupt() from None
    return (
        value.id,
        value.provider_code,
        value.provider_name,
        value.api_name,
        value.api_version,
        value.base_host,
        value.status,
        value.contract_sha256,
        value.documentation_url,
        value.non_secret_config,
        value.effective_from,
        value.effective_to,
        value.created_at,
    )


RakutenGenreStateScalars = tuple[
    RakutenGenreId,
    ProviderEndpointId,
    int,
    int | None,
    str,
    int,
    bool,
    bool,
    SourceSnapshotId,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_catalog_rakuten_genre_from_row(
    *,
    id: RakutenGenreId,
    provider_endpoint_id: ProviderEndpointId,
    external_genre_id: int,
    parent_external_genre_id: int | None,
    genre_name: str,
    genre_level: int,
    is_leaf: bool,
    is_active: bool,
    source_snapshot_id: SourceSnapshotId,
    observed_at: AwareUtcDateTime,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> RakutenGenreState:
    try:
        return RakutenGenreState(
            id=id,
            provider_endpoint_id=provider_endpoint_id,
            external_genre_id=external_genre_id,
            parent_external_genre_id=parent_external_genre_id,
            genre_name=genre_name,
            genre_level=genre_level,
            is_leaf=is_leaf,
            is_active=is_active,
            source_snapshot_id=source_snapshot_id,
            observed_at=observed_at,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_rakuten_genre_to_row(
    value: RakutenGenreState,
) -> RakutenGenreStateScalars:
    if type(value) is not RakutenGenreState:
        raise _corrupt() from None
    return (
        value.id,
        value.provider_endpoint_id,
        value.external_genre_id,
        value.parent_external_genre_id,
        value.genre_name,
        value.genre_level,
        value.is_leaf,
        value.is_active,
        value.source_snapshot_id,
        value.observed_at,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


ReviewAggregateObservationScalars = tuple[
    ReviewAggregateObservationId,
    OfferId,
    int,
    Decimal | None,
    AwareUtcDateTime,
    AwareUtcDateTime,
    SourceSnapshotId,
    AwareUtcDateTime,
]


def map_catalog_review_aggregate_observation_from_row(
    *,
    id: ReviewAggregateObservationId,
    offer_id: OfferId,
    review_count: int,
    review_average: Decimal | None,
    observed_at: AwareUtcDateTime,
    ingested_at: AwareUtcDateTime,
    source_snapshot_id: SourceSnapshotId,
    created_at: AwareUtcDateTime,
) -> ReviewAggregateObservation:
    try:
        return ReviewAggregateObservation(
            id=id,
            offer_id=offer_id,
            review_count=review_count,
            review_average=review_average,
            observed_at=observed_at,
            ingested_at=ingested_at,
            source_snapshot_id=source_snapshot_id,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_review_aggregate_observation_to_row(
    value: ReviewAggregateObservation,
) -> ReviewAggregateObservationScalars:
    if type(value) is not ReviewAggregateObservation:
        raise _corrupt() from None
    return (
        value.id,
        value.offer_id,
        value.review_count,
        value.review_average,
        value.observed_at,
        value.ingested_at,
        value.source_snapshot_id,
        value.created_at,
    )


ShopStateScalars = tuple[
    ShopId,
    str,
    ProviderEndpointId,
    str,
    str,
    UriReference | None,
    bool,
    ShopStatus,
    AwareUtcDateTime,
    AwareUtcDateTime,
    SourceSnapshotId,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_catalog_shop_from_row(
    *,
    id: ShopId,
    display_id: str,
    provider_endpoint_id: ProviderEndpointId,
    external_shop_code: str,
    shop_name: str,
    shop_url: UriReference | None,
    affiliate_capable: bool,
    status: ShopStatus,
    first_observed_at: AwareUtcDateTime,
    last_observed_at: AwareUtcDateTime,
    source_snapshot_id: SourceSnapshotId,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> ShopState:
    try:
        return ShopState(
            id=id,
            display_id=display_id,
            provider_endpoint_id=provider_endpoint_id,
            external_shop_code=external_shop_code,
            shop_name=shop_name,
            shop_url=shop_url,
            affiliate_capable=affiliate_capable,
            status=status,
            first_observed_at=first_observed_at,
            last_observed_at=last_observed_at,
            source_snapshot_id=source_snapshot_id,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_catalog_shop_to_row(value: ShopState) -> ShopStateScalars:
    if type(value) is not ShopState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.provider_endpoint_id,
        value.external_shop_code,
        value.shop_name,
        value.shop_url,
        value.affiliate_capable,
        value.status,
        value.first_observed_at,
        value.last_observed_at,
        value.source_snapshot_id,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


SafeOfferCurrentScalars = tuple[
    OfferId,
    CanonicalProductId,
    ShopId,
    YenMinor | None,
    YenMinor | None,
    OfferCurrentProjectionCurrentAvailability | None,
    int | None,
    Decimal | None,
    UriReference | None,
    str | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    OfferCurrentProjectionFreshnessStatus,
    int,
    AwareUtcDateTime,
]


def map_catalog_v_safe_offer_current_from_row(
    *,
    offer_id: OfferId,
    product_id: CanonicalProductId,
    shop_id: ShopId,
    current_price_jpy: YenMinor | None,
    current_shipping_fee_jpy: YenMinor | None,
    current_availability: OfferCurrentProjectionCurrentAvailability | None,
    review_count: int | None,
    review_average: Decimal | None,
    affiliate_url: UriReference | None,
    destination_host: str | None,
    price_observed_at: AwareUtcDateTime | None,
    availability_observed_at: AwareUtcDateTime | None,
    link_observed_at: AwareUtcDateTime | None,
    freshness_status: OfferCurrentProjectionFreshnessStatus,
    projection_version: int,
    updated_at: AwareUtcDateTime,
) -> SafeOfferCurrent:
    try:
        return SafeOfferCurrent(
            offer_id=offer_id,
            product_id=product_id,
            shop_id=shop_id,
            current_price_jpy=current_price_jpy,
            current_shipping_fee_jpy=current_shipping_fee_jpy,
            current_availability=current_availability,
            review_count=review_count,
            review_average=review_average,
            affiliate_url=affiliate_url,
            destination_host=destination_host,
            price_observed_at=price_observed_at,
            availability_observed_at=availability_observed_at,
            link_observed_at=link_observed_at,
            freshness_status=freshness_status,
            projection_version=projection_version,
            updated_at=updated_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


__all__ = [
    "AffiliateLinkObservationScalars",
    "AttributeDefinitionStateScalars",
    "AvailabilityObservationScalars",
    "CanonicalProductStateScalars",
    "CategoryGenreMappingScalars",
    "GroupingDecisionStateScalars",
    "IngestionRequestStateScalars",
    "OfferCurrentProjectionScalars",
    "OfferStateScalars",
    "PriceObservationScalars",
    "ProductAttributeValueScalars",
    "ProductCandidateStateScalars",
    "ProductGroupMembershipScalars",
    "ProductRelationScalars",
    "ProviderEndpointStateScalars",
    "RakutenGenreStateScalars",
    "ReviewAggregateObservationScalars",
    "SafeOfferCurrentScalars",
    "ShopStateScalars",
    "map_catalog_affiliate_link_observation_from_row",
    "map_catalog_affiliate_link_observation_to_row",
    "map_catalog_attribute_definition_from_row",
    "map_catalog_attribute_definition_to_row",
    "map_catalog_availability_observation_from_row",
    "map_catalog_availability_observation_to_row",
    "map_catalog_canonical_product_from_row",
    "map_catalog_canonical_product_to_row",
    "map_catalog_category_genre_mapping_from_row",
    "map_catalog_category_genre_mapping_to_row",
    "map_catalog_grouping_decision_from_row",
    "map_catalog_grouping_decision_to_row",
    "map_catalog_ingestion_request_from_row",
    "map_catalog_ingestion_request_to_row",
    "map_catalog_offer_current_projection_from_row",
    "map_catalog_offer_current_projection_to_row",
    "map_catalog_offer_from_row",
    "map_catalog_offer_to_row",
    "map_catalog_price_observation_from_row",
    "map_catalog_price_observation_to_row",
    "map_catalog_product_attribute_value_from_row",
    "map_catalog_product_attribute_value_to_row",
    "map_catalog_product_candidate_from_row",
    "map_catalog_product_candidate_to_row",
    "map_catalog_product_group_membership_from_row",
    "map_catalog_product_group_membership_to_row",
    "map_catalog_product_relation_from_row",
    "map_catalog_product_relation_to_row",
    "map_catalog_provider_endpoint_from_row",
    "map_catalog_provider_endpoint_to_row",
    "map_catalog_rakuten_genre_from_row",
    "map_catalog_rakuten_genre_to_row",
    "map_catalog_review_aggregate_observation_from_row",
    "map_catalog_review_aggregate_observation_to_row",
    "map_catalog_shop_from_row",
    "map_catalog_shop_to_row",
    "map_catalog_v_safe_offer_current_from_row",
]

install_mapper_physical_constraint_guards(globals())
