"""Hostile fail-closed contract tests for ST-1603."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from scripts import build_st1603_security_verification_pack as generator
from scripts import build_st1506_production_deployment as base_generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MARKER = "REJECTED_SECURITY_INPUT_1603"


def _validate(document: dict[str, Any]) -> None:
    generator.validate_contract(document, REPOSITORY_ROOT)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        ("asvs_mapping", "status", "PASS"),
        ("asvs_mapping", "mappings", [{"control": MARKER}]),
        ("verification_suites", "required_execution_status", "PASS"),
        ("verification_suites", "evidence_references", [MARKER]),
        ("findings", "collection_status", "COMPLETE"),
        ("findings", "open_critical", 0),
        ("findings", "open_high", 0),
        ("findings", "items", [{"id": MARKER}]),
        ("remediations", "collection_status", "COMPLETE"),
        ("remediations", "items", [MARKER]),
        ("exceptions", "collection_status", "APPROVED"),
        ("exceptions", "items", [MARKER]),
        ("evidence", "collection_status", "PASS"),
        ("evidence", "control_evidence", [MARKER]),
        ("evidence", "scan_results", [MARKER]),
        ("evidence", "manual_results", [MARKER]),
        ("evidence", "artifacts", [MARKER]),
        ("execution_boundary", "scanner_execution", "ALLOWED"),
        ("execution_boundary", "network_access", "ALLOWED"),
        ("execution_boundary", "environment_access", "ALLOWED"),
        ("execution_boundary", "credential_access", "ALLOWED"),
        ("execution_boundary", "staging_action", "ALLOWED"),
        ("execution_boundary", "release_action", "ALLOWED"),
        ("execution_boundary", "production_action", "ALLOWED"),
        ("evidence_boundary", "st_1607_eligible", True),
        ("evidence_boundary", "release_eligible", True),
        ("evidence_boundary", "formal_tst_026", "PASS"),
        ("evidence_boundary", "formal_tst_031", "PASS"),
    ),
)
def test_non_attesting_sections_cannot_be_promoted(
    contract_document: dict[str, Any], section: str, field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document[section][field] = value
    with pytest.raises(generator.SecurityVerificationPackError) as captured:
        _validate(document)
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize("value", (1, True, 0.0, "0"))
def test_action_counts_require_exact_builtin_zero(
    contract_document: dict[str, Any], value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"]["action_counts"]["scan"] = value
    with pytest.raises(generator.SecurityVerificationPackError):
        _validate(document)


def test_approvals_and_decision_cannot_be_forged(
    contract_document: dict[str, Any],
) -> None:
    for field, value in (("approvals", {"reviewer": MARKER}), ("decision", "PASS")):
        document = copy.deepcopy(contract_document)
        document[field] = value
        with pytest.raises(generator.SecurityVerificationPackError) as captured:
            _validate(document)
        assert MARKER not in str(captured.value)


def test_projection_counts_and_verification_truth_cannot_be_rebound(
    contract_document: dict[str, Any],
) -> None:
    mutations = (
        ("projected_control_count", 82),
        ("verified_control_count", 83),
        ("interpretation", "VERIFIED"),
    )
    for field, value in mutations:
        document = copy.deepcopy(contract_document)
        document["catalog_projection"][field] = value
        with pytest.raises(generator.SecurityVerificationPackError):
            _validate(document)


def test_predecessor_safety_cannot_be_weakened(
    contract_document: dict[str, Any],
) -> None:
    mutations = (
        ("workload_credential_seam", "provider_selection", "aws"),
        ("workload_credential_seam", "external_writes", "ALLOWED"),
        ("staging_deployment", "activation", "ENABLED"),
        ("staging_deployment", "live_provider_calls", "ALLOWED"),
    )
    for section, field, value in mutations:
        document = copy.deepcopy(contract_document)
        document["predecessor_bindings"][section][field] = value
        with pytest.raises(generator.SecurityVerificationPackError) as captured:
            _validate(document)
        assert "aws" not in str(captured.value).lower()


def test_source_inventory_is_ordered_unique_and_hash_bound(
    contract_document: dict[str, Any],
) -> None:
    for mutation in ("reorder", "duplicate", "hash"):
        document = copy.deepcopy(contract_document)
        sources = document["sources"]
        if mutation == "reorder":
            sources[0], sources[1] = sources[1], sources[0]
        elif mutation == "duplicate":
            sources[0] = copy.deepcopy(sources[1])
        else:
            sources[0]["sha256"] = "0" * 64
        with pytest.raises(generator.SecurityVerificationPackError):
            _validate(document)


def test_unknown_missing_and_reordered_contract_keys_are_rejected(
    contract_document: dict[str, Any],
) -> None:
    for mutation in ("unknown", "missing", "reorder"):
        document = copy.deepcopy(contract_document)
        if mutation == "unknown":
            document[MARKER] = MARKER
        elif mutation == "missing":
            document.pop("evidence_boundary")
        else:
            first = document.pop("document")
            document["document"] = first
        with pytest.raises(generator.SecurityVerificationPackError) as captured:
            _validate(document)
        assert MARKER not in str(captured.value)


def test_strict_yaml_rejects_duplicate_keys_and_aliases(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text("document: safe\ndocument: blocked\n", encoding="utf-8")
    alias = tmp_path / "alias.yaml"
    alias.write_text("value: &blocked safe\ncopy: *blocked\n", encoding="utf-8")
    for path in (duplicate, alias):
        with pytest.raises(base_generator.ProductionDeploymentContractError):
            base_generator.load_yaml(path)
