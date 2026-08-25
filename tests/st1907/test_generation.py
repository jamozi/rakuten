"""Deterministic secure owner-generation tests for ST-1907."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest
import yaml

from scripts import build_st1907_content_portfolio_optimizer as generator


def test_render_outputs_is_deterministic_and_complete() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert first == second
    assert tuple(first) == generator.GENERATED_PATHS


def test_committed_outputs_match_rendered_bytes() -> None:
    outputs = generator.render_outputs()
    generator.check_outputs(generator.REPO_ROOT, outputs)
    for relative, expected in outputs.items():
        assert (generator.REPO_ROOT / relative).read_bytes() == expected


def test_report_fails_closed_for_current_dependency() -> None:
    parsed = json.loads((generator.REPO_ROOT / generator.REPORT_PATH).read_bytes())
    assert parsed["document"] == {
        "authority": "NONE",
        "canonical_status": "DEFERRED_POST_MVP",
        "classification": (
            "RECORDED_SYNTHETIC_BLOCKED_HUMAN_PROPOSAL_OPTIMIZER_REPORT"
        ),
        "formal_TST-032": "NOT_EXECUTED",
        "production_eligible": False,
        "schema_version": "1.0.0",
        "story_id": "ST-1907",
    }
    evaluation = parsed["evaluation"]
    assert evaluation["availability"] == "UNAVAILABLE"
    assert evaluation["unavailable_reason"] == "DEPENDENCY_BLOCKED_NO_DECISION"
    assert evaluation["proposal_state"] == "NO_PROPOSALS"
    assert evaluation["proposal_count"] == 0
    assert evaluation["proposals"] == []
    assert evaluation["policy"]["finance_values_represented"] is False
    assert evaluation["policy"]["automatic_apply"] is False
    assert all(value is False for value in evaluation["authority"].values())


def test_manifest_inventory_and_boundaries_are_complete() -> None:
    loaded = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    assert loaded["source_artifact_count"] == len(generator.SOURCE_ARTIFACT_PATHS)
    assert [row["uri"] for row in loaded["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    for row in loaded["source_artifacts"]:
        path = generator.REPO_ROOT / row["uri"].removeprefix("repo://")
        content = path.read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == generator.sha256_bytes(content)
    report = (generator.REPO_ROOT / generator.REPORT_PATH).read_bytes()
    assert loaded["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.REPORT_PATH.as_posix()}",
            "bytes": len(report),
            "sha256": generator.sha256_bytes(report),
        }
    ]
    boundary = loaded["boundary"]
    assert boundary["default_scope"] == "DISABLED"
    assert boundary["current_dependency"] == "BLOCKED_NO_DECISION"
    assert boundary["current_availability"] == "UNAVAILABLE"
    assert boundary["current_proposals"] == 0
    assert boundary["human_proposal_only"] is True
    assert boundary["automatic_apply"] is False
    assert boundary["finance_values_represented"] is False
    assert all(
        boundary[field] is False
        for field in (
            "personal_data",
            "provider_call",
            "network",
            "credential_access",
            "persistence",
            "editorial_mutation",
            "recommendation_order_mutation",
            "publication",
            "staging",
            "release",
            "production",
        )
    )
    assert loaded["debt"]["introduced"] == []


def test_check_outputs_rejects_drift(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    outputs = generator.render_outputs()
    for relative, payload in outputs.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        target.chmod(0o644)
    generator.check_outputs(root, outputs)
    target = root / generator.REPORT_PATH
    target.write_bytes(target.read_bytes() + b"drift")
    with pytest.raises(generator.ContentPortfolioOptimizerBuildError) as caught:
        generator.check_outputs(root, outputs)
    assert caught.value.code == "GENERATED_OUTPUT_DRIFT"


def test_secure_publication_builds_exact_outputs_in_isolated_copy(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    contract = yaml.safe_load(
        (generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes()
    )
    required = set(generator.SOURCE_ARTIFACT_PATHS)
    for row in contract["authority"].values():
        required.add(Path(row["path"]))
    required.update(Path(path) for path in contract["dependency"]["exact_sources"])
    required.add(
        Path(contract["measurement_and_signal_policy"]["measurement_contract"]["path"])
    )
    required.add(
        Path(contract["measurement_and_signal_policy"]["signal_policy"]["path"])
    )
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(generator.REPO_ROOT / relative, target)
    generator.build(root)
    generator.build(root, check=True)
    for relative, expected in generator.render_outputs(root).items():
        assert (root / relative).read_bytes() == expected


def test_source_symlink_and_unsupported_arguments_fail_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    target = root / generator.CONTRACT_PATH
    target.parent.mkdir(parents=True)
    target.symlink_to(generator.REPO_ROOT / generator.CONTRACT_PATH)
    with pytest.raises(generator.ContentPortfolioOptimizerBuildError) as caught:
        generator.render_outputs(root)
    assert caught.value.code == "FILE_BOUNDARY_VIOLATION"
    with pytest.raises(SystemExit) as caught_exit:
        generator.parse_args(["--unknown"])
    assert caught_exit.value.code == 2
