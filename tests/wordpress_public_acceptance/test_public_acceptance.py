"""Synthetic anonymous HTML only; no live access or affiliate identifiers."""

import copy
from pathlib import Path
import re
import unittest
from scripts.raos_public_acceptance import assess

ORIGIN = "https://kurashinoshirube.com"
GOOD = """<!doctype html><html><head><title>比較ガイド</title>
<meta name="robots" content="index, follow"><meta name="description" content="条件別の比較">
<link rel="canonical" href="https://kurashinoshirube.com/demo/"></head>
<body><main><h1>比較ガイド</h1><p>広告・アフィリエイトリンクを含みます。</p>
<section id="comparison"><a href="#comparison">比較表</a></section>
<a href="https://hb.afl.rakuten.co.jp/example-private-token/" rel="sponsored nofollow">販売条件を見る</a>
</main></body></html>"""


def observation(html=GOOD, path="/demo/", **extra):
    return dict(
        path=path,
        status=200,
        final_url=ORIGIN + path,
        full_html=True,
        html=html,
        headers={},
        **extra,
    )


class AcceptanceTests(unittest.TestCase):
    def result(self, row=None, **kwargs):
        return assess([observation() if row is None else row], ["/demo/"], **kwargs)

    def codes(self, row=None, **kwargs):
        return {f["code"] for f in self.result(row, **kwargs)["findings"]}

    def test_valid_public_controls_pass(self):
        self.assertEqual(self.result()["status"], "PASS")

    def test_http_200_with_noindex_fails(self):
        self.assertIn(
            "NOINDEX",
            self.codes(observation(GOOD.replace("index, follow", "noindex, nofollow"))),
        )

    def test_googlebot_none_fails(self):
        self.assertIn(
            "NOINDEX",
            self.codes(
                observation(
                    GOOD.replace(
                        "</head>", '<meta name="googlebot" content="none"></head>'
                    )
                )
            ),
        )

    def test_header_noindex_fails(self):
        row = observation()
        row["headers"] = {"X-Robots-Tag": "googlebot: noindex"}
        self.assertIn("NOINDEX", self.codes(row))

    def test_missing_canonical_fails(self):
        self.assertIn(
            "CANONICAL_MISSING_OR_DUPLICATE",
            self.codes(
                observation(
                    GOOD.replace(
                        '<link rel="canonical" href="https://kurashinoshirube.com/demo/">',
                        "",
                    )
                )
            ),
        )

    def test_wrong_canonical_fails(self):
        self.assertIn(
            "CANONICAL_NOT_SELF",
            self.codes(
                observation(
                    GOOD.replace(
                        'href="https://kurashinoshirube.com/demo/"',
                        'href="https://kurashinoshirube.com/other/"',
                    )
                )
            ),
        )

    def test_duplicate_heading_and_ids_fail(self):
        html = GOOD.replace(
            "</main>", '<h1>重複</h1><p id="comparison">重複</p></main>'
        )
        self.assertTrue({"H1_COUNT", "DUPLICATE_ID"} <= self.codes(observation(html)))

    def test_broken_internal_anchor_fails(self):
        self.assertIn(
            "ANCHOR_MISSING",
            self.codes(
                observation(GOOD.replace('href="#comparison"', 'href="#missing"'))
            ),
        )

    def test_missing_cross_page_is_unknown_not_broken(self):
        row = observation(GOOD.replace('href="#comparison"', 'href="/guide/#missing"'))
        self.assertIn("ANCHOR_TARGET_UNCHECKED", self.codes(row))
        self.assertNotIn("ANCHOR_MISSING", self.codes(row))
        self.assertEqual(self.result(row)["status"], "INCOMPLETE")

    def test_missing_expected_page_never_passes(self):
        self.assertEqual(assess([], ["/demo/"])["status"], "INCOMPLETE")

    def test_incomplete_html_never_passes(self):
        row = observation()
        row["full_html"] = False
        self.assertEqual(self.result(row)["status"], "INCOMPLETE")

    def test_network_error_is_not_404(self):
        row = observation()
        row["status"] = None
        row["html"] = ""
        self.assertEqual(self.result(row)["status"], "INCOMPLETE")
        self.assertNotIn("HTTP_NOT_200", self.codes(row))

    def test_404_is_failure(self):
        row = observation()
        row["status"] = 404
        self.assertIn("HTTP_NOT_200", self.codes(row))

    def test_sponsored_or_nofollow_accepted(self):
        self.assertNotIn(
            "AFFILIATE_REL_MISSING",
            self.codes(observation(GOOD.replace("sponsored nofollow", "nofollow"))),
        )

    def test_paid_link_without_qualifier_fails(self):
        self.assertIn(
            "AFFILIATE_REL_MISSING",
            self.codes(
                observation(GOOD.replace('rel="sponsored nofollow"', 'rel="noopener"'))
            ),
        )

    def test_disclosure_after_link_fails(self):
        html = GOOD.replace("<p>広告・アフィリエイトリンクを含みます。</p>", "")
        html = html.replace("</main>", "<p>広告を含みます。</p></main>")
        self.assertIn("DISCLOSURE_NOT_BEFORE_LINK", self.codes(observation(html)))

    def test_hidden_disclosure_does_not_count(self):
        html = GOOD.replace("<p>広告・", "<p hidden>広告・")
        self.assertIn("DISCLOSURE_NOT_BEFORE_LINK", self.codes(observation(html)))

    def test_calculator_requires_script(self):
        row = observation(
            GOOD.replace("</main>", '<div data-raos-cost-calculator="v1"></div></main>')
        )
        self.assertIn("COST_SCRIPT_MISSING", self.codes(row))

    def test_script_is_not_functional_proof(self):
        html = GOOD.replace(
            "</main>",
            '<div data-raos-cost-calculator="v1"></div><script src="/wp-content/themes/kurashinoshirube-child/assets/local-running-cost.js"></script></main>',
        )
        result = self.result(observation(html))
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIn(
            "COST_INTERACTION_UNVERIFIED", {f["code"] for f in result["findings"]}
        )

    def test_sitemap_absence_fails_only_if_supplied(self):
        self.assertNotIn("SITEMAP_MISSING", self.codes())
        self.assertIn("SITEMAP_MISSING", self.codes(sitemap_paths=[]))

    def test_result_does_not_leak_outbound_identifier(self):
        self.assertNotIn("example-private-token", str(self.result()))

    def test_input_not_mutated(self):
        rows = [observation()]
        original = copy.deepcopy(rows)
        assess(rows, ["/demo/"])
        self.assertEqual(rows, original)

    def test_duplicate_observation_is_rejected(self):
        with self.assertRaises(ValueError):
            assess([observation(), observation()], ["/demo/"])

    def test_unsafe_expected_path_rejected(self):
        with self.assertRaises(ValueError):
            assess([], ["https://other.invalid/"])

    def test_no_affiliate_link_is_not_a_failure(self):
        html = GOOD[: GOOD.index('<a href="https://hb.afl')] + "</main></body></html>"
        self.assertEqual(self.result(observation(html))["status"], "PASS")

    def test_empty_listing_fails(self):
        html = GOOD.replace(
            "</main>", "<p>現在、条件に合う公開記事はありません</p></main>"
        )
        self.assertIn("EMPTY_LISTING", self.codes(observation(html)))


