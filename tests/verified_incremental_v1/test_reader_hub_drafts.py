"""Synthetic MCP draft replay tests; never authorize production."""

from copy import deepcopy
from pathlib import Path

import pytest

from scripts import raos_wordpress_reader_hubs as owner

ROOT = Path(__file__).resolve().parents[2]


class Client:
    def __init__(self):
        self.documents = [
            {"id": index + 1, "slug": slug, "post_type": "post", "status": "publish"}
            for index, slug in enumerate(owner.selected_articles(ROOT).values())
        ]
        self.creates = 0
        self.lose_response = False
        self.save_remote = True

    def call(self, name, args):
        if name == "raos-codex-content-create-draft":
            self.creates += 1
            document = {
                **args,
                "id": 100,
                "status": "draft",
                "revision_id": 1,
                "modified_gmt": "2026-09-06T00:00:00Z",
            }
            document["content_sha256"] = owner.publication.sha256_json(
                {
                    "schema": "ContentDocumentV1",
                    "id": 100,
                    "status": "draft",
                    **args,
                }
            )
            if self.save_remote:
                self.documents.append(document)
            if self.lose_response:
                raise TimeoutError("synthetic lost reply")
            return document
        if name == "raos-codex-content-get":
            return next(d for d in self.documents if d["id"] == args["id"])
        raise AssertionError(name)


def run(monkeypatch, client, receipt, persisted):
    monkeypatch.setattr(
        owner.publication,
        "list_all_documents",
        lambda *a, **k: deepcopy(client.documents),
    )
    return owner.reconcile_hub_drafts(
        client,
        root=ROOT,
        selected=["categories"],
        receipt=receipt,
        persist=lambda value: persisted.append(deepcopy(value)),
    )


def fresh():
    return {
        "schema": owner.SCHEMA,
        "registry_sha256": owner.pages.hub_registry_sha256(ROOT),
        "slugs": sorted(owner.pages.HUB_SLUGS),
        "local_validation": {"source_sha256": owner.source_fingerprint(ROOT)},
        "drafts": {},
        "inflight": {},
    }


def test_intent_precedes_create_and_repeat_does_not_duplicate(monkeypatch):
    client, receipt, persisted = Client(), fresh(), []
    run(monkeypatch, client, receipt, persisted)
    assert persisted[0]["inflight"]["categories"]
    assert receipt["drafts"]["categories"]["id"] == 100
    assert receipt["drafts"]["categories"]["status"] == "draft"
    run(monkeypatch, client, receipt, persisted)
    assert client.creates == 1


def test_lost_response_reconciles_remote_document_without_resend(monkeypatch):
    client, receipt, persisted = Client(), fresh(), []
    client.lose_response = True
    with pytest.raises(TimeoutError):
        run(monkeypatch, client, receipt, persisted)
    assert receipt["inflight"]
    run(monkeypatch, client, receipt, persisted)
    assert client.creates == 1 and receipt["drafts"]["categories"]["id"] == 100


def test_unknown_result_without_remote_document_stays_blocked(monkeypatch):
    client, receipt, persisted = Client(), fresh(), []
    client.lose_response, client.save_remote = True, False
    with pytest.raises(TimeoutError):
        run(monkeypatch, client, receipt, persisted)
    with pytest.raises(ValueError, match="WRITE_RESULT_UNKNOWN"):
        run(monkeypatch, client, receipt, persisted)
    assert client.creates == 1


def test_collision_never_updates_existing_page(monkeypatch):
    client = Client()
    client.documents.append(
        {
            "id": 100,
            "slug": "categories",
            "post_type": "page",
            "status": "publish",
            "title": "Existing unrelated page",
            "excerpt": "",
            "block_markup": "<p>Keep</p>",
            "taxonomies": {},
            "media_ids": [],
        }
    )
    with pytest.raises(ValueError, match="SLUG_CONFLICT"):
        run(monkeypatch, client, fresh(), [])
    assert client.creates == 0


def test_unpublished_article_stops_before_draft_write(monkeypatch):
    client = Client()
    client.documents[0]["status"] = "draft"
    with pytest.raises(ValueError, match="PUBLIC_ARTICLE_IDENTITY"):
        run(monkeypatch, client, fresh(), [])
    assert client.creates == 0


