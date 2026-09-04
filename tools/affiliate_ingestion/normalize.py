from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

ALIASES: dict[str, tuple[str, ...]] = {
    "source_id": (
        "id",
        "program_id",
        "advertiser_id",
        "merchant_id",
        "product_id",
        "item_id",
        "transaction_id",
        "order_id",
        "code",
    ),
    "name": (
        "name",
        "program_name",
        "advertiser_name",
        "merchant_name",
        "product_name",
        "item_name",
        "title",
    ),
    "url": (
        "url",
        "affiliate_url",
        "tracking_url",
        "link_url",
        "product_url",
        "landing_url",
    ),
    "status": ("status", "state", "approval_status", "transaction_status"),
    "currency": ("currency", "currency_code"),
    "price": ("price", "unit_price", "product_price", "sales_amount", "amount"),
    "commission": (
        "commission",
        "commission_amount",
        "reward",
        "payout",
        "fee",
    ),
    "occurred_at": (
        "occurred_at",
        "transaction_at",
        "ordered_at",
        "created_at",
        "date",
        "datetime",
    ),
    "approved_at": ("approved_at", "confirmed_at", "locked_at"),
}


def _flatten_keys(record: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in record.items():
        normalized = str(key).strip().casefold().replace("-", "_").replace(" ", "_")
        result.setdefault(normalized, value)
    return result


def _first(record: Mapping[str, Any], aliases: Iterable[str]) -> Any:
    for alias in aliases:
        value = record.get(alias)
        if value not in (None, ""):
            return value
    return None


def _decimal_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    cleaned = str(value).strip().replace(",", "").replace("¥", "").replace("￥", "")
    try:
        return format(Decimal(cleaned), "f")
    except InvalidOperation, ValueError:
        return str(value)


def normalize_record(
    provider: str,
    resource: str,
    record: Mapping[str, Any],
    *,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    fetched = fetched_at or datetime.now(UTC).isoformat()
    flat = _flatten_keys(record)
    canonical: dict[str, Any] = {
        field: _first(flat, aliases) for field, aliases in ALIASES.items()
    }
    canonical["price"] = _decimal_string(canonical["price"])
    canonical["commission"] = _decimal_string(canonical["commission"])
    raw_json = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    fingerprint_seed = "\x1f".join(
        [
            provider,
            resource,
            str(canonical.get("source_id") or ""),
            str(canonical.get("url") or ""),
            raw_json,
        ]
    )
    return {
        "schema_version": 1,
        "provider": provider,
        "resource": resource,
        "fetched_at": fetched,
        "fingerprint_sha256": hashlib.sha256(
            fingerprint_seed.encode("utf-8")
        ).hexdigest(),
        **canonical,
        "raw": dict(record),
    }
