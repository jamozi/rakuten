"""Remaining accepted entry actions, using in-memory generation only."""

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import unittest

from raos.application.editorial.purchase_support import hub_sales_record, render_hub
from raos.application.editorial.site_editorial_pages import render_pages
from scripts.raos_reader_live_patch import Document

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"


class EntryCompletion(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads(CATALOG.read_text())
        self.now = datetime(2026, 9, 13, 15, tzinfo=timezone.utc)

    def test_kitchen_routes_by_capacity_and_water_without_seller_inventory(self):
        template = (
            ROOT / "changes/reader-purchase-support-v1/articles/kitchen.html"
        ).read_text()
        doc = Document(render_hub({}, self.catalog, template, now=self.now))
        capacity = doc.ids["kitchen-comparisons"]
        capacity_html = doc.text[capacity.start : capacity.end]
        for label, destination in (
            ("コンパクト", "/compact-dishwasher-comparison/"),
            ("標準", "/standard-dishwasher-comparison/"),
            ("大容量", "/large-dishwasher-comparison/"),
        ):
            self.assertIn(label, capacity_html)
            self.assertIn(destination, capacity_html)
        self.assertEqual(capacity_html.count("<img "), 3)
        self.assertNotIn("大容量比較は未掲載", capacity_html)
        choose = doc.ids["choose"]
        supply_html = doc.text[choose.start : choose.end]
        for destination in (
            "/without-installation/",
            "/dishwasher-branch-faucet-guide/",
            "/dishwasher-water-supply-methods/",
        ):
            self.assertIn(destination, supply_html)
        for label in ("工事なし（タンク式など）", "工事あり", "違いを知りたい"):
            self.assertIn(label, supply_html)
        registry = json.loads(
            (ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json").read_text()
        )
        for slug, post_id in (
            ("compact-dishwasher-comparison", 549),
            ("standard-dishwasher-comparison", 550),
            ("large-dishwasher-comparison", 551),
            ("dishwasher-branch-faucet-guide", 552),
        ):
            row = next(row for row in registry["articles"] if row["slug"] == slug)
            self.assertTrue((ROOT / row["body_source"]).is_file())
            # Published on 2026-09-13; owner-direct status delegates these ids.
            self.assertEqual((row["mode"], row["post_id"]), ("existing", post_id))
        self.assertLess(capacity.start, choose.start)
        self.assertLess(choose.start, doc.ids["compare"].start)
        self.assertNotIn("kitchen-after-buying", doc.ids)
        self.assertNotIn('href="#kitchen-after-buying"', doc.text)
        for stale_inventory in (
            "確認期限切れ",
            "確認日時は未確認",
            "mini Plus",
            "SS-MA251",
        ):
            self.assertNotIn(stale_inventory, doc.text)
        self.assertNotRegex(doc.text, r"[0-9,]+円")

    def test_kitchen_compare_routes_to_capacity_comparisons_and_cost_guide(self):
        template = (
            ROOT / "changes/reader-purchase-support-v1/articles/kitchen.html"
        ).read_text()
        doc = Document(render_hub({}, self.catalog, template, now=self.now))
        compare = doc.ids["compare"]
        html = doc.text[compare.start : compare.end]
        self.assertIn("<h2>置き場所・機能・費用を確かめる</h2>", html)
        self.assertIn(
            "採寸する箇所の考え方と費用の式の立て方は参考にできますが、数値と手順は選んだ型番の取扱説明書で確かめてください。型番別の数値を載せたガイドは、対象機種をガイド側に明記しています。",
            html,
        )
        self.assertNotIn("ほかの条件も確かめる", doc.text)
        registry = json.loads(
            (ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json").read_text()
        )
        rows = {row["slug"]: row for row in registry["articles"]}
        hrefs = [n.attrs.get("href") or "" for n in doc.nodes if n.tag == "a"]
        compare_hrefs = [
            n.attrs.get("href") or ""
            for n in doc.nodes
            if n.tag == "a" and compare.start < n.start < compare.end
        ]
        for href in (
            "/dishwasher-installation-measurement/#guide-measurement-diagram",
            "/compact-dishwasher-comparison/#compact-compare",
            "/standard-dishwasher-comparison/#std-comparison",
            "/large-dishwasher-comparison/#large-compare",
            "/standard-dishwasher-comparison/#std-purchases",
            "/large-dishwasher-comparison/#large-purchase",
            "/dishwasher-running-cost/#guide-cost-example",
        ):
            with self.subTest(href=href):
                self.assertIn(href, compare_hrefs)
                slug, fragment_id = href.strip("/").split("/#")
                body = Document((ROOT / rows[slug]["body_source"]).read_text())
                self.assertIn(fragment_id, body.ids)
        purchase = doc.ids["purchase-checks"]
        self.assertTrue(compare.start < purchase.start < purchase.end <= compare.end)
        purchase_html = doc.text[purchase.start : purchase.end]
        for href in (
            "/compact-dishwasher-comparison/#compact-compare",
            "/standard-dishwasher-comparison/#std-purchases",
            "/large-dishwasher-comparison/#large-purchase",
            "/dishwasher-running-cost/#guide-cost-example",
        ):
            self.assertIn('href="' + href + '"', purchase_html)
        tank = [
            h
            for h in hrefs
            if h.startswith("/countertop-dishwasher-for-small-households/")
        ]
        self.assertEqual(tank, ["/countertop-dishwasher-for-small-households/"])
        self.assertIn(
            '<a href="/countertop-dishwasher-for-small-households/">タンク式4機種の給水作業を詳しく比べる</a>',
            html,
        )
        for removed in ("#ps-specs", "#dish-meal-work-title", "#ps-offers"):
            self.assertFalse(any(h.endswith(removed) for h in hrefs), removed)

    def test_branch_faucet_guide_routes_to_capacity_comparisons(self):
        registry = json.loads(
            (ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json").read_text()
        )
        rows = {row["slug"]: row for row in registry["articles"]}
        row = rows["dishwasher-branch-faucet-guide"]
        doc = Document((ROOT / row["body_source"]).read_text())
        consult = doc.ids["branch-consult"]
        consult_html = doc.text[consult.start : consult.end]
        for slug, anchor in (
            ("standard-dishwasher-comparison", "std-comparison"),
            ("large-dishwasher-comparison", "large-compare"),
        ):
            self.assertIn('href="/' + slug + "/#" + anchor + '"', consult_html)
            self.assertIn(
                anchor, Document((ROOT / rows[slug]["body_source"]).read_text()).ids
            )
        self.assertIn("給水方式（タンク／分岐水栓など）", consult_html)
        self.assertIn("標準容量の比較（掲載機種は16〜28点）", consult_html)
        self.assertNotIn("「給水」欄", doc.text)
        check = doc.ids["branch-check"]
        check_html = doc.text[check.start : check.end]
        self.assertEqual(
            re.findall(r'<th scope="row">([^<]+)</th>', check_html),
            ["本体側", "水栓側", "設置条件"],
        )
        table = check_html[check_html.index("<table") :]
        # Routes only: no measured or model-specific values in the new table.
        self.assertNotRegex(
            re.sub(r"<[^>]+>", "", table[: table.index("</table>")]),
            r"[0-9]+(?:mm|cm|m|L|MPa|kPa|円|℃|W)",
        )
        self.assertIn("仕様欄にある給水方式", table)
        notes = (
            ROOT
            / "changes/site-improvements-20260913/article-sources/dishwasher-branch-faucet-guide.md"
        ).read_text()
        self.assertIn("#std-comparison", notes)
        self.assertIn("本体側", notes)

    def test_travel_source_lists_published_comparisons_without_pending_cards(self):
        from scripts.build_site_editorial_pages import PAGE_SOURCE_PATHS

        source = (ROOT / PAGE_SOURCE_PATHS["travel"]).read_text()
        notes = (
            ROOT / "changes/site-improvements-20260913/entry-pages/travel.sources.md"
        ).read_text()
        doc = Document(source)
        self.assertNotIn("準備中", source)
        self.assertNotIn("kt-card-pending", source)
        self.assertNotIn("飛行機に乗るなら", source)
        for image in ("travel-medium-", "travel-large-", "travel-move-"):
            self.assertNotIn(image, source)
        for heading in (
            "荷物の量から選ぶ",
            "使いやすさから選ぶ",
            "便やブランドが決まっているなら",
        ):
            self.assertEqual(
                len(re.findall("<h2[^>]*>" + heading + "</h2>", source)), 1
            )
        flight = next(
            n
            for n in doc.nodes
            if n.tag == "section"
            and "便やブランドが決まっているなら" in doc.text[n.start : n.end]
        )
        flight_html = doc.text[flight.start : flight.end]
        self.assertLess(doc.ids["travel-comparisons"].end, flight.start)
        cards = [
            doc.text[n.start : n.end]
            for n in doc.nodes
            if n.tag == "article" and flight.start < n.start < flight.end
        ]
        self.assertEqual(len(cards), 2)
        under_100, ace = cards
        self.assertIn('href="/carry-on-suitcase-under-100-seats/"', under_100)
        self.assertIn(
            "100席未満の便の条件です。100席以上の便とは条件が違います", under_100
        )
        self.assertIn('href="/carry-on-suitcase-comparison/"', ace)
        self.assertIn(
            "エース系3モデル（外寸はANA国内線100席以上の基準で照合。重量は荷物込みで別途確認）",
            ace,
        )
        self.assertNotIn("<img", flight_html)
        if "45×35×20cm" in under_100:
            for url in (
                "https://www.jal.co.jp/jp/ja/dom/baggage/inflight/",
                "https://www.ana.co.jp/ja/jp/notice/carry-on-baggage/20260601/",
            ):
                self.assertIn(url, notes)
            self.assertIn("45×35×20cm", notes)
            self.assertIn("#carry-on-rules", notes)
        details = doc.ids["purchase-checks"]
        details_html = doc.text[details.start : details.end]
        for slug in (
            "carry-on-suitcase-under-100-seats",
            "carry-on-suitcase-comparison",
        ):
            for anchor in ("ps-specs", "ps-offers"):
                self.assertIn('href="/' + slug + "/#" + anchor + '"', details_html)
        self.assertIn("再掲", notes)

    def test_seller_record_is_model_bound_historical_and_keeps_unknown(self):
        product = self.catalog["products"][0]
        offer = next(
            o
            for o in self.catalog["offers"]
            if o["product_id"] == product["product_id"]
        )
        catalog = copy.deepcopy(self.catalog)
        catalog["offers"] = [
            {
                **offer,
                "checked_at": "2026-09-13T14:00:00Z",
                "valid_until": "2026-09-14T14:00:00Z",
                "state": "AVAILABLE",
            }
        ]
        fresh = hub_sales_record(product, catalog, self.now)
        self.assertIn("確認時は注文可の表示", fresh)
        self.assertIn("確認日時：2026年9月13日 23:00 JST", fresh)
        self.assertNotIn("確認期限切れ", fresh)
        self.assertNotIn(str(offer["price_yen"]), fresh)
        catalog["offers"][0]["valid_until"] = "2026-09-13T14:30:00Z"
        self.assertIn("確認期限切れ", hub_sales_record(product, catalog, self.now))
        catalog["offers"][0]["identity_verified"] = False
        self.assertIn("確認日時は未確認", hub_sales_record(product, catalog, self.now))
        catalog["offers"][0]["identity_verified"] = True
        catalog["offers"][0]["checked_at"] = "2026-09-14T14:00:00Z"
        self.assertIn("確認日時は未確認", hub_sales_record(product, catalog, self.now))

    def test_missing_seller_deadline_and_legacy_catalog_remain_safe(self):
        product = self.catalog["products"][0]
        offer = next(
            o
            for o in self.catalog["offers"]
            if o["product_id"] == product["product_id"]
        )
        catalog = copy.deepcopy(self.catalog)
        catalog["offers"] = [{**offer, "seller_id": ""}]
        self.assertIn("確認日時は未確認", hub_sales_record(product, catalog, self.now))
        catalog["offers"] = [{**offer, "valid_until": None}]
        text = hub_sales_record(product, catalog, self.now)
        self.assertIn("記録の有効期限：未確認", text)
        self.assertNotIn("未確認 JST", text)
        self.assertIn("現在の状況は未確認", text)
        catalog["articles"] = [a for a in catalog["articles"] if a["post_id"] != 86]
        template = (
            ROOT / "changes/reader-purchase-support-v1/articles/kitchen.html"
        ).read_text()
        self.assertIn('id="choose"', render_hub({}, catalog, template, now=self.now))

    def test_power_memo_and_travel_comparison_links(self):
        registry = json.loads(
            (ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json").read_text()
        )
        data = json.loads(
            (
                ROOT / "changes/site-improvements-20260913/entry-pages.v1.json"
            ).read_text()
        )
        pages, _, _ = render_pages(registry, self.catalog, data, {})
        power = pages["preparedness"]
        for text in (
            "用途：何を使うか",
            "時間：何時間使うか",
            "同時使用：一緒に動かす機器",
        ):
            self.assertIn(text, power)
        self.assertEqual(power.count("記入："), 3)
        self.assertIn("/portable-power-station-guide/#ps-decision-steps", power)
        travel = Document(pages["travel"])
        urls = [n.attrs.get("href") for n in travel.nodes if n.tag == "a"]
        for slug in (
            "carry-on-suitcase-under-100-seats",
            "lightweight-carry-on-suitcase-under-3kg",
            "front-open-carry-on-suitcase-with-stopper",
            "carry-on-suitcase-comparison",
        ):
            self.assertIn("/" + slug + "/#ps-specs", urls)
            self.assertIn(
                "ps-specs",
                Document(
                    (
                        ROOT
                        / "changes/wordpress-direct-publish-v1/articles"
                        / (slug + ".html")
                    ).read_text()
                ).ids,
            )
