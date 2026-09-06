"""Opt-in reader runtime uses reviewed bytes, a closed config, and no legacy exemption."""

from __future__ import annotations

from copy import deepcopy
import base64
from hashlib import sha256
import json

import pytest

from scripts import raos_wordpress_incremental_seo_audit as audit

runtime = audit.runtime
BOUNDED_TRANSPORT = runtime.seo.BoundedHttpsTransport
ORIGIN = "https://kurashinoshirube.com"
PREFIX = ORIGIN + "/wp-content/plugins/raos-reader-measurement/"
ENDPOINT = ORIGIN + "/wp-json/raos-reader/v1/events"
POLICY = b"<p>Synthetic reviewed privacy disclosure.</p>"
ARTICLE = {
    "article_id": "article-a",
    "slug": "reviewed-article",
    "navigation": [
        {
            "target_article_id": "article-b",
            "journey_stage": "compare",
            "path": "/related-article/",
        }
    ],
    "panels": [{"panel_id": "reader-evidence", "kind": "details"}],
    "references": [
        {
            "source_ref": "SRC-official-manual",
            "url": "https://manufacturer.example/manual/",
        }
    ],
}


def encode(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()


@pytest.fixture
def reviewed():
    contract = {
        "schema": "RAOS_READER_MEASUREMENT_ALLOWLIST_V1",
        "version": "1.0.0",
        "target_origin": ORIGIN,
        "events": [
            "guide_navigation",
            "decision_check_open",
            "official_reference_open",
        ],
        "source_hashes": {
            f"changes/editorial-portfolio-v3/article-{index}.json": "a" * 64
            for index in range(10)
        },
        "articles": [
            ARTICLE,
            {
                "article_id": "article-b",
                "slug": "related-article",
                "navigation": [],
                "panels": [],
                "references": [],
            },
        ]
        + [
            {
                "article_id": f"article-{index}",
                "slug": f"article-{index}",
                "navigation": [],
                "panels": [],
                "references": [],
            }
            for index in range(8)
        ],
    }
    files = {
        "config/reader-allowlist.v1.json": encode(contract),
        "assets/reader-measurement.js": b"/* Synthetic reviewed script, not a production trust anchor. */",
        "assets/reader-measurement.css": b".raos-reader-consent{display:block}",
    }
    files["config/reader-runtime.v1.json"] = encode(
        {
            "schema": "RAOS_READER_MEASUREMENT_RUNTIME_V1",
            "plugin_version": "1.0.0",
            "contract_sha256": sha256(
                files["config/reader-allowlist.v1.json"]
            ).hexdigest(),
            "policy_sha256": sha256(POLICY).hexdigest(),
            "policy_slug": "privacy-policy",
            "revision": "c" * 64,
            "files": {path: sha256(raw).hexdigest() for path, raw in files.items()},
        }
    )
    config = json.loads(files["config/reader-runtime.v1.json"])
    revision_input = "".join(
        path + ":" + digest + "\n" for path, digest in sorted(config["files"].items())
    )
    config["revision"] = sha256(
        (
            revision_input + "policy:" + config["policy_sha256"] + "\nversion:1.0.0\n"
        ).encode()
    ).hexdigest()
    files["config/reader-runtime.v1.json"] = encode(config)
    manifest = {
        "schema": "RAOS_READER_MEASUREMENT_RUNTIME_MANIFEST_V1",
        "plugin_version": "1.0.0",
        "default_enabled": False,
        "approval_required": True,
        "plugin_slug": "raos-reader-measurement",
        "privacy_source": "changes/editorial-portfolio-v3/reader-measurement-privacy.html",
        "contract_sha256": config["contract_sha256"],
        "policy_sha256": config["policy_sha256"],
        "revision": config["revision"],
        "plugin_root": "changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement",
        "plugin_files": [
            {"path": path, "size": len(raw), "sha256": sha256(raw).hexdigest()}
            for path, raw in sorted(files.items())
        ],
    }
    return {"files": files, "manifest": manifest, "policy": POLICY}


def bind(reviewed, *, enabled=False, **overrides):
    factory = getattr(runtime, "reader_measurement_runtime", None)
    assert callable(factory), "explicit reader runtime factory is required"
    raw = encode(reviewed["manifest"])
    options = {
        "expected_manifest_sha256": sha256(raw).hexdigest(),
        "expected_policy_sha256": sha256(reviewed["policy"]).hexdigest(),
        "expected_collection_enabled": enabled,
    }
    options.update(overrides)
    return factory(raw, reviewed["files"], reviewed["policy"], **options)


def test_reviewed_profile_exposes_only_two_exact_versioned_assets(reviewed):
    profile = bind(reviewed)
    assert profile.profile == "reader-minimal-v1"
    assert profile.expected_collection_enabled is False
    assert profile.manifest_sha256 == sha256(encode(reviewed["manifest"])).hexdigest()
    assert (
        profile.contract_sha256
        == sha256(reviewed["files"]["config/reader-allowlist.v1.json"]).hexdigest()
    )
    assert profile.policy_sha256 == sha256(POLICY).hexdigest()
    assert set(profile.resources) == {
        PREFIX + path + "?ver=" + sha256(reviewed["files"][path]).hexdigest()
        for path in ("assets/reader-measurement.js", "assets/reader-measurement.css")
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_manifest_sha256", "f" * 64),
        ("expected_policy_sha256", "f" * 64),
        ("expected_manifest_sha256", None),
        ("expected_policy_sha256", "a" * 64 + "\n"),
        ("expected_collection_enabled", None),
        ("expected_collection_enabled", "false"),
        ("expected_collection_enabled", 0),
    ],
)
def test_unbound_inputs_and_unknown_expected_state_fail_closed(reviewed, field, value):
    with pytest.raises(runtime.seo.AuditError):
        bind(reviewed, **{field: value})


