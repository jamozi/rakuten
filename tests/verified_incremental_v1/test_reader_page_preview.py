"""Pure reader page projections and mocked browser/PHP evidence; no WordPress state."""

from copy import deepcopy
from pathlib import Path
import json

import pytest

from raos.application.editorial.verified_incremental_preview_v1 import (
    build_mixed_preview,
)
from raos.application.editorial.verified_incremental_v1 import (
    IncrementalPublicationFailure,
    canonical,
    digest,
)
from tests.verified_incremental_v1.test_preview import with_policies, metadata_for
from scripts import raos_reader_release_pages as sources

ROOT = Path(__file__).resolve().parents[2]


def saved_home_document():
    return {
        "block_markup": "<section><h1>Saved home fixture</h1></section>\n",
        "excerpt": "Saved home fixture excerpt",
        "media_ids": [],
        "post_type": "page",
        "slug": "home",
        "taxonomies": {},
        "title": "Saved home fixture",
    }


def rehash(row):
    projection = {
        key: row[key]
        for key in (
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
    }
    row["content_sha256"] = digest(
        json.dumps(
            projection,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


def page_inputs(*, hubs=("categories",), draft=True, all_posts=True):
    data = with_policies()
    docs = data["snapshot"]["documents"]
    if all_posts:
        original = docs[0]
        for index in range(2, 10):
            slug = f"article-{index}"
            row = deepcopy(original)
            row.update(id=100 + index, slug=slug, block_markup=f"<p>Old {slug}</p>")
            rehash(row)
            docs.append(row)
            post = deepcopy(data["source_posts"]["posts"][0])
            post.update(
                slug=f"local-preview-{slug}", content_file=f"articles/{slug}.html"
            )
            data["source_posts"]["posts"].append(post)
            data["source_articles"][slug] = b"<p>Unused new draft</p>"
            data["article_ids_by_slug"][slug] = slug
    data["snapshot"]["schema"] = "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2"
    data["snapshot"]["reader_page_slugs"] = sorted(hubs)
    for index, slug in enumerate(hubs):
        row = deepcopy(docs[0])
        row.update(
            id=200 + index,
            post_type="page",
            slug=slug,
            status="draft" if draft else "publish",
            title=f"Old {slug}",
            excerpt=f"Old {slug} excerpt",
            taxonomies={},
            block_markup=f'<!-- wp:shortcode -->[kurashinoshirube_reader_hub slug="{slug}"]<!-- /wp:shortcode -->',
        )
        rehash(row)
        docs.append(row)
    data["snapshot"]["public_metadata"] = metadata_for(
        [row for row in docs if row["status"] == "publish"]
    )
    data["selected_slugs"] = frozenset()
    pages = [sources.load_reader_privacy_page(ROOT)]
    if hubs:
        pages += sources.select_hub_pages(ROOT, list(hubs))
    data["page_overrides"] = {
        "home": saved_home_document(),
        **{page.production_slug: page.document() for page in pages},
    }
    return data


def theme_only_inputs(*, schema="RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1"):
    data = with_policies()
    docs = data["snapshot"]["documents"]
    original = docs[0]
    for index in range(2, 10):
        slug = f"article-{index}"
        row = deepcopy(original)
        row.update(id=100 + index, slug=slug, block_markup=f"<p>Old {slug}</p>")
        rehash(row)
        docs.append(row)
        post = deepcopy(data["source_posts"]["posts"][0])
        post.update(
            slug=f"local-preview-{slug}", content_file=f"articles/{slug}.html"
        )
        data["source_posts"]["posts"].append(post)
        data["source_articles"][slug] = b"<p>Unused new draft</p>"
        data["article_ids_by_slug"][slug] = slug
    data["snapshot"]["schema"] = schema
    if schema.endswith("_V2"):
        data["snapshot"]["reader_page_slugs"] = ["categories"]
        hub = deepcopy(original)
        hub.update(
            id=200,
            post_type="page",
            slug="categories",
            status="publish",
            title="Saved categories",
            excerpt="Saved categories excerpt",
            taxonomies={},
            block_markup=(
                '<!-- wp:shortcode -->[kurashinoshirube_reader_hub slug="categories"]'
                "<!-- /wp:shortcode -->"
            ),
        )
        rehash(hub)
        docs.append(hub)
    home = next(
        row for row in data["snapshot"]["documents"] if row["slug"] == "home"
    )
    home.update(
        title="Saved home title",
        excerpt="Saved home excerpt",
        block_markup=(
            '<div id="ks-magazine" '
            'style="--cover:url(data:image/webp;base64,UklGRg==)">'
            '<div class="km-header"><form role="search" method="get" action="/">'
            '<input type="search" name="s"></form></div>'
            "<h1>Saved home</h1></div>"
        ),
    )
    rehash(home)
    data["snapshot"]["public_metadata"] = metadata_for(
        data["snapshot"]["documents"]
    )
    data["selected_slugs"] = frozenset()
    data["page_overrides"] = {}
    data["home_mode"] = "shared-theme-candidate"
    return data


def test_v1_default_serialization_is_unchanged():
    data = with_policies()
    result = build_mixed_preview(**data)
    assert (
        digest(result.posts)
        == "67ee29fc0159acb7e9ffdc71a1538a0b4fdfba51e67b72c4036a838924028c43"
    )
    assert (
        digest(result.pages)
        == "8f1bc9ead116d530af2b1b4db86f550eb636f5816708d1d7498fd83c8a3f765a"
    )
    assert (
        digest(result.seed_metadata)
        == "ca49feeaf88f89a67899e7c518422a73c27ce8af57ad01d910a85693e2efa09b"
    )
    assert (
        digest(canonical(result.binding))
        == "a8e5f61a7704a0ebad51dcd179b297a53b88969f81542deec6a0931c8e53c97b"
    )
    assert build_mixed_preview(**data, page_overrides={}) == result


def test_page_only_exact_sources_preserve_ten_posts_and_metadata():
    data = page_inputs(hubs=tuple(sorted(sources.HUB_SLUGS)), all_posts=True)
    before = deepcopy(data)
    result = build_mixed_preview(**data)
    assert data == before
    binding = result.binding
    assert binding["selected_slugs"] == []
    assert len(result.articles) == 10
    assert set(binding["article_states"].values()) == {"UNCHANGED_LIVE_CONTENT"}
    assert binding["reader_page_slugs"] == sorted(data["page_overrides"])
    assert binding["reader_page_documents"] == data["page_overrides"]
    assert len(binding["core_document_slugs"]) == 29
    assert binding["snapshot_document_sha256"] == {
        row["slug"]: row["content_sha256"] for row in data["snapshot"]["documents"]
    }
    for slug, page in data["page_overrides"].items():
        assert result.page_bodies[slug] == page["block_markup"].encode()
        assert binding["page_body_sha256"][slug] == digest(
            page["block_markup"].encode()
        )
    assert (
        result.page_bodies["privacy-policy"]
        == (ROOT / sources.PRIVACY_SOURCE).read_bytes()
    )
    metadata = json.loads(result.seed_metadata)
    assert metadata["status"] == "VERIFIED_FIELDS_ONLY"
    assert len(metadata["documents"]) == 14
    assert binding["metadata_blockers"] == []
    assert set(metadata["unpublished_reader_pages"]) == sources.HUB_SLUGS
    for row in metadata["unpublished_reader_pages"].values():
        assert row["publication_date"] == "NOT_VERIFIED"
        assert row["public_taxonomies"] == "NOT_APPLICABLE"
        assert "dates" not in row
    for row in data["snapshot"]["documents"]:
        if row["post_type"] == "post":
            assert result.articles[row["slug"]] == row["block_markup"].encode()
    assert {row["slug"] for row in json.loads(result.pages)["pages"]} == {
        "home",
        "about-ad-policy",
        "comparison-policy",
        "privacy-policy",
        *sources.HUB_SLUGS,
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "undeclared",
        "arbitrary",
        "post_draft",
        "home_draft",
        "private",
        "bad_id",
        "duplicate_id",
        "wrong_type",
        "duplicate_declaration",
        "unsorted",
        "hash",
    ],
)
def test_v2_snapshot_drafts_are_closed_and_hash_bound(mutation):
    data = page_inputs(hubs=("categories", "guides"))
    snapshot = data["snapshot"]
    hub = snapshot["documents"][-1]
    if mutation == "undeclared":
        snapshot["reader_page_slugs"].remove("guides")
    elif mutation == "arbitrary":
        snapshot["reader_page_slugs"] = ["categories", "unregistered"]
        hub["slug"] = "unregistered"
    elif mutation == "post_draft":
        snapshot["documents"][0]["status"] = "draft"
        rehash(snapshot["documents"][0])
    elif mutation == "home_draft":
        row = next(row for row in snapshot["documents"] if row["slug"] == "home")
        row["status"] = "draft"
        rehash(row)
    elif mutation == "private":
        hub["status"] = "private"
    elif mutation == "bad_id":
        hub["id"] = True
    elif mutation == "duplicate_id":
        hub["id"] = snapshot["documents"][0]["id"]
    elif mutation == "wrong_type":
        hub["post_type"] = "post"
    elif mutation == "duplicate_declaration":
        snapshot["reader_page_slugs"].append("guides")
    elif mutation == "unsorted":
        snapshot["reader_page_slugs"].reverse()
    else:
        hub["block_markup"] += "\n"
    if mutation != "hash":
        rehash(hub)
    with pytest.raises(IncrementalPublicationFailure, match="SNAPSHOT"):
        build_mixed_preview(**data)


@pytest.mark.parametrize(
    "mutation",
    [
        "slug",
        "post_type",
        "extra_key",
        "missing_key",
        "h1",
        "script",
        "form",
        "wrong_shortcode",
        "shortcode_newline",
        "unknown_shortcode",
        "local_guide",
    ],
)
def test_overrides_do_not_widen_page_or_markup_permissions(mutation):
    data = page_inputs()
    row = data["page_overrides"]["categories"]
    if mutation == "slug":
        row["slug"] = "guides"
    elif mutation == "post_type":
        row["post_type"] = "post"
    elif mutation == "extra_key":
        row["status"] = "publish"
    elif mutation == "missing_key":
        del row["excerpt"]
    elif mutation in {"h1", "script", "form"}:
        data["page_overrides"]["privacy-policy"]["block_markup"] = (
            f"<{mutation}>test</{mutation}>"
        )
    elif mutation == "wrong_shortcode":
        row["block_markup"] = row["block_markup"].replace(
            'slug="categories"', 'slug="guides"'
        )
    elif mutation == "shortcode_newline":
        row["block_markup"] += "\n"
    elif mutation == "unknown_shortcode":
        data["page_overrides"]["privacy-policy"]["block_markup"] = "[unreviewed]"
    else:
        row["slug"] = "local-preview-extra-guide"
        data["page_overrides"][row["slug"]] = data["page_overrides"].pop("categories")
    with pytest.raises(IncrementalPublicationFailure, match="PREVIEW_READER_PAGE"):
        build_mixed_preview(**data)


def test_published_hub_metadata_is_required_and_unselected_hub_is_preserved():
    data = page_inputs(draft=False)
    del data["page_overrides"]["categories"]
    result = build_mixed_preview(**data)
    assert "categories" in result.binding["core_document_slugs"]
    assert (
        result.page_bodies["categories"]
        == data["snapshot"]["documents"][-1]["block_markup"].encode()
    )
    del data["snapshot"]["public_metadata"]["documents"]["categories"]
    result = build_mixed_preview(**data)
    assert result.binding["metadata_status"] == "UNVERIFIED"
    assert (
        "PUBLIC_METADATA_UNVERIFIED:categories" in result.binding["metadata_blockers"]
    )


def test_unselected_draft_is_bound_but_not_claimed_as_rendered_or_published():
    data = page_inputs()
    del data["page_overrides"]["categories"]
    result = build_mixed_preview(**data)
    assert "categories" in result.binding["snapshot_document_sha256"]
    assert "categories" not in result.page_bodies
    assert "categories" not in result.binding["core_document_slugs"]
    assert "categories" not in json.loads(result.seed_metadata)["documents"]


def test_v1_home_override_and_missing_policy_fixture_use_preserved_pages():
    data = page_inputs(hubs=())
    data["snapshot"]["schema"] = "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1"
    del data["snapshot"]["reader_page_slugs"]
    del data["source_pages"], data["source_page_bodies"]
    result = build_mixed_preview(**data)
    assert (
        result.page_bodies["home"]
        == data["page_overrides"]["home"]["block_markup"].encode()
    )
    assert result.page_bodies["comparison-policy"] == b"<p>Old comparison-policy</p>"


def test_other_snapshot_objects_are_preserved_without_entering_candidate():
    data = page_inputs()
    other = {
        "id": 901,
        "post_type": "page",
        "slug": "outside-candidate",
        "content_sha256": "a" * 64,
    }
    data["snapshot"]["all_document_baselines"] = {"901": other}
    result = build_mixed_preview(**data)
    assert result.binding["all_document_baselines"] == {"901": other}
    assert "outside-candidate" not in result.binding["core_document_slugs"]
    assert (
        result.binding["all_document_baselines"]
        is not data["snapshot"]["all_document_baselines"]
    )


def test_selector_defaults_flags_and_candidate_exact_set(monkeypatch):
    from argparse import Namespace
    from scripts import raos_wordpress_incremental_preview as cli

    assert cli.page_overrides_for_preview(Namespace(), root=ROOT) == {}
    args = Namespace(
        include_home=False, reader_pages="guides,categories", reader_privacy=True
    )
    selected = cli.page_overrides_for_preview(args, root=ROOT)
    assert set(selected) == {"categories", "guides", "privacy-policy"}
    with pytest.raises(ValueError, match="READER_HOME_CONTENT_SOURCE_UNAVAILABLE"):
        cli.page_overrides_for_preview(
            Namespace(include_home=True, reader_pages=None, reader_privacy=False),
            root=ROOT,
        )
    from types import SimpleNamespace
    import raos_wordpress_incremental_publication as publication

    monkeypatch.setattr(
        publication,
        "prepare_candidate",
        lambda *_args, **_kwargs: SimpleNamespace(
            manifest={
                "reader_pages": {"travel": {}, "privacy-policy": {}},
                "shared_artifacts": {"travel": {}, "privacy-policy": {}},
            }
        ),
    )
    args.candidate = Path("/synthetic/candidate")
    assert set(cli.page_overrides_for_preview(args, root=ROOT)) == {
        "travel",
        "privacy-policy",
    }


@pytest.mark.parametrize(
    "selection",
    ["", "categories,categories", "categories, guides", "local-preview-extra-guide"],
)
def test_selector_rejects_nonexact_hub_lists(selection):
    from argparse import Namespace
    from scripts import raos_wordpress_incremental_preview as cli

    with pytest.raises(ValueError):
        cli.page_overrides_for_preview(Namespace(reader_pages=selection), root=ROOT)


def browser_owners():
    import importlib
    import sys

    path = ROOT / "changes/wordpress-local-preview-v1/browser"
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    return importlib.import_module("incremental_scope"), importlib.import_module(
        "mixed_audit_report"
    )


def inventory_for(data):
    surfaces, local = [], []
    for row in data["snapshot"]["documents"]:
        slug = row["slug"]
        kind = (
            "article"
            if row["post_type"] == "post"
            else "home"
            if slug == "home"
            else "policy"
        )
        surface = {
            "surface_id": slug,
            "kind": kind,
            "local_path": "/" if slug == "home" else f"/{slug}/",
            "production_path": "/" if slug == "home" else f"/{slug}/",
        }
        if kind == "article":
            surface.update(
                article_id=data["article_ids_by_slug"][slug],
                local_path=f"/local-preview-{slug}/",
            )
        if slug in sources.HUB_SLUGS:
            surface["kind"] = "reader_hub"
            surface.pop("production_path")
            local.append(surface)
        else:
            surfaces.append(surface)
    local.append(
        {
            "surface_id": "local-only-guide",
            "kind": "local_guide",
            "local_path": "/local-only-guide/",
        }
    )
    return {
        "surfaces": surfaces,
        "local_surfaces": local,
        "viewports": [360, 390, 768, 1024, 1440],
    }


def write_preview(tmp_path, result, *, binding=None, pages=None):
    binding = result.binding if binding is None else binding
    root = tmp_path / f"incremental-preview-{digest(canonical(binding))}"
    root.mkdir(mode=0o700)
    files = {
        "preparation-binding.v1.json": canonical(binding),
        "posts.json": result.posts,
        "pages.json": result.pages if pages is None else pages,
        "seed-metadata.v1.json": result.seed_metadata,
        **{f"articles/{slug}.html": raw for slug, raw in result.articles.items()},
        **{f"pages/{slug}.html": raw for slug, raw in result.page_bodies.items()},
        **{
            f"baseline-pages/{slug}.html": raw
            for slug, raw in result.baseline_pages.items()
        },
    }
    for name, raw in files.items():
        path = root / name
        path.parent.mkdir(mode=0o700, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o600)
    return root


def test_scope_replays_page_only_fixture_and_exact_target_set(tmp_path):
    scope, _ = browser_owners()
    data = page_inputs(hubs=tuple(sorted(sources.HUB_SLUGS)))
    result = build_mixed_preview(**data)
    root = write_preview(tmp_path, result)
    loaded = scope.load_scope(root, inventory_for(data))
    assert loaded["selected_article_ids"] == []
    assert loaded["reader_page_slugs"] == sorted(data["page_overrides"])
    assert len(loaded["core_document_slugs"]) == 29


@pytest.mark.parametrize(
    "schema",
    [
        "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1",
        "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2",
    ],
)
def test_scope_replays_hash_bound_home_for_theme_only_candidate(tmp_path, schema):
    scope, _ = browser_owners()
    data = theme_only_inputs(schema=schema)
    result = build_mixed_preview(**data)
    root = write_preview(tmp_path, result)

    loaded = scope.load_scope(root, inventory_for(data))

    assert loaded["selected_article_ids"] == []
    assert loaded["theme_only_candidate"] is True
    assert {row["slug"] for row in json.loads(result.pages)["pages"]} == {
        "home",
        "about-ad-policy",
        "comparison-policy",
        "privacy-policy",
        *({"categories"} if schema.endswith("_V2") else set()),
    }
    assert result.binding["page_body_sha256"]["home"] == result.binding[
        "baseline_page_sha256"
    ]["home"]
    assert result.page_bodies["home"] == next(
        row["block_markup"]
        for row in data["snapshot"]["documents"]
        if row["slug"] == "home"
    ).encode()
    assert result.binding.get("reader_page_documents") in (None, {})


def test_scope_replays_saved_home_for_shared_theme_with_an_article_target(tmp_path):
    scope, _ = browser_owners()
    data = theme_only_inputs()
    data["selected_slugs"] = frozenset({"first"})
    result = build_mixed_preview(**data)
    root = write_preview(tmp_path, result)

    loaded = scope.load_scope(root, inventory_for(data))

    assert loaded["selected_article_ids"] == ["article-first"]
    assert "theme_only_candidate" not in loaded
    assert result.binding["page_body_sha256"]["home"] == result.binding[
        "baseline_page_sha256"
    ]["home"]


@pytest.mark.parametrize(
    "mutation",
    [
        "mode_flag",
        "scope_flag",
        "home_body",
        "alias_id",
        "alias_target",
        "alias_external",
        "duplicate_alias_source",
    ],
)
def test_scope_rejects_rebound_theme_only_or_home_drift(tmp_path, mutation):
    scope, _ = browser_owners()
    data = theme_only_inputs()
    result = build_mixed_preview(**data)
    binding = deepcopy(result.binding)
    if mutation == "mode_flag":
        del binding["theme_only_candidate"]
    elif mutation == "scope_flag":
        del binding["incremental_scope"]["theme_only_candidate"]
    elif mutation.startswith("alias_") or mutation == "duplicate_alias_source":
        aliases = deepcopy(binding["local_route_aliases"])
        if mutation == "alias_id":
            aliases["routes"][0]["production_id"] = 999
            aliases["routes"][0]["source_path"] = "/?page_id=999"
        elif mutation == "alias_target":
            aliases["routes"][0]["local_path"] = "/local-preview-second/"
        elif mutation == "alias_external":
            aliases["routes"][0]["local_path"] = "https://example.invalid/"
        else:
            aliases["routes"][1]["source_path"] = aliases["routes"][0][
                "source_path"
            ]
        binding["local_route_aliases"] = aliases
        binding["incremental_scope"]["local_route_aliases"] = aliases
    root = write_preview(tmp_path, result, binding=binding)
    if mutation == "home_body":
        (root / "pages/home.html").write_bytes(result.page_bodies["home"] + b"\n")
    with pytest.raises((scope.ScopeFailure, IncrementalPublicationFailure)):
        scope.load_scope(root, inventory_for(data))


@pytest.mark.parametrize(
    "mutation", ["body", "title", "slug", "target_set", "draft_date", "baseline"]
)
def test_scope_rejects_rebound_page_drift(tmp_path, mutation):
    scope, _ = browser_owners()
    data = page_inputs()
    result = build_mixed_preview(**data)
    binding = deepcopy(result.binding)
    pages = json.loads(result.pages)
    if mutation in {"title", "slug"}:
        target = next(row for row in pages["pages"] if row["slug"] == "categories")
        target[mutation] = "guides" if mutation == "slug" else "Changed title"
        binding["pages_sha256"] = digest(canonical(pages))
    elif mutation == "target_set":
        binding["reader_page_slugs"].remove("categories")
    elif mutation == "draft_date":
        binding["unpublished_reader_pages"]["categories"]["publication_date"] = (
            "2026-09-06"
        )
    elif mutation == "baseline":
        binding["snapshot_document_sha256"]["categories"] = "b" * 64
    root = write_preview(
        tmp_path,
        result,
        binding=binding,
        pages=canonical(pages) if mutation in {"title", "slug"} else None,
    )
    if mutation == "body":
        (root / "pages/categories.html").write_bytes(
            result.page_bodies["categories"] + b"\n"
        )
    with pytest.raises((scope.ScopeFailure, IncrementalPublicationFailure)):
        scope.load_scope(root, inventory_for(data))


def candidate_for(data, result):
    from types import SimpleNamespace

    originals = {row["slug"]: row for row in data["snapshot"]["documents"]}
    targets, shared, artifacts, production = {}, {}, {}, {}
    for slug, page in data["page_overrides"].items():
        raw = page["block_markup"].encode()
        original = originals[slug]
        shared[slug] = {
            "key": slug,
            "sha256": digest(raw),
            "post_id": original["id"],
            "baseline_sha256": original["content_sha256"],
        }
        artifacts[slug] = raw
        production[slug] = {
            "post_id": original["id"],
            "document": {
                **page,
                "taxonomies": original["taxonomies"],
                "media_ids": original["media_ids"],
            },
        }
        if slug != "home":
            targets[slug] = {
                "kind": "reader_privacy" if slug == "privacy-policy" else "hub",
                "post_id": original["id"],
                "baseline_status": original["status"],
                "template_sha256": digest(raw),
                "registry_sha256": "f" * 64,
            }
    return SimpleNamespace(
        manifest={"reader_pages": targets, "shared_artifacts": shared, "articles": []},
        snapshot=data["snapshot"],
        artifacts=artifacts,
        preparation={"production_documents": production},
    )


@pytest.mark.parametrize(
    "mutation",
    [None, "body", "title", "status", "post_id", "target_set", "other_object"],
)
def test_report_compares_actual_candidate_page_bytes_fields_and_targets(mutation):
    _, report = browser_owners()
    data = page_inputs()
    result = build_mixed_preview(**data)
    candidate = candidate_for(data, result)
    if mutation == "body":
        candidate.artifacts["privacy-policy"] += b"\n"
    elif mutation == "title":
        candidate.preparation["production_documents"]["home"]["document"]["title"] = (
            "Drift"
        )
    elif mutation == "status":
        candidate.manifest["reader_pages"]["categories"]["baseline_status"] = "publish"
    elif mutation == "post_id":
        candidate.manifest["shared_artifacts"]["categories"]["post_id"] = 999
    elif mutation == "target_set":
        del candidate.manifest["reader_pages"]["privacy-policy"]
    elif mutation == "other_object":
        candidate.snapshot["all_document_baselines"] = {"999": {"id": 999}}
    if mutation is None:
        report.validate_reader_candidate(dict(result.binding), candidate)
    else:
        with pytest.raises(report.ReportFailure):
            report.validate_reader_candidate(dict(result.binding), candidate)


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "article",
        "reader_page",
        "content_shared",
        "production_document",
        "snapshot_fields",
    ],
)
def test_report_binds_theme_only_scope_to_an_actual_shared_theme_candidate(mutation):
    from types import SimpleNamespace

    _, report = browser_owners()
    data = theme_only_inputs(schema="RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2")
    result = build_mixed_preview(**data)
    inputs = deepcopy(result.binding)
    candidate = SimpleNamespace(
        manifest={
            "articles": [],
            "shared_artifacts": {
                "theme": {
                    "key": "theme-tree",
                    "sha256": "a" * 64,
                    "baseline_sha256": "b" * 64,
                    "post_id": None,
                }
            },
        },
        snapshot=deepcopy(data["snapshot"]),
        artifacts={},
        preparation={"production_documents": {}},
    )
    if mutation == "article":
        candidate.manifest["articles"].append({"article_id": "article-first"})
    elif mutation == "reader_page":
        candidate.manifest["reader_pages"] = {"privacy-policy": {}}
    elif mutation == "content_shared":
        candidate.manifest["shared_artifacts"]["home"] = {}
    elif mutation == "production_document":
        candidate.preparation["production_documents"]["home"] = {}
    elif mutation == "snapshot_fields":
        inputs["snapshot_reader_page_slugs"] = []

    if mutation is None:
        report.validate_theme_only_candidate(inputs, candidate)
    else:
        with pytest.raises(report.ReportFailure):
            report.validate_theme_only_candidate(inputs, candidate)


