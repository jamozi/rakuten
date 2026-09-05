"""Synthetic closed-runtime and exact dependency URL transport regressions."""

from dataclasses import replace
import json
from unittest.mock import Mock

import pytest

from scripts import raos_wordpress_incremental_seo_audit as audit

runtime = audit.runtime
STAMP = "2026-09-05T02:00:00Z"
VERSION = "a" * 64
JS_URL = runtime.THEME_PREFIX + "assets/editorial-navigation.js?ver=" + VERSION
CSS_URL = runtime.THEME_PREFIX + "assets/theme.css?ver=" + VERSION
LEGACY_CSS_URL = runtime.THEME_PREFIX + "assets/theme.css?ver=1.4.0"
MODULE_URL = (
    runtime.ORIGIN
    + "/wp-includes/js/dist/script-modules/block-library/navigation/view.js?ver="
    + "b" * 20
)
IMPORT_URL = (
    runtime.ORIGIN
    + "/wp-includes/js/dist/script-modules/interactivity/index.js?ver="
    + "c" * 20
)
SCRIPT = f'<script id="kurashinoshirube-editorial-navigation-js" src="{JS_URL}" defer data-wp-strategy="defer"></script>'


def response(url, body, mime="text/html"):
    return audit.seo.HttpResponse(url, 200, (("Content-Type", mime),), body, STAMP)


@pytest.fixture
def example():
    blobs = {
        JS_URL: (b"approved inert fixture JS", "js", "text/javascript"),
        CSS_URL: (b"p{color:navy}", "css", "text/css"),
        MODULE_URL: (b"approved module fixture", "module", "text/javascript"),
        IMPORT_URL: (b"approved dependency fixture", "module", "text/javascript"),
    }
    resources = {
        url: runtime.Resource(
            audit.digest(raw),
            len(raw),
            kind,
            "@wordpress/interactivity" if url == IMPORT_URL else None,
        )
        for url, (raw, kind, _mime) in blobs.items()
    }
    responses = {
        url: response(url, raw, mime) for url, (raw, _kind, mime) in blobs.items()
    }
    transport = Mock()
    transport.get.side_effect = lambda url: responses[url]
    return resources, responses, transport


def verify(example, markup):
    resources, _responses, transport = example
    return runtime.verify_page(
        response(runtime.ORIGIN + "/", markup.encode()), resources, transport
    )


def test_exact_classic_css_core_importmap_and_speculation_pass(example):
    imports = json.dumps({"imports": {"@wordpress/interactivity": IMPORT_URL}})
    markup = SCRIPT + f'<link rel="stylesheet" href="{CSS_URL}">'
    markup += f'<script type="importmap" id="wp-importmap">{imports}</script>'
    markup += f'<link rel="modulepreload" href="{IMPORT_URL}">'
    markup += f'<script type="module" id="@wordpress/block-library/navigation/view-js-module" src="{MODULE_URL}" data-wp-router-options=\'{json.dumps({"loadOnClientNavigation": True})}\'></script>'
    markup += (
        f'<script type="speculationrules">{json.dumps(runtime.SPECULATION)}</script>'
    )
    markup += "<style>html{scroll-behavior:smooth} p{color:navy}</style>"
    assert set(verify(example, markup)) == {JS_URL, CSS_URL, MODULE_URL, IMPORT_URL}


