"""Stored-field restoration is local-only and cannot certify revised content."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts import raos_wordpress_local_restore as cli
from scripts.raos_wordpress_incremental_snapshot import capture_public_metadata
from raos.application.editorial.verified_incremental_preview_v1 import (
    build_local_restoration,
    verify_local_restoration,
)
from raos.application.editorial.verified_incremental_v1 import (
    IncrementalPublicationFailure,
    canonical,
    digest,
)
from raos.application.editorial.local_scratch_restore_v1 import (
    build_scratch_restoration,
    verify_scratch_restoration,
)
from raos.application.finance.editorial_economics_v3 import write_private_bytes


ROOT = Path(__file__).resolve().parents[2]


def snapshot():
    article_slugs = frozenset(f"article-{index}" for index in range(10))
    documents = []
    for index, slug in enumerate(
        sorted(article_slugs)
        + ["home", "about-ad-policy", "comparison-policy", "privacy-policy"],
        1,
    ):
        post_type = "post" if slug in article_slugs else "page"
        document = {
            "schema": "ContentDocumentV1",
            "id": index,
            "post_type": post_type,
            "status": "publish",
            "slug": slug,
            "title": f"Synthetic private title {slug}",
            "excerpt": "Synthetic private excerpt",
            "block_markup": ""
            if slug == "home"
            else '<p>Original body <a href="https://example.test/old">unchanged link</a></p>',
            "taxonomies": {"category": [5], "post_tag": []}
            if post_type == "post"
            else {},
            "media_ids": [],
        }
        document["content_sha256"] = digest(
            json.dumps(
                document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        )
        document.update(revision_id=2, modified_gmt="2026-09-05T02:00:00Z")
        documents.append(document)

    class Reader:
        def get(self, resource, resource_id):
            fields = "id,type,slug,status,date,date_gmt,modified,modified_gmt,categories,tags"
            if resource == "categories":
                body = {
                    "id": 5,
                    "slug": "original",
                    "name": "Original category",
                    "parent": 0,
                }
                fields = "id,slug,name,parent"
            else:
                doc = next(row for row in documents if row["id"] == resource_id)
                body = {
                    "id": doc["id"],
                    "type": doc["post_type"],
                    "slug": doc["slug"],
                    "status": "publish",
                    "date": "2026-08-01T09:00:00",
                    "date_gmt": "2026-08-01T00:00:00",
                    "modified": "2026-09-05T11:00:00",
                    "modified_gmt": "2026-09-05T02:00:00",
                }
                if doc["post_type"] == "post":
                    body.update(categories=[5], tags=[])
            raw = json.dumps(body)
            return {
                "url": f"https://kurashinoshirube.com/wp-json/wp/v2/{resource}/{resource_id}?_fields={fields}",
                "retrieved_at": "2026-09-05T02:05:00Z",
                "snapshot_sha256": digest(raw.encode()),
                "response_utf8": raw,
                "document": body,
            }

    value = {
        "schema": "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1",
        "publication_profile": "verified-incremental",
        "source": "BOUNDED_WORDPRESS_EDITOR_MCP",
        "origin": "https://kurashinoshirube.com",
        "publication_authority": False,
        "documents": documents,
        "public_metadata": capture_public_metadata(Reader(), documents),
    }
    return value, article_slugs


def prepared():
    value, slugs = snapshot()
    return build_local_restoration(value, article_slugs=slugs)


def readback(expected):
    seed = json.loads(expected.seed)
    documents = {}
    for index, (slug, document) in enumerate(seed["documents"].items(), 101):
        documents[slug] = {
            "local_id": index,
            "before_local_id": index,
            "local_slug": document["local_slug"],
            "post_type": document["post_type"],
            "status": document["status"],
            "title_sha256": digest(document["title"].encode()),
            "excerpt_sha256": digest(document["excerpt"].encode()),
            "body_sha256": document["content_sha256"],
            "dates": document["dates"],
            "taxonomies": {
                name: [
                    {key: term[key] for key in ("name", "slug", "parent")}
                    for term in rows
                ]
                for name, rows in document["taxonomies"].items()
            },
            "source_content_sha256": document["source_content_sha256"],
        }
    return {
        "schema": "RAOS_WORDPRESS_LOCAL_RESTORE_READBACK_V1",
        "publication_profile": "local-restore-rehearsal",
        "publication_authority": False,
        "preparation_sha256": digest(canonical(expected.preparation)),
        "site_url": "http://127.0.0.1:39330",
        "local_only": True,
        "new_post_count": 0,
        "documents": documents,
    }


def test_restore_preserves_all_captured_fields_including_empty_home_without_commerce_edits():
    value, slugs = snapshot()
    original = deepcopy(value)
    result = build_local_restoration(value, article_slugs=slugs)
    assert value == original
    seed = json.loads(result.seed)
    assert len(seed["documents"]) == 14
    assert len(result.bodies) == 13
    for live in value["documents"]:
        row = seed["documents"][live["slug"]]
        assert (row["title"], row["excerpt"]) == (live["title"], live["excerpt"])
        assert row["content_sha256"] == digest(live["block_markup"].encode())
        assert row["source_content_sha256"] == live["content_sha256"]
        assert row["dates"]["date"] == "2026-08-01 09:00:00"
        assert row["dates"]["modified_gmt"] == "2026-09-05 02:00:00"
        if live["slug"] == "home":
            assert row["content_file"] is None
        else:
            assert result.bodies[live["slug"]] == live["block_markup"].encode()
    assert result.preparation["publication_authority"] is False
    assert result.preparation["incremental_preview_pass"] is False
    assert result.preparation["status"] == "PREPARED_NOT_RESTORED"
    assert (
        result.preparation["snapshot_name"]
        == f"live-{digest(canonical(value).rstrip(b'\n'))}.v1.json"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_home",
        "new_page",
        "duplicate_id",
        "wrong_type",
        "body",
        "unverified_metadata",
        "authority",
    ],
)
def test_incomplete_or_tampered_snapshot_cannot_prepare_restoration(mutation):
    value, slugs = snapshot()
    if mutation == "missing_home":
        value["documents"] = [
            row for row in value["documents"] if row["slug"] != "home"
        ]
    elif mutation == "new_page":
        row = deepcopy(value["documents"][-1])
        row["slug"] = "unrequested-page"
        value["documents"].append(row)
    elif mutation == "unverified_metadata":
        value.pop("public_metadata")
    elif mutation == "authority":
        value["publication_authority"] = True
    else:
        value["documents"][0][
            {"duplicate_id": "id", "wrong_type": "post_type", "body": "block_markup"}[
                mutation
            ]
        ] = {"duplicate_id": 2, "wrong_type": "page", "body": "changed"}[mutation]
    with pytest.raises(IncrementalPublicationFailure):
        build_local_restoration(value, article_slugs=slugs)


def test_verified_restore_receipt_is_not_a_visual_or_publication_pass():
    expected = prepared()
    result = verify_local_restoration(expected, readback(expected))
    assert result["verified_document_count"] == 14
    assert result["new_post_count"] == 0
    assert result["incremental_preview_pass"] is False
    assert result["publication_authority"] is False
    assert result["production_writes"] is False
    assert result["status"] == "LOCAL_STORED_FIELDS_RESTORED"


@pytest.mark.parametrize(
    "field",
    [
        "local_id",
        "before_local_id",
        "local_slug",
        "post_type",
        "status",
        "title_sha256",
        "excerpt_sha256",
        "body_sha256",
        "dates",
        "taxonomies",
        "source_content_sha256",
    ],
)
def test_every_stored_field_and_existing_identity_is_compared(field):
    expected = prepared()
    captured = readback(expected)
    captured["documents"]["article-0"][field] = "changed"
    with pytest.raises(IncrementalPublicationFailure):
        verify_local_restoration(expected, captured)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("publication_profile", "verified-incremental"),
        ("publication_authority", True),
        ("local_only", False),
        ("site_url", "https://kurashinoshirube.com"),
        ("site_url", "http://127.0.0.1:99999"),
        ("new_post_count", 1),
        ("new_post_count", False),
        ("preparation_sha256", "0" * 64),
    ],
)
def test_restoration_readback_refuses_foreign_authority_origin_or_binding(field, value):
    expected = prepared()
    captured = readback(expected)
    captured[field] = value
    with pytest.raises(IncrementalPublicationFailure):
        verify_local_restoration(expected, captured)


def test_cli_only_prepares_and_checks_private_files_and_never_leaks_body(
    tmp_path, monkeypatch, capsys
):
    value, slugs = snapshot()
    private = tmp_path / "private"
    monkeypatch.setattr(cli, "owner_root", lambda: private)
    monkeypatch.setattr(cli, "production_article_slugs", lambda: slugs)
    name = f"live-{digest(canonical(value).rstrip(b'\n'))}.v1.json"
    write_private_bytes(private / "incremental-snapshots", name, canonical(value))
    assert cli.main(["prepare", "--snapshot-name", name]) == 0
    result = build_local_restoration(value, article_slugs=slugs)
    identity = digest(canonical(result.preparation))
    root = private / f"local-restore-{identity}"
    assert (root / "restoration-seed.v1.json").read_bytes() == result.seed
    assert cli.main(["check-inputs", "--preparation-sha256", identity]) == 0
    assert not (root / "restoration-receipt.v1.json").exists()
    write_private_bytes(
        root, "restoration-readback.v1.json", canonical(readback(result))
    )
    assert cli.main(["verify", "--preparation-sha256", identity]) == 0
    assert (
        json.loads((root / "restoration-receipt.v1.json").read_bytes())[
            "verified_document_count"
        ]
        == 14
    )
    output = capsys.readouterr()
    assert "Synthetic private" not in output.out + output.err
    write_private_bytes(root / "content", "article-0.html", b"tampered")
    assert cli.main(["check-inputs", "--preparation-sha256", identity]) == 69


def test_restoration_seed_and_shell_are_separate_local_only_existing_row_paths():
    php = (ROOT / "changes/wordpress-local-preview-v1/restore-seed.php").read_text()
    shell = (
        ROOT / "changes/wordpress-local-preview-v1/bin/wordpress_preview.sh"
    ).read_text()
    prefix = php[: php.index("foreach ($prepared as $target)")]
    for guard in (
        "RAOS_LOCAL_PREVIEW",
        "WP_HTTP_BLOCK_EXTERNAL",
        "wp_get_environment_type() !== 'local'",
        "RAOS_LOCAL_RESTORE_EXISTING_ROW_REQUIRED",
        "RAOS_LOCAL_RESTORE_CONTENT_INVALID",
    ):
        assert guard in prefix
    for forbidden in (
        "wp_insert_post(",
        "update_option(",
        "activate_plugin(",
        "switch_theme(",
        "wp_remote_",
        "strtr($content",
    ):
        assert forbidden not in php
    assert "wp_update_post(wp_slash($data), true)" in php
    assert "raos_restore_inventory() !== $before_inventory" in php
    assert "get_option($option) !== $before" in php
    assert php.index("previous-' . hash('sha256'") < php.index("wp_update_post(")
    assert "rename($current, $archive)" in php
    restore = shell.split("do_restore()", 1)[1].split("do_password()", 1)[0]
    assert "check-inputs --preparation-sha256" in restore
    assert "verify --preparation-sha256" in restore
    assert "restore-seed.php" in restore
    assert "seed sync" not in restore and "activate_theme" not in restore


def scratch_prepared():
    value, slugs = snapshot()
    baseline = build_local_restoration(value, article_slugs=slugs)
    identity = digest(canonical(baseline.preparation))
    return build_scratch_restoration(
        value,
        article_slugs=slugs,
        preparation_sha256=identity,
        environment_id=identity[:8] + "-abcdef123456",
    )


def scratch_readback(expected):
    seed = json.loads(expected.seed)
    documents = {}
    for slug, row in seed["documents"].items():
        documents[slug] = {
            "id": row["production_id"],
            "slug": slug,
            "post_type": row["post_type"],
            "status": row["status"],
            "title_sha256": digest(row["title"].encode()),
            "excerpt_sha256": digest(row["excerpt"].encode()),
            "body_sha256": row["content_sha256"],
            "dates": row["dates"],
            "taxonomy_ids": row["taxonomy_ids"],
            "taxonomies": row["taxonomies"],
            "media_ids": [],
            "content_sha256": row["source_content_sha256"],
        }
    return {
        "schema": "RAOS_WORDPRESS_SCRATCH_RESTORE_READBACK_V1",
        "publication_profile": "local-scratch-restore-rehearsal",
        "publication_authority": False,
        "production_authority": False,
        "scratch_only": True,
        "temporary_environment": True,
        "environment_id": seed["environment_id"],
        "seed_sha256": digest(expected.seed),
        "site_url": "http://scratch.wordpress.invalid",
        "original_id_set": sorted(row["id"] for row in documents.values()),
        "documents": documents,
    }


def test_scratch_receipt_verifies_original_ids_and_content_hash_not_local_prefix_ids():
    expected = scratch_prepared()
    result = verify_scratch_restoration(expected, scratch_readback(expected))
    assert result["verified_document_count"] == 14
    assert result["original_id_set"] == list(range(1, 15))
    for name in (
        "production_authority",
        "publication_authority",
        "current_preview_modified",
        "production_writes",
        "incremental_preview_pass",
        "ports_published",
    ):
        assert result[name] is False
    assert result["temporary_environment"] is result["scratch_only"] is True
    assert result["docker_project"].startswith("raos-wp-scratch-")
    assert all(
        row["local_slug"] == slug
        for slug, row in json.loads(expected.seed)["documents"].items()
    )


@pytest.mark.parametrize(
    "field", ["id", "slug", "body_sha256", "content_sha256", "taxonomy_ids", "dates"]
)
def test_scratch_rejects_any_original_identity_or_content_projection_mismatch(field):
    expected = scratch_prepared()
    observed = scratch_readback(expected)
    observed["documents"]["article-0"][field] = "changed"
    with pytest.raises(IncrementalPublicationFailure):
        verify_scratch_restoration(expected, observed)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("production_authority", True),
        ("publication_authority", True),
        ("scratch_only", False),
        ("temporary_environment", False),
        ("site_url", "http://127.0.0.1:39330"),
        ("environment_id", "another-environment"),
        ("original_id_set", [1, 2]),
    ],
)
def test_scratch_rejects_preview_or_production_environment_and_extra_documents(
    field, value
):
    expected = scratch_prepared()
    observed = scratch_readback(expected)
    observed[field] = value
    with pytest.raises(IncrementalPublicationFailure):
        verify_scratch_restoration(expected, observed)


def test_scratch_compose_has_no_ports_or_existing_volumes_and_seed_refuses_preview():
    import yaml

    compose = yaml.safe_load(
        (
            ROOT / "changes/wordpress-local-preview-v1/scratch-restore.compose.yaml"
        ).read_text()
    )
    assert set(compose["volumes"]) == {"scratch_database", "scratch_wordpress"}
    assert compose["networks"] == {
        "scratch_internal": {"driver": "bridge", "internal": True}
    }
    for service in compose["services"].values():
        assert "ports" not in service
        assert service["networks"] == ["scratch_internal"]
        assert "@sha256:" in service["image"]
    php = (
        ROOT / "changes/wordpress-local-preview-v1/scratch-restore-seed.php"
    ).read_text()
    assert "DB_NAME !== 'scratch_wordpress'" in php
    assert "defined('RAOS_LOCAL_PREVIEW')" in php
    assert "get_option('raos_scratch_restore_seed_hash', false) !== false" in php
    assert php.index("RAOS_SCRATCH_NOT_EMPTY") < php.index("wp_delete_post(")
    assert "'import_id' => $row['production_id']" in php
    assert "if ($actual_ids !== $original_ids)" in php
