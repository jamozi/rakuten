"""Owner-generation and provenance tests for ST-1908."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest
import yaml

from scripts import build_st1908_fine_tuning_evaluation as generator


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


def test_generated_report_is_canonical_refusal_and_non_authoritative() -> None:
    content = (generator.REPO_ROOT / generator.REPORT_PATH).read_bytes()
    parsed = json.loads(content)
    assert content == generator._canonical_output(parsed)  # noqa: SLF001
    assert parsed["document"] == {
        "authority": "NONE",
        "default_enabled": False,
        "id": "RAOS-ST1908-FINE-TUNING-EVALUATION-REPORT-001",
        "production_eligible": False,
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "story_id": "ST-1908",
        "version": "1.0.0",
    }
    assert parsed["formal_status"]["canonical"] == "DEFERRED_POST_MVP"
    assert parsed["formal_status"]["formal_tst_032"] == "NOT_EXECUTED"
    report = parsed["report"]
    assert report["outcome"] == "REFUSED_UNAVAILABLE_EVIDENCE"
    assert report["quality_gain_micros"] is None
    assert report["baseline_lifecycle_cost_jpy_micros"] is None
    assert report["candidate_lifecycle_cost_jpy_micros"] is None
    assert report["lifecycle_savings_jpy_micros"] is None
    for field in (
        "consideration_candidate",
        "training_authorized",
        "provider_call_authorized",
        "model_or_route_mutation_authorized",
        "editorial_mutation_authorized",
        "recommendation_mutation_authorized",
        "publication_snapshot_mutation_authorized",
        "publication_authorized",
        "release_authorized",
        "production_eligible",
    ):
        assert report[field] is False


def test_manifest_inventory_hashes_and_boundary_are_complete() -> None:
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    assert manifest["source_artifact_count"] == len(generator.SOURCE_ARTIFACT_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    for row in manifest["source_artifacts"]:
        path = generator.REPO_ROOT / row["uri"].removeprefix("repo://")
        content = path.read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == generator.sha256_bytes(content)
    report = (generator.REPO_ROOT / generator.REPORT_PATH).read_bytes()
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.REPORT_PATH.as_posix()}",
            "bytes": len(report),
            "sha256": generator.sha256_bytes(report),
        }
    ]
    boundary = manifest["boundary"]
    assert boundary["default_enabled"] is False
    assert boundary["recorded_synthetic_only"] is True
    for field in (
        "raw_training_examples",
        "actual_training_executed",
        "live_enabled_state_exists",
        "activation_interface_exists",
        "provider_called",
        "network_used",
        "credential_read",
        "persistence_used",
        "model_or_route_mutated",
        "editorial_mutated",
        "recommendation_mutated",
        "publication_snapshot_mutated",
        "publication_allowed",
        "release_authorized",
        "production_eligible",
    ):
        assert boundary[field] is False
    assert manifest["debt"]["introduced"] == []


def test_check_outputs_rejects_generated_drift(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    outputs = generator.render_outputs()
    for relative, payload in outputs.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    generator.check_outputs(root, outputs)
    target = root / generator.REPORT_PATH
    target.write_bytes(target.read_bytes() + b"drift")
    with pytest.raises(generator.FineTuningBuildError) as caught:
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
        if isinstance(row, dict) and "path" in row:
            required.add(Path(row["path"]))
    required.update(Path(path) for path in contract["predecessor"]["artifacts"])
    for row in contract["canonical_contracts"].values():
        required.add(Path(row["path"]))
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(generator.REPO_ROOT / relative, target)
    generator.build(root)
    generator.build(root, check=True)
    for relative, expected in generator.render_outputs(root).items():
        assert (root / relative).read_bytes() == expected


def test_source_symlink_and_unsupported_arguments_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    target = root / generator.CONTRACT_PATH
    target.parent.mkdir(parents=True)
    target.symlink_to(generator.REPO_ROOT / generator.CONTRACT_PATH)
    with pytest.raises(generator.FineTuningBuildError) as caught:
        generator.render_outputs(root)
    assert caught.value.code == "FILE_BOUNDARY_VIOLATION"
    with pytest.raises(SystemExit) as caught_exit:
        generator.parse_args(["--unknown"])
    assert caught_exit.value.code == 2
