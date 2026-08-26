from __future__ import annotations

from dataclasses import replace
from collections.abc import Callable
from uuid import UUID

import pytest

from raos.adapters.recorded_review_completion import RecordedReviewCompletionStep
from raos.domain.editorial.policy_engine_v2 import (
    PolicyEvaluationRecordReceiptV2,
    unavailable_policy_report,
)
from raos.domain.publishing.review_completion_v2 import (
    ExternalGateStatus,
    ReviewCompletionFailure,
    ReviewCompletionFailureCode,
    ReviewCompletionRequestV2,
    assignment_sha256,
    complete_review_workflow_v2,
    policy_finding_snapshot_sha256,
    policy_receipt_sha256,
    validate_review_decision_v2,
)
from raos.domain.publishing.review_decision_operations import (
    RecordedIdentityProjection,
    RecordedSubjectKind,
    RecordedSubjectStatus,
)
from raos.domain.publishing.review_workflow import (
    ArticleVersionId,
    PrincipalId,
    ReviewAssignment,
    ReviewAssignmentState,
    ReviewDecisionId,
    ReviewDecisionKind,
)
from raos.domain.shared.persistence import Sha256Digest

from .support import request_with


def uuid7(suffix: int) -> UUID:
    return UUID(f"018f3e90-7b00-7000-8000-{suffix:012d}")


def assert_code(
    code: ReviewCompletionFailureCode,
    call: Callable[[], object],
) -> None:
    with pytest.raises(ReviewCompletionFailure) as captured:
        call()
    assert captured.value.code is code
    assert str(captured.value) == code.value
    assert "Recorded local" not in repr(captured.value)


def test_clear_policy_and_all_pass_enable_review_level_approve(
    step: RecordedReviewCompletionStep,
) -> None:
    request = step.request
    validated = validate_review_decision_v2(
        assignment=request.assignment,
        draft=request.draft,
        policy_report=request.policy_report,
        policy_receipt=request.policy_receipt,
    )

    assert validated.decision is ReviewDecisionKind.APPROVE
    assert validated.policy_report_sha256 == request.policy_report.report_sha256
    assert validated.policy_receipt_sha256 == policy_receipt_sha256(
        request.policy_receipt
    )
    assert validated.finding_snapshot_sha256 == policy_finding_snapshot_sha256(
        request.policy_report
    )
    assert all(item.status.value == "PASS" for item in validated.checklist_results)
    assert validated.canonical_bytes() == validated.canonical_bytes()


def test_completion_records_immutable_decision_and_completes_assignment(
    step: RecordedReviewCompletionStep,
) -> None:
    result = complete_review_workflow_v2(
        request=step.request,
        authorization=step.authorization,
    )

    assert result.completed_assignment.status is ReviewAssignmentState.COMPLETED
    reference = result.completed_assignment.completion_decision_reference
    assert reference is not None
    assert reference.decision_id == result.record.decision_id
    assert result.record.decided_by == step.request.assignment.assigned_to
    assert result.source_assignment_sha256 == assignment_sha256(step.request.assignment)
    assert result.audit.record_sha256 == result.record.record_sha256
    assert result.review_decision_recorded is True
    assert result.assignment_completed is True
    assert result.final_approval_authorized is False
    assert result.publication_snapshot_authorized is False
    assert result.publication_authorized is False
    assert result.release_authorized is False
    assert result.production_authorized is False
    assert result.formal_tst_011_status is ExternalGateStatus.NOT_EXECUTED
    assert result.formal_tst_012_status is ExternalGateStatus.NOT_EXECUTED
    assert result.formal_tst_020_status is ExternalGateStatus.NOT_EXECUTED
    assert result.canonical_bytes() == result.canonical_bytes()


def test_approve_refuses_any_failed_checklist_item(
    step: RecordedReviewCompletionStep,
) -> None:
    assert_code(
        ReviewCompletionFailureCode.APPROVE_CHECKLIST_NOT_CLEAR,
        lambda: request_with(
            step.request,
            checklist_status=step.request.draft.checklist_results[0].status.FAIL,
        ),
    )


def test_not_applicable_remains_fail_closed_without_canonical_mapping(
    step: RecordedReviewCompletionStep,
) -> None:
    from raos.domain.publishing.review_workflow import ChecklistItemStatus

    assert_code(
        ReviewCompletionFailureCode.CHECKLIST_APPLICABILITY_UNRESOLVED,
        lambda: request_with(
            step.request,
            checklist_status=ChecklistItemStatus.NOT_APPLICABLE_WITH_REASON,
        ),
    )


def test_negative_review_decision_can_complete_with_a_failed_item(
    step: RecordedReviewCompletionStep,
) -> None:
    from raos.domain.publishing.review_workflow import ChecklistItemStatus

    request = request_with(
        step.request,
        decision=ReviewDecisionKind.CHANGES_REQUESTED,
        checklist_status=ChecklistItemStatus.FAIL,
        decision_id=ReviewDecisionId(uuid7(920)),
    )
    authorization = replace(
        step.authorization,
        request_sha256=request.request_sha256,
    )
    result = complete_review_workflow_v2(
        request=request,
        authorization=authorization,
    )
    assert result.record.decision.decision is ReviewDecisionKind.CHANGES_REQUESTED
    assert result.completed_assignment.status is ReviewAssignmentState.COMPLETED
    assert result.final_approval_authorized is False


