"""Synthetic 29-page SEO readback; no live requests, regeneration or publication."""

from copy import deepcopy
from dataclasses import replace
from html import escape
import json
from pathlib import Path
import re

import pytest

from scripts import raos_wordpress_incremental_seo_audit as audit
from raos.application.editorial.local_scratch_theme_restore_v1 import theme_tree_sha256
from raos.application.editorial.verified_incremental_v1 import READER_HUB_SLUGS
from tests.wordpress_seo_audit_v1 import test_incremental as old
from tests.wordpress_seo_audit_v1.test_incremental import mixed  # noqa: F401, F811

NAV = "assets/editorial-navigation.v3.json"
ROOT = Path(__file__).resolve().parents[2]
THEME_ROOT = ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"


def metadata_fixture(*, media=None):
    assert hasattr(audit, "reader_seo_metadata"), "explicit approved media metadata factory is required"
    navigation = json.loads((THEME_ROOT / NAV).read_bytes())
    navigation["media_assets"] = media or []
    raw = audit.canonical(navigation)
    files = {
        NAV: raw,
        "style.css": b"Version: 1\n",
        "functions.php": ('<?php\nconst KURASHINOSHIRUBE_EDITORIAL_NAVIGATION_SHA256 = "' + audit.digest(raw) + '";\n').replace('"', "'").encode(),
    }
    for asset in media or []:
        files[asset["path"]] = old.IMAGE
    expected = theme_tree_sha256(files)
    return audit.reader_seo_metadata(files, expected_tree=expected), navigation, files, expected


def absent_images(markup):
    markup = re.sub(r'<meta (?:property="og:image[^"]*"|name="twitter:image") [^>]*>\n?', "", markup)
    markup = markup.replace('content="summary_large_image"', 'content="summary"')
    match = re.search(r'(<script type="application/ld\+json">)(.*?)(</script>)', markup, re.S)
    graph = json.loads(match[2])
    for node in graph["@graph"]:
        node.pop("image", None)
    return markup[:match.start(2)] + json.dumps(graph) + markup[match.end(2):]


def reader_article_graph(markup, item, navigation):
    """Current theme: registered section and the fixture's published category hub."""
    if item.role != "article":
        return markup
    article = next(row for row in navigation["articles"] if row["article_code"] == item.identifier)
    categories = [hub for hub in navigation["reader_navigation"]["hubs"]
                  if hub["kind"] == "category" and article["article_id"] in hub["article_ids"]]
    assert len(categories) == 1
    category = categories[0]
    match = re.search(r'(<script type="application/ld\+json">)(.*?)(</script>)', markup, re.S)
    graph = json.loads(match[2])
    nodes = {node["@type"]: node for node in graph["@graph"]}
    nodes["Article"]["articleSection"] = category["label"]
    crumbs = nodes["BreadcrumbList"]["itemListElement"]
    crumbs[-1]["position"] = 3
    crumbs.insert(1, {"@type": "ListItem", "item": audit.publication.ORIGIN + "/" + category["slug"] + "/",
                      "name": category["label"], "position": 2})
    return markup[:match.start(2)] + json.dumps(graph) + markup[match.end(2):]


def hub_html(hub, navigation, documents):
    cards = []
    if hub["kind"] in {"categories", "purposes"}:
        kind = "category" if hub["kind"] == "categories" else "purpose"
        for child in navigation["reader_navigation"]["hubs"]:
            if child["kind"] == kind:
                cards.append(
                    '<li><a class="raos-guide-card raos-taxonomy-card" href="/' + child["slug"] + '/">'
                    '<span class="raos-guide-card__title" role="heading" aria-level="3">' + escape(child["label"]) + '</span>'
                    '<span class="raos-guide-card__excerpt">' + escape(child["description"]) + '</span>'
                    '<span class="raos-guide-card__date">' + str(len(child["article_ids"])) + '記事を読む <span aria-hidden="true">→</span></span></a></li>'
                )
        grid = "raos-guide-grid raos-taxonomy-grid"
    else:
        for row in navigation["articles"]:
            if row["article_id"] not in hub["article_ids"]:
                continue
            document = documents[row["production_slug"]]
            categories = [category for category in navigation["reader_navigation"]["hubs"]
                          if category["kind"] == "category" and row["article_id"] in category["article_ids"]]
            assert len(categories) == 1
            cards.append(
                '<li><a class="raos-guide-card" href="/' + row["production_slug"] + '/">'
                '<span class="raos-article-category">' + escape(categories[0]["label"] + " / " + row["content_role_label"]) + '</span>'
                '<span class="raos-guide-card__title" role="heading" aria-level="3">' + escape(document["title"]) + '</span>'
                '<span class="raos-guide-card__excerpt">' + escape(document["excerpt"]) + '</span>'
                '<span class="raos-guide-card__date">更新 2026年9月5日</span></a></li>'
            )
        grid = "raos-guide-grid"
    return '<div class="raos-reader-hub"><p>' + escape(hub["description"]) + '</p><h2>条件から読み始める</h2><ul class="' + grid + '">' + "".join(cards) + '</ul></div>'


