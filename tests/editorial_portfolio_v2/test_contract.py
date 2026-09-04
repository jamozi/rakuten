from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from html import unescape
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
from typing import cast, Literal
from urllib.parse import urlencode

import pytest

from raos.application.editorial import editorial_portfolio_v2 as portfolio_module
from raos.application.editorial.editorial_portfolio_v2 import (
    ArticleBindingV2,
    EditorialPortfolioV2,
    EditorialPortfolioV2Failure,
    ProductBindingV2,
    ProductEvidenceViewV2,
    _validate_rakuten_identity,
    load_editorial_portfolio_v2,
    materialize_article_v2,
    product_jan_evidence_bindings_v1,
    product_evidence_readiness_v2,
    product_evidence_views_v2,
    require_manufacturer_sales_state_for_products_v1,
)
from raos.domain.editorial.self_hosted_editorial_pilot import RakutenProductEvidence
from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailure,
    EditorialPilotFailureCode,
)
from raos.adapters import self_hosted_editorial_rakuten_capture as capture_module
from raos.adapters import self_hosted_editorial_source_capture as source_capture_module
from raos.application.editorial import self_hosted_editorial_pilot as pilot_module
from raos.application.editorial import product_safety_receipts as safety_receipts_module
from scripts import raos_editorial_portfolio_v2 as portfolio_script


ROOT = Path(__file__).resolve().parents[2]
ARTICLE_ROOT = ROOT / "changes/wordpress-local-preview-v1/fixtures/articles"
SELECTION_NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolate_selection_audit_from_owner_private_captures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit tests use tracked declarations, never a developer's live receipts."""

    def evaluate(repository_root: Path, **kwargs: object) -> object:
        document = json.loads(
            (
                repository_root
                / safety_receipts_module.PRODUCT_SAFETY_RECEIPTS_RELATIVE_PATH
            ).read_text(encoding="utf-8")
        )
        return safety_receipts_module.evaluate_product_safety_receipts(
            document, **kwargs
        )

    monkeypatch.setattr(portfolio_script, "load_product_safety_receipt_audit", evaluate)


FIXED_HEADING_BREAK = re.compile(
    r"<h([12])\b[^>]*>(?:(?!</h\1>).)*?<br\b", re.IGNORECASE | re.DOTALL
)
READER_FACING_PROHIBITED = (
    "起点",
    "候補に残す",
    "演繹",
    "実機未試験の稿",
    "自分で確認",
    "できない人",
    "最終文面",
    "公開判断",
    "公開前",
    "推測しない",
)
STANDARD_AD_DISCLOSURE = (
    "広告を含みます。購入リンクから成果報酬を受け取る場合がありますが、"
    "選定・掲載順には使いません。"
)
STANDARD_AD_DETAILS = (
    "型番が一致する楽天商品を確認できた場合に、楽天アフィリエイトの購入リンクを掲載します。"
    "リンク経由で商品を購入すると、運営者が成果報酬を受け取る場合があります。"
)
NONAFFILIATE_DISCLOSURE = (
    "この記事には購入リンクがありません。以前の比較対象の販売状態を確認する案内記事のため、"
    "商品カードとアフィリエイトリンクは掲載していません。"
)

RENDERER_ARTICLE_IDS = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)


def _complete_safety_binding() -> dict[str, object]:
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
        "binding_sha256": hashlib.sha256(
            portfolio_script._canonical_bytes(material)
        ).hexdigest(),
    }


