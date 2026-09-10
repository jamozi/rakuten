"""Regression coverage for URL selection, partial evidence and semantic anchors."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from raos.application.editorial.purchase_support import (
    cta,
    compile_articles,
    validate_catalog,
)
from raos.domain.editorial.purchase_support import resolve_offer, offer_states
from scripts.raos_public_acceptance import Page, purchase_findings

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "changes/reader-purchase-support-v1"
NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


def offer():
    catalog = json.loads((BASE / "purchase-support.v1.json").read_text())
    return deepcopy(catalog["offers"][0])


def test_price_shipping_installation_and_warranty_do_not_remove_exact_destination():
    value = offer()
    value.update(shipping_yen=None, warranty="UNKNOWN", installation_state="UNKNOWN")
    decision = resolve_offer(value)
    assert decision["href"] == value.get("merchant_url", value.get("url"))
    assert decision["link_purpose"] == "merchant_purchase"
    states = offer_states(value, NOW)
    assert states["price_state"] == "EXPIRED"
    assert (
        states["shipping_state"]
        == states["warranty_state"]
        == states["installation_state"]
        == "UNKNOWN"
    )
    assert states["identity_state"] == "VERIFIED"


@pytest.mark.parametrize(
    "mutation",
    [
        {"identity_verified": False},
        {"variant": ""},
        {"state": "SOLD_OUT"},
        {"condition": "used"},
    ],
)
def test_identity_and_unavailable_offer_remain_blocked(mutation):
    assert resolve_offer({**offer(), **mutation})["href"] is None


def test_affiliate_is_exact_issued_url_and_requires_rights_separate_from_spec():
    value = offer()
    value.update(
        affiliate_ready=True,
        affiliate_url="https://affiliate.example/issued-exact",
        advertiser_authorized=True,
        link_usage_authorized=True,
        site_origin="https://kurashinoshirube.com",
        link_basis="reviewed issued URL",
    )
    result = resolve_offer(value)
    assert result["href"] == value["affiliate_url"]
    assert result["link_purpose"] == "affiliate_purchase"
    value["link_usage_authorized"] = False
    assert resolve_offer(value)["href"] == value.get("merchant_url", value.get("url"))
    assert resolve_offer(value)["affiliate_ready"] is False


def test_same_offer_resolves_identically_in_two_articles():
    value = offer()
    first, a = cta(
        value, {"article_id": "article-a", "post_id": 1}, "snapshot", "top_summary"
    )
    second, b = cta(
        value, {"article_id": "article-b", "post_id": 2}, "snapshot", "product_card"
    )
    assert a["href"] == b["href"] and a["offer_id"] == b["offer_id"]
    assert a["cta_id"] != b["cta_id"] and first != second


def test_unknown_stock_is_not_identity_failure_and_does_not_claim_available():
    value = {**offer(), "state": "UNKNOWN"}
    assert resolve_offer(value)["href"] == value["merchant_url"]
    assert offer_states(value, NOW)["purchasability_state"] == "UNKNOWN"


def test_product_owner_and_affiliate_rel_are_verified_in_public_html():
    value = offer()
    value.update(
        affiliate_ready=True,
        affiliate_url="https://affiliate.example/issued",
        advertiser_authorized=True,
        link_usage_authorized=True,
        site_origin="https://kurashinoshirube.com",
    )
    html, binding = cta(
        value, {"article_id": "article-a", "post_id": 1}, "snapshot", "product_card"
    )
    assert "PURCHASE_CTA_PRODUCT_MISMATCH" in purchase_findings(
        Page('<article data-ps-product="wrong">' + html + "</article>"), [binding]
    )
    assert "PURCHASE_AFFILIATE_REL_MISSING" in purchase_findings(
        Page(html.replace("sponsored nofollow", "noopener")), [binding]
    )
    assert "PURCHASE_HREF_MISMATCH" in purchase_findings(
        Page(html.replace(value["affiliate_url"], value["merchant_url"])), [binding]
    )


def test_legacy_top_placement_is_detected_without_relabelling_its_snapshot():
    html = '<section class="raos-decision-summary"><a data-raos-cta-type="offer" data-raos-placement="final_summary" href="https://seller.example/">購入条件</a></section><article class="raos-product-card">商品</article>'
    assert "PURCHASE_PLACEMENT_MISMATCH" in purchase_findings(Page(html))


def test_duplicate_product_variant_seller_registry_is_rejected():
    catalog = json.loads((BASE / "purchase-support.v1.json").read_text())
    duplicate = {**catalog["offers"][0], "offer_id": "different-id"}
    catalog["offers"].append(duplicate)
    with pytest.raises(ValueError, match="PURCHASE_DUPLICATE_SELLER_VARIANT"):
        validate_catalog(catalog)


@pytest.mark.parametrize(
    "target,code",
    [
        ('<span id="x-purchase"></span>', "PURCHASE_ANCHOR_NOT_OFFER_SECTION"),
        (
            '<section id="x-purchase" class="ps-product-offers" data-ps-product="other">販売先</section>',
            "PURCHASE_ANCHOR_PRODUCT_MISMATCH",
        ),
    ],
)
def test_id_presence_is_not_semantic_purchase_success(target, code):
    html = '<a data-raos-product-id="P" href="#x-purchase">購入条件へ</a>' + target
    assert code in purchase_findings(Page(html))


def test_all_generated_purchase_aliases_reach_same_product_section():
    catalog = json.loads((BASE / "purchase-support.v1.json").read_text())
    articles, _ = compile_articles(
        catalog,
        {p.stem: p.read_text() for p in (BASE / "articles").glob("*.html")},
        json.loads(
            (
                ROOT / "changes/editorial-portfolio-v3/local-reader-guides.v1.json"
            ).read_text()
        ),
    )
    for article in catalog["articles"]:
        if article["post_id"] in (30, 83, 41):
            assert purchase_findings(Page(articles[article["slug"]])) == [], article[
                "slug"
            ]


def test_public_readback_rejects_href_placement_and_missing_cta():
    value = offer()
    html, binding = cta(
        value, {"article_id": "article-a", "post_id": 1}, "snapshot", "top_summary"
    )
    html = '<section id="ps-choose">' + html + "</section>"
    assert purchase_findings(Page(html), [binding]) == []
    assert "PURCHASE_HREF_MISMATCH" in purchase_findings(
        Page(html.replace(binding["href"], "https://wrong.example/")), [binding]
    )
    assert "PURCHASE_PLACEMENT_MISMATCH" in purchase_findings(
        Page(
            html.replace(
                'data-raos-placement="top_summary"',
                'data-raos-placement="final_summary"',
            )
        ),
        [binding],
    )
    assert "PURCHASE_CTA_MISSING_OR_DUPLICATE" in purchase_findings(Page(""), [binding])


def test_public_cli_uses_frozen_expectation_and_returns_failure_without_printing_urls(
    tmp_path, capsys
):
    from scripts import raos_public_acceptance as audit

    link, binding = cta(
        offer(), {"article_id": "article-a", "post_id": 1}, "snapshot", "top_summary"
    )
    html = (
        '<html><head><title>Comparison</title><meta name="description" content="Model comparison"><link rel="canonical" href="https://kurashinoshirube.com/article-a/"></head><body><h1>Comparison</h1><div data-raos-purchase-support="v1">'
        + link
        + "</div></body></html>"
    )
    observation = {
        "path": "/article-a/",
        "status": 200,
        "final_url": "https://kurashinoshirube.com/article-a/",
        "full_html": True,
        "html": html,
        "headers": {},
    }
    batch = {
        "schema": "RAOSAnonymousPageBatchV1",
        "expected_paths": ["/article-a/"],
        "observations": [observation],
    }
    runtime = {
        "schema": "RAOS_PURCHASE_ARTICLE_RUNTIME_V1",
        "articles": [{"slug": "article-a", "bindings": [binding]}],
    }
    source, expected = tmp_path / "public.json", tmp_path / "expected.json"
    expected.write_text(json.dumps(runtime))
    source.write_text(json.dumps(batch))
    argv = ["--input", str(source), "--purchase-runtime", str(expected)]
    assert audit.main(argv) == 0
    assert binding["href"] not in capsys.readouterr().out
    observation["html"] = html.replace(binding["href"], "https://wrong.example/item")
    source.write_text(json.dumps(batch))
    assert audit.main(argv) == 1
    assert "PURCHASE_HREF_MISMATCH" in capsys.readouterr().out
    runtime["articles"] = []
    expected.write_text(json.dumps(runtime))
    assert audit.main(argv) == 2


def test_issued_affiliate_on_new_host_still_requires_visible_disclosure():
    from scripts.raos_public_acceptance import assess

    value = offer()
    value.update(
        affiliate_ready=True,
        affiliate_url="https://affiliate.example/issued",
        advertiser_authorized=True,
        link_usage_authorized=True,
        site_origin="https://kurashinoshirube.com",
    )
    html, binding = cta(
        value, {"article_id": "article-a", "post_id": 1}, "snapshot", "top_summary"
    )
    full = (
        '<html><head><title>A</title><meta name="description" content="A"><link rel="canonical" href="https://kurashinoshirube.com/article-a/"></head><body><h1>A</h1>'
        + html
        + "</body></html>"
    )
    row = {
        "path": "/article-a/",
        "status": 200,
        "final_url": "https://kurashinoshirube.com/article-a/",
        "full_html": True,
        "html": full,
        "headers": {},
        "purchase_bindings": [binding],
    }
    assert "DISCLOSURE_NOT_BEFORE_LINK" in [
        f["code"] for f in assess([row], ["/article-a/"])["findings"]
    ]


def test_inventory_keeps_legacy_names_without_guessing_identity_and_classifies_new_asp():
    from scripts.raos_public_acceptance import purchase_inventory

    table = '<table><tr><th scope="col">比較項目</th><th scope="col">SOLOTA NP-TMLK1-K</th><th scope="col">ラクアmini Plus TK-MDW22B</th></tr></table>'
    rows = purchase_inventory(Page(table), article_id="comparison", post_id=86)
    assert [r["product_name"] for r in rows] == [
        "SOLOTA NP-TMLK1-K",
        "ラクアmini Plus TK-MDW22B",
    ]
    assert all(
        r["product_id"] is None and r["link_type"] == "unavailable" for r in rows
    )
    value = offer()
    value.update(
        affiliate_ready=True,
        affiliate_url="https://affiliate.example/issued",
        advertiser_authorized=True,
        link_usage_authorized=True,
        site_origin="https://kurashinoshirube.com",
    )
    html, _ = cta(value, {"article_id": "a", "post_id": 1}, "snapshot", "top_summary")
    rows = purchase_inventory(Page(html), article_id="a", offers=[value])
    assert rows[0]["link_type"] == "affiliate"
    assert rows[0]["affiliate_ready"] is True
