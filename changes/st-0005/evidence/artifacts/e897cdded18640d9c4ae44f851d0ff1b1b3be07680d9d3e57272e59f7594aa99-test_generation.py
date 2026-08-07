"""Determinism, manifest, check-mode, and atomic-install tests for ST-0107."""

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
from scripts import build_st0107_pr_governance as generator


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
    return [path for path in root.rglob("*") if ".st0107-" in path.name]


def test_rendering_twice_is_byte_identical_and_complete() -> None:
    first = generator.render_outputs(REPOSITORY_ROOT)
    second = generator.render_outputs(REPOSITORY_ROOT)
    assert first == second
    assert tuple(first) == generator.GENERATED_PATHS
    assert all(content.endswith(b"\n") for content in first.values())


def test_committed_outputs_equal_one_deterministic_render() -> None:
    expected = generator.render_outputs(REPOSITORY_ROOT)
    for relative in generator.GENERATED_PATHS:
        path = REPOSITORY_ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert path.read_bytes() == expected[relative]
        assert stat.S_IMODE(path.stat().st_mode) & 0o022 == 0


def test_check_function_accepts_current_generated_artifacts_without_writing() -> None:
    before = _installed_state(REPOSITORY_ROOT)
    generator.check_generated(REPOSITORY_ROOT)
    assert _installed_state(REPOSITORY_ROOT) == before


def test_check_cli_is_no_write_and_reports_the_local_evidence_boundary() -> None:
    before = _installed_state(REPOSITORY_ROOT)
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/build_st0107_pr_governance.py"),
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
        "generated_artifacts": 4,
        "live_ruleset": "NOT_EXECUTED",
        "mode": "check",
        "owner_bindings": "UNVERIFIED_PLACEHOLDERS",
        "status": "PASS",
        "story_id": "ST-0107",
    }
    assert result.stderr == ""
    assert _installed_state(REPOSITORY_ROOT) == before


def test_manifest_hash_binds_every_source_and_non_manifest_output() -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    manifest = yaml.safe_load(outputs[generator.MANIFEST_PATH])
    assert isinstance(manifest, dict)

    source_rows = manifest["source_artifacts"]
    assert manifest["source_artifact_count"] == len(source_rows)
    assert [row["uri"] for row in source_rows] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    assert {
        Path("scripts/build_local_compose.py"),
        Path("scripts/object_storage_service.sh"),
        Path("scripts/object_storage_fixture.py"),
    } <= set(generator.SOURCE_ARTIFACT_PATHS)
    for relative, row in zip(generator.SOURCE_ARTIFACT_PATHS, source_rows, strict=True):
        content = (REPOSITORY_ROOT / relative).read_bytes()
        assert row == {
            "uri": f"repo://{relative.as_posix()}",
            "bytes": len(content),
            "sha256": _sha256(content),
        }

    generated_rows = manifest["generated_artifacts"]
    generated_paths = (
        generator.CODEOWNERS_PATH,
        generator.PULL_REQUEST_TEMPLATE_PATH,
        generator.RULESET_POLICY_PATH,
    )
    assert manifest["generated_artifact_count"] == len(generated_rows) == 3
    for relative, row in zip(generated_paths, generated_rows, strict=True):
        content = outputs[relative]
        assert row == {
            "uri": f"repo://{relative.as_posix()}",
            "bytes": len(content),
            "sha256": _sha256(content),
        }
    assert all(
        row["uri"] != f"repo://{generator.MANIFEST_PATH.as_posix()}"
        for row in generated_rows
    )
    assert manifest["manifest_self_integrity"] == {
        "included_in_generated_artifacts": False,
        "verification": "deterministic byte-for-byte regeneration via --check",
    }


def test_manifest_preserves_provenance_and_unexecuted_boundary() -> None:
    manifest = yaml.safe_load(
        generator.render_outputs(REPOSITORY_ROOT)[generator.MANIFEST_PATH]
    )
    assert manifest["document"] == {
        "id": "RAOS-PR-GOVERNANCE-MANIFEST-001",
        "version": "1.0.0",
        "story_id": "ST-0107",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "generation_command": generator.GENERATION_COMMAND,
    }
    assert manifest["provenance"] == {
        "contract_uri": f"repo://{generator.CONTRACT_PATH.as_posix()}",
        "canonical_inputs": [
            {"uri": f"repo://{relative}", "sha256": digest}
            for relative, digest in generator.PINNED_SOURCES.items()
        ],
    }
    assert manifest["boundary"] == {
        "owner_bindings": "UNVERIFIED_PLACEHOLDERS",
        "ruleset_policy": "DESIRED_STATE_NOT_API_PAYLOAD",
        "remote_mutation": "FORBIDDEN",
        "live_ruleset": "NOT_EXECUTED",
        "formal_tst_001": "NOT_EXECUTED",
    }


