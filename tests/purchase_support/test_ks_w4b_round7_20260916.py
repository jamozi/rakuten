"""W4b review round 6 fixes: the /updates/ cards must describe the published body.

The major first. 553's card told readers that APPLITE 4.0's opening was
corrected 「開閉構造は確認中」→「ブックオープニングタイプ」, but the published row
has never shown 「開閉構造は確認中」 for APPLITE: its 使いやすさ・詳細 cell reads
「38L・2.1kg｜ソフトケース」 at origin/main, and the hedged wording only ever
existed in this branch's own intermediate state (two other rows carry it). A
card that starts with 「訂正：」 is read as "the article used to say this", so the
before it names has to be what readers can see today.

The rest are the round-6 minors that are plainly right: cards that leave out a
reader-visible change of the same day -- the 「約」 the body gained (83 and 30),
a link to an article the body did not link before (82 and 83), and the airline
section 553 moved below the comparison table -- and 83's outer-dimension column,
which prints 幅×奥行×高さ for four models while two of the four official pages
give no axis names at all.

Every check derives its subject from the diff between the published body
(origin/main, which is also this batch's base for every article body) and the
body this candidate compiles, so none of them can go stale by naming a slug.
Each test here failed before the round-7 source edits. No ``\b`` is used next to
Japanese text.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path

import pytest

from scripts import build_reader_purchase_support_v1 as builder

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
ARTICLE_PREFIX = "changes/wordpress-direct-publish-v1/articles/"
BATCH_SUBJECT = "KS W4b"
BATCH_NAME = "W4b"
STATUS = ROOT / "changes/ks-integrated-20260915/status.v1.json"
PUBLISHED = "origin/main"
DAY = "2026-09-16"
LIGHT = "lightweight-carry-on-suitcase-under-3kg"
SMALL = "small-carry-on-suitcase-comparison"


def _git(*arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments), cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def _published(slug: str) -> str:
    """The body readers see today. origin/main == this batch's base for bodies."""
    return _git("show", f"{PUBLISHED}:{ARTICLE_PREFIX}{slug}.html")


def _text(body: str) -> str:
    stripped = re.sub(r"(?s)<(script|style).*?</\1>", "", body)
    return html.unescape(re.sub(r"<[^>]+>", "\n", stripped))


def _candidate_bodies() -> set[str]:
    """Every article body this candidate changed, as a slug set.

    On the candidate branch the set comes from the candidate's own commits. The
    PR branch squashes W4a and W4b into one commit, and this rule is about W4b's
    own bodies -- W4a publishes first and owns its own records -- so there the
    set comes from the batch's published document list in ``status.v1.json``.
    """
    log = _git("log", "--format=%H%x1f%s", "HEAD")
    shas = [
        line.split("\x1f")[0]
        for line in log.splitlines()
        if line and line.split("\x1f")[1].startswith(BATCH_SUBJECT)
    ]
    if not shas:
        batches = json.loads(STATUS.read_text(encoding="utf-8"))["batches"]
        return set(batches[BATCH_NAME]["documents"])
    paths: set[str] = set()
    for sha in shas:
        paths.update(_git("show", "--name-only", "--format=", sha).splitlines())
    paths.update(_git("diff", "--name-only", "HEAD", "--", ARTICLE_PREFIX).splitlines())
    return {
        Path(path).stem
        for path in paths
        if path.startswith(ARTICLE_PREFIX) and path.endswith(".html")
    }


@pytest.fixture(scope="module")
def outputs() -> dict[str, str]:
    return {path.stem: body for path, body in builder.build().items() if path.suffix == ".html"}


@pytest.fixture(scope="module")
def cards() -> dict[str, str]:
    """The day's /updates/ summary for every article that has one."""
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    found = {}
    for row in rows:
        for entry in (row.get("listing") or {}).get("change_log", []):
            if entry["date"] == DAY:
                found[row["article_key"]] = entry["summary"]
    return found


# major: a card names a before the published body never showed ---------------------

# 「…」から / 「…」だけでした / 「…」と表示していました: the quote is the state the
# card says the article used to be in. 「…」に直しました / 「…」と表示しました name
# the article's new state and are read against the compiled body. 「…」に合わせ is
# neither -- what it quotes is the official page the value came from.
BEFORE_QUOTE = re.compile(r"「([^「」]+)」(?:から|だけでした|と表示していました|と書いていました)")
AFTER_QUOTE = re.compile(r"「([^「」]+)」(?:に直しました|と表示しました)")


