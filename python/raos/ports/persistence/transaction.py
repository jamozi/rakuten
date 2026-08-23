"""Framework-neutral transaction ownership values for ST-0308."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Final, NoReturn, SupportsIndex
from uuid import UUID

from raos.domain.shared.identity import require_uuid


_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_JOIN_ISSUER: Final[object] = object()


def _invalid() -> NoReturn:
    raise ValueError("INVALID_TRANSACTION_JOIN") from None


class TransactionState(str, Enum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"
    UNKNOWN = "UNKNOWN"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True, repr=False, init=False)
class TransactionJoin:
    """Opaque, nonserializable capability issued by one active outer UoW."""

    __transaction_id: UUID
    __context_digest: str
    __owner_key: object

    def __init__(
        self,
        transaction_id: UUID,
        context_digest: str,
        owner_key: object,
        *,
        _issuer: object,
    ) -> None:
        if _issuer is not _JOIN_ISSUER or owner_key is None:
            _invalid()
        require_uuid(transaction_id)
        if type(context_digest) is not str or _HASH.fullmatch(context_digest) is None:
            _invalid()
        object.__setattr__(self, "_TransactionJoin__transaction_id", transaction_id)
        object.__setattr__(self, "_TransactionJoin__context_digest", context_digest)
        object.__setattr__(self, "_TransactionJoin__owner_key", owner_key)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("transaction join serialization is not supported")

    def __repr__(self) -> str:
        return "TransactionJoin(<redacted>)"

    def _adapter_fields(self, owner_key: object) -> tuple[UUID, str]:
        if owner_key is not self.__owner_key:
            _invalid()
        return self.__transaction_id, self.__context_digest


def _issue_transaction_join(
    *, transaction_id: UUID, context_digest: str, owner_key: object
) -> TransactionJoin:
    """Adapter-private issuer; intentionally absent from ``__all__``."""

    return TransactionJoin(
        transaction_id,
        context_digest,
        owner_key,
        _issuer=_JOIN_ISSUER,
    )


__all__ = ["TransactionJoin", "TransactionState"]
