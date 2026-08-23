"""Portfolio-owned event classes admitted by the ST-0308 registry."""

from __future__ import annotations

from types import MappingProxyType
from typing import ClassVar, Final, NoReturn
from uuid import UUID

from raos.domain.portfolio.ids import ActionCandidateId
from raos.domain.shared.events import (
    DomainEvent,
    EVENT_BY_TYPE,
    EventRuntimeBinding,
)
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import require_rfc3339_date_time


def _invalid() -> NoReturn:
    raise ValueError("INVALID_DOMAIN_EVENT") from None


def _validate(payload: FrozenJsonObject, aggregate_id: UUID) -> None:
    if tuple(payload) != ("action_candidate_id", "decided_at", "decision"):
        _invalid()
    candidate_id = payload["action_candidate_id"]
    decision = payload["decision"]
    try:
        parsed = UUID(candidate_id) if type(candidate_id) is str else None
        require_rfc3339_date_time(payload["decided_at"])
    except ValueError:
        _invalid()
    if (
        parsed is None
        or str(parsed) != candidate_id
        or parsed != aggregate_id
        or type(decision) is not str
        or not decision
    ):
        _invalid()


class PortfolioActionCandidateDecided(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.portfolio.action_candidate_decided.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "3ae2f73207c27bd019d9fd55e0d24c794e4a0d711265af902c4d38ec63bf2528"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not ActionCandidateId:
            _invalid()
        super().__post_init__()


_DESCRIPTOR = EVENT_BY_TYPE[PortfolioActionCandidateDecided.DESCRIPTOR_TYPE]
_BINDING = EventRuntimeBinding(
    descriptor=_DESCRIPTOR,
    event_class=PortfolioActionCandidateDecided,
    payload_schema_sha256=PortfolioActionCandidateDecided.DATA_SCHEMA_SHA256,
    payload_validator=_validate,
)

_BINDINGS_BY_CLASS: dict[type[object], EventRuntimeBinding] = {
    PortfolioActionCandidateDecided: _BINDING
}
EVENT_RUNTIME_BINDINGS_BY_CLASS: Final[
    MappingProxyType[type[object], EventRuntimeBinding]
] = MappingProxyType(_BINDINGS_BY_CLASS)
EVENT_RUNTIME_BINDINGS_BY_TYPE: Final = MappingProxyType(
    {PortfolioActionCandidateDecided.DESCRIPTOR_TYPE: _BINDING}
)

__all__ = [
    "EVENT_RUNTIME_BINDINGS_BY_CLASS",
    "EVENT_RUNTIME_BINDINGS_BY_TYPE",
    "PortfolioActionCandidateDecided",
]
