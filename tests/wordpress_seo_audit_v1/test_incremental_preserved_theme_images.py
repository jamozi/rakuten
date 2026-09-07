"""Bound old-body theme images; synthetic bytes only, no external requests."""

from copy import deepcopy
from dataclasses import replace
import importlib
import json

import pytest

from scripts import raos_wordpress_incremental_seo_audit as audit
from raos.application.editorial.local_scratch_theme_restore_v1 import theme_tree_sha256
from tests.wordpress_seo_audit_v1.test_incremental_reader import (
    mixed, reader, seal, old,  # noqa: F401
)


@pytest.fixture
def preserved(reader, monkeypatch):  # noqa: F811
    slug = "carry-on-suitcase-under-100-seats"
    paths = ["assets/images/home-hero.webp", "assets/images/article-suitcase-guide.webp"]
    prefix = "/wp-content/themes/kurashinoshirube-child/"
    raw_paths = [prefix + path for path in paths]
    original = next(row for row in reader["original_snapshot"]["documents"] if row["slug"] == slug)
    before = original["block_markup"]
    original["block_markup"] += "".join('<img src="' + path + '" alt="Stored diagram">' for path in raw_paths)
    original["content_sha256"] = audit._stored_content_hash(original)
    reader["original_snapshot"]["public_metadata"]["documents"][slug]["mcp_content_sha256"] = original["content_sha256"]
    reader["current_documents"][slug] = deepcopy(original)
    envelope = reader["context"].to_document()
    envelope["inventory"][slug]["content_sha256"] = original["content_sha256"]
    envelope["unchanged_documents"][slug] = original["content_sha256"]
    files = dict(reader["reader_metadata"].theme_files)
    files.update({path: old.IMAGE for path in paths})
    tree = theme_tree_sha256(files)
    reader["reader_metadata"] = audit.reader_seo_metadata(files, expected_tree=tree)
    reader["deployment_readback"]["theme"]["tree_sha256"] = tree
    envelope["expected_shared_readback_sha256"]["theme"] = tree
    preparation = json.loads((reader["candidate_path"] / "candidate-preparation.v1.json").read_bytes())
    preparation["snapshot_sha256"] = audit.digest(audit.canonical(reader["original_snapshot"]))
    seal(reader, envelope, preparation)
    url = audit.publication.ORIGIN + "/" + slug + "/"
    response = reader["transport"].responses[url]
    reader["transport"].responses[url] = replace(
        response, body=response.body.decode().replace(before, original["block_markup"]).encode(),
    )
    trusted = {audit.publication.ORIGIN + path: audit.digest(old.IMAGE) for path in raw_paths}
    for image_url in trusted:
        reader["transport"].responses[image_url] = replace(
            response, url=image_url, body=old.IMAGE, headers=(("content-type", "image/webp"),),
        )
    def expectations(expected_tree):
        assert expected_tree == tree
        home = reader["current_documents"]["home"]
        return {"title": home["title"], "description": home["excerpt"]}, trusted, {}
    monkeypatch.setattr(audit, "_theme_expectations", expectations)
    return reader, slug, raw_paths, trusted


def test_unchanged_relative_theme_images_are_bound_without_becoming_approved(preserved, monkeypatch):
    case, slug, paths, trusted = preserved
    assert case["reader_metadata"].to_document()["approved_images"] == {}
    result = audit.run_verified_incremental_public_audit(**case)
    assert result["image_evidence_sha256"] == audit.digest(audit.canonical(trusted))
    assert result["page_evidence"][slug]["state"] == "PRESERVED"
    assert result["page_evidence"][slug]["social_image_state"] == "NOT_INCLUDED"
    assert result["page_evidence"][slug]["baseline_preserved_theme_images"] == {
        path: {"state": "BASELINE_PRESERVED", "count": 1, "url": audit.publication.ORIGIN + path,
               "sha256": trusted[audit.publication.ORIGIN + path]} for path in paths
    }
    # The receiver independently rebuilds the fixed-root metadata; new evidence
    # stays in the bound V2 result without changing its approved-media contract.
    from scripts import raos_wordpress_incremental_publication as receiver
    owner = importlib.import_module("raos_wordpress_incremental_seo_audit")
    metadata = audit.reader_seo_metadata(dict(case["reader_metadata"].theme_files),
                                       expected_tree=case["reader_metadata"].theme_sha256)
    def fixed_root(expected_tree):
        assert expected_tree == metadata.theme_sha256
        return metadata
    monkeypatch.setattr(owner, "build_reader_seo_metadata", fixed_root)
    receiver._validate_public_binding(
        result, case["context"], case["original_snapshot"],
        (case["candidate_path"] / "candidate-preparation.v1.json").read_bytes(),
        metadata.theme_sha256, case["site_status_readback"],
    )


