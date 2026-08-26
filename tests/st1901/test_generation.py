"""Owner generation, provenance, and no-write behavior for ST-1901."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time

import pytest
import yaml

from .support import REPOSITORY_ROOT
from scripts import build_st1901_model_judge_calibration as builder


def _owner_paths(*, include_outputs: bool) -> set[Path]:
    contract = yaml.safe_load((REPOSITORY_ROOT / builder.CONTRACT_PATH).read_bytes())
    paths = {builder.CONTRACT_PATH}
    for section in ("authority", "canonical_contracts"):
        for value in contract[section].values():
            paths.add(Path(value["path"]))
    paths.update(Path(path) for path in contract["predecessor"]["artifacts"])
    paths.update(Path(path) for path in contract["owned_sources"])
    if include_outputs:
        paths.update((builder.FIXTURE_PATH, builder.REPORT_PATH, builder.MANIFEST_PATH))
    return paths


def _copy_owner_root(destination: Path, *, include_outputs: bool) -> Path:
    for relative in sorted(_owner_paths(include_outputs=include_outputs)):
        source = REPOSITORY_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def _snapshot(root: Path) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (
            (root / path).read_bytes(),
            (root / path).stat().st_mtime_ns,
            stat.S_IMODE((root / path).stat().st_mode),
        )
        for path in (builder.FIXTURE_PATH, builder.REPORT_PATH, builder.MANIFEST_PATH)
    }


def test_owner_outputs_match_deterministic_rendering() -> None:
    contract = builder._contract(REPOSITORY_ROOT)  # noqa: SLF001
    expected = builder.render_outputs(contract, REPOSITORY_ROOT)
    assert set(expected) == {
        builder.FIXTURE_PATH,
        builder.REPORT_PATH,
        builder.MANIFEST_PATH,
    }
    assert expected == builder.render_outputs(contract, REPOSITORY_ROOT)
    for path, content in expected.items():
        assert (REPOSITORY_ROOT / path).read_bytes() == content


def test_manifest_binds_sources_outputs_and_non_release_status() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / builder.MANIFEST_PATH).read_bytes())
    assert manifest["document"]["canonical_implementation_status"] == (
        "DEFERRED_POST_MVP"
    )
    assert manifest["document"]["authority"] == "NONE"
    assert manifest["document"]["production_eligible"] is False
    assert manifest["evaluation"]["decision_outcome"] == (
        "REFUSED_UNVERIFIABLE_CALIBRATION"
    )
    assert manifest["evaluation"]["separate_release_decision_required"] is True
    assert set(manifest["formal_status"].values()) == {"NOT_EXECUTED"}
    for raw_path, digest in manifest["source_sha256"].items():
        assert (
            hashlib.sha256((REPOSITORY_ROOT / raw_path).read_bytes()).hexdigest()
            == digest
        )
    for raw_path, digest in manifest["generated_sha256"].items():
        assert (
            hashlib.sha256((REPOSITORY_ROOT / raw_path).read_bytes()).hexdigest()
            == digest
        )


def test_generate_then_check_is_no_write(tmp_path: Path) -> None:
    root = _copy_owner_root(tmp_path, include_outputs=False)
    builder.build(root)
    before = _snapshot(root)
    time.sleep(0.002)
    builder.build(root, check=True)
    assert _snapshot(root) == before
    assert all(mode == 0o644 for _content, _mtime, mode in before.values())


def test_check_rejects_drift_without_repair(tmp_path: Path) -> None:
    root = _copy_owner_root(tmp_path, include_outputs=False)
    builder.build(root)
    target = root / builder.REPORT_PATH
    target.write_bytes(target.read_bytes() + b" ")
    target.chmod(0o600)
    before = target.read_bytes()
    with pytest.raises(builder.St1901BuildError):
        builder.build(root, check=True)
    assert target.read_bytes() == before
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_check_rejects_mode_only_drift_without_repair(tmp_path: Path) -> None:
    root = _copy_owner_root(tmp_path, include_outputs=False)
    builder.build(root)
    target = root / builder.FIXTURE_PATH
    before = target.read_bytes()
    target.chmod(0o600)
    with pytest.raises(builder.St1901BuildError):
        builder.build(root, check=True)
    assert target.read_bytes() == before
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_input_and_output_symlink_targets_are_rejected(tmp_path: Path) -> None:
    input_root = _copy_owner_root(tmp_path / "input", include_outputs=False)
    contract = input_root / builder.CONTRACT_PATH
    elsewhere = input_root / "elsewhere.yaml"
    elsewhere.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(elsewhere)
    with pytest.raises(builder.St1901BuildError):
        builder.build(input_root)

    output_root = _copy_owner_root(tmp_path / "output", include_outputs=False)
    builder.build(output_root)
    target = output_root / builder.REPORT_PATH
    outside = output_root / "outside.json"
    outside.write_text("unchanged")
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(builder.St1901BuildError):
        builder.build(output_root)
    assert outside.read_text() == "unchanged"


def test_cli_generate_check_and_unknown_argument_are_safe() -> None:
    command = [
        sys.executable,
        str(REPOSITORY_ROOT / "scripts/build_st1901_model_judge_calibration.py"),
    ]
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": f"{REPOSITORY_ROOT / 'python'}:{REPOSITORY_ROOT}",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    assert (
        subprocess.run(
            [*command, "--check"],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            env=environment,
        ).returncode
        == 0
    )
    canary = "SECRET_CANARY_ST1901"
    rejected = subprocess.run(
        [*command, canary],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert rejected.returncode == 2
    assert canary not in rejected.stdout
    assert canary not in rejected.stderr
