"""Deterministic generation and ownership tests for ST-1502."""

from __future__ import annotations

import ast
import stat
from pathlib import Path

import pytest
import yaml

from scripts import build_st1502_data_services as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _snapshot(paths: tuple[Path, ...]) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in paths
    }


def test_render_outputs_match_committed_bytes() -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    assert set(outputs) == set(generator.GENERATED_PATHS)
    for relative, expected in outputs.items():
        assert (REPOSITORY_ROOT / relative).read_bytes() == expected


def test_check_is_read_only() -> None:
    paths = tuple(REPOSITORY_ROOT / path for path in generator.GENERATED_PATHS)
    before = _snapshot(paths)
    generator.build(REPOSITORY_ROOT, check=True)
    after = _snapshot(paths)
    assert after == before


def test_manifest_inventory_and_hashes_are_complete() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["source_artifact_count"] == len(generator.SOURCE_ARTIFACT_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    for row in manifest["source_artifacts"]:
        path = REPOSITORY_ROOT / row["uri"].removeprefix("repo://")
        content = path.read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == generator.sha256_bytes(content)
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{relative.as_posix()}",
            "bytes": (REPOSITORY_ROOT / relative).stat().st_size,
            "sha256": generator.sha256_file(REPOSITORY_ROOT / relative),
        }
        for relative in generator.GENERATED_ARTIFACT_PATHS
    ]


def test_manifest_pins_authority_predecessor_and_status_boundary() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["document"] == {
        "id": "RAOS-DATA-SERVICES-MANIFEST-001",
        "version": "1.2.0",
        "story_id": "ST-1502",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "generation_command": generator.GENERATION_COMMAND,
    }
    assert manifest["provenance"]["contract_sha256"] == generator.sha256_file(
        REPOSITORY_ROOT / generator.CONTRACT_PATH
    )
    assert manifest["provenance"]["authority_inputs"] == [
        {"uri": f"repo://{path}", "sha256": digest}
        for path, digest in generator.AUTHORITY_SOURCES.items()
    ]
    assert manifest["provenance"]["predecessor_inputs"] == [
        {"uri": f"repo://{path}", "sha256": digest}
        for path, digest in generator.PREDECESSOR_SOURCES.items()
    ]
    boundary = manifest["boundary"]
    assert boundary["classification"] == (
        "SOURCE_DERIVED_PROVIDER_SCHEMA_FREE_EXECUTABLE_LOGICAL_DATA_SERVICES_HCL"
    )
    assert boundary["activation"] == "DISABLED"
    assert boundary["planned_actions"] == {
        action: 0 for action in generator.ACTION_NAMES
    }
    assert boundary["hcl_module"] == (
        "PROVIDER_SCHEMA_FREE_VALIDATION_ONLY_LOGICAL_GRAPH"
    )
    assert boundary["hcl_file_count"] == len(generator.HCL_PATHS)
    assert boundary["logical_resource_node_count"] == len(
        generator.logical_resource_nodes()
    )
    assert boundary["logical_edge_count"] == len(generator.logical_resource_edges())
    assert boundary["logical_iam_role_count"] == len(generator.IAM_ROLE_IDS)
    assert boundary["terraform_cli_version"] == generator.TERRAFORM_VERSION
    assert boundary["terraform_binary_sha256"] == generator.TERRAFORM_BINARY_SHA256
    assert boundary["provider_schema"] is None
    assert boundary["provider_plugins"] == []
    assert boundary["backend"] is None
    assert boundary["physical_resources"] == []
    assert boundary["local_native_validation"] == "EXECUTED_LOCAL_NOT_FORMAL"
    for field in (
        "network_access",
        "credential_access",
        "live_provider_calls",
        "external_writes",
        "migration_action",
        "backup_action",
        "restore_action",
        "redrive_action",
        "destructive_action",
        "deploy_action",
        "release_action",
        "production_action",
    ):
        assert boundary[field] == "FORBIDDEN"
    for field in (
        "formal_tst_026",
        "formal_tst_029",
        "restore_validation",
        "provider_validation",
        "live_staging_release_production",
    ):
        assert boundary[field] == "NOT_EXECUTED"
    assert manifest["manifest_self_integrity"] == {
        "included_in_generated_artifacts": False,
        "verification": "deterministic byte-for-byte regeneration via --check",
    }


def test_check_rejects_drift_without_echoing_bytes(tmp_path: Path) -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    for relative, content in outputs.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    marker = b"REJECTED_OUTPUT_MARKER_1502"
    (tmp_path / generator.REFERENCE_PLAN_PATH).write_bytes(marker)
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.check_outputs(tmp_path, outputs)
    assert captured.value.code == "GENERATED_OUTPUT_DRIFT"
    assert marker.decode("ascii") not in str(captured.value)


def test_check_rejects_symlinked_output_ancestor_without_escape(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "infra").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.check_outputs(tmp_path, generator.render_outputs(REPOSITORY_ROOT))
    assert captured.value.code == "UNSAFE_OUTPUT_ANCESTOR"
    assert list(outside.iterdir()) == []


def test_check_rejects_symlinked_output_file_without_reading_target(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.json"
    marker = b"OUTSIDE_MARKER_1502"
    outside.write_bytes(marker)
    target = tmp_path / generator.REFERENCE_PLAN_PATH
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    with pytest.raises(generator.DataServicesContractError) as captured:
        generator.check_outputs(tmp_path, generator.render_outputs(REPOSITORY_ROOT))
    assert captured.value.code == "UNSAFE_FILE_TYPE"
    assert outside.read_bytes() == marker


def test_atomic_writer_replaces_only_fixed_regular_output(tmp_path: Path) -> None:
    generator._atomic_write(tmp_path, generator.REFERENCE_PLAN_PATH, b"first\n")
    generator._atomic_write(tmp_path, generator.REFERENCE_PLAN_PATH, b"second\n")
    target = tmp_path / generator.REFERENCE_PLAN_PATH
    assert target.read_bytes() == b"second\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_builder_has_no_provider_or_network_client_surface() -> None:
    path = REPOSITORY_ROOT / "scripts/build_st1502_data_services.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    called_names: set[str] = set()
    called_attributes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_attributes.add(node.func.attr)
    assert imported_roots.isdisjoint(
        {
            "boto3",
            "botocore",
            "http",
            "requests",
            "socket",
            "urllib",
        }
    )
    assert called_names.isdisjoint({"eval", "exec", "compile"})
    assert called_attributes.isdisjoint(
        {
            "check_call",
            "check_output",
            "environ",
            "getenv",
            "popen",
            "spawn",
            "system",
        }
    )
    assert "subprocess" in imported_roots
    assert "run" in called_attributes


def test_builder_cli_exposes_only_generation_and_read_only_validation_switches() -> (
    None
):
    parser_result = generator.parse_args([])
    check_result = generator.parse_args(["--check"])
    assert parser_result.check is False
    assert check_result.check is True
    native = generator.parse_args(
        ["--native-check", "--terraform", "/absolute/terraform"]
    )
    assert native.native_check is True
    assert native.terraform == Path("/absolute/terraform")
    source = (REPOSITORY_ROOT / "scripts/build_st1502_data_services.py").read_text(
        encoding="utf-8"
    )
    for forbidden_option in (
        "--account",
        "--region",
        "--provider",
        "--credential",
        "--backend",
        "--retention",
        "--apply",
        "--destroy",
    ):
        assert forbidden_option not in source
