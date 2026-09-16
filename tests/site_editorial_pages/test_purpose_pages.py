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
            "水栓・蛇口までの目安（タテ置き）：50.2cm以上あれば、ドアが水栓・蛇口に当たりにくい",
            "50.2cmの矢印は、開いた扉の先端の線から「壁」と書かれた線まで引かれています",
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
        self.assertNotIn("必要な奥行", solota)
        self.assertNotIn("扉の先より外側", solota)
        closing = text(section_after(page, "例で見る：起点と、まだ分からない範囲"))
        self.assertIn(
            "公式の図から寸法の起点を読み取れない型番は、この例に入れていません。",
            closing,
        )
        self.assertNotIn("矢印や起点の手がかりがない", closing)
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
        mop = text(routes)
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

    def test_purpose_multi_column_tables_scroll_in_their_frame_on_phones(self):
        css = THEME_CSS.read_text()
        expected = {
            "small-space": ["space-zones-table"],
            "save-housework": [
                "housework-record-table",
                "housework-time-table",
                "housework-route-table",
            ],
            "easy-maintenance": [
                "maintenance-dishwasher-table",
                "maintenance-vacuum-table",
                "maintenance-suitcase-table",
            ],
        }
        rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        for slug, ids in expected.items():
            page = self.pages[slug]
            for ident in ids:
                self.assertEqual(page.count(f'id="{ident}"'), 1, ident)
                self.assertRegex(
                    page,
                    r'<div class="ks-editorial-table[^"]*"[^>]*><table[^>]*\sid="'
                    + ident
                    + '"',
                )
                joined = " ".join(
                    body.replace(" ", "")
                    for selector, body in rules
                    if "#" + ident in selector
                )
                self.assertRegex(joined, r"min-width:\d+rem!important", ident)
                self.assertIn("position:sticky!important", joined, ident)

    # Scroll-frame client width measured by static rendering at a 320px viewport
    # (the .np-table frame loses 2px to its own border).
    PHONE_FRAME_PX = {
        "space-zones-table": 240,
        "housework-record-table": 240,
        "housework-time-table": 240,
        "housework-route-table": 240,
        "maintenance-dishwasher-table": 240,
        "maintenance-vacuum-table": 240,
        "maintenance-suitcase-table": 240,
        "np-method-table": 238,
        "np-model-table": 238,
    }
    TABLE_PAGES = {
        "space-zones-table": "small-space",
        "housework-record-table": "save-housework",
        "housework-time-table": "save-housework",
        "housework-route-table": "save-housework",
        "maintenance-dishwasher-table": "easy-maintenance",
        "maintenance-vacuum-table": "easy-maintenance",
        "maintenance-suitcase-table": "easy-maintenance",
        "np-method-table": "without-installation",
        "np-model-table": "without-installation",
    }
    # Horizontal padding plus the collapsed border of one cell at 320px, from the
    # rendered CSS (5+5+1 in .ks-editorial-table, 8.8x2 in .np-table).
    CELL_CHROME_PX = {
        "space-zones-table": 11,
        "housework-record-table": 11,
        "housework-time-table": 11,
        "housework-route-table": 11,
        "maintenance-dishwasher-table": 11,
        "maintenance-vacuum-table": 11,
        "maintenance-suitcase-table": 11,
        "np-method-table": 18,
        "np-model-table": 18,
    }
    # Share of the frame the sticky first column may take. A three-column table
    # carries more of its meaning in the row header, and #np-model-table has to
    # hold an unbreakable model code, so it is allowed half.
    FIRST_COLUMN_SHARE = {"np-model-table": 0.5}
    # Rendered width of the widest nowrap model code (TDWS25SRD) in the
    # #np-model-table row header at a phone viewport: 91.1px at the cell's 15px
    # font. .np-model-code is nowrap, so the column has to be at least that wide
    # or the code is painted over the next column.
    MODEL_CODE_PX = 92
    PHONE_MARKER = "/* Phone table widths"

    def phone_block(self, css: str) -> str:
        self.assertIn(self.PHONE_MARKER, css)
        start = css.index("{", css.index(self.PHONE_MARKER))
        depth = 0
        for index in range(start, len(css)):
            if css[index] == "{":
                depth += 1
            elif css[index] == "}":
                depth -= 1
                if depth == 0:
                    return css[start + 1 : index]
        raise AssertionError("unbalanced phone table width block")

    def phone_px(self, block: str, ident: str, prop: str, first_child: bool) -> float:
        found = []
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", block):
            if "#" + ident not in selector:
                continue
            if (":first-child" in selector) != first_child:
                continue
            match = re.search(prop + r":\s*([\d.]+)rem!important", body)
            if match:
                found.append(float(match.group(1)) * 16)
        self.assertEqual(len(found), 1, (ident, prop, first_child, found))
        return found[0]

    def table_columns(self, page: str, ident: str) -> int:
        start = page.rindex("<table", 0, page.index('id="' + ident + '"'))
        table = page[start : page.index("</table>", start)]
        head = table[table.index("<tr") : table.index("</tr>")]
        return len(re.findall(r"<t[hd][ >]", head))

    def test_sticky_first_column_leaves_room_for_a_whole_data_column(self):
        """table-layout is fixed, so the data columns share (min-width - first).

        A sticky first column as wide as a data column leaves no scroll position
        that shows a whole data cell on a phone.
        """
        css = THEME_CSS.read_text()
        block = self.phone_block(css)
        for ident, frame in self.PHONE_FRAME_PX.items():
            columns = self.table_columns(self.pages[self.TABLE_PAGES[ident]], ident)
            self.assertGreaterEqual(columns, 3, ident)
            first = (
                self.phone_px(block, ident, "width", True) + self.CELL_CHROME_PX[ident]
            )
            minimum = self.phone_px(block, ident, "min-width", False)
            data = (minimum - first) / (columns - 1)
            share = self.FIRST_COLUMN_SHARE.get(ident, 0.45)
            self.assertLessEqual(first, share * frame, ident)
            self.assertGreaterEqual(data, 120, ident)
            self.assertLessEqual(first + data, frame, ident)

    def test_model_table_first_column_holds_the_model_codes(self):
        """The model table's row header carries nowrap model codes.

        Without an id the phone width rules miss the table: the three columns
        just split the frame, nothing scrolls, and below about 380px the codes
        are painted on top of the next column's text.
        """
        source = SOURCE.read_text()
        self.assertEqual(source.count('id="np-model-table"'), 1)
        page = self.pages["without-installation"]
        self.assertEqual(page.count('id="np-model-table"'), 1)
        self.assertRegex(
            page,
            r'<div class="[^"]*np-table[^"]*"[^>]*>\s*<table[^>]*id="np-model-table"',
        )
        css = THEME_CSS.read_text()
        joined = " ".join(
            body.replace(" ", "")
            for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
            if "#np-model-table" in selector
        )
        self.assertIn("position:sticky!important", joined)
        block = self.phone_block(css)
        self.assertGreaterEqual(
            self.phone_px(block, "np-model-table", "width", True), self.MODEL_CODE_PX
        )

    def test_water_supply_dates_agree_across_the_two_pages(self):
        """Two pages in one candidate must not date the same source page
        differently. /save-housework/ records the SS-MA251 manual p.12 water
        amount as checked on 2026-09-16, so the /without-installation/ note,
        whose water-route date is 2026-09-13 with a list of later checks, has to
        name it there."""
        fact = self.data["purpose_evidence"]["save-housework"]["examples"][0][
            "facts"
        ][0]
        self.assertIn("p.12", fact["locator"])
        self.assertIn("ss-ma251", fact["source_url"])
        year, month, day = (int(part) for part in fact["checked_at"].split("-"))
        stamp = f"{year}年{month}月{day}日"
        note = text(section_after(self.pages["without-installation"], "出典・編集方針"))
        head = note.index("給水方法の確認日")
        clause = note[head : note.index("。", head)]
        self.assertNotIn(stamp, clause[: clause.index("（")])
        exceptions = clause[clause.index("（") + 1 : clause.index("）")]
        named = [
            part for part in re.split(r"[、，]", exceptions) if "SS-MA251" in part
        ]
        self.assertTrue(named, exceptions)
        for part in named:
            self.assertIn(stamp, part)

    def test_route_table_rows_stay_one_check_each(self):
        """Every 確かめること cell is a check, and every 次に読む cell a link.

        One row carried a whole product record (412 characters), which made that
        single row 1394px tall on a phone and did not read as 「確かめること」;
        one 次に読む cell was the only one that was neither a link nor a dash.
        """
        page = self.pages["save-housework"]
        routes = section_after(page, "困っていることから比較を選ぶ")
        body = rows(routes)[1:]
        self.assertGreaterEqual(len(body), 6)
        for row in body:
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)
            self.assertEqual(len(cells), 3, row[:60])
            check = text(cells[1]).strip()
            self.assertLessEqual(len(check), 120, check[:40])
            follow = cells[2]
            self.assertTrue(
                "<a " in follow or text(follow).strip() == "—", text(follow)
            )
        # The record itself stays on the page, below the table.
        self.assertIn("N285060", text(routes))
        self.assertNotIn("N285060", "".join(body))

    def test_sticky_first_column_covers_the_scrolled_edge(self):
        """With border-collapse the cell background stops at the middle of the
        collapsed border, so a 1px strip of the scrolled columns shows at the
        sticky column's left edge unless the cell covers it."""
        css = THEME_CSS.read_text()
        rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        for ident in self.PHONE_FRAME_PX:
            if ident.startswith("np-"):
                continue  # .np-table cells carry no left border, so nothing leaks
            joined = " ".join(
                body.replace(" ", "")
                for selector, body in rules
                if "#" + ident in selector and "th:first-child::before" in selector
            )
            self.assertIn("position:absolute", joined, ident)
            self.assertIn("left:-1px", joined, ident)
            self.assertRegex(joined, r"background:#[0-9a-f]{6}", ident)
            self.assertRegex(joined, r"border-left:1pxsolid#[0-9a-f]{6}", ident)


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
