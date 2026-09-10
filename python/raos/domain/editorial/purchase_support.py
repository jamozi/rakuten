"""Reader cost decisions, kept separate from product performance and finance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from math import isfinite
from typing import Any, TypeGuard


PLACEMENTS = ("top_summary", "comparison_table", "product_card", "final_summary")
MAX_PRICE_AGE = timedelta(hours=24)
COST_FIELDS = ("price_yen", "shipping_yen", "required_items_yen")
POLICY = {
    "schema": "RAOS_READER_PURCHASE_POLICY_V1",
    "performance_excludes": [
        "price",
        "points",
        "affiliate_reward_rate",
        "advertising_contract",
        "link_availability",
    ],
    "recommendation_excludes": [
        "affiliate_reward_rate",
        "advertising_contract",
        "link_availability",
        "rakuten_availability",
    ],
    "purchase_decision_inputs": [
        "use_case",
        "purchase_total",
        "running_cost",
        "delivery",
        "warranty",
    ],
    "unknown_is_zero": False,
    "maximum_price_age_hours": 24,
    "conditional_points_and_coupons_subtracted": False,
}


def timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


def money(value: object) -> TypeGuard[int | float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and 0 <= value <= 1_000_000_000
    )


def offer_cost(offer: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    """Return a subtotal even when a current, complete total is unavailable."""
    amounts = [offer.get(key) for key in COST_FIELDS]
    known = [value for value in amounts if money(value)]
    result = {
        "state": "INCOMPLETE",
        "total_yen": None,
        "subtotal_yen": sum(known) if known else None,
    }
    checked, deadline = (
        timestamp(offer.get("checked_at")),
        timestamp(offer.get("valid_until")),
    )
    if not checked or not deadline or now.tzinfo is None or checked > now:
        return {**result, "state": "UNKNOWN"}
    if deadline <= checked or now >= min(deadline, checked + MAX_PRICE_AGE):
        return {**result, "state": "EXPIRED"}
    if (
        offer.get("identity_verified") is not True
        or offer.get("state") != "AVAILABLE"
        or offer.get("condition") != "new"
    ):
        return {**result, "state": "UNKNOWN"}
    if (
        not all(money(value) for value in amounts)
        or offer.get("total_scope_complete") is not True
    ):
        return result
    return {"state": "CURRENT", "total_yen": sum(known), "subtotal_yen": sum(known)}


def budget_decision(offer: Mapping[str, Any], budget: object, now: datetime) -> str:
    if not money(budget):
        return "UNKNOWN"
    total = offer_cost(offer, now)["total_yen"]
    return (
        "UNKNOWN"
        if total is None
        else "WITHIN_BUDGET"
        if total <= budget
        else "OVER_BUDGET"
    )


def select_candidates(
    products: Sequence[Mapping[str, Any]], use_case: str
) -> list[str]:
    """Stable editorial order; no reward, price or link field is consulted."""
    return [
        str(p["product_id"])
        for p in products
        if not use_case or use_case in p.get("use_cases", [])
    ]
