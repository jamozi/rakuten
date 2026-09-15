"""Read-only maintenance queue for the reader purchase-support catalog.

maintenance_report lists what needs re-checking on a given JST date. It is a pure
function: it fetches no URL, writes no file and does not change the catalog.

What it does not measure:
- reachability of any URL (every target is NOT_CHECKED);
- current prices or stock (the re-fetch mechanism is an owner decision);
- whether a recorded value is still correct (only dates, states and the
  installation restatement check are read);
- a spec age limit, until the interval is decided (spec_max_age_days=None).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

from raos.application.editorial.purchase_support import (
    JST,
    UNSETTLED_FACT_STATES,
    installation_consistency_mismatches,
)

SCHEMA = "RAOS_READER_PURCHASE_SUPPORT_MAINTENANCE_REPORT_V1"
NOT_MEASURED = (
    "対象URLへの到達可否（すべて NOT_CHECKED。取得していない）",
    "販売価格・在庫の再取得（方式はオーナー判断待ち。取得していない）",
    "記録された値の正誤（日付・状態・寸法の転記一致だけを見る）",
    "扉・余白の寸法が、同じ文中に既にある別の数値へ変わった場合の不一致",
)


def _date_on(value: object) -> date | None:
    """A YYYY-MM-DD string as recorded, or an offset datetime as its JST date."""
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(JST).date()


def _text(value: object) -> str:
    return "" if value is None else str(value)


def maintenance_report(
    catalog: Mapping[str, Any],
    *,
    as_of: date,
    spec_max_age_days: int | None,
) -> dict[str, Any]:
    """Build a deterministic report of overdue, unsettled, stale and expired items.

    - overdue_research_issues: status other than RESOLVED and next_check_on
      before as_of.
    - unsettled_facts: facts and guide_facts whose state is UNKNOWN or CONFLICT.
    - stale_spec_facts: facts and guide_facts whose checked_at is before
      as_of minus spec_max_age_days; empty with interval_undecided when None.
    - expired_offers: valid_until converted to a JST date and before as_of; an
      offer whose deadline falls later on as_of itself is not counted.
    - target_urls: research target_url and offer source_url / source_urls only;
      url, merchant_url and affiliate_url are not listed.
    - dimension_mismatches: installation_consistency_mismatches per product.
    - unreadable_dates: dates that could not be read, so were not compared.
    """
    if not isinstance(as_of, date) or isinstance(as_of, datetime):
        raise ValueError("MAINTENANCE_AS_OF_INVALID")
    if spec_max_age_days is not None and (
        isinstance(spec_max_age_days, bool)
        or not isinstance(spec_max_age_days, int)
        or spec_max_age_days < 0
    ):
        raise ValueError("MAINTENANCE_SPEC_MAX_AGE_INVALID")
    products = sorted(
        catalog.get("products", []), key=lambda p: _text(p.get("product_id"))
    )
    offers = sorted(catalog.get("offers", []), key=lambda o: _text(o.get("offer_id")))
    issues = sorted(
        catalog.get("research_issues", []), key=lambda i: _text(i.get("issue_id"))
    )
    unreadable: list[dict[str, Any]] = []

    overdue: list[dict[str, Any]] = []
    for issue in issues:
        if issue.get("status") == "RESOLVED":
            continue
        planned = _date_on(issue.get("next_check_on"))
        if planned is None:
            unreadable.append(
                {
                    "kind": "research_issues",
                    "id": issue.get("issue_id"),
                    "name": issue.get("topic"),
                    "field": "next_check_on",
                    "value": issue.get("next_check_on"),
                }
            )
            continue
        if planned < as_of:
            reason = issue.get("unknown_reason")
            overdue.append(
                {
                    "issue_id": issue.get("issue_id"),
                    "product_id": issue.get("product_id"),
                    "status": issue.get("status"),
                    "next_check_on": issue.get("next_check_on"),
                    "days_overdue": (as_of - planned).days,
                    "target_url": issue.get("target_url"),
                    "owner": reason.get("owner") if isinstance(reason, dict) else None,
                }
            )
    overdue.sort(key=lambda r: (_text(r["next_check_on"]), _text(r["issue_id"])))

    records: list[dict[str, Any]] = []
    for product in products:
        for source, name_key in (("facts", "label"), ("guide_facts", "field")):
            for record in product.get(source, []) or []:
                records.append(
                    {
                        "product_id": product.get("product_id"),
                        "source": source,
                        "name": record.get(name_key),
                        "state": record.get("state"),
                        "checked_at": record.get("checked_at"),
                    }
                )
    records.sort(
        key=lambda r: (
            _text(r["product_id"]),
            r["source"],
            _text(r["name"]),
            _text(r["checked_at"]),
            _text(r["state"]),
        )
    )
    unsettled = [r for r in records if r["state"] in UNSETTLED_FACT_STATES]

    stale_items: list[dict[str, Any]] = []
    cutoff = (
        None if spec_max_age_days is None else as_of - timedelta(days=spec_max_age_days)
    )
    for record in records:
        checked = _date_on(record["checked_at"])
        if checked is None:
            unreadable.append(
                {
                    "kind": record["source"],
                    "id": record["product_id"],
                    "name": record["name"],
                    "field": "checked_at",
                    "value": record["checked_at"],
                }
            )
            continue
        if cutoff is not None and checked < cutoff:
            stale_items.append({**record, "age_days": (as_of - checked).days})

    expired_ids: list[str] = []
    targets: dict[str, set[str]] = {}
    for issue in issues:
        url = issue.get("target_url")
        if isinstance(url, str) and url:
            targets.setdefault(url, set()).add(
                "research:" + _text(issue.get("issue_id"))
            )
    for offer in offers:
        deadline = _date_on(offer.get("valid_until"))
        if deadline is None:
            unreadable.append(
                {
                    "kind": "offers",
                    "id": offer.get("offer_id"),
                    "name": offer.get("seller_id"),
                    "field": "valid_until",
                    "value": offer.get("valid_until"),
                }
            )
        elif deadline < as_of:
            expired_ids.append(_text(offer.get("offer_id")))
        urls = [offer.get("source_url"), *(offer.get("source_urls") or [])]
        for url in urls:
            if isinstance(url, str) and url:
                targets.setdefault(url, set()).add(
                    "offer:" + _text(offer.get("offer_id"))
                )

    dimension_mismatches = [
        row
        for product in products
        for row in installation_consistency_mismatches(product)
    ]
    unreadable.sort(
        key=lambda r: (
            r["kind"],
            _text(r["id"]),
            _text(r["name"]),
            r["field"],
            _text(r["value"]),
        )
    )
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": as_of.isoformat(),
        "date_basis": "JST (+09:00)",
        "overdue_research_issues": overdue,
        "unsettled_facts": unsettled,
        "stale_spec_facts": {
            "spec_max_age_days": spec_max_age_days,
            "interval_undecided": spec_max_age_days is None,
            "checked_before": None if cutoff is None else cutoff.isoformat(),
            "items": stale_items,
        },
        "expired_offers": {
            "count": len(expired_ids),
            "offer_ids": sorted(expired_ids),
            "refetch_mechanism": "OWNER_DECISION_PENDING",
            "fetched": False,
        },
        "target_urls": [
            {"url": url, "reachability": "NOT_CHECKED", "referenced_by": sorted(refs)}
            for url, refs in sorted(targets.items())
        ],
        "dimension_mismatches": dimension_mismatches,
        "unreadable_dates": unreadable,
        "not_measured": list(NOT_MEASURED),
    }
    report["counts"] = {
        "overdue_research_issues": len(overdue),
        "unsettled_facts": len(unsettled),
        "stale_spec_facts": len(stale_items),
        "expired_offers": len(expired_ids),
        "target_urls": len(report["target_urls"]),
        "dimension_mismatches": len(dimension_mismatches),
        "unreadable_dates": len(unreadable),
    }
    return report
