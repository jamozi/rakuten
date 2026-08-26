"""Hostile and exact-type provider-neutral validation cases for ST-1503."""

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
HANDOFF_NORMATIVE_SECTIONS = (
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


def _validate(document: dict[str, Any]) -> generator.ComputeEdgeModel:
    return generator.validate_contract(document, REPOSITORY_ROOT)


def _copy_pinned_sources(target_root: Path) -> None:
    for relative in generator.PINNED_SOURCES:
        source = REPOSITORY_ROOT / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _rebind_source(
    document: dict[str, Any],
    relative: str,
    digest: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    authority: bool,
) -> None:
    if authority:
        sources = dict(generator.AUTHORITY_SOURCES)
        sources[relative] = digest
        monkeypatch.setattr(generator, "AUTHORITY_SOURCES", sources)
        pinned = {**sources, **generator.PREDECESSOR_SOURCES}
    else:
        sources = dict(generator.PREDECESSOR_SOURCES)
        sources[relative] = digest
        monkeypatch.setattr(generator, "PREDECESSOR_SOURCES", sources)
        pinned = {**generator.AUTHORITY_SOURCES, **sources}
    monkeypatch.setattr(generator, "PINNED_SOURCES", pinned)
    for row in document["sources"]:
        if row["uri"] == f"repo://{relative}":
            row["sha256"] = digest
            break
    else:
        raise AssertionError(relative)


@pytest.mark.parametrize(
    "mutation",
    ("missing", "unknown", "duplicate", "reorder"),
)
def test_capability_inventory_drift_fails_closed(
    contract_document: dict[str, Any],
    mutation: str,
) -> None:
    document = copy.deepcopy(contract_document)
    rows = document["provider_neutral_compute_edge_admission"][
        "capability_mapping_requirements"
    ]
    if mutation == "missing":
        rows.pop()
        expected = "MISSING_CAPABILITY_MAPPING"
    elif mutation == "unknown":
        rows[-1]["capability_id"] = "unknown_compute_edge_capability"
        expected = "UNKNOWN_CAPABILITY_MAPPING"
    elif mutation == "duplicate":
        rows[-1]["capability_id"] = rows[0]["capability_id"]
        expected = "DUPLICATE_CAPABILITY_MAPPING"
    else:
        rows[0], rows[1] = rows[1], rows[0]
        expected = "CAPABILITY_MAPPING_ORDER_DRIFT"
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == expected


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("selected_profile_id", "aws-reference"),
        ("selected_profile_kind", "AWS"),
        ("selected_provider_name", "AWS"),
        ("default_profile_id", "aws-tokyo"),
        ("fallback_profile_id", "aws-tokyo"),
        ("concrete_alternate_provider_selected", True),
        ("eligible", True),
        ("admission_status", "ELIGIBLE"),
    ),
)
def test_profile_selection_default_fallback_and_shortcut_fail_closed(
    contract_document: dict[str, Any],
    field: str,
    value: object,
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_compute_edge_admission"][field] = value
    with pytest.raises(generator.ComputeEdgeContractError):
        _validate(document)


@pytest.mark.parametrize(
    "binding",
    (
        "provider",
        "account_or_project",
        "region",
        "workload_runtime_or_scheduler",
        "image_registry",
        "ingress_or_edge",
        "dns_or_tls",
        "waf_or_abuse_control",
        "compute_edge_plugin_or_adapter",
    ),
)
@pytest.mark.parametrize("slot", ("selected", "default", "fallback"))
def test_every_provider_resource_binding_must_remain_unset(
    contract_document: dict[str, Any],
    binding: str,
    slot: str,
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_compute_edge_admission"]["binding_policy"][binding][
        slot
    ] = "AWS_LABEL_CANNOT_BIND"
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


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
@pytest.mark.parametrize(
    "section",
    ("reference_architecture", "provider_neutral_compute_edge_admission"),
)
def test_aws_reference_cannot_become_default_fallback_selection_or_evidence(
    contract_document: dict[str, Any],
    section: str,
    field: str,
) -> None:
    document = copy.deepcopy(contract_document)
    target = (
        document[section]
        if section == "reference_architecture"
        else document[section]["aws_reference_boundary"]
    )
    target[field] = True
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SAFE_BOUNDARY_VIOLATION"


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        (
            "reference_architecture",
            "classification",
            "OPTIONAL_HISTORICAL_AWS_REFERENCE_MAPPINGS_ONLY",
        ),
        (
            "provider_neutral_compute_edge_admission",
            "role",
            "OPTIONAL_HISTORICAL_REFERENCE_MAPPINGS_ONLY",
        ),
        (
            "provider_neutral_compute_edge_admission",
            "canonical_story_deliverables",
            "CANONICAL_STORY_DELIVERABLES_REPLACED_BY_PORTABILITY_OVERLAY",
        ),
        (
            "provider_neutral_compute_edge_admission",
            "non_aws_owner_managed_profiles",
            "REPLACEMENT_IMPLEMENTATION_PATHS",
        ),
    ),
)
def test_canonical_reference_cannot_be_demoted_or_replaced_by_overlay(
    contract_document: dict[str, Any], section: str, field: str, value: str
) -> None:
    document = copy.deepcopy(contract_document)
    target = (
        document["reference_architecture"]
        if section == "reference_architecture"
        else document["provider_neutral_compute_edge_admission"][
            "aws_reference_boundary"
        ]
    )
    target[field] = value
    with pytest.raises(generator.ComputeEdgeContractError):
        _validate(document)