@pytest.mark.parametrize(
    "schema",
    [
        "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1",
        "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2",
    ],
)
@pytest.mark.parametrize("mutation", [None, "body", "title", "excerpt"])
def test_report_binds_saved_home_and_rejects_rehashed_fixture_drift(
    tmp_path, schema, mutation
):
    from types import SimpleNamespace

    _, report = browser_owners()
    data = theme_only_inputs(schema=schema)
    result = build_mixed_preview(**data)
    binding = deepcopy(result.binding)
    pages = json.loads(result.pages)
    home_body = result.page_bodies["home"]
    if mutation == "body":
        home_body = home_body.replace(b"Saved home", b"Rebound home")
        rebound = digest(home_body)
        binding["page_body_sha256"]["home"] = rebound
        binding["baseline_page_sha256"]["home"] = rebound
    elif mutation in {"title", "excerpt"}:
        home = next(row for row in pages["pages"] if row["slug"] == "home")
        home[mutation] = f"Rebound {mutation}"
        binding["pages_sha256"] = digest(canonical(pages))
    fixture_root = write_preview(
        tmp_path,
        result,
        binding=binding,
        pages=canonical(pages),
    )
    if mutation == "body":
        (fixture_root / "pages/home.html").write_bytes(home_body)
        (fixture_root / "baseline-pages/home.html").write_bytes(home_body)
    candidate = SimpleNamespace(
        snapshot=deepcopy(data["snapshot"]),
        manifest={"shared_artifacts": {"theme": {}}},
        preparation={"production_documents": {}},
        artifacts={},
    )

    if mutation is None:
        assert (
            report.validate_saved_home_candidate(fixture_root, binding, candidate)
            == next(
                row["block_markup"]
                for row in data["snapshot"]["documents"]
                if row["slug"] == "home"
            )
        )
    else:
        with pytest.raises(report.ReportFailure):
            report.validate_saved_home_candidate(fixture_root, binding, candidate)


