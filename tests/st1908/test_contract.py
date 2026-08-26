"""Canonical, dependency, and contract bindings for ST-1908."""

from __future__ import annotations

import json
from typing import Any, cast

import yaml

from scripts import build_st1908_fine_tuning_evaluation as generator


def _contract() -> dict[str, Any]:
    loaded = yaml.safe_load(
        (generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes()
    )
    assert type(loaded) is dict
    return cast(dict[str, Any], loaded)


def test_document_preserves_deferred_status_and_no_authority() -> None:
    assert _contract()["document"] == {
        "schema_version": "1.0.0",
        "story_id": "ST-1908",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_FINE_TUNING_EVALUATION_V1"
        ),
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "mvp": False,
        "canonical_implementation_status": "DEFERRED_POST_MVP",
        "canonical_status_changed": False,
        "formal_validation": "NOT_EXECUTED",
        "authority": "NONE",
        "production_eligible": False,
    }


def test_authority_story_suite_and_unresolved_decisions_are_current() -> None:
    authority = _contract()["authority"]
    for row in authority.values():
        if isinstance(row, dict) and "path" in row:
            path = generator.REPO_ROOT / row["path"]
            assert generator.sha256_bytes(path.read_bytes()) == row["sha256"]
    backlog = yaml.safe_load(
        (generator.REPO_ROOT / authority["canonical_story"]["path"]).read_bytes()
    )
    story = next(row for row in backlog["stories"] if row["id"] == "ST-1908")
    assert story["depends_on"] == ["ST-0707"]
    assert story["implementation_status"] == "DEFERRED_POST_MVP"
    assert story["test_suites"] == ["TST-032"]
    assert story["acceptance_criteria"] == ["separate release decision required"]
    decisions = yaml.safe_load(
        (generator.REPO_ROOT / authority["open_decisions"]["path"]).read_bytes()
    )
    by_id = {row["id"]: row for row in decisions["items"]}
    assert by_id["OD-005"]["status"] == "HUMAN_DECISION_REQUIRED"
    assert by_id["OD-014"]["status"] == "HUMAN_DECISION_REQUIRED"
    assert by_id["OD-015"]["status"] == "EXTERNAL_EVIDENCE_REQUIRED"
    suite_catalog = yaml.safe_load(
        (generator.REPO_ROOT / authority["test_catalog"]["path"]).read_bytes()
    )
    suite = next(row for row in suite_catalog["suites"] if row["id"] == "TST-032")
    assert suite["environments"] == ["staging"]
    assert suite["execution_status"] == "NOT_EXECUTED"


def test_predecessor_is_semantic_current_st0707_input() -> None:
    predecessor = _contract()["predecessor"]
    assert predecessor["story_id"] == "ST-0707"
    assert len(predecessor["artifacts"]) == 8
    assert all(
        (generator.REPO_ROOT / path).is_file() for path in predecessor["artifacts"]
    )
    semantics = predecessor["required_semantics"]
    assert semantics["recorded_synthetic_only"] is True
    assert semantics["synthetic_release_eligible"] is False
    assert semantics["human_label_status"] == "UNAVAILABLE"
    assert semantics["unavailable_numeric_coercion"] == "FORBIDDEN"
    assert semantics["release_authority"] == "NONE"


def test_contract_closes_training_cost_and_mutation_boundaries() -> None:
    contract = _contract()
    scope = contract["feature_scope"]
    assert scope["default"] == "DISABLED"
    assert scope["closed_states"] == [
        "DISABLED",
        "RECORDED_SYNTHETIC_EVALUATION_ONLY",
    ]
    assert scope["executable_environments"] == ["ENV-DEV", "ENV-CI"]
    assert scope["live_enabled_state_exists"] is False
    assert scope["training_state_exists"] is False
    assert scope["activation_interface_exists"] is False
    assert contract["evaluation_gate"]["actual_fine_tuning_executed"] is False
    assert contract["evaluation_gate"]["positive_release_outcome_exists"] is False
    assert contract["cost_gate"]["missing_or_unverified"] == "UNAVAILABLE"
    assert contract["cost_gate"]["missing_to_zero_coercion"] == "FORBIDDEN"
    assert contract["cost_gate"]["affiliate_reward_or_rate_present"] is False
    assert contract["cost_gate"]["recommendation_input"] is False
    for field in (
        "provider_call",
        "training_job",
        "network",
        "credentials",
        "dataset_write",
        "prompt_mutation",
        "route_or_model_mutation",
        "editorial_mutation",
        "article_html_mutation",
        "cta_mutation",
        "product_selection_mutation",
        "recommendation_order_mutation",
        "publication_snapshot_mutation",
        "publication",
    ):
        assert contract["mutation_boundary"][field] == "FORBIDDEN"
    assert contract["debt"]["introduced"] == []


def test_fixture_is_canonical_synthetic_metadata_only() -> None:
    fixture = _contract()["recorded_fixture"]
    content = (generator.REPO_ROOT / fixture["path"]).read_bytes()
    assert len(content) == fixture["bytes"]
    assert generator.sha256_bytes(content) == fixture["sha256"]
    parsed = json.loads(content)
    assert content == generator._canonical_output(parsed)  # noqa: SLF001
    assert parsed["document"]["synthetic"] is True
    assert parsed["document"]["actual_training_executed"] is False
    assert parsed["dataset"]["rights_status"] == "UNAVAILABLE"
    assert parsed["dataset"]["governance_status"] == "UNAVAILABLE"
    assert parsed["dataset"]["representative"] is False
    assert parsed["dataset"]["release_eligible"] is False
    assert parsed["baseline"]["status"] == "UNAVAILABLE"
    assert parsed["candidate"]["status"] == "UNAVAILABLE"
    assert parsed["cost"]["status"] == "UNAVAILABLE"
    serialized = content.decode("ascii").lower()
    for prohibited in (
        "api_key",
        "commission",
        "endpoint",
        "epc",
        "https://",
        "password",
        "profit",
        "raw_prompt",
        "raw_response",
        'review_body"',
        "rpm",
        "secret://",
        "training_examples",
    ):
        assert prohibited not in serialized
