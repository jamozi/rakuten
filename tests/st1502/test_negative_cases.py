"""Hostile and exact-type validation cases for ST-1502."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from scripts import build_st1502_data_services as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _validate(document: dict[str, Any]) -> generator.DataServicesModel:
    return generator.validate_contract(document, REPOSITORY_ROOT)


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


@pytest.mark.parametrize("field", generator.EXPECTED_SECTIONS["rds_intent"]["selected"])
def test_every_real_rds_value_must_remain_unset(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["rds_intent"]["selected"][field]
    document["rds_intent"]["selected"][field] = (
        ["selected"] if isinstance(current, list) else 1
    )
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize("field", ["port", "multi_az"])
@pytest.mark.parametrize("value", [True, False, 0, 1, "selected"])
def test_rds_port_and_multi_az_reject_bool_int_and_string_bypasses(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["rds_intent"]["selected"][field] = value
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize("role_index", range(len(generator.BUCKET_ROLES)))
@pytest.mark.parametrize("field", ["physical_name", "arn"])
def test_every_bucket_physical_identifier_is_rejected(
    contract_document: dict[str, Any], role_index: int, field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["s3_intent"]["roles"][role_index][field] = "REJECTED_INPUT_MARKER_1502"
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert "REJECTED_INPUT_MARKER_1502" not in str(captured.value)


@pytest.mark.parametrize("section", ["s3_intent", "sqs_intent"])
@pytest.mark.parametrize("mutation", ["duplicate", "reorder"])
def test_bucket_roles_and_queue_classes_reject_duplication_and_reordering(
    contract_document: dict[str, Any], section: str, mutation: str
) -> None:
    document = copy.deepcopy(contract_document)
    collection = "roles" if section == "s3_intent" else "classes"
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
def test_s3_destructive_retention_and_key_values_fail_closed(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["s3_intent"][field] = value
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code in {
        "FIXED_VALUE_VIOLATION",
        "SELECTION_MUST_REMAIN_UNSET",
    }


@pytest.mark.parametrize("field", generator._queue_selection())
def test_every_queue_physical_or_policy_choice_is_rejected(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["sqs_intent"]["classes"][0]["selected"][field] = (
        True if field == "fifo" else "REJECTED_INPUT_MARKER_1502"
    )
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert "REJECTED_INPUT_MARKER_1502" not in str(captured.value)


@pytest.mark.parametrize("queue_index", range(len(generator.QUEUE_CLASSES)))
def test_each_queue_must_keep_a_dlq_and_separated_roles(
    contract_document: dict[str, Any], queue_index: int
) -> None:
    for field in (
        "dlq",
        "producer_consumer_separation",
        "redrive_role_separation",
    ):
        document = copy.deepcopy(contract_document)
        document["sqs_intent"]["classes"][queue_index][field] = "OPTIONAL"
        with pytest.raises(generator.DataServicesContractError) as captured:
            _validate(document)
        assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("secrets_manager_intent", "secret_values", "PRESENT"),
        ("secrets_manager_intent", "secret_names", ["physical-secret"]),
        ("secrets_manager_intent", "secret_arns", ["physical-arn"]),
        ("secrets_manager_intent", "ambient_credential_resolution", "ALLOWED"),
        ("secrets_manager_intent", "environment_credential_resolution", "ALLOWED"),
        ("kms_intent", "key_ids", ["physical-key"]),
        ("kms_intent", "key_arns", ["physical-arn"]),
        ("kms_intent", "aliases", ["physical-alias"]),
        ("kms_intent", "policy_document", {"Statement": []}),
        ("kms_intent", "deletion_window_days", 7),
        ("kms_intent", "key_deletion", "ALLOWED"),
    ],
)
def test_secret_credential_and_kms_selections_are_rejected(
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
    ("path", "value", "expected_code"),
    [
        (("execution_boundary", "activation_enabled"), True, "SAFE_BOUNDARY_VIOLATION"),
        (("execution_boundary", "activation_enabled"), 0, "TYPE_MISMATCH"),
        (("rds_intent", "publicly_accessible"), True, "SAFE_BOUNDARY_VIOLATION"),
        (("rds_intent", "publicly_accessible"), 0, "TYPE_MISMATCH"),
        (
            ("execution_boundary", "live_provider_calls"),
            "ALLOWED",
            "FIXED_VALUE_VIOLATION",
        ),
        (("execution_boundary", "external_writes"), "ALLOWED", "FIXED_VALUE_VIOLATION"),
    ],
)
def test_activation_public_access_bool_as_int_and_external_actions_rejected(
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
    document["rds_intent"]["resource"] = {"type": "aws_db_instance"}
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


def test_yaml_aliases_are_forbidden_without_echoing_content(tmp_path: Path) -> None:
    marker = "REJECTED_INPUT_MARKER_1502"
    path = tmp_path / "alias.yaml"
    path.write_text(f"value: &blocked {marker}\ncopy: *blocked\n", encoding="utf-8")
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.load_yaml(path)
    assert captured.value.code == "YAML_ALIAS_FORBIDDEN"
    assert marker not in str(captured.value)


def test_source_inventory_drift_fails_closed(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["sources"][0]["sha256"] = "0" * 64
    with pytest.raises(generator.DataServicesContractError) as captured:
        _validate(document)
    assert captured.value.code == "SOURCE_INVENTORY_DRIFT"


def _copy_pinned_sources(target_root: Path) -> None:
    for relative in generator.PINNED_SOURCES:
        source = REPOSITORY_ROOT / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def test_predecessor_byte_drift_fails_closed(
    tmp_path: Path, contract_document: dict[str, Any]
) -> None:
    _copy_pinned_sources(tmp_path)
    predecessor = tmp_path / next(iter(generator.PREDECESSOR_SOURCES))
    predecessor.write_bytes(predecessor.read_bytes() + b"\n")
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == "SOURCE_DIGEST_MISMATCH"


def test_predecessor_semantic_drift_fails_even_if_digest_inventory_is_rebound(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"
    path = tmp_path / relative
    plan = json.loads(path.read_bytes())
    plan["activation"]["status"] = "ENABLED"
    path.write_text(json.dumps(plan), encoding="utf-8")
    new_digest = generator.sha256_file(path)
    predecessor_sources = dict(generator.PREDECESSOR_SOURCES)
    predecessor_sources[relative] = new_digest
    pinned_sources = {**generator.AUTHORITY_SOURCES, **predecessor_sources}
    monkeypatch.setattr(generator, "PREDECESSOR_SOURCES", predecessor_sources)
    monkeypatch.setattr(generator, "PINNED_SOURCES", pinned_sources)
    document = copy.deepcopy(contract_document)
    for row in document["sources"]:
        if row["uri"] == f"repo://{relative}":
            row["sha256"] = new_digest
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


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
