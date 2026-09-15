"""Template-level guards for the W2B comparison edits (KS-015/017 small, KS-124, KS-126, KS-133, KS-135, KS-139).

The bodies are compiled in memory from ``changes/reader-purchase-support-v1`` so
each check follows the editorial source rather than a previously generated copy.
Catalog and renderer checks for the same tasks live with their owners.
"""

from __future__ import annotations

import json
import re

import pytest

from raos.application.editorial.reader_html import Element, fragment
from scripts import build_reader_purchase_support_v1 as builder

SCROLL_CLAIM = re.compile(r"スクロール|左右に動かせ")
BERMAS_IMAGE_STATEMENT = (
    "掲載画像は60524の販売ページの画像です。"
    "同じ販売ページの画像でUSBポートがないことと背面のトラベルセントリーIDを2026年9月13日に確認しました。"
    "旧60504の販売ページの画像は使っていません。"
)
SKIPPED_TAGS = frozenset({"script", "style", "template", "code", "pre"})


@pytest.fixture(scope="module")
def outputs() -> dict[str, str]:
    return {
        path.stem: body
        for path, body in builder.build().items()
        if path.suffix == ".html"
    }


@pytest.fixture(scope="module")
def roots(outputs: dict[str, str]) -> dict[str, Element]:
    return {slug: fragment(body) for slug, body in outputs.items()}


def visible_text(node: Element) -> str:
    parts: list[str] = []

    def collect(element: Element) -> None:
        if element.tag in SKIPPED_TAGS:
            return
        for child in element.children:
            if isinstance(child, Element):
                collect(child)
            elif not child.startswith("<!--"):
                parts.append(child)

    collect(node)
    return re.sub(r"\s+", " ", "".join(parts))


def by_id(root: Element, element_id: str) -> list[Element]:
    return [n for n in root.walk() if n.attrs.get("id") == element_id]


def heading_section(root: Element, heading_id: str) -> Element:
    headings = by_id(root, heading_id)
    assert len(headings) == 1, heading_id
    section = headings[0].parent
    assert section is not None and section.tag == "section", heading_id
    return section


def hrefs(node: Element) -> list[str]:
    return [a.attrs.get("href") or "" for a in node.find(tag="a")]


def ancestors(node: Element) -> list[Element]:
    chain = []
    current = node.parent
    while current is not None:
        chain.append(current)
        current = current.parent
    return chain


def test_tpl_brand_comparison_routes_to_overall_comparison(roots) -> None:
    """KS-135: the ACE brand comparison (19) reaches the cross-brand comparison (553)."""
    section = heading_section(roots["carry-on-suitcase-comparison"], "ace-scope-title")
    links = hrefs(section)
    assert "/small-carry-on-suitcase-comparison/" in links
    assert "/lightweight-carry-on-suitcase-under-3kg/" in links


def test_tpl_bermas_image_statement_matches_registered_media(roots) -> None:
    """KS-133: a paragraph naming BERMAS 60524 must not say its image is withheld."""
    catalog = json.loads(builder.CATALOG_INPUT_PATH.read_text(encoding="utf-8"))
    product = next(
        p for p in catalog["products"] if p["product_id"] == "PRD-BERMAS-INTER-CITY-60524"
    )
    assert product["image_review"]["state"] == "VERIFIED_REGISTERED_MEDIA"
    section = heading_section(
        roots["carry-on-suitcase-under-100-seats"], "small-flight-limits-title"
    )
    blocks = [
        visible_text(p) for p in section.find(tag="p") + section.find(tag="li")
        if "60524" in visible_text(p)
    ]
    assert blocks, "the BERMAS 60524 paragraph moved out of the imported section"
    for text in blocks:
        assert not re.search(r"画像は掲載し(?:ていません|ない)|非掲載", text), text
    statement = " ".join(blocks)
    # Only the recorded identity checks (USB removal, rear Travel Sentry ID) are claimed.
    # Decision 9: the two checks are credited to the listing's images, not to the one shown.
    assert BERMAS_IMAGE_STATEMENT in statement
    assert "item.rakuten.co.jp" not in statement


