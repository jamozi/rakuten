"""Closed declared-runtime verification, not a substitute for browser observation.

By default only two audited theme scripts and three pinned core modules may execute.
The explicit reader-minimal-v1 profile additionally binds two reviewed plugin assets,
a fixed inert config and consent subtree, and an expected declared collector state. No
provider-name denylist, arbitrary inline JS, plugin directory wildcard, or live
response learned as an expected hash is accepted. All network reads are public.
"""

from __future__ import annotations

from collections.abc import Mapping
import base64
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
import json
from pathlib import Path
from types import MappingProxyType
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
# Exact core getters emitted by the approved header; no executable expressions.
HEADER_READINESS_BINDINGS = {
    "data-wp-bind--data-raos-nav-ready": (
        "nav", "core/navigation", "raos-primary-nav", "state.isMenuOpen",
    ),
    "data-wp-bind--data-raos-search-ready": (
        "form", "core/search", "raos-header-search", "state.type",
    ),
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
        if key in HEADER_READINESS_BINDINGS:
            expected_tag, namespace, class_name, state = HEADER_READINESS_BINDINGS[key]
            if (
                tag != expected_tag
                or attrs.get("data-wp-interactive") != namespace
                or class_name not in re.split(r"[ \t\r\n\f]+", attrs.get("class") or "")
                or value != state
            ):
                fail()
        elif key == "data-wp-context":
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


def preserved_webp_style(text: str) -> None:
    """Validate existing inline WebPs without permitting a network CSS fetch."""
    count = 0

    def image(match: re.Match[str]) -> str:
        nonlocal count
        encoded = match[2]
        if len(encoded) > 2 * 1024 * 1024:
            fail()
        try:
            raw = base64.b64decode(encoded, validate=True)
        except ValueError:
            fail()
        if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WEBP" or int.from_bytes(raw[4:8], "little") != len(raw) - 8:
            fail()
        count += 1
        return "none"

    remainder = re.sub(r"url\((['\"])data:image/webp;base64,([A-Za-z0-9+/=]+)\1\)", image, text)
    if not count:
        fail()
    inert_css(remainder)


@dataclass(frozen=True)
class Resource:
    sha256: str
    size: int
    kind: str
    module_id: str | None = None
    dependencies: tuple[str, ...] = ()


READER_PROFILE = "reader-minimal-v1"
READER_PREFIX = ORIGIN + "/wp-content/plugins/raos-reader-measurement/"
READER_ENDPOINT = "/wp-json/raos-reader/v1/events"
READER_ASSETS = ("assets/reader-measurement.js", "assets/reader-measurement.css")
READER_ALLOWLIST = "config/reader-allowlist.v1.json"
READER_CONFIG = "config/reader-runtime.v1.json"
READER_PLUGIN_ROOT = (
    "changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement"
)
READER_MANIFEST = "changes/reader-measurement-v1/runtime-manifest.v1.json"
READER_POLICY = "changes/editorial-portfolio-v3/reader-measurement-privacy.html"


READER_CONSENT_TEMPLATE = (
    '<section id="raos-reader-consent-settings" aria-labelledby="raos-reader-consent-title">'
    '<h2 id="raos-reader-consent-title">任意の読者計測</h2>'
    '<p id="raos-reader-site-status" role="status">{site_status}</p>'
    "<p>記事の移動・確認パネル・公式出典の操作件数を、記事改善の参考にします。許可は任意です。"
    '<a href="/privacy-policy/">プライバシーポリシー</a></p>'
    '<p id="raos-reader-user-status" aria-live="polite">あなたの選択：未選択</p>'
    '<button type="button" id="raos-reader-consent-reopen" aria-expanded="true" aria-controls="raos-reader-consent-choices">計測設定を開く</button>'
    '<div id="raos-reader-consent-choices"><button type="button" id="raos-reader-consent-allow">許可する</button> '
    '<button type="button" id="raos-reader-consent-deny">許可しない</button></div>'
    '<button type="button" id="raos-reader-consent-revoke" hidden>許可を撤回する</button>'
    '<p id="raos-reader-consent-error" role="alert" hidden></p>'
    "<noscript><p>JavaScriptが無効なため、この計測は行いません。</p></noscript></section>"
)
READER_SITE_STATUS = {
    False: "サイトの計測は停止中です。現在、操作は送信されません。",
    True: "サイトの計測は有効です。許可した場合だけ対象の操作を送ります。",
}


class _ConsentTokens(HTMLParser):
    """Compare the fixed inert subtree without depending on attribute order."""

    def __init__(self, markup: str) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[tuple[Any, ...]] = []
        self.feed(markup)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.tokens.append(("start", tag, tuple(sorted(attrs))))

    def handle_endtag(self, tag):
        self.tokens.append(("end", tag))

    def handle_data(self, data):
        if data.strip():
            self.tokens.append(("text", data.strip()))

    def handle_comment(self, data):
        reader_fail()

    def handle_startendtag(self, tag, attrs):
        reader_fail()


def reader_fail() -> NoReturn:
    raise seo.AuditError("INCREMENTAL_READER_MEASUREMENT_RUNTIME_MISMATCH")


def _reader_digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _reader_json(raw: bytes) -> Any:
    if type(raw) is not bytes or not raw or len(raw) > 4 * 1024 * 1024:
        reader_fail()
    try:
        return unique_json(raw.decode("utf-8", errors="strict"))
    except UnicodeError, RecursionError:
        reader_fail()


def _reader_path(value: object) -> bool:
    return (
        type(value) is str
        and len(value) <= 512
        and re.fullmatch(r"[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*", value) is not None
        and not {".", ".."} & set(value.split("/"))
    )


@dataclass(frozen=True)
class ReaderMeasurementRuntime:
    """Reviewed runtime identity; declared state is not a browser or human check."""

    manifest_sha256: str
    contract_sha256: str
    policy_sha256: str
    expected_collection_enabled: bool
    plugin_version: str
    resources: Mapping[str, Resource]
    articles: bytes
    revision: str
    profile: str = READER_PROFILE

    def allows_collector_request(
        self, url: str, method: str, *, consent_granted: bool = False
    ) -> bool:
        """Only this extra request can be allowed by a browser audit of this mode."""
        return (
            self.expected_collection_enabled is True
            and consent_granted is True
            and method == "POST"
            and url == ORIGIN + READER_ENDPOINT
        )

    def asset_attributes(self, path: str) -> dict[str, str]:
        if path not in READER_ASSETS:
            reader_fail()
        url, resource = next(
            (url, resource)
            for url, resource in self.resources.items()
            if url.startswith(READER_PREFIX + path + "?ver=")
        )
        common = {
            "integrity": "sha256-"
            + base64.b64encode(bytes.fromhex(resource.sha256)).decode("ascii"),
            "crossorigin": "anonymous",
        }
        if path.endswith(".js"):
            return {"id": "raos-reader-measurement-js", "src": url, **common}
        return {
            "id": "raos-reader-measurement-style-css",
            "rel": "stylesheet",
            "href": url,
            "media": "all",
            **common,
        }

    def client_config(self, page_url: str) -> dict[str, Any]:
        if (
            type(page_url) is not str
            or re.fullmatch(
                re.escape(ORIGIN) + r"/(?:[a-z0-9]+(?:-[a-z0-9]+)*/)?", page_url
            )
            is None
        ):
            reader_fail()
        article = next(
            (
                row
                for row in _reader_json(self.articles)
                if page_url == ORIGIN + "/" + row["slug"] + "/"
            ),
            None,
        )
        return {
            "schema": "RAOSReaderMeasurementClientV1",
            "origin": ORIGIN,
            "endpoint": READER_ENDPOINT,
            "collection_enabled": self.expected_collection_enabled,
            "contract_sha256": self.contract_sha256,
            "policy_sha256": self.policy_sha256,
            "policy_version": self.policy_sha256,
            "article": article,
        }


def reader_measurement_runtime(
    manifest: bytes,
    plugin_files: Mapping[str, bytes],
    policy: bytes,
    *,
    expected_manifest_sha256: str,
    expected_policy_sha256: str,
    expected_collection_enabled: bool,
) -> ReaderMeasurementRuntime:
    """Pure reviewed-byte factory. Expected digests must come from the release.

    None of these trust anchors may be derived from a live HTML/asset response.
    Only the two fixed assets are public resources, even if the reviewed plugin
    also contains PHP, maintenance code, documentation or an article allowlist.
    """
    if (
        not _reader_digest(expected_manifest_sha256)
        or not _reader_digest(expected_policy_sha256)
        or type(expected_collection_enabled) is not bool
        or type(manifest) is not bytes
        or type(policy) is not bytes
        or not policy
        or len(policy) > 1048576
        or seo._sha256(manifest) != expected_manifest_sha256
        or seo._sha256(policy) != expected_policy_sha256
    ):
        reader_fail()
    declared = _reader_json(manifest)
    if (
        type(declared) is not dict
        or declared.get("schema") != "RAOS_READER_MEASUREMENT_RUNTIME_MANIFEST_V1"
        or declared.get("default_enabled") is not False
        or declared.get("approval_required") is not True
        or declared.get("plugin_slug") != "raos-reader-measurement"
        or declared.get("privacy_source") != READER_POLICY
        or declared.get("plugin_root") != READER_PLUGIN_ROOT
        or type(declared.get("plugin_version")) is not str
        or re.fullmatch(
            r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}", declared["plugin_version"]
        )
        is None
        or type(declared.get("plugin_files")) is not list
        or not 4 <= len(declared["plugin_files"]) <= 64
    ):
        reader_fail()
    inventory = {}
    for row in declared["plugin_files"]:
        if (
            type(row) is not dict
            or set(row) != {"path", "size", "sha256"}
            or not _reader_path(row["path"])
            or row["path"] in inventory
            or not _reader_digest(row["sha256"])
            or type(row["size"]) is not int
            or not 0 < row["size"] <= 4 * 1024 * 1024
        ):
            reader_fail()
        raw = plugin_files.get(row["path"])
        if (
            type(raw) is not bytes
            or len(raw) != row["size"]
            or seo._sha256(raw) != row["sha256"]
        ):
            reader_fail()
        inventory[row["path"]] = row
    if set(plugin_files) != set(inventory) or not set(
        (*READER_ASSETS, READER_ALLOWLIST, READER_CONFIG)
    ) <= set(inventory):
        reader_fail()
    config = _reader_json(plugin_files[READER_CONFIG])
    if (
        type(config) is not dict
        or set(config)
        != {
            "schema",
            "plugin_version",
            "contract_sha256",
            "policy_sha256",
            "policy_slug",
            "revision",
            "files",
        }
        or config["schema"] != "RAOS_READER_MEASUREMENT_RUNTIME_V1"
        or config["plugin_version"] != declared["plugin_version"]
        or config["contract_sha256"] != inventory[READER_ALLOWLIST]["sha256"]
        or config["policy_sha256"] != expected_policy_sha256
        or config["policy_slug"] != "privacy-policy"
        or not _reader_digest(config["revision"])
        or type(config["files"]) is not dict
        or set(config["files"]) != set(inventory) - {READER_CONFIG}
        or any(
            declared.get(field) != config[field]
            for field in ("policy_sha256", "contract_sha256", "revision")
        )
        or any(
            path not in inventory or inventory[path]["sha256"] != digest
            for path, digest in config["files"].items()
        )
    ):
        reader_fail()
    revision_input = "".join(
        path + ":" + digest + "\n" for path, digest in sorted(config["files"].items())
    )
    revision_input += (
        "policy:"
        + expected_policy_sha256
        + "\nversion:"
        + declared["plugin_version"]
        + "\n"
    )
    if seo._sha256(revision_input.encode("utf-8")) != config["revision"]:
        reader_fail()
    contract = _reader_json(plugin_files[READER_ALLOWLIST])
    if (
        type(contract) is not dict
        or set(contract)
        != {"schema", "version", "target_origin", "events", "source_hashes", "articles"}
        or contract["schema"] != "RAOS_READER_MEASUREMENT_ALLOWLIST_V1"
        or contract["version"] != "1.0.0"
        or contract["target_origin"] != ORIGIN
        or contract["events"]
        != ["guide_navigation", "decision_check_open", "official_reference_open"]
        or type(contract["source_hashes"]) is not dict
        or len(contract["source_hashes"]) < 10
        or any(
            not _reader_path(path) or not _reader_digest(digest)
            for path, digest in contract["source_hashes"].items()
        )
        or type(contract["articles"]) is not list
        or len(contract["articles"]) != 10
    ):
        reader_fail()
    article_ids, slugs = set(), set()
    for row in contract["articles"]:
        if (
            type(row) is not dict
            or set(row) != {"article_id", "slug", "navigation", "panels", "references"}
            or type(row["article_id"]) is not str
            or re.fullmatch(r"[A-Za-z0-9_-]{1,200}", row["article_id"]) is None
            or row["article_id"] in article_ids
            or type(row["slug"]) is not str
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", row["slug"]) is None
            or len(row["slug"]) > 200
            or row["slug"] in slugs
            or row["slug"].startswith("local-")
            or any(
                type(row[field]) is not list or len(row[field]) > limit
                for field, limit in (
                    ("navigation", 32),
                    ("panels", 3),
                    ("references", 128),
                )
            )
        ):
            reader_fail()
        article_ids.add(row["article_id"])
        slugs.add(row["slug"])
        for panel in row["panels"]:
            if panel not in (
                {"panel_id": "reader-axes", "kind": "anchor"},
                {"panel_id": "reader-purchase-checks", "kind": "anchor"},
                {"panel_id": "reader-evidence", "kind": "details"},
            ):
                reader_fail()
        if len({panel["panel_id"] for panel in row["panels"]}) != len(row["panels"]):
            reader_fail()
        for reference in row["references"]:
            if (
                type(reference) is not dict
                or set(reference) != {"source_ref", "url"}
                or type(reference["source_ref"]) is not str
                or re.fullmatch(r"[A-Za-z0-9_-]{1,200}", reference["source_ref"])
                is None
                or type(reference["url"]) is not str
                or not reference["url"].startswith("https://")
                or len(reference["url"]) > 2048
                or re.search(r"[\x00-\x20\x7f]", reference["url"])
            ):
                reader_fail()
    for row in contract["articles"]:
        for navigation in row["navigation"]:
            if (
                type(navigation) is not dict
                or set(navigation) != {"target_article_id", "journey_stage", "path"}
                or type(navigation["target_article_id"]) is not str
                or navigation["target_article_id"] not in article_ids
                or navigation["target_article_id"] == row["article_id"]
                or type(navigation["journey_stage"]) is not str
                or navigation["journey_stage"]
                not in {"discover", "learn", "compare", "verify", "buy"}
                or navigation["path"]
                != next(
                    "/" + item["slug"] + "/"
                    for item in contract["articles"]
                    if item["article_id"] == navigation["target_article_id"]
                )
            ):
                reader_fail()
    try:
        inert_css(plugin_files[READER_ASSETS[1]].decode("utf-8", errors="strict"))
    except UnicodeError:
        reader_fail()
    resources = {
        READER_PREFIX + path + "?ver=" + inventory[path]["sha256"]: Resource(
            inventory[path]["sha256"],
            inventory[path]["size"],
            "js" if path.endswith(".js") else "css",
        )
        for path in READER_ASSETS
    }
    return ReaderMeasurementRuntime(
        expected_manifest_sha256,
        inventory[READER_ALLOWLIST]["sha256"],
        expected_policy_sha256,
        expected_collection_enabled,
        declared["plugin_version"],
        MappingProxyType(resources),
        canonical(contract["articles"]),
        config["revision"],
    )


