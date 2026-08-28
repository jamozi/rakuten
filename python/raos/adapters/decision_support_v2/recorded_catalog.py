"""Official-fact-only recorded product catalog."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Mapping, cast

from raos.adapters.decision_support_v2.errors import AdapterError, AdapterFailure
from raos.adapters.decision_support_v2.strict_json import loads_strict_json
from raos.domain.decision_support_v2.models import (
    DimensionEdges,
    IdentityStatus,
    ProductModel,
    ProductVariant,
)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    raw = cast("dict[object, object]", value)
    result: dict[str, object] = {}
    for key, item in raw.items():
        if not isinstance(key, str):
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)
        result[key] = item
    return result


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return cast("list[object]", value)


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return value


def _strings(value: object) -> tuple[str, ...]:
    result: list[str] = []
    for item in _list(value):
        result.append(_string(item))
    return tuple(result)


def _decimal(value: object) -> Decimal:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return Decimal(value)


def _dimensions(value: object) -> DimensionEdges:
    if isinstance(value, dict):
        record = _mapping(cast(object, value))
        if (
            set(record) != {"edges_cm", "orientation", "includes_wheels_and_handles"}
            or record.get("orientation") != "ORDERED"
            or record.get("includes_wheels_and_handles") is not True
        ):
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)
        value = record.get("edges_cm")
    edges = _list(value)
    if len(edges) != 3:
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return DimensionEdges(*(_decimal(item) for item in edges))


def load_products(path: Path) -> tuple[ProductModel, ...]:
    try:
        decoded: object = loads_strict_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise AdapterError(AdapterFailure.INVALID_RESPONSE) from exc
    payload = _mapping(decoded)
    if payload.get("schema") != "RAOS_V2_ACE_PRODUCT_MODELS_V1":
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    if (
        set(payload)
        != {
            "schema",
            "version",
            "source_basis",
            "checked_at",
            "products",
        }
        or payload["source_basis"] != "OFFICIAL_MANUFACTURER_RECORDED_FACTS"
    ):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    product_records = _list(payload["products"])
    products: list[ProductModel] = []
    try:
        for raw_record in product_records:
            record = _mapping(raw_record)
            if set(record) != {
                "schema_version",
                "product_id",
                "manufacturer",
                "brand",
                "model_name",
                "model_number",
                "generation",
                "official_source_ids",
                "identity_status",
                "variants",
            }:
                raise AdapterError(AdapterFailure.INVALID_RESPONSE)
            if record["schema_version"] != "1.0.0":
                raise AdapterError(AdapterFailure.INVALID_RESPONSE)
            expected_variant = {
                "schema_version",
                "variant_id",
                "external_dimensions_cm",
                "expanded_dimensions_cm",
                "mass_kg",
                "capacity_l",
                "expanded_capacity_l",
                "declared_features",
                "unknown_fields",
            }
            variants: list[ProductVariant] = []
            for raw_variant in _list(record["variants"]):
                variant = _mapping(raw_variant)
                if (
                    set(variant) != expected_variant
                    or variant["schema_version"] != "1.0.0"
                ):
                    raise AdapterError(AdapterFailure.INVALID_RESPONSE)
                expanded_dimensions = variant["expanded_dimensions_cm"]
                expanded_capacity = variant["expanded_capacity_l"]
                variants.append(
                    ProductVariant(
                        variant_id=_string(variant["variant_id"]),
                        external_dimensions_cm=_dimensions(
                            variant["external_dimensions_cm"]
                        ),
                        expanded_dimensions_cm=(
                            _dimensions(expanded_dimensions)
                            if expanded_dimensions is not None
                            else None
                        ),
                        mass_kg=_decimal(variant["mass_kg"]),
                        capacity_l=_decimal(variant["capacity_l"]),
                        expanded_capacity_l=(
                            _decimal(expanded_capacity)
                            if expanded_capacity is not None
                            else None
                        ),
                        declared_features=_strings(variant["declared_features"]),
                        unknown_fields=_strings(variant["unknown_fields"]),
                    )
                )
            products.append(
                ProductModel(
                    product_id=_string(record["product_id"]),
                    manufacturer=_string(record["manufacturer"]),
                    brand=_string(record["brand"]),
                    model_name=_string(record["model_name"]),
                    model_number=_string(record["model_number"]),
                    generation=_string(record["generation"]),
                    variants=tuple(variants),
                    official_source_ids=_strings(record["official_source_ids"]),
                    identity_status=IdentityStatus(_string(record["identity_status"])),
                )
            )
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise AdapterError(AdapterFailure.INVALID_RESPONSE) from exc
    return tuple(products)


class RecordedProductCatalog:
    mode = "RECORDED_ONLY"
    external_action_count = 0

    def __init__(self, products: tuple[ProductModel, ...]) -> None:
        self._products = {product.product_id: product for product in products}
        if len(self._products) != len(products):
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)

    @classmethod
    def from_file(cls, path: Path) -> RecordedProductCatalog:
        return cls(load_products(path))

    def get(self, product_id: str) -> ProductModel | None:
        return self._products.get(product_id)

    def all(self) -> tuple[ProductModel, ...]:
        return tuple(
            self._products[product_id] for product_id in sorted(self._products)
        )


__all__ = ["RecordedProductCatalog", "load_products"]
