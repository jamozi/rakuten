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
DEPENDENCY_STORIES = ("ST-1501", "ST-1502", "ST-1503", "ST-1504", "ST-1505")
HANDOFF_NORMATIVE_SECTIONS = (
    "schema",
    "version",
    "record_status",
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
)
PREDECESSOR_SOURCE_PATHS = (
    "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
    "changes/st-1501/contracts/terraform-foundation.v1.yaml",
    "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
    "scripts/build_st1501_terraform_foundation.py",
    "changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml",
    "changes/st-1502/contracts/data-services-foundation.v1.yaml",
    "infra/terraform/data-services/data-services.reference-plan.v1.json",
    "scripts/build_st1502_data_services.py",
    "changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml",
    "changes/st-1503/contracts/compute-edge-foundation.v1.yaml",
    "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json",
    "scripts/build_st1503_compute_edge.py",
    "changes/st-0107/contracts/pr-governance.v1.yaml",
    "changes/st-0107/ruleset-policy.v1.json",
    "changes/st-1504/"
    "DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml",
    "changes/st-1504/contracts/github-oidc-deployment.v1.yaml",
    "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json",
    "scripts/build_st1504_github_oidc.py",
    "changes/st-1505/DESIGN_HANDOFF_V1_ST1505_PROVIDER_NEUTRAL_STAGING.yaml",
    "changes/st-1505/contracts/staging-deployment.v1.yaml",
    "infra/terraform/staging/staging-deployment.reference-plan.v1.json",
    "scripts/build_st1505_staging_deployment.py",
)
PREDECESSOR_ARTIFACT_PATHS = tuple(
    path
    for path in PREDECESSOR_SOURCE_PATHS
    if not path.startswith("scripts/") and not path.startswith("changes/st-0107/")
)
PLAN_PATHS = tuple(
    path
    for path in PREDECESSOR_ARTIFACT_PATHS
    if path.endswith("reference-plan.v1.json")
)
COORDINATED_PREDECESSOR_SECTION_CASES = tuple(
    (story_id, section)
    for story_id, sections in (
        (
            "ST-1501",
            (
                "document",
                "sources",
                "reference_architecture",
                "provider_neutral_foundation_admission",
                "selected_configuration",
                "execution_boundary",
                "state_requirements",
                "account_requirements",
                "production_change_requirements",
                "extension_contract",
                "evidence_boundary",
            ),
        ),
        (
            "ST-1502",
            (
                "document",
                "sources",
                "predecessor_binding",
                "reference_architecture",
                "provider_neutral_data_services_admission",
                "selected_configuration",
                "relational_persistence_intent",
                "object_storage_intent",
                "queue_intent",
                "secrets_intent",
                "key_management_intent",
                "recovery_intent",
                "observability_intent",
                "data_boundary_intent",
                "execution_boundary",
                "evidence_boundary",
            ),
        ),
        (
            "ST-1503",
            (
                "document",
                "sources",
                "predecessor_binding",
                "reference_architecture",
                "provider_neutral_compute_edge_admission",
                "selected_configuration",
                "workload_intent",
                "surface_boundary_intent",
                "edge_routing_intent",
                "health_intent",
                "open_decision_boundary",
                "execution_boundary",
                "evidence_boundary",
            ),
        ),
        (
            "ST-1504",
            (
                "document",
                "sources",
                "predecessor_bindings",
                "ci_source_boundary",
                "reference_architecture",
                "provider_neutral_deployment_identity_admission",
                "reference_intent",
                "selected_bindings",
                "trust_constraints",
                "credential_boundary",
                "workflow_permission_intent",
                "environment_protection_intent",
                "lifecycle_control_intent",
                "open_decision_boundary",
                "execution_boundary",
                "evidence_boundary",
            ),
        ),
        (
            "ST-1505",
            (
                "document",
                "sources",
                "predecessor_bindings",
                "reference_architecture",
                "provider_neutral_staging_admission",
                "open_decision_boundary",
                "environment_boundary",
                "selected_bindings",
                "artifact_admission_intent",
                "protected_environment_intent",
                "migration_intent",
                "health_security_runtime_intent",
                "transport_security_intent",
                "observability_alerting_intent",
                "isolation_residency_budget_intent",
                "target_adapter_intent",
                "rollback_restore_intent",
                "logical_phases",
                "execution_boundary",
                "evidence_boundary",
            ),
        ),
    )
    for section in sections
)


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
    ("mutation", "expected_code"),
    (
        ("missing", "MISSING_DEPENDENCY_MAPPING"),
        ("unknown", "UNKNOWN_DEPENDENCY_MAPPING"),
        ("duplicate", "DUPLICATE_DEPENDENCY_MAPPING"),
        ("reorder", "DEPENDENCY_MAPPING_ORDER_DRIFT"),
    ),
)
def test_dependency_admission_inventory_fails_closed(
    contract_document: dict[str, Any], mutation: str, expected_code: str
) -> None:
    document = copy.deepcopy(contract_document)
    rows = document["provider_neutral_admission"]["dependency_admission_requirements"]
    assert tuple(row["story_id"] for row in rows) == DEPENDENCY_STORIES
    if mutation == "missing":
        rows.pop()
    elif mutation == "unknown":
        rows[-1]["story_id"] = "ST-UNKNOWN"
    elif mutation == "duplicate":
        rows[-1]["story_id"] = rows[0]["story_id"]
    else:
        rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        _validate(document)
    assert captured.value.code == expected_code