@pytest.mark.parametrize(
    "path",
    [
        "assets/reader-measurement.js",
        "assets/reader-measurement.css",
        "config/reader-allowlist.v1.json",
    ],
)
def test_manifest_hashes_cannot_be_learned_from_replacement_plugin_bytes(
    reviewed, path
):
    reviewed["files"][path] += b" "
    with pytest.raises(runtime.seo.AuditError):
        bind(reviewed)


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "traversal", "missing_css", "wrong_size", "enabled_by_default"],
)
def test_manifest_refuses_ambiguous_or_unbounded_plugin_inventory(reviewed, mutation):
    rows = reviewed["manifest"]["plugin_files"]
    if mutation == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif mutation == "traversal":
        rows[0]["path"] = "../outside.js"
    elif mutation == "missing_css":
        rows[:] = [
            row for row in rows if row["path"] != "assets/reader-measurement.css"
        ]
    elif mutation == "wrong_size":
        rows[0]["size"] += 1
    else:
        reviewed["manifest"]["default_enabled"] = True
    with pytest.raises(runtime.seo.AuditError):
        bind(reviewed)


@pytest.mark.parametrize(
    "method,url",
    [
        ("GET", ENDPOINT),
        ("POST", ENDPOINT + "?event=1"),
        ("POST", ENDPOINT + "/"),
        ("POST", ENDPOINT + "#fragment"),
        ("POST", "//kurashinoshirube.com/wp-json/raos-reader/v1/events"),
        ("POST", "https://external.example/wp-json/raos-reader/v1/events"),
        ("POST", ORIGIN + "/wp-json/raos-measurement/v1/events"),
        ("POST", "https://www.google-analytics.com/g/collect"),
        ("POST", ORIGIN + "/wp-json/raos-reader/v1/%65vents"),
        ("POST", ORIGIN + "/wp-json/raos-reader/v1/../events"),
        ("post", ENDPOINT),
    ],
)
def test_collection_cannot_gain_another_method_endpoint_origin_or_old8_exemption(
    reviewed, method, url
):
    assert (
        bind(reviewed, enabled=True).allows_collector_request(
            url, method, consent_granted=True
        )
        is False
    )


def test_even_the_exact_collector_requires_enabled_state_and_explicit_consent(reviewed):
    off = bind(reviewed)
    on = bind(reviewed, enabled=True)
    assert off.allows_collector_request(ENDPOINT, "POST", consent_granted=True) is False
    assert on.allows_collector_request(ENDPOINT, "POST", consent_granted=False) is False
    assert on.allows_collector_request(ENDPOINT, "POST", consent_granted=1) is False
    assert on.allows_collector_request(ENDPOINT, "POST", consent_granted=True) is True


def refresh_manifest(reviewed):
    reviewed["manifest"]["plugin_files"] = [
        {"path": path, "size": len(raw), "sha256": sha256(raw).hexdigest()}
        for path, raw in sorted(reviewed["files"].items())
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("contract_sha256", "f" * 64),
        ("policy_sha256", "f" * 64),
        ("policy_slug", "other-policy"),
        ("revision", None),
        ("schema", "Other"),
        ("plugin_version", "1.2.3"),
        ("files", {"assets/reader-measurement.js": "f" * 64}),
    ],
)
def test_plugin_runtime_cross_binds_policy_contract_revision_and_asset_hashes(
    reviewed, field, value
):
    config = json.loads(reviewed["files"]["config/reader-runtime.v1.json"])
    config[field] = value
    reviewed["files"]["config/reader-runtime.v1.json"] = encode(config)
    refresh_manifest(reviewed)
    with pytest.raises(runtime.seo.AuditError):
        bind(reviewed)


@pytest.mark.parametrize("enabled", [False, True])
def test_client_config_is_exact_reviewed_row_and_state_for_this_page(reviewed, enabled):
    profile = bind(reviewed, enabled=enabled)
    expected = {
        "schema": "RAOSReaderMeasurementClientV1",
        "origin": ORIGIN,
        "endpoint": "/wp-json/raos-reader/v1/events",
        "collection_enabled": enabled,
        "contract_sha256": sha256(
            reviewed["files"]["config/reader-allowlist.v1.json"]
        ).hexdigest(),
        "policy_sha256": sha256(POLICY).hexdigest(),
        "policy_version": sha256(POLICY).hexdigest(),
        "article": ARTICLE,
    }
    assert profile.client_config(ORIGIN + "/reviewed-article/") == expected
    expected["article"] = None
    for page in ("/", "/privacy-policy/", "/unregistered-page/"):
        assert profile.client_config(ORIGIN + page) == expected


