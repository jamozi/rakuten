from __future__ import annotations

import copy

import pytest

from scripts import build_st1801_portfolio_expansion as builder


def _record() -> tuple[dict[str, object], dict[str, object]]:
    contract = dict(builder.load_contract())
    record = builder.portfolio_record(
        contract, builder._validate_fixture(builder.REPO_ROOT)
    )
    return contract, record


def test_plan_contains_30_synthetic_non_article_slots() -> None:
    contract, record = _record()
    builder.validate_portfolio_record(record, contract)
    portfolio = record["portfolio"]
    assert isinstance(portfolio, dict)
    slots = portfolio["planned_slots"]
    assert isinstance(slots, list)
    assert len(slots) == 30
    assert [slot["slot_number"] for slot in slots] == list(range(1, 31))
    assert len({slot["placeholder_slot_id"] for slot in slots}) == 30
    for slot in slots:
        assert slot["identity_classification"] == "SYNTHETIC_PLACEHOLDER_NOT_AN_ARTICLE"
        assert slot["creation_status"] == "NOT_CREATED"
        assert slot["approval_status"] == "NOT_APPROVED"
        assert slot["publication_status"] == "NOT_PUBLIC"
        assert slot["article_id"] is None
        assert slot["slug"] is None
        assert slot["url"] is None
        assert slot["schedule"] is None
        assert slot["quality_score"] == "UNAVAILABLE"
        assert slot["major_claim_coverage_percent"] == "UNAVAILABLE"
        assert slot["actual_observations"] == []
        assert slot["evidence_references"] == []


def test_plan_is_blocked_and_contains_no_actual_evidence() -> None:
    _, record = _record()
    assert record["decision"] == {
        "overall": "BLOCKED",
        "dependency_eligibility": "NOT_ELIGIBLE",
        "downstream_gate_1_eligible": False,
        "acceptance_criteria_satisfied": False,
        "qualifying_evidence_references": [],
        "actual_observations": [],
    }
    assert record["actual_observations"] == []
    assert record["qualifying_evidence_references"] == []
    portfolio = record["portfolio"]
    assert isinstance(portfolio, dict)
    for field in (
        "actual_materialized_article_count",
        "actual_approved_article_count",
        "actual_published_article_count",
    ):
        assert portfolio[field] == "UNAVAILABLE"


@pytest.mark.parametrize("count", [29, 46])
def test_count_29_or_46_is_rejected(count: int) -> None:
    contract, record = _record()
    slots = record["portfolio"]["planned_slots"]  # type: ignore[index]
    assert isinstance(slots, list)
    if count < len(slots):
        del slots[count:]
    else:
        slots.extend(copy.deepcopy(slots[-1]) for _ in range(count - len(slots)))
    with pytest.raises(builder.PortfolioExpansionError):
        builder.validate_portfolio_record(record, contract)


def test_duplicate_slot_is_rejected() -> None:
    contract, record = _record()
    slots = record["portfolio"]["planned_slots"]  # type: ignore[index]
    assert isinstance(slots, list)
    slots[1] = copy.deepcopy(slots[0])
    with pytest.raises(builder.PortfolioExpansionError):
        builder.validate_portfolio_record(record, contract)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("creation_status", "CREATED"),
        ("approval_status", "APPROVED"),
        ("publication_status", "PUBLIC"),
        ("quality_score", "95"),
        ("major_claim_coverage_percent", "100.000000"),
        ("article_id", "invented-article"),
        ("url", "https://example.invalid/invented"),
    ],
)
def test_fabricated_article_state_or_evidence_is_rejected(
    field: str, value: object
) -> None:
    contract, record = _record()
    record["portfolio"]["planned_slots"][0][field] = value  # type: ignore[index]
    with pytest.raises(builder.PortfolioExpansionError):
        builder.validate_portfolio_record(record, contract)


@pytest.mark.parametrize(
    ("field", "value"),
    [("planning_category_ref", "REAL_CATEGORY"), ("program", "OTHER_PROGRAM")],
)
def test_unknown_category_or_program_is_rejected(field: str, value: str) -> None:
    contract, record = _record()
    record["portfolio"][field] = value  # type: ignore[index]
    with pytest.raises(builder.PortfolioExpansionError):
        builder.validate_portfolio_record(record, contract)


def test_synthetic_pass_does_not_unblock_generated_plan() -> None:
    _, record = _record()
    harness = record["acceptance_evaluation"]["recorded_synthetic_harness"]  # type: ignore[index]
    assert any(result["status"] == "PASS" for result in harness["results"])
    assert harness["qualifies_as_article_evidence"] is False
    assert harness["qualifies_as_portfolio_evidence"] is False
    assert harness["qualifies_as_gate_evidence"] is False
    assert record["decision"]["overall"] == "BLOCKED"  # type: ignore[index]
