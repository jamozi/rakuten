"""Product identity, source/anchor preservation and shared row commerce boundaries."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from scripts import build_reader_purchase_support_v1 as builder
from raos.application.editorial.purchase_support import (
    comparison_row_columns,
    compile_articles,
    condition_summary,
    resolve_product_media,
    row_commerce,
)
from raos.application.editorial.reader_html import fragment


@pytest.fixture(scope="module")
def rendered():
    catalog = json.loads(builder.CATALOG_INPUT_PATH.read_text())
    templates = {p.stem: p.read_text() for p in builder.TEMPLATE_INPUT_PATHS}
    media = resolve_product_media(
        catalog,
        json.loads(builder.MEDIA_INPUT_PATH.read_text()),
        builder.OFFICIAL_MEDIA_INPUT_PATH.read_bytes(),
    )
    outputs, runtime = compile_articles(
        catalog,
        templates,
        json.loads(builder.GUIDES_INPUT_PATH.read_text()),
        media,
        now=datetime(2026, 9, 13, 7, tzinfo=timezone.utc),
    )
    return catalog, templates, outputs, runtime, media


def test_every_comparison_binds_the_same_product_across_each_row(rendered):
    catalog, templates, outputs, runtime, _ = rendered
    for article in catalog["articles"]:
        if article.get("commerce_presentation") != "comparison_rows":
            continue
        body = fragment(outputs[article["slug"]])
        rows = [
            node for node in body.find(tag="tr") if node.attrs.get("data-product-id")
        ]
        assert [
            row.attrs["data-product-id"]
            for row in rows
            if not row.attrs.get("data-ps-supplementary")
        ] == article["product_ids"]
        assert [
            row.attrs["data-product-id"]
            for row in rows
            if row.attrs.get("data-ps-supplementary")
        ] == article.get("supplementary_product_ids", [])
        ids = [node.attrs["id"] for node in body.walk() if node.attrs.get("id")]
        assert len(ids) == len(set(ids))
        assert {
            n.attrs["id"]
            for n in fragment(templates[article["slug"]]).walk()
            if n.attrs.get("id")
        } <= set(ids)
        for row in rows:
            pid = row.attrs["data-product-id"]
            for node in row.walk():
                assert node.attrs.get("data-ps-media-product", pid) == pid
                assert node.attrs.get("data-raos-product-id", pid) == pid
        entry = next(a for a in runtime["articles"] if a["slug"] == article["slug"])
        assert (
            entry["body_sha256"]
            == sha256(outputs[article["slug"]].encode()).hexdigest()
        )
        assert all(
            binding["snapshot_id"] == entry["snapshot_id"]
            for binding in entry["bindings"]
        )
        for pid, markup in entry["media"].items():
            assert pid in article["product_ids"] + article.get(
                "supplementary_product_ids", []
            )
            assert (
                sum(
                    node.has("ps-product-media")
                    and node.attrs.get("data-ps-media-product") == pid
                    for node in body.walk()
                )
                == 1
            )
            assert (
                entry["snapshot_id"] in markup or "ps-official-product-photo" in markup
            )


def test_missing_image_does_not_remove_verified_reference_or_link(rendered):
    catalog, _, _, _, media = rendered
    catalog = deepcopy(catalog)
    product = next(
        p
        for p in catalog["products"]
        if p["product_id"] == "PRD-THANKO-RAKUA-MINI-PLUS"
    )
    product["image_review"] = {"state": "UNVERIFIED", "reason": "画像だけ未確認"}
    article = next(
        a for a in catalog["articles"] if a["slug"] == "compact-dishwasher-comparison"
    )
    photo, seller, bindings, images = row_commerce(
        product,
        article,
        catalog,
        "test-snapshot",
        media,
        datetime(2026, 9, 13, 7, tzinfo=timezone.utc),
    )
    assert photo == "" and images == {}
    assert len(bindings) == 1 and bindings[0]["placement"] == "comparison_table"
    assert "data-ps-reference-price" in seller and "楽天で見る" in seller
    assert "29,800" not in fragment(seller).text()


def test_ineligible_identity_has_official_link_without_reference(rendered):
    catalog, _, _, _, media = rendered
    catalog = deepcopy(catalog)
    product = next(
        p
        for p in catalog["products"]
        if p["product_id"] == "PRD-THANKO-RAKUA-MINI-PLUS"
    )
    for offer in catalog["offers"]:
        if offer["product_id"] == product["product_id"]:
            offer["identity_verified"] = False
    article = next(
        a for a in catalog["articles"] if a["slug"] == "compact-dishwasher-comparison"
    )
    photo, seller, bindings, images = row_commerce(
        product,
        article,
        catalog,
        "test-snapshot",
        media,
        datetime(2026, 9, 13, 7, tzinfo=timezone.utc),
    )
    assert not photo and not bindings and not images
    assert "data-ps-reference-price" not in seller
    assert product["official_url"].replace("&", "&amp;") in seller


def test_row_axes_cannot_drop_existing_facts_or_duplicate_them():
    article = {"spec_labels": ["容量", "重量"]}
    assert comparison_row_columns(article) == [
        {"heading": "仕様", "fact_labels": ["容量", "重量"]}
    ]
    for labels in (["容量"], ["容量", "容量", "重量"]):
        with pytest.raises(ValueError, match="FACT_COVERAGE"):
            comparison_row_columns(
                {
                    **article,
                    "comparison_row_columns": [
                        {"heading": "仕様", "fact_labels": labels}
                    ],
                }
            )


@pytest.mark.parametrize(
    "state, label",
    [
        ("AVAILABLE", "販売条件の一部を確認中"),
        ("UNKNOWN", "販売条件の一部を確認中"),
        ("SOLD_OUT", "確認した販売先は売り切れ"),
    ],
)
def test_unknown_condition_does_not_invent_a_sold_out_state(rendered, state, label):
    catalog = deepcopy(rendered[0])
    article = next(
        a for a in catalog["articles"] if a["slug"] == "carry-on-suitcase-comparison"
    )
    product = next(
        p for p in catalog["products"] if p["product_id"] == article["product_ids"][0]
    )
    for offer in catalog["offers"]:
        if offer["product_id"] == product["product_id"]:
            offer.update(state=state, condition="UNKNOWN", identity_verified=True)
    text = fragment(
        condition_summary(
            product, article, catalog, datetime(2026, 9, 13, 7, tzinfo=timezone.utc)
        )
    ).text()
    assert label in text
    if state != "SOLD_OUT":
        assert "売り切れ" not in text


def test_standard_detergent_stays_with_its_exact_model(rendered):
    root = fragment(rendered[2]["standard-dishwasher-comparison"])
    rows = {
        r.find(tag="th")[0].text(): r.text()
        for r in root.find(tag="tr")
        if r.find(tag="th") and len(r.find(tag="td")) == 3
    }
    assert "通常約5g（公表試験条件も5g）" in rows["NP-TSP1-W"]
    assert "通常約5g（公表試験条件も5g）" not in rows["AX-S7"]


def test_table_navigation_aliases_point_to_the_table_not_hidden_footer(rendered):
    for slug in (
        "carry-on-suitcase-comparison",
        "anker-solix-c300-c800-c1000-differences",
    ):
        root = fragment(rendered[2][slug])
        links = [a for a in root.find(tag="a") if "比較表へ" in a.text()]
        assert links
        for link in links:
            target = next(
                n for n in root.walk() if n.attrs.get("id") == link.attrs["href"][1:]
            )
            assert target.parent.attrs.get("id") == "ps-specs"


def test_jackery_model_number_is_in_the_same_identity_cell_as_its_image(rendered):
    root = fragment(rendered[2]["portable-power-station-guide"])
    row = next(
        r
        for r in root.find(tag="tr")
        if r.attrs.get("data-product-id") == "PRD-JACKERY-500-NEW"
    )
    identity = row.find(tag="th")[0]
    assert identity.find(cls="ps-row-model")[0].text() == "JE-500A"
    assert identity.find(cls="ps-product-media")


def test_compact_approved_version_is_preserved_for_reconfirmation():
    record = json.loads(
        (
            builder.ROOT
            / "changes/site-improvements-20260913/approved-layout-baselines.v1.json"
        ).read_text()
    )
    baseline = record["articles"]["compact-dishwasher-comparison"]
    assert (
        baseline["body_sha256"]
        == "a8788ae876dcc34b3d86660f91db03476683926b6b7db48438bfa85856b589ad"
    )
    assert baseline["new_layout_review"] == "PENDING_USER_REVIEW"


def test_new_article_template_uses_shared_rows_and_reviewed_media_scope(rendered):
    catalog, templates, _, _, media = deepcopy(rendered)
    directory = builder.CATALOG_INPUT_PATH.parent / "templates"
    article = json.loads((directory / "comparison-row-article.json").read_text())
    slug = "new-comparison-template-example"
    article.update(article_id=slug, slug=slug)
    ids = ["PRD-PANASONIC-NP-TMLK1", "PRD-THANKO-RAKUA-MINI-PLUS"]
    article["product_ids"] = ids
    body = (directory / "comparison-row-article.html.template").read_text()
    for entry, pid, suffix in zip(article["row_products"], ids, "AB", strict=True):
        entry["product_id"] = pid
        product = next(p for p in catalog["products"] if p["product_id"] == pid)
        body = body.replace("登録した商品名・型番" + suffix, product["name"])
    catalog["articles"].append(article)
    templates[slug] = body
    guides = json.loads(builder.GUIDES_INPUT_PATH.read_text())
    with pytest.raises(ValueError, match="MEDIA_ARTICLE_SCOPE_MISMATCH"):
        compile_articles(catalog, templates, guides, media)
    for pid in ids:
        media[pid]["slugs"].append(slug)
    outputs, runtime = compile_articles(
        catalog,
        templates,
        guides,
        media,
        now=datetime(2026, 9, 13, 7, tzinfo=timezone.utc),
    )
    root = fragment(outputs[slug])
    assert len(root.find(cls="ps-row-comparison")) == 1
    assert [r.attrs["data-product-id"] for r in root.find(tag="tr")[1:]] == ids
    assert len(root.find(cls="ps-offer-link")) == 2
    assert (
        "アフィリエイトリンクが含まれます" in root.find(cls="ps-disclosure")[0].text()
    )
    assert "29,800" not in root.text()
    entry = next(a for a in runtime["articles"] if a["slug"] == slug)
    assert set(entry["media"]) == set(ids)
    assert len(entry["bindings"]) == 6
