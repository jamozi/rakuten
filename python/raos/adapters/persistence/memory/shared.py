"""Atomic audit, outbox, and idempotency capabilities for the memory slice."""

from __future__ import annotations

from typing import NoReturn, TypeAlias

from raos.adapters.persistence.memory.store import _MemoryClaimReservation
from raos.adapters.persistence.memory.transaction import _MemoryTransaction
from raos.domain.ops.aggregates import (
    AuditEventRecord,
    IdempotencyRecord,
    OutboxEventRecord,
)
from raos.domain.ops.enums import (
    AuditEventRecordActorType,
    AuditEventRecordOutcome,
    AuditEventRecordSeverity,
    IdempotencyRecordStatus,
    OutboxEventRecordStatus,
)
from raos.domain.ops.ids import AuditEventId, EventId, IdempotencyRecordId
from raos.domain.ops.values import (
    AuditEventRecordDetailsJson,
    IdempotencyRecordResponseBodyJson,
    OutboxEventRecordPayloadJson,
)
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
from raos.domain.shared.identity import (
    ActorId,
    CausationId,
    CorrelationId,
    OpaqueResourceId,
)
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import AwareUtcDateTime, Sha256Digest
from raos.ports.persistence.audit import AuditIntent
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from raos.ports.persistence.outbox import ValidatedOutboxEvent


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