def _rows(body: str) -> dict[str, str]:
    """Each comparison row's visible text, keyed by how the card could name it."""
    found = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        products = re.findall(r'data-raos-product-id="([^"]+)"', row)
        name = re.search(r"<th[^>]*>(.*?)</th>", row, re.S)
        if not products or name is None:
            continue
        identity = " ".join(re.sub(r"<[^>]+>", " ", name.group(1)).split() + products[:1])
        found[identity] = " ".join(_text(row).split())
    return found


def _tokens(identity: str) -> list[str]:
    """Every way a card could name a row: its printed name and its product id.

    The table prints 「アップライト4.0」 where the card prints 「APPLITE 4.0」, so the
    product id counts as a name too (the round-6 tests use the same rule).
    """
    return [t for t in re.split(r"[\s（）()／/、,・\-]+", identity) if len(t) >= 3]


def _mentions(sentence: str, token: str) -> bool:
    """A latin token has to stand on its own: C-LITE must not match APPLITE."""
    if re.fullmatch(r"[\x20-\x7e]+", token):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])"
        return re.search(pattern, sentence) is not None
    return token in sentence


def _named(sentence: str, rows: dict[str, str]) -> list[str]:
    """The rows this sentence names."""
    return [
        text
        for identity, text in rows.items()
        if any(_mentions(sentence, token) for token in _tokens(identity))
    ]


def test_card_before_states_are_what_the_published_body_shows(outputs, cards) -> None:
    """A 訂正 card describes the published article, not an unpublished draft.

    553's card quoted 「開閉構造は確認中」 as APPLITE 4.0's previous opening. That
    string is in the published body twice -- on the PROTECA and Samsonite rows --
    so a whole-body check passes while the claim is still false; the before has
    to be read from the row the sentence names.
    """
    assert len(cards) >= 13, sorted(cards)
    checked = []
    wrong = []
    for slug, summary in sorted(cards.items()):
        published = _published(slug)
        rows = _rows(published)
        for sentence in summary.split("。"):
            for quote in BEFORE_QUOTE.findall(sentence):
                scopes = _named(sentence, rows) or [" ".join(_text(published).split())]
                checked.append((slug, quote))
                if not any(quote in scope for scope in scopes):
                    wrong.append((slug, quote))
            for quote in AFTER_QUOTE.findall(sentence):
                if quote not in " ".join(_text(outputs[slug]).split()):
                    wrong.append((slug, quote, "after"))
    assert wrong == [], wrong
    assert checked != [], "no card quotes a previous state, so this rule proves nothing"


# minor: the card leaves out a reader-visible change of the same day ---------------


def test_card_reports_the_notation_change_its_body_made(outputs, cards) -> None:
    """The batch spent this day writing 「約」 where the official pages write it.

    Ten of the thirteen cards say so. 83 added it to APPLITE's and LIEVE's
    capacity and weight (and to the 600g sentence), 30 to K11+ Pro's station
    height, and neither card mentioned it -- so /updates/ under-reports the very
    change the rest of the batch is announcing.
    """
    missing = []
    for slug, summary in sorted(cards.items()):
        before = _text(_published(slug)).count("約")
        after = _text(outputs[slug]).count("約")
        if after > before and "約" not in summary:
            missing.append((slug, before, after))
    assert missing == [], missing


def _links(body: str) -> set[str]:
    return set(re.findall(r'href="(/[^"#?]*/)"', body))


def test_card_names_an_article_the_body_did_not_link_before(outputs, cards) -> None:
    """A new route to another article is what /updates/ exists to announce.

    19 and 84 name 「小型・機内持ち込みスーツケース比較」 in their cards for exactly
    this change; 82 and 83 gained the same route and named nothing. A link that
    only gets a second copy (19's mid-body route) is not in scope -- that is the
    owner's call on whether it warrants a card at all.
    """
    rows = {row["article_key"]: row for row in json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]}
    candidate = _candidate_bodies()
    assert len(candidate) >= 7, sorted(candidate)
    missing = []
    for slug in sorted(candidate & set(cards)):
        gained = _links(outputs[slug]) - _links(_published(slug))
        for target in sorted(gained):
            row = rows.get(target.strip("/"))
            if row is None:
                continue
            names = {row["title"].split("｜")[0], (row.get("listing") or {}).get("short_title", "")}
            if not any(name and name in cards[slug] for name in names):
                missing.append((slug, target))
    assert missing == [], missing


