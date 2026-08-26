"""Synthetic, immutable builders for the isolated ST-0901 PR1 domain tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.domain.publishing.review_workflow import (  # noqa: E402
    HUMAN_REVIEW_CHECKLIST_IDS,
    HUMAN_REVIEW_CHECKLIST_SHA256,
    HUMAN_REVIEW_CHECKLIST_VERSION,
    ArticleVersionId,
    ChecklistItemId,
    ChecklistItemStatus,
    ChecklistResult,
    DecisionSummary,
    EvidenceId,
    EvidenceReference,
    PrincipalId,
    ReviewAssignment,
    ReviewAssignmentId,
    ReviewAssignmentState,
    ReviewDecisionDraft,
    ReviewDecisionId,
    ReviewDecisionKind,
    ReviewDecisionReference,
    ReviewType,
    Sha256Digest,
    UtcTimestamp,
    create_review_assignment,
    transition_review_assignment,
)


def uuid7(suffix: int) -> UUID:
    return UUID(f"018f3e90-7b00-7000-8000-{suffix:012d}")


ASSIGNMENT_ID = ReviewAssignmentId(uuid7(101))
ARTICLE_VERSION_ID = ArticleVersionId(uuid7(102))
ASSIGNED_BY = PrincipalId(uuid7(103))
ASSIGNED_TO = PrincipalId(uuid7(104))
DECISION_ID = ReviewDecisionId(uuid7(105))
CREATED_AT = UtcTimestamp(datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc))
STARTED_AT = UtcTimestamp(datetime(2026, 8, 12, 1, 0, tzinfo=timezone.utc))
FINISHED_AT = UtcTimestamp(datetime(2026, 8, 12, 2, 0, tzinfo=timezone.utc))


def assigned(*, priority: int = 50) -> ReviewAssignment:
    return create_review_assignment(
        assignment_id=ASSIGNMENT_ID,
        article_version_id=ARTICLE_VERSION_ID,
        review_type=ReviewType.EDITORIAL,
        assigned_by=ASSIGNED_BY,
        assigned_to=ASSIGNED_TO,
        priority=priority,
        created_at=CREATED_AT,
    )


def in_progress(*, priority: int = 50) -> ReviewAssignment:
    return transition_review_assignment(
        assigned(priority=priority),
        ReviewAssignmentState.IN_PROGRESS,
        STARTED_AT,
        None,
    )


def decision_reference(
    *,
    assignment_id: ReviewAssignmentId = ASSIGNMENT_ID,
    article_version_id: ArticleVersionId = ARTICLE_VERSION_ID,
) -> ReviewDecisionReference:
    return ReviewDecisionReference(
        DECISION_ID,
        assignment_id,
        article_version_id,
    )


def evidence(
    suffix: int,
    *,
    assignment_id: ReviewAssignmentId = ASSIGNMENT_ID,
    article_version_id: ArticleVersionId = ARTICLE_VERSION_ID,
) -> EvidenceReference:
    return EvidenceReference(
        EvidenceId(uuid7(1_000 + suffix)),
        Sha256Digest(f"{suffix:064x}"),
        assignment_id,
        article_version_id,
    )


def pass_results() -> tuple[ChecklistResult, ...]:
    return tuple(
        ChecklistResult(
            ChecklistItemId(item_id),
            ChecklistItemStatus.PASS,
            (),
            None,
        )
        for item_id in HUMAN_REVIEW_CHECKLIST_IDS
    )


def replace_result(
    results: tuple[ChecklistResult, ...],
    index: int,
    replacement: ChecklistResult,
) -> tuple[ChecklistResult, ...]:
    return results[:index] + (replacement,) + results[index + 1 :]


def draft(
    *,
    decision: ReviewDecisionKind = ReviewDecisionKind.CHANGES_REQUESTED,
    results: tuple[ChecklistResult, ...] | None = None,
    assignment_id: ReviewAssignmentId = ASSIGNMENT_ID,
    article_version_id: ArticleVersionId = ARTICLE_VERSION_ID,
    version: str = HUMAN_REVIEW_CHECKLIST_VERSION,
    sha256: str = HUMAN_REVIEW_CHECKLIST_SHA256,
) -> ReviewDecisionDraft:
    return ReviewDecisionDraft(
        assignment_id,
        article_version_id,
        decision,
        DecisionSummary("Human reviewer requests the documented changes."),
        version,
        sha256,
        pass_results() if results is None else results,
    )
