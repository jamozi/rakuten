"""Structural review-decision validation behavior and fail-closed gates."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Protocol, cast
from uuid import UUID

import pytest

from .support import (
    ARTICLE_VERSION_ID,
    ASSIGNMENT_ID,
    assigned,
    draft,
    evidence,
    in_progress,
    pass_results,
    replace_result,
    uuid7,
)
from raos.domain.publishing.review_workflow import (
    HUMAN_REVIEW_CHECKLIST_IDS,
    ArticleVersionId,
    ChecklistItemId,
    ChecklistItemStatus,
    ChecklistResult,
    EvidenceId,
    HumanComment,
    ReviewAssignment,
    ReviewAssignmentState,
    ReviewAssignmentId,
    ReviewDecisionDraft,
    ReviewDecisionKind,
    ReviewType,
    ReviewWorkflowFailure,
    ReviewWorkflowFailureCode,
    Sha256Digest,
    StructurallyValidatedReviewDecision,
    validate_review_decision,
)


@pytest.mark.parametrize(
    "decision",
    (ReviewDecisionKind.CHANGES_REQUESTED, ReviewDecisionKind.REJECT),
)
def test_complete_pass_checklist_is_structurally_valid_for_nonapproval_decisions(
    decision: ReviewDecisionKind,
) -> None:
    value = draft(decision=decision)

    result = validate_review_decision(in_progress(), value)

    assert result.decision is decision
    assert result.review_assignment_id == ASSIGNMENT_ID
    assert result.article_version_id == ARTICLE_VERSION_ID
    assert tuple(item.item_id.value for item in result.checklist_results) == (
        HUMAN_REVIEW_CHECKLIST_IDS
    )
    assert all(
        item.status is ChecklistItemStatus.PASS for item in result.checklist_results
    )
    assert value.checklist_results == pass_results()


def test_fail_accepts_evidence_or_nonempty_human_comment() -> None:
    evidence_failure = ChecklistResult(
        ChecklistItemId("REV-001"),
        ChecklistItemStatus.FAIL,
        (evidence(1),),
        None,
    )
    comment_failure = ChecklistResult(
        ChecklistItemId("REV-002"),
        ChecklistItemStatus.FAIL,
        (),
        HumanComment("The source conflict requires a human-authored correction."),
    )
    results = replace_result(pass_results(), 0, evidence_failure)
    results = replace_result(results, 1, comment_failure)

    validated = validate_review_decision(in_progress(), draft(results=results))

    assert validated.checklist_results[0] == evidence_failure
    assert validated.checklist_results[1] == comment_failure


def test_fail_without_evidence_or_comment_is_rejected() -> None:
    with pytest.raises(ReviewWorkflowFailure) as captured:
        ChecklistResult(
            ChecklistItemId("REV-001"),
            ChecklistItemStatus.FAIL,
            (),
            None,
        )

    assert (
        captured.value.code
        is ReviewWorkflowFailureCode.CHECKLIST_FAIL_JUSTIFICATION_REQUIRED
    )


def test_any_not_applicable_result_fails_closed_even_with_reason() -> None:
    not_applicable = ChecklistResult(
        ChecklistItemId("REV-075"),
        ChecklistItemStatus.NOT_APPLICABLE_WITH_REASON,
        (),
        HumanComment("Human supplied reason that cannot prove applicability."),
    )
    results = replace_result(pass_results(), 74, not_applicable)

    with pytest.raises(ReviewWorkflowFailure) as captured:
        validate_review_decision(in_progress(), draft(results=results))

    assert (
        captured.value.code
        is ReviewWorkflowFailureCode.CHECKLIST_APPLICABILITY_UNRESOLVED
    )


@pytest.mark.parametrize(
    ("assignment", "value"),
    (
        (in_progress(), draft(decision=ReviewDecisionKind.APPROVE)),
        (
            in_progress(),
            draft(decision=ReviewDecisionKind.APPROVE, version="1.0.1"),
        ),
        (
            in_progress(),
            replace(
                draft(decision=ReviewDecisionKind.APPROVE),
                checklist_results=pass_results()[:-1],
            ),
        ),
        (
            assigned(),
            draft(decision=ReviewDecisionKind.APPROVE),
        ),
    ),
)
def test_approve_always_fails_closed_with_stable_gate_code(
    assignment: ReviewAssignment,
    value: ReviewDecisionDraft,
) -> None:
    with pytest.raises(ReviewWorkflowFailure) as captured:
        validate_review_decision(assignment, value)

    assert captured.value.code is ReviewWorkflowFailureCode.APPROVE_GATE_UNRESOLVED


def test_approve_gate_requires_exact_draft_and_decision_types_first() -> None:
    value = draft(decision=ReviewDecisionKind.APPROVE)
    object.__setattr__(value, "decision", "APPROVE")
    with pytest.raises(ReviewWorkflowFailure) as raw_decision:
        validate_review_decision(assigned(), value)
    assert raw_decision.value.code is ReviewWorkflowFailureCode.VOCABULARY_INVALID

    clean = draft(decision=ReviewDecisionKind.APPROVE)

    class DraftSubclass(ReviewDecisionDraft):
        pass

    subclass = DraftSubclass(
        clean.review_assignment_id,
        clean.article_version_id,
        clean.decision,
        clean.summary,
        clean.checklist_version,
        clean.checklist_sha256,
        clean.checklist_results,
    )
    with pytest.raises(ReviewWorkflowFailure) as subclass_draft:
        validate_review_decision(assigned(), subclass)
    assert subclass_draft.value.code is ReviewWorkflowFailureCode.INVALID_ARGUMENT


@pytest.mark.parametrize(
    ("mutator", "code"),
    (
        (
            lambda value: replace(value, checklist_version="1.0.1"),
            ReviewWorkflowFailureCode.CHECKLIST_VERSION_MISMATCH,
        ),
        (
            lambda value: replace(value, checklist_sha256="0" * 64),
            ReviewWorkflowFailureCode.CHECKLIST_HASH_MISMATCH,
        ),
        (
            lambda value: replace(
                value, checklist_results=value.checklist_results[:-1]
            ),
            ReviewWorkflowFailureCode.CHECKLIST_MEMBERSHIP_INVALID,
        ),
        (
            lambda value: replace(
                value,
                checklist_results=value.checklist_results[:-1]
                + (value.checklist_results[0],),
            ),
            ReviewWorkflowFailureCode.CHECKLIST_ITEM_DUPLICATE,
        ),
        (
            lambda value: replace(
                value,
                checklist_results=replace_result(
                    value.checklist_results,
                    0,
                    replace(
                        value.checklist_results[0],
                        item_id=ChecklistItemId("REV-999"),
                    ),
                ),
            ),
            ReviewWorkflowFailureCode.CHECKLIST_MEMBERSHIP_INVALID,
        ),
    ),
)
def test_contract_version_hash_and_exact_once_membership_mutations_fail(
    mutator: Callable[[object], object],
    code: ReviewWorkflowFailureCode,
) -> None:
    with pytest.raises(ReviewWorkflowFailure) as captured:
        validate_review_decision(
            in_progress(),
            cast("ReviewDecisionDraft", mutator(draft())),
        )
    assert captured.value.code is code


def test_evidence_must_bind_to_same_assignment_and_article_version() -> None:
    other_assignment = ReviewAssignmentId(uuid7(201))
    other_article = ArticleVersionId(uuid7(202))
    cases = (
        (
            evidence(2, assignment_id=other_assignment),
            ReviewWorkflowFailureCode.ASSIGNMENT_BINDING_MISMATCH,
        ),
        (
            evidence(3, article_version_id=other_article),
            ReviewWorkflowFailureCode.ARTICLE_VERSION_BINDING_MISMATCH,
        ),
    )
    for reference, expected_code in cases:
        failure = ChecklistResult(
            ChecklistItemId("REV-001"),
            ChecklistItemStatus.FAIL,
            (reference,),
            None,
        )
        with pytest.raises(ReviewWorkflowFailure) as captured:
            validate_review_decision(
                in_progress(),
                draft(results=replace_result(pass_results(), 0, failure)),
            )
        assert captured.value.code is expected_code


def test_draft_must_bind_to_same_assignment_and_article_version() -> None:
    cases = (
        (
            draft(assignment_id=ReviewAssignmentId(uuid7(301))),
            ReviewWorkflowFailureCode.ASSIGNMENT_BINDING_MISMATCH,
        ),
        (
            draft(article_version_id=ArticleVersionId(uuid7(302))),
            ReviewWorkflowFailureCode.ARTICLE_VERSION_BINDING_MISMATCH,
        ),
    )
    for value, expected_code in cases:
        with pytest.raises(ReviewWorkflowFailure) as captured:
            validate_review_decision(in_progress(), value)
        assert captured.value.code is expected_code


def test_validation_is_deterministic_under_checklist_and_evidence_permutations() -> (
    None
):
    first_evidence = evidence(5)
    second_evidence = evidence(4)
    failure_forward = ChecklistResult(
        ChecklistItemId("REV-001"),
        ChecklistItemStatus.FAIL,
        (first_evidence, second_evidence),
        None,
    )
    failure_reverse = ChecklistResult(
        ChecklistItemId("REV-001"),
        ChecklistItemStatus.FAIL,
        (second_evidence, first_evidence),
        None,
    )
    forward = replace_result(pass_results(), 0, failure_forward)
    reverse = tuple(reversed(replace_result(pass_results(), 0, failure_reverse)))

    first = validate_review_decision(in_progress(), draft(results=forward))
    second = validate_review_decision(in_progress(), draft(results=reverse))

    assert first == second
    assert tuple(item.item_id.value for item in second.checklist_results) == (
        HUMAN_REVIEW_CHECKLIST_IDS
    )
    assert tuple(
        reference.evidence_id.value.int
        for reference in second.checklist_results[0].evidence
    ) == tuple(
        sorted(
            (
                first_evidence.evidence_id.value.int,
                second_evidence.evidence_id.value.int,
            )
        )
    )


def test_decision_and_status_vocabularies_reject_lowercase_unknown_and_ed030() -> None:
    for token in (
        "approve",
        "request_changes",
        "reject",
        "pause",
        "ED-030",
        "UNKNOWN",
        "REJECTED_DECISION_CANARY",
    ):
        with pytest.raises(ReviewWorkflowFailure) as captured:
            ReviewDecisionKind(token)
        assert captured.value.code is ReviewWorkflowFailureCode.VOCABULARY_INVALID
        assert (
            token
            not in f"{captured.value!s} {captured.value!r} {captured.value.args!r}"
        )


def _exception_graph(root: BaseException) -> tuple[BaseException, ...]:
    pending: list[BaseException] = [root]
    observed: list[BaseException] = []
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        observed.append(current)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return tuple(observed)


class _ClosedEnumConstructor(Protocol):
    def __call__(self, value: str) -> object: ...

    def __getitem__(self, name: str) -> object: ...


@pytest.mark.parametrize(
    "constructor",
    (
        ReviewDecisionKind,
        ChecklistItemStatus,
        ReviewType,
        ReviewAssignmentState,
        ReviewWorkflowFailureCode,
    ),
)
def test_closed_enum_rejection_retains_no_raw_value_anywhere_in_exception_graph(
    constructor: _ClosedEnumConstructor,
) -> None:
    canary = "ST0901_SECRET_ENUM_CANARY"

    with pytest.raises(ReviewWorkflowFailure) as captured:
        constructor(canary)

    assert captured.value.code is ReviewWorkflowFailureCode.VOCABULARY_INVALID
    graph = _exception_graph(captured.value)
    assert graph == (captured.value,)
    assert all(canary not in f"{error!s} {error!r} {error.args!r}" for error in graph)

    with pytest.raises(ReviewWorkflowFailure) as name_lookup:
        constructor[canary]

    assert name_lookup.value.code is ReviewWorkflowFailureCode.VOCABULARY_INVALID
    name_lookup_graph = _exception_graph(name_lookup.value)
    assert name_lookup_graph == (name_lookup.value,)
    assert all(
        canary not in f"{error!s} {error!r} {error.args!r}"
        for error in name_lookup_graph
    )
    for token in (
        "pass",
        "NOT_APPLICABLE",
        "UNKNOWN",
        "REJECTED_CHECKLIST_STATUS_CANARY",
    ):
        with pytest.raises(ReviewWorkflowFailure) as captured:
            ChecklistItemStatus(token)
        assert captured.value.code is ReviewWorkflowFailureCode.VOCABULARY_INVALID
        assert (
            token
            not in f"{captured.value!s} {captured.value!r} {captured.value.args!r}"
        )


def test_evidence_id_and_hash_shapes_are_strict() -> None:
    with pytest.raises(ReviewWorkflowFailure):
        EvidenceId(UUID("00000000-0000-4000-8000-000000000001"))
    for digest in ("A" * 64, "0" * 63, "0" * 65, "not-a-hash"):
        with pytest.raises(ReviewWorkflowFailure):
            Sha256Digest(digest)


def test_duplicate_evidence_ids_are_rejected_even_when_hashes_differ() -> None:
    first = evidence(20)
    duplicate_id = replace(first, sha256=Sha256Digest("f" * 64))

    with pytest.raises(ReviewWorkflowFailure) as captured:
        ChecklistResult(
            ChecklistItemId("REV-001"),
            ChecklistItemStatus.FAIL,
            (first, duplicate_id),
            None,
        )

    assert captured.value.code is ReviewWorkflowFailureCode.CHECKLIST_EVIDENCE_INVALID


def test_validated_result_direct_constructor_rejects_raw_str_and_str_subclasses() -> (
    None
):
    valid = validate_review_decision(in_progress(), draft())

    class StringSubclass(str):
        pass

    cases = (
        ("decision", "CHANGES_REQUESTED", ReviewWorkflowFailureCode.VOCABULARY_INVALID),
        (
            "checklist_version",
            StringSubclass(valid.checklist_version),
            ReviewWorkflowFailureCode.CHECKLIST_VERSION_MISMATCH,
        ),
        (
            "checklist_sha256",
            StringSubclass(valid.checklist_sha256),
            ReviewWorkflowFailureCode.CHECKLIST_HASH_MISMATCH,
        ),
    )
    for field, value, expected_code in cases:
        decision = valid.decision
        version = valid.checklist_version
        sha256 = valid.checklist_sha256
        if field == "decision":
            decision = cast("ReviewDecisionKind", value)
        elif field == "checklist_version":
            version = value
        else:
            sha256 = value
        with pytest.raises(ReviewWorkflowFailure) as captured:
            StructurallyValidatedReviewDecision(
                valid.review_assignment_id,
                valid.article_version_id,
                decision,
                valid.summary,
                version,
                sha256,
                valid.checklist_results,
            )
        assert captured.value.code is expected_code
