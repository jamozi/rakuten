"""Durable happy path, idempotency, duplicate, rejection and recovery tests."""

from __future__ import annotations

from pathlib import Path
import stat
from uuid import UUID

import pytest

from conftest import (
    CONTENT,
    V2_NOW,
    v2_authorization_runtime,
    v2_descriptor,
    v2_intake_runtime,
    v2_source,
)
from raos.adapters.recorded_object_intake_runtime_v2 import (
    DeterministicContentInspectorV2,
    DisabledMalwareScannerV2,
    RecordedIntakeCommitFault,
    RecordedSqliteObjectIntakeRepositoryV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.object_intake import DuplicateStatus
from raos.domain.ops.object_intake_runtime_v2 import (
    DurableIntakeDescriptorV2,
    DurableIntakeState,
    DurableQuarantineReceiptV2,
    IntakeCommandId,
    ObjectIntakeRuntimeFailure,
    ObjectIntakeRuntimeFailureCode,
)
from raos.application.ops.object_intake_runtime_v2 import SecureObjectIntakeRuntimeV2
from raos.domain.iam.authentication import Session
from raos.domain.iam.authorization import (
    AuthorizationCommandResult,
    AuthorizationEvaluationCommand,
)
from raos.ports.object_intake_runtime_v2 import BoundedIntakeSourceV2


class _CanarySource:
    def read_chunk(self, *, maximum_bytes: int) -> bytes:
        del maximum_bytes
        raise RuntimeError("SECRET_CANARY_SOURCE_V2") from None


def _invoke(
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


def test_exact_durable_authorization_precedes_clean_quarantine_and_restart(
    tmp_path: Path,
) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    runtime, repository = v2_intake_runtime(tmp_path, authorization_service=auth)
    descriptor = v2_descriptor()

    assert runtime.action_count == 0
    assert repository.action_count == 0
    assert DeterministicContentInspectorV2().action_count == 0

    receipt = _invoke(
        runtime,
        command_id="RECORDED:ST0406:INTAKE:1",
        descriptor=descriptor,
        session=session,
        authorization_command=command,
        authorization_result=result,
        source=v2_source(),
    )

    assert receipt.state is DurableIntakeState.CLEAN_QUARANTINED
    assert receipt.sha256 == descriptor.descriptor.declared_sha256
    assert receipt.authorization_resource_id == descriptor.authorization_resource_id
    assert receipt.duplicate_status is DuplicateStatus.NEW
    repository.verify_integrity()
    database = tmp_path / "intake" / "secure-object-intake-runtime-v2.sqlite3"
    assert stat.S_IMODE((tmp_path / "intake").stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600

    reopened = RecordedSqliteObjectIntakeRepositoryV2(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=tmp_path / "intake",
    )
    restarted_runtime, _ = v2_intake_runtime(
        tmp_path,
        authorization_service=auth,
        repository=reopened,
    )
    unused_source = v2_source()
    duplicate_call = _invoke(
        restarted_runtime,
        command_id="RECORDED:ST0406:INTAKE:1",
        descriptor=descriptor,
        session=session,
        authorization_command=command,
        authorization_result=result,
        source=unused_source,
    )
    assert duplicate_call == receipt
    assert unused_source.remaining_bytes == len(CONTENT)


def test_duplicate_index_is_deterministic_but_does_not_skip_scanning(
    tmp_path: Path,
) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    runtime, repository = v2_intake_runtime(tmp_path, authorization_service=auth)
    first = _invoke(
        runtime,
        command_id="RECORDED:ST0406:INTAKE:DUPLICATE-1",
        descriptor=v2_descriptor(),
        session=session,
        authorization_command=command,
        authorization_result=result,
        source=v2_source(),
    )
    second_descriptor = v2_descriptor(
        intake_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    )
    second = _invoke(
        runtime,
        command_id="RECORDED:ST0406:INTAKE:DUPLICATE-2",
        descriptor=second_descriptor,
        session=session,
        authorization_command=command,
        authorization_result=result,
        source=v2_source(),
    )
    assert first.duplicate_status is DuplicateStatus.NEW
    assert second.duplicate_status is DuplicateStatus.EXACT_DUPLICATE
    assert second.duplicate_of_intake_id == first.intake_id
    repository.verify_integrity()


def test_disabled_malware_scanner_persists_closed_rejection_and_replays_it(
    tmp_path: Path,
) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    scanner = DisabledMalwareScannerV2()
    assert scanner.action_count == 0
    runtime, repository = v2_intake_runtime(
        tmp_path,
        authorization_service=auth,
        malware_scanner=scanner,
    )
    descriptor = v2_descriptor()
    with pytest.raises(ObjectIntakeRuntimeFailure) as caught:
        _invoke(
            runtime,
            command_id="RECORDED:ST0406:INTAKE:DISABLED-SCANNER",
            descriptor=descriptor,
            session=session,
            authorization_command=command,
            authorization_result=result,
            source=v2_source(),
        )
    assert caught.value.code is ObjectIntakeRuntimeFailureCode.MALWARE_DISABLED
    repository.verify_integrity()

    untouched = v2_source()
    with pytest.raises(ObjectIntakeRuntimeFailure) as replayed:
        _invoke(
            runtime,
            command_id="RECORDED:ST0406:INTAKE:DISABLED-SCANNER",
            descriptor=descriptor,
            session=session,
            authorization_command=command,
            authorization_result=result,
            source=untouched,
        )
    assert replayed.value.code is ObjectIntakeRuntimeFailureCode.MALWARE_DISABLED
    assert untouched.remaining_bytes == len(CONTENT)


def test_after_commit_ambiguity_recovers_exact_accepted_outcome(tmp_path: Path) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    repository = RecordedSqliteObjectIntakeRepositoryV2(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=tmp_path / "intake",
        fault_once_at=RecordedIntakeCommitFault.AFTER_COMMIT,
    )
    runtime, _ = v2_intake_runtime(
        tmp_path,
        authorization_service=auth,
        repository=repository,
    )
    receipt = _invoke(
        runtime,
        command_id="RECORDED:ST0406:INTAKE:AFTER-COMMIT",
        descriptor=v2_descriptor(),
        session=session,
        authorization_command=command,
        authorization_result=result,
        source=v2_source(),
    )
    assert receipt.state is DurableIntakeState.CLEAN_QUARANTINED
    repository.verify_integrity()


def test_before_commit_fault_is_sanitized_and_leaves_no_recoverable_command(
    tmp_path: Path,
) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    repository = RecordedSqliteObjectIntakeRepositoryV2(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=tmp_path / "intake",
        fault_once_at=RecordedIntakeCommitFault.BEFORE_COMMIT,
    )
    runtime, _ = v2_intake_runtime(
        tmp_path,
        authorization_service=auth,
        repository=repository,
    )
    with pytest.raises(ObjectIntakeRuntimeFailure) as caught:
        _invoke(
            runtime,
            command_id="RECORDED:ST0406:INTAKE:BEFORE-COMMIT",
            descriptor=v2_descriptor(),
            session=session,
            authorization_command=command,
            authorization_result=result,
            source=v2_source(),
        )
    assert caught.value.code in {
        ObjectIntakeRuntimeFailureCode.STORAGE_FAILED,
        ObjectIntakeRuntimeFailureCode.STORAGE_COMMIT_UNKNOWN,
    }
    assert "CANARY" not in repr(caught.value)
    repository.verify_integrity()


def test_arbitrary_source_exception_is_sanitized_into_durable_rejection(
    tmp_path: Path,
) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    runtime, repository = v2_intake_runtime(tmp_path, authorization_service=auth)
    with pytest.raises(ObjectIntakeRuntimeFailure) as caught:
        _invoke(
            runtime,
            command_id="RECORDED:ST0406:INTAKE:CANARY-SOURCE",
            descriptor=v2_descriptor(),
            session=session,
            authorization_command=command,
            authorization_result=result,
            source=_CanarySource(),
        )
    assert caught.value.code is ObjectIntakeRuntimeFailureCode.SOURCE_FAILED
    assert "SECRET_CANARY" not in str(caught.value)
    assert "SECRET_CANARY" not in repr(caught.value)
    repository.verify_integrity()
    assert (
        b"SECRET_CANARY"
        not in (
            tmp_path / "intake" / "secure-object-intake-runtime-v2.sqlite3"
        ).read_bytes()
    )
