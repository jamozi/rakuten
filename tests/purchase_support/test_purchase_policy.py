from copy import deepcopy
from datetime import datetime, timezone

from raos.domain.editorial.purchase_support import budget_decision, offer_cost, select_candidates


NOW = datetime(2026, 9, 10, 6, tzinfo=timezone.utc)


def offer():
    return {
        "checked_at": "2026-09-10T05:00:00Z", "valid_until": "2026-09-11T05:00:00Z",
        "identity_verified": True, "condition": "new", "state": "AVAILABLE",
        "price_yen": 30000, "shipping_yen": 1000, "required_items_yen": 500,
        "total_scope_complete": True,
    }


def test_total_requires_every_required_cost_and_does_not_subtract_points():
    value = offer()
    value.update(points=9999, conditional_coupon=10000)
    assert offer_cost(value, NOW)["total_yen"] == 31500
    value["shipping_yen"] = None
    assert offer_cost(value, NOW) == {"state": "INCOMPLETE", "total_yen": None, "subtotal_yen": 30500}
    assert budget_decision(value, 100000, NOW) == "UNKNOWN"


def test_expiry_future_and_false_zero_never_become_budget_pass():
    for change in ({"checked_at": "2026-09-09T05:00:00Z"}, {"valid_until": "2026-09-10T05:59:59Z"},
                   {"checked_at": "2026-09-10T07:00:00Z"}, {"shipping_yen": False},
                   {"price_yen": float("nan")}, {"total_scope_complete": False},
                   {"identity_verified": False}, {"state": "UNKNOWN"}):
        value = {**offer(), **change}
        assert budget_decision(value, 100000, NOW) == "UNKNOWN"


def test_expiry_at_boundary_is_ineligible_and_zero_budget_is_real():
    assert budget_decision({**offer(), "valid_until": "2026-09-10T06:00:00Z"}, 40000, NOW) == "UNKNOWN"
    assert budget_decision(offer(), 0, NOW) == "OVER_BUDGET"
    assert budget_decision(offer(), 31500, NOW) == "WITHIN_BUDGET"


def test_reward_and_link_presence_do_not_change_use_case_recommendation():
    products = [{"product_id": "A", "use_cases": ["small"]}, {"product_id": "B", "use_cases": ["small"]}]
    changed = deepcopy(products)
    changed[0].update(reward_rate=90, affiliate_contract=True, has_link=True)
    changed[1].update(reward_rate=0, affiliate_contract=False, has_link=False)
    assert select_candidates(products, "small") == select_candidates(changed, "small") == ["A", "B"]


def test_price_changes_budget_only_not_performance_or_use_case():
    products = [{"product_id": "A", "use_cases": ["small"]}]
    assert select_candidates(products, "small") == ["A"]
    assert budget_decision(offer(), 30000, NOW) == "OVER_BUDGET"
    assert budget_decision({**offer(), "price_yen": 20000}, 30000, NOW) == "WITHIN_BUDGET"