def seal(case, envelope, preparation):
    raw = audit.canonical(preparation)
    (case["candidate_path"] / "candidate-preparation.v1.json").write_bytes(raw)
    envelope["audit_artifact_hashes"]["candidate-preparation"] = audit.digest(raw)
    envelope["audit_artifact_hashes"]["live-snapshot"] = audit.digest(audit.canonical(case["original_snapshot"]))
    case["context"] = audit.VerifiedIncrementalReleaseV1(old.canonical_json_bytes(envelope))


@pytest.fixture
def reader(mixed, monkeypatch):  # noqa: F811
    metadata, navigation, files, tree = metadata_fixture()
    originals = {row["slug"]: deepcopy(row) for row in mixed["original_snapshot"]["documents"]}
    current = deepcopy(originals)
    preparation = json.loads((mixed["candidate_path"] / "candidate-preparation.v1.json").read_bytes())
    preparation["production_documents"] = {}
    envelope = mixed["context"].to_document()
    envelope.update(schema="RAOS_WORDPRESS_VERIFIED_INCREMENTAL_RELEASE_V2",
                    selected_articles={}, selected_pages={})
    envelope["expected_production_content_sha256"] = {}
    envelope["expected_shared_readback_sha256"]["theme"] = tree
    registry = audit.digest(audit.manifest_canonical(navigation["reader_navigation"]))
    for index, hub in enumerate(navigation["reader_navigation"]["hubs"], 101):
        slug = hub["slug"]
        body = '<!-- wp:shortcode -->[kurashinoshirube_reader_hub slug="' + slug + '"]<!-- /wp:shortcode -->'
        baseline = {
            "schema": "ContentDocumentV1", "id": index, "slug": slug, "post_type": "page",
            "status": "draft", "title": hub["label"], "excerpt": hub["description"],
            "block_markup": body, "taxonomies": {}, "media_ids": [],
        }
        baseline["content_sha256"] = audit.digest(audit.canonical(baseline).rstrip(b"\n"))
        baseline.update(revision_id=index + 100, modified_gmt=old.STAMP)
        originals[slug] = baseline
        current[slug] = {**baseline, "status": "publish", "revision_id": index + 200}
        current[slug]["content_sha256"] = audit.publication._content_after_sha256(current[slug], index)
        preparation["production_documents"][slug] = {"document": current[slug]}
        envelope["expected_production_content_sha256"][slug] = current[slug]["content_sha256"]
        envelope["selected_pages"][slug] = {
            "kind": "hub", "post_id": index, "baseline_status": "draft",
            "template_sha256": audit.digest(body.encode()), "registry_sha256": registry,
            "baseline_sha256": baseline["content_sha256"], "artifact_key": slug,
            "production_artifact_sha256": audit.digest(body.encode()),
        }
    snapshot = mixed["original_snapshot"]
    snapshot.update(schema="RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2",
                    source="BOUNDED_WORDPRESS_EDITOR_MCP", publication_authority=False,
                    reader_page_slugs=sorted(READER_HUB_SLUGS), documents=list(originals.values()))
    envelope["inventory"] = {slug: {
        "post_id": row["id"], "slug": slug, "post_type": row["post_type"],
        "status": row["status"], "content_sha256": row["content_sha256"],
    } for slug, row in originals.items()}
    envelope["unchanged_documents"] = {
        slug: row["content_sha256"] for slug, row in originals.items() if slug not in READER_HUB_SLUGS
    }
    preparation["snapshot_sha256"] = audit.digest(audit.canonical(snapshot))
    contract = audit.seo.load_contract()
    items = contract.items + tuple(audit.seo.InventoryItem(
        contract.origin + "/" + hub["slug"] + "/", "fixed_page", hub["slug"]
    ) for hub in navigation["reader_navigation"]["hubs"])
    extended = replace(contract, items=items, content_urls=frozenset(item.url for item in items if item.role != "home"))
    responses = old.legacy.valid_responses.__wrapped__(extended)
    hubs = {row["slug"]: row for row in navigation["reader_navigation"]["hubs"]}
    for item in items:
        slug = "home" if item.role == "home" else item.url.split("/")[-2]
        row = current[slug]
        markup = old.legacy.html(item, contract.required_types[item.role])
        markup = markup.replace("Valid title", row["title"]).replace("Valid description", row["excerpt"])
        markup = markup.replace("2026-08-30T00:00:00Z", old.STAMP)
        body = hub_html(hubs[slug], navigation, current) if slug in hubs else row["block_markup"]
        markup = markup.replace("Public content", "<h1>" + row["title"] + '</h1><div class="entry-content">' + body + "</div>")
        if slug == "home":
            markup = markup.replace("</body>", "".join('<a href="' + entry.url + '">Route</a>' for entry in items) + "</body>")
        responses[item.url] = replace(responses[item.url], body=reader_article_graph(
            absent_images(markup), item, navigation,
        ).encode())
    mixed.update(current_documents=current, public_metadata_reader=old.Metadata(current),
                 transport=old.legacy.FakeTransport({url: replace(row, observed_at=old.STAMP) for url, row in responses.items()}),
                 reader_metadata=metadata)
    mixed["deployment_readback"]["theme"]["tree_sha256"] = tree
    monkeypatch.setattr(audit, "_theme_expectations", lambda expected: (
        {"title": current["home"]["title"], "description": current["home"]["excerpt"]}, {}, {}
    ))
    seal(mixed, envelope, preparation)
    return mixed


