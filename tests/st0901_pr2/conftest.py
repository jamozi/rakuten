"""Synthetic deterministic builders for the isolated ST-0901 PR2 suite."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_review_assignment import (  # noqa: E402
    RecordedCreateReviewAssignmentStep,
    RecordedListReviewAssignmentsStep,
    RecordedReviewAssignmentAdapter,
    RecordedReviewAssignmentStep,
    RecordedUpdateReviewAssignmentStep,
)
from raos.application.publishing.review_assignment import (  # noqa: E402
    ReviewAssignmentService,
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
from raos.domain.portfolio.workflow import (  # noqa: E402
    EntityVersion,
    IdempotencyKey,
    StrongEtag,
)
from raos.domain.publishing.review_assignment_operations import (  # noqa: E402
    CreateReviewAssignmentRequest,
    ListReviewAssignmentsRequest,
    RecordedAssignmentSnapshotV1,
    RecordedAssignmentTransitionV1,
    RecordedIdentityProjection,
    RecordedSubjectKind,
    RecordedSubjectStatus,
    UpdateReviewAssignmentRequest,
)
from raos.domain.publishing.review_workflow import (  # noqa: E402
    ArticleVersionId,
    PrincipalId,
    ReviewAssignment,
    ReviewAssignmentId,
    ReviewAssignmentState,
    ReviewDecisionId,
    ReviewDecisionReference,
    ReviewType,
    UtcTimestamp,
    create_review_assignment,
    transition_review_assignment,
)


def uuid7(suffix: int) -> UUID:
    return UUID(f"018f3e90-7b00-7000-8000-{suffix:012d}")


SITE_ID = uuid7(1)
OPAQUE_TARGET_RESOURCE_ID = uuid7(2)
ACTOR_ID = PrincipalId(uuid7(3))
REVIEWER_ID = PrincipalId(uuid7(4))
OTHER_REVIEWER_ID = PrincipalId(uuid7(5))
CREATED_AT = UtcTimestamp(datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc))
STARTED_AT = UtcTimestamp(datetime(2026, 8, 12, 1, 0, tzinfo=timezone.utc))
FINISHED_AT = UtcTimestamp(datetime(2026, 8, 12, 2, 0, tzinfo=timezone.utc))


def opaque_target(
    *,
    resource_id: UUID = OPAQUE_TARGET_RESOURCE_ID,
    state: str = "ST0901_PR2_RECORDED_LOCAL_V1:OPAQUE",
) -> AuthorizationTarget:
    """Existing exact target used opaquely, with no article/assignment mapping."""

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
    action: str,
    correlation_id: CorrelationId,
    target: AuthorizationTarget,
    rule_id: str = "ST0901_PR2_RECORDED_LOCAL_V1:RULE",
) -> AuthorizationGrant:
    return AuthorizationGrant(
        recorded_decision=AuthorizationDecision(
            correlation_id=correlation_id,
            effect=DecisionEffect.ALLOW,
            reason=AuthorizationDecisionReason.RULE_MATCH,
            policy_revision=PolicyRevision("ST0901_PR2_RECORDED_LOCAL_V1:POLICY"),
            policy_fingerprint="9" * 64,
            entitlement_revision=EntitlementRevision(
                "ST0901_PR2_RECORDED_LOCAL_V1:ENTITLEMENTS"
            ),
            matched_rule_id=RuleId(rule_id),
            action=ActionCode(action),
            target=target,
        )
    )


def identity(
    principal_id: PrincipalId,
    *,
    kind: RecordedSubjectKind = RecordedSubjectKind.HUMAN,
    status: RecordedSubjectStatus = RecordedSubjectStatus.ACTIVE,
) -> RecordedIdentityProjection:
    return RecordedIdentityProjection(
        principal_id=principal_id,
        subject_kind=kind,
        subject_status=status,
    )


def assignment(
    *,
    suffix: int = 100,
    article_suffix: int = 200,
    assigned_by: PrincipalId = ACTOR_ID,
    assigned_to: PrincipalId = REVIEWER_ID,
    priority: int = 50,
    created_at: UtcTimestamp = CREATED_AT,
    review_type: ReviewType = ReviewType.EDITORIAL,
) -> ReviewAssignment:
    return create_review_assignment(
        assignment_id=ReviewAssignmentId(uuid7(suffix)),
        article_version_id=ArticleVersionId(uuid7(article_suffix)),
        review_type=review_type,
        assigned_by=assigned_by,
        assigned_to=assigned_to,
        priority=priority,
        created_at=created_at,
    )


def snapshot(
    value: ReviewAssignment,
    *,
    etag: str | None = None,
) -> RecordedAssignmentSnapshotV1:
    rendered = (
        f'"ST0901-PR2-LOCAL-{value.assignment_id.value.hex}-v{value.lock_version}"'
        if etag is None
        else etag
    )
    return RecordedAssignmentSnapshotV1(
        assignment=value,
        etag=StrongEtag(rendered),
    )


def list_request(
    *,
    correlation: str = "ST0901_PR2_RECORDED_LOCAL_V1:LIST",
    target: AuthorizationTarget | None = None,
    article_version_id: ArticleVersionId | None = None,
    assigned_to: PrincipalId | None = None,
    status: ReviewAssignmentState | None = None,
    limit: int = 100,
) -> ListReviewAssignmentsRequest:
    return ListReviewAssignmentsRequest(
        correlation_id=CorrelationId(correlation),
        target=opaque_target() if target is None else target,
        article_version_id=article_version_id,
        assigned_to=assigned_to,
        status=status,
        limit=limit,
    )


def list_step(
    *,
    request: ListReviewAssignmentsRequest | None = None,
    items: tuple[RecordedAssignmentSnapshotV1, ...] = (),
    actor: RecordedIdentityProjection | None = None,
    action: str = "publishing:review:read",
    permission: str = "publishing:review:read",
) -> RecordedListReviewAssignmentsStep:
    exact_request = list_request() if request is None else request
    return RecordedListReviewAssignmentsStep(
        request=exact_request,
        grant=recorded_grant(
            action=action,
            correlation_id=exact_request.correlation_id,
            target=exact_request.target,
        ),
        permission_scope=PermissionScope(permission),
        actor=identity(ACTOR_ID) if actor is None else actor,
        items=items,
    )


def create_request(
    *,
    suffix: int = 100,
    article_suffix: int = 200,
    priority: int = 50,
    assigned_to: PrincipalId = REVIEWER_ID,
    correlation: str = "ST0901_PR2_RECORDED_LOCAL_V1:CREATE",
    target: AuthorizationTarget | None = None,
    idempotency_key: str = "ST0901-PR2-LOCAL-CREATE-KEY",
    created_at: UtcTimestamp = CREATED_AT,
) -> CreateReviewAssignmentRequest:
    return CreateReviewAssignmentRequest(
        correlation_id=CorrelationId(correlation),
        target=opaque_target() if target is None else target,
        assignment_id=ReviewAssignmentId(uuid7(suffix)),
        article_version_id=ArticleVersionId(uuid7(article_suffix)),
        review_type=ReviewType.EDITORIAL,
        assigned_to=assigned_to,
        priority=priority,
        created_at=created_at,
        idempotency_key=IdempotencyKey(idempotency_key),
    )


def create_step(
    *,
    request: CreateReviewAssignmentRequest | None = None,
    actor: RecordedIdentityProjection | None = None,
    reviewer: RecordedIdentityProjection | None = None,
    action: str = "publishing:review:assign",
    permission: str = "publishing:review:assign",
    audit_suffix: int = 900,
) -> RecordedCreateReviewAssignmentStep:
    exact_request = create_request() if request is None else request
    exact_actor = identity(ACTOR_ID) if actor is None else actor
    exact_reviewer = (
        identity(exact_request.assigned_to) if reviewer is None else reviewer
    )
    value = create_review_assignment(
        assignment_id=exact_request.assignment_id,
        article_version_id=exact_request.article_version_id,
        review_type=exact_request.review_type,
        assigned_by=exact_actor.principal_id,
        assigned_to=exact_reviewer.principal_id,
        priority=exact_request.priority,
        created_at=exact_request.created_at,
    )
    return RecordedCreateReviewAssignmentStep(
        request=exact_request,
        grant=recorded_grant(
            action=action,
            correlation_id=exact_request.correlation_id,
            target=exact_request.target,
        ),
        permission_scope=PermissionScope(permission),
        actor=exact_actor,
        reviewer=exact_reviewer,
        snapshot=snapshot(value),
        audit_event_id=uuid7(audit_suffix),
        audit_occurred_at=exact_request.created_at,
    )


def decision_reference(value: ReviewAssignment) -> ReviewDecisionReference:
    return ReviewDecisionReference(
        ReviewDecisionId(uuid7(950)),
        value.assignment_id,
        value.article_version_id,
    )


def update_request(
    prior: RecordedAssignmentSnapshotV1,
    *,
    target_state: ReviewAssignmentState,
    occurred_at: UtcTimestamp,
    completion_reference: ReviewDecisionReference | None = None,
    correlation: str = "ST0901_PR2_RECORDED_LOCAL_V1:UPDATE",
    target: AuthorizationTarget | None = None,
    idempotency_key: str = "ST0901-PR2-LOCAL-UPDATE-KEY",
) -> UpdateReviewAssignmentRequest:
    return UpdateReviewAssignmentRequest(
        correlation_id=CorrelationId(correlation),
        target=opaque_target() if target is None else target,
        assignment_id=prior.assignment.assignment_id,
        article_version_id=prior.assignment.article_version_id,
        target_state=target_state,
        occurred_at=occurred_at,
        expected_lock_version=EntityVersion(prior.assignment.lock_version),
        if_match=prior.etag,
        idempotency_key=IdempotencyKey(idempotency_key),
        completion_decision_reference=completion_reference,
    )


def update_step(
    prior: RecordedAssignmentSnapshotV1,
    *,
    target_state: ReviewAssignmentState,
    occurred_at: UtcTimestamp,
    completion_reference: ReviewDecisionReference | None = None,
    request: UpdateReviewAssignmentRequest | None = None,
    actor: RecordedIdentityProjection | None = None,
    reviewer: RecordedIdentityProjection | None = None,
    action: str = "publishing:review:assign",
    permission: str = "publishing:review:assign",
    audit_suffix: int = 901,
) -> RecordedUpdateReviewAssignmentStep:
    exact_request = (
        update_request(
            prior,
            target_state=target_state,
            occurred_at=occurred_at,
            completion_reference=completion_reference,
        )
        if request is None
        else request
    )
    after = transition_review_assignment(
        prior.assignment,
        exact_request.target_state,
        exact_request.occurred_at,
        exact_request.completion_decision_reference,
    )
    return RecordedUpdateReviewAssignmentStep(
        request=exact_request,
        grant=recorded_grant(
            action=action,
            correlation_id=exact_request.correlation_id,
            target=exact_request.target,
        ),
        permission_scope=PermissionScope(permission),
        actor=identity(ACTOR_ID) if actor is None else actor,
        reviewer=(
            identity(prior.assignment.assigned_to) if reviewer is None else reviewer
        ),
        transition=RecordedAssignmentTransitionV1(
            before=prior,
            after=snapshot(after),
        ),
        audit_event_id=uuid7(audit_suffix),
        audit_occurred_at=exact_request.occurred_at,
    )


def adapter(
    *steps: RecordedReviewAssignmentStep,
    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV,
) -> RecordedReviewAssignmentAdapter:
    return RecordedReviewAssignmentAdapter(
        environment=environment,
        script_capacity=max(1, len(steps)),
        scripts=steps,
    )


def service(
    recorded: RecordedReviewAssignmentAdapter,
    *,
    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV,
) -> ReviewAssignmentService:
    return ReviewAssignmentService(
        environment=environment,
        authorization_source=recorded,
        exchange=recorded,
    )


def execute(
    step: RecordedReviewAssignmentStep,
) -> tuple[RecordedReviewAssignmentAdapter, object]:
    recorded = adapter(step)
    result = service(recorded).execute(request=step.request)
    return recorded, result


def clone_request_with_priority(
    request: CreateReviewAssignmentRequest,
    priority: int,
) -> CreateReviewAssignmentRequest:
    return CreateReviewAssignmentRequest(
        correlation_id=request.correlation_id,
        target=request.target,
        assignment_id=request.assignment_id,
        article_version_id=request.article_version_id,
        review_type=request.review_type,
        assigned_to=request.assigned_to,
        priority=priority,
        created_at=request.created_at,
        idempotency_key=request.idempotency_key,
    )


__all__ = [
    "ACTOR_ID",
    "CREATED_AT",
    "FINISHED_AT",
    "OTHER_REVIEWER_ID",
    "REVIEWER_ID",
    "STARTED_AT",
    "adapter",
    "assignment",
    "clone_request_with_priority",
    "create_request",
    "create_step",
    "decision_reference",
    "execute",
    "identity",
    "list_request",
    "list_step",
    "opaque_target",
    "recorded_grant",
    "service",
    "snapshot",
    "update_request",
    "update_step",
    "uuid7",
]
