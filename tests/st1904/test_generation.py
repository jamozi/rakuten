"""Owner-generation and provenance tests for ST-1904."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pytest
import yaml

from scripts import build_st1904_multi_category as generator


def _required_paths() -> set[Path]:
    contract = yaml.safe_load(
        (generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes()
    )
    required = set(generator.SOURCE_ARTIFACT_PATHS)
    for row in contract["authority"].values():
        if isinstance(row, dict) and "path" in row:
            required.add(Path(row["path"]))
    required.update(Path(path) for path in contract["predecessor"]["artifacts"])
    for row in contract["dependency_contracts"].values():
        required.add(Path(row["path"]))
    return required


def _copy_required(root: Path) -> None:
    for relative in _required_paths():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(generator.REPO_ROOT / relative, target)


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


def test_generated_report_is_canonical_non_authoritative_and_blocked() -> None:
    content = (generator.REPO_ROOT / generator.REPORT_PATH).read_bytes()
    parsed = json.loads(content)
    assert content == generator._canonical_output(parsed)  # noqa: SLF001
    assert parsed["document"] == {
        "authority": "NONE",
        "canonical_status": "DEFERRED_POST_MVP",
        "classification": "RECORDED_SYNTHETIC_MULTI_CATEGORY_EVALUATION_V1",
        "formal_validation": "NOT_EXECUTED",
        "production_eligible": False,
        "status": "LOCAL_CODE_COMPLETE_MAX_SAFE_DISABLED",
        "story_id": "ST-1904",
        "version": "1.0.0",
    }
    report = parsed["report"]
    assert report["authority"] == "NONE"
    assert report["outcome"] == "INTERFACE_COMPATIBLE_RECORDED_SYNTHETIC_ONLY"
    assert report["category_ids"] == [
        "synthetic_category_alpha",
        "synthetic_category_beta",
    ]
    assert report["boundary"]["canonical_status"] == "DEFERRED_POST_MVP"
    assert report["boundary"]["category_selection"] == "HUMAN_DECISION_REQUIRED"
    assert report["boundary"]["category_activation"] == "DISABLED"
    assert report["boundary"]["template_activation"] == "DISABLED"
    assert report["boundary"]["release_decision"] == "RELEASE_DECISION_REQUIRED"
    assert report["boundary"]["publication"] == "FORBIDDEN"


def test_manifest_inventory_hashes_and_boundaries_are_complete() -> None:
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
        "real_category_selected",
        "category_identity_resolved",
        "freshness_sla_resolved",
        "templates_activated",
        "live_enabled_state_exists",
        "provider_called",
        "network_used",
        "credential_read",
        "persistence_used",
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
    with pytest.raises(generator.MultiCategoryBuildError) as caught:
        generator.check_outputs(root, outputs)
    assert caught.value.code == "GENERATED_OUTPUT_DRIFT"


def test_secure_publication_builds_exact_outputs_in_isolated_copy(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    _copy_required(root)
    generator.build(root)
    generator.build(root, check=True)
    assert generator.render_outputs(root) == {
        relative: (root / relative).read_bytes()
        for relative in generator.GENERATED_PATHS
    }


def test_source_symlink_hardlink_and_unsupported_arguments_fail_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "symlink-repository"
    target = root / generator.CONTRACT_PATH
    target.parent.mkdir(parents=True)
    target.symlink_to(generator.REPO_ROOT / generator.CONTRACT_PATH)
    with pytest.raises(generator.MultiCategoryBuildError) as symlink_failure:
        generator.render_outputs(root)
    assert symlink_failure.value.code == "FILE_BOUNDARY_VIOLATION"

    hardlink_root = tmp_path / "hardlink-repository"
    hardlink = hardlink_root / generator.CONTRACT_PATH
    hardlink.parent.mkdir(parents=True)
    hardlink_seed = tmp_path / "hardlink-seed.yaml"
    shutil.copyfile(generator.REPO_ROOT / generator.CONTRACT_PATH, hardlink_seed)
    os.link(hardlink_seed, hardlink)
    with pytest.raises(generator.MultiCategoryBuildError) as hardlink_failure:
        generator.render_outputs(hardlink_root)
    assert hardlink_failure.value.code == "FILE_BOUNDARY_VIOLATION"

    with pytest.raises(SystemExit) as caught_exit:
        generator.parse_args(["--unknown"])
    assert caught_exit.value.code == 2


@pytest.mark.parametrize(
    "content",
    (
        b"a: 1\na: 2\n",
        b"a: &x 1\nb: *x\n",
        b"a: !unsafe value\n",
        b"- not-a-mapping\n",
    ),
)
def test_contract_yaml_duplicate_alias_tag_and_shape_fail_closed(
    content: bytes,
) -> None:
    with pytest.raises(generator.MultiCategoryBuildError):
        generator._parse_yaml(content)  # noqa: SLF001
