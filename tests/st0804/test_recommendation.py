"""Canonical recommendation calculations and explanation tests for ST-0804."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json

import pytest

from .support import recommendation_input, valid_recommendation_input
from raos.domain.editorial.recommendation import (
    CandidateEligibility,
    CandidateRecommendation,
    CandidateReasonCode,
    ConflictState,
    ExecutionStatus,
    HardConstraintState,
    RankingState,
    RecommendationDecision,
    RecommendationReport,
    StalenessState,
    generate_recommendations,
)


def _candidate(
    report: RecommendationReport,
    product_id: str,
) -> CandidateRecommendation:
    return next(
        candidate
        for candidate in report.candidates
        if candidate.product_id.value == product_id
    )


def test_all_hard_constraints_pass_and_one_failure_is_ineligible() -> None:
    passing = generate_recommendations(valid_recommendation_input())
    failing_input = recommendation_input(
        (
            (Decimal("0.90"), Decimal("0.80")),
            (Decimal("0.88"), Decimal("0.80")),
        ),
        hard_states={(0, 0): HardConstraintState.FAIL},
    )
    failing = generate_recommendations(failing_input)

    assert passing.decision is RecommendationDecision.PASS
    assert all(
        candidate.eligibility is CandidateEligibility.ELIGIBLE
        for candidate in passing.candidates
    )
    blocked_candidate = _candidate(failing, "PRODUCT_01")
    assert blocked_candidate.eligibility is CandidateEligibility.INELIGIBLE
    assert blocked_candidate.ranking_state is RankingState.INELIGIBLE
    assert CandidateReasonCode.HARD_CONSTRAINT_FAILED in blocked_candidate.reason_codes
    assert blocked_candidate.base_score is None
    assert blocked_candidate.final_score is None
    assert blocked_candidate.rank_group is None
    assert tuple(product.value for product in failing.ranking_order) == ("PRODUCT_02",)


def test_unknown_hard_constraint_and_nonhard_critical_unknown_never_rank() -> None:
    unknown_hard = generate_recommendations(
        recommendation_input(
            (
                (None, Decimal("0.80")),
                (Decimal("0.88"), Decimal("0.80")),
            )
        )
    )
    unknown_critical = generate_recommendations(
        recommendation_input(
            (
                (None, Decimal("0.80")),
                (Decimal("0.88"), Decimal("0.80")),
            ),
            hard_axes=frozenset(),
            critical_axes=frozenset({0}),
        )
    )

    hard_candidate = _candidate(unknown_hard, "PRODUCT_01")
    assert hard_candidate.eligibility is CandidateEligibility.INELIGIBLE
    assert CandidateReasonCode.HARD_CONSTRAINT_UNKNOWN in hard_candidate.reason_codes
    critical_candidate = _candidate(unknown_critical, "PRODUCT_01")
    assert critical_candidate.eligibility is CandidateEligibility.ELIGIBLE
    assert critical_candidate.ranking_state is RankingState.UNRANKED_CRITICAL_EVIDENCE
    assert (
        CandidateReasonCode.CRITICAL_EVIDENCE_UNKNOWN in critical_candidate.reason_codes
    )
    assert critical_candidate.final_score is None


def test_stale_critical_fact_is_ineligible_until_refresh() -> None:
    report = generate_recommendations(
        recommendation_input(
            (
                (Decimal("0.90"), Decimal("0.80")),
                (Decimal("0.88"), Decimal("0.80")),
            ),
            staleness={(0, 0): (StalenessState.STALE, Decimal("2"))},
        )
    )

    stale_candidate = _candidate(report, "PRODUCT_01")
    assert stale_candidate.eligibility is CandidateEligibility.INELIGIBLE
    assert stale_candidate.ranking_state is RankingState.INELIGIBLE
    assert CandidateReasonCode.CRITICAL_EVIDENCE_STALE in stale_candidate.reason_codes
    assert stale_candidate.base_score is None
    assert stale_candidate.final_score is None
    assert stale_candidate.rank_group is None


@pytest.mark.parametrize(
    ("current_weight", "missing_weight", "expected_state", "primary_allowed"),
    [
        (
            Decimal("0.79"),
            Decimal("0.21"),
            RankingState.UNRANKED_LOW_COVERAGE,
            False,
        ),
        (Decimal("0.80"), Decimal("0.20"), RankingState.RANKED, False),
        (Decimal("0.90"), Decimal("0.10"), RankingState.RANKED, True),
    ],
)
def test_weighted_coverage_thresholds_are_inclusive_at_080_and_090(
    current_weight: Decimal,
    missing_weight: Decimal,
    expected_state: RankingState,
    primary_allowed: bool,
) -> None:
    report = generate_recommendations(
        recommendation_input(
            (
                (Decimal("0.90"), None),
                (Decimal("0.80"), Decimal("0.80")),
            ),
            weights=(current_weight, missing_weight),
        )
    )

    selected = _candidate(report, "PRODUCT_01")
    assert selected.weighted_evidence_coverage == current_weight.quantize(
        Decimal("0.0001")
    )
    assert selected.ranking_state is expected_state
    assert selected.primary_recommendation_allowed is primary_allowed
    assert tuple(axis.value for axis in selected.unknown_axis_ids) == ("AXIS_02",)
    if expected_state is RankingState.UNRANKED_LOW_COVERAGE:
        assert (
            CandidateReasonCode.COVERAGE_BELOW_RANK_THRESHOLD in selected.reason_codes
        )
        assert selected.rank_group is None


def test_weights_are_normalized_by_total_deterministically() -> None:
    scores = (
        (Decimal("0.80"), Decimal("0.20")),
        (Decimal("0.60"), Decimal("0.40")),
    )
    first = generate_recommendations(
        recommendation_input(
            scores,
            weights=(Decimal("0.25"), Decimal("0.75")),
        )
    )
    scaled = generate_recommendations(
        recommendation_input(
            scores,
            weights=(Decimal("0.125"), Decimal("0.375")),
        )
    )

    first_candidate = _candidate(first, "PRODUCT_01")
    scaled_candidate = _candidate(scaled, "PRODUCT_01")
    assert first_candidate.base_score == Decimal("35.0000")
    assert scaled_candidate.base_score == Decimal("35.0000")
    assert first_candidate.final_score == scaled_candidate.final_score
    assert first.explanation_sha256 != scaled.explanation_sha256


def test_conflict_and_staleness_penalties_apply_formula_cap_and_clamp() -> None:
    report = generate_recommendations(
        recommendation_input(
            (
                (Decimal("0.10"), Decimal("0.10")),
                (Decimal("0.80"), Decimal("0.80")),
            ),
            weights=(Decimal("0.80"), Decimal("0.20")),
            conflicts={(0, 1): (ConflictState.CONFLICTING, Decimal("12"))},
            staleness={(0, 1): (StalenessState.STALE, Decimal("12"))},
        )
    )

    selected = _candidate(report, "PRODUCT_01")
    assert selected.weighted_evidence_coverage == Decimal("0.8000")
    assert selected.base_score == Decimal("10.0000")
    assert selected.conflict_penalty == Decimal("12.0000")
    assert selected.staleness_penalty == Decimal("12.0000")
    assert selected.uncertainty_penalty == Decimal("20.0000")
    assert selected.final_score == Decimal("0.0000")
    assert selected.public_score == 0
    assert tuple(axis.value for axis in selected.conflicting_axis_ids) == ("AXIS_02",)
    assert tuple(axis.value for axis in selected.stale_axis_ids) == ("AXIS_02",)


def test_near_expiry_is_current_for_coverage_but_requires_and_applies_penalty() -> None:
    report = generate_recommendations(
        recommendation_input(
            (
                (Decimal("0.90"), Decimal("0.80")),
                (Decimal("0.80"), Decimal("0.80")),
            ),
            staleness={(0, 1): (StalenessState.NEAR_EXPIRY, Decimal("3"))},
        )
    )

    selected = _candidate(report, "PRODUCT_01")
    assert selected.weighted_evidence_coverage == Decimal("1.0000")
    assert selected.base_score == Decimal("85.0000")
    assert selected.uncertainty_penalty == Decimal("3.0000")
    assert selected.final_score == Decimal("82.0000")


def test_tie_at_two_points_co_recommends_with_product_id_stable_order() -> None:
    report = generate_recommendations(
        recommendation_input(
            (
                (Decimal("0.88"),),
                (Decimal("0.90"),),
                (Decimal("0.70"),),
            )
        )
    )

    first = _candidate(report, "PRODUCT_01")
    second = _candidate(report, "PRODUCT_02")
    assert first.final_score == Decimal("88.0000")
    assert second.final_score == Decimal("90.0000")
    assert first.rank_group == second.rank_group == 1
    assert first.group_anchor_score == second.group_anchor_score == Decimal("90.0000")
    assert first.co_recommended is second.co_recommended is True
    assert first.strict_order_allowed is second.strict_order_allowed is False
    assert tuple(product.value for product in report.ranking_order[:2]) == (
        "PRODUCT_01",
        "PRODUCT_02",
    )


def test_tie_groups_use_highest_score_anchor_and_two_point_zero_one_separates() -> None:
    report = generate_recommendations(
        recommendation_input(
            (
                (Decimal("0.9000"),),
                (Decimal("0.8800"),),
                (Decimal("0.8799"),),
            )
        )
    )

    product_1 = _candidate(report, "PRODUCT_01")
    product_2 = _candidate(report, "PRODUCT_02")
    product_3 = _candidate(report, "PRODUCT_03")
    assert product_1.rank_group == product_2.rank_group == 1
    assert product_3.rank_group == 2
    assert product_3.group_anchor_score == Decimal("87.9900")
    assert product_3.strict_order_allowed is True


def test_internal_four_decimal_and_public_half_even_integer_are_explicit() -> None:
    report = generate_recommendations(
        recommendation_input(
            (
                (Decimal("0.845"),),
                (Decimal("0.855"),),
            )
        )
    )

    lower = _candidate(report, "PRODUCT_01")
    upper = _candidate(report, "PRODUCT_02")
    assert lower.final_score == Decimal("84.5000")
    assert upper.final_score == Decimal("85.5000")
    assert lower.public_score == 84
    assert upper.public_score == 86


def test_explanation_is_canonical_hash_bound_and_never_authorizes_use() -> None:
    report = generate_recommendations(valid_recommendation_input())

    assert report.decision is RecommendationDecision.PASS
    assert report.findings == ()
    assert report.explanation_json is not None
    assert (
        report.explanation_sha256
        == hashlib.sha256(report.explanation_json.encode("utf-8")).hexdigest()
    )
    assert report.explanation_json == json.dumps(
        json.loads(report.explanation_json),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload = json.loads(report.explanation_json)
    assert payload["comparison_sha256"] == report.comparison_sha256
    assert payload["engine_contract"]["internal_precision"] == "0.0001"
    assert payload["engine_contract"]["tie_anchor"] == "HIGHEST_SCORE_IN_GROUP"
    assert payload["methodology"]["methodology_id"] == "RAOS-CONTENT-RECO-001"
    assert payload["status"] == {
        "formal_test": "NOT_EXECUTED",
        "live_validation": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
    }
    assert report.publication_authorized is False
    assert report.production_eligible is False
    assert report.formal_test_status is ExecutionStatus.NOT_EXECUTED
    assert report.live_validation_status is ExecutionStatus.NOT_EXECUTED
    assert report.staging_status is ExecutionStatus.NOT_EXECUTED
    assert report.release_status is ExecutionStatus.NOT_EXECUTED
    assert report.production_status is ExecutionStatus.NOT_EXECUTED
