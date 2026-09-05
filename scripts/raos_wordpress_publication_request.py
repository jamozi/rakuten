#!/usr/bin/env python3
"""Request and finish one locally verified WordPress publication batch.

Python is used so the workflow can reuse the repository's owner-private
Application Password format. Editor calls use the fixed project MCP endpoint;
deployment calls use the fixed, pinned stdio MCP bridge.
"""

from __future__ import annotations

import argparse
import base64
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import fcntl
import grp
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import stat
import subprocess
import sys
import time
from typing import Any, Final, NoReturn
import urllib.error
import urllib.request
from urllib.parse import urlsplit

PYTHON_ROOT = Path(__file__).resolve().parents[1] / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))
SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from raos.application.editorial.editorial_portfolio_v3 import (  # noqa: E402
    EditorialPortfolioV3Failure,
    load_editorial_portfolio_v3,
)
from raos.application.editorial.editorial_portfolio_v2 import (  # noqa: E402
    EditorialPortfolioV2Failure,
    STATUS_RELATIVE_PATH as V2_STATUS_RELATIVE_PATH,
    load_editorial_portfolio_v2,
    portfolio_sha256 as v2_portfolio_sha256,
    require_manufacturer_sales_state_for_products_v1,
)
from raos.application.editorial.rakuten_measurement_activation_v3 import (  # noqa: E402
    RakutenMeasurementActivationOverlayV3,
    RakutenMeasurementActivationV3Failure,
    _load_verified_v2_evidence,
    _validate_product_safety_publication_binding,
    validate_rakuten_measurement_activation_v3,
)
from raos.application.editorial.rakuten_standard_api_v1 import (  # noqa: E402
    BINDING_SCHEMA as STANDARD_API_BINDING_SCHEMA,
    RakutenStandardApiOverlayV1,
    validate_standard_api_v1,
)
from raos.application.finance.editorial_economics_v3 import EditorialEconomicsV3Failure  # noqa: E402
import raos_wordpress_seo_audit as wordpress_seo_audit  # noqa: E402
import wordpress_quality_audit_v1 as wordpress_quality_audit  # noqa: E402
import build_st1704_self_hosted_theme as theme_owner  # noqa: E402


ROOT: Final = Path(__file__).resolve().parents[1]
PublicationOverlay = RakutenMeasurementActivationOverlayV3 | RakutenStandardApiOverlayV1
PREVIEW_ROOT: Final = ROOT / "changes/wordpress-local-preview-v1"
SOURCE_FIXTURE_ROOT: Final = PREVIEW_ROOT / "fixtures"
FIXTURE_PATH: Final = SOURCE_FIXTURE_ROOT / "posts.json"
PAGES_FIXTURE_PATH: Final = SOURCE_FIXTURE_ROOT / "pages.json"
MAPPING_PATH: Final = PREVIEW_ROOT / "production-mapping.v1.json"
PORTFOLIO_SCRIPT: Final = ROOT / "scripts/raos_editorial_portfolio_v2.py"
PORTFOLIO_PRIVATE_ROOT: Final = ROOT / ".secrets/editorial-portfolio-v2"
PREVIEW_PRIVATE_ROOT: Final = ROOT / ".secrets/wordpress-local-preview"
PORTFOLIO_SUBPROCESS_ENVIRONMENT: Final = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "TZ": "UTC",
    "TMPDIR": "/tmp",
    "TEMP": "/tmp",
    "TMP": "/tmp",
    "PYTHONDONTWRITEBYTECODE": "1",
}
LOCAL_MATERIALIZED_FIXTURE_ROOT: Final = (
    PREVIEW_PRIVATE_ROOT / "materialized-fixtures-v2"
)
LOCAL_MATERIALIZATION_RECEIPT: Final = (
    LOCAL_MATERIALIZED_FIXTURE_ROOT / "materialization-receipt.v2.json"
)
PRODUCTION_MATERIALIZED_FIXTURE_ROOT: Final = (
    PORTFOLIO_PRIVATE_ROOT / "production-materialized-fixtures-v2"
)
PRODUCTION_MATERIALIZATION_RECEIPT: Final = (
    PRODUCTION_MATERIALIZED_FIXTURE_ROOT / "materialization-receipt.v2.json"
)
THEME_STYLE_PATH: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/style.css"
)
THEME_ROOT: Final = THEME_STYLE_PATH.parent
THEME_FUNCTIONS_PATH: Final = THEME_ROOT / "functions.php"
ORIGIN: Final = "https://kurashinoshirube.com"
EXPECTED_SOCIAL_IMAGE_URL: Final = (
    f"{ORIGIN}/wp-content/themes/kurashinoshirube-child/assets/images/home-hero.webp"
)
EXPECTED_ARTICLE_SOCIAL_IMAGE_BY_SLUG: Final = {
    "carry-on-suitcase-comparison": "article-suitcase-guide.webp",
    "portable-power-station-guide": "article-portable-power-guide.webp",
    "anker-solix-c300-c800-c1000-differences": ("article-anker-solix-generations.webp"),
    "countertop-dishwasher-for-small-households": (
        "article-countertop-dishwasher-guide.webp"
    ),
    "compact-robot-vacuum-shortlist": "article-robot-vacuum-guide.webp",
    "carry-on-suitcase-under-100-seats": "article-suitcase-under-100-seats.webp",
    "lightweight-carry-on-suitcase-under-3kg": "article-suitcase-under-3kg.webp",
    "front-open-carry-on-suitcase-with-stopper": (
        "article-suitcase-front-open-stopper.webp"
    ),
    "roomba-mini-vs-switchbot-k11-pro": "article-roomba-mini-k11-comparison.webp",
    "solota-vs-rakua-mini-plus": "article-solota-rakua-replacement.webp",
}
EDITOR_ENDPOINT: Final = f"{ORIGIN}/wp-json/raos-codex-mcp/v1/editor"
REVIEW_URL: Final = f"{ORIGIN}/wp-admin/tools.php?page=raos-codex-proposals"
EDITOR_CREDENTIAL_PATH: Final = (
    ROOT / ".secrets/wordpress-mcp/editor-application-password.v1.json"
)
PRIVATE_REQUEST_DIRECTORY: Final = ROOT / ".secrets/wordpress-mcp/publication-requests"
MEASUREMENT_PLUGIN_MANIFEST_PATH: Final = (
    ROOT / "changes/editorial-measurement-v1/runtime-manifest.v1.json"
)
REPO_PLUGIN_ARTIFACTS_PATH: Final = (
    ROOT / "changes/wordpress-mcp-v1/contracts/repo-plugin-artifacts.v1.json"
)
NODE_BIN: Final = Path("/home/minami/.nvm/versions/node/v24.18.1/bin/node")
DEPLOYMENT_BRIDGE: Final = ROOT / "packages/wordpress-mcp-bridge/src/index.ts"
MAKE_BIN: Final = Path("/usr/bin/make")
SG_BIN: Final = Path("/usr/bin/sg")
DOCKER_SOCKET: Final = Path("/var/run/docker.sock")
PROTOCOL_VERSION: Final = "2025-11-25"
EXPECTED_PLUGIN_VERSION: Final = "1.3.1"
EXPECTED_PLUGIN_RUNTIME_REVISION: Final = (
    "f3e9e302b9a40bf6b312b2457f981272246f4fdd6f3e047d92bec5fda61d8082"
)
EXPECTED_PROPOSAL_REVIEW_TTL_SECONDS: Final = 3600
EXPECTED_APPLY_LEASE_TTL_SECONDS: Final = 900
ATTEMPT_PREPARED_EXPIRY_SECONDS: Final = EXPECTED_PROPOSAL_REVIEW_TTL_SECONDS + 30
RELEASE_FOREGROUND_TIMEOUT_SECONDS: Final = 4680
EXPECTED_THEME_VERSION: Final = theme_owner.THEME_VERSION
EXPECTED_THEME_RUNTIME_REVISION: Final = theme_owner.THEME_RUNTIME_REVISION
THEME_RUNTIME_SENTINEL_PROPERTIES: Final = {
    "assets/theme.css": "--raos-theme-runtime-revision-base",
    "assets/editorial-v2.css": "--raos-theme-runtime-revision-editorial-v2",
}
DIRECT_THEME_STYLESHEET_PATHS: Final = frozenset(
    {
        "/wp-content/themes/kurashinoshirube-child/assets/theme.css",
        "/wp-content/themes/kurashinoshirube-child/assets/editorial-v2.css",
    }
)
AUTOPTIMIZE_SINGLE_STYLESHEET_PREFIX: Final = (
    "/wp-content/cache/autoptimize/autoptimize_single_"
)
EXPECTED_ALL_ARTICLE_COUNT: Final = 10
EXPECTED_MATERIALIZED_PRODUCT_CARD_COUNT: Final = 37
EXPECTED_MATERIALIZED_AFFILIATE_CTA_COUNT: Final = 74
ZERO_PRODUCT_ROUTE_SLUGS: Final = frozenset({"solota-vs-rakua-mini-plus"})
EXPECTED_YOAST_VERSION: Final = "28.3"
EXPECTED_YOAST_OPTIONS: Final = {
    "wpseo": {
        "enable_ai_generator": False,
        "enable_headless_rest_endpoints": False,
        "enable_index_now": False,
        "enable_schema": False,
        "enable_schema_aggregation_endpoint": False,
        "enable_xml_sitemap": True,
        "google_site_kit_feature_enabled": False,
        "googleverify": "",
        "semrush_integration_active": False,
        "tracking": False,
        "wincher_integration_active": False,
    },
    "wpseo_social": {
        "og_default_image": (
            f"{ORIGIN}/wp-content/themes/kurashinoshirube-child/"
            "assets/images/home-hero.webp"
        ),
        "og_default_image_id": "",
        "opengraph": True,
        "twitter": True,
        "twitter_card_type": "summary_large_image",
    },
}
EXPECTED_YOAST_SETTINGS_FINGERPRINT: Final = (
    "907f32107299b0fb8154cdedc87ed20d18ab0b92c2aa3704516c8f44085ca5b9"
)
EXPECTED_POLICY_PAGE_COUNT: Final = 3
CREATE_IF_MISSING_POLICY_PAGE_SLUGS: Final = frozenset({"comparison-policy"})
MAX_PUBLICATION_PROPOSALS: Final = 14
MAX_CONTENT_BYTES: Final = 1024 * 1024
MAX_RESPONSE_BYTES: Final = 16 * 1024 * 1024
MAX_PUBLIC_PAGE_BYTES: Final = 4 * 1024 * 1024
MAX_PUBLIC_STYLESHEET_BYTES: Final = 1024 * 1024
MAX_PUBLIC_STYLESHEET_CACHE_ENTRIES: Final = EXPECTED_ALL_ARTICLE_COUNT * 2
MAX_PUBLIC_SEO_AUDIT_AGE: Final = timedelta(minutes=5)
MAX_RECEIPT_BYTES: Final = 4 * 1024 * 1024
MAX_THEME_PACKAGE_BYTES: Final = 32 * 1024 * 1024
MAX_THEME_FILE_BYTES: Final = 8 * 1024 * 1024
MAX_THEME_FILE_COUNT: Final = 2048
LIST_PER_PAGE: Final = 10
MAX_LIST_DOCUMENTS: Final = 10_000
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
TIMESTAMP_RE: Final = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
QUALITY_AUDIT_IDENTIFIER_RE: Final = re.compile(
    r"[a-z0-9][a-z0-9._-]{7,95}\Z",
    re.ASCII,
)
SLUG_RE: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION_RE: Final = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}(?:[-+][0-9A-Za-z.-]+)?$")
EXPECTED_TOOLS: Final = {
    "raos-codex-site-status",
    "raos-codex-content-list",
    "raos-codex-content-get",
    "raos-codex-content-create-draft",
    "raos-codex-content-update-draft",
    "raos-codex-content-propose-release",
    "raos-codex-publication-batch-register",
    "raos-codex-operation-get",
}
EXPECTED_DEPLOYMENT_TOOLS: Final = {
    "deployment-status",
    "publication-batch-status",
    "release-wait-and-apply",
    "theme-propose-release",
    "plugin-propose-change",
    "plugin-apply-change",
    "operation-recover",
}
WRITE_FIELDS: Final = (
    "post_type",
    "title",
    "slug",
    "excerpt",
    "block_markup",
    "taxonomies",
    "media_ids",
)
SEO_CORE_PAGE_CHECKS: Final = frozenset(
    {
        "http_200_no_redirect",
        "self_canonical",
        "robots_index_follow",
        "title",
        "meta_description",
        "og_title",
        "og_description",
        "og_url",
        "og_image",
        "og_type",
        "og_locale",
        "og_site_name",
        "og_image_width",
        "og_image_height",
        "og_image_type",
        "twitter_card",
        "twitter_title",
        "twitter_description",
        "twitter_image",
        "required_schema",
        "forbidden_schema_absent",
        "structured_data_semantics",
    }
)
SEO_SURFACE_CHECKS: Final = frozenset(
    {"robots", "sitemap", "sitemap_home", "llms_txt_absent"}
)
SEO_INDEX_STATE_BASES: Final = frozenset(
    {
        "UNAVAILABLE",
        "OWNER_PRIVATE_LIVE_GSC_URL_INSPECTION_V1",
        "OWNER_PRIVATE_RECORDED_URL_INSPECTION_V1",
    }
)
SEO_INVENTORY_IDENTIFIERS: Final = frozenset(
    {
        "home",
        *(f"a{number:02d}" for number in range(1, 11)),
        "about-ad-policy",
        "comparison-policy",
        "privacy-policy",
    }
)


class PublicationFailure(RuntimeError):
    """Fail-closed error whose message is a stable, non-sensitive code."""


