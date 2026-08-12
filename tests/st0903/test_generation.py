"""Deterministic generation tests for the ST-0903 reference plan."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat

import pytest
import yaml

from scripts import build_st0903_publication_snapshot_reference_plan as generator


def test_render_is_deterministic_and_matches_installed_outputs() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()

    assert first == second
    for relative, expected in first.items():
        assert (generator.REPO_ROOT / relative).read_bytes() == expected


def test_check_mode_accepts_exact_outputs_and_is_no_write() -> None:
    paths = [generator.REPO_ROOT / relative for relative in generator.GENERATED_PATHS]
    before = {
        path: (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in paths
    }
    assert generator.main(["--check"]) == 0
    after = {
        path: (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in paths
    }
    assert after == before


def test_isolated_generation_is_atomic_0644_and_adjacent(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    for relative in generator.GENERATED_PATHS:
        path = isolated_repository / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert stat.S_IMODE(path.stat().st_mode) == 0o644
        assert not tuple(path.parent.glob(f".{path.name}.*.tmp"))
    generator.build(isolated_repository, check=True)


def test_second_replace_failure_restores_the_exact_output_pair(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator.build(isolated_repository)
    originals = {
        relative: (isolated_repository / relative).read_bytes()
        for relative in generator.GENERATED_PATHS
    }
    changed = {
        relative: content + b"changed" for relative, content in originals.items()
    }
    real_replace = os.replace
    replacement_count = 0

    def fail_second_replace(source: Path, target: Path) -> None:
        nonlocal replacement_count
        replacement_count += 1
        if replacement_count == 2:
            raise OSError("synthetic second replace failure")
        real_replace(source, target)

    monkeypatch.setattr(generator, "render_outputs", lambda _root: changed)
    monkeypatch.setattr(generator, "_replace", fail_second_replace)

    with pytest.raises(
        generator.PublicationSnapshotReferenceError,
        match=r"OUTPUT_TRANSACTION_FAILED field=output$",
    ):
        generator.build(isolated_repository)
    assert {
        relative: (isolated_repository / relative).read_bytes()
        for relative in generator.GENERATED_PATHS
    } == originals
    for relative in generator.GENERATED_PATHS:
        target = isolated_repository / relative
        assert not tuple(target.parent.glob(f".{target.name}.*.tmp"))


def test_manifest_binds_all_inputs_and_marks_digest_noncanonical() -> None:
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    reference = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()

    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    assert (
        manifest["provenance"]["authority_inputs"] == generator._expected_source_rows()
    )
    assert manifest["provenance"]["pro_assistance"] == (
        "PRO_UNAVAILABLE_NONE_NO_PROPOSAL_NO_CONTENT"
    )
    assert manifest["provenance"]["digest_classification"] == (
        "LOCAL_GENERATION_INTEGRITY_ONLY_NONCANONICAL_NONAUDIT"
    )
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.REFERENCE_PLAN_PATH.as_posix()}",
            "bytes": len(reference),
            "sha256": generator._sha256(reference),
            "digest_classification": "LOCAL_GENERATION_INTEGRITY_ONLY_NONCANONICAL_NONAUDIT",
        }
    ]


def test_manifest_boundary_keeps_every_claim_closed() -> None:
    boundary = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )["boundary"]

    assert boundary["executable"] is False
    assert boundary["runtime_reader"] == "NOT_IMPLEMENTED"
    assert boundary["pure_snapshot_builder"] == "NOT_IMPLEMENTED"
    assert boundary["runtime_snapshot_builder"] == "NOT_IMPLEMENTED"
    assert boundary["records"] == "NOT_EVALUATED"
    assert boundary["empty_snapshots"] == (
        "NO_BUILD_OR_EVIDENCE_NOT_ZERO_VALID_SNAPSHOTS"
    )
    assert boundary["formal_tst_014"] == "NOT_EXECUTED"
    assert boundary["formal_tst_021"] == "NOT_EXECUTED"
    assert boundary["story_acceptance"] is False
    assert boundary["readiness"] == "NOT_READY"


def test_generated_or_manifest_drift_is_rejected(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    for relative in generator.GENERATED_PATHS:
        path = isolated_repository / relative
        original = path.read_bytes()
        path.write_bytes(original + b"drift")
        with pytest.raises(generator.PublicationSnapshotReferenceError):
            generator.build(isolated_repository, check=True)
        path.write_bytes(original)


def test_reference_plan_bytes_are_stable_utf8_json() -> None:
    content = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()

    assert content.endswith(b"\n")
    assert b"\r" not in content
    parsed = json.loads(content)
    assert content == generator._json_bytes(parsed)