def build_reader_measurement_runtime(
    *,
    expected_manifest_sha256: str,
    expected_policy_sha256: str,
    expected_collection_enabled: bool,
) -> ReaderMeasurementRuntime:
    """Load only fixed repository sources, with release-supplied trust anchors."""

    def read(path: Path) -> bytes:
        try:
            if (
                path.resolve(strict=True) != path.absolute()
                or not path.is_file()
                or path.stat().st_size > 4 * 1024 * 1024
            ):
                reader_fail()
            return path.read_bytes()
        except OSError:
            reader_fail()

    manifest = read(ROOT / READER_MANIFEST)
    if (
        not _reader_digest(expected_manifest_sha256)
        or seo._sha256(manifest) != expected_manifest_sha256
    ):
        reader_fail()
    declared = _reader_json(manifest)
    if (
        type(declared) is not dict
        or type(declared.get("plugin_files")) is not list
        or not 4 <= len(declared["plugin_files"]) <= 64
    ):
        reader_fail()
    files = {}
    for row in declared["plugin_files"]:
        if (
            type(row) is not dict
            or not _reader_path(row.get("path"))
            or row["path"] in files
        ):
            reader_fail()
        files[row["path"]] = read(ROOT / READER_PLUGIN_ROOT / row["path"])
    return reader_measurement_runtime(
        manifest,
        files,
        read(ROOT / READER_POLICY),
        expected_manifest_sha256=expected_manifest_sha256,
        expected_policy_sha256=expected_policy_sha256,
        expected_collection_enabled=expected_collection_enabled,
    )


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
        scratch.baseline_package(expected_tree)
        if baseline
        else scratch.candidate_package(expected_tree)
    )
    files = parse_theme_package(raw)
    if theme_tree_sha256(files) != expected_tree:
        fail()
    return files


