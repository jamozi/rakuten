from __future__ import annotations

import pytest

from scripts import build_st1801_portfolio_expansion as builder


def test_exact_quality_and_coverage_boundary_passes_without_authority() -> None:
    result = builder.evaluate_recorded_synthetic("85", 4, 4)
    assert result["status"] == "PASS"
    assert result["quality_status"] == "PASS"
    assert result["major_claim_coverage_status"] == "PASS"
    assert result["major_claim_coverage_percent"] == "100.000000"
    assert result["formal_evidence_eligible"] is False
    assert result["article_approval_eligible"] is False
    assert result["story_acceptance_eligible"] is False


@pytest.mark.parametrize("score", ["84.999999", "0", "1.5"])
def test_quality_below_85_fails(score: str) -> None:
    result = builder.evaluate_recorded_synthetic(score, 1, 1)
    assert result["status"] == "FAIL"
    assert result["quality_status"] == "FAIL"


def test_major_claim_coverage_below_100_fails() -> None:
    result = builder.evaluate_recorded_synthetic("100", 4, 3)
    assert result["status"] == "FAIL"
    assert result["major_claim_coverage_status"] == "FAIL"
    assert result["major_claim_coverage_percent"] == "75.000000"


@pytest.mark.parametrize(
    ("score", "total", "evidenced", "missing_axis"),
    [
        (None, 1, 1, "quality_status"),
        ("85", None, None, "major_claim_coverage_status"),
        ("85", 2, None, "major_claim_coverage_status"),
        ("85", 0, 0, "major_claim_coverage_status"),
    ],
)
def test_missing_or_zero_denominator_is_unavailable(
    score: object, total: object, evidenced: object, missing_axis: str
) -> None:
    result = builder.evaluate_recorded_synthetic(score, total, evidenced)
    assert result["status"] == "UNAVAILABLE"
    assert result[missing_axis] == "UNAVAILABLE"


@pytest.mark.parametrize(
    "score", [True, 85, "85.0000000", "-1", "101", "NaN", "1e2", " 85"]
)
def test_invalid_quality_values_are_rejected(score: object) -> None:
    with pytest.raises(builder.PortfolioExpansionError, match="INVALID_QUALITY_SCORE"):
        builder.evaluate_recorded_synthetic(score, 1, 1)


@pytest.mark.parametrize(
    ("total", "evidenced"),
    [(True, 1), (1, False), (-1, 0), (1, -1), (1, 2), (1_000_001, 1)],
)
def test_invalid_claim_counts_are_rejected(total: object, evidenced: object) -> None:
    with pytest.raises(builder.PortfolioExpansionError, match="INVALID_CLAIM_COUNT"):
        builder.evaluate_recorded_synthetic("85", total, evidenced)


def test_recorded_fixture_matches_pure_evaluator() -> None:
    results = builder._validate_fixture(builder.REPO_ROOT)
    assert len(results) == 7
    assert {result["status"] for result in results} == {"PASS", "FAIL", "UNAVAILABLE"}
    assert all(result["formal_evidence_eligible"] is False for result in results)