def test_tpl_purchase_nav_lands_on_seller_section(roots) -> None:
    """KS-139: the renamed nav item lands inside the seller section, not the conclusion cards."""
    root = roots["anker-solix-c300-c800-c1000-differences"]
    navs = by_id(root, "ks-article-nav")
    assert len(navs) == 1
    links = {visible_text(a).strip(): a.attrs.get("href") or "" for a in navs[0].find(tag="a")}
    assert "購入前の確認へ" not in links
    href = links.get("購入費用と販売先へ")
    assert href and href.startswith("#"), links
    target_id = href[1:]
    body = builder.build()[
        next(p for p in builder.ARTICLE_OUTPUT_PATHS if p.stem == "anker-solix-c300-c800-c1000-differences")
    ]
    assert body.count(f'id="{target_id}"') == 1, target_id
    target = by_id(root, target_id)[0]
    # Decision 4 (amended): the nav and the table of contents share one landing point.
    assert target_id == "ps-offers" and target.tag == "section"
    # In this row comparison the section wraps the table whose column carries prices and sellers.
    heads = [visible_text(th).strip() for th in target.find(tag="th") if th.attrs.get("scope") == "col"]
    assert "参考価格・販売先" in heads, heads
    assert any(n.attrs.get("id") == "ps-price-notes" for n in target.walk())
    toc = [a.attrs.get("href") for a in root.find(tag="a") if visible_text(a).strip() == "購入費用と販売先"]
    assert href in toc, toc
    assert href != links.get("容量・重量の比較表へ")


def test_tpl_small_carry_on_matrix_groups_are_labelled(roots) -> None:
    """KS-015: each merged spec group in 553 repeats its column name."""
    root = roots["small-carry-on-suitcase-comparison"]
    expected = ["通常時の外寸・本体重量・容量", "使いやすさ・詳細", "拡張時の外寸・容量"]
    rows = [r for r in root.find(tag="tr") if r.attrs.get("data-product-id")]
    assert len(rows) == 12
    for row in rows:
        labels = []
        for group in row.find(cls="ps-matrix-spec-group"):
            first = next(c for c in group.children if isinstance(c, Element))
            assert first.tag == "span" and first.has("ps-row-fact-label"), row.attrs["id"]
            labels.append(first.text().strip())
        assert labels == expected, row.attrs["id"]


@pytest.mark.parametrize(
    "slug", ["small-carry-on-suitcase-comparison", "dishwasher-water-supply-methods"]
)
def test_tpl_tables_do_not_claim_horizontal_scroll(roots, slug: str) -> None:
    """KS-017: production measurement found no scrolling table behind these hints."""
    root = roots[slug]
    assert not SCROLL_CLAIM.search(visible_text(root))
    labels = [n.attrs.get("aria-label") or "" for n in root.walk()]
    assert not [label for label in labels if SCROLL_CLAIM.search(label)]


def test_tpl_water_supply_supplement_routes_to_same_model(roots) -> None:
    """KS-126: the SS-LH451 supplement row links its own large-comparison row and 552."""
    rows = by_id(roots["dishwasher-water-supply-methods"], "product-dish-ss-lh451-water-example")
    assert len(rows) == 1
    links = hrefs(rows[0])
    assert "/large-dishwasher-comparison/#large-siroca" in links
    assert "/dishwasher-branch-faucet-guide/" in links
    targets = by_id(roots["large-dishwasher-comparison"], "large-siroca")
    assert len(targets) == 1
    assert targets[0].attrs.get("data-product-id") == "PRD-LARGE-DISHWASHER-SS-LH451"


def test_tpl_solota_vs_mini_plus_alternative_links_compact_comparison(roots) -> None:
    """KS-124: when mini Plus cannot be bought, 86 routes to 549 and keeps 41."""
    section = heading_section(roots["solota-vs-rakua-mini-plus"], "mini-plus-alternative-title")
    links = hrefs(section)
    assert links.count("/compact-dishwasher-comparison/") == 1
    assert "/countertop-dishwasher-for-small-households/" in links


