"""Positive contract and reference-plan semantics for ST-1505."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from scripts import build_st1505_staging_deployment as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_contract_loads_as_closed_interface_only_model(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    assert staging_model.contract["document"] == {
        "id": "RAOS-STAGING-DEPLOYMENT-001",
        "version": "1.0.0",
        "story_id": "ST-1505",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "formal_verification": "NOT_EXECUTED",
    }
    assert set(staging_model.contract) == generator.TOP_LEVEL_KEYS


def test_all_three_predecessors_are_exactly_bound_and_fail_closed(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    bindings = _mapping(staging_model.contract["predecessor_bindings"])
    assert bindings == generator.EXPECTED_SECTIONS["predecessor_bindings"]
    assert list(bindings) == ["data_services", "compute_edge", "deployment_identity"]
    for binding in bindings.values():
        row = _mapping(binding)
        assert row["required_contract_non_executable"] is True
        assert row["required_reference_plan_executable"] is False
        assert row["required_activation_status"] == "DISABLED"
        assert row["required_live_provider_calls"] == "FORBIDDEN"
        assert row["required_external_writes"] == "FORBIDDEN"
        assert row["required_selected_values"] == "UNSET"
        assert row["required_planned_actions"] == {
            "create": 0,
            "update": 0,
            "delete": 0,
        }
    assert bindings["deployment_identity"]["required_credential_issuance"] == (
        "FORBIDDEN"
    )


def test_staging_is_an_inert_unconfigured_nonproduction_label(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    environment = _mapping(
        generator.reference_plan_document(staging_model)["environment"]
    )
    assert environment == {
        "label": "STAGING",
        "classification": "INERT_CANONICAL_LABEL_ONLY",
        "configuration_status": "NOT_CONFIGURED",
        "runtime_status": "NOT_EXECUTED",
        "formal_verification_status": "NOT_EXECUTED",
        "allowed_data_classes": ["SYNTHETIC", "APPROVED_ANONYMIZED"],
        "production_data": "FORBIDDEN",
        "dedicated_credentials": "REQUIRED_NOT_CONFIGURED",
        "credential_material": "ABSENT",
        "external_access": "FORBIDDEN",
        "production_action": "FORBIDDEN",
    }


def test_every_physical_runtime_and_release_binding_is_unset(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    selected = _mapping(
        generator.reference_plan_document(staging_model)["selected_bindings"]
    )
    assert set(selected) == set(generator._selected_bindings())
    assert all(value is None or value == [] for value in selected.values())


def test_artifact_admission_requires_immutable_scanned_signed_promotion(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    artifact = _mapping(
        generator.reference_plan_document(staging_model)["artifact_admission"]
    )
    for field in (
        "immutable_digest",
        "sbom",
        "vulnerability_scan",
        "signed_provenance",
        "promote_without_rebuild",
    ):
        assert artifact[field] == "REQUIRED_NOT_CONFIGURED"
    for field in (
        "mutable_artifact",
        "rebuild_between_environments",
        "unsigned_artifact",
        "unscanned_artifact",
    ):
        assert artifact[field] == "FORBIDDEN"


def test_migration_is_expand_migrate_contract_with_contract_deferred(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    migration = _mapping(generator.reference_plan_document(staging_model)["migration"])
    assert migration["strategy"] == "EXPAND_MIGRATE_CONTRACT"
    assert migration["expand"] == "REQUIRED_NOT_CONFIGURED"
    assert migration["migrate"] == "REQUIRED_NOT_CONFIGURED"
    assert migration["contract"] == "DEFERRED_TO_LATER_RELEASE"
    for field in (
        "destructive_contract_current_release",
        "contract_before_expand",
        "direct_ddl",
        "down_migration_primary_recovery",
        "external_api_during_migration",
    ):
        assert migration[field] == "FORBIDDEN"


def test_health_smoke_and_isolation_are_required_without_http_200_inference(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    health = _mapping(
        generator.reference_plan_document(staging_model)["health_and_smoke"]
    )
    for field in (
        "liveness_check",
        "readiness_check",
        "dependency_check",
        "migration_compatibility_check",
        "public_admin_internal_isolation_check",
        "smoke_check",
        "browser_e2e",
    ):
        assert health[field] == "REQUIRED_NOT_CONFIGURED"
    assert health["infer_readiness_from_generic_http_200"] == "FORBIDDEN"
    assert health["external_provider_probe"] == "FORBIDDEN"


def test_rollback_is_declarative_and_never_uses_pitr_for_app_errors(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    rollback = _mapping(generator.reference_plan_document(staging_model)["rollback"])
    assert rollback["execution"] == "FORBIDDEN"
    for field in (
        "prior_immutable_artifact",
        "prior_configuration",
        "known_safe_snapshot",
        "migration_compatibility",
    ):
        assert rollback[field] == "REQUIRED_NOT_CONFIGURED"
    assert rollback["pitr_for_ordinary_application_error"] == "FORBIDDEN"
    assert rollback["destructive_reversal"] == "FORBIDDEN"


def test_logical_phases_are_exactly_ordered_disabled_and_zero_action(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    raw_phases = generator.reference_plan_document(staging_model)["logical_phases"]
    assert isinstance(raw_phases, list)
    phases = cast(list[dict[str, Any]], raw_phases)
    assert [phase["name"] for phase in phases] == list(generator.PHASE_NAMES)
    assert all(
        phase
        == {
            "name": phase["name"],
            "status": "DISABLED",
            "execution_status": "NOT_EXECUTED",
            "external_action": "FORBIDDEN",
            "action_count": 0,
        }
        for phase in phases
    )


def test_activation_operations_and_all_action_counts_fail_closed(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    plan = generator.reference_plan_document(staging_model)
    assert plan["action_counts"] == {name: 0 for name in generator.ACTION_COUNT_NAMES}
    assert plan["activation"] == {
        "enabled": False,
        "status": "DISABLED",
        "runtime_status": "NOT_EXECUTED",
        "network_access": "FORBIDDEN",
        "credential_access": "FORBIDDEN",
        "live_provider_calls": "FORBIDDEN",
        "external_writes": "FORBIDDEN",
        "staging_action": "FORBIDDEN",
        "release_action": "FORBIDDEN",
        "production_action": "FORBIDDEN",
        "operations": {
            operation: "FORBIDDEN" for operation in generator.OPERATION_NAMES
        },
    }


def test_generated_document_and_verification_boundary_are_non_executable(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    plan = generator.reference_plan_document(staging_model)
    assert plan["document"] == {
        "id": "RAOS-STAGING-DEPLOYMENT-REFERENCE-PLAN-001",
        "version": "1.0.0",
        "story_id": "ST-1505",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "generation_command": generator.GENERATION_COMMAND,
        "artifact_kind": (
            "SOURCE_DERIVED_NON_EXECUTABLE_STAGING_DEPLOYMENT_REFERENCE_PLAN"
        ),
        "executable": False,
        "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
    }
    boundary = _mapping(plan["verification_boundary"])
    assert boundary["formal_tst_009"] == "NOT_EXECUTED"
    assert boundary["formal_tst_022"] == "NOT_EXECUTED"
    for field in (
        "migration_database",
        "http_smoke",
        "playwright",
        "staging",
        "rollback",
        "release",
        "production",
    ):
        assert boundary[field] == "NOT_EXECUTED"
    for field in (
        "executable_pipeline",
        "workflow",
        "terraform_or_cloud_runtime",
        "migration_runtime",
        "browser_runtime",
        "credentials",
    ):
        assert boundary[field] == "ABSENT"


def test_source_pins_match_regular_files() -> None:
    for relative, expected_digest in generator.PINNED_SOURCES.items():
        path = REPOSITORY_ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()
        current_override = generator.CURRENT_DEVELOPMENT_SOURCE_OVERRIDES.get(relative)
        live_digest = (
            current_override[1] if current_override is not None else expected_digest
        )
        assert generator.sha256_file(path) == live_digest


def test_generated_json_matches_strict_renderer(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    path = REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH
    assert path.is_file()
    assert not path.is_symlink()
    assert json.loads(path.read_bytes()) == generator.reference_plan_document(
        staging_model
    )


def test_owned_directories_contain_no_executable_deployment_artifact() -> None:
    staging = REPOSITORY_ROOT / "infra/terraform/staging"
    assert sorted(path.name for path in staging.iterdir()) == [
        generator.REFERENCE_PLAN_PATH.name
    ]
    assert sorted(
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in (REPOSITORY_ROOT / "changes/st-1505").rglob("*")
        if path.is_file()
    ) == [
        "changes/st-1505/README.md",
        "changes/st-1505/contracts/staging-deployment.v1.yaml",
        "changes/st-1505/manifest.yaml",
    ]
    forbidden_suffixes = {
        ".tf",
        ".tfvars",
        ".hcl",
        ".lock",
        ".sh",
        ".bash",
        ".yml",
        ".workflow",
    }
    assert not any(
        path.is_file() and path.suffix in forbidden_suffixes
        for directory in (staging, REPOSITORY_ROOT / "changes/st-1505")
        for path in directory.rglob("*")
    )
    assert not any(
        path.is_file() and (path.stat().st_mode & 0o111) for path in staging.rglob("*")
    )


def test_contract_and_generated_inventory_are_closed(
    contract_document: dict[str, Any],
) -> None:
    assert set(contract_document) == generator.TOP_LEVEL_KEYS
    assert generator.GENERATED_PATHS == (
        Path("infra/terraform/staging/staging-deployment.reference-plan.v1.json"),
        Path("changes/st-1505/manifest.yaml"),
    )
