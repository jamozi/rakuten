from datetime import date
import pytest

from raos.application.editorial.local_reader_guides import build_local_guides
from raos.application.editorial.reader_experience_v1 import COMPARISON_REQUIREMENTS


def fixture():
    return {
        "schema": "RAOS_LOCAL_READER_GUIDES_V1",
        "publication_authority": False,
        "official_hosts": ["maker.test"],
        "sources": [
            {
                "source_ref": "official-a",
                "url": "https://maker.test/a",
                "title": "Aの説明書",
                "checked_at": "2026-09-01",
                "authority": "MANUFACTURER_OFFICIAL",
                "models": ["MODEL-A", "MODEL-B"],
            }
        ],
        "facts": [
            {
                "evidence_ref": "a-install",
                "source_ref": "official-a",
                "exact_model": "MODEL-A",
                "requirement": "guide:installation",
                "locator": "設置条件 p.4",
                "text": "扉を開ける場所を確保する。",
                "state": "KNOWN",
            }
        ],
        "articles": [
            {
                "article_id": "installation",
                "local_slug": "local-preview-installation",
                "article_type": "guide",
                "title": "置けるか測る",
                "dek": "設置面を測りたい人へ。",
                "category": "kitchen",
                "purposes": ["small-space"],
                "summary": "扉・給排水を含めて測る。",
                "decision_axes": [
                    {
                        "label": "扉",
                        "why_it_matters": "開く空間が必要",
                        "how_to_check": "説明書と設置場所を照合",
                    }
                ],
                "sections": [
                    {
                        "id": "measure",
                        "heading": "扉の空間を確かめる",
                        "paragraphs": [
                            {
                                "text": "本体だけで設置を決めません。",
                                "evidence_refs": ["a-install"],
                            }
                        ],
                    }
                ],
                "unknowns": [],
                "purchase_checks": ["自宅の指定空間を確認"],
                "evidence_refs": ["a-install"],
                "contextual_links": [],
            }
        ],
    }


def test_local_guide_keeps_official_dates_and_has_no_commerce():
    result = build_local_guides(fixture(), today=date(2026, 9, 6))
    assert not result["blocked"]
    article = result["articles"][0]
    assert "2026-09-01" in article["html"] and "MODEL-A" in article["html"]
    assert 'data-raos-cta-type="verify"' in article["html"]
    assert "offer" not in article["html"]
    assert article["local_slug"] == "local-preview-installation"


@pytest.mark.parametrize(
    "change",
    [
        {"state": "UNKNOWN"},
        {"exact_model": "WRONG"},
        {"source_ref": "missing"},
        {"locator": ""},
    ],
)
def test_unknown_or_unbound_evidence_stops_a_guide(change):
    data = fixture()
    data["facts"][0].update(change)
    result = build_local_guides(data, today=date(2026, 9, 6))
    assert not result["articles"] and result["blocked"]


def test_future_or_nonofficial_sources_do_not_complete_a_guide():
    for change in (
        {"checked_at": "2026-09-07"},
        {"authority": "RETAILER"},
        {"url": "https://untrusted.test/spec"},
    ):
        data = fixture()
        data["sources"][0].update(change)
        assert not build_local_guides(data, today=date(2026, 9, 6))["articles"]


def complete_comparison():
    data = fixture()
    article = data["articles"][0]
    article["article_type"] = "comparison"
    article["comparison_products"] = ["MODEL-A", "MODEL-B"]
    for model in article["comparison_products"]:
        for requirement in COMPARISON_REQUIREMENTS:
            data["facts"].append(
                {
                    "evidence_ref": model + "-" + requirement,
                    "source_ref": "official-a",
                    "exact_model": model,
                    "requirement": requirement,
                    "locator": "仕様表",
                    "text": model + "の確認値",
                    "state": "KNOWN",
                }
            )
    article["evidence_refs"] = [f["evidence_ref"] for f in data["facts"]]
    return data


@pytest.mark.parametrize("requirement", COMPARISON_REQUIREMENTS)
def test_every_missing_comparison_requirement_stops_html_generation(requirement):
    data = complete_comparison()
    missing = "MODEL-B-" + requirement
    data["facts"] = [f for f in data["facts"] if f["evidence_ref"] != missing]
    data["articles"][0]["evidence_refs"].remove(missing)
    result = build_local_guides(data, today=date(2026, 9, 6))
    assert result["articles"] == []
    assert "MODEL-B." + requirement in result["blocked"][0]["issues"]


