"""Positive provider-neutral contract and reference-plan semantics for ST-1502."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from scripts import build_st1502_data_services as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_contract_loads_as_closed_interface_only_model(
    data_services_model: generator.DataServicesModel,
) -> None:
    assert data_services_model.contract["document"] == {
        "id": "RAOS-DATA-SERVICES-FOUNDATION-001",
        "version": "1.1.0",
        "story_id": "ST-1502",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "formal_verification": "NOT_EXECUTED",
    }
    assert set(data_services_model.contract) == generator.TOP_LEVEL_KEYS


def test_direct_handoff_and_predecessor_are_hash_bound(
    data_services_model: generator.DataServicesModel,
) -> None:
    sources = data_services_model.contract["sources"]
    assert isinstance(sources, list)
    assert {row["uri"]: row["sha256"] for row in sources if isinstance(row, dict)} == {
        f"repo://{path}": digest for path, digest in generator.PINNED_SOURCES.items()
    }
    binding = data_services_model.contract["predecessor_binding"]
    assert binding == generator.EXPECTED_SECTIONS["predecessor_binding"]
    assert binding["required_provider_policy"] == (
        "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION"
    )
    assert binding["required_admission_status"] == "NOT_EVALUATED"
    assert binding["required_eligible"] is False
    assert binding["required_activation_status"] == "DISABLED"
    assert binding["required_resource_payloads"] == "FORBIDDEN"


def test_aws_is_optional_historical_reference_mapping_only(
    data_services_model: generator.DataServicesModel,
) -> None:
    plan = generator.reference_plan_document(data_services_model)
    reference = _mapping(plan["reference_architecture"])
    assert reference == generator.EXPECTED_SECTIONS["reference_architecture"]
    assert reference["cloud"] == "AWS"
    assert reference["inherited_from"] == "INT-DEC-007"
    assert reference["service_mappings"] == generator._aws_reference_service_mappings()
    for field in (
        "default",
        "implicit_fallback",
        "selected_binding",
        "eligibility_shortcut",
        "admission_requirement",
        "evidence_substitute",
    ):
        assert reference[field] is False


def test_no_provider_service_or_profile_is_selected_or_defaulted(
    data_services_model: generator.DataServicesModel,
) -> None:
    plan = generator.reference_plan_document(data_services_model)
    admission = _mapping(plan["provider_neutral_data_services_admission"])
    assert admission["admission_status"] == "NOT_EVALUATED"
    assert admission["eligible"] is False
    for field in (
        "selected_profile_id",
        "selected_profile_kind",
        "selected_provider_name",
        "default_profile_id",
        "fallback_profile_id",
    ):
        assert admission[field] is None
    assert admission["concrete_alternate_provider_selected"] is False
    assert admission["cross_capability_security_policy"] == {
        "transport_encryption": "REQUIRED_FOR_ALL_DATA_SERVICE_INTERACTIONS",
        "encryption_at_rest": "REQUIRED_FOR_ALL_PERSISTED_DATA",
        "selected_exceptions": [],
    }
    for binding_name in generator.DATA_SERVICE_BINDING_NAMES:
        assert admission["binding_policy"][binding_name] == {
            "selected": None,
            "default": None,
            "fallback": None,
        }
    selection = _mapping(plan["selected_configuration"])
    assert all(value is None or value == [] for value in selection.values())


def test_complete_exact_capability_mapping_is_required_before_eligibility(
    data_services_model: generator.DataServicesModel,
) -> None:
    admission = _mapping(
        generator.reference_plan_document(data_services_model)[
            "provider_neutral_data_services_admission"
        ]
    )
    policy = admission["mapping_policy"]
    assert policy["required_mapping_mode"] == "EXACTLY_ONE_PER_REQUIRED_CAPABILITY"
    assert policy["required_capability_count"] == len(
        generator.DATA_SERVICE_CAPABILITY_OUTCOMES
    )
    assert policy["configured_mapping_count"] == 0
    assert policy["complete_mapping"] is False
    for field in (
        "missing_mapping",
        "unknown_mapping",
        "duplicate_mapping",
        "implicit_mapping",
        "partial_mapping",
        "provider_label_only_mapping",
        "service_label_only_mapping",
        "reference_only_mapping",
    ):
        assert policy[field] == "REJECT"
    rows = admission["capability_mapping_requirements"]
    assert [row["capability_id"] for row in rows] == [
        capability_id
        for capability_id, _required_outcome in generator.DATA_SERVICE_CAPABILITY_OUTCOMES
    ]
    assert [row["required_outcome"] for row in rows] == [
        required_outcome
        for _capability_id, required_outcome in generator.DATA_SERVICE_CAPABILITY_OUTCOMES
    ]
    assert all(
        row["selected_mapping"] is None
        and row["evidence_refs"] == []
        and row["mapping_status"] == "REQUIRED_NOT_CONFIGURED"
        for row in rows
    )


def test_relational_object_and_queue_intents_are_provider_neutral_and_safe(
    data_services_model: generator.DataServicesModel,
) -> None:
    services = _mapping(
        generator.reference_plan_document(data_services_model)["logical_data_services"]
    )
    relational = _mapping(services["relational_persistence"])
    assert relational["service_contract"] == (
        "POSTGRESQL_COMPATIBLE_RELATIONAL_PERSISTENCE"
    )
    assert relational["private_only"] == "REQUIRED"
    assert relational["publicly_accessible"] is False
    assert relational["transport_encryption"] == "REQUIRED_NOT_CONFIGURED"
    assert relational["migration_framework_compatibility"] == (
        "REQUIRED_NOT_CONFIGURED"
    )
    assert relational["restore_test"] == "REQUIRED_NOT_EXECUTED"
    assert all(
        value is None or value == [] for value in relational["selected"].values()
    )

    storage = _mapping(services["object_storage"])
    assert storage["service_contract"] == "PRIVATE_VERSIONED_OBJECT_STORAGE"
    assert [row["role"] for row in storage["roles"]] == list(generator.BUCKET_ROLES)
    assert all(row["physical_name"] is None for row in storage["roles"])
    assert all(row["resource_identifier"] is None for row in storage["roles"])
    assert storage["public_access"] == "FORBIDDEN"
    assert storage["transport_encryption"] == "REQUIRED_NOT_CONFIGURED"
    assert storage["force_destroy"] == "FORBIDDEN"
    assert storage["automatic_deletion"] == "FORBIDDEN"
    assert storage["retention_days"] is None
    assert storage["roles"][0]["immutability"] == "REQUIRED_NOT_CONFIGURED"

    queue = _mapping(services["queue"])
    assert queue["delivery_semantics"] == "AT_LEAST_ONCE_REQUIRED_NOT_CONFIGURED"
    assert queue["duplicate_delivery"] == "EXPECTED"
    assert queue["consumer_idempotency"] == "REQUIRED_NOT_CONFIGURED"
    assert queue["transport_encryption"] == "REQUIRED_NOT_CONFIGURED"
    assert [row["class"] for row in queue["classes"]] == list(generator.QUEUE_CLASSES)
    for row in queue["classes"]:
        assert row["dlq"] == "REQUIRED_NOT_CONFIGURED"
        assert row["redrive_control"] == "REQUIRED_NOT_CONFIGURED"
        assert all(value is None for value in row["selected"].values())


def test_secret_key_recovery_observability_and_residency_boundaries_are_exact(
    data_services_model: generator.DataServicesModel,
) -> None:
    services = _mapping(
        generator.reference_plan_document(data_services_model)["logical_data_services"]
    )
    assert services["secrets"] == generator.EXPECTED_SECTIONS["secrets_intent"]
    assert (
        services["key_management"]
        == generator.EXPECTED_SECTIONS["key_management_intent"]
    )
    assert services["recovery"] == generator.EXPECTED_SECTIONS["recovery_intent"]
    assert (
        services["observability"] == generator.EXPECTED_SECTIONS["observability_intent"]
    )
    assert (
        services["data_boundary"] == generator.EXPECTED_SECTIONS["data_boundary_intent"]
    )
    assert services["secrets"]["secret_values"] == "ABSENT"
    assert services["secrets"]["transport_encryption"] == ("REQUIRED_NOT_CONFIGURED")
    assert services["secrets"]["ambient_credential_resolution"] == "FORBIDDEN"
    assert services["key_management"]["key_deletion"] == "FORBIDDEN"
    assert services["key_management"]["transport_encryption"] == (
        "REQUIRED_NOT_CONFIGURED"
    )
    assert services["data_boundary"]["production_region"] is None
    assert services["data_boundary"]["backup_region"] is None


def test_activation_actions_gates_and_evidence_remain_fail_closed(
    data_services_model: generator.DataServicesModel,
) -> None:
    plan = generator.reference_plan_document(data_services_model)
    assert plan["planned_actions"] == {action: 0 for action in generator.ACTION_NAMES}
    assert plan["activation"] == {
        "enabled": False,
        "status": "DISABLED",
        "native_plan_status": "NOT_EXECUTED",
        "network_access": "FORBIDDEN",
        "credential_access": "FORBIDDEN",
        "live_provider_calls": "FORBIDDEN",
        "external_writes": "FORBIDDEN",
        "migration_action": "FORBIDDEN",
        "backup_action": "FORBIDDEN",
        "restore_action": "FORBIDDEN",
        "redrive_action": "FORBIDDEN",
        "destructive_action": "FORBIDDEN",
        "deploy_action": "FORBIDDEN",
        "release_action": "FORBIDDEN",
        "production_action": "FORBIDDEN",
        "native_commands": {
            command: "FORBIDDEN" for command in generator.NATIVE_COMMANDS
        },
    }
    assert plan["verification_boundary"] == {
        key: value
        for key, value in generator.EXPECTED_SECTIONS["evidence_boundary"].items()
        if key != "deliverable_classification"
    }
    assert all(
        value == "NOT_EXECUTED"
        for key, value in plan["verification_boundary"].items()
        if key.endswith("validation")
        or key.startswith("formal_")
        or key == "live_staging_release_production"
    )


def test_generated_document_is_non_executable_provider_neutral_reference(
    data_services_model: generator.DataServicesModel,
) -> None:
    document = generator.reference_plan_document(data_services_model)["document"]
    assert document == {
        "id": "RAOS-DATA-SERVICES-REFERENCE-PLAN-001",
        "version": "1.1.0",
        "story_id": "ST-1502",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "generation_command": generator.GENERATION_COMMAND,
        "artifact_kind": (
            "SOURCE_DERIVED_NON_EXECUTABLE_PROVIDER_NEUTRAL_DATA_SERVICES_REFERENCE_PLAN"
        ),
        "executable": False,
        "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
    }


def test_source_pins_match_regular_files() -> None:
    for relative, expected_digest in generator.PINNED_SOURCES.items():
        path = REPOSITORY_ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert generator.sha256_file(path) == expected_digest


def test_generated_json_matches_strict_renderer(
    data_services_model: generator.DataServicesModel,
) -> None:
    path = REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH
    assert path.is_file()
    assert not path.is_symlink()
    assert json.loads(path.read_bytes()) == generator.reference_plan_document(
        data_services_model
    )


def test_data_services_directory_contains_only_non_native_reference_plan() -> None:
    directory = REPOSITORY_ROOT / "infra/terraform/data-services"
    assert sorted(path.name for path in directory.iterdir()) == [
        generator.REFERENCE_PLAN_PATH.name
    ]
    forbidden_suffixes = {".tf", ".tfvars", ".hcl", ".lock"}
    assert not any(
        path.is_file() and path.suffix in forbidden_suffixes
        for path in directory.rglob("*")
    )


def test_contract_top_level_and_generated_inventory_are_closed(
    contract_document: dict[str, Any],
) -> None:
    assert set(contract_document) == generator.TOP_LEVEL_KEYS
    assert generator.GENERATED_PATHS == (
        Path("infra/terraform/data-services/data-services.reference-plan.v1.json"),
        Path("changes/st-1502/manifest.yaml"),
    )
