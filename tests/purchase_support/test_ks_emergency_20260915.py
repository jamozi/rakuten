"""KS-007 / KS-008 / KS-011 regression guards over the 39 published bodies (2026-09-15 batch).

The tracked bodies under ``changes/wordpress-direct-publish-v1/articles`` are the
publication source. These checks read the visible text only: data-* attributes,
scripts, styles and code samples keep their machine states.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from raos.application.editorial.purchase_support import reader_label
from raos.application.editorial.reader_html import Element, fragment

ROOT = Path(__file__).resolve().parents[2]
ARTICLES = ROOT / "changes/wordpress-direct-publish-v1/articles"
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"

# Internal enums and production-time wording that must never reach a reader.
INTERNAL_TOKENS = re.compile(
    r"\b(?:UNKNOWN|UNAVAILABLE|SOLD_OUT|PREORDER|RECHECK_REQUIRED|newPurchaseSku)\b"
    r"|レビュー中|本文候補|TODO|FIXME|lorem ipsum",
    re.IGNORECASE,
)
SKIPPED_TAGS = frozenset({"script", "style", "template", "code", "pre", "kbd", "samp"})


def ledger_bodies() -> dict[str, str]:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    bodies = {}
    for article in ledger["articles"]:
        source = article.get("body_source")
        if not source:
            continue  # patch-only legacy rows are edited against the live document
        bodies[article["article_key"]] = (ROOT / source).read_text(encoding="utf-8")
    assert len(bodies) >= 39, sorted(bodies)
    return bodies


def visible_text(node: Element) -> str:
    """Reader-visible text: element text nodes outside code/script/style."""
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


def strip_block_comments(html: str) -> str:
    return re.sub(r"<!--\s*/?wp:[^>]*-->", "", html)


@pytest.fixture(scope="module")
def bodies() -> dict[str, str]:
    return ledger_bodies()


@pytest.fixture(scope="module")
def roots(bodies: dict[str, str]) -> dict[str, Element]:
    return {key: fragment(strip_block_comments(html)) for key, html in bodies.items()}


def test_reader_label_hides_internal_states() -> None:
    assert reader_label("UNKNOWN") == "未確認"
    assert reader_label("unavailable") == "未確認"
    assert reader_label(None) == "未確認"
    assert reader_label("  ") == "未確認"
    assert reader_label("公式仕様に購入日より12か月") == "公式仕様に購入日より12か月"
    assert reader_label("UNKNOWN", unknown="販売先で確認") == "販売先で確認"


def test_visible_text_has_no_internal_tokens(roots: dict[str, Element]) -> None:
    """KS-008: production-time wording and enum names never reach the reader."""
    leaks = []
    for key, root in roots.items():
        text = visible_text(root)
        for match in INTERNAL_TOKENS.finditer(text):
            start = max(0, match.start() - 40)
            leaks.append((key, text[start : match.end() + 40]))
    assert leaks == []


def _anchor_targets(root: Element) -> dict[str, Element]:
    targets: dict[str, Element] = {}
    for node in root.walk():
        identity = node.attrs.get("id")
        if isinstance(identity, str) and identity not in targets:
            targets[identity] = node
    return targets


def _inside_compat_block(node: Element) -> bool:
    parent: Element | None = node
    while parent is not None:
        if parent.has("ps-compat-anchors"):
            return True
        parent = parent.parent
    return False


def _reaches_content(node: Element) -> bool:
    """An alias span at the head of a section reaches that section's content."""
    if visible_text(node).strip():
        return True
    parent = node.parent
    return parent is not None and bool(visible_text(parent).strip())


def test_fragment_links_resolve_to_content(roots: dict[str, Element]) -> None:
    """KS-011: no internal fragment link lands on an empty trailing anchor."""
    targets = {key: _anchor_targets(root) for key, root in roots.items()}
    problems = []
    for key, root in roots.items():
        for link in root.find(tag="a"):
            href = link.attrs.get("href") or ""
            match = re.fullmatch(
                r"(?:https://kurashinoshirube\.com)?(?:/([a-z0-9-]+)/)?#([^\s\"]+)", href
            )
            if not match:
                continue
            slug, identity = match.group(1), match.group(2)
            page = slug or key
            if page not in targets:
                problems.append((key, href, "unknown page"))
                continue
            node = targets[page].get(identity)
            if node is None:
                problems.append((key, href, "missing id"))
            elif _inside_compat_block(node):
                problems.append((key, href, "lands on trailing compat anchor"))
            elif not _reaches_content(node):
                problems.append((key, href, "empty target"))
    assert problems == []


