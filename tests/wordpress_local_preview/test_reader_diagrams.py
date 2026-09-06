from __future__ import annotations

from raos.application.editorial.reader_components import dimension_diagram
from raos.application.editorial.reader_experience_projection import (
    _resolve_dimension_media,
    project_article,
)
from raos.application.editorial.reader_html import fragment


def _asset(*, approval: str = "approved") -> dict[str, object]:
    return {
        "asset_ref": "dimension-product-a",
        "asset_type": "html_diagram",
        "source": "https://maker.test/product-a",
        "usage_basis": "公式仕様値から編集部が作成するHTML寸法図。",
        "checked_at": "2026-08-31",
        "approval": approval,
        "alt": "本体とステーションの公表寸法比較",
        "caption": "公表された筐体寸法の比較です。",
        "aspect_ratio": [4, 3],
        "role": "dimension",
    }


def _source() -> dict[str, object]:
    return {
        "source_ref": "source-a",
        "url": "https://maker.test/product-a",
        "retrieved_on": "2026-08-31",
        "authority": "MANUFACTURER_OFFICIAL",
    }


def _robot_claim() -> dict[str, object]:
    return {
        "claim_id": "claim-a",
        "classification": "MAJOR_VERIFIABLE",
        "status": "BOUND_TO_OFFICIAL_SOURCE",
        "evidence_refs": ["source-a"],
        "subject_product_ids": ["product-a"],
        "dimensions": [
            {
                "subject": "対象機種の本体",
                "width_cm": 32.5,
                "depth_cm": 32.3,
                "height_cm": 7.2,
            },
            {
                "subject": "対象機種のステーション",
                "width_cm": 27.5,
                "depth_cm": 19.1,
                "height_cm": 21.2,
            },
        ],
    }


def test_robot_figure_uses_approved_media_and_live_axis_labels() -> None:
    figure = dimension_diagram(
        _robot_claim(),
        _source(),
        _asset(),
        product_ref="product-a",
        claim_refs=frozenset({"claim-a"}),
    )

    assert figure is not None
    plan = figure.find(cls="raos-dimension-diagram__comparison-plan")[0]
    assert plan.attrs["aria-label"] == "本体とステーションの公表寸法比較"
    assert {
        node.attrs.get("data-raos-dimension-role") for node in plan.find(tag="span")
    } == {"body", "station"}
    assert not figure.find(tag="svg")
    assert "W（幅）32.5cm / D（奥行）32.3cm / H（高さ）7.2cm" in figure.text()
    assert "W（幅）27.5cm / D（奥行）19.1cm / H（高さ）21.2cm" in figure.text()
    assert figure.attrs["data-raos-media-checked-at"] == "2026-08-31"
    assert "公表された筐体寸法の比較です。" in figure.text()
    assert dimension_diagram(
        _robot_claim(),
        _source(),
        _asset(approval="pending"),
        product_ref="product-a",
        claim_refs=frozenset({"claim-a"}),
    ) is None
    assert dimension_diagram(
        _robot_claim(),
        _source(),
        {**_asset(), "role": "product_identity"},
        product_ref="product-a",
        claim_refs=frozenset({"claim-a"}),
    ) is None


def test_robot_shapes_stay_bound_to_the_claimed_product() -> None:
    claim = _robot_claim()

    assert dimension_diagram(
        claim,
        _source(),
        _asset(),
        product_ref="product-b",
        claim_refs=frozenset({"claim-a"}),
    ) is None
    assert dimension_diagram(
        claim,
        _source(),
        _asset(),
        product_ref="product-a",
        claim_refs=frozenset({"claim-b"}),
    ) is None

    resolved = _resolve_dimension_media(
        {
            "products": [
                {"product_ref": "product-a", "claim_refs": ["claim-a"]},
                {"product_ref": "product-b", "claim_refs": ["claim-b"]},
            ],
            "media": [
                {
                    "asset_ref": "dimension-product-a",
                    "role": "dimension",
                    "evidence_ref": "claim-a",
                }
            ],
        },
        {"claim-a": claim},
        {"source-a": _source()},
        {"dimension-product-a": _asset()},
    )
    assert [row["product_ref"] for row in resolved] == ["product-a"]


