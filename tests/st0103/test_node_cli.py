"""Adversarial Node/npm CLI checks for deterministic ST-0103 evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

import pytest

from conftest import (
    EXPECTED_NODE_VERSION,
    EXPECTED_NPM_VERSION,
    REPOSITORY_ROOT,
    clean_environment,
    copy_node_project,
    run_wrapper,
)


def drift_manifest(project: Path) -> None:
    """Change one direct pin without changing the committed lock."""

    manifest_path = project / "package.json"
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    dependencies = manifest.setdefault("devDependencies", {})
    assert isinstance(dependencies, dict)
    assert dependencies["prettier"] == "3.9.6"
    dependencies["prettier"] = "3.9.5"
    manifest_path.write_text(
        f"{json.dumps(manifest, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )


def minimal_manifest(*, lifecycle_marker: Path | None = None) -> dict[str, Any]:
    """Return a dependency-free manifest accepted by the exact runtime gate."""

    scripts: dict[str, str] = {}
    if lifecycle_marker is not None:
        marker = json.dumps(str(lifecycle_marker))
        scripts["preinstall"] = (
            'node -e \'require("node:fs").writeFileSync(' + marker + ', "ran")\''
        )
    return {
        "name": "raos-node-toolchain-fixture",
        "version": "0.0.0",
        "private": True,
        "packageManager": f"npm@{EXPECTED_NPM_VERSION}",
        "engines": {
            "node": EXPECTED_NODE_VERSION,
            "npm": EXPECTED_NPM_VERSION,
        },
        "devEngines": {
            "runtime": {
                "name": "node",
                "version": EXPECTED_NODE_VERSION,
                "onFail": "error",
            },
            "packageManager": {
                "name": "npm",
                "version": EXPECTED_NPM_VERSION,
                "onFail": "error",
            },
        },
        "scripts": scripts,
    }


def prepare_minimal_project(
    project: Path,
    *,
    lifecycle_marker: Path | None = None,
) -> None:
    """Create a no-dependency fixture using the repository's real entrypoints."""

    project.mkdir(parents=True)
    for relative in (".node-version", ".npmrc", "Makefile"):
        shutil.copy2(REPOSITORY_ROOT / relative, project / relative)
    scripts = project / "scripts"
    scripts.mkdir()
    shutil.copy2(
        REPOSITORY_ROOT / "scripts/node_toolchain.sh",
        scripts / "node_toolchain.sh",
    )
    shutil.copy2(
        REPOSITORY_ROOT / "scripts/node_inventory.mjs",
        scripts / "node_inventory.mjs",
    )
    (project / "package.json").write_text(
        f"{json.dumps(minimal_manifest(lifecycle_marker=lifecycle_marker), indent=2)}\n",
        encoding="utf-8",
    )
    for relative, name in (
        ("apps/web/package.json", "@raos/web"),
        ("packages/web-contracts/package.json", "@raos/web-contracts"),
        ("packages/web-ui/package.json", "@raos/web-ui"),
    ):
        manifest = project / relative
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            f"{json.dumps({'name': name, 'version': '0.0.0', 'private': True}, indent=2)}\n",
            encoding="utf-8",
        )
    (project / "packages/web-contracts/tsconfig.json").write_text(
        "{}\n", encoding="utf-8"
    )


def diagnostics(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout}\n{result.stderr}"


