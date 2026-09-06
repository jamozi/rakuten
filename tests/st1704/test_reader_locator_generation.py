"""Verified literal extensions survive their normal owner generation."""
from copy import deepcopy
import json

import pytest

from scripts import build_st1704_portfolio_source_packets as owner


def documents():
    return (
        json.loads(owner.REGISTRY_PATH.read_bytes()),
        json.loads(owner.LOCATOR_PATH.read_bytes()),
    )


def test_reviewed_extensions_are_stable_under_repeated_generation():
    first = owner._documents()
    second = owner._documents()
    assert first == second
    assert first == (owner.REGISTRY_PATH.read_bytes(), owner.LOCATOR_PATH.read_bytes())
    authored = json.loads(owner.READER_EXPANSIONS_PATH.read_bytes())
    assert authored["publication_authority"] is False
    generated = {row["source_ref"]: row for row in json.loads(first[1])["sources"]}
    for entry in authored["expansions"]:
        fragments = [fragment for item in generated[entry["source_ref"]]["locators"]
                     for fragment in item["exact_utf8_fragments"]]
        assert entry["after"] in fragments
        assert entry["before"] in entry["after"]


def test_changed_statement_cannot_inherit_old_locator_review():
    registry, locator = documents()
    entry = json.loads(owner.READER_EXPANSIONS_PATH.read_bytes())["expansions"][0]
    claim_id = entry["claim_bindings"][0]["claim_id"]
    for packet in registry["source_packets"]:
        for claim in packet["claims"]:
            if claim["claim_id"] == claim_id:
                claim["statement"] += "Synthetic changed claim"
    with pytest.raises(ValueError, match="claim statement changed"):
        owner._apply_reviewed_locator_expansions(registry, locator)


def test_locator_review_cannot_drop_the_previously_verified_fragment(tmp_path, monkeypatch):
    authored = deepcopy(json.loads(owner.READER_EXPANSIONS_PATH.read_bytes()))
    authored["expansions"][0]["after"] = "Synthetic unrelated text"
    path = tmp_path / "expansions.json"
    path.write_text(json.dumps(authored))
    monkeypatch.setattr(owner, "READER_EXPANSIONS_PATH", path)
    with pytest.raises(ValueError, match="strict contextual extension"):
        owner._apply_reviewed_locator_expansions(*documents())
