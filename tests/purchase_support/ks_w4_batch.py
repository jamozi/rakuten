"""The 2026-09-16 batch (W4a・W4b) as the tracked records describe it.

The batch-wide rules below used to ask git: they looked for commits whose
subject began 「KS W4a」/「KS W4b」 and diffed the working tree against
``origin/main``. Both inputs are properties of *this branch*, not of the work:
a squash merge rewrites the subject and moves ``origin/main`` onto the very
bodies the rules call "before", so every one of those rules either goes red or
goes vacuous the moment the branch lands. Worse, the two candidate commits
(``ad936713`` / ``9fa8ee45``) exist only in local branches, so naming them
directly would fail in any fresh clone.

So the batch is read from what the repository keeps for good:

``changes/ks-integrated-20260915/status.v1.json``
    ``batches[W4a|W4b].documents`` — what the publish actually sent.
``changes/wordpress-direct-publish-v1/articles.v1.json``
    ``listing.change_log`` — the card each body owes /updates/ for that day.
``changes/wordpress-direct-publish-v1/articles/updates.html``
    the generated /updates/ page — what a reader is told changed that day.
``ks_w4_published_before.json``
    the state of each of those bodies *before* the publish, captured from the
    commit the batch was written against, for the rules that compare a card
    with the article it corrects.

The first three are independent of each other -- the publication record, the
ledger and the reader-facing page -- so requiring them to agree in both
directions is what keeps a record from setting the scope of its own audit.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "changes/ks-integrated-20260915"
STATUS = PACKAGE / "status.v1.json"
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
ARTICLES = ROOT / "changes/wordpress-direct-publish-v1/articles"
UPDATES = ARTICLES / "updates.html"
BEFORE = Path(__file__).with_name("ks_w4_published_before.json")

#: The day both candidates were published (and the date every card carries).
PUBLISH_DAY = "2026-09-16"
#: The two candidates of this batch, in publication order.
BATCH_NAMES = ("W4a", "W4b")
PUBLISHED = "PUBLISHED_AND_READBACK_VERIFIED"
ARTICLE_PREFIX = "changes/wordpress-direct-publish-v1/articles/"


def status() -> dict:
    return json.loads(STATUS.read_text(encoding="utf-8"))


def ledger_rows() -> dict[str, dict]:
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    return {row["article_key"]: row for row in rows}


def change_log(row: dict) -> list[dict]:
    return (row.get("listing") or {}).get("change_log", [])


def batch_documents(*names: str) -> set[str]:
    """Every document the named candidates published, from the publication record."""
    batches = status()["batches"]
    chosen = names or BATCH_NAMES
    found: set[str] = set()
    for name in chosen:
        batch = batches[name]
        assert batch["publication_status"] == PUBLISHED, name
        found |= set(batch["documents"])
    return found


def batch_article_documents(*names: str) -> set[str]:
    """The batch's documents that are articles carrying a 確認・更新履歴.

    Hub, purpose and entry pages are published by the same candidate and have no
    listing of their own, so only these owe /updates/ a card.
    """
    rows = ledger_rows()
    return {
        slug
        for slug in batch_documents(*names)
        if slug in rows and "change_log" in (rows[slug].get("listing") or {})
    }


def carded(day: str = PUBLISH_DAY) -> dict[str, str]:
    """Each article whose ledger row reports a change on ``day``, with its card."""
    found = {}
    for key, row in ledger_rows().items():
        for entry in change_log(row):
            if entry["date"] == day:
                found[key] = entry["summary"]
    return found


#: One /updates/ card: its link target and the 内容更新日 its meta line prints.
UPDATES_CARD = re.compile(
    r'<article class="ks-editorial-card">.*?<h3><a href="/([^"/]+)/"'
    r".*?内容更新日：(\d{4}-\d{2}-\d{2})",
    re.S,
)


def updates_page_slugs(day: str = PUBLISH_DAY) -> set[str]:
    """The articles the generated /updates/ page shows as updated on ``day``."""
    page = UPDATES.read_text(encoding="utf-8")
    return {slug for slug, when in UPDATES_CARD.findall(page) if when == day}


# Body parsers ------------------------------------------------------------------
# Shared so that a body read from the before-record and a body compiled from the
# sources are always read the same way.


def text(body: str) -> str:
    stripped = re.sub(r"(?s)<(script|style).*?</\1>", "", body)
    return html.unescape(re.sub(r"<[^>]+>", "\n", stripped))


def flat(body: str) -> str:
    return " ".join(text(body).split())


def rows(body: str) -> dict[str, str]:
    """Each comparison row's visible text, keyed by how a card could name it."""
    found = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        products = re.findall(r'data-raos-product-id="([^"]+)"', row)
        name = re.search(r"<th[^>]*>(.*?)</th>", row, re.S)
        if not products or name is None:
            continue
        identity = " ".join(
            re.sub(r"<[^>]+>", " ", name.group(1)).split() + products[:1]
        )
        found[identity] = flat(row)
    return found