@pytest.mark.parametrize(
    "page_url",
    [
        None,
        "https://other.example/reviewed-article/",
        ORIGIN + "/reviewed-article/?x=1",
        ORIGIN + "/reviewed-article/#fragment",
        ORIGIN + "/reviewed-article",
        ORIGIN + "/../reviewed-article/",
    ],
)
def test_profile_does_not_misreport_article_identity_for_ambiguous_or_external_page(
    reviewed, page_url
):
    with pytest.raises(runtime.seo.AuditError):
        bind(reviewed).client_config(page_url)


def materialize(reviewed, root):
    manifest_path = root / "changes/reader-measurement-v1/runtime-manifest.v1.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(encode(reviewed["manifest"]))
    plugin_root = root / reviewed["manifest"]["plugin_root"]
    for path, raw in reviewed["files"].items():
        target = plugin_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    policy_path = (
        root / "changes/editorial-portfolio-v3/reader-measurement-privacy.html"
    )
    policy_path.parent.mkdir(parents=True)
    policy_path.write_bytes(reviewed["policy"])
    return manifest_path, policy_path, plugin_root


def build(reviewed):
    builder = getattr(runtime, "build_reader_measurement_runtime", None)
    assert callable(builder), "fixed repository-source builder is required"
    return builder(
        expected_manifest_sha256=sha256(encode(reviewed["manifest"])).hexdigest(),
        expected_policy_sha256=sha256(reviewed["policy"]).hexdigest(),
        expected_collection_enabled=False,
    )


def test_repository_builder_rehashes_fixed_reviewed_inputs(
    reviewed, tmp_path, monkeypatch
):
    materialize(reviewed, tmp_path)
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    profile = build(reviewed)
    assert profile.client_config(ORIGIN + "/reviewed-article/")["article"] == ARTICLE
    assert profile.expected_collection_enabled is False


@pytest.mark.parametrize("target", ["manifest", "policy", "asset"])
def test_repository_builder_refuses_symlinked_reviewed_inputs(
    reviewed, tmp_path, monkeypatch, target
):
    manifest, policy, plugin_root = materialize(reviewed, tmp_path)
    path = {
        "manifest": manifest,
        "policy": policy,
        "asset": plugin_root / "assets/reader-measurement.js",
    }[target]
    backing = tmp_path / "outside-binding"
    backing.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(backing)
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    with pytest.raises(runtime.seo.AuditError):
        build(reviewed)


def config_script(profile, *, page_url=ORIGIN + "/reviewed-article/", config=None):
    data = profile.client_config(page_url) if config is None else config
    return (
        '<script type="application/json" id="raos-reader-measurement-config">'
        + encode(data).decode()
        + "</script>"
    )


def reader_assets(reviewed):
    def asset(path):
        raw = reviewed["files"][path]
        return (
            PREFIX + path + "?ver=" + sha256(raw).hexdigest(),
            "sha256-" + base64.b64encode(sha256(raw).digest()).decode(),
        )

    js, js_integrity = asset("assets/reader-measurement.js")
    css, css_integrity = asset("assets/reader-measurement.css")
    return (
        f'<link rel="stylesheet" id="raos-reader-measurement-style-css" href="{css}" media="all" integrity="{css_integrity}" crossorigin="anonymous">'
        f'<script id="raos-reader-measurement-js" src="{js}" integrity="{js_integrity}" crossorigin="anonymous"></script>'
    )


def parser(profile, **kwargs):
    return runtime.RuntimeMarkup(
        {}, reader_measurement=profile, page_url=ORIGIN + "/reviewed-article/", **kwargs
    )


@pytest.mark.parametrize("enabled,state", [(False, "OFF"), (True, "ON")])
def test_parser_distinguishes_unknown_and_validated_declared_collection_state(
    reviewed, enabled, state
):
    profile = bind(reviewed, enabled=enabled)
    parsed = parser(profile)
    assert parsed.reader_collection_state == "UNKNOWN"
    parsed.feed(config_script(profile))
    assert parsed.reader_collection_state == state
    # A valid isolated config still cannot finish an audit without consent/assets.
    with pytest.raises(runtime.seo.AuditError):
        parsed.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "Other"),
        ("endpoint", "/wp-json/raos-measurement/v1/events"),
        ("endpoint", "https://external.example/collect"),
        ("origin", "https://external.example"),
        ("collection_enabled", True),
        ("collection_enabled", 0),
        ("collection_enabled", None),
        ("contract_sha256", "f" * 64),
        ("policy_sha256", "f" * 64),
        ("policy_version", "unknown"),
        ("article", None),
        ("article", {"article_id": "article-b"}),
        ("approval_actor_id", 42),
    ],
)
def test_parser_refuses_config_drift_unknown_fields_and_state_coercion(
    reviewed, field, value
):
    profile = bind(reviewed)
    config = profile.client_config(ORIGIN + "/reviewed-article/")
    config[field] = value
    with pytest.raises(runtime.seo.AuditError):
        parser(profile).feed(config_script(profile, config=config))


@pytest.mark.parametrize(
    "markup",
    [
        '<script type="application/json" id="unregistered-config">{}</script>',
        '<script id="raos-reader-measurement-config">fetch("/collect")</script>',
        '<script type="application/json" id="raos-reader-measurement-config">{"schema":1,"schema":2}</script>',
        '<script type="application/json" id="raos-reader-measurement-config" onclick="evil()">{}</script>',
    ],
)
def test_reader_mode_never_grants_generic_json_or_inline_javascript(reviewed, markup):
    with pytest.raises(runtime.seo.AuditError):
        parser(bind(reviewed)).feed(markup)


