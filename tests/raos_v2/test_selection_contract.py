from dataclasses import replace
from dataclasses import fields
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import inspect

import pytest
import yaml

from raos.adapters.decision_support_v2.recorded_catalog import RecordedProductCatalog
from raos.domain.decision_support_v2.business import BusinessObservation
from raos.domain.decision_support_v2.models import (
    CtaState,
    FreshnessState,
    IdentityStatus,
    MediaState,
    OfferObservation,
    OfferStatus,
    cta_state_for_offer,
)
from raos.domain.decision_support_v2.media import (
    MediaBinding,
    media_binding_digest,
    resolve_offer_media,
)
from raos.domain.decision_support_v2.selection import (
    FitInputs,
    rank_products,
    render_semantic_hash,
)


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "changes/raos-v2/phase-2/data/ace-carry-on-models.v2.json"
MEDIA_POLICY = ROOT / "changes/raos-v2/phase-2/media/media-policy.v2.yaml"
CHECKED = datetime.fromisoformat("2026-08-26T13:54:33+09:00")


def _input(product_id: str, *, compatibility: str = "1") -> FitInputs:
    product = RecordedProductCatalog.from_file(CATALOG).get(product_id)
    assert product is not None
    return FitInputs(
        product=product,
        checked_at=CHECKED,
        compatibility=Decimal(compatibility),
        declared_constraint=Decimal("1"),
        verified_spec=Decimal("1"),
        tradeoff_clarity=Decimal("1"),
        evidence_freshness=FreshnessState.FRESH,
        hard_constraint_pass=True,
    )


def test_catalog_contains_only_exact_three_models_and_no_offer_fields() -> None:
    catalog = RecordedProductCatalog.from_file(CATALOG)
    assert {product.model_number for product in catalog.all()} == {
        "06316",
        "05721",
        "01471",
    }
    assert not any(hasattr(product, "price") for product in catalog.all())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mass_kg", Decimal("0")),
        ("capacity_l", Decimal("0")),
        ("expanded_capacity_l", Decimal("0")),
    ],
)
def test_product_variant_quantities_must_be_positive(
    field: str, value: Decimal
) -> None:
    variant = _input("PRD-ACE-CRESTA-06316").product.variants[0]
    with pytest.raises(ValueError):
        replace(variant, **{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("product_id", ""),
        ("manufacturer", ""),
        ("official_source_ids", ()),
        ("official_source_ids", ("not-a-source",)),
    ],
)
def test_product_model_identifiers_and_source_binding_fail_closed(
    field: str, value: object
) -> None:
    product = _input("PRD-ACE-CRESTA-06316").product
    with pytest.raises(ValueError):
        replace(product, **{field: value})


def test_t_v2_028_hard_ineligible_product_cannot_rank() -> None:
    candidate = replace(_input("PRD-ACE-CRESTA-06316"), hard_constraint_pass=False)
    assert rank_products((candidate,)) == ()


def test_ambiguous_identity_cannot_rank() -> None:
    candidate = _input("PRD-ACE-CRESTA-06316")
    candidate = replace(
        candidate,
        product=replace(candidate.product, identity_status=IdentityStatus.AMBIGUOUS),
    )
    assert rank_products((candidate,)) == ()


@pytest.mark.parametrize(
    "freshness", [FreshnessState.UNAVAILABLE, FreshnessState.REJECTED]
)
def test_unavailable_or_rejected_evidence_cannot_rank(
    freshness: FreshnessState,
) -> None:
    candidate = replace(_input("PRD-ACE-CRESTA-06316"), evidence_freshness=freshness)
    assert rank_products((candidate,)) == ()


def test_t_v2_029_fit_order_and_lexical_tie_are_deterministic() -> None:
    candidates = (
        _input("PRD-ACE-MAXPASS4-01471", compatibility="0.8"),
        _input("PRD-ACE-DIFFERENCE-05721", compatibility="0.8"),
        _input("PRD-ACE-CRESTA-06316", compatibility="1"),
    )
    ranked = rank_products(candidates)
    assert [item.product_id for item in ranked] == [
        "PRD-ACE-CRESTA-06316",
        "PRD-ACE-DIFFERENCE-05721",
        "PRD-ACE-MAXPASS4-01471",
    ]


