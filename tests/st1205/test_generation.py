"""Determinism, publication, and manifest tests for ST-1205."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from typing import Any

import pytest

from conftest import REPOSITORY_ROOT, copy_owner_root
from scripts import build_st1205_kpi_read_model_reference_plan as builder


def _snapshot(root: Path) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (
            (root / path).read_bytes(),
            (root / path).stat().st_mtime_ns,
            stat.S_IMODE((root / path).stat().st_mode),
        )
        for path in builder.GENERATED_PATHS
    }


def test_owner_outputs_match_deterministic_rendering() -> None:
    expected = builder.render_outputs(REPOSITORY_ROOT)
    assert set(expected) == set(builder.GENERATED_PATHS)
    for path, content in expected.items():
        assert (REPOSITORY_ROOT / path).read_bytes() == content


def test_rendering_is_byte_deterministic() -> None:
    assert builder.render_outputs(REPOSITORY_ROOT) == builder.render_outputs(
        REPOSITORY_ROOT
    )


def test_generated_json_is_utf8_pretty_json_with_final_newline() -> None:
    content = (REPOSITORY_ROOT / builder.REFERENCE_PLAN_PATH).read_bytes()
    assert content.endswith(b"\n")
    assert json.loads(content) == json.loads(content.decode("utf-8"))
    assert b"NaN" not in content


def test_manifest_binds_every_owner_source_and_generated_plan(
    manifest: dict[str, Any],
) -> None:
    assert manifest["source_artifact_count"] == len(builder.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in builder.SOURCE_PATHS
    ]
    for row in manifest["source_artifacts"]:
        path = Path(row["uri"].removeprefix("repo://"))
        content = (REPOSITORY_ROOT / path).read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()
    generated = manifest["generated_artifacts"]
    assert manifest["generated_artifact_count"] == 1
    assert generated[0]["uri"] == f"repo://{builder.REFERENCE_PLAN_PATH.as_posix()}"


def test_manifest_binds_catalog_helper_and_predecessors(
    manifest: dict[str, Any],
) -> None:
    provenance = manifest["provenance"]
    assert provenance["contract_sha256"] == builder.EXPECTED_CONTRACT_SHA256
    assert provenance["kpi_catalog"]["sha256"] == builder.KPI_CATALOG_SHA256
    assert provenance["implementation_helper"]["sha256"] == builder.HELPER_SHA256
    assert [row["story_id"] for row in provenance["predecessors"]] == [
        "ST-1201",
        "ST-1203",
        "ST-1204",
    ]
    assert provenance["predecessors"][2]["known_owner_debt"] == (
        "INHERITED_PREDECESSOR_HASH_DRIFT"
    )


def test_manifest_boundary_is_nonattesting(manifest: dict[str, Any]) -> None:
    boundary = manifest["boundary"]
    assert boundary["executable"] is False
    assert boundary["non_attesting"] is True
    assert boundary["definition_count"] == 30
    assert boundary["calculation_count"] == 0
    assert boundary["verified_count"] == 0
    assert boundary["action_count_total"] == 0
    assert boundary["formal_tst_030"] == "NOT_EXECUTED"
    assert boundary["story_acceptance"] is False


def test_build_publishes_both_outputs_atomically_with_mode_0644(tmp_path: Path) -> None:
    root = copy_owner_root(tmp_path, include_outputs=False)
    builder.build(root)
    for path in builder.GENERATED_PATHS:
        assert (root / path).is_file()
        assert stat.S_IMODE((root / path).stat().st_mode) == 0o644
    builder.build(root, check=True)


def test_check_mode_is_no_write_for_bytes_mtime_and_mode(tmp_path: Path) -> None:
    root = copy_owner_root(tmp_path, include_outputs=False)
    builder.build(root)
    before = _snapshot(root)
    time.sleep(0.002)
    builder.build(root, check=True)
    assert _snapshot(root) == before


def test_check_detects_generated_drift_without_repair(tmp_path: Path) -> None:
    root = copy_owner_root(tmp_path, include_outputs=False)
    builder.build(root)
    target = root / builder.REFERENCE_PLAN_PATH
    target.write_bytes(target.read_bytes() + b" ")
    before = _snapshot(root)
    with pytest.raises(builder.KpiReferencePlanError):
        builder.build(root, check=True)
    assert _snapshot(root) == before


def test_cli_generate_then_check() -> None:
    command = [sys.executable, str(REPOSITORY_ROOT / builder.GENERATOR_PATH)]
    generated = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
    )
    assert generated.returncode == 0
    checked = subprocess.run(
        [*command, "--check"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
    )
    assert checked.returncode == 0


def test_cli_rejects_unsupported_argument_without_echo() -> None:
    canary = "SECRET_CANARY_ST1205"
    result = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / builder.GENERATOR_PATH), canary],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
    )
    assert result.returncode == 2
    assert canary not in result.stdout
    assert canary not in result.stderr
