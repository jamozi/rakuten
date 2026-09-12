"""Offline contracts for the 14 static hub pages after the 2026-09-12 site audit.

Covers CH-01 (purpose hub body), CH-05 (guides vs comparisons), CH-07 (blurbs per hub),
CH-12 (PR badge per affiliate article), CH-13 (breadcrumb nav). kitchen.html is a
generated page owned by the purchase-support renderer and is checked only loosely.
"""
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
ARTICLES = ROOT / 'changes/wordpress-direct-publish-v1/articles'
CORE = ('categories', 'purposes', 'guides', 'comparisons', 'updates')
CATEGORY = ('travel', 'cleaning', 'preparedness')
PURPOSE = ('small-space', 'save-housework', 'without-installation', 'easy-maintenance',
           'comfortable-travel', 'prepare-outage')
HUBS = CORE + CATEGORY + PURPOSE
# Articles whose live body carries affiliate links (site audit 2026-09-12, REPORT section 5).
AFFILIATE = {'carry-on-suitcase-comparison', 'carry-on-suitcase-under-100-seats',
             'lightweight-carry-on-suitcase-under-3kg', 'front-open-carry-on-suitcase-with-stopper',
             'countertop-dishwasher-for-small-households', 'compact-robot-vacuum-shortlist',
             'roomba-mini-vs-switchbot-k11-pro', 'portable-power-station-guide',
             'anker-solix-c300-c800-c1000-differences'}
NO_AFFILIATE = {'solota-vs-rakua-mini-plus', 'dishwasher-installation-measurement',
                'dishwasher-water-supply-methods', 'dishwasher-detergent-guide',
                'dishwasher-cleaning-guide', 'dishwasher-running-cost'}
PARENT = {**{slug: None for slug in CORE}, **{slug: 'categories' for slug in CATEGORY},
          **{slug: 'purposes' for slug in PURPOSE}}


