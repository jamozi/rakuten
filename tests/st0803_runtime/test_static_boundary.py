from __future__ import annotations

import hashlib
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_sources_have_no_provider_or_publication_surface() -> None:
    paths = (
        "python/raos/domain/editorial/comparison_validation_v2.py",
        "python/raos/ports/editorial/comparison_validation.py",
        "python/raos/application/editorial/comparison_validation.py",
        "python/raos/adapters/recorded_comparison_validation.py",
    )
    forbidden = (
        "import requests",
        "import httpx",
        "import socket",
        "import subprocess",
        "urllib.request",
        "def publish",
        "def rank",
        "def recommend",
        "def update",
        "def delete",
    )
    for relative in paths:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden), relative


def test_manifest_descriptors_and_hashes_are_exact() -> None:
    manifest = yaml.safe_load(
        (REPO_ROOT / "changes/st-0803/runtime-manifest.v2.yaml").read_bytes()
    )
    sources = manifest["source_artifacts"]
    assert manifest["source_artifact_count"] == len(sources)
    assert manifest["authority"]["publication_authorized"] is False
    assert manifest["authority"]["recommendation_authorized"] is False
    assert manifest["authority"]["ranking_authorized"] is False
    allowed_roles = {
        "OWNER_SOURCE",
        "UPSTREAM_RECORDED_FIXTURE",
        "CANONICAL_INPUT",
        "DEPENDENCY_CONTRACT",
        "RUNTIME_DEPENDENCY",
        "LOCKED_TOOLCHAIN",
    }
    for row in sources:
        path = REPO_ROOT / row["uri"].removeprefix("repo://")
        payload = path.read_bytes()
        assert row["artifact_role"] in allowed_roles
        assert row["bytes"] == len(payload)
        assert row["sha256"] == hashlib.sha256(payload).hexdigest()


def test_v1_source_is_not_modified_by_v2_manifest() -> None:
    manifest = yaml.safe_load(
        (REPO_ROOT / "changes/st-0803/runtime-manifest.v2.yaml").read_bytes()
    )
    uris = {row["uri"] for row in manifest["source_artifacts"]}
    assert "repo://python/raos/domain/editorial/comparison_validation.py" in uris
    assert "repo://python/raos/domain/editorial/comparison_validation_v2.py" in uris
