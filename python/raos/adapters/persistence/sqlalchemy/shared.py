"""Atomic Audit, Outbox, and Idempotency SQLAlchemy adapters for ST-0308."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from functools import wraps
import json
from typing import Any, NoReturn, cast
from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.sql.base import Executable

from raos.adapters.persistence.sqlalchemy.generated.ops_reference import (
    AUDIT_EVENT,
    IDEMPOTENCY_SQL,
    OUTBOX_EVENT,
)
from raos.adapters.persistence.sqlalchemy.mappers.ops import (
    map_ops_idempotency_record_from_row,
)
from raos.adapters.persistence.sqlalchemy.transaction import _SqlAlchemyTransaction
from raos.domain.ops.aggregates import IdempotencyRecord
from raos.domain.ops.enums import IdempotencyRecordStatus
from raos.domain.ops.ids import IdempotencyRecordId, ObjectArtifactId
from raos.domain.ops.values import IdempotencyRecordResponseBodyJson
from raos.domain.shared.idempotency import (
    ClaimGranted,
    ClaimInProgress,
    ClaimNotFound,
    IdempotencyClaim,
    IdempotencyClaimDecision,
    IdempotencyClaimHandle,
    IdempotencyIdentity,
    IdempotencyLookupDecision,
    IdempotencyOutcome,
    IdempotencyOutcomeDisposition,
    PayloadMismatch,
    ReplayFailed,
    ReplaySucceeded,
    RequestHash,
    ResourceRef,
    _issue_claim_handle,
)
from raos.domain.shared.identity import OpaqueResourceId
from raos.domain.shared.json_values import FrozenJsonObject, canonical_json_bytes
from raos.domain.shared.persistence import AwareUtcDateTime, Sha256Digest
from raos.ports.persistence.audit import AuditIntent
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from raos.ports.persistence.outbox import ValidatedOutboxEvent


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


def _plain(value: FrozenJsonObject) -> dict[str, object]:
    if type(value) is not FrozenJsonObject:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    try:
        result = json.loads(canonical_json_bytes(value))
    except TypeError, ValueError, UnicodeError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if type(result) is not dict:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return cast(dict[str, object], result)


def _execute_one(
    transaction: _SqlAlchemyTransaction,
    statement: Executable,
    parameters: Mapping[str, object] | None = None,
) -> RowMapping | None:
    transaction.require_operation()
    try:
        result = transaction.session.execute(
            statement,
            cast(Mapping[str, Any], parameters or {}),
        )
        return result.mappings().one_or_none()
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


def _execute_many(
    transaction: _SqlAlchemyTransaction,
    statement: Executable,
    parameters: list[dict[str, object]],
) -> None:
    transaction.require_operation()
    try:
        transaction.session.execute(
            statement,
            cast(list[Mapping[str, Any]], parameters),
        )
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


def _mapping(row: RowMapping) -> Mapping[str, object]:
    return cast(Mapping[str, object], row)


def _guard_transaction_class(adapter_type: type[Any]) -> type[Any]:
    """Poison an adapter transaction when a public call fails after DML."""

    if type(adapter_type) is not type:
        raise TypeError("INVALID_TRANSACTION_ADAPTER_TYPE") from None

    def wrap(method: Callable[..., object]) -> Callable[..., object]:
        @wraps(method)
        def guarded(self: object, *args: object, **kwargs: object) -> object:
            transaction = getattr(self, "_transaction", None)
            before = (
                transaction.successful_dml_count
                if type(transaction) is _SqlAlchemyTransaction
                else None
            )
            try:
                return method(self, *args, **kwargs)
            except BaseException:
                if (
                    type(transaction) is _SqlAlchemyTransaction
                    and before is not None
                    and transaction.successful_dml_count > before
                    and transaction.active
                ):
                    transaction.poison()
                raise

        return guarded

    for name, candidate in tuple(vars(adapter_type).items()):
        if name.startswith("_") or not callable(candidate):
            continue
        setattr(adapter_type, name, wrap(cast(Callable[..., object], candidate)))
    return adapter_type


@_guard_transaction_class
class SqlAlchemyAuditEventAppender:
    __slots__ = ("_transaction",)

    def __init__(self, transaction: _SqlAlchemyTransaction) -> None:
        if type(transaction) is not _SqlAlchemyTransaction:
            raise ValueError("INVALID_SQLALCHEMY_AUDIT_APPENDER") from None
        self._transaction = transaction

    def append_many(self, intents: tuple[AuditIntent, ...]) -> None:
        self._transaction.require_operation()
        if type(intents) is not tuple or any(
            type(intent) is not AuditIntent for intent in intents
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        if not intents:
            return
        context = self._transaction.context
        rows: list[dict[str, object]] = []
        for intent in intents:
            details = FrozenJsonObject.from_mapping(
                {
                    "context": {
                        "causation_id": (
                            None
                            if context.causation_id is None
                            else str(context.causation_id)
                        ),
                        "source": context.source,
                    },
                    "intent": {
                        "details": intent.sanitized_details.value,
                        "reason": intent.reason,
                    },
                }
            )
            rows.append(
                {
                    "occurred_at": context.occurred_at,
                    "actor_type": context.actor.actor_type.value,
                    "actor_id": context.actor.actor_id,
                    "action": intent.action,
                    "target_type": intent.target_type,
                    "target_id": (
                        None if intent.target_id is None else intent.target_id.value
                    ),
                    "outcome": intent.outcome,
                    "severity": "INFO",
                    "correlation_id": context.correlation_id,
                    "request_id": str(context.command_id),
                    "before_hash": None,
                    "after_hash": None,
                    "details": _plain(details),
                }
            )
        _execute_many(self._transaction, insert(AUDIT_EVENT), rows)


@_guard_transaction_class
class SqlAlchemyOutboxEventAppender:
    __slots__ = ("_transaction",)

    def __init__(self, transaction: _SqlAlchemyTransaction) -> None:
        if type(transaction) is not _SqlAlchemyTransaction:
            raise ValueError("INVALID_SQLALCHEMY_OUTBOX_APPENDER") from None
        self._transaction = transaction

    def append_many(self, events: tuple[ValidatedOutboxEvent, ...]) -> None:
        self._transaction.require_operation()
        if type(events) is not tuple or any(
            type(item) is not ValidatedOutboxEvent for item in events
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        if not events:
            return
        context = self._transaction.context
        rows: list[dict[str, object]] = []
        for item in events:
            event = item.event
            descriptor = event.descriptor
            rows.append(
                {
                    "id": event.event_id,
                    "event_type": descriptor.event_type,
                    "event_version": descriptor.event_version,
                    "producer": descriptor.producer,
                    "aggregate_type": descriptor.aggregate_type,
                    "aggregate_id": event.aggregate_id.value,
                    "aggregate_version": event.aggregate_version.value,
                    "correlation_id": context.correlation_id,
                    "causation_id": event.causation_id,
                    "actor_type": context.actor.actor_type.value,
                    "actor_id": context.actor.actor_id,
                    "payload": _plain(event.data),
                    "payload_schema_hash": descriptor.schema_sha256,
                    "status": "PENDING",
                    "available_at": self._transaction.timestamp.value,
                    "published_at": None,
                    "publish_attempts": 0,
                    "last_error": None,
                    "created_at": self._transaction.timestamp.value,
                }
            )
        _execute_many(self._transaction, insert(OUTBOX_EVENT), rows)


_RECORD_KEYS = frozenset(
    {
        "id",
        "actor_fingerprint",
        "route_key",
        "idempotency_key",
        "request_hash",
        "status",
        "response_status",
        "response_body",
        "response_artifact_id",
        "resource_type",
        "resource_id",
        "expires_at",
        "completed_at",
        "created_at",
    }
)
_CLAIM_KEYS = frozenset(
    {
        "id",
        "actor_fingerprint",
        "route_key",
        "idempotency_key",
        "request_hash",
        "status",
        "expires_at",
        "created_at",
    }
)


def _exact(row: Mapping[str, object], key: str, expected: type[object]) -> object:
    if key not in row or type(row[key]) is not expected:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return row[key]


def _optional(row: Mapping[str, object], key: str, expected: type[object]) -> object:
    if key not in row:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    value = row[key]
    if value is not None and type(value) is not expected:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _aware(value: object) -> AwareUtcDateTime:
    if (
        type(value) is not datetime
        or value.utcoffset() is None
        or value.utcoffset() != timezone.utc.utcoffset(value)
        or value.fold
    ):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    try:
        normalized = value.astimezone(timezone.utc)
        return AwareUtcDateTime(normalized)
    except TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _decode_record(row: Mapping[str, object]) -> IdempotencyRecord:
    if frozenset(row) != _RECORD_KEYS or len(row) != len(_RECORD_KEYS):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    response_body_raw = _optional(row, "response_body", dict)
    try:
        return map_ops_idempotency_record_from_row(
            id=IdempotencyRecordId(cast(UUID, _exact(row, "id", UUID))),
            actor_fingerprint=cast(str, _exact(row, "actor_fingerprint", str)),
            route_key=cast(str, _exact(row, "route_key", str)),
            idempotency_key=cast(str, _exact(row, "idempotency_key", str)),
            request_hash=Sha256Digest(cast(str, _exact(row, "request_hash", str))),
            status=IdempotencyRecordStatus(cast(str, _exact(row, "status", str))),
            response_status=cast(int | None, _optional(row, "response_status", int)),
            response_body=(
                None
                if response_body_raw is None
                else IdempotencyRecordResponseBodyJson(
                    FrozenJsonObject.from_mapping(
                        cast(dict[str, object], response_body_raw)
                    )
                )
            ),
            response_artifact_id=(
                None
                if row["response_artifact_id"] is None
                else ObjectArtifactId(
                    cast(
                        UUID,
                        _optional(row, "response_artifact_id", UUID),
                    )
                )
            ),
            resource_type=cast(str | None, _optional(row, "resource_type", str)),
            resource_id=(
                None
                if row["resource_id"] is None
                else OpaqueResourceId(cast(UUID, _optional(row, "resource_id", UUID)))
            ),
            expires_at=_aware(_exact(row, "expires_at", datetime)),
            completed_at=(
                None
                if row["completed_at"] is None
                else _aware(_optional(row, "completed_at", datetime))
            ),
            created_at=_aware(_exact(row, "created_at", datetime)),
        )
    except TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _outcome(record: IdempotencyRecord) -> IdempotencyOutcome:
    if (
        record.status is IdempotencyRecordStatus.IN_PROGRESS
        or record.response_status is None
        or record.completed_at is None
    ):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    try:
        resource = (
            None
            if record.resource_type is None or record.resource_id is None
            else ResourceRef(record.resource_type, record.resource_id)
        )
        return IdempotencyOutcome(
            response_status=record.response_status,
            response_body=(
                None if record.response_body is None else record.response_body.value
            ),
            response_artifact_id=record.response_artifact_id,
            resource=resource,
            disposition=(
                IdempotencyOutcomeDisposition.SUCCESS
                if record.status is IdempotencyRecordStatus.COMPLETED
                else IdempotencyOutcomeDisposition.ROUTE_APPROVED_DETERMINISTIC_BUSINESS_FAILURE
            ),
        )
    except TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _classify(
    record: IdempotencyRecord,
    request_hash: RequestHash,
) -> IdempotencyClaimDecision | IdempotencyLookupDecision:
    if record.request_hash.value != request_hash.value:
        return PayloadMismatch()
    if record.status is IdempotencyRecordStatus.COMPLETED:
        return ReplaySucceeded(_outcome(record))
    if record.status is IdempotencyRecordStatus.FAILED:
        return ReplayFailed(_outcome(record))
    if record.status is IdempotencyRecordStatus.IN_PROGRESS:
        return ClaimInProgress(record.expires_at.value)
    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


@_guard_transaction_class
class SqlAlchemyIdempotencyRepository:
    __slots__ = ("_transaction",)

    def __init__(self, transaction: _SqlAlchemyTransaction) -> None:
        if type(transaction) is not _SqlAlchemyTransaction:
            raise ValueError("INVALID_SQLALCHEMY_IDEMPOTENCY_REPOSITORY") from None
        self._transaction = transaction

    @property
    def _now(self) -> datetime:
        return self._transaction.timestamp.value

    @staticmethod
    def _identity_parameters(identity: IdempotencyIdentity) -> dict[str, object]:
        return {
            "actor_fingerprint": identity.actor_fingerprint.value,
            "route_key": identity.route_key.value,
            "idempotency_key": identity.idempotency_key.value,
        }

    def _handle(
        self,
        row: Mapping[str, object],
        identity: IdempotencyIdentity,
        request_hash: RequestHash,
    ) -> IdempotencyClaimHandle:
        if frozenset(row) != _CLAIM_KEYS or len(row) != len(_CLAIM_KEYS):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        if (
            _exact(row, "actor_fingerprint", str) != identity.actor_fingerprint.value
            or _exact(row, "route_key", str) != identity.route_key.value
            or _exact(row, "idempotency_key", str) != identity.idempotency_key.value
            or _exact(row, "request_hash", str) != request_hash.value
            or _exact(row, "status", str) != "IN_PROGRESS"
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        expires_at = _aware(_exact(row, "expires_at", datetime)).value
        created_at = _aware(_exact(row, "created_at", datetime)).value
        if expires_at <= created_at or expires_at <= self._now:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return _issue_claim_handle(
            record_id=cast(UUID, _exact(row, "id", UUID)),
            identity=identity,
            request_hash=request_hash,
            transaction_id=self._transaction.transaction_id,
        )

    def _read(self, identity: IdempotencyIdentity) -> IdempotencyRecord | None:
        row = _execute_one(
            self._transaction,
            IDEMPOTENCY_SQL["loser_read"],
            self._identity_parameters(identity),
        )
        return None if row is None else _decode_record(_mapping(row))

    def claim(self, claim: IdempotencyClaim) -> IdempotencyClaimDecision:
        if type(claim) is not IdempotencyClaim:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        if claim.expires_at <= self._now:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        parameters = self._identity_parameters(claim.identity)
        parameters.update(
            {
                "request_hash": claim.request_hash.value,
                "expires_at": claim.expires_at,
            }
        )
        row = _execute_one(
            self._transaction,
            IDEMPOTENCY_SQL["initial_claim"],
            parameters,
        )
        if row is not None:
            return ClaimGranted(
                self._handle(_mapping(row), claim.identity, claim.request_hash)
            )
        observed = self._read(claim.identity)
        if observed is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        if observed.expires_at.value > self._now:
            return cast(
                IdempotencyClaimDecision,
                _classify(observed, claim.request_hash),
            )
        locked_row = _execute_one(
            self._transaction,
            IDEMPOTENCY_SQL["expired_lock"],
            self._identity_parameters(claim.identity),
        )
        if locked_row is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        locked = _decode_record(_mapping(locked_row))
        if locked.expires_at.value > self._now:
            return cast(
                IdempotencyClaimDecision,
                _classify(locked, claim.request_hash),
            )
        replacement_parameters = self._identity_parameters(claim.identity)
        replacement_parameters.update(
            {
                "record_id": locked.id.value,
                "new_request_hash": claim.request_hash.value,
                "new_expires_at": claim.expires_at,
                "observed_request_hash": locked.request_hash.value,
                "observed_status": locked.status.value,
                "observed_expires_at": locked.expires_at.value,
            }
        )
        replacement = _execute_one(
            self._transaction,
            IDEMPOTENCY_SQL["expired_in_place_replacement"],
            replacement_parameters,
        )
        if replacement is not None:
            return ClaimGranted(
                self._handle(_mapping(replacement), claim.identity, claim.request_hash)
            )
        current = self._read(claim.identity)
        if current is None:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        if current.expires_at.value <= self._now:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        return cast(
            IdempotencyClaimDecision,
            _classify(current, claim.request_hash),
        )

    def lookup(
        self,
        identity: IdempotencyIdentity,
        request_hash: RequestHash,
    ) -> IdempotencyLookupDecision:
        if (
            type(identity) is not IdempotencyIdentity
            or type(request_hash) is not RequestHash
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        observed = self._read(identity)
        if observed is None or observed.expires_at.value <= self._now:
            return ClaimNotFound()
        return cast(IdempotencyLookupDecision, _classify(observed, request_hash))

    def complete_success(
        self,
        handle: IdempotencyClaimHandle,
        outcome: IdempotencyOutcome,
    ) -> None:
        if (
            type(outcome) is not IdempotencyOutcome
            or outcome.disposition is not IdempotencyOutcomeDisposition.SUCCESS
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self._complete("complete_success", "COMPLETED", handle, outcome)

    def complete_failure(
        self,
        handle: IdempotencyClaimHandle,
        outcome: IdempotencyOutcome,
    ) -> None:
        if (
            type(outcome) is not IdempotencyOutcome
            or outcome.disposition
            is not IdempotencyOutcomeDisposition.ROUTE_APPROVED_DETERMINISTIC_BUSINESS_FAILURE
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        self._complete("complete_failure", "FAILED", handle, outcome)

    def _complete(
        self,
        statement_key: str,
        expected_status: str,
        handle: IdempotencyClaimHandle,
        outcome: IdempotencyOutcome,
    ) -> None:
        if (
            type(handle) is not IdempotencyClaimHandle
            or type(outcome) is not IdempotencyOutcome
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        try:
            record_id, identity, request_hash = handle._adapter_fields(
                self._transaction.transaction_id
            )
        except TypeError, ValueError:
            _fail(PersistenceErrorCode.LOST_IDEMPOTENCY_CLAIM)
        parameters = {
            "handle_record_id": record_id,
            "handle_actor_fingerprint": identity.actor_fingerprint.value,
            "handle_route_key": identity.route_key.value,
            "handle_idempotency_key": identity.idempotency_key.value,
            "handle_request_hash": request_hash.value,
            "response_status": outcome.response_status,
            "response_body": (
                None
                if outcome.response_body is None
                else canonical_json_bytes(outcome.response_body).decode("utf-8")
            ),
            "response_artifact_id": (
                None
                if outcome.response_artifact_id is None
                else outcome.response_artifact_id.value
            ),
            "resource_type": (
                None if outcome.resource is None else outcome.resource.resource_type
            ),
            "resource_id": (
                None if outcome.resource is None else outcome.resource.resource_id.value
            ),
        }
        row = _execute_one(
            self._transaction,
            IDEMPOTENCY_SQL[statement_key],
            parameters,
        )
        if row is None:
            current = self._read(identity)
            if current is None:
                _fail(PersistenceErrorCode.NOT_FOUND)
            _fail(PersistenceErrorCode.LOST_IDEMPOTENCY_CLAIM)
        required = frozenset(
            {
                "id",
                "status",
                "response_status",
                "response_body",
                "response_artifact_id",
                "resource_type",
                "resource_id",
                "completed_at",
            }
        )
        mapped_row = _mapping(row)
        if frozenset(mapped_row) != required or len(mapped_row) != len(required):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        if (
            _exact(mapped_row, "id", UUID) != record_id
            or _exact(mapped_row, "status", str) != expected_status
            or _exact(mapped_row, "response_status", int) != outcome.response_status
            or mapped_row["completed_at"] is None
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        _aware(_optional(mapped_row, "completed_at", datetime))


__all__ = [
    "SqlAlchemyAuditEventAppender",
    "SqlAlchemyIdempotencyRepository",
    "SqlAlchemyOutboxEventAppender",
]