def test_robot_comparison_is_omitted_when_either_shape_is_missing() -> None:
    claim = _robot_claim()
    claim["dimensions"] = claim["dimensions"][1:]

    assert dimension_diagram(
        claim,
        _source(),
        _asset(),
        product_ref="product-a",
        claim_refs=frozenset({"claim-a"}),
    ) is None


def test_expanded_luggage_comparison_requires_both_confirmed_footprints() -> None:
    claim = {
        **_robot_claim(),
        "dimensions": [
            {
                "subject": "対象ケース（通常時）",
                "width_cm": 36,
                "depth_cm": 24,
                "height_cm": 55,
            },
            {
                "subject": "対象ケース（拡張時）",
                "width_cm": 36,
                "depth_cm": 27,
                "height_cm": 55,
            },
        ],
    }
    figure = dimension_diagram(
        claim,
        _source(),
        _asset(),
        product_ref="product-a",
        claim_refs=frozenset({"claim-a"}),
    )

    assert figure is not None
    assert {
        node.attrs.get("data-raos-dimension-role")
        for node in figure.find(cls="raos-dimension-diagram__shape")
    } == {"normal", "expanded"}
    assert "通常時" in figure.text()
    assert "拡張時" in figure.text()
    assert dimension_diagram(
        {**claim, "dimensions": claim["dimensions"][:1]},
        _source(),
        _asset(),
        product_ref="product-a",
        claim_refs=frozenset({"claim-a"}),
    ) is None


def test_unknown_clearance_is_text_only_and_figure_stays_inside_product() -> None:
    resolved = [
        {
            "asset": _asset(),
            "claim": _robot_claim(),
            "source": _source(),
            "product_ref": "product-a",
            "claim_refs": frozenset({"claim-a"}),
        }
    ]
    markup = (
        '<div class="raos-editorial-v2"><section class="products-section">'
        '<article id="a" class="raos-product-card" data-raos-product-id="product-a">'
        '<h3>製品A</h3><dl class="raos-product-card__facts"><div><dt>寸法</dt>'
        '<dd>公式確認済み</dd></div></dl></article>'
        '<article id="b" class="raos-product-card" data-raos-product-id="product-b">'
        '<h3>製品B</h3></article></section></div>'
    )
    output = fragment(
        project_article(
            markup,
            article_id="article-a",
            experience={
                "article_type": "shortlist",
                "components_enabled": True,
                "products": [],
                "_resolved_dimensions": resolved,
            },
        )
    )

    cards = {
        card.attrs["data-raos-product-id"]: card
        for card in output.find(cls="raos-product-card")
    }
    assert len(cards["product-a"].find(tag="figure")) == 1
    assert not cards["product-b"].find(tag="figure")
    assert not output.find(cls="raos-reader-dimensions")
    assert not output.find(tag="h2")
    figure = cards["product-a"].find(tag="figure")[0]
    assert "前方・左右・上方の余白を含めていません" in figure.text()
    assert not any(
        node.attrs.get("data-raos-dimension-role") == "clearance"
        for node in figure.walk()
    )


def test_existing_dishwasher_body_and_door_copy_is_preserved() -> None:
    claim = {
        **_robot_claim(),
        "dimensions": [
            {
                "subject": "対象食洗機本体",
                "width_cm": 30.8,
                "depth_cm": 31.5,
                "height_cm": 41.5,
            },
            {
                "subject": "対象食洗機扉開放時",
                "width_cm": 30.8,
                "depth_cm": 59.4,
                "height_cm": 41.5,
            },
        ],
    }

    figure = dimension_diagram(claim, _source(), _asset())

    assert figure is not None
    assert "幅 30.8cm × 奥行 31.5cm" in figure.text()
    assert "扉を開いたときの奥行：59.4cm（本体を含む）" in figure.text()
