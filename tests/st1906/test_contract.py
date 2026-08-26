"""Contract, privacy, dependency and non-authority bindings for ST-1906."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml

from scripts import build_st1906_advanced_causal_attribution as generator


def _contract() -> dict[str, Any]:
    loaded = yaml.safe_load(
        (generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes()
    )
    assert type(loaded) is dict
    return cast(dict[str, Any], loaded)


def test_document_preserves_deferred_status_and_no_authority() -> None:
    assert _contract()["document"] == generator.EXPECTED_DOCUMENT


def test_authority_story_open_decisions_and_suite_are_current() -> None:
    authority = _contract()["authority"]
    for row in authority.values():
        assert isinstance(row, dict)
        path = generator.REPO_ROOT / str(row["path"])
        assert generator.sha256_bytes(path.read_bytes()) == row["sha256"]

    backlog = yaml.safe_load(
        (generator.REPO_ROOT / authority["canonical_story"]["path"]).read_bytes()
    )
    story = next(row for row in backlog["stories"] if row["id"] == "ST-1906")
    assert story["depends_on"] == ["ST-1303"]
    assert story["test_suites"] == ["TST-032"]
    assert story["implementation_status"] == "DEFERRED_POST_MVP"
    assert story["acceptance_criteria"] == ["separate release decision required"]

    decisions = yaml.safe_load(
        (generator.REPO_ROOT / authority["open_decisions"]["path"]).read_bytes()
    )
    selected = {
        row["id"]: row
        for row in decisions["items"]
        if row["id"] in {"OD-012", "OD-014"}
    }
    assert set(selected) == {"OD-012", "OD-014"}
    assert all(row["status"] == "HUMAN_DECISION_REQUIRED" for row in selected.values())
    assert all(row["blocking"] is True for row in selected.values())

    catalog = yaml.safe_load(
        (generator.REPO_ROOT / authority["test_catalog"]["path"]).read_bytes()
    )
    suite = next(row for row in catalog["suites"] if row["id"] == "TST-032")
    assert suite["release_blocking"] is True
    assert suite["execution_status"] == "NOT_EXECUTED"
    assert suite["environments"] == ["staging"]


def test_predecessor_is_semantic_st1303_input() -> None:
    predecessor = _contract()["predecessor"]
    assert predecessor["story_id"] == "ST-1303"
    assert len(predecessor["artifacts"]) == 8
    assert all(
        (generator.REPO_ROOT / relative).is_file()
        for relative in predecessor["artifacts"]
    )
    assert predecessor["required_semantics"]["arbitrary_total_allocation"] is False
    assert predecessor["required_semantics"]["finance_to_recommendation"] is False


def test_privacy_signal_unavailable_and_mutation_boundaries_are_closed() -> None:
    contract = _contract()
    scope = contract["feature_scope"]
    assert scope["default"] == "DISABLED"
    assert scope["closed_states"] == [
        "DISABLED",
        "RECORDED_SYNTHETIC_AGGREGATE_EVALUATION_ONLY",
    ]
    assert scope["live_enabled_state_exists"] is False
    assert scope["activation_interface_exists"] is False

    privacy = contract["privacy_gate"]
    assert privacy["required_for_available_result"] is True
    for field in (
        "personal_data",
        "persistent_identifier",
        "raw_ip",
        "full_user_agent",
        "free_text",
        "tracking_activation",
        "live_privacy_approval_claimed",
        "retention_policy_activated",
    ):
        assert privacy[field] is False
    assert privacy["not_reviewed_result"] == "UNAVAILABLE"

    signal = contract["signal_contract"]
    assert signal["minimum_exposures_per_arm_per_cell"] == 500
    assert signal["minimum_outcomes_per_arm_per_cell"] == 20
    assert signal["equal_arm_exposures_required"] is True
    assert signal["personal_unit_rows"] is False
    assert signal["observational_identity_linkage"] is False

    unavailable = contract["unavailable_or_refused"]
    for name in (
        "missing_input",
        "privacy_not_reviewed",
        "program_mismatch",
        "period_mismatch",
        "unverified_input",
        "immature_cohort",
        "arm_balance_mismatch",
        "zero_denominator",
        "low_sample",
        "low_outcome_count",
    ):
        assert unavailable[name] == "UNAVAILABLE"
    for name in (
        "unknown_field",
        "personal_or_tracking_field",
        "finance_field",
        "release_decision_input",
    ):
        assert unavailable[name] == "REFUSED"

    mutation = contract["mutation_boundary"]
    assert mutation["authority"] == "NONE"
    assert mutation["tracking_activation"] == "DISABLED"
    assert mutation["finance_values_represented"] is False
    for name in (
        "editorial_mutation",
        "article_html_mutation",
        "cta_mutation",
        "product_selection_mutation",
        "recommendation_order_mutation",
        "publication_snapshot_mutation",
        "publication",
    ):
        assert mutation[name] == "FORBIDDEN"
    assert contract["debt"]["introduced"] == []


def test_fixture_is_canonical_aggregate_synthetic_and_data_minimized() -> None:
    content = (generator.REPO_ROOT / generator.FIXTURE_PATH).read_bytes()
    parsed = json.loads(content)
    assert content == canonical_json(parsed) + b"\n"
    assert parsed["document"]["synthetic"] is True
    assert len(parsed["cells"]) == 5
    serialized = content.decode("ascii").lower()
    for prohibited in (
        "api_key",
        "commission",
        "credential",
        "email",
        "endpoint",
        'full_user_agent":true',
        "password",
        'personal_data":true',
        'persistent_identifier":true',
        "profit",
        'raw_ip":true',
        "review_body",
        "secret://",
        "token",
        'tracking_activation":true',
        "https://",
    ):
        assert prohibited not in serialized


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def test_owned_runtime_has_no_network_provider_or_persistence_import() -> None:
    paths = (
        Path("python/raos/domain/analytics/causal_attribution.py"),
        Path("python/raos/ports/causal_attribution.py"),
        Path("python/raos/application/analytics/causal_attribution.py"),
        Path("python/raos/adapters/recorded_causal_attribution.py"),
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
        "sqlalchemy",
        "psycopg",
        "googleapiclient",
    ):
        assert prohibited not in text