@pytest.mark.parametrize("payload", ("AWS", "ECS", "Fargate", "CloudFront", "WAF"))
@pytest.mark.parametrize("field", ("selected_mapping", "evidence_refs"))
def test_aws_or_service_labels_cannot_satisfy_capability_or_evidence(
    contract_document: dict[str, Any],
    payload: str,
    field: str,
) -> None:
    document = copy.deepcopy(contract_document)
    row = document["provider_neutral_compute_edge_admission"][
        "capability_mapping_requirements"
    ][0]
    row[field] = [payload] if field == "evidence_refs" else payload
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize(
    "policy",
    (
        "provider_label_as_evidence",
        "service_label_as_evidence",
        "reference_metadata_as_evidence",
        "local_test_as_live_evidence",
    ),
)
def test_label_and_local_evidence_substitutions_remain_forbidden(
    contract_document: dict[str, Any],
    policy: str,
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_compute_edge_admission"]["evidence_equivalence_policy"][
        policy
    ] = "ALLOWED"
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("required_mapping_mode", "PARTIAL_OR_IMPLICIT"),
        ("required_capability_count", 7),
        ("configured_mapping_count", 1),
        ("complete_mapping", True),
        ("missing_mapping", "ALLOW"),
        ("unknown_mapping", "ALLOW"),
        ("duplicate_mapping", "ALLOW"),
        ("implicit_mapping", "ALLOW"),
        ("partial_mapping", "ALLOW"),
        ("provider_label_only_mapping", "ALLOW"),
        ("service_label_only_mapping", "ALLOW"),
        ("reference_only_mapping", "ALLOW"),
    ),
)
def test_every_mapping_policy_gate_rejects_relaxation(
    contract_document: dict[str, Any],
    field: str,
    value: object,
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_compute_edge_admission"]["mapping_policy"][field] = value
    with pytest.raises(generator.ComputeEdgeContractError):
        _validate(document)


@pytest.mark.parametrize(
    "field",
    (
        "implicit_binding",
        "name_or_reference_only_eligibility",
    ),
)
def test_binding_shortcut_gates_remain_forbidden(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_compute_edge_admission"]["binding_policy"][field] = (
        "ALLOWED"
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    "field",
    (
        "identical_security_evidence",
        "identical_operations_evidence",
        "identical_release_evidence",
        "identical_performance_load_evidence",
        "identical_health_slo_alerting_evidence",
        "identical_canary_rollback_evidence",
        "identical_identity_secret_egress_evidence",
        "identical_isolation_evidence",
        "identical_region_residency_evidence",
        "identical_transport_security_evidence",
    ),
)
def test_every_equivalent_evidence_gate_remains_required(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_compute_edge_admission"]["evidence_equivalence_policy"][
        field
    ] = "OPTIONAL"
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    "field",
    (
        "public_transport",
        "internal_transport",
        "provider_transport",
        "origin_transport",
    ),
)
def test_all_interaction_transport_security_gates_remain_required(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_compute_edge_admission"][
        "cross_capability_transport_security_policy"
    ][field] = "OPTIONAL"
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


