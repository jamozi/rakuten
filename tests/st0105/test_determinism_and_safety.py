"""Determinism, no-write drift, and rollback checks for ST-0105."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

import pytest

from .support import REPOSITORY_ROOT
from scripts import build_st0105_generated_contracts as generator


TRACKED_ROOTS = (
    REPOSITORY_ROOT / "python/raos/generated",
    REPOSITORY_ROOT / "packages/web-contracts/src/generated",
)


def installed_state() -> dict[str, tuple[int, int, str]]:
    paths = [REPOSITORY_ROOT / "changes/st-0105/manifest.json"]
    for root in TRACKED_ROOTS:
        paths.extend(path for path in root.rglob("*") if path.is_file())
    return {
        path.relative_to(REPOSITORY_ROOT).as_posix(): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(paths)
    }


def run_generator(
    command: list[str], *, check: bool
) -> subprocess.CompletedProcess[str]:
    invoked = [*command[:2], *(["--check"] if check else []), *command[2:]]
    return subprocess.run(
        invoked,
        cwd=REPOSITORY_ROOT,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(REPOSITORY_ROOT / "python"),
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=240,
    )


def test_two_fresh_generations_are_identical_and_check_is_no_write(
    generator_command: list[str],
) -> None:
    before = installed_state()
    first = run_generator(generator_command, check=True)
    middle = installed_state()
    second = run_generator(generator_command, check=True)
    after = installed_state()
    assert first.returncode == 0, f"{first.stdout}\n{first.stderr}"
    assert second.returncode == 0, f"{second.stdout}\n{second.stderr}"
    assert first.stdout == second.stdout
    report = json.loads(first.stdout)
    assert report == {
        "asyncapi_messages": 105,
        "http_operations": 185,
        "mode": "check",
        "python_files": 302,
        "schemas": 224,
        "status": "PASS",
        "story_id": "ST-0105",
        "typescript_files": 52,
    }
    assert before == middle == after


def test_node_default_honors_pinned_node_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pinned_node = Path("/opt/raos/toolchain/node")
    monkeypatch.setenv("NODE", str(pinned_node))
    monkeypatch.setattr(generator.shutil, "which", lambda _name: "/usr/bin/node")

    assert generator.parse_args([]).node == pinned_node


def test_generator_failure_before_render_preserves_installed_outputs(
    generator_command: list[str],
) -> None:
    before = installed_state()
    command = generator_command.copy()
    failing_node = Path("/usr/bin/false").resolve(strict=True)
    command[command.index("--node") + 1] = str(failing_node)
    result = run_generator(command, check=False)
    assert result.returncode != 0
    assert "generator command failed" in result.stderr
    assert f"{failing_node} --version" in result.stderr
    assert installed_state() == before


@pytest.mark.parametrize(
    "value",
    ["", "/absolute", "../escape", "a/../b", "a\\b", "./a", "a//b"],
)
def test_untrusted_relative_paths_are_rejected(value: str) -> None:
    with pytest.raises(RuntimeError, match="unsafe relative path"):
        generator._checked_relative_path(value, source="test")


def test_full_path_and_index_derive_stable_collision_free_type_names() -> None:
    left = generator._type_name(1, "contracts/a-b/v1.schema.json")
    right = generator._type_name(2, "contracts/a/b-v1.schema.json")
    assert left == "Schema001ContractsABV1SchemaJson"
    assert right == "Schema002ContractsABV1SchemaJson"
    assert left != right


def test_running_python_version_drift_is_rejected_before_tool_execution(
    monkeypatch: pytest.MonkeyPatch, generator_command: list[str]
) -> None:
    monkeypatch.setattr(generator, "EXPECTED_PYTHON_VERSION", "0.0.0")
    datamodel_codegen = Path(
        generator_command[generator_command.index("--datamodel-codegen") + 1]
    )
    node = Path(generator_command[generator_command.index("--node") + 1])
    openapi_ts = Path(generator_command[generator_command.index("--openapi-ts") + 1])
    with pytest.raises(RuntimeError, match="required CPython 0.0.0"):
        generator._verify_tools(datamodel_codegen, node, openapi_ts)


def test_tool_verification_rejects_node_modules_ancestor_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    node_executable: Path,
) -> None:
    repository = tmp_path / "repository"
    external = tmp_path / "external-node-modules"
    (repository / ".venv/bin").mkdir(parents=True)
    datamodel_codegen = repository / ".venv/bin/datamodel-codegen"
    datamodel_codegen.write_bytes(b"#!/bin/sh\nexit 0\n")
    datamodel_codegen.chmod(0o755)
    (external / "@hey-api/openapi-ts/bin").mkdir(parents=True)
    (external / "@hey-api/openapi-ts/bin/run.js").write_bytes(b"safe\n")
    (repository / "node_modules").symlink_to(external, target_is_directory=True)
    monkeypatch.setattr(generator, "REPO_ROOT", repository)

    with pytest.raises(RuntimeError, match="physical directory ancestor"):
        generator._verify_tools(
            datamodel_codegen,
            node_executable,
            repository / "node_modules/@hey-api/openapi-ts/bin/run.js",
        )


def test_package_provenance_rejects_version_drift_and_manifest_symlinks(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "package.json"
    manifest.write_text(
        json.dumps({"name": "typescript", "version": "0.0.0"}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="identity/version mismatch"):
        generator._package_version(
            manifest,
            expected_name="typescript",
            expected_version="6.0.3",
            kind="TypeScript package manifest",
        )
    target = tmp_path / "target.json"
    target.write_text(
        json.dumps({"name": "typescript", "version": "6.0.3"}),
        encoding="utf-8",
    )
    manifest.unlink()
    manifest.symlink_to(target)
    with pytest.raises(RuntimeError, match="regular non-symlink"):
        generator._package_version(
            manifest,
            expected_name="typescript",
            expected_version="6.0.3",
            kind="TypeScript package manifest",
        )


def test_generated_tree_reader_rejects_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "generated"
    root.mkdir()
    target = tmp_path / "outside.py"
    target.write_text("safe = True\n", encoding="utf-8")
    try:
        (root / "escape.py").symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlinks are unavailable: {error}")
    with pytest.raises(RuntimeError, match="symlink in generated output"):
        generator._tree_files(root)


def test_manifest_parser_rejects_unsorted_artifacts(
    codegen_manifest: dict[str, Any],
) -> None:
    mutated = json.loads(json.dumps(codegen_manifest))
    mutated["outputs"]["artifacts"].reverse()
    with pytest.raises(RuntimeError, match="not path-sorted"):
        generator._expected_manifest_artifacts(generator._json_bytes(mutated))


def minimal_manifest(python_root: Path, typescript_root: Path) -> bytes:
    artifacts: list[dict[str, object]] = []
    for root, prefix in (
        (python_root, "python/raos/generated"),
        (typescript_root, "packages/web-contracts/src/generated"),
    ):
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            content = path.read_bytes()
            artifacts.append(
                {
                    "path": f"{prefix}/{path.relative_to(root).as_posix()}",
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
    artifacts.sort(key=lambda row: str(row["path"]))
    return generator._json_bytes(
        {
            "outputs": {
                "artifact_count": len(artifacts),
                "artifacts": artifacts,
                "boundary": "EXACT",
                "roots": [
                    "python/raos/generated",
                    "packages/web-contracts/src/generated",
                ],
            }
        }
    )


def test_install_failure_after_exchange_restores_both_trees_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed_python = tmp_path / "python/generated"
    installed_typescript = tmp_path / "typescript/generated"
    rendered_python = tmp_path / "rendered/python"
    rendered_typescript = tmp_path / "rendered/typescript"
    for root, name, content in (
        (installed_python, "old.py", b"old-python\n"),
        (installed_typescript, "old.ts", b"old-typescript\n"),
        (rendered_python, "new.py", b"new-python\n"),
        (rendered_typescript, "new.ts", b"new-typescript\n"),
    ):
        root.mkdir(parents=True)
        (root / name).write_bytes(content)
    manifest_path = tmp_path / "changes/manifest.json"
    manifest_path.parent.mkdir()
    previous_manifest = minimal_manifest(installed_python, installed_typescript)
    manifest_path.write_bytes(previous_manifest)
    next_manifest = minimal_manifest(rendered_python, rendered_typescript)

    monkeypatch.setattr(generator, "PYTHON_OUTPUT_ROOT", installed_python)
    monkeypatch.setattr(generator, "TYPESCRIPT_OUTPUT_ROOT", installed_typescript)
    monkeypatch.setattr(generator, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(generator, "REPO_ROOT", tmp_path)

    def fail_after_manifest(checkpoint: str) -> None:
        if checkpoint == "after-manifest-namespace":
            raise RuntimeError("injected post-install verification failure")

    monkeypatch.setattr(generator, "_checkpoint", fail_after_manifest)
    with pytest.raises(RuntimeError, match="injected post-install"):
        generator._install(rendered_python, rendered_typescript, next_manifest)

    assert generator._tree_files(installed_python) == {"old.py": b"old-python\n"}
    assert generator._tree_files(installed_typescript) == {
        "old.ts": b"old-typescript\n"
    }
    assert manifest_path.read_bytes() == previous_manifest
    assert not (manifest_path.parent / generator.TRANSACTION_DIRECTORY_NAME).exists()


def test_second_stage_failure_cleans_the_first_stage_and_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed_python, installed_typescript, rendered_python, rendered_typescript = (
        make_install_fixture(tmp_path)
    )
    manifest_path = tmp_path / "changes/st-0105/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    previous_manifest = minimal_manifest(installed_python, installed_typescript)
    next_manifest = minimal_manifest(rendered_python, rendered_typescript)
    manifest_path.write_bytes(previous_manifest)
    patch_install_layout(
        monkeypatch,
        tmp_path,
        installed_python,
        installed_typescript,
        manifest_path,
    )
    real_write_tree = generator._write_tree_at
    calls = 0

    def fail_second_stage(parent_fd: int, name: str, files: dict[str, bytes]) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected TypeScript stage failure")
        real_write_tree(parent_fd, name, files)

    monkeypatch.setattr(generator, "_write_tree_at", fail_second_stage)
    with pytest.raises(RuntimeError, match="TypeScript stage failure"):
        generator._install(rendered_python, rendered_typescript, next_manifest)

    assert generator._tree_files(installed_python) == {"old.py": b"old-python\n"}
    assert generator._tree_files(installed_typescript) == {
        "old.ts": b"old-typescript\n"
    }
    assert manifest_path.read_bytes() == previous_manifest
    assert not list(installed_python.parent.glob("*.st0105.*"))
    assert not list(installed_typescript.parent.glob("*.st0105.*"))
    assert not (manifest_path.parent / generator.TRANSACTION_DIRECTORY_NAME).exists()


def test_manifest_recovery_failure_does_not_skip_tree_rollback_or_delete_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed_python, installed_typescript, rendered_python, rendered_typescript = (
        make_install_fixture(tmp_path)
    )
    manifest_path = tmp_path / "changes/st-0105/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    previous_manifest = minimal_manifest(installed_python, installed_typescript)
    next_manifest = minimal_manifest(rendered_python, rendered_typescript)
    manifest_path.write_bytes(previous_manifest)
    patch_install_layout(
        monkeypatch,
        tmp_path,
        installed_python,
        installed_typescript,
        manifest_path,
    )
    real_restore_manifest = generator._restore_manifest_locked

    def fail_after_manifest_publish(checkpoint: str) -> None:
        if checkpoint == "after-manifest-namespace":
            raise RuntimeError("injected install failure")

    def fail_manifest_restore(*_args: object) -> None:
        raise RuntimeError("injected manifest recovery failure")

    monkeypatch.setattr(generator, "_checkpoint", fail_after_manifest_publish)
    monkeypatch.setattr(generator, "_restore_manifest_locked", fail_manifest_restore)
    with pytest.raises(generator.InstallRecoveryRequired, match="recovery remains"):
        generator._install(rendered_python, rendered_typescript, next_manifest)

    assert generator._tree_files(installed_python) == {"old.py": b"old-python\n"}
    assert generator._tree_files(installed_typescript) == {
        "old.ts": b"old-typescript\n"
    }
    assert manifest_path.read_bytes() == next_manifest
    journal = manifest_path.parent / generator.TRANSACTION_DIRECTORY_NAME
    assert journal.is_dir()
    assert list(installed_python.parent.glob("*.st0105.*"))
    assert list(installed_typescript.parent.glob("*.st0105.*"))

    def stop_after_automatic_recovery(checkpoint: str) -> None:
        if checkpoint == "after-startup-recovery":
            raise RuntimeError("stop after automatic recovery")

    monkeypatch.setattr(generator, "_checkpoint", stop_after_automatic_recovery)
    monkeypatch.setattr(generator, "_restore_manifest_locked", real_restore_manifest)
    with pytest.raises(RuntimeError, match="stop after automatic recovery"):
        generator._install(rendered_python, rendered_typescript, next_manifest)
    assert manifest_path.read_bytes() == previous_manifest
    assert not journal.exists()
    assert not list(installed_python.parent.glob("*.st0105.*"))
    assert not list(installed_typescript.parent.glob("*.st0105.*"))


def test_ancestor_symlink_cannot_redirect_staging_outside_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logical = tmp_path / "logical"
    external = tmp_path / "external"
    logical.mkdir()
    external.mkdir()
    (external / "sentinel").write_bytes(b"unchanged\n")
    (logical / "packages").symlink_to(external, target_is_directory=True)
    (logical / "python/raos/generated").mkdir(parents=True)
    (logical / "python/raos/generated/old.py").write_bytes(b"old-python\n")
    (logical / "changes/st-0105").mkdir(parents=True)
    rendered_python = logical / "rendered/python"
    rendered_typescript = logical / "rendered/typescript"
    rendered_python.mkdir(parents=True)
    rendered_typescript.mkdir(parents=True)
    (rendered_python / "new.py").write_bytes(b"new-python\n")
    (rendered_typescript / "new.ts").write_bytes(b"new-typescript\n")
    next_manifest = minimal_manifest(rendered_python, rendered_typescript)

    monkeypatch.setattr(generator, "REPO_ROOT", logical)
    monkeypatch.setattr(
        generator, "PYTHON_OUTPUT_ROOT", logical / "python/raos/generated"
    )
    monkeypatch.setattr(
        generator,
        "TYPESCRIPT_OUTPUT_ROOT",
        logical / "packages/web-contracts/src/generated",
    )
    monkeypatch.setattr(
        generator, "MANIFEST_PATH", logical / "changes/st-0105/manifest.json"
    )
    with pytest.raises(RuntimeError, match="unsafe or missing managed directory"):
        generator._install(rendered_python, rendered_typescript, next_manifest)
    assert (external / "sentinel").read_bytes() == b"unchanged\n"
    assert sorted(path.name for path in external.iterdir()) == ["sentinel"]


def test_read_only_operation_rejects_partial_cleanup_tombstone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed_python, installed_typescript, _, _ = make_fresh_install_fixture(tmp_path)
    manifest_path = tmp_path / "changes/st-0105/manifest.json"
    patch_install_layout(
        monkeypatch,
        tmp_path,
        installed_python,
        installed_typescript,
        manifest_path,
    )
    cleanup = manifest_path.parent / generator.TRANSACTION_CLEANUP_NAME
    cleanup.mkdir()
    (cleanup / generator.TRANSACTION_STATE_NAME).write_bytes(b"partial")

    with generator._open_install_layout(exclusive=False, create=False) as layout:
        with pytest.raises(
            generator.InstallRecoveryRequired,
            match=r"\.install-transaction\.v1\.cleanup",
        ):
            generator._assert_no_pending_transaction_locked(layout)


@pytest.mark.parametrize(
    ("checkpoint", "expected"),
    [
        ("after-python-namespace", "old"),
        ("after-typescript-namespace", "old"),
        ("after-manifest-namespace", "old"),
        ("after-committed-state", "new"),
        ("after-python-stage-cleanup", "new"),
        ("after-journal-tombstone-namespace", "new"),
        ("during-journal-tombstone-cleanup", "new"),
    ],
)
def test_sigkill_checkpoint_is_automatically_recovered_on_next_invocation(
    tmp_path: Path, checkpoint: str, expected: str
) -> None:
    installed_python, installed_typescript, rendered_python, rendered_typescript = (
        make_install_fixture(tmp_path)
    )
    manifest_path = tmp_path / "changes/st-0105/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    previous_manifest = minimal_manifest(installed_python, installed_typescript)
    next_manifest = minimal_manifest(rendered_python, rendered_typescript)
    manifest_path.write_bytes(previous_manifest)
    (tmp_path / "next-manifest.json").write_bytes(next_manifest)
    python, driver, environment = crash_driver_configuration()
    crashed = run_install_driver(
        python, driver, tmp_path, environment, checkpoint=checkpoint
    )
    assert crashed.returncode == 97, f"{crashed.stdout}\n{crashed.stderr}"
    recovered = run_install_driver(
        python,
        driver,
        tmp_path,
        environment,
        checkpoint="after-startup-recovery",
    )
    assert recovered.returncode == 97, f"{recovered.stdout}\n{recovered.stderr}"

    assert_install_state(
        expected,
        installed_python,
        installed_typescript,
        manifest_path,
        previous_manifest=previous_manifest,
        next_manifest=next_manifest,
    )
    assert_transaction_clean(installed_python, installed_typescript, manifest_path)

    completed = run_install_driver(python, driver, tmp_path, environment)
    assert completed.returncode == 0, f"{completed.stdout}\n{completed.stderr}"
    assert_install_state(
        "new",
        installed_python,
        installed_typescript,
        manifest_path,
        previous_manifest=previous_manifest,
        next_manifest=next_manifest,
    )
    assert_transaction_clean(installed_python, installed_typescript, manifest_path)


def test_recovery_can_resume_after_a_second_crash_during_rollback(
    tmp_path: Path,
) -> None:
    installed_python, installed_typescript, rendered_python, rendered_typescript = (
        make_install_fixture(tmp_path)
    )
    manifest_path = tmp_path / "changes/st-0105/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    previous_manifest = minimal_manifest(installed_python, installed_typescript)
    next_manifest = minimal_manifest(rendered_python, rendered_typescript)
    manifest_path.write_bytes(previous_manifest)
    (tmp_path / "next-manifest.json").write_bytes(next_manifest)
    python, driver, environment = crash_driver_configuration()

    initial_crash = run_install_driver(
        python,
        driver,
        tmp_path,
        environment,
        checkpoint="after-typescript-namespace",
    )
    assert initial_crash.returncode == 97, (
        f"{initial_crash.stdout}\n{initial_crash.stderr}"
    )
    recovery_crash = run_install_driver(
        python,
        driver,
        tmp_path,
        environment,
        checkpoint="after-recovery-python-namespace",
    )
    assert recovery_crash.returncode == 97, (
        f"{recovery_crash.stdout}\n{recovery_crash.stderr}"
    )
    recovered = run_install_driver(
        python,
        driver,
        tmp_path,
        environment,
        checkpoint="after-startup-recovery",
    )
    assert recovered.returncode == 97, f"{recovered.stdout}\n{recovered.stderr}"
    assert_install_state(
        "old",
        installed_python,
        installed_typescript,
        manifest_path,
        previous_manifest=previous_manifest,
        next_manifest=next_manifest,
    )
    assert_transaction_clean(installed_python, installed_typescript, manifest_path)

    completed = run_install_driver(python, driver, tmp_path, environment)
    assert completed.returncode == 0, f"{completed.stdout}\n{completed.stderr}"
    assert_install_state(
        "new",
        installed_python,
        installed_typescript,
        manifest_path,
        previous_manifest=previous_manifest,
        next_manifest=next_manifest,
    )
    assert_transaction_clean(installed_python, installed_typescript, manifest_path)


@pytest.mark.parametrize(
    ("checkpoint", "expected"),
    [
        ("after-python-namespace", "empty"),
        ("after-manifest-namespace", "empty"),
        ("after-committed-state", "new"),
        ("after-journal-tombstone-namespace", "new"),
        ("during-journal-tombstone-cleanup", "new"),
    ],
)
def test_fresh_install_crash_is_recovered_before_the_next_install(
    tmp_path: Path, checkpoint: str, expected: str
) -> None:
    installed_python, installed_typescript, rendered_python, rendered_typescript = (
        make_fresh_install_fixture(tmp_path)
    )
    manifest_path = tmp_path / "changes/st-0105/manifest.json"
    next_manifest = minimal_manifest(rendered_python, rendered_typescript)
    (tmp_path / "next-manifest.json").write_bytes(next_manifest)
    python, driver, environment = crash_driver_configuration()

    crashed = run_install_driver(
        python, driver, tmp_path, environment, checkpoint=checkpoint
    )
    assert crashed.returncode == 97, f"{crashed.stdout}\n{crashed.stderr}"
    recovered = run_install_driver(
        python,
        driver,
        tmp_path,
        environment,
        checkpoint="after-startup-recovery",
    )
    assert recovered.returncode == 97, f"{recovered.stdout}\n{recovered.stderr}"
    assert_install_state(
        expected,
        installed_python,
        installed_typescript,
        manifest_path,
        previous_manifest=None,
        next_manifest=next_manifest,
    )
    assert_transaction_clean(installed_python, installed_typescript, manifest_path)

    completed = run_install_driver(python, driver, tmp_path, environment)
    assert completed.returncode == 0, f"{completed.stdout}\n{completed.stderr}"
    assert_install_state(
        "new",
        installed_python,
        installed_typescript,
        manifest_path,
        previous_manifest=None,
        next_manifest=next_manifest,
    )
    assert_transaction_clean(installed_python, installed_typescript, manifest_path)


def make_install_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    installed_python = tmp_path / "python/raos/generated"
    installed_typescript = tmp_path / "packages/web-contracts/src/generated"
    rendered_python = tmp_path / "rendered/python"
    rendered_typescript = tmp_path / "rendered/typescript"
    for root, name, content in (
        (installed_python, "old.py", b"old-python\n"),
        (installed_typescript, "old.ts", b"old-typescript\n"),
        (rendered_python, "new.py", b"new-python\n"),
        (rendered_typescript, "new.ts", b"new-typescript\n"),
    ):
        root.mkdir(parents=True)
        (root / name).write_bytes(content)
    return installed_python, installed_typescript, rendered_python, rendered_typescript


def make_fresh_install_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    installed_python = tmp_path / "python/raos/generated"
    installed_typescript = tmp_path / "packages/web-contracts/src/generated"
    rendered_python = tmp_path / "rendered/python"
    rendered_typescript = tmp_path / "rendered/typescript"
    for parent in (
        installed_python.parent,
        installed_typescript.parent,
        tmp_path / "changes/st-0105",
    ):
        parent.mkdir(parents=True)
    for root, name, content in (
        (rendered_python, "new.py", b"new-python\n"),
        (rendered_typescript, "new.ts", b"new-typescript\n"),
    ):
        root.mkdir(parents=True)
        (root / name).write_bytes(content)
    return installed_python, installed_typescript, rendered_python, rendered_typescript


def crash_driver_configuration() -> tuple[Path, Path, dict[str, str]]:
    return (
        REPOSITORY_ROOT / ".venv/bin/python",
        REPOSITORY_ROOT / "tests/st0105/fixtures/install_crash_driver.py",
        {
            "PATH": os.defpath,
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )


def run_install_driver(
    python: Path,
    driver: Path,
    root: Path,
    environment: dict[str, str],
    *,
    checkpoint: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [str(python), str(driver), "--root", str(root)]
    if checkpoint is not None:
        command.extend(("--checkpoint", checkpoint))
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def assert_install_state(
    expected: str,
    installed_python: Path,
    installed_typescript: Path,
    manifest_path: Path,
    *,
    previous_manifest: bytes | None,
    next_manifest: bytes,
) -> None:
    if expected == "empty":
        assert not installed_python.exists()
        assert not installed_typescript.exists()
        assert not manifest_path.exists()
        return
    if expected == "old":
        assert previous_manifest is not None
        assert generator._tree_files(installed_python) == {"old.py": b"old-python\n"}
        assert generator._tree_files(installed_typescript) == {
            "old.ts": b"old-typescript\n"
        }
        assert manifest_path.read_bytes() == previous_manifest
        return
    if expected != "new":
        raise AssertionError(f"unknown expected install state: {expected}")
    assert generator._tree_files(installed_python) == {"new.py": b"new-python\n"}
    assert generator._tree_files(installed_typescript) == {
        "new.ts": b"new-typescript\n"
    }
    assert manifest_path.read_bytes() == next_manifest


def assert_transaction_clean(
    installed_python: Path,
    installed_typescript: Path,
    manifest_path: Path,
) -> None:
    for name in (
        generator.TRANSACTION_DIRECTORY_NAME,
        generator.TRANSACTION_PREPARING_NAME,
        generator.TRANSACTION_CLEANUP_NAME,
        generator.MANIFEST_TEMPORARY_NAME,
    ):
        assert not (manifest_path.parent / name).exists(), name
    for parent in (installed_python.parent, installed_typescript.parent):
        stages = [entry.name for entry in parent.iterdir() if ".st0105." in entry.name]
        assert not stages, stages


def patch_install_layout(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    installed_python: Path,
    installed_typescript: Path,
    manifest_path: Path,
) -> None:
    monkeypatch.setattr(generator, "REPO_ROOT", root)
    monkeypatch.setattr(generator, "PYTHON_OUTPUT_ROOT", installed_python)
    monkeypatch.setattr(generator, "TYPESCRIPT_OUTPUT_ROOT", installed_typescript)
    monkeypatch.setattr(generator, "MANIFEST_PATH", manifest_path)