@pytest.mark.parametrize(
    "schema",
    [
        "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1",
        "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2",
    ],
)
@pytest.mark.parametrize(
    "mutation", [None, "body_binding", "metadata_binding", "baseline_binding"]
)
def test_report_uses_explicit_candidate_home_and_keeps_snapshot_baseline(
    tmp_path, schema, mutation
):
    _, report = browser_owners()
    data = theme_only_inputs(schema=schema)
    data["page_overrides"] = {"home": saved_home_document()}
    result = build_mixed_preview(**data)
    binding = deepcopy(result.binding)
    pages = json.loads(result.pages)
    page_body = result.page_bodies["home"]
    baseline_body = result.baseline_pages["home"]
    candidate = candidate_for(data, result)
    candidate.manifest["shared_artifacts"]["theme"] = {
        "key": "theme-tree",
        "sha256": "a" * 64,
        "baseline_sha256": "b" * 64,
        "post_id": None,
    }
    if mutation == "body_binding":
        page_body += b"<!-- rebound -->"
        binding["page_body_sha256"]["home"] = digest(page_body)
    elif mutation == "metadata_binding":
        home = next(row for row in pages["pages"] if row["slug"] == "home")
        home["title"] = "Rebound title"
        binding["pages_sha256"] = digest(canonical(pages))
    elif mutation == "baseline_binding":
        baseline_body += b"<!-- rebound -->"
        binding["baseline_page_sha256"]["home"] = digest(baseline_body)
    fixture_root = write_preview(
        tmp_path,
        result,
        binding=binding,
        pages=canonical(pages),
    )
    (fixture_root / "pages/home.html").write_bytes(page_body)
    (fixture_root / "baseline-pages/home.html").write_bytes(baseline_body)

    def validate():
        report.validate_reader_candidate(binding, candidate)
        return report.validate_saved_home_candidate(fixture_root, binding, candidate)

    if mutation is None:
        assert validate() == saved_home_document()["block_markup"]
    else:
        with pytest.raises(report.ReportFailure):
            validate()


