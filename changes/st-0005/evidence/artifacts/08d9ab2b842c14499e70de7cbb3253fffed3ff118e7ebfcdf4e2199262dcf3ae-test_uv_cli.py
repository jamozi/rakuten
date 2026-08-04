"""Offline uv CLI checks for lock freshness and version enforcement."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from conftest import (
    EXPECTED_UV_VERSION,
    REPOSITORY_ROOT,
    local_uv_binaries,
    uv_environment,
)


LOCK_INPUTS = (".python-version", "pyproject.toml", "uv.toml", "uv.lock")


def run_lock_check(
    binary: Path,
    project: Path,
    cache_directory: Path,
) -> subprocess.CompletedProcess[str]:
    """Run a bounded offline lock check with the selected local uv binary."""

    return subprocess.run(
        [str(binary), "lock", "--check"],
        cwd=project,
        env=uv_environment(cache_directory),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def copy_lock_inputs(destination: Path) -> None:
    destination.mkdir()
    for relative in LOCK_INPUTS:
        shutil.copy2(REPOSITORY_ROOT / relative, destination / relative)


def drift_project(project: Path) -> None:
    """Remove one locked direct pin without changing the committed lock."""

    pyproject = project / "pyproject.toml"
    original = pyproject.read_text(encoding="utf-8")
    drifted = original.replace('  "types-pyyaml==6.0.12.20260724",\n', "", 1)
    assert drifted != original
    pyproject.write_text(drifted, encoding="utf-8")


def hydrated_uv_cache(binary: Path) -> Path | None:
    """Return uv's local cache when it can validate the current lock offline."""

    process = subprocess.run(
        [str(binary), "cache", "dir"],
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    if process.returncode != 0:
        return None
    cache = Path(process.stdout.strip())
    if not cache.is_dir():
        return None
    baseline = run_lock_check(binary, REPOSITORY_ROOT, cache)
    return cache if baseline.returncode == 0 else None


def installed_inventory(python: Path) -> list[str]:
    """Return a normalized distribution inventory from an isolated interpreter."""

    script = (
        "import importlib.metadata as m; "
        "print('\\n'.join(sorted('{}=={}'.format("
        "d.metadata['Name'].lower(), d.version) for d in m.distributions())))"
    )
    process = subprocess.run(
        [str(python), "-I", "-c", script],
        env={"PATH": os.defpath},
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    return process.stdout.splitlines()


def test_exact_uv_accepts_the_committed_lock_offline(
    exact_uv_binary: Path,
    tmp_path: Path,
) -> None:
    version = subprocess.run(
        [str(exact_uv_binary), "--version"],
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert version.returncode == 0
    assert version.stdout.startswith(f"uv {EXPECTED_UV_VERSION} ")

    result = run_lock_check(exact_uv_binary, REPOSITORY_ROOT, tmp_path / "cache")
    assert result.returncode == 0, result.stderr


def test_exact_uv_rejects_deliberate_project_drift_offline(
    exact_uv_binary: Path,
    tmp_path: Path,
) -> None:
    cache = hydrated_uv_cache(exact_uv_binary)
    if cache is None:
        pytest.skip(
            "the local uv cache is not hydrated enough for an offline drift resolution"
        )
    copied_project = tmp_path / "drifted-project"
    copy_lock_inputs(copied_project)
    drift_project(copied_project)

    result = run_lock_check(exact_uv_binary, copied_project, cache)
    assert result.returncode != 0
    diagnostic = f"{result.stdout}\n{result.stderr}".lower()
    assert "lock" in diagnostic
    assert "update" in diagnostic or "changed" in diagnostic


def test_make_removes_frozen_and_working_directory_bypasses(
    exact_uv_binary: Path,
    tmp_path: Path,
) -> None:
    cache = hydrated_uv_cache(exact_uv_binary)
    if cache is None:
        pytest.skip(
            "the local uv cache is not hydrated enough for an offline drift resolution"
        )

    drifted_project = tmp_path / "make-drifted-project"
    copy_lock_inputs(drifted_project)
    shutil.copy2(REPOSITORY_ROOT / "Makefile", drifted_project / "Makefile")
    drift_project(drifted_project)

    decoy_project = tmp_path / "decoy-project"
    copy_lock_inputs(decoy_project)

    environment = uv_environment(cache)
    environment.update(
        {
            "UV_FROZEN": "1",
            "UV_WORKING_DIR": str(decoy_project),
            "UV_WORKING_DIRECTORY": str(decoy_project),
            "UV_PROJECT_ENVIRONMENT": str(decoy_project / ".venv"),
        }
    )
    result = subprocess.run(
        [
            "make",
            "python-lock-check",
            f"UV={exact_uv_binary}",
        ],
        cwd=drifted_project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode != 0
    diagnostic = f"{result.stdout}\n{result.stderr}".lower()
    assert "lock" in diagnostic
    assert "update" in diagnostic or "changed" in diagnostic


def test_make_uses_only_the_repository_uv_configuration(
    exact_uv_binary: Path,
    tmp_path: Path,
) -> None:
    user_config = tmp_path / "xdg-config" / "uv"
    user_config.mkdir(parents=True)
    (user_config / "uv.toml").write_text(
        "this is deliberately invalid TOML = [\n",
        encoding="utf-8",
    )
    environment = uv_environment(tmp_path / "cache")
    environment["XDG_CONFIG_HOME"] = str(user_config.parent)
    result = subprocess.run(
        ["make", "python-lock-check", f"UV={exact_uv_binary}"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "deliberately invalid" not in result.stderr


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("MAKEFLAGS", "-i"),
        ("MAKEFLAGS", "--ignore-errors"),
        ("MAKEFLAGS", "-n"),
        ("MAKEFLAGS", "--just-print"),
        ("MAKEFLAGS", "-t"),
        ("MAKEFLAGS", "--touch"),
        ("MAKEFLAGS", "-e"),
        ("GNUMAKEFLAGS", "-i"),
    ],
)
def test_make_rejects_ambient_non_verifying_modes(
    exact_uv_binary: Path,
    tmp_path: Path,
    variable: str,
    value: str,
) -> None:
    environment = uv_environment(tmp_path / "cache")
    environment.update(
        {
            variable: value,
            "UV_CLEAN_ENV": "true",
            "UV_RUN": "true",
        }
    )
    result = subprocess.run(
        ["make", "python-lock-check", f"UV={exact_uv_binary}"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode != 0
    diagnostic = f"{result.stdout}\n{result.stderr}"
    assert "Refusing non-verifying GNU Make mode" in diagnostic


def test_make_rejects_direct_makeflags_assignment_and_preloaded_makefile(
    exact_uv_binary: Path,
    tmp_path: Path,
) -> None:
    environment = uv_environment(tmp_path / "cache")
    direct = subprocess.run(
        [
            "make",
            "python-lock-check",
            f"UV={exact_uv_binary}",
            "MAKEFLAGS=",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert direct.returncode != 0
    assert "Direct MAKEFLAGS assignments are not allowed" in direct.stderr

    preload = tmp_path / "injected.mk"
    preload.write_text(".IGNORE:\n", encoding="utf-8")
    environment["MAKEFILES"] = str(preload)
    preloaded = subprocess.run(
        ["make", "python-lock-check", "UV=/bin/false"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert preloaded.returncode != 0
    assert "Preloaded MAKEFILES are not allowed" in preloaded.stderr


def test_internal_make_helpers_cannot_be_replaced(
    tmp_path: Path,
) -> None:
    environment = uv_environment(tmp_path / "cache")
    environment.update({"UV_CLEAN_ENV": "true", "UV_RUN": "true"})
    result = subprocess.run(
        [
            "make",
            "python-lock-check",
            "UV=/bin/false",
            "UV_CLEAN_ENV=true",
            "UV_RUN=true",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode != 0


def test_make_lock_check_supports_repository_paths_with_spaces(
    exact_uv_binary: Path,
    tmp_path: Path,
) -> None:
    copied_project = tmp_path / "repository path with spaces"
    copy_lock_inputs(copied_project)
    shutil.copy2(REPOSITORY_ROOT / "Makefile", copied_project / "Makefile")
    result = subprocess.run(
        ["make", "python-lock-check", f"UV={exact_uv_binary}"],
        cwd=copied_project,
        env=uv_environment(tmp_path / "cache"),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


@pytest.mark.parametrize(
    "injection_variable",
    ["MAKEFLAGS", "GNUMAKEFLAGS", "MAKEFILES"],
)
def test_trusted_wrapper_removes_preparse_make_injection(
    exact_uv_binary: Path,
    tmp_path: Path,
    injection_variable: str,
) -> None:
    copied_project = tmp_path / "wrapper-drifted-project"
    copy_lock_inputs(copied_project)
    shutil.copy2(REPOSITORY_ROOT / "Makefile", copied_project / "Makefile")
    copied_scripts = copied_project / "scripts"
    copied_scripts.mkdir()
    wrapper = copied_scripts / "python_toolchain.sh"
    shutil.copy2(REPOSITORY_ROOT / "scripts/python_toolchain.sh", wrapper)
    drift_project(copied_project)

    environment = uv_environment(tmp_path / "cache")
    if injection_variable == "MAKEFILES":
        preload = tmp_path / "ignore-errors.mk"
        preload.write_text(".IGNORE:\n", encoding="utf-8")
        injection = str(preload)
    else:
        injection = "--eval=.IGNORE:"
    environment[injection_variable] = injection
    result = subprocess.run(
        [str(wrapper), "--uv", str(exact_uv_binary), "lock-check"],
        cwd=copied_project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode != 0
    diagnostic = f"{result.stdout}\n{result.stderr}".lower()
    assert "lock" in diagnostic
    assert "update" in diagnostic or "changed" in diagnostic


def test_trusted_wrapper_ignores_bash_startup_injection(tmp_path: Path) -> None:
    startup = tmp_path / "bash-env"
    startup.write_text("exit 0\n", encoding="utf-8")
    environment = uv_environment(tmp_path / "cache")
    environment["BASH_ENV"] = str(startup)
    result = subprocess.run(
        [
            str(REPOSITORY_ROOT / "scripts/python_toolchain.sh"),
            "--uv",
            "/bin/false",
            "lock-check",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode != 0
    assert "unable to execute uv" in result.stderr


def test_make_offline_sync_builds_a_fresh_controlled_environment(
    exact_uv_binary: Path,
    tmp_path: Path,
) -> None:
    cache = hydrated_uv_cache(exact_uv_binary)
    if cache is None:
        pytest.skip("the local uv cache is not hydrated enough for an offline sync")

    copied_project = tmp_path / "offline-project"
    copy_lock_inputs(copied_project)
    shutil.copy2(REPOSITORY_ROOT / "Makefile", copied_project / "Makefile")
    result = subprocess.run(
        ["make", "python-sync-offline", f"UV={exact_uv_binary}"],
        cwd=copied_project,
        env=uv_environment(cache),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    offline_environment = copied_project / ".venv-offline-check"
    assert offline_environment.is_dir()
    assert not offline_environment.is_symlink()
    assert installed_inventory(offline_environment / "bin/python") == (
        installed_inventory(Path(sys.executable))
    )


def test_make_test_ignores_collection_only_and_code_injection_environment(
    exact_uv_binary: Path,
    tmp_path: Path,
) -> None:
    if os.environ.get("RAOS_ST0102_NESTED") == "1":
        return

    injected_module_root = tmp_path / "injected"
    injected_module_root.mkdir()
    marker = tmp_path / "sitecustomize-executed"
    (injected_module_root / "sitecustomize.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )
    env_file = tmp_path / "injected.env"
    env_file.write_text("PYTEST_ADDOPTS=--collect-only\n", encoding="utf-8")

    environment = uv_environment(tmp_path / "nested-cache")
    environment.update(
        {
            "PYTEST_ADDOPTS": "--collect-only",
            "PYTEST_PLUGINS": "raos_missing_injected_plugin",
            "PYTHONOPTIMIZE": "2",
            "PYTHONPATH": str(injected_module_root),
            "RAOS_ST0102_NESTED": "1",
            "UV_ENV_FILE": str(env_file),
        }
    )
    result = subprocess.run(
        ["make", "python-test", f"UV={exact_uv_binary}"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert re.search(r"\b\d+ passed\b", result.stdout)
    assert "tests collected" not in result.stdout
    assert not marker.exists()


def test_locally_available_older_uv_is_rejected_by_required_version(
    tmp_path: Path,
) -> None:
    older = [
        (binary, version)
        for binary, version in local_uv_binaries()
        if version != EXPECTED_UV_VERSION
    ]
    if not older:
        pytest.skip("no second, non-0.12.1 uv binary is locally discoverable")

    binary, running_version = older[0]
    result = run_lock_check(binary, REPOSITORY_ROOT, tmp_path / "old-cache")
    assert result.returncode != 0
    diagnostic = f"{result.stdout}\n{result.stderr}".lower()
    assert "required uv version" in diagnostic
    assert f"=={EXPECTED_UV_VERSION}" in diagnostic
    assert running_version in diagnostic
