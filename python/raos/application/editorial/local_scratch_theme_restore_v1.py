"""Replay a files-only child-theme rollback in an isolated restoration scratch."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import PurePosixPath
import re
from typing import cast

from raos.application.editorial.local_scratch_restore_v1 import (
    ScratchRestoration,
    build_scratch_restoration,
    record,
    verify_scratch_restoration,
)
from raos.application.editorial.verified_incremental_v1 import (
    canonical,
    digest,
    fail,
    validate_hash,
)

THEME_SLUG = "kurashinoshirube-child"
MAX_PACKAGE_BYTES = 16 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_FILE_COUNT = 2048
PROFILE = "local-scratch-theme-restore-rehearsal"


def json_document(raw: bytes) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                fail("SCRATCH_THEME_JSON_INVALID")
            result[key] = value
        return result

    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PACKAGE_BYTES:
        fail("SCRATCH_THEME_JSON_INVALID")
    try:
        return record(json.loads(raw, object_pairs_hook=unique))
    except ValueError, UnicodeError, RecursionError:
        fail("SCRATCH_THEME_JSON_INVALID")


def theme_manifest(files: Mapping[str, bytes]) -> list[dict[str, object]]:
    if not 1 <= len(files) <= MAX_FILE_COUNT or "style.css" not in files:
        fail("SCRATCH_THEME_FILES_INVALID")
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    for path, raw in sorted(files.items()):
        if (
            type(path) is not str
            or len(path) > 300
            or re.fullmatch(r"[A-Za-z0-9._/-]+", path) is None
            or path.startswith("/")
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or PurePosixPath(path).as_posix() != path
            or path.casefold() in seen
            or any(
                "/".join(path.split("/")[:index]).casefold() in seen
                for index in range(1, len(path.split("/")))
            )
            or type(raw) is not bytes
            or len(raw) > MAX_FILE_BYTES
        ):
            fail("SCRATCH_THEME_FILES_INVALID")
        seen.add(path.casefold())
        result.append({"path": path, "size": len(raw), "sha256": digest(raw)})
    if sum(len(raw) for raw in files.values()) > MAX_PACKAGE_BYTES:
        fail("SCRATCH_THEME_FILES_INVALID")
    return result


def theme_tree_sha256(files: Mapping[str, bytes]) -> str:
    # Exactly the deployment operator's sorted path/size/content-hash projection.
    return digest(canonical(theme_manifest(files)).rstrip(b"\n"))


def build_theme_package(files: Mapping[str, bytes]) -> bytes:
    manifest = theme_manifest(files)
    raw = canonical(
        {
            "schema": "RAOS_WORDPRESS_SCRATCH_THEME_PACKAGE_V1",
            "theme_slug": THEME_SLUG,
            "tree_sha256": theme_tree_sha256(files),
            "files": [
                {
                    **row,
                    "contents_b64": base64.b64encode(
                        files[cast(str, row["path"])]
                    ).decode("ascii"),
                }
                for row in manifest
            ],
        }
    )
    if len(raw) > MAX_PACKAGE_BYTES:
        fail("SCRATCH_THEME_PACKAGE_TOO_LARGE")
    return raw


def parse_theme_package(raw: bytes) -> dict[str, bytes]:
    package = json_document(raw)
    if (
        set(package) != {"schema", "theme_slug", "tree_sha256", "files"}
        or package["schema"] != "RAOS_WORDPRESS_SCRATCH_THEME_PACKAGE_V1"
        or package["theme_slug"] != THEME_SLUG
        or type(package["files"]) is not list
    ):
        fail("SCRATCH_THEME_PACKAGE_INVALID")
    files: dict[str, bytes] = {}
    for value in cast(list[object], package["files"]):
        row = record(value)
        if set(row) != {"path", "size", "sha256", "contents_b64"}:
            fail("SCRATCH_THEME_PACKAGE_INVALID")
        path, encoded = row["path"], row["contents_b64"]
        if type(path) is not str or path in files or type(encoded) is not str:
            fail("SCRATCH_THEME_PACKAGE_INVALID")
        try:
            files[path] = base64.b64decode(encoded, validate=True)
        except ValueError, binascii.Error:
            fail("SCRATCH_THEME_PACKAGE_INVALID")
    # Exact serialization comparison rejects altered sizes, hashes, types or order.
    if build_theme_package(files) != raw:
        fail("SCRATCH_THEME_PACKAGE_INVALID")
    return files


@dataclass(frozen=True)
class ScratchThemeRestoration:
    preparation: bytes
    content: ScratchRestoration
    baseline_package: bytes
    candidate_package: bytes
    content_receipt: bytes


def build_scratch_theme_restoration(
    snapshot: Mapping[str, object],
    *,
    article_slugs: frozenset[str],
    content_receipt_raw: bytes,
    content_readback_raw: bytes,
    baseline_package_raw: bytes,
    candidate_package_raw: bytes,
) -> ScratchThemeRestoration:
    receipt = json_document(content_receipt_raw)
    environment_id = receipt.get("environment_id")
    if type(environment_id) is not str:
        fail("SCRATCH_THEME_RESTORE_INVALID")
    content = build_scratch_restoration(
        snapshot,
        article_slugs=article_slugs,
        preparation_sha256=validate_hash(receipt.get("source_preparation_sha256")),
        environment_id=environment_id,
    )
    expected_receipt = verify_scratch_restoration(
        content, json_document(content_readback_raw)
    )
    if type(receipt.get("verified_at")) is not str or canonical(receipt) != canonical(
        {**expected_receipt, "verified_at": receipt["verified_at"]}
    ):
        fail("SCRATCH_THEME_CONTENT_RECEIPT_INVALID")
    baseline = parse_theme_package(baseline_package_raw)
    candidate = parse_theme_package(candidate_package_raw)
    deployment = record(snapshot.get("deployment_status"))
    theme = record(deployment.get("theme"))
    if (
        deployment.get("schema") != "RAOS_WORDPRESS_DEPLOYMENT_BASELINE_SNAPSHOT_V1"
        or deployment.get("source") != "BOUNDED_WORDPRESS_DEPLOYMENT_MCP"
        or deployment.get("status") != "CAPTURED_READ_ONLY"
        or theme.get("slug") != THEME_SLUG
        or theme.get("active") is not True
        or theme.get("tree_sha256") != theme_tree_sha256(baseline)
        or theme_tree_sha256(candidate) == theme_tree_sha256(baseline)
    ):
        fail("SCRATCH_THEME_BASELINE_INVALID")
    preparation = canonical(
        {
            "schema": "RAOS_WORDPRESS_SCRATCH_THEME_RESTORE_PREPARATION_V1",
            "publication_profile": PROFILE,
            "publication_authority": False,
            "production_authority": False,
            "scratch_only": True,
            "environment_id": environment_id,
            "theme_slug": THEME_SLUG,
            "source_snapshot_sha256": expected_receipt["source_snapshot_sha256"],
            "content_seed_sha256": digest(content.seed),
            "content_restore_receipt_sha256": digest(content_receipt_raw),
            "baseline_package_sha256": digest(baseline_package_raw),
            "candidate_package_sha256": digest(candidate_package_raw),
            "baseline_tree_sha256": theme_tree_sha256(baseline),
            "candidate_tree_sha256": theme_tree_sha256(candidate),
            "baseline_file_manifest": theme_manifest(baseline),
            "candidate_file_manifest": theme_manifest(candidate),
            "operation": "SAME_BASENAME_FILES_ONLY_NO_ACTIVATION",
        }
    )
    return ScratchThemeRestoration(
        preparation,
        content,
        baseline_package_raw,
        candidate_package_raw,
        content_receipt_raw,
    )


def verify_scratch_theme_restoration(
    expected: ScratchThemeRestoration,
    readback: Mapping[str, object],
) -> dict[str, object]:
    preparation = json_document(expected.preparation)
    fixed = {
        "schema": "RAOS_WORDPRESS_SCRATCH_THEME_RESTORE_READBACK_V1",
        "publication_profile": PROFILE,
        "publication_authority": False,
        "production_authority": False,
        "scratch_only": True,
        "temporary_environment": True,
        "environment_id": preparation["environment_id"],
        "preparation_sha256": digest(expected.preparation),
        "theme_slug": THEME_SLUG,
        "site_url": "http://scratch.wordpress.invalid",
        "operation": "SAME_BASENAME_FILES_ONLY_NO_ACTIVATION",
    }
    if set(readback) != set(fixed) | {"stages"} or canonical(
        {key: readback[key] for key in fixed}
    ) != canonical(fixed):
        fail("SCRATCH_THEME_READBACK_INVALID")
    stages = readback["stages"]
    if type(stages) is not list:
        fail("SCRATCH_THEME_READBACK_INVALID")
    stage_rows = cast(list[object], stages)
    if len(stage_rows) != 3:
        fail("SCRATCH_THEME_READBACK_INVALID")
    option_hashes: set[str] = set()
    for value, name, key in zip(
        stage_rows,
        ("baseline_before", "candidate_installed", "baseline_restored"),
        ("baseline", "candidate", "baseline"),
        strict=True,
    ):
        stage = record(value)
        if set(stage) != {
            "stage",
            "theme_tree_sha256",
            "file_manifest",
            "content_readback",
            "wordpress_options_sha256",
        }:
            fail("SCRATCH_THEME_STAGE_INVALID")
        if (
            stage["stage"] != name
            or stage["theme_tree_sha256"] != preparation[f"{key}_tree_sha256"]
            or canonical(stage["file_manifest"])
            != canonical(preparation[f"{key}_file_manifest"])
        ):
            fail("SCRATCH_THEME_TREE_MISMATCH")
        verify_scratch_restoration(expected.content, record(stage["content_readback"]))
        option_hashes.add(validate_hash(stage["wordpress_options_sha256"]))
    if len(option_hashes) != 1:
        fail("SCRATCH_THEME_OPTIONS_CHANGED")
    return {
        "schema": "RAOS_WORDPRESS_SCRATCH_THEME_RESTORE_RECEIPT_V1",
        "publication_profile": PROFILE,
        "status": "THEME_ROLLBACK_STORED_FIELDS_VERIFIED",
        "publication_authority": False,
        "production_authority": False,
        "scratch_only": True,
        "temporary_environment": True,
        "environment_id": preparation["environment_id"],
        "source_snapshot_sha256": preparation["source_snapshot_sha256"],
        "content_restore_receipt_sha256": digest(expected.content_receipt),
        "preparation_sha256": digest(expected.preparation),
        "readback_sha256": digest(canonical(readback)),
        "baseline_tree_sha256": preparation["baseline_tree_sha256"],
        "candidate_tree_sha256": preparation["candidate_tree_sha256"],
        "restored_tree_sha256": preparation["baseline_tree_sha256"],
        "baseline_package_sha256": digest(expected.baseline_package),
        "candidate_package_sha256": digest(expected.candidate_package),
        "verified_document_count": 14,
        "wordpress_options_unchanged": True,
        "wordpress_options_sha256": next(iter(option_hashes)),
        "activation_changed": False,
        "current_preview_modified": False,
        "production_writes": False,
        "ports_published": False,
        "network": "dedicated_internal",
        "operation": preparation["operation"],
        "verified_noncontent_rollback_targets": ["theme"],
        "not_restored": [
            "production_site_options",
            "plugins",
            "revision_history",
            "author_identity",
            "post_meta",
        ],
    }
