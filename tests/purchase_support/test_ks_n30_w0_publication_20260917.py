"""The 2026-09-17 publish of wave 0, as ``changes/next30-20260916`` records it.

W0-A reached production on 2026-09-17 with the owner's 公開して and was read
back anonymously afterwards. A publish record is the only account a later wave
has of what readers were given, so every field of it answers to something
outside itself:

``published.candidate_id``
    must be a candidate the publication records call published, and must not be
    one an earlier publish already used. A candidate built only to show someone
    a layout is not a publish.
``published.documents``
    must be the documents this wave actually changed. They are measured by
    diffing every ledger row's published body against the wave's
    ``base_commit`` (``b5618eed`` / PR #293), which is on main and so present in
    every clone -- not read back out of the plan the record itself wrote.
``published.published_window`` and ``gates_before_publish``
    must be the moments and the numbers the logs carry, the two clocks naming
    the same instants.

The three approved layouts the owner accepted in the same breath are checked
here as well: an acceptance naming a candidate that no publish lists, or a
digest that is not the body the publish sent, records an acceptance of
something no reader ever saw.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "changes/next30-20260916"
DECISIONS = PACKAGE / "decisions.v1.json"
README = PACKAGE / "README.md"
LEDGER = ROOT / "changes/wordpress-direct-publish-v1/articles.v1.json"
ARTICLE_DIR = ROOT / "changes/wordpress-direct-publish-v1/articles"
BASELINES = (
    ROOT / "changes/site-improvements-20260913/approved-layout-baselines.v1.json"
)
STATUS = ROOT / "changes/ks-integrated-20260915/status.v1.json"
EARLIER_PUBLICATION = (
    ROOT / "changes/site-improvements-20260913/publication-result.v1.json"
)

PUBLISHED = "PUBLISHED_AND_READBACK_VERIFIED"
#: One entry of a candidate's contents: ``about-ad-policy (10)``.
CONTENT = re.compile(r"^(?P<key>[a-z0-9-]+) \((?P<post_id>[0-9]+)\)$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
OBJECT = re.compile(r"^[0-9a-f]{40}$")
SNAPSHOT = re.compile(r"^ps-[0-9a-f]{32}$")
THREAD = "7b238a17-f16f-4f75-9e66-251570af7781"
STATEMENT = "公開して"
TASK = "KS-N30-W0"
#: The revisions this wave published and the owner accepted on 2026-09-17.
ACCEPTED = (
    "compact-robot-vacuum-shortlist",
    "large-dishwasher-comparison",
    "standard-dishwasher-comparison",
)
JST = timedelta(hours=9)
#: Words a measured record may not use in place of a measurement.
ADJECTIVES = ("問題なし", "良好", "きれい", "正しく", "うまく", "特に無し", "特になし")


def _git(*arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments), cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def blob(commit: str, path: str) -> bytes | None:
    """One tracked file at one commit, or ``None`` when it did not exist yet."""
    done = subprocess.run(
        ("git", "show", f"{commit}:{path}"), cwd=ROOT, capture_output=True
    )
    return done.stdout if done.returncode == 0 else None


def commit_is_present(commit: str) -> bool:
    return (
        subprocess.run(
            ("git", "cat-file", "-e", commit + "^{commit}"),
            cwd=ROOT,
            capture_output=True,
        ).returncode
        == 0
    )


def decisions() -> dict:
    return json.loads(DECISIONS.read_text(encoding="utf-8"))


def applied() -> dict:
    return decisions()["wave_zero_applied"]


def published() -> dict:
    return applied()["published"]


def ledger_rows() -> dict[str, dict]:
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))["articles"]
    return {row["article_key"]: row for row in rows}


def contents(entries: list[str]) -> dict[str, int]:
    """``["kitchen (136)"]`` → ``{"kitchen": 136}``, refusing any other shape."""
    parsed: dict[str, int] = {}
    for entry in entries:
        found = CONTENT.match(entry)
        assert found, entry
        key = found.group("key")
        assert key not in parsed, entry
        parsed[key] = int(found.group("post_id"))
    return parsed


def wave_candidate(wave: str, candidate: str) -> dict:
    row = next(row for row in decisions()["waves"] if row["wave"] == wave)
    return row["candidate_a" if candidate == "A" else "candidate_b"]


def documents_changed_since(base: str) -> set[str]:
    """Ledger rows whose published body differs from the one ``base`` carries.

    This is what a publish sends: the ledger's own bodies, generated pages
    included, as they stand in this tree against the commit the wave started
    from. Reading the two ends out of git rather than out of the record is the
    whole point -- a record cannot then set the scope of its own audit.
    """
    changed = set()
    for key, row in ledger_rows().items():
        source = row.get("body_source") or row.get("patch_source")
        assert source, key
        before = blob(base, source)
        path = ROOT / source
        after = path.read_bytes() if path.exists() else None
        if before != after:
            changed.add(key)
    return changed


def moment(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def earlier_published_candidates() -> set[str]:
    """Candidate ids the other publication records already call published."""
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    ids = {
        batch["candidate_id"]
        for batch in status["batches"].values()
        if batch.get("publication_status") == PUBLISHED
    }
    earlier = json.loads(EARLIER_PUBLICATION.read_text(encoding="utf-8"))
    ids |= {
        batch["candidate_id"]
        for batch in earlier["batches"]
        if batch.get("publication_status") == PUBLISHED
    }
    return ids


def test_the_record_names_a_candidate_no_earlier_publish_used() -> None:
    record = published()
    assert record["publication_status"] == PUBLISHED, record["publication_status"]
    assert DIGEST.fullmatch(record["candidate_id"]), record["candidate_id"]
    assert DIGEST.fullmatch(record["snapshot_id"]), record["snapshot_id"]
    assert OBJECT.fullmatch(record["commit"]), record["commit"]
    assert OBJECT.fullmatch(record["tree"]), record["tree"]
    assert record["branch"] == applied()["branch"], record["branch"]
    assert record["theme"] is True, record
    assert record["candidate"] == "W0-A", record["candidate"]

    authorization = record["authorization"]
    assert authorization["user_statement"] == STATEMENT, authorization
    assert authorization["confirmation_source_thread"] == THREAD, authorization

    reused = earlier_published_candidates()
    assert reused, "no published candidate in the other publication records"
    assert record["candidate_id"] not in reused, record["candidate_id"]

    # The commit the publish read is a commit, and it holds the tree the publish
    # reported. It lives on the wave branch, so a clone that has only main after
    # the squash merge cannot have it; the document list below, not this sha, is
    # what the rules measure.
    if commit_is_present(record["commit"]):
        tree = _git("rev-parse", record["commit"] + "^{tree}").strip()
        assert tree == record["tree"], (tree, record["tree"])


def test_the_recorded_documents_are_the_documents_this_wave_changed() -> None:
    record = published()
    base = applied()["base_commit"]
    assert commit_is_present(base), (
        f"{base} is not in this clone, so the wave's own documents cannot be "
        "measured. It is main's commit (PR #293); fetch the full history rather "
        "than letting this rule pass unmeasured."
    )

    documents = contents(record["documents"])
    assert documents == contents(applied()["publish_candidate"]["contents"])
    wave, candidate = applied()["applied_candidate"].values()
    assert documents == contents(wave_candidate(wave, candidate)["contents"])
    assert len(documents) == record["documents_published"] == 19, documents
    assert record["documents_published"] == applied()["documents_changed"]

    rows = ledger_rows()
    for key, post_id in documents.items():
        assert key in rows, key
        assert rows[key]["post_id"] == post_id, (key, rows[key]["post_id"])

    measured = documents_changed_since(base)
    assert set(documents) == measured, set(documents).symmetric_difference(measured)


def test_the_publish_window_is_one_moment_in_two_clocks() -> None:
    window = published()["published_window"]
    start_utc = moment(window["start_utc"])
    end_utc = moment(window["end_utc"])
    start_jst = moment(window["start_jst"])
    end_jst = moment(window["end_jst"])
    readback = moment(window["readback_checked_at_jst"])

    assert start_utc == start_jst, window
    assert end_utc == end_jst, window
    assert start_jst.utcoffset() == JST and end_jst.utcoffset() == JST, window
    assert start_utc < end_utc <= readback, window
    assert start_utc.date().isoformat() == "2026-09-17", window
    assert published()["published_at"] == (
        f"{window['start_utc']}〜{end_utc.strftime('%H:%M:%S')}Z"
    ), published()["published_at"]
    assert window["measured_from"], window


def test_the_recorded_gates_are_the_numbers_the_logs_carried() -> None:
    gates = published()["gates_before_publish"]
    assert gates["at_commit"] == published()["commit"][:8], gates["at_commit"]

    pytest_gate = gates["pytest"]
    assert pytest_gate["passed"] == 3279, pytest_gate
    assert pytest_gate["subtests"] == 442, pytest_gate
    assert pytest_gate["failed"] == 0 and pytest_gate["skipped"] == 0, pytest_gate
    assert str(pytest_gate["passed"]) in pytest_gate["result"], pytest_gate

    check = gates["make_check"]
    assert check["returncode"] == 0, check
    assert "PASS" in check["result"], check

    preview = gates["preview"]
    assert preview["status"] == "PASS", preview
    assert preview["failures"] == 0, preview
    # One URL per published document plus the listing page the preview walks.
    assert preview["urls"] == published()["documents_published"] + 1, preview

    for gate in gates.values():
        if isinstance(gate, dict):
            assert gate["command"], gate
            assert gate["log"], gate


def test_the_readback_findings_are_measurements_not_adjectives() -> None:
    readback = published()["readback"]
    assert readback["status"] == "PASS", readback
    findings = readback["checks"]
    assert len(findings) >= 8, len(findings)
    for finding in findings:
        assert finding["check"].strip(), finding
        assert finding["measured"].strip(), finding
        assert finding["source"].strip(), finding
        for adjective in ADJECTIVES:
            assert adjective not in finding["measured"], finding
        # A measurement is a value: a count, a quoted string, or the empty
        # list a readback prints when it found nothing.
        assert re.search(r"[0-9]|「|\[\]", finding["measured"]), finding


def test_the_readback_findings_still_hold_in_the_bodies_that_were_published() -> None:
    """Three of the readback's checks can be re-measured from the tree itself.

    The tree is the published state: ``published.commit`` is this branch's head
    and the publish read this very ledger. Once a later wave moves these bodies,
    re-pin the reads to the commit that carried W0 to main, the way
    ``ks_w4_batch.PUBLISHED_COMMIT`` is pinned for the 2026-09-16 batch.
    """
    rows = ledger_rows()
    names = decisions()["owner_decisions"]["categories_widened"]["page_names"]
    for key, change in names.items():
        assert rows[key]["title"] == change["after"], key

    labels = set()
    for key in contents(published()["documents"]):
        row = rows[key]
        if row["post_type"] != "post":
            continue
        source = row.get("body_source") or row.get("patch_source")
        body = (ROOT / source).read_text(encoding="utf-8")
        for anchor in re.finditer(
            r'<a[^>]+href="[^"]*/(?:kitchen|cleaning)/"[^>]*>(.*?)</a>', body, re.S
        ):
            labels.add(re.sub(r"<[^>]+>", "", anchor.group(1)).strip())
    assert labels, "no hub link in the published bodies"
    for label in labels:
        assert label.startswith(tuple(change["after"] for change in names.values())), (
            label
        )

    old = decisions()["wave_zero_applied"]["hub_link_labels_rewritten"]["new_labels"]
    assert set(old.values()) == {change["after"] for change in names.values()}, old


def test_the_accepted_layouts_name_the_body_this_candidate_published() -> None:
    record = published()
    keys = contents(record["documents"])
    articles = json.loads(BASELINES.read_text(encoding="utf-8"))["articles"]
    for slug in ACCEPTED:
        entry = articles[slug]
        assert "pending_revision" not in entry, (
            f"{slug} still waits for the owner, but the wave that changed it is "
            "published"
        )
        accepted = entry["latest_accepted"]
        assert accepted["shared_candidate"] == record["candidate_id"], slug
        assert accepted["source_commit"] == record["commit"][:8], slug
        assert accepted["user_statement"] == STATEMENT, slug
        assert accepted["confirmation_source_thread"] == THREAD, slug
        assert accepted["publication_authorized"] is False, slug
        assert accepted["branches"] == [record["branch"]], slug
        assert accepted["tasks"] == [TASK], slug
        assert accepted["source_paths"], slug
        assert slug in keys, slug

        raw = (ARTICLE_DIR / f"{slug}.html").read_bytes()
        assert accepted["body_sha256"] == hashlib.sha256(raw).hexdigest(), slug
        assert SNAPSHOT.fullmatch(accepted["snapshot_id"]), slug
        assert accepted["snapshot_id"] in raw.decode("utf-8"), slug

        previous = entry["previous_accepted"]
        assert previous, slug
        assert previous[0]["shared_candidate"] != record["candidate_id"], slug
        assert previous[0]["body_sha256"] != accepted["body_sha256"], slug
        assert moment(previous[0]["recorded_at"]) < moment(accepted["recorded_at"])


def test_the_readme_records_the_publish_it_says_happened() -> None:
    text = README.read_text(encoding="utf-8")
    record = published()
    for quoted in (
        record["candidate_id"],
        record["commit"][:8],
        PUBLISHED,
        record["published_at"],
        str(record["gates_before_publish"]["pytest"]["passed"]),
    ):
        assert quoted in text, quoted
    for finding in record["readback"]["checks"][:3]:
        assert finding["measured"] in text, finding["measured"]
    assert "approved-layout-baselines.v1.json の Before/After 了承" not in text, (
        "the README still lists the owner's acceptance as unresolved"
    )
