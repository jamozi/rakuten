"""Architecture, safety, and side-effect boundaries for ST-1402."""

from __future__ import annotations

import ast
import builtins
from dataclasses import fields
from inspect import signature
import os
from pathlib import Path
import pickle
import socket
import sqlite3
import time
from typing import NoReturn

import pytest

from raos.application.freshness.safe_degradation import (
    SafeDegradationService,
    bind_safe_degradation_request,
)
from raos.domain.freshness.freshness import FreshnessPolicyActivation
from raos.domain.freshness.safe_degradation import (
    SafeDegradationDecision,
    SafeDegradationFreshnessBinding,
    SafeDegradationRequest,
    decide_safe_degradation,
)
from raos.ports.safe_degradation import SafeDegradationExchange

from .support import bound_request


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_PATHS = (
    ROOT / "python/raos/domain/freshness/safe_degradation.py",
    ROOT / "python/raos/ports/safe_degradation.py",
    ROOT / "python/raos/application/freshness/safe_degradation.py",
    ROOT / "python/raos/adapters/recorded_safe_degradation.py",
)


def _forbidden_side_effect(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise AssertionError("side effect attempted")


def _trees() -> tuple[ast.AST, ...]:
    return tuple(
        ast.parse(path.read_text(encoding="utf-8")) for path in PRODUCTION_PATHS
    )


def test_port_exposes_only_value_free_decision() -> None:
    assert {
        name
        for name, value in SafeDegradationExchange.__dict__.items()
        if callable(value) and not name.startswith("_")
    } == {"decide"}


def test_application_api_requires_complete_st1401_request_and_result() -> None:
    assert tuple(signature(bind_safe_degradation_request).parameters) == (
        "freshness_request",
        "freshness_result",
        "availability_aggregate",
    )
    assert tuple(signature(SafeDegradationService.decide).parameters) == (
        "self",
        "freshness_request",
        "freshness_result",
        "availability_aggregate",
    )


def test_domain_and_port_preserve_inward_dependency_direction() -> None:
    trees = _trees()
    domain_imports = {
        node.module or ""
        for node in ast.walk(trees[0])
        if isinstance(node, ast.ImportFrom)
    }
    port_imports = {
        node.module or ""
        for node in ast.walk(trees[1])
        if isinstance(node, ast.ImportFrom)
    }
    assert not any(
        name.startswith(("raos.application", "raos.adapters", "raos.ports"))
        for name in domain_imports
    )
    assert not any(
        name.startswith(("raos.application", "raos.adapters")) for name in port_imports
    )


def test_slice_has_no_renderer_web_generated_storage_or_provider_dependency() -> None:
    imported = {
        alias.name
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imported.isdisjoint(
        {
            "boto3",
            "fastapi",
            "httpx",
            "pathlib",
            "psycopg",
            "requests",
            "socket",
            "sqlalchemy",
            "subprocess",
            "urllib",
        }
    )
    assert not any(
        name.startswith(
            (
                "raos.generated",
                "raos.application.publishing",
                "raos.adapters.wordpress",
            )
        )
        for name in imported
    )


def test_slice_has_no_clock_io_network_or_state_write_calls() -> None:
    called_names = {
        node.func.id
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert called_names.isdisjoint(
        {"open", "getenv", "system", "exec", "eval", "sleep", "uuid4", "uuid7"}
    )
    assert called_attributes.isdisjoint(
        {
            "add",
            "commit",
            "connect",
            "delete",
            "execute",
            "getenv",
            "now",
            "open",
            "publish",
            "read",
            "request",
            "retry",
            "rollback",
            "save",
            "send",
            "utcnow",
            "write",
        }
    )


def test_decision_does_not_touch_file_env_clock_network_or_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = bound_request()
    monkeypatch.setattr(builtins, "open", _forbidden_side_effect)
    monkeypatch.setattr(Path, "read_text", _forbidden_side_effect)
    monkeypatch.setattr(Path, "read_bytes", _forbidden_side_effect)
    monkeypatch.setattr(os, "getenv", _forbidden_side_effect)
    monkeypatch.setattr(time, "time", _forbidden_side_effect)
    monkeypatch.setattr(socket, "socket", _forbidden_side_effect)
    monkeypatch.setattr(sqlite3, "connect", _forbidden_side_effect)
    decision = decide_safe_degradation(request)
    assert decision.can_change_state is False
    assert decision.renderer_effects.value == "NOT_EXECUTED"


def test_public_shapes_exclude_values_links_copy_html_dom_and_payloads() -> None:
    combined = {
        item.name
        for value_type in (
            SafeDegradationFreshnessBinding,
            SafeDegradationRequest,
            SafeDegradationDecision,
        )
        for item in fields(value_type)
    }
    assert {
        "price",
        "price_jpy",
        "stock",
        "availability",
        "affiliate_url",
        "url",
        "href",
        "link",
        "notice_copy",
        "copy",
        "html",
        "dom",
        "payload",
        "article_body",
        "publication_snapshot",
        "public_read_model",
    }.isdisjoint(combined)


def test_public_surface_has_no_effect_approval_publication_or_reorder_method() -> None:
    public_methods = {
        node.name
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    assert public_methods.isdisjoint(
        {
            "activate",
            "apply",
            "approve",
            "create_job",
            "dispatch",
            "enable_cta",
            "enqueue",
            "execute",
            "persist",
            "publish",
            "render",
            "reorder",
            "republish",
            "retry",
            "save",
            "write",
        }
    )


def test_od007_and_all_effect_boundaries_remain_disabled() -> None:
    request = bound_request()
    decision = decide_safe_degradation(request)
    assert request.freshness.policy_activation is (
        FreshnessPolicyActivation.DISABLED_UNRESOLVED_OD_007
    )
    assert request.freshness.open_decision_id == "OD-007"
    assert request.freshness.policy_active is False
    assert request.freshness.persistence.value == "NOT_EXECUTED"
    assert request.freshness.attestation.value == "NOT_ATTESTED"
    assert decision.renderer_effects.value == "NOT_EXECUTED"
    assert decision.persistence.value == "NOT_EXECUTED"
    assert decision.publication_authorized is False
    assert decision.live_eligible is False


def test_values_failures_fixtures_and_services_are_not_pickleable() -> None:
    request = bound_request()
    decision = decide_safe_degradation(request)
    for value in (request.freshness, request, decision):
        with pytest.raises(TypeError):
            pickle.dumps(value)


def test_repr_and_str_do_not_expose_fingerprints_or_rejected_material() -> None:
    request = bound_request()
    decision = decide_safe_degradation(request)
    assert request.fingerprint not in repr(request)
    assert decision.fingerprint not in repr(decision)
    assert "redacted-st1402" in repr(request)
    assert "redacted-st1402" in str(decision)
