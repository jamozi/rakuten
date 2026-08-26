"""Lossless structural normalization behavior for ST-0503."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import timedelta
import pickle
from typing import Callable, cast
from uuid import UUID

from raos.domain.catalog.catalog_normalization import (
    CatalogNormalizationBatch,
    CatalogNormalizationCommand,
    CatalogNormalizationFailure,
    CatalogNormalizationFailureCode,
    ExecutionStatus,
    IdentityStatus,
    NameNormalization,
    NormalizationDecision,
    NormalizationMode,
    NormalizationScope,
    RepositoryBoundary,
    SourceConfidenceStatus,
    SourceSnapshotStatus,
    SourceValidationStatus,
    lossless_batch_from_command,
)
from raos.domain.catalog.rakuten_item_search import RakutenItemSearchResult

import pytest

from .support import (
    ENDPOINT_ID,
    INGESTED_AT,
    INGESTION_ID,
    OBSERVED_AT,
    RAW_SHA256,
    SECOND_INGESTION_ID,
    expected_batch,
    item_search_command,
    item_search_result,
    normalization_command,
    normalization_service,
)


def test_golden_lossless_recorded_normalization() -> None:
    batch = normalization_service().normalize(normalization_command())

    assert batch.mode is NormalizationMode.RECORDED_TEST_ONLY
    assert batch.scope is NormalizationScope.LOSSLESS_STRUCTURAL_ONLY
    assert batch.identity_status is IdentityStatus.REVIEW_REQUIRED
    assert batch.decision is NormalizationDecision.NOT_READY
    assert len(batch.candidates) == 2
    assert [draft.external_item_code for draft in batch.candidates] == [
        "shop-a:item-1",
        "shop-b:item-2",
    ]
    assert batch.candidates[0].display_name == batch.candidates[1].display_name
    assert all(
        draft.normalized_name == draft.display_name
        and draft.name_normalization is NameNormalization.LOSSLESS_PASSTHROUGH
        and draft.product_id is None
        and draft.model_number is None
        and draft.jan_code is None
        for draft in batch.candidates
    )
    assert batch.canonical_products == ()
    assert batch.grouping_decisions == ()
    assert batch.live_eligible is False


def test_unknown_exact_command_fails_without_fallback() -> None:
    with pytest.raises(CatalogNormalizationFailure) as caught:
        normalization_service().normalize(
            normalization_command(ingestion_request_id=SECOND_INGESTION_ID)
        )
    assert caught.value.code is CatalogNormalizationFailureCode.NORMALIZER_UNAVAILABLE


def test_command_fingerprint_is_deterministic_and_binds_exact_inputs() -> None:
    first = normalization_command()
    second = normalization_command()
    changed = normalization_command(ingestion_request_id=SECOND_INGESTION_ID)

    assert first == second
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != changed.fingerprint
    assert first.search_command == item_search_command()
    assert first.search_result == item_search_result()
    assert first.ingestion_request_id == INGESTION_ID
    assert first.expected_raw_sha256 == RAW_SHA256
    assert first.ingested_at == INGESTED_AT


@pytest.mark.parametrize(
    "factory",
    (
        lambda: replace(normalization_command(), fingerprint="0" * 64),
        lambda: replace(normalization_command(), expected_raw_sha256="0" * 64),
        lambda: replace(normalization_command(), ingestion_request_id=UUID(int=0)),
        lambda: replace(
            normalization_command(), ingested_at=OBSERVED_AT - timedelta(microseconds=1)
        ),
        lambda: CatalogNormalizationCommand.from_search_result(
            search_command=item_search_command(),
            search_result=item_search_result(),
            ingestion_request_id=UUID(int=0),
            ingested_at=INGESTED_AT,
        ),
        lambda: CatalogNormalizationCommand(
            search_command=item_search_command(),
            search_result=cast(RakutenItemSearchResult, object()),
            ingestion_request_id=INGESTION_ID,
            normalizer=normalization_command().normalizer,
            ingested_at=INGESTED_AT,
            expected_raw_sha256=RAW_SHA256,
            fingerprint=normalization_command().fingerprint,
        ),
    ),
)
def test_command_rejects_provenance_time_type_and_hash_drift(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(CatalogNormalizationFailure):
        factory()


def test_source_reference_is_receipt_only_and_non_persistent() -> None:
    source = expected_batch().candidates[0].source

    assert source.provider == "RAKUTEN_ICHIBA"
    assert source.api_version == "2026-07-01"
    assert source.endpoint_id == ENDPOINT_ID
    assert source.command_fingerprint == item_search_command().fingerprint
    assert source.request_sha256 == item_search_result().page.request_sha256
    assert source.raw_artifact_id == item_search_result().page.raw_artifact.artifact_id
    assert source.raw_sha256 == RAW_SHA256
    assert source.raw_byte_size == item_search_result().page.raw_artifact.byte_size
    assert source.observed_at == OBSERVED_AT
    assert source.ingested_at == INGESTED_AT
    assert source.source_snapshot_id is None
    assert source.source_snapshot_status is SourceSnapshotStatus.NOT_AVAILABLE
    assert source.confidence is None
    assert source.confidence_status is SourceConfidenceStatus.SOURCE_ABSENT
    assert (
        source.validation_status
        is SourceValidationStatus.VALIDATED_RECORDED_RECEIPT_ONLY
    )
    assert source.persistence_executed is False
    assert source.repository is RepositoryBoundary.ABSENT
    assert source.database is ExecutionStatus.NOT_EXECUTED


def test_candidate_drafts_are_ordered_lossless_and_identity_free() -> None:
    candidates = expected_batch().candidates

    assert [candidate.ordinal for candidate in candidates] == [1, 2]
    assert [candidate.external_genre_id for candidate in candidates] == [100, 101]
    assert [candidate.display_name for candidate in candidates] == [
        "Model X JAN 4900000000000",
        "Model X JAN 4900000000000",
    ]
    assert all(
        candidate.normalized_name == candidate.display_name for candidate in candidates
    )
    assert all(
        candidate.name_normalization is NameNormalization.LOSSLESS_PASSTHROUGH
        for candidate in candidates
    )
    assert candidates[0].image_urls == (
        "https://example.invalid/images/100-2.jpg",
        "https://example.invalid/images/100-1.jpg",
    )
    for candidate in candidates:
        assert candidate.candidate_id is None
        assert candidate.product_id is None
        assert candidate.shop_id is None
        assert candidate.genre_id is None
        assert candidate.model_number is None
        assert candidate.jan_code is None
        assert candidate.status is None
        assert candidate.confidence is None
        assert candidate.identity_decision is None
        assert candidate.grouping_keys == ()


def test_offer_drafts_do_not_infer_offer_shop_status_or_economics() -> None:
    offers = expected_batch().offers
    assert [offer.external_item_code for offer in offers] == [
        "shop-a:item-1",
        "shop-b:item-2",
    ]
    assert all(offer.endpoint_id == ENDPOINT_ID for offer in offers)
    assert offers[0].item_url == "https://example.invalid/shop-a/item-1"
    for offer in offers:
        assert offer.observed_at == OBSERVED_AT
        assert offer.offer_id is None
        assert offer.product_id is None
        assert offer.shop_id is None
        assert offer.external_offer_id is None
        assert offer.status is None
        assert offer.price is None
        assert offer.currency is None
        assert offer.shipping is None
        assert offer.points is None
        assert offer.affiliate_url is None


def test_price_availability_and_review_facts_are_preserved_without_semantics() -> None:
    batch = expected_batch()
    assert [draft.amount_jpy for draft in batch.prices] == [1234, 2345]
    assert [draft.provider_value for draft in batch.availabilities] == [True, False]
    assert [draft.review_count for draft in batch.review_aggregates] == [3, None]
    assert [draft.review_average for draft in batch.review_aggregates] == [4.5, None]
    assert all(draft.tax_included is None for draft in batch.prices)
    assert all(draft.shipping is None for draft in batch.prices)
    assert all(draft.points is None for draft in batch.prices)
    assert all(draft.semantic_status is None for draft in batch.availabilities)
    assert all(draft.review_body is None for draft in batch.review_aggregates)
    assert all(draft.status is None for draft in batch.review_aggregates)
    assert all(draft.confidence is None for draft in batch.review_aggregates)


def test_batch_is_not_a_catalog_identity_or_persistence_claim() -> None:
    batch = expected_batch()
    assert batch.confidence is None
    assert batch.confidence_status is SourceConfidenceStatus.SOURCE_ABSENT
    assert batch.canonical_products == ()
    assert batch.grouping_decisions == ()
    assert batch.identity_decisions == ()
    assert batch.memberships == ()
    assert batch.merges == ()
    assert batch.splits == ()
    assert batch.repository is RepositoryBoundary.ABSENT
    assert batch.persistence_executed is False
    assert batch.database is ExecutionStatus.NOT_EXECUTED
    assert batch.job is ExecutionStatus.NOT_EXECUTED
    assert batch.event is ExecutionStatus.NOT_EXECUTED
    assert batch.live_eligible is False
    assert batch.decision is NormalizationDecision.NOT_READY
    assert batch.empty_identity_interpretation == (
        "NO_IDENTITY_OR_GROUPING_DECISION_NOT_ZERO_CONFIDENCE"
    )


def test_empty_recorded_page_projects_empty_draft_sets_without_claiming_completeness() -> (
    None
):
    result = item_search_result()
    empty_page = replace(result.page, count=0, page_count=0, items=())
    empty_result = replace(result, page=empty_page)
    command = CatalogNormalizationCommand.from_search_result(
        search_command=item_search_command(),
        search_result=empty_result,
        ingestion_request_id=INGESTION_ID,
        ingested_at=INGESTED_AT,
    )
    batch = lossless_batch_from_command(command)
    assert batch.candidates == ()
    assert batch.offers == ()
    assert batch.prices == ()
    assert batch.availabilities == ()
    assert batch.review_aggregates == ()
    assert batch.identity_status is IdentityStatus.REVIEW_REQUIRED
    assert batch.decision is NormalizationDecision.NOT_READY


@pytest.mark.parametrize(
    "factory",
    (
        lambda: replace(expected_batch().candidates[0], ordinal=True),
        lambda: replace(
            expected_batch().candidates[0], external_item_code="missing-colon"
        ),
        lambda: replace(expected_batch().candidates[0], normalized_name="inferred"),
        lambda: replace(
            expected_batch().candidates[0], candidate_id=cast(None, UUID(int=1))
        ),
        lambda: replace(expected_batch().offers[0], endpoint_id=UUID(int=0)),
        lambda: replace(
            expected_batch().offers[0], external_offer_id=cast(None, "inferred")
        ),
        lambda: replace(expected_batch().prices[0], amount_jpy=True),
        lambda: replace(
            expected_batch().availabilities[0], provider_value=cast(bool, 1)
        ),
        lambda: replace(expected_batch().review_aggregates[0], review_count=True),
        lambda: replace(
            expected_batch().review_aggregates[0], review_average=float("nan")
        ),
        lambda: replace(expected_batch().candidates[0].source, raw_byte_size=True),
        lambda: replace(expected_batch(), persistence_executed=True),
        lambda: replace(
            expected_batch(), canonical_products=cast(tuple[()], ("product",))
        ),
    ),
)
def test_drafts_and_batch_reject_types_inference_and_persistence(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(CatalogNormalizationFailure):
        factory()


def test_values_are_redacted_immutable_and_non_pickleable() -> None:
    command = normalization_command()
    batch = expected_batch()
    assert "Model X" not in repr(command)
    assert "Model X" not in repr(batch)
    with pytest.raises(TypeError):
        pickle.dumps(command)
    with pytest.raises(TypeError):
        pickle.dumps(batch)
    with pytest.raises(Exception):
        setattr(batch, "candidates", ())


def test_public_batch_has_only_closed_typed_fields() -> None:
    assert tuple(field.name for field in fields(CatalogNormalizationBatch)) == (
        "command_fingerprint",
        "ingestion_request_id",
        "mode",
        "scope",
        "candidates",
        "offers",
        "prices",
        "availabilities",
        "review_aggregates",
        "identity_status",
        "confidence",
        "confidence_status",
        "canonical_products",
        "grouping_decisions",
        "identity_decisions",
        "memberships",
        "merges",
        "splits",
        "repository",
        "persistence_executed",
        "database",
        "job",
        "event",
        "live_eligible",
        "decision",
        "empty_identity_interpretation",
    )