ROOT = Path(__file__).resolve().parents[2]
SEMANTICS_RECORD = ROOT / "changes/site-improvements-20260913/technical-local-semantics.md"
THEME_FUNCTIONS = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/functions.php"
)
EXCLUDED_SCHEMA_TYPES = ("Product", "Offer", "Review", "AggregateRating", "FAQPage", "ItemList")


class RecordedStructuredDataPolicyTests(unittest.TestCase):
    """Repository records, not live pages: why the theme leaves some schema types out."""

    def policy_section(self):
        text = SEMANTICS_RECORD.read_text(encoding="utf-8")
        self.assertEqual(text.count("\n## 方針\n"), 1)
        return text.split("\n## 方針\n", 1)[1].split("\n## ", 1)[0]

    def test_excluded_schema_types_have_recorded_rationale(self):
        policy = self.policy_section()
        self.assertIn("| 型 | 採用しない理由 | 根拠 |", policy)
        rows = {}
        for line in policy.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if line.startswith("| ") and len(cells) == 3 and cells[0] in EXCLUDED_SCHEMA_TYPES:
                self.assertNotIn(cells[0], rows)
                rows[cells[0]] = cells
        self.assertEqual(sorted(rows), sorted(EXCLUDED_SCHEMA_TYPES))
        for name, (_, reason, basis) in rows.items():
            self.assertTrue(reason, name)
            self.assertTrue(basis, name)
        self.assertIn("OWNER_DECISION_PENDING", rows["ItemList"][1])
        # Prices are shown by the clock-checked script; only cached HTML and JSON-LD omit them.
        self.assertIn("キャッシュ", rows["Offer"][1])
        emitted = set(re.findall(r"'@type'\s*=>\s*'([A-Za-z]+)'", THEME_FUNCTIONS.read_text(encoding="utf-8")))
        self.assertIn("BreadcrumbList", emitted)
        self.assertEqual(emitted & set(EXCLUDED_SCHEMA_TYPES), set())

    def test_policy_page_breadcrumb_choice_is_recorded(self):
        policy = self.policy_section()
        self.assertIn("BreadcrumbList", policy)
        for slug in ("about-ad-policy", "comparison-policy", "privacy-policy"):
            self.assertIn(slug, policy)


if __name__ == "__main__":
    unittest.main()
