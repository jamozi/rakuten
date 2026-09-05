"""Materialized HTML must agree with the exact selected commerce evidence."""

from datetime import UTC, datetime

import pytest

from raos.application.editorial import verified_incremental_v1 as owner


def test_public_value_validators_preserve_exact_identity_and_utc() -> None:
    assert owner.validate_hash("a" * 64) == "a" * 64
    assert owner.validate_text("exact-value") == "exact-value"
    assert owner.parse_instant("2026-09-05T03:00:00Z") == datetime(
        2026, 9, 5, 3, tzinfo=UTC
    )
    for value in (None, "A" * 64, " " + "a" * 64, "a" * 63):
        with pytest.raises(owner.IncrementalPublicationFailure):
            owner.validate_hash(value)
    for value in (None, "", " surrounding "):
        with pytest.raises(owner.IncrementalPublicationFailure, match="TEXT_INVALID"):
            owner.validate_text(value)
    for value in (None, "2026-09-05", "2026-09-05T03:00:00+00:00"):
        with pytest.raises(owner.IncrementalPublicationFailure):
            owner.parse_instant(value)


def test_public_markup_projection_is_immutable_and_keeps_product_context() -> None:
    elements = owner.parse_markup_elements(
        '<article data-raos-product-id="PRD-FIRST"><p>条件</p><img src="/unverified.jpg"></article>'
    )
    assert tuple(element.tag for element in elements) == ("article", "p", "img")
    assert all(element.product == "PRD-FIRST" for element in elements)
    assert elements[-1].attrs == {"src": "/unverified.jpg"}
    assert elements[0].start == 0
    assert elements[0].opening_end < elements[1].end < elements[0].end
    assert elements[-1].opening_end == elements[-1].end
    with pytest.raises(TypeError):
        elements[-1].attrs["src"] = "/changed.jpg"
    # Syntax parsing must not imply that this unverified image can be published.
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="HTML_IMAGE_UNVERIFIED"
    ):
        owner.verify_commerce_markup(
            '<article class="product-profile" data-raos-product-id="PRD-FIRST"><img src="/unverified.jpg"></article>',
            article_id="article-first",
            editorial_product_ids=frozenset({"PRD-FIRST"}),
            expected_ctas={},
            expected_images={},
        )


@pytest.mark.parametrize(
    "markup",
    [
        "<div>",
        "<div></span>",
        '<div id="first" id="second"></div>',
        "<script></script>",
        "<iframe></iframe>",
    ],
)
def test_public_markup_projection_keeps_strict_parser_rejection(markup: str) -> None:
    with pytest.raises(owner.IncrementalPublicationFailure, match="MARKUP_INVALID"):
        owner.parse_markup_elements(markup)


def test_commerce_omission_preserves_noncommercial_article_identity() -> None:
    markup = '<div class="raos-editorial-v2"><dl class="raos-article-facts"><dt>実機</dt><dd>未使用</dd></dl><article class="product-profile" data-raos-product-id="PRD-FIRST"><h3>正式型番</h3><div class="raos-product-card__actions"><p>購入先未確認</p><a href="https://example.com" data-raos-article-id="article-1" data-raos-product-id="PRD-FIRST" data-raos-placement="product_card">購入</a></div></article><p class="summary-action"><a href="https://example.com" data-raos-article-id="article-1" data-raos-product-id="PRD-FIRST" data-raos-placement="final_summary">購入</a></p></div>'
    result = owner.omit_unverified_commerce(
        markup,
        image_product_ids=frozenset(),
        cta_product_ids=frozenset(),
        article_id="article-1",
    )
    assert result.startswith('<div class="raos-editorial-v2">')
    assert '<dl class="raos-article-facts" data-raos-article-id="article-1">' in result
    assert "正式型番" in result
    assert "購入" not in result
    assert "summary-action" not in result
    assert "raos-product-card__actions" not in result
    with pytest.raises(owner.IncrementalPublicationFailure, match="ARTICLE_ID_INVALID"):
        owner.omit_unverified_commerce(
            markup,
            image_product_ids=frozenset(),
            cta_product_ids=frozenset(),
            article_id="different-article",
        )


