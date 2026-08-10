"""Hostile closed-boundary tests for the ST-0603 owner builder."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, cast

import pytest
import yaml

from scripts import build_st1505_staging_deployment as base
from scripts import (
    build_st0603_fact_conflict_review_reference_plan as generator,
)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "READY"),
        ("executable", True),
        ("interface_only", False),
        ("decision", "READY"),
        ("production_eligible", True),
        ("approval", "approved"),
        ("story_acceptance", True),
    ],
)
def test_false_top_level_execution_or_completion_claim_is_rejected(
    field: str,
    value: object,
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract[field] = value
    with pytest.raises(generator.FactConflictReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("canonical_story_status", "implementation", "IMPLEMENTED"),
        ("canonical_story_status", "verification", "PASS"),
        ("canonical_context", "authority", "AUTHORITATIVE"),
        ("canonical_context", "creates_runtime_contract", True),
        ("canonical_context", "conflict_policy", "BOUND"),
        ("canonical_context", "evidence_requirement", "ATTESTED"),
        ("canonical_context", "security_controls", "BOUND"),
        ("input_defaults", "facts", ["fact"]),
        ("input_defaults", "fact_ids", ["fact-1"]),
        ("input_defaults", "fact_count", 0),
        ("selection_defaults", "conflict_rule", "exact"),
        ("selection_defaults", "comparator", "equals"),
        ("selection_defaults", "tolerance", 0),
        ("selection_defaults", "source", "source-1"),
        ("selection_defaults", "value", "value-1"),
        ("selection_defaults", "severity", "HIGH"),
        ("selection_defaults", "actor", "reviewer-1"),
        ("selection_defaults", "queue_selection", "conflicts"),
        ("selection_defaults", "resolution_policy", "newest-wins"),
        ("projection_defaults", "comparisons", ["comparison"]),
        ("projection_defaults", "conflicts", ["conflict"]),
        ("projection_defaults", "findings", ["finding"]),
        ("projection_defaults", "queue", ["queue-item"]),
        ("projection_defaults", "resolutions", ["resolution"]),
        ("projection_defaults", "comparison_count", 0),
        ("projection_defaults", "conflict_count", 0),
        ("projection_defaults", "finding_count", 0),
        ("projection_defaults", "queue_count", 0),
        ("projection_defaults", "resolution_count", 0),
        ("review_and_resolution_defaults", "comparison_status", "EXECUTED"),
        ("review_and_resolution_defaults", "queue_status", "EXECUTED"),
        ("review_and_resolution_defaults", "resolution_status", "EXECUTED"),
        ("review_and_resolution_defaults", "automatic_resolution_enabled", True),
        ("review_and_resolution_defaults", "silent_resolution_allowed", True),
        ("review_and_resolution_defaults", "blockers", []),
        ("execution_boundary", "detector", "EXECUTED"),
        ("execution_boundary", "comparison", "EXECUTED"),
        ("execution_boundary", "review_queue", "EXECUTED"),
        ("execution_boundary", "resolution", "EXECUTED"),
        ("execution_boundary", "repository", "EXECUTED"),
        ("execution_boundary", "database", "EXECUTED"),
        ("execution_boundary", "event", "EXECUTED"),
        ("execution_boundary", "api", "EXECUTED"),
        ("execution_boundary", "ui", "EXECUTED"),
        ("execution_boundary", "external", "EXECUTED"),
        ("verification_boundary", "predecessor_connection", "CONNECTED"),
        ("verification_boundary", "TST-007", "PASS"),
        ("verification_boundary", "TST-020", "PASS"),
        ("verification_boundary", "formal_validation", "PASS"),
        ("verification_boundary", "staging", "PASS"),
        ("verification_boundary", "release", "PASS"),
        ("verification_boundary", "production", "READY"),
    ],
)
def test_invented_fact_conflict_selection_execution_or_evidence_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.FactConflictReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("replacement", [1, False, True, 0.0, "0"])
@pytest.mark.parametrize("action", generator.ACTION_COUNT_KEYS)
def test_non_exact_integer_zero_action_count_is_rejected(
    action: str,
    replacement: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract["execution_boundary"]["action_counts"][action] = replacement
    with pytest.raises(generator.FactConflictReferenceError):
        generator.validate_contract(contract)


def _remove_top(value: dict[str, Any]) -> None:
    value.pop("selection_defaults")


def _add_top(value: dict[str, Any]) -> None:
    value["unknown"] = None


def _add_nested(value: dict[str, Any]) -> None:
    value["selection_defaults"]["unknown"] = None


def _reverse_predecessor_files(value: dict[str, Any]) -> None:
    value["predecessor"]["files"].reverse()


def _reverse_actions(value: dict[str, Any]) -> None:
    counts = value["execution_boundary"]["action_counts"]
    value["execution_boundary"]["action_counts"] = dict(reversed(tuple(counts.items())))


@pytest.mark.parametrize(
    "mutation",
    [_remove_top, _add_top, _add_nested, _reverse_predecessor_files, _reverse_actions],
)
def test_missing_unknown_and_reordered_keys_are_rejected(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    mutation(contract)
    with pytest.raises(generator.FactConflictReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "payload",
    [
        b"story_id: ST-0603\nstory_id: ST-0603\n",
        b"schema_version: &shared 1\nstory_id: *shared\n",
        b"schema_version: !!python/object/apply:os.system [id]\n",
        b"base: &base {executable: false}\nmerged: {<<: *base}\n",
    ],
)
def test_yaml_duplicate_alias_tag_and_merge_are_rejected(
    isolated_repository: Path,
    payload: bytes,
) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(payload)
    with pytest.raises(
        (generator.FactConflictReferenceError, base.StagingDeploymentContractError)
    ):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(
        (generator.FactConflictReferenceError, base.StagingDeploymentContractError)
    ):
        generator.load_contract(isolated_repository)


def test_symlink_contract_or_ancestor_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    contract = isolated_repository / generator.CONTRACT_PATH
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(outside)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)
    contract.unlink()
    outside.replace(contract)
    changes = isolated_repository / "changes"
    moved = tmp_path / "changes"
    changes.rename(moved)
    changes.symlink_to(moved, target_is_directory=True)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


@pytest.mark.parametrize("relative", generator.GENERATED_PATHS)
def test_output_symlink_target_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
    relative: Path,
) -> None:
    target = isolated_repository / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / f"outside-{target.name}"
    outside.write_bytes(b"outside")
    target.symlink_to(outside)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.build(isolated_repository)
    assert outside.read_bytes() == b"outside"


def test_output_symlink_ancestor_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    generated = isolated_repository / generator.REFERENCE_PLAN_PATH.parent
    outside = tmp_path / "generated"
    outside.mkdir()
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.symlink_to(outside, target_is_directory=True)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.build(isolated_repository)
    assert not tuple(outside.iterdir())


def test_path_traversal_is_rejected(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


@pytest.mark.parametrize(
    "relative",
    [
        generator.STORY_PATH,
        *(path for path, _digest in generator.PREDECESSOR_ARTIFACTS),
    ],
)
def test_authority_or_predecessor_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.FactConflictReferenceError):
        generator.render_outputs(isolated_repository)


def _rebind_predecessor_digest(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    relative: Path,
    digest: str,
) -> None:
    rebound = tuple(
        (candidate, digest if candidate == relative else expected)
        for candidate, expected in generator.PREDECESSOR_ARTIFACTS
    )
    monkeypatch.setattr(generator, "PREDECESSOR_ARTIFACTS", rebound)
    contract = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    next(
        item
        for item in contract["predecessor"]["files"]
        if item["path"] == relative.as_posix()
    )["sha256"] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )


def test_predecessor_contract_semantic_drift_fails_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = generator.PREDECESSOR_ARTIFACTS[1][0]
    path = isolated_repository / relative
    predecessor = yaml.safe_load(path.read_bytes())
    predecessor["input_defaults"]["subject_id"] = "subject-1"
    path.write_text(yaml.safe_dump(predecessor, sort_keys=False), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _rebind_predecessor_digest(
        isolated_repository, monkeypatch, relative=relative, digest=digest
    )
    with pytest.raises(generator.FactConflictReferenceError):
        generator.render_outputs(isolated_repository)


def test_predecessor_plan_semantic_drift_fails_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = generator.PREDECESSOR_ARTIFACTS[2][0]
    path = isolated_repository / relative
    predecessor = json.loads(path.read_bytes())
    predecessor["fact_projection"]["facts"] = ["fact"]
    path.write_text(json.dumps(predecessor, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _rebind_predecessor_digest(
        isolated_repository, monkeypatch, relative=relative, digest=digest
    )
    with pytest.raises(generator.FactConflictReferenceError):
        generator.render_outputs(isolated_repository)


def test_canonical_story_semantic_drift_fails_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story_path = isolated_repository / generator.STORY_PATH
    story_text = story_path.read_text(encoding="utf-8").replace(
        "- id: ST-0603\n  epic_id: EPIC-06",
        "- id: ST-0603\n  epic_id: EPIC-CHANGED",
        1,
    )
    story_path.write_text(story_text, encoding="utf-8")
    digest = hashlib.sha256(story_path.read_bytes()).hexdigest()
    monkeypatch.setattr(generator, "STORY_SHA256", digest)
    contract = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    contract["authority"]["canonical_story_sha256"] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(generator.FactConflictReferenceError):
        generator.render_outputs(isolated_repository)
