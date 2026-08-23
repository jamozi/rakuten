"""Adapter-private Session context and pending-event atomicity tests."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid7

import pytest
from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.session_runtime import (
    bind_session_runtime,
    clear_session_runtime,
    deterministic_event_id,
    persistence_context,
    register_pending_events,
    require_no_unstaged_pending_events,
    require_session_runtime,
    stage_pending_events,
    stage_registered_events,
)
from raos.adapters.persistence.sqlalchemy.shared import SqlAlchemyOutboxEventAppender
from raos.adapters.persistence.sqlalchemy.transaction import (
    _ExecutionStateFactory,
    _SqlAlchemyTransaction,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    PendingEventBuffer,
)
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from tests.st0308_persistence.support import make_context, make_event


def _bound_session(*, suffix: str) -> tuple[Session, _SqlAlchemyTransaction]:
    session = Session()
    transaction = _SqlAlchemyTransaction(
        transaction_id=uuid7(),
        context=make_context(suffix=suffix),
        timestamp=AwareUtcDateTime(datetime.now(timezone.utc)),
        session=session,
        execution_state=_ExecutionStateFactory().new_outer_state(),
    )
    bind_session_runtime(
        session,
        transaction=transaction,
        outbox=SqlAlchemyOutboxEventAppender(transaction),
    )
    return session, transaction


def test_session_runtime_binds_one_exact_immutable_context_and_clears() -> None:
    session, transaction = _bound_session(suffix="binding")
    try:
        assert persistence_context(session) is transaction.context
        with pytest.raises(PersistenceError) as duplicate:
            bind_session_runtime(
                session,
                transaction=transaction,
                outbox=SqlAlchemyOutboxEventAppender(transaction),
            )
        assert duplicate.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
        clear_session_runtime(session)
        with pytest.raises(PersistenceError) as absent:
            require_session_runtime(session)
        assert absent.value.code is PersistenceErrorCode.TRANSACTION_OWNERSHIP
    finally:
        session.close()


def test_deterministic_event_id_is_retry_stable_uuid7() -> None:
    first_session, first_transaction = _bound_session(suffix="event-id")
    second_session = Session()
    second_transaction = _SqlAlchemyTransaction(
        transaction_id=uuid7(),
        context=first_transaction.context,
        timestamp=first_transaction.timestamp,
        session=second_session,
        execution_state=_ExecutionStateFactory().new_outer_state(),
    )
    bind_session_runtime(
        second_session,
        transaction=second_transaction,
        outbox=SqlAlchemyOutboxEventAppender(second_transaction),
    )
    event = make_event(suffix="deterministic")
    arguments = {
        "event_type": event.descriptor.event_type,
        "aggregate_id": event.aggregate_id.value,
        "aggregate_version": event.aggregate_version,
    }
    try:
        first = deterministic_event_id(first_session, **arguments)
        second = deterministic_event_id(second_session, **arguments)
        assert first == second
        assert first.version == 7
        assert first.variant == "specified in RFC 4122"
    finally:
        clear_session_runtime(first_session)
        clear_session_runtime(second_session)
        first_session.close()
        second_session.close()


def test_stage_pending_event_acknowledges_and_known_rollback_restores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, transaction = _bound_session(suffix="stage")
    captured: list[object] = []

    def append_many(
        _self: SqlAlchemyOutboxEventAppender,
        events: tuple[object, ...],
    ) -> None:
        captured.extend(events)

    monkeypatch.setattr(SqlAlchemyOutboxEventAppender, "append_many", append_many)
    event = make_event(suffix="stage")
    buffer = PendingEventBuffer((event,))
    try:
        stage_pending_events(
            session,
            buffer,
            owning_method="JobRepository.add",
            persisted_version=AggregateVersion(0),
            expected_event_type="jp.raos.ops.job_requested.v1",
        )
        assert len(captured) == 1
        assert buffer.pending_events() == ()
        transaction.restore_acknowledged()
        assert buffer.pending_events() == (event,)
    finally:
        clear_session_runtime(session)
        session.close()


def test_stage_pending_event_fails_closed_on_method_or_version_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, transaction = _bound_session(suffix="mismatch")
    monkeypatch.setattr(
        SqlAlchemyOutboxEventAppender,
        "append_many",
        lambda _self, _events: None,
    )
    event = make_event(suffix="mismatch")
    buffer = PendingEventBuffer((event,))
    try:
        with pytest.raises(PersistenceError) as caught:
            stage_pending_events(
                session,
                buffer,
                owning_method="OfferRepository.append_observations",
                persisted_version=AggregateVersion(1),
                expected_event_type="jp.raos.catalog.offer_observed.v1",
            )
        assert caught.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
        assert transaction.rollback_only is True
        assert buffer.pending_events() == (event,)
    finally:
        clear_session_runtime(session)
        session.close()


def test_registered_root_event_cannot_be_silently_committed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, transaction = _bound_session(suffix="registered")
    monkeypatch.setattr(
        SqlAlchemyOutboxEventAppender,
        "append_many",
        lambda _self, _events: None,
    )
    event = make_event(suffix="registered")
    buffer = PendingEventBuffer((event,))
    register_pending_events(
        session,
        aggregate_type="ops.job",
        aggregate_id=event.aggregate_id.value,
        buffer=buffer,
    )
    try:
        with pytest.raises(PersistenceError) as caught:
            require_no_unstaged_pending_events(session)
        assert caught.value.code is PersistenceErrorCode.STATE_CONFLICT
        assert transaction.rollback_only is True
        transaction.rollback_only = False
        stage_registered_events(
            session,
            aggregate_type="ops.job",
            aggregate_id=event.aggregate_id.value,
            owning_method="JobRepository.add",
            persisted_version=AggregateVersion(0),
            expected_event_type="jp.raos.ops.job_requested.v1",
        )
        require_no_unstaged_pending_events(session)
        assert buffer.pending_events() == ()
    finally:
        clear_session_runtime(session)
        session.close()


def test_stage_pending_event_rejects_wrong_specialization_before_outbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, transaction = _bound_session(suffix="specialization")
    append_calls = 0

    def append_many(
        _self: SqlAlchemyOutboxEventAppender,
        _events: tuple[object, ...],
    ) -> None:
        nonlocal append_calls
        append_calls += 1

    monkeypatch.setattr(SqlAlchemyOutboxEventAppender, "append_many", append_many)
    event = make_event(suffix="specialization")
    buffer = PendingEventBuffer((event,))
    try:
        with pytest.raises(PersistenceError) as caught:
            stage_pending_events(
                session,
                buffer,
                owning_method="JobRepository.add",
                persisted_version=AggregateVersion(0),
                expected_event_type="jp.raos.ai.job_requested.v1",
            )
        assert caught.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
        assert transaction.rollback_only is True
        assert append_calls == 0
        assert buffer.pending_events() == (event,)
    finally:
        clear_session_runtime(session)
        session.close()
