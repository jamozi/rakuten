"""Accepted September 13 entry contracts; runtime publication is separate evidence."""

import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from scripts.raos_reader_live_patch import Document

ROOT = Path(__file__).resolve().parents[2]
DIRECT = ROOT / "changes/wordpress-direct-publish-v1"
DATA = json.loads(
    (ROOT / "changes/site-improvements-20260913/entry-pages.v1.json").read_text()
)
META = json.loads(
    (
        ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/site-editorial-metadata.v1.json"
    ).read_text()
)


class HubContracts(unittest.TestCase):
    def setUp(self):
        self.pages = {
            s: Document((DIRECT / "articles" / (s + ".html")).read_text())
            for s in DATA["pages"]
            if s not in ("home", "kitchen")
        }
        self.rows = json.loads((DIRECT / "articles.v1.json").read_text())["articles"]
        self.routes = {"/" + r["slug"] + "/": r for r in self.rows}

    def test_breadcrumbs_show_actual_parent_and_current_title(self):
        for slug, doc in self.pages.items():
            with self.subTest(slug=slug):
                nav = next(
                    n
                    for n in doc.nodes
                    if n.attrs.get("aria-label") == "このサイトの入口"
                )
                html = doc.text[nav.start : nav.end]
                self.assertIn('<a href="/">ホーム</a>', html)
                self.assertIn(
                    'aria-current="page">' + self.routes["/" + slug + "/"]["title"],
                    html,
                )
                if slug in DATA["categories"]:
                    self.assertIn('href="/categories/"', html)
                elif slug not in (
                    "categories",
                    "purposes",
                    "guides",
                    "comparisons",
                    "updates",
                ):
                    self.assertIn('href="/purposes/"', html)
                self.assertNotIn(
                    "<h1", doc.text
                )  # WordPress page template owns the title.

    def test_public_policy_explains_actual_advertising_without_release_markers(self):
        for slug, doc in self.pages.items():
            with self.subTest(slug=slug):
                self.assertIn("記事ごとの広告表示は実際のリンクに基づきます", doc.text)
                self.assertIn("掲載順・評価は報酬条件と切り離しています", doc.text)
                self.assertIn('aria-label="編集方針"', doc.text)
                self.assertNotIn("data-reader-release=", doc.text)

    def test_article_badges_match_public_body_bound_metadata(self):
        records = META["articles"]
        checked = 0
        for doc in self.pages.values():
            for card in (n for n in doc.nodes if n.tag == "article"):
                html = doc.text[card.start : card.end]
                match = re.search(r'<h3><a href="/([^/]+)/', html)
                if not match or match[1] not in records:
                    continue
                checked += 1
                self.assertEqual("ks-pr-badge" in html, records[match[1]]["has_ads"])
                self.assertIn(
                    "主比較" + str(records[match[1]]["comparison_count"]) + "製品"
                    if records[match[1]]["comparison_count"]
                    else "ガイド記事",
                    html,
                )
        self.assertGreater(checked, 30)

    def test_all_legacy_ids_are_unique_readable_destinations(self):
        for slug, doc in self.pages.items():
            for ident in DATA["pages"][slug]["anchors"]:
                with self.subTest(slug=slug, ident=ident):
                    n = doc.ids[ident]
                    self.assertNotEqual(n.attrs.get("aria-hidden"), "true")
                    self.assertTrue(
                        re.sub(
                            "<[^>]+>", "", doc.text[n.open_end : n.close_start]
                        ).strip()
                        or n.tag == "img"
                    )
            for n in doc.nodes:
                if n.tag == "a" and (n.attrs.get("href") or "").startswith("#"):
                    self.assertIn(n.attrs["href"][1:], doc.ids)

    def test_guides_distinguish_five_tasks_from_three_category_procedures(self):
        doc = self.pages["guides"]
        cards = [doc.text[n.start : n.end] for n in doc.nodes if n.tag == "article"]
        self.assertEqual(len(cards), 8)
        links = [
            re.search(r'<h3><a href="([^"]+)">([^<]+)</a>', c).groups() for c in cards
        ]
        self.assertEqual(sum("#" not in h for h, _ in links), 5)
        self.assertEqual(sum("#" in h for h, _ in links), 3)
        self.assertEqual(
            [t for _, t in links[:5]],
            [
                "置き場所を測る",
                "給水作業を比べる",
                "専用洗剤と量を確かめる",
                "型番別の清掃を確かめる",
                "1回・月額を試算する",
            ],
        )
        for href, _ in links:
            url = urlsplit(href)
            target = self.routes[url.path]
            if url.fragment:
                self.assertIn(
                    url.fragment,
                    Document((ROOT / target["body_source"]).read_text()).ids,
                )
        self.assertIn("ガイド記事：", doc.text)
        self.assertIn("比較記事の選び方：", doc.text)

    def test_comparison_index_has_each_comparison_once_and_both_destinations(self):
        doc = self.pages["comparisons"]
        headings = re.findall(r'<h3><a href="([^"]+)">', doc.text)
        expected = {
            "/" + s + "/" for s, a in META["articles"].items() if a["comparison_count"]
        }
        self.assertEqual(set(headings), expected)
        self.assertEqual(len(headings), len(expected))
        for slug, a in META["articles"].items():
            if a["comparison_count"]:
                self.assertIn(
                    'href="/' + slug + "/#" + a["comparison_anchor"] + '"', doc.text
                )
                self.assertIn('href="/' + slug + '/#ps-offers"', doc.text)

    def test_purposes_describe_different_questions_without_forced_first_read(self):
        doc = self.pages["purposes"]
        cards = [doc.text[n.start : n.end] for n in doc.nodes if n.tag == "article"]
        self.assertEqual(len(cards), 6)
        for card in cards:
            self.assertIn("？", card)
            self.assertRegex(card, r"関連 [1-9]記事")
        self.assertIn("順番に全ページを読む必要はありません", doc.text)
        for slug in (
            "small-space",
            "save-housework",
            "without-installation",
            "easy-maintenance",
            "comfortable-travel",
            "prepare-outage",
        ):
            self.assertIn('href="/' + slug + '/"', doc.text)
            self.assertGreater(len(re.sub("<[^>]+>", "", self.pages[slug].text)), 300)

    def test_updates_cover_all_articles_using_substantive_change_records(self):
        doc = self.pages["updates"]
        cards = [doc.text[n.start : n.end] for n in doc.nodes if n.tag == "article"]
        self.assertEqual(len(cards), 15)
        dates = []
        for card in cards:
            slug = re.search(r'<h3><a href="/([^/]+)/', card)[1]
            record = META["articles"][slug]
            self.assertIn(record["change_summary"], card)
            self.assertIn("内容更新日：" + record["updated_on"], card)
            self.assertIn("公開日：" + record["published_on"], doc.text)
            dates.append(record["updated_on"])
        self.assertEqual(dates, sorted(dates, reverse=True))
