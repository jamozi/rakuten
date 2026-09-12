"""Synthetic fixtures only: no live merchant links or account identifiers."""
import copy
import json
from pathlib import Path
import unittest
from scripts.raos_reader_live_patch import PatchFailure, apply_patch
ROOT = Path(__file__).resolve().parents[2]
ANKER_RECIPE = ROOT / 'changes/wordpress-direct-publish-v1/articles/anker-solix-c300-c800-c1000-differences.patch.json'
ANKER_OLD_REASON = '<p><strong>おすすめする理由：</strong>C1000より約1.6kg軽い約11.3kgで、定格出力が50W高いためです。</p>'
ANKER_NEW_REASON = '<p><strong>おすすめする理由：</strong>公表本体重量はC1000より約1.6kg軽い約11.3kgです。拡張バッテリーが不要で、重量とUSB-C端子数を重視する人に向きます。</p>'
ANKER_OLD_SUMMARY = '<small>C1000系で重量と出力を優先</small>'
ANKER_NEW_SUMMARY = '<small>C1000系で重量とUSB-C端子数を優先</small>'
ANKER_MISMATCH_NOTE = '<p>公表定格出力の差は50W前後で、出力の優位は未確定です。</p>'
BODY = '<div class="raos-editorial-v2"><section id="table"><h2>比較表</h2></section><article data-raos-product-id="DEMO"><a href="https://merchant.invalid/item" rel="sponsored nofollow" data-raos-placement="product_card">販売条件</a></article><p>確認日：2026年8月23日</p><section id="sources">出典</section></div>'
PATCH = {'schema': 'RAOSReaderLivePatchV1', 'article_key': 'demo', 'post_id': 99, 'required_ids': ['table', 'sources'], 'required_product_ids': ['DEMO'], 'nav_html': '<nav id="ks-article-nav"><a href="/travel/">カテゴリ</a><a href="#table">比較表へ</a></nav>', 'next_html': '<section id="ks-next-read"><h2 id="ks-next-read-title">次の確認</h2><a href="/travel/">選び方へ</a></section>', 'replacements': []}

