"""Synthetic deterministic builders for the isolated ST-0901 PR3 suite."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_review_decision import (  # noqa: E402
    RecordedReviewDecisionAdapter,
    RecordedReviewDecisionStep,
)
from raos.application.publishing.review_decision import (  # noqa: E402
    ReviewDecisionService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.iam.authorization import (  # noqa: E402
    ActionCode,
    AuthorizationDecision,
    AuthorizationDecisionReason,
    AuthorizationGrant,
    AuthorizationTarget,
    CorrelationId,
    DecisionEffect,
    EntitlementRevision,
    PermissionScope,
    PolicyRevision,
    ResourceScope,
    ResourceScopeKind,
    ResourceState,
    RuleId,
)
from raos.domain.portfolio.workflow import IdempotencyKey  # noqa: E402
from raos.domain.publishing.review_decision_operations import (  # noqa: E402
    RECORDED_LOCAL_PROFILE,
    RecordReviewDecisionRequest,
    RecordReviewDecisionResultV1,
    RecordedIdentityProjection,
    RecordedReviewDecisionHistoryV1,
    RecordedSubjectKind,
    RecordedSubjectStatus,
)
from raos.domain.publishing.review_workflow import (  # noqa: E402
    HUMAN_REVIEW_CHECKLIST_IDS,
    HUMAN_REVIEW_CHECKLIST_SHA256,
    HUMAN_REVIEW_CHECKLIST_VERSION,
    ArticleVersionId,
    ChecklistItemId,
    ChecklistItemStatus,
    ChecklistResult,
    DecisionSummary,
    PrincipalId,
    ReviewAssignment,
    ReviewAssignmentId,
    ReviewAssignmentState,
    ReviewDecisionDraft,
    ReviewDecisionId,
    ReviewDecisionKind,
    ReviewType,
    UtcTimestamp,
    create_review_assignment,
    transition_review_assignment,
)


def uuid7(suffix: int) -> UUID:
    return UUID(f"018f3e90-7b00-7000-8000-{suffix:012d}")


SITE_ID = uuid7(1)
OPAQUE_TARGET_RESOURCE_ID = uuid7(2)
ASSIGNED_BY = PrincipalId(uuid7(3))
REVIEWER_ID = PrincipalId(uuid7(4))
OTHER_REVIEWER_ID = PrincipalId(uuid7(5))
CREATED_AT = UtcTimestamp(datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc))
STARTED_AT = UtcTimestamp(datetime(2026, 8, 12, 1, 0, tzinfo=timezone.utc))
DECIDED_AT = UtcTimestamp(datetime(2026, 8, 12, 2, 0, tzinfo=timezone.utc))
LATER_DECIDED_AT = UtcTimestamp(datetime(2026, 8, 12, 3, 0, tzinfo=timezone.utc))


def opaque_target(
    *,
    resource_id: UUID = OPAQUE_TARGET_RESOURCE_ID,
    state: str = f"{RECORDED_LOCAL_PROFILE}:OPAQUE",
) -> AuthorizationTarget:
    return AuthorizationTarget(
        scope=ResourceScope(
            kind=ResourceScopeKind.SITE,
            site_id=SITE_ID,
            resource_id=resource_id,
        ),
        state=ResourceState(state),
    )


def recorded_grant(
    *,
    correlation_id: CorrelationId,
    target: AuthorizationTarget,
    action: str = "publishing:review:decide",
    rule_id: str = f"{RECORDED_LOCAL_PROFILE}:RULE",
) -> AuthorizationGrant:
    return AuthorizationGrant(
        recorded_decision=AuthorizationDecision(
            correlation_id=correlation_id,
            effect=DecisionEffect.ALLOW,
            reason=AuthorizationDecisionReason.RULE_MATCH,
            policy_revision=PolicyRevision(f"{RECORDED_LOCAL_PROFILE}:POLICY"),
            policy_fingerprint="9" * 64,
            entitlement_revision=EntitlementRevision(
                f"{RECORDED_LOCAL_PROFILE}:ENTITLEMENTS"
            ),
            matched_rule_id=RuleId(rule_id),
            action=ActionCode(action),
            target=target,
        )
    )


def identity(
    principal_id: PrincipalId = REVIEWER_ID,
    *,
    kind: RecordedSubjectKind = RecordedSubjectKind.HUMAN,
    status: RecordedSubjectStatus = RecordedSubjectStatus.ACTIVE,
) -> RecordedIdentityProjection:
    return RecordedIdentityProjection(
        principal_id=principal_id,
        subject_kind=kind,
        subject_status=status,
    )


def in_progress_assignment(
    *,
    assignment_suffix: int = 100,
    article_suffix: int = 200,
    assigned_to: PrincipalId = REVIEWER_ID,
    priority: int = 50,
) -> ReviewAssignment:
    assigned = create_review_assignment(
        assignment_id=ReviewAssignmentId(uuid7(assignment_suffix)),
        article_version_id=ArticleVersionId(uuid7(article_suffix)),
        review_type=ReviewType.EDITORIAL,
        assigned_by=ASSIGNED_BY,
        assigned_to=assigned_to,
        priority=priority,
        created_at=CREATED_AT,
    )
    return transition_review_assignment(
        assigned,
        ReviewAssignmentState.IN_PROGRESS,
        STARTED_AT,
        None,
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


def draft(
    assignment: ReviewAssignment,
    *,
    decision: ReviewDecisionKind = ReviewDecisionKind.CHANGES_REQUESTED,
    results: tuple[ChecklistResult, ...] | None = None,
    summary: str = "Human reviewer requests the documented changes.",
) -> ReviewDecisionDraft:
    return ReviewDecisionDraft(
        review_assignment_id=assignment.assignment_id,
        article_version_id=assignment.article_version_id,
        decision=decision,
        summary=DecisionSummary(summary),
        checklist_version=HUMAN_REVIEW_CHECKLIST_VERSION,
        checklist_sha256=HUMAN_REVIEW_CHECKLIST_SHA256,
        checklist_results=pass_results() if results is None else results,
    )


def request(
    *,
    assignment: ReviewAssignment | None = None,
    decision: ReviewDecisionKind = ReviewDecisionKind.CHANGES_REQUESTED,
    results: tuple[ChecklistResult, ...] | None = None,
    summary: str = "Human reviewer requests the documented changes.",
    supersedes_decision_id: ReviewDecisionId | None = None,
    correlation: str = f"{RECORDED_LOCAL_PROFILE}:RECORD",
    target: AuthorizationTarget | None = None,
    idempotency_key: str = "ST0901-PR3-LOCAL-DECISION-KEY",
) -> RecordReviewDecisionRequest:
    exact_assignment = in_progress_assignment() if assignment is None else assignment
    return RecordReviewDecisionRequest(
        correlation_id=CorrelationId(correlation),
        target=opaque_target() if target is None else target,
        assignment=exact_assignment,
        draft=draft(
            exact_assignment,
            decision=decision,
            results=results,
            summary=summary,
        ),
        idempotency_key=IdempotencyKey(idempotency_key),
        supersedes_decision_id=supersedes_decision_id,
    )


def empty_history(
    value: RecordReviewDecisionRequest,
) -> RecordedReviewDecisionHistoryV1:
    return RecordedReviewDecisionHistoryV1(
        assignment_id=value.assignment.assignment_id,
        article_version_id=value.assignment.article_version_id,
        records=(),
    )


def step(
    *,
    value: RecordReviewDecisionRequest | None = None,
    prior_history: RecordedReviewDecisionHistoryV1 | None = None,
    actor: RecordedIdentityProjection | None = None,
    action: str = "publishing:review:decide",
    permission: str = "publishing:review:decide",
    decision_suffix: int = 900,
    decided_at: UtcTimestamp = DECIDED_AT,
    audit_suffix: int = 950,
) -> RecordedReviewDecisionStep:
    exact_request = request() if value is None else value
    return RecordedReviewDecisionStep(
        request=exact_request,
        grant=recorded_grant(
            correlation_id=exact_request.correlation_id,
            target=exact_request.target,
            action=action,
        ),
        permission_scope=PermissionScope(permission),
        actor=identity() if actor is None else actor,
        prior_history=(
            empty_history(exact_request) if prior_history is None else prior_history
        ),
        decision_id=ReviewDecisionId(uuid7(decision_suffix)),
        decided_at=decided_at,
        audit_event_id=uuid7(audit_suffix),
    )


def scripted_result(value: RecordedReviewDecisionStep) -> RecordReviewDecisionResultV1:
    result = object.__getattribute__(value, "_result")
    if type(result) is not RecordReviewDecisionResultV1:
        raise AssertionError("invalid synthetic step result")
    return result


def adapter(
    *steps: RecordedReviewDecisionStep,
    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV,
) -> RecordedReviewDecisionAdapter:
    return RecordedReviewDecisionAdapter(
        environment=environment,
        script_capacity=max(1, len(steps)),
        scripts=steps,
    )


def service(
    value: RecordedReviewDecisionAdapter,
    *,
    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV,
) -> ReviewDecisionService:
    return ReviewDecisionService(
        environment=environment,
        authorization_source=value,
        exchange=value,
    )
