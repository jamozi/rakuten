from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from raos.adapters.recorded_final_approval import (
    RecordedFinalApprovalStep,
    load_recorded_final_approval_fixture,
)
from raos.domain.publishing.final_approval import (
    FinalApprovalFindingSnapshotV2,
    FinalApprovalId,
    FinalApprovalRequestV2,
    SiteId,
)
from raos.domain.publishing.review_workflow import PrincipalId, UtcTimestamp
from raos.generated.final_approval_pass_v2 import FINAL_APPROVAL_PASS_V2_JSON


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_FIXTURE_PATH = REPO_ROOT / "changes/st-0805/generated/policy-pass.v2.json"
REVIEW_FIXTURE_PATH = (
    REPO_ROOT / "changes/st-0901/generated/review-completion-pass.v2.json"
)


@pytest.fixture
def policy_fixture() -> bytes:
    return POLICY_FIXTURE_PATH.read_bytes()


@pytest.fixture
def review_fixture() -> bytes:
    return REVIEW_FIXTURE_PATH.read_bytes()


@pytest.fixture
def fixture_bytes() -> bytes:
    return FINAL_APPROVAL_PASS_V2_JSON


@pytest.fixture
def step(
    fixture_bytes: bytes,
    policy_fixture: bytes,
    review_fixture: bytes,
) -> RecordedFinalApprovalStep:
    return load_recorded_final_approval_fixture(
        fixture_bytes,
        policy_fixture=policy_fixture,
        review_fixture=review_fixture,
    )


def request_with(
    request: FinalApprovalRequestV2,
    *,
    approval_id: FinalApprovalId | None = None,
    article_author_id: PrincipalId | None = None,
    last_editor_id: PrincipalId | None = None,
    site_id: SiteId | None = None,
    finding_snapshot: FinalApprovalFindingSnapshotV2 | None = None,
    approved_at: UtcTimestamp | None = None,
) -> FinalApprovalRequestV2:
    return replace(
        request,
        approval_id=request.approval_id if approval_id is None else approval_id,
        article_author_id=(
            request.article_author_id
            if article_author_id is None
            else article_author_id
        ),
        last_editor_id=(
            request.last_editor_id if last_editor_id is None else last_editor_id
        ),
        site_id=request.site_id if site_id is None else site_id,
        finding_snapshot=(
            request.finding_snapshot if finding_snapshot is None else finding_snapshot
        ),
        approved_at=request.approved_at if approved_at is None else approved_at,
    )