class LivePatchTests(unittest.TestCase):

    def apply(self, body=BODY, patch=None):
        return apply_patch(body, PATCH if patch is None else patch, article_key='demo', post_id=99)

    def test_keeps_merchant_and_dates(self):
        output = self.apply()
        self.assertIn('href="https://merchant.invalid/item" rel="sponsored nofollow" data-raos-placement="product_card"', output)
        self.assertIn('確認日：2026年8月23日', output)

    def test_idempotent(self):
        once = self.apply()
        self.assertEqual(once, self.apply(once))
        self.assertEqual(once.count('id="ks-article-nav"'), 1)

    def test_wrong_article_rejected(self):
        with self.assertRaises(PatchFailure):
            apply_patch(BODY, PATCH, article_key='other', post_id=99)

    def test_wrong_id_rejected(self):
        with self.assertRaises(PatchFailure):
            apply_patch(BODY, PATCH, article_key='demo', post_id=100)

    def test_wrong_models_rejected(self):
        with self.assertRaises(PatchFailure):
            self.apply(BODY.replace('"DEMO"', '"OTHER"'))

    def test_missing_source_anchor_rejected(self):
        with self.assertRaises(PatchFailure):
            self.apply(BODY.replace('id="sources"', 'id="different"'))

    def test_duplicate_id_rejected(self):
        with self.assertRaises(PatchFailure):
            self.apply(BODY.replace('</div>', '<p id="table">dup</p></div>'))

    def test_new_script_rejected(self):
        p = copy.deepcopy(PATCH)
        p['nav_html'] = '<nav id="ks-article-nav"><script>alert(1)</script></nav>'
        with self.assertRaises(PatchFailure):
            self.apply(patch=p)

    def test_external_new_link_rejected(self):
        p = copy.deepcopy(PATCH)
        p['nav_html'] = '<nav id="ks-article-nav"><a href="https://unrelated.invalid/">bad</a></nav>'
        with self.assertRaises(PatchFailure):
            self.apply(patch=p)

    def test_missing_fragment_rejected(self):
        p = copy.deepcopy(PATCH)
        p['nav_html'] = '<nav id="ks-article-nav"><a href="#absent">bad</a></nav>'
        with self.assertRaises(PatchFailure):
            self.apply(patch=p)

    def test_replacement_is_repeatable(self):
        p = copy.deepcopy(PATCH)
        p['replacements'] = [{'old': '比較表', 'new': '仕様比較', 'max_count': 1}]
        once = self.apply(patch=p)
        self.assertEqual(once, self.apply(once, p))
        self.assertIn('仕様比較', once)

    def test_mismatched_edit_is_not_silently_ignored(self):
        p = copy.deepcopy(PATCH)
        p['replacements'] = [{'old': 'not-present', 'new': 'also-not-present', 'max_count': 1}]
        with self.assertRaises(PatchFailure):
            self.apply(patch=p)

    def test_merchant_mutation_rejected(self):
        p = copy.deepcopy(PATCH)
        p['replacements'] = [{'old': 'https://merchant.invalid/item', 'new': 'https://evil.invalid', 'max_count': 1}]
        with self.assertRaises(PatchFailure):
            self.apply(patch=p)

    def anker_body(self, reason=ANKER_OLD_REASON, summary=ANKER_OLD_SUMMARY):
        return BODY.replace('<h2>比較表</h2>', '<h2>比較表</h2>' + reason + summary + ANKER_MISMATCH_NOTE)

    def anker_patch(self):
        p = copy.deepcopy(PATCH)
        p['replacements'] = json.loads(ANKER_RECIPE.read_text())['replacements']
        return p

    def test_anker_gen2_reason_is_replaced_once_and_the_rest_is_kept(self):
        body = self.anker_body()
        untouched = self.apply(body)
        self.assertIn(ANKER_OLD_REASON, untouched)
        self.assertIn(ANKER_OLD_SUMMARY, untouched)
        once = self.apply(body, self.anker_patch())
        self.assertIn(ANKER_NEW_REASON, once)
        self.assertIn(ANKER_NEW_SUMMARY, once)
        self.assertNotIn('定格出力が50W高いためです', once)
        self.assertNotIn(ANKER_OLD_SUMMARY, once)
        self.assertIn(ANKER_MISMATCH_NOTE, once)
        self.assertIn('href="https://merchant.invalid/item" rel="sponsored nofollow" data-raos-placement="product_card"', once)
        self.assertIn('確認日：2026年8月23日', once)
        self.assertEqual(once, self.apply(once, self.anker_patch()))

    def test_anker_recipe_is_satisfied_when_only_the_new_sentences_exist(self):
        body = self.anker_body(ANKER_NEW_REASON, ANKER_NEW_SUMMARY)
        self.assertEqual(self.apply(body, self.anker_patch()), self.apply(body))

    def test_exclusive_replacement_stops_on_a_mixed_document(self):
        body = self.anker_body().replace(ANKER_MISMATCH_NOTE, ANKER_NEW_SUMMARY + ANKER_MISMATCH_NOTE)
        with self.assertRaises(PatchFailure) as failure:
            self.apply(body, self.anker_patch())
        self.assertEqual(str(failure.exception), 'REPLACEMENT_MIXED_STATE')

    def test_replacement_with_several_matches_is_rejected(self):
        body = self.anker_body().replace(ANKER_MISMATCH_NOTE, ANKER_OLD_SUMMARY + ANKER_MISMATCH_NOTE)
        with self.assertRaises(PatchFailure) as failure:
            self.apply(body, self.anker_patch())
        self.assertEqual(str(failure.exception), 'REPLACEMENT_COUNT_MISMATCH')

    def test_replacement_markup_and_overlap_are_rejected(self):
        p = copy.deepcopy(PATCH)
        p['replacements'] = [{'old': '<h2>比較表</h2>', 'new': '<h2>仕様比較</h2>', 'max_count': 1}]
        with self.assertRaises(PatchFailure) as failure:
            self.apply(patch=p)
        self.assertEqual(str(failure.exception), 'REPLACEMENT_MARKUP_FORBIDDEN')
        p['replacements'] = [{'old': '比較表', 'new': '比較表と条件', 'max_count': 1, 'exclusive': True}]
        with self.assertRaises(PatchFailure) as failure:
            self.apply(patch=p)
        self.assertEqual(str(failure.exception), 'REPLACEMENT_INVALID')
        p['replacements'] = [{'old': '比較表', 'new': '仕様比較', 'max_count': 1, 'exclusive': 'yes'}]
        with self.assertRaises(PatchFailure):
            self.apply(patch=p)

    def test_hero_kept_neutral_removed(self):
        b = BODY.replace('<section id="table">', '<figure class="hero-photo"><img src="/scene.webp" alt="イメージ"></figure><figure><img src="/fake.webp" data-raos-product-image-state="neutral"></figure><section id="table">')
        o = self.apply(b)
        self.assertIn('/scene.webp', o)
        self.assertNotIn('/fake.webp', o)
        self.assertNotIn('<figure></figure>', o)

    def test_void_elements_supported(self):
        b = BODY.replace('出典</section>', '出典<br><img src="/real.png" data-raos-product-image-state="verified"></section>')
        self.assertIn('/real.png', self.apply(b))

    def test_empty_baseline_rejected(self):
        with self.assertRaises(PatchFailure):
            self.apply('')

    def test_unavailable_purchase_keeps_product_and_other_links(self):
        body = BODY.replace('https://merchant.invalid/item', 'https://hb.afl.rakuten.co.jp/synthetic')
        patch = copy.deepcopy(PATCH)
        patch['unavailable_purchase_product_ids'] = ['DEMO']
        output = self.apply(body, patch)
        self.assertNotIn('href="https://hb.afl.rakuten.co.jp/synthetic"', output)
        self.assertIn('data-raos-product-id="DEMO"', output)
        self.assertIn('販売先を確認できないため', output)
        self.assertIn('確認日：2026年8月23日', output)
        self.assertEqual(output, self.apply(output, patch))

    def test_unavailable_purchase_does_not_remove_manufacturer_evidence(self):
        patch = copy.deepcopy(PATCH)
        patch['unavailable_purchase_product_ids'] = ['DEMO']
        with self.assertRaises(PatchFailure):
            self.apply(BODY, patch)

