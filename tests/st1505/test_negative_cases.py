"""Hostile, downgrade, provenance, and filesystem tests for ST-1505."""

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

SELECTED_BINDING_FIELDS = (
    "target_provider_name",
    "target_profile_id",
    "target_profile_kind",
    "target_account_project_or_tenant",
    "target_region",
    "target_backup_region",
    "target_data_residency_policy",
    "target_state_backend",
    "target_deployment_identity",
    "target_federation_audience",
    "target_adapter",
    "target_provider_plugins",
    "target_resource_bindings",
    "github_repository",
    "github_ref",
    "github_workflow",
    "github_environment",
    "artifact_digest",
    "artifact_sbom_reference",
    "artifact_scan_reference",
    "artifact_provenance_reference",
    "release_id",
    "commit_sha",
    "contract_hash",
    "migration_version",
    "migration_task_reference",
    "domain_names",
    "public_endpoint",
    "admin_endpoint",
    "internal_endpoint",
    "liveness_endpoint",
    "readiness_endpoint",
    "smoke_endpoint",
    "health_matcher",
    "browser_base_url",
    "browser_project",
    "telemetry_source",
    "alert_policy",
    "notification_channels",
    "budget_limit",
    "automatic_stop_policy",
    "rollback_artifact_digest",
    "rollback_configuration_version",
    "rollback_snapshot_id",
    "rollback_migration_version",
)
DEPENDENCY_STORIES = ("ST-1501", "ST-1502", "ST-1503", "ST-1504")
CAPABILITY_IDS = (
    "provider_neutral_foundation_profile",
    "provider_neutral_data_services_profile",
    "provider_neutral_compute_edge_profile",
    "provider_neutral_deployment_identity_profile",
    "immutable_build_sbom_scan_and_provenance",
    "migration_compatibility_and_dry_run",
    "protected_environment_human_approval",
    "smoke_security_and_runtime_verification",
    "cross_capability_transport_security",
    "observability_alerting_and_release_markers",
    "rollback_restore_and_recovery_readiness",
    "isolation_region_residency_and_budget_controls",
    "provider_neutral_target_adapter",
)
REFERENCE_FALSE_FIELDS = (
    "default",
    "implicit_fallback",
    "selected_binding",
    "eligibility_shortcut",
    "admission_requirement",
    "evidence_substitute",
)
EVIDENCE_EQUIVALENCE_FIELDS = (
    "identical_predecessor_capability_evidence",
    "identical_security_evidence",
    "identical_operations_evidence",
    "identical_release_evidence",
    "identical_supply_chain_evidence",
    "identical_migration_evidence",
    "identical_independent_migration_review_evidence",
    "identical_protected_approval_evidence",
    "identical_smoke_security_runtime_evidence",
    "identical_transport_security_evidence",
    "identical_observability_alerting_evidence",
    "identical_rollback_restore_evidence",
    "identical_isolation_residency_budget_evidence",
    "identical_target_adapter_evidence",
    "provider_label_as_evidence",
    "aws_label_as_evidence",
    "service_label_as_evidence",
    "predecessor_completion_as_evidence",
    "reference_metadata_as_evidence",
    "local_test_as_live_evidence",
)
NORMATIVE_CONTRACT_SECTIONS = (
    "document",
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
)
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
OPEN_DECISIONS = (
    "OD-002",
    "OD-009",
    "OD-010",
    "OD-011",
    "OD-013",
    "OD-014",
    "OD-015",
)
EXECUTION_FORBIDDEN_FIELDS = (
    "network_access",
    "credential_access",
    "live_provider_calls",
    "external_writes",
    "staging_action",
    "deploy_action",
    "migration_action",
    "migration_review_action",
    "transport_security_action",
    "rollback_action",
    "release_action",
    "production_action",
)
ACTION_COUNT_FIELDS = (
    "create",
    "update",
    "delete",
    "build",
    "promote",
    "approve",
    "deploy",
    "migrate",
    "migration_review",
    "smoke",
    "security",
    "runtime",
    "browser",
    "transport_security",
    "telemetry",
    "alert",
    "rollback",
    "restore",
    "release",
    "production",
)
OPERATION_FIELDS = (
    "dependency_admission",
    "target_adapter_call",
    "artifact_build",
    "artifact_promote",
    "environment_approval",
    "deploy",
    "migration_dry_run",
    "migration_review",
    "migrate",
    "smoke",
    "security_check",
    "runtime_check",
    "browser",
    "transport_security_check",
    "telemetry_write",
    "alert_route_write",
    "rollback",
    "restore",
    "release",
    "production",
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
    "changes/st-1504/DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml",
    "changes/st-1504/contracts/github-oidc-deployment.v1.yaml",
    "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json",
    "scripts/build_st1504_github_oidc.py",
)
PREDECESSOR_ARTIFACT_PATHS = (
    "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
    "changes/st-1501/contracts/terraform-foundation.v1.yaml",
    "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
    "changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml",
    "changes/st-1502/contracts/data-services-foundation.v1.yaml",
    "infra/terraform/data-services/data-services.reference-plan.v1.json",
    "changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml",
    "changes/st-1503/contracts/compute-edge-foundation.v1.yaml",
    "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json",
    "changes/st-1504/DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml",
    "changes/st-1504/contracts/github-oidc-deployment.v1.yaml",
    "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json",
)
COORDINATED_PREDECESSOR_SECTION_CASES = (
    tuple(
        ("ST-1502", section)
        for section in (
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
        )
    )
    + tuple(
        ("ST-1503", section)
        for section in (
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
        )
    )
    + tuple(
        ("ST-1504", section)
        for section in (
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
        )
    )
)


