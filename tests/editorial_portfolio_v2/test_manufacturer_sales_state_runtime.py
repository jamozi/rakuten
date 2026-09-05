from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from raos.application.editorial import editorial_portfolio_v2 as portfolio_module
from raos.application.editorial.editorial_portfolio_v2 import (
    EditorialPortfolioV2Failure,
    ProductEvidenceViewV2,
    load_editorial_portfolio_v2,
    materialize_article_v2,
    product_evidence_readiness_v2,
)
from raos.domain.editorial.self_hosted_editorial_pilot import RakutenProductEvidence


ROOT = Path(__file__).resolve().parents[2]
ARTICLE_ROOT = ROOT / "changes/wordpress-local-preview-v1/fixtures/articles"
OUT_OF_STOCK_PRODUCT_IDS: set[str] = set()
UNKNOWN_PRODUCT_IDS: set[str] = set()


def _canonical_sha256(row: dict[str, object]) -> str:
    payload = {
        field: row[field]
        for field in portfolio_module.MANUFACTURER_SALES_STATE_HASH_FIELDS
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _substitute_sales_document(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, object],
) -> None:
    original = portfolio_module._read_bytes
    sales_path = ROOT / portfolio_module.MANUFACTURER_SALES_STATE_RELATIVE_PATH
    payload = json.dumps(document, ensure_ascii=False).encode("utf-8")

    def substituted(path: Path, *, maximum: int, private: bool = False) -> bytes:
        if path == sales_path:
            return payload
        return original(path, maximum=maximum, private=private)

    monkeypatch.setattr(portfolio_module, "_read_bytes", substituted)


def _verified_views(product_ids: tuple[str, ...]) -> dict[str, ProductEvidenceViewV2]:
    evidence = cast(RakutenProductEvidence, SimpleNamespace())
    return {
        product_id: ProductEvidenceViewV2(
            product_id=product_id,
            state="verified",
            retrieved_at="2026-08-30T16:40:10Z",
            evidence=evidence,
        )
        for product_id in product_ids
    }


def test_runtime_binds_model_and_variant_sales_states_without_attesting_rakuten_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    audit = portfolio.manufacturer_sales_state_audit

    assert audit is not None
    assert audit.checked_at_utc == "2026-08-31T14:19:31Z"
    assert len(audit.products) == len(portfolio.products) == 33
    assert audit.known_product_count == 33
    assert audit.publication_eligible is True
    assert set(audit.product_by_id) == {
        product.product_id for product in portfolio.products
    }
    assert {
        row.product_id for row in audit.products if row.state == "OUT_OF_STOCK"
    } == OUT_OF_STOCK_PRODUCT_IDS
    assert sum(row.state == "AVAILABLE" for row in audit.products) == 33
    assert {
        row.product_id for row in audit.products if row.state == "UNKNOWN"
    } == UNKNOWN_PRODUCT_IDS
    assert (
        audit.product_by_id["PRD-ACE-DIFFERENCE-05721"].availability_scope == "VARIANT"
    )
    assert {
        row.product_id
        for row in audit.products
        if row.availability_scope == "VARIANT"
    } == {
        "PRD-ACE-DIFFERENCE-05721",
        "PRD-BLUETTI-AORA30-V2",
        "PRD-BLUETTI-AORA100-V2",
    }
    assert all(
        row.availability_scope == "MODEL"
        for row in audit.products
        if row.product_id
        not in {
            "PRD-ACE-DIFFERENCE-05721",
            "PRD-BLUETTI-AORA30-V2",
            "PRD-BLUETTI-AORA100-V2",
        }
    )
    assert audit.availability_scope == "MIXED"
    assert all(row.recheck_required for row in audit.products)
    assert all(row.establishes_exact_rakuten_variant is False for row in audit.products)
    assert audit.cta_requires_separate_exact_variant_evidence is True

    products_with_private_codes = tuple(
        replace(
            product,
            rakuten_shop_code="verified-shop",
            rakuten_item_code=f"verified-shop:{10000000 + index}",
        )
        for index, product in enumerate(portfolio.products)
    )
    ready_portfolio = replace(portfolio, products=products_with_private_codes)
    monkeypatch.setattr(
        portfolio_module,
        "load_editorial_portfolio_v2",
        lambda _root: ready_portfolio,
    )
    monkeypatch.setattr(
        portfolio_module,
        "product_evidence_views_v2",
        lambda *_args, **_kwargs: _verified_views(
            tuple(product.product_id for product in ready_portfolio.products)
        ),
    )

    readiness = product_evidence_readiness_v2(
        ROOT,
        now=datetime(2026, 9, 1, 0, 30, tzinfo=UTC),
    )

    assert readiness.complete is True
    assert readiness.manufacturer_sales_state_contract_complete is True
    assert readiness.manufacturer_sales_state_publication_eligible is True
    assert readiness.manufacturer_sales_state_known_product_count == 33
    assert readiness.manufacturer_sales_state_available_product_count == 33
    assert readiness.manufacturer_sales_state_out_of_stock_product_count == 0
    assert set(readiness.manufacturer_sales_state_out_of_stock_product_ids) == (
        OUT_OF_STOCK_PRODUCT_IDS
    )
    assert set(readiness.manufacturer_sales_state_ineligible_product_ids) == (
        UNKNOWN_PRODUCT_IDS
    )
    assert set(readiness.manufacturer_sales_state_unknown_product_ids) == (
        UNKNOWN_PRODUCT_IDS
    )
    assert len(readiness.manufacturer_sales_state_recheck_product_ids) == len(
        portfolio.products
    )
    assert readiness.manufacturer_sales_state_scope == "MIXED"
    assert readiness.manufacturer_state_establishes_exact_rakuten_variant is False
    assert readiness.affiliate_variant_eligibility == (
        "SEPARATE_EXACT_VARIANT_EVIDENCE_REQUIRED"
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "bad-hash",
        "missing-product",
        "official-url-drift",
        "duplicate-evidence",
        "typed-policy-drift",
        "visible-evidence-policy-drift",
        "minimum-timestamp-drift",
    ),
)
def test_runtime_rejects_tampered_or_incomplete_sales_contract(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    path = ROOT / portfolio_module.MANUFACTURER_SALES_STATE_RELATIVE_PATH
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    rows = cast(list[dict[str, object]], document["products"])
    if mutation == "bad-hash":
        rows[0]["structured_snapshot_sha256"] = "0" * 64
    elif mutation == "missing-product":
        rows.pop()
    elif mutation == "official-url-drift":
        rows[0]["official_url"] = "https://example.invalid/wrong-product"
        rows[0]["structured_snapshot_sha256"] = _canonical_sha256(rows[0])
    elif mutation == "duplicate-evidence":
        evidence_urls = cast(list[str], rows[0]["status_evidence_urls"])
        evidence_urls.append(evidence_urls[0])
        rows[0]["structured_snapshot_sha256"] = _canonical_sha256(rows[0])
    elif mutation == "typed-policy-drift":
        policy = cast(dict[str, dict[str, object]], document["publication_policy"])
        policy["AVAILABLE"]["known_state"] = 1
    elif mutation == "visible-evidence-policy-drift":
        policy = cast(dict[str, object], document["evidence_resolution_policy"])
        policy["structured_data_alone_cannot_establish_available"] = False
    elif mutation == "minimum-timestamp-drift":
        document["checked_at_utc"] = "2026-08-30T16:40:11Z"
    else:
        raise AssertionError(mutation)
    _substitute_sales_document(monkeypatch, document)

    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INVALID",
    ):
        load_editorial_portfolio_v2(ROOT)


