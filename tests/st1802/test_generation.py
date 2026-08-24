from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts import build_st1802_gate1_decision as builder


def test_owner_outputs_are_deterministic() -> None:
    first = builder.render_outputs()
    second = builder.render_outputs()
    assert first == second
    assert tuple(first) == builder.GENERATED_PATHS


def test_checked_in_outputs_match_owner() -> None:
    expected = builder.render_outputs()
    for path, content in expected.items():
        assert (builder.REPO_ROOT / path).read_bytes() == content


def test_generated_evaluation_is_closed_non_attesting() -> None:
    record = json.loads((builder.REPO_ROOT / builder.EVALUATION_PATH).read_text())
    builder.validate_evaluation_record(record)
    assert record["classification"] == builder.SYNTHETIC_CLASSIFICATION
    assert record["dependency_context"] == {
        "story_id": "ST-1801",
        "uri": "repo://changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json",
        "sha256": builder.EXPECTED_DEPENDENCY_HASHES[
            "changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json"
        ],
        "decision": "BLOCKED",
        "dependency_eligibility": "NOT_ELIGIBLE",
        "planned_synthetic_placeholder_count": 30,
        "actual_article_count": "UNAVAILABLE",
        "placeholders_are_actual_articles": False,
    }
    assert record["qualifying_evidence_references"] == []
    assert record["formal_evidence_eligible"] is False
    assert record["gate_evidence_eligible"] is False
    assert record["authority"] == "NONE"


def test_generated_evaluation_rejects_nested_unknown_fields() -> None:
    record = json.loads((builder.REPO_ROOT / builder.EVALUATION_PATH).read_text())
    record["dependency_context"]["invented"] = True
    with pytest.raises(builder.Gate1DecisionError, match="UNKNOWN_OR_MISSING_FIELD"):
        builder.validate_evaluation_record(record)


def test_generated_pack_is_closed_and_blocked() -> None:
    pack = json.loads((builder.REPO_ROOT / builder.PACK_PATH).read_text())
    builder.validate_gate_pack(pack)
    assert pack["decision"]["overall"] == "BLOCKED"
    assert pack["decision"]["eligibility"] == "NOT_ELIGIBLE"


def test_manifest_binds_sources_inputs_and_generated_artifacts() -> None:
    manifest = yaml.safe_load((builder.REPO_ROOT / builder.MANIFEST_PATH).read_text())
    assert manifest["story_id"] == "ST-1802"
    assert manifest["source_artifact_count"] == len(builder.SOURCE_PATHS)
    assert manifest["bound_input_count"] == len(builder.EXPECTED_SOURCE_HASHES) + len(
        builder.EXPECTED_DEPENDENCY_HASHES
    )
    assert manifest["generated_artifact_count"] == 2
    for index, path in enumerate((builder.EVALUATION_PATH, builder.PACK_PATH)):
        content = (builder.REPO_ROOT / path).read_bytes()
        assert manifest["generated_artifacts"][index] == {
            "uri": f"repo://{path.as_posix()}",
            "bytes": len(content),
            "sha256": builder._sha256(content),
        }
    assert manifest["boundary"]["decision"] == "BLOCKED"
    assert manifest["boundary"]["eligibility"] == "NOT_ELIGIBLE"


def test_check_is_read_only() -> None:
    before = {
        path: (
            (builder.REPO_ROOT / path).read_bytes(),
            (builder.REPO_ROOT / path).stat().st_mtime_ns,
        )
        for path in builder.GENERATED_PATHS
    }
    builder.build(check=True)
    after = {
        path: (
            (builder.REPO_ROOT / path).read_bytes(),
            (builder.REPO_ROOT / path).stat().st_mtime_ns,
        )
        for path in builder.GENERATED_PATHS
    }
    assert after == before


class SimulatedCrash(BaseException):
    pass


@pytest.mark.parametrize(
    "checkpoint",
    [
        "PREPARED",
        f"PUBLISHED_{builder.EVALUATION_PATH.as_posix()}",
        f"PUBLISHED_{builder.PACK_PATH.as_posix()}",
        "COMMITTED",
    ],
)
def test_interrupted_transaction_recovers_atomically(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch, checkpoint: str
) -> None:
    def crash(name: str) -> None:
        if name == checkpoint:
            raise SimulatedCrash

    monkeypatch.setattr(builder, "_transaction_checkpoint", crash)
    with pytest.raises(SimulatedCrash):
        builder.build(repository_copy)
    assert (
        repository_copy / builder.PACK_PATH.parent / builder.TRANSACTION_NAME
    ).exists()

    monkeypatch.setattr(builder, "_transaction_checkpoint", lambda _name: None)
    builder.build(repository_copy)
    expected = builder.render_outputs(repository_copy)
    for path, content in expected.items():
        assert (repository_copy / path).read_bytes() == content
    generated = repository_copy / builder.PACK_PATH.parent
    assert not any(
        "st1802.next" in path.name
        or "st1802.previous" in path.name
        or "st1802.absent" in path.name
        or "transaction" in path.name
        for path in generated.iterdir()
    )


def test_replace_failure_rolls_back_without_partial_outputs(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)
    originals = {
        path: (repository_copy / path).read_bytes() for path in builder.GENERATED_PATHS
    }

    def fail_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(builder.os, "replace", fail_replace)
    with pytest.raises(builder.Gate1DecisionError, match="OUTPUT_TRANSACTION_FAILED"):
        builder.build(repository_copy)
    for path, content in originals.items():
        assert (repository_copy / path).read_bytes() == content


def test_check_refuses_pending_recovery_without_writing(repository_copy: Path) -> None:
    output = repository_copy / builder.PACK_PATH.parent
    journal = output / builder.TRANSACTION_NAME
    journal.write_text("{}\n")
    journal.chmod(0o600)
    before = journal.read_bytes()
    with pytest.raises(builder.Gate1DecisionError, match="OUTPUT_RECOVERY_REQUIRED"):
        builder.build(repository_copy, check=True)
    assert journal.read_bytes() == before
