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
import subprocess
from pathlib import Path

from raos.application.editorial.reader_html import fragment
from scripts import build_site_editorial_pages as projection

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
    # The candidate is imported one wave at a time (PURCHASE_UNUSED_PRODUCT keeps a
    # product out until the article that references it is written), so the record
    # names the products already served and has to agree with the live catalog in
    # both directions: nothing wired that the record omits, nothing recorded that
    # is not there.
    wired = recorded["wired_into_live_catalog"]
    candidates = [product["product_id"] for product in products]
    assert isinstance(wired, list) and len(wired) == len(set(wired)), recorded
    assert set(wired) <= set(candidates), recorded
    live = json.loads(
        (ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json").read_text(
            encoding="utf-8"
        )
    )
    served = {product["product_id"] for product in live["products"]}
    for product_id in candidates:
        assert (product_id in served) == (product_id in wired), product_id

    text = README.read_text(encoding="utf-8")
    assert "products.candidate.v1.json" in text
    assert "purchase-support.v1.json" in text, (
        "the README does not name the live catalog"
    )
    assert "PURCHASE_UNUSED_PRODUCT" in text, (
        "the README does not say why the import is split across the waves"
    )
    assert str(len(wired)) + " 商品" in text, (
        "the README does not state how many products are served"
    )


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


# --- Deferred work -------------------------------------------------------
# A deferral is work this wave deliberately did not do. It is only honest if
# it names the wave that actually forces it: the record used to send the
# category pages to W5/W7 while kitchen's shelf grows at W1. The waves are
# derived here from the article rows and the candidate contents, so a wave
# written by hand into a deferral cannot drift away from the plan.

TRIGGERS = ("category_first_publishes", "wave_edits_document")
CANDIDATES = ("A", "B")


def wave_rows() -> list[dict]:
    return decisions()["waves"]


def wave_ids() -> list[str]:
    return [wave["wave"] for wave in wave_rows()]


def applied_candidates() -> set[tuple[str, str]]:
    """Candidates already published from this branch, so nothing may defer to them."""
    applied = decisions()["wave_zero_applied"]["applied_candidate"]
    return {(applied["wave"], applied["candidate"])}


def candidate_order() -> list[tuple[str, str, list[str]]]:
    order = []
    for wave in wave_rows():
        for candidate in CANDIDATES:
            key = "candidate_a" if candidate == "A" else "candidate_b"
            order.append((wave["wave"], candidate, wave[key]["contents"]))
    return order


def lists_document(contents: list[str], document: str) -> bool:
    """``kitchen`` matches ``kitchen (136)`` and ``kitchen（EX_KITCHEN→A07）``."""
    return any(
        re.match(rf"{re.escape(document)}(?![0-9a-z-])", entry) for entry in contents
    )


def first_wave_publishing(category: str) -> str | None:
    rows = {row["article_id"]: row for row in article_rows()}
    for wave in wave_rows():
        for article_id in wave["articles"]:
            if rows[article_id]["category"] == category:
                return wave["wave"]
    return None


def deferrals() -> list[dict]:
    return decisions()["deferrals"]


def test_every_deferral_is_a_complete_record() -> None:
    rows = deferrals()
    assert rows, "the record defers work but writes none of it down"
    ids = [row["id"] for row in rows]
    assert ids == sorted(ids), ids
    assert len(ids) == len(set(ids)), ids
    for row in rows:
        assert re.fullmatch(r"DF[0-9]{2}", row["id"]), row["id"]
        for field in ("what", "why"):
            assert row[field].strip(), (row["id"], field)
        assert row["where"], row["id"]
        for path in row["where"]:
            assert (ROOT / path).exists(), (row["id"], path)
        assert row["trigger"] in TRIGGERS, row
        assert row["candidate"] in CANDIDATES, row
        assert row["wave"] in wave_ids(), row


def test_no_deferral_points_at_a_candidate_that_already_shipped() -> None:
    for row in deferrals():
        assert (row["wave"], row["candidate"]) not in applied_candidates(), row["id"]


