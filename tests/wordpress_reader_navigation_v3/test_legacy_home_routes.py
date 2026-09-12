"""Offline contracts for homepage destinations referenced by older articles."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / 'changes/wordpress-direct-publish-v1/articles/home.html'
HOME_CSS = (ROOT / 'changes/st-1704/self-hosted-editorial-pilot-v1/theme'
            / 'kurashinoshirube-child/assets/home-magazine.css')
HERO_IMAGE = ('https://kurashinoshirube.com/wp-content/themes/kurashinoshirube-child'
              '/assets/images/magazine-hero.webp')


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
                # KSES drops scroll-margin-top from inline style on save (2026-09-12 audit T-02),
                # so the offset lives in the home stylesheet instead of the markup.
                self.assertNotIn('scroll-margin-top', attrs.get('style', ''))
        css = HOME_CSS.read_text(encoding='utf-8')
        self.assertIn('#cluster-mobility,#cluster-home,#cluster-ready{scroll-margin-top:24px;}', css)

    def test_feature_cards_link_every_purpose_hub_once(self):
        # 2026-09-12 audit T-19 / CH-01: all six purpose hubs need a home entry.
        links = [a.get('href') for tag, a in self.nodes
                 if tag == 'a' and a.get('class') == 'km-feature']
        self.assertCountEqual(links, ['/save-housework/', '/small-space/', '/easy-maintenance/',
                                      '/comfortable-travel/', '/without-installation/', '/prepare-outage/'])

    def test_hero_heading_is_not_wrapped_in_a_link_and_links_to_articles(self):
        # 2026-09-12 audit CH-08: h1 outside <a>, hero buttons go to articles.
        self.assertNotIn('<a href="/categories/"><span class="km-tag">', self.text)
        hero = self.text.split('<h1 id="km-hero-title">', 1)[1].split('</nav>', 1)[0]
        hrefs = Markup(hero).nodes
        hrefs = [a['href'] for tag, a in hrefs if tag == 'a']
        self.assertEqual(hrefs, ['/lightweight-carry-on-suitcase-under-3kg/',
                                 '/countertop-dishwasher-for-small-households/',
                                 '/compact-robot-vacuum-shortlist/',
                                 '/portable-power-station-guide/'])

    def test_every_published_article_is_linked_directly(self):
        # 2026-09-12 audit T-19: 15 articles reachable from the home in one click.
        hrefs = {a.get('href') for tag, a in self.nodes if tag == 'a'}
        for slug in ('carry-on-suitcase-under-100-seats', 'lightweight-carry-on-suitcase-under-3kg',
                     'front-open-carry-on-suitcase-with-stopper', 'carry-on-suitcase-comparison',
                     'dishwasher-installation-measurement', 'dishwasher-water-supply-methods',
                     'countertop-dishwasher-for-small-households', 'solota-vs-rakua-mini-plus',
                     'dishwasher-running-cost', 'dishwasher-detergent-guide', 'dishwasher-cleaning-guide',
                     'compact-robot-vacuum-shortlist', 'roomba-mini-vs-switchbot-k11-pro',
                     'portable-power-station-guide', 'anker-solix-c300-c800-c1000-differences'):
            self.assertIn(f'/{slug}/', hrefs)

    def test_headings_are_japanese_and_do_not_skip_levels(self):
        # 2026-09-12 audit CH-10 / T-25: h1 -> h2 -> h3, no English h2.
        levels = [int(tag[1]) for tag, _ in self.nodes if tag in ('h1', 'h2', 'h3')]
        self.assertEqual(levels[0], 1)
        for previous, current in zip(levels, levels[1:]):
            self.assertLessEqual(current - previous, 1)
        h2_texts = re.findall(r'<h2[^>]*>(.*?)</h2>', self.text)
        for h2 in h2_texts:
            self.assertRegex(h2, r'[\u3040-\u30ff\u4e00-\u9fff]')

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

    def test_twelve_hosted_editorial_images_keep_dimensions_plus_hero(self):
        # 2026-09-12 audit T-16: the hero became an <img> (LCP candidate discoverable from
        # the markup) so the count is 12 uploads images plus the theme hero image.
        images = [attrs for tag, attrs in self.nodes if tag == 'img']
        self.assertEqual(len(images), 13)
        self.assertEqual(images[0]['src'], HERO_IMAGE)
        self.assertEqual((images[0].get('width'), images[0].get('height')), ('842', '495'))
        self.assertNotIn('loading', images[0])
        for image in images[1:]:
            self.assertTrue(image['src'].startswith('https://kurashinoshirube.com/wp-content/uploads/'))
            self.assertEqual((image.get('width'), image.get('height')), ('762', '506'))
            self.assertTrue(image.get('alt'), image['src'])


if __name__ == '__main__':
    unittest.main()
