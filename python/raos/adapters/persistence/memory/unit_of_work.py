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
    ExecutionPoint,
    ExecutionState,
    ExecutionStateFactory,
)
from raos.adapters.persistence.memory.identity import (
    EffectiveRoleVerifier,
    MemoryConnection,
    MemoryConnectionPool,
    MemorySession,
    MemorySessionFactory,
    WorkloadProfile,
    KnownMemoryCommitFailure,
    UnknownMemoryCommit,
    require_verified_identity,
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
    MemoryTransaction,
    Uuid7Factory,
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
    issue_transaction_join,
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


def _require_effective_role_verifier(value: object) -> EffectiveRoleVerifier:
    if not isinstance(value, EffectiveRoleVerifier):
        raise ValueError("INVALID_MEMORY_UOW_FACTORY") from None
    return value


class _JoinedTransactionCapability:
    """Narrow join bookkeeping; it exposes no owner or persistence state."""

    __slots__ = ("__transaction",)

    def __init__(self, transaction: MemoryTransaction) -> None:
        self.__transaction = transaction

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
        self.__transaction.execution_state.require_allowed(ExecutionPoint.PRE_FLUSH)

    def owns(self, transaction: MemoryTransaction) -> bool:
        return self.__transaction is transaction


@dataclass(frozen=True, slots=True)
class _JoinRegistration:
    transaction_scope: _JoinedTransactionCapability
    context_digest: str
    audit: MemoryAuditEventAppender
    outbox: MemoryOutboxEventAppender
    object_artifacts: MemoryObjectArtifactRepository
    runtime_settings: MemoryRuntimeSettingRepository


class _MemoryFactoryRuntime:
    """Adapter-private dependency owner shared by issued memory UoWs."""

    __slots__ = (
        "_clock",
        "_expected_profile",
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
        self._store = store
        self._pool = pool
        self._verifier = verifier
        self._session_factory = session_factory
        self._expected_profile = expected_profile
        self._clock = clock
        self._id_factory = id_factory
        self._owner_key = object()
        self._registry: dict[UUID, _JoinRegistration] = {}

    def idempotency_allowed(self) -> bool:
        return self._expected_profile is WorkloadProfile.API_COMMAND

    def checkout_connection(self) -> MemoryConnection:
        return self._pool.checkout()

    def verify_connection_identity(self, connection: MemoryConnection) -> None:
        proof = self._verifier.verify(connection, self._expected_profile)
        require_verified_identity(proof, connection, self._expected_profile)

    def create_session(self, connection: MemoryConnection) -> MemorySession:
        return self._session_factory.create(connection)

    def create_transaction(
        self,
        context: PersistenceContext,
        execution_state: ExecutionState,
    ) -> MemoryTransaction:
        revision, state = self._store.begin_transaction()
        return MemoryTransaction(
            transaction_id=_new_uuid7(self._id_factory),
            context=context,
            timestamp=transaction_timestamp(self._clock),
            base_revision=revision,
            state=state,
            store=self._store,
            id_factory=self._id_factory,
            execution_state=execution_state,
        )

    def commit_transaction(
        self,
        transaction: MemoryTransaction,
        commit_session: Callable[[], None],
    ) -> None:
        self._store.commit_transaction(
            transaction.transaction_id,
            tuple(sorted(transaction.claim_reservation_keys)),
            transaction.base_revision,
            transaction.state,
            commit_session,
        )

    def issue_join(self, transaction_id: UUID, context_digest: str) -> TransactionJoin:
        return issue_transaction_join(
            transaction_id=transaction_id,
            context_digest=context_digest,
            owner_key=self._owner_key,
        )

    def registration_for_join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> _JoinRegistration:
        try:
            transaction_id, digest = join_capability.adapter_fields(self._owner_key)
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
        return registration

    def register_transaction(
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

    def unregister_transaction(
        self,
        transaction_id: UUID,
        transaction: MemoryTransaction,
    ) -> None:
        registration = self._registry.get(transaction_id)
        if registration is not None and registration.transaction_scope.owns(
            transaction
        ):
            del self._registry[transaction_id]


class MemoryOpsUnitOfWork:
    """One explicit transaction owner; repositories appear only after enter."""

    __slots__ = (
        "_audit_appender",
        "_connection",
        "_context",
        "_entered",
        "_execution_state",
        "_runtime",
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
        runtime: _MemoryFactoryRuntime,
        context: PersistenceContext,
        execution_state: ExecutionState,
    ) -> None:
        if (
            type(runtime) is not _MemoryFactoryRuntime
            or type(context) is not PersistenceContext
            or type(execution_state) is not ExecutionState
        ):
            raise ValueError("INVALID_MEMORY_UOW") from None
        self._runtime = runtime
        self._context = context
        self._execution_state = execution_state
        self._state = TransactionState.NEW
        self._entered = False
        self._connection: MemoryConnection | None = None
        self._session: MemorySession | None = None
        self._transaction: MemoryTransaction | None = None
        self._audit_appender: MemoryAuditEventAppender | None = None
        self._outbox_appender: MemoryOutboxEventAppender | None = None
        self._idempotency_repository: MemoryIdempotencyRepository | None = None
        self._object_artifact_repository: MemoryObjectArtifactRepository | None = None
        self._runtime_setting_repository: MemoryRuntimeSettingRepository | None = None

    @property
    def context(self) -> PersistenceContext:
        return self._context

    def _active_transaction(self) -> MemoryTransaction:
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
            self._execution_state.require_allowed(ExecutionPoint.PRE_CHECKOUT)
        except PersistenceError:
            self._state = TransactionState.CLOSED
            raise
        try:
            connection = self._runtime.checkout_connection()
        except Exception:
            self._state = TransactionState.CLOSED
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self._connection = connection
        try:
            self._execution_state.require_allowed(ExecutionPoint.POST_CHECKOUT)
            self._runtime.verify_connection_identity(connection)
            self._execution_state.require_allowed(ExecutionPoint.POST_IDENTITY)
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
        transaction: MemoryTransaction | None = None
        registered = False
        try:
            session = self._runtime.create_session(connection)
            self._session = session
            self._execution_state.require_allowed(ExecutionPoint.PRE_SESSION_BEGIN)
            session.begin()
            transaction = self._runtime.create_transaction(
                self._context,
                self._execution_state,
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
            self._execution_state.require_allowed(ExecutionPoint.PRE_EXPOSURE)
            self._runtime.register_transaction(
                transaction.transaction_id,
                registration,
            )
            registered = True
        except Exception as error:
            if transaction is not None:
                if registered:
                    self._runtime.unregister_transaction(
                        transaction.transaction_id,
                        transaction,
                    )
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
        transaction: MemoryTransaction,
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
        self._runtime.unregister_transaction(transaction.transaction_id, transaction)
        if rollback_failed:
            self._close_transport(invalidate=True)
            self._entered = False
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def _finish_unknown(self, transaction: MemoryTransaction) -> None:
        try:
            transaction.finish_acknowledged()
            transaction.release_claim_reservations()
        except Exception:
            pass
        transaction.active = False
        self._state = TransactionState.UNKNOWN
        self._runtime.unregister_transaction(transaction.transaction_id, transaction)
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
        transaction.execution_state.require_allowed(ExecutionPoint.PRE_FLUSH)

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
            transaction.execution_state.require_allowed(ExecutionPoint.PRE_COMMIT)
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
            except KnownMemoryCommitFailure:
                driver_return_known = True
                raise
            driver_return_known = True

        try:
            self._runtime.commit_transaction(
                transaction,
                commit_session,
            )
        except UnknownMemoryCommit:
            self._finish_unknown(transaction)
            _fail(PersistenceErrorCode.UNKNOWN_COMMIT)
        except PersistenceError:
            if driver_return_known:
                transaction.execution_state.observe_known_driver_return()
            self._finish_known_rollback(transaction, rollback_session=True)
            raise
        except KnownMemoryCommitFailure:
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
        self._runtime.unregister_transaction(transaction.transaction_id, transaction)

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
        return self._runtime.issue_join(
            transaction.transaction_id,
            _context_digest(self._context),
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

    __slots__ = ("_execution_state_factory", "_runtime")

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
            or type(session_factory) is not MemorySessionFactory
            or type(expected_profile) is not WorkloadProfile
            or not callable(clock)
            or not callable(id_factory)
        ):
            raise ValueError("INVALID_MEMORY_UOW_FACTORY") from None
        self._execution_state_factory = ExecutionStateFactory()
        self._runtime = _MemoryFactoryRuntime(
            store=store,
            pool=pool,
            verifier=_require_effective_role_verifier(verifier),
            session_factory=session_factory,
            expected_profile=expected_profile,
            clock=clock,
            id_factory=id_factory,
        )

    def begin(self, context: PersistenceContext) -> MemoryOpsUnitOfWork:
        return MemoryOpsUnitOfWork(
            self._runtime,
            context,
            self._execution_state_factory.new_outer_state(),
        )

    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> MemoryIdempotentOpsUnitOfWork:
        if not self._runtime.idempotency_allowed():
            _fail(PersistenceErrorCode.IDENTITY_REJECTED)
        return MemoryIdempotentOpsUnitOfWork(
            self._runtime,
            context,
            self._execution_state_factory.new_outer_state(),
        )

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
        registration = self._runtime.registration_for_join(join_capability, context)
        return MemoryJoinedOpsUnitOfWork(registration, context)


__all__ = [
    "MemoryIdempotentOpsUnitOfWork",
    "MemoryJoinedOpsUnitOfWork",
    "MemoryOpsUnitOfWork",
    "MemoryOpsUnitOfWorkFactory",
]
