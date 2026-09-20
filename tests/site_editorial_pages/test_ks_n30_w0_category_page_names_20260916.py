"""Wave 0 of next30: a category page and its label must name the same thing.

Widening the labels (食洗機→台所, ロボット掃除機→掃除) moved the breadcrumb, the
directory cards and the jump navigation, but left the two category pages' own
titles and excerpts naming a single product kind. A reader who clicked 台所 then
landed on a page headed 食洗機, and the structured breadcrumb disagreed with the
visible one. These checks keep the page name, the excerpt, the hub body and
every record of that name on the widened word — and keep them from promising
article groups that no wave has published yet.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
ENTRY_PAGES = ROOT / "changes/site-improvements-20260913/entry-pages.v1.json"
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
CATALOG = ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
SITE_MAP = ROOT / "changes/wordpress-direct-publish-v1/reader-sync/site-map.v2.json"
HUB_TOOL = (
    ROOT / "changes/wordpress-direct-publish-v1/reader-sync/tools/hub_pages_20260912.py"
)
NOT_FOUND = ROOT / (
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/templates/404.html"
)
KITCHEN_SOURCE = ROOT / "changes/reader-purchase-support-v1/articles/kitchen.html"
CLEANING_SOURCE = ROOT / "changes/site-improvements-20260913/entry-pages/cleaning.html"
TRAVEL_SOURCE = ROOT / "changes/site-improvements-20260913/entry-pages/travel.html"
PREPAREDNESS_SOURCE = (
    ROOT / "changes/site-improvements-20260913/entry-pages/preparedness.html"
)

TITLES = {"kitchen": "台所の道具の選び方・比較", "cleaning": "掃除の道具の選び方・比較"}
EXCERPTS = {
    "kitchen": (
        "台所で使う道具を、置き場所と毎日の手間から選ぶ入口。"
        "いま掲載しているのは卓上食洗機と水切りラックで、容量別の比較と、"
        "設置・給水・洗剤・費用のガイド、水切りラックの置き方・比較・採寸へ案内します。"
    ),
    "cleaning": (
        "掃除の道具を、置き場所と任せたい作業、残る手入れから選ぶ入口。"
        "いま掲載しているのはロボット掃除機で、吸引・水拭き、"
        "自動ゴミ収集・モップ洗浄の違いを整理します。"
    ),
}
LABELS = {"kitchen": "台所", "cleaning": "掃除"}
STOCK_TODAY = {"kitchen": "卓上食洗機", "cleaning": "ロボット掃除機"}
RETIRED_TITLES = ("食洗機の選び方・比較", "ロボット掃除機の選び方・比較")
# Groups the programme will publish later. Until their wave lands, neither the
# page name nor the hub body may claim them. 水切りラック left this tuple when wave 1
# published its three articles (posts 750/751/752); each later wave removes
# exactly the group it published and no other.
ABSENT_GROUPS = (
    "ノンフライヤー",
    "熱風調理",
    "衣類乾燥除湿機",
    "軽量コードレス",
)
# A card that now carries a wide label has to say which product kind is
# actually on the shelf, or the widened word reads as a promise.
ON_THE_SHELF = {"kitchen": "卓上食洗機", "cleaning": "ロボット掃除機"}
PARENT_CRUMB = "商品カテゴリ"


def entry_pages() -> dict:
    return json.loads(ENTRY_PAGES.read_text(encoding="utf-8"))


def ledger_rows() -> dict[str, dict]:
    document = json.loads(LEDGER.read_text(encoding="utf-8"))
    return {row["article_key"]: row for row in document["articles"]}


def test_the_two_category_pages_are_named_by_the_widened_label() -> None:
    pages = entry_pages()["pages"]
    rows = ledger_rows()
    for key, title in TITLES.items():
        assert pages[key]["title"] == title, key
        assert rows[key]["title"] == title, key
        assert pages[key]["description"] == EXCERPTS[key], key
        assert rows[key]["excerpt"] == EXCERPTS[key], key
        assert LABELS[key] in title, key
        assert STOCK_TODAY[key] not in title, key


def test_the_page_name_and_its_breadcrumb_no_longer_disagree() -> None:
    sources = {"kitchen": KITCHEN_SOURCE, "cleaning": CLEANING_SOURCE}
    for key, path in sources.items():
        body = path.read_text(encoding="utf-8")
        crumb = re.search(r'<span aria-current="page">([^<]+)</span>', body)
        assert crumb, key
        assert crumb[1] == LABELS[key], key
        # The word the reader clicked has to appear in the page it landed on.
        assert crumb[1] in TITLES[key], key


def test_the_four_category_pages_spell_their_parent_crumb_the_same_way() -> None:
    for path in (
        KITCHEN_SOURCE,
        CLEANING_SOURCE,
        TRAVEL_SOURCE,
        PREPAREDNESS_SOURCE,
    ):
        body = path.read_text(encoding="utf-8")
        parents = re.findall(r'<a href="/categories/">([^<]+)</a>', body)
        assert parents, path.name
        assert set(parents) == {PARENT_CRUMB}, (path.name, parents)


def test_every_record_of_the_page_name_agrees() -> None:
    site_map = json.loads(SITE_MAP.read_text(encoding="utf-8"))
    by_slug = {page["slug"]: page for page in site_map["pages"]}
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    hubs = {a["slug"]: a for a in catalog["articles"] if a.get("kind") == "hub"}
    categories = entry_pages()["categories"]
    for key, title in TITLES.items():
        assert by_slug[key]["title"] == title, key
        assert by_slug[key]["lead"] == categories[key]["lead"], key
        if key in hubs:
            assert hubs[key]["title"] == title, key

    not_found = NOT_FOUND.read_text(encoding="utf-8")
    tool = HUB_TOOL.read_text(encoding="utf-8")
    for title in TITLES.values():
        assert title in not_found, title
        assert title in tool, title
    for retired in RETIRED_TITLES:
        assert retired not in not_found, retired
        assert retired not in tool, retired
        assert retired not in SITE_MAP.read_text(encoding="utf-8"), retired
        assert retired not in LEDGER.read_text(encoding="utf-8"), retired
        assert retired not in ENTRY_PAGES.read_text(encoding="utf-8"), retired
        assert retired not in CATALOG.read_text(encoding="utf-8"), retired


def test_the_hub_bodies_name_the_category_and_what_it_holds_today() -> None:
    bodies = {
        "kitchen": KITCHEN_SOURCE.read_text(encoding="utf-8"),
        "cleaning": CLEANING_SOURCE.read_text(encoding="utf-8"),
    }
    for key, body in bodies.items():
        opening = body[
            : body.index("</section>") if "</section>" in body else len(body)
        ]
        assert LABELS[key] in opening, key
        assert STOCK_TODAY[key] in opening, key


def test_the_hub_bodies_promise_no_article_group_that_does_not_exist_yet() -> None:
    texts = [
        KITCHEN_SOURCE.read_text(encoding="utf-8"),
        CLEANING_SOURCE.read_text(encoding="utf-8"),
        *TITLES.values(),
        *EXCERPTS.values(),
    ]
    for text in texts:
        for group in ABSENT_GROUPS:
            assert group not in text, group


def test_the_kitchen_hub_no_longer_says_every_comparison_carries_ads() -> None:
    body = KITCHEN_SOURCE.read_text(encoding="utf-8")
    assert "比較記事には広告を含みます" not in body


def test_the_category_cards_say_which_product_kind_is_on_the_shelf() -> None:
    """The widened label stands over a shelf that still holds one product kind."""
    categories = entry_pages()["categories"]
    for key, kind in ON_THE_SHELF.items():
        for field in ("lead", "decides"):
            assert kind in categories[key][field], (key, field)


def test_the_home_call_to_action_names_the_product_kind_it_links_to() -> None:
    """Under 掃除 the old label read as though every vacuum were covered."""
    rows = ledger_rows()
    cta = rows["cleaning"]["reader_role"]["main_cta"]
    target = cta["target"]
    assert target == "compact-robot-vacuum-shortlist"
    # The home card prints the representative article's short_title, and the
    # ledger keeps the hub's main_cta label equal to it.
    assert (
        rows[target]["listing"]["short_title"] == "省スペースのロボット掃除機を比べる"
    )
    assert cta["label"] == rows[target]["listing"]["short_title"], cta


def test_the_excerpts_stay_inside_the_theme_head_bounds() -> None:
    # functions.php only uses a stored excerpt as the meta description when
    # kurashinoshirube_is_clean_text($excerpt, 30, 180) holds.
    for key, excerpt in EXCERPTS.items():
        assert 30 <= len(excerpt) <= 180, (key, len(excerpt))
