#!/usr/bin/env python3
"""Run the bounded, read-only WordPress SEO public-surface audit."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
from typing import Any, Final, NoReturn, Protocol
from urllib.parse import urlsplit
from uuid import UUID
import xml.etree.ElementTree as ET


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.google_live import (  # noqa: E402
    FixedOwnerPrivateAnalyticsSiteBindings,
    GoogleServiceAccountAuthorizedTransport,
    LiveSearchConsoleUrlInspectionProvider,
    SystemGoogleImportClock,
    SystemGoogleRetrySleeper,
)
from raos.application.analytics.google_live_projection import (  # noqa: E402
    gsc_url_inspection_document,
)
from raos.domain.analytics.google_live import (  # noqa: E402
    GoogleProviderFailure,
    SearchConsoleUrlInspectionQuery,
    gsc_url_inspection_request_sha256,
    normalize_url_inspection_state,
)

CONTRACT_PATH: Final = REPO_ROOT / (
    "changes/wordpress-seo-audit-v1/seo-audit-contract.v1.json"
)
PRIVATE_ROOT: Final = REPO_ROOT / ".secrets/wordpress-seo-audit-v1"
DEFAULT_OUTPUT: Final = PRIVATE_ROOT / "report.json"
DEFAULT_GOOGLE_PRIVATE_ROOT: Final = REPO_ROOT / ".secrets/editorial-portfolio-v3"
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_UTC_RE: Final = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z\Z", re.ASCII
)
_ALLOWED_INDEX_STATES: Final = frozenset(
    {"INDEXED", "NOT_INDEXED", "BLOCKED", "UNKNOWN"}
)


class AuditError(RuntimeError):
    """Fail-closed audit error with a non-sensitive code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise AuditError(code) from None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _valid_utc_text(value: object) -> bool:
    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is timezone.utc


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _load_json(path: Path, maximum_bytes: int = 4 * 1024 * 1024) -> Any:
    try:
        if path.is_symlink() or not path.is_file():
            _fail("INPUT_NOT_REGULAR_FILE")
        if path.stat().st_size > maximum_bytes:
            _fail("INPUT_TOO_LARGE")
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError, UnicodeError, json.JSONDecodeError:
        _fail("INPUT_INVALID_JSON")


def _clean_url(origin: str, path: str) -> str:
    if not path.startswith("/") or "?" in path or "#" in path or "\\" in path:
        _fail("INVENTORY_PATH_INVALID")
    value = origin + path
    parts = urlsplit(value)
    if parts.scheme != "https" or parts.query or parts.fragment:
        _fail("INVENTORY_URL_INVALID")
    return value


@dataclass(frozen=True)
class InventoryItem:
    url: str
    role: str
    identifier: str


@dataclass(frozen=True)
class AuditContract:
    origin: str
    items: tuple[InventoryItem, ...]
    content_urls: frozenset[str]
    required_types: dict[str, frozenset[str]]
    forbidden_types: frozenset[str]
    robots_url: str
    sitemap_seed_url: str
    llms_url: str
    connect_timeout: int
    read_timeout: int
    maximum_bytes: int
    maximum_sitemaps: int
    user_agent: str
    contract_sha256: str
    portfolio_sha256: str


