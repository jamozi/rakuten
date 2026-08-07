"""Canonical, schema, and replay semantics for the ST-1203 fixture slice."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
import yaml

from scripts import build_st1203_search_console_recorded_adapter as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_DIMENSIONS = ["date", "query", "page", "country", "device"]
BASELINE_REQUEST_SHA256 = (
    "b062bbe5000e83471fe3f1557f04c01a1b311d312055a74083df19fa7d5bd0be"
)
BEYOND_REQUEST_SHA256 = (
    "603738ab94f0c2cdd7c474ba0418ebd36d66215d125e180acdaefed5e84a0788"
)


def _record(document: dict[str, Any], collection: str, identity: str) -> dict[str, Any]:
    matches = [item for item in document[collection] if item["id"] == identity]
    assert len(matches) == 1
    return matches[0]


def test_canonical_story_and_safe_default_are_unchanged() -> None:
    backlog = yaml.safe_load(
        (
            REPOSITORY_ROOT
            / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
        ).read_bytes()
    )
    story = _record(backlog, "stories", "ST-1203")
    assert story["title"] == "Search Console adapter"
    assert story["objective"] == "GSC factsをVersioned import"
    assert story["depends_on"] == ["ST-0305", "ST-0204"]
    assert story["requirement_ids"] == ["FR-013"]
    assert story["acceptance_criteria"] == [
        "dimension/request preserved",
        "late reimport",
    ]
    assert story["test_suites"] == ["TST-030"]
    assert story["open_decisions"] == ["OD-015"]
    assert story["implementation_status"] == "NOT_STARTED"
    assert story["verification_status"] == "NOT_EXECUTED"

    decisions = yaml.safe_load(
        (
            REPOSITORY_ROOT
            / "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
        ).read_bytes()
    )
    decision = _record(decisions, "items", "OD-015")
    assert decision["blocking"] is True
    assert decision["default_behavior"] == "Recorded fixtureのみ"


def test_tst030_remains_formal_and_not_executed() -> None:
    catalog = yaml.safe_load(
        (
            REPOSITORY_ROOT
            / "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
        ).read_bytes()
    )
    suite = _record(catalog, "suites", "TST-030")
    assert suite["execution_status"] == "NOT_EXECUTED"
    assert set(suite["environments"]) == {"CI", "staging"}


def test_all_requests_and_canonical_rows_match_installed_schemas(
    generated_fixtures: dict[str, dict[str, Any]],
    request_schema: dict[str, Any],
    row_schema: dict[str, Any],
) -> None:
    request_validator = Draft202012Validator(
        request_schema, format_checker=FormatChecker()
    )
    row_validator = Draft202012Validator(row_schema, format_checker=FormatChecker())
    for fixture in generated_fixtures.values():
        request_validator.validate(fixture["request"])
        for row in fixture["recorded_result"]["rows"]:
            row_validator.validate(row)


def test_internal_request_hash_and_provider_wire_names_are_exact(
    generated_fixtures: dict[str, dict[str, Any]],
) -> None:
    for fixture in generated_fixtures.values():
        request = fixture["request"]
        assert (
            generator.canonical_request_sha256(request)
            == fixture["source_request_sha256"]
        )
        body = fixture["outbound_request"]["body"]
        assert body["type"] == request["search_type"]
        assert body["rowLimit"] == request["row_limit"]
        assert body["startRow"] == request["start_row"]
        assert "searchType" not in body


def test_dimension_and_key_order_are_preserved(
    generated_fixtures: dict[str, dict[str, Any]],
) -> None:
    for fixture in generated_fixtures.values():
        assert fixture["request"]["dimensions"] == EXPECTED_DIMENSIONS
        assert fixture["outbound_request"]["body"]["dimensions"] == EXPECTED_DIMENSIONS
        provider_rows = fixture["provider_response"]["rows"]
        canonical_rows = fixture["recorded_result"]["rows"]
        assert len(provider_rows) == len(canonical_rows)
        for provider_row, canonical_row in zip(
            provider_rows, canonical_rows, strict=True
        ):
            assert canonical_row["dimensions"] == EXPECTED_DIMENSIONS
            assert canonical_row["keys"] == provider_row["keys"]
            assert len(canonical_row["keys"]) == len(EXPECTED_DIMENSIONS)


def test_late_replay_is_separately_inspectable_without_supersession_claim(
    generated_fixtures: dict[str, dict[str, Any]],
) -> None:
    baseline = generated_fixtures["baseline.json"]
    revised = generated_fixtures["late-revised.json"]
    assert baseline["request"] == revised["request"]
    assert baseline["source_request_sha256"] == BASELINE_REQUEST_SHA256
    assert revised["source_request_sha256"] == BASELINE_REQUEST_SHA256
    assert baseline["provider_response"]["rows"] != revised["provider_response"]["rows"]
    assert (
        baseline["recorded_result"]["recorded_at"]
        < revised["recorded_result"]["recorded_at"]
    )
    encoded = json.dumps([baseline, revised], sort_keys=True).casefold()
    assert "supersed" not in encoded


def test_beyond_data_offset_is_a_successful_empty_page(
    generated_fixtures: dict[str, dict[str, Any]],
) -> None:
    fixture = generated_fixtures["start-beyond-data.json"]
    assert fixture["source_request_sha256"] == BEYOND_REQUEST_SHA256
    assert fixture["request"]["row_limit"] == 25_000
    assert fixture["request"]["start_row"] == 25_000
    assert fixture["provider_response"]["rows"] == []
    assert fixture["recorded_result"]["rows"] == []
    assert fixture["recorded_result"]["pagination"]["returned_row_count"] == 0


def test_top_rows_caveat_is_explicit_on_results_and_rows(
    generated_fixtures: dict[str, dict[str, Any]],
) -> None:
    for fixture in generated_fixtures.values():
        result = fixture["recorded_result"]
        assert result["top_rows_only"] is True
        assert result["rows_not_guaranteed_complete"] is True
        assert all(row["is_top_rows_limited"] is True for row in result["rows"])


def test_synthetic_boundary_is_materially_declared(
    source_contract: dict[str, Any],
) -> None:
    policy = source_contract["recorded_result_policy"]
    assert policy["synthetic_site_url"] == "sc-domain:example.invalid"
    assert policy["synthetic_page_origin"] == "https://example.invalid"
    assert policy["synthetic_page_components"] == ("NO_USERINFO_PORT_QUERY_OR_FRAGMENT")
    assert policy["synthetic_query_pattern"] == (
        r"synthetic [a-z0-9]+(?:[ -][a-z0-9]+)*"
    )
    assert policy["synthetic_query_max_length"] == 80
    assert policy["dimension_filter_groups"] == "REQUIRED_EMPTY"


def test_manifest_inventory_is_closed_and_byte_bound() -> None:
    manifest_path = REPOSITORY_ROOT / generator.MANIFEST_PATH
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["fixture_count"] == 3
    assert [item["path"] for item in manifest["fixtures"]] == list(
        generator.EXPECTED_FIXTURE_NAMES
    )
    assert manifest["boundary"]["formal_tst_030"] == "NOT_EXECUTED"
    assert manifest["boundary"]["local_result"] == "IMPLEMENTATION_CANDIDATE_ONLY"
    for item in manifest["fixtures"]:
        content = (REPOSITORY_ROOT / generator.FIXTURE_ROOT / item["path"]).read_bytes()
        assert item["bytes"] == len(content)
        assert item["sha256"] == hashlib.sha256(content).hexdigest()