def test_every_deferral_names_the_wave_that_actually_triggers_it() -> None:
    order = candidate_order()
    applied = applied_candidates()
    for row in deferrals():
        documents = row.get("documents", [])
        if row["trigger"] == "category_first_publishes":
            expected = first_wave_publishing(row["category"])
            assert expected is not None, row
            assert row["wave"] == expected, (
                f"{row['id']} defers to {row['wave']} but {row['category']} "
                f"first publishes in {expected}"
            )
        else:
            assert documents, row["id"]
            earliest = next(
                (wave, candidate)
                for wave, candidate, contents in order
                if (wave, candidate) not in applied
                and all(lists_document(contents, name) for name in documents)
            )
            assert (row["wave"], row["candidate"]) == earliest, (row["id"], earliest)

        # The named candidate has to have a slot for the work it defers.
        contents = next(
            contents
            for wave, candidate, contents in order
            if (wave, candidate) == (row["wave"], row["candidate"])
        )
        for name in documents:
            assert lists_document(contents, name), (row["id"], name, contents)


def test_a_deferral_that_repeats_lists_the_later_waves_in_order() -> None:
    ids = wave_ids()
    for row in deferrals():
        later = row.get("later_waves", [])
        assert later == sorted(later, key=ids.index), row["id"]
        assert len(later) == len(set(later)), row["id"]
        for wave in later:
            assert wave in ids, (row["id"], wave)
            assert ids.index(wave) > ids.index(row["wave"]), (row["id"], wave)


def test_the_readme_no_longer_carries_the_deferrals_on_its_own() -> None:
    text = README.read_text(encoding="utf-8")
    assert "W5 / W7 で掲載内容が増えたときに" not in text, (
        "the README still defers the category pages to the wrong waves"
    )
    assert "decisions.v1.json" in text
    assert "deferrals" in text, "the README does not point at the deferral records"
    for row in deferrals():
        assert row["id"] in text, row["id"]


def test_wave_zero_records_the_category_pages_as_widened() -> None:
    applied = decisions()["wave_zero_applied"]
    assert applied["applied_candidate"] == {"wave": "W0", "candidate": "A"}, applied
    for untouched in applied["not_touched"]:
        assert "カテゴリページのタイトル" not in untouched, untouched

    widened = decisions()["owner_decisions"]["categories_widened"]
    names = widened["page_names"]
    ledger = {
        row["article_key"]: row
        for row in json.loads(
            (ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json").read_text(
                encoding="utf-8"
            )
        )["articles"]
    }
    assert set(names) == {"kitchen", "cleaning"}, names
    for key, change in names.items():
        assert ledger[key]["title"] == change["after"], key
        assert change["before"] != change["after"], key
        # W0's excerpt_after is what W0 wrote. A later wave that puts a new kind
        # of article on the shelf has to say so in the excerpt too (DF02), and
        # records that revision here rather than overwriting W0's value -- so the
        # ledger is still compared with one pinned string, the newest one.
        revised = change.get("excerpt_revised")
        expected = revised["excerpt_after"] if revised else change["excerpt_after"]
        assert ledger[key]["excerpt"] == expected, key
        if revised:
            assert revised["in"].startswith("W"), key
            assert revised["excerpt_after"] != change["excerpt_after"], key
            assert revised["why"].strip(), key


# A candidate is a publish batch with a hard ceiling: 20 proposals, one of which
# is always the theme. A deferral that names a wave whose candidates have no
# slot for its document is a promise nothing will keep — DF03 sent the policy
# page to W3/W5/W7 while none of those candidates listed it.
PROPOSAL_LIMIT = 20


def candidate_rows() -> list[tuple[str, str, dict]]:
    return [
        (wave["wave"], candidate, wave["candidate_a" if candidate == "A" else "candidate_b"])
        for wave in wave_rows()
        for candidate in CANDIDATES
    ]


def test_every_candidate_counts_its_own_documents_and_fits_the_limit() -> None:
    for wave, candidate, row in candidate_rows():
        contents = row["contents"]
        assert row["documents"] == len(contents), (wave, candidate, contents)
        assert row["theme"] is True, (wave, candidate)
        proposals = row["documents"] + 1
        assert proposals <= PROPOSAL_LIMIT, (wave, candidate, proposals)
        assert len(contents) == len(set(contents)), (wave, candidate, contents)


