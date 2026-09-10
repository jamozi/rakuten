"""Offline regression checks for published reader-copy source handoff."""
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRECT = ROOT / 'changes/wordpress-direct-publish-v1'
GUIDES = {'dishwasher-installation-measurement': 262, 'dishwasher-water-supply-methods': 263,
          'dishwasher-detergent-guide': 264, 'dishwasher-cleaning-guide': 265,
          'dishwasher-running-cost': 266}
HUBS = {'travel': 142, 'kitchen': 136, 'cleaning': 131, 'preparedness': 138}
DIRECTORIES = {'categories': 130, 'guides': 135, 'comparisons': 133, 'purposes': 139,
               'updates': 143, 'small-space': 141, 'save-housework': 140,
               'without-installation': 144, 'easy-maintenance': 134,
               'comfortable-travel': 132, 'prepare-outage': 137}

class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.hrefs = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.hrefs.append(attrs['href'])

class ReaderSources(unittest.TestCase):
    def registry(self):
        data = json.loads((DIRECT / 'articles.v1.json').read_text())
        self.assertEqual(data['schema'], 'RAOSOwnerDirectArticlesV1')
        self.assertEqual(data['profile'], 'owner-direct-v1')
        return {row['article_key']: row for row in data['articles']}
    def test_published_guides_are_existing_ids(self):
        rows = self.registry()
        for slug, post_id in GUIDES.items():
            with self.subTest(slug=slug):
                self.assertEqual(rows[slug]['mode'], 'existing')
                self.assertEqual(rows[slug]['post_id'], post_id)
    def test_four_hubs_are_editable_existing_pages(self):
        rows = self.registry()
        for slug, post_id in HUBS.items():
            with self.subTest(slug=slug):
                self.assertEqual(rows[slug]['post_type'], 'page')
                self.assertEqual(rows[slug]['post_id'], post_id)
                self.assertEqual(rows[slug]['mode'], 'existing')
                html = (ROOT / rows[slug]['body_source']).read_text()
                self.assertNotIn('[kurashinoshirube_reader_hub', html)
                self.assertIn('id="ks-visual-' + slug + '"', html)
                self.assertIn('id="purchase-checks"', html)
    def test_all_directories_have_existing_targets(self):
        rows = self.registry()
        for slug, post_id in DIRECTORIES.items():
            self.assertEqual(rows[slug]['post_id'], post_id)
            self.assertEqual(rows[slug]['mode'], 'existing')
            html = (ROOT / rows[slug]['body_source']).read_text()
            self.assertNotIn('[kurashinoshirube_reader_hub', html)
            self.assertIn('<a href=', html)
    def test_home_purchase_route_has_a_real_target(self):
        html = (DIRECT / 'articles/home.html').read_text()
        self.assertIn('href="#home-purchase-check"', html)
        self.assertIn('id="home-purchase-check"', html)
        self.assertNotIn('href="/updates/"><div class="km-guide-copy"><span class="km-eyebrow">STEP 3', html)
    def test_new_sources_have_unique_ids_and_local_anchors(self):
        for slug in ('home', *HUBS, *DIRECTORIES):
            with self.subTest(slug=slug):
                parsed = Markup()
                parsed.feed((DIRECT / f'articles/{slug}.html').read_text())
                self.assertEqual(len(parsed.ids), len(set(parsed.ids)))
                for href in parsed.hrefs:
                    if href.startswith('#'):
                        self.assertIn(href[1:], parsed.ids)
    def test_copy_and_css_do_not_contain_affiliate_tokens(self):
        paths = [DIRECT / f'articles/{s}.html' for s in ('home', *HUBS, *DIRECTORIES)]
        paths.append(DIRECT / 'reader-sync/additional-css.css')
        for path in paths:
            text = path.read_text()
            for token in ('hb.afl.rakuten.co.jp', 'rafcid=', 'sk-proj-', 'application_password'):
                self.assertNotIn(token, text)
    def test_text_only_cards_use_full_card_width(self):
        css = (DIRECT / 'reader-sync/additional-css.css').read_text()
        self.assertIn('#ks-magazine .km-decision-path .km-guide', css)
        self.assertIn('display: block', css)
    def test_travel_shortcut_does_not_depend_on_generated_anchor(self):
        html = (DIRECT / 'articles/travel.html').read_text()
        self.assertIn('id="travel-comparisons"', html)
        self.assertIn('href="#compare"', html)
        self.assertIn('id="compare"', html)
        self.assertNotIn('href="#journey-comparison"', html)
    def test_article_fragments_are_not_publication_documents(self):
        data = json.loads((DIRECT / 'reader-sync/article-fragments.v1.json').read_text())
        self.assertIs(data['publication_authority'], False)
        self.assertEqual(data['status'], 'CAPTURED_NOT_WIRED_TO_PUBLICATION')
        self.assertEqual({row['post_id'] for row in data['articles']}, {83, 41, 30, 28, 86})
        for row in data['articles']:
            parsed = Markup()
            parsed.feed(row['html'])
            self.assertEqual(parsed.ids.count(row['marker_id']), 1)
            self.assertTrue(row['required_live_models'])
            if row['post_id'] == 86:
                self.assertEqual(row['before_html'], '')
            else:
                self.assertIn('広告', row['before_html'])
    def test_article_fragments_have_no_external_or_executable_links(self):
        data = json.loads((DIRECT / 'reader-sync/article-fragments.v1.json').read_text())
        for row in data['articles']:
            for field in ('html', 'before_html', 'related_section_html'):
                text = row.get(field, '')
                parsed = Markup()
                parsed.feed(text)
                for href in parsed.hrefs:
                    self.assertTrue(href.startswith(('/', '#')))
                    self.assertFalse(href.startswith('//'))
                for token in ('<script', '<iframe', '<form', 'rafcid=', 'hb.afl.rakuten.co.jp'):
                    self.assertNotIn(token, text.lower())

if __name__ == '__main__':
    unittest.main()
