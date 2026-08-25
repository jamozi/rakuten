"""Exact shared inward persistence ports for ST-0308."""

from raos.ports.persistence.audit import (
    AuditEventAppender,
    AuditIntent,
    SanitizedAuditDetails,
)
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from raos.ports.persistence.idempotency import IdempotencyRepository
from raos.ports.persistence.outbox import OutboxEventAppender, ValidatedOutboxEvent
from raos.ports.persistence.transaction import TransactionJoin, TransactionState

__all__ = [
    "AuditEventAppender",
    "AuditIntent",
    "SanitizedAuditDetails",
    "IdempotencyRepository",
    "OutboxEventAppender",
    "PersistenceContext",
    "PersistenceError",
    "PersistenceErrorCode",
    "TransactionJoin",
    "TransactionState",
    "ValidatedOutboxEvent",
]