def test_registered_media_projection_records_absence_without_hero_fallback():
    metadata, _navigation, _files, tree = metadata_fixture()
    doc = metadata.to_document()
    assert doc["theme_sha256"] == tree
    assert len(doc["social_images"]) == 29
    assert all(value is None for value in doc["social_images"].values())


def test_all_29_pages_and_draft_baselines_are_bound_without_fake_media(reader):
    result = audit.run_verified_incremental_public_audit(**reader)
    assert result["core_document_count"] == 29
    assert len(result["page_evidence"]) == 29
    assert result["schema"] == "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_PUBLIC_READBACK_V2"
    assert all(row["social_image_state"] == "NOT_INCLUDED" for row in result["page_evidence"].values())
    assert result["image_evidence_sha256"] == audit.digest(audit.canonical({}))


@pytest.mark.parametrize("approved_image", [False, True])
@pytest.mark.parametrize("change", [
    "valid", "wrong_category", "wrong_hub", "unknown_hub", "missing_hub",
    "extra_node", "extra_claim", "image",
])
def test_reader_article_graph_is_bound_to_registry_and_published_hub(reader, approved_image, change):
    slug = "solota-vs-rakua-mini-plus"
    url = audit.publication.ORIGIN + "/" + slug + "/"
    response = reader["transport"].responses[url]
    markup = response.body.decode()
    if approved_image:
        # Synthetic owned bytes and rights metadata, never production evidence.
        asset = {
            "asset_ref": slug, "source": "tests/wordpress_seo_audit_v1/test_incremental_reader.py",
            "usage_basis": "Synthetic test fixture",
            "checked_at": "2026-09-05", "approval": "approved", "alt": "Test diagram",
            "caption": "Synthetic diagram", "aspect_ratio": [1200, 630], "role": "hero",
            "asset_type": "illustration", "path": "assets/images/test-reader.webp",
            "sha256": audit.digest(old.IMAGE),
        }
        metadata, _navigation, _files, tree = metadata_fixture(media=[asset])
        reader["reader_metadata"] = metadata
        reader["deployment_readback"]["theme"]["tree_sha256"] = tree
        envelope = reader["context"].to_document()
        envelope["expected_shared_readback_sha256"]["theme"] = tree
        preparation = json.loads((reader["candidate_path"] / "candidate-preparation.v1.json").read_bytes())
        seal(reader, envelope, preparation)
        image = metadata.to_document()["social_images"][slug]["url"]
        markup = markup.replace('content="summary"', 'content="summary_large_image"').replace(
            "</head>", '<meta property="og:image" content="' + image + '">'
            '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
            '<meta property="og:image:type" content="image/webp"><meta name="twitter:image" content="' + image + '"></head>',
        )
        reader["transport"].responses[image] = replace(
            response, url=image, body=old.IMAGE, headers=(("content-type", "image/webp"),),
        )
        card = '<li><a class="raos-guide-card" href="/' + slug + '/">'
        card_image = ('<span class="raos-guide-card__media"><img src="' + image
                      + '" alt="Test diagram" width="1200" height="630" loading="lazy" decoding="async">'
                      '<span class="raos-guide-card__caption">Synthetic diagram</span></span>')
        for hub in _navigation["reader_navigation"]["hubs"]:
            hub_url = audit.publication.ORIGIN + "/" + hub["slug"] + "/"
            hub_response = reader["transport"].responses[hub_url]
            reader["transport"].responses[hub_url] = replace(
                hub_response, body=hub_response.body.decode().replace(card, card + card_image).encode(),
            )
    match = re.search(r'(<script type="application/ld\+json">)(.*?)(</script>)', markup, re.S)
    graph = json.loads(match[2])
    nodes = {node["@type"]: node for node in graph["@graph"]}
    article = nodes["Article"]
    crumbs = nodes["BreadcrumbList"]["itemListElement"]
    assert article["articleSection"] == "キッチン・家事"
    assert crumbs[1] == {"@type": "ListItem", "item": audit.publication.ORIGIN + "/kitchen/",
                         "name": "キッチン・家事", "position": 2}
    if approved_image:
        article["image"] = [image]
    if change == "wrong_category":
        article["articleSection"] = "旅行・外出"
    elif change == "wrong_hub":
        crumbs[1].update(item=audit.publication.ORIGIN + "/travel/", name="旅行・外出")
    elif change == "unknown_hub":
        crumbs[1]["item"] = audit.publication.ORIGIN + "/unregistered-category/"
    elif change == "missing_hub":
        crumbs.pop(1)
        crumbs[-1]["position"] = 2
    elif change == "extra_node":
        graph["@graph"].append({"@type": "Product", "@id": url + "#unsupported"})
    elif change == "extra_claim":
        article["aggregateRating"] = {"ratingValue": 5}
    elif change == "image":
        article["image"] = [audit.publication.ORIGIN + "/unapproved.webp"]
    def install_graph():
        reader["transport"].responses[url] = replace(
            response, body=(markup[:match.start(2)] + json.dumps(graph) + markup[match.end(2):]).encode(),
        )
    install_graph()
    if change == "valid":
        result = audit.run_verified_incremental_public_audit(**reader)
        assert result["page_evidence"][slug]["social_image_state"] == (
            "VERIFIED_PRESENT" if approved_image else "NOT_INCLUDED"
        )
        if approved_image:
            article.pop("image")
            install_graph()
            with pytest.raises(audit.seo.AuditError, match="INCREMENTAL_PUBLIC_SEO_FAILED"):
                audit.run_verified_incremental_public_audit(**reader)
    else:
        with pytest.raises(audit.seo.AuditError, match="INCREMENTAL_PUBLIC_SEO_FAILED"):
            audit.run_verified_incremental_public_audit(**reader)