def load_contract() -> AuditContract:
    raw_bytes = CONTRACT_PATH.read_bytes()
    raw = _load_json(CONTRACT_PATH)
    if not isinstance(raw, dict) or raw.get("schema") != (
        "RAOS_WORDPRESS_SEO_AUDIT_CONTRACT_V1"
    ):
        _fail("CONTRACT_SCHEMA_INVALID")
    origin = raw.get("origin")
    if origin != "https://kurashinoshirube.com":
        _fail("CONTRACT_ORIGIN_INVALID")
    inventory = raw.get("inventory")
    if not isinstance(inventory, dict):
        _fail("CONTRACT_INVENTORY_INVALID")
    article_source = inventory.get("article_source")
    if not isinstance(article_source, str):
        _fail("CONTRACT_ARTICLE_SOURCE_INVALID")
    source_path = (REPO_ROOT / article_source).resolve()
    try:
        source_path.relative_to(REPO_ROOT)
    except ValueError:
        _fail("CONTRACT_ARTICLE_SOURCE_INVALID")
    portfolio_bytes = source_path.read_bytes()
    portfolio = _load_json(source_path)
    articles = portfolio.get("articles") if isinstance(portfolio, dict) else None
    if not isinstance(articles, list) or len(articles) != inventory.get(
        "article_count"
    ):
        _fail("ARTICLE_COUNT_INVALID")
    if len(articles) != 10:
        _fail("ARTICLE_COUNT_INVALID")

    home_path = inventory.get("home_path")
    if home_path != "/":
        _fail("HOME_PATH_INVALID")
    items: list[InventoryItem] = [
        InventoryItem(_clean_url(origin, "/"), "home", "home")
    ]
    article_urls: set[str] = set()
    article_codes: set[str] = set()
    for article in articles:
        if not isinstance(article, dict):
            _fail("ARTICLE_INVALID")
        slug = article.get("production_slug")
        code = article.get("article_code")
        if (
            not isinstance(slug, str)
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)
            or not isinstance(code, str)
            or not re.fullmatch(r"a\d{2}", code)
        ):
            _fail("ARTICLE_IDENTITY_INVALID")
        url = _clean_url(origin, f"/{slug}/")
        if url in article_urls or code in article_codes:
            _fail("ARTICLE_IDENTITY_DUPLICATE")
        article_urls.add(url)
        article_codes.add(code)
        items.append(InventoryItem(url, "article", code))

    pages = inventory.get("fixed_pages")
    if pages != ["about-ad-policy", "comparison-policy", "privacy-policy"]:
        _fail("FIXED_PAGE_INVENTORY_INVALID")
    page_urls = {_clean_url(origin, f"/{slug}/") for slug in pages}
    for slug in pages:
        items.append(InventoryItem(_clean_url(origin, f"/{slug}/"), "fixed_page", slug))
    if len(items) != 14 or len({item.url for item in items}) != 14:
        _fail("CLOSED_INVENTORY_INVALID")

    required_raw = raw.get("required_schema_types")
    if not isinstance(required_raw, dict):
        _fail("REQUIRED_SCHEMA_INVALID")
    required: dict[str, frozenset[str]] = {}
    for role in ("home", "article", "fixed_page"):
        values = required_raw.get(role)
        if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
            _fail("REQUIRED_SCHEMA_INVALID")
        required[role] = frozenset(values)
    forbidden_raw = raw.get("forbidden_schema_types")
    if forbidden_raw != [
        "Product",
        "Offer",
        "Review",
        "AggregateRating",
        "FAQPage",
    ]:
        _fail("FORBIDDEN_SCHEMA_INVALID")
    if raw.get("head_profile") != {
        "canonical_count": 1,
        "meta_description_count": 1,
        "open_graph": [
            "og:title",
            "og:description",
            "og:url",
            "og:image",
            "og:image:width",
            "og:image:height",
            "og:image:type",
            "og:type",
            "og:locale",
            "og:site_name",
        ],
        "title_count": 1,
        "twitter": [
            "twitter:card",
            "twitter:title",
            "twitter:description",
            "twitter:image",
        ],
    }:
        _fail("HEAD_PROFILE_INVALID")
    if raw.get("json_ld_semantics") != {
        "article": "EXACT_ARTICLE_BREADCRUMB_ORGANIZATION_WEBSITE_RELATIONSHIPS",
        "fixed_page": "EXACT_PAGE_BREADCRUMB_ORGANIZATION_WEBSITE_RELATIONSHIPS",
        "home": "EXACT_ORGANIZATION_WEBSITE_RELATIONSHIPS",
        "language": "ja-JP",
        "publisher": "https://kurashinoshirube.com/#organization",
    }:
        _fail("JSON_LD_SEMANTICS_INVALID")
    http = raw.get("http_boundary")
    surfaces = raw.get("surfaces")
    if not isinstance(http, dict) or not isinstance(surfaces, dict):
        _fail("HTTP_CONTRACT_INVALID")
    if http.get("redirects") != 0:
        _fail("REDIRECT_POLICY_INVALID")
    connect_timeout = http.get("connect_timeout_seconds")
    read_timeout = http.get("read_timeout_seconds")
    maximum_bytes = http.get("maximum_response_bytes")
    maximum_sitemaps = http.get("maximum_sitemap_documents")
    if not all(
        isinstance(value, int) and value > 0
        for value in (
            connect_timeout,
            read_timeout,
            maximum_bytes,
            maximum_sitemaps,
        )
    ):
        _fail("HTTP_CONTRACT_INVALID")
    assert isinstance(connect_timeout, int)
    assert isinstance(read_timeout, int)
    assert isinstance(maximum_bytes, int)
    assert isinstance(maximum_sitemaps, int)
    user_agent = http.get("user_agent")
    if not isinstance(user_agent, str) or not user_agent.startswith("RAOS-"):
        _fail("HTTP_CONTRACT_INVALID")
    return AuditContract(
        origin=origin,
        items=tuple(items),
        content_urls=frozenset(article_urls | page_urls),
        required_types=required,
        forbidden_types=frozenset(forbidden_raw),
        robots_url=_clean_url(origin, surfaces.get("robots_path", "")),
        sitemap_seed_url=_clean_url(origin, surfaces.get("sitemap_seed_path", "")),
        llms_url=_clean_url(origin, surfaces.get("forbidden_llms_path", "")),
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        maximum_bytes=maximum_bytes,
        maximum_sitemaps=maximum_sitemaps,
        user_agent=user_agent,
        contract_sha256=_sha256(raw_bytes),
        portfolio_sha256=_sha256(portfolio_bytes),
    )


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    observed_at: str

    def header_values(self, name: str) -> tuple[str, ...]:
        target = name.lower()
        return tuple(value for key, value in self.headers if key.lower() == target)

    @property
    def body_sha256(self) -> str:
        return _sha256(self.body)

    @property
    def headers_sha256(self) -> str:
        normalized = sorted((key.lower(), value.strip()) for key, value in self.headers)
        return _sha256(_canonical_json(normalized))


