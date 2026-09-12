"""Reviewed copy can grow without giving recipes control of merchant attributes."""
import copy

import pytest

from scripts.raos_reader_live_patch import PatchFailure, apply_patch

BODY = '<div class="raos-editorial-v2"><section><header><h2 id="decision">比較</h2></header><p>旧説明</p></section><article data-raos-product-id="DEMO"><a href="https://merchant.invalid/item">購入</a></article><p>2026年8月23日</p><section id="sources">出典</section></div>'
PATCH = {
    'schema': 'RAOSReaderLivePatchV1', 'article_key': 'demo', 'post_id': 99,
    'required_ids': ['decision', 'sources'], 'required_product_ids': ['DEMO'],
    'text_edits': [{'old': '旧説明', 'new': '旧説明を補足した説明'}],
    'editorial_additions': [{
        'id': 'detail', 'target_id': 'decision', 'position': 'before_section',
        'html': '<section id="detail"><p>2026年9月10日確認</p><a href="https://maker.invalid/spec">出典</a></section>',
        'sources': [{'url': 'https://maker.invalid/spec', 'checked_on': '2026-09-10', 'locator': '仕様表'}],
    }],
}


def apply(body=BODY, patch=None):
    return apply_patch(body, PATCH if patch is None else patch, article_key='demo', post_id=99)


def test_text_is_exact_and_addition_is_idempotent_with_original_links_and_dates():
    once = apply()
    assert apply(once) == once
    assert '<a href="https://merchant.invalid/item">' in once
    assert '2026年8月23日' in once
    assert once.index('id="detail"') < once.index('id="decision"')
    assert once.count('旧説明を補足した説明') == 1


@pytest.mark.parametrize('old,new', [
    ('https://merchant.invalid/item', 'https://other.invalid/item'),
    ('2026年8月23日', '2026年9月10日'),
    ('旧説明', '<img src="https://other.invalid/image">'),
])
def test_text_cannot_edit_attributes_dates_or_inject_markup(old, new):
    patch = copy.deepcopy(PATCH)
    patch['text_edits'] = [{'old': old, 'new': new}]
    with pytest.raises(PatchFailure):
        apply(patch=patch)


@pytest.mark.parametrize('html', [
    '<section id="detail"><script>alert(1)</script></section>',
    '<section id="detail" onclick="alert(1)">説明</section>',
    '<section id="detail"><a href="https://other.invalid/">未指定</a></section>',
    '<section id="detail"><img src="https://maker.invalid/image"></section>',
    '<section id="detail" data-raos-product-id="OTHER">説明</section>',
    '<section id="detail"><a href="https://maker.invalid/spec" rel="sponsored">広告</a></section>',
])
def test_additions_reject_execution_media_products_and_unreviewed_links(html):
    patch = copy.deepcopy(PATCH)
    patch['editorial_additions'][0]['html'] = html
    with pytest.raises(PatchFailure):
        apply(patch=patch)


def test_changed_existing_addition_and_missing_target_are_rejected():
    with pytest.raises(PatchFailure, match='EDITORIAL_ADDITION_DRIFT'):
        apply(apply().replace('2026年9月10日確認', '変更済み'))
    patch = copy.deepcopy(PATCH)
    patch['editorial_additions'][0]['target_id'] = 'missing'
    with pytest.raises(PatchFailure, match='EDITORIAL_TARGET_INVALID'):
        apply(patch=patch)


def test_after_header_placement_and_missing_source_evidence():
    patch = copy.deepcopy(PATCH)
    patch['editorial_additions'][0]['position'] = 'after_header'
    once = apply(patch=patch)
    assert once.index('</header>') < once.index('id="detail"') < once.index('旧説明を補足した説明')
    patch['editorial_additions'][0]['sources'][0]['checked_on'] = None
    with pytest.raises(PatchFailure, match='EDITORIAL_SOURCE_INVALID'):
        apply(patch=patch)
