"""Text category cards and stylesheet ownership in the accepted page design."""

import json
import unittest
from pathlib import Path
from scripts.raos_reader_live_patch import Document

ROOT = Path(__file__).resolve().parents[2]
DIRECT = ROOT / "changes/wordpress-direct-publish-v1"


class ReaderPageTests(unittest.TestCase):
    def setUp(self):
        self.doc = Document((DIRECT / "articles/categories.html").read_text())

    def test_four_cards_offer_three_distinct_destinations(self):
        cards = [n for n in self.doc.nodes if n.tag == "article"]
        self.assertEqual(len(cards), 4)
        for card in cards:
            links = [
                n.attrs["href"]
                for n in self.doc.nodes
                if n.tag == "a" and card.start < n.start < card.end
            ]
            self.assertEqual(len(links), 3)
            self.assertEqual(len(set(links)), 3)
        for slug in ("travel", "kitchen", "cleaning", "preparedness"):
            self.assertIn('href="/' + slug + '/"', self.doc.text)

    def test_dynamic_category_counts_and_ads_are_projected(self):
        meta = json.loads(
            (
                ROOT
                / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/site-editorial-metadata.v1.json"
            ).read_text()
        )["articles"]
        for category in ("travel", "kitchen", "cleaning", "preparedness"):
            rows = [a for a in meta.values() if a["category"] == category]
            self.assertIn(
                str(len(rows))
                + "記事・広告リンクを含む記事 "
                + str(sum(a["has_ads"] for a in rows))
                + "本",
                self.doc.text,
            )

    def test_layout_owned_by_theme_and_source_does_not_add_scripts_or_tracking(self):
        css = (
            ROOT
            / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/theme.css"
        ).read_text()
        self.assertIn(".ks-editorial-page", css)
        self.assertIn("grid-template-columns", css)
        for n in self.doc.nodes:
            self.assertNotEqual(n.tag, "script")
            if n.tag == "a":
                self.assertTrue(n.attrs["href"].startswith("/"))
                self.assertFalse(n.attrs["href"].startswith("//"))
        self.assertNotIn("[kurashinoshirube_reader_hub", self.doc.text)
