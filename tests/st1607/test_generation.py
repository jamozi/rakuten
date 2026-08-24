from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest
import yaml

from scripts import build_st1505_staging_deployment as base
from scripts import build_st1607_gate_evidence_pack as builder


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


def _output_state(path: Path) -> tuple[bytes, int, int, int]:
    metadata = path.lstat()
    payload = (
        os.readlink(path).encode()
        if stat.S_ISLNK(metadata.st_mode)
        else path.read_bytes()
    )
    return (
        payload,
        metadata.st_ino,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_mtime_ns,
    )


def _transaction_companions(root: Path) -> tuple[Path, ...]:
    companions: list[Path] = []
    for relative in builder.GENERATED_PATHS:
        target = root / relative
        companions.extend(
            (
                target.with_name(f".{target.name}{builder.NEXT_SUFFIX}"),
                target.with_name(f".{target.name}{builder.PREVIOUS_SUFFIX}"),
                target.with_name(f".{target.name}{builder.ABSENT_SUFFIX}"),
            )
        )
    state_parent = root / builder.MANIFEST_PATH.parent
    companions.extend(
        (
            state_parent / builder.TRANSACTION_STATE_NAME,
            state_parent / builder.TRANSACTION_STATE_NEXT_NAME,
        )
    )
    return tuple(companions)


def _assert_no_transaction_companions(root: Path) -> None:
    assert not [path for path in _transaction_companions(root) if os.path.lexists(path)]


class _SimulatedCrash(BaseException):
    pass


def test_owner_generation_is_deterministic_and_check_is_no_write(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)
    first = {
        path: (repository_copy / path).read_bytes() for path in builder.GENERATED_PATHS
    }
    before = _snapshot(repository_copy)
    builder.build(repository_copy, check=True)
    after = _snapshot(repository_copy)
    assert before == after
    builder.build(repository_copy)
    assert first == {
        path: (repository_copy / path).read_bytes() for path in builder.GENERATED_PATHS
    }
    _assert_no_transaction_companions(repository_copy)


def test_manifest_records_exact_owner_and_input_inventory(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)
    manifest = yaml.safe_load((repository_copy / builder.MANIFEST_PATH).read_text())
    assert manifest["source_artifact_count"] == len(builder.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in builder.SOURCE_PATHS
    ]
    assert manifest["generated_artifact_count"] == 1
    generated = manifest["generated_artifacts"][0]
    report_bytes = (repository_copy / builder.REPORT_PATH).read_bytes()
    assert generated == {
        "uri": f"repo://{builder.REPORT_PATH.as_posix()}",
        "bytes": len(report_bytes),
        "sha256": hashlib.sha256(report_bytes).hexdigest(),
    }
    provenance = manifest["provenance"]
    assert provenance["local_base_commit"] == builder.LOCAL_BASE_COMMIT
    assert provenance["local_base_commit_type"] == builder.LOCAL_BASE_COMMIT_TYPE
    assert provenance["local_base_commit_status"] == builder.LOCAL_BASE_COMMIT_STATUS
    assert provenance["local_base_commit_qualifying_evidence"] is False
    assert provenance["source_freeze_identifier_type"] == (
        builder.SOURCE_FREEZE_ID_TYPE
    )
    assert provenance["source_freeze_status"] == "ABSENT"
    assert provenance["source_freeze_identifier"] is None
    assert provenance["source_freeze_qualifying_evidence"] is False
    assert provenance["reviewed_implementation_tree_commit_type"] == (
        builder.REVIEWED_TREE_COMMIT_TYPE
    )
    assert provenance["reviewed_implementation_tree_commit_status"] == "ABSENT"
    assert provenance["reviewed_implementation_tree_commit"] is None
    assert (
        provenance["reviewed_implementation_tree_commit_qualifying_evidence"] is False
    )
    assert len(provenance["authority_inputs"]) == len(builder.EXPECTED_SOURCE_HASHES)
    assert len(provenance["dependency_inputs"]) == len(
        builder.EXPECTED_DEPENDENCY_HASHES
    )
    assert manifest["boundary"]["input_size_limit_bytes"] == (builder.MAX_INPUT_BYTES)


