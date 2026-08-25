"""Hash-bound EVIDENCE event classes admitted by the ST-0308 registry."""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import ClassVar, Final, NoReturn
from uuid import UUID

from raos.domain.evidence.ids import (
    SourceId,
)
from raos.domain.shared.events import (
    DomainEvent,
    EVENT_BY_TYPE,
    EventDescriptor,
    EventRuntimeBinding,
)
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import require_rfc3339_date_time


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def _invalid_payload() -> NoReturn:
    raise ValueError("INVALID_DOMAIN_EVENT") from None


def _uuid(value: object) -> UUID:
    if type(value) is not str:
        _invalid_payload()
    try:
        parsed = UUID(value)
    except ValueError:
        _invalid_payload()
    if str(parsed) != value:
        _invalid_payload()
    return parsed


def _artifact(value: object) -> None:
    if type(value) is not FrozenJsonObject:
        _invalid_payload()
    allowed = frozenset({"artifact_id", "uri", "sha256", "content_type", "byte_size"})
    if not {"artifact_id", "sha256"}.issubset(value):
        _invalid_payload()
    if not frozenset(value).issubset(allowed):
        _invalid_payload()
    _uuid(value["artifact_id"])
    sha256 = value["sha256"]
    if type(sha256) is not str or _SHA256.fullmatch(sha256) is None:
        _invalid_payload()
    uri = value["uri"] if "uri" in value else None
    if uri is not None and (
        type(uri) is not str or re.match(r"(?:s3|file)://", uri) is None
    ):
        _invalid_payload()
    content_type = value["content_type"] if "content_type" in value else None
    if content_type is not None and (
        type(content_type) is not str or len(content_type) > 120
    ):
        _invalid_payload()
    byte_size = value["byte_size"] if "byte_size" in value else None
    if byte_size is not None and (type(byte_size) is not int or byte_size < 0):
        _invalid_payload()


def _validate_EvidenceSourceSnapshotCaptured(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload)
        != (
            "acquired_at",
            "artifact",
            "source_id",
            "source_snapshot_id",
            "validation_status",
        )
    ):
        _invalid_payload()
    _uuid(payload["source_snapshot_id"])
    parsed_source_id = _uuid(payload["source_id"])
    if parsed_source_id != aggregate_id:
        _invalid_payload()
    _artifact(payload["artifact"])
    if type(payload["validation_status"]) is not str:
        _invalid_payload()
    try:
        require_rfc3339_date_time(payload["acquired_at"])
    except ValueError:
        _invalid_payload()


class EvidenceSourceSnapshotCaptured(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.evidence.source_snapshot_captured.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "f00bb94cea83ca3aede34fb6fe4531121ad356896414f3dddaa435dc8b104e93"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not SourceId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()


_EVIDENCE_SOURCE_SNAPSHOT_CAPTURED_DESCRIPTOR = EVENT_BY_TYPE[
    EvidenceSourceSnapshotCaptured.DESCRIPTOR_TYPE
]
if (
    _EVIDENCE_SOURCE_SNAPSHOT_CAPTURED_DESCRIPTOR.schema_sha256
    != EvidenceSourceSnapshotCaptured.DATA_SCHEMA_SHA256
    or _EVIDENCE_SOURCE_SNAPSHOT_CAPTURED_DESCRIPTOR.python_class
    != "raos.domain.evidence.events.EvidenceSourceSnapshotCaptured"
):
    raise RuntimeError("ST0308_EVIDENCE_EVENT_BINDING_INVALID")
_EVIDENCE_SOURCE_SNAPSHOT_CAPTURED_BINDING = EventRuntimeBinding(
    descriptor=_EVIDENCE_SOURCE_SNAPSHOT_CAPTURED_DESCRIPTOR,
    event_class=EvidenceSourceSnapshotCaptured,
    payload_schema_sha256=EvidenceSourceSnapshotCaptured.DATA_SCHEMA_SHA256,
    payload_validator=_validate_EvidenceSourceSnapshotCaptured,
)

EVENT_RUNTIME_BINDINGS_BY_CLASS: Final[
    MappingProxyType[type[object], EventRuntimeBinding]
] = MappingProxyType(
    {
        EvidenceSourceSnapshotCaptured: _EVIDENCE_SOURCE_SNAPSHOT_CAPTURED_BINDING,
    }
)
EVENT_RUNTIME_BINDINGS_BY_TYPE: Final[MappingProxyType[str, EventRuntimeBinding]] = (
    MappingProxyType(
        {
            EvidenceSourceSnapshotCaptured.DESCRIPTOR_TYPE: _EVIDENCE_SOURCE_SNAPSHOT_CAPTURED_BINDING,
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
    "EvidenceSourceSnapshotCaptured",
]
