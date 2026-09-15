"""KS W3 batch 5: approved-layout comparisons 549 / 550 / 551 (and 553 for KS-026).

KS-120 guide links and KS-129 (549 side) cost cross-reference, KS-122 large-row
dimensions backed by catalog facts, KS-026 one correction contact per curated
comparison, KS-015/017 matrix group labels and no horizontal-scroll claims.

Bodies are compiled in memory from the tracked sources, so these checks do not
depend on regenerated outputs. No `\\b` is used next to Japanese text.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re

import pytest

from scripts import build_reader_purchase_support_v1 as builder
from raos.application.editorial.purchase_support import (
    compile_articles,
    render_curated_commerce,
    resolve_product_media,
)
from raos.application.editorial.reader_html import Element, fragment

THEME_CSS = (
    builder.ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/theme.css"
)
BASELINES = (
    builder.ROOT
    / "changes/site-improvements-20260913/approved-layout-baselines.v1.json"
)
CORRECTION_HREF = "/about-ad-policy/#production-about-correction"
SCROLL_CLAIM = re.compile(r"スクロール|左右に動かせ")
NEGATIVE = re.compile(r"ません|ない|ず[、。]|ではな")
FACT_KEYS = {
    "label",
    "text",
    "source_url",
    "locator",
    "checked_at",
    "state",
    "exact_model",
}
BODY_LABEL = "本体寸法（幅×奥行×高さ）"
DOOR_LABEL = "開扉時の寸法"
LARGE_ROWS = {
    "large-siroca": ("PRD-LARGE-DISHWASHER-SS-LH451", "シロカ2機種"),
    "large-aqua": ("PRD-LARGE-DISHWASHER-ADW-L40B", "AQUA ADW-L40B"),
    "large-ta5": ("PRD-LARGE-DISHWASHER-NP-TA5", "パナソニック3機種"),
    "large-tz500": ("PRD-LARGE-DISHWASHER-NP-TZ500", "パナソニック3機種"),
    "large-th5": ("PRD-LARGE-DISHWASHER-NP-TH5", "パナソニック3機種"),
    "large-la451": ("PRD-LARGE-DISHWASHER-SS-LA451", "シロカ2機種"),
}


@pytest.fixture(scope="module")
def compiled():
    catalog = json.loads(builder.CATALOG_INPUT_PATH.read_text())
    templates = {p.stem: p.read_text() for p in builder.TEMPLATE_INPUT_PATHS}
    media = resolve_product_media(
        catalog,
        json.loads(builder.MEDIA_INPUT_PATH.read_text()),
        builder.OFFICIAL_MEDIA_INPUT_PATH.read_bytes(),
    )
    outputs, _ = compile_articles(
        catalog,
        templates,
        json.loads(builder.GUIDES_INPUT_PATH.read_text()),
        media,
        now=datetime(2026, 9, 13, 7, tzinfo=timezone.utc),
    )
    return catalog, templates, outputs, media


def nodes(root: Element, predicate) -> list[Element]:
    return [n for n in root.walk() if isinstance(n, Element) and predicate(n)]


def by_id(root: Element, ident: str) -> Element:
    found = nodes(root, lambda n: n.attrs.get("id") == ident)
    assert len(found) == 1, ident
    return found[0]


def hrefs(root: Element) -> list[str]:
    return [n.attrs.get("href") or "" for n in nodes(root, lambda n: n.tag == "a")]


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def elements(node: Element) -> list[Element]:
    return [c for c in node.children if isinstance(c, Element)]


def sentence_with(paragraph: Element, link: Element) -> str:
    text = squash(paragraph.text())
    anchor = squash(link.text())
    start = text.index(anchor)
    head = text.rfind("。", 0, start) + 1
    tail = text.find("。", start)
    return text[head : (tail + 1 if tail >= 0 else len(text))]


def link_paragraph(section: Element, href: str) -> tuple[Element, Element]:
    for paragraph in nodes(section, lambda n: n.tag == "p"):
        for link in nodes(paragraph, lambda n: n.tag == "a"):
            if (link.attrs.get("href") or "") == href:
                return paragraph, link
    raise AssertionError(href)


# KS-120 ---------------------------------------------------------------------


def test_compact_comparison_links_the_dishwasher_guides(compiled) -> None:
    _, _, outputs, _ = compiled
    body = outputs["compact-dishwasher-comparison"]
    root = fragment(body)
    space = by_id(root, "compact-space")
    care = by_id(root, "compact-care")
    assert "/dishwasher-installation-measurement/" in hrefs(space)
    assert "/dishwasher-detergent-guide/" in hrefs(care)
    assert "/dishwasher-cleaning-guide/" in hrefs(care)
    # The running-cost link is shared with KS-129: exactly one, in #compact-cost.
    running = [h for h in hrefs(root) if h.startswith("/dishwasher-running-cost/")]
    assert running == ["/dishwasher-running-cost/#guide-cost-example"]
    assert running[0] in hrefs(by_id(root, "compact-cost"))
    # The reviewed-out scope sentence must not come back.
    assert "ガイド本文で型番別に扱うのはSOLOTAとmini colorです" not in body
    for section, href in (
        (space, "/dishwasher-installation-measurement/"),
        (care, "/dishwasher-detergent-guide/"),
        (care, "/dishwasher-cleaning-guide/"),
        (by_id(root, "compact-cost"), "/dishwasher-running-cost/#guide-cost-example"),
    ):
        paragraph, link = link_paragraph(section, href)
        assert not NEGATIVE.search(sentence_with(paragraph, link)), href


def test_compact_guide_scope_sentence_matches_the_guides(compiled) -> None:
    """The model-coverage note sits with the two guide links in #compact-care."""
    _, _, outputs, _ = compiled
    root = fragment(outputs["compact-dishwasher-comparison"])
    space = squash(by_id(root, "compact-space").text())
    care = squash(by_id(root, "compact-care").text())
    assert "型番別に扱っています" not in space
    assert "以前掲載した機種の資料" not in space
    assert (
        "どちらのガイドも、本文ではこの記事の4商品のうちSOLOTAとminicolorを型番別に扱っています"
        in care
    )
    assert (
        "miniとminiPlusの説明書の該当ページは、各ガイド末尾の「以前掲載した機種の資料」にあります"
        in care
    )
    assert "取扱説明書の確認記録" not in care
    for slug in (
        "dishwasher-detergent-guide",
        "dishwasher-cleaning-guide",
    ):
        html = outputs[slug]
        archive = html.find("以前掲載した機種の資料")
        assert archive > 0, slug
        for ident in ("product-dish-np-tmlk1", "product-dish-rakua-mini-color"):
            assert 0 <= html.find('id="' + ident) < archive, (slug, ident)
        for prefix in ("guide-evidence-tk-mdw22w", "guide-evidence-tk-mdw22b"):
            assert html.find(prefix, archive) > archive, (slug, prefix)
    # running-cost has no such section, so the sentence must not name it.
    assert "以前掲載した機種の資料" not in outputs["dishwasher-running-cost"]
    assert "ランニングコスト" not in space