class _RefuseRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Turn every HTTP redirect into an HTTPError before a second request."""

    def redirect_request(self, *_: object, **__: object) -> None:
        return None


def _robots_blocks_indexing(value: object) -> bool:
    """Recognize robots directives without depending on separator style."""

    if type(value) is not str or len(value) > 16 * 1024:
        return False
    directives = {token for token in re.split(r"[\s,;:]+", value.casefold()) if token}
    # `none` is defined as the noindex,nofollow shorthand.
    return bool(directives & {"noindex", "none"})


def _response_header_values(headers: object, name: str) -> list[str]:
    """Read a response header case-insensitively, including repeated fields."""

    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        try:
            values = get_all(name, [])
        except TypeError, ValueError:
            values = []
        return [value for value in values if type(value) is str]
    items = getattr(headers, "items", None)
    if not callable(items):
        return []
    try:
        pairs = items()
    except TypeError, ValueError:
        return []
    return [
        value
        for key, value in pairs
        if type(key) is str and key.casefold() == name.casefold() and type(value) is str
    ]


class _PublicPageEvidenceParser(HTMLParser):
    """Collect only bounded public-page evidence needed for post-publish checks."""

    _VOID_ELEMENTS: Final = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonical_urls: list[str] = []
        self.meta_descriptions: list[str] = []
        self.open_graph: dict[str, list[str]] = {
            "og:title": [],
            "og:description": [],
            "og:url": [],
            "og:image": [],
        }
        self.json_ld_payloads: list[str] = []
        self.page_titles: list[str] = []
        self.headings: list[str] = []
        self.heading_outline: list[tuple[str, str]] = []
        self.h1_titles: list[str] = []
        self.visible_text: list[str] = []
        self.ctas: list[dict[str, object]] = []
        self.affiliate_links: list[dict[str, object]] = []
        self.product_images: list[dict[str, str]] = []
        self.disclosure_text: list[str] = []
        self.stylesheet_urls: list[str] = []
        self.noindex = False
        self._suppressed_depth = 0
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self._title_parts: list[str] | None = None
        self._json_ld_parts: list[str] | None = None
        self._elements: list[tuple[str, str | None, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        attributes = {
            key.lower(): value for key, value in attrs if isinstance(key, str)
        }
        parent_product = self._elements[-1][1] if self._elements else None
        product_id = attributes.get("data-raos-product-id") or parent_product
        classes = {
            value
            for value in (attributes.get("class") or "").casefold().split()
            if value
        }
        parent_disclosure = self._elements[-1][2] if self._elements else False
        in_disclosure = parent_disclosure or bool(
            classes & {"disclosure", "raos-disclosure"}
        )
        if lowered in {"script", "style", "noscript", "template"}:
            if (
                lowered == "script"
                and (attributes.get("type") or "").strip().casefold()
                == "application/ld+json"
            ):
                self._json_ld_parts = []
            self._suppressed_depth += 1
        if lowered == "link":
            rel = (attributes.get("rel") or "").lower().split()
            href = attributes.get("href")
            if "canonical" in rel and isinstance(href, str):
                self.canonical_urls.append(href)
            if "stylesheet" in rel and isinstance(href, str):
                self.stylesheet_urls.append(href)
        if lowered == "meta" and (attributes.get("name") or "").casefold() in {
            "robots",
            "googlebot",
            "googlebot-news",
        }:
            if _robots_blocks_indexing(attributes.get("content")):
                self.noindex = True
        if lowered == "meta":
            name = (attributes.get("name") or "").strip().casefold()
            prop = (attributes.get("property") or "").strip().casefold()
            content = attributes.get("content")
            if name == "description" and isinstance(content, str):
                self.meta_descriptions.append(content)
            if prop in self.open_graph and isinstance(content, str):
                self.open_graph[prop].append(content)
        if lowered == "title" and self._suppressed_depth == 0:
            self._title_parts = []
        if lowered == "a" and attributes.get("data-raos-placement") in {
            "product_card",
            "final_summary",
        }:
            self.ctas.append(
                {
                    "href": attributes.get("href"),
                    "rel": sorted(
                        {
                            token.casefold()
                            for token in (attributes.get("rel") or "").split()
                            if token
                        }
                    ),
                    "article_id": attributes.get("data-raos-article-id"),
                    "cta_id": attributes.get("data-raos-cta-id"),
                    "snapshot_id": attributes.get("data-raos-snapshot-id"),
                    "offer_id": attributes.get("data-raos-offer-id"),
                    "product_id": attributes.get("data-raos-product-id"),
                    "placement": attributes.get("data-raos-placement"),
                    "rakuten_measurement_id": attributes.get(
                        "data-raos-rakuten-measurement-id"
                    ),
                }
            )
        if lowered == "a" and isinstance(attributes.get("href"), str):
            href = attributes["href"]
            try:
                hostname = urlsplit(href).hostname
            except ValueError:
                hostname = None
            if hostname == "hb.afl.rakuten.co.jp":
                self.affiliate_links.append(
                    {
                        "href": href,
                        "article_id": attributes.get("data-raos-article-id"),
                        "product_id": attributes.get("data-raos-product-id"),
                        "placement": attributes.get("data-raos-placement"),
                    }
                )
        if lowered == "img" and isinstance(product_id, str):
            image_product_id = attributes.get("data-raos-product-image-id")
            self.product_images.append(
                {
                    "product_id": image_product_id or product_id,
                    "src": attributes.get("src") or "",
                    "alt": attributes.get("alt") or "",
                }
            )
        if self._suppressed_depth == 0 and lowered in {
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        }:
            if self._heading_tag is not None:
                raise ValueError("nested public heading")
            self._heading_tag = lowered
            self._heading_parts = []
        if lowered not in self._VOID_ELEMENTS:
            self._elements.append((lowered, product_id, in_disclosure))

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == self._heading_tag:
            heading = _normalized_public_text(self._heading_parts)
            if not heading:
                raise ValueError("empty public heading")
            self.headings.append(heading)
            self.heading_outline.append((lowered, heading))
            if lowered == "h1":
                self.h1_titles.append(heading)
            self._heading_tag = None
            self._heading_parts = []
        if lowered == "title" and self._title_parts is not None:
            title = _normalized_public_text(self._title_parts)
            if title:
                self.page_titles.append(title)
            self._title_parts = None
        if lowered == "script" and self._json_ld_parts is not None:
            self.json_ld_payloads.append("".join(self._json_ld_parts))
            self._json_ld_parts = None
        if lowered in {"script", "style", "noscript", "template"}:
            self._suppressed_depth = max(0, self._suppressed_depth - 1)
        for index in range(len(self._elements) - 1, -1, -1):
            if self._elements[index][0] == lowered:
                del self._elements[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._json_ld_parts is not None:
            self._json_ld_parts.append(data)
        if self._suppressed_depth:
            return
        self.visible_text.append(data)
        if self._title_parts is not None:
            self._title_parts.append(data)
        if self._heading_tag is not None:
            self._heading_parts.append(data)
        if self._elements and self._elements[-1][2]:
            self.disclosure_text.append(data)

    def close(self) -> None:
        super().close()
        if self._heading_tag is not None:
            raise ValueError("unclosed public heading")


def fail(code: str) -> NoReturn:
    raise PublicationFailure(code) from None


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError, RecursionError:
        fail("RAOS_WORDPRESS_REQUEST_JSON_INVALID")


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def exact_object(
    value: object, required: set[str], optional: set[str] | None = None
) -> dict[str, object]:
    if type(value) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_INPUT_INVALID")
    record = value
    allowed = required | (optional or set())
    if set(record) - allowed or not required.issubset(record):
        fail("RAOS_WORDPRESS_REQUEST_INPUT_INVALID")
    if any(type(key) is not str for key in record):
        fail("RAOS_WORDPRESS_REQUEST_INPUT_INVALID")
    return record


def load_json(path: Path, maximum: int, code: str) -> dict[str, object]:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        fail(code)
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size != len(payload)
        or not 1 <= len(payload) <= maximum
    ):
        fail(code)
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except UnicodeError, json.JSONDecodeError:
        fail(code)
    if type(value) is not dict:
        fail(code)
    return value


def _load_owner_private_json_snapshot(
    path: Path,
    maximum: int,
    code: str,
) -> tuple[dict[str, object], bytes]:
    """Load one exact private receipt through a non-following file descriptor."""

    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or not 1 <= before.st_size <= maximum
        ):
            fail(code)
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                fail(code)
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
    except OSError:
        fail(code)
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
    if len(payload) != before.st_size or (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        fail(code)
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except UnicodeError, json.JSONDecodeError:
        fail(code)
    if type(value) is not dict:
        fail(code)
    return value, payload


@dataclass(frozen=True)
class Article:
    local_slug: str
    production_slug: str
    title: str
    excerpt: str
    block_markup: str
    taxonomies: dict[str, list[int]]
    post_type: str = "post"
    required_key_content: tuple[str, ...] = ()

    def document(self) -> dict[str, object]:
        return {
            "post_type": self.post_type,
            "title": self.title,
            "slug": self.production_slug,
            "excerpt": self.excerpt,
            "block_markup": self.block_markup,
            "taxonomies": self.taxonomies,
            "media_ids": [],
        }

    def desired_sha256(self) -> str:
        return sha256_json(self.document())


def expected_social_image_url(article: Article) -> str:
    """Return the closed theme image expected for one publication document."""

    if article.post_type == "page":
        return EXPECTED_SOCIAL_IMAGE_URL
    image_name = EXPECTED_ARTICLE_SOCIAL_IMAGE_BY_SLUG.get(article.production_slug)
    if image_name is None:
        fail("RAOS_WORDPRESS_REQUEST_ARTICLE_SELECTION_INVALID")
    return (
        f"{ORIGIN}/wp-content/themes/kurashinoshirube-child/assets/images/{image_name}"
    )


def _valid_taxonomies(value: object) -> dict[str, list[int]]:
    expected = {"category", "post_format", "post_tag"}
    if type(value) is not dict or set(value) != expected:
        fail("RAOS_WORDPRESS_REQUEST_MAPPING_INVALID")
    result: dict[str, list[int]] = {}
    for taxonomy in sorted(expected):
        term_ids = value[taxonomy]
        if (
            type(term_ids) is not list
            or len(term_ids) > 128
            or any(type(term_id) is not int or term_id < 1 for term_id in term_ids)
            or len(set(term_ids)) != len(term_ids)
            or term_ids != sorted(term_ids)
            or (taxonomy == "category" and not term_ids)
            or (taxonomy != "category" and term_ids)
        ):
            fail("RAOS_WORDPRESS_REQUEST_MAPPING_INVALID")
        result[taxonomy] = list(term_ids)
    return result


def load_articles(
    selection: str,
    *,
    fixture_root: Path = SOURCE_FIXTURE_ROOT,
) -> list[Article]:
    if not fixture_root.is_absolute():
        fail("RAOS_WORDPRESS_REQUEST_FIXTURE_INVALID")
    try:
        root_metadata = fixture_root.lstat()
        article_directory = fixture_root / "articles"
        article_directory_metadata = article_directory.lstat()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_FIXTURE_INVALID")
    if (
        fixture_root.is_symlink()
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.geteuid()
        or article_directory.is_symlink()
        or not stat.S_ISDIR(article_directory_metadata.st_mode)
        or article_directory_metadata.st_uid != os.geteuid()
    ):
        fail("RAOS_WORDPRESS_REQUEST_FIXTURE_INVALID")
    fixture = exact_object(
        load_json(
            fixture_root / "posts.json",
            256 * 1024,
            "RAOS_WORDPRESS_REQUEST_FIXTURE_INVALID",
        ),
        {"schema", "seed_version", "posts"},
    )
    mapping = exact_object(
        load_json(MAPPING_PATH, 256 * 1024, "RAOS_WORDPRESS_REQUEST_MAPPING_INVALID"),
        {"schema", "origin", "editor_endpoint", "review_url", "articles", "pages"},
    )
    if (
        fixture["schema"] != "RAOS_WORDPRESS_LOCAL_PREVIEW_FIXTURE_V1"
        or mapping["schema"] != "RAOS_WORDPRESS_PRODUCTION_MAPPING_V1"
        or mapping["origin"] != ORIGIN
        or mapping["editor_endpoint"] != EDITOR_ENDPOINT
        or mapping["review_url"] != REVIEW_URL
        or type(fixture["posts"]) is not list
        or type(mapping["articles"]) is not list
        or not fixture["posts"]
        or len(fixture["posts"]) != len(mapping["articles"])
    ):
        fail("RAOS_WORDPRESS_REQUEST_MAPPING_INVALID")

    fixture_by_slug: dict[str, dict[str, object]] = {}
    for raw_post in fixture["posts"]:
        post = exact_object(
            raw_post,
            {
                "article_id",
                "category",
                "content_file",
                "date",
                "excerpt",
                "slug",
                "title",
            },
        )
        local_slug = post["slug"]
        if (
            type(local_slug) is not str
            or not local_slug.startswith("local-preview-")
            or SLUG_RE.fullmatch(local_slug) is None
            or post["article_id"] != local_slug
            or local_slug in fixture_by_slug
        ):
            fail("RAOS_WORDPRESS_REQUEST_FIXTURE_INVALID")
        fixture_by_slug[local_slug] = post

    mapping_by_production: dict[str, dict[str, object]] = {}
    mapped_local: set[str] = set()
    for raw_mapping in mapping["articles"]:
        row = exact_object(
            raw_mapping,
            {"local_slug", "production_slug", "local_category", "taxonomies"},
        )
        local_slug = row["local_slug"]
        production_slug = row["production_slug"]
        if (
            type(local_slug) is not str
            or type(production_slug) is not str
            or local_slug not in fixture_by_slug
            or local_slug in mapped_local
            or SLUG_RE.fullmatch(production_slug) is None
            or production_slug != local_slug.removeprefix("local-preview-")
            or production_slug in mapping_by_production
            or row["local_category"] != fixture_by_slug[local_slug]["category"]
        ):
            fail("RAOS_WORDPRESS_REQUEST_MAPPING_INVALID")
        _valid_taxonomies(row["taxonomies"])
        mapped_local.add(local_slug)
        mapping_by_production[production_slug] = row
    if mapped_local != set(fixture_by_slug):
        fail("RAOS_WORDPRESS_REQUEST_MAPPING_INVALID")

    available = set(mapping_by_production)
    if selection == "all":
        if len(available) != EXPECTED_ALL_ARTICLE_COUNT:
            fail("RAOS_WORDPRESS_REQUEST_PORTFOLIO_INCOMPLETE")
        selected = available
    else:
        parts = selection.split(",")
        if (
            not parts
            or any(not part or part.strip() != part for part in parts)
            or len(set(parts)) != len(parts)
            or any(SLUG_RE.fullmatch(part) is None for part in parts)
            or not set(parts).issubset(available)
        ):
            fail("RAOS_WORDPRESS_REQUEST_ARTICLE_SELECTION_INVALID")
        selected = set(parts)

    result: list[Article] = []
    for production_slug, row in mapping_by_production.items():
        if production_slug not in selected:
            continue
        local_slug = str(row["local_slug"])
        post = fixture_by_slug[local_slug]
        title = post["title"]
        excerpt = post["excerpt"]
        content_file = post["content_file"]
        if (
            type(title) is not str
            or not title.strip()
            or len(title) > 500
            or len(title.encode("utf-8")) > 2000
            or "<" in title
            or ">" in title
            or type(excerpt) is not str
            or len(excerpt.encode("utf-8")) > 10_000
            or type(content_file) is not str
            or content_file != f"articles/{production_slug}.html"
            or re.fullmatch(r"articles/[a-z0-9-]+\.html", content_file) is None
        ):
            fail("RAOS_WORDPRESS_REQUEST_FIXTURE_INVALID")
        content_path = fixture_root / content_file
        try:
            metadata = content_path.lstat()
            payload = content_path.read_bytes()
        except OSError:
            fail("RAOS_WORDPRESS_REQUEST_ARTICLE_UNAVAILABLE")
        expected_parent = (fixture_root / "articles").resolve()
        if (
            content_path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or content_path.parent.resolve() != expected_parent
            or metadata.st_size != len(payload)
            or not 1 <= len(payload) <= MAX_CONTENT_BYTES
        ):
            fail("RAOS_WORDPRESS_REQUEST_ARTICLE_INVALID")
        try:
            markup = payload.decode("utf-8", errors="strict")
        except UnicodeError:
            fail("RAOS_WORDPRESS_REQUEST_ARTICLE_INVALID")
        if "\x00" in markup:
            fail("RAOS_WORDPRESS_REQUEST_ARTICLE_INVALID")
        result.append(
            Article(
                local_slug=local_slug,
                production_slug=production_slug,
                title=title,
                excerpt=excerpt,
                block_markup=markup,
                taxonomies=_valid_taxonomies(row["taxonomies"]),
            )
        )
    if not result:
        fail("RAOS_WORDPRESS_REQUEST_ARTICLE_SELECTION_INVALID")
    if selection == "all" and len(result) != EXPECTED_ALL_ARTICLE_COUNT:
        fail("RAOS_WORDPRESS_REQUEST_PORTFOLIO_INCOMPLETE")
    return result


def load_policy_pages(
    *,
    fixture_root: Path = SOURCE_FIXTURE_ROOT,
    profile: str = "local",
) -> list[Article]:
    """Load one closed local-preview or production policy document set."""

    if not fixture_root.is_absolute() or profile not in {"local", "production"}:
        fail("RAOS_WORDPRESS_REQUEST_FIXTURE_INVALID")
    page_directory_name = "pages" if profile == "local" else "production-pages"
    fixture_name = "pages.json" if profile == "local" else "production-pages.json"
    expected_schema = (
        "RAOS_WORDPRESS_LOCAL_PREVIEW_PAGES_V1"
        if profile == "local"
        else "RAOS_WORDPRESS_PRODUCTION_POLICY_PAGES_V1"
    )
    page_directory = fixture_root / page_directory_name
    try:
        root_metadata = fixture_root.lstat()
        directory_metadata = page_directory.lstat()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_FIXTURE_INVALID")
    if (
        fixture_root.is_symlink()
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.geteuid()
        or page_directory.is_symlink()
        or not stat.S_ISDIR(directory_metadata.st_mode)
        or directory_metadata.st_uid != os.geteuid()
    ):
        fail("RAOS_WORDPRESS_REQUEST_FIXTURE_INVALID")
    fixture = exact_object(
        load_json(
            fixture_root / fixture_name,
            64 * 1024,
            "RAOS_WORDPRESS_REQUEST_PAGE_FIXTURE_INVALID",
        ),
        {"schema", "seed_version", "pages"},
    )
    mapping = exact_object(
        load_json(MAPPING_PATH, 256 * 1024, "RAOS_WORDPRESS_REQUEST_MAPPING_INVALID"),
        {"schema", "origin", "editor_endpoint", "review_url", "articles", "pages"},
    )
    raw_pages = fixture.get("pages")
    raw_mappings = mapping.get("pages")
    if (
        fixture.get("schema") != expected_schema
        or type(raw_pages) is not list
        or type(raw_mappings) is not list
        or len(raw_pages) != EXPECTED_POLICY_PAGE_COUNT
        or len(raw_mappings) != EXPECTED_POLICY_PAGE_COUNT
    ):
        fail("RAOS_WORDPRESS_REQUEST_PAGE_FIXTURE_INVALID")
    mapping_by_slug: dict[str, tuple[str, ...]] = {}
    for raw_mapping in raw_mappings:
        row = exact_object(
            raw_mapping,
            {
                "production_slug",
                "local_required_key_content",
                "production_required_key_content",
            },
        )
        slug = row.get("production_slug")
        key_content = row.get(f"{profile}_required_key_content")
        if (
            type(slug) is not str
            or SLUG_RE.fullmatch(slug) is None
            or slug in mapping_by_slug
            or type(key_content) is not list
            or not 1 <= len(key_content) <= 8
            or any(
                type(value) is not str
                or not value.strip()
                or len(value.encode("utf-8")) > 512
                for value in key_content
            )
            or len(set(key_content)) != len(key_content)
        ):
            fail("RAOS_WORDPRESS_REQUEST_MAPPING_INVALID")
        mapping_by_slug[slug] = tuple(key_content)

    result: list[Article] = []
    seen: set[str] = set()
    for raw_page in raw_pages:
        page = exact_object(raw_page, {"content_file", "excerpt", "slug", "title"})
        slug = page.get("slug")
        title = page.get("title")
        excerpt = page.get("excerpt")
        content_file = page.get("content_file")
        if (
            type(slug) is not str
            or slug not in mapping_by_slug
            or slug in seen
            or type(title) is not str
            or not title.strip()
            or "<" in title
            or ">" in title
            or len(title.encode("utf-8")) > 2000
            or type(excerpt) is not str
            or not excerpt.strip()
            or "<" in excerpt
            or ">" in excerpt
            or len(excerpt.encode("utf-8")) > 512
            or content_file != f"{page_directory_name}/{slug}.html"
        ):
            fail("RAOS_WORDPRESS_REQUEST_PAGE_FIXTURE_INVALID")
        content_path = fixture_root / str(content_file)
        try:
            metadata = content_path.lstat()
            payload = content_path.read_bytes()
        except OSError:
            fail("RAOS_WORDPRESS_REQUEST_PAGE_UNAVAILABLE")
        if (
            content_path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or content_path.parent.resolve() != page_directory.resolve()
            or metadata.st_size != len(payload)
            or not 1 <= len(payload) <= MAX_CONTENT_BYTES
        ):
            fail("RAOS_WORDPRESS_REQUEST_PAGE_INVALID")
        try:
            markup = payload.decode("utf-8", errors="strict")
        except UnicodeError:
            fail("RAOS_WORDPRESS_REQUEST_PAGE_INVALID")
        if (
            "\x00" in markup
            or re.search(
                r"<(?:script|style|iframe|object|embed|form|input)\b",
                markup,
                flags=re.IGNORECASE,
            )
            or re.search(r"(?:javascript|data)\s*:", markup, flags=re.IGNORECASE)
            or any(value not in markup for value in mapping_by_slug[slug])
            or (
                profile == "production"
                and any(
                    marker in markup
                    for marker in {
                        "LOCAL WORDPRESS PREVIEW",
                        "このローカルプレビュー",
                        "ローカルWordPressプレビュー",
                    }
                )
            )
        ):
            fail("RAOS_WORDPRESS_REQUEST_PAGE_KSES_INVALID")
        seen.add(slug)
        result.append(
            Article(
                local_slug=slug,
                production_slug=slug,
                title=title,
                excerpt=excerpt,
                block_markup=markup,
                taxonomies={},
                post_type="page",
                required_key_content=mapping_by_slug[slug],
            )
        )
    if seen != set(mapping_by_slug):
        fail("RAOS_WORDPRESS_REQUEST_MAPPING_INVALID")
    return result


def load_publication_items(
    selection: str,
    *,
    article_fixture_root: Path = SOURCE_FIXTURE_ROOT,
    page_fixture_root: Path = SOURCE_FIXTURE_ROOT,
) -> list[Article]:
    articles = load_articles(selection, fixture_root=article_fixture_root)
    if selection != "all":
        return articles
    items = [
        *articles,
        *load_policy_pages(
            fixture_root=page_fixture_root,
            profile="production",
        ),
    ]
    if len(items) != EXPECTED_ALL_ARTICLE_COUNT + EXPECTED_POLICY_PAGE_COUNT:
        fail("RAOS_WORDPRESS_REQUEST_PORTFOLIO_INCOMPLETE")
    return items


def run_editorial_portfolio_refresh(
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> None:
    """Capture fresh provider evidence and materialize reviewed/public variants."""

    commands = (
        (
            (sys.executable, PORTFOLIO_SCRIPT.as_posix(), "capture"),
            "RAOS_WORDPRESS_REQUEST_PORTFOLIO_CAPTURE_FAILED",
        ),
        (
            (
                sys.executable,
                PORTFOLIO_SCRIPT.as_posix(),
                "materialize-local",
                "--output-root",
                PREVIEW_PRIVATE_ROOT.as_posix(),
            ),
            "RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_FAILED",
        ),
        (
            (
                sys.executable,
                PORTFOLIO_SCRIPT.as_posix(),
                "materialize-production",
                "--output-root",
                PORTFOLIO_PRIVATE_ROOT.as_posix(),
            ),
            "RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_FAILED",
        ),
    )
    for command, code in commands:
        try:
            completed = runner(
                command,
                cwd=ROOT,
                stdin=None,
                stdout=None,
                stderr=None,
                env=dict(PORTFOLIO_SUBPROCESS_ENVIRONMENT),
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            fail(code)
        if completed.returncode != 0:
            fail(code)


def _validated_materialization_media(
    value: object,
    expected_product_ids: set[str],
    *,
    code: str,
) -> list[dict[str, str]]:
    """Validate the complete, one-image-per-product materialization receipt."""

    if type(value) is not list or len(value) != len(expected_product_ids):
        fail(code)
    media: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in value:
        if type(raw) is not dict or set(raw) != {
            "product_id",
            "image_sha256",
            "image_extension",
        }:
            fail(code)
        product_id = raw.get("product_id")
        image_sha256 = raw.get("image_sha256")
        image_extension = raw.get("image_extension")
        if (
            type(product_id) is not str
            or product_id not in expected_product_ids
            or product_id in seen
            or type(image_sha256) is not str
            or SHA256_RE.fullmatch(image_sha256) is None
            or image_sha256 == "0" * 64
            or type(image_extension) is not str
            or image_extension not in {"jpg", "png", "gif"}
        ):
            fail(code)
        seen.add(product_id)
        media.append(
            {
                "product_id": product_id,
                "image_sha256": image_sha256,
                "image_extension": image_extension,
            }
        )
    if seen != expected_product_ids:
        fail(code)
    return media


def _expected_materialization_completion(
    expected_product_count: int,
) -> dict[str, object]:
    if type(expected_product_count) is not int or expected_product_count <= 0:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    return {
        "state": "COMPLETE",
        "product_count": expected_product_count,
        "verified_product_count": expected_product_count,
        "product_card_count": EXPECTED_MATERIALIZED_PRODUCT_CARD_COUNT,
        "verified_product_card_count": EXPECTED_MATERIALIZED_PRODUCT_CARD_COUNT,
        "affiliate_cta_count": EXPECTED_MATERIALIZED_AFFILIATE_CTA_COUNT,
        "verified_affiliate_cta_count": EXPECTED_MATERIALIZED_AFFILIATE_CTA_COUNT,
        "neutral_product_image_count": 0,
        "manufacturer_fallback_cta_count": 0,
        "measurement_collection_enabled": False,
    }


def _validated_materialization_completion(
    value: object,
    *,
    expected_product_count: int,
    code: str,
) -> dict[str, object]:
    """Require the fail-closed, fully verified V2 completion declaration."""

    expected = _expected_materialization_completion(expected_product_count)
    if type(value) is not dict or set(value) != set(expected):
        fail(code)
    if (
        type(value.get("state")) is not str
        or any(
            type(value.get(name)) is not int
            for name in {
                "product_count",
                "verified_product_count",
                "product_card_count",
                "verified_product_card_count",
                "affiliate_cta_count",
                "verified_affiliate_cta_count",
                "neutral_product_image_count",
                "manufacturer_fallback_cta_count",
            }
        )
        or type(value.get("measurement_collection_enabled")) is not bool
        or value != expected
    ):
        fail(code)
    return dict(value)


def _owner_materialized_product_ids(*, code: str) -> set[str]:
    """Derive the exact product set from the tracked V2 owner contract."""

    try:
        portfolio = load_editorial_portfolio_v2(ROOT)
    except EditorialPortfolioV2Failure:
        fail(code)
    product_ids = {product.product_id for product in portfolio.products}
    if not product_ids or len(product_ids) != len(portfolio.products):
        fail(code)
    return product_ids


def _current_v2_source_binding(*, now: datetime) -> tuple[str, str, str, str]:
    """Reload the V2 portfolio, status and sales audit as one exact binding."""

    try:
        portfolio_before = v2_portfolio_sha256(ROOT)
    except EditorialPortfolioV2Failure:
        fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
    _, status_before = _load_owner_private_json_snapshot(
        ROOT / V2_STATUS_RELATIVE_PATH,
        MAX_RECEIPT_BYTES,
        "RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID",
    )
    try:
        portfolio = load_editorial_portfolio_v2(ROOT)
        audit = require_manufacturer_sales_state_for_products_v1(
            portfolio,
            tuple(product.product_id for product in portfolio.products),
            now=now,
        )
        portfolio_after = v2_portfolio_sha256(ROOT)
    except EditorialPortfolioV2Failure:
        fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
    _, status_after = _load_owner_private_json_snapshot(
        ROOT / V2_STATUS_RELATIVE_PATH,
        MAX_RECEIPT_BYTES,
        "RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID",
    )
    if portfolio_before != portfolio_after or status_before != status_after:
        fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
    return (
        portfolio_before,
        hashlib.sha256(status_before).hexdigest(),
        audit.document_sha256,
        audit.checked_at_utc,
    )


def _current_activation_v2_evidence_binding(*, now: datetime) -> dict[str, object]:
    """Return the URL-free provider identities behind the current V2 receipts."""

    try:
        evidence = _load_verified_v2_evidence(ROOT, now=now)
    except RakutenMeasurementActivationV3Failure:
        fail("RAOS_WORDPRESS_REQUEST_RAKUTEN_ACTIVATION_INVALID")
    return {
        "portfolio_sha256": evidence.portfolio_sha256,
        "evidence_status_sha256": evidence.status_sha256,
        "manufacturer_sales_state_sha256": (evidence.manufacturer_sales_state_sha256),
        "manufacturer_sales_state_checked_at_utc": (
            evidence.manufacturer_sales_state_checked_at_utc
        ),
        "product_safety": dict(evidence.product_safety),
        "products": {
            product_id: {
                "state": "verified",
                "provider_binding_sha256": product.provider_binding_sha256,
            }
            for product_id, product in sorted(evidence.products.items())
        },
        "media": [
            {
                "product_id": product_id,
                "image_sha256": product.image_sha256,
            }
            for product_id, product in sorted(evidence.products.items())
        ],
    }


def production_materialization_binding(
    articles: Sequence[Article],
    *,
    require_recent: bool = True,
) -> dict[str, object]:
    """Bind publication to stable, private provider/materialization evidence."""

    production_document, production_receipt_raw = _load_owner_private_json_snapshot(
        PRODUCTION_MATERIALIZATION_RECEIPT,
        MAX_RECEIPT_BYTES,
        "RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID",
    )
    document = exact_object(
        production_document,
        {
            "schema",
            "mode",
            "generated_at",
            "portfolio_sha256",
            "evidence_status_sha256",
            "manufacturer_sales_state_sha256",
            "manufacturer_sales_state_checked_at_utc",
            "product_safety",
            "articles",
            "products",
            "media",
            "completion",
        },
    )
    generated_at = document["generated_at"]
    if type(generated_at) is not str:
        fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
    try:
        generated = datetime.strptime(generated_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
    except TypeError, ValueError:
        fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
    now = datetime.now(UTC)
    (
        current_portfolio_sha256,
        current_status_sha256,
        current_sales_sha256,
        current_sales_checked_at,
    ) = _current_v2_source_binding(now=now)
    try:
        product_safety = _validate_product_safety_publication_binding(
            document["product_safety"],
            require_complete=True,
        )
    except RakutenMeasurementActivationV3Failure:
        fail("RAOS_WORDPRESS_REQUEST_PRODUCT_SAFETY_INVALID")
    current_product_safety = _current_activation_v2_evidence_binding(now=now).get(
        "product_safety"
    )
    if current_product_safety != product_safety:
        fail("RAOS_WORDPRESS_REQUEST_PRODUCT_SAFETY_INVALID")
    if (
        document["schema"] != "RAOS_EDITORIAL_PORTFOLIO_MATERIALIZATION_RECEIPT_V2"
        or document["mode"] != "production"
        or type(document["portfolio_sha256"]) is not str
        or SHA256_RE.fullmatch(document["portfolio_sha256"]) is None
        or document["portfolio_sha256"] != current_portfolio_sha256
        or type(document["evidence_status_sha256"]) is not str
        or SHA256_RE.fullmatch(document["evidence_status_sha256"]) is None
        or document["evidence_status_sha256"] == "0" * 64
        or document["evidence_status_sha256"] != current_status_sha256
        or type(document["manufacturer_sales_state_sha256"]) is not str
        or SHA256_RE.fullmatch(document["manufacturer_sales_state_sha256"]) is None
        or document["manufacturer_sales_state_sha256"] != current_sales_sha256
        or document["manufacturer_sales_state_checked_at_utc"]
        != current_sales_checked_at
        or generated > now + timedelta(seconds=30)
        or (require_recent and now - generated > timedelta(minutes=15))
        or type(document["articles"]) is not list
        or len(document["articles"]) != EXPECTED_ALL_ARTICLE_COUNT
        or type(document["products"]) is not list
        or not document["products"]
    ):
        fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
    article_hashes: dict[str, str] = {}
    for raw in document["articles"]:
        row = exact_object(raw, {"article_id", "production_slug", "content_sha256"})
        slug = row["production_slug"]
        digest = row["content_sha256"]
        if (
            type(row["article_id"]) is not str
            or not row["article_id"]
            or type(slug) is not str
            or SLUG_RE.fullmatch(slug) is None
            or slug in article_hashes
            or type(digest) is not str
            or SHA256_RE.fullmatch(digest) is None
        ):
            fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
        article_hashes[slug] = digest
    expected_articles = {
        article.production_slug: hashlib.sha256(
            article.block_markup.encode("utf-8")
        ).hexdigest()
        for article in articles
    }
    if article_hashes != expected_articles:
        fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
    product_bindings: dict[str, dict[str, str]] = {}
    for raw in document["products"]:
        row = exact_object(
            raw,
            {"product_id", "state", "provider_binding_sha256"},
        )
        product_id = row["product_id"]
        state = row["state"]
        digest = row["provider_binding_sha256"]
        if (
            type(product_id) is not str
            or not re.fullmatch(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*", product_id)
            or product_id in product_bindings
            or state != "verified"
            or type(digest) is not str
            or SHA256_RE.fullmatch(digest) is None
        ):
            fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
        product_bindings[product_id] = {
            "state": state,
            "provider_binding_sha256": digest,
        }
    expected_product_ids: set[str] = set()
    for article in articles:
        parser = _PublicPageEvidenceParser()
        try:
            parser.feed(article.block_markup)
            parser.close()
        except Exception:
            fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
        expected_product_ids.update(
            str(cta["product_id"])
            for cta in _validated_ctas(
                parser,
                allow_empty=article.production_slug in ZERO_PRODUCT_ROUTE_SLUGS,
            )
            if type(cta.get("product_id")) is str
        )
    if set(product_bindings) != expected_product_ids:
        fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
    if expected_product_ids != _owner_materialized_product_ids(
        code="RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID"
    ):
        fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
    media = _validated_materialization_media(
        document["media"],
        expected_product_ids,
        code="RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID",
    )
    completion = _validated_materialization_completion(
        document["completion"],
        expected_product_count=len(expected_product_ids),
        code="RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID",
    )
    local_receipt_raw = _validate_local_materialization_pair(
        document,
        require_recent=require_recent,
    )
    final_now = datetime.now(UTC)
    if (
        _current_v2_source_binding(now=final_now)
        != (
            current_portfolio_sha256,
            current_status_sha256,
            current_sales_sha256,
            current_sales_checked_at,
        )
        or generated > final_now + timedelta(seconds=30)
        or (require_recent and final_now - generated > timedelta(minutes=15))
        or _load_owner_private_json_snapshot(
            PRODUCTION_MATERIALIZATION_RECEIPT,
            MAX_RECEIPT_BYTES,
            "RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID",
        )[1]
        != production_receipt_raw
        or _load_owner_private_json_snapshot(
            LOCAL_MATERIALIZATION_RECEIPT,
            MAX_RECEIPT_BYTES,
            "RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID",
        )[1]
        != local_receipt_raw
        or _current_activation_v2_evidence_binding(now=final_now).get("product_safety")
        != product_safety
    ):
        fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
    return {
        "schema": "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V1",
        "portfolio_sha256": document["portfolio_sha256"],
        "evidence_status_sha256": current_status_sha256,
        "local_receipt_sha256": hashlib.sha256(local_receipt_raw).hexdigest(),
        "production_receipt_sha256": hashlib.sha256(production_receipt_raw).hexdigest(),
        "manufacturer_sales_state_sha256": current_sales_sha256,
        "manufacturer_sales_state_checked_at_utc": current_sales_checked_at,
        "product_safety": product_safety,
        "articles": dict(sorted(article_hashes.items())),
        "products": {
            product_id: product_bindings[product_id]
            for product_id in sorted(product_bindings)
        },
        "media": sorted(media, key=lambda row: row["product_id"]),
        "completion": completion,
    }


def _validate_local_materialization_pair(
    production: Mapping[str, object],
    *,
    require_recent: bool,
) -> bytes:
    """Prove that preview and proposal variants came from one evidence set."""

    local_document, local_receipt_raw = _load_owner_private_json_snapshot(
        LOCAL_MATERIALIZATION_RECEIPT,
        MAX_RECEIPT_BYTES,
        "RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID",
    )
    local = exact_object(
        local_document,
        {
            "schema",
            "mode",
            "generated_at",
            "portfolio_sha256",
            "evidence_status_sha256",
            "manufacturer_sales_state_sha256",
            "manufacturer_sales_state_checked_at_utc",
            "product_safety",
            "articles",
            "products",
            "media",
            "completion",
        },
    )
    generated_at = local["generated_at"]
    if type(generated_at) is not str:
        fail("RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID")
    try:
        generated = datetime.strptime(generated_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
    except TypeError, ValueError:
        fail("RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID")
    now = datetime.now(UTC)
    production_articles = production.get("articles")
    production_products = production.get("products")
    production_media = production.get("media")
    production_completion = production.get("completion")
    if (
        local["schema"] != "RAOS_EDITORIAL_PORTFOLIO_MATERIALIZATION_RECEIPT_V2"
        or local["mode"] != "local"
        or generated > now + timedelta(seconds=30)
        or (require_recent and now - generated > timedelta(minutes=15))
        or local["portfolio_sha256"] != production.get("portfolio_sha256")
        or local["evidence_status_sha256"] != production.get("evidence_status_sha256")
        or local["manufacturer_sales_state_sha256"]
        != production.get("manufacturer_sales_state_sha256")
        or local["manufacturer_sales_state_checked_at_utc"]
        != production.get("manufacturer_sales_state_checked_at_utc")
        or local["product_safety"] != production.get("product_safety")
        or local["products"] != production_products
        or local["media"] != production_media
        or local["completion"] != production_completion
        or type(local["articles"]) is not list
        or type(production_articles) is not list
        or len(local["articles"]) != EXPECTED_ALL_ARTICLE_COUNT
    ):
        fail("RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID")
    expected_product_ids = {
        row.get("product_id")
        for row in local["products"]
        if type(row) is dict and type(row.get("product_id")) is str
    }
    if expected_product_ids != _owner_materialized_product_ids(
        code="RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID"
    ):
        fail("RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID")
    _validated_materialization_media(
        local["media"],
        expected_product_ids,
        code="RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID",
    )
    _validated_materialization_completion(
        local["completion"],
        expected_product_count=len(expected_product_ids),
        code="RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID",
    )
    production_identities = {
        (row.get("article_id"), row.get("production_slug"))
        for row in production_articles
        if type(row) is dict
    }
    local_identities: set[tuple[object, object]] = set()
    for raw in local["articles"]:
        row = exact_object(raw, {"article_id", "production_slug", "content_sha256"})
        article_id = row["article_id"]
        slug = row["production_slug"]
        digest = row["content_sha256"]
        if (
            type(article_id) is not str
            or not article_id
            or type(slug) is not str
            or SLUG_RE.fullmatch(slug) is None
            or type(digest) is not str
            or SHA256_RE.fullmatch(digest) is None
            or (article_id, slug) in local_identities
        ):
            fail("RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID")
        local_identities.add((article_id, slug))
        content_path = LOCAL_MATERIALIZED_FIXTURE_ROOT / "articles" / f"{slug}.html"
        try:
            content_metadata = content_path.lstat()
            payload = content_path.read_bytes()
        except OSError:
            fail("RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID")
        if (
            content_path.is_symlink()
            or not stat.S_ISREG(content_metadata.st_mode)
            or content_metadata.st_uid != os.geteuid()
            or content_metadata.st_nlink != 1
            or not 1 <= len(payload) <= MAX_CONTENT_BYTES
            or hashlib.sha256(payload).hexdigest() != digest
        ):
            fail("RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID")
    if local_identities != production_identities:
        fail("RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID")
    return local_receipt_raw


def validate_rakuten_activation_dry_run(
    path: Path | None,
    *,
    require_recent: bool = False,
) -> RakutenMeasurementActivationOverlayV3:
    """Load an exact URL-free owner-private activation receipt and overlays."""

    if path is None or not path.is_absolute():
        fail("RAOS_WORDPRESS_REQUEST_RAKUTEN_ACTIVATION_REQUIRED")
    try:
        portfolio = load_editorial_portfolio_v3(ROOT)
        return validate_rakuten_measurement_activation_v3(
            repository_root=ROOT,
            dry_run_path=path,
            portfolio=portfolio,
            local_v2_fixture_root=LOCAL_MATERIALIZED_FIXTURE_ROOT,
            production_v2_fixture_root=PRODUCTION_MATERIALIZED_FIXTURE_ROOT,
            require_recent=require_recent,
        )
    except EditorialPortfolioV3Failure, RakutenMeasurementActivationV3Failure:
        fail("RAOS_WORDPRESS_REQUEST_RAKUTEN_ACTIVATION_INVALID")


def validate_publication_link_evidence(
    path: Path | None,
    *,
    link_mode: str = "measured-admin",
    require_recent: bool = False,
) -> PublicationOverlay:
    if link_mode == "measured-admin":
        return validate_rakuten_activation_dry_run(path, require_recent=require_recent)
    if link_mode != "standard-api" or path is None:
        fail("RAOS_WORDPRESS_REQUEST_LINK_MODE_INVALID")
    try:
        return validate_standard_api_v1(
            repository_root=ROOT,
            receipt_path=path,
            require_recent=require_recent,
        )
    except (
        EditorialEconomicsV3Failure,
        EditorialPortfolioV2Failure,
        EditorialPortfolioV3Failure,
        RakutenMeasurementActivationV3Failure,
        OSError,
    ):
        fail("RAOS_WORDPRESS_REQUEST_STANDARD_API_INVALID")


def activation_materialization_binding(
    activation: PublicationOverlay,
    articles: Sequence[Article],
    *,
    require_recent: bool,
) -> dict[str, object]:
    """Bind activated output to the exact validated V2 local/production pair."""

    if isinstance(activation, RakutenStandardApiOverlayV1):
        current = validate_publication_link_evidence(
            activation.receipt_path,
            link_mode="standard-api",
            require_recent=require_recent,
        )
        hashes = {
            article.production_slug: hashlib.sha256(
                article.block_markup.encode()
            ).hexdigest()
            for article in articles
            if article.post_type == "post"
        }
        if current != activation or hashes != dict(
            activation.production_article_sha256
        ):
            fail("RAOS_WORDPRESS_REQUEST_STANDARD_API_INVALID")
        binding = dict(activation.binding)
        _validate_materialization_binding(binding)
        return binding
    v2_articles = load_articles(
        "all",
        fixture_root=PRODUCTION_MATERIALIZED_FIXTURE_ROOT,
    )
    v2_binding = production_materialization_binding(
        v2_articles,
        require_recent=require_recent,
    )
    current_v2_evidence = _current_activation_v2_evidence_binding(now=datetime.now(UTC))
    activated_hashes = {
        article.production_slug: hashlib.sha256(
            article.block_markup.encode("utf-8")
        ).hexdigest()
        for article in articles
        if article.post_type == "post"
    }
    if (
        v2_binding.get("portfolio_sha256") != activation.v2_portfolio_sha256
        or v2_binding.get("evidence_status_sha256")
        != activation.v2_evidence_status_sha256
        or v2_binding.get("local_receipt_sha256") != activation.v2_local_receipt_sha256
        or v2_binding.get("production_receipt_sha256")
        != activation.v2_production_receipt_sha256
        or current_v2_evidence.get("portfolio_sha256") != activation.v2_portfolio_sha256
        or current_v2_evidence.get("evidence_status_sha256")
        != activation.v2_evidence_status_sha256
        or v2_binding.get("manufacturer_sales_state_sha256")
        != activation.v2_manufacturer_sales_state_sha256
        or v2_binding.get("manufacturer_sales_state_checked_at_utc")
        != activation.v2_manufacturer_sales_state_checked_at_utc
        or current_v2_evidence.get("manufacturer_sales_state_sha256")
        != activation.v2_manufacturer_sales_state_sha256
        or current_v2_evidence.get("manufacturer_sales_state_checked_at_utc")
        != activation.v2_manufacturer_sales_state_checked_at_utc
        or v2_binding.get("product_safety") != activation.v2_product_safety
        or current_v2_evidence.get("product_safety") != activation.v2_product_safety
        or activated_hashes != dict(activation.production_article_sha256)
        or len(activated_hashes) != EXPECTED_ALL_ARTICLE_COUNT
        or activation.article_count != EXPECTED_ALL_ARTICLE_COUNT
        or activation.provider_slot_count != 20
        or activation.provider_measurement_id_count != 20
        or activation.internal_cta_identity_count
        != EXPECTED_MATERIALIZED_AFFILIATE_CTA_COUNT
        or activation.cta_count != EXPECTED_MATERIALIZED_AFFILIATE_CTA_COUNT
        or activation.live_link_count != EXPECTED_MATERIALIZED_AFFILIATE_CTA_COUNT
    ):
        fail("RAOS_WORDPRESS_REQUEST_RAKUTEN_ACTIVATION_INVALID")
    products = v2_binding.get("products")
    media = v2_binding.get("media")
    completion = v2_binding.get("completion")
    if (
        type(products) is not dict
        or type(media) is not list
        or type(completion) is not dict
    ):
        fail("RAOS_WORDPRESS_REQUEST_RAKUTEN_ACTIVATION_INVALID")
    if (
        current_v2_evidence.get("products") != products
        or current_v2_evidence.get("media") != media
        or production_materialization_binding(
            v2_articles,
            require_recent=require_recent,
        )
        != v2_binding
        or _current_activation_v2_evidence_binding(now=datetime.now(UTC))
        != current_v2_evidence
    ):
        fail("RAOS_WORDPRESS_REQUEST_RAKUTEN_ACTIVATION_INVALID")
    binding: dict[str, object] = {
        "schema": "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3",
        "portfolio_sha256": activation.portfolio_sha256,
        "evidence_status_sha256": activation.v2_evidence_status_sha256,
        "local_receipt_sha256": activation.v2_local_receipt_sha256,
        "production_receipt_sha256": activation.v2_production_receipt_sha256,
        "manufacturer_sales_state_sha256": (
            activation.v2_manufacturer_sales_state_sha256
        ),
        "manufacturer_sales_state_checked_at_utc": (
            activation.v2_manufacturer_sales_state_checked_at_utc
        ),
        "product_safety": dict(activation.v2_product_safety),
        "articles": dict(sorted(activated_hashes.items())),
        "products": products,
        "media": media,
        "completion": completion,
        "activation": {
            "dry_run_sha256": activation.dry_run_sha256,
            "v2_evidence_status_sha256": activation.v2_evidence_status_sha256,
            "v2_local_receipt_sha256": activation.v2_local_receipt_sha256,
            "v2_production_receipt_sha256": (activation.v2_production_receipt_sha256),
            "admin_receipt_sha256": activation.admin_receipt_sha256,
            "money_link_mapping_sha256": activation.money_link_mapping_sha256,
            "provider_slot_set_sha256": activation.provider_slot_set_sha256,
            "provider_measurement_binding_sha256": (
                activation.provider_measurement_binding_sha256
            ),
            "materialized_set_sha256": activation.materialized_set_sha256,
            "local_article_set_sha256": activation.local_article_set_sha256,
            "production_article_set_sha256": (activation.production_article_set_sha256),
            "local_overlay_receipt_sha256": (activation.local_overlay_receipt_sha256),
            "production_overlay_receipt_sha256": (
                activation.production_overlay_receipt_sha256
            ),
            "mapping_generated_at_utc": activation.mapping_generated_at_utc,
            "admin_verified_at_utc": activation.admin_verified_at_utc,
            "activated_at_utc": activation.activated_at_utc,
            "article_count": activation.article_count,
            "provider_slot_count": activation.provider_slot_count,
            "provider_measurement_id_count": (activation.provider_measurement_id_count),
            "internal_cta_identity_count": (activation.internal_cta_identity_count),
            "cta_count": activation.cta_count,
            "live_link_count": activation.live_link_count,
        },
    }
    _validate_materialization_binding(binding)
    return binding


def theme_version() -> str:
    try:
        payload = THEME_STYLE_PATH.read_bytes()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    if not 1 <= len(payload) <= 1024 * 1024:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    match = re.search(rb"(?im)^\s*(?:\*\s*)?Version:\s*([^\r\n]+)", payload[:8192])
    if match is None:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    try:
        value = match.group(1).decode("utf-8", errors="strict").strip()
    except UnicodeError:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    if VERSION_RE.fullmatch(value) is None:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    return value


def theme_runtime_revision() -> str:
    """Read the exact loaded-code revision declared by the reviewed theme source."""

    try:
        payload = THEME_FUNCTIONS_PATH.read_bytes()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    if not 1 <= len(payload) <= MAX_THEME_FILE_BYTES:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    matches = re.findall(
        rb"(?m)^const KURASHINOSHIRUBE_THEME_RUNTIME_REVISION = '([0-9a-f]{64})';$",
        payload,
    )
    if len(matches) != 1:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    try:
        value = matches[0].decode("ascii", errors="strict")
    except UnicodeError:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    if value != EXPECTED_THEME_RUNTIME_REVISION:
        fail("RAOS_WORDPRESS_REQUEST_THEME_RUNTIME_REVISION_INVALID")
    return value


def _git(*arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            (
                "/usr/bin/git",
                "--no-optional-locks",
                "--literal-pathspecs",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                ROOT.as_posix(),
                *arguments,
            ),
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
                "TZ": "UTC",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
    except OSError, subprocess.SubprocessError:
        fail("RAOS_WORDPRESS_REQUEST_THEME_GIT_FAILED")
    if completed.returncode != 0 or len(completed.stdout) > 4 * 1024 * 1024:
        fail("RAOS_WORDPRESS_REQUEST_THEME_GIT_FAILED")
    return completed.stdout


def tracked_theme_tree_sha256() -> str:
    """Hash the exact clean tracked tree using the deployment manifest contract."""
    relative_root = THEME_ROOT.relative_to(ROOT).as_posix()
    if _git("status", "--porcelain=v1", "--", relative_root):
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_DIRTY")
    raw_files = _git("ls-files", "-z", "--", relative_root)
    try:
        tracked = [
            value.decode("utf-8", errors="strict")
            for value in raw_files.split(b"\0")
            if value
        ]
    except UnicodeError:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    if not tracked or len(tracked) > MAX_THEME_FILE_COUNT:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    manifest: list[dict[str, object]] = []
    seen: set[str] = set()
    total = 0
    for repository_relative in sorted(tracked):
        source = ROOT / repository_relative
        try:
            metadata = source.lstat()
            payload = source.read_bytes()
            relative = source.relative_to(THEME_ROOT).as_posix()
        except OSError, ValueError:
            fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
        folded = relative.casefold()
        if (
            source.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size != len(payload)
            or not 0 <= len(payload) <= MAX_THEME_FILE_BYTES
            or re.fullmatch(r"[A-Za-z0-9._/-]+", relative) is None
            or len(relative) > 300
            or folded in seen
        ):
            fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
        seen.add(folded)
        total += len(payload)
        if total > MAX_THEME_PACKAGE_BYTES:
            fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
        manifest.append(
            {
                "path": relative,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest.sort(key=lambda entry: str(entry["path"]))
    return sha256_json(manifest)


def run_preview_checks(
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    *,
    fixture_root: Path = LOCAL_MATERIALIZED_FIXTURE_ROOT,
    link_mode: str = "measured-admin",
) -> None:
    if link_mode not in {"standard-api", "measured-admin"}:
        fail("RAOS_WORDPRESS_REQUEST_LINK_MODE_INVALID")
    if not fixture_root.is_absolute():
        fail("RAOS_WORDPRESS_REQUEST_PREVIEW_FIXTURE_INVALID")
    use_stale_group_bridge = _docker_group_membership_is_stale()
    for target, code in (
        ("wordpress-preview-up", "RAOS_WORDPRESS_REQUEST_PREVIEW_UP_FAILED"),
        ("wordpress-preview-sync", "RAOS_WORDPRESS_REQUEST_PREVIEW_SYNC_FAILED"),
        ("wordpress-preview-check", "RAOS_WORDPRESS_REQUEST_PREVIEW_CHECK_FAILED"),
    ):
        command = (
            (SG_BIN.as_posix(), "docker", "-c", f"{MAKE_BIN.as_posix()} {target}")
            if use_stale_group_bridge
            else (MAKE_BIN.as_posix(), target)
        )
        try:
            completed = runner(
                command,
                cwd=ROOT,
                stdin=None,
                stdout=None,
                stderr=None,
                check=False,
                env={
                    **os.environ,
                    "RAOS_WORDPRESS_PREVIEW_FIXTURE_ROOT": fixture_root.as_posix(),
                    "RAOS_WORDPRESS_LINK_MODE": link_mode,
                },
            )
        except OSError, subprocess.SubprocessError:
            fail(code)
        if completed.returncode != 0:
            fail(code)


def _docker_group_membership_is_stale() -> bool:
    try:
        metadata = DOCKER_SOCKET.stat()
        group = grp.getgrgid(metadata.st_gid)
        username = pwd.getpwuid(os.geteuid()).pw_name
    except OSError, KeyError:
        return False
    return (
        stat.S_ISSOCK(metadata.st_mode)
        and group.gr_name == "docker"
        and username in group.gr_mem
        and metadata.st_gid not in os.getgroups()
    )


def _secure_credential() -> tuple[str, str]:
    try:
        metadata = EDITOR_CREDENTIAL_PATH.lstat()
        payload = EDITOR_CREDENTIAL_PATH.read_bytes()
        parent_metadata = EDITOR_CREDENTIAL_PATH.parent.lstat()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_EDITOR_CREDENTIAL_UNAVAILABLE")
    if (
        EDITOR_CREDENTIAL_PATH.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or not 1 <= len(payload) <= 16 * 1024
        or EDITOR_CREDENTIAL_PATH.parent.is_symlink()
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    ):
        fail("RAOS_WORDPRESS_REQUEST_EDITOR_CREDENTIAL_INSECURE")
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except UnicodeError, json.JSONDecodeError:
        fail("RAOS_WORDPRESS_REQUEST_EDITOR_CREDENTIAL_INVALID")
    record = exact_object(
        value,
        {"schema", "origin", "username", "application_password", "purpose"},
    )
    if (
        record["schema"] != "RAOS_WORDPRESS_APPLICATION_PASSWORD_V1"
        or record["origin"] != ORIGIN
        or record["purpose"] != "editor_mcp"
        or type(record["username"]) is not str
        or not record["username"]
        or type(record["application_password"]) is not str
        or not 20 <= len(record["application_password"]) <= 512
    ):
        fail("RAOS_WORDPRESS_REQUEST_EDITOR_CREDENTIAL_INVALID")
    return record["username"], record["application_password"]


class EditorMcpClient:
    """Small fixed-endpoint Streamable HTTP MCP client."""

    def __init__(self) -> None:
        self.endpoint = EDITOR_ENDPOINT
        self.username, self._basic_auth_value = _secure_credential()
        self.session_id: str | None = None
        self.next_id = 1

    def public_authorization(self) -> str:
        """Build an ephemeral front-end readback header without persisting it."""

        encoded = base64.b64encode(
            f"{self.username}:{self._basic_auth_value}".encode("utf-8")
        ).decode("ascii")
        return f"Basic {encoded}"

    def _request(
        self, value: object, *, notification: bool = False
    ) -> tuple[int, bytes, Mapping[str, str]]:
        data = canonical_json_bytes(value)
        authorization = base64.b64encode(
            f"{self.username}:{self._basic_auth_value}".encode("utf-8")
        ).decode("ascii")
        headers = {
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Basic {authorization}",
            "Content-Type": "application/json",
            "User-Agent": "raos-wordpress-publication-request/1.0.0",
        }
        if self.session_id is not None:
            headers["Mcp-Session-Id"] = self.session_id
            headers["Mcp-Protocol-Version"] = PROTOCOL_VERSION
        request = urllib.request.Request(
            self.endpoint, data=data, headers=headers, method="POST"
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _RefuseRedirectHandler(),
        )
        try:
            with opener.open(request, timeout=45) as response:
                if response.geturl() != EDITOR_ENDPOINT:
                    fail("RAOS_WORDPRESS_REQUEST_REDIRECT_REFUSED")
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    fail("RAOS_WORDPRESS_REQUEST_RESPONSE_TOO_LARGE")
                return response.status, body, response.headers
        except urllib.error.HTTPError as error:
            if 300 <= error.code < 400:
                fail("RAOS_WORDPRESS_REQUEST_REDIRECT_REFUSED")
            code = f"RAOS_WORDPRESS_REQUEST_HTTP_{error.code}"
            try:
                error_body = error.read(64 * 1024)
                parsed = json.loads(error_body.decode("utf-8", errors="strict"))
                candidate = parsed.get("code") if type(parsed) is dict else None
                if type(candidate) is str and re.fullmatch(
                    r"[a-z0-9_]{3,96}", candidate
                ):
                    code = candidate.upper()
            except OSError, UnicodeError, json.JSONDecodeError:
                pass
            fail(code)
        except urllib.error.URLError, TimeoutError, OSError:
            fail("RAOS_WORDPRESS_REQUEST_TRANSPORT_FAILED")

    def message(self, method: str, params: dict[str, object]) -> dict[str, object]:
        request_id = self.next_id
        self.next_id += 1
        _, body, headers = self._request(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        try:
            payload = json.loads(body.decode("utf-8", errors="strict"))
        except UnicodeError, json.JSONDecodeError:
            fail("RAOS_WORDPRESS_REQUEST_MCP_RESPONSE_INVALID")
        if (
            type(payload) is not dict
            or payload.get("jsonrpc") != "2.0"
            or payload.get("id") != request_id
            or "error" in payload
            or type(payload.get("result")) is not dict
        ):
            fail("RAOS_WORDPRESS_REQUEST_MCP_RESPONSE_INVALID")
        if method == "initialize":
            session = headers.get("Mcp-Session-Id")
            if type(session) is not str or not session:
                fail("RAOS_WORDPRESS_REQUEST_MCP_SESSION_INVALID")
            self.session_id = session
        result = payload["result"]
        if type(result) is not dict:
            fail("RAOS_WORDPRESS_REQUEST_MCP_RESPONSE_INVALID")
        return dict(result)

    def initialize(self) -> dict[str, object]:
        result = self.message(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "raos-wordpress-publication-request",
                    "version": "1.0.0",
                },
            },
        )
        if result.get("protocolVersion") != PROTOCOL_VERSION:
            fail("RAOS_WORDPRESS_REQUEST_MCP_PROTOCOL_INVALID")
        status, body, _ = self._request(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            notification=True,
        )
        if status != 202 or body not in {b"", b"null"}:
            fail("RAOS_WORDPRESS_REQUEST_MCP_NOTIFICATION_INVALID")
        return result

    def tools(self) -> dict[str, dict[str, object]]:
        value = self.message("tools/list", {}).get("tools")
        if type(value) is not list:
            fail("RAOS_WORDPRESS_REQUEST_TOOL_CONTRACT_INVALID")
        result: dict[str, dict[str, object]] = {}
        for raw_tool in value:
            if type(raw_tool) is not dict or type(raw_tool.get("name")) is not str:
                fail("RAOS_WORDPRESS_REQUEST_TOOL_CONTRACT_INVALID")
            result[raw_tool["name"]] = raw_tool
        return result

    def call(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        result = self.message("tools/call", {"name": name, "arguments": arguments})
        structured = result.get("structuredContent")
        if result.get("isError") is True or type(structured) is not dict:
            code = structured.get("code") if type(structured) is dict else None
            if type(code) is str and re.fullmatch(r"[a-z0-9_]{3,96}", code):
                fail(code.upper())
            fail("RAOS_WORDPRESS_REQUEST_TOOL_CALL_FAILED")
        return structured


def validate_tool_contract(tools: Mapping[str, Mapping[str, object]]) -> None:
    if set(tools) != EXPECTED_TOOLS:
        fail("RAOS_WORDPRESS_REQUEST_TOOL_CONTRACT_INVALID")
    proposal = tools["raos-codex-content-propose-release"]
    schema = proposal.get("inputSchema")
    if type(schema) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_IDEMPOTENCY_BOOTSTRAP_REQUIRED")
    properties = schema.get("properties")
    required = schema.get("required")
    key = properties.get("idempotency_key") if type(properties) is dict else None
    if (
        schema.get("additionalProperties") is not False
        or type(key) is not dict
        or key.get("type") != "string"
        or key.get("pattern") != "^[0-9a-f]{64}$"
        or type(required) is not list
        or "idempotency_key" in required
    ):
        fail("RAOS_WORDPRESS_REQUEST_IDEMPOTENCY_BOOTSTRAP_REQUIRED")
    batch = tools["raos-codex-publication-batch-register"].get("inputSchema")
    batch_properties = batch.get("properties") if type(batch) is dict else None
    proposal_ids = (
        batch_properties.get("proposal_ids") if type(batch_properties) is dict else None
    )
    expected_theme = (
        batch_properties.get("expected_theme_tree_sha256")
        if type(batch_properties) is dict
        else None
    )
    items = proposal_ids.get("items") if type(proposal_ids) is dict else None
    if (
        type(batch) is not dict
        or batch.get("additionalProperties") is not False
        or batch.get("required") != ["proposal_ids", "expected_theme_tree_sha256"]
        or type(proposal_ids) is not dict
        or proposal_ids.get("type") != "array"
        or proposal_ids.get("minItems") != 1
        or proposal_ids.get("maxItems") != 20
        or proposal_ids.get("uniqueItems") is not True
        or type(items) is not dict
        or items.get("type") != "string"
        or items.get("pattern") != "^[0-9a-f]{64}$"
        or type(expected_theme) is not dict
        or expected_theme.get("type") != "string"
        or expected_theme.get("pattern") != "^[0-9a-f]{64}$"
    ):
        fail("RAOS_WORDPRESS_REQUEST_BATCH_BOOTSTRAP_REQUIRED")


def validate_site_status(
    status: Mapping[str, object],
    *,
    require_measurement_ready: bool = False,
    require_measurement_off: bool = False,
) -> None:
    writes = status.get("writes_enabled")
    theme = status.get("theme")
    yoast = status.get("yoast")
    measurement = status.get("measurement")
    server = status.get("server")
    authorization = status.get("apply_authorization")
    if (
        status.get("schema") != "RAOSWordPressSiteStatusV1"
        or status.get("origin") != ORIGIN
        or status.get("wordpress_version_compatible") is not True
        or status.get("mcp_adapter_version") != "0.6.1"
        or status.get("mcp_adapter_version_compatible") is not True
        or status.get("plugin_version") != EXPECTED_PLUGIN_VERSION
        or status.get("plugin_runtime_revision") != EXPECTED_PLUGIN_RUNTIME_REVISION
        or type(writes) is not dict
        or any(
            writes.get(name) is not True
            for name in (
                "global",
                "draft",
                "content_apply",
                "theme_apply",
                "plugin_apply",
            )
        )
        or type(theme) is not dict
        or theme.get("slug") != "kurashinoshirube-child"
        or theme.get("exists") is not True
        or theme.get("active") is not True
        or type(theme.get("version")) is not str
        or VERSION_RE.fullmatch(theme["version"]) is None
        or type(theme.get("runtime_version")) is not str
        or VERSION_RE.fullmatch(theme["runtime_version"]) is None
        or "runtime_revision" not in theme
        or (
            theme.get("runtime_revision") is not None
            and (
                type(theme.get("runtime_revision")) is not str
                or SHA256_RE.fullmatch(theme["runtime_revision"]) is None
            )
        )
        or yoast
        != {
            "plugin_slug": "wordpress-seo",
            "installed": True,
            "active": True,
            "version": EXPECTED_YOAST_VERSION,
            "version_exact": True,
            "options": EXPECTED_YOAST_OPTIONS,
            "settings_fingerprint": EXPECTED_YOAST_SETTINGS_FINGERPRINT,
            "settings_exact": True,
        }
        or authorization
        != {
            "mode": "approval_scoped_lease",
            "default": False,
            "single_use": True,
            "lease_ttl_seconds": EXPECTED_APPLY_LEASE_TTL_SECONDS,
        }
        or type(server) is not dict
        or server.get("endpoint") != EDITOR_ENDPOINT
        or server.get("publish_tool_exposed") is not False
        or server.get("delete_tool_exposed") is not False
        or server.get("media_write_tool_exposed") is not False
        or server.get("proposal_review_ttl_seconds")
        != EXPECTED_PROPOSAL_REVIEW_TTL_SECONDS
        or (
            require_measurement_ready
            and (
                type(measurement) is not dict
                or measurement.get("plugin_active") is not True
                or measurement.get("plugin_version") != "1.0.0"
                or measurement.get("collection_enabled") is not False
                or measurement.get("aggregate_ability_registered") is not True
                or measurement.get("raw_event_tool_exposed") is not False
            )
        )
        or (
            require_measurement_off
            and (
                type(measurement) is not dict
                or measurement.get("plugin_active") is not False
                or measurement.get("collection_enabled") is not False
                or measurement.get("raw_event_tool_exposed") is not False
            )
        )
    ):
        fail("RAOS_WORDPRESS_REQUEST_SITE_NOT_READY")


def precondition(document: Mapping[str, object]) -> dict[str, object]:
    revision = document.get("revision_id")
    modified = document.get("modified_gmt")
    content_hash = document.get("content_sha256")
    if (
        type(revision) is not int
        or revision < 1
        or type(modified) is not str
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", modified) is None
        or type(content_hash) is not str
        or SHA256_RE.fullmatch(content_hash) is None
    ):
        fail("RAOS_WORDPRESS_REQUEST_DOCUMENT_INVALID")
    return {
        "revision_id": revision,
        "modified_gmt": modified,
        "content_sha256": content_hash,
    }


def document_projection(document: Mapping[str, object]) -> dict[str, object]:
    if any(field not in document for field in WRITE_FIELDS):
        fail("RAOS_WORDPRESS_REQUEST_DOCUMENT_INVALID")
    return {field: document[field] for field in WRITE_FIELDS}


def list_all_documents(
    client: Any, *, post_types: Sequence[str] = ("post",)
) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    seen_ids: set[int] = set()
    if (
        not post_types
        or len(set(post_types)) != len(post_types)
        or any(value not in {"post", "page"} for value in post_types)
    ):
        fail("RAOS_WORDPRESS_REQUEST_CONTENT_LIST_INVALID")
    for post_type in post_types:
        expected_total: int | None = None
        type_count = 0
        page = 1
        while True:
            response = client.call(
                "raos-codex-content-list",
                {
                    "post_type": post_type,
                    "status": "any",
                    "page": page,
                    "per_page": LIST_PER_PAGE,
                },
            )
            total = response.get("total")
            batch = response.get("documents")
            if (
                response.get("schema") != "ContentDocumentListV1"
                or response.get("page") != page
                or response.get("per_page") != LIST_PER_PAGE
                or type(total) is not int
                or total < 0
                or total > MAX_LIST_DOCUMENTS
                or type(batch) is not list
                or len(batch) > LIST_PER_PAGE
                or (expected_total is not None and total != expected_total)
            ):
                fail("RAOS_WORDPRESS_REQUEST_CONTENT_LIST_INVALID")
            expected_total = total
            for raw_document in batch:
                if type(raw_document) is not dict:
                    fail("RAOS_WORDPRESS_REQUEST_CONTENT_LIST_INVALID")
                document = raw_document
                post_id = document.get("id")
                if (
                    type(post_id) is not int
                    or post_id < 1
                    or post_id in seen_ids
                    or document.get("post_type") != post_type
                ):
                    fail("RAOS_WORDPRESS_REQUEST_CONTENT_LIST_UNSTABLE")
                precondition(document)
                seen_ids.add(post_id)
                documents.append(document)
                type_count += 1
            if type_count >= total:
                break
            if not batch:
                fail("RAOS_WORDPRESS_REQUEST_CONTENT_LIST_UNSTABLE")
            page += 1
        if type_count != expected_total:
            fail("RAOS_WORDPRESS_REQUEST_CONTENT_LIST_UNSTABLE")
    return documents


def _ensure_private_directory() -> None:
    parent = PRIVATE_REQUEST_DIRECTORY.parent
    try:
        parent_metadata = parent.lstat()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_PRIVATE_DIRECTORY_UNAVAILABLE")
    if (
        parent.is_symlink()
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    ):
        fail("RAOS_WORDPRESS_REQUEST_PRIVATE_DIRECTORY_INSECURE")
    try:
        PRIVATE_REQUEST_DIRECTORY.mkdir(mode=0o700, exist_ok=True)
        metadata = PRIVATE_REQUEST_DIRECTORY.lstat()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_PRIVATE_DIRECTORY_UNAVAILABLE")
    if (
        PRIVATE_REQUEST_DIRECTORY.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        fail("RAOS_WORDPRESS_REQUEST_PRIVATE_DIRECTORY_INSECURE")


@contextmanager
def request_lock() -> Any:
    _ensure_private_directory()
    path = PRIVATE_REQUEST_DIRECTORY / "publication-request.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd_metadata = os.fstat(descriptor)
        path_metadata = path.lstat()
    except BlockingIOError:
        fail("RAOS_WORDPRESS_REQUEST_ALREADY_RUNNING")
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_LOCK_FAILED")
    if (
        not stat.S_ISREG(fd_metadata.st_mode)
        or fd_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(fd_metadata.st_mode) != 0o600
        or fd_metadata.st_nlink != 1
        or (fd_metadata.st_dev, fd_metadata.st_ino)
        != (path_metadata.st_dev, path_metadata.st_ino)
    ):
        os.close(descriptor)
        fail("RAOS_WORDPRESS_REQUEST_LOCK_INSECURE")
    try:
        yield descriptor
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _receipt_path(articles: Sequence[Article]) -> Path:
    identity = sha256_json(
        {
            "schema": "RAOS_WORDPRESS_PUBLICATION_SELECTION_V1",
            "slugs": sorted(article.production_slug for article in articles),
        }
    )
    return PRIVATE_REQUEST_DIRECTORY / f"request-{identity}.json"


def _read_receipt(path: Path) -> dict[str, object] | None:
    if not path.exists() and not path.is_symlink():
        return None
    try:
        metadata = path.lstat()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INSECURE")
    return load_json(path, MAX_RECEIPT_BYTES, "RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")


def validate_measurement_plugin_apply_receipt(path: Path | None) -> None:
    """Require the exact separate-admin plugin apply before an all-mode batch."""

    _ensure_private_directory()
    if path is None or not path.is_absolute():
        fail("RAOS_WORDPRESS_REQUEST_MEASUREMENT_PLUGIN_RECEIPT_REQUIRED")
    try:
        private_root = PRIVATE_REQUEST_DIRECTORY.resolve(strict=True)
        lexical = Path(os.path.abspath(path))
        resolved = path.resolve(strict=True)
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_MEASUREMENT_PLUGIN_RECEIPT_INVALID")
    if lexical != resolved or resolved.parent != private_root:
        fail("RAOS_WORDPRESS_REQUEST_MEASUREMENT_PLUGIN_RECEIPT_INVALID")
    proposal_receipt = _read_receipt(
        PRIVATE_REQUEST_DIRECTORY / "measurement-plugin-proposal-v3.json"
    )
    apply_receipt = _read_receipt(resolved)
    if type(proposal_receipt) is not dict or type(apply_receipt) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_MEASUREMENT_PLUGIN_RECEIPT_INVALID")
    manifest = load_json(
        MEASUREMENT_PLUGIN_MANIFEST_PATH,
        MAX_RECEIPT_BYTES,
        "RAOS_WORDPRESS_REQUEST_MEASUREMENT_PLUGIN_RECEIPT_INVALID",
    )
    registry = load_json(
        REPO_PLUGIN_ARTIFACTS_PATH,
        MAX_RECEIPT_BYTES,
        "RAOS_WORDPRESS_REQUEST_MEASUREMENT_PLUGIN_RECEIPT_INVALID",
    )
    manifest_files = manifest.get("plugin_files")
    artifacts = registry.get("artifacts")
    matching_artifacts = (
        [
            artifact
            for artifact in artifacts
            if type(artifact) is dict
            and artifact.get("artifact_id") == "raos-editorial-measurement-v1"
        ]
        if type(artifacts) is list
        else []
    )
    expected_file_manifest_sha256 = (
        hashlib.sha256(canonical_json_bytes(manifest_files)).hexdigest()
        if type(manifest_files) is list
        else None
    )
    proposal = proposal_receipt.get("proposal")
    if (
        manifest.get("schema") != "RAOS_EDITORIAL_MEASUREMENT_RUNTIME_MANIFEST_V1"
        or manifest.get("artifact_id") != "raos-editorial-measurement-v1"
        or manifest.get("plugin_slug") != "raos-editorial-measurement"
        or manifest.get("plugin_version") != "1.0.0"
        or manifest.get("default_enabled") is not False
        or manifest.get("host_gate") != "RAOS_MEASUREMENT_ENABLED"
        or type(manifest.get("package_sha256")) is not str
        or SHA256_RE.fullmatch(manifest["package_sha256"]) is None
        or expected_file_manifest_sha256 is None
        or len(matching_artifacts) != 1
        or matching_artifacts[0].get("slug") != manifest.get("plugin_slug")
        or matching_artifacts[0].get("version") != manifest.get("plugin_version")
        or matching_artifacts[0].get("package_sha256") != manifest.get("package_sha256")
        or proposal_receipt.get("schema")
        != "RAOS_MEASUREMENT_PLUGIN_PROPOSAL_RECEIPT_V3"
        or proposal_receipt.get("state") != "WAITING_FOR_SEPARATE_ADMIN_PLUGIN_APPROVAL"
        or proposal_receipt.get("artifact_id") != "raos-editorial-measurement-v1"
        or proposal_receipt.get("plugin_slug") != "raos-editorial-measurement"
        or proposal_receipt.get("plugin_version") != "1.0.0"
        or proposal_receipt.get("package_sha256") != manifest.get("package_sha256")
        or proposal_receipt.get("file_manifest_sha256") != expected_file_manifest_sha256
        or proposal_receipt.get("measurement_gate_default_off") is not True
        or type(proposal) is not dict
        or proposal.get("after_sha256") != expected_file_manifest_sha256
        or apply_receipt.get("schema") != "OperationReceiptV1"
        or apply_receipt.get("proposal_id") != proposal.get("proposal_id")
        or apply_receipt.get("operation_id") != proposal.get("operation_id")
        or apply_receipt.get("state") != "APPLIED"
        or apply_receipt.get("result_code") != "PLUGIN_CHANGE_APPLIED"
        or apply_receipt.get("after_sha256") != proposal.get("after_sha256")
    ):
        fail("RAOS_WORDPRESS_REQUEST_MEASUREMENT_PLUGIN_RECEIPT_INVALID")


def _atomic_receipt(path: Path, value: Mapping[str, object]) -> None:
    payload = canonical_json_bytes(dict(value)) + b"\n"
    if len(payload) > MAX_RECEIPT_BYTES:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_TOO_LARGE")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    descriptor = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written < 1:
                fail("RAOS_WORDPRESS_REQUEST_RECEIPT_WRITE_FAILED")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        directory_fd = os.open(PRIVATE_REQUEST_DIRECTORY, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_WRITE_FAILED")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_WRITE_FAILED")


def _fresh_receipt(
    articles: Sequence[Article],
    path: Path,
    desired_theme_tree_sha256: str | None = None,
    materialization_binding: Mapping[str, object] | None = None,
    quality_audit_binding: Mapping[str, object] | None = None,
) -> dict[str, object]:
    theme_tree = (
        tracked_theme_tree_sha256()
        if desired_theme_tree_sha256 is None
        else desired_theme_tree_sha256
    )
    if SHA256_RE.fullmatch(theme_tree) is None:
        fail("RAOS_WORDPRESS_REQUEST_THEME_SOURCE_INVALID")
    return {
        "schema": "RAOS_WORDPRESS_PUBLICATION_REQUEST_RECEIPT_V1",
        "receipt_path_sha256": hashlib.sha256(path.name.encode("ascii")).hexdigest(),
        "selected_slugs": sorted(article.production_slug for article in articles),
        "selected_documents": {
            article.production_slug: article.post_type for article in articles
        },
        "desired_sha256": {
            article.production_slug: article.desired_sha256() for article in articles
        },
        "desired_theme_tree_sha256": theme_tree,
        "desired_theme_runtime_revision": EXPECTED_THEME_RUNTIME_REVISION,
        "state": "LOCAL_VERIFIED",
        "attempt_id": None,
        "attempt_created_at_gmt": None,
        "materialization_binding": (
            dict(materialization_binding)
            if materialization_binding is not None
            else None
        ),
        "quality_audit_binding": (
            dict(quality_audit_binding) if quality_audit_binding is not None else None
        ),
        "baselines": {},
        "drafts": {},
        "proposal_keys": {},
        "proposals": [],
        "operation_ids": {},
        "batch_registration": None,
        "review_url": REVIEW_URL,
        "apply_receipt": None,
        "authenticated_readback": None,
        "prior_applied_reconciliation": None,
        "public_readback": None,
        "seo_audit_readback": None,
        "updated_at_gmt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _validate_materialization_binding(value: object) -> None:
    if value is None:
        return
    if type(value) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    schema = value.get("schema")
    expected_keys = {
        "schema",
        "portfolio_sha256",
        "evidence_status_sha256",
        "local_receipt_sha256",
        "production_receipt_sha256",
        "manufacturer_sales_state_sha256",
        "manufacturer_sales_state_checked_at_utc",
        "product_safety",
        "articles",
        "products",
        "media",
        "completion",
    }
    if schema in {
        "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V2",
        "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3",
    }:
        expected_keys.add("activation")
    if schema == STANDARD_API_BINDING_SCHEMA:
        expected_keys |= {
            "link_mode",
            "measurement_collection_enabled",
            "standard_api_receipt_sha256",
        }
        if (
            value.get("link_mode") != "standard-api"
            or value.get("measurement_collection_enabled") is not False
            or type(value.get("standard_api_receipt_sha256")) is not str
            or SHA256_RE.fullmatch(value["standard_api_receipt_sha256"]) is None
        ):
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    if set(value) != expected_keys:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    articles = value.get("articles")
    products = value.get("products")
    media = value.get("media")
    if (
        schema
        not in {
            "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V1",
            "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V2",
            "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3",
            STANDARD_API_BINDING_SCHEMA,
        }
        or type(value.get("portfolio_sha256")) is not str
        or SHA256_RE.fullmatch(value["portfolio_sha256"]) is None
        or any(
            type(value.get(name)) is not str or SHA256_RE.fullmatch(value[name]) is None
            for name in {
                "evidence_status_sha256",
                "local_receipt_sha256",
                "production_receipt_sha256",
            }
        )
        or type(value.get("manufacturer_sales_state_sha256")) is not str
        or SHA256_RE.fullmatch(value["manufacturer_sales_state_sha256"]) is None
        or type(value.get("manufacturer_sales_state_checked_at_utc")) is not str
        or TIMESTAMP_RE.fullmatch(value["manufacturer_sales_state_checked_at_utc"])
        is None
        or type(articles) is not dict
        or len(articles) != EXPECTED_ALL_ARTICLE_COUNT
        or type(products) is not dict
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    if any(
        type(slug) is not str
        or SLUG_RE.fullmatch(slug) is None
        or type(digest) is not str
        or SHA256_RE.fullmatch(digest) is None
        for slug, digest in articles.items()
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    try:
        _validate_product_safety_publication_binding(
            value.get("product_safety"),
            require_complete=True,
        )
    except RakutenMeasurementActivationV3Failure:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    for product_id, raw in products.items():
        if (
            type(product_id) is not str
            or not re.fullmatch(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*", product_id)
            or type(raw) is not dict
            or set(raw) != {"state", "provider_binding_sha256"}
            or raw.get("state") != "verified"
            or type(raw.get("provider_binding_sha256")) is not str
            or SHA256_RE.fullmatch(raw["provider_binding_sha256"]) is None
        ):
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    if set(products) != _owner_materialized_product_ids(
        code="RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID"
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    _validated_materialization_media(
        media,
        set(products),
        code="RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID",
    )
    _validated_materialization_completion(
        value.get("completion"),
        expected_product_count=len(products),
        code="RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID",
    )
    if schema in {
        "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V2",
        "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3",
    }:
        activation = value.get("activation")
        expected_activation_keys = {
            "dry_run_sha256",
            "v2_evidence_status_sha256",
            "v2_local_receipt_sha256",
            "v2_production_receipt_sha256",
            "admin_receipt_sha256",
            "money_link_mapping_sha256",
            "materialized_set_sha256",
            "local_article_set_sha256",
            "production_article_set_sha256",
            "local_overlay_receipt_sha256",
            "production_overlay_receipt_sha256",
            "mapping_generated_at_utc",
            "admin_verified_at_utc",
            "activated_at_utc",
            "article_count",
            "cta_count",
        }
        if schema == "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3":
            expected_activation_keys |= {
                "provider_slot_set_sha256",
                "provider_measurement_binding_sha256",
                "provider_slot_count",
                "provider_measurement_id_count",
                "internal_cta_identity_count",
                "live_link_count",
            }
        activation_times: list[datetime] = []
        if type(activation) is dict:
            for name in (
                "mapping_generated_at_utc",
                "admin_verified_at_utc",
                "activated_at_utc",
            ):
                raw_time = activation.get(name)
                if (
                    type(raw_time) is not str
                    or TIMESTAMP_RE.fullmatch(raw_time) is None
                ):
                    fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
                try:
                    activation_times.append(
                        datetime.strptime(raw_time, "%Y-%m-%dT%H:%M:%SZ").replace(
                            tzinfo=UTC
                        )
                    )
                except ValueError:
                    fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        if (
            type(activation) is not dict
            or set(activation) != expected_activation_keys
            or any(
                type(activation.get(name)) is not str
                or SHA256_RE.fullmatch(activation[name]) is None
                for name in expected_activation_keys
                if name.endswith("_sha256")
            )
            or activation.get("article_count") != EXPECTED_ALL_ARTICLE_COUNT
            or activation.get("cta_count") != EXPECTED_MATERIALIZED_AFFILIATE_CTA_COUNT
            or (
                schema == "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3"
                and (
                    activation.get("provider_slot_count") != 20
                    or activation.get("provider_measurement_id_count") != 20
                    or activation.get("internal_cta_identity_count")
                    != EXPECTED_MATERIALIZED_AFFILIATE_CTA_COUNT
                    or activation.get("live_link_count")
                    != EXPECTED_MATERIALIZED_AFFILIATE_CTA_COUNT
                )
            )
            or activation_times != sorted(activation_times)
        ):
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")


def _validate_baseline_record(
    value: object, slug: str, post_type: str | None = None
) -> dict[str, object]:
    old_fields = {
        "id",
        "slug",
        "status",
        "content_sha256",
        "revision_id",
        "modified_gmt",
    }
    if type(value) is not dict or set(value) not in {
        frozenset(old_fields),
        frozenset(old_fields | {"post_type"}),
    }:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    if (
        type(value.get("id")) is not int
        or value["id"] < 1
        or value.get("slug") != slug
        or (post_type is not None and value.get("post_type", "post") != post_type)
        or value.get("status") not in {"draft", "publish"}
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    precondition(value)
    return value


def _validate_prior_applied_reconciliation(
    value: object,
    selected_slugs: Sequence[str],
) -> None:
    if value is None:
        return
    if type(value) is not dict or set(value) != {
        "schema",
        "captured_at_gmt",
        "documents",
        "operations",
    }:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    documents = value.get("documents")
    operations = value.get("operations")
    if (
        value.get("schema") != "RAOS_WORDPRESS_PRIOR_APPLIED_RECONCILIATION_V1"
        or type(value.get("captured_at_gmt")) is not str
        or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
            value["captured_at_gmt"],
        )
        is None
        or type(documents) is not dict
        or set(documents) != set(selected_slugs)
        or type(operations) is not dict
        or not operations
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    for slug, document in documents.items():
        if (
            type(slug) is not str
            or type(document) is not dict
            or document.get("status") != "publish"
        ):
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        _validate_baseline_record(document, slug)
    for proposal_id, operation in operations.items():
        if (
            type(proposal_id) is not str
            or SHA256_RE.fullmatch(proposal_id) is None
            or type(operation) is not dict
            or operation.get("schema") != "OperationReceiptV1"
            or operation.get("proposal_id") != proposal_id
            or operation.get("state") != "APPLIED"
            or type(operation.get("operation_id")) is not str
            or SHA256_RE.fullmatch(operation["operation_id"]) is None
            or type(operation.get("after_sha256")) is not str
            or SHA256_RE.fullmatch(operation["after_sha256"]) is None
            or type(operation.get("audit_id")) is not str
            or SHA256_RE.fullmatch(operation["audit_id"]) is None
        ):
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")


def _validate_receipt(
    receipt: dict[str, object], articles: Sequence[Article]
) -> dict[str, object]:
    required = {
        "schema",
        "receipt_path_sha256",
        "selected_slugs",
        "desired_sha256",
        "desired_theme_tree_sha256",
        "state",
        "attempt_id",
        "attempt_created_at_gmt",
        "drafts",
        "proposal_keys",
        "proposals",
        "batch_registration",
        "review_url",
        "apply_receipt",
        "updated_at_gmt",
    }
    exact_object(
        receipt,
        required,
        {
            "authenticated_readback",
            "baselines",
            "desired_theme_runtime_revision",
            "materialization_binding",
            "operation_ids",
            "prior_applied_reconciliation",
            "public_readback",
            "quality_audit_binding",
            "seo_audit_readback",
            "selected_documents",
        },
    )
    receipt.setdefault("authenticated_readback", None)
    receipt.setdefault("baselines", {})
    receipt.setdefault(
        "desired_theme_runtime_revision",
        None,
    )
    receipt.setdefault("materialization_binding", None)
    receipt.setdefault("operation_ids", {})
    receipt.setdefault("prior_applied_reconciliation", None)
    receipt.setdefault("public_readback", None)
    receipt.setdefault("quality_audit_binding", None)
    receipt.setdefault("seo_audit_readback", None)
    selected = sorted(article.production_slug for article in articles)
    selected_documents = receipt.setdefault(
        "selected_documents",
        {article.production_slug: article.post_type for article in articles},
    )
    desired = receipt.get("desired_sha256")
    if (
        receipt["schema"] != "RAOS_WORDPRESS_PUBLICATION_REQUEST_RECEIPT_V1"
        or receipt["selected_slugs"] != selected
        or selected_documents
        != {article.production_slug: article.post_type for article in articles}
        or type(desired) is not dict
        or set(desired) != set(selected)
        or any(
            type(digest) is not str or SHA256_RE.fullmatch(digest) is None
            for digest in desired.values()
        )
        or type(receipt["desired_theme_tree_sha256"]) is not str
        or SHA256_RE.fullmatch(receipt["desired_theme_tree_sha256"]) is None
        or (
            receipt["desired_theme_runtime_revision"] is not None
            and (
                type(receipt["desired_theme_runtime_revision"]) is not str
                or SHA256_RE.fullmatch(receipt["desired_theme_runtime_revision"])
                is None
            )
        )
        or type(receipt["baselines"]) is not dict
        or type(receipt["drafts"]) is not dict
        or type(receipt["proposal_keys"]) is not dict
        or type(receipt["proposals"]) is not list
        or type(receipt["operation_ids"]) is not dict
        or (
            receipt["authenticated_readback"] is not None
            and type(receipt["authenticated_readback"]) is not dict
        )
        or (
            receipt["materialization_binding"] is not None
            and type(receipt["materialization_binding"]) is not dict
        )
        or (
            receipt["public_readback"] is not None
            and type(receipt["public_readback"]) is not dict
        )
        or (
            receipt["quality_audit_binding"] is not None
            and type(receipt["quality_audit_binding"]) is not dict
        )
        or (
            receipt["seo_audit_readback"] is not None
            and type(receipt["seo_audit_readback"]) is not dict
        )
        or (
            receipt["prior_applied_reconciliation"] is not None
            and type(receipt["prior_applied_reconciliation"]) is not dict
        )
        or receipt["review_url"] != REVIEW_URL
        or type(receipt["state"]) is not str
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    _validate_materialization_binding(receipt["materialization_binding"])
    _validate_quality_audit_binding(receipt["quality_audit_binding"])
    _validate_seo_audit_binding(receipt["seo_audit_readback"])
    _validate_prior_applied_reconciliation(
        receipt["prior_applied_reconciliation"],
        selected,
    )
    baselines = receipt["baselines"]
    if any(type(slug) is not str or slug not in selected for slug in baselines):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    for slug, baseline in baselines.items():
        _validate_baseline_record(baseline, slug, selected_documents[slug])
    operation_ids = receipt["operation_ids"]
    if not operation_ids and receipt["proposals"]:
        migrated: dict[str, str] = {}
        for proposal in receipt["proposals"]:
            proposal_id = (
                proposal.get("proposal_id") if type(proposal) is dict else None
            )
            if type(proposal_id) is not str or SHA256_RE.fullmatch(proposal_id) is None:
                fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
            migrated[proposal_id] = proposal_id
        receipt["operation_ids"] = migrated
        operation_ids = migrated
    if any(
        type(proposal_id) is not str
        or SHA256_RE.fullmatch(proposal_id) is None
        or type(operation_id) is not str
        or SHA256_RE.fullmatch(operation_id) is None
        for proposal_id, operation_id in operation_ids.items()
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    return receipt


def _touch_receipt(path: Path, receipt: dict[str, object], state: str) -> None:
    receipt["state"] = state
    receipt["updated_at_gmt"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    _atomic_receipt(path, receipt)


def _known_draft(
    receipt: Mapping[str, object], slug: str, document: Mapping[str, object]
) -> bool:
    drafts = receipt.get("drafts")
    known = drafts.get(slug) if type(drafts) is dict else None
    return (
        type(known) is dict
        and known.get("id") == document.get("id")
        and known.get("content_sha256") == document.get("content_sha256")
    )


def _baseline_record(document: Mapping[str, object]) -> dict[str, object]:
    post_id = document.get("id")
    slug = document.get("slug")
    status = document.get("status")
    condition = precondition(document)
    if (
        type(post_id) is not int
        or post_id < 1
        or type(slug) is not str
        or SLUG_RE.fullmatch(slug) is None
        or status not in {"draft", "publish"}
        or document.get("post_type") not in {"post", "page"}
    ):
        fail("RAOS_WORDPRESS_REQUEST_DOCUMENT_INVALID")
    result: dict[str, object] = {
        "id": post_id,
        "slug": slug,
        "status": status,
        **condition,
    }
    if document.get("post_type") == "page":
        result["post_type"] = "page"
    return result


def _known_baseline(
    receipt: Mapping[str, object], slug: str, document: Mapping[str, object]
) -> bool:
    baselines = receipt.get("baselines")
    baseline = baselines.get(slug) if type(baselines) is dict else None
    return type(baseline) is dict and baseline == _baseline_record(document)


def _known_applied_target(
    receipt: Mapping[str, object], slug: str, document: Mapping[str, object]
) -> bool:
    drafts = receipt.get("drafts")
    known = drafts.get(slug) if type(drafts) is dict else None
    if type(known) is not dict or known.get("id") != document.get("id"):
        return False
    proposals = receipt.get("proposals")
    return type(proposals) is list and any(
        type(proposal) is dict
        and proposal.get("kind") == "CONTENT_RELEASE"
        and proposal.get("slug") == slug
        and proposal.get("post_type", document.get("post_type", "post"))
        == document.get("post_type", "post")
        and proposal.get("after_sha256") == document.get("content_sha256")
        for proposal in proposals
    )


def _prior_applied_documents_for_fresh_capture(
    receipt: Mapping[str, object],
    selected: set[str],
) -> Mapping[str, object] | None:
    """Return the just-reconciled old attempt's exact document evidence.

    The evidence is pending only while the receipt still carries the same old
    content proposal set that produced its applied operation receipts. After a
    replacement attempt is created, the historical evidence remains in the
    receipt but must not become a permanent baseline for future releases.
    """

    reconciliation = receipt.get("prior_applied_reconciliation")
    if receipt.get("state") != "APPLIED" or reconciliation is None:
        return None
    if type(reconciliation) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    documents = reconciliation.get("documents")
    operations = reconciliation.get("operations")
    proposals = receipt.get("proposals")
    if (
        type(documents) is not dict
        or type(operations) is not dict
        or type(proposals) is not list
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    proposal_ids: set[str] = set()
    for proposal in proposals:
        if type(proposal) is not dict:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        if proposal.get("kind") != "CONTENT_RELEASE":
            continue
        proposal_id = proposal.get("proposal_id")
        if type(proposal_id) is not str or SHA256_RE.fullmatch(proposal_id) is None:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        proposal_ids.add(proposal_id)
    if set(operations) != proposal_ids:
        return None
    expected_document_count = EXPECTED_ALL_ARTICLE_COUNT + EXPECTED_POLICY_PAGE_COUNT
    if (
        len(selected) != expected_document_count
        or len(proposal_ids) != expected_document_count
        or set(documents) != selected
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    return documents


def capture_existing_baselines(
    client: Any,
    articles: Sequence[Article],
    documents: Sequence[Mapping[str, object]],
    receipt: dict[str, object],
    path: Path,
    *,
    require_existing_published: bool = False,
) -> list[dict[str, object]]:
    """Read every existing selected target and bind its exact CAS baseline."""

    selected = {article.production_slug for article in articles}
    prior_applied_documents = _prior_applied_documents_for_fresh_capture(
        receipt,
        selected,
    )
    listed: dict[str, list[Mapping[str, object]]] = {}
    for document in documents:
        slug = document.get("slug")
        if type(slug) is str and slug in selected:
            listed.setdefault(slug, []).append(document)
    baselines = receipt.get("baselines")
    if type(baselines) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    authoritative: list[dict[str, object]] = []
    changed = False
    rebase_applied = receipt.get("state") == "APPLIED_ATTEMPT_REPLACED"
    for article in articles:
        slug = article.production_slug
        candidates = listed.get(slug, [])
        create_if_missing = (
            article.post_type == "page" and slug in CREATE_IF_MISSING_POLICY_PAGE_SLUGS
        )
        if len(candidates) > 1:
            fail("RAOS_WORDPRESS_REQUEST_SLUG_CONFLICT")
        prior = baselines.get(slug)
        if not candidates:
            if (
                prior is not None
                or prior_applied_documents is not None
                or (require_existing_published and not create_if_missing)
            ):
                fail("RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT")
            continue
        listed_document = candidates[0]
        known_created_draft = create_if_missing and _known_draft(
            receipt, slug, listed_document
        )
        if (
            require_existing_published
            and listed_document.get("status") != "publish"
            and not known_created_draft
        ):
            fail("RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT")
        if listed_document.get("post_type") != article.post_type:
            fail("RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT")
        post_id = listed_document.get("id")
        if type(post_id) is not int or post_id < 1:
            fail("RAOS_WORDPRESS_REQUEST_CONTENT_LIST_INVALID")
        readback = client.call("raos-codex-content-get", {"id": post_id})
        listed_baseline = _baseline_record(listed_document)
        current_baseline = _baseline_record(readback)
        if listed_baseline != current_baseline:
            fail("RAOS_WORDPRESS_REQUEST_BASELINE_CHANGED_DURING_READ")
        if current_baseline["slug"] != slug:
            fail("RAOS_WORDPRESS_REQUEST_BASELINE_CHANGED_DURING_READ")
        if (
            prior_applied_documents is not None
            and prior_applied_documents.get(slug) != current_baseline
        ):
            # This comparison intentionally precedes both known-target
            # exceptions below. A same-content save still changes the exact CAS
            # precondition and is an unknown production write.
            fail("RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT")
        if prior is None:
            proposals = receipt.get("proposals")
            if (
                type(proposals) is list
                and proposals
                and not _known_draft(receipt, slug, readback)
                and not _known_applied_target(receipt, slug, readback)
            ):
                fail("RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT")
            baselines[slug] = current_baseline
            changed = True
        else:
            _validate_baseline_record(prior, slug, article.post_type)
            if prior != current_baseline:
                if rebase_applied and _known_draft(receipt, slug, readback):
                    baselines[slug] = current_baseline
                    changed = True
                elif not _known_draft(
                    receipt, slug, readback
                ) and not _known_applied_target(receipt, slug, readback):
                    fail("RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT")
        authoritative.append(readback)
    if changed:
        receipt["updated_at_gmt"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        _atomic_receipt(path, receipt)
    return authoritative


def reconcile_drafts(
    client: Any,
    articles: Sequence[Article],
    documents: Sequence[Mapping[str, object]],
    receipt: dict[str, object],
    path: Path,
) -> dict[str, dict[str, object]]:
    by_slug: dict[str, list[Mapping[str, object]]] = {}
    selected = {article.production_slug for article in articles}
    for document in documents:
        slug = document.get("slug")
        if type(slug) is str and slug in selected:
            by_slug.setdefault(slug, []).append(document)
    result: dict[str, dict[str, object]] = {}
    receipt_drafts = receipt["drafts"]
    if type(receipt_drafts) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    replacing_published_targets = receipt.get("state") in {
        "APPLIED_ATTEMPT_REPLACED",
        "EXPIRED_ATTEMPT_REPLACED",
    }
    for article in articles:
        candidates = by_slug.get(article.production_slug, [])
        if len(candidates) > 1:
            fail("RAOS_WORDPRESS_REQUEST_SLUG_CONFLICT")
        desired = article.document()
        published_target = False
        if not candidates:
            document = client.call("raos-codex-content-create-draft", desired)
        else:
            current = candidates[0]
            if current.get("status") == "publish":
                if not (
                    _known_baseline(receipt, article.production_slug, current)
                    or _known_applied_target(receipt, article.production_slug, current)
                    or (
                        replacing_published_targets
                        and _known_draft(receipt, article.production_slug, current)
                    )
                ):
                    fail("RAOS_WORDPRESS_REQUEST_PUBLISHED_CONFLICT")
                # Build the next immutable release proposal directly from the
                # exact prior applied target. Never unpublish it into a draft.
                document = dict(current)
                published_target = True
            elif current.get("status") != "draft":
                fail("RAOS_WORDPRESS_REQUEST_DRAFT_TARGET_INVALID")
            elif document_projection(current) == desired:
                document = dict(current)
            elif _known_draft(
                receipt, article.production_slug, current
            ) or _known_baseline(receipt, article.production_slug, current):
                document = client.call(
                    "raos-codex-content-update-draft",
                    {
                        "id": current["id"],
                        "mode": "replace",
                        "precondition": precondition(current),
                        "changes": desired,
                    },
                )
            else:
                fail("RAOS_WORDPRESS_REQUEST_UNKNOWN_DRAFT_DRIFT")
        if type(document.get("id")) is not int or (
            not published_target
            and (
                document.get("status") != "draft"
                or document_projection(document) != desired
            )
        ):
            fail("RAOS_WORDPRESS_REQUEST_DRAFT_WRITE_INVALID")
        readback = client.call("raos-codex-content-get", {"id": document["id"]})
        if (
            readback.get("content_sha256") != document.get("content_sha256")
            or (published_target and readback.get("status") != "publish")
            or (
                published_target
                and _baseline_record(readback) != _baseline_record(document)
            )
            or (
                not published_target
                and (
                    readback.get("status") != "draft"
                    or document_projection(readback) != desired
                )
            )
        ):
            fail("RAOS_WORDPRESS_REQUEST_DRAFT_READBACK_FAILED")
        precondition(readback)
        result[article.production_slug] = readback
        receipt_drafts[article.production_slug] = {
            "id": readback["id"],
            "content_sha256": readback["content_sha256"],
        }
        _touch_receipt(path, receipt, "DRAFTS_IN_PROGRESS")
    _touch_receipt(path, receipt, "DRAFTS_READY")
    return result


def _validate_deployment_tools(tools: object) -> None:
    if type(tools) is not list:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_TOOL_CONTRACT_INVALID")
    by_name: dict[str, dict[str, object]] = {}
    for tool in tools:
        if type(tool) is not dict or type(tool.get("name")) is not str:
            fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_TOOL_CONTRACT_INVALID")
        by_name[tool["name"]] = tool
    if set(by_name) != EXPECTED_DEPLOYMENT_TOOLS:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_TOOL_CONTRACT_INVALID")
    for name, tool in by_name.items():
        annotations = tool.get("annotations")
        read_only = name in {"deployment-status", "publication-batch-status"}
        destructive = name in {
            "release-wait-and-apply",
            "plugin-apply-change",
            "operation-recover",
        }
        idempotent = name not in {"theme-propose-release", "plugin-propose-change"}
        open_world = name == "plugin-propose-change"
        if (
            type(annotations) is not dict
            or annotations.get("readOnlyHint") is not read_only
            or annotations.get("destructiveHint") is not destructive
            or annotations.get("idempotentHint") is not idempotent
            or annotations.get("openWorldHint") is not open_world
        ):
            fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_TOOL_CONTRACT_INVALID")
    status_schema = by_name["deployment-status"].get("inputSchema")
    theme_schema = by_name["theme-propose-release"].get("inputSchema")
    wait_schema = by_name["release-wait-and-apply"].get("inputSchema")
    batch_status_schema = by_name["publication-batch-status"].get("inputSchema")
    theme_properties = (
        theme_schema.get("properties") if type(theme_schema) is dict else None
    )
    theme_key = (
        theme_properties.get("idempotency_key")
        if type(theme_properties) is dict
        else None
    )
    wait_properties = (
        wait_schema.get("properties") if type(wait_schema) is dict else None
    )
    wait_ids = (
        wait_properties.get("proposal_ids") if type(wait_properties) is dict else None
    )
    wait_batch_token = (
        wait_properties.get("batch_token") if type(wait_properties) is dict else None
    )
    wait_manifest_hash = (
        wait_properties.get("batch_manifest_sha256")
        if type(wait_properties) is dict
        else None
    )
    wait_items = wait_ids.get("items") if type(wait_ids) is dict else None
    wait_evidence_expiry = (
        wait_properties.get("evidence_expires_at_gmt")
        if type(wait_properties) is dict
        else None
    )
    batch_status_properties = (
        batch_status_schema.get("properties")
        if type(batch_status_schema) is dict
        else None
    )
    if (
        type(status_schema) is not dict
        or status_schema.get("type") != "object"
        or status_schema.get("properties") != {}
        or type(theme_schema) is not dict
        or theme_schema.get("type") != "object"
        or type(theme_key) is not dict
        or theme_key.get("type") != "string"
        or theme_key.get("pattern") != "^[0-9a-f]{64}$"
        or type(wait_schema) is not dict
        or type(wait_ids) is not dict
        or wait_schema.get("type") != "object"
        or wait_schema.get("additionalProperties") is not False
        or wait_schema.get("required")
        != ["batch_token", "batch_manifest_sha256", "proposal_ids"]
        or type(wait_batch_token) is not dict
        or wait_batch_token.get("type") != "string"
        or wait_batch_token.get("pattern") != "^[0-9a-f]{64}$"
        or type(wait_manifest_hash) is not dict
        or wait_manifest_hash.get("type") != "string"
        or wait_manifest_hash.get("pattern") != "^[0-9a-f]{64}$"
        or wait_ids.get("type") != "array"
        or wait_ids.get("minItems") != 1
        or wait_ids.get("maxItems") != 20
        or type(wait_items) is not dict
        or wait_items.get("type") != "string"
        or wait_items.get("pattern") != "^[0-9a-f]{64}$"
        or type(batch_status_schema) is not dict
        or batch_status_schema.get("type") != "object"
        or batch_status_schema.get("additionalProperties") is not False
        or batch_status_schema.get("required")
        != ["batch_token", "batch_manifest_sha256", "proposal_ids"]
        or type(wait_properties) is not dict
        or set(wait_properties)
        - {
            "batch_token",
            "batch_manifest_sha256",
            "proposal_ids",
            "evidence_expires_at_gmt",
        }
        or (
            "evidence_expires_at_gmt" in wait_properties
            and wait_evidence_expiry
            != {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"}
        )
        or batch_status_properties
        != {
            key: value
            for key, value in wait_properties.items()
            if key != "evidence_expires_at_gmt"
        }
    ):
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_TOOL_CONTRACT_INVALID")


def _deployment_mcp_call(
    command: str,
    value: Mapping[str, object],
    *,
    timeout: int,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, object]:
    if command not in {
        "deployment-status",
        "publication-batch-status",
        "theme-propose-release",
        "plugin-propose-change",
        "release-wait-and-apply",
    }:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_COMMAND_INVALID")
    messages = (
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "raos-wordpress-publication-request",
                    "version": "1.0.0",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": command, "arguments": dict(value)},
        },
    )
    stdin = b"".join(canonical_json_bytes(message) + b"\n" for message in messages)
    try:
        completed = runner(
            (
                NODE_BIN.as_posix(),
                "--experimental-strip-types",
                DEPLOYMENT_BRIDGE.as_posix(),
            ),
            cwd=ROOT,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "TZ": "UTC",
            },
        )
    except subprocess.TimeoutExpired:
        fail("RAOS_WORDPRESS_REQUEST_APPROVAL_TIMEOUT")
    except OSError, subprocess.SubprocessError:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_UNAVAILABLE")
    if len(completed.stdout) > MAX_RECEIPT_BYTES or len(completed.stderr) > 4096:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_OUTPUT_INVALID")
    if completed.returncode != 0:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_FAILED")
    responses: dict[int, dict[str, object]] = {}
    try:
        for line in completed.stdout.splitlines():
            if not line:
                continue
            response = json.loads(line.decode("utf-8", errors="strict"))
            if (
                type(response) is not dict
                or response.get("jsonrpc") != "2.0"
                or type(response.get("id")) is not int
                or response["id"] in responses
            ):
                fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_OUTPUT_INVALID")
            responses[response["id"]] = response
    except UnicodeError, json.JSONDecodeError:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_OUTPUT_INVALID")
    if set(responses) != {1, 2, 3} or any(
        "error" in responses[response_id] for response_id in responses
    ):
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_OUTPUT_INVALID")
    initialized = responses[1].get("result")
    initialized_server = (
        initialized.get("serverInfo") if type(initialized) is dict else None
    )
    listed = responses[2].get("result")
    if (
        type(initialized) is not dict
        or initialized.get("protocolVersion") != PROTOCOL_VERSION
        or type(initialized_server) is not dict
        or initialized_server.get("name") != "raos-wordpress-bridge"
        or initialized_server.get("version") != "1.1.0"
        or type(listed) is not dict
    ):
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_OUTPUT_INVALID")
    _validate_deployment_tools(listed.get("tools"))
    call_result = responses[3].get("result")
    structured = (
        call_result.get("structuredContent") if type(call_result) is dict else None
    )
    if type(call_result) is not dict or type(structured) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_OUTPUT_INVALID")
    if call_result.get("isError") is True:
        code = structured.get("code")
        if type(code) is str and re.fullmatch(r"[A-Z0-9_]{3,96}", code):
            fail(code)
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_MCP_TOOL_FAILED")
    return structured


def _proposal_record(
    *,
    kind: str,
    slug: str | None,
    key: str,
    response: Mapping[str, object],
    expected_after: str | None = None,
    post_type: str | None = None,
) -> dict[str, object]:
    payload: object = response
    if kind == "THEME_RELEASE":
        payload = response.get("proposal")
    if type(payload) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_PROPOSAL_INVALID")
    proposal_id = payload.get("proposal_id")
    after_sha256 = payload.get(
        "after_sha256" if kind == "CONTENT_RELEASE" else "after_tree_sha256"
    )
    expires = payload.get("expires_at_gmt")
    if (
        type(proposal_id) is not str
        or SHA256_RE.fullmatch(proposal_id) is None
        or type(after_sha256) is not str
        or SHA256_RE.fullmatch(after_sha256) is None
        or (expected_after is not None and after_sha256 != expected_after)
        or type(expires) is not str
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", expires) is None
    ):
        fail("RAOS_WORDPRESS_REQUEST_PROPOSAL_INVALID")
    result: dict[str, object] = {
        "kind": kind,
        "slug": slug,
        "proposal_id": proposal_id,
        "after_sha256": after_sha256,
        "expires_at_gmt": expires,
        "idempotency_key": key,
    }
    if kind == "CONTENT_RELEASE":
        if post_type not in {"post", "page"}:
            fail("RAOS_WORDPRESS_REQUEST_PROPOSAL_INVALID")
        result["post_type"] = post_type
    return result


def deployment_status(
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, object]:
    response = _deployment_mcp_call("deployment-status", {}, timeout=120, runner=runner)
    theme = response.get("theme")
    gates = response.get("gates")
    authorization = response.get("apply_authorization")
    if (
        response.get("schema") != "RAOSWordPressDeploymentStatusV1"
        or response.get("origin") != ORIGIN
        or response.get("plugin_runtime_revision") != EXPECTED_PLUGIN_RUNTIME_REVISION
        or response.get("private_directory_ready") is not True
        or type(theme) is not dict
        or theme.get("slug") != "kurashinoshirube-child"
        or theme.get("active") is not True
        or type(theme.get("version")) is not str
        or VERSION_RE.fullmatch(theme["version"]) is None
        or type(theme.get("runtime_version")) is not str
        or VERSION_RE.fullmatch(theme["runtime_version"]) is None
        or "runtime_revision" not in theme
        or (
            theme.get("runtime_revision") is not None
            and (
                type(theme.get("runtime_revision")) is not str
                or SHA256_RE.fullmatch(theme["runtime_revision"]) is None
            )
        )
        or type(theme.get("tree_sha256")) is not str
        or SHA256_RE.fullmatch(theme["tree_sha256"]) is None
        or type(gates) is not dict
        or any(
            gates.get(name) is not True
            for name in ("global", "content_apply", "theme_apply")
        )
        or authorization
        != {
            "mode": "approval_scoped_lease",
            "default": False,
            "single_use": True,
            "lease_ttl_seconds": EXPECTED_APPLY_LEASE_TTL_SECONDS,
        }
    ):
        fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_STATUS_INVALID")
    return response


def _content_after_sha256(document: Mapping[str, object], post_id: int) -> str:
    material = {
        "schema": "ContentDocumentV1",
        "post_type": document["post_type"],
        "id": post_id,
        "status": "publish",
        "title": document["title"],
        "slug": document["slug"],
        "excerpt": document["excerpt"],
        "block_markup": document["block_markup"],
        "taxonomies": document["taxonomies"],
        "media_ids": document["media_ids"],
    }
    return sha256_json(material)


def _attempt_expired(receipt: Mapping[str, object]) -> bool:
    proposals = receipt.get("proposals")
    if type(proposals) is not list or not proposals:
        created = receipt.get("attempt_created_at_gmt")
        if type(created) is not str:
            return False
        try:
            created_at = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC
            )
        except ValueError:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        return datetime.now(UTC) >= created_at + timedelta(
            seconds=ATTEMPT_PREPARED_EXPIRY_SECONDS
        )
    expirations: list[datetime] = []
    for proposal in proposals:
        if (
            type(proposal) is not dict
            or type(proposal.get("expires_at_gmt")) is not str
        ):
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        try:
            expirations.append(
                datetime.strptime(
                    proposal["expires_at_gmt"], "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=UTC)
            )
        except ValueError:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    return datetime.now(UTC) >= min(expirations)


def _prepare_attempt(
    receipt: dict[str, object],
    articles: Sequence[Article],
    drafts: Mapping[str, Mapping[str, object]],
    include_theme: bool,
    path: Path,
) -> None:
    attempt = receipt.get("attempt_id")
    if type(attempt) is not str or SHA256_RE.fullmatch(attempt) is None:
        attempt = secrets.token_hex(32)
        receipt["attempt_id"] = attempt
        receipt["attempt_created_at_gmt"] = datetime.now(UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        receipt["proposals"] = []
        receipt["operation_ids"] = {}
        receipt["batch_registration"] = None
        receipt["apply_receipt"] = None
        receipt["authenticated_readback"] = None
        receipt["public_readback"] = None
        receipt["seo_audit_readback"] = None
        receipt["proposal_keys"] = {}
    keys = receipt["proposal_keys"]
    if type(keys) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    if include_theme:
        desired_tree = receipt.get("desired_theme_tree_sha256")
        if type(desired_tree) is not str or SHA256_RE.fullmatch(desired_tree) is None:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        keys.setdefault(
            "theme",
            sha256_json(
                {
                    "schema": "RAOS_WORDPRESS_THEME_PROPOSAL_KEY_V1",
                    "attempt_id": attempt,
                    "theme_version": theme_version(),
                    "theme_runtime_revision": theme_runtime_revision(),
                    "theme_tree_sha256": desired_tree,
                }
            ),
        )
    for article in articles:
        draft = drafts[article.production_slug]
        keys.setdefault(
            f"content:{article.production_slug}",
            sha256_json(
                {
                    "schema": "RAOS_WORDPRESS_CONTENT_PROPOSAL_KEY_V1",
                    "attempt_id": attempt,
                    "id": draft["id"],
                    "precondition": precondition(draft),
                    "document": article.document(),
                }
            ),
        )
    _touch_receipt(path, receipt, "ATTEMPT_PREPARED")


def create_proposals(
    client: Any,
    articles: Sequence[Article],
    drafts: Mapping[str, Mapping[str, object]],
    include_theme: bool,
    receipt: dict[str, object],
    path: Path,
    deployment_runner: Callable[
        ..., subprocess.CompletedProcess[bytes]
    ] = subprocess.run,
) -> list[dict[str, object]]:
    _prepare_attempt(receipt, articles, drafts, include_theme, path)
    keys = receipt["proposal_keys"]
    if type(keys) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    existing = receipt["proposals"]
    if type(existing) is not list:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    by_identity: dict[str, dict[str, object]] = {}
    for proposal in existing:
        if type(proposal) is not dict:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        identity = (
            "theme"
            if proposal.get("kind") == "THEME_RELEASE"
            else f"content:{proposal.get('slug')}"
        )
        by_identity[identity] = proposal

    if include_theme and "theme" not in by_identity:
        key = keys.get("theme")
        desired_tree = receipt.get("desired_theme_tree_sha256")
        if type(key) is not str or SHA256_RE.fullmatch(key) is None:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        if type(desired_tree) is not str or SHA256_RE.fullmatch(desired_tree) is None:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        response = _deployment_mcp_call(
            "theme-propose-release",
            {"idempotency_key": key},
            timeout=120,
            runner=deployment_runner,
        )
        proposal = _proposal_record(
            kind="THEME_RELEASE",
            slug=None,
            key=key,
            response=response,
            expected_after=desired_tree,
        )
        existing.append(proposal)
        by_identity["theme"] = proposal
        _touch_receipt(path, receipt, "PROPOSALS_IN_PROGRESS")

    for article in articles:
        identity = f"content:{article.production_slug}"
        if identity in by_identity:
            continue
        key = keys.get(identity)
        if type(key) is not str or SHA256_RE.fullmatch(key) is None:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        draft = drafts[article.production_slug]
        draft_id = draft.get("id")
        if type(draft_id) is not int or draft_id < 1:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        expected_after = _content_after_sha256(article.document(), draft_id)
        response = client.call(
            "raos-codex-content-propose-release",
            {
                "id": draft_id,
                "precondition": precondition(draft),
                "document": article.document(),
                "idempotency_key": key,
            },
        )
        proposal = _proposal_record(
            kind="CONTENT_RELEASE",
            slug=article.production_slug,
            key=key,
            response=response,
            expected_after=expected_after,
            post_type=article.post_type,
        )
        existing.append(proposal)
        by_identity[identity] = proposal
        _touch_receipt(path, receipt, "PROPOSALS_IN_PROGRESS")

    ordered: list[dict[str, object]] = []
    if include_theme:
        ordered.append(by_identity["theme"])
    ordered.extend(
        by_identity[f"content:{article.production_slug}"] for article in articles
    )
    receipt["proposals"] = ordered
    receipt["operation_ids"] = {
        proposal["proposal_id"]: proposal["proposal_id"] for proposal in ordered
    }
    _touch_receipt(path, receipt, "PROPOSALS_READY")
    return ordered


def _proposal_ids(receipt: Mapping[str, object]) -> list[str]:
    proposals = receipt.get("proposals")
    selected_slugs = receipt.get("selected_slugs")
    selected_documents = receipt.get("selected_documents")
    desired_tree = receipt.get("desired_theme_tree_sha256")
    if (
        type(proposals) is not list
        or not 1 <= len(proposals) <= MAX_PUBLICATION_PROPOSALS
        or type(selected_slugs) is not list
        or any(type(slug) is not str for slug in selected_slugs)
        or type(selected_documents) is not dict
        or type(desired_tree) is not str
        or SHA256_RE.fullmatch(desired_tree) is None
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    result: list[str] = []
    content_slugs: list[str] = []
    theme_count = 0
    old_fields = {
        "kind",
        "slug",
        "proposal_id",
        "after_sha256",
        "expires_at_gmt",
        "idempotency_key",
    }
    for proposal in proposals:
        if type(proposal) is not dict or set(proposal) not in {
            frozenset(old_fields),
            frozenset(old_fields | {"post_type"}),
        }:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        kind = proposal.get("kind")
        slug = proposal.get("slug")
        proposal_id = proposal.get("proposal_id")
        after_sha256 = proposal.get("after_sha256")
        key = proposal.get("idempotency_key")
        expires = proposal.get("expires_at_gmt")
        if (
            kind not in {"CONTENT_RELEASE", "THEME_RELEASE"}
            or type(proposal_id) is not str
            or SHA256_RE.fullmatch(proposal_id) is None
            or proposal_id in result
            or type(after_sha256) is not str
            or SHA256_RE.fullmatch(after_sha256) is None
            or type(key) is not str
            or SHA256_RE.fullmatch(key) is None
            or type(expires) is not str
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", expires) is None
        ):
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        if kind == "THEME_RELEASE":
            theme_count += 1
            if slug is not None or after_sha256 != desired_tree:
                fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        else:
            if type(slug) is not str or SLUG_RE.fullmatch(slug) is None:
                fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
            if proposal.get("post_type", "post") != selected_documents.get(slug):
                fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
            content_slugs.append(slug)
        result.append(proposal_id)
    if (
        theme_count > 1
        or len(content_slugs) != len(set(content_slugs))
        or sorted(content_slugs) != selected_slugs
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    return result


def _operation_ids(receipt: Mapping[str, object]) -> dict[str, str]:
    proposal_ids = _proposal_ids(receipt)
    raw = receipt.get("operation_ids")
    if (
        type(raw) is not dict
        or set(raw) != set(proposal_ids)
        or any(
            type(operation_id) is not str
            or SHA256_RE.fullmatch(operation_id) is None
            or operation_id != proposal_id
            for proposal_id, operation_id in raw.items()
        )
    ):
        fail("RAOS_WORDPRESS_REQUEST_OPERATION_ID_INVALID")
    return dict(raw)


def read_content_operations(
    client: Any,
    receipt: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    """Resume content members by their durable operation IDs, never by UI state."""

    operations = _operation_ids(receipt)
    proposals = receipt.get("proposals")
    if type(proposals) is not list:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    result: dict[str, dict[str, object]] = {}
    for proposal in proposals:
        if type(proposal) is not dict or proposal.get("kind") != "CONTENT_RELEASE":
            continue
        proposal_id = proposal.get("proposal_id")
        if type(proposal_id) is not str or proposal_id not in operations:
            fail("RAOS_WORDPRESS_REQUEST_OPERATION_ID_INVALID")
        operation_id = operations[proposal_id]
        operation = client.call(
            "raos-codex-operation-get",
            {"operation_id": operation_id},
        )
        if (
            operation.get("schema") != "OperationReceiptV1"
            or operation.get("proposal_id") != proposal_id
            or operation.get("operation_id") != operation_id
            or operation.get("state")
            not in {
                "PENDING",
                "MANUAL_REQUIRED",
                "APPROVED",
                "APPLYING",
                "APPLIED",
                "FAILED",
                "EXPIRED",
            }
            or type(operation.get("result_code")) is not str
            or re.fullmatch(r"[A-Z0-9_]{3,96}", operation["result_code"]) is None
            or (
                operation.get("before_sha256") is not None
                and (
                    type(operation.get("before_sha256")) is not str
                    or SHA256_RE.fullmatch(operation["before_sha256"]) is None
                )
            )
            or operation.get("after_sha256") != proposal.get("after_sha256")
            or type(operation.get("audit_id")) is not str
            or SHA256_RE.fullmatch(operation["audit_id"]) is None
        ):
            fail("RAOS_WORDPRESS_REQUEST_OPERATION_READBACK_INVALID")
        result[proposal_id] = operation
    return result


def register_publication_batch(
    client: Any,
    receipt: dict[str, object],
    path: Path,
) -> dict[str, object]:
    proposal_ids = sorted(_proposal_ids(receipt))
    expected_theme_tree_sha256 = receipt.get("desired_theme_tree_sha256")
    if (
        type(expected_theme_tree_sha256) is not str
        or SHA256_RE.fullmatch(expected_theme_tree_sha256) is None
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    response = client.call(
        "raos-codex-publication-batch-register",
        {
            "proposal_ids": proposal_ids,
            "expected_theme_tree_sha256": expected_theme_tree_sha256,
        },
    )
    if type(response) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_BATCH_REGISTRATION_INVALID")
    batch_token = response.get("batch_token")
    manifest_hash = response.get("batch_manifest_sha256")
    expires = response.get("expires_at_gmt")
    if (
        response.get("schema") != "RAOSWordPressPublicationBatchV1"
        or type(batch_token) is not str
        or SHA256_RE.fullmatch(batch_token) is None
        or type(manifest_hash) is not str
        or SHA256_RE.fullmatch(manifest_hash) is None
        or response.get("expected_theme_tree_sha256") != expected_theme_tree_sha256
        or response.get("proposal_count") != len(proposal_ids)
        or response.get("proposal_ids") != proposal_ids
        or response.get("state") not in {"REGISTERED", "APPROVED", "EXPIRED"}
        or type(expires) is not str
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", expires) is None
        or response.get("review_url") != REVIEW_URL
    ):
        fail("RAOS_WORDPRESS_REQUEST_BATCH_REGISTRATION_INVALID")
    receipt["batch_registration"] = response
    _touch_receipt(path, receipt, "BATCH_REGISTERED")
    return dict(response)


def _registered_proposal_ids(receipt: Mapping[str, object]) -> list[str]:
    registration = receipt.get("batch_registration")
    proposal_ids = (
        registration.get("proposal_ids") if type(registration) is dict else None
    )
    if (
        type(registration) is not dict
        or registration.get("schema") != "RAOSWordPressPublicationBatchV1"
        or type(registration.get("batch_token")) is not str
        or SHA256_RE.fullmatch(registration["batch_token"]) is None
        or type(registration.get("batch_manifest_sha256")) is not str
        or SHA256_RE.fullmatch(registration["batch_manifest_sha256"]) is None
        or registration.get("expected_theme_tree_sha256")
        != receipt.get("desired_theme_tree_sha256")
        or type(proposal_ids) is not list
        or proposal_ids != sorted(proposal_ids)
        or len(proposal_ids) != len(set(proposal_ids))
        or any(
            type(value) is not str or SHA256_RE.fullmatch(value) is None
            for value in proposal_ids
        )
        or proposal_ids != sorted(_proposal_ids(receipt))
        or registration.get("proposal_count") != len(proposal_ids)
        or registration.get("state") not in {"REGISTERED", "APPROVED", "EXPIRED"}
        or type(registration.get("expires_at_gmt")) is not str
        or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
            registration["expires_at_gmt"],
        )
        is None
        or registration.get("review_url") != REVIEW_URL
    ):
        fail("RAOS_WORDPRESS_REQUEST_BATCH_REGISTRATION_INVALID")
    return proposal_ids


def publication_batch_status(
    receipt: Mapping[str, object],
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, object]:
    proposal_ids = _registered_proposal_ids(receipt)
    registration = receipt.get("batch_registration")
    if type(registration) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_BATCH_REGISTRATION_INVALID")
    batch_token = registration.get("batch_token")
    manifest_hash = registration.get("batch_manifest_sha256")
    if type(batch_token) is not str or type(manifest_hash) is not str:
        fail("RAOS_WORDPRESS_REQUEST_BATCH_REGISTRATION_INVALID")
    response = _deployment_mcp_call(
        "publication-batch-status",
        {
            "batch_token": batch_token,
            "batch_manifest_sha256": manifest_hash,
            "proposal_ids": proposal_ids,
        },
        timeout=120,
        runner=runner,
    )
    expires_at_gmt = response.get("expires_at_gmt")
    if (
        set(response)
        != {
            "schema",
            "batch_token",
            "batch_manifest_sha256",
            "proposal_count",
            "proposal_ids",
            "state",
            "expires_at_gmt",
            "preconditions_ready",
        }
        or response.get("schema") != "RAOSWordPressPublicationBatchStatusV1"
        or response.get("batch_token") != batch_token
        or response.get("batch_manifest_sha256") != manifest_hash
        or response.get("proposal_count") != len(proposal_ids)
        or response.get("proposal_ids") != proposal_ids
        or response.get("state")
        not in {"REGISTERED", "APPROVED", "APPLIED", "EXPIRED", "FAILED"}
        or type(expires_at_gmt) is not str
        or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
            expires_at_gmt,
        )
        is None
        or type(response.get("preconditions_ready")) is not bool
    ):
        fail("RAOS_WORDPRESS_REQUEST_BATCH_STATUS_INVALID")
    return response


def _codex_publication_evidence_expiry(receipt: Mapping[str, object]) -> str:
    """Only shorten the audit window using the exact bound provider receipts."""

    quality = receipt.get("quality_audit_binding")
    materialization = receipt.get("materialization_binding")
    _validate_quality_audit_binding(quality)
    if type(quality) is not dict or type(materialization) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_CODEX_EVIDENCE_DEADLINE_INVALID")

    def timestamp(value: object) -> datetime:
        if type(value) is not str or TIMESTAMP_RE.fullmatch(value) is None:
            fail("RAOS_WORDPRESS_REQUEST_CODEX_EVIDENCE_DEADLINE_INVALID")
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except ValueError:
            fail("RAOS_WORDPRESS_REQUEST_CODEX_EVIDENCE_DEADLINE_INVALID")

    deadlines = [timestamp(quality["expires_at"])]
    for path, hash_field in (
        (LOCAL_MATERIALIZATION_RECEIPT, "local_receipt_sha256"),
        (PRODUCTION_MATERIALIZATION_RECEIPT, "production_receipt_sha256"),
        (ROOT / V2_STATUS_RELATIVE_PATH, "evidence_status_sha256"),
    ):
        document, raw = _load_owner_private_json_snapshot(
            path,
            MAX_RECEIPT_BYTES,
            "RAOS_WORDPRESS_REQUEST_CODEX_EVIDENCE_DEADLINE_INVALID",
        )
        if hashlib.sha256(raw).hexdigest() != materialization.get(hash_field):
            fail("RAOS_WORDPRESS_REQUEST_CODEX_EVIDENCE_DEADLINE_INVALID")
        if hash_field != "evidence_status_sha256":
            deadlines.append(
                timestamp(document.get("generated_at")) + timedelta(minutes=15)
            )
            continue
        products = document.get("products")
        expected_products = materialization.get("products")
        if (
            type(products) is not list
            or len(products) != 33
            or type(expected_products) is not dict
            or len(expected_products) != 33
            or any(
                type(row) is not dict
                or row.get("state") != "verified"
                or type(row.get("product_id")) is not str
                for row in products
            )
            or {row.get("product_id") for row in products} != set(expected_products)
        ):
            fail("RAOS_WORDPRESS_REQUEST_CODEX_EVIDENCE_DEADLINE_INVALID")
        deadlines.extend(
            timestamp(row.get("retrieved_at")) + timedelta(hours=24) for row in products
        )
    deadlines.append(
        timestamp(materialization.get("manufacturer_sales_state_checked_at_utc"))
        + timedelta(hours=24)
    )
    deadline = min(deadlines)
    if deadline <= datetime.now(UTC):
        fail("RAOS_WORDPRESS_REQUEST_CODEX_EVIDENCE_EXPIRED")
    return deadline.strftime("%Y-%m-%dT%H:%M:%SZ")


def wait_and_apply(
    receipt: dict[str, object],
    path: Path,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    *,
    finalize_applied: bool = False,
) -> dict[str, object]:
    proposal_ids = _registered_proposal_ids(receipt)
    operation_ids = _operation_ids(receipt)
    registration = receipt.get("batch_registration")
    if type(registration) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_BATCH_REGISTRATION_INVALID")
    batch_token = registration.get("batch_token")
    manifest_hash = registration.get("batch_manifest_sha256")
    if type(batch_token) is not str or type(manifest_hash) is not str:
        fail("RAOS_WORDPRESS_REQUEST_BATCH_REGISTRATION_INVALID")
    proposals = receipt.get("proposals")
    if type(proposals) is not list:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    bounded_evidence: dict[str, object] = {}
    quality = receipt.get("quality_audit_binding")
    if (
        not finalize_applied
        and type(quality) is dict
        and quality.get("schema") == wordpress_quality_audit.CODEX_OWNER_BINDING_SCHEMA
    ):
        bounded_evidence["evidence_expires_at_gmt"] = (
            _codex_publication_evidence_expiry(receipt)
        )
    if finalize_applied:
        print(
            "\n適用済みバッチのdeferred cleanupとruntime反映を確認中です。",
            flush=True,
        )
        _touch_receipt(path, receipt, "FINALIZING_APPLIED")
    else:
        quality = receipt.get("quality_audit_binding")
        if (
            type(quality) is dict
            and quality.get("schema")
            == wordpress_quality_audit.CODEX_OWNER_BINDING_SCHEMA
        ):
            _validate_quality_audit_binding(quality)
            print(
                "監査方式: Codex技術監査。人間による第三者署名ではありません。"
                "監査実行の出所・結果と、このバッチの変更内容を確認してください。"
            )
            print(f"Codex監査報告SHA-256: {quality['codex_report_sha256']}")
        print("\nWordPress管理画面で内容を確認し、「一括承認」を押してください。")
        print(f"承認対象バッチtoken末尾12文字: {batch_token[-12:]}")
        print(f"入力するbatch manifest hash末尾8文字: {manifest_hash[-8:]}")
        print(REVIEW_URL)
        if bounded_evidence:
            print(
                f"証跡の有効期限（UTC）: {bounded_evidence['evidence_expires_at_gmt']}。承認後も延長されません。"
            )
        else:
            print(
                "承認期限は提案作成から60分です。承認後は15分の適用・復旧枠へ切り替わります。"
            )
        print("承認待機中です。このコマンドは閉じないでください。", flush=True)
        _touch_receipt(path, receipt, "WAITING_FOR_APPROVAL")
    aggregate = _deployment_mcp_call(
        "release-wait-and-apply",
        {
            "batch_token": batch_token,
            "batch_manifest_sha256": manifest_hash,
            "proposal_ids": proposal_ids,
            **bounded_evidence,
        },
        timeout=RELEASE_FOREGROUND_TIMEOUT_SECONDS,
        runner=runner,
    )
    aggregate_receipts = aggregate.get("receipts")
    if (
        aggregate.get("schema") != "ReleaseWaitApplyReceiptV1"
        or aggregate.get("batch_token") != batch_token
        or aggregate.get("batch_manifest_sha256") != manifest_hash
        or aggregate.get("proposal_count") != len(proposal_ids)
        or aggregate.get("proposal_ids") != proposal_ids
        or aggregate.get("state") != "APPLIED"
        or type(aggregate_receipts) is not list
        or len(aggregate_receipts) != len(proposal_ids)
    ):
        fail("RAOS_WORDPRESS_REQUEST_APPLY_RECEIPT_INVALID")
    proposal_by_id = {
        proposal["proposal_id"]: proposal
        for proposal in proposals
        if type(proposal) is dict and type(proposal.get("proposal_id")) is str
    }
    expected_order = sorted(
        proposal_ids,
        key=lambda proposal_id: (
            proposal_by_id[proposal_id].get("kind") != "THEME_RELEASE",
            proposal_ids.index(proposal_id),
        ),
    )
    for proposal_id, operation in zip(expected_order, aggregate_receipts, strict=True):
        proposal = proposal_by_id.get(proposal_id)
        expected_after = (
            proposal.get("after_sha256") if type(proposal) is dict else None
        )
        if (
            type(operation) is not dict
            or operation.get("schema") != "OperationReceiptV1"
            or operation.get("proposal_id") != proposal_id
            or operation.get("operation_id") != operation_ids[proposal_id]
            or operation.get("state") != "APPLIED"
            or type(operation.get("result_code")) is not str
            or re.fullmatch(r"[A-Z0-9_]{3,96}", operation["result_code"]) is None
            or type(operation.get("after_sha256")) is not str
            or SHA256_RE.fullmatch(operation["after_sha256"]) is None
            or operation["after_sha256"] != expected_after
        ):
            fail("RAOS_WORDPRESS_REQUEST_APPLY_RECEIPT_INVALID")
    receipt["apply_receipt"] = aggregate
    receipt["operation_ids"] = {
        operation["proposal_id"]: operation["operation_id"]
        for operation in aggregate_receipts
    }
    _touch_receipt(path, receipt, "APPLY_RETURNED")
    return aggregate


def _normalized_public_text(parts: Sequence[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _public_stylesheet_candidate_kind(href: str) -> str | None:
    """Classify only child-theme stylesheet evidence; ignore unrelated CSS."""

    try:
        parsed = urlsplit(href)
    except ValueError:
        if (
            any(path in href for path in DIRECT_THEME_STYLESHEET_PATHS)
            or AUTOPTIMIZE_SINGLE_STYLESHEET_PREFIX in href
        ):
            return "invalid"
        return None
    if any(parsed.path.startswith(path) for path in DIRECT_THEME_STYLESHEET_PATHS):
        return "direct"
    if parsed.path.startswith(AUTOPTIMIZE_SINGLE_STYLESHEET_PREFIX):
        return "autoptimize"
    return None


def _public_stylesheet_origin_is_valid(
    href: str,
    *,
    allow_root_relative: bool,
) -> bool:
    try:
        parsed = urlsplit(href)
        port = parsed.port
    except ValueError:
        return False
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        return False
    if not parsed.scheme and not parsed.netloc:
        return allow_root_relative and parsed.path.startswith("/")
    return (
        parsed.scheme == "https"
        and parsed.hostname == urlsplit(ORIGIN).hostname
        and port is None
    )


def _public_theme_stylesheets_are_valid(
    stylesheet_urls: Sequence[str],
    *,
    expected_assets: frozenset[str] = frozenset(THEME_RUNTIME_SENTINEL_PROPERTIES),
) -> bool:
    """Validate direct or Autoptimize materialization of the two theme assets."""

    if not expected_assets or not expected_assets.issubset(
        THEME_RUNTIME_SENTINEL_PROPERTIES
    ):
        return False
    candidates = [
        (kind, href)
        for href in stylesheet_urls
        if (kind := _public_stylesheet_candidate_kind(href)) is not None
    ]
    if (
        len(candidates) != len(expected_assets)
        or len({kind for kind, _href in candidates}) != 1
    ):
        return False
    kind = candidates[0][0]
    if kind == "direct":
        paths: set[str] = set()
        for _kind, href in candidates:
            if len(href) > 8192 or not _public_stylesheet_origin_is_valid(
                href,
                allow_root_relative=True,
            ):
                return False
            try:
                parsed = urlsplit(href)
            except ValueError:
                return False
            if (
                parsed.path not in DIRECT_THEME_STYLESHEET_PATHS
                or parsed.query != f"ver={EXPECTED_THEME_RUNTIME_REVISION}"
            ):
                return False
            paths.add(parsed.path)
        return paths == {
            f"/wp-content/themes/kurashinoshirube-child/{asset}"
            for asset in expected_assets
        }
    if kind == "autoptimize":
        hashes: set[str] = set()
        for _kind, href in candidates:
            if len(href) > 8192 or not _public_stylesheet_origin_is_valid(
                href,
                allow_root_relative=True,
            ):
                return False
            try:
                parsed = urlsplit(href)
            except ValueError:
                return False
            match = re.fullmatch(
                re.escape(AUTOPTIMIZE_SINGLE_STYLESHEET_PREFIX)
                + r"([0-9a-f]{32})\.php",
                parsed.path,
            )
            if (
                match is None
                or parsed.query != f"ver={EXPECTED_THEME_RUNTIME_REVISION}"
            ):
                return False
            hashes.add(match.group(1))
        return len(hashes) == len(expected_assets)
    return False


def _absolute_public_stylesheet_url(href: str) -> str:
    """Resolve one already-validated root-relative or fixed-origin CSS URL."""

    parsed = urlsplit(href)
    if not parsed.scheme and not parsed.netloc:
        return f"{ORIGIN}{href}"
    return href


def _css_code_without_comments_or_strings(source: str) -> str:
    """Mask non-code CSS regions so comments/strings cannot forge a sentinel."""

    output: list[str] = []
    index = 0
    while index < len(source):
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
            output.append(" ")
            index = end + 2
            continue
        character = source[index]
        if character in {'"', "'"}:
            quote = character
            index += 1
            while index < len(source):
                character = source[index]
                if character == "\\":
                    index += 2
                    continue
                index += 1
                if character == quote:
                    break
            else:
                fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
            output.append(" ")
            continue
        output.append(character)
        index += 1
    return "".join(output)


def _public_stylesheet_sentinels(payload: bytes) -> tuple[str, ...]:
    """Return the one exact runtime sentinel carried by a fetched stylesheet."""

    if not payload or len(payload) > MAX_PUBLIC_STYLESHEET_BYTES:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
    try:
        source = payload.decode("utf-8", errors="strict")
    except UnicodeError:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
    if "\x00" in source:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
    code = _css_code_without_comments_or_strings(source)
    found: list[str] = []
    whitespace = r"[\t\n\f\r ]*"
    for asset, property_name in THEME_RUNTIME_SENTINEL_PROPERTIES.items():
        property_pattern = re.compile(
            rf"(?<![-_A-Za-z0-9]){re.escape(property_name)}(?={whitespace}:)"
        )
        exact_pattern = re.compile(
            rf"(?<![-_A-Za-z0-9]){re.escape(property_name)}"
            rf"{whitespace}:{whitespace}{EXPECTED_THEME_RUNTIME_REVISION}"
            rf"(?={whitespace}(?:;|\}}))"
        )
        property_count = len(property_pattern.findall(code))
        exact_count = len(exact_pattern.findall(code))
        if property_count:
            if property_count != 1 or exact_count != 1:
                fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
            found.append(asset)
    if len(found) != 1:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
    return tuple(found)


def _fetch_public_stylesheet_sentinels(
    href: str,
    opener: urllib.request.OpenerDirector,
    cache: dict[str, dict[str, object]],
    *,
    authorization: str | None,
) -> dict[str, object]:
    """Fetch one fixed-origin CSS response without redirects and cache its verdict."""

    url = _absolute_public_stylesheet_url(href)
    cached = cache.get(url)
    if cached is not None:
        return cached
    if len(cache) >= MAX_PUBLIC_STYLESHEET_CACHE_ENTRIES:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
    headers = {
        "Accept": "text/css",
        "Cache-Control": "no-cache",
        "User-Agent": "raos-publication-readback/1.0",
    }
    if authorization is not None:
        headers["Authorization"] = authorization
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with opener.open(request, timeout=30) as response:
            status = response.getcode()
            final_url = response.geturl()
            content_types = _response_header_values(response.headers, "Content-Type")
            payload = response.read(MAX_PUBLIC_STYLESHEET_BYTES + 1)
    except urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
    if (
        status != 200
        or final_url != url
        or len(content_types) != 1
        or content_types[0].split(";", 1)[0].strip().casefold() != "text/css"
        or len(payload) > MAX_PUBLIC_STYLESHEET_BYTES
    ):
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
    result: dict[str, object] = {
        "sentinels": _public_stylesheet_sentinels(payload),
        "content_sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }
    cache[url] = result
    return result


def _public_theme_stylesheet_evidence(
    stylesheet_urls: Sequence[str],
    opener: urllib.request.OpenerDirector,
    cache: dict[str, dict[str, object]],
    *,
    authorization: str | None,
    expected_assets: frozenset[str] = frozenset(THEME_RUNTIME_SENTINEL_PROPERTIES),
) -> list[dict[str, object]]:
    """Bind the accepted URL pair to two distinct fetched runtime sentinels."""

    if not _public_theme_stylesheets_are_valid(
        stylesheet_urls,
        expected_assets=expected_assets,
    ):
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED")
    candidates = [
        (kind, href)
        for href in stylesheet_urls
        if (kind := _public_stylesheet_candidate_kind(href)) is not None
    ]
    kind = candidates[0][0]
    evidence_by_asset: dict[str, dict[str, object]] = {}
    for _candidate_kind, href in candidates:
        fetched = _fetch_public_stylesheet_sentinels(
            href,
            opener,
            cache,
            authorization=authorization,
        )
        sentinels = fetched.get("sentinels")
        if type(sentinels) is not tuple or len(sentinels) != 1:
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
        asset = sentinels[0]
        if asset in evidence_by_asset:
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
        if kind == "direct":
            path = urlsplit(href).path
            expected_asset = path.removeprefix(
                "/wp-content/themes/kurashinoshirube-child/"
            )
            if asset != expected_asset:
                fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
        evidence_by_asset[asset] = {
            "asset": asset,
            "url": _absolute_public_stylesheet_url(href),
            "status": 200,
            "content_type": "text/css",
            "content_sha256": fetched["content_sha256"],
            "bytes": fetched["bytes"],
            "sentinel_property": THEME_RUNTIME_SENTINEL_PROPERTIES[asset],
            "runtime_revision": EXPECTED_THEME_RUNTIME_REVISION,
        }
    if set(evidence_by_asset) != set(expected_assets):
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_STYLESHEET_INVALID")
    return [evidence_by_asset[asset] for asset in sorted(evidence_by_asset)]


def _validated_ctas(
    parser: _PublicPageEvidenceParser,
    *,
    allow_empty: bool = False,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    identities: set[tuple[str, str]] = set()
    placements_by_product: dict[str, set[str]] = {}
    for raw in parser.ctas:
        href = raw.get("href")
        rel = raw.get("rel")
        article_id = raw.get("article_id")
        cta_id = raw.get("cta_id")
        snapshot_id = raw.get("snapshot_id")
        offer_id = raw.get("offer_id")
        product_id = raw.get("product_id")
        placement = raw.get("placement")
        rakuten_measurement_id = raw.get("rakuten_measurement_id")
        if (
            type(href) is not str
            or len(href) > 8192
            or type(rel) is not list
            or any(type(token) is not str for token in rel)
            or type(article_id) is not str
            or not article_id
            or type(product_id) is not str
            or not re.fullmatch(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*", product_id)
            or placement not in {"product_card", "final_summary"}
        ):
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_CTA_INVALID")
        parsed = urlsplit(href)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_CTA_INVALID")
        if parsed.hostname == "hb.afl.rakuten.co.jp":
            if (
                set(rel) != {"sponsored", "nofollow"}
                or type(cta_id) is not str
                or not cta_id
                or type(snapshot_id) is not str
                or not snapshot_id
                or type(offer_id) is not str
                or not offer_id
                or type(rakuten_measurement_id) is not str
                or re.fullmatch(
                    r"[a-z0-9]+-[a-z0-9]+-(?:card|final)",
                    rakuten_measurement_id,
                )
                is None
            ):
                fail("RAOS_WORDPRESS_REQUEST_PUBLIC_CTA_INVALID")
        elif any(
            value is not None
            for value in (cta_id, snapshot_id, offer_id, rakuten_measurement_id)
        ):
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_CTA_INVALID")
        identity = (product_id, placement)
        if identity in identities:
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_CTA_INVALID")
        identities.add(identity)
        placements_by_product.setdefault(product_id, set()).add(placement)
        result.append(
            {
                "href": href,
                "rel": rel,
                "article_id": article_id,
                "cta_id": cta_id,
                "snapshot_id": snapshot_id,
                "offer_id": offer_id,
                "product_id": product_id,
                "placement": placement,
                "rakuten_measurement_id": rakuten_measurement_id,
            }
        )
    if not result and allow_empty and not parser.affiliate_links:
        return []
    if not result:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_CTA_INVALID")
    if any(
        placements != {"product_card", "final_summary"}
        for placements in placements_by_product.values()
    ):
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_CTA_INVALID")
    affiliate_ctas = [
        {
            "href": cta["href"],
            "article_id": cta["article_id"],
            "product_id": cta["product_id"],
            "placement": cta["placement"],
        }
        for cta in result
        if urlsplit(str(cta["href"])).hostname == "hb.afl.rakuten.co.jp"
    ]
    if parser.affiliate_links != affiliate_ctas:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_CTA_INVALID")
    return result


def _validated_product_images(
    parser: _PublicPageEvidenceParser,
    *,
    product_ids: set[str],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for image in parser.product_images:
        product_id = image.get("product_id")
        src = image.get("src")
        alt = image.get("alt")
        if (
            product_id not in product_ids
            or product_id in seen
            or type(src) is not str
            or not src
            or len(src) > 8192
            or type(alt) is not str
            or not alt.strip()
        ):
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_PRODUCT_IMAGE_INVALID")
        parsed = urlsplit(src)
        if parsed.scheme and parsed.scheme != "https":
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_PRODUCT_IMAGE_INVALID")
        if parsed.scheme == "https" and not parsed.hostname:
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_PRODUCT_IMAGE_INVALID")
        if not parsed.scheme and not src.startswith("/"):
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_PRODUCT_IMAGE_INVALID")
        seen.add(product_id)
        result.append({"product_id": product_id, "src": src, "alt": alt})
    if seen != product_ids:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_PRODUCT_IMAGE_INVALID")
    return result


def _json_object_without_duplicates(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_JSON_LD_INVALID")
        result[key] = value
    return result


def _structured_data_types(
    parser: _PublicPageEvidenceParser,
    *,
    post_type: str,
) -> list[str]:
    if (
        len(parser.json_ld_payloads) != 1
        or not parser.json_ld_payloads[0].strip()
        or len(parser.json_ld_payloads[0].encode("utf-8")) > 256 * 1024
    ):
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_JSON_LD_INVALID")
    try:
        payload = json.loads(
            parser.json_ld_payloads[0],
            object_pairs_hook=_json_object_without_duplicates,
        )
    except UnicodeError, json.JSONDecodeError, ValueError, RecursionError:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_JSON_LD_INVALID")
    if (
        type(payload) is not dict
        or set(payload) != {"@context", "@graph"}
        or payload.get("@context") != "https://schema.org"
        or type(payload.get("@graph")) is not list
        or not payload["@graph"]
    ):
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_JSON_LD_INVALID")
    discovered: set[str] = set()

    def add_type(value: str) -> None:
        normalized = re.split(r"[/#:]", value)[-1]
        if not normalized or re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", normalized) is None:
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_JSON_LD_INVALID")
        discovered.add(normalized)

    def visit(value: object, depth: int = 0) -> None:
        if depth > 16:
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_JSON_LD_INVALID")
        if type(value) is dict:
            node_type = value.get("@type")
            if type(node_type) is str:
                add_type(node_type)
            elif type(node_type) is list:
                if not node_type or any(type(item) is not str for item in node_type):
                    fail("RAOS_WORDPRESS_REQUEST_PUBLIC_JSON_LD_INVALID")
                for item in node_type:
                    add_type(item)
            elif node_type is not None:
                fail("RAOS_WORDPRESS_REQUEST_PUBLIC_JSON_LD_INVALID")
            for child in value.values():
                visit(child, depth + 1)
        elif type(value) is list:
            for child in value:
                visit(child, depth + 1)

    visit(payload)
    forbidden = {"Product", "Offer", "Review", "FAQPage"}
    required = {"BreadcrumbList", "Organization", "WebSite"}
    if post_type == "post":
        required.add("Article")
    elif post_type != "page":
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_JSON_LD_INVALID")
    if (
        forbidden & discovered
        or not required.issubset(discovered)
        or (post_type == "page" and "Article" in discovered)
    ):
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_JSON_LD_INVALID")
    return sorted(discovered)


def _validated_public_head(
    parser: _PublicPageEvidenceParser,
    article: Article,
    url: str,
) -> dict[str, object]:
    expected_social_image = expected_social_image_url(article)
    expected_og = {
        "og:title": [article.title],
        "og:description": [article.excerpt],
        "og:url": [url],
        "og:image": [expected_social_image],
    }
    image = urlsplit(expected_social_image)
    if (
        not article.excerpt.strip()
        or parser.meta_descriptions != [article.excerpt]
        or parser.open_graph != expected_og
        or image.scheme != "https"
        or image.hostname != urlsplit(ORIGIN).hostname
        or image.username is not None
        or image.password is not None
        or image.query
        or image.fragment
    ):
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_HEAD_INVALID")
    return {
        "meta_description": article.excerpt,
        "open_graph": {
            key: values[0] for key, values in sorted(parser.open_graph.items())
        },
        "json_ld_types": _structured_data_types(
            parser,
            post_type=article.post_type,
        ),
    }


def _public_page_evidence(
    article: Article,
    opener: urllib.request.OpenerDirector,
    *,
    authorization: str | None = None,
    stylesheet_cache: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    url = f"{ORIGIN}/{article.production_slug}/"
    request_headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "raos-publication-readback/1.0",
    }
    if authorization is not None:
        if (
            type(authorization) is not str
            or not authorization.startswith("Basic ")
            or len(authorization) > 2048
            or "\r" in authorization
            or "\n" in authorization
        ):
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_INVALID")
        request_headers["Authorization"] = authorization
    request = urllib.request.Request(
        url,
        headers=request_headers,
        method="GET",
    )
    try:
        with opener.open(request, timeout=30) as response:
            status = response.getcode()
            final_url = response.geturl()
            content_type = (
                (response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
            )
            response_noindex = any(
                _robots_blocks_indexing(value)
                for value in _response_header_values(
                    response.headers,
                    "X-Robots-Tag",
                )
            )
            payload = response.read(MAX_PUBLIC_PAGE_BYTES + 1)
    except urllib.error.HTTPError as error:
        if 300 <= error.code < 400:
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_REDIRECT_REFUSED")
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_HTTP_FAILED")
    except urllib.error.URLError, TimeoutError, OSError:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_TRANSPORT_FAILED")
    if (
        status != 200
        or final_url != url
        or content_type not in {"text/html", "application/xhtml+xml"}
        or len(payload) > MAX_PUBLIC_PAGE_BYTES
    ):
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_RESPONSE_INVALID")
    try:
        markup = payload.decode("utf-8", errors="strict")
    except UnicodeError:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_RESPONSE_INVALID")

    parser = _PublicPageEvidenceParser()
    desired = _PublicPageEvidenceParser()
    try:
        parser.feed(markup)
        parser.close()
        desired.feed(article.block_markup)
        desired.close()
    except Exception:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_HTML_INVALID")
    visible = _normalized_public_text(parser.visible_text)
    required_headings = desired.headings
    head_evidence = _validated_public_head(parser, article, url)
    expected_heading_prefix = [
        ("h1", article.title),
        *desired.heading_outline,
    ]
    allowed_heading_outlines = [
        [
            *expected_heading_prefix,
            ("h2", "暮らしのしるべ"),
        ]
    ]
    if article.post_type == "post":
        allowed_heading_outlines.append(
            [
                *expected_heading_prefix,
                ("h2", "関連記事"),
                ("h2", "暮らしのしるべ"),
            ]
        )
    expected_stylesheet_assets = {"assets/theme.css"}
    if article.post_type == "post":
        expected_stylesheet_assets.add("assets/editorial-v2.css")
    expected_assets = frozenset(expected_stylesheet_assets)
    common_invalid = (
        response_noindex
        or parser.noindex
        or parser.canonical_urls != [url]
        or len(parser.page_titles) != 1
        or article.title not in parser.page_titles[0]
        or parser.h1_titles != [article.title]
        or not required_headings
        or parser.heading_outline not in allowed_heading_outlines
        or any(heading not in visible for heading in required_headings)
        or not _public_theme_stylesheets_are_valid(
            parser.stylesheet_urls,
            expected_assets=expected_assets,
        )
    )
    if common_invalid:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED")
    stylesheet_evidence = _public_theme_stylesheet_evidence(
        parser.stylesheet_urls,
        opener,
        stylesheet_cache if stylesheet_cache is not None else {},
        authorization=authorization,
        expected_assets=expected_assets,
    )
    if article.post_type == "page":
        private_markers = {
            "confirmed_contribution_profit",
            "owner_hourly_rate",
            "service_account_key",
            "private_key",
            ".secrets/",
            "rakuten_order_id=",
        }
        if (
            any(value not in visible for value in article.required_key_content)
            or any(marker in visible.casefold() for marker in private_markers)
            or parser.ctas
            or parser.affiliate_links
        ):
            fail("RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED")
        return {
            "url": url,
            "status": 200,
            "post_type": "page",
            "canonical_url": parser.canonical_urls[0],
            "indexable": True,
            "title": parser.page_titles[0],
            "h1": parser.h1_titles[0],
            "heading_count": len(required_headings),
            "required_key_content": list(article.required_key_content),
            "private_financial_data_absent": True,
            "theme_version": EXPECTED_THEME_VERSION,
            "theme_runtime_revision": EXPECTED_THEME_RUNTIME_REVISION,
            "theme_stylesheets": stylesheet_evidence,
            **head_evidence,
        }
    allow_empty_ctas = article.production_slug in ZERO_PRODUCT_ROUTE_SLUGS
    expected_ctas = _validated_ctas(desired, allow_empty=allow_empty_ctas)
    actual_ctas = _validated_ctas(parser, allow_empty=allow_empty_ctas)
    product_ids = {
        str(cta["product_id"])
        for cta in expected_ctas
        if type(cta.get("product_id")) is str
    }
    expected_images = _validated_product_images(desired, product_ids=product_ids)
    actual_images = _validated_product_images(parser, product_ids=product_ids)
    expected_disclosure = _normalized_public_text(desired.disclosure_text)
    actual_disclosure = _normalized_public_text(parser.disclosure_text)
    if (
        expected_ctas != actual_ctas
        or expected_images != actual_images
        or "広告を含みます" not in expected_disclosure
        or expected_disclosure != actual_disclosure
    ):
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED")
    cta_evidence = [
        {
            **{key: value for key, value in cta.items() if key != "href"},
            "destination_sha256": hashlib.sha256(
                str(cta["href"]).encode("utf-8")
            ).hexdigest(),
        }
        for cta in actual_ctas
    ]
    return {
        "url": url,
        "status": 200,
        "canonical_url": parser.canonical_urls[0],
        "indexable": True,
        "title": parser.page_titles[0],
        "heading_count": len(required_headings),
        "ctas": cta_evidence,
        "product_images": actual_images,
        "advertising_disclosure": actual_disclosure,
        "theme_version": EXPECTED_THEME_VERSION,
        "theme_runtime_revision": EXPECTED_THEME_RUNTIME_REVISION,
        "theme_stylesheets": stylesheet_evidence,
        **head_evidence,
    }


def verify_public_pages(
    articles: Sequence[Article],
    *,
    attempts: int = 6,
    sleeper: Callable[[float], None] = time.sleep,
    opener: urllib.request.OpenerDirector | None = None,
    authorization: str | None = None,
) -> dict[str, object]:
    if not 1 <= attempts <= 10:
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_INVALID")
    public_opener = opener or urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _RefuseRedirectHandler(),
    )
    evidence: dict[str, object] = {}
    stylesheet_cache: dict[str, dict[str, object]] = {}
    for article in articles:
        last_error: PublicationFailure | None = None
        for attempt in range(attempts):
            try:
                evidence[article.production_slug] = _public_page_evidence(
                    article,
                    public_opener,
                    authorization=authorization,
                    stylesheet_cache=stylesheet_cache,
                )
                last_error = None
                break
            except PublicationFailure as error:
                last_error = error
                if attempt + 1 < attempts:
                    sleeper(2.0)
        if last_error is not None:
            raise last_error
    return evidence


def _require_quality_audit_attestation_inputs(
    attestation_path: Path | None,
    signature_path: Path | None,
) -> tuple[Path, Path]:
    """Require the exact owner-private detached-attestation input pair."""

    if attestation_path is None or signature_path is None:
        fail("RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_ATTESTATION_REQUIRED")
    if not attestation_path.is_absolute() or not signature_path.is_absolute():
        fail("RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_ATTESTATION_INVALID")
    return attestation_path, signature_path


def _validate_quality_audit_binding(value: object) -> None:
    if value is None:
        return
    if (
        type(value) is dict
        and value.get("schema") == wordpress_quality_audit.CODEX_OWNER_BINDING_SCHEMA
    ):
        try:
            wordpress_quality_audit.validate_codex_owner_binding(value)
        except wordpress_quality_audit.QualityAuditFailure:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        return
    if type(value) is not dict or set(value) != {
        "schema",
        "audit_phase",
        "status",
        "completion_state",
        "production_parity_state",
        "evaluated_at",
        "contract_file_sha256",
        "ledger_file_sha256",
        "ledger_sha256",
        "fingerprint_bundle_sha256",
        "latest_round_sha256",
        "round_count",
        "consecutive_clean_rounds",
        "attestation_payload_sha256",
        "attestation_signature_sha256",
        "reviewer_key_id",
        "reviewer_id",
        "expires_at",
        "reviewer_attestation_verified",
    }:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    evaluated_at = value.get("evaluated_at")
    expires_at = value.get("expires_at")
    try:
        evaluated = datetime.strptime(
            evaluated_at,
            "%Y-%m-%dT%H:%M:%SZ",
        ).replace(tzinfo=UTC)
        expires = datetime.strptime(
            expires_at,
            "%Y-%m-%dT%H:%M:%SZ",
        ).replace(tzinfo=UTC)
    except TypeError, ValueError:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    if (
        value.get("schema") != "RAOS_WORDPRESS_QUALITY_AUDIT_BINDING_V3"
        or value.get("audit_phase") != wordpress_quality_audit.PRE_PUBLICATION_PHASE_ID
        or value.get("status") != "COMPLETE"
        or value.get("completion_state")
        != wordpress_quality_audit.PRE_PUBLICATION_COMPLETION_STATE
        or value.get("production_parity_state")
        != wordpress_quality_audit.POST_APPLY_PENDING_STATE
        or type(evaluated_at) is not str
        or TIMESTAMP_RE.fullmatch(evaluated_at) is None
        or type(expires_at) is not str
        or TIMESTAMP_RE.fullmatch(expires_at) is None
        or expires <= evaluated
        or any(
            type(value.get(name)) is not str or SHA256_RE.fullmatch(value[name]) is None
            for name in {
                "contract_file_sha256",
                "ledger_file_sha256",
                "ledger_sha256",
                "fingerprint_bundle_sha256",
                "latest_round_sha256",
                "attestation_payload_sha256",
                "attestation_signature_sha256",
            }
        )
        or type(value.get("reviewer_key_id")) is not str
        or QUALITY_AUDIT_IDENTIFIER_RE.fullmatch(value["reviewer_key_id"]) is None
        or type(value.get("reviewer_id")) is not str
        or QUALITY_AUDIT_IDENTIFIER_RE.fullmatch(value["reviewer_id"]) is None
        or value.get("reviewer_attestation_verified") is not True
        or type(value.get("round_count")) is not int
        or value["round_count"] < 2
        or type(value.get("consecutive_clean_rounds")) is not int
        or value["consecutive_clean_rounds"] < 2
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")


def _require_quality_audit_inputs(
    attestation_path: Path | None,
    signature_path: Path | None,
    *,
    audit_mode: str = "signed-independent",
    codex_report_path: Path | None = None,
) -> None:
    if audit_mode == "signed-independent":
        if codex_report_path is not None:
            fail("RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_MODE_INVALID")
        _require_quality_audit_attestation_inputs(attestation_path, signature_path)
    elif audit_mode == "codex-owner":
        if attestation_path is not None or signature_path is not None:
            fail("RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_MODE_INVALID")
        if codex_report_path is None or not codex_report_path.is_absolute():
            fail("RAOS_WORDPRESS_REQUEST_CODEX_AUDIT_REPORT_REQUIRED")
    else:
        fail("RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_MODE_INVALID")


def publication_quality_audit(
    attestation_path: Path | None,
    signature_path: Path | None,
    *,
    audit_mode: str = "signed-independent",
    codex_report_path: Path | None = None,
) -> dict[str, object]:
    _require_quality_audit_inputs(
        attestation_path,
        signature_path,
        audit_mode=audit_mode,
        codex_report_path=codex_report_path,
    )
    if audit_mode == "signed-independent":
        return strict_local_quality_audit(attestation_path, signature_path)
    assert codex_report_path is not None
    try:
        binding = wordpress_quality_audit.validate_codex_owner_report(codex_report_path)
    except wordpress_quality_audit.QualityAuditFailure:
        fail("RAOS_WORDPRESS_REQUEST_CODEX_AUDIT_INCOMPLETE")
    _validate_quality_audit_binding(binding)
    return binding


def strict_local_quality_audit(
    attestation_path: Path | None,
    signature_path: Path | None,
) -> dict[str, object]:
    """Require two fresh, independent clean rounds for the exact repository."""

    attestation_path, signature_path = _require_quality_audit_attestation_inputs(
        attestation_path,
        signature_path,
    )
    try:
        attestation_raw_before = wordpress_quality_audit._read_secure_exact_path(
            attestation_path,
            maximum=wordpress_quality_audit.MAX_ATTESTATION_BYTES,
        )
        signature_raw_before = wordpress_quality_audit._read_secure_exact_path(
            signature_path,
            maximum=wordpress_quality_audit.MAX_ATTESTATION_SIGNATURE_BYTES,
        )
        contract, contract_file_sha256 = wordpress_quality_audit.load_contract()
        ledger, ledger_raw = wordpress_quality_audit.read_json(
            wordpress_quality_audit.DEFAULT_LEDGER_PATH
        )
        result = wordpress_quality_audit.validate_document(
            ledger,
            contract,
            contract_file_sha256,
            attestation_path=attestation_path,
            attestation_signature_path=signature_path,
        )
        attestation_payload = wordpress_quality_audit._read_canonical_attestation(
            attestation_path
        )
        attestation_raw_after = wordpress_quality_audit._read_secure_exact_path(
            attestation_path,
            maximum=wordpress_quality_audit.MAX_ATTESTATION_BYTES,
        )
        signature_raw_after = wordpress_quality_audit._read_secure_exact_path(
            signature_path,
            maximum=wordpress_quality_audit.MAX_ATTESTATION_SIGNATURE_BYTES,
        )
        completion = ledger.get("completion")
        rounds = ledger.get("rounds")
        repository_fingerprints = ledger.get("repository_fingerprints")
        completion_streak = (
            completion.get("consecutive_clean_rounds")
            if type(completion) is dict
            else None
        )
        if (
            result.status != "COMPLETE"
            or result.audit_phase != wordpress_quality_audit.PRE_PUBLICATION_PHASE_ID
            or result.completion_state
            != wordpress_quality_audit.PRE_PUBLICATION_COMPLETION_STATE
            or result.production_parity_state
            != wordpress_quality_audit.POST_APPLY_PENDING_STATE
            or result.round_count < 2
            or result.consecutive_clean_rounds < 2
            or result.reviewer_attestation_verified is not True
            or attestation_raw_before != attestation_raw_after
            or signature_raw_before != signature_raw_after
            or attestation_raw_after
            != wordpress_quality_audit.canonical_json(attestation_payload) + b"\n"
            or type(completion) is not dict
            or completion.get("status") != "COMPLETE"
            or completion.get("audit_phase")
            != wordpress_quality_audit.PRE_PUBLICATION_PHASE_ID
            or completion.get("completion_state")
            != wordpress_quality_audit.PRE_PUBLICATION_COMPLETION_STATE
            or completion.get("production_parity_state")
            != wordpress_quality_audit.POST_APPLY_PENDING_STATE
            or type(completion_streak) is not int
            or completion_streak < 2
            or type(rounds) is not list
            or len(rounds) != result.round_count
            or type(rounds[-1]) is not dict
            or type(rounds[-1].get("round_sha256")) is not str
            or type(repository_fingerprints) is not dict
        ):
            fail("RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_INCOMPLETE")
        binding: dict[str, object] = {
            "schema": "RAOS_WORDPRESS_QUALITY_AUDIT_BINDING_V3",
            "audit_phase": result.audit_phase,
            "status": "COMPLETE",
            "completion_state": result.completion_state,
            "production_parity_state": result.production_parity_state,
            "evaluated_at": ledger["evaluated_at"],
            "contract_file_sha256": contract_file_sha256,
            "ledger_file_sha256": hashlib.sha256(ledger_raw).hexdigest(),
            "ledger_sha256": result.ledger_sha256,
            "fingerprint_bundle_sha256": (
                wordpress_quality_audit.fingerprint_bundle_sha256(
                    repository_fingerprints
                )
            ),
            "latest_round_sha256": rounds[-1]["round_sha256"],
            "round_count": result.round_count,
            "consecutive_clean_rounds": result.consecutive_clean_rounds,
            "attestation_payload_sha256": hashlib.sha256(
                attestation_raw_after
            ).hexdigest(),
            "attestation_signature_sha256": hashlib.sha256(
                signature_raw_after
            ).hexdigest(),
            "reviewer_key_id": attestation_payload["reviewer_key_id"],
            "reviewer_id": attestation_payload["reviewer_id"],
            "expires_at": attestation_payload["expires_at"],
            "reviewer_attestation_verified": True,
        }
    except wordpress_quality_audit.QualityAuditFailure:
        fail("RAOS_WORDPRESS_REQUEST_QUALITY_AUDIT_INVALID")
    _validate_quality_audit_binding(binding)
    return binding


def _seo_utc_instant(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")
    if parsed.utcoffset() != timedelta(0):
        fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")
    return parsed.astimezone(UTC)


def _validated_seo_check(
    value: object,
    *,
    now: datetime,
    require_recent: bool,
) -> dict[str, str]:
    if type(value) is not dict or set(value) != {
        "status",
        "detail",
        "evidence_sha256",
        "observed_at",
    }:
        fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")
    observed = _seo_utc_instant(value.get("observed_at"))
    if (
        value.get("status") != "PASS"
        or type(value.get("detail")) is not str
        or not value["detail"]
        or type(value.get("evidence_sha256")) is not str
        or SHA256_RE.fullmatch(value["evidence_sha256"]) is None
        or observed > now + timedelta(seconds=30)
        or (require_recent and now - observed > MAX_PUBLIC_SEO_AUDIT_AGE)
    ):
        fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")
    return dict(value)


def _validate_seo_audit_binding(value: object) -> None:
    if value is None:
        return
    if type(value) is not dict or set(value) != {
        "schema",
        "origin",
        "status",
        "generated_at",
        "inventory_count",
        "content_sitemap_count",
        "contract_sha256",
        "portfolio_sha256",
        "report_sha256",
        "page_evidence_sha256",
        "surface_evidence_sha256",
        "index_state_basis",
    }:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    pages = value.get("page_evidence_sha256")
    surfaces = value.get("surface_evidence_sha256")
    if (
        value.get("schema") != "RAOS_WORDPRESS_SEO_AUDIT_BINDING_V1"
        or value.get("origin") != ORIGIN
        or value.get("status") != "PASS"
        or value.get("inventory_count") != 14
        or value.get("content_sitemap_count") != 13
        or type(value.get("contract_sha256")) is not str
        or SHA256_RE.fullmatch(value["contract_sha256"]) is None
        or type(value.get("portfolio_sha256")) is not str
        or SHA256_RE.fullmatch(value["portfolio_sha256"]) is None
        or type(value.get("report_sha256")) is not str
        or SHA256_RE.fullmatch(value["report_sha256"]) is None
        or type(pages) is not dict
        or set(pages) != SEO_INVENTORY_IDENTIFIERS
        or any(
            type(digest) is not str or SHA256_RE.fullmatch(digest) is None
            for digest in pages.values()
        )
        or type(surfaces) is not dict
        or set(surfaces) != SEO_SURFACE_CHECKS
        or any(
            type(digest) is not str or SHA256_RE.fullmatch(digest) is None
            for digest in surfaces.values()
        )
        or value.get("index_state_basis") not in SEO_INDEX_STATE_BASES
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    try:
        _seo_utc_instant(value.get("generated_at"))
    except PublicationFailure:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")


def _validated_public_seo_audit_report(
    report: object,
    contract: wordpress_seo_audit.AuditContract,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    observed_now = datetime.now(UTC) if now is None else now.astimezone(UTC)
    if type(report) is not dict or set(report) != {
        "schema",
        "generated_at",
        "origin",
        "status",
        "inventory_count",
        "content_sitemap_count",
        "contract_sha256",
        "portfolio_sha256",
        "pages",
        "surfaces",
        "index_state_basis",
    }:
        fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")
    generated = _seo_utc_instant(report.get("generated_at"))
    pages = report.get("pages")
    surfaces = report.get("surfaces")
    index_basis = report.get("index_state_basis")
    if (
        report.get("schema") != "RAOS_WORDPRESS_SEO_AUDIT_REPORT_V1"
        or report.get("origin") != contract.origin
        or contract.origin != ORIGIN
        or report.get("status") != "PASS"
        or report.get("inventory_count") != len(contract.items)
        or report.get("inventory_count") != 14
        or report.get("content_sitemap_count") != len(contract.content_urls)
        or report.get("content_sitemap_count") != 13
        or report.get("contract_sha256") != contract.contract_sha256
        or report.get("portfolio_sha256") != contract.portfolio_sha256
        or generated > observed_now + timedelta(seconds=30)
        or observed_now - generated > MAX_PUBLIC_SEO_AUDIT_AGE
        or type(pages) is not list
        or len(pages) != 14
        or type(surfaces) is not dict
        or set(surfaces) != SEO_SURFACE_CHECKS
        or index_basis not in SEO_INDEX_STATE_BASES
    ):
        fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")

    expected_items = {item.identifier: item for item in contract.items}
    page_hashes: dict[str, str] = {}
    for page in pages:
        if type(page) is not dict or set(page) != {
            "identifier",
            "role",
            "url",
            "status",
            "checks",
            "schema_types",
            "index_state",
        }:
            fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")
        identifier = page.get("identifier")
        if type(identifier) is not str or identifier in page_hashes:
            fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")
        item = expected_items.get(identifier)
        checks = page.get("checks")
        schema_types = page.get("schema_types")
        index_state = page.get("index_state")
        if (
            item is None
            or page.get("role") != item.role
            or page.get("url") != item.url
            or page.get("status") != "PASS"
            or type(checks) is not dict
            or frozenset(checks)
            not in {
                SEO_CORE_PAGE_CHECKS,
                SEO_CORE_PAGE_CHECKS | {"gsc_indexed"},
            }
            or type(schema_types) is not list
            or any(type(name) is not str for name in schema_types)
            or not contract.required_types[item.role].issubset(schema_types)
            or bool(contract.forbidden_types & set(schema_types))
            or type(index_state) is not dict
            or index_state.get("basis") != index_basis
        ):
            fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")
        for name, check in checks.items():
            _validated_seo_check(
                check,
                now=observed_now,
                require_recent=name != "gsc_indexed",
            )
        if index_basis == "UNAVAILABLE":
            if index_state.get("state") != "UNAVAILABLE" or "gsc_indexed" in checks:
                fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")
        elif index_state.get("state") != "INDEXED" or "gsc_indexed" not in checks:
            fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")
        page_hashes[identifier] = hashlib.sha256(canonical_json_bytes(page)).hexdigest()
    if set(page_hashes) != set(expected_items) or set(page_hashes) != (
        SEO_INVENTORY_IDENTIFIERS
    ):
        fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")

    surface_hashes: dict[str, str] = {}
    for name, check in surfaces.items():
        _validated_seo_check(check, now=observed_now, require_recent=True)
        surface_hashes[name] = hashlib.sha256(canonical_json_bytes(check)).hexdigest()
    binding: dict[str, object] = {
        "schema": "RAOS_WORDPRESS_SEO_AUDIT_BINDING_V1",
        "origin": ORIGIN,
        "status": "PASS",
        "generated_at": report["generated_at"],
        "inventory_count": 14,
        "content_sitemap_count": 13,
        "contract_sha256": contract.contract_sha256,
        "portfolio_sha256": contract.portfolio_sha256,
        "report_sha256": hashlib.sha256(canonical_json_bytes(report)).hexdigest(),
        "page_evidence_sha256": dict(sorted(page_hashes.items())),
        "surface_evidence_sha256": dict(sorted(surface_hashes.items())),
        "index_state_basis": index_basis,
    }
    _validate_seo_audit_binding(binding)
    return binding


def strict_public_seo_audit() -> dict[str, object]:
    """Run the complete 14-URL semantic SEO audit after publication readback."""

    try:
        contract = wordpress_seo_audit.load_contract()
        report = wordpress_seo_audit.run_audit(
            wordpress_seo_audit.BoundedHttpsTransport(contract),
            contract,
        )
    except wordpress_seo_audit.AuditError:
        fail("RAOS_WORDPRESS_REQUEST_SEO_AUDIT_INVALID")
    return _validated_public_seo_audit_report(report, contract)


def _published_document_evidence(
    client: Any,
    articles: Sequence[Article],
    receipt: Mapping[str, object],
) -> dict[str, object]:
    drafts = receipt.get("drafts")
    if type(drafts) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    evidence: dict[str, object] = {}
    for article in articles:
        draft = drafts.get(article.production_slug)
        if type(draft) is not dict or type(draft.get("id")) is not int:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        post_id = draft["id"]
        document = client.call("raos-codex-content-get", {"id": post_id})
        if (
            document.get("status") != "publish"
            or document_projection(document) != article.document()
            or document.get("content_sha256")
            != _content_after_sha256(article.document(), post_id)
        ):
            fail("RAOS_WORDPRESS_REQUEST_PUBLISH_READBACK_FAILED")
        evidence[article.production_slug] = {
            "id": post_id,
            "slug": article.production_slug,
            "post_type": article.post_type,
            "status": "publish",
            **precondition(document),
        }
    return evidence


def _published_receipt_document_evidence(
    client: Any,
    receipt: Mapping[str, object],
) -> dict[str, object]:
    """Read back an applied legacy attempt without its stale local fixture.

    The immutable proposal records identify the exact published target.  The
    live content hash is necessary but not sufficient evidence, so recompute it
    from the returned document projection before preserving a CAS baseline.
    """

    _proposal_ids(receipt)
    selected_slugs = receipt.get("selected_slugs")
    drafts = receipt.get("drafts")
    proposals = receipt.get("proposals")
    if (
        type(selected_slugs) is not list
        or type(drafts) is not dict
        or type(proposals) is not list
        or set(drafts) != set(selected_slugs)
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    targets = {
        proposal["slug"]: proposal
        for proposal in proposals
        if type(proposal) is dict and proposal.get("kind") == "CONTENT_RELEASE"
    }
    if set(targets) != set(selected_slugs):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")

    evidence: dict[str, object] = {}
    for slug in selected_slugs:
        draft = drafts.get(slug)
        proposal = targets.get(slug)
        if (
            type(slug) is not str
            or type(draft) is not dict
            or set(draft) != {"id", "content_sha256"}
            or type(draft.get("id")) is not int
            or draft["id"] < 1
            or type(draft.get("content_sha256")) is not str
            or SHA256_RE.fullmatch(draft["content_sha256"]) is None
            or type(proposal) is not dict
        ):
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        post_id = draft["id"]
        after_sha256 = proposal.get("after_sha256")
        document = client.call("raos-codex-content-get", {"id": post_id})
        if (
            document.get("id") != post_id
            or document.get("slug") != slug
            or document.get("status") != "publish"
            or document.get("content_sha256") != after_sha256
            or _content_after_sha256(document_projection(document), post_id)
            != after_sha256
        ):
            fail("RAOS_WORDPRESS_REQUEST_PUBLISH_READBACK_FAILED")
        evidence[slug] = _baseline_record(document)
    return evidence


def _require_applied_receipt_content_operations(
    receipt: Mapping[str, object],
    operations: Mapping[str, Mapping[str, object]],
) -> None:
    proposals = receipt.get("proposals")
    _proposal_ids(receipt)
    if type(proposals) is not list:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    expected = {
        proposal["proposal_id"]
        for proposal in proposals
        if type(proposal) is dict and proposal.get("kind") == "CONTENT_RELEASE"
    }
    if set(operations) != expected or any(
        type(operation) is not dict or operation.get("state") != "APPLIED"
        for operation in operations.values()
    ):
        fail("RAOS_WORDPRESS_REQUEST_OPERATION_READBACK_INVALID")


def verify_published(
    client: Any,
    articles: Sequence[Article],
    receipt: dict[str, object],
    path: Path,
    *,
    expected_theme_version: str,
    expected_theme_tree_sha256: str,
    theme_was_proposed: bool,
    require_measurement_ready: bool,
    deployment_runner: Callable[..., subprocess.CompletedProcess[bytes]],
) -> None:
    drafts = receipt.get("drafts")
    expected_theme_runtime_revision = receipt.get("desired_theme_runtime_revision")
    if (
        type(drafts) is not dict
        or expected_theme_runtime_revision != EXPECTED_THEME_RUNTIME_REVISION
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    document_evidence = _published_document_evidence(client, articles, receipt)
    status = client.call("raos-codex-site-status", {})
    validate_site_status(
        status,
        require_measurement_ready=require_measurement_ready,
        require_measurement_off=not require_measurement_ready,
    )
    theme = status.get("theme")
    if (
        type(theme) is not dict
        or theme.get("version") != expected_theme_version
        or theme.get("runtime_version") != expected_theme_version
        or theme.get("runtime_revision") != expected_theme_runtime_revision
        or expected_theme_version != EXPECTED_THEME_VERSION
    ):
        fail("RAOS_WORDPRESS_REQUEST_THEME_READBACK_FAILED")
    deployed = deployment_status(deployment_runner)
    deployed_theme = deployed.get("theme")
    if (
        type(deployed_theme) is not dict
        or deployed_theme.get("version") != expected_theme_version
        or deployed_theme.get("runtime_version") != expected_theme_version
        or deployed_theme.get("runtime_revision") != expected_theme_runtime_revision
        or deployed_theme.get("tree_sha256") != expected_theme_tree_sha256
    ):
        fail("RAOS_WORDPRESS_REQUEST_THEME_READBACK_FAILED")
    operation_evidence = read_content_operations(client, receipt)
    if any(
        operation.get("state") != "APPLIED" for operation in operation_evidence.values()
    ):
        fail("RAOS_WORDPRESS_REQUEST_OPERATION_READBACK_INVALID")
    authorization_factory = getattr(client, "public_authorization", None)
    if not callable(authorization_factory):
        fail("RAOS_WORDPRESS_REQUEST_AUTHENTICATED_READBACK_UNAVAILABLE")
    authorization = authorization_factory()
    if type(authorization) is not str or not authorization.startswith("Basic "):
        fail("RAOS_WORDPRESS_REQUEST_AUTHENTICATED_READBACK_UNAVAILABLE")
    authenticated_pages = verify_public_pages(
        articles,
        authorization=authorization,
    )
    receipt["authenticated_readback"] = {
        "documents": document_evidence,
        "operations": operation_evidence,
        "public_pages": authenticated_pages,
        "theme": {
            "version": expected_theme_version,
            "runtime_version": expected_theme_version,
            "runtime_revision": expected_theme_runtime_revision,
            "tree_sha256": expected_theme_tree_sha256,
            "proposed": theme_was_proposed,
        },
    }
    receipt["public_readback"] = verify_public_pages(articles)
    receipt["seo_audit_readback"] = strict_public_seo_audit()
    _validate_seo_audit_binding(receipt["seo_audit_readback"])
    _touch_receipt(path, receipt, "APPLIED")


def _receipt_matches_captured_inputs(
    receipt: Mapping[str, object],
    articles: Sequence[Article],
    desired_theme_tree_sha256: str,
    materialization_binding: Mapping[str, object] | None,
    quality_audit_binding: Mapping[str, object] | None,
) -> bool:
    return (
        receipt.get("desired_sha256")
        == {article.production_slug: article.desired_sha256() for article in articles}
        and receipt.get("desired_theme_tree_sha256") == desired_theme_tree_sha256
        and receipt.get("materialization_binding")
        == (
            dict(materialization_binding)
            if materialization_binding is not None
            else None
        )
        and receipt.get("quality_audit_binding")
        == (dict(quality_audit_binding) if quality_audit_binding is not None else None)
    )


def _same_desired(
    receipt: Mapping[str, object],
    articles: Sequence[Article],
    desired_theme_tree_sha256: str,
    materialization_binding: Mapping[str, object] | None,
    quality_audit_binding: Mapping[str, object] | None,
) -> bool:
    return (
        _receipt_matches_captured_inputs(
            receipt,
            articles,
            desired_theme_tree_sha256,
            materialization_binding,
            quality_audit_binding,
        )
        and receipt.get("desired_theme_runtime_revision")
        == EXPECTED_THEME_RUNTIME_REVISION
    )


def _revalidate_apply_inputs(
    receipt: Mapping[str, object],
    *,
    rakuten_activation_dry_run: Path | None,
    expected_activation: PublicationOverlay | None,
    quality_audit_attestation: Path | None,
    quality_audit_signature: Path | None,
    quality_audit_mode: str = "signed-independent",
    codex_audit_report: Path | None = None,
) -> tuple[
    PublicationOverlay,
    list[Article],
    dict[str, object],
    dict[str, object],
]:
    """Revalidate every mutable local authorization input before live apply."""

    current_activation = validate_publication_link_evidence(
        rakuten_activation_dry_run,
        link_mode=(
            "standard-api"
            if isinstance(expected_activation, RakutenStandardApiOverlayV1)
            else "measured-admin"
        ),
        require_recent=True,
    )
    if expected_activation is not None and current_activation != expected_activation:
        fail("RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT")
    current_articles = load_publication_items(
        "all",
        article_fixture_root=current_activation.production_fixture_root,
    )
    current_materialization = activation_materialization_binding(
        current_activation,
        [article for article in current_articles if article.post_type == "post"],
        require_recent=True,
    )
    current_theme_tree = tracked_theme_tree_sha256()
    if (
        theme_version() != EXPECTED_THEME_VERSION
        or theme_runtime_revision() != EXPECTED_THEME_RUNTIME_REVISION
    ):
        fail("RAOS_WORDPRESS_REQUEST_PENDING_THEME_DRIFT")
    current_quality = publication_quality_audit(
        quality_audit_attestation,
        quality_audit_signature,
        audit_mode=quality_audit_mode,
        codex_report_path=codex_audit_report,
    )
    if not _same_desired(
        receipt,
        current_articles,
        current_theme_tree,
        current_materialization,
        current_quality,
    ):
        fail("RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT")
    return (
        current_activation,
        current_articles,
        current_materialization,
        current_quality,
    )


def _resume_ready(receipt: Mapping[str, object], expected_count: int) -> bool:
    proposals = receipt.get("proposals")
    return (
        receipt.get("state")
        in {
            "BATCH_REGISTERED",
            "WAITING_FOR_APPROVAL",
            "FINALIZING_APPLIED",
            "APPLY_RETURNED",
            "APPLIED",
        }
        and type(proposals) is list
        and len(proposals) in {expected_count, expected_count + 1}
        and type(receipt.get("batch_registration")) is dict
    )


def _theme_was_proposed(receipt: Mapping[str, object], content_count: int) -> bool:
    proposals = receipt.get("proposals")
    return type(proposals) is list and len(proposals) == content_count + 1


def _require_applied_batch_ready(batch: Mapping[str, object]) -> None:
    if batch.get("state") != "APPLIED" or batch.get("preconditions_ready") is not True:
        fail("RAOS_WORDPRESS_REQUEST_BATCH_STATUS_INVALID")


def _unregistered_proposal_set_ready(
    receipt: Mapping[str, object],
    content_count: int,
) -> bool:
    proposals = receipt.get("proposals")
    if (
        receipt.get("state") != "PROPOSALS_READY"
        or type(proposals) is not list
        or len(proposals) not in {content_count, content_count + 1}
        or receipt.get("batch_registration") is not None
    ):
        return False
    return len(_proposal_ids(receipt)) == len(proposals)


def _uses_current_activation_binding(receipt: Mapping[str, object]) -> bool:
    materialization_binding = receipt.get("materialization_binding")
    return type(materialization_binding) is dict and materialization_binding.get(
        "schema"
    ) in {"RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3", STANDARD_API_BINDING_SCHEMA}


def _uses_historical_activation_binding(receipt: Mapping[str, object]) -> bool:
    materialization_binding = receipt.get("materialization_binding")
    return type(materialization_binding) is dict and materialization_binding.get(
        "schema"
    ) in {
        "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V1",
        "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V2",
    }


def _replace_unregistered_terminal_attempt(
    client: Any,
    receipt: dict[str, object],
    path: Path,
    *,
    articles: Sequence[Article],
    desired_theme_tree_sha256: str,
    materialization_binding: Mapping[str, object],
    quality_audit_binding: Mapping[str, object] | None,
) -> None:
    """Read back a terminal unregistered legacy attempt before entering V3.

    An unregistered legacy set containing a theme proposal has no complete
    editor-side read-only proof, so it remains fail-closed.
    """

    proposals = receipt.get("proposals")
    if (
        type(proposals) is not list
        or len(proposals) != len(articles)
        or any(
            type(proposal) is not dict or proposal.get("kind") != "CONTENT_RELEASE"
            for proposal in proposals
        )
    ):
        fail("RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT")
    operations = read_content_operations(client, receipt)
    proposal_ids = set(_proposal_ids(receipt))
    if set(operations) != proposal_ids:
        fail("RAOS_WORDPRESS_REQUEST_OPERATION_READBACK_INVALID")
    states = {operation.get("state") for operation in operations.values()}
    if states not in ({"EXPIRED"}, {"APPLIED"}):
        fail("RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT")
    terminal_state = next(iter(states))

    preserved_baselines = receipt.get("baselines")
    preserved_drafts = receipt.get("drafts")
    prior_reconciliation = receipt.get("prior_applied_reconciliation")
    if (
        type(preserved_baselines) is not dict
        or type(preserved_drafts) is not dict
        or any(
            type(slug) is not str or type(value) is not dict
            for slug, value in preserved_drafts.items()
        )
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    preserved_baselines = dict(preserved_baselines)
    preserved_drafts = {slug: dict(value) for slug, value in preserved_drafts.items()}
    if terminal_state == "APPLIED":
        _require_applied_receipt_content_operations(receipt, operations)
        for proposal in proposals:
            slug = proposal.get("slug")
            after_sha256 = proposal.get("after_sha256")
            target = preserved_drafts.get(slug) if type(slug) is str else None
            if (
                type(target) is not dict
                or type(target.get("id")) is not int
                or type(after_sha256) is not str
                or SHA256_RE.fullmatch(after_sha256) is None
            ):
                fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
            target["content_sha256"] = after_sha256
        prior_reconciliation = {
            "schema": "RAOS_WORDPRESS_PRIOR_APPLIED_RECONCILIATION_V1",
            "captured_at_gmt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "documents": _published_receipt_document_evidence(client, receipt),
            "operations": operations,
        }

    replacement = _fresh_receipt(
        articles,
        path,
        desired_theme_tree_sha256,
        materialization_binding,
        quality_audit_binding,
    ) | {
        "baselines": preserved_baselines,
        "drafts": preserved_drafts,
        "prior_applied_reconciliation": prior_reconciliation,
    }
    receipt.clear()
    receipt.update(replacement)
    _touch_receipt(path, receipt, f"{terminal_state}_ATTEMPT_REPLACED")


def _register_unregistered_proposal_set(
    client: Any,
    receipt: dict[str, object],
    path: Path,
    *,
    articles: Sequence[Article],
    desired_theme_tree_sha256: str,
    activation: RakutenMeasurementActivationOverlayV3 | None,
    materialization_binding: Mapping[str, object] | None,
    quality_audit_binding: Mapping[str, object] | None,
) -> None:
    if not _unregistered_proposal_set_ready(receipt, len(articles)):
        return
    if activation is None:
        if not _same_desired(
            receipt,
            articles,
            desired_theme_tree_sha256,
            materialization_binding,
            quality_audit_binding,
        ):
            fail("RAOS_WORDPRESS_REQUEST_UNREGISTERED_BATCH_HANDOFF_REQUIRED")
        register_publication_batch(client, receipt, path)
        return
    if _uses_current_activation_binding(receipt):
        if not _same_desired(
            receipt,
            articles,
            desired_theme_tree_sha256,
            materialization_binding,
            quality_audit_binding,
        ):
            fail("RAOS_WORDPRESS_REQUEST_UNREGISTERED_BATCH_HANDOFF_REQUIRED")
        register_publication_batch(client, receipt, path)
        return
    if (
        not _uses_historical_activation_binding(receipt)
        or materialization_binding is None
    ):
        fail("RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT")
    _replace_unregistered_terminal_attempt(
        client,
        receipt,
        path,
        articles=articles,
        desired_theme_tree_sha256=desired_theme_tree_sha256,
        materialization_binding=materialization_binding,
        quality_audit_binding=quality_audit_binding,
    )


def _resume_existing_all_attempt(
    source_articles: Sequence[Article],
    loaded_receipt: dict[str, object] | None,
    path: Path,
    *,
    activation: PublicationOverlay | None = None,
    rakuten_activation_dry_run: Path | None = None,
    quality_audit_attestation: Path | None = None,
    quality_audit_signature: Path | None = None,
    quality_audit_mode: str = "signed-independent",
    codex_audit_report: Path | None = None,
    client_factory: Callable[[], Any],
    deployment_runner: Callable[..., subprocess.CompletedProcess[bytes]],
) -> bool:
    """Recover an active 10-article batch before any provider refresh.

    The proposal set and its materialized documents are immutable inputs to an
    interrupted operation. Re-capturing provider state first could change those
    inputs and make a separately approved batch impossible to reconcile.
    """

    if loaded_receipt is None:
        return False
    receipt = _validate_receipt(loaded_receipt, source_articles)
    # APPLIED is terminal evidence for the inputs captured by that receipt, not
    # proof that today's provider materialization and committed theme are still
    # identical. Only interrupted non-terminal batches may bypass a fresh
    # capture/preview cycle.
    if receipt.get("state") == "APPLIED":
        return False
    if not _resume_ready(receipt, len(source_articles)):
        return False
    historical_activation_binding = activation is not None and not (
        _uses_current_activation_binding(receipt)
    )
    batch = publication_batch_status(receipt, deployment_runner)
    if historical_activation_binding and batch["state"] not in {
        "APPLIED",
        "EXPIRED",
    }:
        # A pre-provider-slot receipt may be reconciled after exact APPLIED
        # readback or replaced after irreversible expiry. It can never resume
        # approval/application under the V3 attribution contract.
        fail("RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT")
    if batch["state"] == "EXPIRED":
        return False
    if batch["state"] == "FAILED":
        fail("RAOS_WORDPRESS_REQUEST_BATCH_STATUS_INVALID")
    if batch["state"] == "APPLIED":
        _require_applied_batch_ready(batch)
    articles: Sequence[Article] | None = None
    if batch["state"] != "APPLIED":
        _current_activation, articles, _binding, _quality = _revalidate_apply_inputs(
            receipt,
            rakuten_activation_dry_run=rakuten_activation_dry_run,
            expected_activation=activation,
            quality_audit_attestation=quality_audit_attestation,
            quality_audit_signature=quality_audit_signature,
            quality_audit_mode=quality_audit_mode,
            codex_audit_report=codex_audit_report,
        )

    client = client_factory()
    client.initialize()
    validate_tool_contract(client.tools())
    validate_site_status(
        client.call("raos-codex-site-status", {}),
        require_measurement_ready=not isinstance(
            activation, RakutenStandardApiOverlayV1
        ),
        require_measurement_off=isinstance(activation, RakutenStandardApiOverlayV1),
    )
    operations = read_content_operations(client, receipt)
    if batch["state"] == "APPLIED":
        _require_applied_receipt_content_operations(receipt, operations)
    wait_and_apply(
        receipt,
        path,
        deployment_runner,
        finalize_applied=batch["state"] == "APPLIED",
    )
    operations = read_content_operations(client, receipt)
    if batch["state"] == "APPLIED":
        _require_applied_receipt_content_operations(receipt, operations)
    elif any(operation.get("state") != "APPLIED" for operation in operations.values()):
        fail("RAOS_WORDPRESS_REQUEST_OPERATION_READBACK_INVALID")
    documents = (
        _published_receipt_document_evidence(client, receipt)
        if batch["state"] == "APPLIED"
        else _published_document_evidence(client, articles or (), receipt)
    )
    if batch["state"] == "APPLIED":
        _require_applied_batch_ready(
            publication_batch_status(receipt, deployment_runner)
        )
    receipt["prior_applied_reconciliation"] = {
        "schema": "RAOS_WORDPRESS_PRIOR_APPLIED_RECONCILIATION_V1",
        "captured_at_gmt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "documents": documents,
        "operations": operations,
    }
    # This terminal state belongs only to the old immutable attempt.  The same
    # foreground execution continues through fresh capture/preview. The normal
    # path either verifies an unchanged release or replaces a changed one.
    _touch_receipt(path, receipt, "APPLIED")
    return False


def execute(
    selection: str,
    *,
    measurement_plugin_apply_receipt: Path | None = None,
    rakuten_activation_dry_run: Path | None = None,
    link_mode: str = "measured-admin",
    standard_api_receipt: Path | None = None,
    quality_audit_attestation: Path | None = None,
    quality_audit_signature: Path | None = None,
    quality_audit_mode: str = "signed-independent",
    codex_audit_report: Path | None = None,
    portfolio_refresh: Callable[[], None] = run_editorial_portfolio_refresh,
    preview: Callable[[], None] = run_preview_checks,
    preview_fixture: Callable[[Path], None] | None = None,
    client_factory: Callable[[], Any] = EditorMcpClient,
    deployment_runner: Callable[
        ..., subprocess.CompletedProcess[bytes]
    ] = subprocess.run,
) -> Path:
    if selection != "all":
        # A production proposal is valid only for the exact portfolio whose
        # product evidence, images, Money Links, policy pages, theme and local
        # quality audit are bound by the all-mode receipts.  Historical narrow
        # requests used tracked source fixtures and therefore could bypass the
        # Owner-derived 33-product/37-image/74-CTA completion gate.
        fail("RAOS_WORDPRESS_REQUEST_COMPLETE_PORTFOLIO_REQUIRED")
    if link_mode not in {"standard-api", "measured-admin"}:
        fail("RAOS_WORDPRESS_REQUEST_LINK_MODE_INVALID")
    if link_mode == "standard-api":
        if (
            standard_api_receipt is None
            or rakuten_activation_dry_run is not None
            or measurement_plugin_apply_receipt is not None
        ):
            fail("RAOS_WORDPRESS_REQUEST_LINK_MODE_INVALID")
        rakuten_activation_dry_run = standard_api_receipt
    elif standard_api_receipt is not None:
        fail("RAOS_WORDPRESS_REQUEST_LINK_MODE_INVALID")
    require_measurement = link_mode == "measured-admin"
    activation: PublicationOverlay | None = None
    if selection == "all":
        # This owner-private, read-only validation is deliberately first. A
        # missing, insecure, partial, or drifted activation cannot create a
        # lock, refresh provider state, read credentials, or call WordPress.
        activation = validate_publication_link_evidence(
            rakuten_activation_dry_run,
            link_mode=link_mode,
            require_recent=False,
        )
        if require_measurement:
            validate_measurement_plugin_apply_receipt(measurement_plugin_apply_receipt)
        _require_quality_audit_inputs(
            quality_audit_attestation,
            quality_audit_signature,
            audit_mode=quality_audit_mode,
            codex_report_path=codex_audit_report,
        )
    with request_lock():
        initial_fixture_root = (
            activation.production_fixture_root
            if activation is not None
            else SOURCE_FIXTURE_ROOT
        )
        source_articles = load_publication_items(
            selection,
            article_fixture_root=initial_fixture_root,
        )
        initial_path = _receipt_path(source_articles)
        initial_receipt = _read_receipt(initial_path)
        if selection == "all" and _resume_existing_all_attempt(
            source_articles,
            initial_receipt,
            initial_path,
            activation=activation,
            rakuten_activation_dry_run=rakuten_activation_dry_run,
            quality_audit_attestation=quality_audit_attestation,
            quality_audit_signature=quality_audit_signature,
            quality_audit_mode=quality_audit_mode,
            codex_audit_report=codex_audit_report,
            client_factory=client_factory,
            deployment_runner=deployment_runner,
        ):
            return initial_path
        # Rakuten capture is local input acquisition. No WordPress credential
        # read, WordPress status call, draft write, or proposal happens until
        # the exact materialization survives local sync/check unchanged.
        fixture_root = SOURCE_FIXTURE_ROOT
        materialization_before_preview: dict[str, object] | None = None
        if selection == "all":
            assert activation is not None
            # V2 capture/materialization happened before the separately
            # attested activation dry-run. Re-running it here would mutate the
            # reviewed input and make the Money Link receipt stale.
            fixture_root = activation.production_fixture_root
        articles_before_preview = load_publication_items(
            selection,
            article_fixture_root=fixture_root,
        )
        if selection == "all":
            assert activation is not None
            materialization_before_preview = activation_materialization_binding(
                activation,
                [
                    article
                    for article in articles_before_preview
                    if article.post_type == "post"
                ],
                require_recent=True,
            )
        reviewed_article_hashes = {
            article.production_slug: article.desired_sha256()
            for article in articles_before_preview
        }
        theme_tree_before_preview = tracked_theme_tree_sha256()
        if activation is None:
            preview()
        elif preview_fixture is not None:
            preview_fixture(activation.local_fixture_root)
        elif preview is run_preview_checks:
            run_preview_checks(
                fixture_root=activation.local_fixture_root, link_mode=link_mode
            )
        else:
            # Compatibility for injected no-argument test/audit callbacks.
            preview()
        if activation is not None:
            activation_after_preview = validate_publication_link_evidence(
                rakuten_activation_dry_run,
                link_mode=link_mode,
                require_recent=True,
            )
            if activation_after_preview != activation:
                fail("RAOS_WORDPRESS_REQUEST_ARTICLE_CHANGED_DURING_PREVIEW")
        articles = load_publication_items(
            selection,
            article_fixture_root=fixture_root,
        )
        materialization_binding = (
            activation_materialization_binding(
                activation,
                [article for article in articles if article.post_type == "post"],
                require_recent=True,
            )
            if activation is not None
            else None
        )
        if {
            article.production_slug: article.desired_sha256() for article in articles
        } != reviewed_article_hashes or (
            materialization_binding != materialization_before_preview
        ):
            fail("RAOS_WORDPRESS_REQUEST_ARTICLE_CHANGED_DURING_PREVIEW")
        local_theme_version = theme_version()
        if local_theme_version != EXPECTED_THEME_VERSION:
            fail("RAOS_WORDPRESS_REQUEST_THEME_VERSION_INVALID")
        local_theme_runtime_revision = theme_runtime_revision()
        if local_theme_runtime_revision != EXPECTED_THEME_RUNTIME_REVISION:
            fail("RAOS_WORDPRESS_REQUEST_THEME_RUNTIME_REVISION_INVALID")
        local_theme_tree_sha256 = tracked_theme_tree_sha256()
        if local_theme_tree_sha256 != theme_tree_before_preview:
            fail("RAOS_WORDPRESS_REQUEST_THEME_CHANGED_DURING_PREVIEW")
        quality_audit_binding = (
            publication_quality_audit(
                quality_audit_attestation,
                quality_audit_signature,
                audit_mode=quality_audit_mode,
                codex_report_path=codex_audit_report,
            )
            if selection == "all"
            else None
        )
        path = _receipt_path(articles)
        loaded = _read_receipt(path)
        is_new_receipt = loaded is None
        receipt = (
            _fresh_receipt(
                articles,
                path,
                local_theme_tree_sha256,
                materialization_binding,
                quality_audit_binding,
            )
            if loaded is None
            else _validate_receipt(loaded, articles)
        )
        client = client_factory()
        client.initialize()
        tools = client.tools()
        validate_tool_contract(tools)
        status = client.call("raos-codex-site-status", {})
        validate_site_status(
            status,
            require_measurement_ready=require_measurement,
            require_measurement_off=not require_measurement,
        )
        live_theme = status["theme"]
        if type(live_theme) is not dict:
            fail("RAOS_WORDPRESS_REQUEST_SITE_NOT_READY")

        documents = list_all_documents(
            client,
            post_types=("post", "page") if selection == "all" else ("post",),
        )
        documents = capture_existing_baselines(
            client,
            articles,
            documents,
            receipt,
            path,
            require_existing_published=selection == "all",
        )

        _register_unregistered_proposal_set(
            client,
            receipt,
            path,
            articles=articles,
            desired_theme_tree_sha256=local_theme_tree_sha256,
            activation=activation,
            materialization_binding=materialization_binding,
            quality_audit_binding=quality_audit_binding,
        )

        desired_matches = _same_desired(
            receipt,
            articles,
            local_theme_tree_sha256,
            materialization_binding,
            quality_audit_binding,
        )
        desired_change_with_proposals = bool(
            not desired_matches and receipt.get("proposals")
        )
        if desired_change_with_proposals:
            # The receipt's creation-time expiry is not authoritative: human
            # approval extends server leases. Preserve the old attempt until the
            # exact remote batch proves that authority expired or every member
            # reached its exact applied readback.
            if type(receipt.get("batch_registration")) is not dict:
                fail("RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT")
        elif not desired_matches:
            receipt["desired_sha256"] = {
                article.production_slug: article.desired_sha256()
                for article in articles
            }
            receipt["desired_theme_tree_sha256"] = local_theme_tree_sha256
            receipt["desired_theme_runtime_revision"] = EXPECTED_THEME_RUNTIME_REVISION
            receipt["materialization_binding"] = materialization_binding
            receipt["quality_audit_binding"] = quality_audit_binding
            receipt["attempt_id"] = None
            receipt["attempt_created_at_gmt"] = None
            receipt["proposal_keys"] = {}
            receipt["proposals"] = []
            receipt["operation_ids"] = {}
            receipt["batch_registration"] = None
            receipt["apply_receipt"] = None
            receipt["authenticated_readback"] = None
            receipt["public_readback"] = None
            receipt["seo_audit_readback"] = None
        if is_new_receipt or (
            not desired_matches and not desired_change_with_proposals
        ):
            _touch_receipt(path, receipt, "LOCAL_VERIFIED")
        else:
            _atomic_receipt(path, receipt)

        if desired_change_with_proposals:
            old_batch = publication_batch_status(receipt, deployment_runner)
            terminal_state = old_batch["state"]
            if terminal_state not in {"EXPIRED", "APPLIED"}:
                fail("RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT")
            if terminal_state == "APPLIED":
                _require_applied_batch_ready(old_batch)
            preserved_drafts = receipt.get("drafts", {})
            preserved_baselines = receipt.get("baselines", {})
            prior_reconciliation = receipt.get("prior_applied_reconciliation")
            if terminal_state == "APPLIED":
                if type(preserved_drafts) is not dict:
                    fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
                preserved_drafts = {
                    slug: dict(value)
                    for slug, value in preserved_drafts.items()
                    if type(slug) is str and type(value) is dict
                }
                proposals = receipt.get("proposals")
                if type(proposals) is not list:
                    fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
                for proposal in proposals:
                    if (
                        type(proposal) is not dict
                        or proposal.get("kind") != "CONTENT_RELEASE"
                    ):
                        continue
                    slug = proposal.get("slug")
                    after_sha256 = proposal.get("after_sha256")
                    target = preserved_drafts.get(slug) if type(slug) is str else None
                    if (
                        type(target) is not dict
                        or type(target.get("id")) is not int
                        or type(after_sha256) is not str
                        or SHA256_RE.fullmatch(after_sha256) is None
                    ):
                        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
                    target["content_sha256"] = after_sha256
            receipt = _fresh_receipt(
                articles,
                path,
                local_theme_tree_sha256,
                materialization_binding,
                quality_audit_binding,
            ) | {
                "baselines": preserved_baselines,
                "drafts": preserved_drafts,
                "prior_applied_reconciliation": prior_reconciliation,
            }
            _touch_receipt(path, receipt, f"{terminal_state}_ATTEMPT_REPLACED")
            documents = capture_existing_baselines(
                client,
                articles,
                documents,
                receipt,
                path,
                require_existing_published=selection == "all",
            )
        deployed_before = deployment_status(deployment_runner)
        deployed_theme = deployed_before.get("theme")
        if type(deployed_theme) is not dict:
            fail("RAOS_WORDPRESS_REQUEST_DEPLOYMENT_STATUS_INVALID")
        include_theme = (
            deployed_theme.get("tree_sha256") != local_theme_tree_sha256
            or deployed_theme.get("version") != EXPECTED_THEME_VERSION
            or deployed_theme.get("runtime_version") != EXPECTED_THEME_VERSION
            or deployed_theme.get("runtime_revision") != EXPECTED_THEME_RUNTIME_REVISION
            or live_theme.get("version") != EXPECTED_THEME_VERSION
            or live_theme.get("runtime_version") != EXPECTED_THEME_VERSION
            or live_theme.get("runtime_revision") != EXPECTED_THEME_RUNTIME_REVISION
        )

        if _resume_ready(receipt, len(articles)):
            proposal_ids = _proposal_ids(receipt)
            proposals = receipt.get("proposals")
            if type(proposals) is not list or not proposal_ids:
                fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
            has_desired_theme = any(
                type(proposal) is dict
                and proposal.get("kind") == "THEME_RELEASE"
                and proposal.get("after_sha256") == local_theme_tree_sha256
                for proposal in proposals
            )
            if include_theme and not has_desired_theme:
                # A content-only approval batch cannot publish after the live
                # theme drifts away from the locally reviewed exact tree.
                fail("RAOS_WORDPRESS_REQUEST_PENDING_THEME_DRIFT")
            read_content_operations(client, receipt)
            _revalidate_apply_inputs(
                receipt,
                rakuten_activation_dry_run=rakuten_activation_dry_run,
                expected_activation=activation,
                quality_audit_attestation=quality_audit_attestation,
                quality_audit_signature=quality_audit_signature,
                quality_audit_mode=quality_audit_mode,
                codex_audit_report=codex_audit_report,
            )
            try:
                wait_and_apply(receipt, path, deployment_runner)
            except PublicationFailure as error:
                if str(error) != "WORDPRESS_MCP_RELEASE_EXPIRED":
                    raise
                # The remote operation state, not the receipt clock, decides
                # whether an interrupted apply succeeded. Only a confirmed
                # EXPIRED result permits a new proposal attempt.
                receipt["attempt_id"] = None
                receipt["attempt_created_at_gmt"] = None
                receipt["proposal_keys"] = {}
                receipt["proposals"] = []
                receipt["operation_ids"] = {}
                receipt["batch_registration"] = None
                receipt["apply_receipt"] = None
                receipt["authenticated_readback"] = None
                receipt["public_readback"] = None
                receipt["seo_audit_readback"] = None
                _touch_receipt(path, receipt, "EXPIRED_ATTEMPT_REPLACED")
            else:
                verify_published(
                    client,
                    articles,
                    receipt,
                    path,
                    expected_theme_version=local_theme_version,
                    expected_theme_tree_sha256=local_theme_tree_sha256,
                    theme_was_proposed=_theme_was_proposed(receipt, len(articles)),
                    require_measurement_ready=require_measurement,
                    deployment_runner=deployment_runner,
                )
                return path

        if receipt.get("attempt_id") is not None and _attempt_expired(receipt):
            receipt["attempt_id"] = None
            receipt["attempt_created_at_gmt"] = None
            receipt["proposal_keys"] = {}
            receipt["proposals"] = []
            receipt["operation_ids"] = {}
            receipt["batch_registration"] = None
            receipt["apply_receipt"] = None
            receipt["authenticated_readback"] = None
            receipt["public_readback"] = None
            receipt["seo_audit_readback"] = None
            _touch_receipt(path, receipt, "EXPIRED_ATTEMPT_REPLACED")

        drafts = reconcile_drafts(client, articles, documents, receipt, path)
        proposals = create_proposals(
            client,
            articles,
            drafts,
            include_theme,
            receipt,
            path,
            deployment_runner,
        )
        if len(proposals) != len(articles) + (1 if include_theme else 0):
            fail("RAOS_WORDPRESS_REQUEST_PROPOSAL_SET_INVALID")
        register_publication_batch(client, receipt, path)
        _revalidate_apply_inputs(
            receipt,
            rakuten_activation_dry_run=rakuten_activation_dry_run,
            expected_activation=activation,
            quality_audit_attestation=quality_audit_attestation,
            quality_audit_signature=quality_audit_signature,
            quality_audit_mode=quality_audit_mode,
            codex_audit_report=codex_audit_report,
        )
        wait_and_apply(receipt, path, deployment_runner)
        verify_published(
            client,
            articles,
            receipt,
            path,
            expected_theme_version=local_theme_version,
            expected_theme_tree_sha256=local_theme_tree_sha256,
            theme_was_proposed=include_theme,
            require_measurement_ready=require_measurement,
            deployment_runner=deployment_runner,
        )
        return path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(allow_abbrev=False)
    result.add_argument(
        "--quality-audit-mode",
        choices=("signed-independent", "codex-owner"),
        default="signed-independent",
        help="explicit audit policy; neither mode replaces wp-admin approval",
    )
    result.add_argument("--codex-audit-report", type=Path)
    result.add_argument(
        "--link-mode",
        choices=("standard-api", "measured-admin"),
        default="measured-admin",
    )
    result.add_argument("--standard-api-receipt", type=Path)
    result.add_argument(
        "--articles",
        default=os.environ.get("ARTICLES", "all"),
        help="all (default) or a comma-separated list of exact production slugs",
    )
    result.add_argument(
        "--measurement-plugin-apply-receipt",
        type=Path,
        default=(
            Path(os.environ["MEASUREMENT_PLUGIN_APPLY_RECEIPT"])
            if os.environ.get("MEASUREMENT_PLUGIN_APPLY_RECEIPT")
            else None
        ),
        help=(
            "absolute owner-private OperationReceiptV1 from the separately "
            "approved measurement plugin apply; required in measured-admin mode"
        ),
    )
    result.add_argument(
        "--rakuten-activation-dry-run",
        type=Path,
        default=(
            Path(os.environ["RAKUTEN_ACTIVATION_DRY_RUN"])
            if os.environ.get("RAKUTEN_ACTIVATION_DRY_RUN")
            else None
        ),
        help=(
            "absolute owner-private URL-free Editorial V3 activation dry-run; "
            "required in measured-admin mode"
        ),
    )
    result.add_argument(
        "--quality-audit-attestation",
        type=Path,
        default=(
            Path(os.environ["QUALITY_AUDIT_ATTESTATION"])
            if os.environ.get("QUALITY_AUDIT_ATTESTATION")
            else None
        ),
        help=(
            "absolute owner-private canonical independent-reviewer attestation; "
            "required with --quality-audit-signature for --articles all"
        ),
    )
    result.add_argument(
        "--quality-audit-signature",
        type=Path,
        default=(
            Path(os.environ["QUALITY_AUDIT_SIGNATURE"])
            if os.environ.get("QUALITY_AUDIT_SIGNATURE")
            else None
        ),
        help=(
            "absolute owner-private detached Ed25519 signature for the quality "
            "audit attestation; required with --quality-audit-attestation"
        ),
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = parser().parse_args(argv)
        path = execute(
            arguments.articles,
            measurement_plugin_apply_receipt=(
                arguments.measurement_plugin_apply_receipt
            ),
            rakuten_activation_dry_run=arguments.rakuten_activation_dry_run,
            link_mode=arguments.link_mode,
            standard_api_receipt=arguments.standard_api_receipt,
            quality_audit_attestation=arguments.quality_audit_attestation,
            quality_audit_signature=arguments.quality_audit_signature,
            quality_audit_mode=arguments.quality_audit_mode,
            codex_audit_report=arguments.codex_audit_report,
        )
        print("公開と本番read-backが完了しました。")
        print(f"受領書: {path}")
        return 0
    except KeyboardInterrupt:
        sys.stderr.write("RAOS_WORDPRESS_REQUEST_INTERRUPTED\n")
        return 130
    except PublicationFailure as error:
        sys.stderr.write(str(error) + "\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
