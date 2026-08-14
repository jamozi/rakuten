"""Adversarial Node/npm CLI checks for deterministic ST-0103 evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Literal

import pytest

from conftest import (
    EXPECTED_NODE_VERSION,
    EXPECTED_NPM_VERSION,
    REPOSITORY_ROOT,
    clean_environment,
    copy_node_project,
    run_wrapper,
)


NpmColdCacheMissKind = Literal["online-fetch", "offline-replay"]
NPM_COLD_CACHE_TARBALL_URL = (
    "https://registry.npmjs.org/zod-validation-error/-/zod-validation-error-4.0.2.tgz"
)
NPM_COLD_CACHE_ERROR_LINES: dict[NpmColdCacheMissKind, tuple[str, ...]] = {
    "online-fetch": (
        "npm error code EAI_AGAIN",
        "npm error syscall getaddrinfo",
        "npm error errno EAI_AGAIN",
        f"npm error request to {NPM_COLD_CACHE_TARBALL_URL} failed, reason: "
        "getaddrinfo EAI_AGAIN registry.npmjs.org",
    ),
    "offline-replay": (
        "npm error code ENOTCACHED",
        f"npm error request to {NPM_COLD_CACHE_TARBALL_URL} failed: cache mode "
        "is 'only-if-cached' but no cached response is available.",
    ),
}
NPM_DEBUG_LOG_PREFIX = "npm error A complete log of this run can be found in: "
NPM_COLD_CACHE_MAKE_ERROR: dict[NpmColdCacheMissKind, str] = {
    "online-fetch": "make: *** [Makefile:619: node-sync] Error 1",
    "offline-replay": "make: *** [Makefile:637: node-sync-offline] Error 1",
}
NPM_COLD_CACHE_WRAPPER_COMMAND: dict[NpmColdCacheMissKind, str] = {
    "online-fetch": "versions",
    "offline-replay": "sync-offline",
}


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
        "workspaces": [
            "apps/web",
            "packages/web-contracts",
            "packages/web-ui",
        ],
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


def continued_make_command(
    command: str,
    argument_rows: tuple[tuple[Path, ...], ...],
) -> str:
    """Render one reviewed multiline Make recipe command exactly."""

    lines = [f"{command} \\"]
    for index, row in enumerate(argument_rows):
        suffix = " \\" if index < len(argument_rows) - 1 else ""
        lines.append("\t" + " ".join(f'"{path}"' for path in row) + suffix)
    return "\n".join(lines)


def npm_cold_cache_wrapper_args(
    kind: NpmColdCacheMissKind,
    *,
    node: Path,
    npm_cli: Path,
) -> list[str]:
    """Return the one reviewed wrapper invocation for a cache-miss kind."""

    return [
        str(REPOSITORY_ROOT / "scripts/node_toolchain.sh"),
        "--node",
        str(node),
        "--npm-cli",
        str(npm_cli),
        NPM_COLD_CACHE_WRAPPER_COMMAND[kind],
    ]


def npm_cold_cache_wrapper_stdout(
    kind: NpmColdCacheMissKind,
    *,
    node: Path,
) -> str:
    """Render the complete reviewed pre-failure Make stdout."""

    root = REPOSITORY_ROOT
    node_environment = (
        f'env -i PATH="/usr/bin:/bin" HOME="{root}" '
        "LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC "
        "COREPACK_ENABLE_NETWORK=0 COREPACK_ENABLE_PROJECT_SPEC=0 "
        f'COREPACK_HOME="{root}/.npm-cache/corepack" '
        "NEXT_TELEMETRY_DISABLED=1 "
        f'NPM_CONFIG_USERCONFIG="{root}/.npmrc" '
        "NPM_CONFIG_GLOBALCONFIG=/dev/null "
        f'NPM_CONFIG_CACHE="{root}/.npm-cache" '
        "NPM_CONFIG_REGISTRY=https://registry.npmjs.org/ "
        "NPM_CONFIG_IGNORE_SCRIPTS=true NPM_CONFIG_AUDIT=false "
        "NPM_CONFIG_FUND=false NPM_CONFIG_UPDATE_NOTIFIER=false "
        f'"{node}" "{root}/scripts/node_inventory.mjs"'
    )
    records = [
        continued_make_command(
            f"{node_environment} guard",
            (
                (root / "apps",),
                (root / "apps/web",),
                (root / "packages",),
                (root / "packages/web-contracts",),
                (root / "packages/web-ui",),
                (root / ".npm-cache", root / "node_modules"),
                (root / "apps/web/node_modules",),
                (root / "packages/web-contracts/node_modules",),
                (root / "packages/web-ui/node_modules",),
            ),
        ),
        continued_make_command(
            f"{node_environment} guard-files",
            (
                (root / ".npmrc", root / "package.json"),
                (root / "apps/web/package.json",),
                (root / "packages/web-contracts/package.json",),
                (root / "packages/web-contracts/tsconfig.json",),
                (root / "packages/web-ui/package.json",),
            ),
        ),
        continued_make_command(
            f"{node_environment} guard-optional-files",
            ((root / "package-lock.json",),),
        ),
        f'test -f "{root}/package-lock.json"',
    ]
    if kind == "online-fetch":
        records.append(
            continued_make_command(
                f"{node_environment} verify-lock-manifests",
                (
                    (root / "package-lock.json",),
                    (root / "package.json",),
                    (root / "apps/web/package.json",),
                    (root / "packages/web-contracts/package.json",),
                    (root / "packages/web-ui/package.json",),
                ),
            )
        )
    else:
        records.extend(
            (
                f'test -d "{root}/.npm-cache"',
                f'test -d "{root}/node_modules"',
            )
        )
    return "\n".join(records) + "\n"


def npm_cold_cache_toolchain(
    result: subprocess.CompletedProcess[str],
    kind: NpmColdCacheMissKind,
) -> tuple[Path, Path] | None:
    """Validate and extract the reviewed wrapper invocation paths."""

    if not isinstance(result.args, list) or not all(
        isinstance(argument, str) for argument in result.args
    ):
        return None
    if len(result.args) != 6:
        return None
    wrapper, node_flag, node_value, npm_flag, npm_value, command = result.args
    node = Path(node_value)
    npm_cli = Path(npm_value)
    if (
        wrapper != str(REPOSITORY_ROOT / "scripts/node_toolchain.sh")
        or node_flag != "--node"
        or npm_flag != "--npm-cli"
        or command != NPM_COLD_CACHE_WRAPPER_COMMAND[kind]
        or not node.is_absolute()
        or not npm_cli.is_absolute()
        or npm_cli != node.parent.parent / "lib/node_modules/npm/bin/npm-cli.js"
    ):
        return None
    return node, npm_cli


def is_exact_npm_cold_cache_miss(
    result: subprocess.CompletedProcess[str],
    kind: NpmColdCacheMissKind,
) -> bool:
    """Classify only the reviewed npm 11.16.0 missing-tarball diagnostics."""

    if result.returncode == 0:
        return False
    toolchain = npm_cold_cache_toolchain(result, kind)
    if toolchain is None:
        return False
    node, _ = toolchain
    if result.stdout != npm_cold_cache_wrapper_stdout(kind, node=node):
        return False
    stderr_lines = result.stderr.splitlines()
    expected_error_lines = NPM_COLD_CACHE_ERROR_LINES[kind]
    if tuple(stderr_lines[: len(expected_error_lines)]) != expected_error_lines:
        return False
    remaining_lines = stderr_lines[len(expected_error_lines) :]
    if len(remaining_lines) != 2:
        return False
    debug_log_line, make_error_line = remaining_lines
    debug_log_path = debug_log_line.removeprefix(NPM_DEBUG_LOG_PREFIX)
    expected_log_prefix = re.escape(f"{REPOSITORY_ROOT}/.npm-cache/_logs/")
    if (
        debug_log_path == debug_log_line
        or re.fullmatch(
            expected_log_prefix + r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
            r"[0-9]{2}_[0-9]{2}_[0-9]{2}_[0-9]{3}Z-debug-0\.log",
            debug_log_path,
        )
        is None
    ):
        return False
    return make_error_line == NPM_COLD_CACHE_MAKE_ERROR[kind]


def skip_exact_npm_cold_cache_miss(
    result: subprocess.CompletedProcess[str],
    kind: NpmColdCacheMissKind,
) -> None:
    """Skip a positive capability probe only for the exact cold-cache shape."""

    if result.returncode == 0:
        assert not any(
            line.startswith("npm error ")
            for line in (result.stdout + "\n" + result.stderr).splitlines()
        ), diagnostics(result)
        return
    if is_exact_npm_cold_cache_miss(result, kind):
        pytest.skip(
            "the repository npm cache lacks the exact public "
            "zod-validation-error@4.0.2 tarball"
        )


def npm_cold_cache_wrapper_stderr(
    kind: NpmColdCacheMissKind,
    error_lines: tuple[str, ...],
    *,
    debug_log_path: str | None = None,
    make_error_line: str | None = None,
) -> str:
    """Build one deterministic npm wrapper diagnostic for classifier tests."""

    if debug_log_path is None:
        debug_log_path = (
            f"{REPOSITORY_ROOT}/.npm-cache/_logs/2026-08-15T00_00_00_000Z-debug-0.log"
        )
    if make_error_line is None:
        make_error_line = NPM_COLD_CACHE_MAKE_ERROR[kind]
    return "\n".join(
        (
            *error_lines,
            NPM_DEBUG_LOG_PREFIX + debug_log_path,
            make_error_line,
        )
    )


@pytest.mark.parametrize(
    ("kind", "error_lines"),
    list(NPM_COLD_CACHE_ERROR_LINES.items()),
)
def test_exact_npm_cold_cache_classifier_accepts_only_reviewed_shapes(
    kind: NpmColdCacheMissKind,
    error_lines: tuple[str, ...],
) -> None:
    node = Path("/opt/raos-node/bin/node")
    npm_cli = Path("/opt/raos-node/lib/node_modules/npm/bin/npm-cli.js")
    result = subprocess.CompletedProcess(
        args=npm_cold_cache_wrapper_args(kind, node=node, npm_cli=npm_cli),
        returncode=1,
        stdout=npm_cold_cache_wrapper_stdout(kind, node=node),
        stderr=npm_cold_cache_wrapper_stderr(kind, error_lines),
    )
    assert is_exact_npm_cold_cache_miss(result, kind)


@pytest.mark.parametrize(
    ("kind", "returncode", "error_lines"),
    [
        ("online-fetch", 0, NPM_COLD_CACHE_ERROR_LINES["online-fetch"]),
        (
            "online-fetch",
            1,
            NPM_COLD_CACHE_ERROR_LINES["online-fetch"][:-1],
        ),
        (
            "online-fetch",
            1,
            (
                *NPM_COLD_CACHE_ERROR_LINES["online-fetch"][:-1],
                NPM_COLD_CACHE_ERROR_LINES["online-fetch"][-1].replace(
                    "EAI_AGAIN", "EAI_AGAIN: temporary failure", 1
                ),
            ),
        ),
        (
            "online-fetch",
            1,
            tuple(
                line.replace("registry.npmjs.org", "registry.example.invalid")
                for line in NPM_COLD_CACHE_ERROR_LINES["online-fetch"]
            ),
        ),
        (
            "online-fetch",
            1,
            tuple(
                line.replace("zod-validation-error-4.0.2", "zod-validation-error-4.0.1")
                for line in NPM_COLD_CACHE_ERROR_LINES["online-fetch"]
            ),
        ),
        (
            "online-fetch",
            1,
            (
                *NPM_COLD_CACHE_ERROR_LINES["online-fetch"],
                "npm error code EINTEGRITY",
            ),
        ),
        (
            "online-fetch",
            1,
            (
                *NPM_COLD_CACHE_ERROR_LINES["online-fetch"],
                "error: dependency integrity check failed",
            ),
        ),
        (
            "offline-replay",
            1,
            (
                *NPM_COLD_CACHE_ERROR_LINES["offline-replay"],
                "error: package-lock inventory mismatch",
            ),
        ),
        (
            "offline-replay",
            1,
            NPM_COLD_CACHE_ERROR_LINES["online-fetch"],
        ),
        (
            "offline-replay",
            1,
            (
                "npm error code ENOTCACHED",
                NPM_COLD_CACHE_ERROR_LINES["offline-replay"][-1].replace(
                    "no cached response is available.", "cache entry was not found."
                ),
            ),
        ),
        ("online-fetch", 1, ("error: package-lock inventory mismatch",)),
        ("online-fetch", 1, ("error: dependency integrity check failed",)),
        ("online-fetch", 1, ("error: shell injection marker was created",)),
        ("online-fetch", 1, ("error: required Node version ==24.18.1",)),
    ],
)
def test_exact_npm_cold_cache_classifier_rejects_hostile_near_misses(
    kind: NpmColdCacheMissKind,
    returncode: int,
    error_lines: tuple[str, ...],
) -> None:
    node = Path("/opt/raos-node/bin/node")
    npm_cli = Path("/opt/raos-node/lib/node_modules/npm/bin/npm-cli.js")
    result = subprocess.CompletedProcess(
        args=npm_cold_cache_wrapper_args(kind, node=node, npm_cli=npm_cli),
        returncode=returncode,
        stdout=npm_cold_cache_wrapper_stdout(kind, node=node),
        stderr=npm_cold_cache_wrapper_stderr(kind, error_lines),
    )
    assert not is_exact_npm_cold_cache_miss(result, kind)


@pytest.mark.parametrize(
    "extra_stdout",
    [
        "cache capability probe complete",
        "dependency integrity verification failed",
        "security policy check failed",
    ],
)
@pytest.mark.parametrize(
    ("kind", "error_lines"),
    list(NPM_COLD_CACHE_ERROR_LINES.items()),
)
def test_exact_npm_cold_cache_classifier_rejects_any_extra_stdout(
    kind: NpmColdCacheMissKind,
    error_lines: tuple[str, ...],
    extra_stdout: str,
) -> None:
    node = Path("/opt/raos-node/bin/node")
    npm_cli = Path("/opt/raos-node/lib/node_modules/npm/bin/npm-cli.js")
    result = subprocess.CompletedProcess(
        args=npm_cold_cache_wrapper_args(kind, node=node, npm_cli=npm_cli),
        returncode=1,
        stdout=(npm_cold_cache_wrapper_stdout(kind, node=node) + extra_stdout + "\n"),
        stderr=npm_cold_cache_wrapper_stderr(kind, error_lines),
    )
    assert not is_exact_npm_cold_cache_miss(result, kind)


@pytest.mark.parametrize(
    "debug_log_path",
    [
        f"{REPOSITORY_ROOT}/.npm-cache/_logs/../outside-debug-0.log",
        f"{REPOSITORY_ROOT}/.npm-cache/logs/2026-08-15T00_00_00_000Z-debug-0.log",
        "/tmp/alternate/.npm-cache/_logs/2026-08-15T00_00_00_000Z-debug-0.log",
        f"{REPOSITORY_ROOT}/.npm-cache/_logs/"
        "2026-08-15T00_00_00_000Z-debug-0.log.residual",
        f"{REPOSITORY_ROOT}/.npm-cache/_logs/2026-08-15T00:00:00.000Z-debug-0.log",
        f"{REPOSITORY_ROOT}/.npm-cache/_logs/2026-08-15T00_00_00_000Z-debug-1.log",
    ],
)
@pytest.mark.parametrize(
    ("kind", "error_lines"),
    list(NPM_COLD_CACHE_ERROR_LINES.items()),
)
def test_exact_npm_cold_cache_classifier_rejects_debug_log_path_near_misses(
    kind: NpmColdCacheMissKind,
    error_lines: tuple[str, ...],
    debug_log_path: str,
) -> None:
    node = Path("/opt/raos-node/bin/node")
    npm_cli = Path("/opt/raos-node/lib/node_modules/npm/bin/npm-cli.js")
    result = subprocess.CompletedProcess(
        args=npm_cold_cache_wrapper_args(kind, node=node, npm_cli=npm_cli),
        returncode=1,
        stdout=npm_cold_cache_wrapper_stdout(kind, node=node),
        stderr=npm_cold_cache_wrapper_stderr(
            kind,
            error_lines,
            debug_log_path=debug_log_path,
        ),
    )
    assert not is_exact_npm_cold_cache_miss(result, kind)


@pytest.mark.parametrize(
    "make_error_line",
    [
        "make: *** [Makefile:619: node-sync-offline] Error 1",
        "make: *** [Makefile:618: node-sync] Error 1",
        "make: *** [Makefile:619: node-sync] Error 2",
        "make: *** [Makefile:619: node-sync] Error 1 ",
    ],
)
def test_exact_npm_cold_cache_classifier_rejects_make_error_near_misses(
    make_error_line: str,
) -> None:
    kind: NpmColdCacheMissKind = "online-fetch"
    node = Path("/opt/raos-node/bin/node")
    npm_cli = Path("/opt/raos-node/lib/node_modules/npm/bin/npm-cli.js")
    result = subprocess.CompletedProcess(
        args=npm_cold_cache_wrapper_args(kind, node=node, npm_cli=npm_cli),
        returncode=1,
        stdout=npm_cold_cache_wrapper_stdout(kind, node=node),
        stderr=npm_cold_cache_wrapper_stderr(
            kind,
            NPM_COLD_CACHE_ERROR_LINES[kind],
            make_error_line=make_error_line,
        ),
    )
    assert not is_exact_npm_cold_cache_miss(result, kind)


@pytest.mark.parametrize(
    "invocation_mutation",
    ["wrapper", "node-flag", "unbundled-npm", "command", "extra-argument"],
)
def test_exact_npm_cold_cache_classifier_rejects_unreviewed_invocation(
    invocation_mutation: str,
) -> None:
    kind: NpmColdCacheMissKind = "online-fetch"
    node = Path("/opt/raos-node/bin/node")
    npm_cli = Path("/opt/raos-node/lib/node_modules/npm/bin/npm-cli.js")
    arguments = npm_cold_cache_wrapper_args(kind, node=node, npm_cli=npm_cli)
    if invocation_mutation == "wrapper":
        arguments[0] = "/tmp/unreviewed/node_toolchain.sh"
    elif invocation_mutation == "node-flag":
        arguments[1] = "--runtime"
    elif invocation_mutation == "unbundled-npm":
        arguments[4] = "/opt/unbundled/npm-cli.js"
    elif invocation_mutation == "command":
        arguments[5] = "check"
    else:
        arguments.append("extra")
    result = subprocess.CompletedProcess(
        args=arguments,
        returncode=1,
        stdout=npm_cold_cache_wrapper_stdout(kind, node=node),
        stderr=npm_cold_cache_wrapper_stderr(
            kind,
            NPM_COLD_CACHE_ERROR_LINES[kind],
        ),
    )
    assert not is_exact_npm_cold_cache_miss(result, kind)


@pytest.mark.parametrize(
    ("kind", "error_lines", "error_stream"),
    [
        (kind, error_lines, error_stream)
        for kind, error_lines in NPM_COLD_CACHE_ERROR_LINES.items()
        for error_stream in ("stdout", "stderr")
    ],
)
def test_skip_helper_fails_closed_on_zero_exit_with_npm_errors(
    kind: NpmColdCacheMissKind,
    error_lines: tuple[str, ...],
    error_stream: Literal["stdout", "stderr"],
) -> None:
    error_diagnostic = npm_cold_cache_wrapper_stderr(kind, error_lines)
    node = Path("/opt/raos-node/bin/node")
    npm_cli = Path("/opt/raos-node/lib/node_modules/npm/bin/npm-cli.js")
    result = subprocess.CompletedProcess(
        args=npm_cold_cache_wrapper_args(kind, node=node, npm_cli=npm_cli),
        returncode=0,
        stdout=(
            f"v{EXPECTED_NODE_VERSION}\n{EXPECTED_NPM_VERSION}\n"
            + (error_diagnostic if error_stream == "stdout" else "")
        ),
        stderr=error_diagnostic if error_stream == "stderr" else "",
    )
    with pytest.raises(AssertionError):
        skip_exact_npm_cold_cache_miss(result, kind)


def npm_debug_logs(project: Path) -> list[Path]:
    """Return npm debug logs created below an isolated fixture project."""

    return list((project / ".npm-cache").glob("_logs/*"))


def run_lock_manifest_validator(
    node: Path,
    project: Path,
    *,
    lock: Path | None = None,
    manifests: list[Path] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run only the local manifest/lock preflight with explicit paths."""

    if manifests is None:
        manifests = [
            project / "package.json",
            project / "apps/web/package.json",
            project / "packages/web-contracts/package.json",
            project / "packages/web-ui/package.json",
        ]
    return subprocess.run(
        [
            str(node),
            str(project / "scripts/node_inventory.mjs"),
            "verify-lock-manifests",
            str(lock or project / "package-lock.json"),
            *(str(manifest) for manifest in manifests),
        ],
        cwd=project,
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )


