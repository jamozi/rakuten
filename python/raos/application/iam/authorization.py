"""Transport-neutral, deny-default ST-0403 authorization guard."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, NoReturn, cast

from raos.application.iam.authentication import AuthenticationService
from raos.domain.iam.authentication import (
    PrincipalIdentity as AuthenticatedPrincipalIdentity,
    Session,
    SessionId,
)
from raos.domain.iam.authorization import (
    ActionCode,
    AuthorizationDecision,
    AuthorizationDecisionReason,
    AuthorizationGrant,
    AuthorizationRule,
    AuthorizationTarget,
    CorrelationId,
    DecisionEffect,
    EntitlementRevision,
    EntitlementSnapshot,
    PolicyMode,
    PolicyRevision,
    PolicySnapshot,
    PrincipalIdentity,
    RuleId,
    ScopedBusinessRole,
    ScopedPermission,
    deny_authorization,
)
from raos.ports.authorization import (
    AuthorizationDecisionSink,
    AuthorizationPolicySource,
    EntitlementSource,
)


_UNAVAILABLE_POLICY_REVISION = PolicyRevision("TEST_ONLY:UNAVAILABLE_POLICY")
_UNAVAILABLE_ENTITLEMENT_REVISION = EntitlementRevision(
    "TEST_ONLY:UNAVAILABLE_ENTITLEMENTS"
)
_UNAVAILABLE_POLICY_FINGERPRINT = (
    "0000000000000000000000000000000000000000000000000000000000000000"
)


def _deny() -> NoReturn:
    deny_authorization()


def _load_policy(source: AuthorizationPolicySource) -> object:
    return source.load()


def _resolve_entitlements(
    source: EntitlementSource, principal: PrincipalIdentity
) -> object:
    return source.resolve(principal)


def _record_result(
    sink: AuthorizationDecisionSink, decision: AuthorizationDecision
) -> object:
    recorder: Callable[[AuthorizationDecision], object] = sink.record
    return recorder(decision)


def _role_matches(
    rule: AuthorizationRule,
    target: AuthorizationTarget,
    roles: tuple[ScopedBusinessRole, ...],
) -> bool:
    return any(role.role is rule.role and role.scope == target.scope for role in roles)


def _permission_matches(
    rule: AuthorizationRule,
    target: AuthorizationTarget,
    permissions: tuple[ScopedPermission, ...],
) -> bool:
    return any(
        permission.permission_scope == rule.permission_scope
        and permission.scope == target.scope
        for permission in permissions
    )


def _rule_matches(
    *,
    rule: AuthorizationRule,
    action: ActionCode,
    target: AuthorizationTarget,
    entitlements: EntitlementSnapshot,
) -> bool:
    return (
        rule.action == action
        and rule.resource_kind is target.scope.kind
        and rule.resource_state == target.state
        and _role_matches(rule, target, entitlements.roles)
        and _permission_matches(rule, target, entitlements.permission_scopes)
    )


class AuthorizationGuard:
    """Authorize an active admin user against one exact recorded snapshot.

    The only public entrypoint derives the user/admin principal from the active
    ST-0401 session.  There is intentionally no service entrypoint in this
    Story slice.
    """

    def __init__(
        self,
        *,
        session_service: AuthenticationService,
        policy_source: AuthorizationPolicySource,
        entitlement_source: EntitlementSource,
        decision_sink: AuthorizationDecisionSink,
    ) -> None:
        if type(session_service) is not AuthenticationService:
            raise TypeError("session_service must be an exact AuthenticationService")
        if not isinstance(cast(object, policy_source), AuthorizationPolicySource):
            raise TypeError("policy_source must implement AuthorizationPolicySource")
        if not isinstance(cast(object, entitlement_source), EntitlementSource):
            raise TypeError("entitlement_source must implement EntitlementSource")
        if not isinstance(cast(object, decision_sink), AuthorizationDecisionSink):
            raise TypeError("decision_sink must implement AuthorizationDecisionSink")
        self._session_service = session_service
        self._policy_source = policy_source
        self._entitlement_source = entitlement_source
        self._decision_sink = decision_sink

    def require_admin_user(
        self,
        *,
        session_id: SessionId,
        now: datetime,
        action: ActionCode,
        target: AuthorizationTarget,
        correlation_id: CorrelationId,
    ) -> AuthorizationGrant:
        """Return one exact recorded grant or expose only ``DENIED``.

        Active-session validation is deliberately the first operation.  A
        failed, inactive, expired, revoked, rotated, or unknown session causes
        zero policy, entitlement, and decision-sink calls.
        """

        session: object = None
        session_failed = False
        try:
            session = self._session_service.require_session(
                session_id=session_id, now=now
            )
        except Exception:
            session_failed = True
        if session_failed or type(session) is not Session:
            _deny()

        if (
            type(action) is not ActionCode
            or type(target) is not AuthorizationTarget
            or type(correlation_id) is not CorrelationId
            or type(session.principal) is not AuthenticatedPrincipalIdentity
        ):
            _deny()

        principal: PrincipalIdentity | None = None
        principal_failed = False
        try:
            principal = PrincipalIdentity.admin_user(
                issuer=session.principal.issuer,
                subject=session.principal.subject,
            )
        except Exception:
            principal_failed = True
        if principal_failed or principal is None:
            _deny()

        policy: object = None
        policy_failed = False
        try:
            policy = _load_policy(self._policy_source)
            if type(policy) is not PolicySnapshot:
                policy_failed = True
            else:
                policy.require_valid()
        except Exception:
            policy_failed = True
        if policy_failed or type(policy) is not PolicySnapshot:
            self._record_denial(
                correlation_id=correlation_id,
                reason=AuthorizationDecisionReason.POLICY_FAILURE,
                policy_revision=_UNAVAILABLE_POLICY_REVISION,
                policy_fingerprint=_UNAVAILABLE_POLICY_FINGERPRINT,
                entitlement_revision=_UNAVAILABLE_ENTITLEMENT_REVISION,
                action=action,
                target=target,
            )

        if policy.mode is PolicyMode.DISABLED:
            self._record_denial(
                correlation_id=correlation_id,
                reason=AuthorizationDecisionReason.POLICY_DISABLED,
                policy_revision=policy.revision,
                policy_fingerprint=policy.fingerprint,
                entitlement_revision=_UNAVAILABLE_ENTITLEMENT_REVISION,
                action=action,
                target=target,
            )
        if policy.mode is not PolicyMode.RECORDED_TEST:
            self._record_denial(
                correlation_id=correlation_id,
                reason=AuthorizationDecisionReason.POLICY_FAILURE,
                policy_revision=policy.revision,
                policy_fingerprint=policy.fingerprint,
                entitlement_revision=_UNAVAILABLE_ENTITLEMENT_REVISION,
                action=action,
                target=target,
            )

        entitlements: object = None
        entitlement_failed = False
        try:
            entitlements = _resolve_entitlements(self._entitlement_source, principal)
            if type(entitlements) is not EntitlementSnapshot:
                entitlement_failed = True
            else:
                entitlements.require_valid()
                if entitlements.principal != principal:
                    entitlement_failed = True
        except Exception:
            entitlement_failed = True
        if entitlement_failed or type(entitlements) is not EntitlementSnapshot:
            self._record_denial(
                correlation_id=correlation_id,
                reason=AuthorizationDecisionReason.ENTITLEMENT_FAILURE,
                policy_revision=policy.revision,
                policy_fingerprint=policy.fingerprint,
                entitlement_revision=_UNAVAILABLE_ENTITLEMENT_REVISION,
                action=action,
                target=target,
            )

        matches = tuple(
            rule
            for rule in policy.rules
            if _rule_matches(
                rule=rule,
                action=action,
                target=target,
                entitlements=entitlements,
            )
        )
        if not matches:
            self._record_denial(
                correlation_id=correlation_id,
                reason=AuthorizationDecisionReason.NO_MATCH,
                policy_revision=policy.revision,
                policy_fingerprint=policy.fingerprint,
                entitlement_revision=entitlements.revision,
                action=action,
                target=target,
            )
        if len(matches) != 1:
            self._record_denial(
                correlation_id=correlation_id,
                reason=AuthorizationDecisionReason.AMBIGUOUS_MATCH,
                policy_revision=policy.revision,
                policy_fingerprint=policy.fingerprint,
                entitlement_revision=entitlements.revision,
                action=action,
                target=target,
            )

        return self._record_allow(
            correlation_id=correlation_id,
            policy=policy,
            entitlements=entitlements,
            matched_rule_id=matches[0].rule_id,
            action=action,
            target=target,
        )

    def _record_denial(
        self,
        *,
        correlation_id: CorrelationId,
        reason: AuthorizationDecisionReason,
        policy_revision: PolicyRevision,
        policy_fingerprint: str,
        entitlement_revision: EntitlementRevision,
        action: ActionCode,
        target: AuthorizationTarget,
    ) -> NoReturn:
        decision_failed = False
        decision: AuthorizationDecision | None = None
        try:
            decision = AuthorizationDecision(
                correlation_id=correlation_id,
                effect=DecisionEffect.DENY,
                reason=reason,
                policy_revision=policy_revision,
                policy_fingerprint=policy_fingerprint,
                entitlement_revision=entitlement_revision,
                matched_rule_id=None,
                action=action,
                target=target,
            )
        except Exception:
            decision_failed = True
        if not decision_failed and decision is not None:
            try:
                self._decision_sink.record(decision)
            except Exception:
                pass
        _deny()

    def _record_allow(
        self,
        *,
        correlation_id: CorrelationId,
        policy: PolicySnapshot,
        entitlements: EntitlementSnapshot,
        matched_rule_id: RuleId,
        action: ActionCode,
        target: AuthorizationTarget,
    ) -> AuthorizationGrant:
        decision = AuthorizationDecision(
            correlation_id=correlation_id,
            effect=DecisionEffect.ALLOW,
            reason=AuthorizationDecisionReason.RULE_MATCH,
            policy_revision=policy.revision,
            policy_fingerprint=policy.fingerprint,
            entitlement_revision=entitlements.revision,
            matched_rule_id=matched_rule_id,
            action=action,
            target=target,
        )
        record_result: object = None
        sink_failed = False
        try:
            record_result = _record_result(self._decision_sink, decision)
        except Exception:
            sink_failed = True
        if (
            sink_failed
            or record_result is not None
            or decision.correlation_id != correlation_id
            or decision.effect is not DecisionEffect.ALLOW
            or decision.reason is not AuthorizationDecisionReason.RULE_MATCH
            or decision.policy_revision != policy.revision
            or decision.policy_fingerprint != policy.fingerprint
            or decision.entitlement_revision != entitlements.revision
            or decision.matched_rule_id != matched_rule_id
            or decision.action != action
            or decision.target != target
        ):
            _deny()
        normalized_recorded_decision = AuthorizationDecision(
            correlation_id=correlation_id,
            effect=DecisionEffect.ALLOW,
            reason=AuthorizationDecisionReason.RULE_MATCH,
            policy_revision=policy.revision,
            policy_fingerprint=policy.fingerprint,
            entitlement_revision=entitlements.revision,
            matched_rule_id=matched_rule_id,
            action=action,
            target=target,
        )
        return AuthorizationGrant(recorded_decision=normalized_recorded_decision)


__all__ = ["AuthorizationGuard"]
