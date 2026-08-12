"""Purity, immutable-value, and non-actioning boundaries for ST-0901 PR1."""

from __future__ import annotations

import ast
import builtins
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
import os
from pathlib import Path
import socket
import sqlite3
import time
from typing import NoReturn

import pytest

from conftest import (
    FINISHED_AT,
    REPOSITORY_ROOT,
    STARTED_AT,
    assigned,
    decision_reference,
    draft,
    in_progress,
)
from raos.domain.publishing import review_workflow as domain


SOURCE_PATH = REPOSITORY_ROOT / "python/raos/domain/publishing/review_workflow.py"


def _forbidden_side_effect(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise AssertionError("side effect attempted")


def test_module_imports_and_calls_are_pure_domain_only() -> None:
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    allowed_import_roots = {
        "__future__",
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "re",
        "types",
        "typing",
        "uuid",
    }
    imported_roots: set[str] = set()
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.partition(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
    assert imported_roots <= allowed_import_roots
    assert called.isdisjoint(
        {
            "open",
            "read_text",
            "read_bytes",
            "getenv",
            "connect",
            "request",
            "urlopen",
            "publish",
            "save",
            "commit",
            "write",
            "emit",
            "now",
            "utcnow",
            "time",
            "uuid1",
            "uuid4",
            "uuid6",
            "uuid7",
        }
    )


def test_evaluation_does_not_touch_files_env_clock_network_or_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builtins, "open", _forbidden_side_effect)
    monkeypatch.setattr(Path, "read_text", _forbidden_side_effect)
    monkeypatch.setattr(Path, "read_bytes", _forbidden_side_effect)
    monkeypatch.setattr(os, "getenv", _forbidden_side_effect)
    monkeypatch.setattr(time, "time", _forbidden_side_effect)
    monkeypatch.setattr(socket, "socket", _forbidden_side_effect)
    monkeypatch.setattr(sqlite3, "connect", _forbidden_side_effect)

    started = domain.transition_review_assignment(
        assigned(),
        domain.ReviewAssignmentState.IN_PROGRESS,
        STARTED_AT,
        None,
    )
    validated = domain.validate_review_decision(started, draft())
    completed = domain.transition_review_assignment(
        started,
        domain.ReviewAssignmentState.COMPLETED,
        FINISHED_AT,
        decision_reference(),
    )

    assert validated.decision is domain.ReviewDecisionKind.CHANGES_REQUESTED
    assert completed.status is domain.ReviewAssignmentState.COMPLETED


def test_domain_dataclasses_are_frozen_slotted_and_redacted() -> None:
    for name, value in vars(domain).items():
        if not inspect.isclass(value) or not is_dataclass(value):
            continue
        assert "__slots__" in value.__dict__, name
        parameters = getattr(value, "__dataclass_params__")
        assert parameters.frozen is True, name
        assert parameters.repr is False, name

    value = in_progress()
    assert "018f" not in repr(value)
    assert repr(value) == "ReviewAssignment(<redacted>)"
    assert str(value) == "<redacted>"
    with pytest.raises(FrozenInstanceError):
        value.priority = 99  # type: ignore[misc]


def test_all_public_collection_values_are_immutable_tuples() -> None:
    assert type(domain.HUMAN_REVIEW_CHECKLIST) is tuple
    assert type(domain.HUMAN_REVIEW_CHECKLIST_IDS) is tuple
    assert type(domain.CHECKLIST_RESPONSE_TOKENS) is tuple
    assert type(domain.CHECKLIST_EVIDENCE_OR_COMMENT_REQUIRED_ON) is tuple
    value = domain.validate_review_decision(in_progress(), draft())
    assert type(value.checklist_results) is tuple
    assert all(type(result.evidence) is tuple for result in value.checklist_results)


def test_pr1_defines_no_application_persistence_or_operation_execution_surface() -> (
    None
):
    source = SOURCE_PATH.read_text(encoding="utf-8")
    forbidden_names = {
        "FastAPI",
        "Repository",
        "UnitOfWork",
        "Session",
        "PUBADM",
        "ED-030",
        "If-Match",
        "Idempotency-Key",
        "supersedes",
        "effective_decision",
        "finding_status",
        "approval_record",
    }
    assert all(name not in source for name in forbidden_names)
    assert not hasattr(domain, "ReviewWorkflowService")
    assert not hasattr(domain, "ReviewDecisionRepository")
    assert not hasattr(domain, "approve")
    assert not hasattr(domain, "execute")


def test_pubadm004_structural_validation_does_not_mutate_assignment() -> None:
    assignment = in_progress()
    coordinates = (
        assignment.assignment_id,
        assignment.article_version_id,
        assignment.review_type,
        assignment.assigned_by,
        assignment.assigned_to,
        assignment.priority,
        assignment.status,
        assignment.lock_version,
    )

    domain.validate_review_decision(assignment, draft())

    assert (
        assignment.assignment_id,
        assignment.article_version_id,
        assignment.review_type,
        assignment.assigned_by,
        assignment.assigned_to,
        assignment.priority,
        assignment.status,
        assignment.lock_version,
    ) == coordinates


def test_local_policy_eligibility_and_finding_vocabulary_are_not_imported() -> None:
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "raos.domain.editorial.policy_engine" not in imported_modules
    assert not hasattr(domain, "local_eligibility")
    assert not hasattr(domain, "FindingState")
