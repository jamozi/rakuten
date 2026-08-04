"""Shared fixtures for the isolated ST-0102 Python-toolchain suite."""

from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_UV_VERSION = "0.12.1"
UV_VERSION_PATTERN = re.compile(r"^uv (?P<version>\d+\.\d+\.\d+)(?:\s|$)")


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
