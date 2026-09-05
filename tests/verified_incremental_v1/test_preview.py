"""Mix exact old content with selected new drafts; neither implies publication."""

from copy import deepcopy
import hashlib
import json
from typing import Any

import pytest

from scripts.raos_wordpress_incremental_snapshot import (
    capture_public_metadata,
    publication,
)
from raos.application.editorial.verified_incremental_preview_v1 import (
    build_mixed_preview,
    derive_editorial_browser_expectations,
)
from raos.application.editorial.verified_incremental_v1 import (
    IncrementalPublicationFailure,
)


def metadata_for(documents: list[dict[str, Any]]) -> dict[str, object]:
    class Reader:
        def get(self, resource: str, resource_id: int) -> dict[str, object]:
            if resource in {"categories", "tags"}:
                document = {
                    "id": resource_id,
                    "name": "本番の分類",
                    "slug": "live-category",
                    "parent": 0,
                }
                fields = "id,slug,name,parent"
            else:
                live = next(row for row in documents if row["id"] == resource_id)
                document = {
                    "id": resource_id,
                    "slug": live["slug"],
                    "status": "publish",
                    "type": live["post_type"],
                    "date": "2026-08-01T09:23:00",
                    "date_gmt": "2026-08-01T00:23:00",
                    "modified": "2026-09-05T11:00:00",
                    "modified_gmt": "2026-09-05T02:00:00",
                }
                if live["post_type"] == "post":
                    document.update(categories=[5], tags=[])
                fields = "id,type,slug,status,date,date_gmt,modified,modified_gmt,categories,tags"
            raw = json.dumps(document)
            return {
                "document": document,
                "url": f"https://kurashinoshirube.com/wp-json/wp/v2/{resource}/{resource_id}?_fields={fields}",
                "retrieved_at": "2026-09-05T02:05:00Z",
                "snapshot_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "response_utf8": raw,
            }

    return capture_public_metadata(Reader(), documents)


def inputs() -> dict[str, Any]:
    posts = []
    documents = []
    articles = {}
    for index, slug in enumerate(("first", "second"), start=1):
        posts.append(
            {
                "article_id": f"local-preview-{slug}",
                "slug": f"local-preview-{slug}",
                "title": f"New {slug}",
                "excerpt": "New excerpt",
                "category": "移動",
                "date": "2026-08-29 00:00:00",
                "content_file": f"articles/{slug}.html",
            }
        )
        document: dict[str, object] = {
            "schema": "ContentDocumentV1",
            "id": index,
            "post_type": "post",
            "status": "publish",
            "slug": slug,
            "title": f"Old {slug}",
            "excerpt": "Old excerpt",
            "block_markup": f"<div><p>Old {slug}</p></div>",
            "taxonomies": {"category": [5]},
            "media_ids": [],
            "revision_id": 2,
            "modified_gmt": "2026-09-05T02:00:00Z",
        }
        document["content_sha256"] = publication._content_after_sha256(document, index)
        documents.append(document)
        articles[slug] = (
            f'<div class="raos-article-facts"></div><article class="product-profile" data-raos-product-id="PRD-{index}"><h3>New {slug}</h3><div data-raos-purchase-action>Unverified purchase</div></article>'.encode()
        )
    return {
        "snapshot": {
            "schema": "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1",
            "publication_profile": "verified-incremental",
            "origin": publication.ORIGIN,
            "publication_authority": False,
            "source": "BOUNDED_WORDPRESS_EDITOR_MCP",
            "documents": documents,
            "public_metadata": metadata_for(documents),
        },
        "source_posts": {
            "schema": "RAOS_WORDPRESS_LOCAL_PREVIEW_FIXTURE_V1",
            "seed_version": "2026-09-05.1",
            "posts": posts,
        },
        "source_articles": articles,
        "selected_slugs": frozenset({"first"}),
        "article_ids_by_slug": {"first": "article-first", "second": "article-second"},
    }


def test_selected_drafts_and_old_body_title_excerpt_are_distinct() -> None:
    data = inputs()
    before = deepcopy(data)
    result = build_mixed_preview(**data)
    assert data == before
    assert (
        result.articles["second"]
        == data["snapshot"]["documents"][1]["block_markup"].encode()
    )
    assert b"New first" in result.articles["first"]
    assert b"Unverified purchase" not in result.articles["first"]
    assert b"Old second" in result.posts and b"New second" not in result.posts
    assert result.binding["publication_authority"] is False
    assert result.binding["status"] == "NOT_VERIFIED_FOR_PUBLICATION"
    scope = result.binding["incremental_scope"]
    assert isinstance(scope, dict)
    assert scope["selected_article_ids"] == ["article-first"]
    assert scope["articles"][0]["expected_ctas"] == []
    assert b'data-raos-article-id="article-first"' in result.articles["first"]
    assert result.binding["metadata_status"] == "VERIFIED_FIELDS_ONLY"
    for row in json.loads(result.posts)["posts"]:
        assert row["date"] == "2026-08-01 09:23:00"
        assert row["category"] == "本番の分類"


