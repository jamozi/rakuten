"""Credential-free recorded Rakuten adapter and strict model identity matcher."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re
from typing import Mapping, cast
import unicodedata

from raos.adapters.decision_support_v2.errors import AdapterError, AdapterFailure
from raos.adapters.decision_support_v2.strict_json import loads_strict_json
from raos.domain.decision_support_v2.models import (
    IdentityStatus,
    OfferObservation,
    OfferStatus,
    ProductModel,
)


_ACCESSORY = re.compile(
    r"(?:cover|caster|wheel|replacement|strap|accessory|spare[ -]?part|"
    r"収納ケース|保護ケース|(?:スーツ|キャリー)ケース用(?:カバー|ケース|キャスター)?|"
    r"専用カバー|カバー|キャスター|交換|替え|ストラップ|付属品)",
    re.IGNORECASE,
)
_OLD_GENERATION = re.compile(
    r"(?:old[ -]?generation|previous[ -]?generation|旧型|旧世代|旧モデル)",
    re.IGNORECASE,
)
_SET_OR_MIXED = re.compile(
    r"(?:mixed|bundle|\bset\b|セット|2個(?:組|セット)?|新旧|旧型.*現行|現行.*旧型)",
    re.IGNORECASE,
)
_OPAQUE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
_OPAQUE_PROVIDER_REF = re.compile(r"OPAQUE-[A-Z0-9][A-Z0-9._:-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


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


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _string(value)


def _strings(value: object) -> tuple[str, ...]:
    result: list[str] = []
    for item in _list(value):
        result.append(_string(item))
    return tuple(result)


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return Decimal(value)


def _validate_opaque_ref(
    value: object, *, nullable: bool = True, provider_ref: bool = False
) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not _OPAQUE_REF.fullmatch(value):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    if provider_ref and not _OPAQUE_PROVIDER_REF.fullmatch(value):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    lowered = value.casefold()
    if (
        lowered.startswith(("http:", "https:", "javascript:", "data:"))
        or "?" in value
        or "#" in value
        or any(token in lowered for token in ("credential", "password", "secret"))
    ):
        raise AdapterError(AdapterFailure.INVALID_RESPONSE)
    return value


def normalize_identity_token(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def _contains_identity_component(title: str, component: str) -> bool:
    haystack = normalize_identity_token(title)
    needle = normalize_identity_token(component)
    if not needle:
        return False
    start = 0
    while (index := haystack.find(needle, start)) >= 0:
        before = haystack[index - 1] if index else ""
        after_index = index + len(needle)
        after = haystack[after_index] if after_index < len(haystack) else ""
        bad_before = (
            needle[0].isascii()
            and needle[0].isalnum()
            and before.isascii()
            and before.isalnum()
        )
        bad_after = (
            needle[-1].isascii()
            and needle[-1].isalnum()
            and after.isascii()
            and after.isalnum()
        )
        if not bad_before and not bad_after:
            return True
        start = index + 1
    return False


def identity_match(
    *, product: ProductModel, observed_model_number: str | None, title: str
) -> IdentityStatus:
    if _ACCESSORY.search(title):
        return IdentityStatus.REJECTED
    if _OLD_GENERATION.search(title):
        return IdentityStatus.AMBIGUOUS
    if _SET_OR_MIXED.search(title):
        return IdentityStatus.AMBIGUOUS
    if observed_model_number is None:
        return IdentityStatus.UNRESOLVED
    expected = normalize_identity_token(product.model_number)
    observed = normalize_identity_token(observed_model_number)
    if observed != expected:
        return IdentityStatus.AMBIGUOUS
    if not _contains_identity_component(title, product.model_number):
        return IdentityStatus.AMBIGUOUS
    if not _contains_identity_component(title, product.model_name):
        return IdentityStatus.AMBIGUOUS
    identity_names = {product.manufacturer, product.brand}
    if not any(_contains_identity_component(title, name) for name in identity_names):
        return IdentityStatus.AMBIGUOUS
    generation = normalize_identity_token(product.generation)
    if generation not in {"", "current", "current-2026", "current2026"}:
        if not _contains_identity_component(title, product.generation):
            return IdentityStatus.AMBIGUOUS
    return IdentityStatus.EXACT


class RecordedRakutenSearch:
    mode = "RECORDED_ONLY"
    external_action_count = 0

    def __init__(
        self,
        *,
        offers: tuple[OfferObservation, ...],
        products: Mapping[str, ProductModel],
    ) -> None:
        self._offers = offers
        self._products = dict(products)

    @classmethod
    def from_file(
        cls, path: Path, *, products: Mapping[str, ProductModel]
    ) -> RecordedRakutenSearch:
        try:
            decoded: object = loads_strict_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise AdapterError(AdapterFailure.INVALID_RESPONSE) from exc
        payload = _mapping(decoded)
        if payload.get("schema") != "RAOS_V2_RAKUTEN_RECORDED_SEARCH_2026_07_01":
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)
        expected_payload = {
            "schema",
            "version",
            "mode",
            "fixture_kind",
            "synthetic_created_at",
            "source_sha256",
            "offers",
        }
        if (
            set(payload) != expected_payload
            or payload["version"] != "2026-07-01"
            or payload["mode"] != "RECORDED_ONLY"
            or payload["fixture_kind"] != "SYNTHETIC_CONTRACT_FIXTURE"
            or not _SHA256.fullmatch(_string(payload["source_sha256"]))
        ):
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)
        offer_records = _list(payload["offers"])
        offers: list[OfferObservation] = []
        try:
            synthetic_created_at = datetime.fromisoformat(
                _string(payload["synthetic_created_at"]).replace("Z", "+00:00")
            )
            if (
                synthetic_created_at.tzinfo is None
                or synthetic_created_at.utcoffset() is None
            ):
                raise AdapterError(AdapterFailure.INVALID_RESPONSE)
            for raw_record in offer_records:
                record = _mapping(raw_record)
                if set(record) != {"offer_observation", "identity_input"}:
                    raise AdapterError(AdapterFailure.INVALID_RESPONSE)
                observation = _mapping(record["offer_observation"])
                identity_input = _mapping(record["identity_input"])
                required_observation = {
                    "schema_version",
                    "offer_id",
                    "product_id",
                    "provider",
                    "mode",
                    "item_code",
                    "shop_code",
                    "observed_at",
                    "price_jpy",
                    "availability",
                    "affiliate_url_ref",
                    "image_ref",
                    "identity_evidence",
                    "status",
                }
                if (
                    set(observation) != required_observation
                    or set(identity_input) != {"observed_model_number", "title"}
                    or observation["schema_version"] != "1.0.0"
                    or observation["provider"] != "RAKUTEN"
                    or observation["mode"] != "RECORDED_ONLY"
                ):
                    raise AdapterError(AdapterFailure.INVALID_RESPONSE)
                identity_evidence = _strings(observation["identity_evidence"])
                if not identity_evidence:
                    raise AdapterError(AdapterFailure.INVALID_RESPONSE)
                item_code = _validate_opaque_ref(observation["item_code"])
                shop_code = _validate_opaque_ref(observation["shop_code"])
                affiliate_url_ref = _validate_opaque_ref(
                    observation["affiliate_url_ref"], provider_ref=True
                )
                image_ref = _validate_opaque_ref(
                    observation["image_ref"], provider_ref=True
                )
                observed_model_number = _optional_string(
                    identity_input.get("observed_model_number")
                )
                title = _string(identity_input.get("title"))
                product_id = _string(observation["product_id"])
                recorded_status = OfferStatus(_string(observation["status"]))
                product = products.get(product_id)
                if product is None:
                    status = OfferStatus.IDENTITY_BLOCKED
                    identity = IdentityStatus.UNRESOLVED
                else:
                    identity = identity_match(
                        product=product,
                        observed_model_number=observed_model_number,
                        title=title,
                    )
                    status = (
                        recorded_status
                        if identity is IdentityStatus.EXACT
                        else OfferStatus.IDENTITY_BLOCKED
                    )
                observed_at = datetime.fromisoformat(
                    _string(observation["observed_at"]).replace("Z", "+00:00")
                )
                if (
                    observed_at.tzinfo is None
                    or observed_at.utcoffset() is None
                    or observed_at > synthetic_created_at
                ):
                    raise AdapterError(AdapterFailure.INVALID_RESPONSE)
                offers.append(
                    OfferObservation(
                        offer_id=_string(observation["offer_id"]),
                        product_id=product_id,
                        provider="RAKUTEN_RECORDED",
                        item_code=item_code,
                        shop_code=shop_code,
                        observed_at=observed_at,
                        affiliate_url_ref=affiliate_url_ref,
                        image_ref=image_ref,
                        identity_evidence=(identity.value,),
                        status=status,
                        display_price_jpy=_optional_decimal(observation["price_jpy"]),
                        in_stock=(
                            True
                            if _optional_string(observation["availability"])
                            == "IN_STOCK"
                            else None
                        ),
                    )
                )
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise AdapterError(AdapterFailure.INVALID_RESPONSE) from exc
        return cls(offers=tuple(offers), products=products)

    def search(self, request: Mapping[str, object]) -> tuple[OfferObservation, ...]:
        if set(request) != {"product_ids", "schema_version"}:
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)
        if request["schema_version"] != "2026-07-01":
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)
        product_ids = request["product_ids"]
        if isinstance(product_ids, list):
            raw_product_ids = cast("list[object]", product_ids)
        elif isinstance(product_ids, tuple):
            raw_product_ids = list(cast("tuple[object, ...]", product_ids))
        else:
            raise AdapterError(AdapterFailure.INVALID_RESPONSE)
        wanted: set[str] = set()
        for value in raw_product_ids:
            wanted.add(_string(value))
        return tuple(offer for offer in self._offers if offer.product_id in wanted)


__all__ = [
    "RecordedRakutenSearch",
    "identity_match",
    "normalize_identity_token",
]
