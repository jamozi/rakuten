"""Purity, immutability, authority, and non-actioning boundary tests."""

from __future__ import annotations

import ast
import builtins
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime
import os
from pathlib import Path
import socket
import sqlite3
import time
from typing import NoReturn

import pytest

from .support import valid_policy_input, with_gate_state, with_policy_result
from raos.domain.editorial import policy_engine
from raos.domain.editorial.policy_engine import (
    ExecutionStatus,
    GateAssessmentState,
    GateFailureAction,
    PolicyRuleResult,
    evaluate_editorial_policy,
)


SOURCE_PATH = Path(policy_engine.__file__)


def _forbidden_side_effect(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise AssertionError("side effect attempted")


def test_module_imports_are_domain_safe_and_have_no_dynamic_io_calls() -> None:
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    allowed_import_roots = {
        "__future__",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "hashlib",
        "json",
        "re",
        "typing",
    }
    imported_roots: set[str] = set()
    forbidden_calls: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            else:
                continue
            if name in {
                "open",
                "getenv",
                "connect",
                "request",
                "urlopen",
                "publish",
                "rollback",
                "pause",
                "send",
                "emit",
                "now",
                "utcnow",
            }:
                forbidden_calls.append(name)

    assert imported_roots <= allowed_import_roots
    assert forbidden_calls == []


def test_evaluation_does_not_touch_file_env_clock_network_or_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builtins, "open", _forbidden_side_effect)
    monkeypatch.setattr(Path, "read_text", _forbidden_side_effect)
    monkeypatch.setattr(Path, "read_bytes", _forbidden_side_effect)
    monkeypatch.setattr(os, "getenv", _forbidden_side_effect)
    monkeypatch.setattr(time, "time", _forbidden_side_effect)
    monkeypatch.setattr(socket, "socket", _forbidden_side_effect)
    monkeypatch.setattr(sqlite3, "connect", _forbidden_side_effect)

    result = evaluate_editorial_policy(valid_policy_input())

    assert result.local_eligibility is True
    assert result.publication_authorized is False


def test_all_returned_collections_and_nested_records_are_immutable() -> None:
    value = with_policy_result(
        valid_policy_input(),
        "POL-CONT-001",
        PolicyRuleResult.FAIL,
    )
    result = evaluate_editorial_policy(value)

    assert type(result.input_findings) is tuple
    assert type(result.policy_findings) is tuple
    assert type(result.waiver_evaluations) is tuple
    assert type(result.policy_findings[0].evidence) is tuple
    with pytest.raises(FrozenInstanceError):
        result.local_eligibility = True  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.policy_findings[0].is_blocking = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.policy_findings[0].target.target_ref = value.article_version_id  # type: ignore[misc]


def test_caller_input_is_not_mutated() -> None:
    value = valid_policy_input()
    before = deepcopy(value)
    policy_assessments = value.policy_assessments
    axis_assessments = value.axis_assessments

    evaluate_editorial_policy(value)

    assert value == before
    assert value.policy_assessments is policy_assessments
    assert value.axis_assessments is axis_assessments


def test_qg_cont_012_exposes_only_symbolic_required_action() -> None:
    value = with_gate_state(
        valid_policy_input(),
        "QG-CONT-012",
        GateAssessmentState.FAIL,
    )
    before = deepcopy(value)

    result = evaluate_editorial_policy(value)

    assert (
        result.post_publication_required_action is GateFailureAction.ROLLBACK_OR_PAUSE
    )
    assert result.local_eligibility is False
    assert result.publication_authorized is False
    assert result.production_eligible is False
    assert value == before


def test_every_result_keeps_formal_live_and_release_boundaries_not_executed() -> None:
    values = (
        valid_policy_input(),
        with_policy_result(
            valid_policy_input(),
            "POL-CONT-001",
            PolicyRuleResult.FAIL,
        ),
        object(),
    )

    for value in values:
        result = evaluate_editorial_policy(value)
        assert result.publication_authorized is False
        assert result.production_eligible is False
        assert result.formal_test_status is ExecutionStatus.NOT_EXECUTED
        assert result.live_validation_status is ExecutionStatus.NOT_EXECUTED
        assert result.staging_status is ExecutionStatus.NOT_EXECUTED
        assert result.release_status is ExecutionStatus.NOT_EXECUTED
        assert result.production_status is ExecutionStatus.NOT_EXECUTED


def test_evaluation_uses_only_explicit_caller_utc_time() -> None:
    value = valid_policy_input()
    changed_time = replace(
        value.evaluated_at,
        value=datetime(
            2026, 8, 12, 1, 2, 3, 456789, tzinfo=value.evaluated_at.value.tzinfo
        ),
    )

    first = evaluate_editorial_policy(value)
    second = evaluate_editorial_policy(replace(value, evaluated_at=changed_time))

    assert first.local_result_digest != second.local_result_digest
    assert "2026-08-12T01:02:03.456789Z" in second.local_result_json