class HttpTransport(Protocol):
    def get(self, url: str) -> HttpResponse: ...


class BoundedHttpsTransport:
    """Exact-origin HTTPS GET transport; it never follows redirects."""

    def __init__(self, contract: AuditContract) -> None:
        self._contract = contract
        self._origin_parts = urlsplit(contract.origin)
        self._ssl_context = ssl.create_default_context()

    def get(self, url: str) -> HttpResponse:
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or parts.netloc != self._origin_parts.netloc
            or parts.hostname is None
            or parts.query
            or parts.fragment
            or not parts.path.startswith("/")
        ):
            _fail("HTTP_URL_OUT_OF_BOUNDARY")
        connection = http.client.HTTPSConnection(
            parts.hostname,
            parts.port or 443,
            timeout=self._contract.connect_timeout,
            context=self._ssl_context,
        )
        try:
            connection.request(
                "GET",
                parts.path,
                headers={
                    "Accept": "text/html,application/xml,text/plain;q=0.9,*/*;q=0.1",
                    "User-Agent": self._contract.user_agent,
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            if connection.sock is not None:
                connection.sock.settimeout(self._contract.read_timeout)
            body = response.read(self._contract.maximum_bytes + 1)
            if len(body) > self._contract.maximum_bytes:
                _fail("HTTP_RESPONSE_TOO_LARGE")
            return HttpResponse(
                url=url,
                status=response.status,
                headers=tuple((key, value) for key, value in response.getheaders()),
                body=body,
                observed_at=datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            )
        except OSError, TimeoutError, http.client.HTTPException:
            _fail("HTTP_FETCH_FAILED")
        finally:
            connection.close()


class _SeoHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.in_jsonld = False
        self.title_count = 0
        self.title_parts: list[str] = []
        self.jsonld_parts: list[str] = []
        self.jsonld_documents: list[str] = []
        self.meta: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        lowered = tag.lower()
        if lowered == "title":
            self.in_title = True
            self.title_count += 1
        elif lowered == "meta":
            self.meta.append(values)
        elif lowered == "link":
            self.links.append(values)
        elif lowered == "script" and values.get("type", "").lower() == (
            "application/ld+json"
        ):
            self.in_jsonld = True
            self.jsonld_parts = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self.in_title = False
        elif lowered == "script" and self.in_jsonld:
            self.jsonld_documents.append("".join(self.jsonld_parts))
            self.in_jsonld = False
            self.jsonld_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.in_jsonld:
            self.jsonld_parts.append(data)


def _meta_values(parser: _SeoHtmlParser, attr: str, name: str) -> list[str]:
    lowered = name.lower()
    return [
        item.get("content", "").strip()
        for item in parser.meta
        if item.get(attr, "").lower() == lowered
    ]


def _schema_types(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        raw_type = value.get("@type")
        if isinstance(raw_type, str):
            found.add(raw_type)
        elif isinstance(raw_type, list):
            found.update(item for item in raw_type if isinstance(item, str))
        for child in value.values():
            found.update(_schema_types(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_schema_types(child))
    return found


def _single_graph(parser: _SeoHtmlParser) -> tuple[dict[str, Any] | None, set[str]]:
    if len(parser.jsonld_documents) != 1:
        return None, set()
    try:
        document = json.loads(parser.jsonld_documents[0])
    except json.JSONDecodeError:
        return None, set()
    if (
        not isinstance(document, dict)
        or document.get("@context") != "https://schema.org"
        or not isinstance(document.get("@graph"), list)
    ):
        return None, _schema_types(document)
    return document, _schema_types(document)


def _same_origin_https_url(value: object, origin: str) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    expected = urlsplit(origin)
    return (
        parsed.scheme == "https"
        and parsed.netloc == expected.netloc
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and parsed.path.startswith("/")
    )


def _structured_data_semantics(
    document: dict[str, Any] | None,
    item: InventoryItem,
    contract: AuditContract,
    title: str,
    description: str,
    social_image: str,
) -> bool:
    if document is None:
        return False
    graph = document.get("@graph")
    if not isinstance(graph, list) or not all(isinstance(node, dict) for node in graph):
        return False
    typed_nodes = [node for node in graph if isinstance(node, dict)]
    top_types = [node.get("@type") for node in typed_nodes]
    if not all(isinstance(value, str) for value in top_types):
        return False
    expected_page_type = (
        "AboutPage" if item.identifier == "about-ad-policy" else "WebPage"
    )
    expected_types = {
        "home": ["Organization", "WebSite"],
        "article": ["Article", "BreadcrumbList", "Organization", "WebSite"],
        "fixed_page": [
            expected_page_type,
            "BreadcrumbList",
            "Organization",
            "WebSite",
        ],
    }[item.role]
    if sorted(top_types) != sorted(expected_types):
        return False
    identifiers = [node.get("@id") for node in typed_nodes]
    if (
        not all(isinstance(value, str) for value in identifiers)
        or len(set(identifiers)) != len(identifiers)
        or not all(
            _same_origin_https_url(str(value).split("#", 1)[0], contract.origin)
            for value in identifiers
        )
    ):
        return False
    by_type = {str(node["@type"]): node for node in typed_nodes}
    organization_id = contract.origin + "/#organization"
    website_id = contract.origin + "/#website"
    organization = by_type.get("Organization", {})
    website = by_type.get("WebSite", {})
    if organization != {
        "@id": organization_id,
        "@type": "Organization",
        "name": "暮らしのしるべ編集者",
        "url": contract.origin + "/",
    }:
        return False
    if website != {
        "@id": website_id,
        "@type": "WebSite",
        "inLanguage": "ja-JP",
        "name": "暮らしのしるべ",
        "publisher": {"@id": organization_id},
        "url": contract.origin + "/",
    }:
        return False
    if item.role == "home":
        return len(typed_nodes) == 2
    breadcrumb = by_type.get("BreadcrumbList", {})
    items = breadcrumb.get("itemListElement")
    if (
        breadcrumb.get("@id") != item.url + "#breadcrumb"
        or not isinstance(items, list)
        or len(items) != 2
        or items[0]
        != {
            "@type": "ListItem",
            "item": contract.origin + "/",
            "name": "ホーム",
            "position": 1,
        }
        or items[1]
        != {
            "@type": "ListItem",
            "item": item.url,
            "name": title,
            "position": 2,
        }
    ):
        return False
    if item.role == "article":
        article = by_type.get("Article", {})
        published = article.get("datePublished")
        modified = article.get("dateModified")
        if not _valid_utc_text(published) or not _valid_utc_text(modified):
            return False
        assert isinstance(published, str) and isinstance(modified, str)
        return (
            modified >= published
            and article.get("@id") == item.url + "#article"
            and article.get("articleSection") in {"移動", "家事", "備え"}
            and article.get("author") == {"@id": organization_id}
            and article.get("breadcrumb") == {"@id": item.url + "#breadcrumb"}
            and article.get("description") == description
            and article.get("headline") == title
            and article.get("image") == [social_image]
            and article.get("inLanguage") == "ja-JP"
            and article.get("mainEntityOfPage") == item.url
            and article.get("publisher") == {"@id": organization_id}
            and article.get("url") == item.url
        )
    page = by_type.get(expected_page_type, {})
    return page == {
        "@id": item.url + "#webpage",
        "@type": expected_page_type,
        "breadcrumb": {"@id": item.url + "#breadcrumb"},
        "description": description,
        "inLanguage": "ja-JP",
        "isPartOf": {"@id": website_id},
        "name": title,
        "url": item.url,
    }


def _check(
    status: bool, evidence_sha256: str, observed_at: str, detail: str
) -> dict[str, str]:
    if not _SHA256_RE.fullmatch(evidence_sha256):
        _fail("EVIDENCE_HASH_INVALID")
    return {
        "status": "PASS" if status else "FAIL",
        "detail": detail,
        "evidence_sha256": evidence_sha256,
        "observed_at": observed_at,
    }


def _page_checks(
    item: InventoryItem, response: HttpResponse, contract: AuditContract
) -> tuple[dict[str, dict[str, str]], set[str]]:
    body_hash = response.body_sha256
    header_hash = response.headers_sha256
    observed = response.observed_at
    checks: dict[str, dict[str, str]] = {}
    checks["http_200_no_redirect"] = _check(
        response.status == 200,
        header_hash,
        observed,
        f"HTTP_{response.status}",
    )
    try:
        html = response.body.decode("utf-8")
    except UnicodeDecodeError:
        html = ""
    parser = _SeoHtmlParser()
    parser.feed(html)

    canonicals = []
    for link in parser.links:
        rel = {part.lower() for part in link.get("rel", "").split()}
        if "canonical" in rel:
            canonicals.append(link.get("href", "").strip())
    checks["self_canonical"] = _check(
        canonicals == [item.url], body_hash, observed, "EXACT_ONE_SELF_CANONICAL"
    )

    robots_values = _meta_values(parser, "name", "robots")
    x_robots = list(response.header_values("X-Robots-Tag"))
    directives = {
        token.strip().lower()
        for value in robots_values + x_robots
        for token in value.split(",")
        if token.strip()
    }
    robots_ok = "noindex" not in directives and "nofollow" not in directives
    checks["robots_index_follow"] = _check(
        len(robots_values) == 1 and robots_ok,
        _sha256(_canonical_json([body_hash, header_hash])),
        observed,
        "NO_NOINDEX_OR_NOFOLLOW",
    )

    title = " ".join("".join(parser.title_parts).split())
    descriptions = _meta_values(parser, "name", "description")
    checks["title"] = _check(
        parser.title_count == 1 and bool(title),
        body_hash,
        observed,
        "EXACT_ONE_NONEMPTY",
    )
    checks["meta_description"] = _check(
        len(descriptions) == 1 and bool(descriptions[0]),
        body_hash,
        observed,
        "EXACT_ONE_NONEMPTY",
    )

    description = descriptions[0] if len(descriptions) == 1 else ""
    og_requirements = {
        "og_title": ("og:title", title),
        "og_description": ("og:description", description),
        "og_url": ("og:url", item.url),
        "og_image": ("og:image", None),
        "og_type": ("og:type", "article" if item.role == "article" else "website"),
        "og_locale": ("og:locale", "ja_JP"),
        "og_site_name": ("og:site_name", "暮らしのしるべ"),
        "og_image_width": ("og:image:width", None),
        "og_image_height": ("og:image:height", None),
        "og_image_type": ("og:image:type", "image/webp"),
    }
    for check_name, (property_name, exact) in og_requirements.items():
        values = _meta_values(parser, "property", property_name)
        ok = len(values) == 1 and bool(values[0])
        if exact is not None:
            ok = ok and values[0] == exact
        if property_name in {"og:image:width", "og:image:height"}:
            ok = ok and values[0].isdigit() and int(values[0]) > 0
        if property_name == "og:image":
            ok = ok and _same_origin_https_url(values[0], contract.origin)
        checks[check_name] = _check(ok, body_hash, observed, "EXACT_ONE_VALID")

    og_images = _meta_values(parser, "property", "og:image")
    social_image = og_images[0] if len(og_images) == 1 else ""
    twitter_requirements = {
        "twitter_card": ("twitter:card", "summary_large_image"),
        "twitter_title": ("twitter:title", title),
        "twitter_description": ("twitter:description", description),
        "twitter_image": ("twitter:image", social_image),
    }
    for check_name, (name, exact) in twitter_requirements.items():
        values = _meta_values(parser, "name", name)
        checks[check_name] = _check(
            values == [exact] and bool(exact),
            body_hash,
            observed,
            "EXACT_ONE_MATCHED",
        )

    document, schema_types = _single_graph(parser)
    jsonld_valid = document is not None
    required = contract.required_types[item.role]
    checks["required_schema"] = _check(
        jsonld_valid and required.issubset(schema_types),
        body_hash,
        observed,
        "REQUIRED_TYPES_PRESENT",
    )
    checks["forbidden_schema_absent"] = _check(
        not bool(contract.forbidden_types & schema_types),
        body_hash,
        observed,
        "FORBIDDEN_TYPES_ABSENT",
    )
    checks["structured_data_semantics"] = _check(
        _structured_data_semantics(
            document,
            item,
            contract,
            title,
            description,
            social_image,
        ),
        body_hash,
        observed,
        "EXACT_GRAPH_RELATIONSHIPS_AND_VALUES",
    )
    return checks, schema_types


def _robots_allows(body: bytes, inventory_paths: tuple[str, ...]) -> bool:
    try:
        lines = body.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return False
    applies = False
    disallows: list[str] = []
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, value = (part.strip() for part in line.split(":", 1))
        if field.lower() == "user-agent":
            applies = value == "*"
        elif field.lower() == "disallow" and applies and value.startswith("/"):
            if value != "/":
                disallows.append(value)
            else:
                return False
    return all(
        not any(path.startswith(rule) for rule in disallows) for path in inventory_paths
    )


def _xml_locations(body: bytes) -> tuple[str, set[str]]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        _fail("SITEMAP_XML_INVALID")
    root_name = root.tag.rsplit("}", 1)[-1]
    if root_name not in {"sitemapindex", "urlset"}:
        _fail("SITEMAP_ROOT_INVALID")
    expected_parent = "sitemap" if root_name == "sitemapindex" else "url"
    locations: set[str] = set()
    for child in root:
        if child.tag.rsplit("}", 1)[-1] != expected_parent:
            _fail("SITEMAP_CHILD_INVALID")
        direct_locations = [
            (element.text or "").strip()
            for element in child
            if element.tag.rsplit("}", 1)[-1] == "loc"
        ]
        if len(direct_locations) != 1 or not direct_locations[0]:
            _fail("SITEMAP_LOCATION_INVALID")
        location = direct_locations[0]
        if location in locations:
            _fail("SITEMAP_LOCATION_DUPLICATE")
        locations.add(location)
    return root_name, locations


def _validate_surface_url(url: str, contract: AuditContract) -> None:
    parts = urlsplit(url)
    origin = urlsplit(contract.origin)
    if (
        parts.scheme != "https"
        or parts.netloc != origin.netloc
        or parts.query
        or parts.fragment
        or not parts.path.startswith("/")
    ):
        _fail("SITEMAP_URL_OUT_OF_BOUNDARY")


def _load_index_states(
    path: Path | None, contract: AuditContract
) -> dict[str, dict[str, str | None]]:
    if path is None:
        return {
            item.url: {
                "state": "UNAVAILABLE",
                "verdict": None,
                "indexing_state": None,
                "observed_at": None,
                "last_crawl_at": None,
                "request_sha256": None,
                "response_sha256": None,
                "evidence_sha256": None,
                "basis": "UNAVAILABLE",
            }
            for item in contract.items
        }
    if path.is_symlink():
        _fail("INDEX_INPUT_NOT_REGULAR_FILE")
    resolved = path.resolve()
    private_root = PRIVATE_ROOT.resolve()
    try:
        resolved.relative_to(private_root)
    except ValueError:
        _fail("INDEX_INPUT_OUTSIDE_PRIVATE_ROOT")
    try:
        if (
            not private_root.is_dir()
            or stat.S_IMODE(private_root.stat().st_mode) != 0o700
        ):
            _fail("INDEX_PRIVATE_ROOT_MODE_INVALID")
        if resolved.parent != private_root or not resolved.is_file():
            _fail("INDEX_INPUT_NOT_REGULAR_FILE")
        mode = stat.S_IMODE(resolved.stat().st_mode)
    except OSError:
        _fail("INDEX_INPUT_NOT_REGULAR_FILE")
    if mode != 0o600:
        _fail("INDEX_INPUT_MODE_INVALID")
    raw_bytes = resolved.read_bytes()
    raw = _load_json(resolved)
    if not isinstance(raw, dict) or raw.get("schema") != (
        "RAOS_OWNER_PRIVATE_URL_INSPECTION_V1"
    ):
        _fail("INDEX_INPUT_SCHEMA_INVALID")
    observed_at = raw.get("observed_at")
    results = raw.get("results")
    if not _valid_utc_text(observed_at):
        _fail("INDEX_INPUT_TIMESTAMP_INVALID")
    if not isinstance(results, list) or len(results) != len(contract.items):
        _fail("INDEX_INPUT_INVENTORY_INVALID")
    expected = {item.url for item in contract.items}
    expected_order = tuple(item.url for item in contract.items)
    live_source = raw.get("source") == "GSC_URL_INSPECTION_API_V1"
    if live_source:
        if set(raw) != {
            "schema",
            "version",
            "source",
            "site_id",
            "site_url",
            "observed_at",
            "request_sha256",
            "result_count",
            "results",
        }:
            _fail("INDEX_INPUT_SCHEMA_INVALID")
        site_id = raw.get("site_id")
        site_url = raw.get("site_url")
        request_sha256 = raw.get("request_sha256")
        if (
            raw.get("version") != 1
            or raw.get("result_count") != len(contract.items)
            or not isinstance(site_id, str)
            or not isinstance(site_url, str)
            or not isinstance(request_sha256, str)
            or _SHA256_RE.fullmatch(request_sha256) is None
        ):
            _fail("INDEX_INPUT_SCHEMA_INVALID")
        try:
            live_query = SearchConsoleUrlInspectionQuery(
                site_id=UUID(site_id),
                site_url=site_url,
                inspection_urls=expected_order,
            )
        except ValueError, GoogleProviderFailure:
            _fail("INDEX_INPUT_SITE_BINDING_INVALID")
        if live_query.request_sha256 != request_sha256:
            _fail("INDEX_INPUT_REQUEST_HASH_INVALID")
    elif set(raw) != {"schema", "observed_at", "results"}:
        _fail("INDEX_INPUT_SCHEMA_INVALID")
    parsed: dict[str, dict[str, str | None]] = {}
    for position, result in enumerate(results):
        expected_result_keys = (
            {
                "url",
                "state",
                "verdict",
                "indexing_state",
                "last_crawl_at",
                "request_sha256",
                "response_sha256",
            }
            if live_source
            else {"url", "state", "last_crawl_at"}
        )
        if not isinstance(result, dict) or set(result) != expected_result_keys:
            _fail("INDEX_INPUT_RESULT_INVALID")
        url = result.get("url")
        state = result.get("state")
        crawl = result.get("last_crawl_at")
        if (
            not isinstance(url, str)
            or urlsplit(url).query
            or not isinstance(state, str)
            or state not in _ALLOWED_INDEX_STATES
            or (crawl is not None and not _valid_utc_text(crawl))
            or url in parsed
        ):
            _fail("INDEX_INPUT_RESULT_INVALID")
        if live_source:
            verdict = result.get("verdict")
            indexing_state = result.get("indexing_state")
            result_request_sha256 = result.get("request_sha256")
            result_response_sha256 = result.get("response_sha256")
            if (
                url != expected_order[position]
                or not isinstance(verdict, str)
                or not isinstance(indexing_state, str)
                or not isinstance(result_request_sha256, str)
                or _SHA256_RE.fullmatch(result_request_sha256) is None
                or not isinstance(result_response_sha256, str)
                or _SHA256_RE.fullmatch(result_response_sha256) is None
            ):
                _fail("INDEX_INPUT_RESULT_INVALID")
            try:
                expected_state = normalize_url_inspection_state(
                    verdict=verdict,
                    indexing_state=indexing_state,
                )
                expected_request_sha256 = gsc_url_inspection_request_sha256(
                    site_url=live_query.site_url,
                    inspection_url=url,
                )
            except GoogleProviderFailure:
                _fail("INDEX_INPUT_RESULT_INVALID")
            if (
                state != expected_state
                or result_request_sha256 != expected_request_sha256
            ):
                _fail("INDEX_INPUT_RESULT_INVALID")
        else:
            verdict = None
            indexing_state = None
            result_request_sha256 = None
            result_response_sha256 = None
        parsed[url] = {
            "state": state,
            "verdict": verdict,
            "indexing_state": indexing_state,
            "observed_at": observed_at,
            "last_crawl_at": crawl,
            "request_sha256": result_request_sha256,
            "response_sha256": result_response_sha256,
            "evidence_sha256": result_response_sha256 or _sha256(raw_bytes),
            "basis": (
                "OWNER_PRIVATE_LIVE_GSC_URL_INSPECTION_V1"
                if live_source
                else "OWNER_PRIVATE_RECORDED_URL_INSPECTION_V1"
            ),
        }
    if set(parsed) != expected:
        _fail("INDEX_INPUT_INVENTORY_INVALID")
    return parsed


def run_audit(
    transport: HttpTransport,
    contract: AuditContract,
    *,
    index_states: dict[str, dict[str, str | None]] | None = None,
) -> dict[str, Any]:
    if index_states is None:
        index_states = _load_index_states(None, contract)
    if set(index_states) != {item.url for item in contract.items}:
        _fail("INDEX_STATE_INVENTORY_INVALID")
    index_bases = {value.get("basis") for value in index_states.values()}
    if len(index_bases) != 1 or not all(
        isinstance(value, str) for value in index_bases
    ):
        _fail("INDEX_STATE_BASIS_INVALID")
    index_basis = next(iter(index_bases))
    pages: list[dict[str, Any]] = []
    for item in contract.items:
        response = transport.get(item.url)
        if response.url != item.url:
            _fail("TRANSPORT_URL_MISMATCH")
        checks, schema_types = _page_checks(item, response, contract)
        index_state = index_states[item.url]
        if index_state["state"] != "UNAVAILABLE":
            evidence_sha256 = index_state["evidence_sha256"]
            observed_at = index_state["observed_at"]
            state = index_state["state"]
            if (
                not isinstance(evidence_sha256, str)
                or not isinstance(observed_at, str)
                or not isinstance(state, str)
            ):
                _fail("INDEX_STATE_EVIDENCE_INVALID")
            checks["gsc_indexed"] = _check(
                state == "INDEXED",
                evidence_sha256,
                observed_at,
                state,
            )
        page_pass = all(check["status"] == "PASS" for check in checks.values())
        pages.append(
            {
                "identifier": item.identifier,
                "role": item.role,
                "url": item.url,
                "status": "PASS" if page_pass else "FAIL",
                "checks": checks,
                "schema_types": sorted(schema_types),
                "index_state": index_state,
            }
        )

    robots = transport.get(contract.robots_url)
    inventory_paths = tuple(urlsplit(item.url).path for item in contract.items)
    robots_ok = robots.status == 200 and _robots_allows(robots.body, inventory_paths)
    robots_check = _check(
        robots_ok,
        _sha256(_canonical_json([robots.body_sha256, robots.headers_sha256])),
        robots.observed_at,
        "ALL_INVENTORY_URLS_ALLOWED",
    )

    pending = [contract.sitemap_seed_url]
    seen: set[str] = set()
    content_urls: set[str] = set()
    sitemap_evidence: list[str] = []
    sitemap_observed: list[str] = []
    while pending:
        url = pending.pop(0)
        if url in seen:
            continue
        if len(seen) >= contract.maximum_sitemaps:
            _fail("SITEMAP_DOCUMENT_LIMIT_EXCEEDED")
        _validate_surface_url(url, contract)
        response = transport.get(url)
        seen.add(url)
        sitemap_evidence.append(response.body_sha256)
        sitemap_observed.append(response.observed_at)
        if response.status != 200:
            continue
        root_type, locations = _xml_locations(response.body)
        for location in locations:
            _validate_surface_url(location, contract)
        if root_type == "sitemapindex":
            pending.extend(sorted(locations - seen))
        else:
            content_urls.update(locations)
    home_urls = [item.url for item in contract.items if item.role == "home"]
    if len(home_urls) != 1:
        _fail("HOME_INVENTORY_INVALID")
    home_url = home_urls[0]
    home_in_sitemap = home_url in content_urls
    content_urls.discard(home_url)
    sitemap_ok = content_urls == set(contract.content_urls)
    sitemap_evidence_sha256 = _sha256(_canonical_json(sorted(sitemap_evidence)))
    sitemap_observed_at = (
        max(sitemap_observed)
        if sitemap_observed
        else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    sitemap_check = _check(
        sitemap_ok,
        sitemap_evidence_sha256,
        sitemap_observed_at,
        "EXACT_13_CONTENT_URLS",
    )
    sitemap_home_check = _check(
        True,
        sitemap_evidence_sha256,
        sitemap_observed_at,
        "PRESENT_SEPARATE" if home_in_sitemap else "ABSENT_ALLOWED",
    )

    llms = transport.get(contract.llms_url)
    llms_check = _check(
        llms.status in {404, 410},
        _sha256(_canonical_json([llms.body_sha256, llms.headers_sha256])),
        llms.observed_at,
        "ABSENT_404_OR_410",
    )
    overall = (
        all(page["status"] == "PASS" for page in pages)
        and robots_check["status"] == "PASS"
        and sitemap_check["status"] == "PASS"
        and sitemap_home_check["status"] == "PASS"
        and llms_check["status"] == "PASS"
    )
    return {
        "schema": "RAOS_WORDPRESS_SEO_AUDIT_REPORT_V1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "origin": contract.origin,
        "status": "PASS" if overall else "FAIL",
        "inventory_count": len(contract.items),
        "content_sitemap_count": len(contract.content_urls),
        "contract_sha256": contract.contract_sha256,
        "portfolio_sha256": contract.portfolio_sha256,
        "pages": pages,
        "surfaces": {
            "robots": robots_check,
            "sitemap": sitemap_check,
            "sitemap_home": sitemap_home_check,
            "llms_txt_absent": llms_check,
        },
        "index_state_basis": index_basis,
    }


def _ensure_private_output(path: Path) -> Path:
    resolved_root = PRIVATE_ROOT.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        _fail("OUTPUT_OUTSIDE_PRIVATE_ROOT")
    resolved_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(resolved_root, 0o700)
    resolved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(resolved.parent, 0o700)
    if resolved.exists() and (resolved.is_symlink() or not resolved.is_file()):
        _fail("OUTPUT_NOT_REGULAR_FILE")
    return resolved


def _write_private_report(path: Path, report: dict[str, Any]) -> None:
    target = _ensure_private_output(path)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_json(report))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _refresh_live_index_input(
    *,
    path: Path,
    contract: AuditContract,
    google_owner_private_root: Path,
) -> None:
    """Fetch exactly the closed inventory without exposing provider payloads."""

    bindings = FixedOwnerPrivateAnalyticsSiteBindings(
        google_owner_private_root.resolve()
    )
    binding = bindings.gsc()
    clock = SystemGoogleImportClock()
    sleeper = SystemGoogleRetrySleeper()
    provider = LiveSearchConsoleUrlInspectionProvider(
        transport=GoogleServiceAccountAuthorizedTransport(binding=binding),
        clock=clock,
        sleeper=sleeper,
    )
    batch = provider.inspect(
        SearchConsoleUrlInspectionQuery(
            site_id=binding.site_id,
            site_url=binding.resource,
            inspection_urls=tuple(item.url for item in contract.items),
        )
    )
    _write_private_report(path, gsc_url_inspection_document(batch))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--index-input", type=Path)
    parser.add_argument(
        "--refresh-index-from-gsc",
        action="store_true",
        help="replace --index-input from the exact live GSC URL Inspection batch",
    )
    parser.add_argument(
        "--google-owner-private-root",
        type=Path,
        default=DEFAULT_GOOGLE_PRIVATE_ROOT,
        help="0700 root containing separate google/gsc and google/ga4 bindings",
    )
    arguments = parser.parse_args(argv)
    try:
        contract = load_contract()
        if arguments.refresh_index_from_gsc:
            if arguments.index_input is None:
                _fail("INDEX_OUTPUT_REQUIRED_FOR_REFRESH")
            _refresh_live_index_input(
                path=arguments.index_input,
                contract=contract,
                google_owner_private_root=arguments.google_owner_private_root,
            )
        index_states = _load_index_states(arguments.index_input, contract)
        report = run_audit(
            BoundedHttpsTransport(contract), contract, index_states=index_states
        )
        _write_private_report(arguments.output, report)
    except AuditError as error:
        parser.error(error.code)
    except GoogleProviderFailure as error:
        parser.error(error.code.value)
    print(json.dumps({"status": report["status"], "output": str(arguments.output)}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