def test_v2_contract_loader_has_no_successor_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loading the predecessor must not read any generated V3 artifact."""

    observed_paths: list[Path] = []
    original_read_json = portfolio_module._read_json

    def read_json(path: Path, *, maximum: int, private: bool = False) -> object:
        observed_paths.append(path)
        return original_read_json(path, maximum=maximum, private=private)

    monkeypatch.setattr(portfolio_module, "_read_json", read_json)
    load_editorial_portfolio_v2(ROOT)

    assert observed_paths == [
        ROOT / portfolio_module.PORTFOLIO_RELATIVE_PATH,
        ROOT / portfolio_module.SOURCE_FIXTURE_RELATIVE_PATH / "posts.json",
    ]
    assert all(
        "editorial-portfolio-v3" not in path.as_posix() for path in observed_paths
    )


def _attributes(tag: str) -> dict[str, str]:
    return {
        name: value
        for name, _quote, value in re.findall(
            r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", tag, flags=re.DOTALL
        )
    }


def _fake_view(
    product_id: str,
    *,
    state: Literal["verified", "not_found", "ambiguous", "expired"],
) -> ProductEvidenceViewV2:
    evidence = None
    if state == "verified":
        evidence = cast(
            RakutenProductEvidence,
            SimpleNamespace(
                destination_url=(
                    "https://hb.afl.rakuten.co.jp/hgc/test/"
                    "?pc=https%3A%2F%2Fitem.rakuten.co.jp%2Fshop%2Fitem%2F"
                    "&m=https%3A%2F%2Fm.rakuten.co.jp%2Fshop%2Fi%2F10000000%2F"
                    "&rafcid=test"
                ),
                image_url=(
                    "https://thumbnail.image.rakuten.co.jp/@0_mall/shop/"
                    "cabinet/item.jpg?_ex=128x128"
                ),
                image_sha256="a" * 64,
            ),
        )
    return ProductEvidenceViewV2(
        product_id=product_id,
        state=state,
        retrieved_at="2026-08-29T00:00:00Z",
        evidence=evidence,
        image_extension="jpg" if evidence is not None else None,
    )


def _visible_text(markup: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", markup))


FORMAL_PRODUCT_PREFIX_OVERRIDES = {
    "PRD-IROBOT-ROOMBA-PLUS-515-COMBO": (
        "iRobot「Roomba Plus 515 Combo ロボット + "
        "AutoWash 充電ステーション」（型番：N285060",
        "Roomba Plus 515 Combo ロボット + AutoWash 充電ステーション",
    ),
    "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060": (
        "「Roomba Mini Slim 掃除機＆床拭きロボット + "
        "SlimCharge 充電スタンド」（代表型番：F115060",
        "Roomba Mini Slim 掃除機＆床拭きロボット + SlimCharge 充電スタンド",
    ),
    "PRD-SWITCHBOT-K11-PRO": (
        "SwitchBot「ロボット掃除機 K11+ Pro」",
        "ロボット掃除機 K11+ Pro",
    ),
    "PRD-SWITCHBOT-K10-PRO-COMBO": (
        "SwitchBot「ロボット掃除機 K10+ Pro Combo」",
        "ロボット掃除機 K10+ Pro Combo",
    ),
}


def _formal_product_prefix(
    product_id: str, official_name: str, representative_model: str
) -> tuple[str, str]:
    override = FORMAL_PRODUCT_PREFIX_OVERRIDES.get(product_id)
    if override is not None:
        return override
    if representative_model.casefold() in official_name.casefold():
        return official_name, official_name
    return f"{official_name}（型番：{representative_model}", official_name


def test_portfolio_closes_ten_articles_owner_products_and_thirty_seven_cards() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    tracked = json.loads(
        (ROOT / portfolio_module.PORTFOLIO_RELATIVE_PATH).read_text(encoding="utf-8")
    )

    assert portfolio.version == "2.0.0"
    assert tracked["evidence_policy"]["identity_validation"]["jan"] == (
        "required_exact_when_official_jan_registered"
    )
    assert tracked["evidence_policy"]["completion_gate"] == {
        "required_product_count": len(portfolio.products),
        "required_product_card_count": 37,
        "required_affiliate_cta_count": 74,
        "required_product_state": "verified",
        "required_product_image_state": "verified",
        "maximum_neutral_product_images": 0,
        "maximum_manufacturer_fallback_ctas": 0,
    }
    assert tracked["selection_policy"]["zero_weight_factors"] == {
        "price": 0,
        "affiliate_reward_rate": 0,
        "rakuten_availability": 0,
    }
    assert portfolio.theme_version == "1.5.0"
    assert "theme_runtime_revision" not in tracked
    assert len(portfolio.articles) == 10
    assert len(portfolio.products) == 33
    assert sum(len(article.product_ids) for article in portfolio.articles) == 37
    assert len(portfolio.selection_audits) == len(portfolio.products)
    audits = {audit.product_id: audit for audit in portfolio.selection_audits}
    assert set(audits) == {product.product_id for product in portfolio.products}
    for product in portfolio.products:
        audit = audits[product.product_id]
        assessments = dict(audit.axis_assessments)
        assert assessments["safety"] == (
            "SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED"
        )
        assert assessments["warranty_and_support"] == (
            "SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED"
        )
        assert assessments["maintainability"] == (
            "SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED"
        )
        assert tuple(axis for axis, _assessment in audit.axis_assessments) == tuple(
            tracked["selection_policy"]["ranking_factors"]
        )
        assert audit.article_ids == tuple(
            article.article_id
            for article in portfolio.articles
            if product.product_id in article.product_ids
        )
        assert audit.evidence_refs
        assert audit.evidence_refs[0] == product.official_url
        assert len(audit.evidence_refs) == len(set(audit.evidence_refs))
        assert audit.inclusion_reason.endswith("。")
        assert audit.excluded_alternatives
        assert all(value.reason.endswith("。") for value in audit.excluded_alternatives)
    assert {
        product.product_id: product.representative_model
        for product in portfolio.products
        if product.product_id
        in {
            "PRD-ANKER-SOLIX-C300",
            "PRD-ANKER-SOLIX-C800-PLUS",
            "PRD-ANKER-SOLIX-C1000",
            "PRD-ANKER-SOLIX-C1000-GEN2",
            "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
            "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
            "PRD-SIROCA-SS-M171",
        }
    } == {
        "PRD-ANKER-SOLIX-C300": "A17225Z1",
        "PRD-ANKER-SOLIX-C800-PLUS": "A1754",
        "PRD-ANKER-SOLIX-C1000": "A17615Z1",
        "PRD-ANKER-SOLIX-C1000-GEN2": "A17635Z1",
        "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060": "F115060",
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W": "TK-MDW22W",
        "PRD-SIROCA-SS-M171": "SS-M171",
    }
    assert {article.category for article in portfolio.articles} == {
        "移動",
        "家事",
        "備え",
    }


def test_editorial_review_and_product_source_dates_remain_distinct() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    registry = json.loads(
        (
            ROOT
            / "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json"
        ).read_text(encoding="utf-8")
    )
    sources = {source["source_ref"]: source for source in registry["sources"]}
    source_dates_by_article = {
        packet["article_id"]: tuple(
            sources[source_ref]["retrieved_on"] for source_ref in packet["source_refs"]
        )
        for packet in registry["source_packets"]
    }
    assert set(source_dates_by_article) == {
        article.article_id for article in portfolio.articles
    }
    contract = portfolio_script._source_fact_date_contract(portfolio)
    assert portfolio.editorial_reviewed_on == "2026-09-01"
    assert set(contract.article_dates.values()) == {portfolio.editorial_reviewed_on}
    assert all(
        max(source_dates) <= contract.article_dates[article_id]
        for article_id, source_dates in source_dates_by_article.items()
    )
    assert contract.product_dates["st1704-portable-power-station-guide"] == {
        "PRD-ANKER-SOLIX-C300": "2026-08-31",
        "PRD-BLUETTI-AORA30-V2": "2026-08-31",
        "PRD-JACKERY-500-NEW": "2026-08-31",
        "PRD-ANKER-SOLIX-C800": "2026-08-31",
        "PRD-JACKERY-1000-NEW-V3": "2026-09-01",
        "PRD-BLUETTI-AORA100-V2": "2026-08-31",
        "PRD-DJI-POWER-1000-V2": "2026-08-31",
    }
    assert contract.product_dates["st1704-anker-solix-c300-c800-c1000-differences"] == {
        "PRD-ANKER-SOLIX-C300": "2026-08-31",
        "PRD-ANKER-SOLIX-C800-PLUS": "2026-08-31",
        "PRD-ANKER-SOLIX-C1000": "2026-08-31",
        "PRD-ANKER-SOLIX-C1000-GEN2": "2026-08-31",
    }

    for article in portfolio.articles:
        observed = datetime.fromisoformat(contract.article_dates[article.article_id])
        japanese = f"{observed.year}年{observed.month}月{observed.day}日"
        dotted = observed.strftime("%Y.%m.%d")
        markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
            encoding="utf-8"
        )
        markup = portfolio_script._replace_displayed_fact_date(
            markup,
            contract.article_dates[article.article_id],
            product_dates=contract.product_dates[article.article_id],
        )
        assert markup.count(f"<dt>最終確認日</dt><dd>{japanese}</dd>") == 1
        if "SPECIFICATIONS CHECKED / " in markup:
            assert f"SPECIFICATIONS CHECKED / {dotted}" in markup
        if "一次情報確認日 / " in markup:
            assert f"一次情報確認日 / {dotted}" in markup
        for product_id, product_date in contract.product_dates[
            article.article_id
        ].items():
            card = re.search(
                r'<article\b(?=[^>]*data-raos-product-id="'
                + re.escape(product_id)
                + r'")[^>]*>.*?</article>',
                markup,
                flags=re.DOTALL,
            )
            assert card is not None
            assert f"情報確認日 {portfolio_script._japanese_date(product_date)}" in (
                card.group(0)
            )
            assert all(
                product_date <= sources[source_ref]["retrieved_on"]
                for source_ref in contract.product_source_refs[article.article_id][
                    product_id
                ]
            )

    synthetic = (
        "<dt>最終確認日</dt><dd>2026年8月29日</dd>"
        "<p>確認日：2026年8月29日</p><p>規則施行日：2026年7月1日</p>"
        "<small>SPECIFICATIONS CHECKED / 2026.08.29</small>"
    )
    normalized = portfolio_script._replace_displayed_fact_date(
        synthetic,
        "2026-08-31",
    )
    assert normalized.count("2026年8月29日") == 1
    assert "2026.08.29" not in normalized
    assert normalized.count("2026年8月31日") == 1
    assert "2026.08.31" in normalized
    assert "2026年7月1日" in normalized


def test_aora_products_replace_a09_boundary_products_without_weakening_counts() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    articles = {article.article_id: article for article in portfolio.articles}
    assert articles["st1704-portable-power-station-guide"].product_ids == (
        "PRD-ANKER-SOLIX-C300",
        "PRD-BLUETTI-AORA30-V2",
        "PRD-JACKERY-500-NEW",
        "PRD-ANKER-SOLIX-C800",
        "PRD-JACKERY-1000-NEW-V3",
        "PRD-BLUETTI-AORA100-V2",
        "PRD-DJI-POWER-1000-V2",
    )
    assert articles["roomba-mini-vs-switchbot-k11-pro"].product_ids == (
        "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
        "PRD-SWITCHBOT-K11-PRO",
    )
    assert len(portfolio.products) == 33
    assert sum(len(article.product_ids) for article in portfolio.articles) == 37

    audits = {audit.product_id: audit for audit in portfolio.selection_audits}
    for product_id in ("PRD-BLUETTI-AORA30-V2", "PRD-BLUETTI-AORA100-V2"):
        audit = audits[product_id]
        assert tuple(axis for axis, _state in audit.axis_assessments) == (
            "use_case_fit",
            "safety",
            "dimensions",
            "performance",
            "warranty_and_support",
            "maintainability",
            "primary_source_confidence",
        )
        assert audit.article_ids == ("st1704-portable-power-station-guide",)
        assert audit.evidence_refs
        assert all(
            ref.startswith("https://www.bluetti.jp/") for ref in audit.evidence_refs
        )
        assert not re.search(
            r"枠|source packet|ソースパケット", audit.inclusion_reason, re.I
        )


def test_selected_tri_air_is_not_also_registered_as_an_excluded_alternative() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    assert "PRD-PROTECA-TRI-AIR-01541" in portfolio.product_by_id
    excluded_scopes = {
        alternative.scope
        for audit in portfolio.selection_audits
        for alternative in audit.excluded_alternatives
    }
    assert all("Tri-Air" not in scope for scope in excluded_scopes)


def test_a09_and_a10_keep_their_reader_facing_scope_boundaries() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    a09_markup = (ARTICLE_ROOT / "roomba-mini-vs-switchbot-k11-pro.html").read_text(
        encoding="utf-8"
    )
    a09_article = next(
        article
        for article in portfolio.articles
        if article.article_id == "roomba-mini-vs-switchbot-k11-pro"
    )
    assert a09_article.product_ids == (
        "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
        "PRD-SWITCHBOT-K11-PRO",
    )
    assert "PRD-EUFY-AUTOEMPTY-C10-T2292" not in a09_markup
    assert "PRD-ECOVACS-DEEBOT-MINI2" not in a09_markup
    assert a09_markup.count('href="/compact-robot-vacuum-shortlist/"') == 1
    assert a09_markup.count('data-raos-placement="product_card"') == 2
    assert a09_markup.count('data-raos-placement="final_summary"') == 2

    a10_markup = (ARTICLE_ROOT / "solota-vs-rakua-mini-plus.html").read_text(
        encoding="utf-8"
    )
    lead = a10_markup.split('<p class="pullquote">', 1)[0]
    assert 'href="/countertop-dishwasher-for-small-households/"' in lead
    assert "NP-TMLK1-K" in a10_markup
    assert "NP-TML1-W" not in a10_markup
    assert "data-raos-product-id=" not in a10_markup
    assert "data-raos-placement=" not in a10_markup
    assert "https://developers.rakuten.com/" not in a10_markup
    assert NONAFFILIATE_DISCLOSURE in a10_markup


def test_anker_generation_table_uses_bound_expansion_facts() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    article = next(
        article
        for article in portfolio.articles
        if article.article_id == "st1704-anker-solix-c300-c800-c1000-differences"
    )
    markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
        encoding="utf-8"
    )

    normalized = portfolio_script._normalize_anker_compatibility(
        markup,
        article.article_id,
    )

    c1000 = "拡張バッテリー対応・AC出力6口・USB-C 2口・SurgePad 2000W"
    gen2 = "拡張バッテリー非対応・AC出力5口・USB-C 3口・電池4,000回サイクル"
    assert portfolio_script._anker_feature_claim_is_bound() is True
    assert normalized.count(c1000) == 2
    assert normalized.count(gen2) == 2
    assert "C1000 Gen 2との互換性は未確認" not in normalized
    assert "C1000（第1世代）との互換性は未確認" not in normalized
    assert "アクセサリ互換性は未確認（推奨根拠外）" in normalized


@pytest.mark.parametrize("mutation", ["origin", "article-category"])
def test_v2_contract_is_self_contained_and_rejects_site_identity_drift(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracked_path = ROOT / portfolio_module.PORTFOLIO_RELATIVE_PATH
    tracked = json.loads(tracked_path.read_text(encoding="utf-8"))
    if mutation == "origin":
        tracked["target_origin"] = "https://example.invalid"
    else:
        tracked["articles"][0]["category"] = "家事"
    original = portfolio_module._read_json

    def substituted(path: Path, *, maximum: int, private: bool = False) -> object:
        if path == tracked_path:
            return tracked
        return original(path, maximum=maximum, private=private)

    monkeypatch.setattr(portfolio_module, "_read_json", substituted)
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID",
    ):
        load_editorial_portfolio_v2(ROOT)


@pytest.mark.parametrize(
    ("article_id", "from_text", "to_text"),
    [
        (
            "solota-vs-rakua-mini-plus",
            NONAFFILIATE_DISCLOSURE,
            STANDARD_AD_DISCLOSURE,
        ),
        (
            "roomba-mini-vs-switchbot-k11-pro",
            STANDARD_AD_DISCLOSURE,
            NONAFFILIATE_DISCLOSURE,
        ),
    ],
)
def test_v2_loader_rejects_affiliate_and_nonaffiliate_disclosure_mixing(
    article_id: str,
    from_text: str,
    to_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracked = json.loads(
        (ROOT / portfolio_module.PORTFOLIO_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    article = next(
        row for row in tracked["articles"] if row["article_id"] == article_id
    )
    target = ROOT / article["content_ref"]
    original = Path.read_bytes

    def substituted(path: Path) -> bytes:
        payload = original(path)
        if path == target:
            text = payload.decode("utf-8", errors="strict")
            assert text.count(from_text) == 1
            return text.replace(from_text, to_text).encode("utf-8")
        return payload

    monkeypatch.setattr(Path, "read_bytes", substituted)
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID",
    ):
        load_editorial_portfolio_v2(ROOT)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-product",
        "nonzero-price",
        "invented-score",
        "wrong-evidence",
        "axis-not-evaluated",
        "generic-safety",
    ],
)
def test_selection_audit_fails_closed_on_incomplete_or_finance_weighted_data(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    tracked_path = ROOT / portfolio_module.PORTFOLIO_RELATIVE_PATH
    tracked = json.loads(tracked_path.read_text(encoding="utf-8"))
    audit_document = cast(dict[str, object], tracked["selection_audits"])
    audit_products = cast(list[dict[str, object]], audit_document["products"])
    if mutation == "missing-product":
        audit_products.pop()
    elif mutation == "nonzero-price":
        cast(dict[str, object], audit_document["zero_weight_factors"])["price"] = 1
    elif mutation == "invented-score":
        cast(dict[str, object], audit_products[0]["axis_assessments"])[
            "performance"
        ] = "BEST_IN_CLASS"
    elif mutation == "wrong-evidence":
        audit_products[0]["evidence_refs"] = ["https://example.invalid/product"]
    elif mutation == "axis-not-evaluated":
        cast(dict[str, object], audit_products[0]["axis_assessments"])["safety"] = (
            "NOT_EVALUATED"
        )
    elif mutation == "generic-safety":
        cast(dict[str, object], audit_products[0]["axis_assessments"])["safety"] = (
            "EVALUATED_NOT_DIFFERENTIATING"
        )
    else:
        raise AssertionError(mutation)
    original = portfolio_module._read_json

    def substituted(path: Path, *, maximum: int, private: bool = False) -> object:
        if path == tracked_path:
            return tracked
        return original(path, maximum=maximum, private=private)

    monkeypatch.setattr(portfolio_module, "_read_json", substituted)
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID",
    ):
        load_editorial_portfolio_v2(ROOT)


@pytest.mark.parametrize(
    "statement",
    [
        "公式2文書で保証期間が1年と2年に分かれ、矛盾は未解消です。",
        "交換部品の供給期間は未確認です。",
        "support state: CONFLICT_UNRESOLVED",
        "修理窓口を公式ページで確認できない状態です。",
        "保証の日本向け適用条件は記載なしです。",
        "消耗品の供給継続性は要確認です。",
        "国内修理窓口の照合は未実施です。",
        "対象型番のサポート範囲を特定できず。",
        "warranty evidence: RECHECK_REQUIRED",
    ],
)
def test_unresolved_support_prose_cannot_complete_a_selection_axis(
    statement: str,
) -> None:
    assert portfolio_script._selection_axis_statement_is_resolved(statement) is False


def test_affirmative_support_prose_remains_eligible_for_structured_checks() -> None:
    assert (
        portfolio_script._selection_axis_statement_is_resolved(
            "日本国内の正規販売店購入品は本体2年保証で、公式修理窓口が受け付けます。"
        )
        is True
    )


@pytest.mark.parametrize(
    "statement",
    [
        "製品名はExample Power Station ABC-100です。",
        "日本国内の正規購入品は5年保証です。",
        "補修用性能部品を6年保有します。",
        "定格1200Wという記載は未確認です。",
    ],
)
def test_identity_warranty_and_unresolved_prose_are_not_performance(
    statement: str,
) -> None:
    assert (
        portfolio_script._selection_performance_statement_is_substantive(statement)
        is False
    )


def test_measurable_product_spec_is_substantive_performance() -> None:
    assert (
        portfolio_script._selection_performance_statement_is_substantive(
            "容量768Wh、定格1200W、重量10.5kgの公表仕様です。"
        )
        is True
    )


def test_dimensions_and_performance_require_the_exact_product_subject() -> None:
    product_id = "PRD-EXAMPLE-ABC100"
    claim: dict[str, object] = {
        "statement": "容量768Wh、定格1200Wです。",
        "dimensions": [
            {"subject": "ABC-100", "width_cm": 20, "depth_cm": 30, "height_cm": 40}
        ],
        "subject_product_ids": [],
    }

    assert (
        portfolio_script._selection_dimension_claim_is_product_scoped(claim, product_id)
        is False
    )
    assert (
        portfolio_script._selection_performance_claim_is_product_scoped(
            "CLM-EXAMPLE-SPECS", claim, product_id
        )
        is False
    )
    claim["subject_product_ids"] = [product_id]
    assert (
        portfolio_script._selection_dimension_claim_is_product_scoped(claim, product_id)
        is True
    )
    assert (
        portfolio_script._selection_performance_claim_is_product_scoped(
            "CLM-EXAMPLE-SPECS", claim, product_id
        )
        is True
    )
    assert (
        portfolio_script._selection_performance_claim_is_product_scoped(
            "CLM-EXAMPLE-WARRANTY", claim, product_id
        )
        is False
    )


def test_recall_gates_bind_all_selected_products_to_the_central_document() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    _registry, _sources, packets, _affiliates, _claims = pilot_module._validate_sources(
        pilot_module._read_fixed_json(ROOT, pilot_module.SOURCE_REGISTRY_RELATIVE_PATH)
    )

    requirements = portfolio_script._product_safety_requirements_from_gates(
        portfolio, packets
    )

    assert [value.product_id for value in requirements] == [
        product.product_id for product in portfolio.products
    ]
    assert [value.exact_model_tokens for value in requirements] == [
        product.official_models for product in portfolio.products
    ]

    tampered = deepcopy(packets)
    first_packet = next(iter(tampered.values()))
    gate_claim = next(
        value
        for value in first_packet["claims"]
        if value.get("product_specific_recall_query_gate") is not None
    )
    gate_claim["product_specific_recall_query_gate"]["required_product_ids"].pop()
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID",
    ):
        portfolio_script._product_safety_requirements_from_gates(portfolio, tampered)


def test_receipt_registry_context_rejects_manuals_as_manufacturer_query_sources() -> (
    None
):
    portfolio = load_editorial_portfolio_v2(ROOT)
    _registry, sources, packets, _affiliates, claims = pilot_module._validate_sources(
        pilot_module._read_fixed_json(ROOT, pilot_module.SOURCE_REGISTRY_RELATIVE_PATH)
    )
    plan = portfolio_script._validated_capture_plan()
    requirements = portfolio_script._product_safety_requirements_from_gates(
        portfolio, packets
    )

    context = portfolio_script._product_safety_registry_context(
        requirements=requirements,
        sources=sources,
        claims=claims,
        plan=plan,
    )

    assert "SRC-METI-ELECTRICAL-RECALLS" in context.sources
    assert context.sources[
        "SRC-METI-ELECTRICAL-RECALLS"
    ].covered_product_ids == frozenset(
        product.product_id for product in portfolio.products
    )
    assert all("MANUAL" not in source_ref for source_ref in context.sources)
    assert not any(
        value.authority_kind == "MANUFACTURER_OFFICIAL"
        for value in context.sources.values()
    )


def test_selection_report_projects_receipt_refs_and_hashes_without_receipt_bodies() -> (
    None
):
    checked_at = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    status = SimpleNamespace(
        receipts=(
            SimpleNamespace(
                authority_kind="MANUFACTURER_OFFICIAL",
                official_source_ref="SRC-EXAMPLE-SAFETY-NOTICE",
                checked_at=checked_at,
                result="NONE_FOUND",
                capture_sha256="a" * 64,
                receipt_sha256="b" * 64,
                model_tokens=("ABC-100",),
                query_terms=("ABC-100 リコール",),
                coverage_caveat="owner body",
            ),
        )
    )

    refs = portfolio_script._product_safety_receipt_refs(status)

    assert refs == [
        {
            "authority_kind": "MANUFACTURER_OFFICIAL",
            "official_source_ref": "SRC-EXAMPLE-SAFETY-NOTICE",
            "checked_at_utc": "2026-09-01T00:00:00Z",
            "result": "NONE_FOUND",
            "capture_sha256": "a" * 64,
            "receipt_sha256": "b" * 64,
        }
    ]
    assert "model_tokens" not in refs[0]
    assert "query_terms" not in refs[0]
    assert "coverage_caveat" not in refs[0]


def test_selection_locator_loader_fails_closed_on_cross_document_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = portfolio_script._validated_capture_plan()
    assert portfolio_script._validated_locator_claims(plan)

    def drift(_root: Path) -> object:
        raise source_capture_module.OfficialSourceCaptureFailure(
            source_capture_module.OfficialSourceCaptureFailureCode.CONTRACT_INVALID
        )

    monkeypatch.setattr(portfolio_script, "load_source_capture_plan", drift)
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID",
    ):
        portfolio_script._validated_capture_plan()


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 9, 1, 12, 0),
        datetime(2026, 9, 1, 12, 0, tzinfo=timezone(timedelta(hours=9))),
    ],
)
def test_selection_audit_requires_an_explicit_utc_clock(now: datetime) -> None:
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID",
    ):
        portfolio_script._selection_audit_now(now)


def test_effective_selection_audit_is_product_specific_and_evidence_honest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    monkeypatch.setattr(
        portfolio_script,
        "_load_sales_statuses",
        lambda value, _dates, **_kwargs: portfolio_script._unknown_sales_statuses(
            value
        ),
    )

    report = portfolio_script._selection_audit_report(portfolio, now=SELECTION_NOW)
    products = cast(list[dict[str, object]], report["products"])

    assert report["schema"] == "RAOS_PRODUCT_SELECTION_AUDIT_V2"
    assert len(products) == len(portfolio.products)
    assert len({row["product_id"] for row in products}) == len(portfolio.products)
    assert len({row["inclusion_reason"] for row in products}) == len(portfolio.products)
    by_id = {cast(str, row["product_id"]): row for row in products}
    for product in portfolio.products:
        row = by_id[product.product_id]
        axes = cast(list[dict[str, object]], row["axes"])
        candidates = cast(list[dict[str, object]], row["considered_candidates"])
        assert [axis["axis"] for axis in axes] == report["axis_order"]
        assert all(product.official_name in cast(str, axis["reason"]) for axis in axes)
        assert candidates
        assert all(
            candidate["product_id"] in portfolio.product_by_id
            and candidate["official_name"]
            == portfolio.product_by_id[cast(str, candidate["product_id"])].official_name
            and candidate["product_id"] != product.product_id
            for candidate in candidates
        )
        for axis in axes:
            assert axis["state"] in {
                "OFFICIAL_SPEC_CONFIRMED",
                "PUBLISHED_SPEC_ONLY",
                "OFFICIAL_SOURCE_LOCATOR_BOUND",
                "EDITORIAL_JUDGMENT_FROM_BOUND_FACTS",
                "OFFICIAL_SAFETY_NOTICE_CHECK_BOUND",
                "OFFICIAL_SAFETY_GUIDANCE_BOUND_RECHECK_REQUIRED",
                "NOT_EXECUTED",
                "NOT_EVALUATED",
                "UNVERIFIED",
            }
            if axis["state"] in {"NOT_EXECUTED", "NOT_EVALUATED", "UNVERIFIED"}:
                assert axis["source_refs"] == []
                assert axis["locator_refs"] == []
                assert any(
                    value in cast(str, axis["reason"])
                    for value in ("推奨根拠", "未評価", "不足", "期限")
                )
            else:
                assert axis["source_refs"]
                assert axis["locator_refs"]
            if axis["axis"] in {
                "safety",
                "warranty_and_support",
                "maintainability",
            }:
                assert date.fromisoformat(
                    cast(str, axis["recheck_by"])
                ) > date.fromisoformat(cast(str, row["evaluated_on"]))
        assert (
            cast(dict[str, object], row["manufacturer_sales_state"])["state"]
            == "UNKNOWN"
        )
    jackery_axes = {
        cast(str, axis["axis"]): axis
        for axis in cast(list[dict[str, object]], by_id["PRD-JACKERY-500-NEW"]["axes"])
    }
    assert jackery_axes["dimensions"]["state"] == "OFFICIAL_SPEC_CONFIRMED"
    assert jackery_axes["performance"]["state"] == "PUBLISHED_SPEC_ONLY"
    assert jackery_axes["safety"]["state"] == (
        "OFFICIAL_SAFETY_GUIDANCE_BOUND_RECHECK_REQUIRED"
    )
    assert jackery_axes["warranty_and_support"]["state"] == "NOT_EXECUTED"
    assert jackery_axes["warranty_and_support"]["partial_locator_refs"]
    assert jackery_axes["maintainability"]["state"] == "NOT_EXECUTED"
    assert jackery_axes["maintainability"]["partial_locator_refs"]
    assert jackery_axes["safety"]["receipt_status"] == ("BLOCKED_MISSING_RECEIPT")
    assert jackery_axes["safety"]["receipt_refs"] == []
    assert jackery_axes["safety"]["missing_authority_kinds"] == [
        "MANUFACTURER_OFFICIAL",
        "JAPAN_ADMINISTRATIVE_OFFICIAL",
    ]
    deebot_safety = next(
        axis
        for axis in cast(
            list[dict[str, object]],
            by_id["PRD-ECOVACS-DEEBOT-MINI2"]["axes"],
        )
        if axis["axis"] == "safety"
    )
    assert deebot_safety["state"] == "NOT_EXECUTED"
    assert deebot_safety["connected_privacy_recheck_required"] is True
    assert deebot_safety["connected_privacy_locator_refs"]
    assert "privacy/connected feature" in cast(str, deebot_safety["reason"])
    assert "推奨根拠には使" in cast(str, deebot_safety["reason"])
    safety_bound_ids = {
        cast(str, row["product_id"])
        for row in products
        if {
            cast(str, axis["axis"]): axis["state"]
            for axis in cast(list[dict[str, object]], row["axes"])
        }["safety"]
        != "NOT_EXECUTED"
    }
    assert safety_bound_ids == {
        "PRD-ANKER-SOLIX-C300",
        "PRD-ANKER-SOLIX-C800",
        "PRD-ANKER-SOLIX-C800-PLUS",
        "PRD-ANKER-SOLIX-C1000",
        "PRD-ANKER-SOLIX-C1000-GEN2",
        "PRD-BLUETTI-AORA30-V2",
        "PRD-BLUETTI-AORA100-V2",
        "PRD-DJI-POWER-1000-V2",
        "PRD-JACKERY-1000-NEW-V3",
        "PRD-JACKERY-500-NEW",
    }
    completion = cast(dict[str, object], report["completion"])
    receipt_contract = cast(
        dict[str, object], report["product_safety_receipt_contract"]
    )
    safety_binding = cast(
        dict[str, object], report["product_safety_publication_binding"]
    )
    assert receipt_contract["complete_product_count"] == 0
    assert set(cast(list[str], receipt_contract["incomplete_product_ids"])) == {
        product.product_id for product in portfolio.products
    }
    assert safety_binding == {
        "schema": "RAOS_PRODUCT_SAFETY_PUBLICATION_BINDING_V1",
        "required_product_count": 33,
        "required_authority_kinds": [
            "MANUFACTURER_OFFICIAL",
            "JAPAN_ADMINISTRATIVE_OFFICIAL",
        ],
        "required_administrative_capture_count": 99,
        "administrative_bundle_sha256": None,
        "administrative_capture_count": 0,
        "administrative_verified_product_count": 0,
        "manufacturer_verified_product_count": 0,
        "complete_product_count": 0,
        "complete": False,
        "binding_sha256": safety_binding["binding_sha256"],
    }
    assert re.fullmatch(r"[0-9a-f]{64}", cast(str, safety_binding["binding_sha256"]))
    assert completion["product_safety_receipt_complete_product_count"] == 0
    assert completion["axis_complete_product_count"] == 0
    assert set(cast(list[str], completion["axis_incomplete_product_ids"])) == {
        product.product_id for product in portfolio.products
    }
    assert completion["state"] == "INCOMPLETE"
    assert all("販売" not in cast(str, row["inclusion_reason"]) for row in products)


def test_selection_recheck_deadline_and_future_sources_are_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    monkeypatch.setattr(
        portfolio_script,
        "_load_sales_statuses",
        lambda value, _dates, **_kwargs: portfolio_script._unknown_sales_statuses(
            value
        ),
    )

    expired = portfolio_script._selection_audit_report(
        portfolio,
        now=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
    )
    for product in cast(list[dict[str, object]], expired["products"]):
        axes = {
            cast(str, axis["axis"]): axis
            for axis in cast(list[dict[str, object]], product["axes"])
        }
        assert axes["use_case_fit"]["state"] == "NOT_EVALUATED"
        assert axes["dimensions"]["state"] == "NOT_EVALUATED"
        assert axes["performance"]["state"] == "NOT_EVALUATED"
        assert axes["primary_source_confidence"]["state"] == "UNVERIFIED"

    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID",
    ):
        portfolio_script._selection_audit_report(
            portfolio,
            now=datetime(2026, 8, 30, 0, 0, tzinfo=UTC),
        )


def test_missing_official_sales_evidence_is_unknown_and_blocks_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    fact_dates = portfolio_script._source_fact_date_contract(portfolio)
    monkeypatch.setattr(portfolio_script, "ROOT", tmp_path)

    statuses = portfolio_script._load_sales_statuses(portfolio, fact_dates)

    assert set(statuses) == {product.product_id for product in portfolio.products}
    assert {status.state for status in statuses.values()} == {"UNKNOWN"}
    monkeypatch.setattr(
        portfolio_script,
        "_selection_audit_report",
        lambda _portfolio, **_kwargs: {
            "product_safety_publication_binding": _complete_safety_binding(),
            "completion": {
                "state": "INCOMPLETE",
                "product_count": len(portfolio.products),
                "axis_complete_product_count": len(portfolio.products),
                "unknown_product_ids": sorted(statuses),
            },
        },
    )
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_SALES_STATE_UNVERIFIED",
    ):
        portfolio_script._require_selection_completion(portfolio)


def test_selection_completion_rejects_an_unevaluated_decision_axis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    observed_now: list[datetime | None] = []

    def incomplete_report(
        _portfolio: EditorialPortfolioV2, *, now: datetime | None = None
    ) -> dict[str, object]:
        observed_now.append(now)
        return {
            "product_safety_publication_binding": {
                **_complete_safety_binding(),
            },
            "completion": {
                "state": "COMPLETE",
                "product_count": len(portfolio.products),
                "axis_complete_product_count": len(portfolio.products) - 1,
                "axis_incomplete_product_ids": [portfolio.products[0].product_id],
            },
        }

    monkeypatch.setattr(
        portfolio_script,
        "_selection_audit_report",
        incomplete_report,
    )

    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INCOMPLETE",
    ):
        portfolio_script._require_selection_completion(portfolio, now=SELECTION_NOW)
    assert observed_now == [SELECTION_NOW]


def test_model_sales_state_contract_verifies_hash_and_does_not_attest_cta_variant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    fact_dates = portfolio_script._source_fact_date_contract(portfolio)
    checked_at = "2026-08-30T16:40:10Z"
    out_of_stock = {
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-M171",
    }
    rows: list[dict[str, object]] = []
    for product in portfolio.products:
        availability_scope = (
            "VARIANT" if product.product_id == "PRD-ACE-DIFFERENCE-05721" else "MODEL"
        )
        material: dict[str, object] = {
            "checked_at_utc": checked_at,
            "product_id": product.product_id,
            "state": (
                "OUT_OF_STOCK" if product.product_id in out_of_stock else "AVAILABLE"
            ),
            "availability_scope": availability_scope,
            "official_url": product.official_url,
            "status_evidence_urls": [product.official_url],
            "locator": "公式販売ページの構造化販売状態表示",
            "basis": "公式ページ上のモデル単位販売状態を確認。",
            "variant_caveat": {
                "code": "MODEL_SCOPE_ONLY",
                "detail": "モデル単位の状態であり、楽天CTAのvariant適格性は証明しない。",
                "establishes_exact_rakuten_variant": False,
            },
            "alternative": None,
        }
        rows.append(
            dict(material)
            | {
                "snapshot_kind": portfolio_script.SALES_STATUS_SNAPSHOT_KIND,
                "structured_snapshot_sha256": hashlib.sha256(
                    portfolio_script._canonical_bytes(material)
                ).hexdigest(),
            }
        )
    document = {
        "schema": portfolio_script.SALES_STATUS_SCHEMA,
        "checked_at_utc": checked_at,
        "snapshot_kind": portfolio_script.SALES_STATUS_SNAPSHOT_KIND,
        "hash_contract": {
            "algorithm": "SHA-256",
            "canonicalization": (
                "UTF-8 JSON with recursively sorted object keys, no insignificant "
                "whitespace, and unescaped Unicode"
            ),
            "fields": list(portfolio_script.SALES_STATUS_HASH_FIELDS),
        },
        "availability_scope_policy": {
            "MODEL": {
                "establishes_exact_rakuten_variant": False,
                "cta_requires_separate_exact_variant_evidence": True,
            },
            "VARIANT": {
                "establishes_exact_rakuten_variant": False,
                "cta_requires_separate_exact_variant_evidence": True,
            },
        },
        "evidence_resolution_policy": {
            "exact_variant_reader_visible_purchase_ui_required": True,
            "reader_visible_sold_out_discontinued_or_preorder_precedes_hidden_structured_availability": True,
            "structured_data_alone_cannot_establish_available": True,
            "conflict_resolution": "FAIL_CLOSED_TO_UNKNOWN_OR_OUT_OF_STOCK",
            "preorder_resolution": "FAIL_CLOSED_TO_UNKNOWN",
        },
        "publication_policy": {
            "AVAILABLE": {
                "state_gate": "CONDITIONAL",
                "known_state": True,
                "recheck_required": True,
            },
            "OUT_OF_STOCK": {
                "state_gate": "INELIGIBLE",
                "known_state": True,
                "recheck_required": True,
            },
            "UNKNOWN": {
                "state_gate": "INELIGIBLE",
                "known_state": False,
                "recheck_required": True,
            },
            "DISCONTINUED": {
                "state_gate": "INELIGIBLE",
                "known_state": True,
                "recheck_required": True,
            },
        },
        "products": rows,
    }
    audit_path = tmp_path / portfolio_script.SALES_STATUS_RELATIVE_PATH
    audit_path.parent.mkdir(parents=True)
    audit_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    audit_path.chmod(0o644)
    monkeypatch.setattr(portfolio_script, "ROOT", tmp_path)
    monkeypatch.setattr(
        portfolio_script,
        "_read_sales_json",
        lambda _path: document,
    )

    statuses = portfolio_script._load_sales_statuses(portfolio, fact_dates)

    assert sum(status.state == "AVAILABLE" for status in statuses.values()) == 31
    assert sum(status.state == "OUT_OF_STOCK" for status in statuses.values()) == 2
    assert all(status.state != "UNKNOWN" for status in statuses.values())
    assert statuses["PRD-ACE-DIFFERENCE-05721"].availability_scope == "VARIANT"
    assert all(
        status.availability_scope == "MODEL"
        for product_id, status in statuses.items()
        if product_id != "PRD-ACE-DIFFERENCE-05721"
    )
    assert all(
        status.variant_caveat is not None
        and cast(dict[str, object], status.variant_caveat)[
            "establishes_exact_rakuten_variant"
        ]
        is False
        for status in statuses.values()
    )

    future_document = deepcopy(document)
    future_checked_at = "2026-09-01T00:06:00Z"
    future_document["checked_at_utc"] = future_checked_at
    for row in cast(list[dict[str, object]], future_document["products"]):
        row["checked_at_utc"] = future_checked_at
        row["structured_snapshot_sha256"] = hashlib.sha256(
            portfolio_script._canonical_bytes(
                {
                    field: row[field]
                    for field in portfolio_script.SALES_STATUS_HASH_FIELDS
                }
            )
        ).hexdigest()
    monkeypatch.setattr(
        portfolio_script,
        "_read_sales_json",
        lambda _path: future_document,
    )
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID",
    ):
        portfolio_script._load_sales_statuses(
            portfolio,
            fact_dates,
            now=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        )
    monkeypatch.setattr(
        portfolio_script,
        "_read_sales_json",
        lambda _path: document,
    )

    cast(dict[str, object], rows[0])["structured_snapshot_sha256"] = "0" * 64
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID",
    ):
        portfolio_script._load_sales_statuses(portfolio, fact_dates)


def test_tracked_manufacturer_sales_audit_binds_all_products_but_does_not_hide_due_diligence_gaps() -> (
    None
):
    portfolio = load_editorial_portfolio_v2(ROOT)
    fact_dates = portfolio_script._source_fact_date_contract(portfolio)

    statuses = portfolio_script._load_sales_statuses(portfolio, fact_dates)
    report = portfolio_script._selection_audit_report(portfolio, now=SELECTION_NOW)
    completion = cast(dict[str, object], report["completion"])

    assert len(statuses) == len(portfolio.products) == 33
    assert sum(status.state == "AVAILABLE" for status in statuses.values()) == len(
        portfolio.products
    )
    assert {
        product_id
        for product_id, status in statuses.items()
        if status.state == "UNKNOWN"
    } == set()
    assert all(
        status.official_url == portfolio.product_by_id[product_id].official_url
        and status.snapshot_sha256 is not None
        and status.status_evidence_urls
        for product_id, status in statuses.items()
    )
    assert statuses["PRD-ACE-DIFFERENCE-05721"].availability_scope == "VARIANT"
    report_by_id = {
        cast(str, row["product_id"]): row
        for row in cast(list[dict[str, object]], report["products"])
    }
    assert (
        cast(
            dict[str, object],
            report_by_id["PRD-ACE-DIFFERENCE-05721"]["manufacturer_sales_state"],
        )["availability_scope"]
        == "VARIANT"
    )
    assert completion["sales_state_verified_product_count"] == 33
    assert completion["axis_complete_product_count"] == 0
    assert set(cast(list[str], completion["axis_incomplete_product_ids"])) == {
        product.product_id for product in portfolio.products
    }
    assert completion["state"] == "INCOMPLETE"
    assert set(cast(list[str], completion["ineligible_product_ids"])) == set()

    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_PRODUCT_SAFETY_INCOMPLETE",
    ):
        portfolio_script._require_selection_completion(portfolio)


def test_known_out_of_stock_requires_recheck_and_blocks_with_unknown_or_discontinued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    out_of_stock = {
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-SIROCA-SS-M171",
    }

    def statuses_with(overrides: dict[str, str]) -> dict[str, object]:
        result: dict[str, object] = {}
        for product in portfolio.products:
            state = overrides.get(
                product.product_id,
                "OUT_OF_STOCK" if product.product_id in out_of_stock else "AVAILABLE",
            )
            result[product.product_id] = portfolio_script.SalesStatusEvidence(
                product_id=product.product_id,
                state=state,
                availability_scope="MODEL",
                official_url=product.official_url,
                status_evidence_urls=(product.official_url,),
                locator="公式販売状態",
                basis="公式ページ確認",
                variant_caveat={
                    "code": "MODEL_SCOPE_ONLY",
                    "detail": "モデル単位であり楽天CTAのvariant適格性は証明しない。",
                    "establishes_exact_rakuten_variant": False,
                },
                alternative=None,
                snapshot_sha256="a" * 64,
            )
        return result

    monkeypatch.setattr(
        portfolio_script,
        "_load_sales_statuses",
        lambda _portfolio, _dates, **_kwargs: statuses_with({}),
    )
    report = portfolio_script._selection_audit_report(portfolio, now=SELECTION_NOW)
    completion = cast(dict[str, object], report["completion"])
    assert completion["state"] == "INCOMPLETE"
    assert completion["sales_state_available_product_count"] == 31
    assert completion["sales_state_out_of_stock_product_count"] == 2
    assert set(cast(list[str], completion["out_of_stock_recheck_product_ids"])) == (
        out_of_stock
    )
    assert set(cast(list[str], completion["ineligible_product_ids"])) == out_of_stock
    assert completion["affiliate_variant_eligibility"] == (
        "NOT_ATTESTED_BY_MODEL_SALES_STATE"
    )

    for blocked_state in ("UNKNOWN", "DISCONTINUED"):
        monkeypatch.setattr(
            portfolio_script,
            "_load_sales_statuses",
            lambda _portfolio, _dates, state=blocked_state, **_kwargs: statuses_with(
                {portfolio.products[0].product_id: state}
            ),
        )
        blocked = portfolio_script._selection_audit_report(portfolio, now=SELECTION_NOW)
        assert cast(dict[str, object], blocked["completion"])["state"] == "INCOMPLETE"


def test_production_and_strict_local_materialization_require_sales_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    monkeypatch.setattr(
        portfolio_script,
        "load_editorial_portfolio_v2",
        lambda _root: portfolio,
    )

    def reject(
        _portfolio: EditorialPortfolioV2, *, now: datetime | None = None
    ) -> None:
        del now
        raise EditorialPortfolioV2Failure(
            "RAOS_EDITORIAL_PORTFOLIO_SALES_STATE_UNVERIFIED"
        )

    monkeypatch.setattr(portfolio_script, "_require_selection_completion", reject)
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_SALES_STATE_UNVERIFIED",
    ):
        portfolio_script.materialize(tmp_path.resolve(), mode="production")
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_SALES_STATE_UNVERIFIED",
    ):
        portfolio_script.materialize(
            tmp_path.resolve(),
            mode="local",
            require_complete=True,
        )


def test_materialization_receipt_counts_actual_cta_kinds() -> None:
    article = cast(
        ArticleBindingV2,
        SimpleNamespace(product_ids=("PRD-TEST-ONE",)),
    )
    markup = (
        '<a class="rakuten-cta raos-cta" href="https://example.test/one" '
        'rel="sponsored nofollow" data-raos-product-id="PRD-TEST-ONE" '
        'data-raos-placement="product_card">楽天</a>'
        '<a class="official-product-link raos-cta" '
        'href="https://manufacturer.example/one" rel="noopener noreferrer" '
        'data-raos-product-id="PRD-TEST-ONE" '
        'data-raos-placement="final_summary">公式</a>'
    )

    assert portfolio_script._materialized_cta_kind_counts(
        markup,
        article=article,
    ) == (1, 1)

    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_CTA_STRUCTURE_INVALID",
    ):
        portfolio_script._materialized_cta_kind_counts(
            markup.replace("sponsored nofollow", "nofollow"),
            article=article,
        )


def test_materialization_source_snapshot_is_rechecked_before_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio = cast(
        EditorialPortfolioV2,
        SimpleNamespace(source_sha256="a" * 64, products=()),
    )
    views = cast(dict[str, ProductEvidenceViewV2], {"PRD-TEST": object()})
    expected = {
        portfolio_script.ROOT / portfolio_script.PORTFOLIO_RELATIVE_PATH: b"portfolio",
        portfolio_script.ROOT / portfolio_script.STATUS_RELATIVE_PATH: b"status",
        portfolio_script.ROOT / portfolio_script.SALES_STATUS_RELATIVE_PATH: b"sales",
    }
    sales_reads = 0

    def read(path: Path, *, optional: bool = False) -> bytes | None:
        nonlocal sales_reads
        assert path in expected
        if path == portfolio_script.ROOT / portfolio_script.SALES_STATUS_RELATIVE_PATH:
            sales_reads += 1
            if sales_reads == 2:
                return b"changed-sales"
        return expected[path]

    monkeypatch.setattr(portfolio_script, "_read_source_snapshot", read)
    monkeypatch.setattr(
        portfolio_script,
        "load_editorial_portfolio_v2",
        lambda _root: portfolio,
    )
    monkeypatch.setattr(
        portfolio_script,
        "product_evidence_views_v2",
        lambda *_args, **_kwargs: views,
    )
    monkeypatch.setattr(
        portfolio_script,
        "require_manufacturer_sales_state_for_products_v1",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_SOURCE_CHANGED",
    ):
        portfolio_script._require_materialization_sources_current(
            portfolio_raw=b"portfolio",
            status_raw=b"status",
            sales_state_raw=b"sales",
            portfolio=portfolio,
            views=views,
            now=datetime.now(UTC),
            require_complete=True,
        )


def _provider_identity_evidence(
    binding: ProductBindingV2,
    *,
    item_name: str | None = None,
    jan: str | None | object = ...,
    source_item: str | None = None,
    affiliate_pc_item: str | None = None,
) -> RakutenProductEvidence:
    assert binding.rakuten_item_code is not None
    shop, item = binding.rakuten_item_code.split(":", 1)
    source_tail = item if source_item is None else source_item
    affiliate_pc_tail = source_tail if affiliate_pc_item is None else affiliate_pc_item
    source = f"https://item.rakuten.co.jp/{shop}/{source_tail}/"
    affiliate_pc = f"https://item.rakuten.co.jp/{shop}/{affiliate_pc_tail}/"
    destination = "https://hb.afl.rakuten.co.jp/hgc/test.abc/?" + urlencode(
        {
            "m": f"https://m.rakuten.co.jp/{shop}/i/{item}/",
            "pc": affiliate_pc,
            "rafcid": "provider-identity-test",
        }
    )
    return cast(
        RakutenProductEvidence,
        SimpleNamespace(
            product_id=binding.product_id,
            affiliate_ref=binding.affiliate_ref,
            media_asset_ref=binding.media_asset_ref,
            item_code=binding.rakuten_item_code,
            item_name=(
                f"{binding.official_name} {binding.representative_model} "
                f"{binding.required_title_tokens[0]} {binding.product_kind_tokens[0]}"
                if item_name is None
                else item_name
            ),
            jan=binding.official_jan if jan is ... else jan,
            variant=binding.representative_model,
            source_url=source,
            destination_url=destination,
            width=128,
            height=128,
        ),
    )


def test_provider_identity_uses_separate_official_jan_evidence_and_exact_item() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    binding = portfolio.product_by_id["PRD-IROBOT-ROOMBA-PLUS-515-COMBO"]
    jan_binding_sha256 = "a" * 64

    _validate_rakuten_identity(
        binding,
        _provider_identity_evidence(binding, jan=None),
        jan_evidence_sha256=jan_binding_sha256,
    )
    _validate_rakuten_identity(
        binding,
        _provider_identity_evidence(binding, source_item="provider-custom-slug"),
        jan_evidence_sha256=jan_binding_sha256,
    )

    title_without_model = "Roomba Plus Combo ロボット掃除機"
    for evidence in (
        _provider_identity_evidence(binding, item_name=title_without_model),
        _provider_identity_evidence(binding, jan="4900000000000"),
        _provider_identity_evidence(binding, affiliate_pc_item="different-item"),
    ):
        with pytest.raises(
            EditorialPortfolioV2Failure,
            match="RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID",
        ):
            _validate_rakuten_identity(
                binding,
                evidence,
                jan_evidence_sha256=jan_binding_sha256,
            )
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID",
    ):
        _validate_rakuten_identity(
            binding,
            _provider_identity_evidence(binding, jan=None),
        )


def test_official_jan_snapshot_contract_binds_exact_model_jan_and_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = ProductBindingV2(
        product_id="PRD-TEST-JAN",
        official_name="JAN Test",
        official_models=("MODEL-JAN",),
        representative_model="MODEL-JAN",
        official_jan="4901234567894",
        official_url="https://manufacturer.example/products/model-jan",
        rakuten_shop_code="shop",
        rakuten_item_code="shop:10000001",
        required_title_tokens=("MODEL-JAN",),
        product_kind_tokens=("test",),
        forbidden_title_tokens=("accessory",),
    )
    portfolio = EditorialPortfolioV2(
        version="test",
        target_origin="https://example.com",
        theme_version="1.5.0",
        editorial_reviewed_on="2026-09-01",
        articles=(),
        products=(product,),
    )
    verified_at = "2026-09-01T00:00:00Z"
    snapshot = b"MODEL-JAN official JAN 4901234567894\n"
    snapshot_root = tmp_path / portfolio_module.JAN_EVIDENCE_SNAPSHOT_RELATIVE_ROOT
    snapshot_root.mkdir(parents=True, mode=0o700)
    snapshot_path = snapshot_root / "PRD-TEST-JAN.snapshot.txt"
    snapshot_path.write_bytes(snapshot)
    snapshot_path.chmod(0o600)
    receipt_path = tmp_path / portfolio_module.JAN_EVIDENCE_RELATIVE_PATH
    receipt_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = {
        "schema": portfolio_module.JAN_EVIDENCE_SCHEMA,
        "verified_at": verified_at,
        "portfolio_sha256": "a" * 64,
        "owner_attested": True,
        "products": [
            {
                "product_id": product.product_id,
                "representative_model": product.representative_model,
                "official_jan": product.official_jan,
                "official_url": product.official_url,
                "source_locator": "公式仕様表のJANコード欄",
                "source_snapshot_file": snapshot_path.name,
                "source_snapshot_sha256": hashlib.sha256(snapshot).hexdigest(),
                "verified_at": verified_at,
            }
        ],
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    receipt_path.chmod(0o600)
    monkeypatch.setattr(portfolio_module, "portfolio_sha256", lambda _: "a" * 64)

    bindings = product_jan_evidence_bindings_v1(
        tmp_path,
        portfolio=portfolio,
        now=datetime(2026, 9, 1, 1, tzinfo=UTC),
    )

    assert set(bindings) == {product.product_id}
    assert re.fullmatch(r"[0-9a-f]{64}", bindings[product.product_id])
    assert portfolio_script._target(product).jan is None

    snapshot_path.write_text("MODEL-JAN wrong JAN", encoding="utf-8")
    snapshot_path.chmod(0o600)
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_JAN_EVIDENCE_INVALID",
    ):
        product_jan_evidence_bindings_v1(
            tmp_path,
            portfolio=portfolio,
            now=datetime(2026, 9, 1, 1, tzinfo=UTC),
        )


def test_capture_listing_mismatch_falls_back_per_product_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    products = tuple(
        ProductBindingV2(
            product_id=f"PRD-TEST-{number}",
            official_name=f"Test {number}",
            official_models=(f"MODEL-{number}",),
            representative_model=f"MODEL-{number}",
            official_jan=None,
            official_url=f"https://example.com/{number}",
            rakuten_shop_code="shop",
            rakuten_item_code=f"shop:1000000{number}",
            required_title_tokens=(f"MODEL-{number}",),
            product_kind_tokens=("test",),
            forbidden_title_tokens=("accessory",),
        )
        for number in (1, 2)
    )
    portfolio = EditorialPortfolioV2(
        version="test",
        target_origin="https://example.com",
        theme_version="1.3.10",
        editorial_reviewed_on="2026-08-31",
        articles=(),
        products=products,
    )
    calls: list[str] = []

    def no_existing(*_args: object, **_kwargs: object) -> None:
        raise EditorialPilotFailure(EditorialPilotFailureCode.RESOURCE_NOT_READY)

    def capture_one(
        _root: Path, target: object, _credentials: object, **_kwargs: object
    ) -> object:
        product_id = cast(capture_module.ProductCaptureTarget, target).product_id
        calls.append(product_id)
        if product_id == "PRD-TEST-1":
            raise capture_module.RakutenProductCaptureFailure(
                capture_module.RakutenProductCaptureFailureCode.PRODUCT_LISTING_MISMATCH
            )
        return SimpleNamespace(
            product_id=product_id,
            retrieved_at="2026-08-30T00:00:00Z",
            item_code="shop:10000002",
            response_sha256="b" * 64,
            affiliate_response_sha256="c" * 64,
            image_sha256="d" * 64,
        )

    monkeypatch.setattr(portfolio_script, "ROOT", tmp_path)
    monkeypatch.setattr(
        portfolio_script, "load_editorial_portfolio_v2", lambda _: portfolio
    )
    monkeypatch.setattr(portfolio_script, "portfolio_sha256", lambda _: "e" * 64)
    monkeypatch.setattr(
        portfolio_script, "product_evidence_views_v2", lambda *_a, **_k: {}
    )
    monkeypatch.setattr(portfolio_script, "read_rakuten_product_evidence", no_existing)
    monkeypatch.setattr(
        capture_module, "require_clean_capture_environment", lambda: None
    )
    monkeypatch.setattr(capture_module, "read_owner_credentials", lambda _: object())
    monkeypatch.setattr(
        capture_module, "SystemRakutenHttpsConnectionFactory", lambda _: object()
    )
    monkeypatch.setattr(capture_module, "_capture_product", capture_one)
    monkeypatch.setattr(
        portfolio_script,
        "_fixed_listing_failure_status",
        lambda *_a, **_k: ("ambiguous", "f" * 64),
    )

    counts = portfolio_script.capture()

    assert calls == ["PRD-TEST-1", "PRD-TEST-2"]
    assert counts == {"verified": 1, "not_found": 0, "ambiguous": 1}
    receipt = json.loads(
        (tmp_path / portfolio_module.STATUS_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    assert [row["state"] for row in receipt["products"]] == ["ambiguous", "verified"]


@pytest.mark.parametrize(
    "code",
    (
        capture_module.RakutenProductCaptureFailureCode.RESPONSE_INVALID,
        capture_module.RakutenProductCaptureFailureCode.CREDENTIAL_REFLECTION,
        capture_module.RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_INVALID,
        capture_module.RakutenProductCaptureFailureCode.IMAGE_INVALID,
    ),
)
def test_capture_integrity_and_runtime_failures_are_not_product_fallbacks(
    code: capture_module.RakutenProductCaptureFailureCode,
) -> None:
    assert (
        portfolio_script._is_product_listing_fallback(
            capture_module.RakutenProductCaptureFailure(code)
        )
        is False
    )


def test_fixed_listing_fallback_rejects_credential_reflection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = load_editorial_portfolio_v2(ROOT).product_by_id[
        "PRD-IROBOT-ROOMBA-PLUS-515-COMBO"
    ]
    assert binding.rakuten_item_code is not None
    shop, item = binding.rakuten_item_code.split(":", 1)
    raw = json.dumps(
        {
            "Items": [
                {
                    "itemCode": binding.rakuten_item_code,
                    "itemName": "Roomba N285060 test-access-key ロボット掃除機",
                    "itemUrl": f"https://item.rakuten.co.jp/{shop}/{item}/",
                    "mediumImageUrls": [],
                }
            ]
        },
        separators=(",", ":"),
    ).encode()
    credentials = capture_module.RakutenCredentials(
        "test-application", "test-access-key", "test-affiliate"
    )
    monkeypatch.setattr(capture_module, "_api_request", lambda *_a, **_k: raw)

    with pytest.raises(capture_module.RakutenProductCaptureFailure) as captured:
        portfolio_script._fixed_listing_failure_status(
            binding,
            credentials,
            object(),
            output_directory=tmp_path,
        )

    assert (
        captured.value.code
        is capture_module.RakutenProductCaptureFailureCode.CREDENTIAL_REFLECTION
    )


def test_each_product_is_formally_introduced_before_its_first_shortened_reference() -> (
    None
):
    portfolio = load_editorial_portfolio_v2(ROOT)
    audited_product_ids: set[str] = set()
    audited_article_cards = 0

    for article in portfolio.articles:
        markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
            encoding="utf-8"
        )
        first_bound_product = markup.find("data-raos-product-id=")
        if not article.product_ids:
            assert first_bound_product == -1
            continue
        assert first_bound_product > 0
        introduction = _visible_text(markup[:first_bound_product])
        article_text = _visible_text(markup)

        for product_id in article.product_ids:
            product = portfolio.product_by_id[product_id]
            formal_prefix, first_reference = _formal_product_prefix(
                product_id, product.official_name, product.representative_model
            )
            formal_position = article_text.find(formal_prefix)
            assert formal_position >= 0, (article.production_slug, product_id)
            first_reference_position = article_text.find(first_reference)
            assert first_reference_position == formal_position + formal_prefix.find(
                first_reference
            ), (
                article.production_slug,
                product_id,
            )
            assert formal_prefix in introduction, (article.production_slug, product_id)
            audited_product_ids.add(product_id)
            audited_article_cards += 1

    assert audited_product_ids == set(portfolio.product_by_id)
    assert audited_article_cards == 37


def test_all_source_articles_are_editorial_v2_and_have_two_cta_slots_per_card() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)

    for article in portfolio.articles:
        markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
            encoding="utf-8"
        )
        assert markup.count('class="raos-editorial-v2"') == 1
        assert markup.count('class="raos-disclosure disclosure"') == 1
        if article.article_id == "solota-vs-rakua-mini-plus":
            assert article.product_ids == ()
            assert markup.count(STANDARD_AD_DISCLOSURE) == 0
            assert markup.count(STANDARD_AD_DETAILS) == 0
            assert markup.count(NONAFFILIATE_DISCLOSURE) == 1
        else:
            assert article.product_ids
            assert markup.count(STANDARD_AD_DISCLOSURE) == 1
            assert markup.count(STANDARD_AD_DETAILS) == 1
            assert markup.count(NONAFFILIATE_DISCLOSURE) == 0
        if article.article_id.startswith("st1704-") or article.article_id.startswith(
            "st1703-"
        ):
            intro_at = markup.index('class="raos-article-intro"')
            facts_at = markup.index('class="raos-article-facts article-meta"')
            disclosure_at = markup.index('class="raos-disclosure disclosure"')
            scope_at = markup.index('class="raos-article-scope"')
            assert intro_at < facts_at < disclosure_at < scope_at
            intro_scope_paragraphs = re.findall(
                r'<p class="raos-article-intro__scope">(.*?)</p>',
                markup,
                flags=re.DOTALL,
            )
            assert intro_scope_paragraphs
            assert all(
                len(_visible_text(paragraph)) <= 300
                for paragraph in intro_scope_paragraphs
            )
            if article.article_id in {
                "st1704-anker-solix-c300-c800-c1000-differences",
                "st1704-countertop-dishwasher-for-small-households",
                "st1704-compact-robot-vacuum-shortlist",
            }:
                assert len(intro_scope_paragraphs) == 2
        if article.source_kind == "html_fixture":
            lead_at = markup.index('class="lead-section"')
            facts_at = markup.index('class="raos-article-facts article-meta"')
            lead_close_at = markup.index("</section>", lead_at)
            disclosure_at = markup.index('class="raos-disclosure disclosure"')
            decision_at = markup.index('class="decision-section"')
            assert 'class="hero-photo"' not in markup
            assert lead_at < facts_at < lead_close_at < disclosure_at < decision_at
            lead_paragraphs = re.findall(
                r"<p(?:\s[^>]*)?>(.*?)</p>",
                markup[lead_at:facts_at],
                flags=re.DOTALL,
            )
            assert lead_paragraphs
            assert all(
                len(_visible_text(paragraph)) <= 300 for paragraph in lead_paragraphs
            )
            if (
                article.article_id
                == "st1704-countertop-dishwasher-for-small-households"
            ):
                assert markup.count("仕様上の比較ポイント：") == 0
                assert markup.count("おすすめする理由：") == 4
        assert FIXED_HEADING_BREAK.search(markup) is None
        assert not any(term in markup for term in READER_FACING_PROHIBITED)
        observed_units = set(re.findall(r"(?<=\d)(?:cm|mm)", markup))
        if article.article_id == "st1704-compact-robot-vacuum-shortlist":
            assert observed_units == {"cm", "mm"}
            assert "幅32.0×奥行40.0×高さ38.5cm" in markup
            assert "各数値の軸は未確認" not in markup
        elif article.article_id == "roomba-mini-vs-switchbot-k11-pro":
            assert observed_units == {"cm"}
        elif article.article_id == "solota-vs-rakua-mini-plus":
            assert observed_units == set()
            assert "以前の比較対象の販売状態を確認し" in markup
            assert "商品カードとアフィリエイトリンクは掲載していません" in markup
        elif article.article_id == "front-open-carry-on-suitcase-with-stopper":
            assert observed_units == {"cm", "mm"}
            assert "55mm静音キャスター" in markup
            assert "60mm大径キャスター" in markup
        else:
            assert "幅×奥行×高さ" in markup
            assert len(observed_units) == 1
        assert (
            re.search(
                r"(?:^|[^A-Za-z])(?:W|D|H)\s*\d+(?:\.\d+)?\s*(?:cm|mm)",
                markup,
            )
            is None
        )
        assert "https://hb.afl.rakuten.co.jp/" not in markup
        source_sections = re.findall(
            r'<section\b[^>]*class=["\'][^"\']*\bsources-section\b[^"\']*["\'][^>]*>'
            r".*?</section>",
            markup,
            flags=re.IGNORECASE | re.DOTALL,
        )
        assert source_sections
        assert all("data-raos-placement=" not in section for section in source_sections)
        assert all("rakuten-cta" not in section for section in source_sections)
        for product_id in article.product_ids:
            assert portfolio.product_by_id[product_id].official_url in markup
            tags = re.findall(
                r"<a\b(?=[^>]*\bdata-raos-product-id=[\"']"
                + re.escape(product_id)
                + r"[\"'])[^>]*>",
                markup,
                flags=re.IGNORECASE,
            )
            placements = sorted(_attributes(tag)["data-raos-placement"] for tag in tags)
            assert placements == ["final_summary", "product_card"]
            assert (
                len(
                    re.findall(
                        r"<article\b(?=[^>]*\bdata-raos-product-id=[\"']"
                        + re.escape(product_id)
                        + r"[\"'])[^>]*>",
                        markup,
                        flags=re.IGNORECASE,
                    )
                )
                == 1
            )


def test_renderer_market_exclusions_are_source_bound_and_idempotent() -> None:
    base = (
        '<section class="method-section"><h2>比較方法</h2></section>'
        '<section class="after"><h2>次の節</h2></section>'
    )

    for article_id in RENDERER_ARTICLE_IDS:
        audit = portfolio_script._market_candidate_audit_for(article_id)
        heading = cast(str, audit["reader_visible_exclusions_heading"])
        rendered = portfolio_script._reader_visible_market_exclusions(
            base,
            article_id,
        )
        assert rendered.count(f">{heading}</h2>") == 1
        assert "メーカー公式情報を確認する" in rendered
        assert "型番・対象範囲：" in rendered
        assert "比較表に含めなかった理由：" in rendered
        assert "EVALUATED_NOT_DIFFERENTIATING" not in rendered
        assert "SELECTED_PRODUCT_DUE_DILIGENCE" not in rendered
        assert (
            portfolio_script._reader_visible_market_exclusions(
                rendered,
                article_id,
            )
            == rendered
        )


def test_every_audited_external_candidate_is_visible_and_source_linked() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    for article in portfolio.articles:
        markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
            encoding="utf-8"
        )
        assert (
            portfolio_script._validate_reader_visible_market_exclusions(
                markup,
                article.article_id,
            )
            == markup
        )

    target = next(
        article
        for article in portfolio.articles
        if article.article_id == "carry-on-suitcase-under-100-seats"
    )
    markup = (ARTICLE_ROOT / f"{target.production_slug}.html").read_text(
        encoding="utf-8"
    )
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_NOT_READER_VISIBLE",
    ):
        portfolio_script._validate_reader_visible_market_exclusions(
            markup.replace(
                "https://www.muji.com/jp/ja/store/cmdty/detail/4550723184182",
                "https://example.invalid/hidden",
            ),
            target.article_id,
        )


def test_tracked_source_fixtures_match_their_owner_projection() -> None:
    assert portfolio_script.check_source_fixtures() == 10


def test_reader_visible_role_and_intent_are_projected_from_v3_identities() -> None:
    identities = json.loads(
        (ROOT / portfolio_script.EDITORIAL_IDENTITIES_RELATIVE_PATH).read_text(
            encoding="utf-8"
        )
    )
    portfolio = load_editorial_portfolio_v2(ROOT)
    article_by_id = {article.article_id: article for article in portfolio.articles}

    for row in identities["articles"]:
        article = article_by_id[row["article_id"]]
        markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
            encoding="utf-8"
        )
        assert (
            markup.count(
                f"<div><dt>記事分類</dt><dd>{row['content_role_label']}</dd></div>"
            )
            == 1
        )
        assert (
            markup.count(
                "<div><dt>この記事で答えること</dt><dd>"
                f"{row['primary_query_intent']}</dd></div>"
            )
            == 1
        )


def test_rakuten_credit_sanitizer_restores_the_unmodified_provider_snippet() -> None:
    markup = (
        '<section class="sources-section"><ol><li>一次情報</li></ol>'
        '<p class="raos-source-link"><a href="https://developers.rakuten.com/">'
        "商品情報の取得に楽天ウェブサービスを利用しています</a></p></section>"
    )
    rendered = portfolio_script._ensure_exact_rakuten_credit(markup)
    exact_anchor = (
        '<a href="https://developers.rakuten.com/" target="_blank" rel="noopener noreferrer">'
        "Supported by Rakuten Developers</a>"
    )

    assert rendered.count(exact_anchor) == 1
    assert "商品情報の取得には楽天ウェブサービスを利用しています。" in rendered
    assert rendered.count("Rakuten Web Services Attribution Snippet FROM HERE") == 1
    assert rendered.count("Rakuten Web Services Attribution Snippet TO HERE") == 1
    assert portfolio_script._ensure_exact_rakuten_credit(rendered) == rendered


def test_unverified_product_media_is_visible_status_not_a_generic_image() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    for article in portfolio.articles:
        markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
            encoding="utf-8"
        )
        for product_id in article.product_ids:
            card = re.search(
                r"<article\b(?=[^>]*\bdata-raos-product-id=[\"']"
                + re.escape(product_id)
                + r"[\"'])[^>]*>.*?</article>",
                markup,
                flags=re.IGNORECASE | re.DOTALL,
            )
            assert card is not None
            assert re.search(r"<img\b", card.group(0), flags=re.I) is None
            assert card.group(0).count("商品画像未確認・購入導線停止") == 1
            assert f'data-raos-product-image-id="{product_id}"' in card.group(0)
            assert 'data-raos-product-image-state="unverified"' in card.group(0)
            assert "商品写真ではありません" not in card.group(0)
        if article.source_kind == "st1704_renderer":
            assert 'class="raos-comparison__product-image"' not in markup
            assert markup.count("raos-product-image-status--compact") == (
                len(article.product_ids) * 2
            )

    siroca = portfolio.product_by_id["PRD-SIROCA-SS-MA251"]
    assert siroca.official_name == "siroca 食器洗い乾燥機 SS-MA251"
    assert siroca.official_models == ("SS-MA251",)
    assert siroca.representative_model == "SS-MA251"


def test_materialization_uses_exact_two_affiliate_ctas_or_official_fallback() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    products = portfolio.product_by_id
    out_of_stock_ids = {
        product_id
        for product_id, sales_state in (
            portfolio.manufacturer_sales_state_by_product_id.items()
        )
        if sales_state.state == "OUT_OF_STOCK"
    }
    sales_ineligible_ids = {
        product_id
        for product_id, sales_state in (
            portfolio.manufacturer_sales_state_by_product_id.items()
        )
        if sales_state.state != "AVAILABLE"
    }
    fallback_ids = {
        product.product_id
        for position, product in enumerate(portfolio.products)
        if position % 3 == 1
    }

    for article in portfolio.articles:
        markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
            encoding="utf-8"
        )
        views = {
            product_id: _fake_view(
                product_id,
                state="not_found" if product_id in fallback_ids else "verified",
            )
            for product_id in article.product_ids
        }
        rendered = materialize_article_v2(
            markup,
            article=article,
            portfolio=portfolio,
            evidence_views=views,
            mode="local",
        )
        for product_id in article.product_ids:
            tags = re.findall(
                r"<a\b(?=[^>]*\bdata-raos-product-id=[\"']"
                + re.escape(product_id)
                + r"[\"'])[^>]*>",
                rendered,
                flags=re.IGNORECASE,
            )
            assert len(tags) == 2
            attributes = [_attributes(tag) for tag in tags]
            assert {item["data-raos-placement"] for item in attributes} == {
                "product_card",
                "final_summary",
            }
            assert {item["data-raos-article-id"] for item in attributes} == {
                article.article_id
            }
            if product_id in fallback_ids or product_id in sales_ineligible_ids:
                sales_state = portfolio.manufacturer_sales_state_by_product_id[
                    product_id
                ]
                attributes_by_placement = {
                    item["data-raos-placement"]: item for item in attributes
                }
                expected_product_card_url = (
                    sales_state.status_evidence_urls[0]
                    if product_id in sales_ineligible_ids
                    else products[product_id].official_url
                )
                assert attributes_by_placement["product_card"]["href"] == (
                    expected_product_card_url
                )
                assert (
                    attributes_by_placement["final_summary"]["href"]
                    == (sales_state.status_evidence_urls[0])
                )
                assert all(
                    "official-product-link" in item["class"] for item in attributes
                )
                assert not any("rakuten-cta" in item["class"] for item in attributes)
                if product_id in out_of_stock_ids:
                    oos_anchors = re.findall(
                        r"<a\b(?=[^>]*\bdata-raos-product-id=[\"']"
                        + re.escape(product_id)
                        + r"[\"'])[^>]*>.*?</a>",
                        rendered,
                        flags=re.IGNORECASE | re.DOTALL,
                    )
                    assert len(oos_anchors) == 2
                    assert all(
                        _visible_text(anchor).startswith(
                            "メーカー公式で販売状況を確認する"
                        )
                        for anchor in oos_anchors
                    )
                    assert "メーカー公式通販で在庫切れのため" in rendered
                    assert "楽天購入リンクは掲載していません" in rendered
                else:
                    assert "一致する楽天商品を確認できなかったため" in rendered
            else:
                assert len({item["href"] for item in attributes}) == 1
                assert all(item["rel"] == "sponsored nofollow" for item in attributes)
                assert all("rakuten-cta" in item["class"] for item in attributes)
                assert "販売元、価格、在庫、商品画像を確認できます" in rendered

            if product_id in fallback_ids:
                card = re.search(
                    r"<article\b(?=[^>]*\bdata-raos-product-id=[\"']"
                    + re.escape(product_id)
                    + r"[\"'])[^>]*>.*?</article>",
                    rendered,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                assert card is not None
                assert re.search(r"<img\b", card.group(0), flags=re.I) is None
                assert "商品画像未確認・購入導線停止" in card.group(0)
                assert 'data-raos-product-image-state="unverified"' in card.group(0)
            else:
                image = re.search(
                    rf'<img\b(?=[^>]*data-raos-product-image-id="{re.escape(product_id)}")'
                    r'(?=[^>]*data-raos-product-image-state="verified")[^>]*>',
                    rendered,
                )
                assert image is not None
                image_attributes = _attributes(image.group(0))
                assert image_attributes["width"] == "128"
                assert image_attributes["height"] == "128"
                assert image_attributes["loading"] == "lazy"
                assert products[product_id].official_name in image_attributes["alt"]
                assert f'src="/raos-product-media/{product_id}.jpg"' in rendered
        assert (
            re.search(r"\bsrc=([\"'])https://", rendered, flags=re.IGNORECASE) is None
        )
        assert 'class="raos-comparison__product-image"' not in rendered


def test_lifecycle_route_materializes_without_products_and_rejects_cta_injection() -> (
    None
):
    portfolio = load_editorial_portfolio_v2(ROOT)
    article = portfolio.article_by_production_slug["solota-vs-rakua-mini-plus"]
    assert article.product_ids == ()
    markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
        encoding="utf-8"
    )

    rendered = materialize_article_v2(
        markup,
        article=article,
        portfolio=portfolio,
        evidence_views={},
        mode="production",
    )
    assert "data-raos-product-id=" not in rendered

    injected = markup.replace(
        "</div>",
        '<a data-raos-product-id="PRD-SIROCA-SS-M171" '
        'data-raos-placement="product_card" href="https://example.invalid/">x</a>'
        "</div>",
        1,
    )
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_CTA_STRUCTURE_INVALID",
    ):
        materialize_article_v2(
            injected,
            article=article,
            portfolio=portfolio,
            evidence_views={},
            mode="production",
        )


def test_product_card_image_is_the_only_browser_candidate() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    article = portfolio.articles[0]
    markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
        encoding="utf-8"
    )
    views = {
        product_id: _fake_view(product_id, state="verified")
        for product_id in article.product_ids
    }
    first_product_id = article.product_ids[0]
    responsive = re.sub(
        r"<p\b(?=[^>]*data-raos-product-image-placement=[\"']product_card[\"'])"
        r"[^>]*>.*?</p>",
        (
            '<img src="/wp-content/themes/kurashinoshirube-child/assets/images/'
            'article-suitcase-guide.webp" alt="stale" '
            'srcset="https://example.invalid/unverified.webp 2x" sizes="100vw" '
            f'data-raos-product-image-id="{first_product_id}" '
            'data-raos-product-image-placement="product_card" '
            'data-raos-product-image-state="unverified">'
        ),
        markup,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    rendered = materialize_article_v2(
        responsive,
        article=article,
        portfolio=portfolio,
        evidence_views=views,
        mode="local",
    )
    first_card = re.search(
        r"<article\b(?=[^>]*data-raos-product-id=).*?</article>",
        rendered,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert first_card is not None
    assert len(re.findall(r"<img\b", first_card.group(0), flags=re.I)) == 1
    assert re.search(r"\s(?:srcset|sizes)\s*=", first_card.group(0), flags=re.I) is None


@pytest.mark.parametrize(
    "injected",
    (
        '<img src="/wp-content/themes/kurashinoshirube-child/assets/images/extra.webp" alt="">',
        '<source srcset="https://example.invalid/unverified.webp">',
    ),
)
def test_product_card_rejects_extra_image_candidates(injected: str) -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    article = portfolio.articles[0]
    markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
        encoding="utf-8"
    )
    markup = re.sub(
        r"(<article\b(?=[^>]*data-raos-product-id=)[^>]*>.*?"
        r"<div\b[^>]*class=[\"'][^\"']*raos-product-card__media[^\"']*[\"']"
        r"[^>]*>)",
        lambda match: match.group(1) + injected,
        markup,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID",
    ):
        materialize_article_v2(
            markup,
            article=article,
            portfolio=portfolio,
            evidence_views={
                product_id: _fake_view(product_id, state="verified")
                for product_id in article.product_ids
            },
            mode="local",
        )


def test_manufacturer_sales_state_gate_binds_digest_freshness_and_availability() -> (
    None
):
    portfolio = load_editorial_portfolio_v2(ROOT)
    audit = portfolio.manufacturer_sales_state_audit
    assert audit is not None
    assert (
        audit.document_sha256
        == hashlib.sha256(
            (
                ROOT / portfolio_module.MANUFACTURER_SALES_STATE_RELATIVE_PATH
            ).read_bytes()
        ).hexdigest()
    )
    checked_at = max(
        datetime.fromisoformat(row.checked_at_utc.replace("Z", "+00:00"))
        for row in audit.products
    )
    available_product_ids = tuple(
        row.product_id for row in audit.products if row.state == "AVAILABLE"
    )
    assert (
        require_manufacturer_sales_state_for_products_v1(
            portfolio,
            available_product_ids,
            now=checked_at,
        ).document_sha256
        == audit.document_sha256
    )
    assert available_product_ids == tuple(
        product.product_id for product in portfolio.products
    )
    ineligible = replace(
        portfolio,
        manufacturer_sales_state_audit=replace(
            audit,
            products=tuple(
                replace(
                    row,
                    state="OUT_OF_STOCK" if index == 0 else "AVAILABLE",
                )
                for index, row in enumerate(audit.products)
            ),
        ),
    )
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INELIGIBLE",
    ):
        require_manufacturer_sales_state_for_products_v1(
            ineligible,
            tuple(product.product_id for product in ineligible.products),
            now=checked_at,
        )

    current = datetime.now(UTC).replace(microsecond=0)
    current_text = current.strftime("%Y-%m-%dT%H:%M:%SZ")
    available = replace(
        portfolio,
        manufacturer_sales_state_audit=replace(
            audit,
            checked_at_utc=current_text,
            products=tuple(
                replace(row, state="AVAILABLE", checked_at_utc=current_text)
                for row in audit.products
            ),
        ),
    )
    assert (
        require_manufacturer_sales_state_for_products_v1(
            available,
            tuple(product.product_id for product in available.products),
            now=current,
        ).document_sha256
        == audit.document_sha256
    )
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_STALE",
    ):
        require_manufacturer_sales_state_for_products_v1(
            available,
            tuple(product.product_id for product in available.products),
            now=current + timedelta(hours=24, seconds=1),
        )


@pytest.mark.parametrize("fallback_state", ("not_found", "ambiguous", "expired"))
def test_each_unverified_state_uses_only_official_fallbacks(
    fallback_state: Literal["not_found", "ambiguous", "expired"],
) -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)

    for article in portfolio.articles:
        markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
            encoding="utf-8"
        )
        rendered = materialize_article_v2(
            markup,
            article=article,
            portfolio=portfolio,
            evidence_views={
                product_id: _fake_view(product_id, state=fallback_state)
                for product_id in article.product_ids
            },
            mode="local",
        )
        assert 'rel="sponsored nofollow"' not in rendered

        for product_id in article.product_ids:
            product = portfolio.product_by_id[product_id]
            tags = re.findall(
                r"<a\b(?=[^>]*\bdata-raos-product-id=[\"']"
                + re.escape(product_id)
                + r"[\"'])[^>]*>",
                rendered,
                flags=re.IGNORECASE,
            )
            assert len(tags) == 2
            attributes = [_attributes(tag) for tag in tags]
            assert {item["data-raos-placement"] for item in attributes} == {
                "product_card",
                "final_summary",
            }
            sales_state = portfolio.manufacturer_sales_state_by_product_id[product_id]
            attributes_by_placement = {
                item["data-raos-placement"]: item for item in attributes
            }
            expected_product_card_url = (
                sales_state.status_evidence_urls[0]
                if sales_state.state != "AVAILABLE"
                else product.official_url
            )
            assert attributes_by_placement["product_card"]["href"] == (
                expected_product_card_url
            )
            assert (
                attributes_by_placement["final_summary"]["href"]
                == (sales_state.status_evidence_urls[0])
            )
            assert all(item.get("rel") == "noopener noreferrer" for item in attributes)
            assert all(
                "sponsored" not in item.get("rel", "").split() for item in attributes
            )
            assert all("official-product-link" in item["class"] for item in attributes)
            assert not any("rakuten-cta" in item["class"] for item in attributes)

            card = re.search(
                r"<article\b(?=[^>]*\bdata-raos-product-id=[\"']"
                + re.escape(product_id)
                + r"[\"'])[^>]*>.*?</article>",
                rendered,
                flags=re.IGNORECASE | re.DOTALL,
            )
            assert card is not None
            assert re.search(r"<img\b", card.group(0), flags=re.I) is None
            assert "商品画像未確認・購入導線停止" in card.group(0)
            assert 'data-raos-product-image-state="unverified"' in card.group(0)
            if sales_state.state == "OUT_OF_STOCK":
                assert "メーカー公式通販で在庫切れのため" in card.group(0)
                assert "楽天購入リンクは掲載していません" in card.group(0)
                assert "メーカー公式で販売状況を確認する" in card.group(0)
            elif sales_state.state == "UNKNOWN":
                assert "現行販売を確認できていないため購入候補として勧めず" in (
                    card.group(0)
                )
                assert "楽天購入リンクは掲載していません" in card.group(0)
                assert "メーカー公式で販売状況を確認する" in card.group(0)
            else:
                assert "一致する楽天商品を確認できなかったため" in card.group(0)
            assert f"/raos-product-media/{product_id}." not in card.group(0)


def test_production_materialization_uses_provider_image_and_rejects_heading_break(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    article = portfolio.article_by_production_slug["roomba-mini-vs-switchbot-k11-pro"]
    markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
        encoding="utf-8"
    )
    views = {
        product_id: _fake_view(product_id, state="verified")
        for product_id in article.product_ids
    }
    # The checked-in sales-state fixture is intentionally older than the
    # production freshness window.  Keep this rendering contract test focused
    # on provider-image materialization by extending the window locally; the
    # real publication gate remains fail-closed on stale state.
    monkeypatch.setattr(
        portfolio_module,
        "MANUFACTURER_SALES_STATE_FRESHNESS",
        portfolio_module.MANUFACTURER_SALES_STATE_FRESHNESS * 365,
    )

    rendered = materialize_article_v2(
        markup,
        article=article,
        portfolio=portfolio,
        evidence_views=views,
        mode="production",
    )
    assert rendered.count("https://thumbnail.image.rakuten.co.jp/") == len(
        article.product_ids
    )

    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID",
    ):
        materialize_article_v2(
            markup.replace("<h2", "<h2>固定<br></h2><h2", 1),
            article=article,
            portfolio=portfolio,
            evidence_views=views,
            mode="production",
        )

    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INCOMPLETE",
    ):
        materialize_article_v2(
            markup,
            article=article,
            portfolio=portfolio,
            evidence_views={
                product_id: _fake_view(product_id, state="not_found")
                for product_id in article.product_ids
            },
            mode="production",
        )


def test_completion_gate_reports_all_unresolved_product_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    monkeypatch.setattr(
        portfolio_module,
        "product_evidence_views_v2",
        lambda *_args, **_kwargs: {
            product.product_id: _fake_view(product.product_id, state="expired")
            for product in portfolio.products
        },
    )

    readiness = product_evidence_readiness_v2(ROOT)

    assert readiness.complete is False
    assert readiness.product_count == len(portfolio.products) == 33
    assert readiness.product_card_count == 37
    assert readiness.affiliate_cta_count == 74
    assert readiness.verified_product_count == 0
    assert readiness.missing_registry_product_ids == (
        "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002",
        "PRD-ANKER-SOLIX-C800",
        "PRD-BERMAS-INTER-CITY-III-60570",
        "PRD-BLUETTI-AORA100-V2",
        "PRD-BLUETTI-AORA30-V2",
        "PRD-DJI-POWER-1000-V2",
        "PRD-ECOVACS-DEEBOT-MINI2",
        "PRD-EUFY-AUTOEMPTY-C10-T2292",
        "PRD-JACKERY-1000-NEW-V3",
        "PRD-PROTECA-TRI-AIR-01541",
        "PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
        "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549",
        "PRD-SIROCA-SS-M171",
        "PRD-THANKO-RAKUA-MINI-TK-MDW22W",
        "PRD-TOSHIBA-DWS-33B-W",
    )

    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_EXPIRED",
    ):
        product_evidence_views_v2(ROOT, require_verified_set=True)


def test_status_receipt_binds_each_product_to_its_own_evidence_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    products = tuple(
        ProductBindingV2(
            product_id=f"PRD-TEST-{number}",
            official_name=f"Test {number}",
            official_models=(f"MODEL-{number}",),
            representative_model=f"MODEL-{number}",
            official_jan=None,
            official_url=f"https://example.com/{number}",
            rakuten_shop_code="shop",
            rakuten_item_code=f"shop:1000000{number}",
            required_title_tokens=(f"MODEL-{number}",),
            product_kind_tokens=("test",),
            forbidden_title_tokens=("forbidden",),
        )
        for number in (1, 2)
    )
    portfolio = EditorialPortfolioV2(
        version="test",
        target_origin="https://example.com",
        theme_version="1.3.10",
        editorial_reviewed_on="2026-08-31",
        articles=(),
        products=products,
    )
    timestamps = {
        "PRD-TEST-1": "2026-08-29T10:00:00Z",
        "PRD-TEST-2": "2026-08-29T11:00:00Z",
    }
    evidences = {
        product.product_id: cast(
            RakutenProductEvidence,
            SimpleNamespace(
                product_id=product.product_id,
                retrieved_at=timestamps[product.product_id],
                item_code=product.rakuten_item_code,
                response_sha256="a" * 64,
                affiliate_response_sha256="b" * 64,
                image_sha256="c" * 64,
            ),
        )
        for product in products
    }
    receipt = {
        "schema": "RAOS_EDITORIAL_PORTFOLIO_PRODUCT_EVIDENCE_STATUS_V2",
        "captured_at": "2026-08-29T11:05:00Z",
        "portfolio_sha256": "d" * 64,
        "products": [
            {
                "product_id": product.product_id,
                "state": "verified",
                "retrieved_at": timestamps[product.product_id],
                "item_code": product.rakuten_item_code,
                "response_sha256": "a" * 64,
                "affiliate_response_sha256": "b" * 64,
                "image_sha256": "c" * 64,
            }
            for product in products
        ],
    }
    monkeypatch.setattr(
        portfolio_module, "load_editorial_portfolio_v2", lambda _: portfolio
    )
    monkeypatch.setattr(portfolio_module, "portfolio_sha256", lambda _: "d" * 64)
    monkeypatch.setattr(portfolio_module, "_load_status_receipt", lambda _: receipt)
    monkeypatch.setattr(
        portfolio_module,
        "read_rakuten_product_evidence",
        lambda _, *, product_id: evidences[product_id],
    )
    monkeypatch.setattr(
        portfolio_module,
        "_validate_rakuten_identity",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        portfolio_module,
        "_verified_product_image_extension",
        lambda *_args, **_kwargs: "jpg",
    )

    views = product_evidence_views_v2(
        ROOT,
        now=datetime(2026, 8, 29, 12, tzinfo=UTC),
        require_fresh_set=True,
    )

    assert {
        product_id: view.retrieved_at for product_id, view in views.items()
    } == timestamps


def test_stale_portfolio_receipt_is_safe_fallback_locally_and_closed_for_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = {
        "schema": "RAOS_EDITORIAL_PORTFOLIO_PRODUCT_EVIDENCE_STATUS_V2",
        "captured_at": "2026-08-29T11:05:00Z",
        "portfolio_sha256": "0" * 64,
        "products": [],
    }
    monkeypatch.setattr(portfolio_module, "_load_status_receipt", lambda _: receipt)

    local_views = product_evidence_views_v2(ROOT, require_fresh_set=False)
    assert set(local_views) == {
        product.product_id for product in load_editorial_portfolio_v2(ROOT).products
    }
    assert {view.state for view in local_views.values()} == {"expired"}

    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID",
    ):
        product_evidence_views_v2(ROOT, require_fresh_set=True)


def test_expired_verified_row_falls_back_without_loading_private_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = ProductBindingV2(
        product_id="PRD-TEST-EXPIRED",
        official_name="Expired Test",
        official_models=("MODEL-EXPIRED",),
        representative_model="MODEL-EXPIRED",
        official_jan=None,
        official_url="https://example.com/expired",
        rakuten_shop_code="shop",
        rakuten_item_code="shop:10000001",
        required_title_tokens=("MODEL-EXPIRED",),
        product_kind_tokens=("test",),
        forbidden_title_tokens=("forbidden",),
    )
    portfolio = EditorialPortfolioV2(
        version="test",
        target_origin="https://example.com",
        theme_version="1.3.10",
        editorial_reviewed_on="2026-08-31",
        articles=(),
        products=(product,),
    )
    receipt = {
        "schema": "RAOS_EDITORIAL_PORTFOLIO_PRODUCT_EVIDENCE_STATUS_V2",
        "captured_at": "2026-08-29T12:00:00Z",
        "portfolio_sha256": "d" * 64,
        "products": [
            {
                "product_id": product.product_id,
                "state": "verified",
                "retrieved_at": "2026-08-27T11:59:59Z",
                "item_code": product.rakuten_item_code,
                "response_sha256": "a" * 64,
                "affiliate_response_sha256": "b" * 64,
                "image_sha256": "c" * 64,
            }
        ],
    }
    monkeypatch.setattr(
        portfolio_module, "load_editorial_portfolio_v2", lambda _: portfolio
    )
    monkeypatch.setattr(portfolio_module, "portfolio_sha256", lambda _: "d" * 64)
    monkeypatch.setattr(portfolio_module, "_load_status_receipt", lambda _: receipt)

    def private_evidence_must_not_be_loaded(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("expired evidence must not be materialized")

    monkeypatch.setattr(
        portfolio_module,
        "read_rakuten_product_evidence",
        private_evidence_must_not_be_loaded,
    )
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)

    local = product_evidence_views_v2(ROOT, now=now, require_fresh_set=False)

    assert local[product.product_id].state == "expired"
    assert local[product.product_id].evidence is None
    with pytest.raises(
        EditorialPortfolioV2Failure,
        match="RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_EXPIRED",
    ):
        product_evidence_views_v2(ROOT, now=now, require_fresh_set=True)
