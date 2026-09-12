"""Purpose-first R2.1 deltas: hub product links, comparison slots and guide routes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from raos.application.editorial import purchase_support as ps
from raos.application.editorial.reader_html import fragment

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "changes/reader-purchase-support-v1"
PUBLISHED = ROOT / "changes/wordpress-direct-publish-v1/articles"
DISHWASHERS = (
    "PRD-PANASONIC-NP-TMLK1",
    "PRD-THANKO-RAKUA-MINI-COLOR",
    "PRD-SIROCA-SS-MA251",
    "PRD-PANASONIC-NP-TSP1",
)


@pytest.fixture
def catalog():
    return json.loads((BASE / "purchase-support.v1.json").read_text())


def compile(catalog):
    return ps.compile_articles(
        catalog,
        {p.stem: p.read_text() for p in (BASE / "articles").glob("*.html")},
        json.loads(
            (
                ROOT / "changes/editorial-portfolio-v3/local-reader-guides.v1.json"
            ).read_text()
        ),
    )


def ids_of(markup):
    return {n.attrs["id"] for n in fragment(markup).walk() if "id" in n.attrs}


def dishwashers(catalog):
    return [p for p in catalog["products"] if p["product_id"] in DISHWASHERS]


# --- FD-08 / R-BRIDGE: category 136 promises only what the comparison offers ---


def test_hub_links_each_condition_product_to_its_own_anchor(catalog):
    html, _ = compile(catalog)
    hub = fragment(html["kitchen"])
    choose = next(n for n in hub.find(tag="section") if n.attrs.get("id") == "choose")
    anchors = {p["anchor"]: p["name"] for p in dishwashers(catalog)}
    links = [
        a
        for a in choose.find(tag="a")
        if a.attrs.get("href", "").startswith(f"/{ps.MAIN_SLUG}/#")
    ]
    product_links = [a for a in links if a.attrs["href"].split("#", 1)[1] in anchors]
    assert len(product_links) == 4
    assert {a.attrs["href"].split("#", 1)[1] for a in product_links} == set(anchors)
    for a in product_links:
        assert a.text() == anchors[a.attrs["href"].split("#", 1)[1]]
    assert not [a for a in links if a.attrs["href"].endswith("#ps-choose")]
    # AC31: the anchors already exist in the published comparison, so the neutral
    # category text can go first without waiting for the new comparison layout.
    published = ids_of((PUBLISHED / f"{ps.MAIN_SLUG}.html").read_text())
    assert set(anchors) <= published
    assert "ps-specs" in published


def test_hub_lead_and_cta_do_not_promise_budget_filtering(catalog):
    html, _ = compile(catalog)
    hub = html["kitchen"]
    assert "予算" not in hub
    assert (
        "候補を比べたい方は4機種の比較へ。設置や給水、購入後の手入れを確かめたい方は、"
        "該当する機種のガイドへ進めます。"
    ) in hub
    assert (
        f'<a href="/{ps.MAIN_SLUG}/#ps-specs">4機種の違いと、毎回の作業を比較する</a>'
        in hub
    )
    for _, slug in ps.STAGES.values():
        assert f'href="/{slug}/"' in hub
    assert 'href="/solota-vs-rakua-mini-plus/"' in hub


@pytest.mark.parametrize("mutation", ["missing_product", "missing_anchor"])
def test_hub_condition_links_fail_closed(catalog, mutation):
    products = dishwashers(catalog)
    condition = {"id": "x", "label": "x", "product_ids": ["PRD-PANASONIC-NP-TMLK1"]}
    if mutation == "missing_product":
        condition["product_ids"] = ["PRD-UNKNOWN"]
    else:
        products = [
            dict(p, anchor="") if p["product_id"] == "PRD-PANASONIC-NP-TMLK1" else p
            for p in products
        ]
    with pytest.raises(ValueError):
        ps.condition_product_links(condition, products, ps.MAIN_SLUG)
