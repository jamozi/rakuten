from __future__ import annotations

import hashlib

import pytest
import yaml

from raos.adapters.recorded_review_completion_fixture_v2 import (
    REVIEW_COMPLETION_PASS_V2_JSON,
    REVIEW_COMPLETION_PASS_V2_SHA256,
)
from scripts import build_st0901_review_completion_v2 as generator


def test_owner_generation_and_no_write_check_are_deterministic() -> None:
    generator.build(generator.REPO_ROOT)
    paths = (generator.FIXTURE_PATH, generator.MODULE_PATH, generator.MANIFEST_PATH)
    before = tuple((generator.REPO_ROOT / path).read_bytes() for path in paths)
    generator.build(generator.REPO_ROOT, check=True)
    generator.build(generator.REPO_ROOT)
    after = tuple((generator.REPO_ROOT / path).read_bytes() for path in paths)
    assert before == after


def test_generated_module_is_exact_fixture_bytes() -> None:
    fixture = (generator.REPO_ROOT / generator.FIXTURE_PATH).read_bytes()
    assert REVIEW_COMPLETION_PASS_V2_JSON == fixture
    assert REVIEW_COMPLETION_PASS_V2_SHA256 == hashlib.sha256(fixture).hexdigest()


def test_manifest_hashes_every_owner_and_dependency() -> None:
    document = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_text()
    )
    artifacts = document["source_artifacts"]
    assert document["source_artifact_count"] == len(artifacts)
    assert len({item["uri"] for item in artifacts}) == len(artifacts)
    for item in artifacts:
        path = generator.REPO_ROOT / item["uri"].removeprefix("repo://")
        payload = path.read_bytes()
        assert item["bytes"] == len(payload)
        assert item["sha256"] == hashlib.sha256(payload).hexdigest()
    assert all(
        value is False
        for key, value in document["authority"].items()
        if key.endswith("authorized")
    )
    assert all(
        value == "NOT_EXECUTED"
        for key, value in document["authority"].items()
        if not key.endswith("authorized")
    )


def test_check_detects_generated_drift_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(_artifacts: object) -> None:
        raise AssertionError("check attempted a write transaction")

    monkeypatch.setattr(generator, "_replace_generated", forbidden)
    paths = (generator.FIXTURE_PATH, generator.MODULE_PATH, generator.MANIFEST_PATH)
    before = tuple(
        (
            (generator.REPO_ROOT / path).stat().st_mtime_ns,
            (generator.REPO_ROOT / path).read_bytes(),
        )
        for path in paths
    )
    generator.build(generator.REPO_ROOT, check=True)
    after = tuple(
        (
            (generator.REPO_ROOT / path).stat().st_mtime_ns,
            (generator.REPO_ROOT / path).read_bytes(),
        )
        for path in paths
    )
    assert before == after
