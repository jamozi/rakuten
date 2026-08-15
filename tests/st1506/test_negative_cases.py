"""Bounded hostile and fail-closed tests for ST-1506."""

from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import build_st1506_production_deployment as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MARKER = "REJECTED_INPUT_MARKER_1506"


def _validate(document: dict[str, Any]) -> generator.ProductionDeploymentModel:
    return generator.validate_contract(document, REPOSITORY_ROOT)


@pytest.mark.parametrize(
    "field",
    (
        "cloud_provider",
        "cloud_account_id",
        "cloud_region",
        "backup_region",
        "cross_border_policy",
        "state_backend",
        "github_repository",
        "github_ref",
        "github_workflow",
        "github_environment",
        "deployment_role",
        "credential_source",
        "credential_names",
        "provider_plugins",
        "external_action_references",
        "artifact_digest",
        "artifact_sbom_reference",
        "artifact_scan_reference",
        "artifact_provenance_reference",
        "release_id",
        "commit_sha",
        "contract_hash",
        "migration_version",
        "migration_task_reference",
        "canary_configuration",
        "canary_percentage",
        "canary_duration",
        "traffic_target",
        "telemetry_source",
        "error_budget_policy",
        "alert_policy",
        "notification_channels",
        "reviewers",
        "domain_names",
        "public_endpoint",
        "admin_endpoint",
        "internal_endpoint",
        "liveness_endpoint",
        "readiness_endpoint",
        "smoke_endpoint",
        "health_matcher",
        "rollback_artifact_digest",
        "rollback_configuration_version",
        "rollback_snapshot_id",
        "rollback_migration_version",
    ),
)
def test_every_selected_actual_value_must_remain_unset(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["selected_bindings"][field]
    document["selected_bindings"][field] = (
        [MARKER] if isinstance(current, list) else MARKER
    )
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    ("section", "field"),
    (
        ("production_budget", "selected_budget"),
        ("production_budget", "selected_acceptable_loss"),
        ("notification_channels", "selected_channels"),
        ("notification_channels", "selected_escalation_contacts"),
        ("production_region_and_data_residency", "selected_production_region"),
        ("production_region_and_data_residency", "selected_backup_region"),
        ("production_region_and_data_residency", "selected_cross_border_policy"),
        ("production_provider_credentials", "selected_accounts"),
        ("production_provider_credentials", "selected_permissions"),
        ("production_provider_credentials", "selected_credentials"),
        ("production_provider_credentials", "selected_secrets"),
    ),
)
def test_open_decision_values_cannot_be_selected(
    contract_document: dict[str, Any], section: str, field: str
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["open_decision_defaults"][section][field]
    document["open_decision_defaults"][section][field] = (
        [MARKER] if isinstance(current, list) else MARKER
    )
    with pytest.raises(generator.ProductionDeploymentContractError):
        _validate(document)


@pytest.mark.parametrize("artifact", generator.APPROVAL_ARTIFACT_NAMES)
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("artifact_value", MARKER),
        ("artifact_digest", "0" * 64),
        ("human_reviewer", "automation"),
        ("approval_status", "APPROVED"),
        ("approval_status", False),
    ),
)
def test_human_approval_artifacts_cannot_be_populated_or_forged(
    contract_document: dict[str, Any], artifact: str, field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["human_approval_gates"][artifact][field] = value
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        _validate(document)
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    "field",
    (
        "self_approval",
        "automation_as_approval",
        "synthesized_approval",
        "forged_approval",
        "shared_artifact_slots",
        "bypass",
        "override",
    ),
)
def test_approval_shortcuts_are_forbidden(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["human_approval_gates"][field] = "ALLOWED"
    with pytest.raises(generator.ProductionDeploymentContractError):
        _validate(document)


def test_approval_slots_must_remain_distinct(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["human_approval_gates"]["gate_report"]["artifact_type"] = document[
        "human_approval_gates"
    ]["release_decision"]["artifact_type"]
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == "APPROVAL_ARTIFACT_NOT_DISTINCT"


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        ("artifact_admission_intent", "immutable_digest", "OPTIONAL"),
        ("artifact_admission_intent", "sbom", "ABSENT"),
        ("artifact_admission_intent", "signed_provenance", "ABSENT"),
        ("artifact_admission_intent", "mutable_artifact", "ALLOWED"),
        ("artifact_admission_intent", "unbound_artifact", "ALLOWED"),
        ("protected_environment_intent", "protected_environment", "OPTIONAL"),
        ("protected_environment_intent", "exact_repository", "WILDCARD"),
        ("protected_environment_intent", "exact_ref", "WILDCARD"),
        ("protected_environment_intent", "exact_workflow", "WILDCARD"),
        ("protected_environment_intent", "repository_wildcard", "ALLOWED"),
        ("migration_intent", "execution", "ALLOWED"),
        ("migration_intent", "destructive_change", "ALLOWED"),
        ("migration_intent", "compatibility_gate", "NOT_REQUIRED"),
        ("canary_intent", "execution", "ALLOWED"),
        ("canary_intent", "traffic_mutation", "ALLOWED"),
        ("canary_intent", "automatic_advance", "ALLOWED"),
        ("canary_intent", "automatic_promotion", "ALLOWED"),
        ("observability_intent", "telemetry", "NOT_REQUIRED"),
        ("observability_intent", "error_budget", "NOT_REQUIRED"),
        ("observability_intent", "alerts", "NOT_REQUIRED"),
        ("health_and_smoke_intent", "execution", "ALLOWED"),
        ("health_and_smoke_intent", "endpoint_binding", "BOUND"),
        ("rollback_intent", "execution", "ALLOWED"),
        ("rollback_intent", "automatic_rollback", "ALLOWED"),
        ("rollback_intent", "migration_compatibility", "NOT_REQUIRED"),
    ),
)
def test_artifact_environment_migration_canary_and_rollback_cannot_be_weakened(
    contract_document: dict[str, Any], section: str, field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document[section][field] = value
    with pytest.raises(generator.ProductionDeploymentContractError):
        _validate(document)


@pytest.mark.parametrize("action", generator.ACTION_COUNT_NAMES)
@pytest.mark.parametrize("value", (1, True, 0.0, "0"))
def test_every_action_count_requires_exact_builtin_integer_zero(
    contract_document: dict[str, Any], action: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"]["action_counts"][action] = value
    with pytest.raises(generator.ProductionDeploymentContractError):
        _validate(document)


@pytest.mark.parametrize("mutation", ("missing", "extra"))
def test_action_count_inventory_is_closed(
    contract_document: dict[str, Any], mutation: str
) -> None:
    document = copy.deepcopy(contract_document)
    counts = document["execution_boundary"]["action_counts"]
    if mutation == "missing":
        counts.pop("status")
    else:
        counts["unexpected"] = 0
    with pytest.raises(generator.ProductionDeploymentContractError):
        _validate(document)


@pytest.mark.parametrize(
    "mutation", ("reorder", "remove", "extra", "enable", "advance", "count")
)
def test_logical_canary_observe_rollback_phases_are_exact_and_inert(
    contract_document: dict[str, Any], mutation: str
) -> None:
    document = copy.deepcopy(contract_document)
    phases = document["logical_phases"]
    if mutation == "reorder":
        phases[0], phases[1] = phases[1], phases[0]
    elif mutation == "remove":
        phases.pop()
    elif mutation == "extra":
        phases.append(copy.deepcopy(phases[-1]))
    elif mutation == "enable":
        phases[0]["status"] = "ENABLED"
    elif mutation == "advance":
        phases[0]["auto_advance"] = "ALLOWED"
    else:
        phases[0]["action_count"] = True
    with pytest.raises(generator.ProductionDeploymentContractError):
        _validate(document)


@pytest.mark.parametrize(
    "field",
    (
        "network_access",
        "credential_access",
        "live_provider_calls",
        "external_writes",
        "github_action",
        "aws_action",
        "iam_action",
        "deploy_action",
        "release_action",
        "production_action",
    ),
)
def test_every_external_execution_surface_remains_forbidden(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"][field] = "ALLOWED"
    with pytest.raises(generator.ProductionDeploymentContractError):
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
        with pytest.raises(generator.ProductionDeploymentContractError) as captured:
            _validate(document)
        assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    (
        (f"document: safe\ndocument: {MARKER}\n", "YAML_INVALID"),
        (f"value: &blocked {MARKER}\ncopy: *blocked\n", "YAML_ALIAS_FORBIDDEN"),
        (f"value: !!str {MARKER}\n", "YAML_TAG_FORBIDDEN"),
        (f"value: {{<<: {{nested: {MARKER}}}}}\n", "YAML_INVALID"),
        (f"document: safe\n---\ndocument: {MARKER}\n", "YAML_INVALID"),
    ),
)
def test_strict_yaml_rejects_duplicates_aliases_tags_and_multiple_documents(
    tmp_path: Path, payload: str, expected_code: str
) -> None:
    path = tmp_path / "hostile.yaml"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.load_yaml(path)
    assert captured.value.code == expected_code
    assert MARKER not in str(captured.value)


def test_json_duplicate_keys_and_nonregular_inputs_fail_sanitized(
    tmp_path: Path,
) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(f'{{"safe": 1, "safe": "{MARKER}"}}', encoding="utf-8")
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.load_json(path)
    assert captured.value.code == "JSON_DUPLICATE_KEY"
    assert MARKER not in str(captured.value)
    fifo = tmp_path / "fifo"
    fifo.mkdir()
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.load_yaml(fifo)
    assert captured.value.code == "UNSAFE_FILE_TYPE"


@pytest.mark.parametrize(
    ("suffix", "loader", "expected_code"),
    (
        ("yaml", generator.load_yaml, "YAML_SIZE_LIMIT"),
        ("json", generator.load_json, "JSON_SIZE_LIMIT"),
    ),
)
def test_oversized_regular_inputs_fail_before_any_payload_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    loader: Any,
    expected_code: str,
) -> None:
    path = tmp_path / f"oversized.{suffix}"
    with path.open("wb") as stream:
        stream.truncate(generator.MAX_DOCUMENT_BYTES + 1)

    def forbidden_read(_descriptor: int, _size: int) -> bytes:
        raise AssertionError("oversized payload must not be read")

    monkeypatch.setattr(generator.os, "read", forbidden_read)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        loader(path)
    assert captured.value.code == expected_code


def test_oversized_exact_authority_fails_before_any_payload_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = Path("authority.yaml")
    path = tmp_path / relative
    with path.open("wb") as stream:
        stream.truncate(2)

    def forbidden_read(_descriptor: int, _size: int) -> bytes:
        raise AssertionError("oversized authority must not be read")

    monkeypatch.setattr(generator.os, "read", forbidden_read)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._load_exact_authority_document(
            tmp_path,
            relative,
            expected_bytes=1,
            expected_sha256="0" * 64,
            root_key="DESIGN_HANDOFF_V1",
            field="implementation_handoff",
        )
    assert captured.value.code == "IMPLEMENTATION_AUTHORITY_BYTES_MISMATCH"


def _copy_pinned_sources(target_root: Path) -> None:
    live_handoff_only_sources = (
        "AGENTS.md",
        "docs/canonical/08_codex/AGENTS.md",
    )
    for relative in dict.fromkeys(
        (*generator.PINNED_SOURCES, *live_handoff_only_sources)
    ):
        source = REPOSITORY_ROOT / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


@pytest.mark.parametrize(
    ("relative", "expected_code"),
    (
        (
            generator.STANDING_DEVELOPMENT_AUTHORITY_PATH,
            "CURRENT_DEVELOPMENT_AUTHORITY_DRIFT",
        ),
        (
            Path("docs/execplans/RAOS-IMPLEMENTATION-FIRST.md"),
            "CURRENT_DEVELOPMENT_SOURCE_DRIFT",
        ),
    ),
)
def test_current_development_binding_drift_fails_closed_without_echoing_bytes(
    tmp_path: Path,
    contract_document: dict[str, Any],
    relative: Path,
    expected_code: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + f"\n{MARKER}\n".encode())
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == expected_code
    assert MARKER not in str(captured.value)


def test_current_development_policy_rejects_bool_as_zero_action_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = copy.deepcopy(generator.CURRENT_DEVELOPMENT_REBINDING_POLICY)
    policy["action_count"] = True
    monkeypatch.setattr(generator, "CURRENT_DEVELOPMENT_REBINDING_POLICY", policy)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._validate_current_development_rebinding_policy()
    _assert_exact_value_free_diagnostic(
        captured.value,
        code="TYPE_MISMATCH",
        field="current_development_rebinding.action_count",
        rejected_value=True,
    )


def _rebind_immediate_predecessor(
    document: dict[str, Any],
    relative: str,
    digest: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predecessor_sources = dict(generator.PREDECESSOR_SOURCES)
    predecessor_sources[relative] = digest
    monkeypatch.setattr(generator, "PREDECESSOR_SOURCES", predecessor_sources)
    monkeypatch.setattr(
        generator,
        "PINNED_SOURCES",
        {
            **generator.AUTHORITY_SOURCES,
            **generator.IMPLEMENTATION_AUTHORITY_SOURCES,
            **predecessor_sources,
        },
    )
    for row in document["sources"]:
        if row["uri"] == f"repo://{relative}":
            row["sha256"] = digest
            break
    else:
        raise AssertionError("source row missing")
    binding_key = (
        "contract_sha256" if relative.endswith(".yaml") else "reference_plan_sha256"
    )
    document["predecessor_binding"][binding_key] = digest


@pytest.mark.parametrize(
    ("relative", "mutation"),
    (
        ("changes/st-1505/contracts/staging-deployment.v1.yaml", "enabled"),
        ("changes/st-1505/contracts/staging-deployment.v1.yaml", "nonzero"),
        ("changes/st-1505/contracts/staging-deployment.v1.yaml", "selected"),
        ("changes/st-1505/contracts/staging-deployment.v1.yaml", "external"),
        ("changes/st-1505/contracts/staging-deployment.v1.yaml", "tst009"),
        ("changes/st-1505/contracts/staging-deployment.v1.yaml", "tst022"),
        (
            "infra/terraform/staging/staging-deployment.reference-plan.v1.json",
            "executable",
        ),
        (
            "infra/terraform/staging/staging-deployment.reference-plan.v1.json",
            "enabled",
        ),
    ),
)
def test_st1505_semantic_drift_fails_even_after_digest_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    mutation: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    if relative.endswith(".yaml"):
        value = yaml.safe_load(path.read_bytes())
        if mutation == "enabled":
            value["execution_boundary"]["activation_enabled"] = True
        elif mutation == "nonzero":
            value["execution_boundary"]["action_counts"]["deploy"] = 1
        elif mutation == "selected":
            value["selected_bindings"]["github_repository"] = "attempted/repo"
        elif mutation == "external":
            value["execution_boundary"]["external_writes"] = "ALLOWED"
        elif mutation == "tst009":
            value["evidence_boundary"]["formal_tst_009"] = "EXECUTED"
        else:
            value["evidence_boundary"]["formal_tst_022"] = "EXECUTED"
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    else:
        value = json.loads(path.read_bytes())
        if mutation == "executable":
            value["document"]["executable"] = True
        else:
            value["activation"]["enabled"] = True
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    document = copy.deepcopy(contract_document)
    _rebind_immediate_predecessor(
        document, relative, generator.sha256_file(path), monkeypatch
    )
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code in {
        "IMPLEMENTATION_HANDOFF_SOURCE_DRIFT",
        "PREDECESSOR_SEMANTIC_DRIFT",
        "CONTRACT_DEFINITION_DRIFT",
    }


@pytest.mark.parametrize("mutation", ("missing", "reorder", "extra"))
def test_st1505_transitive_binding_inventory_drift_is_rejected(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = "changes/st-1505/contracts/staging-deployment.v1.yaml"
    path = tmp_path / relative
    value = yaml.safe_load(path.read_bytes())
    bindings = value["predecessor_bindings"]
    if mutation == "missing":
        bindings.pop("deployment_identity")
    elif mutation == "extra":
        bindings["unexpected"] = copy.deepcopy(bindings["data_services"])
    else:
        value["predecessor_bindings"] = {
            "compute_edge": bindings["compute_edge"],
            "data_services": bindings["data_services"],
            "deployment_identity": bindings["deployment_identity"],
        }
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    document = copy.deepcopy(contract_document)
    _rebind_immediate_predecessor(
        document, relative, generator.sha256_file(path), monkeypatch
    )
    with pytest.raises(generator.ProductionDeploymentContractError):
        generator.validate_contract(document, tmp_path)


@pytest.mark.parametrize(
    ("relative", "expected_code"),
    (
        (
            "changes/st-1505/contracts/staging-deployment.v1.yaml",
            "IMPLEMENTATION_HANDOFF_SOURCE_DRIFT",
        ),
        (
            "infra/terraform/staging/staging-deployment.reference-plan.v1.json",
            "SOURCE_DIGEST_MISMATCH",
        ),
    ),
)
def test_immediate_predecessor_byte_drift_fails_closed(
    tmp_path: Path,
    contract_document: dict[str, Any],
    relative: str,
    expected_code: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == expected_code


def test_source_order_symlink_ancestor_and_escaped_path_fail_closed(
    tmp_path: Path, contract_document: dict[str, Any]
) -> None:
    document = copy.deepcopy(contract_document)
    document["sources"][0], document["sources"][1] = (
        document["sources"][1],
        document["sources"][0],
    )
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == "SOURCE_INVENTORY_DRIFT"

    isolated = tmp_path / "isolated"
    isolated.mkdir()
    for relative in (
        generator.HANDOFF_PATH,
        generator.APPROVAL_PATH,
        Path("AGENTS.md"),
    ):
        source = REPOSITORY_ROOT / relative
        target = isolated / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    outside = tmp_path / "outside"
    outside.mkdir()
    (isolated / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), isolated)
    assert captured.value.code == "UNSAFE_ANCESTOR"
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._read_repository_file(
            REPOSITORY_ROOT,
            Path("../escape"),
            "hostile",
            max_bytes=1,
            size_error_code="FILE_SIZE_LIMIT",
        )
    assert captured.value.code == "UNSAFE_REPOSITORY_PATH"


@pytest.mark.parametrize(
    "collision_field",
    (
        "size_error_code",
        "path_error_code",
        "ancestor_error_code",
        "file_type_error_code",
    ),
)
def test_optional_repository_read_rejects_internal_error_code_collisions(
    tmp_path: Path,
    collision_field: str,
) -> None:
    hostile = tmp_path / "hostile"
    hostile.write_bytes(b"present")
    error_codes = {
        "size_error_code": "FILE_SIZE_LIMIT",
        "path_error_code": "UNSAFE_REPOSITORY_PATH",
        "ancestor_error_code": "UNSAFE_ANCESTOR",
        "file_type_error_code": "UNSAFE_FILE_TYPE",
    }
    error_codes[collision_field] = generator.OPTIONAL_MISSING_ERROR_CODE

    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._read_optional_repository_file(
            tmp_path,
            Path("hostile"),
            "hostile_optional_read",
            max_bytes=0,
            **error_codes,
        )
    _assert_exact_value_free_diagnostic(
        captured.value,
        code="OPTIONAL_ERROR_CODE_COLLISION",
        field="hostile_optional_read",
        rejected_value=generator.OPTIONAL_MISSING_ERROR_CODE,
    )


def _set_interface_value(
    document: dict[str, Any], path: tuple[str, ...], value: object
) -> None:
    current: dict[str, Any] = document["wordpress_signed_delivery_interface"]
    for part in path[:-1]:
        nested = current[part]
        assert isinstance(nested, dict)
        current = nested
    current[path[-1]] = value


def _get_interface_value(document: Mapping[str, Any], path: tuple[str, ...]) -> object:
    current: object = document["wordpress_signed_delivery_interface"]
    for part in path:
        assert isinstance(current, Mapping)
        current = current[part]
    return current


def _expected_ordered_diagnostic(
    actual: object, expected: object, field: str
) -> tuple[str, str]:
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping) or not all(
            type(key) is str for key in actual
        ):
            return "TYPE_MISMATCH", field
        if tuple(actual) != tuple(expected):
            return "CLOSED_SCHEMA_VIOLATION", field
        for key, expected_value in expected.items():
            if actual[key] != expected_value:
                return _expected_ordered_diagnostic(
                    actual[key], expected_value, f"{field}.{key}"
                )
        raise AssertionError("mutation did not change the expected mapping")
    if type(expected) is list:
        if type(actual) is not list:
            return "TYPE_MISMATCH", field
        if len(actual) != len(expected):
            return "FIXED_VALUE_VIOLATION", field
        for actual_item, expected_item in zip(actual, expected, strict=True):
            if actual_item != expected_item:
                return _expected_ordered_diagnostic(
                    actual_item, expected_item, f"{field}.item"
                )
        raise AssertionError("mutation did not change the expected list")
    if expected is None:
        if actual is not None:
            return "SELECTION_MUST_REMAIN_UNSET", field
        raise AssertionError("mutation did not change the expected null")
    if type(actual) is not type(expected):
        return "TYPE_MISMATCH", field
    if actual != expected:
        if type(expected) is bool or (type(expected) is int and expected == 0):
            return "SAFE_BOUNDARY_VIOLATION", field
        return "FIXED_VALUE_VIOLATION", field
    raise AssertionError("mutation did not change the expected scalar")


def _assert_exact_value_free_diagnostic(
    error: generator.ProductionDeploymentContractError,
    *,
    code: str,
    field: str,
    rejected_value: object,
) -> None:
    expected_message = f"{code} field={field}"
    assert error.code == code
    assert error.field == field
    assert error.args == (expected_message,)
    assert str(error) == expected_message
    assert vars(error) == {"code": code, "field": field}
    rejected_serialization = json.dumps(
        rejected_value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert rejected_serialization not in expected_message


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("trust_bootstrap", "origin_aliases"), "ALLOWED"),
        (("trust_bootstrap", "cross_origin_redirect"), "ALLOWED"),
        (("trust_bootstrap", "caller_supplied_artifact_url"), "ALLOWED"),
        (("trust_bootstrap", "pinned_update_service_origin"), MARKER),
        (("trust_bootstrap", "pinned_offline_root_algorithm"), "RSA"),
        (("trust_bootstrap", "root_key_remote_rotation"), "ALLOWED"),
        (("canonical_encoding", "format"), "ORDINARY_JSON"),
        (("canonical_encoding", "duplicate_keys"), "ALLOW"),
        (("canonical_encoding", "floating_point_values"), "ALLOWED"),
        (("canonical_encoding", "nonfinite_values"), "ALLOWED"),
        (("canonical_encoding", "unknown_fields"), "ALLOW"),
        (("canonical_encoding", "unknown_schema_versions"), "ALLOW"),
        (("keyring", "schema"), "RAOS_WP_KEYRING_V2"),
        (("keyring", "signer"), "ROUTINE_RELEASE_KEY"),
        (("keyring", "persisted_high_water_required"), False),
        (("keyring", "equal_or_lower_epoch"), "ACCEPT"),
        (("keyring", "allowed_algorithm"), "RSA"),
        (("keyring", "required_release_purposes"), ["RELEASE_SIGNER"]),
        (("release_set", "schema"), "RAOS_WP_RELEASE_SET_V2"),
        (("release_set", "signature_requirement"), "ONE_SIGNATURE"),
        (("release_set", "required_signature_purposes"), ["RELEASE_SIGNER"]),
        (("release_set", "release_sequence"), "SEMANTIC_VERSION"),
        (("release_set", "semantic_version_as_replay_control"), "ALLOWED"),
        (("release_set", "timestamp_as_sole_replay_control"), "ALLOWED"),
        (("release_set", "unsigned_digest_only_package"), "ALLOWED"),
        (("release_set", "exact_limits"), {"expanded_bytes": 2**63}),
        (("components", "allowed_kinds"), ["WORDPRESS_COMPANION_PLUGIN"]),
        (("components", "coupled_components_default"), "INDEPENDENT"),
        (
            (
                "components",
                "independent_release_requires_declared_no_dependency_and_hostile_compatibility_proof",
            ),
            False,
        ),
        (("components", "mixed_release_set"), "ALLOWED"),
        (("package_admission", "transport"), "CALLER_SUPPLIED_URL"),
        (("package_admission", "certificate_and_hostname_validation"), "OPTIONAL"),
        (("package_admission", "redirect"), "ALLOWED"),
        (("package_admission", "exact_limits"), {"member_count": 2**31}),
        (
            ("package_admission", "post_extraction_exact_inventory_revalidation"),
            "OPTIONAL",
        ),
        (("package_admission", "time_of_check_time_of_use_replacement"), "ACCEPT"),
        (("replay_and_journal", "sequence_consumed_before_filesystem_mutation"), False),
        (("replay_and_journal", "failed_or_interrupted_sequence_reuse"), "ALLOWED"),
        (("replay_and_journal", "equal_or_lower_release_sequence"), "ACCEPT"),
        (("replay_and_journal", "restored_database_may_lower_high_water"), True),
        (("replay_and_journal", "uncertain_high_water_result"), "CONTINUE"),
        (("replay_and_journal", "blind_retry"), "ALLOWED"),
        (("transaction_state_machine", "initial_state"), "PREPARED"),
        (("transaction_state_machine", "runtime_transition_execution"), "ALLOWED"),
        (("transaction_state_machine", "stage_all_components_before_switch"), False),
        (("transaction_state_machine", "durable_prepared_state_required"), False),
        (("transaction_state_machine", "concurrent_update"), "CONTINUE"),
        (("transaction_state_machine", "partial_switch"), "CONTINUE"),
        (("transaction_state_machine", "journal_corruption"), "IGNORE"),
        (("transaction_state_machine", "automatic_advance"), "ALLOWED"),
        (("wordpress_filesystem", "atomicity_assumption"), "ALLOWED"),
        (("wordpress_filesystem", "direct_filesystem_method"), "direct"),
        (("wordpress_filesystem", "ssh_or_ssh_backed_filesystem"), "ALLOWED"),
        (("health_and_restore", "failed_new_release_restore_attempt_limit"), 2),
        (("health_and_restore", "restore_source"), "REMOTE_DOWNGRADE"),
        (("health_and_restore", "remotely_supplied_downgrade"), "ALLOWED"),
        (("health_and_restore", "restore_may_reduce_high_water"), True),
        (("health_and_restore", "failed_or_ambiguous_restore_result"), "RETRY"),
        (("health_and_restore", "further_automatic_write_after_restore"), "ALLOWED"),
        (("authorization", "authentication_transport"), "WORDPRESS_PASSWORD_OVER_HTTP"),
        (("authorization", "update_and_content_identities_distinct"), "OPTIONAL"),
        (("authorization", "custom_minimal_roles"), "ADMINISTRATOR"),
        (("authorization", "update_custom_capability"), "activate_plugins"),
        (("authorization", "route_level_permission_callback"), "ALLOW_ALL"),
        (("authorization", "update_identity_general_post_edit_or_publish"), "ALLOWED"),
        (
            ("authorization", "update_identity_general_plugin_theme_user_option_admin"),
            "ALLOWED",
        ),
        (("authorization", "arbitrary_url_file_path_code_or_version_input"), "ALLOWED"),
        (("authorization", "request_shape"), "ARBITRARY_PAYLOAD"),
        (
            (
                "authorization",
                "credential_values_in_repository_prompt_package_log_or_receipt",
            ),
            "ALLOWED",
        ),
        (("availability", "update_service_is_request_serving_dependency"), True),
        (("availability", "outage_result"), "USE_FALLBACK"),
        (("availability", "retry_storm"), "ALLOWED"),
        (("availability", "fallback_origin_or_mirror"), "ALLOWED"),
        (("availability", "unsigned_cached_package"), "ALLOWED"),
        (("automatic_delivery_classification", "current_authority"), "AUTOMATIC"),
        (("automatic_delivery_classification", "default"), "AUTOMATIC"),
        (("automatic_delivery_classification", "unknown_classification"), "AUTOMATIC"),
        (("receipts", "tamper_evident_required"), False),
        (("receipts", "sanitized_required"), False),
        (("receipts", "retention"), "30_DAYS"),
        (("control_plane_separation", "code_delivery_may_publish_content"), True),
        (("control_plane_separation", "publication_may_trigger_deployment"), True),
        (("control_plane_separation", "identities_separate"), False),
        (("control_plane_separation", "queues_separate"), False),
        (("control_plane_separation", "state_machines_separate"), False),
        (("control_plane_separation", "receipts_separate"), False),
        (("control_plane_separation", "kill_switches_separate"), False),
        (
            (
                "control_plane_separation",
                "failed_code_delivery_may_modify_public_content",
            ),
            True,
        ),
        (("evidence_boundary", "live_wordpress"), "EXECUTED"),
        (("evidence_boundary", "production"), "EXECUTED"),
    ),
)
def test_signed_delivery_hostile_policy_mutations_fail_closed(
    contract_document: dict[str, Any], path: tuple[str, ...], value: object
) -> None:
    expected_value = _get_interface_value(contract_document, path)
    expected_code, expected_field = _expected_ordered_diagnostic(
        value,
        expected_value,
        f"wordpress_signed_delivery_interface.{'.'.join(path)}",
    )
    document = copy.deepcopy(contract_document)
    _set_interface_value(document, path, value)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        _validate(document)
    _assert_exact_value_free_diagnostic(
        captured.value,
        code=expected_code,
        field=expected_field,
        rejected_value=value,
    )


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("interface_status", "action_count"), True),
        (("interface_status", "action_count"), 0.0),
        (("interface_status", "action_count"), "0"),
        (("interface_status", "executable"), 0),
        (("interface_status", "activation_status"), " DISABLED"),
        (("interface_status", "activation_status"), "disabled"),
        (("keyring", "persisted_high_water_required"), 1),
        (("health_and_restore", "failed_new_release_restore_attempt_limit"), True),
        (("health_and_restore", "failed_new_release_restore_attempt_limit"), 1.0),
        (("health_and_restore", "failed_new_release_restore_attempt_limit"), "1"),
    ),
)
def test_signed_delivery_wrong_shape_case_padding_and_boolean_integer_fail(
    contract_document: dict[str, Any], path: tuple[str, ...], value: object
) -> None:
    expected_value = _get_interface_value(contract_document, path)
    expected_code, expected_field = _expected_ordered_diagnostic(
        value,
        expected_value,
        f"wordpress_signed_delivery_interface.{'.'.join(path)}",
    )
    document = copy.deepcopy(contract_document)
    _set_interface_value(document, path, value)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        _validate(document)
    _assert_exact_value_free_diagnostic(
        captured.value,
        code=expected_code,
        field=expected_field,
        rejected_value=value,
    )


