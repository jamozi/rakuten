"""Dynamic no-write and no-network checks for the ST-0105 wrapper."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from typing import Final

import pytest

from conftest import REPOSITORY_ROOT


SNAPSHOT_ROOTS = (
    ".venv",
    "node_modules",
    ".npm-cache",
    ".pytest_cache",
    "python/raos/generated",
    "packages/web-contracts/src/generated",
    "changes/st-0105/manifest.json",
)
UV: Final = Path("/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv")
TRANSACTION_NAMES: Final = (
    ".install-transaction.v1",
    ".install-transaction.v1.preparing",
    ".install-transaction.v1.cleanup",
)


def exact_toolchain(node_executable: Path) -> tuple[Path, Path]:
    npm_cli = node_executable.parent.parent / "lib/node_modules/npm/bin/npm-cli.js"
    if not UV.is_file() or not npm_cli.is_file():
        pytest.skip("exact local uv/Node/npm toolchain is unavailable")
    return UV, npm_cli


def wrapper_command(
    node_executable: Path,
    command: str,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> list[str]:
    uv, npm_cli = exact_toolchain(node_executable)
    return [
        str(repository_root / "scripts/codegen_toolchain.sh"),
        "--uv",
        str(uv),
        "--node",
        str(node_executable),
        "--npm-cli",
        str(npm_cli),
        command,
    ]


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def build_recovery_probe_repository(root: Path) -> None:
    files = (
        ".npmrc",
        "Makefile",
        "package.json",
        "pyproject.toml",
        "uv.lock",
        "uv.toml",
        "apps/web/package.json",
        "packages/web-contracts/package.json",
        "packages/web-contracts/tsconfig.json",
        "packages/web-ui/package.json",
        "python/raos/__init__.py",
        "python/raos/shared/__init__.py",
        "python/raos/shared/contract_repository.py",
        "scripts/build_st0105_generated_contracts.py",
        "scripts/codegen_toolchain.sh",
        "scripts/node_inventory.mjs",
    )
    for relative in files:
        source = REPOSITORY_ROOT / relative
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    shutil.copytree(
        REPOSITORY_ROOT / ".venv",
        root / ".venv",
        symlinks=True,
        copy_function=shutil.copy2,
    )
    for relative in (
        ".npm-cache",
        "node_modules",
        "packages/web-contracts/src",
        "changes/st-0105",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)


def repository_state() -> dict[str, tuple[int, int, int, str | None]]:
    result: dict[str, tuple[int, int, int, str | None]] = {}
    for relative in SNAPSHOT_ROOTS:
        root = REPOSITORY_ROOT / relative
        paths = [root]
        if root.is_dir() and not root.is_symlink():
            paths.extend(sorted(root.rglob("*")))
        for path in paths:
            if not path.exists() and not path.is_symlink():
                continue
            metadata = path.lstat()
            key = path.relative_to(REPOSITORY_ROOT).as_posix()
            result[key] = (
                stat.S_IFMT(metadata.st_mode),
                metadata.st_size,
                metadata.st_mtime_ns,
                os.readlink(path) if path.is_symlink() else None,
            )
    return result


def test_wrapper_check_is_repository_read_only_and_opens_no_ip_socket(
    tmp_path: Path, node_executable: Path
) -> None:
    strace = shutil.which("strace")
    if strace is None:
        pytest.skip("strace is unavailable")
    command = wrapper_command(node_executable, "check")
    trace = tmp_path / "network.trace"
    before = repository_state()
    process = subprocess.run(
        [
            strace,
            "-f",
            "-qq",
            "-e",
            "trace=network",
            "-o",
            str(trace),
            *command,
        ],
        cwd=REPOSITORY_ROOT,
        env={
            "PATH": os.defpath,
            "HOME": str(Path.home()),
            "BASH_ENV": str(tmp_path / "must-not-run"),
            "ENV": str(tmp_path / "must-not-run"),
            "MAKEFILES": str(tmp_path / "must-not-load.mk"),
            "MAKEFLAGS": "-i -n",
            "NODE_OPTIONS": "--require=/must-not-load.js",
            "UV_INDEX_URL": "https://example.invalid/simple",
            "npm_config_registry": "https://example.invalid/",
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    after = repository_state()
    assert process.returncode == 0, f"{process.stdout}\n{process.stderr}"
    assert before == after
    network_calls = trace.read_text(encoding="utf-8", errors="replace")
    assert "socket(AF_INET," not in network_calls
    assert "socket(AF_INET6," not in network_calls
    assert "sa_family=AF_INET," not in network_calls
    assert "sa_family=AF_INET6," not in network_calls


def test_wrapper_install_recovers_pending_preparing_transaction(
    node_executable: Path,
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="raos-st0105-wrapper-recovery-"
    ) as temporary:
        isolated_root = Path(temporary) / "repository"
        build_recovery_probe_repository(isolated_root)
        command = wrapper_command(
            node_executable, "install", repository_root=isolated_root
        )
        transaction_parent = isolated_root / "changes/st-0105"
        pending = [transaction_parent / name for name in TRANSACTION_NAMES]
        assert not [path for path in pending if path.exists() or path.is_symlink()]
        before = repository_state()
        preparing = transaction_parent / TRANSACTION_NAMES[1]
        preparing.mkdir(mode=0o700)
        fsync_directory(transaction_parent)
        process = subprocess.run(
            command,
            cwd=isolated_root,
            env={
                "PATH": os.defpath,
                "HOME": str(Path.home()),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        assert process.returncode == 2, f"{process.stdout}\n{process.stderr}"
        assert "openapi-ts entrypoint has an unsafe or missing" in process.stderr
        assert not [path for path in pending if path.exists() or path.is_symlink()]
        assert not (isolated_root / "changes/st-0105/manifest.json").exists()
        assert not (isolated_root / "python/raos/generated").exists()
        assert not (isolated_root / "packages/web-contracts/src/generated").exists()
        assert repository_state() == before
