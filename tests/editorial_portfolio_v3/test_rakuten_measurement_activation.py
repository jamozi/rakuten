from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
import re
import stat
from types import SimpleNamespace
from typing import Callable, Literal, cast
from urllib.parse import quote

import pytest

import raos.application.editorial.rakuten_measurement_activation_v3 as activation_module
from raos.application.editorial.editorial_portfolio_v2 import (
    ProductEvidenceViewV2,
    load_editorial_portfolio_v2,
    materialize_article_v2,
)
from raos.application.editorial.editorial_portfolio_v3 import (
    PORTFOLIO_RELATIVE_PATH,
    load_editorial_portfolio_v3,
)
from raos.application.editorial.rakuten_measurement_activation_v3 import (
    ADMIN_RECEIPT_SCHEMA,
    DRY_RUN_SCHEMA,
    MONEY_LINK_MAPPING_SCHEMA,
    RakutenMeasurementActivationV3Failure,
    admin_verification_receipt_template_v3,
    materialize_article_html,
    materialize_rakuten_measurement_activation_v3,
    money_link_mapping_template_v3,
    validate_rakuten_measurement_activation_v3,
)
from raos.application.editorial.product_safety_query_capture import (
    ProductSafetyAdministrativeProductEvidence,
)
from raos.application.finance.editorial_economics_v3 import (
    TRUSTED_T0_EVIDENCE_REQUIRED,
    EditorialEconomicsV3Failure,
    canonical_json_bytes,
    establish_t0_receipt,
    production_readback_template,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    RakutenProductEvidence,
)
from scripts.raos_rakuten_measurement_activation_v3 import main as activation_main
from tests.editorial_portfolio_v3.test_economics import _publication_evidence


ROOT = Path(__file__).resolve().parents[2]
_REAL_V2_EVIDENCE_LOADER = activation_module._load_verified_v2_evidence
_SYNTHETIC_SALES_STATE_SHA256 = hashlib.sha256(
    (
        ROOT / "changes/editorial-portfolio-v2/manufacturer-sales-state.v1.json"
    ).read_bytes()
).hexdigest()
_SYNTHETIC_SALES_STATE_CHECKED_AT = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
_SYNTHETIC_V2_PORTFOLIO_SHA256 = hashlib.sha256(
    (ROOT / "changes/editorial-portfolio-v2/editorial-portfolio.v2.json").read_bytes()
).hexdigest()


def _synthetic_product_safety_binding() -> dict[str, object]:
    material: dict[str, object] = {
        "schema": "RAOS_PRODUCT_SAFETY_PUBLICATION_BINDING_V1",
        "required_product_count": 33,
        "required_authority_kinds": [
            "MANUFACTURER_OFFICIAL",
            "JAPAN_ADMINISTRATIVE_OFFICIAL",
        ],
        "required_administrative_capture_count": 99,
        "administrative_bundle_sha256": "9" * 64,
        "administrative_capture_count": 99,
        "administrative_verified_product_count": 33,
        "manufacturer_verified_product_count": 33,
        "complete_product_count": 33,
        "complete": True,
    }
    return {
        **material,
        "binding_sha256": activation_module._compact_json_sha256(material),
    }


def _synthetic_administrative_safety_evidence(
    *,
    now: datetime,
) -> activation_module.ProductSafetyAdministrativeEvidenceSet:
    portfolio = load_editorial_portfolio_v2(ROOT)
    return activation_module.ProductSafetyAdministrativeEvidenceSet(
        schema=activation_module.CAPTURE_BUNDLE_SCHEMA,
        version=activation_module.CAPTURE_BUNDLE_VERSION,
        plan_sha256="8" * 64,
        portfolio_sha256=_SYNTHETIC_V2_PORTFOLIO_SHA256,
        capture_count=99,
        bundle_sha256="9" * 64,
        evaluated_at=now,
        products=tuple(
            ProductSafetyAdministrativeProductEvidence(
                product_id=product.product_id,
                exact_model_tokens=product.official_models,
                status="VERIFIED_NONE_FOUND",
                captures=cast(tuple[object, ...], (object(), object(), object())),
                matched_notice_ids=(),
                stale_provider_scopes=(),
            )
            for product in portfolio.products
        ),
        complete=True,
    )


def _synthetic_image_extension(product_id: str) -> Literal["jpg", "png", "gif"]:
    """Exercise every supported byte-derived extension deterministically."""

    return ("jpg", "png", "gif")[
        hashlib.sha256(product_id.encode("ascii")).digest()[0] % 3
    ]


def _synthetic_image_payload(product_id: str) -> bytes:
    marker = f"verified-image:{product_id}".encode("ascii")
    extension = _synthetic_image_extension(product_id)
    if extension == "jpg":
        return b"\xff\xd8\xff\xe0" + marker + b"\xff\xd9"
    if extension == "png":
        return b"\x89PNG\r\n\x1a\n" + marker
    return b"GIF89a" + marker


def _synthetic_image_url(product_id: str) -> str:
    return (
        "https://thumbnail.image.rakuten.co.jp/@0_mall/test-shop/cabinet/"
        f"{product_id.casefold()}.jpg?_ex=128x128"
    )


def _synthetic_destination_url(product_id: str) -> str:
    return "https://hb.afl.rakuten.co.jp/hgc/v2-test/?pc=" + quote(
        f"https://item.rakuten.co.jp/test-shop/{product_id.casefold()}/",
        safe="",
    )


def _synthetic_provider_binding_sha256(product_id: str, index: int) -> str:
    image_sha256 = hashlib.sha256(_synthetic_image_payload(product_id)).hexdigest()
    return activation_module._compact_json_sha256(
        {
            "product_id": product_id,
            "state": "verified",
            "item_code": f"test-shop:{10000 + index}",
            "destination_url": _synthetic_destination_url(product_id),
            "image_url": _synthetic_image_url(product_id),
            "image_sha256": image_sha256,
            "jan_evidence_sha256": None,
        }
    )


