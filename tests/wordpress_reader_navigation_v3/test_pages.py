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

    def _cards(self):
        cards = [n for n in self.doc.nodes if n.tag == "article"]
        self.assertEqual(len(cards), 4)
        for card in cards:
            inside = [n for n in self.doc.nodes if card.start < n.start < card.end]
            details = [n for n in inside if n.tag == "details"]
            self.assertEqual(len(details), 1)
            yield card, inside, details[0]

    def test_cards_link_category_representative_and_choice_before_details(self):
        entry = json.loads(
            (
                ROOT / "changes/site-improvements-20260913/entry-pages.v1.json"
            ).read_text()
        )["categories"]
        seen = set()
        for _, inside, details in self._cards():
            top = [
                n.attrs["href"]
                for n in inside
                if n.tag == "a" and n.start < details.start
            ]
            # Category page, representative comparison and measurement/choice;
            # the last two merge into one link when they are the same post.
            self.assertIn(len(top), (2, 3))
            self.assertEqual(len(set(top)), len(top))
            slug = top[0].strip("/")
            self.assertIn(slug, entry)
            seen.add(slug)
            representative = "/" + entry[slug]["representative"] + "/"
            self.assertTrue(any(h.startswith(representative) for h in top[1:]))
        self.assertEqual(seen, {"travel", "kitchen", "cleaning", "preparedness"})

    def test_details_list_every_published_article_with_ledger_counts(self):
        meta = json.loads(
            (
                ROOT
                / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/site-editorial-metadata.v1.json"
            ).read_text()
        )["articles"]
        entry = json.loads(
            (
                ROOT / "changes/site-improvements-20260913/entry-pages.v1.json"
            ).read_text()
        )["categories"]
        self.assertNotIn("広告リンクを含む記事", self.doc.text)
        for _, inside, details in self._cards():
            slug = next(n for n in inside if n.tag == "a").attrs["href"].strip("/")
            rows = [a for a in meta.values() if a["category"] == slug]
            comparisons = sum(a["role"] == "comparison" for a in rows)
            guides = sum(a["role"] == "guide" for a in rows)
            kinds = "比較" + str(comparisons) + "本" + (
                "・ガイド" + str(guides) + "本" if guides else ""
            )
            summary = entry[slug]["name"] + "の記事 " + str(len(rows)) + "本（" + kinds + "）"
            self.assertIn("<summary>" + summary + "</summary>", self.doc.text)
            listed = {
                n.attrs["href"].split("#", 1)[0].strip("/")
                for n in inside
                if n.tag == "a" and details.start < n.start < details.end
            }
            self.assertEqual(listed, {a["slug"] for a in rows})

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
