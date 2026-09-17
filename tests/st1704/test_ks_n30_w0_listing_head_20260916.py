"""The post listing's own meta description must use the widened category labels.

``/?post_type=post`` is a public, indexable page whose head is built in the
theme. Its description enumerated the four domains by their old narrow names
while ``/categories/`` — the same set of articles — had already moved to the
widened labels, so the two pages described the same shelf differently. The
enumeration also had to stop naming a single product kind before wave 1 puts
dish racks on that listing.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
THEME_DIR = ROOT / (
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)
FUNCTIONS = THEME_DIR / "functions.php"
ENTRY_PAGES = ROOT / "changes/site-improvements-20260913/entry-pages.v1.json"

LISTING_DESCRIPTION = (
    "スーツケース・台所・掃除・ポータブル電源の記事一覧。"
    "用途や設置条件、仕様の違い、購入前の確認事項から、必要な比較やガイドを探せます。"
)
RETIRED_ENUMERATIONS = (
    "食洗機・ロボット掃除機・スーツケース・ポータブル電源",
    "スーツケース・食洗機・ロボット掃除機・ポータブル電源",
)
RETIRED_TITLES = ("食洗機の選び方・比較", "ロボット掃除機の選び方・比較")


def listing_context() -> str:
    source = FUNCTIONS.read_text(encoding="utf-8")
    body = source.split("function kurashinoshirube_post_listing_head_context", 1)[
        1
    ].split("/**", 1)[0]
    return body


def test_the_post_listing_description_uses_the_widened_labels() -> None:
    found = re.search(r"'description' => '([^']+)'", listing_context())
    assert found, "the listing head no longer declares a description"
    assert found[1] == LISTING_DESCRIPTION, found[1]
    # Same bound the theme enforces on every other public description.
    assert 30 <= len(found[1]) <= 180, len(found[1])


def test_the_listing_names_the_same_categories_in_the_same_order() -> None:
    labels = [
        category["name"]
        for category in json.loads(ENTRY_PAGES.read_text(encoding="utf-8"))[
            "categories"
        ].values()
    ]
    assert LISTING_DESCRIPTION.startswith("・".join(labels) + "の記事一覧。"), labels


def test_no_theme_surface_still_enumerates_the_retired_four_domains() -> None:
    surfaces = [FUNCTIONS, *sorted((THEME_DIR / "templates").glob("*.html"))]
    surfaces.extend(sorted((THEME_DIR / "parts").glob("*.html")))
    for path in surfaces:
        text = path.read_text(encoding="utf-8")
        for enumeration in RETIRED_ENUMERATIONS:
            assert enumeration not in text, (path.name, enumeration)
        for title in RETIRED_TITLES:
            assert title not in text, (path.name, title)
