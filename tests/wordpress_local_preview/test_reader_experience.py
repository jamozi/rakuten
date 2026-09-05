from dataclasses import replace

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