@pytest.mark.parametrize("unavailable", ["unbound", "missing", "draft"])
def test_category_section_does_not_authorize_unpublished_or_unbound_breadcrumb(reader, unavailable):
    metadata = reader["reader_metadata"].to_document()
    contract = audit.seo.load_contract()
    item = next(row for row in contract.items if row.url.endswith("/solota-vs-rakua-mini-plus/"))
    documents = deepcopy(reader["current_documents"])
    if unavailable != "unbound":
        contract = replace(contract, items=contract.items + (
            audit.seo.InventoryItem(contract.origin + "/kitchen/", "fixed_page", "kitchen"),
        ))
    if unavailable == "missing":
        documents.pop("kitchen")
    elif unavailable == "draft":
        documents["kitchen"]["status"] = "draft"
    markup = reader["transport"].responses[item.url].body.decode()
    graph = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', markup, re.S)[1])
    document = documents["solota-vs-rakua-mini-plus"]
    def valid():
        return audit._reader_structured_data_semantics(
            graph, item, contract, document["title"], document["excerpt"], metadata, documents,
        )
    assert not valid()
    crumbs = next(node for node in graph["@graph"] if node["@type"] == "BreadcrumbList")["itemListElement"]
    crumbs.pop(1)
    crumbs[-1]["position"] = 2
    assert valid()  # Registry section stays キッチン・家事, independent of hub publication.


