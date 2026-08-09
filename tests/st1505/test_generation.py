"""Deterministic generation and ownership tests for ST-1505."""

from __future__ import annotations

import ast
import stat
from pathlib import Path

import pytest
import yaml

from scripts import build_st1505_staging_deployment as generator


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
            "uri": f"repo://{generator.REFERENCE_PLAN_PATH.as_posix()}",
            "bytes": (REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH).stat().st_size,
            "sha256": generator.sha256_file(
                REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH
            ),
        }
    ]


def test_manifest_pins_authority_predecessors_and_status_boundary() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
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
    assert boundary["environment_label"] == "STAGING"
    assert boundary["configuration_status"] == "NOT_CONFIGURED"
    assert boundary["activation"] == "DISABLED"
    assert boundary["action_counts"] == {
        name: 0 for name in generator.ACTION_COUNT_NAMES
    }
    for field in (
        "selected_provider",
        "selected_account",
        "selected_region",
        "selected_repository",
        "selected_environment",
        "selected_role",
        "selected_artifact",
    ):
        assert boundary[field] is None
    assert boundary["credentials"] == "ABSENT"
    for field in (
        "formal_tst_009",
        "formal_tst_022",
        "migration_database",
        "http_smoke",
        "playwright",
        "staging",
        "rollback",
        "release",
        "production",
    ):
        assert boundary[field] == "NOT_EXECUTED"


def test_check_rejects_drift_without_echoing_bytes(tmp_path: Path) -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    for relative, content in outputs.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    marker = b"REJECTED_OUTPUT_MARKER_1505"
    (tmp_path / generator.REFERENCE_PLAN_PATH).write_bytes(marker)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, outputs)
    assert captured.value.code == "GENERATED_OUTPUT_DRIFT"
    assert marker.decode("ascii") not in str(captured.value)


def test_check_rejects_missing_output_without_creating_directories(
    tmp_path: Path,
) -> None:
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, generator.render_outputs(REPOSITORY_ROOT))
    assert captured.value.code == "GENERATED_OUTPUT_MISSING"
    assert list(tmp_path.iterdir()) == []


def test_check_rejects_symlinked_output_ancestor_without_escape(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "infra").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, generator.render_outputs(REPOSITORY_ROOT))
    assert captured.value.code == "UNSAFE_OUTPUT_ANCESTOR"
    assert list(outside.iterdir()) == []


def test_check_rejects_symlinked_output_file_without_reading_target(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.json"
    marker = b"OUTSIDE_MARKER_1505"
    outside.write_bytes(marker)
    target = tmp_path / generator.REFERENCE_PLAN_PATH
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
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


def test_atomic_writer_rejects_symlink_target_without_touching_outside(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.json"
    marker = b"OUTSIDE_WRITE_MARKER_1505"
    outside.write_bytes(marker)
    target = tmp_path / generator.REFERENCE_PLAN_PATH
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator._atomic_write(tmp_path, generator.REFERENCE_PLAN_PATH, b"blocked\n")
    assert captured.value.code == "UNSAFE_FILE_TYPE"
    assert outside.read_bytes() == marker


def test_output_path_escape_and_symlinked_repository_root_are_rejected(
    tmp_path: Path,
) -> None:
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator._atomic_write(tmp_path, Path("../escape"), b"blocked\n")
    assert captured.value.code == "UNSAFE_OUTPUT_PATH"
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "root-link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(generator.StagingDeploymentContractError) as captured:
        generator._atomic_write(link, generator.REFERENCE_PLAN_PATH, b"blocked\n")
    assert captured.value.code == "UNSAFE_ROOT_TYPE"


def test_builder_has_no_ambient_env_network_process_provider_browser_or_native_tool_surface() -> (
    None
):
    path = REPOSITORY_ROOT / "scripts/build_st1505_staging_deployment.py"
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
            "github",
            "http",
            "playwright",
            "requests",
            "selenium",
            "socket",
            "subprocess",
            "terraform",
            "urllib",
        }
    )
    assert called_names.isdisjoint({"eval", "exec", "compile"})
    assert called_attributes.isdisjoint(
        {
            "check_call",
            "check_output",
            "connect",
            "environ",
            "getenv",
            "popen",
            "run",
            "spawn",
            "system",
            "urlopen",
        }
    )


def test_builder_cli_exposes_only_read_only_check_switch() -> None:
    assert generator.parse_args([]).check is False
    assert generator.parse_args(["--check"]).check is True
    with pytest.raises(SystemExit):
        generator.parse_args(["--deploy"])
    source = (REPOSITORY_ROOT / "scripts/build_st1505_staging_deployment.py").read_text(
        encoding="utf-8"
    )
    for forbidden_option in (
        "--provider",
        "--account",
        "--region",
        "--repository",
        "--environment",
        "--role",
        "--credential",
        "--artifact",
        "--release",
        "--migration",
        "--domain",
        "--url",
        "--browser",
        "--rollback",
        "--deploy",
        "--apply",
    ):
        assert forbidden_option not in source
