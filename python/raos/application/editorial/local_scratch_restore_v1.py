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
) -> ScratchRestoration:
    if re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{12}", environment_id) is None:
        fail("SCRATCH_RESTORE_ENVIRONMENT_INVALID")
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
