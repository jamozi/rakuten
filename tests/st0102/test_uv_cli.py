"""uv lock checks at the setup/final boundary."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from .support import REPOSITORY_ROOT, local_uv_binaries, uv_environment


LOCK_INPUTS = (".python-version", "pyproject.toml", "uv.toml", "uv.lock")


def run_lock_check(binary: Path, project: Path, cache: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(binary), "lock", "--check"],
        cwd=project,
        env=uv_environment(cache),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def compatible_uv() -> Path:
    candidates = [
        binary for binary, version in local_uv_binaries() if version.startswith("0.12.")
    ]
    assert candidates, "a compatible uv 0.12.x binary is required"
    return candidates[0]


def test_compatible_uv_accepts_the_committed_lock(tmp_path: Path) -> None:
    result = run_lock_check(compatible_uv(), REPOSITORY_ROOT, tmp_path / "cache")
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_lock_check_rejects_project_drift(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    for relative in LOCK_INPUTS:
        shutil.copy2(REPOSITORY_ROOT / relative, project / relative)
    pyproject = project / "pyproject.toml"
    original = pyproject.read_text(encoding="utf-8")
    changed = original.replace('  "types-pyyaml==6.0.12.20260724",\n', "", 1)
    assert changed != original
    pyproject.write_text(changed, encoding="utf-8")

    result = run_lock_check(compatible_uv(), project, tmp_path / "cache")
    assert result.returncode != 0
    diagnostic = f"{result.stdout}\n{result.stderr}".lower()
    assert "lock" in diagnostic or "network was disabled" in diagnostic


def test_uv_version_range_is_checked_once_by_setup_and_final() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "verify_dev_toolchain.py" in makefile.split("setup:", 1)[1].split("\n\n", 1)[0]
    assert "verify_dev_toolchain.py" in makefile.split("final-lock:", 1)[1].split("\n\n", 1)[0]
    for target in ("generate", "check", "fast"):
        block = makefile.split(f"{target}:", 1)[1].split("\n\n", 1)[0]
        assert "verify_dev_toolchain.py" not in block
