#!/usr/bin/env python3
"""Read-only mixed-release readback; never infer new-copy expectations for old posts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from html import escape, unescape
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
import raos_wordpress_runtime_audit as runtime  # noqa: E402
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
    READER_HUB_SLUGS,
    canonical as manifest_canonical,
    _Markup,
    digest,
    html_attribute_tokens,
    supported_article_element,
    supported_html_token_attributes,
)

PRIVATE = Path("/home/minami/rakuten/.secrets/wordpress-mcp/incremental-candidates")
SCHEMA = "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_PUBLIC_READBACK_V1"
SCHEMA_V2 = "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_PUBLIC_READBACK_V2"
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

    def __init__(self, markup: str, *, home: bool = False) -> None:
        super().__init__(convert_charrefs=False)
        self.markup = markup
        self.home = home
        self.main_count = 0
        self.offsets = [0] + [match.end() for match in re.finditer("\n", markup)]
        self.stack: list[tuple[str, int | None]] = []
        self.bodies: list[str] = []

    def absolute_offset(self) -> int:
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if self.home:
            if tag == "main":
                self.main_count += 1
                if values.get("id") != "main-content":
                    fail("PUBLIC_HOME_SCOPE_INVALID")
            if tag == "main" or "entry-content" in html_attribute_tokens(values.get("class")):
                if {"hidden", "inert", "aria-hidden", "style"} & set(values):
                    fail("PUBLIC_HOME_SCOPE_INVALID")
            if self.stack and self.stack[-1][0] == "main":
                if tag != "div" or not {"entry-content", "wp-block-post-content"} <= html_attribute_tokens(values.get("class")):
                    fail("PUBLIC_HOME_SCOPE_INVALID")
            if "entry-content" in html_attribute_tokens(values.get("class")) and (
                not self.stack or self.stack[-1][0] != "main"
            ):
                fail("PUBLIC_HOME_SCOPE_INVALID")
        if tag in VOID:
            return
        start = None
        if "entry-content" in html_attribute_tokens(values.get("class")):
            if not supported_html_token_attributes(self.get_starttag_text() or ""):
                fail("PUBLIC_BODY_SCOPE_INVALID")
            start = self.absolute_offset() + len(self.get_starttag_text() or "")
        self.stack.append((tag, start))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            if self.home:
                fail("PUBLIC_HOME_SCOPE_INVALID")
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1][0] != tag:
            fail("PUBLIC_HTML_UNBALANCED")
        _tag, start = self.stack.pop()
        if start is not None:
            self.bodies.append(self.markup[start : self.absolute_offset()])

    def handle_data(self, data: str) -> None:
        if self.home and self.stack and self.stack[-1][0] == "main" and data.strip():
            fail("PUBLIC_HOME_SCOPE_INVALID")

    def handle_entityref(self, name: str) -> None:
        self.handle_data(unescape("&" + name + ";"))

    def handle_charref(self, name: str) -> None:
        self.handle_data(unescape("&#" + name + ";"))


def _body(markup: str, *, home: bool = False) -> str:
    parser = _EntryContent(markup, home=home)
    parser.feed(markup)
    parser.close()
    if parser.stack or len(parser.bodies) != 1 or home and parser.main_count != 1:
        fail("PUBLIC_BODY_SCOPE_INVALID")
    return parser.bodies[0]


def _require_supported_element(
    tag: str,
    attrs: Mapping[str, str | None],
    *,
    article_body: bool = False,
    raw_starttag: str | None = None,
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
    # Scope both element and resource-attribute grammar to the article only.
    # Theme icons, inline layout styles and head tags have separate contracts.
    if article_body and (
        not supported_article_element(tag, attrs)
        or raw_starttag is not None
        and not supported_html_token_attributes(raw_starttag)
    ):
        fail("PUBLIC_ARTICLE_MARKUP_UNSUPPORTED")


class _SupportedBodyMarkup(_Markup):
    def __init__(self, markup: str) -> None:
        super().__init__(markup)
        self.editor_note_text: list[tuple[int, int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _require_supported_element(
            tag,
            dict(attrs),
            article_body=True,
            raw_starttag=self.get_starttag_text(),
        )
        super().handle_starttag(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _require_supported_element(
            tag,
            dict(attrs),
            article_body=True,
            raw_starttag=self.get_starttag_text(),
        )
        super().handle_startendtag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        element = self.stack[-1] if self.stack else None
        closing_start = self.absolute_offset()
        super().handle_endtag(tag)
        if element is not None and tag == "p" and "section-number" in html_attribute_tokens(element.attrs.get("class")):
            label = unescape(self.markup[element.opening_end:closing_start])
            if re.fullmatch(r"[0-9]+[ \u3000]+EDITOR['’]S NOTE", label):
                self.editor_note_text.append((element.opening_end, closing_start, label.replace("’", "'")))


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
        classes = html_attribute_tokens(element.attrs.get("class"))
        if classes & INJECTED:
            if not rendered:
                fail("AUTHORED_BODY_USES_RESERVED_RUNTIME_CLASS")
            removed.append((element.start, element.end))
    # Runtime TOC, back links and contextual handoffs are separately audited UI.
    # Only these closed, known additions may differ from the stored article.
    filtered = markup
    for start, end in sorted(removed, reverse=True):
        filtered = filtered[:start] + filtered[end:]
    projected = _SupportedBodyMarkup(filtered)
    projected.feed(filtered)
    projected.close()
    # wptexturize changes this closed decorative label. Only visible text is
    # canonicalized; original tags, attributes, URLs and identities stay intact.
    display_text = filtered
    for start, end, label in reversed(projected.editor_note_text):
        display_text = display_text[:start] + label + display_text[end:]
    evidence = publication._PublicPageEvidenceParser()
    evidence.feed(display_text)
    evidence.close()
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
                    "rel": sorted(
                        html_attribute_tokens((attrs.get("rel") or "").lower())
                    ),
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


class _HomeBodyMarkup(_Markup):
    """Compare an existing home body including its exact inline styles.

    This is readback of a frozen baseline, not permission to author CSS or media.
    Article grammar and its stricter resource rules remain unchanged.
    """

    def __init__(self, markup: str) -> None:
        super().__init__(markup)
        self.tokens: list[list[Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if len(values) != len(attrs):
            fail("PUBLIC_ATTRIBUTES_DUPLICATE")
        if any(not unescape(reference) for reference in re.findall(
            r"&#(?:[xX][0-9a-fA-F]+|[0-9]+);?", self.get_starttag_text() or ""
        )):
            fail("PUBLIC_HOME_ATTRIBUTE_REFERENCE_INVALID")
        _require_supported_element(tag, values)
        # The closed HTML grammar still validates tags, nesting and every other
        # attribute. Styles are retained verbatim in the compared token stream.
        shadow_tag, search_attributes = {
            "form": ("div", {"action", "method"}),
            "label": ("span", {"for"}),
            "input": ("img", {"name", "type", "placeholder", "required"}),
            "button": ("span", {"type"}),
        }.get(tag, (tag, set()))
        if tag in {"form", "label", "input", "button"}:
            # Preserve the saved, same-site GET search in the hidden inline
            # header. This does not authorize general forms or new form writes.
            in_header = any("km-header" in html_attribute_tokens(row.attrs.get("class")) for row in self.stack)
            in_search = any(row.tag == "form" and row.attrs.get("role") == "search" for row in self.stack)
            if not in_header or (tag != "form" and not in_search) or (
                tag == "form" and (values.get("method") != "get" or values.get("action") != "/" or values.get("role") != "search")
                or tag == "input" and (values.get("type") != "search" or values.get("name") != "s")
                or tag == "button" and values.get("type") != "submit"
            ):
                fail("PUBLIC_HOME_SEARCH_INVALID")
        super().handle_starttag(shadow_tag, [(key, value) for key, value in attrs if key != "style" and key not in search_attributes])
        self.elements[-1].tag = tag
        self.elements[-1].attrs = values
        self.tokens.append(["open", tag, sorted((key, value or "") for key, value in values.items())])

    def handle_endtag(self, tag: str) -> None:
        element = self.stack[-1] if self.stack else None
        parent = self.stack[-2] if len(self.stack) >= 2 else None
        if (
            tag == "span" and element is not None and not element.attrs
            and parent is not None and parent.tag == "div"
            and "km-spine" in html_attribute_tokens(parent.attrs.get("class"))
            and parent.attrs.get("aria-hidden") == "true"
            and self.tokens and self.tokens[-1] == ["text", "EDITOR’S PICK"]
        ):
            # WordPress texturizes this one decorative label; never normalize
            # editorial prose, attributes, URLs, images or arbitrary apostrophes.
            self.tokens[-1] = ["text", "EDITOR'S PICK"]
        super().handle_endtag(tag)
        self.tokens.append(["close", tag])

    def _text(self, data: str) -> None:
        if not self.stack and not data.strip("\t\n\f\r "):
            return
        if self.tokens and self.tokens[-1][0] == "text":
            self.tokens[-1][1] += data
        else:
            self.tokens.append(["text", data])

    def handle_data(self, data: str) -> None:
        super().handle_data(data)
        self._text(data)

    def handle_entityref(self, name: str) -> None:
        super().handle_entityref(name)
        self._text(unescape("&" + name + ";"))

    def handle_charref(self, name: str) -> None:
        super().handle_charref(name)
        decoded = unescape("&#" + name + ";")
        if not decoded:
            fail("PUBLIC_HOME_TEXT_REFERENCE_INVALID")
        self._text(decoded)


def _home_projection(markup: str) -> list[list[Any]]:
    parser = _parsed_home_body(markup)
    if sum(element.tag == "h1" for element in parser.elements) != 1:
        fail("PUBLIC_HOME_BODY_INVALID")
    return parser.tokens


def _parsed_home_body(markup: str) -> _HomeBodyMarkup:
    parser = _HomeBodyMarkup(markup)
    parser.feed(markup)
    parser.close()
    ids = [element.attrs["id"] for element in parser.elements if element.attrs.get("id")]
    if parser.stack or len(ids) != len(set(ids)):
        fail("PUBLIC_HOME_BODY_INVALID")
    return parser


def verify_rendered_home_body(expected: str, actual_page: str) -> str:
    expected_projection = _home_projection(expected)
    actual_projection = _home_projection(_body(actual_page, home=True))
    if expected_projection != actual_projection:
        fail("PUBLIC_HOME_BODY_MISMATCH")
    return digest(canonical(expected_projection))


def _preserved_home_style(markup: str) -> str | None:
    parser = _parsed_home_body(markup)
    return next((element.attrs["style"] for element in parser.elements
                 if element.tag == "div" and element.attrs.get("id") == "ks-magazine"
                 and "data:image/webp;base64," in (element.attrs.get("style") or "")), None)


def home_image_urls(markup: str) -> set[str]:
    """Extract only the existing closed home body's approved remote images."""
    parser = _parsed_home_body(markup)
    style = _preserved_home_style(markup)
    if style is not None:
        runtime.preserved_webp_style(style)
    urls = set()
    for element in parser.elements:
        if element.tag != "img":
            continue
        value = element.attrs.get("src")
        if not isinstance(value, str) or element.attrs.get("srcset"):
            fail("PUBLIC_HOME_IMAGE_MARKUP_INVALID")
        if value.startswith("https://"):
            baseline_media.validate_url(value)
            urls.add(value)
        elif value.startswith("http:"):
            fail("PUBLIC_HOME_IMAGE_URL_NOT_SUPPORTED")
    return urls


