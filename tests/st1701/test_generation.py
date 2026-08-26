"""ST-1701 deterministic generation checks."""

from __future__ import annotations

import hashlib
import json

import yaml

from scripts import build_st1701_business_inputs as generator


def test_repository_outputs_are_current() -> None:
    generator.build(check=True)


def test_manifest_v2_contains_only_semantic_and_canonical_inputs() -> None:
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    assert manifest["schema_version"] == 2
    assert manifest["generator_owner_id"] == "build_st1701_business_inputs"
    assert {row["semantic_id"] for row in manifest["semantic_inputs"]} == {
        "st1701-unresolved-business-inputs",
        "st1701-business-decision-model",
    }
    for row in manifest["outputs"]:
        payload = (
            generator.REPO_ROOT / row["uri"].removeprefix("repo://")
        ).read_bytes()
        assert row["bytes"] == len(payload)
        assert row["sha256"] == hashlib.sha256(payload).hexdigest()
    text = (generator.REPO_ROOT / generator.MANIFEST_PATH).read_text()
    assert "handoff" not in text.lower()
    assert "approval" not in text.lower()
    assert "base_commit" not in text.lower()


def test_external_gold_validation_is_reported_unexecuted() -> None:
    document = json.loads(
        (generator.REPO_ROOT / generator.GOLD_VALIDATION_PATH).read_bytes()
    )
    assert document["status"] == "EXTERNAL_EVIDENCE_NOT_EXECUTED"
    assert document["eligible_for_canonical_revision"] is False
