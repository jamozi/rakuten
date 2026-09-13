"""September 13 homepage composition and meaningful legacy URLs."""

import json
import re
import unittest
from pathlib import Path
from scripts.raos_reader_live_patch import Document
from scripts.build_site_editorial_pages import build

ROOT = Path(__file__).resolve().parents[2]
DIRECT = ROOT / "changes/wordpress-direct-publish-v1"
HOME_CSS = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/home-magazine.css"
)


class LegacyHomeRoutes(unittest.TestCase):
    def setUp(self):
        self.doc = Document(
            build()[Path("changes/wordpress-direct-publish-v1/articles/home.html")]
        )
        self.text = self.doc.text

    def test_legacy_breadcrumb_destinations_are_real_category_links(self):
        for ident, href in {
            "cluster-mobility": "/travel/",
            "cluster-home": "/kitchen/",
            "cluster-ready": "/preparedness/",
        }.items():
            n = self.doc.ids[ident]
            self.assertEqual((n.tag, n.attrs.get("href")), ("a", href))
            self.assertTrue(self.text[n.open_end : n.close_start].strip())
            self.assertNotIn("hidden", n.attrs)

    def test_old_purchase_hash_links_to_purchase_checks_without_extra_section(self):
        n = self.doc.ids["home-purchase-check"]
        content = self.text[n.open_end : n.close_start]
        self.assertIn("/comparisons/#purchase-checks", content)
        self.assertNotIn("各記事の購入条件", self.text)
        self.assertNotIn("選び方の3ステップ", self.text)

    def test_four_image_cards_use_category_destinations(self):
        n = next(
            n
            for n in self.doc.nodes
            if "ks-home-category-grid" in n.attrs.get("class", "").split()
        )
        urls = re.findall(r'<h3><a [^>]*href="([^"]+)">', self.text[n.start : n.end])
        self.assertEqual(
            urls,
            [
                "/kitchen/",
                "/travel/",
                "/cleaning/",
                "/preparedness/",
            ],
        )

    def test_four_categories_and_four_recent_articles_keep_secondary_links(self):
        for ident, count in [
            ("km-categories-title", 4),
            ("km-updates-title", 4),
        ]:
            n = self.doc.ids[ident]
            self.assertEqual(self.text[n.start : n.end].count("<article "), count)
        self.assertIn('href="/updates/"', self.text)
        self.assertEqual(self.doc.ids["km-purposes-title"].attrs["href"], "/purposes/")
        # Entire inventory remains reachable through category/list pages, not repeated on home.
        self.assertNotIn("掲載 15記事", self.text)

    def test_one_unlinked_h1_and_no_skipped_heading_levels(self):
        headings = [n for n in self.doc.nodes if n.tag in ("h1", "h2", "h3")]
        self.assertEqual(sum(n.tag == "h1" for n in headings), 1)
        for prior, current in zip(headings, headings[1:]):
            self.assertLessEqual(int(current.tag[1]) - int(prior.tag[1]), 1)
        for n in headings:
            self.assertRegex(
                self.text[n.open_end : n.close_start], r"[\u3040-\u30ff\u4e00-\u9fff]"
            )
        n = headings[0]
        self.assertNotEqual(self.doc.nodes[n.parent].tag, "a")

    def test_hero_and_editorial_feature_images_preserve_media_boundaries(self):
        images = [n.attrs for n in self.doc.nodes if n.tag == "img"]
        self.assertEqual(len(images), 9)
        self.assertTrue(
            images[0]["src"].endswith("/assets/images/home-lifestyle-20260913.webp")
        )
        self.assertEqual((images[0]["width"], images[0]["height"]), ("1672", "941"))
        self.assertNotIn("<figcaption", self.text)
        data = json.loads(
            (
                ROOT / "changes/site-improvements-20260913/entry-pages.v1.json"
            ).read_text()
        )
        self.assertEqual(data["home_image_style"], "editorial")
        for image, category in zip(
            images[1:5], ("kitchen", "travel", "cleaning", "preparedness")
        ):
            self.assertTrue(
                image["src"].endswith(f"/ks-{category}-editorial-ai-20260910.webp")
            )
            self.assertEqual((image["width"], image["height"]), ("762", "506"))
        slots = [
            n.attrs["data-ks-home-product"]
            for n in self.doc.nodes
            if "data-ks-home-product" in n.attrs
        ]
        self.assertEqual(slots, [])
        self.assertNotIn("hb.afl.rakuten.co.jp", self.text)
        template = (
            ROOT
            / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/templates/front-page.html"
        ).read_text()
        self.assertEqual(template.count('data-raos-ad-disclosure="site"'), 1)
        self.assertIn('href="/about-ad-policy/"', template)
        self.assertIn("広告を含みます", template)

    def test_all_preserved_anchors_have_content(self):
        data = json.loads(
            (
                ROOT / "changes/site-improvements-20260913/entry-pages.v1.json"
            ).read_text()
        )
        for ident in data["pages"]["home"]["anchors"]:
            n = self.doc.ids[ident]
            self.assertTrue(
                re.sub("<[^>]+>", "", self.text[n.open_end : n.close_start]).strip(),
                ident,
            )
