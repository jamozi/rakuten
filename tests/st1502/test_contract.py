"""Positive contract and reference-plan semantics for ST-1502."""

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
        "version": "1.0.0",
        "story_id": "ST-1502",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "formal_verification": "NOT_EXECUTED",
    }
    assert set(data_services_model.contract) == generator.TOP_LEVEL_KEYS


def test_predecessor_is_hash_bound_and_fail_closed(
    data_services_model: generator.DataServicesModel,
) -> None:
    binding = data_services_model.contract["predecessor_binding"]
    assert binding == generator.EXPECTED_SECTIONS["predecessor_binding"]
    assert binding["required_activation_status"] == "DISABLED"
    assert binding["required_resource_payloads"] == "FORBIDDEN"
    assert binding["required_planned_actions"] == {
        "create": 0,
        "update": 0,
        "delete": 0,
    }


def test_reference_metadata_does_not_select_a_real_configuration(
    data_services_model: generator.DataServicesModel,
) -> None:
    plan = generator.reference_plan_document(data_services_model)
    assert plan["reference_architecture"] == {
        "cloud": "AWS",
        "region": "ap-northeast-1",
        "classification": "INHERITED_REFERENCE_METADATA_ONLY",
        "portable_core_required": True,
    }
    selection = plan["selected_configuration"]
    assert isinstance(selection, dict)
    for value in selection.values():
        assert value is None or value == []


def test_rds_is_private_logical_postgresql_with_every_real_value_unset(
    data_services_model: generator.DataServicesModel,
) -> None:
    services = _mapping(
        generator.reference_plan_document(data_services_model)["logical_data_services"]
    )
    rds = _mapping(services["rds"])
    assert rds["service"] == "PostgreSQL"
    assert rds["classification"] == "LOGICAL_SERVICE_INTENT_ONLY"
    assert rds["private_only"] == "REQUIRED"
    assert rds["publicly_accessible"] is False
    assert {
        rds["encryption_at_rest"],
        rds["backup"],
        rds["point_in_time_recovery"],
        rds["deletion_protection"],
        rds["final_snapshot"],
    } == {"REQUIRED_NOT_CONFIGURED"}
    assert rds["restore_test"] == "REQUIRED_NOT_EXECUTED"
    assert all(value is None or value == [] for value in rds["selected"].values())


def test_s3_roles_and_non_destructive_requirements_are_exact(
    data_services_model: generator.DataServicesModel,
) -> None:
    services = _mapping(
        generator.reference_plan_document(data_services_model)["logical_data_services"]
    )
    s3 = _mapping(services["s3"])
    assert [row["role"] for row in s3["roles"]] == list(generator.BUCKET_ROLES)
    assert all(row["physical_name"] is None for row in s3["roles"])
    assert all(row["arn"] is None for row in s3["roles"])
    assert s3["public_access_block"] == "REQUIRED"
    assert s3["encryption_at_rest"] == "REQUIRED_NOT_CONFIGURED"
    assert s3["versioning"] == "REQUIRED_NOT_CONFIGURED"
    assert s3["force_destroy"] == "FORBIDDEN"
    assert s3["lifecycle_deletion"] == "FORBIDDEN"
    assert s3["automatic_deletion"] == "FORBIDDEN"
    assert s3["retention_days"] is None
    assert s3["lifecycle_rules"] == []
    raw = s3["roles"][0]
    assert raw["immutability"] == "REQUIRED_NOT_CONFIGURED"
    assert raw["integrity_metadata"] == "REQUIRED_NOT_CONFIGURED"
    assert raw["deletion_role_separation"] == "REQUIRED_NOT_CONFIGURED"


def test_every_canonical_queue_class_requires_dlq_and_separated_roles(
    data_services_model: generator.DataServicesModel,
) -> None:
    services = _mapping(
        generator.reference_plan_document(data_services_model)["logical_data_services"]
    )
    queues_value = _mapping(services["sqs"])["classes"]
    assert isinstance(queues_value, list)
    queues = cast(list[dict[str, Any]], queues_value)
    assert [row["class"] for row in queues] == list(generator.QUEUE_CLASSES)
    for row in queues:
        assert row["dlq"] == "REQUIRED_NOT_CONFIGURED"
        assert row["producer_consumer_separation"] == "REQUIRED_NOT_CONFIGURED"
        assert row["redrive_role_separation"] == "REQUIRED_NOT_CONFIGURED"
        assert all(value is None for value in row["selected"].values())


def test_secrets_and_kms_are_metadata_only_without_identifiers_or_policies(
    data_services_model: generator.DataServicesModel,
) -> None:
    services = _mapping(
        generator.reference_plan_document(data_services_model)["logical_data_services"]
    )
    secrets = _mapping(services["secrets_manager"])
    assert secrets == generator.EXPECTED_SECTIONS["secrets_manager_intent"]
    kms = _mapping(services["kms"])
    assert kms == generator.EXPECTED_SECTIONS["kms_intent"]
    assert secrets["secret_values"] == "ABSENT"
    assert secrets["secret_names"] == []
    assert secrets["secret_arns"] == []
    assert kms["key_ids"] == []
    assert kms["key_arns"] == []
    assert kms["aliases"] == []
    assert kms["policy_document"] is None
    assert kms["deletion_window_days"] is None
    assert kms["key_deletion"] == "FORBIDDEN"


def test_activation_native_operations_and_action_counts_fail_closed(
    data_services_model: generator.DataServicesModel,
) -> None:
    plan = generator.reference_plan_document(data_services_model)
    assert plan["planned_actions"] == {"create": 0, "update": 0, "delete": 0}
    assert plan["activation"] == {
        "enabled": False,
        "status": "DISABLED",
        "native_plan_status": "NOT_EXECUTED",
        "live_provider_calls": "FORBIDDEN",
        "external_writes": "FORBIDDEN",
        "native_commands": {
            "init": "FORBIDDEN",
            "plan": "FORBIDDEN",
            "apply": "FORBIDDEN",
            "destroy": "FORBIDDEN",
            "import": "FORBIDDEN",
            "refresh": "FORBIDDEN",
        },
    }


def test_generated_document_and_verification_boundary_are_non_executable(
    data_services_model: generator.DataServicesModel,
) -> None:
    plan = generator.reference_plan_document(data_services_model)
    assert plan["document"] == {
        "id": "RAOS-DATA-SERVICES-REFERENCE-PLAN-001",
        "version": "1.0.0",
        "story_id": "ST-1502",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "generation_command": generator.GENERATION_COMMAND,
        "artifact_kind": ("SOURCE_DERIVED_NON_EXECUTABLE_DATA_SERVICES_REFERENCE_PLAN"),
        "executable": False,
        "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
    }
    assert plan["verification_boundary"] == {
        "executable_terraform": "ABSENT",
        "terraform_cli": "UNPINNED_NOT_INVOKED",
        "provider_plugins": "UNPINNED_NOT_INVOKED",
        "aws_account": "UNSET",
        "credentials": "ABSENT",
        "native_iac_validation": "NOT_EXECUTED",
        "formal_tst_026": "NOT_EXECUTED",
        "formal_tst_029": "NOT_EXECUTED",
        "restore_validation": "NOT_EXECUTED",
        "live_staging_release_production": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
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
