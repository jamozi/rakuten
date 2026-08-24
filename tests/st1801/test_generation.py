from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts import build_st1801_portfolio_expansion as builder


def test_owner_outputs_are_deterministic() -> None:
    first = builder.render_outputs()
    second = builder.render_outputs()
    assert first == second
    assert tuple(first) == builder.GENERATED_PATHS


def test_checked_in_outputs_match_owner() -> None:
    expected = builder.render_outputs()
    for path, content in expected.items():
        assert (builder.REPO_ROOT / path).read_bytes() == content


def test_generated_pack_is_closed_and_blocked() -> None:
    pack = json.loads((builder.REPO_ROOT / builder.PACK_PATH).read_text())
    contract = builder.load_contract()
    builder.validate_portfolio_record(pack, contract)
    assert pack["story"]["id"] == "ST-1801"
    assert pack["decision"]["overall"] == "BLOCKED"
    assert pack["decision"]["downstream_gate_1_eligible"] is False
    assert pack["actual_observations"] == []
    assert pack["qualifying_evidence_references"] == []


def test_manifest_binds_sources_dependencies_and_pack() -> None:
    manifest = yaml.safe_load((builder.REPO_ROOT / builder.MANIFEST_PATH).read_text())
    assert manifest["story_id"] == "ST-1801"
    assert manifest["source_artifact_count"] == len(builder.SOURCE_PATHS)
    assert manifest["bound_input_count"] == len(builder.EXPECTED_SOURCE_HASHES) + len(
        builder.EXPECTED_DEPENDENCY_HASHES
    )
    pack = (builder.REPO_ROOT / builder.PACK_PATH).read_bytes()
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{builder.PACK_PATH.as_posix()}",
            "bytes": len(pack),
            "sha256": builder._sha256(pack),
        }
    ]
    assert manifest["boundary"]["decision"] == "BLOCKED"
    assert manifest["boundary"]["actual_articles"] == "UNAVAILABLE"


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
    "checkpoint", ["PREPARED", f"PUBLISHED_{builder.PACK_PATH.as_posix()}", "COMMITTED"]
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
        "st1801.next" in path.name
        or "st1801.previous" in path.name
        or "st1801.absent" in path.name
        or "transaction" in path.name
        for path in generated.iterdir()
    )


def test_replace_failure_is_sanitized_and_rolls_back(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)
    originals = {
        path: (repository_copy / path).read_bytes() for path in builder.GENERATED_PATHS
    }

    def fail_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(builder.os, "replace", fail_replace)
    with pytest.raises(
        builder.PortfolioExpansionError, match="OUTPUT_TRANSACTION_FAILED"
    ):
        builder.build(repository_copy)

    for path, content in originals.items():
        assert (repository_copy / path).read_bytes() == content
    generated = repository_copy / builder.PACK_PATH.parent
    assert not any(
        "st1801.next" in path.name
        or "st1801.previous" in path.name
        or "st1801.absent" in path.name
        or "transaction" in path.name
        for path in generated.iterdir()
    )
