"""Hostile closed-boundary tests for the ST-0604 owner builder."""

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
    build_st0604_source_packet_lifecycle_reference_plan as generator,
)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "READY"),
        ("executable", True),
        ("interface_only", False),
        ("decision", "READY"),
        ("production_eligible", True),
        ("approval", True),
        ("story_acceptance", True),
        ("generation_permitted", True),
    ],
)
def test_false_top_level_execution_approval_or_completion_claim_is_rejected(
    field: str,
    value: object,
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract[field] = value
    with pytest.raises(generator.SourcePacketReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("canonical_story_status", "implementation", "IMPLEMENTED"),
        ("canonical_story_status", "verification", "PASS"),
        ("vocabulary_context", "authority", "AUTHORITATIVE"),
        ("vocabulary_context", "creates_runtime_contract", True),
        ("vocabulary_context", "inferred_mappings", ["packet=version"]),
        ("selection_defaults", "packet_id", "packet-1"),
        ("selection_defaults", "packet_status", "DRAFT"),
        ("selection_defaults", "version_id", "version-1"),
        ("selection_defaults", "version_status", "READY"),
        ("selection_defaults", "job_id", "job-1"),
        ("selection_defaults", "job_status", "QUEUED"),
        ("selection_defaults", "reviewer", "reviewer-1"),
        ("selection_defaults", "authorization", "allowed"),
        ("selection_defaults", "artifact_id", "artifact-1"),
        ("selection_defaults", "artifact_ref", "s3://bucket/key"),
        ("selection_defaults", "content_hash", "0" * 64),
        ("collection_defaults", "packets", ["packet"]),
        ("collection_defaults", "versions", ["version"]),
        ("collection_defaults", "jobs", ["job"]),
        ("collection_defaults", "transitions", ["transition"]),
        ("collection_defaults", "mappings", ["mapping"]),
        ("collection_defaults", "reviews", ["review"]),
        ("collection_defaults", "approvals", ["approval"]),
        ("collection_defaults", "artifacts", ["artifact"]),
        ("collection_defaults", "packet_count", 0),
        ("collection_defaults", "version_count", 0),
        ("collection_defaults", "job_count", 0),
        ("collection_defaults", "transition_count", 0),
        ("collection_defaults", "mapping_count", 0),
        ("collection_defaults", "review_count", 0),
        ("collection_defaults", "approval_count", 0),
        ("collection_defaults", "artifact_count", 0),
        ("lifecycle_defaults", "transition_status", "AVAILABLE"),
        ("lifecycle_defaults", "mapping_status", "AVAILABLE"),
        ("lifecycle_defaults", "approval", True),
        ("lifecycle_defaults", "generation_permitted", True),
        ("lifecycle_defaults", "blockers", []),
        ("execution_boundary", "packet", "EXECUTED"),
        ("execution_boundary", "version", "EXECUTED"),
        ("execution_boundary", "transition", "EXECUTED"),
        ("execution_boundary", "mapping", "EXECUTED"),
        ("execution_boundary", "review", "EXECUTED"),
        ("execution_boundary", "authorization", "EXECUTED"),
        ("execution_boundary", "artifact", "EXECUTED"),
        ("execution_boundary", "repository", "EXECUTED"),
        ("execution_boundary", "database", "EXECUTED"),
        ("execution_boundary", "job", "EXECUTED"),
        ("execution_boundary", "event", "EXECUTED"),
        ("execution_boundary", "api", "EXECUTED"),
        ("execution_boundary", "approval", "EXECUTED"),
        ("execution_boundary", "generation", "EXECUTED"),
        ("execution_boundary", "external", "EXECUTED"),
        ("verification_boundary", "predecessor_connection", "CONNECTED"),
        ("verification_boundary", "TST-012", "PASS"),
        ("verification_boundary", "TST-020", "PASS"),
        ("verification_boundary", "formal_validation", "PASS"),
        ("verification_boundary", "staging", "PASS"),
        ("verification_boundary", "release", "PASS"),
        ("verification_boundary", "production", "READY"),
    ],
)
def test_invented_selection_collection_lifecycle_execution_or_evidence_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.SourcePacketReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("replacement", [1, False, True, 0.0, "0"])
@pytest.mark.parametrize("action", generator.ACTION_COUNT_KEYS)
def test_non_exact_integer_zero_action_count_is_rejected(
    action: str,
    replacement: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract["execution_boundary"]["action_counts"][action] = replacement
    with pytest.raises(generator.SourcePacketReferenceError):
        generator.validate_contract(contract)


def _remove_top(value: dict[str, Any]) -> None:
    value.pop("selection_defaults")


def _add_top(value: dict[str, Any]) -> None:
    value["unknown"] = None


def _add_nested(value: dict[str, Any]) -> None:
    value["lifecycle_defaults"]["unknown"] = None


def _reverse_predecessors(value: dict[str, Any]) -> None:
    value["predecessors"].reverse()


def _reverse_predecessor_files(value: dict[str, Any]) -> None:
    value["predecessors"][2]["files"].reverse()


def _reverse_actions(value: dict[str, Any]) -> None:
    counts = value["execution_boundary"]["action_counts"]
    value["execution_boundary"]["action_counts"] = dict(reversed(tuple(counts.items())))


@pytest.mark.parametrize(
    "mutation",
    [
        _remove_top,
        _add_top,
        _add_nested,
        _reverse_predecessors,
        _reverse_predecessor_files,
        _reverse_actions,
    ],
)
def test_missing_unknown_and_reordered_keys_are_rejected(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    mutation(contract)
    with pytest.raises(generator.SourcePacketReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "payload",
    [
        b"story_id: ST-0604\nstory_id: ST-0604\n",
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
        (generator.SourcePacketReferenceError, base.StagingDeploymentContractError)
    ):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(
        (generator.SourcePacketReferenceError, base.StagingDeploymentContractError)
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
        *(path for path, _digest in generator.ST0602_ARTIFACTS),
        *(path for path, _digest in generator.ST0603_ARTIFACTS),
        *(path for path, _digest in generator.ST0403_ARTIFACTS),
    ],
)
def test_authority_or_predecessor_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.SourcePacketReferenceError):
        generator.render_outputs(isolated_repository)


def _rebind_predecessor_digest(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    artifact_name: str,
    story_id: str,
    relative: Path,
    digest: str,
) -> None:
    artifacts = getattr(generator, artifact_name)
    rebound = tuple(
        (candidate, digest if candidate == relative else expected)
        for candidate, expected in artifacts
    )
    monkeypatch.setattr(generator, artifact_name, rebound)
    contract = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    predecessor = next(
        row for row in contract["predecessors"] if row["story_id"] == story_id
    )
    next(item for item in predecessor["files"] if item["path"] == relative.as_posix())[
        "sha256"
    ] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )


def test_st0602_semantic_drift_fails_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = generator.ST0602_ARTIFACTS[1][0]
    path = isolated_repository / relative
    predecessor = yaml.safe_load(path.read_bytes())
    predecessor["input_defaults"]["subject_id"] = "subject-1"
    path.write_text(yaml.safe_dump(predecessor, sort_keys=False), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _rebind_predecessor_digest(
        isolated_repository,
        monkeypatch,
        artifact_name="ST0602_ARTIFACTS",
        story_id="ST-0602",
        relative=relative,
        digest=digest,
    )
    with pytest.raises(generator.SourcePacketReferenceError):
        generator.render_outputs(isolated_repository)


def test_st0603_semantic_drift_fails_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = generator.ST0603_ARTIFACTS[2][0]
    path = isolated_repository / relative
    predecessor = json.loads(path.read_bytes())
    predecessor["conflict_projection"]["conflicts"] = ["conflict"]
    path.write_text(json.dumps(predecessor, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _rebind_predecessor_digest(
        isolated_repository,
        monkeypatch,
        artifact_name="ST0603_ARTIFACTS",
        story_id="ST-0603",
        relative=relative,
        digest=digest,
    )
    with pytest.raises(generator.SourcePacketReferenceError):
        generator.render_outputs(isolated_repository)


def test_st0403_semantic_drift_fails_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = generator.ST0403_ARTIFACTS[3][0]
    path = isolated_repository / relative
    text = path.read_text(encoding="utf-8").replace(
        'DISABLED = "DISABLED"', 'DISABLED = "ENABLED"', 1
    )
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _rebind_predecessor_digest(
        isolated_repository,
        monkeypatch,
        artifact_name="ST0403_ARTIFACTS",
        story_id="ST-0403",
        relative=relative,
        digest=digest,
    )
    with pytest.raises(generator.SourcePacketReferenceError):
        generator.render_outputs(isolated_repository)


def test_canonical_story_semantic_drift_fails_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story_path = isolated_repository / generator.STORY_PATH
    story_text = story_path.read_text(encoding="utf-8").replace(
        "- id: ST-0604\n  epic_id: EPIC-06",
        "- id: ST-0604\n  epic_id: EPIC-CHANGED",
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
    with pytest.raises(generator.SourcePacketReferenceError):
        generator.render_outputs(isolated_repository)