def _validate(document: dict[str, Any]) -> generator.StagingDeploymentModel:
    return generator.validate_contract(document, REPOSITORY_ROOT)


def _assert_rejected(
    document: dict[str, Any], expected_codes: set[str] | None = None
) -> None:
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        _validate(document)
    if expected_codes is not None:
        assert captured.value.code in expected_codes
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize("field", SELECTED_BINDING_FIELDS)
def test_every_target_resource_runtime_and_release_binding_remains_unset(
    contract_document: dict[str, Any], field: str
) -> None:
    assert tuple(contract_document["selected_bindings"]) == SELECTED_BINDING_FIELDS
    document = copy.deepcopy(contract_document)
    current = document["selected_bindings"][field]
    document["selected_bindings"][field] = (
        [MARKER] if isinstance(current, list) else MARKER
    )
    _assert_rejected(document, {"PREDECESSOR_SELECTION_SET"})


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("admission_status", "ELIGIBLE"),
        ("eligible", True),
        ("selected_profile_id", "aws-staging"),
        ("selected_profile_kind", "AWS"),
        ("selected_provider_name", "AWS"),
        ("default_profile_id", "aws-staging"),
        ("fallback_profile_id", "aws-staging"),
        ("concrete_alternate_provider_selected", True),
        ("eligibility_condition", "AWS_LABEL_PRESENT"),
    ),
)
def test_provider_name_default_fallback_and_eligibility_shortcuts_fail_closed(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_staging_admission"][field] = value
    _assert_rejected(document)


@pytest.mark.parametrize("field", REFERENCE_FALSE_FIELDS)
@pytest.mark.parametrize(
    "section", ("reference_architecture", "provider_neutral_staging_admission")
)
def test_aws_reference_can_never_become_a_default_selection_or_evidence(
    contract_document: dict[str, Any], section: str, field: str
) -> None:
    document = copy.deepcopy(contract_document)
    target = document[section]
    if section == "provider_neutral_staging_admission":
        target = target["aws_reference_boundary"]
    target[field] = True
    _assert_rejected(document)


@pytest.mark.parametrize(
    ("section_path", "value"),
    (
        (
            ("reference_architecture", "classification"),
            "OPTIONAL_HISTORICAL_AWS_STAGING_REFERENCE_MAPPINGS_ONLY",
        ),
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
            "CANONICAL_STORY_DELIVERABLES_REPLACED",
        ),
        (
            (
                "provider_neutral_staging_admission",
                "aws_reference_boundary",
                "non_aws_owner_managed_profiles",
            ),
            "PRIMARY_REPLACEMENT_PATHS",
        ),
        (
            ("environment_boundary", "reference_region_use"),
            "OPTIONAL_HISTORICAL_METADATA_ONLY",
        ),
    ),
)
def test_canonical_reference_and_portable_path_semantics_cannot_be_demoted(
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    section_path: tuple[str, ...],
    value: str,
) -> None:
    document = copy.deepcopy(contract_document)
    target: dict[str, Any] = document
    for key in section_path[:-1]:
        target = target[key]
    target[section_path[-1]] = value
    monkeypatch.setattr(
        generator,
        "EXPECTED_CONTRACT_SEMANTIC_SHA256",
        generator.semantic_sha256(document),
    )
    _assert_rejected(document, {"FIXED_VALUE_VIOLATION"})