def test_default_parser_keeps_rejecting_reader_scripts_and_config(reviewed):
    profile = bind(reviewed)
    for markup in (reader_assets(reviewed), config_script(profile)):
        with pytest.raises(runtime.seo.AuditError):
            parsed = runtime.RuntimeMarkup(profile.resources)
            parsed.feed(markup)
            parsed.close()


SITE_STATUS = {
    False: "サイトの計測は停止中です。現在、操作は送信されません。",
    True: "サイトの計測は有効です。許可した場合だけ対象の操作を送ります。",
}
CONSENT = (
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


def consent(enabled=False):
    return CONSENT.format(site_status=SITE_STATUS[enabled])


def complete_markup(reviewed, *, enabled=False):
    return (
        reader_assets(reviewed)
        + consent(enabled)
        + config_script(bind(reviewed, enabled=enabled))
    )


@pytest.mark.parametrize("enabled,state", [(False, "OFF"), (True, "ON")])
def test_exact_reader_assets_config_and_consent_complete_the_opt_in_audit(
    reviewed, enabled, state
):
    profile = bind(reviewed, enabled=enabled)
    parsed = parser(profile)
    parsed.feed(complete_markup(reviewed, enabled=enabled))
    parsed.close()
    assert parsed.reader_collection_state == state
    assert parsed.reader_consent_seen is True
    assert parsed.required == set(profile.resources)


@pytest.mark.parametrize(
    "before,after",
    [
        ('id="raos-reader-consent-deny"', 'id="other-deny"'),
        (
            'id="raos-reader-consent-settings"',
            'id="raos-reader-consent-settings" hidden',
        ),
        ('type="button"', 'type="submit"'),
        ('aria-live="polite"', 'aria-live="assertive"'),
        ('href="/privacy-policy/"', 'href="https://external.example/privacy/"'),
        ("</div>", '<input type="email" name="email"></div>'),
        (
            '<div id="raos-reader-consent-choices">',
            '<form action="/collect" method="post">',
        ),
        ("<h2", '<h2 onclick="collect()"'),
        ("</section>", '<script>fetch("/collect")</script></section>'),
        ("</section>", "<!-- added control --></section>"),
        ("</section>", ""),
    ],
)
def test_reader_consent_is_fixed_complete_balanced_and_never_a_form_exemption(
    reviewed, before, after
):
    markup = (
        reader_assets(reviewed)
        + consent().replace(before, after)
        + config_script(bind(reviewed))
    )
    with pytest.raises(runtime.seo.AuditError):
        parsed = parser(bind(reviewed))
        parsed.feed(markup)
        parsed.close()


@pytest.mark.parametrize("missing", ["assets", "config", "consent"])
def test_absent_reader_surface_cannot_be_reported_as_off(reviewed, missing):
    parts = {
        "assets": reader_assets(reviewed),
        "config": config_script(bind(reviewed)),
        "consent": consent(),
    }
    del parts[missing]
    with pytest.raises(runtime.seo.AuditError):
        parsed = parser(bind(reviewed))
        parsed.feed("".join(parts.values()))
        parsed.close()


@pytest.mark.parametrize("wrapper", ["template", "noscript", "svg"])
def test_reader_config_and_choices_cannot_hide_in_inert_or_foreign_content(
    reviewed, wrapper
):
    with pytest.raises(runtime.seo.AuditError):
        parsed = parser(bind(reviewed))
        parsed.feed(f"<{wrapper}>" + complete_markup(reviewed) + f"</{wrapper}>")
        parsed.close()


def test_duplicate_reader_controls_and_wrong_visible_collector_state_are_rejected(
    reviewed,
):
    for markup in (
        reader_assets(reviewed) + consent() * 2 + config_script(bind(reviewed)),
        reader_assets(reviewed) + consent(True) + config_script(bind(reviewed)),
        complete_markup(reviewed)
        + '<button id="raos-reader-consent-unknown" type="button">Extra</button>',
    ):
        with pytest.raises(runtime.seo.AuditError):
            parsed = parser(bind(reviewed))
            parsed.feed(markup)
            parsed.close()


class PublicResponses:
    def __init__(self, reviewed):
        self.requests = []
        self.responses = {
            PREFIX
            + path
            + "?ver="
            + sha256(reviewed["files"][path]).hexdigest(): response(
                PREFIX + path + "?ver=" + sha256(reviewed["files"][path]).hexdigest(),
                reviewed["files"][path],
                "text/css" if path.endswith(".css") else "text/javascript",
            )
            for path in (
                "assets/reader-measurement.js",
                "assets/reader-measurement.css",
            )
        }

    def get(self, url):
        self.requests.append(("GET", url))
        return self.responses[url]

    def post(self, *args, **kwargs):
        pytest.fail("Declared runtime audit must never submit a collector event")


def response(url, body, mime="text/html"):
    return audit.seo.HttpResponse(
        url, 200, (("Content-Type", mime),), body, "2026-09-06T01:00:00Z"
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_page_verifier_keeps_old_return_shape_and_gets_only_bound_assets(
    reviewed, enabled
):
    profile = bind(reviewed, enabled=enabled)
    transport = PublicResponses(reviewed)
    result = runtime.verify_page(
        response(
            ORIGIN + "/reviewed-article/",
            complete_markup(reviewed, enabled=enabled).encode(),
        ),
        {},
        transport,
        reader_measurement=profile,
    )
    assert result == {
        url: resource.sha256 for url, resource in profile.resources.items()
    }
    assert transport.requests == [("GET", url) for url in sorted(profile.resources)]


@pytest.mark.parametrize("problem", ["digest", "size", "mime", "cookie", "redirect"])
def test_reader_asset_response_cannot_redefine_reviewed_expectations(reviewed, problem):
    from dataclasses import replace

    profile = bind(reviewed)
    transport = PublicResponses(reviewed)
    url = next(url for url in profile.resources if ".js?" in url)
    original = transport.responses[url]
    if problem == "digest":
        changed = replace(original, body=b"x" * len(original.body))
    elif problem == "size":
        changed = replace(original, body=original.body + b" ")
    elif problem == "mime":
        changed = replace(original, headers=(("Content-Type", "text/html"),))
    elif problem == "cookie":
        changed = replace(
            original, headers=original.headers + (("Set-Cookie", "visitor=synthetic"),)
        )
    else:
        changed = replace(original, url="https://external.example/reader.js")
    transport.responses[url] = changed
    with pytest.raises(runtime.seo.AuditError):
        runtime.verify_page(
            response(ORIGIN + "/reviewed-article/", complete_markup(reviewed).encode()),
            {},
            transport,
            reader_measurement=profile,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("policy_sha256", "f" * 64),
        ("contract_sha256", "f" * 64),
        ("revision", "f" * 64),
        ("privacy_source", "changes/other-policy.html"),
        ("approval_required", False),
        ("plugin_slug", "raos-editorial-measurement"),
    ],
)
def test_manifest_policy_and_contract_identity_cannot_disagree_with_plugin_config(
    reviewed, field, value
):
    reviewed["manifest"][field] = value
    with pytest.raises(runtime.seo.AuditError):
        bind(reviewed)


def test_plugin_revision_is_computed_from_exact_files_and_policy(reviewed):
    config = json.loads(reviewed["files"]["config/reader-runtime.v1.json"])
    config["revision"] = "f" * 64
    reviewed["manifest"]["revision"] = config["revision"]
    reviewed["files"]["config/reader-runtime.v1.json"] = encode(config)
    refresh_manifest(reviewed)
    with pytest.raises(runtime.seo.AuditError):
        bind(reviewed)


@pytest.fixture
def prewrite_world(reviewed, monkeypatch):
    from types import SimpleNamespace
    from datetime import datetime, UTC

    transport = PublicResponses(reviewed)
    for slug in ("reviewed-article", "categories", "unselected"):
        url = ORIGIN + "/" + slug + "/"
        transport.responses[url] = response(url, b"<p>Public fixture</p>")
    monkeypatch.setattr(runtime, "trusted_theme_files", lambda *args, **kwargs: {})
    monkeypatch.setattr(runtime, "resources_for_theme", lambda files: {})
    monkeypatch.setattr(
        runtime.seo,
        "load_contract",
        lambda: SimpleNamespace(
            items=[
                SimpleNamespace(url=ORIGIN + "/" + slug + "/")
                for slug in ("reviewed-article", "categories", "unselected")
            ],
        ),
    )
    monkeypatch.setattr(
        runtime.seo, "BoundedHttpsTransport", lambda *args, **kwargs: transport
    )
    snapshot = {
        "schema": "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V2",
        "origin": ORIGIN,
        "publication_profile": "verified-incremental",
        "reader_page_slugs": ["categories"],
        "documents": [
            {
                "slug": "reviewed-article",
                "status": "publish",
                "post_type": "post",
                "block_markup": "<p>Public fixture</p>",
            },
            {
                "slug": "categories",
                "status": "draft",
                "post_type": "page",
                "block_markup": "<p>Bound draft</p>",
            },
        ],
    }

    def verify(candidate=snapshot, profile=None):
        return runtime.verify_before_write(
            current_tree="a" * 64,
            baseline_tree="a" * 64,
            candidate_tree="a" * 64,
            now=datetime(2026, 9, 6, 1, tzinfo=UTC),
            snapshot=candidate,
            reader_measurement=profile,
        )

    return snapshot, transport, verify


def test_before_write_only_reads_baseline_published_snapshot_documents(prewrite_world):
    _snapshot, transport, verify = prewrite_world
    result = verify()
    assert set(result["pages"]) == {ORIGIN + "/reviewed-article/"}
    assert transport.requests == [("GET", ORIGIN + "/reviewed-article/")]
    assert "reader_measurement" not in result


@pytest.mark.parametrize(
    "problem",
    [
        "v1_draft",
        "unknown_schema",
        "undeclared",
        "unregistered",
        "post_draft",
        "private",
        "missing_status",
        "duplicate_declaration",
        "missing_declared_page",
    ],
)
def test_before_write_refuses_unbound_drafts_before_any_public_request(
    prewrite_world, problem
):
    snapshot, transport, verify = prewrite_world
    if problem == "v1_draft":
        snapshot["schema"] = "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1"
        snapshot.pop("reader_page_slugs")
    elif problem == "unknown_schema":
        snapshot["schema"] = "unknown"
    elif problem == "undeclared":
        snapshot["reader_page_slugs"] = []
    elif problem == "unregistered":
        snapshot["reader_page_slugs"] = ["arbitrary-draft"]
        snapshot["documents"][1]["slug"] = "arbitrary-draft"
    elif problem == "post_draft":
        snapshot["documents"][1]["post_type"] = "post"
    elif problem == "private":
        snapshot["documents"][1]["status"] = "private"
    elif problem == "missing_status":
        snapshot["documents"][0].pop("status")
    elif problem == "duplicate_declaration":
        snapshot["reader_page_slugs"] *= 2
    else:
        snapshot["reader_page_slugs"].append("guides")
    with pytest.raises(runtime.seo.AuditError):
        verify()
    assert transport.requests == []


def test_before_write_reader_report_labels_declared_state_and_skips_drafts(
    prewrite_world, reviewed
):
    _snapshot, transport, verify = prewrite_world
    url = ORIGIN + "/reviewed-article/"
    transport.responses[url] = response(url, complete_markup(reviewed).encode())
    result = verify(profile=bind(reviewed))
    assert set(result["pages"]) == {url}
    assert result["reader_measurement"]["collection_state"] == "OFF"
    assert result["reader_measurement"]["state_source"] == "DECLARED_CLIENT_CONFIG"
    assert result["reader_measurement"]["browser_observation"] == "NOT_EXECUTED"
    assert ("GET", ORIGIN + "/categories/") not in transport.requests


THEME_HARNESS = r"""
$input=json_decode(base64_decode($argv[1]),true,512,JSON_THROW_ON_ERROR);
$fixture=sys_get_temp_dir().'/reader-theme-'.bin2hex(random_bytes(8));
mkdir($fixture.'/theme/assets', recursive:true);
define('ABSPATH',$fixture.'/');
define('WP_PLUGIN_DIR',$fixture.'/plugins');
$theme_fixture=$fixture.'/theme';
$root=WP_PLUGIN_DIR.'/raos-reader-measurement';
$maintenance_loaded=false;
$hooks=array();
function get_stylesheet_directory() { return $GLOBALS['theme_fixture']; }
function add_action($hook,$callback,...$args) { $GLOBALS['hooks'][$hook][]=$callback; }
function add_filter(...$args) {}
function add_shortcode(...$args) {}
function raos_reader_measurement_status() { throw new RuntimeException('PROFILE_RECURSION'); }
function raos_reader_measurement_enabled() { throw new RuntimeException('PROFILE_RECURSION'); }
function update_option(...$args) { throw new RuntimeException('PROFILE_WRITE'); }
function wp_remote_request(...$args) { throw new RuntimeException('PROFILE_NETWORK'); }
foreach ($input['files'] as $path=>$raw) {
    if (!is_dir(dirname($root.'/'.$path))) { mkdir(dirname($root.'/'.$path),recursive:true); }
    file_put_contents($root.'/'.$path,base64_decode($raw));
}
$meta=$input['binding'];
$scenario=$input['scenario'];
if ($scenario==='unknown_file') { $meta['plugin_files'][0]['path']='../unreviewed.php'; }
if ($scenario==='duplicate_file') { $meta['plugin_files'][]=$meta['plugin_files'][0]; }
if ($scenario==='old_plugin') { $meta['plugin_slug']='raos-editorial-measurement'; }
$bytes=json_encode($meta,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);
$pin=hash('sha256',$bytes);
if ($scenario==='metadata_drift') { $bytes.=' '; }
file_put_contents($theme_fixture.'/assets/reader-measurement-runtime.v1.json',$bytes);
if ($scenario==='asset_drift') { file_put_contents($root.'/assets/reader-measurement.js','changed'); }
if ($scenario==='maintenance_drift') { file_put_contents($root.'/includes/reader-measurement-maintenance.php','<?php throw new RuntimeException("UNREVIEWED_MAINTENANCE");'); }
if ($scenario==='missing_plugin') { unlink($root.'/raos-reader-measurement.php'); }
if ($scenario==='maintenance_symlink') {
    rename($root.'/includes/reader-measurement-maintenance.php',$fixture.'/outside.php');
    symlink($fixture.'/outside.php',$root.'/includes/reader-measurement-maintenance.php');
}
$source=file_get_contents($argv[2]);
$source=preg_replace("/const KURASHINOSHIRUBE_READER_RUNTIME_METADATA_SHA256 = '[a-f0-9]{64}';/",
    "const KURASHINOSHIRUBE_READER_RUNTIME_METADATA_SHA256 = '".$pin."';",$source);
eval(substr($source,5));
if (!function_exists('kurashinoshirube_reader_runtime_profile')) {
    echo json_encode(array('profile'=>'MISSING')); exit;
}
$profile=kurashinoshirube_reader_runtime_profile();
kurashinoshirube_load_reader_measurement_maintenance();
echo json_encode(array('profile'=>$profile,'maintenance_loaded'=>$maintenance_loaded,
    'cleanup_hook_registered'=>in_array('kurashinoshirube_load_reader_measurement_maintenance',$hooks['after_setup_theme']??array(),true)),JSON_THROW_ON_ERROR);
"""


def run_theme(scenario):
    import os
    from pathlib import Path
    import shutil
    import subprocess

    php = os.environ.get("RAOS_PHP_BIN") or shutil.which("php")
    if not php:
        pytest.skip("PHP CLI unavailable; theme runtime contract not executed")
    files = {
        "README.md": b"Synthetic reviewed package",
        "assets/reader-measurement.css": b"p{color:navy}",
        "assets/reader-measurement.js": b"/* synthetic */",
        "config/reader-allowlist.v1.json": b"{}",
        "config/reader-runtime.v1.json": b"{}",
        "includes/class-reader-contract.php": b"<?php // never execute",
        "includes/class-reader-store.php": b"<?php // never execute",
        "includes/reader-measurement-maintenance.php": b"<?php $GLOBALS['maintenance_loaded']=true;",
        "raos-reader-measurement.php": b"<?php throw new RuntimeException('INACTIVE_BOOTSTRAP_FORBIDDEN');",
    }
    binding = {
        "schema": "RAOS_READER_MEASUREMENT_THEME_BINDING_V1",
        "plugin_slug": "raos-reader-measurement",
        "plugin_version": "1.0.0",
        "manifest_sha256": "a" * 64,
        "policy_sha256": "b" * 64,
        "contract_sha256": "c" * 64,
        "revision": "d" * 64,
        "plugin_files": [
            {"path": path, "size": len(raw), "sha256": sha256(raw).hexdigest()}
            for path, raw in sorted(files.items())
        ],
        "maintenance_file": "includes/reader-measurement-maintenance.php",
        "maintenance_sha256": sha256(
            files["includes/reader-measurement-maintenance.php"]
        ).hexdigest(),
    }
    payload = {
        "scenario": scenario,
        "binding": binding,
        "files": {path: base64.b64encode(raw).decode() for path, raw in files.items()},
    }
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            php,
            "-d",
            "display_errors=1",
            "-r",
            THEME_HARNESS,
            base64.b64encode(encode(payload)).decode(),
            str(
                root
                / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/functions.php"
            ),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "scenario,profile,maintenance",
    [
        ("reviewed", "reader-minimal-v1", True),
        ("asset_drift", "off", True),
        ("missing_plugin", "off", False),
        ("maintenance_drift", "off", False),
        ("metadata_drift", "off", False),
        ("maintenance_symlink", "off", False),
        ("unknown_file", "off", False),
        ("duplicate_file", "off", False),
        ("old_plugin", "off", False),
    ],
)
def test_theme_profile_is_nonrecursive_and_only_pinned_maintenance_can_load(
    scenario, profile, maintenance
):
    assert run_theme(scenario) == {
        "profile": profile,
        "maintenance_loaded": maintenance,
        "cleanup_hook_registered": True,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", []),
        ("schema", {}),
        ("post_type", []),
        ("post_type", {}),
    ],
)
def test_malformed_snapshot_scope_fails_closed_before_network(
    prewrite_world, field, value
):
    snapshot, transport, verify = prewrite_world
    if field == "schema":
        snapshot[field] = value
    else:
        snapshot["documents"][0][field] = value
    with pytest.raises(runtime.seo.AuditError):
        verify()
    assert transport.requests == []


