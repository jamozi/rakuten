"""Local source graph checks. HTTP/browser verification is separate evidence."""
import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit
from scripts.raos_reader_live_patch import Document, inline_reader_styles
ROOT = Path(__file__).resolve().parents[2]
DIRECT = ROOT / 'changes/wordpress-direct-publish-v1'

class SiteSourceTests(unittest.TestCase):

    def setUp(self):
        self.registry = json.loads((DIRECT / 'articles.v1.json').read_text())['articles']
        self.site = json.loads((DIRECT / 'reader-sync/site-map.v2.json').read_text())
        self.pages = {p['slug']: Document((DIRECT / 'articles' / (p['slug'] + '.html')).read_text()) for p in self.site['pages']}

    def test_all_existing_targets_have_one_source(self):
        self.assertEqual(len(self.registry), 31)
        self.assertEqual(len({r['post_id'] for r in self.registry}), 31)
        for row in self.registry:
            self.assertEqual(row['mode'], 'existing')
            self.assertNotEqual(bool(row.get('body_source')), bool(row.get('patch_source')))
            if row['article_key'] != 'home':
                self.assertTrue((ROOT / (row.get('body_source') or row['patch_source'])).is_file())

    def test_directories_do_not_depend_on_empty_shortcode(self):
        for slug, doc in self.pages.items():
            with self.subTest(slug=slug):
                self.assertNotIn('[kurashinoshirube_reader_hub', doc.text)
                self.assertNotIn('現在、条件に合う公開記事はありません', doc.text)
                self.assertTrue(any((n.tag == 'a' for n in doc.nodes)))

    def test_each_article_is_directly_reachable_from_category(self):
        for article in self.site['articles']:
            hrefs = {n.attrs.get('href') for n in self.pages[article['category']].nodes if n.tag == 'a'}
            self.assertIn('/' + article['slug'] + '/', hrefs)

    def test_all_source_routes_and_same_page_fragments_resolve(self):
        routes = {'/', '/comparison-policy/', '/about-ad-policy/'}
        routes |= {'/' + r['slug'] + '/' for r in self.registry}
        for slug, doc in self.pages.items():
            for node in doc.nodes:
                if node.tag != 'a':
                    continue
                href = node.attrs.get('href') or ''
                parsed = urlsplit(href)
                self.assertFalse(parsed.scheme or parsed.netloc)
                if parsed.path:
                    self.assertIn(parsed.path, routes)
                target = self.pages.get(parsed.path.strip('/')) if parsed.path else doc
                if parsed.fragment and target:
                    self.assertIn(parsed.fragment, target.ids)

    def test_article_recipes_preserve_richer_existing_sections(self):
        rows = [r for r in self.registry if r.get('patch_source')]
        self.assertEqual(len(rows), 15)
        for row in rows:
            recipe = json.loads((ROOT / row['patch_source']).read_text())
            self.assertEqual(recipe['article_key'], row['article_key'])
            self.assertEqual(recipe['post_id'], row['post_id'])
            self.assertTrue(recipe['keep_existing_fragments'])
            self.assertGreaterEqual(len(recipe['required_ids']), 2)
            for field in ('nav_html', 'next_html'):
                for node in Document(recipe[field]).nodes:
                    if node.tag == 'a':
                        href = node.attrs.get('href', '')
                        self.assertTrue(href.startswith(('/', '#')) and (not href.startswith('//')))

    def test_sources_do_not_contain_merchant_tracking_values(self):
        for path in (DIRECT / 'articles').glob('*'):
            if path.stem == 'home':
                continue
            text = path.read_text()
            for forbidden in ('hb.afl.rakuten.co.jp', 'rafcid=', 'sk-proj-'):
                self.assertNotIn(forbidden, text)

    def test_reader_styles_can_be_applied_without_losing_images(self):
        for slug, doc in self.pages.items():
            with self.subTest(slug=slug):
                styled = inline_reader_styles(doc.text)
                self.assertEqual(inline_reader_styles(styled), styled)
                before_images = [n.attrs for n in doc.nodes if n.tag == 'img']
                after_images = [n.attrs for n in Document(styled).nodes if n.tag == 'img']
                self.assertEqual(before_images, after_images)
                self.assertIn('data-ks-inline-style="v1"', styled)
if __name__ == '__main__':
    unittest.main()