def run_python_runtime_validator(
    node: Path,
    venv_root: Path,
    *,
    bin_directory: Path | None = None,
    python_path: Path | None = None,
    expected_version: str = "3.14.6",
) -> subprocess.CompletedProcess[str]:
    """Run only the fail-closed interpreter identity preflight."""

    bin_path = bin_directory or venv_root / "bin"
    interpreter = python_path or bin_path / "python"
    return subprocess.run(
        [
            str(node),
            str(REPOSITORY_ROOT / "scripts/node_inventory.mjs"),
            "verify-python-runtime",
            str(venv_root),
            str(bin_path),
            str(interpreter),
            expected_version,
        ],
        cwd=REPOSITORY_ROOT,
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )


def make_runtime_fixture(root: Path) -> Path:
    """Create a minimal uv-style venv path around the hydrated CPython."""

    source_venv = REPOSITORY_ROOT / ".venv"
    source_python = source_venv / "bin/python"
    if not source_python.exists():
        pytest.skip("the exact Python environment is not hydrated")
    venv_root = root / ".venv"
    (venv_root / "bin").mkdir(parents=True)
    shutil.copy2(source_venv / "pyvenv.cfg", venv_root / "pyvenv.cfg")
    (venv_root / "bin/python").symlink_to(source_python.resolve(strict=True))
    return venv_root


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
    skip_exact_npm_cold_cache_miss(result, "online-fetch")
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
    assert not marker.exists()
    skip_exact_npm_cold_cache_miss(result, "online-fetch")
    assert result.returncode == 0, diagnostics(result)


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
    assert not marker.exists()
    skip_exact_npm_cold_cache_miss(result, "online-fetch")
    assert result.returncode == 0, diagnostics(result)


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
        "package manifest metadata does not match package-lock.json: "
        "package.json:devDependencies" in diagnostics(result)
    )
    assert not npm_debug_logs(project)


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
    assert (
        "package manifest metadata does not match package-lock.json: "
        "package.json:devDependencies" in diagnostics(result)
    )
    assert not npm_debug_logs(project)