@pytest.mark.parametrize("change", ["missing", "ambiguous"])
def test_article_graph_and_hub_cards_reject_nonunique_category_membership(reader, change):
    files = dict(reader["reader_metadata"].theme_files)
    navigation = json.loads(files[NAV])
    old_sha = audit.digest(files[NAV])
    hubs = {hub["slug"]: hub for hub in navigation["reader_navigation"]["hubs"]}
    article_id = "solota-vs-rakua-mini-plus"
    if change == "missing":
        hubs["kitchen"]["article_ids"].remove(article_id)
    else:
        hubs["travel"]["article_ids"].append(article_id)
    files[NAV] = audit.canonical(navigation)
    files["functions.php"] = files["functions.php"].replace(old_sha.encode(), audit.digest(files[NAV]).encode())
    metadata = audit.reader_seo_metadata(files, expected_tree=theme_tree_sha256(files)).to_document()
    contract = audit.seo.load_contract()
    item = next(row for row in contract.items if row.url.endswith("/" + article_id + "/"))
    markup = reader["transport"].responses[item.url].body.decode()
    graph = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', markup, re.S)[1])
    documents = reader["current_documents"]
    article = documents[article_id]
    with pytest.raises(audit.seo.AuditError, match="READER_ARTICLE_CATEGORY_INVALID"):
        audit._reader_structured_data_semantics(
            graph, item, contract, article["title"], article["excerpt"], metadata, documents,
        )
    dates = {slug: {"dates": {"modified": row["modified_gmt"]}} for slug, row in documents.items()}
    hub_slug = next(hub["slug"] for hub in metadata["hubs"]
                    if hub["kind"] == "updates" and article_id in hub["article_ids"])
    with pytest.raises(audit.seo.AuditError, match="READER_ARTICLE_CATEGORY_INVALID"):
        audit._reader_hub_body(hub_slug, metadata, documents, dates)


@pytest.mark.parametrize("label", ["家事", "旅行・外出"])
def test_hub_card_rejects_legacy_or_other_article_category_label(reader, label):
    url = audit.publication.ORIGIN + "/kitchen/"
    response = reader["transport"].responses[url]
    markup = response.body.decode()
    assert "キッチン・家事 / " in markup
    reader["transport"].responses[url] = replace(
        response, body=markup.replace("キッチン・家事 / ", label + " / ").encode(),
    )
    with pytest.raises(audit.seo.AuditError, match="PUBLIC_BODY_OR_COMMERCE_MISMATCH"):
        audit.run_verified_incremental_public_audit(**reader)


@pytest.mark.parametrize("change", [
    "extra_document", "missing_hub", "id", "boolean_id", "status", "baseline_hash",
    "origin", "title", "canonical", "body", "route", "image", "empty_image",
    "article_image_schema", "theme", "registry", "runtime_dict",
])
def test_v2_readback_rejects_identity_scope_head_media_or_registry_promotion(reader, change):
    envelope = reader["context"].to_document()
    preparation = json.loads((reader["candidate_path"] / "candidate-preparation.v1.json").read_bytes())
    if change == "extra_document":
        reader["current_documents"]["local-guide"] = deepcopy(reader["current_documents"]["categories"])
    elif change == "missing_hub":
        reader["current_documents"].pop("categories")
    elif change in {"id", "boolean_id", "status"}:
        field, value = {"id": ("id", 999), "boolean_id": ("id", True), "status": ("status", "draft")}[change]
        reader["current_documents"]["categories"][field] = value
    elif change == "baseline_hash":
        envelope["inventory"]["categories"]["content_sha256"] = "f" * 64
        seal(reader, envelope, preparation)
    elif change == "registry":
        envelope["selected_pages"]["categories"]["registry_sha256"] = "f" * 64
        seal(reader, envelope, preparation)
    elif change == "theme":
        reader["deployment_readback"]["theme"]["tree_sha256"] = "f" * 64
    elif change == "runtime_dict":
        reader["reader_measurement"] = {}
    else:
        slug = "categories" if change != "article_image_schema" else audit.seo.load_contract().items[1].url.split("/")[-2]
        url = audit.publication.ORIGIN + "/" + slug + "/"
        response = reader["transport"].responses[url]
        markup = response.body.decode()
        if change == "origin":
            reader["transport"].responses[url] = replace(response, url="https://evil.test/categories/")
            markup = None
        elif change == "title":
            markup = markup.replace("<title>", "<title>Wrong ")
        elif change == "canonical":
            markup = markup.replace('rel="canonical" href="' + url, 'rel="canonical" href="https://evil.test/categories/')
        elif change == "body":
            markup = markup.replace("条件から読み始める", "Unsupported hub story")
        elif change == "route":
            markup = markup.replace('href="/travel/"', 'href="/local-guide/"')
        elif change == "article_image_schema":
            markup = markup.replace('"@type": "Article"', '"@type": "Article", "image": [""]')
        else:
            content = "" if change == "empty_image" else old.audit.publication.EXPECTED_SOCIAL_IMAGE_URL
            markup = markup.replace("</head>", '<meta property="og:image" content="' + content + '"></head>')
        if markup is not None:
            reader["transport"].responses[url] = replace(response, body=markup.encode())
    with pytest.raises((audit.seo.AuditError, audit.publication.PublicationFailure)):
        audit.run_verified_incremental_public_audit(**reader)