def test_mixed_editorial_expectations_come_from_each_selected_or_preserved_body() -> (
    None
):
    data = inputs()
    facts = (
        "<dl><dt>記事分類</dt><dd>新稿の分類</dd>"
        "<dt>この記事で答えること</dt><dd>新稿の問い</dd></dl>"
        '<aside class="raos-disclosure"><a href="/comparison-policy/">方針</a></aside>'
    )
    data["source_articles"]["first"] += facts.encode()
    # The unselected source is deliberately different from the live snapshot.
    data["source_articles"]["second"] += facts.encode()
    result = build_mixed_preview(**data)
    rows = {
        row["article_id"]: row
        for row in result.binding["incremental_scope"]["articles"]
    }
    assert rows["article-first"]["expected_article_facts"] == {
        "content_role_labels": ["新稿の分類"],
        "primary_query_intents": ["新稿の問い"],
    }
    assert rows["article-first"]["expected_disclosure_policy_link_count"] == 1
    assert rows["article-second"]["expected_article_facts"] == {
        "content_role_labels": [],
        "primary_query_intents": [],
    }
    assert rows["article-second"]["expected_disclosure_policy_link_count"] == 0
    for slug, article_id in data["article_ids_by_slug"].items():
        expected = derive_editorial_browser_expectations(result.articles[slug].decode())
        assert all(rows[article_id][key] == value for key, value in expected.items())


def test_changed_old_snapshot_body_is_not_accepted_with_old_hash() -> None:
    data = inputs()
    data["snapshot"]["documents"][1]["block_markup"] = "Changed"
    with pytest.raises(IncrementalPublicationFailure, match="SNAPSHOT_HASH_INVALID"):
        build_mixed_preview(**data)


@pytest.mark.parametrize("selected", [frozenset(), frozenset({"new-page"})])
def test_no_empty_or_new_publication_targets(selected: frozenset[str]) -> None:
    data = inputs()
    data["selected_slugs"] = selected
    with pytest.raises(IncrementalPublicationFailure, match="PREVIEW_TARGET_INVALID"):
        build_mixed_preview(**data)


def test_unmodified_old_body_not_sanitized_to_hide_existing_problems() -> None:
    data = inputs()
    old = data["snapshot"]["documents"][1]
    old["block_markup"] = (
        '<div><img src="/old-neutral.webp" alt="Old neutral visual"></div>'
    )
    old["content_sha256"] = publication._content_after_sha256(old, old["id"])
    data["snapshot"]["public_metadata"] = metadata_for(data["snapshot"]["documents"])
    result = build_mixed_preview(**data)
    assert result.articles["second"] == old["block_markup"].encode()


def test_missing_metadata_never_reuses_new_dates_or_category_for_old_posts() -> None:
    data = inputs()
    data["snapshot"].pop("public_metadata")
    result = build_mixed_preview(**data)
    assert result.binding["metadata_status"] == "UNVERIFIED"
    assert result.binding["metadata_blockers"]
    for row in json.loads(result.posts)["posts"]:
        assert row["date"] == row["category"] == "UNVERIFIED"
    assert json.loads(result.seed_metadata)["status"] == "UNVERIFIED"


@pytest.mark.parametrize(
    "mutation", ["date", "revision", "category", "url", "sha", "timezone"]
)
def test_metadata_mismatch_cannot_claim_exact_mixed_preview(mutation: str) -> None:
    data = inputs()
    entry = data["snapshot"]["public_metadata"]["documents"]["second"]
    evidence = entry["evidence"]
    if mutation == "date":
        evidence["document"]["date"] = "2026-08-29T00:00:00"
    elif mutation == "revision":
        entry["mcp_revision_id"] = 99
    elif mutation == "category":
        evidence["document"]["categories"] = [7]
    elif mutation == "url":
        evidence["url"] = "https://other.example/wp-json/wp/v2/posts/2"
    elif mutation == "sha":
        evidence["snapshot_sha256"] = "0" * 64
    else:
        evidence["document"]["date"] = "2026-08-01T10:23:00"
        evidence["response_utf8"] = json.dumps(evidence["document"])
        evidence["snapshot_sha256"] = hashlib.sha256(
            evidence["response_utf8"].encode()
        ).hexdigest()
    with pytest.raises(IncrementalPublicationFailure, match="PREVIEW_METADATA"):
        build_mixed_preview(**data)


