"""Owner generation, provenance, and no-write checks for ST-1206."""

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

from .support import REPOSITORY_ROOT, copy_owner_root
from scripts import build_st1206_keyword_rank_import as builder


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


def test_generated_evidence_contains_summary_only_and_closed_boundaries() -> None:
    content = (REPOSITORY_ROOT / builder.EVIDENCE_PATH).read_bytes()
    assert content.endswith(b"\n")
    document = json.loads(content)
    evaluation = document["recorded_evaluation"]
    assert evaluation["row_count"] == 6
    assert evaluation["unique_keyword_count"] == 2
    assert evaluation["metric_counts"] == {
        "POSITION": 2,
        "SEARCH_VOLUME": 2,
        "DIFFICULTY": 2,
    }
    assert evaluation["default_scope"] == "DISABLED"
    assert evaluation["import_state"] == "EVALUATED_NOT_IMPORTED"
    assert evaluation["serp_scrape"] == "FORBIDDEN"
    assert evaluation["provider"] == "NOT_EXECUTED"
    assert evaluation["formal_TST-030"] == "NOT_EXECUTED"
    assert "observations" not in evaluation
    assert "query" not in evaluation


def test_manifest_binds_every_source_and_generated_artifact() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / builder.MANIFEST_PATH).read_text())
    assert manifest["source_artifact_count"] == len(builder.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in builder.SOURCE_PATHS
    ]
    for row in manifest["source_artifacts"]:
        relative = Path(row["uri"].removeprefix("repo://"))
        content = (REPOSITORY_ROOT / relative).read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()
    completion = manifest["local_completion"]
    assert completion["local_code_status"] == "LOCAL_CODE_COMPLETE"
    assert completion["implementation_boundary"] == "MAXIMUM_SAFE_DISABLED"
    assert completion["introduced_debt"] == []
    assert completion["effective_canonical_status"] == "DEFERRED_POST_MVP"
    assert completion["story_acceptance"] is False


def test_generate_then_check_is_no_write(tmp_path: Path) -> None:
    root = copy_owner_root(tmp_path, builder, include_outputs=False)
    builder.build(root)
    before = _snapshot(root)
    time.sleep(0.002)
    builder.build(root, check=True)
    assert _snapshot(root) == before
    assert all(mode == 0o644 for _content, _mtime, mode in before.values())


def test_check_detects_byte_and_mode_drift_without_repair(tmp_path: Path) -> None:
    root = copy_owner_root(tmp_path, builder, include_outputs=False)
    builder.build(root)
    target = root / builder.EVIDENCE_PATH
    target.write_bytes(target.read_bytes() + b" ")
    target.chmod(0o600)
    before = target.read_bytes()
    with pytest.raises(builder.KeywordRankBuildError):
        builder.build(root, check=True)
    assert target.read_bytes() == before
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("feature_scope", "default", "ENABLED"),
        ("feature_scope", "live_enabled_state_exists", True),
        ("port_contract", "url_field", True),
        ("recorded_fixture_contract", "raw_keyword_text_present", True),
        ("csv_security_contract", "partial_result_on_failure", True),
        ("evaluation_contract", "recommendation_order_modified", True),
        ("execution_boundary", "serp_scrape", "EXECUTED"),
        ("execution_boundary", "provider", "EXECUTED"),
        ("execution_boundary", "production", "EXECUTED"),
        ("execution_boundary", "story_acceptance", True),
    ],
)
def test_safety_mutation_is_rejected_even_when_contract_hash_is_rebound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    section: str,
    key: str,
    value: object,
) -> None:
    root = copy_owner_root(tmp_path, builder, include_outputs=False)
    contract = yaml.safe_load((root / builder.CONTRACT_PATH).read_text())
    contract[section][key] = value
    _rewrite_contract(root, contract, monkeypatch)
    with pytest.raises(builder.KeywordRankBuildError):
        builder.load_contract(root)


def test_predecessor_bytes_are_semantic_inputs(tmp_path: Path) -> None:
    root = copy_owner_root(tmp_path, builder, include_outputs=False)
    predecessor = root / builder.PREDECESSOR_PATHS[0]
    predecessor.write_bytes(predecessor.read_bytes() + b"\n")
    builder.load_contract(root)


def test_input_and_output_symlink_targets_are_rejected(tmp_path: Path) -> None:
    root = copy_owner_root(tmp_path / "input", builder, include_outputs=False)
    contract = root / builder.CONTRACT_PATH
    elsewhere = root / "contract-elsewhere.yaml"
    elsewhere.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(elsewhere)
    with pytest.raises(Exception):
        builder.load_contract(root)

    output_root = copy_owner_root(tmp_path / "output", builder, include_outputs=False)
    builder.build(output_root)
    target = output_root / builder.EVIDENCE_PATH
    outside = output_root / "outside.json"
    outside.write_text("unchanged")
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(Exception):
        builder.build(output_root)
    assert outside.read_text() == "unchanged"


def test_cli_generate_check_and_secret_argument_rejection() -> None:
    command = [sys.executable, str(REPOSITORY_ROOT / builder.GENERATOR_PATH)]
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": f"{REPOSITORY_ROOT / 'python'}:{REPOSITORY_ROOT}",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
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
    canary = "SECRET_CANARY_ST1206"
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