class StyleTests(unittest.TestCase):

    def test_generated_styles_survive_wordpress_safe_css(self):
        from scripts.raos_reader_live_patch import Document, inline_reader_styles
        body = '<section class="ks-reader-start"><p class="ks-reader-ad-note">広告を含みます</p><div class="ks-route-grid"><article>案内</article></div></section>'
        result = inline_reader_styles(body)
        for node in Document(result).nodes:
            css = node.attrs.get('style') or ''
            self.assertFalse(css.endswith(';'))
            self.assertNotIn('box-sizing:', css)
            self.assertNotIn('overflow-wrap:', css)

    def test_reader_style_survives_without_additional_css(self):
        from scripts.raos_reader_live_patch import inline_reader_styles
        body = '<section class="ks-reader-start"><div class="ks-route-grid"><article>案内</article></div></section>'
        result = inline_reader_styles(body)
        self.assertIn('flex-wrap:wrap', result)
        self.assertIn('line-height:1.85', result)
        self.assertEqual(inline_reader_styles(result), result)

    def test_style_does_not_change_merchant_link(self):
        from scripts.raos_reader_live_patch import inline_reader_styles
        self.assertIn('href="https://merchant.invalid/item" rel="sponsored nofollow"', inline_reader_styles(BODY))
if __name__ == '__main__':
    unittest.main()
