"""Purity, immutability, and non-authority boundaries for ST-0807."""

from __future__ import annotations

import ast
import builtins
from dataclasses import MISSING, FrozenInstanceError, fields, is_dataclass, replace
import inspect
import json
import os
from pathlib import Path
import random
import secrets
import socket
import time
import urllib.request

import pytest

from raos.domain.editorial import seo_renderer as domain

from .support import REPOSITORY_ROOT, render_request


SOURCE = REPOSITORY_ROOT / "python/raos/domain/editorial/seo_renderer.py"


def _tree() -> ast.Module:
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def test_module_imports_are_domain_safe_and_have_no_io_dependencies() -> None:
    forbidden = {
        "boto3",
        "botocore",
        "http",
        "httpx",
        "openai",
        "os",
        "pathlib",
        "psycopg",
        "random",
        "requests",
        "secrets",
        "socket",
        "sqlalchemy",
        "sqlite3",
        "subprocess",
        "time",
        "urllib",
        "uuid",
    }
    imported: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            imported.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.partition(".")[0])
    assert imported.isdisjoint(forbidden)


def test_module_has_no_dynamic_io_clock_random_database_or_action_calls() -> None:
    forbidden = {
        "approve",
        "connect",
        "emit",
        "fetch",
        "getenv",
        "now",
        "open",
        "persist",
        "publish",
        "request",
        "save",
        "send",
        "time",
        "time_ns",
        "urlopen",
        "uuid4",
        "uuid7",
        "write",
    }
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(_tree())
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert calls.isdisjoint(forbidden)


def test_render_does_not_touch_file_env_clock_random_network_or_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("side effect attempted")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(time, "time", forbidden)
    monkeypatch.setattr(time, "time_ns", forbidden)
    monkeypatch.setattr(random, "random", forbidden)
    monkeypatch.setattr(secrets, "token_hex", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)

    result = domain.render_seo(render_request())
    assert result.status is domain.RenderStatus.RENDERED_LOCAL


def test_request_result_and_every_nested_record_are_immutable() -> None:
    request = render_request()
    result = domain.render_seo(request)

    for value in (
        request,
        request.contracts,
        request.metadata,
        request.route,
        request.visible,
        request.visible.author,
        request.breadcrumbs[0],
        request.change,
        request.external_assessments[0],
        result,
        result.rendered_metadata,
        result.structured_data_manifest,
        result.binding_ledger[0],
    ):
        assert value is not None
        with pytest.raises(FrozenInstanceError):
            setattr(value, "unexpected", object())
    assert type(request.breadcrumbs) is tuple
    assert type(request.external_assessments) is tuple
    assert type(result.binding_ledger) is tuple
    assert type(result.external_assessments) is tuple


def test_domain_dataclasses_have_no_implicit_defaults() -> None:
    for value in vars(domain).values():
        if inspect.isclass(value) and is_dataclass(value):
            assert all(
                field.default is MISSING and field.default_factory is MISSING
                for field in fields(value)
            )


def test_caller_input_is_not_mutated() -> None:
    request = render_request()
    before = repr(request)
    metadata = request.metadata
    breadcrumbs = request.breadcrumbs
    assessments = request.external_assessments

    domain.render_seo(request)

    assert repr(request) == before
    assert request.metadata is metadata
    assert request.breadcrumbs is breadcrumbs
    assert request.external_assessments is assessments


