"""Outer, idempotent, and joined UoWs for the no-I/O OPS reference slice."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import hashlib
from types import TracebackType
from typing import Literal, NoReturn, Self
from uuid import RFC_4122, UUID

from raos.adapters.persistence.memory.execution import (
    _ExecutionPoint,
    _ExecutionStateFactory,
)
from raos.adapters.persistence.memory.identity import (
    EffectiveRoleVerifier,
    MemoryConnection,
    MemoryConnectionPool,
    MemorySession,
    MemorySessionFactory,
    WorkloadProfile,
    _KnownCommitFailure,
    _UnknownCommit,
    _require_verified_identity,
)
from raos.adapters.persistence.memory.repositories import (
    MemoryObjectArtifactRepository,
    MemoryRuntimeSettingRepository,
)
from raos.adapters.persistence.memory.shared import (
    MemoryAuditEventAppender,
    MemoryIdempotencyRepository,
    MemoryOutboxEventAppender,
)
from raos.adapters.persistence.memory.store import MemoryPersistenceStore
from raos.adapters.persistence.memory.transaction import (
    Uuid7Factory,
    _MemoryTransaction,
    transaction_timestamp,
)
from raos.domain.shared.events import DomainEvent
from raos.domain.shared.json_values import FrozenJsonObject, canonical_json_bytes
from raos.domain.shared.persistence import PendingEventBuffer
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from raos.ports.persistence.outbox import ValidatedOutboxEvent
from raos.ports.persistence.transaction import (
    TransactionJoin,
    TransactionState,
    _issue_transaction_join,
)


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


def _context_digest(context: PersistenceContext) -> str:
    material = FrozenJsonObject.from_mapping(
        {
            "actor_id": (
                None if context.actor.actor_id is None else str(context.actor.actor_id)
            ),
            "actor_type": context.actor.actor_type.value,
            "causation_id": (
                None if context.causation_id is None else str(context.causation_id)
            ),
            "command_id": str(context.command_id),
            "correlation_id": str(context.correlation_id),
            "occurred_at": context.occurred_at.isoformat(),
            "source": context.source,
        }
    )
    return hashlib.sha256(canonical_json_bytes(material)).hexdigest()


def _new_uuid7(factory: Uuid7Factory) -> UUID:
    value = factory()
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


@dataclass(frozen=True, slots=True)
class _JoinedTransactionCapability:
    """Narrow join bookkeeping; it exposes no owner or persistence state."""

    __transaction: _MemoryTransaction

    @property
    def transaction_id(self) -> UUID:
        return self.__transaction.transaction_id

    def require_active(self, transaction_id: UUID) -> None:
        if self.__transaction.transaction_id != transaction_id:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        self.__transaction.require_active()

    def enter(self, transaction_id: UUID) -> None:
        self.require_active(transaction_id)
        self.__transaction.joined_count += 1

    def exit(self, transaction_id: UUID, *, rollback_only: bool) -> None:
        self.require_active(transaction_id)
        if self.__transaction.joined_count < 1:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        if rollback_only:
            self.__transaction.rollback_only = True
        self.__transaction.joined_count -= 1

    def mark_rollback_only(self, transaction_id: UUID) -> None:
        self.require_active(transaction_id)
        self.__transaction.rollback_only = True

    def require_flush_allowed(self, transaction_id: UUID) -> None:
        self.require_active(transaction_id)
        self.__transaction.execution_state.require_allowed(_ExecutionPoint.PRE_FLUSH)

    def owns(self, transaction: _MemoryTransaction) -> bool:
        return self.__transaction is transaction


@dataclass(frozen=True, slots=True)
class _JoinRegistration:
    transaction_scope: _JoinedTransactionCapability
    context_digest: str
    audit: MemoryAuditEventAppender
    outbox: MemoryOutboxEventAppender
    object_artifacts: MemoryObjectArtifactRepository
    runtime_settings: MemoryRuntimeSettingRepository


class MemoryOpsUnitOfWork:
    """One explicit transaction owner; repositories appear only after enter."""

    __slots__ = (
        "_audit_appender",
        "_connection",
        "_context",
        "_entered",
        "_execution_state",
        "_factory",
        "_idempotency_repository",
        "_object_artifact_repository",
        "_outbox_appender",
        "_runtime_setting_repository",
        "_session",
        "_state",
        "_transaction",
    )

    def __init__(
        self,
        factory: MemoryOpsUnitOfWorkFactory,
        context: PersistenceContext,
    ) -> None:
        if type(context) is not PersistenceContext:
            raise ValueError("INVALID_MEMORY_UOW") from None
        self._factory = factory
        self._context = context
        self._execution_state = factory._execution_state_factory.new_outer_state()
        self._state = TransactionState.NEW
        self._entered = False
        self._connection: MemoryConnection | None = None
        self._session: MemorySession | None = None
        self._transaction: _MemoryTransaction | None = None
        self._audit_appender: MemoryAuditEventAppender | None = None
        self._outbox_appender: MemoryOutboxEventAppender | None = None
        self._idempotency_repository: MemoryIdempotencyRepository | None = None
        self._object_artifact_repository: MemoryObjectArtifactRepository | None = None
        self._runtime_setting_repository: MemoryRuntimeSettingRepository | None = None

    @property
    def context(self) -> PersistenceContext:
        return self._context

    def _active_transaction(self) -> _MemoryTransaction:
        transaction = self._transaction
        if (
            not self._entered
            or self._state is not TransactionState.ACTIVE
            or transaction is None
        ):
            _fail(PersistenceErrorCode.TRANSACTION_CLOSED)
        transaction.require_active()
        return transaction

    @property
    def audit(self) -> MemoryAuditEventAppender:
        self._active_transaction()
        value = self._audit_appender
        if value is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return value

    @property
    def outbox(self) -> MemoryOutboxEventAppender:
        self._active_transaction()
        value = self._outbox_appender
        if value is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return value

    @property
    def object_artifacts(self) -> MemoryObjectArtifactRepository:
        self._active_transaction()
        value = self._object_artifact_repository
        if value is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return value

    @property
    def runtime_settings(self) -> MemoryRuntimeSettingRepository:
        self._active_transaction()
        value = self._runtime_setting_repository
        if value is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return value

    def __enter__(self) -> Self:
        if self._entered or self._state is not TransactionState.NEW:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        try:
            self._execution_state.require_allowed(_ExecutionPoint.PRE_CHECKOUT)
        except PersistenceError:
            self._state = TransactionState.CLOSED
            raise
        try:
            connection = self._factory._pool.checkout()
        except Exception:
            self._state = TransactionState.CLOSED
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self._connection = connection
        try:
            self._execution_state.require_allowed(_ExecutionPoint.POST_CHECKOUT)
            proof = self._factory._verifier.verify(
                connection, self._factory._expected_profile
            )
            _require_verified_identity(
                proof, connection, self._factory._expected_profile
            )
            self._execution_state.require_allowed(_ExecutionPoint.POST_IDENTITY)
        except PersistenceError as error:
            if error.code in {
                PersistenceErrorCode.CANCELLED,
                PersistenceErrorCode.DEADLINE_EXCEEDED,
            }:
                connection.close()
                self._connection = None
                self._state = TransactionState.CLOSED
                raise error from None
            connection.invalidate()
            connection.close()
            self._connection = None
            self._state = TransactionState.CLOSED
            _fail(PersistenceErrorCode.IDENTITY_REJECTED)
        except Exception:
            connection.invalidate()
            connection.close()
            self._connection = None
            self._state = TransactionState.CLOSED
            _fail(PersistenceErrorCode.IDENTITY_REJECTED)
        session: MemorySession | None = None
        transaction: _MemoryTransaction | None = None
        registered = False
        try:
            session = self._factory._session_factory.create(connection)
            self._session = session
            self._execution_state.require_allowed(_ExecutionPoint.PRE_SESSION_BEGIN)
            session.begin()
            revision, state = self._factory._store._begin()
            timestamp = transaction_timestamp(self._factory._clock)
            transaction = _MemoryTransaction(
                transaction_id=_new_uuid7(self._factory._id_factory),
                context=self._context,
                timestamp=timestamp,
                base_revision=revision,
                state=state,
                store=self._factory._store,
                id_factory=self._factory._id_factory,
                execution_state=self._execution_state,
            )
            audit = MemoryAuditEventAppender(transaction)
            outbox = MemoryOutboxEventAppender(transaction)
            idempotency = MemoryIdempotencyRepository(transaction)
            object_artifacts = MemoryObjectArtifactRepository(transaction)
            runtime_settings = MemoryRuntimeSettingRepository(transaction)
            registration = _JoinRegistration(
                transaction_scope=_JoinedTransactionCapability(transaction),
                context_digest=_context_digest(self._context),
                audit=audit,
                outbox=outbox,
                object_artifacts=object_artifacts,
                runtime_settings=runtime_settings,
            )
            self._execution_state.require_allowed(_ExecutionPoint.PRE_EXPOSURE)
            self._factory._register(transaction.transaction_id, registration)
            registered = True
        except Exception as error:
            if transaction is not None:
                if registered:
                    self._factory._unregister(transaction.transaction_id, transaction)
                try:
                    transaction.release_claim_reservations()
                    transaction.restore_acknowledged()
                except Exception:
                    pass
                transaction.active = False
            if session is not None:
                try:
                    session.rollback()
                except Exception:
                    pass
                session.close()
            connection.invalidate()
            connection.close()
            self._connection = None
            self._session = None
            self._transaction = None
            self._audit_appender = None
            self._outbox_appender = None
            self._idempotency_repository = None
            self._object_artifact_repository = None
            self._runtime_setting_repository = None
            self._state = TransactionState.CLOSED
            if isinstance(error, PersistenceError):
                raise error from None
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self._transaction = transaction
        self._audit_appender = audit
        self._outbox_appender = outbox
        self._idempotency_repository = idempotency
        self._object_artifact_repository = object_artifacts
        self._runtime_setting_repository = runtime_settings
        self._entered = True
        self._state = TransactionState.ACTIVE
        return self

    def _close_transport(self, *, invalidate: bool = False) -> None:
        connection = self._connection
        session = self._session
        if invalidate and connection is not None:
            connection.invalidate()
        if session is not None:
            session.close()
        if connection is not None:
            connection.close()
        self._session = None
        self._connection = None

    def _finish_known_rollback(
        self,
        transaction: _MemoryTransaction,
        *,
        rollback_session: bool,
    ) -> None:
        session = self._session
        rollback_failed = False
        if rollback_session and session is not None:
            try:
                session.rollback()
            except Exception:
                rollback_failed = True
        try:
            transaction.release_claim_reservations()
            transaction.restore_acknowledged()
        except Exception:
            rollback_failed = True
        transaction.active = False
        self._state = TransactionState.ROLLED_BACK
        self._factory._unregister(transaction.transaction_id, transaction)
        if rollback_failed:
            self._close_transport(invalidate=True)
            self._entered = False
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def _finish_unknown(self, transaction: _MemoryTransaction) -> None:
        try:
            transaction.finish_acknowledged()
            transaction.release_claim_reservations()
        except Exception:
            pass
        transaction.active = False
        self._state = TransactionState.UNKNOWN
        self._factory._unregister(transaction.transaction_id, transaction)
        self._close_transport(invalidate=True)
        self._entered = False

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_value, traceback
        try:
            if self._state is TransactionState.ACTIVE:
                try:
                    self.rollback()
                except Exception:
                    if exc_type is None:
                        raise
        finally:
            self._close_transport()
            self._entered = False
            if self._state not in {
                TransactionState.COMMITTED,
                TransactionState.ROLLED_BACK,
                TransactionState.UNKNOWN,
            }:
                self._state = TransactionState.CLOSED
        return False

    def flush(self) -> None:
        transaction = self._active_transaction()
        transaction.execution_state.require_allowed(_ExecutionPoint.PRE_FLUSH)

    def mark_rollback_only(self) -> None:
        self._active_transaction().rollback_only = True

    def commit(self) -> None:
        transaction = self._active_transaction()
        if transaction.joined_count:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        if transaction.rollback_only:
            self.rollback()
            _fail(PersistenceErrorCode.TRANSACTION_ROLLBACK_ONLY)
        session = self._session
        if session is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        try:
            transaction.execution_state.require_allowed(_ExecutionPoint.PRE_COMMIT)
        except PersistenceError as error:
            if error.code in {
                PersistenceErrorCode.CANCELLED,
                PersistenceErrorCode.DEADLINE_EXCEEDED,
            }:
                self._finish_known_rollback(transaction, rollback_session=True)
            raise
        driver_return_known = False

        def commit_session() -> None:
            nonlocal driver_return_known
            try:
                session.commit()
            except _KnownCommitFailure:
                driver_return_known = True
                raise
            driver_return_known = True

        try:
            self._factory._store._commit_transaction(
                transaction.transaction_id,
                tuple(sorted(transaction.claim_reservation_keys)),
                transaction.base_revision,
                transaction.state,
                commit_session,
            )
        except _UnknownCommit:
            self._finish_unknown(transaction)
            _fail(PersistenceErrorCode.UNKNOWN_COMMIT)
        except PersistenceError:
            if driver_return_known:
                transaction.execution_state.observe_known_driver_return()
            self._finish_known_rollback(transaction, rollback_session=True)
            raise
        except _KnownCommitFailure:
            if driver_return_known:
                transaction.execution_state.observe_known_driver_return()
            self._finish_known_rollback(transaction, rollback_session=True)
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        except Exception:
            self._finish_unknown(transaction)
            _fail(PersistenceErrorCode.UNKNOWN_COMMIT)
        transaction.execution_state.observe_known_driver_return()
        transaction.claim_reservation_keys.clear()
        transaction.finish_acknowledged()
        transaction.active = False
        self._state = TransactionState.COMMITTED
        self._factory._unregister(transaction.transaction_id, transaction)

    def rollback(self) -> None:
        transaction = self._active_transaction()
        if transaction.joined_count:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        session = self._session
        if session is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self._finish_known_rollback(transaction, rollback_session=True)

    def join_token(self) -> TransactionJoin:
        transaction = self._active_transaction()
        return _issue_transaction_join(
            transaction_id=transaction.transaction_id,
            context_digest=_context_digest(self._context),
            owner_key=self._factory._owner_key,
        )

    def _stage_pending_events(
        self,
        buffer: PendingEventBuffer[DomainEvent],
    ) -> None:
        transaction = self._active_transaction()
        if type(buffer) is not PendingEventBuffer:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        events = buffer.pending_events()
        if not events:
            return
        self.outbox.append_many(tuple(ValidatedOutboxEvent(event) for event in events))
        try:
            buffer.acknowledge_events(tuple(event.event_id for event in events))
            transaction.acknowledge(buffer)
        except TypeError, ValueError:
            transaction.rollback_only = True
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


class MemoryIdempotentOpsUnitOfWork(MemoryOpsUnitOfWork):
    __slots__ = ()

    @property
    def idempotency(self) -> MemoryIdempotencyRepository:
        self._active_transaction()
        value = self._idempotency_repository
        if value is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return value


class MemoryJoinedOpsUnitOfWork:
    __slots__ = (
        "_audit",
        "_context",
        "_entered",
        "_object_artifacts",
        "_outbox",
        "_runtime_settings",
        "_transaction_scope",
        "_transaction_id",
    )

    def __init__(
        self,
        registration: _JoinRegistration,
        context: PersistenceContext,
    ) -> None:
        self._transaction_scope = registration.transaction_scope
        self._transaction_id = registration.transaction_scope.transaction_id
        self._context = context
        self._audit = registration.audit
        self._outbox = registration.outbox
        self._object_artifacts = registration.object_artifacts
        self._runtime_settings = registration.runtime_settings
        self._entered = False

    @property
    def context(self) -> PersistenceContext:
        return self._context

    def _require_active(self) -> None:
        if not self._entered:
            _fail(PersistenceErrorCode.TRANSACTION_CLOSED)
        self._transaction_scope.require_active(self._transaction_id)

    @property
    def audit(self) -> MemoryAuditEventAppender:
        self._require_active()
        return self._audit

    @property
    def outbox(self) -> MemoryOutboxEventAppender:
        self._require_active()
        return self._outbox

    @property
    def object_artifacts(self) -> MemoryObjectArtifactRepository:
        self._require_active()
        return self._object_artifacts

    @property
    def runtime_settings(self) -> MemoryRuntimeSettingRepository:
        self._require_active()
        return self._runtime_settings

    def __enter__(self) -> Self:
        if self._entered:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        self._transaction_scope.enter(self._transaction_id)
        self._entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_value, traceback
        if self._entered:
            self._transaction_scope.exit(
                self._transaction_id,
                rollback_only=exc_type is not None,
            )
            self._entered = False
        return False

    def flush(self) -> None:
        self._require_active()
        self._transaction_scope.require_flush_allowed(self._transaction_id)

    def mark_rollback_only(self) -> None:
        self._require_active()
        self._transaction_scope.mark_rollback_only(self._transaction_id)


class MemoryOpsUnitOfWorkFactory:
    """Factory owns workload profile; ``PersistenceContext`` never selects it."""

    __slots__ = (
        "_clock",
        "_expected_profile",
        "_execution_state_factory",
        "_id_factory",
        "_owner_key",
        "_pool",
        "_registry",
        "_session_factory",
        "_store",
        "_verifier",
    )

    def __init__(
        self,
        *,
        store: MemoryPersistenceStore,
        pool: MemoryConnectionPool,
        verifier: EffectiveRoleVerifier,
        session_factory: MemorySessionFactory,
        expected_profile: WorkloadProfile,
        clock: Callable[[], datetime],
        id_factory: Uuid7Factory,
    ) -> None:
        if (
            type(store) is not MemoryPersistenceStore
            or type(pool) is not MemoryConnectionPool
            or not isinstance(verifier, EffectiveRoleVerifier)
            or type(session_factory) is not MemorySessionFactory
            or type(expected_profile) is not WorkloadProfile
            or not callable(clock)
            or not callable(id_factory)
        ):
            raise ValueError("INVALID_MEMORY_UOW_FACTORY") from None
        self._store = store
        self._pool = pool
        self._verifier = verifier
        self._session_factory = session_factory
        self._expected_profile = expected_profile
        self._execution_state_factory = _ExecutionStateFactory()
        self._clock = clock
        self._id_factory = id_factory
        self._owner_key = object()
        self._registry: dict[UUID, _JoinRegistration] = {}

    def begin(self, context: PersistenceContext) -> MemoryOpsUnitOfWork:
        return MemoryOpsUnitOfWork(self, context)

    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> MemoryIdempotentOpsUnitOfWork:
        if self._expected_profile is not WorkloadProfile.API_COMMAND:
            _fail(PersistenceErrorCode.IDENTITY_REJECTED)
        return MemoryIdempotentOpsUnitOfWork(self, context)

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> MemoryJoinedOpsUnitOfWork:
        if (
            type(join_capability) is not TransactionJoin
            or type(context) is not PersistenceContext
        ):
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        try:
            transaction_id, digest = join_capability._adapter_fields(self._owner_key)
        except TypeError, ValueError:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        registration = self._registry.get(transaction_id)
        supplied_context_digest = _context_digest(context)
        if (
            registration is None
            or digest != registration.context_digest
            or supplied_context_digest != registration.context_digest
        ):
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        registration.transaction_scope.require_active(transaction_id)
        return MemoryJoinedOpsUnitOfWork(registration, context)

    def _register(
        self,
        transaction_id: UUID,
        registration: _JoinRegistration,
    ) -> None:
        if transaction_id in self._registry:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        if (
            type(registration) is not _JoinRegistration
            or registration.transaction_scope.transaction_id != transaction_id
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self._registry[transaction_id] = registration

    def _unregister(
        self,
        transaction_id: UUID,
        transaction: _MemoryTransaction,
    ) -> None:
        registration = self._registry.get(transaction_id)
        if registration is not None and registration.transaction_scope.owns(
            transaction
        ):
            del self._registry[transaction_id]


__all__ = [
    "MemoryIdempotentOpsUnitOfWork",
    "MemoryJoinedOpsUnitOfWork",
    "MemoryOpsUnitOfWork",
    "MemoryOpsUnitOfWorkFactory",
]
