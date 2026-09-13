"""Conclusion links retain identity while using distinct placements and source bytes."""

from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from scripts import build_reader_purchase_support_v1 as builder
from raos.application.editorial.purchase_support import (
    bind_condition_commerce,
    resolve_product_media,
)
from raos.application.editorial.reader_html import fragment, readable_tables


def inputs():
    catalog = json.loads(builder.CATALOG_INPUT_PATH.read_text())
    article = next(
        a for a in catalog["articles"] if a["slug"] == "compact-robot-vacuum-shortlist"
    )
    media = resolve_product_media(
        catalog,
        json.loads(builder.MEDIA_INPUT_PATH.read_text()),
        builder.OFFICIAL_MEDIA_INPUT_PATH.read_bytes(),
    )
    return catalog, article, media


def test_conclusions_have_exact_products_and_distinct_snapshot_bound_links():
    outputs = builder.build()
    runtime = json.loads(outputs[builder.RUNTIME_OUTPUT_PATH])
    for article in runtime["articles"]:
        if not article.get("condition_media"):
            continue
        bindings = article["bindings"]
        assert len({b["cta_id"] for b in bindings}) == len(bindings)
        for entry in article["condition_media"].values():
            pid, key = entry["product_id"], entry["condition_id"]
            assert pid in article["media"]
            if "ps-official-product-photo" in entry["html"]:
                continue
            for size in ("240", "300"):
                cta_id = f"purchase-image-{pid}-{size}-condition-{key}"
                row = next(
                    b for b in bindings if b["cta_id"] == f"purchase-image-{pid}-{size}"
                )
                conclusion = next(b for b in bindings if b["cta_id"] == cta_id)
                assert conclusion["href"] == row["href"]
                assert conclusion["snapshot_id"] == article["snapshot_id"]
                assert conclusion["placement"] == "top_summary"
                assert conclusion["affiliate"] == "true"
                assert conclusion["link_purpose"] == "affiliate_purchase"


@pytest.mark.parametrize(
    "mutation", ["duplicate", "wrong_product", "wrong_condition", "nonempty"]
)
def test_condition_slots_reject_duplicate_or_mismatched_sources(mutation):
    catalog, article, media = inputs()
    article = deepcopy(article)
    html = (
        builder.CATALOG_INPUT_PATH.parent / "articles" / (article["slug"] + ".html")
    ).read_text()
    root = fragment(html)
    slot = root.find(cls="ps-condition-product-media")[0]
    if mutation == "duplicate":
        html += slot.html()
    elif mutation == "wrong_product":
        slot.attrs["data-ps-media-product"] = article["product_ids"][-1]
        html = root.html()
    elif mutation == "wrong_condition":
        slot.attrs["data-ps-condition"] = "unregistered-condition"
        html = root.html()
    else:
        slot.children.append("unexpected embedded picture")
        html = root.html()
    with pytest.raises(ValueError, match="PURCHASE_CONDITION_SLOT_INVALID"):
        bind_condition_commerce(
            html,
            article,
            catalog,
            "snapshot",
            media,
            datetime(2026, 9, 13, tzinfo=timezone.utc),
        )


def test_readable_table_keeps_values_links_and_semantic_column_labels():
    source = '<div><table><thead><tr><th>機種</th><th>手順</th></tr></thead><tbody><tr><th id="model">モデルA</th><td><a href="#model">3g・毎回</a></td></tr></tbody></table></div>'
    root = fragment(readable_tables(source))
    assert root.find(tag="td")[0].attrs["data-ks-column-label"] == "手順"
    assert root.find(tag="td")[0].text() == "3g・毎回"
    assert root.find(tag="a")[0].attrs["href"] == "#model"
    assert root.find(tag="th")[-1].attrs["id"] == "model"
    assert readable_tables(root.html()) == root.html()


def test_matrix_rows_preserve_product_identity_facts_sources_and_purchase_links():
    from raos.application.editorial.purchase_support import matrix_comparison_markup

    source = '<div><table class="ps-row-comparison"><thead><tr><th>商品</th><th id="dimensions">寸法</th><th>容量</th><th>購入</th></tr></thead><tbody><tr id="model-a" data-product-id="A"><th><strong>A</strong><div data-ps-media-product="A"></div></th><td id="axis"><p>幅24cm<a href="#source">根拠</a></p></td><td><p>3L</p></td><td><a href="https://example.com/issued" data-raos-product-id="A">購入</a></td></tr></tbody></table></div>'
    result = matrix_comparison_markup(source)
    root = fragment(result)
    table = root.find(cls="ps-matrix-comparison")[0]
    row = table.find(tag="tbody")[0].find(tag="tr")[0]
    assert len(table.find(tag="thead")[0].find(tag="th")) == 3
    assert [n.tag for n in row.children if hasattr(n, "tag")] == ["th", "td", "td"]
    assert row.attrs["data-product-id"] == "A"
    assert {n.attrs["id"] for n in root.walk() if n.attrs.get("id")} == {
        "dimensions",
        "model-a",
        "axis",
    }
    assert [n.attrs.get("href") for n in root.find(tag="a")] == [
        "#source",
        "https://example.com/issued",
    ]
    assert row.find(cls="ps-matrix-specs")[0].text() == "幅24cm根拠3L"
    assert matrix_comparison_markup(result) == result


def test_native_supporting_table_keeps_full_width_group_headings():
    source = '<div><table><thead><tr><th>型番</th><th>使用水量</th></tr></thead><tbody><tr><th colspan="2" scope="rowgroup">旧機種</th></tr><tr id="old"><th>B</th><td>未確認</td></tr></tbody></table></div>'
    result = readable_tables(source)
    assert fragment(result).text() == fragment(source).text()
    assert len(fragment(result).find(cls="ks-readable-table")) == 1
    assert readable_tables(result) == result
