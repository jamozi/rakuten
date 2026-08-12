"""Deterministic generation tests for ST-0904."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat

import pytest
import yaml

from scripts import build_st0904_public_projection_reference_plan as generator


def test_render_is_deterministic_and_matches_outputs() -> None:
    assert generator.render_outputs() == generator.render_outputs()
    for relative, expected in generator.render_outputs().items():
        assert (generator.REPO_ROOT / relative).read_bytes() == expected


def test_check_is_no_write() -> None:
    paths = [generator.REPO_ROOT / path for path in generator.GENERATED_PATHS]
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    assert generator.main(["--check"]) == 0
    assert before == [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]


def test_generation_is_atomic_0644_and_rolls_back_pair(
    isolated_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generator.build(isolated_repository)
    originals = {
        path: (isolated_repository / path).read_bytes()
        for path in generator.GENERATED_PATHS
    }
    assert all(
        stat.S_IMODE((isolated_repository / path).stat().st_mode) == 0o644
        for path in generator.GENERATED_PATHS
    )
    changed = {path: content + b"changed" for path, content in originals.items()}
    real_replace = os.replace
    calls = 0

    def fail_second(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic")
        real_replace(source, target)

    monkeypatch.setattr(generator, "render_outputs", lambda _root: changed)
    monkeypatch.setattr(generator, "_replace", fail_second)
    with pytest.raises(
        generator.PublicProjectionReferenceError, match="OUTPUT_TRANSACTION_FAILED"
    ):
        generator.build(isolated_repository)
    assert originals == {
        path: (isolated_repository / path).read_bytes()
        for path in generator.GENERATED_PATHS
    }
    for relative in generator.GENERATED_PATHS:
        target = isolated_repository / relative
        assert not tuple(target.parent.glob(f".{target.name}.*.tmp"))


def test_each_generated_output_drift_is_rejected(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    for relative in generator.GENERATED_PATHS:
        path = isolated_repository / relative
        original = path.read_bytes()
        path.write_bytes(original + b"drift")
        with pytest.raises(generator.PublicProjectionReferenceError):
            generator.build(isolated_repository, check=True)
        path.write_bytes(original)


def test_manifest_closes_source_and_generated_inventory() -> None:
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    reference = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert (
        manifest["provenance"]["pro_assistance"]
        == "PRO_UNAVAILABLE_NONE_NO_PROPOSAL_NO_CONTENT"
    )
    assert manifest["generated_artifacts"][0]["sha256"] == generator._sha256(reference)
    assert json.loads(reference)["document"]["executable"] is False
