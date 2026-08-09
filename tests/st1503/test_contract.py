"""Positive contract and reference-plan semantics for ST-1503."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from scripts import build_st1503_compute_edge as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_contract_loads_as_closed_interface_only_model(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    assert compute_edge_model.contract["document"] == {
        "id": "RAOS-COMPUTE-EDGE-FOUNDATION-001",
        "version": "1.0.0",
        "story_id": "ST-1503",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "formal_verification": "NOT_EXECUTED",
    }
    assert set(compute_edge_model.contract) == generator.TOP_LEVEL_KEYS


def test_predecessor_is_hash_bound_and_fail_closed(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    binding = compute_edge_model.contract["predecessor_binding"]
    assert binding == generator.EXPECTED_SECTIONS["predecessor_binding"]
    assert binding["extension_kind"] == "COMPUTE_CDN_WAF"
    assert binding["required_activation_status"] == "DISABLED"
    assert binding["required_resource_payloads"] == "FORBIDDEN"
    assert binding["required_planned_actions"] == {
        "create": 0,
        "update": 0,
        "delete": 0,
    }


def test_reference_component_families_are_labels_not_selections(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    plan = generator.reference_plan_document(compute_edge_model)
    reference = _mapping(plan["reference_architecture"])
    assert reference["component_families"] == generator.COMPONENT_FAMILIES
    assert reference["classification"] == "INHERITED_REFERENCE_METADATA_ONLY"
    selection = _mapping(plan["selected_configuration"])
    assert all(value is None or value == [] for value in selection.values())


def test_logical_workload_roles_and_supply_chain_requirements_are_exact(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    logical = _mapping(
        generator.reference_plan_document(compute_edge_model)["logical_compute_edge"]
    )
    workloads = _mapping(logical["workloads"])
    roles = cast(list[dict[str, Any]], workloads["roles"])
    assert [row["role"] for row in roles] == list(generator.WORKLOAD_ROLES)
    for requirement in (
        "immutable_digest_selected_images",
        "signed_provenance",
        "sbom",
        "image_scanning",
        "least_privilege_workload_identities",
        "encrypted_logs",
        "graceful_shutdown",
    ):
        assert workloads[requirement] == "REQUIRED_NOT_CONFIGURED"
    assert workloads["secret_material"] == "ABSENT"
    for row in roles:
        assert row["component_family"] == "ECS_Fargate"
        assert row["direct_public_access"] == "FORBIDDEN"
        assert all(value is None or value == [] for value in row["selected"].values())


def test_public_admin_internal_boundaries_are_distinct_and_unconfigured(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    logical = _mapping(
        generator.reference_plan_document(compute_edge_model)["logical_compute_edge"]
    )
    boundaries = _mapping(logical["surfaces"])
    for field in (
        "trust_boundary_separation",
        "cache_separation",
        "cookie_separation",
        "host_separation",
        "csp_separation",
        "authentication_separation",
    ):
        assert boundaries[field] == "REQUIRED_NOT_CONFIGURED"
    surfaces = cast(list[dict[str, Any]], boundaries["surfaces"])
    assert [row["surface"] for row in surfaces] == list(generator.SURFACE_ROLES)
    assert [row["trust_boundary"] for row in surfaces] == [
        "PUBLIC",
        "ADMIN",
        "INTERNAL",
    ]
    public, admin, internal = surfaces
    assert public["public_projection_only"] == "REQUIRED"
    assert public["direct_internal_data_plane_access"] == "FORBIDDEN"
    assert admin["approved_identity_authorization"] == "REQUIRED_NOT_CONFIGURED"
    assert admin["selected"]["authentication_policy_reference"] is None
    assert internal["approved_identity_authorization"] == (
        "SERVICE_IDENTITY_REQUIRED_NOT_CONFIGURED"
    )
    for row in surfaces:
        assert all(value is None or value == [] for value in row["selected"].values())


def test_api_worker_and_edge_origins_are_private_or_edge_mediated(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    logical = _mapping(
        generator.reference_plan_document(compute_edge_model)["logical_compute_edge"]
    )
    roles = cast(list[dict[str, Any]], _mapping(logical["workloads"])["roles"])
    assert roles[0]["origin_exposure"] == "EDGE_MEDIATED_REQUIRED_NOT_CONFIGURED"
    assert roles[1]["origin_exposure"] == "EDGE_MEDIATED_REQUIRED_NOT_CONFIGURED"
    assert roles[2]["origin_exposure"] == "PRIVATE_ONLY_REQUIRED"
    assert roles[3]["origin_exposure"] == "PRIVATE_ONLY_REQUIRED"
    edge = _mapping(logical["edge_routing"])
    assert edge["edge_only_public_entry"] == "REQUIRED_NOT_CONFIGURED"
    assert edge["origin_private_only"] == "REQUIRED"
    assert edge["api_worker_data_origins_private_only"] == "REQUIRED"
    assert edge["direct_origin_public_access"] == "FORBIDDEN"
    assert all(value is None or value == [] for value in edge["selected"].values())


def test_liveness_and_readiness_are_distinct_without_inferred_matchers(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    logical = _mapping(
        generator.reference_plan_document(compute_edge_model)["logical_compute_edge"]
    )
    health = _mapping(logical["health"])
    assert health["roles"] == list(generator.WORKLOAD_ROLES)
    liveness = _mapping(health["liveness"])
    readiness = _mapping(health["readiness"])
    assert liveness["purpose"] == "PROCESS_ONLY"
    assert liveness["external_dependency_coupling"] == "FORBIDDEN"
    assert readiness["purpose"] == "DEPENDENCY_AND_MIGRATION_READINESS"
    assert readiness["dependency_check"] == "REQUIRED_NOT_CONFIGURED"
    assert readiness["migration_compatibility_check"] == "REQUIRED_NOT_CONFIGURED"
    assert readiness["infer_from_http_200_body"] == "FORBIDDEN"
    for probe in (liveness, readiness):
        assert probe["bounded_failure_behavior"] == "REQUIRED_NOT_CONFIGURED"
        assert all(value is None or value == [] for value in probe["selected"].values())


def test_activation_native_operations_and_action_counts_fail_closed(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    plan = generator.reference_plan_document(compute_edge_model)
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
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    plan = generator.reference_plan_document(compute_edge_model)
    assert plan["document"] == {
        "id": "RAOS-COMPUTE-EDGE-REFERENCE-PLAN-001",
        "version": "1.0.0",
        "story_id": "ST-1503",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "generation_command": generator.GENERATION_COMMAND,
        "artifact_kind": "SOURCE_DERIVED_NON_EXECUTABLE_COMPUTE_EDGE_REFERENCE_PLAN",
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
        "formal_tst_027": "NOT_EXECUTED",
        "performance_validation": "NOT_EXECUTED",
        "health_runtime_validation": "NOT_EXECUTED",
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
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    path = REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH
    assert path.is_file()
    assert not path.is_symlink()
    assert json.loads(path.read_bytes()) == generator.reference_plan_document(
        compute_edge_model
    )


def test_compute_edge_directory_contains_only_non_native_reference_plan() -> None:
    directory = REPOSITORY_ROOT / "infra/terraform/compute-edge"
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
        Path("infra/terraform/compute-edge/compute-edge.reference-plan.v1.json"),
        Path("changes/st-1503/manifest.yaml"),
    )
