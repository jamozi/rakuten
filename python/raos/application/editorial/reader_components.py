"""Reusable reader decisions, evidence, uncertainty and checks as HTML fragments.

Product identity and facts are resolved by the existing editorial adapters. This
module renders editorial judgments separately and cannot make a provider call.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
import math
from typing import cast

from raos.application.editorial.reader_html import Element, block
from raos.application.editorial.reader_experience_v1 import ArticleType, CtaType, CtaEvidence, cta_visible
from raos.application.editorial.reader_experience_v1 import CheckedFact, approved_media_record
import re


def section(identifier: str, heading: str, content: str, cls: str) -> Element:
    return block(f'<section class="{escape(cls)}" aria-labelledby="{escape(identifier)}"><h2 id="{escape(identifier)}">{escape(heading)}</h2>{content}</section>')


def decision_axes(axes: Sequence[Mapping[str, str]]) -> Element | None:
    if not axes:
        return None
    if len(axes) > 5:
        raise ValueError("READER_AXES_MAX_FIVE")
    items = ''.join(f'<li><h3>{escape(row["label"])}</h3><p>{escape(row["why_it_matters"])}</p><p><strong>確認方法：</strong>{escape(row["how_to_check"])}</p></li>' for row in axes)
    return section('reader-axes', f'最初に確かめる{len(axes)}条件', f'<ol class="raos-reader-axes">{items}</ol>', 'raos-decision-axes')


def decision_table(rows: Sequence[Mapping[str, str]]) -> Element | None:
    if not rows:
        return None
    headings = ('条件', '候補', '選ぶ理由', '妥協点・選ばない条件', '購入前の確認')
    keys = ('condition', 'product_name', 'reason', 'tradeoff', 'purchase_check')
    body: list[str] = []
    for row in rows:
        cells: list[str] = []
        for index, (label, key) in enumerate(zip(headings, keys, strict=True)):
            value = escape(row[key])
            if key == 'product_name':
                value = f'<a href="#{escape(row["anchor"], quote=True)}">{value}</a>'
            if key == 'tradeoff':
                value = ('<p><strong>妥協点：</strong>' + value + '</p>') if value else (
                    '<p><strong>妥協点：</strong><a href="#' + escape(row['anchor'], quote=True) + '">商品の詳細で確認</a></p>')
                if row.get('not_for'):
                    value += '<p><strong>選ばない条件：</strong>' + escape(row['not_for']) + '</p>'
            tag = 'th' if index == 0 else 'td'
            scope = ' scope="row"' if index == 0 else ''
            cells.append(f'<{tag}{scope} data-label="{label}">{value}</{tag}>')
        body.append('<tr>' + ''.join(cells) + '</tr>')
    return section('reader-decisions', '自分の条件と、引き受ける妥協点で絞る', '<table class="raos-decision-table"><caption>条件と候補を対応させる判断表</caption><thead><tr>' + ''.join(f'<th scope="col">{label}</th>' for label in headings) + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table>', 'raos-reader-decision-table')


def unknowns_panel(items: Sequence[Mapping[str, str]]) -> Element | None:
    if not items:
        return None
    body = ''.join(f'<div><h3>{escape(row["topic"])}</h3><dl><div><dt>仕様だけでは分からない理由</dt><dd>{escape(row["why_unknown"])}</dd></div><div><dt>確かめる方法</dt><dd>{escape(row["how_to_verify"])}</dd></div><div><dt>選択への影響</dt><dd>{escape(row["decision_effect"])}</dd></div></dl></div>' for row in items)
    return section('reader-unknowns', '仕様だけでは分からないこと', body, 'raos-unknowns-panel')


def purchase_checklist(checks: Sequence[str]) -> Element | None:
    if not checks:
        return None
    items = ''.join(f'<li>{escape(check)}</li>' for check in checks)
    return section('reader-purchase-checks', '購入前に、この条件を確かめる', f'<ul class="raos-purchase-checklist">{items}</ul>', 'raos-reader-purchase-checklist')


def safety_rule_panel(rule: Mapping[str, str]) -> Element | None:
    """Optional rule module, supplied only after its official reference resolves."""
    if any(not isinstance(rule.get(k), str) or not rule[k].strip() for k in ('authority', 'final_decision_by', 'exceptions', 'scope_limit', 'evidence_ref', 'url')):
        return None
    if not rule['url'].startswith('https://') or not CheckedFact(rule['evidence_ref'], rule['url'], rule.get('checked_at'), 'KNOWN').usable:
        return None
    rows = [('規定主体', rule['authority']), ('確認日', rule['checked_at']), ('最終確認と判断', rule['final_decision_by']), ('条件による違い', rule['exceptions']), ('この記事の範囲', rule['scope_limit'])]
    content = '<dl>' + ''.join('<div><dt>' + escape(label) + '</dt><dd>' + escape(value) + '</dd></div>' for label,value in rows) + '</dl>'
    content += '<p><a data-raos-cta-type="verify" href="' + escape(rule['url'], quote=True) + '">規定主体の公式案内で現在の条件を確認する</a></p>'
    return section('reader-rule-status', '適用条件と、最後に確認する場所', content, 'raos-rule-status')


def contextual_cta(kind: str, label: str, url: str, *, product_ref: str | None,
                   evidence: CtaEvidence, article_type: str, placement: str) -> str:
    if kind not in {'learn', 'verify', 'offer'} or (kind == 'offer' and placement not in {'product_detail', 'final_check'}):
        return ''
    if article_type not in {'shortlist', 'comparison', 'model_difference', 'status_check', 'safety_rule'}:
        return ''
    if not cta_visible(cast(CtaType, kind), url, product_ref, evidence, article_type=cast(ArticleType, article_type)):
        return ''
    rel = ' rel="sponsored nofollow noopener noreferrer"' if kind == 'offer' else ''
    return f'<a class="raos-contextual-cta" data-raos-cta-type="{kind}" href="{escape(url, quote=True)}"{rel}>{escape(label)}</a>'


def contextual_link(question: str, target: str, stage: str, *, existing_targets: frozenset[str]) -> Element | None:
    if target not in existing_targets or stage not in {'discover', 'learn', 'compare', 'verify', 'buy'}:
        return None
    return block(f'<p class="raos-contextual-related" data-journey-stage="{stage}"><a href="{escape(target, quote=True)}">{escape(question)}</a></p>')


def enhance_specification_tables(root: Element) -> None:
    for table in list(root.find(tag='table')):
        if table.has('raos-decision-table'):
            continue
        for cell in table.find(tag='td'):
            if cell.text().strip() in {'', 'UNKNOWN', '未確認', '不明'}:
                cell.attrs['data-raos-value-state'] = 'UNKNOWN'
                if not cell.text().strip():
                    cell.children = ['未確認（UNKNOWN）']
        heads = table.find(tag='thead')
        bodies = table.find(tag='tbody')
        if not heads or not bodies:
            continue
        header_rows = heads[0].find(tag='tr')
        rows = bodies[0].find(tag='tr')
        if not header_rows or len(rows) < 2:
            continue
        header = [c for c in header_rows[0].children if isinstance(c, Element)]
        cells = [[c for c in row.children if isinstance(c, Element)] for row in rows]
        if not header or any(len(row) != len(header) for row in cells):
            continue
        common = [i for i in range(1, len(header)) if len({row[i].text() for row in cells}) == 1 and not any(any(token in row[i].text() for token in ('UNKNOWN', '未確認', '不明')) for row in cells)]
        if not common:
            continue
        caption = table.find(tag='caption')
        title = caption[0].text() if caption else '確認した仕様'
        shared = block(f'<details class="raos-common-specifications"><summary>共通する仕様を確認する</summary><div class="comparison-table-wrap" role="region" tabindex="0" aria-label="共通仕様の表"><table><caption>{escape(title)}：共通する仕様</caption></table></div></details>')
        common_table = shared.find(tag='table')[0]
        identity_header = block(header[0].html())
        for node in identity_header.walk():
            node.attrs.pop('id', None)
        common_table.append(block('<thead><tr>' + identity_header.html() + ''.join(header[i].html() for i in common) + '</tr></thead>'))
        common_body = block('<tbody></tbody>')
        for row in cells:
            identity = block(row[0].html())
            for node in identity.walk():
                node.attrs.pop('id', None)
            for image in identity.find(tag='img'):
                image.remove()
            common_body.append(block('<tr>' + identity.html() + ''.join(row[i].html() for i in common) + '</tr>'))
        common_table.append(common_body)
        for row in [header, *cells]:
            for i in common:
                row[i].remove()
        # Insert outside the existing scroll region; keep every source note and ID.
        wrapper = table.parent
        while wrapper and wrapper.parent and not wrapper.has('comparison-table-wrap'):
            wrapper = wrapper.parent
        if wrapper and wrapper.parent:
            wrapper.parent.append(shared)


def _dimension_row(raw: object) -> tuple[str, float, float, float] | None:
    if not isinstance(raw, Mapping):
        return None
    raw = cast(Mapping[str, object], raw)
    values: list[float] = []
    for key in ('width_cm', 'depth_cm', 'height_cm'):
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if not math.isfinite(value) or value <= 0:
            return None
        values.append(float(value))
    return (str(raw.get('subject', '')).strip(), values[0], values[1], values[2])


def _axis_label(row: tuple[str, float, float, float]) -> str:
    return (
        f'W（幅）{row[1]:g}cm / D（奥行）{row[2]:g}cm / '
        f'H（高さ）{row[3]:g}cm'
    )


def _comparison_plan(
    rows: Sequence[tuple[str, float, float, float]],
    roles: Sequence[str],
    *,
    overlay: bool,
    alt: str,
) -> str:
    # HTML/CSS keeps the existing WordPress post allow-list unchanged.
    max_width = max(row[1] for row in rows)
    max_depth = max(row[2] for row in rows)
    available_width = 260 if overlay else 120
    scale = min(available_width / max_width, 150 / max_depth)
    shapes: list[str] = []
    for index, (row, role) in enumerate(zip(rows, roles, strict=True)):
        width = row[1] * scale
        depth = row[2] * scale
        x = (320 - width) / 2 if overlay else 20 + index * 160 + (120 - width) / 2
        y = 15 + (150 - depth) / 2
        shapes.append(
            '<span class="raos-dimension-diagram__shape" '
            f'data-raos-dimension-role="{escape(role, quote=True)}" '
            f'style="left:{x / 320 * 100:g}%;top:{y / 180 * 100:g}%;'
            f'width:{width / 320 * 100:g}%;height:{depth / 180 * 100:g}%"></span>'
        )
    return (
        '<div class="raos-dimension-diagram__comparison-plan" '
        f'role="img" aria-label="{escape(alt, quote=True)}">'
        + ''.join(reversed(shapes) if overlay else shapes)
        + '</div>'
    )


def _comparison_diagram(
    dimensions: Sequence[tuple[str, float, float, float]],
    asset: Mapping[str, object],
) -> tuple[str, str] | None:
    body = next((row for row in dimensions if '本体' in row[0]), None)
    station = next(
        (row for row in dimensions if any(token in row[0] for token in ('ステーション', '充電台', 'ドック', 'スタンド'))),
        None,
    )
    if station is not None:
        if body is None:
            return None
        rows = (body, station)
        labels = (('body', '本体'), ('station', 'ステーション'))
        unknown = (
            'この図には、設置に必要な前方・左右・上方の余白を含めていません。'
            '帰還経路と手入れの動線はメーカー公式で別に確認してください。'
        )
        plan = _comparison_plan(
            rows,
            tuple(role for role, _ in labels),
            overlay=False,
            alt=str(asset['alt']),
        )
    else:
        normal = next((row for row in dimensions if '通常' in row[0] or '非拡張' in row[0]), None)
        expanded = next((row for row in dimensions if '拡張' in row[0] and '非拡張' not in row[0]), None)
        if normal is None and expanded is None:
            return None
        if normal is None or expanded is None:
            return None
        rows = (normal, expanded)
        labels = (('normal', '通常時'), ('expanded', '拡張時'))
        unknown = (
            'この図には、ケースを開くための床面と左右の余白を含めていません。'
            '利用場所と持ち込み条件は別に確認してください。'
        )
        plan = _comparison_plan(
            rows,
            tuple(role for role, _ in labels),
            overlay=True,
            alt=str(asset['alt']),
        )
    live_labels = ''.join(
        '<div data-raos-dimension-label="' + escape(role, quote=True) + '"><dt>'
        + escape(label) + '</dt><dd>' + escape(_axis_label(row)) + '</dd></div>'
        for row, (role, label) in zip(rows, labels, strict=True)
    )
    return (
        plan + '<dl class="raos-dimension-diagram__labels">' + live_labels + '</dl>',
        unknown,
    )


def dimension_diagram(
    claim: Mapping[str, object],
    source: Mapping[str, object],
    asset: Mapping[str, object],
    *,
    product_ref: str | None = None,
    claim_refs: frozenset[str] | None = None,
) -> Element | None:
    """Draw only product-bound official dimensions; never infer clearance."""
    references = claim.get('evidence_refs')
    if not isinstance(references, list):
        return None
    if (not approved_media_record(asset) or asset.get('asset_type') != 'html_diagram'
        or asset.get('role') != 'dimension'
        or claim.get('classification') != 'MAJOR_VERIFIABLE' or claim.get('status') != 'BOUND_TO_OFFICIAL_SOURCE'
        or source.get('authority') != 'MANUFACTURER_OFFICIAL'
        or not CheckedFact(str(claim.get('claim_id', '')), str(source.get('source_ref', '')), cast(str | None, source.get('retrieved_on')), 'KNOWN').usable
        or source.get('url') != asset.get('source') or source.get('source_ref') not in references):
        return None
    if product_ref is not None:
        products = claim.get('subject_product_ids')
        if (
            claim_refs is None
            or claim.get('claim_id') not in claim_refs
            or not isinstance(products, list)
            or product_ref not in products
        ):
            return None
    dimensions = claim.get('dimensions')
    if not isinstance(dimensions, list) or not dimensions:
        return None
    dimensions = cast(list[object], dimensions)
    typed_dimensions = [_dimension_row(row) for row in dimensions]
    if any(row is None for row in typed_dimensions):
        return None
    rows = cast(list[tuple[str, float, float, float]], typed_dimensions)
    comparison = _comparison_diagram(rows, asset)
    comparison_tokens = ('ステーション', '充電台', 'ドック', 'スタンド', '通常', '非拡張', '拡張')
    if comparison is None and any(
        token in row[0] for row in rows for token in comparison_tokens
    ):
        return None
    identifier = escape(str(asset['asset_ref']), quote=True)
    metadata = (
        f'id="{identifier}" data-raos-media-state="approved" '
        f'data-raos-media-checked-at="{escape(str(asset["checked_at"]), quote=True)}" '
        f'data-source-ref="{escape(str(source["source_ref"]), quote=True)}" '
        f'data-claim-id="{escape(str(claim["claim_id"]), quote=True)}"'
    )
    if product_ref is not None:
        metadata += f' data-raos-product-id="{escape(product_ref, quote=True)}"'
    source_note = (
        '<p class="raos-dimension-source">'
        + (escape(str(asset['caption'])) if comparison is None else '')
        + ' <a data-raos-cta-type="verify" href="'
        + escape(str(asset['source']), quote=True)
        + '">メーカー公式で寸法条件を確認する</a>。公式情報確認：'
        + escape(str(source['retrieved_on']))
        + '</p>'
    )
    if comparison is not None:
        visual, unknown = comparison
        return block(
            f'<figure class="raos-dimension-diagram raos-dimension-diagram--comparison" {metadata}>'
            f'<figcaption><strong>{escape(str(asset["caption"]))}</strong></figcaption>'
            + visual
            + '<p class="raos-dimension-unknown" data-raos-value-state="UNKNOWN">'
            + escape(unknown)
            + '</p>'
            + source_note
            + '</figure>'
        )
    body = rows[0]
    width, depth, height = body[1:]
    opened = next((row for row in rows[1:] if any(token in row[0] for token in ('扉', 'ドア'))), None)
    door = f'扉を開いたときの奥行：{opened[2]:g}cm（本体を含む）。' if opened else '扉開放時の寸法：この記事で確認できた資料では未確認。取扱説明書で確認してください。'
    return block(
        f'<figure class="raos-dimension-diagram" {metadata}>'
        f'<figcaption><strong>{escape(body[0] or "本体寸法")}</strong></figcaption>'
        f'<div class="raos-dimension-diagram__plan" role="img" aria-label="{escape(str(asset["alt"]), quote=True)}" style="aspect-ratio:{width:g}/{depth:g}"><span>上から見た本体</span><span>幅 {width:g}cm × 奥行 {depth:g}cm</span></div>'
        f'<p>高さ：{height:g}cm。{escape(door)}</p>'
        '<p>上方・左右の余白、給水・排水ホース、電源への経路は別に確かめます。</p>'
        + source_note
        + '</figure>'
    )


def numerical_difference(left: str, right: str) -> str | None:
    """A derived difference between like official units, never a runtime guarantee."""
    pattern = r'^(約)?([0-9]+(?:\.[0-9]+)?)(Wh|W|kg)$'
    first, second = re.fullmatch(pattern, left), re.fullmatch(pattern, right)
    if not first or not second or first[3] != second[3]:
        return None
    base, target = float(first[2]), float(second[2])
    if base <= 0 or not math.isfinite(base) or not math.isfinite(target):
        return None
    delta = target - base
    approximation = '約' if first[1] or second[1] else ''
    return f'{approximation}{delta:+g}{first[3]}（{delta / base * 100:+.1f}%）'
