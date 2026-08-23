"""Immutable command context; database workload identity is deliberately absent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from uuid import UUID

from raos.domain.shared.identity import Actor, require_uuid


_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,126}\Z", re.ASCII)


@dataclass(frozen=True, slots=True, repr=False)
class PersistenceContext:
    command_id: UUID
    correlation_id: UUID
    causation_id: UUID | None
    actor: Actor
    source: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        require_uuid(self.command_id)
        require_uuid(self.correlation_id)
        if self.causation_id is not None:
            require_uuid(self.causation_id)
        if type(self.actor) is not Actor:
            raise ValueError("INVALID_PERSISTENCE_CONTEXT") from None
        if type(self.source) is not str or _TOKEN.fullmatch(self.source) is None:
            raise ValueError("INVALID_PERSISTENCE_CONTEXT") from None
        if (
            type(self.occurred_at) is not datetime
            or self.occurred_at.tzinfo is not timezone.utc
            or self.occurred_at.fold
        ):
            raise ValueError("INVALID_PERSISTENCE_CONTEXT") from None

    def __repr__(self) -> str:
        return "PersistenceContext(<redacted>)"


__all__ = ["PersistenceContext"]
