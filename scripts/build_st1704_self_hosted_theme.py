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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_editorial_measurement_v1 as measurement_owner  # noqa: E402
from scripts import (  # noqa: E402
    build_editorial_v3_theme_navigation as editorial_navigation_owner,
)
from scripts import build_st1704_theme_assets as theme_asset_owner  # noqa: E402


THEME_SLUG: Final = "kurashinoshirube-child"
THEME_VERSION: Final = "1.4.0"
THEME_RUNTIME_REVISION: Final = (
    "9d514cb4237cf2b0af40e514eb870ea54d1a80647835d2b41d3bee545ff8a019"
)
RUNTIME_STYLESHEET_SENTINELS: Final = {
    "assets/theme.css": "--raos-theme-runtime-revision-base",
    "assets/editorial-v2.css": "--raos-theme-runtime-revision-editorial-v2",
}
THEME_REPOSITORY_ROOT: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)
THEME_ROOT: Final = ROOT / THEME_REPOSITORY_ROOT
OUTPUT_DIRECTORY: Final = ROOT / ".secrets/st1704-self-hosted-editorial-pilot/theme"
OUTPUT_PATH: Final = OUTPUT_DIRECTORY / f"{THEME_SLUG}-{THEME_VERSION}.zip"
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
MAX_PACKAGE_BYTES: Final = 16 * 1024 * 1024
ZIP_TIMESTAMP: Final = (2026, 8, 23, 0, 0, 0)

EDITORIAL_NAVIGATION_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/editorial-navigation.v3.json"
)
PORTABLE_POWER_ASSET_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/images/article-portable-power-guide.webp"
)
MEASUREMENT_CLIENT_INPUT_PATH: Final = THEME_REPOSITORY_ROOT / "assets/measurement.js"
THEME_FUNCTIONS_INPUT_PATH: Final = THEME_REPOSITORY_ROOT / "functions.php"
THEME_SOURCE_INPUT_PATHS: Final = (
    EDITORIAL_NAVIGATION_INPUT_PATH,
    THEME_REPOSITORY_ROOT / "assets/editorial-v2.css",
    PORTABLE_POWER_ASSET_INPUT_PATH,
    THEME_REPOSITORY_ROOT / "assets/images/article-suitcase-guide.webp",
    THEME_REPOSITORY_ROOT / "assets/images/brand-mark.svg",
    THEME_REPOSITORY_ROOT / "assets/images/home-hero.webp",
    MEASUREMENT_CLIENT_INPUT_PATH,
    THEME_REPOSITORY_ROOT / "assets/theme.css",
    THEME_FUNCTIONS_INPUT_PATH,
    THEME_REPOSITORY_ROOT / "parts/footer.html",
    THEME_REPOSITORY_ROOT / "parts/header.html",
    THEME_REPOSITORY_ROOT / "raos-assets.v1.json",
    THEME_REPOSITORY_ROOT / "style.css",
    THEME_REPOSITORY_ROOT / "templates/front-page.html",
    THEME_REPOSITORY_ROOT / "templates/single.html",
    THEME_REPOSITORY_ROOT / "theme-contract.v1.json",
    THEME_REPOSITORY_ROOT / "theme.json",
)
SOURCE_FILES: Final = tuple(
    path.relative_to(THEME_REPOSITORY_ROOT).as_posix()
    for path in THEME_SOURCE_INPUT_PATHS
)

