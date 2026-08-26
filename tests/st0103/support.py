"""Shared fixtures for the isolated ST-0103 Node-toolchain suite."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_NODE_VERSION = "24.18.1"
EXPECTED_NPM_VERSION = "11.16.0"
NODE_VERSION_PATTERN = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")
NPM_VERSION_PATTERN = re.compile(r"^(?P<version>\d+\.\d+\.\d+)$")

NODE_PROJECT_FILES = (
    ".node-version",
    ".npmrc",
    "package.json",
    "package-lock.json",
    "tsconfig.base.json",
    "tsconfig.json",
    "eslint.config.mjs",
    "prettier.config.mjs",
    "pyrightconfig.json",
    "vitest.config.ts",
    "Makefile",
    "scripts/node_toolchain.sh",
    "scripts/node_inventory.mjs",
    "apps/web/package.json",
    "packages/web-contracts/package.json",
    "packages/web-contracts/tsconfig.json",
    "packages/web-ui/package.json",
    "tests/st0103/toolchain.test.ts",
)


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object without accepting a top-level scalar or array."""

    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


@pytest.fixture(scope="session")
def package_manifest() -> dict[str, Any]:
    """Load the root npm workspace manifest."""

    return load_json(REPOSITORY_ROOT / "package.json")


@pytest.fixture(scope="session")
def web_manifest() -> dict[str, Any]:
    """Load the intentionally package-only Next.js workspace boundary."""

    return load_json(REPOSITORY_ROOT / "apps/web/package.json")


@pytest.fixture(scope="session")
def web_ui_manifest() -> dict[str, Any]:
    """Load the intentionally inert shared-UI workspace boundary."""

    return load_json(REPOSITORY_ROOT / "packages/web-ui/package.json")


@pytest.fixture(scope="session")
def web_contracts_manifest() -> dict[str, Any]:
    """Load the generated contract workspace boundary."""

    return load_json(REPOSITORY_ROOT / "packages/web-contracts/package.json")


@pytest.fixture(scope="session")
def package_lock() -> dict[str, Any]:
    """Load the generated npm lockfile v3."""

    return load_json(REPOSITORY_ROOT / "package-lock.json")


def clean_environment(cache_directory: Path) -> dict[str, str]:
    """Return a credential-free process environment for local CLI probes."""

    environment = {
        "HOME": str(cache_directory.parent / "empty-home"),
        "PATH": os.defpath,
        "RAOS_NPM_CACHE": str(cache_directory),
        "TMPDIR": str(cache_directory.parent / "tmp"),
    }
    Path(environment["HOME"]).mkdir(parents=True, exist_ok=True)
    Path(environment["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    for name in ("LANG", "LC_ALL"):
        if value := os.environ.get(name):
            environment[name] = value
    return environment


def _candidate_node_paths() -> Iterator[Path]:
    configured = os.environ.get("NODE")
    if configured:
        resolved = shutil.which(configured)
        if resolved:
            yield Path(resolved)
        else:
            candidate = Path(configured)
            if candidate.is_absolute() and candidate.is_file():
                yield candidate

    if resolved := shutil.which("node"):
        yield Path(resolved)

    # The exact runtime is installed as an explicit local prerequisite rather
    # than fetched by a package-manager shim during verification.
    yield Path(f"/home/minami/.nvm/versions/node/v{EXPECTED_NODE_VERSION}/bin/node")

    proc_parent = Path(f"/proc/{os.getppid()}/exe")
    try:
        parent_executable = proc_parent.resolve(strict=True)
    except FileNotFoundError, OSError, RuntimeError:
        return
    if parent_executable.name == "node":
        yield parent_executable


def node_version(binary: Path) -> str | None:
    """Return a locally executable Node semantic version."""

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
    match = NODE_VERSION_PATTERN.fullmatch(process.stdout.strip())
    if process.returncode != 0 or match is None:
        return None
    return match.group("version")


def npm_cli_for_node(binary: Path) -> Path | None:
    """Resolve the npm CLI bundled below a normal Node installation prefix."""

    configured = os.environ.get("NPM_CLI")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    try:
        prefix = binary.resolve(strict=True).parent.parent
    except FileNotFoundError, OSError, RuntimeError:
        return None
    candidates.extend(
        (
            prefix / "lib/node_modules/npm/bin/npm-cli.js",
            prefix / "node_modules/npm/bin/npm-cli.js",
        )
    )
    for candidate in candidates:
        if candidate.is_absolute() and candidate.is_file():
            return candidate
    return None


def npm_version(binary: Path, npm_cli: Path) -> str | None:
    """Return the npm semantic version produced by the selected Node binary."""

    try:
        process = subprocess.run(
            [str(binary), str(npm_cli), "--version"],
            env={"PATH": os.defpath},
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    match = NPM_VERSION_PATTERN.fullmatch(process.stdout.strip())
    if process.returncode != 0 or match is None:
        return None
    return match.group("version")


def local_node_toolchains() -> list[tuple[Path, Path, str, str]]:
    """Discover unique runnable Node/npm pairs from local execution context."""

    discovered: list[tuple[Path, Path, str, str]] = []
    seen: set[Path] = set()
    for candidate in _candidate_node_paths():
        try:
            canonical = candidate.resolve(strict=True)
        except FileNotFoundError, OSError, RuntimeError:
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        running_node = node_version(candidate)
        npm_cli = npm_cli_for_node(candidate)
        if running_node is None or npm_cli is None:
            continue
        running_npm = npm_version(candidate, npm_cli)
        if running_npm is not None:
            discovered.append((candidate, npm_cli, running_node, running_npm))
    return discovered


@pytest.fixture(scope="session")
def exact_node_toolchain() -> tuple[Path, Path]:
    """Select the exact local Node/npm pair, or skip with an actionable reason."""

    for node, npm_cli, running_node, running_npm in local_node_toolchains():
        if (
            running_node == EXPECTED_NODE_VERSION
            and running_npm == EXPECTED_NPM_VERSION
        ):
            return node, npm_cli
    pytest.skip(
        "exact Node 24.18.1 with bundled npm 11.16.0 is not locally discoverable"
    )


def run_wrapper(
    node: Path,
    npm_cli: Path,
    command: str,
    *,
    cwd: Path = REPOSITORY_ROOT,
    environment: Mapping[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run the trusted Node evidence wrapper with an explicit toolchain pair."""

    return subprocess.run(
        [
            str(cwd / "scripts/node_toolchain.sh"),
            "--node",
            str(node),
            "--npm-cli",
            str(npm_cli),
            command,
        ],
        cwd=cwd,
        env=dict(environment) if environment is not None else None,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


def copy_node_project(destination: Path) -> None:
    """Copy only the maintained Node inputs needed by isolated CLI probes."""

    destination.mkdir(parents=True)
    for relative in NODE_PROJECT_FILES:
        source = REPOSITORY_ROOT / relative
        if not source.exists():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