# KS-129 (549 side) -----------------------------------------------------------


def cost_per_run(
    wh: float, litres: float, yen_kwh: float, yen_m3: float, detergent: float
) -> float:
    return round(wh / 1000 * yen_kwh + litres / 1000 * yen_m3 + detergent, 2)


def test_compact_cost_example_cross_references_the_running_cost_exercise(
    compiled,
) -> None:
    _, _, outputs, _ = compiled
    cost = by_id(fragment(outputs["compact-dishwasher-comparison"]), "compact-cost")
    text = squash(cost.text())
    assert "/dishwasher-running-cost/#guide-cost-example" in hrefs(cost)
    # Both examples, each with its own stated unit prices.
    assert cost_per_run(230, 2.5, 30, 300, 5) == 12.65
    assert cost_per_run(230, 2.5, 31, 300, 0.8 * 2) == 9.48
    for token in (
        "約9.48円",
        "電気31円/kWh",
        "洗剤0.8円/g・2g",
        "12.65円",
        "電気30円/kWh",
        "洗剤5円/回",
    ):
        assert token in text, token
    assert "機種を特定しない式の練習" in text
    assert "どの機種にも使える" not in text
    assert "単価の仮定が違うため、2つの金額は比べません" in text
    # The home-price trial is limited to what the running-cost guide computes.
    assert "自宅の単価での試算" not in text
    assert "SOLOTAとminicolorも型番別の公表条件で試算できます" in text
    assert "minicolorは電気代を算出できず、水道代と洗剤代の小計だけです" in text
    # The linked target states the same amounts and unit prices.
    target = squash(
        by_id(fragment(outputs["dishwasher-running-cost"]), "guide-cost-example").text()
    )
    for token in ("電気30円/kWh", "洗剤5円/回", "12.65円/回", "架空の条件"):
        assert token in target, token
    # The home-price trial sentence matches the running-cost guide's own scope
    # statement, which follows #guide-cost-example on that page.
    guide = squash(fragment(outputs["dishwasher-running-cost"]).text())
    assert (
        "ラクアminicolorとSS-MA251は、1回の消費電力量が公表資料で確認できないため電気代を算出できず、水道代と洗剤代の小計だけを示します"
        in guide
    )