def test_t_v2_030_finance_mutation_cannot_change_order_or_render_hash() -> None:
    candidates = (
        _input("PRD-ACE-CRESTA-06316"),
        _input("PRD-ACE-DIFFERENCE-05721", compatibility="0.9"),
    )
    ranked = rank_products(candidates)
    digest = render_semantic_hash(ranked)
    low = BusinessObservation("ARTICLE", Decimal("1"), 10, 100, Decimal("10"))
    high = BusinessObservation("ARTICLE", Decimal("999999"), 1, 1, Decimal("0"))
    assert low.confirmed_epc != high.confirmed_epc
    assert rank_products(candidates) == ranked
    assert render_semantic_hash(rank_products(candidates)) == digest
    assert tuple(inspect.signature(rank_products).parameters) == ("candidates",)
    assert not {
        "business_score",
        "confirmed_epc",
        "commission",
        "price",
        "revenue",
    } & {field.name for field in fields(type(ranked[0]))}
    selection_source = (
        ROOT / "python/raos/domain/decision_support_v2/selection.py"
    ).read_text(encoding="utf-8")
    assert "decision_support_v2.business" not in selection_source


def test_cta_requires_complete_offer_and_exact_identity_binding() -> None:
    product = _input("PRD-ACE-CRESTA-06316").product
    base = OfferObservation(
        offer_id="RECORDED",
        product_id=product.product_id,
        provider="RAKUTEN_RECORDED",
        item_code="shop:item",
        shop_code="shop",
        observed_at=CHECKED,
        affiliate_url_ref="AFFILIATE-REF-NOT-A-URL",
        image_ref=None,
        identity_evidence=("EXACT",),
        status=OfferStatus.CURRENT,
        in_stock=True,
    )
    no_image = resolve_offer_media(
        base, declared_state=MediaState.NO_IMAGE_INTENTIONAL, binding=None
    )
    assert no_image.render_kind == "NEUTRAL_PLACEHOLDER"
    assert (
        cta_state_for_offer(
            product, base, media_state=no_image.state, evaluated_at=CHECKED
        )
        is CtaState.AVAILABLE
    )
    assert (
        cta_state_for_offer(
            product,
            replace(base, item_code=None),
            media_state=no_image.state,
            evaluated_at=CHECKED,
        )
        is CtaState.UNAVAILABLE
    )
    assert (
        cta_state_for_offer(
            product,
            replace(base, identity_evidence=("AMBIGUOUS",)),
            media_state=no_image.state,
            evaluated_at=CHECKED,
        )
        is CtaState.BLOCKED
    )
    assert (
        cta_state_for_offer(
            product,
            replace(base, status=OfferStatus.IDENTITY_BLOCKED),
            media_state=no_image.state,
            evaluated_at=CHECKED,
        )
        is CtaState.BLOCKED
    )
    assert (
        cta_state_for_offer(
            product,
            replace(base, in_stock=False),
            media_state=no_image.state,
            evaluated_at=CHECKED,
        )
        is CtaState.UNAVAILABLE
    )
    assert (
        cta_state_for_offer(
            product,
            replace(base, in_stock=None),
            media_state=no_image.state,
            evaluated_at=CHECKED,
        )
        is CtaState.UNAVAILABLE
    )

    assert (
        cta_state_for_offer(
            product,
            base,
            media_state=no_image.state,
            evaluated_at=CHECKED + timedelta(hours=24),
        )
        is CtaState.UNAVAILABLE
    )
    assert (
        cta_state_for_offer(
            product,
            base,
            media_state=no_image.state,
            evaluated_at=CHECKED + timedelta(hours=23, minutes=59, seconds=59),
        )
        is CtaState.AVAILABLE
    )
    assert (
        cta_state_for_offer(
            product,
            base,
            media_state=no_image.state,
            evaluated_at=CHECKED - timedelta(microseconds=1),
        )
        is CtaState.BLOCKED
    )
    with pytest.raises(ValueError, match="evaluated_at must be timezone-aware"):
        cta_state_for_offer(
            product,
            base,
            media_state=no_image.state,
            evaluated_at=datetime(2026, 8, 26, 13, 54, 33),
        )


