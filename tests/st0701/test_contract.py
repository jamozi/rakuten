"""Compiled contract, provenance, routing, and boundary tests for ST-0701."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from raos.adapters.ai_contract_registry import CompiledTaskRegistry
from raos.ports import UnknownTaskContract
from raos.shared import ContractRepository


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPOSITORY_ROOT / "changes/st-0701/generated/ai-task-registry.v1.json"
MANIFEST_PATH = REPOSITORY_ROOT / "changes/st-0701/manifest.yaml"
CONTRACT_PATH = (
    REPOSITORY_ROOT / "changes/st-0701/contracts/ai-contract-registry-loader.v1.yaml"
)
EXPECTED_FRONTMATTER_KEYS = {
    "prompt_code",
    "version",
    "task_code",
    "status",
    "locale",
    "route_code",
    "output_schema",
    "human_review_required",
    "tools_allowed",
    "network_access",
}


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_sha256(value: object) -> str:
    return _sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_bytes())
    assert isinstance(value, dict)
    return value


def test_compiled_registry_has_exact_live_adapter_shape_and_hash_domains() -> None:
    document = _load_json(REGISTRY_PATH)
    assert set(document) == {"document", "task_count", "tasks"}
    assert document["document"] == {
        "id": "RAOS-AI-TASK-REGISTRY-001",
        "version": "1.0.0",
        "story_id": "ST-0701",
        "status": "IMPLEMENTATION_CANDIDATE",
    }
    assert document["task_count"] == len(document["tasks"]) == 12
    task_codes = [entry["task"]["task_code"] for entry in document["tasks"]]
    assert task_codes == sorted(task_codes)
    assert len(set(task_codes)) == 12

    for entry in document["tasks"]:
        assert set(entry) == {
            "task",
            "task_sha256",
            "prompt",
            "output_schema",
            "route",
            "binding_sha256",
        }
        unsigned = {
            key: value for key, value in entry.items() if key != "binding_sha256"
        }
        assert entry["task_sha256"] == _canonical_sha256(entry["task"])
        assert entry["route"]["sha256"] == _canonical_sha256(entry["route"]["metadata"])
        assert entry["binding_sha256"] == _canonical_sha256(unsigned)
        frontmatter = entry["prompt"]["metadata"]["frontmatter"]
        assert set(frontmatter) == EXPECTED_FRONTMATTER_KEYS
        assert frontmatter["task_code"] == entry["task"]["task_code"]
        assert frontmatter["prompt_code"] == entry["prompt"]["prompt_code"]
        assert frontmatter["route_code"] == entry["route"]["route_code"]
        assert (
            frontmatter["output_schema"] == entry["output_schema"]["metadata"]["path"]
        )


def test_generated_manifest_closes_sources_predecessors_and_output() -> None:
    manifest = _load_yaml(MANIFEST_PATH)
    registry_content = REGISTRY_PATH.read_bytes()
    assert set(manifest) == {
        "document",
        "provenance",
        "source_artifact_count",
        "source_artifacts",
        "generated_artifact_count",
        "generated_artifacts",
        "closure",
        "integrity",
        "boundary",
    }
    assert manifest["document"]["story_id"] == "ST-0701"
    assert manifest["source_artifact_count"] == len(manifest["source_artifacts"]) == 24
    source_uris = [entry["uri"] for entry in manifest["source_artifacts"]]
    assert len(source_uris) == len(set(source_uris))
    assert manifest["generated_artifact_count"] == 1
    assert manifest["generated_artifacts"] == [
        {
            "uri": "repo://changes/st-0701/generated/ai-task-registry.v1.json",
            "bytes": len(registry_content),
            "sha256": _sha256(registry_content),
        }
    ]
    predecessors = {
        entry["story_id"]: entry for entry in manifest["provenance"]["predecessors"]
    }
    assert predecessors["ST-0003"]["sha256"] == (
        "142d27a392ab5ecd2362327d231c9f8ea2a8d716e3f6fcd7bb15440697a50482"
    )
    assert predecessors["ST-0104"]["sha256"] == (
        "54fc0cbb0c943f0b876881dbd2d55b49bb354f3cd8e533caef99dbbff4efaeef"
    )
    compiler_inputs = manifest["provenance"]["compiler_inputs"]
    assert len(compiler_inputs) == manifest["closure"]["compiler_input_count"] == 30
    assert [entry["repository_path"] for entry in compiler_inputs] == sorted(
        entry["repository_path"] for entry in compiler_inputs
    )
    assert manifest["closure"]["registry_entry_counts"] == {
        "tasks": 12,
        "prompts": 12,
        "schemas": 14,
        "routes": 7,
        "models": 3,
    }
    assert manifest["closure"]["unbound_schema_ids"] == [
        "https://schemas.raos.local/evaluation/case/v1",
        "https://schemas.raos.local/evaluation/judge_output/v1",
    ]
    assert manifest["closure"]["unbound_route_codes"] == [
        "route.embedding_default.v1",
        "route.judge_high.v1",
    ]
    assert manifest["integrity"]["compiled_registry_sha256"] == _sha256(
        registry_content
    )
    assert manifest["integrity"]["network_retrieval"] == "FORBIDDEN"


def test_source_contract_matches_pinned_registry_and_runtime_boundary() -> None:
    contract = _load_yaml(CONTRACT_PATH)
    assert contract["story"]["open_decisions"] == []
    assert contract["story"]["dependencies"] == ["ST-0104", "ST-0003"]
    assert contract["compiled_projection"]["top_level_keys"] == [
        "document",
        "task_count",
        "tasks",
    ]
    assert [entry["kind"] for entry in contract["registries"]] == [
        "TASK",
        "PROMPT",
        "SCHEMA",
        "ROUTE",
    ]
    assert contract["closure"]["duplicate_keys"] == "REJECT"
    assert contract["closure"]["missing_references"] == "REJECT"
    assert contract["boundary"]["provider_api"] == "NOT_USED"
    assert contract["boundary"]["network"] == "NOT_USED"
    assert contract["boundary"]["database"] == "NOT_USED"
    assert contract["boundary"]["formal_tst_001"] == "NOT_EXECUTED"
    assert contract["boundary"]["formal_tst_017"] == "NOT_EXECUTED"


def test_generated_artifact_loads_all_tasks_through_runtime_adapter() -> None:
    manifest = _load_yaml(MANIFEST_PATH)
    expected_sha256 = manifest["generated_artifacts"][0]["sha256"]
    registry = CompiledTaskRegistry(
        ContractRepository(), REGISTRY_PATH, expected_sha256=expected_sha256
    )
    assert len(registry.task_codes) == 12
    for task_code in registry.task_codes:
        contract = registry.get(task_code)
        assert contract.task_code == task_code
        assert contract.prompt.content.startswith("---\nprompt_code:")
        assert (
            contract.output_schema.document["$id"] == contract.output_schema.schema_id
        )
    with pytest.raises(UnknownTaskContract):
        registry.get("ai.unknown.v1")


def test_unified_development_commands_replace_story_specific_targets() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    story_readme = (REPOSITORY_ROOT / "changes/st-0701/README.md").read_text(
        encoding="utf-8"
    )
    for target in ("setup", "generate", "check", "fast", "final"):
        assert f"\n{target}:" in f"\n{makefile}"
    for target in ("ai-registry-generate", "ai-registry-check", "ai-registry-test"):
        assert f"{target}:" not in makefile
    assert "CompiledTaskRegistry(" in story_readme
    assert ".resolve()" in story_readme
    assert _load_yaml(MANIFEST_PATH)["generated_artifacts"]
