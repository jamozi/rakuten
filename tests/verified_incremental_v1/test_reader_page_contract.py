"""Pure page release regressions; fixtures are synthetic, never publication evidence."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path

import pytest

from raos.adapters.self_hosted_editorial_source_capture import (
    LOCATOR_CONTRACT_RELATIVE_PATH,
    SOURCE_REGISTRY_RELATIVE_PATH,
)
from raos.application.editorial import verified_incremental_audit_v1 as audit
from raos.application.editorial import verified_incremental_release_v1 as release
from raos.application.editorial import verified_incremental_sources_v1 as sources
from raos.application.editorial import verified_incremental_v1 as manifest
from tests.verified_incremental_v1.test_release import (
    NOW,
    sample as article_sample,
    stamp,
)

HUBS = (
    "categories",
    "purposes",
    "guides",
    "comparisons",
    "updates",
    "travel",
    "kitchen",
    "cleaning",
    "preparedness",
    "small-space",
    "save-housework",
    "without-installation",
    "easy-maintenance",
    "comfortable-travel",
    "prepare-outage",
)


def empty_sources():
    return sources.SelectedOfficialSourcesV1(
        (),
        {},
        {},
        {},
        (),
        {"source_registry": "d" * 64, "locator_contract": "e" * 64},
        stamp(NOW),
    )


def page_sample(slug="categories", *, status="draft", kind="hub"):
    # Losing the closed target API must not silently fall back to an article.
    assert hasattr(manifest, "ReaderPageTarget")
    inventory = {
        f"article-{index}": manifest.ExistingDocument(
            index + 1, f"article-{index}", "post", manifest.digest(str(index).encode())
        )
        for index in range(10)
    }
    inventory["home"] = manifest.ExistingDocument(15, "home", "page", "c" * 64)
    inventory[slug] = manifest.ExistingDocument(101, slug, "page", "a" * 64, status)
    target = manifest.ReaderPageTarget(
        kind,
        101,
        status,
        manifest.digest(b'<nav><a href="/article-0/">Guide</a></nav>'),
        "f" * 64,
    )
    artifacts = {slug: b'<nav><a href="/article-0/">Guide</a></nav>'}
    document = {
        "schema": "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_MANIFEST_V2",
        "publication_profile": "verified-incremental",
        "link_mode": "standard-api",
        "measurement_collection_enabled": False,
        "publication_authority": False,
        "evaluated_at": stamp(NOW),
        "expires_at": stamp(NOW + timedelta(hours=24)),
        "articles": [],
        "reader_pages": {slug: asdict(target)},
        "shared_artifacts": {
            slug: {
                "key": slug,
                "sha256": target.template_sha256,
                "post_id": 101,
                "baseline_sha256": "a" * 64,
            }
        },
        "unchanged_documents": {
            key: value.content_sha256 for key, value in inventory.items() if key != slug
        },
        "rendered_document_slugs": sorted(inventory),
    }
    inputs = {
        "inventory": inventory,
        "article_targets": {
            f"a{index:02}": (f"article-{index}", index + 1) for index in range(10)
        },
        "reader_page_targets": {slug: target},
        "shared_baseline_sha256": {},
        "article_products": {},
        "article_claims": {},
        "claim_sources": {},
        "source_receipt_sha256": {},
        "verified_image_sha256": {},
        "verified_cta_sha256": {},
        "image_article_products": {},
        "cta_article_products": {},
        "artifact_bytes": artifacts,
        "now": NOW,
    }
    return document, inputs


def page_scope():
    return audit.IncrementalAuditScopeV1(
        (),
        tuple(f"a{index:02}" for index in range(10)),
        tuple(f"a{index:02}" for index in range(10)),
        True,
        {},
        selected_page_slugs=("categories",),
    )


def release_sample():
    document, args = page_sample()
    validated = manifest.validate_manifest(document, **args)
    scope = page_scope()
    official = empty_sources()
    audited = {
        **args["artifact_bytes"],
        "source-replay": manifest.canonical(official.to_document()),
    }
    binding = audit.VerifiedIncrementalAuditBindingV1(
        "5" * 64,
        validated.manifest_sha256,
        release._digest(scope.to_document()),
        release._digest({key: manifest.digest(raw) for key, raw in audited.items()}),
        "6" * 64,
        stamp(NOW),
        stamp(NOW + timedelta(hours=24)),
        "OWNER_CONFIRMED",
    )
    return document, {
        "validated_manifest": validated,
        "audit_binding": binding,
        "audit_scope": scope,
        "official_sources": official,
        "artifact_bytes": args["artifact_bytes"],
        "audit_artifact_bytes": audited,
        "inventory": args["inventory"],
        "article_targets": args["article_targets"],
        "reader_page_targets": args["reader_page_targets"],
        "commerce_views": {},
        "image_article_products": {},
        "cta_bindings": {},
        "expected_production_content_sha256": {"categories": "7" * 64},
        "expected_shared_readback_sha256": {},
        "source_article_id_by_article_id": {},
        "now": NOW,
    }


def test_empty_source_record_is_not_claimed_as_verified():
    record = empty_sources()
    assert record.status == "NOT_REQUIRED"
    assert record.to_document()["status"] == "NOT_REQUIRED"
    assert record.expires_at is None


def test_empty_source_loader_requires_opt_in_and_binds_actual_contracts(tmp_path):
    root = Path(__file__).resolve().parents[2]
    with pytest.raises(sources.SelectedOfficialSourcesFailure):
        sources.validate_selected_official_sources(root, tmp_path, (), NOW)
    record = sources.validate_selected_official_sources(
        root, tmp_path, (), NOW, allow_empty=True
    )
    assert record.status == "NOT_REQUIRED"
    assert record.contract_file_sha256 == {
        "source_registry": manifest.digest(
            (root / SOURCE_REGISTRY_RELATIVE_PATH).read_bytes()
        ),
        "locator_contract": manifest.digest(
            (root / LOCATOR_CONTRACT_RELATIVE_PATH).read_bytes()
        ),
    }
    assert record.article_ids == () and record.sources == {}
    assert list(tmp_path.iterdir()) == []


def test_v1_serialized_contracts_remain_byte_identical():
    document, inputs = article_sample()
    assert (
        inputs["validated_manifest"].manifest_sha256
        == "bec8b34fbc56823930491b99218ccc0ecfef6e60d67b9d9c25b256a453a8e444"
    )
    assert (
        release.build_verified_incremental_release_v1(document, **inputs).sha256
        == "1269ffe08f14500bc582de832e734b3f6c52f13bf476983c31c623dec4adf5b7"
    )
    for field, expected in (
        (
            "audit_scope",
            "0fbe20041f5bf82c9ede453f0aa2b812fb05fc933f636234afa20944c2c8d81a",
        ),
        (
            "audit_binding",
            "dbfe522c9ec991f614d46b401960b20af117ec9cb4345194aad873a69a97b358",
        ),
        (
            "official_sources",
            "3afe4d61ace0749bb4a40b4ad8201a70232564df5f2188df662d654c6d03e0e5",
        ),
    ):
        assert (
            manifest.digest(manifest.canonical(inputs[field].to_document())) == expected
        )


@pytest.mark.parametrize("slug", HUBS)
@pytest.mark.parametrize("status", ["draft", "publish"])
def test_registered_hubs_are_pages_and_keep_all_article_baselines(slug, status):
    document, inputs = page_sample(slug, status=status)
    result = manifest.validate_manifest(document, **inputs)
    assert result.schema == manifest.SCHEMA_V2
    assert result.articles == () and result.counts["articles"] == 0
    assert result.reader_pages == inputs["reader_page_targets"]
    assert len(result.unchanged_sha256) == 11
    with pytest.raises(TypeError):
        result.reader_pages["other"] = inputs["reader_page_targets"][slug]


@pytest.mark.parametrize(
    "change",
    [
        "v1_extension",
        "v1_empty",
        "no_targets",
        "empty_pages",
        "missing_pages",
        "unknown_slug",
        "local5",
        "id",
        "bool_id",
        "missing_id",
        "registry",
        "body",
        "shared_missing",
        "shared_extra",
        "shared_id",
        "shared_baseline",
        "shared_key",
        "unselected_draft",
        "article_draft",
        "unchanged",
        "fake_article",
        "shadow_article",
    ],
)
def test_manifest_rejects_untrusted_or_unbound_page_scope(change):
    document, inputs = page_sample()
    row = document["reader_pages"]["categories"]
    if change.startswith("v1"):
        document["schema"] = manifest.SCHEMA
        if change == "v1_empty":
            del document["reader_pages"]
    elif change == "no_targets":
        inputs.pop("reader_page_targets")
    elif change == "empty_pages":
        document["reader_pages"] = {}
    elif change == "missing_pages":
        del document["reader_pages"]
    elif change in {"unknown_slug", "local5"}:
        new_slug = "unknown-hub" if change == "unknown_slug" else "first-suitcase-guide"
        document["reader_pages"][new_slug] = document["reader_pages"].pop("categories")
        inputs["reader_page_targets"][new_slug] = inputs["reader_page_targets"].pop(
            "categories"
        )
    elif change in {"id", "bool_id", "missing_id"}:
        row["post_id"] = {"id": 999, "bool_id": True, "missing_id": 0}[change]
    elif change == "registry":
        row["registry_sha256"] = "b" * 64
    elif change == "body":
        inputs["artifact_bytes"]["categories"] = b"<nav>Rewritten semantic source</nav>"
        row["template_sha256"] = manifest.digest(inputs["artifact_bytes"]["categories"])
        document["shared_artifacts"]["categories"]["sha256"] = row["template_sha256"]
    elif change == "shared_missing":
        document["shared_artifacts"] = {}
    elif change == "shared_extra":
        row["artifact"] = "categories"
    elif change in {"shared_id", "shared_baseline", "shared_key"}:
        field = {
            "shared_id": "post_id",
            "shared_baseline": "baseline_sha256",
            "shared_key": "key",
        }[change]
        document["shared_artifacts"]["categories"][field] = {
            "post_id": 999,
            "baseline_sha256": "b" * 64,
            "key": "absent",
        }[field]
    elif change in {"unselected_draft", "article_draft"}:
        slug = "home" if change == "unselected_draft" else "article-0"
        inputs["inventory"][slug] = replace(inputs["inventory"][slug], status="draft")
    elif change == "unchanged":
        document["unchanged_documents"]["article-0"] = "b" * 64
    else:
        fake = deepcopy(article_sample()[0]["articles"][0])
        fake.update(article_id="categories", slug="categories", post_id=101)
        if change == "shadow_article":
            fake.update(article_id="a00", slug="article-0", post_id=1)
        document["articles"] = [fake]
    with pytest.raises(manifest.IncrementalPublicationFailure):
        manifest.validate_manifest(document, **inputs)


@pytest.mark.parametrize("status", ["draft", "publish"])
def test_privacy_update_requires_existing_published_privacy_page(status):
    document, inputs = page_sample(
        "privacy-policy", status=status, kind="reader_privacy"
    )
    if status == "draft":
        with pytest.raises(manifest.IncrementalPublicationFailure):
            manifest.validate_manifest(document, **inputs)
    else:
        assert (
            manifest.validate_manifest(document, **inputs)
            .reader_pages["privacy-policy"]
            .kind
            == "reader_privacy"
        )


@pytest.mark.parametrize(
    "body",
    [
        b'<nav><a href="javascript:alert(1)">Bad</a></nav>',
        b'<nav><a href="//evil.test/">Bad</a></nav>',
        b'<nav><a href="/unregistered/">Bad</a></nav>',
        b'<nav><a href="/article-0/" href="/home/">Bad</a></nav>',
        b'<nav><a href="/article-0/%ZZ">Bad</a></nav>',
        b'<img src="https://example.test/unverified.png" alt="Product">',
        b'<div data-raos-product-id="PRD-FAKE">Fake article product</div>',
    ],
)
def test_even_trusted_page_artifacts_must_have_safe_bound_shared_markup(body):
    document, inputs = page_sample()
    proof = manifest.digest(body)
    inputs["artifact_bytes"]["categories"] = body
    inputs["reader_page_targets"]["categories"] = replace(
        inputs["reader_page_targets"]["categories"], template_sha256=proof
    )
    document["reader_pages"]["categories"]["template_sha256"] = proof
    document["shared_artifacts"]["categories"]["sha256"] = proof
    with pytest.raises(manifest.IncrementalPublicationFailure):
        manifest.validate_manifest(document, **inputs)


def test_page_only_scope_is_explicit_and_has_no_product_or_article_promotions():
    scope = page_scope()
    document = scope.to_document()
    assert document["selected_article_ids"] == []
    assert document["selected_page_slugs"] == ["categories"]
    assert len(document["rendered_article_ids"]) == 10
    assert document["claim_ids_by_article"] == {}
    for changes in (
        {"selected_page_slugs": ()},
        {"selected_page_slugs": ("first-suitcase-guide",)},
        {"selected_page_slugs": ("categories", "categories")},
        {"shared_changes": False},
        {"existing_article_ids": ("a00",)},
        {"rendered_article_ids": ("a00",)},
        {"retained_product_ids": ("PRD-FAKE",)},
        {"affiliate_cta_ids": ("cta",)},
        {"product_image_ids": ("image",)},
        {"claim_ids_by_article": {"a00": ("claim",)}},
    ):
        with pytest.raises(audit.IncrementalAuditFailure):
            replace(scope, **changes).to_document()


def test_page_release_binds_pages_without_fake_articles_or_source_verification():
    document, inputs = release_sample()
    result = release.build_verified_incremental_release_v1(document, **inputs)
    envelope = result.to_document()
    assert envelope["schema"] == "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_RELEASE_V2"
    assert envelope["selected_articles"] == {}
    assert envelope["selected_pages"] == {
        "categories": {
            **document["reader_pages"]["categories"],
            "baseline_sha256": "a" * 64,
            "artifact_key": "categories",
            "production_artifact_sha256": document["reader_pages"]["categories"][
                "template_sha256"
            ],
        }
    }
    assert envelope["source_receipts"] == {} and envelope["product_receipts"] == {}
    assert envelope["owner_approval_required"] is True
    assert envelope["publication_authority"] is False
    assert envelope["measurement_collection_enabled"] is False
    assert result.expires_at == NOW + timedelta(seconds=900)


@pytest.mark.parametrize(
    "change",
    [
        "targets_missing",
        "target_drift",
        "registry_drift",
        "baseline_drift",
        "page_status_drift",
        "article_status_drift",
        "id_drift",
        "bool_id",
        "empty_sources_article",
        "empty_sources_claims",
        "empty_sources_refs",
        "empty_sources_receipts",
        "empty_sources_issues",
        "empty_sources_contracts",
        "commerce",
        "images",
        "ctas",
        "audit_scope",
        "audit_binding",
        "audit_expiry",
        "activation_expiry",
        "source_replay",
        "source_audit_future",
    ],
)
def test_page_release_replays_trust_and_requires_clean_empty_evidence(change):
    document, inputs = release_sample()
    if change == "targets_missing":
        inputs.pop("reader_page_targets")
    elif change in {"target_drift", "registry_drift"}:
        field = "template_sha256" if change == "target_drift" else "registry_sha256"
        inputs["reader_page_targets"]["categories"] = replace(
            inputs["reader_page_targets"]["categories"], **{field: "b" * 64}
        )
    elif change in {
        "baseline_drift",
        "article_status_drift",
        "page_status_drift",
        "id_drift",
        "bool_id",
    }:
        slug = (
            "categories"
            if change in {"page_status_drift", "id_drift", "bool_id"}
            else "article-0"
        )
        changes = {
            "baseline_drift": {"content_sha256": "b" * 64},
            "article_status_drift": {"status": "draft"},
            "page_status_drift": {"status": "publish"},
            "id_drift": {"post_id": 999},
            "bool_id": {"post_id": True},
        }
        inputs["inventory"][slug] = replace(
            inputs["inventory"][slug], **changes[change]
        )
    elif change.startswith("empty_sources"):
        _doc, article_inputs = article_sample()
        original = article_inputs["official_sources"]
        changes = {
            "empty_sources_article": {"article_ids": original.article_ids},
            "empty_sources_claims": {
                "article_claim_sources": original.article_claim_sources
            },
            "empty_sources_refs": {"article_source_refs": original.article_source_refs},
            "empty_sources_receipts": {"sources": original.sources},
            "empty_sources_issues": {
                "issues": (sources.SelectedSourceIssueV1("s", (), "MISSING"),)
            },
            "empty_sources_contracts": {
                "contract_file_sha256": {"source_registry": "d" * 64}
            },
        }
        inputs["official_sources"] = replace(
            inputs["official_sources"], **changes[change]
        )
    elif change in {"commerce", "images", "ctas"}:
        field = {
            "commerce": "commerce_views",
            "images": "image_article_products",
            "ctas": "cta_bindings",
        }[change]
        inputs[field] = {"fake": None}
    elif change == "audit_scope":
        inputs["audit_scope"] = replace(
            inputs["audit_scope"], selected_page_slugs=("purposes",)
        )
    elif change == "audit_binding":
        inputs["audit_binding"] = replace(
            inputs["audit_binding"], scope_sha256="b" * 64
        )
    elif change == "audit_expiry":
        inputs["audit_binding"] = replace(
            inputs["audit_binding"], expires_at=stamp(NOW)
        )
    elif change == "activation_expiry":
        inputs["now"] = NOW + timedelta(seconds=900)
        inputs["activation_evaluated_at"] = NOW
    else:
        if change == "source_replay":
            inputs["audit_artifact_bytes"].pop("source-replay")
        else:
            record = inputs["official_sources"].to_document()
            record["evaluated_at"] = stamp(NOW + timedelta(seconds=1))
            inputs["audit_artifact_bytes"]["source-replay"] = manifest.canonical(record)
        inputs["audit_binding"] = replace(
            inputs["audit_binding"],
            artifact_bundle_sha256=release._digest(
                {
                    key: manifest.digest(raw)
                    for key, raw in inputs["audit_artifact_bytes"].items()
                }
            ),
        )
    with pytest.raises(
        (
            manifest.IncrementalPublicationFailure,
            sources.SelectedOfficialSourcesFailure,
            audit.IncrementalAuditFailure,
        )
    ):
        release.build_verified_incremental_release_v1(document, **inputs)


def test_readback_requires_declared_hub_publication_and_preserves_all_other_objects():
    document, inputs = release_sample()
    result = release.build_verified_incremental_release_v1(document, **inputs)
    current = dict(inputs["inventory"])
    current["categories"] = replace(
        current["categories"], status="publish", content_sha256="7" * 64
    )
    assert (
        release.verify_release_readback(
            result, current_inventory=current, shared_readback_sha256={}, now=NOW
        )["status"]
        == "CONTENT_AND_IDENTITY_HASHES_MATCH"
    )
    for slug, changes in (
        ("categories", {"status": "draft"}),
        ("home", {"status": "draft"}),
        ("article-0", {"content_sha256": "b" * 64}),
        ("categories", {"post_id": 999}),
    ):
        changed = {**current, slug: replace(current[slug], **changes)}
        with pytest.raises(manifest.IncrementalPublicationFailure):
            release.verify_release_readback(
                result, current_inventory=changed, shared_readback_sha256={}, now=NOW
            )


@pytest.mark.parametrize("count", [20, 21])
def test_twenty_proposal_limit_counts_articles_pages_and_theme_once(count):
    document, inputs = page_sample()
    article_template = article_sample()[0]["articles"][0]
    for index, (article_id, (slug, post_id)) in enumerate(
        inputs["article_targets"].items()
    ):
        row = deepcopy(article_template)
        row.update(
            article_id=article_id,
            slug=slug,
            post_id=post_id,
            baseline_sha256=inputs["inventory"][slug].content_sha256,
        )
        for mode in ("local", "production"):
            key = f"{mode}-{slug}"
            inputs["artifact_bytes"][key] = (
                f"<p>Verified claim for {index}</p>".encode()
            )
            row[f"{mode}_artifact"] = {
                "key": key,
                "sha256": manifest.digest(inputs["artifact_bytes"][key]),
            }
        document["articles"].append(row)
        inputs["article_products"][article_id] = []
        inputs["article_claims"][article_id] = ["claim-1"]
        document["unchanged_documents"].pop(slug)
    inputs["claim_sources"] = {"claim-1": ["source-1"]}
    inputs["source_receipt_sha256"] = article_template["source_receipts"]
    # Ten articles, eight/nine hubs, home and theme: twenty/twenty-one proposals.
    for index, slug in enumerate(HUBS[1 : count - 12], 102):
        row = deepcopy(document["reader_pages"]["categories"])
        row["post_id"] = index
        document["reader_pages"][slug] = row
        inputs["reader_page_targets"][slug] = manifest.ReaderPageTarget(**row)
        inputs["inventory"][slug] = manifest.ExistingDocument(
            index, slug, "page", "a" * 64, "draft"
        )
        inputs["artifact_bytes"][slug] = inputs["artifact_bytes"]["categories"]
        document["shared_artifacts"][slug] = {
            "key": slug,
            "sha256": row["template_sha256"],
            "post_id": index,
            "baseline_sha256": "a" * 64,
        }
    for slug, post_id, baseline in (("home", 15, "c" * 64), ("theme", None, "9" * 64)):
        body = b"<nav>Reader home</nav>" if slug == "home" else b"synthetic theme"
        inputs["artifact_bytes"][slug] = body
        document["shared_artifacts"][slug] = {
            "key": slug,
            "sha256": manifest.digest(body),
            "post_id": post_id,
            "baseline_sha256": baseline,
        }
    document["unchanged_documents"].pop("home")
    inputs["shared_baseline_sha256"]["theme"] = "9" * 64
    document["rendered_document_slugs"] = sorted(inputs["inventory"])
    if count == 21:
        with pytest.raises(
            manifest.IncrementalPublicationFailure, match="PROPOSAL_LIMIT"
        ):
            manifest.validate_manifest(document, **inputs)
    else:
        result = manifest.validate_manifest(document, **inputs)
        assert len(result.articles) == 10 and len(result.reader_pages) == 8


def test_registered_shortcode_body_can_be_bound_without_a_fake_article():
    document, inputs = page_sample()
    body = b'<!-- wp:shortcode -->[kurashinoshirube_reader_hub slug="categories"]<!-- /wp:shortcode -->'
    inputs["artifact_bytes"]["categories"] = body
    target = replace(
        inputs["reader_page_targets"]["categories"],
        template_sha256=manifest.digest(body),
    )
    inputs["reader_page_targets"]["categories"] = target
    document["reader_pages"]["categories"] = asdict(target)
    document["shared_artifacts"]["categories"]["sha256"] = target.template_sha256
    assert manifest.validate_manifest(document, **inputs).articles == ()


@pytest.mark.parametrize(
    "field,value",
    [
        ("baseline_status", []),
        ("kind", {}),
        ("registry_sha256", []),
        ("post_id", 101.0),
        ("post_id", -1),
        ("template_sha256", None),
    ],
)
def test_malformed_typed_targets_fail_closed(field, value):
    document, inputs = page_sample()
    document["reader_pages"]["categories"][field] = value
    inputs["reader_page_targets"]["categories"] = replace(
        inputs["reader_page_targets"]["categories"], **{field: value}
    )
    with pytest.raises(manifest.IncrementalPublicationFailure):
        manifest.validate_manifest(document, **inputs)


def test_an_article_can_never_use_empty_source_replay():
    document, inputs = article_sample()
    inputs["official_sources"] = empty_sources()
    inputs["source_article_id_by_article_id"] = {}
    with pytest.raises(manifest.IncrementalPublicationFailure):
        release.build_verified_incremental_release_v1(document, **inputs)


def test_v1_rejects_reader_field_even_when_article_manifest_is_otherwise_valid():
    from tests.verified_incremental_v1.test_manifest import sample

    document, inputs = sample()
    document["reader_pages"] = {}
    with pytest.raises(manifest.IncrementalPublicationFailure, match="FIELDS_INVALID"):
        manifest.validate_manifest(document, **inputs)
