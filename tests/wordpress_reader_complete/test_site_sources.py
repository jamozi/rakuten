"""Local source graph checks. HTTP/browser verification is separate evidence."""

import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit
from scripts.raos_reader_live_patch import Document, inline_reader_styles

ROOT = Path(__file__).resolve().parents[2]
DIRECT = ROOT / "changes/wordpress-direct-publish-v1"


class SiteSourceTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads((DIRECT / "articles.v1.json").read_text())[
            "articles"
        ]
        self.site = json.loads((DIRECT / "reader-sync/site-map.v2.json").read_text())
        self.pages = {
            p["slug"]: Document(
                (DIRECT / "articles" / (p["slug"] + ".html")).read_text()
            )
            for p in self.site["pages"]
        }

    def published_posts(self):
        return [
            r
            for r in self.registry
            if r["post_type"] == "post"
            and (r.get("listing") or {}).get("state") == "published"
        ]

    def test_all_existing_targets_have_one_source(self):
        # site-map.v2.json predates the 2026-09-13 posts (KS-001); the ledger
        # listing is the published inventory.
        published = {r["post_id"] for r in self.published_posts()}
        self.assertLessEqual({a["post_id"] for a in self.site["articles"]}, published)
        expected = {p["post_id"] for p in self.site["pages"]} | {15, 3, 10, 120} | published
        self.assertEqual({r["post_id"] for r in self.registry if r["mode"] == "existing"}, expected)
        self.assertEqual(len([r for r in self.registry if r["mode"] == "existing"]), len(expected))
        for row in self.published_posts():
            self.assertEqual(row["mode"], "existing")
            self.assertIs(type(row["post_id"]), int)
        for row in self.registry:
            self.assertIn(row["mode"], {"existing", "new"})
            if row["mode"] == "new":
                self.assertIsNone(row["post_id"])
            self.assertNotEqual(
                bool(row.get("body_source")), bool(row.get("patch_source"))
            )
            if row["article_key"] != "home":
                self.assertTrue(
                    (ROOT / (row.get("body_source") or row["patch_source"])).is_file()
                )

    def test_directories_do_not_depend_on_empty_shortcode(self):
        for slug, doc in self.pages.items():
            with self.subTest(slug=slug):
                self.assertNotIn("[kurashinoshirube_reader_hub", doc.text)
                self.assertNotIn("現在、条件に合う公開記事はありません", doc.text)
                self.assertTrue(any((n.tag == "a" for n in doc.nodes)))

    def test_each_article_is_reachable_from_category_or_public_index(self):
        for row in self.published_posts():
            docs = [
                self.pages[slug]
                for slug in (row["listing"]["category"], "comparisons", "guides")
                if slug in self.pages
            ]
            hrefs = {
                urlsplit(n.attrs.get("href") or "").path
                for doc in docs
                for n in doc.nodes
                if n.tag == "a"
            }
            self.assertIn("/" + row["slug"] + "/", hrefs)

    def test_all_source_routes_and_same_page_fragments_resolve(self):
        routes = {"/", "/comparison-policy/", "/about-ad-policy/"}
        routes |= {"/" + r["slug"] + "/" for r in self.registry}
        for slug, doc in self.pages.items():
            for node in doc.nodes:
                if node.tag != "a":
                    continue
                href = node.attrs.get("href") or ""
                parsed = urlsplit(href)
                if parsed.scheme or parsed.netloc:
                    self.assertEqual(parsed.scheme, "https")
                    self.assertTrue(parsed.hostname)
                    self.assertFalse(parsed.username or parsed.password)
                    continue
                if parsed.path:
                    self.assertIn(parsed.path, routes)
                target = self.pages.get(parsed.path.strip("/")) if parsed.path else doc
                if parsed.fragment and target:
                    self.assertIn(parsed.fragment, target.ids)

    def test_article_recipes_preserve_richer_existing_sections(self):
        rows = [r for r in self.registry if r.get("patch_source")]
        purchase = json.loads(
            (
                ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
            ).read_text()
        )
        adopted = {a["slug"] for a in purchase["articles"]}
        self.assertEqual(
            {r["slug"] for r in rows},
            {a["slug"] for a in self.site["articles"]} - adopted,
        )
        for row in rows:
            recipe = json.loads((ROOT / row["patch_source"]).read_text())
            self.assertEqual(recipe["article_key"], row["article_key"])
            self.assertEqual(recipe["post_id"], row["post_id"])
            self.assertTrue(recipe["keep_existing_fragments"])
            self.assertGreaterEqual(len(recipe["required_ids"]), 2)
            for field in ("nav_html", "next_html"):
                for node in Document(recipe[field]).nodes:
                    if node.tag == "a":
                        href = node.attrs.get("href", "")
                        self.assertTrue(
                            href.startswith(("/", "#")) and (not href.startswith("//"))
                        )

    def test_anker_recipe_carries_only_the_bounded_gen2_corrections(self):
        recipe = json.loads(
            (
                DIRECT / "articles/anker-solix-c300-c800-c1000-differences.patch.json"
            ).read_text()
        )
        edits = recipe["replacements"]
        self.assertEqual(len(edits), 2)
        for edit in edits:
            self.assertEqual(set(edit), {"old", "new", "max_count", "exclusive"})
            self.assertEqual(edit["max_count"], 1)
            self.assertIs(edit["exclusive"], True)
            self.assertFalse(any((c in edit["old"] + edit["new"] for c in "<>")))
            self.assertNotIn("50W", edit["new"])
            self.assertIn("USB-C端子数", edit["new"])
        self.assertIn("定格出力が50W高いためです", edits[0]["old"])
        self.assertEqual(edits[1]["old"], "C1000系で重量と出力を優先")
        self.assertTrue(recipe["keep_existing_fragments"])
        self.assertEqual(
            recipe["required_ids"],
            ["blk-anker-008-title", "blk-anker-017-title", "blk-anker-003-title"],
        )

    def test_sources_do_not_contain_merchant_tracking_values(self):
        runtime = json.loads(
            (ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/purchase-support.v1.json").read_text()
        )
        entries = {a["slug"]: a for a in runtime["articles"]}
        for path in (DIRECT / "articles").glob("*"):
            if path.stem == "home":
                continue
            text = path.read_text()
            for forbidden in ("rafcid=", "sk-proj-"):
                self.assertNotIn(forbidden, text)
            allowed = {
                b["cta_id"]: b["href"] for b in entries.get(path.stem, {}).get("bindings", [])
                if b.get("affiliate") == "true"
            }
            for node in Document(text).nodes:
                href = node.attrs.get("href", "")
                if "hb.afl.rakuten.co.jp" in href:
                    self.assertEqual(allowed.get(node.attrs.get("data-raos-cta-id")), href)
                    self.assertIn("sponsored", node.attrs.get("rel", "").split())

    def test_reader_styles_can_be_applied_without_losing_images(self):
        for slug, doc in self.pages.items():
            with self.subTest(slug=slug):
                styled = inline_reader_styles(doc.text)
                self.assertEqual(inline_reader_styles(styled), styled)
                before_images = [n.attrs for n in doc.nodes if n.tag == "img"]
                after_images = [
                    n.attrs for n in Document(styled).nodes if n.tag == "img"
                ]
                self.assertEqual(before_images, after_images)
                if 'class="ps-article"' in doc.text:
                    # The adopted snapshot loads the reviewed stylesheet from the theme.
                    self.assertEqual(styled, doc.text)
                elif any(
                    "ks-editorial-page" in (n.attrs.get("class") or "").split()
                    for n in doc.nodes
                ):
                    # Current entry pages use theme styles. The bounded legacy
                    # inliner may leave them unchanged or style nested old routes.
                    theme = (
                        ROOT
                        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/theme.css"
                    )
                    self.assertIn(".ks-editorial-page", theme.read_text())
                    self.assertEqual(
                        [n.attrs for n in doc.nodes if n.tag == "a"],
                        [n.attrs for n in Document(styled).nodes if n.tag == "a"],
                    )
                else:
                    self.assertIn('data-ks-inline-style="v1"', styled)


if __name__ == "__main__":
    unittest.main()
