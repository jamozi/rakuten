"""Durability, recovery, and tamper evidence for the ST-1505 local journal."""

from __future__ import annotations

import os
import sqlite3
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from raos.adapters.disabled_deployment_identity import (
    DisabledDeploymentIdentityActivation,
)
from raos.adapters.recorded_staging_admission import (
    RecordedStagingAdmissionJournal,
)
from raos.application.ops.staging_admission import (
    LocalStagingAdmissionRun,
    LocalStagingAdmissionRunReceipt,
    LocalStagingAdmissionService,
)
from raos.domain.ops.staging_admission import LocalStagingAdmissionSpec
from raos.ports.staging_admission import (
    StagingAdmissionJournalError,
    StagingAdmissionJournalFailureCode,
)


_DATABASE_NAME = "st1505-local-admission.sqlite3"
_APPLICATION_ID = 1_505_003
_DATABASE_SCHEMA_VERSION = 3


def _service(
    specification: LocalStagingAdmissionSpec,
    journal: RecordedStagingAdmissionJournal,
) -> LocalStagingAdmissionService:
    return LocalStagingAdmissionService(
        spec=specification,
        activation=DisabledDeploymentIdentityActivation(),
        journal=journal,
    )


def _run(
    service: LocalStagingAdmissionService,
    *,
    suffix: str,
    key_suffix: str | None = None,
) -> LocalStagingAdmissionRunReceipt:
    identifier = suffix.replace("_", "-")
    key_identifier = (key_suffix or suffix).replace("_", "-")
    return service.execute(
        LocalStagingAdmissionRun(
            run_id=f"st1505-run-{identifier}",
            idempotency_key=f"st1505-key-{key_identifier}",
        )
    )


