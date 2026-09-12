"""Behavior checks for generated entry pages and honest date/advertising labels."""

import copy
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "site_builder", ROOT / "scripts/build_site_editorial_pages.py"
)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ProjectionTest(unittest.TestCase):
    def test_all_entry_ids_are_unique(self):
        for path, body in builder.build().items():
            if path.suffix != ".html":
                continue
            with self.subTest(path=path):
                ids = re.findall(r'\bid="([^"]+)"', body)
                self.assertEqual(len(ids), len(set(ids)))
                self.assertNotIn("どちらが決まる", body)
                self.assertNotIn("STEP 1", body)

    def test_dates_ads_counts_follow_records(self):
        import json
        from raos.application.editorial.site_editorial_pages import (
            metadata,
            render_pages,
        )

        data, registry, catalog = [
            json.loads((ROOT / p).read_text()) for p in builder.INPUT_PATHS[:3]
        ]
        changed = copy.deepcopy(data)
        changed["articles"]["41"]["published_on"] = None
        changed["articles"]["41"]["updated_on"] = "2026-09-13"
        changed["articles"]["41"]["change_summary"] = "比較対象の構成を整理しました。"
        slug = "countertop-dishwasher-for-small-households"
        record = metadata(
            registry,
            catalog,
            changed,
            {slug: '<a href="https://example.com" rel="sponsored">販売先</a>'},
        )[slug]
        self.assertTrue(record["has_ads"])
        self.assertIsNone(record["published_on"])
        self.assertEqual(record["updated_on"], "2026-09-13")
        self.assertEqual(
            record["comparison_count"],
            len(
                next(a for a in catalog["articles"] if a["slug"] == slug)["product_ids"]
            ),
        )
        pages, _, _ = render_pages(registry, catalog, changed, {})
        self.assertIn("比較対象の構成を整理しました。", pages["updates"])
        self.assertNotIn("内容更新日：", pages["home"])
        self.assertIn("内容更新日：2026-09-13", pages["updates"])
        self.assertNotIn("新しく公開：2026-09-13", pages["updates"])

    def test_home_feature_order(self):
        result = builder.build()
        home = next(v for k, v in result.items() if k.name == "home.html")
        slugs = [
            "countertop-dishwasher-for-small-households",
            "lightweight-carry-on-suitcase-under-3kg",
            "compact-robot-vacuum-shortlist",
        ]
        positions = [home.index("/" + s + "/") for s in slugs]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("旅行の荷物を楽に", home)
        self.assertIn("停電に備える", home)

    def test_home_uses_short_links_without_card_metadata(self):
        result = builder.build()
        home = next(v for k, v in result.items() if k.name == "home.html")
        for text in (
            "PR・広告リンクあり",
            "広告リンクなし",
            "主比較",
            "内容更新日：",
            "関連 4記事",
        ):
            self.assertNotIn(text, home)
        self.assertEqual(home.count('data-ks-home-product="'), 6)
        self.assertNotIn(
            "hb.afl.rakuten.co.jp", home
        )  # theme admits the unmodified image snippets.
        self.assertIn("/comparison-policy/", home)


if __name__ == "__main__":
    unittest.main()
