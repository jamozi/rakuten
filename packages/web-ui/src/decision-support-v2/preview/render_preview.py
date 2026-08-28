"""Pure renderer for deterministic, offline RAOS V2 preview artifacts."""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any
from urllib.parse import urlsplit

_TEMPLATES = frozenset(
    {"HOME", "HUB", "GUIDE", "COMPARISON", "DIFFERENCE", "TOOL", "POLICY"}
)
_ARTICLE_TEMPLATES = frozenset({"GUIDE", "COMPARISON", "DIFFERENCE", "POLICY"})
_PUBLICATION_STATES = frozenset({"LOCAL_PREVIEW", "PLANNED_LOCKED", "FIXTURE_ONLY"})
_CTA_STATES = frozenset({"IDENTITY_BLOCKED", "UNAVAILABLE"})
_FRESHNESS_STATES = frozenset({"FRESH", "DUE", "HARD_STALE"})
_ROUTE = re.compile(r"^/(?:[a-z0-9]+(?:-[a-z0-9]+)*/)*$")
_SAFE_INTERNAL_HREFS = frozenset(
    {
        "/",
        "/carry-on/",
        "/tools/carry-on-size-checker/",
        "/guides/carry-on-baggage-rules/",
        "/guides/low-cost-carrier-7kg-packing/",
        "/carry-on-suitcase-comparison/",
        "/guides/carry-on-bag-measurement/",
        "/policy/how-we-compare-carry-on-products/",
        "/policy/how-we-compare-carry-on-products/#corrections",
        "/differences/ace-cresta-vs-difference-vs-maxpass4/",
        "/privacy-policy/",
    }
)
_SAFE_EXTERNAL_HREFS = frozenset(
    {
        "https://www.ana.co.jp/ja/jp/guide/boarding-procedures/baggage/domestic/carry-rule/",
        "https://www.jal.co.jp/jp/ja/dom/baggage/inflight/",
        "https://www.flypeach.com/lm/ai/airports/baggage/carry_on_bag",
        "https://www.jetstar.com/jp/ja/flights/baggage/carry-on-baggage",
        "https://store.ace.jp/shop/g/g06316-01/",
        "https://store.ace.jp/shop/g/g05721-04",
        "https://store.ace.jp/shop/g/g01471-02",
    }
)


class PreviewInputError(ValueError):
    """Raised when untrusted preview source input is not renderable."""


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PreviewInputError(f"{field}_MUST_BE_MAPPING")
    return value


