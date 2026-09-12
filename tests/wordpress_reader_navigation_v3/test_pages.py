"""Offline authored-page contracts; these do not establish live deployment."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
ARTICLES = ROOT / "changes/wordpress-direct-publish-v1/articles"


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.nodes = []

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))


class ReaderPageTests(unittest.TestCase):
    def setUp(self):
        self.body = (ARTICLES / "categories.html").read_text(encoding="utf-8")
        self.parsed = Tags()
        self.parsed.feed(self.body)

    def test_four_real_hosted_category_images(self):
        images = [attrs for tag, attrs in self.parsed.nodes if tag == "img"]
        self.assertEqual(len(images), 4)
        for attrs in images:
            self.assertTrue(attrs["src"].startswith(
                "https://kurashinoshirube.com/wp-content/uploads/"
            ))
            self.assertEqual((attrs["width"], attrs["height"]), ("762", "506"))

    def test_four_categories_remain_reachable(self):
        hrefs = [attrs.get("href") for tag, attrs in self.parsed.nodes if tag == "a"]
        for slug in ("travel", "kitchen", "cleaning", "preparedness"):
            self.assertIn("/" + slug + "/", hrefs)

    def test_unique_ids_and_image_disclosure(self):
        ids = [attrs["id"] for _, attrs in self.parsed.nodes if attrs.get("id")]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("AI生成", self.body)
        self.assertIn("実物写真", self.body)

    def test_layout_is_in_editable_source(self):
        self.assertIn("grid-template-columns:", self.body)
        self.assertIn("height:auto", self.body)
        self.assertNotIn("[kurashinoshirube_reader_hub", self.body)

    def test_no_unrelated_external_links_or_new_scripts(self):
        for tag, attrs in self.parsed.nodes:
            self.assertNotEqual(tag, "script")
            if tag == "a":
                self.assertTrue(attrs["href"].startswith("/"))
                self.assertFalse(attrs["href"].startswith("//"))

    def test_home_shared_guide_is_not_travel_only(self):
        home = (ARTICLES / "home.html").read_text(encoding="utf-8")
        self.assertIn('<h2 class="km-promos-title">選び方の3ステップ</h2>', home)
        self.assertIn('<a href="/categories/">商品カテゴリから探す ', home)
        self.assertNotIn('href="/travel/">スーツケース選びを始める', home)

    def test_home_retains_photos_and_purchase_target(self):
        home = (ARTICLES / "home.html").read_text(encoding="utf-8")
        parsed = Tags()
        parsed.feed(home)
        ids = [attrs["id"] for _, attrs in parsed.nodes if attrs.get("id")]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("ks-visual-categories", ids)
        self.assertIn("home-purchase-check", ids)
        self.assertIn('href="#home-purchase-check"', home)
        for slug in ("travel", "kitchen", "cleaning", "preparedness"):
            self.assertIn("ks-" + slug + "-editorial-ai-20260910.webp", home)


if __name__ == "__main__":
    unittest.main()