# KS-015 / KS-017 --------------------------------------------------------------


def spec_rows(root: Element) -> list[Element]:
    return nodes(root, lambda n: n.tag == "tr" and bool(n.attrs.get("data-product-id")))


def test_curated_matrix_spec_groups_are_labelled(compiled) -> None:
    _, _, outputs, _ = compiled
    compact = fragment(outputs["compact-dishwasher-comparison"])
    rows = [
        r for r in spec_rows(compact) if nodes(r, lambda n: n.has("ps-matrix-specs"))
    ]
    assert len(rows) == 4
    for row in rows:
        groups = nodes(row, lambda n: n.has("ps-matrix-spec-group"))
        assert [elements(g)[0].text() for g in groups] == [
            "容量／幅×奥行×高さ",
            "給水・機能",
        ]
        assert all(elements(g)[0].has("ps-row-fact-label") for g in groups)
    large = fragment(outputs["large-dishwasher-comparison"])
    rows = [r for r in spec_rows(large) if r.attrs.get("id") in LARGE_ROWS]
    assert len(rows) == 6
    for row in rows:
        first, second = nodes(row, lambda n: n.has("ps-matrix-spec-group"))
        assert (
            elements(first)[0].tag == "strong" and elements(first)[0].text() == "給水"
        )
        assert not nodes(first, lambda n: n.has("ps-row-fact-label"))
        assert elements(second)[0].has("ps-row-fact-label")
        assert elements(second)[0].text() == "選ぶ前に"


@pytest.mark.parametrize(
    "slug",
    [
        "compact-dishwasher-comparison",
        "large-dishwasher-comparison",
        "standard-dishwasher-comparison",
    ],
)
def test_approved_layout_bodies_do_not_claim_horizontal_scroll(compiled, slug) -> None:
    _, templates, outputs, _ = compiled
    assert not SCROLL_CLAIM.search(templates[slug])
    assert not SCROLL_CLAIM.search(outputs[slug])


def test_theme_css_has_no_generated_scroll_instruction() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")
    assert not re.search(r"content\s*:\s*\"[^\"]*(?:スクロール|左右に動かせ)", css)
    assert ".ks-large-guide .lg-table:before" not in css


# KS-122 -----------------------------------------------------------------------


