"""Remaining accepted entry actions, using in-memory generation only."""

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
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