@pytest.mark.parametrize("mutation", [None, "home_hash", "nonhome_hash"])
def test_report_binds_each_theme_only_home_result_to_the_saved_body_projection(
    mutation,
):
    from tests.wordpress_local_preview import test_mixed_audit_report as fixtures

    _, report = browser_owners()
    inputs, results, inventory = fixtures.inputs_and_results()
    expected = "c" * 64
    inputs["theme_only_candidate"] = True
    inputs["home_body_projection_sha256"] = expected
    inputs["scope"]["selected_article_ids"] = []
    inputs["scope"]["theme_only_candidate"] = True
    for row in results:
        if row["profileSemantics"]["incrementalCommerceStatus"] == "NOT_INCLUDED":
            row["profileSemantics"]["incrementalCommerceStatus"] = (
                "UNCHANGED_NOT_REVERIFIED"
            )
        if row["surface"] == "home":
            row["homeBodyProjectionSha256"] = expected
    if mutation == "home_hash":
        next(row for row in results if row["surface"] == "home")[
            "homeBodyProjectionSha256"
        ] = "d" * 64
    elif mutation == "nonhome_hash":
        next(row for row in results if row["surface"] != "home")[
            "homeBodyProjectionSha256"
        ] = expected

    if mutation is None:
        report.validate_results(results, inventory, inputs)
    else:
        with pytest.raises(report.ReportFailure):
            report.validate_results(results, inventory, inputs)