def sections(body: str) -> list[str]:
    return re.findall(r'<section[^>]*id="([^"]+)"', body)


def internal_links(body: str) -> set[str]:
    return set(re.findall(r'href="(/[^"#?]*/)"', body))


USABILITY_LABEL = "使いやすさ・詳細"


def openings(body: str) -> dict[str, str]:
    """Each matrix-comparison row's opening note, keyed by the row's product name."""
    table = re.search(
        r'<table class="ps-row-comparison ps-matrix-comparison".*?</table>', body, re.S
    )
    assert table, "matrix comparison table"
    found = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(0), re.S):
        name = re.search(r"<th[^>]*>(.*?)</th>", row, re.S)
        group = re.search(USABILITY_LABEL + r"</span>(.*?)</div>", row, re.S)
        if name is None or group is None:
            continue
        note = re.search(r"<small>(.*?)</small>", group.group(1), re.S)
        if note is None:
            continue
        plain = re.sub(r"<[^>]+>", " ", name.group(1)).replace("公式の仕様を見る", "")
        identity = " ".join(
            plain.split() + re.findall(r'data-raos-product-id="([^"]+)"', row)[:1]
        )
        found[identity] = re.sub(r"<[^>]+>", "", note.group(1)).strip()
    return found


# The published state each card corrects ----------------------------------------


def before_record() -> dict:
    return json.loads(BEFORE.read_text(encoding="utf-8"))


def published_before(slug: str) -> dict:
    """What the body showed before this batch published it.

    Keys: ``body_sha256`` (of the pre-publish file), ``text``, ``rows``,
    ``sections``, ``links``, ``openings`` and ``approximations`` (the count of
    「約」 in the visible text).
    """
    return before_record()["bodies"][slug]


def capture(ref: str = "origin/main") -> dict:
    """Rebuild ``ks_w4_published_before.json`` from a commit that predates W4.

    Run as ``.venv/bin/python -m tests.purchase_support.ks_w4_batch <ref>`` from
    the repository root while a pre-publish commit is still reachable. Every
    body this batch changed is read out of ``<ref>`` and reduced to what the
    card rules compare; the file also keeps each body's sha256, so its text can
    never be edited afterwards without the recorded digest disagreeing.
    """
    import hashlib
    import subprocess

    head = subprocess.run(
        ("git", "rev-parse", ref),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    bodies: dict[str, dict] = {}
    for slug in sorted(batch_article_documents()):
        raw = subprocess.run(
            ("git", "show", f"{ref}:{ARTICLE_PREFIX}{slug}.html"),
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        body = raw.decode("utf-8")
        record = {
            "body_sha256": hashlib.sha256(raw).hexdigest(),
            "approximations": text(body).count("約"),
            "sections": sections(body),
            "links": sorted(internal_links(body)),
            "rows": rows(body),
            "text": flat(body),
        }
        try:
            record["openings"] = openings(body)
        except AssertionError:
            record["openings"] = {}
        bodies[slug] = record
    return {
        "schema": "RAOS_KS_W4_PUBLISHED_BEFORE_V1",
        "captured_from": {"ref": ref, "commit": head},
        "publish_day": PUBLISH_DAY,
        "batches": list(BATCH_NAMES),
        "bodies": bodies,
    }


if __name__ == "__main__":  # pragma: no cover - capture harness
    import sys

    BEFORE.write_text(
        json.dumps(
            capture(*sys.argv[1:2]), ensure_ascii=False, indent=1, sort_keys=False
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {BEFORE}")
