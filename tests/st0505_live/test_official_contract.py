"""Pinned official-contract checks for Rakuten Ichiba Item Search 20260701."""

from __future__ import annotations

from raos.adapters.rakuten_live_smoke import SecretText

from conftest import APPLICATION_MATERIAL, request


def test_format_version_two_request_preserves_required_envelope_fields() -> None:
    """`elements` must retain every envelope field validated by the smoke."""

    exact_request = request()
    query = dict(exact_request._query(SecretText(APPLICATION_MATERIAL)))

    assert query["formatVersion"] == "2"
    assert query["hits"] == "1"
    assert query["page"] == "1"
    assert query["elements"].split(",") == [
        "count",
        "page",
        "hits",
        "pageCount",
        "itemCode",
        "itemName",
        "itemPrice",
        "itemUrl",
        "shopCode",
    ]


def test_format_version_two_fixture_uses_flat_lowercase_items() -> None:
    """The pinned 20260701 formatVersion=2 shape is lowercase, flat `items`."""

    import json

    from conftest import BODY

    payload = json.loads(BODY)
    assert "items" in payload
    assert "Items" not in payload
    assert len(payload["items"]) == 1
    assert "item" not in payload["items"][0]
    assert payload["items"][0]["itemCode"] == "test-shop:item-1"
