"""W4b review round 5 fixes, re-stacked on the round-6 W4a head.

The major first: the phone-width work in the previous round sized both new
tables against a 302px scroll frame, which left out
``.raos-article-shell { padding-inline: 1rem }``. The real frame at 320px is
286px, so neither table framed a whole data cell there -- the defect the round-4
review reported was recorded as solved while it was still present, because the
binding test had 302.0 written into it. ``phone_table_frames`` now carries the
measured frames and the harness that produces them.

Then the minors that are plainly right: 19 and 84 gained an /updates/ card in
the previous round without a line in their own 確認・更新履歴; 553's card named
one of the five openings it changed that day; 553 dropped the 座席下 half of
ANA's and ソラシドエア's 追加条件 that 83 states in full; and the evidence file's
unresolved list was one row short of the article.

Bodies compile in memory from ``changes/reader-purchase-support-v1`` so each
check follows the editorial source. Every test here failed before the round-6
source edits. No ``\b`` is used next to Japanese text.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from scripts import build_reader_purchase_support_v1 as builder
from tests.purchase_support import phone_table_frames

ROOT = Path(__file__).resolve().parents[2]
THEME_CSS = ROOT / (
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/theme.css"
)
CATALOG = ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
EVIDENCE = ROOT / "changes/ks-integrated-20260915/evidence/KS-131.md"
SMALL = "small-carry-on-suitcase-comparison"
LIGHT = "lightweight-carry-on-suitcase-under-3kg"
BROAD = "carry-on-suitcase-comparison"
FRONT = "front-open-carry-on-suitcase-with-stopper"
DAY = "2026-09-16"


def test_fit_matrix_frames_a_whole_data_cell_on_a_phone() -> None:
    """The fit matrix needs the same constraint the robot space table has.

    ``table-layout:fixed`` splits ``min-width - first column`` between the data
    columns, so one of them fits beside the sticky model column only when
    ``(min-width - head) / columns <= frame - head``. The frames are measured;
    see ``tests/purchase_support/phone_table_frames.py``.
    """
    css = THEME_CSS.read_text(encoding="utf-8")
    base = css.replace(" ", "")
    phone = phone_table_frames.phone_block(css)
    declared = re.search(r"table\.sc-fit-table\{[^}]*?min-width:(\d+(?:\.\d+)?)rem", base)
    assert declared, "sc-fit-table min-width"
    assert "table-layout:fixed" in base, "sc-fit-table relies on the fixed layout"
    override = re.search(r"table\.sc-fit-table\{[^}]*?min-width:(\d+(?:\.\d+)?)rem!important", phone)
    total = float((override or declared).group(1)) * 16
    head_rule = re.search(
        r"table\.sc-fit-table:is\(theadth:first-child,tbodyth\)\{[^}]*?width:(\d+(?:\.\d+)?)rem",
        phone,
    ) or re.search(
        r"table\.sc-fit-table:is\(theadth:first-child,tbodyth\)\{[^}]*?width:(\d+(?:\.\d+)?)rem",
        base,
    )
    assert head_rule, "sc-fit-table sticky first column width"
    head = float(head_rule.group(1)) * 16
    columns = phone_table_frames.data_columns(SMALL, "sc-fit-table")
    assert columns == 5, columns
    for viewport, frame in sorted(phone_table_frames.ARTICLE_SCROLL_FRAME.items()):
        assert (total - head) / columns <= frame - head, (viewport, frame, total, head)


def test_measured_frames_agree_with_the_css_that_produces_them() -> None:
    """The measured constants must stay tied to the rules that create the frame.

    ``.raos-article-shell`` takes 1rem off each side at these widths and the
    scroll container draws a 1px border on each side, so an article body's frame
    is ``viewport - 34``. The round this replaced used ``viewport - 18`` (302 at
    320px): it counted the border and not the padding. Reading both numbers out
    of the stylesheets means a change to either one fails here rather than
    silently making the table rules wrong again.
    """
    editorial = (THEME_CSS.parent / "editorial-v2.css").read_text(encoding="utf-8")
    phone_shell = re.search(
        r"@media \(max-width: 48rem\) \{.*?\.raos-article-shell \{ padding-inline: (\d+(?:\.\d+)?)rem; \}",
        editorial,
        re.S,
    )
    assert phone_shell, "article shell phone padding"
    padding = float(phone_shell.group(1)) * 16
    border = re.search(
        r"\.sc-table-scroll\{[^}]*?border:(\d+(?:\.\d+)?)px solid", THEME_CSS.read_text(encoding="utf-8")
    )
    assert border, "scroll container border"
    inset = 2 * padding + 2 * float(border.group(1))
    assert inset == 34.0, inset
    assert sorted(phone_table_frames.ARTICLE_SCROLL_FRAME) == [320, 360, 375, 390]
    for viewport, frame in phone_table_frames.ARTICLE_SCROLL_FRAME.items():
        assert frame == viewport - inset, (viewport, frame, inset)


@pytest.fixture(scope="module")
def outputs() -> dict[str, str]:
    return {path.stem: body for path, body in builder.build().items() if path.suffix == ".html"}


@pytest.fixture(scope="module")
def catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ledger() -> dict:
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    return {row["article_key"]: row for row in rows}


# minor: an /updates/ card without a line in the article's own history -------------

# Bodies this candidate changed against its base, read from its own commits plus
# the working tree -- the shape W4a uses for the same kind of batch-wide rule.
BATCH_SUBJECT = "KS W4b"
BATCH_NAME = "W4b"
STATUS = ROOT / "changes/ks-integrated-20260915/status.v1.json"
ARTICLE_PREFIX = "changes/wordpress-direct-publish-v1/articles/"


def _git(*arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments), cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def _batch_shas() -> list[str]:
    log = _git("log", "--format=%H%x1f%s", "HEAD")
    return [
        line.split("\x1f")[0]
        for line in log.splitlines()
        if line and line.split("\x1f")[1].startswith(BATCH_SUBJECT)
    ]


def _published_documents() -> set[str]:
    """The documents this candidate published, from the publication record."""
    batches = json.loads(STATUS.read_text(encoding="utf-8"))["batches"]
    return set(batches[BATCH_NAME]["documents"])


def _batch_bodies() -> set[str]:
    """Every article body this candidate changed, as a slug set.

    On the candidate branch the set comes from the candidate's own commits. The
    PR branch squashes W4a and W4b into one commit, and this rule is about W4b's
    own bodies -- W4a publishes first and owns its own records -- so there the
    set comes from the batch's published document list in ``status.v1.json``.
    """
    shas = _batch_shas()
    if not shas:
        return _published_documents()
    paths = set()
    for sha in shas:
        paths.update(_git("show", "--name-only", "--format=", sha).splitlines())
    paths.update(_git("diff", "--name-only", "HEAD", "--", ARTICLE_PREFIX).splitlines())
    return {
        Path(path).stem
        for path in paths
        if path.startswith(ARTICLE_PREFIX) and path.endswith(".html")
    }


def test_every_body_this_candidate_carded_today_shows_the_day_in_its_own_history(
    outputs, ledger
) -> None:
    """The rule the previous round applied to four slugs, applied to all of them.

    That round named 82, 83, 30 and 85 and added the 9/16 line to each, then gave
    19 and 84 an /updates/ card in the same commit -- so two articles tell
    /updates/ they changed today while their own 確認・更新履歴 does not say so.
    Deriving the set from this candidate's own diff is what stops a hard-coded
    list going stale the next time a body joins the batch. Bodies outside this
    candidate are not in scope: W4a publishes first and owns its own records.
    """
    changed = _batch_bodies()
    assert len(changed) >= 10, sorted(changed)
    missing = []
    for slug in sorted(changed):
        row = ledger.get(slug)
        if row is None or slug not in outputs:
            continue
        if not any(
            entry["date"] == DAY for entry in (row.get("listing") or {}).get("change_log", [])
        ):
            continue
        history = re.search(r'<details class="ps-history">(.*?)</details>', outputs[slug], re.S)
        if history is None:
            continue
        if f'<time datetime="{DAY}">' not in history.group(1):
            missing.append(slug)
    assert missing == [], missing


# minor: the card names one of the five openings it changed ------------------------

OPENING_WORDS = ("開き方", "開閉", "ファスナー", "フロントオープン", "ブックオープニング")
USABILITY_LABEL = "使いやすさ・詳細"


def _batch_base() -> str:
    """The body this candidate started from.

    The first batch commit's parent on the candidate branch; on the PR branch,
    where the batch is squashed with W4a, the published bodies on origin/main.
    """
    batch = _batch_shas()
    if batch:
        return _git("rev-parse", f"{batch[-1]}^").strip()
    return _git("rev-parse", "origin/main").strip()


def _openings(text: str) -> dict[str, str]:
    """Each comparison row's opening note, keyed by the row's product name."""
    table = re.search(r'<table class="ps-row-comparison ps-matrix-comparison".*?</table>', text, re.S)
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
        identity = " ".join(plain.split() + re.findall(r'data-raos-product-id="([^"]+)"', row)[:1])
        found[identity] = re.sub(r"<[^>]+>", "", note.group(1)).strip()
    return found


def _name_tokens(name: str) -> list[str]:
    """Every way the card could name the row: its displayed name and its id.

    The table writes 「アップライト4.0」 and the card writes 「APPLITE 4.0」 for the
    one product, so the product id (PRD-AMERICAN-TOURISTER-APPLITE-4-…) has to
    count as a name too.
    """
    return [t for t in re.split(r"[\s（）()／/、,・\-]+", name) if len(t) >= 3]


def test_card_names_every_opening_it_changed_that_day(ledger) -> None:
    """/updates/ promises the specific changes, and the opening is one of three axes.

    The previous round named APPLITE alone while five of the twelve rows took a
    new opening the same day, and the same card lists three of 無印良品's four
    new values -- so a reader comparing the card with the row sees a different
    count. The changed set is read from this candidate's own diff.
    """
    body = Path("changes/wordpress-direct-publish-v1/articles/small-carry-on-suitcase-comparison.html")
    before = _openings(_git("show", f"{_batch_base()}:{body.as_posix()}"))
    after = _openings((ROOT / body).read_text(encoding="utf-8"))
    changed = sorted(name for name, note in after.items() if before.get(name) != note)
    assert len(changed) == 5, changed
    entry = next(
        e
        for e in ledger["small-carry-on-suitcase-comparison"]["listing"]["change_log"]
        if e["date"] == DAY
    )
    sentences = entry["summary"].split("。")
    unreported = []
    for name in changed:
        tokens = _name_tokens(name)
        if not any(
            any(token in sentence for token in tokens)
            and any(word in sentence for word in OPENING_WORDS)
            for sentence in sentences
        ):
            unreported.append(name)
    assert unreported == [], unreported


# minor: two articles in one candidate state one official condition differently -----

PERSONAL_ITEM = "身の回り品"


def _condition_cells(body: str) -> dict[str, str]:
    """The 追加条件 cell of each airline row, keyed by the carrier's official URL."""
    table = re.search(r"<table[^>]*-airline-table[^>]*>.*?</table>", body, re.S)
    assert table, "airline table"
    cells = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(0), re.S):
        links = re.findall(r'<th[^>]*>.*?href="([^"]+)"', row, re.S)
        columns = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(links) != 1 or not columns:
            continue
        cells[links[0]] = re.sub(r"<[^>]+>", "", columns[-1]).strip()
    return cells