def test_the_applied_candidate_records_the_size_it_actually_holds() -> None:
    applied = decisions()["wave_zero_applied"]
    published = applied["publish_candidate"]
    wave, candidate = applied["applied_candidate"].values()
    planned = next(
        row for w, c, row in candidate_rows() if (w, c) == (wave, candidate)
    )
    assert published["documents"] == planned["documents"], (published, planned)
    assert published["contents"] == planned["contents"], published["contents"]
    assert published["proposals"] == published["documents"] + 1, published
    assert published["limit"] == PROPOSAL_LIMIT, published
    assert applied["documents_changed"] == published["documents"], applied


def test_a_deferral_that_repeats_fits_every_later_wave_it_names() -> None:
    """Each repeat needs a candidate that republishes the document it changes."""
    order = candidate_order()
    for row in deferrals():
        documents = row.get("documents", [])
        for wave in row.get("later_waves", []):
            fitting = [
                candidate
                for held_wave, candidate, contents in order
                if held_wave == wave
                and all(lists_document(contents, name) for name in documents)
            ]
            assert fitting, (
                f"{row['id']} repeats in {wave}, but no {wave} candidate lists "
                f"{documents}"
            )


def test_each_deferral_quotes_wording_the_named_file_really_carries() -> None:
    """DF05 named a file that never held the sentence it deferred."""
    rows = deferrals()
    assert any("where_quote" in row for row in rows), (
        "no deferral pins the wording it defers to the file that carries it"
    )
    for row in rows:
        quotes = row.get("where_quote", {})
        rewritten = row.get("where_quote_after", {})
        assert set(rewritten) <= set(quotes), (row["id"], sorted(rewritten))
        if rewritten:
            applied = row["applied_in"]
            assert (applied["wave"], applied["candidate"]) == (
                row["wave"],
                row["candidate"],
            ), (row["id"], applied)
        for path, quote in quotes.items():
            assert path in row["where"], (row["id"], path)
            text = (ROOT / path).read_text(encoding="utf-8")
            if path in rewritten:
                # The candidate this deferral names has already rewritten the
                # file: the deferred wording has to be gone and the wording the
                # record says replaced it has to be there.
                assert quote not in text, (row["id"], path, quote)
                assert rewritten[path] in text, (row["id"], path, rewritten[path])
            else:
                assert quote in text, (row["id"], path, quote)


# --- the record answers to the artifact ------------------------------------
# Three ways the record drifted from what the files hold: a deferral that named
# the sentence it defers but not every page that prints it, the reader's unit
# 「分野」 written as the working word 「群」, and a row of the wave table that
# counted two links in an article that has one.
UNIT_WORD = "群"
# The only place the record may still use it: quoting the note it removed.
UNIT_WORD_QUOTED_IN = ("reader_note_changes",)
HUB_LINK_ROW = re.compile(
    r"^\| `(?P<slug>[a-z0-9-]+)` \| \d+ \| [^|]+ \| `/(?P<hub>kitchen|cleaning)/` "
    r"[^|]*?リンク (?P<count>\d+) 本の文言 \|$",
    re.M,
)


def test_a_deferral_lists_every_document_its_quoted_wording_reaches() -> None:
    """DF02 quoted a source file whose sentence prints on a page it never listed."""
    documents = projection.reader_documents()
    for row in deferrals():
        listed = row.get("documents", [])
        after = row.get("where_quote_after", {})
        for path, quote in row.get("where_quote", {}).items():
            # A file the deferral already rewrote is measured by the wording
            # that replaced it; the deferred sentence reaches nothing by design.
            wording = after.get(path, quote)
            reached = sorted(key for key, body in documents.items() if wording in body)
            assert reached, (row["id"], path, wording)
            for key in reached:
                assert key in listed, (row["id"], path, key, listed)


# The card source that prints somewhere other than the page a deferral names.
SHARED_CARD_SOURCE = "changes/site-improvements-20260913/entry-pages.v1.json"


def test_a_deferral_that_defers_the_shared_cards_quotes_them() -> None:
    """entry-pages.v1.json prints on /categories/ and home, not on the hub it names.

    DF02 named the file and quoted only the hub's own sentence, so the reach
    check above had nothing to catch: the two pages that really carry the
    deferred wording stayed off its documents list.
    """
    for row in deferrals():
        if SHARED_CARD_SOURCE not in row["where"] or not row.get("where_quote"):
            continue
        assert SHARED_CARD_SOURCE in row["where_quote"], row["id"]


