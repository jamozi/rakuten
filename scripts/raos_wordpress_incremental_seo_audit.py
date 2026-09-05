#!/usr/bin/env python3
"""Read-only mixed-release readback; never infer new-copy expectations for old posts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, NoReturn, cast
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "python", ROOT / "scripts"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import raos_wordpress_publication_request as publication  # noqa: E402
import raos_wordpress_seo_audit as seo  # noqa: E402
import raos_wordpress_baseline_media as baseline_media  # noqa: E402
from raos_wordpress_incremental_snapshot import (  # noqa: E402
    PublicMetadataReader,
    capture_public_metadata,
)
from raos.application.editorial.verified_incremental_preview_v1 import (  # noqa: E402
    _public_metadata,
)
from raos.application.editorial.legacy_media_display_projection_v1 import (  # noqa: E402
    LegacyMediaProjectionFailure,
    TARGETS as LEGACY_MEDIA_TARGETS,
    project_legacy_media,
)
from raos.application.editorial.verified_incremental_release_v1 import (  # noqa: E402
    VerifiedIncrementalReleaseV1,
    validate_release_envelope,
)
from raos.application.editorial.verified_incremental_v1 import (  # noqa: E402
    _Markup,
    digest,
    supported_article_element,
)

PRIVATE = Path("/home/minami/rakuten/.secrets/wordpress-mcp/incremental-candidates")
SCHEMA = "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_PUBLIC_READBACK_V1"
VOID = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)
INJECTED = frozenset(
    {"raos-article-toc", "raos-back-to-toc-wrap", "raos-contextual-guide"}
)


def fail(code: str) -> NoReturn:
    raise seo.AuditError("INCREMENTAL_" + code) from None


def canonical(value: object) -> bytes:
    return publication.canonical_json_bytes(value)


def _read(path: Path) -> bytes:
    try:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o077
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or info.st_size > 16 * 1024 * 1024
        ):
            fail("PRIVATE_INPUT_INVALID")
        return path.read_bytes()
    except OSError:
        fail("PRIVATE_INPUT_UNAVAILABLE")


def _json(raw: bytes) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                fail("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except ValueError, UnicodeError:
        fail("JSON_INVALID")
    if type(value) is not dict:
        fail("JSON_INVALID")
    return cast(dict[str, Any], value)


class _EntryContent(HTMLParser):
    """Locate the single rendered post body without trusting a substring match."""

    def __init__(self, markup: str) -> None:
        super().__init__(convert_charrefs=False)
        self.markup = markup
        self.offsets = [0] + [match.end() for match in re.finditer("\n", markup)]
        self.stack: list[tuple[str, int | None]] = []
        self.bodies: list[str] = []

    def absolute_offset(self) -> int:
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID:
            return
        values = dict(attrs)
        start = None
        if "entry-content" in (values.get("class") or "").split():
            start = self.absolute_offset() + len(self.get_starttag_text() or "")
        self.stack.append((tag, start))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in VOID:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1][0] != tag:
            fail("PUBLIC_HTML_UNBALANCED")
        _tag, start = self.stack.pop()
        if start is not None:
            self.bodies.append(self.markup[start : self.absolute_offset()])


def _body(markup: str) -> str:
    parser = _EntryContent(markup)
    parser.feed(markup)
    parser.close()
    if parser.stack or len(parser.bodies) != 1:
        fail("PUBLIC_BODY_SCOPE_INVALID")
    return parser.bodies[0]


def _require_supported_element(
    tag: str, attrs: Mapping[str, str | None], *, article_body: bool = False
) -> None:
    # There is no identity/byte contract for responsive image alternatives in
    # this release. Do not equate a safe fallback img with a different source.
    if tag in {"picture", "source"} or "srcset" in attrs or "imagesrcset" in attrs:
        fail("PUBLIC_RESPONSIVE_MEDIA_UNSUPPORTED")
    if article_body and tag in {
        "script",
        "style",
        "iframe",
        "frame",
        "frameset",
        "object",
        "embed",
        "applet",
        "base",
        "link",
        "meta",
    }:
        fail("PUBLIC_ACTIVE_CONTENT_FORBIDDEN")
    # Scope this grammar to the extracted article only. The surrounding
    # WordPress theme can legitimately use SVG menu/search icons and head tags.
    if article_body and not supported_article_element(tag, attrs):
        fail("PUBLIC_ARTICLE_MARKUP_UNSUPPORTED")
    url_attributes = {
        "href",
        "src",
        "xlink:href",
        "action",
        "formaction",
        "poster",
        "data",
        "background",
        "cite",
        "codebase",
        "manifest",
        "longdesc",
        "profile",
    }
    for key, value in attrs.items():
        if key.startswith("on") or key == "srcdoc":
            fail("PUBLIC_EXECUTABLE_ATTRIBUTE_FORBIDDEN")
        if key in url_attributes:
            # HTMLParser has decoded character references; URL parsers ignore
            # ASCII controls/whitespace in executable schemes as well.
            normalized = re.sub(r"[\x00-\x20\x7f]", "", value or "").lower()
            scheme = re.match(r"^([a-z][a-z0-9+.-]*):", normalized)
            if scheme and scheme[1] not in {"https", "http", "mailto", "tel"}:
                fail("PUBLIC_EXECUTABLE_URL_FORBIDDEN")


class _SupportedBodyMarkup(_Markup):
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _require_supported_element(tag, dict(attrs), article_body=True)
        super().handle_starttag(tag, attrs)


def _project(markup: str, *, rendered: bool) -> dict[str, object]:
    parser = _SupportedBodyMarkup(markup)
    parser.feed(markup)
    parser.close()
    if parser.stack:
        fail("CONTENT_HTML_INVALID")
    removed: list[tuple[int, int]] = []
    for element in parser.elements:
        # Audit before excluding known runtime wrappers: an injected handler
        # must not disappear merely because its class belongs to the TOC.
        classes = set((element.attrs.get("class") or "").split())
        if classes & INJECTED:
            if not rendered:
                fail("AUTHORED_BODY_USES_RESERVED_RUNTIME_CLASS")
            removed.append((element.start, element.end))
    # Runtime TOC, back links and contextual handoffs are separately audited UI.
    # Only these closed, known additions may differ from the stored article.
    filtered = markup
    for start, end in sorted(removed, reverse=True):
        filtered = filtered[:start] + filtered[end:]
    evidence = publication._PublicPageEvidenceParser()
    evidence.feed(filtered)
    evidence.close()
    projected = _Markup(filtered)
    projected.feed(filtered)
    links, images, visibility, identities = [], [], [], []
    for element in projected.elements:
        attrs = element.attrs
        if element.tag == "a":
            href = attrs.get("href") or ""
            links.append(
                {
                    "href": href
                    if href.startswith("#")
                    else urljoin(publication.ORIGIN, href),
                    "rel": sorted(set((attrs.get("rel") or "").lower().split())),
                    "bindings": {
                        key: value
                        for key, value in attrs.items()
                        if key.startswith("data-raos-")
                    },
                }
            )
        if element.tag == "img":
            images.append(
                {key: attrs.get(key) for key in ("src", "alt", "width", "height")}
            )
        hidden = {
            key: attrs[key]
            for key in ("hidden", "inert", "style", "aria-hidden")
            if key in attrs
        }
        if hidden:
            visibility.append({"tag": element.tag, "attributes": hidden})
        bindings = {
            key: value for key, value in attrs.items() if key.startswith("data-raos-")
        }
        if bindings and element.tag != "a":
            identities.append({"tag": element.tag, "bindings": bindings})
    return {
        "text": re.sub(r"\s+", "", "".join(evidence.visible_text)),
        "headings": evidence.heading_outline,
        "links": links,
        "images": images,
        "visibility": visibility,
        "identities": identities,
    }


def verify_rendered_body(
    expected: str, actual_page: str, *, article_id: str | None = None
) -> str:
    if article_id is not None:
        try:
            expected = project_legacy_media(
                expected, article_id, profile="production"
            ).markup
        except LegacyMediaProjectionFailure:
            fail("DISPLAY_PROJECTION_MISMATCH")
    expected_projection = _project(expected, rendered=False)
    actual_projection = _project(_body(actual_page), rendered=True)
    if expected_projection != actual_projection:
        fail("PUBLIC_BODY_OR_COMMERCE_MISMATCH")
    return digest(canonical(expected_projection))


class _PageAssets(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: set[str] = set()
        self.links: set[str] = set()
        self.measurement_scripts = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if len(values) != len(attrs):
            fail("PUBLIC_ATTRIBUTES_DUPLICATE")
        _require_supported_element(tag, values)
        if tag == "img":
            if not values.get("src"):
                fail("PUBLIC_IMAGE_SOURCE_MISSING")
            self.images.add(str(values["src"]))
        if tag == "a" and values.get("href"):
            self.links.add(urljoin(publication.ORIGIN, str(values["href"])))
        if tag == "script" and re.search(
            r"measurement|googletagmanager|google-analytics",
            " ".join(str(values.get(key) or "") for key in ("src", "id")),
            re.I,
        ):
            self.measurement_scripts += 1


def _require_current_timestamp(value: object, now: datetime) -> None:
    if not seo._valid_utc_text(value):
        fail("HTTP_OBSERVATION_INVALID")
    observed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if not now - timedelta(minutes=5) <= observed <= now + timedelta(minutes=15):
        fail("HTTP_OBSERVATION_EXPIRED")


class _ObservedTransport:
    def __init__(self, delegate: seo.HttpTransport, now: datetime) -> None:
        self.delegate = delegate
        self.now = now
        self.responses: dict[str, seo.HttpResponse] = {}

    def get(self, url: str) -> seo.HttpResponse:
        if url not in self.responses:
            response = self.delegate.get(url)
            if response.url != url:
                fail("HTTP_OBSERVATION_INVALID")
            _require_current_timestamp(response.observed_at, self.now)
            self.responses[url] = response
        return self.responses[url]


def _theme_expectations(expected_tree: str) -> tuple[dict[str, str], dict[str, str]]:
    """Use the exact audited source tree, never a changed local title lookup."""
    import raos_wordpress_deployment_operator as deployment

    _archive, descriptor = deployment.theme_package()
    if digest(canonical(descriptor["file_manifest"])) != expected_tree:
        fail("AUDITED_THEME_SOURCE_CHANGED")
    raw = publication.THEME_FUNCTIONS_PATH.read_text(encoding="utf-8")
    values = {}
    for key in ("TITLE", "DESCRIPTION"):
        found = re.findall(
            r"^const KURASHINOSHIRUBE_HOME_" + key + r" = '([^'\n]+)';$", raw, re.M
        )
        if len(found) != 1:
            fail("HOME_HEAD_SOURCE_INVALID")
        values[key.lower()] = found[0]
    image_hashes = {
        publication.ORIGIN
        + "/wp-content/themes/kurashinoshirube-child/"
        + row["path"]: row["sha256"]
        for row in cast(list[dict[str, Any]], descriptor["file_manifest"])
        if row["path"].startswith("assets/images/")
    }
    return values, image_hashes


def _baseline_image_expectations(
    envelope: Mapping[str, Any],
    candidate_path: Path,
    snapshot: Mapping[str, Any],
) -> dict[str, str]:
    """Read the already-audited local replay, never use newest unbound cache data."""
    report_sha = envelope["audit_artifact_hashes"].get("mixed-browser-report")
    if (
        not isinstance(report_sha, str)
        or re.fullmatch(r"[a-f0-9]{64}", report_sha) is None
    ):
        fail("BASELINE_IMAGE_AUDIT_MISSING")
    report_raw = _read(candidate_path / "audit/inputs" / f"{report_sha}.bin")
    if digest(report_raw) != report_sha:
        fail("BASELINE_IMAGE_AUDIT_CHANGED")
    report = _json(report_raw)
    if (
        report.get("schema") != "RAOS_WORDPRESS_MIXED_BROWSER_AUDIT_V1"
        or report.get("status") != "LOCAL_MIXED_BROWSER_AUDIT_PASSED"
    ):
        fail("BASELINE_IMAGE_AUDIT_INVALID")
    preparation_sha = report.get("inputs", {}).get("preparation_binding_sha256")
    if (
        not isinstance(preparation_sha, str)
        or re.fullmatch(r"[a-f0-9]{64}", preparation_sha) is None
    ):
        fail("BASELINE_IMAGE_AUDIT_INVALID")
    prepared_raw = _read(
        PRIVATE.parent
        / f"incremental-preview-{preparation_sha}"
        / "preparation-binding.v1.json"
    )
    if digest(prepared_raw) != preparation_sha:
        fail("BASELINE_IMAGE_AUDIT_CHANGED")
    prepared = _json(prepared_raw)
    receipt = prepared.get("baseline_media", {})
    if (
        prepared.get("publication_profile") != "verified-incremental"
        or prepared.get("source_snapshot_sha256") != digest(canonical(snapshot))
        or set(prepared.get("selected_slugs", [])) != set(envelope["selected_articles"])
        or receipt.get("schema") != baseline_media.SCHEMA
        or receipt.get("publication_authority") is not False
        or receipt.get("new_commerce_verified") is not False
    ):
        fail("BASELINE_IMAGE_AUDIT_INVALID")
    expected_urls = set()
    for row in snapshot["documents"]:
        if (
            row["post_type"] == "post"
            and row["slug"] not in envelope["selected_articles"]
        ):
            expected_urls.update(baseline_media.image_urls(row["block_markup"]))
    entries = receipt.get("images", {})
    if {row.get("source_url") for row in entries.values()} != expected_urls:
        fail("BASELINE_IMAGE_SCOPE_MISMATCH")
    result = {}
    for key, entry in entries.items():
        url, expected = entry["source_url"], entry.get("content_sha256")
        if (
            key != digest(url.encode())
            or not isinstance(expected, str)
            or re.fullmatch(r"[a-f0-9]{64}", expected) is None
        ):
            fail("BASELINE_IMAGE_AUDIT_INVALID")
        result[url] = expected
    return result


def run_verified_incremental_public_audit(
    *,
    context: VerifiedIncrementalReleaseV1,
    candidate_path: Path,
    original_snapshot: Mapping[str, Any],
    current_documents: Mapping[str, Mapping[str, Any]],
    now: datetime,
    deployment_readback: Mapping[str, Any],
    site_status_readback: Mapping[str, Any] | None = None,
    transport: seo.HttpTransport | None = None,
    public_metadata_reader: Any | None = None,
    external_image_fetch: Callable[
        [str], baseline_media.ImageResponse
    ] = baseline_media.fetch_image,
) -> dict[str, object]:
    """All fourteen URLs: semantic SEO plus candidate/baseline-exact readback.

    No credential is read here. The caller supplies fresh bounded MCP readbacks;
    missing dates are diagnosed with fixed-origin, unauthenticated REST reads.
    Expired releases may only be inspected, never renewed or applied here.
    """
    envelope = cast(dict[str, Any], context.to_document())
    validate_release_envelope(
        envelope,
        current_context=context,
        publication_profile="verified-incremental",
        link_mode="standard-api",
        stage="readback",
        now=now,
    )
    if site_status_readback is None:
        fail("SITE_STATUS_MISSING")
    publication.validate_site_status(site_status_readback, require_measurement_off=True)
    if (
        candidate_path.parent != PRIVATE
        or candidate_path.name != envelope["manifest_sha256"]
    ):
        fail("CANDIDATE_PATH_INVALID")
    for directory in (
        candidate_path,
        candidate_path / "audit",
        candidate_path / "audit/inputs",
    ):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
            fail("PRIVATE_DIRECTORY_INVALID")
    prep_raw = _read(candidate_path / "candidate-preparation.v1.json")
    preparation = _json(prep_raw)
    if digest(prep_raw) != envelope["audit_artifact_hashes"].get(
        "candidate-preparation"
    ) or digest(canonical(original_snapshot)) != envelope["audit_artifact_hashes"].get(
        "live-snapshot"
    ):
        fail("AUDITED_INPUT_CHANGED")
    if preparation.get("manifest_sha256") != envelope[
        "manifest_sha256"
    ] or preparation.get("snapshot_sha256") != digest(canonical(original_snapshot)):
        fail("PREPARATION_SCOPE_INVALID")
    originals = {row["slug"]: row for row in original_snapshot["documents"]}
    contract = seo.load_contract()
    slugs = {
        "home" if item.role == "home" else urlsplit(item.url).path.strip("/")
        for item in contract.items
    }
    if (
        len(originals) != 14
        or set(originals) != slugs
        or set(envelope["inventory"]) != slugs
    ):
        fail("CORE_INVENTORY_MISMATCH")
    # The caller also checks the full WordPress inventory. Here, extras cannot be
    # mistaken for one of the fourteen core targets and missing targets fail.
    current = {
        slug: dict(current_documents[slug])
        for slug in slugs
        if slug in current_documents
    }
    if set(current) != slugs:
        fail("CORE_INVENTORY_MISMATCH")
    expected_hashes: dict[str, str] = {
        **envelope["unchanged_documents"],
        **envelope["expected_production_content_sha256"],
    }
    prepared = preparation["production_documents"]
    if set(prepared) != set(envelope["expected_production_content_sha256"]):
        fail("PREPARED_TARGET_SET_MISMATCH")
    expected = {}
    for slug in sorted(slugs):
        baseline, observed = originals[slug], current[slug]
        if publication._content_after_sha256(baseline, baseline["id"]) != baseline.get(
            "content_sha256"
        ):
            fail("BASELINE_HASH_INVALID")
        if any(
            observed.get(key) != baseline.get(key)
            for key in ("id", "slug", "post_type", "status")
        ):
            fail("DOCUMENT_IDENTITY_CHANGED")
        if (
            publication._content_after_sha256(observed, observed["id"])
            != expected_hashes[slug]
            or observed.get("content_sha256") != expected_hashes[slug]
        ):
            fail("MCP_CONTENT_MISMATCH")
        target = prepared[slug]["document"] if slug in prepared else baseline
        if (
            publication._content_after_sha256(target, baseline["id"])
            != expected_hashes[slug]
        ):
            fail("PREPARED_CONTENT_MISMATCH")
        if slug not in prepared and publication._baseline_record(
            observed
        ) != publication._baseline_record(baseline):
            fail("UNTOUCHED_DOCUMENT_CHANGED")
        expected[slug] = target
    theme = deployment_readback.get("theme", {})
    expected_tree = (
        envelope["expected_shared_readback_sha256"].get("theme")
        or original_snapshot["deployment_status"]["theme"]["tree_sha256"]
    )
    if (
        deployment_readback.get("schema") != "RAOSWordPressDeploymentStatusV1"
        or deployment_readback.get("origin") != contract.origin
        or theme.get("slug") != "kurashinoshirube-child"
        or theme.get("active") is not True
        or theme.get("tree_sha256") != expected_tree
    ):
        fail("DEPLOYMENT_THEME_MISMATCH")
    home_head, theme_images = _theme_expectations(expected_tree)
    metadata = capture_public_metadata(
        public_metadata_reader or PublicMetadataReader(), list(current.values())
    )
    replayed_raw, blockers = _public_metadata({"public_metadata": metadata}, current)
    baseline_raw, baseline_blockers = _public_metadata(original_snapshot, originals)
    replayed = cast(dict[str, Any], replayed_raw)
    baseline_metadata = cast(dict[str, Any], baseline_raw)
    if (
        blockers
        or baseline_blockers
        or set(replayed) != slugs
        or set(baseline_metadata) != slugs
    ):
        fail("PUBLIC_METADATA_UNVERIFIED")
    for row in cast(dict[str, Any], metadata["documents"]).values():
        _require_current_timestamp(row["evidence"]["retrieved_at"], now)
    for slug in slugs:
        if (
            replayed[slug]["dates"]["date_gmt"]
            != baseline_metadata[slug]["dates"]["date_gmt"]
            or replayed[slug]["taxonomies"] != baseline_metadata[slug]["taxonomies"]
        ):
            fail("PUBLISHED_DATE_OR_TAXONOMY_CHANGED")
        if slug not in prepared and replayed[slug] != baseline_metadata[slug]:
            fail("UNTOUCHED_METADATA_CHANGED")
    observed_http = _ObservedTransport(
        transport or seo.BoundedHttpsTransport(contract), now
    )
    report = seo.run_audit(observed_http, contract)
    if report["status"] != "PASS":
        fail("PUBLIC_SEO_FAILED")
    page_bindings = {}
    image_urls: set[str] = set()
    for item in contract.items:
        slug = "home" if item.role == "home" else urlsplit(item.url).path.strip("/")
        page = observed_http.get(item.url)
        markup = page.body.decode("utf-8", errors="strict")
        head = seo._SeoHtmlParser()
        head.feed(markup)
        target = expected[slug]
        wanted_head = (
            home_head
            if item.role == "home"
            else {"title": target["title"], "description": target["excerpt"]}
        )
        if "".join(head.title_parts).strip() != wanted_head[
            "title"
        ] or seo._meta_values(head, "name", "description") != [
            wanted_head["description"]
        ]:
            fail("CANDIDATE_OR_BASELINE_HEAD_MISMATCH")
        image = (
            publication.EXPECTED_SOCIAL_IMAGE_URL
            if item.role != "article"
            else contract.origin
            + "/wp-content/themes/kurashinoshirube-child/assets/images/"
            + publication.EXPECTED_ARTICLE_SOCIAL_IMAGE_BY_SLUG[slug]
        )
        if seo._meta_values(head, "property", "og:image") != [image]:
            fail("SOCIAL_IMAGE_MISMATCH")
        image_urls.add(image)
        graph, _types = seo._single_graph(head)
        if graph is None:
            fail("JSONLD_GRAPH_INVALID")
        if item.role == "article":
            article = next(
                row for row in graph["@graph"] if row.get("@type") == "Article"
            )
            dates = replayed[slug]["dates"]
            if (
                article["datePublished"]
                != str(dates["date_gmt"]).replace(" ", "T") + "Z"
                or article["dateModified"]
                != str(dates["modified_gmt"]).replace(" ", "T") + "Z"
            ):
                fail("JSONLD_DATES_MISMATCH")
        display_article_id = next(
            (
                article_id
                for article_id, target in LEGACY_MEDIA_TARGETS.items()
                if target[0] == slug
            ),
            slug,
        )
        display_proof = None
        if item.role == "article":
            try:
                display_proof = dict(
                    project_legacy_media(
                        target["block_markup"], display_article_id, profile="production"
                    ).proof
                )
            except LegacyMediaProjectionFailure:
                fail("DISPLAY_PROJECTION_MISMATCH")
        projection_sha = (
            None
            if item.role == "home"
            else verify_rendered_body(
                target["block_markup"],
                markup,
                article_id=display_article_id if item.role == "article" else None,
            )
        )
        evidence = publication._PublicPageEvidenceParser()
        evidence.feed(markup)
        if item.role != "home" and evidence.h1_titles != [target["title"]]:
            fail("PUBLIC_H1_MISMATCH")
        assets = _PageAssets()
        assets.feed(markup)
        assets.close()
        if assets.measurement_scripts or page.header_values("set-cookie"):
            fail("PUBLIC_MEASUREMENT_OFF_MISMATCH")
        if (
            item.role == "home"
            and not {entry.url for entry in contract.items if entry.role == "article"}
            <= assets.links
        ):
            fail("HOME_ARTICLE_ROUTES_MISSING")
        image_urls.update(assets.images)
        page_bindings[slug] = {
            "url": item.url,
            "post_id": current[slug]["id"],
            "state": "UPDATED" if slug in prepared else "PRESERVED",
            "content_sha256": current[slug]["content_sha256"],
            "rendered_body_projection_sha256": projection_sha,
            "legacy_media_display_projection": display_proof,
            "public_response_sha256": page.body_sha256,
            "public_headers_sha256": page.headers_sha256,
            "measurement_state": "NO_MEASUREMENT_SCRIPT_OR_SET_COOKIE",
        }
    image_bindings = {}
    external_urls = {
        url for url in image_urls if urlsplit(url).netloc != "kurashinoshirube.com"
    }
    baseline_images = (
        _baseline_image_expectations(envelope, candidate_path, original_snapshot)
        if external_urls
        else {}
    )
    for url in sorted(image_urls):
        parts = urlsplit(url)
        if url in baseline_images:
            response_image = external_image_fetch(url)
            if (
                response_image.url != url
                or digest(response_image.body) != baseline_images[url]
            ):
                fail("BASELINE_IMAGE_PUBLIC_BYTES_CHANGED")
            _require_current_timestamp(response_image.retrieved_at, now)
            baseline_media.image_extension(
                response_image.body, response_image.content_type
            )
            image_bindings[url] = baseline_images[url]
            continue
        if (
            parts.scheme != "https"
            or parts.netloc != "kurashinoshirube.com"
            or parts.query
            or parts.fragment
        ):
            fail("PUBLIC_IMAGE_ORIGIN_UNVERIFIED")
        response = observed_http.get(url)
        if (
            response.status != 200
            or not response.body
            or not any(
                value.split(";", 1)[0].lower().startswith("image/")
                for value in response.header_values("content-type")
            )
        ):
            fail("PUBLIC_IMAGE_BROKEN")
        if url in theme_images and response.body_sha256 != theme_images[url]:
            fail("THEME_IMAGE_BYTES_MISMATCH")
        image_bindings[url] = response.body_sha256
    result = {
        "schema": SCHEMA,
        "publication_profile": "verified-incremental",
        "link_mode": "standard-api",
        "measurement_collection_enabled": False,
        "publication_authority": False,
        "status": "PUBLIC_READBACK_PASSED",
        "release_sha256": context.sha256,
        "manifest_sha256": envelope["manifest_sha256"],
        "snapshot_sha256": digest(canonical(original_snapshot)),
        "candidate_preparation_sha256": digest(prep_raw),
        "site_status_sha256": digest(canonical(site_status_readback)),
        "theme_tree_sha256": expected_tree,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "core_document_count": 14,
        "page_evidence": page_bindings,
        "public_metadata_sha256": digest(canonical(metadata)),
        "seo_report_sha256": digest(canonical(report)),
        "image_evidence_sha256": digest(canonical(image_bindings)),
        "monetization_state": envelope["monetization_state"],
        "not_verified_by_this_report": [
            "real_reader_tests",
            "live_browser_interaction",
            "external_checkout",
            "search_ranking",
            "revenue",
        ],
    }
    return {**result, "binding_sha256": digest(canonical(result))}