def test_both_suitcase_articles_state_the_same_personal_item_condition(outputs) -> None:
    """One candidate must not publish one carrier's rule two ways on the same day.

    ソラシドエア's page reads 「前の座席の下に収納できる大きさ、かつ「40cm×30cm×20cm
    以内」」 and ANA's notice says the same; 83 writes both halves and 553 dropped
    the under-seat half. Both tables say 2026年9月16日確認, so a reader moving
    between them sees the same carrier checked the same day with two conditions.
    """
    light = _condition_cells(outputs[LIGHT])
    small = _condition_cells(outputs[SMALL])
    shared = sorted(set(light) & set(small))
    assert len(shared) >= 6, shared
    differing = []
    for url in shared:
        clauses = [
            tuple(c for c in cell.split("。") if PERSONAL_ITEM in c)
            for cell in (light[url], small[url])
        ]
        if clauses[0] != clauses[1]:
            differing.append((url, clauses))
    assert differing == [], differing


# minor: the record's unresolved list is one row short of the article ---------------

HEDGE = "開閉構造は確認中"


def test_record_lists_every_row_whose_opening_is_still_unverified(catalog) -> None:
    """The owner counts remaining work here, so the list has to match the table.

    The record named three model numbers while the table hedges four --
    Samsonite C-Lite was missing, so the list read one item short. Deriving the
    set from the published rows is what keeps the two in step.
    """
    body = (
        ROOT / "changes/wordpress-direct-publish-v1/articles/small-carry-on-suitcase-comparison.html"
    ).read_text(encoding="utf-8")
    products = {p["product_id"]: p for p in catalog["products"]}
    hedged = set()
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        group = re.search(USABILITY_LABEL + r"</span>(.*?)</div>", row, re.S)
        if group is None or HEDGE not in re.sub(r"<[^>]+>", "", group.group(1)):
            continue
        for product_id in re.findall(r'data-raos-product-id="([^"]+)"', row)[:1]:
            # The model code as the article prints it: 01521, CS2*09007, 1-250, 06316
            # (exact_model carries a longer form for two of them, e.g. 01521-09).
            code = re.search(r"[A-Za-z0-9*\-]+$", products[product_id]["name"])
            assert code, product_id
            hedged.add(code.group(0))
    assert len(hedged) == 4, sorted(hedged)
    unresolved = EVIDENCE.read_text(encoding="utf-8").split("## 未解決", 1)[1]
    opening = next(line for line in unresolved.splitlines() if "開き方が未確認" in line)
    missing = sorted(model for model in hedged if model not in opening)
    assert missing == [], (missing, opening)