def strings_with_paths(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from strings_with_paths(value, (*path, key))
    elif isinstance(node, list):
        for value in node:
            yield from strings_with_paths(value, path)
    elif isinstance(node, str):
        yield path, node


def test_the_record_counts_the_declared_fields_the_way_the_page_counts_them() -> None:
    """One unit for one subject: the policy page says 分野, so the record does too."""
    assert UNIT_WORD not in README.read_text(encoding="utf-8")
    leaked = [
        path
        for path, text in strings_with_paths(decisions())
        if UNIT_WORD in text and not any(key in UNIT_WORD_QUOTED_IN for key in path)
    ]
    assert leaked == [], leaked


def test_the_wave_zero_table_counts_the_hub_links_it_says_it_rewrote() -> None:
    """The table said 「2 本」 for an article whose body links the hub once."""
    rows = HUB_LINK_ROW.findall(README.read_text(encoding="utf-8"))
    assert len(rows) == 12, rows
    for slug, hub, count in rows:
        body = (
            ROOT / f"changes/wordpress-direct-publish-v1/articles/{slug}.html"
        ).read_text(encoding="utf-8")
        links = [
            anchor
            for anchor in fragment(body).find(tag="a")
            if (anchor.attrs.get("href") or "").split("#")[0].rstrip("/").endswith(
                f"/{hub}"
            )
        ]
        assert len(links) == int(count), (slug, hub, count, len(links))


# --- the hub-link table answers to the bodies it rewrote --------------------
# ``hub_link_labels_rewritten.before`` lists the wording this wave replaced. The
# counts beside each label were written by hand and two of them were wrong: the
# 「・記事一覧」 label was credited to four articles when two carry it, and the bare
# 「食洗機の選び方」 row named only the branch-faucet guide, leaving out the four
# guides that carry it once each. Counted on the bodies published at the base
# commit, the seven rows have to add up to every hub link the wave rewrote.
HUB_ANCHOR_HREF = re.compile(r"/(kitchen|cleaning)/$")
LABEL_COUNT = re.compile(r"(\d+)\s*(本|か所)")


def _git(*arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments), cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def hub_link_record() -> dict:
    return decisions()["wave_zero_applied"]["hub_link_labels_rewritten"]


def hub_links_at_the_base_commit() -> dict[str, list[str]]:
    """Link text → the articles that carried it, as published before this wave."""
    base = decisions()["wave_zero_applied"]["base_commit"]
    ledger = json.loads(
        _git("show", f"{base}:changes/wordpress-direct-publish-v1/articles.v1.json")
    )["articles"]
    carried: dict[str, list[str]] = {}
    for row in ledger:
        source = row.get("body_source") or row.get("patch_source")
        if row["post_type"] != "post" or not source:
            continue
        for anchor in fragment(_git("show", f"{base}:{source}")).find(tag="a"):
            href = (anchor.attrs.get("href") or "").split("#")[0].split("?")[0]
            if HUB_ANCHOR_HREF.search(href):
                carried.setdefault(anchor.text().strip(), []).append(row["slug"])
    return carried


def labels_of(row: str) -> list[str]:
    return [label for label in row.split("（")[0].split("／") if label]


def test_the_record_names_every_hub_link_label_the_wave_replaced() -> None:
    """Seven rows, and between them every hub link the 12 bodies carried."""
    record = hub_link_record()
    carried = hub_links_at_the_base_commit()
    named = [label for row in record["before"] for label in labels_of(row)]
    assert len(named) == len(set(named)), named
    assert sorted(named) == sorted(carried), (sorted(named), sorted(carried))
    occurrences = sum(len(articles) for articles in carried.values())
    articles = {slug for articles in carried.values() for slug in articles}
    assert len(articles) == record["documents"], (sorted(articles), record["documents"])
    assert occurrences == 21, occurrences


def test_each_hub_link_row_counts_what_the_published_bodies_carried() -> None:
    """「4 本」 for a label two articles carry is a number nobody can check."""
    carried = hub_links_at_the_base_commit()
    for row in hub_link_record()["before"]:
        labels = labels_of(row)
        occurrences = sum(len(carried.get(label, [])) for label in labels)
        articles = {slug for label in labels for slug in carried.get(label, [])}
        for number, unit in LABEL_COUNT.findall(row):
            measured = len(articles) if unit == "本" else occurrences
            assert int(number) == measured, (row, unit, measured)
