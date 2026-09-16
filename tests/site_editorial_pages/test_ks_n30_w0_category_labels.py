"""Wave 0 of the next30 programme: the two narrow category labels are widened.

The owner widened what readers see for two existing category keys, so that the
dish racks and air fryers of later waves fit ``kitchen`` and the cordless
vacuums fit ``cleaning``. The keys never move; only the visible label does.
Every surface that prints the label — the category directory, the home cards,
the comparison and guide hubs, the category page breadcrumbs and the theme's
journey cards — has to say the same widened word.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "site_builder_n30_w0", ROOT / "scripts/build_site_editorial_pages.py"
)
assert _spec and _spec.loader
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)

ENTRY_PAGES = ROOT / "changes/site-improvements-20260913/entry-pages.v1.json"
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
CLEANING_SOURCE = ROOT / "changes/site-improvements-20260913/entry-pages/cleaning.html"
# /kitchen/ is projected by build_reader_purchase_support_v1.py, so the
# breadcrumb has to be widened in its source, never in the projection.
KITCHEN_SOURCE = ROOT / "changes/reader-purchase-support-v1/articles/kitchen.html"
READER_EXPERIENCE = ROOT / "python/raos/application/editorial/reader_experience_v1.py"
THEME_FUNCTIONS = ROOT / (
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/functions.php"
)

WIDENED = {"kitchen": "台所", "cleaning": "掃除"}
NARROWED = {"kitchen": "食洗機", "cleaning": "ロボット掃除機"}
ORDERED_LABELS = ["スーツケース", "台所", "掃除", "ポータブル電源"]
CATEGORIES_LEAD = (
    "スーツケース・台所・掃除・ポータブル電源から選べます。"
    "代表比較と、条件で候補を絞る節へ直接進めます。"
)


def data() -> dict:
    return json.loads(ENTRY_PAGES.read_text(encoding="utf-8"))


def pages() -> dict[str, str]:
    return {
        "kitchen" if path.stem == "kitchen-template" else path.stem: body
        for path, body in builder.build().items()
        if path.suffix == ".html"
    }


def test_entry_pages_carry_the_widened_label_under_the_same_keys() -> None:
    categories = data()["categories"]
    assert list(categories) == ["travel", "kitchen", "cleaning", "preparedness"]
    for key, label in WIDENED.items():
        assert categories[key]["name"] == label, key
    assert [category["name"] for category in categories.values()] == ORDERED_LABELS


def test_no_category_keeps_the_narrow_product_kind_as_its_name() -> None:
    names = {category["name"] for category in data()["categories"].values()}
    assert names.isdisjoint(set(NARROWED.values()))


def test_the_category_directory_lead_names_the_widened_categories() -> None:
    entry = data()["pages"]["categories"]["description"]
    ledger = {
        row["article_key"]: row
        for row in json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    }
    assert entry == CATEGORIES_LEAD
    assert ledger["categories"]["excerpt"] == CATEGORIES_LEAD
    # The theme navigation projection is built from this literal, not from the
    # entry-pages file, so the widened lead has to be pinned here as well.
    assert CATEGORIES_LEAD in READER_EXPERIENCE.read_text(encoding="utf-8")


def test_the_category_directory_cards_are_headed_by_the_widened_label() -> None:
    body = pages()["categories"]
    headings = re.findall(r'<article class="ks-editorial-card"><h2>([^<]+)</h2>', body)
    assert headings == ORDERED_LABELS
    assert re.findall(r'<p class="ks-directory-lead">([^<]*)</p>', body) == [
        CATEGORIES_LEAD
    ]


def test_the_home_category_cards_link_out_under_the_widened_label() -> None:
    body = pages()["home"]
    start = body.index("ks-home-category-grid")
    grid = body[start : body.index("</section>", start)]
    cards = re.findall(
        r'<h3><a(?: id="[^"]*")? href="/([a-z-]+)/">([^<]+)</a></h3>', grid
    )
    # The home grid leads with the kitchen card; the directory order is checked
    # on /categories/ instead.
    assert dict(cards) == dict(zip(data()["categories"], ORDERED_LABELS))
    for key, label in WIDENED.items():
        assert (key, label) in cards, key


def test_the_comparison_and_guide_hubs_group_under_the_widened_label() -> None:
    rendered = pages()
    jumps = (("comparisons", "ks-comparison-jump"), ("guides", "ks-guide-jump"))
    for slug, jump in jumps:
        body = rendered[slug]
        nav = re.search(r'<nav id="' + jump + r'"[^>]*>(.*?)</nav>', body, flags=re.S)
        assert nav, slug
        assert re.findall(r"<a [^>]*>([^<]+)</a>", nav[1]) == ORDERED_LABELS, slug
    comparisons = rendered["comparisons"]
    for key, label in WIDENED.items():
        assert f'<section id="compare-{key}"><h2>{label}</h2>' in comparisons, key


def test_the_category_page_breadcrumbs_end_on_the_widened_label() -> None:
    sources = {
        "cleaning": CLEANING_SOURCE.read_text(encoding="utf-8"),
        "kitchen": KITCHEN_SOURCE.read_text(encoding="utf-8"),
    }
    for key, body in sources.items():
        crumb = re.search(r'<span aria-current="page">([^<]+)</span>', body)
        assert crumb, key
        assert crumb[1] == WIDENED[key], key


def test_the_theme_journey_cards_use_the_widened_label() -> None:
    php = THEME_FUNCTIONS.read_text(encoding="utf-8")
    journeys = php[php.index("function kurashinoshirube_reader_journeys") :]
    journeys = journeys[: journeys.index("\n}")]
    for key, label in WIDENED.items():
        assert f"'{key}' => array('label' => '{label}'," in journeys, key
    for narrow in NARROWED.values():
        assert f"'label' => '{narrow}'" not in journeys, narrow
