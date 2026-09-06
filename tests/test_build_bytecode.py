"""Build entrypoints must not contaminate generated output with import caches."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_build_imports(tmp_path: Path) -> tuple[list[str], Path]:
    if sys.platform != "linux" or shutil.which("bwrap") is None:
        pytest.skip("Linux bubblewrap is required for the read-only host probe")

    # Copy tracked inputs only. Existing host caches and user files stay outside
    # the writable mounts; no generator or cleanup runs against the checkout.
    directories = ("scripts", "python/raos/generated")
    for directory in directories:
        (tmp_path / directory).mkdir(parents=True)
        tracked = subprocess.check_output(
            ["git", "ls-files", "-z", "--", directory], cwd=ROOT
        ).decode()
        for name in filter(None, tracked.split("\0")):
            source = ROOT / name
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    (tmp_path / "home").mkdir()
    command = [
        "bwrap",
        "--die-with-parent",
        "--unshare-net",
        "--clearenv",
        "--ro-bind",
        "/",
        "/",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--bind",
        str(tmp_path),
        str(tmp_path),
        "--setenv",
        "HOME",
        str(tmp_path / "home"),
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--chdir",
        str(ROOT),
    ]
    for directory in directories:
        command.extend(("--bind", str(tmp_path / directory), str(ROOT / directory)))
    return command, tmp_path


def test_make_generate_imports_do_not_create_bytecode(
    isolated_build_imports: tuple[list[str], Path],
) -> None:
    command, scratch = isolated_build_imports
    launcher = scratch / "python-import-probe"
    trace = scratch / "entries.txt"
    launcher.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$1\" >> '{trace}'\n"
        f"exec '{sys.executable}' \"$1\" --help\n"
    )
    launcher.chmod(0o755)

    # Use the actual Makefile's recipe environment and actual script imports,
    # replacing each generation action with its non-mutating help entrypoint.
    result = subprocess.run(
        [*command, "make", "--no-print-directory", f"PYTHON={launcher}", "generate"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert trace.read_text().splitlines() == [
        "scripts/raos_editorial_portfolio_v2.py",
        "scripts/raos_build.py",
        "scripts/status_v2.py",
    ]
    assert not list((scratch / "python/raos/generated").rglob("*.pyc"))
    assert not list((scratch / "scripts").rglob("__pycache__"))


@pytest.mark.parametrize("arguments", [("--help",), ("plan", "--json")])
def test_direct_build_entry_does_not_create_bytecode(
    isolated_build_imports: tuple[list[str], Path], arguments: tuple[str, ...]
) -> None:
    command, scratch = isolated_build_imports
    result = subprocess.run(
        [
            *command,
            sys.executable,
            str(ROOT / "scripts/raos_build.py"),
            *arguments,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout
    assert not list((scratch / "scripts").rglob("__pycache__"))
    assert not list((scratch / "python/raos/generated").rglob("*.pyc"))
