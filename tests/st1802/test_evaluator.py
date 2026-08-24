from __future__ import annotations

import copy

import pytest

from scripts import build_st1802_gate1_decision as builder


def _pass_input() -> dict[str, object]:
    fixture = builder._load_json(builder.REPO_ROOT, builder.FIXTURE_PATH, "fixture")
    cases = fixture["cases"]
    assert isinstance(cases, list)
    value = cases[0]["input"]
    assert isinstance(value, dict)
    return copy.deepcopy(value)


def _statuses(result: dict[str, object]) -> dict[str, str]:
    rows = result["criterion_results"]
    assert isinstance(rows, list)
    return {row["criterion_id"]: row["status"] for row in rows}


def test_exact_thresholds_pass_without_authority() -> None:
    result = builder.evaluate_recorded_synthetic(_pass_input())
    assert result["overall_status"] == "PASS"
    assert result["classification"] == builder.SYNTHETIC_CLASSIFICATION
    assert result["formal_evidence_eligible"] is False
    assert result["gate_evidence_eligible"] is False
    assert result["story_acceptance_eligible"] is False
    assert result["article_approval_eligible"] is False
    assert result["publication_eligible"] is False


@pytest.mark.parametrize(
    ("field", "value", "criterion"),
    [
        ("category_count", 2, "SYN-G1-C01-SINGLE-CATEGORY"),
        ("intent_cluster_count", 2, "SYN-G1-C02-INTENT-CLUSTERS"),
        ("article_count", 46, "SYN-G1-C03-ARTICLE-COUNT"),
        ("article_type_count", 2, "SYN-G1-C04-ARTICLE-TYPES"),
        ("article_type_count", 6, "SYN-G1-C04-ARTICLE-TYPES"),
        ("minimum_quality_score", "84.999999", "SYN-G1-C05-ALL-QUALITY-85"),
        ("critical_factual_error_count", 1, "SYN-G1-C06-CRITICAL-FACTUAL-ERRORS"),
        ("evidenced_claim_count", 94, "SYN-G1-C07-ALL-CLAIM-COVERAGE"),
        ("evidenced_major_claim_count", 9, "SYN-G1-C08-MAJOR-CLAIM-COVERAGE"),
        ("fabricated_experience_count", 1, "SYN-G1-C09-FABRICATED-EXPERIENCE"),
        ("product_identity_error_count", 1, "SYN-G1-C10-PRODUCT-IDENTITY"),
        ("link_error_count", 1, "SYN-G1-C11-LINK-ERRORS"),
        ("first_pass_approved_count", 23, "SYN-G1-C12-FIRST-PASS-HUMAN-APPROVAL"),
        ("freshness_displayed_count", 29, "SYN-G1-C13-FRESHNESS-TIMESTAMPS"),
        ("measurement_connected", False, "SYN-G1-C14-MEASUREMENT-CONNECTED"),
        ("per_article_cost_measurable", False, "SYN-G1-C15-PER-ARTICLE-COST"),
        ("human_time_measurable", False, "SYN-G1-C16-HUMAN-TIME"),
        ("change_history_audit_verified", False, "SYN-G1-C17-CHANGE-HISTORY-AUDIT"),
        ("rollback_verified", False, "SYN-G1-C18-ROLLBACK"),
    ],
)
def test_known_threshold_failures(field: str, value: object, criterion: str) -> None:
    input_value = _pass_input()
    input_value[field] = value
    result = builder.evaluate_recorded_synthetic(input_value)
    assert result["overall_status"] == "FAIL"
    assert _statuses(result)[criterion] == "FAIL"


def test_article_count_below_minimum_fails_with_coherent_cohort_counts() -> None:
    input_value = _pass_input()
    input_value.update(
        {
            "article_count": 29,
            "quality_evaluated_article_count": 29,
            "quality_passing_article_count": 29,
            "human_reviewed_count": 29,
            "first_pass_approved_count": 29,
            "freshness_eligible_article_count": 29,
            "freshness_displayed_count": 29,
        }
    )
    result = builder.evaluate_recorded_synthetic(input_value)
    assert result["overall_status"] == "FAIL"
    assert _statuses(result)["SYN-G1-C03-ARTICLE-COUNT"] == "FAIL"


@pytest.mark.parametrize(
    "field",
    [
        "category_count",
        "intent_cluster_count",
        "article_count",
        "article_type_count",
        "minimum_quality_score",
        "critical_factual_error_count",
        "measurement_connected",
        "rollback_verified",
    ],
)
def test_missing_input_is_unavailable(field: str) -> None:
    input_value = _pass_input()
    input_value[field] = None
    result = builder.evaluate_recorded_synthetic(input_value)
    assert result["overall_status"] == "UNAVAILABLE"
    assert "UNAVAILABLE" in _statuses(result).values()


@pytest.mark.parametrize(
    ("numerator", "denominator"),
    [
        ("evidenced_claim_count", "verifiable_claim_count"),
        ("evidenced_major_claim_count", "major_claim_count"),
        ("first_pass_approved_count", "human_reviewed_count"),
        ("freshness_displayed_count", "freshness_eligible_article_count"),
    ],
)
def test_zero_denominator_is_unavailable(numerator: str, denominator: str) -> None:
    input_value = _pass_input()
    input_value[numerator] = 0
    input_value[denominator] = 0
    assert (
        builder.evaluate_recorded_synthetic(input_value)["overall_status"]
        == "UNAVAILABLE"
    )


@pytest.mark.parametrize(
    "denominator",
    [
        "verifiable_claim_count",
        "major_claim_count",
        "human_reviewed_count",
        "freshness_eligible_article_count",
    ],
)
def test_missing_denominator_is_unavailable(denominator: str) -> None:
    input_value = _pass_input()
    input_value[denominator] = None
    assert (
        builder.evaluate_recorded_synthetic(input_value)["overall_status"]
        == "UNAVAILABLE"
    )


@pytest.mark.parametrize(
    "score", [True, 85, "-1", "101", "NaN", "1e2", " 85", "85.0000000"]
)
def test_invalid_score_is_rejected(score: object) -> None:
    input_value = _pass_input()
    input_value["minimum_quality_score"] = score
    with pytest.raises(builder.Gate1DecisionError, match="INVALID_SCORE"):
        builder.evaluate_recorded_synthetic(input_value)


@pytest.mark.parametrize("value", [True, -1, 1_000_001, "1"])
def test_invalid_count_is_rejected(value: object) -> None:
    input_value = _pass_input()
    input_value["article_count"] = value
    with pytest.raises(builder.Gate1DecisionError, match="INVALID_COUNT"):
        builder.evaluate_recorded_synthetic(input_value)


def test_numerator_above_denominator_is_rejected() -> None:
    input_value = _pass_input()
    input_value["evidenced_claim_count"] = 101
    with pytest.raises(builder.Gate1DecisionError, match="INVALID_RATIO_COUNTS"):
        builder.evaluate_recorded_synthetic(input_value)


def test_inconsistent_quality_counts_are_rejected() -> None:
    input_value = _pass_input()
    input_value["quality_passing_article_count"] = 31
    with pytest.raises(builder.Gate1DecisionError, match="INVALID_QUALITY_COUNTS"):
        builder.evaluate_recorded_synthetic(input_value)


def test_recorded_fixture_matches_evaluator() -> None:
    results = builder._validate_fixture(builder.REPO_ROOT)
    assert len(results) == 4
    assert {row["overall_status"] for row in results} == {"PASS", "FAIL", "UNAVAILABLE"}
    assert all(row["gate_evidence_eligible"] is False for row in results)
