from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import pytest

from scripts import (
    build_st0708_openai_live_bounded_evaluation_reference_plan as generator,
)
from scripts import secure_generated_publication as publication
from tests.st0708_v2.support import ROOT


def test_owner_generator_is_deterministic_and_no_write_check_passes() -> None:
    generator.build(ROOT, check=True)
    first = generator.render_outputs(ROOT)
    second = generator.render_outputs(ROOT)
    assert first == second
    assert tuple(first) == generator.GENERATED_PATHS
    assert {
        path: hashlib.sha256(payload).hexdigest() for path, payload in first.items()
    } == {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in first
    }


def test_runtime_manifest_binds_exact_helper_sources_and_formal_nonexecution() -> None:
    manifest = json.loads((ROOT / generator.RUNTIME_MANIFEST_PATH).read_bytes())
    assert manifest["document"]["status"] == "LOCAL_IMPLEMENTATION_COMPLETE"
    assert manifest["helper"] == {
        "path": "scripts/secure_generated_publication.py",
        "sha256": generator.HELPER_SHA256,
    }
    assert (
        manifest["source_sha256"]["scripts/secure_generated_publication.py"]
        == generator.HELPER_SHA256
    )
    assert manifest["formal_status"] == {
        "formal_tst_018": "NOT_EXECUTED",
        "live": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
    }
    for relative, digest in manifest["generated_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


def test_generated_report_is_proposal_only_incomplete_evidence_refusal() -> None:
    root = json.loads((ROOT / generator.REPORT_PATH).read_bytes())
    report = root["report"]
    assert root["document"]["status"] == "LOCAL_IMPLEMENTATION_COMPLETE"
    assert report["decision_kind"] == "PROPOSAL"
    assert report["authority"] == "NONE"
    assert report["outcome"] == "REFUSED_INCOMPLETE_EVIDENCE"
    assert all(item["status"] == "UNAVAILABLE" for item in report["metrics"])
    assert all(item["status"] == "UNAVAILABLE" for item in report["zero_tolerance"])
    assert all(value is False for value in report["operational_authority"].values())


def test_multi_output_publication_preserves_foreign_files() -> None:
    with tempfile.TemporaryDirectory(prefix=".st0708-publish-", dir=ROOT) as raw:
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
            namespace="st0708",
            maximum_payload_bytes=generator.MAX_SOURCE_BYTES,
        )
        assert [path.read_bytes() for path in destinations] == [
            b"new-0",
            b"new-1",
            b"new-2",
        ]
        assert foreign.read_bytes() == b"foreign-owner-material"


def test_multi_output_publication_rolls_back_every_owned_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix=".st0708-rollback-", dir=ROOT) as raw:
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
                namespace="st0708",
                maximum_payload_bytes=generator.MAX_SOURCE_BYTES,
            )
        assert tuple(path.read_bytes() for path in destinations) == originals


def test_existing_target_race_preserves_foreign_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix=".st0708-target-", dir=ROOT) as raw:
        tmp_path = Path(raw)
        destination = tmp_path / "target.json"
        foreign = tmp_path / "foreign.json"
        destination.write_bytes(b"owner-before")
        foreign.write_bytes(b"foreign-racer")
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
                ((destination.resolve(), b"owner-after"),),
                namespace="st0708",
                maximum_payload_bytes=generator.MAX_SOURCE_BYTES,
            )
        assert destination.read_bytes() == b"foreign-racer"


def test_missing_target_race_is_no_clobber(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix=".st0708-missing-", dir=ROOT) as raw:
        tmp_path = Path(raw)
        destination = tmp_path / "target.json"
        real_link = os.link
        raced = False

        def race_then_link(*args: Any, **kwargs: Any) -> None:
            nonlocal raced
            if not raced:
                raced = True
                destination.write_bytes(b"foreign-racer")
            real_link(*args, **kwargs)

        monkeypatch.setattr(os, "link", race_then_link)
        with pytest.raises(publication.SecurePublicationError):
            publication.publish_generated(
                ((destination.resolve(), b"owner-after"),),
                namespace="st0708",
                maximum_payload_bytes=generator.MAX_SOURCE_BYTES,
            )
        assert destination.read_bytes() == b"foreign-racer"


def test_parent_swap_refuses_replacement_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix=".st0708-parent-", dir=ROOT) as raw:
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
                namespace="st0708",
                maximum_payload_bytes=generator.MAX_SOURCE_BYTES,
            )
        assert (owned / "target.json").read_bytes() == b"attacker-before"
        assert (held / "target.json").read_bytes() == b"owner-before"
