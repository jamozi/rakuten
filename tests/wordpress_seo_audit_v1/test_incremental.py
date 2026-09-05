"""Synthetic mixed-scope readback: no live credentials, content, or network."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import raos_wordpress_incremental_seo_audit as audit
from raos.application.editorial.verified_incremental_release_v1 import (
    SCHEMA,
    VerifiedIncrementalReleaseV1,
    canonical_json_bytes,
)

NOW = datetime(2026, 9, 5, 2, tzinfo=UTC)
STAMP = "2026-09-05T02:00:00Z"
THEME = "b" * 64
MANIFEST = "a" * 64
IMAGE = b"recorded image response, not a product photograph"
spec = importlib.util.spec_from_file_location(
    "incremental_seo_legacy_fixture", Path(__file__).with_name("test_runtime.py")
)
assert spec and spec.loader
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


class Metadata:
    def __init__(self, documents: dict[str, Any]) -> None:
        self.documents = documents
        self.retrieved_at = STAMP

    def get(self, resource: str, identifier: int) -> dict[str, Any]:
        row = next(row for row in self.documents.values() if row["id"] == identifier)
        modified = row["modified_gmt"].removesuffix("Z")
        record = {
            "id": identifier,
            "type": row["post_type"],
            "slug": row["slug"],
            "status": "publish",
            "date_gmt": "2026-08-29T00:00:00",
            "date": "2026-08-29T09:00:00",
            "modified_gmt": modified,
            "modified": (
                datetime.fromisoformat(modified) + timedelta(hours=9)
            ).isoformat(),
            "categories": [],
            "tags": [],
        }
        raw = audit.canonical(record)
        return {
            "document": record,
            "response_utf8": raw.decode(),
            "snapshot_sha256": audit.digest(raw),
            "retrieved_at": self.retrieved_at,
            "url": f"{audit.publication.ORIGIN}/wp-json/wp/v2/{resource}/{identifier}?_fields=id,type,slug,status,date,date_gmt,modified,modified_gmt,categories,tags",
        }


def site_status() -> dict[str, Any]:
    owner = audit.publication
    return {
        "schema": "RAOSWordPressSiteStatusV1",
        "origin": owner.ORIGIN,
        "wordpress_version_compatible": True,
        "mcp_adapter_version": "0.6.1",
        "mcp_adapter_version_compatible": True,
        "plugin_version": owner.EXPECTED_PLUGIN_VERSION,
        "plugin_runtime_revision": owner.EXPECTED_PLUGIN_RUNTIME_REVISION,
        "writes_enabled": {
            key: True
            for key in (
                "global",
                "draft",
                "content_apply",
                "theme_apply",
                "plugin_apply",
            )
        },
        "theme": {
            "slug": "kurashinoshirube-child",
            "exists": True,
            "active": True,
            "version": "1.5.1",
            "runtime_version": "1.5.1",
            "runtime_revision": "c" * 64,
        },
        "yoast": {
            "plugin_slug": "wordpress-seo",
            "installed": True,
            "active": True,
            "version": owner.EXPECTED_YOAST_VERSION,
            "version_exact": True,
            "options": owner.EXPECTED_YOAST_OPTIONS,
            "settings_fingerprint": owner.EXPECTED_YOAST_SETTINGS_FINGERPRINT,
            "settings_exact": True,
        },
        "apply_authorization": {
            "mode": "approval_scoped_lease",
            "default": False,
            "single_use": True,
            "lease_ttl_seconds": owner.EXPECTED_APPLY_LEASE_TTL_SECONDS,
        },
        "server": {
            "endpoint": owner.EDITOR_ENDPOINT,
            "publish_tool_exposed": False,
            "delete_tool_exposed": False,
            "media_write_tool_exposed": False,
            "proposal_review_ttl_seconds": owner.EXPECTED_PROPOSAL_REVIEW_TTL_SECONDS,
        },
        "measurement": {
            "plugin_active": False,
            "collection_enabled": False,
            "raw_event_tool_exposed": False,
        },
    }


@pytest.fixture
def mixed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    contract = audit.seo.load_contract()
    originals = {}
    for number, item in enumerate(contract.items, 1):
        slug = "home" if item.role == "home" else item.url.split("/")[-2]
        old_body = f'<div><h2>Original {number}</h2><p>Stored old article {number}.</p><a href="https://example.com/spec-{number}">Official specification</a></div>'
        row = {
            "schema": "ContentDocumentV1",
            "id": number,
            "slug": slug,
            "status": "publish",
            "post_type": "post" if item.role == "article" else "page",
            "title": f"Original title {number}",
            "excerpt": f"Original description {number}",
            "block_markup": old_body,
            "taxonomies": {},
            "media_ids": [],
            "revision_id": number + 100,
            "modified_gmt": STAMP,
        }
        row["content_sha256"] = audit.publication._content_after_sha256(row, number)
        originals[slug] = row
    selected = contract.items[10].url.split("/")[-2]
    current = deepcopy(originals)
    target = current[selected]
    target.update(
        title="Revised candidate title",
        excerpt="Revised candidate description",
        block_markup="<div><h2>Verified new article</h2><p>No unverified purchase link or photo.</p></div>",
        revision_id=1001,
    )
    target["content_sha256"] = audit.publication._content_after_sha256(
        target, target["id"]
    )
    metadata = audit.capture_public_metadata(
        Metadata(originals), list(originals.values())
    )
    snapshot = {
        "schema": "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1",
        "publication_profile": "verified-incremental",
        "origin": contract.origin,
        "documents": list(originals.values()),
        "public_metadata": metadata,
        "deployment_status": {"theme": {"tree_sha256": "c" * 64}},
    }
    preparation = {
        "schema": "RAOS_WORDPRESS_INCREMENTAL_CANDIDATE_PREPARATION_V1",
        "publication_profile": "verified-incremental",
        "manifest_sha256": MANIFEST,
        "snapshot_sha256": audit.digest(audit.canonical(snapshot)),
        "production_documents": {selected: {"document": target}},
    }
    prep_raw = audit.canonical(preparation)
    private = tmp_path / "candidates"
    candidate = private / MANIFEST
    candidate.mkdir(parents=True, mode=0o700)
    (candidate / "audit").mkdir(mode=0o700)
    (candidate / "audit/inputs").mkdir(mode=0o700)
    prep_path = candidate / "candidate-preparation.v1.json"
    prep_path.write_bytes(prep_raw)
    prep_path.chmod(0o600)
    monkeypatch.setattr(audit, "PRIVATE", private)
    envelope = {
        "schema": SCHEMA,
        "publication_profile": "verified-incremental",
        "link_mode": "standard-api",
        "publication_authority": False,
        "measurement_collection_enabled": False,
        "owner_approval_required": True,
        "manifest_sha256": MANIFEST,
        "audit_artifact_hashes": {
            "candidate-preparation": audit.digest(prep_raw),
            "live-snapshot": audit.digest(audit.canonical(snapshot)),
        },
        "inventory": {slug: {} for slug in originals},
        "unchanged_documents": {
            slug: row["content_sha256"]
            for slug, row in originals.items()
            if slug != selected
        },
        "expected_production_content_sha256": {selected: target["content_sha256"]},
        "expected_shared_readback_sha256": {"theme": THEME},
        "evaluated_at": STAMP,
        "expires_at": "2026-09-05T02:15:00Z",
        "monetization_state": "NOT_INCLUDED",
    }
    responses = legacy.valid_responses.__wrapped__(contract)
    for url, response in list(responses.items()):
        responses[url] = replace(response, observed_at=STAMP)
    images = {}
    for item in contract.items:
        slug = "home" if item.role == "home" else item.url.split("/")[-2]
        wanted = current[slug]
        image = audit.publication.EXPECTED_SOCIAL_IMAGE_URL
        if item.role == "article":
            image = (
                contract.origin
                + "/wp-content/themes/kurashinoshirube-child/assets/images/"
                + audit.publication.EXPECTED_ARTICLE_SOCIAL_IMAGE_BY_SLUG[slug]
            )
        images[image] = audit.digest(IMAGE)
        markup = legacy.html(item, contract.required_types[item.role])
        markup = markup.replace("Valid title", wanted["title"]).replace(
            "Valid description", wanted["excerpt"]
        )
        markup = markup.replace(audit.publication.EXPECTED_SOCIAL_IMAGE_URL, image)
        markup = markup.replace("2026-08-30T00:00:00Z", STAMP)
        markup = markup.replace(
            "Public content",
            "<h1>"
            + wanted["title"]
            + '</h1><div class="entry-content wp-block-post-content">'
            + wanted["block_markup"]
            + "</div>",
        )
        if item.role == "home":
            markup = markup.replace(
                "</body>",
                "".join(
                    f'<a href="{entry.url}">Existing article</a>'
                    for entry in contract.items
                    if entry.role == "article"
                )
                + "</body>",
            )
        responses[item.url] = replace(responses[item.url], body=markup.encode())
        responses[image] = audit.seo.HttpResponse(
            image, 200, (("Content-Type", "image/webp"),), IMAGE, STAMP
        )
    monkeypatch.setattr(
        audit,
        "_theme_expectations",
        lambda tree: (
            {
                "title": current["home"]["title"],
                "description": current["home"]["excerpt"],
            },
            images,
        ),
    )
    return {
        "context": VerifiedIncrementalReleaseV1(canonical_json_bytes(envelope)),
        "candidate_path": candidate,
        "original_snapshot": snapshot,
        "current_documents": current,
        "now": NOW,
        "deployment_readback": {
            "schema": "RAOSWordPressDeploymentStatusV1",
            "origin": contract.origin,
            "theme": {
                "active": True,
                "slug": "kurashinoshirube-child",
                "tree_sha256": THEME,
            },
        },
        "site_status_readback": site_status(),
        "transport": legacy.FakeTransport(responses),
        "public_metadata_reader": Metadata(current),
    }


def test_mixed_one_new_nine_old_passes_without_new_content_global_expectations(
    mixed: dict[str, Any],
) -> None:
    binding = audit.run_verified_incremental_public_audit(**mixed)
    assert binding["status"] == "PUBLIC_READBACK_PASSED"
    assert binding["core_document_count"] == 14
    assert binding["monetization_state"] == "NOT_INCLUDED"
    assert (
        sum(row["state"] == "UPDATED" for row in binding["page_evidence"].values()) == 1
    )
    assert binding["snapshot_sha256"] == audit.digest(
        audit.canonical(mixed["original_snapshot"])
    )


def test_expired_release_can_be_read_back_but_not_renewed(
    mixed: dict[str, Any],
) -> None:
    mixed["now"] = NOW + timedelta(minutes=16)
    mixed["public_metadata_reader"].retrieved_at = "2026-09-05T02:16:00Z"
    for url, response in list(mixed["transport"].responses.items()):
        mixed["transport"].responses[url] = replace(
            response, observed_at="2026-09-05T02:16:00Z"
        )
    assert (
        audit.run_verified_incremental_public_audit(**mixed)["status"]
        == "PUBLIC_READBACK_PASSED"
    )


@pytest.mark.parametrize(
    "change,code",
    [
        ("same-count-wrong-title", "CANDIDATE_OR_BASELINE_HEAD_MISMATCH"),
        ("body", "PUBLIC_BODY_OR_COMMERCE_MISMATCH"),
        ("link", "PUBLIC_BODY_OR_COMMERCE_MISMATCH"),
        ("photo", "PUBLIC_BODY_OR_COMMERCE_MISMATCH"),
        ("hidden", "PUBLIC_BODY_OR_COMMERCE_MISMATCH"),
        ("date", "JSONLD_DATES_MISMATCH"),
        ("duplicate-canonical", "PUBLIC_SEO_FAILED"),
        ("review-schema", "PUBLIC_SEO_FAILED"),
    ],
)
def test_live_html_tamper_is_rejected(
    mixed: dict[str, Any], change: str, code: str
) -> None:
    transport = mixed["transport"]
    item = audit.seo.load_contract().items[1]
    response = transport.responses[item.url]
    text = response.body.decode()
    if change == "same-count-wrong-title":
        text = text.replace("Original title 2", "Another title 2")
    elif change == "body":
        text = text.replace("Stored old article 2.", "Changed old article 2.")
    elif change == "link":
        text = text.replace(
            "https://example.com/spec-2", "https://example.com/wrong-product"
        )
    elif change == "photo":
        text = text.replace(
            "</div></body>",
            '<img src="https://kurashinoshirube.com/unverified.webp" alt="Wrong product"></div></body>',
        )
    elif change == "hidden":
        text = text.replace(
            "<p>Stored old article 2.", "<p hidden>Stored old article 2."
        )
    elif change == "date":
        text = text.replace("2026-08-29T00:00:00Z", "2026-08-28T00:00:00Z")
    elif change == "duplicate-canonical":
        text = text.replace(
            "</head>", f'<link rel="canonical" href="{item.url}"></head>'
        )
    else:
        text = text.replace('"@type": "Article"', '"@type": "Review"')
    transport.responses[item.url] = replace(response, body=text.encode())
    with pytest.raises(audit.seo.AuditError, match=code):
        audit.run_verified_incremental_public_audit(**mixed)


@pytest.mark.parametrize(
    "field", ["title", "id", "slug", "block_markup", "revision_id"]
)
def test_unselected_mcp_document_changes_are_rejected(
    mixed: dict[str, Any], field: str
) -> None:
    row = next(
        row for slug, row in mixed["current_documents"].items() if slug != "home"
    )
    row[field] = 9999 if field in {"id", "revision_id"} else "tampered"
    with pytest.raises(audit.seo.AuditError):
        audit.run_verified_incremental_public_audit(**mixed)


def test_snapshot_and_preparation_are_bound_to_audited_bytes(
    mixed: dict[str, Any],
) -> None:
    mixed["original_snapshot"]["documents"][0]["title"] = "Changed original"
    with pytest.raises(audit.seo.AuditError, match="AUDITED_INPUT_CHANGED"):
        audit.run_verified_incremental_public_audit(**mixed)


def test_changed_theme_cannot_reuse_content_receipts(mixed: dict[str, Any]) -> None:
    mixed["deployment_readback"]["theme"]["tree_sha256"] = "f" * 64
    with pytest.raises(audit.seo.AuditError, match="DEPLOYMENT_THEME_MISMATCH"):
        audit.run_verified_incremental_public_audit(**mixed)


def test_missing_or_enabled_measurement_is_not_reported_as_off(
    mixed: dict[str, Any],
) -> None:
    mixed["site_status_readback"]["measurement"]["collection_enabled"] = True
    with pytest.raises(audit.publication.PublicationFailure, match="SITE_NOT_READY"):
        audit.run_verified_incremental_public_audit(**mixed)
    del mixed["site_status_readback"]
    with pytest.raises(audit.seo.AuditError, match="SITE_STATUS_MISSING"):
        audit.run_verified_incremental_public_audit(**mixed)


def test_stale_http_response_cannot_be_used_as_current_readback(
    mixed: dict[str, Any],
) -> None:
    url = audit.seo.load_contract().items[0].url
    mixed["transport"].responses[url] = replace(
        mixed["transport"].responses[url], observed_at="2026-09-05T01:54:00Z"
    )
    with pytest.raises(audit.seo.AuditError, match="HTTP_OBSERVATION_EXPIRED"):
        audit.run_verified_incremental_public_audit(**mixed)


def test_image_same_url_changed_bytes_rejected(mixed: dict[str, Any]) -> None:
    url = audit.publication.EXPECTED_SOCIAL_IMAGE_URL
    mixed["transport"].responses[url] = replace(
        mixed["transport"].responses[url], body=b"different image"
    )
    with pytest.raises(audit.seo.AuditError, match="THEME_IMAGE_BYTES_MISMATCH"):
        audit.run_verified_incremental_public_audit(**mixed)


@pytest.mark.parametrize(
    "change, code",
    [
        ("set-cookie", "PUBLIC_MEASUREMENT_OFF_MISMATCH"),
        ("measurement-script", "PUBLIC_MEASUREMENT_OFF_MISMATCH"),
        ("home-route", "HOME_ARTICLE_ROUTES_MISSING"),
        ("single-quoted-image", "PUBLIC_IMAGE_BROKEN"),
    ],
)
def test_shared_home_public_runtime_is_checked(
    mixed: dict[str, Any], change: str, code: str
) -> None:
    url = audit.seo.load_contract().items[0].url
    response = mixed["transport"].responses[url]
    if change == "set-cookie":
        response = replace(
            response, headers=(*response.headers, ("Set-Cookie", "synthetic=1"))
        )
    elif change == "measurement-script":
        response = replace(
            response,
            body=response.body.replace(
                b"</body>",
                b'<script id="kurashinoshirube-measurement-v1"></script></body>',
            ),
        )
    elif change == "home-route":
        response = replace(
            response,
            body=response.body.replace(
                b"carry-on-suitcase-comparison/", b"wrong-same-count/"
            ),
        )
    else:
        image = "https://kurashinoshirube.com/missing.webp"
        response = replace(
            response,
            body=response.body.replace(
                b"</body>", f"<img src='{image}' alt='Missing'></body>".encode()
            ),
        )
        mixed["transport"].responses[image] = audit.seo.HttpResponse(
            image, 404, (), b"", STAMP
        )
    mixed["transport"].responses[url] = response
    with pytest.raises(audit.seo.AuditError, match=code):
        audit.run_verified_incremental_public_audit(**mixed)


def test_old_rest_evidence_does_not_become_current_by_reusing_mcp_hash(
    mixed: dict[str, Any],
) -> None:
    mixed["public_metadata_reader"].retrieved_at = "2026-09-04T02:00:00Z"
    with pytest.raises(audit.seo.AuditError, match="HTTP_OBSERVATION_EXPIRED"):
        audit.run_verified_incremental_public_audit(**mixed)


def test_remote_baseline_image_hash_is_loaded_only_through_audited_preparation(
    mixed: dict[str, Any],
) -> None:
    url = "https://thumbnail.image.rakuten.co.jp/@0_mall/example/cabinet/a.jpg?_ex=300x300"
    selected = "solota-vs-rakua-mini-plus"
    snapshot = deepcopy(mixed["original_snapshot"])
    old = next(
        row
        for row in snapshot["documents"]
        if row["post_type"] == "post" and row["slug"] != selected
    )
    old["block_markup"] += '<img src="' + url + '" alt="Existing photo">'
    preparation = {
        "publication_profile": "verified-incremental",
        "source_snapshot_sha256": audit.digest(audit.canonical(snapshot)),
        "selected_slugs": [selected],
        "baseline_media": {
            "schema": audit.baseline_media.SCHEMA,
            "publication_authority": False,
            "new_commerce_verified": False,
            "images": {
                audit.digest(url.encode()): {
                    "source_url": url,
                    "content_sha256": "d" * 64,
                }
            },
        },
    }
    raw = audit.canonical(preparation)
    prep_sha = audit.digest(raw)
    directory = audit.PRIVATE.parent / f"incremental-preview-{prep_sha}"
    directory.mkdir(mode=0o700)
    path = directory / "preparation-binding.v1.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    report = {
        "schema": "RAOS_WORDPRESS_MIXED_BROWSER_AUDIT_V1",
        "status": "LOCAL_MIXED_BROWSER_AUDIT_PASSED",
        "inputs": {"preparation_binding_sha256": prep_sha},
    }
    raw_report = audit.canonical(report)
    report_sha = audit.digest(raw_report)
    report_path = mixed["candidate_path"] / "audit/inputs" / f"{report_sha}.bin"
    report_path.write_bytes(raw_report)
    report_path.chmod(0o600)
    envelope = {
        "audit_artifact_hashes": {"mixed-browser-report": report_sha},
        "selected_articles": {selected: {}},
    }
    assert audit._baseline_image_expectations(
        envelope, mixed["candidate_path"], snapshot
    ) == {url: "d" * 64}
    changed = deepcopy(snapshot)
    old_index = next(
        index
        for index, row in enumerate(changed["documents"])
        if row["slug"] == old["slug"]
    )
    changed["documents"][old_index]["block_markup"] = old["block_markup"].replace(
        "a.jpg", "wrong.jpg"
    )
    with pytest.raises(audit.seo.AuditError, match="BASELINE_IMAGE_AUDIT_INVALID"):
        audit._baseline_image_expectations(envelope, mixed["candidate_path"], changed)
    report_path.write_bytes(json.dumps({"status": "PASS"}).encode())
    with pytest.raises(audit.seo.AuditError, match="BASELINE_IMAGE_AUDIT_CHANGED"):
        audit._baseline_image_expectations(envelope, mixed["candidate_path"], snapshot)


def test_known_toc_and_hand_off_are_only_allowed_rendered_additions() -> None:
    stored = '<div><h2 id="decision">Question</h2><p>Answer.</p></div>'
    rendered = '<html><head></head><body><div class="entry-content"><div><nav class="raos-article-toc"><a href="#decision">Question</a></nav><div class="raos-editorial-v2__main"><h2 id="decision" tabindex="-1">Question</h2><p>Answer.</p><p class="raos-back-to-toc-wrap"><a href="#toc">Back</a></p><p class="raos-contextual-guide">Known runtime guide</p></div></div></div></body></html>'
    assert len(audit.verify_rendered_body(stored, rendered)) == 64
    with pytest.raises(audit.seo.AuditError, match="PUBLIC_BODY_OR_COMMERCE_MISMATCH"):
        audit.verify_rendered_body(stored, rendered.replace("Answer.", "Wrong answer."))


def test_arbitrary_same_count_product_and_cta_are_not_equivalent() -> None:
    stored = '<article data-raos-product-id="P1"><a href="https://example.com" data-raos-cta-id="CTA1" data-raos-product-id="P1">Purchase</a><img src="https://kurashinoshirube.com/p.webp" alt="P1" width="300" height="300"></article>'
    live = (
        '<html><body><div class="entry-content">'
        + stored.replace("P1", "P2")
        + "</div></body></html>"
    )
    with pytest.raises(audit.seo.AuditError, match="PUBLIC_BODY_OR_COMMERCE_MISMATCH"):
        audit.verify_rendered_body(stored, live)