@pytest.mark.parametrize(
    "markup",
    [
        '<script src="https://stats.wp.com/e-202636.js" id="jetpack-stats-js"></script>',
        '<script src="https://example.com/harmless.js"></script>',
        '<script src="https://kurashinoshirube.com/wp-content/cache/a.js"></script>',
        '<script>fetch("/track")</script>',
        '<script>navigator.sendBeacon("/collect", "x")</script>',
        '<script>new Image().src="/pixel"</script>',
        '<script type="module">import("/loader.js")</script>',
        '<script id="kurashinoshirube-editorial-navigation-js">window["fet"+"ch"]("/track")</script>',
        SCRIPT.replace("</script>", 'fetch("/collect")</script>'),
        SCRIPT.replace(" defer", " async defer"),
        SCRIPT.replace('data-wp-strategy="defer"', 'data-wp-strategy="async"'),
        SCRIPT.replace('id="kurashinoshirube-editorial-navigation-js"', 'id="wrong"'),
        SCRIPT + SCRIPT,
        SCRIPT.replace("</script>", "").replace("></", "/></"),
        '<script type="application/json">{"tracking":true}</script>',
        '<script type="application/ld+json" src="https://example.com/a.js">{}</script>',
        '<script type="application/ld+json">{"a":1,"a":2}</script>',
        '<script type="speculationrules">{"prerender":[{"source":"list","urls":["https://example.com/"]}]}</script>',
        '<link rel="stylesheet" href="https://example.com/a.css">',
        f'<link rel="stylesheet modulepreload" href="{CSS_URL}">',
        f'<link rel="preload" as="script" href="{JS_URL}">',
        '<style>@import "https://example.com/a.css";</style>',
        '<style>p{background:url("https://example.com/pixel")}</style>',
        r'<style>p{background:u\72l("https://example.com/pixel")}</style>',
        '<style>p{background:image-set("https://example.com/pixel" 1x)}</style>',
        '<p style="background:url(https://example.com/pixel)">Text</p>',
        '<iframe src="https://example.com/"></iframe>',
        '<object data="https://example.com/"></object>',
        '<embed src="https://example.com/">',
        '<svg><image href="https://example.com/pixel"></image></svg>',
        '<svg><use href="https://example.com/icons.svg#icon"></use></svg>',
        '<input type="image" src="https://example.com/pixel">',
        '<body background="https://example.com/pixel"></body>',
        '<video poster="https://example.com/pixel"></video>',
        '<base href="https://example.com/">',
        '<meta http-equiv="refresh" content="0;https://example.com/">',
        '<a href="/" ping="https://example.com/track">Go</a>',
        "<p onmouseover=\"fetch('/collect')\">Text</p>",
        '<!--><script>fetch("/collect")</script>-->',
        '<!---><script>fetch("/collect")</script>-->',
        '<!-- safe --!><script>fetch("/collect")</script>-->',
        '<![CDATA[><script>fetch("/collect")</script>]]>',
        '<![CDATA[<script>fetch("/collect")</script>]]>',
        "<?processing instruction?>",
        '<svg><style><script>fetch("/collect")</script></style></svg>',
        '<math><style><script>fetch("/collect")</script></style></math>',
        '<x:script xmlns:x="http://www.w3.org/1999/xhtml">fetch("/collect")</x:script>',
        "<!-- unterminated",
    ],
)
def test_unknown_or_active_content_fails_closed(example, markup):
    with pytest.raises(audit.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
        verify(example, markup)


def test_normal_wp_comments_doctype_escaped_text_and_theme_svg_pass(example):
    markup = '<!DOCTYPE html><html><body><!-- wp:group {"className":"hello"} --><p>Math: x &lt; 2; analytics is ordinary text.</p><!-- /wp:group --><svg role="img"><path d="M0 0 L1 1"/></svg></body></html>'
    assert verify(example, markup) == {}


@pytest.mark.parametrize(
    "directive",
    [
        "data-wp-bind--src",
        "data-wp-bind--src---probe",
        "data-wp-bind--srcset",
        "data-wp-bind--style",
        "data-wp-on--load",
        "data-wp-watch---probe",
    ],
)
def test_approved_core_module_cannot_be_used_as_resource_binding_gadget(
    example, directive
):
    markup = (
        '<form data-wp-interactive="core/search"><img src="https://kurashinoshirube.com/approved.webp" '
        + directive
        + '="context.url"></form>'
    )
    with pytest.raises(audit.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
        verify(example, markup)


def test_approved_interactivity_context_cannot_smuggle_resource_or_callback(example):
    markup = '<form data-wp-interactive="core/search" data-wp-context=\'{"url":"https://pixel.wp.com/probe.gif"}\'></form>'
    with pytest.raises(audit.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
        verify(example, markup)


def test_real_search_and_navigation_directive_shapes_pass(example):
    search = {
        "isSearchInputVisible": False,
        "inputId": "wp-block-search__input-2",
        "ariaLabelExpanded": "検索する",
        "ariaLabelCollapsed": "検索欄を開く",
    }
    nav = {
        "overlayOpenedBy": {"click": False, "hover": False, "focus": False},
        "type": "overlay",
        "roleAttribute": "",
        "ariaLabel": "メニュー",
    }
    markup = f'<form data-wp-interactive="core/search" data-wp-context=\'{json.dumps(search)}\'><input data-wp-bind--tabindex="state.tabindex"><button data-wp-on--click="actions.openSearchInput">検索</button></form>'
    markup += f'<nav data-wp-interactive="core/navigation" data-wp-context=\'{json.dumps(nav)}\'><div data-wp-watch="callbacks.initMenu"><button data-wp-on--click="actions.openMenuOnClick">メニュー</button></div></nav>'
    assert verify(example, markup) == {}


@pytest.mark.parametrize(
    "edit",
    [
        "extra",
        "scopes",
        "duplicate",
        "version",
        "external",
        "twice",
        "preload-mismatch",
    ],
)
def test_import_map_tampering_is_rejected(example, edit):
    text = json.dumps({"imports": {"@wordpress/interactivity": IMPORT_URL}})
    if edit == "extra":
        text = json.dumps(
            {"imports": {"@wordpress/interactivity": IMPORT_URL, "tracker": JS_URL}}
        )
    elif edit == "scopes":
        text = json.dumps(
            {"imports": {"@wordpress/interactivity": IMPORT_URL}, "scopes": {}}
        )
    elif edit == "duplicate":
        text = (
            '{"imports":{},"imports":{"@wordpress/interactivity":'
            + json.dumps(IMPORT_URL)
            + "}}"
        )
    elif edit == "version":
        text = text.replace("c" * 20, "d" * 20)
    elif edit == "external":
        text = text.replace(IMPORT_URL, "https://example.com/a.js")
    markup = f'<script type="importmap" id="wp-importmap">{text}</script>'
    if edit == "twice":
        markup += markup
    elif edit == "preload-mismatch":
        other = IMPORT_URL.replace("index.js", "index.min.js")
        example[0][other] = example[0][IMPORT_URL]
        markup += f'<link rel="modulepreload" href="{other}">'
    with pytest.raises(audit.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
        verify(example, markup)


@pytest.mark.parametrize("target", [[], {}, 1, True, None])
def test_non_string_import_target_fails_with_bounded_audit_error(example, target):
    text = json.dumps({"imports": {"@wordpress/interactivity": target}})
    with pytest.raises(audit.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
        verify(example, f'<script type="importmap" id="wp-importmap">{text}</script>')


@pytest.mark.parametrize(
    "edit", ["bytes", "redirect", "mime", "cookie", "url", "status"]
)
def test_exact_url_cannot_launder_changed_resource(example, edit):
    responses = example[1]
    row = responses[JS_URL]
    changes = {
        "bytes": {"body": b"new unapproved script"},
        "redirect": {
            "status": 302,
            "headers": (("Location", "https://example.com/a.js"),),
        },
        "mime": {"headers": (("Content-Type", "text/html"),)},
        "cookie": {"headers": row.headers + (("Set-Cookie", "synthetic=value"),)},
        "url": {"url": JS_URL + "&different=1"},
        "status": {"status": 404},
    }
    responses[JS_URL] = replace(row, **changes[edit])
    with pytest.raises(audit.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
        verify(example, SCRIPT)


def test_unknown_noscript_pixel_rejected_by_prewrite_image_scope(example):
    markup = '<noscript><img src="https://pixel.wp.com/g.gif"></noscript>'
    with pytest.raises(audit.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
        runtime.verify_page(
            response(runtime.ORIGIN + "/", markup.encode()),
            example[0],
            example[2],
            allowed_images=frozenset(),
        )


def test_approved_image_cannot_hide_unapproved_responsive_pixel(example):
    allowed = runtime.THEME_PREFIX + "assets/images/home-hero.webp"
    markup = f'<img src="{allowed}" srcset="https://pixel.wp.com/probe.gif 2x">'
    with pytest.raises(audit.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
        runtime.verify_page(
            response(runtime.ORIGIN + "/", markup.encode()),
            example[0],
            example[2],
            allowed_images=frozenset({allowed}),
        )


def test_approved_image_without_responsive_alternative_passes(example):
    allowed = runtime.THEME_PREFIX + "assets/images/home-hero.webp"
    markup = f'<img src="{allowed}" alt="Approved illustration">'
    assert (
        runtime.verify_page(
            response(runtime.ORIGIN + "/", markup.encode()),
            example[0],
            example[2],
            allowed_images=frozenset({allowed}),
        )
        == {}
    )


@pytest.mark.parametrize(
    "url",
    [
        JS_URL + "&other=1",
        JS_URL + "&ver=" + VERSION,
        JS_URL + "#fragment",
        JS_URL.replace("https:", "http:"),
        JS_URL.replace("kurashinoshirube.com", "example.com"),
        JS_URL.replace("kurashinoshirube.com", "user@kurashinoshirube.com"),
        JS_URL.replace("kurashinoshirube.com", "kurashinoshirube.com:444"),
        runtime.ORIGIN + "/wp-json/collect?ver=" + VERSION,
        JS_URL.replace(VERSION, "1.4.0"),
        MODULE_URL.replace("b" * 20, "1.4.0"),
        LEGACY_CSS_URL.replace("theme.css", "other.css"),
        LEGACY_CSS_URL + "&extra=1",
        LEGACY_CSS_URL + "&ver=1.4.0",
        LEGACY_CSS_URL.replace("1.4.0", "1.4"),
        LEGACY_CSS_URL.replace("1.4.0", "1%2E4%2E0"),
        LEGACY_CSS_URL + "#fragment",
    ],
)
def test_resource_transport_does_not_expand_page_url_boundary(url):
    with pytest.raises(audit.seo.AuditError, match="HTTP_URL_OUT_OF_BOUNDARY"):
        audit.seo.BoundedHttpsTransport(
            audit.seo.load_contract(), allowed_resource_urls=frozenset({url})
        )


@pytest.mark.parametrize(
    "url",
    [JS_URL, LEGACY_CSS_URL, LEGACY_CSS_URL.replace("theme.css", "editorial-v2.css")],
)
def test_query_is_opt_in_and_sent_without_modification(monkeypatch, url):
    contract = audit.seo.load_contract()
    with pytest.raises(audit.seo.AuditError, match="HTTP_URL_OUT_OF_BOUNDARY"):
        audit.seo.BoundedHttpsTransport(contract).get(url)
    connection = Mock()
    reply = connection.getresponse.return_value
    reply.status = 200
    reply.read.return_value = b"approved fixture"
    reply.getheaders.return_value = [("Content-Type", "text/javascript")]
    monkeypatch.setattr(
        audit.seo.http.client, "HTTPSConnection", lambda *a, **kw: connection
    )
    transport = audit.seo.BoundedHttpsTransport(
        contract, allowed_resource_urls=frozenset({url})
    )
    assert transport.get(url).url == url
    assert connection.request.call_args.args[1] == url.removeprefix(runtime.ORIGIN)
    with pytest.raises(audit.seo.AuditError, match="HTTP_URL_OUT_OF_BOUNDARY"):
        transport.get(url.replace(VERSION, "f" * 64).replace("1.4.0", "1.4.1"))


@pytest.fixture
def legacy_theme_files():
    # Exact enqueue shapes from the audited 1.4.0 baseline, not live HTML.
    functions = f"const KURASHINOSHIRUBE_THEME_RUNTIME_REVISION = '{VERSION}';\n"
    functions += "const KURASHINOSHIRUBE_THEME_VERSION = '1.4.0';\n"
    functions += """
    $theme = wp_get_theme();
    wp_enqueue_style(
        'kurashinoshirube-editorial',
        get_stylesheet_directory_uri() . '/assets/theme.css',
        array(),
        $theme->get('Version')
    );
    wp_enqueue_style(
        'kurashinoshirube-editorial-v2',
        get_stylesheet_directory_uri() . '/assets/editorial-v2.css',
        array('kurashinoshirube-editorial'),
        $theme->get('Version')
    );
    """
    return {
        "functions.php": functions.encode(),
        "style.css": b"/*\nVersion: 1.4.0\n*/\n",
        "assets/theme.css": b"p{color:navy}",
        "assets/editorial-v2.css": b"p{color:blue}",
        "assets/editorial-navigation.js": b"approved fixture JS",
    }


@pytest.mark.parametrize("legacy", [True, False])
def test_css_uses_only_the_audited_enqueue_version(legacy_theme_files, legacy):
    files = legacy_theme_files
    if not legacy:
        files["functions.php"] = files["functions.php"].replace(
            b"$theme->get('Version')", b"KURASHINOSHIRUBE_THEME_RUNTIME_REVISION"
        )
    resources = runtime.resources_for_theme(files)
    version = "1.4.0" if legacy else VERSION
    other_version = VERSION if legacy else "1.4.0"
    for path in ("assets/theme.css", "assets/editorial-v2.css"):
        url = runtime.THEME_PREFIX + path + "?ver=" + version
        assert resources[url].sha256 == audit.digest(files[path])
        assert resources[url].size == len(files[path])
        assert runtime.THEME_PREFIX + path + "?ver=" + other_version not in resources
        markup = f'<link rel="stylesheet" href="{url}">'
        transport = Mock()
        transport.get.return_value = response(url, files[path], "text/css")
        assert set(
            runtime.verify_page(
                response(runtime.ORIGIN + "/", markup.encode()), resources, transport
            )
        ) == {url}
        with pytest.raises(audit.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
            runtime.verify_page(
                response(
                    runtime.ORIGIN + "/",
                    markup.replace(version, other_version).encode(),
                ),
                resources,
                transport,
            )
    assert JS_URL in resources
    assert JS_URL.replace(VERSION, "1.4.0") not in resources


@pytest.mark.parametrize(
    "edit",
    [
        "missing-header",
        "duplicate-header",
        "mismatched-header",
        "query-header",
        "missing-constant",
        "duplicate-constant",
        "duplicate-enqueue",
    ],
)
def test_legacy_css_version_metadata_must_be_unambiguous(legacy_theme_files, edit):
    files = legacy_theme_files
    if edit == "missing-header":
        del files["style.css"]
    elif edit == "duplicate-header":
        files["style.css"] += b"Version: 1.4.0\n"
    elif edit == "mismatched-header":
        files["style.css"] = b"Version: 1.4.1\n"
    elif edit == "query-header":
        files["style.css"] = b"Version: 1.4.0&extra=1\n"
        files["functions.php"] = files["functions.php"].replace(
            b"1.4.0", b"1.4.0&extra=1"
        )
    elif edit == "missing-constant":
        files["functions.php"] = files["functions.php"].replace(
            b"const KURASHINOSHIRUBE_THEME_VERSION = '1.4.0';\n", b""
        )
    elif edit == "duplicate-constant":
        files["functions.php"] += b"\nconst KURASHINOSHIRUBE_THEME_VERSION = '1.4.0';\n"
    elif edit == "duplicate-enqueue":
        files["functions.php"] += files["functions.php"].split(
            b"$theme = wp_get_theme();"
        )[1]
    with pytest.raises(audit.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
        runtime.resources_for_theme(files)


def test_current_dependency_lock_has_both_exact_variants_and_no_dynamic_imports():
    lock = json.loads(runtime.LOCK.read_text())
    assert (
        lock["image"]
        in (
            runtime.ROOT / "changes/wordpress-local-preview-v1/compose.yaml"
        ).read_text()
    )
    rows = lock["modules"]
    assert len(rows) == 6
    assert {row["variant"] for row in rows} == {"debug", "minified"}
    assert all(
        row["static_imports"] in ([], ["@wordpress/interactivity"]) for row in rows
    )
    assert len({row["path"] for row in rows}) == 6
