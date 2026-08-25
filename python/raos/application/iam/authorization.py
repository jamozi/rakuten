"""Transport-neutral, deny-default ST-0403 authorization guard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
from typing import Callable, NoReturn, TypeVar, cast

from raos.application.iam.authentication import AuthenticationService
from raos.domain.iam.authentication import (
    AuthenticationFailure,
    PrincipalIdentity as AuthenticatedPrincipalIdentity,
    Session,
    SessionId,
    snapshot_session,
    snapshot_session_id,
)
from raos.domain.iam.authorization import (
    ActionCode,
    AuthorizationBindingStatus,
    AuthorizationCommandId,
    AuthorizationCommandResult,
    AuthorizationDecision,
    AuthorizationDecisionReason,
    AuthorizationGrant,
    AuthorizationRule,
    AuthorizationTarget,
    AuthorizationEvaluationCommand,
    AuthorizationFailure,
    CanonicalAuthorizationRegistry,
    CorrelationId,
    DecisionEffect,
    EntitlementRevision,
    EntitlementSnapshot,
    IndependentActorEvidence,
    MatrixAction,
    MatrixPermissionDefinition,
    OperationAuthorizationBinding,
    OperationId,
    PolicyMode,
    PolicyRevision,
    PolicySnapshot,
    PrincipalIdentity,
    AuthorizationRepositoryFailure,
    RuleId,
    ScopedBusinessRole,
    ScopedPermission,
    deny_authorization,
    snapshot_authorization_evaluation_command,
    snapshot_authorization_result,
    snapshot_authorization_target,
    snapshot_entitlement_snapshot,
    snapshot_independent_actor_evidence,
    snapshot_policy_snapshot,
)
from raos.ports.authorization import (
    AuthorizationDecisionSink,
    AuthorizationPolicySource,
    EntitlementSource,
    AuthorizationRepository,
    AuthorizationUnitOfWork,
    SingleUseStepUpGrantConsumer,
)
from raos.domain.iam.step_up import (
    StepUpAuthorizationReceipt,
    StepUpCommandResult,
    StepUpFailure,
    StepUpOperation,
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

        try:
            session = snapshot_session(session)
            target = snapshot_authorization_target(target)
            action = ActionCode(action.value)
            correlation_id = CorrelationId(correlation_id.value)
        except Exception:
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
                policy = snapshot_policy_snapshot(policy)
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
                entitlements = snapshot_entitlement_snapshot(entitlements)
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


@dataclass(frozen=True, slots=True)
class _DurableEvaluation:
    decision: AuthorizationDecision
    binding: OperationAuthorizationBinding | None
    definition: MatrixPermissionDefinition | None
    requires_step_up: bool


def _durable_action(action: MatrixAction | None) -> ActionCode:
    return ActionCode("authorization.unmapped" if action is None else action.value)


def _durable_decision(
    *,
    command: AuthorizationEvaluationCommand,
    action: MatrixAction | None,
    effect: DecisionEffect,
    reason: AuthorizationDecisionReason,
    policy: PolicySnapshot,
    entitlements: EntitlementSnapshot,
    matched_rule_id: RuleId | None,
) -> AuthorizationDecision:
    return AuthorizationDecision(
        correlation_id=command.correlation_id,
        effect=effect,
        reason=reason,
        policy_revision=policy.revision,
        policy_fingerprint=policy.fingerprint,
        entitlement_revision=entitlements.revision,
        matched_rule_id=matched_rule_id,
        action=_durable_action(action),
        target=command.target,
    )


def _independent_actor_reason(
    *,
    evidence: IndependentActorEvidence | None,
    principal: PrincipalIdentity,
    action: MatrixAction,
    operation_id: OperationId,
    target: AuthorizationTarget,
    observed_at: datetime,
) -> AuthorizationDecisionReason | None:
    if evidence is None:
        return AuthorizationDecisionReason.SEPARATION_OF_DUTIES_REQUIRED
    if hmac.compare_digest(evidence.actor_fingerprint, principal.fingerprint):
        return AuthorizationDecisionReason.SEPARATION_OF_DUTIES_SELF
    if (
        evidence.action is not action
        or evidence.operation_id != operation_id
        or evidence.site_id != target.scope.site_id
        or evidence.resource_id != target.scope.resource_id
        or evidence.recorded_at > observed_at
    ):
        return AuthorizationDecisionReason.SEPARATION_OF_DUTIES_MISMATCH
    return None


def _evaluate_durable(
    *,
    uow: AuthorizationUnitOfWork,
    registry: CanonicalAuthorizationRegistry,
    command: AuthorizationEvaluationCommand,
    principal: PrincipalIdentity,
    step_up_satisfied: bool,
    step_up_failed: bool,
) -> _DurableEvaluation:
    policy = uow.load_policy()
    entitlements = uow.load_entitlements(principal)
    if (
        type(policy) is not PolicySnapshot
        or type(entitlements) is not EntitlementSnapshot
    ):
        _deny()
    policy = snapshot_policy_snapshot(policy)
    entitlements = snapshot_entitlement_snapshot(entitlements)
    if entitlements.principal != principal:
        _deny()
    resolution = registry.resolve(command.operation_id)
    action = resolution.action

    def denied(reason: AuthorizationDecisionReason) -> _DurableEvaluation:
        return _DurableEvaluation(
            decision=_durable_decision(
                command=command,
                action=action,
                effect=DecisionEffect.DENY,
                reason=reason,
                policy=policy,
                entitlements=entitlements,
                matched_rule_id=None,
            ),
            binding=None,
            definition=None,
            requires_step_up=False,
        )

    if policy.revision != command.expected_policy_revision:
        return denied(AuthorizationDecisionReason.STALE_POLICY)
    if entitlements.revision != command.expected_entitlement_revision:
        return denied(AuthorizationDecisionReason.STALE_ENTITLEMENTS)
    if policy.mode is PolicyMode.DISABLED:
        return denied(AuthorizationDecisionReason.POLICY_DISABLED)
    if resolution.status is not AuthorizationBindingStatus.ACTIVE_RECORDED:
        return denied(
            AuthorizationDecisionReason.OPERATION_UNMAPPED
            if resolution.block_reason is not None
            and resolution.block_reason.value == "UNMAPPED_OPERATION"
            else AuthorizationDecisionReason.OPERATION_BLOCKED
        )
    binding = resolution.binding
    if type(binding) is not OperationAuthorizationBinding or action is None:
        return denied(AuthorizationDecisionReason.OPERATION_BLOCKED)
    definition = registry.definition(action)
    if (
        binding.resource_kind is not command.target.scope.kind
        or not binding.accepts_state(command.target.state)
    ):
        return denied(AuthorizationDecisionReason.NO_MATCH)
    matches = tuple(
        rule
        for rule in policy.rules
        if rule.action == ActionCode(action.value)
        and rule.permission_scope == binding.permission_scope
        and rule.role in definition.allowed_roles
        and _rule_matches(
            rule=rule,
            action=ActionCode(action.value),
            target=command.target,
            entitlements=entitlements,
        )
    )
    if not matches:
        return denied(AuthorizationDecisionReason.NO_MATCH)
    if len(matches) != 1:
        return denied(AuthorizationDecisionReason.AMBIGUOUS_MATCH)
    if definition.separation_of_duties:
        evidence = (
            None
            if command.independent_actor_evidence_id is None
            else uow.load_independent_actor_evidence(
                command.independent_actor_evidence_id
            )
        )
        if evidence is not None:
            evidence = snapshot_independent_actor_evidence(evidence)
        reason = _independent_actor_reason(
            evidence=evidence,
            principal=principal,
            action=action,
            operation_id=command.operation_id,
            target=command.target,
            observed_at=command.observed_at,
        )
        if reason is not None:
            return denied(reason)
    requires_step_up = definition.mfa_required or definition.step_up_required
    if requires_step_up and (
        command.step_up_command_id is None or command.step_up_grant_id is None
    ):
        return denied(AuthorizationDecisionReason.STEP_UP_REQUIRED)
    if step_up_failed:
        return denied(AuthorizationDecisionReason.STEP_UP_FAILURE)
    if requires_step_up and not step_up_satisfied:
        return _DurableEvaluation(
            decision=_durable_decision(
                command=command,
                action=action,
                effect=DecisionEffect.ALLOW,
                reason=AuthorizationDecisionReason.RULE_MATCH,
                policy=policy,
                entitlements=entitlements,
                matched_rule_id=matches[0].rule_id,
            ),
            binding=binding,
            definition=definition,
            requires_step_up=True,
        )
    return _DurableEvaluation(
        decision=_durable_decision(
            command=command,
            action=action,
            effect=DecisionEffect.ALLOW,
            reason=AuthorizationDecisionReason.RULE_MATCH,
            policy=policy,
            entitlements=entitlements,
            matched_rule_id=matches[0].rule_id,
        ),
        binding=binding,
        definition=definition,
        requires_step_up=False,
    )


def _safe_rollback(uow: object) -> None:
    try:
        if isinstance(uow, AuthorizationUnitOfWork):
            uow.rollback()
    except Exception:
        pass


def _step_up_receipt_fingerprint(receipt: StepUpAuthorizationReceipt) -> str:
    if type(receipt) is not StepUpAuthorizationReceipt:
        _deny()
    material = "|".join(
        (
            receipt.grant_id.fingerprint(),
            receipt.binding.session_id.fingerprint(),
            receipt.binding.action.value,
            receipt.binding.resource.resource_type.value,
            receipt.binding.resource.resource_id.hex,
            receipt.authorized_at.isoformat(timespec="microseconds"),
        )
    )
    return hashlib.sha256(material.encode("ascii")).hexdigest()


class DurableAuthorizationService:
    """Evaluate and durably record authorization without running an action."""

    def __init__(
        self,
        *,
        session_service: AuthenticationService,
        repository: AuthorizationRepository,
        registry: CanonicalAuthorizationRegistry,
        step_up_consumer: SingleUseStepUpGrantConsumer | None,
    ) -> None:
        if type(session_service) is not AuthenticationService:
            raise TypeError("session_service must be an exact AuthenticationService")
        if not isinstance(cast(object, repository), AuthorizationRepository):
            raise TypeError("repository must implement AuthorizationRepository")
        if type(registry) is not CanonicalAuthorizationRegistry:
            raise TypeError("registry must be an exact CanonicalAuthorizationRegistry")
        if step_up_consumer is not None and not isinstance(
            cast(object, step_up_consumer), SingleUseStepUpGrantConsumer
        ):
            raise TypeError("step_up_consumer must implement the ST-0402 surface")
        self._session_service = session_service
        self._repository = repository
        self._registry = registry
        self._step_up_consumer = step_up_consumer

    def _session(self, *, session_id: SessionId, observed_at: datetime) -> Session:
        try:
            session = self._session_service.require_session(
                session_id=session_id, now=observed_at
            )
        except Exception:
            _deny()
        if type(session) is not Session:
            _deny()
        try:
            return snapshot_session(session)
        except Exception:
            _deny()

    @staticmethod
    def _principal(session: Session) -> PrincipalIdentity:
        if type(session.principal) is not AuthenticatedPrincipalIdentity:
            _deny()
        return PrincipalIdentity.admin_user(
            issuer=session.principal.issuer,
            subject=session.principal.subject,
        )

    def _begin(self) -> AuthorizationUnitOfWork:
        try:
            value = self._repository.begin()
        except AuthorizationFailure, AuthorizationRepositoryFailure:
            raise
        except Exception:
            _deny()
        if not isinstance(cast(object, value), AuthorizationUnitOfWork):
            _deny()
        return value

    @staticmethod
    def _record(
        *,
        uow: AuthorizationUnitOfWork,
        command: AuthorizationEvaluationCommand,
        request_digest: str,
        session_fingerprint: str,
        evaluation: _DurableEvaluation,
        step_up_receipt_fingerprint: str | None,
    ) -> AuthorizationCommandResult:
        try:
            result = uow.record_decision(
                command_id=command.command_id,
                request_digest=request_digest,
                session_fingerprint=session_fingerprint,
                decision=evaluation.decision,
                occurred_at=command.observed_at,
                step_up_receipt_fingerprint=step_up_receipt_fingerprint,
            )
            if type(result) is not AuthorizationCommandResult:
                _safe_rollback(uow)
                _deny()
            result = snapshot_authorization_result(result)
            if (
                result.command_id != command.command_id
                or not hmac.compare_digest(result.request_digest, request_digest)
                or not hmac.compare_digest(
                    result.session_fingerprint, session_fingerprint
                )
                or result.decision != evaluation.decision
                or result.audit.occurred_at != command.observed_at
                or result.step_up_receipt_fingerprint != step_up_receipt_fingerprint
            ):
                _safe_rollback(uow)
                _deny()
            uow.commit()
            return result
        except AuthorizationFailure, AuthorizationRepositoryFailure:
            _safe_rollback(uow)
            raise
        except Exception:
            _safe_rollback(uow)
            _deny()

    @staticmethod
    def _existing(
        *,
        uow: AuthorizationUnitOfWork,
        command: AuthorizationEvaluationCommand,
        request_digest: str,
        session_fingerprint: str,
    ) -> AuthorizationCommandResult | None:
        try:
            result = uow.load_command(
                command_id=command.command_id,
                request_digest=request_digest,
            )
        except AuthorizationFailure, AuthorizationRepositoryFailure:
            _safe_rollback(uow)
            raise
        except Exception:
            _safe_rollback(uow)
            _deny()
        if result is None:
            return None
        if type(result) is not AuthorizationCommandResult:
            _safe_rollback(uow)
            _deny()
        result = snapshot_authorization_result(result)
        if (
            result.command_id != command.command_id
            or not hmac.compare_digest(result.request_digest, request_digest)
            or not hmac.compare_digest(result.session_fingerprint, session_fingerprint)
        ):
            _safe_rollback(uow)
            _deny()
        uow.rollback()
        return result

    def evaluate_admin(
        self,
        *,
        session_id: SessionId,
        command: AuthorizationEvaluationCommand,
    ) -> AuthorizationCommandResult:
        """Return one durable allow or deny result; never call a business handler."""

        if (
            type(session_id) is not SessionId
            or type(command) is not AuthorizationEvaluationCommand
        ):
            _deny()
        try:
            session_id = snapshot_session_id(session_id)
            command = snapshot_authorization_evaluation_command(command)
        except Exception:
            _deny()
        session = self._session(session_id=session_id, observed_at=command.observed_at)
        principal = self._principal(session)
        session_fingerprint = session.session_id.fingerprint()
        request_digest = command.request_digest(session_fingerprint=session_fingerprint)
        uow = self._begin()
        try:
            existing = self._existing(
                uow=uow,
                command=command,
                request_digest=request_digest,
                session_fingerprint=session_fingerprint,
            )
            if existing is not None:
                return existing
            evaluation = _evaluate_durable(
                uow=uow,
                registry=self._registry,
                command=command,
                principal=principal,
                step_up_satisfied=False,
                step_up_failed=False,
            )
            if not evaluation.requires_step_up:
                return self._record(
                    uow=uow,
                    command=command,
                    request_digest=request_digest,
                    session_fingerprint=session_fingerprint,
                    evaluation=evaluation,
                    step_up_receipt_fingerprint=None,
                )
            uow.rollback()
        except AuthorizationFailure, AuthorizationRepositoryFailure:
            _safe_rollback(uow)
            raise
        except Exception:
            _safe_rollback(uow)
            _deny()

        binding = evaluation.binding
        if (
            type(binding) is not OperationAuthorizationBinding
            or binding.step_up_action is None
            or binding.step_up_resource_type is None
            or command.step_up_command_id is None
            or command.step_up_grant_id is None
        ):
            _deny()
        receipt_fingerprint: str | None = None
        step_up_failed = False
        try:
            consumer = self._step_up_consumer
            if consumer is None:
                step_up_failed = True
            else:
                consumed = consumer.consume_grant(
                    command_id=command.step_up_command_id,
                    session_id=session_id,
                    grant_id=command.step_up_grant_id,
                    action=binding.step_up_action,
                    resource_type=binding.step_up_resource_type,
                    resource_id=command.target.scope.resource_id,
                    now=command.observed_at,
                )
                if (
                    type(consumed) is not StepUpCommandResult
                    or consumed.operation is not StepUpOperation.CONSUME_GRANT
                    or type(consumed.authorization) is not StepUpAuthorizationReceipt
                ):
                    step_up_failed = True
                else:
                    receipt = consumed.authorization
                    exact_binding = receipt.binding
                    if (
                        not hmac.compare_digest(
                            exact_binding.session_id.fingerprint(),
                            session.session_id.fingerprint(),
                        )
                        or not hmac.compare_digest(
                            exact_binding.issuer.reveal(),
                            session.principal.issuer.reveal(),
                        )
                        or not hmac.compare_digest(
                            exact_binding.subject.reveal(),
                            session.principal.subject.reveal(),
                        )
                        or exact_binding.action is not binding.step_up_action
                        or exact_binding.resource.resource_type
                        is not binding.step_up_resource_type
                        or exact_binding.resource.resource_id
                        != command.target.scope.resource_id
                        or receipt.authorized_at != command.observed_at
                    ):
                        step_up_failed = True
                    else:
                        receipt_fingerprint = _step_up_receipt_fingerprint(receipt)
        except AuthenticationFailure, StepUpFailure:
            step_up_failed = True
        except Exception:
            step_up_failed = True

        refreshed_session = self._session(
            session_id=session_id, observed_at=command.observed_at
        )
        refreshed_principal = self._principal(refreshed_session)
        if (
            not hmac.compare_digest(
                refreshed_session.session_id.fingerprint(), session_fingerprint
            )
            or refreshed_principal != principal
        ):
            _deny()

        final_uow = self._begin()
        try:
            existing = self._existing(
                uow=final_uow,
                command=command,
                request_digest=request_digest,
                session_fingerprint=session_fingerprint,
            )
            if existing is not None:
                return existing
            final_evaluation = _evaluate_durable(
                uow=final_uow,
                registry=self._registry,
                command=command,
                principal=principal,
                step_up_satisfied=not step_up_failed,
                step_up_failed=step_up_failed,
            )
            return self._record(
                uow=final_uow,
                command=command,
                request_digest=request_digest,
                session_fingerprint=session_fingerprint,
                evaluation=final_evaluation,
                step_up_receipt_fingerprint=receipt_fingerprint,
            )
        except AuthorizationFailure, AuthorizationRepositoryFailure:
            _safe_rollback(final_uow)
            raise
        except Exception:
            _safe_rollback(final_uow)
            _deny()

    def require_admin(
        self,
        *,
        session_id: SessionId,
        command: AuthorizationEvaluationCommand,
    ) -> AuthorizationGrant:
        return self.evaluate_admin(session_id=session_id, command=command).grant()

    def recover_admin(
        self,
        *,
        command_id: AuthorizationCommandId,
        session_id: SessionId,
        now: datetime,
    ) -> AuthorizationCommandResult:
        """Recover only after rechecking the exact active ST-0401 session."""

        if (
            type(command_id) is not AuthorizationCommandId
            or type(session_id) is not SessionId
        ):
            _deny()
        try:
            command_id = AuthorizationCommandId(command_id.value)
            session_id = snapshot_session_id(session_id)
        except Exception:
            _deny()
        session = self._session(session_id=session_id, observed_at=now)
        try:
            result = self._repository.recover(command_id)
        except AuthorizationFailure, AuthorizationRepositoryFailure:
            raise
        except Exception:
            _deny()
        if type(result) is not AuthorizationCommandResult:
            _deny()
        result = snapshot_authorization_result(result)
        if result.command_id != command_id or not hmac.compare_digest(
            result.session_fingerprint, session.session_id.fingerprint()
        ):
            _deny()
        return result


@dataclass(frozen=True, slots=True)
class AuthorizationRequirement:
    """Framework-neutral metadata; it never wraps or invokes a handler."""

    operation_id: OperationId

    def __post_init__(self) -> None:
        if type(self.operation_id) is not OperationId:
            raise TypeError("operation_id must be an exact OperationId")


_HandlerT = TypeVar("_HandlerT", bound=Callable[..., object])


def authorization_requirement(
    operation_id: str,
) -> Callable[[_HandlerT], _HandlerT]:
    """Attach immutable enforcement metadata without adding an execution path."""

    requirement = AuthorizationRequirement(operation_id=OperationId(operation_id))

    def decorate(handler: _HandlerT) -> _HandlerT:
        if not callable(handler) or hasattr(
            handler, "__raos_authorization_requirement__"
        ):
            raise TypeError("invalid or already-decorated authorization handler")
        setattr(handler, "__raos_authorization_requirement__", requirement)
        return handler

    return decorate


class AuthorizationEnforcementDependency:
    """Evaluate metadata and return a grant without executing application code."""

    def __init__(self, *, service: DurableAuthorizationService) -> None:
        if type(service) is not DurableAuthorizationService:
            raise TypeError("service must be an exact DurableAuthorizationService")
        self._service = service

    def enforce(
        self,
        *,
        requirement: AuthorizationRequirement,
        session_id: SessionId,
        command: AuthorizationEvaluationCommand,
    ) -> AuthorizationGrant:
        if (
            type(requirement) is not AuthorizationRequirement
            or requirement.operation_id != command.operation_id
        ):
            _deny()
        return self._service.require_admin(session_id=session_id, command=command)


__all__ = [
    "AuthorizationEnforcementDependency",
    "AuthorizationGuard",
    "AuthorizationRequirement",
    "DurableAuthorizationService",
    "authorization_requirement",
]