def test_canonical_reference_status_cannot_replace_dependency_admission(
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = copy.deepcopy(contract_document)
    policy = document["provider_neutral_staging_admission"][
        "dependency_admission_policy"
    ]
    policy["historical_reference_only"] = policy.pop(
        "canonical_reference_architecture_status_only"
    )
    monkeypatch.setattr(
        generator,
        "EXPECTED_CONTRACT_SEMANTIC_SHA256",
        generator.semantic_sha256(document),
    )
    _assert_rejected(document, {"CLOSED_SCHEMA_VIOLATION"})


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("missing", "MISSING_DEPENDENCY_MAPPING"),
        ("unknown", "UNKNOWN_DEPENDENCY_MAPPING"),
        ("duplicate", "DUPLICATE_DEPENDENCY_MAPPING"),
        ("reorder", "DEPENDENCY_MAPPING_ORDER_DRIFT"),
        ("eligible", "SAFE_BOUNDARY_VIOLATION"),
        ("profile", "SELECTION_MUST_REMAIN_UNSET"),
        ("provider", "SELECTION_MUST_REMAIN_UNSET"),
        ("evidence", "SELECTION_MUST_REMAIN_UNSET"),
        ("status", "FIXED_VALUE_VIOLATION"),
        ("policy", "FIXED_VALUE_VIOLATION"),
        ("satisfied", "FIXED_VALUE_VIOLATION"),
    ),
)
def test_dependency_admission_is_complete_exact_and_not_name_based(
    contract_document: dict[str, Any], mutation: str, expected_code: str
) -> None:
    document = copy.deepcopy(contract_document)
    rows = document["provider_neutral_staging_admission"][
        "dependency_admission_requirements"
    ]
    assert tuple(row["story_id"] for row in rows) == DEPENDENCY_STORIES
    if mutation == "missing":
        rows.pop()
    elif mutation == "unknown":
        rows[0]["story_id"] = "ST-UNKNOWN"
    elif mutation == "duplicate":
        rows[1]["story_id"] = rows[0]["story_id"]
    elif mutation == "reorder":
        rows[0], rows[1] = rows[1], rows[0]
    elif mutation == "eligible":
        rows[0]["current_eligible"] = True
    elif mutation == "profile":
        rows[0]["selected_profile_id"] = "aws-staging"
    elif mutation == "provider":
        rows[0]["selected_provider_name"] = "AWS"
    elif mutation == "evidence":
        rows[0]["evidence_references"] = ["aws-label"]
    elif mutation == "status":
        rows[0]["current_admission_status"] = "ELIGIBLE"
    elif mutation == "policy":
        rows[0]["required_policy"] = "AWS_REFERENCE"
    else:
        rows[0]["dependency_status"] = "SATISFIED"
    _assert_rejected(document, {expected_code})


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("missing", "MISSING_CAPABILITY_MAPPING"),
        ("unknown", "UNKNOWN_CAPABILITY_MAPPING"),
        ("duplicate", "DUPLICATE_CAPABILITY_MAPPING"),
        ("reorder", "CAPABILITY_MAPPING_ORDER_DRIFT"),
        ("mapping", "SELECTION_MUST_REMAIN_UNSET"),
        ("evidence", "SELECTION_MUST_REMAIN_UNSET"),
        ("status", "FIXED_VALUE_VIOLATION"),
        ("outcome", "FIXED_VALUE_VIOLATION"),
    ),
)
def test_capability_mapping_is_complete_exact_and_unconfigured(
    contract_document: dict[str, Any], mutation: str, expected_code: str
) -> None:
    document = copy.deepcopy(contract_document)
    rows = document["provider_neutral_staging_admission"][
        "capability_mapping_requirements"
    ]
    assert tuple(row["capability_id"] for row in rows) == CAPABILITY_IDS
    if mutation == "missing":
        rows.pop()
    elif mutation == "unknown":
        rows[0]["capability_id"] = "aws_account_present"
    elif mutation == "duplicate":
        rows[1]["capability_id"] = rows[0]["capability_id"]
    elif mutation == "reorder":
        rows[0], rows[1] = rows[1], rows[0]
    elif mutation == "mapping":
        rows[0]["selected_mapping"] = "AWS"
    elif mutation == "evidence":
        rows[0]["evidence_references"] = ["RDS"]
    elif mutation == "status":
        rows[0]["mapping_status"] = "CONFIGURED"
    else:
        rows[0]["required_outcome"] = "AWS_LABEL_PRESENT"
    _assert_rejected(document, {expected_code})


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        ("dependency_admission_policy", "partial_dependencies", "ALLOW"),
        ("dependency_admission_policy", "provider_label_only_dependency", "ALLOW"),
        ("dependency_admission_policy", "predecessor_completion_only", "ALLOW"),
        ("mapping_policy", "missing_mapping", "ALLOW"),
        ("mapping_policy", "partial_mapping", "ALLOW"),
        ("mapping_policy", "aws_label_only_mapping", "ALLOW"),
        ("mapping_policy", "reference_only_mapping", "ALLOW"),
        ("binding_policy", "implicit_target_binding", "ALLOWED"),
        ("binding_policy", "provider_name_or_reference_eligibility", "ALLOWED"),
        ("binding_policy", "predecessor_name_or_completion_eligibility", "ALLOWED"),
    ),
)
def test_partial_label_reference_and_predecessor_shortcut_policies_fail(
    contract_document: dict[str, Any],
    section: str,
    field: str,
    value: object,
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_staging_admission"][section][field] = value
    _assert_rejected(
        document,
        {"CONTRACT_SEMANTIC_DRIFT", "FIXED_VALUE_VIOLATION"},
    )


@pytest.mark.parametrize("field", EVIDENCE_EQUIVALENCE_FIELDS)
def test_every_equivalent_evidence_requirement_and_substitution_ban_is_normative(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    policy = document["provider_neutral_staging_admission"][
        "evidence_equivalence_policy"
    ]
    assert tuple(policy) == EVIDENCE_EQUIVALENCE_FIELDS
    policy[field] = "OPTIONAL" if policy[field] == "REQUIRED" else "ALLOWED"
    _assert_rejected(document, {"CONTRACT_SEMANTIC_DRIFT"})


@pytest.mark.parametrize("section", NORMATIVE_CONTRACT_SECTIONS)
def test_every_normative_contract_section_is_semantically_closed(
    contract_document: dict[str, Any], section: str
) -> None:
    document = copy.deepcopy(contract_document)
    value = document[section]
    if isinstance(value, dict):
        value[MARKER] = MARKER
    elif isinstance(value, list):
        value.append(MARKER)
    else:
        document[section] = MARKER
    _assert_rejected(
        document,
        {
            "CLOSED_SCHEMA_VIOLATION",
            "CONTRACT_SEMANTIC_DRIFT",
            "FIXED_VALUE_VIOLATION",
            "PREDECESSOR_SELECTION_SET",
            "TYPE_MISMATCH",
        },
    )


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        ("artifact_admission_intent", "signed_provenance", "OPTIONAL"),
        ("artifact_admission_intent", "critical_high_findings", "ALLOWED"),
        ("protected_environment_intent", "independent_human_approval", "OPTIONAL"),
        ("protected_environment_intent", "approval_bypass", "ALLOWED"),
        ("protected_environment_intent", "wildcard_subject", "ALLOWED"),
        ("protected_environment_intent", "static_cloud_secret", "ALLOWED"),
        ("migration_intent", "strategy", "CONTRACT_FIRST"),
        ("migration_intent", "migration_dry_run", "OPTIONAL"),
        ("migration_intent", "migration_owner_assignment", "OPTIONAL"),
        ("migration_intent", "independent_migration_review", "OPTIONAL"),
        ("migration_intent", "independent_migration_approval", "OPTIONAL"),
        ("migration_intent", "migration_self_approval", "ALLOWED"),
        ("migration_intent", "migration_review_bypass", "ALLOWED"),
        ("migration_intent", "direct_ddl", "ALLOWED"),
        ("health_security_runtime_intent", "security_check", "OPTIONAL"),
        ("health_security_runtime_intent", "local_fixture_as_live_evidence", "ALLOWED"),
        ("transport_security_intent", "all_staging_network_flows", "OPTIONAL"),
        ("transport_security_intent", "authenticated_encryption", "OPTIONAL"),
        (
            "transport_security_intent",
            "certificate_identity_and_hostname_verification",
            "OPTIONAL",
        ),
        ("transport_security_intent", "plaintext_transport", "ALLOWED"),
        ("transport_security_intent", "insecure_skip_verification", "ALLOWED"),
        (
            "transport_security_intent",
            "provider_managed_label_as_evidence",
            "ALLOWED",
        ),
        ("observability_alerting_intent", "alert_routes", "OPTIONAL"),
        ("observability_alerting_intent", "alert_bypass", "ALLOWED"),
        ("isolation_residency_budget_intent", "data_residency", "OPTIONAL"),
        ("isolation_residency_budget_intent", "budget_limit", "OPTIONAL"),
        ("target_adapter_intent", "provider_name_only_admission", "ALLOWED"),
        ("target_adapter_intent", "provider_sdk_types_in_domain", "ALLOWED"),
        ("rollback_restore_intent", "restore_rehearsal", "OPTIONAL"),
        ("rollback_restore_intent", "rollback_without_human_gate", "ALLOWED"),
    ),
)
def test_security_operations_release_and_recovery_gates_cannot_be_downgraded(
    contract_document: dict[str, Any], section: str, field: str, value: str
) -> None:
    document = copy.deepcopy(contract_document)
    document[section][field] = value
    _assert_rejected(document, {"CONTRACT_SEMANTIC_DRIFT"})


