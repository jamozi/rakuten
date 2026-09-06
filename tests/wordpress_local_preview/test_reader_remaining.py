from raos.application.editorial.reader_experience_projection import project_article
from raos.application.editorial.reader_html import fragment
from raos.application.editorial.reader_experience_v1 import validate_experience

MARKUP = """<div class="raos-editorial-v2"><section class="decision-section"><h2>結論</h2><ul class="decision-list"><li><h3>条件A</h3><p>候補の理由</p><a href="#model-a">候補A</a></li></ul></section><section class="products-section"><h2>商品</h2><article class="raos-product-card" id="model-a" data-raos-product-id="a"><h3>候補A</h3><div class="raos-product-card__fit"><ul><li>設置幅を優先</li></ul><ul><li>給水作業を避けたい人</li></ul></div><p class="raos-product-card__caution">排水経路を確認</p></article></section></div>"""
BASE = {
    "article_type": "shortlist",
    "components_enabled": True,
    "decision_summary": {
        "key_difference": "最大差の説明",
        "no_purchase_condition": "設置できなければ見送る",
        "options": [],
    },
    "decision_axes": [
        {
            "label": "設置を測る",
            "why_it_matters": "置ける条件",
            "how_to_check": "説明書を見る",
        }
    ],
}


def render(settings):
    return fragment(
        project_article(MARKUP, article_id="test", experience={**BASE, **settings})
    )


def test_common_decision_precedes_candidates_and_links_to_existing_axes():
    root = render({})
    summary = root.find(cls="decision-section")[0]
    assert summary.html().index("最大差の説明") < summary.html().index(
        'class="decision-list"'
    )
    assert summary.html().index("設置できなければ見送る") < summary.html().index(
        'class="decision-list"'
    )
    assert any(a.attrs.get("href") == "#reader-axes" for a in summary.find(tag="a"))
    assert len([n for n in root.walk() if n.attrs.get("id") == "reader-axes"]) == 1


def test_tradeoff_and_exclusion_are_distinct_in_summary_and_table():
    root = render(
        {
            "products": [
                {
                    "product_ref": "a",
                    "tradeoffs": ["使うたびに水を補給する"],
                    "not_for": ["給水作業を避けたい人"],
                    "purchase_checks": ["専用の排水経路を確認"],
                }
            ]
        }
    )
    summary = root.find(cls="decision-section")[0]
    assert "妥協点：使うたびに水を補給する" in summary.text()
    assert "妥協点：給水作業を避けたい人" not in root.text()
    table = root.find(cls="raos-decision-table")[0]
    assert "妥協点・選ばない条件" in table.text()
    assert "選ばない条件：給水作業を避けたい人" in table.text()
    assert "専用の排水経路を確認" in table.text()


def test_old_missing_tradeoff_is_not_filled_with_an_exclusion_or_purchase_check():
    root = render({})
    assert "妥協点：給水作業を避けたい人" not in root.text()
    assert "妥協点：排水経路を確認" not in root.text()
    table = root.find(cls="raos-decision-table")[0]
    assert "選ばない条件：給水作業を避けたい人" in table.text()
    assert "商品の詳細で確認" in table.text()


def test_product_decision_fields_reject_unstructured_copy():
    base = {
        "article_type": "shortlist",
        "research_status": {
            "real_world_tested": False,
            "ranking_uses_commission": False,
        },
    }
    for key in ("tradeoffs", "not_for", "purchase_checks"):
        issues = validate_experience(
            {**base, "products": [{"product_ref": "a", key: "not an array"}]},
            product_refs=frozenset({"a"}),
            evidence_refs=frozenset(),
        )
        assert "products." + key + ".invalid" in issues


def test_official_link_identity_includes_skus_without_importing_sales_or_marketing():
    from raos.application.editorial.reader_experience_v1 import (
        official_reference_identity,
    )

    assert (
        official_reference_identity("ラクアmini Plus", "TK-MDW22B")
        == "ラクアmini Plus（TK-MDW22B）"
    )
    assert (
        official_reference_identity(
            "ラクアmini color",
            "ミスティーブルー TDWS25SBL（JAN 4580060603756）／クラシックローズ TDWS25SRD",
        )
        == "ラクアmini color（TDWS25SBL／TDWS25SRD）"
    )
    assert (
        official_reference_identity(
            "INTER CITY II 60561", "シルバー（公式ページで購入UIを確認）"
        )
        == "INTER CITY II 60561"
    )
    assert (
        official_reference_identity("DELTA 3 Plus", "DELTA 3 Plus | 防災に最適")
        == "DELTA 3 Plus"
    )



def test_research_summary_uses_source_observations_without_redating_metadata():
    from raos.application.editorial.reader_experience_projection import project_article
    html = '<div class="raos-editorial-v2"><dl class="raos-article-facts"><div><dt>最終確認日</dt><dd>2026年9月6日</dd></div><div><dt>実機確認</dt><dd>未実施</dd></div></dl></div>'
    result = project_article(html, article_id="scoped-update", experience={"article_type": "shortlist", "_resolved_source_dates": ["2026-08-23", "2026-09-06"]})
    assert "公式情報確認：2026-08-23〜2026-09-06（出典別）" in result
    assert "<dd>2026年9月6日</dd>" in result



def test_single_letter_official_skus_remain_in_verification_labels():
    from raos.application.editorial.reader_experience_v1 import official_reference_identity
    for model, code in (("Solix C1000 Plus", "A1765"), ("Robot Vacuum 3-in-1 E20", "T2070"), ("Robot Vacuum Omni E25", "T2353")):
        assert official_reference_identity(model, code) == model + "（" + code + "）"
