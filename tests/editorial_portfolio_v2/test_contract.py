from __future__ import annotations

from datetime import UTC, datetime
from html import unescape
import json
from pathlib import Path
import re
from types import SimpleNamespace
from typing import cast, Literal
from urllib.parse import urlencode

import pytest

from raos.application.editorial import editorial_portfolio_v2 as portfolio_module
from raos.application.editorial.editorial_portfolio_v2 import (
    EditorialPortfolioV2,
    EditorialPortfolioV2Failure,
    ProductBindingV2,
    ProductEvidenceViewV2,
    _validate_rakuten_identity,
    load_editorial_portfolio_v2,
    materialize_article_v2,
    product_evidence_views_v2,
)
from raos.domain.editorial.self_hosted_editorial_pilot import RakutenProductEvidence
from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailure,
    EditorialPilotFailureCode,
)
from raos.adapters import self_hosted_editorial_rakuten_capture as capture_module
from scripts import raos_editorial_portfolio_v2 as portfolio_script


ROOT = Path(__file__).resolve().parents[2]
ARTICLE_ROOT = ROOT / "changes/wordpress-local-preview-v1/fixtures/articles"
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
    "構成です",
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
    )


def _visible_text(markup: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", markup))


FORMAL_PRODUCT_PREFIX_OVERRIDES = {
    "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY": (
        "iRobot「Roomba Mini 掃除機＆床拭きロボット + "
        "AutoEmpty 充電ステーション」（型番：F155260",
        "Roomba Mini 掃除機＆床拭きロボット + AutoEmpty 充電ステーション",
    ),
    "PRD-IROBOT-ROOMBA-PLUS-515-COMBO": (
        "iRobot「Roomba Plus 515 Combo ロボット + "
        "AutoWash 充電ステーション」（型番：N285060",
        "Roomba Plus 515 Combo ロボット + AutoWash 充電ステーション",
    ),
    "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060": (
        "iRobot「Roomba Mini Slim 掃除機＆床拭きロボット + "
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


def test_portfolio_closes_ten_articles_thirty_two_products_and_thirty_seven_cards() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    tracked = json.loads(
        (ROOT / portfolio_module.PORTFOLIO_RELATIVE_PATH).read_text(encoding="utf-8")
    )

    assert portfolio.version == "2.0.0"
    assert tracked["evidence_policy"]["identity_validation"]["jan"] == (
        "required_exact_when_official_jan_registered"
    )
    assert portfolio.theme_version == "1.3.10"
    assert portfolio.theme_runtime_revision == (
        "c719a3b0994fe9b80fd2edc9a758e6ac4b23e4604824495aa54ffb62f6010ac9"
    )
    assert len(portfolio.articles) == 10
    assert len(portfolio.products) == 32
    assert sum(len(article.product_ids) for article in portfolio.articles) == 37
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
            "PRD-THANKO-RAKUA-MINI-PLUS-TK-MDW22B",
        }
    } == {
        "PRD-ANKER-SOLIX-C300": "A17225Z1",
        "PRD-ANKER-SOLIX-C800-PLUS": "A1754",
        "PRD-ANKER-SOLIX-C1000": "A17615Z1",
        "PRD-ANKER-SOLIX-C1000-GEN2": "A17635Z1",
        "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060": "F115060",
        "PRD-THANKO-RAKUA-MINI-PLUS-TK-MDW22B": "TK-MDW22B",
    }


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
    affiliate_pc_tail = (
        source_tail if affiliate_pc_item is None else affiliate_pc_item
    )
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


def test_provider_identity_requires_title_model_official_jan_and_exact_direct_item() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    binding = portfolio.product_by_id["PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY"]

    _validate_rakuten_identity(binding, _provider_identity_evidence(binding))
    _validate_rakuten_identity(
        binding,
        _provider_identity_evidence(binding, source_item="provider-custom-slug"),
    )

    title_without_model = (
        "Roomba Mini AutoEmpty ロボット掃除機"
    )
    for evidence in (
        _provider_identity_evidence(binding, item_name=title_without_model),
        _provider_identity_evidence(binding, jan=None),
        _provider_identity_evidence(binding, jan="0885155054982"),
        _provider_identity_evidence(binding, affiliate_pc_item="different-item"),
    ):
        with pytest.raises(
            EditorialPortfolioV2Failure,
            match="RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID",
        ):
            _validate_rakuten_identity(binding, evidence)


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
        theme_runtime_revision="a" * 64,
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
    monkeypatch.setattr(portfolio_script, "product_evidence_views_v2", lambda *_a, **_k: {})
    monkeypatch.setattr(portfolio_script, "read_rakuten_product_evidence", no_existing)
    monkeypatch.setattr(capture_module, "require_clean_capture_environment", lambda: None)
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
    assert portfolio_script._is_product_listing_fallback(
        capture_module.RakutenProductCaptureFailure(code)
    ) is False


def test_fixed_listing_fallback_rejects_credential_reflection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = load_editorial_portfolio_v2(ROOT).product_by_id[
        "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY"
    ]
    assert binding.rakuten_item_code is not None
    shop, item = binding.rakuten_item_code.split(":", 1)
    raw = json.dumps(
        {
            "Items": [
                {
                    "itemCode": binding.rakuten_item_code,
                    "itemName": "Roomba F155260 test-access-key ロボット掃除機",
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


def test_each_product_is_formally_introduced_before_its_first_shortened_reference() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    audited_product_ids: set[str] = set()
    audited_article_cards = 0

    for article in portfolio.articles:
        markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
            encoding="utf-8"
        )
        first_bound_product = markup.find("data-raos-product-id=")
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
        assert markup.count(STANDARD_AD_DISCLOSURE) == 1
        assert markup.count(STANDARD_AD_DETAILS) == 1
        assert FIXED_HEADING_BREAK.search(markup) is None
        assert not any(term in markup for term in READER_FACING_PROHIBITED)
        assert "幅×奥行×高さ" in markup
        assert len(set(re.findall(r"(?<=\d)(?:cm|mm)", markup))) == 1
        assert re.search(
            r"(?:^|[^A-Za-z])(?:W|D|H)\s*\d+(?:\.\d+)?\s*(?:cm|mm)",
            markup,
        ) is None
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
            placements = sorted(
                _attributes(tag)["data-raos-placement"] for tag in tags
            )
            assert placements == ["final_summary", "product_card"]
            assert len(
                re.findall(
                    r"<article\b(?=[^>]*\bdata-raos-product-id=[\"']"
                    + re.escape(product_id)
                    + r"[\"'])[^>]*>",
                    markup,
                    flags=re.IGNORECASE,
                )
            ) == 1


def test_materialization_uses_exact_two_affiliate_ctas_or_official_fallback() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    products = portfolio.product_by_id
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
            if product_id in fallback_ids:
                assert {item["href"] for item in attributes} == {
                    products[product_id].official_url
                }
                assert all(
                    "official-product-link" in item["class"] for item in attributes
                )
                assert not any(
                    "rakuten-cta" in item["class"] for item in attributes
                )
                assert re.search(
                    rf'<img\b(?=[^>]*data-raos-product-image-id="{re.escape(product_id)}")'
                    r'(?=[^>]*data-raos-product-image-state="neutral")[^>]*>',
                    rendered,
                )
                assert "商品写真ではありません" in rendered
                assert "一致する楽天商品を確認できなかったため" in rendered
            else:
                assert len({item["href"] for item in attributes}) == 1
                assert all(
                    item["rel"] == "sponsored nofollow" for item in attributes
                )
                assert all("rakuten-cta" in item["class"] for item in attributes)
                assert re.search(
                    rf'<img\b(?=[^>]*data-raos-product-image-id="{re.escape(product_id)}")'
                    r'(?=[^>]*data-raos-product-image-state="verified")[^>]*>',
                    rendered,
                )
                assert f'src="/raos-product-media/{product_id}.image"' in rendered
                assert "販売元、価格、在庫、商品画像を確認できます" in rendered
            if article.production_slug == "front-open-carry-on-suitcase-with-stopper":
                card = re.search(
                    r"<article\b(?=[^>]*\bdata-raos-product-id=[\"']"
                    + re.escape(product_id)
                    + r"[\"'])[^>]*>.*?</article>",
                    rendered,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                assert card is not None
                if product_id in fallback_ids:
                    assert (
                        "<figcaption>比較検討用の中立イメージ"
                        "（商品写真ではありません）</figcaption>"
                    ) in card.group(0)
                else:
                    assert (
                        f"<figcaption>{products[product_id].official_name}の商品画像"
                        "（楽天市場の商品情報より）</figcaption>"
                    ) in card.group(0)
        assert (
            re.search(r"\bsrc=([\"'])https://", rendered, flags=re.IGNORECASE)
            is None
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
            assert {item["href"] for item in attributes} == {product.official_url}
            assert all(
                item.get("rel") == "noopener noreferrer" for item in attributes
            )
            assert all(
                "sponsored" not in item.get("rel", "").split()
                for item in attributes
            )
            assert all(
                "official-product-link" in item["class"] for item in attributes
            )
            assert not any("rakuten-cta" in item["class"] for item in attributes)

            card = re.search(
                r"<article\b(?=[^>]*\bdata-raos-product-id=[\"']"
                + re.escape(product_id)
                + r"[\"'])[^>]*>.*?</article>",
                rendered,
                flags=re.IGNORECASE | re.DOTALL,
            )
            assert card is not None
            assert re.search(
                rf'<img\b(?=[^>]*data-raos-product-image-id="{re.escape(product_id)}")'
                r'(?=[^>]*data-raos-product-image-state="neutral")[^>]*>',
                card.group(0),
            )
            assert "商品写真ではありません" in card.group(0)
            assert "一致する楽天商品を確認できなかったため" in card.group(0)
            assert f"/raos-product-media/{product_id}.image" not in card.group(0)


def test_production_materialization_uses_provider_image_and_rejects_heading_break() -> None:
    portfolio = load_editorial_portfolio_v2(ROOT)
    article = portfolio.article_by_production_slug["roomba-mini-vs-switchbot-k11-pro"]
    markup = (ARTICLE_ROOT / f"{article.production_slug}.html").read_text(
        encoding="utf-8"
    )
    views = {product_id: _fake_view(product_id, state="verified") for product_id in article.product_ids}

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
        theme_runtime_revision="a" * 64,
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
    monkeypatch.setattr(portfolio_module, "load_editorial_portfolio_v2", lambda _: portfolio)
    monkeypatch.setattr(portfolio_module, "portfolio_sha256", lambda _: "d" * 64)
    monkeypatch.setattr(portfolio_module, "_load_status_receipt", lambda _: receipt)
    monkeypatch.setattr(
        portfolio_module,
        "read_rakuten_product_evidence",
        lambda _, *, product_id: evidences[product_id],
    )
    monkeypatch.setattr(portfolio_module, "_validate_rakuten_identity", lambda *_: None)

    views = product_evidence_views_v2(
        ROOT,
        now=datetime(2026, 8, 29, 12, tzinfo=UTC),
        require_fresh_set=True,
    )

    assert {product_id: view.retrieved_at for product_id, view in views.items()} == timestamps


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
        theme_runtime_revision="a" * 64,
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
    monkeypatch.setattr(portfolio_module, "load_editorial_portfolio_v2", lambda _: portfolio)
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