@pytest.mark.parametrize("command", ["lock-check", "sync"])
def test_lock_preflight_rejects_a_deliberately_stale_manifest(
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
    assert (
        "package manifest metadata does not match package-lock.json: "
        "package.json:devDependencies" in diagnostics(result)
    )
    assert not npm_debug_logs(project)


def test_lock_manifest_validator_accepts_the_committed_metadata(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / "valid-lock-manifests"
    copy_node_project(project)

    result = run_lock_manifest_validator(node, project)

    assert result.returncode == 0, diagnostics(result)
    assert not npm_debug_logs(project)


@pytest.mark.parametrize(
    ("field", "stale_value"),
    [("name", "stale-root-name"), ("version", "999.0.0")],
)
def test_lock_manifest_validator_rejects_stale_top_level_identity(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    field: str,
    stale_value: str,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / f"stale-top-{field}"
    copy_node_project(project)
    lock_path = project / "package-lock.json"
    lock: dict[str, Any] = json.loads(lock_path.read_text(encoding="utf-8"))
    lock[field] = stale_value
    lock_path.write_text(f"{json.dumps(lock, indent=2)}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode != 0, diagnostics(result)
    assert (
        f"package-lock.json top-level identity does not match root package manifest: {field}"
        in diagnostics(result)
    )
    assert not npm_debug_logs(project)


@pytest.mark.parametrize("operation", ["missing", "extra"])
def test_lock_manifest_validator_rejects_nonexact_top_level_keys(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    operation: str,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / f"top-keys-{operation}"
    copy_node_project(project)
    lock_path = project / "package-lock.json"
    lock: dict[str, Any] = json.loads(lock_path.read_text(encoding="utf-8"))
    if operation == "missing":
        del lock["name"]
    else:
        lock["unexpected"] = True
    lock_path.write_text(f"{json.dumps(lock, indent=2)}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode != 0, diagnostics(result)
    assert (
        "package-lock.json top-level keys do not match the fixed v3 contract: "
        "package-lock.json" in diagnostics(result)
    )
    assert not npm_debug_logs(project)


@pytest.mark.parametrize("operation", ["false", "missing"])
def test_lock_manifest_validator_requires_the_exact_requires_flag(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    operation: str,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / f"requires-{operation}"
    copy_node_project(project)
    lock_path = project / "package-lock.json"
    lock: dict[str, Any] = json.loads(lock_path.read_text(encoding="utf-8"))
    if operation == "missing":
        del lock["requires"]
    else:
        lock["requires"] = False
    lock_path.write_text(f"{json.dumps(lock, indent=2)}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode != 0, diagnostics(result)
    assert "package-lock.json requires must be true: package-lock.json" in diagnostics(
        result
    )
    assert not npm_debug_logs(project)


@pytest.mark.parametrize(
    "location",
    [
        "apps/stale",
        "../node_modules/package",
        "node_modules/../package",
        "node_modules/./package",
        "node_modules//package",
        "node_modules/package/",
        r"node_modules\package",
        "node_modules/package/lib",
        "node_modules",
        "node_modules/node_modules",
        "node_modules/@scope",
        "node_modules/@scope/node_modules",
        "node_modules/@/package",
        "node_modules/package/node_modules",
        "node_modules/@scope/@package",
    ],
)
def test_lock_manifest_validator_rejects_noncanonical_package_locations(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    location: str,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / "noncanonical-package-location"
    copy_node_project(project)
    lock_path = project / "package-lock.json"
    lock: dict[str, Any] = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock["packages"]
    assert isinstance(packages, dict)
    packages[location] = {}
    lock_path.write_text(f"{json.dumps(lock, indent=2)}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode != 0, diagnostics(result)
    assert "package-lock.json contains a noncanonical package location" in diagnostics(
        result
    )
    assert not npm_debug_logs(project)


@pytest.mark.parametrize(
    "location",
    [
        "node_modules/package.with-punctuation",
        "node_modules/@scope/package_name",
        "node_modules/parent/node_modules/child",
        "node_modules/@scope/parent/node_modules/@nested/child",
    ],
)
def test_lock_manifest_validator_accepts_canonical_package_locations(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    location: str,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / "canonical-package-location"
    copy_node_project(project)
    lock_path = project / "package-lock.json"
    lock: dict[str, Any] = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock["packages"]
    assert isinstance(packages, dict)
    packages[location] = {}
    lock_path.write_text(f"{json.dumps(lock, indent=2)}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode == 0, diagnostics(result)
    assert not npm_debug_logs(project)


def test_lock_manifest_validator_rejects_a_nonobject_package_entry(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / "invalid-package-entry"
    copy_node_project(project)
    lock_path = project / "package-lock.json"
    lock: dict[str, Any] = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock["packages"]
    assert isinstance(packages, dict)
    packages["node_modules/prettier"] = "not-an-object"
    lock_path.write_text(f"{json.dumps(lock, indent=2)}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode != 0, diagnostics(result)
    assert (
        "package-lock.json package entries must have string keys and object values"
        in diagnostics(result)
    )
    assert not npm_debug_logs(project)


@pytest.mark.parametrize(
    ("relative", "field", "operation"),
    [
        ("package.json", "license", "remove"),
        ("packages/web-ui/package.json", "license", "add"),
        ("apps/web/package.json", "dependencies", "change"),
    ],
)
def test_lock_manifest_validator_rejects_added_removed_or_changed_metadata(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    relative: str,
    field: str,
    operation: str,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / f"metadata-{operation}"
    copy_node_project(project)
    manifest_path = project / relative
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if operation == "remove":
        del manifest[field]
    elif operation == "add":
        manifest[field] = "UNLICENSED"
    else:
        dependencies = manifest[field]
        assert isinstance(dependencies, dict)
        dependencies["react"] = "19.2.7"
    manifest_path.write_text(f"{json.dumps(manifest, indent=2)}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode != 0, diagnostics(result)
    assert (
        f"package manifest metadata does not match package-lock.json: {relative}:{field}"
        in diagnostics(result)
    )
    assert not npm_debug_logs(project)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bundleDependencies", ["prettier"]),
        ("bundledDependencies", ["prettier"]),
        ("acceptDependencies", {"prettier": "3.9.6"}),
        ("funding", "https://example.invalid/funding"),
        ("os", ["linux"]),
        ("cpu", ["x64"]),
        ("libc", ["glibc"]),
        ("bin", "cli.mjs"),
        ("deprecated", "fixture only"),
    ],
)
def test_lock_manifest_validator_rejects_unsupported_lock_metadata(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / f"unsupported-{field}"
    copy_node_project(project)
    manifest_path = project / "package.json"
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = value
    manifest_path.write_text(f"{json.dumps(manifest, indent=2)}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode != 0, diagnostics(result)
    assert (
        f"unsupported package manifest lock metadata: package.json:{field}"
        in diagnostics(result)
    )
    assert not npm_debug_logs(project)


@pytest.mark.parametrize("script", ["preinstall", "install", "postinstall"])
def test_lock_manifest_validator_projects_install_scripts_to_the_lock_bit(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    script: str,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / f"install-script-{script}"
    copy_node_project(project)
    manifest_path = project / "package.json"
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    scripts = manifest.setdefault("scripts", {})
    assert isinstance(scripts, dict)
    scripts[script] = 'node -e ""'
    manifest_path.write_text(f"{json.dumps(manifest, indent=2)}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode != 0, diagnostics(result)
    assert (
        "package manifest metadata does not match package-lock.json: "
        "package.json:hasInstallScript" in diagnostics(result)
    )
    assert not npm_debug_logs(project)


@pytest.mark.parametrize("script", ["preinstall", "install", "postinstall"])
def test_lock_manifest_validator_accepts_a_matching_derived_install_script_bit(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    script: str,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / f"matching-install-script-{script}"
    copy_node_project(project)
    manifest_path = project / "package.json"
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    scripts = manifest.setdefault("scripts", {})
    assert isinstance(scripts, dict)
    scripts[script] = 'node -e ""'
    manifest_path.write_text(f"{json.dumps(manifest, indent=2)}\n", encoding="utf-8")

    lock_path = project / "package-lock.json"
    lock: dict[str, Any] = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock["packages"]
    assert isinstance(packages, dict)
    root_entry = packages[""]
    assert isinstance(root_entry, dict)
    root_entry["hasInstallScript"] = True
    lock_path.write_text(f"{json.dumps(lock, indent=2)}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode == 0, diagnostics(result)
    assert not npm_debug_logs(project)


@pytest.mark.parametrize(
    ("scripts", "diagnostic"),
    [
        (None, "package scripts must be an object: package.json:scripts"),
        ([], "package scripts must be an object: package.json:scripts"),
        ({"install": None}, "package.json:scripts.install"),
        ({"postinstall": ""}, "package.json:scripts.postinstall"),
    ],
)
def test_lock_manifest_validator_rejects_ambiguous_lifecycle_script_shapes(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    scripts: object,
    diagnostic: str,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / "invalid-lifecycle-shape"
    copy_node_project(project)
    manifest_path = project / "package.json"
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scripts"] = scripts
    manifest_path.write_text(f"{json.dumps(manifest, indent=2)}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode != 0, diagnostics(result)
    assert diagnostic in diagnostics(result)
    assert not npm_debug_logs(project)


def test_lock_manifest_validator_rejects_raw_has_install_script_metadata(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / "raw-install-script-bit"
    copy_node_project(project)
    manifest_path = project / "package.json"
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["hasInstallScript"] = True
    manifest_path.write_text(f"{json.dumps(manifest, indent=2)}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode != 0, diagnostics(result)
    assert (
        "unsupported package manifest lock metadata: package.json:hasInstallScript"
        in diagnostics(result)
    )
    assert not npm_debug_logs(project)


def test_lock_manifest_validator_rejects_stale_derived_and_unsupported_lock_metadata(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / "stale-lock-metadata"
    copy_node_project(project)
    lock_path = project / "package-lock.json"
    lock: dict[str, Any] = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock["packages"]
    assert isinstance(packages, dict)
    root_entry = packages[""]
    assert isinstance(root_entry, dict)
    root_entry["hasInstallScript"] = True
    lock_path.write_text(f"{json.dumps(lock, indent=2)}\n", encoding="utf-8")

    derived = run_lock_manifest_validator(node, project)
    assert derived.returncode != 0, diagnostics(derived)
    assert "package.json:hasInstallScript" in diagnostics(derived)

    del root_entry["hasInstallScript"]
    root_entry["funding"] = {"url": "https://example.invalid/funding"}
    lock_path.write_text(f"{json.dumps(lock, indent=2)}\n", encoding="utf-8")

    unsupported = run_lock_manifest_validator(node, project)
    assert unsupported.returncode != 0, diagnostics(unsupported)
    assert "unsupported package-lock metadata: package.json:funding" in diagnostics(
        unsupported
    )
    assert not npm_debug_logs(project)


@pytest.mark.parametrize("target", ["package-lock.json", "apps/web/package.json"])
def test_lock_manifest_validator_rejects_malformed_json(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
    target: str,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / "malformed-lock-manifests"
    copy_node_project(project)
    (project / target).write_text("{not-json}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode != 0, diagnostics(result)
    assert "invalid JSON object:" in diagnostics(result)
    assert not npm_debug_logs(project)


def test_lock_manifest_validator_rejects_a_missing_lock_entry(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / "missing-lock-entry"
    copy_node_project(project)
    lock_path = project / "package-lock.json"
    lock: dict[str, Any] = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock["packages"]
    assert isinstance(packages, dict)
    del packages["apps/web"]
    lock_path.write_text(f"{json.dumps(lock, indent=2)}\n", encoding="utf-8")

    result = run_lock_manifest_validator(node, project)

    assert result.returncode != 0, diagnostics(result)
    assert (
        "package-lock.json entry is missing or invalid: apps/web/package.json"
        in diagnostics(result)
    )
    assert not npm_debug_logs(project)


def test_lock_manifest_validator_rejects_relative_outside_and_duplicate_manifests(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / "unsafe-lock-manifest-paths"
    copy_node_project(project)
    valid = [
        project / "package.json",
        project / "apps/web/package.json",
        project / "packages/web-contracts/package.json",
        project / "packages/web-ui/package.json",
    ]

    relative = run_lock_manifest_validator(
        node,
        project,
        manifests=[Path("package.json"), *valid[1:]],
    )
    assert relative.returncode != 0, diagnostics(relative)
    assert "lock manifest path must be absolute" in diagnostics(relative)

    outside_manifest = tmp_path / "package.json"
    outside_manifest.write_text("{}\n", encoding="utf-8")
    outside = run_lock_manifest_validator(
        node,
        project,
        manifests=[outside_manifest, *valid[1:]],
    )
    assert outside.returncode != 0, diagnostics(outside)
    assert "package manifest escapes package-lock.json root" in diagnostics(outside)

    duplicate = run_lock_manifest_validator(
        node,
        project,
        manifests=[valid[0], valid[1], valid[2], valid[2]],
    )
    assert duplicate.returncode != 0, diagnostics(duplicate)
    assert "duplicate package manifest key: packages/web-contracts" in diagnostics(
        duplicate
    )


def test_lock_manifest_validator_rejects_symlink_and_wrong_lock_basename(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, _ = exact_node_toolchain
    project = tmp_path / "unsafe-lock-files"
    copy_node_project(project)
    manifest = project / "apps/web/package.json"
    target = tmp_path / "outside-web-package.json"
    shutil.copy2(manifest, target)
    manifest.unlink()
    try:
        manifest.symlink_to(target)
    except OSError as error:
        pytest.skip(f"file symlinks are unavailable: {error}")

    symlink = run_lock_manifest_validator(node, project)
    assert symlink.returncode != 0, diagnostics(symlink)
    assert "regular non-symlink file" in diagnostics(symlink)

    manifest.unlink()
    shutil.copy2(target, manifest)
    wrong_lock = project / "not-the-package-lock.json"
    shutil.copy2(project / "package-lock.json", wrong_lock)
    wrong_basename = run_lock_manifest_validator(node, project, lock=wrong_lock)
    assert wrong_basename.returncode != 0, diagnostics(wrong_basename)
    assert "lock manifest filename must be package-lock.json" in diagnostics(
        wrong_basename
    )
    assert not npm_debug_logs(project)


def test_python_runtime_validator_accepts_the_exact_hydrated_environment(
    exact_node_toolchain: tuple[Path, Path],
) -> None:
    node, _ = exact_node_toolchain

    result = run_python_runtime_validator(node, REPOSITORY_ROOT / ".venv")

    assert result.returncode == 0, diagnostics(result)
    assert result.stdout == ""
    assert result.stderr == ""


def test_python_runtime_validator_rejects_missing_and_symlinked_directories(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, _ = exact_node_toolchain

    missing = run_python_runtime_validator(node, tmp_path / "missing/.venv")
    assert missing.returncode != 0, diagnostics(missing)
    assert "Python runtime path must be a real directory: .venv" in diagnostics(missing)

    physical_root = tmp_path / "physical/.venv"
    physical_root.mkdir(parents=True)
    linked_root = tmp_path / "linked/.venv"
    linked_root.parent.mkdir()
    try:
        linked_root.symlink_to(physical_root, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")
    root_symlink = run_python_runtime_validator(node, linked_root)
    assert root_symlink.returncode != 0, diagnostics(root_symlink)
    assert "Python runtime path must be a real directory: .venv" in diagnostics(
        root_symlink
    )

    venv_root = tmp_path / "bin-link/.venv"
    venv_root.mkdir(parents=True)
    physical_bin = tmp_path / "physical-bin"
    physical_bin.mkdir()
    (venv_root / "bin").symlink_to(physical_bin, target_is_directory=True)
    bin_symlink = run_python_runtime_validator(node, venv_root)
    assert bin_symlink.returncode != 0, diagnostics(bin_symlink)
    assert "Python runtime path must be a real directory: .venv/bin" in diagnostics(
        bin_symlink
    )


def test_python_runtime_validator_rejects_nonexecutable_and_wrong_runtime(
    exact_node_toolchain: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    node, _ = exact_node_toolchain
    venv_root = make_runtime_fixture(tmp_path / "nonexecutable")
    python_path = venv_root / "bin/python"
    python_path.unlink()
    python_path.write_text("not executable\n", encoding="utf-8")
    python_path.chmod(0o600)

    nonexecutable = run_python_runtime_validator(node, venv_root)
    assert nonexecutable.returncode != 0, diagnostics(nonexecutable)
    assert "Python runtime resolved target must be executable" in diagnostics(
        nonexecutable
    )

    wrong_root = make_runtime_fixture(tmp_path / "wrong-runtime")
    wrong_python = wrong_root / "bin/python"
    wrong_python.unlink()
    wrong_python.write_text(
        "#!/bin/sh\nprintf '%s\\n' "
        '\'{"implementation":"NotCPython","prefix":"wrong","version":"3.14.6"}\'\n',
        encoding="utf-8",
    )
    wrong_python.chmod(0o700)

    wrong_runtime = run_python_runtime_validator(node, wrong_root)
    assert wrong_runtime.returncode != 0, diagnostics(wrong_runtime)
    assert "required Python runtime identity does not match" in diagnostics(
        wrong_runtime
    )


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
    generated_lock: dict[str, Any] = json.loads(
        (project / "package-lock.json").read_text(encoding="utf-8")
    )
    generated_packages = generated_lock["packages"]
    assert isinstance(generated_packages, dict)
    generated_root = generated_packages[""]
    assert isinstance(generated_root, dict)
    assert generated_root["hasInstallScript"] is True

    logs_before_projection = set(npm_debug_logs(project))
    projected = run_lock_manifest_validator(node, project)
    assert projected.returncode == 0, diagnostics(projected)
    assert set(npm_debug_logs(project)) == logs_before_projection

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
    assert not list(REPOSITORY_ROOT.glob(".node-offline-check.*"))
    skip_exact_npm_cold_cache_miss(result, "offline-replay")
    assert result.returncode == 0, diagnostics(result)


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
