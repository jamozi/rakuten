"""Deterministic owner-generation tests for ST-1906."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest
import yaml

from scripts import build_st1906_advanced_causal_attribution as generator


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


def test_generated_report_is_analysis_only_and_non_authoritative() -> None:
    parsed = json.loads((generator.REPO_ROOT / generator.REPORT_PATH).read_bytes())
    assert parsed["document"] == {
        "authority": "NONE",
        "canonical_status": "DEFERRED_POST_MVP",
        "classification": "RECORDED_SYNTHETIC_AGGREGATE_CAUSAL_ANALYSIS_CANDIDATE",
        "formal_TST-032": "NOT_EXECUTED",
        "production_eligible": False,
        "schema_version": "1.0.0",
        "story_id": "ST-1906",
    }
    evaluation = parsed["evaluation"]
    assert evaluation["availability"] == "AVAILABLE"
    assert evaluation["candidate_state"] == "ANALYSIS_CANDIDATE_ONLY"
    assert evaluation["policy"]["arbitrary_provider_total_allocation"] is False
    assert evaluation["policy"]["automatic_editorial_use"] is False
    assert evaluation["policy"]["automatic_recommendation_use"] is False
    assert evaluation["policy"]["finance_values_represented"] is False
    assert all(value is False for value in evaluation["authority"].values())


def test_manifest_inventory_hashes_and_boundaries_are_complete() -> None:
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
    assert boundary["personal_data"] is False
    assert boundary["tracking_activation"] is False
    assert boundary["finance_values_represented"] is False
    assert boundary["provider_total_allocation"] is False
    assert boundary["editorial_mutation"] is False
    assert boundary["recommendation_order_mutation"] is False
    assert boundary["publication"] is False
    assert boundary["release"] is False
    assert boundary["production"] is False
    assert loaded["debt"]["introduced"] == []


def test_check_outputs_rejects_generated_drift(tmp_path: Path) -> None:
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
    with pytest.raises(generator.CausalAttributionBuildError) as caught:
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
    required.update(Path(path) for path in contract["predecessor"]["artifacts"])
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
    with pytest.raises(generator.CausalAttributionBuildError) as caught:
        generator.render_outputs(root)
    assert caught.value.code == "FILE_BOUNDARY_VIOLATION"
    with pytest.raises(SystemExit) as caught_exit:
        generator.parse_args(["--unknown"])
    assert caught_exit.value.code == 2
