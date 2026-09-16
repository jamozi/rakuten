"""Guards for the KS integrated-task records (KS-005 baseline metrics, KS-303 evaluation).

These records are internal evidence, not reader-facing text. The checks keep them honest:
every metric names its denominator, source, period and missing-data handling; unmeasured
values are never written as 0; the evaluation lists every published batch in its own §1
table and does not treat the 2026-08-16〜09-12 reference period as an unchanged pre-change
baseline; every published batch has an evidence file of its own; and no numeric multipliers
or bounce rates from the attached PDFs are copied in.

The last check here is the one that keeps the others honest: the batch a record describes
must be the same set of bodies that the ledger and the reader-facing /updates/ page name,
so a record cannot narrow the scope of its own audit by dropping a document.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from tests.purchase_support import ks_w4_batch

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "changes/ks-integrated-20260915"
STATUS = PACKAGE / "status.v1.json"
KS005 = PACKAGE / "evidence/KS-005.md"
KS303 = PACKAGE / "evidence/KS-303.md"
PUBLICATION_20260913 = (
    ROOT / "changes/site-improvements-20260913/publication-result.v1.json"
)

# Numeric PDF-derived phrases only ("1.5〜2倍", "40〜50%", "離脱率 40%"). A sentence saying
# that multipliers or bounce rates are not used must still pass.
PDF_NUMERIC_PHRASE = re.compile(
    r"[0-9.]+\s*〜\s*[0-9.]+\s*(?:倍|[%％])|離脱率\s*[:：]?\s*[0-9]"
)
EMPTY_CELL = re.compile(r"^(?:|-|—|–|n/?a|null|none)$", re.IGNORECASE)
PUBLISHED = "PUBLISHED_AND_READBACK_VERIFIED"
EVIDENCE = PACKAGE / "evidence"
#: Per-batch evidence files. KS-303 is the evaluation record, not a batch record.
BATCH_EVIDENCE = sorted(
    path
    for pattern in ("KS-301*.md", "KS-302*.md")
    for path in EVIDENCE.glob(pattern)
)


def markdown_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """Return (header, rows) for every pipe table in the document."""
    tables: list[tuple[list[str], list[list[str]]]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        separator = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if line.startswith("|") and re.fullmatch(
            r"\|(?:\s*:?-{3,}:?\s*\|)+", separator
        ):
            header = [cell.strip() for cell in line.strip("|").split("|")]
            rows: list[list[str]] = []
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(
                    [
                        cell.strip()
                        for cell in lines[index].strip().strip("|").split("|")
                    ]
                )
                index += 1
            tables.append((header, rows))
            continue
        index += 1
    return tables


def metric_table(text: str) -> tuple[list[str], list[dict[str, str]]]:
    required = (
        "指標",
        "値",
        "分母",
        "取得元",
        "期間",
        "取得日時",
        "同意・除外の影響",
        "不足データの扱い",
    )
    for header, rows in markdown_tables(text):
        if all(column in header for column in required):
            return header, [dict(zip(header, row, strict=True)) for row in rows]
    raise AssertionError(f"KS-005.md has no metric table with columns {required}")


def row_named(rows: list[dict[str, str]], pattern: str) -> dict[str, str]:
    matches = [row for row in rows if re.search(pattern, row["指標"])]
    assert len(matches) == 1, (pattern, [row["指標"] for row in rows])
    return matches[0]


def test_pdf_numeric_phrase_guard_targets_numbers_only() -> None:
    for copied in ("成約率が1.5〜2倍", "離脱率40%", "離脱率 12%", "改善幅40〜50%"):
        assert PDF_NUMERIC_PHRASE.search(copied), copied
    for compliant in (
        "離脱率・倍率は合格基準に使わない",
        "08-16〜09-12",
        "14:30〜14:50 JST",
    ):
        assert not PDF_NUMERIC_PHRASE.search(compliant), compliant


def test_baseline_metrics_define_denominator_source_period_and_missing_data() -> None:
    assert KS005.is_file(), "evidence/KS-005.md is missing"
    text = KS005.read_text(encoding="utf-8")
    header, rows = metric_table(text)

    for row in rows:
        for column in (
            "値",
            "分母",
            "取得元",
            "期間",
            "取得日時",
            "同意・除外の影響",
            "不足データの扱い",
        ):
            assert not EMPTY_CELL.match(row[column]), (row["指標"], column, row[column])

    for pattern in (
        r"GSC.*表示回数",
        r"GSC.*クリック数",
        r"GSC.*CTR",
        r"GSC.*平均掲載順位",
        r"楽天.*クリック.*直近30日",
        r"楽天.*クリック.*今月",
        r"楽天.*売上件数",
        r"楽天.*成果報酬",
        r"楽天.*確定報酬",
        r"GA4.*表示回数",
        r"offer_click",
        r"非提携",
    ):
        row_named(rows, pattern)

    # Rakuten clicks cover every affiliate placement (offer CTA and product-photo links),
    # so the denominator must not claim a per-offer count.
    rakuten_30d = row_named(rows, r"楽天.*クリック.*直近30日")
    assert not re.search(r"52\s*/\s*83|52\s*(?:件の)?\s*offer", rakuten_30d["分母"]), (
        rakuten_30d
    )
    assert "帰属できない" in rakuten_30d["分母"], rakuten_30d

    this_month = row_named(rows, r"楽天.*クリック.*今月")
    assert "取得時点" in this_month["期間"] and "未記録" in this_month["期間"], (
        this_month
    )

    position = row_named(rows, r"GSC.*平均掲載順位")
    assert "GSC 表示値" in position["分母"] + position["取得元"], position

    # offer_click is enabled in production but nothing has been read from GA4: never 0.
    offer_click = row_named(rows, r"offer_click")
    assert not re.match(r"^\s*0(?![0-9.])", offer_click["値"]), offer_click
    assert "未取得" in offer_click["値"], offer_click
    assert '"enabled":true' in offer_click["取得元"] + offer_click["値"], offer_click

    confirmed = row_named(rows, r"楽天.*確定報酬")
    assert "未取得" in confirmed["値"], confirmed

    profit = text[text.index("## 利益") :] if "## 利益" in text else ""
    assert profit, "KS-005.md has no 利益 section"
    for phrase in ("確定報酬", "対象費用", "運営時間", "算定不能"):
        assert phrase in profit, phrase
    assert re.search(r"運営時間[^\n]*(?:含める|含めない|未決定)", profit), profit

    assert "## ファネル" in text, "KS-005.md has no funnel definition"
    funnel = text[text.index("## ファネル") : text.index("## 利益")]
    assert "段階間の率は計算しない" in funnel, funnel
    assert not PDF_NUMERIC_PHRASE.search(text), PDF_NUMERIC_PHRASE.search(text)


def section(text: str, heading: str) -> str:
    """One `## ` section of a markdown record, without the sections after it."""
    start = text.index(heading)
    rest = text[start + len(heading) :]
    end = rest.find("\n## ")
    return rest if end < 0 else rest[:end]


def table_cells(text: str) -> set[str]:
    """Every cell of every pipe table in `text`."""
    return {
        cell
        for _, rows in markdown_tables(text)
        for row in rows
        for cell in row
    }


def published_candidates() -> dict[str, str]:
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    candidates = {
        f"batch {name}": batch["candidate_id"]
        for name, batch in status["batches"].items()
        if batch.get("publication_status") == PUBLISHED
    }
    earlier = json.loads(PUBLICATION_20260913.read_text(encoding="utf-8"))
    for index, batch in enumerate(earlier["batches"]):
        if batch.get("publication_status") == PUBLISHED:
            candidates[f"2026-09-13 batch {index}"] = batch["candidate_id"]
    assert len(candidates) >= 7, candidates
    return candidates


def test_evaluation_record_lists_every_published_batch_and_defers_decision() -> None:
    """§1 says a publish is added to *that table*, so the table is what is checked.

    Searching the whole file passed while the W4b row was deleted, because §5
    still names the candidate in a sentence about confounding -- the record's own
    rule was stronger than the check behind it.
    """
    assert KS303.is_file(), "evidence/KS-303.md is missing"
    text = KS303.read_text(encoding="utf-8")

    published_table = " | ".join(sorted(table_cells(section(text, "\n## 1. 対象の公開"))))
    missing = {
        name: cid[:8]
        for name, cid in published_candidates().items()
        if cid not in published_table
    }
    assert not missing, f"KS-303.md §1 does not list published candidates: {missing}"

    # 2026-08-16〜09-12 is a reference period that already contains production changes.
    assert "参照期間" in text and "変更前ではない" in text
    assert "2026-08-16" in text and "2026-09-12" in text
    in_window = [
        day
        for day in ("2026-09-05", "2026-09-09", "2026-09-10", "2026-09-12")
        if day in text
    ]
    assert len(in_window) >= 3, in_window

    assert "継続観察" in text
    assert re.search(r"比較できる期間[^\n]*2026-\d{2}-\d{2}", text), (
        "no date for a comparable window"
    )
    assert "帰属できない" in text  # sales are not shown as per-article effects
    assert not re.search(
        r"判断[^\n]{0,20}[:：]\s*(?:続行|修正|停止)(?:する)?\s*$", text, re.MULTILINE
    )
    assert re.search(r"^- 判断[:：]\s*\**継続観察", text, re.MULTILINE), "decision line"
    for field in ("オーナーの判断 (続行・修正・停止)", "判断した人", "判断日"):
        assert re.search(
            rf"^- {re.escape(field)}[:：]\s*未記入\s*$", text, re.MULTILINE
        ), field
    assert not PDF_NUMERIC_PHRASE.search(text), PDF_NUMERIC_PHRASE.search(text)


#: One `## ` section of a record, heading included.
SECTION = re.compile(r"^## .*?(?=^## |\Z)", re.M | re.S)
#: The sections that describe a batch: where its candidate is prepared, approved,
#: inspected or published. 「## 復元」「## 受入条件」「## 途中の失敗と対処」 and the
#: Before/After notes are not, so a candidate named only there does not count.
BATCH_HEADING = re.compile(r"候補|承認|KS-30[12]")


def evidence_sections() -> list[tuple[str, str, str]]:
    """(file, heading, section text) for the KS-301 / KS-302 records."""
    found = []
    for path in BATCH_EVIDENCE:
        for match in SECTION.finditer(path.read_text(encoding="utf-8")):
            text = match.group(0)
            found.append((path.name, text.splitlines()[0], text))
    return found


def test_every_published_batch_has_an_evidence_file() -> None:
    """A batch that reached production owes a record of its own, not just a table row.

    KS-303 is the evaluation record and names every candidate by design, so it
    does not count here: the check is that each publish also has a KS-301 / KS-302
    evidence file naming the candidate that carried it.

    The name has to be the full 64-hex id, on a line that names it as the
    candidate, in the section that prepares, approves, inspects or publishes it.
    An 8-character prefix anywhere in the file was not enough: deleting the full
    id from W4b's 候補 line left this rule green, because 「作り直した候補
    `7cea2e0a…` でも同じ」 -- a parenthetical about screenshot counts -- still
    carried the prefix. It is the same looseness the KS-303 §1 rule above had to
    drop, for the same reason.
    """
    assert BATCH_EVIDENCE, "no KS-301 / KS-302 evidence files"
    sections = evidence_sections()
    assert sections, "no `## ` sections in the KS-301 / KS-302 evidence"
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    named: dict[str, list[str]] = {}
    missing = {}
    for name, batch in status["batches"].items():
        if batch.get("publication_status") != PUBLISHED:
            continue
        candidate = batch["candidate_id"]
        found = [
            f"{file} {heading}"
            for file, heading, text in sections
            if BATCH_HEADING.search(heading)
            and any(
                candidate in line and "candidate" in line
                for line in text.splitlines()
            )
        ]
        if found:
            named[name] = found
        else:
            missing[name] = candidate[:8]
    assert not missing, (
        "no KS-301 / KS-302 evidence section names these publishes by their full "
        f"candidate id: {missing}"
    )
    assert len(named) >= 10, sorted(named)


def test_the_batch_records_agree_with_the_ledger_and_the_updates_page() -> None:
    """What a batch says it published must be what the site says changed that day.

    The W4 rules read their scope out of ``status.v1.json``; dropping a document
    there would silently narrow every one of them instead of failing. The ledger's
    2026-09-16 cards and the generated /updates/ page are two observations that do
    not come from that record, so requiring all three to agree in both directions
    is what gives the record a scope it cannot set for itself.
    """
    rows = ks_w4_batch.ledger_rows()
    # A published document is a page this repository has: a row of the ledger the
    # publisher reads, with a body on disk. Without this, a slug that never
    # existed could be added to the record and simply be filtered back out.
    unknown = sorted(
        doc
        for doc in ks_w4_batch.batch_documents()
        if doc not in rows
        or not (ks_w4_batch.ARTICLES / f"{doc}.html").is_file()
    )
    assert unknown == [], unknown

    documents = ks_w4_batch.batch_article_documents()
    cards = set(ks_w4_batch.carded())
    page = ks_w4_batch.updates_page_slugs()
    assert len(documents) == 13, sorted(documents)
    assert documents == cards, sorted(documents ^ cards)
    assert documents == page, sorted(documents ^ page)
    # /updates/ itself is republished by each candidate that writes a card.
    for name in ks_w4_batch.BATCH_NAMES:
        assert "updates" in ks_w4_batch.batch_documents(name), name


def git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(("git", *args), cwd=ROOT, capture_output=True)


def test_the_before_record_is_the_bodies_at_the_pinned_main_commit() -> None:
    """The "before" every card rule is measured against comes from outside itself.

    ``tests/purchase_support/ks_w4_published_before.json`` is written by the same
    commit as the cards it validates, so until this rule nothing constrained it.
    Measured on this tree: appending 「背面は5cm必要」 to 551's ``text`` and to its
    AQUA ADW-L40B row (``body_sha256`` untouched, because no check recomputes it
    from those fields) and prepending a 訂正 card quoting that phrase -- a state
    the published body never showed -- left the eight record and batch files at
    `146 passed`. The digest is not enough on its own either: the card rules read
    ``text``/``rows``/``sections``/``links``/``openings``, none of which a digest
    covers, so the whole record is re-derived here.

    The record is re-derived from ``ks_w4_batch.PRE_PUBLISH_COMMIT`` (batch G,
    PR #292): a commit of *main*, so it is in every clone that has history, and
    it changed no article body, so it holds the bodies this batch published over.

    A missing object fails; it does not skip. The job that runs pytest checks
    this repository out with ``fetch-depth: 0`` -- ``.github/workflows/ci.yml``,
    job ``tests``, and so do ``plan``, ``static``, ``php``, ``contracts``,
    ``data``, ``storage``, ``secrets`` and ``final``; only ``lock``, which runs
    no test, takes the default shallow checkout. So the commit is always
    reachable where this rule runs, and a skip would let the one thing that
    binds the record to an observation outside itself disappear without a word.
    """
    record = ks_w4_batch.before_record()
    commit = ks_w4_batch.PRE_PUBLISH_COMMIT
    assert record["captured_from"]["commit"] == commit, record["captured_from"]

    present = git("cat-file", "-e", commit + "^{commit}")
    assert present.returncode == 0, (
        f"{commit} is not in this clone, so the before-record cannot be checked "
        "against the bodies it claims to hold. CI checks out with fetch-depth: 0 "
        "(.github/workflows/ci.yml), so fetch the full history rather than "
        "letting this rule pass unmeasured."
    )

    bodies = record["bodies"]
    documents = ks_w4_batch.batch_article_documents()
    assert set(bodies) == documents, sorted(set(bodies) ^ documents)

    published_over = {}
    for slug in sorted(bodies):
        blob = git("show", f"{commit}:{ks_w4_batch.ARTICLE_PREFIX}{slug}.html")
        assert blob.returncode == 0, (slug, blob.stderr.decode("utf-8", "replace"))
        published_over[slug] = hashlib.sha256(blob.stdout).hexdigest()
    assert {slug: body["body_sha256"] for slug, body in bodies.items()} == (
        published_over
    )

    # Every field the card rules actually read, which no digest can cover.
    rebuilt = ks_w4_batch.capture(commit)["bodies"]
    edited = sorted(slug for slug in bodies if bodies[slug] != rebuilt[slug])
    assert edited == [], edited
