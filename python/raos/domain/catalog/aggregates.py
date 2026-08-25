"""Exact immutable CATALOG persistence domain values for ST-0308."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import re
from typing import NoReturn
import unicodedata
from urllib.parse import urlsplit
from uuid import UUID

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
from raos.domain.shared.events import DomainEvent
from raos.domain.shared.identity import EntityId
from raos.domain.shared.persistence import PendingEventBuffer

_MAX_BIGINT = (1 << 63) - 1


def _invalid() -> NoReturn:
    raise ValueError("INVALID_CATALOG_PERSISTENCE_VALUE") from None


def _text(value: object) -> None:
    if (
        type(value) is not str
        or not value
        or len(value) > 4096
        or value != value.strip()
        or unicodedata.normalize("NFC", value) != value
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        _invalid()


def _integer(value: object) -> None:
    if type(value) is not int or not 0 <= value <= _MAX_BIGINT:
        _invalid()


def _decimal(value: object) -> None:
    if type(value) is not Decimal or not value.is_finite():
        _invalid()


def _nominal(value: object, module: str, name: str) -> None:
    if (
        not isinstance(value, EntityId)
        or type(value).__module__ != module
        or type(value).__name__ != name
    ):
        _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class AffiliateLinkObservation:
    id: AffiliateLinkObservationId
    offer_id: OfferId
    affiliate_url: UriReference
    url_sha256: Sha256Digest
    destination_host: str
    is_api_returned: bool
    affiliate_rate: Decimal | None
    observed_at: AwareUtcDateTime
    valid_until: AwareUtcDateTime | None
    source_snapshot_id: SourceSnapshotId
    validation_status: AffiliateLinkObservationValidationStatus
    link_contract_version: str
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not AffiliateLinkObservationId:
            _invalid()
        if type(self.offer_id) is not OfferId:
            _invalid()
        if type(self.affiliate_url) is not UriReference:
            _invalid()
        if type(self.url_sha256) is not Sha256Digest:
            _invalid()
        _text(self.destination_host)
        if type(self.is_api_returned) is not bool:
            _invalid()
        if self.affiliate_rate is not None:
            _decimal(self.affiliate_rate)
        if type(self.observed_at) is not AwareUtcDateTime:
            _invalid()
        if self.valid_until is not None:
            if type(self.valid_until) is not AwareUtcDateTime:
                _invalid()
        _nominal(
            self.source_snapshot_id, "raos.domain.evidence.ids", "SourceSnapshotId"
        )
        if type(self.validation_status) is not AffiliateLinkObservationValidationStatus:
            _invalid()
        _text(self.link_contract_version)
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "AffiliateLinkObservation(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AttributeDefinitionState:
    id: AttributeDefinitionId
    category_id: CategoryId | None
    attribute_code: str
    name: str
    data_type: AttributeDefinitionDataType
    unit_family: str | None
    is_comparable: bool
    is_required: bool
    normalization_rule_version: str
    status: AttributeDefinitionStatus
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not AttributeDefinitionId:
            _invalid()
        if self.category_id is not None:
            if type(self.category_id) is not CategoryId:
                _invalid()
        _text(self.attribute_code)
        _text(self.name)
        if type(self.data_type) is not AttributeDefinitionDataType:
            _invalid()
        if self.unit_family is not None:
            _text(self.unit_family)
        if type(self.is_comparable) is not bool:
            _invalid()
        if type(self.is_required) is not bool:
            _invalid()
        _text(self.normalization_rule_version)
        if type(self.status) is not AttributeDefinitionStatus:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()

    def __repr__(self) -> str:
        return "AttributeDefinitionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AvailabilityObservation:
    id: AvailabilityObservationId
    offer_id: OfferId
    availability: AvailabilityObservationAvailability
    quantity: int | None
    lead_time_text: str | None
    observed_at: AwareUtcDateTime
    ingested_at: AwareUtcDateTime
    valid_until: AwareUtcDateTime | None
    source_snapshot_id: SourceSnapshotId
    validation_status: AvailabilityObservationValidationStatus
    confidence: Decimal
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not AvailabilityObservationId:
            _invalid()
        if type(self.offer_id) is not OfferId:
            _invalid()
        if type(self.availability) is not AvailabilityObservationAvailability:
            _invalid()
        if self.quantity is not None:
            _integer(self.quantity)
        if self.lead_time_text is not None:
            _text(self.lead_time_text)
        if type(self.observed_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.ingested_at) is not AwareUtcDateTime:
            _invalid()
        if self.valid_until is not None:
            if type(self.valid_until) is not AwareUtcDateTime:
                _invalid()
        _nominal(
            self.source_snapshot_id, "raos.domain.evidence.ids", "SourceSnapshotId"
        )
        if type(self.validation_status) is not AvailabilityObservationValidationStatus:
            _invalid()
        _decimal(self.confidence)
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "AvailabilityObservation(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalProductState:
    id: CanonicalProductId
    display_id: str
    category_id: CategoryId
    canonical_name: str
    brand_name: str | None
    manufacturer_name: str | None
    model_number: str | None
    jan_code: str | None
    product_type: str
    lifecycle_status: CanonicalProductLifecycleStatus
    identity_confidence: Decimal
    identity_attributes: CanonicalProductIdentityAttributesJson
    merged_into_product_id: CanonicalProductId | None
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not CanonicalProductId:
            _invalid()
        _text(self.display_id)
        if type(self.category_id) is not CategoryId:
            _invalid()
        _text(self.canonical_name)
        if self.brand_name is not None:
            _text(self.brand_name)
        if self.manufacturer_name is not None:
            _text(self.manufacturer_name)
        if self.model_number is not None:
            _text(self.model_number)
        if self.jan_code is not None:
            _text(self.jan_code)
        _text(self.product_type)
        if type(self.lifecycle_status) is not CanonicalProductLifecycleStatus:
            _invalid()
        _decimal(self.identity_confidence)
        if type(self.identity_attributes) is not CanonicalProductIdentityAttributesJson:
            _invalid()
        if self.merged_into_product_id is not None:
            if type(self.merged_into_product_id) is not CanonicalProductId:
                _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()

    def __repr__(self) -> str:
        return "CanonicalProductState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class CategoryGenreMapping:
    id: CategoryGenreMappingId
    category_id: CategoryId
    rakuten_genre_id: RakutenGenreId
    mapping_role: CategoryGenreMappingMappingRole
    valid_from: AwareUtcDateTime
    valid_to: AwareUtcDateTime | None
    decision_reason: str
    decided_by_principal_id: PrincipalId
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not CategoryGenreMappingId:
            _invalid()
        if type(self.category_id) is not CategoryId:
            _invalid()
        if type(self.rakuten_genre_id) is not RakutenGenreId:
            _invalid()
        if type(self.mapping_role) is not CategoryGenreMappingMappingRole:
            _invalid()
        if type(self.valid_from) is not AwareUtcDateTime:
            _invalid()
        if self.valid_to is not None:
            if type(self.valid_to) is not AwareUtcDateTime:
                _invalid()
        _text(self.decision_reason)
        if type(self.decided_by_principal_id) is not PrincipalId:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "CategoryGenreMapping(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class GroupingDecisionState:
    id: GroupingDecisionId
    product_candidate_id: ProductCandidateId
    proposed_product_id: CanonicalProductId | None
    decision_type: GroupingDecisionDecisionType
    decision_score: Decimal | None
    rule_version: str
    reasons: GroupingDecisionReasonsJson
    decided_by_actor_type: str
    decided_by_actor_id: DecidedByActorId | None
    decided_at: AwareUtcDateTime
    supersedes_decision_id: GroupingDecisionId | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not GroupingDecisionId:
            _invalid()
        if type(self.product_candidate_id) is not ProductCandidateId:
            _invalid()
        if self.proposed_product_id is not None:
            if type(self.proposed_product_id) is not CanonicalProductId:
                _invalid()
        if type(self.decision_type) is not GroupingDecisionDecisionType:
            _invalid()
        if self.decision_score is not None:
            _decimal(self.decision_score)
        _text(self.rule_version)
        if type(self.reasons) is not GroupingDecisionReasonsJson:
            _invalid()
        _text(self.decided_by_actor_type)
        if self.decided_by_actor_id is not None:
            if type(self.decided_by_actor_id) is not DecidedByActorId:
                _invalid()
        if type(self.decided_at) is not AwareUtcDateTime:
            _invalid()
        if self.supersedes_decision_id is not None:
            if type(self.supersedes_decision_id) is not GroupingDecisionId:
                _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "GroupingDecisionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class IngestionRequestState:
    id: IngestionRequestId
    display_id: str
    provider_endpoint_id: ProviderEndpointId
    job_id: JobId
    request_fingerprint: str
    request_parameters: IngestionRequestRequestParametersJson
    requested_at: AwareUtcDateTime
    responded_at: AwareUtcDateTime | None
    http_status: int | None
    status: IngestionRequestStatus
    raw_response_artifact_id: ObjectArtifactId | None
    item_count: int | None
    rate_limit_observation: IngestionRequestRateLimitObservationJson
    error_class: str | None
    error_code: str | None
    error_message: str | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not IngestionRequestId:
            _invalid()
        _text(self.display_id)
        if type(self.provider_endpoint_id) is not ProviderEndpointId:
            _invalid()
        if type(self.job_id) is not JobId:
            _invalid()
        _text(self.request_fingerprint)
        if type(self.request_parameters) is not IngestionRequestRequestParametersJson:
            _invalid()
        if type(self.requested_at) is not AwareUtcDateTime:
            _invalid()
        if self.responded_at is not None:
            if type(self.responded_at) is not AwareUtcDateTime:
                _invalid()
        if self.http_status is not None:
            _integer(self.http_status)
        if type(self.status) is not IngestionRequestStatus:
            _invalid()
        if self.raw_response_artifact_id is not None:
            if type(self.raw_response_artifact_id) is not ObjectArtifactId:
                _invalid()
        if self.item_count is not None:
            _integer(self.item_count)
        if (
            type(self.rate_limit_observation)
            is not IngestionRequestRateLimitObservationJson
        ):
            _invalid()
        if self.error_class is not None:
            _text(self.error_class)
        if self.error_code is not None:
            _text(self.error_code)
        if self.error_message is not None:
            _text(self.error_message)
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "IngestionRequestState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class OfferState:
    id: OfferId
    display_id: str
    provider_endpoint_id: ProviderEndpointId
    external_offer_id: str
    product_candidate_id: ProductCandidateId
    product_id: CanonicalProductId | None
    shop_id: ShopId
    item_url: UriReference
    status: OfferStatus
    first_observed_at: AwareUtcDateTime
    last_observed_at: AwareUtcDateTime
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not OfferId:
            _invalid()
        _text(self.display_id)
        if type(self.provider_endpoint_id) is not ProviderEndpointId:
            _invalid()
        _text(self.external_offer_id)
        if type(self.product_candidate_id) is not ProductCandidateId:
            _invalid()
        if self.product_id is not None:
            if type(self.product_id) is not CanonicalProductId:
                _invalid()
        if type(self.shop_id) is not ShopId:
            _invalid()
        if type(self.item_url) is not UriReference:
            _invalid()
        if type(self.status) is not OfferStatus:
            _invalid()
        if type(self.first_observed_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.last_observed_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()

    def __repr__(self) -> str:
        return "OfferState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class OfferCurrentProjection:
    offer_id: OfferId
    product_id: CanonicalProductId | None
    price_observation_id: PriceObservationId | None
    availability_observation_id: AvailabilityObservationId | None
    review_observation_id: ReviewAggregateObservationId | None
    affiliate_link_observation_id: AffiliateLinkObservationId | None
    current_price_jpy: YenMinor | None
    current_shipping_fee_jpy: YenMinor | None
    current_availability: OfferCurrentProjectionCurrentAvailability
    review_count: int | None
    review_average: Decimal | None
    affiliate_url: UriReference | None
    destination_host: str | None
    price_observed_at: AwareUtcDateTime | None
    availability_observed_at: AwareUtcDateTime | None
    link_observed_at: AwareUtcDateTime | None
    freshness_status: OfferCurrentProjectionFreshnessStatus
    projection_version: int
    updated_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.offer_id) is not OfferId:
            _invalid()
        if self.product_id is not None:
            if type(self.product_id) is not CanonicalProductId:
                _invalid()
        if self.price_observation_id is not None:
            if type(self.price_observation_id) is not PriceObservationId:
                _invalid()
        if self.availability_observation_id is not None:
            if type(self.availability_observation_id) is not AvailabilityObservationId:
                _invalid()
        if self.review_observation_id is not None:
            if type(self.review_observation_id) is not ReviewAggregateObservationId:
                _invalid()
        if self.affiliate_link_observation_id is not None:
            if (
                type(self.affiliate_link_observation_id)
                is not AffiliateLinkObservationId
            ):
                _invalid()
        if self.current_price_jpy is not None:
            if type(self.current_price_jpy) is not YenMinor:
                _invalid()
        if self.current_shipping_fee_jpy is not None:
            if type(self.current_shipping_fee_jpy) is not YenMinor:
                _invalid()
        if (
            type(self.current_availability)
            is not OfferCurrentProjectionCurrentAvailability
        ):
            _invalid()
        if self.review_count is not None:
            _integer(self.review_count)
        if self.review_average is not None:
            _decimal(self.review_average)
        if self.affiliate_url is not None:
            if type(self.affiliate_url) is not UriReference:
                _invalid()
        if self.destination_host is not None:
            _text(self.destination_host)
        if self.price_observed_at is not None:
            if type(self.price_observed_at) is not AwareUtcDateTime:
                _invalid()
        if self.availability_observed_at is not None:
            if type(self.availability_observed_at) is not AwareUtcDateTime:
                _invalid()
        if self.link_observed_at is not None:
            if type(self.link_observed_at) is not AwareUtcDateTime:
                _invalid()
        if type(self.freshness_status) is not OfferCurrentProjectionFreshnessStatus:
            _invalid()
        _integer(self.projection_version)
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "OfferCurrentProjection(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class PriceObservation:
    id: PriceObservationId
    offer_id: OfferId
    price_jpy: YenMinor
    tax_included: bool
    shipping_fee_jpy: YenMinor | None
    shipping_condition: PriceObservationShippingCondition
    points_rate: Decimal | None
    observed_at: AwareUtcDateTime
    ingested_at: AwareUtcDateTime
    valid_until: AwareUtcDateTime | None
    source_snapshot_id: SourceSnapshotId
    validation_status: PriceObservationValidationStatus
    confidence: Decimal
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not PriceObservationId:
            _invalid()
        if type(self.offer_id) is not OfferId:
            _invalid()
        if type(self.price_jpy) is not YenMinor:
            _invalid()
        if type(self.tax_included) is not bool:
            _invalid()
        if self.shipping_fee_jpy is not None:
            if type(self.shipping_fee_jpy) is not YenMinor:
                _invalid()
        if type(self.shipping_condition) is not PriceObservationShippingCondition:
            _invalid()
        if self.points_rate is not None:
            _decimal(self.points_rate)
        if type(self.observed_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.ingested_at) is not AwareUtcDateTime:
            _invalid()
        if self.valid_until is not None:
            if type(self.valid_until) is not AwareUtcDateTime:
                _invalid()
        _nominal(
            self.source_snapshot_id, "raos.domain.evidence.ids", "SourceSnapshotId"
        )
        if type(self.validation_status) is not PriceObservationValidationStatus:
            _invalid()
        _decimal(self.confidence)
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "PriceObservation(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ProductAttributeValue:
    id: ProductAttributeValueId
    product_id: CanonicalProductId
    attribute_definition_id: AttributeDefinitionId
    value_text: str | None
    value_numeric: Decimal | None
    value_boolean: bool | None
    value_date: date | None
    value_code: str | None
    unit_code: str | None
    source_fact_id: FactId | None
    confidence: Decimal
    valid_from: AwareUtcDateTime
    valid_to: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ProductAttributeValueId:
            _invalid()
        if type(self.product_id) is not CanonicalProductId:
            _invalid()
        if type(self.attribute_definition_id) is not AttributeDefinitionId:
            _invalid()
        if self.value_text is not None:
            _text(self.value_text)
        if self.value_numeric is not None:
            _decimal(self.value_numeric)
        if self.value_boolean is not None:
            if type(self.value_boolean) is not bool:
                _invalid()
        if self.value_date is not None:
            if type(self.value_date) is not date:
                _invalid()
        if self.value_code is not None:
            _text(self.value_code)
        if self.unit_code is not None:
            _text(self.unit_code)
        if self.source_fact_id is not None:
            _nominal(self.source_fact_id, "raos.domain.evidence.ids", "FactId")
        _decimal(self.confidence)
        if type(self.valid_from) is not AwareUtcDateTime:
            _invalid()
        if self.valid_to is not None:
            if type(self.valid_to) is not AwareUtcDateTime:
                _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "ProductAttributeValue(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ProductCandidateState:
    id: ProductCandidateId
    display_id: str
    provider_endpoint_id: ProviderEndpointId
    external_item_code: str
    shop_id: ShopId
    rakuten_genre_id: RakutenGenreId | None
    item_name: str
    normalized_item_name: str
    model_number_candidate: str | None
    jan_code_candidate: str | None
    image_set: ProductCandidateImageSetJson
    listing_status: ProductCandidateListingStatus
    first_observed_at: AwareUtcDateTime
    last_observed_at: AwareUtcDateTime
    source_snapshot_id: SourceSnapshotId
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not ProductCandidateId:
            _invalid()
        _text(self.display_id)
        if type(self.provider_endpoint_id) is not ProviderEndpointId:
            _invalid()
        _text(self.external_item_code)
        if type(self.shop_id) is not ShopId:
            _invalid()
        if self.rakuten_genre_id is not None:
            if type(self.rakuten_genre_id) is not RakutenGenreId:
                _invalid()
        _text(self.item_name)
        _text(self.normalized_item_name)
        if self.model_number_candidate is not None:
            _text(self.model_number_candidate)
        if self.jan_code_candidate is not None:
            _text(self.jan_code_candidate)
        if type(self.image_set) is not ProductCandidateImageSetJson:
            _invalid()
        if type(self.listing_status) is not ProductCandidateListingStatus:
            _invalid()
        if type(self.first_observed_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.last_observed_at) is not AwareUtcDateTime:
            _invalid()
        _nominal(
            self.source_snapshot_id, "raos.domain.evidence.ids", "SourceSnapshotId"
        )
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()

    def __repr__(self) -> str:
        return "ProductCandidateState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ProductGroupMembership:
    id: ProductGroupMembershipId
    product_id: CanonicalProductId
    product_candidate_id: ProductCandidateId
    grouping_decision_id: GroupingDecisionId
    valid_from: AwareUtcDateTime
    valid_to: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ProductGroupMembershipId:
            _invalid()
        if type(self.product_id) is not CanonicalProductId:
            _invalid()
        if type(self.product_candidate_id) is not ProductCandidateId:
            _invalid()
        if type(self.grouping_decision_id) is not GroupingDecisionId:
            _invalid()
        if type(self.valid_from) is not AwareUtcDateTime:
            _invalid()
        if self.valid_to is not None:
            if type(self.valid_to) is not AwareUtcDateTime:
                _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "ProductGroupMembership(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ProductRelation:
    id: ProductRelationId
    from_product_id: CanonicalProductId
    to_product_id: CanonicalProductId
    relation_type: ProductRelationRelationType
    confidence: Decimal
    source_fact_id: FactId | None
    valid_from: AwareUtcDateTime
    valid_to: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ProductRelationId:
            _invalid()
        if type(self.from_product_id) is not CanonicalProductId:
            _invalid()
        if type(self.to_product_id) is not CanonicalProductId:
            _invalid()
        if type(self.relation_type) is not ProductRelationRelationType:
            _invalid()
        _decimal(self.confidence)
        if self.source_fact_id is not None:
            _nominal(self.source_fact_id, "raos.domain.evidence.ids", "FactId")
        if type(self.valid_from) is not AwareUtcDateTime:
            _invalid()
        if self.valid_to is not None:
            if type(self.valid_to) is not AwareUtcDateTime:
                _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "ProductRelation(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ProviderEndpointState:
    id: ProviderEndpointId
    provider_code: str
    provider_name: str
    api_name: str
    api_version: str
    base_host: str
    status: ProviderEndpointStatus
    contract_sha256: Sha256Digest
    documentation_url: UriReference | None
    non_secret_config: ProviderEndpointNonSecretConfigJson
    effective_from: AwareUtcDateTime
    effective_to: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ProviderEndpointId:
            _invalid()
        _text(self.provider_code)
        _text(self.provider_name)
        _text(self.api_name)
        _text(self.api_version)
        _text(self.base_host)
        if (
            len(self.base_host) > 253
            or self.base_host != self.base_host.casefold()
            or re.fullmatch(
                r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
                self.base_host,
                re.ASCII,
            )
            is None
        ):
            _invalid()
        if type(self.status) is not ProviderEndpointStatus:
            _invalid()
        if type(self.contract_sha256) is not Sha256Digest:
            _invalid()
        if self.documentation_url is not None:
            if type(self.documentation_url) is not UriReference:
                _invalid()
            documentation = urlsplit(self.documentation_url.value)
            if (
                documentation.scheme != "https"
                or not documentation.netloc
                or documentation.username is not None
                or documentation.password is not None
                or documentation.query
                or documentation.fragment
            ):
                _invalid()
        if type(self.non_secret_config) is not ProviderEndpointNonSecretConfigJson:
            _invalid()
        if type(self.effective_from) is not AwareUtcDateTime:
            _invalid()
        if self.effective_to is not None:
            if type(self.effective_to) is not AwareUtcDateTime:
                _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "ProviderEndpointState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RakutenGenreState:
    id: RakutenGenreId
    provider_endpoint_id: ProviderEndpointId
    external_genre_id: int
    parent_external_genre_id: int | None
    genre_name: str
    genre_level: int
    is_leaf: bool
    is_active: bool
    source_snapshot_id: SourceSnapshotId
    observed_at: AwareUtcDateTime
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not RakutenGenreId:
            _invalid()
        if type(self.provider_endpoint_id) is not ProviderEndpointId:
            _invalid()
        _integer(self.external_genre_id)
        if self.parent_external_genre_id is not None:
            _integer(self.parent_external_genre_id)
        _text(self.genre_name)
        _integer(self.genre_level)
        if type(self.is_leaf) is not bool:
            _invalid()
        if type(self.is_active) is not bool:
            _invalid()
        _nominal(
            self.source_snapshot_id, "raos.domain.evidence.ids", "SourceSnapshotId"
        )
        if type(self.observed_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()

    def __repr__(self) -> str:
        return "RakutenGenreState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ReviewAggregateObservation:
    id: ReviewAggregateObservationId
    offer_id: OfferId
    review_count: int
    review_average: Decimal | None
    observed_at: AwareUtcDateTime
    ingested_at: AwareUtcDateTime
    source_snapshot_id: SourceSnapshotId
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not ReviewAggregateObservationId:
            _invalid()
        if type(self.offer_id) is not OfferId:
            _invalid()
        _integer(self.review_count)
        if self.review_average is not None:
            _decimal(self.review_average)
        if type(self.observed_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.ingested_at) is not AwareUtcDateTime:
            _invalid()
        _nominal(
            self.source_snapshot_id, "raos.domain.evidence.ids", "SourceSnapshotId"
        )
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "ReviewAggregateObservation(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ShopState:
    id: ShopId
    display_id: str
    provider_endpoint_id: ProviderEndpointId
    external_shop_code: str
    shop_name: str
    shop_url: UriReference | None
    affiliate_capable: bool
    status: ShopStatus
    first_observed_at: AwareUtcDateTime
    last_observed_at: AwareUtcDateTime
    source_snapshot_id: SourceSnapshotId
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not ShopId:
            _invalid()
        _text(self.display_id)
        if type(self.provider_endpoint_id) is not ProviderEndpointId:
            _invalid()
        _text(self.external_shop_code)
        _text(self.shop_name)
        if self.shop_url is not None:
            if type(self.shop_url) is not UriReference:
                _invalid()
        if type(self.affiliate_capable) is not bool:
            _invalid()
        if type(self.status) is not ShopStatus:
            _invalid()
        if type(self.first_observed_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.last_observed_at) is not AwareUtcDateTime:
            _invalid()
        _nominal(
            self.source_snapshot_id, "raos.domain.evidence.ids", "SourceSnapshotId"
        )
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()

    def __repr__(self) -> str:
        return "ShopState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SafeOfferCurrent:
    offer_id: OfferId
    product_id: CanonicalProductId
    shop_id: ShopId
    current_price_jpy: YenMinor | None
    current_shipping_fee_jpy: YenMinor | None
    current_availability: OfferCurrentProjectionCurrentAvailability | None
    review_count: int | None
    review_average: Decimal | None
    affiliate_url: UriReference | None
    destination_host: str | None
    price_observed_at: AwareUtcDateTime | None
    availability_observed_at: AwareUtcDateTime | None
    link_observed_at: AwareUtcDateTime | None
    freshness_status: OfferCurrentProjectionFreshnessStatus
    projection_version: int
    updated_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.offer_id) is not OfferId:
            _invalid()
        if type(self.product_id) is not CanonicalProductId:
            _invalid()
        if type(self.shop_id) is not ShopId:
            _invalid()
        if self.current_price_jpy is not None:
            if type(self.current_price_jpy) is not YenMinor:
                _invalid()
        if self.current_shipping_fee_jpy is not None:
            if type(self.current_shipping_fee_jpy) is not YenMinor:
                _invalid()
        if self.current_availability is not None:
            if (
                type(self.current_availability)
                is not OfferCurrentProjectionCurrentAvailability
            ):
                _invalid()
        if self.review_count is not None:
            _integer(self.review_count)
        if self.review_average is not None:
            _decimal(self.review_average)
        if self.affiliate_url is not None:
            if type(self.affiliate_url) is not UriReference:
                _invalid()
        if self.destination_host is not None:
            _text(self.destination_host)
        if self.price_observed_at is not None:
            if type(self.price_observed_at) is not AwareUtcDateTime:
                _invalid()
        if self.availability_observed_at is not None:
            if type(self.availability_observed_at) is not AwareUtcDateTime:
                _invalid()
        if self.link_observed_at is not None:
            if type(self.link_observed_at) is not AwareUtcDateTime:
                _invalid()
        if type(self.freshness_status) is not OfferCurrentProjectionFreshnessStatus:
            _invalid()
        _integer(self.projection_version)
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "SafeOfferCurrent(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AttributeDefinition:
    state: AttributeDefinitionState
    product_attribute_value_rows: tuple[ProductAttributeValue, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not AttributeDefinitionState:
            _invalid()
        if type(self.product_attribute_value_rows) is not tuple or any(
            type(item) is not ProductAttributeValue
            for item in self.product_attribute_value_rows
        ):
            _invalid()
        if any(
            item.attribute_definition_id.value != self.state.id.value
            for item in self.product_attribute_value_rows
        ):
            _invalid()

    def __repr__(self) -> str:
        return "AttributeDefinition(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalProduct:
    state: CanonicalProductState
    product_group_membership_rows: tuple[ProductGroupMembership, ...] = ()
    product_relation_rows: tuple[ProductRelation, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not CanonicalProductState:
            _invalid()
        if type(self.product_group_membership_rows) is not tuple or any(
            type(item) is not ProductGroupMembership
            for item in self.product_group_membership_rows
        ):
            _invalid()
        if any(
            item.product_id.value != self.state.id.value
            for item in self.product_group_membership_rows
        ):
            _invalid()
        if type(self.product_relation_rows) is not tuple or any(
            type(item) is not ProductRelation for item in self.product_relation_rows
        ):
            _invalid()
        if any(
            item.from_product_id.value != self.state.id.value
            for item in self.product_relation_rows
        ):
            _invalid()

    def __repr__(self) -> str:
        return "CanonicalProduct(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class GroupingDecision:
    state: GroupingDecisionState

    def __post_init__(self) -> None:
        if type(self.state) is not GroupingDecisionState:
            _invalid()

    def __repr__(self) -> str:
        return "GroupingDecision(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class IngestionRequest:
    state: IngestionRequestState

    def __post_init__(self) -> None:
        if type(self.state) is not IngestionRequestState:
            _invalid()

    def __repr__(self) -> str:
        return "IngestionRequest(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Offer:
    state: OfferState
    price_observation_rows: tuple[PriceObservation, ...] = ()
    availability_observation_rows: tuple[AvailabilityObservation, ...] = ()
    review_aggregate_observation_rows: tuple[ReviewAggregateObservation, ...] = ()
    affiliate_link_observation_rows: tuple[AffiliateLinkObservation, ...] = ()
    offer_current_projection: OfferCurrentProjection | None = None
    _event_buffer: PendingEventBuffer[DomainEvent] = field(
        default_factory=PendingEventBuffer[DomainEvent], init=False, compare=False
    )

    def __post_init__(self) -> None:
        if type(self.state) is not OfferState:
            _invalid()
        if type(self.price_observation_rows) is not tuple or any(
            type(item) is not PriceObservation for item in self.price_observation_rows
        ):
            _invalid()
        if any(
            item.offer_id.value != self.state.id.value
            for item in self.price_observation_rows
        ):
            _invalid()
        if type(self.availability_observation_rows) is not tuple or any(
            type(item) is not AvailabilityObservation
            for item in self.availability_observation_rows
        ):
            _invalid()
        if any(
            item.offer_id.value != self.state.id.value
            for item in self.availability_observation_rows
        ):
            _invalid()
        if type(self.review_aggregate_observation_rows) is not tuple or any(
            type(item) is not ReviewAggregateObservation
            for item in self.review_aggregate_observation_rows
        ):
            _invalid()
        if any(
            item.offer_id.value != self.state.id.value
            for item in self.review_aggregate_observation_rows
        ):
            _invalid()
        if type(self.affiliate_link_observation_rows) is not tuple or any(
            type(item) is not AffiliateLinkObservation
            for item in self.affiliate_link_observation_rows
        ):
            _invalid()
        if any(
            item.offer_id.value != self.state.id.value
            for item in self.affiliate_link_observation_rows
        ):
            _invalid()
        if (
            self.offer_current_projection is not None
            and type(self.offer_current_projection) is not OfferCurrentProjection
        ):
            _invalid()
        if (
            self.offer_current_projection is not None
            and self.offer_current_projection.offer_id.value != self.state.id.value
        ):
            _invalid()

    def pending_events(self) -> tuple[DomainEvent, ...]:
        return self._event_buffer.pending_events()

    def acknowledge_events(self, event_ids: tuple[UUID, ...]) -> None:
        if type(event_ids) is not tuple or any(
            type(item) is not UUID for item in event_ids
        ):
            _invalid()
        self._event_buffer.acknowledge_events(event_ids)

    def _record_event(self, event: DomainEvent) -> None:
        self._event_buffer.record(event)

    def _restore_acknowledged_events(self) -> None:
        self._event_buffer.restore_acknowledged()

    def _finish_acknowledged_events(self) -> None:
        self._event_buffer.finish_acknowledged()

    def __repr__(self) -> str:
        return "Offer(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ProductCandidate:
    state: ProductCandidateState

    def __post_init__(self) -> None:
        if type(self.state) is not ProductCandidateState:
            _invalid()

    def __repr__(self) -> str:
        return "ProductCandidate(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ProviderEndpoint:
    state: ProviderEndpointState

    def __post_init__(self) -> None:
        if type(self.state) is not ProviderEndpointState:
            _invalid()

    def __repr__(self) -> str:
        return "ProviderEndpoint(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RakutenGenre:
    state: RakutenGenreState
    category_genre_mapping_rows: tuple[CategoryGenreMapping, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not RakutenGenreState:
            _invalid()
        if type(self.category_genre_mapping_rows) is not tuple or any(
            type(item) is not CategoryGenreMapping
            for item in self.category_genre_mapping_rows
        ):
            _invalid()
        if any(
            item.rakuten_genre_id.value != self.state.id.value
            for item in self.category_genre_mapping_rows
        ):
            _invalid()

    def __repr__(self) -> str:
        return "RakutenGenre(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Shop:
    state: ShopState

    def __post_init__(self) -> None:
        if type(self.state) is not ShopState:
            _invalid()

    def __repr__(self) -> str:
        return "Shop(<redacted>)"


__all__ = [
    "AffiliateLinkObservation",
    "AttributeDefinition",
    "AttributeDefinitionState",
    "AvailabilityObservation",
    "CanonicalProduct",
    "CanonicalProductState",
    "CategoryGenreMapping",
    "GroupingDecision",
    "GroupingDecisionState",
    "IngestionRequest",
    "IngestionRequestState",
    "Offer",
    "OfferCurrentProjection",
    "OfferState",
    "PriceObservation",
    "ProductAttributeValue",
    "ProductCandidate",
    "ProductCandidateState",
    "ProductGroupMembership",
    "ProductRelation",
    "ProviderEndpoint",
    "ProviderEndpointState",
    "RakutenGenre",
    "RakutenGenreState",
    "ReviewAggregateObservation",
    "SafeOfferCurrent",
    "Shop",
    "ShopState",
]