# A card that names the new heading without saying the block moved leaves the
# reader looking for it where it used to be.
MOVED_WORDS = ("移し", "移動", "下へ", "上へ", "末尾へ", "冒頭へ", "後ろへ", "前へ")


def _sections(body: str) -> list[str]:
    return re.findall(r'<section[^>]*id="([^"]+)"', body)


def _moved(before: list[str], after: list[str]) -> list[str]:
    """Section ids in both orders that no common subsequence can keep in place."""
    shared_before = [s for s in before if s in set(after)]
    shared_after = [s for s in after if s in set(before)]
    table = [[0] * (len(shared_after) + 1) for _ in range(len(shared_before) + 1)]
    for i, left in enumerate(shared_before, 1):
        for j, right in enumerate(shared_after, 1):
            table[i][j] = (
                table[i - 1][j - 1] + 1 if left == right else max(table[i - 1][j], table[i][j - 1])
            )
    keep: list[str] = []
    i, j = len(shared_before), len(shared_after)
    while i and j:
        if shared_before[i - 1] == shared_after[j - 1]:
            keep.append(shared_before[i - 1])
            i, j = i - 1, j - 1
        elif table[i - 1][j] >= table[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return [s for s in shared_before if s not in set(keep)]


def test_card_reports_the_section_this_candidate_moved(outputs, cards) -> None:
    """553 moved the airline table from the top of the article to below the table.

    A reader who knows the article looks for that block where it used to be, so
    the card has to name its new heading. The moved set is computed from the two
    bodies, not written down here.
    """
    moved = {}
    for slug in sorted(_candidate_bodies() & set(cards)):
        published = _published(slug)
        for section in _moved(_sections(published), _sections(outputs[slug])):
            heading = re.search(
                r'<section[^>]*id="' + re.escape(section) + r'".*?<h2[^>]*>(.*?)</h2>',
                outputs[slug],
                re.S,
            )
            assert heading, (slug, section)
            moved[(slug, section)] = re.sub(r"<[^>]+>", "", heading.group(1)).strip()
    assert moved, "no section moved, so this rule proves nothing"
    unreported = []
    for key, heading in sorted(moved.items()):
        said = [
            sentence
            for sentence in cards[key[0]].split("。")
            if heading in sentence and any(word in sentence for word in MOVED_WORDS)
        ]
        if not said:
            unreported.append((key, heading))
    assert unreported == [], (unreported, moved)


# minor: an axis-named column over models whose official pages name no axis --------

AXIS_LABEL = "通常時外寸（幅×奥行×高さ）"
EDITORIAL_ASSIGNMENT = "編集部"


def test_outer_dimension_axis_note_covers_every_model_in_the_column(outputs) -> None:
    """83 prints 幅×奥行×高さ for four models; two official pages name no axis.

    Re-fetched 2026-09-16 by me: PROTECA 01521-09 (エース公式通販 store.ace.jp,
    HTTP 200, 134,490 bytes) says 「H55×W36×D23 cm」 and FREQUENTER LIEVE 1-250
    (bagworld.co.jp, HTTP 200, 140,587 bytes) says 「横35cm×縦55cm×奥行23m」 --
    both name the edges. AMERICAN TOURISTER QJ6-68002 (HTTP 200, 324,550 bytes)
    says 「サイズ（外寸）: 55 x 35 x 25/28 cm」 and Samsonite CS2*09007 (rendered
    in Chromium, HTTP 200) says 「55.0 x 40.0 x 20.0 cm」 -- neither does. 553
    already tells its readers which edge names are the editor's; 83 claimed the
    names for all four. The note must account for every row in the column.
    """
    body = outputs[LIGHT]
    rows = {
        identity: text
        for identity, text in _rows(body).items()
        if AXIS_LABEL in text.replace(" ", "")
    }
    assert len(rows) == 4, sorted(rows)
    note = next(
        (
            re.sub(r"<[^>]+>", "", match)
            for match in re.findall(r"<p class=\"ps-note[^\"]*\"[^>]*>(.*?)</p>", body, re.S)
            if "軸名" in re.sub(r"<[^>]+>", "", match)
        ),
        None,
    )
    assert note, "no note states where the axis names come from"
    assert EDITORIAL_ASSIGNMENT in note, note
    unaccounted = []
    for identity in sorted(rows):
        if not any(_mentions(note, token) for token in _tokens(identity)):
            unaccounted.append(identity)
    assert unaccounted == [], (unaccounted, note)
