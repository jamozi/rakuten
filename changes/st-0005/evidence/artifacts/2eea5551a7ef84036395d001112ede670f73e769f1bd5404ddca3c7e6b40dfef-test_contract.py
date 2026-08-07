from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from scripts import build_st0205_synthetic_data as generator


def test_contract_is_exact_approved_story(contract: dict[str, Any]) -> None:
    assert contract["document"] == {
        "id": "RAOS-SYNTHETIC-DATA-FACTORY-001",
        "version": "1.0.0",
        "story_id": "ST-0205",
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "formal_verification": "NOT_EXECUTED",
    }
    assert contract["story"]["dependencies"] == ["ST-0201", "ST-0202"]
    assert contract["story"]["design_refs"] == ["RAOS-TEST-001"]
    assert contract["story"]["required_suites"] == ["TST-005", "TST-031"]
    assert contract["story"]["open_decisions"] == []


def test_contract_covers_exact_canonical_domain_map(contract: dict[str, Any]) -> None:
    domains = contract["domains"]
    assert domains["exact_count"] == 13
    assert tuple(domains["ordered"]) == generator.DOMAIN_ORDER
    assert domains["payload_allowlists"] == {
        name: list(fields) for name, fields in generator.PAYLOAD_ALLOWLISTS.items()
    }


def test_contract_covers_required_edge_dimensions(contract: dict[str, Any]) -> None:
    assert tuple(contract["seed_scenarios"]["required_dimensions"]) == (
        generator.SCENARIO_DIMENSIONS
    )
    assert (
        tuple(
            tuple(pair)
            for pair in contract["seed_scenarios"]["ordered_fixture_scenarios"]
        )
        == generator.FIXTURE_SCENARIOS
    )


def test_contract_recognizes_all_canonical_classes_and_refuses_restricted(
    contract: dict[str, Any],
) -> None:
    privacy = contract["privacy"]
    assert privacy["classification_values"] == [
        "PUBLIC",
        "INTERNAL",
        "CONFIDENTIAL",
        "RESTRICTED",
    ]
    assert privacy["missing_classification_default"] == "CONFIDENTIAL"
    assert privacy["unknown_classification"] == "REJECT"
    assert privacy["restricted_classification"] == ("FORBIDDEN_IN_REPOSITORY_AND_LOGS")


def test_contract_maps_required_security_controls(contract: dict[str, Any]) -> None:
    control_ids = [row["id"] for row in contract["security"]["control_mappings"]]
    assert control_ids == [
        "SEC-APP-001",
        "SEC-DATA-003",
        "SEC-DATA-004",
        "SEC-DATA-007",
        "SEC-SDLC-006",
    ]


def test_dependency_manifest_hashes_are_exact_live_bytes(
    contract: dict[str, Any],
) -> None:
    rows = contract["provenance"]["predecessor_manifests"]
    assert [row["story_id"] for row in rows] == ["ST-0201", "ST-0202"]
    for row in rows:
        content = (generator.REPO_ROOT / row["path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == row["sha256"]


def test_license_metadata_is_repository_authoritative(contract: dict[str, Any]) -> None:
    provenance = contract["provenance"]
    authority = provenance["fixture_license_authority"]
    package = generator.REPO_ROOT / authority["path"]
    assert hashlib.sha256(package.read_bytes()).hexdigest() == authority["sha256"]
    assert authority["json_pointer"] == "/license"
    assert json.loads(package.read_bytes())["license"] == "UNLICENSED"
    assert provenance["fixture_license"] == "UNLICENSED"


def test_contract_preserves_non_runtime_and_status_boundaries(
    contract: dict[str, Any],
) -> None:
    boundary = contract["boundary"]
    assert boundary["formal_tst_005"] == "NOT_EXECUTED"
    assert boundary["formal_tst_031"] == "NOT_EXECUTED"
    assert boundary["privacy_security_review"] == "NOT_EXECUTED"
    assert boundary["retention_period_decision"] == "NOT_MADE"
    assert boundary["status_apply"] == "FORBIDDEN"
    assert boundary["effective_canonical_status"] == "UNCHANGED"
    assert "STATUS_EVIDENCE_OR_CANONICAL_APPLY" in contract["out_of_scope"]


def test_all_pinned_canonical_inputs_match_current_bytes() -> None:
    for name, digest in generator.PINNED_CANONICAL_INPUTS.items():
        path = generator.REPO_ROOT / Path(name)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