@pytest.fixture(autouse=True)
def _stub_verified_v2_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep activation tests private and deterministic without fake repo secrets."""

    def load(
        _repository_root: Path,
        *,
        now: datetime,
    ) -> activation_module._VerifiedV2EvidenceSet:
        products = load_editorial_portfolio_v2(ROOT).products
        retrieved_at = _SYNTHETIC_SALES_STATE_CHECKED_AT
        return activation_module._VerifiedV2EvidenceSet(
            portfolio_sha256=_SYNTHETIC_V2_PORTFOLIO_SHA256,
            status_sha256="e" * 64,
            manufacturer_sales_state_sha256=_SYNTHETIC_SALES_STATE_SHA256,
            manufacturer_sales_state_checked_at_utc=(_SYNTHETIC_SALES_STATE_CHECKED_AT),
            product_safety=_synthetic_product_safety_binding(),
            products={
                product.product_id: activation_module._VerifiedV2ProductEvidence(
                    product_id=product.product_id,
                    retrieved_at=retrieved_at,
                    provider_binding_sha256=_synthetic_provider_binding_sha256(
                        product.product_id,
                        index,
                    ),
                    image_url=_synthetic_image_url(product.product_id),
                    image_sha256=hashlib.sha256(
                        _synthetic_image_payload(product.product_id)
                    ).hexdigest(),
                    image_extension=_synthetic_image_extension(product.product_id),
                    jan_evidence_sha256=None,
                )
                for index, product in enumerate(products)
            },
        )

    monkeypatch.setattr(activation_module, "_load_verified_v2_evidence", load)


def test_product_safety_gate_replays_99_admin_captures_and_blocks_without_manufacturer_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    portfolio = load_editorial_portfolio_v2(ROOT)
    administrative = _synthetic_administrative_safety_evidence(now=now)
    monkeypatch.setattr(
        activation_module,
        "verify_product_safety_query_capture_set",
        lambda *_args, **_kwargs: administrative,
    )

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_PRODUCT_SAFETY_INCOMPLETE",
    ):
        activation_module._current_product_safety_publication_binding(
            ROOT,
            portfolio,
            now=now,
        )

    monkeypatch.setattr(
        activation_module,
        "_verified_manufacturer_product_safety_ids",
        lambda *_args, **_kwargs: frozenset(
            product.product_id for product in portfolio.products
        ),
    )
    binding = activation_module._current_product_safety_publication_binding(
        ROOT,
        portfolio,
        now=now,
    )
    assert binding["administrative_capture_count"] == 99
    assert binding["manufacturer_verified_product_count"] == 33
    assert binding["complete_product_count"] == 33
    assert binding["complete"] is True
    assert not {
        "query_terms",
        "response_raw",
        "private_path",
        "official_source_url",
    }.intersection(binding)
    assert "://" not in json.dumps(binding, sort_keys=True)


def test_product_safety_public_binding_rejects_self_attested_count_or_hash() -> None:
    for field, value in (
        ("administrative_capture_count", 92),
        ("manufacturer_verified_product_count", 30),
        ("binding_sha256", "f" * 64),
    ):
        binding = _synthetic_product_safety_binding()
        binding[field] = value
        with pytest.raises(
            RakutenMeasurementActivationV3Failure,
            match="RAOS_RAKUTEN_ACTIVATION_PRODUCT_SAFETY_INVALID",
        ):
            activation_module._validate_product_safety_publication_binding(
                binding,
                require_complete=True,
            )


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        )
        + "\n"
    ).encode()


def _private_root(tmp_path: Path) -> Path:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root.resolve()


def _write_private(root: Path, name: str, content: bytes) -> None:
    path = root / name
    path.write_bytes(content)
    os.chmod(path, 0o600)


def _documents() -> tuple[dict[str, object], dict[str, object]]:
    portfolio = load_editorial_portfolio_v3(ROOT)
    v2 = load_editorial_portfolio_v2(ROOT)
    models = {
        product.product_id: product.representative_model for product in v2.products
    }
    portfolio_sha256 = hashlib.sha256(
        (ROOT / PORTFOLIO_RELATIVE_PATH).read_bytes()
    ).hexdigest()
    provider_measurement_ids = {
        slot.provider_slot_id: f"test-provider-{index:02d}"
        for index, slot in enumerate(portfolio.provider_slots, start=1)
    }
    mapping_provider_slots = [
        {
            "provider_slot_id": slot.provider_slot_id,
            "rakuten_measurement_id": provider_measurement_ids[slot.provider_slot_id],
        }
        for slot in portfolio.provider_slots
    ]
    receipt_provider_slots = [
        {
            "provider_slot_id": slot.provider_slot_id,
            "rakuten_measurement_id": provider_measurement_ids[slot.provider_slot_id],
            "csv_echoed_measurement_id": provider_measurement_ids[
                slot.provider_slot_id
            ],
            "admin_console_measurement_id_verified": True,
        }
        for slot in portfolio.provider_slots
    ]
    mapping_rows: list[dict[str, object]] = []
    receipt_money_links: list[dict[str, object]] = []
    for article in portfolio.articles:
        for binding in article.cta_bindings:
            encoded_destination = quote(
                "https://item.rakuten.co.jp/test-shop/"
                f"{binding.product_id.casefold()}/",
                safe="",
            )
            mapping_rows.append(
                {
                    "article_id": binding.article_id,
                    "product_id": binding.product_id,
                    "placement": binding.placement,
                    "provider_slot_id": binding.provider_slot_id,
                    "representative_model": models[binding.product_id],
                    "destination_url": (
                        "https://hb.afl.rakuten.co.jp/hgc/"
                        f"{provider_measurement_ids[binding.provider_slot_id]}/"
                        f"{binding.cta_id}/?pc={encoded_destination}"
                    ),
                }
            )
            receipt_money_links.append(
                {
                    "article_id": binding.article_id,
                    "product_id": binding.product_id,
                    "placement": binding.placement,
                    "provider_slot_id": binding.provider_slot_id,
                    "representative_model": models[binding.product_id],
                    "csv_echoed_representative_model": models[binding.product_id],
                    "money_link_provider_slot_selection_verified": True,
                    "money_link_product_identity_verified": True,
                }
            )
    now = datetime.now(UTC).replace(microsecond=0)
    mapping_generated_at = (now - timedelta(minutes=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    admin_verified_at = (now - timedelta(minutes=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    mapping: dict[str, object] = {
        "schema": MONEY_LINK_MAPPING_SCHEMA,
        "version": "2.0.0",
        "generated_at": mapping_generated_at,
        "portfolio_sha256": portfolio_sha256,
        "provider_slot_count": 20,
        "money_link_count": 74,
        "urls_copied_from_rakuten_admin": True,
        "provider_parameter_inference_used": False,
        "provider_slots": mapping_provider_slots,
        "rows": mapping_rows,
    }
    mapping_sha256 = hashlib.sha256(_json_bytes(mapping)).hexdigest()
    receipt: dict[str, object] = {
        "schema": ADMIN_RECEIPT_SCHEMA,
        "version": "2.0.0",
        "state": "OWNER_VERIFIED_RAKUTEN_ADMIN_AND_CSV",
        "verified_at": admin_verified_at,
        "owner_attested": True,
        "portfolio_sha256": portfolio_sha256,
        "money_link_mapping_sha256": mapping_sha256,
        "provider_slot_count": 20,
        "money_link_count": 74,
        "verification": {
            "all_expected_provider_slots_accepted_by_admin": True,
            "provider_slot_limit_verified": True,
            "character_set_and_length_verified": True,
            "csv_export_verified": True,
            "all_money_links_product_identity_verified": True,
            "provider_parameter_inference_used": False,
            "production_publication_authorized": False,
        },
        "provider_slots": receipt_provider_slots,
        "money_links": receipt_money_links,
    }
    return mapping, receipt


def test_credential_free_templates_cover_all_74_bindings_and_fail_closed() -> None:
    portfolio = load_editorial_portfolio_v3(ROOT)
    template = money_link_mapping_template_v3(
        repository_root=ROOT,
        portfolio=portfolio,
        generated_at="2026-08-30T10:00:00Z",
    )
    rows = cast(list[dict[str, object]], template["rows"])
    slots = cast(list[dict[str, object]], template["provider_slots"])

    assert template["schema"] == MONEY_LINK_MAPPING_SCHEMA
    assert template["urls_copied_from_rakuten_admin"] is False
    assert len(rows) == 74
    assert len(slots) == 20
    assert {slot["rakuten_measurement_id"] for slot in slots} == {None}
    assert all("rakuten_measurement_id" not in row for row in rows)
    assert {row["destination_url"] for row in rows} == {None}
    assert "hb.afl.rakuten.co.jp" not in json.dumps(template)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_MAPPING_INVALID",
    ):
        admin_verification_receipt_template_v3(
            repository_root=ROOT,
            portfolio=portfolio,
            money_link_mapping=_json_bytes(template),
            generated_at="2026-08-30T10:05:00Z",
        )

    mapping, _receipt = _documents()
    admin_template = admin_verification_receipt_template_v3(
        repository_root=ROOT,
        portfolio=portfolio,
        money_link_mapping=_json_bytes(mapping),
        generated_at="2026-08-30T10:05:00Z",
    )
    provider_slots = cast(list[dict[str, object]], admin_template["provider_slots"])
    money_links = cast(list[dict[str, object]], admin_template["money_links"])
    assert len(provider_slots) == 20
    assert len(money_links) == 74
    assert admin_template["state"] == "OWNER_VERIFICATION_REQUIRED"
    assert admin_template["owner_attested"] is False
    assert all(row["csv_echoed_measurement_id"] is None for row in provider_slots)
    assert all(
        row["money_link_product_identity_verified"] is False
        for row in money_links
    )


def _bind_and_write(
    root: Path,
    mapping: dict[str, object],
    receipt: dict[str, object],
) -> None:
    mapping_raw = _json_bytes(mapping)
    receipt["money_link_mapping_sha256"] = hashlib.sha256(mapping_raw).hexdigest()
    _write_private(root, "money-links.json", mapping_raw)
    _write_private(root, "admin-receipt.json", _json_bytes(receipt))


def _rebind_activation_sources_and_dry_run(
    root: Path,
    mapping: dict[str, object],
    receipt: dict[str, object],
    *,
    activated_at: str,
) -> None:
    mapping_raw = _json_bytes(mapping)
    receipt["money_link_mapping_sha256"] = hashlib.sha256(mapping_raw).hexdigest()
    admin_raw = _json_bytes(receipt)
    _write_private(root, "money-links.json", mapping_raw)
    _write_private(root, "admin-receipt.json", admin_raw)
    dry_run_path = root / "activation-dry-run.json"
    dry_run = cast(
        dict[str, object], json.loads(dry_run_path.read_text(encoding="utf-8"))
    )
    dry_run["money_link_mapping_sha256"] = hashlib.sha256(mapping_raw).hexdigest()
    dry_run["admin_receipt_sha256"] = hashlib.sha256(admin_raw).hexdigest()
    activation_inputs = cast(dict[str, object], dry_run["activation_inputs"])
    activation_inputs["mapping_generated_at_utc"] = mapping["generated_at"]
    activation_inputs["admin_verified_at_utc"] = receipt["verified_at"]
    activation_inputs["activated_at_utc"] = activated_at
    _write_private(root, "activation-dry-run.json", _json_bytes(dry_run))


def _v2_pair(root: Path) -> tuple[Path, Path]:
    base = root.parent / "v2"
    local = base / "local"
    production = base / "production"
    media_root = base / "product-media"
    portfolio = load_editorial_portfolio_v2(ROOT)
    sales_audit = portfolio.manufacturer_sales_state_audit
    assert sales_audit is not None
    # Activation mechanics are tested against a hypothetical all-available
    # manufacturer snapshot. The tracked snapshot intentionally contains
    # out-of-stock products and must continue to block real production output.
    portfolio = replace(
        portfolio,
        manufacturer_sales_state_audit=replace(
            sales_audit,
            checked_at_utc=_SYNTHETIC_SALES_STATE_CHECKED_AT,
            document_sha256=_SYNTHETIC_SALES_STATE_SHA256,
            products=tuple(
                replace(
                    product,
                    state="AVAILABLE",
                    checked_at_utc=_SYNTHETIC_SALES_STATE_CHECKED_AT,
                )
                for product in sales_audit.products
            ),
        ),
    )
    portfolio_sha256 = hashlib.sha256(
        (
            ROOT / "changes/editorial-portfolio-v2/editorial-portfolio.v2.json"
        ).read_bytes()
    ).hexdigest()
    posts = (
        ROOT / "changes/wordpress-local-preview-v1/fixtures/posts.json"
    ).read_bytes()
    media_root.mkdir(parents=True)
    media_root.chmod(0o700)
    image_hashes: dict[str, str] = {}
    for product in portfolio.products:
        payload = _synthetic_image_payload(product.product_id)
        image_path = media_root / (
            f"{product.product_id}.{_synthetic_image_extension(product.product_id)}"
        )
        image_path.write_bytes(payload)
        image_path.chmod(0o600)
        image_hashes[product.product_id] = hashlib.sha256(payload).hexdigest()
    products = [
        {
            "product_id": product.product_id,
            "state": "verified",
            "provider_binding_sha256": _synthetic_provider_binding_sha256(
                product.product_id,
                index,
            ),
        }
        for index, product in enumerate(portfolio.products)
    ]
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for mode, fixture_root in (("local", local), ("production", production)):
        article_root = fixture_root / "articles"
        article_root.mkdir(parents=True)
        fixture_root.chmod(0o700)
        article_root.chmod(0o700)
        article_rows = []
        for article in portfolio.articles:
            tracked_source = (
                ROOT
                / "changes/wordpress-local-preview-v1/fixtures/articles"
                / f"{article.production_slug}.html"
            ).read_bytes()
            views = {
                product_id: ProductEvidenceViewV2(
                    product_id=product_id,
                    state="verified",
                    retrieved_at=generated_at,
                    evidence=cast(
                        RakutenProductEvidence,
                        SimpleNamespace(
                            destination_url=(_synthetic_destination_url(product_id)),
                            image_url=_synthetic_image_url(product_id),
                            image_sha256=image_hashes[product_id],
                        ),
                    ),
                    image_extension=_synthetic_image_extension(product_id),
                )
                for product_id in article.product_ids
            }
            source = materialize_article_v2(
                tracked_source.decode("utf-8"),
                article=article,
                portfolio=portfolio,
                evidence_views=cast(dict[str, ProductEvidenceViewV2], views),
                mode=cast(Literal["local", "production"], mode),
            ).encode()
            target = article_root / f"{article.production_slug}.html"
            target.write_bytes(source)
            target.chmod(0o600)
            article_rows.append(
                {
                    "article_id": article.article_id,
                    "production_slug": article.production_slug,
                    "content_sha256": hashlib.sha256(source).hexdigest(),
                }
            )
        posts_path = fixture_root / "posts.json"
        posts_path.write_bytes(posts)
        posts_path.chmod(0o600)
        receipt = {
            "schema": "RAOS_EDITORIAL_PORTFOLIO_MATERIALIZATION_RECEIPT_V2",
            "mode": mode,
            "generated_at": generated_at,
            "portfolio_sha256": portfolio_sha256,
            "evidence_status_sha256": "e" * 64,
            "manufacturer_sales_state_sha256": _SYNTHETIC_SALES_STATE_SHA256,
            "manufacturer_sales_state_checked_at_utc": (
                _SYNTHETIC_SALES_STATE_CHECKED_AT
            ),
            "product_safety": _synthetic_product_safety_binding(),
            "articles": article_rows,
            "products": products,
            "media": [
                {
                    "product_id": product.product_id,
                    "image_sha256": image_hashes[product.product_id],
                    "image_extension": _synthetic_image_extension(product.product_id),
                }
                for product in portfolio.products
            ],
            "completion": {
                "state": "COMPLETE",
                "product_count": len(portfolio.products),
                "verified_product_count": len(portfolio.products),
                "product_card_count": 37,
                "verified_product_card_count": 37,
                "affiliate_cta_count": 74,
                "verified_affiliate_cta_count": 74,
                "neutral_product_image_count": 0,
                "manufacturer_fallback_cta_count": 0,
                "measurement_collection_enabled": False,
            },
        }
        receipt_path = fixture_root / "materialization-receipt.v2.json"
        receipt_path.write_bytes(_json_bytes(receipt))
        receipt_path.chmod(0o600)
    return local.resolve(), production.resolve()


def _run(root: Path) -> dict[str, object]:
    local, production = _v2_pair(root)
    report = materialize_rakuten_measurement_activation_v3(
        repository_root=ROOT,
        private_root=root,
        portfolio=load_editorial_portfolio_v3(ROOT),
        admin_receipt_name="admin-receipt.json",
        money_link_mapping_name="money-links.json",
        dry_run_output_name="activation-dry-run.json",
        local_v2_fixture_root=local,
        production_v2_fixture_root=production,
    )
    return dict(report)


def test_v2_pair_uses_byte_bound_image_extensions_end_to_end(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    local, _production = _v2_pair(private)
    portfolio = load_editorial_portfolio_v2(ROOT)
    receipt = json.loads(
        (local / "materialization-receipt.v2.json").read_text(encoding="utf-8")
    )
    media = cast(list[dict[str, str]], receipt["media"])

    assert {row["image_extension"] for row in media} == {"jpg", "png", "gif"}
    assert {path.name for path in (private.parent / "v2/product-media").iterdir()} == {
        f"{row['product_id']}.{row['image_extension']}" for row in media
    }
    local_markup = "".join(
        path.read_text(encoding="utf-8") for path in (local / "articles").glob("*.html")
    )
    assert ".image" not in local_markup
    for product in portfolio.products:
        expected_source = (
            f"/raos-product-media/{product.product_id}."
            f"{_synthetic_image_extension(product.product_id)}"
        )
        assert expected_source in local_markup


def _reseal_production_overlay_after_html_change(
    private: Path,
    report: dict[str, object],
    mutate: Callable[[str], str],
) -> None:
    overlays = cast(dict[str, dict[str, object]], report["overlays"])
    production = overlays["production"]
    old_root = private / cast(str, production["directory_name"])
    rows = cast(list[dict[str, object]], production["articles"])
    row = rows[0]
    slug = cast(str, row["production_slug"])
    article_path = old_root / "articles" / f"{slug}.html"
    changed = mutate(article_path.read_text(encoding="utf-8"))
    article_path.write_text(changed, encoding="utf-8")
    article_path.chmod(0o600)
    row["materialized_sha256"] = hashlib.sha256(changed.encode()).hexdigest()
    article_set_sha256 = hashlib.sha256(
        canonical_json_bytes(
            [
                {
                    "article_id": article_row["article_id"],
                    "production_slug": article_row["production_slug"],
                    "sha256": article_row["materialized_sha256"],
                }
                for article_row in rows
            ]
        )
    ).hexdigest()
    production["article_set_sha256"] = article_set_sha256

    receipt_path = old_root / "materialization-receipt.v3.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["article_set_sha256"] = article_set_sha256
    receipt["articles"] = rows
    receipt_raw = canonical_json_bytes(receipt)
    overlay_receipt_sha256 = hashlib.sha256(receipt_raw).hexdigest()
    receipt_path.write_bytes(receipt_raw)
    receipt_path.chmod(0o600)
    new_name = f"production-materialized-fixtures-v3-{overlay_receipt_sha256[:16]}"
    production["directory_name"] = new_name
    production["overlay_receipt_sha256"] = overlay_receipt_sha256
    old_root.rename(private / new_name)

    report["materialized_set_sha256"] = hashlib.sha256(
        canonical_json_bytes(
            {
                mode: {
                    "posts_sha256": overlays[mode]["posts_sha256"],
                    "article_set_sha256": overlays[mode]["article_set_sha256"],
                    "overlay_receipt_sha256": overlays[mode]["overlay_receipt_sha256"],
                }
                for mode in ("local", "production")
            }
        )
    ).hexdigest()
    _write_private(private, "activation-dry-run.json", canonical_json_bytes(report))


def _replace_first_cta_href_with_host_decoy(markup: str) -> str:
    match = re.search(
        r'href="(https://hb\.afl\.rakuten\.co\.jp/[^"]+)"',
        markup,
    )
    assert match is not None
    return (
        markup[: match.start(1)]
        + "https://example.invalid/not-a-money-link"
        + markup[match.end(1) :]
        + f"\n<!-- {match.group(1)} -->"
    )


def _add_srcset_to_first_product_card_image(markup: str) -> str:
    return re.sub(
        r"(<article\b(?=[^>]*data-raos-product-id=)[^>]*>.*?<img\b)",
        r'\1 srcset="https://example.invalid/unverified.webp 2x" sizes="100vw"',
        markup,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _add_extra_first_product_card_image(markup: str) -> str:
    return re.sub(
        r"(<article\b(?=[^>]*data-raos-product-id=)[^>]*>.*?)(<img\b)",
        lambda match: (
            match.group(1)
            + '<img src="https://example.invalid/extra.webp" alt="">'
            + match.group(2)
        ),
        markup,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )


def test_exact_20_provider_slots_and_74_money_links_materialize_without_live_write(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    tracked_before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            ROOT / "changes/wordpress-local-preview-v1/fixtures/articles"
        ).glob("*.html")
    }

    report = _run(private)

    assert report["schema"] == DRY_RUN_SCHEMA
    assert report["state"] == "OWNER_PRIVATE_MATERIALIZED_NOT_PUBLISHED"
    assert report["article_count"] == 10
    assert report["provider_slot_count"] == 20
    assert report["provider_measurement_id_count"] == 20
    assert report["internal_cta_identity_count"] == 74
    assert report["live_link_count"] == 74
    assert report["cta_count"] == 74
    portfolio = load_editorial_portfolio_v3(ROOT)
    expected_provider_slot_set_sha256 = hashlib.sha256(
        canonical_json_bytes(
            [
                {
                    "provider_slot_id": slot.provider_slot_id,
                    "article_id": slot.article_id,
                    "placement": slot.placement,
                }
                for slot in sorted(
                    portfolio.provider_slots,
                    key=lambda value: value.provider_slot_id,
                )
            ]
        )
    ).hexdigest()
    assert report["provider_slot_set_sha256"] == expected_provider_slot_set_sha256
    assert re.fullmatch(
        r"[0-9a-f]{64}", cast(str, report["provider_measurement_binding_sha256"])
    )
    assert report["tracked_source_modified"] is False
    assert report["live_write_performed"] is False
    assert report["publication_authorized"] is False
    assert report["provider_parameter_inference_used"] is False
    assert "hb.afl.rakuten.co.jp" not in json.dumps(report)
    activation_inputs = cast(dict[str, str], report["activation_inputs"])
    assert activation_inputs["admin_receipt_name"] == "admin-receipt.json"
    assert activation_inputs["money_link_mapping_name"] == "money-links.json"
    assert activation_inputs["mapping_generated_at_utc"] == mapping["generated_at"]
    assert activation_inputs["admin_verified_at_utc"] == receipt["verified_at"]
    assert report["version"] == "3.0.0"
    v2_materialization = cast(dict[str, object], report["v2_materialization"])
    assert (
        v2_materialization["manufacturer_sales_state_sha256"]
        == _SYNTHETIC_SALES_STATE_SHA256
    )
    assert (
        v2_materialization["manufacturer_sales_state_checked_at_utc"]
        == _SYNTHETIC_SALES_STATE_CHECKED_AT
    )
    assert "test-provider-" not in json.dumps(report)

    overlay_names = cast(dict[str, dict[str, object]], report["overlays"])
    for mode in ("local", "production"):
        overlay_receipt = json.loads(
            (
                private
                / str(overlay_names[mode]["directory_name"])
                / "materialization-receipt.v3.json"
            ).read_text(encoding="utf-8")
        )
        assert overlay_receipt["provider_slot_count"] == 20
        assert overlay_receipt["provider_measurement_id_count"] == 20
        assert overlay_receipt["internal_cta_identity_count"] == 74
        assert overlay_receipt["live_link_count"] == 74
        assert overlay_receipt["cta_count"] == 74
    materialized = list(
        (
            private / str(overlay_names["production"]["directory_name"]) / "articles"
        ).glob("*.html")
    )
    assert len(materialized) == 10
    combined = b"".join(path.read_bytes() for path in materialized)
    assert combined.count(b"https://hb.afl.rakuten.co.jp/") == 74
    assert combined.count(b'data-raos-cta-id="') == 74
    assert combined.count(b'data-raos-snapshot-id="') == 74
    assert combined.count(b'data-raos-offer-id="') == 74
    assert combined.count(b'data-raos-product-id="') >= 74
    assert combined.count(b'data-raos-placement="') >= 74
    assert combined.count(b'data-raos-rakuten-provider-slot-id="') == 74
    assert b'data-raos-rakuten-measurement-id="' not in combined
    assert combined.count(b'rel="sponsored nofollow"') == 74
    assert combined.count("型番と最新価格を楽天市場で確認する".encode()) == 37
    assert combined.count("在庫・カラーを楽天市場で確認する".encode()) == 37
    assert "一致する楽天商品を確認できなかったため".encode() not in combined
    anchors = re.findall(
        rb'<a class="rakuten-cta raos-cta"[^>]+>',
        combined,
    )
    required_attributes = {
        b"data-raos-article-id",
        b"data-raos-cta-id",
        b"data-raos-snapshot-id",
        b"data-raos-offer-id",
        b"data-raos-product-id",
        b"data-raos-placement",
        b"data-raos-rakuten-provider-slot-id",
    }
    assert len(anchors) == 74
    assert all(
        set(re.findall(rb"\b(data-raos-[a-z-]+)=", anchor)) == required_attributes
        for anchor in anchors
    )
    assert {
        value.decode()
        for value in re.findall(
            rb'data-raos-rakuten-provider-slot-id="([^"]+)"', combined
        )
    } == {
        binding.provider_slot_id
        for article in portfolio.articles
        for binding in article.cta_bindings
    }
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in materialized)
    assert stat.S_IMODE(private.stat().st_mode) == 0o700
    assert tracked_before == {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked_before
    }
    local = (private.parent / "v2/local").resolve()
    production = (private.parent / "v2/production").resolve()
    validated = validate_rakuten_measurement_activation_v3(
        repository_root=ROOT,
        dry_run_path=private / "activation-dry-run.json",
        portfolio=load_editorial_portfolio_v3(ROOT),
        local_v2_fixture_root=local,
        production_v2_fixture_root=production,
    )
    assert validated.article_count == 10
    assert validated.provider_slot_count == 20
    assert validated.provider_measurement_id_count == 20
    assert validated.internal_cta_identity_count == 74
    assert validated.live_link_count == 74
    assert validated.cta_count == 74
    assert validated.mapping_generated_at_utc == mapping["generated_at"]
    assert validated.admin_verified_at_utc == receipt["verified_at"]
    assert validated.activated_at_utc == activation_inputs["activated_at_utc"]
    assert validated.provider_slot_set_sha256 == report["provider_slot_set_sha256"]
    assert (
        validated.provider_measurement_binding_sha256
        == report["provider_measurement_binding_sha256"]
    )
    assert validated.production_article_sha256 == {
        path.stem: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in materialized
    }


def test_activation_rejects_nonverified_v2_completion_receipt(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    local, production = _v2_pair(private)
    for root in (local, production):
        path = root / "materialization-receipt.v2.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["products"][0]["state"] = "not_found"
        document["completion"]["state"] = "INCOMPLETE"
        document["completion"]["verified_product_count"] = (
            len(load_editorial_portfolio_v2(ROOT).products) - 1
        )
        path.write_bytes(_json_bytes(document))
        path.chmod(0o600)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE",
    ):
        materialize_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            private_root=private,
            portfolio=load_editorial_portfolio_v3(ROOT),
            admin_receipt_name="admin-receipt.json",
            money_link_mapping_name="money-links.json",
            dry_run_output_name="activation-dry-run.json",
            local_v2_fixture_root=local,
            production_v2_fixture_root=production,
        )


def test_activation_rejects_stale_v2_materialization_pair(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    local, production = _v2_pair(private)
    for root in (local, production):
        path = root / "materialization-receipt.v2.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["generated_at"] = "2026-01-01T00:00:00Z"
        path.write_bytes(_json_bytes(document))
        path.chmod(0o600)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_STALE",
    ):
        materialize_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            private_root=private,
            portfolio=load_editorial_portfolio_v3(ROOT),
            admin_receipt_name="admin-receipt.json",
            money_link_mapping_name="money-links.json",
            dry_run_output_name="activation-dry-run.json",
            local_v2_fixture_root=local,
            production_v2_fixture_root=production,
        )


def test_activation_rejects_resealed_different_canonical_product_image_url(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    local, production = _v2_pair(private)
    receipt_path = production / "materialization-receipt.v2.json"
    materialization = json.loads(receipt_path.read_text(encoding="utf-8"))
    article = cast(list[dict[str, object]], materialization["articles"])[0]
    article_path = production / "articles" / f"{article['production_slug']}.html"
    source = article_path.read_text(encoding="utf-8")
    changed = source.replace(".jpg?_ex=128x128", "-different.jpg?_ex=128x128", 1)
    assert changed != source
    article_path.write_text(changed, encoding="utf-8")
    article_path.chmod(0o600)
    article["content_sha256"] = hashlib.sha256(changed.encode()).hexdigest()
    receipt_path.write_bytes(_json_bytes(materialization))
    receipt_path.chmod(0o600)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE",
    ):
        materialize_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            private_root=private,
            portfolio=load_editorial_portfolio_v3(ROOT),
            admin_receipt_name="admin-receipt.json",
            money_link_mapping_name="money-links.json",
            dry_run_output_name="activation-dry-run.json",
            local_v2_fixture_root=local,
            production_v2_fixture_root=production,
        )


@pytest.mark.parametrize(
    "field",
    ["evidence_status", "manufacturer_sales_state", "provider_binding"],
)
def test_activation_rejects_resealed_receipt_not_bound_to_actual_v2_evidence(
    tmp_path: Path,
    field: str,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    local, production = _v2_pair(private)
    for fixture_root in (local, production):
        receipt_path = fixture_root / "materialization-receipt.v2.json"
        materialization = json.loads(receipt_path.read_text(encoding="utf-8"))
        if field == "evidence_status":
            materialization["evidence_status_sha256"] = "f" * 64
        elif field == "manufacturer_sales_state":
            materialization["manufacturer_sales_state_sha256"] = "f" * 64
        else:
            materialization["products"][0]["provider_binding_sha256"] = "f" * 64
        receipt_path.write_bytes(_json_bytes(materialization))
        receipt_path.chmod(0o600)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_V2_(?:MATERIALIZATION|EVIDENCE)_",
    ):
        materialize_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            private_root=private,
            portfolio=load_editorial_portfolio_v3(ROOT),
            admin_receipt_name="admin-receipt.json",
            money_link_mapping_name="money-links.json",
            dry_run_output_name="activation-dry-run.json",
            local_v2_fixture_root=local,
            production_v2_fixture_root=production,
        )


def test_activation_rejects_resealed_local_media_not_bound_to_actual_image(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    local, production = _v2_pair(private)
    product_id = load_editorial_portfolio_v2(ROOT).products[0].product_id
    image_extension = _synthetic_image_extension(product_id)
    changed_payload = b"resealed-different-product-image"
    changed_sha256 = hashlib.sha256(changed_payload).hexdigest()
    media_path = private.parent / "v2/product-media" / f"{product_id}.{image_extension}"
    media_path.write_bytes(changed_payload)
    media_path.chmod(0o600)
    for fixture_root in (local, production):
        receipt_path = fixture_root / "materialization-receipt.v2.json"
        materialization = json.loads(receipt_path.read_text(encoding="utf-8"))
        media_rows = cast(list[dict[str, object]], materialization["media"])
        next(row for row in media_rows if row["product_id"] == product_id)[
            "image_sha256"
        ] = changed_sha256
        receipt_path.write_bytes(_json_bytes(materialization))
        receipt_path.chmod(0o600)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE",
    ):
        materialize_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            private_root=private,
            portfolio=load_editorial_portfolio_v3(ROOT),
            admin_receipt_name="admin-receipt.json",
            money_link_mapping_name="money-links.json",
            dry_run_output_name="activation-dry-run.json",
            local_v2_fixture_root=local,
            production_v2_fixture_root=production,
        )


def test_validation_rechecks_current_manufacturer_sales_state_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    _run(private)
    current = activation_module._load_verified_v2_evidence(
        ROOT,
        now=datetime.now(UTC),
    )
    monkeypatch.setattr(
        activation_module,
        "_load_verified_v2_evidence",
        lambda *_args, **_kwargs: replace(
            current,
            manufacturer_sales_state_sha256="f" * 64,
        ),
    )

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INVALID",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=private / "activation-dry-run.json",
            portfolio=load_editorial_portfolio_v3(ROOT),
            local_v2_fixture_root=(private.parent / "v2/local").resolve(),
            production_v2_fixture_root=(private.parent / "v2/production").resolve(),
        )


@pytest.mark.parametrize(
    "binding",
    ["portfolio", "status", "provider", "sales_state"],
)
def test_materialization_rejects_v2_source_change_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    binding: str,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    local, production = _v2_pair(private)
    stable_loader = activation_module._load_verified_v2_evidence
    calls = 0

    def load(
        repository_root: Path,
        *,
        now: datetime,
    ) -> activation_module._VerifiedV2EvidenceSet:
        nonlocal calls
        calls += 1
        evidence = stable_loader(repository_root, now=now)
        if calls == 1:
            return evidence
        if binding == "portfolio":
            return replace(evidence, portfolio_sha256="f" * 64)
        if binding == "status":
            return replace(evidence, status_sha256="f" * 64)
        if binding == "sales_state":
            return replace(
                evidence,
                manufacturer_sales_state_sha256="f" * 64,
            )
        products = dict(evidence.products)
        product_id = next(iter(products))
        products[product_id] = replace(
            products[product_id],
            provider_binding_sha256="f" * 64,
        )
        return replace(evidence, products=products)

    monkeypatch.setattr(activation_module, "_load_verified_v2_evidence", load)
    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED",
    ):
        materialize_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            private_root=private,
            portfolio=load_editorial_portfolio_v3(ROOT),
            admin_receipt_name="admin-receipt.json",
            money_link_mapping_name="money-links.json",
            dry_run_output_name="activation-dry-run.json",
            local_v2_fixture_root=local,
            production_v2_fixture_root=production,
        )


def test_materialization_rejects_v2_receipt_change_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    local, production = _v2_pair(private)
    real_write = activation_module.write_private_bytes

    def write(root: Path, name: str, payload: bytes) -> Path:
        result = real_write(root, name, payload)
        if name == "activation-dry-run.json":
            receipt_path = production / "materialization-receipt.v2.json"
            receipt_path.write_bytes(receipt_path.read_bytes() + b"\n")
            receipt_path.chmod(0o600)
        return result

    monkeypatch.setattr(activation_module, "write_private_bytes", write)
    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED",
    ):
        materialize_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            private_root=private,
            portfolio=load_editorial_portfolio_v3(ROOT),
            admin_receipt_name="admin-receipt.json",
            money_link_mapping_name="money-links.json",
            dry_run_output_name="activation-dry-run.json",
            local_v2_fixture_root=local,
            production_v2_fixture_root=production,
        )


def test_validation_rejects_provider_change_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    _run(private)
    stable_loader = activation_module._load_verified_v2_evidence
    calls = 0

    def load(
        repository_root: Path,
        *,
        now: datetime,
    ) -> activation_module._VerifiedV2EvidenceSet:
        nonlocal calls
        calls += 1
        evidence = stable_loader(repository_root, now=now)
        if calls == 1:
            return evidence
        products = dict(evidence.products)
        product_id = next(iter(products))
        products[product_id] = replace(
            products[product_id],
            provider_binding_sha256="f" * 64,
        )
        return replace(evidence, products=products)

    monkeypatch.setattr(activation_module, "_load_verified_v2_evidence", load)
    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=private / "activation-dry-run.json",
            portfolio=load_editorial_portfolio_v3(ROOT),
            local_v2_fixture_root=(private.parent / "v2/local").resolve(),
            production_v2_fixture_root=(private.parent / "v2/production").resolve(),
        )


@pytest.mark.parametrize("drift", ["status", "receipt"])
def test_v2_snapshot_guard_reopens_final_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    evidence = activation_module._VerifiedV2EvidenceSet(
        portfolio_sha256="a" * 64,
        status_sha256="b" * 64,
        manufacturer_sales_state_sha256="c" * 64,
        manufacturer_sales_state_checked_at_utc=now,
        product_safety=_synthetic_product_safety_binding(),
        products={},
    )
    source = {
        "generated_at": now,
        "receipt_raw": b"receipt",
    }
    evidence_reads = 0

    def load(*_args: object, **_kwargs: object) -> object:
        nonlocal evidence_reads
        evidence_reads += 1
        if drift == "status" and evidence_reads == 2:
            return replace(evidence, status_sha256="f" * 64)
        return evidence

    monkeypatch.setattr(activation_module, "_load_verified_v2_evidence", load)
    monkeypatch.setattr(
        activation_module,
        "_v2_materialization",
        lambda **_kwargs: dict(source),
    )

    def read(path: Path, **_kwargs: object) -> bytes:
        if drift == "receipt" and "production" in path.as_posix():
            return b"changed-receipt"
        return b"receipt"

    monkeypatch.setattr(activation_module, "_read_owner_regular_file", read)
    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED",
    ):
        activation_module._require_v2_materializations_current(
            repository_root=tmp_path.resolve(),
            portfolio=cast(object, SimpleNamespace()),
            local_fixture_root=(tmp_path / "local").resolve(),
            production_fixture_root=(tmp_path / "production").resolve(),
            expected_evidence=evidence,
            expected_local=source,
            expected_production=source,
            require_recent=True,
        )


def test_activation_requires_the_actual_v2_status_file(tmp_path: Path) -> None:
    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_SOURCE_INVALID",
    ):
        _REAL_V2_EVIDENCE_LOADER(
            tmp_path.resolve(),
            now=datetime.now(UTC),
        )


def test_cli_emits_only_safe_hash_and_count_receipt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    local, production = _v2_pair(private)
    monkeypatch.setattr(
        "raos.application.editorial.rakuten_measurement_activation_v3._default_v2_fixture_roots",
        lambda _root: (local, production),
    )

    assert (
        activation_main(
            [
                "--private-root",
                str(private),
                "activate",
                "--admin-receipt",
                "admin-receipt.json",
                "--money-link-mapping",
                "money-links.json",
                "--dry-run-output",
                "activation-dry-run.json",
            ]
        )
        == 0
    )
    output = capsys.readouterr()
    assert output.err == ""
    assert '"provider_slot_count":20' in output.out
    assert '"provider_measurement_id_count":20' in output.out
    assert '"internal_cta_identity_count":74' in output.out
    assert '"live_link_count":74' in output.out
    assert '"cta_count":74' in output.out
    assert "hb.afl.rakuten.co.jp" not in output.out
    assert "item.rakuten.co.jp" not in output.out
    assert "test-provider-" not in output.out


def test_cli_generates_private_mapping_and_admin_receipt_templates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private = _private_root(tmp_path)

    assert (
        activation_main(
            [
                "--private-root",
                str(private),
                "money-link-template",
                "--output",
                "money-links-template.json",
            ]
        )
        == 0
    )
    mapping_template_path = private / "money-links-template.json"
    mapping_template = json.loads(mapping_template_path.read_text(encoding="utf-8"))
    assert len(mapping_template["rows"]) == 74
    assert mapping_template["urls_copied_from_rakuten_admin"] is False
    assert stat.S_IMODE(mapping_template_path.stat().st_mode) == 0o600
    safe_mapping_output = capsys.readouterr()
    assert '"row_count":74' in safe_mapping_output.out
    assert "hb.afl.rakuten.co.jp" not in safe_mapping_output.out

    completed_mapping, _receipt = _documents()
    _write_private(
        private, "completed-money-links.json", _json_bytes(completed_mapping)
    )
    assert (
        activation_main(
            [
                "--private-root",
                str(private),
                "admin-receipt-template",
                "--money-link-mapping",
                "completed-money-links.json",
                "--output",
                "admin-receipt-template.json",
            ]
        )
        == 0
    )
    receipt_path = private / "admin-receipt-template.json"
    admin_template = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert len(admin_template["provider_slots"]) == 20
    assert len(admin_template["money_links"]) == 74
    assert admin_template["owner_attested"] is False
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    safe_receipt_output = capsys.readouterr()
    assert '"row_count":74' in safe_receipt_output.out
    assert "hb.afl.rakuten.co.jp" not in safe_receipt_output.out


@pytest.mark.parametrize(
    "mutate",
    [
        lambda mapping, _receipt: mapping["rows"].pop(),
        lambda mapping, _receipt: mapping["provider_slots"].pop(),
        lambda mapping, _receipt: mapping.update({"provider_slot_count": 74}),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {"provider_slot_id": "rps-a99-card"}
        ),
        lambda mapping, _receipt: mapping["provider_slots"][1].update(
            {
                "rakuten_measurement_id": mapping["provider_slots"][0][
                    "rakuten_measurement_id"
                ]
            }
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {"representative_model": "=FORMULA()"}
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {"destination_url": "http://hb.afl.rakuten.co.jp/hgc/bad/"}
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {"destination_url": "https://evil.example/hgc/bad/"}
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {
                "destination_url": (
                    "https://hb.afl.rakuten.co.jp/hgc/bad/?keyword=private-query"
                )
            }
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {"destination_url": ("https://user:password@hb.afl.rakuten.co.jp/hgc/bad/")}
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {"destination_url": ("https://hb.afl.rakuten.co.jp/hgc/%2e%2e/bad/")}
        ),
        lambda mapping, _receipt: mapping["rows"][0].update(
            {
                "destination_url": (
                    "https://hb.afl.rakuten.co.jp/hgc/bad/?pc="
                    "https%3A%2F%2Fitem.rakuten.co.jp%2Fsearch%2Fprivate-query%2F"
                )
            }
        ),
        lambda mapping, _receipt: mapping["rows"][1].update(
            {"destination_url": mapping["rows"][0]["destination_url"]}
        ),
        lambda _mapping, receipt: receipt["provider_slots"][0].update(
            {"csv_echoed_measurement_id": "wrong-provider-id"}
        ),
        lambda _mapping, receipt: receipt["provider_slots"][0].update(
            {
                "rakuten_measurement_id": "wrong-provider-id",
                "csv_echoed_measurement_id": "wrong-provider-id",
            }
        ),
        lambda _mapping, receipt: receipt["money_links"][0].update(
            {"csv_echoed_representative_model": "WRONG-MODEL"}
        ),
        lambda _mapping, receipt: receipt["verification"].update(
            {"csv_export_verified": False}
        ),
    ],
)
def test_missing_extra_mismatched_formula_sensitive_or_unverified_input_fails_closed(
    tmp_path: Path,
    mutate: Callable[[dict[str, object], dict[str, object]], object],
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    mutate(mapping, receipt)
    _bind_and_write(private, mapping, receipt)

    with pytest.raises(RakutenMeasurementActivationV3Failure):
        _run(private)

    assert not list(private.glob("*-materialized-fixtures-v3-*"))
    assert not (private / "activation-dry-run.json").exists()


def test_admin_receipt_rejects_wrong_valid_slot_for_article_placement(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    money_links = cast(list[dict[str, object]], receipt["money_links"])
    provider_slots = cast(list[dict[str, object]], receipt["provider_slots"])
    assert money_links[0]["provider_slot_id"] != provider_slots[1]["provider_slot_id"]
    money_links[0]["provider_slot_id"] = provider_slots[1]["provider_slot_id"]
    _bind_and_write(private, mapping, receipt)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_RECEIPT_INVALID",
    ):
        _run(private)


def test_admin_receipt_requires_separate_provider_slot_selection_verification(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    money_links = cast(list[dict[str, object]], receipt["money_links"])
    money_links[0]["money_link_provider_slot_selection_verified"] = False
    _bind_and_write(private, mapping, receipt)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_RECEIPT_INVALID",
    ):
        _run(private)


def test_mapping_raw_hash_must_equal_owner_receipt_binding(tmp_path: Path) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    mapping_raw = _json_bytes(mapping)
    receipt["money_link_mapping_sha256"] = "0" * 64
    _write_private(private, "money-links.json", mapping_raw)
    _write_private(private, "admin-receipt.json", _json_bytes(receipt))

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_RECEIPT_INVALID",
    ):
        _run(private)


def test_validation_reopens_original_mapping_and_rejects_resealed_url_drift(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    report = _run(private)
    first = cast(list[dict[str, object]], mapping["rows"])[0]
    provider_measurement_id = next(
        str(row["rakuten_measurement_id"])
        for row in cast(list[dict[str, object]], mapping["provider_slots"])
        if row["provider_slot_id"] == first["provider_slot_id"]
    )
    first["destination_url"] = (
        "https://hb.afl.rakuten.co.jp/hgc/"
        f"{provider_measurement_id}/resealed/?pc="
        + quote(
            "https://item.rakuten.co.jp/test-shop/resealed-different-product/",
            safe="",
        )
    )
    activation_inputs = cast(dict[str, str], report["activation_inputs"])
    _rebind_activation_sources_and_dry_run(
        private,
        mapping,
        receipt,
        activated_at=activation_inputs["activated_at_utc"],
    )

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=private / "activation-dry-run.json",
            portfolio=load_editorial_portfolio_v3(ROOT),
            local_v2_fixture_root=(private.parent / "v2/local").resolve(),
            production_v2_fixture_root=(private.parent / "v2/production").resolve(),
        )


def test_activation_input_order_and_publication_freshness_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    now = datetime.now(UTC).replace(microsecond=0)
    mapping["generated_at"] = (now - timedelta(days=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    receipt["verified_at"] = (now - timedelta(minutes=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    _bind_and_write(private, mapping, receipt)
    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_INPUT_STALE",
    ):
        _run(private)

    verification_root = tmp_path / "stale-verification"
    verification_root.mkdir()
    private = _private_root(verification_root)
    mapping, receipt = _documents()
    mapping["generated_at"] = (now - timedelta(minutes=20)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    receipt["verified_at"] = (now - timedelta(minutes=19)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    _bind_and_write(private, mapping, receipt)
    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_INPUT_STALE",
    ):
        _run(private)

    stale_root = tmp_path / "stale-validation"
    stale_root.mkdir()
    private = _private_root(stale_root)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    report = _run(private)
    future_now = datetime.now(UTC) + timedelta(days=1)

    class FutureDateTime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            del cls
            if tz is None:
                return future_now.replace(tzinfo=None)
            return future_now.astimezone(cast(object, tz))  # type: ignore[arg-type]

    monkeypatch.setattr(activation_module, "datetime", FutureDateTime)
    arguments = {
        "repository_root": ROOT,
        "dry_run_path": private / "activation-dry-run.json",
        "portfolio": load_editorial_portfolio_v3(ROOT),
        "local_v2_fixture_root": (private.parent / "v2/local").resolve(),
        "production_v2_fixture_root": (private.parent / "v2/production").resolve(),
    }
    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_INPUT_STALE",
    ):
        validate_rakuten_measurement_activation_v3(**arguments)
    validated = validate_rakuten_measurement_activation_v3(
        **arguments,
        require_recent=False,
    )
    assert validated.activated_at_utc == cast(dict[str, str], report["activation_inputs"])[
        "activated_at_utc"
    ]


def test_private_inputs_require_exact_modes(tmp_path: Path) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    os.chmod(private / "money-links.json", 0o644)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_PRIVATE_INPUT_INVALID",
    ):
        _run(private)


def test_validated_overlay_fails_closed_on_mode_or_v2_receipt_drift(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    report = _run(private)
    local = (private.parent / "v2/local").resolve()
    production = (private.parent / "v2/production").resolve()
    portfolio = load_editorial_portfolio_v3(ROOT)
    production_overlay = private / str(
        cast(dict[str, dict[str, object]], report["overlays"])["production"][
            "directory_name"
        ]
    )
    target = next((production_overlay / "articles").glob("*.html"))
    target.chmod(0o644)
    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_SOURCE_INVALID",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=private / "activation-dry-run.json",
            portfolio=portfolio,
            local_v2_fixture_root=local,
            production_v2_fixture_root=production,
        )
    target.chmod(0o600)
    source_receipt = production / "materialization-receipt.v2.json"
    source_receipt.write_bytes(source_receipt.read_bytes() + b"\n")
    source_receipt.chmod(0o600)
    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_V2_SOURCE_DRIFT",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=private / "activation-dry-run.json",
            portfolio=portfolio,
            local_v2_fixture_root=local,
            production_v2_fixture_root=production,
        )


def test_validated_overlay_rechecks_local_verified_media_bytes(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    _run(private)
    media = next((private.parent / "v2/product-media").glob("*.*"))
    media.write_bytes(b"tampered")
    media.chmod(0o600)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=private / "activation-dry-run.json",
            portfolio=load_editorial_portfolio_v3(ROOT),
            local_v2_fixture_root=(private.parent / "v2/local").resolve(),
            production_v2_fixture_root=(private.parent / "v2/production").resolve(),
        )


@pytest.mark.parametrize(
    "mutate",
    [
        _replace_first_cta_href_with_host_decoy,
        lambda markup: markup.replace(
            'rel="sponsored nofollow"',
            'rel="noopener"',
            1,
        ),
        lambda markup: markup.replace(
            ".jpg?_ex=128x128",
            "-different.jpg?_ex=128x128",
            1,
        ),
        _add_srcset_to_first_product_card_image,
        _add_extra_first_product_card_image,
        lambda markup: re.sub(
            r'data-raos-rakuten-provider-slot-id="[^"]+"',
            'data-raos-rakuten-provider-slot-id="rps-a99-card"',
            markup,
            count=1,
        ),
    ],
    ids=(
        "cta-href-with-host-decoy",
        "cta-rel",
        "product-image-identity",
        "product-image-srcset",
        "extra-product-card-image",
        "logical-provider-slot",
    ),
)
def test_resealed_overlay_revalidates_each_cta_and_product_image(
    tmp_path: Path,
    mutate: Callable[[str], str],
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    report = _run(private)
    _reseal_production_overlay_after_html_change(private, report, mutate)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_(?:URL|OVERLAY)_INVALID",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=private / "activation-dry-run.json",
            portfolio=load_editorial_portfolio_v3(ROOT),
            local_v2_fixture_root=(private.parent / "v2/local").resolve(),
            production_v2_fixture_root=(private.parent / "v2/production").resolve(),
        )


def test_legacy_v2_dry_run_identity_is_rejected(tmp_path: Path) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    _run(private)
    dry_run_path = private / "activation-dry-run.json"
    dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
    dry_run["schema"] = "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_DRY_RUN_V2"
    dry_run["version"] = "2.0.0"
    dry_run_path.write_bytes(_json_bytes(dry_run))
    dry_run_path.chmod(0o600)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_DRY_RUN_INVALID",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=dry_run_path,
            portfolio=load_editorial_portfolio_v3(ROOT),
            local_v2_fixture_root=(private.parent / "v2/local").resolve(),
            production_v2_fixture_root=(private.parent / "v2/production").resolve(),
        )


@pytest.mark.parametrize(
    ("field", "invalid_count"),
    (
        ("provider_measurement_id_count", 19),
        ("internal_cta_identity_count", 73),
        ("live_link_count", 73),
    ),
)
def test_dry_run_validator_rejects_explicit_provider_or_live_link_count_drift(
    tmp_path: Path,
    field: str,
    invalid_count: int,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    _run(private)
    dry_run_path = private / "activation-dry-run.json"
    dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
    dry_run[field] = invalid_count
    dry_run_path.write_bytes(_json_bytes(dry_run))
    dry_run_path.chmod(0o600)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_DRY_RUN_INVALID",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=dry_run_path,
            portfolio=load_editorial_portfolio_v3(ROOT),
            local_v2_fixture_root=(private.parent / "v2/local").resolve(),
            production_v2_fixture_root=(private.parent / "v2/production").resolve(),
        )


def test_v3_dry_run_requires_explicit_internal_cta_identity_count(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    _run(private)
    dry_run_path = private / "activation-dry-run.json"
    dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
    assert dry_run["schema"] == DRY_RUN_SCHEMA
    dry_run.pop("internal_cta_identity_count")
    dry_run_path.write_bytes(_json_bytes(dry_run))
    dry_run_path.chmod(0o600)

    with pytest.raises(
        RakutenMeasurementActivationV3Failure,
        match="RAOS_RAKUTEN_ACTIVATION_DOCUMENT_INVALID",
    ):
        validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=dry_run_path,
            portfolio=load_editorial_portfolio_v3(ROOT),
            local_v2_fixture_root=(private.parent / "v2/local").resolve(),
            production_v2_fixture_root=(private.parent / "v2/production").resolve(),
        )


def test_real_v3_activation_dry_run_cannot_establish_unsigned_t0(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, admin = _documents()
    _bind_and_write(private, mapping, admin)
    activation = _run(private)
    portfolio = load_editorial_portfolio_v3(ROOT)
    activation_raw = (private / "activation-dry-run.json").read_bytes()
    activation_sha256 = hashlib.sha256(activation_raw).hexdigest()
    readback = production_readback_template(portfolio)
    readback["owner_attested"] = True
    publication_binding, publication_contents = _publication_evidence(
        portfolio,
        activation,
        activation_sha256,
        portfolio.source_sha256,
    )
    readback["publication_binding"] = publication_binding
    readback["analytics_site_binding"] = {
        "state": "OWNER_PRIVATE_READ_ONLY_BINDING_VERIFIED",
        "binding_sha256": "a" * 64,
        "ga4_property_id_sha256": "b" * 64,
        "ga4_configuration_response_sha256": "c" * 64,
    }
    timestamps = (
        "2026-08-30T10:01:00Z",
        "2026-08-30T10:02:00Z",
        "2026-08-30T10:03:00Z",
    )
    observations = cast(list[dict[str, object]], readback["observations"])
    for row, timestamp in zip(observations, timestamps, strict=True):
        row["state"] = "SUCCESS"
        row["observed_at"] = timestamp
        row["request_sha256"] = "d" * 64
        row["response_sha256"] = "e" * 64
    production = cast(dict[str, dict[str, object]], activation["overlays"])[
        "production"
    ]
    rakuten = cast(dict[str, object], observations[0]["details"])
    rakuten.update(
        {
            "provider_slot_count": 20,
            "provider_measurement_id_count": 20,
            "internal_cta_identity_count": 74,
            "live_link_count": 74,
            "all_provider_measurement_ids_echo_verified": True,
            "provider_slot_set_sha256": activation["provider_slot_set_sha256"],
            "provider_measurement_binding_sha256": activation[
                "provider_measurement_binding_sha256"
            ],
            "activation_dry_run_sha256": activation_sha256,
            "materialized_set_sha256": activation["materialized_set_sha256"],
            "production_posts_sha256": production["posts_sha256"],
            "production_article_set_sha256": production["article_set_sha256"],
            "production_overlay_receipt_sha256": production["overlay_receipt_sha256"],
        }
    )
    cast(dict[str, object], observations[1]["details"]).update(
        {
            "http_status": 202,
            "aggregate_readback_observed": True,
            "event_id_sha256": "f" * 64,
        }
    )
    cast(dict[str, object], observations[2]["details"]).update(
        {
            "property_id_sha256": "b" * 64,
            "configuration_response_sha256": "c" * 64,
            "analytics_site_binding_sha256": "a" * 64,
            "article_id": portfolio.articles[0].article_id,
            "event_observed": True,
        }
    )
    readback_sha256 = hashlib.sha256(canonical_json_bytes(readback)).hexdigest()
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match=f"^{TRUSTED_T0_EVIDENCE_REQUIRED}$",
    ):
        establish_t0_receipt(
            document=readback,
            observation_sha256=readback_sha256,
            rakuten_activation=activation,
            rakuten_activation_sha256=activation_sha256,
            expected_portfolio_sha256=portfolio.source_sha256,
            portfolio=portfolio,
            **publication_contents,
            evaluated_at=datetime(2026, 8, 30, 11, 0, tzinfo=UTC),
        )


def test_output_name_cannot_overwrite_an_input(
    tmp_path: Path,
) -> None:
    private = _private_root(tmp_path)
    mapping, receipt = _documents()
    _bind_and_write(private, mapping, receipt)
    portfolio = load_editorial_portfolio_v3(ROOT)

    for output_name in ("admin-receipt.json", "money-links.json"):
        with pytest.raises(
            RakutenMeasurementActivationV3Failure,
            match="RAOS_RAKUTEN_ACTIVATION_PRIVATE_NAME_INVALID",
        ):
            materialize_rakuten_measurement_activation_v3(
                repository_root=ROOT,
                private_root=private,
                portfolio=portfolio,
                admin_receipt_name="admin-receipt.json",
                money_link_mapping_name="money-links.json",
                dry_run_output_name=output_name,
            )


def test_article_materialization_rejects_missing_or_duplicate_cta() -> None:
    portfolio = load_editorial_portfolio_v3(ROOT)
    article = portfolio.articles[0]
    source = (
        ROOT
        / "changes/wordpress-local-preview-v1/fixtures/articles"
        / f"{article.production_slug}.html"
    ).read_bytes()
    mapping, _receipt = _documents()
    mapping_rows = cast(list[dict[str, object]], mapping["rows"])
    urls = cast(
        dict[tuple[str, str, str], str],
        {
            (row["article_id"], row["product_id"], row["placement"]): row[
                "destination_url"
            ]
            for row in mapping_rows
            if row["article_id"] == article.article_id
        },
    )
    text = source.decode()
    first = re.search(
        r"<a\b(?=[^>]*data-raos-product-id)[^>]*data-raos-placement="
        r"[\"'](?:product_card|final_summary)[\"'][^>]*>.*?</a>",
        text,
        flags=re.DOTALL,
    )
    assert first is not None

    with pytest.raises(RakutenMeasurementActivationV3Failure):
        materialize_article_html(
            article,
            text.replace(first.group(0), "", 1).encode(),
            urls,
        )
    with pytest.raises(RakutenMeasurementActivationV3Failure):
        materialize_article_html(
            article,
            (text + first.group(0)).encode(),
            urls,
        )