def _reader_resources(
    resources: Mapping[str, Resource],
    reader_measurement: ReaderMeasurementRuntime | None,
) -> Mapping[str, Resource]:
    if reader_measurement is None:
        return resources
    if (
        type(reader_measurement) is not ReaderMeasurementRuntime
        or reader_measurement.profile != READER_PROFILE
        or type(reader_measurement.expected_collection_enabled) is not bool
    ):
        reader_fail()
    combined = dict(resources)
    for url, resource in reader_measurement.resources.items():
        if url in combined and combined[url] != resource:
            reader_fail()
        combined[url] = resource
    return combined


class RuntimeMarkup(HTMLParser):
    def __init__(
        self,
        resources: Mapping[str, Resource],
        allowed_images: frozenset[str] | None = None,
        *,
        expected_dns_hints: int = 0,
        reader_measurement: ReaderMeasurementRuntime | None = None,
        page_url: str | None = None,
        preserved_home_style: str | None = None,
    ) -> None:
        super().__init__(convert_charrefs=False)
        if type(expected_dns_hints) is not int or expected_dns_hints not in {0, 1}:
            fail()
        self.expected_dns_hints = expected_dns_hints
        self.dns_hints = 0
        self.preserved_home_style = preserved_home_style
        self.home_style_seen = False
        if preserved_home_style is not None:
            if page_url != ORIGIN + "/":
                fail()
            preserved_webp_style(preserved_home_style)
        self.markup: str | None = None
        self.offsets: list[int] = []
        self.doctype_seen = False
        self.svg_depth = 0
        self.resources = _reader_resources(resources, reader_measurement)
        self.reader_measurement = reader_measurement
        self.reader_collection_state = "UNKNOWN"
        self.reader_consent_seen = False
        self.reader_consent_stack: list[str] = []
        self.reader_consent_start = 0
        self.reader_inert_depth = 0
        self.expected_reader_config = (
            reader_measurement.client_config(page_url)
            if reader_measurement is not None
            else None
        )
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
        if url.startswith(READER_PREFIX) and (
            self.reader_measurement is None
            or url not in self.reader_measurement.resources
        ):
            reader_fail()
        self.required.add(url)
        return url

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if len(values) != len(attrs) or self.current is not None:
            fail()
        identifier = values.get("id") or ""
        if identifier.startswith("raos-reader-"):
            if (
                self.reader_measurement is None
                or self.reader_inert_depth
                or self.svg_depth
            ):
                reader_fail()
            if identifier == "raos-reader-consent-settings":
                if self.reader_consent_seen or self.reader_consent_stack:
                    reader_fail()
                line, column = self.getpos()
                self.reader_consent_start = self.offsets[line - 1] + column
                self.reader_consent_stack.append(tag)
            elif not self.reader_consent_stack and identifier not in {
                "raos-reader-measurement-config",
                "raos-reader-measurement-js",
                "raos-reader-measurement-style-css",
            }:
                reader_fail()
            elif self.reader_consent_stack:
                self.reader_consent_stack.append(tag)
        elif self.reader_consent_stack:
            self.reader_consent_stack.append(tag)
        if self.reader_measurement is not None:
            if tag in {"template", "noscript"}:
                self.reader_inert_depth += 1
            if (
                "formaction" in values
                or tag == "form"
                and (
                    values.get("method") != "get"
                    or values.get("action") != ORIGIN + "/"
                    or values.get("role") != "search"
                    or "wp-block-search" not in (values.get("class") or "").split()
                )
            ):
                reader_fail()
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
            if self.preserved_home_style is not None and tag == "div" and identifier == "ks-magazine":
                if self.home_style_seen or values["style"] != self.preserved_home_style:
                    fail()
                preserved_webp_style(values["style"] or "")
                self.home_style_seen = True
            else:
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
            if (
                self.reader_measurement is not None
                and values.get("href") in self.reader_measurement.resources
            ):
                if values != self.reader_measurement.asset_attributes(READER_ASSETS[1]):
                    reader_fail()
                self.require_resource(values["href"], {"css"})
                return
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
        if (
            self.reader_consent_stack
            or dict(attrs).get("id") == "raos-reader-consent-settings"
        ):
            reader_fail()
        if tag in {"script", "style"}:
            fail()
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self.reader_consent_stack:
            if tag != self.reader_consent_stack.pop():
                reader_fail()
            if not self.reader_consent_stack:
                line, column = self.getpos()
                end = self.markup.index(">", self.offsets[line - 1] + column) + 1
                fragment = self.markup[self.reader_consent_start : end]
                expected = READER_CONSENT_TEMPLATE.format(
                    site_status=READER_SITE_STATUS[
                        self.reader_measurement.expected_collection_enabled
                    ]
                )
                if _ConsentTokens(fragment).tokens != _ConsentTokens(expected).tokens:
                    reader_fail()
                self.reader_consent_seen = True
        if self.reader_measurement is not None and tag in {"template", "noscript"}:
            self.reader_inert_depth -= 1
            if self.reader_inert_depth < 0:
                reader_fail()
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
            if (
                self.reader_measurement is not None
                and attrs.get("src") in self.reader_measurement.resources
            ):
                expected = self.reader_measurement.asset_attributes(READER_ASSETS[0])
                if "type" in attrs:
                    expected["type"] = "text/javascript"
                if text.strip() or attrs != expected:
                    reader_fail()
                self.require_resource(attrs["src"], {"js"})
                return
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
        if data_type == "application/json" and self.reader_measurement is not None:
            if attrs != {
                "id": "raos-reader-measurement-config",
                "type": "application/json",
            } or canonical(data) != canonical(self.expected_reader_config):
                reader_fail()
            self.reader_collection_state = (
                "ON" if data["collection_enabled"] is True else "OFF"
            )
        elif data_type == "application/ld+json":
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
        if self.reader_measurement is not None and (
            self.reader_collection_state == "UNKNOWN"
            or not self.reader_consent_seen
            or self.reader_consent_stack
            or self.reader_inert_depth
            or not set(self.reader_measurement.resources) <= self.required
        ):
            reader_fail()
        if self.dns_hints != self.expected_dns_hints:
            fail()
        if self.preserved_home_style is not None and not self.home_style_seen:
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
    reader_measurement: ReaderMeasurementRuntime | None = None,
    preserved_home_style: str | None = None,
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
    resources = _reader_resources(resources, reader_measurement)
    parser = RuntimeMarkup(
        resources,
        allowed_images,
        expected_dns_hints=expected_dns_hints,
        reader_measurement=reader_measurement,
        page_url=page.url,
        preserved_home_style=preserved_home_style,
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


def _published_snapshot_documents(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    from raos_reader_release_pages import HUB_SLUGS

    schema = snapshot.get("schema")
    if (
        type(schema) is not str
        or schema
        not in {
            "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1",
            "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2",
        }
        or type(snapshot.get("documents")) is not list
    ):
        reader_fail()
    declared = snapshot.get("reader_page_slugs", [])
    if (
        type(declared) is not list
        or any(type(slug) is not str for slug in declared)
        or len(set(declared)) != len(declared)
        or not set(declared) <= HUB_SLUGS
        or (schema.endswith("_V1") and "reader_page_slugs" in snapshot)
        or (schema.endswith("_V2") and not declared)
    ):
        reader_fail()
    selected, published, seen = set(declared), [], set()
    for document in snapshot["documents"]:
        if (
            type(document) is not dict
            or type(document.get("slug")) is not str
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", document["slug"]) is None
            or document["slug"] in seen
            or type(document.get("post_type")) is not str
            or document["post_type"] not in {"post", "page"}
            or type(document.get("block_markup")) is not str
        ):
            reader_fail()
        slug = document["slug"]
        seen.add(slug)
        if slug in selected and document["post_type"] != "page":
            reader_fail()
        if document.get("status") == "publish":
            published.append(document)
        elif not (
            document.get("status") == "draft"
            and slug in selected
            and document["post_type"] == "page"
        ):
            reader_fail()
    if not selected <= seen:
        reader_fail()
    return published


def verify_before_write(
    *,
    current_tree: str,
    baseline_tree: str,
    candidate_tree: str,
    now: datetime,
    snapshot: Mapping[str, Any],
    runtime_transition: Mapping[str, Any] | None = None,
    reader_measurement: ReaderMeasurementRuntime | None = None,
) -> dict[str, Any]:
    from raos_wordpress_incremental_seo_audit import (
        _ObservedTransport,
        _preserved_home_style,
        captured_home_theme_image_urls,
        home_image_urls,
        home_uses_post_content,
    )
    import raos_wordpress_baseline_media as baseline_media

    if current_tree not in {baseline_tree, candidate_tree}:
        fail()
    published_documents = _published_snapshot_documents(snapshot)
    files = trusted_theme_files(current_tree, baseline=current_tree != candidate_tree)
    resources = _reader_resources(resources_for_theme(files), reader_measurement)
    theme_images = {
        THEME_PREFIX + path for path in files if path.startswith("assets/images/")
    }
    document_images: dict[str, set[str]] = {}
    preserved_home_styles: dict[str, str] = {}
    home_post_content = home_uses_post_content(files)
    for document in published_documents:
        is_home = document["slug"] == "home"
        if is_home and document["post_type"] != "page":
            reader_fail()
        url = (
            ORIGIN
            + "/"
            + (document["slug"] + "/" if not is_home else "")
        )
        if is_home:
            document_images[url] = home_image_urls(document["block_markup"])
            if home_post_content:
                style = _preserved_home_style(document["block_markup"])
                if style is not None:
                    preserved_home_styles[url] = style
        else:
            document_images[url] = baseline_media.image_urls(document["block_markup"])
        if current_tree == baseline_tree and current_tree != candidate_tree:
            document_images[url].update(
                (
                    captured_home_theme_image_urls(document["block_markup"])
                    if is_home
                    else captured_theme_image_urls(document["block_markup"])
                )
            )
    contract = seo.load_contract()
    inventory = {item.url: item for item in contract.items}
    # V2 can additionally bind registered hub pages. Only their baseline
    # published state admits a public GET; draft preparation never does.
    for slug in snapshot.get("reader_page_slugs", []):
        url = ORIGIN + "/" + slug + "/"
        if url in document_images and url not in inventory:
            inventory[url] = seo.InventoryItem(url, "reader_page", slug)
    if not document_images or not set(document_images) <= set(inventory):
        reader_fail()
    public_items = [item for url, item in inventory.items() if url in document_images]
    transitional = False
    if runtime_transition is not None:
        expected = build_dns_transition(
            baseline_tree=baseline_tree,
            candidate_tree=candidate_tree,
            page_urls=frozenset(item.url for item in public_items),
        )
        if canonical(runtime_transition) != canonical(expected):
            fail()
        transitional = current_tree == baseline_tree
    transport = _ObservedTransport(
        seo.BoundedHttpsTransport(
            contract,
            allowed_resource_urls=frozenset(resources),
            **(
                {"reader_measurement": reader_measurement}
                if reader_measurement is not None
                else {}
            ),
        ),
        now,
    )
    pages = {}
    for item in public_items:
        response = transport.get(item.url)
        observed = verify_page(
            response,
            resources,
            transport,
            allowed_images=frozenset(
                theme_images | document_images.get(item.url, set())
            ),
            expected_dns_hints=1 if transitional else 0,
            reader_measurement=reader_measurement,
            **(
                {"preserved_home_style": preserved_home_styles[item.url]}
                if item.url in preserved_home_styles
                else {}
            ),
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
    if reader_measurement is not None:
        result["reader_measurement"] = {
            "profile": reader_measurement.profile,
            "manifest_sha256": reader_measurement.manifest_sha256,
            "contract_sha256": reader_measurement.contract_sha256,
            "policy_sha256": reader_measurement.policy_sha256,
            "revision": reader_measurement.revision,
            "expected_collection_enabled": reader_measurement.expected_collection_enabled,
            "collection_state": "ON"
            if reader_measurement.expected_collection_enabled
            else "OFF",
            "state_source": "DECLARED_CLIENT_CONFIG",
            "browser_observation": "NOT_EXECUTED",
        }
    return result
