"""Deterministic owner-generation tests for ST-1905."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest
import yaml

from scripts import build_st1905_advanced_rank_provider as generator


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


def test_generated_report_is_canonical_and_non_authoritative() -> None:
    content = (generator.REPO_ROOT / generator.REPORT_PATH).read_bytes()
    parsed = json.loads(content)
    assert content == generator._canonical_output(parsed)  # noqa: SLF001
    assert parsed["document"] == {
        "authority": "NONE",
        "default_enabled": False,
        "id": "RAOS-ST1905-ADVANCED-RANK-PROVIDER-REPORT-001",
        "production_eligible": False,
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "story_id": "ST-1905",
        "version": "1.0.0",
    }
    assert parsed["formal_status"] == {
        "canonical": "DEFERRED_POST_MVP",
        "formal_tst_032": "NOT_EXECUTED",
        "live": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
    }
    report = parsed["report"]
    assert report["outcome"] == "CONTRACT_COMPATIBLE_RECORDED_ONLY"
    assert report["boundary"]["provider_selection"] == "HUMAN_DECISION_REQUIRED"
    assert report["boundary"]["provider_call"] == "NOT_EXECUTED"
    assert report["boundary"]["network"] == "FORBIDDEN"
    assert report["boundary"]["recommendation_input"] == "DISABLED"
    assert report["boundary"]["publication"] == "FORBIDDEN"


def test_manifest_inventory_hashes_and_boundary_are_complete() -> None:
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
    assert boundary["default_enabled"] is False
    assert boundary["selected_provider_state_exists"] is False
    assert boundary["live_enabled_state_exists"] is False
    assert boundary["activation_interface_exists"] is False
    assert boundary["provider_called"] is False
    assert boundary["network_used"] is False
    assert boundary["credential_read"] is False
    assert boundary["serp_scrape"] is False
    assert boundary["persistence_used"] is False
    assert boundary["kpi_mutated"] is False
    assert boundary["recommendation_mutated"] is False
    assert boundary["publication_allowed"] is False
    assert boundary["release_authorized"] is False
    assert boundary["production_eligible"] is False
    assert loaded["debt"]["introduced"] == []


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
    with pytest.raises(generator.AdvancedRankProviderBuildError) as caught:
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
    with pytest.raises(generator.AdvancedRankProviderBuildError) as caught:
        generator.render_outputs(root)
    assert caught.value.code == "FILE_BOUNDARY_VIOLATION"
    with pytest.raises(SystemExit) as caught_exit:
        generator.parse_args(["--unknown"])
    assert caught_exit.value.code == 2
