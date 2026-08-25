from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

import pytest

from raos.domain.ai.evaluation_harness import TRUSTED_RUNTIME_CONTRACT_SHA256
from scripts import build_st0707_evaluation_harness_runtime as generator
from scripts import secure_generated_publication as publication
from tests.st0707_runtime.support import PATHS, ROOT


def test_owner_generator_is_deterministic_and_no_write_check_passes() -> None:
    generator.build(ROOT, check=True)
    first = generator.render_outputs(generator._contract(ROOT), ROOT)
    second = generator.render_outputs(generator._contract(ROOT), ROOT)
    assert first == second
    assert {
        path: hashlib.sha256(payload).hexdigest() for path, payload in first.items()
    } == {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in first
    }


def test_runtime_contract_and_all_dependency_artifacts_are_exactly_bound() -> None:
    assert (
        hashlib.sha256(PATHS["runtime_contract_bytes"].read_bytes()).hexdigest()
        == TRUSTED_RUNTIME_CONTRACT_SHA256
    )
    manifest = json.loads(PATHS["runtime_manifest_bytes"].read_bytes())
    source = manifest["source_sha256"]
    for path in PATHS.values():
        relative = path.relative_to(ROOT).as_posix()
        if relative in source:
            assert source[relative] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest["formal_status"] == {
        "formal_tst_018": "NOT_EXECUTED",
        "formal_tst_019": "NOT_EXECUTED",
        "live": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
    }


def test_generated_dataset_has_closed_synthetic_nonrelease_provenance() -> None:
    root = json.loads(PATHS["dataset_bytes"].read_bytes())
    dataset = root["dataset"]
    assert dataset["status"] == "LOCKED_SYNTHETIC_NON_RELEASE"
    assert dataset["provenance"] == "SYNTHETIC_PLUMBING_ONLY"
    assert dataset["source_kind"] == "GENERATED_RECORDED_SYNTHETIC"
    assert dataset["label_provenance"] == []
    assert dataset["human_label_status"] == "UNAVAILABLE"
    for name in (
        "release_eligible",
        "canonical_dataset",
        "representative_dataset",
        "human_labeled",
    ):
        assert dataset[name] is False
    assert len(dataset["cases"]) == 1
    assert dataset["cases"][0]["split"] == "HOLDOUT"
    evaluation_case = dataset["cases"][0]["evaluation_case"]
    assert evaluation_case["case_id"] == dataset["cases"][0]["case_id"]
    assert evaluation_case["task_code"] == "ai.opportunity_assessment.v1"
    assert evaluation_case["dataset_version"] == dataset["version"]
    assert evaluation_case["split"] == "HOLDOUT"
    assert evaluation_case["risk_level"] == "HIGH"
    assert evaluation_case["gold_artifact"] is None
    assert evaluation_case["tags"] == ["synthetic", "plumbing", "nonrelease"]


def test_multi_output_publication_preserves_foreign_files() -> None:
    with tempfile.TemporaryDirectory(prefix=".st0707-publish-", dir=ROOT) as raw:
        tmp_path = Path(raw)
        destinations = tuple(
            tmp_path / name for name in ("one.json", "two.json", "three.json")
        )
        for index, destination in enumerate(destinations):
            destination.write_bytes(f"old-{index}".encode())
        foreign = tmp_path / "foreign-owner.txt"
        foreign.write_bytes(b"foreign-owner-material")
        publication.publish_generated(
            tuple(
                (destination.resolve(), f"new-{index}".encode())
                for index, destination in enumerate(destinations)
            ),
            namespace="st0707",
            maximum_payload_bytes=generator.MAX_SOURCE_BYTES,
        )
        assert [path.read_bytes() for path in destinations] == [
            b"new-0",
            b"new-1",
            b"new-2",
        ]
        assert foreign.read_bytes() == b"foreign-owner-material"
        assert not tuple(path for path in tmp_path.iterdir() if ".st0705-" in path.name)


def test_multi_output_publication_rolls_back_every_owned_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix=".st0707-rollback-", dir=ROOT) as raw:
        tmp_path = Path(raw)
        destinations = tuple(
            tmp_path / name for name in ("one.json", "two.json", "three.json")
        )
        originals = (b"old-one", b"old-two", b"old-three")
        for destination, payload in zip(destinations, originals, strict=True):
            destination.write_bytes(payload)
        real_commit = publication._commit_stage
        calls = 0

        def fail_second(stage: publication._StagedOutput) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected transaction failure")
            real_commit(stage)

        monkeypatch.setattr(publication, "_commit_stage", fail_second)
        with pytest.raises(publication.SecurePublicationError):
            publication.publish_generated(
                tuple((path.resolve(), b"replacement") for path in destinations),
                namespace="st0707",
                maximum_payload_bytes=generator.MAX_SOURCE_BYTES,
            )
        assert tuple(path.read_bytes() for path in destinations) == originals
        assert not tuple(path for path in tmp_path.iterdir() if ".st0705-" in path.name)


def test_target_toctou_preserves_the_foreign_racing_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix=".st0707-toctou-", dir=ROOT) as raw:
        tmp_path = Path(raw)
        destination = tmp_path / "one.json"
        foreign = tmp_path / "foreign.json"
        destination.write_bytes(b"old-owner-value")
        foreign.write_bytes(b"foreign-racer-value")
        real_exchange = publication._rename_exchange
        calls = 0

        def race_then_exchange(parent_descriptor: int, left: str, right: str) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                os.replace(foreign, destination)
            real_exchange(parent_descriptor, left, right)

        monkeypatch.setattr(publication, "_rename_exchange", race_then_exchange)
        with pytest.raises(publication.SecurePublicationError):
            publication.publish_generated(
                ((destination.resolve(), b"new-owner-value"),),
                namespace="st0707",
                maximum_payload_bytes=generator.MAX_SOURCE_BYTES,
            )
        assert calls >= 2
        assert destination.read_bytes() == b"foreign-racer-value"


def test_parent_swap_is_refused_without_writing_the_replacement_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix=".st0707-parent-", dir=ROOT) as raw:
        base = Path(raw)
        owned = base / "owned"
        attacker = base / "attacker"
        held = base / "held"
        owned.mkdir()
        attacker.mkdir()
        target = owned / "target.json"
        target.write_bytes(b"owner-before")
        (attacker / "target.json").write_bytes(b"attacker-before")
        real_validate = publication._validate_directories
        calls = 0

        def swap_parent(
            bindings: tuple[publication._DirectoryBinding, ...],
        ) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                owned.rename(held)
                attacker.rename(owned)
            real_validate(bindings)

        monkeypatch.setattr(publication, "_validate_directories", swap_parent)
        with pytest.raises(publication.SecurePublicationError):
            publication.publish_generated(
                ((target.resolve(), b"owner-after"),),
                namespace="st0707",
                maximum_payload_bytes=generator.MAX_SOURCE_BYTES,
            )
        assert (owned / "target.json").read_bytes() == b"attacker-before"
        assert (held / "target.json").read_bytes() == b"owner-before"