class MemoryAuditEventAppender:
    __slots__ = ("_transaction",)

    def __init__(self, transaction: _MemoryTransaction) -> None:
        self._transaction = transaction

    def append_many(self, intents: tuple[AuditIntent, ...]) -> None:
        self._transaction.require_operation()
        if type(intents) is not tuple or any(
            type(intent) is not AuditIntent for intent in intents
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        context = self._transaction.context
        actor_id = (
            None if context.actor.actor_id is None else ActorId(context.actor.actor_id)
        )
        correlation_id = CorrelationId(context.correlation_id)
        timestamp = self._transaction.timestamp
        records: list[AuditEventRecord] = []
        for intent in intents:
            details = AuditEventRecordDetailsJson(
                FrozenJsonObject.from_mapping(
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
            )
            record = AuditEventRecord(
                id=AuditEventId(self._transaction.new_uuid7()),
                occurred_at=AwareUtcDateTime(context.occurred_at),
                actor_type=AuditEventRecordActorType(context.actor.actor_type.value),
                actor_id=actor_id,
                action=intent.action,
                target_type=intent.target_type,
                target_id=(
                    None
                    if intent.target_id is None
                    else OpaqueResourceId(intent.target_id.value)
                ),
                outcome=AuditEventRecordOutcome(intent.outcome),
                severity=AuditEventRecordSeverity.INFO,
                correlation_id=correlation_id,
                request_id=str(context.command_id),
                before_hash=None,
                after_hash=None,
                details=details,
                created_at=timestamp,
            )
            records.append(record)
        existing_ids = {record.id for record in self._transaction.state.audit_events}
        staged_ids = tuple(record.id for record in records)
        if existing_ids.intersection(staged_ids) or len(staged_ids) != len(
            set(staged_ids)
        ):
            _fail(PersistenceErrorCode.ALREADY_EXISTS)
        self._transaction.state.audit_events.extend(records)


class MemoryOutboxEventAppender:
    __slots__ = ("_transaction",)

    def __init__(self, transaction: _MemoryTransaction) -> None:
        self._transaction = transaction

    def append_many(self, events: tuple[ValidatedOutboxEvent, ...]) -> None:
        self._transaction.require_operation()
        if type(events) is not tuple or any(
            type(event) is not ValidatedOutboxEvent for event in events
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        context = self._transaction.context
        actor_id = (
            None if context.actor.actor_id is None else ActorId(context.actor.actor_id)
        )
        records: list[OutboxEventRecord] = []
        for validated in events:
            event = validated.event
            descriptor = event.descriptor
            record = OutboxEventRecord(
                id=EventId(event.event_id),
                event_type=descriptor.event_type,
                event_version=descriptor.event_version,
                producer=descriptor.producer,
                aggregate_type=descriptor.aggregate_type,
                aggregate_id=OpaqueResourceId(event.aggregate_id.value),
                aggregate_version=event.aggregate_version.value,
                correlation_id=CorrelationId(context.correlation_id),
                causation_id=(
                    None
                    if event.causation_id is None
                    else CausationId(event.causation_id)
                ),
                actor_type=context.actor.actor_type.value,
                actor_id=actor_id,
                payload=OutboxEventRecordPayloadJson(event.data),
                payload_schema_hash=Sha256Digest(descriptor.schema_sha256),
                status=OutboxEventRecordStatus.PENDING,
                available_at=self._transaction.timestamp,
                published_at=None,
                publish_attempts=0,
                last_error=None,
                created_at=self._transaction.timestamp,
            )
            records.append(record)
        existing_ids = {record.id for record in self._transaction.state.outbox_events}
        staged_ids = tuple(record.id for record in records)
        if existing_ids.intersection(staged_ids) or len(staged_ids) != len(
            set(staged_ids)
        ):
            _fail(PersistenceErrorCode.ALREADY_EXISTS)
        self._transaction.state.outbox_events.extend(records)


def _identity_key(identity: IdempotencyIdentity) -> tuple[str, str, str]:
    return (
        identity.actor_fingerprint.value,
        identity.route_key.value,
        identity.idempotency_key.value,
    )


def _record_key(record: IdempotencyRecord) -> tuple[str, str, str]:
    return (record.actor_fingerprint, record.route_key, record.idempotency_key)


def _outcome(record: IdempotencyRecord) -> IdempotencyOutcome:
    response_status = record.response_status
    if response_status is None:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    resource = (
        None
        if record.resource_type is None or record.resource_id is None
        else ResourceRef(record.resource_type, record.resource_id)
    )
    return IdempotencyOutcome(
        response_status=response_status,
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


_ReplayDecision: TypeAlias = (
    ReplaySucceeded | ReplayFailed | ClaimInProgress | PayloadMismatch
)


def _classify(
    record: IdempotencyRecord,
    request_hash: RequestHash,
) -> _ReplayDecision:
    if record.request_hash.value != request_hash.value:
        return PayloadMismatch()
    if record.status is IdempotencyRecordStatus.COMPLETED:
        return ReplaySucceeded(_outcome(record))
    if record.status is IdempotencyRecordStatus.FAILED:
        return ReplayFailed(_outcome(record))
    return ClaimInProgress(record.expires_at.value)


def _classify_reservation(
    reservation: _MemoryClaimReservation,
    request_hash: RequestHash,
) -> ClaimInProgress | PayloadMismatch:
    if reservation.request_hash != request_hash.value:
        return PayloadMismatch()
    return ClaimInProgress(reservation.expires_at)


class MemoryIdempotencyRepository:
    __slots__ = ("_transaction",)

    def __init__(self, transaction: _MemoryTransaction) -> None:
        self._transaction = transaction

    def _find(self, identity: IdempotencyIdentity) -> IdempotencyRecord | None:
        key = _identity_key(identity)
        rows = tuple(
            record
            for record in self._transaction.state.idempotency_records.values()
            if _record_key(record) == key
        )
        if len(rows) > 1:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return None if not rows else rows[0]

    def _handle(
        self,
        record: IdempotencyRecord,
        identity: IdempotencyIdentity,
        request_hash: RequestHash,
    ) -> IdempotencyClaimHandle:
        return _issue_claim_handle(
            record_id=record.id.value,
            identity=identity,
            request_hash=request_hash,
            transaction_id=self._transaction.transaction_id,
        )

    def claim(self, claim: IdempotencyClaim) -> IdempotencyClaimDecision:
        self._transaction.require_operation()
        if type(claim) is not IdempotencyClaim:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        now = self._transaction.timestamp
        if claim.expires_at <= now.value:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        record = self._find(claim.identity)
        if record is None:
            record_id = IdempotencyRecordId(self._transaction.new_uuid7())
            observed = self._transaction.store._observe_or_reserve_idempotency_claim(
                transaction_id=self._transaction.transaction_id,
                identity_key=_identity_key(claim.identity),
                request_hash=claim.request_hash.value,
                expires_at=claim.expires_at,
                record_id=record_id,
                observed_record=None,
            )
            if isinstance(observed, IdempotencyRecord):
                if observed.expires_at.value <= now.value:
                    _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
                return _classify(observed, claim.request_hash)
            if type(observed) is not _MemoryClaimReservation:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            if observed.owner_transaction_id != self._transaction.transaction_id:
                return _classify_reservation(observed, claim.request_hash)
            self._transaction.reserve_claim_key(observed.identity_key)
            record = IdempotencyRecord(
                id=observed.record_id,
                actor_fingerprint=claim.identity.actor_fingerprint.value,
                route_key=claim.identity.route_key.value,
                idempotency_key=claim.identity.idempotency_key.value,
                request_hash=Sha256Digest(claim.request_hash.value),
                status=IdempotencyRecordStatus.IN_PROGRESS,
                response_status=None,
                response_body=None,
                response_artifact_id=None,
                resource_type=None,
                resource_id=None,
                expires_at=AwareUtcDateTime(claim.expires_at),
                completed_at=None,
                created_at=now,
            )
            self._transaction.state.idempotency_records[record.id] = record
            return ClaimGranted(
                self._handle(record, claim.identity, claim.request_hash)
            )
        if record.expires_at.value > now.value:
            return _classify(record, claim.request_hash)
        observed = self._transaction.store._observe_or_reserve_idempotency_claim(
            transaction_id=self._transaction.transaction_id,
            identity_key=_identity_key(claim.identity),
            request_hash=claim.request_hash.value,
            expires_at=claim.expires_at,
            record_id=record.id,
            observed_record=record,
        )
        if isinstance(observed, IdempotencyRecord):
            if observed.expires_at.value <= now.value:
                _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
            return _classify(observed, claim.request_hash)
        if type(observed) is not _MemoryClaimReservation:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        if observed.owner_transaction_id != self._transaction.transaction_id:
            return _classify_reservation(observed, claim.request_hash)
        self._transaction.reserve_claim_key(observed.identity_key)
        replacement = IdempotencyRecord(
            id=record.id,
            actor_fingerprint=claim.identity.actor_fingerprint.value,
            route_key=claim.identity.route_key.value,
            idempotency_key=claim.identity.idempotency_key.value,
            request_hash=Sha256Digest(claim.request_hash.value),
            status=IdempotencyRecordStatus.IN_PROGRESS,
            response_status=None,
            response_body=None,
            response_artifact_id=None,
            resource_type=None,
            resource_id=None,
            expires_at=AwareUtcDateTime(claim.expires_at),
            completed_at=None,
            created_at=now,
        )
        self._transaction.state.idempotency_records[record.id] = replacement
        return ClaimGranted(
            self._handle(replacement, claim.identity, claim.request_hash)
        )

    def lookup(
        self,
        identity: IdempotencyIdentity,
        request_hash: RequestHash,
    ) -> IdempotencyLookupDecision:
        self._transaction.require_operation()
        if (
            type(identity) is not IdempotencyIdentity
            or type(request_hash) is not RequestHash
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        record = self._find(identity)
        if (
            record is None
            or record.expires_at.value <= self._transaction.timestamp.value
        ):
            return ClaimNotFound()
        return _classify(record, request_hash)

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
        self._complete(handle, outcome, IdempotencyRecordStatus.COMPLETED)

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
        self._complete(handle, outcome, IdempotencyRecordStatus.FAILED)

    def _complete(
        self,
        handle: IdempotencyClaimHandle,
        outcome: IdempotencyOutcome,
        terminal_status: IdempotencyRecordStatus,
    ) -> None:
        self._transaction.require_operation()
        if (
            type(handle) is not IdempotencyClaimHandle
            or type(outcome) is not IdempotencyOutcome
            or terminal_status
            not in {IdempotencyRecordStatus.COMPLETED, IdempotencyRecordStatus.FAILED}
        ):
            _fail(PersistenceErrorCode.LOST_IDEMPOTENCY_CLAIM)
        try:
            record_uuid, identity, request_hash = handle._adapter_fields(
                self._transaction.transaction_id
            )
        except TypeError, ValueError:
            _fail(PersistenceErrorCode.LOST_IDEMPOTENCY_CLAIM)
        record = next(
            (
                candidate
                for candidate in self._transaction.state.idempotency_records.values()
                if candidate.id.value == record_uuid
            ),
            None,
        )
        if (
            record is None
            or _record_key(record) != _identity_key(identity)
            or record.request_hash.value != request_hash.value
            or record.status is not IdempotencyRecordStatus.IN_PROGRESS
            or record.completed_at is not None
            or record.expires_at.value <= self._transaction.timestamp.value
            or _identity_key(identity) not in self._transaction.claim_reservation_keys
        ):
            _fail(PersistenceErrorCode.LOST_IDEMPOTENCY_CLAIM)
        if (
            outcome.response_artifact_id is not None
            and outcome.response_artifact_id
            not in self._transaction.state.object_artifacts
        ):
            _fail(PersistenceErrorCode.INTEGRITY_CONFLICT)
        resource_type = (
            None if outcome.resource is None else outcome.resource.resource_type
        )
        resource_id = None if outcome.resource is None else outcome.resource.resource_id
        replacement = IdempotencyRecord(
            id=record.id,
            actor_fingerprint=record.actor_fingerprint,
            route_key=record.route_key,
            idempotency_key=record.idempotency_key,
            request_hash=record.request_hash,
            status=terminal_status,
            response_status=outcome.response_status,
            response_body=(
                None
                if outcome.response_body is None
                else IdempotencyRecordResponseBodyJson(outcome.response_body)
            ),
            response_artifact_id=outcome.response_artifact_id,
            resource_type=resource_type,
            resource_id=resource_id,
            expires_at=record.expires_at,
            completed_at=self._transaction.timestamp,
            created_at=record.created_at,
        )
        self._transaction.state.idempotency_records[record.id] = replacement


__all__ = [
    "MemoryAuditEventAppender",
    "MemoryIdempotencyRepository",
    "MemoryOutboxEventAppender",
]