def test_compat_anchor_blocks_are_empty(roots: dict[str, Element]) -> None:
    """KS-011: every reviewed legacy bookmark is aliased beside current content."""
    leftovers = {
        key: [n.attrs.get("id") for block in root.find(cls="ps-compat-anchors") for n in block.walk() if n is not block]
        for key, root in roots.items()
    }
    assert {key: ids for key, ids in leftovers.items() if ids} == {}


def test_content_aliases_sit_at_section_start(roots: dict[str, Element]) -> None:
    for key, root in roots.items():
        for alias in root.walk():
            target = alias.attrs.get("data-ps-content-alias")
            if not target:
                continue
            parent = alias.parent
            assert parent is not None and parent.attrs.get("id") in {target, None} or parent.parent is not None, key
            assert visible_text(parent).strip(), (key, alias.attrs.get("id"))


def test_single_h1_per_article_body(roots: dict[str, Element]) -> None:
    """The theme renders the title; bodies of posts and hub pages carry no extra h1."""
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    kinds = {a["article_key"]: (a["post_type"], a["slug"]) for a in ledger["articles"]}
    extra = {
        key: len(root.find(tag="h1"))
        for key, root in roots.items()
        if root.find(tag="h1") and kinds[key][1] != "home"
    }
    assert extra == {}


KS007_FACTS = {
    # DELTA 3 Classic: width x depth x height (20.0 x 39.8 x 28.3 cm) must never be swapped again.
    "DELTA 3 Classic": {
        "dimension_marker": r"\d+\.\d×",
        "must": re.compile(r"(?:幅)?20\.0×(?:奥行)?39\.8×(?:高さ)?28\.3"),
        "forbid": re.compile(r"(?:幅)?39\.8×(?:奥行)?20\.0"),
    },
    # SOLOTA clearance: unverified in official material, never presented as confirmed.
    "SOLOTAの上・左右": {
        "dimension_marker": r"余白",
        "must": re.compile(r"未確認"),
        "forbid": re.compile(r"余白は確認済み"),
    },
}


def test_cross_page_numeric_consistency(roots: dict[str, Element]) -> None:
    """KS-007: every page that states a model's figures states the same figures."""
    failures = []
    for key, root in roots.items():
        text = visible_text(root)
        for subject, rule in KS007_FACTS.items():
            for match in re.finditer(re.escape(subject), text):
                window = text[max(0, match.start() - 250) : match.end() + 250]
                if not re.search(rule["dimension_marker"], window):
                    continue  # the page names the model without stating the figures
                if rule["forbid"].search(window):
                    failures.append((key, subject, "forbidden", rule["forbid"].search(window).group(0)))
                if not rule["must"].search(window):
                    failures.append((key, subject, "missing", rule["must"].pattern))
    assert failures == []


def test_ledger_titles_and_excerpts_have_no_internal_tokens() -> None:
    """KS-008: the excerpt reaches readers as meta description, og/twitter and the standfirst.

    A body-only scan misses it, which is how "比較対象の範囲はレビュー中です。" stayed live
    on post 549 until the 2026-09-15 whole-site production check.
    """
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    production_wording = re.compile(r"レビュー中|本文候補|執筆中|作成中|検討中|仮題|TODO|FIXME")
    leaks = [
        (row["article_key"], field, row[field])
        for row in ledger["articles"]
        for field in ("title", "excerpt")
        if row.get(field) and (INTERNAL_TOKENS.search(row[field]) or production_wording.search(row[field]))
    ]
    assert leaks == []


def test_rakuten_media_pages_carry_the_api_credit(bodies: dict[str, str]) -> None:
    """KS-006: Rakuten Web Service branding appears wherever its media is displayed.

    The theme injects the photos into every `ps-product-media` placeholder, so the
    credit has to follow the placeholder rather than one renderer path.
    """
    missing = [
        key for key, html in bodies.items()
        if "data-ps-media-product" in html and "ps-media-credit" not in html
    ]
    assert missing == []


def test_api_credit_only_where_media_is_shown(bodies: dict[str, str]) -> None:
    """The same guideline forbids the branding on pages that do not use the service."""
    stray = [
        key for key, html in bodies.items()
        if "ps-media-credit" in html and "data-ps-media-product" not in html
    ]
    assert stray == []