def test_unquoted_purchase_fragment_is_retargeted_after_omission() -> None:
    markup = "<div><a href=#purchase>詳細</a><article id=model data-raos-product-id=PRD-FIRST><div id=purchase data-raos-purchase-action>購入</div></article></div>"
    result = owner.omit_unverified_commerce(
        markup, image_product_ids=frozenset(), cta_product_ids=frozenset()
    )
    assert 'href="#model"' in result
    assert "#purchase" not in result


def test_final_html_matches_exact_commerce_placements_with_same_url_reuse() -> None:
    url = "https://hb.afl.rakuten.co.jp/hgc/recorded/"
    markup = f'''<article class="product-profile" data-raos-product-id="PRD-FIRST"><p>条件と妥協点</p><a data-raos-article-id="article-1" data-raos-product-id="PRD-FIRST" data-raos-placement="product_card" data-raos-cta-id="icta_a01_p01_card" href="{url}" rel="sponsored nofollow">購入</a><a data-raos-article-id="article-1" data-raos-product-id="PRD-FIRST" data-raos-placement="final_summary" data-raos-cta-id="icta_a01_p01_final" href="{url}" rel="sponsored nofollow">購入</a></article>'''
    expected = {
        "icta_a01_p01_card": ("PRD-FIRST", "product_card", url),
        "icta_a01_p01_final": ("PRD-FIRST", "final_summary", url),
    }

    def verify(raw: str) -> None:
        owner.verify_commerce_markup(
            raw,
            article_id="article-1",
            editorial_product_ids=frozenset({"PRD-FIRST"}),
            expected_ctas=expected,
            expected_images={},
        )

    verify(markup)
    for modified in (
        markup.replace(url, "https://hb.afl.rakuten.co.jp/hgc/invented/", 1),
        markup.replace('rel="sponsored nofollow"', 'rel="nofollow"', 1),
        markup.replace("icta_a01_p01_card", "icta_a02_p01_card", 1),
        markup.replace("article-1", "article-2", 1),
        markup + f'<a href="{url}">Undeclared affiliate</a>',
    ):
        with pytest.raises(owner.IncrementalPublicationFailure):
            verify(modified)


def test_final_html_allows_no_commerce_but_not_neutral_image() -> None:
    markup = '<article class="product-profile" data-raos-product-id="PRD-FIRST"><p>比較対象として残す</p></article>'

    def verify(raw: str) -> None:
        owner.verify_commerce_markup(
            raw,
            article_id="article-1",
            editorial_product_ids=frozenset({"PRD-FIRST"}),
            expected_ctas={},
            expected_images={},
        )

    verify(markup)
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="HTML_IMAGE_UNVERIFIED"
    ):
        verify(markup.replace("</article>", '<img src="/unverified.jpg"></article>'))
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="HTML_IMAGE_UNVERIFIED"
    ):
        verify(
            markup
            + '<img data-raos-product-image-id="PRD-FIRST" data-raos-product-image-state="neutral" src="/generic.webp">'
        )


def test_final_verified_image_checks_size_alt_loading_and_source() -> None:
    markup = '<article class="product-profile" data-raos-product-id="PRD-FIRST"><img src="/matched.jpg" data-raos-product-image-id="PRD-FIRST" data-raos-product-image-state="verified" width="128" height="128" alt="照合済み商品の正面" loading="lazy"></article>'

    def verify(raw: str) -> None:
        owner.verify_commerce_markup(
            raw,
            article_id="article-1",
            editorial_product_ids=frozenset({"PRD-FIRST"}),
            expected_ctas={},
            expected_images={"PRD-FIRST": "/matched.jpg"},
        )

    verify(markup)
    for modified in (
        markup.replace("/matched.jpg", "/unrelated.jpg"),
        markup.replace('width="128"', 'width="0"'),
        markup.replace('loading="lazy"', ""),
        markup.replace("照合済み商品の正面", ""),
        markup.replace("<img ", '<img srcset="/unverified.jpg 2x" '),
        markup.replace(
            "<img ", '<picture><source srcset="/unverified.jpg"><img '
        ).replace("</article>", "</picture></article>"),
    ):
        with pytest.raises(
            owner.IncrementalPublicationFailure, match="HTML_IMAGE_UNVERIFIED"
        ):
            verify(modified)


