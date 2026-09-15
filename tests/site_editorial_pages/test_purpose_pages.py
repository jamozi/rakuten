"""KS-111〜114 purpose pages: figures, record values, water routes, maintenance rows.

The `Fails before W4a` class covers content and validation added by W4a; each test
failed before purpose_evidence and the page blocks existed. `Regression` keeps
wording guards that already passed on the published pages.
"""

from __future__ import annotations

import copy
import importlib.util
from html import unescape
import json
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "site_builder_purpose", ROOT / "scripts/build_site_editorial_pages.py"
)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

from raos.application.editorial import site_editorial_pages as editorial  # noqa: E402

SOURCE = (
    ROOT / "changes/site-improvements-20260913/entry-pages/without-installation.html"
)
THEME_CSS = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/theme.css"
)
ALLOWED_HOSTS = {
    "panasonic.jp",
    "jpn.faq.panasonic.com",
    "www.siroca.co.jp",
    "www.thanko.jp",
    "www.data.thanko.jp",
    "data.thanko.jp",
    "cdn.shopify.com",
    "www.switchbot.jp",
    "support.switch-bot.com",
    "store.irobot-jp.com",
    "prod-help-content.care.irobotapi.com",
    "www.bagworld.co.jp",
}


def text(html: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", html))


def section_after(html: str, heading: str) -> str:
    start = html.index("<h2>" + heading + "</h2>")
    return html[start : html.index("</section>", start)]


def rows(html: str) -> list[str]:
    return re.findall(r"<tr[^>]*>.*?</tr>", html, re.S)


def row_with(html: str, needle: str) -> str:
    found = [r for r in rows(html) if needle in r]
    assert len(found) == 1, (needle, len(found))
    return found[0]


class PurposeBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.registry, cls.catalog = [
            json.loads((ROOT / p).read_text()) for p in builder.INPUT_PATHS[:3]
        ]
        cls.bodies = builder.load_bodies(cls.registry)
        cls.pages, _, cls.updates, _ = builder.render(
            cls.data, cls.registry, cls.catalog, cls.bodies
        )

    def render_with(self, data):
        return editorial.render_pages(self.registry, self.catalog, data, {})


class FailsBeforeW4a(PurposeBase):
    def test_small_space_separates_three_measuring_zones(self):
        page = self.pages["small-space"]
        zones = section_after(page, "測る場所を3つに分ける")
        for label in ("①本体が入る空間", "②動かす範囲", "③作業と周囲の空間"):
            self.assertEqual(len([r for r in rows(zones) if label in r]), 1, label)
        self.assertIn(
            "起点が分からない数字は、本体の奥行に足しも引きもしません", text(zones)
        )

    def test_small_space_figures_state_origin_record_values_and_unknowns(self):
        page = self.pages["small-space"]
        self.assertNotIn("<svg", page)
        self.assertNotIn(" style=", page)
        self.assertIn('class="ks-purpose-diagrams"', page)
        figures = re.findall(
            r'<figure class="ks-purpose-diagram">.*?</figure>', page, re.S
        )
        self.assertEqual(len(figures), 2)
        for figure in figures:
            body = text(figure)
            for word in ("起点", "記録値", "未確認", "縮尺なし", "出典"):
                self.assertIn(word, body)
            self.assertRegex(figure, r"<pre>[^<]+</pre>")
            pre = unescape(re.search(r"<pre>([^<]+)</pre>", figure).group(1))
            for line in pre.splitlines():
                self.assertLessEqual(len(line), 22, line)
            hosts = {
                urlsplit(h).hostname
                for h in re.findall(r'href="(https://[^"]+)"', figure)
            }
            self.assertTrue(hosts)
            self.assertLessEqual(hosts, ALLOWED_HOSTS)
        solota, k11 = (text(f) for f in figures)
        for phrase in (
            "NP-TMLK1-K",
            "壁",
            "図の線から読み取った起点",
            "必要な奥行（タテ置き）：50.2cm以上あれば、ドアが水栓・蛇口に当たりにくい",
            "同じ図の代替テキストは「図：高さが49cm以上あればOK、背面から50.2cm以上あれば、ドアが水栓・蛇口に当たりにくい。」",
            "48.5cmの起点も確認できていないため、この足し算では判断しません（編集部の計算）",
            "1.7cm以上",
            "排水ホース外径分を含む",
            "本体と壁の間に0.5cm以上",
            "できるだけあけて",
            "上方5cm",
        ):
            self.assertIn(phrase, solota)
        self.assertNotIn("公式ページはこの内訳を書いていません", solota)
        self.assertNotIn("検算", solota)
        for phrase in (
            "K11+ Pro",
            "両側に0.5m",
            "前方および上方に1.5m",
            "壁際",
            "底面240×180mm",
            "幅と奥行の対応は未確認",
            "高さ約25cm",
            "サポート記事",
        ):
            self.assertIn(phrase, k11)
        self.assertNotIn("SS-MA251", "".join(figures))
        for href in (
            "/dishwasher-installation-measurement/#product-dish-np-tmlk1",
            "/roomba-mini-vs-switchbot-k11-pro/#product-robot-k11-pro",
        ):
            self.assertIn(f'href="{href}"', page)

    def test_save_housework_record_values_fill_in_table_and_routes(self):
        page = self.pages["save-housework"]
        first = section_after(page, "任せる作業／残る作業")
        self.assertIn("記録値の例（型番・出典）", first)
        self.assertIn("約6L", row_with(first, "SS-MA251"))
        self.assertIn("90日ごと", row_with(first, "K11+ Pro"))
        self.assertIn("タンクの補給とすすぎ（構成による）", text(first))
        self.assertIn('href="https://www.siroca.co.jp/im/ss-ma251.pdf"', first)
        self.assertIn("https://cdn.shopify.com/", first)
        fill = section_after(page, "自分の作業時間を書き出す")
        self.assertIn("今の頻度と1回の時間（記入）", fill)
        self.assertIn("＿", fill)
        for word in ("記録値", "仮定"):
            self.assertIn(word, text(fill))
        routes = section_after(page, "困っていることから比較を選ぶ")
        self.assertGreaterEqual(len(rows(routes)) - 1, 5)
        for href in (
            "/without-installation/#first-read",
            "/dishwasher-branch-faucet-guide/",
            "/dishwasher-cleaning-guide/",
            "/easy-maintenance/",
            "/standard-dishwasher-comparison/",
            "/large-dishwasher-comparison/",
            "/roomba-mini-vs-switchbot-k11-pro/",
            "/compact-robot-vacuum-shortlist/",
        ):
            self.assertIn(f'href="{href}"', routes)
        mop = text(row_with(routes, "N285060"))
        for phrase in (
            "奥行き34.0×幅33.0×高さ48.5cm",
            "給水・廃水タンクのすすぎ",
            "3～6か月ごと",
            "6～12か月ごと",
        ):
            self.assertIn(phrase, mop)

    def test_without_installation_names_three_routes_and_pump_scope(self):
        source = SOURCE.read_text()
        page = self.pages["without-installation"]
        first = page[page.index('id="first-read"') : page.index('id="np-models"')]
        methods = re.findall(r'<div class="np-method">.*?</div>', first, re.S)
        self.assertEqual(len(methods), 3)
        labels = re.findall(r'<p class="np-method-label">([^<]+)</p>', first)
        self.assertEqual(
            labels,
            [
                "①タンク式（手注ぎ）",
                "②タンク式＋別売の給水補助ポンプ",
                "③外部容器から本体が吸い上げる",
            ],
        )
        self.assertIn('href="https://www.thanko.jp/smartphone/page262.html"', source)
        self.assertIn('href="https://www.thanko.jp/view/item/000000004261"', source)
        body = text(source)
        for quote in (
            "ラクア（STTDWADW、STTDWADB）：使用可能です。",
            "ラクアmini Plus ブラック（TK-MDW22B）：現行販売品のみ使用可能です。",
            "ラクアmini Plus ホワイト（TK-STTDPSWH）：現行販売品のみ使用可能です。",
            "ラクアmini（TK-MDW22W）：使用できません。",
            "mini plus対応可否の見分け方（給水口を確認してください）",
            "過去、ラクアmini （Plus含む）とポンプのセット販売品をご購入のお客様",
            "問題なくご利用可能ですが、動作安定性向上のための現在販売分は仕様が変更となっております。",
        ):
            self.assertIn(quote, body)
        sentences = [s for s in re.split(r"(?<=。)", body) if "自動給水" in s]
        self.assertTrue(sentences)
        for sentence in sentences:
            self.assertIn("シロカ", sentence)
            self.assertNotIn("ポンプでタンク", sentence)
        self.assertIn("シロカは③を「自動給水式」と呼んでいます", body)
        self.assertNotIn("タンク式・ポンプ給水", body)
        self.assertNotIn("専用バケツからポンプ給水", body)
        for sentence in (s for s in re.split(r"[。\n]", body) if "約10L" in s):
            self.assertIn("用意", sentence)
            self.assertNotIn("使用水量", sentence)
        for value in editorial.PURPOSES["without-installation"]:
            self.assertNotIn("ポンプ給水", value)

    def test_easy_maintenance_rows_show_model_frequencies_and_parts(self):
        page = self.pages["easy-maintenance"]
        body = text(page)
        self.assertNotIn("対象型番の記事の公式資料・確認日・販売条件を参照。", body)
        self.assertIn("費用がかからないとは扱いません", body)
        for phrase in ("0円", "交換不要", "無料"):
            self.assertNotIn(phrase, body)
        dish = section_after(page, "食洗機")
        for model in ("SS-MA251", "TDWS25SBL / TDWS25SRD", "NP-TSP1-W"):
            self.assertIn(model, row_with(dish, model))
        self.assertIn("週1回", row_with(dish, "NP-TSP1-W"))
        self.assertIn("毎回", row_with(dish, "SS-MA251"))
        robot = section_after(page, "掃除機")
        k11 = text(row_with(robot, "K11+ Pro"))
        for phrase in (
            "90日ごと",
            "約20分",
            "必要に応じて洗浄",
            "2~3カ月ごと",
            "12カ月ごと",
        ):
            self.assertIn(phrase, k11)
        mini = text(row_with(robot, "F155260"))
        plus = text(row_with(robot, "N285060"))
        for number in ("4849916", "4859242", "4859243", "4859244", "4860285"):
            self.assertIn(number, mini)
        for number in ("4860486", "4860487", "4860682", "4849916", "4860283"):
            self.assertIn(number, plus)
        for number in ("4859242", "4859243", "4859244", "4860285"):
            self.assertNotIn(number, plus)
        for number in ("4860486", "4860487", "4860682", "4860283"):
            self.assertNotIn(number, mini)
        self.assertIn("3～6か月ごと", mini)
        self.assertIn("6～12か月ごと", plus)
        suitcase = section_after(page, "スーツケース")
        self.assertIn("1-623", row_with(suitcase, "1-250"))
        for table_html in (dish, robot, suitcase):
            for row in rows(table_html)[1:]:
                self.assertIn("未確認", text(row))
                hosts = {
                    urlsplit(h).hostname
                    for h in re.findall(r'href="(https://[^"]+)"', row)
                }
                self.assertTrue(hosts, row[:80])
                self.assertLessEqual(hosts, ALLOWED_HOSTS)

    def test_purpose_facts_reject_model_source_zero_and_unknown_values(self):
        evidence = self.data["purpose_evidence"]
        self.assertEqual(
            sorted(evidence), ["easy-maintenance", "save-housework", "small-space"]
        )

        def mutated(change):
            data = copy.deepcopy(self.data)
            change(data["purpose_evidence"])
            return data

        cases = {
            "PURPOSE_FACT_MODEL_MISMATCH": [
                lambda e: e["small-space"]["figures"][0].update(exact_model="NP-TMLK1"),
                lambda e: e["easy-maintenance"]["groups"][0]["rows"][2].update(
                    exact_model="NP-TSP1"
                ),
                lambda e: e["save-housework"]["examples"][0].update(
                    product_id="PRD-UNKNOWN"
                ),
            ],
            "PURPOSE_FACT_SOURCE": [
                lambda e: e["small-space"]["figures"][1]["facts"][0].update(
                    source_url="http://www.switchbot.jp/x"
                ),
                lambda e: e["small-space"]["figures"][1]["facts"][0].update(
                    source_url="https://example.com/x"
                ),
                lambda e: e["small-space"]["figures"][1]["facts"][0].update(
                    checked_at="2026/09/16"
                ),
            ],
            "PURPOSE_FACT_ZERO": [
                lambda e: e["easy-maintenance"]["groups"][0]["rows"][0]["price"][
                    0
                ].update(
                    state="KNOWN",
                    text="部品代0円",
                    source_url="https://www.siroca.co.jp/x",
                    locator="x",
                    checked_at="2026-09-16",
                ),
                lambda e: e["easy-maintenance"]["groups"][1]["rows"][0]["parts"][
                    0
                ].update(text="交換不要"),
            ],
            "PURPOSE_FACT_UNKNOWN_VALUE": [
                lambda e: e["small-space"]["figures"][1]["unknowns"][0].update(
                    text="1.5m"
                ),
            ],
        }
        for code, changes in cases.items():
            for index, change in enumerate(changes):
                with self.subTest(code=code, index=index):
                    with self.assertRaisesRegex(ValueError, code):
                        self.render_with(mutated(change))

    def test_theme_sizes_purpose_figures_above_the_generic_figure_rule(self):
        css = THEME_CSS.read_text()
        self.assertIn(
            "body .ks-editorial-page .ks-purpose-diagrams figure{max-width:none;", css
        )
        self.assertRegex(
            css,
            r"body \.ks-editorial-page \.ks-purpose-diagrams pre\{[^}]*white-space:pre-wrap",
        )
        self.assertRegex(
            css,
            r"body \.ks-editorial-page \.ks-purpose-diagrams\{display:grid;[^}]*minmax\(min\(100%,18rem\),1fr\)",
        )


class W4aReviewFixes(PurposeBase):
    def css_rule(self, css: str, selector: str) -> str:
        found = re.findall(
            r"(?:^|[}\n])\s*" + re.escape(selector) + r"\s*\{([^{}]*)\}", css
        )
        self.assertTrue(found, selector)
        return found[0]

    def test_without_installation_methods_are_three_columns_then_one(self):
        css = THEME_CSS.read_text()
        self.assertIn(
            "grid-template-columns:repeat(3,minmax(0,1fr))",
            self.css_rule(css, ".ks-no-plumbing .np-methods").replace(" ", ""),
        )
        third = self.css_rule(css, ".ks-no-plumbing .np-method:nth-child(3)")
        second = self.css_rule(css, ".ks-no-plumbing .np-method:nth-child(2)")
        self.assertIn("background", third)
        self.assertNotEqual(third, second)
        start = css.index("@media (max-width:600px) {\n  .ks-no-plumbing")
        narrow = css[start : css.index("\n}\n", start)]
        self.assertNotIn("repeat(3", narrow)
        self.assertIn(
            "grid-template-columns:1fr",
            self.css_rule(narrow, ".ks-no-plumbing .np-methods").replace(" ", ""),
        )

    def test_wide_new_tables_scroll_in_their_frame_on_phones(self):
        css = THEME_CSS.read_text()
        source = SOURCE.read_text()
        tables = re.findall(r"<table[^>]*>", source)
        self.assertEqual(tables[0], '<table id="np-method-table">')
        self.assertEqual(source.count('id="np-method-table"'), 1)
        page = self.pages["without-installation"]
        self.assertRegex(
            page,
            r'<div class="[^"]*np-table[^"]*"[^>]*>\s*<table[^>]*id="np-method-table"',
        )
        for table in ("#compact-space-table", "#np-method-table"):
            rules = [
                body
                for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
                if table in selector
            ]
            joined = " ".join(rules).replace(" ", "")
            self.assertIn("min-width:44rem!important", joined, table)
            self.assertIn("position:sticky!important", joined, table)


class Regression(PurposeBase):
    def test_no_measured_time_savings_or_rankings(self):
        for slug in (
            "small-space",
            "save-housework",
            "without-installation",
            "easy-maintenance",
        ):
            body = text(self.pages[slug])
            with self.subTest(slug=slug):
                self.assertNotRegex(body, r"[0-9]+\s*分(短縮|減|節約)")
                for phrase in ("時短になります", "1位", "おすすめ順", "設置できます"):
                    self.assertNotIn(phrase, body)
        self.assertIn(
            "運転時間と人の作業時間は異なります", text(self.pages["save-housework"])
        )
        source = text(SOURCE.read_text())
        self.assertIn("分岐水栓の取り付けが不要という意味", source)
        self.assertIn("電源やアースの工事が必要になる場合", source)

    def test_generated_deep_links_land_on_one_id(self):
        purpose = {s: self.pages[s] for s in editorial.PURPOSES}
        self.assertEqual(
            editorial.validate_listing_anchors(self.registry, self.bodies, purpose), []
        )


if __name__ == "__main__":
    unittest.main()
