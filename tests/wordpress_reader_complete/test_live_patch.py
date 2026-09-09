"""Synthetic fixtures only: no live merchant links or account identifiers."""
import copy
import unittest
from scripts.raos_reader_live_patch import PatchFailure, apply_patch
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
