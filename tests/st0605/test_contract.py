from __future__ import annotations

from typing import Any

import pytest

from scripts import build_st0605_claim_evidence_coverage_reference_plan as generator


EXPECTED_CASE_IDS = [f"CT-{number:04d}" for number in range(389, 551)]
EXPECTED_RESULT_COUNTS = {
    "PASS": 36,
    "FAIL": 63,
    "FAIL_BLOCKER": 54,
    "FAIL_OR_DEGRADE": 9,
}


def test_authored_contract_has_exact_closed_sections(contract: dict[str, Any]) -> None:
    assert tuple(contract) == generator.CONTRACT_KEYS
    assert contract["schema_version"] == 1
    assert contract["story_id"] == "ST-0605"
    assert contract["classification"] == (
        "SOURCE_DERIVED_NONEXECUTABLE_CLAIM_EVIDENCE_COVERAGE_REFERENCE_PLAN"
    )


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    ("field", "expected"),
    [
        ("status", "LOCAL_IMPLEMENTATION_CANDIDATE"),
        ("executable", False),
        ("interface_only", True),
        ("decision", "NOT_READY"),
        ("production_eligible", False),
        ("approval", False),
        ("story_acceptance", False),
        ("publication_permitted", False),
    ],
)
def test_authored_document_remains_partial_and_non_executable(
    contract: dict[str, Any], field: str, expected: object
) -> None:
    assert type(contract[field]) is type(expected)
    assert contract[field] == expected


def test_authority_and_policy_describe_but_do_not_supply_mapping(
    contract: dict[str, Any],
) -> None:
    assert contract["authority"] == generator.EXPECTED_AUTHORITY
    vocabulary = contract["vocabulary_context"]
    assert vocabulary["authority"] == "DESCRIPTIVE_ONLY"
    assert vocabulary["creates_runtime_contract"] is False
    assert vocabulary["inferred_mappings"] == []
    matrix = contract["coverage_policy"]["matrix"]
    assert matrix["semantics"] == "CANONICAL_EXPECTED_OUTCOMES_ONLY"
    assert matrix["mapping_authority"] == "UNAVAILABLE"
    assert matrix["executable"] is False
    assert matrix["row_count"] == 162
    assert matrix["expected_outcome_counts"] == EXPECTED_RESULT_COUNTS


def test_predecessors_preserve_empty_unready_inputs(contract: dict[str, Any]) -> None:
    predecessors = contract["predecessors"]
    assert [row["story_id"] for row in predecessors] == [
        "ST-0602",
        "ST-0603",
        "ST-0604",
    ]
    assert [row["required_semantics"]["decision"] for row in predecessors] == [
        "NOT_READY",
        "NOT_READY",
        "NOT_READY",
    ]
    assert predecessors[0]["required_semantics"]["facts"] == []
    assert predecessors[0]["required_semantics"]["fact_count"] is None
    assert predecessors[1]["required_semantics"]["conflicts"] == []
    assert predecessors[1]["required_semantics"]["conflict_count"] is None
    assert predecessors[2]["required_semantics"]["packets"] == []
    assert predecessors[2]["required_semantics"]["packet_count"] is None
    assert predecessors[2]["required_semantics"]["approval"] is False
    assert predecessors[2]["required_semantics"]["generation_permitted"] is False


def test_all_runtime_selections_are_unset(contract: dict[str, Any]) -> None:
    assert contract["selection_defaults"] == generator.EXPECTED_SELECTIONS
    assert all(value is None for value in contract["selection_defaults"].values())


def test_collections_are_empty_with_unknown_counts(contract: dict[str, Any]) -> None:
    collections = contract["collection_defaults"]
    assert collections == generator.EXPECTED_COLLECTIONS
    for name in ("claims", "facts", "links", "sources", "citations", "conflicts"):
        assert collections[name] == []
    for name, value in collections.items():
        if name.endswith("_count"):
            assert value is None


def test_coverage_is_unevaluable_not_vacuously_satisfied(
    contract: dict[str, Any],
) -> None:
    coverage = contract["coverage_defaults"]
    assert coverage == generator.EXPECTED_COVERAGE_DEFAULTS
    assert coverage["coverage_status"] == "UNEVALUABLE"
    assert coverage["coverage_evaluable"] is False
    assert coverage["major_claim_evidence_coverage_ratio"] is None
    assert coverage["all_verifiable_claim_evidence_coverage_ratio"] is None
    assert coverage["major_claim_requirement_satisfied"] is None
    assert coverage["all_verifiable_claim_requirement_satisfied"] is None
    assert coverage["zero_denominator_outcome"] == "UNEVALUABLE"
    assert coverage["vacuous_zero_over_zero_pass_forbidden"] is True
    assert coverage["publication_permitted"] is False
    assert coverage["blockers"] == generator.EXPECTED_BLOCKERS


def test_execution_and_formal_verification_remain_unexecuted(
    contract: dict[str, Any],
) -> None:
    execution = contract["execution_boundary"]
    assert execution == generator.EXPECTED_EXECUTION
    assert tuple(execution["action_counts"]) == generator.ACTION_COUNT_KEYS
    assert all(
        type(value) is int and value == 0
        for value in execution["action_counts"].values()
    )
    assert all(
        status == "NOT_EXECUTED"
        for name, status in execution.items()
        if name != "action_counts"
    )
    assert contract["verification_boundary"] == generator.EXPECTED_VERIFICATION
    assert all(
        status == "NOT_EXECUTED"
        for status in contract["verification_boundary"].values()
    )
