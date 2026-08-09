"""Hostile and exact-type validation cases for ST-1501."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

import pytest

from scripts import build_st1501_terraform_foundation as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _validate(document: dict[str, Any]) -> generator.FoundationModel:
    return generator.validate_contract(document, REPOSITORY_ROOT)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cloud_provider", "provider-selection"),
        ("production_region", "region-selection"),
        ("backup_region", "backup-selection"),
        ("development_account_id", "development-account-selection"),
        ("production_account_id", "production-account-selection"),
        ("terraform_cli_version", "tool-version-selection"),
        ("provider_plugins", ["provider-plugin-selection"]),
        ("state_backend", "backend-selection"),
        ("credential_source", "REJECTED_INPUT_MARKER_91e6"),
        ("network_cidrs", ["network-selection"]),
        ("availability_zones", ["zone-selection"]),
        ("kms_key_reference", "key-selection"),
        ("monthly_budget_jpy", 1),
        ("resource_definitions", ["resource-selection"]),
    ],
)
def test_selected_provider_account_backend_credential_and_resources_fail_closed(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["selected_configuration"][field] = value
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert "REJECTED_INPUT_MARKER_91e6" not in str(captured.value)


@pytest.mark.parametrize(
    ("path", "value", "expected_code"),
    [
        (("execution_boundary", "activation_enabled"), True, "SAFE_BOUNDARY_VIOLATION"),
        (("execution_boundary", "activation_enabled"), 0, "TYPE_MISMATCH"),
        (
            ("execution_boundary", "activation_status"),
            "ENABLED",
            "FIXED_VALUE_VIOLATION",
        ),
        (
            ("execution_boundary", "live_provider_calls"),
            "ALLOWED",
            "FIXED_VALUE_VIOLATION",
        ),
        (("execution_boundary", "external_writes"), "ALLOWED", "FIXED_VALUE_VIOLATION"),
        (
            ("production_change_requirements", "production_apply"),
            "ALLOWED",
            "FIXED_VALUE_VIOLATION",
        ),
        (
            ("production_change_requirements", "manual_change"),
            "ALLOWED",
            "FIXED_VALUE_VIOLATION",
        ),
    ],
)
def test_activation_live_apply_and_external_write_inputs_are_rejected(
    contract_document: dict[str, Any],
    path: tuple[str, str],
    value: object,
    expected_code: str,
) -> None:
    document = copy.deepcopy(contract_document)
    document[path[0]][path[1]] = value
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == expected_code


@pytest.mark.parametrize("command", generator.NATIVE_COMMANDS)
def test_every_native_operation_must_remain_forbidden(
    contract_document: dict[str, Any], command: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"]["commands"][command] = "ALLOWED"
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize("action", generator.ACTION_NAMES)
@pytest.mark.parametrize("value", [1, -1, True, "0"])
def test_planned_action_counts_require_exact_integer_zero(
    contract_document: dict[str, Any], action: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"]["planned_actions"][action] = value
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    if type(value) is int:
        assert captured.value.code == "SAFE_BOUNDARY_VIOLATION"
    else:
        assert captured.value.code == "TYPE_MISMATCH"


def test_unknown_fields_are_rejected_without_echoing_names_or_values(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    marker = "REJECTED_INPUT_MARKER_91e6"
    document[marker] = marker
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"
    assert marker not in str(captured.value)


def test_resource_like_nested_unknown_field_is_rejected(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["extension_contract"]["resources"] = []
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"


def test_reference_region_cannot_be_promoted_to_selected_region(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["selected_configuration"]["production_region"] = document[
        "reference_architecture"
    ]["region"]
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


def test_yaml_duplicate_keys_fail_with_sanitized_error(tmp_path: Path) -> None:
    marker = "REJECTED_INPUT_MARKER_91e6"
    path = tmp_path / "duplicate.yaml"
    path.write_text(f"document: safe\ndocument: {marker}\n", encoding="utf-8")
    with pytest.raises(generator.FoundationContractError) as captured:
        generator.load_yaml(path)
    assert captured.value.code == "YAML_INVALID"
    assert marker not in str(captured.value)


def test_yaml_aliases_are_forbidden_without_echoing_content(tmp_path: Path) -> None:
    marker = "REJECTED_INPUT_MARKER_91e6"
    path = tmp_path / "alias.yaml"
    path.write_text(f"value: &blocked {marker}\ncopy: *blocked\n", encoding="utf-8")
    with pytest.raises(generator.FoundationContractError) as captured:
        generator.load_yaml(path)
    assert captured.value.code == "YAML_ALIAS_FORBIDDEN"
    assert marker not in str(captured.value)


def test_source_digest_drift_fails_closed(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["sources"][0]["sha256"] = "0" * 64
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == "SOURCE_INVENTORY_DRIFT"


def test_pinned_source_byte_drift_fails_closed(
    tmp_path: Path, contract_document: dict[str, Any]
) -> None:
    for relative in generator.PINNED_SOURCES:
        source = REPOSITORY_ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    drifted = tmp_path / next(iter(generator.PINNED_SOURCES))
    drifted.write_bytes(drifted.read_bytes() + b"\n")
    with pytest.raises(generator.FoundationContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == "SOURCE_DIGEST_MISMATCH"


def test_contract_file_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.yaml"
    target.write_text("document: {}\n", encoding="utf-8")
    link = tmp_path / "contract.yaml"
    link.symlink_to(target)
    with pytest.raises(generator.FoundationContractError) as captured:
        generator.load_yaml(link)
    assert captured.value.code == "UNSAFE_FILE_TYPE"
