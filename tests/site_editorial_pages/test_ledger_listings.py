"""Ledger-owned lists, counts, dates and anchors (plan section 3.1, batch F).

Every test here failed before batch F moved listings into the article ledger,
except the ones whose docstring starts with "Regression".
"""

from __future__ import annotations

from collections import Counter
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import re
import unittest

from scripts.raos_reader_live_patch import Document

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "site_builder_ledger", ROOT / "scripts/build_site_editorial_pages.py"
)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

from raos.application.editorial import site_editorial_pages as editorial  # noqa: E402

NEW_POST_IDS = {
    "compact-dishwasher-comparison": 549,
    "standard-dishwasher-comparison": 550,
    "large-dishwasher-comparison": 551,
    "dishwasher-branch-faucet-guide": 552,
    "small-carry-on-suitcase-comparison": 553,
}
# Anonymous GET /wp-json/wp/v2/posts/<id>?_fields=id,date_gmt,modified_gmt,slug on 2026-09-15.
REST_DATE_GMT = {
    "compact-dishwasher-comparison": "2026-09-13T10:57:35Z",
    "standard-dishwasher-comparison": "2026-09-13T10:58:27Z",
    "large-dishwasher-comparison": "2026-09-13T10:58:06Z",
    "dishwasher-branch-faucet-guide": "2026-09-13T10:58:04Z",
    "small-carry-on-suitcase-comparison": "2026-09-13T10:57:43Z",
}
LISTING_KEYS = {
    "state",
    "role",
    "category",
    "short_title",
    "task_label",
    "main_label",
    "main_count",
    "reference_count",
    "reference_label",
    "reference_unit",
    "comparison_anchor",
    "offers_anchor",
    "card_image",
    "published_at_gmt",
    "published_on",
    "home_order",
    "change_log",
    "specification_checked_on",
    "sales_checked_at",
}
JST = timezone(timedelta(hours=9))
HUB_PAGES = ("home", "categories", "comparisons", "updates", "guides", "purposes")
# Wording replaced in earlier batch F rounds; none may come back on a hub.
BANNED_HUB_WORDS = (
    "移動で選ぶ",
    "移動のしやすさ",
    "任せる作業",
    "任せたい作業",
    "洗う量",
    "採寸・条件整理",
)
# Key nouns of each home category decision; each must be in the representative body.
HOME_DECISION_WORDS = {
    "travel": ("軽さ", "開き方", "車輪"),
    "kitchen": ("食器量", "給水方法"),
    "cleaning": ("本体", "台", "置き場所", "自動ゴミ収集", "水拭き"),
    "preparedness": ("機器", "時間", "容量", "出力"),
}
CATEGORIES_LEAD = (
    "スーツケース・食洗機・ロボット掃除機・ポータブル電源から選べます。"
    "代表比較と、条件で候補を絞る節へ直接進めます。"
)
NAVIGATION_ASSET = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/"
    "assets/editorial-navigation.v3.json"
)


def inputs():
    return [json.loads((ROOT / p).read_text()) for p in builder.INPUT_PATHS[:3]]


def published_posts(registry):
    return [
        r
        for r in registry["articles"]
        if r["post_type"] == "post"
        and r.get("mode") == "existing"
        and (r.get("listing") or {}).get("state") == "published"
    ]


def body_text(row):
    body = (ROOT / row["body_source"]).read_text()
    return re.sub(r"<[^>]+>", "", re.sub(r"<script.*?</script>", "", body, flags=re.S))


def walk(node):
    if isinstance(node, dict):
        yield node
        values = node.values()
    elif isinstance(node, list):
        values = node
    else:
        return
    for value in values:
        yield from walk(value)


def section(html, ident):
    node = Document(html).ids[ident]
    return html[node.start : node.end]


def heading_slugs(html):
    return re.findall(r'<h3><a href="/([^/"#]+)/', html)