# KS-137 (decision 10): the conclusion cards keep the app / Wi-Fi axis, but the
# band is shown as one attribute of the app choice, never as the headline that
# picks a model on its own. Both robots support 2.4GHz, so "2.4GHzを使う" alone
# would point a 2.4GHz household at one model only.
ROBOT_ARTICLE = "roomba-mini-vs-switchbot-k11-pro"
BAND_ONLY_LABEL = re.compile(r"^[^（(]*[0-9./]+GHz[^（(]*を使う$")


def test_robot_condition_labels_are_not_wifi_band_only(roots: dict[str, Element]) -> None:
    catalog = json.loads(builder.CATALOG_INPUT_PATH.read_text(encoding="utf-8"))
    article = next(a for a in catalog["articles"] if a["article_id"] == ROBOT_ARTICLE)
    labels = [c["label"] for c in article["conditions"]]
    assert labels == [
        "Roomba Homeアプリで使う（Wi-Fiは2.4GHz・5GHz）",
        "SwitchBotアプリで使う（Wi-Fiは2.4GHzのみ）",
    ]
    assert not [label for label in labels if BAND_ONLY_LABEL.match(label)]
    choose = by_id(roots[ROBOT_ARTICLE], "ps-choose")
    assert len(choose) == 1
    headings = [visible_text(n).strip() for n in choose[0].walk() if n.tag == "h3"]
    assert headings == labels



def test_price_notes_anchor_is_unique_in_every_row_comparison(outputs: dict[str, str]) -> None:
    """Decision 4: a generated price-notes block carries its id at most once per body.

    compact-robot-vacuum-shortlist keeps an authored copy of the notes without the id.
    """
    stamped = 0
    for slug, body in outputs.items():
        if 'class="ps-row-price-notes"' in body:
            assert body.count('id="ps-price-notes"') <= 1, slug
            stamped += body.count('id="ps-price-notes"')
    assert stamped >= 8


WIFI_CONDITION_NOTE = "Wi-Fiの周波数帯は選ぶ条件の1つで、これだけで機種は決めません。"
IROBOT_APP_SUPPORT = "https://answers.irobot.com/ja/knowledge/10503"


def test_robot_choice_says_the_band_is_one_condition(roots: dict[str, Element]) -> None:
    """Decision 10: one sentence near the conclusion cards."""
    choose = by_id(roots[ROBOT_ARTICLE], "ps-choose")
    assert len(choose) == 1
    assert visible_text(choose[0]).count(WIFI_CONDITION_NOTE) == 1


def test_robot_app_support_page_is_a_link_and_faq_date_matches_recheck(roots: dict[str, Element]) -> None:
    """Decision 10: 10503 is a link; F155260 and F115060 / F115260 were rechecked on 2026-09-15."""
    root = roots[ROBOT_ARTICLE]
    assert IROBOT_APP_SUPPORT in hrefs(root)
    assert IROBOT_APP_SUPPORT not in visible_text(root)
    faq = [visible_text(n) for n in root.walk() if n.tag == "dd" and "F155260" in visible_text(n)]
    assert len(faq) == 1, faq
    assert "2026年9月15日に再確認した公式仕様では、F155260とF115060 / F115260が2.4GHz / 5GHz対応です。" in faq[0]
    assert "2026年8月29日" not in faq[0]


def test_tpl_brand_comparison_keeps_expansion_sizes_with_the_three_models(roots) -> None:
    """Decision 12: the 553 route sentence closes the paragraph about the 3 models."""
    section = heading_section(roots["carry-on-suitcase-comparison"], "ace-scope-title")
    first = visible_text(section.find(tag="p")[0]).strip()
    assert first.index("拡張時はクレスタ") < first.index("ブランドを限らずに")
    assert first.endswith("小型・機内持ち込みスーツケース比較へ進めます。")
