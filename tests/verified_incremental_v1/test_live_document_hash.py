"""Synthetic current-state hashing, including unselected existing drafts."""

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts import raos_wordpress_incremental_publication as port


def server_hash(document):
    # Independently mirror the server's ContentDocumentV1 document_hash fields.
    fields = (
        "schema",
        "post_type",
        "id",
        "status",
        "title",
        "slug",
        "excerpt",
        "block_markup",
        "taxonomies",
        "media_ids",
    )
    raw = json.dumps(
        {key: document[key] for key in fields},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def document(status, ident):
    value = {
        "schema": "ContentDocumentV1",
        "post_type": "post",
        "id": ident,
        "status": status,
        "title": "Synthetic 日本語",
        "slug": f"synthetic-{ident}",
        "excerpt": "Synthetic excerpt",
        "block_markup": "<p>Synthetic only</p>",
        "taxonomies": {"category": [1], "post_tag": []},
        "media_ids": [],
        "revision_id": ident,
        "modified_gmt": "2026-09-05T12:00:00Z",
    }
    value["content_sha256"] = server_hash(value)
    return value


class ReadOnlyServer:
    def __init__(self, documents):
        self.documents = documents

    def call(self, name, arguments):
        assert name == "raos-codex-content-get"
        return deepcopy(
            next(row for row in self.documents if row["id"] == arguments["id"])
        )


@pytest.fixture
def world(monkeypatch):
    rows = [document("publish", 1), document("draft", 2), document("draft", 3)]
    server = ReadOnlyServer(rows)
    monkeypatch.setattr(
        port.publication,
        "list_all_documents",
        lambda client, **kwargs: deepcopy(client.documents),
    )
    baseline = SimpleNamespace(
        snapshot={
            "all_document_baselines": {
                str(row["id"]): port.publication._baseline_record(row) for row in rows
            },
            "deployment_status": {"theme": {"tree_sha256": "a" * 64}},
        }
    )
    return server, baseline


def test_current_state_keeps_drafts_while_proposal_after_remains_publish(world):
    server, baseline = world
    before = deepcopy(server.documents)
    current = port._live_documents(server)
    assert list(current) == [row["slug"] for row in before]
    assert server.documents == before
    for row in current.values():
        assert port._stored_document_sha256(row) == server_hash(row)
        after = port.publication._content_after_sha256(row, row["id"])
        assert after == server_hash({**row, "status": "publish"})
        assert (after == row["content_sha256"]) == (row["status"] == "publish")
    port._require_before(baseline, current, {"theme": {"tree_sha256": "a" * 64}})


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "Changed"),
        ("block_markup", "<p>Changed</p>"),
        ("status", "publish"),
        ("excerpt", "Changed"),
        ("taxonomies", {"category": [2]}),
        ("media_ids", [4]),
    ],
)
def test_draft_content_tamper_is_not_hidden_by_identical_list_and_get(
    world, field, value
):
    server, _ = world
    server.documents[1][field] = value
    with pytest.raises(
        port.publication.PublicationFailure, match="LIVE_DOCUMENT_CHANGED_DURING_READ"
    ):
        port._live_documents(server)


@pytest.mark.parametrize("mutation", ["add", "remove", "change", "publish"])
def test_entire_inventory_stays_bound_including_unselected_drafts(world, mutation):
    server, baseline = world
    if mutation == "add":
        server.documents.append(document("draft", 4))
    elif mutation == "remove":
        server.documents.pop()
    else:
        row = server.documents[1]
        row["title" if mutation == "change" else "status"] = (
            "Changed" if mutation == "change" else "publish"
        )
        row["content_sha256"] = server_hash(row)
    current = port._live_documents(server)
    with pytest.raises(
        port.publication.PublicationFailure, match="LIVE_BASELINE_CHANGED"
    ):
        port._require_before(baseline, current, {"theme": {"tree_sha256": "a" * 64}})


def test_list_get_difference_still_fails(world, monkeypatch):
    server, _ = world
    original = server.call

    def changed(name, arguments):
        row = original(name, arguments)
        row["revision_id"] += 1
        return row

    monkeypatch.setattr(server, "call", changed)
    with pytest.raises(
        port.publication.PublicationFailure, match="LIVE_DOCUMENT_CHANGED_DURING_READ"
    ):
        port._live_documents(server)


@pytest.mark.parametrize("status", ["pending", "private", "trash", "future", ""])
def test_unsupported_status_never_becomes_a_valid_observation(status):
    with pytest.raises(
        port.publication.PublicationFailure, match="LIVE_DOCUMENT_STATUS_INVALID"
    ):
        port._stored_document_sha256(document(status, 1))
