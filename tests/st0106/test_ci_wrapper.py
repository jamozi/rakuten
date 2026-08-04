"""Adversarial checks for the exact-tool local CI job wrapper."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = REPOSITORY_ROOT / "scripts/ci_job.sh"
NETWORK_WRAPPER = REPOSITORY_ROOT / "scripts/run_network_denied.sh"
NETWORK_ASSERTION = REPOSITORY_ROOT / "scripts/assert_network_denied.py"
OUTER_NETWORK_SANDBOX = os.environ.get("RAOS_NETWORK_DENIED") == "1"
UNSANDBOXED_PARENT_REASON = (
    "requires an unsandboxed parent so ci_job.sh can enter and verify a fresh "
    "network/PID namespace; the outer ci-network-assert already reasserts its guard"
)
requires_unsandboxed_parent = pytest.mark.skipif(
    OUTER_NETWORK_SANDBOX,
    reason=UNSANDBOXED_PARENT_REASON,
)


def write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def make_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    repository = tmp_path / "repository with spaces"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(WRAPPER, scripts / "ci_job.sh")
    shutil.copy2(NETWORK_WRAPPER, scripts / "run_network_denied.sh")
    shutil.copy2(NETWORK_ASSERTION, scripts / "assert_network_denied.py")

    home = tmp_path / "home"
    home.mkdir()
    makefile = """\
.PHONY: ci-hydrate ci-static ci-unit ci-contracts
ci-hydrate:
	@:
ci-static:
\t@printf 'static\\n' > "$(HOME)/observed-job"
ci-unit:
\t@printf 'unit\\n' > "$(HOME)/observed-job"
ci-contracts:
\t@printf 'contracts\\n' > "$(HOME)/observed-job"
"""
    (repository / "Makefile").write_text(makefile, encoding="utf-8")

    tool_root = tmp_path / "tools"
    uv = tool_root / "uv" / "uv"
    write_executable(
        uv,
        "#!/bin/sh\n"
        'test "$#" -eq 1 && test "$1" = --version || exit 91\n'
        "printf 'uv 0.12.1\\n'\n",
    )
    node = tool_root / "node" / "bin" / "node"
    write_executable(
        node,
        "#!/bin/sh\n"
        'if test "${NODE_OPTIONS+x}${npm_config_ignore_scripts+x}'
        '${NPM_CONFIG_IGNORE_SCRIPTS+x}" != ""; then\n'
        "  exit 93\n"
        "fi\n"
        'if test "$#" -eq 1 && test "$1" = --version; then\n'
        "  printf 'v24.18.1\\n'\n"
        'elif test "$#" -eq 2 && test "$2" = --version; then\n'
        "  printf '11.16.0\\n'\n"
        "else\n"
        "  exit 92\n"
        "fi\n",
    )
    npm_cli = tool_root / "node/lib/node_modules/npm/bin/npm-cli.js"
    npm_cli.parent.mkdir(parents=True)
    npm_cli.write_text("// exact bundled fixture\n", encoding="utf-8")
    return repository / "scripts/ci_job.sh", uv, node, npm_cli, home


def run_wrapper(
    wrapper: Path,
    uv: Path,
    node: Path,
    npm_cli: Path,
    home: Path,
    job: str,
    *,
    extra_environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = {
        "PATH": os.defpath,
        "HOME": str(home),
    }
    if extra_environment:
        environment.update(extra_environment)
    return subprocess.run(
        [
            str(wrapper),
            "--uv",
            str(uv),
            "--node",
            str(node),
            "--npm-cli",
            str(npm_cli),
            job,
        ],
        cwd=home,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )


def test_repository_wrapper_is_executable_and_syntax_valid() -> None:
    assert WRAPPER.is_file() and not WRAPPER.is_symlink()
    assert os.access(WRAPPER, os.X_OK)
    result = subprocess.run(
        ["bash", "-n", str(WRAPPER)],
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    content = WRAPPER.read_text(encoding="utf-8")
    assert content.startswith("#!/bin/bash -p\n\nPATH=/usr/bin:/bin")
    assert "env -i" in content
    assert "ci-hydrate" not in content
    assert "dependency-hydration" not in content
    assert "RAOS_CI_OFFLINE=1" in content
    assert "RAOS_NETWORK_DENIED" in content
    assert '/usr/bin/python3 -I "$network_assertion"' in content
    assert "run_network_denied.sh" in content
    assert "required uv version ==0.12.1" in content
    assert "required Node version ==24.18.1" in content
    assert "required npm version ==11.16.0" in content
    assert "npm CLI is not bundled with the selected Node" in content
    assert "--no-builtin-rules --no-builtin-variables" in content


@requires_unsandboxed_parent
@pytest.mark.parametrize("job", ["static", "unit", "contracts"])
def test_wrapper_maps_each_fixed_job_to_one_make_target(
    tmp_path: Path, job: str
) -> None:
    wrapper, uv, node, npm_cli, home = make_fixture(tmp_path)
    result = run_wrapper(wrapper, uv, node, npm_cli, home, job)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert (home / "observed-job").read_text(encoding="utf-8") == f"{job}\n"


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--uv", "relative", "--node", "/bin/false", "--npm-cli", "/x", "unit"],
        [
            "--uv",
            "/bin/false",
            "--node",
            "/bin/false",
            "--npm-cli",
            "/bin/false",
            "unknown",
        ],
        [
            "--uv",
            "/bin/false",
            "--node",
            "/bin/false",
            "--npm-cli",
            "/bin/false",
            "unit",
            "extra",
        ],
    ],
)
def test_wrapper_rejects_invalid_or_extended_cli(arguments: list[str]) -> None:
    result = subprocess.run(
        [str(WRAPPER), *arguments],
        cwd=REPOSITORY_ROOT,
        env={"PATH": os.defpath, "HOME": str(REPOSITORY_ROOT)},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode != 0
    assert "usage:" in result.stderr.lower() or "error:" in result.stderr.lower()


def test_wrapper_rejects_wrong_uv_before_make(tmp_path: Path) -> None:
    wrapper, uv, node, npm_cli, home = make_fixture(tmp_path)
    uv.write_text("#!/bin/sh\nprintf 'uv 0.12.0\\n'\n", encoding="utf-8")
    result = run_wrapper(wrapper, uv, node, npm_cli, home, "unit")
    assert result.returncode != 0
    assert "required uv version ==0.12.1" in result.stderr
    assert not (home / "observed-job").exists()


def test_wrapper_rejects_unbundled_npm_lookalike(tmp_path: Path) -> None:
    wrapper, uv, node, _, home = make_fixture(tmp_path)
    npm_cli = tmp_path / "npm-cli.js"
    npm_cli.write_text("// lookalike\n", encoding="utf-8")
    result = run_wrapper(wrapper, uv, node, npm_cli, home, "static")
    assert result.returncode != 0
    assert "not bundled" in result.stderr
    assert not (home / "observed-job").exists()


@requires_unsandboxed_parent
def test_wrapper_canonicalizes_safe_tool_symlink_arguments(tmp_path: Path) -> None:
    wrapper, uv, node, npm_cli, home = make_fixture(tmp_path)
    links = tmp_path / "tool links"
    links.mkdir()
    linked_uv = links / "uv"
    linked_node = links / "node"
    linked_npm_cli = links / "npm-cli.js"
    try:
        linked_uv.symlink_to(uv)
        linked_node.symlink_to(node)
        linked_npm_cli.symlink_to(npm_cli)
    except OSError:
        pytest.skip("symlinks are not supported")

    result = run_wrapper(
        wrapper,
        linked_uv,
        linked_node,
        linked_npm_cli,
        home,
        "unit",
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert (home / "observed-job").read_text(encoding="utf-8") == "unit\n"


@requires_unsandboxed_parent
def test_wrapper_removes_shell_make_node_and_npm_injection(tmp_path: Path) -> None:
    wrapper, uv, node, npm_cli, home = make_fixture(tmp_path)
    startup_marker = tmp_path / "startup-ran"
    preload_marker = tmp_path / "preload-ran"
    node_marker = tmp_path / "node-ran"
    startup = tmp_path / "startup.sh"
    startup.write_text(f"touch {startup_marker}\n", encoding="utf-8")
    preload = tmp_path / "preload.mk"
    preload.write_text(
        f"PRELOAD := $(shell touch {preload_marker})\n", encoding="utf-8"
    )
    result = run_wrapper(
        wrapper,
        uv,
        node,
        npm_cli,
        home,
        "contracts",
        extra_environment={
            "BASH_ENV": str(startup),
            "MAKEFILES": str(preload),
            "MAKEFLAGS": "--eval=.IGNORE:",
            "NODE_OPTIONS": f"--require={node_marker}",
            "npm_config_ignore_scripts": "false",
            "NPM_CONFIG_IGNORE_SCRIPTS": "false",
        },
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert not startup_marker.exists()
    assert not preload_marker.exists()
    assert not node_marker.exists()
    assert (home / "observed-job").read_text(encoding="utf-8") == "contracts\n"
