"""Closed source and live-smoke reference assertions for ST-0505."""

from __future__ import annotations

import json
from typing import Any

from scripts import build_st0505_rakuten_live_smoke_reference_plan as generator


EXPECTED_PREDECESSOR_URIS = (
    "repo://changes/st-0502/README.md",
    "repo://python/raos/domain/catalog/rakuten_item_search.py",
    "repo://python/raos/ports/rakuten_item_search.py",
    "repo://python/raos/application/catalog/rakuten_item_search.py",
    "repo://python/raos/adapters/recorded_rakuten_item_search.py",
    "repo://tests/st0502/conftest.py",
    "repo://tests/st0502/test_boundaries.py",
    "repo://tests/st0502/test_failure_isolation.py",
    "repo://tests/st0502/test_rakuten_item_search.py",
    "repo://python/raos/domain/catalog/rakuten_item_search_live_request_v1.py",
    "repo://tests/st0502/test_rakuten_item_search_live_request_v1.py",
)


def _plan() -> dict[str, Any]:
    return generator.reference_plan(generator.load_contract())


def test_plan_has_exact_sections_and_non_executable_document() -> None:
    plan = _plan()
    assert tuple(plan) == generator.PLAN_KEYS
    assert plan["document"] == generator.EXPECTED_DOCUMENT
    assert plan["document"]["version"] == "1.1.0"
    assert plan["document"]["executable"] is False
    assert plan["document"]["interface_only"] is True
    assert plan["document"]["decision"] == "NOT_READY"
    assert plan["document"]["story_acceptance"] is False
    assert plan["document"]["production_eligible"] is False
    assert plan["document"]["approval"] is None


def test_predecessor_binds_commit_artifacts_and_recorded_only_semantics() -> None:
    predecessor = _plan()["predecessor_binding"]
    assert predecessor["story_id"] == "ST-0502"
    assert predecessor["commit"] == generator.PREDECESSOR_COMMIT
    assert predecessor["artifacts"] == generator._expected_predecessor_artifacts()
    assert tuple(row["uri"] for row in predecessor["artifacts"]) == (
        EXPECTED_PREDECESSOR_URIS
    )
    assert len(predecessor["artifacts"]) == 11
    assert predecessor["semantics"] == generator.EXPECTED_PREDECESSOR_SEMANTICS
    semantics = predecessor["semantics"]
    assert semantics["purpose"] == "CONTRACT_TEST"
    assert semantics["mode"] == "RECORDED_TEST_ONLY"
    assert semantics["live_eligible"] is False
    assert semantics["health"] == "NOT_EXECUTED"
    assert semantics["requested_page"] == 1
    assert semantics["page_fetch_count"] == 1
    assert type(semantics["retry_count"]) is int
    assert semantics["retry_count"] == 0
    assert type(semantics["pagination_count"]) is int
    assert semantics["pagination_count"] == 0
    assert semantics["storage"] == "NOT_EXECUTED"
    assert semantics["persistence"] == "NOT_EXECUTED"
    assert semantics["receipt_uri"] is None


def test_predecessor_binds_exact_non_executable_live_request_policy() -> None:
    policy = _plan()["predecessor_binding"]["semantics"]["live_request_policy"]

    assert policy == generator.EXPECTED_LIVE_REQUEST_POLICY_SEMANTICS
    assert policy == {
        "policy_name": "RakutenItemSearchLiveRequestV1",
        "policy_version": "V1",
        "provider_api_version": "2026-07-01",
        "non_executable": True,
        "requested_page": 1,
        "hits_minimum": 1,
        "hits_maximum": 30,
        "retry_limit": 0,
        "pagination_followup_limit": 0,
        "review_derived_request_inputs": "EXCLUDED",
        "affiliate_rate_request_inputs": "EXCLUDED",
        "provider_text_trust": "UNTRUSTED_DATA",
    }


def test_predecessor_selects_no_live_endpoint_account_or_capability() -> None:
    semantics = _plan()["predecessor_binding"]["semantics"]
    assert semantics["endpoint_url"] is None
    assert semantics["account"] is None
    assert semantics["credential_access"] == "FORBIDDEN"
    assert semantics["network_access"] == "FORBIDDEN"
    assert semantics["provider_sdk"] == "ABSENT"
    assert semantics["filesystem"] == "ABSENT"
    assert semantics["repository"] == "ABSENT"
    assert semantics["external_actions"] == []


