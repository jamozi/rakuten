"""MCP snapshot replay and existing-only guard; synthetic documents only."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import raos_wordpress_incremental_snapshot as owner


def document() -> dict[str, object]:
    row: dict[str, object] = {
        "schema": "ContentDocumentV1",
        "id": 19,
        "status": "publish",
        "post_type": "post",
        "slug": "guide",
        "title": "Synthetic guide",
        "excerpt": "Synthetic excerpt",
        "block_markup": "<p>Recorded fixture</p>",
        "taxonomies": {"category": [5], "post_tag": [], "post_format": []},
        "media_ids": [],
        "revision_id": 2,
        "modified_gmt": "2026-09-05T02:00:00Z",
    }
    row["content_sha256"] = owner.publication._content_after_sha256(row, 19)
    return row


class Client:
    def __init__(self) -> None:
        self.row = document()
        self.get_row = deepcopy(self.row)
        self.calls: list[str] = []

    def initialize(self) -> None:
        self.calls.append("initialize")

    def call(self, name: str, args: dict[str, Any]) -> dict[str, object]:
        self.calls.append(name)
        if name == "raos-codex-site-status":
            return {"schema": "RecordedStatus", "publication_authority": False}
        if name == "raos-codex-content-get":
            return self.get_row
        assert name == "raos-codex-content-list"
        rows = [self.row] if args["post_type"] == "post" else []
        return {
            "schema": "ContentDocumentListV1",
            "page": args["page"],
            "per_page": args["per_page"],
            "total": len(rows),
            "documents": rows,
        }


def test_snapshot_only_uses_bounded_readonly_mcp() -> None:
    client = Client()
    result = owner.capture_snapshot(client, expected_slugs=frozenset({"guide"}))
    assert result["publication_authority"] is False
    assert result["documents"] == [client.row]
    assert result["public_metadata"]["status"] == "UNVERIFIED"
    assert result["deployment_status"] == {"status": "NOT_CAPTURED", "theme": None}
    assert set(client.calls) == {
        "initialize",
        "raos-codex-site-status",
        "raos-codex-content-get",
        "raos-codex-content-list",
    }


def test_snapshot_refuses_missing_policy_instead_of_creating() -> None:
    with pytest.raises(
        owner.publication.PublicationFailure, match="EXISTING_TARGET_MISSING"
    ):
        owner.capture_snapshot(
            Client(), expected_slugs=frozenset({"guide", "comparison-policy"})
        )


def test_snapshot_refuses_changed_document_between_list_and_get() -> None:
    client = Client()
    client.get_row["block_markup"] = "<p>Changed</p>"
    with pytest.raises(
        owner.publication.PublicationFailure, match="CHANGED_DURING_READ"
    ):
        owner.capture_snapshot(client, expected_slugs=frozenset({"guide"}))


def test_snapshot_recomputes_wordpress_hash() -> None:
    client = Client()
    client.row["block_markup"] = "<p>Changed</p>"
    client.get_row = deepcopy(client.row)
    with pytest.raises(owner.publication.PublicationFailure, match="HASH_INVALID"):
        owner.capture_snapshot(client, expected_slugs=frozenset({"guide"}))


def test_nonowner_path_fails_before_any_credential_read(tmp_path: Path) -> None:
    with pytest.raises(
        owner.publication.PublicationFailure, match="OWNER_CHECKOUT_INVALID"
    ):
        owner.publication.EditorMcpClient(owner_checkout=tmp_path)


class MetadataReader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.post: dict[str, object] = {
            "id": 19,
            "type": "post",
            "slug": "guide",
            "status": "publish",
            "date": "2026-08-01T09:23:00",
            "date_gmt": "2026-08-01T00:23:00",
            "modified": "2026-09-05T11:00:00",
            "modified_gmt": "2026-09-05T02:00:00",
            "categories": [5],
            "tags": [],
        }

    def get(self, resource: str, resource_id: int) -> dict[str, object]:
        self.calls.append((resource, resource_id))
        if resource == "categories":
            body = {
                "id": resource_id,
                "name": "暮らしの道具",
                "slug": "live-category",
                "parent": 0,
            }
            fields = "id,slug,name,parent"
        else:
            assert resource == "posts"
            body = deepcopy(self.post)
            fields = "id,type,slug,status,date,date_gmt,modified,modified_gmt,categories,tags"
        raw = json.dumps(body)
        return {
            "document": body,
            "url": f"https://kurashinoshirube.com/wp-json/wp/v2/{resource}/{resource_id}?_fields={fields}",
            "snapshot_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "response_utf8": raw,
            "retrieved_at": "2026-09-05T02:05:00Z",
        }


def test_public_metadata_is_separate_cross_checked_and_stable() -> None:
    reader = MetadataReader()
    client = Client()
    result = owner.capture_snapshot(
        client, expected_slugs=frozenset({"guide"}), public_metadata_reader=reader
    )
    metadata = result["public_metadata"]
    assert metadata["status"] == "VERIFIED"
    assert metadata["unverified"] == {}
    assert (
        metadata["documents"]["guide"]["mcp_content_sha256"]
        == client.row["content_sha256"]
    )
    assert (
        metadata["documents"]["guide"]["evidence"]["document"]["date_gmt"]
        == "2026-08-01T00:23:00"
    )
    assert reader.calls == [
        ("posts", 19),
        ("categories", 5),
        ("categories", 5),
        ("posts", 19),
    ]
    assert "front_page_setting" in metadata["not_observed"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 20),
        ("slug", "wrong"),
        ("categories", [7]),
        ("status", "draft"),
        ("type", "page"),
        ("modified_gmt", "2026-09-04T02:00:00"),
        ("date", "invented"),
    ],
)
def test_public_metadata_mismatch_is_unverified_not_owner_input_missing(
    field: str, value: object
) -> None:
    reader = MetadataReader()
    reader.post[field] = value
    result = owner.capture_snapshot(
        Client(), expected_slugs=frozenset({"guide"}), public_metadata_reader=reader
    )
    metadata = result["public_metadata"]
    assert metadata["status"] == "UNVERIFIED"
    assert metadata["documents"] == {}
    assert list(metadata["unverified"]) == ["guide"]
    assert "OWNER" not in json.dumps(metadata["unverified"])


def test_public_metadata_connection_failure_is_honest_unverified() -> None:
    class Missing:
        def get(self, *_args: object) -> None:
            raise owner.PublicMetadataUnavailable("PUBLIC_METADATA_UNAVAILABLE")

    result = owner.capture_snapshot(
        Client(), expected_slugs=frozenset({"guide"}), public_metadata_reader=Missing()
    )
    assert result["public_metadata"]["unverified"] == {
        "guide": ["PUBLIC_METADATA_UNAVAILABLE"]
    }


def deployment_status() -> dict[str, object]:
    return {
        "schema": "RAOSWordPressDeploymentStatusV1",
        "origin": owner.publication.ORIGIN,
        "theme": {
            "slug": "kurashinoshirube-child",
            "active": True,
            "tree_sha256": "d" * 64,
        },
        "gates": {"ignored_private_detail": True},
    }


def test_deployment_theme_baseline_uses_readonly_callback_twice_and_minimal_fields() -> (
    None
):
    calls: list[str] = []

    def reader() -> dict[str, object]:
        calls.append("deployment-status")
        return deployment_status()

    result = owner.capture_snapshot(
        Client(), expected_slugs=frozenset({"guide"}), deployment_status_reader=reader
    )
    assert calls == ["deployment-status", "deployment-status"]
    baseline = result["deployment_status"]
    assert baseline["theme"]["tree_sha256"] == "d" * 64
    assert baseline["status"] == "CAPTURED_READ_ONLY"
    assert "gates" not in baseline and "origin" not in baseline
    assert "https://" not in json.dumps(baseline)


def test_deployment_theme_change_during_snapshot_is_rejected() -> None:
    calls = 0

    def reader() -> dict[str, object]:
        nonlocal calls
        calls += 1
        row = deployment_status()
        row["theme"]["tree_sha256"] = ("d" if calls == 1 else "e") * 64
        return row

    with pytest.raises(
        owner.publication.PublicationFailure, match="THEME_CHANGED_DURING_READ"
    ):
        owner.capture_snapshot(
            Client(),
            expected_slugs=frozenset({"guide"}),
            deployment_status_reader=reader,
        )


@pytest.mark.parametrize(
    "resource,resource_id",
    [("settings", 1), ("posts", 0), ("https://outside.example", 19)],
)
def test_public_reader_has_no_arbitrary_url_or_settings_capability(
    resource: str, resource_id: int
) -> None:
    with pytest.raises(owner.PublicMetadataUnavailable, match="TARGET_INVALID"):
        owner.PublicMetadataReader().get(resource, resource_id)
