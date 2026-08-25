"""Concrete aggregate-specific SQLAlchemy repositories for CATALOG (ST-0308)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import json
from typing import Literal, NoReturn, TypeVar, cast, overload
from uuid import UUID

from sqlalchemy import Table, func, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.base import Executable
from sqlalchemy.sql.selectable import TableClause

import raos.adapters.persistence.sqlalchemy.mappers.catalog as domain_mappers
from raos.adapters.persistence.sqlalchemy.session_runtime import (
    aggregate_event_buffer,
    fail_session_operation,
    guard_repository_class,
    register_pending_events,
    stage_registered_events,
    transaction_timestamp,
)
from raos.domain.catalog.aggregates import (
    AffiliateLinkObservation,
    AttributeDefinition,
    AttributeDefinitionState,
    AvailabilityObservation,
    CanonicalProduct,
    CanonicalProductState,
    CategoryGenreMapping,
    GroupingDecision,
    GroupingDecisionState,
    IngestionRequest,
    IngestionRequestState,
    Offer,
    OfferCurrentProjection,
    OfferState,
    PriceObservation,
    ProductAttributeValue,
    ProductCandidate,
    ProductCandidateState,
    ProductGroupMembership,
    ProductRelation,
    ProviderEndpoint,
    ProviderEndpointState,
    RakutenGenre,
    RakutenGenreState,
    ReviewAggregateObservation,
    SafeOfferCurrent,
    Shop,
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
from raos.domain.iam.ids import (
    PrincipalId,
)
from raos.domain.evidence.ids import FactId, SourceSnapshotId
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
from raos.domain.shared.identity import EntityId
from raos.domain.shared.json_values import FrozenJsonObject, canonical_json_bytes
from raos.domain.shared.persistence import EmailAddress
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode

T = TypeVar("T")
RowData = Mapping[str, object] | RowMapping


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


def _table(relation: str) -> Table:
    try:
        from raos.adapters.persistence.sqlalchemy.generated.catalog import (
            TABLES_BY_RELATION,
        )

        table = cast(object, TABLES_BY_RELATION[relation])
    except ImportError, KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if not isinstance(table, Table):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return table


def _view(relation: str) -> TableClause:
    try:
        from raos.adapters.persistence.sqlalchemy.generated.catalog import (
            READ_ONLY_VIEWS,
        )

        view = cast(object, READ_ONLY_VIEWS[relation])
    except ImportError, KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if not isinstance(view, TableClause):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return view


def _exact(row: RowData, key: str, expected: type[T]) -> T:
    try:
        value = row[key]
    except KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if type(value) is not expected:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _optional(row: RowData, key: str, expected: type[T]) -> T | None:
    try:
        value = row[key]
    except KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if value is None:
        return None
    if type(value) is not expected:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _json_object(row: RowData, key: str) -> FrozenJsonObject:
    value = cast(dict[str, object], _exact(row, key, dict))
    try:
        return FrozenJsonObject.from_mapping(value)
    except ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


@overload
def _evidence_id(row: RowData, key: str, name: Literal["FactId"]) -> FactId: ...


@overload
def _evidence_id(
    row: RowData, key: str, name: Literal["SourceSnapshotId"]
) -> SourceSnapshotId: ...


def _evidence_id(
    row: RowData, key: str, name: Literal["FactId", "SourceSnapshotId"]
) -> FactId | SourceSnapshotId:
    try:
        raw = _exact(row, key, UUID)
        if name == "FactId":
            return FactId(raw)
        return SourceSnapshotId(raw)
    except ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_scalar(value: object) -> object:
    if value is None or type(value) in {str, int, bool, Decimal, date}:
        return value
    if isinstance(value, EntityId):
        return value.value
    if isinstance(value, Enum):
        return value.value
    if type(value) is AwareUtcDateTime:
        return value.value
    if isinstance(
        value,
        (AggregateVersion, YenMinor, Sha256Digest, EmailAddress, UriReference),
    ):
        return value.value
    if isinstance(
        value,
        (
            CanonicalProductIdentityAttributesJson,
            GroupingDecisionReasonsJson,
            IngestionRequestRateLimitObservationJson,
            IngestionRequestRequestParametersJson,
            ProductCandidateImageSetJson,
            ProviderEndpointNonSecretConfigJson,
        ),
    ):
        return json.loads(canonical_json_bytes(value.value))
    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encoded(columns: tuple[str, ...], values: tuple[object, ...]) -> dict[str, object]:
    if len(columns) != len(values):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return {
        column: _encode_scalar(value)
        for column, value in zip(columns, values, strict=True)
    }


def _execute_one(session: Session, statement: Executable) -> RowMapping | None:
    try:
        return session.execute(statement).mappings().one_or_none()
    except IntegrityError:
        fail_session_operation(session, PersistenceErrorCode.INTEGRITY_CONFLICT)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)


def _execute(session: Session, statement: Executable) -> None:
    try:
        session.execute(statement)
    except IntegrityError:
        fail_session_operation(session, PersistenceErrorCode.INTEGRITY_CONFLICT)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)


def _decode_catalog_affiliate_link_observation(
    row: RowData,
) -> AffiliateLinkObservation:
    try:
        return domain_mappers.map_catalog_affiliate_link_observation_from_row(
            id=AffiliateLinkObservationId(_exact(row, "id", UUID)),
            offer_id=OfferId(_exact(row, "offer_id", UUID)),
            affiliate_url=UriReference(_exact(row, "affiliate_url", str)),
            url_sha256=Sha256Digest(_exact(row, "url_sha256", str)),
            destination_host=_exact(row, "destination_host", str),
            is_api_returned=_exact(row, "is_api_returned", bool),
            affiliate_rate=_optional(row, "affiliate_rate", Decimal),
            observed_at=AwareUtcDateTime(_exact(row, "observed_at", datetime)),
            valid_until=(
                None
                if row.get("valid_until") is None
                else AwareUtcDateTime(_exact(row, "valid_until", datetime))
            ),
            source_snapshot_id=_evidence_id(
                row, "source_snapshot_id", "SourceSnapshotId"
            ),
            validation_status=AffiliateLinkObservationValidationStatus(
                _exact(row, "validation_status", str)
            ),
            link_contract_version=_exact(row, "link_contract_version", str),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_affiliate_link_observation(
    value: AffiliateLinkObservation,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "offer_id",
            "affiliate_url",
            "url_sha256",
            "destination_host",
            "is_api_returned",
            "affiliate_rate",
            "observed_at",
            "valid_until",
            "source_snapshot_id",
            "validation_status",
            "link_contract_version",
            "created_at",
        ),
        domain_mappers.map_catalog_affiliate_link_observation_to_row(value),
    )


def _decode_catalog_attribute_definition(
    row: RowData,
) -> AttributeDefinitionState:
    try:
        return domain_mappers.map_catalog_attribute_definition_from_row(
            id=AttributeDefinitionId(_exact(row, "id", UUID)),
            category_id=(
                None
                if row.get("category_id") is None
                else CategoryId(_exact(row, "category_id", UUID))
            ),
            attribute_code=_exact(row, "attribute_code", str),
            name=_exact(row, "name", str),
            data_type=AttributeDefinitionDataType(_exact(row, "data_type", str)),
            unit_family=_optional(row, "unit_family", str),
            is_comparable=_exact(row, "is_comparable", bool),
            is_required=_exact(row, "is_required", bool),
            normalization_rule_version=_exact(row, "normalization_rule_version", str),
            status=AttributeDefinitionStatus(_exact(row, "status", str)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_attribute_definition(
    value: AttributeDefinitionState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "category_id",
            "attribute_code",
            "name",
            "data_type",
            "unit_family",
            "is_comparable",
            "is_required",
            "normalization_rule_version",
            "status",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_catalog_attribute_definition_to_row(value),
    )


def _decode_catalog_availability_observation(
    row: RowData,
) -> AvailabilityObservation:
    try:
        return domain_mappers.map_catalog_availability_observation_from_row(
            id=AvailabilityObservationId(_exact(row, "id", UUID)),
            offer_id=OfferId(_exact(row, "offer_id", UUID)),
            availability=AvailabilityObservationAvailability(
                _exact(row, "availability", str)
            ),
            quantity=_optional(row, "quantity", int),
            lead_time_text=_optional(row, "lead_time_text", str),
            observed_at=AwareUtcDateTime(_exact(row, "observed_at", datetime)),
            ingested_at=AwareUtcDateTime(_exact(row, "ingested_at", datetime)),
            valid_until=(
                None
                if row.get("valid_until") is None
                else AwareUtcDateTime(_exact(row, "valid_until", datetime))
            ),
            source_snapshot_id=_evidence_id(
                row, "source_snapshot_id", "SourceSnapshotId"
            ),
            validation_status=AvailabilityObservationValidationStatus(
                _exact(row, "validation_status", str)
            ),
            confidence=_exact(row, "confidence", Decimal),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_availability_observation(
    value: AvailabilityObservation,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "offer_id",
            "availability",
            "quantity",
            "lead_time_text",
            "observed_at",
            "ingested_at",
            "valid_until",
            "source_snapshot_id",
            "validation_status",
            "confidence",
            "created_at",
        ),
        domain_mappers.map_catalog_availability_observation_to_row(value),
    )


def _decode_catalog_canonical_product(
    row: RowData,
) -> CanonicalProductState:
    try:
        return domain_mappers.map_catalog_canonical_product_from_row(
            id=CanonicalProductId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            category_id=CategoryId(_exact(row, "category_id", UUID)),
            canonical_name=_exact(row, "canonical_name", str),
            brand_name=_optional(row, "brand_name", str),
            manufacturer_name=_optional(row, "manufacturer_name", str),
            model_number=_optional(row, "model_number", str),
            jan_code=_optional(row, "jan_code", str),
            product_type=_exact(row, "product_type", str),
            lifecycle_status=CanonicalProductLifecycleStatus(
                _exact(row, "lifecycle_status", str)
            ),
            identity_confidence=_exact(row, "identity_confidence", Decimal),
            identity_attributes=CanonicalProductIdentityAttributesJson(
                _json_object(row, "identity_attributes")
            ),
            merged_into_product_id=(
                None
                if row.get("merged_into_product_id") is None
                else CanonicalProductId(_exact(row, "merged_into_product_id", UUID))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_canonical_product(
    value: CanonicalProductState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "category_id",
            "canonical_name",
            "brand_name",
            "manufacturer_name",
            "model_number",
            "jan_code",
            "product_type",
            "lifecycle_status",
            "identity_confidence",
            "identity_attributes",
            "merged_into_product_id",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_catalog_canonical_product_to_row(value),
    )


def _decode_catalog_category_genre_mapping(
    row: RowData,
) -> CategoryGenreMapping:
    try:
        return domain_mappers.map_catalog_category_genre_mapping_from_row(
            id=CategoryGenreMappingId(_exact(row, "id", UUID)),
            category_id=CategoryId(_exact(row, "category_id", UUID)),
            rakuten_genre_id=RakutenGenreId(_exact(row, "rakuten_genre_id", UUID)),
            mapping_role=CategoryGenreMappingMappingRole(
                _exact(row, "mapping_role", str)
            ),
            valid_from=AwareUtcDateTime(_exact(row, "valid_from", datetime)),
            valid_to=(
                None
                if row.get("valid_to") is None
                else AwareUtcDateTime(_exact(row, "valid_to", datetime))
            ),
            decision_reason=_exact(row, "decision_reason", str),
            decided_by_principal_id=PrincipalId(
                _exact(row, "decided_by_principal_id", UUID)
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_category_genre_mapping(
    value: CategoryGenreMapping,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "category_id",
            "rakuten_genre_id",
            "mapping_role",
            "valid_from",
            "valid_to",
            "decision_reason",
            "decided_by_principal_id",
            "created_at",
        ),
        domain_mappers.map_catalog_category_genre_mapping_to_row(value),
    )


def _decode_catalog_grouping_decision(
    row: RowData,
) -> GroupingDecisionState:
    try:
        return domain_mappers.map_catalog_grouping_decision_from_row(
            id=GroupingDecisionId(_exact(row, "id", UUID)),
            product_candidate_id=ProductCandidateId(
                _exact(row, "product_candidate_id", UUID)
            ),
            proposed_product_id=(
                None
                if row.get("proposed_product_id") is None
                else CanonicalProductId(_exact(row, "proposed_product_id", UUID))
            ),
            decision_type=GroupingDecisionDecisionType(
                _exact(row, "decision_type", str)
            ),
            decision_score=_optional(row, "decision_score", Decimal),
            rule_version=_exact(row, "rule_version", str),
            reasons=GroupingDecisionReasonsJson(_json_object(row, "reasons")),
            decided_by_actor_type=_exact(row, "decided_by_actor_type", str),
            decided_by_actor_id=(
                None
                if row.get("decided_by_actor_id") is None
                else DecidedByActorId(_exact(row, "decided_by_actor_id", UUID))
            ),
            decided_at=AwareUtcDateTime(_exact(row, "decided_at", datetime)),
            supersedes_decision_id=(
                None
                if row.get("supersedes_decision_id") is None
                else GroupingDecisionId(_exact(row, "supersedes_decision_id", UUID))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_grouping_decision(
    value: GroupingDecisionState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "product_candidate_id",
            "proposed_product_id",
            "decision_type",
            "decision_score",
            "rule_version",
            "reasons",
            "decided_by_actor_type",
            "decided_by_actor_id",
            "decided_at",
            "supersedes_decision_id",
            "created_at",
        ),
        domain_mappers.map_catalog_grouping_decision_to_row(value),
    )


def _decode_catalog_ingestion_request(
    row: RowData,
) -> IngestionRequestState:
    try:
        return domain_mappers.map_catalog_ingestion_request_from_row(
            id=IngestionRequestId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            provider_endpoint_id=ProviderEndpointId(
                _exact(row, "provider_endpoint_id", UUID)
            ),
            job_id=JobId(_exact(row, "job_id", UUID)),
            request_fingerprint=_exact(row, "request_fingerprint", str),
            request_parameters=IngestionRequestRequestParametersJson(
                _json_object(row, "request_parameters")
            ),
            requested_at=AwareUtcDateTime(_exact(row, "requested_at", datetime)),
            responded_at=(
                None
                if row.get("responded_at") is None
                else AwareUtcDateTime(_exact(row, "responded_at", datetime))
            ),
            http_status=_optional(row, "http_status", int),
            status=IngestionRequestStatus(_exact(row, "status", str)),
            raw_response_artifact_id=(
                None
                if row.get("raw_response_artifact_id") is None
                else ObjectArtifactId(_exact(row, "raw_response_artifact_id", UUID))
            ),
            item_count=_optional(row, "item_count", int),
            rate_limit_observation=IngestionRequestRateLimitObservationJson(
                _json_object(row, "rate_limit_observation")
            ),
            error_class=_optional(row, "error_class", str),
            error_code=_optional(row, "error_code", str),
            error_message=_optional(row, "error_message", str),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_ingestion_request(
    value: IngestionRequestState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "provider_endpoint_id",
            "job_id",
            "request_fingerprint",
            "request_parameters",
            "requested_at",
            "responded_at",
            "http_status",
            "status",
            "raw_response_artifact_id",
            "item_count",
            "rate_limit_observation",
            "error_class",
            "error_code",
            "error_message",
            "created_at",
        ),
        domain_mappers.map_catalog_ingestion_request_to_row(value),
    )


def _decode_catalog_offer(row: RowData) -> OfferState:
    try:
        return domain_mappers.map_catalog_offer_from_row(
            id=OfferId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            provider_endpoint_id=ProviderEndpointId(
                _exact(row, "provider_endpoint_id", UUID)
            ),
            external_offer_id=_exact(row, "external_offer_id", str),
            product_candidate_id=ProductCandidateId(
                _exact(row, "product_candidate_id", UUID)
            ),
            product_id=(
                None
                if row.get("product_id") is None
                else CanonicalProductId(_exact(row, "product_id", UUID))
            ),
            shop_id=ShopId(_exact(row, "shop_id", UUID)),
            item_url=UriReference(_exact(row, "item_url", str)),
            status=OfferStatus(_exact(row, "status", str)),
            first_observed_at=AwareUtcDateTime(
                _exact(row, "first_observed_at", datetime)
            ),
            last_observed_at=AwareUtcDateTime(
                _exact(row, "last_observed_at", datetime)
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_offer(value: OfferState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "provider_endpoint_id",
            "external_offer_id",
            "product_candidate_id",
            "product_id",
            "shop_id",
            "item_url",
            "status",
            "first_observed_at",
            "last_observed_at",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_catalog_offer_to_row(value),
    )


def _decode_catalog_offer_current_projection(
    row: RowData,
) -> OfferCurrentProjection:
    try:
        return domain_mappers.map_catalog_offer_current_projection_from_row(
            offer_id=OfferId(_exact(row, "offer_id", UUID)),
            product_id=(
                None
                if row.get("product_id") is None
                else CanonicalProductId(_exact(row, "product_id", UUID))
            ),
            price_observation_id=(
                None
                if row.get("price_observation_id") is None
                else PriceObservationId(_exact(row, "price_observation_id", UUID))
            ),
            availability_observation_id=(
                None
                if row.get("availability_observation_id") is None
                else AvailabilityObservationId(
                    _exact(row, "availability_observation_id", UUID)
                )
            ),
            review_observation_id=(
                None
                if row.get("review_observation_id") is None
                else ReviewAggregateObservationId(
                    _exact(row, "review_observation_id", UUID)
                )
            ),
            affiliate_link_observation_id=(
                None
                if row.get("affiliate_link_observation_id") is None
                else AffiliateLinkObservationId(
                    _exact(row, "affiliate_link_observation_id", UUID)
                )
            ),
            current_price_jpy=(
                None
                if row.get("current_price_jpy") is None
                else YenMinor(_exact(row, "current_price_jpy", int))
            ),
            current_shipping_fee_jpy=(
                None
                if row.get("current_shipping_fee_jpy") is None
                else YenMinor(_exact(row, "current_shipping_fee_jpy", int))
            ),
            current_availability=OfferCurrentProjectionCurrentAvailability(
                _exact(row, "current_availability", str)
            ),
            review_count=_optional(row, "review_count", int),
            review_average=_optional(row, "review_average", Decimal),
            affiliate_url=(
                None
                if row.get("affiliate_url") is None
                else UriReference(_exact(row, "affiliate_url", str))
            ),
            destination_host=_optional(row, "destination_host", str),
            price_observed_at=(
                None
                if row.get("price_observed_at") is None
                else AwareUtcDateTime(_exact(row, "price_observed_at", datetime))
            ),
            availability_observed_at=(
                None
                if row.get("availability_observed_at") is None
                else AwareUtcDateTime(_exact(row, "availability_observed_at", datetime))
            ),
            link_observed_at=(
                None
                if row.get("link_observed_at") is None
                else AwareUtcDateTime(_exact(row, "link_observed_at", datetime))
            ),
            freshness_status=OfferCurrentProjectionFreshnessStatus(
                _exact(row, "freshness_status", str)
            ),
            projection_version=_exact(row, "projection_version", int),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_offer_current_projection(
    value: OfferCurrentProjection,
) -> dict[str, object]:
    return _encoded(
        (
            "offer_id",
            "product_id",
            "price_observation_id",
            "availability_observation_id",
            "review_observation_id",
            "affiliate_link_observation_id",
            "current_price_jpy",
            "current_shipping_fee_jpy",
            "current_availability",
            "review_count",
            "review_average",
            "affiliate_url",
            "destination_host",
            "price_observed_at",
            "availability_observed_at",
            "link_observed_at",
            "freshness_status",
            "projection_version",
            "updated_at",
        ),
        domain_mappers.map_catalog_offer_current_projection_to_row(value),
    )


def _decode_catalog_price_observation(row: RowData) -> PriceObservation:
    try:
        return domain_mappers.map_catalog_price_observation_from_row(
            id=PriceObservationId(_exact(row, "id", UUID)),
            offer_id=OfferId(_exact(row, "offer_id", UUID)),
            price_jpy=YenMinor(_exact(row, "price_jpy", int)),
            tax_included=_exact(row, "tax_included", bool),
            shipping_fee_jpy=(
                None
                if row.get("shipping_fee_jpy") is None
                else YenMinor(_exact(row, "shipping_fee_jpy", int))
            ),
            shipping_condition=PriceObservationShippingCondition(
                _exact(row, "shipping_condition", str)
            ),
            points_rate=_optional(row, "points_rate", Decimal),
            observed_at=AwareUtcDateTime(_exact(row, "observed_at", datetime)),
            ingested_at=AwareUtcDateTime(_exact(row, "ingested_at", datetime)),
            valid_until=(
                None
                if row.get("valid_until") is None
                else AwareUtcDateTime(_exact(row, "valid_until", datetime))
            ),
            source_snapshot_id=_evidence_id(
                row, "source_snapshot_id", "SourceSnapshotId"
            ),
            validation_status=PriceObservationValidationStatus(
                _exact(row, "validation_status", str)
            ),
            confidence=_exact(row, "confidence", Decimal),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_price_observation(value: PriceObservation) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "offer_id",
            "price_jpy",
            "tax_included",
            "shipping_fee_jpy",
            "shipping_condition",
            "points_rate",
            "observed_at",
            "ingested_at",
            "valid_until",
            "source_snapshot_id",
            "validation_status",
            "confidence",
            "created_at",
        ),
        domain_mappers.map_catalog_price_observation_to_row(value),
    )


def _decode_catalog_product_attribute_value(
    row: RowData,
) -> ProductAttributeValue:
    try:
        return domain_mappers.map_catalog_product_attribute_value_from_row(
            id=ProductAttributeValueId(_exact(row, "id", UUID)),
            product_id=CanonicalProductId(_exact(row, "product_id", UUID)),
            attribute_definition_id=AttributeDefinitionId(
                _exact(row, "attribute_definition_id", UUID)
            ),
            value_text=_optional(row, "value_text", str),
            value_numeric=_optional(row, "value_numeric", Decimal),
            value_boolean=_optional(row, "value_boolean", bool),
            value_date=_optional(row, "value_date", date),
            value_code=_optional(row, "value_code", str),
            unit_code=_optional(row, "unit_code", str),
            source_fact_id=(
                None
                if row.get("source_fact_id") is None
                else _evidence_id(row, "source_fact_id", "FactId")
            ),
            confidence=_exact(row, "confidence", Decimal),
            valid_from=AwareUtcDateTime(_exact(row, "valid_from", datetime)),
            valid_to=(
                None
                if row.get("valid_to") is None
                else AwareUtcDateTime(_exact(row, "valid_to", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_product_attribute_value(
    value: ProductAttributeValue,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "product_id",
            "attribute_definition_id",
            "value_text",
            "value_numeric",
            "value_boolean",
            "value_date",
            "value_code",
            "unit_code",
            "source_fact_id",
            "confidence",
            "valid_from",
            "valid_to",
            "created_at",
        ),
        domain_mappers.map_catalog_product_attribute_value_to_row(value),
    )


def _decode_catalog_product_candidate(
    row: RowData,
) -> ProductCandidateState:
    try:
        return domain_mappers.map_catalog_product_candidate_from_row(
            id=ProductCandidateId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            provider_endpoint_id=ProviderEndpointId(
                _exact(row, "provider_endpoint_id", UUID)
            ),
            external_item_code=_exact(row, "external_item_code", str),
            shop_id=ShopId(_exact(row, "shop_id", UUID)),
            rakuten_genre_id=(
                None
                if row.get("rakuten_genre_id") is None
                else RakutenGenreId(_exact(row, "rakuten_genre_id", UUID))
            ),
            item_name=_exact(row, "item_name", str),
            normalized_item_name=_exact(row, "normalized_item_name", str),
            model_number_candidate=_optional(row, "model_number_candidate", str),
            jan_code_candidate=_optional(row, "jan_code_candidate", str),
            image_set=ProductCandidateImageSetJson(_json_object(row, "image_set")),
            listing_status=ProductCandidateListingStatus(
                _exact(row, "listing_status", str)
            ),
            first_observed_at=AwareUtcDateTime(
                _exact(row, "first_observed_at", datetime)
            ),
            last_observed_at=AwareUtcDateTime(
                _exact(row, "last_observed_at", datetime)
            ),
            source_snapshot_id=_evidence_id(
                row, "source_snapshot_id", "SourceSnapshotId"
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_product_candidate(
    value: ProductCandidateState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "provider_endpoint_id",
            "external_item_code",
            "shop_id",
            "rakuten_genre_id",
            "item_name",
            "normalized_item_name",
            "model_number_candidate",
            "jan_code_candidate",
            "image_set",
            "listing_status",
            "first_observed_at",
            "last_observed_at",
            "source_snapshot_id",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_catalog_product_candidate_to_row(value),
    )


def _decode_catalog_product_group_membership(
    row: RowData,
) -> ProductGroupMembership:
    try:
        return domain_mappers.map_catalog_product_group_membership_from_row(
            id=ProductGroupMembershipId(_exact(row, "id", UUID)),
            product_id=CanonicalProductId(_exact(row, "product_id", UUID)),
            product_candidate_id=ProductCandidateId(
                _exact(row, "product_candidate_id", UUID)
            ),
            grouping_decision_id=GroupingDecisionId(
                _exact(row, "grouping_decision_id", UUID)
            ),
            valid_from=AwareUtcDateTime(_exact(row, "valid_from", datetime)),
            valid_to=(
                None
                if row.get("valid_to") is None
                else AwareUtcDateTime(_exact(row, "valid_to", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_product_group_membership(
    value: ProductGroupMembership,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "product_id",
            "product_candidate_id",
            "grouping_decision_id",
            "valid_from",
            "valid_to",
            "created_at",
        ),
        domain_mappers.map_catalog_product_group_membership_to_row(value),
    )


def _decode_catalog_product_relation(row: RowData) -> ProductRelation:
    try:
        return domain_mappers.map_catalog_product_relation_from_row(
            id=ProductRelationId(_exact(row, "id", UUID)),
            from_product_id=CanonicalProductId(_exact(row, "from_product_id", UUID)),
            to_product_id=CanonicalProductId(_exact(row, "to_product_id", UUID)),
            relation_type=ProductRelationRelationType(
                _exact(row, "relation_type", str)
            ),
            confidence=_exact(row, "confidence", Decimal),
            source_fact_id=(
                None
                if row.get("source_fact_id") is None
                else _evidence_id(row, "source_fact_id", "FactId")
            ),
            valid_from=AwareUtcDateTime(_exact(row, "valid_from", datetime)),
            valid_to=(
                None
                if row.get("valid_to") is None
                else AwareUtcDateTime(_exact(row, "valid_to", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_product_relation(value: ProductRelation) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "from_product_id",
            "to_product_id",
            "relation_type",
            "confidence",
            "source_fact_id",
            "valid_from",
            "valid_to",
            "created_at",
        ),
        domain_mappers.map_catalog_product_relation_to_row(value),
    )


def _decode_catalog_provider_endpoint(
    row: RowData,
) -> ProviderEndpointState:
    try:
        return domain_mappers.map_catalog_provider_endpoint_from_row(
            id=ProviderEndpointId(_exact(row, "id", UUID)),
            provider_code=_exact(row, "provider_code", str),
            provider_name=_exact(row, "provider_name", str),
            api_name=_exact(row, "api_name", str),
            api_version=_exact(row, "api_version", str),
            base_host=_exact(row, "base_host", str),
            status=ProviderEndpointStatus(_exact(row, "status", str)),
            contract_sha256=Sha256Digest(_exact(row, "contract_sha256", str)),
            documentation_url=(
                None
                if row.get("documentation_url") is None
                else UriReference(_exact(row, "documentation_url", str))
            ),
            non_secret_config=ProviderEndpointNonSecretConfigJson(
                _json_object(row, "non_secret_config")
            ),
            effective_from=AwareUtcDateTime(_exact(row, "effective_from", datetime)),
            effective_to=(
                None
                if row.get("effective_to") is None
                else AwareUtcDateTime(_exact(row, "effective_to", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_provider_endpoint(
    value: ProviderEndpointState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "provider_code",
            "provider_name",
            "api_name",
            "api_version",
            "base_host",
            "status",
            "contract_sha256",
            "documentation_url",
            "non_secret_config",
            "effective_from",
            "effective_to",
            "created_at",
        ),
        domain_mappers.map_catalog_provider_endpoint_to_row(value),
    )


def _decode_catalog_rakuten_genre(row: RowData) -> RakutenGenreState:
    try:
        return domain_mappers.map_catalog_rakuten_genre_from_row(
            id=RakutenGenreId(_exact(row, "id", UUID)),
            provider_endpoint_id=ProviderEndpointId(
                _exact(row, "provider_endpoint_id", UUID)
            ),
            external_genre_id=_exact(row, "external_genre_id", int),
            parent_external_genre_id=_optional(row, "parent_external_genre_id", int),
            genre_name=_exact(row, "genre_name", str),
            genre_level=_exact(row, "genre_level", int),
            is_leaf=_exact(row, "is_leaf", bool),
            is_active=_exact(row, "is_active", bool),
            source_snapshot_id=_evidence_id(
                row, "source_snapshot_id", "SourceSnapshotId"
            ),
            observed_at=AwareUtcDateTime(_exact(row, "observed_at", datetime)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_rakuten_genre(value: RakutenGenreState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "provider_endpoint_id",
            "external_genre_id",
            "parent_external_genre_id",
            "genre_name",
            "genre_level",
            "is_leaf",
            "is_active",
            "source_snapshot_id",
            "observed_at",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_catalog_rakuten_genre_to_row(value),
    )


def _decode_catalog_review_aggregate_observation(
    row: RowData,
) -> ReviewAggregateObservation:
    try:
        return domain_mappers.map_catalog_review_aggregate_observation_from_row(
            id=ReviewAggregateObservationId(_exact(row, "id", UUID)),
            offer_id=OfferId(_exact(row, "offer_id", UUID)),
            review_count=_exact(row, "review_count", int),
            review_average=_optional(row, "review_average", Decimal),
            observed_at=AwareUtcDateTime(_exact(row, "observed_at", datetime)),
            ingested_at=AwareUtcDateTime(_exact(row, "ingested_at", datetime)),
            source_snapshot_id=_evidence_id(
                row, "source_snapshot_id", "SourceSnapshotId"
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_review_aggregate_observation(
    value: ReviewAggregateObservation,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "offer_id",
            "review_count",
            "review_average",
            "observed_at",
            "ingested_at",
            "source_snapshot_id",
            "created_at",
        ),
        domain_mappers.map_catalog_review_aggregate_observation_to_row(value),
    )


def _decode_catalog_shop(row: RowData) -> ShopState:
    try:
        return domain_mappers.map_catalog_shop_from_row(
            id=ShopId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            provider_endpoint_id=ProviderEndpointId(
                _exact(row, "provider_endpoint_id", UUID)
            ),
            external_shop_code=_exact(row, "external_shop_code", str),
            shop_name=_exact(row, "shop_name", str),
            shop_url=(
                None
                if row.get("shop_url") is None
                else UriReference(_exact(row, "shop_url", str))
            ),
            affiliate_capable=_exact(row, "affiliate_capable", bool),
            status=ShopStatus(_exact(row, "status", str)),
            first_observed_at=AwareUtcDateTime(
                _exact(row, "first_observed_at", datetime)
            ),
            last_observed_at=AwareUtcDateTime(
                _exact(row, "last_observed_at", datetime)
            ),
            source_snapshot_id=_evidence_id(
                row, "source_snapshot_id", "SourceSnapshotId"
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_catalog_shop(value: ShopState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "provider_endpoint_id",
            "external_shop_code",
            "shop_name",
            "shop_url",
            "affiliate_capable",
            "status",
            "first_observed_at",
            "last_observed_at",
            "source_snapshot_id",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_catalog_shop_to_row(value),
    )


def _decode_catalog_v_safe_offer_current(row: RowData) -> SafeOfferCurrent:
    try:
        return domain_mappers.map_catalog_v_safe_offer_current_from_row(
            offer_id=OfferId(_exact(row, "offer_id", UUID)),
            product_id=CanonicalProductId(_exact(row, "product_id", UUID)),
            shop_id=ShopId(_exact(row, "shop_id", UUID)),
            current_price_jpy=(
                None
                if row.get("current_price_jpy") is None
                else YenMinor(_exact(row, "current_price_jpy", int))
            ),
            current_shipping_fee_jpy=(
                None
                if row.get("current_shipping_fee_jpy") is None
                else YenMinor(_exact(row, "current_shipping_fee_jpy", int))
            ),
            current_availability=(
                None
                if row.get("current_availability") is None
                else OfferCurrentProjectionCurrentAvailability(
                    _exact(row, "current_availability", str)
                )
            ),
            review_count=_optional(row, "review_count", int),
            review_average=_optional(row, "review_average", Decimal),
            affiliate_url=(
                None
                if row.get("affiliate_url") is None
                else UriReference(_exact(row, "affiliate_url", str))
            ),
            destination_host=_optional(row, "destination_host", str),
            price_observed_at=(
                None
                if row.get("price_observed_at") is None
                else AwareUtcDateTime(_exact(row, "price_observed_at", datetime))
            ),
            availability_observed_at=(
                None
                if row.get("availability_observed_at") is None
                else AwareUtcDateTime(_exact(row, "availability_observed_at", datetime))
            ),
            link_observed_at=(
                None
                if row.get("link_observed_at") is None
                else AwareUtcDateTime(_exact(row, "link_observed_at", datetime))
            ),
            freshness_status=OfferCurrentProjectionFreshnessStatus(
                _exact(row, "freshness_status", str)
            ),
            projection_version=_exact(row, "projection_version", int),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


# Aggregate-specific classes below are the only DML surface.


def _cas_update(
    session: Session,
    table: Table,
    aggregate_id: UUID,
    expected_version: AggregateVersion,
    values: dict[str, object],
) -> AggregateVersion:
    values = dict(values)
    values.pop("id")
    values["lock_version"] = expected_version.value + 1
    try:
        persisted = session.execute(
            update(table)
            .where(
                table.c.id == aggregate_id,
                table.c.lock_version == expected_version.value,
            )
            .values(**values)
            .returning(table.c.lock_version)
        ).scalar_one_or_none()
    except IntegrityError:
        fail_session_operation(session, PersistenceErrorCode.INTEGRITY_CONFLICT)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    if type(persisted) is int:
        return AggregateVersion(persisted)
    observed = _execute_one(
        session, select(table.c.lock_version).where(table.c.id == aggregate_id)
    )
    if observed is None:
        _fail(PersistenceErrorCode.NOT_FOUND)
    if _exact(observed, "lock_version", int) != expected_version.value:
        _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


@guard_repository_class
class SqlAlchemyProviderEndpointRepository:
    __slots__ = ("_session", "_table")

    _EDGES = frozenset(
        {
            (ProviderEndpointStatus.DRAFT, ProviderEndpointStatus.ACTIVE),
            (ProviderEndpointStatus.DRAFT, ProviderEndpointStatus.BLOCKED),
            (ProviderEndpointStatus.DRAFT, ProviderEndpointStatus.RETIRED),
            (ProviderEndpointStatus.ACTIVE, ProviderEndpointStatus.DEPRECATED),
            (ProviderEndpointStatus.ACTIVE, ProviderEndpointStatus.BLOCKED),
            (ProviderEndpointStatus.ACTIVE, ProviderEndpointStatus.RETIRED),
            (ProviderEndpointStatus.DEPRECATED, ProviderEndpointStatus.ACTIVE),
            (ProviderEndpointStatus.DEPRECATED, ProviderEndpointStatus.BLOCKED),
            (ProviderEndpointStatus.DEPRECATED, ProviderEndpointStatus.RETIRED),
            (ProviderEndpointStatus.BLOCKED, ProviderEndpointStatus.DRAFT),
            (ProviderEndpointStatus.BLOCKED, ProviderEndpointStatus.DEPRECATED),
            (ProviderEndpointStatus.BLOCKED, ProviderEndpointStatus.RETIRED),
        }
    )

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_CATALOG_REPOSITORY") from None
        self._session = session
        self._table = _table("catalog.provider_endpoint")

    def get(self, endpoint_id: ProviderEndpointId) -> ProviderEndpoint | None:
        if type(endpoint_id) is not ProviderEndpointId:
            raise ValueError("INVALID_PROVIDER_ENDPOINT_ID") from None
        row = _execute_one(
            self._session,
            select(self._table).where(self._table.c.id == endpoint_id.value),
        )
        return (
            None
            if row is None
            else ProviderEndpoint(_decode_catalog_provider_endpoint(row))
        )

    def get_active(self, provider_code: str, api_name: str) -> ProviderEndpoint | None:
        if (
            type(provider_code) is not str
            or not provider_code
            or type(api_name) is not str
            or not api_name
        ):
            raise ValueError("INVALID_PROVIDER_ENDPOINT_LOOKUP") from None
        row = _execute_one(
            self._session,
            select(self._table).where(
                self._table.c.provider_code == provider_code,
                self._table.c.api_name == api_name,
                self._table.c.status == ProviderEndpointStatus.ACTIVE.value,
                self._table.c.effective_to.is_(None),
            ),
        )
        return (
            None
            if row is None
            else ProviderEndpoint(_decode_catalog_provider_endpoint(row))
        )

    def add(self, endpoint: ProviderEndpoint) -> None:
        if type(endpoint) is not ProviderEndpoint:
            raise ValueError("INVALID_PROVIDER_ENDPOINT") from None
        _execute(
            self._session,
            insert(self._table).values(
                **_encode_catalog_provider_endpoint(endpoint.state)
            ),
        )

    def transition(
        self,
        endpoint_id: ProviderEndpointId,
        transition: ProviderEndpoint,
        expected_status: ProviderEndpointStatus,
    ) -> ProviderEndpoint:
        if (
            type(endpoint_id) is not ProviderEndpointId
            or type(transition) is not ProviderEndpoint
            or transition.state.id != endpoint_id
            or type(expected_status) is not ProviderEndpointStatus
            or (expected_status, transition.state.status) not in self._EDGES
        ):
            raise ValueError("INVALID_PROVIDER_ENDPOINT_TRANSITION") from None
        current = self.get(endpoint_id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        if current.state.status is not expected_status:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if (
            current.state.id,
            current.state.provider_code,
            current.state.provider_name,
            current.state.api_name,
            current.state.api_version,
            current.state.base_host,
            current.state.contract_sha256,
            current.state.documentation_url,
            current.state.non_secret_config,
            current.state.created_at,
        ) != (
            transition.state.id,
            transition.state.provider_code,
            transition.state.provider_name,
            transition.state.api_name,
            transition.state.api_version,
            transition.state.base_host,
            transition.state.contract_sha256,
            transition.state.documentation_url,
            transition.state.non_secret_config,
            transition.state.created_at,
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        target_status = transition.state.status
        conditions = [
            self._table.c.id == endpoint_id.value,
            self._table.c.status == expected_status.value,
        ]
        values: dict[str, object] = {"status": target_status.value}
        if target_status is ProviderEndpointStatus.ACTIVE:
            at = transaction_timestamp(self._session)
            expected_effective_from = current.state.effective_from
            if (
                transition.state.effective_from != expected_effective_from
                or transition.state.effective_to is not None
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            values.update(
                effective_from=func.coalesce(self._table.c.effective_from, at.value),
                effective_to=None,
            )
        elif expected_status is ProviderEndpointStatus.ACTIVE and target_status in {
            ProviderEndpointStatus.DEPRECATED,
            ProviderEndpointStatus.RETIRED,
        }:
            at = transaction_timestamp(self._session)
            if (
                current.state.effective_to is not None
                or transition.state.effective_from != current.state.effective_from
                or transition.state.effective_to is None
                or transition.state.effective_to.value != at.value
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            conditions.append(self._table.c.effective_to.is_(None))
            values["effective_to"] = at.value
        elif (
            transition.state.effective_from != current.state.effective_from
            or transition.state.effective_to != current.state.effective_to
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        row = _execute_one(
            self._session,
            update(self._table)
            .where(*conditions)
            .values(**values)
            .returning(self._table),
        )
        if row is None:
            observed = self.get(endpoint_id)
            if observed is None:
                _fail(PersistenceErrorCode.NOT_FOUND)
            if observed.state.status is not expected_status or (
                expected_status is ProviderEndpointStatus.ACTIVE
                and target_status
                in {
                    ProviderEndpointStatus.DEPRECATED,
                    ProviderEndpointStatus.RETIRED,
                }
                and observed.state.effective_to is not None
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        persisted = ProviderEndpoint(_decode_catalog_provider_endpoint(row))
        if persisted.state != transition.state:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return persisted


@guard_repository_class
class SqlAlchemyIngestionRequestRepository:
    __slots__ = ("_session", "_table")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_CATALOG_REPOSITORY") from None
        self._session = session
        self._table = _table("catalog.ingestion_request")

    def get(self, request_id: IngestionRequestId) -> IngestionRequest | None:
        if type(request_id) is not IngestionRequestId:
            raise ValueError("INVALID_INGESTION_REQUEST_ID") from None
        row = _execute_one(
            self._session,
            select(self._table).where(self._table.c.id == request_id.value),
        )
        return (
            None
            if row is None
            else IngestionRequest(_decode_catalog_ingestion_request(row))
        )

    def add(self, request: IngestionRequest) -> None:
        if (
            type(request) is not IngestionRequest
            or request.state.status is not IngestionRequestStatus.REQUESTED
            or any(
                value is not None
                for value in (
                    request.state.responded_at,
                    request.state.http_status,
                    request.state.raw_response_artifact_id,
                    request.state.item_count,
                    request.state.error_class,
                    request.state.error_code,
                    request.state.error_message,
                )
            )
        ):
            raise ValueError("INVALID_INGESTION_REQUEST") from None
        _execute(
            self._session,
            insert(self._table).values(
                **_encode_catalog_ingestion_request(request.state)
            ),
        )

    def complete(
        self,
        request_id: IngestionRequestId,
        outcome: IngestionRequest,
        expected_status: IngestionRequestStatus,
    ) -> IngestionRequest:
        if (
            type(request_id) is not IngestionRequestId
            or type(outcome) is not IngestionRequest
            or outcome.state.id != request_id
            or expected_status is not IngestionRequestStatus.REQUESTED
            or outcome.state.status
            not in {
                IngestionRequestStatus.SUCCEEDED,
                IngestionRequestStatus.FAILED,
                IngestionRequestStatus.QUARANTINED,
            }
            or outcome.state.responded_at is None
        ):
            raise ValueError("INVALID_INGESTION_COMPLETION") from None
        if outcome.state.status is IngestionRequestStatus.SUCCEEDED:
            if outcome.state.raw_response_artifact_id is None or any(
                value is not None
                for value in (
                    outcome.state.error_class,
                    outcome.state.error_code,
                    outcome.state.error_message,
                )
            ):
                raise ValueError("INVALID_INGESTION_COMPLETION") from None
        elif outcome.state.error_class is None or outcome.state.error_code is None:
            raise ValueError("INVALID_INGESTION_COMPLETION") from None
        current = self.get(request_id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        if current.state.status is not expected_status:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if any(
            value is not None
            for value in (
                current.state.responded_at,
                current.state.http_status,
                current.state.raw_response_artifact_id,
                current.state.item_count,
                current.state.error_class,
                current.state.error_code,
                current.state.error_message,
            )
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        if (
            current.state.id,
            current.state.display_id,
            current.state.provider_endpoint_id,
            current.state.job_id,
            current.state.request_fingerprint,
            current.state.request_parameters,
            current.state.requested_at,
            current.state.created_at,
        ) != (
            outcome.state.id,
            outcome.state.display_id,
            outcome.state.provider_endpoint_id,
            outcome.state.job_id,
            outcome.state.request_fingerprint,
            outcome.state.request_parameters,
            outcome.state.requested_at,
            outcome.state.created_at,
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        encoded_outcome = _encode_catalog_ingestion_request(outcome.state)
        values = {
            column: encoded_outcome[column]
            for column in (
                "status",
                "responded_at",
                "http_status",
                "raw_response_artifact_id",
                "item_count",
                "rate_limit_observation",
                "error_class",
                "error_code",
                "error_message",
            )
        }
        row = _execute_one(
            self._session,
            update(self._table)
            .where(
                self._table.c.id == request_id.value,
                self._table.c.status == expected_status.value,
                self._table.c.responded_at.is_(None),
                self._table.c.http_status.is_(None),
                self._table.c.raw_response_artifact_id.is_(None),
                self._table.c.item_count.is_(None),
                self._table.c.error_class.is_(None),
                self._table.c.error_code.is_(None),
                self._table.c.error_message.is_(None),
            )
            .values(**values)
            .returning(self._table),
        )
        if row is None:
            observed = self.get(request_id)
            if observed is None:
                _fail(PersistenceErrorCode.NOT_FOUND)
            if observed.state.status is not expected_status or any(
                value is not None
                for value in (
                    observed.state.responded_at,
                    observed.state.http_status,
                    observed.state.raw_response_artifact_id,
                    observed.state.item_count,
                    observed.state.error_class,
                    observed.state.error_code,
                    observed.state.error_message,
                )
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        persisted = IngestionRequest(_decode_catalog_ingestion_request(row))
        if persisted.state != outcome.state:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return persisted


@guard_repository_class
class SqlAlchemyRakutenGenreRepository:
    __slots__ = ("_mapping", "_root", "_session")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_CATALOG_REPOSITORY") from None
        self._session = session
        self._root = _table("catalog.rakuten_genre")
        self._mapping = _table("catalog.category_genre_mapping")

    def get(self, genre_id: RakutenGenreId) -> RakutenGenre | None:
        if type(genre_id) is not RakutenGenreId:
            raise ValueError("INVALID_RAKUTEN_GENRE_ID") from None
        row = _execute_one(
            self._session, select(self._root).where(self._root.c.id == genre_id.value)
        )
        if row is None:
            return None
        try:
            mappings = tuple(
                _decode_catalog_category_genre_mapping(item)
                for item in self._session.execute(
                    select(self._mapping)
                    .where(self._mapping.c.rakuten_genre_id == genre_id.value)
                    .order_by(self._mapping.c.id)
                ).mappings()
            )
        except DBAPIError:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        except PersistenceError as error:
            fail_session_operation(self._session, error.code)
        except Exception:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        try:
            return RakutenGenre(
                state=_decode_catalog_rakuten_genre(row),
                category_genre_mapping_rows=mappings,
            )
        except ValueError:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def add(self, genre: RakutenGenre) -> AggregateVersion:
        if type(genre) is not RakutenGenre or genre.state.lock_version.value != 0:
            raise ValueError("INVALID_RAKUTEN_GENRE") from None
        _execute(
            self._session,
            insert(self._root).values(**_encode_catalog_rakuten_genre(genre.state)),
        )
        for mapping in genre.category_genre_mapping_rows:
            _execute(
                self._session,
                insert(self._mapping).values(
                    **_encode_catalog_category_genre_mapping(mapping)
                ),
            )
        return AggregateVersion(0)

    def save(
        self, genre: RakutenGenre, expected_version: AggregateVersion
    ) -> AggregateVersion:
        if (
            type(genre) is not RakutenGenre
            or type(expected_version) is not AggregateVersion
            or genre.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_RAKUTEN_GENRE") from None
        current = self.get(genre.state.id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current_by_id = {
            item.id.value: item for item in current.category_genre_mapping_rows
        }
        proposed_by_id = {
            item.id.value: item for item in genre.category_genre_mapping_rows
        }
        if not current_by_id.keys() <= proposed_by_id.keys() or any(
            proposed_by_id[key] != value for key, value in current_by_id.items()
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        persisted = _cas_update(
            self._session,
            self._root,
            genre.state.id.value,
            expected_version,
            _encode_catalog_rakuten_genre(genre.state),
        )
        for key, mapping in proposed_by_id.items():
            if key not in current_by_id:
                _execute(
                    self._session,
                    insert(self._mapping).values(
                        **_encode_catalog_category_genre_mapping(mapping)
                    ),
                )
        return persisted

    def get_mapping(
        self, mapping_id: CategoryGenreMappingId
    ) -> CategoryGenreMapping | None:
        if type(mapping_id) is not CategoryGenreMappingId:
            raise ValueError("INVALID_CATEGORY_GENRE_MAPPING_ID") from None
        row = _execute_one(
            self._session,
            select(self._mapping).where(self._mapping.c.id == mapping_id.value),
        )
        return None if row is None else _decode_catalog_category_genre_mapping(row)

    def append_mapping(self, mapping: CategoryGenreMapping) -> None:
        if type(mapping) is not CategoryGenreMapping:
            raise ValueError("INVALID_CATEGORY_GENRE_MAPPING") from None
        _execute(
            self._session,
            insert(self._mapping).values(
                **_encode_catalog_category_genre_mapping(mapping)
            ),
        )


@guard_repository_class
class SqlAlchemyShopRepository:
    __slots__ = ("_session", "_table")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_CATALOG_REPOSITORY") from None
        self._session = session
        self._table = _table("catalog.shop")

    def get(self, shop_id: ShopId) -> Shop | None:
        if type(shop_id) is not ShopId:
            raise ValueError("INVALID_SHOP_ID") from None
        row = _execute_one(
            self._session, select(self._table).where(self._table.c.id == shop_id.value)
        )
        return None if row is None else Shop(_decode_catalog_shop(row))

    def add(self, shop: Shop) -> AggregateVersion:
        if type(shop) is not Shop or shop.state.lock_version.value != 0:
            raise ValueError("INVALID_SHOP") from None
        _execute(
            self._session,
            insert(self._table).values(**_encode_catalog_shop(shop.state)),
        )
        return AggregateVersion(0)

    def save(self, shop: Shop, expected_version: AggregateVersion) -> AggregateVersion:
        if (
            type(shop) is not Shop
            or type(expected_version) is not AggregateVersion
            or shop.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_SHOP") from None
        return _cas_update(
            self._session,
            self._table,
            shop.state.id.value,
            expected_version,
            _encode_catalog_shop(shop.state),
        )


@guard_repository_class
class SqlAlchemyProductCandidateRepository:
    __slots__ = ("_session", "_table")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_CATALOG_REPOSITORY") from None
        self._session = session
        self._table = _table("catalog.product_candidate")

    def get(self, candidate_id: ProductCandidateId) -> ProductCandidate | None:
        if type(candidate_id) is not ProductCandidateId:
            raise ValueError("INVALID_PRODUCT_CANDIDATE_ID") from None
        row = _execute_one(
            self._session,
            select(self._table).where(self._table.c.id == candidate_id.value),
        )
        return (
            None
            if row is None
            else ProductCandidate(_decode_catalog_product_candidate(row))
        )

    def add(self, candidate: ProductCandidate) -> AggregateVersion:
        if (
            type(candidate) is not ProductCandidate
            or candidate.state.lock_version.value != 0
        ):
            raise ValueError("INVALID_PRODUCT_CANDIDATE") from None
        _execute(
            self._session,
            insert(self._table).values(
                **_encode_catalog_product_candidate(candidate.state)
            ),
        )
        return AggregateVersion(0)

    def save(
        self, candidate: ProductCandidate, expected_version: AggregateVersion
    ) -> AggregateVersion:
        if (
            type(candidate) is not ProductCandidate
            or type(expected_version) is not AggregateVersion
            or candidate.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_PRODUCT_CANDIDATE") from None
        return _cas_update(
            self._session,
            self._table,
            candidate.state.id.value,
            expected_version,
            _encode_catalog_product_candidate(candidate.state),
        )


@guard_repository_class
class SqlAlchemyGroupingDecisionRepository:
    __slots__ = ("_session", "_table")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_CATALOG_REPOSITORY") from None
        self._session = session
        self._table = _table("catalog.grouping_decision")

    def get(self, decision_id: GroupingDecisionId) -> GroupingDecision | None:
        if type(decision_id) is not GroupingDecisionId:
            raise ValueError("INVALID_GROUPING_DECISION_ID") from None
        row = _execute_one(
            self._session,
            select(self._table).where(self._table.c.id == decision_id.value),
        )
        return (
            None
            if row is None
            else GroupingDecision(_decode_catalog_grouping_decision(row))
        )

    def append(self, decision: GroupingDecision) -> None:
        if type(decision) is not GroupingDecision:
            raise ValueError("INVALID_GROUPING_DECISION") from None
        _execute(
            self._session,
            insert(self._table).values(
                **_encode_catalog_grouping_decision(decision.state)
            ),
        )


@guard_repository_class
class SqlAlchemyCanonicalProductRepository:
    __slots__ = ("_membership", "_relation", "_root", "_session")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_CATALOG_REPOSITORY") from None
        self._session = session
        self._root = _table("catalog.canonical_product")
        self._membership = _table("catalog.product_group_membership")
        self._relation = _table("catalog.product_relation")

    def get(self, product_id: CanonicalProductId) -> CanonicalProduct | None:
        if type(product_id) is not CanonicalProductId:
            raise ValueError("INVALID_CANONICAL_PRODUCT_ID") from None
        row = _execute_one(
            self._session,
            select(self._root).where(self._root.c.id == product_id.value),
        )
        if row is None:
            return None
        try:
            memberships = tuple(
                _decode_catalog_product_group_membership(item)
                for item in self._session.execute(
                    select(self._membership)
                    .where(self._membership.c.product_id == product_id.value)
                    .order_by(self._membership.c.id)
                ).mappings()
            )
            relations = tuple(
                _decode_catalog_product_relation(item)
                for item in self._session.execute(
                    select(self._relation)
                    .where(self._relation.c.from_product_id == product_id.value)
                    .order_by(self._relation.c.id)
                ).mappings()
            )
        except DBAPIError:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        except PersistenceError as error:
            fail_session_operation(self._session, error.code)
        except Exception:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        try:
            return CanonicalProduct(
                state=_decode_catalog_canonical_product(row),
                product_group_membership_rows=memberships,
                product_relation_rows=relations,
            )
        except ValueError:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def add(self, product: CanonicalProduct) -> AggregateVersion:
        if (
            type(product) is not CanonicalProduct
            or product.state.lock_version.value != 0
        ):
            raise ValueError("INVALID_CANONICAL_PRODUCT") from None
        _execute(
            self._session,
            insert(self._root).values(
                **_encode_catalog_canonical_product(product.state)
            ),
        )
        for membership in product.product_group_membership_rows:
            _execute(
                self._session,
                insert(self._membership).values(
                    **_encode_catalog_product_group_membership(membership)
                ),
            )
        for relation in product.product_relation_rows:
            _execute(
                self._session,
                insert(self._relation).values(
                    **_encode_catalog_product_relation(relation)
                ),
            )
        return AggregateVersion(0)

    def save(
        self, product: CanonicalProduct, expected_version: AggregateVersion
    ) -> AggregateVersion:
        if (
            type(product) is not CanonicalProduct
            or type(expected_version) is not AggregateVersion
            or product.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_CANONICAL_PRODUCT") from None
        current = self.get(product.state.id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current_memberships = {
            item.id.value: item for item in current.product_group_membership_rows
        }
        proposed_memberships = {
            item.id.value: item for item in product.product_group_membership_rows
        }
        current_relations = {
            item.id.value: item for item in current.product_relation_rows
        }
        proposed_relations = {
            item.id.value: item for item in product.product_relation_rows
        }
        if (
            not current_memberships.keys() <= proposed_memberships.keys()
            or not current_relations.keys() <= proposed_relations.keys()
            or any(
                proposed_memberships[key] != value
                for key, value in current_memberships.items()
            )
            or any(
                proposed_relations[key] != value
                for key, value in current_relations.items()
            )
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        persisted = _cas_update(
            self._session,
            self._root,
            product.state.id.value,
            expected_version,
            _encode_catalog_canonical_product(product.state),
        )
        for key, membership in proposed_memberships.items():
            if key not in current_memberships:
                _execute(
                    self._session,
                    insert(self._membership).values(
                        **_encode_catalog_product_group_membership(membership)
                    ),
                )
        for key, relation in proposed_relations.items():
            if key not in current_relations:
                _execute(
                    self._session,
                    insert(self._relation).values(
                        **_encode_catalog_product_relation(relation)
                    ),
                )
        return persisted

    def append_memberships(
        self,
        product_id: CanonicalProductId,
        memberships: tuple[ProductGroupMembership, ...],
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(product_id) is not CanonicalProductId
            or type(memberships) is not tuple
            or not memberships
            or any(
                type(item) is not ProductGroupMembership
                or item.product_id != product_id
                for item in memberships
            )
            or type(expected_version) is not AggregateVersion
        ):
            raise ValueError("INVALID_PRODUCT_MEMBERSHIP_BATCH") from None
        row = _execute_one(
            self._session,
            select(self._root).where(self._root.c.id == product_id.value),
        )
        if row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        state = _decode_catalog_canonical_product(row)
        if state.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        persisted = _cas_update(
            self._session,
            self._root,
            product_id.value,
            expected_version,
            _encode_catalog_canonical_product(state),
        )
        for membership in memberships:
            _execute(
                self._session,
                insert(self._membership).values(
                    **_encode_catalog_product_group_membership(membership)
                ),
            )
        return persisted

    def append_relations(
        self,
        product_id: CanonicalProductId,
        relations: tuple[ProductRelation, ...],
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(product_id) is not CanonicalProductId
            or type(relations) is not tuple
            or not relations
            or any(
                type(item) is not ProductRelation or item.from_product_id != product_id
                for item in relations
            )
            or type(expected_version) is not AggregateVersion
        ):
            raise ValueError("INVALID_PRODUCT_RELATION_BATCH") from None
        row = _execute_one(
            self._session,
            select(self._root).where(self._root.c.id == product_id.value),
        )
        if row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        state = _decode_catalog_canonical_product(row)
        if state.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        persisted = _cas_update(
            self._session,
            self._root,
            product_id.value,
            expected_version,
            _encode_catalog_canonical_product(state),
        )
        for relation in relations:
            _execute(
                self._session,
                insert(self._relation).values(
                    **_encode_catalog_product_relation(relation)
                ),
            )
        return persisted


@guard_repository_class
class SqlAlchemyAttributeDefinitionRepository:
    __slots__ = ("_product", "_root", "_session", "_value")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_CATALOG_REPOSITORY") from None
        self._session = session
        self._root = _table("catalog.attribute_definition")
        self._value = _table("catalog.product_attribute_value")
        self._product = _table("catalog.canonical_product")

    def get(self, definition_id: AttributeDefinitionId) -> AttributeDefinition | None:
        if type(definition_id) is not AttributeDefinitionId:
            raise ValueError("INVALID_ATTRIBUTE_DEFINITION_ID") from None
        row = _execute_one(
            self._session,
            select(self._root).where(self._root.c.id == definition_id.value),
        )
        if row is None:
            return None
        try:
            values = tuple(
                _decode_catalog_product_attribute_value(item)
                for item in self._session.execute(
                    select(self._value)
                    .where(self._value.c.attribute_definition_id == definition_id.value)
                    .order_by(self._value.c.id)
                ).mappings()
            )
        except DBAPIError:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        except PersistenceError as error:
            fail_session_operation(self._session, error.code)
        except Exception:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        try:
            return AttributeDefinition(
                state=_decode_catalog_attribute_definition(row),
                product_attribute_value_rows=values,
            )
        except ValueError:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def add(self, definition: AttributeDefinition) -> AggregateVersion:
        if (
            type(definition) is not AttributeDefinition
            or definition.state.lock_version.value != 0
            or definition.product_attribute_value_rows
        ):
            raise ValueError("INVALID_ATTRIBUTE_DEFINITION") from None
        _execute(
            self._session,
            insert(self._root).values(
                **_encode_catalog_attribute_definition(definition.state)
            ),
        )
        return AggregateVersion(0)

    def save(
        self, definition: AttributeDefinition, expected_version: AggregateVersion
    ) -> AggregateVersion:
        if (
            type(definition) is not AttributeDefinition
            or type(expected_version) is not AggregateVersion
            or definition.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_ATTRIBUTE_DEFINITION") from None
        current = self.get(definition.state.id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        if (
            current.product_attribute_value_rows
            != definition.product_attribute_value_rows
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        return _cas_update(
            self._session,
            self._root,
            definition.state.id.value,
            expected_version,
            _encode_catalog_attribute_definition(definition.state),
        )

    def append_values(
        self,
        definition_id: AttributeDefinitionId,
        values: tuple[ProductAttributeValue, ...],
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(definition_id) is not AttributeDefinitionId
            or type(values) is not tuple
            or not values
            or any(
                type(item) is not ProductAttributeValue
                or item.attribute_definition_id != definition_id
                for item in values
            )
            or len({item.product_id for item in values}) != 1
            or type(expected_version) is not AggregateVersion
        ):
            raise ValueError("INVALID_ATTRIBUTE_VALUE_BATCH") from None
        row = _execute_one(
            self._session,
            select(self._root).where(self._root.c.id == definition_id.value),
        )
        if row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        product_id = values[0].product_id
        product_row = _execute_one(
            self._session,
            select(self._product).where(self._product.c.id == product_id.value),
        )
        if product_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        product_state = _decode_catalog_canonical_product(product_row)
        if product_state.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        persisted = _cas_update(
            self._session,
            self._product,
            product_id.value,
            expected_version,
            _encode_catalog_canonical_product(product_state),
        )
        for value in values:
            _execute(
                self._session,
                insert(self._value).values(
                    **_encode_catalog_product_attribute_value(value)
                ),
            )
        return persisted


OfferObservation = (
    PriceObservation
    | AvailabilityObservation
    | ReviewAggregateObservation
    | AffiliateLinkObservation
)


def _offer_observation_event_type(
    batch: tuple[OfferObservation, ...],
) -> str:
    """Select the one closed event type using the Canonical precedence."""

    if any(
        type(item) is AffiliateLinkObservation
        and item.validation_status is not AffiliateLinkObservationValidationStatus.VALID
        for item in batch
    ):
        return "jp.raos.catalog.affiliate_link_invalid.v1"
    if any(
        type(item) is AvailabilityObservation
        and item.validation_status is AvailabilityObservationValidationStatus.VALID
        and item.availability
        in {
            AvailabilityObservationAvailability.OUT_OF_STOCK,
            AvailabilityObservationAvailability.DISCONTINUED,
        }
        for item in batch
    ):
        return "jp.raos.catalog.offer_unavailable.v1"
    return "jp.raos.catalog.offer_observed.v1"


@guard_repository_class
class SqlAlchemyOfferRepository:
    __slots__ = (
        "_affiliate",
        "_availability",
        "_price",
        "_projection",
        "_review",
        "_root",
        "_session",
    )

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_CATALOG_REPOSITORY") from None
        self._session = session
        self._root = _table("catalog.offer")
        self._price = _table("catalog.price_observation")
        self._availability = _table("catalog.availability_observation")
        self._review = _table("catalog.review_aggregate_observation")
        self._affiliate = _table("catalog.affiliate_link_observation")
        self._projection = _table("catalog.offer_current_projection")

    def _load(self, offer_id: OfferId) -> Offer | None:
        if type(offer_id) is not OfferId:
            raise ValueError("INVALID_OFFER_ID") from None
        row = _execute_one(
            self._session, select(self._root).where(self._root.c.id == offer_id.value)
        )
        if row is None:
            return None
        try:
            prices = tuple(
                _decode_catalog_price_observation(item)
                for item in self._session.execute(
                    select(self._price)
                    .where(self._price.c.offer_id == offer_id.value)
                    .order_by(self._price.c.id)
                ).mappings()
            )
            availability = tuple(
                _decode_catalog_availability_observation(item)
                for item in self._session.execute(
                    select(self._availability)
                    .where(self._availability.c.offer_id == offer_id.value)
                    .order_by(self._availability.c.id)
                ).mappings()
            )
            reviews = tuple(
                _decode_catalog_review_aggregate_observation(item)
                for item in self._session.execute(
                    select(self._review)
                    .where(self._review.c.offer_id == offer_id.value)
                    .order_by(self._review.c.id)
                ).mappings()
            )
            links = tuple(
                _decode_catalog_affiliate_link_observation(item)
                for item in self._session.execute(
                    select(self._affiliate)
                    .where(self._affiliate.c.offer_id == offer_id.value)
                    .order_by(self._affiliate.c.id)
                ).mappings()
            )
        except DBAPIError:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        except PersistenceError as error:
            fail_session_operation(self._session, error.code)
        except Exception:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        projection_row = _execute_one(
            self._session,
            select(self._projection).where(
                self._projection.c.offer_id == offer_id.value
            ),
        )
        try:
            return Offer(
                state=_decode_catalog_offer(row),
                price_observation_rows=prices,
                availability_observation_rows=availability,
                review_aggregate_observation_rows=reviews,
                affiliate_link_observation_rows=links,
                offer_current_projection=(
                    None
                    if projection_row is None
                    else _decode_catalog_offer_current_projection(projection_row)
                ),
            )
        except ValueError:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def get(self, offer_id: OfferId) -> Offer | None:
        offer = self._load(offer_id)
        if offer is not None:
            register_pending_events(
                self._session,
                aggregate_type="catalog.offer",
                aggregate_id=offer.state.id.value,
                buffer=aggregate_event_buffer(offer),
            )
        return offer

    def add(self, offer: Offer) -> AggregateVersion:
        if type(offer) is not Offer or offer.state.lock_version.value != 0:
            raise ValueError("INVALID_OFFER") from None
        register_pending_events(
            self._session,
            aggregate_type="catalog.offer",
            aggregate_id=offer.state.id.value,
            buffer=aggregate_event_buffer(offer),
        )
        _execute(
            self._session,
            insert(self._root).values(**_encode_catalog_offer(offer.state)),
        )
        for price_row in offer.price_observation_rows:
            _execute(
                self._session,
                insert(self._price).values(
                    **_encode_catalog_price_observation(price_row)
                ),
            )
        for availability_row in offer.availability_observation_rows:
            _execute(
                self._session,
                insert(self._availability).values(
                    **_encode_catalog_availability_observation(availability_row)
                ),
            )
        for review_row in offer.review_aggregate_observation_rows:
            _execute(
                self._session,
                insert(self._review).values(
                    **_encode_catalog_review_aggregate_observation(review_row)
                ),
            )
        for affiliate_row in offer.affiliate_link_observation_rows:
            _execute(
                self._session,
                insert(self._affiliate).values(
                    **_encode_catalog_affiliate_link_observation(affiliate_row)
                ),
            )
        if offer.offer_current_projection is not None:
            _execute(
                self._session,
                insert(self._projection).values(
                    **_encode_catalog_offer_current_projection(
                        offer.offer_current_projection
                    )
                ),
            )
        return AggregateVersion(0)

    def save(
        self, offer: Offer, expected_version: AggregateVersion
    ) -> AggregateVersion:
        if (
            type(offer) is not Offer
            or type(expected_version) is not AggregateVersion
            or offer.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_OFFER") from None
        current = self._load(offer.state.id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        register_pending_events(
            self._session,
            aggregate_type="catalog.offer",
            aggregate_id=offer.state.id.value,
            buffer=aggregate_event_buffer(offer),
        )
        if (
            current.price_observation_rows != offer.price_observation_rows
            or current.availability_observation_rows
            != offer.availability_observation_rows
            or current.review_aggregate_observation_rows
            != offer.review_aggregate_observation_rows
            or current.affiliate_link_observation_rows
            != offer.affiliate_link_observation_rows
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        current_projection = current.offer_current_projection
        proposed_projection = offer.offer_current_projection
        if current_projection is not None and proposed_projection is None:
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        if (
            proposed_projection is not None
            and proposed_projection.projection_version < 1
        ):
            raise ValueError("INVALID_OFFER_PROJECTION") from None
        if (
            current_projection is not None
            and proposed_projection is not None
            and proposed_projection != current_projection
            and proposed_projection.projection_version
            <= current_projection.projection_version
        ):
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        persisted = _cas_update(
            self._session,
            self._root,
            offer.state.id.value,
            expected_version,
            _encode_catalog_offer(offer.state),
        )
        if current_projection == proposed_projection:
            return persisted
        if proposed_projection is None:
            return persisted
        projection_values = _encode_catalog_offer_current_projection(
            proposed_projection
        )
        projection_values.pop("offer_id")
        if current_projection is None:
            _execute(
                self._session,
                insert(self._projection).values(
                    **_encode_catalog_offer_current_projection(proposed_projection)
                ),
            )
        else:
            projection_row = _execute_one(
                self._session,
                update(self._projection)
                .where(self._projection.c.offer_id == offer.state.id.value)
                .values(**projection_values)
                .returning(self._projection.c.offer_id),
            )
            if projection_row is None:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return persisted

    def append_observations(
        self,
        offer_id: OfferId,
        batch: tuple[OfferObservation, ...],
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        allowed = (
            PriceObservation,
            AvailabilityObservation,
            ReviewAggregateObservation,
            AffiliateLinkObservation,
        )
        if (
            type(offer_id) is not OfferId
            or type(batch) is not tuple
            or not batch
            or any(
                type(item) not in allowed or item.offer_id != offer_id for item in batch
            )
            or type(expected_version) is not AggregateVersion
        ):
            raise ValueError("INVALID_OFFER_OBSERVATION_BATCH") from None
        expected_event_type = _offer_observation_event_type(batch)
        root_row = _execute_one(
            self._session, select(self._root).where(self._root.c.id == offer_id.value)
        )
        if root_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        state = _decode_catalog_offer(root_row)
        if state.lock_version != expected_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        persisted = _cas_update(
            self._session,
            self._root,
            offer_id.value,
            expected_version,
            _encode_catalog_offer(state),
        )
        for observation in batch:
            if type(observation) is PriceObservation:
                statement = insert(self._price).values(
                    **_encode_catalog_price_observation(observation)
                )
            elif type(observation) is AvailabilityObservation:
                statement = insert(self._availability).values(
                    **_encode_catalog_availability_observation(observation)
                )
            elif type(observation) is ReviewAggregateObservation:
                statement = insert(self._review).values(
                    **_encode_catalog_review_aggregate_observation(observation)
                )
            elif type(observation) is AffiliateLinkObservation:
                statement = insert(self._affiliate).values(
                    **_encode_catalog_affiliate_link_observation(observation)
                )
            else:
                raise ValueError("INVALID_OFFER_OBSERVATION") from None
            _execute(self._session, statement)
        stage_registered_events(
            self._session,
            aggregate_type="catalog.offer",
            aggregate_id=offer_id.value,
            owning_method="OfferRepository.append_observations",
            persisted_version=persisted,
            expected_event_type=expected_event_type,
        )
        return persisted

    def get_current_projection(
        self, offer_id: OfferId
    ) -> OfferCurrentProjection | None:
        if type(offer_id) is not OfferId:
            raise ValueError("INVALID_OFFER_ID") from None
        row = _execute_one(
            self._session,
            select(self._projection).where(
                self._projection.c.offer_id == offer_id.value
            ),
        )
        return None if row is None else _decode_catalog_offer_current_projection(row)


@guard_repository_class
class SqlAlchemySafeOfferCurrentReader:
    __slots__ = ("_session", "_view")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_CATALOG_REPOSITORY") from None
        self._session = session
        self._view = _view("catalog.v_safe_offer_current")

    def get_by_offer(self, offer_id: OfferId) -> SafeOfferCurrent | None:
        if type(offer_id) is not OfferId:
            raise ValueError("INVALID_OFFER_ID") from None
        row = _execute_one(
            self._session,
            select(self._view).where(self._view.c.offer_id == offer_id.value),
        )
        return None if row is None else _decode_catalog_v_safe_offer_current(row)

    def list_by_product(
        self, product_id: CanonicalProductId
    ) -> tuple[SafeOfferCurrent, ...]:
        if type(product_id) is not CanonicalProductId:
            raise ValueError("INVALID_CANONICAL_PRODUCT_ID") from None
        try:
            rows = self._session.execute(
                select(self._view)
                .where(self._view.c.product_id == product_id.value)
                .order_by(self._view.c.offer_id)
            ).mappings()
            return tuple(_decode_catalog_v_safe_offer_current(row) for row in rows)
        except DBAPIError:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        except PersistenceError as error:
            fail_session_operation(self._session, error.code)
        except Exception:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )


__all__ = [
    "SqlAlchemyAttributeDefinitionRepository",
    "SqlAlchemyCanonicalProductRepository",
    "SqlAlchemyGroupingDecisionRepository",
    "SqlAlchemyIngestionRequestRepository",
    "SqlAlchemyOfferRepository",
    "SqlAlchemyProductCandidateRepository",
    "SqlAlchemyProviderEndpointRepository",
    "SqlAlchemyRakutenGenreRepository",
    "SqlAlchemySafeOfferCurrentReader",
    "SqlAlchemyShopRepository",
]
