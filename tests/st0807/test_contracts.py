"""Contract and origin validation for ST-0807."""

from __future__ import annotations

from dataclasses import replace

import pytest

from raos.domain.editorial.seo_renderer import (
    InputFindingCode,
    OriginMode,
    OriginSource,
    RenderStatus,
    _normalize_origin,
    render_seo,
)

from conftest import render_request


@pytest.mark.parametrize(
    ("raw", "normalized"),
    (
        (None, None),
        ("https://example.test", "https://example.test"),
        ("https://example.test/", "https://example.test"),
        ("https://example.test:8443", "https://example.test:8443"),
    ),
)
def test_origin_accepts_only_explicit_normalized_https_origin(
    raw: str | None,
    normalized: str | None,
) -> None:
    assert _normalize_origin(raw) == (True, normalized)


@pytest.mark.parametrize(
    "raw",
    (
        "http://example.test",
        "https://user@example.test",
        "https://example.test/path",
        "https://example.test?query=1",
        "https://example.test#fragment",
        "https://example.test:443",
        "https://EXAMPLE.test",
    ),
)
def test_origin_rejects_non_origin_or_non_normalized_values(raw: str) -> None:
    assert _normalize_origin(raw) == (False, None)


def test_origin_mode_is_explicit_and_digest_bound() -> None:
    caller = render_request()
    route_only = render_request(origin=None)

    caller_result = render_seo(caller)
    route_only_result = render_seo(route_only)

    assert caller.origin_mode is OriginMode.CALLER_SUPPLIED_ORIGIN
    assert caller_result.origin_source is OriginSource.CALLER_SUPPLIED_UNAPPROVED
    assert '"origin_mode":"CALLER_SUPPLIED_ORIGIN"' in caller_result.local_result_json
    assert route_only.origin_mode is OriginMode.ROUTE_ONLY
    assert route_only_result.origin_source is OriginSource.NONE
    assert '"origin_mode":"ROUTE_ONLY"' in route_only_result.local_result_json
    assert caller_result.local_result_digest != route_only_result.local_result_digest


@pytest.mark.parametrize(
    "render_input",
    (
        replace(render_request(), origin_mode=OriginMode.ROUTE_ONLY),
        replace(
            render_request(origin=None),
            origin_mode=OriginMode.CALLER_SUPPLIED_ORIGIN,
        ),
    ),
)
def test_origin_mode_and_origin_presence_mismatch_fails_closed(
    render_input: object,
) -> None:
    result = render_seo(render_input)

    assert result.status is RenderStatus.INVALID_INPUT
    assert InputFindingCode.ORIGIN_MODE_MISMATCH in result.input_findings
    assert result.rendered_metadata is None
    assert result.jsonld_json is None
    assert result.conditional_local_eligibility is False


def test_runtime_origin_mode_value_is_revalidated() -> None:
    request = render_request()
    object.__setattr__(request, "origin_mode", "CALLER_SUPPLIED_ORIGIN")

    result = render_seo(request)

    assert result.status is RenderStatus.INVALID_INPUT
    assert InputFindingCode.ORIGIN_MODE_INVALID in result.input_findings
    assert result.rendered_metadata is None
