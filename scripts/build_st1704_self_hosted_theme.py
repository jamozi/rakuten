#!/usr/bin/env python3
"""Validate and deterministically package the ST-1704 WordPress child theme."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile
from typing import Final, NoReturn
from xml.etree import ElementTree


ROOT: Final = Path(__file__).resolve().parents[1]
THEME_SLUG: Final = "kurashinoshirube-child"
THEME_VERSION: Final = "1.3.6"
THEME_ROOT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme" / THEME_SLUG
)
OUTPUT_DIRECTORY: Final = ROOT / ".secrets/st1704-self-hosted-editorial-pilot/theme"
OUTPUT_PATH: Final = OUTPUT_DIRECTORY / f"{THEME_SLUG}-{THEME_VERSION}.zip"
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
MAX_PACKAGE_BYTES: Final = 16 * 1024 * 1024
ZIP_TIMESTAMP: Final = (2026, 8, 23, 0, 0, 0)

SOURCE_FILES: Final = (
    "assets/images/article-suitcase-guide.webp",
    "assets/images/brand-mark.svg",
    "assets/images/home-hero.webp",
    "assets/theme.css",
    "functions.php",
    "parts/footer.html",
    "parts/header.html",
    "raos-assets.v1.json",
    "style.css",
    "templates/front-page.html",
    "templates/single.html",
    "theme-contract.v1.json",
    "theme.json",
)

PUBLIC_LISTING_ELIGIBILITY: Final = {
    "candidate_query": {
        "max_candidates_per_slot": 2,
        "max_rows": 10,
        "post_type": "post",
        "query_limit": 11,
        "slug_classes": [
            "raos-review-*",
            "snapshot.article_bindings[].slug",
        ],
        "slot_count": 5,
    },
    "candidate_overflow_policy": "LOOKUP_FAILURE_WHEN_RESULT_COUNT_EXCEEDS_MAX_ROWS",
    "consumers": {
        "front_page_latest_posts": {
            "filter": "query_loop_block_query_vars",
            "merge_target": "post__not_in",
        },
        "yoast_sitemap": {
            "filter": "wpseo_exclude_from_sitemap_by_post_ids",
        },
    },
    "existing_exclusion_policy": "PRESERVE_POSITIVE_POST_IDS_AND_DEDUPLICATE",
    "lookup_failure_policy": "SUPPRESS_POST_SITEMAP_AND_FRONT_PAGE_POST_RESULTS",
    "lookup_success_requirement": "GET_RESULTS_ARRAY_AND_WPDB_LAST_ERROR_EMPTY_STRING",
    "matrix": [
        {
            "eligible": False,
            "slug_class": "RAOS_REVIEW",
            "snapshot_state": "ANY",
        },
        {
            "eligible": False,
            "slug_class": "ALLOWLISTED_FINAL",
            "snapshot_state": "MISSING_INVALID_OR_ARTICLE_ID_MISMATCH",
        },
        {
            "eligible": True,
            "slug_class": "ALLOWLISTED_FINAL",
            "snapshot_state": "EXACT_PUBLISHED_BOUND_MATCHING_ARTICLE_ID",
        },
        {
            "eligible": True,
            "slug_class": "UNRELATED_POST",
            "snapshot_state": "NOT_EVALUATED",
        },
    ],
    "query_cache": "REQUEST_LOCAL_ONLY",
    "snapshot_validator": "kurashinoshirube_bound_post_snapshot(post_id,false)",
}

DOCUMENT_TITLE_DEDUPLICATION: Final = {
    "active_when": "WPSEO_VERSION_DEFINED",
    "hook": "wp_head",
    "hook_priority": 0,
    "removed_priority_1_callbacks": [
        "_wp_render_title_tag",
        "_block_template_render_title_tag",
        "gutenberg_render_title_tag",
    ],
}


class ThemeBuildFailure(RuntimeError):
    """Closed source or package validation failure."""


def _fail() -> NoReturn:
    raise ThemeBuildFailure("SELF_HOSTED_EDITORIAL_THEME_INVALID") from None


def _safe_relative(value: str) -> PurePosixPath:
    if type(value) is not str or not value or value != value.strip() or "\\" in value:
        _fail()
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail()
    return relative


def _read_source(relative: str) -> bytes:
    safe = _safe_relative(relative)
    path = THEME_ROOT.joinpath(*safe.parts)
    try:
        metadata = path.lstat()
    except OSError:
        _fail()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > MAX_SOURCE_BYTES
    ):
        _fail()
    try:
        payload = path.read_bytes()
    except OSError:
        _fail()
    if len(payload) != metadata.st_size:
        _fail()
    return payload


def _text(relative: str) -> str:
    try:
        return _read_source(relative).decode("utf-8")
    except UnicodeDecodeError:
        _fail()


def _json(relative: str) -> dict[str, object]:
    try:
        value = json.loads(_text(relative))
    except json.JSONDecodeError:
        _fail()
    if type(value) is not dict:
        _fail()
    return value


def _validate_exact_tree() -> None:
    try:
        metadata = THEME_ROOT.lstat()
    except OSError:
        _fail()
    if THEME_ROOT.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        _fail()
    observed: list[str] = []
    try:
        candidates = sorted(THEME_ROOT.rglob("*"))
    except OSError:
        _fail()
    for candidate in candidates:
        try:
            item = candidate.lstat()
        except OSError:
            _fail()
        if candidate.is_symlink():
            _fail()
        if stat.S_ISDIR(item.st_mode):
            continue
        if not stat.S_ISREG(item.st_mode):
            _fail()
        observed.append(candidate.relative_to(THEME_ROOT).as_posix())
    if tuple(observed) != SOURCE_FILES:
        _fail()


def _validate_webp(relative: str) -> None:
    payload = _read_source(relative)
    if (
        len(payload) < 20
        or payload[:4] != b"RIFF"
        or payload[8:12] != b"WEBP"
        or int.from_bytes(payload[4:8], "little") != len(payload) - 8
        or b"ANIM" in payload[:128]
        or b"ANMF" in payload
    ):
        _fail()


def _validate_svg() -> None:
    payload = _read_source("assets/images/brand-mark.svg")
    lowered = payload.lower()
    if (
        b"<!doctype" in lowered
        or b"<!entity" in lowered
        or b"<script" in lowered
        or b"foreignobject" in lowered
        or b"javascript:" in lowered
    ):
        _fail()
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        _fail()
    if root.tag not in {"svg", "{http://www.w3.org/2000/svg}svg"}:
        _fail()
    for element in root.iter():
        for attribute, value in element.attrib.items():
            local = attribute.rsplit("}", 1)[-1].lower()
            if local.startswith("on") or local in {"href", "src"}:
                if value and not value.startswith("#"):
                    _fail()


def validate_sources() -> dict[str, str]:
    _validate_exact_tree()
    sources = {relative: _read_source(relative) for relative in SOURCE_FILES}
    style = _text("style.css")
    if (
        "Theme Name: 暮らしのしるべ Child" not in style
        or f"Version: {THEME_VERSION}" not in style
        or "Template:" not in style
    ):
        _fail()
    front_page = _text("templates/front-page.html")
    single = _text("templates/single.html")
    if (
        "<span>暮らしの道具を、</span><span>根拠から選ぶ。</span>"
        not in front_page
    ):
        _fail()
    if single.count("wp:post-title") != 1:
        _fail()
    if "subscribe" in (_text("parts/footer.html") + front_page).lower():
        _fail()

    css = _text("assets/theme.css")
    for token in (
        ":focus-visible",
        "prefers-reduced-motion",
        "overflow-x",
        "@media",
    ):
        if token not in css:
            _fail()

    php = _text("functions.php")
    required_php = (
        "_raos_publication_snapshot_v1",
        "KURASHINOSHIRUBE_THEME_VERSION",
        "wpseo_json_ld_output",
        "wpseo_title",
        "wpseo_metadesc",
        "wpseo_canonical",
        "wpseo_robots",
        "kurashinoshirube_select_document_title_owner",
        "'_wp_render_title_tag'",
        "'_block_template_render_title_tag'",
        "'gutenberg_render_title_tag'",
        "remove_action('wp_head', $callback, 1)",
        "wpseo_exclude_from_sitemap_by_post_ids",
        "query_loop_block_query_vars",
        "kurashinoshirube_public_listing_post_is_eligible",
        "kurashinoshirube_public_listing_excluded_post_ids",
        "KURASHINOSHIRUBE_EXISTING_UPDATE_ACTION",
        "kurashinoshirube_handle_existing_update",
    )
    if not all(token in php for token in required_php):
        _fail()
    forbidden_php = (
        "eval(",
        "base64_decode(",
        "shell_exec(",
        "wp_remote_",
        "curl_",
        "$_GET",
        "$_POST",
        "$_REQUEST",
    )
    if any(token in php for token in forbidden_php):
        _fail()
    php_theme_version = re.search(
        r"const KURASHINOSHIRUBE_THEME_VERSION = '([^']+)';",
        php,
    )
    if (
        php_theme_version is None
        or php_theme_version.group(1) != THEME_VERSION
        or "$theme->get('Version') !== KURASHINOSHIRUBE_THEME_VERSION" not in php
    ):
        _fail()

    theme_json = _json("theme.json")
    if theme_json.get("version") != 3:
        _fail()
    contract = _json("theme-contract.v1.json")
    if (
        contract.get("schema") != "SELF_HOSTED_EDITORIAL_THEME_CONTRACT_V1"
        or contract.get("theme_version") != THEME_VERSION
        or contract.get("publication_authority") != "NONE"
        or contract.get("head", {}).get("document_title_deduplication")
        != DOCUMENT_TITLE_DEDUPLICATION
        or contract.get("head", {}).get("document_title_owner")
        != "YOAST_WHEN_ACTIVE_OTHERWISE_WORDPRESS_OR_GUTENBERG_FALLBACK"
        or contract.get("public_listing_eligibility") != PUBLIC_LISTING_ELIGIBILITY
        or not isinstance(contract.get("snapshot"), dict)
        or contract["snapshot"].get("excerpt_binding")
        != "EXACT_WORDPRESS_POST_EXCERPT_EQUALS_DESCRIPTION_RAW_UTF8"
        or not isinstance(contract.get("human_existing_update"), dict)
    ):
        _fail()
    related = contract.get("related_navigation")
    if type(related) is not dict or type(related.get("map")) is not dict:
        _fail()
    relation_bytes = json.dumps(
        related["map"],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if related.get("map_sha256") != hashlib.sha256(relation_bytes).hexdigest():
        _fail()
    php_map_match = re.search(
        r"const KURASHINOSHIRUBE_RELATED_ARTICLE_MAP_JSON = '([^']+)';",
        php,
    )
    php_hash_match = re.search(
        r"const KURASHINOSHIRUBE_RELATED_ARTICLE_MAP_SHA256 = '([0-9a-f]{64})';",
        php,
    )
    if (
        php_map_match is None
        or php_hash_match is None
        or php_map_match.group(1).encode("utf-8") != relation_bytes
        or php_hash_match.group(1) != related["map_sha256"]
    ):
        _fail()
    homepage = contract.get("homepage_clusters")
    if type(homepage) is not dict or type(homepage.get("config")) is not dict:
        _fail()
    homepage_bytes = json.dumps(
        homepage["config"],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    homepage_map = homepage["config"].get("clusters")
    homepage_order = homepage["config"].get("display_order")
    homepage_json_match = re.search(
        r"const KURASHINOSHIRUBE_HOMEPAGE_CLUSTERS_JSON = '([^']+)';",
        php,
    )
    homepage_hash_match = re.search(
        r"const KURASHINOSHIRUBE_HOMEPAGE_CLUSTERS_SHA256 = '([0-9a-f]{64})';",
        php,
    )
    if (
        type(homepage_map) is not dict
        or type(homepage_order) is not list
        or len(homepage_order) != 3
        or any(type(cluster_id) is not str for cluster_id in homepage_order)
        or len(set(homepage_order)) != 3
        or set(homepage_order) != set(homepage_map)
        or homepage.get("config_sha256") != hashlib.sha256(homepage_bytes).hexdigest()
        or homepage_json_match is None
        or homepage_hash_match is None
        or homepage_json_match.group(1).encode("utf-8") != homepage_bytes
        or homepage_hash_match.group(1) != homepage["config_sha256"]
    ):
        _fail()
    assets = _json("raos-assets.v1.json")
    if (
        assets.get("schema") != "SELF_HOSTED_EDITORIAL_THEME_ASSETS_V1"
        or assets.get("theme_version") != THEME_VERSION
    ):
        _fail()

    _validate_webp("assets/images/article-suitcase-guide.webp")
    _validate_webp("assets/images/home-hero.webp")
    _validate_svg()
    return {
        relative: hashlib.sha256(payload).hexdigest()
        for relative, payload in sources.items()
    }


def build_package() -> bytes:
    validate_sources()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for relative in SOURCE_FILES:
            info = zipfile.ZipInfo(f"{THEME_SLUG}/{relative}", ZIP_TIMESTAMP)
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, _read_source(relative))
    payload = output.getvalue()
    if not payload or len(payload) > MAX_PACKAGE_BYTES:
        _fail()
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        expected = [f"{THEME_SLUG}/{relative}" for relative in SOURCE_FILES]
        if archive.namelist() != expected:
            _fail()
        if any(
            archive.read(name) != _read_source(name.split("/", 1)[1])
            for name in expected
        ):
            _fail()
    return payload


def _write_package(payload: bytes) -> None:
    try:
        OUTPUT_DIRECTORY.mkdir(mode=0o700, parents=True, exist_ok=True)
        if OUTPUT_DIRECTORY.is_symlink():
            _fail()
        os.chmod(OUTPUT_DIRECTORY, 0o700)
        temporary = OUTPUT_DIRECTORY / f".{OUTPUT_PATH.name}.{os.getpid()}.tmp"
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, OUTPUT_PATH)
        os.chmod(OUTPUT_PATH, 0o600)
    except OSError, ThemeBuildFailure:
        _fail()


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument("--source-check", action="store_true")
    commands.add_argument("--package", action="store_true")
    commands.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.source_check:
            validate_sources()
            print("SELF_HOSTED_EDITORIAL_THEME_SOURCE_OK")
            return 0
        first = build_package()
        second = build_package()
        if first != second:
            _fail()
        digest = hashlib.sha256(first).hexdigest()
        package_mode = arguments.package or not arguments.check
        if package_mode:
            _write_package(first)
            print(
                json.dumps(
                    {
                        "artifact": OUTPUT_PATH.as_posix(),
                        "bytes": len(first),
                        "publication_authority": "NONE",
                        "sha256": digest,
                    },
                    sort_keys=True,
                )
            )
        else:
            print(f"SELF_HOSTED_EDITORIAL_THEME_OK sha256={digest}")
        return 0
    except ThemeBuildFailure as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
