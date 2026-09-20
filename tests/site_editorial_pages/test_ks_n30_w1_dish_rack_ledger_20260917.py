"""next30 Wave 1 (2026-09-17): the three dish-rack rows carry their publication identity.

A new article reaches the site in two candidates, and this file now pins the
second one. The owner-direct publisher is the only thing that can mint a post
id, and on 2026-09-20 it minted three: 750, 751 and 752. A row that holds one
says so — ``mode:"existing"`` with the id — and only such a row may carry a
``listing``, because everything a listing carries — the hub card, the count on
/comparisons/, the published date — is a claim about a post that exists.
Writing one on a row that still has no id is not a harmless placeholder:
``metadata`` raises ``LEDGER_IDENTITY_STALE`` for a ``mode:"new"`` row whose
listing says published (site_editorial_pages.py:370), and every generated hub
would otherwise link a URL that 404s. The negative control below still proves
that guard, on a copied row instead of on the three that are now live.

So the invariant this wave has to hold is narrow and testable: the three rows
exist, they are complete enough for the publisher and for ``validate_reader_roles``
(which checks identity for every row and link targets only for published ones),
their bodies exist on disk where ``load_bodies`` reads them, and the projection
the hubs are built from grows by exactly these three entries and no others —
the 20 posts that were public at the wave's base commit keep their publication
and the post id each already had, so /home/, /categories/, /comparisons/,
/guides/ and /updates/ gained the three dish-rack articles and lost nothing.
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
# The ids the owner-direct publisher minted for the three on 2026-09-20.
POST_IDS = {
    "dish-rack-installation-measurement": 750,
    "slim-dish-rack-under-20cm": 751,
    "dish-rack-no-space": 752,
}

# (state, role, category, task_label, main_count, comparison_anchor, published_at_gmt)
LISTINGS = {
    "dish-rack-installation-measurement": (
        "published",
        "guide",
        "kitchen",
        "水切りラックを置けるか測る",
        0,
        None,
        "2026-09-20T03:33:04Z",
    ),
    "slim-dish-rack-under-20cm": (
        "published",
        "comparison",
        "kitchen",
        None,
        3,
        "slim-compare",
        "2026-09-20T03:33:00Z",
    ),
    "dish-rack-no-space": (
        "published",
        "comparison",
        "kitchen",
        None,
        5,
        "rack-methods",
        "2026-09-20T03:32:56Z",
    ),
}
TITLES = {
    "dish-rack-installation-measurement": "水切りラックを置けるか測る｜シンク・脚・蛇口の確認",
    "slim-dish-rack-under-20cm": "短辺20cm以下のすき間に据え置く水切りラック3商品を比べる",
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
            "label": "短辺20cm以下のすき間に据え置く3商品を比べる",
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
        "primary_intent": "短辺20cm以下のすき間に据え置ける水切りラックを選びたい",
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

# The 20 posts public at the base commit, with the id each already had.
BASE_PUBLISHED_POSTS = {
    "carry-on-suitcase-comparison": 19,
    "carry-on-suitcase-under-100-seats": 82,
    "lightweight-carry-on-suitcase-under-3kg": 83,
    "front-open-carry-on-suitcase-with-stopper": 84,
    "countertop-dishwasher-for-small-households": 41,
    "solota-vs-rakua-mini-plus": 86,
    "dishwasher-installation-measurement": 262,
    "dishwasher-water-supply-methods": 263,
    "dishwasher-detergent-guide": 264,
    "dishwasher-cleaning-guide": 265,
    "dishwasher-running-cost": 266,
    "compact-robot-vacuum-shortlist": 30,
    "roomba-mini-vs-switchbot-k11-pro": 85,
    "portable-power-station-guide": 28,
    "anker-solix-c300-c800-c1000-differences": 29,
    "compact-dishwasher-comparison": 549,
    "standard-dishwasher-comparison": 550,
    "large-dishwasher-comparison": 551,
    "dishwasher-branch-faucet-guide": 552,
    "small-carry-on-suitcase-comparison": 553,
}


class WaveOneLedgerRows(unittest.TestCase):
    def setUp(self):
        self.data, self.registry, self.catalog = builder.load_inputs()
        self.rows = {row["article_key"]: row for row in self.registry["articles"]}

    def test_the_three_rows_carry_the_post_id_the_publisher_minted(self):
        for key in WAVE_ONE:
            with self.subTest(key=key):
                row = self.rows[key]
                self.assertEqual(
                    (row["mode"], row["post_id"], row["post_type"], row["slug"]),
                    ("existing", POST_IDS[key], "post", key),
                )
                self.assertEqual(row["title"], TITLES[key])
                self.assertTrue(row["excerpt"].strip())
                self.assertEqual(row["taxonomies"], FULL_TAXONOMIES)

    def test_a_published_row_carries_the_listing_its_post_earned(self):
        """A listing is a claim about a post that exists; these three now do."""
        for key in WAVE_ONE:
            with self.subTest(key=key):
                listing = self.rows[key]["listing"]
                self.assertEqual(
                    (
                        listing["state"],
                        listing["role"],
                        listing["category"],
                        listing["task_label"],
                        listing["main_count"],
                        listing["comparison_anchor"],
                        listing["published_at_gmt"],
                    ),
                    LISTINGS[key],
                )
                # A first publication carries no change_log. Wave 2 touched all
                # three on 2026-09-20 -- two gained a route, 750 also carries the
                # correction of its 7835 source line -- so each now holds exactly
                # that one entry, and nothing older.
                log = listing["change_log"]
                self.assertEqual([entry["date"] for entry in log], ["2026-09-20"])
                self.assertIn(log[0]["kind"], {"content", "correction"})
                self.assertTrue(log[0]["summary"].strip())

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

    def test_the_projection_the_hubs_read_grows_by_exactly_the_three(self):
        """Regression: wave 1 adds three listings, wave 2 three more, no others."""
        # The owner-direct publisher minted three more ids on 2026-09-20 — 766,
        # 767 and 768 for wave 2's dish-rack comparisons — so the projection the
        # hubs read grows by six rows, not three. Pinned by id like wave 1's: a
        # seventh listing still has to be accounted for.
        wave_two_post_ids = {
            "dish-rack-one-tier-vs-two-tier": 766,
            "foldable-rack-vs-extendable-basket": 767,
            "dish-rack-with-dishwasher": 768,
        }
        published_post_ids = {**POST_IDS, **wave_two_post_ids}
        bodies = builder.load_bodies(self.registry)
        meta = editorial.metadata(self.registry, self.catalog, self.data, bodies)
        self.assertEqual(
            len(meta), PUBLISHED_POSTS_AT_BASE + len(published_post_ids)
        )
        for key, post_id in published_post_ids.items():
            with self.subTest(key=key):
                self.assertIn(key, meta)
                self.assertEqual(meta[key]["post_id"], post_id)
                self.assertTrue(editorial.is_published(self.rows[key]))

    def test_a_published_listing_on_a_new_row_is_refused(self):
        """Negative control: the stale-identity guard is what binds listing to post id.

        Proved on a copy of a live row — same valid published listing, no minted
        id — so the three rows the hubs now read stay exactly as published.
        """
        registry = copy.deepcopy(self.registry)
        row = copy.deepcopy(self.rows[WAVE_ONE[0]])
        row["article_key"] = row["slug"] = WAVE_ONE[0] + "-unminted-copy"
        row["mode"] = "new"
        row["post_id"] = None
        registry["articles"].append(row)
        bodies = builder.load_bodies(registry)
        with self.assertRaisesRegex(ValueError, "LEDGER_IDENTITY_STALE"):
            editorial.metadata(registry, self.catalog, self.data, bodies)

    def test_the_published_articles_of_the_base_commit_are_untouched(self):
        # Wave 2 published three more dish-rack rows on 2026-09-20 (766/767/768).
        # Like wave 1's, they are new posts, not edits to the 20 the base commit
        # had, so they are set aside here instead of being weighed against it.
        wave_two = (
            "dish-rack-one-tier-vs-two-tier",
            "foldable-rack-vs-extendable-basket",
            "dish-rack-with-dishwasher",
        )
        published = {
            row["article_key"]: row["post_id"]
            for row in self.registry["articles"]
            if row["post_type"] == "post" and editorial.is_published(row)
        }
        self.assertEqual(
            len(published), PUBLISHED_POSTS_AT_BASE + len(WAVE_ONE) + len(wave_two)
        )
        self.assertEqual(
            {
                key: pid
                for key, pid in published.items()
                if key not in WAVE_ONE and key not in wave_two
            },
            BASE_PUBLISHED_POSTS,
        )


if __name__ == "__main__":
    unittest.main()