def test_generated_report_is_blocked_and_non_attesting(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)
    report = json.loads((repository_copy / builder.REPORT_PATH).read_text())
    assert report["classification"] == (
        "LOCAL_BLOCKED_GATE_EVIDENCE_PACK_NON_ATTESTING"
    )
    assert all(gate["status"] == "BLOCKED" for gate in report["gate_report"]["gates"])
    assert report["evidence_boundary"]["formal_tst_032"] == "NOT_EXECUTED"
    assert report["authority_boundary"]["release_authority"] == "NONE"
    assert report["authority_boundary"]["production_authority"] == "NONE"
    assert report["execution_boundary"]["external_action_count"] == 0


def test_check_detects_generated_output_drift(repository_copy: Path) -> None:
    builder.build(repository_copy)
    (repository_copy / builder.REPORT_PATH).write_text("{}\n")
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.build(repository_copy, check=True)
    assert error.value.code == "GENERATED_OUTPUT_DRIFT"


def test_source_dependency_and_decision_hash_drift_fail_closed(
    repository_copy: Path,
) -> None:
    cases = (
        (next(iter(builder.EXPECTED_SOURCE_HASHES)), "SOURCE_HASH_DRIFT"),
        (next(iter(builder.EXPECTED_DEPENDENCY_HASHES)), "DEPENDENCY_HASH_DRIFT"),
        (
            next(iter(builder.EXPECTED_DECISION_GATE_HASHES)),
            "DECISION_INPUT_HASH_DRIFT",
        ),
    )
    for relative, error_code in cases:
        target = repository_copy / relative
        original = target.read_bytes()
        target.write_bytes(original + b"\n")
        with pytest.raises(builder.GateEvidencePackError) as error:
            builder.render_outputs(repository_copy)
        assert error.value.code == error_code
        target.write_bytes(original)


