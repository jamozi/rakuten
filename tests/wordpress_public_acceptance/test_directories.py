"""Regression checks for the two reader-facing directories, with no network."""

import os
from pathlib import Path
import unittest
from scripts.raos_public_acceptance import Page

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(
    os.environ.get(
        "KS_DIRECTORY_TEST_SOURCE",
        ROOT / "changes/wordpress-direct-publish-v1/articles",
    )
)


class DirectoryTests(unittest.TestCase):
    def text(self, slug):
        return (SOURCE / (slug + ".html")).read_text()

    def test_comparison_has_category_shortcuts(self):
        doc = Page(self.text("comparisons"))
        self.assertIn("ks-comparison-jump", doc.ids)
        self.assertTrue(
            {
                "#compare-travel",
                "#compare-kitchen",
                "#compare-cleaning",
                "#compare-preparedness",
            }
            <= {x[0] for x in doc.links}
        )

    def test_guide_has_category_shortcuts(self):
        doc = Page(self.text("guides"))
        self.assertIn("ks-guide-jump", doc.ids)
        self.assertTrue(
            {"#travel-guides", "#kitchen-guides", "#cleaning-guides", "#preparedness-guides"}
            <= {x[0] for x in doc.links}
        )

    def test_new_fragments_resolve(self):
        for slug in ("comparisons", "guides"):
            doc = Page(self.text(slug))
            self.assertEqual(len(doc.ids), len(set(doc.ids)))
            for href, _, _ in doc.links:
                if href.startswith("#"):
                    self.assertIn(href[1:], doc.ids)

    def test_preserves_comparison_article_routes(self):
        doc = Page(self.text("comparisons"))
        hubs = {
            "/", "/categories/", "/purposes/", "/guides/", "/comparisons/", "/updates/",
            "/travel/", "/kitchen/", "/cleaning/", "/preparedness/",
            "/comparison-policy/", "/about-ad-policy/", "/privacy-policy/",
        }
        article_links = {
            h
            for h, _, _ in doc.links
            if h.startswith("/") and h not in hubs and not h.startswith("/#")
        }
        self.assertEqual(len(article_links), 10)
        self.assertIn("/solota-vs-rakua-mini-plus/", article_links)
        self.assertIn("/anker-solix-c300-c800-c1000-differences/", article_links)

    def test_guides_list_five_guides_and_condition_sections_of_ten_comparisons(self):
        # 2026-09-12 audit CH-05: guide-type articles are listed as routes; comparison
        # articles appear only through fragment links to their condition sections.
        doc = Page(self.text("guides"))
        hubs = {
            "/", "/categories/", "/purposes/", "/comparisons/", "/comparison-policy/",
            "/about-ad-policy/", "/without-installation/",
        }
        routes = {h for h, _, _ in doc.links if h.startswith("/") and h not in hubs}
        plain = {h for h in routes if "#" not in h}
        fragments = {h.split("#")[0] for h in routes if "#" in h}
        self.assertEqual(
            plain,
            {
                "/dishwasher-installation-measurement/",
                "/dishwasher-water-supply-methods/",
                "/dishwasher-detergent-guide/",
                "/dishwasher-cleaning-guide/",
                "/dishwasher-running-cost/",
            },
        )
        self.assertEqual(len(fragments), 10)
        self.assertFalse(plain & fragments)

    def test_payment_and_points_are_separate(self):
        text = self.text("comparisons")
        self.assertIn("buyer-offer-check", text)
        self.assertIn("ポイントや条件付きクーポンは、支払額と分けて", text)
        self.assertIn("今回は見送る選択", text)

    def test_guide_does_not_promise_active_calculator(self):
        text = self.text("guides")
        self.assertIn("公表値と自宅の単価から計算する式が決まります", text)
        self.assertNotIn("計算フォーム", text)

    def test_no_external_or_tracking_links_added(self):
        for slug in ("guides", "comparisons"):
            for href, _, _ in Page(self.text(slug)).links:
                self.assertTrue(
                    href.startswith(("/", "#")) and not href.startswith("//")
                )
            self.assertIn(
                "比較記事（PR表示あり）には販売店への広告リンクが含まれます", self.text(slug)
            )


if __name__ == "__main__":
    unittest.main()
