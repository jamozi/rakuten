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


ROOT: Final = Path(__file__).resolve().parents[1]
PREVIEW_ROOT: Final = ROOT / "changes/wordpress-local-preview-v1"
SOURCE_FIXTURE_ROOT: Final = PREVIEW_ROOT / "fixtures"
FIXTURE_PATH: Final = SOURCE_FIXTURE_ROOT / "posts.json"
PAGES_FIXTURE_PATH: Final = SOURCE_FIXTURE_ROOT / "pages.json"
MAPPING_PATH: Final = PREVIEW_ROOT / "production-mapping.v1.json"
PORTFOLIO_SCRIPT: Final = ROOT / "scripts/raos_editorial_portfolio_v2.py"
PORTFOLIO_PRIVATE_ROOT: Final = ROOT / ".secrets/editorial-portfolio-v2"
PREVIEW_PRIVATE_ROOT: Final = ROOT / ".secrets/wordpress-local-preview"
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
ORIGIN: Final = "https://kurashinoshirube.com"
EXPECTED_SOCIAL_IMAGE_URL: Final = (
    f"{ORIGIN}/wp-content/themes/kurashinoshirube-child/"
    "assets/images/home-hero.webp"
)
EDITOR_ENDPOINT: Final = f"{ORIGIN}/wp-json/raos-codex-mcp/v1/editor"
REVIEW_URL: Final = f"{ORIGIN}/wp-admin/tools.php?page=raos-codex-proposals"
EDITOR_CREDENTIAL_PATH: Final = (
    ROOT / ".secrets/wordpress-mcp/editor-application-password.v1.json"
)
PRIVATE_REQUEST_DIRECTORY: Final = ROOT / ".secrets/wordpress-mcp/publication-requests"
NODE_BIN: Final = Path("/home/minami/.nvm/versions/node/v24.18.1/bin/node")
DEPLOYMENT_BRIDGE: Final = ROOT / "packages/wordpress-mcp-bridge/src/index.ts"
MAKE_BIN: Final = Path("/usr/bin/make")
SG_BIN: Final = Path("/usr/bin/sg")
DOCKER_SOCKET: Final = Path("/var/run/docker.sock")
PROTOCOL_VERSION: Final = "2025-11-25"
EXPECTED_PLUGIN_VERSION: Final = "1.3.0"
EXPECTED_THEME_VERSION: Final = "1.4.0"
EXPECTED_ALL_ARTICLE_COUNT: Final = 10
EXPECTED_POLICY_PAGE_COUNT: Final = 3
MAX_PUBLICATION_PROPOSALS: Final = 14
MAX_CONTENT_BYTES: Final = 1024 * 1024
MAX_RESPONSE_BYTES: Final = 16 * 1024 * 1024
MAX_PUBLIC_PAGE_BYTES: Final = 4 * 1024 * 1024
MAX_RECEIPT_BYTES: Final = 4 * 1024 * 1024
MAX_THEME_PACKAGE_BYTES: Final = 32 * 1024 * 1024
MAX_THEME_FILE_BYTES: Final = 8 * 1024 * 1024
MAX_THEME_FILE_COUNT: Final = 2048
LIST_PER_PAGE: Final = 10
MAX_LIST_DOCUMENTS: Final = 10_000
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
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
        self.theme_stylesheets: set[tuple[str, str]] = set()
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
                match = re.search(
                    r"/wp-content/themes/kurashinoshirube-child/assets/"
                    r"(theme|editorial-v2)\.css\?ver=([^&#]+)",
                    href,
                )
                if match is not None:
                    self.theme_stylesheets.add(
                        (f"{match.group(1)}.css", match.group(2))
                    )
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
                    "product_id": attributes.get("data-raos-product-id"),
                    "placement": attributes.get("data-raos-placement"),
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
            self._heading_tag = lowered
            self._heading_parts = []
        if lowered not in self._VOID_ELEMENTS:
            self._elements.append((lowered, product_id, in_disclosure))

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == self._heading_tag:
            heading = _normalized_public_text(self._heading_parts)
            if heading:
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
    *, fixture_root: Path = SOURCE_FIXTURE_ROOT
) -> list[Article]:
    """Load the three tracked policy pages as exact publication documents."""

    if not fixture_root.is_absolute():
        fail("RAOS_WORDPRESS_REQUEST_FIXTURE_INVALID")
    page_directory = fixture_root / "pages"
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
            fixture_root / "pages.json",
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
        fixture.get("schema") != "RAOS_WORDPRESS_LOCAL_PREVIEW_PAGES_V1"
        or type(raw_pages) is not list
        or type(raw_mappings) is not list
        or len(raw_pages) != EXPECTED_POLICY_PAGE_COUNT
        or len(raw_mappings) != EXPECTED_POLICY_PAGE_COUNT
    ):
        fail("RAOS_WORDPRESS_REQUEST_PAGE_FIXTURE_INVALID")
    mapping_by_slug: dict[str, tuple[str, ...]] = {}
    for raw_mapping in raw_mappings:
        row = exact_object(raw_mapping, {"production_slug", "required_key_content"})
        slug = row.get("production_slug")
        key_content = row.get("required_key_content")
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
            or content_file != f"pages/{slug}.html"
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
    items = [*articles, *load_policy_pages(fixture_root=page_fixture_root)]
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
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            fail(code)
        if completed.returncode != 0:
            fail(code)


