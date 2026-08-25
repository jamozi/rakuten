"""Concrete outer, idempotent, and joined SQLAlchemy UoWs for ST-0308."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from types import MappingProxyType, TracebackType
from typing import TYPE_CHECKING, Literal, NoReturn, Self, cast
from uuid import UUID, uuid7

from sqlalchemy import event, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.sql.elements import TextClause

from raos.adapters.persistence.sqlalchemy.identity import WorkloadProfile
from raos.adapters.persistence.sqlalchemy.provider import (
    SqlAlchemyEngineProvider,
    VerifiedConnection,
    checkout_verified,
    close_checkout,
    create_session,
    invalidate_and_close,
)
from raos.adapters.persistence.sqlalchemy.repositories.ai import (
    SqlAlchemyAiJobRepository,
    SqlAlchemyAiTaskDefinitionRepository,
    SqlAlchemyEvaluationDatasetRepository,
    SqlAlchemyEvaluationResultRepository,
    SqlAlchemyEvaluationRunRepository,
    SqlAlchemyEvaluationSuiteRepository,
    SqlAlchemyJudgeCalibrationRepository,
    SqlAlchemyModelDefinitionRepository,
    SqlAlchemyModelRouteVersionRepository,
    SqlAlchemyOutputSchemaVersionRepository,
    SqlAlchemyPromptVersionRepository,
    SqlAlchemyReleaseDecisionRepository,
)
from raos.adapters.persistence.sqlalchemy.repositories.catalog import (
    SqlAlchemyAttributeDefinitionRepository,
    SqlAlchemyCanonicalProductRepository,
    SqlAlchemyGroupingDecisionRepository,
    SqlAlchemyIngestionRequestRepository,
    SqlAlchemyOfferRepository,
    SqlAlchemyProductCandidateRepository,
    SqlAlchemyProviderEndpointRepository,
    SqlAlchemyRakutenGenreRepository,
    SqlAlchemySafeOfferCurrentReader,
    SqlAlchemyShopRepository,
)
from raos.adapters.persistence.sqlalchemy.repositories.editorial import (
    SqlAlchemyArticlePlanRepository,
    SqlAlchemyArticleRepository,
    SqlAlchemyEditorialContractRepository,
    SqlAlchemyMediaAssetRepository,
    SqlAlchemyReviewCommentRepository,
)
from raos.adapters.persistence.sqlalchemy.repositories.evidence import (
    SqlAlchemyClaimRepository,
    SqlAlchemyFactRepository,
    SqlAlchemyFirstHandExperienceRepository,
    SqlAlchemySourcePacketRepository,
    SqlAlchemySourceRepository,
    SqlAlchemySourceSnapshotRepository,
)
from raos.adapters.persistence.sqlalchemy.repositories.iam import (
    SqlAlchemyBreakGlassRecordRepository,
    SqlAlchemyPrincipalRepository,
    SqlAlchemyPrincipalRoleAssignmentRepository,
    SqlAlchemyRoleCatalogRepository,
    SqlAlchemySessionRevocationRepository,
)
from raos.adapters.persistence.sqlalchemy.repositories.ops import (
    SqlAlchemyJobRepository,
    SqlAlchemyObjectArtifactRepository,
    SqlAlchemyRuntimeSettingRepository,
)
from raos.adapters.persistence.sqlalchemy.repositories.policy import (
    SqlAlchemyFindingRepository,
    SqlAlchemyGateDecisionRepository,
    SqlAlchemyPolicyBundleRepository,
    SqlAlchemyQualityCheckRunRepository,
    SqlAlchemyRuleVersionRepository,
    SqlAlchemyWaiverRepository,
)
from raos.adapters.persistence.sqlalchemy.repositories.portfolio import (
    SqlAlchemyActionCandidateRepository,
    SqlAlchemyCategoryRepository,
    SqlAlchemyIntentClusterRepository,
    SqlAlchemyKeywordRepository,
    SqlAlchemyOpportunityAssessmentRepository,
    SqlAlchemySiteRepository,
)
from raos.adapters.persistence.sqlalchemy.shared import (
    SqlAlchemyAuditEventAppender,
    SqlAlchemyIdempotencyRepository,
    SqlAlchemyOutboxEventAppender,
)
from raos.adapters.persistence.sqlalchemy.session_runtime import (
    bind_session_runtime,
    clear_session_runtime,
    record_successful_dml,
    require_no_unstaged_pending_events,
    require_session_runtime,
)
from raos.adapters.persistence.sqlalchemy.transaction import (
    ExecutionBudget,
    ExecutionPoint,
    ExecutionStateFactory,
    SqlAlchemyTransaction,
    require_uuid7,
)
import raos.ports.persistence.transaction as transaction_port
from raos.domain.shared.events import DomainEvent
from raos.domain.shared.json_values import FrozenJsonObject, canonical_json_bytes
from raos.domain.shared.persistence import AwareUtcDateTime, PendingEventBuffer
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from raos.ports.persistence.transaction import (
    TransactionJoin,
    TransactionState,
)


RepositoryConstructor = Callable[[Session], object]


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


def _issue_join(
    *,
    transaction_id: UUID,
    context_digest: str,
    owner_key: object,
) -> TransactionJoin:
    issuer = cast(
        Callable[..., TransactionJoin],
        getattr(transaction_port, "_issue_transaction_join"),
    )
    return issuer(
        transaction_id=transaction_id,
        context_digest=context_digest,
        owner_key=owner_key,
    )


def _join_fields(
    join_capability: TransactionJoin,
    owner_key: object,
) -> tuple[UUID, str]:
    fields = cast(
        Callable[[object], tuple[UUID, str]],
        getattr(join_capability, "_adapter_fields"),
    )
    return fields(owner_key)


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


def _transaction_timestamp(session: Session) -> AwareUtcDateTime:
    try:
        row = (
            session.execute(
                text("SELECT transaction_timestamp() AS transaction_timestamp")
            )
            .mappings()
            .one_or_none()
        )
    except DBAPIError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    except Exception:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if not isinstance(row, RowMapping):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    row_values = cast(Mapping[str, object], row)
    if frozenset(row_values) != frozenset({"transaction_timestamp"}):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    value = row_values["transaction_timestamp"]
    if (
        type(value) is not datetime
        or value.utcoffset() is None
        or value.utcoffset() != timezone.utc.utcoffset(value)
        or value.fold
    ):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    try:
        return AwareUtcDateTime(value.astimezone(timezone.utc))
    except TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _set_transaction_timezone_utc(session: Session) -> None:
    """Make every timestamptz value in this transaction decode as exact UTC."""

    try:
        session.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    except DBAPIError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    except Exception:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _is_mutating_statement(state: ORMExecuteState) -> bool:
    """Recognize both SQLAlchemy DML nodes and closed generated text DML."""

    if state.is_insert or state.is_update or state.is_delete:
        return True
    statement = state.statement
    if type(statement) is not TextClause:
        return False
    tokens = statement.text.lstrip().split(None, 1)
    return bool(tokens) and tokens[0].upper() in {"DELETE", "INSERT", "UPDATE"}


@dataclass(frozen=True, slots=True)
class _ModuleComposition:
    module: str
    repositories: Mapping[str, RepositoryConstructor]

    def __post_init__(self) -> None:
        repositories_candidate: object = self.repositories
        if type(repositories_candidate) is not MappingProxyType:
            raise ValueError("INVALID_SQLALCHEMY_MODULE_COMPOSITION") from None
        repositories = cast(
            Mapping[str, RepositoryConstructor],
            repositories_candidate,
        )
        if (
            type(self.module) is not str
            or self.module
            not in {
                "ops",
                "iam",
                "portfolio",
                "catalog",
                "evidence",
                "editorial",
                "ai",
                "policy",
            }
            or not repositories
            or any(
                type(name) is not str or not name or not callable(constructor)
                for name, constructor in repositories.items()
            )
        ):
            raise ValueError("INVALID_SQLALCHEMY_MODULE_COMPOSITION") from None


@dataclass(frozen=True, slots=True)
class _JoinedTransactionCapability:
    _transaction: SqlAlchemyTransaction

    @property
    def transaction_id(self) -> UUID:
        return self._transaction.transaction_id

    def require_active(self, transaction_id: UUID) -> None:
        if self._transaction.transaction_id != transaction_id:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        self._transaction.require_active()

    def enter(self, transaction_id: UUID) -> None:
        self.require_active(transaction_id)
        self._transaction.joined_count += 1

    def exit(self, transaction_id: UUID, *, rollback_only: bool) -> None:
        self.require_active(transaction_id)
        if self._transaction.joined_count < 1:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        if rollback_only:
            self._transaction.rollback_only = True
        self._transaction.joined_count -= 1

    def mark_rollback_only(self, transaction_id: UUID) -> None:
        self.require_active(transaction_id)
        self._transaction.rollback_only = True

    def require_flush_allowed(self, transaction_id: UUID) -> None:
        self.require_active(transaction_id)
        try:
            self._transaction.execution_state.require_allowed(ExecutionPoint.PRE_FLUSH)
            self._transaction.session.flush()
        except IntegrityError:
            self._transaction.poison()
            _fail(PersistenceErrorCode.INTEGRITY_CONFLICT)
        except DBAPIError:
            self._transaction.poison()
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        except PersistenceError as error:
            self._transaction.poison()
            raise error from None
        except Exception:
            self._transaction.poison()
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def owns(self, transaction: SqlAlchemyTransaction) -> bool:
        return self._transaction is transaction


@dataclass(frozen=True, slots=True)
class _JoinRegistration:
    transaction_scope: _JoinedTransactionCapability
    context_digest: str
    module: str
    audit: SqlAlchemyAuditEventAppender
    outbox: SqlAlchemyOutboxEventAppender
    repositories: Mapping[str, object]


class _SqlAlchemyOuterUnitOfWork:
    """One explicit transaction owner; concrete subclasses expose one module."""

    __slots__ = (
        "_audit_appender",
        "_checkout",
        "_context",
        "_entered",
        "_execution_state",
        "_factory",
        "_guard",
        "_idempotency_repository",
        "_outbox_appender",
        "_repositories",
        "_session",
        "_state",
        "_transaction",
    )

    def __init__(
        self,
        factory: _SqlAlchemyModuleFactory,
        context: PersistenceContext,
    ) -> None:
        if type(context) is not PersistenceContext:
            raise ValueError("INVALID_SQLALCHEMY_UOW") from None
        self._factory = factory
        self._context = context
        self._execution_state = _factory_execution_state_factory(
            factory
        ).new_outer_state()
        self._state = TransactionState.NEW
        self._entered = False
        self._checkout: VerifiedConnection | None = None
        self._session: Session | None = None
        self._transaction: SqlAlchemyTransaction | None = None
        self._audit_appender: SqlAlchemyAuditEventAppender | None = None
        self._outbox_appender: SqlAlchemyOutboxEventAppender | None = None
        self._idempotency_repository: SqlAlchemyIdempotencyRepository | None = None
        self._repositories: Mapping[str, object] | None = None
        self._guard: Callable[[ORMExecuteState], object] | None = None

    @property
    def context(self) -> PersistenceContext:
        return self._context

    def _active_transaction(self) -> SqlAlchemyTransaction:
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
    def audit(self) -> SqlAlchemyAuditEventAppender:
        self._active_transaction()
        value = self._audit_appender
        if value is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return value

    @property
    def outbox(self) -> SqlAlchemyOutboxEventAppender:
        self._active_transaction()
        value = self._outbox_appender
        if value is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return value

    def _repository(self, name: str) -> object:
        self._active_transaction()
        repositories = self._repositories
        if repositories is None or name not in repositories:
            _fail(PersistenceErrorCode.CROSS_MODULE_WRITE)
        return repositories[name]

    def __enter__(self) -> Self:
        if self._entered or self._state is not TransactionState.NEW:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        try:
            self._execution_state.require_allowed(ExecutionPoint.PRE_CHECKOUT)
        except PersistenceError:
            self._state = TransactionState.CLOSED
            raise
        checkout: VerifiedConnection | None = None
        session: Session | None = None
        transaction: SqlAlchemyTransaction | None = None
        try:
            provider = _factory_provider(self._factory)
            composition = _factory_composition(self._factory)
            checkout = checkout_verified(provider, self._execution_state)
            self._checkout = checkout
            session = create_session(provider, checkout)
            self._session = session
            self._execution_state.require_allowed(ExecutionPoint.PRE_SESSION_BEGIN)
            session.begin()
            _set_transaction_timezone_utc(session)
            timestamp = _transaction_timestamp(session)
            transaction = SqlAlchemyTransaction(
                transaction_id=require_uuid7(uuid7()),
                context=self._context,
                timestamp=timestamp,
                session=session,
                execution_state=self._execution_state,
            )
            audit = SqlAlchemyAuditEventAppender(transaction)
            outbox = SqlAlchemyOutboxEventAppender(transaction)
            idempotency = SqlAlchemyIdempotencyRepository(transaction)
            bind_session_runtime(
                session,
                transaction=transaction,
                outbox=outbox,
            )
            repositories = MappingProxyType(
                {
                    name: constructor(session)
                    for name, constructor in composition.repositories.items()
                }
            )
            registration = _JoinRegistration(
                transaction_scope=_JoinedTransactionCapability(transaction),
                context_digest=_context_digest(self._context),
                module=composition.module,
                audit=audit,
                outbox=outbox,
                repositories=repositories,
            )
            self._execution_state.require_allowed(ExecutionPoint.PRE_EXPOSURE)
            _factory_register(self._factory, transaction.transaction_id, registration)

            def guard(state: ORMExecuteState) -> object:
                """Own every Session.execute path, including repository bypasses."""

                try:
                    transaction.require_operation()
                    result = state.invoke_statement()
                    if _is_mutating_statement(state):
                        record_successful_dml(session)
                    return result
                except IntegrityError:
                    transaction.poison()
                    _fail(PersistenceErrorCode.INTEGRITY_CONFLICT)
                except DBAPIError:
                    transaction.poison()
                    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
                except PersistenceError as error:
                    transaction.poison()
                    raise error from None
                except Exception:
                    transaction.poison()
                    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

            event.listen(session, "do_orm_execute", guard, retval=True)
            self._guard = guard
        except Exception as error:
            if transaction is not None:
                self._discard_registration(transaction)
                try:
                    transaction.restore_acknowledged()
                except Exception:
                    pass
                transaction.active = False
            if session is not None:
                try:
                    clear_session_runtime(session)
                except Exception:
                    pass
                try:
                    session.rollback()
                except Exception:
                    pass
                try:
                    session.close()
                except Exception:
                    pass
            if checkout is not None:
                try:
                    invalidate_and_close(_factory_provider(self._factory), checkout)
                except Exception:
                    pass
            self._clear_runtime()
            self._state = TransactionState.CLOSED
            if isinstance(error, PersistenceError):
                raise error from None
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self._transaction = transaction
        self._audit_appender = audit
        self._outbox_appender = outbox
        self._idempotency_repository = idempotency
        self._repositories = repositories
        self._entered = True
        self._state = TransactionState.ACTIVE
        return self

    def _remove_guard(self) -> None:
        session = self._session
        guard = self._guard
        if session is not None and guard is not None:
            try:
                event.remove(session, "do_orm_execute", guard)
            except Exception:
                pass
        self._guard = None

    def _clear_runtime(self) -> None:
        self._remove_guard()
        self._checkout = None
        self._session = None
        self._transaction = None
        self._audit_appender = None
        self._outbox_appender = None
        self._idempotency_repository = None
        self._repositories = None
        self._entered = False

    def _close_transport(self, *, invalidate: bool = False) -> None:
        self._remove_guard()
        checkout = self._checkout
        session = self._session
        failed = False
        if session is not None:
            try:
                clear_session_runtime(session)
            except Exception:
                failed = True
            try:
                session.close()
            except Exception:
                failed = True
        if checkout is not None:
            try:
                if invalidate:
                    invalidate_and_close(_factory_provider(self._factory), checkout)
                else:
                    close_checkout(_factory_provider(self._factory), checkout)
            except Exception:
                failed = True
        self._checkout = None
        self._session = None
        if failed:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def _discard_registration(self, transaction: SqlAlchemyTransaction) -> bool:
        """Best-effort terminal registry cleanup; report any internal defect."""

        failed = False
        try:
            _factory_unregister(self._factory, transaction.transaction_id, transaction)
        except Exception:
            failed = True
        try:
            registry = _factory_registry(self._factory)
            registration = registry.get(transaction.transaction_id)
            if registration is not None:
                if registration.transaction_scope.owns(transaction):
                    del registry[transaction.transaction_id]
                else:
                    failed = True
        except Exception:
            failed = True
        return failed

    def _finish_known_rollback(
        self,
        transaction: SqlAlchemyTransaction,
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
            transaction.restore_acknowledged()
        except Exception:
            rollback_failed = True
        transaction.active = False
        self._state = TransactionState.ROLLED_BACK
        rollback_failed = self._discard_registration(transaction) or rollback_failed
        try:
            self._close_transport(invalidate=rollback_failed)
        except PersistenceError:
            rollback_failed = True
        finally:
            self._clear_runtime()
        if rollback_failed:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def _finish_unknown(self, transaction: SqlAlchemyTransaction) -> None:
        try:
            transaction.finish_acknowledged()
        except Exception:
            pass
        transaction.active = False
        self._state = TransactionState.UNKNOWN
        self._discard_registration(transaction)
        try:
            self._close_transport(invalidate=True)
        except PersistenceError:
            pass
        self._clear_runtime()

    def _finish_known_commit(self, transaction: SqlAlchemyTransaction) -> None:
        """Finalize a driver-confirmed commit without ever reclassifying it unknown."""

        terminal_failed = False
        transaction.active = False
        self._state = TransactionState.COMMITTED
        try:
            transaction.execution_state.observe_known_driver_return()
        except Exception:
            terminal_failed = True
        try:
            transaction.finish_acknowledged()
        except Exception:
            terminal_failed = True
            transaction.acknowledged_buffers.clear()
        if self._discard_registration(transaction):
            terminal_failed = True
        try:
            self._close_transport()
        except PersistenceError:
            terminal_failed = True
        finally:
            self._clear_runtime()
        if terminal_failed:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

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
            try:
                self._close_transport()
            finally:
                self._clear_runtime()
                if self._state not in {
                    TransactionState.COMMITTED,
                    TransactionState.ROLLED_BACK,
                    TransactionState.UNKNOWN,
                }:
                    self._state = TransactionState.CLOSED
        return False

    def flush(self) -> None:
        transaction = self._active_transaction()
        session = self._session
        if session is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        try:
            transaction.execution_state.require_allowed(ExecutionPoint.PRE_FLUSH)
            session.flush()
        except IntegrityError:
            transaction.poison()
            _fail(PersistenceErrorCode.INTEGRITY_CONFLICT)
        except DBAPIError:
            transaction.poison()
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        except PersistenceError as error:
            transaction.poison()
            raise error from None
        except Exception:
            transaction.poison()
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

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
            require_no_unstaged_pending_events(session)
            transaction.execution_state.require_allowed(ExecutionPoint.PRE_COMMIT)
        except PersistenceError as error:
            if error.code in {
                PersistenceErrorCode.CANCELLED,
                PersistenceErrorCode.DEADLINE_EXCEEDED,
                PersistenceErrorCode.STATE_CONFLICT,
            }:
                self._finish_known_rollback(transaction, rollback_session=True)
            raise
        try:
            session.commit()
        except DBAPIError as error:
            if error.connection_invalidated:
                self._finish_unknown(transaction)
                _fail(PersistenceErrorCode.UNKNOWN_COMMIT)
            try:
                transaction.execution_state.observe_known_driver_return()
            except Exception:
                # The driver already reported a definite failure.  Housekeeping
                # faults must not leak or reclassify that outcome as unknown.
                pass
            self._finish_known_rollback(transaction, rollback_session=True)
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        except Exception:
            self._finish_unknown(transaction)
            _fail(PersistenceErrorCode.UNKNOWN_COMMIT)
        self._finish_known_commit(transaction)

    def rollback(self) -> None:
        transaction = self._active_transaction()
        if transaction.joined_count:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        if self._session is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self._finish_known_rollback(transaction, rollback_session=True)

    def join_token(self) -> TransactionJoin:
        transaction = self._active_transaction()
        return _issue_join(
            transaction_id=transaction.transaction_id,
            context_digest=_context_digest(self._context),
            owner_key=_factory_owner_key(self._factory),
        )

    def _stage_pending_events(
        self,
        buffer: PendingEventBuffer[DomainEvent],
    ) -> None:
        self._active_transaction()
        session = self._session
        if session is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        require_session_runtime(session).stage_pending_events(buffer)


class _SqlAlchemyIdempotentOuterUnitOfWork(_SqlAlchemyOuterUnitOfWork):
    __slots__ = ()

    @property
    def idempotency(self) -> SqlAlchemyIdempotencyRepository:
        self._active_transaction()
        value = self._idempotency_repository
        if value is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return value


class _SqlAlchemyJoinedUnitOfWork:
    __slots__ = (
        "_audit",
        "_context",
        "_entered",
        "_outbox",
        "_repositories",
        "_transaction_id",
        "_transaction_scope",
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
        self._repositories = registration.repositories
        self._entered = False

    @property
    def context(self) -> PersistenceContext:
        return self._context

    def _require_active(self) -> None:
        if not self._entered:
            _fail(PersistenceErrorCode.TRANSACTION_CLOSED)
        self._transaction_scope.require_active(self._transaction_id)

    @property
    def audit(self) -> SqlAlchemyAuditEventAppender:
        self._require_active()
        return self._audit

    @property
    def outbox(self) -> SqlAlchemyOutboxEventAppender:
        self._require_active()
        return self._outbox

    def _repository(self, name: str) -> object:
        self._require_active()
        if name not in self._repositories:
            _fail(PersistenceErrorCode.CROSS_MODULE_WRITE)
        return self._repositories[name]

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


class _SqlAlchemyModuleFactory:
    __slots__ = (
        "_composition",
        "_execution_state_factory",
        "_owner_key",
        "_provider",
        "_registry",
    )

    _composition_definition: _ModuleComposition
    _outer_type: type[_SqlAlchemyOuterUnitOfWork]
    _idempotent_type: type[_SqlAlchemyIdempotentOuterUnitOfWork]
    _joined_type: type[_SqlAlchemyJoinedUnitOfWork]
    _requires_api_profile: bool = False

    def __init__(
        self,
        provider: SqlAlchemyEngineProvider,
        *,
        timeout_ns: int | None = None,
    ) -> None:
        if not isinstance(cast(object, provider), SqlAlchemyEngineProvider):
            raise ValueError("INVALID_SQLALCHEMY_UOW_FACTORY") from None
        if (
            self._requires_api_profile
            and provider.expected_profile is not WorkloadProfile.API_COMMAND
        ):
            _fail(PersistenceErrorCode.IDENTITY_REJECTED)
        self._provider = provider
        self._composition = self._composition_definition
        self._execution_state_factory = ExecutionStateFactory(
            ExecutionBudget(timeout_ns)
        )
        self._owner_key = object()
        self._registry: dict[UUID, _JoinRegistration] = {}

    def _begin(self, context: PersistenceContext) -> _SqlAlchemyOuterUnitOfWork:
        return self._outer_type(self, context)

    def _begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> _SqlAlchemyIdempotentOuterUnitOfWork:
        if self._provider.expected_profile is not WorkloadProfile.API_COMMAND:
            _fail(PersistenceErrorCode.IDENTITY_REJECTED)
        return self._idempotent_type(self, context)

    def _join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> _SqlAlchemyJoinedUnitOfWork:
        if (
            type(join_capability) is not TransactionJoin
            or type(context) is not PersistenceContext
        ):
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        try:
            transaction_id, digest = _join_fields(join_capability, self._owner_key)
        except TypeError, ValueError:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        registration = self._registry.get(transaction_id)
        supplied_digest = _context_digest(context)
        if (
            registration is None
            or registration.module != self._composition.module
            or digest != registration.context_digest
            or supplied_digest != registration.context_digest
        ):
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        registration.transaction_scope.require_active(transaction_id)
        return self._joined_type(registration, context)

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
            or registration.module != self._composition.module
            or frozenset(registration.repositories)
            != frozenset(self._composition.repositories)
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self._registry[transaction_id] = registration

    def _unregister(
        self,
        transaction_id: UUID,
        transaction: SqlAlchemyTransaction,
    ) -> None:
        registration = self._registry.get(transaction_id)
        if registration is not None and registration.transaction_scope.owns(
            transaction
        ):
            del self._registry[transaction_id]


def _factory_provider(
    factory: _SqlAlchemyModuleFactory,
) -> SqlAlchemyEngineProvider:
    value = getattr(factory, "_provider", None)
    if not isinstance(value, SqlAlchemyEngineProvider):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _factory_composition(factory: _SqlAlchemyModuleFactory) -> _ModuleComposition:
    value = getattr(factory, "_composition", None)
    if type(value) is not _ModuleComposition:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _factory_execution_state_factory(
    factory: _SqlAlchemyModuleFactory,
) -> ExecutionStateFactory:
    value = getattr(factory, "_execution_state_factory", None)
    if type(value) is not ExecutionStateFactory:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _factory_owner_key(factory: _SqlAlchemyModuleFactory) -> object:
    value = getattr(factory, "_owner_key", None)
    if value is None:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _factory_registry(
    factory: _SqlAlchemyModuleFactory,
) -> dict[UUID, _JoinRegistration]:
    value = getattr(factory, "_registry", None)
    if type(value) is not dict:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return cast(dict[UUID, _JoinRegistration], value)


def _factory_register(
    factory: _SqlAlchemyModuleFactory,
    transaction_id: UUID,
    registration: _JoinRegistration,
) -> None:
    method = cast(
        Callable[[UUID, _JoinRegistration], None],
        getattr(factory, "_register"),
    )
    method(transaction_id, registration)


def _factory_unregister(
    factory: _SqlAlchemyModuleFactory,
    transaction_id: UUID,
    transaction: SqlAlchemyTransaction,
) -> None:
    method = cast(
        Callable[[UUID, SqlAlchemyTransaction], None],
        getattr(factory, "_unregister"),
    )
    method(transaction_id, transaction)


def _composition(
    module: str,
    repositories: dict[str, RepositoryConstructor],
) -> _ModuleComposition:
    return _ModuleComposition(module, MappingProxyType(repositories))


class _RepositoryProperties:
    if TYPE_CHECKING:

        def _repository(self, name: str) -> object: ...


class _OpsRepositories(_RepositoryProperties):
    @property
    def jobs(self) -> SqlAlchemyJobRepository:
        return cast(SqlAlchemyJobRepository, self._repository("jobs"))

    @property
    def object_artifacts(self) -> SqlAlchemyObjectArtifactRepository:
        return cast(
            SqlAlchemyObjectArtifactRepository,
            self._repository("object_artifacts"),
        )

    @property
    def runtime_settings(self) -> SqlAlchemyRuntimeSettingRepository:
        return cast(
            SqlAlchemyRuntimeSettingRepository,
            self._repository("runtime_settings"),
        )


class SqlAlchemyOpsUnitOfWork(_OpsRepositories, _SqlAlchemyOuterUnitOfWork):
    __slots__ = ()


class SqlAlchemyIdempotentOpsUnitOfWork(
    _OpsRepositories,
    _SqlAlchemyIdempotentOuterUnitOfWork,
):
    __slots__ = ()


class SqlAlchemyJoinedOpsUnitOfWork(
    _OpsRepositories,
    _SqlAlchemyJoinedUnitOfWork,
):
    __slots__ = ()


_OPS_COMPOSITION = _composition(
    "ops",
    {
        "jobs": SqlAlchemyJobRepository,
        "object_artifacts": SqlAlchemyObjectArtifactRepository,
        "runtime_settings": SqlAlchemyRuntimeSettingRepository,
    },
)


class SqlAlchemyOpsUnitOfWorkFactory(_SqlAlchemyModuleFactory):
    __slots__ = ()
    _composition_definition = _OPS_COMPOSITION
    _outer_type = SqlAlchemyOpsUnitOfWork
    _idempotent_type = SqlAlchemyIdempotentOpsUnitOfWork
    _joined_type = SqlAlchemyJoinedOpsUnitOfWork

    def begin(self, context: PersistenceContext) -> SqlAlchemyOpsUnitOfWork:
        return cast(SqlAlchemyOpsUnitOfWork, self._begin(context))

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> SqlAlchemyJoinedOpsUnitOfWork:
        return cast(
            SqlAlchemyJoinedOpsUnitOfWork,
            self._join(join_capability, context),
        )


class SqlAlchemyIdempotentOpsUnitOfWorkFactory(
    SqlAlchemyOpsUnitOfWorkFactory,
):
    __slots__ = ()
    _requires_api_profile = True

    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> SqlAlchemyIdempotentOpsUnitOfWork:
        return cast(
            SqlAlchemyIdempotentOpsUnitOfWork,
            self._begin_idempotent(context),
        )


class _IamRepositories(_RepositoryProperties):
    @property
    def principals(self) -> SqlAlchemyPrincipalRepository:
        return cast(SqlAlchemyPrincipalRepository, self._repository("principals"))

    @property
    def role_catalog(self) -> SqlAlchemyRoleCatalogRepository:
        return cast(
            SqlAlchemyRoleCatalogRepository,
            self._repository("role_catalog"),
        )

    @property
    def role_assignments(self) -> SqlAlchemyPrincipalRoleAssignmentRepository:
        return cast(
            SqlAlchemyPrincipalRoleAssignmentRepository,
            self._repository("role_assignments"),
        )

    @property
    def session_revocations(self) -> SqlAlchemySessionRevocationRepository:
        return cast(
            SqlAlchemySessionRevocationRepository,
            self._repository("session_revocations"),
        )

    @property
    def break_glass_records(self) -> SqlAlchemyBreakGlassRecordRepository:
        return cast(
            SqlAlchemyBreakGlassRecordRepository,
            self._repository("break_glass_records"),
        )


class SqlAlchemyIamUnitOfWork(_IamRepositories, _SqlAlchemyOuterUnitOfWork):
    __slots__ = ()


class SqlAlchemyIdempotentIamUnitOfWork(
    _IamRepositories,
    _SqlAlchemyIdempotentOuterUnitOfWork,
):
    __slots__ = ()


class SqlAlchemyJoinedIamUnitOfWork(
    _IamRepositories,
    _SqlAlchemyJoinedUnitOfWork,
):
    __slots__ = ()


_IAM_COMPOSITION = _composition(
    "iam",
    {
        "principals": SqlAlchemyPrincipalRepository,
        "role_catalog": SqlAlchemyRoleCatalogRepository,
        "role_assignments": SqlAlchemyPrincipalRoleAssignmentRepository,
        "session_revocations": SqlAlchemySessionRevocationRepository,
        "break_glass_records": SqlAlchemyBreakGlassRecordRepository,
    },
)


class SqlAlchemyIamUnitOfWorkFactory(_SqlAlchemyModuleFactory):
    __slots__ = ()
    _composition_definition = _IAM_COMPOSITION
    _outer_type = SqlAlchemyIamUnitOfWork
    _idempotent_type = SqlAlchemyIdempotentIamUnitOfWork
    _joined_type = SqlAlchemyJoinedIamUnitOfWork
    _requires_api_profile = True

    def begin(self, context: PersistenceContext) -> SqlAlchemyIamUnitOfWork:
        return cast(SqlAlchemyIamUnitOfWork, self._begin(context))

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> SqlAlchemyJoinedIamUnitOfWork:
        return cast(
            SqlAlchemyJoinedIamUnitOfWork,
            self._join(join_capability, context),
        )


class SqlAlchemyIdempotentIamUnitOfWorkFactory(
    SqlAlchemyIamUnitOfWorkFactory,
):
    __slots__ = ()

    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> SqlAlchemyIdempotentIamUnitOfWork:
        return cast(
            SqlAlchemyIdempotentIamUnitOfWork,
            self._begin_idempotent(context),
        )


class _PortfolioRepositories(_RepositoryProperties):
    @property
    def sites(self) -> SqlAlchemySiteRepository:
        return cast(SqlAlchemySiteRepository, self._repository("sites"))

    @property
    def categories(self) -> SqlAlchemyCategoryRepository:
        return cast(SqlAlchemyCategoryRepository, self._repository("categories"))

    @property
    def intent_clusters(self) -> SqlAlchemyIntentClusterRepository:
        return cast(
            SqlAlchemyIntentClusterRepository,
            self._repository("intent_clusters"),
        )

    @property
    def keywords(self) -> SqlAlchemyKeywordRepository:
        return cast(SqlAlchemyKeywordRepository, self._repository("keywords"))

    @property
    def opportunity_assessments(
        self,
    ) -> SqlAlchemyOpportunityAssessmentRepository:
        return cast(
            SqlAlchemyOpportunityAssessmentRepository,
            self._repository("opportunity_assessments"),
        )

    @property
    def action_candidates(self) -> SqlAlchemyActionCandidateRepository:
        return cast(
            SqlAlchemyActionCandidateRepository,
            self._repository("action_candidates"),
        )


class SqlAlchemyPortfolioUnitOfWork(
    _PortfolioRepositories,
    _SqlAlchemyOuterUnitOfWork,
):
    __slots__ = ()


class SqlAlchemyIdempotentPortfolioUnitOfWork(
    _PortfolioRepositories,
    _SqlAlchemyIdempotentOuterUnitOfWork,
):
    __slots__ = ()


class SqlAlchemyJoinedPortfolioUnitOfWork(
    _PortfolioRepositories,
    _SqlAlchemyJoinedUnitOfWork,
):
    __slots__ = ()


_PORTFOLIO_COMPOSITION = _composition(
    "portfolio",
    {
        "sites": SqlAlchemySiteRepository,
        "categories": SqlAlchemyCategoryRepository,
        "intent_clusters": SqlAlchemyIntentClusterRepository,
        "keywords": SqlAlchemyKeywordRepository,
        "opportunity_assessments": SqlAlchemyOpportunityAssessmentRepository,
        "action_candidates": SqlAlchemyActionCandidateRepository,
    },
)


class SqlAlchemyPortfolioUnitOfWorkFactory(_SqlAlchemyModuleFactory):
    __slots__ = ()
    _composition_definition = _PORTFOLIO_COMPOSITION
    _outer_type = SqlAlchemyPortfolioUnitOfWork
    _idempotent_type = SqlAlchemyIdempotentPortfolioUnitOfWork
    _joined_type = SqlAlchemyJoinedPortfolioUnitOfWork

    def begin(self, context: PersistenceContext) -> SqlAlchemyPortfolioUnitOfWork:
        return cast(SqlAlchemyPortfolioUnitOfWork, self._begin(context))

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> SqlAlchemyJoinedPortfolioUnitOfWork:
        return cast(
            SqlAlchemyJoinedPortfolioUnitOfWork,
            self._join(join_capability, context),
        )


class SqlAlchemyIdempotentPortfolioUnitOfWorkFactory(
    SqlAlchemyPortfolioUnitOfWorkFactory,
):
    __slots__ = ()
    _requires_api_profile = True

    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> SqlAlchemyIdempotentPortfolioUnitOfWork:
        return cast(
            SqlAlchemyIdempotentPortfolioUnitOfWork,
            self._begin_idempotent(context),
        )


class _CatalogRepositories(_RepositoryProperties):
    @property
    def provider_endpoints(self) -> SqlAlchemyProviderEndpointRepository:
        return cast(
            SqlAlchemyProviderEndpointRepository,
            self._repository("provider_endpoints"),
        )

    @property
    def ingestion_requests(self) -> SqlAlchemyIngestionRequestRepository:
        return cast(
            SqlAlchemyIngestionRequestRepository,
            self._repository("ingestion_requests"),
        )

    @property
    def rakuten_genres(self) -> SqlAlchemyRakutenGenreRepository:
        return cast(
            SqlAlchemyRakutenGenreRepository,
            self._repository("rakuten_genres"),
        )

    @property
    def shops(self) -> SqlAlchemyShopRepository:
        return cast(SqlAlchemyShopRepository, self._repository("shops"))

    @property
    def canonical_products(self) -> SqlAlchemyCanonicalProductRepository:
        return cast(
            SqlAlchemyCanonicalProductRepository,
            self._repository("canonical_products"),
        )

    @property
    def product_candidates(self) -> SqlAlchemyProductCandidateRepository:
        return cast(
            SqlAlchemyProductCandidateRepository,
            self._repository("product_candidates"),
        )

    @property
    def grouping_decisions(self) -> SqlAlchemyGroupingDecisionRepository:
        return cast(
            SqlAlchemyGroupingDecisionRepository,
            self._repository("grouping_decisions"),
        )

    @property
    def attribute_definitions(self) -> SqlAlchemyAttributeDefinitionRepository:
        return cast(
            SqlAlchemyAttributeDefinitionRepository,
            self._repository("attribute_definitions"),
        )

    @property
    def offers(self) -> SqlAlchemyOfferRepository:
        return cast(SqlAlchemyOfferRepository, self._repository("offers"))

    @property
    def safe_offer_current(self) -> SqlAlchemySafeOfferCurrentReader:
        return cast(
            SqlAlchemySafeOfferCurrentReader,
            self._repository("safe_offer_current"),
        )


class SqlAlchemyCatalogUnitOfWork(
    _CatalogRepositories,
    _SqlAlchemyOuterUnitOfWork,
):
    __slots__ = ()


class SqlAlchemyIdempotentCatalogUnitOfWork(
    _CatalogRepositories,
    _SqlAlchemyIdempotentOuterUnitOfWork,
):
    __slots__ = ()


class SqlAlchemyJoinedCatalogUnitOfWork(
    _CatalogRepositories,
    _SqlAlchemyJoinedUnitOfWork,
):
    __slots__ = ()


_CATALOG_COMPOSITION = _composition(
    "catalog",
    {
        "provider_endpoints": SqlAlchemyProviderEndpointRepository,
        "ingestion_requests": SqlAlchemyIngestionRequestRepository,
        "rakuten_genres": SqlAlchemyRakutenGenreRepository,
        "shops": SqlAlchemyShopRepository,
        "canonical_products": SqlAlchemyCanonicalProductRepository,
        "product_candidates": SqlAlchemyProductCandidateRepository,
        "grouping_decisions": SqlAlchemyGroupingDecisionRepository,
        "attribute_definitions": SqlAlchemyAttributeDefinitionRepository,
        "offers": SqlAlchemyOfferRepository,
        "safe_offer_current": SqlAlchemySafeOfferCurrentReader,
    },
)


class SqlAlchemyCatalogUnitOfWorkFactory(_SqlAlchemyModuleFactory):
    __slots__ = ()
    _composition_definition = _CATALOG_COMPOSITION
    _outer_type = SqlAlchemyCatalogUnitOfWork
    _idempotent_type = SqlAlchemyIdempotentCatalogUnitOfWork
    _joined_type = SqlAlchemyJoinedCatalogUnitOfWork

    def begin(self, context: PersistenceContext) -> SqlAlchemyCatalogUnitOfWork:
        return cast(SqlAlchemyCatalogUnitOfWork, self._begin(context))

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> SqlAlchemyJoinedCatalogUnitOfWork:
        return cast(
            SqlAlchemyJoinedCatalogUnitOfWork,
            self._join(join_capability, context),
        )


class SqlAlchemyIdempotentCatalogUnitOfWorkFactory(
    SqlAlchemyCatalogUnitOfWorkFactory,
):
    __slots__ = ()
    _requires_api_profile = True

    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> SqlAlchemyIdempotentCatalogUnitOfWork:
        return cast(
            SqlAlchemyIdempotentCatalogUnitOfWork,
            self._begin_idempotent(context),
        )


class _EvidenceRepositories(_RepositoryProperties):
    @property
    def sources(self) -> SqlAlchemySourceRepository:
        return cast(SqlAlchemySourceRepository, self._repository("sources"))

    @property
    def source_snapshots(self) -> SqlAlchemySourceSnapshotRepository:
        return cast(
            SqlAlchemySourceSnapshotRepository,
            self._repository("source_snapshots"),
        )

    @property
    def facts(self) -> SqlAlchemyFactRepository:
        return cast(SqlAlchemyFactRepository, self._repository("facts"))

    @property
    def source_packets(self) -> SqlAlchemySourcePacketRepository:
        return cast(
            SqlAlchemySourcePacketRepository,
            self._repository("source_packets"),
        )

    @property
    def claims(self) -> SqlAlchemyClaimRepository:
        return cast(SqlAlchemyClaimRepository, self._repository("claims"))

    @property
    def first_hand_experiences(
        self,
    ) -> SqlAlchemyFirstHandExperienceRepository:
        return cast(
            SqlAlchemyFirstHandExperienceRepository,
            self._repository("first_hand_experiences"),
        )


class SqlAlchemyEvidenceUnitOfWork(
    _EvidenceRepositories,
    _SqlAlchemyOuterUnitOfWork,
):
    __slots__ = ()


class SqlAlchemyIdempotentEvidenceUnitOfWork(
    _EvidenceRepositories,
    _SqlAlchemyIdempotentOuterUnitOfWork,
):
    __slots__ = ()


class SqlAlchemyJoinedEvidenceUnitOfWork(
    _EvidenceRepositories,
    _SqlAlchemyJoinedUnitOfWork,
):
    __slots__ = ()


_EVIDENCE_COMPOSITION = _composition(
    "evidence",
    {
        "sources": SqlAlchemySourceRepository,
        "source_snapshots": SqlAlchemySourceSnapshotRepository,
        "facts": SqlAlchemyFactRepository,
        "source_packets": SqlAlchemySourcePacketRepository,
        "claims": SqlAlchemyClaimRepository,
        "first_hand_experiences": SqlAlchemyFirstHandExperienceRepository,
    },
)


class SqlAlchemyEvidenceUnitOfWorkFactory(_SqlAlchemyModuleFactory):
    __slots__ = ()
    _composition_definition = _EVIDENCE_COMPOSITION
    _outer_type = SqlAlchemyEvidenceUnitOfWork
    _idempotent_type = SqlAlchemyIdempotentEvidenceUnitOfWork
    _joined_type = SqlAlchemyJoinedEvidenceUnitOfWork

    def begin(self, context: PersistenceContext) -> SqlAlchemyEvidenceUnitOfWork:
        return cast(SqlAlchemyEvidenceUnitOfWork, self._begin(context))

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> SqlAlchemyJoinedEvidenceUnitOfWork:
        return cast(
            SqlAlchemyJoinedEvidenceUnitOfWork,
            self._join(join_capability, context),
        )


class SqlAlchemyIdempotentEvidenceUnitOfWorkFactory(
    SqlAlchemyEvidenceUnitOfWorkFactory,
):
    __slots__ = ()
    _requires_api_profile = True

    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> SqlAlchemyIdempotentEvidenceUnitOfWork:
        return cast(
            SqlAlchemyIdempotentEvidenceUnitOfWork,
            self._begin_idempotent(context),
        )


class _EditorialRepositories(_RepositoryProperties):
    @property
    def article_plans(self) -> SqlAlchemyArticlePlanRepository:
        return cast(
            SqlAlchemyArticlePlanRepository,
            self._repository("article_plans"),
        )

    @property
    def articles(self) -> SqlAlchemyArticleRepository:
        return cast(SqlAlchemyArticleRepository, self._repository("articles"))

    @property
    def review_comments(self) -> SqlAlchemyReviewCommentRepository:
        return cast(
            SqlAlchemyReviewCommentRepository,
            self._repository("review_comments"),
        )

    @property
    def editorial_contracts(self) -> SqlAlchemyEditorialContractRepository:
        return cast(
            SqlAlchemyEditorialContractRepository,
            self._repository("editorial_contracts"),
        )

    @property
    def media_assets(self) -> SqlAlchemyMediaAssetRepository:
        return cast(
            SqlAlchemyMediaAssetRepository,
            self._repository("media_assets"),
        )


class SqlAlchemyEditorialUnitOfWork(
    _EditorialRepositories,
    _SqlAlchemyOuterUnitOfWork,
):
    __slots__ = ()


class SqlAlchemyIdempotentEditorialUnitOfWork(
    _EditorialRepositories,
    _SqlAlchemyIdempotentOuterUnitOfWork,
):
    __slots__ = ()


class SqlAlchemyJoinedEditorialUnitOfWork(
    _EditorialRepositories,
    _SqlAlchemyJoinedUnitOfWork,
):
    __slots__ = ()


_EDITORIAL_COMPOSITION = _composition(
    "editorial",
    {
        "article_plans": SqlAlchemyArticlePlanRepository,
        "articles": SqlAlchemyArticleRepository,
        "review_comments": SqlAlchemyReviewCommentRepository,
        "editorial_contracts": SqlAlchemyEditorialContractRepository,
        "media_assets": SqlAlchemyMediaAssetRepository,
    },
)


class SqlAlchemyEditorialUnitOfWorkFactory(_SqlAlchemyModuleFactory):
    __slots__ = ()
    _composition_definition = _EDITORIAL_COMPOSITION
    _outer_type = SqlAlchemyEditorialUnitOfWork
    _idempotent_type = SqlAlchemyIdempotentEditorialUnitOfWork
    _joined_type = SqlAlchemyJoinedEditorialUnitOfWork

    def begin(self, context: PersistenceContext) -> SqlAlchemyEditorialUnitOfWork:
        return cast(SqlAlchemyEditorialUnitOfWork, self._begin(context))

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> SqlAlchemyJoinedEditorialUnitOfWork:
        return cast(
            SqlAlchemyJoinedEditorialUnitOfWork,
            self._join(join_capability, context),
        )


class SqlAlchemyIdempotentEditorialUnitOfWorkFactory(
    SqlAlchemyEditorialUnitOfWorkFactory,
):
    __slots__ = ()
    _requires_api_profile = True

    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> SqlAlchemyIdempotentEditorialUnitOfWork:
        return cast(
            SqlAlchemyIdempotentEditorialUnitOfWork,
            self._begin_idempotent(context),
        )


class _AiRepositories(_RepositoryProperties):
    @property
    def task_definitions(self) -> SqlAlchemyAiTaskDefinitionRepository:
        return cast(
            SqlAlchemyAiTaskDefinitionRepository,
            self._repository("task_definitions"),
        )

    @property
    def output_schemas(self) -> SqlAlchemyOutputSchemaVersionRepository:
        return cast(
            SqlAlchemyOutputSchemaVersionRepository,
            self._repository("output_schemas"),
        )

    @property
    def model_definitions(self) -> SqlAlchemyModelDefinitionRepository:
        return cast(
            SqlAlchemyModelDefinitionRepository,
            self._repository("model_definitions"),
        )

    @property
    def model_routes(self) -> SqlAlchemyModelRouteVersionRepository:
        return cast(
            SqlAlchemyModelRouteVersionRepository,
            self._repository("model_routes"),
        )

    @property
    def prompt_versions(self) -> SqlAlchemyPromptVersionRepository:
        return cast(
            SqlAlchemyPromptVersionRepository,
            self._repository("prompt_versions"),
        )

    @property
    def ai_jobs(self) -> SqlAlchemyAiJobRepository:
        return cast(SqlAlchemyAiJobRepository, self._repository("ai_jobs"))

    @property
    def evaluation_results(self) -> SqlAlchemyEvaluationResultRepository:
        return cast(
            SqlAlchemyEvaluationResultRepository,
            self._repository("evaluation_results"),
        )

    @property
    def evaluation_suites(self) -> SqlAlchemyEvaluationSuiteRepository:
        return cast(
            SqlAlchemyEvaluationSuiteRepository,
            self._repository("evaluation_suites"),
        )

    @property
    def evaluation_datasets(self) -> SqlAlchemyEvaluationDatasetRepository:
        return cast(
            SqlAlchemyEvaluationDatasetRepository,
            self._repository("evaluation_datasets"),
        )

    @property
    def evaluation_runs(self) -> SqlAlchemyEvaluationRunRepository:
        return cast(
            SqlAlchemyEvaluationRunRepository,
            self._repository("evaluation_runs"),
        )

    @property
    def judge_calibrations(self) -> SqlAlchemyJudgeCalibrationRepository:
        return cast(
            SqlAlchemyJudgeCalibrationRepository,
            self._repository("judge_calibrations"),
        )

    @property
    def release_decisions(self) -> SqlAlchemyReleaseDecisionRepository:
        return cast(
            SqlAlchemyReleaseDecisionRepository,
            self._repository("release_decisions"),
        )


class SqlAlchemyAiUnitOfWork(_AiRepositories, _SqlAlchemyOuterUnitOfWork):
    __slots__ = ()


class SqlAlchemyIdempotentAiUnitOfWork(
    _AiRepositories,
    _SqlAlchemyIdempotentOuterUnitOfWork,
):
    __slots__ = ()


class SqlAlchemyJoinedAiUnitOfWork(
    _AiRepositories,
    _SqlAlchemyJoinedUnitOfWork,
):
    __slots__ = ()


_AI_COMPOSITION = _composition(
    "ai",
    {
        "task_definitions": SqlAlchemyAiTaskDefinitionRepository,
        "output_schemas": SqlAlchemyOutputSchemaVersionRepository,
        "model_definitions": SqlAlchemyModelDefinitionRepository,
        "model_routes": SqlAlchemyModelRouteVersionRepository,
        "prompt_versions": SqlAlchemyPromptVersionRepository,
        "ai_jobs": SqlAlchemyAiJobRepository,
        "evaluation_results": SqlAlchemyEvaluationResultRepository,
        "evaluation_suites": SqlAlchemyEvaluationSuiteRepository,
        "evaluation_datasets": SqlAlchemyEvaluationDatasetRepository,
        "evaluation_runs": SqlAlchemyEvaluationRunRepository,
        "judge_calibrations": SqlAlchemyJudgeCalibrationRepository,
        "release_decisions": SqlAlchemyReleaseDecisionRepository,
    },
)


class SqlAlchemyAiUnitOfWorkFactory(_SqlAlchemyModuleFactory):
    __slots__ = ()
    _composition_definition = _AI_COMPOSITION
    _outer_type = SqlAlchemyAiUnitOfWork
    _idempotent_type = SqlAlchemyIdempotentAiUnitOfWork
    _joined_type = SqlAlchemyJoinedAiUnitOfWork

    def begin(self, context: PersistenceContext) -> SqlAlchemyAiUnitOfWork:
        return cast(SqlAlchemyAiUnitOfWork, self._begin(context))

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> SqlAlchemyJoinedAiUnitOfWork:
        return cast(
            SqlAlchemyJoinedAiUnitOfWork,
            self._join(join_capability, context),
        )


class SqlAlchemyIdempotentAiUnitOfWorkFactory(
    SqlAlchemyAiUnitOfWorkFactory,
):
    __slots__ = ()
    _requires_api_profile = True

    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> SqlAlchemyIdempotentAiUnitOfWork:
        return cast(
            SqlAlchemyIdempotentAiUnitOfWork,
            self._begin_idempotent(context),
        )


class _PolicyRepositories(_RepositoryProperties):
    @property
    def policy_bundles(self) -> SqlAlchemyPolicyBundleRepository:
        return cast(
            SqlAlchemyPolicyBundleRepository,
            self._repository("policy_bundles"),
        )

    @property
    def rule_versions(self) -> SqlAlchemyRuleVersionRepository:
        return cast(
            SqlAlchemyRuleVersionRepository,
            self._repository("rule_versions"),
        )

    @property
    def quality_check_runs(self) -> SqlAlchemyQualityCheckRunRepository:
        return cast(
            SqlAlchemyQualityCheckRunRepository,
            self._repository("quality_check_runs"),
        )

    @property
    def findings(self) -> SqlAlchemyFindingRepository:
        return cast(SqlAlchemyFindingRepository, self._repository("findings"))

    @property
    def waivers(self) -> SqlAlchemyWaiverRepository:
        return cast(SqlAlchemyWaiverRepository, self._repository("waivers"))

    @property
    def gate_decisions(self) -> SqlAlchemyGateDecisionRepository:
        return cast(
            SqlAlchemyGateDecisionRepository,
            self._repository("gate_decisions"),
        )


class SqlAlchemyPolicyUnitOfWork(
    _PolicyRepositories,
    _SqlAlchemyOuterUnitOfWork,
):
    __slots__ = ()


class SqlAlchemyIdempotentPolicyUnitOfWork(
    _PolicyRepositories,
    _SqlAlchemyIdempotentOuterUnitOfWork,
):
    __slots__ = ()


class SqlAlchemyJoinedPolicyUnitOfWork(
    _PolicyRepositories,
    _SqlAlchemyJoinedUnitOfWork,
):
    __slots__ = ()


_POLICY_COMPOSITION = _composition(
    "policy",
    {
        "policy_bundles": SqlAlchemyPolicyBundleRepository,
        "rule_versions": SqlAlchemyRuleVersionRepository,
        "quality_check_runs": SqlAlchemyQualityCheckRunRepository,
        "findings": SqlAlchemyFindingRepository,
        "waivers": SqlAlchemyWaiverRepository,
        "gate_decisions": SqlAlchemyGateDecisionRepository,
    },
)


class SqlAlchemyPolicyUnitOfWorkFactory(_SqlAlchemyModuleFactory):
    __slots__ = ()
    _composition_definition = _POLICY_COMPOSITION
    _outer_type = SqlAlchemyPolicyUnitOfWork
    _idempotent_type = SqlAlchemyIdempotentPolicyUnitOfWork
    _joined_type = SqlAlchemyJoinedPolicyUnitOfWork

    def begin(self, context: PersistenceContext) -> SqlAlchemyPolicyUnitOfWork:
        return cast(SqlAlchemyPolicyUnitOfWork, self._begin(context))

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> SqlAlchemyJoinedPolicyUnitOfWork:
        return cast(
            SqlAlchemyJoinedPolicyUnitOfWork,
            self._join(join_capability, context),
        )


class SqlAlchemyIdempotentPolicyUnitOfWorkFactory(
    SqlAlchemyPolicyUnitOfWorkFactory,
):
    __slots__ = ()
    _requires_api_profile = True

    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> SqlAlchemyIdempotentPolicyUnitOfWork:
        return cast(
            SqlAlchemyIdempotentPolicyUnitOfWork,
            self._begin_idempotent(context),
        )


__all__ = [
    "SqlAlchemyAiUnitOfWork",
    "SqlAlchemyAiUnitOfWorkFactory",
    "SqlAlchemyCatalogUnitOfWork",
    "SqlAlchemyCatalogUnitOfWorkFactory",
    "SqlAlchemyEditorialUnitOfWork",
    "SqlAlchemyEditorialUnitOfWorkFactory",
    "SqlAlchemyEvidenceUnitOfWork",
    "SqlAlchemyEvidenceUnitOfWorkFactory",
    "SqlAlchemyIamUnitOfWork",
    "SqlAlchemyIamUnitOfWorkFactory",
    "SqlAlchemyIdempotentAiUnitOfWork",
    "SqlAlchemyIdempotentAiUnitOfWorkFactory",
    "SqlAlchemyIdempotentCatalogUnitOfWork",
    "SqlAlchemyIdempotentCatalogUnitOfWorkFactory",
    "SqlAlchemyIdempotentEditorialUnitOfWork",
    "SqlAlchemyIdempotentEditorialUnitOfWorkFactory",
    "SqlAlchemyIdempotentEvidenceUnitOfWork",
    "SqlAlchemyIdempotentEvidenceUnitOfWorkFactory",
    "SqlAlchemyIdempotentIamUnitOfWork",
    "SqlAlchemyIdempotentIamUnitOfWorkFactory",
    "SqlAlchemyIdempotentOpsUnitOfWork",
    "SqlAlchemyIdempotentOpsUnitOfWorkFactory",
    "SqlAlchemyIdempotentPolicyUnitOfWork",
    "SqlAlchemyIdempotentPolicyUnitOfWorkFactory",
    "SqlAlchemyIdempotentPortfolioUnitOfWork",
    "SqlAlchemyIdempotentPortfolioUnitOfWorkFactory",
    "SqlAlchemyJoinedAiUnitOfWork",
    "SqlAlchemyJoinedCatalogUnitOfWork",
    "SqlAlchemyJoinedEditorialUnitOfWork",
    "SqlAlchemyJoinedEvidenceUnitOfWork",
    "SqlAlchemyJoinedIamUnitOfWork",
    "SqlAlchemyJoinedOpsUnitOfWork",
    "SqlAlchemyJoinedPolicyUnitOfWork",
    "SqlAlchemyJoinedPortfolioUnitOfWork",
    "SqlAlchemyOpsUnitOfWork",
    "SqlAlchemyOpsUnitOfWorkFactory",
    "SqlAlchemyPolicyUnitOfWork",
    "SqlAlchemyPolicyUnitOfWorkFactory",
    "SqlAlchemyPortfolioUnitOfWork",
    "SqlAlchemyPortfolioUnitOfWorkFactory",
]
