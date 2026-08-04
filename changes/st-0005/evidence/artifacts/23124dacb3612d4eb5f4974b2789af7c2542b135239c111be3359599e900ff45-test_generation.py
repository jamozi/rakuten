"""Determinism, manifest, no-write, and atomic-install tests for ST-0201."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest
import yaml

from conftest import REPOSITORY_ROOT
from scripts import build_st0201_postgres_service as generator


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _installed_state(root: Path) -> dict[str, tuple[int, int, int, str]]:
    state: dict[str, tuple[int, int, int, str]] = {}
    for relative in generator.GENERATED_PATHS:
        path = root / relative
        metadata = path.stat()
        state[relative.as_posix()] = (
            stat.S_IMODE(metadata.st_mode),
            metadata.st_size,
            metadata.st_mtime_ns,
            _sha256(path.read_bytes()),
        )
    return state


def _synthetic_outputs(prefix: bytes = b"new") -> dict[Path, bytes]:
    return {
        relative: prefix + b":" + relative.as_posix().encode("utf-8") + b"\n"
        for relative in generator.GENERATED_PATHS
    }


def _write_outputs(root: Path, outputs: dict[Path, bytes]) -> None:
    for relative, content in outputs.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o644)


def _temporary_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if ".st0201-" in path.name]


def test_rendering_twice_is_byte_identical_and_complete() -> None:
    first = generator.render_outputs(REPOSITORY_ROOT)
    second = generator.render_outputs(REPOSITORY_ROOT)
    assert first == second
    assert tuple(first) == generator.GENERATED_PATHS
    assert all(content.endswith(b"\n") for content in first.values())


def test_wrapper_compose_digest_binding_fails_closed(tmp_path: Path) -> None:
    wrapper = tmp_path / generator.RUNTIME_WRAPPER_PATH
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text(
        "readonly expected_compose_sha256='" + "0" * 64 + "'\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Compose digest binding drifted"):
        generator.validate_wrapper_compose_binding(tmp_path, b"services: {}\n")


def test_committed_outputs_equal_one_deterministic_render() -> None:
    expected = generator.render_outputs(REPOSITORY_ROOT)
    for relative in generator.GENERATED_PATHS:
        path = REPOSITORY_ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert path.read_bytes() == expected[relative]
        assert stat.S_IMODE(path.stat().st_mode) & 0o022 == 0


def test_check_function_accepts_current_outputs_without_writing() -> None:
    before = _installed_state(REPOSITORY_ROOT)
    generator.check_generated(REPOSITORY_ROOT)
    assert _installed_state(REPOSITORY_ROOT) == before


def test_check_cli_is_no_write_and_reports_unexecuted_boundary() -> None:
    before = _installed_state(REPOSITORY_ROOT)
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/build_st0201_postgres_service.py"),
            "--check",
        ],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert json.loads(result.stdout) == {
        "docker_runtime": "NOT_EXECUTED",
        "formal_tst_008": "NOT_EXECUTED",
        "generated_artifacts": 2,
        "mode": "check",
        "status": "PASS",
        "story_id": "ST-0201",
    }
    assert result.stderr == ""
    assert _installed_state(REPOSITORY_ROOT) == before


def test_manifest_hashes_every_source_and_compose_output() -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    manifest = yaml.safe_load(outputs[generator.MANIFEST_PATH])
    source_rows = manifest["source_artifacts"]
    assert manifest["source_artifact_count"] == len(source_rows)
    assert [row["uri"] for row in source_rows] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    for relative, row in zip(generator.SOURCE_ARTIFACT_PATHS, source_rows, strict=True):
        content = (REPOSITORY_ROOT / relative).read_bytes()
        assert row == {
            "uri": f"repo://{relative.as_posix()}",
            "bytes": len(content),
            "sha256": _sha256(content),
        }
    assert manifest["generated_artifact_count"] == 1
    assert manifest["generated_artifacts"] == [
        {
            "uri": "repo://docker-compose.yml",
            "bytes": len(outputs[generator.COMPOSE_PATH]),
            "sha256": _sha256(outputs[generator.COMPOSE_PATH]),
        }
    ]
    assert manifest["manifest_self_integrity"] == {
        "included_in_generated_artifacts": False,
        "verification": "deterministic byte-for-byte regeneration via --check",
    }


def test_manifest_covers_cross_story_repository_integration_surfaces() -> None:
    assert {path.as_posix() for path in generator.SOURCE_ARTIFACT_PATHS} >= {
        ".github/workflows/ci.yml",
        "changes/st-0107/contracts/pr-governance.v1.yaml",
        "changes/st-0107/manifest.yaml",
        "tests/st0106/test_workflow_contract.py",
        "workspace-layout.json",
        "infra/docker/README.md",
        "AGENTS.md",
        "Makefile",
        "README.md",
    }


def test_manifest_preserves_image_provenance_and_boundary() -> None:
    manifest = yaml.safe_load(
        generator.render_outputs(REPOSITORY_ROOT)[generator.MANIFEST_PATH]
    )
    assert manifest["provenance"]["architecture_snapshot"] == {
        "uri": "repo://docs/architecture/ST-0201-postgres-image-snapshot.yaml",
        "sha256": generator.EXPECTED_ARCHITECTURE_SNAPSHOT_SHA256,
    }
    assert manifest["provenance"]["image"] == {
        "reference": generator.EXPECTED_IMAGE["reference"],
        "index_digest": generator.EXPECTED_IMAGE["index_digest"],
        "linux_amd64_manifest_digest": generator.EXPECTED_IMAGE["platform"][
            "manifest_digest"
        ],
        "config_digest": generator.EXPECTED_IMAGE["platform"]["config_digest"],
    }
    assert manifest["boundary"] == {
        "environment": "LOCAL_AND_CI_ONLY",
        "production_use": "FORBIDDEN",
        "remote_database": "FORBIDDEN",
        "docker_runtime": "NOT_EXECUTED",
        "container_vulnerability_scan": "NOT_EXECUTED",
        "formal_tst_008": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
    }


def test_install_creates_outputs_with_safe_modes_and_no_stages(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outputs = _synthetic_outputs()
    generator.install_outputs(outputs, repository)
    for relative, expected in outputs.items():
        target = repository / relative
        assert target.read_bytes() == expected
        assert stat.S_IMODE(target.stat().st_mode) == 0o644
    assert _temporary_files(repository) == []


def test_install_rolls_back_compose_after_manifest_commit_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    previous = _synthetic_outputs(b"old")
    replacement = _synthetic_outputs(b"new")
    _write_outputs(repository, previous)
    real_replace = generator.os.replace
    injected = False

    def fail_manifest_once(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        nonlocal injected
        if not injected and Path(target).name == generator.MANIFEST_PATH.name:
            injected = True
            raise OSError("injected manifest commit failure")
        real_replace(source, target)

    monkeypatch.setattr(generator.os, "replace", fail_manifest_once)
    with pytest.raises(OSError, match="injected manifest commit failure"):
        generator.install_outputs(replacement, repository)
    assert injected is True
    for relative, expected in previous.items():
        assert (repository / relative).read_bytes() == expected
    assert _temporary_files(repository) == []


def test_install_stage_failure_preserves_previous_outputs_and_cleans_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    previous = _synthetic_outputs(b"old")
    _write_outputs(repository, previous)
    real_stage = generator._stage_file
    calls = 0

    def fail_second_stage(parent: Path, name: str, content: bytes) -> Path:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected staging failure")
        return real_stage(parent, name, content)

    monkeypatch.setattr(generator, "_stage_file", fail_second_stage)
    with pytest.raises(OSError, match="injected staging failure"):
        generator.install_outputs(_synthetic_outputs(), repository)
    for relative, expected in previous.items():
        assert (repository / relative).read_bytes() == expected
    assert _temporary_files(repository) == []


def test_install_rejects_symlink_parent_without_writing_outside(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    repository.mkdir()
    outside.mkdir()
    (repository / "changes").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="generated parent is not a real directory"):
        generator.install_outputs(_synthetic_outputs(), repository)
    assert list(outside.iterdir()) == []
    assert not (repository / generator.COMPOSE_PATH).exists()
    assert _temporary_files(repository) == []


def test_install_rejects_symlink_target_without_modifying_target(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    repository.mkdir()
    outside.write_bytes(b"outside\n")
    (repository / generator.COMPOSE_PATH).symlink_to(outside)
    with pytest.raises(RuntimeError, match="generated target cannot be a symlink"):
        generator.install_outputs(_synthetic_outputs(), repository)
    assert outside.read_bytes() == b"outside\n"
    assert _temporary_files(repository) == []


def test_install_rejects_output_inventory_addition(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outputs = _synthetic_outputs()
    outputs[Path("../escape")] = b"escape\n"
    with pytest.raises(RuntimeError, match="output inventory differs"):
        generator.install_outputs(outputs, repository)
    assert not (tmp_path / "escape").exists()


def test_safe_parent_rejects_unsafe_relative_path(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    with pytest.raises(RuntimeError, match="unsafe generated path"):
        generator._safe_parent(repository, Path("../escape"))
    assert not (tmp_path / "escape").exists()


def test_check_rejects_drift_and_group_writable_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outputs = _synthetic_outputs()
    _write_outputs(repository, outputs)
    monkeypatch.setattr(generator, "render_outputs", lambda root: outputs)
    generator.check_generated(repository)
    compose = repository / generator.COMPOSE_PATH
    compose.write_bytes(b"drift\n")
    with pytest.raises(RuntimeError, match="generated artifact drift"):
        generator.check_generated(repository)
    compose.write_bytes(outputs[generator.COMPOSE_PATH])
    compose.chmod(0o664)
    with pytest.raises(RuntimeError, match="group/world writable"):
        generator.check_generated(repository)


def test_install_rejects_missing_output_inventory(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outputs = _synthetic_outputs()
    del outputs[generator.MANIFEST_PATH]
    with pytest.raises(RuntimeError, match="output inventory differs"):
        generator.install_outputs(outputs, repository)
