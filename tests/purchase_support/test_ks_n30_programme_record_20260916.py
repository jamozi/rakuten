"""Guards for the next30 programme record (``changes/next30-20260916``).

The record is internal evidence, not reader-facing text: it holds the intake
package the programme came from, the owner decisions of 2026-09-16, the
verified product catalog and the eight-wave plan. The checks keep it honest —
all three files stay present, every article of the 30-article intake carries a
verdict, and an article the programme dropped never reappears in the wave plan
(neither in the data nor in the prose). The widened category labels and the
still-absent ``laundry`` category are read back from the live source of truth so
the record cannot drift away from what the site actually says.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "changes/next30-20260916"
README = PACKAGE / "README.md"
DECISIONS = PACKAGE / "decisions.v1.json"
CATALOG = PACKAGE / "products.candidate.v1.json"
ENTRY_PAGES = ROOT / "changes/site-improvements-20260913/entry-pages.v1.json"

INTAKE_IDS = tuple(f"A{number:02d}" for number in range(1, 31))
VERDICTS = ("KEEP", "RESHAPE", "DROP")
DROP_SOURCES = ("owner", "feasibility")


def decisions() -> dict:
    return json.loads(DECISIONS.read_text(encoding="utf-8"))


def article_rows() -> list[dict]:
    return decisions()["articles"]


def dropped_ids() -> list[str]:
    return [row["article_id"] for row in article_rows() if row["verdict"] == "DROP"]


def mentions(text: str, article_id: str) -> bool:
    """True when the document names this article id (A06 must not match A061)."""
    return bool(re.search(rf"(?<![A-Za-z0-9]){article_id}(?![0-9])", text))


def readme_section(title: str) -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index(f"## {title}")
    rest = text.index("\n## ", start + 1)
    return text[start:rest]


def test_the_record_files_exist() -> None:
    for path in (README, DECISIONS, CATALOG):
        assert path.is_file(), f"{path} is missing"
        assert path.stat().st_size > 0, f"{path} is empty"

    document = decisions()
    assert document["schema"] == "RAOSNext30DecisionsV1", document["schema"]
    assert document["recorded_on"] == "2026-09-16", document["recorded_on"]

    products = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert len(products) == 17, len(products)
    facts = sum(len(product["facts"]) for product in products)
    assert facts == 284, facts
    recorded = document["product_catalog"]
    assert recorded["products"] == 17 and recorded["facts"] == 284, recorded
    assert recorded["wired_into_live_catalog"] is False, recorded

    # The copy is a candidate: nothing has imported it into the served catalog yet.
    text = README.read_text(encoding="utf-8")
    assert "products.candidate.v1.json" in text
    assert "purchase-support.v1.json" in text, (
        "the README does not name the live catalog"
    )
    assert "取り込んでいません" in text, (
        "the README does not say the catalog is unwired"
    )
    live = (
        ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
    ).read_text(encoding="utf-8")
    for product_id in (product["product_id"] for product in products):
        assert product_id not in live, f"{product_id} is already in the live catalog"


def test_the_decisions_file_gives_every_intake_article_a_verdict() -> None:
    rows = article_rows()
    ids = [row["article_id"] for row in rows]
    assert ids == sorted(ids), "articles are not in id order"
    assert set(ids) == set(INTAKE_IDS), set(INTAKE_IDS).symmetric_difference(ids)
    assert len(ids) == len(set(ids)) == 30, ids

    for row in rows:
        assert row["verdict"] in VERDICTS, row
        for field in ("slug", "title", "cluster"):
            assert row[field], (row["article_id"], field)
        if row["verdict"] == "DROP":
            assert row["drop_source"] in DROP_SOURCES, row
            assert row["note"], row["article_id"]
            assert row.get("wave") is None, row
        else:
            assert row["wave"], row["article_id"]
            assert row["category"] in ("kitchen", "cleaning", "laundry"), row
            assert row["role"] in ("comparison", "guide"), row

    verdicts = {
        verdict: sum(1 for row in rows if row["verdict"] == verdict)
        for verdict in VERDICTS
    }
    assert verdicts == {"KEEP": 1, "RESHAPE": 24, "DROP": 5}, verdicts
    sources = [row["drop_source"] for row in rows if row["verdict"] == "DROP"]
    assert sources.count("owner") == 4 and sources.count("feasibility") == 1, sources

    text = README.read_text(encoding="utf-8")
    for article_id in dropped_ids():
        assert mentions(text, article_id), (
            f"README does not explain dropped {article_id}"
        )


def test_no_dropped_article_appears_in_the_wave_plan() -> None:
    document = decisions()
    dropped = set(dropped_ids())
    assert dropped == {"A06", "A16", "A18", "A23", "A29"}, dropped

    planned: list[str] = []
    for wave in document["waves"]:
        planned.extend(wave["articles"])
    assert len(planned) == len(set(planned)), planned
    assert not dropped.intersection(planned), dropped.intersection(planned)

    survivors = {
        row["article_id"] for row in article_rows() if row["verdict"] != "DROP"
    }
    assert set(planned) == survivors, survivors.symmetric_difference(planned)
    assert len(planned) == 25, len(planned)

    waves = {wave["wave"] for wave in document["waves"]}
    assert waves == {"W0", "W1", "W2", "W3", "W4", "W5", "W6", "W7"}, waves
    for wave in document["waves"]:
        for article_id in wave["articles"]:
            row = next(r for r in article_rows() if r["article_id"] == article_id)
            assert row["wave"] == wave["wave"], (article_id, row["wave"])

    section = readme_section("波計画")
    for article_id in dropped:
        assert not mentions(section, article_id), f"{article_id} is in the wave plan"


def test_the_recorded_category_decision_matches_the_live_labels() -> None:
    document = decisions()
    entry_pages = json.loads(ENTRY_PAGES.read_text(encoding="utf-8"))
    categories = entry_pages["categories"]

    widened = document["owner_decisions"]["categories_widened"]
    for key, change in widened["renamed"].items():
        assert key in categories, key
        assert categories[key]["name"] == change["after"], (key, categories[key])
        assert change["after"] != change["before"], change

    # The key never moves; only the label the reader sees does.
    assert set(widened["renamed"]) == {"kitchen", "cleaning"}, widened

    laundry = document["owner_decisions"]["laundry_category"]
    assert laundry["wave_zero_touches_it"] is False, laundry
    assert laundry["wordpress_post_id"] == 701, laundry
    assert laundry["delegated"] is False, laundry
    assert "laundry" not in categories, "laundry is already a category"
    assert "laundry" not in entry_pages["pages"], "laundry already has an entry page"