def test_idempotent_replay_does_not_append_duplicate(
    runtime_spec: LocalStagingAdmissionSpec, owner_private_root: Path
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    service = _service(runtime_spec, journal)
    first = _run(service, suffix="idempotent-001")
    second = _run(service, suffix="idempotent-001")
    assert first.persistence.sequence == second.persistence.sequence == 1
    assert first.persistence.entry_sha256 == second.persistence.entry_sha256
    assert first.persistence.replayed is False
    assert second.persistence.replayed is True
    assert journal.verify_integrity() == 1


def test_restart_recovery_preserves_exact_chain(
    runtime_spec: LocalStagingAdmissionSpec, owner_private_root: Path
) -> None:
    first_journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    first = _run(_service(runtime_spec, first_journal), suffix="restart-001")
    second_journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    replay = _run(_service(runtime_spec, second_journal), suffix="restart-001")
    appended = _run(_service(runtime_spec, second_journal), suffix="restart-002")
    assert replay.persistence.replayed is True
    assert replay.persistence.entry_sha256 == first.persistence.entry_sha256
    assert appended.persistence.sequence == 2
    assert appended.persistence.previous_entry_sha256 == first.persistence.entry_sha256
    assert second_journal.verify_integrity() == 2


def test_commit_ambiguity_recovers_without_retrying_mutation(
    runtime_spec: LocalStagingAdmissionSpec, owner_private_root: Path
) -> None:
    journal = RecordedStagingAdmissionJournal(
        private_root=owner_private_root,
        simulate_commit_ambiguity_once=True,
    )
    receipt = _run(_service(runtime_spec, journal), suffix="ambiguity-001")
    assert receipt.recovered_after_commit_ambiguity is True
    assert receipt.persistence.replayed is True
    assert receipt.persistence.sequence == 1
    assert journal.verify_integrity() == 1


@pytest.mark.parametrize("conflict_kind", ["run_id", "idempotency_key"])
def test_replay_conflict_fails_closed(
    runtime_spec: LocalStagingAdmissionSpec,
    owner_private_root: Path,
    conflict_kind: str,
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    service = _service(runtime_spec, journal)
    _run(service, suffix="conflict-first", key_suffix="conflict-key")
    if conflict_kind == "run_id":
        request = LocalStagingAdmissionRun(
            run_id="st1505-run-conflict-first",
            idempotency_key="st1505-key-conflict-other",
        )
    else:
        request = LocalStagingAdmissionRun(
            run_id="st1505-run-conflict-other",
            idempotency_key="st1505-key-conflict-key",
        )
    with pytest.raises(StagingAdmissionJournalError) as captured:
        service.execute(request)
    assert captured.value.code is StagingAdmissionJournalFailureCode.REPLAY_CONFLICT
    assert journal.verify_integrity() == 1


@pytest.mark.parametrize("tamper", ["tail", "result", "sequence", "run_request"])
def test_append_only_guards_reject_row_tamper_before_commit(
    runtime_spec: LocalStagingAdmissionSpec,
    owner_private_root: Path,
    tamper: str,
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    _run(_service(runtime_spec, journal), suffix=f"tamper-{tamper}")
    database = owner_private_root / _DATABASE_NAME
    connection = sqlite3.connect(database)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            if tamper == "tail":
                connection.execute(
                    "UPDATE admission_metadata SET tail_sha256 = ? WHERE singleton = 1",
                    ("f" * 64,),
                )
            elif tamper == "result":
                connection.execute(
                    "UPDATE admission_run SET result_json = ?",
                    (b'{"tampered":true}',),
                )
            elif tamper == "sequence":
                connection.execute(
                    "UPDATE admission_run SET sequence = 9 WHERE sequence = 1"
                )
            else:
                connection.execute(
                    "UPDATE admission_run SET request_sha256 = ?",
                    ("f" * 64,),
                )
        connection.rollback()
    finally:
        connection.close()
    assert journal.verify_integrity() == 1


def test_exact_strict_schema_foreign_keys_and_trigger_inventory(
    owner_private_root: Path,
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    connection = sqlite3.connect(owner_private_root / _DATABASE_NAME)
    try:
        assert connection.execute("PRAGMA application_id").fetchone() == (
            _APPLICATION_ID,
        )
        assert connection.execute("PRAGMA user_version").fetchone() == (
            _DATABASE_SCHEMA_VERSION,
        )
        assert connection.execute(
            "SELECT name, strict FROM pragma_table_list "
            "WHERE schema = 'main' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall() == [
            ("admission_journal", 1),
            ("admission_metadata", 1),
            ("admission_run", 1),
        ]
        assert [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'trigger' ORDER BY name"
            ).fetchall()
        ] == [
            "st1505_journal_guard_insert",
            "st1505_journal_no_delete",
            "st1505_journal_no_update",
            "st1505_metadata_guard_update",
            "st1505_metadata_no_delete",
            "st1505_metadata_no_insert",
            "st1505_run_guard_insert",
            "st1505_run_no_delete",
            "st1505_run_no_update",
        ]
        foreign_keys = connection.execute(
            'PRAGMA foreign_key_list("admission_journal")'
        ).fetchall()
        assert len(foreign_keys) == 5
        assert {(row[3], row[4]) for row in foreign_keys} == {
            ("run_id", "run_id"),
            ("idempotency_key_sha256", "idempotency_key_sha256"),
            ("request_sha256", "request_sha256"),
            ("result_sha256", "result_sha256"),
            ("sequence", "sequence"),
        }
        assert {(row[5], row[6]) for row in foreign_keys} == {("RESTRICT", "RESTRICT")}
    finally:
        connection.close()
    assert journal.verify_integrity() == 0


@pytest.mark.parametrize("tamper", ["application_id", "user_version", "trigger"])
def test_schema_header_and_guard_removal_are_detected(
    owner_private_root: Path, tamper: str
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    connection = sqlite3.connect(owner_private_root / _DATABASE_NAME)
    try:
        if tamper == "application_id":
            connection.execute("PRAGMA application_id=0")
        elif tamper == "user_version":
            connection.execute("PRAGMA user_version=0")
        else:
            connection.execute("DROP TRIGGER st1505_journal_no_delete")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(StagingAdmissionJournalError) as captured:
        journal.verify_integrity()
    assert captured.value.code is StagingAdmissionJournalFailureCode.TAMPER_DETECTED


def test_restored_trigger_inventory_cannot_hide_canonical_row_tamper(
    runtime_spec: LocalStagingAdmissionSpec, owner_private_root: Path
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    _run(_service(runtime_spec, journal), suffix="restored-trigger-tamper-001")
    connection = sqlite3.connect(owner_private_root / _DATABASE_NAME)
    try:
        row = connection.execute(
            "SELECT sql FROM sqlite_schema "
            "WHERE type='trigger' AND name='st1505_run_no_update'"
        ).fetchone()
        assert row is not None and isinstance(row[0], str)
        trigger_sql = row[0]
        connection.execute("DROP TRIGGER st1505_run_no_update")
        connection.execute("UPDATE admission_run SET result_json=?", (b"{}",))
        connection.execute(trigger_sql)
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(StagingAdmissionJournalError) as captured:
        journal.verify_integrity()
    assert captured.value.code is StagingAdmissionJournalFailureCode.TAMPER_DETECTED


def test_lifecycle_guards_reject_delete_and_out_of_order_insert(
    runtime_spec: LocalStagingAdmissionSpec, owner_private_root: Path
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    _run(_service(runtime_spec, journal), suffix="guard-001")
    statements: tuple[tuple[str, tuple[object, ...]], ...] = (
        ("DELETE FROM admission_metadata", ()),
        ("DELETE FROM admission_run", ()),
        ("DELETE FROM admission_journal", ()),
        (
            "INSERT INTO admission_run VALUES(?,?,?,?,?,?,?)",
            (
                "st1505-run-hostile-999",
                "1" * 64,
                "2" * 64,
                "3" * 64,
                "4" * 64,
                b"{}",
                99,
            ),
        ),
        (
            "INSERT INTO admission_journal VALUES(?,?,?,?,?,?,?)",
            (
                99,
                "0" * 64,
                "5" * 64,
                "st1505-run-hostile-999",
                "1" * 64,
                "2" * 64,
                "4" * 64,
            ),
        ),
    )
    connection = sqlite3.connect(owner_private_root / _DATABASE_NAME)
    try:
        for statement, parameters in statements:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement, parameters)
            connection.rollback()
    finally:
        connection.close()
    assert journal.verify_integrity() == 1


def test_concurrent_distinct_commits_are_serialized_and_chained(
    runtime_spec: LocalStagingAdmissionSpec, owner_private_root: Path
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    service = _service(runtime_spec, journal)

    def execute(index: int) -> LocalStagingAdmissionRunReceipt:
        return _run(service, suffix=f"concurrent-{index:03d}")

    with ThreadPoolExecutor(max_workers=4) as executor:
        receipts = list(executor.map(execute, range(8)))
    assert sorted(receipt.persistence.sequence for receipt in receipts) == list(
        range(1, 9)
    )
    assert len({receipt.persistence.entry_sha256 for receipt in receipts}) == 8
    assert journal.verify_integrity() == 8


def test_concurrent_identical_commit_is_one_entry_and_exact_replay(
    runtime_spec: LocalStagingAdmissionSpec, owner_private_root: Path
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    service = _service(runtime_spec, journal)
    with ThreadPoolExecutor(max_workers=4) as executor:
        receipts = list(
            executor.map(
                lambda _index: _run(service, suffix="same-concurrent-001"),
                range(4),
            )
        )
    assert {receipt.persistence.sequence for receipt in receipts} == {1}
    assert len({receipt.persistence.entry_sha256 for receipt in receipts}) == 1
    assert sum(receipt.persistence.replayed for receipt in receipts) == 3
    assert journal.verify_integrity() == 1


def test_private_root_and_database_modes_are_exact(
    runtime_spec: LocalStagingAdmissionSpec, owner_private_root: Path
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    _run(_service(runtime_spec, journal), suffix="mode-001")
    database = owner_private_root / _DATABASE_NAME
    assert stat.S_IMODE(owner_private_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    database.chmod(0o640)
    with pytest.raises(StagingAdmissionJournalError) as captured:
        journal.verify_integrity()
    assert captured.value.code is (
        StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID
    )


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_symlink_and_hardlink_database_targets_are_rejected(
    tmp_path: Path, kind: str
) -> None:
    private_root = tmp_path / f"private-{kind}"
    private_root.mkdir(mode=0o700)
    outside = tmp_path / f"outside-{kind}.sqlite3"
    outside.write_bytes(b"outside")
    outside.chmod(0o600)
    target = private_root / _DATABASE_NAME
    if kind == "symlink":
        target.symlink_to(outside)
    else:
        os.link(outside, target)
    with pytest.raises(StagingAdmissionJournalError) as captured:
        RecordedStagingAdmissionJournal(private_root=private_root)
    assert captured.value.code is (
        StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID
    )
    assert outside.read_bytes() == b"outside"


def test_symlinked_private_root_and_nonprivate_mode_are_rejected(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real-private"
    real.mkdir(mode=0o700)
    linked = tmp_path / "linked-private"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(StagingAdmissionJournalError):
        RecordedStagingAdmissionJournal(private_root=linked)
    real.chmod(0o750)
    with pytest.raises(StagingAdmissionJournalError):
        RecordedStagingAdmissionJournal(private_root=real)


def test_preexisting_zero_byte_database_is_never_adopted(
    owner_private_root: Path,
) -> None:
    database = owner_private_root / _DATABASE_NAME
    database.write_bytes(b"")
    database.chmod(0o600)
    with pytest.raises(StagingAdmissionJournalError) as captured:
        RecordedStagingAdmissionJournal(private_root=owner_private_root)
    assert captured.value.code is (
        StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID
    )
    assert database.read_bytes() == b""


def test_preexisting_valid_empty_sqlite_database_is_never_adopted(
    owner_private_root: Path,
) -> None:
    database = owner_private_root / _DATABASE_NAME
    connection = sqlite3.connect(database)
    try:
        connection.execute("VACUUM")
    finally:
        connection.close()
    database.chmod(0o600)
    before = database.read_bytes()
    assert before
    with pytest.raises(StagingAdmissionJournalError) as captured:
        RecordedStagingAdmissionJournal(private_root=owner_private_root)
    assert captured.value.code is StagingAdmissionJournalFailureCode.TAMPER_DETECTED
    assert database.read_bytes() == before
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM sqlite_schema").fetchone() == (
            0,
        )
    finally:
        connection.close()


def test_same_named_tables_with_weakened_constraints_are_rejected(
    owner_private_root: Path,
) -> None:
    database = owner_private_root / _DATABASE_NAME
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE admission_metadata "
            "(singleton INTEGER, schema_version TEXT, entry_count INTEGER, "
            "tail_sha256 TEXT)"
        )
        connection.execute(
            "CREATE TABLE admission_run "
            "(run_id TEXT, idempotency_key_sha256 TEXT, request_sha256 TEXT, "
            "contract_sha256 TEXT, result_sha256 TEXT, result_json BLOB, "
            "sequence INTEGER)"
        )
        connection.execute(
            "CREATE TABLE admission_journal "
            "(sequence INTEGER, previous_entry_sha256 TEXT, entry_sha256 TEXT, "
            "run_id TEXT, idempotency_key_sha256 TEXT, request_sha256 TEXT, "
            "result_sha256 TEXT)"
        )
        connection.execute(
            "INSERT INTO admission_metadata VALUES (1, ?, 0, ?)",
            ("ST1505_LOCAL_ADMISSION_JOURNAL_V2", "0" * 64),
        )
        connection.commit()
    finally:
        connection.close()
    database.chmod(0o600)
    with pytest.raises(StagingAdmissionJournalError) as captured:
        RecordedStagingAdmissionJournal(private_root=owner_private_root)
    assert captured.value.code is StagingAdmissionJournalFailureCode.TAMPER_DETECTED


def test_database_inode_replacement_is_detected(
    owner_private_root: Path,
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    database = owner_private_root / _DATABASE_NAME
    original_inode = database.stat().st_ino
    replacement = owner_private_root / "replacement.sqlite3"
    replacement.write_bytes(database.read_bytes())
    replacement.chmod(0o600)
    os.replace(replacement, database)
    assert database.stat().st_ino != original_inode
    with pytest.raises(StagingAdmissionJournalError) as captured:
        journal.verify_integrity()
    assert captured.value.code is (
        StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID
    )


def test_private_root_inode_replacement_is_detected(
    owner_private_root: Path,
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    displaced = owner_private_root.with_name(f"{owner_private_root.name}-displaced")
    owner_private_root.rename(displaced)
    owner_private_root.mkdir(mode=0o700)
    database = owner_private_root / _DATABASE_NAME
    database.write_bytes((displaced / _DATABASE_NAME).read_bytes())
    database.chmod(0o600)
    with pytest.raises(StagingAdmissionJournalError) as captured:
        journal.verify_integrity()
    assert captured.value.code is (
        StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID
    )


def test_same_inode_whole_database_rollback_is_detected_by_process_anchor(
    runtime_spec: LocalStagingAdmissionSpec, owner_private_root: Path
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    service = _service(runtime_spec, journal)
    _run(service, suffix="rollback-anchor-001")
    database = owner_private_root / _DATABASE_NAME
    original_inode = database.stat().st_ino
    one_entry_snapshot = database.read_bytes()
    _run(service, suffix="rollback-anchor-002")
    database.write_bytes(one_entry_snapshot)
    assert database.stat().st_ino == original_inode
    with pytest.raises(StagingAdmissionJournalError) as captured:
        journal.verify_integrity()
    assert captured.value.code is StagingAdmissionJournalFailureCode.TAMPER_DETECTED


def test_sidecar_target_is_rejected_without_following_it(
    owner_private_root: Path,
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    outside = owner_private_root.parent / "outside-sidecar"
    outside.write_bytes(b"outside")
    sidecar = owner_private_root / f"{_DATABASE_NAME}-wal"
    sidecar.symlink_to(outside)
    with pytest.raises(StagingAdmissionJournalError) as captured:
        journal.verify_integrity()
    assert captured.value.code is (
        StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID
    )
    assert outside.read_bytes() == b"outside"


def test_extra_schema_object_is_detected_after_initialization(
    runtime_spec: LocalStagingAdmissionSpec, owner_private_root: Path
) -> None:
    journal = RecordedStagingAdmissionJournal(private_root=owner_private_root)
    _run(_service(runtime_spec, journal), suffix="schema-extra-001")
    connection = sqlite3.connect(owner_private_root / _DATABASE_NAME)
    try:
        connection.execute(
            "CREATE INDEX attacker_index ON admission_run(request_sha256)"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(StagingAdmissionJournalError) as captured:
        journal.verify_integrity()
    assert captured.value.code is StagingAdmissionJournalFailureCode.TAMPER_DETECTED