def test_before_write_includes_registered_published_hub_even_outside_core_contract(
    prewrite_world, monkeypatch
):
    from types import SimpleNamespace

    snapshot, transport, verify = prewrite_world
    snapshot["documents"][1]["status"] = "publish"
    monkeypatch.setattr(
        runtime.seo,
        "load_contract",
        lambda: SimpleNamespace(
            items=[SimpleNamespace(url=ORIGIN + "/reviewed-article/")],
        ),
    )
    result = verify()
    assert set(result["pages"]) == {
        ORIGIN + "/reviewed-article/",
        ORIGIN + "/categories/",
    }
    assert set(transport.requests) == {
        ("GET", ORIGIN + "/reviewed-article/"),
        ("GET", ORIGIN + "/categories/"),
    }


@pytest.mark.parametrize("empty_kind", ["empty", "only_draft", "outside_inventory"])
def test_before_write_never_reports_unobserved_empty_public_scope(
    prewrite_world, empty_kind
):
    snapshot, transport, verify = prewrite_world
    if empty_kind == "empty":
        snapshot["schema"] = "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1"
        snapshot.pop("reader_page_slugs")
        snapshot["documents"] = []
    elif empty_kind == "only_draft":
        snapshot["documents"] = snapshot["documents"][1:]
    else:
        snapshot["documents"][0]["slug"] = "arbitrary-public-url"
    with pytest.raises(runtime.seo.AuditError):
        verify()
    assert transport.requests == []


