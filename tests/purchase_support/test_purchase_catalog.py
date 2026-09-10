"""Exact identity, date/price and public projection boundaries across the 13 candidates."""

from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from raos.application.editorial.purchase_support import (
    compile_articles,
    validate_catalog,
    PLACEMENTS,
)
from raos.application.editorial.purchase_offer_import import (
    approved_offer_from_normalized,
)
from raos.application.editorial.reader_html import fragment
from tools.affiliate_ingestion.normalize import normalize_record

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "changes/reader-purchase-support-v1"


@pytest.fixture
def catalog():
    return json.loads((BASE / "purchase-support.v1.json").read_text())


def compile(catalog):
    return compile_articles(
        catalog,
        {p.stem: p.read_text() for p in (BASE / "articles").glob("*.html")},
        json.loads(
            (
                ROOT / "changes/editorial-portfolio-v3/local-reader-guides.v1.json"
            ).read_text()
        ),
    )


def test_all_sixteen_slots_have_actionable_research_and_preserve_identity_routes(
    catalog,
):
    validate_catalog(catalog)
    html, runtime = compile(catalog)
    assert len(html) == 13 and len(catalog["products"]) == 16
    roots = {slug: fragment(body) for slug, body in html.items()}
    for slug, root in roots.items():
        ids = [n.attrs["id"] for n in root.walk() if "id" in n.attrs]
        assert len(ids) == len(set(ids)), slug
        old = fragment((BASE / "articles" / f"{slug}.html").read_text())
        assert {n.attrs["id"] for n in old.walk() if "id" in n.attrs} <= set(ids), slug
        for a in root.find(tag="a"):
            link = urlsplit(a.attrs.get("href", ""))
            target = link.path.strip("/") or slug
            if not link.netloc and target in roots and link.fragment:
                assert link.fragment in {
                    n.attrs.get("id") for n in roots[target].walk()
                }, (slug, a.attrs)
    for route in catalog["routes"]:
        product = next(
            p for p in catalog["products"] if p["product_id"] == route["product_id"]
        )
        assert route["anchor"] == product["anchor"]
    for a in runtime["articles"]:
        links = [
            n
            for n in roots[a["slug"]].find(tag="a")
            if n.attrs.get("data-raos-cta-type") == "offer"
        ]
        assert len(links) == len(a["bindings"])
        for b in a["bindings"]:
            assert set(b) == {
                "article_id",
                "product_id",
                "seller_id",
                "offer_id",
                "cta_id",
                "placement",
                "snapshot_id",
                "href",
            }
            link = next(n for n in links if n.attrs["data-raos-cta-id"] == b["cta_id"])
            assert link.attrs["href"] == b["href"]
            assert all(
                link.attrs["data-raos-" + k.replace("_", "-")] == b[k]
                for k in b
                if k != "href"
            )
        if a["bindings"]:
            assert {b["placement"] for b in a["bindings"]} == set(PLACEMENTS)
    tsp = next(p for p in catalog["products"] if p["exact_model"] == "NP-TSP1-W")
    assert not any(
        b["product_id"] == tsp["product_id"]
        for a in runtime["articles"]
        for b in a["bindings"]
    )


@pytest.mark.parametrize(
    "mutation", ["model", "rights", "private", "missing_research", "route"]
)
def test_reject_misbinding_or_missing_management(catalog, mutation):
    if mutation == "model":
        catalog["offers"][0]["product_model"] = "OTHER-MODEL"
    elif mutation == "rights":
        catalog["offers"][0]["affiliate"] = True
    elif mutation == "private":
        catalog["offers"][0]["provider_measurement_id"] = "PRIVATE"
    elif mutation == "missing_research":
        pid = catalog["products"][0]["product_id"]
        catalog["research_issues"] = [
            i for i in catalog["research_issues"] if i["product_id"] != pid
        ]
    else:
        catalog["routes"][0]["anchor"] = "another-product"
    with pytest.raises(ValueError):
        validate_catalog(catalog)


def test_asp_normalized_record_requires_independent_permission_and_never_projects_finance(
    catalog,
):
    offer = deepcopy(catalog["offers"][0])
    offer.update(
        affiliate=True,
        advertiser_authorized=True,
        link_usage_authorized=True,
        site_origin="https://kurashinoshirube.com",
    )
    record = normalize_record(
        "a8net",
        "products",
        {
            "product_id": "private-source-id",
            "affiliate_url": offer["url"],
            "commission": "9999",
            "raw_secret": "never public",
        },
    )
    review = {
        "schema": "RAOS_PURCHASE_ASP_REVIEW_V1",
        "source_fingerprint_sha256": record["fingerprint_sha256"],
        "material_storage_authorized": True,
        "offer": offer,
    }
    assert approved_offer_from_normalized(record, review) == offer
    for key, value in [
        ("advertiser_authorized", False),
        ("link_usage_authorized", False),
        ("identity_verified", False),
        ("url", "https://example.invalid/other"),
    ]:
        bad = deepcopy(review)
        bad["offer"][key] = value
        with pytest.raises(ValueError):
            approved_offer_from_normalized(record, bad)
    bad = deepcopy(review)
    bad["source_fingerprint_sha256"] = "x" * 64
    with pytest.raises(ValueError):
        approved_offer_from_normalized(record, bad)


def test_advertising_changes_do_not_change_conditions_or_model_selection(catalog):
    before, _ = compile(catalog)
    for offer in catalog["offers"]:
        offer.update(
            affiliate=True,
            advertiser_authorized=True,
            link_usage_authorized=True,
            site_origin="https://kurashinoshirube.com",
        )
    after, _ = compile(catalog)
    for slug in before:
        for cls in ("ps-condition-grid", "ps-product-grid"):
            # Ads may change link disclosure attributes; readable recommendation reasons stay identical.
            assert [n.text() for n in fragment(before[slug]).walk() if n.has(cls)] == [
                n.text() for n in fragment(after[slug]).walk() if n.has(cls)
            ]
