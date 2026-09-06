from types import SimpleNamespace

import pytest

from raos.application.editorial.self_hosted_editorial_pilot import _Renderer
from raos.application.editorial.reader_html import fragment
from raos.domain.editorial.self_hosted_editorial_pilot import EditorialPilotFailure


def renderer():
    table = {
        "comparison_table_ref": "support",
        "caption": "公表条件の読み方",
        "axis_refs": ["cycle", "source"],
        "presentation": {
            "role": "supporting_evidence",
            "checked_at": "2026-09-06",
            "source_axis_ref": "source",
        },
        "rows": [
            {
                "product_selection_ref": "a",
                "cells": [
                    {
                        "axis_ref": "cycle",
                        "value": "未確認",
                        "state": "UNKNOWN",
                        "claim_ids": [],
                    },
                    {
                        "axis_ref": "source",
                        "value": "2026-09-06確認",
                        "state": "KNOWN",
                        "claim_ids": ["claim"],
                    },
                ],
            }
        ],
    }
    return _Renderer(
        article={
            "article_id": "example",
            "render_model": {
                "comparison_axes": [
                    {"comparison_axis_ref": a, "label": a, "description": a}
                    for a in ["cycle", "source"]
                ],
                "comparison_tables": [table],
                "recommendations": [],
            },
        },
        routes={},
        sources={"official": {"url": "https://www.ankerjapan.com/products/a1722"}},
        claims={"claim": {"evidence_level": "A", "evidence_refs": ["official"]}},
        cards={
            "a": {
                "product_id": "a",
                "product_name": "MODEL-A",
                "presentation_v2": {"facts_checked_on": "2026-09-01"},
            }
        },
        evidences={"a": SimpleNamespace(image_url="https://maker.test/photo.png")},
        alts={},
        facts_checked_on="2026-09-01",
        product_media_verified=True,
    )


def block():
    return {
        "block_id": "supporting-block",
        "comparison_table_ref": "support",
        "comparison_axis_refs": ["cycle", "source"],
        "product_selection_refs": ["a"],
    }


def test_supporting_table_uses_its_own_heading_date_and_bound_source_without_photo():
    html = renderer().comparison(block())
    root = fragment(html)
    assert root.find(tag="h2")[0].text() == "公表条件の読み方"
    assert "2026年9月6日" in html and "2026年9月1日" not in html
    assert "未確認" in html
    assert 'href="https://www.ankerjapan.com/products/a1722"' in html
    assert not root.find(tag="img") and "商品画像未確認" not in html


def test_supporting_table_rejects_source_axis_outside_its_axes():
    target = renderer()
    target.tables["support"]["presentation"]["source_axis_ref"] = "unrelated"
    with pytest.raises(EditorialPilotFailure):
        target.comparison(block())


def test_unknown_cell_is_not_labelled_verified_but_still_validates_claims():
    target = renderer()
    cell = target.tables["support"]["rows"][0]["cells"][0]
    cell["claim_ids"] = ["claim"]
    html = target.comparison(block())
    assert "未確認" in html and "公式確認済み" not in html
    cell["claim_ids"] = ["missing-claim"]
    with pytest.raises(EditorialPilotFailure):
        target.comparison(block())


def test_lifecycle_status_and_heading_exemptions_cannot_hide_numeric_facts():
    from scripts import build_st1704_reader_claim_coverage as coverage

    assert coverage.UNKNOWN_STATUS_RE.fullmatch(
        "未確認(この型番の公表回数に対応する基準)"
    )
    assert not coverage.UNKNOWN_STATUS_RE.fullmatch("未確認(容量80%)")
    assert not coverage.UNKNOWN_STATUS_RE.fullmatch("3,000回 未確認")

    def label(text, tag):
        return coverage._table_or_definition_label_matches(
            SimpleNamespace(text=text, locator=f"/table[1]/{tag}[1]::text")
        )

    assert label("公表サイクル数", "th")
    assert label("充放電サイクルの条件と製品保証", "caption")
    assert not label("電池3,000回", "caption")
    assert not label("公表サイクル数", "td")
