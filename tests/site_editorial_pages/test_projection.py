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

    def test_home_category_order(self):
        result = builder.build()
        home = next(v for k, v in result.items() if k.name == "home.html")
        slugs = [
            "kitchen",
            "travel",
            "cleaning",
            "preparedness",
        ]
        positions = [home.index("/" + s + "/") for s in slugs]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('href="/purposes/"', home)
        self.assertNotIn("悩み・目的から探す", home)

    def test_unpublished_drafts_do_not_change_entry_pages_or_counts(self):
        import json
        from raos.application.editorial.site_editorial_pages import render_pages

        data, registry, catalog = [
            json.loads((ROOT / p).read_text()) for p in builder.INPUT_PATHS[:3]
        ]
        baseline = render_pages(registry, catalog, data, {})
        for post_id in (None, 123456):
            with self.subTest(post_id=post_id):
                changed = copy.deepcopy(registry)
                changed["articles"].append(
                    {
                        "article_key": "unpublished-comparison",
                        "mode": "new",
                        "post_id": post_id,
                        "post_type": "post",
                        "title": "未公開の比較候補",
                        "slug": "unpublished-comparison",
                    }
                )
                self.assertEqual(render_pages(changed, catalog, data, {}), baseline)
                changed["articles"][-1].update(mode="existing", post_id=123456)
                with self.assertRaisesRegex(ValueError, "Missing editorial category"):
                    render_pages(changed, catalog, data, {})

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
        self.assertNotIn('data-ks-home-product="', home)
        self.assertEqual(home.count('class="ks-feature-image"'), 4)
        self.assertEqual(home.count("商品カテゴリー"), 1)
        self.assertNotIn("暮らしに合う道具を比較する", home)
        self.assertNotIn("AI編集イメージ・実物写真ではありません", home)
        self.assertNotIn("hb.afl.rakuten.co.jp", home)
        self.assertIn("/comparison-policy/", home)
        recent_images = re.findall(
            r'<a class="ks-recent-image" href="[^"]+"><img src="([^"]+)"', home
        )
        self.assertEqual(len(recent_images), 4)
        self.assertEqual(len(set(recent_images)), 4)
        self.assertTrue(
            all(src.startswith("/wp-content/themes/") for src in recent_images)
        )


if __name__ == "__main__":
    unittest.main()

    def test_authored_entry_sources_keep_the_selected_layout_and_required_anchors(self):
        import json
        from raos.application.editorial.site_editorial_pages import render_pages

        data, registry, catalog = [
            json.loads((ROOT / p).read_text()) for p in builder.INPUT_PATHS[:3]
        ]
        source = (ROOT / builder.PAGE_SOURCE_PATHS["cleaning"]).read_text()
        pages, _, _ = render_pages(
            registry, catalog, data, {}, page_sources={"cleaning": source}
        )
        self.assertEqual(pages["cleaning"], source)
        self.assertNotIn('id="purchase-checks"', source)
        self.assertNotIn("機種を比べる", source)
        self.assertNotIn("写真はAI生成の編集イメージ", source)
        with self.assertRaisesRegex(ValueError, "EDITORIAL_PAGE_SOURCE_INVALID"):
            render_pages(
                registry,
                catalog,
                data,
                {},
                page_sources={
                    "cleaning": source.replace(
                        'id="site-editorial-policy"', 'id="missing"'
                    )
                },
            )
