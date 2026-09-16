"""W4b review round 3 fixes, re-stacked on the W4a head.

Two findings the round-4 reviews left open, plus the minors that are plainly
right: 83's /updates/ card omitted AIRDO while 553's card on the same page named
it; 553's APPLITE row said 開閉構造は確認中 although the official page states the
opening; the 無印良品 row dated only three of the four values it took on
2026-09-16; 83 and 30 are approved layouts this candidate rewrote without a
pending_revision; 83 and 82 gained an /updates/ card without a line in their own
確認・更新履歴; the 553 summary bullet claimed 国内線 for carriers whose scope the
same bullet says is unstated; and the evidence file had no record of this round.

Bodies compile in memory from ``changes/reader-purchase-support-v1`` so each
check follows the editorial source. Every test here failed before the round-5
source edits. No ``\\b`` is used next to Japanese text.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

import pytest

from raos.application.editorial.reader_html import Element, fragment
from scripts import build_reader_purchase_support_v1 as builder

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
EVIDENCE = ROOT / "changes/ks-integrated-20260915/evidence/KS-131.md"
SMALL = "small-carry-on-suitcase-comparison"
LIGHT = "lightweight-carry-on-suitcase-under-3kg"
UNDER100 = "carry-on-suitcase-under-100-seats"
ROBOT = "compact-robot-vacuum-shortlist"
STATION = "roomba-mini-vs-switchbot-k11-pro"
DAY = "2026-09-16"
NO_SCOPE = "対象便は公式ページに記載なし"
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


@pytest.fixture(scope="module")
def catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ledger() -> dict:
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    return {row["article_key"]: row for row in rows}


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
    return "".join(parts)


def by_id(root: Element, element_id: str) -> Element:
    found = [node for node in root.walk() if node.attrs.get("id") == element_id]
    assert len(found) == 1, element_id
    return found[0]


def rules(catalog: dict) -> list[dict]:
    article = next(a for a in catalog["articles"] if a["slug"] == SMALL)
    return article["carry_on_fit"]["rules"]


def same_day_summary(ledger: dict, slug: str) -> str:
    entries = [e for e in ledger[slug]["listing"]["change_log"] if e["date"] == DAY]
    assert len(entries) == 1, (slug, [e["date"] for e in ledger[slug]["listing"]["change_log"]])
    return entries[0]["summary"]


def detail_cell(body: str, product_key: str) -> str:
    row = re.search(rf'<tr id="product-{product_key}".*?</tr>', body, re.S)
    assert row, product_key
    group = re.search(
        r'<div class="ps-matrix-spec-group"><span[^>]*>使いやすさ・詳細</span>(.*?)<details>',
        row.group(0),
        re.S,
    )
    assert group, product_key
    return re.sub(r"<[^>]+>", "", group.group(1))


def row_text(body: str, product_key: str) -> str:
    row = re.search(rf'<tr id="product-{product_key}".*?</tr>', body, re.S)
    assert row, product_key
    return re.sub(r"<[^>]+>", "", row.group(0))


# (a) 83 and 553 describe the same correction ---------------------------------------


def test_scope_correction_names_every_carrier_it_changed(ledger, catalog) -> None:
    """/updates/ shows both cards, so both must name the same carriers.

    83's card listed スカイマーク and ソラシドエア only while 553's card on the
    same page named AIRDO too, although 83's own table changed AIRDO's row.
    """
    undeclared = [rule["carrier"] for rule in rules(catalog) if rule["scope"] == NO_SCOPE]
    assert len(undeclared) == 3, undeclared
    missing: list[tuple[str, str]] = []
    for slug in (SMALL, LIGHT):
        summary = same_day_summary(ledger, slug)
        # The carriers have to stand in the 対象便 clause, not merely somewhere
        # in the card: 83 named AIRDO only in the size clause beside it.
        clauses = [c for c in re.split(r"[。、]", summary) if "対象便" in c]
        assert len(clauses) == 1, (slug, summary)
        for carrier in undeclared:
            if carrier not in clauses[0]:
                missing.append((slug, carrier))
    assert missing == []


def test_both_cards_state_the_scope_correction_in_one_list(ledger, catalog) -> None:
    undeclared = [rule["carrier"] for rule in rules(catalog) if rule["scope"] == NO_SCOPE]
    joined = "・".join(undeclared) + "の対象便"
    for slug in (SMALL, LIGHT):
        assert joined in same_day_summary(ledger, slug), slug


# (b) the APPLITE opening -----------------------------------------------------------


def test_applite_row_states_the_opening_its_official_page_states(outputs) -> None:
    """The official product page describes the opening, so the row must not hedge.

    https://www.americantourister.jp/american-tourister/applite4_0/spinner55exp/grey_red
    (re-fetched 2026-09-16, HTTP 200, 324545 bytes, ページ内に「品番: QJ6-68002」)
    shows in the visible product-long-description:
    「フタ部分を薄く、メイン収納部を深く設計したブックオープニングタイプ仕様で、…
    フタを90度開くだけで荷物の出し入れができるため…」
    """
    label = detail_cell(outputs[SMALL], "applite-qj6-68002")
    assert "ブックオープニングタイプ" in label, label
    assert "確認中" not in label, label
    assert "未確認" not in label, label
    # The wording is the collection description, hedged the way PROTECA's 素材 is.
    assert "公式のコレクション説明" in label, label


def test_applite_opening_is_reported_on_updates(ledger) -> None:
    summary = same_day_summary(ledger, SMALL)
    assert "ブックオープニングタイプ" in summary, summary


def test_rows_that_hedge_still_have_no_official_opening(outputs) -> None:
    """Only APPLITE had a stated opening; the other three stay 確認中."""
    for key in ("aeroflex-01521", "lieve-1-250", "cresta-06316"):
        assert "確認中" in detail_cell(outputs[SMALL], key), key


# minor: every value taken on the day is dated on the row ---------------------------


def test_rows_date_every_value_they_took_on_the_day(outputs) -> None:
    body = outputs[SMALL]
    muji = row_text(body, "muji-76431312")
    assert "本体重量・最大積載量・素材・開閉方法は2026-09-16" in muji, muji
    assert "本体重量約2.9kg・最大積載量（目安）約36L・素材・開閉方法は、現行の商品番号76431312のページの表記です" in muji
    applite = row_text(body, "applite-qj6-68002")
    assert "本体重量・容量の「約」・開閉方法は2026-09-16" in applite, applite


# minor: the summary bullet may not claim a scope the same bullet denies ------------


def test_summary_bullet_claims_no_scope_the_rules_leave_unstated(roots, catalog) -> None:
    undeclared = {rule["carrier"] for rule in rules(catalog) if rule["scope"] == NO_SCOPE}
    items = by_id(roots[SMALL], "carry-on-summary").find(tag="li")
    covering = [li for li in items if undeclared <= set(re.findall("|".join(undeclared), visible_text(li)))]
    assert len(covering) == 1, [visible_text(li)[:40] for li in items]
    heading = visible_text(covering[0].find(tag="strong")[0])
    assert "国内線" not in heading, heading
    for carrier in undeclared:
        assert carrier in heading, (carrier, heading)


# minor: the body history reports the day the ledger reports ------------------------

# The four articles this candidate corrected. 30 and 85 already carry the line;
# 82 and 83 did not, so the same candidate answered the question two ways.
CORRECTED = (UNDER100, LIGHT, ROBOT, STATION)


def test_corrected_articles_show_the_day_in_their_own_history(outputs, ledger) -> None:
    assert len(CORRECTED) == 4
    missing: list[str] = []
    for slug in CORRECTED:
        assert any(e["date"] == DAY for e in ledger[slug]["listing"]["change_log"]), slug
        history = re.search(
            r'<details class="ps-history">(.*?)</details>', outputs[slug], re.S
        )
        assert history, slug
        if '<time datetime="2026-09-16">' not in history.group(1):
            missing.append(slug)
    assert missing == []


def test_authored_history_and_catalog_history_agree(outputs, catalog) -> None:
    """83 carries the list in its source and in the catalog; both have to move.

    30 already has this guard (test_shortlist_history_matches_catalog); 83 did
    not, so its two records could drift apart.
    """
    entries = next(a for a in catalog["articles"] if a["slug"] == LIGHT)["history"]
    history = re.search(
        r'<details class="ps-history">(.*?)</details>', outputs[LIGHT], re.S
    )
    assert history
    lines = re.findall(r"<li>(.*?)</li>", history.group(1), re.S)
    assert len(lines) == len(entries), (len(lines), len(entries))
    for line, entry in zip(lines, entries, strict=True):
        assert f'datetime="{entry["date"]}"' in line, entry["date"]
        assert re.sub(r"<[^>]+>", "", line).endswith(entry["text"]), entry["date"]


# minor: approved layouts this candidate rewrote are on the owner's list -----------


def test_evidence_file_records_this_review_round() -> None:
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "## レビュー 3 巡目の修正 (2026-09-16)" in text
    # The AIRDO decision and its re-fetch.
    assert "新千歳空港国内線旅客ターミナル" in text
    # The five opening values and where each came from.
    assert "ブックオープニングタイプ" in text
    assert "開閉方法／ファスナー" in text
    # Stale lines from the earlier rounds are brought up to date.
    assert "JAL・ANA・スカイマークは 3 辺の数値だけで軸名を書いていないため" not in text
    assert "min-width 50rem" not in text
    assert "スカイマークとソラシドエアの対象便は「公式ページに記載なし」" not in text


def test_evidence_file_states_the_unresolved_items_as_they_stand() -> None:
    text = EVIDENCE.read_text(encoding="utf-8")
    unresolved = text.split("## 未解決", 1)[1]
    assert "スカイマークの規定も車輪の扱いと対象便が未確認" not in unresolved
    assert "スカイマーク・AIRDO・ソラシドエア" in unresolved
    # APPLITE moved out of the opening-unknown list.
    assert "AMERICAN TOURISTER" in unresolved


# the two cross-linked bodies report their own change ------------------------------


def _changed_bodies_against(ref: str) -> set[str]:
    out = subprocess.run(
        (
            "git",
            "diff",
            "--name-only",
            ref,
            "--",
            "changes/wordpress-direct-publish-v1/articles/",
        ),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {Path(p).stem for p in out.splitlines() if p.endswith(".html")}


def test_cross_linked_comparisons_report_their_new_route(ledger) -> None:
    """81 and 84 gained a sentence and a link to 553, so /updates/ says so."""
    for slug in ("carry-on-suitcase-comparison", "front-open-carry-on-suitcase-with-stopper"):
        entries = [e for e in ledger[slug]["listing"]["change_log"] if e["date"] == DAY]
        assert len(entries) == 1, slug
        assert "小型・機内持ち込みスーツケース比較" in entries[0]["summary"], slug
