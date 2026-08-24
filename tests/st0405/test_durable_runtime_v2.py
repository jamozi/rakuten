"""Durability, authorization provenance, and fail-closed query tests for ST-0405."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import pickle
import sqlite3
from threading import Barrier, Thread
from uuid import UUID

import pytest

from conftest import (
    ACTOR_ID,
    AUTHORIZATION_COMMAND_ID,
    EVENT_ID,
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
    DisabledAuditQueryServiceV2,
    DurableAuditRequestV2,
    DurableAuditWriterV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import SessionId
from raos.domain.iam.authorization import AuthorizationCommandId
from raos.domain.ops.audit import (
    AuditActorType,
    AuditOutcome,
    AuditReasonCode,
    AuditSeverity,
)
from raos.domain.ops.audit_runtime_v2 import (
    AUDIT_QUERY_BLOCK_REASON_V2,
    AUDIT_RUNTIME_GENESIS_SHA256_V2,
    AuditRuntimeFailureCodeV2,
    AuditRuntimeFailureV2,
)


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def _request(
    *,
    command_id: AuthorizationCommandId = AUTHORIZATION_COMMAND_ID,
    reason: str = "RECORDED:ST0405:AUTHORIZED_CHANGE",
) -> DurableAuditRequestV2:
    session_id = _CURRENT_SESSION
    if type(session_id) is not SessionId:
        raise AssertionError("test session has not been initialized")
    return DurableAuditRequestV2(
        authorization_command_id=command_id,
        session_id=session_id,
        now=NOW,
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.NOTICE,
        reason_code=AuditReasonCode(reason),
        before_hash="a" * 64,
        after_hash="b" * 64,
    )


_CURRENT_SESSION: SessionId | None = None


def _writer(
    tmp_path: Path,
    *,
    contexts: int = 1,
    fault: RecordedAuditFaultV2 | None = None,
) -> tuple[DurableAuditWriterV2, RecordedSqliteAuditRuntimeStoreFactoryV2]:
    global _CURRENT_SESSION
    authorization, _, session, _ = durable_authorization_bundle(
        _private(tmp_path / "authorization")
    )
    _CURRENT_SESSION = session.session_id
    grant = authorization.recover_admin(
        command_id=AUTHORIZATION_COMMAND_ID,
        session_id=session.session_id,
        now=NOW,
    ).grant()
    scripted = tuple(
        audit_context(
            grant,
            event_id=(
                EVENT_ID
                if index == 0
                else UUID(f"66666666-6666-4666-8666-{index:012d}")
            ),
        )
        for index in range(contexts)
    )
    context_source = RecordedAuditAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=max(contexts, 1),
        context_script=scripted,
    )
    factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=_private(tmp_path / "audit"),
        fault_once_at=fault,
    )
    return (
        DurableAuditWriterV2(
            authorization=authorization,
            context_source=context_source,
            store_factory=factory,
        ),
        factory,
    )


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


def test_durable_append_restart_exact_query_and_chain(tmp_path: Path) -> None:
    writer, factory = _writer(tmp_path)
    committed = writer.record(_request())

    assert committed.receipt.replayed is False
    assert committed.recovered_after_commit_ambiguity is False
    assert committed.record.sequence == 1
    assert committed.record.previous_entry_sha256 == AUDIT_RUNTIME_GENESIS_SHA256_V2
    assert committed.record.candidate.event_id == EVENT_ID
    assert committed.record.candidate.actor_type == AuditActorType.USER.value
    assert committed.record.candidate.actor_id == ACTOR_ID
    assert committed.record.candidate.action == "edit_article_draft"
    assert committed.record.candidate.target_type == "ARTICLE_VERSION"
    assert committed.record.candidate.outcome == "SUCCESS"

    restarted = factory.open()
    assert restarted.verify_chain() == (committed.record.entry_sha256, 1)
    assert restarted.load_exact(EVENT_ID) == committed.record
    assert restarted.query_internal_correlation(
        committed.record.candidate.correlation_id, limit=10
    ) == (committed.record,)


def test_same_authorization_and_request_replays_without_consuming_context(
    tmp_path: Path,
) -> None:
    writer, factory = _writer(tmp_path, contexts=1)
    first = writer.record(_request())
    second = writer.record(_request())
    assert second.record == first.record
    assert second.receipt.replayed is True
    assert second.recovered_after_commit_ambiguity is False
    assert factory.open().verify_chain()[1] == 1


def test_same_authorization_with_different_request_is_conflict(tmp_path: Path) -> None:
    writer, factory = _writer(tmp_path, contexts=1)
    writer.record(_request())
    _failure(
        AuditRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT,
        lambda: writer.record(_request(reason="RECORDED:ST0405:DIFFERENT")),
    )
    assert factory.open().verify_chain()[1] == 1


def test_atomic_marker_rolls_back_with_event_and_retry_can_commit(
    tmp_path: Path,
) -> None:
    writer, factory = _writer(
        tmp_path,
        contexts=2,
        fault=RecordedAuditFaultV2.AFTER_MARKER_BEFORE_EVENT,
    )
    _failure(
        AuditRuntimeFailureCodeV2.STORAGE_ROLLED_BACK, lambda: writer.record(_request())
    )
    assert factory.open().verify_chain() == (AUDIT_RUNTIME_GENESIS_SHA256_V2, 0)

    committed = writer.record(_request())
    assert committed.record.candidate.event_id != EVENT_ID
    assert factory.open().verify_chain()[1] == 1


def test_commit_ambiguity_recovers_exactly_without_second_append(
    tmp_path: Path,
) -> None:
    writer, factory = _writer(
        tmp_path,
        fault=RecordedAuditFaultV2.AFTER_COMMIT,
    )
    committed = writer.record(_request())
    assert committed.recovered_after_commit_ambiguity is True
    assert committed.receipt.replayed is True
    assert factory.open().verify_chain()[1] == 1


def test_authorization_failure_precedes_audit_store_open_and_context_issue(
    tmp_path: Path,
) -> None:
    global _CURRENT_SESSION
    authorization, _, session, _ = durable_authorization_bundle(
        _private(tmp_path / "authorization"), revoked=True
    )
    _CURRENT_SESSION = session.session_id

    class ContextProbe:
        calls = 0

        def issue(self, grant: object) -> object:
            del grant
            self.calls += 1
            raise AssertionError("context must not be requested")

    context = ContextProbe()
    factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=tmp_path / "missing-audit-root",
    )
    writer = DurableAuditWriterV2(
        authorization=authorization,
        context_source=context,  # type: ignore[arg-type]
        store_factory=factory,
    )
    _failure(
        AuditRuntimeFailureCodeV2.AUTHORIZATION_DENIED,
        lambda: writer.record(_request()),
    )
    assert factory.open_count == 0
    assert context.calls == 0
    assert not (tmp_path / "missing-audit-root").exists()


def test_unknown_authorization_command_cannot_open_store(tmp_path: Path) -> None:
    writer, factory = _writer(tmp_path)
    _failure(
        AuditRuntimeFailureCodeV2.AUTHORIZATION_DENIED,
        lambda: writer.record(
            _request(
                command_id=AuthorizationCommandId(
                    "RECORDED:ST0405:AUTHORIZATION:UNKNOWN"
                )
            )
        ),
    )
    assert factory.open_count == 0


def test_outward_query_is_blocked_before_store_open(tmp_path: Path) -> None:
    factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.CI,
        private_root=tmp_path / "not-created",
    )
    query = DisabledAuditQueryServiceV2(store_factory=factory)
    assert query.block_reason == AUDIT_QUERY_BLOCK_REASON_V2
    _failure(
        AuditRuntimeFailureCodeV2.QUERY_AUTHORIZATION_UNAVAILABLE,
        lambda: query.query(UUID(int=1), limit=1),
    )
    assert factory.open_count == 0
    assert not (tmp_path / "not-created").exists()


def test_database_row_and_schema_tampering_fail_closed(tmp_path: Path) -> None:
    writer, factory = _writer(tmp_path)
    writer.record(_request())
    database = tmp_path / "audit" / "st0405-recorded-audit-runtime-v2.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("UPDATE audit_event_v2 SET candidate_json='{}' WHERE sequence=1")
    connection.commit()
    connection.close()
    _failure(AuditRuntimeFailureCodeV2.TAMPER_DETECTED, factory.open)

    writer2, factory2 = _writer(tmp_path / "schema")
    writer2.record(_request())
    database2 = (
        tmp_path / "schema" / "audit" / "st0405-recorded-audit-runtime-v2.sqlite3"
    )
    connection = sqlite3.connect(database2)
    connection.execute("ALTER TABLE audit_event_v2 ADD COLUMN surprise TEXT")
    connection.commit()
    connection.close()
    _failure(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT, factory2.open)


def test_private_path_permissions_and_symlink_are_rejected_after_authorization(
    tmp_path: Path,
) -> None:
    writer, _ = _writer(tmp_path / "baseline")
    del writer
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

    open_root = tmp_path / "open-root"
    open_root.mkdir(mode=0o777)
    open_root.chmod(0o777)
    factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=open_root,
    )
    writer = DurableAuditWriterV2(
        authorization=authorization,
        context_source=context,
        store_factory=factory,
    )
    global _CURRENT_SESSION
    _CURRENT_SESSION = session.session_id
    _failure(
        AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE, lambda: writer.record(_request())
    )

    target = _private(tmp_path / "real-root")
    link = tmp_path / "link-root"
    link.symlink_to(target, target_is_directory=True)
    symlink_factory = RecordedSqliteAuditRuntimeStoreFactoryV2(
        environment=RuntimeEnvironment.CI,
        private_root=link,
    )
    _failure(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE, symlink_factory.open)


def test_concurrent_exact_replay_keeps_one_row(tmp_path: Path) -> None:
    writer, factory = _writer(tmp_path)
    committed = writer.record(_request())
    store = factory.open()
    candidate = committed.record.candidate
    barrier = Barrier(3)
    receipts: list[object] = []

    def run() -> None:
        barrier.wait()
        receipts.append(store.append_atomic(candidate))

    threads = (Thread(target=run), Thread(target=run))
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert len(receipts) == 2
    assert all(receipt.replayed is True for receipt in receipts)  # type: ignore[attr-defined]
    assert store.verify_chain()[1] == 1


def test_values_are_immutable_redacted_and_failure_supports_traceback_metadata(
    tmp_path: Path,
) -> None:
    writer, _ = _writer(tmp_path)
    committed = writer.record(_request())
    with pytest.raises(FrozenInstanceError):
        committed.record.sequence = 2  # type: ignore[misc]
    assert "RECORDED" not in repr(committed.record)
    assert "RECORDED" not in repr(committed.receipt)
    for value in (committed.record, committed.receipt, committed.record.candidate):
        with pytest.raises((TypeError, pickle.PicklingError)):
            pickle.dumps(value)

    with pytest.raises(AuditRuntimeFailureV2) as caught:
        raise AuditRuntimeFailureV2(AuditRuntimeFailureCodeV2.INVALID_ARGUMENT)
    caught.value.__traceback__ = caught.value.__traceback__
    assert caught.value.code is AuditRuntimeFailureCodeV2.INVALID_ARGUMENT


def test_candidate_mutation_cannot_validate_as_persisted_record(tmp_path: Path) -> None:
    writer, _ = _writer(tmp_path)
    committed = writer.record(_request())
    with pytest.raises(AuditRuntimeFailureV2) as caught:
        replace(
            committed.record,
            candidate=replace(
                committed.record.candidate,
                request_sha256="f" * 64,
            ),
        )
    assert caught.value.code is AuditRuntimeFailureCodeV2.TAMPER_DETECTED