def runtime_case(reader, *, enabled=False, bound=True):
    from tests.wordpress_seo_audit_v1 import test_reader_measurement_runtime as fixtures

    reviewed = fixtures.reviewed.__wrapped__()
    navigation = reader["reader_metadata"].to_document()
    files = reviewed["files"]
    allowlist = json.loads(files[audit.runtime.READER_ALLOWLIST])
    allowlist["articles"] = [
        {"article_id": row["article_id"], "slug": row["production_slug"],
         "navigation": [], "panels": [], "references": []}
        for row in navigation["articles"]
    ]
    files[audit.runtime.READER_ALLOWLIST] = fixtures.encode(allowlist)
    config = json.loads(files[audit.runtime.READER_CONFIG])
    config["contract_sha256"] = audit.digest(files[audit.runtime.READER_ALLOWLIST])
    config["files"] = {path: audit.digest(raw) for path, raw in files.items()
                       if path != audit.runtime.READER_CONFIG}
    material = "".join(path + ":" + sha + "\n" for path, sha in sorted(config["files"].items()))
    config["revision"] = audit.digest((material + "policy:" + config["policy_sha256"] + "\nversion:1.0.0\n").encode())
    files[audit.runtime.READER_CONFIG] = fixtures.encode(config)
    reviewed["manifest"].update({key: config[key] for key in ("revision", "contract_sha256")})
    fixtures.refresh_manifest(reviewed)
    profile = fixtures.bind(reviewed, enabled=enabled)
    envelope = reader["context"].to_document()
    preparation = json.loads((reader["candidate_path"] / "candidate-preparation.v1.json").read_bytes())
    policy = reader["current_documents"]["privacy-policy"]
    previous_body = policy["block_markup"]
    policy["block_markup"] = reviewed["policy"].decode()
    policy["revision_id"] += 1
    policy["content_sha256"] = audit.publication._content_after_sha256(policy, policy["id"])
    envelope["unchanged_documents"].pop("privacy-policy")
    envelope["expected_production_content_sha256"]["privacy-policy"] = policy["content_sha256"]
    preparation["production_documents"]["privacy-policy"] = {"document": deepcopy(policy)}
    previous = next(row for row in reader["original_snapshot"]["documents"] if row["slug"] == "privacy-policy")
    envelope["selected_pages"]["privacy-policy"] = {
        "kind": "reader_privacy", "post_id": policy["id"], "baseline_status": "publish",
        "template_sha256": profile.policy_sha256, "registry_sha256": profile.policy_sha256,
        "baseline_sha256": previous["content_sha256"], "artifact_key": "privacy-policy",
        "production_artifact_sha256": profile.policy_sha256,
    }
    if bound:
        envelope["reader_measurement"] = {
            "schema": "RAOS_READER_MEASUREMENT_RELEASE_V1",
            "profile": profile.profile, "manifest_sha256": profile.manifest_sha256,
            "policy_sha256": profile.policy_sha256, "contract_sha256": profile.contract_sha256,
            "revision": profile.revision, "expected_collection_enabled": False,
        }
    seal(reader, envelope, preparation)
    reader["reader_measurement"] = profile
    reader["site_status_readback"]["reader_measurement"] = {
        "schema": "RAOSReaderMeasurementStatusV1",
        "plugin_active": True, "plugin_version": profile.plugin_version,
        "collection_enabled": enabled,
        "contract_sha256": profile.contract_sha256, "policy_sha256": profile.policy_sha256,
        "approved_revision": profile.revision if enabled else None,
        "cleanup": {"healthy": True, "last_error_code": None, "last_success_date": "2026-09-05"},
    }
    for url, response in list(reader["transport"].responses.items()):
        if "text/html" not in " ".join(response.header_values("content-type")):
            continue
        markup = response.body.decode()
        if url == audit.publication.ORIGIN + "/privacy-policy/":
            markup = markup.replace(previous_body, policy["block_markup"])
        config_tag = '<script type="application/json" id="raos-reader-measurement-config">' + json.dumps(profile.client_config(url)) + '</script>'
        markup = markup.replace("</head>", fixtures.reader_assets(reviewed) + config_tag + "</head>")
        markup = markup.replace("</body>", fixtures.consent(enabled) + "</body>")
        reader["transport"].responses[url] = replace(response, body=markup.encode())
    reader["transport"].responses.update({
        url: replace(response, observed_at=old.STAMP)
        for url, response in fixtures.PublicResponses(reviewed).responses.items()
    })
    return profile


