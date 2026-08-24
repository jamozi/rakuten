from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts import build_st1801_portfolio_expansion as builder


def test_contract_is_closed_and_safe(contract: dict[str, object]) -> None:
    assert tuple(contract) == tuple(builder._expected_contract_sections())
    assert contract["document"] == builder._expected_contract_sections()["document"]
    policy = contract["portfolio_policy"]
    assert isinstance(policy, dict)
    assert policy["selected_placeholder_slot_count"] == 30
    assert policy["minimum_slot_count"] == 30
    assert policy["maximum_slot_count"] == 45
    assert policy["program"] == "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
    assert policy["category"]["actual_category"] == "UNAVAILABLE"  # type: ignore[index]
    assert policy["selection_inputs_excluded"] == [
        "AFFILIATE_COMMISSION_RATE",
        "EPC",
        "RPM",
        "REWARD",
        "COST",
        "PROFIT",
    ]


def test_fixture_schema_closes_every_object() -> None:
    schema = json.loads((builder.REPO_ROOT / builder.FIXTURE_SCHEMA_PATH).read_text())
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["case"]["additionalProperties"] is False
    assert (
        schema["$defs"]["case"]["properties"]["input"]["additionalProperties"] is False
    )
    assert (
        schema["$defs"]["case"]["properties"]["expected"]["additionalProperties"]
        is False
    )


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


def test_contract_yaml_has_no_alias_or_dynamic_evidence_path() -> None:
    raw = (builder.REPO_ROOT / builder.CONTRACT_PATH).read_text()
    parsed = yaml.safe_load(raw)
    assert "current_input" not in raw
    assert parsed["recorded_synthetic_harness"]["dynamic_input_path"] == "FORBIDDEN"
    assert parsed["decision"]["qualifying_evidence_references"] == []
    assert parsed["decision"]["actual_observations"] == []


def test_owned_paths_are_story_scoped() -> None:
    assert all(
        path.parts[:2] == ("changes", "st-1801") for path in builder.SOURCE_PATHS[:5]
    )
    assert builder.GENERATOR_PATH == Path("scripts/build_st1801_portfolio_expansion.py")
    assert all(path.parts[:2] == ("tests", "st1801") for path in builder.TEST_PATHS)
