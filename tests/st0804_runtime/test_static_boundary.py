from __future__ import annotations

import hashlib
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_sources_have_no_external_or_authority_surface() -> None:
    paths = (
        "python/raos/domain/editorial/recommendation_v2.py",
        "python/raos/ports/editorial/recommendation.py",
        "python/raos/application/editorial/recommendation.py",
        "python/raos/adapters/recorded_recommendation.py",
    )
    forbidden = (
        "import requests",
        "import httpx",
        "import socket",
        "import subprocess",
        "urllib.request",
        "def publish",
        "def activate",
        "def approve",
        "def override",
        "def update",
        "def delete",
        "def send",
    )
    for relative in paths:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden), relative


def test_manifest_descriptors_hashes_and_authority_are_exact() -> None:
    manifest = yaml.safe_load(
        (REPO_ROOT / "changes/st-0804/runtime-manifest.v2.yaml").read_bytes()
    )
    sources = manifest["source_artifacts"]
    assert manifest["local_status"] == "LOCAL_IMPLEMENTATION_COMPLETE"
    assert manifest["source_artifact_count"] == len(sources)
    authority = manifest["authority"]
    assert authority["approval_authorized"] is False
    assert authority["override_supported"] is False
    assert authority["publication_authorized"] is False
    assert authority["recommendation_authorized"] is False
    assert authority["ranking_authorized"] is False
    assert authority["activation_authorized"] is False
    assert authority["production_eligible"] is False
    assert manifest["generation"]["transaction"] == (
        "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK"
    )
    assert manifest["generation"]["existing_destination_commit"] == (
        "RENAMEAT2_EXCHANGE_WITH_REVERSE_VERIFY"
    )
    assert manifest["generation"]["missing_destination_commit"] == "HARDLINK_NO_CLOBBER"
    assert manifest["generation"]["foreign_target_policy"] == "PRESERVE_AND_FAIL_CLOSED"
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


def test_v1_compatibility_source_and_v2_are_both_manifest_bound() -> None:
    manifest = yaml.safe_load(
        (REPO_ROOT / "changes/st-0804/runtime-manifest.v2.yaml").read_bytes()
    )
    uris = {row["uri"] for row in manifest["source_artifacts"]}
    assert "repo://python/raos/domain/editorial/recommendation.py" in uris
    assert "repo://python/raos/domain/editorial/recommendation_v2.py" in uris
    assert "repo://scripts/secure_generated_publication.py" in uris


def test_runtime_source_contains_no_finance_input_model_fields() -> None:
    source = (
        REPO_ROOT / "python/raos/domain/editorial/recommendation_v2.py"
    ).read_text(encoding="utf-8")
    declarations = source.split("class RecommendationEnvelopeV2", 1)[1].split(
        "class CandidateRecommendationV2", 1
    )[0]
    for token in (
        "affiliate_rate",
        "commission",
        "epc",
        "rpm",
        "revenue",
        "reward",
        "profit",
    ):
        assert f"    {token}:" not in declarations.casefold()