def test_default_audit_cannot_accept_even_a_valid_unbound_reader_runtime(reader):
    runtime_case(reader, bound=False)
    with pytest.raises(audit.seo.AuditError, match="READER_MEASUREMENT_BINDING"):
        audit.run_verified_incremental_public_audit(**reader)


def test_reader_runtime_requires_exact_envelope_binding_on_all29_pages(reader):
    profile = runtime_case(reader)
    result = audit.run_verified_incremental_public_audit(**reader)
    assert result["reader_measurement"]["expected_collection_enabled"] is False
    assert result["measurement_collection_enabled"] is False
    assert all(set(row["runtime_resources"]) == set(profile.resources)
               for row in result["page_evidence"].values())
    assert not any("/events" in url for url in reader["transport"].requested)


def test_postactivation_on_requires_explicit_read_only_mode(reader):
    runtime_case(reader, enabled=True)
    with pytest.raises(audit.seo.AuditError, match="READER_MEASUREMENT_BINDING"):
        audit.run_verified_incremental_public_audit(**reader)
    reader["reader_measurement_mode"] = "post-activation-readback"
    result = audit.run_verified_incremental_public_audit(**reader)
    assert result["reader_measurement"]["expected_collection_enabled"] is True
    assert result["reader_measurement"]["mode"] == "post-activation-readback"
    assert result["publication_authority"] is False
    assert result["measurement_collection_enabled"] is False


@pytest.mark.parametrize("field", [
    "manifest_sha256", "policy_sha256", "contract_sha256", "revision",
    "profile", "expected_collection_enabled",
])
def test_reader_runtime_binding_cannot_drift(reader, field):
    runtime_case(reader)
    envelope = reader["context"].to_document()
    envelope["reader_measurement"][field] = True if field == "expected_collection_enabled" else "f" * 64
    preparation = json.loads((reader["candidate_path"] / "candidate-preparation.v1.json").read_bytes())
    seal(reader, envelope, preparation)
    with pytest.raises(audit.seo.AuditError, match="READER_MEASUREMENT_BINDING"):
        audit.run_verified_incremental_public_audit(**reader)


@pytest.mark.parametrize("mutation", ["asset_bytes", "extra_script", "config", "consent", "status", "cleanup", "missing_profile"])
def test_reader_runtime_never_waives_resource_consent_config_or_status(reader, mutation):
    profile = runtime_case(reader)
    url = audit.publication.ORIGIN + "/categories/"
    response = reader["transport"].responses[url]
    if mutation == "asset_bytes":
        url = next(url for url in profile.resources if ".js?" in url)
        response = reader["transport"].responses[url]
        reader["transport"].responses[url] = replace(response, body=response.body + b" ")
    elif mutation == "status":
        reader["site_status_readback"]["reader_measurement"]["collection_enabled"] = True
    elif mutation == "cleanup":
        reader["site_status_readback"]["reader_measurement"]["cleanup"]["healthy"] = False
    elif mutation == "missing_profile":
        reader.pop("reader_measurement")
    else:
        markup = response.body.decode()
        if mutation == "extra_script":
            markup = markup.replace("</head>", '<script src="https://example.com/measurement.js"></script></head>')
        elif mutation == "config":
            markup = markup.replace('"collection_enabled": false', '"collection_enabled": true')
        else:
            markup = markup.replace('id="raos-reader-consent-deny"', 'id="wrong-control"')
        reader["transport"].responses[url] = replace(response, body=markup.encode())
    with pytest.raises(audit.seo.AuditError):
        audit.run_verified_incremental_public_audit(**reader)


