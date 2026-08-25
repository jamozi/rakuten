"""Executable logical-HCL and native-validation boundary tests for ST-1503."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import build_st1503_compute_edge as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_logical_plan_is_closed_zero_action_and_provider_free(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    plan = generator.logical_plan_document(compute_edge_model)
    generator.validate_logical_plan_document(plan)
    assert plan["document"] == {
        "id": "RAOS-COMPUTE-EDGE-LOGICAL-PLAN-001",
        "version": "1.0.0",
        "story_id": "ST-1503",
        "classification": "DETERMINISTIC_NO_APPLY_LOGICAL_COMPUTE_EDGE_GRAPH",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "generation_command": generator.GENERATION_COMMAND,
        "terraform_version": generator.TERRAFORM_VERSION,
        "provider_schema_bound": False,
        "provider_plugin_required": False,
        "physical_resources": False,
        "terraform_state": False,
    }
    assert len(plan["components"]) == 37
    assert len(plan["edges"]) == 53
    assert plan["planned_actions"] == {action: 0 for action in generator.ACTION_NAMES}


def test_reference_services_cover_canonical_compute_edge_topology(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    components = generator.logical_plan_document(compute_edge_model)["components"]
    services = {
        service
        for component in components
        for service in component["reference_services"]
    }
    assert services == {
        "ECS",
        "Fargate",
        "ECR",
        "ALB",
        "CloudFront",
        "WAF",
        "Route53",
        "ACM",
    }


def test_public_admin_internal_and_private_origin_isolation(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    plan = generator.logical_plan_document(compute_edge_model)
    components = {row["component_id"]: row for row in plan["components"]}
    publicly_addressable = {
        component_id
        for component_id, component in components.items()
        if component["publicly_addressable"]
    }
    assert publicly_addressable == {
        "edge_public",
        "edge_admin",
        "dns_tls_public",
        "dns_tls_admin",
    }
    for component_id in generator.WORKLOAD_COMPONENT_IDS:
        assert components[component_id]["publicly_addressable"] is False
        assert components[component_id]["private_origin"] is True
        assert components[component_id]["direct_data_plane_access"] is False
    surfaces = plan["surface_policies"]
    assert surfaces["public"]["public_projection_only"] is True
    assert surfaces["admin"]["shared_cache_allowed"] is False
    assert surfaces["internal"]["shared_cache_allowed"] is False


def test_images_identity_egress_and_secrets_are_fail_closed(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    components = {
        row["component_id"]: row
        for row in generator.logical_plan_document(compute_edge_model)["components"]
    }
    for component_id in generator.WORKLOAD_COMPONENT_IDS:
        component = components[component_id]
        assert component["immutable_image_required"] is True
        assert component["digest_selection_required"] is True
        assert component["signed_provenance_required"] is True
        assert component["sbom_required"] is True
        assert component["image_scan_required"] is True
        assert component["controlled_egress_required"] is True
    assert all(not row["secret_material_present"] for row in components.values())


def test_liveness_and_readiness_are_distinct_and_unbound(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    health = generator.logical_plan_document(compute_edge_model)["health_contracts"]
    assert set(health) == set(generator.WORKLOAD_ROLES)
    for contract in health.values():
        assert contract["liveness"] == {
            "purpose": "PROCESS_ONLY",
            "external_provider_dependency": "FORBIDDEN",
            "database_dependency": "FORBIDDEN",
            "generic_http_200_inference": "FORBIDDEN",
            "endpoint_path": None,
            "listener_port": None,
            "matcher": None,
        }
        assert contract["readiness"]["purpose"] == (
            "DEPENDENCY_AND_MIGRATION_READINESS"
        )
        assert contract["readiness"]["generic_http_200_inference"] == "FORBIDDEN"
        assert contract["readiness"]["endpoint_path"] is None
        assert contract["readiness"]["listener_port"] is None
        assert contract["readiness"]["matcher"] is None


def test_waf_rate_observability_canary_and_rollback_are_required(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    components = {
        row["component_id"]: row
        for row in generator.logical_plan_document(compute_edge_model)["components"]
    }
    for component_id in generator.WAF_COMPONENT_IDS:
        assert components[component_id]["waf_required"] is True
        assert components[component_id]["rate_limit_required"] is True
    for component_id in generator.RATE_LIMIT_COMPONENT_IDS:
        assert components[component_id]["rate_limit_required"] is True
    assert all(component["observability_required"] for component in components.values())
    assert components["canary_release_boundary"]["canary_required"] is True
    assert components["rollback_boundary"]["rollback_required"] is True


def test_identity_permissions_are_explicit_and_wildcard_free(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    permissions = generator.logical_plan_document(compute_edge_model)[
        "identity_permissions"
    ]
    assert set(permissions) == set(generator.IDENTITY_PERMISSIONS)
    assert permissions["identity_public_web"] == [
        "public_projection.read",
        "telemetry.write",
    ]
    assert all(
        permission != "*"
        and not permission.endswith(":*")
        and not permission.endswith(".*")
        for values in permissions.values()
        for permission in values
    )


def test_successor_activation_port_is_present_and_unsatisfied(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    port = generator.logical_plan_document(compute_edge_model)[
        "successor_activation_port"
    ]
    assert port == generator.EXPECTED_SUCCESSOR_ACTIVATION_PORT
    assert port["supplied_gate_evidence"] == []
    assert port["complete_gate_evidence"] is False
    assert port["provider_binding"] == "FORBIDDEN_IN_CURRENT_REVISION"
    assert port["infrastructure_plan"] == "FORBIDDEN"
    assert port["infrastructure_apply"] == "FORBIDDEN"


def test_committed_hcl_and_logical_plan_match_owner_renderer(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    for relative, content in generator.render_hcl_bundle(compute_edge_model).items():
        assert (REPOSITORY_ROOT / relative).read_bytes() == content
    logical_plan = REPOSITORY_ROOT / generator.LOGICAL_PLAN_PATH
    assert json.loads(logical_plan.read_bytes()) == generator.logical_plan_document(
        compute_edge_model
    )


def test_hcl_bundle_has_only_validation_blocks_and_no_provider_schema(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    bundle = generator.render_hcl_bundle(compute_edge_model)
    generator.validate_hcl_bundle(bundle)
    assert set(bundle) == set(generator.HCL_PATHS)
    text = b"\n".join(bundle.values()).decode("utf-8")
    for forbidden in (
        'provider "',
        "backend {",
        'module "',
        'data "',
        'resource "',
        'provisioner "',
        "terraform_remote_state",
        "hashicorp/aws",
        "registry.terraform.io/",
    ):
        assert forbidden not in text
    assert f'required_version = "{generator.TERRAFORM_REQUIRED_VERSION}"' in text
    assert "var.activation_enabled == false" in text
    assert "var.production_apply_authorized == false" in text


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("secret_material_present", True, "LOGICAL_PLAN_SECRET_MATERIAL_FORBIDDEN"),
        ("direct_data_plane_access", True, "LOGICAL_PLAN_DATA_PLANE_EXPOSURE"),
        (
            "transport_encryption_required",
            False,
            "LOGICAL_PLAN_TRANSPORT_ENCRYPTION_DISABLED",
        ),
    ],
)
def test_logical_plan_rejects_security_boundary_mutations(
    compute_edge_model: generator.ComputeEdgeModel,
    field: str,
    value: object,
    expected_code: str,
) -> None:
    plan = copy.deepcopy(generator.logical_plan_document(compute_edge_model))
    plan["components"][1][field] = value
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_logical_plan_document(plan)
    assert captured.value.code == expected_code


@pytest.mark.parametrize(
    "field",
    [
        "immutable_image_required",
        "digest_selection_required",
        "signed_provenance_required",
        "sbom_required",
        "image_scan_required",
        "controlled_egress_required",
        "canary_required",
        "rollback_required",
    ],
)
def test_logical_plan_rejects_workload_supply_chain_weakening(
    compute_edge_model: generator.ComputeEdgeModel, field: str
) -> None:
    plan = copy.deepcopy(generator.logical_plan_document(compute_edge_model))
    plan["components"][1][field] = False
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_logical_plan_document(plan)
    assert captured.value.code == "LOGICAL_PLAN_WORKLOAD_SUPPLY_CHAIN_WEAKENED"


def test_logical_plan_rejects_public_origin_and_shared_admin_cache(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    plan = copy.deepcopy(generator.logical_plan_document(compute_edge_model))
    plan["components"][1]["publicly_addressable"] = True
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_logical_plan_document(plan)
    assert captured.value.code == "LOGICAL_PLAN_PRIVATE_ORIGIN_EXPOSED"

    plan = copy.deepcopy(generator.logical_plan_document(compute_edge_model))
    plan["surface_policies"]["admin"]["shared_cache_allowed"] = True
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_logical_plan_document(plan)
    assert captured.value.code == "LOGICAL_PLAN_SURFACE_ISOLATION_WEAKENED"


def test_logical_plan_rejects_health_semantic_conflation(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    plan = copy.deepcopy(generator.logical_plan_document(compute_edge_model))
    plan["health_contracts"]["public_web"]["liveness"][
        "external_provider_dependency"
    ] = "REQUIRED"
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_logical_plan_document(plan)
    assert captured.value.code == "LOGICAL_PLAN_HEALTH_SEMANTICS_WEAKENED"

    plan = copy.deepcopy(generator.logical_plan_document(compute_edge_model))
    plan["health_contracts"]["public_web"]["readiness"][
        "generic_http_200_inference"
    ] = "ALLOWED"
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_logical_plan_document(plan)
    assert captured.value.code == "LOGICAL_PLAN_HEALTH_SEMANTICS_WEAKENED"


@pytest.mark.parametrize("wildcard", ["*", "origin:*", "origin.*"])
def test_logical_plan_rejects_wildcard_identity_permissions(
    compute_edge_model: generator.ComputeEdgeModel, wildcard: str
) -> None:
    plan = copy.deepcopy(generator.logical_plan_document(compute_edge_model))
    plan["identity_permissions"]["identity_edge_origin"] = [wildcard]
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_logical_plan_document(plan)
    assert captured.value.code == "LOGICAL_PLAN_WILDCARD_IAM"


@pytest.mark.parametrize(
    "injection",
    [
        '\nprovider "aws" {}\n',
        '\nbackend "s3" {}\n',
        '\nmodule "remote" { source = "invalid" }\n',
        '\ndata "external" "x" {}\n',
        '\nresource "aws_ecs_service" "x" {}\n',
        '\nprovisioner "local-exec" {}\n',
    ],
)
def test_hcl_rejects_provider_and_physical_block_injection(
    compute_edge_model: generator.ComputeEdgeModel, injection: str
) -> None:
    bundle = dict(generator.render_hcl_bundle(compute_edge_model))
    bundle[generator.HCL_PATHS[0]] += injection.encode("utf-8")
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_hcl_bundle(bundle)
    assert captured.value.code in {"HCL_FORBIDDEN_BLOCK", "HCL_FORBIDDEN_OPERATION"}


def test_hcl_rejects_semantic_and_tool_version_drift(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    bundle = dict(generator.render_hcl_bundle(compute_edge_model))
    bundle[generator.HCL_PATHS[2]] = bundle[generator.HCL_PATHS[2]].replace(
        b"shared_cache_allowed            = false",
        b"shared_cache_allowed            = true ",
        1,
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_hcl_bundle(bundle)
    assert captured.value.code == "HCL_SEMANTIC_DRIFT"

    bundle = dict(generator.render_hcl_bundle(compute_edge_model))
    bundle[generator.HCL_PATHS[0]] = bundle[generator.HCL_PATHS[0]].replace(
        b"1.15.9", b"1.15.8"
    )
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_hcl_bundle(bundle)
    assert captured.value.code == "HCL_TOOL_VERSION_DRIFT"


def test_toolchain_lock_inherits_exact_st1501_validation_boundary(
    compute_edge_model: generator.ComputeEdgeModel,
) -> None:
    lock = json.loads(
        generator.render_toolchain_lock(compute_edge_model, REPOSITORY_ROOT)
    )
    assert lock["toolchain"]["version"] == generator.TERRAFORM_VERSION
    assert lock["toolchain"]["official_release"]["extracted_binary_sha256"] == (
        generator.TERRAFORM_BINARY_SHA256
    )
    boundary = lock["toolchain"]["validation_boundary"]
    assert boundary["allowed_commands"] == [
        "version -json",
        "fmt -check -recursive",
        "validate -json",
    ]
    assert boundary["provider_plugins"] == []
    assert boundary["initialization"] == "FORBIDDEN"
    assert lock["module"]["provider_requirements"] == []
    assert lock["module"]["physical_resources"] == []


def test_native_validator_rejects_forbidden_command_before_process_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def forbidden_run(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(generator.subprocess, "run", forbidden_run)
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator._native_command(
            Path("/usr/bin/unshare"),
            tmp_path / "terraform",
            ("plan",),
            working_directory=tmp_path,
            data_directory=tmp_path / "data",
        )
    assert captured.value.code == "NATIVE_VALIDATOR_COMMAND_FORBIDDEN"
    assert called is False


def test_native_validator_rejects_binary_digest_and_runner_drift(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "terraform"
    binary.write_bytes(b"not-the-pinned-binary")
    binary.chmod(0o700)
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.verify_native_hcl(REPOSITORY_ROOT, binary)
    assert captured.value.code == "NATIVE_VALIDATOR_DIGEST_MISMATCH"

    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator._native_command(
            tmp_path / "unshare",
            binary,
            ("version", "-json"),
            working_directory=tmp_path,
            data_directory=tmp_path / "data",
        )
    assert captured.value.code == "NETWORK_NAMESPACE_RUNNER_FORBIDDEN"


def test_native_validator_uses_only_closed_commands_and_makes_no_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "terraform"
    binary.write_bytes(b"fixture")
    binary.chmod(0o700)
    original_sha256_file = generator.sha256_file
    calls: list[tuple[tuple[str, ...], dict[str, str], Path]] = []

    def fake_sha256_file(path: Path) -> str:
        if path == binary:
            return generator.TERRAFORM_BINARY_SHA256
        return original_sha256_file(path)

    def fake_run(
        command: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        check: bool,
        capture_output: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[bytes]:
        assert check is False
        assert capture_output is True
        assert timeout == 30
        calls.append((command, env, cwd))
        arguments = command[6:]
        if arguments == ("version", "-json"):
            output = json.dumps(
                {
                    "terraform_version": generator.TERRAFORM_VERSION,
                    "platform": generator.TERRAFORM_PLATFORM,
                    "provider_selections": {},
                    "terraform_outdated": False,
                }
            ).encode()
        elif arguments == ("validate", "-json"):
            output = json.dumps(
                {"valid": True, "error_count": 0, "warning_count": 0}
            ).encode()
        else:
            assert arguments == ("fmt", "-check", "-recursive")
            output = b""
        return subprocess.CompletedProcess(command, 0, output, b"")

    monkeypatch.setattr(generator, "sha256_file", fake_sha256_file)
    monkeypatch.setattr(generator.subprocess, "run", fake_run)
    before = {
        relative: (REPOSITORY_ROOT / relative).read_bytes()
        for relative in generator.GENERATED_PATHS
    }
    result = generator.verify_native_hcl(REPOSITORY_ROOT, binary)
    after = {
        relative: (REPOSITORY_ROOT / relative).read_bytes()
        for relative in generator.GENERATED_PATHS
    }
    assert result == generator.NativeValidationResult(
        terraform_version=generator.TERRAFORM_VERSION,
        platform=generator.TERRAFORM_PLATFORM,
        provider_selections=(),
        format_valid=True,
        semantic_valid=True,
        network_namespace=True,
        repository_unchanged=True,
    )
    assert before == after
    assert [call[0][6:] for call in calls] == list(generator.ALLOWED_NATIVE_ARGUMENTS)
    for command, environment, _cwd in calls:
        assert command[:6] == (
            "/usr/bin/unshare",
            "--user",
            "--map-root-user",
            "--net",
            "--",
            str(binary),
        )
        assert set(environment) == {
            "CHECKPOINT_DISABLE",
            "LANG",
            "LC_ALL",
            "TF_DATA_DIR",
            "TF_IN_AUTOMATION",
            "TF_INPUT",
            "TF_REGISTRY_CLIENT_TIMEOUT",
            "TF_REGISTRY_DISCOVERY_RETRY",
        }
        assert not any(name.startswith(("AWS_", "TF_VAR_")) for name in environment)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("selected_provider_schema", "provider/schema"),
        ("selected_provider_plugin", "plugin-version"),
        ("selected_account_or_project", "account-reference"),
        ("selected_region", "region-reference"),
        ("selected_state_backend", "remote-state"),
        ("selected_credential_source", "ambient"),
        ("selected_network_segments", ["network-reference"]),
        ("selected_domain_names", ["example.invalid"]),
        ("selected_image_digests", ["digest-reference"]),
        ("selected_workload_identity_references", ["identity-reference"]),
        ("selected_secret_references", ["secret-reference"]),
        ("selected_waf_rule_definitions", ["rule-reference"]),
        ("selected_rate_limit_thresholds", [1]),
        ("selected_health_endpoint_bindings", ["health-reference"]),
        ("supplied_gate_evidence", ["local-only"]),
        ("complete_gate_evidence", True),
        ("provider_binding", "ALLOWED"),
        ("physical_resource_materialization", "ALLOWED"),
        ("infrastructure_plan", "ALLOWED"),
        ("infrastructure_apply", "ALLOWED"),
    ],
)
def test_successor_activation_port_rejects_current_revision_binding(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["successor_activation_port"][field] = value
    with pytest.raises(generator.ComputeEdgeContractError) as captured:
        generator.validate_contract(document, REPOSITORY_ROOT)
    assert captured.value.code in {
        "FIXED_VALUE_VIOLATION",
        "SELECTION_MUST_REMAIN_UNSET",
        "SAFE_BOUNDARY_VIOLATION",
    }
