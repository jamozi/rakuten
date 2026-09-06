"""Public page selection is sourced from the closed reader registry, not local guides."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import raos_reader_release_pages as pages
from .test_candidate import sample
from scripts import raos_wordpress_incremental_candidate as candidate


ROOT = Path(__file__).resolve().parents[2]


def test_hubs_are_the_fifteen_registered_pages_without_local_articles() -> None:
    hubs = pages.load_hub_pages(ROOT)
    assert {p.production_slug for p in hubs} == pages.HUB_SLUGS
    assert len(hubs) == 15
    for page in hubs:
        assert page.post_type == "page"
        assert page.block_markup == (
            '<!-- wp:shortcode -->[kurashinoshirube_reader_hub slug="'
            + page.production_slug
            + '"]<!-- /wp:shortcode -->'
        )
        assert page.taxonomies == {}
        assert "local-preview-" not in str(page.document())


def test_home_is_derived_from_the_owned_template_without_site_chrome() -> None:
    home = pages.load_home_page(ROOT)
    assert home.production_slug == "home"
    assert home.post_type == "page"
    assert "暮らしに合うものを、" in home.block_markup
    assert "wp:template-part" not in home.block_markup
    assert "<main" not in home.block_markup
    assert home.block_markup.count("<h1") == 1
    assert '[kurashinoshirube_reader_home section="categories"]' in home.block_markup


def test_local_guide_slug_cannot_be_requested_as_a_hub() -> None:
    with pytest.raises(ValueError, match="HUB_SELECTION"):
        pages.select_hub_pages(ROOT, ("dishwasher-running-cost",))


def test_duplicate_hub_selection_does_not_silently_deduplicate() -> None:
    with pytest.raises(ValueError, match="HUB_SELECTION"):
        pages.select_hub_pages(ROOT, ("categories", "categories"))


def test_explicit_home_update_binds_original_id_without_changing_policies() -> None:
    inputs = sample()
    home = pages.load_home_page(ROOT)
    manifest, artifacts, preparation = candidate.prepare_noncommercial_candidate(
        **inputs, home_article=home
    )
    original = next(
        row for row in inputs["snapshot"]["documents"] if row["slug"] == "home"
    )
    assert preparation["production_documents"]["home"]["post_id"] == original["id"]
    assert (
        preparation["production_documents"]["home"]["document"]["block_markup"]
        == home.block_markup
    )
    assert artifacts["production-home"] == home.block_markup.encode()
    assert set(manifest["shared_artifacts"]) == {"home"}
    assert {"about-ad-policy", "comparison-policy", "privacy-policy"} <= set(
        manifest["unchanged_documents"]
    )


def test_home_is_never_implicitly_selected() -> None:
    manifest, _, _ = candidate.prepare_noncommercial_candidate(**sample())
    assert "home" in manifest["unchanged_documents"]
    assert "home" not in manifest["shared_artifacts"]


def test_home_parameter_rejects_hub_page() -> None:
    with pytest.raises(ValueError, match="HOME_TARGET"):
        candidate.prepare_noncommercial_candidate(
            **sample(), home_article=pages.load_hub_pages(ROOT)[0]
        )


def test_privacy_is_separate_from_legacy_off_policy_loader() -> None:
    page = pages.load_reader_privacy_page(ROOT)
    assert page.production_slug == "privacy-policy"
    assert "30日" in page.block_markup and "90日" in page.block_markup
    assert "Google Analytics 4" in page.block_markup
    assert "<script" not in page.block_markup


def _page_only_inputs():
    from raos.application.editorial.verified_incremental_sources_v1 import (
        validate_selected_official_sources,
    )
    from scripts import raos_wordpress_publication_request as publication

    inputs = sample()
    page = pages.load_hub_pages(ROOT)[0]
    original = {
        **page.document(),
        "id": 201,
        "status": "draft",
        "revision_id": 1,
        "modified_gmt": "2026-09-01T00:00:00Z",
    }
    original["content_sha256"] = publication.sha256_json(
        {
            "schema": "ContentDocumentV1",
            "id": 201,
            "status": "draft",
            **publication.document_projection(original),
        }
    )
    inputs["snapshot"]["schema"] = "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2"
    inputs["snapshot"]["reader_page_slugs"] = [page.production_slug]
    inputs["snapshot"]["documents"].append(original)
    inputs["articles"] = []
    inputs["sources"] = validate_selected_official_sources(
        ROOT, ROOT, (), inputs["now"], allow_empty=True
    )
    inputs["reader_page_articles"] = [page]
    inputs["reader_page_targets"] = pages.reader_page_targets(
        ROOT, [page], inputs["snapshot"]
    )
    return inputs


def test_page_only_candidate_binds_draft_id_without_noop_article():
    inputs = _page_only_inputs()
    manifest, _, preparation = candidate.prepare_noncommercial_candidate(**inputs)
    slug = inputs["reader_page_articles"][0].production_slug
    assert manifest["schema"].endswith("_V2")
    assert manifest["articles"] == []
    assert manifest["reader_pages"][slug]["post_id"] == 201
    assert manifest["reader_pages"][slug]["baseline_status"] == "draft"
    assert len(manifest["unchanged_documents"]) == 14
    assert set(preparation["production_documents"]) == {slug}
    assert preparation["source_evidence"]["status"] == "NOT_REQUIRED"


def test_undeclared_draft_cannot_enter_snapshot():
    inputs = _page_only_inputs()
    inputs["snapshot"]["reader_page_slugs"] = []
    with pytest.raises(ValueError, match="SNAPSHOT"):
        candidate.prepare_noncommercial_candidate(**inputs)


def test_tampered_hub_template_cannot_be_bound_as_owned_source():
    from dataclasses import replace

    inputs = _page_only_inputs()
    page = replace(
        inputs["reader_page_articles"][0], block_markup="<p>Unexpected content</p>"
    )
    with pytest.raises(ValueError, match="READER_PAGE_SOURCE"):
        pages.reader_page_targets(ROOT, [page], inputs["snapshot"])


def test_reader_privacy_requires_explicit_conflict_free_selection():
    from argparse import Namespace

    with pytest.raises(ValueError, match="SELECTION_CONFLICT"):
        pages.selected_page_slugs(
            ROOT, Namespace(reader_privacy=True, update_policies="all")
        )


def test_declared_hub_snapshot_keeps_draft_and_skips_public_metadata(monkeypatch):
    from scripts import raos_wordpress_incremental_snapshot as snapshot_owner

    inputs = _page_only_inputs()
    rows = inputs["snapshot"]["documents"]
    by_id = {row["id"]: row for row in rows}

    class Client:
        def initialize(self):
            pass

        def call(self, name, args):
            if name == "raos-codex-site-status":
                return {}
            assert name == "raos-codex-content-get"
            return by_id[args["id"]]

    observed = []
    monkeypatch.setattr(
        snapshot_owner.publication, "list_all_documents", lambda *args, **kwargs: rows
    )
    monkeypatch.setattr(
        snapshot_owner,
        "capture_public_metadata",
        lambda reader, docs: observed.extend(docs) or {"status": "SYNTHETIC_ONLY"},
    )
    slug = inputs["reader_page_articles"][0].production_slug
    result = snapshot_owner.capture_snapshot(
        Client(),
        expected_slugs=frozenset(row["slug"] for row in rows),
        reader_page_slugs=frozenset({slug}),
    )
    assert result["schema"].endswith("_V2")
    assert result["reader_page_slugs"] == [slug]
    assert len(result["documents"]) == 15
    assert len(observed) == 14
    assert all(row["status"] == "publish" for row in observed)


def _privacy_inputs():
    from raos.application.editorial.verified_incremental_sources_v1 import (
        validate_selected_official_sources,
    )

    inputs = sample()
    inputs["articles"] = []
    inputs["sources"] = validate_selected_official_sources(
        ROOT, ROOT, (), inputs["now"], allow_empty=True
    )
    page = pages.load_reader_privacy_page(ROOT)
    inputs["reader_page_articles"] = [page]
    inputs["reader_page_targets"] = pages.reader_page_targets(
        ROOT, [page], inputs["snapshot"]
    )
    profile, raw = pages.reader_measurement_projection(ROOT)
    inputs["reader_measurement"] = profile
    inputs["reader_measurement_manifest"] = raw
    return inputs


def test_privacy_candidate_binds_exact_off_plugin_and_policy_bytes():
    inputs = _privacy_inputs()
    manifest, artifacts, preparation = candidate.prepare_noncommercial_candidate(
        **inputs
    )
    profile = manifest["reader_measurement"]
    assert profile["expected_collection_enabled"] is False
    assert (
        profile["policy_sha256"]
        == manifest["reader_pages"]["privacy-policy"]["template_sha256"]
    )
    assert (
        artifacts["reader-measurement-manifest"]
        == inputs["reader_measurement_manifest"]
    )
    assert preparation["artifact_files"]["reader-measurement-manifest"].endswith(
        ".v1.json"
    )


@pytest.mark.parametrize(
    "change", ["enable", "policy", "manifest", "unselected_privacy"]
)
def test_measurement_candidate_cannot_promote_activation_or_unbound_bytes(change):
    inputs = _privacy_inputs()
    if change == "enable":
        inputs["reader_measurement"]["expected_collection_enabled"] = True
    elif change == "policy":
        inputs["reader_measurement"]["policy_sha256"] = "1" * 64
    elif change == "manifest":
        inputs["reader_measurement_manifest"] += b" "
    else:
        inputs["reader_page_articles"] = []
        inputs["reader_page_targets"] = {}
    with pytest.raises(ValueError):
        candidate.prepare_noncommercial_candidate(**inputs)

def test_explicit_pages_must_match_frozen_candidate():
    from argparse import Namespace
    from scripts.raos_wordpress_release_workflow import validate_explicit_selection, WorkflowFailure
    frozen = {"articles": [], "shared_artifacts": {"categories": {}}}
    with pytest.raises(WorkflowFailure, match="page selection"):
        validate_explicit_selection(Namespace(reader_pages="guides", include_home=True), frozen)
    validate_explicit_selection(Namespace(reader_pages="categories"), frozen)
    validate_explicit_selection(Namespace(), frozen)


def test_explicit_home_or_theme_cannot_expand_a_frozen_candidate():
    from argparse import Namespace
    from scripts.raos_wordpress_release_workflow import validate_explicit_selection, WorkflowFailure
    frozen = {"articles": [], "shared_artifacts": {"categories": {}}}
    with pytest.raises(WorkflowFailure, match="page selection"):
        validate_explicit_selection(Namespace(include_home=True), frozen)
    with pytest.raises(WorkflowFailure, match="theme selection"):
        validate_explicit_selection(Namespace(include_theme=True), frozen)

def test_shared_candidate_cannot_omit_already_published_registered_hub():
    inputs = sample()
    inputs["home_article"] = pages.load_home_page(ROOT)
    inputs["snapshot"]["all_document_baselines"] = {
        "999": {"id": 999, "slug": "categories", "status": "publish", "post_type": "page"}
    }
    with pytest.raises(ValueError, match="PUBLISHED_HUB_SNAPSHOT"):
        candidate.prepare_noncommercial_candidate(**inputs)

def test_unselected_hub_draft_does_not_expand_shared_candidate():
    inputs = sample()
    inputs["home_article"] = pages.load_home_page(ROOT)
    inputs["snapshot"]["all_document_baselines"] = {
        "999": {"id": 999, "slug": "categories", "status": "draft", "post_type": "page"}
    }
    manifest, _, _ = candidate.prepare_noncommercial_candidate(**inputs)
    assert set(manifest["shared_artifacts"]) == {"home"}
    assert "reader_pages" not in manifest
