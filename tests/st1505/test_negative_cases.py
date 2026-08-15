"""Bounded hostile and fail-closed tests for ST-1505."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import build_st1505_staging_deployment as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MARKER = "REJECTED_INPUT_MARKER_1505"


def _validate(document: dict[str, Any]) -> generator.StagingDeploymentModel:
    return generator.validate_contract(document, REPOSITORY_ROOT)


@pytest.mark.parametrize("field", generator._selected_bindings())
def test_every_selected_physical_runtime_and_release_value_must_remain_unset(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["selected_bindings"][field]
    document["selected_bindings"][field] = (
        [MARKER] if isinstance(current, list) else MARKER
    )
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("reorder", "FIXED_VALUE_VIOLATION"),
        ("duplicate", "FIXED_VALUE_VIOLATION"),
        ("remove", "FIXED_VALUE_VIOLATION"),
        ("status", "FIXED_VALUE_VIOLATION"),
        ("execution", "FIXED_VALUE_VIOLATION"),
        ("external", "FIXED_VALUE_VIOLATION"),
        ("nonzero", "SAFE_BOUNDARY_VIOLATION"),
        ("bool", "TYPE_MISMATCH"),
    ],
)
def test_phase_order_identity_disabled_state_and_integer_zero_are_exact(
    contract_document: dict[str, Any], mutation: str, expected_code: str
) -> None:
    document = copy.deepcopy(contract_document)
    phases = document["logical_phases"]
    if mutation == "reorder":
        phases[0], phases[1] = phases[1], phases[0]
    elif mutation == "duplicate":
        phases[1]["name"] = phases[0]["name"]
    elif mutation == "remove":
        phases.pop()
    elif mutation == "status":
        phases[0]["status"] = "ENABLED"
    elif mutation == "execution":
        phases[0]["execution_status"] = "EXECUTED"
    elif mutation == "external":
        phases[0]["external_action"] = "ALLOWED"
    elif mutation == "nonzero":
        phases[0]["action_count"] = 1
    else:
        phases[0]["action_count"] = False
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == expected_code


@pytest.mark.parametrize("action", generator.ACTION_COUNT_NAMES)
@pytest.mark.parametrize("value", [1, True])
def test_every_action_count_requires_exact_integer_zero(
    contract_document: dict[str, Any], action: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"]["action_counts"][action] = value
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == (
        "SAFE_BOUNDARY_VIOLATION" if type(value) is int else "TYPE_MISMATCH"
    )


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("activation_enabled", True, "SAFE_BOUNDARY_VIOLATION"),
        ("activation_enabled", 0, "TYPE_MISMATCH"),
        ("activation_status", "ENABLED", "FIXED_VALUE_VIOLATION"),
        ("runtime_status", "EXECUTED", "FIXED_VALUE_VIOLATION"),
        ("network_access", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("credential_access", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("live_provider_calls", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("external_writes", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("staging_action", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("release_action", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("production_action", "ALLOWED", "FIXED_VALUE_VIOLATION"),
    ],
)
def test_activation_and_all_external_boundaries_fail_closed(
    contract_document: dict[str, Any],
    field: str,
    value: object,
    expected_code: str,
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"][field] = value
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == expected_code


@pytest.mark.parametrize("operation", generator.OPERATION_NAMES)
def test_every_runtime_operation_remains_forbidden(
    contract_document: dict[str, Any], operation: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"]["operations"][operation] = "ALLOWED"
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("immutable_digest", "OPTIONAL"),
        ("sbom", "ABSENT"),
        ("vulnerability_scan", "ABSENT"),
        ("signed_provenance", "ABSENT"),
        ("promote_without_rebuild", "NOT_REQUIRED"),
        ("mutable_artifact", "ALLOWED"),
        ("rebuild_between_environments", "ALLOWED"),
    ],
)
def test_mutable_rebuilt_or_incomplete_supply_chain_artifact_is_rejected(
    contract_document: dict[str, Any], field: str, value: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["artifact_admission_intent"][field] = value
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    "field",
    ["immutable_digest", "sbom", "vulnerability_scan", "signed_provenance"],
)
def test_missing_supply_chain_requirement_is_a_closed_schema_failure(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["artifact_admission_intent"].pop(field)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("strategy", "CONTRACT_FIRST"),
        ("contract", "CURRENT_RELEASE"),
        ("destructive_contract_current_release", "ALLOWED"),
        ("contract_before_expand", "ALLOWED"),
        ("direct_ddl", "ALLOWED"),
        ("down_migration_primary_recovery", "ALLOWED"),
        ("external_api_during_migration", "ALLOWED"),
    ],
)
def test_destructive_contract_first_direct_ddl_down_and_external_migration_fail(
    contract_document: dict[str, Any], field: str, value: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["migration_intent"][field] = value
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("health_and_smoke_intent", "infer_readiness_from_generic_http_200", "ALLOWED"),
        (
            "health_and_smoke_intent",
            "public_admin_internal_isolation_check",
            "NOT_REQUIRED",
        ),
        ("health_and_smoke_intent", "dependency_check", "NOT_REQUIRED"),
        ("health_and_smoke_intent", "migration_compatibility_check", "NOT_REQUIRED"),
        ("rollback_intent", "execution", "ALLOWED"),
        ("rollback_intent", "prior_immutable_artifact", "NOT_REQUIRED"),
        ("rollback_intent", "prior_configuration", "NOT_REQUIRED"),
        ("rollback_intent", "known_safe_snapshot", "NOT_REQUIRED"),
        ("rollback_intent", "migration_compatibility", "NOT_REQUIRED"),
        ("rollback_intent", "pitr_for_ordinary_application_error", "ALLOWED"),
    ],
)
def test_readiness_isolation_and_declarative_rollback_cannot_be_weakened(
    contract_document: dict[str, Any], section: str, field: str, value: str
) -> None:
    document = copy.deepcopy(contract_document)
    document[section][field] = value
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


def test_unknown_fields_are_rejected_without_echoing_names_or_values(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document[MARKER] = MARKER
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (f"document: safe\ndocument: {MARKER}\n", "YAML_INVALID"),
        (f"value: &blocked {MARKER}\ncopy: *blocked\n", "YAML_ALIAS_FORBIDDEN"),
        (f"value: !!python/object/apply:builtins.str [{MARKER}]\n", "YAML_INVALID"),
    ],
)
def test_yaml_duplicate_alias_and_unsafe_tag_fail_sanitized(
    tmp_path: Path, payload: str, expected_code: str
) -> None:
    path = tmp_path / "hostile.yaml"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.load_yaml(path)
    assert captured.value.code == expected_code
    assert MARKER not in str(captured.value)


def test_json_duplicate_keys_fail_with_sanitized_error(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(f'{{"safe": 1, "safe": "{MARKER}"}}', encoding="utf-8")
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.load_json(path)
    assert captured.value.code == "JSON_DUPLICATE_KEY"
    assert MARKER not in str(captured.value)


def test_source_inventory_digest_duplicate_and_reordering_fail_closed(
    contract_document: dict[str, Any],
) -> None:
    for mutation in ("digest", "duplicate", "reorder"):
        document = copy.deepcopy(contract_document)
        if mutation == "digest":
            document["sources"][0]["sha256"] = "0" * 64
        elif mutation == "duplicate":
            document["sources"][1] = copy.deepcopy(document["sources"][0])
        else:
            document["sources"][0], document["sources"][1] = (
                document["sources"][1],
                document["sources"][0],
            )
        with pytest.raises(generator.StagingDeploymentContractError) as captured:
            _validate(document)
        assert captured.value.code in {"SOURCE_DUPLICATE", "SOURCE_INVENTORY_DRIFT"}


def _copy_pinned_sources(target_root: Path) -> None:
    for relative in dict.fromkeys(
        (*generator.PINNED_SOURCES, generator.STANDING_DEVELOPMENT_AUTHORITY_PATH)
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
    marker = f"\n{MARKER}\n".encode()
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + marker)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == expected_code
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize("relative", tuple(generator.PREDECESSOR_SOURCES))
def test_every_predecessor_byte_drift_fails_closed(
    tmp_path: Path, contract_document: dict[str, Any], relative: str
) -> None:
    _copy_pinned_sources(tmp_path)
    predecessor = tmp_path / relative
    predecessor.write_bytes(predecessor.read_bytes() + b"\n")
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == "SOURCE_DIGEST_MISMATCH"


def _rebind_predecessor_digest(
    document: dict[str, Any],
    relative: str,
    new_digest: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predecessor_sources = dict(generator.PREDECESSOR_SOURCES)
    predecessor_sources[relative] = new_digest
    monkeypatch.setattr(generator, "PREDECESSOR_SOURCES", predecessor_sources)
    monkeypatch.setattr(
        generator,
        "PINNED_SOURCES",
        {**generator.AUTHORITY_SOURCES, **predecessor_sources},
    )
    for row in document["sources"]:
        if row["uri"] == f"repo://{relative}":
            row["sha256"] = new_digest
            return
    raise AssertionError("predecessor source row missing")


@pytest.mark.parametrize(
    ("relative", "kind"),
    [
        ("changes/st-1502/contracts/data-services-foundation.v1.yaml", "data_contract"),
        (
            "infra/terraform/data-services/data-services.reference-plan.v1.json",
            "data_plan",
        ),
        (
            "changes/st-1503/contracts/compute-edge-foundation.v1.yaml",
            "compute_contract",
        ),
        (
            "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json",
            "compute_plan",
        ),
        ("changes/st-1504/contracts/github-oidc-deployment.v1.yaml", "oidc_contract"),
        (
            "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json",
            "oidc_plan",
        ),
    ],
)
def test_every_predecessor_semantic_tamper_fails_after_digest_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    kind: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    if kind.endswith("contract"):
        value = yaml.safe_load(path.read_bytes())
        if kind == "data_contract":
            value["execution_boundary"]["activation_enabled"] = True
        elif kind == "compute_contract":
            value["health_intent"]["readiness"]["infer_from_http_200_body"] = "ALLOWED"
        else:
            value["selected_bindings"]["github_repository"] = "attempted/repository"
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    else:
        value = json.loads(path.read_bytes())
        if kind == "data_plan":
            value["planned_actions"]["create"] = 1
        elif kind == "compute_plan":
            value["selected_configuration"]["cloud_provider"] = "attempted-provider"
        else:
            value["activation"]["credential_issuance"] = "ALLOWED"
        path.write_text(json.dumps(value), encoding="utf-8")
    document = copy.deepcopy(contract_document)
    _rebind_predecessor_digest(
        document, relative, generator.sha256_file(path), monkeypatch
    )
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code in {
        "FIXED_VALUE_VIOLATION",
        "SAFE_BOUNDARY_VIOLATION",
        "PREDECESSOR_SELECTION_SET",
    }


def test_authority_semantic_drift_fails_even_when_digest_is_rebound(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
    path = tmp_path / relative
    value = yaml.safe_load(path.read_bytes())
    for story in value["stories"]:
        if story["id"] == "ST-1505":
            story["open_decisions"] = ["invented"]
            break
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    digest = generator.sha256_file(path)
    authority_sources = dict(generator.AUTHORITY_SOURCES)
    authority_sources[relative] = digest
    monkeypatch.setattr(generator, "AUTHORITY_SOURCES", authority_sources)
    monkeypatch.setattr(
        generator,
        "PINNED_SOURCES",
        {**authority_sources, **generator.PREDECESSOR_SOURCES},
    )
    document = copy.deepcopy(contract_document)
    for row in document["sources"]:
        if row["uri"] == f"repo://{relative}":
            row["sha256"] = digest
            break
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


def test_contract_file_and_pinned_source_ancestor_symlinks_are_rejected(
    tmp_path: Path, contract_document: dict[str, Any]
) -> None:
    target = tmp_path / "target.yaml"
    target.write_text("document: {}\n", encoding="utf-8")
    link = tmp_path / "contract.yaml"
    link.symlink_to(target)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.load_yaml(link)
    assert captured.value.code == "UNSAFE_FILE_TYPE"

    isolated = tmp_path / "isolated"
    isolated.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (isolated / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), isolated)
    assert captured.value.code == "UNSAFE_ANCESTOR"
    assert list(outside.iterdir()) == []