def test_post_root_capture_ancestor_swap_cannot_read_outside_repository(
    repository_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    relative = Path("authority/source.yaml")
    authority = repository_copy / relative.parent
    authority.mkdir()
    inside = b"inside-synthetic\n"
    (repository_copy / relative).write_bytes(inside)
    parked = repository_copy / "authority.parked"
    outside = tmp_path_factory.mktemp("st1607-input-race-outside")
    outside_source = outside / relative.name
    outside_source.write_bytes(b"outside-synthetic\n")
    outside_read = False
    real_read = os.read

    def replace_ancestor(_root_descriptor: int, observed_relative: Path) -> None:
        assert observed_relative == relative
        authority.rename(parked)
        authority.symlink_to(outside, target_is_directory=True)

    def record_read(descriptor: int, size: int) -> bytes:
        nonlocal outside_read
        if os.readlink(f"/proc/self/fd/{descriptor}") == str(outside_source):
            outside_read = True
        return real_read(descriptor, size)

    monkeypatch.setattr(builder, "_input_path_walk_checkpoint", replace_ancestor)
    monkeypatch.setattr(os, "read", record_read)
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder._read(repository_copy, relative, "authority")
    assert error.value.code == "UNSAFE_ANCESTOR"
    assert outside_read is False


def test_drifted_hash_bound_helper_is_never_imported_or_executed(
    repository_copy: Path,
) -> None:
    helper_relative = Path(next(iter(builder.EXPECTED_IMPLEMENTATION_HASHES)))
    helper = repository_copy / helper_relative
    execution_sentinel = repository_copy / "untrusted-helper-executed"
    helper.write_text(
        "from pathlib import Path\n"
        f"Path({str(execution_sentinel)!r}).write_text('executed')\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(repository_copy / builder.GENERATOR_PATH),
            "--check",
        ],
        cwd=repository_copy,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == (
        "ST1607_ERROR code=IMPLEMENTATION_DEPENDENCY_DRIFT field=implementation"
    )
    assert not execution_sentinel.exists()


@pytest.mark.parametrize("unsafe_relative", builder.GENERATED_PATHS)
def test_any_unsafe_output_is_rejected_before_either_output_is_replaced(
    unsafe_relative: Path, repository_copy: Path
) -> None:
    builder.build(repository_copy)
    unsafe = repository_copy / unsafe_relative
    unsafe.unlink()
    unsafe.symlink_to(repository_copy / builder.CONTRACT_PATH)
    before = {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    }
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.build(repository_copy)
    assert error.value.code == "UNSAFE_OUTPUT_TARGET"
    after = {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    }
    assert after == before


def test_unsafe_later_output_ancestor_preserves_both_outputs(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)
    unsafe_manifest = Path("unsafe-manifest-parent/manifest.yaml")
    unsafe_parent = repository_copy / unsafe_manifest.parent
    unsafe_parent.symlink_to(
        repository_copy / builder.MANIFEST_PATH.parent,
        target_is_directory=True,
    )
    monkeypatch.setattr(builder, "MANIFEST_PATH", unsafe_manifest)
    monkeypatch.setattr(
        builder,
        "GENERATED_PATHS",
        (builder.REPORT_PATH, unsafe_manifest),
    )
    before = {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    }
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.build(repository_copy)
    assert error.value.code == "UNSAFE_OUTPUT_ANCESTOR"
    after = {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    }
    assert after == before


@pytest.mark.parametrize("failure_after_link", (False, True))
def test_injected_second_publish_failure_restores_exact_output_tuples(
    failure_after_link: bool,
    repository_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder.build(repository_copy)
    report = repository_copy / builder.REPORT_PATH
    report.write_bytes(b"drifted-first-report\n")
    report.chmod(0o600)
    os.utime(report, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    before = {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    }
    real_publish = builder._publish_output
    calls = 0

    def fail_second(root: Path, slot: builder._OutputSlot) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            if failure_after_link:
                real_publish(root, slot)
            raise OSError("injected second publish failure")
        real_publish(root, slot)

    monkeypatch.setattr(builder, "_publish_output", fail_second)
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.build(repository_copy)
    assert error.value.code == "OUTPUT_TRANSACTION_FAILED"
    assert {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    } == before
    _assert_no_transaction_companions(repository_copy)


def test_injected_second_publish_failure_restores_absent_outputs(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)
    for relative in builder.GENERATED_PATHS:
        (repository_copy / relative).unlink()
    real_publish = builder._publish_output
    calls = 0

    def fail_second(root: Path, slot: builder._OutputSlot) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second publish failure")
        real_publish(root, slot)

    monkeypatch.setattr(builder, "_publish_output", fail_second)
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.build(repository_copy)
    assert error.value.code == "OUTPUT_TRANSACTION_FAILED"
    assert all(
        not (repository_copy / relative).exists()
        for relative in builder.GENERATED_PATHS
    )
    _assert_no_transaction_companions(repository_copy)


def test_post_preflight_target_swap_is_not_overwritten(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)
    before = {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    }
    target = repository_copy / builder.MANIFEST_PATH
    parked = target.with_name("manifest.parked-for-test")

    def swap_target(_slots: object) -> None:
        target.rename(parked)
        target.symlink_to(repository_copy / builder.CONTRACT_PATH)

    monkeypatch.setattr(builder, "_before_transaction_commit", swap_target)
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.build(repository_copy)
    assert error.value.code == "OUTPUT_ROLLBACK_REQUIRED"
    assert target.is_symlink()
    assert (
        _output_state(repository_copy / builder.REPORT_PATH)
        == before[builder.REPORT_PATH]
    )
    target.unlink()
    parked.rename(target)
    monkeypatch.setattr(builder, "_before_transaction_commit", lambda _slots: None)
    builder._recover_pending_transaction(repository_copy, mutate=True)
    assert {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    } == before
    _assert_no_transaction_companions(repository_copy)


def test_target_swap_after_final_revalidation_rolls_back_earlier_output(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)
    before = {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    }
    target = repository_copy / builder.MANIFEST_PATH
    parked = target.with_name("manifest.parked-after-final-preflight")
    real_write_state = builder._write_rollback_state

    def state_then_swap(slots: Sequence[builder._OutputSlot]) -> None:
        real_write_state(slots)
        target.rename(parked)
        target.symlink_to(repository_copy / builder.CONTRACT_PATH)

    monkeypatch.setattr(builder, "_write_rollback_state", state_then_swap)
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.build(repository_copy)
    assert error.value.code == "OUTPUT_ROLLBACK_REQUIRED"
    assert target.is_symlink()
    assert (
        _output_state(repository_copy / builder.REPORT_PATH)
        == before[builder.REPORT_PATH]
    )
    target.unlink()
    parked.rename(target)
    monkeypatch.setattr(builder, "_write_rollback_state", real_write_state)
    builder._recover_pending_transaction(repository_copy, mutate=True)
    assert {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    } == before
    _assert_no_transaction_companions(repository_copy)


def test_post_preflight_ancestor_swap_is_not_followed(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)
    before = {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    }
    generated = repository_copy / builder.REPORT_PATH.parent
    parked = generated.with_name("generated.parked-for-test")

    def swap_ancestor(_slots: object) -> None:
        generated.rename(parked)
        generated.symlink_to(parked, target_is_directory=True)

    monkeypatch.setattr(builder, "_before_transaction_commit", swap_ancestor)
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.build(repository_copy)
    assert error.value.code == "OUTPUT_ROLLBACK_REQUIRED"
    assert generated.is_symlink()
    generated.unlink()
    parked.rename(generated)
    monkeypatch.setattr(builder, "_before_transaction_commit", lambda _slots: None)
    builder._recover_pending_transaction(repository_copy, mutate=True)
    assert {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    } == before
    _assert_no_transaction_companions(repository_copy)


def test_ancestor_swap_after_final_revalidation_retains_recoverable_state(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)
    before = {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    }
    generated = repository_copy / builder.REPORT_PATH.parent
    parked = generated.with_name("generated.parked-after-final-preflight")
    real_write_state = builder._write_rollback_state

    def state_then_swap(slots: Sequence[builder._OutputSlot]) -> None:
        real_write_state(slots)
        generated.rename(parked)
        generated.symlink_to(parked, target_is_directory=True)

    monkeypatch.setattr(builder, "_write_rollback_state", state_then_swap)
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.build(repository_copy)
    assert error.value.code == "OUTPUT_ROLLBACK_REQUIRED"
    state = (
        repository_copy / builder.MANIFEST_PATH.parent / builder.TRANSACTION_STATE_NAME
    )
    assert state.read_bytes() == builder.ROLLBACK_STATE
    generated.unlink()
    parked.rename(generated)
    monkeypatch.setattr(builder, "_write_rollback_state", real_write_state)
    builder._recover_pending_transaction(repository_copy, mutate=True)
    assert {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    } == before
    _assert_no_transaction_companions(repository_copy)


@pytest.mark.parametrize(
    "boundary",
    (
        f"BACKED_UP_{builder.REPORT_PATH.as_posix()}",
        f"BACKED_UP_{builder.MANIFEST_PATH.as_posix()}",
        f"PUBLISHED_{builder.REPORT_PATH.as_posix()}",
        f"PUBLISHED_{builder.MANIFEST_PATH.as_posix()}",
        "COMMIT_MARKED",
    ),
)
def test_crash_after_each_transaction_rename_recovers_idempotently(
    boundary: str, repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)

    def crash_at(name: str) -> None:
        if name == boundary:
            raise _SimulatedCrash

    monkeypatch.setattr(builder, "_transaction_checkpoint", crash_at)
    with pytest.raises(_SimulatedCrash):
        builder.build(repository_copy)
    assert any(
        os.path.lexists(path) for path in _transaction_companions(repository_copy)
    )
    monkeypatch.setattr(builder, "_transaction_checkpoint", lambda _name: None)
    builder.build(repository_copy)
    first = {
        relative: (repository_copy / relative).read_bytes()
        for relative in builder.GENERATED_PATHS
    }
    builder.build(repository_copy)
    assert first == {
        relative: (repository_copy / relative).read_bytes()
        for relative in builder.GENERATED_PATHS
    }
    _assert_no_transaction_companions(repository_copy)


def test_rollback_failure_retains_recoverable_state_then_recovers(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)
    before = {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    }
    real_publish = builder._publish_output
    real_recover = builder._recover_rollback
    publish_calls = 0

    def fail_second(root: Path, slot: builder._OutputSlot) -> None:
        nonlocal publish_calls
        publish_calls += 1
        if publish_calls == 2:
            raise OSError("injected publish failure")
        real_publish(root, slot)

    def fail_rollback(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected rollback failure")

    monkeypatch.setattr(builder, "_publish_output", fail_second)
    monkeypatch.setattr(builder, "_recover_rollback", fail_rollback)
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.build(repository_copy)
    assert error.value.code == "OUTPUT_ROLLBACK_REQUIRED"
    state = (
        repository_copy / builder.MANIFEST_PATH.parent / builder.TRANSACTION_STATE_NAME
    )
    assert state.read_bytes() == builder.ROLLBACK_STATE
    assert any(
        os.path.lexists(path) for path in _transaction_companions(repository_copy)
    )

    monkeypatch.setattr(builder, "_publish_output", real_publish)
    monkeypatch.setattr(builder, "_recover_rollback", real_recover)
    builder._recover_pending_transaction(repository_copy, mutate=True)
    assert {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    } == before
    _assert_no_transaction_companions(repository_copy)
    builder.build(repository_copy)
    _assert_no_transaction_companions(repository_copy)


def test_crash_during_partial_rollback_is_recovered_on_next_rerun(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)
    before = {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    }

    def crash_after_first_publish(name: str) -> None:
        if name == f"PUBLISHED_{builder.REPORT_PATH.as_posix()}":
            raise _SimulatedCrash

    monkeypatch.setattr(builder, "_transaction_checkpoint", crash_after_first_publish)
    with pytest.raises(_SimulatedCrash):
        builder.build(repository_copy)

    def crash_after_first_restore(name: str) -> None:
        if name == f"RESTORED_{builder.MANIFEST_PATH.as_posix()}":
            raise _SimulatedCrash

    monkeypatch.setattr(builder, "_transaction_checkpoint", crash_after_first_restore)
    with pytest.raises(_SimulatedCrash):
        builder._recover_pending_transaction(repository_copy, mutate=True)
    assert any(
        os.path.lexists(path) for path in _transaction_companions(repository_copy)
    )
    monkeypatch.setattr(builder, "_transaction_checkpoint", lambda _name: None)
    builder._recover_pending_transaction(repository_copy, mutate=True)
    assert {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    } == before
    _assert_no_transaction_companions(repository_copy)


def test_check_refuses_pending_recovery_without_writing(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)

    def crash_after_first_publish(name: str) -> None:
        if name == f"PUBLISHED_{builder.REPORT_PATH.as_posix()}":
            raise _SimulatedCrash

    monkeypatch.setattr(builder, "_transaction_checkpoint", crash_after_first_publish)
    with pytest.raises(_SimulatedCrash):
        builder.build(repository_copy)
    before = _snapshot(repository_copy)
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.build(repository_copy, check=True)
    assert error.value.code == "OUTPUT_RECOVERY_REQUIRED"
    assert _snapshot(repository_copy) == before


@pytest.mark.parametrize(
    "shape",
    (
        "symlink-next",
        "regular-next",
        "regular-previous",
        "wrong-mode-state",
        "wrong-token-state",
    ),
)
def test_malicious_companion_shape_is_retained_and_rejected_without_output_write(
    shape: str, repository_copy: Path
) -> None:
    builder.build(repository_copy)
    before = {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    }
    if shape == "symlink-next":
        target = repository_copy / builder.REPORT_PATH
        companion = target.with_name(f".{target.name}{builder.NEXT_SUFFIX}")
        companion.symlink_to(repository_copy / builder.CONTRACT_PATH)
    elif shape == "regular-next":
        target = repository_copy / builder.REPORT_PATH
        companion = target.with_name(f".{target.name}{builder.NEXT_SUFFIX}")
        companion.write_bytes(b"unexpected companion\n")
        companion.chmod(builder.OUTPUT_MODE)
    elif shape == "regular-previous":
        target = repository_copy / builder.REPORT_PATH
        companion = target.with_name(f".{target.name}{builder.PREVIOUS_SUFFIX}")
        companion.write_bytes(b"unexpected previous\n")
        companion.chmod(builder.OUTPUT_MODE)
    else:
        companion = (
            repository_copy
            / builder.MANIFEST_PATH.parent
            / builder.TRANSACTION_STATE_NAME
        )
        companion.write_bytes(
            b"ST1607_UNKNOWN_TRANSACTION_STATE_V1\n"
            if shape == "wrong-token-state"
            else builder.ROLLBACK_STATE
        )
        companion.chmod(
            builder.PRIVATE_COMPANION_MODE if shape == "wrong-token-state" else 0o644
        )
    with pytest.raises(builder.GateEvidencePackError):
        builder.build(repository_copy)
    assert os.path.lexists(companion)
    assert {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    } == before


def test_unexpected_target_during_recovery_is_never_overwritten(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)

    def crash_after_first_publish(name: str) -> None:
        if name == f"PUBLISHED_{builder.REPORT_PATH.as_posix()}":
            raise _SimulatedCrash

    monkeypatch.setattr(builder, "_transaction_checkpoint", crash_after_first_publish)
    with pytest.raises(_SimulatedCrash):
        builder.build(repository_copy)
    report = repository_copy / builder.REPORT_PATH
    report.unlink()
    report.symlink_to(repository_copy / builder.CONTRACT_PATH)
    monkeypatch.setattr(builder, "_transaction_checkpoint", lambda _name: None)
    with pytest.raises(builder.GateEvidencePackError):
        builder.build(repository_copy)
    assert report.is_symlink()
    state = (
        repository_copy / builder.MANIFEST_PATH.parent / builder.TRANSACTION_STATE_NAME
    )
    assert state.read_bytes() == builder.ROLLBACK_STATE


def test_concurrent_same_uid_writer_is_rejected_without_recovery_or_output_write(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)
    before = {
        relative: _output_state(repository_copy / relative)
        for relative in builder.GENERATED_PATHS
    }
    writer_lock = builder._acquire_writer_lock(repository_copy)
    try:
        with pytest.raises(builder.GateEvidencePackError) as error:
            builder.build(repository_copy)
        assert error.value.code == "CONCURRENT_OUTPUT_WRITER"
        check_before = _snapshot(repository_copy)
        with pytest.raises(builder.GateEvidencePackError) as error:
            builder.build(repository_copy, check=True)
        assert error.value.code == "CONCURRENT_OUTPUT_WRITER"
        assert _snapshot(repository_copy) == check_before
        assert {
            relative: _output_state(repository_copy / relative)
            for relative in builder.GENERATED_PATHS
        } == before
    finally:
        builder._release_writer_lock(writer_lock)
    _assert_no_transaction_companions(repository_copy)
    builder.build(repository_copy)
    _assert_no_transaction_companions(repository_copy)


def test_publish_and_coordinator_transitions_fsync_each_owning_directory(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)
    events: list[tuple[str, str, str]] = []
    real_fsync = os.fsync
    real_link = os.link
    real_replace = os.replace

    def record_fsync(descriptor: int) -> None:
        events.append(("fsync", os.readlink(f"/proc/self/fd/{descriptor}"), ""))
        real_fsync(descriptor)

    def record_link(
        source: str,
        target: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        events.append(("link", source, target))
        real_link(
            source,
            target,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    def record_replace(
        source: str,
        target: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        events.append(("replace", source, target))
        real_replace(
            source,
            target,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(os, "fsync", record_fsync)
    monkeypatch.setattr(os, "link", record_link)
    monkeypatch.setattr(os, "replace", record_replace)
    builder.build(repository_copy)

    report_parent = str((repository_copy / builder.REPORT_PATH.parent).resolve())
    manifest_parent = str((repository_copy / builder.MANIFEST_PATH.parent).resolve())

    def event_index(kind: str, source: str, target: str) -> int:
        return next(
            index
            for index, event in enumerate(events)
            if event == (kind, source, target)
        )

    def assert_parent_fsync_between(start: int, end: int, parent: str) -> None:
        assert any(
            event[0] == "fsync" and event[1] == parent
            for event in events[start + 1 : end]
        )

    backup_report = event_index(
        "replace",
        builder.REPORT_PATH.name,
        f".{builder.REPORT_PATH.name}{builder.PREVIOUS_SUFFIX}",
    )
    backup_manifest = event_index(
        "replace",
        builder.MANIFEST_PATH.name,
        f".{builder.MANIFEST_PATH.name}{builder.PREVIOUS_SUFFIX}",
    )
    publish_report = event_index(
        "link",
        f".{builder.REPORT_PATH.name}{builder.NEXT_SUFFIX}",
        builder.REPORT_PATH.name,
    )
    publish_manifest = event_index(
        "link",
        f".{builder.MANIFEST_PATH.name}{builder.NEXT_SUFFIX}",
        builder.MANIFEST_PATH.name,
    )
    commit_state = event_index(
        "replace",
        builder.TRANSACTION_STATE_NEXT_NAME,
        builder.TRANSACTION_STATE_NAME,
    )
    assert_parent_fsync_between(backup_report, backup_manifest, report_parent)
    assert_parent_fsync_between(backup_manifest, publish_report, manifest_parent)
    assert_parent_fsync_between(publish_report, publish_manifest, report_parent)
    assert_parent_fsync_between(publish_manifest, commit_state, manifest_parent)
    assert any(
        event[0] == "fsync" and event[1] == manifest_parent
        for event in events[commit_state + 1 :]
    )

    events.clear()
    real_publish = builder._publish_output
    publish_calls = 0

    def fail_second_publish(root: Path, slot: builder._OutputSlot) -> None:
        nonlocal publish_calls
        publish_calls += 1
        if publish_calls == 2:
            raise OSError("injected rollback-order failure")
        real_publish(root, slot)

    monkeypatch.setattr(builder, "_publish_output", fail_second_publish)
    with pytest.raises(builder.GateEvidencePackError):
        builder.build(repository_copy)
    restore_manifest = event_index(
        "replace",
        f".{builder.MANIFEST_PATH.name}{builder.PREVIOUS_SUFFIX}",
        builder.MANIFEST_PATH.name,
    )
    restore_report = event_index(
        "replace",
        f".{builder.REPORT_PATH.name}{builder.PREVIOUS_SUFFIX}",
        builder.REPORT_PATH.name,
    )
    assert_parent_fsync_between(restore_manifest, restore_report, manifest_parent)
    assert any(
        event[0] == "fsync" and event[1] == report_parent
        for event in events[restore_report + 1 :]
    )
    _assert_no_transaction_companions(repository_copy)


def test_post_commit_coordinator_fsync_failure_retains_commit_recovery_state(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder.build(repository_copy)
    real_fsync = os.fsync
    real_replace = os.replace
    commit_replaced = False
    failed = False

    def replace_then_flag(
        source: str,
        target: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal commit_replaced
        real_replace(
            source,
            target,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )
        if (
            source == builder.TRANSACTION_STATE_NEXT_NAME
            and target == builder.TRANSACTION_STATE_NAME
        ):
            commit_replaced = True

    def fail_commit_directory_fsync(descriptor: int) -> None:
        nonlocal failed
        path = os.readlink(f"/proc/self/fd/{descriptor}")
        manifest_parent = str(
            (repository_copy / builder.MANIFEST_PATH.parent).resolve()
        )
        if commit_replaced and not failed and path == manifest_parent:
            failed = True
            raise OSError("injected coordinator fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "replace", replace_then_flag)
    monkeypatch.setattr(os, "fsync", fail_commit_directory_fsync)
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.build(repository_copy)
    assert error.value.code == "OUTPUT_RECOVERY_REQUIRED"
    state = (
        repository_copy / builder.MANIFEST_PATH.parent / builder.TRANSACTION_STATE_NAME
    )
    assert state.read_bytes() == builder.COMMIT_STATE
    assert any(
        os.path.lexists(path) for path in _transaction_companions(repository_copy)
    )

    monkeypatch.setattr(os, "replace", real_replace)
    monkeypatch.setattr(os, "fsync", real_fsync)
    builder.build(repository_copy)
    _assert_no_transaction_companions(repository_copy)


@pytest.mark.parametrize(
    "relative",
    (
        Path(next(iter(builder.EXPECTED_SOURCE_HASHES))),
        Path(next(iter(builder.EXPECTED_DEPENDENCY_HASHES))),
        builder.CONTRACT_PATH,
        builder.README_PATH,
    ),
)
def test_oversized_input_fails_before_output_mutation(
    relative: Path, repository_copy: Path
) -> None:
    builder.build(repository_copy)
    target = repository_copy / relative
    target.write_bytes(b"x" * (builder.MAX_INPUT_BYTES + 1))
    before = {
        output: _output_state(repository_copy / output)
        for output in builder.GENERATED_PATHS
    }
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.build(repository_copy)
    assert error.value.code == "INPUT_SIZE_LIMIT"
    after = {
        output: _output_state(repository_copy / output)
        for output in builder.GENERATED_PATHS
    }
    assert after == before


def test_symlinked_output_target_and_ancestor_are_rejected(
    repository_copy: Path,
) -> None:
    builder.build(repository_copy)
    output = repository_copy / builder.REPORT_PATH
    output.unlink()
    output.symlink_to(repository_copy / builder.CONTRACT_PATH)
    with pytest.raises(base_exception_types()):
        builder.build(repository_copy)
    output.unlink()
    generated = repository_copy / builder.REPORT_PATH.parent
    os.rmdir(generated)
    generated.symlink_to(
        repository_copy / "changes/st-1607/contracts", target_is_directory=True
    )
    with pytest.raises(base_exception_types()):
        builder.build(repository_copy)


def base_exception_types() -> tuple[type[BaseException], ...]:
    return (
        builder.GateEvidencePackError,
        base.StagingDeploymentContractError,
    )