def cards(html):
    doc = Document(html)
    return [
        html[n.start : n.end]
        for n in doc.nodes
        if n.tag == "article"
        and "ks-editorial-card" in (n.attrs.get("class") or "").split()
    ]


def card_for(html, slug):
    return next(c for c in cards(html) if f'<h3><a href="/{slug}/' in c)


class LedgerListings(unittest.TestCase):
    def setUp(self):
        self.data, self.registry, self.catalog = inputs()
        self.pages, self.meta, _ = editorial.render_pages(
            self.registry, self.catalog, self.data, {}
        )

    def test_new_posts_are_existing_rows_with_full_taxonomies(self):
        rows = {r["article_key"]: r for r in self.registry["articles"]}
        for key, post_id in NEW_POST_IDS.items():
            with self.subTest(key=key):
                row = rows[key]
                self.assertEqual(
                    (row["mode"], row["post_id"], row["post_type"], row["slug"]),
                    ("existing", post_id, "post", key),
                )
                self.assertEqual(
                    row["taxonomies"],
                    {"category": [5], "post_format": [], "post_tag": []},
                )
        for article in self.catalog["articles"]:
            if article["slug"] in rows:
                self.assertEqual(article["post_id"], rows[article["slug"]]["post_id"])

    def test_every_post_row_has_a_complete_listing(self):
        posts = [r for r in self.registry["articles"] if r["post_type"] == "post"]
        self.assertEqual(len(posts), 20)
        for row in posts:
            with self.subTest(slug=row["slug"]):
                listing = row["listing"]
                self.assertEqual(set(listing), LISTING_KEYS)
                self.assertEqual(listing["state"], "published")
                if listing["role"] == "guide":
                    self.assertTrue(listing["task_label"])
                    self.assertIsNone(listing["comparison_anchor"])
                else:
                    self.assertEqual(listing["role"], "comparison")
                    self.assertGreater(listing["main_count"], 0)
                    self.assertTrue(listing["comparison_anchor"])
        self.assertEqual(
            Counter(r["listing"]["role"] for r in posts),
            {"comparison": 14, "guide": 6},
        )
        self.assertEqual(
            Counter(r["listing"]["category"] for r in posts),
            {"kitchen": 11, "travel": 5, "cleaning": 2, "preparedness": 2},
        )

    def test_comparison_index_is_every_ledger_comparison_with_its_own_anchors(self):
        html = self.pages["comparisons"]
        expected = [
            r["slug"]
            for r in published_posts(self.registry)
            if r["listing"]["role"] == "comparison"
        ]
        self.assertEqual(len(expected), 14)
        self.assertEqual(sorted(heading_slugs(html)), sorted(expected))
        for row in published_posts(self.registry):
            listing = row["listing"]
            if listing["role"] != "comparison":
                continue
            with self.subTest(slug=row["slug"]):
                base = "/" + row["slug"] + "/#"
                if listing["offers_anchor"]:
                    self.assertIn(
                        f'href="{base}{listing["comparison_anchor"]}">比較表へ</a>',
                        html,
                    )
                    self.assertIn(
                        f'href="{base}{listing["offers_anchor"]}">販売条件へ</a>', html
                    )
                else:
                    self.assertIn(
                        f'href="{base}{listing["comparison_anchor"]}">比較表・販売条件へ</a>',
                        html,
                    )
                    self.assertNotIn(base + "ps-offers", html)

    def test_guides_list_every_ledger_guide_then_in_article_sections(self):
        html = self.pages["guides"]
        first = section(html, "kitchen-guides")
        guides = [
            r for r in published_posts(self.registry) if r["listing"]["role"] == "guide"
        ]
        self.assertEqual(
            re.findall(r'<h3><a href="/[^"#]+/">([^<]+)</a>', first),
            [r["listing"]["task_label"] for r in guides],
        )
        self.assertIn("蛇口の品番と設置費用を確かめる", first)
        self.assertIn("<h2>比較記事内の説明：採寸と条件整理</h2>", html)
        self.assertNotIn("比較記事の選び方：", html)
        for item in self.data["guides_in_article"]:
            node = Document(html).ids[item["category"] + "-guides"]
            self.assertIn(
                f'href="/{item["article_key"]}/#{item["anchor"]}"',
                html[node.start : node.end],
            )

    def test_updates_separate_content_changes_from_new_articles(self):
        html = self.pages["updates"]
        updated = section(html, "updated-content")
        new = section(html, "new-articles")
        posts = published_posts(self.registry)
        self.assertEqual(sorted(heading_slugs(new)), sorted(r["slug"] for r in posts))
        entries = [(r, e) for r in posts for e in r["listing"]["change_log"]]
        self.assertEqual(len(heading_slugs(updated)), len(entries))
        dates = re.findall(r"内容更新日：(\d{4}-\d{2}-\d{2})", updated)
        self.assertEqual(len(dates), len(entries))
        self.assertEqual(dates, sorted(dates, reverse=True))
        published = re.findall(r"公開日：(\d{4}-\d{2}-\d{2})", new)
        self.assertNotIn("訂正日", html)
        self.assertEqual(len(published), len(posts))
        self.assertEqual(published, sorted(published, reverse=True))
        corrections = {r["slug"]: e for r, e in entries if e["date"] == "2026-09-15"}
        self.assertEqual(
            set(corrections),
            {
                "portable-power-station-guide",
                "front-open-carry-on-suitcase-with-stopper",
            },
        )
        for slug, entry in corrections.items():
            self.assertEqual(entry["kind"], "correction")
            self.assertIn("訂正：" + entry["summary"], card_for(updated, slug))
            self.assertIn("内容更新日：2026-09-15", card_for(updated, slug))
        self.assertIn("価格だけの再取得では内容更新日を進めません", html)

    def test_updated_content_cards_carry_their_own_publication_date(self):
        updated = section(self.pages["updates"], "updated-content")
        posts = {r["slug"]: r for r in published_posts(self.registry)}
        entries = [e for r in posts.values() for e in r["listing"]["change_log"]]
        found = cards(updated)
        self.assertEqual(len(found), len(entries))
        for card in found:
            slug = heading_slugs(card)[0]
            published_on = posts[slug]["listing"]["published_on"]
            meta = re.search(r'<p class="ks-card-meta">(.*?)</p>', card)[1]
            self.assertRegex(
                meta, r"内容更新日：\d{4}-\d{2}-\d{2} ／ 公開日：" + published_on + "$"
            )
        outside = re.sub(
            r'<article class="ks-editorial-card">.*?</article>', "", updated
        )
        self.assertNotIn("公開日", outside)

    def test_same_change_has_the_same_date_label_on_updates_and_hubs(self):
        posts = {r["slug"]: r for r in published_posts(self.registry)}
        updated = cards(section(self.pages["updates"], "updated-content"))
        checked = set()
        for name, html in self.pages.items():
            self.assertNotIn("訂正日", html, name)
            if name == "updates":
                continue
            for card in cards(html):
                slugs = heading_slugs(card)
                log = (
                    posts[slugs[0]]["listing"]["change_log"]
                    if slugs and slugs[0] in posts
                    else []
                )
                if not log:
                    continue
                if 'class="ks-recent-image"' in card:
                    # Home recent cards show no date at all, so they cannot disagree.
                    self.assertNotIn("日：", card)
                    continue
                label = "内容更新日：" + max(e["date"] for e in log)
                with self.subTest(page=name, slug=slugs[0]):
                    self.assertIn(label, card)
                    self.assertTrue(
                        any(
                            label in c
                            for c in updated
                            if heading_slugs(c)[0] == slugs[0]
                        )
                    )
                checked.add(slugs[0])
        self.assertTrue(
            {
                "portable-power-station-guide",
                "front-open-carry-on-suitcase-with-stopper",
            }
            <= checked
        )

    def test_ledger_rows_alone_add_and_withdraw_articles(self):
        self.assertIn(
            "食洗機の記事 11本（比較5本・ガイド6本）", self.pages["categories"]
        )
        changed = copy.deepcopy(self.registry)
        source = next(
            r
            for r in changed["articles"]
            if r["slug"] == "dishwasher-branch-faucet-guide"
        )
        extra = copy.deepcopy(source)
        extra.update(
            article_key="dishwasher-sample-guide",
            slug="dishwasher-sample-guide",
            post_id=999999,
            title="試験用のガイド",
        )
        extra["listing"].update(task_label="試験用の作業", home_order=None)
        changed["articles"].append(extra)
        pages, meta, _ = editorial.render_pages(changed, self.catalog, self.data, {})
        self.assertIn("dishwasher-sample-guide", meta)
        self.assertIn(
            'href="/dishwasher-sample-guide/"',
            section(pages["guides"], "kitchen-guides"),
        )
        self.assertIn(
            'href="/dishwasher-sample-guide/"',
            section(pages["updates"], "new-articles"),
        )
        self.assertIn("食洗機の記事 12本（比較5本・ガイド7本）", pages["categories"])
        source["listing"]["state"] = "withdrawn"
        pages, meta, _ = editorial.render_pages(changed, self.catalog, self.data, {})
        self.assertNotIn("dishwasher-branch-faucet-guide", meta)
        for slug, html in pages.items():
            self.assertNotIn("/dishwasher-branch-faucet-guide/", html, slug)
        self.assertIn("食洗機の記事 11本（比較5本・ガイド6本）", pages["categories"])

    def test_home_recent_uses_publication_day_then_editorial_order(self):
        recent = section(self.pages["home"], "km-updates-title")
        self.assertEqual(
            re.findall(r'<a class="ks-recent-image" href="/([^/]+)/"', recent),
            [
                "small-carry-on-suitcase-comparison",
                "compact-dishwasher-comparison",
                "standard-dishwasher-comparison",
                "large-dishwasher-comparison",
            ],
        )
        images = re.findall(
            r'<a class="ks-recent-image" href="[^"]+"><img src="([^"]+)"', recent
        )
        self.assertEqual(len(set(images)), 4)
        self.assertTrue(all(src.startswith("/wp-content/themes/") for src in images))
        reordered = copy.deepcopy(self.registry)
        reordered["articles"].reverse()
        pages, _, _ = editorial.render_pages(reordered, self.catalog, self.data, {})
        self.assertEqual(section(pages["home"], "km-updates-title"), recent)

    def test_home_lead_and_category_cards_state_decisions(self):
        home = self.pages["home"]
        self.assertIn(self.data["pages"]["home"]["lead"], home)
        self.assertNotIn("購入費用から", home)
        grid = section(home, "km-categories-title")
        for slug, category in self.data["categories"].items():
            with self.subTest(slug=slug):
                self.assertIn("<p>" + category["decides"] + "</p>", grid)
                representative = next(
                    r
                    for r in self.registry["articles"]
                    if r["article_key"] == category["representative"]
                )
                self.assertIn(
                    f'href="/{representative["slug"]}/">{representative["listing"]["short_title"]}</a>',
                    grid,
                )

    def test_counts_and_labels_come_from_the_listing(self):
        html = self.pages["comparisons"]
        self.assertIn(
            "主比較4製品・同系列の補足2製品",
            card_for(html, "large-dishwasher-comparison"),
        )
        self.assertIn("掲載13製品", card_for(html, "standard-dishwasher-comparison"))
        self.assertIn(
            "掲載12製品", card_for(html, "small-carry-on-suitcase-comparison")
        )
        self.assertIn(
            "主比較2製品・別構成1件", card_for(html, "roomba-mini-vs-switchbot-k11-pro")
        )
        self.assertNotIn("主比較6製品", html)
        self.assertIn(
            "公開日：2026-09-13", card_for(html, "standard-dishwasher-comparison")
        )
        self.assertIn(
            "内容更新日：2026-09-16", card_for(html, "compact-dishwasher-comparison")
        )
        record = self.meta["large-dishwasher-comparison"]
        self.assertEqual(
            (record["comparison_count"], record["reference_count"]), (4, 2)
        )

    def test_catalog_kind_does_not_change_roles_or_counts(self):
        changed = copy.deepcopy(self.catalog)
        for article in changed["articles"]:
            if article["kind"] in {"comparison", "curated_comparison"}:
                article["kind"] = (
                    "curated_comparison"
                    if article["kind"] == "comparison"
                    else "comparison"
                )
        self.assertEqual(
            editorial.metadata(self.registry, changed, self.data, {}), self.meta
        )

    def test_listing_anchors_must_exist_once_in_published_bodies(self):
        bodies = builder.load_bodies(self.registry)
        self.assertEqual(
            editorial.validate_listing_anchors(self.registry, bodies, self.pages), []
        )
        broken = dict(bodies)
        broken["compact-dishwasher-comparison"] = broken[
            "compact-dishwasher-comparison"
        ].replace('id="compact-compare"', 'id="compact-compare-moved"')
        self.assertIn(
            "EDITORIAL_ANCHOR_MISSING: compact-dishwasher-comparison#compact-compare",
            editorial.validate_listing_anchors(self.registry, broken, self.pages),
        )
        data = copy.deepcopy(self.data)
        data["categories"]["travel"]["choose"]["anchor"] = "missing-choose"
        pages, _, _ = editorial.render_pages(self.registry, self.catalog, data, {})
        self.assertIn(
            "EDITORIAL_ANCHOR_MISSING: carry-on-suitcase-under-100-seats#missing-choose",
            editorial.validate_listing_anchors(self.registry, bodies, pages),
        )

    def test_category_cards_count_ledger_articles_without_ad_counts(self):
        html = self.pages["categories"]
        self.assertNotIn("広告リンクを含む記事", html)
        names = {c["name"]: slug for slug, c in self.data["categories"].items()}
        found = 0
        for card in cards(html):
            match = re.search(
                r"<summary>(.+?)の記事 (\d+)本（([^）]+)）</summary>", card
            )
            if not match:
                continue
            found += 1
            slug = names[match[1]]
            rows = [
                r
                for r in published_posts(self.registry)
                if r["listing"]["category"] == slug
            ]
            details = card[card.index("<details") :]
            self.assertEqual(int(match[2]), len(rows))
            self.assertEqual(
                sorted(re.findall(r'<li><a href="/([^/"#]+)/">', details)),
                sorted(r["slug"] for r in rows),
            )
            top = re.findall(r'href="(/[^"]*)"', card[: card.index("<details")])
            self.assertEqual(len(top), len(set(top)), slug)
            self.assertNotRegex(
                card[: card.index("<details")], r'href="/' + slug + r'/">[^<]*\d+'
            )
        self.assertEqual(found, 4)

    def test_merged_representative_route_opens_the_article_top(self):
        html = self.pages["categories"]
        slugs = {r["article_key"]: r["slug"] for r in published_posts(self.registry)}
        names = {c["name"]: c for c in self.data["categories"].values()}
        merged = 0
        for card in cards(html):
            name = re.search(r"<h2>([^<]+)</h2>", card)[1]
            category = names[name]
            top = card[: card.index("<details")]
            main = slugs[category["representative"]]
            self.assertNotIn("代表比較を読む（", top)
            self.assertIn(f'href="/{main}/">代表比較を読む</a>', top)
            if category["choose"]["article_key"] == category["representative"]:
                merged += 1
                self.assertEqual(
                    re.findall(rf'href="/{main}/(#[^"]*)?"', top),
                    ["", "#" + category["choose"]["anchor"]],
                )
        self.assertEqual(merged, 2)

    def test_every_category_card_third_link_names_its_landing_heading(self):
        html = self.pages["categories"]
        lead = re.search(r'<div id="category-cards"><p>([^<]+)</p>', html)[1]
        self.assertNotIn("採寸", lead)
        rows = {r["article_key"]: r for r in published_posts(self.registry)}
        names = {c["name"]: c for c in self.data["categories"].values()}
        found = cards(html)
        self.assertEqual(len(found), len(names))
        for card in found:
            name = re.search(r"<h2>([^<]+)</h2>", card)[1]
            choose = names[name]["choose"]
            row = rows[choose["article_key"]]
            top = card[: card.index("<details")]
            body = (ROOT / row["body_source"]).read_text()
            landing = body[body.index(f' id="{choose["anchor"]}"') :]
            heading = re.sub(
                r"<[^>]+>", "", re.search(r"<h2[^>]*>(.*?)</h2>", landing, re.S)[1]
            )
            with self.subTest(category=name, heading=heading):
                self.assertEqual(len(re.findall(r"<li>", top)), 3)
                self.assertIn(
                    f'href="/{row["slug"]}/#{choose["anchor"]}">{choose["label"]}</a>',
                    top,
                )
                self.assertIn(choose["label"], heading)

    def test_small_suitcase_comparison_has_one_table_and_offers_link(self):
        row = next(
            r
            for r in published_posts(self.registry)
            if r["slug"] == "small-carry-on-suitcase-comparison"
        )
        self.assertIsNone(row["listing"]["offers_anchor"])
        card = self.pages["comparisons"]
        self.assertIn(
            'href="/small-carry-on-suitcase-comparison/#specs">比較表・販売条件へ</a>',
            card,
        )
        self.assertNotIn('href="/small-carry-on-suitcase-comparison/#offers"', card)

    def test_home_new_arrivals_do_not_repeat_category_card_labels(self):
        home = self.pages["home"]
        labels = [
            re.sub(r"<[^>]+>", "", text).strip()
            for text in re.findall(r"<a [^>]*>(.*?)</a>", home, flags=re.S)
            + re.findall(r"<h2[^>]*>(.*?)</h2>", home, flags=re.S)
        ]
        labels = [label for label in labels if label]
        repeated = sorted({label for label in labels if labels.count(label) > 1})
        self.assertEqual(repeated, [])
        rows = {r["slug"]: r for r in published_posts(self.registry)}
        recent = section(home, "km-updates-title")
        slugs = re.findall(r'<a class="ks-recent-image" href="/([^/]+)/"', recent)
        self.assertEqual(len(slugs), 4)
        titles = re.findall(r"<h3><a [^>]*>(.*?)</a></h3>", recent)
        self.assertEqual(titles, [rows[slug]["title"] for slug in slugs])

    def test_home_suitcase_decision_uses_words_from_the_comparison_body(self):
        decides = self.data["categories"]["travel"]["decides"]
        self.assertEqual(decides, "軽さ・開き方・車輪のどれを優先するか決める")
        self.assertIn(
            f"<p>{decides}</p>", section(self.pages["home"], "km-categories-title")
        )
        body = (
            ROOT
            / "changes/wordpress-direct-publish-v1/articles/small-carry-on-suitcase-comparison.html"
        ).read_text()
        text = re.sub(
            r"<[^>]+>", "", re.sub(r"<script.*?</script>", "", body, flags=re.S)
        )
        for word in ("軽さ", "開き", "車輪"):
            self.assertIn(word, text)

    def test_hub_wording_uses_words_from_the_linked_body(self):
        rows = {r["article_key"]: r for r in published_posts(self.registry)}
        suitcase = rows["small-carry-on-suitcase-comparison"]
        dishwasher = rows["standard-dishwasher-comparison"]
        robot = rows["compact-robot-vacuum-shortlist"]
        cleaning = self.data["categories"]["cleaning"]["decides"]
        hub = suitcase["title"] + suitcase["excerpt"]
        hub += suitcase["reader_role"]["decision_after_reading"]
        self.assertNotIn("移動", hub)
        self.assertNotIn("手入れ", dishwasher["excerpt"])
        self.assertNotIn("任せる", cleaning)
        self.assertNotIn("任せ", robot["excerpt"])
        cases = (
            (suitcase, hub, ("軽さ", "開き方", "車輪", "ストッパー")),
            (dishwasher, dishwasher["excerpt"], ("毎日の手間",)),
            (robot, cleaning, ("本体", "台", "置き場所", "自動ゴミ収集", "水拭き")),
            (robot, robot["excerpt"], ("置き場所", "自動ゴミ収集", "水拭き")),
        )
        for row, wording, words in cases:
            text = body_text(row)
            for word in words:
                with self.subTest(key=row["article_key"], word=word):
                    self.assertIn(word, wording)
                    self.assertIn(word, text)

    def test_hub_outputs_do_not_bring_back_replaced_wording(self):
        rows = {r["article_key"]: r for r in self.registry["articles"]}
        navigation = json.loads((ROOT / NAVIGATION_ASSET).read_text())
        nav_leads = [
            node["description"]
            for node in walk(navigation)
            if node.get("slug") == "categories" and "description" in node
        ]
        self.assertTrue(nav_leads)
        header = re.findall(
            r'<p class="ks-directory-lead">([^<]*)</p>', self.pages["categories"]
        )
        leads = {
            "rendered header": header,
            "entry-pages": [self.data["pages"]["categories"]["description"]],
            "ledger excerpt": [rows["categories"]["excerpt"]],
            "navigation": nav_leads,
        }
        for source, found in leads.items():
            with self.subTest(source=source):
                self.assertEqual(found, [CATEGORIES_LEAD])
        texts = {slug: self.pages[slug] for slug in HUB_PAGES}
        texts["categories decision"] = rows["categories"]["reader_role"][
            "decision_after_reading"
        ]
        for name, text in texts.items():
            for word in BANNED_HUB_WORDS:
                with self.subTest(page=name, word=word):
                    self.assertNotIn(word, text)
        home = self.pages["home"]
        label = re.search(r'href="/comparisons/#purchase-checks">([^<]+)</a>', home)[1]
        checks = section(self.pages["comparisons"], "purchase-checks")
        heading = re.sub(r"<[^>]+>", "", re.search(r"<h2[^>]*>(.*?)</h2>", checks)[1])
        self.assertEqual(label, heading)

    def test_home_decisions_use_nouns_from_their_representative_body(self):
        rows = {r["article_key"]: r for r in published_posts(self.registry)}
        grid = section(self.pages["home"], "km-categories-title")
        self.assertEqual(set(HOME_DECISION_WORDS), set(self.data["categories"]))
        for slug, category in self.data["categories"].items():
            decides = category["decides"]
            text = body_text(rows[category["representative"]])
            self.assertIn(f"<p>{decides}</p>", grid)
            for word in HOME_DECISION_WORDS[slug]:
                with self.subTest(category=slug, word=word):
                    self.assertIn(word, decides)
                    self.assertIn(word, text)

    def test_updates_lists_each_change_log_entry_with_its_own_date(self):
        """Regression: README 内容更新日の規則 (one card per change_log entry)."""
        posts = {r["slug"]: r for r in published_posts(self.registry)}
        dates = {}
        for card in cards(section(self.pages["updates"], "updated-content")):
            date = re.search(r"内容更新日：(\d{4}-\d{2}-\d{2})", card)[1]
            dates.setdefault(heading_slugs(card)[0], []).append(date)
        for slug, row in posts.items():
            log = sorted(e["date"] for e in row["listing"]["change_log"])
            with self.subTest(slug=slug):
                self.assertEqual(sorted(dates.get(slug, [])), log)
        self.assertTrue(any(len(v) > 1 for v in dates.values()))
        readme = (ROOT / "changes/wordpress-direct-publish-v1/README.md").read_text()
        self.assertIn("同じ記事が複数回載る", readme)
        self.assertNotIn("/updates/`で同じ「内容更新日」", readme)

    def test_correction_lines_do_not_repeat_the_correction_word(self):
        updated = section(self.pages["updates"], "updated-content")
        for summary in re.findall(r"<p>(訂正：[^<]*)</p>", updated):
            with self.subTest(summary=summary):
                self.assertEqual(summary.count("訂正"), 1)

    def test_purposes_are_grouped_without_article_counts(self):
        html = self.pages["purposes"]
        before = section(html, "purpose-before")
        in_use = section(html, "purpose-in-use")
        self.assertIn("<h2>購入前に</h2>", before)
        self.assertIn("<h2>使い始めてからの手間で選ぶ</h2>", in_use)
        self.assertIn(">手入れを続けやすいものを選びたい</a></h3>", in_use)
        self.assertEqual(heading_slugs(before), self.data["purpose_groups"]["before"])
        self.assertEqual(heading_slugs(in_use), ["easy-maintenance"])
        self.assertNotRegex(html, r"関連 ?[0-9]+記事")

    def test_reference_to_unpublished_article_is_rejected(self):
        changed = copy.deepcopy(self.registry)
        row = next(
            r
            for r in changed["articles"]
            if r["slug"] == "standard-dishwasher-comparison"
        )
        row["listing"]["state"] = "draft"
        with self.assertRaisesRegex(
            ValueError,
            "EDITORIAL_REFERENCE_UNPUBLISHED: standard-dishwasher-comparison",
        ):
            editorial.render_pages(changed, self.catalog, self.data, {})

    def test_publication_dates_match_rest_evidence(self):
        records = self.data["publication_date_evidence"]["records"]
        rows = {r["article_key"]: r for r in self.registry["articles"]}
        for key, date_gmt in REST_DATE_GMT.items():
            self.assertEqual(rows[key]["listing"]["published_at_gmt"], date_gmt)
        for row in published_posts(self.registry):
            with self.subTest(slug=row["slug"]):
                record = records[str(row["post_id"])]
                self.assertEqual(record["slug"], row["slug"])
                self.assertEqual(
                    row["listing"]["published_at_gmt"], record["date_gmt"] + "Z"
                )
                local = (
                    datetime.fromisoformat(record["date_gmt"])
                    .replace(tzinfo=timezone.utc)
                    .astimezone(JST)
                )
                self.assertEqual(
                    row["listing"]["published_on"], local.date().isoformat()
                )
                self.assertEqual(
                    self.meta[row["slug"]]["published_on"], local.date().isoformat()
                )

    def test_rechecking_sales_or_specifications_does_not_change_pages(self):
        """Regression intent of plan 2.3, expressed against the new listing fields."""
        changed = copy.deepcopy(self.registry)
        for row in published_posts(changed):
            row["listing"]["sales_checked_at"] = "2026-09-15T00:00:00Z"
            row["listing"]["specification_checked_on"] = "2026-09-15"
        pages, _, _ = editorial.render_pages(changed, self.catalog, self.data, {})
        self.assertEqual(pages, self.pages)

    def test_generator_keeps_no_post_id_literals(self):
        source = (
            ROOT / "python/raos/application/editorial/site_editorial_pages.py"
        ).read_text()
        ids = "19|28|29|30|41|82|83|84|85|86|262|263|264|265|266|549|550|551|552|553"
        self.assertNotRegex(source, r"[\[(,]\s*(?:" + ids + r")\s*[,\])]")
        self.assertNotIn("ps-offers", source)
        self.assertNotIn("home_short_titles", source)
        self.assertNotIn("home_article_images", source)
        for removed in ("articles", "home_short_titles", "home_article_images"):
            self.assertNotIn(removed, self.data)
        for category in self.data["categories"].values():
            self.assertNotIn("order", category)


if __name__ == "__main__":
    unittest.main()
