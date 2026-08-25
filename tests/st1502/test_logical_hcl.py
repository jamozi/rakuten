"""Executable logical HCL and native-validation boundary tests for ST-1502."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import build_st1502_data_services as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_logical_plan_is_closed_private_encrypted_and_zero_action(
    data_services_model: generator.DataServicesModel,
) -> None:
    plan = generator.logical_plan_document(data_services_model)
    generator.validate_logical_plan_document(plan)
    assert plan["document"] == {
        "id": "RAOS-DATA-SERVICES-LOGICAL-PLAN-001",
        "version": "1.0.0",
        "story_id": "ST-1502",
        "classification": "DETERMINISTIC_NO_APPLY_LOGICAL_RESOURCE_GRAPH",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "generation_command": generator.GENERATION_COMMAND,
        "terraform_version": generator.TERRAFORM_VERSION,
        "provider_schema_bound": False,
        "provider_plugin_required": False,
        "physical_resources": False,
        "terraform_state": False,
    }
    nodes = plan["nodes"]
    assert isinstance(nodes, list)
    assert len(nodes) == 37
    assert [node["node_id"] for node in nodes] == [
        node["node_id"] for node in generator.logical_resource_nodes()
    ]
    assert all(node["public_access"] is False for node in nodes)
    assert all(
        not node["persisted_data"] or node["encryption_at_rest"] for node in nodes
    )
    assert all(
        not node["network_interaction"] or node["transport_encryption"]
        for node in nodes
    )
    assert plan["planned_actions"] == {action: 0 for action in generator.ACTION_NAMES}


def test_logical_plan_covers_reference_services_recovery_and_dlqs(
    data_services_model: generator.DataServicesModel,
) -> None:
    plan = generator.logical_plan_document(data_services_model)
    nodes = {node["node_id"]: node for node in plan["nodes"]}
    assert nodes["relational_database"]["reference_service"] == "RDS"
    assert nodes["relational_database"]["backup_declared"] is True
    assert nodes["relational_database"]["encryption_at_rest"] is True
    assert set(generator.OBJECT_NODE_IDS).issubset(nodes)
    assert all(
        nodes[node_id]["immutable_declared"] for node_id in generator.OBJECT_NODE_IDS
    )
    assert set(generator.KMS_NODE_IDS).issubset(nodes)
    assert all(
        nodes[node_id]["key_rotation_declared"] for node_id in generator.KMS_NODE_IDS
    )
    assert nodes["secret_metadata"]["contains_secret_material"] is False
    edges = {(edge["from"], edge["to"], edge["relationship"]) for edge in plan["edges"]}
    for primary, dlq in zip(
        generator.PRIMARY_QUEUE_NODE_IDS, generator.DLQ_NODE_IDS, strict=True
    ):
        assert (primary, dlq, "REDRIVES_TO") in edges
    assert (
        "backup_relational_pitr",
        "relational_database",
        "PROTECTS",
    ) in edges
    assert all(
        ("backup_object_versions", node_id, "PROTECTS") in edges
        for node_id in generator.OBJECT_NODE_IDS
    )


def test_logical_permissions_are_separated_and_wildcard_free(
    data_services_model: generator.DataServicesModel,
) -> None:
    permissions = generator.logical_plan_document(data_services_model)[
        "iam_permissions"
    ]
    assert set(permissions) == set(generator.IAM_ROLE_IDS)
    assert permissions["iam_queue_producer"] == ["queue.send"]
    assert permissions["iam_queue_consumer"] == [
        "queue.receive",
        "queue.delete",
        "queue.visibility.change",
    ]
    assert permissions["iam_queue_redrive_operator"] == ["queue.redrive"]
    assert all(
        permission != "*"
        and not permission.endswith(":*")
        and not permission.endswith(".*")
        for values in permissions.values()
        for permission in values
    )


def test_successor_activation_port_is_present_but_unsatisfied(
    data_services_model: generator.DataServicesModel,
) -> None:
    port = generator.logical_plan_document(data_services_model)[
        "successor_activation_port"
    ]
    assert port == generator.EXPECTED_SUCCESSOR_ACTIVATION_PORT
    assert port["successor_contract_revision_required"] is True
    assert port["supplied_gate_evidence"] == []
    assert port["complete_gate_evidence"] is False
    assert port["provider_binding"] == "FORBIDDEN_IN_CURRENT_REVISION"
    assert port["resource_materialization"] == "FORBIDDEN_IN_CURRENT_REVISION"
    assert port["infrastructure_plan"] == "FORBIDDEN"
    assert port["infrastructure_apply"] == "FORBIDDEN"


def test_hcl_bundle_is_exact_provider_backend_and_resource_free(
    data_services_model: generator.DataServicesModel,
) -> None:
    bundle = generator.render_hcl_bundle(data_services_model)
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
        "local-exec",
        "remote-exec",
    ):
        assert forbidden not in text
    assert f'required_version = "{generator.TERRAFORM_REQUIRED_VERSION}"' in text
    assert "activation_enabled == false" in text
    assert "production_apply_authorized == false" in text


def test_committed_hcl_and_logical_plan_match_owner_renderer(
    data_services_model: generator.DataServicesModel,
) -> None:
    for relative, content in generator.render_hcl_bundle(data_services_model).items():
        assert (REPOSITORY_ROOT / relative).read_bytes() == content
    logical_plan = REPOSITORY_ROOT / generator.LOGICAL_PLAN_PATH
    assert json.loads(logical_plan.read_bytes()) == generator.logical_plan_document(
        data_services_model
    )


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("public_access", True, "LOGICAL_PLAN_PUBLIC_EXPOSURE"),
        ("encryption_at_rest", False, "LOGICAL_PLAN_ENCRYPTION_DISABLED"),
        (
            "transport_encryption",
            False,
            "LOGICAL_PLAN_TRANSPORT_ENCRYPTION_DISABLED",
        ),
        ("backup_declared", False, "LOGICAL_PLAN_BACKUP_MISSING"),
        ("least_privilege", False, "LOGICAL_PLAN_WILDCARD_IAM"),
        ("wildcard_iam", True, "LOGICAL_PLAN_WILDCARD_IAM"),
        (
            "contains_secret_material",
            True,
            "LOGICAL_PLAN_SECRET_MATERIAL_FORBIDDEN",
        ),
    ],
)
def test_logical_plan_rejects_unsafe_database_mutations(
    data_services_model: generator.DataServicesModel,
    field: str,
    value: object,
    expected_code: str,
) -> None:
    plan = copy.deepcopy(generator.logical_plan_document(data_services_model))
    plan["nodes"][0][field] = value
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_logical_plan_document(plan)
    assert captured.value.code == expected_code


def test_logical_plan_rejects_missing_immutability_and_dlq(
    data_services_model: generator.DataServicesModel,
) -> None:
    plan = copy.deepcopy(generator.logical_plan_document(data_services_model))
    object_node = next(
        node for node in plan["nodes"] if node["node_id"] == "object_raw"
    )
    object_node["immutable_declared"] = False
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_logical_plan_document(plan)
    assert captured.value.code == "LOGICAL_PLAN_IMMUTABILITY_MISSING"

    plan = copy.deepcopy(generator.logical_plan_document(data_services_model))
    plan["edges"] = [
        edge
        for edge in plan["edges"]
        if not (
            edge["from"] == generator.PRIMARY_QUEUE_NODE_IDS[0]
            and edge["relationship"] == "REDRIVES_TO"
        )
    ]
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_logical_plan_document(plan)
    assert captured.value.code == "LOGICAL_PLAN_DLQ_MISSING"


@pytest.mark.parametrize("wildcard", ["*", "queue:*", "queue.*"])
def test_logical_plan_rejects_wildcard_iam(
    data_services_model: generator.DataServicesModel, wildcard: str
) -> None:
    plan = copy.deepcopy(generator.logical_plan_document(data_services_model))
    plan["iam_permissions"]["iam_queue_producer"] = [wildcard]
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_logical_plan_document(plan)
    assert captured.value.code == "LOGICAL_PLAN_WILDCARD_IAM"


@pytest.mark.parametrize(
    "injection",
    [
        '\nprovider "aws" {}\n',
        '\nbackend "s3" {}\n',
        '\nmodule "remote" { source = "invalid" }\n',
        '\ndata "external" "x" {}\n',
        '\nresource "aws_s3_bucket" "x" {}\n',
        '\nprovisioner "local-exec" {}\n',
    ],
)
def test_hcl_rejects_provider_backend_module_data_resource_and_provisioner_injection(
    data_services_model: generator.DataServicesModel, injection: str
) -> None:
    bundle = dict(generator.render_hcl_bundle(data_services_model))
    bundle[generator.HCL_PATHS[0]] += injection.encode("utf-8")
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_hcl_bundle(bundle)
    assert captured.value.code in {"HCL_FORBIDDEN_BLOCK", "HCL_FORBIDDEN_OPERATION"}


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b"public_access            = false", b"public_access            = true"),
        (b"encryption_at_rest       = true", b"encryption_at_rest       = false"),
        (b"transport_encryption     = true", b"transport_encryption     = false"),
        (b"backup_declared          = true", b"backup_declared          = false"),
        (b"dlq_declared             = true", b"dlq_declared             = false"),
    ],
)
def test_hcl_rejects_public_encryption_backup_and_dlq_weakening(
    data_services_model: generator.DataServicesModel, old: bytes, new: bytes
) -> None:
    bundle = dict(generator.render_hcl_bundle(data_services_model))
    locals_path = generator.HCL_PATHS[2]
    assert old in bundle[locals_path]
    bundle[locals_path] = bundle[locals_path].replace(old, new, 1)
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_hcl_bundle(bundle)
    assert captured.value.code == "HCL_SAFETY_DECLARATION_DRIFT"


def test_hcl_rejects_wildcard_permission_injection(
    data_services_model: generator.DataServicesModel,
) -> None:
    bundle = dict(generator.render_hcl_bundle(data_services_model))
    locals_path = generator.HCL_PATHS[2]
    bundle[locals_path] = bundle[locals_path].replace(b'"queue.send"', b'"*"', 1)
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_hcl_bundle(bundle)
    assert captured.value.code == "HCL_WILDCARD_IAM"


def test_hcl_rejects_tool_version_and_file_inventory_drift(
    data_services_model: generator.DataServicesModel,
) -> None:
    bundle = dict(generator.render_hcl_bundle(data_services_model))
    bundle[generator.HCL_PATHS[0]] = bundle[generator.HCL_PATHS[0]].replace(
        b"1.15.9", b"1.15.8"
    )
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_hcl_bundle(bundle)
    assert captured.value.code == "HCL_TOOL_VERSION_DRIFT"

    bundle = dict(generator.render_hcl_bundle(data_services_model))
    bundle.pop(generator.HCL_PATHS[-1])
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_hcl_bundle(bundle)
    assert captured.value.code == "HCL_FILE_INVENTORY_DRIFT"


def test_toolchain_lock_inherits_exact_st1501_validation_boundary(
    data_services_model: generator.DataServicesModel,
) -> None:
    lock = json.loads(
        generator.render_toolchain_lock(data_services_model, REPOSITORY_ROOT)
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
    with pytest.raises(generator.DataServicesContractError) as captured:
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
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.verify_native_hcl(REPOSITORY_ROOT, binary)
    assert captured.value.code == "NATIVE_VALIDATOR_DIGEST_MISMATCH"

    with pytest.raises(generator.DataServicesContractError) as captured:
        generator._native_command(
            tmp_path / "unshare",
            binary,
            ("version", "-json"),
            working_directory=tmp_path,
            data_directory=tmp_path / "data",
        )
    assert captured.value.code == "NETWORK_NAMESPACE_RUNNER_FORBIDDEN"


def test_native_validator_uses_only_closed_env_commands_and_makes_no_writes(
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
            ).encode("utf-8")
        elif arguments == ("validate", "-json"):
            output = json.dumps(
                {"valid": True, "error_count": 0, "warning_count": 0}
            ).encode("utf-8")
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
        ("selected_provider_schema", "hashicorp/aws"),
        ("selected_provider_plugin", "aws@latest"),
        ("selected_account_or_project", "account"),
        ("selected_primary_region", "ap-northeast-1"),
        ("selected_backup_region", "other"),
        ("selected_state_backend", "remote"),
        ("selected_credential_source", "ambient"),
        ("selected_network_segments", ["subnet"]),
        ("selected_security_policy_bindings", ["policy"]),
        ("selected_retention_policy_id", "retention"),
        ("supplied_gate_evidence", ["local-test"]),
        ("complete_gate_evidence", True),
        ("resource_materialization", "ALLOWED"),
        ("infrastructure_plan", "ALLOWED"),
        ("infrastructure_apply", "ALLOWED"),
    ],
)
def test_successor_activation_port_rejects_current_revision_binding(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["successor_activation_port"][field] = value
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.validate_contract(document, REPOSITORY_ROOT)
    assert captured.value.code in {
        "FIXED_VALUE_VIOLATION",
        "SELECTION_MUST_REMAIN_UNSET",
        "SAFE_BOUNDARY_VIOLATION",
    }
