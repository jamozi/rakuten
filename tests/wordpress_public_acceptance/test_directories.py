"""Regression checks for the two reader-facing directories, with no network."""

import json
import os
from pathlib import Path
import unittest
from urllib.parse import urlsplit
from scripts.raos_reader_live_patch import Document
from scripts.raos_public_acceptance import Page

ROOT = Path(__file__).resolve().parents[2]
METADATA = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/site-editorial-metadata.v1.json"
)
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
            {
                "#travel-guides",
                "#kitchen-guides",
                "#cleaning-guides",
                "#preparedness-guides",
            }
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
            "/",
            "/categories/",
            "/purposes/",
            "/guides/",
            "/comparisons/",
            "/updates/",
            "/travel/",
            "/kitchen/",
            "/cleaning/",
            "/preparedness/",
            "/comparison-policy/",
            "/about-ad-policy/",
            "/privacy-policy/",
        }
        article_links = {
            urlsplit(h).path
            for h, _, _ in doc.links
            if h.startswith("/") and h not in hubs and not h.startswith("/#")
        }
        comparisons = {
            slug: record
            for slug, record in json.loads(METADATA.read_text())["articles"].items()
            if record["comparison_count"]
        }
        self.assertEqual(article_links, {"/" + slug + "/" for slug in comparisons})
        self.assertEqual(len(article_links), 16)
        hrefs = {h for h, _, _ in doc.links}
        for slug, record in comparisons.items():
            route = "/" + slug + "/"
            self.assertIn(route, hrefs)
            self.assertIn(route + "#" + record["comparison_anchor"], hrefs)
            if record["offers_anchor"]:
                self.assertIn(route + "#" + record["offers_anchor"], hrefs)
            else:
                self.assertNotIn(route + "#ps-offers", hrefs)
        self.assertIn("/solota-vs-rakua-mini-plus/", article_links)
        self.assertIn("/anker-solix-c300-c800-c1000-differences/", article_links)

    def test_guides_list_ledger_guides_and_representative_condition_sections(self):
        # Guide articles have direct routes; the other three categories lead to
        # selected comparison sections that help readers establish conditions.
        doc = Page(self.text("guides"))
        hubs = {
            "/",
            "/categories/",
            "/purposes/",
            "/comparisons/",
            "/comparison-policy/",
            "/about-ad-policy/",
            "/without-installation/",
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
                "/dishwasher-branch-faucet-guide/",
                # next30 W1: the first guide outside the dishwasher set.
                "/dish-rack-installation-measurement/",
            },
        )
        self.assertEqual(
            {h for h in routes if "#" in h},
            {
                "/lightweight-carry-on-suitcase-under-3kg/#ps-choose",
                "/compact-robot-vacuum-shortlist/#ps-choose",
                "/portable-power-station-guide/#ps-decision-steps",
            },
        )
        self.assertFalse(plain & fragments)

    def test_payment_and_points_are_separate(self):
        text = self.text("comparisons")
        self.assertIn("buyer-offer-check", text)
        self.assertIn("ポイントや条件付きクーポンは、支払額と分けて", text)
        self.assertIn("条件が残る場合は買わずに保留できます", text)

    def test_guide_does_not_promise_active_calculator(self):
        text = self.text("guides")
        self.assertIn("/dishwasher-running-cost/", text)
        self.assertIn("従量費を式で確認", text)
        self.assertIn("計算できる小計と不足値を分けます", text)
        self.assertFalse(any(n.tag in {"form", "input"} for n in Document(text).nodes))
        self.assertNotIn("計算フォーム", text)

    def test_no_external_or_tracking_links_added(self):
        for slug in ("guides", "comparisons"):
            for href, _, _ in Page(self.text(slug)).links:
                self.assertTrue(
                    href.startswith(("/", "#")) and not href.startswith("//")
                )
            text = self.text(slug)
            self.assertIn("記事ごとの広告表示は実際のリンクに基づきます", text)
            self.assertIn("掲載順・評価は報酬条件と切り離しています", text)
            doc = Document(text)
            cards = [n for n in doc.nodes if n.tag == "article"]
            self.assertEqual(len(cards), 10 if slug == "guides" else 16)
            for card in cards:
                content = text[card.start : card.end]
                self.assertEqual(
                    content.count("PR・広告リンクあり")
                    + content.count("広告リンクなし"),
                    1,
                )
                metadata = json.loads(METADATA.read_text())["articles"]
                target = urlsplit(Page(content).links[0][0]).path.strip("/")
                expected = (
                    "PR・広告リンクあり"
                    if metadata[target]["has_ads"]
                    else "広告リンクなし"
                )
                self.assertIn(expected, content)


if __name__ == "__main__":
    unittest.main()