def transport_contract():
    from types import SimpleNamespace

    return SimpleNamespace(
        origin=ORIGIN,
        connect_timeout=1,
        read_timeout=1,
        maximum_bytes=1048576,
        user_agent="synthetic-reader-audit",
    )


def test_real_transport_accepts_only_opt_in_bound_reader_assets_and_uses_get(
    reviewed, monkeypatch
):
    from types import SimpleNamespace

    requests = []
    bodies = PublicResponses(reviewed).responses

    class Connection:
        sock = None

        def __init__(self, host, port, **kwargs):
            assert (host, port) == ("kurashinoshirube.com", 443)

        def request(self, method, path, *, headers):
            requests.append((method, ORIGIN + path))

        def getresponse(self):
            response = bodies[requests[-1][1]]
            return SimpleNamespace(
                status=response.status,
                read=lambda maximum: response.body[:maximum],
                getheaders=lambda: response.headers,
            )

        def close(self):
            pass

    monkeypatch.setattr(runtime.seo.http.client, "HTTPSConnection", Connection)
    profile = bind(reviewed)
    urls = frozenset(profile.resources)
    transport = runtime.seo.BoundedHttpsTransport(
        transport_contract(),
        allowed_resource_urls=urls,
        reader_measurement=profile,
    )
    for url in sorted(urls):
        assert transport.get(url).body_sha256 == profile.resources[url].sha256
    assert requests == [("GET", url) for url in sorted(urls)]
    with pytest.raises(runtime.seo.AuditError):
        runtime.seo.BoundedHttpsTransport(
            transport_contract(), allowed_resource_urls=urls
        )


