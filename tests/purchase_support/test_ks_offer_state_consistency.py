"""KS-019: one sales-state judgement per offer across every placement (2026-09-15 batch B).

The published bodies render each seller offer once as a panel
(``.ps-seller[data-ps-offer][data-ps-state]``) and may repeat a purchase CTA
(``a.ps-offer-link[data-raos-offer-id][data-raos-placement]``) in the top
summary, comparison table, product card and final summary. These checks read the
tracked bodies and assert that the CTA presence and target agree with the panel
state, so a "sold out / on hold" detail can never sit next to a live purchase
button for the same offer.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

from raos.application.editorial.reader_html import Element, fragment

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
CATALOG = ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
PLACEMENTS = {"top_summary", "comparison_table", "product_card", "final_summary"}
# Offers that the renderer treats as not purchasable right now.
HELD_STATES = {"SOLD_OUT", "UNAVAILABLE", "UNKNOWN"}


def _bodies() -> dict[str, Element]:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    out = {}
    for row in ledger["articles"]:
        if row.get("body_source"):
            html = (ROOT / row["body_source"]).read_text(encoding="utf-8")
            out[row["article_key"]] = fragment(re.sub(r"<!--\s*/?wp:[^>]*-->", "", html))
    return out


@pytest.fixture(scope="module")
def roots() -> dict[str, Element]:
    return _bodies()


@pytest.fixture(scope="module")
def offers() -> dict[str, dict]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {o["offer_id"]: o for o in catalog["offers"]}


def _panels(root: Element) -> dict[str, list[Element]]:
    found: dict[str, list[Element]] = defaultdict(list)
    for node in root.walk():
        offer = node.attrs.get("data-ps-offer")
        if offer and node.has("ps-seller"):
            found[offer].append(node)
    return found


def _ctas(root: Element) -> dict[str, list[Element]]:
    found: dict[str, list[Element]] = defaultdict(list)
    for node in root.find(tag="a"):
        if node.attrs.get("data-raos-cta-type") == "offer" and node.attrs.get("data-raos-offer-id"):
            found[node.attrs["data-raos-offer-id"]].append(node)
    return found


def test_cta_placements_are_known(roots: dict[str, Element]) -> None:
    unknown = [
        (key, a.attrs.get("data-raos-placement"))
        for key, root in roots.items()
        for group in _ctas(root).values()
        for a in group
        if a.attrs.get("data-raos-placement") not in PLACEMENTS
    ]
    assert unknown == []


def test_held_offers_have_no_purchase_cta_anywhere(roots: dict[str, Element]) -> None:
    """A panel that says sold out / on hold must not coexist with a purchase button for that offer."""
    problems = []
    for key, root in roots.items():
        ctas = _ctas(root)
        for offer, panels in _panels(root).items():
            held = any(
                p.attrs.get("data-ps-state") in HELD_STATES or p.find(cls="ps-unavailable")
                for p in panels
            )
            live = [
                a for a in ctas.get(offer, [])
                if a.attrs.get("data-raos-link-purpose") in {"affiliate_purchase", "merchant_purchase"}
                and not _is_listing_reference(a)
            ]
            if held and live:
                problems.append((key, offer, sorted({a.attrs.get("data-raos-placement") for a in live})))
    assert problems == []


def _is_listing_reference(anchor: Element) -> bool:
    """'楽天で見る' / '販売先で見る' links point at the listing to check current conditions, not a buy action."""
    return anchor.text().strip() in {"楽天で見る", "販売先で見る"}


def test_offer_state_is_single_valued_per_article(roots: dict[str, Element]) -> None:
    """The same offer never carries two different states or price states inside one article."""
    problems = []
    for key, root in roots.items():
        for offer, panels in _panels(root).items():
            states = {(p.attrs.get("data-ps-state"), p.attrs.get("data-ps-price-state")) for p in panels}
            if len(states) > 1:
                problems.append((key, offer, sorted(states)))
    assert problems == []


def test_cta_targets_agree_across_placements(roots: dict[str, Element]) -> None:
    """Every CTA for one offer leads to the same destination and seller."""
    problems = []
    for key, root in roots.items():
        for offer, anchors in _ctas(root).items():
            hrefs = {a.attrs.get("href") for a in anchors if not _is_listing_reference(a)}
            sellers = {a.attrs.get("data-raos-seller-id") for a in anchors}
            if len(hrefs) > 1 or len(sellers) > 1:
                problems.append((key, offer, sorted(hrefs), sorted(sellers)))
    assert problems == []


def test_cta_offers_exist_in_catalog_and_match_product(roots: dict[str, Element], offers: dict[str, dict]) -> None:
    problems = []
    for key, root in roots.items():
        for offer, anchors in _ctas(root).items():
            if offer not in offers:
                problems.append((key, offer, "missing in catalog"))
                continue
            for a in anchors:
                if a.attrs.get("data-raos-product-id") != offers[offer]["product_id"]:
                    problems.append((key, offer, "product mismatch", a.attrs.get("data-raos-product-id")))
    assert problems == []


def test_expired_price_is_not_shown_as_current(roots: dict[str, Element]) -> None:
    """Visible text never states a yen amount for an offer whose price state is EXPIRED."""
    problems = []
    for key, root in roots.items():
        for offer, panels in _panels(root).items():
            for p in panels:
                if p.attrs.get("data-ps-price-state") == "EXPIRED":
                    text = p.text()
                    if re.search(r"[0-9]{1,3}(?:,[0-9]{3})+\s*円|¥\s*[0-9]", text) and "確認期限切れ" not in text:
                        problems.append((key, offer, text[:80]))
    assert problems == []
