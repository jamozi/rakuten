"""Reusable reader decisions, evidence, uncertainty and checks as HTML fragments.

Product identity and facts are resolved by the existing editorial adapters. This
module renders editorial judgments separately and cannot make a provider call.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import cast

from raos.application.editorial.reader_html import Element, block
from raos.application.editorial.reader_experience_v1 import ArticleType, CtaType, CtaEvidence, cta_visible


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
    headings = ('条件', '候補', '選ぶ理由', '妥協点', '購入前の確認')
    keys = ('condition', 'product_name', 'reason', 'tradeoff', 'purchase_check')
    body = []
    for row in rows:
        cells = []
        for index, (label, key) in enumerate(zip(headings, keys, strict=True)):
            value = escape(row[key])
            if key == 'product_name':
                value = f'<a href="#{escape(row["anchor"], quote=True)}">{value}</a>'
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