def test_od_015_stays_blocking_unresolved_and_recorded_only() -> None:
    decision = _plan()["open_decision"]
    assert decision == generator.EXPECTED_OPEN_DECISION
    assert decision["status"] == "EXTERNAL_EVIDENCE_REQUIRED"
    assert decision["blocking"] is True
    assert decision["resolved"] is False
    assert decision["safe_default"] == "RECORDED_FIXTURE_ONLY"
    assert decision["live_credentials_available"] is False
    assert decision["live_execution_authorized"] is False


def test_tst_016_is_exact_but_has_no_formal_evidence() -> None:
    suite = _plan()["test_suite"]
    for key, expected in generator.EXPECTED_TEST_SUITE.items():
        assert suite[key] == expected
    assert suite["candidate_tools"] == ["live credential"]
    assert suite["environments"] == ["staging"]
    assert suite["formal_execution"] == "NOT_EXECUTED"
    assert suite["evidence"] is None


def test_live_smoke_is_not_configured_or_runnable() -> None:
    smoke = _plan()["live_smoke_definition"]
    assert smoke == generator.EXPECTED_SMOKE
    assert smoke["status"] == "NOT_CONFIGURED"
    assert smoke["runnable"] is False
    for key in (
        "runner",
        "command",
        "selected_environment",
        "selected_account",
        "selected_endpoint",
        "request",
        "response",
        "report",
        "retry_policy",
        "pagination_policy",
    ):
        assert smoke[key] is None
    assert smoke["credential_selection"] == "ABSENT"
    assert smoke["artifacts"] == []


def test_observations_are_absent_not_success_or_zero_errors() -> None:
    observations = _plan()["observation_boundary"]
    assert observations == generator.EXPECTED_OBSERVATIONS
    assert observations["status"] == "NOT_EXECUTED"
    for key in (
        "started_at",
        "finished_at",
        "auth_observation",
        "schema_observation",
        "rate_observation",
        "provider_request_id",
        "http_status",
        "latency",
    ):
        assert observations[key] is None
    assert observations["observations"] == []
    assert observations["errors"] == []
    assert observations["evidence"] == []
    assert observations["empty_interpretation"] == (
        "NO_LIVE_EXECUTION_EVIDENCE_NOT_ZERO_ERRORS_OR_SUCCESS"
    )


def test_rate_quota_cost_and_capacity_values_are_all_unset() -> None:
    boundary = _plan()["rate_quota_cost_boundary"]
    assert boundary == generator.EXPECTED_RATE_QUOTA_COST
    for key in (
        "rate_limit",
        "rate_remaining",
        "rate_reset",
        "quota_limit",
        "quota_remaining",
        "cost",
        "currency",
        "capacity",
    ):
        assert boundary[key] is None
    assert boundary["values"] == []


def test_execution_is_disabled_with_exact_integer_zero_actions() -> None:
    execution = _plan()["execution_boundary"]
    assert execution["enabled"] is False
    assert execution["status"] == "DISABLED"
    assert tuple(execution["action_counts"]) == generator.ACTION_COUNT_KEYS
    assert all(
        type(value) is int and value == 0
        for value in execution["action_counts"].values()
    )
    assert execution["network"] == "FORBIDDEN"
    assert execution["credential"] == "FORBIDDEN"
    assert execution["provider"] == "FORBIDDEN"
    assert execution["sdk"] == "ABSENT"
    assert execution["filesystem"] == "ABSENT"
    assert execution["repository"] == "ABSENT"
    assert execution["external_actions"] == []


def test_verification_boundary_contains_no_live_or_formal_claim() -> None:
    verification = _plan()["verification_boundary"]
    assert verification["projection_only"] is True
    assert verification["predecessor_connection"] == "NOT_EXECUTED"
    assert verification["formal_tst_016"] == "NOT_EXECUTED"
    for key in (
        "live_auth",
        "live_schema",
        "live_rate",
        "provider_runtime",
        "network",
        "credentials",
        "storage",
        "persistence",
        "staging",
        "release",
        "production",
    ):
        assert verification[key] == "NOT_EXECUTED"
    assert verification["story_acceptance"] is False
    assert verification["production_eligible"] is False
    assert verification["approval"] is None


def test_installed_plan_contains_no_false_completion_claim_values() -> None:
    plan = json.loads(
        (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    )
    assert tuple(plan) == generator.PLAN_KEYS

    def strings(value: object) -> list[str]:
        if type(value) is str:
            return [value]
        if type(value) is list:
            return [item for child in value for item in strings(child)]
        if type(value) is dict:
            return [item for child in value.values() for item in strings(child)]
        return []

    assert {
        "PASS",
        "READY",
        "VALIDATED",
        "IMPLEMENTED",
        "LIVE_SUCCESS",
        "AUTHENTICATED",
        "PRODUCTION_READY",
    }.isdisjoint(strings(plan))
