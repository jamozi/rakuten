"""Coordination-only ST-0405 audit recording service.

The returned commit token proves only that the configured appender accepted one
exact local audit event.  This service performs no business mutation or
callback and cannot make a business change atomic with audit recording.  A
durable unit of work and database integration remain deferred to ST-0308 and a
later persistence slice.
"""

from __future__ import annotations

from enum import Enum
import re
from typing import NoReturn, SupportsIndex, final

from raos.domain.iam.authorization import AuthorizationGrant
from raos.domain.ops.audit import (
    AuditContext,
    AuditEvent,
    AuditEventId,
    AuditOutcome,
    AuditReasonCode,
    AuditSeverity,
)
from raos.ports.audit import (
    AuditAppendOutcome,
    AuditAppendReceipt,
    AuditContextSource,
    AuditEventAppender,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class AuditFailureCode(str, Enum):
    """The sole stable failure visible to an application caller."""

    REQUIRED_RECORD_NOT_COMMITTED = "REQUIRED_RECORD_NOT_COMMITTED"


@final
class AuditFailure(RuntimeError):
    """Sanitized immutable failure with no collaborator data or cause."""

    __slots__ = ("_code", "_sealed")
    _code: AuditFailureCode
    _sealed: bool

    def __init__(self, code: AuditFailureCode) -> None:
        if (
            type(code) is not AuditFailureCode
            or code is not AuditFailureCode.REQUIRED_RECORD_NOT_COMMITTED
        ):
            raise TypeError("invalid audit failure code")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)
        object.__setattr__(self, "_sealed", True)

    @property
    def code(self) -> AuditFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuditFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AuditFailure is immutable")

    def __repr__(self) -> str:
        return "AuditFailure(REQUIRED_RECORD_NOT_COMMITTED)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("audit failure serialization is not supported")


def _fail() -> NoReturn:
    raise AuditFailure(AuditFailureCode.REQUIRED_RECORD_NOT_COMMITTED) from None


@final
class AuditCommitToken:
    """Immutable proof that one exact event/digest receipt was validated."""

    __slots__ = ("_event_digest", "_event_id", "_sealed")
    _event_id: AuditEventId
    _event_digest: str
    _sealed: bool

    def __init__(self, *, event_id: AuditEventId, event_digest: str) -> None:
        if (
            type(event_id) is not AuditEventId
            or type(event_digest) is not str
            or _SHA256.fullmatch(event_digest) is None
        ):
            _fail()
        event_id_failed = False
        try:
            event_id.require_valid()
        except Exception:
            event_id_failed = True
        if event_id_failed:
            _fail()
        object.__setattr__(self, "_event_id", event_id)
        object.__setattr__(self, "_event_digest", event_digest)
        object.__setattr__(self, "_sealed", True)

    @property
    def event_id(self) -> AuditEventId:
        return self._event_id

    @property
    def event_digest(self) -> str:
        return self._event_digest

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuditCommitToken is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AuditCommitToken is immutable")

    def __repr__(self) -> str:
        return "AuditCommitToken(<redacted-audit-token>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("audit commit token serialization is not supported")


def _supports(candidate: object, protocol: type[object]) -> bool:
    try:
        return isinstance(candidate, protocol)
    except Exception:
        return False


@final
class AuditService:
    """Require one exact append before returning an audit commit token."""

    __slots__ = ("_appender", "_context_source")

    def __init__(
        self,
        *,
        context_source: AuditContextSource,
        appender: AuditEventAppender,
    ) -> None:
        if not _supports(context_source, AuditContextSource):
            raise TypeError("context_source must implement AuditContextSource")
        if not _supports(appender, AuditEventAppender):
            raise TypeError("appender must implement AuditEventAppender")
        self._context_source = context_source
        self._appender = appender

    def require_authorized_record(
        self,
        *,
        grant: AuthorizationGrant,
        outcome: AuditOutcome,
        severity: AuditSeverity,
        reason_code: AuditReasonCode,
        before_hash: str | None = None,
        after_hash: str | None = None,
    ) -> AuditCommitToken:
        """Append once or raise only ``REQUIRED_RECORD_NOT_COMMITTED``.

        Callers must not claim that a related business operation succeeded
        unless they receive this token.  Receiving it still does not make a
        separate business mutation transactional with the recorded event.
        """

        if (
            type(grant) is not AuthorizationGrant
            or type(outcome) is not AuditOutcome
            or type(severity) is not AuditSeverity
            or type(reason_code) is not AuditReasonCode
            or (before_hash is not None and type(before_hash) is not str)
            or (after_hash is not None and type(after_hash) is not str)
        ):
            _fail()

        context: object = None
        context_failed = False
        try:
            context = self._context_source.issue(grant)
            if type(context) is AuditContext:
                context.require_bound_to(grant)
        except Exception:
            context_failed = True
        if context_failed or type(context) is not AuditContext:
            _fail()

        event: AuditEvent | None = None
        event_failed = False
        try:
            event = AuditEvent(
                grant=grant,
                context=context,
                outcome=outcome,
                severity=severity,
                reason_code=reason_code,
                before_hash=before_hash,
                after_hash=after_hash,
            )
            event.require_valid()
        except Exception:
            event_failed = True
        if event_failed or type(event) is not AuditEvent:
            _fail()

        receipt: object = None
        receipt_failed = False
        try:
            receipt = self._appender.append(event)
            if type(receipt) is AuditAppendReceipt:
                receipt.require_valid()
        except Exception:
            receipt_failed = True
        if (
            receipt_failed
            or type(receipt) is not AuditAppendReceipt
            or receipt.outcome is not AuditAppendOutcome.RECORDED
            or receipt.event_id != event.event_id
            or receipt.event_digest != event.digest
        ):
            _fail()

        commit_token: AuditCommitToken | None = None
        commit_token_failed = False
        try:
            commit_token = AuditCommitToken(
                event_id=event.event_id,
                event_digest=event.digest,
            )
        except Exception:
            commit_token_failed = True
        if commit_token_failed or type(commit_token) is not AuditCommitToken:
            _fail()
        return commit_token


__all__ = [
    "AuditCommitToken",
    "AuditFailure",
    "AuditFailureCode",
    "AuditService",
]
