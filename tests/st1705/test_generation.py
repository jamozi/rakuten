from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

import pytest
import yaml

from scripts import build_st1705_pilot_signoff as builder


def _snapshot(root: Path) -> dict[Path, tuple[bytes, int, int, int]]:
    return {
        path.relative_to(root): (
            path.read_bytes(),
            path.stat().st_ino,
            path.stat().st_mtime_ns,
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def _companions(root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for relative in builder.GENERATED_PATHS:
        target = root / relative
        paths.extend(
            (
                target.with_name(f".{target.name}{builder.NEXT_SUFFIX}"),
                target.with_name(f".{target.name}{builder.PREVIOUS_SUFFIX}"),
                target.with_name(f".{target.name}{builder.ABSENT_SUFFIX}"),
            )
        )
    parent = root / builder.MANIFEST_PATH.parent
    paths.extend(
        (parent / builder.TRANSACTION_NAME, parent / builder.TRANSACTION_NEXT_NAME)
    )
    return tuple(paths)


def _assert_no_companions(root: Path) -> None:
    assert not [path for path in _companions(root) if os.path.lexists(path)]


class _Crash(BaseException):
    pass


def test_owner_generation_is_deterministic_and_check_is_no_write(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)
    first = {
        relative: (repository_copy / relative).read_bytes()
        for relative in builder.GENERATED_PATHS
    }
    before = _snapshot(repository_copy)
    builder.build(repository_copy, check=True)
    after = _snapshot(repository_copy)
    assert before == after
    builder.build(repository_copy)
    assert first == {
        relative: (repository_copy / relative).read_bytes()
        for relative in builder.GENERATED_PATHS
    }
    _assert_no_companions(repository_copy)


def test_manifest_records_exact_source_dependency_and_generated_inventory(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)
    manifest = yaml.safe_load((repository_copy / builder.MANIFEST_PATH).read_text())
    assert manifest["story_id"] == "ST-1705"
    assert manifest["source_artifact_count"] == len(builder.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in builder.SOURCE_PATHS
    ]
    assert manifest["bound_input_count"] == len(builder.EXPECTED_SOURCE_HASHES) + len(
        builder.EXPECTED_DEPENDENCY_HASHES
    )
    record_bytes = (repository_copy / builder.DECISION_PATH).read_bytes()
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{builder.DECISION_PATH.as_posix()}",
            "bytes": len(record_bytes),
            "sha256": hashlib.sha256(record_bytes).hexdigest(),
        }
    ]
    assert manifest["boundary"]["decision"] == "BLOCKED"
    assert manifest["boundary"]["sign_off"] == "NOT_SIGNED_OFF"
    assert manifest["boundary"]["pilot_eligibility"] == "NOT_ELIGIBLE"


def test_generated_record_is_non_attesting(repository_copy: Path) -> None:
    builder.build(repository_copy)
    record = json.loads((repository_copy / builder.DECISION_PATH).read_text())
    assert record["classification"] == "LOCAL_BLOCKED_PILOT_SIGNOFF_NON_ATTESTING"
    assert record["decision"]["overall"] == "BLOCKED"
    assert record["decision"]["security_sign_off"] == "NOT_SIGNED_OFF"
    assert record["decision"]["pilot_eligibility"] == "NOT_ELIGIBLE"
    assert record["evidence_boundary"]["validated_claim"] is False
    assert record["authority_boundary"]["production_authority"] == "NONE"


def test_check_detects_output_drift(repository_copy: Path) -> None:
    builder.build(repository_copy)
    (repository_copy / builder.DECISION_PATH).write_text("{}\n")
    with pytest.raises(builder.PilotSignoffError) as error:
        builder.build(repository_copy, check=True)
    assert error.value.code == "GENERATED_OUTPUT_DRIFT"


@pytest.mark.parametrize(
    "checkpoint",
    (
        "PREPARED",
        f"STAGED_{builder.DECISION_PATH.as_posix()}",
        f"BACKED_UP_{builder.DECISION_PATH.as_posix()}",
        f"PUBLISHED_{builder.DECISION_PATH.as_posix()}",
        f"PUBLISHED_{builder.MANIFEST_PATH.as_posix()}",
        "COMMITTED",
    ),
)
def test_crash_is_recovered_by_next_default_build(
    checkpoint: str,
    repository_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def crash(observed: str) -> None:
        if observed == checkpoint:
            raise _Crash

    monkeypatch.setattr(builder, "_transaction_checkpoint", crash)
    with pytest.raises(_Crash):
        builder.build(repository_copy)
    before_check = _snapshot(repository_copy)
    with pytest.raises(builder.PilotSignoffError) as error:
        builder.build(repository_copy, check=True)
    assert error.value.code == "OUTPUT_RECOVERY_REQUIRED"
    assert _snapshot(repository_copy) == before_check
    monkeypatch.setattr(builder, "_transaction_checkpoint", lambda _name: None)
    builder.build(repository_copy)
    builder.build(repository_copy, check=True)
    _assert_no_companions(repository_copy)


def test_regular_transaction_failure_rolls_back_immediately(
    repository_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(observed: str) -> None:
        if observed == f"PUBLISHED_{builder.DECISION_PATH.as_posix()}":
            raise RuntimeError("synthetic regular failure")

    monkeypatch.setattr(builder, "_transaction_checkpoint", fail)
    with pytest.raises(RuntimeError, match="synthetic regular failure"):
        builder.build(repository_copy)
    assert not any(
        (repository_copy / path).exists() for path in builder.GENERATED_PATHS
    )
    _assert_no_companions(repository_copy)


def test_existing_outputs_are_restored_before_rebuild_after_crash(
    repository_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder.build(repository_copy)
    original = {
        path: (repository_copy / path).read_bytes() for path in builder.GENERATED_PATHS
    }
    real_record = builder.decision_record

    def altered_record(contract: dict[str, object]) -> dict[str, object]:
        record = real_record(contract)
        record["test_only_generation"] = "changed"
        return record

    monkeypatch.setattr(builder, "decision_record", altered_record)

    def crash(observed: str) -> None:
        if observed == f"PUBLISHED_{builder.DECISION_PATH.as_posix()}":
            raise _Crash

    monkeypatch.setattr(builder, "_transaction_checkpoint", crash)
    with pytest.raises(_Crash):
        builder.build(repository_copy)
    monkeypatch.setattr(builder, "decision_record", real_record)
    monkeypatch.setattr(builder, "_transaction_checkpoint", lambda _name: None)
    builder.build(repository_copy)
    assert original == {
        path: (repository_copy / path).read_bytes() for path in builder.GENERATED_PATHS
    }
    _assert_no_companions(repository_copy)


def test_concurrent_writer_is_rejected(repository_copy: Path) -> None:
    lock = builder._acquire_lock(repository_copy, shared=False)  # noqa: SLF001
    try:
        with pytest.raises(builder.PilotSignoffError) as error:
            builder.build(repository_copy)
        assert error.value.code == "CONCURRENT_OUTPUT_WRITER"
    finally:
        builder._release_lock(lock)  # noqa: SLF001


def test_transaction_inventory_is_exact() -> None:
    assert builder.GENERATED_PATHS == (builder.DECISION_PATH, builder.MANIFEST_PATH)
    assert builder.TRANSACTION_NAME.startswith(".manifest.yaml.st1705.")
    assert builder.MAX_INPUT_BYTES == 2 * 1024 * 1024
