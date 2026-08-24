"""Durability, concurrency, tamper and owner-private storage tests for ST-0406 V2."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
from uuid import UUID

import pytest

from conftest import (
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
        "st0406_intake_result",
        "st0406_duplicate_index",
    ):
        with sqlite3.connect(database) as connection:
            with pytest.raises(sqlite3.IntegrityError, match="ST0406_APPEND_ONLY"):
                connection.execute(f"DELETE FROM {table}")
    repository.verify_integrity()


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
