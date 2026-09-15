"""Dated listing prices do not turn unknown availability into purchase totals."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

import pytest

from raos.domain.editorial.purchase_support import budget_decision, reference_price
from raos.application.editorial.purchase_support import reference_price_markup

NOW = datetime(2026, 9, 13, 5, tzinfo=timezone.utc)
PRODUCT = {"product_id": "p1", "exact_model": "MODEL-BLACK"}


def observation():
    offer = {
        "product_id": "p1",
        "product_model": "MODEL-BLACK",
        "variant": "Black base unit",
        "variant_id": "black-base",
        "identity_verified": True,
        "condition": "UNKNOWN",
        "state": "SOLD_OUT",
        "merchant_url": "https://example.com/item/",
        "seller": "Seller",
        "seller_id": "seller-1",
        "price_yen": None,
        "shipping_yen": None,
        "required_items_yen": None,
        "total_scope_complete": False,
        "checked_at": NOW.isoformat(),
        "valid_until": (NOW + timedelta(days=1)).isoformat(),
    }
    offer["reference_price"] = {
        "schema": "RAOS_REFERENCE_PRICE_V1",
        "verified": True,
        "product_id": "p1",
        "exact_model": "MODEL-BLACK",
        "variant": offer["variant"],
        "variant_id": offer["variant_id"],
        "amount_yen": 29800,
        "currency": "JPY",
        "tax_included": True,
        "scope": "base_unit",
        "pricing_basis": "listed_sale_price",
        "source_url": offer["merchant_url"],
        "source_locator": "selected black / base-unit price",
        "evidence_sha256": "a" * 64,
        "checked_at": offer["checked_at"],
        "valid_until": offer["valid_until"],
    }
    return offer


@pytest.mark.parametrize("state", ["AVAILABLE", "UNKNOWN", "SOLD_OUT", "PREORDER"])
def test_dated_price_does_not_promote_unknown_condition_or_budget(state):
    offer = observation()
    offer["state"] = state
    original = deepcopy(offer)
    assert reference_price(offer, PRODUCT, NOW)["amount_yen"] == 29800
    assert budget_decision(offer, 50000, NOW) == "UNKNOWN"
    assert offer == original
    html = reference_price_markup(PRODUCT, offer, NOW)
    assert "29,800円" not in html and ">29800<" not in html
    assert "data-ps-reference-price" in html


@pytest.mark.parametrize(
    "key,value",
    [
        ("amount_yen", "29800"),
        ("amount_yen", 29800.5),
        ("amount_yen", 0),
        ("amount_yen", True),
        ("amount_yen", -1),
        ("amount_yen", None),
        ("product_id", "another"),
        ("exact_model", "MODEL-WHITE"),
        ("variant_id", "black-rack"),
        ("variant", "White base unit"),
        ("currency", "USD"),
        ("tax_included", False),
        ("scope", "bundle"),
        ("pricing_basis", "after_coupon"),
        ("source_url", "https://other.com/"),
        ("source_locator", ""),
        ("evidence_sha256", ""),
        ("verified", False),
        ("checked_at", "2026-09-13"),
        ("valid_until", "invalid"),
    ],
)
def test_unverified_or_mismatched_reference_never_displays(key, value):
    offer = observation()
    offer["reference_price"][key] = value
    assert reference_price(offer, PRODUCT, NOW) is None
    assert "data-ps-reference-price" not in reference_price_markup(PRODUCT, offer, NOW)


def test_reference_expiry_and_future_clock_boundary():
    offer = observation()
    assert reference_price(offer, PRODUCT, NOW - timedelta(microseconds=1)) is None
    assert reference_price(offer, PRODUCT, NOW + timedelta(days=1, microseconds=-1))
    assert reference_price(offer, PRODUCT, NOW + timedelta(days=1)) is None
    offer["reference_price"]["valid_until"] = (NOW + timedelta(hours=2)).isoformat()
    assert reference_price(offer, PRODUCT, NOW + timedelta(hours=2)) is None
    offer["reference_price"]["valid_until"] = (NOW + timedelta(days=5)).isoformat()
    assert reference_price(offer, PRODUCT, NOW + timedelta(days=1)) is None


def test_reference_browser_validation_uses_same_deadline(tmp_path):
    root = Path(__file__).resolve().parents[2]
    js = (
        root
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/purchase-support.js"
    )
    offer = observation()
    ref = {
        **offer["reference_price"],
        "seller": offer["seller"],
        "seller_id": offer["seller_id"],
    }
    data = tmp_path / "reference.json"
    data.write_text(json.dumps(ref))
    result = subprocess.run(
        [
            "node",
            "-e",
            """
const assert=require('node:assert/strict');
const context={module:{exports:{}}};
require('node:vm').runInNewContext(require('node:fs').readFileSync(process.argv[1],'utf8'),context);
const api=context.module.exports, ref=require(process.argv[2]);
const now=Date.parse(ref.checked_at), day=86400000;
assert.match(api.referencePricePresentation(ref,now).text,/29,800円/);
assert.equal(api.referencePricePresentation(ref,now-1).state,'UNKNOWN');
assert.equal(api.referencePricePresentation(ref,now+day-1).state,'CURRENT_REFERENCE');
assert.equal(api.referencePricePresentation(ref,now+day).state,'EXPIRED');
assert.doesNotMatch(api.referencePricePresentation(ref,now+day).text,/29,800/);
for(const value of ['29800',0,-1,NaN,true,29800.5]) assert.equal(api.referencePricePresentation({...ref,amount_yen:value},now).state,'UNKNOWN');
assert.equal(api.referencePricePresentation({...ref,valid_until:new Date(now+1000).toISOString()},now+1000).state,'EXPIRED');
assert.equal(api.referencePricePresentation({...ref,valid_until:new Date(now+day*3).toISOString()},now+day).state,'EXPIRED');
""",
            str(js),
            str(data),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    browser = subprocess.run(
        [
            "node",
            str(root / "tests/purchase_support/reference_price_browser.mjs"),
            str(js),
            str(data),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert browser.returncode == 0, browser.stdout + browser.stderr


def test_unavailable_used_or_wrong_offer_and_private_fields_stay_out():
    for changes in [
        {"condition": "used"},
        {"state": "UNAVAILABLE"},
        {"product_id": "another"},
        {"product_model": "OTHER"},
        {"identity_verified": False},
    ]:
        offer = {**observation(), **changes}
        assert reference_price(offer, PRODUCT, NOW) is None
    offer = observation()
    offer["reference_price"]["owner_private_note"] = "not-for-public-output"
    ref = reference_price(offer, PRODUCT, NOW)
    assert "owner_private_note" not in ref
