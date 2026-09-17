"""next30 Wave 1 (2026-09-17): the three dish-rack rows enter the ledger unpublished.

A new article reaches the site in two candidates, and this file pins the first
one. The owner-direct publisher is the only thing that can mint a post id, so a
row for an article nobody has published yet has to say so: ``mode:"new"`` with
``post_id`` still null. Everything a listing carries — the hub card, the count
on /comparisons/, the published date — is a claim about a post that exists, so
a row in that state carries no ``listing`` at all. Writing one anyway is not a
harmless placeholder: ``metadata`` raises ``LEDGER_IDENTITY_STALE`` for a
``mode:"new"`` row whose listing says published (site_editorial_pages.py:367),
and every generated hub would otherwise link a URL that 404s.

So the invariant this wave has to hold is narrow and testable: the three rows
exist, they are complete enough for the publisher and for ``validate_reader_roles``
(which checks identity for every row and link targets only for published ones),
their bodies exist on disk where ``load_bodies`` reads them, and the projection
the hubs are built from does not grow by a single entry. The second candidate,
after the post ids exist, is what turns them into ``mode:"existing"`` rows with a
full listing; until then /home/, /categories/, /comparisons/, /guides/ and
/updates/ must look exactly as they did at the wave's base commit.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "site_builder_w1_ledger", ROOT / "scripts/build_site_editorial_pages.py"
)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

from raos.application.editorial import site_editorial_pages as editorial  # noqa: E402

WAVE_ONE = ("dish-rack-installation-measurement", "slim-dish-rack-under-20cm", "dish-rack-no-space")
BODY_DIRECTORY = "changes/wordpress-direct-publish-v1/articles"
FULL_TAXONOMIES = {"category": [5], "post_format": [], "post_tag": []}
# The 20 posts that were public at the wave's base commit (cd8c6eec).
PUBLISHED_POSTS_AT_BASE = 20

TITLES = {
    "dish-rack-installation-measurement": "水切りラックを置けるか測る｜シンク・脚・蛇口の確認",
    "slim-dish-rack-under-20cm": "短辺20cm以下の水切りラック3商品を比べる",
    "dish-rack-no-space": "水切りかごを置く場所がない｜3つの方式から選ぶ",
}
READER_ROLES = {
    "dish-rack-installation-measurement": {
        "page_kind": "task_guide",
        "primary_intent": "水切りラックを置けるか、自宅のシンク周りを測って判断したい",
        "reader": "候補の水切りラックが置けるか分からない人",
        "decision_after_reading": "公式条件で絞った後、どこを自分で測るか",
        "main_cta": {
            "kind": "internal",
            "target": "slim-dish-rack-under-20cm",
            "anchor": "",
            "label": "短辺20cm以下の3商品を比べる",
        },
        "next_question": {
            "question": "置く場所そのものが取れない？",
            "target": "dish-rack-no-space",
            "anchor": "",
            "status": "live",
        },
        "scope": {
            "primary_product_ids": [
                "PRD-YAMAZAKI-4314",
                "PRD-YAMAZAKI-5070",
                "PRD-SHIMOMURA-42666",
                "PRD-YAMAZAKI-7835",
                "PRD-YAMAZAKI-3492",
            ],
            "reference_product_ids": [],
        },
    },
    "slim-dish-rack-under-20cm": {
        "page_kind": "condition_comparison",
        "primary_intent": "シンク横の短辺20cm以下に置ける水切りラックを選びたい",
        "reader": "すき間に常設したい人",
        "decision_after_reading": "3商品のどれを候補にするか",
        "main_cta": {
            "kind": "internal",
            "target": "dish-rack-installation-measurement",
            "anchor": "",
            "label": "購入前に脚と水受けの動きまで測る",
        },
        "next_question": {
            "question": "置く場所そのものが取れない？",
            "target": "dish-rack-no-space",
            "anchor": "",
            "status": "live",
        },
    },
    "dish-rack-no-space": {
        "page_kind": "broad_comparison",
        "primary_intent": "洗った食器の置き場がないので、水切りの方式から決めたい",
        "reader": "水切りかごを置く場所が確保できない人",
        "decision_after_reading": "常設・シンク上・都度収納のどれで探すか",
        "main_cta": {
            "kind": "internal",
            "target": "slim-dish-rack-under-20cm",
            "anchor": "",
            "label": "すき間に置く3商品を比べる",
        },
        "next_question": {
            "question": "置き場所の寸法から確かめる？",
            "target": "dish-rack-installation-measurement",
            "anchor": "",
            "status": "live",
        },
    },
}


class WaveOneLedgerRows(unittest.TestCase):
    def setUp(self):
        self.data, self.registry, self.catalog = builder.load_inputs()
        self.rows = {row["article_key"]: row for row in self.registry["articles"]}

    def test_the_three_rows_are_new_posts_without_a_publication_identity(self):
        for key in WAVE_ONE:
            with self.subTest(key=key):
                row = self.rows[key]
                self.assertEqual(
                    (row["mode"], row["post_id"], row["post_type"], row["slug"]),
                    ("new", None, "post", key),
                )
                self.assertEqual(row["title"], TITLES[key])
                self.assertTrue(row["excerpt"].strip())
                self.assertEqual(row["taxonomies"], FULL_TAXONOMIES)

    def test_an_unpublished_row_carries_no_listing(self):
        """A listing is a claim about a post that exists; these posts do not yet."""
        for key in WAVE_ONE:
            with self.subTest(key=key):
                self.assertNotIn("listing", self.rows[key])

    def test_the_body_the_row_names_is_generated_and_present(self):
        for key in WAVE_ONE:
            with self.subTest(key=key):
                source = self.rows[key]["body_source"]
                self.assertEqual(source, f"{BODY_DIRECTORY}/{key}.html")
                self.assertNotIn("patch_source", self.rows[key])
                body = (ROOT / source).read_text()
                self.assertTrue(body.strip())
                self.assertIn("ps-article", body)

    def test_reader_role_is_exactly_what_the_wave_specified(self):
        for key in WAVE_ONE:
            with self.subTest(key=key):
                self.assertEqual(self.rows[key]["reader_role"], READER_ROLES[key])

    def test_no_wave_one_row_claims_an_offer_cta(self):
        """No approved seller exists for the five racks, so no row may promise one."""
        for key in WAVE_ONE:
            with self.subTest(key=key):
                self.assertIn(
                    self.rows[key]["reader_role"]["main_cta"]["kind"],
                    {"internal", "none"},
                )

    def test_reader_roles_validate_across_the_whole_ledger(self):
        documents = builder.reader_documents()
        self.assertEqual(
            set(documents), {row["article_key"] for row in self.registry["articles"]}
        )
        self.assertEqual(
            editorial.validate_reader_roles(self.registry, documents, self.catalog), []
        )

    def test_primary_intents_stay_unique_after_the_wave(self):
        intents = [row["reader_role"]["primary_intent"] for row in self.registry["articles"]]
        self.assertEqual(len(intents), len(set(intents)))

    def test_the_projection_the_hubs_read_does_not_grow(self):
        """Regression: the first candidate publishes bodies, never a listing entry."""
        bodies = builder.load_bodies(self.registry)
        meta = editorial.metadata(self.registry, self.catalog, self.data, bodies)
        self.assertEqual(len(meta), PUBLISHED_POSTS_AT_BASE)
        for key in WAVE_ONE:
            with self.subTest(key=key):
                self.assertNotIn(key, meta)
                self.assertFalse(editorial.is_published(self.rows[key]))

    def test_a_published_listing_on_a_new_row_is_refused(self):
        """Negative control: the stale-identity guard is what makes 'no listing' safe."""
        registry = copy.deepcopy(self.registry)
        row = next(r for r in registry["articles"] if r["article_key"] == WAVE_ONE[0])
        row["listing"] = {"state": "published"}
        bodies = builder.load_bodies(registry)
        with self.assertRaisesRegex(ValueError, "LEDGER_IDENTITY_STALE"):
            editorial.metadata(registry, self.catalog, self.data, bodies)

    def test_the_published_articles_of_the_base_commit_are_untouched(self):
        published = {
            row["article_key"]
            for row in self.registry["articles"]
            if row["post_type"] == "post" and editorial.is_published(row)
        }
        self.assertEqual(len(published), PUBLISHED_POSTS_AT_BASE)
        self.assertTrue(published.isdisjoint(WAVE_ONE))


if __name__ == "__main__":
    unittest.main()