def test_complete_comparison_can_render_but_remains_local_and_without_offers():
    result = build_local_guides(complete_comparison(), today=date(2026, 9, 6))
    assert len(result["articles"]) == 1 and not result["blocked"]
    assert result["publication_authority"] is False
    assert 'data-raos-cta-type="offer"' not in result["articles"][0]["html"]


def test_invalid_local_routes_and_publication_authority_are_rejected():
    for field, value in (("publication_authority", True),):
        data = fixture()
        data[field] = value
        with pytest.raises(ValueError):
            build_local_guides(data, today=date(2026, 9, 6))
    data = fixture()
    data["articles"][0]["local_slug"] = "production-url"
    with pytest.raises(ValueError):
        build_local_guides(data, today=date(2026, 9, 6))


def test_related_links_only_target_completed_local_articles_or_known_routes():
    data = fixture()
    data["articles"][0]["contextual_links"] = [
        {
            "question": "未制作の比較を読む",
            "target_ref": "missing",
            "journey_stage": "compare",
        }
    ]
    result = build_local_guides(data, today=date(2026, 9, 6))
    assert "未制作の比較を読む" not in result["articles"][0]["html"]


def test_source_models_must_be_an_exact_list_and_nested_records_are_checked():
    data = fixture()
    data["sources"][0]["models"] = "MODEL-A-OTHER"
    with pytest.raises(ValueError):
        build_local_guides(data, today=date(2026, 9, 6))
    data = fixture()
    data["articles"][0]["sections"][0]["paragraphs"] = ["not a paragraph record"]
    with pytest.raises(ValueError):
        build_local_guides(data, today=date(2026, 9, 6))


def test_existing_targets_cannot_become_production_or_protocol_relative_links():
    for url in ("/production-article/", "//external.test/", "/wp-admin/", "/"):
        with pytest.raises(ValueError):
            build_local_guides(
                fixture(), today=date(2026, 9, 6), existing_targets={"target": url}
            )


def test_conflicting_comparison_evidence_does_not_depend_on_record_order():
    data = complete_comparison()
    duplicate = dict(
        data["facts"][-1], evidence_ref="conflicting", text="Different configuration"
    )
    data["facts"].append(duplicate)
    data["articles"][0]["evidence_refs"].append("conflicting")
    for reverse in (False, True):
        if reverse:
            data["facts"].reverse()
            data["articles"][0]["evidence_refs"].reverse()
        result = build_local_guides(data, today=date(2026, 9, 6))
        assert not result["articles"]
        assert any(
            "conflicting_evidence" in issue for issue in result["blocked"][0]["issues"]
        )


def test_evidence_anchors_are_visible_without_javascript_or_details_support():
    from raos.application.editorial.reader_html import fragment

    html = build_local_guides(fixture(), today=date(2026, 9, 6))["articles"][0]["html"]
    root = fragment(html)
    assert not root.find(tag="details")
    ids = {node.attrs["id"] for node in root.walk() if node.attrs.get("id")}
    assert all(
        a.attrs["href"][1:] in ids
        for a in root.find(tag="a")
        if str(a.attrs.get("href", "")).startswith("#")
    )



def test_candidate_request_cannot_generate_comparison_prose():
    data = fixture()
    data["comparison_candidates"] = [{
        "candidate_id": "comparison-awaiting-evidence",
        "exact_models": ["MODEL-A", "MODEL-B"],
        "evidence_refs": [],
    }]
    result = build_local_guides(data, today=date(2026, 9, 6))
    assert [a["article_id"] for a in result["articles"]] == ["installation"]
    assert len(result["blocked"][0]["issues"]) == 2 * len(COMPARISON_REQUIREMENTS)



def test_authored_guides_return_to_existing_comparison_and_block_incomplete_new_one():
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from scripts.build_local_reader_guides import build_documents
    result = build_documents()[0]
    articles = {a["article_id"]: a for a in result["articles"]}
    assert set(articles) == {
        "dishwasher-installation-measurement", "dishwasher-water-supply-methods",
        "dishwasher-detergent-guide", "dishwasher-cleaning-guide", "dishwasher-running-cost",
    }
    assert '/local-preview-countertop-dishwasher-for-small-households/' in articles["dishwasher-running-cost"]["html"]
    assert result["blocked"] == [{
        "article_id": "solota-rakua-mini-plus-comparison",
        "issues": [
            "NP-TMLK1-K.water_supply_and_drainage",
            "NP-TMLK1-K.maintenance", "NP-TMLK1-K.warranty",
        ],
    }]
    assert all("data-raos-cta-type=\"offer\"" not in a["html"] for a in articles.values())
