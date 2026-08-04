"""Determinism, composition, no-write, and atomic-install tests for local Compose."""

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
from scripts import build_local_compose as generator
from scripts import build_st0201_postgres_service as postgres_generator


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


def test_ordered_components_and_namespaces_are_explicit() -> None:
    assert [item.story_id for item in generator.ORDERED_COMPONENTS] == [
        "ST-0201",
        "ST-0202",
    ]
    model = generator.assemble_compose(REPOSITORY_ROOT)
    assert tuple(model) == generator.COMPOSE_NAMESPACES
    assert tuple(model["services"]) == ("postgres", "object-storage")
    assert tuple(model["secrets"]) == (
        "postgres_password",
        "object_storage_s3_config",
    )
    assert tuple(model["volumes"]) == ("postgres_data", "object_storage_data")
    assert tuple(model["networks"]) == (
        "postgres_internal",
        "object_storage_internal",
    )


def test_object_storage_secret_is_staged_for_the_unprivileged_entrypoint() -> None:
    service = generator.assemble_compose(REPOSITORY_ROOT)["services"]["object-storage"]
    assert service["entrypoint"] == ["/bin/sh", "-eu", "-c"]
    assert service["tmpfs"] == [
        "/run/raos:rw,noexec,nosuid,nodev,size=64k,mode=0700,uid=0,gid=0"
    ]
    assert service["secrets"] == [
        {
            "source": "object_storage_s3_config",
            "target": "/run/secrets/object_storage_s3_config",
            "mode": "0400",
        }
    ]
    assert service["command"] == [
        "umask 077; cp /run/secrets/object_storage_s3_config "
        "/run/raos/object-storage-s3-config.json; chown 1000:1000 "
        "/run/raos/object-storage-s3-config.json; chmod 0400 "
        "/run/raos/object-storage-s3-config.json; chown 1000:1000 /run/raos; "
        "chmod 0700 /run/raos; chmod 0700 /run/secrets; "
        'exec /entrypoint.sh "$$@"',
        "raos-object-storage",
        "mini",
        "-dir=/data",
        "-s3.config=/run/raos/object-storage-s3-config.json",
        "-s3.port=8333",
        "-master.telemetry=false",
        "-webdav=false",
        "-admin.ui=false",
        "-s3.port.iceberg=0",
        "-s3.allowDeleteBucketNotEmpty=false",
    ]


def test_wrapper_compose_digest_binding_fails_closed(tmp_path: Path) -> None:
    wrapper = tmp_path / postgres_generator.RUNTIME_WRAPPER_PATH
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text(
        "readonly expected_compose_sha256='" + "0" * 64 + "'\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Compose digest binding drifted"):
        postgres_generator.validate_wrapper_compose_binding(tmp_path, b"services: {}\n")


def test_committed_output_equals_one_deterministic_render() -> None:
    expected = generator.render_outputs(REPOSITORY_ROOT)
    for relative in generator.GENERATED_PATHS:
        path = REPOSITORY_ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert path.read_bytes() == expected[relative]
        assert stat.S_IMODE(path.stat().st_mode) & 0o022 == 0


def test_check_function_accepts_current_output_without_writing() -> None:
    before = _installed_state(REPOSITORY_ROOT)
    generator.check_generated(REPOSITORY_ROOT)
    assert _installed_state(REPOSITORY_ROOT) == before


@pytest.mark.parametrize(
    "script",
    ["build_local_compose.py", "build_st0201_postgres_service.py"],
)
def test_check_cli_is_no_write_and_legacy_cli_delegates(script: str) -> None:
    before = _installed_state(REPOSITORY_ROOT)
    result = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / script), "--check"],
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
        "component_story_ids": ["ST-0201", "ST-0202"],
        "generated_artifacts": 2,
        "mode": "check",
        "status": "PASS",
    }
    assert result.stderr == ""
    assert _installed_state(REPOSITORY_ROOT) == before


def test_st0201_manifest_remains_a_frozen_component_attestation() -> None:
    committed = REPOSITORY_ROOT / postgres_generator.MANIFEST_PATH
    assert postgres_generator.MANIFEST_PATH not in generator.GENERATED_PATHS
    assert _sha256(committed.read_bytes()) == (
        "fce4b7f18cec09425264a1058bda59759e081be0c04826ffa3eae433a68fcda3"
    )


def test_active_manifest_attests_cumulative_stack_and_frozen_predecessor() -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    manifest = yaml.safe_load(outputs[generator.MANIFEST_PATH])
    assert manifest["document"] == {
        "id": "RAOS-LOCAL-OBJECT-STORAGE-MANIFEST-001",
        "version": "1.0.0",
        "story_id": "ST-0202",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "generation_command": generator.GENERATION_COMMAND,
    }
    assert manifest["stack"] == {"stories": ["ST-0201", "ST-0202"]}
    assert manifest["provenance"]["predecessor_manifest"] == {
        "uri": "repo://changes/st-0201/manifest.yaml",
        "sha256": generator.EXPECTED_PREDECESSOR_MANIFEST_SHA256,
        "story_id": "ST-0201",
    }
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


def test_active_manifest_covers_the_maintained_integration_surfaces() -> None:
    manifest = yaml.safe_load(
        generator.render_outputs(REPOSITORY_ROOT)[generator.MANIFEST_PATH]
    )
    rows = manifest["source_artifacts"]
    assert manifest["source_artifact_count"] == len(generator.SOURCE_ARTIFACT_PATHS)
    assert [row["uri"] for row in rows] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    for relative, row in zip(generator.SOURCE_ARTIFACT_PATHS, rows, strict=True):
        content = (REPOSITORY_ROOT / relative).read_bytes()
        assert row == {
            "uri": f"repo://{relative.as_posix()}",
            "bytes": len(content),
            "sha256": _sha256(content),
        }


def test_active_manifest_boundary_is_the_exact_source_contract_boundary() -> None:
    manifest = yaml.safe_load(
        generator.render_outputs(REPOSITORY_ROOT)[generator.MANIFEST_PATH]
    )
    contract = generator.load_and_validate_object_contract(REPOSITORY_ROOT)
    assert manifest["boundary"] == contract["boundary"]


def test_install_creates_output_with_safe_mode_and_no_stage(tmp_path: Path) -> None:
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


def test_install_rejects_output_inventory_addition_or_removal(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outputs = _synthetic_outputs()
    outputs[Path("../escape")] = b"escape\n"
    with pytest.raises(RuntimeError, match="output inventory differs"):
        generator.install_outputs(outputs, repository)
    assert not (tmp_path / "escape").exists()
    with pytest.raises(RuntimeError, match="output inventory differs"):
        generator.install_outputs({}, repository)


def test_check_rejects_drift_and_group_writable_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outputs = _synthetic_outputs()
    _write_outputs(repository, outputs)
    monkeypatch.setattr(generator, "render_outputs", lambda root: outputs)
    monkeypatch.setattr(
        postgres_generator,
        "validate_wrapper_compose_binding",
        lambda root, content: None,
    )
    monkeypatch.setattr(
        generator,
        "_validate_object_wrapper_compose_binding",
        lambda root, content: None,
    )
    generator.check_generated(repository)
    compose = repository / generator.COMPOSE_PATH
    compose.write_bytes(b"drift\n")
    with pytest.raises(RuntimeError, match="generated artifact drift"):
        generator.check_generated(repository)
    compose.write_bytes(outputs[generator.COMPOSE_PATH])
    compose.chmod(0o664)
    with pytest.raises(RuntimeError, match="group/world writable"):
        generator.check_generated(repository)
