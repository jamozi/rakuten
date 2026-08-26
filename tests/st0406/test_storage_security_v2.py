"""Durability, concurrency, tamper and owner-private storage tests for ST-0406 V2."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
from uuid import UUID

import pytest

from .support import (
    V2_NOW,
    v2_authorization_runtime,
    v2_descriptor,
    v2_intake_runtime,
    v2_source,
)
from raos.adapters.recorded_object_intake_runtime_v2 import (
    RecordedSqliteObjectIntakeRepositoryV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.application.ops.object_intake_runtime_v2 import SecureObjectIntakeRuntimeV2
from raos.domain.iam.authentication import Session
from raos.domain.iam.authorization import (
    AuthorizationCommandResult,
    AuthorizationEvaluationCommand,
)
from raos.domain.ops.object_intake_runtime_v2 import (
    DurableIntakeDescriptorV2,
    DurableQuarantineReceiptV2,
    IntakeCommandId,
    ObjectIntakeRuntimeFailure,
    ObjectIntakeRuntimeFailureCode,
)
from raos.ports.object_intake_runtime_v2 import BoundedIntakeSourceV2


_DATABASE = "secure-object-intake-runtime-v2.sqlite3"


def _intake(
    runtime: SecureObjectIntakeRuntimeV2,
    *,
    command_id: str,
    descriptor: DurableIntakeDescriptorV2,
    session: Session,
    authorization_command: AuthorizationEvaluationCommand,
    authorization_result: AuthorizationCommandResult,
    source: BoundedIntakeSourceV2,
) -> DurableQuarantineReceiptV2:
    return runtime.intake(
        command_id=IntakeCommandId(command_id),
        descriptor=descriptor,
        session_id=session.session_id,
        authorization_command=authorization_command,
        authorization_result=authorization_result,
        authorization_checked_at=V2_NOW,
        source=source,
    )


def test_concurrent_same_command_has_one_exact_durable_outcome(tmp_path: Path) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    runtime, repository = v2_intake_runtime(tmp_path, authorization_service=auth)
    descriptor = v2_descriptor()
    sources = (v2_source(), v2_source())

    def invoke(index: int) -> DurableQuarantineReceiptV2:
        return _intake(
            runtime,
            command_id="RECORDED:ST0406:INTAKE:CONCURRENT",
            descriptor=descriptor,
            session=session,
            authorization_command=command,
            authorization_result=result,
            source=sources[index],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = tuple(executor.map(invoke, (0, 1)))

    assert receipts[0] == receipts[1]
    assert sum(source.remaining_bytes == 0 for source in sources) == 1
    repository.verify_integrity()


def test_same_command_with_changed_descriptor_is_an_idempotency_conflict(
    tmp_path: Path,
) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    runtime, repository = v2_intake_runtime(tmp_path, authorization_service=auth)
    _intake(
        runtime,
        command_id="RECORDED:ST0406:INTAKE:CONFLICT",
        descriptor=v2_descriptor(),
        session=session,
        authorization_command=command,
        authorization_result=result,
        source=v2_source(),
    )
    changed = v2_descriptor(intake_id=UUID(int=7))
    untouched = v2_source()
    with pytest.raises(ObjectIntakeRuntimeFailure) as caught:
        _intake(
            runtime,
            command_id="RECORDED:ST0406:INTAKE:CONFLICT",
            descriptor=changed,
            session=session,
            authorization_command=command,
            authorization_result=result,
            source=untouched,
        )
    assert caught.value.code is ObjectIntakeRuntimeFailureCode.IDEMPOTENCY_CONFLICT
    assert untouched.remaining_bytes == changed.descriptor.declared_size
    repository.verify_integrity()


def test_content_row_tamper_and_schema_drift_fail_closed(tmp_path: Path) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    runtime, repository = v2_intake_runtime(tmp_path, authorization_service=auth)
    _intake(
        runtime,
        command_id="RECORDED:ST0406:INTAKE:TAMPER",
        descriptor=v2_descriptor(),
        session=session,
        authorization_command=command,
        authorization_result=result,
        source=v2_source(),
    )
    database = tmp_path / "intake" / _DATABASE
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE st0406_quarantine SET content=x'00'")
    with pytest.raises(ObjectIntakeRuntimeFailure) as tampered:
        repository.verify_integrity()
    assert tampered.value.code is ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED

    schema_root = tmp_path / "schema-drift"
    RecordedSqliteObjectIntakeRepositoryV2(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=schema_root,
    )
    with sqlite3.connect(schema_root / _DATABASE) as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(ObjectIntakeRuntimeFailure) as drifted:
        RecordedSqliteObjectIntakeRepositoryV2(
            environment=RuntimeEnvironment.ENV_DEV,
            private_root=schema_root,
        )
    assert drifted.value.code is ObjectIntakeRuntimeFailureCode.SCHEMA_DRIFT


def test_append_only_event_result_and_duplicate_rows_reject_mutation(
    tmp_path: Path,
) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    runtime, repository = v2_intake_runtime(tmp_path, authorization_service=auth)
    _intake(
        runtime,
        command_id="RECORDED:ST0406:INTAKE:IMMUTABLE",
        descriptor=v2_descriptor(),
        session=session,
        authorization_command=command,
        authorization_result=result,
        source=v2_source(),
    )
    database = tmp_path / "intake" / _DATABASE
    for table in (
        "st0406_quarantine_event",
        "st0406_intake_command",
        "st0406_intake_audit",
        "st0406_intake_result",
        "st0406_duplicate_index",
        "st0406_quarantine",
    ):
        with sqlite3.connect(database) as connection:
            with pytest.raises(sqlite3.IntegrityError, match="ST0406_APPEND_ONLY"):
                connection.execute(f"DELETE FROM {table}")
            if table != "st0406_quarantine":
                with pytest.raises(sqlite3.IntegrityError, match="ST0406_APPEND_ONLY"):
                    connection.execute(
                        f"UPDATE {table} SET record_sha256=record_sha256"
                    )
    repository.verify_integrity()


def test_preexisting_empty_partial_foreign_and_hardlinked_database_are_rejected(
    tmp_path: Path,
) -> None:
    for case in ("empty", "partial", "foreign", "hardlink", "symlink", "fifo"):
        root = tmp_path / case
        root.mkdir(mode=0o700)
        os.chmod(root, 0o700)
        database = root / _DATABASE
        if case == "empty":
            database.touch(mode=0o600)
        elif case == "partial":
            database.write_bytes(b"not-a-sqlite-database")
            os.chmod(database, 0o600)
        elif case == "foreign":
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE foreign_table(value TEXT)")
            os.chmod(database, 0o600)
        elif case == "hardlink":
            source = root / "foreign.sqlite3"
            source.write_bytes(b"not-a-sqlite-database")
            os.chmod(source, 0o600)
            os.link(source, database)
        elif case == "symlink":
            source = root / "foreign.sqlite3"
            source.write_bytes(b"not-a-sqlite-database")
            os.chmod(source, 0o600)
            database.symlink_to(source.name)
        else:
            os.mkfifo(database, 0o600)
        with pytest.raises(ObjectIntakeRuntimeFailure) as caught:
            RecordedSqliteObjectIntakeRepositoryV2(
                environment=RuntimeEnvironment.ENV_DEV,
                private_root=root,
            )
        assert caught.value.code in {
            ObjectIntakeRuntimeFailureCode.STORAGE_FAILED,
            ObjectIntakeRuntimeFailureCode.SCHEMA_DRIFT,
        }


def test_schema_is_strict_exact_and_all_three_journals_are_canonical(
    tmp_path: Path,
) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    runtime, repository = v2_intake_runtime(tmp_path, authorization_service=auth)
    _intake(
        runtime,
        command_id="RECORDED:ST0406:INTAKE:SCHEMA",
        descriptor=v2_descriptor(),
        session=session,
        authorization_command=command,
        authorization_result=result,
        source=v2_source(),
    )
    database = tmp_path / "intake" / _DATABASE
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA application_id").fetchone() == (
            1_380_400_602,
        )
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        strict = connection.execute(
            "SELECT name,strict FROM pragma_table_list "
            "WHERE schema='main' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        assert strict and all(row[1] == 1 for row in strict)
        explicit_indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='index' AND sql IS NOT NULL"
            )
        }
        assert explicit_indexes == {
            "st0406_audit_command_sequence",
            "st0406_command_command_version",
            "st0406_event_command_version",
        }
        lifecycle = connection.execute(
            "SELECT event_document FROM st0406_quarantine_event ORDER BY sequence"
        ).fetchall()
        commands = connection.execute(
            "SELECT intent_document,result_document FROM st0406_intake_command "
            "ORDER BY sequence"
        ).fetchall()
        counts = connection.execute(
            "SELECT event_count,command_count,audit_count FROM st0406_runtime_metadata"
        ).fetchone()
        assert counts == (len(lifecycle), len(commands), len(commands))
        documents = [row[0] for row in lifecycle]
        documents.extend(value for row in commands for value in row)
        for document in documents:
            assert (
                json.dumps(
                    json.loads(document),
                    ensure_ascii=True,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                == document
            )
        with pytest.raises(
            sqlite3.IntegrityError, match="ST0406_METADATA_TRANSITION_INVALID"
        ):
            connection.execute(
                "UPDATE st0406_runtime_metadata SET event_count=event_count+1"
            )
    repository.verify_integrity()


def test_same_inode_snapshot_rollback_and_database_replacement_are_detected(
    tmp_path: Path,
) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    runtime, repository = v2_intake_runtime(tmp_path, authorization_service=auth)
    _intake(
        runtime,
        command_id="RECORDED:ST0406:INTAKE:ANCHOR-1",
        descriptor=v2_descriptor(),
        session=session,
        authorization_command=command,
        authorization_result=result,
        source=v2_source(),
    )
    database = tmp_path / "intake" / _DATABASE
    snapshot = database.read_bytes()
    anchored_inode = database.stat().st_ino
    _intake(
        runtime,
        command_id="RECORDED:ST0406:INTAKE:ANCHOR-2",
        descriptor=v2_descriptor(
            intake_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        ),
        session=session,
        authorization_command=command,
        authorization_result=result,
        source=v2_source(),
    )
    with database.open("r+b") as stream:
        stream.truncate(0)
        stream.write(snapshot)
        stream.flush()
        os.fsync(stream.fileno())
    assert database.stat().st_ino == anchored_inode
    with pytest.raises(ObjectIntakeRuntimeFailure) as rolled_back:
        repository.verify_integrity()
    assert rolled_back.value.code is ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED

    replacement_root = tmp_path / "replacement-case"
    replacement_repository = RecordedSqliteObjectIntakeRepositoryV2(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=replacement_root,
    )
    replacement_database = replacement_root / _DATABASE
    replacement_bytes = replacement_database.read_bytes()
    replacement = replacement_root / "replacement.sqlite3"
    replacement.write_bytes(replacement_bytes)
    os.chmod(replacement, 0o600)
    os.replace(replacement, replacement_database)
    with pytest.raises(ObjectIntakeRuntimeFailure) as replaced:
        replacement_repository.verify_integrity()
    assert replaced.value.code is ObjectIntakeRuntimeFailureCode.STORAGE_FAILED


def test_private_root_rejects_symlink_and_non_owner_mode(tmp_path: Path) -> None:
    owned = tmp_path / "owned"
    owned.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(owned, target_is_directory=True)
    with pytest.raises(ObjectIntakeRuntimeFailure) as symlinked:
        RecordedSqliteObjectIntakeRepositoryV2(
            environment=RuntimeEnvironment.ENV_DEV,
            private_root=linked,
        )
    assert symlinked.value.code is ObjectIntakeRuntimeFailureCode.STORAGE_FAILED

    insecure = tmp_path / "insecure"
    insecure.mkdir(mode=0o755)
    os.chmod(insecure, 0o755)
    with pytest.raises(ObjectIntakeRuntimeFailure) as bad_mode:
        RecordedSqliteObjectIntakeRepositoryV2(
            environment=RuntimeEnvironment.ENV_DEV,
            private_root=insecure,
        )
    assert bad_mode.value.code is ObjectIntakeRuntimeFailureCode.STORAGE_FAILED


def test_repository_public_surface_has_no_content_or_lifecycle_operation() -> None:
    public = {
        name
        for name in dir(RecordedSqliteObjectIntakeRepositoryV2)
        if not name.startswith("_")
    }
    assert public == {"action_count", "begin", "recover", "verify_integrity"}
    forbidden = {
        "bytes",
        "cleanup",
        "delete",
        "download",
        "export",
        "lifecycle",
        "promote",
        "purge",
        "read",
        "release",
        "retention",
        "restore",
    }
    assert forbidden.isdisjoint(public)
