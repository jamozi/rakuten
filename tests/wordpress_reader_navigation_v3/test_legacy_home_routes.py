"""Offline contracts for homepage destinations referenced by older articles."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / 'changes/wordpress-direct-publish-v1/articles/home.html'


class Markup(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.nodes = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))


class LegacyHomeRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = HOME.read_text(encoding='utf-8')
        cls.nodes = Markup(cls.text).nodes

    def test_legacy_breadcrumb_destinations_are_real_category_cards(self):
        destinations = {'cluster-mobility': '/travel/',
                        'cluster-home': '/kitchen/',
                        'cluster-ready': '/preparedness/'}
        for ident, href in destinations.items():
            with self.subTest(ident=ident):
                matches = [(tag, attrs) for tag, attrs in self.nodes
                           if attrs.get('id') == ident]
                self.assertEqual(len(matches), 1)
                tag, attrs = matches[0]
                self.assertEqual(tag, 'a')
                self.assertEqual(attrs.get('href'), href)
                self.assertNotIn('hidden', attrs)
                self.assertNotIn('display:none', attrs.get('style', ''))
                self.assertIn('scroll-margin-top:24px', attrs.get('style', ''))

    def test_feature_cards_offer_three_distinct_reader_needs(self):
        links = [a.get('href') for tag, a in self.nodes
                 if tag == 'a' and a.get('class') == 'km-feature']
        self.assertCountEqual(links, ['/save-housework/', '/small-space/', '/easy-maintenance/'])

    def test_ids_are_unique(self):
        counts = Counter(a['id'] for _, a in self.nodes if 'id' in a)
        self.assertFalse([key for key, count in counts.items() if count != 1])

    def test_one_h1(self):
        self.assertEqual(sum(tag == 'h1' for tag, _ in self.nodes), 1)

    def test_four_image_categories_are_retained(self):
        for label in ('スーツケース', '食洗機', 'ロボット掃除機', 'ポータブル電源'):
            self.assertIn(label, self.text)
        for slug in ('travel', 'kitchen', 'cleaning', 'preparedness'):
            self.assertIn(f'href="/{slug}/"', self.text)
            self.assertIn(f'ks-{slug}-editorial-ai-20260910.webp', self.text)

    def test_ai_and_advertising_disclosures_are_retained(self):
        self.assertIn('カテゴリ画像はAI生成の編集イメージです。', self.text)
        self.assertIn('掲載順・評価は報酬条件と切り離しています。', self.text)

    def test_home_purchase_check_remains_reachable(self):
        self.assertIn('href="#home-purchase-check"', self.text)
        self.assertIn('id="home-purchase-check"', self.text)
        self.assertIn('選び方の3ステップ', self.text)

    def test_twelve_hosted_editorial_images_keep_dimensions(self):
        images = [attrs for tag, attrs in self.nodes if tag == 'img']
        self.assertEqual(len(images), 12)
        for image in images:
            self.assertTrue(image['src'].startswith('https://kurashinoshirube.com/wp-content/uploads/'))
            self.assertEqual((image.get('width'), image.get('height')), ('762', '506'))


if __name__ == '__main__':
    unittest.main()
