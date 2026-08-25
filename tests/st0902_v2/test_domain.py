from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest

from raos.adapters.recorded_final_approval import RecordedFinalApprovalStep
from raos.domain.publishing.final_approval import (
    ExternalGateStatus,
    FinalApprovalFailure,
    FinalApprovalFailureCode,
    FinalApprovalFindingSnapshotV2,
    RecordedFinalApprovalAuthorizationV2,
    RecordedFinalApproverV2,
    SiteId,
    grant_final_approval_v2,
)
from raos.domain.publishing.review_decision_operations import (
    RecordedSubjectKind,
    RecordedSubjectStatus,
)
from raos.domain.publishing.review_workflow import PrincipalId, UtcTimestamp
from raos.domain.shared.persistence import Sha256Digest

from .conftest import request_with


def uuid7(suffix: int) -> UUID:
    return UUID(f"018f3e90-7b00-7000-8000-{suffix:012d}")


def assert_code(
    code: FinalApprovalFailureCode,
    call: Callable[[], object],
) -> None:
    with pytest.raises(FinalApprovalFailure) as captured:
        call()
    assert captured.value.code is code
    assert str(captured.value) == code.value
    assert "Recorded synthetic human" not in repr(captured.value)


def authorization_for(
    step: RecordedFinalApprovalStep,
    actor: RecordedFinalApproverV2,
) -> RecordedFinalApprovalAuthorizationV2:
    return RecordedFinalApprovalAuthorizationV2(
        request_sha256=step.request.request_sha256,
        actor=actor,
    )


def test_exact_gate_bundle_records_only_local_final_approval(
    step: RecordedFinalApprovalStep,
) -> None:
    request = step.request
    result = grant_final_approval_v2(
        request=request,
        authorization=step.authorization,
    )

    assert request.gate_bundle.article_version_id == request.article_version_id
    assert request.gate_bundle.coverage_report_sha256 == (
        request.coverage_report.report_sha256
    )
    assert request.gate_bundle.policy_report_sha256 == (
        request.policy_report.report_sha256
    )
    assert request.gate_bundle.review_result_sha256 == (
        request.review_result.result_sha256
    )
    assert request.gate_bundle.finding_clearance_sha256 == (
        request.finding_snapshot.snapshot_sha256
    )
    assert result.record.approved_by == step.actor.principal_id
    assert result.audit.record_sha256 == result.record.record_sha256
    assert result.local_final_approval_recorded is True
    assert result.real_final_approval_authorized is False
    assert result.publication_snapshot_authorized is False
    assert result.publication_authorized is False
    assert result.release_authorized is False
    assert result.production_authorized is False
    assert result.durable_transaction is False
    assert result.event_emitted is False
    assert result.formal_tst_012_status is ExternalGateStatus.NOT_EXECUTED
    assert result.formal_tst_021_status is ExternalGateStatus.NOT_EXECUTED
    assert result.canonical_bytes() == result.canonical_bytes()


def test_open_blocking_finding_rejects_without_waiver(
    step: RecordedFinalApprovalStep,
) -> None:
    original = step.request.finding_snapshot
    blocked = FinalApprovalFindingSnapshotV2(
        article_version_id=original.article_version_id,
        policy_report_sha256=original.policy_report_sha256,
        policy_finding_snapshot_sha256=(original.policy_finding_snapshot_sha256),
        captured_at=original.captured_at,
        open_blocking_finding_ids=(uuid7(940),),
    )
    assert_code(
        FinalApprovalFailureCode.BLOCKING_FINDING_PRESENT,
        lambda: request_with(step.request, finding_snapshot=blocked),
    )
    assert_code(
        FinalApprovalFailureCode.FINDING_SNAPSHOT_INVALID,
        lambda: replace(original, waiver_applied=True),
    )


@pytest.mark.parametrize("field", ["article_author_id", "last_editor_id"])
def test_author_and_last_editor_cannot_final_approve(
    step: RecordedFinalApprovalStep,
    field: str,
) -> None:
    request = (
        request_with(
            step.request,
            article_author_id=step.actor.principal_id,
        )
        if field == "article_author_id"
        else request_with(
            step.request,
            last_editor_id=step.actor.principal_id,
        )
    )
    authorization = RecordedFinalApprovalAuthorizationV2(
        request_sha256=request.request_sha256,
        actor=step.actor,
    )
    assert_code(
        FinalApprovalFailureCode.SELF_APPROVAL_FORBIDDEN,
        lambda: grant_final_approval_v2(
            request=request,
            authorization=authorization,
        ),
    )


