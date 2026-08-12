"""Positive recorded-local PUBADM-004 decision append behavior."""

from __future__ import annotations

import pytest

from conftest import REVIEWER_ID, adapter, request, service, step
from raos.domain.publishing.review_decision_operations import (
    RecordedAuditAction,
    RecordedExecution,
    RecordedReadiness,
)
from raos.domain.publishing.review_workflow import ReviewDecisionKind


@pytest.mark.parametrize(
    "decision",
    (ReviewDecisionKind.CHANGES_REQUESTED, ReviewDecisionKind.REJECT),
)
def test_negative_decision_append_returns_immutable_local_artifacts(
    decision: ReviewDecisionKind,
) -> None:
    command = request(decision=decision)
    scripted = step(value=command)
    exchange = adapter(scripted)

    result = service(exchange).execute(request=command)

    assert result.record.decision.decision is decision
    assert result.record.decided_by == REVIEWER_ID
    assert result.assignment == command.assignment
    assert result.record.assignment_sha256 == command.assignment_sha256
    assert result.history.records == (result.record,)
    assert result.audit.action is RecordedAuditAction.DECISION_RECORD
    assert result.audit.record_sha256 == result.record.record_sha256
    assert result.execution is RecordedExecution.RECORDED_ONLY
    assert result.readiness is RecordedReadiness.NOT_READY
    for field in (
        "authentication",
        "identity_attestation",
        "persistence",
        "transaction",
        "unit_of_work",
        "database_enforcement",
        "durable_idempotency",
        "audit_durability",
        "audit_atomicity",
        "events",
        "outbox",
        "delivery",
        "assignment_mutation",
        "finding_mutation",
        "approval",
        "http_api",
        "formal_verification",
        "live",
        "staging",
        "release",
        "production",
        "publication",
    ):
        assert getattr(result, field) is RecordedExecution.NOT_EXECUTED
    assert result.canonical_bytes() == result.canonical_bytes()


def test_recording_never_changes_any_assignment_coordinate() -> None:
    command = request()
    before = command.assignment

    result = service(adapter(step(value=command))).execute(request=command)

    assert result.assignment is not before
    assert result.assignment == before
    assert result.assignment.assignment_id == before.assignment_id
    assert result.assignment.article_version_id == before.article_version_id
    assert result.assignment.status is before.status
    assert result.assignment.lock_version == before.lock_version
    assert result.assignment.priority == before.priority
    assert result.assignment.started_at == before.started_at
    assert result.assignment.updated_at == before.updated_at
    assert result.assignment.completion_decision_reference is None
