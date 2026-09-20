"""W4b guards: robot dimensions and space table (corrections 1 and 12, KS-136) and two records.

The article bodies are compiled in memory from ``changes/reader-purchase-support-v1``.
Every value checked here comes from the re-fetched official sources recorded for W4
(N285060 store page, OG515jaJP.pdf, OGRoombaMinijaJP.pdf, the K11+ Pro and K10+ Pro
Combo Japanese manuals and product pages). The records are internal evidence:
``evidence/KS-P2-deferrals.md`` and the KS-031a content-treatment ledger.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from raos.application.editorial.reader_html import Element, fragment
from tests.purchase_support import phone_table_frames
from scripts import build_reader_purchase_support_v1 as builder

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "changes/ks-integrated-20260915"
P2_RECORD = PACKAGE / "evidence/KS-P2-deferrals.md"
TREATMENT_RECORD = PACKAGE / "evidence/KS-031-content-treatment.v1.json"
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
SHORTLIST = "compact-robot-vacuum-shortlist"
HEAD_TO_HEAD = "roomba-mini-vs-switchbot-k11-pro"

MINI = "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY"
K11 = "PRD-SWITCHBOT-K11-PRO"
K10 = "PRD-SWITCHBOT-K10-PRO-COMBO"
PLUS_515 = "PRD-IROBOT-ROOMBA-PLUS-515-COMBO"
MINI_MANUAL = "https://prod-help-content.care.irobotapi.com/files/2026/OwnersGuides/Mini/OGRoombaMinijaJP.pdf"
PLUS_515_MANUAL = "https://prod-help-content.care.irobotapi.com/files/2026/OwnersGuides/515/OG515jaJP.pdf"
K11_MANUAL = "https://cdn.shopify.com/s/files/1/0522/2458/9999/files/K11_Pro-SMS-JP-2604-Q.pdf?v=1784279900"
K10_MANUAL = "https://cdn.shopify.com/s/files/1/0522/2458/9999/files/K10_Pro_Combo-SMS-JP-24.pdf"

SCROLL_CLAIM = re.compile(r"スクロール|左右に動かせ")
SKIPPED_TAGS = frozenset({"script", "style", "template", "code", "pre"})


@pytest.fixture(scope="module")
def catalog() -> dict[str, Any]:
    return json.loads(builder.CATALOG_INPUT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def outputs() -> dict[str, str]:
    return {
        path.stem: body
        for path, body in builder.build().items()
        if path.suffix == ".html"
    }


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


def hrefs(node: Element) -> list[str]:
    return [a.attrs.get("href") or "" for a in node.find(tag="a")]


def product(catalog: dict[str, Any], product_id: str) -> dict[str, Any]:
    return next(p for p in catalog["products"] if p["product_id"] == product_id)


def fact(entry: dict[str, Any], label_prefix: str) -> dict[str, Any]:
    matches = [f for f in entry["facts"] if f["label"].startswith(label_prefix)]
    assert len(matches) == 1, (entry["product_id"], label_prefix)
    return matches[0]


def article(catalog: dict[str, Any], slug: str) -> dict[str, Any]:
    return next(a for a in catalog["articles"] if a["slug"] == slug)


# --- Correction 1: N285060 publishes 奥行き first ("30.3 (奥行き) ×29.8 (幅)").


def test_roomba_plus_515_dimensions_follow_the_official_axis_labels(catalog, outputs) -> None:
    entry = product(catalog, PLUS_515)
    body = fact(entry, "本体寸法")
    station = fact(entry, "ステーション寸法")
    assert body["text"] == "幅29.8×奥行30.3×高さ8.4cm"
    assert station["text"] == "幅33.0×奥行34.0×高さ48.5cm"
    for record in (body, station):
        assert "30.3 (奥行き) ×29.8 (幅) ×8.4 (高さ)" in record["locator"]
        assert "34.0 (奥行き) ×33.0 (幅) ×48.5 (高さ)" in record["locator"]
    assert "ステーション（幅33.0×奥行34.0×高さ48.5cm）を置ける人" in entry["fit"]
    serialized = json.dumps(entry, ensure_ascii=False)
    template = (builder.CATALOG_INPUT_PATH.parent / "articles" / f"{SHORTLIST}.html").read_text(
        encoding="utf-8"
    )
    text = visible_text(fragment(outputs[SHORTLIST]))
    for swapped in ("幅30.3×奥行29.8", "幅34.0×奥行33.0"):
        assert swapped not in serialized
        assert swapped not in template
        assert swapped not in text
    # Conclusion card facts and the specification row both show the corrected order.
    assert text.count("幅29.8×奥行30.3×高さ8.4cm") >= 2
    assert text.count("幅33.0×奥行34.0×高さ48.5cm") >= 3


# --- Correction 12: the K11+ Pro product page states 高さ約25cm and 底面240×180mm.


def test_k11_station_states_published_height_and_footprint_but_not_width_depth(
    catalog, outputs
) -> None:
    station = fact(product(catalog, K11), "ステーション寸法")
    assert station["state"] == "UNKNOWN"
    assert station["text"].startswith("240×180×250mm")
    assert "底面240×180mm" in station["text"] and "高さ約25cm" in station["text"]
    assert "底面の幅・奥行の対応は未確認" in station["text"]
    assert "高さも約25cm" in station["locator"]
    assert "ステーション底面わずか240×180mm" in station["locator"]
    for slug in (SHORTLIST, HEAD_TO_HEAD):
        text = visible_text(fragment(outputs[slug]))
        assert "高さ約25cm" in text, slug
        for stale in ("幅・奥行・高さとの対応は未確認", "軸順が未確認のため", "軸の対応が未確認"):
            assert stale not in text, (slug, stale)


STATION_LABEL = "ステーション寸法（幅×奥行×高さ。K11+ Proは底面の幅・奥行が未確認）"
THEME_CSS = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/theme.css"
)


def test_k11_station_label_names_only_the_unconfirmed_footprint_axes(catalog, outputs) -> None:
    serialized = json.dumps(catalog, ensure_ascii=False)
    assert "K11+ Proは軸順未確認" not in serialized
    assert STATION_LABEL in serialized
    assert fact(product(catalog, K11), "ステーション寸法")["label"] == STATION_LABEL
    assert STATION_LABEL in outputs[HEAD_TO_HEAD]
    for slug in (SHORTLIST, HEAD_TO_HEAD):
        template = (builder.CATALOG_INPUT_PATH.parent / "articles" / f"{slug}.html").read_text(
            encoding="utf-8"
        )
        # Unused template copies must not carry the narrowed claim back on regeneration.
        assert "軸順" not in template, slug
        assert "24×18×25cm" not in template, slug
    head = (builder.CATALOG_INPUT_PATH.parent / "articles" / f"{HEAD_TO_HEAD}.html").read_text(
        encoding="utf-8"
    )
    assert head.count("底面240×180mm・高さ約25cm") >= 4


def test_robot_space_table_keeps_the_model_column_in_view() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")
    # The phone block below re-declares this selector to narrow the column, so look at
    # the unconditional rule: the column must be sticky at every width, not only there.
    css = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)
    rule = re.search(
        r'\.ps-article\[data-raos-article-id="compact-robot-vacuum-shortlist"\] '
        r"table\.robot-space-table :is\(thead th:first-child, tbody th\) \{([^}]*)\}",
        css,
    )
    assert rule, "sticky model column"
    compact = rule.group(1).replace(" ", "")
    assert "position:sticky" in compact and "left:0" in compact and "background:" in compact


# --- KS-136: body passage, return space and access are compared per model.


def space_rows(root: Element) -> tuple[Element, dict[str, list[Element]]]:
    sections = by_id(root, "robot-space")
    assert len(sections) == 1
    section = sections[0]
    assert section.tag == "section"
    tables = section.find(tag="table")
    assert len(tables) == 1
    rows = tables[0].find(tag="tbody")[0].find(tag="tr")
    return section, {
        str(row.attrs.get("data-robot-space-product")): row.find(tag="td") for row in rows
    }


def test_robot_space_table_follows_specs_and_keeps_each_model_to_its_own_sources(
    catalog, outputs
) -> None:
    html = outputs[SHORTLIST]
    assert html.index('id="ps-specs"') < html.index('id="robot-space"') < html.index(
        'id="ps-decision-steps"'
    )
    root = fragment(html)
    section, cells = space_rows(root)
    parent = section.parent
    while parent is not None:
        assert parent.attrs.get("id") != "ps-specs"
        parent = parent.parent
    table = section.find(tag="table")[0]
    wrapper = table.parent
    assert wrapper is not None and wrapper.has("ps-table-scroll")
    assert wrapper.attrs.get("role") == "region" and wrapper.attrs.get("aria-label")
    assert len(table.find(tag="thead")[0].find(tag="th")) == 4
    assert list(cells) == article(catalog, SHORTLIST)["product_ids"]
    assert all(len(tds) == 3 for tds in cells.values())
    text = {pid: [visible_text(td) for td in tds] for pid, tds in cells.items()}

    # Printed manual text for the SwitchBot stations (values differ by model).
    assert "両側に0.5m、前方および上方に1.5m" in text[K11][1]
    assert K11_MANUAL in hrefs(cells[K11][1])
    assert "両側に0.5m、前方および上方に1m" in text[K10][1]
    assert "コードレス掃除機を集塵ステーションに設置した高さ：1230mm" in text[K10][1]
    assert K10_MANUAL in hrefs(cells[K10][1])

    # iRobot figures carry no direction words: the direction is read from the drawing.
    assert "図から読み取った向き" in text[PLUS_515][1]
    assert "1.22m超" in text[PLUS_515][1] and "0.46m超" in text[PLUS_515][1]
    assert "階段から1.22メートル以上" in text[PLUS_515][1]
    assert PLUS_515_MANUAL in hrefs(cells[PLUS_515][1])
    assert "図から読み取った向き" in text[MINI][1]
    assert "0.46m" in text[MINI][1] and "超" not in text[MINI][1]
    assert MINI_MANUAL in hrefs(cells[MINI][1])

    for pid, columns in text.items():
        joined = "".join(columns)
        if pid != K11:
            assert "1.5m" not in joined, pid
        if pid != K10:
            assert "1230mm" not in joined, pid
            assert not re.search(r"(?<![0-9.])1m", joined), pid
        if pid not in {MINI, PLUS_515}:
            assert "1.22m" not in joined and "0.46m" not in joined, pid
        if pid not in {K11, K10}:
            assert "0.5m" not in joined, pid
        for td in cells[pid]:
            if re.search(r"[0-9]", visible_text(td)):
                assert any(h.startswith("https://") for h in hrefs(td)), (pid, visible_text(td))

    section_text = visible_text(section)
    assert "本体寸法だけで、通過・清掃・帰還を保証するものではありません。" in section_text
    assert "公式の日本語資料で確認できていません" in section_text
    for unsourced in ("手を入れる", "これより高い隙間が必要", "高さに加えて余裕", "確認後に掲載", "立てた状態"):
        assert unsourced not in section_text
    assert not SCROLL_CLAIM.search(section_text)
    toc = root.find(cls="ps-toc")[0]
    assert "#robot-space" in hrefs(toc)


def test_decision_step_two_matches_catalog_and_points_to_the_space_table(catalog, outputs) -> None:
    steps = article(catalog, SHORTLIST)["decision_steps"]["steps"]
    root = fragment(outputs[SHORTLIST])
    items = by_id(root, "ps-decision-steps")[0].find(tag="li")
    assert [visible_text(li).strip() for li in items] == steps
    assert "上の表" in steps[1] and "2機種比較" in steps[1]


def test_shortlist_history_matches_catalog(catalog, outputs) -> None:
    """Regression: the authored history list and the catalog history stay identical."""
    history = article(catalog, SHORTLIST)["history"]
    root = fragment(outputs[SHORTLIST])
    items = root.find(cls="ps-history")[0].find(tag="li")
    rendered = [(li.find(tag="time")[0].attrs.get("datetime"), visible_text(li)) for li in items]
    assert [date for date, _ in rendered] == [h["date"] for h in history]
    for (_, line), entry in zip(rendered, history, strict=True):
        assert line.endswith(entry["text"])


# --- KS-024 / 202 / 203 / 204 / 205 / 206: deferral record.


def markdown_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    tables: list[tuple[list[str], list[list[str]]]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        separator = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if line.startswith("|") and re.fullmatch(r"\|(?:\s*:?-{3,}:?\s*\|)+", separator):
            header = [cell.strip() for cell in line.strip("|").split("|")]
            rows: list[list[str]] = []
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            tables.append((header, rows))
            continue
        index += 1
    return tables


def test_p2_deferral_record_names_reason_and_restart_condition_for_each_task() -> None:
    assert P2_RECORD.is_file(), "evidence/KS-P2-deferrals.md is missing"
    text = P2_RECORD.read_text(encoding="utf-8")
    tables = [
        (header, rows)
        for header, rows in markdown_tables(text)
        if header and header[0] == "タスク" and len(header) == 4
    ]
    assert len(tables) == 1
    header, rows = tables[0]
    assert header[1] == "判断" and header[2].startswith("理由") and header[3].startswith("再開の条件")
    assert [re.match(r"KS-[0-9]{3}", row[0]).group(0) for row in rows] == [
        "KS-024",
        "KS-202",
        "KS-203",
        "KS-204",
        "KS-205",
        "KS-206",
    ]
    for row in rows:
        assert len(row) == 4 and all(cell for cell in row), row
        assert row[1] in {"保留", "不採用 (現時点)"}, row
    ks203 = rows[2]
    assert "2026-10-14" in ks203[3]
    assert "KS-031-content-treatment.v1.json" in ks203[3]
    assert "新規の ASP 申請・契約はしない" in text


# --- KS-031a: content-treatment ledger (keep / update / merge / new).

TREATMENTS = frozenset({"keep", "update", "merge_candidate", "new_candidate"})
APPROVAL_STATES = frozenset({"owner_review_pending", "approved", "changes_requested", "rejected"})
REVIEW_ON = "2026-10-14"
NEW_CANDIDATE_FIELDS = ("answer", "evidence", "figure", "applicability", "routes", "maintenance")


def published_posts(ledger: dict[str, Any]) -> dict[str, int]:
    return {
        row["article_key"]: row["post_id"]
        for row in ledger["articles"]
        if row.get("post_type") == "post" and (row.get("listing") or {}).get("state") == "published"
    }


def validate_content_treatment(record: dict[str, Any], ledger: dict[str, Any]) -> None:
    """Raise ValueError(code) when the ledger breaks a KS-031a rule."""
    if record.get("schema") != "RAOSContentTreatmentV1":
        raise ValueError("CONTENT_TREATMENT_SCHEMA")
    posts = published_posts(ledger)
    entries = record["articles"]
    keys = [entry["article_key"] for entry in entries]
    if len(keys) != len(set(keys)) or set(keys) != set(posts):
        raise ValueError("CONTENT_TREATMENT_LEDGER_MISMATCH")
    checks = {check["id"]: check for check in record["consolidation_checks"]}
    for check in checks.values():
        if not set(check["members"]) <= set(posts.values()):
            raise ValueError("CONTENT_TREATMENT_CHECK_MEMBERS")
        if any(not str(check.get(key) or "").strip() for key in ("internal_links", "redirect", "search")):
            raise ValueError("CONTENT_TREATMENT_MERGE_CHECK_REQUIRED")
        if sum(1 for option in check["options"] if option.get("chosen")) != 1:
            raise ValueError("CONTENT_TREATMENT_CHECK_OPTION")
        if check["reevaluate_on_or_after"] < REVIEW_ON:
            raise ValueError("CONTENT_TREATMENT_REVIEW_DATE")
    for entry in entries:
        if entry["post_id"] != posts[entry["article_key"]]:
            raise ValueError("CONTENT_TREATMENT_POST_ID_MISMATCH")
        if entry["treatment"] not in TREATMENTS or entry["approval"]["state"] not in APPROVAL_STATES:
            raise ValueError("CONTENT_TREATMENT_ENUM")
        if not str(entry.get("reason") or "").strip():
            raise ValueError("CONTENT_TREATMENT_REASON_REQUIRED")
        if entry["treatment"] == "update" and not entry.get("actions"):
            raise ValueError("CONTENT_TREATMENT_ACTIONS_REQUIRED")
        if entry["treatment"] == "merge_candidate" and entry.get("consolidation_check_id") not in checks:
            raise ValueError("CONTENT_TREATMENT_MERGE_CHECK_REQUIRED")
        reevaluate = entry.get("reevaluate")
        if reevaluate is not None and reevaluate["on_or_after"] < REVIEW_ON:
            raise ValueError("CONTENT_TREATMENT_REVIEW_DATE")
    candidates = record["new_candidates"]
    if len(candidates) > 3 or any(
        not str(candidate.get(field) or "").strip()
        for candidate in candidates
        for field in NEW_CANDIDATE_FIELDS
    ):
        raise ValueError("CONTENT_TREATMENT_NEW_CANDIDATES")
    trial = record["model_diff_trial"]
    if trial.get("task") != "KS-203":
        raise ValueError("CONTENT_TREATMENT_TRIAL")
    if trial.get("state") == "deferred":
        conditions = trial.get("start_conditions") or []
        if [c.get("id") for c in conditions] != [f"C{n}" for n in range(1, 7)] or any(
            not str(c.get("text") or "").strip() for c in conditions
        ):
            raise ValueError("CONTENT_TREATMENT_TRIAL_CONDITIONS")
        if str(trial.get("earliest_review_on") or "") < REVIEW_ON:
            raise ValueError("CONTENT_TREATMENT_REVIEW_DATE")


def test_content_treatment_record_covers_the_ledger_with_the_planned_judgements() -> None:
    assert TREATMENT_RECORD.is_file(), "evidence/KS-031-content-treatment.v1.json is missing"
    record = json.loads(TREATMENT_RECORD.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    validate_content_treatment(record, ledger)
    by_treatment: dict[str, set[int]] = {}
    for entry in record["articles"]:
        by_treatment.setdefault(entry["treatment"], set()).add(entry["post_id"])
        assert entry["approval"]["state"] == "owner_review_pending"
    assert by_treatment.get("update") == {553, 549, 41, 86}
    # next30 W1 added 750-752 and W2 added 766-768, all kept as their own questions.
    assert len(by_treatment.get("keep", set())) == 22
    assert "merge_candidate" not in by_treatment and "new_candidate" not in by_treatment
    assert record["new_candidates"] == []
    assert record["model_diff_trial"]["state"] == "deferred"
    assert record["model_diff_trial"]["earliest_review_on"] == REVIEW_ON
    countertop = next(e for e in record["articles"] if e["post_id"] == 41)
    assert any("タンク式食洗機4モデルの給水と設置を比較" in action for action in countertop["actions"])
    serialized = json.dumps(record, ensure_ascii=False)
    # WordPress core keeps old-slug redirects, which cannot merge two articles.
    assert "old-slug" in serialized
    assert "slug間の301の仕組みが無い" not in serialized


def minimal_record(ledger: dict[str, Any]) -> dict[str, Any]:
    posts = published_posts(ledger)
    return {
        "schema": "RAOSContentTreatmentV1",
        "articles": [
            {
                "article_key": key,
                "post_id": post_id,
                "treatment": "keep",
                "reason": "問いが独立している",
                "actions": [],
                "approval": {"state": "owner_review_pending", "approved_at": None},
            }
            for key, post_id in posts.items()
        ],
        "consolidation_checks": [
            {
                "id": "group",
                "members": list(posts.values())[:2],
                "internal_links": "被リンクを数えた",
                "redirect": "統合用の転送なし",
                "search": "ページ行なし",
                "options": [{"id": "C", "chosen": True}],
                "reevaluate_on_or_after": REVIEW_ON,
            }
        ],
        "new_candidates": [],
        "model_diff_trial": {
            "task": "KS-203",
            "state": "deferred",
            "earliest_review_on": REVIEW_ON,
            "start_conditions": [{"id": f"C{n}", "text": "条件"} for n in range(1, 7)],
        },
    }


def _drop_article(record: dict[str, Any]) -> None:
    record["articles"].pop()


def _unknown_treatment(record: dict[str, Any]) -> None:
    record["articles"][0]["treatment"] = "noindex"


def _empty_reason(record: dict[str, Any]) -> None:
    record["articles"][0]["reason"] = " "


def _update_without_actions(record: dict[str, Any]) -> None:
    record["articles"][0]["treatment"] = "update"


def _merge_without_check(record: dict[str, Any]) -> None:
    record["articles"][0]["treatment"] = "merge_candidate"


def _check_without_redirect(record: dict[str, Any]) -> None:
    record["consolidation_checks"][0]["redirect"] = ""


def _four_new_candidates(record: dict[str, Any]) -> None:
    record["new_candidates"] = [{field: "x" for field in NEW_CANDIDATE_FIELDS}] * 4


def _deferred_without_conditions(record: dict[str, Any]) -> None:
    record["model_diff_trial"]["start_conditions"] = record["model_diff_trial"]["start_conditions"][:5]


def _early_review(record: dict[str, Any]) -> None:
    record["model_diff_trial"]["earliest_review_on"] = "2026-09-30"


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (_drop_article, "CONTENT_TREATMENT_LEDGER_MISMATCH"),
        (_unknown_treatment, "CONTENT_TREATMENT_ENUM"),
        (_empty_reason, "CONTENT_TREATMENT_REASON_REQUIRED"),
        (_update_without_actions, "CONTENT_TREATMENT_ACTIONS_REQUIRED"),
        (_merge_without_check, "CONTENT_TREATMENT_MERGE_CHECK_REQUIRED"),
        (_check_without_redirect, "CONTENT_TREATMENT_MERGE_CHECK_REQUIRED"),
        (_four_new_candidates, "CONTENT_TREATMENT_NEW_CANDIDATES"),
        (_deferred_without_conditions, "CONTENT_TREATMENT_TRIAL_CONDITIONS"),
        (_early_review, "CONTENT_TREATMENT_REVIEW_DATE"),
    ],
)
def test_content_treatment_validator_rejects_broken_records(mutate, code) -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    record = minimal_record(ledger)
    validate_content_treatment(copy.deepcopy(record), ledger)
    mutate(record)
    with pytest.raises(ValueError, match=code):
        validate_content_treatment(record, ledger)


def test_robot_space_table_frames_a_whole_data_cell_on_a_phone() -> None:
    """At phone widths the sticky model column has to leave room for one data column.

    The frame is measured, not assumed: see
    ``tests/purchase_support/phone_table_frames.py``. An earlier round of this
    work computed the 320px frame as 302px, which left out
    ``.raos-article-shell { padding-inline: 1rem }``; the real frame is 286px, and
    at 302px the rule below passes while no data column is actually framed.
    """
    css = THEME_CSS.read_text(encoding="utf-8")
    phone = phone_table_frames.phone_block(css)
    width = re.search(r"table\.robot-space-table\{min-width:(\d+(?:\.\d+)?)rem!important", phone)
    first = re.search(
        r"table\.robot-space-table:is\(theadth:first-child,tbodyth\)\{width:(\d+(?:\.\d+)?)rem!important",
        phone,
    )
    # table-layout:fixed is what makes the declared first-column width bind; without
    # it the auto layout sizes the column to its content and the rule does nothing.
    assert width and first, phone[-800:]
    assert "table-layout:fixed!important" in phone
    total, head = float(width.group(1)) * 16, float(first.group(1)) * 16
    columns = phone_table_frames.data_columns(SHORTLIST, "robot-space-table")
    assert columns == 3, columns
    for viewport, frame in sorted(phone_table_frames.ARTICLE_SCROLL_FRAME.items()):
        assert (total - head) / columns <= frame - head, (viewport, frame, total, head)
