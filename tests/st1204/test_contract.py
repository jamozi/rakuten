"""Canonical, schema, and replay semantics for the ST-1204 fixture slice."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
import yaml

from scripts import build_st1204_ga4_recorded_adapter as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_DIMENSIONS = ["date", "pagePath", "deviceCategory"]
EXPECTED_METRICS = ["sessions", "screenPageViews", "engagedSessions"]
INTERNAL_REQUEST_SHA256 = (
    "ee206e0ec5d7c98afa2e871a33db134e558a2d854a724832ba834394bb2a22eb"
)
WIRE_REQUEST_SHA256 = "42a74836abe8d2be8cea6c4ffa47a3899e22cdec3f9ba31aa21be23622c7836a"


def _record(document: dict[str, Any], collection: str, identity: str) -> dict[str, Any]:
    matches = [item for item in document[collection] if item["id"] == identity]
    assert len(matches) == 1
    return cast(dict[str, Any], matches[0])


def test_canonical_story_and_safe_defaults_are_unchanged() -> None:
    backlog = yaml.safe_load(
        (
            REPOSITORY_ROOT
            / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
        ).read_bytes()
    )
    story = _record(backlog, "stories", "ST-1204")
    assert story["title"] == "GA4 Data API adapter"
    assert story["objective"] == "aggregate factsをimport"
    assert story["depends_on"] == ["ST-0305", "ST-0204"]
    assert story["requirement_ids"] == ["FR-013"]
    assert story["acceptance_criteria"] == ["property/config snapshot"]
    assert story["test_suites"] == ["TST-030"]
    assert story["open_decisions"] == ["OD-012", "OD-015"]
    assert story["implementation_status"] == "NOT_STARTED"
    assert story["verification_status"] == "NOT_EXECUTED"

    decisions = yaml.safe_load(
        (
            REPOSITORY_ROOT
            / "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
        ).read_bytes()
    )
    privacy = _record(decisions, "items", "OD-012")
    credentials = _record(decisions, "items", "OD-015")
    assert privacy["blocking"] is True
    assert privacy["default_behavior"] == (
        "非必須Trackingを無効化しFirst-party最小Eventのみ"
    )
    assert credentials["blocking"] is True
    assert credentials["default_behavior"] == "Recorded fixtureのみ"


def test_tst030_remains_formal_and_not_executed() -> None:
    catalog = yaml.safe_load(
        (
            REPOSITORY_ROOT
            / "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
        ).read_bytes()
    )
    suite = _record(catalog, "suites", "TST-030")
    assert suite["execution_status"] == "NOT_EXECUTED"
    assert suite["implementation_status"] == "NOT_STARTED"
    assert set(suite["environments"]) == {"CI", "staging"}


def test_source_contract_preserves_official_provider_shapes(
    source_contract: dict[str, Any],
) -> None:
    provider = source_contract["provenance"]["official_provider_references"]
    semantics = provider["semantics"]
    assert semantics["run_report_method"] == "POST"
    assert semantics["request_limit_wire_type"] == "INT64_STRING"
    assert semantics["request_offset_wire_type"] == "INT64_STRING"
    assert semantics["response_headers_and_values"] == "REQUEST_ORDERED"
    assert semantics["metric_values"] == "PROVIDER_STRINGS"
    assert semantics["quota_error_http_status"] == 429
    assert semantics["quota_error_canonical_status"] == "RESOURCE_EXHAUSTED"
    assert semantics["reporting_identity_values"] == [
        "BLENDED",
        "OBSERVED",
        "DEVICE_BASED",
    ]
    assert all(
        item["uri"].startswith("https://developers.google.com/analytics/")
        for item in provider["sources"]
    )


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
        request_validator.validate(fixture["internal_request"])
        for row in fixture["recorded_result"]["canonical_rows"]:
            row_validator.validate(row)


def test_internal_and_wire_request_hashes_are_exact(
    generated_fixtures: dict[str, dict[str, Any]],
) -> None:
    for fixture in generated_fixtures.values():
        request = fixture["internal_request"]
        wire = fixture["wire_request"]
        assert generator.canonical_request_sha256(request) == INTERNAL_REQUEST_SHA256
        assert fixture["internal_request_sha256"] == INTERNAL_REQUEST_SHA256
        assert generator.canonical_json_sha256(wire) == WIRE_REQUEST_SHA256
        assert fixture["wire_request_sha256"] == WIRE_REQUEST_SHA256
        assert wire["dateRanges"] == [
            {"startDate": "2026-07-01", "endDate": "2026-07-02"}
        ]
        assert wire["dimensions"] == [{"name": value} for value in EXPECTED_DIMENSIONS]
        assert wire["metrics"] == [{"name": value} for value in EXPECTED_METRICS]
        assert wire["limit"] == "2"
        assert wire["offset"] == "0"
        assert wire["keepEmptyRows"] is False
        assert wire["returnPropertyQuota"] is True


def test_ordered_provider_values_map_to_canonical_rows_without_conversion(
    generated_fixtures: dict[str, dict[str, Any]],
) -> None:
    for name in ("baseline.json", "late-revised.json"):
        fixture = generated_fixtures[name]
        response = fixture["provider_capture"]["run_report"]["response"]
        result = fixture["recorded_result"]
        assert [item["name"] for item in response["dimensionHeaders"]] == (
            EXPECTED_DIMENSIONS
        )
        assert [item["name"] for item in response["metricHeaders"]] == (
            EXPECTED_METRICS
        )
        assert result["raw_ordered_report"]["rows"] == response["rows"]
        for provider_row, canonical_row in zip(
            response["rows"], result["canonical_rows"], strict=True
        ):
            dimension_values = [
                item["value"] for item in provider_row["dimensionValues"]
            ]
            metric_values = [item["value"] for item in provider_row["metricValues"]]
            assert canonical_row["dimension_values"] == dict(
                zip(EXPECTED_DIMENSIONS, dimension_values, strict=True)
            )
            assert canonical_row["metric_values"] == dict(
                zip(EXPECTED_METRICS, metric_values, strict=True)
            )
            assert all(isinstance(value, str) for value in metric_values)


def test_metadata_quota_and_reporting_identity_are_preserved(
    generated_fixtures: dict[str, dict[str, Any]],
) -> None:
    for name in ("baseline.json", "late-revised.json"):
        fixture = generated_fixtures[name]
        response = fixture["provider_capture"]["run_report"]["response"]
        identity = fixture["provider_capture"]["reporting_identity"]["response"]
        result = fixture["recorded_result"]
        assert result["report_metadata"] == response["metadata"]
        assert result["property_quota"] == response["propertyQuota"]
        assert result["reporting_identity_snapshot"] == identity
        assert result["pagination"] == {
            "limit": 2,
            "offset": 0,
            "returned_row_count": 2,
            "provider_row_count": 3,
            "row_count_independent_of_pagination": True,
        }
        assert all(
            row["reporting_identity"] == identity["reportingIdentity"]
            and row["quota_metadata"] == response["propertyQuota"]
            and row["thresholding_applied"]
            == response["metadata"]["subjectToThresholding"]
            for row in result["canonical_rows"]
        )


def test_late_revision_is_separately_inspectable_without_supersession(
    generated_fixtures: dict[str, dict[str, Any]],
) -> None:
    baseline = generated_fixtures["baseline.json"]
    revised = generated_fixtures["late-revised.json"]
    assert baseline["internal_request"] == revised["internal_request"]
    assert baseline["wire_request"] == revised["wire_request"]
    assert baseline["internal_request_sha256"] == revised["internal_request_sha256"]
    assert baseline["wire_request_sha256"] == revised["wire_request_sha256"]
    assert (
        baseline["recorded_result"]["recorded_at"]
        < revised["recorded_result"]["recorded_at"]
    )
    assert (
        baseline["recorded_result"]["canonical_rows"][0]["metric_values"]
        != (revised["recorded_result"]["canonical_rows"][0]["metric_values"])
    )
    assert baseline["recorded_result"]["supersession_claim"] == "NONE"
    assert revised["recorded_result"]["supersession_claim"] == "NONE"


def test_provider_error_is_sanitized_and_has_no_rows_or_retry_policy(
    generated_fixtures: dict[str, dict[str, Any]],
) -> None:
    fixture = generated_fixtures["provider-error-429.json"]
    expected = {
        "error": {
            "code": 429,
            "message": "Synthetic quota limit reached.",
            "status": "RESOURCE_EXHAUSTED",
        }
    }
    assert fixture["provider_capture"]["run_report"]["http_status"] == 429
    assert fixture["provider_capture"]["run_report"]["response"] == expected
    assert fixture["provider_capture"]["reporting_identity"] == (
        "NOT_ATTEMPTED_AFTER_PROVIDER_ERROR"
    )
    result = fixture["recorded_result"]
    assert result["outcome"] == "PROVIDER_ERROR"
    assert result["provider_error"] == expected
    assert result["canonical_rows"] == []
    assert result["retry_scheduling_policy"] == "NOT_DEFINED"
    assert result["request_hashes"]["reporting_identity_response_sha256"] is None


def test_synthetic_and_safe_boundaries_are_materially_declared(
    source_contract: dict[str, Any],
) -> None:
    request = source_contract["request_policy"]
    boundary = source_contract["boundary"]
    assert request["synthetic_property_id"] == "1000001204"
    assert source_contract["recorded_result_policy"]["synthetic_page_path_prefix"] == (
        "/synthetic/"
    )
    assert boundary["network"] == "FORBIDDEN"
    assert boundary["credentials"] == "FORBIDDEN"
    assert boundary["google_sdk"] == "FORBIDDEN"
    assert boundary["job_dispatch"] == "FORBIDDEN"
    assert boundary["event_publication"] == "FORBIDDEN"
    assert boundary["database_writes"] == "FORBIDDEN"
    assert boundary["persistent_writes"] == "FORBIDDEN"
    assert boundary["retry_scheduling_policy"] == "NOT_DEFINED"
    assert boundary["consent_and_privacy_configuration"] == "NOT_DEFINED"
    assert boundary["formal_tst_030"] == "NOT_EXECUTED"
    assert boundary["production_readiness"] == "NOT_READY"


def test_atomic_publication_design_is_closed_without_resolving_external_decisions(
    source_contract: dict[str, Any],
) -> None:
    generation = source_contract["generation"]
    assert generation["authoritative_root"] == "changes/st-1204/generated"
    assert generation["fixture_root"] == ("changes/st-1204/generated/fixtures/recorded")
    assert generation["manifest_path"] == "changes/st-1204/generated/manifest.json"
    assert generation["legacy_disposition"] == (
        "NON_AUTHORITATIVE_AFTER_COMMIT_THEN_DESCRIPTOR_RELATIVE_REMOVAL"
    )

    handoff_path = REPOSITORY_ROOT / generator.PUBLICATION_DESIGN_PATH
    handoff = yaml.safe_load(handoff_path.read_bytes())["DESIGN_HANDOFF_V1"]
    assert handoff["approved_story"] == "ST-1204"
    assert handoff["open_decisions"] == []
    assert [item["id"] for item in handoff["deferred_external_decisions"]] == [
        "OD-012",
        "OD-015",
    ]
    decision = handoff["decision"]
    assert decision["ST1204-FIXTURE-D1"]["selected_layout"] == (
        "SINGLE_GENERATED_DIRECTORY"
    )
    assert decision["ST1204-FIXTURE-D2"]["locking"] == {
        "owner": "CAPTURED_STORY_DIRECTORY_INODE",
        "check": "NONBLOCKING_SHARED_FLOCK",
        "generate_and_recovery": "NONBLOCKING_EXCLUSIVE_FLOCK",
        "contention": "FAIL_CLOSED_WITHOUT_RETRY",
    }
    assert decision["ST1204-FIXTURE-D2"]["namespace_operation"]["replacement"] == (
        "LINUX_RENAMEAT2_RENAME_EXCHANGE"
    )
    assert handoff["formal_tst_030"] == "NOT_EXECUTED"
    assert handoff["production_readiness"] == "NOT_READY"


def test_manifest_inventory_is_closed_and_byte_bound() -> None:
    manifest_path = REPOSITORY_ROOT / generator.MANIFEST_PATH
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["document"] == {
        "id": "RAOS-GA4-RECORDED-MANIFEST-001",
        "story_id": "ST-1204",
        "version": "1.1.0",
    }
    assert manifest["fixture_count"] == 3
    assert [item["path"] for item in manifest["fixtures"]] == list(
        generator.EXPECTED_FIXTURE_NAMES
    )
    assert manifest["boundary"]["formal_tst_030"] == "NOT_EXECUTED"
    assert manifest["boundary"]["local_result"] == "SOURCE_CONTRACT_CANDIDATE_ONLY"
    for item in manifest["fixtures"]:
        content = (REPOSITORY_ROOT / generator.FIXTURE_ROOT / item["path"]).read_bytes()
        assert item["bytes"] == len(content)
        assert item["sha256"] == hashlib.sha256(content).hexdigest()
