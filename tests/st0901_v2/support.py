from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from raos.adapters.recorded_review_completion import (
    RecordedReviewCompletionStep,
    load_recorded_review_completion_fixture,
)
from raos.domain.publishing.review_completion_v2 import ReviewCompletionRequestV2
from raos.domain.publishing.review_workflow import (
    ChecklistItemStatus,
    ChecklistResult,
    HumanComment,
    ReviewDecisionDraft,
    ReviewDecisionId,
    ReviewDecisionKind,
)
from raos.adapters.recorded_review_completion_fixture_v2 import (
    REVIEW_COMPLETION_PASS_V2_JSON,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_FIXTURE_PATH = REPO_ROOT / "changes/st-0805/generated/policy-pass.v2.json"


@pytest.fixture
def policy_fixture() -> bytes:
    return POLICY_FIXTURE_PATH.read_bytes()


@pytest.fixture
def fixture_bytes() -> bytes:
    return REVIEW_COMPLETION_PASS_V2_JSON


@pytest.fixture
def step(fixture_bytes: bytes, policy_fixture: bytes) -> RecordedReviewCompletionStep:
    return load_recorded_review_completion_fixture(
        fixture_bytes,
        policy_fixture=policy_fixture,
    )


def request_with(
    request: ReviewCompletionRequestV2,
    *,
    decision: ReviewDecisionKind | None = None,
    checklist_status: ChecklistItemStatus | None = None,
    decision_id: ReviewDecisionId | None = None,
) -> ReviewCompletionRequestV2:
    results = request.draft.checklist_results
    if checklist_status is not None:
        first = results[0]
        results = (
            ChecklistResult(
                item_id=first.item_id,
                status=checklist_status,
                evidence=first.evidence,
                human_comment=(
                    HumanComment("Recorded local reason.")
                    if checklist_status
                    in {
                        ChecklistItemStatus.FAIL,
                        ChecklistItemStatus.NOT_APPLICABLE_WITH_REASON,
                    }
                    else None
                ),
            ),
            *results[1:],
        )
    draft = ReviewDecisionDraft(
        review_assignment_id=request.draft.review_assignment_id,
        article_version_id=request.draft.article_version_id,
        decision=request.draft.decision if decision is None else decision,
        summary=request.draft.summary,
        checklist_version=request.draft.checklist_version,
        checklist_sha256=request.draft.checklist_sha256,
        checklist_results=results,
    )
    return replace(
        request,
        draft=draft,
        decision_id=request.decision_id if decision_id is None else decision_id,
    )
