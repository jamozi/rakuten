from __future__ import annotations

from datetime import datetime
from typing import Any

from scripts import build_st0205_synthetic_data as generator


def test_bundle_covers_all_13_domains_once_or_more(bundle: dict[str, Any]) -> None:
    assert bundle["domain_count"] == 13
    assert bundle["fixture_count"] == len(generator.FIXTURE_SCENARIOS) == 18
    assert {fixture["schema_domain"] for fixture in bundle["fixtures"]} == set(
        generator.DOMAIN_ORDER
    )


def test_time_values_are_timezone_aware(bundle: dict[str, Any]) -> None:
    observed: list[datetime] = []
    for fixture in bundle["fixtures"]:
        for key, value in fixture["payload"].items():
            if key.endswith("_at") and value is not None:
                parsed = datetime.fromisoformat(value)
                assert parsed.tzinfo is not None
                observed.append(parsed)
    assert observed


def test_currency_large_value_and_jst_are_present(
    fixtures_by_pair: dict[tuple[str, str], dict[str, Any]],
) -> None:
    catalog = fixtures_by_pair[("catalog", "unicode-large-jpy")]["payload"]
    finance = fixtures_by_pair[("finance", "currency-large")]["payload"]
    portfolio = fixtures_by_pair[("portfolio", "jst")]["payload"]
    assert {catalog["currency"], finance["currency"]} == {"JPY", "USD"}
    assert catalog["amount_minor"] == finance["amount_minor"] == 9_007_199_254_740_991
    assert portfolio["timezone"] == "Asia/Tokyo"
    assert portfolio["locale"] == "ja-JP"


def test_locale_and_unicode_are_preserved(
    fixtures_by_pair: dict[tuple[str, str], dict[str, Any]],
) -> None:
    values = [
        fixtures_by_pair[("catalog", "unicode-large-jpy")]["payload"]["label"],
        fixtures_by_pair[("editorial", "unicode-locale")]["payload"]["title"],
        fixtures_by_pair[("readmodel", "unicode-locale")]["payload"]["headline"],
    ]
    assert all(any(ord(character) > 127 for character in value) for value in values)
    assert all("🧪" in value for value in values)


def test_dst_fold_represents_two_distinct_instants(
    fixtures_by_pair: dict[tuple[str, str], dict[str, Any]],
) -> None:
    before = fixtures_by_pair[("freshness", "dst-before")]["payload"]
    after = fixtures_by_pair[("freshness", "dst-after")]["payload"]
    before_time = datetime.fromisoformat(before["observed_at"])
    after_time = datetime.fromisoformat(after["observed_at"])
    assert before_time.replace(tzinfo=None) == after_time.replace(tzinfo=None)
    assert before_time.utcoffset() != after_time.utcoffset()
    assert before_time.timestamp() != after_time.timestamp()


def test_duplicate_delivery_has_identical_logical_payload(
    fixtures_by_pair: dict[tuple[str, str], dict[str, Any]],
) -> None:
    original = fixtures_by_pair[("ops", "duplicate-original")]
    replay = fixtures_by_pair[("ops", "duplicate-replay")]
    assert original["fixture_id"] != replay["fixture_id"]
    assert original["payload"] == replay["payload"]


def test_out_of_order_delivery_is_encoded_in_bundle_order(
    bundle: dict[str, Any],
    fixtures_by_pair: dict[tuple[str, str], dict[str, Any]],
) -> None:
    pairs = [(row["schema_domain"], row["scenario"]) for row in bundle["fixtures"]]
    later_pair = ("freshness", "out-of-order-later")
    earlier_pair = ("freshness", "out-of-order-earlier")
    assert pairs.index(later_pair) < pairs.index(earlier_pair)
    later = fixtures_by_pair[later_pair]["payload"]
    earlier = fixtures_by_pair[earlier_pair]["payload"]
    assert later["logical_event_id"] == earlier["logical_event_id"]
    assert later["sequence_no"] == 2
    assert earlier["sequence_no"] == 1
    assert datetime.fromisoformat(later["observed_at"]) > datetime.fromisoformat(
        earlier["observed_at"]
    )


def test_scenario_dimension_catalog_is_exact(bundle: dict[str, Any]) -> None:
    assert tuple(bundle["scenario_dimensions"]) == generator.SCENARIO_DIMENSIONS
