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
from typing import Final, Mapping, NoReturn
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
THEME_VERSION: Final = "1.5.1"
THEME_RUNTIME_REVISION: Final = (
    "b5bd9b8add7d062ccf6322e12196cd87c7e1c9ea3978a4e440bdc99a82d28513"
)
RUNTIME_STYLESHEET_SENTINELS: Final = {
    "assets/theme.css": "--raos-theme-runtime-revision-base",
    "assets/editorial-v2.css": "--raos-theme-runtime-revision-editorial-v2",
}
THEME_REPOSITORY_ROOT: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)
THEME_ROOT: Final = ROOT / THEME_REPOSITORY_ROOT
THEME_BUILDER_SOURCE_PATH: Final = ROOT / "scripts/build_st1704_self_hosted_theme.py"
DESIGN_HANDOFF_PATH: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/DESIGN_HANDOFF_V1.yaml"
)
OPERATIONS_RUNBOOK_PATH: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/OPERATIONS_RUNBOOK.md"
)
OUTPUT_DIRECTORY: Final = ROOT / ".secrets/st1704-self-hosted-editorial-pilot/theme"
OUTPUT_PATH: Final = OUTPUT_DIRECTORY / f"{THEME_SLUG}-{THEME_VERSION}.zip"
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
MAX_PACKAGE_BYTES: Final = 16 * 1024 * 1024
ZIP_TIMESTAMP: Final = (2026, 8, 23, 0, 0, 0)