def test_transport_security_exceptions_cannot_be_selected(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_compute_edge_admission"][
        "cross_capability_transport_security_policy"
    ]["selected_exceptions"] = ["INTERNAL"]
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize(
    "field",
    generator.EXPECTED_SECTIONS["selected_configuration"],
)
def test_all_concrete_configuration_bindings_remain_unset(
    contract_document: dict[str, Any],
    field: str,
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["selected_configuration"][field]
    document["selected_configuration"][field] = (
        ["AWS_LABEL_CANNOT_SELECT"] if isinstance(current, list) else "AWS"
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize("role_index", range(len(generator.WORKLOAD_ROLES)))
@pytest.mark.parametrize("field", generator._workload_selection())
def test_all_workload_runtime_identity_network_and_sizing_bindings_remain_unset(
    contract_document: dict[str, Any],
    role_index: int,
    field: str,
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["workload_intent"]["roles"][role_index]["selected"][field]
    document["workload_intent"]["roles"][role_index]["selected"][field] = (
        ["REJECTED_BINDING"] if isinstance(current, list) else "REJECTED_BINDING"
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize("surface_index", range(len(generator.SURFACE_ROLES)))
@pytest.mark.parametrize("field", generator._surface_selection())
def test_all_surface_domain_route_cache_cookie_csp_and_auth_bindings_remain_unset(
    contract_document: dict[str, Any],
    surface_index: int,
    field: str,
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["surface_boundary_intent"]["surfaces"][surface_index][
        "selected"
    ][field]
    document["surface_boundary_intent"]["surfaces"][surface_index]["selected"][
        field
    ] = ["REJECTED_BINDING"] if isinstance(current, list) else "REJECTED_BINDING"
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize(
    "field",
    generator.EXPECTED_SECTIONS["edge_routing_intent"]["selected"],
)
def test_all_edge_dns_tls_waf_origin_and_route_bindings_remain_unset(
    contract_document: dict[str, Any],
    field: str,
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["edge_routing_intent"]["selected"][field]
    document["edge_routing_intent"]["selected"][field] = (
        ["REJECTED_BINDING"] if isinstance(current, list) else "REJECTED_BINDING"
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize("probe", ("liveness", "readiness"))
def test_all_health_bindings_remain_unset(
    contract_document: dict[str, Any],
    probe: str,
) -> None:
    for field in generator.EXPECTED_SECTIONS["health_intent"][probe]["selected"]:
        document = copy.deepcopy(contract_document)
        current = document["health_intent"][probe]["selected"][field]
        document["health_intent"][probe]["selected"][field] = (
            ["REJECTED_BINDING"] if isinstance(current, list) else "REJECTED_BINDING"
        )
        with pytest.raises(generator.ComputeEdgeContractError) as captured:
            _validate(document)
        assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize(
    "field",
    (
        "network_access",
        "credential_access",
        "live_provider_calls",
        "external_writes",
        "deploy_action",
        "release_action",
        "production_action",
    ),
)
def test_every_execution_surface_remains_forbidden(
    contract_document: dict[str, Any],
    field: str,
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"][field] = "ALLOWED"
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize("command", generator.NATIVE_COMMANDS)
def test_every_native_command_remains_forbidden(
    contract_document: dict[str, Any],
    command: str,
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"]["commands"][command] = "ALLOWED"
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize("action", generator.ACTION_NAMES)
@pytest.mark.parametrize("value", (1, -1, True, "0"))
def test_actions_require_exact_integer_zero(
    contract_document: dict[str, Any],
    action: str,
    value: object,
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
    (
        ("workload_intent", "controlled_egress", "CONFIGURED"),
        ("workload_intent", "secret_material", "PRESENT"),
        ("surface_boundary_intent", "public_data_plane_access", "ALLOWED"),
        ("edge_routing_intent", "direct_origin_public_access", "ALLOWED"),
        ("edge_routing_intent", "origin_private_only", "OPTIONAL"),
        ("health_intent", "human_release_approval", "OPTIONAL"),
        ("health_intent", "kill_switch_change", "AUTOMATIC"),
    ),
)
def test_security_health_and_release_gates_cannot_be_downgraded(
    contract_document: dict[str, Any],
    section: str,
    field: str,
    value: object,
) -> None:
    document = copy.deepcopy(contract_document)
    document[section][field] = value
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    "decision_id", tuple(generator.EXPECTED_SECTIONS["open_decision_boundary"])
)
@pytest.mark.parametrize(
    ("field", "value"),
    (("resolved", True), ("blocking", False), ("status", "RESOLVED")),
)
def test_open_decisions_cannot_be_resolved_or_unblocked(
    contract_document: dict[str, Any],
    decision_id: str,
    field: str,
    value: object,
) -> None:
    document = copy.deepcopy(contract_document)
    document["open_decision_boundary"][decision_id][field] = value
    with pytest.raises(generator.ComputeEdgeContractError):
        _validate(document)


def test_unknown_and_nested_provider_resource_fields_are_rejected(
    contract_document: dict[str, Any],
) -> None:
    for section, field in (
        (None, "unknown_provider"),
        ("edge_routing_intent", "aws_cloudfront_distribution"),
        ("workload_intent", "ecs_cluster"),
    ):
        document = copy.deepcopy(contract_document)
        target = document if section is None else document[section]
        target[field] = {"selected": True}
        with pytest.raises(generator.ComputeEdgeContractError) as captured:
            _validate(document)
        assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"


@pytest.mark.parametrize("section", HANDOFF_NORMATIVE_SECTIONS)
def test_product_handoff_sections_are_semantically_validated_without_digest_authority(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    section: str,
) -> None:
    if section not in {
        "approved_story",
        "source_design_refs",
        "decision",
        "open_decision_state",
    }:
        pytest.skip("workflow prose is not an active implementation authority")
    _copy_pinned_sources(tmp_path)
    relative = generator.DESIGN_HANDOFF_PATH.as_posix()
    path = tmp_path / relative
    handoff = yaml.safe_load(path.read_bytes())
    value = handoff[section]
    if isinstance(value, list):
        value.append("HOSTILE_NORMATIVE_REPLACEMENT")
    elif isinstance(value, dict):
        first_key = next(iter(value))
        value[first_key] = "HOSTILE_NORMATIVE_REPLACEMENT"
    else:
        handoff[section] = "HOSTILE_NORMATIVE_REPLACEMENT"
    path.write_text(yaml.safe_dump(handoff, sort_keys=False), encoding="utf-8")
    document = copy.deepcopy(contract_document)
    _rebind_source(
        document,
        relative,
        generator.sha256_file(path),
        monkeypatch,
        authority=True,
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code in {
        "FIXED_VALUE_VIOLATION",
        "TYPE_MISMATCH",
    }


def test_handoff_approval_prose_is_not_an_implementation_gate(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = generator.DESIGN_HANDOFF_PATH.as_posix()
    path = tmp_path / relative
    handoff = yaml.safe_load(path.read_bytes())
    handoff["security_and_approval_gates"] = [
        "AWS labels automatically satisfy all gates"
    ]
    path.write_text(yaml.safe_dump(handoff, sort_keys=False), encoding="utf-8")
    document = copy.deepcopy(contract_document)
    _rebind_source(
        document,
        relative,
        generator.sha256_file(path),
        monkeypatch,
        authority=True,
    )
    model = generator.validate_contract(document, tmp_path)
    assert model.contract == document


@pytest.mark.parametrize(
    ("relative", "mutate"),
    (
        (
            "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
            "handoff",
        ),
        ("changes/st-1501/contracts/terraform-foundation.v1.yaml", "contract"),
        (
            "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
            "plan",
        ),
    ),
)
def test_predecessor_semantic_downgrades_fail_after_digest_rebind(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    mutate: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    if mutate == "handoff":
        payload = yaml.safe_load(path.read_bytes())
        payload["security_and_approval_gates"] = ["AWS label bypass"]
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    elif mutate == "contract":
        payload = yaml.safe_load(path.read_bytes())
        payload["execution_boundary"]["network_access"] = "ALLOWED"
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    else:
        payload = json.loads(path.read_bytes())
        payload["activation"]["network_access"] = "ALLOWED"
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    document = copy.deepcopy(contract_document)
    _rebind_source(
        document,
        relative,
        generator.sha256_file(path),
        monkeypatch,
        authority=False,
    )
    if mutate == "plan":
        with pytest.raises(generator.ComputeEdgeContractError) as captured:
            generator.validate_contract(document, tmp_path)
        assert captured.value.code != "SOURCE_DIGEST_MISMATCH"
    else:
        generator.validate_contract(document, tmp_path)


def test_predecessor_plan_formatting_drift_fails_after_digest_rebind(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"
    path = tmp_path / relative
    payload = json.loads(path.read_bytes())
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    document = copy.deepcopy(contract_document)
    _rebind_source(
        document,
        relative,
        generator.sha256_file(path),
        monkeypatch,
        authority=False,
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_GENERATED_DRIFT"


def test_current_canonical_authority_mapping_drift_fails_after_digest_rebind(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = "docs/upstream/key_documents/RAOS_02_architecture_catalog_v0.1.yaml"
    path = tmp_path / relative
    payload = yaml.safe_load(path.read_bytes())
    payload["deployment"]["aws_mapping"]["compute"] = "UNREVIEWED_REFERENCE"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    document = copy.deepcopy(contract_document)
    _rebind_source(
        document,
        relative,
        generator.sha256_file(path),
        monkeypatch,
        authority=True,
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "AUTHORITY_ARCHITECTURE_DRIFT"


def test_source_inventory_digest_duplicate_and_order_drift_fail_closed(
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
            "SOURCE_DIGEST_MISMATCH",
            "SOURCE_DUPLICATE",
            "SOURCE_INVENTORY_DRIFT",
        }


def test_yaml_duplicate_alias_tag_and_multiple_document_fail_closed(
    tmp_path: Path,
) -> None:
    cases = {
        "duplicate.yaml": ("safe: 1\nsafe: 2\n", "YAML_INVALID"),
        "alias.yaml": ("safe: &blocked 1\ncopy: *blocked\n", "YAML_ALIAS_FORBIDDEN"),
        "tag.yaml": ("safe: !blocked value\n", "YAML_TAG_FORBIDDEN"),
        "multi.yaml": ("safe: 1\n---\nother: 2\n", "YAML_INVALID"),
    }
    for name, (content, code) in cases.items():
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        with pytest.raises(generator.ComputeEdgeContractError) as captured:
            generator.load_yaml(path)
        assert captured.value.code == code


def test_json_duplicate_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"safe": 1, "safe": 2}', encoding="utf-8")
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.load_json(path)
    assert captured.value.code == "JSON_DUPLICATE_KEY"


def test_contract_and_pinned_source_symlinks_are_rejected(
    tmp_path: Path,
    contract_document: dict[str, Any],
) -> None:
    target = tmp_path / "target.yaml"
    target.write_text("document: {}\n", encoding="utf-8")
    link = tmp_path / "contract.yaml"
    link.symlink_to(target)
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.load_yaml(link)
    assert captured.value.code == "UNSAFE_FILE_TYPE"

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), root)
    assert captured.value.code == "UNSAFE_ANCESTOR"
    assert list(outside.iterdir()) == []
