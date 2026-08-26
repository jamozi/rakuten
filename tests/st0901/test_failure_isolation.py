"""Strict type, tamper revalidation, and redaction regressions for PR1."""

from __future__ import annotations

import pickle
from typing import Callable, cast

import pytest

from .support import (
    ASSIGNMENT_ID,
    FINISHED_AT,
    STARTED_AT,
    assigned,
    decision_reference,
    draft,
    evidence,
    in_progress,
    pass_results,
)
from raos.domain.publishing.review_workflow import (
    HUMAN_REVIEW_CHECKLIST_SHA256,
    ChecklistCatalogItem,
    ChecklistItemId,
    ChecklistItemStatus,
    ChecklistResult,
    DecisionSummary,
    EvidenceReference,
    HumanComment,
    ReviewAssignmentState,
    ReviewDecisionDraft,
    ReviewDecisionKind,
    ReviewWorkflowFailure,
    ReviewWorkflowFailureCode,
    Sha256Digest,
    StructurallyValidatedReviewDecision,
    transition_review_assignment,
    validate_review_decision,
)


REJECTED_CANARY = "REJECTED_ST0901_SUMMARY_COMMENT_EVIDENCE_CANARY"


def test_raw_human_text_and_evidence_locator_never_appear_in_repr_or_exception() -> (
    None
):
    values = (
        DecisionSummary(REJECTED_CANARY),
        HumanComment(REJECTED_CANARY),
        evidence(77),
        ChecklistResult(
            ChecklistItemId("REV-001"),
            ChecklistItemStatus.FAIL,
            (),
            HumanComment(REJECTED_CANARY),
        ),
    )
    for value in values:
        rendered = f"{value!r} {value!s}"
        assert REJECTED_CANARY not in rendered
        assert "018f" not in rendered
        assert "<redacted>" in rendered

    with pytest.raises(ReviewWorkflowFailure) as captured:
        DecisionSummary(f" {REJECTED_CANARY} ")
    error = captured.value
    rendered_error = f"{error!r} {error!s} {error.args!r}"
    assert REJECTED_CANARY not in rendered_error
    assert error.code is ReviewWorkflowFailureCode.DECISION_SUMMARY_INVALID


@pytest.mark.parametrize(
    "value",
    (
        assigned,
        in_progress,
        draft,
        decision_reference,
        lambda: validate_review_decision(in_progress(), draft()),
        lambda: ReviewWorkflowFailure(ReviewWorkflowFailureCode.INVALID_ARGUMENT),
    ),
)
def test_sensitive_domain_values_and_failures_are_not_pickleable(
    value: Callable[[], object],
) -> None:
    built = value()
    with pytest.raises(TypeError):
        pickle.dumps(built)


def test_mutable_collections_are_rejected_without_coercion() -> None:
    valid = draft()
    with pytest.raises(ReviewWorkflowFailure):
        ReviewDecisionDraft(
            valid.review_assignment_id,
            valid.article_version_id,
            valid.decision,
            valid.summary,
            valid.checklist_version,
            valid.checklist_sha256,
            cast("tuple[ChecklistResult, ...]", list(valid.checklist_results)),
        )
    with pytest.raises(ReviewWorkflowFailure):
        ChecklistResult(
            ChecklistItemId("REV-001"),
            ChecklistItemStatus.PASS,
            cast("tuple[EvidenceReference, ...]", [evidence(1)]),
            None,
        )


def test_plain_scalar_subclasses_are_rejected_where_runtime_identity_matters() -> None:
    class StringSubclass(str):
        pass

    class IntegerSubclass(int):
        pass

    with pytest.raises(ReviewWorkflowFailure):
        ChecklistItemId(StringSubclass("REV-001"))
    with pytest.raises(ReviewWorkflowFailure):
        Sha256Digest(StringSubclass("0" * 64))
    with pytest.raises(ReviewWorkflowFailure):
        assigned(priority=IntegerSubclass(50))


def test_nested_object_tampering_is_revalidated_before_transition_or_validation() -> (
    None
):
    assignment = in_progress()
    object.__setattr__(assignment, "article_version_id", ASSIGNMENT_ID)
    with pytest.raises(ReviewWorkflowFailure):
        validate_review_decision(assignment, draft())

    clean = in_progress()
    object.__setattr__(clean, "lock_version", True)
    with pytest.raises(ReviewWorkflowFailure) as captured:
        transition_review_assignment(
            clean,
            ReviewAssignmentState.CANCELLED,
            FINISHED_AT,
            None,
        )
    assert captured.value.code is ReviewWorkflowFailureCode.LOCK_VERSION_INVALID


def test_tampered_checklist_result_is_revalidated_before_decision() -> None:
    results = pass_results()
    object.__setattr__(results[0], "status", "PASS")
    with pytest.raises(ReviewWorkflowFailure) as captured:
        ReviewDecisionDraft(
            draft().review_assignment_id,
            draft().article_version_id,
            ReviewDecisionKind.CHANGES_REQUESTED,
            DecisionSummary("A bounded human summary."),
            "1.0.0",
            HUMAN_REVIEW_CHECKLIST_SHA256,
            results,
        )
    assert captured.value.code is ReviewWorkflowFailureCode.CHECKLIST_STATUS_INVALID


