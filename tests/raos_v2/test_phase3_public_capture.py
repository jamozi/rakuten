"""Bounded, read-only Phase 3 public observation contract."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from scripts import validate_raos_v2_successor as validator


SAFE_OUTPUT = Path(
    "changes/raos-v2/recorded-inputs/phase3/one-url-public-observation.v1.json"
)


def _retime_capture(
    capture: dict[str, object], *, captured_at: datetime, observed_at: datetime
) -> dict[str, object]:
    capture["captured_at"] = captured_at.isoformat()
    observation = capture["observation"]
    assert isinstance(observation, dict)
    observation["observed_at"] = observed_at.isoformat()
    return capture


def _capture_html(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
    *,
    page_headers: dict[str, str] | None = None,
) -> dict[str, object]:
    plugin_css = (
        validator.ROOT
        / validator.PHASE3_PLUGIN_SOURCE_ROOT
        / "assets/decision-support.css"
    ).read_bytes()
    monkeypatch.setattr(
        validator,
        "_sitemap_urls",
        lambda *, membership_target=None: ({validator.PHASE3_PUBLIC_URL}, []),
    )
    monkeypatch.setattr(
        validator,
        "_fetch",
        lambda url: (
            (
                200,
                plugin_css,
                {"Content-Type": "text/css; charset=utf-8"},
                [],
            )
            if url == validator.PHASE3_PLUGIN_CSS_URL
            else (
                200,
                b"User-agent: *\nAllow: /\n",
                {"Content-Type": "text/plain; charset=utf-8"},
                [],
            )
            if url == validator.PHASE3_ROBOTS_URL
            else (
                200,
                body,
                page_headers or {"Content-Type": "text/html; charset=utf-8"},
                [],
            )
        ),
    )
    monkeypatch.setattr(
        validator, "_write_new_phase3_capture", lambda _output, _payload: None
    )
    return validator.capture_phase3_public(
        public_read_only=True,
        output=SAFE_OUTPUT,
    )


def _preaction_public_capture(
    monkeypatch: pytest.MonkeyPatch, *, base_time: datetime
) -> dict[str, object]:
    body = (
        '<!doctype html><html><head><link rel="canonical" '
        f'href="{validator.PHASE3_PUBLIC_URL}">'
        "<title>Current published article</title>"
        '<meta name="description" content="Current description">'
        '<meta name="robots" content="index,follow">'
        '<link rel="stylesheet" href="/wp-content/themes/current/theme.css">'
        "<style>.theme{display:block}</style>"
        '<script src="/wp-includes/js/theme.js"></script>'
        "<script>window.themeReady=true</script>"
        '</head><body><img src="/wp-content/themes/current/logo.png" alt="">'
        "<h1>Current published article</h1><p>Current body</p></body></html>"
    ).encode("utf-8")
    return _retime_capture(
        _capture_html(monkeypatch, body),
        captured_at=base_time + timedelta(seconds=1),
        observed_at=base_time + timedelta(seconds=2),
    )


def _sealed_package_record(
    preaction_capture: dict[str, object], *, base_time: datetime
) -> dict[str, object]:
    candidate = json.loads(
        (
            validator.ROOT
            / "changes/raos-v2/phase-3/generated/review-candidate.v1.json"
        ).read_text(encoding="utf-8")
    )
    assert isinstance(candidate, dict)
    phase2 = candidate["phase2_candidate"]
    assert isinstance(phase2, dict)
    update = candidate["update_payload"]
    assert isinstance(update, dict)
    fields = update["fields"]
    assert isinstance(fields, dict)
    preaction_observation = preaction_capture["observation"]
    assert isinstance(preaction_observation, dict)
    binding = {
        "schema": "RAOS_V2_PHASE3_PREACTION_BINDING_V1",
        "version": "1.0.0",
        "status": "VERIFIED_PREACTION",
        "provenance": "PUBLIC_READ_ONLY_CAPTURE_AND_OWNER_WORDPRESS_EXPORT",
        "captured_at": (base_time + timedelta(seconds=3)).isoformat(),
        "target": {
            "origin": validator.ORIGIN,
            "route": validator.PHASE3_PUBLIC_PATH,
            "kind": "EXISTING_POST",
            "post_id": 123,
            "exact_match_count": 1,
        },
        "current_public_body_sha256": preaction_observation["body_sha256"],
        "public_capture_sha256": validator._semantic_digest(preaction_capture),
        "wordpress_export_sha256": "a" * 64,
        "wordpress_export_bytes": 4096,
    }
    binding_digest = validator._semantic_digest(binding)
    target = update["target"]
    assert isinstance(target, dict)
    target["expected_public_body_sha256"] = preaction_observation["body_sha256"]
    update["preaction"] = {
        "status": "VERIFIED_PREACTION",
        "binding_digest": binding_digest,
        "binding": binding,
    }
    structured = validator._phase3_expected_structured_data(fields)
    update["structured_data_expectation"] = structured
    candidate["preaction_status"] = "VERIFIED_PREACTION"
    candidate["preaction_binding_digest"] = binding_digest
    candidate["structured_data_expectation_sha256"] = structured["json_ld_sha256"]
    candidate["payload_digest"] = validator._semantic_digest(update)
    reviewed_at = base_time + timedelta(seconds=4)
    receipt = {
        "schema": "RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_V1",
        "version": "1.0.0",
        "reviewer_id": "TEST-OWNER-REVIEW",
        "reviewed_at": reviewed_at.isoformat(),
        "review_version": "P3-TEST-V1",
        "correction_count": 0,
        "accepted": True,
        "synthetic": False,
        "candidate_digest": candidate["candidate_digest"],
        "payload_digest": candidate["payload_digest"],
        "target_route": validator.PHASE3_PUBLIC_PATH,
    }
    semantic = {
        "schema": "RAOS_V2_PHASE3_PUBLICATION_PACKAGE_V1",
        "version": "1.0.0",
        "state": "PACKAGE_SEALED",
        "review_candidate": candidate,
        "human_review_receipt": receipt,
        "structured_data_expectation_sha256": structured["json_ld_sha256"],
        "capabilities": {"network": False, "wordpress_write": False, "publish": False},
    }
    return {**semantic, "package_digest": validator._semantic_digest(semantic)}


def _successful_public_capture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    package: dict[str, object],
    base_time: datetime,
) -> dict[str, object]:
    candidate = package["review_candidate"]
    assert isinstance(candidate, dict)
    update = candidate["update_payload"]
    assert isinstance(update, dict)
    fields = update["fields"]
    assert isinstance(fields, dict)
    title = str(fields["post_title"])
    description = str(fields["meta_description"])
    structured_expectation = update["structured_data_expectation"]
    assert isinstance(structured_expectation, dict)
    documents = structured_expectation["documents"]
    assert isinstance(documents, list) and len(documents) == 1
    structured_data = documents[0]
    body = (
        '<!doctype html><html><head><link rel="canonical" '
        f'href="{validator.PHASE3_PUBLIC_URL}">'
        f"<title>{title}</title>"
        f'<meta name="description" content="{description}">'
        '<meta name="robots" content="index,follow">'
        '<link rel="stylesheet" href="/wp-content/themes/current/theme.css">'
        '<link rel="stylesheet" href="/wp-content/plugins/'
        'raos-v2-decision-support/assets/decision-support.css">'
        "<style>.theme{display:block}</style>"
        '<script src="/wp-includes/js/theme.js"></script>'
        "<script>window.themeReady=true</script>"
        '<script type="application/ld+json">'
        f"{json.dumps(structured_data, ensure_ascii=False)}"
        "</script></head><body>"
        '<img src="/wp-content/themes/current/logo.png" alt="">'
        f"<h1>{title}</h1>"
        '<div data-raos-v2-post-content-envelope="RAOS_V2_A05_ENVELOPE_V1">'
        f"{fields['post_content']}"
        "</div>"
        "</body></html>"
    ).encode("utf-8")

    return _retime_capture(
        _capture_html(monkeypatch, body),
        captured_at=base_time + timedelta(seconds=6),
        observed_at=base_time + timedelta(seconds=7),
    )


def _post_action_export_binding(
    *, package: dict[str, object], capture: dict[str, object], base_time: datetime
) -> dict[str, object]:
    candidate = package["review_candidate"]
    assert isinstance(candidate, dict)
    update = candidate["update_payload"]
    assert isinstance(update, dict)
    fields = update["fields"]
    preaction = update["preaction"]
    assert isinstance(fields, dict) and isinstance(preaction, dict)
    observation = capture["observation"]
    assert isinstance(observation, dict)
    return {
        "schema": "RAOS_V2_WORDPRESS_EXPORT_BINDING_V2",
        "version": "2.0.0",
        "export_role": "POST_ACTION_OWNER_EXPORT",
        "target": {
            "origin": validator.ORIGIN,
            "route": validator.PHASE3_PUBLIC_PATH,
            "kind": "EXISTING_POST",
            "post_id": 123,
            "exact_match_count": 1,
        },
        "captured_at": (base_time + timedelta(seconds=5)).isoformat(),
        "field_hashes": {
            name: validator._semantic_digest({"field": name, "value": value})
            for name, value in sorted(fields.items())
        },
        "public_body_sha256": observation["body_sha256"],
        "preaction_binding_sha256": preaction["binding_digest"],
        "export_sha256": "b" * 64,
        "export_bytes": 8192,
        "restore_artifact_sha256": "c" * 64,
        "theme_artifact_sha256": "d" * 64,
        "seo_state_sha256": "e" * 64,
        "redirect_map_sha256": "f" * 64,
        "sitemap_state_sha256": "1" * 64,
        "raw_export_location": "OWNER_STORAGE_ONLY_NOT_GIT",
        "status": "VERIFIED_HUMAN_EXPORT",
    }


def _verification_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    dict[str, object], dict[str, object], dict[str, object], dict[str, object], datetime
]:
    generated = json.loads(
        (
            validator.ROOT
            / "changes/raos-v2/phase-3/generated/review-candidate.v1.json"
        ).read_text(encoding="utf-8")
    )
    phase2 = generated["phase2_candidate"]
    assert isinstance(phase2, dict)
    base_time = datetime.fromisoformat(str(phase2["created_at"]))
    preaction = _preaction_public_capture(monkeypatch, base_time=base_time)
    package = _sealed_package_record(preaction, base_time=base_time)
    capture = _successful_public_capture(
        monkeypatch, package=package, base_time=base_time
    )
    export = _post_action_export_binding(
        package=package, capture=capture, base_time=base_time
    )
    evaluated_at = base_time + timedelta(seconds=8)
    return preaction, capture, package, export, evaluated_at


def _derive(
    inputs: tuple[
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, object],
        datetime,
    ],
) -> dict[str, object]:
    preaction, capture, package, export, evaluated_at = inputs
    return validator.derive_phase3_public_verification_receipt(
        preaction_capture=preaction,
        capture=capture,
        sealed_package=package,
        post_action_export_binding=export,
        evaluated_at=evaluated_at,
        rollback_invoked=False,
    )


def test_offline_default_records_not_executed_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[tuple[Path, bytes]] = []

    def deny_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("network must remain disabled without the explicit flag")

    monkeypatch.setattr(validator, "_fetch", deny_network)
    monkeypatch.setattr(validator, "_sitemap_urls", deny_network)
    monkeypatch.setattr(
        validator,
        "_write_new_phase3_capture",
        lambda output, payload: written.append((output, payload)),
    )

    document = validator.capture_phase3_public(
        public_read_only=False,
        output=SAFE_OUTPUT,
    )

    assert document["public_observation_status"] == "NOT_EXECUTED"
    assert document["observation"] is None
    assert document["supporting_resources"]["sitemaps"] == []
    assert document["external_write_actions"] == "NOT_EXECUTED"
    assert document["phase0_baseline_write"] == "PROHIBITED"
    assert written and written[0][0] == SAFE_OUTPUT
    assert json.loads(written[0][1])["public_observation_status"] == "NOT_EXECUTED"


def test_explicit_capture_is_fixed_to_one_page_and_discards_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = (
        b'<!doctype html><html><head><link rel="canonical" '
        b'href="https://kurashinoshirube.com/carry-on-suitcase-comparison/">'
        b'<meta name="robots" content="index,follow"></head>'
        b"<body><h1>Carry-on <span>suitcase comparison</span></h1></body></html>"
    )
    calls: list[str] = []
    written: list[bytes] = []

    def fake_sitemaps(
        *, membership_target: str | None = None
    ) -> tuple[set[str], list[dict[str, object]]]:
        assert membership_target == validator.PHASE3_PUBLIC_URL
        return {validator.PHASE3_PUBLIC_URL}, [
            {
                "url": f"{validator.ORIGIN}/sitemap_index.xml",
                "status": 200,
                "sha256": "a" * 64,
                "redirect_chain": [],
            }
        ]

    def fake_fetch(
        url: str,
    ) -> tuple[int, bytes, dict[str, str], list[dict[str, object]]]:
        calls.append(url)
        if url == validator.PHASE3_ROBOTS_URL:
            return (
                200,
                b"User-agent: *\nAllow: /\n",
                {"content-type": "text/plain; charset=utf-8"},
                [],
            )
        return 200, body, {"content-type": "text/html; charset=utf-8"}, []

    monkeypatch.setattr(validator, "_sitemap_urls", fake_sitemaps)
    monkeypatch.setattr(validator, "_fetch", fake_fetch)
    monkeypatch.setattr(
        validator,
        "_write_new_phase3_capture",
        lambda _output, payload: written.append(payload),
    )

    document = validator.capture_phase3_public(
        public_read_only=True,
        output=SAFE_OUTPUT,
    )

    assert calls == [validator.PHASE3_PUBLIC_URL, validator.PHASE3_ROBOTS_URL]
    assert document["target_url"] == validator.PHASE3_PUBLIC_URL
    assert document["public_observation_status"] == "PUBLIC_READ_ONLY"
    observation = document["observation"]
    assert isinstance(observation, dict)
    assert observation == {
        "url": validator.PHASE3_PUBLIC_URL,
        "path": validator.PHASE3_PUBLIC_PATH,
        "status": 200,
        "redirect_chain": [],
        "canonical": validator.PHASE3_PUBLIC_URL,
        "canonical_tag_count": 1,
        "head_tag_count": 1,
        "metadata_location_violation_count": 0,
        "title": "UNAVAILABLE",
        "title_tag_count": 0,
        "meta_description": "UNAVAILABLE",
        "meta_description_tag_count": 0,
        "robots": "index,follow",
        "robots_meta": "index,follow",
        "robots_http": "UNAVAILABLE",
        "robots_http_indexability_safe": True,
        "content_type_media_type": "text/html",
        "refresh_http_present": False,
        "link_http_sha256": "UNAVAILABLE",
        "robots_tag_count": 1,
        "crawler_robots_tag_count": 0,
        "crawler_robots_indexability_safe": True,
        "h1": "Carry-on suitcase comparison",
        "h1_count": 1,
        "sitemap_membership": True,
        "package_marker_count": 0,
        "package_marker_attribute_count": 0,
        "post_content_envelope_count": 0,
        "post_content_envelope_attribute_count": 0,
        "blocked_post_content_envelope_count": 0,
        "post_content_envelope_marker_child_count": 0,
        "post_content_envelope_valid": False,
        "post_content_marker_subtree_count": 0,
        "post_content_semantic_sha256": "UNAVAILABLE",
        "disclosure_marker_count": 0,
        "cta_state_count": 0,
        "blocked_cta_count": 0,
        "affiliate_url_count": 0,
        "ambiguous_attribute_count": 0,
        "image_count": 0,
        "inline_executable_script_count": 0,
        "external_script_count": 0,
        "resource_inventory": {
            "script_resource_sha256": [],
            "image_resource_sha256": [],
            "stylesheet_resource_sha256": [],
            "active_resource_sha256": [],
            "inline_executable_script_sha256": [],
            "inline_style_sha256": [],
            "executable_attribute_sha256": [],
            "unsafe_resource_count": 0,
        },
        "json_ld_script_count": 0,
        "json_ld_invalid_count": 0,
        "json_ld_sha256": "UNAVAILABLE",
        "json_ld_types": [],
        "json_ld_visible_content_match": False,
        "body_sha256": validator.sha256(body),
        "body_bytes": len(body),
        "body_storage": "DISCARDED_AFTER_HASH",
        "observed_at": observation["observed_at"],
    }
    assert str(observation["observed_at"]).endswith("+09:00")
    serialized = written[0]
    assert body not in serialized
    assert validator.sha256(body).encode("ascii") in serialized
    policy = document["request_policy"]
    assert policy == {
        "target_page_count": 1,
        "maximum_page_and_asset_requests": 3,
        "same_origin_only": True,
        "https_only": True,
        "credentials": "NOT_USED",
        "cookies": "NOT_USED",
        "query_strings": "REJECTED",
        "environment_proxies": "DISABLED",
        "maximum_redirects_per_request": 1,
    }


def test_capture_does_not_sniff_html_and_binds_navigation_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _capture_html(
        monkeypatch,
        b"<html><head><title>Must not parse</title></head><body></body></html>",
        page_headers={
            "Content-Type": "text/plain; charset=utf-8",
            "Refresh": "0; url=https://a.r10.to/unsafe",
            "Link": "</assets/x.js>; rel=preload; as=script",
        },
    )
    observation = capture["observation"]
    assert isinstance(observation, dict)
    assert observation["content_type_media_type"] == "text/plain"
    assert observation["refresh_http_present"] is True
    assert observation["link_http_sha256"] != "UNAVAILABLE"
    assert observation["head_tag_count"] == 0


def test_v2_public_receipt_is_strictly_derived_from_capture_and_sealed_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _verification_inputs(monkeypatch)
    preaction, capture, package, export, _evaluated_at = inputs
    receipt = _derive(inputs)
    schema = json.loads(
        (
            validator.ROOT
            / "contracts/raos-v2/v2/public-verification-receipt.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(receipt)
    observation = capture["observation"]
    assert isinstance(observation, dict)
    assert receipt["capture_sha256"] == validator._semantic_digest(capture)
    assert receipt["package_digest"] == package["package_digest"]
    assert receipt["preaction_capture_sha256"] == validator._semantic_digest(preaction)
    assert receipt["post_action_export_binding_sha256"] == (
        validator._semantic_digest(export)
    )
    assert receipt["body_sha256"] == observation["body_sha256"]
    assert receipt["package_marker_count"] == 1
    assert receipt["post_content_envelope"] == validator.PHASE3_CONTENT_ENVELOPE
    assert receipt["post_content_envelope_valid"] is True
    assert receipt["disclosure_marker_present"] is True
    assert receipt["blocked_cta_count"] == 3
    assert receipt["affiliate_url_count"] == 0
    assert receipt["resource_change_status"] == (
        "NO_UNAPPROVED_NEW_TRACKED_RESOURCE"
    )
    assert receipt["plugin_artifact_status"] == (
        "LOCAL_SOURCE_BOUND_AND_PUBLIC_CSS_MATCHED"
    )
    assert receipt["public_browser_verification_status"] == (
        "SEPARATE_RECEIPT_REQUIRED"
    )
    assert receipt["phase_exit_eligible"] is False
    assert receipt["rollback_invoked"] is False
    assert receipt["robots_txt_target_allowed_for_googlebot"] is True
    assert receipt["indexability_evidence_scope"] == (
        "HEAD_META_HTTP_SITEMAP_AND_ROBOTS_TXT"
    )


@pytest.mark.parametrize(
    ("payload", "status", "allowed"),
    [
        (b"User-agent: *\nDisallow: /carry-on-suitcase-comparison/\n", 200, False),
        (
            b"User-agent: *\nDisallow: /\nAllow: /carry-on-suitcase-comparison/\n",
            200,
            True,
        ),
        (
            b"User-agent: *\nDisallow: /\nUser-agent: Googlebot\nAllow: /\n",
            200,
            True,
        ),
        (
            b"User-agent: *\nAllow: /\nUser-agent: Googlebot\nDisallow: /carry-on-*\n",
            200,
            False,
        ),
        (
            b"User-agent: Googlebot\n"
            b"Disallow: /carry%2Don%2Dsuitcase%2Dcomparison/\n",
            200,
            False,
        ),
        (
            b"User-agent: *\nDisallow: /\n"
            b"Allow: /carry-on-suitcase-comparison%2F\n",
            200,
            False,
        ),
        (
            b"User-agent: *\nAllow: /\n"
            b"User-agent: googlebot/1.2\n"
            b"Disallow: /carry-on-suitcase-comparison/\n",
            200,
            False,
        ),
        (
            b"User-agent: *\n"
            b"Allow: /carry-on-suitcase-comparison/\n"
            b"Disallow: /*carry-on-suitcase-comparison/\n",
            200,
            False,
        ),
        (b"", 404, True),
        (b"", 503, False),
        (b"\xff", 200, False),
    ],
)
def test_robots_txt_target_evaluation_is_fail_closed(
    payload: bytes, status: int, allowed: bool
) -> None:
    assert validator._phase3_robots_target_allowed(payload, status=status) is allowed


def test_robots_txt_ignores_rules_after_google_processing_limit() -> None:
    prefix = b"User-agent: *\nDisallow: /\n#"
    padding = b"x" * validator.PHASE3_ROBOTS_MAX_BYTES
    late_allow = b"\nAllow: /carry-on-suitcase-comparison/\n"
    assert (
        validator._phase3_robots_target_allowed(
            prefix + padding + late_allow,
            status=200,
        )
        is False
    )


def test_public_receipt_rejects_robots_txt_disallow_or_unbound_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preaction, capture, package, export, evaluated_at = _verification_inputs(
        monkeypatch
    )
    resources = capture["supporting_resources"]
    assert isinstance(resources, dict)
    robots = resources["robots_txt"]
    assert isinstance(robots, dict)
    robots["target_allowed_for_googlebot"] = False
    with pytest.raises(
        validator.ValidationFailure,
        match="RAOS_V2_PUBLIC_VERIFICATION_ROBOTS_INVALID",
    ):
        validator.derive_phase3_public_verification_receipt(
            preaction_capture=preaction,
            capture=capture,
            sealed_package=package,
            post_action_export_binding=export,
            evaluated_at=evaluated_at,
            rollback_invoked=False,
        )


def test_public_receipt_requires_exact_public_plugin_stylesheet_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _verification_inputs(monkeypatch)
    preaction, capture, package, export, evaluated_at = inputs
    resources = capture["supporting_resources"]
    assert isinstance(resources, dict)
    evidence = resources["plugin_stylesheet"]
    assert isinstance(evidence, dict)
    evidence["sha256"] = "0" * 64

    with pytest.raises(
        validator.ValidationFailure,
        match="RAOS_V2_PUBLIC_VERIFICATION_PLUGIN_STYLESHEET_INVALID",
    ):
        validator.derive_phase3_public_verification_receipt(
            preaction_capture=preaction,
            capture=capture,
            sealed_package=package,
            post_action_export_binding=export,
            evaluated_at=evaluated_at,
            rollback_invoked=False,
        )


def test_public_receipt_requires_plugin_stylesheet_to_be_new_and_version_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preaction, capture, package, export, evaluated_at = _verification_inputs(
        monkeypatch
    )
    observation = capture["observation"]
    assert isinstance(observation, dict)
    inventory = observation["resource_inventory"]
    assert isinstance(inventory, dict)
    stylesheets = inventory["stylesheet_resource_sha256"]
    assert isinstance(stylesheets, list)
    expected = validator._sanitized_resource_ref_sha256(
        validator.PHASE3_PLUGIN_CSS_RESOURCE_URL
    )
    assert isinstance(expected, str)
    stylesheets.remove(expected)
    resources = capture["supporting_resources"]
    assert isinstance(resources, dict)
    resources["plugin_stylesheet"] = {"status": "NOT_OBSERVED"}

    with pytest.raises(
        validator.ValidationFailure,
        match="RAOS_V2_PUBLIC_VERIFICATION_PLUGIN_STYLESHEET_INVALID",
    ):
        validator.derive_phase3_public_verification_receipt(
            preaction_capture=preaction,
            capture=capture,
            sealed_package=package,
            post_action_export_binding=export,
            evaluated_at=evaluated_at,
            rollback_invoked=False,
        )

    assert validator._sanitized_resource_ref_sha256(
        validator.PHASE3_PLUGIN_CSS_URL + "?ver=0.1.1"
    ) != validator._sanitized_resource_ref_sha256(
        validator.PHASE3_PLUGIN_CSS_RESOURCE_URL
    )


@pytest.mark.parametrize(
    "html",
    [
        '<div data-raos-v2-package-marker="RAOS_V2_A05_POST_CONTENT_V1"></div>',
        (
            '<div data-raos-v2-post-content-envelope="RAOS_V2_A05_ENVELOPE_V1">'
            '<div data-raos-v2-package-marker="RAOS_V2_A05_POST_CONTENT_V1"></div>'
            "<p>unsealed sibling</p></div>"
        ),
        (
            '<div data-raos-v2-post-content-envelope="RAOS_V2_A05_ENVELOPE_V1">'
            '<div data-raos-v2-package-marker="RAOS_V2_A05_POST_CONTENT_V1">'
            "<span></div></span></div>"
        ),
    ],
)
def test_content_envelope_rejects_missing_sibling_or_mismatched_markup(
    html: str,
) -> None:
    summary = validator._phase3_content_envelope_summary(html)
    assert summary["post_content_envelope_valid"] is False


def test_active_navigation_affiliate_and_duplicate_attributes_fail_closed() -> None:
    parser = validator._MetadataParser()
    parser.feed(
        '<base href="https://a.r10.to/">'
        '<meta http-equiv="refresh" content="0;url=https://a.r10.to/redirect">'
        '<link rel="modulepreload" href="/wp-content/theme/module.js">'
        '<a href="/policy/" href="https://a.r10.to/affiliate">policy</a>'
        '<a href="https://a.r10.to/direct">affiliate</a>'
    )
    inventory = parser.resource_inventory()
    assert inventory["unsafe_resource_count"] == 2
    assert len(inventory["active_resource_sha256"]) == 1
    assert parser.ambiguous_attribute_count == 1
    assert parser.affiliate_url_count == 1


def test_seo_metadata_must_be_inside_exactly_one_head() -> None:
    parser = validator._MetadataParser()
    parser.feed(
        "<html><body><title>Body title</title>"
        '<link rel="canonical" href="https://kurashinoshirube.com/">'
        '<meta name="robots" content="index,follow">'
        '<meta name="description" content="Body description"></body></html>'
    )
    assert parser.head_tag_count == 0
    assert parser.metadata_location_violation_count == 4

    parser = validator._MetadataParser()
    parser.feed(
        "<html><head><div>HTML5 closes head here</div>"
        "<title>Not head metadata</title>"
        '<link rel="canonical" href="https://kurashinoshirube.com/">'
        '<meta name="robots" content="index,follow">'
        '<meta name="description" content="Not head metadata"></html>'
    )
    assert parser.head_tag_count == 1
    assert parser.metadata_location_violation_count == 5


@pytest.mark.parametrize("container", ["template", "noscript"])
def test_template_or_noscript_metadata_is_not_document_head_metadata(
    container: str,
) -> None:
    parser = validator._MetadataParser()
    parser.feed(
        f"<html><head><{container}>"
        "<title>Hidden title</title>"
        '<link rel="canonical" href="https://kurashinoshirube.com/">'
        '<meta name="robots" content="index,follow">'
        '<meta name="description" content="Hidden description">'
        f"</{container}></head><body><h1>Visible</h1></body></html>"
    )
    assert parser.head_tag_count == 1
    assert parser.metadata_location_violation_count == 4


def test_self_closing_template_keeps_following_metadata_inert_like_chromium() -> None:
    parser = validator._MetadataParser()
    parser.feed(
        '<html><head><template/><title>Hidden title</title>'
        '<link rel="canonical" href="https://kurashinoshirube.com/">'
        '<meta name="robots" content="index,follow">'
        '<meta name="description" content="Hidden description">'
        '</head><body><h1>Hidden heading</h1></body></html>'
    )
    assert parser.head_tag_count == 1
    assert parser.title_tag_count == 0
    assert parser.canonical_tag_count == 0
    assert parser.h1_count == 0
    assert parser.metadata_location_violation_count >= 4


def test_inert_body_template_cannot_supply_public_content_markers() -> None:
    parser = validator._MetadataParser()
    parser.feed(
        '<html><head><title>Visible title</title></head><body><template/>'
        f'<div data-raos-v2-post-content-envelope="{validator.PHASE3_CONTENT_ENVELOPE}">'
        f'<main data-raos-v2-package-marker="{validator.PHASE3_PACKAGE_MARKER}">'
        '<h1>Hidden heading</h1><span data-raos-v2-cta-state="BLOCKED">x</span>'
        '</main></div></body></html>'
    )
    assert parser.package_marker_count == 0
    assert parser.post_content_envelope_count == 0
    assert parser.cta_state_count == 0
    assert parser.h1_count == 0
    assert parser.metadata_location_violation_count >= 3


def test_mismatched_inert_container_close_is_fail_closed() -> None:
    parser = validator._MetadataParser()
    parser.feed('<html><head><template></noscript><title>Hidden</title></head></html>')
    assert parser.title_tag_count == 0
    assert parser.metadata_location_violation_count >= 2


def test_crawler_specific_meta_noindex_is_not_hidden_by_general_robots() -> None:
    capture_parser = validator._MetadataParser()
    capture_parser.feed(
        '<html><head><meta name="robots" content="index,follow">'
        '<meta name="googlebot" content="noindex">'
        '<meta name="googlebot-news" content="nofollow"></head></html>'
    )
    values = [
        validator._normalize_robots_directives(value)
        for value in capture_parser.crawler_robots_values
    ]
    assert len(values) == 2
    assert all(validator._robots_indexability_safe(value) is False for value in values)


@pytest.mark.parametrize(
    "directives",
    [
        "googlebot:noindex",
        "googlebot-news:nofollow",
        "bingbot:none",
        "index,googlebot:noindex",
        "unavailable_after:2026-08-29T00:00:00Z",
        "googlebot:unavailable_after:2026-08-29T00:00:00Z",
    ],
)
def test_agent_scoped_x_robots_directives_are_not_indexability_safe(
    directives: str,
) -> None:
    normalized = validator._normalize_robots_directives(directives)
    assert validator._robots_indexability_safe(normalized) is False


@pytest.mark.parametrize(
    "href",
    [
        "https://%61.r10.to/x",
        "https://a%2er10%2eto/x",
        "https://ａ．r10.to/x",
        "https://a.r10.to./x",
        "javascript:alert(1)",
        "https://a.r10.to\\@example.com/x",
    ],
)
def test_browser_ambiguous_or_executable_navigation_is_unsafe(href: str) -> None:
    parser = validator._MetadataParser()
    parser.feed(f'<a href="{href}">unsafe</a>')
    assert parser.resource_inventory()["unsafe_resource_count"] == 1


def test_area_affiliate_and_anchor_tracking_attributes_fail_closed() -> None:
    parser = validator._MetadataParser()
    parser.feed(
        '<map><area href="https://a.r10.to/direct"></map>'
        '<a href="/safe/" ping="https://tracker.invalid/ping" '
        'attributionsrc="https://tracker.invalid/register">safe text</a>'
    )
    assert parser.affiliate_url_count == 1
    assert parser.resource_inventory()["unsafe_resource_count"] == 2


def test_input_and_svg_resources_are_inventoried() -> None:
    parser = validator._MetadataParser()
    parser.feed(
        '<input type="image" src="/images/submit.png">'
        '<svg><image href="/images/vector.svg"></image>'
        '<use href="/sprites/icons.svg#check"></use></svg>'
    )
    inventory = parser.resource_inventory()
    assert parser.image_count == 2
    assert len(inventory["image_resource_sha256"]) == 2
    assert len(inventory["active_resource_sha256"]) == 1
    assert inventory["unsafe_resource_count"] == 0


def test_link_with_multiple_active_relations_is_inventoried_in_each_category() -> None:
    parser = validator._MetadataParser()
    parser.feed('<link rel="stylesheet modulepreload" href="/assets/app.css">')
    inventory = parser.resource_inventory()
    assert len(inventory["stylesheet_resource_sha256"]) == 1
    assert len(inventory["active_resource_sha256"]) == 1


def test_icon_and_svg_fetches_are_inventoried() -> None:
    parser = validator._MetadataParser()
    parser.feed(
        '<link rel="icon" href="/favicon-new.svg">'
        '<svg><feImage href="/images/filter.png"></feImage>'
        '<script href="/scripts/vector.js"></script></svg>'
    )
    inventory = parser.resource_inventory()
    assert len(inventory["active_resource_sha256"]) == 1
    assert len(inventory["image_resource_sha256"]) == 1
    assert len(inventory["script_resource_sha256"]) == 1


@pytest.mark.parametrize("container", ["script", "style", "textarea"])
def test_self_closing_raw_text_container_is_fail_closed(container: str) -> None:
    parser = validator._MetadataParser()
    parser.feed(
        f"<{container}/><h1>Browser-hidden heading</h1>"
        f'<main data-raos-v2-package-marker="{validator.PHASE3_PACKAGE_MARKER}">'
        "hidden marker</main>"
    )
    assert parser.resource_inventory()["unsafe_resource_count"] >= 1


@pytest.mark.parametrize(
    "captured_offset",
    [3, 7],
)
def test_post_action_export_role_and_order_are_not_swappable(
    captured_offset: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preaction, capture, package, export, evaluated_at = _verification_inputs(
        monkeypatch
    )
    candidate = package["review_candidate"]
    assert isinstance(candidate, dict)
    phase2 = candidate["phase2_candidate"]
    assert isinstance(phase2, dict)
    base_time = datetime.fromisoformat(str(phase2["created_at"]))
    export["captured_at"] = (base_time + timedelta(seconds=captured_offset)).isoformat()
    if captured_offset == 3:
        export["export_role"] = "PRE_WRITE_EXPORT"

    with pytest.raises(
        validator.ValidationFailure,
        match=(
            "RAOS_V2_PUBLIC_VERIFICATION_EXPORT_INVALID"
            if captured_offset == 3
            else "RAOS_V2_PUBLIC_VERIFICATION_EXPORT_STALE"
        ),
    ):
        validator.derive_phase3_public_verification_receipt(
            preaction_capture=preaction,
            capture=capture,
            sealed_package=package,
            post_action_export_binding=export,
            evaluated_at=evaluated_at,
            rollback_invoked=False,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("redirect_chain", [{"status": 301}]),
        ("canonical_tag_count", 2),
        ("head_tag_count", 2),
        ("metadata_location_violation_count", 1),
        ("title", "Drifted title"),
        ("title_tag_count", 2),
        ("meta_description", "Drifted description"),
        ("meta_description_tag_count", 2),
        ("robots_meta", "noindex"),
        ("robots_http", "noindex"),
        ("robots_http_indexability_safe", False),
        ("content_type_media_type", "text/plain"),
        ("refresh_http_present", True),
        ("link_http_sha256", "f" * 64),
        ("robots_tag_count", 2),
        ("crawler_robots_tag_count", -1),
        ("crawler_robots_indexability_safe", False),
        ("h1_count", 2),
        ("package_marker_count", 0),
        ("package_marker_attribute_count", 2),
        ("post_content_envelope_count", 0),
        ("post_content_envelope_attribute_count", 2),
        ("blocked_post_content_envelope_count", 1),
        ("post_content_envelope_marker_child_count", 0),
        ("post_content_envelope_valid", False),
        ("post_content_marker_subtree_count", 0),
        ("post_content_semantic_sha256", "f" * 64),
        ("disclosure_marker_count", 0),
        ("cta_state_count", 4),
        ("blocked_cta_count", 2),
        ("affiliate_url_count", 1),
        ("ambiguous_attribute_count", 1),
        ("image_count", -1),
        ("inline_executable_script_count", -1),
        ("external_script_count", -1),
        ("json_ld_script_count", 0),
        ("json_ld_sha256", "UNAVAILABLE"),
        ("json_ld_types", ["Article"]),
        ("json_ld_visible_content_match", False),
    ],
)
def test_v2_public_receipt_rejects_observation_self_assertion_or_drift(
    field: str,
    value: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _verification_inputs(monkeypatch)
    preaction, capture, package, export, evaluated_at = inputs
    observation = capture["observation"]
    assert isinstance(observation, dict)
    observation[field] = value
    with pytest.raises(
        validator.ValidationFailure,
        match="RAOS_V2_PUBLIC_VERIFICATION_DERIVATION_INVALID",
    ):
        validator.derive_phase3_public_verification_receipt(
            preaction_capture=preaction,
            capture=capture,
            sealed_package=package,
            post_action_export_binding=export,
            evaluated_at=evaluated_at,
            rollback_invoked=False,
        )


def test_v2_public_receipt_rejects_unsealed_or_stale_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preaction, capture, package, export, evaluated_at = _verification_inputs(
        monkeypatch
    )
    unsealed = deepcopy(package)
    unsealed["state"] = "HUMAN_REVIEWED"
    semantic = dict(unsealed)
    semantic.pop("package_digest")
    unsealed["package_digest"] = validator._semantic_digest(semantic)
    with pytest.raises(
        validator.ValidationFailure,
        match="RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_INVALID",
    ):
        validator.derive_phase3_public_verification_receipt(
            preaction_capture=preaction,
            capture=capture,
            sealed_package=unsealed,
            post_action_export_binding=export,
            evaluated_at=evaluated_at,
            rollback_invoked=False,
        )

    stale_preaction, stale_capture, stale_package, stale_export, _ = (
        _verification_inputs(monkeypatch)
    )
    candidate = stale_package["review_candidate"]
    assert isinstance(candidate, dict)
    bindings = candidate["claim_bindings"]
    assert isinstance(bindings, list)
    deadline = min(
        datetime.fromisoformat(str(binding["next_review_at"]))
        for binding in bindings
        if isinstance(binding, dict)
    )
    observation = stale_capture["observation"]
    assert isinstance(observation, dict)
    stale_capture["captured_at"] = deadline.isoformat()
    observation["observed_at"] = deadline.isoformat()
    stale_export["captured_at"] = deadline.isoformat()
    with pytest.raises(
        validator.ValidationFailure,
        match="RAOS_V2_PUBLIC_VERIFICATION_PACKAGE_STALE",
    ):
        validator.derive_phase3_public_verification_receipt(
            preaction_capture=stale_preaction,
            capture=stale_capture,
            sealed_package=stale_package,
            post_action_export_binding=stale_export,
            evaluated_at=deadline,
            rollback_invoked=False,
        )


@pytest.mark.parametrize(
    "injected_json",
    [
        (
            '{"@graph":['
            '{"@type":"Article","headline":"Title",'
            '"mainEntityOfPage":{"@id":"https://kurashinoshirube.com/'
            'carry-on-suitcase-comparison/"},"about":{"@type":"Product"}},'
            '{"@type":"BreadcrumbList","itemListElement":[]},'
            '{"@type":"Organization","url":"https://kurashinoshirube.com/"},'
            '{"@type":"WebSite","url":"https://kurashinoshirube.com/"}'
            "]}"
        ),
        '{"@graph":[],"duplicate":1,"duplicate":2}',
        '{"@graph":[],"invalid":NaN}',
    ],
)
def test_json_ld_rejects_nested_forbidden_type_duplicate_key_or_nonfinite(
    injected_json: str,
) -> None:
    parser = validator._MetadataParser()
    parser.feed(
        '<script type="application/ld+json">'
        + injected_json
        + "</script><h1>Title</h1>"
    )
    summary = validator._phase3_json_ld_summary(
        parser,
        h1="Title",
        canonical=validator.PHASE3_PUBLIC_URL,
    )
    assert parser.json_ld_invalid_count > 0
    assert summary["json_ld_visible_content_match"] is False


@pytest.mark.parametrize(
    "output",
    [
        Path("/tmp/capture.json"),
        Path("changes/raos-v2/recorded-inputs/phase0-capture.v1.json"),
        Path("changes/raos-v2/recorded-inputs/phase3/../escape.json"),
        Path("changes/raos-v2/recorded-inputs/phase3/nested/capture.json"),
        Path("changes/raos-v2/recorded-inputs/phase3/capture.yaml"),
        Path("changes/raos-v2/recorded-inputs/phase3/.hidden.json"),
    ],
)
def test_phase3_output_allowlist_rejects_escape_and_phase0_baseline(
    output: Path,
) -> None:
    with pytest.raises(
        validator.ValidationFailure,
        match="PHASE3_CAPTURE_OUTPUT_REJECTED",
    ):
        validator._phase3_capture_output_path(output)


def test_phase3_writer_creates_once_and_cannot_touch_phase0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    phase0 = repository / "changes/raos-v2/recorded-inputs/phase0-capture.v1.json"
    phase0.parent.mkdir(parents=True)
    phase0.write_text("immutable phase 0\n", encoding="utf-8")
    monkeypatch.setattr(validator, "ROOT", repository)

    validator._write_new_phase3_capture(SAFE_OUTPUT, b'{"safe":true}\n')
    target = repository / SAFE_OUTPUT
    assert target.read_bytes() == b'{"safe":true}\n'
    with pytest.raises(
        validator.ValidationFailure,
        match="PHASE3_CAPTURE_OUTPUT_ALREADY_EXISTS",
    ):
        validator._write_new_phase3_capture(SAFE_OUTPUT, b'{"overwrite":true}\n')
    assert target.read_bytes() == b'{"safe":true}\n'
    assert phase0.read_text(encoding="utf-8") == "immutable phase 0\n"


def test_phase3_writer_rejects_symlink_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    recorded_inputs = repository / "changes/raos-v2/recorded-inputs"
    recorded_inputs.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (recorded_inputs / "phase3").symlink_to(outside)
    monkeypatch.setattr(validator, "ROOT", repository)

    with pytest.raises(
        validator.ValidationFailure,
        match="PHASE3_CAPTURE_OUTPUT_UNSAFE",
    ):
        validator._write_new_phase3_capture(SAFE_OUTPUT, b"unsafe")
    assert list(outside.iterdir()) == []


def test_phase3_target_membership_survives_general_url_capture_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locations = [
        f"{validator.ORIGIN}/unrelated-{index}/"
        for index in range(validator.MAX_CAPTURE_URLS)
    ] + [validator.PHASE3_PUBLIC_URL]
    xml = (
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{url}</loc></url>" for url in locations)
        + "</urlset>"
    ).encode("utf-8")

    monkeypatch.setattr(
        validator,
        "_fetch",
        lambda url: (200, xml, {"Content-Type": "application/xml"}, []),
    )
    members, evidence = validator._sitemap_urls(
        membership_target=validator.PHASE3_PUBLIC_URL
    )

    assert validator.PHASE3_PUBLIC_URL in members
    assert evidence[0]["url"] == f"{validator.ORIGIN}/sitemap_index.xml"


@pytest.mark.parametrize(
    "xml",
    [
        b'<?xml version="1.0"?><rss><channel /></rss>',
        (
            b'<?xml version="1.0"?><urlset '
            b'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            b"<url><loc>https://kurashinoshirube.com/duplicate/</loc></url>"
            b"<url><loc>https://kurashinoshirube.com/duplicate/</loc></url>"
            b"</urlset>"
        ),
    ],
)
def test_sitemap_requires_exact_protocol_shape_and_unique_locations(
    xml: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        validator,
        "_fetch",
        lambda _url: (200, xml, {"Content-Type": "application/xml"}, []),
    )
    with pytest.raises(
        validator.ValidationFailure,
        match="RAOS_V2_SITEMAP_XML_INVALID",
    ):
        validator._sitemap_urls(membership_target=validator.PHASE3_PUBLIC_URL)


def test_redirect_handler_rejects_a_second_hop() -> None:
    handler = validator._SafeRedirectHandler()
    handler.chain.append(
        {
            "status": 301,
            "from": validator.PHASE3_PUBLIC_URL,
            "to": f"{validator.ORIGIN}/first-hop/",
        }
    )
    with pytest.raises(
        validator.ValidationFailure,
        match="CAPTURE_REDIRECT_LIMIT",
    ):
        handler.redirect_request(
            validator.Request(f"{validator.ORIGIN}/first-hop/"),
            None,
            302,
            "Found",
            {},
            validator.PHASE3_PUBLIC_URL,
        )


def test_unsafe_output_is_rejected_before_optional_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_fetch(_url: str) -> object:
        nonlocal called
        called = True
        raise AssertionError("unsafe output must fail before network")

    monkeypatch.setattr(validator, "_fetch", fake_fetch)
    with pytest.raises(
        validator.ValidationFailure,
        match="PHASE3_CAPTURE_OUTPUT_REJECTED",
    ):
        validator.capture_phase3_public(
            public_read_only=True,
            output=Path("changes/raos-v2/recorded-inputs/phase0-capture.v1.json"),
        )
    assert called is False
