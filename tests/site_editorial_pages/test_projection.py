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
        changed = copy.deepcopy(registry)
        slug = "countertop-dishwasher-for-small-households"
        row = next(r for r in changed["articles"] if r["slug"] == slug)
        row["listing"].update(
            published_on=None,
            published_at_gmt=None,
            change_log=[
                {
                    "date": "2026-09-13",
                    "kind": "content",
                    "summary": "比較対象の構成を整理しました。",
                }
            ],
        )
        record = metadata(
            changed,
            catalog,
            data,
            {slug: '<a href="https://example.com" rel="sponsored">販売先</a>'},
        )[slug]
        self.assertTrue(record["has_ads"])
        self.assertIsNone(record["published_on"])
        self.assertEqual(record["updated_on"], "2026-09-13")
        # Counts are the ledger listing's, which must agree with the catalog scope.
        self.assertEqual(record["comparison_count"], row["listing"]["main_count"])
        self.assertEqual(
            record["comparison_count"],
            len(
                next(a for a in catalog["articles"] if a["slug"] == slug)["product_ids"]
            ),
        )
        pages, _, _ = render_pages(changed, catalog, data, {})
        self.assertIn("比較対象の構成を整理しました。", pages["updates"])
        self.assertNotIn("内容更新日：", pages["home"])
        self.assertIn("内容更新日：2026-09-13", pages["updates"])
        self.assertNotIn("新しく公開：2026-09-13", pages["updates"])
        row["listing"]["change_log"].append(
            {
                "date": "2026-09-15",
                "kind": "correction",
                "summary": "寸法の表記を訂正しました。",
            }
        )
        self.assertEqual(
            metadata(changed, catalog, data, {})[slug]["updated_on"], "2026-09-15"
        )

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
        listing = next(
            r
            for r in registry["articles"]
            if r["slug"] == "dishwasher-branch-faucet-guide"
        )["listing"]
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
                with self.assertRaisesRegex(ValueError, "Missing editorial listing"):
                    render_pages(changed, catalog, data, {})
                changed["articles"][-1]["listing"] = dict(
                    copy.deepcopy(listing), state="draft"
                )
                self.assertEqual(render_pages(changed, catalog, data, {}), baseline)
                changed["articles"][-1]["listing"]["state"] = "withdrawn"
                self.assertEqual(render_pages(changed, catalog, data, {}), baseline)
                changed["articles"][-1].update(mode="new", post_id=None)
                changed["articles"][-1]["listing"]["state"] = "published"
                with self.assertRaisesRegex(ValueError, "LEDGER_IDENTITY_STALE"):
                    render_pages(changed, catalog, data, {})

    def test_prepare_outage_is_a_paper_worksheet_with_worked_example(self):
        from scripts.raos_reader_live_patch import Document

        body = next(
            b for p, b in builder.build().items() if p.name == "prepare-outage.html"
        )
        self.assertIn("記入式", body)
        self.assertIn("自動で計算はしません", body)
        for tag in ("<form", "<input", "<select", "<textarea"):
            self.assertNotIn(tag, body)
        doc = Document(body)
        tables = [n for n in doc.nodes if n.tag == "table"]
        self.assertEqual(len(tables), 1)
        table = body[tables[0].start : tables[0].end]
        headers = re.findall(r'<th scope="col"[^>]*>([^<]+)</th>', table)
        self.assertEqual(
            headers,
            [
                "使う機器",
                "消費電力W・同時に使うか",
                "必要時間",
                "起動時の条件",
                "動かす場所・手持ちの備え",
            ],
        )
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)[1:]
        cells = [
            [
                re.sub(r"<[^>]+>", "", c)
                for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)
            ]
            for r in rows
        ]
        examples = [r for r in cells if r[0].startswith("記入例")]
        self.assertEqual(len(examples), 2)
        self.assertEqual(examples[0][1:3], ["10W扇風機と同時", "8時間"])
        self.assertEqual(examples[1][1:3], ["40W合わせて50W", "4時間"])
        # Five columns stay readable at 320px; the blank rule lives in the lead.
        self.assertTrue(all(len(r) == 5 for r in cells))
        self.assertIn("未確認なら空欄のままにします", body)
        self.assertFalse(any("未確認なら空欄" in c for r in cells for c in r))
        self.assertTrue(all(len(c) <= 16 for r in cells for c in r))
        blank = [r for r in cells if all(set(c) <= set("＿W時間") for c in r)]
        self.assertGreaterEqual(len(blank), 2)
        self.assertIn("10W×8時間＋40W×4時間＝240Wh", body)
        self.assertNotEqual(
            next(
                n.attrs.get("aria-label")
                for n in doc.nodes
                if n.attrs.get("role") == "region" and n.start < tables[0].start < n.end
            ),
            "確認項目の表",
        )
        self.assertIn('href="/portable-power-station-guide/#ps-decision-steps"', body)
        self.assertIn("電源を買い足す必要はありません", body)
        self.assertIn("定格1000W・1500Wなどの階級だけで起動を保証しません", body)

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
        self.assertNotIn("商品カテゴリー", home)
        self.assertEqual(
            home.count('<h2 id="km-articles-title">商品カテゴリ</h2>'), 1
        )
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