@pytest.mark.parametrize("decision_id", OPEN_DECISIONS)
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("resolved", True),
        ("blocking", False),
        ("status", "RESOLVED"),
        ("safe_default", "LIVE"),
    ),
)
def test_all_inherited_open_decisions_remain_unresolved_and_blocking(
    contract_document: dict[str, Any],
    decision_id: str,
    field: str,
    value: object,
) -> None:
    document = copy.deepcopy(contract_document)
    assert tuple(document["open_decision_boundary"]) == OPEN_DECISIONS
    document["open_decision_boundary"][decision_id][field] = value
    _assert_rejected(document)


@pytest.mark.parametrize("field", EXECUTION_FORBIDDEN_FIELDS)
def test_every_external_execution_surface_remains_forbidden(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"][field] = "ALLOWED"
    _assert_rejected(document, {"FIXED_VALUE_VIOLATION"})


@pytest.mark.parametrize("field", ACTION_COUNT_FIELDS)
@pytest.mark.parametrize("value", (1, True))
def test_every_action_count_is_exact_integer_zero(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    assert tuple(document["execution_boundary"]["action_counts"]) == ACTION_COUNT_FIELDS
    document["execution_boundary"]["action_counts"][field] = value
    _assert_rejected(
        document,
        {"SAFE_BOUNDARY_VIOLATION" if type(value) is int else "TYPE_MISMATCH"},
    )


@pytest.mark.parametrize("field", OPERATION_FIELDS)
def test_every_operation_is_forbidden(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    assert tuple(document["execution_boundary"]["operations"]) == OPERATION_FIELDS
    document["execution_boundary"]["operations"][field] = "ALLOWED"
    _assert_rejected(document, {"FIXED_VALUE_VIOLATION"})


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("reorder", "FIXED_VALUE_VIOLATION"),
        ("remove", "FIXED_VALUE_VIOLATION"),
        ("enable", "FIXED_VALUE_VIOLATION"),
        ("execute", "FIXED_VALUE_VIOLATION"),
        ("external", "FIXED_VALUE_VIOLATION"),
        ("nonzero", "SAFE_BOUNDARY_VIOLATION"),
        ("bool", "TYPE_MISMATCH"),
    ),
)
def test_logical_phases_remain_exactly_ordered_disabled_and_zero(
    contract_document: dict[str, Any], mutation: str, expected_code: str
) -> None:
    document = copy.deepcopy(contract_document)
    phases = document["logical_phases"]
    if mutation == "reorder":
        phases[0], phases[1] = phases[1], phases[0]
    elif mutation == "remove":
        phases.pop()
    elif mutation == "enable":
        phases[0]["status"] = "ENABLED"
    elif mutation == "execute":
        phases[0]["execution_status"] = "EXECUTED"
    elif mutation == "external":
        phases[0]["external_action"] = "ALLOWED"
    elif mutation == "nonzero":
        phases[0]["action_count"] = 1
    else:
        phases[0]["action_count"] = False
    _assert_rejected(document, {expected_code})


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    (
        (f"document: safe\ndocument: {MARKER}\n", "YAML_INVALID"),
        (f"value: &blocked {MARKER}\ncopy: *blocked\n", "YAML_ALIAS_FORBIDDEN"),
        (
            f"value: !!python/object/apply:builtins.str [{MARKER}]\n",
            "YAML_TAG_FORBIDDEN",
        ),
    ),
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


def test_json_duplicate_keys_fail_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "hostile.json"
    path.write_text(f'{{"safe": 1, "safe": "{MARKER}"}}', encoding="utf-8")
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.load_json(path)
    assert captured.value.code == "JSON_DUPLICATE_KEY"
    assert MARKER not in str(captured.value)


def test_source_inventory_digest_duplicate_reorder_and_unknown_fail_closed(
    contract_document: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    for mutation in ("digest", "duplicate", "reorder", "unknown"):
        document = copy.deepcopy(contract_document)
        if mutation == "digest":
            document["sources"][0]["sha256"] = "0" * 64
        elif mutation == "duplicate":
            document["sources"][1] = copy.deepcopy(document["sources"][0])
        elif mutation == "reorder":
            document["sources"][0], document["sources"][1] = (
                document["sources"][1],
                document["sources"][0],
            )
        else:
            document["sources"][0]["uri"] = "repo://unknown"
        monkeypatch.setattr(
            generator,
            "EXPECTED_CONTRACT_SEMANTIC_SHA256",
            generator.semantic_sha256(document),
        )
        _assert_rejected(document, {"SOURCE_DUPLICATE", "SOURCE_INVENTORY_DRIFT"})


def _copy_pinned_sources(target_root: Path) -> None:
    for relative in generator.PINNED_SOURCES:
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
) -> tuple[dict[str, Any], str]:
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
    raise AssertionError("predecessor binding missing")


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
    binding, prefix = _predecessor_binding(document, relative)
    binding[f"{prefix}_sha256"] = new_digest
    monkeypatch.setattr(
        generator,
        "EXPECTED_CONTRACT_SEMANTIC_SHA256",
        generator.semantic_sha256(document),
    )


@pytest.mark.parametrize("relative", PREDECESSOR_SOURCE_PATHS)
def test_every_predecessor_raw_byte_drift_fails_closed(
    tmp_path: Path, contract_document: dict[str, Any], relative: str
) -> None:
    assert tuple(generator.PREDECESSOR_SOURCES) == PREDECESSOR_SOURCE_PATHS
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == "SOURCE_DIGEST_MISMATCH"


def _tamper_predecessor(document: dict[str, Any], relative: str) -> None:
    if relative.endswith(".json"):
        document["document"]["executable"] = True
    elif "DESIGN_HANDOFF" in relative:
        document["approved_scope"][0] = MARKER
    else:
        document["document"]["formal_verification"] = "EXECUTED"


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
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_SEMANTIC_DRIFT"


def _predecessor_contract_and_plan_paths(story_id: str) -> tuple[str, str]:
    for specification in generator.PREDECESSOR_SPECIFICATIONS:
        if specification[1] == story_id:
            return specification[4], specification[5]
    raise AssertionError("predecessor specification missing")


def _render_without_owner_validation(story_id: str, contract: dict[str, Any]) -> bytes:
    if story_id == "ST-1502":
        from scripts import build_st1502_data_services as owner

        return owner.render_reference_plan(owner.DataServicesModel(contract=contract))
    if story_id == "ST-1503":
        from scripts import build_st1503_compute_edge as owner

        return owner.render_reference_plan(owner.ComputeEdgeModel(contract=contract))
    if story_id == "ST-1504":
        from scripts import build_st1504_github_oidc as owner

        return owner.render_reference_plan(owner.GithubOidcModel(contract=contract))
    raise AssertionError("unsupported coordinated-rebind story")


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
        document,
        contract_relative,
        generator.sha256_file(contract_path),
        monkeypatch,
    )
    _rebind_predecessor_raw_digest(
        document,
        plan_relative,
        generator.sha256_file(plan_path),
        monkeypatch,
    )
    semantic_hashes = dict(generator.PREDECESSOR_SEMANTIC_SHA256)
    semantic_hashes[contract_relative] = generator.semantic_sha256(predecessor_contract)
    semantic_hashes[plan_relative] = generator.semantic_sha256(plan_document)
    monkeypatch.setattr(generator, "PREDECESSOR_SEMANTIC_SHA256", semantic_hashes)
    contract_binding, contract_prefix = _predecessor_binding(
        document, contract_relative
    )
    contract_binding[f"{contract_prefix}_semantic_sha256"] = semantic_hashes[
        contract_relative
    ]
    plan_binding, plan_prefix = _predecessor_binding(document, plan_relative)
    plan_binding[f"{plan_prefix}_semantic_sha256"] = semantic_hashes[plan_relative]
    monkeypatch.setattr(
        generator,
        "EXPECTED_CONTRACT_SEMANTIC_SHA256",
        generator.semantic_sha256(document),
    )

    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_SEMANTIC_DRIFT"
    assert MARKER not in str(captured.value)


PLAN_PATHS = (
    "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
    "infra/terraform/data-services/data-services.reference-plan.v1.json",
    "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json",
    "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json",
)


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
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_GENERATED_DRIFT"


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
    monkeypatch.setattr(
        generator,
        "EXPECTED_CONTRACT_SEMANTIC_SHA256",
        generator.semantic_sha256(document),
    )


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
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code in {
        "CLOSED_SCHEMA_VIOLATION",
        "FIXED_VALUE_VIOLATION",
        "SAFE_BOUNDARY_VIOLATION",
        "SELECTION_MUST_REMAIN_UNSET",
        "HANDOFF_SEMANTIC_DRIFT",
    }


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


def test_oversized_yaml_and_json_fail_before_parsing(tmp_path: Path) -> None:
    for name, loader in (
        ("large.yaml", generator.load_yaml),
        ("large.json", generator.load_json),
    ):
        path = tmp_path / name
        path.write_bytes(b"x" * (generator.MAX_DOCUMENT_BYTES + 1))
        with pytest.raises(generator.StagingDeploymentContractError) as captured:
            loader(path)
        assert captured.value.code in {"YAML_SIZE_LIMIT", "JSON_SIZE_LIMIT"}
