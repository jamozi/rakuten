"""Phase 0 baseline, measurement and rollback acceptance checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts import build_raos_v2_successor as builder
from scripts import validate_raos_v2_successor as validator


ROOT = Path(__file__).resolve().parents[2]
PHASE0 = ROOT / "changes/raos-v2/phase-0"


def read_yaml(name: str) -> dict[str, object]:
    value = yaml.safe_load((PHASE0 / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_phase0_has_exact_nine_required_artifacts() -> None:
    assert {path.name for path in PHASE0.iterdir() if path.is_file()} == {
        "preflight-report.json",
        "source-audit-report.json",
        "public-url-inventory.yaml",
        "production-observation-plan.md",
        "metric-dictionary.yaml",
        "deprecation-ledger.yaml",
        "pilot-reconciliation.yaml",
        "rollback-contract.yaml",
        "phase-0-report.md",
    }


def test_preflight_records_live_repository_and_evidence_boundaries() -> None:
    value = json.loads((PHASE0 / "preflight-report.json").read_text(encoding="utf-8"))
    assert value["repository"]["branch"] == "codex/raos-v2-vertical-slice"
    assert value["repository"]["head"]
    assert value["repository"]["initial_worktree_state"] == "CLEAN"
    assert value["repository"]["initial_status_porcelain"] == []
    assert value["repository"]["initial_diffstat"] == []
    assert (
        value["boundaries"]["generator_owner"] == "scripts/build_raos_v2_successor.py"
    )
    assert value["boundaries"]["external_actions"] == "NOT_EXECUTED"
    assert value["boundaries"]["public_observation"] == "PUBLIC_READ_ONLY"


def test_public_inventory_preserves_observed_urls_without_mutation() -> None:
    value = read_yaml("public-url-inventory.yaml")
    rows = {row["path"]: row for row in value["urls"]}
    assert value["evidence_class"] == "PUBLIC_READ_ONLY"
    assert value["automatic_public_mutation"] is False
    assert rows["/carry-on-suitcase-comparison/"]["observation"]["status"] == 200
    assert (
        rows["/portable-power-station-guide/"]["safe_initial_disposition"]
        == "KEEP_CURRENT_DEFER_V2"
    )
    assert (
        rows["/countertop-dishwasher-for-small-households/"]["observation"]["status"]
        == 404
    )
    assert (
        rows["/countertop-dishwasher-for-small-households/"]["safe_initial_disposition"]
        == "NO_ROUTE_OR_REDIRECT"
    )
    assert rows["/about-ad-policy/"]["observation"]["status"] == 200
    assert rows["/advertising-policy/"]["observation"]["status"] == 404
    assert len(value["visual_baseline"]) == 12
    assert value["visual_baseline_evidence"] == {
        "source": "changes/raos-v2/recorded-inputs/phase0-visual-evidence.v1.json",
        "classification": "PUBLIC_READ_ONLY_MANUAL_RECORDED",
        "raw_images": "LOCAL_ONLY_NOT_TRACKED_NOT_REVERIFIED",
        "capture_contract": "PLAYWRIGHT_CLI_SNAPSHOT_FIRST_390_768_1440_V1",
    }
    assert {
        (row["path"], row["viewport"]) for row in value["visual_baseline"]
    } == {
        (path, viewport)
        for path in {
            "/",
            "/carry-on-suitcase-comparison/",
            "/portable-power-station-guide/",
            "/anker-solix-c300-c800-c1000-differences/",
        }
        for viewport in {"390x844", "768x1024", "1440x900"}
    }


def test_pilot_reconciliation_uses_actual_public_observation() -> None:
    value = read_yaml("pilot-reconciliation.yaml")
    rows = {row["route"]: row for row in value["articles"]}
    assert all(
        row["observation"]["evidence_class"] == "PUBLIC_READ_ONLY"
        for row in rows.values()
    )
    assert rows["/carry-on-suitcase-comparison/"]["observation"]["status"] == 200
    assert (
        rows["/countertop-dishwasher-for-small-households/"]["observation"]["status"]
        == 404
    )
    assert not any("REOBSERVE_REQUIRED" in json.dumps(row) for row in rows.values())


def test_metric_dictionary_never_coerces_unavailable_to_zero() -> None:
    value = read_yaml("metric-dictionary.yaml")
    assert value["rules"]["missing_value"] == "UNAVAILABLE"
    assert value["rules"]["missing_never_equals_zero"] is True
    identifiers = {row["id"] for row in value["metrics"]}
    assert {
        "QDS",
        "AFFILIATE_OUTBOUND_CTR",
        "CONFIRMED_EPC",
        "CONFIRMED_RPM",
        "ECONOMIC_CONTRIBUTION_PROFIT",
        "MONTHLY_CONFIRMED_CONTRIBUTION_PROFIT",
        "ARTICLE_PAYBACK_MONTHS",
        "CATEGORY_PAYBACK_MONTHS",
        "COMPLAINT_FIRST_RESPONSE_WITHIN_72H_RATE",
        "HUMAN_HOURS_PER_ARTICLE",
        "UPDATE_COST_PER_PAGE",
    } <= identifiers
    assert all(row["current_value"] == "UNAVAILABLE" for row in value["metrics"])
    assert all(
        row["source"] and row["required_maturity"] and row["unavailable_rule"]
        for row in value["metrics"]
    )


def test_deprecation_ledger_covers_all_fifteen_asset_classes_without_auto_delete() -> (
    None
):
    ledger = read_yaml("deprecation-ledger.yaml")
    assert ledger["automatic_deletion"] is False
    assert (
        ledger["default_removal_gate"]
        == "MINIMUM_2_RELEASES_AND_30_DAYS_UNUSED_PLUS_HUMAN_APPROVAL"
    )
    assets = ledger["assets"]
    assert len(assets) == 15
    assert ledger["retire_requires_verified_unused"] is True
    required = {
        "asset",
        "decision",
        "reason",
        "migration",
        "deletion_gate",
        "usage_evidence",
        "replacement",
        "rollback",
        "removal_readiness",
    }
    assert all(set(row) == required for row in assets)
    assert {row["decision"] for row in assets} <= {
        "KEEP",
        "REWORK",
        "MIGRATE",
        "RETIRE",
        "DEFER",
    }
    assert all(
        row["deletion_gate"] == ledger["default_removal_gate"]
        for row in assets
        if row["decision"] == "RETIRE"
    )
    assert all(
        row["usage_evidence"]["verified_unused"] is False
        and row["removal_readiness"] == "BLOCKED_USAGE_NOT_VERIFIED_UNUSED"
        for row in assets
        if row["decision"] == "RETIRE"
    )
    assert all(
        row["replacement"]["plan"]
        and row["rollback"]["plan"]
        and row["rollback"]["production_execution"] == "NOT_EXECUTED"
        for row in assets
    )


def test_retire_cannot_advance_without_verified_unused_evidence() -> None:
    ledger = builder.deprecation_ledger()
    retired = next(row for row in ledger["assets"] if row["decision"] == "RETIRE")
    retired["removal_readiness"] = "READY_FOR_REMOVAL_GATE"
    with pytest.raises(builder.BuildFailure, match="DEPRECATION_LEDGER"):
        builder.validate_deprecation_ledger_document(ledger)


@pytest.mark.parametrize(
    "rows",
    [
        [
            {"source": "/a/", "destination": "/b/"},
            {"source": "/b/", "destination": "/c/"},
        ],
        [
            {"source": "/a/", "destination": "/b/"},
            {"source": "/b/", "destination": "/a/"},
        ],
        [{"source": "/a/", "destination": "/"}, {"source": "/b/", "destination": "/"}],
    ],
)
def test_redirect_contract_fails_closed(rows: list[dict[str, object]]) -> None:
    with pytest.raises(validator.ValidationFailure):
        validator.validate_redirect_rules(rows)


def test_route_canonical_robots_round_trip_restores_exact_baseline() -> None:
    baseline: validator.RouteSnapshot = (
        "/carry-on-suitcase-comparison/",
        200,
        "https://kurashinoshirube.com/carry-on-suitcase-comparison/",
        "index,follow",
    )
    candidate: validator.RouteSnapshot = (
        baseline[0],
        200,
        baseline[2],
        "noindex,nofollow",
    )
    receipt = validator.simulate_route_round_trip(baseline, candidate)
    assert receipt["status"] == "PASSED_LOCAL"
    assert receipt["exact_tuple_restored"] is True
    assert receipt["baseline_sha256"] == receipt["restored_sha256"]
    contract = read_yaml("rollback-contract.yaml")
    recorded = contract["simulation"]["route_tuple_round_trip"]
    assert recorded == receipt


def test_route_round_trip_rejects_tampered_baseline_binding() -> None:
    baseline: validator.RouteSnapshot = (
        "/carry-on-suitcase-comparison/",
        200,
        "https://kurashinoshirube.com/carry-on-suitcase-comparison/",
        "index,follow",
    )
    candidate: validator.RouteSnapshot = (
        baseline[0],
        200,
        baseline[2],
        "noindex,nofollow",
    )
    receipt = validator.simulate_route_round_trip(baseline, candidate)
    tampered: validator.RouteSnapshot = (
        baseline[0],
        baseline[1],
        baseline[2],
        "noindex",
    )
    with pytest.raises(validator.ValidationFailure):
        validator.restore_route_projection(
            candidate,
            tampered,
            expected_baseline_sha256=str(receipt["baseline_sha256"]),
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://kurashinoshirube.com/",
        "https://example.com/",
        "https://kurashinoshirube.com/wp-admin/",
        "https://kurashinoshirube.com/?preview=1",
        "https://user:password@kurashinoshirube.com/",
        "https://kurashinoshirube.com/%77p-admin/",
        "https://kurashinoshirube.com/%2e%2e/private/",
        "https://kurashinoshirube.com/a/../wp-admin/",
    ],
)
def test_capture_url_policy_rejects_unsafe_targets(url: str) -> None:
    with pytest.raises(validator.ValidationFailure):
        validator.validate_public_url(url)


def test_phase0_local_validation_is_not_production_evidence() -> None:
    receipt = validator.validate_generated()
    assert receipt["status"] == "STRUCTURAL_VALIDATION_PASSED_LOCAL"
    assert receipt["external_actions"] == "NOT_EXECUTED"
    report = (PHASE0 / "phase-0-report.md").read_text(encoding="utf-8")
    assert "Production backup/restore/write | NOT_EXECUTED" in report