def test_t_v2_044_image_requires_exact_sealed_media_provenance() -> None:
    product = _input("PRD-ACE-CRESTA-06316").product
    offer = OfferObservation(
        offer_id="RECORDED-IMAGE",
        product_id=product.product_id,
        provider="RAKUTEN_RECORDED",
        item_code="shop:item",
        shop_code="shop",
        observed_at=CHECKED,
        affiliate_url_ref="AFFILIATE-REF-NOT-A-URL",
        image_ref="OPAQUE-IMAGE-REF",
        identity_evidence=("EXACT",),
        status=OfferStatus.CURRENT,
        in_stock=True,
    )
    payload = {
        "source_id": "SRC-RAKUTEN-MEDIA-SYNTHETIC",
        "offer_id": offer.offer_id,
        "product_id": offer.product_id,
        "item_code": offer.item_code,
        "image_ref": offer.image_ref,
        "content_sha256": "5" * 64,
        "alt_text": "ACE クレスタ 06316 の商品画像",
        "checked_at": offer.observed_at.isoformat(),
    }
    assert all(isinstance(value, str) for value in payload.values())
    binding = MediaBinding(
        source_id=payload["source_id"],
        offer_id=payload["offer_id"],
        product_id=payload["product_id"],
        item_code=payload["item_code"],
        image_ref=payload["image_ref"],
        content_sha256=payload["content_sha256"],
        alt_text=payload["alt_text"],
        checked_at=CHECKED,
        binding_sha256=media_binding_digest(payload),
    )
    eligible = resolve_offer_media(
        offer, declared_state=MediaState.ELIGIBLE, binding=binding
    )
    assert eligible.state is MediaState.ELIGIBLE
    assert eligible.render_ref == "OPAQUE-IMAGE-REF"
    assert (
        cta_state_for_offer(
            product, offer, media_state=eligible.state, evaluated_at=CHECKED
        )
        is CtaState.AVAILABLE
    )

    unbound = resolve_offer_media(
        offer, declared_state=MediaState.ELIGIBLE, binding=None
    )
    assert unbound.state is MediaState.BLOCKED
    assert unbound.render_ref is None
    assert (
        cta_state_for_offer(
            product, offer, media_state=unbound.state, evaluated_at=CHECKED
        )
        is CtaState.BLOCKED
    )

    modified = resolve_offer_media(
        offer,
        declared_state=MediaState.ELIGIBLE,
        binding=replace(binding, content_sha256="6" * 64),
    )
    assert modified.state is MediaState.BLOCKED
    assert modified.reason_codes == ("MEDIA_BINDING_MODIFIED",)
    assert modified.render_ref is None
    assert (
        cta_state_for_offer(
            product, offer, media_state=modified.state, evaluated_at=CHECKED
        )
        is CtaState.BLOCKED
    )
    with pytest.raises(ValueError):
        replace(binding, image_ref="javascript:alert")

    wrong_item = replace(
        binding,
        item_code="other:item",
        binding_sha256=media_binding_digest({**payload, "item_code": "other:item"}),
    )
    mismatch = resolve_offer_media(
        offer, declared_state=MediaState.ELIGIBLE, binding=wrong_item
    )
    assert mismatch.state is MediaState.BLOCKED
    assert mismatch.reason_codes == ("MEDIA_BINDING_MISMATCH",)


def test_t_v2_044_no_image_requires_explicit_neutral_placeholder_intent() -> None:
    product = _input("PRD-ACE-CRESTA-06316").product
    offer = OfferObservation(
        offer_id="RECORDED-NO-IMAGE",
        product_id=product.product_id,
        provider="RAKUTEN_RECORDED",
        item_code="shop:item",
        shop_code="shop",
        observed_at=CHECKED,
        affiliate_url_ref="AFFILIATE-REF-NOT-A-URL",
        image_ref=None,
        identity_evidence=("EXACT",),
        status=OfferStatus.CURRENT,
        in_stock=True,
    )
    unresolved = resolve_offer_media(
        offer, declared_state=MediaState.ELIGIBLE, binding=None
    )
    assert unresolved.state is MediaState.BLOCKED
    assert (
        cta_state_for_offer(
            product, offer, media_state=unresolved.state, evaluated_at=CHECKED
        )
        is CtaState.BLOCKED
    )
    intentional = resolve_offer_media(
        offer, declared_state=MediaState.NO_IMAGE_INTENTIONAL, binding=None
    )
    assert intentional.state is MediaState.NO_IMAGE_INTENTIONAL
    assert intentional.render_kind == "NEUTRAL_PLACEHOLDER"

    policy = yaml.safe_load(MEDIA_POLICY.read_text(encoding="utf-8"))
    registry = {row["product_id"]: row for row in policy["product_registry"]}
    assert registry[product.product_id] == {
        "product_id": product.product_id,
        "state": "NO_IMAGE_INTENTIONAL",
        "image_binding": None,
        "render": "NEUTRAL_PLACEHOLDER",
    }
