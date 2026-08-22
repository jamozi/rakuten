"""Bounded hostile and fail-closed tests for ST-1506."""

from __future__ import annotations

import copy
import json
import shutil
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
def test_no_provider_profile_can_be_selected_defaulted_or_fallbacked(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_admission"][field] = "AWS"
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("missing", "MISSING_CAPABILITY_MAPPING"),
        ("unknown", "UNKNOWN_CAPABILITY_MAPPING"),
        ("duplicate", "DUPLICATE_CAPABILITY_MAPPING"),
        ("reorder", "CAPABILITY_MAPPING_ORDER_DRIFT"),
    ),
)
def test_capability_mapping_inventory_fails_closed(
    contract_document: dict[str, Any], mutation: str, expected_code: str
) -> None:
    document = copy.deepcopy(contract_document)
    rows = document["provider_neutral_admission"]["capability_mapping_requirements"]
    if mutation == "missing":
        rows.pop()
    elif mutation == "unknown":
        rows[-1]["capability_id"] = "provider_specific_shortcut"
    elif mutation == "duplicate":
        rows[-1]["capability_id"] = rows[0]["capability_id"]
    else:
        rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
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
def test_profile_eligibility_cannot_precede_complete_mapping_and_evidence(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_admission"][field] = value
    with pytest.raises(generator.ProductionDeploymentContractError):
        _validate(document)


def test_aws_label_alone_cannot_satisfy_admission(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    admission = document["provider_neutral_admission"]
    admission["eligible"] = True
    admission["selected_profile_id"] = "AWS_TOKYO"
    admission["selected_profile_kind"] = "AWS"
    admission["selected_provider_name"] = "AWS"
    admission["mapping_policy"]["configured_mapping_count"] = len(
        generator.REQUIRED_CAPABILITY_IDS
    )
    admission["mapping_policy"]["complete_mapping"] = True
    for row in admission["capability_mapping_requirements"]:
        row["selected_mapping"] = f"AWS_LABEL::{row['capability_id']}"
        row["mapping_status"] = "CONFIGURED"
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == "SAFE_BOUNDARY_VIOLATION"


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
def test_aws_reference_cannot_be_promoted_to_provider_semantics(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_admission"]["aws_reference_boundary"][field] = True
    with pytest.raises(generator.ProductionDeploymentContractError):
        _validate(document)


@pytest.mark.parametrize(
    "field",
    (
        "provider_label_as_evidence",
        "reference_metadata_as_evidence",
        "predecessor_completion_as_evidence",
        "local_test_as_live_evidence",
    ),
)
def test_provider_neutral_evidence_rules_cannot_be_weakened(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_admission"]["evidence_equivalence_policy"][field] = (
        "ALLOWED"
    )
    with pytest.raises(generator.ProductionDeploymentContractError):
        _validate(document)


def test_partial_capability_mapping_without_evidence_is_rejected(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    row = document["provider_neutral_admission"]["capability_mapping_requirements"][0]
    row["selected_mapping"] = "owner-managed-runtime"
    row["mapping_status"] = "CONFIGURED"
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


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


def _copy_pinned_sources(target_root: Path) -> None:
    for relative in generator.PINNED_SOURCES:
        source = REPOSITORY_ROOT / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


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
        {**generator.AUTHORITY_SOURCES, **predecessor_sources},
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
    ("relative", "mutation", "expected_code"),
    (
        (
            "changes/st-1505/contracts/staging-deployment.v1.yaml",
            "enabled",
            "SAFE_BOUNDARY_VIOLATION",
        ),
        (
            "changes/st-1505/contracts/staging-deployment.v1.yaml",
            "nonzero",
            "SAFE_BOUNDARY_VIOLATION",
        ),
        (
            "changes/st-1505/contracts/staging-deployment.v1.yaml",
            "selected",
            "SELECTION_MUST_REMAIN_UNSET",
        ),
        (
            "changes/st-1505/contracts/staging-deployment.v1.yaml",
            "external",
            "FIXED_VALUE_VIOLATION",
        ),
        *(
            (
                "changes/st-1505/contracts/staging-deployment.v1.yaml",
                mutation,
                "FIXED_VALUE_VIOLATION",
            )
            for mutation in (
                "network",
                "credential",
                "staging_action",
                "release_action",
                "production_action",
            )
        ),
        (
            "changes/st-1505/contracts/staging-deployment.v1.yaml",
            "tst009",
            "FIXED_VALUE_VIOLATION",
        ),
        (
            "changes/st-1505/contracts/staging-deployment.v1.yaml",
            "tst022",
            "FIXED_VALUE_VIOLATION",
        ),
        (
            "infra/terraform/staging/staging-deployment.reference-plan.v1.json",
            "executable",
            "SAFE_BOUNDARY_VIOLATION",
        ),
        (
            "infra/terraform/staging/staging-deployment.reference-plan.v1.json",
            "enabled",
            "SAFE_BOUNDARY_VIOLATION",
        ),
        *(
            (
                "infra/terraform/staging/staging-deployment.reference-plan.v1.json",
                mutation,
                "PREDECESSOR_SEMANTIC_DRIFT",
            )
            for mutation in (
                "network",
                "credential",
                "staging_action",
                "release_action",
                "production_action",
            )
        ),
    ),
)
def test_st1505_semantic_drift_fails_even_after_digest_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    mutation: str,
    expected_code: str,
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
        elif mutation in {
            "network",
            "credential",
            "staging_action",
            "release_action",
            "production_action",
        }:
            field = {
                "network": "network_access",
                "credential": "credential_access",
                "staging_action": "staging_action",
                "release_action": "release_action",
                "production_action": "production_action",
            }[mutation]
            value["execution_boundary"][field] = "ALLOWED"
        elif mutation == "tst009":
            value["evidence_boundary"]["formal_tst_009"] = "EXECUTED"
        else:
            value["evidence_boundary"]["formal_tst_022"] = "EXECUTED"
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    else:
        value = json.loads(path.read_bytes())
        if mutation == "executable":
            value["document"]["executable"] = True
        elif mutation == "enabled":
            value["activation"]["enabled"] = True
        else:
            field = {
                "network": "network_access",
                "credential": "credential_access",
                "staging_action": "staging_action",
                "release_action": "release_action",
                "production_action": "production_action",
            }[mutation]
            value["activation"][field] = "ALLOWED"
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    document = copy.deepcopy(contract_document)
    _rebind_immediate_predecessor(
        document, relative, generator.sha256_file(path), monkeypatch
    )
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == expected_code


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
    "relative",
    (
        "changes/st-1505/contracts/staging-deployment.v1.yaml",
        "infra/terraform/staging/staging-deployment.reference-plan.v1.json",
    ),
)
def test_immediate_predecessor_byte_drift_fails_closed(
    tmp_path: Path, contract_document: dict[str, Any], relative: str
) -> None:
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == "SOURCE_DIGEST_MISMATCH"


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
    outside = tmp_path / "outside"
    outside.mkdir()
    (isolated / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), isolated)
    assert captured.value.code == "UNSAFE_ANCESTOR"
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._repository_regular_file(
            REPOSITORY_ROOT, Path("../escape"), "hostile"
        )
    assert captured.value.code == "UNSAFE_REPOSITORY_PATH"