@pytest.mark.parametrize("nested_spoof", [False, True])
def test_verified_images_cannot_be_swapped_between_product_cards(
    nested_spoof: bool,
) -> None:
    def card(card_product: str, image_product: str) -> str:
        opening = (
            f'<div data-raos-product-id="{image_product}">' if nested_spoof else "<div>"
        )
        return (
            f'<article class="product-profile" data-raos-product-id="{card_product}">'
            f'{opening}<img src="/{image_product}.jpg" '
            f'data-raos-product-id="{image_product}" '
            f'data-raos-product-image-id="{image_product}" '
            'data-raos-product-image-state="verified" width="128" height="128" '
            'alt="照合済み商品" loading="lazy"></div></article>'
        )

    def verify(markup: str) -> None:
        owner.verify_commerce_markup(
            markup,
            article_id="article-1",
            editorial_product_ids=frozenset({"PRD-FIRST", "PRD-SECOND"}),
            expected_ctas={},
            expected_images={
                "PRD-FIRST": "/PRD-FIRST.jpg",
                "PRD-SECOND": "/PRD-SECOND.jpg",
            },
        )

    verify(card("PRD-FIRST", "PRD-FIRST") + card("PRD-SECOND", "PRD-SECOND"))
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="HTML_IMAGE_UNVERIFIED"
    ):
        verify(card("PRD-FIRST", "PRD-SECOND") + card("PRD-SECOND", "PRD-FIRST"))


@pytest.mark.parametrize("placement", ["product_card", "final_summary"])
def test_cta_product_must_match_its_ancestor_card(placement: str) -> None:
    url = "https://hb.afl.rakuten.co.jp/hgc/recorded/"
    link = (
        '<a data-raos-article-id="article-1" data-raos-product-id="PRD-SECOND" '
        f'data-raos-placement="{placement}" data-raos-cta-id="cta-1" '
        f'href="{url}" rel="sponsored nofollow">購入</a>'
    )
    first = '<article class="product-profile" data-raos-product-id="PRD-FIRST">'
    second = '<article class="product-profile" data-raos-product-id="PRD-SECOND">'

    def verify(markup: str) -> None:
        owner.verify_commerce_markup(
            markup,
            article_id="article-1",
            editorial_product_ids=frozenset({"PRD-FIRST", "PRD-SECOND"}),
            expected_ctas={"cta-1": ("PRD-SECOND", placement, url)},
            expected_images={},
        )

    verify(first + "</article>" + second + link + "</article>")
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="HTML_CTA_UNVERIFIED"
    ):
        verify(
            first
            + '<div data-raos-product-id="PRD-SECOND">'
            + link
            + "</div></article>"
            + second
            + "</article>"
        )
    outside = first + "</article>" + second + "</article>" + link
    if placement == "final_summary":
        verify(outside)
    else:
        with pytest.raises(
            owner.IncrementalPublicationFailure, match="HTML_CTA_UNVERIFIED"
        ):
            verify(outside)


@pytest.mark.parametrize(
    "link",
    [
        '<a href="https://item.rakuten.co.jp/recorded/item/">購入する</a>',
        '<a href="https://search.rakuten.co.jp/search/mall/model/">購入先</a>',
        '<a href="https://hb.afl.rakuten.co.jp/hgc/recorded/">商品</a>',
        '<a data-raos-cta-id="undeclared" href="https://example.com/">購入する</a>',
        '<a data-raos-purchase-action href="https://example.com/">購入する</a>',
        '<div class="product-purchase-action"><a href="https://example.com/">メーカーで購入</a></div>',
    ],
)
def test_undeclared_purchase_links_cannot_count_as_zero_commerce(link: str) -> None:
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="HTML_CTA_UNVERIFIED"
    ):
        owner.verify_commerce_markup(
            "<p>公式情報の確認案内</p>" + link,
            article_id="article-1",
            editorial_product_ids=frozenset(),
            expected_ctas={},
            expected_images={},
        )


def test_unmarked_body_photo_cannot_be_published_as_zero_verified_images() -> None:
    with pytest.raises(
        owner.IncrementalPublicationFailure, match="HTML_IMAGE_UNVERIFIED"
    ):
        owner.verify_commerce_markup(
            '<figure><img src="/unverified-photo.jpg" alt="商品例"></figure>',
            article_id="article-1",
            editorial_product_ids=frozenset(),
            expected_ctas={},
            expected_images={},
        )
