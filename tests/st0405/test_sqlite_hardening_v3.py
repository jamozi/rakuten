"""Created-only SQLite, append guards, anchors, and recovery for ST-0405."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
from threading import Barrier, Thread

import pytest

from conftest import (
    AUTHORIZATION_COMMAND_ID,
    NOW,
    audit_context,
    durable_authorization_bundle,
)
from raos.adapters.recorded_audit import RecordedAuditAdapter
from raos.adapters.recorded_audit_runtime_v2 import (
    RecordedAuditFaultV2,
    RecordedSqliteAuditRuntimeStoreFactoryV2,
)
from raos.application.ops.audit_runtime_v2 import (
    DurableAuditRequestV2,
    DurableAuditWriterV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.audit import AuditOutcome, AuditReasonCode, AuditSeverity
from raos.domain.ops.audit_runtime_v2 import (
    AUDIT_RUNTIME_GENESIS_SHA256_V2,
    AuditAppendReceiptV2,
    AuditRuntimeFailureCodeV2,
    AuditRuntimeFailureV2,
)


_DATABASE_NAME = "st0405-recorded-audit-runtime-v2.sqlite3"
_APPLICATION_ID = 1_380_400_502


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def _bundle(
    tmp_path: Path,
    *,
    fault: RecordedAuditFaultV2 | None = None,
) -> tuple[
    DurableAuditWriterV2,
    DurableAuditRequestV2,
    RecordedSqliteAuditRuntimeStoreFactoryV2,
]:
    authorization, _, session, _ = durable_authorization_bundle(
        _private(tmp_path / "authorization")
    )
    grant = authorization.recover_admin(
        command_id=AUTHORIZATION_COMMAND_ID,
        session_id=session.session_id,
        now=NOW,
    ).grant()
    context = RecordedAuditAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=1,
        context_script=(audit_context(grant),),
    )
    factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=_private(tmp_path / "audit"),
        fault_once_at=fault,
    )
    writer = DurableAuditWriterV2(
        authorization=authorization,
        context_source=context,
        store_factory=factory,
    )
    request = DurableAuditRequestV2(
        authorization_command_id=AUTHORIZATION_COMMAND_ID,
        session_id=session.session_id,
        now=NOW,
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.NOTICE,
        reason_code=AuditReasonCode("RECORDED:ST0405:HARDENED_CHANGE"),
        before_hash="a" * 64,
        after_hash="b" * 64,
    )
    return writer, request, factory


def _failure(
    code: AuditRuntimeFailureCodeV2, operation: object
) -> AuditRuntimeFailureV2:
    assert callable(operation)
    with pytest.raises(AuditRuntimeFailureV2) as caught:
        operation()
    assert caught.value.code is code
    assert caught.value.args == (code.value,)
    assert caught.value.__cause__ is None
    return caught.value


@pytest.mark.parametrize("payload", [b"", b"partial", b"SQLite format 3\x00short"])
def test_preexisting_empty_and_partial_databases_are_rejected_unchanged(
    tmp_path: Path, payload: bytes
) -> None:
    root = _private(tmp_path / hashlib.sha256(payload).hexdigest())
    database = root / _DATABASE_NAME
    database.write_bytes(payload)
    database.chmod(0o600)
    before = database.stat()

    factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.CI,
        private_root=root,
    )
    _failure(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT, factory.open)

    after = database.stat()
    assert database.read_bytes() == payload
    assert (after.st_dev, after.st_ino, after.st_mode, after.st_size) == (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
    )


def test_preexisting_foreign_sqlite_database_is_rejected_unchanged(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path / "foreign")
    database = root / _DATABASE_NAME
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE foreign_owner(value TEXT) STRICT")
    connection.commit()
    connection.close()
    database.chmod(0o600)
    before = database.read_bytes()
    before_inode = database.stat().st_ino

    factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.CI,
        private_root=root,
    )
    _failure(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT, factory.open)
    assert database.read_bytes() == before
    assert database.stat().st_ino == before_inode


def test_created_database_has_exact_strict_fk_index_and_trigger_inventory(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path / "exact")
    factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.CI,
        private_root=root,
    )
    store = factory.open()
    database = root / _DATABASE_NAME

    connection = sqlite3.connect(database)
    assert connection.execute("PRAGMA application_id").fetchone() == (_APPLICATION_ID,)
    assert connection.execute("PRAGMA user_version").fetchone() == (2,)
    assert {
        row[1]: (row[4], row[5])
        for row in connection.execute("PRAGMA table_list").fetchall()
        if row[1].startswith("audit_")
    } == {
        "audit_metadata_v2": (0, 1),
        "audit_atomic_marker_v2": (0, 1),
        "audit_event_v2": (0, 1),
    }
    assert (
        len(connection.execute("PRAGMA foreign_key_list(audit_event_v2)").fetchall())
        == 5
    )
    assert {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    } == {
        "audit_atomic_marker_v2_append_guard",
        "audit_atomic_marker_v2_no_update",
        "audit_atomic_marker_v2_no_delete",
        "audit_event_v2_append_guard",
        "audit_event_v2_no_update",
        "audit_event_v2_no_delete",
        "audit_metadata_v2_guard_update",
        "audit_metadata_v2_no_delete",
        "audit_metadata_v2_no_insert",
    }
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='audit_event_v2_correlation_sequence_idx'"
    ).fetchone() == ("audit_event_v2_correlation_sequence_idx",)
    connection.close()

    assert type(factory.external_action_count) is int
    assert factory.external_action_count == 0
    assert type(store.external_action_count) is int
    assert store.external_action_count == 0
    assert store.verify_chain() == (AUDIT_RUNTIME_GENESIS_SHA256_V2, 0)


def test_append_only_triggers_reject_mutation_and_invalid_transitions(
    tmp_path: Path,
) -> None:
    writer, request, _ = _bundle(tmp_path)
    writer.record(request)
    database = tmp_path / "audit" / _DATABASE_NAME
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys = ON")
    statements = (
        "UPDATE audit_event_v2 SET candidate_json='{}' WHERE sequence=1",
        "DELETE FROM audit_event_v2 WHERE sequence=1",
        "UPDATE audit_atomic_marker_v2 SET request_sha256='f' || substr(request_sha256,2) WHERE sequence=1",
        "DELETE FROM audit_atomic_marker_v2 WHERE sequence=1",
        "DELETE FROM audit_metadata_v2 WHERE singleton=1",
        "INSERT INTO audit_metadata_v2 SELECT * FROM audit_metadata_v2",
        "UPDATE audit_metadata_v2 SET event_count=event_count+2 WHERE singleton=1",
        "INSERT INTO audit_atomic_marker_v2 VALUES (3,'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','77777777-7777-4777-8777-777777777777','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc')",
    )
    for statement in statements:
        with pytest.raises(sqlite3.Error):
            connection.execute(statement)
    connection.rollback()
    connection.close()


def test_named_database_replacement_is_detected_by_live_process_anchor(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path / "replacement")
    factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.CI,
        private_root=root,
    )
    store = factory.open()
    assert store.verify_chain() == (AUDIT_RUNTIME_GENESIS_SHA256_V2, 0)
    database = root / _DATABASE_NAME
    original_inode = database.stat().st_ino
    replacement = root / "replacement.sqlite3"
    replacement.write_bytes(database.read_bytes())
    replacement.chmod(0o600)
    os.replace(replacement, database)
    assert database.stat().st_ino != original_inode

    _failure(AuditRuntimeFailureCodeV2.TAMPER_DETECTED, store.verify_chain)
    _failure(AuditRuntimeFailureCodeV2.TAMPER_DETECTED, factory.open)


def test_owner_root_replacement_is_detected_across_factory_reopen(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path / "root-replacement")
    factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.CI,
        private_root=root,
    )
    store = factory.open()
    database_payload = (root / _DATABASE_NAME).read_bytes()
    displaced = tmp_path / "displaced-root"
    root.rename(displaced)
    root = _private(tmp_path / "root-replacement")
    replacement_database = root / _DATABASE_NAME
    replacement_database.write_bytes(database_payload)
    replacement_database.chmod(0o600)

    _failure(AuditRuntimeFailureCodeV2.TAMPER_DETECTED, store.verify_chain)
    _failure(AuditRuntimeFailureCodeV2.TAMPER_DETECTED, factory.open)


def test_same_inode_older_valid_snapshot_is_detected_in_same_process(
    tmp_path: Path,
) -> None:
    writer, request, factory = _bundle(tmp_path)
    store = factory.open()
    assert store.verify_chain() == (AUDIT_RUNTIME_GENESIS_SHA256_V2, 0)
    database = tmp_path / "audit" / _DATABASE_NAME
    older = database.read_bytes()
    inode = database.stat().st_ino

    committed = writer.record(request)
    assert committed.record.sequence == 1
    database.write_bytes(older)
    assert database.stat().st_ino == inode

    _failure(AuditRuntimeFailureCodeV2.TAMPER_DETECTED, store.verify_chain)
    _failure(AuditRuntimeFailureCodeV2.TAMPER_DETECTED, factory.open)


def test_commit_exception_before_commit_is_known_rollback(
    tmp_path: Path,
) -> None:
    writer, request, factory = _bundle(
        tmp_path, fault=RecordedAuditFaultV2.BEFORE_COMMIT
    )
    _failure(
        AuditRuntimeFailureCodeV2.STORAGE_ROLLED_BACK, lambda: writer.record(request)
    )
    assert factory.open().verify_chain() == (AUDIT_RUNTIME_GENESIS_SHA256_V2, 0)


def test_concurrent_first_append_serializes_to_one_exact_event(tmp_path: Path) -> None:
    source_writer, source_request, _ = _bundle(tmp_path / "source")
    candidate = source_writer.record(source_request).record.candidate
    target_factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.CI,
        private_root=_private(tmp_path / "target"),
    )
    target = target_factory.open()
    barrier = Barrier(3)
    receipts: list[AuditAppendReceiptV2] = []
    failures: list[BaseException] = []

    def append() -> None:
        try:
            barrier.wait()
            receipts.append(target.append_atomic(candidate))
        except BaseException as error:
            failures.append(error)

    threads = (Thread(target=append), Thread(target=append))
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert failures == []
    assert len(receipts) == 2
    assert {receipt.replayed for receipt in receipts} == {False, True}
    assert target.verify_chain()[1] == 1


def test_cross_process_append_serializes_with_exact_unknown_recovery(
    tmp_path: Path,
) -> None:
    source_writer, source_request, _ = _bundle(tmp_path / "source-process")
    candidate = source_writer.record(source_request).record.candidate
    target_factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.CI,
        private_root=_private(tmp_path / "target-process"),
    )
    assert target_factory.open().verify_chain() == (
        AUDIT_RUNTIME_GENESIS_SHA256_V2,
        0,
    )
    start_read, start_write = os.pipe()
    children: list[tuple[int, int]] = []
    for _index in range(2):
        result_read, result_write = os.pipe()
        process_id = os.fork()
        if process_id == 0:
            os.close(start_write)
            os.close(result_read)
            try:
                if os.read(start_read, 1) != b"G":
                    os._exit(2)
                store = target_factory.open()
                try:
                    receipt = store.append_atomic(candidate)
                except AuditRuntimeFailureV2 as error:
                    if (
                        error.code
                        is not AuditRuntimeFailureCodeV2.STORAGE_COMMIT_UNKNOWN
                    ):
                        raise
                    receipt = store.recover_exact(candidate)
                os.write(result_write, b"R" if receipt.replayed else b"N")
                os._exit(0)
            except AuditRuntimeFailureV2 as error:
                os.write(result_write, b"E:" + error.code.value.encode("ascii"))
                os._exit(1)
            except BaseException:
                os.write(result_write, b"E:UNEXPECTED")
                os._exit(1)
        os.close(result_write)
        children.append((process_id, result_read))
    os.close(start_read)
    os.write(start_write, b"GG")
    os.close(start_write)

    outcomes: list[bytes] = []
    statuses: list[int] = []
    for process_id, result_read in children:
        outcomes.append(os.read(result_read, 128))
        os.close(result_read)
        waited_process, status = os.waitpid(process_id, 0)
        assert waited_process == process_id
        statuses.append(status)

    assert sorted(outcomes) == [b"N", b"R"]
    assert statuses == [0, 0]
    assert target_factory.open().verify_chain()[1] == 1


def test_redundant_column_tamper_is_detected_after_exact_trigger_restoration(
    tmp_path: Path,
) -> None:
    writer, request, factory = _bundle(tmp_path)
    writer.record(request)
    database = tmp_path / "audit" / _DATABASE_NAME
    connection = sqlite3.connect(database)
    trigger = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='audit_event_v2_no_update'"
    ).fetchone()
    assert trigger is not None and type(trigger[0]) is str
    connection.execute("DROP TRIGGER audit_event_v2_no_update")
    connection.execute(
        "UPDATE audit_event_v2 SET correlation_id='77777777-7777-4777-8777-777777777777' WHERE sequence=1"
    )
    connection.execute(trigger[0])
    connection.commit()
    connection.close()

    _failure(AuditRuntimeFailureCodeV2.TAMPER_DETECTED, factory.open)


def test_schema_trigger_drift_is_classified_before_row_use(tmp_path: Path) -> None:
    writer, request, factory = _bundle(tmp_path)
    writer.record(request)
    database = tmp_path / "audit" / _DATABASE_NAME
    connection = sqlite3.connect(database)
    connection.execute("DROP TRIGGER audit_event_v2_no_delete")
    connection.commit()
    connection.close()

    _failure(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT, factory.open)


def test_nonzero_or_mutating_collaborator_action_count_fails_closed(
    tmp_path: Path,
) -> None:
    authorization, _, session, _ = durable_authorization_bundle(
        _private(tmp_path / "authorization")
    )
    grant = authorization.recover_admin(
        command_id=AUTHORIZATION_COMMAND_ID,
        session_id=session.session_id,
        now=NOW,
    ).grant()
    delegate = RecordedAuditAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=1,
        context_script=(audit_context(grant),),
    )
    factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.CI,
        private_root=_private(tmp_path / "audit"),
    )
    request = DurableAuditRequestV2(
        authorization_command_id=AUTHORIZATION_COMMAND_ID,
        session_id=session.session_id,
        now=NOW,
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.NOTICE,
        reason_code=AuditReasonCode("RECORDED:ST0405:COLLABORATOR_CHECK"),
    )

    class MutatingContext:
        def __init__(self) -> None:
            self.reads = 0
            self.calls = 0

        @property
        def external_action_count(self) -> int:
            self.reads += 1
            return 0 if self.reads <= 2 else 1

        def issue(self, supplied_grant: object) -> object:
            self.calls += 1
            return delegate.issue(supplied_grant)  # type: ignore[arg-type]

    context = MutatingContext()
    writer = DurableAuditWriterV2(
        authorization=authorization,
        context_source=context,  # type: ignore[arg-type]
        store_factory=factory,
    )
    _failure(AuditRuntimeFailureCodeV2.TAMPER_DETECTED, lambda: writer.record(request))
    assert context.calls == 1
    assert factory.open().verify_chain() == (AUDIT_RUNTIME_GENESIS_SHA256_V2, 0)

    class InvalidCounterFactory:
        open_count = 0

        def __init__(self, counter: object) -> None:
            self.external_action_count = counter

        def open(self) -> object:
            self.open_count += 1
            raise AssertionError("invalid authority must be rejected before open")

    for invalid_counter in (1, True, "0"):
        invalid = InvalidCounterFactory(invalid_counter)
        writer2 = DurableAuditWriterV2(
            authorization=authorization,
            context_source=delegate,
            store_factory=invalid,  # type: ignore[arg-type]
        )
        _failure(
            AuditRuntimeFailureCodeV2.TAMPER_DETECTED,
            lambda: writer2.record(request),
        )
        assert invalid.open_count == 0


def test_runtime_surfaces_report_exact_zero_external_actions(tmp_path: Path) -> None:
    writer, _, factory = _bundle(tmp_path)
    store = factory.open()
    for value in (writer, factory, store):
        assert type(value.external_action_count) is int
        assert value.external_action_count == 0