class Text(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.chunks = []
        self.feed(html)

    def handle_data(self, data):
        self.chunks.append(data)


def visible_chars(html):
    return len(re.sub(r'\s+', '', ''.join(Text(html).chunks)))


class HubContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = {slug: (ARTICLES / f'{slug}.html').read_text(encoding='utf-8') for slug in HUBS}
        rows = json.loads((ROOT / 'changes/wordpress-direct-publish-v1/articles.v1.json').read_text())['articles']
        cls.title = {row['slug']: row['title'] for row in rows}

    def test_breadcrumb_nav_is_uniform_and_marks_the_current_page(self):
        for slug in HUBS:
            with self.subTest(slug=slug):
                html = self.html[slug]
                nav = re.search(r'<nav aria-label="このサイトの入口">(.*?)</nav>', html).group(1)
                crumbs = re.findall(r'<a href="([^"]+)">([^<]+)</a>', nav)
                self.assertEqual(crumbs[0], ('/', 'ホーム'))
                if PARENT[slug]:
                    self.assertEqual(crumbs[1], (f'/{PARENT[slug]}/', self.title[PARENT[slug]]))
                    self.assertEqual(len(crumbs), 2)
                else:
                    self.assertEqual(len(crumbs), 1)
                self.assertIn(f'<span aria-current="page">{self.title[slug]}</span>', nav)
                self.assertEqual(nav.count(' ＞ '), len(crumbs))

    def test_release_marker_and_policy_note_are_shared(self):
        for slug in HUBS:
            with self.subTest(slug=slug):
                html = self.html[slug]
                self.assertIn('data-reader-release="20260912-audit-fix"', html)
                self.assertIn('比較記事（PR表示あり）には販売店への広告リンクが含まれます。ガイド記事には含まれません。', html)
                self.assertNotIn('広告が含まれる場合があります', html)
                self.assertIn('<nav aria-label="編集方針">', html)

    def test_pr_badge_marks_exactly_the_affiliate_articles(self):
        for slug in HUBS:
            html = self.html[slug]
            for m in re.finditer(r'<h3>(.*?)</h3>', html):
                heading = m.group(1)
                href = re.search(r'href="/([a-z0-9-]+)/', heading)
                if not href:
                    continue
                target = href.group(1)
                badged = 'class="ks-pr-badge"' in heading
                if target in AFFILIATE:
                    self.assertTrue(badged, (slug, target))
                elif target in NO_AFFILIATE:
                    self.assertFalse(badged, (slug, target))

    def test_article_anchor_text_is_the_article_title_or_a_target_heading(self):
        for slug in HUBS:
            html = self.html[slug]
            for m in re.finditer(r'<h3>(?:<abbr[^>]*>PR</abbr>)?<a href="/([a-z0-9-]+)/(#[^"]*)?">([^<]+)</a></h3>', html):
                target, fragment, text = m.groups()
                if target in self.title and not fragment:
                    self.assertEqual(text, self.title[target], (slug, target))

    def test_blurbs_are_not_repeated_across_hubs(self):
        seen = {}
        for slug in HUBS:
            for m in re.finditer(r'<article>(.*?)</article>', self.html[slug], re.S):
                block = m.group(1)
                href = re.search(r'href="/([a-z0-9-]+)/', block)
                paragraphs = re.findall(r'<p>(.*?)</p>', block)
                if not href or href.group(1) not in self.title or not paragraphs:
                    continue
                key = (href.group(1), re.sub(r'<[^>]+>', '', paragraphs[0]))
                self.assertNotIn(key, seen, (slug, seen.get(key)))
                seen[key] = slug

    def test_purpose_hubs_have_a_first_read_and_enough_body(self):
        for slug in PURPOSE:
            with self.subTest(slug=slug):
                html = self.html[slug]
                self.assertIn('<h2>まず読む1本</h2>', html)
                self.assertGreaterEqual(visible_chars(html), 300)
                cards = re.findall(r'<article>.*?</article>', html, re.S)
                self.assertGreaterEqual(len(cards), 2)
                for card in cards:
                    self.assertIn('この記事で決まること：', card)
                self.assertIn('候補が決まったら、最後の確認</a>', html)

    def test_guides_and_comparisons_do_not_list_the_same_article_twice(self):
        guides = set(re.findall(r'<h3>(?:<abbr[^>]*>PR</abbr>)?<a href="/([a-z0-9-]+)/">', self.html['guides']))
        comparisons = set(re.findall(r'<h3>(?:<abbr[^>]*>PR</abbr>)?<a href="/([a-z0-9-]+)/">', self.html['comparisons']))
        self.assertEqual(guides & comparisons, set())
        self.assertEqual(len(guides), 5)
        self.assertEqual(len(comparisons), 10)
        fragment_links = re.findall(r'<h3>(?:<abbr[^>]*>PR</abbr>)?<a href="/([a-z0-9-]+)/#', self.html['guides'])
        self.assertEqual(len(fragment_links), 10)
        self.assertIn('候補を横並びで比べたい方は', self.html['guides'])
        self.assertIn('条件の整理から始めたい方は', self.html['comparisons'])

    def test_category_hubs_share_the_kitchen_skeleton(self):
        for slug in CATEGORY:
            with self.subTest(slug=slug):
                html = self.html[slug]
                for marker in (f'id="{slug}-axes"', 'id="choose"', 'id="compare"', 'id="purchase-checks"',
                               f'id="ks-visual-{slug}"', '<nav aria-label="このページの読み方">',
                               '<nav aria-label="ほかの商品カテゴリ">', '先に確かめる4つの条件', '条件から候補を見る'):
                    self.assertIn(marker, html)
                self.assertEqual(html.count('<nav '), 4)
                self.assertEqual(len(re.findall(r'<li>[^<]*：<a href="/[a-z0-9-]+/#[^"]+">', html)), len(re.findall(r'<li>[^<]*：<a ', html)))

    def test_updates_lists_every_article_with_a_date_and_a_change_note(self):
        html = self.html['updates']
        cards = re.findall(r'<article>.*?</article>', html, re.S)
        self.assertEqual(len(cards), 15)
        dates = []
        for card in cards:
            self.assertRegex(card, r'<time datetime="2026-\d\d-\d\d">2026年\d+月\d+日</time>更新')
            self.assertIn('変更点：', card)
            dates.append(re.search(r'datetime="([^"]+)"', card).group(1))
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_purposes_index_names_count_and_products_per_card(self):
        html = self.html['purposes']
        for slug in PURPOSE:
            self.assertIn(f'<h3><a href="/{slug}/">{self.title[slug]}</a></h3>', html)
        self.assertEqual(len(re.findall(r'<strong>\d記事・', html)), 6)


if __name__ == '__main__':
    unittest.main()
