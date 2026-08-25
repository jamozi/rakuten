"""Value-free deterministic ST-1402 decision behavior."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import timedelta
from typing import cast

import pytest

from raos.application.freshness.safe_degradation import (
    bind_safe_degradation_request,
)
from raos.domain.freshness.freshness import (
    FreshnessObservationStatus,
    FreshnessReviewAction,
    RecommendationOrderAction,
)
from raos.domain.freshness.safe_degradation import (
    AvailabilityAggregate,
    SafeDegradationAction,
    SafeDegradationFailure,
    SafeDegradationFailureCode,
    SafeDegradationNoticeCode,
    decide_safe_degradation,
)

from conftest import bound_request, freshness_request, freshness_result


def test_non_latest_price_hides_value_and_emits_only_notice_code() -> None:
    request = freshness_request(freshness_class_id="FRESH-001")
    decision_request = bound_request(request=request)
    decision = decide_safe_degradation(decision_request)

    assert decision.actions == (SafeDegradationAction.HIDE_VALUE,)
    assert decision.notice_code is (
        SafeDegradationNoticeCode.FRESH_001_OFFER_PRICE_NOT_LATEST
    )
    assert decision.review_action is FreshnessReviewAction.NONE
    assert decision.recommendation_order_action is RecommendationOrderAction.FORBIDDEN
    assert (
        decision.freshness_evaluation_fingerprint
        == freshness_result(request).fingerprint
    )


@pytest.mark.parametrize(
    "status",
    (
        FreshnessObservationStatus.MISSING,
        FreshnessObservationStatus.FETCH_FAILED,
        FreshnessObservationStatus.RECOVERY_UNVALIDATED,
    ),
)
def test_unknown_price_states_fail_closed_to_the_same_value_hiding_decision(
    status: FreshnessObservationStatus,
) -> None:
    request = freshness_request(
        freshness_class_id="FRESH-001",
        observation_status=status,
    )
    decision = decide_safe_degradation(bound_request(request=request))
    assert decision.actions == (SafeDegradationAction.HIDE_VALUE,)
    assert decision.notice_code is (
        SafeDegradationNoticeCode.FRESH_001_OFFER_PRICE_NOT_LATEST
    )


def test_price_recommendation_impact_preserves_review_candidate_without_reorder() -> (
    None
):
    request = freshness_request(
        freshness_class_id="FRESH-001",
        recommendation_basis_affected=True,
    )
    decision = decide_safe_degradation(bound_request(request=request))
    assert decision.review_action is FreshnessReviewAction.CREATE_REVIEW_CANDIDATE
    assert decision.recommendation_order_action is RecommendationOrderAction.FORBIDDEN


def test_availability_hides_assertion_without_pausing_cta_when_not_all_unavailable() -> (
    None
):
    request = freshness_request(freshness_class_id="FRESH-002")
    decision = decide_safe_degradation(
        bound_request(
            request=request,
            availability_aggregate=(
                AvailabilityAggregate.NOT_ALL_PRIMARY_OFFERS_UNAVAILABLE
            ),
        )
    )
    assert decision.actions == (SafeDegradationAction.HIDE_AVAILABILITY_ASSERTION,)
    assert decision.review_action is FreshnessReviewAction.NONE
    assert decision.notice_code is None


def test_all_primary_offers_unavailable_adds_only_cta_pause_and_review_candidates() -> (
    None
):
    request = freshness_request(freshness_class_id="FRESH-002")
    decision = decide_safe_degradation(
        bound_request(
            request=request,
            availability_aggregate=(
                AvailabilityAggregate.ALL_PRIMARY_OFFERS_UNAVAILABLE
            ),
        )
    )
    assert decision.actions == (
        SafeDegradationAction.HIDE_AVAILABILITY_ASSERTION,
        SafeDegradationAction.CTA_PAUSE_CANDIDATE,
    )
    assert decision.review_action is FreshnessReviewAction.CREATE_REVIEW_CANDIDATE
    assert decision.can_change_state is False
    assert decision.renderer_effects.value == "NOT_EXECUTED"


def test_non_latest_link_hides_cta_and_retains_body_only_with_valid_basis() -> None:
    request = freshness_request(freshness_class_id="FRESH-003")
    decision = decide_safe_degradation(bound_request(request=request))
    assert decision.actions == (
        SafeDegradationAction.HIDE_CTA,
        SafeDegradationAction.RETAIN_ARTICLE_BODY,
    )
    assert decision.review_action is FreshnessReviewAction.NONE
    assert decision.publication_authorized is False
    assert decision.live_eligible is False


def test_link_with_affected_recommendation_basis_rejects_instead_of_retaining_body() -> (
    None
):
    request = freshness_request(
        freshness_class_id="FRESH-003",
        recommendation_basis_affected=True,
    )
    with pytest.raises(SafeDegradationFailure) as raised:
        bound_request(request=request)
    assert raised.value.code is (
        SafeDegradationFailureCode.RECOMMENDATION_BASIS_INVALID
    )


@pytest.mark.parametrize(
    ("freshness_class_id", "age"),
    (
        ("FRESH-001", timedelta(hours=1)),
        ("FRESH-001", timedelta(hours=24)),
        ("FRESH-002", timedelta(hours=1)),
        ("FRESH-003", timedelta(hours=24)),
    ),
)
def test_latest_fresh_or_warning_evaluation_is_not_a_degradation_input(
    freshness_class_id: str,
    age: timedelta,
) -> None:
    request = freshness_request(
        freshness_class_id=freshness_class_id,
        age=age,
    )
    aggregate = (
        AvailabilityAggregate.NOT_ALL_PRIMARY_OFFERS_UNAVAILABLE
        if freshness_class_id == "FRESH-002"
        else AvailabilityAggregate.NOT_APPLICABLE
    )
    with pytest.raises(SafeDegradationFailure) as raised:
        bind_safe_degradation_request(
            freshness_request=request,
            freshness_result=freshness_result(request),
            availability_aggregate=aggregate,
        )
    assert raised.value.code is SafeDegradationFailureCode.FRESHNESS_NOT_DEGRADABLE


@pytest.mark.parametrize(
    "freshness_class_id",
    (
        "FRESH-004",
        "FRESH-005",
        "FRESH-006",
        "FRESH-007",
        "FRESH-008",
        "FRESH-009",
        "FRESH-010",
        "FRESH-011",
        "FRESH-012",
    ),
)
def test_remaining_freshness_classes_are_rejected_without_inference(
    freshness_class_id: str,
) -> None:
    request = freshness_request(
        freshness_class_id=freshness_class_id,
        age=timedelta(days=400),
    )
    with pytest.raises(SafeDegradationFailure) as raised:
        bind_safe_degradation_request(
            freshness_request=request,
            freshness_result=freshness_result(request),
            availability_aggregate=AvailabilityAggregate.NOT_APPLICABLE,
        )
    assert raised.value.code is (SafeDegradationFailureCode.UNSUPPORTED_FRESHNESS_CLASS)


def test_non_string_unhashable_class_material_fails_with_only_closed_codes() -> None:
    request = bound_request()
    decision = decide_safe_degradation(request)
    with pytest.raises(SafeDegradationFailure) as binding_failure:
        replace(
            request.freshness,
            freshness_class_id=cast(str, []),
        )
    assert binding_failure.value.code is (
        SafeDegradationFailureCode.FRESHNESS_RESULT_INVALID
    )
    with pytest.raises(SafeDegradationFailure) as decision_failure:
        replace(
            decision,
            freshness_class_id=cast(str, []),
        )
    assert decision_failure.value.code is SafeDegradationFailureCode.DECISION_MISMATCH


def test_availability_aggregate_is_required_only_for_availability_class() -> None:
    price_request = freshness_request(freshness_class_id="FRESH-001")
    availability_request = freshness_request(freshness_class_id="FRESH-002")
    with pytest.raises(SafeDegradationFailure):
        bound_request(
            request=price_request,
            availability_aggregate=(
                AvailabilityAggregate.ALL_PRIMARY_OFFERS_UNAVAILABLE
            ),
        )
    with pytest.raises(SafeDegradationFailure):
        bound_request(
            request=availability_request,
            availability_aggregate=AvailabilityAggregate.NOT_APPLICABLE,
        )


def test_decision_fingerprint_is_deterministic_and_request_bound() -> None:
    first_request = freshness_request(freshness_class_id="FRESH-002")
    first = decide_safe_degradation(
        bound_request(
            request=first_request,
            availability_aggregate=(
                AvailabilityAggregate.NOT_ALL_PRIMARY_OFFERS_UNAVAILABLE
            ),
        )
    )
    repeat = decide_safe_degradation(
        bound_request(
            request=first_request,
            availability_aggregate=(
                AvailabilityAggregate.NOT_ALL_PRIMARY_OFFERS_UNAVAILABLE
            ),
        )
    )
    all_unavailable = decide_safe_degradation(
        bound_request(
            request=first_request,
            availability_aggregate=(
                AvailabilityAggregate.ALL_PRIMARY_OFFERS_UNAVAILABLE
            ),
        )
    )
    assert first == repeat
    assert first.fingerprint == repeat.fingerprint
    assert first.fingerprint != all_unavailable.fingerprint
    assert first.request_fingerprint != all_unavailable.request_fingerprint


def test_public_shapes_have_no_value_copy_url_html_or_payload_field() -> None:
    field_names = {
        item.name
        for value_type in (
            type(bound_request().freshness),
            type(bound_request()),
            type(decide_safe_degradation(bound_request())),
        )
        for item in fields(value_type)
    }
    assert {
        "price",
        "price_jpy",
        "stock",
        "availability",
        "url",
        "href",
        "link",
        "notice_copy",
        "copy",
        "html",
        "dom",
        "payload",
        "article_body",
    }.isdisjoint(field_names)