def test_reviewer_cannot_be_final_approver(
    step: RecordedFinalApprovalStep,
) -> None:
    actor = replace(
        step.actor,
        principal_id=step.request.review_result.record.decided_by,
    )
    assert_code(
        FinalApprovalFailureCode.REVIEWER_APPROVER_SEPARATION_REQUIRED,
        lambda: grant_final_approval_v2(
            request=step.request,
            authorization=authorization_for(step, actor),
        ),
    )


@pytest.mark.parametrize(
    ("kind", "status"),
    [
        (RecordedSubjectKind.SERVICE, RecordedSubjectStatus.ACTIVE),
        (RecordedSubjectKind.HUMAN, RecordedSubjectStatus.INACTIVE),
    ],
)
def test_final_approver_must_be_active_human(
    step: RecordedFinalApprovalStep,
    kind: RecordedSubjectKind,
    status: RecordedSubjectStatus,
) -> None:
    actor = replace(step.actor, subject_kind=kind, subject_status=status)
    assert_code(
        FinalApprovalFailureCode.APPROVER_NOT_ACTIVE_HUMAN,
        lambda: grant_final_approval_v2(
            request=step.request,
            authorization=authorization_for(step, actor),
        ),
    )


def test_site_scope_and_step_up_freshness_are_fail_closed(
    step: RecordedFinalApprovalStep,
) -> None:
    other_site = replace(step.actor, site_id=SiteId(uuid7(941)))
    assert_code(
        FinalApprovalFailureCode.SITE_SCOPE_MISMATCH,
        lambda: grant_final_approval_v2(
            request=step.request,
            authorization=authorization_for(step, other_site),
        ),
    )
    stale = replace(
        step.actor,
        reauthenticated_at=UtcTimestamp(
            step.request.approved_at.value - timedelta(seconds=301)
        ),
    )
    assert_code(
        FinalApprovalFailureCode.STEP_UP_STALE,
        lambda: grant_final_approval_v2(
            request=step.request,
            authorization=authorization_for(step, stale),
        ),
    )
    future = replace(
        step.actor,
        reauthenticated_at=UtcTimestamp(
            step.request.approved_at.value + timedelta(seconds=1)
        ),
    )
    assert_code(
        FinalApprovalFailureCode.STEP_UP_STALE,
        lambda: grant_final_approval_v2(
            request=step.request,
            authorization=authorization_for(step, future),
        ),
    )


def test_nested_request_and_result_tamper_are_revalidated(
    step: RecordedFinalApprovalStep,
) -> None:
    object.__setattr__(
        step.request.gate_bundle,
        "gate_bundle_sha256",
        Sha256Digest("0" * 64),
    )
    assert_code(FinalApprovalFailureCode.OUTCOME_MISMATCH, step.request.require_valid)


def test_authorization_and_authority_tamper_are_revalidated(
    step: RecordedFinalApprovalStep,
) -> None:
    result = step.result
    object.__setattr__(result, "publication_authorized", True)
    assert_code(FinalApprovalFailureCode.OUTCOME_MISMATCH, result.require_valid)

    actor = step.actor
    object.__setattr__(actor, "role", "ADMIN")
    assert_code(
        FinalApprovalFailureCode.AUTHORIZATION_INVALID,
        step.authorization.require_valid,
    )


def test_idempotency_receipt_tamper_is_revalidated(
    step: RecordedFinalApprovalStep,
) -> None:
    object.__setattr__(
        step.result,
        "idempotency_receipt_sha256",
        Sha256Digest("0" * 64),
    )
    assert_code(FinalApprovalFailureCode.OUTCOME_MISMATCH, step.result.require_valid)


def test_principal_values_are_redacted_and_not_serializable(
    step: RecordedFinalApprovalStep,
) -> None:
    import pickle

    assert str(step.request) == "<redacted-st0902-v2>"
    assert "000000000926" not in repr(step.actor)
    with pytest.raises(TypeError):
        pickle.dumps(step.request)
    assert step.request.article_author_id == PrincipalId(uuid7(923))
