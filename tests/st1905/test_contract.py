"""Contract, authority, and dependency bindings for ST-1905."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml

from scripts import build_st1905_advanced_rank_provider as generator


def _contract() -> dict[str, Any]:
    loaded = yaml.safe_load(
        (generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes()
    )
    assert type(loaded) is dict
    return cast(dict[str, Any], loaded)


def test_document_preserves_deferred_status_and_no_authority() -> None:
    document = _contract()["document"]
    assert document == {
        "schema_version": "1.0.0",
        "story_id": "ST-1905",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_ADVANCED_RANK_PROVIDER_V1"
        ),
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "mvp": False,
        "canonical_implementation_status": "DEFERRED_POST_MVP",
        "canonical_status_changed": False,
        "formal_validation": "NOT_EXECUTED",
        "authority": "NONE",
        "production_eligible": False,
    }


def test_authority_hashes_story_decision_and_suite_are_current() -> None:
    authority = _contract()["authority"]
    assert isinstance(authority, dict)
    for row in authority.values():
        assert isinstance(row, dict)
        path = generator.REPO_ROOT / str(row["path"])
        assert generator.sha256_bytes(path.read_bytes()) == row["sha256"]

    backlog = yaml.safe_load(
        (generator.REPO_ROOT / authority["canonical_story"]["path"]).read_bytes()
    )
    story = next(row for row in backlog["stories"] if row["id"] == "ST-1905")
    assert story["depends_on"] == ["ST-1206"]
    assert story["test_suites"] == ["TST-032"]
    assert story["implementation_status"] == "DEFERRED_POST_MVP"
    assert story["acceptance_criteria"] == ["separate release decision required"]

    decisions = yaml.safe_load(
        (generator.REPO_ROOT / authority["open_decisions"]["path"]).read_bytes()
    )
    decision = next(row for row in decisions["items"] if row["id"] == "OD-004")
    assert decision["status"] == "HUMAN_DECISION_REQUIRED"
    assert decision["default_behavior"] == "Search Consoleと手動CSVのみ"

    catalog = yaml.safe_load(
        (generator.REPO_ROOT / authority["test_catalog"]["path"]).read_bytes()
    )
    suite = next(row for row in catalog["suites"] if row["id"] == "TST-032")
    assert suite["release_blocking"] is True
    assert suite["execution_status"] == "NOT_EXECUTED"
    assert suite["environments"] == ["staging"]


def test_predecessor_is_semantic_st1206_input() -> None:
    predecessor = _contract()["predecessor"]
    assert predecessor["story_id"] == "ST-1206"
    assert len(predecessor["artifacts"]) == 8
    assert all(
        (generator.REPO_ROOT / relative).is_file()
        for relative in predecessor["artifacts"]
    )
    semantics = predecessor["required_semantics"]
    assert semantics["default_scope"] == "DISABLED"
    assert semantics["live_provider_rows"] is False
    assert semantics["serp_scrape"] == "FORBIDDEN"
    assert semantics["recommendation_input"] == "DISABLED"
    assert semantics["formal_TST-030"] == "NOT_EXECUTED"


def test_canonical_dispatch_is_not_silently_extended() -> None:
    contract = _contract()
    bindings = contract["canonical_contracts"]
    dispatch = bindings["provider_dispatch_job"]
    path = generator.REPO_ROOT / dispatch["path"]
    assert generator.sha256_bytes(path.read_bytes()) == dispatch["sha256"]
    schema = json.loads(path.read_bytes())
    source_types = schema["allOf"][1]["properties"]["payload"]["properties"][
        "source_type"
    ]["enum"]
    assert source_types == ["SEARCH_CONSOLE", "GA4", "KEYWORD_RANK_CSV"]
    assert dispatch["advanced_provider_source_type_present"] is False
    assert dispatch["dispatch_modified_by_this_story"] is False


def test_feature_mutation_execution_and_debt_boundaries_are_closed() -> None:
    contract = _contract()
    scope = contract["feature_scope"]
    assert scope["default"] == "DISABLED"
    assert scope["closed_states"] == [
        "DISABLED",
        "RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY",
    ]
    for field in (
        "live_enabled_state_exists",
        "selected_provider_state_exists",
        "activation_interface_exists",
    ):
        assert scope[field] is False
    execution = contract["execution_boundary"]
    assert execution["provider_selection"] == "HUMAN_DECISION_REQUIRED"
    assert execution["provider_approval"] == "ABSENT"
    assert execution["network"] == "FORBIDDEN"
    assert execution["serp_scrape"] == "FORBIDDEN"
    assert execution["release_decision"] == "REQUIRED_SEPARATELY"
    assert execution["formal_TST-032"] == "NOT_EXECUTED"
    assert execution["story_acceptance"] is False
    for field in (
        "recommendation_order",
        "cta_mutation",
        "article_mutation",
        "publication_snapshot_mutation",
        "publication",
    ):
        assert contract["mutation_boundary"][field] == "FORBIDDEN"
    assert contract["debt"]["introduced"] == []


def test_fixture_is_synthetic_canonical_and_data_minimized() -> None:
    contract = _contract()
    fixture = contract["recorded_fixture"]
    content = (generator.REPO_ROOT / fixture["path"]).read_bytes()
    assert len(content) == fixture["bytes"]
    assert generator.sha256_bytes(content) == fixture["sha256"]
    parsed = json.loads(content)
    assert content == generator._canonical_output(parsed)  # noqa: SLF001
    assert parsed["document"]["synthetic"] is True
    assert len(parsed["observations"]) == 6
    serialized = content.decode("ascii").lower()
    for prohibited in (
        "affiliate",
        "api_key",
        "commission",
        "endpoint",
        "keyword_text",
        "password",
        "profit",
        "query_text",
        "raw_response",
        "recommendation",
        "review_body",
        "secret://",
        "token",
        "https://",
    ):
        assert prohibited not in serialized


def test_owned_runtime_has_no_network_or_provider_sdk_import() -> None:
    paths = (
        Path("python/raos/domain/analytics/advanced_rank_provider.py"),
        Path("python/raos/ports/advanced_rank_provider.py"),
        Path("python/raos/application/analytics/advanced_rank_provider.py"),
        Path("python/raos/adapters/recorded_advanced_rank_provider.py"),
    )
    text = "\n".join(
        (generator.REPO_ROOT / path).read_text(encoding="utf-8") for path in paths
    )
    for prohibited in (
        "import requests",
        "import urllib",
        "import httpx",
        "import socket",
        "boto3",
        "googleapiclient",
        "selenium",
    ):
        assert prohibited not in text