@pytest.mark.parametrize(
    "value", [{}, {"profile": "reader-minimal-v1"}, True, "reader-minimal-v1"]
)
def test_transport_reader_option_never_accepts_arbitrary_dicts_or_profile_strings(
    value,
):
    with pytest.raises(runtime.seo.AuditError):
        runtime.seo.BoundedHttpsTransport(
            transport_contract(), reader_measurement=value
        )


@pytest.mark.parametrize(
    "replacement",
    [
        PREFIX + "assets/other.js?ver=" + "a" * 64,
        ORIGIN
        + "/wp-content/plugins/raos-editorial-measurement/assets/reader-measurement.js?ver="
        + "a" * 64,
        "https://external.example/reader-measurement.js?ver=" + "a" * 64,
        PREFIX + "assets/reader-measurement.js?ver=" + "a" * 20,
        PREFIX + "assets/reader-measurement.js?ver=" + "a" * 64 + "&extra=1",
        PREFIX + "assets/reader-measurement.js",
        ENDPOINT,
    ],
)
def test_transport_reader_option_does_not_grant_plugin_wildcards_or_collector_get(
    reviewed, replacement
):
    profile = bind(reviewed)
    with pytest.raises(runtime.seo.AuditError):
        runtime.seo.BoundedHttpsTransport(
            transport_contract(),
            allowed_resource_urls=frozenset(profile.resources) | {replacement},
            reader_measurement=profile,
        )


