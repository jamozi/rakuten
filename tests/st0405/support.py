"""Import isolation and synthetic builders for the ST-0405 suite."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"

if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_audit import RecordedAuditAdapter  # noqa: E402
from raos.adapters.development_oidc import (  # noqa: E402
    DevelopmentOidcAdapter,
    InMemoryAuthenticationRepository,
    SystemEntropySource,
)
from raos.adapters.generated_st0403_authorization_registry import (  # noqa: E402
    CANONICAL_AUTHORIZATION_REGISTRY,
)
from raos.adapters.recorded_authorization import (  # noqa: E402
    RecordedSqliteAuthorizationRepository,
    recorded_authorization_policy_snapshot,
)
from raos.application.iam.authentication import AuthenticationService  # noqa: E402
from raos.application.iam.authorization import DurableAuthorizationService  # noqa: E402
from raos.application.ops.audit import AuditService  # noqa: E402
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.iam.authorization import (  # noqa: E402
    ActionCode,
    AuthorizationCommandId,
    AuthorizationDecision,
    AuthorizationDecisionReason,
    AuthorizationEvaluationCommand,
    AuthorizationGrant,
    AuthorizationRule,
    AuthorizationTarget,
    BusinessRole,
    CorrelationId,
    DecisionEffect,
    EntitlementRevision,
    EntitlementSnapshot,
    MatrixAction,
    OperationId,
    PermissionScope,
    PolicyRevision,
    PrincipalIdentity,
    ResourceScope,
    ResourceScopeKind,
    ResourceState,
    RuleId,
    ScopedBusinessRole,
    ScopedPermission,
)
from raos.domain.iam.authentication import (  # noqa: E402
    Issuer,
    PrincipalIdentity as AuthenticatedPrincipalIdentity,
    Session,
    SessionId,
    Subject,
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
POLICY_REVISION = PolicyRevision("RECORDED:ST0403:ST0405:POLICY:V1")
ENTITLEMENT_REVISION = EntitlementRevision("RECORDED:ST0405:ENTITLEMENT:V1")
AUTHORIZATION_COMMAND_ID = AuthorizationCommandId(
    "RECORDED:ST0405:AUTHORIZATION:ED011:1"
)


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


def durable_session(*, revoked_at: datetime | None = None) -> Session:
    return Session(
        session_id=SessionId.from_bytes(bytes([7]) * 32),
        principal=AuthenticatedPrincipalIdentity(
            issuer=Issuer("https://st0405.test.invalid"),
            subject=Subject("RECORDED:ST0405:EDITOR"),
            display_name="Recorded ST-0405 Editor",
        ),
        created_at=NOW - timedelta(minutes=5),
        last_seen_at=NOW - timedelta(seconds=1),
        idle_expires_at=NOW + timedelta(minutes=30),
        absolute_expires_at=NOW + timedelta(hours=2),
        revoked_at=revoked_at,
    )


def durable_authentication_service(active_session: Session) -> AuthenticationService:
    repository = InMemoryAuthenticationRepository(
        environment=RuntimeEnvironment.ENV_DEV
    )
    repository.create_session(active_session)
    return AuthenticationService(
        provider=DevelopmentOidcAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            principal=active_session.principal,
        ),
        repository=repository,
        entropy=SystemEntropySource(),
    )


def durable_authorization_principal() -> PrincipalIdentity:
    principal = durable_session().principal
    return PrincipalIdentity.admin_user(
        issuer=principal.issuer,
        subject=principal.subject,
    )


def durable_target() -> AuthorizationTarget:
    return AuthorizationTarget(
        scope=ResourceScope(
            kind=ResourceScopeKind.ARTICLE_VERSION,
            site_id=SITE_ID,
            resource_id=ARTICLE_ID,
        ),
        state=ResourceState("DRAFT"),
    )


def durable_authorization_bundle(
    root: Path,
    *,
    revoked: bool = False,
) -> tuple[
    DurableAuthorizationService,
    RecordedSqliteAuthorizationRepository,
    Session,
    AuthorizationEvaluationCommand,
]:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    active_session = durable_session(revoked_at=NOW if revoked else None)
    repository = RecordedSqliteAuthorizationRepository(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=root,
    )
    target = durable_target()
    repository.install_policy(
        expected_revision="TEST_ONLY:DISABLED",
        snapshot=recorded_authorization_policy_snapshot(
            revision=POLICY_REVISION,
            rules=(
                AuthorizationRule(
                    rule_id=RuleId("RECORDED:ST0403:ED-011:EDITOR"),
                    role=BusinessRole.EDITOR,
                    permission_scope=PermissionScope("editorial:version:write"),
                    action=ActionCode(MatrixAction.EDIT_ARTICLE_DRAFT.value),
                    resource_kind=ResourceScopeKind.ARTICLE_VERSION,
                    resource_state=ResourceState("DRAFT"),
                ),
            ),
        ),
    )
    principal = durable_authorization_principal()
    repository.install_entitlements(
        principal=principal,
        expected_revision=None,
        snapshot=EntitlementSnapshot(
            revision=ENTITLEMENT_REVISION,
            principal=principal,
            roles=(ScopedBusinessRole(role=BusinessRole.EDITOR, scope=target.scope),),
            permission_scopes=(
                ScopedPermission(
                    permission_scope=PermissionScope("editorial:version:write"),
                    scope=target.scope,
                ),
            ),
        ),
    )
    service = DurableAuthorizationService(
        session_service=durable_authentication_service(active_session),
        repository=repository,
        registry=CANONICAL_AUTHORIZATION_REGISTRY,
        step_up_consumer=None,
    )
    command = AuthorizationEvaluationCommand(
        command_id=AUTHORIZATION_COMMAND_ID,
        operation_id=OperationId("ED-011"),
        target=target,
        correlation_id=CorrelationId(str(CORRELATION_ID)),
        expected_policy_revision=POLICY_REVISION,
        expected_entitlement_revision=ENTITLEMENT_REVISION,
        observed_at=NOW,
    )
    if not revoked:
        service.require_admin(session_id=active_session.session_id, command=command)
    return service, repository, active_session, command