EDITORIAL_NAVIGATION_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/editorial-navigation.v3.json"
)
ANKER_GENERATIONS_ASSET_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/images/article-anker-solix-generations.webp"
)
PORTABLE_POWER_ASSET_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/images/article-portable-power-guide.webp"
)
DISHWASHER_ASSET_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/images/article-countertop-dishwasher-guide.webp"
)
ROBOT_VACUUM_ASSET_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/images/article-robot-vacuum-guide.webp"
)
ROOMBA_K11_ASSET_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/images/article-roomba-mini-k11-comparison.webp"
)
SOLOTA_RAKUA_ASSET_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/images/article-solota-rakua-replacement.webp"
)
HOME_HERO_ASSET_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/images/home-hero.webp"
)
SUITCASE_GUIDE_ASSET_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/images/article-suitcase-guide.webp"
)
SUITCASE_FRONT_OPEN_ASSET_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/images/article-suitcase-front-open-stopper.webp"
)
SUITCASE_UNDER_100_ASSET_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/images/article-suitcase-under-100-seats.webp"
)
SUITCASE_UNDER_3KG_ASSET_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/images/article-suitcase-under-3kg.webp"
)
MEASUREMENT_CLIENT_INPUT_PATH: Final = THEME_REPOSITORY_ROOT / "assets/measurement.js"
ANALYTICS_CONSENT_GATE_INPUT_PATH: Final = (
    THEME_REPOSITORY_ROOT / "assets/analytics-consent-gate.js"
)
THEME_FUNCTIONS_INPUT_PATH: Final = THEME_REPOSITORY_ROOT / "functions.php"
THEME_SOURCE_INPUT_PATHS: Final = (
    ANALYTICS_CONSENT_GATE_INPUT_PATH,
    THEME_REPOSITORY_ROOT / "assets/editorial-navigation.js",
    EDITORIAL_NAVIGATION_INPUT_PATH,
    THEME_REPOSITORY_ROOT / "assets/editorial-v2.css",
    ANKER_GENERATIONS_ASSET_INPUT_PATH,
    DISHWASHER_ASSET_INPUT_PATH,
    PORTABLE_POWER_ASSET_INPUT_PATH,
    ROBOT_VACUUM_ASSET_INPUT_PATH,
    ROOMBA_K11_ASSET_INPUT_PATH,
    SOLOTA_RAKUA_ASSET_INPUT_PATH,
    SUITCASE_FRONT_OPEN_ASSET_INPUT_PATH,
    SUITCASE_GUIDE_ASSET_INPUT_PATH,
    SUITCASE_UNDER_100_ASSET_INPUT_PATH,
    SUITCASE_UNDER_3KG_ASSET_INPUT_PATH,
    THEME_REPOSITORY_ROOT / "assets/images/brand-mark.svg",
    HOME_HERO_ASSET_INPUT_PATH,
    THEME_REPOSITORY_ROOT / "assets/legacy-media-display-projection.v1.json",
    MEASUREMENT_CLIENT_INPUT_PATH,
    THEME_REPOSITORY_ROOT / "assets/theme.css",
    THEME_FUNCTIONS_INPUT_PATH,
    THEME_REPOSITORY_ROOT / "parts/footer.html",
    THEME_REPOSITORY_ROOT / "parts/header.html",
    THEME_REPOSITORY_ROOT / "raos-assets.v1.json",
    THEME_REPOSITORY_ROOT / "style.css",
    THEME_REPOSITORY_ROOT / "templates/404.html",
    THEME_REPOSITORY_ROOT / "templates/archive.html",
    THEME_REPOSITORY_ROOT / "templates/front-page.html",
    THEME_REPOSITORY_ROOT / "templates/search.html",
    THEME_REPOSITORY_ROOT / "templates/single.html",
    THEME_REPOSITORY_ROOT / "theme-contract.v1.json",
    THEME_REPOSITORY_ROOT / "theme.json",
)
SOURCE_FILES: Final = tuple(
    path.relative_to(THEME_REPOSITORY_ROOT).as_posix()
    for path in THEME_SOURCE_INPUT_PATHS
)
THEME_FINGERPRINT_EXCLUDED_PATHS: Final = frozenset(
    {"raos-assets.v1.json", "theme-contract.v1.json"}
)
THEME_FINGERPRINT_SOURCE_FILES: Final = tuple(
    relative
    for relative in SOURCE_FILES
    if relative not in THEME_FINGERPRINT_EXCLUDED_PATHS
)
PHP_INTEGRITY_BINDINGS: Final = {
    "KURASHINOSHIRUBE_LEGACY_MEDIA_PROJECTION_SHA256": (
        "assets/legacy-media-display-projection.v1.json"
    ),
    "KURASHINOSHIRUBE_SOCIAL_IMAGE_SHA256": "assets/images/home-hero.webp",
    "KURASHINOSHIRUBE_ARTICLE_IMAGE_SHA256": (
        "assets/images/article-suitcase-guide.webp"
    ),
    "KURASHINOSHIRUBE_POWER_ARTICLE_IMAGE_SHA256": (
        "assets/images/article-portable-power-guide.webp"
    ),
    "KURASHINOSHIRUBE_DISHWASHER_ARTICLE_IMAGE_SHA256": (
        "assets/images/article-countertop-dishwasher-guide.webp"
    ),
    "KURASHINOSHIRUBE_ROBOT_ARTICLE_IMAGE_SHA256": (
        "assets/images/article-robot-vacuum-guide.webp"
    ),
    "KURASHINOSHIRUBE_SUITCASE_UNDER_100_IMAGE_SHA256": (
        "assets/images/article-suitcase-under-100-seats.webp"
    ),
    "KURASHINOSHIRUBE_SUITCASE_UNDER_3KG_IMAGE_SHA256": (
        "assets/images/article-suitcase-under-3kg.webp"
    ),
    "KURASHINOSHIRUBE_SUITCASE_FRONT_OPEN_IMAGE_SHA256": (
        "assets/images/article-suitcase-front-open-stopper.webp"
    ),
    "KURASHINOSHIRUBE_ANKER_GENERATIONS_IMAGE_SHA256": (
        "assets/images/article-anker-solix-generations.webp"
    ),
    "KURASHINOSHIRUBE_SOLOTA_RAKUA_IMAGE_SHA256": (
        "assets/images/article-solota-rakua-replacement.webp"
    ),
    "KURASHINOSHIRUBE_ROOMBA_K11_IMAGE_SHA256": (
        "assets/images/article-roomba-mini-k11-comparison.webp"
    ),
    "KURASHINOSHIRUBE_BRAND_MARK_SHA256": "assets/images/brand-mark.svg",
    "KURASHINOSHIRUBE_MEASUREMENT_ASSET_SHA256": "assets/measurement.js",
    "KURASHINOSHIRUBE_ANALYTICS_CONSENT_GATE_ASSET_SHA256": (
        "assets/analytics-consent-gate.js"
    ),
    "KURASHINOSHIRUBE_NAVIGATION_ASSET_SHA256": ("assets/editorial-navigation.js"),
    "KURASHINOSHIRUBE_EDITORIAL_NAVIGATION_SHA256": (
        "assets/editorial-navigation.v3.json"
    ),
}

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
    "detection": ("EXACT_PUBLISHED_PAGE_SLUG_TITLE_AND_EXCERPT_MATCH_CLOSED_HEAD_MAP"),
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
    generated_theme_assets = {
        asset.output.relative_to(ROOT) for asset in theme_asset_owner.ASSETS
    }
    if (
        editorial_navigation_owner.OUTPUT.relative_to(ROOT)
        != EDITORIAL_NAVIGATION_INPUT_PATH
        or generated_theme_assets
        != {
            ANKER_GENERATIONS_ASSET_INPUT_PATH,
            DISHWASHER_ASSET_INPUT_PATH,
            HOME_HERO_ASSET_INPUT_PATH,
            PORTABLE_POWER_ASSET_INPUT_PATH,
            ROBOT_VACUUM_ASSET_INPUT_PATH,
            ROOMBA_K11_ASSET_INPUT_PATH,
            SOLOTA_RAKUA_ASSET_INPUT_PATH,
            SUITCASE_FRONT_OPEN_ASSET_INPUT_PATH,
            SUITCASE_GUIDE_ASSET_INPUT_PATH,
            SUITCASE_UNDER_100_ASSET_INPUT_PATH,
            SUITCASE_UNDER_3KG_ASSET_INPUT_PATH,
        }
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


def _normalized_fingerprint_payload(
    relative: str,
    payload: bytes | None = None,
) -> bytes:
    """Return runtime bytes with only the self-referential digest normalized."""
    if payload is None:
        payload = _read_source(relative)
    if relative == "functions.php":
        try:
            source = payload.decode("utf-8")
        except UnicodeDecodeError:
            _fail()
        replacements = {
            "KURASHINOSHIRUBE_THEME_RUNTIME_REVISION": (
                "<RAOS_THEME_RUNTIME_REVISION>"
            ),
            "KURASHINOSHIRUBE_THEME_SOURCE_FINGERPRINT": (
                "<RAOS_THEME_SOURCE_FINGERPRINT>"
            ),
        }
        for constant, marker in replacements.items():
            source, count = re.subn(
                rf"(?m)^(const {constant} = ')[0-9a-f]{{64}}(';)$",
                rf"\g<1>{marker}\g<2>",
                source,
            )
            if count != 1:
                _fail()
        return source.encode("utf-8")
    if relative in RUNTIME_STYLESHEET_SENTINELS:
        try:
            source = payload.decode("utf-8")
        except UnicodeDecodeError:
            _fail()
        property_name = RUNTIME_STYLESHEET_SENTINELS[relative]
        source, count = re.subn(
            rf"({re.escape(property_name)}:\s*)[0-9a-f]{{64}}(;)",
            r"\g<1><RAOS_THEME_RUNTIME_REVISION>\g<2>",
            source,
        )
        if count != 1:
            _fail()
        return source.encode("utf-8")
    return payload


def _fingerprint_from_payloads(payloads: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative in THEME_FINGERPRINT_SOURCE_FILES:
        payload = payloads.get(relative)
        if type(payload) is not bytes:
            _fail()
        payload = _normalized_fingerprint_payload(relative, payload)
        encoded_path = relative.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(4, "big"))
        digest.update(encoded_path)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def theme_source_fingerprint() -> str:
    return _fingerprint_from_payloads(
        {
            relative: _read_source(relative)
            for relative in THEME_FINGERPRINT_SOURCE_FILES
        }
    )


def _canonical_json(document: object) -> bytes:
    try:
        return (
            json.dumps(
                document,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _fail()


def _replace_exact_hash_constant(source: str, constant: str, digest: str) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        _fail()
    source, count = re.subn(
        rf"(?m)^(const {re.escape(constant)} = ')[0-9a-f]{{64}}(';)$",
        rf"\g<1>{digest}\g<2>",
        source,
    )
    if count != 1:
        _fail()
    return source


def _replace_stylesheet_revision(
    source: str,
    property_name: str,
    revision: str,
) -> str:
    source, count = re.subn(
        rf"({re.escape(property_name)}:\s*)[0-9a-f]{{64}}(;)",
        rf"\g<1>{revision}\g<2>",
        source,
    )
    if count != 1:
        _fail()
    return source


def _read_regular_path(path: Path, *, maximum: int = MAX_SOURCE_BYTES) -> bytes:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        _fail()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size <= 0
        or metadata.st_size > maximum
        or len(payload) != metadata.st_size
    ):
        _fail()
    return payload


def _decoded_utf8(payload: bytes) -> str:
    try:
        return payload.decode("utf-8", errors="strict")
    except UnicodeError:
        _fail()


def _load_json_payload(payload: bytes) -> dict[str, object]:
    try:
        document = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError):
        _fail()
    if type(document) is not dict:
        _fail()
    return document


def render_theme_stamp_payloads() -> tuple[dict[Path, bytes], str]:
    """Render the complete non-circular theme identity from current owner inputs."""

    sources = {relative: _read_source(relative) for relative in SOURCE_FILES}
    functions = _decoded_utf8(sources["functions.php"])
    for constant, relative in PHP_INTEGRITY_BINDINGS.items():
        payload = sources.get(relative)
        if type(payload) is not bytes:
            _fail()
        functions = _replace_exact_hash_constant(
            functions,
            constant,
            hashlib.sha256(payload).hexdigest(),
        )
    prospective = dict(sources)
    prospective["functions.php"] = functions.encode("utf-8")
    revision = _fingerprint_from_payloads(prospective)

    functions = _replace_exact_hash_constant(
        functions,
        "KURASHINOSHIRUBE_THEME_RUNTIME_REVISION",
        revision,
    )
    functions = _replace_exact_hash_constant(
        functions,
        "KURASHINOSHIRUBE_THEME_SOURCE_FINGERPRINT",
        revision,
    )
    rendered: dict[Path, bytes] = {
        THEME_ROOT / "functions.php": functions.encode("utf-8"),
    }
    for relative, property_name in RUNTIME_STYLESHEET_SENTINELS.items():
        rendered[THEME_ROOT / relative] = _replace_stylesheet_revision(
            _decoded_utf8(sources[relative]),
            property_name,
            revision,
        ).encode("utf-8")

    navigation_payload = sources["assets/editorial-navigation.v3.json"]
    navigation = _load_json_payload(navigation_payload)
    navigation_digest = hashlib.sha256(navigation_payload).hexdigest()
    source_navigation_sha256 = navigation.get("source_navigation_sha256")
    source_portfolio_sha256 = navigation.get("source_portfolio_sha256")
    if (
        re.fullmatch(r"[0-9a-f]{64}", str(source_navigation_sha256)) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(source_portfolio_sha256)) is None
    ):
        _fail()

    contract = _load_json_payload(sources["theme-contract.v1.json"])
    contract["editorial_navigation"] = {
        "article_count": 10,
        "cluster_count": 3,
        "generated_by": "scripts/build_editorial_v3_theme_navigation.py",
        "path": "assets/editorial-navigation.v3.json",
        "schema": "RAOS_EDITORIAL_THEME_NAVIGATION_V3",
        "sha256": navigation_digest,
        "source_navigation_sha256": source_navigation_sha256,
        "source_portfolio_sha256": source_portfolio_sha256,
    }
    contract["theme_version"] = THEME_VERSION
    contract["runtime_evidence"] = {
        "revision": revision,
        "source_fingerprint": revision,
        "source_fingerprint_files": list(THEME_FINGERPRINT_SOURCE_FILES),
        "stylesheets": RUNTIME_STYLESHEET_SENTINELS,
    }
    rendered[THEME_ROOT / "theme-contract.v1.json"] = _canonical_json(contract)

    assets = _load_json_payload(sources["raos-assets.v1.json"])
    assets["source_files"] = list(SOURCE_FILES)
    assets["theme_runtime_revision"] = revision
    assets["theme_source_fingerprint"] = revision
    assets["theme_slug"] = THEME_SLUG
    assets["theme_version"] = THEME_VERSION
    rendered[THEME_ROOT / "raos-assets.v1.json"] = _canonical_json(assets)

    builder = _decoded_utf8(_read_regular_path(THEME_BUILDER_SOURCE_PATH))
    builder, count = re.subn(
        r'(THEME_RUNTIME_REVISION: Final = \(\n\s*")[0-9a-f]{64}("\n\))',
        rf"\g<1>{revision}\g<2>",
        builder,
    )
    if count != 1:
        _fail()
    rendered[THEME_BUILDER_SOURCE_PATH] = builder.encode("utf-8")

    handoff = _decoded_utf8(_read_regular_path(DESIGN_HANDOFF_PATH))
    handoff, count = re.subn(
        r"(?m)^(\s*child_theme_runtime_revision:\s*)[0-9a-f]{64}(\s*)$",
        rf"\g<1>{revision}\g<2>",
        handoff,
    )
    if count != 1:
        _fail()
    rendered[DESIGN_HANDOFF_PATH] = handoff.encode("utf-8")

    runbook = _decoded_utf8(_read_regular_path(OPERATIONS_RUNBOOK_PATH))
    runbook, count = re.subn(
        r"(?m)^(revision `)[0-9a-f]{64}(`\.)$",
        rf"\g<1>{revision}\g<2>",
        runbook,
    )
    if count != 1:
        _fail()
    rendered[OPERATIONS_RUNBOOK_PATH] = runbook.encode("utf-8")
    return rendered, revision


