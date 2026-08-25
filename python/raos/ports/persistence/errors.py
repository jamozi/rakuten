"""Sanitized closed errors for inward persistence ports."""

from __future__ import annotations

from enum import Enum
from typing import NoReturn


class PersistenceErrorCode(str, Enum):
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    STATE_CONFLICT = "STATE_CONFLICT"
    INTEGRITY_CONFLICT = "INTEGRITY_CONFLICT"
    CROSS_MODULE_WRITE = "CROSS_MODULE_WRITE"
    READ_ONLY_RELATION = "READ_ONLY_RELATION"
    APPEND_ONLY_RELATION = "APPEND_ONLY_RELATION"
    TRANSACTION_OWNERSHIP = "TRANSACTION_OWNERSHIP"
    TRANSACTION_CLOSED = "TRANSACTION_CLOSED"
    TRANSACTION_ROLLBACK_ONLY = "TRANSACTION_ROLLBACK_ONLY"
    UNKNOWN_COMMIT = "UNKNOWN_COMMIT"
    IDENTITY_REJECTED = "IDENTITY_REJECTED"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    CANCELLED = "CANCELLED"
    STORAGE_CORRUPTION = "STORAGE_CORRUPTION"
    LOST_IDEMPOTENCY_CLAIM = "LOST_IDEMPOTENCY_CLAIM"


class PersistenceError(RuntimeError):
    """One immutable code with no raw SQL, field value, or underlying cause.

    Standard ``BaseException`` traceback/context fields remain writable because
    the interpreter and context-manager machinery own their lifecycle.
    """

    __slots__ = ("_code",)

    def __init__(self, code: PersistenceErrorCode) -> None:
        if type(code) is not PersistenceErrorCode:
            raise TypeError("invalid persistence error code")
        RuntimeError.__init__(self, code.value)
        self._code = code

    def __setattr__(self, name: str, value: object) -> None:
        if name == "_code":
            try:
                object.__getattribute__(self, name)
            except AttributeError:
                object.__setattr__(self, name, value)
                return
            raise AttributeError("immutable persistence error code") from None
        object.__setattr__(self, name, value)

    @property
    def code(self) -> PersistenceErrorCode:
        return self._code

    def __str__(self) -> str:
        return self._code.value

    def __repr__(self) -> str:
        return f"PersistenceError({self._code.value})"


class TransactionOwnershipError(PersistenceError):
    def __init__(self) -> None:
        super().__init__(PersistenceErrorCode.TRANSACTION_OWNERSHIP)


def fail_persistence(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


__all__ = [
    "PersistenceError",
    "PersistenceErrorCode",
    "TransactionOwnershipError",
    "fail_persistence",
]
