"""Deterministic, identity-safe ST-0503 V2 catalog normalization behavior."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType

import pytest

from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    CATALOG_EVENT_CHANNEL_V2,
    CATALOG_EVENT_TYPE_V2,
    CATALOG_FORBIDDEN_RECOMMENDATION_INPUTS_V2,
    CATALOG_IDENTITY_OPEN_DECISION_V2,
    CATALOG_NORMALIZER_VERSION_V2,
    CatalogConfidenceStatusV2,
    CatalogIdentityStatusV2,
    CatalogNormalizationRuntimeFailure,
    CatalogNormalizationRuntimeFailureCode,
    CatalogObservationKindV2,
    CatalogReadinessV2,
    CatalogReplayStatusV2,
    CatalogSourceModeV2,
    fail_catalog_normalization_runtime,
    normalize_persisted_item_search_page_v2,
)
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    ProviderTextTrustV2,
)

from runtime_v2_fixtures import (
    normalization_service_v2,
    normalization_store_v2,
    source_fixture_v2,
)


def test_exact_persisted_page_normalizes_to_stable_provenance_bound_records(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path)
    first = normalize_persisted_item_search_page_v2(
        command=fixture.command,
        page=fixture.page,
        raw_body=fixture.raw_body,
    )
    second = normalize_persisted_item_search_page_v2(
        command=fixture.command,
        page=fixture.page,
        raw_body=fixture.raw_body,
    )
    receipt = fixture.source_step.receipt

    assert first == second
    assert receipt is not None
    assert first.normalizer_version == CATALOG_NORMALIZER_VERSION_V2
    assert first.source_snapshot.source_mode is CatalogSourceModeV2.RECORDED_PERSISTED
    assert (
        first.source_snapshot.source_session_id
        == fixture.source_step.session.session_id
    )
    assert (
        first.source_snapshot.source_session_version
        == fixture.source_step.session.version
    )
    assert first.source_snapshot.receipt_id == receipt.receipt_id
    assert first.source_snapshot.raw_sha256 == receipt.artifact_sha256
    assert first.source_snapshot.raw_byte_size == receipt.byte_size
    assert first.source_snapshot.request_fingerprint == receipt.request_fingerprint
    assert first.source_snapshot.confidence is None
    assert (
        first.source_snapshot.confidence_status
        is CatalogConfidenceStatusV2.SOURCE_ABSENT
    )
    assert len(first.candidates) == len(first.offers) == 2
    assert len(first.observations) == 8
    assert len({candidate.candidate_id for candidate in first.candidates}) == 2
    assert len({offer.offer_id for offer in first.offers}) == 2
    assert len({observation.observation_id for observation in first.observations}) == 8


def test_od006_never_infers_identity_or_ranking_from_provider_text(
    tmp_path: Path,
) -> None:
    canary = "BEST MODEL-X JAN 4900000000001 PROFIT EPC RPM"
    fixture = source_fixture_v2(tmp_path, item_name=canary)
    batch = normalize_persisted_item_search_page_v2(
        command=fixture.command,
        page=fixture.page,
        raw_body=fixture.raw_body,
    )

    assert batch.identity_status is CatalogIdentityStatusV2.HUMAN_REVIEW
    assert batch.readiness is CatalogReadinessV2.NOT_READY
    assert batch.open_decision == CATALOG_IDENTITY_OPEN_DECISION_V2 == "OD-006"
    assert batch.canonical_products == ()
    assert batch.grouping_decisions == ()
    assert batch.provider_derived_recommendation_inputs == ()
    assert set(CATALOG_FORBIDDEN_RECOMMENDATION_INPUTS_V2).issuperset(
        {
            "affiliate_rate",
            "commission",
            "epc",
            "profit",
            "reward",
            "review_aggregate",
            "review_body",
            "rpm",
        }
    )
    candidate = batch.candidates[0]
    assert candidate.item_name.value == canary
    assert candidate.item_name.trust is ProviderTextTrustV2.UNTRUSTED_DATA
    assert candidate.model_number_candidate is None
    assert candidate.jan_code_candidate is None
    assert candidate.canonical_product_id is None
    assert candidate.identity_confidence is None
    assert candidate.recommendation_eligible is False
    assert batch.offers[0].canonical_product_id is None
    assert batch.offers[0].recommendation_eligible is False
    assert canary not in repr(candidate)
    assert canary not in repr(batch)


def test_price_availability_postage_and_affiliate_link_are_nonranking_observations(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path)
    batch = normalize_persisted_item_search_page_v2(
        command=fixture.command,
        page=fixture.page,
        raw_body=fixture.raw_body,
    )
    by_offer = {
        offer.offer_id: tuple(
            observation
            for observation in batch.observations
            if observation.offer_id == offer.offer_id
        )
        for offer in batch.offers
    }

    assert all(
        tuple(observation.kind for observation in observations)
        == (
            CatalogObservationKindV2.PRICE_JPY,
            CatalogObservationKindV2.AVAILABILITY_PROVIDER_FLAG,
            CatalogObservationKindV2.POSTAGE_INCLUDED_PROVIDER_FLAG,
            CatalogObservationKindV2.AFFILIATE_LINK,
        )
        for observations in by_offer.values()
    )
    assert all(
        observation.recommendation_input is False
        and observation.confidence is None
        and observation.confidence_status is CatalogConfidenceStatusV2.SOURCE_ABSENT
        for observation in batch.observations
    )
    assert batch.observations[0].integer_value == 10_001
    assert batch.observations[0].unit_code == "JPY"
    assert batch.observations[3].url_value is not None
    assert batch.observations[3].url_value.trust is ProviderTextTrustV2.UNTRUSTED_DATA


@pytest.mark.parametrize(
    ("item_ordinals", "operation_index"),
    (((1,), 0), ((2, 3), 1), ((3, 2, 1), 2)),
)
def test_bounded_structural_variants_preserve_order_and_deterministic_ids(
    tmp_path: Path,
    item_ordinals: tuple[int, ...],
    operation_index: int,
) -> None:
    fixture = source_fixture_v2(
        tmp_path,
        item_ordinals=item_ordinals,
        normalize_operation_index=operation_index,
    )
    first = normalize_persisted_item_search_page_v2(
        command=fixture.command,
        page=fixture.page,
        raw_body=fixture.raw_body,
    )
    second = normalize_persisted_item_search_page_v2(
        command=fixture.command,
        page=fixture.page,
        raw_body=fixture.raw_body,
    )

    assert first == second
    assert tuple(candidate.ordinal for candidate in first.candidates) == tuple(
        range(1, len(item_ordinals) + 1)
    )
    assert tuple(
        candidate.external_item_code.value for candidate in first.candidates
    ) == tuple(f"synthetic-shop:item-{value}" for value in item_ordinals)
    assert len({candidate.candidate_id for candidate in first.candidates}) == len(
        item_ordinals
    )
    assert first.canonical_products == ()
    assert first.grouping_decisions == ()


def test_application_atomically_persists_repositories_outbox_and_replays(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path)
    store = normalization_store_v2(tmp_path)
    service = normalization_service_v2(fixture=fixture, store=store)

    first = service.normalize(fixture.command)
    replay = service.normalize(fixture.command)
    batch = first.persisted.batch

    assert first.replay_status is CatalogReplayStatusV2.DIRECT_COMMIT
    assert replay.replay_status is CatalogReplayStatusV2.IDEMPOTENT_REPLAY
    assert replay.persisted == first.persisted
    assert first.external_actions == replay.external_actions == 0
    assert store.current_version == 1
    assert store.load_batch(batch.batch_id) == batch
    assert (
        store.load_snapshot(batch.source_snapshot.snapshot_id) == batch.source_snapshot
    )
    assert store.load_candidate(batch.candidates[0].candidate_id) == batch.candidates[0]
    assert store.load_offer(batch.offers[0].offer_id) == batch.offers[0]
    assert store.list_observations(batch.offers[0].offer_id) == batch.observations[:4]
    event = store.load_outbox(first.persisted.event.event_id)
    assert event == first.persisted.event
    assert event.event_type == CATALOG_EVENT_TYPE_V2
    assert event.channel == CATALOG_EVENT_CHANNEL_V2
    assert event.identity_status is CatalogIdentityStatusV2.HUMAN_REVIEW
    assert event.readiness is CatalogReadinessV2.NOT_READY
    assert event.external_actions == 0


def test_closed_runtime_failure_supports_traceback_and_context_manager() -> None:
    @contextmanager
    def passthrough() -> Generator[None]:
        try:
            yield
        except CatalogNormalizationRuntimeFailure:
            raise

    failure = CatalogNormalizationRuntimeFailure(
        CatalogNormalizationRuntimeFailureCode.SOURCE_INTEGRITY
    )
    failure.__traceback__ = None
    assert failure.__traceback__ is None
    assert failure.args == ("SOURCE_INTEGRITY",)
    assert "secret" not in repr(failure)

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        with passthrough():
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.SOURCE_INTEGRITY
            )
    traceback: TracebackType | None = caught.value.__traceback__
    assert traceback is not None
    assert caught.value.code is CatalogNormalizationRuntimeFailureCode.SOURCE_INTEGRITY