def _write_theme_stamp_payloads(payloads: Mapping[Path, bytes]) -> None:
    staged: list[tuple[Path, Path]] = []
    try:
        for index, target in enumerate(
            sorted(payloads, key=lambda path: path.as_posix())
        ):
            payload = payloads[target]
            if type(payload) is not bytes or not payload:
                _fail()
            _read_regular_path(target)
            temporary = target.with_name(f".{target.name}.{os.getpid()}.{index}.tmp")
            descriptor = os.open(
                temporary,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o644,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            staged.append((target, temporary))
        for target, temporary in staged:
            os.replace(temporary, target)
    except (OSError, ThemeBuildFailure):
        for _target, temporary in staged:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        _fail()


def generate_theme_stamps() -> str:
    payloads, revision = render_theme_stamp_payloads()
    _write_theme_stamp_payloads(payloads)
    second, second_revision = render_theme_stamp_payloads()
    if (
        second_revision != revision
        or second != payloads
        or any(path.read_bytes() != payload for path, payload in payloads.items())
    ):
        _fail()
    return revision


def check_theme_stamps() -> str:
    payloads, revision = render_theme_stamp_payloads()
    if any(
        path.is_symlink() or path.read_bytes() != payload
        for path, payload in payloads.items()
    ):
        _fail()
    return revision


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


def _validate_asset_manifest(
    assets: dict[str, object],
    sources: dict[str, bytes],
) -> None:
    if (
        set(assets)
        != {
            "required_images",
            "schema",
            "source_files",
            "theme_slug",
            "theme_runtime_revision",
            "theme_source_fingerprint",
            "theme_version",
        }
        or assets.get("schema") != "SELF_HOSTED_EDITORIAL_THEME_ASSETS_V2"
        or assets.get("theme_slug") != THEME_SLUG
        or assets.get("theme_version") != THEME_VERSION
        or assets.get("theme_runtime_revision") != THEME_RUNTIME_REVISION
        or assets.get("theme_source_fingerprint") != THEME_RUNTIME_REVISION
        or assets.get("source_files") != list(SOURCE_FILES)
    ):
        _fail()

    records = assets.get("required_images")
    if type(records) is not list or len(records) != 12:
        _fail()
    generated_assets = {
        asset.output.relative_to(THEME_ROOT).as_posix(): asset
        for asset in theme_asset_owner.ASSETS
    }
    seen_paths: set[str] = set()
    for value in records:
        if type(value) is not dict or set(value) != {
            "alt",
            "canvas_height",
            "canvas_width",
            "delivery",
            "path",
            "provenance",
            "sha256",
            "status",
            "usage",
        }:
            _fail()
        record = value
        path = record.get("path")
        digest = record.get("sha256")
        if (
            type(path) is not str
            or path in seen_paths
            or record.get("status") != "FINAL"
            or type(digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or type(record.get("canvas_width")) is not int
            or type(record.get("canvas_height")) is not int
            or type(record.get("delivery")) is not str
            or not record["delivery"]
            or type(record.get("usage")) is not str
            or not record["usage"]
            or type(record.get("alt")) is not str
            or type(record.get("provenance")) is not dict
            or path not in sources
        ):
            _fail()
        seen_paths.add(path)
        if hashlib.sha256(sources[path]).hexdigest() != digest:
            _fail()
        generated = generated_assets.get(path)
        if generated is not None:
            if (
                record["canvas_width"] != generated.output_width
                or record["canvas_height"] != generated.output_height
                or record["provenance"]
                != theme_asset_owner.manifest_provenance(generated)
            ):
                _fail()
            continue
        if path != "assets/images/brand-mark.svg":
            _fail()
        if record["provenance"] != {
            "allowed_modifications": [
                "COLOR_ADAPTATION",
                "FORMAT_CONVERSION",
                "RESIZE",
            ],
            "allowed_uses": ["FAVICON_FALLBACK"],
            "created_on": "2026-08-23",
            "creation_method": "REPOSITORY_AUTHORED_VECTOR",
            "creator_record": "SITE_REPOSITORY_MAINTAINER",
            "external_license_dependency": False,
            "generation_intent": "ORIGINAL_SITE_IDENTITY_MARK",
            "original_sha256": digest,
            "original_source_path": (
                "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
                "kurashinoshirube-child/assets/images/brand-mark.svg"
            ),
            "provenance_evidence": "GIT_TRACKED_SOURCE",
            "rights_basis": "OWNER_AUTHORIZED_REPOSITORY_ORIGINAL",
            "rights_status": "RECORDED_FOR_SITE_USE",
        }:
            _fail()
    if seen_paths != {
        "assets/images/article-anker-solix-generations.webp",
        "assets/images/article-countertop-dishwasher-guide.webp",
        "assets/images/article-portable-power-guide.webp",
        "assets/images/article-robot-vacuum-guide.webp",
        "assets/images/article-roomba-mini-k11-comparison.webp",
        "assets/images/article-solota-rakua-replacement.webp",
        "assets/images/article-suitcase-front-open-stopper.webp",
        "assets/images/article-suitcase-guide.webp",
        "assets/images/article-suitcase-under-100-seats.webp",
        "assets/images/article-suitcase-under-3kg.webp",
        "assets/images/brand-mark.svg",
        "assets/images/home-hero.webp",
    }:
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
    search = _text("templates/search.html")
    archive = _text("templates/archive.html")
    not_found = _text("templates/404.html")
    home_hero_image = (
        '<img class="raos-home-hero__image" '
        'src="/wp-content/themes/kurashinoshirube-child/assets/images/home-hero.webp" '
        'alt="鍋、マグカップ、照明とチェックリストを描いた暮らしの道具のイラスト" '
        'width="1600" height="900" fetchpriority="high" decoding="async">'
    )
    if (
        '<h1 id="home-hero-title"><span>暮らしの選択に、</span>'
        '<span>たしかな</span><span>道しるべを。</span></h1>' not in front_page
        or front_page.count(home_hero_image) != 1
        or '<span class="raos-home-hero__image"' in front_page
        or "loading=" in home_hero_image
    ):
        _fail()
    if single.count("wp:post-title") != 1:
        _fail()
    if (
        search.count("wp:post-excerpt") != 1
        or "wp:post-content" in search
        or search.count("[kurashinoshirube_search_empty_state]") != 1
        or "記事を探す" not in search
        or ">SEARCH<" in search
        or archive.count("wp:post-excerpt") != 1
        or "wp:post-content" in archive
        or "比較ガイド一覧" not in archive
        or ">GUIDES<" in archive
        or "ページが見つかりませんでした" not in not_found
        or "記事を検索" not in not_found
    ):
        _fail()
    navigation_chrome = _text("parts/header.html") + _text("parts/footer.html")
    if (
        "subscribe" in (navigation_chrome + front_page).lower()
        or "新しい記事" in navigation_chrome
        or navigation_chrome.count("最近更新したガイド") != 2
    ):
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
    if 'url("images/home-hero.webp")' in css:
        _fail()

    php = _text("functions.php")
    article_visuals = php.split("$article_visuals = array(", 1)[1].split(
        "$assets = array(", 1
    )[0]
    if (
        article_visuals.count(
            "暮らしのしるべ編集者の比較イメージ（商品写真ではありません）"
        )
        != 10
        or "抽象図" in article_visuals
    ):
        _fail()
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
    php_source_fingerprint = re.findall(
        r"^const KURASHINOSHIRUBE_THEME_SOURCE_FINGERPRINT = '([0-9a-f]{64})';$",
        php,
        flags=re.MULTILINE,
    )
    calculated_source_fingerprint = theme_source_fingerprint()
    if (
        php_runtime_revision != [THEME_RUNTIME_REVISION]
        or php_source_fingerprint != [THEME_RUNTIME_REVISION]
        or calculated_source_fingerprint != THEME_RUNTIME_REVISION
    ):
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
            "source_fingerprint": THEME_RUNTIME_REVISION,
            "source_fingerprint_files": list(THEME_FINGERPRINT_SOURCE_FILES),
            "stylesheets": RUNTIME_STYLESHEET_SENTINELS,
        }
        or contract.get("publication_authority") != "NONE"
        or contract.get("editorial_v2") != EDITORIAL_V2_PRESENTATION
        or contract.get("policy_v3") != POLICY_V3_PRESENTATION
        or contract.get("head", {}).get("document_title_deduplication")
        != DOCUMENT_TITLE_DEDUPLICATION
        or contract.get("head", {}).get("document_title_owner")
        != "YOAST_WHEN_ACTIVE_OTHERWISE_WORDPRESS_OR_GUTENBERG_FALLBACK"
        or contract.get("head", {}).get("metadata_owner")
        != (
            "PRODUCTION_YOAST_SEO_FILTERED_BY_VALID_RAOS_SNAPSHOT_OR_CLOSED_"
            "PUBLIC_HEAD_CONTEXT_AND_CONFIG_READBACK"
        )
        or contract.get("head", {}).get("raos_metadata_delivery")
        != (
            "PRODUCTION_YOAST_METADATA_FILTERS_WITH_LOCAL_PREVIEW_NO_YOAST_"
            "FALLBACK"
        )
        or contract.get("head", {}).get("local_preview_metadata_fallback")
        != {
            "active_when": (
                "EXACT_RAOS_LOCAL_PREVIEW_AND_WPSEO_VERSION_UNDEFINED_AND_"
                "CLOSED_HEAD_CONTEXT_AND_VERIFIED_SOCIAL_IMAGE"
            ),
            "canonical_owner": "RAOS_THEME_AFTER_REMOVING_CORE_REL_CANONICAL",
            "document_title_owner": "WORDPRESS_PRE_GET_DOCUMENT_TITLE_FILTER",
            "fields": [
                "canonical",
                "meta_description",
                "og_description",
                "og_image",
                "og_title",
                "og_url",
            ],
            "production_effect": "NONE",
        }
        or contract.get("public_listing_eligibility") != PUBLIC_LISTING_ELIGIBILITY
        or not isinstance(contract.get("snapshot"), dict)
        or contract["snapshot"].get("excerpt_binding")
        != "EXACT_WORDPRESS_POST_EXCERPT_EQUALS_DESCRIPTION_RAW_UTF8"
        or not isinstance(contract.get("human_existing_update"), dict)
    ):
        _fail()
    content_markup = contract.get("content_markup")
    affiliate_cta = (
        content_markup.get("affiliate_cta")
        if isinstance(content_markup, dict)
        else None
    )
    if affiliate_cta != {
        "class": "raos-cta",
        "data_attributes": [
            "data-raos-article-id",
            "data-raos-cta-id",
            "data-raos-offer-id",
            "data-raos-placement",
            "data-raos-product-id",
            "data-raos-rakuten-provider-slot-id",
            "data-raos-snapshot-id",
        ],
        "materialized_labels": {
            "available_official_fallback_final_summary": (
                "メーカー公式で販売状況を確認する"
            ),
            "available_official_fallback_product_card": (
                "メーカー公式で仕様と型番を確認する"
            ),
            "out_of_stock_official_fallback": ("メーカー公式で販売状況を確認する"),
            "verified_final_summary": ("楽天市場でこの候補の型番・在庫を確認する"),
            "verified_product_card": ("楽天市場で型番・在庫・販売元を確認する"),
        },
        "rel_tokens": ["nofollow", "sponsored"],
        "required_host_provenance": "VALIDATED_RAKUTEN_DIRECT_AFFILIATE_URL",
        "source_placeholder_label": "楽天市場で現在の価格・在庫・カラーを見る",
        "fallback_target_sources": {
            "available_official_fallback_final_summary": (
                "manufacturer_sales_state.status_evidence_urls[0]"
            ),
            "available_official_fallback_product_card": "product.official_url",
            "out_of_stock_official_fallback": (
                "manufacturer_sales_state.status_evidence_urls[0]"
            ),
        },
    }:
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
            or len(row["related_articles"]) < 1
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
        "article_link_placements": {
            "article_body": {"maximum": 1, "minimum": 1},
            "related_navigation": {"maximum": 1, "minimum": 0},
        },
        "availability_transition": "TARGET_HUMAN_PUBLICATION_ONLY",
        "category_home_links_per_article": 1,
        "content_hash_scope": "THEME_CHROME_OUTSIDE_WORDPRESS_POST_CONTENT",
        "duplicate_article_urls_allowed": False,
        "intent_group_policy": "RELATED_TARGETS_MUST_SHARE_INTENT_GROUP",
        "maximum_targets_per_article": 2,
        "minimum_targets_per_article": 1,
        "owner": "EDITORIAL_V3_GENERATED_NAVIGATION",
        "reader_link_count_per_article": {"maximum": 3, "minimum": 2},
        "relationship_types": [
            "broader_guide",
            "narrower_comparison",
            "lifecycle_reference",
            "adjacent_condition",
        ],
        "rendered_relationships": (
            "FIRST_SEMANTIC_SAME_INTENT_IN_BODY_PLUS_OPTIONAL_SECOND_"
            "SEMANTIC_SAME_INTENT_AND_CLUSTER_HOME_LINK"
        ),
        "source": ("assets/editorial-navigation.v3.json#articles[].related_articles"),
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
        "local_preview_substitute": "EXACT_LOCAL_SLUG_FOR_SAME_ARTICLE_ID",
        "selection": "FIXED_ARTICLE_ID_WITH_EXACT_PUBLIC_ARTICLE_IDENTITY",
    }:
        _fail()
    _validate_asset_manifest(_json("raos-assets.v1.json"), sources)

    for asset in theme_asset_owner.ASSETS:
        _validate_webp(asset.output.relative_to(THEME_ROOT).as_posix())
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
    except (OSError, ThemeBuildFailure):
        _fail()


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument("--generate", action="store_true")
    commands.add_argument("--source-check", action="store_true")
    commands.add_argument("--package", action="store_true")
    commands.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.generate or not (
            arguments.source_check or arguments.package or arguments.check
        ):
            revision = generate_theme_stamps()
            print(f"SELF_HOSTED_EDITORIAL_THEME_GENERATED revision={revision}")
            return 0
        if arguments.source_check:
            check_theme_stamps()
            validate_sources()
            print("SELF_HOSTED_EDITORIAL_THEME_SOURCE_OK")
            return 0
        check_theme_stamps()
        first = build_package()
        second = build_package()
        if first != second:
            _fail()
        digest = hashlib.sha256(first).hexdigest()
        if arguments.package:
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
