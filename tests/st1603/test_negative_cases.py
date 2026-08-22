"""Hostile fail-closed contract tests for ST-1603."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import build_st1603_security_verification_pack as generator
from scripts import build_st1505_staging_deployment as staging_owner
from scripts import build_st1506_production_deployment as base_generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MARKER = "REJECTED_SECURITY_INPUT_1603"


def _validate(document: dict[str, Any]) -> None:
    generator.validate_contract(document, REPOSITORY_ROOT)


def _replace_nested(
    document: dict[str, Any], path: tuple[str, ...], value: object
) -> None:
    cursor = document
    for name in path[:-1]:
        nested = cursor[name]
        assert isinstance(nested, dict)
        cursor = nested
    cursor[path[-1]] = value


def _rebind_predecessor_bytes(
    monkeypatch: pytest.MonkeyPatch,
    contract_document: dict[str, Any],
    relative: Path,
    content: bytes,
) -> None:
    digest = hashlib.sha256(content).hexdigest()
    expected_hashes = dict(generator.EXPECTED_PREDECESSOR_HASHES)
    expected_hashes[relative.as_posix()] = digest
    monkeypatch.setattr(generator, "EXPECTED_PREDECESSOR_HASHES", expected_hashes)

    binding_fields = {
        generator.STAGING_CONTRACT_PATH: "contract_sha256",
        generator.STAGING_PLAN_PATH: "reference_plan_sha256",
        generator.STAGING_MANIFEST_PATH: "manifest_sha256",
    }
    staging_binding = contract_document["predecessor_bindings"]["staging_deployment"]
    assert isinstance(staging_binding, dict)
    staging_binding[binding_fields[relative]] = digest

    original_read = generator._read  # noqa: SLF001

    def rebound_read(root: Path, candidate: Path, field: str) -> bytes:
        if candidate == relative:
            return content
        return original_read(root, candidate, field)

    monkeypatch.setattr(generator, "_read", rebound_read)


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


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("eligible", True),
        ("complete_mapping", True),
        ("selected_provider_name", "aws"),
        ("selected_profile_id", "default-profile"),
        ("default_profile_id", "default-profile"),
        ("fallback_profile_id", "fallback-profile"),
        ("aws_reference_role", "OPTIONAL_HISTORICAL_REFERENCE_MAPPINGS_ONLY"),
        ("canonical_story_deliverables", "REPLACED_BY_PORTABLE_OVERLAY"),
        ("non_aws_owner_managed_profiles", "REPLACEMENT_IMPLEMENTATION_PATHS"),
        ("aws_reference_selected_binding", True),
    ),
)
def test_staging_provider_neutral_admission_cannot_be_shortcut(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["predecessor_bindings"]["staging_deployment"][
        "provider_neutral_admission"
    ][field] = value
    with pytest.raises(generator.SecurityVerificationPackError) as captured:
        _validate(document)
    assert "aws" not in str(captured.value).lower()


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("activation", "network_access"), "ALLOWED"),
        (("activation", "credential_access"), "ALLOWED"),
        (("activation", "live_provider_calls"), "ALLOWED"),
        (("activation", "external_writes"), "ALLOWED"),
        (("activation", "operations", "target_adapter_call"), "ALLOWED"),
        (("reference_architecture", "eligibility_shortcut"), True),
        (
            (
                "provider_neutral_staging_admission",
                "aws_reference_boundary",
                "role",
            ),
            "OPTIONAL_HISTORICAL_REFERENCE_MAPPINGS_ONLY",
        ),
        (
            (
                "provider_neutral_staging_admission",
                "aws_reference_boundary",
                "canonical_story_deliverables",
            ),
            "REPLACED_BY_PORTABLE_OVERLAY",
        ),
    ),
)
def test_staging_plan_safety_bypass_fails_after_digest_rebind(
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    path: tuple[str, ...],
    value: object,
) -> None:
    plan = json.loads((REPOSITORY_ROOT / generator.STAGING_PLAN_PATH).read_bytes())
    assert isinstance(plan, dict)
    _replace_nested(plan, path, value)
    content = (
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _rebind_predecessor_bytes(
        monkeypatch,
        contract_document,
        generator.STAGING_PLAN_PATH,
        content,
    )

    with pytest.raises(generator.SecurityVerificationPackError) as captured:
        _validate(contract_document)
    assert captured.value.code == "PREDECESSOR_OWNER_OUTPUT_DRIFT"


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("execution_boundary", "network_access"), "ALLOWED"),
        (("reference_architecture", "eligibility_shortcut"), True),
        (
            ("reference_architecture", "classification"),
            "OPTIONAL_HISTORICAL_REFERENCE_ARCHITECTURE_ONLY",
        ),
        (
            (
                "provider_neutral_staging_admission",
                "aws_reference_boundary",
                "non_aws_owner_managed_profiles",
            ),
            "REPLACEMENT_IMPLEMENTATION_PATHS",
        ),
    ),
)
def test_staging_owner_contract_bypass_fails_after_digest_rebind(
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    path: tuple[str, ...],
    value: object,
) -> None:
    owner_contract = staging_owner.load_yaml(
        REPOSITORY_ROOT / generator.STAGING_CONTRACT_PATH
    )
    assert isinstance(owner_contract, dict)
    rebound_contract = copy.deepcopy(owner_contract)
    _replace_nested(rebound_contract, path, value)
    content = yaml.safe_dump(
        rebound_contract, sort_keys=False, allow_unicode=True
    ).encode("utf-8")
    _rebind_predecessor_bytes(
        monkeypatch,
        contract_document,
        generator.STAGING_CONTRACT_PATH,
        content,
    )

    original_load_yaml = generator._load_yaml  # noqa: SLF001

    def rebound_load_yaml(root: Path, candidate: Path, field: str) -> Mapping[str, Any]:
        if candidate == generator.STAGING_CONTRACT_PATH:
            return rebound_contract
        return original_load_yaml(root, candidate, field)

    monkeypatch.setattr(generator, "_load_yaml", rebound_load_yaml)

    with pytest.raises(generator.SecurityVerificationPackError) as captured:
        _validate(contract_document)
    assert captured.value.code == "PREDECESSOR_OWNER_VALIDATION_FAILED"


def test_staging_manifest_drift_fails_after_digest_rebind(
    contract_document: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = yaml.safe_load(
        (REPOSITORY_ROOT / generator.STAGING_MANIFEST_PATH).read_bytes()
    )
    assert isinstance(manifest, dict)
    _replace_nested(manifest, ("boundary", "activation"), "ENABLED")
    content = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode(
        "utf-8"
    )
    _rebind_predecessor_bytes(
        monkeypatch,
        contract_document,
        generator.STAGING_MANIFEST_PATH,
        content,
    )

    with pytest.raises(generator.SecurityVerificationPackError) as captured:
        _validate(contract_document)
    assert captured.value.code == "PREDECESSOR_OWNER_OUTPUT_DRIFT"


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
