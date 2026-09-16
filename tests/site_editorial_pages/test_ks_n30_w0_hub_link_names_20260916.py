"""Wave 0 of next30: one hub URL keeps one name on every page that links to it.

The wave renamed the two category pages (「食洗機の選び方・比較」→
「台所の道具の選び方・比較」, 「ロボット掃除機の選び方・比較」→
「掃除の道具の選び方・比較」). The theme prints every post's breadcrumb and its
BreadcrumbList from the hub page's stored title, so an article whose own link
text still says 「食洗機の選び方」 shows two names for one URL on the same screen —
the reader clicks one name and lands on another.

These checks read the published body of every ledger row (what the publisher
would send, not the hand-written source) and refuse any visible link text or
heading that names a hub by a label the hub no longer uses. They also require
the other direction: an article that links to a hub has to call it by the name
the hub answers to today.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from raos.application.editorial.reader_html import Element, fragment
from scripts import build_site_editorial_pages as projection

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"

HUB_KEYS = ("kitchen", "cleaning")
# The product word each hub stopped standing for. 「掃除機」 also catches
# 「ロボット掃除機」; the widened name 「掃除の道具」 does not contain it.
RETIRED_WORDS = {"kitchen": ("食洗機",), "cleaning": ("掃除機",)}
RETIRED_TITLES = ("食洗機の選び方・比較", "ロボット掃除機の選び方・比較")
# Ways the retired labels were written in link text and headings. An external
# link may still quote a manufacturer's own page title, so only internal links
# and headings are read here.
RETIRED_PHRASES = (
    "食洗機の選び方",
    "食洗機選び",
    "ロボット掃除機の選び方",
    "ロボット掃除機選び",
    "掃除機選び",
)
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")


@pytest.fixture(scope="module")
def ledger() -> dict[str, dict]:
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    return {row["article_key"]: row for row in rows}


@pytest.fixture(scope="module")
def documents() -> dict[str, str]:
    """The public body per ledger row, exactly as the publisher would send it."""
    return projection.reader_documents()


def hub_of(href: str | None) -> str | None:
    """The hub a link points at, for a relative or an absolute href."""
    if not href:
        return None
    path = href.split("#", 1)[0].split("?", 1)[0]
    for key in HUB_KEYS:
        if path.endswith(f"/{key}/"):
            return key
    return None


def hub_links(body: str) -> list[tuple[str, Element]]:
    return [
        (hub, anchor)
        for anchor in fragment(body).find(tag="a")
        if (hub := hub_of(anchor.attrs.get("href"))) is not None
    ]


def test_no_published_body_names_a_hub_by_a_label_it_no_longer_uses(
    documents,
) -> None:
    offences = [
        (key, hub, anchor.text())
        for key, body in documents.items()
        for hub, anchor in hub_links(body)
        for word in RETIRED_WORDS[hub]
        if word in anchor.text()
    ]
    assert offences == [], offences


def test_every_article_calls_a_hub_by_the_name_the_hub_answers_to(
    documents, ledger
) -> None:
    """A post links back to its shelf; the label has to be the shelf's own name."""
    for key, row in ledger.items():
        if row["post_type"] != "post":
            continue
        for hub, anchor in hub_links(documents[key]):
            assert ledger[hub]["title"] in anchor.text(), (key, hub, anchor.text())


def test_only_the_revision_note_still_quotes_a_retired_page_title(documents) -> None:
    """One exception, and it is the point: the note tells the reader what changed.

    Everywhere else a retired title is a stale name for a live URL. In the
    revision note it is the名前 the reader had bookmarked, quoted once beside the
    name that replaced it, which is the only way that record means anything.
    """
    policy = documents["about-ad-policy"]
    note = [
        block.text()
        for block in fragment(policy).find(tag="p")
        if "最終更新日" in block.text()
    ]
    assert len(note) == 1, policy[:400]
    for title in RETIRED_TITLES:
        assert note[0].count(title) == 1, (title, note)
        assert policy.count(title) == 1, (title, "quoted outside the revision note")
    for key, body in documents.items():
        if key == "about-ad-policy":
            continue
        for title in RETIRED_TITLES:
            assert title not in body, (key, title)


