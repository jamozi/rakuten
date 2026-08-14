"""Shared fixtures for the isolated ST-0102 Python-toolchain suite."""

from __future__ import annotations

from collections.abc import Iterator
import functools
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import tomllib
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_UV_VERSION = "0.12.1"
UV_VERSION_PATTERN = re.compile(r"^uv (?P<version>\d+\.\d+\.\d+)(?:\s|$)")
UV_LOCK_INPUTS = (".python-version", "pyproject.toml", "uv.toml", "uv.lock")


@pytest.fixture(scope="session")
def project_config() -> dict[str, Any]:
    """Load the maintained project contract with Python 3.14 ``tomllib``."""

    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)


@pytest.fixture(scope="session")
def uv_config() -> dict[str, Any]:
    """Load the sole uv resolution/install configuration."""

    with (REPOSITORY_ROOT / "uv.toml").open("rb") as stream:
        return tomllib.load(stream)


@pytest.fixture(scope="session")
def lock_config() -> dict[str, Any]:
    """Load the generated uv lock with Python 3.14 ``tomllib``."""

    with (REPOSITORY_ROOT / "uv.lock").open("rb") as stream:
        return tomllib.load(stream)


def uv_environment(cache_directory: Path) -> dict[str, str]:
    """Return a credential-free environment that makes network use impossible."""

    environment = {
        "PATH": os.defpath,
        "PYTHONDONTWRITEBYTECODE": "1",
        "RAOS_CI_OFFLINE": "1",
        "UV_CACHE_DIR": str(cache_directory),
        "UV_NO_PROGRESS": "1",
        "UV_OFFLINE": "1",
        "UV_PYTHON_DOWNLOADS": "never",
    }
    for name in ("LANG", "LC_ALL"):
        if value := os.environ.get(name):
            environment[name] = value
    return environment


def explicit_ci_uv_cache() -> Path | None:
    """Return the exact CI cache, failing rather than falling back if unsafe."""

    configured = os.environ.get("RAOS_CI_UV_CACHE_DIR")
    if configured is None:
        return None
    if not configured.startswith("/"):
        pytest.fail("RAOS_CI_UV_CACHE_DIR must be an absolute canonical directory")
    candidate = Path(configured)
    try:
        metadata = candidate.lstat()
        canonical = candidate.resolve(strict=True)
    except OSError, RuntimeError:
        pytest.fail("RAOS_CI_UV_CACHE_DIR must be an existing safe directory")
    if (
        str(canonical) != configured
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        pytest.fail("RAOS_CI_UV_CACHE_DIR ownership, mode, or path is unsafe")
    return canonical


@functools.cache
def uv_cache_supports_locked_offline_sync(binary: Path, cache: Path) -> bool:
    """Prove that a cache can build the exact locked dev environment offline."""

    with tempfile.TemporaryDirectory(prefix="raos-st0102-cache-probe-") as temporary:
        project = Path(temporary) / "project"
        project.mkdir()
        for relative in UV_LOCK_INPUTS:
            shutil.copy2(REPOSITORY_ROOT / relative, project / relative)
        process = subprocess.run(
            [
                str(binary),
                "--no-config",
                "--color",
                "never",
                "--cache-dir",
                str(cache),
                "sync",
                "--locked",
                "--offline",
                "--no-default-groups",
                "--group",
                "dev",
                "--no-install-project",
                "--no-install-local",
                "--managed-python",
                "--no-python-downloads",
                "--python",
                "3.14.6",
                "--no-build",
                "--no-sources",
                "--default-index",
                "https://pypi.org/simple",
                "--index-strategy",
                "first-index",
                "--keyring-provider",
                "disabled",
                "--link-mode",
                "copy",
                "--resolution",
                "highest",
                "--prerelease",
                "disallow",
                "--exclude-newer",
                "2026-08-01T16:50:16Z",
                "--no-progress",
            ],
            cwd=project,
            env=uv_environment(cache),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
        python = project / ".venv" / "bin" / "python"
        return process.returncode == 0 and python.is_file()


def _candidate_uv_paths() -> Iterator[Path]:
    configured = os.environ.get("UV")
    if configured:
        resolved = shutil.which(configured)
        if resolved:
            yield Path(resolved)
        else:
            candidate = Path(configured)
            if candidate.is_absolute() and candidate.is_file():
                yield candidate

    if resolved := shutil.which("uv"):
        yield Path(resolved)

    # ``uv run`` remains the parent while its command executes on Linux. This
    # recovers the exact configured executable even when make did not export UV.
    proc_parent = Path(f"/proc/{os.getppid()}/exe")
    try:
        parent_executable = proc_parent.resolve(strict=True)
    except FileNotFoundError, OSError, RuntimeError:
        return
    if parent_executable.name == "uv":
        yield parent_executable


def uv_version(binary: Path) -> str | None:
    """Return a locally executable uv semantic version, without network access."""

    try:
        process = subprocess.run(
            [str(binary), "--version"],
            env={"PATH": os.defpath},
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    match = UV_VERSION_PATTERN.match(process.stdout.strip())
    if process.returncode != 0 or match is None:
        return None
    return match.group("version")


def local_uv_binaries() -> list[tuple[Path, str]]:
    """Discover unique runnable uv binaries from repository execution context."""

    discovered: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for candidate in _candidate_uv_paths():
        try:
            canonical = candidate.resolve(strict=True)
        except FileNotFoundError, OSError, RuntimeError:
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        # Preserve the invoked path. Snap app links, for example, resolve to the
        # generic ``snap`` launcher and only retain app identity through argv[0].
        if version := uv_version(candidate):
            discovered.append((candidate, version))
    return discovered


@pytest.fixture(scope="session")
def exact_uv_binary() -> Path:
    """Select the configured exact uv, or skip with an actionable reason."""

    for binary, version in local_uv_binaries():
        if version == EXPECTED_UV_VERSION:
            return binary
    pytest.skip(
        "exact uv 0.12.1 is not locally discoverable; run through the repository "
        "Make target with UV=/absolute/path/to/uv"
    )
