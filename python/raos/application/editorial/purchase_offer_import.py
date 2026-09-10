"""Promote one reviewed ASP product record without exposing its private payload."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from raos.application.editorial.purchase_support import ORIGIN, https
from raos.domain.editorial.purchase_support import money, timestamp

PROVIDERS = {"a8net", "valuecommerce", "moshimo", "linkshare", "accesstrade", "afb"}
PUBLIC_FIELDS = {
    "offer_id",
    "product_id",
    "product_model",
    "seller_id",
    "seller",
    "url",
    "source_url",
    "source_urls",
    "checked_at",
    "valid_until",
    "price_yen",
    "shipping_yen",
    "required_items_yen",
    "state",
    "condition",
    "variant",
    "warranty",
    "delivery",
    "price_scope",
    "identity_verified",
    "total_scope_complete",
    "affiliate",
    "advertiser_authorized",
    "link_usage_authorized",
    "site_origin",
    "link_basis",
}


def approved_offer_from_normalized(
    record: Mapping[str, Any], review: Mapping[str, Any]
) -> dict[str, Any]:
    """Use tools.affiliate_ingestion.normalize output, requiring independent identity/rights review.

    Commission, source/account IDs and raw are never copied to the public offer.
    Provider status or a normalized URL alone never establishes link permission.
    """
    if (
        record.get("schema_version") != 1
        or record.get("provider") not in PROVIDERS
        or record.get("resource") != "products"
    ):
        raise ValueError("PURCHASE_ASP_PRODUCT_RECORD_REQUIRED")
    if (
        review.get("schema") != "RAOS_PURCHASE_ASP_REVIEW_V1"
        or review.get("source_fingerprint_sha256") != record.get("fingerprint_sha256")
        or not isinstance(record.get("fingerprint_sha256"), str)
        or len(record["fingerprint_sha256"]) != 64
    ):
        raise ValueError("PURCHASE_ASP_REVIEW_BINDING_REQUIRED")
    offer = review.get("offer")
    if (
        not isinstance(offer, dict)
        or set(offer) - PUBLIC_FIELDS
        or offer.get("url") != record.get("url")
    ):
        raise ValueError("PURCHASE_ASP_EXACT_ISSUED_LINK_REQUIRED")
    if (
        offer.get("affiliate") is not True
        or offer.get("advertiser_authorized") is not True
        or offer.get("link_usage_authorized") is not True
        or offer.get("site_origin") != ORIGIN
        or review.get("material_storage_authorized") is not True
    ):
        raise ValueError("PURCHASE_ASP_PERMISSION_REQUIRED")
    if (
        offer.get("identity_verified") is not True
        or not all(
            offer.get(k)
            for k in (
                "product_id",
                "product_model",
                "variant",
                "seller_id",
                "seller",
                "warranty",
                "link_basis",
            )
        )
        or offer.get("warranty") == "UNKNOWN"
    ):
        raise ValueError("PURCHASE_ASP_IDENTITY_REVIEW_REQUIRED")
    if (
        not https(offer.get("url"))
        or not https(offer.get("source_url"))
        or not timestamp(offer.get("checked_at"))
        or not timestamp(offer.get("valid_until"))
    ):
        raise ValueError("PURCHASE_ASP_SOURCE_DATE_REQUIRED")
    for key in ("price_yen", "shipping_yen", "required_items_yen"):
        if offer.get(key) is not None and not money(offer[key]):
            raise ValueError("PURCHASE_ASP_MONEY_INVALID")
    return dict(offer)
