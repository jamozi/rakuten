"""Synthetic migration regressions, not production/audit approval evidence."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import base64
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import raos_wordpress_incremental_seo_audit as audit
from scripts import raos_wordpress_incremental_publication as port

runtime = audit.runtime
BASELINE = "b" * 64
CANDIDATE = "c" * 64
NOW = datetime(2026, 9, 6, tzinfo=UTC)
URLS = frozenset({runtime.ORIGIN + "/", runtime.ORIGIN + "/guide/"})
HINT = '<link rel="dns-prefetch" href="//www.googletagmanager.com">'
POST_CONTENT = '<!-- wp:post-content {"layout":{"type":"default"}} /-->'


def saved_home(*, image: str = "") -> str:
    encoded = base64.b64encode(b"RIFF\x04\x00\x00\x00WEBP").decode()
    return (
        '<div id="ks-magazine" style="--km-hero-image:url(\'data:image/webp;base64,'
        + encoded
        + "')\"><header class=\"km-header\"><form action=\"/\" method=\"get\" role=\"search\">"
        '<label for="search">Search</label><input id="search" name="s" type="search">'
        '<button type="submit">Search</button></form></header><h1>Home</h1>'
        + image
        + "</div>"
    )


@pytest.fixture
def world(monkeypatch):
    before = {
        "functions.php": b"const KURASHINOSHIRUBE_THEME_RUNTIME_REVISION = '"
        + BASELINE.encode()
        + b"';\n"
    }
    after = {"functions.php": before["functions.php"] + runtime.DNS_REMOVAL_SOURCE}
    monkeypatch.setattr(
        runtime,
        "trusted_theme_files",
        lambda tree, **kw: before if tree == BASELINE else after,
    )
    monkeypatch.setattr(
        runtime.seo,
        "load_contract",
        lambda: SimpleNamespace(
            items=[SimpleNamespace(url=url) for url in sorted(URLS)]
        ),
    )
    transport = Mock()
    responses = {
        url: runtime.seo.HttpResponse(
            url,
            200,
            (("Content-Type", "text/html"),),
            HINT.encode(),
            "2026-09-06T00:00:00Z",
        )
        for url in URLS
    }
    transport.get.side_effect = lambda url: responses[url]
    monkeypatch.setattr(
        runtime.seo, "BoundedHttpsTransport", lambda *a, **kw: transport
    )
    policy = runtime.build_dns_transition(
        baseline_tree=BASELINE, candidate_tree=CANDIDATE, page_urls=URLS
    )
    return SimpleNamespace(
        policy=policy, responses=responses, after=after, transport=transport
    )


def verify(
    world,
    current=BASELINE,
    *,
    opt_in=True,
    home_markup="<div><h1>Home</h1></div>",
    home_post_type="page",
):
    return runtime.verify_before_write(
        current_tree=current,
        baseline_tree=BASELINE,
        candidate_tree=CANDIDATE,
        now=NOW,
        snapshot={
            "schema": "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1",
            "documents": [
                {
                    "slug": "home",
                    "status": "publish",
                    "post_type": home_post_type,
                    "block_markup": home_markup,
                },
                {"slug": "guide", "status": "publish", "post_type": "post", "block_markup": ""},
            ],
        },
        runtime_transition=world.policy if opt_in else None,
    )


def test_saved_home_runtime_uses_closed_parser_and_exact_style_only_for_post_content(
    world,
):
    markup = saved_home()
    world.after["templates/front-page.html"] = POST_CONTENT.encode()
    for url, response in list(world.responses.items()):
        world.responses[url] = replace(response, body=b"<p>Clean page</p>")
    world.responses[runtime.ORIGIN + "/"] = replace(
        world.responses[runtime.ORIGIN + "/"], body=markup.encode()
    )
    result = verify(world, current=CANDIDATE, home_markup=markup)
    assert result["state"] == "CLOSED_DECLARED_RUNTIME_VERIFIED"

    world.responses[runtime.ORIGIN + "/"] = replace(
        world.responses[runtime.ORIGIN + "/"],
        body=markup.replace("--km-hero-image", "--changed-image").encode(),
    )
    with pytest.raises(runtime.seo.AuditError):
        verify(world, current=CANDIDATE, home_markup=markup)


def test_fixed_template_baseline_parses_saved_home_without_requiring_it_in_output(
    world,
):
    assert verify(world, home_markup=saved_home())["state"] == runtime.DNS_TRANSITION_STATE


@pytest.mark.parametrize("markup", ["", "<p>Saved home body</p>"])
def test_fixed_template_baseline_accepts_home_without_a_saved_heading(world, markup):
    assert verify(world, home_markup=markup)["state"] == runtime.DNS_TRANSITION_STATE
    with pytest.raises(runtime.seo.AuditError):
        audit._home_projection(markup)


def test_post_content_home_without_preserved_webp_style_remains_supported(world):
    markup = '<div id="ks-magazine"><h1>Home</h1></div>'
    world.after["templates/front-page.html"] = POST_CONTENT.encode()
    for url, response in list(world.responses.items()):
        world.responses[url] = replace(response, body=b"<p>Clean page</p>")
    world.responses[runtime.ORIGIN + "/"] = replace(
        world.responses[runtime.ORIGIN + "/"], body=markup.encode()
    )
    assert (
        verify(world, current=CANDIDATE, home_markup=markup)["state"]
        == "CLOSED_DECLARED_RUNTIME_VERIFIED"
    )


def test_home_runtime_branch_requires_the_home_document_to_be_a_page(world):
    with pytest.raises(runtime.seo.AuditError):
        verify(world, home_post_type="post")


@pytest.mark.parametrize(
    "image",
    [
        '<img src="https://example.com/unbound.png" alt="">',
        '<img src="x" onerror="alert(1)" alt="">',
    ],
)
def test_saved_home_image_inventory_does_not_expand_urls_or_active_markup(image):
    with pytest.raises((runtime.seo.AuditError, ValueError)):
        audit.home_image_urls(saved_home(image=image))


def test_captured_home_theme_reference_is_allowed_only_for_fixed_baseline(world):
    path = "/wp-content/themes/kurashinoshirube-child/assets/images/old-missing.png"
    markup = f'<div><h1>Home</h1><img src="{path}" alt=""></div>'
    home_url = runtime.ORIGIN + "/"
    world.responses[home_url] = replace(
        world.responses[home_url], body=(HINT + markup).encode()
    )
    assert verify(world, home_markup=markup)["state"] == runtime.DNS_TRANSITION_STATE

    world.responses[home_url] = replace(
        world.responses[home_url], body=markup.encode()
    )
    with pytest.raises(runtime.seo.AuditError):
        verify(world, current=CANDIDATE, opt_in=False, home_markup=markup)


def test_baseline_transition_is_distinct_bound_and_does_not_fetch_external_host(world):
    result = verify(world)
    assert result["state"] == runtime.DNS_TRANSITION_STATE
    assert result["runtime_transition_sha256"] == runtime.seo._sha256(
        runtime.canonical(world.policy)
    )
    assert {
        url: page["dns_hints"] for url, page in result["pages"].items()
    } == dict.fromkeys(URLS, 1)
    assert {call.args[0] for call in world.transport.get.call_args_list} == URLS
    assert port.runtime_precondition_matches(
        result, {"runtime_transition": world.policy}, BASELINE
    )
    assert not port.runtime_precondition_matches(result, {}, BASELINE)
    assert not port.runtime_precondition_matches(
        result, {"runtime_transition": world.policy}, CANDIDATE
    )


def test_default_is_strict_no_fallback(world):
    with pytest.raises(runtime.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
        verify(world, opt_in=False)


def test_candidate_installed_always_requires_zero_hints(world):
    with pytest.raises(runtime.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
        verify(world, current=CANDIDATE)
    for url, response in list(world.responses.items()):
        world.responses[url] = replace(
            response, body=b"<p>Candidate without DNS hints</p>"
        )
    result = verify(world, current=CANDIDATE)
    assert result["state"] == "CLOSED_DECLARED_RUNTIME_VERIFIED"
    assert "runtime_transition_sha256" not in result
    assert port.runtime_precondition_matches(
        result, {"runtime_transition": world.policy}, CANDIDATE
    )
    assert not port.runtime_precondition_matches(
        result, {"runtime_transition": world.policy}, BASELINE
    )


@pytest.mark.parametrize(
    "markup",
    [
        "",
        HINT + HINT,
        HINT.replace("dns-prefetch", "preconnect"),
        HINT.replace("www.googletagmanager.com", "other.example"),
        HINT.replace("//www", "https://www"),
        HINT.replace(">", ' crossorigin="anonymous">'),
        HINT.replace(">", ' href="//www.googletagmanager.com">'),
        HINT + '<script>fetch("/track")</script>',
        HINT + '<link rel="dns-prefetch" href="//example.com">',
        HINT + '<img src="https://example.com/pixel">',
        HINT + '<style>@import "https://example.com/style.css"</style>',
        HINT + '<script src="https://www.googletagmanager.com/gtag/js"></script>',
    ],
)
def test_exact_count_attributes_and_other_runtime_guards_remain(world, markup):
    url = sorted(URLS)[0]
    world.responses[url] = replace(world.responses[url], body=markup.encode())
    with pytest.raises(runtime.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
        verify(world)


@pytest.mark.parametrize(
    "header",
    [
        ("Set-Cookie", "fixture=1"),
        ("Link", '<//www.googletagmanager.com>; rel="dns-prefetch"'),
        ("Refresh", "0;url=https://example.com"),
    ],
)
def test_response_header_exceptions_are_never_granted(world, header):
    url = sorted(URLS)[0]
    world.responses[url] = replace(
        world.responses[url], headers=world.responses[url].headers + (header,)
    )
    with pytest.raises(runtime.seo.AuditError, match="MEASUREMENT_OFF_MISMATCH"):
        verify(world)


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema", "other"),
        ("mode", "measured-admin"),
        ("candidate_theme_sha256", "a" * 64),
        ("baseline_theme_sha256", CANDIDATE),
        ("candidate_functions_sha256", "f" * 64),
        ("expected_baseline_hints", {runtime.ORIGIN + "/": 1}),
        ("expected_baseline_hints", dict.fromkeys(URLS, True)),
        ("expected_baseline_hints", dict.fromkeys(URLS, 1.0)),
        ("expected_baseline_hints", dict.fromkeys(URLS, 2)),
        ("hint", {"rel": "preconnect", "href": "//www.googletagmanager.com"}),
        ("post_apply_state", runtime.DNS_TRANSITION_STATE),
        ("unexpected", True),
    ],
)
def test_policy_tampering_does_not_become_runtime_permission(world, key, value):
    world.policy = deepcopy(world.policy)
    world.policy[key] = value
    with pytest.raises(runtime.seo.AuditError):
        verify(world)


def test_filter_bytes_and_actual_current_tree_are_rechecked(world):
    with pytest.raises(runtime.seo.AuditError):
        verify(world, current="d" * 64)
    world.after["functions.php"] = world.after["functions.php"].replace(
        b"unset($urls[$key]);", b"// missing removal"
    )
    with pytest.raises(runtime.seo.AuditError):
        verify(world)


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "CLOSED_DECLARED_RUNTIME_VERIFIED"),
        ("runtime_transition_sha256", "f" * 64),
        ("theme_tree_sha256", CANDIDATE),
        ("pages", {}),
        ("pages", {url: {"dns_hints": True} for url in URLS}),
    ],
)
def test_transitional_result_tampering_cannot_pass_publication_port(
    world, field, value
):
    result = verify(world)
    result[field] = value
    assert not port.runtime_precondition_matches(
        result, {"runtime_transition": world.policy}, BASELINE
    )


def test_strict_page_readback_has_no_implicit_transition_switch(world):
    with pytest.raises(runtime.seo.AuditError):
        runtime.verify_page(world.responses[sorted(URLS)[0]], {}, world.transport)


@pytest.mark.parametrize("count", [True, 1.0, 2, -1])
def test_parser_rejects_open_ended_or_ambiguous_exception_counts(count):
    with pytest.raises(runtime.seo.AuditError):
        runtime.RuntimeMarkup({}, expected_dns_hints=count)


def test_captured_relative_reference_is_baseline_only_and_page_bound(world):
    path = "/wp-content/themes/kurashinoshirube-child/assets/images/old-missing.png"
    markup = f'<img src="{path}" alt="">'
    document = {"slug": "guide", "status": "publish", "post_type": "post", "block_markup": markup}
    url = runtime.ORIGIN + "/guide/"
    world.responses[url] = replace(world.responses[url], body=(HINT + markup).encode())
    args = dict(
        baseline_tree=BASELINE,
        candidate_tree=CANDIDATE,
        now=NOW,
        snapshot={
            "schema": "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1",
            "documents": [
                {
                    "slug": "home",
                    "status": "publish",
                    "post_type": "page",
                    "block_markup": "<div><h1>Home</h1></div>",
                },
                document,
            ],
        },
        runtime_transition=world.policy,
    )
    result = runtime.verify_before_write(current_tree=BASELINE, **args)
    assert result["state"] == runtime.DNS_TRANSITION_STATE
    # It was never granted to a different page, nor learned from a live response.
    home = runtime.ORIGIN + "/"
    world.responses[home] = replace(
        world.responses[home], body=(HINT + markup).encode()
    )
    with pytest.raises(runtime.seo.AuditError):
        runtime.verify_before_write(current_tree=BASELINE, **args)
    for url, response in list(world.responses.items()):
        world.responses[url] = replace(
            response, body=response.body.replace(HINT.encode(), b"")
        )
    world.responses[home] = replace(world.responses[home], body=b"<p>Clean home</p>")
    with pytest.raises(runtime.seo.AuditError):
        runtime.verify_before_write(current_tree=CANDIDATE, **args)


@pytest.mark.parametrize(
    "path",
    [
        "//example.com/pixel.png",
        "/wp-content/uploads/image.png",
        "/wp-content/themes/kurashinoshirube-child/assets/images/a.png?track=1",
        "/wp-content/themes/kurashinoshirube-child/assets/images/../a.png",
    ],
)
def test_captured_inventory_does_not_expand_into_generic_root_relative_requests(path):
    assert runtime.captured_theme_image_urls(f'<img src="{path}">') == frozenset()
