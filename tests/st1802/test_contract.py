from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts import build_st1802_gate1_decision as builder


def test_contract_is_closed_and_fail_closed(contract: dict[str, object]) -> None:
    builder._validate_contract_structure(contract)
    assert tuple(contract) == (
        "document",
        "source_bindings",
        "dependency_bindings",
        "gate_definition",
        "status_vocabulary",
        "mandatory_criteria",
        "recorded_synthetic_harness",
        "decision",
        "authority_boundary",
        "execution_boundary",
        "evidence_boundary",
    )
    assert contract["decision"] == {
        "overall": "BLOCKED",
        "eligibility": "NOT_ELIGIBLE",
        "mandatory_criteria_satisfied": False,
        "next_gate_eligible": False,
        "qualifying_evidence_references": [],
        "approval_artifacts": [],
    }


def test_gate_definition_matches_all_authoritative_thresholds(
    contract: dict[str, object],
) -> None:
    assert contract["gate_definition"] == builder.EXPECTED_GATE_DEFINITION
    definition = contract["gate_definition"]
    assert isinstance(definition, dict)
    assert definition["revenue_required"] is False
    assert definition["minimum_article_count"] == 30
    assert definition["maximum_article_count"] == 45
    assert definition["minimum_quality_score"] == "85"
    assert definition["zero_denominator"] == "UNAVAILABLE"


def test_mandatory_criteria_inventory_is_closed_and_complete(
    contract: dict[str, object],
) -> None:
    rows = contract["mandatory_criteria"]
    assert isinstance(rows, list)
    assert len(rows) == 25
    assert [row["criterion_id"] for row in rows] == [
        row[0] for row in builder._CRITERIA_ROWS
    ]
    assert all(row["status"] in builder.STATUS_VOCABULARY for row in rows)
    assert all(row["status"] != "PASS" for row in rows)


def test_authority_is_entirely_absent(contract: dict[str, object]) -> None:
    authority = contract["authority_boundary"]
    assert isinstance(authority, dict)
    assert authority
    assert set(authority.values()) == {"NONE"}


def test_exact_hash_bindings_match() -> None:
    for path, digest in {
        **builder.EXPECTED_SOURCE_HASHES,
        **builder.EXPECTED_DEPENDENCY_HASHES,
    }.items():
        assert builder._sha256((builder.REPO_ROOT / path).read_bytes()) == digest
    assert (
        builder._sha256((builder.REPO_ROOT / builder.FIXTURE_SCHEMA_PATH).read_bytes())
        == builder.FIXTURE_SCHEMA_SHA256
    )
    assert (
        builder._sha256((builder.REPO_ROOT / builder.FIXTURE_PATH).read_bytes())
        == builder.FIXTURE_SHA256
    )


def test_fixture_schema_closes_every_object() -> None:
    schema = json.loads(
        (builder.REPO_ROOT / builder.FIXTURE_SCHEMA_PATH).read_text(encoding="utf-8")
    )
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["input"]["additionalProperties"] is False
    assert schema["$defs"]["case"]["additionalProperties"] is False
    assert set(schema["$defs"]["input"]["required"]) == set(builder.INPUT_KEYS)


def test_recorded_fixture_conforms_to_closed_schema() -> None:
    schema = json.loads(
        (builder.REPO_ROOT / builder.FIXTURE_SCHEMA_PATH).read_text(encoding="utf-8")
    )
    fixture = json.loads(
        (builder.REPO_ROOT / builder.FIXTURE_PATH).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(fixture)


def test_owned_paths_are_story_scoped() -> None:
    assert builder.CONTRACT_PATH.parts[:2] == ("changes", "st-1802")
    assert builder.FIXTURE_PATH.parts[:2] == ("changes", "st-1802")
    assert builder.GENERATOR_PATH == Path("scripts/build_st1802_gate1_decision.py")
    assert all(path.parts[:2] == ("tests", "st1802") for path in builder.TEST_PATHS)
