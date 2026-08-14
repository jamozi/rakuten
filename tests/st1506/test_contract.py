"""Positive Production deployment reference semantics for ST-1506."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from scripts import build_st1505_staging_deployment as predecessor_generator
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


def test_wordpress_signed_delivery_interface_is_exact_data_only_boundary(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    interface = _mapping(
        production_model.contract["wordpress_signed_delivery_interface"]
    )
    assert tuple(interface) == generator.WORDPRESS_INTERFACE_KEYS
    assert (
        generator.reference_plan_document(production_model)[
            "wordpress_signed_delivery_interface"
        ]
        == interface
    )
    status = _mapping(interface["interface_status"])
    assert status == {
        "classification": (
            "SOURCE_DERIVED_NON_EXECUTABLE_WORDPRESS_SIGNED_DELIVERY_INTERFACE"
        ),
        "executable": False,
        "activation_status": "DISABLED",
        "configuration_status": "NOT_CONFIGURED",
        "runtime_status": "NOT_EXECUTED",
        "live_status": "NOT_EXECUTED",
        "formal_verification_status": "NOT_EXECUTED",
        "automatic_delivery_authority": "NONE",
        "manual_delivery_authority": "NONE",
        "external_access": "FORBIDDEN",
        "credential_access": "FORBIDDEN",
        "action_count": 0,
    }
    assert type(status["action_count"]) is int


def test_wordpress_trust_release_package_and_replay_rules_are_closed(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    interface = _mapping(
        production_model.contract["wordpress_signed_delivery_interface"]
    )
    bootstrap = _mapping(interface["trust_bootstrap"])
    assert bootstrap["installation"] == "FUTURE_MANUAL_OWNER_GATED_ONLY"
    assert bootstrap["pinned_update_service_origin"] == "REQUIRED_NOT_CONFIGURED"
    assert bootstrap["pinned_offline_root_algorithm"] == "Ed25519"
    assert bootstrap["pinned_root_public_key"] == "REQUIRED_NOT_CONFIGURED"
    assert bootstrap["updater_self_update"] == "FORBIDDEN"
    assert bootstrap["cross_origin_redirect"] == "FORBIDDEN"

    encoding = _mapping(interface["canonical_encoding"])
    assert encoding["format"] == "RFC_8785_CANONICAL_JSON"
    assert encoding["duplicate_keys"] == "REJECT"
    assert encoding["floating_point_values"] == "FORBIDDEN"
    assert encoding["unknown_fields"] == "REJECT"

    keyring = _mapping(interface["keyring"])
    assert keyring["signer"] == "PINNED_OFFLINE_ROOT"
    assert keyring["keyring_epoch"] == "STRICTLY_MONOTONIC_UNSIGNED_INTEGER"
    assert keyring["required_release_purposes"] == [
        "RELEASE_SIGNER",
        "OWNER_RELEASE_APPROVAL_SIGNER",
    ]
    release_set = _mapping(interface["release_set"])
    assert release_set["signature_requirement"] == (
        "TWO_DISTINCT_ACTIVE_KEYS_OVER_IDENTICAL_CANONICAL_ENVELOPE"
    )
    assert release_set["release_sequence"] == ("STRICTLY_MONOTONIC_UNSIGNED_INTEGER")
    assert release_set["semantic_version_as_replay_control"] == "FORBIDDEN"

    package = _mapping(interface["package_admission"])
    assert package["transport"] == "EXACT_PINNED_HTTPS_ORIGIN_ONLY"
    assert package["redirect"] == "FORBIDDEN"
    assert package["exact_limits"] == "REQUIRED_NOT_CONFIGURED"
    assert {
        "ABSOLUTE_PATH",
        "DOT_SEGMENT",
        "SYMLINK",
        "HARD_LINK",
        "DUPLICATE_MEMBER",
        "CASE_FOLD_COLLISION",
        "UNICODE_NORMALIZATION_COLLISION",
        "COMPRESSION_LIMIT_EXCEEDED",
    }.issubset(set(package["reject_entries"]))
    replay = _mapping(interface["replay_and_journal"])
    assert replay["sequence_consumed_before_filesystem_mutation"] is True
    assert replay["equal_or_lower_release_sequence"] == "REJECT"
    assert replay["restored_database_may_lower_high_water"] is False
    assert replay["blind_retry"] == "FORBIDDEN"


def test_wordpress_restore_authorization_receipts_and_control_planes_are_inert(
    production_model: generator.ProductionDeploymentModel,
) -> None:
    interface = _mapping(
        production_model.contract["wordpress_signed_delivery_interface"]
    )
    machine = _mapping(interface["transaction_state_machine"])
    assert machine["initial_state"] == "DISABLED"
    assert machine["runtime_transition_execution"] == "FORBIDDEN"
    assert machine["concurrent_update"] == "STOP"
    assert machine["partial_switch"] == "STOP"
    assert machine["journal_corruption"] == "STOP"

    health = _mapping(interface["health_and_restore"])
    assert health["failed_new_release_restore_attempt_limit"] == 1
    assert type(health["failed_new_release_restore_attempt_limit"]) is int
    assert health["restore_may_reduce_high_water"] is False
    assert health["successful_restore_result"] == "RESTORED_STOPPED"
    assert health["further_automatic_write_after_restore"] == "FORBIDDEN"

    authorization = _mapping(interface["authorization"])
    assert authorization["authentication_transport"] == (
        "WORDPRESS_APPLICATION_PASSWORD_OVER_HTTPS"
    )
    assert authorization["custom_minimal_roles"] == "REQUIRED_NOT_CONFIGURED"
    assert authorization["update_custom_capability"] == "REQUIRED_NOT_CONFIGURED"
    assert authorization["arbitrary_url_file_path_code_or_version_input"] == (
        "FORBIDDEN"
    )
    receipts = _mapping(interface["receipts"])
    assert receipts["tamper_evident_required"] is True
    assert receipts["sanitized_required"] is True
    assert "APPLICATION_PASSWORD" in receipts["forbidden_fields"]
    assert "SIGNING_PRIVATE_KEY" in receipts["forbidden_fields"]

    separation = _mapping(interface["control_plane_separation"])
    assert separation["code_delivery_may_publish_content"] is False
    assert separation["publication_may_trigger_deployment"] is False
    assert separation["kill_switches_separate"] is True
    assert separation["failed_code_delivery_may_modify_public_content"] is False
    evidence = _mapping(interface["evidence_boundary"])
    assert evidence["local_tests"] == "DEVELOPER_EVIDENCE_ONLY"
    assert all(value == "NOT_EXECUTED" for value in list(evidence.values())[1:])


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
        name: 0 for name in predecessor_generator.ACTION_COUNT_NAMES
    }
    transitive = _mapping(binding["transitive_predecessor_bindings"])
    predecessor = predecessor_generator.load_and_validate_contract(REPOSITORY_ROOT)
    assert tuple(transitive) == (
        "data_services",
        "compute_edge",
        "deployment_identity",
    )
    assert transitive == predecessor.contract["predecessor_bindings"]


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
