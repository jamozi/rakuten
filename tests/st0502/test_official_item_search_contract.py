"""Pinned official-contract assertions for the synthetic ST-0502 fixture."""

from __future__ import annotations

import json

from conftest import RAW_BODY, item_search_request


def test_20260701_format_version_two_fixture_is_lowercase_and_flat() -> None:
    payload = json.loads(RAW_BODY)

    assert item_search_request().format_version == 2
    assert "items" in payload
    assert "Items" not in payload
    assert len(payload["items"]) == 1
    assert "item" not in payload["items"][0]
    assert "Item" not in payload["items"][0]
    assert payload["items"][0]["itemCode"] == "test-shop:item-1"


def test_20260701_fixture_retains_requested_envelope_fields() -> None:
    payload = json.loads(RAW_BODY)

    assert payload["count"] == 1
    assert payload["page"] == 1
    assert payload["hits"] == 1
    assert payload["pageCount"] == 1
