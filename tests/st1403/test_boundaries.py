"""Architecture, trust, authority, and side-effect boundaries for ST-1403."""

from __future__ import annotations

import ast
import builtins
from dataclasses import fields
from inspect import signature
import os
from pathlib import Path
import socket
import sqlite3
import time
from typing import NoReturn

import pytest

from raos.application.freshness.refresh_proposal import (
    RefreshProposalService,
    bind_refresh_proposal_request,
)
from raos.domain.freshness.refresh_proposal import (
    RefreshActionCandidate,
    RefreshDiff,
    RefreshExecutionStatus,
    RefreshProposal,
    build_refresh_proposal,
)
from raos.ports.refresh_proposal import RefreshProposalExchange

from .support import (
    freshness_request,
    freshness_result,
    policy_result,
    proposal_candidate,
    valid_policy_input,
)


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_PATHS = (
    ROOT / "python/raos/domain/freshness/refresh_proposal.py",
    ROOT / "python/raos/ports/refresh_proposal.py",
    ROOT / "python/raos/application/freshness/refresh_proposal.py",
    ROOT / "python/raos/adapters/recorded_refresh_proposal.py",
)


def _forbidden_side_effect(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise AssertionError("side effect attempted")


def _trees() -> tuple[ast.AST, ...]:
    return tuple(
        ast.parse(path.read_text(encoding="utf-8")) for path in PRODUCTION_PATHS
    )


def _proposal() -> RefreshProposal:
    exact_freshness_request = freshness_request()
    exact_policy_request = valid_policy_input()
    request = bind_refresh_proposal_request(
        candidate=proposal_candidate(),
        freshness_request=exact_freshness_request,
        freshness_result=freshness_result(request=exact_freshness_request),
        policy_request=exact_policy_request,
        policy_result=policy_result(exact_policy_request),
    )
    return build_refresh_proposal(request)


def test_port_exposes_only_proposal_generation() -> None:
    assert {
        name
        for name, value in RefreshProposalExchange.__dict__.items()
        if callable(value) and not name.startswith("_")
    } == {"propose"}


def test_application_api_requires_complete_predecessor_requests_and_results() -> None:
    assert tuple(signature(bind_refresh_proposal_request).parameters) == (
        "candidate",
        "freshness_request",
        "freshness_result",
        "policy_request",
        "policy_result",
    )
    assert tuple(signature(RefreshProposalService.propose).parameters) == (
        "self",
        "candidate",
        "freshness_request",
        "freshness_result",
        "policy_request",
        "policy_result",
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


def test_production_slice_has_no_io_network_provider_or_database_imports() -> None:
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
    assert not any(name.startswith("raos.generated") for name in imported)


def test_production_slice_has_no_clock_io_or_state_write_calls() -> None:
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


def test_generation_does_not_touch_file_env_clock_network_or_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exact_freshness_request = freshness_request()
    exact_policy_request = valid_policy_input()
    request = bind_refresh_proposal_request(
        candidate=proposal_candidate(),
        freshness_request=exact_freshness_request,
        freshness_result=freshness_result(request=exact_freshness_request),
        policy_request=exact_policy_request,
        policy_result=policy_result(exact_policy_request),
    )
    monkeypatch.setattr(builtins, "open", _forbidden_side_effect)
    monkeypatch.setattr(Path, "read_text", _forbidden_side_effect)
    monkeypatch.setattr(Path, "read_bytes", _forbidden_side_effect)
    monkeypatch.setattr(os, "getenv", _forbidden_side_effect)
    monkeypatch.setattr(time, "time", _forbidden_side_effect)
    monkeypatch.setattr(socket, "socket", _forbidden_side_effect)
    monkeypatch.setattr(sqlite3, "connect", _forbidden_side_effect)

    result = build_refresh_proposal(request)

    assert result.can_change_state is False
    assert result.automatic_reordering_authorized is False


def test_public_surface_has_no_execution_publication_or_reordering_method() -> None:
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
            "approve",
            "create_job",
            "dispatch",
            "enqueue",
            "execute",
            "persist",
            "publish",
            "reorder",
            "republish",
            "retry",
            "save",
            "write",
        }
    )


def test_diff_and_action_shapes_exclude_raw_values_and_finance_inputs() -> None:
    diff_fields = {item.name for item in fields(RefreshDiff)}
    action_fields = {item.name for item in fields(RefreshActionCandidate)}
    combined = diff_fields | action_fields

    assert {
        "before_value",
        "after_value",
        "affiliate_rate",
        "commission_amount",
        "expected_incremental_profit_jpy",
        "revenue_by_product",
        "rakuten_review_body",
        "unapproved_priority_override",
    }.isdisjoint(combined)
    assert {"before_sha256", "after_sha256"} <= diff_fields
    assert "deterministic_priority_rank" in diff_fields


def test_every_output_preserves_non_authority_and_unexecuted_boundaries() -> None:
    proposal = _proposal()

    assert proposal.authority.value == "UNAPPROVED_PROPOSAL"
    assert proposal.can_change_state is False
    assert proposal.automatic_reordering_authorized is False
    assert all(
        status is RefreshExecutionStatus.NOT_EXECUTED
        for status in (
            proposal.persistence_status,
            proposal.formal_test_status,
            proposal.live_validation_status,
            proposal.staging_status,
            proposal.release_status,
            proposal.production_status,
        )
    )
    assert all(item.can_change_state is False for item in proposal.action_candidates)


def test_slice_does_not_claim_formal_validation_or_production_eligibility() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in PRODUCTION_PATHS)

    assert '"VALIDATED"' not in combined
    assert "PRODUCTION_ELIGIBLE" not in combined


def test_slice_keeps_od007_disabled_and_does_not_add_threshold_inputs() -> None:
    proposal = _proposal()
    exact_freshness_request = freshness_request()
    exact_policy_request = valid_policy_input()
    freshness = bind_refresh_proposal_request(
        candidate=proposal_candidate(),
        freshness_request=exact_freshness_request,
        freshness_result=freshness_result(request=exact_freshness_request),
        policy_request=exact_policy_request,
        policy_result=policy_result(exact_policy_request),
    ).freshness

    assert freshness.open_decision_id == "OD-007"
    assert freshness.policy_active is False
    assert freshness.policy_activation.value == "DISABLED_UNRESOLVED_OD_007"
    assert proposal.freshness_evaluation_fingerprint == freshness.evaluation_fingerprint
    assert "freshness_threshold" not in {item.name for item in fields(RefreshDiff)}