@pytest.mark.parametrize("mutation", ("missing", "unknown", "duplicate", "reorder"))
def test_five_direct_predecessor_binding_inventory_is_closed(
    contract_document: dict[str, Any], mutation: str
) -> None:
    document = copy.deepcopy(contract_document)
    bindings = document["predecessor_bindings"]
    assert tuple(bindings) == (
        "foundation",
        "data_services",
        "compute_edge",
        "deployment_identity",
        "staging",
    )
    if mutation == "missing":
        bindings.pop("staging")
    elif mutation == "unknown":
        bindings["unknown"] = bindings.pop("staging")
    elif mutation == "duplicate":
        bindings["staging"]["story_id"] = "ST-1501"
    else:
        first = bindings.pop("foundation")
        bindings["foundation"] = first
    with pytest.raises(generator.ProductionDeploymentContractError):
        _validate(document)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("satisfied_dependency_count", 1),
        ("complete_dependency_chain", True),
        ("partial_dependency", "ALLOW"),
        ("predecessor_completion_only", "ALLOW"),
        ("provider_label_only", "ALLOW"),
        ("dependency_shortcut", "ALLOWED"),
    ),
)
def test_no_partial_predecessor_or_provider_shortcut_can_satisfy_admission(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_admission"]["dependency_admission_policy"][field] = value
    with pytest.raises(generator.ProductionDeploymentContractError):
        _validate(document)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("current_admission_status", "ELIGIBLE"),
        ("current_eligible", True),
        ("selected_profile_id", "AWS_TOKYO"),
        ("selected_provider_name", "AWS"),
        ("evidence_references", ["repo://shortcut"]),
        ("dependency_status", "SATISFIED"),
    ),
)
def test_no_single_predecessor_row_can_be_promoted_or_used_as_evidence(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_admission"]["dependency_admission_requirements"][0][
        field
    ] = value
    with pytest.raises(generator.ProductionDeploymentContractError):
        _validate(document)


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
        "partial_predecessor_chain_as_evidence",
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
        ("migration_intent", "migration_owner_assignment", "OPTIONAL"),
        ("migration_intent", "independent_migration_review", "OPTIONAL"),
        ("migration_intent", "independent_migration_approval", "OPTIONAL"),
        ("migration_intent", "migration_self_approval", "ALLOWED"),
        ("migration_intent", "migration_review_bypass", "ALLOWED"),
        ("transport_security_intent", "all_production_network_flows", "OPTIONAL"),
        ("transport_security_intent", "authenticated_encryption", "OPTIONAL"),
        (
            "transport_security_intent",
            "certificate_identity_and_hostname_verification",
            "OPTIONAL",
        ),
        ("transport_security_intent", "downgrade_resistance", "OPTIONAL"),
        ("transport_security_intent", "plaintext_transport", "ALLOWED"),
        ("transport_security_intent", "insecure_skip_verification", "ALLOWED"),
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
def test_artifact_environment_migration_transport_canary_and_rollback_are_strict(
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
        "provider_action",
        "aws_action",
        "iam_action",
        "staging_action",
        "deploy_action",
        "migration_review_action",
        "transport_security_action",
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


def _owner_modules() -> tuple[object, ...]:
    from scripts import build_st1501_terraform_foundation as st1501
    from scripts import build_st1502_data_services as st1502
    from scripts import build_st1503_compute_edge as st1503
    from scripts import build_st1504_github_oidc as st1504
    from scripts import build_st1505_staging_deployment as st1505

    return st1501, st1502, st1503, st1504, st1505


def _copy_pinned_sources(target_root: Path) -> None:
    relative_paths = set(generator.PINNED_SOURCES)
    for owner in _owner_modules():
        relative_paths.update(owner.PINNED_SOURCES)
    for relative in sorted(relative_paths):
        source = REPOSITORY_ROOT / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _source_row(document: dict[str, Any], relative: str) -> dict[str, Any]:
    matches = [row for row in document["sources"] if row["uri"] == f"repo://{relative}"]
    assert len(matches) == 1
    return matches[0]


def _predecessor_binding(
    document: dict[str, Any], relative: str
) -> tuple[dict[str, Any], str] | None:
    for (
        binding_name,
        _story_id,
        owner_generator_path,
        handoff_path,
        contract_path,
        plan_path,
        _admission_name,
        _action_counts,
    ) in generator.PREDECESSOR_SPECIFICATIONS:
        binding = document["predecessor_bindings"][binding_name]
        if relative == owner_generator_path:
            return binding, "owner_generator"
        if relative == handoff_path:
            return binding, "design_handoff"
        if relative == contract_path:
            return binding, "contract"
        if relative == plan_path:
            return binding, "reference_plan"
    return None


def _refresh_contract_fingerprint(
    document: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        generator,
        "EXPECTED_CONTRACT_FINGERPRINT",
        generator._object_fingerprint(document),
    )


def _rebind_predecessor_raw_digest(
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
    _source_row(document, relative)["sha256"] = new_digest
    binding_result = _predecessor_binding(document, relative)
    if binding_result is not None:
        binding, prefix = binding_result
        binding[f"{prefix}_sha256"] = new_digest
    _refresh_contract_fingerprint(document, monkeypatch)


def _rebind_predecessor_semantic_digest(
    document: dict[str, Any],
    relative: str,
    value: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic_sources = dict(generator.PREDECESSOR_SEMANTIC_SHA256)
    semantic_sources[relative] = generator.semantic_sha256(value)
    monkeypatch.setattr(generator, "PREDECESSOR_SEMANTIC_SHA256", semantic_sources)
    binding_result = _predecessor_binding(document, relative)
    assert binding_result is not None
    binding, prefix = binding_result
    binding[f"{prefix}_semantic_sha256"] = semantic_sources[relative]
    _refresh_contract_fingerprint(document, monkeypatch)


@pytest.mark.parametrize("relative", PREDECESSOR_SOURCE_PATHS)
def test_every_predecessor_raw_byte_drift_fails_closed(
    tmp_path: Path, contract_document: dict[str, Any], relative: str
) -> None:
    assert tuple(generator.PREDECESSOR_SOURCES) == PREDECESSOR_SOURCE_PATHS
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == "SOURCE_DIGEST_MISMATCH"


def _tamper_predecessor(value: dict[str, Any], relative: str) -> None:
    if relative.endswith(".json"):
        value["document"]["executable"] = True
    elif "DESIGN_HANDOFF" in relative:
        value["approved_scope"][0] = MARKER
    else:
        value["document"]["formal_verification"] = "EXECUTED"


@pytest.mark.parametrize("relative", PREDECESSOR_ARTIFACT_PATHS)
def test_every_predecessor_semantic_tamper_fails_after_raw_digest_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    is_json = relative.endswith(".json")
    value = (
        json.loads(path.read_bytes()) if is_json else yaml.safe_load(path.read_bytes())
    )
    _tamper_predecessor(value, relative)
    if is_json:
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    else:
        path.write_text(
            yaml.safe_dump(value, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    document = copy.deepcopy(contract_document)
    _rebind_predecessor_raw_digest(
        document, relative, generator.sha256_file(path), monkeypatch
    )
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_SEMANTIC_DRIFT"
    assert MARKER not in str(captured.value)


def _predecessor_contract_and_plan_paths(story_id: str) -> tuple[str, str]:
    for specification in generator.PREDECESSOR_SPECIFICATIONS:
        if specification[1] == story_id:
            return specification[4], specification[5]
    raise AssertionError("predecessor specification missing")


def _render_without_owner_validation(story_id: str, contract: dict[str, Any]) -> bytes:
    owners = _owner_modules()
    owner_by_story = dict(zip(DEPENDENCY_STORIES, owners, strict=True))
    model_names = {
        "ST-1501": "FoundationModel",
        "ST-1502": "DataServicesModel",
        "ST-1503": "ComputeEdgeModel",
        "ST-1504": "GithubOidcModel",
        "ST-1505": "StagingDeploymentModel",
    }
    owner = owner_by_story[story_id]
    if story_id == "ST-1501":
        plan_relative = _predecessor_contract_and_plan_paths(story_id)[1]
        plan = json.loads((REPOSITORY_ROOT / plan_relative).read_bytes())
        plan["document"][MARKER] = MARKER
        return (
            json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    model = getattr(owner, model_names[story_id])(contract=contract)
    return owner.render_reference_plan(model)


def _add_normative_section_downgrade(contract: dict[str, Any], section: str) -> None:
    value = contract[section]
    if isinstance(value, dict):
        value[MARKER] = (
            None
            if section in {"selected_configuration", "selected_bindings"}
            else MARKER
        )
        return
    if isinstance(value, list) and value and isinstance(value[0], dict):
        value[0][MARKER] = MARKER
        return
    if isinstance(value, list):
        value.append(MARKER)
        return
    raise AssertionError("unsupported normative section shape")


@pytest.mark.parametrize(("story_id", "section"), COORDINATED_PREDECESSOR_SECTION_CASES)
def test_owner_validator_rejects_every_coordinated_predecessor_section_rebind(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    story_id: str,
    section: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    contract_relative, plan_relative = _predecessor_contract_and_plan_paths(story_id)
    contract_path = tmp_path / contract_relative
    predecessor_contract = yaml.safe_load(contract_path.read_bytes())
    assert isinstance(predecessor_contract, dict)
    _add_normative_section_downgrade(predecessor_contract, section)
    contract_path.write_text(
        yaml.safe_dump(predecessor_contract, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    plan_path = tmp_path / plan_relative
    plan_bytes = _render_without_owner_validation(story_id, predecessor_contract)
    plan_path.write_bytes(plan_bytes)
    plan_document = json.loads(plan_bytes)

    document = copy.deepcopy(contract_document)
    _rebind_predecessor_raw_digest(
        document, contract_relative, generator.sha256_file(contract_path), monkeypatch
    )
    _rebind_predecessor_raw_digest(
        document, plan_relative, generator.sha256_file(plan_path), monkeypatch
    )
    _rebind_predecessor_semantic_digest(
        document, contract_relative, predecessor_contract, monkeypatch
    )
    _rebind_predecessor_semantic_digest(
        document, plan_relative, plan_document, monkeypatch
    )

    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_SEMANTIC_DRIFT"
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize("relative", PLAN_PATHS)
def test_every_predecessor_plan_requires_exact_owner_generated_bytes(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    value = json.loads(path.read_bytes())
    path.write_text(json.dumps(value, separators=(",", ":")) + "\n", encoding="utf-8")
    assert (
        generator.semantic_sha256(value)
        == generator.PREDECESSOR_SEMANTIC_SHA256[relative]
    )
    document = copy.deepcopy(contract_document)
    _rebind_predecessor_raw_digest(
        document, relative, generator.sha256_file(path), monkeypatch
    )
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_GENERATED_DRIFT"


@pytest.mark.parametrize(
    "relative",
    (
        "changes/st-0107/contracts/pr-governance.v1.yaml",
        "changes/st-0107/ruleset-policy.v1.json",
    ),
)
def test_st0107_raw_rebind_cannot_bypass_st1504_owner_validation(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    if relative.endswith(".json"):
        value = json.loads(path.read_bytes())
        value[MARKER] = MARKER
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    else:
        value = yaml.safe_load(path.read_bytes())
        value[MARKER] = MARKER
        path.write_text(
            yaml.safe_dump(value, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    document = copy.deepcopy(contract_document)
    _rebind_predecessor_raw_digest(
        document, relative, generator.sha256_file(path), monkeypatch
    )
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_SEMANTIC_DRIFT"
    assert MARKER not in str(captured.value)


def _rebind_handoff_raw_digest(
    document: dict[str, Any],
    new_digest: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = generator.DESIGN_HANDOFF_PATH.as_posix()
    authority_sources = dict(generator.AUTHORITY_SOURCES)
    authority_sources[relative] = new_digest
    monkeypatch.setattr(generator, "AUTHORITY_SOURCES", authority_sources)
    monkeypatch.setattr(
        generator,
        "PINNED_SOURCES",
        {**authority_sources, **generator.PREDECESSOR_SOURCES},
    )
    _source_row(document, relative)["sha256"] = new_digest
    _refresh_contract_fingerprint(document, monkeypatch)


def _tamper_handoff(document: dict[str, Any], section: str) -> None:
    value = document[section]
    if section == "schema":
        document[section] = "DESIGN_HANDOFF_V0"
    elif section == "version":
        document[section] = 2
    elif section in {"record_status", "approved_story"}:
        document[section] = MARKER
    elif isinstance(value, list):
        value[0] = MARKER
    elif section == "decision":
        value["selected_profile"] = "AWS"
    elif section == "open_decision_state":
        value["OD-009"]["resolved"] = True
    else:
        raise AssertionError(section)


@pytest.mark.parametrize("section", HANDOFF_NORMATIVE_SECTIONS)
def test_every_handoff_normative_section_is_exact_after_raw_hash_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    section: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    path = tmp_path / generator.DESIGN_HANDOFF_PATH
    handoff = yaml.safe_load(path.read_bytes())
    assert tuple(handoff) == HANDOFF_NORMATIVE_SECTIONS
    _tamper_handoff(handoff, section)
    path.write_text(
        yaml.safe_dump(handoff, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    document = copy.deepcopy(contract_document)
    _rebind_handoff_raw_digest(document, generator.sha256_file(path), monkeypatch)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code in {
        "CLOSED_SCHEMA_VIOLATION",
        "FIXED_VALUE_VIOLATION",
        "HANDOFF_SEMANTIC_DRIFT",
        "SAFE_BOUNDARY_VIOLATION",
        "SELECTION_MUST_REMAIN_UNSET",
    }
    assert MARKER not in str(captured.value)


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