@pytest.mark.parametrize("mutation", ("missing", "extra", "reorder"))
def test_every_signed_delivery_mapping_is_closed_and_ordered(
    contract_document: dict[str, Any], mutation: str
) -> None:
    document = copy.deepcopy(contract_document)
    interface = document["wordpress_signed_delivery_interface"]
    status = interface["interface_status"]
    if mutation == "missing":
        status.pop("credential_access")
    elif mutation == "extra":
        status[MARKER] = MARKER
    else:
        first = status.pop("classification")
        status["classification"] = first
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        _validate(document)
    _assert_exact_value_free_diagnostic(
        captured.value,
        code="CLOSED_SCHEMA_VIOLATION",
        field="wordpress_signed_delivery_interface.interface_status",
        rejected_value=status,
    )


@pytest.mark.parametrize("mutation", ("missing", "extra", "reorder"))
def test_archive_rejection_and_signature_purpose_inventories_are_exact(
    contract_document: dict[str, Any], mutation: str
) -> None:
    for section, field in (
        ("package_admission", "reject_entries"),
        ("release_set", "required_signature_purposes"),
        ("keyring", "required_release_purposes"),
    ):
        document = copy.deepcopy(contract_document)
        values = document["wordpress_signed_delivery_interface"][section][field]
        expected_values = copy.deepcopy(values)
        if mutation == "missing":
            values.pop()
        elif mutation == "extra":
            values.append(MARKER)
        else:
            values[0], values[1] = values[1], values[0]
        with pytest.raises(generator.ProductionDeploymentContractError) as captured:
            _validate(document)
        expected_code, expected_field = _expected_ordered_diagnostic(
            values,
            expected_values,
            f"wordpress_signed_delivery_interface.{section}.{field}",
        )
        _assert_exact_value_free_diagnostic(
            captured.value,
            code=expected_code,
            field=expected_field,
            rejected_value=values,
        )


