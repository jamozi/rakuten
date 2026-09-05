"""Closed declared-runtime verification, not a substitute for browser observation.

Only two audited theme scripts and three pinned core modules may execute. No
provider-name denylist, arbitrary inline JS, plugin directory wildcard, or live
response learned as an expected hash is accepted. All network reads are public.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any, NoReturn

import raos_wordpress_seo_audit as seo
from raos.application.editorial.verified_incremental_v1 import (
    DNS_HINT,
    DNS_TRANSITION_MODE,
    DNS_TRANSITION_STATE,
    canonical,
    validate_dns_transition,
)

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://kurashinoshirube.com"
THEME_PREFIX = ORIGIN + "/wp-content/themes/kurashinoshirube-child/"
BRAND_ICON_PATH = "assets/images/brand-mark.svg"
LOCK = ROOT / "changes/wordpress-local-preview-v1/wordpress-runtime.lock.json"
THEME_ASSETS = frozenset(
    {
        "assets/analytics-consent-gate.js",
        "assets/editorial-navigation.js",
        "assets/theme.css",
        "assets/editorial-v2.css",
    }
)
DNS_REMOVAL_SOURCE = """function kurashinoshirube_remove_google_dns_prefetch(array $urls, string $relation_type): array
{
    if ($relation_type !== 'dns-prefetch') {
        return $urls;
    }
    foreach ($urls as $key => $entry) {
        if ($entry === '//www.googletagmanager.com') {
            unset($urls[$key]);
        }
    }
    return $urls;
}
add_filter('wp_resource_hints', 'kurashinoshirube_remove_google_dns_prefetch', PHP_INT_MAX, 2);
""".encode()
DIRECTIVES = {
    "nav": {"data-wp-interactive": {"core/navigation"}},
    "form": {
        "data-wp-interactive": {"core/search"},
        "data-wp-class--wp-block-search__searchfield-hidden": {
            "!context.isSearchInputVisible"
        },
        "data-wp-on--keydown": {"actions.handleSearchKeydown"},
        "data-wp-on--focusout": {"actions.handleSearchFocusout"},
    },
    "button": {
        "data-wp-bind--aria-controls": {"state.ariaControls"},
        "data-wp-bind--aria-expanded": {"context.isSearchInputVisible"},
        "data-wp-bind--aria-label": {"state.ariaLabel"},
        "data-wp-bind--type": {"state.type"},
        "data-wp-on--click": {
            "actions.openSearchInput",
            "actions.closeMenuOnClick",
            "actions.openMenuOnClick",
        },
        "data-wp-on--keydown": {"actions.handleMenuKeydown"},
    },
    "div": {
        "data-wp-bind--aria-modal": {"state.ariaModal"},
        "data-wp-bind--aria-label": {"state.ariaLabel"},
        "data-wp-bind--role": {"state.roleAttribute"},
        "data-wp-class--has-modal-open": {"state.isMenuOpen"},
        "data-wp-class--is-menu-open": {"state.isMenuOpen"},
        "data-wp-watch": {"callbacks.initMenu", "callbacks.focusFirstElement"},
        "data-wp-on--keydown": {"actions.handleMenuKeydown"},
        "data-wp-on--focusout": {"actions.handleMenuFocusout"},
    },
    "input": {
        "data-wp-bind--aria-hidden": {"!context.isSearchInputVisible"},
        "data-wp-bind--tabindex": {"state.tabindex"},
    },
    "script": {
        "data-wp-strategy": {"defer"},
        "data-wp-router-options": {'{"loadOnClientNavigation":true}'},
    },
}
SPECULATION = {
    "prefetch": [
        {
            "source": "document",
            "where": {
                "and": [
                    {"href_matches": "/*"},
                    {
                        "not": {
                            "href_matches": [
                                "/wp-*.php",
                                "/wp-admin/*",
                                "/wp-content/uploads/*",
                                "/wp-content/*",
                                "/wp-content/plugins/*",
                                "/wp-content/themes/kurashinoshirube-child/*",
                                "/wp-content/themes/twentytwentyfive/*",
                                "/*\\?(.+)",
                            ]
                        }
                    },
                    {"not": {"selector_matches": 'a[rel~="nofollow"]'}},
                    {"not": {"selector_matches": ".no-prefetch, .no-prefetch a"}},
                ]
            },
            "eagerness": "conservative",
        }
    ],
}


def fail() -> NoReturn:
    raise seo.AuditError("INCREMENTAL_PUBLIC_MEASUREMENT_OFF_MISMATCH")


def unique_json(text: str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                fail()
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=unique)
    except ValueError:
        fail()


def validate_directives(tag: str, attrs: Mapping[str, str | None]) -> None:
    for key, value in attrs.items():
        if not key.startswith("data-wp-"):
            continue
        if key == "data-wp-context":
            context = unique_json(value or "")
            if type(context) is not dict:
                fail()
            if tag == "nav" and attrs.get("data-wp-interactive") == "core/navigation":
                expected = {
                    "overlayOpenedBy": {"click": False, "hover": False, "focus": False},
                    "type": "overlay",
                    "roleAttribute": "",
                    "ariaLabel": context.get("ariaLabel"),
                }
                if context != expected or type(context.get("ariaLabel")) is not str:
                    fail()
            elif tag == "form" and attrs.get("data-wp-interactive") == "core/search":
                if (
                    set(context)
                    != {
                        "isSearchInputVisible",
                        "inputId",
                        "ariaLabelExpanded",
                        "ariaLabelCollapsed",
                    }
                    or type(context["isSearchInputVisible"]) is not bool
                    or type(context["inputId"]) is not str
                    or re.fullmatch(
                        r"wp-block-search__input-\d{1,6}", context["inputId"]
                    )
                    is None
                    or any(
                        type(context[name]) is not str
                        for name in ("ariaLabelExpanded", "ariaLabelCollapsed")
                    )
                ):
                    fail()
            else:
                fail()
        elif key == "data-wp-router-options" and tag == "script":
            if unique_json(value or "") != {"loadOnClientNavigation": True}:
                fail()
        elif value not in DIRECTIVES.get(tag, {}).get(key, set()):
            # Exact names intentionally reject namespace/suffix variants too.
            fail()


def inert_css(text: str) -> None:
    # Deliberately conservative: current inline layout CSS has no escapes or
    # fetch functions. Strip comments before inspection, never decode away risk.
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    if re.search(
        r"\\|/\*|@import|@font-face|(?:url|src|image|image-set|expression)\s*\(|(?<![-\w])behavior\s*:|-moz-binding",
        text,
        re.I,
    ):
        fail()


@dataclass(frozen=True)
class Resource:
    sha256: str
    size: int
    kind: str
    module_id: str | None = None
    dependencies: tuple[str, ...] = ()


def theme_asset_version(files: Mapping[str, bytes], path: str, revision: str) -> str:
    """Recognize the two legacy enqueues in already tree-verified theme bytes.

    This is not a general PHP evaluator or permission to accept a live version.
    The baseline uses the theme header for CSS only; current assets use the
    runtime revision. Unknown enqueue shapes do not gain a version alternative.
    """
    legacy_styles = {
        "assets/theme.css": ("kurashinoshirube-editorial", ""),
        "assets/editorial-v2.css": (
            "kurashinoshirube-editorial-v2",
            "'kurashinoshirube-editorial'",
        ),
    }
    if path not in legacy_styles:
        return revision
    handle, dependencies = legacy_styles[path]
    functions = files.get("functions.php", b"").decode("utf-8", errors="strict")
    enqueue = (
        r"wp_enqueue_style\(\s*'" + re.escape(handle) + r"',\s*"
        r"get_stylesheet_directory_uri\(\)\s*\.\s*'/" + re.escape(path) + r"',\s*"
        r"array\(" + re.escape(dependencies) + r"\),\s*"
        r"\$theme->get\('Version'\)\s*\);"
    )
    matches = re.findall(enqueue, functions)
    if not matches:
        return revision
    if len(matches) != 1:
        fail()
    header = files.get("style.css", b"").decode("utf-8", errors="strict")
    headers = re.findall(r"^Version:\s*([^\r\n]+)$", header, re.M)
    constants = re.findall(
        r"^const KURASHINOSHIRUBE_THEME_VERSION = '([^']+)';$", functions, re.M
    )
    if (
        len(headers) != 1
        or headers != constants
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", headers[0]) is None
    ):
        fail()
    return headers[0]


def resources_for_theme(files: Mapping[str, bytes]) -> dict[str, Resource]:
    functions = files.get("functions.php", b"").decode("utf-8", errors="strict")
    versions = re.findall(
        r"^const KURASHINOSHIRUBE_THEME_RUNTIME_REVISION = '([a-f0-9]{64})';$",
        functions,
        re.M,
    )
    if len(versions) != 1:
        fail()
    resources = {}
    for path in sorted(THEME_ASSETS):
        if path not in files:
            continue  # Older audited theme may lack the article navigation file.
        raw = files[path]
        dependencies = []
        if path.endswith(".css"):
            # Only literal relative references into the same audited image tree.
            pattern = r'url\("(images/[a-z0-9.-]+\.(?:svg|webp|png))"\)'
            for image_path in re.findall(pattern, raw.decode("utf-8")):
                image_path = "assets/" + image_path
                if image_path not in files:
                    fail()
                url = THEME_PREFIX + image_path
                dependencies.append(url)
                payload = files[image_path]
                resources[url] = Resource(seo._sha256(payload), len(payload), "image")
            inert_css(re.sub(pattern, "", raw.decode("utf-8")))
        version = theme_asset_version(files, path, versions[0])
        resources[THEME_PREFIX + path + "?ver=" + version] = Resource(
            seo._sha256(raw),
            len(raw),
            "css" if path.endswith(".css") else "js",
            dependencies=tuple(sorted(set(dependencies))),
        )
    # Register last: the same SVG may also be a CSS image dependency. Preserve
    # its stricter MIME contract in either role instead of overwriting it with
    # the generic image kind while collecting stylesheet dependencies.
    if BRAND_ICON_PATH in files:
        icon = files[BRAND_ICON_PATH]
        resources[THEME_PREFIX + BRAND_ICON_PATH] = Resource(
            seo._sha256(icon), len(icon), "icon"
        )
    lock = unique_json(LOCK.read_text(encoding="utf-8"))
    if lock.get("schema") != "RAOS_WORDPRESS_PUBLIC_RUNTIME_DEPENDENCIES_V1":
        fail()
    for row in lock["modules"]:
        resources[ORIGIN + "/" + row["path"] + "?ver=" + row["version_query"]] = (
            Resource(row["sha256"], row["byte_length"], "module", row["module_id"])
        )
    return resources


def trusted_theme_files(
    expected_tree: str, *, baseline: bool = False
) -> dict[str, bytes]:
    from raos.application.editorial.local_scratch_theme_restore_v1 import (
        parse_theme_package,
        theme_tree_sha256,
    )
    import raos_wordpress_scratch_theme_restore as scratch

    # Both factories rehash actual reviewed repository bytes; no live download
    # or caller-controlled checkout/archive path becomes a trust anchor.
    raw = (
        scratch.baseline_package()
        if baseline
        else scratch.candidate_package(expected_tree)
    )
    files = parse_theme_package(raw)
    if theme_tree_sha256(files) != expected_tree:
        fail()
    return files


class RuntimeMarkup(HTMLParser):
    def __init__(
        self,
        resources: Mapping[str, Resource],
        allowed_images: frozenset[str] | None = None,
        *,
        expected_dns_hints: int = 0,
    ) -> None:
        super().__init__(convert_charrefs=False)
        if type(expected_dns_hints) is not int or expected_dns_hints not in {0, 1}:
            fail()
        self.expected_dns_hints = expected_dns_hints
        self.dns_hints = 0
        self.markup: str | None = None
        self.offsets: list[int] = []
        self.doctype_seen = False
        self.svg_depth = 0
        self.resources = resources
        self.allowed_images = allowed_images
        self.required: set[str] = set()
        self.imports: dict[str, str] | None = None
        self.modules: set[str] = set()
        self.data_types: set[str] = set()
        self.ids: set[str] = set()
        self.current: tuple[str, dict[str, str | None], list[str]] | None = None

    def feed(self, data: str) -> None:
        if self.markup is not None:
            fail()
        self.markup = data
        self.offsets = [0] + [match.end() for match in re.finditer("\n", data)]
        super().feed(data)

    def handle_comment(self, data: str) -> None:
        line, column = self.getpos()
        offset = self.offsets[line - 1] + column
        if (
            self.markup is None
            or not self.markup.startswith("<!--" + data + "-->", offset)
            or data.startswith((">", "->"))
            or "--" in data
            or data.endswith("<!-")
        ):
            fail()

    def handle_decl(self, decl: str) -> None:
        if self.doctype_seen or decl.casefold() != "doctype html":
            fail()
        self.doctype_seen = True

    def handle_pi(self, data: str) -> None:
        fail()

    def unknown_decl(self, data: str) -> None:
        fail()

    def require_resource(self, url: str | None, kinds: set[str]) -> str:
        # Exact absolute URLs, including their original version query.
        if (
            type(url) is not str
            or not url
            or url not in self.resources
            or self.resources[url].kind not in kinds
        ):
            fail()
        self.required.add(url)
        return url

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if len(values) != len(attrs) or self.current is not None:
            fail()
        if ":" in tag or tag == "math":
            fail()
        if tag == "svg":
            self.svg_depth += 1
        if self.svg_depth and tag in {"script", "style"}:
            fail()
        validate_directives(tag, values)
        if "srcset" in values or "imagesrcset" in values:
            fail()
        if any(
            key.startswith("on") or key in {"srcdoc", "ping", "manifest"}
            for key in values
        ):
            fail()
        if values.get("id"):
            identifier = str(values["id"])
            if identifier in self.ids:
                fail()
            self.ids.add(identifier)
        if "background" in values or "poster" in values:
            fail()
        for key in {"href", "src", "xlink:href", "action", "formaction", "data"} & set(
            values
        ):
            normalized = re.sub(r"[\x00-\x20\x7f]", "", values[key] or "")
            scheme = re.match(r"^([a-z][a-z0-9+.-]*):", normalized, re.I)
            if scheme and scheme[1].lower() not in {"https", "http", "mailto", "tel"}:
                fail()
        if tag in {
            "iframe",
            "frame",
            "frameset",
            "object",
            "embed",
            "applet",
            "base",
            "audio",
            "video",
            "source",
            "track",
            "foreignobject",
            "animate",
            "animatemotion",
            "animatetransform",
            "set",
            "feimage",
        }:
            fail()
        if tag == "meta" and "http-equiv" in values:
            fail()
        if "style" in values:
            inert_css(values["style"] or "")
        if tag not in {"script", "img"} and "src" in values:
            fail()
        if tag == "img" and self.allowed_images is not None:
            source = values.get("src")
            # The audited baseline front-page template uses root-relative theme
            # images. Resolve only that exact namespace, never generic relative
            # URLs, dot segments, queries, alternate origins or live-learned paths.
            if type(source) is str and source.startswith(
                "/wp-content/themes/kurashinoshirube-child/assets/images/"
            ):
                source = ORIGIN + source
            if source not in self.allowed_images:
                fail()
        if tag == "use" and not (
            values.get("href") or values.get("xlink:href") or ""
        ).startswith("#"):
            fail()
        if tag not in {"a", "link", "use"} and {"href", "xlink:href"} & set(values):
            fail()
        if tag in {"script", "style"}:
            self.current = (tag, values, [])
        if tag == "link":
            rel = values.get("rel") or ""
            if rel == "dns-prefetch":
                if values != DNS_HINT or self.expected_dns_hints != 1:
                    fail()
                self.dns_hints += 1
                if self.dns_hints > 1:
                    fail()
            elif rel == "icon":
                if values != {
                    "rel": "icon",
                    "href": THEME_PREFIX + BRAND_ICON_PATH,
                    "type": "image/svg+xml",
                }:
                    fail()
                self.require_resource(values["href"], {"icon"})
            elif rel in {"stylesheet", "modulepreload", "preload"}:
                if not set(values) <= {
                    "rel",
                    "href",
                    "id",
                    "as",
                    "media",
                    "fetchpriority",
                }:
                    fail()
                kind = "module" if rel == "modulepreload" else "css"
                if rel == "preload" and values.get("as") != "style":
                    fail()
                self.require_resource(values.get("href"), {kind})
            elif rel not in {
                "canonical",
                "alternate",
                "https://api.w.org/",
                "EditURI",
                "shortlink",
            }:
                fail()

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.current[2].append(data)
        elif "<" in data:
            fail()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            fail()
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "svg":
            self.svg_depth -= 1
            if self.svg_depth < 0:
                fail()
        if self.current is None:
            return
        current, attrs, pieces = self.current
        if current != tag:
            fail()
        self.current = None
        text = "".join(pieces)
        if tag == "style":
            if not set(attrs) <= {"id", "type", "media"}:
                fail()
            inert_css(text)
            return
        if "src" in attrs:
            if text.strip() or not set(attrs) <= {
                "src",
                "id",
                "type",
                "defer",
                "data-wp-strategy",
                "data-wp-router-options",
                "fetchpriority",
            }:
                fail()
            url = self.require_resource(attrs.get("src"), {"js", "module"})
            if self.resources[url].kind == "module":
                module_path = url.split("/script-modules/", 1)[1].split("?", 1)[0]
                identifier = (
                    "@wordpress/"
                    + re.sub(r"(?:\.min)?\.js$", "", module_path)
                    + "-js-module"
                )
                if (
                    attrs.get("type") != "module"
                    or attrs.get("id") != identifier
                    or attrs.get("fetchpriority") not in {None, "low"}
                ):
                    fail()
                self.modules.add(url)
            else:
                identifier = (
                    "kurashinoshirube-"
                    + url.split("/assets/", 1)[1].split(".js", 1)[0]
                    + "-js"
                )
                if (
                    attrs.get("type") not in {None, "text/javascript"}
                    or attrs.get("id") != identifier
                    or attrs.get("data-wp-strategy") != "defer"
                    or "defer" not in attrs
                ):
                    fail()
            if "data-wp-router-options" in attrs and unique_json(
                attrs["data-wp-router-options"] or ""
            ) != {"loadOnClientNavigation": True}:
                fail()
            return
        data_type = attrs.get("type") or ""
        if not set(attrs) <= {"id", "type"} or data_type in self.data_types:
            fail()
        self.data_types.add(data_type)
        data = unique_json(text)
        if data_type == "application/ld+json":
            if type(data) is not dict:
                fail()  # The caller separately verifies the entire graph semantics.
        elif data_type == "importmap":
            if (
                attrs.get("id") != "wp-importmap"
                or type(data) is not dict
                or set(data) != {"imports"}
            ):
                fail()
            imports = data["imports"]
            if type(imports) is not dict or set(imports) != {
                "@wordpress/interactivity"
            }:
                fail()
            url = self.require_resource(imports["@wordpress/interactivity"], {"module"})
            if self.resources[url].module_id != "@wordpress/interactivity":
                fail()
            self.imports = imports
        elif data_type == "speculationrules":
            if data != SPECULATION:
                fail()
        else:
            fail()  # Includes every inline executable script, even an empty one.

    def close(self) -> None:
        if self.rawdata or self.svg_depth:
            fail()
        super().close()
        if self.dns_hints != self.expected_dns_hints:
            fail()
        if self.current is not None or (self.modules and self.imports is None):
            fail()
        dependencies = {
            url
            for url in self.required
            if self.resources[url].module_id == "@wordpress/interactivity"
        }
        if dependencies and (
            self.imports is None or dependencies != set(self.imports.values())
        ):
            fail()


def verify_page(
    page: seo.HttpResponse,
    resources: Mapping[str, Resource],
    transport: seo.HttpTransport,
    *,
    allowed_images: frozenset[str] | None = None,
    expected_dns_hints: int = 0,
) -> dict[str, str]:
    if (
        page.status != 200
        or page.header_values("set-cookie")
        or page.header_values("refresh")
    ):
        fail()
    if any(
        re.search(r"preload|prefetch|preconnect|dns-prefetch", value, re.I)
        for value in page.header_values("link")
    ):
        fail()
    parser = RuntimeMarkup(
        resources, allowed_images, expected_dns_hints=expected_dns_hints
    )
    parser.feed(page.body.decode("utf-8", errors="strict"))
    parser.close()
    required = set(parser.required)
    # These exact theme CSS bytes refer to the same bound image tree. Never
    # trust a CSS response merely because it is hosted on the same origin.
    for url in parser.required:
        required.update(resources[url].dependencies)
    observed = {}
    for url in sorted(required):
        response = transport.get(url)
        expected = resources[url]
        mime = response.header_values("content-type")
        allowed_mime = {
            "js": {"application/javascript", "text/javascript"},
            "module": {"application/javascript", "text/javascript"},
            "css": {"text/css"},
            "image": {"image/svg+xml", "image/webp", "image/png"},
            "icon": {"image/svg+xml"},
        }[expected.kind]
        if (
            response.url != url
            or response.status != 200
            or response.header_values("set-cookie")
            or response.header_values("refresh")
            or any(
                re.search(r"preload|prefetch|preconnect|dns-prefetch", value, re.I)
                for value in response.header_values("link")
            )
            or response.body_sha256 != expected.sha256
            or len(response.body) != expected.size
            or len(mime) != 1
            or mime[0].split(";", 1)[0].lower() not in allowed_mime
        ):
            fail()
        observed[url] = response.body_sha256
    return observed


def build_dns_transition(
    *, baseline_tree: str, candidate_tree: str, page_urls: frozenset[str]
) -> dict[str, object]:
    """Declare the opt-in subject from audited source, never from live HTML."""
    files = trusted_theme_files(candidate_tree)
    functions = files.get("functions.php", b"")
    if functions.count(DNS_REMOVAL_SOURCE) != 1:
        fail()
    policy = {
        "schema": "RAOS_WORDPRESS_SITEKIT_DNS_TRANSITION_V1",
        "mode": DNS_TRANSITION_MODE,
        "baseline_theme_sha256": baseline_tree,
        "candidate_theme_sha256": candidate_tree,
        "candidate_functions_sha256": seo._sha256(functions),
        "hint": dict(DNS_HINT),
        "expected_baseline_hints": {url: 1 for url in sorted(page_urls)},
        "post_apply_state": "CLOSED_DECLARED_RUNTIME_VERIFIED",
    }
    return validate_dns_transition(
        policy,
        baseline_tree=baseline_tree,
        candidate_tree=candidate_tree,
        candidate_functions_sha256=seo._sha256(functions),
        page_urls=page_urls,
    )


def captured_theme_image_urls(markup: str) -> frozenset[str]:
    """Identify exact stored baseline references, not image availability/rights.

    Some captured old articles reference a missing PNG that the audited candidate
    removes at render time. This prewrite runtime inventory does not promote that
    image to verified or permit it in candidate/final image quality validation.
    """
    from raos.application.editorial.verified_incremental_v1 import _Markup

    parser = _Markup(markup)
    parser.feed(markup)
    parser.close()
    if parser.stack:
        fail()
    return frozenset(
        ORIGIN + source
        for element in parser.elements
        if element.tag == "img"
        and type(source := element.attrs.get("src")) is str
        and re.fullmatch(
            r"/wp-content/themes/kurashinoshirube-child/assets/images/[a-z0-9-]+\.(?:png|webp|svg)",
            source,
        )
        is not None
    )


def verify_before_write(
    *,
    current_tree: str,
    baseline_tree: str,
    candidate_tree: str,
    now: datetime,
    snapshot: Mapping[str, Any],
    runtime_transition: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from raos_wordpress_incremental_seo_audit import _ObservedTransport
    import raos_wordpress_baseline_media as baseline_media

    if current_tree not in {baseline_tree, candidate_tree}:
        fail()
    files = trusted_theme_files(current_tree, baseline=current_tree != candidate_tree)
    resources = resources_for_theme(files)
    theme_images = {
        THEME_PREFIX + path for path in files if path.startswith("assets/images/")
    }
    document_images: dict[str, set[str]] = {}
    for document in snapshot["documents"]:
        url = (
            ORIGIN
            + "/"
            + (document["slug"] + "/" if document["slug"] != "home" else "")
        )
        document_images[url] = baseline_media.image_urls(document["block_markup"])
        if current_tree == baseline_tree and current_tree != candidate_tree:
            document_images[url].update(
                captured_theme_image_urls(document["block_markup"])
            )
    contract = seo.load_contract()
    transitional = False
    if runtime_transition is not None:
        expected = build_dns_transition(
            baseline_tree=baseline_tree,
            candidate_tree=candidate_tree,
            page_urls=frozenset(item.url for item in contract.items),
        )
        if canonical(runtime_transition) != canonical(expected):
            fail()
        transitional = current_tree == baseline_tree
    transport = _ObservedTransport(
        seo.BoundedHttpsTransport(contract, allowed_resource_urls=frozenset(resources)),
        now,
    )
    pages = {}
    for item in contract.items:
        response = transport.get(item.url)
        observed = verify_page(
            response,
            resources,
            transport,
            allowed_images=frozenset(
                theme_images | document_images.get(item.url, set())
            ),
            expected_dns_hints=1 if transitional else 0,
        )
        pages[item.url] = {"html_sha256": response.body_sha256, "resources": observed}
        if transitional:
            pages[item.url]["dns_hints"] = 1
    result = {
        "state": DNS_TRANSITION_STATE
        if transitional
        else "CLOSED_DECLARED_RUNTIME_VERIFIED",
        "theme_tree_sha256": current_tree,
        "pages": pages,
    }
    if transitional:
        result["runtime_transition_sha256"] = seo._sha256(canonical(runtime_transition))
    return result
