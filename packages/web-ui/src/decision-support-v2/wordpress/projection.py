"""Pure WordPress ``post_content`` projection for the Phase 3 A05 slice.

The caller owns input loading and output persistence.  This module deliberately
has no filesystem, clock, network, WordPress, or hashing dependency; identical
validated input mappings therefore produce identical UTF-8 text.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape as _html_escape
import re
from typing import Final


SCHEMA: Final = "RAOS_V2_WORDPRESS_POST_CONTENT_PROJECTION_V1"
TARGET_ROUTE: Final = "/carry-on-suitcase-comparison/"
TARGET_ARTICLE_ID: Final = "A05"
TARGET_TEMPLATE: Final = "COMPARISON"
PACKAGE_MARKER: Final = "RAOS_V2_A05_POST_CONTENT_V1"
HEADING_OWNER: Final = "WORDPRESS_POST_TITLE"

VERIFIED_PUBLIC_INTERNAL_ROUTES: Final = frozenset(
    {
        "/",
        TARGET_ROUTE,
        "/about-ad-policy/",
        "/privacy-policy/",
    }
)

EXPECTED_PRODUCT_IDS: Final = (
    "PRD-ACE-CRESTA-06316",
    "PRD-ACE-DIFFERENCE-05721",
    "PRD-ACE-MAXPASS4-01471",
)
OFFICIAL_SOURCE_LINKS: Final = {
    "PRD-ACE-CRESTA-06316": (
        "https://store.ace.jp/shop/g/g06316-01/",
        "クレスタ06316公式仕様",
    ),
    "PRD-ACE-DIFFERENCE-05721": (
        "https://store.ace.jp/shop/g/g05721-04",
        "ディフェレンス05721公式仕様",
    ),
    "PRD-ACE-MAXPASS4-01471": (
        "https://store.ace.jp/shop/g/g01471-02",
        "マックスパス4 01471公式仕様",
    ),
}

_FORBIDDEN_PRODUCT_FIELDS: Final = frozenset(
    {
        "affiliate_url",
        "business_score",
        "epc",
        "image_url",
        "offer",
        "price",
        "rate",
    }
)
_WORDPRESS_ENTITY_REFERENCE = re.compile(
    r"&(?:\#[xX][0-9a-fA-F]+;?|\#\d+;?|[a-zA-Z][a-zA-Z0-9]+;)",
    re.ASCII,
)
_COMPARISON_AXIS_EVIDENCE: Final = {
    "通常時の外寸": ("A_OFFICIAL_FACT", "公式情報"),
    "通常時の容量": ("A_OFFICIAL_FACT", "公式情報"),
    "公表重量": ("A_OFFICIAL_FACT", "公式情報"),
    "条件別の特徴": ("D_EDITORIAL_JUDGEMENT", "編集判断"),
}


class WordPressProjectionError(ValueError):
    """Raised when source data cannot be projected without inventing facts."""


def escape(value: str, quote: bool = True) -> str:
    """Escape HTML and neutralize WordPress shortcode delimiters."""

    return _html_escape(value, quote=quote).replace("[", "&#91;").replace("]", "&#93;")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise WordPressProjectionError(f"{field} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise WordPressProjectionError(f"{field} keys must be strings")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise WordPressProjectionError(f"{field} must be an array")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise WordPressProjectionError(f"{field} must be non-empty clean text")
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise WordPressProjectionError(f"{field} must be single-line text")
    return value


def _wordpress_plain_text(value: object, field: str) -> str:
    """Validate a raw WordPress scalar that must never be interpreted as markup."""

    text = _text(value, field)
    if (
        not text.isprintable()
        or any(delimiter in text for delimiter in ("<", ">", "[", "]"))
        or _WORDPRESS_ENTITY_REFERENCE.search(text) is not None
    ):
        raise WordPressProjectionError(f"{field} must be strict plain text")
    return text


def _text_list(value: object, field: str) -> tuple[str, ...]:
    return tuple(
        _text(item, f"{field}[{index}]")
        for index, item in enumerate(_sequence(value, field))
    )


def _paragraphs(values: Sequence[str]) -> str:
    return "".join(f"<p>{escape(value)}</p>" for value in values)


def _render_comparison_table(
    axes: Sequence[object], products: Sequence[Mapping[str, object]]
) -> str:
    if len(axes) != 4 or len(products) != 3:
        raise WordPressProjectionError(
            "A05 comparison must contain 4 axes and 3 products"
        )
    headers = "".join(
        f'<th scope="col">{escape(_text(product["name"], "product.name"))}</th>'
        for product in products
    )
    rows: list[str] = []
    mobile_cards: list[str] = []
    product_ids = tuple(
        _text(product.get("product_id"), "product.product_id") for product in products
    )
    for axis_index, raw_axis in enumerate(axes):
        axis = _mapping(raw_axis, f"page.comparison_axes[{axis_index}]")
        label = _text(axis.get("label"), f"comparison_axes[{axis_index}].label")
        evidence = _COMPARISON_AXIS_EVIDENCE.get(label)
        if evidence is None:
            raise WordPressProjectionError("comparison axis evidence type is unknown")
        evidence_type, evidence_label = evidence
        values = _mapping(axis.get("values"), f"comparison_axes[{axis_index}].values")
        expected_value_keys = set(product_ids)
        if set(values) != expected_value_keys:
            raise WordPressProjectionError(
                "comparison axis values must exactly match the bound products"
            )
        cells = "".join(
            f"<td>{escape(_text(values.get(product_id), 'axis.value'))}</td>"
            for product_id in product_ids
        )
        rows.append(
            f'<tr data-raos-v2-evidence="{evidence_type}"><th scope="row">'
            f'<span class="raos-v2-decision-support__axis-title">{escape(label)}</span>'
            f'<span class="raos-v2-decision-support__axis-evidence">{evidence_label}</span>'
            f"</th>{cells}</tr>"
        )
        axis_id = f"raos-v2-mobile-axis-{axis_index + 1}"
        mobile_values = "".join(
            "<div>"
            f"<dt>{escape(_text(product['name'], 'product.name'))}</dt>"
            f"<dd>{escape(_text(values.get(product_id), 'axis.value'))}</dd>"
            "</div>"
            for product, product_id in zip(products, product_ids, strict=True)
        )
        mobile_cards.append(
            '<article class="raos-v2-decision-support__comparison-card" '
            f'data-raos-v2-evidence="{evidence_type}" aria-labelledby="{axis_id}">'
            f'<h3 id="{axis_id}">{escape(label)}</h3>'
            f'<p class="raos-v2-decision-support__axis-evidence">{evidence_label}</p>'
            f"<dl>{mobile_values}</dl></article>"
        )
    return (
        '<div class="raos-v2-decision-support__table-scroll" role="region" '
        'aria-label="ACE 3モデル比較表" tabindex="0"><table>'
        "<caption>公式仕様と条件別の編集判断</caption><thead><tr>"
        f'<th scope="col">比較軸</th>{headers}</tr></thead><tbody>'
        f"{''.join(rows)}</tbody></table></div>"
        '<div class="raos-v2-decision-support__comparison-cards" role="region" '
        'aria-label="ACE 3モデル比較（モバイル表示）">'
        f"{''.join(mobile_cards)}</div>"
    )


def _render_product(product: Mapping[str, object]) -> str:
    product_id = _text(product.get("product_id"), "product.product_id")
    if product_id not in EXPECTED_PRODUCT_IDS:
        raise WordPressProjectionError("product.product_id is outside the A05 scope")
    name = _text(product.get("name"), f"products.{product_id}.name")
    model_number = _text(
        product.get("model_number"), f"products.{product_id}.model_number"
    )
    facts = _text_list(product.get("facts"), f"products.{product_id}.facts")
    source = _mapping(product.get("source"), f"products.{product_id}.source")
    publisher = _text(source.get("publisher"), f"products.{product_id}.publisher")
    source_href = _text(source.get("href"), f"products.{product_id}.source.href")
    source_label = _text(source.get("label"), f"products.{product_id}.source.label")
    if (source_href, source_label) != OFFICIAL_SOURCE_LINKS[product_id]:
        raise WordPressProjectionError(
            f"{product_id} official source link is outside the closed allowlist"
        )
    if source.get("status") != "FRESH":
        raise WordPressProjectionError(f"{product_id} official source is not fresh")
    checked_at = _text(source.get("checked_at"), f"products.{product_id}.checked_at")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked_at):
        raise WordPressProjectionError("product checked_at must be an ISO date")
    if product.get("cta_state") != "IDENTITY_BLOCKED":
        raise WordPressProjectionError(f"{product_id} CTA must fail closed")
    if _FORBIDDEN_PRODUCT_FIELDS.intersection(product):
        raise WordPressProjectionError(f"{product_id} contains commerce-only fields")

    facts_markup = "".join(f"<li>{escape(fact)}</li>" for fact in facts)
    fit = escape(_text(product.get("fit"), f"products.{product_id}.fit"))
    non_fit = escape(_text(product.get("non_fit"), f"products.{product_id}.non_fit"))
    tradeoff = escape(_text(product.get("tradeoff"), f"products.{product_id}.tradeoff"))
    unknown = escape(_text(product.get("unknown"), f"products.{product_id}.unknown"))
    heading_id = f"raos-v2-product-{product_id.lower()}"
    escaped_product_id = escape(product_id, quote=True)
    escaped_heading_id = escape(heading_id, quote=True)
    return (
        '<section class="raos-v2-decision-support__product" '
        f'aria-labelledby="{escaped_heading_id}" '
        f'data-raos-v2-product-id="{escaped_product_id}">'
        f'<p class="raos-v2-decision-support__model">メーカー型番 {escape(model_number)}</p>'
        f'<h3 id="{escaped_heading_id}">{escape(name)}</h3>'
        "<h4>公式仕様</h4>"
        f"<ul>{facts_markup}</ul>"
        '<dl class="raos-v2-decision-support__judgement">'
        f"<div><dt>向く条件</dt><dd>{fit}</dd></div>"
        f"<div><dt>向かない条件</dt><dd>{non_fit}</dd></div>"
        f"<div><dt>トレードオフ</dt><dd>{tradeoff}</dd></div>"
        f'<div data-raos-v2-claim-state="UNKNOWN"><dt>未確認</dt><dd>{unknown}</dd></div>'
        "</dl>"
        '<p class="raos-v2-decision-support__evidence" data-raos-v2-evidence="A_OFFICIAL_FACT">'
        f'公式情報：<a href="{escape(source_href, quote=True)}">'
        f"{escape(source_label)}</a>（{escape(publisher)}）／確認日 "
        f'<time datetime="{checked_at}">'
        f"{checked_at}</time></p>"
        '<div class="raos-v2-decision-support__cta is-blocked" '
        'data-raos-v2-cta-state="BLOCKED" role="status">'
        "<strong>楽天市場の商品リンク：確認待ち</strong>"
        "<p>型番・世代・販売単位を一意に確認できるまで、商品リンクを表示しません。</p>"
        '<button type="button" disabled aria-disabled="true">現在は商品リンクを利用できません</button>'
        "</div></section>"
    )


def project_a05_wordpress_post_content_v1(
    package: Mapping[str, object],
) -> dict[str, object]:
    """Return the exact A05 WordPress projection without any side effect.

    The returned ``post_content`` is an HTML fragment.  The selected WordPress
    mapping keeps the document H1 in the existing post-title template, so this
    fragment intentionally contains no H1, ``html``, ``head``, or metadata tags.
    """

    package = _mapping(package, "package")
    pages = _sequence(package.get("pages"), "package.pages")
    matches = [
        _mapping(page, "package.pages[]")
        for page in pages
        if isinstance(page, Mapping) and page.get("article_id") == TARGET_ARTICLE_ID
    ]
    if len(matches) != 1:
        raise WordPressProjectionError("package must contain exactly one A05 page")
    page = matches[0]
    if (
        page.get("route") != TARGET_ROUTE
        or page.get("template") != TARGET_TEMPLATE
        or page.get("public_candidate") is not True
    ):
        raise WordPressProjectionError("A05 route/template/public binding is invalid")

    product_ids = tuple(
        _text(value, "page.products[]")
        for value in _sequence(page.get("products"), "page.products")
    )
    if product_ids != EXPECTED_PRODUCT_IDS:
        raise WordPressProjectionError("A05 product order/scope is invalid")
    product_map = _mapping(package.get("products"), "package.products")
    products = tuple(
        _mapping(product_map.get(product_id), f"products.{product_id}")
        for product_id in product_ids
    )
    if any(
        product.get("product_id") != expected_id
        for expected_id, product in zip(product_ids, products, strict=True)
    ):
        raise WordPressProjectionError(
            "product map key and nested product_id must match exactly"
        )

    sections = _sequence(page.get("sections"), "page.sections")
    if len(sections) != 1:
        raise WordPressProjectionError("A05 must have one conditional conclusion")
    conclusion = _mapping(sections[0], "page.sections[0]")
    conclusion_title = _text(conclusion.get("title"), "page.sections[0].title")
    conclusion_paragraphs = _text_list(
        conclusion.get("paragraphs"), "page.sections[0].paragraphs"
    )
    disclosure = _text(package.get("disclosure"), "package.disclosure")
    checked_at = _text(package.get("checked_at"), "package.checked_at")
    checked_date_match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})T.*", checked_at)
    if checked_date_match is None:
        raise WordPressProjectionError("package.checked_at must include an ISO date")
    checked_date = checked_date_match.group(1)

    title = _wordpress_plain_text(page.get("title"), "page.title")
    description = _wordpress_plain_text(page.get("description"), "page.description")
    summary = _text(page.get("summary"), "page.summary")
    comparison = _render_comparison_table(
        _sequence(page.get("comparison_axes"), "page.comparison_axes"), products
    )
    product_markup = "".join(_render_product(product) for product in products)
    unknown_items = "".join(
        f"<li><strong>{escape(_text(product.get('name'), 'product.name'))}：</strong>"
        f"{escape(_text(product.get('unknown'), 'product.unknown'))}</li>"
        for product in products
    )

    post_content = (
        '<div class="raos-v2-decision-support" '
        f'data-raos-v2-package-marker="{PACKAGE_MARKER}" '
        f'data-raos-v2-article-id="{TARGET_ARTICLE_ID}">'
        '<aside class="raos-v2-decision-support__disclosure" aria-label="広告表示">'
        f"<strong>広告リンクに関する表示</strong><p>{escape(disclosure)}</p>"
        '<p><a href="/about-ad-policy/">運営・広告方針を確認する</a></p></aside>'
        '<header class="raos-v2-decision-support__intro">'
        '<p class="raos-v2-decision-support__eyebrow">条件で結論が変わる比較</p>'
        f'<p class="raos-v2-decision-support__lead">{escape(summary)}</p>'
        '<dl class="raos-v2-decision-support__metadata">'
        "<div><dt>編集主体</dt><dd>暮らしのしるべ編集部</dd></div>"
        f'<div><dt>根拠パケット基準日</dt><dd><time datetime="{checked_date}">'
        f"{checked_date}</time></dd></div>"
        "<div><dt>実機試験</dt><dd>実施していません</dd></div>"
        "</dl></header>"
        '<section class="raos-v2-decision-support__section" '
        'aria-labelledby="raos-v2-conditional-conclusion">'
        f'<h2 id="raos-v2-conditional-conclusion">{escape(conclusion_title)}</h2>'
        f"{_paragraphs(conclusion_paragraphs)}</section>"
        '<section class="raos-v2-decision-support__section" '
        'aria-labelledby="raos-v2-comparison">'
        '<h2 id="raos-v2-comparison">仕様を同じ軸で比較</h2>'
        f"{comparison}</section>"
        '<section class="raos-v2-decision-support__section" '
        'aria-labelledby="raos-v2-products">'
        '<h2 id="raos-v2-products">条件ごとの候補</h2>'
        f'<div class="raos-v2-decision-support__product-grid">{product_markup}</div>'
        "</section>"
        '<section class="raos-v2-decision-support__section '
        'raos-v2-decision-support__evidence-method" '
        'aria-labelledby="raos-v2-evidence-method">'
        '<h2 id="raos-v2-evidence-method">根拠と編集判断の分け方</h2>'
        "<dl><div><dt>公式情報</dt><dd>メーカーが公表した仕様を、発行主体と確認日付きで示します。</dd></div>"
        "<div><dt>編集判断</dt><dd>公式仕様から導いた条件別の判断として明示します。</dd></div>"
        "<div><dt>未確認</dt><dd>実機を使わなければ確認できない事項は推測しません。</dd></div></dl>"
        "</section>"
        '<section class="raos-v2-decision-support__section '
        'raos-v2-decision-support__unknown" data-raos-v2-result-state="UNKNOWN" '
        'aria-labelledby="raos-v2-unknown">'
        '<h2 id="raos-v2-unknown">未確認（UNKNOWN）の事項</h2>'
        f"<ul>{unknown_items}</ul>"
        "<p>未確認事項を購入判断に使わず、必要な場合は確認できるまで判断を止めます。</p>"
        "</section>"
        '<nav class="raos-v2-decision-support__policies" aria-label="関連方針">'
        '<a href="/about-ad-policy/">運営・広告方針</a>'
        '<a href="/privacy-policy/">プライバシーポリシー</a>'
        "</nav></div>"
    )

    lowered = post_content.lower()
    if re.search(r"<(?:h1|html|head|img|script)(?:\s|>)", lowered) is not None or any(
        token in lowered
        for token in (
            "affiliate.rakuten",
            "hb.afl.rakuten",
            "ローカルプレビュー",
        )
    ):
        raise WordPressProjectionError(
            "projection contains forbidden presentation data"
        )
    hrefs = tuple(re.findall(r'href="([^"]+)"', post_content))
    linked_routes = tuple(dict.fromkeys(href for href in hrefs if href.startswith("/")))
    if not set(linked_routes).issubset(VERIFIED_PUBLIC_INTERNAL_ROUTES):
        raise WordPressProjectionError("projection links an unverified internal route")
    official_sources = {href for href, _label in OFFICIAL_SOURCE_LINKS.values()}
    if (
        any(
            href not in VERIFIED_PUBLIC_INTERNAL_ROUTES and href not in official_sources
            for href in hrefs
        )
        or {href for href in hrefs if href.startswith("https://")} != official_sources
    ):
        raise WordPressProjectionError("projection links an unverified external source")
    if post_content.count('data-raos-v2-cta-state="BLOCKED"') != 3:
        raise WordPressProjectionError(
            "projection must contain exactly three blocked CTAs"
        )

    return {
        "schema": SCHEMA,
        "article_id": TARGET_ARTICLE_ID,
        "route": TARGET_ROUTE,
        "post_type": "post",
        "post_title": title,
        "post_excerpt": description,
        "post_status": "publish",
        "comment_status": "closed",
        "ping_status": "closed",
        "package_marker": PACKAGE_MARKER,
        "heading_contract": {
            "document_heading_owner": HEADING_OWNER,
            "expected_document_h1_count": 1,
            "post_content_h1_count": 0,
        },
        "linked_internal_routes": list(linked_routes),
        "image_count": 0,
        "affiliate_url_count": 0,
        "blocked_cta_count": 3,
        "post_content": post_content,
    }