def results_for(inventory, binding):
    _, report = browser_owners()
    rows = []
    by_article = {
        row["article_id"]: row for row in binding["incremental_scope"]["articles"]
    }
    for surface in inventory["surfaces"] + inventory["local_surfaces"]:
        for width in inventory["viewports"]:
            identifier = surface["surface_id"]
            article = by_article.get(surface.get("article_id"))
            rows.append(
                {
                    "auditResultSchema": "RAOS_WORDPRESS_LOCAL_BROWSER_RESULT_V1",
                    "surface": identifier,
                    "width": width,
                    "localPath": surface["local_path"],
                    "productionPath": surface.get("production_path"),
                    "httpStatus": 200,
                    "mandatoryCounts": {key: 0 for key in report.COUNT_FIELDS},
                    "profileSemantics": {
                        "publicationProfile": "verified-incremental",
                        "linkMode": "standard-api",
                        "preparationBindingSha256": "a" * 64,
                        "incrementalCommerceStatus": "UNCHANGED_NOT_REVERIFIED"
                        if article
                        else "NOT_AN_ARTICLE",
                        "legacyMediaDisplayProjection": article["display_projection"]
                        if article
                        else None,
                    },
                    "screenshot": f"/synthetic/local-preview-{identifier}-{width}.png",
                    "zoomScreenshot": f"/synthetic/local-preview-{identifier}-zoom200.png"
                    if width == 390
                    else None,
                }
            )
    return rows


def test_report_requires_real_29_surface_coverage_plus_five_widths_and_zoom():
    _, report = browser_owners()
    from scripts.raos_wordpress_browser_plan import browser_plan

    data = page_inputs(hubs=tuple(sorted(sources.HUB_SLUGS)))
    binding = build_mixed_preview(**data).binding
    inventory = inventory_for(data)
    inputs = {
        **binding,
        "scope": binding["incremental_scope"],
        "preparation_binding_sha256": "a" * 64,
    }
    promoted = report.bind_reader_inventory(inventory, inputs)
    assert len(promoted["surfaces"]) == 29
    assert [row["surface_id"] for row in promoted["local_surfaces"]] == [
        "local-only-guide"
    ]
    rows = results_for(inventory, binding)
    assert len(report.validate_results(rows, inventory, inputs)) == 30 * 6
    inputs["browser_plan"] = browser_plan(inventory)
    inputs["browser_plan"]["surface_ids"].remove("categories")
    with pytest.raises(report.ReportFailure):
        report.validate_results(
            [row for row in rows if row["surface"] != "categories"], inventory, inputs
        )
    del inputs["browser_plan"]
    for missing in [("categories", 1024), ("home", 390)]:
        with pytest.raises(report.ReportFailure):
            report.validate_results(
                [row for row in rows if (row["surface"], row["width"]) != missing],
                inventory,
                inputs,
            )
    rows[1]["zoomScreenshot"] = None
    with pytest.raises(report.ReportFailure):
        report.validate_results(rows, inventory, inputs)
    inventory["local_surfaces"] = [
        row for row in inventory["local_surfaces"] if row["surface_id"] != "categories"
    ]
    with pytest.raises(report.ReportFailure):
        report.bind_reader_inventory(inventory, inputs)


PHP_IMAGE = "wordpress:7.1.0-php8.3-apache@sha256:8801a1239d7ba9fb340a5fc5ba0bf7f8d3652adbd64893e3fba7992ba618108e"

PHP_ALIAS_FIXTURE = r"""
$input = json_decode(file_get_contents('php://stdin'), true, 64, JSON_THROW_ON_ERROR);
class WP_Post {
    public $ID, $post_type, $post_status, $post_name, $permalink;
    function __construct($row) { foreach ($row as $key => $value) { $this->$key = $value; } }
}
function get_post($id) {
    $row = $GLOBALS['input']['posts'][(string) $id] ?? null;
    return is_array($row) ? new WP_Post($row) : null;
}
function home_url($path) { return 'http://127.0.0.1:28952' . $path; }
function get_permalink($post) { return $post->permalink; }
$GLOBALS['input'] = $input;
$source = file_get_contents('/repo/changes/wordpress-local-preview-v1/mu-plugins/raos-local-preview.php');
$start = strpos($source, 'function raos_local_preview_alias_sorted_keys(');
$end = strpos($source, 'function raos_local_preview_route_alias_redirect(', $start);
eval(substr($source, $start, $end - $start));
$target = raos_local_preview_route_alias_target(
    $input['state'], $input['hash'], $input['method'], $input['uri']
);
echo json_encode(['target' => $target], JSON_THROW_ON_ERROR);
"""


