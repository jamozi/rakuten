"""Offline contracts for public editorial images and category navigation."""
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
ROOT = Path(__file__).resolve().parents[2]
DIRECT = ROOT / 'changes/wordpress-direct-publish-v1'

class Markup(HTMLParser):

    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.append(a['id'])
        if tag == 'a':
            self.links.append(a.get('href', ''))
        if tag == 'img':
            self.images.append(a)

class Visuals(unittest.TestCase):

    def manifest(self):
        return json.loads((DIRECT / 'reader-sync/visual-assets.v1.json').read_text())

    def test_four_distinct_images(self):
        assets = self.manifest()['assets']
        self.assertEqual(len(assets), 4)
        self.assertEqual(len({a['url'] for a in assets}), 4)

    def test_own_hosted_images(self):
        for a in self.manifest()['assets']:
            u = urlsplit(a['url'])
            self.assertEqual(u.scheme, 'https')
            self.assertEqual(u.netloc, 'kurashinoshirube.com')
            self.assertFalse(u.query)
            self.assertTrue(u.path.startswith('/wp-content/uploads/'))

    def test_not_product_evidence(self):
        for a in self.manifest()['assets']:
            self.assertEqual(a['purpose'], 'editorial_illustration')
            self.assertFalse(a['product_evidence'])
            self.assertIn('AI', a['caption'])
            self.assertEqual(a['width'], 762)
            self.assertEqual(a['height'], 506)

    def test_all_articles_mapped(self):
        ids = [p for a in self.manifest()['assets'] for p in a['article_post_ids']]
        self.assertEqual(len(ids), 15)
        self.assertEqual(len(set(ids)), 15)

    def test_all_four_sources_have_images(self):
        for a in self.manifest()['assets']:
            html = (DIRECT / 'articles' / f"{a['category']}.html").read_text()
            m = Markup()
            m.feed(html)
            self.assertTrue(any((i['src'] == a['url'] for i in m.images)))
            self.assertIn(a['caption'], html)

    def test_sources_do_not_restore_empty_shortcodes(self):
        for a in self.manifest()['assets']:
            html = (DIRECT / 'articles' / f"{a['category']}.html").read_text()
            self.assertNotIn('[kurashinoshirube_reader_hub', html)

    def test_ids_and_anchors(self):
        for a in self.manifest()['assets']:
            m = Markup()
            m.feed((DIRECT / 'articles' / f"{a['category']}.html").read_text())
            self.assertEqual(len(m.ids), len(set(m.ids)))
            for href in m.links:
                if href.startswith('#'):
                    self.assertIn(href[1:], m.ids)

    def test_no_tracking_or_temp_credentials(self):
        for slug in ('home', 'travel', 'kitchen', 'cleaning', 'preparedness'):
            raw = (DIRECT / 'articles' / f'{slug}.html').read_text()
            for bad in ('X-Amz-Signature', 'firestorage.ai', 'hb.afl.rakuten', 'rafcid=', 'sk-proj-'):
                self.assertNotIn(bad, raw)

    def test_home_keeps_purchase_target(self):
        html = (DIRECT / 'articles/home.html').read_text()
        self.assertIn('href="#home-purchase-check"', html)
        self.assertIn('id="home-purchase-check"', html)
        self.assertIn('id="ks-visual-categories"', html)

    def test_actual_dimensions_not_upscaled_claim(self):
        for a in self.manifest()['assets']:
            self.assertEqual(a['source_crop_size'], [762, 506])
            self.assertFalse(a['upscaled'])
if __name__ == '__main__':
    unittest.main()