def test_install_creates_all_artifacts_with_safe_modes_and_no_stages(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outputs = _synthetic_outputs()

    generator.install_outputs(outputs, repository)

    for relative, expected in outputs.items():
        target = repository / relative
        assert target.read_bytes() == expected
        assert stat.S_IMODE(target.stat().st_mode) == 0o644
    assert _temporary_files(repository) == []


def test_install_rolls_back_every_replaced_file_after_mid_commit_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    previous = _synthetic_outputs(b"old")
    replacement = _synthetic_outputs(b"new")
    _write_outputs(repository, previous)
    real_replace = generator.os.replace
    injected = False

    def fail_ruleset_once(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        nonlocal injected
        if not injected and Path(target).name == generator.RULESET_POLICY_PATH.name:
            injected = True
            raise OSError("injected mid-commit failure")
        real_replace(source, target)

    monkeypatch.setattr(generator.os, "replace", fail_ruleset_once)
    with pytest.raises(OSError, match="injected mid-commit failure"):
        generator.install_outputs(replacement, repository)

    assert injected is True
    for relative, expected in previous.items():
        assert (repository / relative).read_bytes() == expected
    assert _temporary_files(repository) == []


def test_install_stage_failure_preserves_existing_outputs_and_cleans_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    previous = _synthetic_outputs(b"old")
    _write_outputs(repository, previous)
    real_stage_file = generator._stage_file
    calls = 0

    def fail_third_stage(parent: Path, name: str, content: bytes) -> Path:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("injected staging failure")
        return real_stage_file(parent, name, content)

    monkeypatch.setattr(generator, "_stage_file", fail_third_stage)
    with pytest.raises(OSError, match="injected staging failure"):
        generator.install_outputs(_synthetic_outputs(b"new"), repository)

    for relative, expected in previous.items():
        assert (repository / relative).read_bytes() == expected
    assert _temporary_files(repository) == []


def test_install_rejects_symlink_parent_without_writing_outside(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    repository.mkdir()
    outside.mkdir()
    (repository / ".github").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="generated parent is not a real directory"):
        generator.install_outputs(_synthetic_outputs(), repository)

    assert list(outside.iterdir()) == []
    assert _temporary_files(repository) == []


def test_install_rejects_symlink_target_without_modifying_target(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    github = repository / ".github"
    outside = tmp_path / "outside"
    github.mkdir(parents=True)
    outside.write_bytes(b"outside\n")
    (github / "CODEOWNERS").symlink_to(outside)

    with pytest.raises(RuntimeError, match="generated target cannot be a symlink"):
        generator.install_outputs(_synthetic_outputs(), repository)

    assert outside.read_bytes() == b"outside\n"
    assert _temporary_files(repository) == []


def test_install_rejects_unsafe_relative_output_path(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outputs = _synthetic_outputs()
    outputs[Path("../escape")] = b"escape\n"

    with pytest.raises(RuntimeError, match="unsafe generated path"):
        generator.install_outputs(outputs, repository)

    assert not (tmp_path / "escape").exists()
    assert _temporary_files(repository) == []


def test_check_rejects_drift_and_group_writable_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outputs = _synthetic_outputs()
    _write_outputs(repository, outputs)
    monkeypatch.setattr(generator, "render_outputs", lambda root: outputs)

    generator.check_generated(repository)
    drifted = repository / generator.CODEOWNERS_PATH
    drifted.write_bytes(b"drift\n")
    with pytest.raises(RuntimeError, match="generated artifact drift"):
        generator.check_generated(repository)

    drifted.write_bytes(outputs[generator.CODEOWNERS_PATH])
    drifted.chmod(0o664)
    with pytest.raises(RuntimeError, match="group/world writable"):
        generator.check_generated(repository)