@pytest.mark.parametrize(
    "problem",
    ["url_hash_mismatch", "other_asset", "extra_asset", "profile", "wrong_kind"],
)
def test_transport_validates_fixed_profile_asset_shape_even_on_typed_runtime(
    reviewed, problem
):
    from dataclasses import replace

    profile = bind(reviewed)
    resources = dict(profile.resources)
    js = next(url for url in resources if ".js?" in url)
    row = resources.pop(js)
    if problem == "url_hash_mismatch":
        resources[js] = replace(row, sha256="f" * 64)
    elif problem == "other_asset":
        resources[js.replace("reader-measurement.js", "arbitrary.js")] = row
    elif problem == "extra_asset":
        resources[js] = row
        resources[js.replace("reader-measurement.js", "arbitrary.js")] = row
    elif problem == "profile":
        resources[js] = row
        profile = replace(profile, profile="unknown")
    else:
        resources[js] = replace(row, kind="module")
    with pytest.raises(runtime.seo.AuditError):
        runtime.seo.BoundedHttpsTransport(
            transport_contract(),
            allowed_resource_urls=frozenset(resources),
            reader_measurement=replace(profile, resources=resources),
        )


def test_before_write_uses_real_transport_with_bound_reader_assets(
    prewrite_world, reviewed, monkeypatch
):
    _snapshot, responses, verify = prewrite_world
    contract = transport_contract()
    contract.items = runtime.seo.load_contract().items
    monkeypatch.setattr(runtime.seo, "load_contract", lambda: contract)
    monkeypatch.setattr(runtime.seo, "BoundedHttpsTransport", BOUNDED_TRANSPORT)
    monkeypatch.setattr(BOUNDED_TRANSPORT, "get", lambda self, url: responses.get(url))
    profile = bind(reviewed)
    url = ORIGIN + "/reviewed-article/"
    responses.responses[url] = response(url, complete_markup(reviewed).encode())
    result = verify(profile=profile)
    assert result["reader_measurement"]["collection_state"] == "OFF"
    assert responses.requests == [("GET", url)] + [
        ("GET", asset) for asset in sorted(profile.resources)
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile", "off"),
        ("profile", "reader-minimal-v2"),
        ("expected_collection_enabled", None),
        ("expected_collection_enabled", 0),
    ],
)
def test_pure_parser_requires_exact_opt_in_profile_and_literal_expected_state(
    reviewed, field, value
):
    from dataclasses import replace

    profile = replace(bind(reviewed), **{field: value})
    with pytest.raises(runtime.seo.AuditError):
        runtime.RuntimeMarkup(
            {}, reader_measurement=profile, page_url=ORIGIN + "/reviewed-article/"
        )
