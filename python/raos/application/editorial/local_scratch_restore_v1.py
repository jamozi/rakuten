"""Separate backup restoration rehearsal, never a production or preview gate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re
from typing import cast

from raos.application.editorial.verified_incremental_preview_v1 import (
    build_local_restoration,
)
from raos.application.editorial.verified_incremental_v1 import (
    READER_HUB_SLUGS,
    READER_PAGE_SLUGS,
    canonical,
    digest,
    fail,
    validate_hash,
)


@dataclass(frozen=True)
class ScratchRestoration:
    seed: bytes
    bodies: Mapping[str, bytes]


def record(value: object) -> dict[str, object]:
    if type(value) is not dict:
        fail("SCRATCH_RESTORE_RECORD_INVALID")
    return cast(dict[str, object], value)


def build_scratch_restoration(
    snapshot: Mapping[str, object],
    *,
    article_slugs: frozenset[str],
    preparation_sha256: str,
    environment_id: str,
    selected_page_slugs: frozenset[str] = frozenset(),
) -> ScratchRestoration:
    if re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{12}", environment_id) is None:
        fail("SCRATCH_RESTORE_ENVIRONMENT_INVALID")
    if selected_page_slugs:
        return _build_reader_restoration(
            snapshot,
            article_slugs=article_slugs,
            selected_page_slugs=selected_page_slugs,
            preparation_sha256=preparation_sha256,
            environment_id=environment_id,
        )
    baseline = build_local_restoration(snapshot, article_slugs=article_slugs)
    if digest(canonical(baseline.preparation)) != validate_hash(
        preparation_sha256
    ) or not environment_id.startswith(preparation_sha256[:8] + "-"):
        fail("SCRATCH_RESTORE_PREPARATION_INVALID")
    original = record(json.loads(baseline.seed))
    documents = record(original["documents"])
    for raw in cast(list[object], snapshot["documents"]):
        source = record(raw)
        slug = cast(str, source["slug"])
        row = record(documents[slug])
        # Attachments require separate binary backups; never create fake media.
        if source["media_ids"] != []:
            fail("SCRATCH_RESTORE_ATTACHMENT_BACKUP_REQUIRED")
        row["local_slug"] = slug
        row["taxonomy_ids"] = source["taxonomies"]
        row["taxonomy_ids_encoding"] = (
            "object" if type(source["taxonomies"]) is dict else "array"
        )
        row["media_ids"] = []
    return ScratchRestoration(
        canonical(
            {
                "schema": "RAOS_WORDPRESS_SCRATCH_RESTORE_SEED_V1",
                "publication_profile": "local-scratch-restore-rehearsal",
                "publication_authority": False,
                "production_authority": False,
                "scratch_only": True,
                "environment_id": environment_id,
                "source_preparation_sha256": preparation_sha256,
                "source_snapshot_sha256": baseline.preparation[
                    "source_snapshot_sha256"
                ],
                "documents": documents,
            }
        ),
        baseline.bodies,
    )


def verify_scratch_restoration(
    expected: ScratchRestoration, readback: Mapping[str, object]
) -> dict[str, object]:
    seed = record(json.loads(expected.seed))
    if seed.get("schema") == READER_SEED_SCHEMA:
        return _verify_reader_restoration(expected, readback)
    fields = {
        "schema",
        "publication_profile",
        "publication_authority",
        "production_authority",
        "scratch_only",
        "temporary_environment",
        "environment_id",
        "seed_sha256",
        "site_url",
        "original_id_set",
        "documents",
    }
    if set(readback) != fields or any(
        readback.get(key) != value
        for key, value in {
            "schema": "RAOS_WORDPRESS_SCRATCH_RESTORE_READBACK_V1",
            "publication_profile": "local-scratch-restore-rehearsal",
            "publication_authority": False,
            "production_authority": False,
            "scratch_only": True,
            "temporary_environment": True,
            "environment_id": seed["environment_id"],
            "seed_sha256": digest(expected.seed),
            "site_url": "http://scratch.wordpress.invalid",
        }.items()
    ):
        fail("SCRATCH_RESTORE_READBACK_INVALID")
    for flag, value in (
        ("publication_authority", False),
        ("production_authority", False),
        ("scratch_only", True),
        ("temporary_environment", True),
    ):
        if readback.get(flag) is not value:
            fail("SCRATCH_RESTORE_READBACK_INVALID")
    documents = record(seed["documents"])
    observed = record(readback.get("documents"))
    if set(observed) != set(documents) or len(documents) != 14:
        fail("SCRATCH_RESTORE_TARGET_INVALID")
    expected_ids: list[int] = []
    for slug, raw in documents.items():
        document = record(raw)
        expected_ids.append(cast(int, document["production_id"]))
        terms = record(document["taxonomies"])
        semantic_terms: dict[str, list[dict[str, object]]] = {}
        for taxonomy, rows in terms.items():
            semantic_terms[taxonomy] = sorted(
                [record(row) for row in cast(list[object], rows)],
                key=lambda row: cast(int, row["id"]),
            )
        projection: dict[str, object] = {
            "id": document["production_id"],
            "slug": slug,
            "post_type": document["post_type"],
            "status": document["status"],
            "title_sha256": digest(cast(str, document["title"]).encode()),
            "excerpt_sha256": digest(cast(str, document["excerpt"]).encode()),
            "body_sha256": document["content_sha256"],
            "dates": document["dates"],
            "taxonomy_ids": document["taxonomy_ids"],
            "taxonomies": semantic_terms,
            "media_ids": [],
            "content_sha256": document["source_content_sha256"],
        }
        if canonical(record(observed[slug])) != canonical(projection):
            fail("SCRATCH_RESTORE_STORED_FIELDS_MISMATCH")
    if canonical(readback["original_id_set"]) != canonical(sorted(expected_ids)):
        fail("SCRATCH_RESTORE_ID_SET_MISMATCH")
    return {
        "schema": "RAOS_WORDPRESS_SCRATCH_RESTORE_RECEIPT_V1",
        "publication_profile": "local-scratch-restore-rehearsal",
        "publication_authority": False,
        "production_authority": False,
        "scratch_only": True,
        "temporary_environment": True,
        "environment_id": seed["environment_id"],
        "docker_project": f"raos-wp-scratch-{seed['environment_id']}",
        "status": "SCRATCH_STORED_FIELDS_RESTORED",
        "verified_document_count": 14,
        "original_id_set": sorted(expected_ids),
        "source_snapshot_sha256": seed["source_snapshot_sha256"],
        "source_preparation_sha256": seed["source_preparation_sha256"],
        "seed_sha256": digest(expected.seed),
        "readback_sha256": digest(canonical(readback)),
        "current_preview_modified": False,
        "production_writes": False,
        "incremental_preview_pass": False,
        "ports_published": False,
        "network": "dedicated_internal",
        "volumes": "dedicated_scratch_only",
        "not_restored": [
            "revision_history",
            "author_identity",
            "post_meta",
            "theme",
            "plugins",
            "production_site_options",
        ],
    }


READER_SEED_SCHEMA = "RAOS_WORDPRESS_READER_PAGE_RESTORE_SEED_V2"
CORE_PAGES = frozenset(
    {"home", "about-ad-policy", "comparison-policy", "privacy-policy"}
)
CONTENT_FIELDS = frozenset(
    {
        "schema",
        "id",
        "post_type",
        "status",
        "title",
        "slug",
        "excerpt",
        "block_markup",
        "taxonomies",
        "media_ids",
    }
)


def _reader_documents(
    snapshot: Mapping[str, object],
    *,
    article_slugs: frozenset[str],
    selected_page_slugs: frozenset[str],
) -> dict[str, dict[str, object]]:
    legacy_privacy = (
        snapshot.get("schema") == "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1"
        and selected_page_slugs == {"privacy-policy"}
        and "reader_page_slugs" not in snapshot
    )
    if (
        not selected_page_slugs
        or not selected_page_slugs <= READER_PAGE_SLUGS
        or len(article_slugs) != 10
        or article_slugs & (CORE_PAGES | READER_HUB_SLUGS)
        or any(
            type(slug) is not str
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) is None
            for slug in article_slugs
        )
        or (
            snapshot.get("schema") != "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2"
            and not legacy_privacy
        )
        or snapshot.get("publication_profile") != "verified-incremental"
        or snapshot.get("source") != "BOUNDED_WORDPRESS_EDITOR_MCP"
        or snapshot.get("origin") != "https://kurashinoshirube.com"
        or snapshot.get("publication_authority") is not False
    ):
        fail("SCRATCH_READER_SCOPE_INVALID")
    declared = snapshot.get("reader_page_slugs", [])
    if (
        type(declared) is not list
        or any(
            type(slug) is not str or slug not in READER_HUB_SLUGS for slug in declared
        )
        or declared != sorted(set(declared))
        or not selected_page_slugs - CORE_PAGES <= set(declared)
    ):
        fail("SCRATCH_READER_SCOPE_INVALID")
    rows = snapshot.get("documents")
    if type(rows) is not list or not 14 <= len(rows) <= 29:
        fail("SCRATCH_READER_DOCUMENT_SET_INVALID")
    documents: dict[str, dict[str, object]] = {}
    ids: set[int] = set()
    for value in rows:
        row = record(value)
        slug, post_id = row.get("slug"), row.get("id")
        if (
            not CONTENT_FIELDS <= set(row)
            or type(slug) is not str
            or slug in documents
            or slug not in article_slugs | CORE_PAGES | set(declared)
            or type(post_id) is not int
            or post_id < 1
            or post_id in ids
            or row["schema"] != "ContentDocumentV1"
            or row["post_type"] != ("post" if slug in article_slugs else "page")
            or type(row["status"]) is not str
            or row["status"]
            not in (
                {"draft", "publish"}
                if slug in selected_page_slugs & READER_HUB_SLUGS
                else {"publish"}
            )
            or row["media_ids"] != []
            or any(
                type(row[key]) is not str
                for key in ("title", "excerpt", "block_markup")
            )
        ):
            fail("SCRATCH_READER_DOCUMENT_INVALID")
        terms = row["taxonomies"]
        if type(terms) is list:
            if terms != []:
                fail("SCRATCH_READER_TAXONOMY_INVALID")
        elif type(terms) is dict:
            if not set(terms) <= {"category", "post_tag", "post_format"}:
                fail("SCRATCH_READER_TAXONOMY_INVALID")
            for term_ids in terms.values():
                if (
                    type(term_ids) is not list
                    or any(type(term) is not int or term < 1 for term in term_ids)
                    or term_ids != sorted(set(term_ids))
                ):
                    fail("SCRATCH_READER_TAXONOMY_INVALID")
        else:
            fail("SCRATCH_READER_TAXONOMY_INVALID")
        projection = {key: row[key] for key in CONTENT_FIELDS}
        content_hash = digest(canonical(projection).rstrip(b"\n"))
        if content_hash != validate_hash(row.get("content_sha256")):
            fail("SCRATCH_READER_DOCUMENT_HASH_INVALID")
        documents[slug] = {**projection, "content_sha256": content_hash}
        ids.add(post_id)
    if set(documents) != article_slugs | CORE_PAGES | set(declared):
        fail("SCRATCH_READER_DOCUMENT_SET_INVALID")
    return documents


def reader_page_preparation(
    snapshot: Mapping[str, object],
    *,
    article_slugs: frozenset[str],
    selected_page_slugs: frozenset[str],
) -> dict[str, object]:
    """Prepare only: exact snapshot and explicit candidate page scope, no receipt."""
    if len(canonical(snapshot)) > 16 * 1024 * 1024:
        fail("SCRATCH_READER_SNAPSHOT_TOO_LARGE")
    documents = _reader_documents(
        snapshot, article_slugs=article_slugs, selected_page_slugs=selected_page_slugs
    )
    snapshot_hash = digest(canonical(snapshot).rstrip(b"\n"))
    return {
        "schema": "RAOS_WORDPRESS_READER_PAGE_RESTORE_PREPARATION_V2",
        "publication_profile": "local-scratch-restore-rehearsal",
        "publication_authority": False,
        "production_authority": False,
        "status": "PREPARED_NOT_RESTORED",
        "scratch_only": True,
        "source_snapshot_sha256": snapshot_hash,
        "snapshot_name": f"live-{snapshot_hash}.v1.json",
        "selected_page_slugs": sorted(selected_page_slugs),
        "article_slugs": sorted(article_slugs),
        "document_slugs": sorted(documents),
        "original_id_set": sorted(cast(int, row["id"]) for row in documents.values()),
    }


def _build_reader_restoration(
    snapshot: Mapping[str, object],
    *,
    article_slugs: frozenset[str],
    selected_page_slugs: frozenset[str],
    preparation_sha256: str,
    environment_id: str,
) -> ScratchRestoration:
    preparation = reader_page_preparation(
        snapshot, article_slugs=article_slugs, selected_page_slugs=selected_page_slugs
    )
    if digest(canonical(preparation)) != validate_hash(
        preparation_sha256
    ) or not environment_id.startswith(preparation_sha256[:8] + "-"):
        fail("SCRATCH_RESTORE_PREPARATION_INVALID")
    documents = _reader_documents(
        snapshot, article_slugs=article_slugs, selected_page_slugs=selected_page_slugs
    )
    seed_rows: dict[str, object] = {}
    bodies: dict[str, bytes] = {}
    for slug, source in documents.items():
        body = cast(str, source["block_markup"]).encode()
        if len(body) > 1024 * 1024:
            fail("SCRATCH_READER_BODY_TOO_LARGE")
        if body:
            bodies[slug] = body
        # Only ContentDocument taxonomy IDs are certified by V2. Term labels are
        # scratch scaffolding, not source facts or restored taxonomy definitions.
        terms = source["taxonomies"]
        labels = (
            {
                name: [
                    {
                        "id": term_id,
                        "parent": 0,
                        "name": f"Scratch term {term_id}",
                        "slug": f"scratch-term-{term_id}",
                    }
                    for term_id in cast(list[int], term_ids)
                ]
                for name, term_ids in record(terms).items()
            }
            if type(terms) is dict
            else {}
        )
        seed_rows[slug] = {
            "production_id": source["id"],
            "production_slug": slug,
            "local_slug": slug,
            "post_type": source["post_type"],
            "status": source["status"],
            "title": source["title"],
            "excerpt": source["excerpt"],
            "content_file": f"content/{slug}.html" if body else None,
            "content_sha256": digest(body),
            "source_content_sha256": source["content_sha256"],
            "dates": {},
            "taxonomy_ids": terms,
            "taxonomy_ids_encoding": "object" if type(terms) is dict else "array",
            "taxonomies": labels,
            "media_ids": [],
        }
    seed = canonical(
        {
            "schema": READER_SEED_SCHEMA,
            "publication_profile": "local-scratch-restore-rehearsal",
            "publication_authority": False,
            "production_authority": False,
            "scratch_only": True,
            "environment_id": environment_id,
            "source_preparation_sha256": preparation_sha256,
            "source_snapshot_sha256": preparation["source_snapshot_sha256"],
            "selected_page_slugs": sorted(selected_page_slugs),
            "article_slugs": sorted(article_slugs),
            "reader_page_slugs": sorted(set(documents) - article_slugs - CORE_PAGES),
            "documents": seed_rows,
            "content_documents": documents,
        }
    )
    if len(seed) > 16 * 1024 * 1024:
        fail("SCRATCH_READER_SEED_TOO_LARGE")
    return ScratchRestoration(seed, bodies)


def _verify_reader_restoration(
    expected: ScratchRestoration,
    readback: Mapping[str, object],
) -> dict[str, object]:
    seed = record(json.loads(expected.seed))
    documents = record(seed["content_documents"])
    expected_ids = sorted(cast(int, record(row)["id"]) for row in documents.values())
    wanted = {
        "schema": "RAOS_WORDPRESS_READER_PAGE_RESTORE_READBACK_V2",
        "publication_profile": "local-scratch-restore-rehearsal",
        "publication_authority": False,
        "production_authority": False,
        "scratch_only": True,
        "temporary_environment": True,
        "environment_id": seed["environment_id"],
        "site_url": "http://scratch.wordpress.invalid",
        "source_snapshot_sha256": seed["source_snapshot_sha256"],
        "original_id_set": expected_ids,
        "documents": documents,
    }
    if canonical(readback) != canonical(wanted):
        fail("SCRATCH_READER_READBACK_MISMATCH")
    return {
        "schema": "RAOS_WORDPRESS_READER_PAGE_RESTORE_RECEIPT_V2",
        "publication_profile": "local-scratch-restore-rehearsal",
        "publication_authority": False,
        "production_authority": False,
        "scratch_only": True,
        "temporary_environment": True,
        "environment_id": seed["environment_id"],
        "status": "SCRATCH_CONTENT_DOCUMENT_FIELDS_RESTORED",
        "source_snapshot_sha256": seed["source_snapshot_sha256"],
        "readback_sha256": digest(canonical(readback)),
        "verified_document_count": len(documents),
        "original_id_set": expected_ids,
        "selected_page_slugs": seed["selected_page_slugs"],
        "current_preview_modified": False,
        "production_writes": False,
        "incremental_preview_pass": False,
        "not_restored": [
            "revision_history",
            "author_identity",
            "dates",
            "post_meta",
            "theme",
            "plugins",
            "production_site_options",
        ],
    }
