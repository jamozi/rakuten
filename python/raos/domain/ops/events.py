"""OPS-owned event classes admitted by the ST-0308 closed registry."""

from __future__ import annotations

from types import MappingProxyType
from typing import ClassVar, Final, NoReturn
from uuid import UUID

from raos.domain.catalog.events import (
    EVENT_RUNTIME_BINDINGS_BY_CLASS as CATALOG_BINDINGS_BY_CLASS,
    EVENT_RUNTIME_BINDINGS_BY_TYPE as CATALOG_BINDINGS_BY_TYPE,
)
from raos.domain.ops.ids import JobId
from raos.domain.shared.events import (
    DomainEvent,
    EVENT_BY_TYPE,
    EventDescriptor,
    EventRuntimeBinding,
)
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import require_rfc3339_date_time
from raos.domain.portfolio.events import (
    EVENT_RUNTIME_BINDINGS_BY_CLASS as PORTFOLIO_BINDINGS_BY_CLASS,
    EVENT_RUNTIME_BINDINGS_BY_TYPE as PORTFOLIO_BINDINGS_BY_TYPE,
)


def _invalid_payload() -> NoReturn:
    raise ValueError("INVALID_DOMAIN_EVENT") from None


def _validate_ops_job_requested_payload(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload) != ("available_at", "job_id", "job_type", "queue")
    ):
        _invalid_payload()
    job_id = payload["job_id"]
    job_type = payload["job_type"]
    queue = payload["queue"]
    available_at = payload["available_at"]
    try:
        parsed_job_id = UUID(job_id) if type(job_id) is str else None
        require_rfc3339_date_time(available_at)
    except ValueError:
        _invalid_payload()
    if (
        parsed_job_id is None
        or str(parsed_job_id) != job_id
        or parsed_job_id != aggregate_id
        or type(job_type) is not str
        or type(queue) is not str
    ):
        _invalid_payload()


class OpsJobRequested(DomainEvent):
    """Exact event class for ``jp.raos.ops.job_requested.v1``."""

    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.ops.job_requested.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "c10f9773b621000705684bec152bdc8f037c46b688f390216effa2872ab8e671"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not JobId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()


_OPS_JOB_REQUESTED_DESCRIPTOR = EVENT_BY_TYPE[OpsJobRequested.DESCRIPTOR_TYPE]
if (
    _OPS_JOB_REQUESTED_DESCRIPTOR.schema_sha256 != OpsJobRequested.DATA_SCHEMA_SHA256
    or _OPS_JOB_REQUESTED_DESCRIPTOR.python_class
    != "raos.domain.ops.events.OpsJobRequested"
):
    raise RuntimeError("ST0308_OPS_EVENT_BINDING_INVALID")

_OPS_JOB_REQUESTED_BINDING = EventRuntimeBinding(
    descriptor=_OPS_JOB_REQUESTED_DESCRIPTOR,
    event_class=OpsJobRequested,
    payload_schema_sha256=OpsJobRequested.DATA_SCHEMA_SHA256,
    payload_validator=_validate_ops_job_requested_payload,
)

EVENT_RUNTIME_BINDINGS_BY_CLASS: Final[
    MappingProxyType[type[object], EventRuntimeBinding]
] = MappingProxyType(
    {
        OpsJobRequested: _OPS_JOB_REQUESTED_BINDING,
        **PORTFOLIO_BINDINGS_BY_CLASS,
        **CATALOG_BINDINGS_BY_CLASS,
    }
)
EVENT_RUNTIME_BINDINGS_BY_TYPE: Final[MappingProxyType[str, EventRuntimeBinding]] = (
    MappingProxyType(
        {
            OpsJobRequested.DESCRIPTOR_TYPE: _OPS_JOB_REQUESTED_BINDING,
            **PORTFOLIO_BINDINGS_BY_TYPE,
            **CATALOG_BINDINGS_BY_TYPE,
        }
    )
)
EVENT_CLASS_DESCRIPTORS: Final[MappingProxyType[type[object], EventDescriptor]] = (
    MappingProxyType(
        {
            event_class: binding.descriptor
            for event_class, binding in EVENT_RUNTIME_BINDINGS_BY_CLASS.items()
        }
    )
)


__all__ = [
    "EVENT_CLASS_DESCRIPTORS",
    "EVENT_RUNTIME_BINDINGS_BY_CLASS",
    "EVENT_RUNTIME_BINDINGS_BY_TYPE",
    "OpsJobRequested",
]