PUBLIC_LISTING_ELIGIBILITY: Final = {
    "candidate_query": {
        "max_candidates_per_slot": 2,
        "max_rows": 20,
        "post_type": "post",
        "query_limit": 21,
        "slug_classes": [
            "raos-review-*",
            "editorial_v2_publication_bindings[].slug",
            'raw_content_prefix:<div class="raos-editorial-v2">',
        ],
        "slot_count": 10,
    },
    "candidate_overflow_policy": "LOOKUP_FAILURE_WHEN_RESULT_COUNT_EXCEEDS_MAX_ROWS",
    "consumers": {
        "front_page_latest_posts": {
            "additional_exclusion": "FIXED_FEATURED_POST_WHEN_ELIGIBLE",
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
            "slug_class": "PORTFOLIO_FINAL",
            "snapshot_state": "PUBLIC_ARTICLE_IDENTITY_MISSING_OR_MISMATCH",
        },
        {
            "eligible": True,
            "slug_class": "PORTFOLIO_FINAL",
            "snapshot_state": (
                "EXACT_STORED_SNAPSHOT_OR_EDITORIAL_V2_PUBLISHED_IDENTITY"
            ),
        },
        {
            "eligible": True,
            "slug_class": "UNRELATED_POST",
            "snapshot_state": "NOT_EVALUATED",
        },
    ],
    "query_cache": "REQUEST_LOCAL_ONLY",
    "snapshot_validator": "kurashinoshirube_public_article_identity(post_id)",
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

EDITORIAL_V2_PRESENTATION: Final = {
    "asset": "assets/editorial-v2.css",
    "base_style_dependency": "kurashinoshirube-editorial",
    "body_class": "raos-editorial-v2-page",
    "category_fallback_allowlist": ["移動", "家事", "備え"],
    "content_root": '<div class="raos-editorial-v2">',
    "detection": "EXACT_RAW_CONTENT_PREFIX_ON_SINGULAR_POST",
    "publication_identity_predicate": (
        "PUBLISH_POST_EXACT_SINGLE_EDITORIAL_V2_ROOT_AND_CLOSED_SLUG_ARTICLE_ID_MATCH"
    ),
    "publication_snapshot_required": False,
    "scope": "ORDINARY_WORDPRESS_POST_ONLY",
    "section_binding_count": 10,
    "section_binding_source": "assets/editorial-navigation.v3.json#articles",
}

POLICY_V3_PRESENTATION: Final = {
    "body_class": "raos-policy-v3-page",
    "detection": (
        "EXACT_PUBLISHED_PAGE_SLUG_TITLE_AND_EXCERPT_MATCH_CLOSED_HEAD_MAP"
    ),
    "footer_presentation": "SAME_RICH_RESPONSIVE_FOOTER_AS_HOME_AND_EDITORIAL_V2",
    "scope": "EXACT_THREE_REVIEWED_WORDPRESS_POLICY_PAGES_ONLY",
    "slugs": ["about-ad-policy", "comparison-policy", "privacy-policy"],
}


class ThemeBuildFailure(RuntimeError):
    """Closed source or package validation failure."""


def _fail() -> NoReturn:
    raise ThemeBuildFailure("SELF_HOSTED_EDITORIAL_THEME_INVALID") from None


def _validate_owner_bindings() -> None:
    measurement_inputs = set(measurement_owner.RUNTIME_INPUT_PATHS)
    if (
        editorial_navigation_owner.OUTPUT.relative_to(ROOT)
        != EDITORIAL_NAVIGATION_INPUT_PATH
        or theme_asset_owner.OUTPUT.relative_to(ROOT)
        != PORTABLE_POWER_ASSET_INPUT_PATH
        or not {
            MEASUREMENT_CLIENT_INPUT_PATH,
            THEME_FUNCTIONS_INPUT_PATH,
        }.issubset(measurement_inputs)
    ):
        _fail()


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
    _validate_owner_bindings()
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
    if "暮らしの選択に、<br>たしかな道しるべを。" not in front_page:
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
        "kurashinoshirube_is_policy_v3_page",
        "'raos-policy-v3-page'",
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
    php_runtime_revision = re.findall(
        r"^const KURASHINOSHIRUBE_THEME_RUNTIME_REVISION = '([0-9a-f]{64})';$",
        php,
        flags=re.MULTILINE,
    )
    if php_runtime_revision != [THEME_RUNTIME_REVISION]:
        _fail()
    for relative, property_name in RUNTIME_STYLESHEET_SENTINELS.items():
        source = _text(relative)
        declaration = f"{property_name}: {THEME_RUNTIME_REVISION};"
        if source.count(property_name) != 1 or source.count(declaration) != 1:
            _fail()

    theme_json = _json("theme.json")
    if theme_json.get("version") != 3:
        _fail()
    contract = _json("theme-contract.v1.json")
    if (
        contract.get("schema") != "SELF_HOSTED_EDITORIAL_THEME_CONTRACT_V1"
        or contract.get("theme_version") != THEME_VERSION
        or contract.get("runtime_evidence")
        != {
            "revision": THEME_RUNTIME_REVISION,
            "stylesheets": RUNTIME_STYLESHEET_SENTINELS,
        }
        or contract.get("publication_authority") != "NONE"
        or contract.get("editorial_v2") != EDITORIAL_V2_PRESENTATION
        or contract.get("policy_v3") != POLICY_V3_PRESENTATION
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
    navigation_contract = contract.get("editorial_navigation")
    navigation = _json("assets/editorial-navigation.v3.json")
    navigation_payload = _read_source("assets/editorial-navigation.v3.json")
    navigation_digest = hashlib.sha256(navigation_payload).hexdigest()
    if (
        navigation_contract
        != {
            "article_count": 10,
            "cluster_count": 3,
            "generated_by": "scripts/build_editorial_v3_theme_navigation.py",
            "path": "assets/editorial-navigation.v3.json",
            "schema": "RAOS_EDITORIAL_THEME_NAVIGATION_V3",
            "sha256": navigation_digest,
            "source_navigation_sha256": navigation.get("source_navigation_sha256"),
            "source_portfolio_sha256": navigation.get("source_portfolio_sha256"),
        }
        or navigation.get("schema") != "RAOS_EDITORIAL_THEME_NAVIGATION_V3"
        or navigation.get("target_origin") != "https://kurashinoshirube.com"
        or navigation.get("version") != "3.0.0"
        or type(navigation.get("articles")) is not list
        or len(navigation["articles"]) != 10
        or type(navigation.get("clusters")) is not list
        or len(navigation["clusters"]) != 3
        or len({row.get("article_id") for row in navigation["articles"]}) != 10
        or any(
            type(row) is not dict
            or type(row.get("related_articles")) is not list
            or len(row["related_articles"]) < 2
            for row in navigation["articles"]
        )
    ):
        _fail()
    php_path_match = re.search(
        r"const KURASHINOSHIRUBE_EDITORIAL_NAVIGATION_PATH = '([^']+)';",
        php,
    )
    php_hash_match = re.search(
        r"const KURASHINOSHIRUBE_EDITORIAL_NAVIGATION_SHA256 = '([0-9a-f]{64})';",
        php,
    )
    if (
        php_path_match is None
        or php_path_match.group(1) != "assets/editorial-navigation.v3.json"
        or php_hash_match is None
        or php_hash_match.group(1) != navigation_digest
        or "KURASHINOSHIRUBE_RELATED_ARTICLE_MAP_JSON" in php
        or "KURASHINOSHIRUBE_HOMEPAGE_CLUSTERS_JSON" in php
    ):
        _fail()
    related = contract.get("related_navigation")
    if related != {
        "availability_transition": "TARGET_HUMAN_PUBLICATION_ONLY",
        "content_hash_scope": "THEME_CHROME_OUTSIDE_WORDPRESS_POST_CONTENT",
        "minimum_targets_per_article": 2,
        "owner": "EDITORIAL_V3_GENERATED_NAVIGATION",
        "preparedness_two_article_policy": (
            "ONE_SAME_CLUSTER_PLUS_ONE_ADJACENT_CONTEXT_WITHOUT_NEW_ARTICLE"
        ),
        "source": (
            "assets/editorial-navigation.v3.json#articles[].related_articles"
        ),
        "target_requirement": (
            "PUBLISHED_EXACT_SAME_ORIGIN_PERMALINK_WITH_CLOSED_PUBLIC_ARTICLE_IDENTITY"
        ),
    }:
        _fail()
    homepage = contract.get("homepage_clusters")
    if homepage != {
        "article_count": 10,
        "cluster_count": 3,
        "link_requirement": (
            "PUBLISHED_EXACT_SAME_ORIGIN_PERMALINK_WITH_CLOSED_PUBLIC_ARTICLE_IDENTITY"
        ),
        "owner": "EDITORIAL_V3_GENERATED_NAVIGATION",
        "source": "assets/editorial-navigation.v3.json#clusters",
    }:
        _fail()
    if contract.get("homepage_featured") != {
        "article_id": "st1704-portable-power-station-guide",
        "exclude_from_latest": True,
        "local_preview_substitute": "LATEST_SYNTHETIC_POST_LAYOUT_ONLY",
        "selection": "FIXED_ARTICLE_ID_WITH_EXACT_PUBLIC_ARTICLE_IDENTITY",
    }:
        _fail()
    assets = _json("raos-assets.v1.json")
    if (
        assets.get("schema") != "SELF_HOSTED_EDITORIAL_THEME_ASSETS_V1"
        or assets.get("theme_version") != THEME_VERSION
        or assets.get("theme_runtime_revision") != THEME_RUNTIME_REVISION
    ):
        _fail()

    _validate_webp("assets/images/article-portable-power-guide.webp")
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