def production_materialization_binding(
    articles: Sequence[Article],
    *,
    require_recent: bool = True,
) -> dict[str, object]:
    """Bind publication to stable, private provider/materialization evidence."""

    try:
        metadata = PRODUCTION_MATERIALIZATION_RECEIPT.lstat()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
    if (
        PRODUCTION_MATERIALIZATION_RECEIPT.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
    document = exact_object(
        load_json(
            PRODUCTION_MATERIALIZATION_RECEIPT,
            MAX_RECEIPT_BYTES,
            "RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID",
        ),
        {
            "schema",
            "mode",
            "generated_at",
            "portfolio_sha256",
            "evidence_status_sha256",
            "articles",
            "products",
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
    if (
        document["schema"] != "RAOS_EDITORIAL_PORTFOLIO_MATERIALIZATION_RECEIPT_V2"
        or document["mode"] != "production"
        or type(document["portfolio_sha256"]) is not str
        or SHA256_RE.fullmatch(document["portfolio_sha256"]) is None
        or type(document["evidence_status_sha256"]) is not str
        or SHA256_RE.fullmatch(document["evidence_status_sha256"]) is None
        or document["evidence_status_sha256"] == "0" * 64
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
            or state not in {"verified", "not_found", "ambiguous", "expired"}
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
            for cta in _validated_ctas(parser)
            if type(cta.get("product_id")) is str
        )
    if set(product_bindings) != expected_product_ids:
        fail("RAOS_WORDPRESS_REQUEST_PRODUCTION_MATERIALIZATION_INVALID")
    _validate_local_materialization_pair(
        document,
        require_recent=require_recent,
    )
    return {
        "schema": "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V1",
        "portfolio_sha256": document["portfolio_sha256"],
        "articles": dict(sorted(article_hashes.items())),
        "products": {
            product_id: product_bindings[product_id]
            for product_id in sorted(product_bindings)
        },
    }


def _validate_local_materialization_pair(
    production: Mapping[str, object],
    *,
    require_recent: bool,
) -> None:
    """Prove that preview and proposal variants came from one evidence set."""

    try:
        metadata = LOCAL_MATERIALIZATION_RECEIPT.lstat()
    except OSError:
        fail("RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID")
    if (
        LOCAL_MATERIALIZATION_RECEIPT.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        fail("RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID")
    local = exact_object(
        load_json(
            LOCAL_MATERIALIZATION_RECEIPT,
            MAX_RECEIPT_BYTES,
            "RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID",
        ),
        {
            "schema",
            "mode",
            "generated_at",
            "portfolio_sha256",
            "evidence_status_sha256",
            "articles",
            "products",
        },
    )
    generated_at = local["generated_at"]
    if type(generated_at) is not str:
        fail("RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID")
    try:
        generated = datetime.strptime(
            generated_at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
    except TypeError, ValueError:
        fail("RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID")
    now = datetime.now(UTC)
    production_articles = production.get("articles")
    production_products = production.get("products")
    if (
        local["schema"] != "RAOS_EDITORIAL_PORTFOLIO_MATERIALIZATION_RECEIPT_V2"
        or local["mode"] != "local"
        or generated > now + timedelta(seconds=30)
        or (require_recent and now - generated > timedelta(minutes=15))
        or local["portfolio_sha256"] != production.get("portfolio_sha256")
        or local["evidence_status_sha256"]
        != production.get("evidence_status_sha256")
        or local["products"] != production_products
        or type(local["articles"]) is not list
        or type(production_articles) is not list
        or len(local["articles"]) != EXPECTED_ALL_ARTICLE_COUNT
    ):
        fail("RAOS_WORDPRESS_REQUEST_LOCAL_MATERIALIZATION_INVALID")
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
) -> None:
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
                    "RAOS_WORDPRESS_PREVIEW_FIXTURE_ROOT": (
                        LOCAL_MATERIALIZED_FIXTURE_ROOT.as_posix()
                    ),
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


def validate_site_status(status: Mapping[str, object]) -> None:
    writes = status.get("writes_enabled")
    theme = status.get("theme")
    server = status.get("server")
    authorization = status.get("apply_authorization")
    if (
        status.get("schema") != "RAOSWordPressSiteStatusV1"
        or status.get("origin") != ORIGIN
        or status.get("wordpress_version_compatible") is not True
        or status.get("mcp_adapter_version") != "0.6.1"
        or status.get("mcp_adapter_version_compatible") is not True
        or status.get("plugin_version") != EXPECTED_PLUGIN_VERSION
        or type(writes) is not dict
        or any(
            writes.get(name) is not True
            for name in ("global", "draft", "content_apply", "theme_apply")
        )
        or type(theme) is not dict
        or theme.get("slug") != "kurashinoshirube-child"
        or theme.get("exists") is not True
        or theme.get("active") is not True
        or type(theme.get("version")) is not str
        or authorization
        != {
            "mode": "approval_scoped_lease",
            "default": False,
            "single_use": True,
            "ttl_seconds": 900,
        }
        or type(server) is not dict
        or server.get("endpoint") != EDITOR_ENDPOINT
        or server.get("publish_tool_exposed") is not False
        or server.get("delete_tool_exposed") is not False
        or server.get("media_write_tool_exposed") is not False
        or server.get("proposal_ttl_seconds") != 900
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
        "state": "LOCAL_VERIFIED",
        "attempt_id": None,
        "attempt_created_at_gmt": None,
        "materialization_binding": (
            dict(materialization_binding)
            if materialization_binding is not None
            else None
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
        "public_readback": None,
        "updated_at_gmt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _validate_materialization_binding(value: object) -> None:
    if value is None:
        return
    if type(value) is not dict or set(value) != {
        "schema",
        "portfolio_sha256",
        "articles",
        "products",
    }:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    articles = value.get("articles")
    products = value.get("products")
    if (
        value.get("schema") != "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V1"
        or type(value.get("portfolio_sha256")) is not str
        or SHA256_RE.fullmatch(value["portfolio_sha256"]) is None
        or type(articles) is not dict
        or len(articles) != EXPECTED_ALL_ARTICLE_COUNT
        or type(products) is not dict
        or not products
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
    for product_id, raw in products.items():
        if (
            type(product_id) is not str
            or not re.fullmatch(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*", product_id)
            or type(raw) is not dict
            or set(raw) != {"state", "provider_binding_sha256"}
            or raw.get("state") not in {"verified", "not_found", "ambiguous", "expired"}
            or type(raw.get("provider_binding_sha256")) is not str
            or SHA256_RE.fullmatch(raw["provider_binding_sha256"]) is None
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
            "materialization_binding",
            "operation_ids",
            "public_readback",
            "selected_documents",
        },
    )
    receipt.setdefault("authenticated_readback", None)
    receipt.setdefault("baselines", {})
    receipt.setdefault("materialization_binding", None)
    receipt.setdefault("operation_ids", {})
    receipt.setdefault("public_readback", None)
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
        or receipt["review_url"] != REVIEW_URL
        or type(receipt["state"]) is not str
    ):
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    _validate_materialization_binding(receipt["materialization_binding"])
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
        if len(candidates) > 1:
            fail("RAOS_WORDPRESS_REQUEST_SLUG_CONFLICT")
        prior = baselines.get(slug)
        if not candidates:
            if prior is not None or require_existing_published:
                fail("RAOS_WORDPRESS_REQUEST_UNKNOWN_BASELINE_DRIFT")
            continue
        listed_document = candidates[0]
        if require_existing_published and listed_document.get("status") != "publish":
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
        or batch_status_properties != wait_properties
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
        or response.get("private_directory_ready") is not True
        or type(theme) is not dict
        or theme.get("slug") != "kurashinoshirube-child"
        or theme.get("active") is not True
        or type(theme.get("version")) is not str
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
            "ttl_seconds": 900,
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
        return datetime.now(UTC) >= created_at + timedelta(seconds=930)
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


def wait_and_apply(
    receipt: dict[str, object],
    path: Path,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
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
    print("\nWordPress管理画面で内容を確認し、「一括承認」を押してください。")
    print(f"承認対象バッチtoken末尾12文字: {batch_token[-12:]}")
    print(f"入力するbatch manifest hash末尾8文字: {manifest_hash[-8:]}")
    print(REVIEW_URL)
    print("承認待機中です。このコマンドは閉じないでください。", flush=True)
    _touch_receipt(path, receipt, "WAITING_FOR_APPROVAL")
    aggregate = _deployment_mcp_call(
        "release-wait-and-apply",
        {
            "batch_token": batch_token,
            "batch_manifest_sha256": manifest_hash,
            "proposal_ids": proposal_ids,
        },
        timeout=1080,
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
    for proposal_id, operation in zip(
        expected_order, aggregate_receipts, strict=True
    ):
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


def _validated_ctas(parser: _PublicPageEvidenceParser) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    identities: set[tuple[str, str]] = set()
    placements_by_product: dict[str, set[str]] = {}
    for raw in parser.ctas:
        href = raw.get("href")
        rel = raw.get("rel")
        article_id = raw.get("article_id")
        product_id = raw.get("product_id")
        placement = raw.get("placement")
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
            if set(rel) != {"sponsored", "nofollow"}:
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
                "product_id": product_id,
                "placement": placement,
            }
        )
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
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
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
    expected_og = {
        "og:title": [article.title],
        "og:description": [article.excerpt],
        "og:url": [url],
        "og:image": [EXPECTED_SOCIAL_IMAGE_URL],
    }
    image = urlsplit(EXPECTED_SOCIAL_IMAGE_URL)
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
    common_invalid = (
        response_noindex
        or parser.noindex
        or parser.canonical_urls != [url]
        or len(parser.page_titles) != 1
        or article.title not in parser.page_titles[0]
        or parser.h1_titles != [article.title]
        or not required_headings
        or parser.heading_outline
        != [("h1", article.title), *desired.heading_outline]
        or any(heading not in visible for heading in required_headings)
        or parser.theme_stylesheets
        != {
            ("theme.css", EXPECTED_THEME_VERSION),
            ("editorial-v2.css", EXPECTED_THEME_VERSION),
        }
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
            common_invalid
            or any(value not in visible for value in article.required_key_content)
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
            **head_evidence,
        }
    expected_ctas = _validated_ctas(desired)
    actual_ctas = _validated_ctas(parser)
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
        common_invalid
        or expected_ctas != actual_ctas
        or expected_images != actual_images
        or "広告を含みます" not in expected_disclosure
        or expected_disclosure != actual_disclosure
    ):
        fail("RAOS_WORDPRESS_REQUEST_PUBLIC_READBACK_FAILED")
    return {
        "url": url,
        "status": 200,
        "canonical_url": parser.canonical_urls[0],
        "indexable": True,
        "title": parser.page_titles[0],
        "heading_count": len(required_headings),
        "ctas": actual_ctas,
        "product_images": actual_images,
        "advertising_disclosure": actual_disclosure,
        "theme_version": EXPECTED_THEME_VERSION,
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
    for article in articles:
        last_error: PublicationFailure | None = None
        for attempt in range(attempts):
            try:
                evidence[article.production_slug] = _public_page_evidence(
                    article,
                    public_opener,
                    authorization=authorization,
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


def verify_published(
    client: Any,
    articles: Sequence[Article],
    receipt: dict[str, object],
    path: Path,
    *,
    expected_theme_version: str,
    expected_theme_tree_sha256: str,
    theme_was_proposed: bool,
    deployment_runner: Callable[..., subprocess.CompletedProcess[bytes]],
) -> None:
    drafts = receipt.get("drafts")
    if type(drafts) is not dict:
        fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
    document_evidence: dict[str, object] = {}
    for article in articles:
        draft = drafts.get(article.production_slug)
        if type(draft) is not dict or type(draft.get("id")) is not int:
            fail("RAOS_WORDPRESS_REQUEST_RECEIPT_INVALID")
        document = client.call("raos-codex-content-get", {"id": draft["id"]})
        if (
            document.get("status") != "publish"
            or document_projection(document) != article.document()
            or document.get("content_sha256")
            != _content_after_sha256(article.document(), draft["id"])
        ):
            fail("RAOS_WORDPRESS_REQUEST_PUBLISH_READBACK_FAILED")
        condition = precondition(document)
        document_evidence[article.production_slug] = {
            "id": draft["id"],
            "slug": article.production_slug,
            "post_type": article.post_type,
            "status": "publish",
            **condition,
        }
    status = client.call("raos-codex-site-status", {})
    validate_site_status(status)
    theme = status.get("theme")
    if (
        type(theme) is not dict
        or theme.get("version") != expected_theme_version
        or expected_theme_version != EXPECTED_THEME_VERSION
    ):
        fail("RAOS_WORDPRESS_REQUEST_THEME_READBACK_FAILED")
    deployed = deployment_status(deployment_runner)
    deployed_theme = deployed.get("theme")
    if (
        type(deployed_theme) is not dict
        or deployed_theme.get("version") != expected_theme_version
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
            "tree_sha256": expected_theme_tree_sha256,
            "proposed": theme_was_proposed,
        },
    }
    receipt["public_readback"] = verify_public_pages(articles)
    _touch_receipt(path, receipt, "APPLIED")


def _same_desired(
    receipt: Mapping[str, object],
    articles: Sequence[Article],
    desired_theme_tree_sha256: str,
    materialization_binding: Mapping[str, object] | None,
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
    )


def _resume_ready(receipt: Mapping[str, object], expected_count: int) -> bool:
    proposals = receipt.get("proposals")
    return (
        receipt.get("state")
        in {"BATCH_REGISTERED", "WAITING_FOR_APPROVAL", "APPLY_RETURNED", "APPLIED"}
        and type(proposals) is list
        and len(proposals) in {expected_count, expected_count + 1}
        and type(receipt.get("batch_registration")) is dict
    )


def _theme_was_proposed(
    receipt: Mapping[str, object], content_count: int
) -> bool:
    proposals = receipt.get("proposals")
    return type(proposals) is list and len(proposals) == content_count + 1


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


def _resume_existing_all_attempt(
    source_articles: Sequence[Article],
    loaded_receipt: dict[str, object] | None,
    path: Path,
    *,
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
    batch = publication_batch_status(receipt, deployment_runner)
    if batch["state"] == "EXPIRED":
        return False
    if batch["state"] == "FAILED":
        fail("RAOS_WORDPRESS_REQUEST_BATCH_STATUS_INVALID")
    articles = load_publication_items(
        "all",
        article_fixture_root=PRODUCTION_MATERIALIZED_FIXTURE_ROOT,
    )
    binding = production_materialization_binding(
        [article for article in articles if article.post_type == "post"],
        require_recent=False,
    )
    desired_tree = receipt.get("desired_theme_tree_sha256")
    if (
        type(desired_tree) is not str
        or SHA256_RE.fullmatch(desired_tree) is None
        or not _same_desired(receipt, articles, desired_tree, binding)
    ):
        fail("RAOS_WORDPRESS_REQUEST_PENDING_REQUEST_CONFLICT")

    client = client_factory()
    client.initialize()
    validate_tool_contract(client.tools())
    validate_site_status(client.call("raos-codex-site-status", {}))
    read_content_operations(client, receipt)
    if batch["state"] != "APPLIED":
        wait_and_apply(receipt, path, deployment_runner)
    verify_published(
        client,
        articles,
        receipt,
        path,
        expected_theme_version=EXPECTED_THEME_VERSION,
        expected_theme_tree_sha256=desired_tree,
        theme_was_proposed=_theme_was_proposed(receipt, len(articles)),
        deployment_runner=deployment_runner,
    )
    return True


def execute(
    selection: str,
    *,
    portfolio_refresh: Callable[[], None] = run_editorial_portfolio_refresh,
    preview: Callable[[], None] = run_preview_checks,
    client_factory: Callable[[], Any] = EditorMcpClient,
    deployment_runner: Callable[
        ..., subprocess.CompletedProcess[bytes]
    ] = subprocess.run,
) -> Path:
    with request_lock():
        source_articles = load_publication_items(
            selection,
            article_fixture_root=SOURCE_FIXTURE_ROOT,
        )
        initial_path = _receipt_path(source_articles)
        initial_receipt = _read_receipt(initial_path)
        if selection == "all" and _resume_existing_all_attempt(
            source_articles,
            initial_receipt,
            initial_path,
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
            # Capture and both materializations run in the foreground. The local
            # variant is what preview sync/check consumes; proposals use the
            # separate production variant with provider image URLs.
            portfolio_refresh()
            fixture_root = PRODUCTION_MATERIALIZED_FIXTURE_ROOT
        articles_before_preview = load_publication_items(
            selection,
            article_fixture_root=fixture_root,
        )
        if selection == "all":
            materialization_before_preview = production_materialization_binding(
                [
                    article
                    for article in articles_before_preview
                    if article.post_type == "post"
                ]
            )
        reviewed_article_hashes = {
            article.production_slug: article.desired_sha256()
            for article in articles_before_preview
        }
        theme_tree_before_preview = tracked_theme_tree_sha256()
        preview()
        articles = load_publication_items(
            selection,
            article_fixture_root=fixture_root,
        )
        materialization_binding = (
            production_materialization_binding(
                [article for article in articles if article.post_type == "post"]
            )
            if selection == "all"
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
        local_theme_tree_sha256 = tracked_theme_tree_sha256()
        if local_theme_tree_sha256 != theme_tree_before_preview:
            fail("RAOS_WORDPRESS_REQUEST_THEME_CHANGED_DURING_PREVIEW")
        path = _receipt_path(articles)
        loaded = _read_receipt(path)
        is_new_receipt = loaded is None
        receipt = (
            _fresh_receipt(
                articles,
                path,
                local_theme_tree_sha256,
                materialization_binding,
            )
            if loaded is None
            else _validate_receipt(loaded, articles)
        )

        client = client_factory()
        client.initialize()
        tools = client.tools()
        validate_tool_contract(tools)
        status = client.call("raos-codex-site-status", {})
        validate_site_status(status)
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

        if _unregistered_proposal_set_ready(receipt, len(articles)):
            # Reconcile a potentially lost registration response before
            # comparing against newly edited local inputs. The exact reviewed
            # old proposal set must first regain its authoritative batch token.
            register_publication_batch(client, receipt, path)

        desired_matches = _same_desired(
            receipt,
            articles,
            local_theme_tree_sha256,
            materialization_binding,
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
            receipt["materialization_binding"] = materialization_binding
            receipt["attempt_id"] = None
            receipt["attempt_created_at_gmt"] = None
            receipt["proposal_keys"] = {}
            receipt["proposals"] = []
            receipt["operation_ids"] = {}
            receipt["batch_registration"] = None
            receipt["apply_receipt"] = None
            receipt["authenticated_readback"] = None
            receipt["public_readback"] = None
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
            preserved_drafts = receipt.get("drafts", {})
            preserved_baselines = receipt.get("baselines", {})
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
            ) | {
                "baselines": preserved_baselines,
                "drafts": preserved_drafts,
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
        wait_and_apply(receipt, path, deployment_runner)
        verify_published(
            client,
            articles,
            receipt,
            path,
            expected_theme_version=local_theme_version,
            expected_theme_tree_sha256=local_theme_tree_sha256,
            theme_was_proposed=include_theme,
            deployment_runner=deployment_runner,
        )
        return path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(allow_abbrev=False)
    result.add_argument(
        "--articles",
        default=os.environ.get("ARTICLES", "all"),
        help="all (default) or a comma-separated list of exact production slugs",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = parser().parse_args(argv)
        path = execute(arguments.articles)
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