def test_large_main_rows_carry_body_and_open_door_depth(compiled) -> None:
    catalog, _, outputs, _ = compiled
    products = {p["product_id"]: p for p in catalog["products"]}
    root = fragment(outputs["large-dishwasher-comparison"])
    space_rows = {}
    space = nodes(
        root,
        lambda n: (
            n.tag == "section" and n.attrs.get("aria-labelledby") == "large-space"
        ),
    )
    assert len(space) == 1
    for tr in nodes(space[0], lambda n: n.tag == "tr"):
        cells = elements(tr)
        if cells and cells[0].tag == "th" and cells[0].attrs.get("scope") == "row":
            space_rows[squash(cells[0].text())] = squash(cells[1].text())
    figure = {
        squash(elements(row)[0].text()): squash(elements(row)[1].text())
        for row in nodes(space[0], lambda n: n.has("lg-depth-row"))
    }
    for row_id, (pid, brand) in LARGE_ROWS.items():
        product = products[pid]
        facts = {}
        for label in (BODY_LABEL, DOOR_LABEL):
            matching = [f for f in product["facts"] if f["label"] == label]
            assert len(matching) == 1, (pid, label)
            fact = matching[0]
            assert set(fact) == FACT_KEYS, (pid, label)
            assert fact["exact_model"] == product["exact_model"]
            assert fact["source_url"].startswith("https://")
            assert fact["locator"] and re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", fact["checked_at"]
            )
            assert fact["state"] in {"KNOWN", "UNKNOWN"}
            facts[label] = fact
        row = by_id(root, row_id)
        assert row.attrs.get("data-product-id") == pid
        first = squash(nodes(row, lambda n: n.has("ps-matrix-spec-group"))[0].text())
        body, door = facts[BODY_LABEL], facts[DOOR_LABEL]
        for fact, heading in ((body, "本体（幅×奥行×高さ）"), (door, "開扉時の奥行")):
            if fact["state"] == "KNOWN":
                assert squash(fact["text"]) in first, (row_id, fact["text"])
            else:
                assert fact["text"] == "未確認"
                assert heading + "未確認" in first, row_id
        if body["state"] == "KNOWN":
            assert squash(body["text"]) == space_rows[squash(brand)] + "cm", row_id
        if door["state"] == "KNOWN":
            assert squash(door["text"]).endswith(figure[squash(brand)]), row_id


# KS-026 -----------------------------------------------------------------------


def test_curated_comparisons_show_one_correction_contact(compiled) -> None:
    catalog, _, outputs, _ = compiled
    curated = [a for a in catalog["articles"] if a["kind"] == "curated_comparison"]
    assert {a["slug"] for a in curated} >= {
        "compact-dishwasher-comparison",
        "standard-dishwasher-comparison",
        "large-dishwasher-comparison",
        "small-carry-on-suitcase-comparison",
    }
    for article in curated:
        root = fragment(outputs[article["slug"]])
        links = nodes(
            root, lambda n: n.tag == "a" and n.attrs.get("href") == CORRECTION_HREF
        )
        assert len(links) == 1, article["slug"]
        editor = links[0].parent
        assert editor is not None and editor.tag == "p" and editor.has("ps-editor")
        container = editor.parent
        assert container is not None and container.has("ps-article"), article["slug"]
        assert elements(container)[-1] is editor, article["slug"]
        history = nodes(root, lambda n: n.has("ps-history"))
        assert len(history) == (1 if article.get("history") else 0), article["slug"]
    for article in catalog["articles"]:
        if article["kind"] in {"comparison", "guide"}:
            assert outputs[article["slug"]].count(CORRECTION_HREF) >= 1, article["slug"]


def test_curated_history_block_requires_one_article_root(compiled) -> None:
    catalog, templates, _, media = compiled
    article = next(
        a for a in catalog["articles"] if a["slug"] == "compact-dishwasher-comparison"
    )
    template = templates["compact-dishwasher-comparison"].replace(
        "ps-article compact-draft", "compact-draft", 1
    )
    with pytest.raises(ValueError, match="PURCHASE_CURATED_ROOT_REQUIRED"):
        render_curated_commerce(
            template,
            article,
            catalog,
            "ps-test",
            media,
            datetime(2026, 9, 13, 7, tzinfo=timezone.utc),
        )


# Approved-layout record ----------------------------------------------------------


def test_changed_approved_layouts_are_recorded_as_pending_owner_review() -> None:
    record = json.loads(BASELINES.read_text(encoding="utf-8"))["articles"]
    for slug in (
        "compact-dishwasher-comparison",
        "standard-dishwasher-comparison",
        "large-dishwasher-comparison",
    ):
        pending = record[slug]["pending_revision"]
        assert pending["review"] == "PENDING_OWNER_BEFORE_AFTER"
        assert pending["publication_authorized"] is False
        assert pending["tasks"] and all(t.startswith("KS-") for t in pending["tasks"])
        assert pending["source_paths"]
