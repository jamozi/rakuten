"""Acceptance checks for the shared RAOS build and status foundations."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import yaml

from scripts.raos_build_core import (
    ACTIVE_MANIFEST_PATH,
    EXPLICIT_OWNER_DEPENDENCIES,
    OWNER_PRIVATE_OWNER_IDS,
    REPOSITORY_ROOT,
    InputKind,
    active_manifest_document,
    affected_owners,
    discover_registry,
    run_commands,
)


def test_all_generators_have_one_owner_and_an_acyclic_graph() -> None:
    registry = discover_registry()
    # The migration started with 134 owners; new generators must join the same
    # registry instead of requiring another Story-specific workflow.
    assert len(registry) >= 134
    outputs = [path for spec in registry.values() for path in spec.outputs]
    assert len(outputs) == len(set(outputs))
    for owner, dependencies in EXPLICIT_OWNER_DEPENDENCIES.items():
        assert set(dependencies) <= set(registry[owner].owner_dependencies)


def test_build_infrastructure_change_selects_the_complete_graph() -> None:
    registry = discover_registry()
    selected = affected_owners(registry, {Path("scripts/raos_build_core.py")})
    assert set(selected) == set(registry)


def test_owner_commands_do_not_write_python_bytecode(tmp_path: Path) -> None:
    (tmp_path / "owner_module.py").write_text("VALUE = 1\n", encoding="utf-8")

    run_commands(((sys.executable, "-c", "import owner_module"),), root=tmp_path)

    assert not (tmp_path / "__pycache__").exists()


def test_physical_runtime_generator_is_owner_private() -> None:
    assert "build_st1703_self_hosted_runtime_manifest" in OWNER_PRIVATE_OWNER_IDS


def test_active_manifest_uses_hashes_only_for_integrity_inputs_and_outputs() -> None:
    registry = discover_registry()
    committed = json.loads((REPOSITORY_ROOT / ACTIVE_MANIFEST_PATH).read_bytes())
    assert committed == active_manifest_document(registry)
    assert committed["document"]["mutable_source_hash_authority"] is False
    for owner in committed["owners"]:
        for item in owner["semantic_inputs"]:
            if item["kind"] in {InputKind.IMMUTABLE, InputKind.DEPENDENCY}:
                assert set(item) >= {"uri", "kind", "sha256"}
            else:
                assert "sha256" not in item
                assert set(item) >= {"uri", "kind", "semantic_id", "version"}
        for output in owner["outputs"]:
            assert set(output) == {"uri", "bytes", "sha256"}


def test_status_v2_is_compact_and_contains_no_evidence_bodies() -> None:
    status = yaml.safe_load(
        (REPOSITORY_ROOT / "changes/status/status.v2.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert status["document"] == {
        "id": "RAOS-STATUS-002",
        "version": "2.0.0",
        "history": "GIT_AND_CI",
        "legacy_v1": "ARCHIVE_ONLY",
    }
    assert len(status["stories"]) > 100
    assert all(
        set(story) == {
            "story_id",
            "implementation",
            "verification",
            "external_not_run",
        }
        for story in status["stories"]
    )
    assert "evidence" not in json.dumps(status).lower()


def test_root_development_policy_is_short_and_has_only_two_stop_classes() -> None:
    policy = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert len(policy.splitlines()) <= 80
    assert "## 唯一の停止条件" in policy
    assert "1. GitHub 開発操作を除く live 外部作用" in policy
    assert "2. 回復不能な操作" in policy
    for obsolete in (
        "exact SHA",
        "head confirmation",
        "1 Story/PR",
        "gpt-5.6-sol",
        'reasoning_effort = "ultra"',
    ):
        assert obsolete not in policy
