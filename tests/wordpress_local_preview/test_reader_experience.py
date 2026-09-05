from dataclasses import replace
from pathlib import Path

from raos.application.editorial.reader_experience_projection import fragment, project_article

from raos.application.editorial.reader_experience_v1 import (
    COMPARISON_REQUIREMENTS,
    CheckedFact,
    CtaEvidence,
    MediaAsset,
    comparison_issues,
    cta_visible,
    validate_experience,
)


def test_unknown_or_undated_fact_never_completes_a_comparison() -> None:
    fact = CheckedFact("fact", "official", "2026-09-01", "KNOWN")
    products = {p: dict.fromkeys(COMPARISON_REQUIREMENTS, fact) for p in ("a", "b")}
    assert comparison_issues(products) == ()
    products["a"]["sales_state"] = replace(fact, state="UNKNOWN")
    products["b"]["door_or_installation_space"] = replace(fact, checked_at=None)
    assert comparison_issues(products) == ("a.sales_state", "b.door_or_installation_space")


def test_offer_requires_the_exact_product_url_and_sales_eligibility() -> None:
    url = "https://example.test/offer"
    evidence = CtaEvidence(
        existing_targets=frozenset({"#installation"}),
        official_urls=frozenset({"https://manufacturer.test/manual"}),
        verified_offers=frozenset({("a", url)}),
        eligible_products=frozenset({"a"}),
    )
    assert cta_visible("offer", url, "a", evidence, article_type="shortlist")
    assert not cta_visible("offer", url, "b", evidence, article_type="shortlist")
    assert not cta_visible("offer", url, "a", replace(evidence, eligible_products=frozenset()), article_type="shortlist")
    assert not cta_visible("offer", url, "a", evidence, article_type="status_check")
    assert cta_visible("learn", "#installation", None, evidence, article_type="shortlist")
    assert not cta_visible("learn", "/missing/", None, evidence, article_type="shortlist")
    assert cta_visible("verify", "https://manufacturer.test/manual", None, evidence, article_type="status_check")


def test_media_needs_approval_and_complete_usage_metadata() -> None:
    asset = MediaAsset("diagram", "https://manufacturer.test/manual", "original specification diagram", "2026-09-01", "approved", "Door clearance diagram", "Official dimensions; not a product photo", (4, 3), "dimension")
    assert asset.displayable
    for change in ({"approval": "pending"}, {"checked_at": None}, {"usage_basis": ""}, {"alt": ""}, {"aspect_ratio": (0, 3)}):
        assert not replace(asset, **change).displayable


def test_status_article_cannot_become_a_recommendation_via_the_view_model() -> None:
    experience = {
        "article_type": "status_check",
        "research_status": {"ranking_uses_commission": False, "real_world_tested": False},
        "decision_summary": {"options": [{"product_ref": "a"}]},
        "evidence": ["unknown-evidence"],
    }
    assert validate_experience(experience, product_refs=frozenset({"a"}), evidence_refs=frozenset()) == (
        "status_check.recommendation_forbidden", "evidence.unresolved_reference",
    )


def test_projection_omits_unverified_commerce_and_preserves_sources_and_dates() -> None:
    root = Path(__file__).resolve().parents[2]
    markup = (root / "changes/wordpress-local-preview-v1/fixtures/articles/countertop-dishwasher-for-small-households.html").read_text()
    result = project_article(markup, article_id="st1704-countertop-dishwasher-for-small-households", experience={"article_type": "shortlist"})
    parsed = fragment(result)
    assert not parsed.find(cls="raos-product-card__media")
    assert not parsed.find(cls="raos-product-image-status")
    assert not any("data-raos-placement" in e.attrs for e in parsed.find(tag="a"))
    assert "2026年9月1日" in result
    assert "SS-M171" in result and "TK-MDW22W" in result
    original_sources = {n.attrs["href"] for n in fragment(markup).find(tag="a") if "data-raos-placement" not in n.attrs and str(n.attrs.get("href", "")).startswith("https://")}
    assert original_sources <= {n.attrs.get("href") for n in parsed.find(tag="a")}
    assert len(parsed.find(cls="raos-article-facts")) == 1
    assert project_article(result, article_id="st1704-countertop-dishwasher-for-small-households", experience={"article_type": "shortlist"}) == result


def test_repeated_projection_rechecks_offers_when_evidence_is_removed() -> None:
    markup = '<div class="raos-editorial-v2"><span class="raos-reader-view" hidden></span><p class="summary-action"><a data-raos-product-id="a" data-raos-placement="product_card" href="https://example.test/offer">Offer</a></p><p>UNKNOWN</p></div>'
    result = project_article(markup, article_id="example")
    assert "example.test" not in result and "UNKNOWN" in result


def test_registered_view_cannot_relabel_a_status_article(tmp_path) -> None:
    import json
    import shutil
    import pytest
    from raos.application.editorial.reader_experience_projection import load_experiences, REGISTRY_PATH
    root = Path(__file__).resolve().parents[2]
    for relative in (REGISTRY_PATH, Path('changes/editorial-portfolio-v2/editorial-portfolio.v2.json'), Path('changes/editorial-portfolio-v3/editorial-identities.v1.json'), Path('changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json')):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    assert load_experiences(tmp_path)['solota-vs-rakua-mini-plus']['article_type'] == 'status_check'
    path = tmp_path / REGISTRY_PATH
    registry = json.loads(path.read_text())
    registry['articles']['solota-vs-rakua-mini-plus']['article_type'] = 'comparison'
    path.write_text(json.dumps(registry))
    with pytest.raises(ValueError, match='INTENT_MISMATCH'):
        load_experiences(tmp_path)


def test_unverified_experience_rejects_positive_claims_but_accepts_limits() -> None:
    base = {'article_type':'shortlist', 'research_status':{'real_world_tested':False,'ranking_uses_commission':False}}
    for statement in ('実際に使って洗浄力を確認しました。', '使ってみると音が静かでした。'):
        assert 'research_status.unverified_experience_claim' in validate_experience({**base,'dek':statement},product_refs=frozenset(),evidence_refs=frozenset())
    for statement in ('実際に使ってはいません。', '使ってみたときの洗浄力は未確認です。'):
        assert not validate_experience({**base,'dek':statement},product_refs=frozenset(),evidence_refs=frozenset())