def test_public_validated_result_revalidates_nested_tampering() -> None:
    valid = validate_review_decision(in_progress(), draft())
    object.__setattr__(
        valid.checklist_results[0], "item_id", ChecklistItemId("REV-999")
    )
    with pytest.raises(ReviewWorkflowFailure):
        StructurallyValidatedReviewDecision(
            valid.review_assignment_id,
            valid.article_version_id,
            valid.decision,
            valid.summary,
            valid.checklist_version,
            valid.checklist_sha256,
            valid.checklist_results,
        )


def test_direct_draft_and_validated_result_detach_rebuilt_nested_values() -> None:
    source_results = pass_results()
    direct_draft = ReviewDecisionDraft(
        draft().review_assignment_id,
        draft().article_version_id,
        ReviewDecisionKind.CHANGES_REQUESTED,
        DecisionSummary("A bounded human summary."),
        "1.0.0",
        HUMAN_REVIEW_CHECKLIST_SHA256,
        source_results,
    )
    direct_result = StructurallyValidatedReviewDecision(
        direct_draft.review_assignment_id,
        direct_draft.article_version_id,
        direct_draft.decision,
        direct_draft.summary,
        direct_draft.checklist_version,
        direct_draft.checklist_sha256,
        direct_draft.checklist_results,
    )

    assert direct_draft.checklist_results == source_results
    assert direct_draft.checklist_results is not source_results
    assert all(
        rebuilt is not source
        for rebuilt, source in zip(
            direct_draft.checklist_results,
            source_results,
            strict=True,
        )
    )
    assert direct_result.checklist_results == direct_draft.checklist_results
    assert direct_result.checklist_results is not direct_draft.checklist_results


def test_direct_validated_result_rebuilds_tampered_nested_evidence_order() -> None:
    source = ChecklistResult(
        ChecklistItemId("REV-001"),
        ChecklistItemStatus.PASS,
        (evidence(31), evidence(32)),
        None,
    )
    object.__setattr__(source, "evidence", tuple(reversed(source.evidence)))
    source_results = (source,) + pass_results()[1:]
    template = draft()

    result = StructurallyValidatedReviewDecision(
        template.review_assignment_id,
        template.article_version_id,
        template.decision,
        template.summary,
        template.checklist_version,
        template.checklist_sha256,
        source_results,
    )

    assert result.checklist_results[0] is not source
    assert tuple(
        reference.evidence_id.value.int
        for reference in result.checklist_results[0].evidence
    ) == tuple(sorted(reference.evidence_id.value.int for reference in source.evidence))
    assert result.checklist_results[0].evidence != source.evidence


def test_summary_and_comment_are_nonempty_bounded_utf8_without_control_chars() -> None:
    invalid_values = ("", " leading", "trailing ", "line\nbreak", "x" * 8_001)
    for value in invalid_values:
        with pytest.raises(ReviewWorkflowFailure):
            DecisionSummary(value)
        with pytest.raises(ReviewWorkflowFailure):
            HumanComment(value)


@pytest.mark.parametrize(
    "constructor",
    (
        DecisionSummary,
        HumanComment,
        lambda value: ChecklistCatalogItem("REV-001", value, "check"),
        lambda value: ChecklistCatalogItem("REV-001", "section", value),
    ),
)
def test_invalid_utf8_text_is_absent_from_entire_exception_chain(
    constructor: Callable[[str], object],
) -> None:
    canary = "ST0901_SECRET_TEXT_CANARY\ud800"

    with pytest.raises(ReviewWorkflowFailure) as captured:
        constructor(canary)

    error = captured.value
    assert error.__cause__ is None
    assert error.__context__ is None
    assert "ST0901_SECRET_TEXT_CANARY" not in f"{error!s} {error!r} {error.args!r}"


def test_validated_decision_does_not_create_decision_id_history_or_effectiveness() -> (
    None
):
    result = validate_review_decision(in_progress(), draft())
    assert not hasattr(result, "decision_id")
    assert not hasattr(result, "supersedes_decision_id")
    assert not hasattr(result, "effective_decision")
    assert not hasattr(result, "persisted")


def test_result_type_rejects_approve_even_through_direct_constructor() -> None:
    value = validate_review_decision(in_progress(), draft())
    with pytest.raises(ReviewWorkflowFailure) as captured:
        StructurallyValidatedReviewDecision(
            value.review_assignment_id,
            value.article_version_id,
            ReviewDecisionKind.APPROVE,
            value.summary,
            value.checklist_version,
            value.checklist_sha256,
            value.checklist_results,
        )
    assert captured.value.code is ReviewWorkflowFailureCode.APPROVE_GATE_UNRESOLVED


def test_no_partial_transition_result_is_returned_on_failure() -> None:
    initial = assigned()
    before = (
        initial.status,
        initial.started_at,
        initial.updated_at,
        initial.lock_version,
    )
    with pytest.raises(ReviewWorkflowFailure):
        transition_review_assignment(
            initial,
            ReviewAssignmentState.COMPLETED,
            STARTED_AT,
            decision_reference(),
        )
    assert (
        initial.status,
        initial.started_at,
        initial.updated_at,
        initial.lock_version,
    ) == before
