"""Synthetic pure-contract examples: no actual audit, owner approval or release."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any
from urllib.parse import urlencode

import pytest

from raos.application.editorial import verified_incremental_release_v1 as release
from raos.application.editorial import verified_incremental_v1 as manifest
from raos.application.editorial.editorial_portfolio_v2 import ProductEvidenceViewV2
from raos.application.editorial.verified_incremental_audit_v1 import (
    IncrementalAuditScopeV1,
    VerifiedIncrementalAuditBindingV1,
)
from raos.application.editorial.verified_incremental_sources_v1 import (
    SelectedOfficialSourceReceiptV1,
    SelectedOfficialSourcesV1,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    RakutenProductEvidence,
    canonical_sha256,
)

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


def stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def sample() -> tuple[dict[str, Any], dict[str, Any]]:
    inventory = {
        "guide": manifest.ExistingDocument(19, "guide", "post", "a" * 64),
        "older": manifest.ExistingDocument(28, "older", "post", "b" * 64),
        "home": manifest.ExistingDocument(15, "home", "page", "c" * 64),
    }
    targets = {"article-1": ("guide", 19), "article-2": ("older", 28)}
    artifacts = {
        "local-guide": b"<div><h2>Reference</h2><p>Verified identity only.</p></div>",
        "production-guide": b"<div><h2>Reference</h2><p>Verified identity only.</p></div>",
    }
    contracts = {"source_registry": "d" * 64, "locator_contract": "e" * 64}
    receipt = SelectedOfficialSourceReceiptV1(
        "source-1",
        stamp(NOW - timedelta(hours=1)),
        stamp(NOW + timedelta(hours=23)),
        "f" * 64,
        "1" * 64,
        "2" * 64,
        "3" * 64,
        contracts,
        {"claim-1": "4" * 64},
    )
    sources = SelectedOfficialSourcesV1(
        ("source-article-1",),
        {"source-article-1": {"claim-1": ("source-1",)}},
        {"source-article-1": ("source-1",)},
        {"source-1": receipt},
        (),
        contracts,
        stamp(NOW),
    )
    document = {
        "schema": manifest.SCHEMA,
        "publication_profile": manifest.PROFILE,
        "link_mode": "standard-api",
        "measurement_collection_enabled": False,
        "publication_authority": False,
        "evaluated_at": stamp(NOW),
        "expires_at": stamp(NOW + timedelta(minutes=15)),
        "articles": [
            {
                "article_id": "article-1",
                "post_id": 19,
                "slug": "guide",
                "baseline_sha256": "a" * 64,
                "editorial_product_ids": [],
                "claim_ids": ["claim-1"],
                "source_receipts": sources.source_receipt_sha256,
                "images": {},
                "ctas": {},
                "excluded_commerce": {},
                "local_artifact": {
                    "key": "local-guide",
                    "sha256": manifest.digest(artifacts["local-guide"]),
                },
                "production_artifact": {
                    "key": "production-guide",
                    "sha256": manifest.digest(artifacts["production-guide"]),
                },
            }
        ],
        "unchanged_documents": {"older": "b" * 64, "home": "c" * 64},
        "shared_artifacts": {},
        "rendered_document_slugs": ["guide"],
    }
    validated = manifest.validate_manifest(
        document,
        inventory=inventory,
        article_targets=targets,
        shared_baseline_sha256={},
        article_products={"article-1": []},
        article_claims={"article-1": ["claim-1"]},
        claim_sources={"claim-1": ["source-1"]},
        source_receipt_sha256=sources.source_receipt_sha256,
        verified_image_sha256={},
        verified_cta_sha256={},
        image_article_products={},
        cta_article_products={},
        artifact_bytes=artifacts,
        now=NOW,
    )
    scope = IncrementalAuditScopeV1(
        ("article-1",),
        ("article-1", "article-2"),
        ("article-1",),
        False,
        {"article-1": ("claim-1",)},
    )
    audit = VerifiedIncrementalAuditBindingV1(
        "5" * 64,
        validated.manifest_sha256,
        release._digest(scope.to_document()),
        release._digest({key: manifest.digest(raw) for key, raw in artifacts.items()}),
        "6" * 64,
        stamp(NOW),
        stamp(NOW + timedelta(minutes=10)),
        "OWNER_CONFIRMED",
    )
    return document, {
        "validated_manifest": validated,
        "audit_binding": audit,
        "audit_scope": scope,
        "official_sources": sources,
        "artifact_bytes": artifacts,
        "audit_artifact_bytes": dict(artifacts),
        "inventory": inventory,
        "article_targets": targets,
        "commerce_views": {},
        "image_article_products": {},
        "cta_bindings": {},
        # Synthetic ContentDocumentV1 projection digest, deliberately not HTML.
        "expected_production_content_sha256": {"guide": "7" * 64},
        "expected_shared_readback_sha256": {},
        "source_article_id_by_article_id": {"article-1": "source-article-1"},
        "now": NOW,
    }


def build(document=None, inputs=None):
    if document is None:
        document, inputs = sample()
    return release.build_verified_incremental_release_v1(document, **inputs)


def reseal(document, inputs) -> None:
    """Synthetic upstream replay result for a deliberately changed test input."""
    row = document["articles"][0]
    for mode in ("local", "production"):
        artifact = row[f"{mode}_artifact"]
        artifact["sha256"] = manifest.digest(inputs["artifact_bytes"][artifact["key"]])
    row["source_receipts"] = inputs["official_sources"].source_receipt_sha256
    inputs["audit_artifact_bytes"] = dict(inputs["artifact_bytes"])
    inputs["validated_manifest"] = manifest.validate_manifest(
        document,
        inventory=inputs["inventory"],
        article_targets=inputs["article_targets"],
        shared_baseline_sha256={"theme": "9" * 64},
        article_products={"article-1": row["editorial_product_ids"]},
        article_claims={"article-1": ["claim-1"]},
        claim_sources={"claim-1": ["source-1"]},
        source_receipt_sha256=inputs["official_sources"].source_receipt_sha256,
        verified_image_sha256=row["images"],
        verified_cta_sha256=row["ctas"],
        image_article_products=inputs["image_article_products"],
        cta_article_products={
            key: value[:2] for key, value in inputs["cta_bindings"].items()
        },
        artifact_bytes=inputs["artifact_bytes"],
        now=NOW,
    )
    inputs["audit_scope"] = replace(
        inputs["audit_scope"],
        retained_product_ids=tuple(row["editorial_product_ids"]),
        affiliate_cta_ids=tuple(row["ctas"]),
        product_image_ids=tuple(row["images"]),
        shared_changes=bool(document["shared_artifacts"]),
        required_noncontent_rollback_targets=tuple(
            sorted(set(document["shared_artifacts"]) & {"theme", "seo", "plugins"})
        ),
        rendered_article_ids=("article-1", "article-2")
        if document["shared_artifacts"]
        else ("article-1",),
    )
    inputs["audit_binding"] = replace(
        inputs["audit_binding"],
        manifest_sha256=inputs["validated_manifest"].manifest_sha256,
        scope_sha256=release._digest(inputs["audit_scope"].to_document()),
        artifact_bundle_sha256=release._digest(
            {key: manifest.digest(raw) for key, raw in inputs["artifact_bytes"].items()}
        ),
    )


def product_view(captured: datetime) -> ProductEvidenceViewV2:
    """Valid domain-schema synthetic record, never a real provider attestation."""
    item_url = "https://item.rakuten.co.jp/test-shop/unit/"
    destination = "https://hb.afl.rakuten.co.jp/hgc/test.abc/?" + urlencode(
        {
            "m": "https://m.rakuten.co.jp/test-shop/i/unit/",
            "pc": item_url,
            "rafcid": "synthetic-test",
        }
    )
    image_url = "https://thumbnail.image.rakuten.co.jp/@0_mall/test-shop/cabinet/unit.jpg?_ex=128x128"
    request = {
        "api_version": "2026-07-01",
        "elements": ["itemCode", "itemName", "itemUrl", "mediumImageUrls"],
        "endpoint": "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701",
        "format": "json",
        "format_version": 2,
        "affiliate_id_supplied": False,
        "image_flag": 1,
        "item_code": "test-shop:unit",
        "schema": "RAOS_ST1704_RAKUTEN_ITEM_SEARCH_REQUEST_V1",
        "secret_fields_excluded": ["accessKey", "affiliateId", "applicationId"],
    }
    identity = {
        "image_url": image_url,
        "item_code": "test-shop:unit",
        "item_name": "Synthetic unit",
        "jan": None,
        "schema": "RAOS_ST1704_RAKUTEN_PROVIDER_IDENTITY_V1",
        "source_url": item_url,
    }
    affiliate_identity = {
        "affiliate_url": destination,
        "image_url": image_url,
        "item_code": "test-shop:unit",
        "item_name": "Synthetic unit",
        "item_url": destination,
        "jan": None,
        "schema": "RAOS_ST1704_RAKUTEN_AFFILIATE_PROVIDER_IDENTITY_V1",
    }
    evidence = RakutenProductEvidence(
        product_id="PRD-ONE",
        affiliate_ref="synthetic-affiliate",
        media_asset_ref="synthetic-media",
        item_code="test-shop:unit",
        item_name="Synthetic unit",
        jan=None,
        variant="new-black",
        source_url=item_url,
        destination_url=destination,
        image_url=image_url,
        width=128,
        height=128,
        retrieved_at=stamp(captured),
        request_fingerprint=canonical_sha256(request),
        response_sha256="a" * 64,
        selected_result_sha256=canonical_sha256(identity),
        affiliate_request_fingerprint=canonical_sha256(
            {
                **request,
                "affiliate_id_supplied": True,
                "elements": ["affiliateUrl", *request["elements"]],
            }
        ),
        affiliate_response_sha256="b" * 64,
        affiliate_selected_result_sha256=canonical_sha256(affiliate_identity),
        image_sha256="c" * 64,
        no_modification_policy=tuple(
            (key, False)
            for key in (
                "aspect_ratio_change_allowed",
                "crop_allowed",
                "modification_allowed",
                "text_overlay_allowed",
                "upscale_allowed",
            )
        ),
    )
    return ProductEvidenceViewV2(
        "PRD-ONE", "verified", stamp(captured), evidence, "jpg"
    )


def commercial_sample(captured=NOW):
    document, inputs = sample()
    view = product_view(captured)
    evidence = view.evidence
    assert evidence is not None
    inputs["commerce_views"] = {"PRD-ONE": view}
    inputs["image_article_products"] = {"image-1": ("article-1", "PRD-ONE")}
    inputs["cta_bindings"] = {
        "cta-1": ("article-1", "PRD-ONE", "product_card"),
        "cta-2": ("article-1", "PRD-ONE", "final_summary"),
    }
    row = document["articles"][0]
    row.update(
        editorial_product_ids=["PRD-ONE"],
        images={"image-1": evidence.image_sha256},
        ctas={
            key: release.commerce_receipt_sha256(view) for key in inputs["cta_bindings"]
        },
    )
    markup = '<div><article class="product-profile" data-raos-product-id="PRD-ONE"><h3>Unit</h3>'
    markup += f'<img data-raos-product-image-id="PRD-ONE" data-raos-product-image-state="verified" src="{escape(evidence.image_url)}" width="128" height="128" alt="Unit" loading="lazy">'
    for key, (_article, product, placement) in inputs["cta_bindings"].items():
        markup += f'<a data-raos-cta-id="{key}" data-raos-article-id="article-1" data-raos-product-id="{product}" data-raos-placement="{placement}" rel="sponsored nofollow" href="{escape(evidence.destination_url)}">Check</a>'
    for key in inputs["artifact_bytes"]:
        inputs["artifact_bytes"][key] = (markup + "</article></div>").encode()
    reseal(document, inputs)
    return document, inputs


def test_standard_api_same_url_reuse_succeeds_and_product_expiry_is_shortest() -> None:
    document, inputs = commercial_sample(
        NOW - timedelta(hours=24) + timedelta(seconds=45)
    )
    context = build(document, inputs)
    assert context.expires_at == NOW + timedelta(seconds=45)
    assert context.to_document()["commerce_state"] == "VERIFIED_PRESENT"
    assert set(context.to_document()["product_receipts"]) == {"PRD-ONE"}


@pytest.mark.parametrize("age", [timedelta(hours=24), timedelta(seconds=-1)])
def test_expired_or_future_product_replay_cannot_pass(age) -> None:
    document, inputs = commercial_sample(NOW - age)
    with pytest.raises(manifest.IncrementalPublicationFailure, match="PRODUCT_EXPIRED"):
        build(document, inputs)


@pytest.mark.parametrize(
    "old,new",
    [
        ('alt="Unit"', 'alt=""'),
        ('width="128"', 'width="0"'),
        ('rel="sponsored nofollow"', 'rel="nofollow"'),
        ('data-raos-cta-id="cta-2"', 'data-raos-cta-id="cta-other"'),
        ('data-raos-product-id="PRD-ONE"', 'data-raos-product-id="PRD-OTHER"'),
        ("cabinet/unit.jpg", "cabinet/different.jpg"),
        ("rafcid=synthetic-test", "rafcid=changed"),
    ],
)
def test_rehashed_html_cannot_substitute_product_image_url_or_slot(old, new) -> None:
    document, inputs = commercial_sample()
    inputs["artifact_bytes"]["production-guide"] = inputs["artifact_bytes"][
        "production-guide"
    ].replace(old.encode(), new.encode())
    reseal(document, inputs)
    with pytest.raises(manifest.IncrementalPublicationFailure, match="HTML_"):
        build(document, inputs)


def test_official_source_expiry_can_be_shorter_than_audit_or_manifest() -> None:
    document, inputs = sample()
    sources = inputs["official_sources"]
    receipt = replace(
        sources.sources["source-1"],
        retrieved_at=stamp(NOW - timedelta(hours=24) + timedelta(seconds=25)),
        expires_at=stamp(NOW + timedelta(seconds=25)),
    )
    inputs["official_sources"] = replace(sources, sources={"source-1": receipt})
    reseal(document, inputs)
    assert build(document, inputs).expires_at == NOW + timedelta(seconds=25)


def supporting_source_sample():
    """Synthetic capture-plan terms source, deliberately not an article claim."""
    document, inputs = sample()
    sources = inputs["official_sources"]
    policy = replace(
        sources.sources["source-1"],
        source_ref="policy-source",
        claim_statement_sha256={},
    )
    inputs["official_sources"] = replace(
        sources,
        sources={**sources.sources, "policy-source": policy},
        article_source_refs={"source-article-1": ("policy-source", "source-1")},
    )
    bind_source_replay(inputs)
    return document, inputs


def bind_source_replay(inputs, raw=None):
    """Synthetic audit of the exact source document, never live audit evidence."""
    inputs["audit_artifact_bytes"]["source-replay"] = (
        release.canonical_json_bytes(inputs["official_sources"].to_document())
        if raw is None
        else raw
    )
    inputs["audit_binding"] = replace(
        inputs["audit_binding"],
        artifact_bundle_sha256=release._digest(
            {
                key: manifest.digest(value)
                for key, value in inputs["audit_artifact_bytes"].items()
            }
        ),
    )


def test_supporting_capture_is_bound_without_fabricating_an_article_claim() -> None:
    document, inputs = supporting_source_sample()
    context = build(document, inputs).to_document()
    assert set(document["articles"][0]["source_receipts"]) == {"source-1"}
    assert set(context["source_receipts"]) == {"source-1", "policy-source"}
    assert (
        context["source_receipts"] == inputs["official_sources"].source_receipt_sha256
    )


def test_supporting_capture_requires_a_hash_bound_source_audit() -> None:
    document, inputs = supporting_source_sample()
    inputs["audit_artifact_bytes"].pop("source-replay")
    inputs["audit_binding"] = sample()[1]["audit_binding"]
    with pytest.raises(
        manifest.IncrementalPublicationFailure, match="SOURCE_AUDIT_REQUIRED"
    ):
        build(document, inputs)


@pytest.mark.parametrize(
    "field,value",
    [
        ("body_file_sha256", "a" * 64),
        ("response_sha256", "a" * 64),
        ("evidence_file_sha256", "a" * 64),
        ("locator_binding_sha256", "a" * 64),
        ("claim_statement_sha256", {"unclaimed": "a" * 64}),
        (
            "contract_file_sha256",
            {"source_registry": "a" * 64, "locator_contract": "e" * 64},
        ),
        ("retrieved_at", stamp(NOW - timedelta(hours=2))),
        ("expires_at", stamp(NOW + timedelta(hours=22))),
    ],
)
def test_supporting_receipt_cannot_change_after_audit(field, value) -> None:
    document, inputs = supporting_source_sample()
    sources = inputs["official_sources"]
    inputs["official_sources"] = replace(
        sources,
        sources={
            **sources.sources,
            "policy-source": replace(
                sources.sources["policy-source"], **{field: value}
            ),
        },
    )
    with pytest.raises(manifest.IncrementalPublicationFailure):
        build(document, inputs)


@pytest.mark.parametrize(
    "change",
    [
        "drop-both",
        "missing-receipt",
        "unassigned-receipt",
        "claim-outside-capture",
        "duplicate-ref",
    ],
)
def test_capture_scope_tamper_is_rejected(change) -> None:
    document, inputs = supporting_source_sample()
    sources = inputs["official_sources"]
    records = dict(sources.sources)
    refs = dict(sources.article_source_refs)
    if change in {"drop-both", "missing-receipt"}:
        records.pop("policy-source")
    if change in {"drop-both", "unassigned-receipt"}:
        refs["source-article-1"] = ("source-1",)
    if change == "claim-outside-capture":
        refs["source-article-1"] = ("policy-source",)
    if change == "duplicate-ref":
        refs["source-article-1"] += ("policy-source",)
    inputs["official_sources"] = replace(
        sources, sources=records, article_source_refs=refs
    )
    with pytest.raises(manifest.IncrementalPublicationFailure):
        build(document, inputs)


@pytest.mark.parametrize(
    "variant",
    [
        "invalid-json",
        "noncanonical",
        "extra-field",
        "future-evaluation",
        "predates-capture",
    ],
)
def test_supporting_source_audit_format_and_clock_are_closed(variant) -> None:
    document, inputs = supporting_source_sample()
    observed = inputs["official_sources"].to_document()
    raw = release.canonical_json_bytes(observed)
    if variant == "invalid-json":
        raw = b"not json"
    elif variant == "noncanonical":
        raw += b"\n"
    else:
        if variant == "extra-field":
            observed["unknown"] = True
        else:
            observed["evaluated_at"] = (
                stamp(NOW + timedelta(seconds=1))
                if variant == "future-evaluation"
                else stamp(NOW - timedelta(hours=2))
            )
        raw = release.canonical_json_bytes(observed)
    bind_source_replay(inputs, raw)
    with pytest.raises(
        manifest.IncrementalPublicationFailure, match="SOURCE_AUDIT_INVALID"
    ):
        build(document, inputs)


def test_supporting_source_expiry_and_replay_do_not_extend_activation() -> None:
    document, inputs = supporting_source_sample()
    sources = inputs["official_sources"]
    policy = replace(
        sources.sources["policy-source"],
        retrieved_at=stamp(NOW - timedelta(hours=24) + timedelta(seconds=25)),
        expires_at=stamp(NOW + timedelta(seconds=25)),
    )
    inputs["official_sources"] = replace(
        sources, sources={**sources.sources, "policy-source": policy}
    )
    bind_source_replay(inputs)
    original = build(document, inputs)
    assert original.expires_at == NOW + timedelta(seconds=25)
    inputs["now"] = NOW + timedelta(seconds=10)
    inputs["official_sources"] = replace(
        inputs["official_sources"], evaluated_at=stamp(inputs["now"])
    )
    inputs["activation_evaluated_at"] = NOW
    assert build(document, inputs).sha256 == original.sha256
    inputs["now"] = NOW + timedelta(seconds=25)
    with pytest.raises(manifest.IncrementalPublicationFailure, match="SOURCE_EXPIRED"):
        build(document, inputs)


def test_shared_theme_requires_full_article_audit_and_exact_shared_readback() -> None:
    document, inputs = sample()
    raw = b"synthetic-theme-package"
    inputs["artifact_bytes"]["theme"] = raw
    document["shared_artifacts"] = {
        "theme": {
            "key": "theme",
            "sha256": manifest.digest(raw),
            "baseline_sha256": "9" * 64,
            "post_id": None,
        }
    }
    document["rendered_document_slugs"] = sorted(inputs["inventory"])
    inputs["expected_shared_readback_sha256"] = {"theme": "8" * 64}
    reseal(document, inputs)
    context = build(document, inputs)
    current = dict(inputs["inventory"])
    current["guide"] = replace(current["guide"], content_sha256="7" * 64)
    release.verify_release_readback(
        context,
        current_inventory=current,
        shared_readback_sha256={"theme": "8" * 64},
        now=NOW,
    )
    with pytest.raises(manifest.IncrementalPublicationFailure, match="READBACK_SHARED"):
        release.verify_release_readback(
            context, current_inventory=current, shared_readback_sha256={}, now=NOW
        )
    verified_scope = inputs["audit_scope"]
    inputs["audit_scope"] = replace(
        verified_scope, required_noncontent_rollback_targets=()
    )
    # Even a newly rehashed audit cannot hide the manifest's theme rollback target.
    inputs["audit_binding"] = replace(
        inputs["audit_binding"],
        scope_sha256=release._digest(inputs["audit_scope"].to_document()),
    )
    with pytest.raises(
        manifest.IncrementalPublicationFailure, match="AUDIT_SCOPE_INVALID"
    ):
        build(document, inputs)
    inputs["audit_scope"] = replace(verified_scope, rendered_article_ids=("article-1",))
    with pytest.raises(ValueError, match="SCOPE_INVALID"):
        build(document, inputs)


def test_zero_commerce_has_no_receipt_no_authority_and_shortest_expiry() -> None:
    context = build()
    doc = context.to_document()
    assert doc["commerce_state"] == doc["monetization_state"] == "NOT_INCLUDED"
    assert doc["product_receipts"] == {}
    assert doc["owner_approval_required"] is True
    assert doc["publication_authority"] is False
    assert doc["measurement_collection_enabled"] is False
    assert context.expires_at == NOW + timedelta(minutes=10)
    assert doc["expected_production_content_sha256"]["guide"] == "7" * 64
    assert doc["selected_articles"]["guide"]["production_artifact_sha256"] != "7" * 64


def test_envelope_cannot_be_mutated_via_returned_nested_maps() -> None:
    context = build()
    original = context.sha256
    doc = context.to_document()
    doc["unchanged_documents"].clear()
    doc["inventory"]["older"]["post_id"] = 1000
    assert context.sha256 == original
    assert context.to_document()["unchanged_documents"]


def test_replay_time_does_not_extend_or_change_an_unchanged_envelope() -> None:
    document, inputs = sample()
    first = build(document, inputs)
    inputs["activation_evaluated_at"] = NOW
    inputs["now"] = NOW + timedelta(minutes=1)
    inputs["official_sources"] = replace(
        inputs["official_sources"], evaluated_at=stamp(inputs["now"])
    )
    second = build(document, inputs)
    assert second.sha256 == first.sha256
    assert second.expires_at == first.expires_at


def test_long_lived_audited_subject_gets_only_fifteen_minute_activation() -> None:
    document, inputs = sample()
    document["evaluated_at"] = stamp(NOW - timedelta(hours=2))
    document["expires_at"] = stamp(NOW + timedelta(hours=12))
    inputs["audit_binding"] = replace(
        inputs["audit_binding"], expires_at=document["expires_at"]
    )
    reseal(document, inputs)
    first = build(document, inputs)
    assert first.expires_at == NOW + timedelta(minutes=15)
    assert first.to_document()["evaluated_at"] == stamp(NOW)
    inputs["activation_evaluated_at"] = NOW
    inputs["now"] = NOW + timedelta(minutes=10)
    assert build(document, inputs).sha256 == first.sha256
    inputs["now"] = NOW + timedelta(minutes=15)
    with pytest.raises(ValueError, match="ACTIVATION_EXPIRED"):
        build(document, inputs)
    # The expired original can still be read; it is not reissued or extended.
    assert (
        release.validate_release_envelope(
            first.to_document(),
            current_context=first,
            publication_profile="verified-incremental",
            link_mode="standard-api",
            stage="readback",
            now=inputs["now"],
        )
        == "EXPIRED_READ_ONLY"
    )


@pytest.mark.parametrize(
    "activation",
    [
        NOW - timedelta(seconds=1),
        NOW + timedelta(seconds=1),
        NOW.replace(microsecond=1),
        NOW.replace(tzinfo=None),
    ],
)
def test_activation_must_be_real_canonical_time_after_audit_and_not_in_future(
    activation,
):
    document, inputs = sample()
    inputs["activation_evaluated_at"] = activation
    with pytest.raises(ValueError, match="ACTIVATION_TIME_INVALID"):
        build(document, inputs)


def test_rehashed_activation_cannot_claim_more_than_fifteen_minutes_even_for_readback():
    document = build().to_document()
    document["expires_at"] = stamp(NOW + timedelta(minutes=16))
    forged = release.VerifiedIncrementalReleaseV1(manifest.canonical(document))
    with pytest.raises(ValueError, match="ACTIVATION_WINDOW_INVALID"):
        release.validate_release_envelope(
            document,
            current_context=forged,
            publication_profile="verified-incremental",
            link_mode="standard-api",
            stage="readback",
            now=NOW,
        )


@pytest.mark.parametrize("stage", ["proposal", "resume", "apply", "readback"])
def test_all_stages_use_identical_scope_artifacts_and_mode(stage) -> None:
    context = build()
    assert (
        release.validate_release_envelope(
            context.to_document(),
            current_context=context,
            publication_profile=release.PROFILE,
            link_mode="standard-api",
            stage=stage,
            now=NOW,
        )
        == "FRESH"
    )


@pytest.mark.parametrize("stage", ["proposal", "resume", "apply"])
def test_expired_evidence_cannot_authorize_new_work(stage) -> None:
    context = build()
    with pytest.raises(manifest.IncrementalPublicationFailure, match="EXPIRED"):
        release.validate_release_envelope(
            context.to_document(),
            current_context=context,
            publication_profile=release.PROFILE,
            link_mode="standard-api",
            stage=stage,
            now=context.expires_at,
        )


def test_expired_readback_is_possible_without_refresh_or_permission() -> None:
    document, inputs = sample()
    context = build(document, inputs)
    current = dict(inputs["inventory"])
    current["guide"] = replace(current["guide"], content_sha256="7" * 64)
    report = release.verify_release_readback(
        context,
        current_inventory=current,
        shared_readback_sha256={},
        now=NOW + timedelta(hours=2),
    )
    assert report["evidence_freshness"] == "EXPIRED_READ_ONLY"
    assert report["publication_completed"] is False
    assert report["publication_authority"] is False
    assert context.expires_at == NOW + timedelta(minutes=10)


@pytest.mark.parametrize(
    "field,value",
    [
        ("link_mode", "measured-admin"),
        ("publication_profile", "full"),
        ("measurement_collection_enabled", True),
        ("publication_authority", True),
        ("schema", "RAOS_WORDPRESS_STANDARD_API_BINDING_V1"),
    ],
)
def test_legacy_mode_and_authority_evidence_cannot_be_reused(field, value) -> None:
    document, inputs = sample()
    document[field] = value
    with pytest.raises(manifest.IncrementalPublicationFailure):
        build(document, inputs)
    context = build()
    payload = context.to_document()
    payload[field] = value
    with pytest.raises(manifest.IncrementalPublicationFailure):
        release.validate_release_envelope(
            payload,
            current_context=context,
            publication_profile=release.PROFILE,
            link_mode="standard-api",
            stage="apply",
            now=NOW,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d, i: d["articles"][0].update(claim_ids=[]),
        lambda d, i: i["artifact_bytes"].update({"local-guide": b"changed"}),
        lambda d, i: i["audit_artifact_bytes"].update({"production-guide": b"changed"}),
        lambda d, i: i["source_article_id_by_article_id"].update(
            {"article-1": "article-1"}
        ),
        lambda d, i: i["expected_production_content_sha256"].update(
            {"older": "8" * 64}
        ),
        lambda d, i: i["expected_production_content_sha256"].clear(),
        lambda d, i: i["expected_shared_readback_sha256"].update({"theme": "9" * 64}),
        lambda d, i: i["article_targets"].pop("article-2"),
        lambda d, i: i.update(
            audit_scope=replace(i["audit_scope"], selected_article_ids=("article-2",))
        ),
        lambda d, i: i.update(
            audit_binding=replace(i["audit_binding"], manifest_sha256="9" * 64)
        ),
        lambda d, i: i.update(
            audit_binding=replace(i["audit_binding"], expires_at=stamp(NOW))
        ),
    ],
)
def test_scope_receipt_artifact_and_audit_tamper_rejected(mutation) -> None:
    document, inputs = sample()
    mutation(document, inputs)
    with pytest.raises(ValueError):
        build(document, inputs)


def test_still_present_fallback_or_unverified_cta_is_rejected_even_with_rehashed_manifest() -> (
    None
):
    document, inputs = sample()
    raw = b'<div><a class="raos-cta" href="https://manufacturer.example/">Buy</a></div>'
    inputs["artifact_bytes"]["production-guide"] = raw
    document["articles"][0]["production_artifact"]["sha256"] = manifest.digest(raw)
    # Simulate independently valid hash scope; the release layer still checks
    # actual HTML, which an integrity-only manifest validator does not inspect.
    inputs["validated_manifest"] = replace(
        inputs["validated_manifest"],
        manifest_sha256=release._digest(document),
        articles=(
            replace(
                inputs["validated_manifest"].articles[0],
                production_sha256=manifest.digest(raw),
            ),
        ),
    )
    with pytest.raises(
        manifest.IncrementalPublicationFailure, match="HTML_CTA_UNVERIFIED"
    ):
        build(document, inputs)


def test_source_expiry_is_enforced_even_if_cached_output_claims_verified() -> None:
    document, inputs = sample()
    sources = inputs["official_sources"]
    receipt = replace(
        sources.sources["source-1"],
        retrieved_at=stamp(NOW - timedelta(days=1)),
        expires_at=stamp(NOW),
    )
    inputs["official_sources"] = replace(sources, sources={"source-1": receipt})
    with pytest.raises(manifest.IncrementalPublicationFailure, match="SOURCE_EXPIRED"):
        build(document, inputs)


def test_zero_commerce_rejects_unused_provider_evidence() -> None:
    document, inputs = sample()
    inputs["commerce_views"] = {
        "product-1": ProductEvidenceViewV2("product-1", "unresolved", stamp(NOW), None)
    }
    with pytest.raises(manifest.IncrementalPublicationFailure, match="COMMERCE_SET"):
        build(document, inputs)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda current: current.pop("older"),
        lambda current: current.update(
            new=manifest.ExistingDocument(99, "new", "post", "a" * 64)
        ),
        lambda current: current.update(
            older=replace(current["older"], content_sha256="a" * 64)
        ),
        lambda current: current.update(
            guide=replace(current["guide"], content_sha256="a" * 64)
        ),
        lambda current: current.update(guide=replace(current["guide"], post_id=99)),
        lambda current: current.update(home=replace(current["home"], status="draft")),
        lambda current: current.update(guide=replace(current["guide"], slug="changed")),
    ],
)
def test_readback_preserves_unchanged_complement_identity_and_content(mutation) -> None:
    document, inputs = sample()
    context = build(document, inputs)
    current = deepcopy(inputs["inventory"])
    current["guide"] = replace(current["guide"], content_sha256="7" * 64)
    mutation(current)
    with pytest.raises(manifest.IncrementalPublicationFailure):
        release.verify_release_readback(
            context, current_inventory=current, shared_readback_sha256={}, now=NOW
        )
