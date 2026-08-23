"""Catalog-owned event classes admitted by the ST-0308 registry."""

from __future__ import annotations

from types import MappingProxyType
from typing import ClassVar, Final, NoReturn
from uuid import UUID

from raos.domain.catalog.ids import OfferId
from raos.domain.shared.events import (
    DomainEvent,
    EVENT_BY_TYPE,
    EventRuntimeBinding,
)
from raos.domain.shared.json_values import FrozenJsonArray, FrozenJsonObject
from raos.domain.shared.persistence import require_rfc3339_date_time


def _invalid() -> NoReturn:
    raise ValueError("INVALID_DOMAIN_EVENT") from None


def _uuid_text(value: object, expected: UUID | None = None) -> None:
    try:
        parsed = UUID(value) if type(value) is str else None
    except ValueError:
        _invalid()
    if (
        parsed is None
        or str(parsed) != value
        or (expected is not None and parsed != expected)
    ):
        _invalid()


def _text(value: object) -> None:
    if type(value) is not str or not value or value != value.strip():
        _invalid()


def _string_array(value: object) -> None:
    if type(value) is not FrozenJsonArray or any(
        type(item) is not str or not item for item in value
    ):
        _invalid()


def _validate_observed(payload: FrozenJsonObject, aggregate_id: UUID) -> None:
    if tuple(payload) != (
        "changed_fields",
        "freshness_status",
        "observation_types",
        "observed_at",
        "offer_id",
    ):
        _invalid()
    _uuid_text(payload["offer_id"], aggregate_id)
    _string_array(payload["observation_types"])
    _string_array(payload["changed_fields"])
    _text(payload["freshness_status"])
    require_rfc3339_date_time(payload["observed_at"])


def _validate_unavailable(payload: FrozenJsonObject, aggregate_id: UUID) -> None:
    if tuple(payload) != (
        "alternative_search_required",
        "observed_at",
        "offer_id",
        "reason_code",
    ):
        _invalid()
    _uuid_text(payload["offer_id"], aggregate_id)
    _text(payload["reason_code"])
    require_rfc3339_date_time(payload["observed_at"])
    if payload["alternative_search_required"] is not True:
        _invalid()


def _validate_affiliate_invalid(payload: FrozenJsonObject, aggregate_id: UUID) -> None:
    if tuple(payload) != (
        "cta_disabled",
        "link_observation_id",
        "offer_id",
        "risk_code",
    ):
        _invalid()
    _uuid_text(payload["offer_id"], aggregate_id)
    _uuid_text(payload["link_observation_id"])
    _text(payload["risk_code"])
    if payload["cta_disabled"] is not True:
        _invalid()


class _CatalogOfferEvent(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str]
    DATA_SCHEMA_SHA256: ClassVar[str]

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not OfferId:
            _invalid()
        super().__post_init__()


class CatalogOfferObserved(_CatalogOfferEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.catalog.offer_observed.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "c3e38d1c0cf17c475ca5d70a922b4ddcdfcdc8b2e381750a2b32c21fe1622f04"
    )


class CatalogOfferUnavailable(_CatalogOfferEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.catalog.offer_unavailable.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "d8a2df0bfcdb0056a3056d95350a77697a6f8659daea5e264ca9ad13487175b7"
    )


class CatalogAffiliateLinkInvalid(_CatalogOfferEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.catalog.affiliate_link_invalid.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "0787d7d44ef70f0a002be9c8ed4768ee19f6f833e5dd81e3399436593f72940a"
    )


def _binding(
    event_class: type[_CatalogOfferEvent],
    validator: object,
) -> EventRuntimeBinding:
    descriptor = EVENT_BY_TYPE[event_class.DESCRIPTOR_TYPE]
    if not callable(validator):
        raise RuntimeError("ST0308_CATALOG_EVENT_BINDING_INVALID")
    return EventRuntimeBinding(
        descriptor=descriptor,
        event_class=event_class,
        payload_schema_sha256=event_class.DATA_SCHEMA_SHA256,
        payload_validator=validator,
    )


_BINDINGS = (
    _binding(CatalogOfferObserved, _validate_observed),
    _binding(CatalogOfferUnavailable, _validate_unavailable),
    _binding(CatalogAffiliateLinkInvalid, _validate_affiliate_invalid),
)
_BINDINGS_BY_CLASS: dict[type[object], EventRuntimeBinding] = {
    binding.event_class: binding for binding in _BINDINGS
}
EVENT_RUNTIME_BINDINGS_BY_CLASS: Final[
    MappingProxyType[type[object], EventRuntimeBinding]
] = MappingProxyType(_BINDINGS_BY_CLASS)
EVENT_RUNTIME_BINDINGS_BY_TYPE: Final = MappingProxyType(
    {binding.descriptor.event_type: binding for binding in _BINDINGS}
)

__all__ = [
    "CatalogAffiliateLinkInvalid",
    "CatalogOfferObserved",
    "CatalogOfferUnavailable",
    "EVENT_RUNTIME_BINDINGS_BY_CLASS",
    "EVENT_RUNTIME_BINDINGS_BY_TYPE",
]
