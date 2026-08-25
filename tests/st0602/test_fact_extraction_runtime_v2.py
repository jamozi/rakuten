"""Focused exact-domain and application checks for ST-0602 V2."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import pickle

import pytest

from raos.application.evidence.fact_extraction_runtime_v2 import (
    DurableFactExtractionServiceV2,
)
from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    CatalogObservationKindV2,
)
from raos.domain.evidence.fact_extraction_runtime_v2 import (
    FACT_EXTRACTION_CONFIDENCE_V2,
    FACT_EXTRACTION_EVENT_TYPE_V2,
    ExactOfferFactV2,
    FactConfidenceBasisV2,
    FactExtractionFailureCodeV2,
    FactExtractionFailureV2,
    FactExtractionReplayStatusV2,
    FactPublicationReadinessV2,
    FactSubjectTypeV2,
    FactTruthAttestationV2,
    build_fact_extraction_artifacts_v2,
    canonical_json_bytes_v2,
    fact_from_mapping_v2,
    fact_mapping_v2,
)
from tests.st0602.runtime_v2_fixtures import (
    exact_dependencies_v2,
    fact_store_v2,
)


def _failure_code(call: object) -> FactExtractionFailureCodeV2:
    assert callable(call)
    with pytest.raises(FactExtractionFailureV2) as captured:
        call()
    return captured.value.code


def test_extracts_only_exact_structural_offer_facts(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    command, batch, event = build_fact_extraction_artifacts_v2(
        artifact=dependencies.artifact,
        normalization=dependencies.normalization,
    )
    assert (
        command.source_snapshot_id
        == dependencies.normalization.batch.source_snapshot.snapshot_id
    )
    assert command.job_type == "evidence.extract_facts.v1"
    assert command.queue == "quality"
    assert command.subject_hints == ()
    assert len(batch.facts) == 6
    assert {fact.predicate for fact in batch.facts} == {
        CatalogObservationKindV2.PRICE_JPY.value,
        CatalogObservationKindV2.AVAILABILITY_PROVIDER_FLAG.value,
        CatalogObservationKindV2.POSTAGE_INCLUDED_PROVIDER_FLAG.value,
    }
    assert all(fact.subject_type is FactSubjectTypeV2.OFFER for fact in batch.facts)
    assert all(fact.confidence == FACT_EXTRACTION_CONFIDENCE_V2 for fact in batch.facts)
    assert all(
        fact.confidence_basis
        is FactConfidenceBasisV2.EXACT_STRUCTURAL_EXTRACTION_NOT_TRUTH_ATTESTATION
        for fact in batch.facts
    )
    assert all(
        validation.truth_attestation is FactTruthAttestationV2.NOT_ATTESTED
        and validation.publication_readiness is FactPublicationReadinessV2.NOT_READY
        and validation.manual_review_required
        for validation in batch.validations
    )
    assert event.event_type == FACT_EXTRACTION_EVENT_TYPE_V2
    assert event.schema_data == {
        "source_snapshot_id": str(command.source_snapshot_id),
        "fact_ids": [str(fact.fact_id) for fact in batch.facts],
        "extractor_version": command.extractor_version,
        "manual_review_required_count": 6,
    }
    assert (
        batch.external_action_count,
        batch.provider_action_count,
        batch.publication_action_count,
        batch.ai_action_count,
        event.external_action_count,
    ) == (0, 0, 0, 0, 0)


def test_affiliate_urls_are_not_facts_or_serialized(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    _command, batch, _event = build_fact_extraction_artifacts_v2(
        artifact=dependencies.artifact,
        normalization=dependencies.normalization,
    )
    payload = canonical_json_bytes_v2(batch.canonical_material)
    assert b"affiliate" not in payload.lower()
    assert b"http" not in payload.lower()
    assert b"Unicode" not in payload
    assert all("URL" not in fact.predicate for fact in batch.facts)


def test_service_commits_and_replays_deterministically(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    store = fact_store_v2(tmp_path)
    service = DurableFactExtractionServiceV2(store)
    first = service.extract(
        artifact=dependencies.artifact,
        normalization=dependencies.normalization,
    )
    second = service.extract(
        artifact=dependencies.artifact,
        normalization=dependencies.normalization,
    )
    assert first.replay_status is FactExtractionReplayStatusV2.DIRECT_COMMIT
    assert second.replay_status is FactExtractionReplayStatusV2.IDEMPOTENT_REPLAY
    assert first.persisted == second.persisted
    assert store.verify_chain() == (first.persisted.chain_hash, 1)
    assert store.load_batch(first.persisted.batch.batch_id) == first.persisted.batch
    assert store.load_outbox(first.persisted.event.event_id) == first.persisted.event
    assert (
        store.list_validations(first.persisted.batch.batch_id)
        == first.persisted.batch.validations
    )
    assert all(
        store.load_fact(fact.fact_id) == fact for fact in first.persisted.batch.facts
    )


def test_numeric_and_boolean_types_are_exact(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path, item_ordinals=(1,))
    _command, batch, _event = build_fact_extraction_artifacts_v2(
        artifact=dependencies.artifact,
        normalization=dependencies.normalization,
    )
    price = next(fact for fact in batch.facts if fact.value_numeric is not None)
    booleans = [fact for fact in batch.facts if fact.value_boolean is not None]
    assert type(price.value_numeric) is Decimal
    assert price.value_numeric == Decimal("10001")
    assert price.unit_code == "JPY" and price.locale == "ja-JP"
    assert all(
        type(fact.value_boolean) is bool and fact.unit_code is None for fact in booleans
    )
    assert all(fact.locale is None for fact in booleans)


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (
            {"confidence": Decimal("0.9999")},
            FactExtractionFailureCodeV2.INVALID_ARGUMENT,
        ),
        ({"confidence": Decimal("1")}, FactExtractionFailureCodeV2.INVALID_ARGUMENT),
        ({"confidence": 1.0}, FactExtractionFailureCodeV2.INVALID_ARGUMENT),
        ({"unit_code": "USD"}, FactExtractionFailureCodeV2.VALUE_INVALID),
        ({"value_numeric": Decimal("1.5")}, FactExtractionFailureCodeV2.VALUE_INVALID),
        (
            {"value_numeric": Decimal("100000000000000000000")},
            FactExtractionFailureCodeV2.VALUE_INVALID,
        ),
    ],
)
def test_invalid_confidence_unit_and_numeric_values_fail_closed(
    tmp_path, change: dict[str, object], code: FactExtractionFailureCodeV2
) -> None:
    dependencies = exact_dependencies_v2(tmp_path, item_ordinals=(1,))
    _command, batch, _event = build_fact_extraction_artifacts_v2(
        artifact=dependencies.artifact,
        normalization=dependencies.normalization,
    )
    price = next(fact for fact in batch.facts if fact.value_numeric is not None)
    assert _failure_code(lambda: replace(price, **change)) is code


def test_mapping_round_trip_and_malformed_value_fail_closed(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path, item_ordinals=(1,))
    _command, batch, _event = build_fact_extraction_artifacts_v2(
        artifact=dependencies.artifact,
        normalization=dependencies.normalization,
    )
    fact = batch.facts[0]
    mapping = fact_mapping_v2(fact)
    assert fact_from_mapping_v2(mapping) == fact
    malformed = dict(mapping)
    malformed["confidence"] = "NaN"
    assert (
        _failure_code(lambda: fact_from_mapping_v2(malformed))
        is FactExtractionFailureCodeV2.TAMPER_DETECTED
    )
    price = next(item for item in batch.facts if item.value_numeric is not None)
    noncanonical_numeric = fact_mapping_v2(price)
    noncanonical_numeric["value_numeric"] = "010001"
    assert (
        _failure_code(lambda: fact_from_mapping_v2(noncanonical_numeric))
        is FactExtractionFailureCodeV2.TAMPER_DETECTED
    )


def test_duplicates_out_of_order_and_boolean_action_counts_fail_closed(
    tmp_path,
) -> None:
    dependencies = exact_dependencies_v2(tmp_path, item_ordinals=(1,))
    _command, batch, _event = build_fact_extraction_artifacts_v2(
        artifact=dependencies.artifact,
        normalization=dependencies.normalization,
    )
    assert (
        _failure_code(
            lambda: replace(
                batch, facts=batch.facts[::-1], validations=batch.validations[::-1]
            )
        )
        is FactExtractionFailureCodeV2.INVALID_ARGUMENT
    )
    assert (
        _failure_code(
            lambda: replace(
                batch,
                facts=(batch.facts[0], batch.facts[0]),
                validations=(batch.validations[0], batch.validations[0]),
            )
        )
        is FactExtractionFailureCodeV2.INVALID_ARGUMENT
    )
    assert (
        _failure_code(lambda: replace(batch, external_action_count=False))
        is FactExtractionFailureCodeV2.INVALID_ARGUMENT
    )


def test_failure_is_closed_redacted_and_traceback_assignable() -> None:
    error = FactExtractionFailureV2(FactExtractionFailureCodeV2.SOURCE_INTEGRITY)
    assert str(error) == "SOURCE_INTEGRITY"
    assert "http" not in repr(error).lower()
    error.__traceback__ = None
    with pytest.raises(TypeError):
        pickle.dumps(error)
    uninitialized = object.__new__(ExactOfferFactV2)
    with pytest.raises(TypeError):
        pickle.dumps(uninitialized)