def _rebind_implementation_authority(
    document: dict[str, Any],
    relative: str,
    digest: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    implementation_sources = dict(generator.IMPLEMENTATION_AUTHORITY_SOURCES)
    implementation_sources[relative] = digest
    monkeypatch.setattr(
        generator, "IMPLEMENTATION_AUTHORITY_SOURCES", implementation_sources
    )
    monkeypatch.setattr(
        generator,
        "PINNED_SOURCES",
        {
            **generator.AUTHORITY_SOURCES,
            **implementation_sources,
            **generator.PREDECESSOR_SOURCES,
        },
    )
    for row in document["sources"]:
        if row["uri"] == f"repo://{relative}":
            row["sha256"] = digest
            return
    raise AssertionError("implementation authority source row missing")


@pytest.mark.parametrize("kind", ("handoff", "approval"))
def test_authority_semantic_drift_fails_after_digest_and_size_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    if kind == "handoff":
        relative = generator.HANDOFF_PATH.as_posix()
        path = tmp_path / generator.HANDOFF_PATH
        value = yaml.safe_load(path.read_bytes())
        value["DESIGN_HANDOFF_V1"]["approved_story"] = "ST-9999"
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
        monkeypatch.setattr(generator, "HANDOFF_BYTES", path.stat().st_size)
        monkeypatch.setattr(generator, "HANDOFF_SHA256", generator.sha256_file(path))
        expected_code = "IMPLEMENTATION_HANDOFF_SEMANTIC_DRIFT"
    else:
        relative = generator.APPROVAL_PATH.as_posix()
        path = tmp_path / generator.APPROVAL_PATH
        value = yaml.safe_load(path.read_bytes())
        value["DESIGN_HANDOFF_APPROVAL_V1"]["status"] = "REVOKED"
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
        monkeypatch.setattr(generator, "APPROVAL_BYTES", path.stat().st_size)
        monkeypatch.setattr(generator, "APPROVAL_SHA256", generator.sha256_file(path))
        expected_code = "IMPLEMENTATION_APPROVAL_SEMANTIC_DRIFT"
    document = copy.deepcopy(contract_document)
    _rebind_implementation_authority(
        document, relative, generator.sha256_file(path), monkeypatch
    )
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == expected_code


@pytest.mark.parametrize("relative", (generator.HANDOFF_PATH, generator.APPROVAL_PATH))
def test_authority_byte_drift_fails_before_parse_with_value_free_error(
    tmp_path: Path,
    contract_document: dict[str, Any],
    relative: Path,
) -> None:
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + f"\n# {MARKER}\n".encode())
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == "IMPLEMENTATION_AUTHORITY_BYTES_MISMATCH"
    assert MARKER not in str(captured.value)


def test_contract_object_and_captured_bytes_cannot_diverge(
    contract_document: dict[str, Any],
) -> None:
    content = (REPOSITORY_ROOT / generator.CONTRACT_PATH).read_bytes()
    mismatched = content.replace(b"version: 1.1.0", b"version: 1.2.0", 1)
    assert mismatched != content
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(
            copy.deepcopy(contract_document),
            REPOSITORY_ROOT,
            contract_content=mismatched,
        )
    _assert_exact_value_free_diagnostic(
        captured.value,
        code="CONTRACT_CONTENT_MISMATCH",
        field="contract_content",
        rejected_value="1.2.0",
    )
