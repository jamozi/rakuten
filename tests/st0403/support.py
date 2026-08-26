"""Import isolation and synthetic builders for the ST-0403 suite."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import NoReturn
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"

if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.development_authorization import (  # noqa: E402
    DevelopmentAuthorizationPolicySource,
    DevelopmentEntitlementSource,
    InMemoryAuthorizationDecisionSink,
)
from raos.adapters.development_oidc import (  # noqa: E402
    DevelopmentOidcAdapter,
    InMemoryAuthenticationRepository,
    SystemEntropySource,
)
from raos.application.iam.authentication import AuthenticationService  # noqa: E402
from raos.application.iam.authorization import AuthorizationGuard  # noqa: E402
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.iam.authentication import (  # noqa: E402
    Issuer,
    PrincipalIdentity as AuthenticatedPrincipalIdentity,
    Session,
    SessionId,
    Subject,
)
from raos.domain.iam.authorization import (  # noqa: E402
    ActionCode,
    AuthorizationFailure,
    AuthorizationRule,
    AuthorizationTarget,
    BusinessRole,
    EntitlementRevision,
    EntitlementSnapshot,
    PermissionScope,
    PolicyMode,
    PolicyRevision,
    PrincipalIdentity,
    ResourceScope,
    ResourceScopeKind,
    ResourceState,
    RuleId,
    ScopedBusinessRole,
    ScopedPermission,
)


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
SITE_A = UUID("11111111-1111-4111-8111-111111111111")
SITE_B = UUID("22222222-2222-4222-8222-222222222222")
ARTICLE_A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
ARTICLE_B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
CATEGORY_A = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


def bytes32(index: int) -> bytes:
    return bytes([index]) * 32


def authenticated_principal() -> AuthenticatedPrincipalIdentity:
    return AuthenticatedPrincipalIdentity(
        issuer=Issuer("https://test-only.dev.invalid"),
        subject=Subject("TEST_ONLY:ADMIN_USER"),
        display_name="Test Only Admin User",
    )


def session(
    *,
    index: int = 1,
    revoked_at: datetime | None = None,
    idle_expires_at: datetime = NOW + timedelta(minutes=30),
    absolute_expires_at: datetime = NOW + timedelta(hours=2),
) -> Session:
    return Session(
        session_id=SessionId.from_bytes(bytes32(index)),
        principal=authenticated_principal(),
        created_at=NOW - timedelta(minutes=5),
        last_seen_at=NOW - timedelta(seconds=1),
        idle_expires_at=idle_expires_at,
        absolute_expires_at=absolute_expires_at,
        revoked_at=revoked_at,
    )


def authentication_service(active_session: Session) -> AuthenticationService:
    repository = InMemoryAuthenticationRepository(
        environment=RuntimeEnvironment.ENV_DEV
    )
    repository.create_session(active_session)
    provider = DevelopmentOidcAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        principal=active_session.principal,
    )
    return AuthenticationService(
        provider=provider,
        repository=repository,
        entropy=SystemEntropySource(),
    )


def authorization_principal() -> PrincipalIdentity:
    principal = authenticated_principal()
    return PrincipalIdentity.admin_user(
        issuer=principal.issuer,
        subject=principal.subject,
    )


def scope(
    *,
    kind: ResourceScopeKind = ResourceScopeKind.ARTICLE,
    site_id: UUID = SITE_A,
    resource_id: UUID = ARTICLE_A,
) -> ResourceScope:
    return ResourceScope(kind=kind, site_id=site_id, resource_id=resource_id)


def target(
    *,
    resource_scope: ResourceScope | None = None,
    state: ResourceState | None = ResourceState("TEST_ONLY:DRAFT"),
) -> AuthorizationTarget:
    return AuthorizationTarget(
        scope=scope() if resource_scope is None else resource_scope,
        state=state,
    )


def rule(
    *,
    rule_id: str = "TEST_ONLY:RULE_EDIT_ARTICLE",
    role: BusinessRole = BusinessRole.EDITOR,
    permission_scope: str = "TEST_ONLY:ARTICLE_WRITE",
    action: str = "TEST_ONLY:EDIT_ARTICLE",
    resource_kind: ResourceScopeKind = ResourceScopeKind.ARTICLE,
    resource_state: ResourceState | None = ResourceState("TEST_ONLY:DRAFT"),
) -> AuthorizationRule:
    return AuthorizationRule(
        rule_id=RuleId(rule_id),
        role=role,
        permission_scope=PermissionScope(permission_scope),
        action=ActionCode(action),
        resource_kind=resource_kind,
        resource_state=resource_state,
    )


def entitlements(
    *,
    principal: PrincipalIdentity | None = None,
    roles: tuple[ScopedBusinessRole, ...] | None = None,
    permissions: tuple[ScopedPermission, ...] | None = None,
    resource_scope: ResourceScope | None = None,
) -> EntitlementSnapshot:
    exact_scope = scope() if resource_scope is None else resource_scope
    role_values = (
        (ScopedBusinessRole(role=BusinessRole.EDITOR, scope=exact_scope),)
        if roles is None
        else roles
    )
    permission_values = (
        (
            ScopedPermission(
                permission_scope=PermissionScope("TEST_ONLY:ARTICLE_WRITE"),
                scope=exact_scope,
            ),
        )
        if permissions is None
        else permissions
    )
    return EntitlementSnapshot(
        revision=EntitlementRevision("TEST_ONLY:ENTITLEMENTS_V1"),
        principal=authorization_principal() if principal is None else principal,
        roles=tuple(sorted(role_values, key=lambda value: value.canonical_key)),
        permission_scopes=tuple(
            sorted(permission_values, key=lambda value: value.canonical_key)
        ),
    )


def guard(
    *,
    active_session: Session | None = None,
    rules: tuple[AuthorizationRule, ...] = (),
    snapshots: tuple[EntitlementSnapshot, ...] = (),
    mode: PolicyMode = PolicyMode.RECORDED_TEST,
    sink: InMemoryAuthorizationDecisionSink | None = None,
) -> tuple[AuthorizationGuard, InMemoryAuthorizationDecisionSink]:
    current_session = session() if active_session is None else active_session
    decision_sink = (
        InMemoryAuthorizationDecisionSink(environment=RuntimeEnvironment.ENV_DEV)
        if sink is None
        else sink
    )
    policy_source = DevelopmentAuthorizationPolicySource(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=mode,
        revision=PolicyRevision(
            "TEST_ONLY:POLICY_V1"
            if mode is PolicyMode.RECORDED_TEST
            else "TEST_ONLY:DISABLED"
        ),
        rules=tuple(sorted(rules, key=lambda value: value.canonical_key)),
    )
    entitlement_source = DevelopmentEntitlementSource(
        environment=RuntimeEnvironment.ENV_DEV,
        snapshots=snapshots,
    )
    return (
        AuthorizationGuard(
            session_service=authentication_service(current_session),
            policy_source=policy_source,
            entitlement_source=entitlement_source,
            decision_sink=decision_sink,
        ),
        decision_sink,
    )


def assert_denied(call: object) -> AuthorizationFailure:
    if not callable(call):
        raise TypeError("call must be callable")
    try:
        call()
    except AuthorizationFailure as error:
        return error
    raise AssertionError("expected AuthorizationFailure(DENIED)")


def deny() -> NoReturn:
    raise AssertionError("unreachable")
