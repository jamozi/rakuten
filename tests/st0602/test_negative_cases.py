"""Hostile closed-boundary tests for the ST-0602 owner builder."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any, Callable, cast

import pytest
import yaml

from scripts import raos_build_core as base
from scripts import (
    build_st0602_fact_extraction_validation_reference_plan as generator,
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
    with pytest.raises(generator.FactExtractionReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("canonical_story_status", "implementation", "IMPLEMENTED"),
        ("canonical_story_status", "verification", "PASS"),
        ("canonical_context", "authority", "AUTHORITATIVE"),
        ("canonical_context", "creates_runtime_contract", True),
        ("canonical_context", "fact_model", "BOUND"),
        ("canonical_context", "extraction_job", "BOUND"),
        ("canonical_context", "fact_event", "BOUND"),
        ("canonical_context", "security_controls", "BOUND"),
        ("input_defaults", "source_snapshot_id", "snapshot-1"),
        ("input_defaults", "artifact_id", "artifact-1"),
        ("input_defaults", "artifact_ref", "s3://bucket/key"),
        ("input_defaults", "subject_id", "subject-1"),
        ("input_defaults", "predicate", "price"),
        ("input_defaults", "unit", "JPY"),
        ("input_defaults", "confidence", 0.9),
        ("input_defaults", "locator", "$.price"),
        ("input_defaults", "extractor", "extractor-v1"),
        ("input_defaults", "manual_review_count", 0),
        ("fact_projection_defaults", "facts", ["fact"]),
        ("fact_projection_defaults", "fact_ids", ["fact-1"]),
        ("fact_projection_defaults", "derivations", ["derived"]),
        ("fact_projection_defaults", "validation_records", ["record"]),
        ("fact_projection_defaults", "manual_review_records", ["review"]),
        ("validation_defaults", "status", "PASS"),
        ("validation_defaults", "unit_validation", "PASS"),
        ("validation_defaults", "time_validation", "PASS"),
        ("validation_defaults", "source_validation", "PASS"),
        ("validation_defaults", "confidence_validation", "PASS"),
        ("validation_defaults", "passed", True),
        ("validation_defaults", "blockers", []),
        ("execution_boundary", "extraction", "EXECUTED"),
        ("execution_boundary", "validation", "EXECUTED"),
        ("execution_boundary", "manual_review", "EXECUTED"),
        ("execution_boundary", "repository", "EXECUTED"),
        ("execution_boundary", "database", "EXECUTED"),
        ("execution_boundary", "job", "EXECUTED"),
        ("execution_boundary", "event", "EXECUTED"),
        ("execution_boundary", "provider", "EXECUTED"),
        ("execution_boundary", "live", "EXECUTED"),
        ("execution_boundary", "external", "EXECUTED"),
        ("verification_boundary", "TST-005", "PASS"),
        ("verification_boundary", "TST-007", "PASS"),
        ("verification_boundary", "formal_validation", "PASS"),
        ("verification_boundary", "staging", "PASS"),
        ("verification_boundary", "release", "PASS"),
        ("verification_boundary", "production", "READY"),
    ],
)
def test_invented_input_fact_execution_or_evidence_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.FactExtractionReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("replacement", [1, False, True, 0.0, "0"])
@pytest.mark.parametrize("action", generator.ACTION_COUNT_KEYS)
def test_non_exact_integer_zero_action_count_is_rejected(
    action: str,
    replacement: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract["execution_boundary"]["action_counts"][action] = replacement
    with pytest.raises(generator.FactExtractionReferenceError):
        generator.validate_contract(contract)


def _remove_top(value: dict[str, Any]) -> None:
    value.pop("input_defaults")


def _add_top(value: dict[str, Any]) -> None:
    value["unknown"] = None


def _add_nested(value: dict[str, Any]) -> None:
    value["input_defaults"]["unknown"] = None


def _reverse_predecessors(value: dict[str, Any]) -> None:
    value["predecessors"].reverse()


def _reverse_actions(value: dict[str, Any]) -> None:
    counts = value["execution_boundary"]["action_counts"]
    value["execution_boundary"]["action_counts"] = dict(reversed(tuple(counts.items())))


@pytest.mark.parametrize(
    "mutation",
    [_remove_top, _add_top, _add_nested, _reverse_predecessors, _reverse_actions],
)
def test_missing_unknown_and_reordered_keys_are_rejected(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    mutation(contract)
    with pytest.raises(generator.FactExtractionReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "payload",
    [
        b"story_id: ST-0602\nstory_id: ST-0602\n",
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
        (generator.FactExtractionReferenceError, base.StagingDeploymentContractError)
    ):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(
        (generator.FactExtractionReferenceError, base.StagingDeploymentContractError)
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


def test_canonical_authority_byte_drift_is_rejected(
    isolated_repository: Path,
) -> None:
    path = isolated_repository / generator.STORY_PATH
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.FactExtractionReferenceError):
        generator.render_outputs(isolated_repository)


def test_predecessor_readmes_are_semantic_not_digest_bound(
    isolated_repository: Path,
) -> None:
    for relative in (
        generator.ST0601_ARTIFACTS[0][0],
        generator.ST0503_ARTIFACTS[0][0],
    ):
        path = isolated_repository / relative
        path.write_bytes(path.read_bytes() + b"\neditorial note\n")
    assert generator.render_outputs(isolated_repository)


def _rebind_predecessor_digest(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    artifact_name: str,
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
    row = next(
        item
        for item in contract["predecessors"]
        if item["story_id"]
        == ("ST-0601" if artifact_name == "ST0601_ARTIFACTS" else "ST-0503")
    )
    next(item for item in row["files"] if item["path"] == relative.as_posix())[
        "sha256"
    ] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )


def test_st0601_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = generator.ST0601_ARTIFACTS[1][0]
    path = isolated_repository / relative
    text = path.read_text(encoding="utf-8").replace(
        'NOT_READY = "NOT_READY"', 'NOT_READY = "READY"', 1
    )
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _rebind_predecessor_digest(
        isolated_repository,
        monkeypatch,
        artifact_name="ST0601_ARTIFACTS",
        relative=relative,
        digest=digest,
    )
    with pytest.raises(generator.FactExtractionReferenceError):
        generator.render_outputs(isolated_repository)


def test_st0503_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = generator.ST0503_ARTIFACTS[1][0]
    path = isolated_repository / relative
    text = path.read_text(encoding="utf-8").replace(
        'SOURCE_ABSENT = "SOURCE_ABSENT"', 'SOURCE_ABSENT = "INFERRED"', 1
    )
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _rebind_predecessor_digest(
        isolated_repository,
        monkeypatch,
        artifact_name="ST0503_ARTIFACTS",
        relative=relative,
        digest=digest,
    )
    with pytest.raises(generator.FactExtractionReferenceError):
        generator.render_outputs(isolated_repository)


def test_canonical_story_semantic_drift_is_rejected_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story_path = isolated_repository / generator.STORY_PATH
    story_text = story_path.read_text(encoding="utf-8").replace(
        "- id: ST-0602\n  epic_id: EPIC-06",
        "- id: ST-0602\n  epic_id: EPIC-CHANGED",
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
    with pytest.raises(generator.FactExtractionReferenceError):
        generator.render_outputs(isolated_repository)