@pytest.mark.parametrize(
    ("state", "failure_code", "contract_complete"),
    (
        (
            "UNKNOWN",
            "RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_UNVERIFIED",
            False,
        ),
        (
            "DISCONTINUED",
            "RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INELIGIBLE",
            True,
        ),
    ),
)
def test_unknown_and_discontinued_states_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    failure_code: str,
    contract_complete: bool,
) -> None:
    path = ROOT / portfolio_module.MANUFACTURER_SALES_STATE_RELATIVE_PATH
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    rows = cast(list[dict[str, object]], document["products"])
    rows[0]["state"] = state
    rows[0]["structured_snapshot_sha256"] = _canonical_sha256(rows[0])
    _substitute_sales_document(monkeypatch, document)
    portfolio = load_editorial_portfolio_v2(ROOT)
    product_id = cast(str, rows[0]["product_id"])
    audit = portfolio.manufacturer_sales_state_audit
    assert audit is not None
    assert audit.product_by_id[product_id].state == state

    monkeypatch.setattr(
        portfolio_module,
        "load_editorial_portfolio_v2",
        lambda _root: portfolio,
    )
    monkeypatch.setattr(
        portfolio_module,
        "product_evidence_views_v2",
        lambda *_args, **_kwargs: _verified_views(
            tuple(product.product_id for product in portfolio.products)
        ),
    )
    # The tracked fixture is deliberately old enough to fail the real
    # 24-hour freshness gate; this test exercises the state-specific gate.
    monkeypatch.setattr(
        portfolio_module,
        "MANUFACTURER_SALES_STATE_FRESHNESS",
        portfolio_module.MANUFACTURER_SALES_STATE_FRESHNESS * 365,
    )
    readiness = product_evidence_readiness_v2(ROOT)
    assert readiness.complete is False
    assert readiness.manufacturer_sales_state_contract_complete is contract_complete
    assert product_id in readiness.manufacturer_sales_state_ineligible_product_ids
    if state == "UNKNOWN":
        assert set(readiness.manufacturer_sales_state_unknown_product_ids) == (
            UNKNOWN_PRODUCT_IDS | {product_id}
        )
    else:
        assert readiness.manufacturer_sales_state_discontinued_product_ids == (
            product_id,
        )

    article = next(
        article for article in portfolio.articles if product_id in article.product_ids
    )
    markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
        encoding="utf-8"
    )
    with pytest.raises(EditorialPortfolioV2Failure, match=failure_code):
        materialize_article_v2(
            markup,
            article=article,
            portfolio=portfolio,
            evidence_views=_verified_views(article.product_ids),
            mode="production",
        )


def test_current_sales_state_covers_only_available_selected_models() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    assert set(portfolio.manufacturer_sales_state_by_product_id) == {
        product.product_id for product in portfolio.products
    }
    states = portfolio.manufacturer_sales_state_by_product_id
    assert {
        product_id for product_id, row in states.items() if row.state != "AVAILABLE"
    } == UNKNOWN_PRODUCT_IDS
    assert "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY" not in states
    assert "PRD-EUFY-AUTOEMPTY-C10-T2292" in states
