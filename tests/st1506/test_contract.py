"""Positive Production deployment reference semantics for ST-1506."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from scripts import build_st1506_production_deployment as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_contract_loads_as_closed_non_executable_definition(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    document = _mapping(production_model.contract["document"])
    assert document == {
        "id": "RAOS-PRODUCTION-DEPLOYMENT-DEFINITION-001",
        "version": "1.1.0",
        "story_id": "ST-1506",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "classification": (
            "SOURCE_DERIVED_NON_EXECUTABLE_PRODUCTION_DEPLOYMENT_DEFINITION"
        ),
        "executable": False,
        "activation_status": "DISABLED",
        "formal_verification": "NOT_EXECUTED",
    }
    assert tuple(production_model.contract) == generator.TOP_LEVEL_KEYS


def test_immediate_predecessor_and_all_transitive_bindings_are_exact(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    binding = _mapping(production_model.contract["predecessor_binding"])
    assert binding["story_id"] == "ST-1505"
    assert (
        binding["contract_sha256"]
        == generator.PREDECESSOR_SOURCES[
            "changes/st-1505/contracts/staging-deployment.v1.yaml"
        ]
    )
    assert (
        binding["reference_plan_sha256"]
        == generator.PREDECESSOR_SOURCES[
            "infra/terraform/staging/staging-deployment.reference-plan.v1.json"
        ]
    )
    assert binding["required_contract_non_executable"] is True
    assert binding["required_reference_plan_executable"] is False
    assert binding["required_activation_status"] == "DISABLED"
    assert binding["required_live_provider_calls"] == "FORBIDDEN"
    assert binding["required_external_writes"] == "FORBIDDEN"
    assert binding["required_selected_values"] == "UNSET"
    assert binding["required_formal_tst_009"] == "NOT_EXECUTED"
    assert binding["required_formal_tst_022"] == "NOT_EXECUTED"
    assert binding["required_action_counts"] == {
        name: 0 for name in generator.PREDECESSOR_ACTION_COUNT_NAMES
    }
    transitive = _mapping(binding["transitive_predecessor_bindings"])
    predecessor = _mapping(
        generator.load_yaml(
            REPOSITORY_ROOT / "changes/st-1505/contracts/staging-deployment.v1.yaml"
        )
    )
    assert tuple(transitive) == (
        "data_services",
        "compute_edge",
        "deployment_identity",
    )
    assert transitive == predecessor["predecessor_bindings"]


def test_provider_neutral_admission_is_closed_unselected_and_evidence_equal(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    admission = _mapping(production_model.contract["provider_neutral_admission"])
    assert tuple(admission) == generator.PROVIDER_NEUTRAL_ADMISSION_KEYS
    assert admission["classification"] == (
        "STRICT_PROVIDER_NEUTRAL_CAPABILITY_ADMISSION"
    )
    assert admission["admission_status"] == "NOT_EVALUATED"
    assert admission["eligible"] is False
    assert admission["selected_profile_id"] is None
    assert admission["selected_profile_kind"] is None
    assert admission["selected_provider_name"] is None
    assert admission["default_profile_id"] is None
    assert admission["fallback_profile_id"] is None
    assert admission["concrete_alternate_provider_selected"] is False
    assert admission["eligible_profile_kinds"] == [
        "AWS",
        "OTHER_CLOUD",
        "OWNER_MANAGED_INFRASTRUCTURE",
    ]

    policy = _mapping(admission["mapping_policy"])
    assert policy["cardinality"] == "EXACTLY_ONE_PER_REQUIRED_CAPABILITY"
    assert policy["required_mapping_count"] == len(generator.REQUIRED_CAPABILITY_IDS)
    assert policy["configured_mapping_count"] == 0
    assert policy["complete_mapping"] is False
    assert all(
        policy[field] == "REJECT"
        for field in (
            "missing_mapping",
            "unknown_mapping",
            "duplicate_mapping",
            "implicit_mapping",
            "partial_mapping",
            "provider_label_only",
        )
    )

    aws = _mapping(admission["aws_reference_boundary"])
    assert aws["canonical_decision_id"] == "INT-DEC-007"
    assert aws["reference_profile"] == "AWS_TOKYO"
    assert aws["role"] == "OPTIONAL_HISTORICAL_REFERENCE_ONLY"
    assert all(
        aws[field] is False
        for field in (
            "default",
            "implicit_fallback",
            "selected_binding",
            "eligibility_shortcut",
            "admission_requirement",
            "evidence_substitute",
        )
    )
    predecessor = _mapping(admission["predecessor_reference_boundary"])
    assert predecessor["st_1501_through_st_1505"] == (
        "IMMUTABLE_AWS_SPECIFIC_HISTORY_AND_REFERENCE_ONLY"
    )
    assert predecessor["mandatory_provider_semantics"] is False
    assert predecessor["provider_selection_authority"] == "NONE"
    assert predecessor["eligibility_authority"] == "NONE"

    evidence = _mapping(admission["evidence_equivalence_policy"])
    assert evidence["same_requirements_for_all_profile_kinds"] is True
    assert evidence["provider_label_as_evidence"] == "FORBIDDEN"
    assert evidence["reference_metadata_as_evidence"] == "FORBIDDEN"
    assert evidence["predecessor_completion_as_evidence"] == "FORBIDDEN"
    rows = cast(list[dict[str, Any]], admission["capability_mapping_requirements"])
    assert [row["capability_id"] for row in rows] == list(
        generator.REQUIRED_CAPABILITY_IDS
    )
    for row in rows:
        capability_id = cast(str, row["capability_id"])
        assert (
            row["required_outcome"]
            == (generator.REQUIRED_CAPABILITY_OUTCOMES[capability_id])
        )
        assert row["selected_mapping"] is None
        assert row["evidence_references"] == []
        assert row["mapping_status"] == "REQUIRED_NOT_CONFIGURED"


def test_provider_neutral_rules_do_not_weaken_release_gates_or_status(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    plan = generator.reference_plan_document(production_model)
    admission = _mapping(plan["provider_neutral_admission"])
    activation = _mapping(plan["activation"])
    approvals = _mapping(plan["human_approval_gates"])
    verification = _mapping(plan["verification_boundary"])
    assert admission["eligible"] is False
    assert activation["enabled"] is False
    assert activation["status"] == "DISABLED"
    assert approvals["populated_artifact_count"] == 0
    assert approvals["human_control_required"] is True
    assert verification["formal_tst_032"] == "NOT_EXECUTED"
    assert verification["release"] == "NOT_EXECUTED"
    assert verification["production"] == "NOT_EXECUTED"
    assert verification["effective_canonical_status"] == "UNCHANGED"


def test_open_decisions_keep_only_documented_safe_defaults(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    defaults = _mapping(production_model.contract["open_decision_defaults"])
    assert tuple(defaults) == (
        "production_budget",
        "notification_channels",
        "production_region_and_data_residency",
        "production_provider_credentials",
    )
    assert defaults["production_budget"]["selected_budget"] is None
    assert defaults["production_budget"]["selected_acceptable_loss"] is None
    assert defaults["production_budget"]["safe_default"] == "PRODUCTION_DISABLED"
    notification = defaults["notification_channels"]
    assert notification["selected_channels"] == []
    assert notification["selected_escalation_contacts"] == []
    assert notification["safe_default"] == "LOCAL_LOG_ONLY"
    region = defaults["production_region_and_data_residency"]
    assert region["reference_region_metadata"] == "ap-northeast-1"
    assert region["reference_metadata_only"] is True
    assert region["selected_production_region"] is None
    assert region["production_apply"] == "FORBIDDEN"
    credentials = defaults["production_provider_credentials"]
    assert credentials["safe_default"] == "RECORDED_FIXTURES_ONLY"
    assert credentials["selected_accounts"] == []
    assert credentials["selected_permissions"] == []
    assert credentials["selected_credentials"] == []
    assert credentials["selected_secrets"] == []


def test_production_environment_is_inert_and_region_is_metadata_only(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    environment = _mapping(
        generator.reference_plan_document(production_model)["environment"]
    )
    assert environment["label"] == "PRODUCTION"
    assert environment["configuration_status"] == "NOT_CONFIGURED"
    assert environment["activation_status"] == "DISABLED"
    assert environment["runtime_status"] == "NOT_EXECUTED"
    assert environment["live_status"] == "NOT_EXECUTED"
    assert environment["reference_region_metadata"] == "ap-northeast-1"
    assert environment["reference_region_use"] == "METADATA_ONLY"
    assert environment["apply_target"] is None
    assert environment["data_source"] == "RECORDED_FIXTURES_ONLY"
    assert environment["credential_material"] == "ABSENT"
    assert environment["external_access"] == "FORBIDDEN"


def test_every_actual_binding_is_null_or_empty(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    selected = _mapping(
        generator.reference_plan_document(production_model)["selected_bindings"]
    )
    assert selected
    assert all(value is None or value == [] for value in selected.values())


def test_four_human_controlled_artifacts_are_distinct_and_unpopulated(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    gates = _mapping(
        generator.reference_plan_document(production_model)["human_approval_gates"]
    )
    artifact_types: list[str] = []
    for name in generator.APPROVAL_ARTIFACT_NAMES:
        artifact = _mapping(gates[name])
        artifact_types.append(cast(str, artifact["artifact_type"]))
        assert artifact["artifact_value"] is None
        assert artifact["artifact_digest"] is None
        assert artifact["human_reviewer"] is None
        assert artifact["approval_status"] == "NOT_PROVIDED"
    assert len(set(artifact_types)) == 4
    assert gates["populated_artifact_count"] == 0
    for field in (
        "self_approval",
        "automation_as_approval",
        "synthesized_approval",
        "forged_approval",
        "shared_artifact_slots",
        "bypass",
        "override",
    ):
        assert gates[field] == "FORBIDDEN"


def test_all_admission_protection_observation_and_rollback_requirements_are_unset(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    plan = generator.reference_plan_document(production_model)
    required_fields = {
        "artifact_admission": (
            "immutable_digest",
            "sbom",
            "vulnerability_scan",
            "signed_provenance",
            "promote_without_rebuild",
            "digest_binding",
        ),
        "protected_environment": (
            "protected_environment",
            "exact_repository",
            "exact_ref",
            "exact_workflow",
            "deployment_role",
            "least_privilege",
            "human_reviewers",
        ),
        "migration": (
            "compatibility_gate",
            "backward_compatibility",
            "forward_compatibility",
            "migration_dry_run",
            "rollback_compatibility",
        ),
        "canary": (
            "configuration",
            "cohort_definition",
            "traffic_policy",
            "observation_window",
            "success_criteria",
            "abort_criteria",
        ),
        "observability": (
            "telemetry",
            "error_budget",
            "alerts",
            "dashboards",
            "release_markers",
            "notification_routing",
        ),
        "health_and_smoke": (
            "liveness_check",
            "readiness_check",
            "migration_compatibility_check",
            "smoke_check",
            "endpoint_binding",
        ),
        "rollback": (
            "prior_immutable_artifact",
            "prior_configuration",
            "known_safe_snapshot",
            "migration_compatibility",
            "trigger_criteria",
            "human_decision",
        ),
    }
    for section, fields in required_fields.items():
        values = _mapping(plan[section])
        for field in fields:
            assert values[field] == "REQUIRED_NOT_CONFIGURED"
    canary = _mapping(plan["canary"])
    rollback = _mapping(plan["rollback"])
    assert canary["automatic_advance"] == "FORBIDDEN"
    assert canary["traffic_mutation"] == "FORBIDDEN"
    assert rollback["automatic_rollback"] == "FORBIDDEN"


def test_logical_phases_and_all_action_counts_are_exactly_zero(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    plan = generator.reference_plan_document(production_model)
    phases = cast(list[dict[str, Any]], plan["logical_phases"])
    assert [phase["name"] for phase in phases] == list(generator.PHASE_NAMES)
    assert all(
        phase
        == {
            "name": phase["name"],
            "status": "DISABLED",
            "execution_status": "NOT_EXECUTED",
            "action": "FORBIDDEN",
            "auto_advance": "FORBIDDEN",
            "action_count": 0,
        }
        for phase in phases
    )
    assert plan["action_counts"] == {name: 0 for name in generator.ACTION_COUNT_NAMES}
    assert all(type(value) is int for value in plan["action_counts"].values())


def test_generated_plan_is_non_executable_and_formal_live_work_is_unexecuted(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    plan = generator.reference_plan_document(production_model)
    document = _mapping(plan["document"])
    assert document["executable"] is False
    assert document["story_id"] == "ST-1506"
    activation = _mapping(plan["activation"])
    assert activation["enabled"] is False
    assert activation["status"] == "DISABLED"
    assert all(value == "FORBIDDEN" for value in activation["operations"].values())
    boundary = _mapping(plan["verification_boundary"])
    assert boundary["formal_tst_032"] == "NOT_EXECUTED"
    for field in (
        "hosted_ci",
        "staging",
        "live_provider",
        "migration",
        "smoke",
        "canary",
        "rollback",
        "release",
        "production",
        "status_transition",
    ):
        assert boundary[field] == "NOT_EXECUTED"


def test_generated_json_matches_renderer_and_no_hcl_or_workflow_exists(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    plan_path = REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH
    assert json.loads(plan_path.read_bytes()) == generator.reference_plan_document(
        production_model
    )
    production_dir = plan_path.parent
    assert sorted(path.name for path in production_dir.iterdir()) == [plan_path.name]
    assert not list(production_dir.rglob("*.tf"))
    assert not list(production_dir.rglob("*.hcl"))
    assert not (REPOSITORY_ROOT / ".github/workflows/st-1506.yml").exists()
