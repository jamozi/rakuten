"""ST-0702 deterministic generation checks."""

from __future__ import annotations

import hashlib

import yaml

from scripts import build_st0702_context_pack_reference_plan as generator


def test_repository_outputs_are_current() -> None:
    generator.build(check=True)


def test_manifest_uses_semantic_predecessor_owners() -> None:
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    predecessors = manifest["provenance"]["predecessors"]
    assert predecessors == [
        {
            "story_id": "ST-0604",
            "owner_id": "build_st0604_source_packet_lifecycle_reference_plan",
            "owner_version": "2",
            "binding": "SEMANTIC_OWNER_GRAPH",
        },
        {
            "story_id": "ST-0701",
            "owner_id": "build_st0701_ai_registry",
            "owner_version": "2",
            "binding": "SEMANTIC_OWNER_GRAPH",
        },
    ]
    assert "base_commit" not in str(manifest).lower()
    assert "generation_command" not in str(manifest).lower()
    generated = manifest["generated_artifacts"][0]
    output = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert generated["sha256"] == hashlib.sha256(output).hexdigest()
