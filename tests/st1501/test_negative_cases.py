"""Hostile and exact-type validation cases for ST-1501."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import build_st1501_terraform_foundation as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _validate(document: dict[str, Any]) -> generator.FoundationModel:
    return generator.validate_contract(document, REPOSITORY_ROOT)


def _copy_pinned_sources(destination: Path) -> None:
    for relative in generator.PINNED_SOURCES:
        source = REPOSITORY_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _rebind_handoff_source(
    root: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    handoff_path = root / generator.DESIGN_HANDOFF_PATH
    digest = generator.sha256_file(handoff_path)
    rebound_sources = dict(generator.PINNED_SOURCES)
    rebound_sources[generator.DESIGN_HANDOFF_PATH.as_posix()] = digest
    monkeypatch.setattr(generator, "PINNED_SOURCES", rebound_sources)

    rebound_contract = copy.deepcopy(contract_document)
    handoff_uri = f"repo://{generator.DESIGN_HANDOFF_PATH.as_posix()}"
    source_rows = [
        row for row in rebound_contract["sources"] if row["uri"] == handoff_uri
    ]
    assert len(source_rows) == 1
    source_rows[0]["sha256"] = digest
    return rebound_contract


@pytest.mark.parametrize(
    "field",
    (
        "selected_profile_id",
        "selected_profile_kind",
        "selected_provider_name",
        "default_profile_id",
        "fallback_profile_id",
    ),
)
def test_no_foundation_profile_can_be_selected_defaulted_or_fallbacked(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_foundation_admission"][field] = "AWS_TOKYO"
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize("binding_name", generator.FOUNDATION_BINDING_NAMES)
@pytest.mark.parametrize("field", ("selected", "default", "fallback"))
def test_provider_account_region_plugin_and_backend_bindings_remain_unset(
    contract_document: dict[str, Any], binding_name: str, field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_foundation_admission"]["binding_policy"][binding_name][
        field
    ] = "AWS_REFERENCE_SHORTCUT"
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize(
    "field", ("implicit_binding", "name_or_reference_only_eligibility")
)
def test_implicit_or_name_only_foundation_binding_is_forbidden(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_foundation_admission"]["binding_policy"][field] = (
        "ALLOWED"
    )
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("configured_mapping_count", 1),
        ("complete_mapping", True),
        ("required_mapping_mode", "PROVIDER_LABEL_ONLY"),
    ),
)
def test_mapping_policy_cannot_claim_completion_without_mappings(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_foundation_admission"]["mapping_policy"][field] = value
    with pytest.raises(generator.FoundationContractError):
        _validate(document)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("missing", "MISSING_CAPABILITY_MAPPING"),
        ("unknown", "UNKNOWN_CAPABILITY_MAPPING"),
        ("duplicate", "DUPLICATE_CAPABILITY_MAPPING"),
        ("reorder", "CAPABILITY_MAPPING_ORDER_DRIFT"),
    ),
)
def test_foundation_capability_inventory_fails_closed(
    contract_document: dict[str, Any], mutation: str, expected_code: str
) -> None:
    document = copy.deepcopy(contract_document)
    rows = document["provider_neutral_foundation_admission"][
        "capability_mapping_requirements"
    ]
    if mutation == "missing":
        rows.pop()
    elif mutation == "unknown":
        rows[-1]["capability_id"] = "provider_specific_shortcut"
    elif mutation == "duplicate":
        rows[-1]["capability_id"] = rows[0]["capability_id"]
    else:
        rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == expected_code


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("eligible", True),
        ("admission_status", "ELIGIBLE"),
        ("concrete_alternate_provider_selected", True),
    ),
)
def test_eligibility_cannot_precede_complete_mapping_and_evidence(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_foundation_admission"][field] = value
    with pytest.raises(generator.FoundationContractError):
        _validate(document)


def test_aws_labels_cannot_satisfy_foundation_admission(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    admission = document["provider_neutral_foundation_admission"]
    admission["eligible"] = True
    admission["selected_profile_id"] = "AWS_TOKYO"
    admission["selected_profile_kind"] = "AWS"
    admission["selected_provider_name"] = "AWS"
    admission["mapping_policy"]["configured_mapping_count"] = len(
        generator.REQUIRED_FOUNDATION_CAPABILITY_IDS
    )
    admission["mapping_policy"]["complete_mapping"] = True
    for row in admission["capability_mapping_requirements"]:
        row["selected_mapping"] = f"AWS_LABEL::{row['capability_id']}"
        row["mapping_status"] = "CONFIGURED"
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == "SAFE_BOUNDARY_VIOLATION"


def test_aws_label_mapping_is_rejected_without_changing_eligibility(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    row = document["provider_neutral_foundation_admission"][
        "capability_mapping_requirements"
    ][0]
    row["selected_mapping"] = "AWS"
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize(
    "field",
    (
        "default",
        "implicit_fallback",
        "selected_binding",
        "eligibility_shortcut",
        "admission_requirement",
        "evidence_substitute",
    ),
)
@pytest.mark.parametrize(
    "section",
    ("reference_architecture", "aws_reference_boundary"),
)
def test_aws_reference_cannot_be_promoted_to_provider_semantics(
    contract_document: dict[str, Any], section: str, field: str
) -> None:
    document = copy.deepcopy(contract_document)
    target = (
        document["reference_architecture"]
        if section == "reference_architecture"
        else document["provider_neutral_foundation_admission"][section]
    )
    target[field] = True
    with pytest.raises(generator.FoundationContractError):
        _validate(document)


@pytest.mark.parametrize(
    "field",
    (
        "provider_label_as_evidence",
        "reference_metadata_as_evidence",
        "local_test_as_live_evidence",
    ),
)
def test_provider_neutral_evidence_rules_cannot_be_weakened(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_foundation_admission"]["evidence_equivalence_policy"][
        field
    ] = "ALLOWED"
    with pytest.raises(generator.FoundationContractError):
        _validate(document)


def test_partial_foundation_capability_mapping_without_evidence_is_rejected(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    row = document["provider_neutral_foundation_admission"][
        "capability_mapping_requirements"
    ][0]
    row["selected_mapping"] = "owner-managed-toolchain"
    row["mapping_status"] = "CONFIGURED"
    with pytest.raises(generator.FoundationContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


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
        (("execution_boundary", "network_access"), "ALLOWED", "FIXED_VALUE_VIOLATION"),
        (
            ("execution_boundary", "credential_access"),
            "ALLOWED",
            "FIXED_VALUE_VIOLATION",
        ),
        (("execution_boundary", "external_writes"), "ALLOWED", "FIXED_VALUE_VIOLATION"),
        (("execution_boundary", "deploy_action"), "ALLOWED", "FIXED_VALUE_VIOLATION"),
        (("execution_boundary", "release_action"), "ALLOWED", "FIXED_VALUE_VIOLATION"),
        (
            ("execution_boundary", "production_action"),
            "ALLOWED",
            "FIXED_VALUE_VIOLATION",
        ),
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


def test_yaml_tags_and_multiple_documents_fail_closed(tmp_path: Path) -> None:
    tagged = tmp_path / "tagged.yaml"
    tagged.write_text("value: !!str blocked\n", encoding="utf-8")
    with pytest.raises(generator.FoundationContractError) as captured:
        generator.load_yaml(tagged)
    assert captured.value.code == "YAML_TAG_FORBIDDEN"

    multiple = tmp_path / "multiple.yaml"
    multiple.write_text("value: safe\n---\nvalue: blocked\n", encoding="utf-8")
    with pytest.raises(generator.FoundationContractError) as captured:
        generator.load_yaml(multiple)
    assert captured.value.code == "YAML_INVALID"


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


@pytest.mark.parametrize(
    "section",
    (
        "approved_scope",
        "source_design_refs",
        "decision",
        "rationale",
        "rejected_alternatives",
        "constraints",
        "security_and_approval_gates",
        "acceptance_criteria",
        "required_test_evidence",
        "open_decision_state",
    ),
)
def test_hash_rebound_handoff_normative_mutations_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contract_document: dict[str, Any],
    section: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    handoff_path = tmp_path / generator.DESIGN_HANDOFF_PATH
    handoff = generator.load_yaml(handoff_path)
    assert isinstance(handoff, dict)

    if section == "decision":
        handoff[section]["foundation_provider_policy"] = "AWS_REQUIRED"
    elif section == "open_decision_state":
        handoff[section]["OD-013"]["safe_default"] = "PRODUCTION_APPLY_ALLOWED"
    elif section == "security_and_approval_gates":
        handoff[section][0] = (
            "Production changes may bypass human approval and formal security gates."
        )
    else:
        handoff[section][0] = "HOSTILE_REBOUND_NORMATIVE_REPLACEMENT"
    handoff_path.write_text(
        yaml.safe_dump(handoff, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    rebound_contract = _rebind_handoff_source(tmp_path, contract_document, monkeypatch)
    with pytest.raises(generator.FoundationContractError) as captured:
        generator.validate_contract(rebound_contract, tmp_path)
    assert captured.value.code in {
        "FIXED_VALUE_VIOLATION",
        "SAFE_BOUNDARY_VIOLATION",
    }


def test_contract_file_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.yaml"
    target.write_text("document: {}\n", encoding="utf-8")
    link = tmp_path / "contract.yaml"
    link.symlink_to(target)
    with pytest.raises(generator.FoundationContractError) as captured:
        generator.load_yaml(link)
    assert captured.value.code == "UNSAFE_FILE_TYPE"
