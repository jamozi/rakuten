"""Adapter-private Session binding for one verified ST-0308 transaction.

Repositories receive only a SQLAlchemy ``Session``.  This module binds the
already validated immutable command context and the transaction-owned Outbox
capability to that Session without widening any inward Repository protocol or
public factory signature.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import hashlib
from typing import Callable, Final, NoReturn, Protocol, TypeVar, cast
from uuid import RFC_4122, UUID

from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.shared import SqlAlchemyOutboxEventAppender
from raos.adapters.persistence.sqlalchemy.transaction import SqlAlchemyTransaction
from raos.domain.shared.events import (
    EVENT_BY_TYPE,
    EVENT_DESCRIPTORS,
    DomainEvent,
    require_allowed_event,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    PendingEventBuffer,
)
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from raos.ports.persistence.outbox import ValidatedOutboxEvent


_SESSION_RUNTIME_KEY: Final = "raos.st0308.private.session-runtime.v1"
RepositoryT = TypeVar("RepositoryT")


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


def _restore_acknowledged(buffer: PendingEventBuffer[DomainEvent]) -> None:
    restore = cast(
        Callable[[], None],
        getattr(buffer, "_restore_acknowledged"),
    )
    restore()


def aggregate_events_buffer(aggregate: object) -> PendingEventBuffer[DomainEvent]:
    """Resolve the approved ``_events`` aggregate seam and validate its type."""

    value = getattr(aggregate, "_events", None)
    if type(value) is not PendingEventBuffer:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return cast(PendingEventBuffer[DomainEvent], value)


def aggregate_event_buffer(aggregate: object) -> PendingEventBuffer[DomainEvent]:
    """Resolve the approved ``_event_buffer`` aggregate seam and validate it."""

    value = getattr(aggregate, "_event_buffer", None)
    if type(value) is not PendingEventBuffer:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return cast(PendingEventBuffer[DomainEvent], value)


class _TransactionRuntime(Protocol):
    active: bool
    context: PersistenceContext
    rollback_only: bool
    session: Session
    successful_dml_count: int
    timestamp: AwareUtcDateTime

    def acknowledge(self, buffer: PendingEventBuffer[DomainEvent]) -> None: ...

    def poison(self) -> None: ...

    def record_successful_dml(self) -> None: ...

    def require_active(self) -> None: ...


def _is_sqlalchemy_transaction(value: object) -> bool:
    return type(value) is SqlAlchemyTransaction


class _SqlAlchemySessionRuntime:
    """Exact mutable event-ID/staging seam owned by one outer UoW."""

    context: PersistenceContext
    outbox: SqlAlchemyOutboxEventAppender
    transaction: _TransactionRuntime

    __slots__ = (
        "_pending_buffers",
        "context",
        "outbox",
        "transaction",
    )

    def __init__(
        self,
        *,
        transaction: _TransactionRuntime,
        outbox: SqlAlchemyOutboxEventAppender,
    ) -> None:
        outbox_transaction = getattr(outbox, "_transaction", None)
        if (
            not _is_sqlalchemy_transaction(transaction)
            or type(outbox) is not SqlAlchemyOutboxEventAppender
            or outbox_transaction is not transaction
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self.transaction = transaction
        self.outbox = outbox
        self.context = transaction.context
        self._pending_buffers: dict[
            tuple[str, UUID], PendingEventBuffer[DomainEvent]
        ] = {}

    @property
    def successful_dml_count(self) -> int:
        return self.transaction.successful_dml_count

    def record_successful_dml(self) -> None:
        self.transaction.record_successful_dml()

    @property
    def timestamp(self) -> AwareUtcDateTime:
        self.transaction.require_active()
        return self.transaction.timestamp

    def deterministic_event_id(
        self,
        *,
        event_type: str,
        aggregate_id: UUID,
        aggregate_version: AggregateVersion,
    ) -> UUID:
        """Derive an idempotent RFC 9562 UUIDv7 from immutable command data."""

        self.transaction.require_active()
        if (
            type(event_type) is not str
            or not event_type
            or type(aggregate_id) is not UUID
            or type(aggregate_version) is not AggregateVersion
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        occurred_at = self.context.occurred_at
        milliseconds = int(occurred_at.timestamp() * 1000)
        if not 0 <= milliseconds < 1 << 48:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        material = b"\x00".join(
            (
                self.context.command_id.bytes,
                event_type.encode("utf-8"),
                aggregate_id.bytes,
                aggregate_version.value.to_bytes(8, "big"),
            )
        )
        entropy = int.from_bytes(hashlib.sha256(material).digest()[:10], "big")
        random_a = (entropy >> 68) & 0xFFF
        random_b = entropy & ((1 << 62) - 1)
        value = (
            (milliseconds << 80)
            | (0x7 << 76)
            | (random_a << 64)
            | (0b10 << 62)
            | random_b
        )
        event_id = UUID(int=value)
        if event_id.version != 7 or event_id.variant != RFC_4122:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return event_id

    def stage_pending_events(
        self,
        buffer: PendingEventBuffer[DomainEvent],
        *,
        owning_method: str | None = None,
        persisted_version: AggregateVersion | None = None,
        expected_event_type: str | None = None,
    ) -> None:
        self.transaction.require_active()
        if (
            type(buffer) is not PendingEventBuffer
            or (owning_method is not None and type(owning_method) is not str)
            or (
                persisted_version is not None
                and type(persisted_version) is not AggregateVersion
            )
            or (
                expected_event_type is not None
                and (
                    type(expected_event_type) is not str
                    or expected_event_type not in EVENT_BY_TYPE
                )
            )
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        events = buffer.pending_events()
        if not events:
            return
        if len(events) != 1:
            self.transaction.rollback_only = True
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        event = events[0]
        try:
            require_allowed_event(event)
            if (
                owning_method is not None
                and event.descriptor.owning_method != owning_method
            ):
                raise ValueError("EVENT_METHOD_MISMATCH")
            if (
                persisted_version is not None
                and event.aggregate_version != persisted_version
            ):
                raise ValueError("EVENT_VERSION_MISMATCH")
            if (
                expected_event_type is not None
                and event.descriptor.event_type != expected_event_type
            ):
                raise ValueError("EVENT_SPECIALIZATION_MISMATCH")
            self.outbox.append_many((ValidatedOutboxEvent(event),))
            event_ids = (event.event_id,)
            buffer.acknowledge_events(event_ids)
            self.transaction.acknowledge(buffer)
        except PersistenceError:
            self.transaction.rollback_only = True
            if not buffer.pending_events():
                _restore_acknowledged(buffer)
            raise
        except TypeError, ValueError:
            self.transaction.rollback_only = True
            if not buffer.pending_events():
                _restore_acknowledged(buffer)
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def register_pending_events(
        self,
        *,
        aggregate_type: str,
        aggregate_id: UUID,
        buffer: PendingEventBuffer[DomainEvent],
    ) -> None:
        self.transaction.require_active()
        allowed_types = {descriptor.aggregate_type for descriptor in EVENT_DESCRIPTORS}
        if (
            type(aggregate_type) is not str
            or aggregate_type not in allowed_types
            or type(aggregate_id) is not UUID
            or type(buffer) is not PendingEventBuffer
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        key = (aggregate_type, aggregate_id)
        current = self._pending_buffers.get(key)
        if current is not None and current is not buffer:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        self._pending_buffers[key] = buffer

    def stage_registered_events(
        self,
        *,
        aggregate_type: str,
        aggregate_id: UUID,
        owning_method: str,
        persisted_version: AggregateVersion,
        expected_event_type: str,
    ) -> None:
        self.transaction.require_active()
        buffer = self._pending_buffers.get((aggregate_type, aggregate_id))
        if buffer is None or not buffer.pending_events():
            self.transaction.rollback_only = True
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        events = buffer.pending_events()
        try:
            if len(events) != 1:
                raise ValueError("EVENT_COUNT_MISMATCH")
            event = require_allowed_event(events[0])
            if (
                event.descriptor.aggregate_type != aggregate_type
                or event.aggregate_id.value != aggregate_id
            ):
                raise ValueError("EVENT_ROOT_MISMATCH")
        except TypeError, ValueError:
            self.transaction.rollback_only = True
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self.stage_pending_events(
            buffer,
            owning_method=owning_method,
            persisted_version=persisted_version,
            expected_event_type=expected_event_type,
        )

    def require_no_unstaged_pending_events(self) -> None:
        self.transaction.require_active()
        if any(buffer.pending_events() for buffer in self._pending_buffers.values()):
            self.transaction.rollback_only = True
            _fail(PersistenceErrorCode.STATE_CONFLICT)


def bind_session_runtime(
    session: Session,
    *,
    transaction: SqlAlchemyTransaction,
    outbox: SqlAlchemyOutboxEventAppender,
) -> None:
    if (
        not isinstance(cast(object, session), Session)
        or _SESSION_RUNTIME_KEY in session.info
    ):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    session.info[_SESSION_RUNTIME_KEY] = _SqlAlchemySessionRuntime(
        transaction=transaction,
        outbox=outbox,
    )


def clear_session_runtime(session: Session) -> None:
    if not isinstance(cast(object, session), Session):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    session.info.pop(_SESSION_RUNTIME_KEY, None)


def require_session_runtime(session: Session) -> _SqlAlchemySessionRuntime:
    if not isinstance(cast(object, session), Session):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    value = session.info.get(_SESSION_RUNTIME_KEY)
    if type(value) is not _SqlAlchemySessionRuntime:
        _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
    value.transaction.require_active()
    if value.transaction.session is not session:
        _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
    return value


def fail_session_operation(
    session: Session,
    code: PersistenceErrorCode,
) -> NoReturn:
    """Poison one known-failed transaction and expose only its closed error code."""

    if type(code) is not PersistenceErrorCode:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    runtime = require_session_runtime(session)
    runtime.transaction.poison()
    _fail(code)


def record_successful_dml(session: Session) -> None:
    require_session_runtime(session).record_successful_dml()


def guard_repository_class(repository_type: type[RepositoryT]) -> type[RepositoryT]:
    """Poison a bound transaction when a repository fails after successful DML."""

    if type(repository_type) is not type:
        raise TypeError("INVALID_REPOSITORY_TYPE") from None

    def wrap(method: Callable[..., object]) -> Callable[..., object]:
        @wraps(method)
        def guarded(self: object, *args: object, **kwargs: object) -> object:
            session = getattr(self, "_session", None)
            runtime = (
                session.info.get(_SESSION_RUNTIME_KEY)
                if isinstance(session, Session)
                else None
            )
            before = (
                runtime.successful_dml_count
                if type(runtime) is _SqlAlchemySessionRuntime
                else None
            )
            try:
                return method(self, *args, **kwargs)
            except BaseException:
                if (
                    type(runtime) is _SqlAlchemySessionRuntime
                    and before is not None
                    and runtime.successful_dml_count > before
                    and runtime.transaction.active
                ):
                    runtime.transaction.poison()
                raise

        return guarded

    for name, candidate in tuple(vars(repository_type).items()):
        if name.startswith("_") or not callable(candidate):
            continue
        setattr(repository_type, name, wrap(candidate))
    return repository_type


def persistence_context(session: Session) -> PersistenceContext:
    return require_session_runtime(session).context


def transaction_timestamp(session: Session) -> AwareUtcDateTime:
    return require_session_runtime(session).timestamp


def deterministic_event_id(
    session: Session,
    *,
    event_type: str,
    aggregate_id: UUID,
    aggregate_version: AggregateVersion,
) -> UUID:
    return require_session_runtime(session).deterministic_event_id(
        event_type=event_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
    )


def stage_pending_events(
    session: Session,
    buffer: PendingEventBuffer[DomainEvent],
    *,
    owning_method: str,
    persisted_version: AggregateVersion,
    expected_event_type: str,
) -> None:
    require_session_runtime(session).stage_pending_events(
        buffer,
        owning_method=owning_method,
        persisted_version=persisted_version,
        expected_event_type=expected_event_type,
    )


def register_pending_events(
    session: Session,
    *,
    aggregate_type: str,
    aggregate_id: UUID,
    buffer: PendingEventBuffer[DomainEvent],
) -> None:
    require_session_runtime(session).register_pending_events(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        buffer=buffer,
    )


def stage_registered_events(
    session: Session,
    *,
    aggregate_type: str,
    aggregate_id: UUID,
    owning_method: str,
    persisted_version: AggregateVersion,
    expected_event_type: str,
) -> None:
    require_session_runtime(session).stage_registered_events(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        owning_method=owning_method,
        persisted_version=persisted_version,
        expected_event_type=expected_event_type,
    )


def require_no_unstaged_pending_events(session: Session) -> None:
    require_session_runtime(session).require_no_unstaged_pending_events()


def context_occurred_at(session: Session) -> datetime:
    value = persistence_context(session).occurred_at
    if value.tzinfo is not timezone.utc:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


__all__: list[str] = []
