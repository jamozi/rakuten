#!/usr/bin/env python3
"""Prepare a source-verified, non-monetized candidate; never publish or approve.

This is the explicit first incremental route. Commercial assets are all omitted
until their API evidence is independently materialized. It never marks their
absence as successful monetization and never changes the legacy full route.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "python", ROOT / "scripts"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import raos_wordpress_publication_request as publication  # noqa: E402
from raos.application.editorial.editorial_portfolio_v3 import (  # noqa: E402
    EditorialPortfolioV3,
    load_editorial_portfolio_v3,
)
from raos.application.editorial.verified_incremental_sources_v1 import (  # noqa: E402
    SelectedOfficialSourcesFailure,
    SelectedOfficialSourcesV1,
    validate_selected_official_sources,
)
from raos.application.editorial.verified_incremental_v1 import (  # noqa: E402
    ExistingDocument,
    AUDIT_SUBJECT_MAX_AGE,
    IncrementalPublicationFailure,
    PROFILE,
    SCHEMA,
    HASH,
    canonical,
    digest,
    fail,
    omit_unverified_commerce,
    validate_manifest,
    verify_commerce_markup,
)
from raos.application.finance.editorial_economics_v3 import (  # noqa: E402
    EditorialEconomicsV3Failure,
    ensure_private_root,
    read_private_json,
    write_private_bytes,
)


def prepare_noncommercial_candidate(
    *,
    portfolio: EditorialPortfolioV3,
    snapshot: Mapping[str, Any],
    sources: SelectedOfficialSourcesV1,
    articles: Sequence[publication.Article],
    now: datetime,
    theme_projection: bytes | None = None,
    policy_articles: Sequence[publication.Article] = (),
) -> tuple[dict[str, object], dict[str, bytes], dict[str, object]]:
    """All source evidence is replayed by the caller; no supplied PASS flags."""
    sources.require_complete()
    if (
        snapshot.get("schema") != "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1"
        or snapshot.get("publication_profile") != PROFILE
        or snapshot.get("origin") != publication.ORIGIN
        or snapshot.get("publication_authority") is not False
        or snapshot.get("source") != "BOUNDED_WORDPRESS_EDITOR_MCP"
        or type(snapshot.get("documents")) is not list
    ):
        fail("SNAPSHOT_INVALID")
    documents: dict[str, dict[str, Any]] = {}
    inventory: dict[str, ExistingDocument] = {}
    for document in snapshot["documents"]:
        if (
            type(document) is not dict
            or document.get("slug") in documents
            or document.get("status") != "publish"
            or type(document.get("id")) is not int
            or publication._content_after_sha256(document, document["id"])
            != document.get("content_sha256")
        ):
            fail("SNAPSHOT_INVALID")
        slug = document["slug"]
        documents[slug] = document
        inventory[slug] = ExistingDocument(
            document["id"], slug, document["post_type"], document["content_sha256"]
        )
    existing_slugs = {a.production_slug for a in portfolio.articles}
    if set(documents) != existing_slugs | {
        "home",
        "about-ad-policy",
        "comparison-policy",
        "privacy-policy",
    }:
        fail("SNAPSHOT_INVALID")
    selected = {article.production_slug for article in articles}
    if not selected or len(selected) != len(articles) or not selected <= existing_slugs:
        fail("ARTICLE_SET_INVALID")
    bindings = [portfolio.article_by_slug[slug] for slug in sorted(selected)]
    if set(sources.article_ids) != {binding.article_id for binding in bindings}:
        fail("SOURCE_SET_MISMATCH")
    if sources.expires_at is None:
        fail("SOURCE_UNVERIFIED")
    expiry = min(
        now + AUDIT_SUBJECT_MAX_AGE,
        datetime.strptime(sources.expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC),
    )
    output: dict[str, bytes] = {}
    rows: list[dict[str, object]] = []
    production_documents: dict[str, object] = {}
    by_slug = {article.production_slug: article for article in articles}
    possible_images = {
        f"image:{binding.article_id}:{product_id}": (binding.article_id, product_id)
        for binding in bindings
        for product_id in binding.product_ids
    }
    possible_ctas = {
        cta.cta_id: (cta.article_id, cta.product_id)
        for binding in bindings
        for cta in binding.cta_bindings
    }
    claims = {
        claim: refs
        for article_claims in sources.article_claim_sources.values()
        for claim, refs in article_claims.items()
    }
    for binding in bindings:
        article = by_slug[binding.production_slug]
        original = documents[binding.production_slug]
        if article.post_type != "post" or original["post_type"] != "post":
            fail("EXISTING_TARGET_MISMATCH")
        markup = omit_unverified_commerce(
            article.block_markup,
            image_product_ids=frozenset(),
            cta_product_ids=frozenset(),
            article_id=binding.article_id,
        )
        verify_commerce_markup(
            markup,
            article_id=binding.article_id,
            editorial_product_ids=frozenset(binding.product_ids),
            expected_ctas={},
            expected_images={},
        )
        if "local-preview-" in markup or "127.0.0.1" in markup:
            fail("PRODUCTION_ARTIFACT_INVALID")
        target = article.document()
        # An article update is not a taxonomy/media migration. Preserve both
        # from the actual MCP baseline; they are included in the desired hash.
        target["taxonomies"] = original["taxonomies"]
        target["media_ids"] = original["media_ids"]
        target["block_markup"] = markup
        production_documents[binding.production_slug] = {
            "post_id": original["id"],
            "baseline_precondition": publication.precondition(original),
            "document": target,
            "after_sha256": publication._content_after_sha256(target, original["id"]),
        }
        artifacts = {}
        for mode in ("local", "production"):
            key = f"{mode}-{binding.production_slug}"
            output[key] = markup.encode()
            artifacts[f"{mode}_artifact"] = {"key": key, "sha256": digest(output[key])}
        rows.append(
            {
                "article_id": binding.article_id,
                "post_id": original["id"],
                "slug": binding.production_slug,
                "baseline_sha256": original["content_sha256"],
                "editorial_product_ids": sorted(binding.product_ids),
                "claim_ids": sorted(sources.article_claim_sources[binding.article_id]),
                "source_receipts": {
                    ref: sources.source_receipt_sha256[ref]
                    for ref in sorted(
                        {
                            source_ref
                            for refs in sources.article_claim_sources[
                                binding.article_id
                            ].values()
                            for source_ref in refs
                        }
                    )
                },
                "images": {},
                "ctas": {},
                "excluded_commerce": {
                    key: "NOT_INCLUDED_NO_VERIFIED_COMMERCIAL_MATERIALIZATION"
                    for key, identity in {**possible_images, **possible_ctas}.items()
                    if identity[0] == binding.article_id
                },
                **artifacts,
            }
        )
    shared: dict[str, object] = {}
    shared_baselines: dict[str, str] = {}
    expected_shared_readback: dict[str, str] = {}
    if theme_projection is not None:
        deployment = snapshot.get("deployment_status")
        theme = deployment.get("theme") if type(deployment) is dict else None
        if type(deployment) is not dict or type(theme) is not dict:
            fail("THEME_BASELINE_UNVERIFIED")
        baseline = theme.get("tree_sha256")
        if (
            type(baseline) is not str
            or HASH.fullmatch(baseline) is None
            or deployment.get("schema")
            != "RAOS_WORDPRESS_DEPLOYMENT_BASELINE_SNAPSHOT_V1"
            or deployment.get("source") != "BOUNDED_WORDPRESS_DEPLOYMENT_MCP"
            or deployment.get("status") != "CAPTURED_READ_ONLY"
            or theme.get("slug") != "kurashinoshirube-child"
            or theme.get("active") is not True
        ):
            fail("THEME_BASELINE_UNVERIFIED")
        try:
            projection = json.loads(theme_projection)
        except ValueError, UnicodeError:
            fail("THEME_ARTIFACT_INVALID")
        if (
            not isinstance(projection, list)
            or not projection
            or len(projection) > publication.MAX_THEME_FILE_COUNT
            or publication.canonical_json_bytes(projection) != theme_projection
        ):
            fail("THEME_ARTIFACT_INVALID")
        paths: list[str] = []
        total_size = 0
        for entry in projection:
            if type(entry) is not dict or set(entry) != {"path", "size", "sha256"}:
                fail("THEME_ARTIFACT_INVALID")
            path, size, checksum = entry["path"], entry["size"], entry["sha256"]
            if (
                type(path) is not str
                or len(path) > 300
                or re.fullmatch(r"[A-Za-z0-9._/-]+", path) is None
                or path.startswith("/")
                or any(part in {".", "..", ""} for part in path.split("/"))
                or PurePosixPath(path).as_posix() != path
                or type(size) is not int
                or not 0 <= size <= publication.MAX_THEME_FILE_BYTES
                or type(checksum) is not str
                or HASH.fullmatch(checksum) is None
            ):
                fail("THEME_ARTIFACT_INVALID")
            paths.append(path)
            total_size += size
        if (
            paths != sorted(paths)
            or len({path.casefold() for path in paths}) != len(paths)
            or total_size > publication.MAX_THEME_PACKAGE_BYTES
        ):
            fail("THEME_ARTIFACT_INVALID")
        output["theme-tree"] = theme_projection
        shared_baselines["theme"] = baseline
        expected_shared_readback["theme"] = digest(theme_projection)
        shared["theme"] = {
            "key": "theme-tree",
            "sha256": digest(theme_projection),
            "baseline_sha256": baseline,
            "post_id": None,
        }
    selected_policy_slugs: set[str] = set()
    for article in policy_articles:
        slug = article.production_slug
        if (
            article.post_type != "page"
            or slug not in {"about-ad-policy", "comparison-policy", "privacy-policy"}
            or slug in selected_policy_slugs
        ):
            fail("SHARED_TARGET_INVALID")
        selected_policy_slugs.add(slug)
        if (
            "local-preview-" in article.block_markup
            or "127.0.0.1" in article.block_markup
        ):
            fail("PRODUCTION_ARTIFACT_INVALID")
        verify_commerce_markup(
            article.block_markup,
            article_id=slug,
            editorial_product_ids=frozenset(),
            expected_ctas={},
            expected_images={},
        )
        original = documents[slug]
        target = article.document()
        target["taxonomies"] = original["taxonomies"]
        target["media_ids"] = original["media_ids"]
        production_documents[slug] = {
            "post_id": original["id"],
            "baseline_precondition": publication.precondition(original),
            "document": target,
            "after_sha256": publication._content_after_sha256(target, original["id"]),
        }
        key = f"production-{slug}"
        output[key] = article.block_markup.encode()
        shared[slug] = {
            "key": key,
            "sha256": digest(output[key]),
            "baseline_sha256": original["content_sha256"],
            "post_id": original["id"],
        }
    manifest = {
        "schema": SCHEMA,
        "publication_profile": PROFILE,
        "link_mode": "standard-api",
        "measurement_collection_enabled": False,
        "publication_authority": False,
        "evaluated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "articles": rows,
        "unchanged_documents": {
            slug: entry.content_sha256
            for slug, entry in inventory.items()
            if slug not in selected | selected_policy_slugs
        },
        "shared_artifacts": shared,
        "rendered_document_slugs": sorted(documents if shared else selected),
    }
    validated = validate_manifest(
        manifest,
        inventory=inventory,
        article_targets={
            b.article_id: (b.production_slug, inventory[b.production_slug].post_id)
            for b in bindings
        },
        shared_baseline_sha256=shared_baselines,
        article_products={b.article_id: b.product_ids for b in bindings},
        article_claims={a: tuple(c) for a, c in sources.article_claim_sources.items()},
        claim_sources=claims,
        source_receipt_sha256=sources.source_receipt_sha256,
        verified_image_sha256={},
        verified_cta_sha256={},
        image_article_products=possible_images,
        cta_article_products=possible_ctas,
        artifact_bytes=output,
        now=now,
    )
    preparation = {
        "schema": "RAOS_WORDPRESS_INCREMENTAL_CANDIDATE_PREPARATION_V1",
        "publication_profile": PROFILE,
        "link_mode": "standard-api",
        "status": "SOURCE_VERIFIED_AUDIT_NOT_EXECUTED",
        "publication_authority": False,
        "manifest_sha256": validated.manifest_sha256,
        "snapshot_sha256": digest(publication.canonical_json_bytes(snapshot)),
        "snapshot_name": f"live-{digest(publication.canonical_json_bytes(snapshot))}.v1.json",
        "source_evidence": sources.to_document(),
        "counts": validated.counts,
        "monetization_state": "NOT_INCLUDED",
        "production_documents": production_documents,
        "expected_shared_readback_sha256": expected_shared_readback,
        "artifact_files": {
            key: f"{key}.v1.json" if key == "theme-tree" else f"{key}.html"
            for key in output
        },
        "required_next_gates": [
            "MIXED_LOCAL_PREVIEW_WITH_EXACT_THEME_AND_METADATA",
            "ALL_STATIC_AND_RUNTIME_CHECKS",
            "BACKUP_RESTORATION_REHEARSAL",
            "TWO_INDEPENDENT_CODEX_AUDITS",
            "FRESH_MCP_BASELINE_AND_EVIDENCE_REPLAY",
            "CONCRETE_OWNER_WP_ADMIN_APPROVAL",
            "POST_APPLY_READBACK",
        ],
    }
    return manifest, output, preparation


def current_theme_projection() -> bytes:
    # Reuse the fixed tracked-package owner; no caller-selected package paths.
    import raos_wordpress_deployment_operator as deployment

    _archive, descriptor = deployment.theme_package()
    raw = publication.canonical_json_bytes(descriptor["file_manifest"])
    if (
        digest(raw) != descriptor["file_manifest_sha256"]
        or digest(raw) != publication.tracked_theme_tree_sha256()
    ):
        fail("THEME_ARTIFACT_INVALID")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--snapshot-name", required=True)
    parser.add_argument("--articles", required=True)
    parser.add_argument("--include-theme", action="store_true")
    parser.add_argument("--update-policies", choices=("none", "all"), default="none")
    args = parser.parse_args()
    try:
        owner = Path("/home/minami/rakuten")
        snapshot = read_private_json(
            owner / ".secrets/wordpress-mcp/incremental-snapshots", args.snapshot_name
        )
        if (
            args.snapshot_name
            != f"live-{digest(publication.canonical_json_bytes(snapshot))}.v1.json"
        ):
            fail("SNAPSHOT_NAME_INVALID")
        portfolio = load_editorial_portfolio_v3(ROOT)
        articles = publication.load_articles(args.articles)
        selected_ids = tuple(
            portfolio.article_by_slug[a.production_slug].article_id for a in articles
        )
        now = datetime.now(UTC).replace(microsecond=0)
        sources = validate_selected_official_sources(
            repository_root=ROOT, evidence_root=ROOT, article_ids=selected_ids, now=now
        )
        if sources.issues:
            print(
                json.dumps(
                    {
                        "status": "BLOCKED",
                        "issues": [issue.to_document() for issue in sources.issues],
                    },
                    ensure_ascii=False,
                )
            )
            return 69
        manifest, artifacts, preparation = prepare_noncommercial_candidate(
            portfolio=portfolio,
            snapshot=snapshot,
            sources=sources,
            articles=articles,
            now=now,
            theme_projection=current_theme_projection() if args.include_theme else None,
            policy_articles=(
                publication.load_policy_pages(profile="production")
                if args.update_policies == "all"
                else ()
            ),
        )
        target = (
            owner
            / ".secrets/wordpress-mcp/incremental-candidates"
            / digest(canonical(manifest))
        )
        ensure_private_root(target.parent)
        ensure_private_root(target)
        for key, raw in artifacts.items():
            name = f"{key}.v1.json" if key == "theme-tree" else f"{key}.html"
            write_private_bytes(target / "artifacts", name, raw)
        write_private_bytes(target, "manifest.v1.json", canonical(manifest))
        write_private_bytes(
            target, "candidate-preparation.v1.json", canonical(preparation)
        )
        print(f"Source-verified candidate: {target}")
        print(
            "Audit: NOT_EXECUTED; monetization: NOT_INCLUDED; production writes: NOT_EXECUTED"
        )
        return 0
    except (
        IncrementalPublicationFailure,
        SelectedOfficialSourcesFailure,
        EditorialEconomicsV3Failure,
        publication.PublicationFailure,
    ) as error:
        sys.stderr.write(f"{error}\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