def test_updated_article_cannot_inherit_old_theme_image_preservation(preserved):
    case, slug, _paths, trusted = preserved
    originals = {row["slug"]: row for row in case["original_snapshot"]["documents"]}
    assert audit._preserved_theme_images(originals, {slug: {}}, trusted) == ({}, {})


@pytest.mark.parametrize("change", ["home", "hub", "other_article", "header_duplicate", "move_to_header", "absolute_alias", "bytes", "unknown", "og"])
def test_preserved_images_cannot_escape_the_bound_article_and_raw_occurrences(preserved, change):
    case, slug, paths, trusted = preserved
    if change == "bytes":
        image_url = next(iter(trusted))
        case["transport"].responses[image_url] = replace(case["transport"].responses[image_url], body=b"Changed pixels")
    else:
        target = {"home": "", "hub": "kitchen", "other_article": "solota-vs-rakua-mini-plus"}.get(change, slug)
        target_url = audit.publication.ORIGIN + "/" + (target + "/" if target else "")
        response = case["transport"].responses[target_url]
        markup = response.body.decode()
        image = '<img src="' + paths[0] + '" alt="Stored diagram">'
        if change == "absolute_alias":
            markup = markup.replace(paths[0], audit.publication.ORIGIN + paths[0])
        elif change == "unknown":
            markup = markup.replace("</body>", '<img src="/wp-content/themes/kurashinoshirube-child/assets/images/unknown.webp"></body>')
        elif change == "og":
            markup = markup.replace("</head>", '<meta property="og:image" content="' + audit.publication.ORIGIN + paths[0] + '"></head>')
        else:
            if change == "move_to_header":
                markup = markup.replace(image, "", 1)
            markup = markup.replace("<body>", "<body>" + image)
        case["transport"].responses[target_url] = replace(response, body=markup.encode())
    with pytest.raises(audit.seo.AuditError):
        audit.run_verified_incremental_public_audit(**case)


@pytest.mark.parametrize("release_version,report_version", [(1, 1), (1, 2), (2, 1), (2, 2)])
def test_external_baseline_receipt_requires_the_release_bound_report_version(mixed, release_version, report_version):  # noqa: F811
    snapshot = mixed["original_snapshot"]
    preparation = {
        "publication_profile": "verified-incremental",
        "source_snapshot_sha256": audit.digest(audit.canonical(snapshot)),
        "selected_slugs": [],
        "baseline_media": {"schema": audit.baseline_media.SCHEMA, "publication_authority": False,
                           "new_commerce_verified": False, "images": {}},
    }
    raw = audit.canonical(preparation)
    sha = audit.digest(raw)
    directory = audit.PRIVATE.parent / ("incremental-preview-" + sha)
    directory.mkdir(mode=0o700)
    path = directory / "preparation-binding.v1.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    report = {"schema": "RAOS_WORDPRESS_MIXED_BROWSER_AUDIT_V" + str(report_version),
              "status": "LOCAL_MIXED_BROWSER_AUDIT_PASSED", "inputs": {"preparation_binding_sha256": sha}}
    report_raw = audit.canonical(report)
    report_sha = audit.digest(report_raw)
    report_path = mixed["candidate_path"] / "audit/inputs" / (report_sha + ".bin")
    report_path.write_bytes(report_raw)
    report_path.chmod(0o600)
    envelope = {"schema": "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_RELEASE_V" + str(release_version),
                "audit_artifact_hashes": {"mixed-browser-report": report_sha}, "selected_articles": {}}
    if release_version == report_version:
        assert audit._baseline_image_expectations(envelope, mixed["candidate_path"], snapshot) == {}
    else:
        with pytest.raises(audit.seo.AuditError, match="BASELINE_IMAGE_AUDIT_INVALID"):
            audit._baseline_image_expectations(envelope, mixed["candidate_path"], snapshot)
