"""Hash-bound POLICY event classes admitted by the ST-0308 registry."""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import ClassVar, Final, NoReturn
from uuid import UUID

from raos.domain.policy.ids import (
    PolicyBundleId,
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


def _validate_PolicyPolicyBundleActivated(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload)
        != (
            "bundle_code",
            "bundle_sha256",
            "effective_from",
            "policy_bundle_id",
            "version_no",
        )
    ):
        _invalid_payload()
    parsed_policy_bundle_id = _uuid(payload["policy_bundle_id"])
    if parsed_policy_bundle_id != aggregate_id:
        _invalid_payload()
    if type(payload["bundle_code"]) is not str:
        _invalid_payload()
    if type(payload["version_no"]) is not int:
        _invalid_payload()
    if (
        type(payload["bundle_sha256"]) is not str
        or re.fullmatch("^[0-9a-f]{64}$", payload["bundle_sha256"]) is None
    ):
        _invalid_payload()
    try:
        require_rfc3339_date_time(payload["effective_from"])
    except ValueError:
        _invalid_payload()


class PolicyPolicyBundleActivated(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.policy.policy_bundle_activated.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "cb6c7233454a08ab0eea46e12fd4ff353205763393853f16d812bfe0cadbd461"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not PolicyBundleId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()


_POLICY_POLICY_BUNDLE_ACTIVATED_DESCRIPTOR = EVENT_BY_TYPE[
    PolicyPolicyBundleActivated.DESCRIPTOR_TYPE
]
if (
    _POLICY_POLICY_BUNDLE_ACTIVATED_DESCRIPTOR.schema_sha256
    != PolicyPolicyBundleActivated.DATA_SCHEMA_SHA256
    or _POLICY_POLICY_BUNDLE_ACTIVATED_DESCRIPTOR.python_class
    != "raos.domain.policy.events.PolicyPolicyBundleActivated"
):
    raise RuntimeError("ST0308_POLICY_EVENT_BINDING_INVALID")
_POLICY_POLICY_BUNDLE_ACTIVATED_BINDING = EventRuntimeBinding(
    descriptor=_POLICY_POLICY_BUNDLE_ACTIVATED_DESCRIPTOR,
    event_class=PolicyPolicyBundleActivated,
    payload_schema_sha256=PolicyPolicyBundleActivated.DATA_SCHEMA_SHA256,
    payload_validator=_validate_PolicyPolicyBundleActivated,
)

EVENT_RUNTIME_BINDINGS_BY_CLASS: Final[
    MappingProxyType[type[object], EventRuntimeBinding]
] = MappingProxyType(
    {
        PolicyPolicyBundleActivated: _POLICY_POLICY_BUNDLE_ACTIVATED_BINDING,
    }
)
EVENT_RUNTIME_BINDINGS_BY_TYPE: Final[MappingProxyType[str, EventRuntimeBinding]] = (
    MappingProxyType(
        {
            PolicyPolicyBundleActivated.DESCRIPTOR_TYPE: _POLICY_POLICY_BUNDLE_ACTIVATED_BINDING,
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
    "PolicyPolicyBundleActivated",
]