# minor: the axis note claimed more than the pages leave out -----------------------

WITHDRAWN_AXIS_NOTE = "3辺の数値だけを示し、どの数値が高さ・幅・奥行かは書いていません"
AXIS_NOTE = "各辺の数値に高さ・幅・奥行の語を付けていません"
AIRDO_FIGURE = "AIRDOはサイズ図で55cmを縦、40cmを横、25cmを奥行の矢印に示しています"


def test_axis_note_states_only_what_the_official_pages_leave_out(outputs, catalog) -> None:
    """AIRDO's only source is a figure, and the figure does assign the edges.

    Re-fetched 2026-09-16: airdo.jp/departure/baggage/carry-on-baggage/ (HTTP
    200, 109,176 bytes) carries no dimension in its text, and the size image
    carry-on-baggage02-2609.png (HTTP 200, 86,011 bytes) draws 55cm on the
    vertical arrow, 40cm on the horizontal one and 25cm on the receding one
    (身の回り品: 40 / 30 / 20 the same way). So the word 高さ・幅・奥行 is absent,
    but 「どの数値が…かは書いていません」 overstates it for AIRDO. The carriers are
    still derived from the rules that publish per-edge limits with no axis names.
    """
    rules = {
        rule["rule_id"]: rule
        for rule in next(
            a for a in catalog["articles"] if a["slug"] == SMALL
        )["carry_on_fit"]["rules"]
    }
    unnamed = [
        link["label"]
        for rule in rules.values()
        if rule["edges_cm"] and not rule["edge_axes"] and rule["in_fit_matrix"]
        for link in rule["carrier_links"]
    ]
    assert unnamed == ["JAL", "ANA", "スカイマーク", "AIRDO", "ソラシドエア", "スターフライヤー"]
    text = re.sub(r"<[^>]+>", "", outputs[SMALL])
    assert WITHDRAWN_AXIS_NOTE not in text
    assert text.count("・".join(unnamed) + "は、" + AXIS_NOTE) == 2, text.count(AXIS_NOTE)
    assert AIRDO_FIGURE in text
    # The locator has to carry what the figure shows, or the note has no source.
    assert "55 が縦" in rules["airdo"]["locator"], rules["airdo"]["locator"]
