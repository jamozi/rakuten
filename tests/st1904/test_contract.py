"""Canonical, dependency, and contract bindings for ST-1904."""

from __future__ import annotations

import json
from typing import Any, cast

import yaml

from scripts import build_st1904_multi_category as generator


def _contract() -> dict[str, Any]:
    loaded = yaml.safe_load(
        (generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes()
    )
    assert type(loaded) is dict
    return cast(dict[str, Any], loaded)


def test_document_preserves_deferred_status_and_no_authority() -> None:
    assert _contract()["document"] == {
        "schema_version": "1.0.0",
        "story_id": "ST-1904",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_MULTI_CATEGORY_CONTRACT_V1"
        ),
        "status": "LOCAL_CODE_COMPLETE_MAX_SAFE_DISABLED",
        "mvp": False,
        "canonical_implementation_status": "DEFERRED_POST_MVP",
        "canonical_status_changed": False,
        "formal_validation": "NOT_EXECUTED",
        "authority": "NONE",
        "production_eligible": False,
    }


def test_authority_story_suite_and_open_decisions_are_current() -> None:
    authority = _contract()["authority"]
    for row in authority.values():
        if isinstance(row, dict) and "path" in row:
            path = generator.REPO_ROOT / row["path"]
            assert generator.sha256_bytes(path.read_bytes()) == row["sha256"]
    backlog = yaml.safe_load(
        (generator.REPO_ROOT / authority["canonical_story"]["path"]).read_bytes()
    )
    story = next(row for row in backlog["stories"] if row["id"] == "ST-1904")
    assert story["depends_on"] == ["ST-1805"]
    assert story["implementation_status"] == "DEFERRED_POST_MVP"
    assert story["test_suites"] == ["TST-032"]
    assert story["acceptance_criteria"] == ["separate release decision required"]
    decisions = yaml.safe_load(
        (generator.REPO_ROOT / authority["open_decisions"]["path"]).read_bytes()
    )
    by_id = {row["id"]: row for row in decisions["items"]}
    assert by_id["OD-001"]["status"] == "HUMAN_DECISION_REQUIRED"
    assert by_id["OD-006"]["status"] == "EXTERNAL_EVIDENCE_REQUIRED"
    assert by_id["OD-007"]["status"] == "HUMAN_DECISION_REQUIRED"
    assert all(
        by_id[identifier]["blocking"] for identifier in ("OD-001", "OD-006", "OD-007")
    )
    suite_catalog = yaml.safe_load(
        (generator.REPO_ROOT / authority["test_catalog"]["path"]).read_bytes()
    )
    suite = next(row for row in suite_catalog["suites"] if row["id"] == "TST-032")
    assert suite["environments"] == ["staging"]
    assert suite["owner"] == "Product Owner"
    assert suite["execution_status"] == "NOT_EXECUTED"


def test_predecessor_is_semantic_blocked_st1805_no_decision() -> None:
    predecessor = _contract()["predecessor"]
    assert predecessor["story_id"] == "ST-1805"
    assert all(
        (generator.REPO_ROOT / path).is_file() for path in predecessor["artifacts"]
    )
    report = json.loads(
        (
            generator.REPO_ROOT
            / "changes/st-1805/generated/portfolio-decision.local-blocked.v1.json"
        ).read_bytes()
    )
    assert report["overall"] == "BLOCKED"
    assert report["acceptance_criteria_satisfied"] is False
    assert report["actual_observations"] == []
    assert report["decision"]["outcome"] == "NO_DECISION"
    assert report["decision"]["authorized"] is False
    assert report["authority"]["category_change"] == "NONE"


def test_dependencies_are_semantic_and_keep_safe_semantics() -> None:
    dependencies = _contract()["dependency_contracts"]
    for row in dependencies.values():
        path = generator.REPO_ROOT / row["path"]
        assert path.is_file()
    runtime = json.loads(
        (
            generator.REPO_ROOT / dependencies["st1702_recorded_fixture"]["path"]
        ).read_bytes()
    )
    assert runtime["dataClass"] == "SYNTHETIC_VALIDATOR_FIXTURE_ONLY"
    assert runtime["category"]["candidateApplied"] is False
    assert runtime["identityPolicy"]["automaticMergeEnabled"] is False
    assert runtime["identityPolicy"]["automaticSplitEnabled"] is False
    assert runtime["identityPolicy"]["humanReviewRequired"] is True
    assert runtime["freshnessPolicy"]["categoryOverrides"] == []
    assert runtime["freshnessPolicy"]["providerOverrides"] == []
    assert runtime["freshnessPolicy"]["recommendationAutoReorder"] == "FORBIDDEN"
    assert all(
        value is False
        for value in runtime["authority"].values()
        if isinstance(value, bool)
    )


def test_contract_closes_category_activation_and_mutation_boundaries() -> None:
    contract = _contract()
    scope = contract["feature_scope"]
    assert scope["default"] == "DISABLED"
    assert scope["closed_states"] == [
        "DISABLED",
        "RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY",
    ]
    assert scope["executable_environments"] == ["ENV-DEV", "ENV-CI"]
    assert scope["live_enabled_state_exists"] is False
    assert scope["category_activation_state_exists"] is False
    assert scope["template_activation_state_exists"] is False
    assert scope["release_interface_exists"] is False
    category = contract["multi_category_contract"]
    assert category["real_category_selected"] is False
    assert category["identity_disposition"] == "HUMAN_REVIEW_REQUIRED"
    assert category["automatic_merge_enabled"] is False
    assert category["automatic_split_enabled"] is False
    assert category["category_override"] is None
    assert category["provider_override"] is None
    assert category["recommendation_auto_reorder"] == "FORBIDDEN"
    assert category["template_active"] is False
    for field in (
        "provider_call",
        "network",
        "category_selection",
        "category_activation",
        "identity_decision",
        "freshness_override",
        "template_activation",
        "editorial_mutation",
        "article_html_mutation",
        "cta_mutation",
        "product_selection_mutation",
        "recommendation_order_mutation",
        "publication_snapshot_mutation",
        "publication",
        "status_apply",
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
    assert len(parsed["categories"]) == 2
    assert all(category["synthetic"] is True for category in parsed["categories"])
    assert all(
        category["real_category_selected"] is False for category in parsed["categories"]
    )
    assert all(
        category["template"]["active"] is False for category in parsed["categories"]
    )
    assert all(value is False for value in parsed["authority"].values())
    serialized = content.decode("ascii").lower()
    for prohibited in (
        "api_key",
        "commission",
        "endpoint",
        "epc",
        "https://",
        "password",
        "profit",
        "provider_id",
        "review_body",
        "rpm",
        "secret://",
    ):
        assert prohibited not in serialized
