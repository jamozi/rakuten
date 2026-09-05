"""Recorded, non-production incremental scope and omission regression tests."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from raos.application.editorial import verified_incremental_v1 as owner


NOW = datetime(2026, 9, 5, 2, 0, tzinfo=UTC)


def sample() -> tuple[dict[str, Any], dict[str, Any]]:
    inventory = {
        "guide": owner.ExistingDocument(19, "guide", "post", "a" * 64),
        "older": owner.ExistingDocument(28, "older", "post", "b" * 64),
        "home": owner.ExistingDocument(15, "home", "page", "c" * 64),
    }
    artifacts = {"local-guide": b"local comparison", "production-guide": b"comparison"}
    document = {
        "schema": owner.SCHEMA,
        "publication_profile": owner.PROFILE,
        "link_mode": "standard-api",
        "measurement_collection_enabled": False,
        "publication_authority": False,
        "evaluated_at": "2026-09-05T02:00:00Z",
        "expires_at": "2026-09-05T02:15:00Z",
        "articles": [
            {
                "article_id": "article-1",
                "post_id": 19,
                "slug": "guide",
                "baseline_sha256": "a" * 64,
                "editorial_product_ids": ["PRD-FIRST", "PRD-SECOND"],
                "claim_ids": ["claim-1"],
                "source_receipts": {"source-1": "d" * 64},
                "images": {},
                "ctas": {},
                "excluded_commerce": {
                    "image-1": "IMAGE_NOT_VERIFIED",
                    "cta-1": "API_IDENTITY_AMBIGUOUS",
                    "image-2": "IMAGE_NOT_VERIFIED",
                    "cta-2": "API_IDENTITY_AMBIGUOUS",
                },
                "local_artifact": {
                    "key": "local-guide",
                    "sha256": owner.digest(artifacts["local-guide"]),
                },
                "production_artifact": {
                    "key": "production-guide",
                    "sha256": owner.digest(artifacts["production-guide"]),
                },
            }
        ],
        "unchanged_documents": {"older": "b" * 64, "home": "c" * 64},
        "shared_artifacts": {},
        "rendered_document_slugs": ["guide"],
    }
    inputs = {
        "inventory": inventory,
        "article_targets": {"article-1": ("guide", 19)},
        "shared_baseline_sha256": {"theme": "d" * 64},
        "article_products": {"article-1": ["PRD-FIRST", "PRD-SECOND"]},
        "article_claims": {"article-1": ["claim-1"]},
        "claim_sources": {"claim-1": ["source-1"]},
        "source_receipt_sha256": {"source-1": "d" * 64},
        "verified_image_sha256": {},
        "verified_cta_sha256": {},
        "image_article_products": {
            "image-1": ("article-1", "PRD-FIRST"),
            "image-2": ("article-1", "PRD-SECOND"),
        },
        "cta_article_products": {
            "cta-1": ("article-1", "PRD-FIRST"),
            "cta-2": ("article-1", "PRD-SECOND"),
        },
        "artifact_bytes": artifacts,
        "now": NOW,
    }
    return document, inputs


def test_editorial_products_do_not_require_unverified_commerce() -> None:
    document, inputs = sample()
    result = owner.validate_manifest(document, **inputs)
    assert result.counts == {
        "articles": 1,
        "editorial_products": 2,
        "images": 0,
        "ctas": 0,
        "monetized_articles": 0,
    }
    assert result.articles[0].monetization_state == "NOT_INCLUDED"
    assert result.manifest_sha256 == owner.digest(owner.canonical(document))


@pytest.mark.parametrize(
    "field,value",
    [
        ("publication_profile", "full"),
        ("link_mode", "measured-admin"),
        ("measurement_collection_enabled", True),
        ("publication_authority", True),
        ("expires_at", "2026-09-06T02:00:01Z"),
        ("expires_at", "2026-09-05T02:00:00Z"),
        ("evaluated_at", "2026-09-05T02:00:01Z"),
        ("articles", []),
    ],
)
def test_profile_authority_and_expiry_are_fail_closed(
    field: str, value: object
) -> None:
    document, inputs = sample()
    document[field] = value
    with pytest.raises(owner.IncrementalPublicationFailure):
        owner.validate_manifest(document, **inputs)


@pytest.mark.parametrize(
    "field,value",
    [
        ("post_id", 0),
        ("post_id", True),
        ("post_id", 20),
        ("slug", "new-page"),
        ("baseline_sha256", "f" * 64),
        ("editorial_product_ids", ["PRD-FIRST"]),
        ("claim_ids", []),
        ("source_receipts", {}),
        ("images", {"image-1": "f" * 64}),
        ("ctas", {"cta-1": "f" * 64}),
        ("excluded_commerce", {}),
    ],
)
def test_target_source_and_commerce_tampering_rejected(
    field: str, value: object
) -> None:
    document, inputs = sample()
    document["articles"][0][field] = value
    with pytest.raises(owner.IncrementalPublicationFailure):
        owner.validate_manifest(document, **inputs)


def test_manifest_cannot_exclude_product_just_because_commerce_missing() -> None:
    document, inputs = sample()
    document["articles"][0]["editorial_product_ids"] = []
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="EDITORIAL_SET_MISMATCH"
    ):
        owner.validate_manifest(document, **inputs)


def test_existing_article_cannot_be_rebound_to_a_different_existing_url() -> None:
    document, inputs = sample()
    document["articles"][0].update(slug="older", post_id=28, baseline_sha256="b" * 64)
    document["unchanged_documents"] = {"guide": "a" * 64, "home": "c" * 64}
    document["rendered_document_slugs"] = ["older"]
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="EXISTING_TARGET_MISMATCH"
    ):
        owner.validate_manifest(document, **inputs)


def test_existing_draft_is_not_a_publication_target() -> None:
    document, inputs = sample()
    inputs["inventory"]["guide"] = replace(inputs["inventory"]["guide"], status="draft")
    with pytest.raises(owner.IncrementalPublicationFailure, match="INVENTORY_INVALID"):
        owner.validate_manifest(document, **inputs)


def test_verified_commerce_exact_placement_set_and_no_owner_flag() -> None:
    document, inputs = sample()
    document["articles"][0]["ctas"] = {"cta-1": "e" * 64}
    del document["articles"][0]["excluded_commerce"]["cta-1"]
    inputs["verified_cta_sha256"] = {"cta-1": "e" * 64}
    result = owner.validate_manifest(document, **inputs)
    assert result.counts["ctas"] == 1
    assert result.articles[0].monetization_state == "VERIFIED_PRESENT"
    document["articles"][0]["owner_attested"] = True
    with pytest.raises(owner.IncrementalPublicationFailure):
        owner.validate_manifest(document, **inputs)


def test_other_articles_evidence_cannot_be_reused() -> None:
    document, inputs = sample()
    document["articles"][0]["ctas"] = {"cta-1": "e" * 64}
    del document["articles"][0]["excluded_commerce"]["cta-1"]
    inputs["verified_cta_sha256"] = {"cta-1": "e" * 64}
    inputs["cta_article_products"]["cta-1"] = ("other-article", "PRD-FIRST")
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="COMMERCE_UNVERIFIED"
    ):
        owner.validate_manifest(document, **inputs)


def test_shared_theme_requires_mixed_preview_including_old_articles() -> None:
    document, inputs = sample()
    inputs["artifact_bytes"]["theme"] = b"theme-package"
    document["shared_artifacts"]["theme"] = {
        "key": "theme",
        "sha256": owner.digest(b"theme-package"),
        "baseline_sha256": "d" * 64,
        "post_id": None,
    }
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="MIXED_PREVIEW_REQUIRED"
    ):
        owner.validate_manifest(document, **inputs)
    document["rendered_document_slugs"] = sorted(inputs["inventory"])
    assert owner.validate_manifest(document, **inputs).shared_artifact_sha256
    document["shared_artifacts"]["theme"]["baseline_sha256"] = "f" * 64
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="SHARED_TARGET_INVALID"
    ):
        owner.validate_manifest(document, **inputs)


def test_source_and_output_replay_hashes_cannot_be_replaced() -> None:
    document, inputs = sample()
    inputs["artifact_bytes"]["production-guide"] = b"unreviewed changes"
    with pytest.raises(owner.IncrementalPublicationFailure, match="ARTIFACT_MISMATCH"):
        owner.validate_manifest(document, **inputs)
    document, inputs = sample()
    inputs["source_receipt_sha256"].clear()
    with pytest.raises(owner.IncrementalPublicationFailure, match="SOURCE_UNVERIFIED"):
        owner.validate_manifest(document, **inputs)


def test_readback_proves_untouched_pages_and_no_new_creation() -> None:
    document, inputs = sample()
    result = owner.validate_manifest(document, **inputs)
    before = inputs["inventory"]
    after = deepcopy(before)
    after["guide"] = replace(after["guide"], content_sha256="f" * 64)
    owner.verify_untouched_documents(result, after, before)
    after["older"] = replace(after["older"], content_sha256="f" * 64)
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="UNTOUCHED_DOCUMENT_CHANGED"
    ):
        owner.verify_untouched_documents(result, after, before)
    after = deepcopy(before)
    after["new"] = owner.ExistingDocument(99, "new", "page", "f" * 64)
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="UNEXPECTED_DOCUMENT"
    ):
        owner.verify_untouched_documents(result, after, before)


def test_omission_removes_whole_frames_and_actions_not_product_or_sources() -> None:
    markup = """<div><a href="#model-purchase">条件を見る</a>
    <article id="model" data-raos-product-id="PRD-FIRST"><h3>商品比較</h3>
    <div class="raos-product-card__media"><p data-raos-product-image-id="PRD-FIRST">未確認</p></div>
    <p>向く条件と妥協点</p><a href="https://example.com/source">公式出典</a>
    <div id="model-purchase" data-raos-purchase-action><p>購入停止</p>
    <a data-raos-product-id="PRD-FIRST" data-raos-placement="product_card" href="https://example.com/">購入</a></div></article>
    <div class="final-summary-action" data-raos-product-id="PRD-FIRST"><a data-raos-product-id="PRD-FIRST" data-raos-placement="final_summary" href="https://example.com/">購入</a></div></div>"""
    result = owner.omit_unverified_commerce(
        markup, image_product_ids=frozenset(), cta_product_ids=frozenset()
    )
    assert 'href="#model"' in result
    assert (
        "商品比較" in result and "向く条件と妥協点" in result and "公式出典" in result
    )
    assert "未確認" not in result and "購入停止" not in result
    assert (
        "data-raos-placement" not in result and "raos-product-card__media" not in result
    )


def test_retained_urls_never_synthesized_or_changed_and_same_product_url_can_repeat() -> (
    None
):
    markup = """<article data-raos-product-id="PRD-FIRST"><div class="raos-product-card__media"><img data-raos-product-image-id="PRD-FIRST" src="https://example.com/image.jpg"></div><div data-raos-purchase-action><a data-raos-product-id="PRD-FIRST" data-raos-placement="product_card" href="https://example.com/exact">購入</a></div><div class="final-summary-action"><a data-raos-product-id="PRD-FIRST" data-raos-placement="final_summary" href="https://example.com/exact">購入</a></div></article>"""
    result = owner.omit_unverified_commerce(
        markup,
        image_product_ids=frozenset({"PRD-FIRST"}),
        cta_product_ids=frozenset({"PRD-FIRST"}),
    )
    assert result == markup
    assert result.count('href="https://example.com/exact"') == 2


@pytest.mark.parametrize(
    "markup",
    [
        "<div><script>alert(1)</script></div>",
        '<div id="a" id="b"></div>',
        "<div><p></div>",
        "<div>",
    ],
)
def test_omission_cannot_silently_repair_unsafe_or_malformed_html(markup: str) -> None:
    with pytest.raises(owner.IncrementalPublicationFailure, match="MARKUP_INVALID"):
        owner.omit_unverified_commerce(
            markup, image_product_ids=frozenset(), cta_product_ids=frozenset()
        )