@pytest.mark.parametrize(
    "mutation",
    [None, "unknown", "query", "method", "hash", "external", "duplicate", "object"],
)
def test_local_alias_redirect_is_exact_binding_and_object_scoped(mutation):
    import shutil
    import subprocess

    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Pinned PHP image is required; never pulls")
    inspected = subprocess.run(
        [docker, "image", "inspect", PHP_IMAGE], capture_output=True, timeout=15
    )
    if inspected.returncode:
        pytest.skip("Pinned PHP image absent; never pulls")
    payload = theme_only_php_payload()
    aliases = deepcopy(payload["binding"]["local_route_aliases"])
    state_routes, posts = [], {}
    for index, row in enumerate(aliases["routes"], start=900):
        state_routes.append({**row, "local_post_id": index})
        local_slug = (
            f"local-preview-{row['production_slug']}"
            if row["kind"] == "post_slug"
            else row["production_slug"]
        )
        posts[str(index)] = {
            "ID": index,
            "post_type": "post" if row["kind"] == "post_slug" else "page",
            "post_status": "publish",
            "post_name": local_slug,
            "permalink": f"http://127.0.0.1:28952{row['local_path']}",
        }
    bound_hash = "a" * 64
    state = {
        "schema": "RAOS_WORDPRESS_LOCAL_ROUTE_ALIAS_STATE_V1",
        "publication_profile": "verified-incremental",
        "publication_authority": False,
        "preparation_binding_sha256": bound_hash,
        "routes": state_routes,
    }
    uri = aliases["routes"][0]["source_path"]
    method = "GET"
    if mutation == "unknown":
        uri = "/unknown/"
    elif mutation == "query":
        uri += "?unexpected=1"
    elif mutation == "method":
        method = "POST"
    elif mutation == "hash":
        bound_hash = "b" * 64
    elif mutation == "external":
        aliases["routes"][0]["local_path"] = "https://example.invalid/"
        state["routes"][0]["local_path"] = "https://example.invalid/"
    elif mutation == "duplicate":
        aliases["routes"][1]["source_path"] = aliases["routes"][0]["source_path"]
        state["routes"][1]["source_path"] = state["routes"][0]["source_path"]
    elif mutation == "object":
        posts["900"]["post_name"] = "different"
    binding = {
        "schema": "RAOS_WORDPRESS_MIXED_PREVIEW_PREPARATION_V1",
        "publication_profile": "verified-incremental",
        "publication_authority": False,
        "status": "NOT_VERIFIED_FOR_PUBLICATION",
        "local_route_aliases": aliases,
    }
    result = subprocess.run(
        [
            docker, "run", "--pull=never", "--rm", "-i", "--network", "none",
            "--read-only", "--cap-drop=ALL", "--security-opt", "no-new-privileges",
            "--mount", f"type=bind,src={ROOT},dst=/repo,readonly",
            "--entrypoint", "php", PHP_IMAGE, "-r", PHP_ALIAS_FIXTURE,
        ],
        input=json.dumps(
            {"state": state, "binding": binding, "hash": bound_hash,
             "method": method, "uri": uri, "posts": posts}
        ),
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    target = json.loads(result.stdout)["target"]
    assert target == (
        "http://127.0.0.1:28952/local-preview-first/"
        if mutation is None
        else None
    )

def test_seed_updates_the_current_request_rewrite_before_seeding_local_guides():
    source = (ROOT / "changes/wordpress-local-preview-v1/seed.php").read_text()
    rewrite = source.index(
        "$wp_rewrite->set_permalink_structure('/%postname%/');"
    )
    guide_seed = source.index("raos_local_reader_guides_seed(")
    assert rewrite < guide_seed
    assert "update_option('permalink_structure', '/%postname%/');" not in source


PHP_PAGE_FIXTURE = r"""
$input = json_decode(file_get_contents('php://stdin'), true, 64, JSON_THROW_ON_ERROR);
define('OBJECT', 'OBJECT');
class WP_CLI { static function error($message) { throw new RuntimeException($message); } }
class WP_Post {
    public $ID, $post_type, $post_name, $post_title, $post_excerpt, $post_content;
    function __construct($row) { foreach ($row as $key => $value) { $this->$key = $value; } }
}
function wp_strip_all_tags($text) { return strip_tags($text); }
function apply_filters($name, $value, ...$args) { return $value; }
function wp_allowed_protocols() { return ['http', 'https', 'mailto']; }
require '/usr/src/wordpress/wp-includes/compat.php';
require '/usr/src/wordpress/wp-includes/class-wp-token-map.php';
foreach (glob('/usr/src/wordpress/wp-includes/html-api/*.php') as $path) {
    if (basename($path) !== 'class-wp-html-processor.php') { require_once $path; }
}
require '/usr/src/wordpress/wp-includes/kses.php';
function raos_local_preview_has_only_reviewed_https_links($content) { return true; }
function get_stylesheet_directory() {
    return '/repo/changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child';
}
function add_filter($name, $callback) { $GLOBALS['date_filter'] = $callback; }
function wp_slash($value) {
    return is_array($value) ? array_map('wp_slash', $value) : (is_string($value) ? addslashes($value) : $value);
}
function fixture_unslash($value) {
    return is_array($value) ? array_map('fixture_unslash', $value) : (is_string($value) ? stripslashes($value) : $value);
}
function get_page_by_path($slug, ...$args) { return $GLOBALS['fixture_existing'][$slug] ?? null; }
function wp_insert_post($data, ...$args) {
    $data = fixture_unslash($data);
    $data = ($GLOBALS['date_filter'])($data);
    $id = $data['ID'] ?? 900 + count($GLOBALS['writes']);
    $GLOBALS['writes'][] = $data;
    $GLOBALS['stored'][$id] = $data;
    return $id;
}
function get_post_field($key, $id, ...$args) { return $GLOBALS['stored'][$id][$key] ?? ''; }
function is_wp_error($value) { return false; }
$source = file_get_contents('/repo/changes/wordpress-local-preview-v1/seed.php');
$start = strpos($source, 'function raos_local_preview_reader_hub_slugs(');
$end = strpos($source, "\n$" . "mode = getenv", $start);
eval(substr($source, $start, $end - $start));
$mixed_binding = $input['binding'];
$mixed_metadata = $input['metadata'];
$fixture = $input['posts'];
$page_fixture = $input['pages'];
$page_content_root = '/tmp/fixture';
mkdir($page_content_root . '/pages', 0700, true);
foreach ($input['bodies'] as $slug => $body) {
    file_put_contents($page_content_root . '/pages/' . $slug . '.html', $body);
}
$preview_author_id = 77;
$reader_page_mode = $input['reader_mode'];
$GLOBALS['fixture_existing'] = [];
foreach ($input['existing'] as $slug => $id) {
    $GLOBALS['fixture_existing'][$slug] = new WP_Post(['ID' => $id, 'post_type' => 'page', 'post_name' => $slug]);
}
$GLOBALS['writes'] = [];
try {
    $theme_only_candidate = raos_local_preview_theme_only_candidate($mixed_binding);
    $shared_theme_home = raos_local_preview_shared_theme_home($mixed_binding);
    $managed_reader_pages = $reader_page_mode
        ? raos_local_preview_reader_scope($mixed_binding, $mixed_metadata)
        : array();
    $local_route_aliases = raos_local_preview_route_aliases(
        $mixed_binding, $mixed_metadata, $fixture, $page_fixture
    );
    $start = strpos($source, "if ($" . "mixed_metadata !== null) {\n    // Core normally");
    $end = strpos($source, "$" . "article_path_replacements = array();", $start);
    eval(substr($source, $start, $end - $start));
    echo json_encode(['valid' => true, 'writes' => $GLOBALS['writes'], 'heads' => $mixed_policy_heads, 'aliases' => $local_route_aliases], JSON_THROW_ON_ERROR);
} catch (RuntimeException $error) {
    echo json_encode(['valid' => false, 'error' => $error->getMessage(), 'writes' => $GLOBALS['writes']], JSON_THROW_ON_ERROR);
}
"""


@pytest.fixture(scope="module")
def php_fixture_runner():
    import shutil
    import subprocess

    docker = shutil.which("docker")
    if docker is None:
        pytest.skip(
            "Mocked PHP fixture requires the existing pinned image; never pulls"
        )
    inspected = subprocess.run(
        [docker, "image", "inspect", PHP_IMAGE], capture_output=True, timeout=15
    )
    if inspected.returncode:
        pytest.skip("Pinned PHP image absent; never pulls")

    def run(payload):
        result = subprocess.run(
            [
                docker,
                "run",
                "--pull=never",
                "--rm",
                "-i",
                "--network",
                "none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt",
                "no-new-privileges",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=16m",
                "--mount",
                f"type=bind,src={ROOT},dst=/repo,readonly",
                "--entrypoint",
                "php",
                PHP_IMAGE,
                "-r",
                PHP_PAGE_FIXTURE,
            ],
            input=canonical(payload).decode(),
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stderr == "", result.stderr
        return json.loads(result.stdout)

    return run


def php_payload(*, existing_hub=True, published=False, hubs=("categories",)):
    data = page_inputs(draft=not published, hubs=hubs)
    result = build_mixed_preview(**data)
    payload = {
        "binding": deepcopy(result.binding),
        "metadata": json.loads(result.seed_metadata),
        "pages": json.loads(result.pages),
        "posts": json.loads(result.posts),
        "bodies": {slug: raw.decode() for slug, raw in result.page_bodies.items()},
        "reader_mode": "reader_page_slugs" in result.binding,
        "existing": {
            "home": 51,
            "about-ad-policy": 52,
            "comparison-policy": 53,
            "privacy-policy": 54,
        },
    }
    if existing_hub:
        payload["existing"]["categories"] = 55
    return payload


def theme_only_php_payload(*, schema="RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1"):
    data = theme_only_inputs(schema=schema)
    result = build_mixed_preview(**data)
    return {
        "binding": deepcopy(result.binding),
        "metadata": json.loads(result.seed_metadata),
        "pages": json.loads(result.pages),
        "posts": json.loads(result.posts),
        "bodies": {slug: raw.decode() for slug, raw in result.page_bodies.items()},
        "reader_mode": "reader_page_slugs" in result.binding,
        "existing": {
            "home": 51,
            "about-ad-policy": 52,
            "comparison-policy": 53,
            "privacy-policy": 54,
        },
    }


def shared_theme_article_php_payload():
    data = theme_only_inputs()
    data["selected_slugs"] = frozenset({"first"})
    result = build_mixed_preview(**data)
    return {
        "binding": deepcopy(result.binding),
        "metadata": json.loads(result.seed_metadata),
        "pages": json.loads(result.pages),
        "posts": json.loads(result.posts),
        "bodies": {slug: raw.decode() for slug, raw in result.page_bodies.items()},
        "reader_mode": False,
        "existing": {
            "home": 51,
            "about-ad-policy": 52,
            "comparison-policy": 53,
            "privacy-policy": 54,
        },
    }


@pytest.mark.parametrize(
    "existing_hub,published", [(True, False), (False, False), (True, True)]
)
def test_php_seed_reuses_local_hubs_without_fabricating_publication_dates(
    php_fixture_runner, existing_hub, published
):
    payload = php_payload(existing_hub=existing_hub, published=published)
    result = php_fixture_runner(payload)
    assert result["valid"], result
    writes = {row["post_name"]: row for row in result["writes"]}
    assert len(writes) == 5
    assert set(result["heads"]) == {
        "about-ad-policy",
        "comparison-policy",
        "privacy-policy",
    }
    hub = writes["categories"]
    assert hub["post_status"] == "publish"
    assert hub.get("ID") == (55 if existing_hub else None)
    assert hub["post_content"] == payload["bodies"]["categories"]
    if published:
        assert hub["post_date"] == "2026-08-01 09:23:00"
    else:
        assert all(
            key not in hub
            for key in (
                "post_date",
                "post_date_gmt",
                "post_modified",
                "post_modified_gmt",
            )
        )
    assert writes["home"]["ID"] == 51
    assert writes["privacy-policy"]["post_date"] == "2026-08-01 09:23:00"


@pytest.mark.parametrize(
    "schema",
    [
        "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1",
        "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2",
    ],
)
def test_php_seed_reuses_exact_saved_home_for_theme_only_preview(
    php_fixture_runner, schema
):
    payload = theme_only_php_payload(schema=schema)

    result = php_fixture_runner(payload)

    assert result["valid"], result
    writes = {row["post_name"]: row for row in result["writes"]}
    assert set(writes) == {
        "home",
        "about-ad-policy",
        "comparison-policy",
        "privacy-policy",
        *({"categories"} if schema.endswith("_V2") else set()),
    }
    assert writes["home"]["ID"] == 51
    assert writes["home"]["post_content"] == payload["bodies"]["home"]
    assert writes["home"]["post_title"] == "Saved home title"
    assert writes["home"]["post_excerpt"] == "Saved home excerpt"
    assert "data:image/webp;base64," in writes["home"]["post_content"]


def test_php_v1_theme_only_home_preserves_backslashes(php_fixture_runner):
    payload = theme_only_php_payload()
    payload["bodies"]["home"] = payload["bodies"]["home"].replace(
        "Saved home", r"Saved \\ home"
    )
    rebound = digest(payload["bodies"]["home"].encode())
    payload["binding"]["page_body_sha256"]["home"] = rebound
    payload["binding"]["baseline_page_sha256"]["home"] = rebound

    result = php_fixture_runner(payload)

    assert result["valid"], result
    home = next(row for row in result["writes"] if row["post_name"] == "home")
    assert home["post_content"] == payload["bodies"]["home"]


@pytest.mark.parametrize(
    "mutation", [None, "id", "source", "target", "external", "duplicate"]
)
def test_php_seed_binds_local_route_aliases_to_saved_metadata(
    php_fixture_runner, mutation
):
    payload = theme_only_php_payload()
    aliases = deepcopy(payload["binding"]["local_route_aliases"])
    if mutation == "id":
        aliases["routes"][0]["production_id"] = 999
    elif mutation == "source":
        aliases["routes"][0]["source_path"] = "/different/"
    elif mutation == "target":
        aliases["routes"][0]["local_path"] = "/local-preview-different/"
    elif mutation == "external":
        aliases["routes"][0]["local_path"] = "https://example.invalid/"
    elif mutation == "duplicate":
        aliases["routes"][1]["source_path"] = aliases["routes"][0][
            "source_path"
        ]
    if mutation is not None:
        payload["binding"]["local_route_aliases"] = aliases
        payload["binding"]["incremental_scope"]["local_route_aliases"] = aliases

    result = php_fixture_runner(payload)

    assert result["valid"] is (mutation is None), result
    if mutation is None:
        assert result["aliases"] == payload["binding"]["local_route_aliases"][
            "routes"
        ]
    else:
        assert result["error"] == "RAOS_WORDPRESS_PREVIEW_ROUTE_ALIAS_INVALID"


def test_php_seed_reuses_saved_home_for_shared_theme_with_article_target(
    php_fixture_runner,
):
    payload = shared_theme_article_php_payload()
    result = php_fixture_runner(payload)
    assert result["valid"], result
    writes = {row["post_name"]: row for row in result["writes"]}
    assert writes["home"]["post_content"] == payload["bodies"]["home"]


@pytest.mark.parametrize(
    "mutation", ["home_body", "home_script", "home_mode", "missing_home"]
)
def test_php_theme_only_home_permission_remains_exact_and_existing_only(
    php_fixture_runner, mutation
):
    payload = theme_only_php_payload()
    if mutation == "home_body":
        payload["bodies"]["home"] += "<!-- rebound -->"
        payload["binding"]["page_body_sha256"]["home"] = digest(
            payload["bodies"]["home"].encode()
        )
    elif mutation == "home_script":
        payload["bodies"]["home"] += "<script>alert(1)</script>"
        rebound = digest(payload["bodies"]["home"].encode())
        payload["binding"]["page_body_sha256"]["home"] = rebound
        payload["binding"]["baseline_page_sha256"]["home"] = rebound
    elif mutation == "home_mode":
        payload["binding"]["home_mode"] = "preserve-live-baseline"
    else:
        del payload["existing"]["home"]

    result = php_fixture_runner(payload)

    assert result["valid"] is False, result
    assert result["error"].startswith("RAOS_WORDPRESS_PREVIEW_")


@pytest.mark.parametrize(
    "mutation",
    [
        "home_bytes",
        "home_script",
        "policy_h1",
        "policy_form",
        "policy_script",
        "hub_newline",
        "wrong_hub_shortcode",
        "policy_shortcode",
        "title",
        "slug",
        "missing_policy",
        "fake_date",
        "extra_metadata",
        "undeclared",
    ],
)
def test_php_seed_rejects_page_permission_or_metadata_widening(
    php_fixture_runner, mutation
):
    payload = php_payload()
    target = (
        "home"
        if mutation.startswith("home")
        else "categories"
        if mutation in {"hub_newline", "wrong_hub_shortcode"}
        else "privacy-policy"
    )
    markup = payload["bodies"][target]
    if mutation == "home_bytes":
        markup += "<!-- unbound template change -->"
    elif mutation in {"home_script", "policy_script"}:
        markup += "<script>alert(1)</script>"
    elif mutation == "policy_h1":
        markup += "<h1>Forbidden</h1>"
    elif mutation == "policy_form":
        markup += '<form><input name="value"></form>'
    elif mutation == "hub_newline":
        markup += "\n"
    elif mutation == "wrong_hub_shortcode":
        markup = markup.replace('slug="categories"', 'slug="guides"')
    elif mutation == "policy_shortcode":
        markup += "[arbitrary_shortcode]"
    elif mutation in {"title", "slug"}:
        row = next(row for row in payload["pages"]["pages"] if row["slug"] == target)
        row[mutation] = "changed"
    elif mutation == "missing_policy":
        del payload["existing"]["privacy-policy"]
    elif mutation == "fake_date":
        payload["binding"]["unpublished_reader_pages"]["categories"][
            "publication_date"
        ] = "2026-09-06"
    elif mutation == "extra_metadata":
        payload["metadata"]["documents"]["categories"] = {
            "dates": {"date": "2026-09-06"}
        }
    elif mutation == "undeclared":
        payload["binding"]["snapshot_reader_page_slugs"] = []
    payload["bodies"][target] = markup
    if mutation != "home_bytes":
        payload["binding"]["reader_page_documents"][target]["block_markup"] = markup
        payload["binding"]["page_body_sha256"][target] = digest(markup.encode())
    scope, _ = browser_owners()
    for key in scope.READER_BINDING_FIELDS:
        payload["metadata"][key] = deepcopy(payload["binding"][key])
    result = php_fixture_runner(payload)
    assert result["valid"] is False, result
    assert result["error"].startswith("RAOS_WORDPRESS_PREVIEW_")


def test_closed_hub_registry_matches_public_authoring_helper():
    from raos.application.editorial.verified_incremental_preview_v1 import (
        READER_HUB_SLUGS,
    )

    assert READER_HUB_SLUGS == sources.HUB_SLUGS
    assert len(READER_HUB_SLUGS) == 15


def test_report_v2_counts_actual_hubs_and_declares_five_local_guides_outside_candidate(
    tmp_path, monkeypatch
):
    from tests.wordpress_local_preview import test_mixed_audit_report as fixtures
    from scripts.raos_wordpress_browser_plan import browser_plan

    _, report = browser_owners()
    inputs, raw, screenshots, _ = fixtures.evidence(tmp_path, monkeypatch)
    monkeypatch.setattr(report, "LIGHTHOUSE", fixtures.owner.LIGHTHOUSE)
    inventory = json.loads(report.INVENTORY.read_bytes())
    results = report.parse_results(raw)
    template = next(
        row for row in results if row["surface"] == "home" and row["width"] == 360
    )
    core = {
        "home" if row["kind"] == "home" else row["production_path"].strip("/")
        for row in inventory["surfaces"]
    }
    local_guides = [f"local-only-guide-{index}" for index in range(5)]
    extras = [
        {"surface_id": slug, "kind": "local_guide", "local_path": f"/{slug}/"}
        for slug in local_guides
    ]
    inventory["local_surfaces"].extend(extras)
    for surface in inventory["reader_hubs"] + extras:
        identifier = surface["surface_id"]
        for width in inventory["viewports"]:
            row = deepcopy(template)
            row.update(
                surface=identifier,
                width=width,
                localPath=surface["local_path"],
                productionPath=None,
                screenshot=f"/synthetic/local-preview-{identifier}-{width}.png",
                zoomScreenshot=f"/synthetic/local-preview-{identifier}-zoom200.png"
                if width == 390
                else None,
            )
            results.append(row)
    inputs.update(
        reader_page_slugs=sorted(sources.HUB_SLUGS),
        core_document_slugs=sorted(core | sources.HUB_SLUGS),
    )
    inputs["browser_plan"] = browser_plan(
        report.bind_reader_inventory(inventory, inputs)
    )
    inputs["scope"].update(
        reader_page_slugs=inputs["reader_page_slugs"],
        core_document_slugs=inputs["core_document_slugs"],
    )
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_bytes(canonical(inventory))
    monkeypatch.setattr(report, "INVENTORY", inventory_path)
    for name in report.validate_results(results, inventory, inputs):
        (screenshots / name).write_bytes(b"\x89PNG\r\n\x1a\nSynthetic PNG fixture")
    assembled = report.assemble_report(
        inputs=inputs,
        raw_result=b"### Result\n" + canonical(results),
        artifact_directory=screenshots,
        started_at="2026-09-05T02:00:00+00:00",
        captured_at="2026-09-05T02:05:00+00:00",
    )
    assert assembled["schema"] == report.SCHEMA_V2
    assert len(assembled["core_document_slugs"]) == 29
    assert len(assembled["screenshots"]) == len(results) // 5 * 6
    assert set(local_guides) <= set(assembled["outside_candidate_surface_ids"])
    assert not set(local_guides) & set(assembled["core_document_slugs"])


def test_php_all_fifteen_hubs_keep_policy_head_contract_and_public_metadata(
    php_fixture_runner,
):
    payload = php_payload(hubs=tuple(sorted(sources.HUB_SLUGS)))
    result = php_fixture_runner(payload)
    assert result["valid"], result
    assert len(result["writes"]) == 19
    assert len(payload["metadata"]["documents"]) == 14
    assert set(result["heads"]) == {
        "about-ad-policy",
        "comparison-policy",
        "privacy-policy",
    }
    assert len(payload["binding"]["core_document_slugs"]) == 29
