from __future__ import annotations

import hashlib
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_sources_have_no_external_or_operational_authority_surface() -> None:
    paths = (
        "python/raos/domain/editorial/policy_engine_v2.py",
        "python/raos/ports/editorial/policy_engine.py",
        "python/raos/application/editorial/policy_engine.py",
        "python/raos/adapters/recorded_policy_engine.py",
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
        "def apply_waiver",
        "def override",
        "def update",
        "def delete",
        "def send",
    )
    for relative in paths:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden), relative


def test_manifest_descriptors_hashes_transaction_and_authority_are_exact() -> None:
    manifest = yaml.safe_load(
        (REPO_ROOT / "changes/st-0805/runtime-manifest.v2.yaml").read_bytes()
    )
    sources = manifest["source_artifacts"]
    assert manifest["local_status"] == "LOCAL_IMPLEMENTATION_COMPLETE"
    assert manifest["source_artifact_count"] == len(sources)
    authority = manifest["authority"]
    assert authority["finding_proposal_only"] is True
    assert authority["waiver_proposal_only"] is True
    for key in (
        "approval_authorized",
        "waiver_apply_authorized",
        "merge_authorized",
        "recommendation_override_authorized",
        "ranking_override_authorized",
        "publication_authorized",
        "activation_authorized",
        "production_eligible",
    ):
        assert authority[key] is False
    generation = manifest["generation"]
    assert generation["transaction"] == (
        "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK"
    )
    assert generation["existing_destination_commit"] == (
        "RENAMEAT2_EXCHANGE_WITH_REVERSE_VERIFY"
    )
    assert generation["missing_destination_commit"] == "HARDLINK_NO_CLOBBER"
    assert generation["foreign_target_policy"] == "PRESERVE_AND_FAIL_CLOSED"
    for row in sources:
        path = REPO_ROOT / row["uri"].removeprefix("repo://")
        payload = path.read_bytes()
        assert row["bytes"] == len(payload)
        assert row["sha256"] == hashlib.sha256(payload).hexdigest()


def test_legacy_v1_and_additive_v2_are_both_manifest_bound() -> None:
    manifest = yaml.safe_load(
        (REPO_ROOT / "changes/st-0805/runtime-manifest.v2.yaml").read_bytes()
    )
    uris = {row["uri"] for row in manifest["source_artifacts"]}
    assert "repo://python/raos/domain/editorial/policy_engine.py" in uris
    assert "repo://python/raos/domain/editorial/policy_engine_v2.py" in uris
    assert "repo://scripts/secure_generated_publication.py" in uris
    assert "repo://changes/st-0804/generated/recommendation-pass.v2.json" in uris


def test_v2_input_models_have_no_finance_or_waiver_authority_fields() -> None:
    source = (REPO_ROOT / "python/raos/domain/editorial/policy_engine_v2.py").read_text(
        encoding="utf-8"
    )
    envelope = source.split("class PolicyEvaluationEnvelopeV2", 1)[1].split(
        "class PolicyEvaluationRecordReceiptV2", 1
    )[0]
    for token in (
        "affiliate_rate",
        "commission",
        "epc",
        "rpm",
        "revenue",
        "reward",
        "profit",
        "waiver_approved",
        "waiver_effective",
    ):
        assert f"    {token}:" not in envelope.casefold()
