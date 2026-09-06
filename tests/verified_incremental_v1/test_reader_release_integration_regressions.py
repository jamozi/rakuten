"""Cross-owner regressions for the reader release path; test evidence only."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import importlib
import json

import pytest

from raos.application.editorial import verified_incremental_audit_v1 as audit_contract
from raos.application.editorial import verified_incremental_release_v1 as release
from raos.application.editorial import verified_incremental_v1 as manifest_contract
from scripts import raos_wordpress_incremental_candidate as candidate_owner
from scripts import raos_wordpress_incremental_publication as publication_port
from scripts import raos_wordpress_incremental_seo_audit as seo_audit
from tests.verified_incremental_v1 import test_candidate as candidate_fixtures
from tests.verified_incremental_v1 import test_reader_pages as reader_page_fixtures
from tests.wordpress_seo_audit_v1 import test_incremental_reader as reader_fixtures
from tests.wordpress_seo_audit_v1.test_incremental import mixed  # noqa: F401


@pytest.fixture
def reader_case(mixed, monkeypatch):  # noqa: F811
    return reader_fixtures.reader.__wrapped__(mixed, monkeypatch)


def _preparation_bytes(case):
    return (case["candidate_path"] / "candidate-preparation.v1.json").read_bytes()


def _run_public_audit(case):
    return seo_audit.run_verified_incremental_public_audit(
        **{key: value for key, value in case.items() if not key.startswith("_")}
    )


def _bind_independent_fixed_root_metadata(monkeypatch, expected_theme):
    metadata, _navigation, _files, tree = reader_fixtures.metadata_fixture()
    assert tree == expected_theme

    def build(observed_theme):
        assert observed_theme == expected_theme
        return metadata

    fixed_root_owner = importlib.import_module("raos_wordpress_incremental_seo_audit")
    monkeypatch.setattr(fixed_root_owner, "build_reader_seo_metadata", build)


def _validate_receiver(case, visible, *, post_activation):
    publication_port._validate_public_binding(
        visible,
        case["context"],
        case["original_snapshot"],
        _preparation_bytes(case),
        case["deployment_readback"]["theme"]["tree_sha256"],
        case["site_status_readback"],
        post_activation=post_activation,
    )


@pytest.mark.parametrize("post_activation", [False, True])
def test_receiver_accepts_actual_reader_seo_v2_readback(
    reader_case, monkeypatch, post_activation
):
    reader_fixtures.runtime_case(reader_case, enabled=post_activation)
    if post_activation:
        reader_case["reader_measurement_mode"] = "post-activation-readback"
    _bind_independent_fixed_root_metadata(
        monkeypatch, reader_case["deployment_readback"]["theme"]["tree_sha256"]
    )

    visible = _run_public_audit(reader_case)

    assert visible["schema"] == "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_PUBLIC_READBACK_V2"
    _validate_receiver(reader_case, visible, post_activation=post_activation)


@pytest.mark.parametrize("mutation", ["unbound", "reader_v1_schema", "integer_boolean"])
@pytest.mark.parametrize("post_activation", [False, True])
def test_receiver_rejects_unbound_or_version_mismatched_reader_readback(
    reader_case, monkeypatch, mutation, post_activation
):
    reader_fixtures.runtime_case(reader_case, enabled=post_activation)
    if post_activation:
        reader_case["reader_measurement_mode"] = "post-activation-readback"
    _bind_independent_fixed_root_metadata(
        monkeypatch, reader_case["deployment_readback"]["theme"]["tree_sha256"]
    )
    visible = _run_public_audit(reader_case)
    if mutation == "unbound":
        visible.pop("reader_measurement")
    elif mutation == "integer_boolean":
        visible["reader_measurement"]["expected_collection_enabled"] = int(post_activation)
    else:
        visible["schema"] = "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_PUBLIC_READBACK_V1"
    unsigned = {key: value for key, value in visible.items() if key != "binding_sha256"}
    visible["binding_sha256"] = publication_port.digest(
        publication_port.publication.canonical_json_bytes(unsigned)
    )

    with pytest.raises(
        publication_port.publication.PublicationFailure,
        match="PUBLIC_READER_READBACK_BINDING_INVALID|PUBLIC_READBACK_BINDING_INVALID",
    ):
        _validate_receiver(reader_case, visible, post_activation=post_activation)


def test_runtime_absent_v2_receiver_requires_exact_not_included(
    reader_case, monkeypatch
):
    _bind_independent_fixed_root_metadata(
        monkeypatch, reader_case["deployment_readback"]["theme"]["tree_sha256"]
    )
    visible = _run_public_audit(reader_case)
    assert visible["reader_measurement"] == {"state": "NOT_INCLUDED"}

    _validate_receiver(reader_case, visible, post_activation=False)


def test_runtime_absent_v2_receiver_rejects_nonexact_not_included(
    reader_case, monkeypatch
):
    _bind_independent_fixed_root_metadata(
        monkeypatch, reader_case["deployment_readback"]["theme"]["tree_sha256"]
    )
    visible = _run_public_audit(reader_case)
    visible["reader_measurement"] = {
        "state": "NOT_INCLUDED",
        "expected_collection_enabled": False,
    }
    unsigned = {key: value for key, value in visible.items() if key != "binding_sha256"}
    visible["binding_sha256"] = publication_port.digest(
        publication_port.publication.canonical_json_bytes(unsigned)
    )

    with pytest.raises(
        publication_port.publication.PublicationFailure,
        match="PUBLIC_READER_READBACK_BINDING_INVALID|PUBLIC_READBACK_BINDING_INVALID",
    ):
        _validate_receiver(reader_case, visible, post_activation=False)


def _privacy_release_case():
    source = reader_page_fixtures._privacy_inputs()
    manifest_document, artifacts, preparation = (
        candidate_owner.prepare_noncommercial_candidate(**source)
    )
    documents = {row["slug"]: row for row in source["snapshot"]["documents"]}
    inventory = {
        slug: manifest_contract.ExistingDocument(
            row["id"],
            slug,
            row["post_type"],
            row["content_sha256"],
            row["status"],
        )
        for slug, row in documents.items()
    }
    article_targets = {
        row.article_id: (
            row.production_slug,
            inventory[row.production_slug].post_id,
        )
        for row in source["portfolio"].articles
    }
    validated = manifest_contract.validate_manifest(
        manifest_document,
        inventory=inventory,
        article_targets=article_targets,
        reader_page_targets=source["reader_page_targets"],
        reader_measurement=source["reader_measurement"],
        shared_baseline_sha256={},
        article_products={},
        article_claims={},
        claim_sources={},
        source_receipt_sha256={},
        verified_image_sha256={},
        verified_cta_sha256={},
        image_article_products={},
        cta_article_products={},
        artifact_bytes=artifacts,
        now=source["now"],
    )
    article_ids = tuple(sorted(article_targets))
    scope = audit_contract.IncrementalAuditScopeV1(
        (),
        article_ids,
        article_ids,
        True,
        {},
        selected_page_slugs=("privacy-policy",),
    )
    audited = {
        **artifacts,
        "source-replay": manifest_contract.canonical(source["sources"].to_document()),
    }
    binding = audit_contract.VerifiedIncrementalAuditBindingV1(
        "5" * 64,
        validated.manifest_sha256,
        release._digest(scope.to_document()),
        release._digest(
            {key: manifest_contract.digest(raw) for key, raw in audited.items()}
        ),
        "6" * 64,
        candidate_fixtures.NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        (candidate_fixtures.NOW + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "OWNER_CONFIRMED",
    )
    return (
        manifest_document,
        {
            "validated_manifest": validated,
            "audit_binding": binding,
            "audit_scope": scope,
            "official_sources": source["sources"],
            "artifact_bytes": artifacts,
            "audit_artifact_bytes": audited,
            "inventory": inventory,
            "article_targets": article_targets,
            "reader_page_targets": source["reader_page_targets"],
            "reader_measurement": source["reader_measurement"],
            "commerce_views": {},
            "image_article_products": {},
            "cta_bindings": {},
            "expected_production_content_sha256": {
                "privacy-policy": preparation["production_documents"]["privacy-policy"][
                    "after_sha256"
                ]
            },
            "expected_shared_readback_sha256": {},
            "source_article_id_by_article_id": {},
            "now": source["now"],
        },
        source,
    )


def test_validated_reader_manifest_artifact_is_consumed_by_release():
    manifest_document, inputs, _source = _privacy_release_case()

    result = release.build_verified_incremental_release_v1(manifest_document, **inputs)

    assert (
        result.to_document()["reader_measurement"]
        == manifest_document["reader_measurement"]
    )


def test_release_still_rejects_an_extra_unbound_artifact():
    manifest_document, inputs, _source = _privacy_release_case()
    inputs["artifact_bytes"] = {
        **inputs["artifact_bytes"],
        "unexpected-test-artifact": b"not bound by the candidate manifest",
    }
    inputs["audit_artifact_bytes"] = {
        **inputs["audit_artifact_bytes"],
        "unexpected-test-artifact": b"not bound by the candidate manifest",
    }
    inputs["audit_binding"] = replace(
        inputs["audit_binding"],
        artifact_bundle_sha256=release._digest(
            {
                key: manifest_contract.digest(raw)
                for key, raw in inputs["audit_artifact_bytes"].items()
            }
        ),
    )

    with pytest.raises(
        manifest_contract.IncrementalPublicationFailure,
        match="RELEASE_ARTIFACT_SET_INVALID",
    ):
        release.build_verified_incremental_release_v1(manifest_document, **inputs)


def _candidate_valid_v1_inventory_case():
    manifest_document, release_inputs, source = _privacy_release_case()
    context = release.build_verified_incremental_release_v1(
        manifest_document, **release_inputs
    )
    original_bytes = candidate_owner.publication.canonical_json_bytes(
        source["snapshot"]
    )
    snapshot = json.loads(original_bytes)
    originals = {row["slug"]: row for row in snapshot["documents"]}
    base_contract = seo_audit.seo.load_contract()
    items = tuple(
        seo_audit.seo.InventoryItem(
            base_contract.origin + ("/" if slug == "home" else f"/{slug}/"),
            "home"
            if slug == "home"
            else ("article" if row["post_type"] == "post" else "fixed_page"),
            slug,
        )
        for slug, row in originals.items()
    )
    contract = replace(
        base_contract,
        items=items,
        content_urls=frozenset(item.url for item in items if item.role != "home"),
    )
    return context.to_document(), snapshot, originals, contract, original_bytes


def test_privacy_only_v2_candidate_accepts_candidate_valid_exact14_v1_bytes():
    envelope, snapshot, originals, contract, original_bytes = (
        _candidate_valid_v1_inventory_case()
    )

    result = seo_audit._reader_inventory(envelope, snapshot, originals, contract)

    assert result == contract
    assert candidate_owner.publication.canonical_json_bytes(snapshot) == original_bytes


@pytest.mark.parametrize("mutation", ["extra", "missing", "incomplete", "hub_request"])
def test_v1_snapshot_fallback_remains_exact_and_privacy_only(mutation):
    envelope, snapshot, originals, contract, _original_bytes = (
        _candidate_valid_v1_inventory_case()
    )
    if mutation == "extra":
        extra = deepcopy(snapshot["documents"][0])
        extra.update(id=901, slug="unexpected-retained-page", post_type="page")
        extra["content_sha256"] = seo_audit.publication.sha256_json(
            {
                "schema": "ContentDocumentV1",
                "id": extra["id"],
                "status": extra["status"],
                **seo_audit.publication.document_projection(extra),
            }
        )
        snapshot["documents"].append(extra)
        originals[extra["slug"]] = extra
    elif mutation == "missing":
        removed = snapshot["documents"].pop(0)
        originals.pop(removed["slug"])
    elif mutation == "incomplete":
        snapshot["documents"][0].pop("content_sha256")
    else:
        envelope["selected_pages"]["categories"] = {
            "kind": "hub",
            "post_id": 901,
            "baseline_status": "draft",
            "template_sha256": "1" * 64,
            "registry_sha256": "2" * 64,
            "baseline_sha256": "3" * 64,
            "artifact_key": "categories",
            "production_artifact_sha256": "1" * 64,
        }

    with pytest.raises(
        seo_audit.seo.AuditError,
        match="CORE_INVENTORY|BASELINE_INVENTORY|READER_PAGE",
    ):
        seo_audit._reader_inventory(envelope, snapshot, originals, contract)