def test_new_hub_dates_come_only_from_current_rest_evidence(reader):
    class FreshDates(old.Metadata):
        def get(self, resource, identifier):
            result = super().get(resource, identifier)
            if result["document"]["slug"] in READER_HUB_SLUGS:
                result["document"].update(date_gmt="2026-09-05T02:00:00", date="2026-09-05T11:00:00")
                raw = audit.canonical(result["document"])
                result.update(response_utf8=raw.decode(), snapshot_sha256=audit.digest(raw))
            return result
    reader["public_metadata_reader"] = FreshDates(reader["current_documents"])
    result = audit.run_verified_incremental_public_audit(**reader)
    page = result["page_evidence"]["categories"]
    assert page["baseline_publication_date"] == "NOT_REQUIRED"
    assert page["public_dates"]["date_gmt"] == "2026-09-05 02:00:00"
    assert "categories" not in reader["original_snapshot"]["public_metadata"]["documents"]


@pytest.mark.parametrize("change", ["missing_date", "modified_drift", "missing_hub_metadata", "stale"])
def test_new_hub_dates_require_fresh_current_mcp_crosscheck(reader, change):
    class InvalidDates(old.Metadata):
        def get(self, resource, identifier):
            result = super().get(resource, identifier)
            if result["document"]["slug"] == "categories":
                if change == "missing_date":
                    result["document"].pop("date_gmt")
                elif change == "modified_drift":
                    result["document"]["modified_gmt"] = "2026-09-05T01:00:00"
                elif change == "missing_hub_metadata":
                    raise ValueError("missing public page")
                else:
                    result["retrieved_at"] = "2026-09-05T01:00:00Z"
                raw = audit.canonical(result["document"])
                result.update(response_utf8=raw.decode(), snapshot_sha256=audit.digest(raw))
            return result
    reader["public_metadata_reader"] = InvalidDates(reader["current_documents"])
    with pytest.raises((audit.seo.AuditError, audit.publication.PublicationFailure, old.IncrementalPublicationFailure)):
        audit.run_verified_incremental_public_audit(**reader)

def test_postactivation_reader_on_cannot_enable_legacy_collector(reader):
    runtime_case(reader, enabled=True)
    reader["reader_measurement_mode"] = "post-activation-readback"
    reader["site_status_readback"]["measurement"]["collection_enabled"] = True
    with pytest.raises(audit.seo.AuditError, match="LEGACY_MEASUREMENT"):
        audit.run_verified_incremental_public_audit(**reader)

def _with_untouched_extra_draft(reader):
    snapshot = reader["original_snapshot"]
    extra = deepcopy(snapshot["documents"][0])
    extra.update(id=900, slug="unrelated-retained-draft", post_type="page", status="draft")
    extra["content_sha256"] = audit.publication.sha256_json({
        "schema": "ContentDocumentV1", "id": extra["id"], "status": "draft",
        **audit.publication.document_projection(extra),
    })
    snapshot["all_document_baselines"] = {
        str(row["id"]): audit.publication._baseline_record(row)
        for row in [*snapshot["documents"], extra]
    }
    reader["current_documents"][extra["slug"]] = extra
    preparation = json.loads((reader["candidate_path"] / "candidate-preparation.v1.json").read_bytes())
    preparation["snapshot_sha256"] = audit.digest(audit.canonical(snapshot))
    seal(reader, reader["context"].to_document(), preparation)
    return extra["slug"]


def test_registered_hub_audit_preserves_unrelated_snapshot_bound_draft(reader):
    slug = _with_untouched_extra_draft(reader)
    result = audit.run_verified_incremental_public_audit(**reader)
    assert result["core_document_count"] == 29
    assert slug not in result["page_evidence"]


def test_registered_hub_audit_rejects_changed_untargeted_draft(reader):
    slug = _with_untouched_extra_draft(reader)
    reader["current_documents"][slug]["revision_id"] += 1
    with pytest.raises(audit.seo.AuditError, match="UNSELECTED_DOCUMENT"):
        audit.run_verified_incremental_public_audit(**reader)
