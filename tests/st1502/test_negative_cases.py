"""Hostile and exact-type provider-neutral validation cases for ST-1502."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import build_st1502_data_services as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _validate(document: dict[str, Any]) -> generator.DataServicesModel:
    return generator.validate_contract(document, REPOSITORY_ROOT)


def _copy_pinned_sources(target_root: Path) -> None:
    for relative in generator.PINNED_SOURCES:
        source = REPOSITORY_ROOT / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _rebind_source(
    *,
    document: dict[str, Any],
    relative: str,
    digest: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if relative in generator.AUTHORITY_SOURCES:
        authority_sources = dict(generator.AUTHORITY_SOURCES)
        authority_sources[relative] = digest
        predecessor_sources = dict(generator.PREDECESSOR_SOURCES)
        monkeypatch.setattr(generator, "AUTHORITY_SOURCES", authority_sources)
    else:
        authority_sources = dict(generator.AUTHORITY_SOURCES)
        predecessor_sources = dict(generator.PREDECESSOR_SOURCES)
        predecessor_sources[relative] = digest
        monkeypatch.setattr(generator, "PREDECESSOR_SOURCES", predecessor_sources)
    monkeypatch.setattr(
        generator,
        "PINNED_SOURCES",
        {**authority_sources, **predecessor_sources},
    )
    for row in document["sources"]:
        if row["uri"] == f"repo://{relative}":
            row["sha256"] = digest
            return
    raise AssertionError("source row missing")


@pytest.mark.parametrize("field", generator.EXPECTED_SECTIONS["selected_configuration"])
def test_every_real_global_selection_must_remain_unset(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["selected_configuration"][field]
    document["selected_configuration"][field] = (
        ["REJECTED_INPUT_MARKER_1502"]
        if isinstance(current, list)
        else "REJECTED_INPUT_MARKER_1502"
    )
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert "REJECTED_INPUT_MARKER_1502" not in str(captured.value)


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
def test_provider_profile_selection_default_and_fallback_are_rejected(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_data_services_admission"][field] = "AWS"
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize("binding", generator.DATA_SERVICE_BINDING_NAMES)
@pytest.mark.parametrize("mode", ("selected", "default", "fallback"))
def test_every_provider_service_binding_mode_must_remain_unset(
    contract_document: dict[str, Any], binding: str, mode: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_data_services_admission"]["binding_policy"][binding][
        mode
    ] = "AWS"
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("eligible", True),
        ("concrete_alternate_provider_selected", True),
    ],
)
def test_provider_eligibility_cannot_be_asserted_without_evidence(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_data_services_admission"][field] = value
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SAFE_BOUNDARY_VIOLATION"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", "MISSING_CAPABILITY_MAPPING"),
        ("unknown", "UNKNOWN_CAPABILITY_MAPPING"),
        ("duplicate", "DUPLICATE_CAPABILITY_MAPPING"),
        ("reorder", "CAPABILITY_MAPPING_ORDER_DRIFT"),
    ],
)
def test_capability_inventory_missing_unknown_duplicate_and_order_fail_closed(
    contract_document: dict[str, Any], mutation: str, expected_code: str
) -> None:
    document = copy.deepcopy(contract_document)
    rows = document["provider_neutral_data_services_admission"][
        "capability_mapping_requirements"
    ]
    if mutation == "missing":
        rows.pop()
    elif mutation == "unknown":
        rows[0]["capability_id"] = "unknown_capability"
    elif mutation == "duplicate":
        rows[1]["capability_id"] = rows[0]["capability_id"]
    else:
        rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == expected_code


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("mapping_policy", "configured_mapping_count"), 9),
        (("mapping_policy", "complete_mapping"), True),
        (("mapping_policy", "partial_mapping"), "ALLOW"),
        (("mapping_policy", "provider_label_only_mapping"), "ALLOW"),
        (("mapping_policy", "service_label_only_mapping"), "ALLOW"),
        (("mapping_policy", "reference_only_mapping"), "ALLOW"),
        (("evidence_equivalence_policy", "provider_label_as_evidence"), "ALLOWED"),
        (("evidence_equivalence_policy", "service_label_as_evidence"), "ALLOWED"),
        (
            ("evidence_equivalence_policy", "reference_metadata_as_evidence"),
            "ALLOWED",
        ),
        (
            ("evidence_equivalence_policy", "local_test_as_live_evidence"),
            "ALLOWED",
        ),
        (
            (
                "evidence_equivalence_policy",
                "identical_transport_encryption_evidence",
            ),
            "OPTIONAL",
        ),
    ],
)
def test_partial_label_reference_and_local_evidence_shortcuts_are_rejected(
    contract_document: dict[str, Any],
    path: tuple[str, str],
    value: object,
) -> None:
    document = copy.deepcopy(contract_document)
    admission = document["provider_neutral_data_services_admission"]
    admission[path[0]][path[1]] = value
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code in {
        "SAFE_BOUNDARY_VIOLATION",
        "FIXED_VALUE_VIOLATION",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("transport_encryption", "OPTIONAL"),
        ("encryption_at_rest", "OPTIONAL"),
        ("selected_exceptions", ["AWS"]),
    ],
)
def test_cross_capability_encryption_policy_cannot_be_weakened(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_data_services_admission"][
        "cross_capability_security_policy"
    ][field] = value
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code in {
        "FIXED_VALUE_VIOLATION",
        "SELECTION_MUST_REMAIN_UNSET",
    }


def test_aws_service_label_cannot_satisfy_capability_or_evidence(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    row = document["provider_neutral_data_services_admission"][
        "capability_mapping_requirements"
    ][0]
    row["selected_mapping"] = "RDS"
    row["evidence_refs"] = ["INT-DEC-007"]
    row["mapping_status"] = "SATISFIED"
    with pytest.raises(generator.DataServicesContractError) as captured:
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
    ("reference_architecture", "provider_neutral_data_services_admission"),
)
def test_aws_current_canonical_reference_flags_cannot_be_promoted(
    contract_document: dict[str, Any], section: str, field: str
) -> None:
    document = copy.deepcopy(contract_document)
    target = (
        document[section]
        if section == "reference_architecture"
        else document[section]["aws_reference_boundary"]
    )
    target[field] = True
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SAFE_BOUNDARY_VIOLATION"


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        (
            "reference_architecture",
            "classification",
            "OPTIONAL_HISTORICAL_AWS_REFERENCE_MAPPINGS_ONLY",
        ),
        (
            "provider_neutral_data_services_admission",
            "role",
            "OPTIONAL_HISTORICAL_REFERENCE_MAPPINGS_ONLY",
        ),
        (
            "provider_neutral_data_services_admission",
            "canonical_story_deliverables",
            "CANONICAL_STORY_DELIVERABLES_REPLACED_BY_PORTABILITY_OVERLAY",
        ),
        (
            "provider_neutral_data_services_admission",
            "non_aws_owner_managed_profiles",
            "REPLACEMENT_IMPLEMENTATION_PATHS",
        ),
    ),
)
def test_canonical_reference_cannot_be_demoted_or_replaced_by_overlay(
    contract_document: dict[str, Any], section: str, field: str, value: str
) -> None:
    document = copy.deepcopy(contract_document)
    target = (
        document["reference_architecture"]
        if section == "reference_architecture"
        else document["provider_neutral_data_services_admission"][
            "aws_reference_boundary"
        ]
    )
    target[field] = value
    with pytest.raises(generator.DataServicesContractError):
        _validate(document)


@pytest.mark.parametrize(
    "field",
    generator.EXPECTED_SECTIONS["relational_persistence_intent"]["selected"],
)
def test_every_relational_physical_value_must_remain_unset(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["relational_persistence_intent"]["selected"][field]
    document["relational_persistence_intent"]["selected"][field] = (
        ["selected"] if isinstance(current, list) else "selected"
    )
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize("field", ("port", "high_availability_mode"))
@pytest.mark.parametrize("value", [True, False, 0, 1, "selected"])
def test_relational_port_and_ha_reject_bool_int_and_string_bypasses(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["relational_persistence_intent"]["selected"][field] = value
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize("role_index", range(len(generator.BUCKET_ROLES)))
@pytest.mark.parametrize("field", ("physical_name", "resource_identifier"))
def test_every_object_storage_physical_identifier_is_rejected(
    contract_document: dict[str, Any], role_index: int, field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["object_storage_intent"]["roles"][role_index][field] = (
        "REJECTED_INPUT_MARKER_1502"
    )
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert "REJECTED_INPUT_MARKER_1502" not in str(captured.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("force_destroy", "ALLOWED"),
        ("lifecycle_deletion", "ALLOWED"),
        ("automatic_deletion", "ALLOWED"),
        ("retention_days", 30),
        ("lifecycle_rules", [{"delete_after_days": 30}]),
        ("selected_encryption_key_reference", "key-selection"),
    ],
)
def test_object_storage_destructive_retention_and_key_values_fail_closed(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["object_storage_intent"][field] = value
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code in {
        "FIXED_VALUE_VIOLATION",
        "SELECTION_MUST_REMAIN_UNSET",
    }


@pytest.mark.parametrize("section", ("object_storage_intent", "queue_intent"))
@pytest.mark.parametrize("mutation", ("duplicate", "reorder"))
def test_storage_roles_and_queue_classes_reject_duplicate_and_reordered_rows(
    contract_document: dict[str, Any], section: str, mutation: str
) -> None:
    document = copy.deepcopy(contract_document)
    collection = "roles" if section == "object_storage_intent" else "classes"
    rows = document[section][collection]
    if mutation == "duplicate":
        rows[1] = copy.deepcopy(rows[0])
    else:
        rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code in {
        "CLOSED_SCHEMA_VIOLATION",
        "FIXED_VALUE_VIOLATION",
    }


@pytest.mark.parametrize("field", generator._queue_selection())
def test_every_queue_physical_or_policy_choice_is_rejected(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["queue_intent"]["classes"][0]["selected"][field] = (
        "REJECTED_INPUT_MARKER_1502"
    )
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert "REJECTED_INPUT_MARKER_1502" not in str(captured.value)


@pytest.mark.parametrize("queue_index", range(len(generator.QUEUE_CLASSES)))
@pytest.mark.parametrize(
    "field",
    (
        "dlq",
        "producer_consumer_separation",
        "redrive_role_separation",
        "redrive_control",
    ),
)
def test_each_queue_keeps_dlq_idempotency_and_separated_roles(
    contract_document: dict[str, Any], queue_index: int, field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["queue_intent"]["classes"][queue_index][field] = "OPTIONAL"
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("secrets_intent", "secret_values", "PRESENT"),
        ("secrets_intent", "secret_names", ["physical-secret"]),
        ("secrets_intent", "secret_references", ["physical-reference"]),
        ("secrets_intent", "ambient_credential_resolution", "ALLOWED"),
        ("secrets_intent", "environment_credential_resolution", "ALLOWED"),
        ("key_management_intent", "key_identifiers", ["physical-key"]),
        ("key_management_intent", "key_references", ["physical-reference"]),
        ("key_management_intent", "aliases", ["physical-alias"]),
        ("key_management_intent", "policy_document", {"Statement": []}),
        ("key_management_intent", "deletion_window_days", 7),
        ("key_management_intent", "key_deletion", "ALLOWED"),
        ("observability_intent", "sensitive_telemetry", "ALLOWED"),
        ("data_boundary_intent", "direct_public_database_access", "ALLOWED"),
        ("data_boundary_intent", "direct_public_object_admin_access", "ALLOWED"),
        ("data_boundary_intent", "direct_public_queue_admin_access", "ALLOWED"),
    ],
)
def test_secret_key_telemetry_and_data_boundary_bypasses_are_rejected(
    contract_document: dict[str, Any], section: str, field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document[section][field] = value
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code in {
        "FIXED_VALUE_VIOLATION",
        "SELECTION_MUST_REMAIN_UNSET",
    }


@pytest.mark.parametrize(
    "section",
    (
        "relational_persistence_intent",
        "object_storage_intent",
        "queue_intent",
        "secrets_intent",
        "key_management_intent",
    ),
)
def test_transport_encryption_is_required_for_every_data_service_intent(
    contract_document: dict[str, Any], section: str
) -> None:
    document = copy.deepcopy(contract_document)
    document[section]["transport_encryption"] = "OPTIONAL"
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    ("path", "value", "expected_code"),
    [
        (("execution_boundary", "activation_enabled"), True, "SAFE_BOUNDARY_VIOLATION"),
        (("execution_boundary", "activation_enabled"), 0, "TYPE_MISMATCH"),
        (
            ("relational_persistence_intent", "publicly_accessible"),
            True,
            "SAFE_BOUNDARY_VIOLATION",
        ),
        (
            ("relational_persistence_intent", "publicly_accessible"),
            0,
            "TYPE_MISMATCH",
        ),
    ],
)
def test_activation_public_access_and_bool_as_int_bypasses_are_rejected(
    contract_document: dict[str, Any],
    path: tuple[str, str],
    value: object,
    expected_code: str,
) -> None:
    document = copy.deepcopy(contract_document)
    document[path[0]][path[1]] = value
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == expected_code


@pytest.mark.parametrize(
    "field",
    (
        "network_access",
        "credential_access",
        "live_provider_calls",
        "external_writes",
        "migration_action",
        "backup_action",
        "restore_action",
        "redrive_action",
        "destructive_action",
        "deploy_action",
        "release_action",
        "production_action",
    ),
)
def test_every_execution_surface_remains_forbidden(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"][field] = "ALLOWED"
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize("command", generator.NATIVE_COMMANDS)
def test_every_native_operation_must_remain_forbidden(
    contract_document: dict[str, Any], command: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"]["commands"][command] = "ALLOWED"
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize("action", generator.ACTION_NAMES)
@pytest.mark.parametrize("value", [1, -1, True, "0"])
def test_planned_actions_require_exact_integer_zero(
    contract_document: dict[str, Any], action: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"]["planned_actions"][action] = value
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == (
        "SAFE_BOUNDARY_VIOLATION" if type(value) is int else "TYPE_MISMATCH"
    )


def test_unknown_fields_are_rejected_without_echoing_names_or_values(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    marker = "REJECTED_INPUT_MARKER_1502"
    document[marker] = marker
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"
    assert marker not in str(captured.value)


def test_nested_resource_like_unknown_field_is_rejected(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["relational_persistence_intent"]["resource"] = {"type": "aws_db_instance"}
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"


def test_yaml_duplicate_keys_fail_with_sanitized_error(tmp_path: Path) -> None:
    marker = "REJECTED_INPUT_MARKER_1502"
    path = tmp_path / "duplicate.yaml"
    path.write_text(f"document: safe\ndocument: {marker}\n", encoding="utf-8")
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.load_yaml(path)
    assert captured.value.code == "YAML_INVALID"
    assert marker not in str(captured.value)


def test_yaml_aliases_tags_and_multiple_documents_fail_closed(tmp_path: Path) -> None:
    cases = {
        "alias.yaml": "value: &blocked marker\ncopy: *blocked\n",
        "tag.yaml": "value: !!str marker\n",
        "documents.yaml": "value: safe\n---\nvalue: second\n",
    }
    expected = {
        "alias.yaml": "YAML_ALIAS_FORBIDDEN",
        "tag.yaml": "YAML_TAG_FORBIDDEN",
        "documents.yaml": "YAML_INVALID",
    }
    for name, content in cases.items():
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        with pytest.raises(generator.DataServicesContractError) as captured:
            generator.load_yaml(path)
        assert captured.value.code == expected[name]


def test_source_inventory_drift_fails_closed(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["sources"][0]["sha256"] = "0" * 64
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SOURCE_INVENTORY_DRIFT"


def test_predecessor_byte_drift_fails_closed(
    tmp_path: Path, contract_document: dict[str, Any]
) -> None:
    _copy_pinned_sources(tmp_path)
    predecessor = tmp_path / next(iter(generator.PREDECESSOR_SOURCES))
    predecessor.write_bytes(predecessor.read_bytes() + b"\n")
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == "SOURCE_DIGEST_MISMATCH"


@pytest.mark.parametrize(
    ("relative", "mutation"),
    [
        (
            "changes/st-1501/contracts/terraform-foundation.v1.yaml",
            "network_allowed",
        ),
        (
            "changes/st-1501/contracts/terraform-foundation.v1.yaml",
            "execution_field_omitted",
        ),
        (
            "changes/st-1501/contracts/terraform-foundation.v1.yaml",
            "eligible",
        ),
        (
            "changes/st-1501/contracts/terraform-foundation.v1.yaml",
            "aws_default",
        ),
        (
            "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
            "network_allowed",
        ),
        (
            "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
            "execution_field_omitted",
        ),
        (
            "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
            "eligible",
        ),
        (
            "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
            "aws_default",
        ),
    ],
)
def test_complete_predecessor_semantics_fail_after_digest_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    mutation: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    if path.suffix == ".json":
        predecessor = json.loads(path.read_bytes())
        execution = predecessor["activation"]
        admission = predecessor["provider_neutral_foundation_admission"]
        reference = predecessor["reference_architecture"]
    else:
        predecessor = yaml.safe_load(path.read_bytes())
        execution = predecessor["execution_boundary"]
        admission = predecessor["provider_neutral_foundation_admission"]
        reference = predecessor["reference_architecture"]
    if mutation == "network_allowed":
        execution["network_access"] = "ALLOWED"
    elif mutation == "execution_field_omitted":
        del execution["credential_access"]
    elif mutation == "eligible":
        admission["eligible"] = True
    else:
        reference["default"] = True
    if path.suffix == ".json":
        path.write_text(json.dumps(predecessor), encoding="utf-8")
    else:
        path.write_text(
            yaml.safe_dump(predecessor, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    document = copy.deepcopy(contract_document)
    _rebind_source(
        document=document,
        relative=relative,
        digest=generator.sha256_file(path),
        monkeypatch=monkeypatch,
    )
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_SEMANTIC_DRIFT"


def test_predecessor_handoff_drift_fails_after_digest_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = (
        "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml"
    )
    path = tmp_path / relative
    handoff = yaml.safe_load(path.read_bytes())
    handoff["security_and_approval_gates"][0] = "BYPASS_ALL_GATES"
    path.write_text(
        yaml.safe_dump(handoff, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    document = copy.deepcopy(contract_document)
    _rebind_source(
        document=document,
        relative=relative,
        digest=generator.sha256_file(path),
        monkeypatch=monkeypatch,
    )
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_SEMANTIC_DRIFT"


def test_predecessor_plan_byte_drift_fails_after_digest_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"
    path = tmp_path / relative
    plan = json.loads(path.read_bytes())
    path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    document = copy.deepcopy(contract_document)
    _rebind_source(
        document=document,
        relative=relative,
        digest=generator.sha256_file(path),
        monkeypatch=monkeypatch,
    )
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_GENERATED_DRIFT"


@pytest.mark.parametrize(
    "section",
    (
        "approved_story",
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
def test_every_normative_handoff_section_fails_after_digest_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    section: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = generator.DESIGN_HANDOFF_PATH.as_posix()
    path = tmp_path / relative
    handoff = yaml.safe_load(path.read_bytes())
    if section == "approved_story":
        handoff[section] = "ST-9999"
    elif section == "source_design_refs":
        handoff[section] = handoff[section][1:]
    elif section == "decision":
        handoff[section]["selected_profile"] = "AWS"
    elif section == "open_decision_state":
        handoff[section]["OD-013"]["resolved"] = True
    elif section == "security_and_approval_gates":
        handoff[section][0] = "BYPASS_ALL_SECURITY_AND_HUMAN_GATES"
    else:
        handoff[section].append("UNAUTHORIZED_NORMATIVE_MUTATION")
    path.write_text(
        yaml.safe_dump(handoff, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    document = copy.deepcopy(contract_document)
    _rebind_source(
        document=document,
        relative=relative,
        digest=generator.sha256_file(path),
        monkeypatch=monkeypatch,
    )
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code in {
        "HANDOFF_SEMANTIC_DRIFT",
        "FIXED_VALUE_VIOLATION",
        "SELECTION_MUST_REMAIN_UNSET",
        "SAFE_BOUNDARY_VIOLATION",
    }


def test_handoff_unknown_field_fails_after_digest_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = generator.DESIGN_HANDOFF_PATH.as_posix()
    path = tmp_path / relative
    handoff = yaml.safe_load(path.read_bytes())
    handoff["approval_bypass"] = True
    path.write_text(
        yaml.safe_dump(handoff, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    document = copy.deepcopy(contract_document)
    _rebind_source(
        document=document,
        relative=relative,
        digest=generator.sha256_file(path),
        monkeypatch=monkeypatch,
    )
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"


def test_contract_file_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.yaml"
    target.write_text("document: {}\n", encoding="utf-8")
    link = tmp_path / "contract.yaml"
    link.symlink_to(target)
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.load_yaml(link)
    assert captured.value.code == "UNSAFE_FILE_TYPE"


def test_pinned_source_ancestor_symlink_is_rejected_without_escape(
    tmp_path: Path, contract_document: dict[str, Any]
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == "UNSAFE_ANCESTOR"
    assert list(outside.iterdir()) == []
