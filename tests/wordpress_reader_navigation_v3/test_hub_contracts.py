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
                    if n.attrs.get("aria-label") in {"このサイトの入口", "パンくずリスト"}
                )
                html = doc.text[nav.start : nav.end]
                self.assertIn('<a href="/">ホーム</a>', html)
                self.assertIn(
                    'aria-current="page">' + {'travel': 'スーツケース', 'cleaning': 'ロボット掃除機', 'preparedness': 'ポータブル電源', 'without-installation': '工事なし'}.get(slug, self.routes['/' + slug + '/']['title']),
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
                    self.assertIn('href="/kitchen/"' if slug == "without-installation" else 'href="/purposes/"', html)
                self.assertNotIn(
                    "<h1", doc.text
                )  # WordPress page template owns the title.

    def test_public_policy_explains_actual_advertising_without_release_markers(self):
        for slug, doc in self.pages.items():
            with self.subTest(slug=slug):
                self.assertIn('href="/about-ad-policy/"', doc.text)
                self.assertIn('href="/comparison-policy/"', doc.text)
                self.assertIn('aria-label="編集方針"', doc.text)
                self.assertNotIn("data-reader-release=", doc.text)

    def test_article_badges_match_public_body_bound_metadata(self):
        records = META["articles"]
        checked = 0
        for doc in self.pages.values():
            for card in (n for n in doc.nodes if n.tag == "article" and "ks-editorial-card" in (n.attrs.get("class") or "").split()):
                html = doc.text[card.start : card.end]
                match = re.search(r'<h3><a href="/([^/]+)/', html)
                if not match or match[1] not in records:
                    continue
                checked += 1
                self.assertEqual("ks-pr-badge" in html, records[match[1]]["has_ads"])
                record = records[match[1]]
                self.assertIn(
                    record["main_label"] + str(record["comparison_count"]) + "製品"
                    if record["comparison_count"]
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

    def test_guides_distinguish_ledger_tasks_from_three_category_procedures(self):
        doc = self.pages["guides"]
        guides = [
            r
            for r in self.rows
            if r["post_type"] == "post"
            and (r.get("listing") or {}).get("state") == "published"
            and r["listing"]["role"] == "guide"
        ]
        self.assertEqual(len(guides), 6)
        cards = [doc.text[n.start : n.end] for n in doc.nodes if n.tag == "article"]
        self.assertEqual(len(cards), len(guides) + 3)
        links = [
            re.search(r'<h3><a href="([^"]+)">([^<]+)</a>', c).groups() for c in cards
        ]
        self.assertEqual(sum("#" not in h for h, _ in links), len(guides))
        self.assertEqual(sum("#" in h for h, _ in links), 3)
        self.assertEqual(
            [t for _, t in links[: len(guides)]],
            [r["listing"]["task_label"] for r in guides],
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
        self.assertIn("比較記事内の説明：", doc.text)

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
                body = Document(
                    (ROOT / self.routes["/" + slug + "/"]["body_source"]).read_text()
                )
                self.assertIn(
                    'href="/' + slug + "/#" + a["comparison_anchor"] + '"', doc.text
                )
                self.assertIn(a["comparison_anchor"], body.ids)
                if a["offers_anchor"]:
                    self.assertIn(
                        'href="/' + slug + "/#" + a["offers_anchor"] + '"', doc.text
                    )
                    self.assertIn(a["offers_anchor"], body.ids)
                else:
                    self.assertNotIn('href="/' + slug + '/#ps-offers"', doc.text)

    def test_purposes_describe_different_questions_without_forced_first_read(self):
        doc = self.pages["purposes"]
        cards = [doc.text[n.start : n.end] for n in doc.nodes if n.tag == "article"]
        self.assertEqual(len(cards), 6)
        for card in cards:
            self.assertIn("？", card)
        self.assertNotRegex(doc.text, r"関連 ?[0-9]+記事")
        for ident, heading in (("purpose-before", "購入前に"), ("purpose-in-use", "使い始めてからの手間で選ぶ")):
            node = doc.ids[ident]
            self.assertIn("<h2>" + heading + "</h2>", doc.text[node.start : node.end])
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

    def test_updates_separate_new_articles_from_substantive_change_records(self):
        doc = self.pages["updates"]
        records = META["articles"]
        node = doc.ids["new-articles"]
        new = doc.text[node.start : node.end]
        slugs = re.findall(r'<h3><a href="/([^/]+)/', new)
        self.assertEqual(sorted(slugs), sorted(records))
        dates = [records[s]["published_on"] for s in slugs]
        self.assertEqual(dates, sorted(dates, reverse=True))
        for slug in slugs:
            self.assertIn("公開日：" + records[slug]["published_on"], new)
        node = doc.ids["updated-content"]
        changed = doc.text[node.start : node.end]
        entries = [e for r in records.values() for e in r["change_log"]]
        self.assertEqual(len(re.findall(r"<h3><a ", changed)), len(entries))
        for entry in entries:
            reason = ("訂正：" if entry["kind"] == "correction" else "") + entry["summary"]
            self.assertIn(reason, changed)
            self.assertIn("内容更新日：" + entry["date"], changed)
        self.assertNotIn("訂正日", doc.text)
        found = re.findall(r"内容更新日：(\d{4}-\d{2}-\d{2})", changed)
        self.assertEqual(found, sorted(found, reverse=True))
