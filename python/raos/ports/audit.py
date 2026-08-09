"""Inward context and append-only recording ports for ST-0405."""

from __future__ import annotations

from enum import Enum
import re
from typing import NoReturn, Protocol, SupportsIndex, final, runtime_checkable

from raos.domain.iam.authorization import AuthorizationGrant
from raos.domain.ops.audit import AuditContext, AuditEvent, AuditEventId


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class AuditAppendOutcome(str, Enum):
    """The only successful append result in this local seam."""

    RECORDED = "RECORDED"


@final
class AuditAppendReceipt:
    """Immutable acknowledgement for one exact audit event and digest."""

    __slots__ = ("_event_digest", "_event_id", "_outcome", "_sealed")
    _event_id: AuditEventId
    _event_digest: str
    _outcome: AuditAppendOutcome
    _sealed: bool

    def __init__(
        self,
        *,
        event_id: AuditEventId,
        event_digest: str,
        outcome: AuditAppendOutcome,
    ) -> None:
        if (
            type(event_id) is not AuditEventId
            or type(event_digest) is not str
            or _SHA256.fullmatch(event_digest) is None
            or type(outcome) is not AuditAppendOutcome
            or outcome is not AuditAppendOutcome.RECORDED
        ):
            raise ValueError("invalid audit append receipt") from None
        event_id.require_valid()
        object.__setattr__(self, "_event_id", event_id)
        object.__setattr__(self, "_event_digest", event_digest)
        object.__setattr__(self, "_outcome", outcome)
        object.__setattr__(self, "_sealed", True)

    @property
    def event_id(self) -> AuditEventId:
        return self._event_id

    @property
    def event_digest(self) -> str:
        return self._event_digest

    @property
    def outcome(self) -> AuditAppendOutcome:
        return self._outcome

    def require_valid(self) -> None:
        if (
            type(self._event_id) is not AuditEventId
            or type(self._event_digest) is not str
            or _SHA256.fullmatch(self._event_digest) is None
            or type(self._outcome) is not AuditAppendOutcome
            or self._outcome is not AuditAppendOutcome.RECORDED
        ):
            raise ValueError("invalid audit append receipt") from None
        self._event_id.require_valid()

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuditAppendReceipt is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AuditAppendReceipt is immutable")

    def __repr__(self) -> str:
        return "AuditAppendReceipt(<redacted-audit-receipt>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("audit append receipt serialization is not supported")


@runtime_checkable
class AuditContextSource(Protocol):
    """Issue one explicit trusted context already bound to ``grant``."""

    def issue(self, grant: AuthorizationGrant) -> AuditContext:
        """Return one exact context without ambient time, UUID, or environment."""

        ...


@runtime_checkable
class AuditEventAppender(Protocol):
    """Append one event and expose no update, delete, clear, export, or query."""

    def append(self, event: AuditEvent) -> AuditAppendReceipt:
        """Synchronously append exactly once and return its exact receipt."""

        ...


__all__ = [
    "AuditAppendOutcome",
    "AuditAppendReceipt",
    "AuditContextSource",
    "AuditEventAppender",
]
