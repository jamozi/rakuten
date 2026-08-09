"""Import isolation and synthetic builders for the ST-0405 suite."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"

if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_audit import RecordedAuditAdapter  # noqa: E402
from raos.application.ops.audit import AuditService  # noqa: E402
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
    PolicyRevision,
    ResourceScope,
    ResourceScopeKind,
    ResourceState,
    RuleId,
)
from raos.domain.ops.audit import (  # noqa: E402
    AuditActor,
    AuditActorType,
    AuditContext,
    AuditEvent,
    AuditEventId,
    AuditOutcome,
    AuditReasonCode,
    AuditRequestId,
    AuditSeverity,
)


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
SITE_ID = UUID("11111111-1111-4111-8111-111111111111")
ARTICLE_ID = UUID("22222222-2222-4222-8222-222222222222")
ACTOR_ID = UUID("33333333-3333-4333-8333-333333333333")
CORRELATION_ID = UUID("44444444-4444-4444-8444-444444444444")
EVENT_ID = UUID("55555555-5555-4555-8555-555555555555")
OTHER_EVENT_ID = UUID("66666666-6666-4666-8666-666666666666")


def authorization_grant(
    *,
    action: str = "TEST_ONLY:AUDIT_CRITICAL",
    resource_id: UUID = ARTICLE_ID,
    correlation_id: UUID = CORRELATION_ID,
    kind: ResourceScopeKind = ResourceScopeKind.ARTICLE,
) -> AuthorizationGrant:
    target = AuthorizationTarget(
        scope=ResourceScope(
            kind=kind,
            site_id=SITE_ID,
            resource_id=resource_id,
        ),
        state=ResourceState("TEST_ONLY:APPROVED"),
    )
    decision = AuthorizationDecision(
        correlation_id=CorrelationId(str(correlation_id)),
        effect=DecisionEffect.ALLOW,
        reason=AuthorizationDecisionReason.RULE_MATCH,
        policy_revision=PolicyRevision("TEST_ONLY:POLICY_V1"),
        policy_fingerprint="1" * 64,
        entitlement_revision=EntitlementRevision("TEST_ONLY:ENTITLEMENTS_V1"),
        matched_rule_id=RuleId("TEST_ONLY:AUDIT_RULE"),
        action=ActionCode(action),
        target=target,
    )
    return AuthorizationGrant(recorded_decision=decision)


def audit_actor(
    *,
    actor_type: AuditActorType = AuditActorType.USER,
    actor_id: UUID | None = ACTOR_ID,
) -> AuditActor:
    return AuditActor(actor_type=actor_type, actor_id=actor_id)


def audit_context(
    grant: AuthorizationGrant,
    *,
    event_id: UUID = EVENT_ID,
    actor: AuditActor | None = None,
    occurred_at: datetime = NOW,
    request_id: AuditRequestId | None = AuditRequestId("TEST_ONLY:REQUEST_1"),
) -> AuditContext:
    return AuditContext(
        grant=grant,
        event_id=AuditEventId(event_id),
        actor=audit_actor() if actor is None else actor,
        occurred_at=occurred_at,
        request_id=request_id,
    )


def audit_event(
    grant: AuthorizationGrant,
    *,
    context: AuditContext | None = None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    severity: AuditSeverity = AuditSeverity.NOTICE,
    reason_code: AuditReasonCode | None = None,
    before_hash: str | None = "a" * 64,
    after_hash: str | None = "b" * 64,
) -> AuditEvent:
    return AuditEvent(
        grant=grant,
        context=audit_context(grant) if context is None else context,
        outcome=outcome,
        severity=severity,
        reason_code=(
            AuditReasonCode("TEST_ONLY:AUTHORIZED_CHANGE")
            if reason_code is None
            else reason_code
        ),
        before_hash=before_hash,
        after_hash=after_hash,
    )


def service_bundle(
    *,
    contexts: tuple[AuditContext, ...],
    capacity: int,
) -> tuple[AuditService, RecordedAuditAdapter]:
    adapter = RecordedAuditAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=capacity,
        context_script=contexts,
    )
    return (
        AuditService(context_source=adapter, appender=adapter),
        adapter,
    )