def test_unknown_local_guide_never_reaches_mcp():
    with pytest.raises(ValueError, match="HUB_SELECTION"):
        owner.reconcile_hub_drafts(
            Client(),
            root=ROOT,
            selected=["dishwasher-running-cost"],
            receipt=fresh(),
            persist=lambda value: None,
        )

def test_selection_changes_reuse_the_same_inflight_target(monkeypatch):
    client, receipt = Client(), fresh()
    client.lose_response, client.save_remote = True, False
    with pytest.raises(TimeoutError):
        run(monkeypatch, client, receipt, [])
    with pytest.raises(ValueError, match="WRITE_RESULT_UNKNOWN"):
        owner.reconcile_hub_drafts(client, root=ROOT, selected=["categories", "guides"],
                                  receipt=receipt, persist=lambda value: None)
    assert client.creates == 1


def test_source_drift_after_validation_stops_before_any_create(monkeypatch):
    client, receipt = Client(), fresh()
    monkeypatch.setattr(owner, "source_fingerprint", lambda root: "f" * 64)
    with pytest.raises(ValueError, match="LOCAL_VALIDATION_CHANGED"):
        run(monkeypatch, client, receipt, [])
    assert client.creates == 0


def test_source_is_rechecked_immediately_before_create(monkeypatch):
    client, receipt = Client(), fresh()
    original = receipt["local_validation"]["source_sha256"]
    reads = iter([original, "f" * 64])
    monkeypatch.setattr(owner, "source_fingerprint", lambda root: next(reads))
    with pytest.raises(ValueError, match="LOCAL_VALIDATION_CHANGED"):
        run(monkeypatch, client, receipt, [])
    assert client.creates == 0

def test_known_unsent_source_change_can_resume_after_revalidation(monkeypatch):
    client, receipt, persisted = Client(), fresh(), []
    original = receipt["local_validation"]["source_sha256"]
    reads = iter([original, "f" * 64])
    monkeypatch.setattr(owner, "source_fingerprint", lambda root: next(reads))
    with pytest.raises(ValueError, match="LOCAL_VALIDATION_CHANGED"):
        run(monkeypatch, client, receipt, persisted)
    assert client.creates == 0 and receipt["inflight"] == {}
    assert persisted[-1]["inflight"] == {}
    monkeypatch.setattr(owner, "source_fingerprint", lambda root: original)
    run(monkeypatch, client, receipt, persisted)
    assert client.creates == 1


class PhpEmptyTaxonomyClient(Client):
    """WordPress encodes an empty PHP taxonomy array as JSON []."""

    def call(self, name, args):
        if name == "raos-codex-content-create-draft":
            args = {**args, "taxonomies": []}
        return super().call(name, args)


@pytest.mark.parametrize("lost_response", [False, True])
def test_php_empty_taxonomies_reconcile_without_resend_or_hash_rewrite(
    monkeypatch, lost_response
):
    client, receipt, persisted = PhpEmptyTaxonomyClient(), fresh(), []
    client.lose_response = lost_response
    if lost_response:
        with pytest.raises(TimeoutError):
            run(monkeypatch, client, receipt, persisted)
    run(monkeypatch, client, receipt, persisted)
    run(monkeypatch, client, receipt, persisted)
    actual = client.documents[-1]
    assert actual["taxonomies"] == []
    assert receipt["drafts"]["categories"]["content_sha256"] == actual["content_sha256"]
    assert client.creates == 1
    assert receipt["inflight"] == {}


def test_nonempty_taxonomy_array_is_not_normalized(monkeypatch):
    client, receipt = PhpEmptyTaxonomyClient(), fresh()
    client.lose_response = True
    with pytest.raises(TimeoutError):
        run(monkeypatch, client, receipt, [])
    client.documents[-1]["taxonomies"] = ["unexpected"]
    with pytest.raises(ValueError, match="SLUG_CONFLICT"):
        run(monkeypatch, client, receipt, [])
    assert client.creates == 1
    assert receipt["inflight"]