def with_policies() -> dict[str, Any]:
    data = inputs()
    documents = data["snapshot"]["documents"]
    policy_slugs = ("about-ad-policy", "comparison-policy", "privacy-policy")
    for index, slug in enumerate((*policy_slugs, "home"), start=10):
        row = deepcopy(documents[0])
        row.update(
            id=index,
            post_type="page",
            slug=slug,
            title=f"Old {slug}",
            excerpt=f"Old {slug} excerpt",
            block_markup=f"<p>Old {slug}</p>",
            taxonomies={},
        )
        row["content_sha256"] = publication._content_after_sha256(row, index)
        documents.append(row)
    data["snapshot"]["public_metadata"] = metadata_for(documents)
    data["source_pages"] = {
        "schema": "RAOS_WORDPRESS_PRODUCTION_POLICY_PAGES_V1",
        "seed_version": "2026-09-05.1",
        "pages": [
            {
                "content_file": f"production-pages/{slug}.html",
                "excerpt": f"New {slug} excerpt",
                "slug": slug,
                "title": f"New {slug}",
            }
            for slug in policy_slugs
        ],
    }
    data["source_page_bodies"] = {
        slug: f"<p>New production {slug}</p>".encode() for slug in policy_slugs
    }
    return data


def test_unselected_policies_and_home_baseline_are_saved_without_fake_render_claim() -> (
    None
):
    data = with_policies()
    result = build_mixed_preview(**data)
    assert result.page_bodies["privacy-policy"] == b"<p>Old privacy-policy</p>"
    assert result.baseline_pages["home"] == b"<p>Old home</p>"
    assert result.binding["home_state"] == "BASELINE_CAPTURED_NOT_RENDERED"
    assert set(result.binding["policy_states"].values()) == {
        "PRESERVED_LIVE_PRODUCTION_POLICY"
    }
    assert "home" not in {row["slug"] for row in json.loads(result.pages)["pages"]}
    assert len(json.loads(result.pages)["pages"]) == 3


def test_common_changes_are_explicit_and_never_reuse_local_policy_text() -> None:
    data = with_policies()
    data["updated_policy_slugs"] = frozenset({"comparison-policy"})
    data["home_mode"] = "shared-theme-candidate"
    result = build_mixed_preview(**data)
    assert (
        result.page_bodies["comparison-policy"]
        == data["source_page_bodies"]["comparison-policy"]
    )
    assert result.page_bodies["privacy-policy"] == b"<p>Old privacy-policy</p>"
    assert result.binding["home_state"] == "SHARED_THEME_CANDIDATE_NOT_VERIFIED"
    data["source_page_bodies"]["comparison-policy"] = (
        "<p>このローカルプレビューでは</p>".encode()
    )
    with pytest.raises(IncrementalPublicationFailure, match="POLICY_PROFILE_MIXED"):
        build_mixed_preview(**data)


@pytest.mark.parametrize("mutation", ["new_policy", "missing_home", "local_profile"])
def test_common_target_or_profile_mismatch_is_rejected(mutation: str) -> None:
    data = with_policies()
    if mutation == "new_policy":
        data["updated_policy_slugs"] = frozenset({"new-page"})
    elif mutation == "missing_home":
        data["snapshot"]["documents"].pop()
    else:
        data["source_pages"]["schema"] = "RAOS_WORDPRESS_LOCAL_PREVIEW_PAGES_V1"
    with pytest.raises(IncrementalPublicationFailure, match="PREVIEW_POLICY"):
        build_mixed_preview(**data)


@pytest.mark.parametrize("value", [None, {}, "5", [True], ["5"], [[5]], [0], [-5]])
def test_replayed_rest_taxonomies_require_positive_integer_lists(value: object) -> None:
    data = inputs()
    evidence = data["snapshot"]["public_metadata"]["documents"]["second"]["evidence"]
    evidence["document"]["categories"] = value
    evidence["response_utf8"] = json.dumps(evidence["document"])
    evidence["snapshot_sha256"] = hashlib.sha256(
        evidence["response_utf8"].encode()
    ).hexdigest()
    with pytest.raises(
        IncrementalPublicationFailure, match="PREVIEW_METADATA_MCP_MISMATCH"
    ):
        build_mixed_preview(**data)


@pytest.mark.parametrize("location", ["metadata", "documents", "evidence", "term"])
def test_metadata_records_reject_nonstring_keys(location: str) -> None:
    data = inputs()
    metadata = data["snapshot"]["public_metadata"]
    if location == "metadata":
        target = metadata
    elif location == "documents":
        target = metadata["documents"]
    elif location == "evidence":
        target = metadata["documents"]["second"]["evidence"]
    else:
        target = metadata["terms"]["category"]["5"]
    target[1] = "invalid key"
    with pytest.raises(IncrementalPublicationFailure, match="PREVIEW_METADATA"):
        build_mixed_preview(**data)


@pytest.mark.parametrize("value", [None, [], "page", {"slug": []}, {1: "page"}])
def test_policy_fixture_rows_are_runtime_validated_before_projection(
    value: object,
) -> None:
    data = with_policies()
    data["source_pages"]["pages"][0] = value
    with pytest.raises(
        IncrementalPublicationFailure, match="PREVIEW_POLICY_FIXTURE_INVALID"
    ):
        build_mixed_preview(**data)
