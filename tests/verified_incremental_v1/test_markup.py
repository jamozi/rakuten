"""Materialized HTML must agree with the exact selected commerce evidence."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from raos.application.editorial import verified_incremental_v1 as owner


NON_HTML_WHITESPACE = (
    "\v",
    "\x1c",
    "\x85",
    "\xa0",
    "\u1680",
    "\u2000",
    "\u2003",
    "\u2007",
    "\u2009",
    "\u2028",
    "\u2029",
    "\u202f",
    "\u205f",
    "\u3000",
)
ASCII_TOKEN_SEPARATORS = (
    " ",
    "\t",
    "\n",
    "\f",
    "\r",
    " \t\n\f\r ",
    "&#32;",
    "&#9;",
    "&#10;",
    "&#12;",
    "&#13;",
    "&Tab;",
    "&NewLine;",
)


@pytest.mark.parametrize("separator", NON_HTML_WHITESPACE)
def test_html_attribute_token_helper_never_splits_unicode_whitespace(
    separator: str,
) -> None:
    assert owner.html_attribute_tokens("first" + separator + "second") == {
        "first" + separator + "second"
    }
    assert owner.html_attribute_tokens(separator + "first" + separator) == {
        separator + "first" + separator
    }
    assert owner.html_attribute_tokens(" \tfirst\nsecond\ffirst\r ") == {
        "first",
        "second",
    }
    assert owner.html_attribute_tokens(None) == frozenset()
    assert owner.html_attribute_tokens(" \t\n\r\f") == frozenset()


@pytest.mark.parametrize("attribute", ["class", "rel"])
@pytest.mark.parametrize(
    "separator",
    (
        *NON_HTML_WHITESPACE,
        "&nbsp;",
        "&#160;",
        "&#xA0;",
        "&#11;",
        "&ThinSpace;",
        "&#x3000;",
    ),
)
def test_non_html_class_and_rel_separators_cannot_verify_commerce(
    attribute: str,
    separator: str,
) -> None:
    url = "https://hb.afl.rakuten.co.jp/hgc/recorded/"
    classes = "product-profile" + (separator if attribute == "class" else " ") + "promo"
    rel = "sponsored" + (separator if attribute == "rel" else " ") + "nofollow"
    markup = (
        f'<article class="{classes}" data-raos-product-id="A">'
        f'<a href="{url}" rel="{rel}" data-raos-product-id="A" '
        'data-raos-article-id="article-1" data-raos-placement="product_card" '
        'data-raos-cta-id="cta-1">購入</a></article>'
    )
    with pytest.raises(owner.IncrementalPublicationFailure, match="MARKUP_INVALID"):
        owner.verify_commerce_markup(
            markup,
            article_id="article-1",
            editorial_product_ids=frozenset({"A"}),
            expected_ctas={"cta-1": ("A", "product_card", url)},
            expected_images={},
        )
    with pytest.raises(owner.IncrementalPublicationFailure, match="MARKUP_INVALID"):
        owner.omit_unverified_commerce(
            markup,
            image_product_ids=frozenset(),
            cta_product_ids=frozenset(),
        )


@pytest.mark.parametrize("separator", ASCII_TOKEN_SEPARATORS)
def test_html_ascii_token_separators_preserve_commerce_and_facts(
    separator: str,
) -> None:
    url = "https://hb.afl.rakuten.co.jp/hgc/recorded/"
    markup = (
        f'<dl class="{separator}raos-article-facts{separator}補足{separator}">'
        "<dt>比較</dt><dd>条件\xa0の確認</dd></dl>"
        f'<article class="{separator}product-profile{separator}比較カード{separator}" data-raos-product-id="A">'
        f'<a href="{url}" rel="{separator}sponsored{separator}nofollow{separator}" '
        'data-raos-product-id="A" data-raos-article-id="article-1" '
        'data-raos-placement="product_card" data-raos-cta-id="cta-1">購入</a></article>'
    )
    owner.verify_commerce_markup(
        markup,
        article_id="article-1",
        editorial_product_ids=frozenset({"A"}),
        expected_ctas={"cta-1": ("A", "product_card", url)},
        expected_images={},
    )
    omitted = owner.omit_unverified_commerce(
        markup,
        image_product_ids=frozenset(),
        cta_product_ids=frozenset(),
        article_id="article-1",
    )
    assert "購入" not in omitted
    assert "条件\xa0の確認" in omitted
    assert 'data-raos-article-id="article-1"' in omitted


@pytest.mark.parametrize(
    "markup",
    [
        '<table background="https://other.invalid/p.png"><tr><td>条件</td></tr></table>',
        '<table><tr><td BACKGROUND="https://other.invalid/p.png">条件</td></tr></table>',
        '<div style="background-image:url(https://other.invalid/p.png)">条件</div>',
        '<span style="content:url(https://other.invalid/p.png)">条件</span>',
        r'<span style="content:\75rl(https://other.invalid/p.png)">条件</span>',
        '<div style="">条件</div>',
        '<a href="https://example.com" ping="https://other.invalid/track">購入</a>',
        '<a href="https://example.com" ping="">購入</a>',
        '<img src="/matched.jpg" lowsrc="https://other.invalid/p.png">',
        '<img src="/matched.jpg" dynsrc="https://other.invalid/p.png">',
        '<div data="https://other.invalid/p.png"></div>',
        '<div src="https://other.invalid/p.png"></div>',
    ],
)
def test_article_resource_attributes_require_a_closed_evidence_surface(
    markup: str,
) -> None:
    with pytest.raises(owner.IncrementalPublicationFailure, match="MARKUP_INVALID"):
        owner.parse_markup_elements(markup)
    with pytest.raises(owner.IncrementalPublicationFailure, match="MARKUP_INVALID"):
        owner.verify_commerce_markup(
            markup,
            article_id="article-1",
            editorial_product_ids=frozenset(),
            expected_ctas={},
            expected_images={},
        )


@pytest.mark.parametrize(
    "markup",
    [
        "<table><article><tr><td>商品</td></tr></article></table>",
        "<table><tbody><article><tr><td>商品</td></tr></article></tbody></table>",
        "<table><tr><article><td>商品</td></article></tr></table>",
        "<table><tr><td><article><td>商品</td></article></td></tr></table>",
        "<table><tr><div>商品</div></tr></table>",
        "<table><td>商品</td></table>",
        "<div><td>商品</td></div>",
        "<table><colgroup><div>商品</div></colgroup></table>",
        "<table>商品<tr><td>条件</td></tr></table>",
        "<table>&nbsp;<tr><td>条件</td></tr></table>",
        "<table>&#160;<tr><td>条件</td></tr></table>",
        "<table><tbody>&#x41;<tr><td>条件</td></tr></tbody></table>",
        "<table><caption><div><table><tr><td>商品</td></tr></table></div></caption></table>",
        "<article/><article>商品</article>",
        "<p/>商品",
        "<div/>商品",
        '<a href="#a"><span><a href="#b">商品</a></span></a>',
        "<p><span><p>商品</p></span></p>",
        "<p><article>商品</article></p>",
        "<p><span><table><tr><td>商品</td></tr></table></span></p>",
        "<h2><span><h3>商品</h3></span></h2>",
        "<ul><li><article><li>商品</li></article></li></ul>",
        "<dl><dd><div><dt>商品</dt></div></dd></dl>",
        "<ruby><rt><rp>商品</rp></rt></ruby>",
    ],
)
def test_browser_implicit_closure_and_table_fostering_are_rejected(markup: str) -> None:
    with pytest.raises(owner.IncrementalPublicationFailure, match="MARKUP_INVALID"):
        owner.parse_markup_elements(markup)


def test_verified_card_cannot_be_fostered_outside_its_images_or_cta() -> None:
    url = "https://hb.afl.rakuten.co.jp/hgc/recorded/"
    contents = (
        '<img src="/matched.jpg" data-raos-product-image-id="A" '
        'data-raos-product-image-state="verified" width="128" height="128" alt="A" loading="lazy">'
        '<a data-raos-product-id="A" data-raos-article-id="article-1" '
        'data-raos-placement="product_card" data-raos-cta-id="cta-1" '
        f'href="{url}" rel="sponsored nofollow">A購入</a>'
    )
    opening = '<article class="product-profile" data-raos-product-id="A">'
    kwargs = {
        "article_id": "article-1",
        "editorial_product_ids": frozenset({"A"}),
        "expected_images": {"A": "/matched.jpg"},
        "expected_ctas": {"cta-1": ("A", "product_card", url)},
    }
    valid = "<table><tr><td>" + opening + contents + "</article></td></tr></table>"
    owner.verify_commerce_markup(valid, **kwargs)
    for invalid in (
        "<table>" + opening + "<tr><td>" + contents + "</td></tr></article></table>",
        "<table><tr><td>"
        + opening
        + "<td>"
        + contents
        + "</td></article></td></tr></table>",
        opening[:-1] + "/><table><tr><td>" + contents + "</td></tr></table>",
    ):
        with pytest.raises(owner.IncrementalPublicationFailure):
            owner.verify_commerce_markup(invalid, **kwargs)


def test_normal_explicit_wordpress_tables_lists_and_ruby_remain_supported() -> None:
    markup = (
        "<!-- wp:html --><section><table>\n<caption>条件</caption>"
        '<colgroup><col span="2"/></colgroup><thead><tr><th scope="col">型番</th>'
        '<th scope="col">用途</th></tr></thead><tbody>\n<tr><td colspan="2">'
        "<article><p>用途に合うか確認する。<br/>注意点も読む。</p></article>"
        "</td></tr></tbody><tfoot><tr><td>補足</td><td>条件付き</td></tr></tfoot></table>"
        "<table>&#32;<tr><td>tbody省略</td></tr></table>"
        '<ul><li><p>条件</p><ol start="2"><li>次の条件</li></ol></li></ul>'
        "<dl><div><dt>確認</dt><dd><dl><dt>型番</dt><dd>表記を照合</dd></dl></dd></div></dl>"
        "<p><ruby>比較<rp>（</rp><rt>ひかく</rt><rp>）</rp></ruby></p></section><!-- /wp:html -->"
    )
    assert owner.parse_markup_elements(markup)


def test_all_current_authored_articles_and_production_policies_use_supported_grammar() -> (
    None
):
    fixtures = (
        Path(__file__).resolve().parents[2]
        / "changes/wordpress-local-preview-v1/fixtures"
    )
    paths = sorted((fixtures / "articles").glob("*.html")) + sorted(
        (fixtures / "production-pages").glob("*.html")
    )
    assert len(paths) == 13
    for path in paths:
        assert owner.parse_markup_elements(path.read_text(encoding="utf-8")), path.name


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
        '<a href="https://example.invalid" onclick="this.href=\'https://other.invalid\'">購入</a>',
        '<div onpointerover="redirect()"></div>',
        '<a href="java&#x09;script:redirect()">購入</a>',
        '<embed src="https://example.invalid">',
        '<div srcdoc="untrusted"></div>',
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
        markup.replace("<a ", "<a onclick=\"this.href='https://other.invalid'\" ", 1),
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


@pytest.mark.parametrize(
    "foreign_markup",
    [
        '<svg><image href="https://other.invalid/p.png" width="128" height="128"/></svg>',
        '<SVG><IMAGE HREF="https://other.invalid/p.png"/></SVG>',
        '<svg:svg><svg:image href="https://other.invalid/p.png"/></svg:svg>',
        '<s:svg xmlns:s="http://www.w3.org/2000/svg"><s:image href="/p.png"/></s:svg>',
        '<image href="https://other.invalid/p.png"/>',
        '<svg><foreignObject><a href="https://other.invalid/">別の購入先</a></foreignObject></svg>',
        '<foreignObject><img src="https://other.invalid/p.png"></foreignObject>',
        '<svg><set href="#verified-cta" attributeName="href" to="https://other.invalid/" begin="0s"/></svg>',
        '<set href="#verified-cta" attributeName="href" to="https://other.invalid/"/>',
        '<animate href="#verified-cta" attributeName="href" values="https://other.invalid/"/>',
        '<math><mtext><img src="https://other.invalid/p.png"></mtext></math>',
        '<MATH><annotation-xml encoding="text/html"><a href="https://other.invalid/">別商品</a></annotation-xml></MATH>',
        "<math:math><math:mi>比較</math:mi></math:math>",
        '<div xmlns="http://www.w3.org/2000/svg"></div>',
        '<div XMLNS:x="http://www.w3.org/1999/xlink"></div>',
        '<a xlink:href="https://other.invalid/">別の購入先</a>',
        '<a xml:base="https://other.invalid/" href="/product">別の購入先</a>',
        '<a is="unverified-link" href="#verified-cta">比較</a>',
        '<unverified-image src="https://other.invalid/p.png"></unverified-image>',
        '<template><img src="https://other.invalid/p.png"></template>',
        '<noscript><img src="https://other.invalid/p.png"></noscript>',
        "<canvas>未照合の描画領域</canvas>",
        '<video poster="https://other.invalid/p.png"></video>',
        '<audio src="https://other.invalid/p.mp3"></audio>',
        '<?xml-stylesheet href="https://other.invalid/style.xsl"?>',
        "<!DOCTYPE svg>",
        '<![CDATA[<svg><image href="https://other.invalid/p.png"/></svg>]]>',
        '<!--><svg><image href="/unverified.png"/></svg>-->',
        '<!---><svg><image href="/unverified.png"/></svg>-->',
        '<!-- safe --!><svg><image href="/unverified.png"/></svg>-->',
        '<!-- loose -- ><svg><image href="/unverified.png"/></svg>-->',
        '<![CDATA[><svg><image href="/unverified.png"/></svg>',
        "<!-- unclosed",
        "<svg",
        "<?xml",
    ],
)
def test_foreign_grammar_cannot_hide_beside_valid_product_image_and_cta(
    foreign_markup: str,
) -> None:
    url = "https://hb.afl.rakuten.co.jp/hgc/recorded/"
    valid = (
        '<article class="product-profile" data-raos-product-id="PRD-FIRST">'
        '<img src="/matched.jpg" data-raos-product-image-id="PRD-FIRST" '
        'data-raos-product-image-state="verified" width="128" height="128" '
        'alt="正しい商品" loading="lazy">'
        '<a id="verified-cta" data-raos-article-id="article-1" '
        'data-raos-product-id="PRD-FIRST" data-raos-placement="product_card" '
        f'data-raos-cta-id="cta-1" href="{url}" rel="sponsored nofollow">購入</a>'
        "</article>"
    )

    def verify(markup: str) -> None:
        owner.verify_commerce_markup(
            markup,
            article_id="article-1",
            editorial_product_ids=frozenset({"PRD-FIRST"}),
            expected_ctas={"cta-1": ("PRD-FIRST", "product_card", url)},
            expected_images={"PRD-FIRST": "/matched.jpg"},
        )

    verify(valid)
    with pytest.raises(owner.IncrementalPublicationFailure, match="MARKUP_INVALID"):
        verify(valid + foreign_markup)
    with pytest.raises(owner.IncrementalPublicationFailure, match="MARKUP_INVALID"):
        owner.parse_markup_elements(foreign_markup)


def test_nonimage_html_comparison_diagram_and_block_comments_remain_supported() -> None:
    markup = (
        "<!-- wp:html --><section><h2>設置場所から比較する</h2>"
        '<figure role="group" aria-label="設置条件の比較図">'
        '<div class="comparison-visual"><span>置き場所</span><strong>幅を確認</strong></div>'
        "<figcaption>商品写真ではないHTMLの比較図です。</figcaption></figure>"
        '<table><caption>設置条件</caption><thead><tr><th scope="col">項目</th>'
        '<th scope="col">確認点</th></tr></thead><tbody><tr><th scope="row">幅</th>'
        "<td>設置場所を測る</td></tr></tbody></table><details><summary>補足</summary>"
        "<p>公式仕様と実測値を分けます。2 &lt; 3。</p></details></section><!-- /wp:html -->"
        "<!-- Correctly delimited <svg> text is an inert comment. -->"
    )
    owner.verify_commerce_markup(
        markup,
        article_id="article-1",
        editorial_product_ids=frozenset(),
        expected_ctas={},
        expected_images={},
    )
    assert {
        row.tag for row in owner.parse_markup_elements(markup)
    } <= owner.ARTICLE_HTML_TAGS
