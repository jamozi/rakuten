"""Bounded process-local ST-0405 audit context and append adapter.

This adapter is restricted to exact ``ENV-DEV`` and an explicitly supplied
synthetic context script.  Its lock protects only this process.  The adapter
is not a durable writer, database transaction, immutable database role,
cross-process fence, retention mechanism, export, or production query service.
"""

from __future__ import annotations

from threading import RLock
from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authorization import AuthorizationGrant
from raos.domain.ops.audit import AuditContext, AuditEvent, AuditEventId
from raos.ports.audit import AuditAppendOutcome, AuditAppendReceipt


_MAX_CAPACITY = 10_000


def _reject() -> NoReturn:
    raise ValueError("recorded audit operation failed") from None


@final
class RecordedAuditAdapter:
    """One deterministic context script and append-only ordered event tuple."""

    __slots__ = (
        "_capacity",
        "_context_index",
        "_context_script",
        "_environment",
        "_event_ids",
        "_events",
        "_lock",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        capacity: int,
        context_script: tuple[AuditContext, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment is not RuntimeEnvironment.ENV_DEV
            or type(capacity) is not int
            or not 1 <= capacity <= _MAX_CAPACITY
            or type(context_script) is not tuple
            or any(type(context) is not AuditContext for context in context_script)
        ):
            _reject()
        for context in context_script:
            context_failed = False
            try:
                context.event_id.require_valid()
            except Exception:
                context_failed = True
            if context_failed:
                _reject()
        if len({context.event_id for context in context_script}) != len(context_script):
            _reject()
        self._environment = environment
        self._capacity = capacity
        self._context_script = context_script
        self._context_index = 0
        self._events: tuple[AuditEvent, ...] = ()
        self._event_ids: frozenset[AuditEventId] = frozenset()
        self._lock = RLock()

    @property
    def environment(self) -> RuntimeEnvironment:
        return self._environment

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def external_action_count(self) -> int:
        """The recorded collaborator performs no external action."""

        return 0

    def issue(self, grant: AuthorizationGrant) -> AuditContext:
        """Consume one exact scripted context already bound to ``grant``."""

        if type(grant) is not AuthorizationGrant:
            _reject()
        with self._lock:
            if self._context_index >= len(self._context_script):
                _reject()
            context = self._context_script[self._context_index]
            context_failed = False
            try:
                context.require_bound_to(grant)
            except Exception:
                context_failed = True
            if context_failed:
                _reject()
            self._context_index += 1
            return context

    def append(self, event: AuditEvent) -> AuditAppendReceipt:
        """Append once; full, duplicate, or malformed events never evict data."""

        if type(event) is not AuditEvent:
            _reject()
        event_failed = False
        try:
            event.require_valid()
        except Exception:
            event_failed = True
        if event_failed:
            _reject()
        with self._lock:
            if len(self._events) >= self._capacity or event.event_id in self._event_ids:
                _reject()
            self._events = (*self._events, event)
            self._event_ids = self._event_ids | {event.event_id}
            return AuditAppendReceipt(
                event_id=event.event_id,
                event_digest=event.digest,
                outcome=AuditAppendOutcome.RECORDED,
            )

    def snapshot(self) -> tuple[AuditEvent, ...]:
        """Return the immutable ordered test snapshot; no filter/query is exposed."""

        with self._lock:
            return self._events

    def __repr__(self) -> str:
        return "RecordedAuditAdapter(<redacted-recorded-audit>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded audit adapter serialization is not supported")


__all__ = ["RecordedAuditAdapter"]
