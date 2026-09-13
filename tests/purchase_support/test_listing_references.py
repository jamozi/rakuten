"""A rights-reviewed product image cannot silently become a purchase-price claim."""

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from raos.application.editorial.purchase_support import (
    media_allowed,
    resolve_product_media,
)
from raos.domain.editorial.purchase_support import budget_decision, resolve_offer

ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)


def inputs():
    catalog = json.loads(
        (
            ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
        ).read_text()
    )
    product = next(
        p for p in catalog["products"] if p["product_id"] == "PRD-THANKO-TK-MDW22W"
    )
    return catalog, product


def test_sold_out_image_is_a_listing_reference_without_new_price_or_budget():
    catalog, product = inputs()
    offer = next(
        o for o in catalog["offers"] if o["product_id"] == product["product_id"]
    )
    assert offer["condition"] == "UNKNOWN" and offer["state"] == "SOLD_OUT"
    assert media_allowed(product, catalog)
    assert resolve_offer(offer)["href"] is None
    assert (
        budget_decision(offer, 50000, datetime(2026, 9, 13, 5, tzinfo=timezone.utc))
        == "UNKNOWN"
    )


@pytest.mark.parametrize(
    "change",
    ["wrong_seller", "wrong_identity", "missing_review", "unavailable_listing", "used"],
)
def test_listing_media_requires_the_exact_reviewed_listing(change):
    catalog, product = inputs()
    offer = next(
        o for o in catalog["offers"] if o["product_id"] == product["product_id"]
    )
    if change == "wrong_seller":
        offer["merchant_url"] = "https://item.rakuten.co.jp/another/shop/"
    if change == "wrong_identity":
        offer["identity_verified"] = False
    if change == "missing_review":
        product["image_review"]["visual_identity_verified"] = False
    if change == "unavailable_listing":
        offer["state"] = "UNAVAILABLE"
    if change == "used":
        offer["condition"] = "used"
    assert not media_allowed(product, catalog)


def test_listing_review_cannot_be_rebound_to_another_media_seller():
    catalog, product = inputs()
    product["image_review"]["listing_url"] = "https://item.rakuten.co.jp/another/shop/"
    records = json.loads((THEME / "assets/rakuten-product-media.json").read_text())
    with pytest.raises(ValueError, match="PURCHASE_MEDIA_LISTING_REVIEW_REQUIRED"):
        resolve_product_media(
            catalog,
            records,
            (THEME / "assets/images/roomba-mini-official.jpg").read_bytes(),
        )


def test_curated_scope_keeps_four_identities_and_rejects_duplicate_or_missing_anchor():
    from raos.application.editorial.purchase_support import compile_articles

    catalog, _ = inputs()
    templates = {
        p.stem: p.read_text()
        for p in (ROOT / "changes/reader-purchase-support-v1/articles").glob("*.html")
    }
    guides = json.loads(
        (
            ROOT / "changes/editorial-portfolio-v3/local-reader-guides.v1.json"
        ).read_text()
    )
    article = next(a for a in catalog["articles"] if a["kind"] == "curated_comparison")
    assert len(article["product_ids"]) == 4 and article["post_id"] is None
    article["product_ids"].append(article["product_ids"][0])
    with pytest.raises(ValueError, match="PURCHASE_CURATED_SCOPE_INVALID"):
        compile_articles(catalog, templates, guides)
    article["product_ids"].pop()
    article["commerce_anchor"] = "nonexistent-slot"
    with pytest.raises(ValueError, match="PURCHASE_CURATED_ANCHOR_REQUIRED"):
        compile_articles(catalog, templates, guides)


def test_guide_slots_preserve_model_identity_and_reject_duplicates():
    from raos.application.editorial.purchase_support import bind_guide_purchase_slots

    catalog, _ = inputs()
    article = dict(
        next(
            a for a in catalog["articles"] if a["slug"] == "dishwasher-detergent-guide"
        )
    )
    product = next(
        p for p in catalog["products"] if p["product_id"] == "PRD-PANASONIC-NP-TMLK1"
    )
    article["purchase_slots"] = [
        {"product_id": product["product_id"], "position": "after_identity"}
    ]
    body = (
        '<section class="ps-guide-model" id="'
        + product["anchor"]
        + '"><h3>SOLOTA</h3><p>型番の手順</p></section>'
    )
    now = datetime(2026, 9, 13, 5, tzinfo=timezone.utc)
    rendered, bindings, media = bind_guide_purchase_slots(
        body, article, catalog, "test-snapshot", None, now
    )
    assert "型番の手順" in rendered and "ps-guide-purchase" in rendered
    assert all(b["product_id"] == product["product_id"] for b in bindings)
    assert media == {}
    article["purchase_slots"] *= 2
    with pytest.raises(ValueError, match="PURCHASE_GUIDE_SLOT_DUPLICATE"):
        bind_guide_purchase_slots(body, article, catalog, "test-snapshot", None, now)
    article["purchase_slots"].pop()
    with pytest.raises(ValueError, match="PURCHASE_GUIDE_SLOT_MODEL_REQUIRED"):
        bind_guide_purchase_slots(
            body.replace(product["anchor"], "other-model"),
            article,
            catalog,
            "test-snapshot",
            None,
            now,
        )