@pytest.mark.parametrize(
    "render_input",
    (
        render_request(),
        render_request(origin=None),
        render_request(mode=domain.RenderMode.PREVIEW),
        render_request(assessment_state=domain.ExternalAssessmentState.NOT_EVALUATED),
    ),
)
def test_every_result_keeps_all_formal_live_and_release_authority_false(
    render_input: domain.SeoRenderRequest,
) -> None:
    result = domain.render_seo(render_input)
    expected_origin_source = (
        domain.OriginSource.NONE
        if render_input.caller_origin is None
        else domain.OriginSource.CALLER_SUPPLIED_UNAPPROVED
    )
    assert result.origin_source is expected_origin_source
    assert result.domain_approved is False
    assert result.production_domain_selected is False
    assert result.approval_authorized is False
    assert result.publication_authorized is False
    assert result.release_authorized is False
    assert result.production_authorized is False
    assert result.production_eligible is False
    assert result.formal_evidence is False
    assert result.browser_executed is False
    assert result.staging_executed is False
    assert result.tst_020_executed is False
    assert result.tst_022_executed is False
    authority = json.loads(result.local_result_json)["authority"]
    assert authority == {
        "approval_authorized": False,
        "browser": "NOT_EXECUTED",
        "browser_executed": False,
        "domain_approved": False,
        "formal_evidence": False,
        "formal_test": "NOT_EXECUTED",
        "live_validation": "NOT_EXECUTED",
        "origin_source": expected_origin_source.value,
        "production": "NOT_EXECUTED",
        "production_authorized": False,
        "production_domain_selected": False,
        "production_eligible": False,
        "publication_authorized": False,
        "release": "NOT_EXECUTED",
        "release_authorized": False,
        "runtime": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "staging_executed": False,
        "tst_020": "NOT_EXECUTED",
        "tst_020_executed": False,
        "tst_022": "NOT_EXECUTED",
        "tst_022_executed": False,
    }
    assert {
        result.formal_test_status,
        result.tst_020_status,
        result.tst_022_status,
        result.runtime_status,
        result.live_validation_status,
        result.browser_status,
        result.staging_status,
        result.release_status,
        result.production_status,
    } == {domain.ExecutionStatus.NOT_EXECUTED}


def test_only_explicit_caller_utc_time_changes_manifest_and_digest() -> None:
    request = render_request()
    later = domain.UtcInstant(request.validated_at.value.replace(microsecond=1))

    first = domain.render_seo(request)
    second = domain.render_seo(replace(request, validated_at=later))

    assert first.structured_data_manifest is not None
    assert second.structured_data_manifest is not None
    assert first.structured_data_manifest.validated_at is request.validated_at
    assert second.structured_data_manifest.validated_at is later
    assert first.local_result_digest != second.local_result_digest


def test_invalid_result_retains_the_same_closed_non_authority_shape() -> None:
    request = render_request()
    object.__setattr__(request, "origin_mode", domain.OriginMode.ROUTE_ONLY)

    result = domain.render_seo(request)

    assert result.status is domain.RenderStatus.INVALID_INPUT
    assert result.origin_source is domain.OriginSource.CALLER_SUPPLIED_UNAPPROVED
    assert result.rendered_metadata is None
    assert result.domain_approved is False
    assert result.production_domain_selected is False
    assert result.production_authorized is False
    assert result.production_eligible is False
    assert result.formal_evidence is False
    assert result.browser_executed is False
    assert result.staging_executed is False
    assert result.tst_020_executed is False
    assert result.tst_022_executed is False
    authority = json.loads(result.local_result_json)["authority"]
    assert authority["origin_source"] == "CALLER_SUPPLIED_UNAPPROVED"
    assert authority["production_authorized"] is False
    assert authority["formal_evidence"] is False


def test_public_api_has_one_request_one_result_and_one_renderer() -> None:
    assert domain.SeoRenderRequest.__name__ == "SeoRenderRequest"
    assert domain.SeoRenderResult.__name__ == "SeoRenderResult"
    assert not hasattr(domain, "LocalSeoRenderResult")
    assert not hasattr(domain, "RouteOnlyRenderRequest")
    assert not hasattr(domain, "render_route_only")
    assert {
        name
        for name, value in vars(domain).items()
        if name.startswith("render_") and inspect.isfunction(value)
    } == {"render_seo"}


def test_source_is_the_only_owned_runtime_module() -> None:
    runtime_imports = {
        node.module
        for node in ast.walk(_tree())
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(
        name.startswith(("raos.adapters", "raos.application", "raos.framework"))
        for name in runtime_imports
    )
    assert SOURCE == Path(
        REPOSITORY_ROOT, "python/raos/domain/editorial/seo_renderer.py"
    )
