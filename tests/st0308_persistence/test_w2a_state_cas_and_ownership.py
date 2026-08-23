"""Exact W2A state-CAS, child-root ownership, and event-wiring tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
import inspect
from typing import Any

import pytest
from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.repositories import catalog as catalog_sql
from raos.adapters.persistence.sqlalchemy.repositories import iam as iam_sql
from raos.adapters.persistence.sqlalchemy.repositories import ops as ops_sql
from raos.adapters.persistence.sqlalchemy.repositories import portfolio as portfolio_sql
from raos.domain.catalog.aggregates import (
    AffiliateLinkObservation,
    AttributeDefinition,
    AttributeDefinitionState,
    AvailabilityObservation,
    CanonicalProductState,
    IngestionRequest,
    IngestionRequestState,
    OfferState,
    PriceObservation,
    ProductAttributeValue,
    ProviderEndpoint,
    ProviderEndpointState,
)
from raos.domain.catalog.enums import (
    AffiliateLinkObservationValidationStatus,
    AttributeDefinitionDataType,
    AttributeDefinitionStatus,
    AvailabilityObservationAvailability,
    AvailabilityObservationValidationStatus,
    CanonicalProductLifecycleStatus,
    IngestionRequestStatus,
    OfferStatus,
    PriceObservationShippingCondition,
    PriceObservationValidationStatus,
    ProviderEndpointStatus,
)
from raos.domain.catalog.ids import (
    AffiliateLinkObservationId,
    AttributeDefinitionId,
    AvailabilityObservationId,
    CanonicalProductId,
    IngestionRequestId,
    OfferId,
    PriceObservationId,
    ProductAttributeValueId,
    ProviderEndpointId,
    ProductCandidateId,
    ShopId,
)
from raos.domain.catalog.values import (
    CanonicalProductIdentityAttributesJson,
    IngestionRequestRateLimitObservationJson,
    IngestionRequestRequestParametersJson,
    ProviderEndpointNonSecretConfigJson,
)
from raos.domain.iam.aggregates import (
    PrincipalRoleAssignment,
    PrincipalRoleAssignmentRecord,
)
from raos.domain.iam.enums import PrincipalRoleAssignmentScopeType
from raos.domain.iam.ids import (
    PrincipalId,
    PrincipalRoleAssignmentId,
    RoleId,
)
from raos.domain.evidence.ids import SourceSnapshotId
from raos.domain.ops.aggregates import Job, JobState
from raos.domain.ops.enums import JobStatus
from raos.domain.ops.events import OpsJobRequested
from raos.domain.ops.ids import JobId, ObjectArtifactId
from raos.domain.ops.values import JobPayloadJson
from raos.domain.portfolio.aggregates import ActionCandidate, ActionCandidateState
from raos.domain.portfolio.enums import (
    ActionCandidateActionType,
    ActionCandidateStatus,
    ActionCandidateTargetEntityType,
)
from raos.domain.portfolio.events import PortfolioActionCandidateDecided
from raos.domain.portfolio.ids import ActionCandidateId, CategoryId, SiteId
from raos.domain.portfolio.values import ActionCandidateRationaleJson
from raos.domain.shared.identity import ActorId, CorrelationId
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    Sha256Digest,
    UriReference,
    YenMinor,
)
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from tests.st0308_persistence.support import (
    FIXED_TIME,
    make_context,
    make_runtime_setting,
    stable_uuid,
)


LATER = FIXED_TIME + timedelta(hours=1)


class _Result:
    def __init__(
        self,
        *,
        row: dict[str, object] | None = None,
        scalar: object = None,
    ) -> None:
        self._row = row
        self._scalar = scalar

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> dict[str, object] | None:
        return self._row

    def scalar_one_or_none(self) -> object:
        return self._scalar


class _ScriptedSession(Session):
    def __init__(self, *results: _Result) -> None:
        super().__init__()
        self._results = list(results)
        self.statements: list[object] = []

    def execute(self, statement: object, *args: object, **kwargs: object) -> Any:
        del args, kwargs
        self.statements.append(statement)
        if not self._results:
            raise AssertionError("unexpected SQL execution")
        return self._results.pop(0)


def _write_columns(statement: object) -> frozenset[str]:
    values = getattr(statement, "_values")
    return frozenset(key if type(key) is str else key.name for key in values)


def _provider(
    status: ProviderEndpointStatus,
    *,
    effective_to: datetime | None = None,
) -> ProviderEndpoint:
    return ProviderEndpoint(
        ProviderEndpointState(
            id=ProviderEndpointId(stable_uuid("provider:endpoint")),
            provider_code="RAKUTEN",
            provider_name="Rakuten",
            api_name="IchibaItemSearch",
            api_version="2022-06-01",
            base_host="app.rakuten.co.jp",
            status=status,
            contract_sha256=Sha256Digest("1" * 64),
            documentation_url=None,
            non_secret_config=ProviderEndpointNonSecretConfigJson(
                FrozenJsonObject.from_mapping({"live_enabled": False})
            ),
            effective_from=AwareUtcDateTime(FIXED_TIME),
            effective_to=(
                None if effective_to is None else AwareUtcDateTime(effective_to)
            ),
            created_at=AwareUtcDateTime(FIXED_TIME),
        )
    )


def _provider_row(value: ProviderEndpoint) -> dict[str, object]:
    return catalog_sql._encode_catalog_provider_endpoint(value.state)


@pytest.mark.parametrize(
    ("source", "target", "expected_columns"),
    (
        (
            ProviderEndpointStatus.DRAFT,
            ProviderEndpointStatus.BLOCKED,
            frozenset({"status"}),
        ),
        (
            ProviderEndpointStatus.DRAFT,
            ProviderEndpointStatus.ACTIVE,
            frozenset({"status", "effective_from", "effective_to"}),
        ),
        (
            ProviderEndpointStatus.ACTIVE,
            ProviderEndpointStatus.DEPRECATED,
            frozenset({"status", "effective_to"}),
        ),
    ),
)
def test_provider_transition_uses_only_edge_specific_set_columns(
    monkeypatch: pytest.MonkeyPatch,
    source: ProviderEndpointStatus,
    target: ProviderEndpointStatus,
    expected_columns: frozenset[str],
) -> None:
    current = _provider(source)
    transition = ProviderEndpoint(
        replace(
            current.state,
            status=target,
            effective_to=(
                AwareUtcDateTime(LATER)
                if source is ProviderEndpointStatus.ACTIVE
                and target
                in {
                    ProviderEndpointStatus.DEPRECATED,
                    ProviderEndpointStatus.RETIRED,
                }
                else None
            ),
        )
    )
    monkeypatch.setattr(
        catalog_sql,
        "transaction_timestamp",
        lambda _session: AwareUtcDateTime(LATER),
    )
    session = _ScriptedSession(
        _Result(row=_provider_row(current)),
        _Result(row=_provider_row(transition)),
    )
    persisted = catalog_sql.SqlAlchemyProviderEndpointRepository(session).transition(
        current.state.id, transition, source
    )
    assert persisted == transition
    assert _write_columns(session.statements[1]) == expected_columns
    compiled = str(session.statements[1].compile())
    if source is ProviderEndpointStatus.ACTIVE and target in {
        ProviderEndpointStatus.DEPRECATED,
        ProviderEndpointStatus.RETIRED,
    }:
        assert "effective_to IS NULL" in compiled


@pytest.mark.parametrize(
    ("observed", "expected"),
    (
        (None, PersistenceErrorCode.NOT_FOUND),
        (ProviderEndpointStatus.ACTIVE, PersistenceErrorCode.STATE_CONFLICT),
        (ProviderEndpointStatus.DRAFT, PersistenceErrorCode.STORAGE_CORRUPTION),
    ),
)
def test_provider_zero_row_is_classified_without_retry(
    observed: ProviderEndpointStatus | None,
    expected: PersistenceErrorCode,
) -> None:
    current = _provider(ProviderEndpointStatus.DRAFT)
    transition = ProviderEndpoint(
        replace(current.state, status=ProviderEndpointStatus.BLOCKED)
    )
    observed_row = None if observed is None else _provider_row(_provider(observed))
    session = _ScriptedSession(
        _Result(row=_provider_row(current)),
        _Result(row=None),
        _Result(row=observed_row),
    )
    with pytest.raises(PersistenceError) as captured:
        catalog_sql.SqlAlchemyProviderEndpointRepository(session).transition(
            current.state.id,
            transition,
            ProviderEndpointStatus.DRAFT,
        )
    assert captured.value.code is expected
    assert len(session.statements) == 3


def _ingestion(status: IngestionRequestStatus) -> IngestionRequest:
    terminal = status is not IngestionRequestStatus.REQUESTED
    success = status is IngestionRequestStatus.SUCCEEDED
    return IngestionRequest(
        IngestionRequestState(
            id=IngestionRequestId(stable_uuid("ingestion:request")),
            display_id="ING-001",
            provider_endpoint_id=ProviderEndpointId(stable_uuid("provider:endpoint")),
            job_id=JobId(stable_uuid("job:ingestion")),
            request_fingerprint="2" * 64,
            request_parameters=IngestionRequestRequestParametersJson(
                FrozenJsonObject.from_mapping({"keyword": "battery"})
            ),
            requested_at=AwareUtcDateTime(FIXED_TIME),
            responded_at=AwareUtcDateTime(LATER) if terminal else None,
            http_status=(200 if success else 503) if terminal else None,
            status=status,
            raw_response_artifact_id=(
                ObjectArtifactId(stable_uuid("artifact:response")) if success else None
            ),
            item_count=3 if success else None,
            rate_limit_observation=IngestionRequestRateLimitObservationJson(
                FrozenJsonObject.from_mapping({"remaining": 9} if terminal else {})
            ),
            error_class=None if not terminal or success else "PROVIDER",
            error_code=None if not terminal or success else "UNAVAILABLE",
            error_message=None if not terminal or success else "provider unavailable",
            created_at=AwareUtcDateTime(FIXED_TIME),
        )
    )


@pytest.mark.parametrize(
    "status",
    (
        IngestionRequestStatus.SUCCEEDED,
        IngestionRequestStatus.FAILED,
        IngestionRequestStatus.QUARANTINED,
    ),
)
def test_ingestion_completion_uses_exact_outcome_columns(
    status: IngestionRequestStatus,
) -> None:
    current = _ingestion(IngestionRequestStatus.REQUESTED)
    outcome = _ingestion(status)
    session = _ScriptedSession(
        _Result(row=catalog_sql._encode_catalog_ingestion_request(current.state)),
        _Result(row=catalog_sql._encode_catalog_ingestion_request(outcome.state)),
    )
    assert (
        catalog_sql.SqlAlchemyIngestionRequestRepository(session).complete(
            current.state.id,
            outcome,
            IngestionRequestStatus.REQUESTED,
        )
        == outcome
    )
    assert _write_columns(session.statements[1]) == frozenset(
        {
            "status",
            "responded_at",
            "http_status",
            "raw_response_artifact_id",
            "item_count",
            "rate_limit_observation",
            "error_class",
            "error_code",
            "error_message",
        }
    )


def _assignment(*, revoked: bool, actor: PrincipalId) -> PrincipalRoleAssignment:
    return PrincipalRoleAssignment(
        PrincipalRoleAssignmentRecord(
            id=PrincipalRoleAssignmentId(stable_uuid("assignment:one")),
            principal_id=PrincipalId(stable_uuid("principal:subject")),
            role_id=RoleId(stable_uuid("role:editor")),
            scope_type=PrincipalRoleAssignmentScopeType.GLOBAL,
            scope_id=None,
            valid_from=AwareUtcDateTime(FIXED_TIME),
            valid_to=None,
            assigned_by_principal_id=PrincipalId(stable_uuid("principal:assigner")),
            assignment_reason="editorial role",
            revoked_at=AwareUtcDateTime(LATER) if revoked else None,
            revoked_by_principal_id=actor if revoked else None,
            revocation_reason="access removed" if revoked else None,
            created_at=AwareUtcDateTime(FIXED_TIME),
        )
    )


def test_iam_revocation_binds_context_actor_and_exact_three_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context(suffix="iam-revoke")
    assert context.actor.actor_id is not None
    actor = PrincipalId(context.actor.actor_id)
    current = _assignment(revoked=False, actor=actor)
    target = _assignment(revoked=True, actor=actor)
    monkeypatch.setattr(iam_sql, "persistence_context", lambda _session: context)
    session = _ScriptedSession(
        _Result(row=iam_sql._encode_iam_principal_role_assignment(current.state)),
        _Result(row=iam_sql._encode_iam_principal_role_assignment(target.state)),
    )
    assert (
        iam_sql.SqlAlchemyPrincipalRoleAssignmentRepository(session).revoke(
            current.state.id,
            target,
            "ACTIVE",
        )
        == target
    )
    assert _write_columns(session.statements[1]) == frozenset(
        {"revoked_at", "revoked_by_principal_id", "revocation_reason"}
    )
    assert session.statements[1].compile().params["revoked_by_principal_id"] == (
        context.actor.actor_id
    )


def test_iam_revocation_rejects_claimed_actor_mismatch_before_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context(suffix="iam-actor-mismatch")
    target = _assignment(
        revoked=True,
        actor=PrincipalId(stable_uuid("principal:not-context")),
    )
    monkeypatch.setattr(iam_sql, "persistence_context", lambda _session: context)
    session = _ScriptedSession()
    with pytest.raises(PersistenceError) as captured:
        iam_sql.SqlAlchemyPrincipalRoleAssignmentRepository(session).revoke(
            target.state.id,
            target,
            "ACTIVE",
        )
    assert captured.value.code is PersistenceErrorCode.STATE_CONFLICT
    assert session.statements == []


def test_runtime_activation_binds_context_actor_and_exact_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context(suffix="runtime-activate")
    assert context.actor.actor_id is not None
    current = make_runtime_setting(suffix="state-cas")
    target = make_runtime_setting(
        suffix="state-cas",
        status=ops_sql.RuntimeSettingVersionStatus.ACTIVE,
        approved_by=PrincipalId(context.actor.actor_id),
        approval_reason="approved for local use",
        effective_from=AwareUtcDateTime(LATER),
    )
    monkeypatch.setattr(ops_sql, "persistence_context", lambda _session: context)
    session = _ScriptedSession(
        _Result(row=ops_sql._encode_ops_runtime_setting_version(current.state)),
        _Result(row=ops_sql._encode_ops_runtime_setting_version(target.state)),
    )
    assert (
        ops_sql.SqlAlchemyRuntimeSettingRepository(session).transition(
            current.state.id,
            target,
            ops_sql.RuntimeSettingVersionStatus.DRAFT,
        )
        == target
    )
    assert _write_columns(session.statements[1]) == frozenset(
        {
            "status",
            "approved_by_principal_id",
            "approval_reason",
            "effective_from",
            "effective_to",
        }
    )


def _definition() -> AttributeDefinition:
    return AttributeDefinition(
        AttributeDefinitionState(
            id=AttributeDefinitionId(stable_uuid("attribute:capacity")),
            category_id=CategoryId(stable_uuid("category:power")),
            attribute_code="capacity_wh",
            name="Capacity",
            data_type=AttributeDefinitionDataType.NUMERIC,
            unit_family="energy",
            is_comparable=True,
            is_required=True,
            normalization_rule_version="1.0.0",
            status=AttributeDefinitionStatus.ACTIVE,
            created_at=AwareUtcDateTime(FIXED_TIME),
            updated_at=AwareUtcDateTime(FIXED_TIME),
            lock_version=AggregateVersion(0),
        )
    )


def _product(
    *, product_id: CanonicalProductId, version: int = 0
) -> CanonicalProductState:
    return CanonicalProductState(
        id=product_id,
        display_id="PROD-001",
        category_id=CategoryId(stable_uuid("category:power")),
        canonical_name="Portable power station",
        brand_name="Example",
        manufacturer_name=None,
        model_number="P100",
        jan_code=None,
        product_type="POWER_STATION",
        lifecycle_status=CanonicalProductLifecycleStatus.ACTIVE,
        identity_confidence=Decimal("1.0"),
        identity_attributes=CanonicalProductIdentityAttributesJson(
            FrozenJsonObject.from_mapping({"model": "P100"})
        ),
        merged_into_product_id=None,
        created_at=AwareUtcDateTime(FIXED_TIME),
        updated_at=AwareUtcDateTime(FIXED_TIME),
        lock_version=AggregateVersion(version),
    )


def _attribute_value(
    *,
    product_id: CanonicalProductId,
    definition_id: AttributeDefinitionId,
    suffix: str,
) -> ProductAttributeValue:
    return ProductAttributeValue(
        id=ProductAttributeValueId(stable_uuid(f"attribute-value:{suffix}")),
        product_id=product_id,
        attribute_definition_id=definition_id,
        value_text=None,
        value_numeric=Decimal("288"),
        value_boolean=None,
        value_date=None,
        value_code=None,
        unit_code="Wh",
        source_fact_id=None,
        confidence=Decimal("1.0"),
        valid_from=AwareUtcDateTime(FIXED_TIME),
        valid_to=None,
        created_at=AwareUtcDateTime(FIXED_TIME),
    )


def test_attribute_values_cas_one_canonical_product_before_child_insert() -> None:
    definition = _definition()
    product_id = CanonicalProductId(stable_uuid("product:one"))
    product = _product(product_id=product_id)
    value = _attribute_value(
        product_id=product_id,
        definition_id=definition.state.id,
        suffix="one",
    )
    session = _ScriptedSession(
        _Result(row=catalog_sql._encode_catalog_attribute_definition(definition.state)),
        _Result(row=catalog_sql._encode_catalog_canonical_product(product)),
        _Result(scalar=1),
        _Result(),
    )
    persisted = catalog_sql.SqlAlchemyAttributeDefinitionRepository(
        session
    ).append_values(definition.state.id, (value,), AggregateVersion(0))
    assert persisted == AggregateVersion(1)
    assert session.statements[2].table.fullname == "catalog.canonical_product"
    assert session.statements[3].table.fullname == "catalog.product_attribute_value"


@pytest.mark.parametrize(
    ("product_row", "expected"),
    (
        (None, PersistenceErrorCode.NOT_FOUND),
        ("stale", PersistenceErrorCode.CONCURRENCY_CONFLICT),
    ),
)
def test_attribute_value_append_classifies_product_missing_and_stale(
    product_row: str | None,
    expected: PersistenceErrorCode,
) -> None:
    definition = _definition()
    product_id = CanonicalProductId(stable_uuid("product:one"))
    value = _attribute_value(
        product_id=product_id,
        definition_id=definition.state.id,
        suffix="one",
    )
    encoded_product = (
        None
        if product_row is None
        else catalog_sql._encode_catalog_canonical_product(
            _product(product_id=product_id, version=2)
        )
    )
    session = _ScriptedSession(
        _Result(row=catalog_sql._encode_catalog_attribute_definition(definition.state)),
        _Result(row=encoded_product),
    )
    with pytest.raises(PersistenceError) as captured:
        catalog_sql.SqlAlchemyAttributeDefinitionRepository(session).append_values(
            definition.state.id,
            (value,),
            AggregateVersion(0),
        )
    assert captured.value.code is expected
    assert len(session.statements) == 2


@pytest.mark.parametrize("mixed", ("product", "definition"))
def test_attribute_value_append_rejects_mixed_batch_before_io(mixed: str) -> None:
    definition = _definition()
    product_id = CanonicalProductId(stable_uuid("product:one"))
    first = _attribute_value(
        product_id=product_id,
        definition_id=definition.state.id,
        suffix="one",
    )
    second = _attribute_value(
        product_id=(
            CanonicalProductId(stable_uuid("product:two"))
            if mixed == "product"
            else product_id
        ),
        definition_id=(
            AttributeDefinitionId(stable_uuid("attribute:other"))
            if mixed == "definition"
            else definition.state.id
        ),
        suffix="two",
    )
    session = _ScriptedSession()
    with pytest.raises(ValueError, match="INVALID_ATTRIBUTE_VALUE_BATCH"):
        catalog_sql.SqlAlchemyAttributeDefinitionRepository(session).append_values(
            definition.state.id,
            (first, second),
            AggregateVersion(0),
        )
    assert session.statements == []


def _offer_state(offer_id: OfferId) -> OfferState:
    return OfferState(
        id=offer_id,
        display_id="OFFER-001",
        provider_endpoint_id=ProviderEndpointId(stable_uuid("provider:endpoint")),
        external_offer_id="external-offer-001",
        product_candidate_id=ProductCandidateId(stable_uuid("candidate:one")),
        product_id=None,
        shop_id=ShopId(stable_uuid("shop:one")),
        item_url=UriReference("https://example.test/item/one"),
        status=OfferStatus.ACTIVE,
        first_observed_at=AwareUtcDateTime(FIXED_TIME),
        last_observed_at=AwareUtcDateTime(FIXED_TIME),
        created_at=AwareUtcDateTime(FIXED_TIME),
        updated_at=AwareUtcDateTime(FIXED_TIME),
        lock_version=AggregateVersion(0),
    )


def _price(offer_id: OfferId) -> PriceObservation:
    return PriceObservation(
        id=PriceObservationId(stable_uuid("price:one")),
        offer_id=offer_id,
        price_jpy=YenMinor(1000),
        tax_included=True,
        shipping_fee_jpy=None,
        shipping_condition=PriceObservationShippingCondition.FREE,
        points_rate=None,
        observed_at=AwareUtcDateTime(FIXED_TIME),
        ingested_at=AwareUtcDateTime(FIXED_TIME),
        valid_until=AwareUtcDateTime(LATER),
        source_snapshot_id=SourceSnapshotId(stable_uuid("snapshot:price")),
        validation_status=PriceObservationValidationStatus.VALID,
        confidence=Decimal("1.0"),
        created_at=AwareUtcDateTime(FIXED_TIME),
    )


def _unavailable(offer_id: OfferId) -> AvailabilityObservation:
    return AvailabilityObservation(
        id=AvailabilityObservationId(stable_uuid("availability:one")),
        offer_id=offer_id,
        availability=AvailabilityObservationAvailability.OUT_OF_STOCK,
        quantity=0,
        lead_time_text=None,
        observed_at=AwareUtcDateTime(FIXED_TIME),
        ingested_at=AwareUtcDateTime(FIXED_TIME),
        valid_until=AwareUtcDateTime(LATER),
        source_snapshot_id=SourceSnapshotId(stable_uuid("snapshot:availability")),
        validation_status=AvailabilityObservationValidationStatus.VALID,
        confidence=Decimal("1.0"),
        created_at=AwareUtcDateTime(FIXED_TIME),
    )


def _invalid_affiliate(offer_id: OfferId) -> AffiliateLinkObservation:
    return AffiliateLinkObservation(
        id=AffiliateLinkObservationId(stable_uuid("affiliate:one")),
        offer_id=offer_id,
        affiliate_url=UriReference("https://example.test/affiliate/one"),
        url_sha256=Sha256Digest("3" * 64),
        destination_host="example.test",
        is_api_returned=True,
        affiliate_rate=None,
        observed_at=AwareUtcDateTime(FIXED_TIME),
        valid_until=AwareUtcDateTime(LATER),
        source_snapshot_id=SourceSnapshotId(stable_uuid("snapshot:affiliate")),
        validation_status=AffiliateLinkObservationValidationStatus.UNVERIFIED,
        link_contract_version="1.0.0",
        created_at=AwareUtcDateTime(FIXED_TIME),
    )


@pytest.mark.parametrize(
    ("batch_kind", "expected_event_type"),
    (
        ("observed", "jp.raos.catalog.offer_observed.v1"),
        ("unavailable", "jp.raos.catalog.offer_unavailable.v1"),
        ("affiliate", "jp.raos.catalog.affiliate_link_invalid.v1"),
        ("precedence", "jp.raos.catalog.affiliate_link_invalid.v1"),
    ),
)
def test_offer_append_passes_canonical_event_precedence_to_shared_stager(
    monkeypatch: pytest.MonkeyPatch,
    batch_kind: str,
    expected_event_type: str,
) -> None:
    offer_id = OfferId(stable_uuid("offer:one"))
    batch = {
        "observed": (_price(offer_id),),
        "unavailable": (_unavailable(offer_id),),
        "affiliate": (_invalid_affiliate(offer_id),),
        "precedence": (_unavailable(offer_id), _invalid_affiliate(offer_id)),
    }[batch_kind]
    staged: list[str] = []

    def capture_stage(
        _session: Session,
        *,
        aggregate_type: str,
        aggregate_id: object,
        owning_method: str,
        persisted_version: AggregateVersion,
        expected_event_type: str,
    ) -> None:
        assert aggregate_type == "catalog.offer"
        assert aggregate_id == offer_id.value
        assert owning_method == "OfferRepository.append_observations"
        assert persisted_version == AggregateVersion(1)
        staged.append(expected_event_type)

    monkeypatch.setattr(catalog_sql, "stage_registered_events", capture_stage)
    session = _ScriptedSession(
        _Result(row=catalog_sql._encode_catalog_offer(_offer_state(offer_id))),
        _Result(scalar=1),
        *(_Result() for _item in batch),
    )
    persisted = catalog_sql.SqlAlchemyOfferRepository(session).append_observations(
        offer_id,
        batch,
        AggregateVersion(0),
    )
    assert persisted == AggregateVersion(1)
    assert staged == [expected_event_type]


def _job(*, with_event: bool) -> Job:
    job_id = JobId(stable_uuid("job:requested"))
    job = Job(
        JobState(
            id=job_id,
            display_id="JOB-001",
            job_type="CATALOG_INGEST",
            queue_name="catalog",
            status=JobStatus.REQUESTED,
            priority=50,
            idempotency_key="job-one",
            site_id=None,
            aggregate_type=None,
            aggregate_id=None,
            payload=JobPayloadJson(
                FrozenJsonObject.from_mapping({"provider": "rakuten"})
            ),
            payload_artifact_id=None,
            scheduled_at=None,
            available_at=AwareUtcDateTime(FIXED_TIME),
            started_at=None,
            completed_at=None,
            max_attempts=3,
            attempt_count=0,
            lease_owner=None,
            lease_expires_at=None,
            correlation_id=CorrelationId(stable_uuid("correlation:job")),
            causation_id=None,
            parent_job_id=None,
            budget_jpy=None,
            created_by_actor_type="USER",
            created_by_actor_id=ActorId(stable_uuid("actor:job")),
            last_error_class=None,
            last_error_code=None,
            last_error_message=None,
            created_at=AwareUtcDateTime(FIXED_TIME),
            updated_at=AwareUtcDateTime(FIXED_TIME),
            lock_version=AggregateVersion(0),
            job_version=1,
            deadline_at=AwareUtcDateTime(LATER),
            cancel_requested_at=None,
        )
    )
    if with_event:
        job._record_event(
            OpsJobRequested(
                event_id=stable_uuid("event:job-requested"),
                aggregate_id=job_id,
                aggregate_version=AggregateVersion(0),
                occurred_at=FIXED_TIME,
                causation_id=None,
                data=FrozenJsonObject.from_mapping(
                    {
                        "available_at": FIXED_TIME.isoformat(),
                        "job_id": str(job_id.value),
                        "job_type": "CATALOG_INGEST",
                        "queue": "catalog",
                    }
                ),
            )
        )
    return job


def test_job_add_requires_matching_requested_event_before_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged: list[str] = []
    monkeypatch.setattr(ops_sql, "register_pending_events", lambda *_a, **_k: None)
    monkeypatch.setattr(
        ops_sql,
        "stage_registered_events",
        lambda _session, **kwargs: staged.append(kwargs["expected_event_type"]),
    )
    session = _ScriptedSession(_Result())
    assert ops_sql.SqlAlchemyJobRepository(session).add(
        _job(with_event=True)
    ) == AggregateVersion(0)
    assert staged == ["jp.raos.ops.job_requested.v1"]

    missing_session = _ScriptedSession()
    with pytest.raises(PersistenceError) as missing:
        ops_sql.SqlAlchemyJobRepository(missing_session).add(_job(with_event=False))
    assert missing.value.code is PersistenceErrorCode.STATE_CONFLICT
    assert missing_session.statements == []


def _action(
    *,
    status: ActionCandidateStatus,
    decided: bool,
    with_event: bool,
) -> ActionCandidate:
    candidate_id = ActionCandidateId(stable_uuid("action:one"))
    candidate = ActionCandidate(
        ActionCandidateState(
            id=candidate_id,
            display_id="ACTION-001",
            site_id=SiteId(stable_uuid("site:one")),
            category_id=None,
            action_type=ActionCandidateActionType.CREATE,
            target_entity_type=ActionCandidateTargetEntityType.ARTICLE,
            target_entity_id=None,
            secondary_entity_id=None,
            source_signal="editorial-gap",
            expected_incremental_profit_jpy=None,
            urgency_score=Decimal("50"),
            confidence=Decimal("0.9"),
            priority_score=Decimal("45"),
            status=status,
            rationale=ActionCandidateRationaleJson(
                FrozenJsonObject.from_mapping({"reason": "coverage gap"})
            ),
            generated_at=AwareUtcDateTime(FIXED_TIME),
            expires_at=AwareUtcDateTime(LATER),
            decided_by_principal_id=(
                PrincipalId(stable_uuid("principal:decider")) if decided else None
            ),
            decided_at=AwareUtcDateTime(LATER) if decided else None,
            decision_note="approved" if decided else None,
            created_at=AwareUtcDateTime(FIXED_TIME),
            updated_at=AwareUtcDateTime(FIXED_TIME),
            lock_version=AggregateVersion(0),
        )
    )
    if with_event:
        candidate._record_event(
            PortfolioActionCandidateDecided(
                event_id=stable_uuid("event:action-decided"),
                aggregate_id=candidate_id,
                aggregate_version=AggregateVersion(1),
                occurred_at=LATER,
                causation_id=None,
                data=FrozenJsonObject.from_mapping(
                    {
                        "action_candidate_id": str(candidate_id.value),
                        "decided_at": LATER.isoformat(),
                        "decision": status.value,
                    }
                ),
            )
        )
    return candidate


def test_action_save_stages_only_a_new_matching_decision_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _action(
        status=ActionCandidateStatus.PROPOSED,
        decided=False,
        with_event=False,
    )
    decided = _action(
        status=ActionCandidateStatus.ACCEPTED,
        decided=True,
        with_event=True,
    )
    staged: list[str] = []
    monkeypatch.setattr(
        portfolio_sql,
        "register_pending_events",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        portfolio_sql,
        "stage_registered_events",
        lambda _session, **kwargs: staged.append(kwargs["expected_event_type"]),
    )
    session = _ScriptedSession(
        _Result(row=portfolio_sql._encode_portfolio_action_candidate(current.state)),
        _Result(scalar=1),
    )
    assert portfolio_sql.SqlAlchemyActionCandidateRepository(session).save(
        decided,
        AggregateVersion(0),
    ) == AggregateVersion(1)
    assert staged == ["jp.raos.portfolio.action_candidate_decided.v1"]

    ordinary = replace(
        current, state=replace(current.state, priority_score=Decimal("40"))
    )
    ordinary_session = _ScriptedSession(
        _Result(row=portfolio_sql._encode_portfolio_action_candidate(current.state)),
        _Result(scalar=1),
    )
    assert portfolio_sql.SqlAlchemyActionCandidateRepository(ordinary_session).save(
        ordinary,
        AggregateVersion(0),
    ) == AggregateVersion(1)
    assert staged == ["jp.raos.portfolio.action_candidate_decided.v1"]

    missing_event = _action(
        status=ActionCandidateStatus.REJECTED,
        decided=True,
        with_event=False,
    )
    missing_session = _ScriptedSession(
        _Result(row=portfolio_sql._encode_portfolio_action_candidate(current.state))
    )
    with pytest.raises(PersistenceError) as missing:
        portfolio_sql.SqlAlchemyActionCandidateRepository(missing_session).save(
            missing_event,
            AggregateVersion(0),
        )
    assert missing.value.code is PersistenceErrorCode.STATE_CONFLICT
    assert len(missing_session.statements) == 1


def test_runtime_series_lock_and_event_staging_have_required_source_order() -> None:
    append_source = inspect.getsource(
        ops_sql.SqlAlchemyRuntimeSettingRepository.append_version
    )
    assert (
        append_source.index("lock_runtime_setting_version_series(")
        < (append_source.index("self.get_current("))
        < append_source.index("insert(")
    )

    job_source = inspect.getsource(ops_sql.SqlAlchemyJobRepository.add)
    assert (
        job_source.index("register_pending_events(")
        < job_source.index("insert(")
        < job_source.index("stage_registered_events(")
    )
    assert 'expected_event_type="jp.raos.ops.job_requested.v1"' in job_source

    action_source = inspect.getsource(
        portfolio_sql.SqlAlchemyActionCandidateRepository.save
    )
    assert (
        action_source.index("register_pending_events(")
        < action_source.index("_cas_update(")
        < action_source.index("stage_registered_events(")
    )
    assert "jp.raos.portfolio.action_candidate_decided.v1" in action_source

    offer_append_source = inspect.getsource(
        catalog_sql.SqlAlchemyOfferRepository.append_observations
    )
    assert offer_append_source.index("_cas_update(") < offer_append_source.index(
        "stage_registered_events("
    )