def captured_home_theme_image_urls(markup: str) -> frozenset[str]:
    """Retain only exact old child-theme image references for baseline replay."""
    parser = _parsed_home_body(markup)
    return frozenset(
        runtime.ORIGIN + source
        for element in parser.elements
        if element.tag == "img"
        and type(source := element.attrs.get("src")) is str
        and re.fullmatch(
            r"/wp-content/themes/kurashinoshirube-child/assets/images/[a-z0-9-]+\.(?:png|webp|svg)",
            source,
        )
        is not None
    )


def home_uses_post_content(files: Mapping[str, bytes]) -> bool:
    return files.get("templates/front-page.html", b"").count(
        b'<!-- wp:post-content {"layout":{"type":"default"}} /-->'
    ) == 1


class _PageAssets(HTMLParser):
    def __init__(self, *, verified_home_body: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.verified_home_body = verified_home_body
        self.images: set[str] = set()
        self.image_counts: Counter[str] = Counter()
        self.links: set[str] = set()
        self.measurement_scripts = 0
        self._content_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if len(values) != len(attrs):
            fail("PUBLIC_ATTRIBUTES_DUPLICATE")
        _require_supported_element(
            tag,
            values,
            article_body=self._content_depth > 0 and not self.verified_home_body,
            raw_starttag=self.get_starttag_text(),
        )
        if tag not in VOID:
            if self._content_depth:
                self._content_depth += 1
            elif "entry-content" in html_attribute_tokens(values.get("class")):
                if not supported_html_token_attributes(self.get_starttag_text() or ""):
                    fail("PUBLIC_BODY_SCOPE_INVALID")
                self._content_depth = 1
        if tag == "img":
            if not values.get("src"):
                fail("PUBLIC_IMAGE_SOURCE_MISSING")
            self.images.add(str(values["src"]))
            self.image_counts[str(values["src"])] += 1
        if tag == "a" and values.get("href"):
            self.links.add(urljoin(publication.ORIGIN, str(values["href"])))
        if tag == "script" and re.search(
            r"measurement|googletagmanager|google-analytics",
            " ".join(str(values.get(key) or "") for key in ("src", "id")),
            re.I,
        ):
            self.measurement_scripts += 1

    def handle_endtag(self, tag: str) -> None:
        if tag not in VOID and self._content_depth:
            self._content_depth -= 1


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


def _theme_expectations(
    expected_tree: str,
) -> tuple[dict[str, str], dict[str, str], dict[str, runtime.Resource]]:
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
    return (
        values,
        image_hashes,
        runtime.resources_for_theme(runtime.trusted_theme_files(expected_tree)),
    )


def _preserved_theme_images(
    originals: Mapping[str, Any], updated: Mapping[str, Any], trusted: Mapping[str, str],
) -> tuple[dict[str, Counter[str]], dict[str, str]]:
    """Keep exact old-body root-relative paths, never grant them media approval."""
    paths = {urlsplit(url).path: url for url in trusted
             if url == publication.ORIGIN + urlsplit(url).path}
    occurrences: dict[str, Counter[str]] = {}
    hashes: dict[str, str] = {}
    for slug, document in originals.items():
        if document["post_type"] != "post" or slug in updated:
            continue
        article_id = next((key for key, target in LEGACY_MEDIA_TARGETS.items() if target[0] == slug), slug)
        try:
            markup = project_legacy_media(document["block_markup"], article_id, profile="production").markup
        except LegacyMediaProjectionFailure:
            fail("DISPLAY_PROJECTION_MISMATCH")
        assets = _PageAssets()
        assets.feed(markup)
        assets.close()
        counts = Counter({raw: count for raw, count in assets.image_counts.items() if raw in paths})
        if counts:
            occurrences[slug] = counts
            hashes.update({paths[raw]: trusted[paths[raw]] for raw in counts})
    return occurrences, hashes


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
        report.get("schema") != (
            "RAOS_WORDPRESS_MIXED_BROWSER_AUDIT_V2"
            if envelope.get("schema") == "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_RELEASE_V2"
            else "RAOS_WORDPRESS_MIXED_BROWSER_AUDIT_V1"
        )
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



@dataclass(frozen=True)
class ReaderSeoMetadata:
    """Immutable source bytes, rechecked against the audited theme on every replay."""

    theme_files: tuple[tuple[str, bytes], ...]
    theme_sha256: str

    def to_document(self) -> dict[str, Any]:
        if len(dict(self.theme_files)) != len(self.theme_files):
            fail("READER_THEME_INVALID")
        return _reader_seo_projection(dict(self.theme_files), self.theme_sha256)


def reader_seo_metadata(
    theme_files: Mapping[str, bytes], *, expected_tree: str
) -> ReaderSeoMetadata:
    """Opt in using the registered theme's navigation and approved media projection."""
    result = ReaderSeoMetadata(tuple(sorted(theme_files.items())), expected_tree)
    result.to_document()
    return result


def build_reader_seo_metadata(expected_tree: str) -> ReaderSeoMetadata:
    return reader_seo_metadata(
        runtime.trusted_theme_files(expected_tree), expected_tree=expected_tree
    )


def _reader_seo_projection(files: Mapping[str, bytes], expected_tree: str) -> dict[str, Any]:
    from raos.application.editorial.local_scratch_theme_restore_v1 import (
        theme_tree_sha256,
    )
    from raos.application.editorial.reader_experience_v1 import approved_media_record

    if theme_tree_sha256(files) != expected_tree:
        fail("READER_THEME_CHANGED")
    path = "assets/editorial-navigation.v3.json"
    raw = files.get(path, b"")
    functions = files.get("functions.php", b"").decode("utf-8")
    pins = re.findall(
        r"^const KURASHINOSHIRUBE_EDITORIAL_NAVIGATION_SHA256 = '([a-f0-9]{64})';$",
        functions, re.M,
    )
    if pins != [digest(raw)]:
        fail("READER_NAVIGATION_PIN_INVALID")
    navigation = _json(raw)
    contract = seo.load_contract()
    if (
        navigation.get("schema") != "RAOS_EDITORIAL_THEME_NAVIGATION_V3"
        or navigation.get("target_origin") != contract.origin
    ):
        fail("READER_NAVIGATION_INVALID")
    articles = navigation.get("articles")
    if type(articles) is not list or len(articles) != 10 or not all(
        type(row) is dict for row in articles
    ):
        fail("READER_ARTICLE_SCOPE_INVALID")
    if {row.get("article_code"): row.get("production_slug") for row in articles} != {
        item.identifier: _item_slug(item) for item in contract.items if item.role == "article"
    } or any(
        not isinstance(row.get("article_id"), str)
        or not row["article_id"]
        or any(not isinstance(row.get(key), str) or not row[key]
               for key in ("category_label", "content_role_label"))
        for row in articles
    ):
        fail("READER_ARTICLE_SCOPE_INVALID")
    article_ids = {row["article_id"] for row in articles}
    if len(article_ids) != 10:
        fail("READER_ARTICLE_SCOPE_INVALID")
    registry = navigation.get("reader_navigation")
    hubs = registry.get("hubs") if type(registry) is dict else None
    if type(hubs) is not list or len(hubs) != 15 or any(
        type(row) is not dict or not isinstance(row.get("slug"), str) for row in hubs
    ) or {row["slug"] for row in hubs} != READER_HUB_SLUGS:
        fail("READER_HUB_SCOPE_INVALID")
    for row in hubs:
        if (
            row.get("kind") not in ("categories", "purposes", "category", "purpose", "collection", "updates")
            or any(not isinstance(row.get(key), str) or not row[key]
                   for key in ("label", "description"))
            or type(row.get("article_ids")) is not list
            or not row["article_ids"]
            or any(not isinstance(value, str) for value in row["article_ids"])
            or len(set(row["article_ids"])) != len(row["article_ids"])
            or not set(row["article_ids"]) <= article_ids
        ):
            fail("READER_HUB_SCOPE_INVALID")
    media = navigation.get("media_assets")
    if type(media) is not list:
        fail("READER_MEDIA_INVALID")
    approved = {}
    seen = set()
    for asset in media:
        if type(asset) is not dict or not isinstance(asset.get("asset_ref"), str):
            fail("READER_MEDIA_INVALID")
        ref = asset["asset_ref"]
        if ref in seen:
            fail("READER_MEDIA_AMBIGUOUS")
        seen.add(ref)
        # HTML diagrams have no raster slot. Missing approval never becomes an image.
        if not approved_media_record(asset):
            continue
        if "path" not in asset and "sha256" not in asset:
            continue
        asset_path, expected = asset.get("path"), asset.get("sha256")
        if (
            not isinstance(asset_path, str)
            or re.fullmatch(r"assets/images/[a-z0-9-]+\.(?:webp|svg)", asset_path) is None
            or not isinstance(expected, str)
            or re.fullmatch(r"[a-f0-9]{64}", expected) is None
            or asset_path not in files
            or digest(files[asset_path]) != expected
        ):
            fail("READER_MEDIA_BYTES_INVALID")
        approved[ref] = {
            **asset,
            "url": contract.origin + "/wp-content/themes/kurashinoshirube-child/" + asset_path,
            "width": asset["aspect_ratio"][0],
            "height": asset["aspect_ratio"][1],
        }
    social = {
        _item_slug(item): approved.get(
            next(row["article_id"] for row in articles if row["production_slug"] == _item_slug(item))
            if item.role == "article" else "home"
        )
        for item in contract.items
    }
    social.update({row["slug"]: approved.get("home") for row in hubs})
    return {
        "schema": "RAOS_WORDPRESS_READER_SEO_METADATA_V1",
        "theme_sha256": expected_tree,
        "home_content_mode": (
            "POST_CONTENT" if home_uses_post_content(files) else "TEMPLATE"
        ),
        "navigation_sha256": digest(raw),
        "registry_sha256": digest(manifest_canonical(registry)),
        "articles": articles,
        "hubs": hubs,
        "social_images": social,
        "approved_images": {row["url"]: row["sha256"] for row in approved.values()},
    }


def _item_slug(item: seo.InventoryItem) -> str:
    return "home" if item.role == "home" else urlsplit(item.url).path.strip("/")


def _stored_content_hash(document: Mapping[str, Any]) -> str:
    fields = (
        "schema", "post_type", "id", "status", "title", "slug", "excerpt",
        "block_markup", "taxonomies", "media_ids",
    )
    if not set(fields) <= set(document):
        fail("BASELINE_HASH_INVALID")
    return digest(canonical({key: document[key] for key in fields}).rstrip(b"\n"))


def _reader_inventory(
    envelope: Mapping[str, Any], snapshot: Mapping[str, Any],
    originals: Mapping[str, Mapping[str, Any]], contract: seo.AuditContract,
) -> seo.AuditContract:
    base = {_item_slug(item) for item in contract.items}
    selected = envelope.get("selected_pages")
    inventory = envelope.get("inventory")
    legacy_privacy = (
        snapshot.get("schema") == "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1"
        and type(selected) is dict
        and set(selected) == {"privacy-policy"}
        and envelope.get("selected_articles") == {}
        and "reader_page_slugs" not in snapshot
        and len(base) == 14
    )
    # This compatibility reads the original V1 bytes; it never relabels a
    # snapshot or grants permission to add a hub.
    declared = [] if legacy_privacy else snapshot.get("reader_page_slugs")
    if (
        (snapshot.get("schema") != "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2"
         and not legacy_privacy)
        or snapshot.get("origin") != contract.origin
        or snapshot.get("source") != "BOUNDED_WORDPRESS_EDITOR_MCP"
        or snapshot.get("publication_authority") is not False
        or type(selected) is not dict or not selected
        or type(inventory) is not dict
        or type(declared) is not list
        or any(not isinstance(slug, str) for slug in declared)
        or len(declared) != len(set(declared))
        or not set(declared) <= READER_HUB_SLUGS
        or set(originals) != base | set(declared)
        or set(inventory) != set(originals)
        or not set(selected) <= set(declared) | {"privacy-policy"}
    ):
        fail("CORE_INVENTORY_MISMATCH")
    ids = set()
    for slug, baseline in originals.items():
        identifier = baseline.get("id")
        if (
            type(identifier) is not int or identifier <= 0 or identifier in ids
            or inventory[slug] != {
                "post_id": identifier, "slug": slug, "post_type": baseline.get("post_type"),
                "status": baseline.get("status"), "content_sha256": baseline.get("content_sha256"),
            }
            or baseline.get("slug") != slug
            or baseline.get("post_type") != (
                "post" if slug in {_item_slug(item) for item in contract.items if item.role == "article"}
                else "page"
            )
            or baseline.get("status") not in ("draft", "publish")
            or baseline.get("status") == "draft" and (
                slug not in selected or slug not in READER_HUB_SLUGS
            )
        ):
            fail("BASELINE_INVENTORY_BINDING_INVALID")
        ids.add(identifier)
    for slug, row in selected.items():
        baseline = originals[slug]
        if type(row) is not dict or (
            row.get("kind") != ("reader_privacy" if slug == "privacy-policy" else "hub")
            or type(row.get("post_id")) is not int
            or row.get("post_id") != baseline["id"]
            or row.get("baseline_status") != baseline["status"]
            or row.get("baseline_sha256") != baseline["content_sha256"]
            or not isinstance(row.get("artifact_key"), str) or not row["artifact_key"]
            or any(not isinstance(row.get(key), str) or re.fullmatch(r"[a-f0-9]{64}", row[key]) is None
                   for key in ("template_sha256", "registry_sha256", "production_artifact_sha256"))
            or slug == "privacy-policy" and baseline["status"] != "publish"
        ):
            fail("READER_PAGE_BINDING_INVALID")
    items = contract.items + tuple(
        seo.InventoryItem(contract.origin + "/" + slug + "/", "fixed_page", slug)
        for slug in sorted(set(declared))
    )
    return replace(contract, items=items, content_urls=frozenset(
        item.url for item in items if item.role != "home"
    ))


def _reader_category(metadata: Mapping[str, Any], article_id: str) -> Mapping[str, Any]:
    categories = [hub for hub in metadata["hubs"]
                  if hub["kind"] == "category" and article_id in hub["article_ids"]]
    if len(categories) != 1:
        fail("READER_ARTICLE_CATEGORY_INVALID")
    return categories[0]


def _reader_structured_data_semantics(
    graph: dict[str, Any] | None, item: seo.InventoryItem,
    contract: seo.AuditContract, title: str, description: str,
    metadata: Mapping[str, Any], documents: Mapping[str, Any],
) -> bool:
    asset = metadata["social_images"][_item_slug(item)]
    image = asset["url"] if asset is not None else ""
    if item.role != "article":
        return seo._structured_data_semantics(graph, item, contract, title, description, image)
    articles = [row for row in metadata["articles"]
                if row["article_code"] == item.identifier and row["production_slug"] == _item_slug(item)]
    if len(articles) != 1:
        return False
    category = _reader_category(metadata, articles[0]["article_id"])
    hub_slug = category["slug"]
    hub_url = contract.origin + "/" + hub_slug + "/"
    hub = documents.get(hub_slug, {})
    # These documents have already passed candidate/baseline identity and hash
    # checks. The theme links a hub as soon as its page is published (fail-open);
    # the crumb label is the hub page's own stored title.
    hub_title = hub.get("title")
    published_hub = (
        any(entry.role == "fixed_page" and entry.identifier == hub_slug and entry.url == hub_url
            for entry in contract.items)
        and hub.get("slug") == hub_slug and hub.get("post_type") == "page"
        and hub.get("status") == "publish"
        and isinstance(hub_title, str) and hub_title.strip() != ""
    )
    breadcrumbs = [
        {"@type": "ListItem", "item": contract.origin + "/", "name": "ホーム", "position": 1},
    ]
    if published_hub:
        breadcrumbs.append({"@type": "ListItem", "item": hub_url, "name": hub_title, "position": 2})
    breadcrumbs.append({"@type": "ListItem", "item": item.url, "name": title, "position": len(breadcrumbs) + 1})
    if graph is None or type(graph.get("@graph")) is not list:
        return False
    nodes = graph["@graph"]
    if any(type(node) is not dict or not isinstance(node.get("@type"), str)
           or not isinstance(node.get("@id"), str) for node in nodes):
        return False
    if sorted(node["@type"] for node in nodes) != [
        "Article", "BreadcrumbList", "Organization", "Organization", "WebSite",
    ]:
        return False
    by_id = {node["@id"]: node for node in nodes}
    if len(by_id) != len(nodes):
        return False
    org = contract.origin + "/#organization"
    team = contract.origin + "/#editorial-team"
    website = contract.origin + "/#website"
    if org not in by_id or website not in by_id or team not in by_id:
        return False
    common = {"@context": graph.get("@context"), "@graph": [by_id[org], by_id[website]]}
    home = next(entry for entry in contract.items if entry.role == "home")
    if not seo._structured_data_semantics(common, home, contract, title, description, ""):
        return False
    if not seo._editorial_team_semantics(by_id[team], contract):
        return False
    article = by_id.get(item.url + "#article", {})
    published, modified = article.get("datePublished"), article.get("dateModified")
    if not seo._valid_utc_text(published) or not seo._valid_utc_text(modified):
        return False
    return (
        modified >= published
        and article == {
            "@id": item.url + "#article", "@type": "Article",
            "articleSection": category["label"], "author": {"@id": team},
            "breadcrumb": {"@id": item.url + "#breadcrumb"},
            "datePublished": published, "dateModified": modified,
            "description": description, "headline": title,
            "inLanguage": "ja-JP", "mainEntityOfPage": item.url,
            "publisher": {"@id": org}, "url": item.url,
            **({"image": [image]} if asset is not None else {}),
        }
        and by_id.get(item.url + "#breadcrumb") == {
            "@id": item.url + "#breadcrumb", "@type": "BreadcrumbList",
            "itemListElement": breadcrumbs,
        }
    )


def _reader_seo_report(
    report: dict[str, Any], contract: seo.AuditContract,
    transport: _ObservedTransport, metadata: Mapping[str, Any], documents: Mapping[str, Any],
) -> None:
    """Check trusted reader taxonomy and media against candidate-bound documents."""
    for item, row in zip(contract.items, report["pages"], strict=True):
        response = transport.get(item.url)
        parser = seo._SeoHtmlParser()
        parser.feed(response.body.decode("utf-8"))
        asset = metadata["social_images"][_item_slug(item)]
        checks = row["checks"]
        def check(ok: bool, detail: str) -> dict[str, str]:
            return seo._check(ok, response.body_sha256, response.observed_at, detail)
        if asset is None:
            for key in ("og_image", "og_image_width", "og_image_height", "og_image_type", "twitter_image"):
                del checks[key]
            checks["social_image_absent"] = check(
                not any(
                    str(meta.get(key, "")).lower().startswith(("og:image", "twitter:image"))
                    for meta in parser.meta for key in ("property", "name")
                ), "APPROVED_PROJECTION_HAS_NO_IMAGE_SLOT",
            )
            checks["twitter_card"] = check(
                seo._meta_values(parser, "name", "twitter:card") == ["summary"],
                "EXACT_SUMMARY_WITHOUT_IMAGE",
            )
        else:
            for key, prop, wanted in (
                ("og_image", "og:image", asset["url"]),
                ("og_image_width", "og:image:width", str(asset["width"])),
                ("og_image_height", "og:image:height", str(asset["height"])),
            ):
                checks[key] = check(
                    seo._meta_values(parser, "property", prop) == [wanted],
                    "EXACT_APPROVED_MEDIA_VALUE",
                )
            checks["twitter_image"] = check(
                seo._meta_values(parser, "name", "twitter:image") == [asset["url"]],
                "EXACT_APPROVED_MEDIA_VALUE",
            )
        graph, _types = seo._single_graph(parser)
        descriptions = seo._meta_values(parser, "name", "description")
        checks["structured_data_semantics"] = check(
            _reader_structured_data_semantics(
                graph, item, contract, " ".join("".join(parser.title_parts).split()),
                descriptions[0] if len(descriptions) == 1 else "", metadata, documents,
            ), "EXACT_READER_GRAPH_WITH_APPROVED_IMAGE" if asset is not None else "EXACT_GRAPH_WITH_NO_IMAGE_CLAIM",
        )
        row["status"] = "PASS" if all(v["status"] == "PASS" for v in checks.values()) else "FAIL"
    report["surfaces"]["sitemap"]["detail"] = f"EXACT_{len(contract.content_urls)}_CONTENT_URLS"
    report["status"] = "PASS" if (
        all(row["status"] == "PASS" for row in report["pages"])
        and all(row["status"] == "PASS" for row in report["surfaces"].values())
    ) else "FAIL"


def _reader_hub_body(
    slug: str, metadata: Mapping[str, Any], documents: Mapping[str, Any],
    public_metadata: Mapping[str, Any],
) -> str:
    hubs = metadata["hubs"]
    hub = next(row for row in hubs if row["slug"] == slug)
    cards = []
    if hub["kind"] in ("categories", "purposes"):
        kind = "category" if hub["kind"] == "categories" else "purpose"
        for child in hubs:
            if child["kind"] != kind or child["slug"] not in documents:
                continue
            cards.append(
                '<li><a class="raos-guide-card raos-taxonomy-card" href="/' + child["slug"] + '/">'
                '<span class="raos-guide-card__title" role="heading" aria-level="3">' + escape(child["label"]) + '</span>'
                '<span class="raos-guide-card__excerpt">' + escape(child["description"]) + '</span>'
                '<span class="raos-guide-card__date">' + str(len(child["article_ids"]))
                + '記事を読む <span aria-hidden="true">→</span></span></a></li>'
            )
        grid = "raos-guide-grid raos-taxonomy-grid"
    else:
        rows = [row for row in metadata["articles"] if row["article_id"] in hub["article_ids"]]
        if hub["kind"] == "updates":
            rows.sort(key=lambda row: public_metadata[row["production_slug"]]["dates"]["modified"], reverse=True)
        for row in rows:
            article_slug = row["production_slug"]
            category = _reader_category(metadata, row["article_id"])
            document = documents[article_slug]
            date = datetime.fromisoformat(public_metadata[article_slug]["dates"]["modified"])
            asset = metadata["social_images"][article_slug]
            media = "" if asset is None else (
                '<span class="raos-guide-card__media"><img src="' + escape(asset["url"], quote=True)
                + '" alt="' + escape(asset["alt"], quote=True)
                + '" width="' + str(asset["width"]) + '" height="' + str(asset["height"])
                + '" loading="lazy" decoding="async"><span class="raos-guide-card__caption">'
                + escape(asset["caption"]) + '</span></span>'
            )
            cards.append(
                '<li><a class="raos-guide-card" href="/' + article_slug + '/">' + media
                + '<span class="raos-article-category">' + escape(category["label"] + " / " + row["content_role_label"]) + '</span>'
                '<span class="raos-guide-card__title" role="heading" aria-level="3">' + escape(document["title"]) + '</span>'
                '<span class="raos-guide-card__excerpt">' + escape(document["excerpt"]) + '</span>'
                '<span class="raos-guide-card__date">更新 ' + f"{date.year}年{date.month}月{date.day}日" + '</span></a></li>'
            )
        grid = "raos-guide-grid"
    body = ('<h2>条件から読み始める</h2><ul class="' + grid + '">' + "".join(cards) + "</ul>"
            if cards else "<p>現在、条件に合う公開記事はありません。</p>")
    return '<div class="raos-reader-hub"><p>' + escape(hub["description"]) + "</p>" + body + "</div>"



def _reader_runtime_binding(
    envelope: Mapping[str, Any], profile: runtime.ReaderMeasurementRuntime | None,
    mode: str,
) -> None:
    if mode not in ("release", "post-activation-readback"):
        fail("READER_MEASUREMENT_BINDING_MODE_INVALID")
    binding = envelope.get("reader_measurement")
    if profile is None:
        if binding is not None or mode != "release":
            fail("READER_MEASUREMENT_BINDING_MISSING")
        return
    if type(profile) is not runtime.ReaderMeasurementRuntime:
        fail("READER_MEASUREMENT_BINDING_INVALID")
    if mode == "post-activation-readback" and profile.expected_collection_enabled is not True:
        fail("READER_MEASUREMENT_BINDING_STATE_INVALID")
    if mode == "release" and (binding is None or profile.expected_collection_enabled is not False):
        fail("READER_MEASUREMENT_BINDING_MISSING")
    if binding is not None and (
        type(binding) is not dict or binding != {
            "schema": "RAOS_READER_MEASUREMENT_RELEASE_V1",
            "profile": profile.profile,
            "manifest_sha256": profile.manifest_sha256,
            "policy_sha256": profile.policy_sha256,
            "contract_sha256": profile.contract_sha256,
            "revision": profile.revision,
            "expected_collection_enabled": False,
        } or binding.get("expected_collection_enabled") is not False
    ):
        fail("READER_MEASUREMENT_BINDING_MISMATCH")


def _reader_runtime_status(
    site_status: Mapping[str, Any], profile: runtime.ReaderMeasurementRuntime | None,
) -> None:
    status = site_status.get("reader_measurement")
    if profile is None:
        if status is not None and (
            type(status) is not dict or status.get("plugin_active") is not False
            or (status.get("collection_enabled") is not False and status.get("collection_enabled") is not None)
        ):
            fail("READER_MEASUREMENT_NOT_DECLARED")
        return
    if type(profile) is not runtime.ReaderMeasurementRuntime:
        fail("READER_MEASUREMENT_PROFILE_INVALID")
    if (
        type(status) is not dict
        or status.get("schema") != "RAOSReaderMeasurementStatusV1"
        or status.get("plugin_active") is not True
        or status.get("plugin_version") != profile.plugin_version
        or status.get("collection_enabled") is not profile.expected_collection_enabled
        or status.get("contract_sha256") != profile.contract_sha256
        or status.get("policy_sha256") != profile.policy_sha256
        or status.get("approved_revision") != (
            profile.revision if profile.expected_collection_enabled else None
        )
        or profile.profile != "reader-minimal-v1"
        or type(profile.expected_collection_enabled) is not bool
    ):
        fail("READER_MEASUREMENT_STATUS_MISMATCH")
    cleanup = status.get("cleanup")
    if type(cleanup) is not dict or (
        cleanup.get("healthy") is not True or cleanup.get("last_error_code") is not None
        or not isinstance(cleanup.get("last_success_date"), str)
    ):
        fail("READER_MEASUREMENT_CLEANUP_UNVERIFIED")
    try:
        datetime.strptime(cleanup["last_success_date"], "%Y-%m-%d")
    except ValueError:
        fail("READER_MEASUREMENT_CLEANUP_UNVERIFIED")


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
    reader_metadata: ReaderSeoMetadata | None = None,
    reader_measurement: runtime.ReaderMeasurementRuntime | None = None,
    reader_measurement_mode: str = "release",
    external_image_fetch: Callable[
        [str], baseline_media.ImageResponse
    ] = baseline_media.fetch_image,
) -> dict[str, object]:
    """Every bound URL: semantic SEO plus candidate/baseline-exact readback.

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
    _reader_runtime_binding(envelope, reader_measurement, reader_measurement_mode)
    legacy_runtime = (
        reader_measurement is None and "reader_measurement" not in envelope
        and not any(row.get("kind") == "reader_privacy" for row in envelope.get("selected_pages", {}).values())
    )
    try:
        publication.validate_site_status(
            site_status_readback,
            require_measurement_off=reader_measurement_mode != "post-activation-readback",
            **({"allow_legacy_runtime": True} if legacy_runtime else {}),
        )
    except publication.PublicationFailure:
        if reader_measurement is None:
            raise
        fail("SITE_STATUS_INVALID")
    # An explicit reader ON readback never opens the legacy eight-event collector.
    if site_status_readback.get("measurement", {}).get("collection_enabled") is not False:
        fail("LEGACY_MEASUREMENT_NOT_OFF")
    _reader_runtime_status(site_status_readback, reader_measurement)
    is_v2 = envelope["schema"] == "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_RELEASE_V2"
    if is_v2 and reader_metadata is None or reader_measurement is not None and reader_metadata is None:
        fail("READER_METADATA_REQUIRED")
    if reader_metadata is not None and type(reader_metadata) is not ReaderSeoMetadata:
        fail("READER_METADATA_INVALID")
    reader = reader_metadata.to_document() if reader_metadata is not None else None
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
    if is_v2:
        if len(originals) != len(original_snapshot["documents"]):
            fail("CORE_INVENTORY_MISMATCH")
        contract = _reader_inventory(envelope, original_snapshot, originals, contract)
    slugs = {
        "home" if item.role == "home" else urlsplit(item.url).path.strip("/")
        for item in contract.items
    }
    if (
        len(originals) != len(contract.items)
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
    if reader is not None:
        baselines = original_snapshot.get("all_document_baselines", {})
        if not isinstance(baselines, Mapping):
            fail("UNSELECTED_DOCUMENT_CHANGED")
        expected_extra = {
            str(key): row for key, row in baselines.items()
            if isinstance(row, Mapping) and row.get("slug") not in slugs
        }
        observed_extra = {}
        ids = [row.get("id") for row in current_documents.values()]
        if len(ids) != len(set(ids)):
            fail("UNSELECTED_DOCUMENT_CHANGED")
        for slug, row in current_documents.items():
            if slug in slugs:
                continue
            if row.get("slug") != slug or publication.sha256_json({
                "schema": "ContentDocumentV1", "id": row.get("id"),
                "status": row.get("status"), **publication.document_projection(row),
            }) != row.get("content_sha256"):
                fail("UNSELECTED_DOCUMENT_CHANGED")
            observed_extra[str(row["id"])] = publication._baseline_record(row)
        if observed_extra != expected_extra:
            fail("UNSELECTED_DOCUMENT_CHANGED")
    expected_hashes: dict[str, str] = {
        **envelope["unchanged_documents"],
        **envelope["expected_production_content_sha256"],
    }
    if reader is not None and (
        set(expected_hashes) != slugs
        or set(envelope["unchanged_documents"]) & set(envelope["expected_production_content_sha256"])
        or not set(envelope.get("selected_pages", {})) <= set(envelope["expected_production_content_sha256"])
    ):
        fail("PREPARED_TARGET_SET_MISMATCH")
    prepared = preparation["production_documents"]
    if set(prepared) != set(envelope["expected_production_content_sha256"]):
        fail("PREPARED_TARGET_SET_MISMATCH")
    expected = {}
    for slug in sorted(slugs):
        baseline, observed = originals[slug], current[slug]
        baseline_hash = (_stored_content_hash(baseline) if is_v2
                         else publication._content_after_sha256(baseline, baseline["id"]))
        if baseline_hash != baseline.get("content_sha256"):
            fail("BASELINE_HASH_INVALID")
        status = "publish" if is_v2 and slug in envelope["selected_pages"] else baseline.get("status")
        if any(
            observed.get(key) != baseline.get(key)
            for key in ("id", "slug", "post_type")
        ) or observed.get("status") != status or (
            reader is not None and (type(observed.get("id")) is not int or observed["id"] <= 0)
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
        if is_v2 and slug in envelope["selected_pages"]:
            page_row = envelope["selected_pages"][slug]
            artifact_sha = digest(target["block_markup"].encode())
            if artifact_sha != page_row["template_sha256"] or artifact_sha != page_row["production_artifact_sha256"]:
                fail("READER_PAGE_ARTIFACT_CHANGED")
            if page_row["kind"] == "hub" and page_row["registry_sha256"] != reader["registry_sha256"]:
                fail("READER_HUB_REGISTRY_CHANGED")
        if reader is not None and slug in READER_HUB_SLUGS:
            registered = next(row for row in reader["hubs"] if row["slug"] == slug)
            template = '<!-- wp:shortcode -->[kurashinoshirube_reader_hub slug="' + slug + '"]<!-- /wp:shortcode -->'
            if (target["block_markup"] != template or target["title"] != registered["label"]
                or target["excerpt"] != registered["description"]):
                fail("READER_HUB_TEMPLATE_CHANGED")
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
    if reader is not None and reader["theme_sha256"] != expected_tree:
        fail("READER_THEME_CHANGED")
    home_head, theme_images, runtime_resources = _theme_expectations(expected_tree)
    preserved_counts: dict[str, Counter[str]] = {}
    preserved_hashes: dict[str, str] = {}
    if reader is not None:
        preserved_counts, preserved_hashes = _preserved_theme_images(originals, prepared, theme_images)
        theme_images = dict(reader["approved_images"])
    preserved_paths = {raw for counts in preserved_counts.values() for raw in counts}
    resources = runtime._reader_resources(runtime_resources, reader_measurement)
    if reader_measurement is not None:
        if digest(expected["privacy-policy"]["block_markup"].encode()) != reader_measurement.policy_sha256:
            fail("READER_MEASUREMENT_POLICY_CHANGED")
        runtime_articles = json.loads(reader_measurement.articles)
        if (type(runtime_articles) is not list or len(runtime_articles) != 10
            or any(type(row) is not dict for row in runtime_articles)
            or {row.get("article_id"): row.get("slug") for row in runtime_articles}
            != {row["article_id"]: row["production_slug"] for row in reader["articles"]}):
            fail("READER_MEASUREMENT_ARTICLE_SCOPE_CHANGED")
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
        or set(baseline_metadata) != (
            {slug for slug in slugs if originals[slug]["status"] == "publish"}
            if is_v2 else slugs
        )
    ):
        fail("PUBLIC_METADATA_UNVERIFIED")
    for row in cast(dict[str, Any], metadata["documents"]).values():
        _require_current_timestamp(row["evidence"]["retrieved_at"], now)
    for slug in slugs:
        if replayed[slug]["dates"]["modified_gmt"] < replayed[slug]["dates"]["date_gmt"]:
            fail("PUBLIC_METADATA_DATE_ORDER_INVALID")
        if slug not in baseline_metadata:
            # A draft has no captured publication date. Only fresh post-publish
            # REST evidence cross-checked against current MCP fields supplies it.
            continue
        if (
            replayed[slug]["dates"]["date_gmt"]
            != baseline_metadata[slug]["dates"]["date_gmt"]
            or replayed[slug]["taxonomies"] != baseline_metadata[slug]["taxonomies"]
        ):
            fail("PUBLISHED_DATE_OR_TAXONOMY_CHANGED")
        if slug not in prepared and replayed[slug] != baseline_metadata[slug]:
            fail("UNTOUCHED_METADATA_CHANGED")
    observed_http = _ObservedTransport(
        transport
        or seo.BoundedHttpsTransport(
            contract, allowed_resource_urls=frozenset(resources) | frozenset(theme_images) | frozenset(preserved_hashes),
            **({"reader_measurement": reader_measurement} if reader_measurement is not None else {}),
        ),
        now,
    )
    report = seo.run_audit(observed_http, contract)
    if reader is not None:
        _reader_seo_report(report, contract, observed_http, reader, current)
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
        social_asset = reader["social_images"][slug] if reader is not None else None
        if reader is None:
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
        elif social_asset is not None:
            image_urls.add(social_asset["url"])
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
        body_markup = (
            _reader_hub_body(slug, reader, current, replayed)
            if reader is not None and slug in READER_HUB_SLUGS
            else target["block_markup"]
        )
        home_post_content = item.role == "home" and reader is not None and reader["home_content_mode"] == "POST_CONTENT"
        projection_sha = (
            verify_rendered_home_body(body_markup, markup)
            if home_post_content else None if item.role == "home" else verify_rendered_body(
                body_markup,
                markup,
                article_id=display_article_id if item.role == "article" else None,
            )
        )
        evidence = publication._PublicPageEvidenceParser()
        evidence.feed(markup)
        if item.role != "home" and evidence.h1_titles != [target["title"]]:
            fail("PUBLIC_H1_MISMATCH")
        assets = _PageAssets(verified_home_body=home_post_content)
        assets.feed(markup)
        assets.close()
        expected_preserved = preserved_counts.get(slug, Counter())
        observed_preserved = Counter({
            raw: count for raw, count in assets.image_counts.items()
            if raw in preserved_paths or raw in preserved_hashes and raw not in theme_images
        })
        if observed_preserved != expected_preserved:
            fail("BASELINE_THEME_IMAGE_OCCURRENCES_CHANGED")
        if (assets.measurement_scripts and reader_measurement is None) or page.header_values("set-cookie"):
            fail("PUBLIC_MEASUREMENT_OFF_MISMATCH")
        runtime_options = {}
        if reader_measurement is not None:
            runtime_options["reader_measurement"] = reader_measurement
        if home_post_content:
            runtime_options["preserved_home_style"] = _preserved_home_style(body_markup)
        runtime_evidence = runtime.verify_page(page, runtime_resources, observed_http, **runtime_options)
        if item.role == "home" and not home_post_content:
            if reader is None:
                required_routes = {entry.url for entry in contract.items if entry.role == "article"}
            else:
                # The approved home exposes category/purpose cards and its guide
                # entry set; it no longer promises ten direct article links.
                required_routes = {
                    contract.origin + "/" + row["slug"] + "/"
                    for row in reader["hubs"]
                    if row["kind"] in ("category", "purpose") and row["slug"] in slugs
                }
                guide_ids = next(row["article_ids"] for row in reader["hubs"] if row["slug"] == "guides")
                required_routes.update(
                    contract.origin + "/" + row["production_slug"] + "/"
                    for row in reader["articles"] if row["article_id"] in guide_ids
                )
            if not required_routes <= assets.links:
                fail("HOME_ARTICLE_ROUTES_MISSING")
        image_urls.update(publication.ORIGIN + raw if raw in expected_preserved else raw for raw in assets.images)
        page_bindings[slug] = {
            "url": item.url,
            "post_id": current[slug]["id"],
            "state": "UPDATED" if slug in prepared else "PRESERVED",
            "content_sha256": current[slug]["content_sha256"],
            "rendered_body_projection_sha256": projection_sha,
            "legacy_media_display_projection": display_proof,
            "public_response_sha256": page.body_sha256,
            "public_headers_sha256": page.headers_sha256,
            "measurement_state": "CLOSED_DECLARED_RUNTIME_VERIFIED",
            "runtime_resources": runtime_evidence,
        }
        if reader is not None:
            page_bindings[slug].update({
                "baseline_status": originals[slug]["status"],
                "status": current[slug]["status"],
                "public_dates": replayed[slug]["dates"],
                "baseline_publication_date": (
                    "NOT_REQUIRED" if originals[slug]["status"] == "draft"
                    else baseline_metadata[slug]["dates"]["date_gmt"]
                ),
                "social_image_state": "NOT_INCLUDED" if social_asset is None else "VERIFIED_PRESENT",
                "social_image": social_asset,
            })
            if expected_preserved:
                page_bindings[slug]["baseline_preserved_theme_images"] = {
                    raw: {"state": "BASELINE_PRESERVED", "count": count,
                          "url": publication.ORIGIN + raw, "sha256": preserved_hashes[publication.ORIGIN + raw]}
                    for raw, count in sorted(expected_preserved.items())
                }
    image_bindings = {}
    non_theme_urls = image_urls - set(theme_images) - set(preserved_hashes)
    baseline_urls = set()
    for document in original_snapshot["documents"]:
        if document["post_type"] == "post" and document["slug"] not in prepared:
            baseline_urls.update(baseline_media.image_urls(document["block_markup"]))
    if non_theme_urls - baseline_urls:
        # Same-origin pixels outside entry-content are not trusted simply because
        # they return 200 image/*; reject before requesting an unapproved URL.
        fail("PUBLIC_IMAGE_IDENTITY_UNVERIFIED")
    baseline_images = (
        _baseline_image_expectations(envelope, candidate_path, original_snapshot)
        if non_theme_urls
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
        if url in preserved_hashes and response.body_sha256 != preserved_hashes[url]:
            fail("BASELINE_THEME_IMAGE_BYTES_MISMATCH")
        image_bindings[url] = response.body_sha256
    result = {
        "schema": SCHEMA_V2 if reader is not None else SCHEMA,
        "publication_profile": "verified-incremental",
        "link_mode": "standard-api",
        "measurement_collection_enabled": False,
        "measurement_assessment": "CLOSED_DECLARED_RUNTIME_VERIFIED",
        "publication_authority": False,
        "status": "PUBLIC_READBACK_PASSED",
        "release_sha256": context.sha256,
        "manifest_sha256": envelope["manifest_sha256"],
        "snapshot_sha256": digest(canonical(original_snapshot)),
        "candidate_preparation_sha256": digest(prep_raw),
        "site_status_sha256": digest(canonical(site_status_readback)),
        "theme_tree_sha256": expected_tree,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "core_document_count": len(contract.items),
        "page_evidence": page_bindings,
        "public_metadata_sha256": digest(canonical(metadata)),
        "seo_report_sha256": digest(canonical(report)),
        "image_evidence_sha256": digest(canonical(image_bindings)),
        "monetization_state": envelope["monetization_state"],
        "not_verified_by_this_report": [
            "real_reader_tests",
            "live_browser_interaction",
            "conditional_or_service_worker_network_activity",
            "external_checkout",
            "search_ranking",
            "revenue",
        ],
    }
    if reader is not None:
        result["reader_metadata_sha256"] = digest(canonical(reader))
        result["reader_measurement"] = (
            {"profile": reader_measurement.profile,
             "manifest_sha256": reader_measurement.manifest_sha256,
             "contract_sha256": reader_measurement.contract_sha256,
             "policy_sha256": reader_measurement.policy_sha256,
             "revision": reader_measurement.revision,
             "expected_collection_enabled": reader_measurement.expected_collection_enabled,
             "mode": reader_measurement_mode,
             "state": "DECLARED_RUNTIME_AND_MCP_STATUS_VERIFIED"}
            if reader_measurement is not None else {"state": "NOT_INCLUDED"}
        )
    return {**result, "binding_sha256": digest(canonical(result))}