def test_wrapper_reports_the_exact_node_and_npm_versions(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, npm_cli = exact_node_toolchain
    result = run_wrapper(
        node,
        npm_cli,
        "versions",
        environment=clean_environment(tmp_path / "cache"),
    )
    assert result.returncode == 0, diagnostics(result)
    assert re.search(rf"(?m)^v?{re.escape(EXPECTED_NODE_VERSION)}$", result.stdout)
    assert re.search(rf"(?m)^{re.escape(EXPECTED_NPM_VERSION)}$", result.stdout)


def test_wrapper_rejects_the_wrong_node_before_running_npm(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    _, npm_cli = exact_node_toolchain
    wrong_node = Path("/usr/bin/node")
    if not wrong_node.is_file():
        pytest.skip("the host has no second Node runtime for the negative probe")
    running = subprocess.run(
        [str(wrong_node), "--version"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    ).stdout.strip()
    if running == f"v{EXPECTED_NODE_VERSION}":
        pytest.skip("the host /usr/bin/node unexpectedly matches the exact pin")

    result = run_wrapper(
        wrong_node,
        npm_cli,
        "versions",
        environment=clean_environment(tmp_path / "cache"),
    )
    assert result.returncode != 0
    assert f"required Node version =={EXPECTED_NODE_VERSION}" in result.stderr
    assert running.removeprefix("v") in result.stderr


def test_wrapper_rejects_the_wrong_npm_cli(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, _ = exact_node_toolchain
    wrong_npm = tmp_path / "wrong-npm-cli.js"
    wrong_npm.write_text("console.log('0.0.0');\n", encoding="utf-8")
    result = run_wrapper(
        node,
        wrong_npm,
        "versions",
        environment=clean_environment(tmp_path / "cache"),
    )
    assert result.returncode != 0
    diagnostic = result.stderr.lower()
    assert "npm" in diagnostic
    assert any(word in diagnostic for word in ("bundled", "installation", "version"))


def test_wrapper_rejects_an_unbundled_exact_version_npm_lookalike(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, _ = exact_node_toolchain
    lookalike = tmp_path / "npm-cli.js"
    lookalike.write_text(
        f"console.log('{EXPECTED_NPM_VERSION}');\n",
        encoding="utf-8",
    )
    result = run_wrapper(
        node,
        lookalike,
        "versions",
        environment=clean_environment(tmp_path / "cache"),
    )
    assert result.returncode != 0
    assert "bundled" in result.stderr.lower() or "installation" in result.stderr.lower()


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--node", "relative/node", "--npm-cli", "/tmp/npm-cli.js", "versions"],
        ["--node", "/bin/false", "--npm-cli", "/tmp/npm-cli.js", "unknown"],
        [
            "--node",
            "/bin/false",
            "--npm-cli",
            "/tmp/npm-cli.js",
            "versions",
            "extra",
        ],
    ],
)
def test_wrapper_rejects_invalid_or_extended_cli(arguments: list[str]) -> None:
    result = subprocess.run(
        [str(REPOSITORY_ROOT / "scripts/node_toolchain.sh"), *arguments],
        cwd=REPOSITORY_ROOT,
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode != 0
    assert "usage:" in result.stderr.lower() or "error:" in result.stderr.lower()


def test_wrapper_ignores_bash_startup_injection(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, npm_cli = exact_node_toolchain
    marker = tmp_path / "bash-env-ran"
    startup = tmp_path / "bash-env"
    startup.write_text(f"touch {marker}\nexit 0\n", encoding="utf-8")
    environment = clean_environment(tmp_path / "cache")
    environment["BASH_ENV"] = str(startup)
    result = run_wrapper(node, npm_cli, "versions", environment=environment)
    assert result.returncode == 0, diagnostics(result)
    assert not marker.exists()


def test_wrapper_removes_node_options_code_injection(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, npm_cli = exact_node_toolchain
    marker = tmp_path / "node-options-ran"
    injection = tmp_path / "injection.cjs"
    injection.write_text(
        "require('node:fs').writeFileSync(" + json.dumps(str(marker)) + ", 'ran');\n",
        encoding="utf-8",
    )
    environment = clean_environment(tmp_path / "cache")
    environment["NODE_OPTIONS"] = f"--require={injection}"
    environment["NODE_PATH"] = str(tmp_path / "untrusted-modules")
    result = run_wrapper(node, npm_cli, "versions", environment=environment)
    assert result.returncode == 0, diagnostics(result)
    assert not marker.exists()


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("MAKEFLAGS", "--eval=.IGNORE:"),
        ("GNUMAKEFLAGS", "--eval=.IGNORE:"),
        ("npm_config_package_lock", "false"),
        ("NPM_CONFIG_PACKAGE_LOCK", "false"),
        ("npm_config_ignore_scripts", "false"),
        ("NPM_CONFIG_IGNORE_SCRIPTS", "false"),
    ],
)
def test_wrapper_cannot_be_poisoned_into_accepting_a_stale_lock(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    variable: str,
    value: str,
) -> None:
    node, npm_cli = exact_node_toolchain
    project = tmp_path / "drifted-project"
    copy_node_project(project)
    drift_manifest(project)
    environment = clean_environment(tmp_path / "cache")
    environment[variable] = value
    result = run_wrapper(
        node,
        npm_cli,
        "lock-check",
        cwd=project,
        environment=environment,
    )
    assert result.returncode != 0, diagnostics(result)
    assert (
        "package-lock" in diagnostics(result).lower()
        or "npm ci" in diagnostics(result).lower()
    )


def test_wrapper_removes_preloaded_makefile_false_pass(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, npm_cli = exact_node_toolchain
    project = tmp_path / "preloaded-drifted-project"
    copy_node_project(project)
    drift_manifest(project)
    preload = tmp_path / "ignore.mk"
    preload.write_text(".IGNORE:\n", encoding="utf-8")
    environment = clean_environment(tmp_path / "cache")
    environment["MAKEFILES"] = str(preload)
    result = run_wrapper(
        node,
        npm_cli,
        "lock-check",
        cwd=project,
        environment=environment,
    )
    assert result.returncode != 0, diagnostics(result)


@pytest.mark.parametrize("command", ["lock-check", "sync"])
def test_npm_ci_rejects_a_deliberately_stale_lock(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    command: str,
) -> None:
    node, npm_cli = exact_node_toolchain
    project = tmp_path / f"stale-{command}"
    copy_node_project(project)
    drift_manifest(project)
    result = run_wrapper(
        node,
        npm_cli,
        command,
        cwd=project,
        environment=clean_environment(tmp_path / "cache"),
    )
    assert result.returncode != 0, diagnostics(result)
    diagnostic = diagnostics(result).lower()
    assert "package-lock" in diagnostic or "npm ci" in diagnostic


def test_wrapper_commands_support_repository_paths_with_spaces(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, npm_cli = exact_node_toolchain
    project = tmp_path / "repository path with spaces"
    prepare_minimal_project(project)
    environment = clean_environment(tmp_path / "cache")
    generated = run_wrapper(
        node,
        npm_cli,
        "lock",
        cwd=project,
        environment=environment,
    )
    assert generated.returncode == 0, diagnostics(generated)
    checked = run_wrapper(
        node,
        npm_cli,
        "lock-check",
        cwd=project,
        environment=environment,
    )
    assert checked.returncode == 0, diagnostics(checked)


def test_wrapper_canonicalizes_hostile_tool_parent_alias_before_make(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, npm_cli = exact_node_toolchain
    project = tmp_path / "canonical-tool-alias-project"
    prepare_minimal_project(project)
    environment = clean_environment(tmp_path / "cache")
    generated = run_wrapper(
        node,
        npm_cli,
        "lock",
        cwd=project,
        environment=environment,
    )
    assert generated.returncode == 0, diagnostics(generated)

    marker_make = project / "RAOS_MAKE_ALIAS_MARKER"
    marker_shell = project / "RAOS_SHELL_ALIAS_MARKER"
    alias = tmp_path / (
        "tool-$(error PWNED)-$(shell touch RAOS_MAKE_ALIAS_MARKER)-"
        "`touch RAOS_SHELL_ALIAS_MARKER`"
    )
    prefix = node.resolve(strict=True).parent.parent
    try:
        alias.symlink_to(prefix, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")

    alias_node = alias / "bin/node"
    alias_npm = alias / "lib/node_modules/npm/bin/npm-cli.js"
    checked = run_wrapper(
        alias_node,
        alias_npm,
        "lock-check",
        cwd=project,
        environment=environment,
    )
    assert checked.returncode == 0, diagnostics(checked)
    assert "PWNED" not in diagnostics(checked)
    assert not marker_make.exists()
    assert not marker_shell.exists()


def test_wrapper_ignores_hostile_helpers_on_ambient_path(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, npm_cli = exact_node_toolchain
    project = tmp_path / "hostile-path-project"
    prepare_minimal_project(project)
    environment = clean_environment(tmp_path / "cache")
    generated = run_wrapper(
        node,
        npm_cli,
        "lock",
        cwd=project,
        environment=environment,
    )
    assert generated.returncode == 0, diagnostics(generated)

    fake_bin = tmp_path / "hostile-bin"
    fake_bin.mkdir()
    markers: list[Path] = []
    for helper in ("dirname", "realpath", "env", "make"):
        marker = tmp_path / f"ambient-{helper}-executed"
        markers.append(marker)
        executable = fake_bin / helper
        executable.write_text(
            f'#!/bin/sh\n/usr/bin/touch "{marker}"\nexit 97\n',
            encoding="utf-8",
        )
        executable.chmod(0o755)

    hostile_environment = dict(environment)
    hostile_environment["PATH"] = f"{fake_bin}:{os.defpath}"
    checked = run_wrapper(
        node,
        npm_cli,
        "lock-check",
        cwd=project,
        environment=hostile_environment,
    )
    assert checked.returncode == 0, diagnostics(checked)
    assert not any(marker.exists() for marker in markers)


def test_lock_and_sync_never_execute_package_lifecycle_scripts(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, npm_cli = exact_node_toolchain
    project = tmp_path / "malicious-lifecycle-project"
    marker = tmp_path / "lifecycle-ran"
    prepare_minimal_project(project, lifecycle_marker=marker)
    environment = clean_environment(tmp_path / "cache")
    hostile_user_config = tmp_path / "hostile.npmrc"
    hostile_user_config.write_text("ignore-scripts=false\n", encoding="utf-8")
    environment.update(
        {
            "NPM_CONFIG_USERCONFIG": str(hostile_user_config),
            "NPM_CONFIG_IGNORE_SCRIPTS": "false",
            "npm_config_ignore_scripts": "false",
        }
    )

    locked = run_wrapper(
        node,
        npm_cli,
        "lock",
        cwd=project,
        environment=environment,
    )
    assert locked.returncode == 0, diagnostics(locked)
    assert not marker.exists()

    synced = run_wrapper(
        node,
        npm_cli,
        "sync",
        cwd=project,
        environment=environment,
    )
    assert synced.returncode == 0, diagnostics(synced)
    assert not marker.exists()


def test_offline_sync_recreates_the_exact_installed_inventory(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, npm_cli = exact_node_toolchain
    if (
        not (REPOSITORY_ROOT / ".npm-cache").is_dir()
        or not (REPOSITORY_ROOT / "node_modules").is_dir()
    ):
        pytest.skip("the exact online install and npm cache are not hydrated yet")
    result = run_wrapper(
        node,
        npm_cli,
        "sync-offline",
        environment=clean_environment(tmp_path / "cache"),
        timeout=240,
    )
    assert result.returncode == 0, diagnostics(result)
    assert not list(REPOSITORY_ROOT.glob(".node-offline-check.*"))


def replace_directory_with_external_symlink(
    project: Path,
    relative: str,
    external_root: Path,
) -> tuple[Path, Path]:
    """Replace one copied owned directory with an external symlink fixture."""

    source = project / relative
    target = external_root / relative.replace("/", "-")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    shutil.rmtree(source)
    try:
        source.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")

    workspace = target
    if relative == "apps":
        workspace = target / "web"
    elif relative == "packages":
        workspace = target / "web-ui"
    external_modules = workspace / "node_modules"
    external_modules.mkdir()
    marker = external_modules / "must-not-be-touched"
    marker.write_bytes(b"external workspace sentinel\n")
    return target, marker


@pytest.mark.parametrize(
    "relative",
    [
        "apps",
        "apps/web",
        "packages",
        "packages/web-contracts",
        "packages/web-ui",
    ],
)
@pytest.mark.parametrize("command", ["lock", "lock-check", "sync"])
def test_owned_directory_symlinks_fail_before_external_workspace_access(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    relative: str,
    command: str,
) -> None:
    node, npm_cli = exact_node_toolchain
    project = tmp_path / "symlinked-directory-project"
    copy_node_project(project)
    target, marker = replace_directory_with_external_symlink(
        project,
        relative,
        tmp_path / "external-directories",
    )
    before = marker.read_bytes()

    result = run_wrapper(
        node,
        npm_cli,
        command,
        cwd=project,
        environment=clean_environment(tmp_path / "cache"),
    )
    assert result.returncode != 0, diagnostics(result)
    diagnostic = diagnostics(result).lower()
    assert "symbolic" in diagnostic or "symlink" in diagnostic
    assert target.is_dir()
    assert marker.read_bytes() == before
    assert not (project / "node_modules").exists()
    assert not (project / ".npm-cache").exists()


FIXED_NODE_FILES = (
    ".npmrc",
    "package.json",
    "package-lock.json",
    "apps/web/package.json",
    "packages/web-contracts/package.json",
    "packages/web-contracts/tsconfig.json",
    "packages/web-ui/package.json",
)


@pytest.mark.parametrize("relative", FIXED_NODE_FILES)
@pytest.mark.parametrize("command", ["lock", "lock-check", "sync"])
def test_fixed_input_symlinks_fail_without_mutating_the_external_target(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    relative: str,
    command: str,
) -> None:
    node, npm_cli = exact_node_toolchain
    project = tmp_path / "symlinked-input-project"
    copy_node_project(project)
    source = project / relative
    target = tmp_path / "external-files" / relative.replace("/", "-")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    before = target.read_bytes()
    source.unlink()
    try:
        source.symlink_to(target)
    except OSError as error:
        pytest.skip(f"file symlinks are unavailable: {error}")

    result = run_wrapper(
        node,
        npm_cli,
        command,
        cwd=project,
        environment=clean_environment(tmp_path / "cache"),
    )
    assert result.returncode != 0, diagnostics(result)
    diagnostic = diagnostics(result).lower()
    assert "symbolic" in diagnostic or "symlink" in diagnostic
    assert target.read_bytes() == before
    assert not (project / "node_modules").exists()
    assert not (project / ".npm-cache").exists()


@pytest.mark.parametrize("relative", FIXED_NODE_FILES)
def test_fixed_inputs_must_be_regular_files(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    relative: str,
) -> None:
    node, npm_cli = exact_node_toolchain
    project = tmp_path / "nonregular-input-project"
    copy_node_project(project)
    source = project / relative
    source.unlink()
    source.mkdir()

    result = run_wrapper(
        node,
        npm_cli,
        "lock-check",
        cwd=project,
        environment=clean_environment(tmp_path / "cache"),
    )
    assert result.returncode != 0, diagnostics(result)
    diagnostic = diagnostics(result).lower()
    assert "regular file" in diagnostic or "not a file" in diagnostic
    assert not (project / "node_modules").exists()
    assert not (project / ".npm-cache").exists()


@pytest.mark.parametrize("command", ["lock-check", "sync"])
def test_existing_lock_is_mandatory_for_non_lock_commands(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    command: str,
) -> None:
    node, npm_cli = exact_node_toolchain
    project = tmp_path / "missing-lock-project"
    copy_node_project(project)
    lock = project / "package-lock.json"
    lock.unlink()

    result = run_wrapper(
        node,
        npm_cli,
        command,
        cwd=project,
        environment=clean_environment(tmp_path / "cache"),
    )
    assert result.returncode != 0, diagnostics(result)
    assert not lock.exists()
    assert not (project / "node_modules").exists()
    assert not (project / ".npm-cache").exists()