def test_no_internal_link_or_heading_still_reads_as_the_old_shelf(documents) -> None:
    """The old labels also reached readers as headings and as plain link text."""
    offences: list[tuple[str, str, str]] = []
    for key, body in documents.items():
        root = fragment(body)
        texts = [
            ("link", anchor.text())
            for anchor in root.find(tag="a")
            if (anchor.attrs.get("href") or "").startswith("/")
        ]
        texts += [
            ("heading", node.text())
            for tag in HEADING_TAGS
            for node in root.find(tag=tag)
        ]
        offences += [
            (key, kind, text)
            for kind, text in texts
            for phrase in RETIRED_PHRASES
            if phrase in text
        ]
    assert offences == [], offences


# --- what the wave is allowed to change in a published article ------------
# /updates/ cards every 実質的な本文変更. Renaming the link that points at a hub
# whose own name changed in this same wave is not one: no fact, figure, order or
# recommendation moves, and the rename is announced once on the policy page
# rather than twelve times on /updates/. So a post this wave touched either
# already carries today's card for a change of its own, or it changed nothing
# but the text inside its links to the two renamed hubs.

DECISIONS = ROOT / "changes/next30-20260916/decisions.v1.json"
ARTICLE_PREFIX = "changes/wordpress-direct-publish-v1/articles/"
DAY = "2026-09-16"
HUB_ANCHOR = re.compile(
    r'(<a\b[^>]*href="[^"]*/(?:kitchen|cleaning)/"[^>]*>).*?(</a>)', re.S
)
# The renderer keys each offer snapshot to a hash of the body, so it moves with
# any edit. It is an attribute, not something a reader sees.
SNAPSHOT_ID = re.compile(r'data-raos-snapshot-id="[^"]*"')


def _git(*arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments), cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def base_commit() -> str:
    record = json.loads(DECISIONS.read_text(encoding="utf-8"))
    return record["wave_zero_applied"]["base_commit"]


def without_hub_link_text(body: str) -> str:
    """The body with everything a hub rename is allowed to move taken out."""
    return SNAPSHOT_ID.sub("@snapshot@", HUB_ANCHOR.sub(r"\1@hub@\2", body))


def test_a_post_this_wave_touched_either_cards_its_change_or_only_renamed_the_link(
    ledger,
) -> None:
    base = base_commit()
    by_source = {
        row["body_source"]: row
        for row in ledger.values()
        if row.get("body_source") and row["post_type"] == "post"
    }
    changed = [
        path
        for path in _git(
            "diff", "--name-only", base, "--", ARTICLE_PREFIX
        ).splitlines()
        if path in by_source
    ]
    assert len(changed) == 12, changed

    label_only = []
    for path in changed:
        row = by_source[path]
        log = (row.get("listing") or {}).get("change_log", [])
        if any(entry["date"] == DAY for entry in log):
            continue
        before = without_hub_link_text(_git("show", f"{base}:{path}"))
        after = without_hub_link_text((ROOT / path).read_text(encoding="utf-8"))
        assert before == after, row["slug"]
        label_only.append(row["slug"])
    assert sorted(label_only) == [
        "dishwasher-branch-faucet-guide",
        "dishwasher-cleaning-guide",
        "dishwasher-detergent-guide",
        "dishwasher-running-cost",
        "dishwasher-water-supply-methods",
    ], label_only


def test_the_rename_is_announced_once_where_the_site_records_revisions(
    documents,
) -> None:
    """The reader is told the links were renamed — on the policy page, not per article."""
    policy = documents["about-ad-policy"]
    assert "戻るリンクの文言は新しいページ名に合わせた" in policy, policy[:400]
