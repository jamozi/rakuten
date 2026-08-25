"""Positive provider-neutral contract semantics for ST-1503."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml

from scripts import build_st1503_compute_edge as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_contract_is_closed_provider_neutral_interface(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    contract = compute_edge_model.contract
    assert contract["document"] == generator.EXPECTED_SECTIONS["document"]
    assert set(contract) == generator.TOP_LEVEL_KEYS
    admission = _mapping(contract["provider_neutral_compute_edge_admission"])
    assert admission["classification"] == (
        "STRICT_PROVIDER_NEUTRAL_COMPUTE_EDGE_CAPABILITY_ADMISSION"
    )
    assert admission["admission_status"] == "NOT_EVALUATED"
    assert admission["eligible"] is False
    for key in (
        "selected_profile_id",
        "selected_profile_kind",
        "selected_provider_name",
        "default_profile_id",
        "fallback_profile_id",
    ):
        assert admission[key] is None
    assert admission["concrete_alternate_provider_selected"] is False


def test_direct_handoff_is_hash_and_semantic_bound() -> None:
    handoff_path = REPOSITORY_ROOT / generator.DESIGN_HANDOFF_PATH
    handoff = generator.load_yaml(handoff_path)
    assert (
        generator.sha256_file(handoff_path)
        == generator.AUTHORITY_SOURCES[generator.DESIGN_HANDOFF_PATH.as_posix()]
    )
    assert (
        generator.semantic_sha256(handoff) == generator.EXPECTED_HANDOFF_SEMANTIC_SHA256
    )
    assert handoff["approved_story"] == "ST-1503"
    assert handoff["decision"]["required_capability_ids"] == [
        capability_id
        for capability_id, _outcome in generator.COMPUTE_EDGE_CAPABILITY_OUTCOMES
    ]


def test_predecessor_is_fully_bound_and_fail_closed(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    binding = compute_edge_model.contract["predecessor_binding"]
    assert binding == generator.EXPECTED_SECTIONS["predecessor_binding"]
    assert binding["required_provider_policy"] == (
        "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION"
    )
    assert binding["required_admission_status"] == "NOT_EVALUATED"
    assert binding["required_eligible"] is False
    assert binding["required_activation_status"] == "DISABLED"
    assert binding["required_planned_actions"] == {
        "create": 0,
        "update": 0,
        "delete": 0,
    }


def test_aws_labels_are_current_canonical_reference_architecture_only(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    reference = _mapping(compute_edge_model.contract["reference_architecture"])
    assert reference["classification"] == (
        "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
    )
    assert reference["service_mappings"] == generator._aws_reference_service_mappings()
    for key in (
        "default",
        "implicit_fallback",
        "selected_binding",
        "eligibility_shortcut",
        "admission_requirement",
        "evidence_substitute",
    ):
        assert reference[key] is False
    admission = _mapping(
        compute_edge_model.contract["provider_neutral_compute_edge_admission"]
    )
    assert admission["aws_reference_boundary"]["role"] == (
        "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
    )
    assert admission["aws_reference_boundary"]["canonical_story_deliverables"] == (
        "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
    )
    assert (
        admission["aws_reference_boundary"]["non_aws_owner_managed_profiles"]
        == "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
    )
    assert admission["eligible_profile_kinds"] == list(generator.ELIGIBLE_PROFILE_KINDS)
    assert admission["mapping_policy"]["configured_mapping_count"] == 0
    assert admission["mapping_policy"]["complete_mapping"] is False
    assert all(
        value == "FORBIDDEN"
        for key, value in admission["evidence_equivalence_policy"].items()
        if key.endswith("_as_evidence")
    )


def test_capability_inventory_is_exact_complete_and_unconfigured(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    rows = compute_edge_model.contract["provider_neutral_compute_edge_admission"][
        "capability_mapping_requirements"
    ]
    assert rows == generator._capability_mapping_requirements()
    assert [row["capability_id"] for row in rows] == [
        capability_id
        for capability_id, _outcome in generator.COMPUTE_EDGE_CAPABILITY_OUTCOMES
    ]
    for row in rows:
        assert row["selected_mapping"] is None
        assert row["evidence_refs"] == []
        assert row["mapping_status"] == "REQUIRED_NOT_CONFIGURED"


def test_mapping_transport_and_equivalent_evidence_gates_are_exact(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    admission = compute_edge_model.contract["provider_neutral_compute_edge_admission"]
    assert admission["mapping_policy"] == {
        "required_mapping_mode": "EXACTLY_ONE_PER_REQUIRED_CAPABILITY",
        "required_capability_count": 8,
        "configured_mapping_count": 0,
        "complete_mapping": False,
        "missing_mapping": "REJECT",
        "unknown_mapping": "REJECT",
        "duplicate_mapping": "REJECT",
        "implicit_mapping": "REJECT",
        "partial_mapping": "REJECT",
        "provider_label_only_mapping": "REJECT",
        "service_label_only_mapping": "REJECT",
        "reference_only_mapping": "REJECT",
    }
    assert admission["binding_policy"]["implicit_binding"] == "FORBIDDEN"
    assert admission["binding_policy"]["name_or_reference_only_eligibility"] == (
        "FORBIDDEN"
    )
    assert admission["cross_capability_transport_security_policy"] == {
        "public_transport": "TLS_REQUIRED_NOT_CONFIGURED",
        "internal_transport": "TLS_REQUIRED_NOT_CONFIGURED",
        "provider_transport": "TLS_REQUIRED_NOT_CONFIGURED",
        "origin_transport": "TLS_REQUIRED_NOT_CONFIGURED",
        "selected_exceptions": [],
    }
    assert admission["evidence_equivalence_policy"] == {
        "identical_security_evidence": "REQUIRED",
        "identical_operations_evidence": "REQUIRED",
        "identical_release_evidence": "REQUIRED",
        "identical_performance_load_evidence": "REQUIRED",
        "identical_health_slo_alerting_evidence": "REQUIRED",
        "identical_canary_rollback_evidence": "REQUIRED",
        "identical_identity_secret_egress_evidence": "REQUIRED",
        "identical_isolation_evidence": "REQUIRED",
        "identical_region_residency_evidence": "REQUIRED",
        "identical_transport_security_evidence": "REQUIRED",
        "provider_label_as_evidence": "FORBIDDEN",
        "service_label_as_evidence": "FORBIDDEN",
        "reference_metadata_as_evidence": "FORBIDDEN",
        "local_test_as_live_evidence": "FORBIDDEN",
    }


def test_all_bindings_and_logical_intents_remain_unset(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    contract = compute_edge_model.contract
    assert all(
        value is None or value == []
        for value in contract["selected_configuration"].values()
    )
    workloads = contract["workload_intent"]
    assert [row["role"] for row in workloads["roles"]] == list(generator.WORKLOAD_ROLES)
    for row in workloads["roles"]:
        assert "component_family" not in row
        assert row["direct_public_access"] == "FORBIDDEN"
        assert all(value is None or value == [] for value in row["selected"].values())
    surfaces = contract["surface_boundary_intent"]
    assert [row["surface"] for row in surfaces["surfaces"]] == list(
        generator.SURFACE_ROLES
    )
    assert surfaces["public_data_plane_access"] == "FORBIDDEN"
    assert all(
        value is None or value == []
        for value in contract["edge_routing_intent"]["selected"].values()
    )


def test_health_gates_and_open_decisions_remain_unresolved(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    health = compute_edge_model.contract["health_intent"]
    assert health["telemetry"] == "REQUIRED_NOT_CONFIGURED"
    assert health["slo_capacity"] == "REQUIRED_NOT_CONFIGURED"
    assert health["human_release_approval"] == "REQUIRED"
    assert health["kill_switch_change"] == "HUMAN_APPROVAL_REQUIRED"
    assert health["liveness"]["purpose"] == "PROCESS_ONLY"
    assert health["readiness"]["infer_from_http_200_body"] == "FORBIDDEN"
    decisions = compute_edge_model.contract["open_decision_boundary"]
    assert tuple(decisions) == (
        "OD-002",
        "OD-009",
        "OD-010",
        "OD-011",
        "OD-013",
        "OD-015",
    )
    assert all(
        row["resolved"] is False and row["blocking"] is True
        for row in decisions.values()
    )


def test_execution_and_evidence_are_inert_not_executed(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    plan = generator.reference_plan_document(compute_edge_model)
    assert plan["planned_actions"] == {action: 0 for action in generator.ACTION_NAMES}
    activation = plan["activation"]
    assert activation["enabled"] is False
    assert activation["status"] == "DISABLED"
    for key in (
        "network_access",
        "credential_access",
        "live_provider_calls",
        "external_writes",
        "deploy_action",
        "release_action",
        "production_action",
    ):
        assert activation[key] == "FORBIDDEN"
    assert set(activation["native_commands"].values()) == {"FORBIDDEN"}
    evidence = plan["verification_boundary"]
    assert evidence["credentials"] == "ABSENT"
    assert evidence["native_iac_validation"] == "EXECUTED_LOCAL_NOT_FORMAL"
    assert all(
        value == "NOT_EXECUTED"
        for key, value in evidence.items()
        if key.startswith("formal_")
        or (key.endswith("_validation") and key != "native_iac_validation")
    )


def test_source_pins_and_generated_json_match() -> None:
    for relative, expected_digest in generator.PINNED_SOURCES.items():
        path = REPOSITORY_ROOT / relative
        assert path.is_file() and not path.is_symlink()
        assert generator.sha256_file(path) == expected_digest
    model = generator.load_and_validate_contract(REPOSITORY_ROOT)
    path = REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH
    assert json.loads(path.read_bytes()) == generator.reference_plan_document(model)


def test_manifest_contains_handoff_and_provider_neutral_boundary() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert f"repo://{generator.DESIGN_HANDOFF_PATH.as_posix()}" in {
        row["uri"] for row in manifest["source_artifacts"]
    }
    boundary = manifest["boundary"]
    assert boundary["admission_status"] == "NOT_EVALUATED"
    assert boundary["eligible"] is False
    assert boundary["required_capability_count"] == 8
    assert boundary["configured_mapping_count"] == 0
    assert boundary["selected_provider_name"] is None
    assert boundary["default_profile_id"] is None
    assert boundary["fallback_profile_id"] is None
    assert boundary["aws_reference_role"] == (
        "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
    )
    assert boundary["canonical_story_deliverables"] == (
        "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
    )
    assert boundary["portable_implementation_paths"] == (
        "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
    )
    assert all(
        boundary[key] is False
        for key in (
            "aws_reference_default",
            "aws_reference_implicit_fallback",
            "aws_reference_selected_binding",
            "aws_reference_eligibility_shortcut",
            "aws_reference_admission_requirement",
            "aws_reference_evidence_substitute",
        )
    )


def test_compute_edge_directory_contains_only_owned_provider_free_outputs() -> None:
    directory = REPOSITORY_ROOT / "infra/terraform/compute-edge"
    assert sorted(path.name for path in directory.iterdir()) == sorted(
        path.name for path in generator.GENERATED_ARTIFACT_PATHS
    )
    hcl = "\n".join((directory / path.name).read_text() for path in generator.HCL_PATHS)
    assert 'provider "' not in hcl
    assert 'resource "' not in hcl
    assert "backend {" not in hcl
