"""Owner generation, determinism, and provenance tests for ST-1205."""

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
import yaml

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


def _rewrite_contract(
    root: Path, contract: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    content = yaml.safe_dump(contract, sort_keys=False, allow_unicode=True).encode()
    (root / builder.CONTRACT_PATH).write_bytes(content)
    monkeypatch.setattr(
        builder, "EXPECTED_CONTRACT_SHA256", hashlib.sha256(content).hexdigest()
    )


def test_owner_outputs_match_deterministic_rendering() -> None:
    expected = builder.render_outputs(REPOSITORY_ROOT)
    assert set(expected) == set(builder.GENERATED_PATHS)
    for path, content in expected.items():
        assert (REPOSITORY_ROOT / path).read_bytes() == content
    assert expected == builder.render_outputs(REPOSITORY_ROOT)


def test_generated_contract_is_pretty_json_and_reproduces_all_formulas() -> None:
    content = (REPOSITORY_ROOT / builder.REFERENCE_PLAN_PATH).read_bytes()
    assert content.endswith(b"\n")
    assert b"NaN" not in content
    document = json.loads(content)
    assert document["definition_count"] == 30
    assert len(document["definitions"]) == 30
    reproduction = document["recorded_reproduction"]
    assert reproduction["available_kpis"] == 30
    assert reproduction["expected_kpis_reproduced"] == 30
    assert reproduction["expected_learning_metrics_reproduced"] == 5
    assert reproduction["provider"] == "NOT_EXECUTED"
    assert reproduction["network"] == "NOT_EXECUTED"
    assert reproduction["recommendation_input"] == "DISABLED"
    assert reproduction["formal_TST-030"] == "NOT_EXECUTED"


def test_manifest_binds_every_source_current_predecessor_and_generated_contract() -> (
    None
):
    manifest = yaml.safe_load((REPOSITORY_ROOT / builder.MANIFEST_PATH).read_text())
    assert manifest["source_artifact_count"] == len(builder.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in builder.SOURCE_PATHS
    ]
    for row in manifest["source_artifacts"]:
        path = Path(row["uri"].removeprefix("repo://"))
        content = (REPOSITORY_ROOT / path).read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()
    assert [row["story_id"] for row in manifest["provenance"]["predecessors"]] == [
        "ST-1201",
        "ST-1203",
        "ST-1204",
    ]
    assert manifest["generated_artifact_count"] == 1
    assert manifest["local_completion"]["DEBT-W2-054"] == "CLOSED"
    assert manifest["local_completion"]["DEBT-W2-062"] == "CLOSED"
    assert manifest["local_completion"]["story_acceptance"] is False


def test_generate_then_check_is_no_write(tmp_path: Path) -> None:
    root = copy_owner_root(tmp_path, include_outputs=False)
    builder.build(root)
    before = _snapshot(root)
    time.sleep(0.002)
    builder.build(root, check=True)
    assert _snapshot(root) == before
    assert all(mode == 0o644 for _content, _mtime, mode in before.values())


def test_check_detects_byte_and_mode_drift_without_repair(tmp_path: Path) -> None:
    root = copy_owner_root(tmp_path, include_outputs=False)
    builder.build(root)
    target = root / builder.REFERENCE_PLAN_PATH
    target.write_bytes(target.read_bytes() + b" ")
    target.chmod(0o600)
    before = target.read_bytes()
    with pytest.raises((builder.KpiReadModelBuildError, Exception)):
        builder.build(root, check=True)
    assert target.read_bytes() == before
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("input_contract", "float_allowed", True),
        ("input_contract", "missing_allowed_as_zero", True),
        ("definition_contract", "calculation_count", 0),
        ("definition_contract", "zero_denominator", "ZERO"),
        ("learning_contract", "modifies_recommendation_order", True),
        ("execution_boundary", "provider", "EXECUTED"),
        ("execution_boundary", "production", "EXECUTED"),
        ("execution_boundary", "story_acceptance", True),
    ],
)
def test_safety_contract_mutation_is_rejected_even_when_hash_is_rebound(
    isolated_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    section: str,
    key: str,
    value: object,
) -> None:
    contract = yaml.safe_load((isolated_root / builder.CONTRACT_PATH).read_text())
    contract[section][key] = value
    _rewrite_contract(isolated_root, contract, monkeypatch)
    with pytest.raises(builder.KpiReadModelBuildError):
        builder.load_contract(isolated_root)


def test_predecessor_hash_drift_is_rejected(isolated_root: Path) -> None:
    target = isolated_root / next(iter(builder.PREDECESSOR_HASHES))
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(builder.KpiReadModelBuildError):
        builder.load_contract(isolated_root)


def test_input_and_output_symlink_targets_are_rejected(isolated_root: Path) -> None:
    contract = isolated_root / builder.CONTRACT_PATH
    elsewhere = isolated_root / "contract-elsewhere.yaml"
    elsewhere.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(elsewhere)
    with pytest.raises(Exception):
        builder.load_contract(isolated_root)

    root = copy_owner_root(isolated_root / "second")
    target = root / builder.REFERENCE_PLAN_PATH
    outside = root / "outside.json"
    outside.write_text("unchanged")
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(Exception):
        builder.build(root)
    assert outside.read_text() == "unchanged"


def test_cli_generate_then_check_and_rejects_secret_argument() -> None:
    command = [sys.executable, str(REPOSITORY_ROOT / builder.GENERATOR_PATH)]
    environment = {"PATH": os.environ.get("PATH", "")}
    generated = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert generated.returncode == 0
    checked = subprocess.run(
        [*command, "--check"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert checked.returncode == 0
    canary = "SECRET_CANARY_ST1205"
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