def test_policy_receipt_hash_mismatch_is_rejected(
    step: RecordedReviewCompletionStep,
) -> None:
    request = step.request
    receipt = PolicyEvaluationRecordReceiptV2(
        sequence=1,
        report_sha256=Sha256Digest("0" * 64),
    )
    assert_code(
        ReviewCompletionFailureCode.POLICY_BINDING_MISMATCH,
        lambda: ReviewCompletionRequestV2(
            assignment=request.assignment,
            draft=request.draft,
            policy_report=request.policy_report,
            policy_receipt=receipt,
            decision_id=request.decision_id,
            decided_at=request.decided_at,
            audit_event_id=request.audit_event_id,
            idempotency_key=request.idempotency_key,
        ),
    )


def test_unbound_unavailable_policy_report_is_rejected(
    step: RecordedReviewCompletionStep,
) -> None:
    request = step.request
    report = unavailable_policy_report()
    receipt = PolicyEvaluationRecordReceiptV2(
        sequence=1,
        report_sha256=report.report_sha256,
    )
    assert_code(
        ReviewCompletionFailureCode.POLICY_BINDING_MISMATCH,
        lambda: validate_review_decision_v2(
            assignment=request.assignment,
            draft=request.draft,
            policy_report=report,
            policy_receipt=receipt,
        ),
    )


def test_cross_article_assignment_is_rejected(
    step: RecordedReviewCompletionStep,
) -> None:
    request = step.request
    assignment = ReviewAssignment(
        assignment_id=request.assignment.assignment_id,
        article_version_id=ArticleVersionId(uuid7(921)),
        review_type=request.assignment.review_type,
        assigned_by=request.assignment.assigned_by,
        assigned_to=request.assignment.assigned_to,
        priority=request.assignment.priority,
        status=request.assignment.status,
        started_at=request.assignment.started_at,
        completed_at=request.assignment.completed_at,
        cancelled_at=request.assignment.cancelled_at,
        created_at=request.assignment.created_at,
        updated_at=request.assignment.updated_at,
        lock_version=request.assignment.lock_version,
        completion_decision_reference=None,
    )
    draft = replace(request.draft, article_version_id=assignment.article_version_id)
    assert_code(
        ReviewCompletionFailureCode.POLICY_BINDING_MISMATCH,
        lambda: validate_review_decision_v2(
            assignment=assignment,
            draft=draft,
            policy_report=request.policy_report,
            policy_receipt=request.policy_receipt,
        ),
    )


@pytest.mark.parametrize(
    ("kind", "status", "code"),
    [
        (
            RecordedSubjectKind.SERVICE,
            RecordedSubjectStatus.ACTIVE,
            ReviewCompletionFailureCode.REVIEWER_NOT_ACTIVE_HUMAN,
        ),
        (
            RecordedSubjectKind.HUMAN,
            RecordedSubjectStatus.INACTIVE,
            ReviewCompletionFailureCode.REVIEWER_NOT_ACTIVE_HUMAN,
        ),
    ],
)
def test_non_active_human_reviewer_is_rejected(
    step: RecordedReviewCompletionStep,
    kind: RecordedSubjectKind,
    status: RecordedSubjectStatus,
    code: ReviewCompletionFailureCode,
) -> None:
    actor = RecordedIdentityProjection(
        principal_id=step.request.assignment.assigned_to,
        subject_kind=kind,
        subject_status=status,
    )
    authorization = replace(step.authorization, actor=actor)
    assert_code(
        code,
        lambda: complete_review_workflow_v2(
            request=step.request,
            authorization=authorization,
        ),
    )


def test_other_human_reviewer_is_rejected(
    step: RecordedReviewCompletionStep,
) -> None:
    actor = RecordedIdentityProjection(
        principal_id=PrincipalId(uuid7(922)),
        subject_kind=RecordedSubjectKind.HUMAN,
        subject_status=RecordedSubjectStatus.ACTIVE,
    )
    authorization = replace(step.authorization, actor=actor)
    assert_code(
        ReviewCompletionFailureCode.REVIEWER_ASSIGNMENT_MISMATCH,
        lambda: complete_review_workflow_v2(
            request=step.request,
            authorization=authorization,
        ),
    )


def test_nested_tamper_is_revalidated(step: RecordedReviewCompletionStep) -> None:
    request = step.request
    object.__setattr__(request, "request_sha256", Sha256Digest("0" * 64))
    assert_code(ReviewCompletionFailureCode.OUTCOME_MISMATCH, request.require_valid)


def test_result_tamper_is_revalidated(step: RecordedReviewCompletionStep) -> None:
    result = step.result
    object.__setattr__(result, "publication_authorized", True)
    assert_code(ReviewCompletionFailureCode.OUTCOME_MISMATCH, result.require_valid)
