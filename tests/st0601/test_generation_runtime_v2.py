"""Owner contract generation, provenance, and status-boundary checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from raos.domain.ops.artifact_registry_runtime_v2 import (
    ARTIFACT_REGISTRY_CONTRACT_SHA256_V2,
)
from scripts import build_st0601_artifact_registry_runtime as generator


def _tree_snapshot(root: Path) -> tuple[tuple[str, int, int, str], ...]:
    result: list[tuple[str, int, int, str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            data = path.read_bytes()
            result.append(
                (
                    path.relative_to(root).as_posix(),
                    path.stat().st_mode,
                    path.stat().st_mtime_ns,
                    hashlib.sha256(data).hexdigest(),
                )
            )
    return tuple(result)


def test_committed_generated_ir_is_byte_exact_and_check_is_no_write() -> None:
    before = _tree_snapshot(generator.REPOSITORY_ROOT / "changes/st-0601")

    assert generator.main(["--check"]) == 0

    after = _tree_snapshot(generator.REPOSITORY_ROOT / "changes/st-0601")
    assert after == before
    assert generator.OUTPUT_PATH.read_bytes() == generator.render()


def test_generated_ir_binds_contract_generator_sources_and_authority() -> None:
    value = json.loads(generator.render())

    assert value["contract_sha256"] == ARTIFACT_REGISTRY_CONTRACT_SHA256_V2
    assert value["owner_generator"] == {
        "path": "scripts/build_st0601_artifact_registry_runtime.py",
        "sha256": hashlib.sha256(generator.GENERATOR_PATH.read_bytes()).hexdigest(),
    }
    assert value["document"]["status"] == "LOCAL_CODE_COMPLETE"
    assert value["document"]["formal_tst_014"] == "NOT_EXECUTED"
    assert value["authority"]["external_operation"] == "NOT_GRANTED"
    assert value["authority"]["formal_validation"] == "NOT_GRANTED"
    assert value["authority"]["publication"] == "NOT_GRANTED"
    assert value["authority"]["production"] == "NOT_GRANTED"
    assert value["runtime"]["retention"] == {
        "decision": "OD_014_UNRESOLVED",
        "retention_class": None,
        "retention_period": None,
        "default": None,
        "lifecycle": "ABSENT",
        "delete": "ABSENT",
        "purge": "ABSENT",
    }
    assert set(value["runtime"]["action_counts"].values()) == {0}
    assert len(value["sources"]) == 9
    for source in value["sources"]:
        path = generator.REPOSITORY_ROOT / source["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]


def test_generator_rejects_local_promotion_of_formal_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = yaml.safe_load(generator.CONTRACT_PATH.read_text(encoding="utf-8"))
    contract["document"]["formal_tst_014"] = "PASS"
    candidate = tmp_path / "candidate.yaml"
    candidate.write_text(
        yaml.safe_dump(contract, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(generator, "CONTRACT_PATH", candidate)

    with pytest.raises(generator.GenerationFailure, match="status boundary"):
        generator.render()


def test_generator_rejects_source_digest_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = yaml.safe_load(generator.CONTRACT_PATH.read_text(encoding="utf-8"))
    contract["sources"][0]["sha256"] = "0" * 64
    candidate = tmp_path / "candidate.yaml"
    candidate.write_text(
        yaml.safe_dump(contract, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    monkeypatch.setattr(generator, "CONTRACT_PATH", candidate)
    monkeypatch.setattr(
        generator,
        "ARTIFACT_REGISTRY_CONTRACT_SHA256_V2",
        candidate_hash,
    )

    with pytest.raises(generator.GenerationFailure, match="source drift"):
        generator.render()
