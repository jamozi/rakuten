"""Hostile and exact-type validation cases for ST-1503."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import build_st1503_compute_edge as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _validate(document: dict[str, Any]) -> generator.ComputeEdgeModel:
    return generator.validate_contract(document, REPOSITORY_ROOT)


@pytest.mark.parametrize("field", generator.EXPECTED_SECTIONS["selected_configuration"])
def test_every_real_global_selection_must_remain_unset(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["selected_configuration"][field]
    document["selected_configuration"][field] = (
        ["REJECTED_INPUT_MARKER_1503"]
        if isinstance(current, list)
        else "REJECTED_INPUT_MARKER_1503"
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert "REJECTED_INPUT_MARKER_1503" not in str(captured.value)


@pytest.mark.parametrize("role_index", range(len(generator.WORKLOAD_ROLES)))
@pytest.mark.parametrize("field", generator._workload_selection())
def test_every_workload_physical_sizing_image_identity_and_network_value_is_rejected(
    contract_document: dict[str, Any], role_index: int, field: str
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["workload_intent"]["roles"][role_index]["selected"][field]
    document["workload_intent"]["roles"][role_index]["selected"][field] = (
        ["REJECTED_INPUT_MARKER_1503"]
        if isinstance(current, list)
        else "REJECTED_INPUT_MARKER_1503"
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert "REJECTED_INPUT_MARKER_1503" not in str(captured.value)


@pytest.mark.parametrize("role_index", range(len(generator.WORKLOAD_ROLES)))
@pytest.mark.parametrize(
    "field",
    [
        "container_port",
        "cpu_units",
        "memory_mib",
        "desired_count",
        "autoscaling_min",
        "autoscaling_max",
        "public_ip",
    ],
)
@pytest.mark.parametrize("value", [True, False, 0, 1, "selected"])
def test_workload_null_numeric_and_boolean_fields_reject_bool_as_int_bypasses(
    contract_document: dict[str, Any], role_index: int, field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["workload_intent"]["roles"][role_index]["selected"][field] = value
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize("surface_index", range(len(generator.SURFACE_ROLES)))
@pytest.mark.parametrize("field", generator._surface_selection())
def test_every_surface_domain_host_route_cache_cookie_csp_and_auth_value_is_rejected(
    contract_document: dict[str, Any], surface_index: int, field: str
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["surface_boundary_intent"]["surfaces"][surface_index][
        "selected"
    ][field]
    document["surface_boundary_intent"]["surfaces"][surface_index]["selected"][
        field
    ] = (
        ["REJECTED_INPUT_MARKER_1503"]
        if isinstance(current, list)
        else "REJECTED_INPUT_MARKER_1503"
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert "REJECTED_INPUT_MARKER_1503" not in str(captured.value)


@pytest.mark.parametrize(
    "field", generator.EXPECTED_SECTIONS["edge_routing_intent"]["selected"]
)
def test_every_edge_dns_tls_waf_origin_route_and_cache_value_is_rejected(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["edge_routing_intent"]["selected"][field]
    document["edge_routing_intent"]["selected"][field] = (
        ["REJECTED_INPUT_MARKER_1503"]
        if isinstance(current, list)
        else "REJECTED_INPUT_MARKER_1503"
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert "REJECTED_INPUT_MARKER_1503" not in str(captured.value)


@pytest.mark.parametrize("probe", ["liveness", "readiness"])
def test_every_health_endpoint_port_matcher_schema_and_timing_value_is_rejected(
    contract_document: dict[str, Any], probe: str
) -> None:
    fields = generator.EXPECTED_SECTIONS["health_intent"][probe]["selected"]
    for field in fields:
        document = copy.deepcopy(contract_document)
        current = document["health_intent"][probe]["selected"][field]
        document["health_intent"][probe]["selected"][field] = (
            ["REJECTED_INPUT_MARKER_1503"]
            if isinstance(current, list)
            else "REJECTED_INPUT_MARKER_1503"
        )
        with pytest.raises(generator.ComputeEdgeContractError) as captured:
            _validate(document)
        assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
        assert "REJECTED_INPUT_MARKER_1503" not in str(captured.value)


@pytest.mark.parametrize("probe", ["liveness", "readiness"])
@pytest.mark.parametrize(
    "field",
    [
        "port",
        "interval_seconds",
        "timeout_seconds",
        "healthy_threshold",
        "unhealthy_threshold",
    ],
)
@pytest.mark.parametrize("value", [True, False, 0, 1, "200"])
def test_health_null_numeric_fields_reject_bool_int_and_string_bypasses(
    contract_document: dict[str, Any], probe: str, field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["health_intent"][probe]["selected"][field] = value
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize(
    ("section", "collection"),
    [
        ("workload_intent", "roles"),
        ("surface_boundary_intent", "surfaces"),
        ("health_intent", "roles"),
    ],
)
@pytest.mark.parametrize("mutation", ["duplicate", "reorder"])
def test_fixed_role_and_surface_inventories_reject_duplicates_and_reordering(
    contract_document: dict[str, Any],
    section: str,
    collection: str,
    mutation: str,
) -> None:
    document = copy.deepcopy(contract_document)
    rows = document[section][collection]
    if mutation == "duplicate":
        rows[1] = copy.deepcopy(rows[0])
    else:
        rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code in {
        "CLOSED_SCHEMA_VIOLATION",
        "FIXED_VALUE_VIOLATION",
    }


@pytest.mark.parametrize(
    ("path", "value", "expected_code"),
    [
        (("execution_boundary", "activation_enabled"), True, "SAFE_BOUNDARY_VIOLATION"),
        (("execution_boundary", "activation_enabled"), 0, "TYPE_MISMATCH"),
        (("reference_architecture", "portable_core_required"), 1, "TYPE_MISMATCH"),
        (
            ("execution_boundary", "live_provider_calls"),
            "ALLOWED",
            "FIXED_VALUE_VIOLATION",
        ),
        (("execution_boundary", "external_writes"), "ALLOWED", "FIXED_VALUE_VIOLATION"),
    ],
)
def test_activation_bool_as_int_and_external_actions_are_rejected(
    contract_document: dict[str, Any],
    path: tuple[str, str],
    value: object,
    expected_code: str,
) -> None:
    document = copy.deepcopy(contract_document)
    document[path[0]][path[1]] = value
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == expected_code


@pytest.mark.parametrize("command", generator.NATIVE_COMMANDS)
def test_every_native_operation_must_remain_forbidden(
    contract_document: dict[str, Any], command: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"]["commands"][command] = "ALLOWED"
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize("action", generator.ACTION_NAMES)
@pytest.mark.parametrize("value", [1, -1, True, "0"])
def test_planned_actions_require_exact_integer_zero(
    contract_document: dict[str, Any], action: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"]["planned_actions"][action] = value
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == (
        "SAFE_BOUNDARY_VIOLATION" if type(value) is int else "TYPE_MISMATCH"
    )


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("workload_intent", "secret_material", "PRESENT"),
        ("workload_intent", "immutable_digest_selected_images", "CONFIGURED"),
        ("workload_intent", "signed_provenance", "CONFIGURED"),
        ("workload_intent", "sbom", "CONFIGURED"),
        ("workload_intent", "image_scanning", "CONFIGURED"),
        ("workload_intent", "least_privilege_workload_identities", "CONFIGURED"),
        ("workload_intent", "encrypted_logs", "CONFIGURED"),
        ("workload_intent", "graceful_shutdown", "CONFIGURED"),
        ("edge_routing_intent", "direct_origin_public_access", "ALLOWED"),
        ("health_intent", "classification", "RUNTIME_VALIDATED"),
    ],
)
def test_future_requirements_cannot_be_promoted_to_configured_claims(
    contract_document: dict[str, Any], section: str, field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document[section][field] = value
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


def test_public_surface_cannot_gain_direct_internal_data_plane_access(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["surface_boundary_intent"]["surfaces"][0][
        "direct_internal_data_plane_access"
    ] = "ALLOWED"
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    ("section", "index", "field", "value"),
    [
        ("workload_intent", 0, "trust_boundary", "INTERNAL"),
        ("workload_intent", 2, "trust_boundary", "PUBLIC"),
        ("surface_boundary_intent", 0, "trust_boundary", "INTERNAL"),
        ("surface_boundary_intent", 2, "trust_boundary", "PUBLIC"),
    ],
)
def test_role_and_surface_cross_binding_cannot_swap_public_and_internal_boundaries(
    contract_document: dict[str, Any],
    section: str,
    index: int,
    field: str,
    value: str,
) -> None:
    document = copy.deepcopy(contract_document)
    collection = "roles" if section == "workload_intent" else "surfaces"
    document[section][collection][index][field] = value
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


def test_admin_surface_cannot_claim_configured_identity_or_idp(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["surface_boundary_intent"]["surfaces"][1][
        "approved_identity_authorization"
    ] = "CONFIGURED"
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


def test_readiness_cannot_be_inferred_from_a_successful_http_body(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["health_intent"]["readiness"]["infer_from_http_200_body"] = "ALLOWED"
    document["health_intent"]["readiness"]["selected"]["success_status_codes"] = [200]
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


def test_liveness_cannot_be_reclassified_as_dependency_readiness(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["health_intent"]["liveness"]["purpose"] = (
        "DEPENDENCY_AND_MIGRATION_READINESS"
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize("family", generator.COMPONENT_FAMILIES)
def test_reference_component_label_tampering_is_rejected(
    contract_document: dict[str, Any], family: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["reference_architecture"]["component_families"][family] = (
        "REJECTED_COMPONENT"
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


def test_unknown_fields_are_rejected_without_echoing_names_or_values(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    marker = "REJECTED_INPUT_MARKER_1503"
    document[marker] = marker
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"
    assert marker not in str(captured.value)


def test_nested_resource_like_unknown_field_is_rejected(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["edge_routing_intent"]["resource"] = {
        "type": "aws_cloudfront_distribution"
    }
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"


def test_yaml_duplicate_keys_fail_with_sanitized_error(tmp_path: Path) -> None:
    marker = "REJECTED_INPUT_MARKER_1503"
    path = tmp_path / "duplicate.yaml"
    path.write_text(f"document: safe\ndocument: {marker}\n", encoding="utf-8")
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.load_yaml(path)
    assert captured.value.code == "YAML_INVALID"
    assert marker not in str(captured.value)


def test_yaml_aliases_are_forbidden_without_echoing_content(tmp_path: Path) -> None:
    marker = "REJECTED_INPUT_MARKER_1503"
    path = tmp_path / "alias.yaml"
    path.write_text(f"value: &blocked {marker}\ncopy: *blocked\n", encoding="utf-8")
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.load_yaml(path)
    assert captured.value.code == "YAML_ALIAS_FORBIDDEN"
    assert marker not in str(captured.value)


def test_json_duplicate_keys_fail_with_sanitized_error(tmp_path: Path) -> None:
    marker = "REJECTED_INPUT_MARKER_1503"
    path = tmp_path / "duplicate.json"
    path.write_text(f'{{"safe": 1, "safe": "{marker}"}}', encoding="utf-8")
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.load_json(path)
    assert captured.value.code == "JSON_DUPLICATE_KEY"
    assert marker not in str(captured.value)


def test_source_inventory_drift_and_reordering_fail_closed(
    contract_document: dict[str, Any],
) -> None:
    for mutation in ("digest", "duplicate", "reorder"):
        document = copy.deepcopy(contract_document)
        if mutation == "digest":
            document["sources"][0]["sha256"] = "0" * 64
        elif mutation == "duplicate":
            document["sources"][1] = copy.deepcopy(document["sources"][0])
        else:
            document["sources"][0], document["sources"][1] = (
                document["sources"][1],
                document["sources"][0],
            )
        with pytest.raises(generator.ComputeEdgeContractError) as captured:
            _validate(document)
        assert captured.value.code in {
            "SOURCE_DUPLICATE",
            "SOURCE_INVENTORY_DRIFT",
        }


def _copy_pinned_sources(target_root: Path) -> None:
    for relative in generator.PINNED_SOURCES:
        source = REPOSITORY_ROOT / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def test_predecessor_byte_drift_fails_closed(
    tmp_path: Path, contract_document: dict[str, Any]
) -> None:
    _copy_pinned_sources(tmp_path)
    predecessor = tmp_path / next(iter(generator.PREDECESSOR_SOURCES))
    predecessor.write_bytes(predecessor.read_bytes() + b"\n")
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == "SOURCE_DIGEST_MISMATCH"


def test_predecessor_semantic_drift_fails_even_if_digest_inventory_is_rebound(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"
    path = tmp_path / relative
    plan = json.loads(path.read_bytes())
    plan["activation"]["status"] = "ENABLED"
    path.write_text(json.dumps(plan), encoding="utf-8")
    new_digest = generator.sha256_file(path)
    predecessor_sources = dict(generator.PREDECESSOR_SOURCES)
    predecessor_sources[relative] = new_digest
    pinned_sources = {**generator.AUTHORITY_SOURCES, **predecessor_sources}
    monkeypatch.setattr(generator, "PREDECESSOR_SOURCES", predecessor_sources)
    monkeypatch.setattr(generator, "PINNED_SOURCES", pinned_sources)
    document = copy.deepcopy(contract_document)
    for row in document["sources"]:
        if row["uri"] == f"repo://{relative}":
            row["sha256"] = new_digest
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


def test_authority_semantic_drift_fails_even_if_digest_inventory_is_rebound(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = "docs/upstream/key_documents/RAOS_02_architecture_catalog_v0.1.yaml"
    path = tmp_path / relative
    architecture = yaml.safe_load(path.read_bytes())
    architecture["deployment"]["aws_mapping"]["compute"] = "OTHER_COMPUTE"
    path.write_text(yaml.safe_dump(architecture), encoding="utf-8")
    new_digest = generator.sha256_file(path)
    authority_sources = dict(generator.AUTHORITY_SOURCES)
    authority_sources[relative] = new_digest
    pinned_sources = {**authority_sources, **generator.PREDECESSOR_SOURCES}
    monkeypatch.setattr(generator, "AUTHORITY_SOURCES", authority_sources)
    monkeypatch.setattr(generator, "PINNED_SOURCES", pinned_sources)
    document = copy.deepcopy(contract_document)
    for row in document["sources"]:
        if row["uri"] == f"repo://{relative}":
            row["sha256"] = new_digest
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "AUTHORITY_ARCHITECTURE_DRIFT"


def test_contract_file_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.yaml"
    target.write_text("document: {}\n", encoding="utf-8")
    link = tmp_path / "contract.yaml"
    link.symlink_to(target)
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.load_yaml(link)
    assert captured.value.code == "UNSAFE_FILE_TYPE"


def test_pinned_source_ancestor_symlink_is_rejected_without_escape(
    tmp_path: Path, contract_document: dict[str, Any]
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == "UNSAFE_ANCESTOR"
    assert list(outside.iterdir()) == []