def _sequence(value: object, field: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise PreviewInputError(f"{field}_MUST_BE_LIST")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PreviewInputError(f"{field}_MUST_BE_NON_EMPTY_STRING")
    return value


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise PreviewInputError(f"{field}_MUST_BE_BOOLEAN")
    return value


def _escape(value: object) -> str:
    return html.escape(_string(value, "TEXT"), quote=True)


def _validate_route(value: object, field: str = "ROUTE") -> str:
    route = _string(value, field)
    if route != "/" and _ROUTE.fullmatch(route) is None:
        raise PreviewInputError(f"{field}_INVALID")
    if "//" in route or "." in route:
        raise PreviewInputError(f"{field}_INVALID")
    return route


def _render_link(value: object, *, class_name: str = "") -> str:
    link = _mapping(value, "LINK")
    href = _string(link.get("href"), "LINK_HREF")
    label = _escape(link.get("label"))
    external = link.get("external", False)
    if not isinstance(external, bool):
        raise PreviewInputError("LINK_EXTERNAL_MUST_BE_BOOLEAN")
    parsed = urlsplit(href)
    if external:
        if (
            href not in _SAFE_EXTERNAL_HREFS
            or parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.query
            or parsed.fragment
        ):
            raise PreviewInputError("EXTERNAL_LINK_INVALID")
        attributes = ' target="_blank" rel="noopener noreferrer"'
        suffix = '<span class="visually-hidden">（外部サイト）</span>'
    else:
        if (
            href not in _SAFE_INTERNAL_HREFS
            or parsed.query
            or parsed.username is not None
        ):
            raise PreviewInputError("INTERNAL_LINK_INVALID")
        attributes = ""
        suffix = ""
    class_attribute = (
        f' class="{html.escape(class_name, quote=True)}"' if class_name else ""
    )
    return (
        f'<a{class_attribute} href="{html.escape(href, quote=True)}"{attributes}>'
        f"{label}{suffix}</a>"
    )


def _render_breadcrumbs(page: Mapping[str, Any]) -> str:
    breadcrumbs = _sequence(page.get("breadcrumbs"), "BREADCRUMBS")
    items: list[str] = []
    for index, breadcrumb in enumerate(breadcrumbs):
        link = _mapping(breadcrumb, "BREADCRUMB")
        current = index == len(breadcrumbs) - 1
        content = _escape(link.get("label")) if current else _render_link(link)
        current_attribute = ' aria-current="page"' if current else ""
        items.append(f"<li{current_attribute}>{content}</li>")
    return (
        '<nav class="breadcrumbs reading" aria-label="パンくず"><ol>'
        + "".join(items)
        + "</ol></nav>"
    )


def _render_nav() -> str:
    links = (
        '<a href="/carry-on/">機内持ち込み</a>'
        '<a href="/tools/carry-on-size-checker/">条件チェッカー</a>'
        '<a href="/carry-on-suitcase-comparison/">比較ガイド</a>'
        '<a href="/policy/how-we-compare-carry-on-products/">比較方法</a>'
    )
    return (
        '<header class="site-header"><nav class="shell" aria-label="主要ナビゲーション">'
        '<a class="wordmark" href="/">暮らしのしるべ</a>'
        f'<div class="nav-links desktop-nav">{links}</div>'
        '<details class="mobile-menu"><summary>メニュー</summary>'
        f'<div class="nav-links">{links}</div></details>'
        "</nav></header>"
    )


def _render_disclosure(disclosure: object) -> str:
    return (
        '<aside class="disclosure-bar" aria-label="広告表示"><div class="shell">'
        "<strong>広告リンクに関する表示</strong>"
        f"<span>{_escape(disclosure)}</span>"
        '<a href="/policy/how-we-compare-carry-on-products/">比較・広告方針</a>'
        "</div></aside>"
    )


def _render_sections(page: Mapping[str, Any]) -> str:
    rendered: list[str] = []
    for raw_section in _sequence(page.get("sections"), "SECTIONS"):
        section = _mapping(raw_section, "SECTION")
        identifier = _string(section.get("id"), "SECTION_ID")
        if re.fullmatch(r"[a-z][a-z0-9-]*", identifier) is None:
            raise PreviewInputError("SECTION_ID_INVALID")
        paragraphs = "".join(
            f"<p>{_escape(paragraph)}</p>"
            for paragraph in _sequence(section.get("paragraphs"), "SECTION_PARAGRAPHS")
        )
        links = "".join(
            f"<li>{_render_link(link)}</li>"
            for link in _sequence(section.get("links"), "SECTION_LINKS")
        )
        rendered.append(
            '<section class="reading content-section" '
            f'aria-labelledby="{identifier}"><h2 id="{identifier}">'
            f"{_escape(section.get('title'))}</h2>{paragraphs}"
            f"{f'<ul class="link-list">{links}</ul>' if links else ''}</section>"
        )
    return "".join(rendered)


def _render_checker() -> str:
    carrier_options = (
        '<option value="">選択してください</option>'
        '<option value="ANA">ANA</option><option value="JAL">JAL</option>'
        '<option value="PEACH">Peach</option>'
        '<option value="JETSTAR_JAPAN">Jetstar Japan（GK運航便）</option>'
    )
    aircraft_options = (
        '<option value="">わからない</option>'
        '<option value="LARGE">100席以上</option>'
        '<option value="SMALL">100席未満</option>'
    )
    journey_scope_options = (
        '<option value="">選択してください</option>'
        '<option value="DOMESTIC">国内線</option>'
        '<option value="INTERNATIONAL">国際線</option>'
        '<option value="UNKNOWN">わからない・確認中</option>'
    )
    fare_options = (
        '<option value="">わからない・確認中</option>'
        '<option value="STANDARD_7KG">標準7kg条件</option>'
        '<option value="UP_TO_14KG_OPTION">機内持込手荷物オプション（最大14kg）</option>'
        '<option value="NOT_APPLICABLE">該当なし</option>'
    )
    return f"""
<section class="wide tool-panel" aria-labelledby="checker-title">
  <div>
    <p class="eyebrow">入力はこのブラウザ内だけで処理</p>
    <h2 id="checker-title">機内持ち込み条件チェッカー</h2>
    <p>航空会社を推測しません。キャスターとハンドルを含む外寸、身の回り品を含む合計重量・個数を入力してください。</p>
  </div>
  <form id="carry-on-checker" novalidate>
    <div id="form-errors" class="error-summary" tabindex="-1" hidden><h3>入力を確認してください</h3><ul></ul></div>
    <fieldset>
      <legend>搭乗区間1（必須）</legend>
      <label for="carrier">航空会社<select id="carrier" name="carrier" required>{carrier_options}</select></label>
      <label for="journey-scope">路線区分<select id="journey-scope" name="journey-scope" required>{journey_scope_options}</select></label>
      <label for="aircraft">便・機材条件<select id="aircraft" name="aircraft">{aircraft_options}</select></label>
      <label for="fare-option">運賃・手荷物オプション<select id="fare-option" name="fare-option">{fare_options}</select></label>
      <label for="departure-at-jst">出発日時（JST）<input id="departure-at-jst" name="departure-at-jst" type="datetime-local" required></label>
    </fieldset>
    <details>
      <summary>乗り継ぎ区間を追加</summary>
      <fieldset>
        <legend>搭乗区間2（任意）</legend>
        <label for="carrier-2">航空会社<select id="carrier-2" name="carrier-2">{carrier_options}</select></label>
        <label for="journey-scope-2">路線区分<select id="journey-scope-2" name="journey-scope-2">{journey_scope_options}</select></label>
        <label for="aircraft-2">便・機材条件<select id="aircraft-2" name="aircraft-2">{aircraft_options}</select></label>
        <label for="fare-option-2">運賃・手荷物オプション<select id="fare-option-2" name="fare-option-2">{fare_options}</select></label>
        <label for="departure-at-jst-2">出発日時（JST）<input id="departure-at-jst-2" name="departure-at-jst-2" type="datetime-local"></label>
      </fieldset>
    </details>
    <fieldset>
      <legend>荷物（付属部品を含む）</legend>
      <label for="bag-state">測定状態<select id="bag-state" name="bag-state" required><option value="">選択してください</option><option value="NORMAL">通常時</option><option value="EXPANDED">拡張時</option></select></label>
      <div class="field-grid">
        <label for="height">高さ <span>cm</span><input id="height" name="height" inputmode="decimal" autocomplete="off" required></label>
        <label for="width">幅 <span>cm</span><input id="width" name="width" inputmode="decimal" autocomplete="off" required></label>
        <label for="depth">奥行 <span>cm</span><input id="depth" name="depth" inputmode="decimal" autocomplete="off" required></label>
      </div>
      <label for="weight">身の回り品を含む合計重量 <span>kg</span><input id="weight" name="weight" inputmode="decimal" autocomplete="off" required></label>
      <div class="field-grid">
        <label for="carry-on-count">機内持ち込み手荷物の個数<input id="carry-on-count" name="carry-on-count" inputmode="numeric" autocomplete="off" value="1" required></label>
        <label for="personal-item-count">身の回り品の個数<input id="personal-item-count" name="personal-item-count" inputmode="numeric" autocomplete="off" value="1" required></label>
      </div>
      <label class="check-label" for="appendages-included"><input id="appendages-included" name="appendages-included" type="checkbox" value="yes" required>キャスター・ハンドル・外ポケットを含む最大外寸です</label>
      <label class="check-label" for="personal-item-underseat-confirmed"><input id="personal-item-underseat-confirmed" name="personal-item-underseat-confirmed" type="checkbox" value="yes">Jetstar Japanを利用する場合、身の回り品を前の座席の下に収納できることを確認しました</label>
    </fieldset>
    <button class="button primary" type="submit">結果を見る</button>
    <button class="button secondary" type="reset">入力を消す</button>
    <p class="privacy-note">入力値は送信・保存しません。判定後も航空会社の公式ページで最終確認してください。</p>
  </form>
  <div id="checker-result" class="result-panel" data-state="UNKNOWN" role="status" aria-live="polite" aria-atomic="true">
    <h3>まだ判定していません</h3><p>航空会社と荷物条件を入力してください。</p>
  </div>
  <noscript><p class="no-js-note">JavaScriptが無効なため自動判定は使えません。航空会社の公式リンクと入力項目を照らし合わせてください。</p></noscript>
</section>""".strip()


def _render_source(product: Mapping[str, Any]) -> str:
    source = _mapping(product.get("source"), "PRODUCT_SOURCE")
    status = _string(source.get("status"), "SOURCE_STATUS")
    if status not in _FRESHNESS_STATES:
        raise PreviewInputError("SOURCE_STATUS_INVALID")
    stale = "<strong>再確認期限超過</strong>" if status == "HARD_STALE" else ""
    link = {
        "href": source.get("href"),
        "label": source.get("label"),
        "external": True,
    }
    return (
        f'<p class="source-chip" data-freshness="{status}"><span>'
        f"{_escape(source.get('publisher'))}・確認 {_escape(source.get('checked_at'))}"
        f"</span>{stale}{_render_link(link)}</p>"
    )


def _render_product(product: Mapping[str, Any]) -> str:
    product_id = _string(product.get("product_id"), "PRODUCT_ID")
    if re.fullmatch(r"[A-Z0-9-]+", product_id) is None:
        raise PreviewInputError("PRODUCT_ID_INVALID")
    cta_state = _string(product.get("cta_state"), "CTA_STATE")
    if cta_state not in _CTA_STATES:
        raise PreviewInputError("CTA_STATE_INVALID")
    facts = "".join(
        f"<li>{_escape(fact)}</li>"
        for fact in _sequence(product.get("facts"), "PRODUCT_FACTS")
    )
    judgement = "".join(
        f"<div><dt>{label}</dt><dd>{_escape(product.get(field))}</dd></div>"
        for field, label in (
            ("fit", "向く条件"),
            ("non_fit", "向かない条件"),
            ("tradeoff", "トレードオフ"),
            ("unknown", "未確認"),
        )
    )
    return (
        f'<article class="product-card" aria-labelledby="product-{product_id}">'
        f'<p class="meta">メーカー型番 {_escape(product.get("model_number"))}</p>'
        f'<h3 id="product-{product_id}">{_escape(product.get("name"))}</h3>'
        '<div class="product-placeholder" role="img" aria-label="商品画像は使用していません">商品画像なし</div>'
        f"<h4>公式仕様</h4><ul>{facts}</ul>"
        f'<dl class="judgement-list">{judgement}</dl>{_render_source(product)}'
        '<div class="affiliate-cta is-blocked" role="group" aria-label="楽天リンク利用不可">'
        "<strong>楽天CTA：確認待ち</strong>"
        "<p>型番・世代・販売単位を一意に結び付けられるまでリンクを表示しません。</p>"
        '<button type="button" disabled>現在情報を確認できません</button></div></article>'
    )


def _render_comparison(
    page: Mapping[str, Any], products: Mapping[str, Mapping[str, Any]]
) -> str:
    product_ids = [
        _string(value, "PAGE_PRODUCT_ID")
        for value in _sequence(page.get("products"), "PAGE_PRODUCTS")
    ]
    if not product_ids:
        return ""
    selected = [products[product_id] for product_id in product_ids]
    axes = [
        _mapping(value, "COMPARISON_AXIS")
        for value in _sequence(page.get("comparison_axes"), "COMPARISON_AXES")
    ]
    headers = "".join(
        f'<th scope="col">{_escape(product.get("name"))}</th>' for product in selected
    )
    rows: list[str] = []
    mobile: list[str] = []
    for axis in axes:
        values = _mapping(axis.get("values"), "COMPARISON_VALUES")
        label = _escape(axis.get("label"))
        cells = "".join(
            f"<td>{_escape(values.get(product_id, '未確認'))}</td>"
            for product_id in product_ids
        )
        rows.append(f'<tr><th scope="row">{label}</th>{cells}</tr>')
        descriptions = "".join(
            f"<div><dt>{_escape(product.get('name'))}</dt>"
            f"<dd>{_escape(values.get(product_id, '未確認'))}</dd></div>"
            for product_id, product in zip(product_ids, selected, strict=True)
        )
        mobile.append(
            f'<article class="matrix-mobile-card"><h3>{label}</h3><dl>{descriptions}</dl></article>'
        )
    table = (
        '<div class="table-scroll" role="region" aria-label="3モデル比較表" tabindex="0">'
        "<table><caption>ACE 3モデルの公式仕様と未確認事項</caption>"
        f'<thead><tr><th scope="col">比較軸</th>{headers}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )
    cards = "".join(_render_product(product) for product in selected)
    return (
        '<section class="wide comparison-matrix" aria-labelledby="comparison-matrix-title">'
        '<h2 id="comparison-matrix-title">仕様を同じ軸で比較</h2>'
        f'{table}<div class="matrix-mobile">{"".join(mobile)}</div></section>'
        '<section class="wide" aria-labelledby="product-cards-title">'
        f'<h2 id="product-cards-title">条件ごとの候補</h2><div class="product-grid">{cards}</div>'
        '<aside class="none-fit"><h3>3商品とも合わない条件</h3>'
        "<p>航空会社の条件、拡張時の外寸、必要容量が一致しない場合は購入候補にしません。条件を見直すか、別の商品群を探してください。</p>"
        "</aside></section>"
    )


def _article_metadata(page: Mapping[str, Any]) -> tuple[str, str, str] | None:
    """Return visible Article metadata only when the complete tuple is valid."""

    raw = (
        page.get("author_name"),
        page.get("date_published"),
        page.get("date_modified"),
    )
    if all(value is None for value in raw):
        return None
    if any(value is None for value in raw):
        raise PreviewInputError("ARTICLE_METADATA_INCOMPLETE")
    author, published, modified = raw
    if (
        page.get("template") not in _ARTICLE_TEMPLATES
        or not isinstance(author, str)
        or not author.strip()
        or author != author.strip()
        or not isinstance(published, str)
        or not isinstance(modified, str)
    ):
        raise PreviewInputError("ARTICLE_METADATA_INVALID")
    try:
        published_date = date.fromisoformat(published)
        modified_date = date.fromisoformat(modified)
    except ValueError as exc:
        raise PreviewInputError("ARTICLE_METADATA_INVALID") from exc
    if (
        published != published_date.isoformat()
        or modified != modified_date.isoformat()
        or modified_date < published_date
    ):
        raise PreviewInputError("ARTICLE_METADATA_INVALID")
    return author, published, modified


def _render_article_metadata(page: Mapping[str, Any]) -> str:
    metadata = _article_metadata(page)
    if metadata is None:
        return ""
    author, published, modified = metadata
    return (
        '<p class="article-meta">'
        f'<span>執筆者：{_escape(author)}</span>'
        f'<span>公開日：<time datetime="{published}">{published}</time></span>'
        f'<span>更新日：<time datetime="{modified}">{modified}</time></span>'
        "</p>"
    )


def _render_json_ld(page: Mapping[str, Any], origin: str, preview_robots: str) -> str:
    if preview_robots != "index,follow":
        return ""
    route = _validate_route(page.get("route"))
    graph: list[dict[str, Any]] = [
        {
            "@type": "Organization",
            "@id": f"{origin}/#organization",
            "name": "暮らしのしるべ",
            "url": f"{origin}/",
        }
    ]
    if page.get("template") == "HOME":
        graph.append(
            {
                "@type": "WebSite",
                "@id": f"{origin}/#website",
                "inLanguage": "ja-JP",
                "name": "暮らしのしるべ",
                "url": f"{origin}/",
                "publisher": {"@id": f"{origin}/#organization"},
            }
        )
    else:
        breadcrumb_items = []
        for position, raw_link in enumerate(
            _sequence(page.get("breadcrumbs"), "BREADCRUMBS"), start=1
        ):
            link = _mapping(raw_link, "BREADCRUMB")
            href = _string(link.get("href"), "BREADCRUMB_HREF")
            breadcrumb_items.append(
                {
                    "@type": "ListItem",
                    "position": position,
                    "name": _string(link.get("label"), "BREADCRUMB_LABEL"),
                    "item": f"{origin}{href}",
                }
            )
        graph.append(
            {
                "@type": "BreadcrumbList",
                "itemListElement": breadcrumb_items,
            }
        )
        metadata = _article_metadata(page)
        if metadata is not None:
            author, published, modified = metadata
            graph.append(
                {
                    "@type": "Article",
                    "author": {"@type": "Organization", "name": author},
                    "dateModified": modified,
                    "datePublished": published,
                    "headline": _string(page.get("title"), "TITLE"),
                    "inLanguage": "ja-JP",
                    "mainEntityOfPage": f"{origin}{route}",
                    "publisher": {"@id": f"{origin}/#organization"},
                }
            )
    serialized = json.dumps(
        {"@context": "https://schema.org", "@graph": graph},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{serialized}</script>'


def _render_page(
    *,
    page: Mapping[str, Any],
    products: Mapping[str, Mapping[str, Any]],
    origin: str,
    disclosure: str,
    preview_robots: str,
    css: str,
    javascript: str,
) -> bytes:
    route = _validate_route(page.get("route"))
    template = _string(page.get("template"), "TEMPLATE")
    if template not in _TEMPLATES:
        raise PreviewInputError("TEMPLATE_INVALID")
    state = _string(page.get("publication_state"), "PUBLICATION_STATE")
    if state not in _PUBLICATION_STATES:
        raise PreviewInputError("PUBLICATION_STATE_INVALID")
    intended_index_candidate = _boolean(
        page.get("intended_index_candidate"), "INTENDED_INDEX_CANDIDATE"
    )
    public_candidate = _boolean(page.get("public_candidate"), "PUBLIC_CANDIDATE")
    if state != "LOCAL_PREVIEW" and (intended_index_candidate or public_candidate):
        raise PreviewInputError("NON_PUBLIC_STATE_CANDIDATE_INVALID")
    title = _string(page.get("title"), "TITLE")
    canonical = f"{origin}{route}"
    robots = preview_robots
    checker = (
        _render_checker() if _boolean(page.get("show_checker"), "SHOW_CHECKER") else ""
    )
    comparison = _render_comparison(page, products)
    structured_data = _render_json_ld(page, origin, preview_robots)
    runtime = f"<script>{javascript}</script>" if checker else ""
    document = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src 'none'; connect-src data:; form-action 'none'; base-uri 'none'">
  <meta name="referrer" content="no-referrer">
  <link rel="icon" href="data:,">
  <title>{html.escape(title)} | 暮らしのしるべ</title>
  <meta name="description" content="{_escape(page.get("description"))}">
  <meta name="robots" content="{robots}">
  <link rel="canonical" href="{html.escape(canonical, quote=True)}">
  {structured_data}
  <style>{css}</style>
</head>
<body data-template="{template}" data-route="{html.escape(route, quote=True)}" data-publication-state="{state}">
  <a class="skip-link" href="#main">本文へ移動</a>
  {_render_nav()}
  {_render_disclosure(disclosure)}
  {_render_breadcrumbs(page)}
  <main id="main" tabindex="-1">
    <header class="decision-hero reading">
      <p class="eyebrow">{_escape(page.get("eyebrow"))}</p>
      <h1>{html.escape(title)}</h1>
      <p class="lead">{_escape(page.get("summary"))}</p>
      {_render_article_metadata(page)}
    </header>
    {checker}
    {_render_sections(page)}
    {comparison}
    <section class="reading trust-strip" aria-labelledby="trust-title">
      <h2 id="trust-title">根拠の読み方</h2>
      <dl><div><dt>公式情報</dt><dd>発行主体と確認日を表示します。</dd></div><div><dt>編集判断</dt><dd>条件と理由を明記します。</dd></div><div><dt>未確認</dt><dd>推測せず、購入判断を止めます。</dd></div></dl>
    </section>
    <section class="reading change-log" aria-labelledby="change-log-title">
      <h2 id="change-log-title">確認・変更履歴</h2>
      <p>ローカルプレビュー。公開・配信・WordPress書き込みは実行していません。</p>
      <a href="/policy/how-we-compare-carry-on-products/#corrections">誤りを知らせる</a>
    </section>
  </main>
  <footer class="site-footer"><div class="shell"><p>暮らしのしるべ — 公式情報と編集判断を分ける購買支援</p><nav aria-label="方針"><a href="/policy/how-we-compare-carry-on-products/">比較方法</a><a href="/privacy-policy/">プライバシー</a></nav></div></footer>
  {runtime}
</body>
</html>
"""
    return document.encode("utf-8")


def render_pages(
    *, pages: dict[str, Any], css: str, javascript: str
) -> dict[str, bytes]:
    """Render route-keyed HTML without filesystem, clock, random or network access."""

    if pages.get("schema_version") != "2.0.0":
        raise PreviewInputError("SCHEMA_VERSION_INVALID")
    if pages.get("classification") != "DETERMINISTIC_LOCAL_PREVIEW_INPUT":
        raise PreviewInputError("CLASSIFICATION_INVALID")
    if "</style" in css.lower() or "</script" in javascript.lower():
        raise PreviewInputError("INLINE_BOUNDARY_INVALID")
    forbidden_runtime_tokens = (
        "fetch(",
        "xmlhttprequest",
        "sendbeacon",
        "localstorage",
        "sessionstorage",
        "indexeddb",
        "serviceworker",
        "document.cookie",
    )
    lowered_runtime = javascript.lower()
    if any(token in lowered_runtime for token in forbidden_runtime_tokens):
        raise PreviewInputError("RUNTIME_EXTERNAL_EFFECT_PROHIBITED")
    origin = _string(pages.get("target_origin"), "TARGET_ORIGIN").rstrip("/")
    parsed_origin = urlsplit(origin)
    if (
        parsed_origin.scheme != "https"
        or parsed_origin.netloc != "kurashinoshirube.com"
        or parsed_origin.path
        or parsed_origin.query
        or parsed_origin.fragment
    ):
        raise PreviewInputError("TARGET_ORIGIN_INVALID")
    if pages.get("publication_authority") != "NONE":
        raise PreviewInputError("PUBLICATION_AUTHORITY_INVALID")
    preview_robots = _string(pages.get("preview_robots"), "PREVIEW_ROBOTS")
    if preview_robots != "noindex,nofollow":
        raise PreviewInputError("PREVIEW_ROBOTS_MUST_BE_NOINDEX")
    disclosure = _string(pages.get("disclosure"), "DISCLOSURE")
    product_values = _mapping(pages.get("products"), "PRODUCTS")
    products: dict[str, Mapping[str, Any]] = {}
    for product_id, raw_product in product_values.items():
        product = _mapping(raw_product, "PRODUCT")
        if product.get("product_id") != product_id:
            raise PreviewInputError("PRODUCT_ID_BINDING_INVALID")
        products[product_id] = product
    rendered: dict[str, bytes] = {}
    for raw_page in _sequence(pages.get("pages"), "PAGES"):
        page = _mapping(raw_page, "PAGE")
        route = _validate_route(page.get("route"))
        if route in rendered:
            raise PreviewInputError("ROUTE_DUPLICATE")
        for product_id in _sequence(page.get("products"), "PAGE_PRODUCTS"):
            if product_id not in products:
                raise PreviewInputError("PAGE_PRODUCT_UNKNOWN")
        rendered[route] = _render_page(
            page=page,
            products=products,
            origin=origin,
            disclosure=disclosure,
            preview_robots=preview_robots,
            css=css,
            javascript=javascript,
        )
    return dict(sorted(rendered.items()))
