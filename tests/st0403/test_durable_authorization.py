"""Durable registry, UoW, step-up, recovery, and hostile-path coverage."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
from threading import Barrier, Thread
from typing import Callable
from uuid import UUID

import pytest

from conftest import (
    ARTICLE_A,
    NOW,
    SITE_A,
    SITE_B,
    authentication_service,
    authorization_principal,
    session,
)
from raos.adapters.generated_st0403_authorization_registry import (
    CANONICAL_AUTHORIZATION_REGISTRY,
)
from raos.adapters.recorded_authorization import (
    RecordedAuthorizationCommitFault,
    RecordedSqliteAuthorizationRepository,
    recorded_authorization_policy_snapshot,
)
from raos.adapters.recorded_step_up import (
    RecordedSqliteStepUpRepository,
    RecordedSyntheticMfaVerifier,
)
from raos.application.iam.authentication import AuthenticationService
from raos.application.iam.authorization import DurableAuthorizationService
from raos.application.iam.step_up import DurableStepUpService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authorization import (
    ActionCode,
    AuthorizationBindingBlockReason,
    AuthorizationBindingResolution,
    AuthorizationBindingStatus,
    AuthorizationCommandId,
    AuthorizationCommandResult,
    AuthorizationDataClass,
    AuthorizationDecision,
    AuthorizationDecisionReason,
    AuthorizationEvaluationCommand,
    AuthorizationFailure,
    AuthorizationRepositoryFailure,
    AuthorizationRepositoryFailureCode,
    AuthorizationRule,
    AuthorizationTarget,
    BusinessRole,
    CorrelationId,
    DecisionEffect,
    EntitlementRevision,
    EntitlementSnapshot,
    IndependentActorEvidence,
    MatrixAction,
    MatrixPermissionDefinition,
    OperationAuthorizationBinding,
    OperationId,
    PermissionScope,
    PolicyRevision,
    PolicySnapshot,
    PrincipalIdentity,
    ResourceScope,
    ResourceScopeKind,
    ResourceState,
    RuleId,
    ScopedBusinessRole,
    ScopedPermission,
)
from raos.domain.iam.step_up import (
    BoundStepUpGrant,
    BoundStepUpGrantId,
    CriticalStepUpAction,
    CriticalStepUpPolicyRegistry,
    StepUpCommandId,
    StepUpCommandResult,
    StepUpResourceType,
)
from raos.domain.iam.authentication import SessionId
from raos.ports.authorization import AuthorizationUnitOfWork


REVENUE_IMPORT = UUID("018f3e90-7b00-7000-8000-000000000406")
PUBLICATION = UUID("018f3e90-7b00-7000-8000-000000000412")
POLICY_REVISION = PolicyRevision("RECORDED:ST0403:POLICY:V1")
ENTITLEMENT_REVISION = EntitlementRevision("RECORDED:ST0403:ENTITLEMENT:V1")


def _private(path: Path) -> Path:
    path.chmod(0o700)
    return path


def _raw(label: str) -> bytes:
    return hashlib.sha256(label.encode("ascii")).digest()


def _step_command(label: str) -> StepUpCommandId:
    return StepUpCommandId.from_bytes(_raw(f"ST0403-STEP-{label}"))


class _Entropy:
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._index = 0

    def token_bytes(self, size: int) -> bytes:
        assert size == 32
        self._index += 1
        return _raw(f"{self._prefix}-{self._index}")


class _RevokingStepUpConsumer:
    def __init__(
        self,
        *,
        delegate: DurableStepUpService,
        authentication: AuthenticationService,
    ) -> None:
        self._delegate = delegate
        self._authentication = authentication

    def consume_grant(
        self,
        *,
        command_id: StepUpCommandId,
        session_id: SessionId,
        grant_id: BoundStepUpGrantId,
        action: CriticalStepUpAction,
        resource_type: StepUpResourceType,
        resource_id: UUID,
        now: datetime,
    ) -> StepUpCommandResult:
        result = self._delegate.consume_grant(
            command_id=command_id,
            session_id=session_id,
            grant_id=grant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            now=now,
        )
        self._authentication.revoke_session(session_id=session_id, now=now)
        return result

    def recover(self, *, command_id: StepUpCommandId) -> StepUpCommandResult:
        return self._delegate.recover(command_id=command_id)


class _FailingStepUpConsumer:
    def consume_grant(
        self,
        *,
        command_id: StepUpCommandId,
        session_id: SessionId,
        grant_id: BoundStepUpGrantId,
        action: CriticalStepUpAction,
        resource_type: StepUpResourceType,
        resource_id: UUID,
        now: datetime,
    ) -> StepUpCommandResult:
        del command_id, session_id, grant_id, action, resource_type, resource_id, now
        raise RuntimeError("secret-private-collaborator-canary") from None

    def recover(self, *, command_id: StepUpCommandId) -> StepUpCommandResult:
        del command_id
        raise RuntimeError("secret-private-collaborator-canary") from None


class _FailingAuthorizationUnitOfWork:
    def __init__(
        self,
        *,
        delegate: AuthorizationUnitOfWork,
        phase: str,
        rollback_callback: Callable[[], None],
        rollback_raises: bool,
    ) -> None:
        self._delegate = delegate
        self._phase = phase
        self._rollback_callback = rollback_callback
        self._rollback_raises = rollback_raises
        self._rolled_back = False

    def _fail_if(self, phase: str) -> None:
        if self._phase == phase:
            raise RuntimeError("secret-private-collaborator-canary") from None

    def load_command(
        self,
        *,
        command_id: AuthorizationCommandId,
        request_digest: str,
    ) -> AuthorizationCommandResult | None:
        self._fail_if("load_command")
        return self._delegate.load_command(
            command_id=command_id,
            request_digest=request_digest,
        )

    def load_policy(self) -> PolicySnapshot:
        self._fail_if("load_policy")
        return self._delegate.load_policy()

    def load_entitlements(self, principal: PrincipalIdentity) -> EntitlementSnapshot:
        self._fail_if("load_entitlements")
        return self._delegate.load_entitlements(principal)

    def load_independent_actor_evidence(
        self, evidence_id: UUID
    ) -> IndependentActorEvidence | None:
        self._fail_if("load_independent_actor_evidence")
        return self._delegate.load_independent_actor_evidence(evidence_id)

    def record_decision(
        self,
        *,
        command_id: AuthorizationCommandId,
        request_digest: str,
        session_fingerprint: str,
        decision: AuthorizationDecision,
        occurred_at: datetime,
        step_up_receipt_fingerprint: str | None,
    ) -> AuthorizationCommandResult:
        self._fail_if("record_decision")
        result = self._delegate.record_decision(
            command_id=command_id,
            request_digest=request_digest,
            session_fingerprint=session_fingerprint,
            decision=decision,
            occurred_at=occurred_at,
            step_up_receipt_fingerprint=step_up_receipt_fingerprint,
        )
        if self._phase == "mutate_result":
            object.__setattr__(result, "request_digest", "f" * 64)
        return result

    def commit(self) -> None:
        self._fail_if("commit")
        self._delegate.commit()

    def rollback(self) -> None:
        if not self._rolled_back:
            self._rolled_back = True
            self._rollback_callback()
            self._delegate.rollback()
        if self._rollback_raises:
            raise RuntimeError("secret-private-rollback-canary") from None


class _FailingAuthorizationRepository:
    def __init__(
        self,
        *,
        delegate: RecordedSqliteAuthorizationRepository,
        phase: str,
        rollback_raises: bool = False,
    ) -> None:
        self._delegate = delegate
        self._phase = phase
        self._rollback_raises = rollback_raises
        self.rollback_calls = 0

    def _noted_rollback(self) -> None:
        self.rollback_calls += 1

    def begin(self) -> AuthorizationUnitOfWork:
        if self._phase == "begin":
            raise RuntimeError("secret-private-collaborator-canary") from None
        return _FailingAuthorizationUnitOfWork(
            delegate=self._delegate.begin(),
            phase=self._phase,
            rollback_callback=self._noted_rollback,
            rollback_raises=self._rollback_raises,
        )

    def recover(self, command_id: AuthorizationCommandId) -> AuthorizationCommandResult:
        if self._phase == "recover":
            raise RuntimeError("secret-private-collaborator-canary") from None
        return self._delegate.recover(command_id)


class _MutatingCallerRepository:
    def __init__(
        self,
        *,
        delegate: RecordedSqliteAuthorizationRepository,
        caller_command: AuthorizationEvaluationCommand,
    ) -> None:
        self._delegate = delegate
        self._caller_command = caller_command

    def begin(self) -> AuthorizationUnitOfWork:
        object.__setattr__(
            self._caller_command,
            "target",
            AuthorizationTarget(
                scope=ResourceScope(
                    kind=ResourceScopeKind.ARTICLE_VERSION,
                    site_id=SITE_B,
                    resource_id=ARTICLE_A,
                ),
                state=ResourceState("DRAFT"),
            ),
        )
        return self._delegate.begin()

    def recover(self, command_id: AuthorizationCommandId) -> AuthorizationCommandResult:
        return self._delegate.recover(command_id)


def _target(
    *,
    kind: ResourceScopeKind = ResourceScopeKind.ARTICLE_VERSION,
    site_id: UUID = SITE_A,
    resource_id: UUID = ARTICLE_A,
    state: str | None = "DRAFT",
) -> AuthorizationTarget:
    return AuthorizationTarget(
        scope=ResourceScope(
            kind=kind,
            site_id=site_id,
            resource_id=resource_id,
        ),
        state=None if state is None else ResourceState(state),
    )


def _rule(
    *,
    operation_id: str = "ED-011",
    action: MatrixAction = MatrixAction.EDIT_ARTICLE_DRAFT,
    role: BusinessRole = BusinessRole.EDITOR,
    permission: str = "editorial:version:write",
    kind: ResourceScopeKind = ResourceScopeKind.ARTICLE_VERSION,
    state: str | None = "DRAFT",
) -> AuthorizationRule:
    return AuthorizationRule(
        rule_id=RuleId(f"RECORDED:ST0403:{operation_id}:{role.value}"),
        role=role,
        permission_scope=PermissionScope(permission),
        action=ActionCode(action.value),
        resource_kind=kind,
        resource_state=None if state is None else ResourceState(state),
    )


def _entitlements(
    *,
    role: BusinessRole = BusinessRole.EDITOR,
    permission: str = "editorial:version:write",
    target: AuthorizationTarget | None = None,
    revision: EntitlementRevision = ENTITLEMENT_REVISION,
) -> EntitlementSnapshot:
    exact = _target() if target is None else target
    return EntitlementSnapshot(
        revision=revision,
        principal=authorization_principal(),
        roles=(ScopedBusinessRole(role=role, scope=exact.scope),),
        permission_scopes=(
            ScopedPermission(
                permission_scope=PermissionScope(permission),
                scope=exact.scope,
            ),
        ),
    )


def _repository(
    root: Path,
    *,
    rule: AuthorizationRule | None = None,
    entitlements: EntitlementSnapshot | None = None,
    fault: RecordedAuthorizationCommitFault | None = None,
) -> RecordedSqliteAuthorizationRepository:
    repository = RecordedSqliteAuthorizationRepository(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=root,
        fault_once_at=fault,
    )
    if rule is not None:
        policy = recorded_authorization_policy_snapshot(
            revision=POLICY_REVISION,
            rules=(rule,),
        )
        repository.install_policy(
            expected_revision="TEST_ONLY:DISABLED", snapshot=policy
        )
    if entitlements is not None:
        repository.install_entitlements(
            principal=authorization_principal(),
            expected_revision=None,
            snapshot=entitlements,
        )
    return repository


def _service(
    repository: RecordedSqliteAuthorizationRepository,
    *,
    step_up: DurableStepUpService | None = None,
) -> DurableAuthorizationService:
    return DurableAuthorizationService(
        session_service=authentication_service(session()),
        repository=repository,
        registry=CANONICAL_AUTHORIZATION_REGISTRY,
        step_up_consumer=step_up,
    )


def _command(
    *,
    label: str = "ED011-1",
    operation_id: str = "ED-011",
    target: AuthorizationTarget | None = None,
    policy_revision: PolicyRevision = POLICY_REVISION,
    entitlement_revision: EntitlementRevision = ENTITLEMENT_REVISION,
    observed_at: datetime = NOW,
    step_up_command_id: StepUpCommandId | None = None,
    step_up_grant_id: BoundStepUpGrantId | None = None,
    evidence_id: UUID | None = None,
) -> AuthorizationEvaluationCommand:
    return AuthorizationEvaluationCommand(
        command_id=AuthorizationCommandId(f"RECORDED:ST0403:COMMAND:{label}"),
        operation_id=OperationId(operation_id),
        target=_target() if target is None else target,
        correlation_id=CorrelationId(f"RECORDED:ST0403:CORRELATION:{label}"),
        expected_policy_revision=policy_revision,
        expected_entitlement_revision=entitlement_revision,
        observed_at=observed_at,
        step_up_command_id=step_up_command_id,
        step_up_grant_id=step_up_grant_id,
        independent_actor_evidence_id=evidence_id,
    )


def _repository_failure(
    code: AuthorizationRepositoryFailureCode, operation: Callable[[], object]
) -> AuthorizationRepositoryFailure:
    with pytest.raises(AuthorizationRepositoryFailure) as caught:
        operation()
    assert caught.value.code is code
    return caught.value


def test_registry_is_complete_closed_and_exposes_typed_blocked_evidence() -> None:
    registry = CANONICAL_AUTHORIZATION_REGISTRY
    assert len(registry.definitions) == 19
    assert {definition.action for definition in registry.definitions} == set(
        MatrixAction
    )
    edit = registry.resolve(OperationId("ED-011"))
    assert edit.status is AuthorizationBindingStatus.ACTIVE_RECORDED
    assert edit.action is MatrixAction.EDIT_ARTICLE_DRAFT
    final = registry.resolve(OperationId("PUBADM-005"))
    assert final.status is AuthorizationBindingStatus.BLOCKED
    assert (
        final.block_reason is AuthorizationBindingBlockReason.RESOURCE_SCOPE_UNRESOLVED
    )
    assert "ST0902_GATE_002_role_and_resource_scope" in final.required_evidence
    kill_switch = registry.resolve(OperationId("OPS-006"))
    assert kill_switch.status is AuthorizationBindingStatus.BLOCKED
    assert (
        kill_switch.block_reason is AuthorizationBindingBlockReason.AMBIGUOUS_OPERATION
    )
    unknown = registry.resolve(OperationId("TEST-UNKNOWN"))
    assert unknown.block_reason is AuthorizationBindingBlockReason.UNMAPPED_OPERATION


def test_direct_runtime_record_construction_rejects_incomplete_security_state() -> None:
    with pytest.raises(AuthorizationFailure):
        MatrixPermissionDefinition(
            action=MatrixAction.FINAL_APPROVE,
            data_class=AuthorizationDataClass.CONFIDENTIAL,
            allowed_roles=(BusinessRole.MANAGING_EDITOR,),
            mfa_required=True,
            step_up_required=True,
            separation_of_duties=True,
            blocked_reason=AuthorizationBindingBlockReason.RESOURCE_SCOPE_UNRESOLVED,
            required_evidence=(),
        )
    with pytest.raises(AuthorizationFailure):
        OperationAuthorizationBinding(
            operation_id=OperationId("TEST-INVALID"),
            action=MatrixAction.EDIT_ARTICLE_DRAFT,
            permission_scope=PermissionScope("editorial:version:write"),
            resource_kind=ResourceScopeKind.ARTICLE_VERSION,
            allowed_states=(ResourceState("DRAFT"),),
            status=AuthorizationBindingStatus.BLOCKED,
        )
    with pytest.raises(AuthorizationFailure):
        OperationAuthorizationBinding(
            operation_id=OperationId("TEST-STEP-UP-ACTION-MISMATCH"),
            action=MatrixAction.COMMIT_REVENUE_IMPORT,
            permission_scope=PermissionScope("finance:revenue:confirm"),
            resource_kind=ResourceScopeKind.REVENUE_IMPORT,
            allowed_states=(ResourceState("DRY_RUN_READY"),),
            status=AuthorizationBindingStatus.ACTIVE_RECORDED,
            step_up_action=CriticalStepUpAction.ROLLBACK,
            step_up_resource_type=StepUpResourceType.REVENUE_IMPORT,
        )
    with pytest.raises(AuthorizationFailure):
        AuthorizationBindingResolution(
            operation_id=OperationId("TEST-INVALID"),
            status=AuthorizationBindingStatus.BLOCKED,
            action=None,
            binding=None,
            block_reason=AuthorizationBindingBlockReason.UNMAPPED_OPERATION,
            required_evidence=(),
        )
    active_binding = CANONICAL_AUTHORIZATION_REGISTRY.resolve(
        OperationId("ED-011")
    ).binding
    assert type(active_binding) is OperationAuthorizationBinding
    with pytest.raises(AuthorizationFailure):
        AuthorizationBindingResolution(
            operation_id=OperationId("ED-011"),
            status=AuthorizationBindingStatus.ACTIVE_RECORDED,
            action=None,
            binding=active_binding,
            block_reason=None,
            required_evidence=(),
        )
    with pytest.raises(AuthorizationFailure):
        AuthorizationBindingResolution(
            operation_id=OperationId("TEST-WRONG-OPERATION"),
            status=AuthorizationBindingStatus.ACTIVE_RECORDED,
            action=MatrixAction.EDIT_ARTICLE_DRAFT,
            binding=active_binding,
            block_reason=None,
            required_evidence=(),
        )
    with pytest.raises(AuthorizationFailure):
        _command(step_up_command_id=_step_command("PARTIAL"))


def test_default_empty_policy_and_unknown_operation_are_durable_denials(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    repository = _repository(root, entitlements=_entitlements())
    service = _service(repository)
    disabled = service.evaluate_admin(
        session_id=session().session_id,
        command=_command(policy_revision=PolicyRevision("TEST_ONLY:DISABLED")),
    )
    assert disabled.decision.effect is DecisionEffect.DENY
    assert disabled.decision.reason is AuthorizationDecisionReason.POLICY_DISABLED

    active = recorded_authorization_policy_snapshot(
        revision=POLICY_REVISION, rules=(_rule(),)
    )
    repository.install_policy(expected_revision="TEST_ONLY:DISABLED", snapshot=active)
    unmapped = service.evaluate_admin(
        session_id=session().session_id,
        command=_command(label="UNKNOWN", operation_id="TEST-UNKNOWN"),
    )
    assert unmapped.decision.effect is DecisionEffect.DENY
    assert unmapped.decision.reason is AuthorizationDecisionReason.OPERATION_UNMAPPED
    assert [event.sequence for event in repository.audit_snapshot()] == [1, 2]


def test_exact_allow_is_idempotent_restartable_and_does_not_execute_action(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    repository = _repository(root, rule=_rule(), entitlements=_entitlements())
    service = _service(repository)
    command = _command()
    first = service.evaluate_admin(session_id=session().session_id, command=command)
    duplicate = service.evaluate_admin(session_id=session().session_id, command=command)
    assert duplicate == first
    assert first.decision.effect is DecisionEffect.ALLOW
    assert first.decision.reason is AuthorizationDecisionReason.RULE_MATCH
    assert first.grant().target == command.target
    assert len(repository.audit_snapshot()) == 1
    reopened = RecordedSqliteAuthorizationRepository(
        environment=RuntimeEnvironment.ENV_DEV, private_root=root
    )
    recovered = _service(reopened).recover_admin(
        command_id=command.command_id,
        session_id=session().session_id,
        now=NOW,
    )
    assert recovered == first
    assert (
        root / "st0403-recorded-authorization.sqlite3"
    ).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    ("requested", "operation_id"),
    (
        (_target(site_id=SITE_B), "ED-011"),
        (_target(resource_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")), "ED-011"),
        (_target(state="APPROVED"), "ED-011"),
        (_target(kind=ResourceScopeKind.ARTICLE), "ED-011"),
        (_target(), "PUBADM-004"),
        (_target(), "PUBADM-005"),
    ),
)
def test_horizontal_resource_state_kind_action_and_blocked_paths_deny(
    tmp_path: Path, requested: AuthorizationTarget, operation_id: str
) -> None:
    root = _private(tmp_path)
    repository = _repository(root, rule=_rule(), entitlements=_entitlements())
    result = _service(repository).evaluate_admin(
        session_id=session().session_id,
        command=_command(
            label=f"DENY-{operation_id}-{requested.scope.site_id.hex[:4]}",
            operation_id=operation_id,
            target=requested,
        ),
    )
    assert result.decision.effect is DecisionEffect.DENY
    assert result.decision.matched_rule_id is None


@pytest.mark.parametrize(
    "snapshot",
    (
        _entitlements(role=BusinessRole.REVIEWER),
        _entitlements(permission="publishing:review:decide"),
    ),
)
def test_vertical_role_and_permission_mismatch_deny(
    tmp_path: Path, snapshot: EntitlementSnapshot
) -> None:
    root = _private(tmp_path)
    repository = _repository(root, rule=_rule(), entitlements=snapshot)
    result = _service(repository).evaluate_admin(
        session_id=session().session_id,
        command=_command(label=f"VERTICAL-{snapshot.roles[0].role.value}"),
    )
    assert result.decision.effect is DecisionEffect.DENY
    assert result.decision.reason is AuthorizationDecisionReason.NO_MATCH


def test_stale_policy_and_entitlement_revisions_deny_without_zero_coercion(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    repository = _repository(root, rule=_rule(), entitlements=_entitlements())
    service = _service(repository)
    stale_policy = service.evaluate_admin(
        session_id=session().session_id,
        command=_command(
            label="STALE-POLICY",
            policy_revision=PolicyRevision("RECORDED:ST0403:POLICY:STALE"),
        ),
    )
    stale_entitlement = service.evaluate_admin(
        session_id=session().session_id,
        command=_command(
            label="STALE-ENTITLEMENT",
            entitlement_revision=EntitlementRevision(
                "RECORDED:ST0403:ENTITLEMENT:STALE"
            ),
        ),
    )
    assert stale_policy.decision.reason is AuthorizationDecisionReason.STALE_POLICY
    assert (
        stale_entitlement.decision.reason
        is AuthorizationDecisionReason.STALE_ENTITLEMENTS
    )


def test_command_reuse_with_changed_target_conflicts_without_second_audit(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    repository = _repository(root, rule=_rule(), entitlements=_entitlements())
    service = _service(repository)
    service.evaluate_admin(session_id=session().session_id, command=_command())
    _repository_failure(
        AuthorizationRepositoryFailureCode.COMMAND_CONFLICT,
        lambda: service.evaluate_admin(
            session_id=session().session_id,
            command=_command(target=_target(site_id=SITE_B)),
        ),
    )
    assert len(repository.audit_snapshot()) == 1


def _step_up_service(root: Path) -> DurableStepUpService:
    return DurableStepUpService(
        session_service=authentication_service(session()),
        repository=RecordedSqliteStepUpRepository(
            environment=RuntimeEnvironment.ENV_DEV,
            private_root=root,
        ),
        verifier=RecordedSyntheticMfaVerifier(environment=RuntimeEnvironment.ENV_DEV),
        entropy=_Entropy("ST0403-STEP-UP"),
        policy=CriticalStepUpPolicyRegistry(),
    )


def _issue_revenue_grant(
    service: DurableStepUpService, *, resource_id: UUID
) -> BoundStepUpGrant:
    begun = service.begin_challenge(
        command_id=_step_command("BEGIN"),
        session_id=session().session_id,
        action=CriticalStepUpAction.COMMIT_REVENUE_IMPORT,
        resource_type=StepUpResourceType.REVENUE_IMPORT,
        resource_id=resource_id,
        now=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    assert begun.challenge is not None
    verified = service.verify_challenge(
        command_id=_step_command("VERIFY"),
        session_id=session().session_id,
        challenge_id=begun.challenge.challenge_id,
        now=NOW + timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=9),
    )
    assert verified.verification is not None
    issued = service.issue_grant(
        command_id=_step_command("ISSUE"),
        session_id=session().session_id,
        receipt_id=verified.verification.receipt_id,
        now=NOW + timedelta(minutes=2),
        expires_at=NOW + timedelta(minutes=8),
    )
    assert issued.grant is not None
    return issued.grant


def _revenue_fixture(
    root: Path,
) -> tuple[AuthorizationTarget, RecordedSqliteAuthorizationRepository]:
    target = _target(
        kind=ResourceScopeKind.REVENUE_IMPORT,
        resource_id=REVENUE_IMPORT,
        state="DRY_RUN_READY",
    )
    rule = _rule(
        operation_id="FIN-006",
        action=MatrixAction.COMMIT_REVENUE_IMPORT,
        role=BusinessRole.ANALYST,
        permission="finance:revenue:confirm",
        kind=ResourceScopeKind.REVENUE_IMPORT,
        state="DRY_RUN_READY",
    )
    entitlements = _entitlements(
        role=BusinessRole.ANALYST,
        permission="finance:revenue:confirm",
        target=target,
    )
    repository = _repository(root, rule=rule, entitlements=entitlements)
    return target, repository


def test_exact_st0402_grant_is_required_consumed_once_and_cross_resource_denies(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    target, repository = _revenue_fixture(root)
    step_up = _step_up_service(root)
    service = _service(repository, step_up=step_up)
    missing = service.evaluate_admin(
        session_id=session().session_id,
        command=_command(
            label="FIN-MISSING",
            operation_id="FIN-006",
            target=target,
            observed_at=NOW + timedelta(minutes=3),
        ),
    )
    assert missing.decision.reason is AuthorizationDecisionReason.STEP_UP_REQUIRED
    grant = _issue_revenue_grant(step_up, resource_id=REVENUE_IMPORT)
    command = _command(
        label="FIN-ALLOW",
        operation_id="FIN-006",
        target=target,
        observed_at=NOW + timedelta(minutes=3),
        step_up_command_id=_step_command("CONSUME"),
        step_up_grant_id=grant.grant_id,
    )
    allowed = service.evaluate_admin(session_id=session().session_id, command=command)
    assert allowed.decision.effect is DecisionEffect.ALLOW
    assert allowed.step_up_receipt_fingerprint is not None
    replay = service.evaluate_admin(
        session_id=session().session_id,
        command=_command(
            label="FIN-REPLAY",
            operation_id="FIN-006",
            target=target,
            observed_at=NOW + timedelta(minutes=3),
            step_up_command_id=_step_command("CONSUME-REPLAY"),
            step_up_grant_id=grant.grant_id,
        ),
    )
    assert replay.decision.reason is AuthorizationDecisionReason.STEP_UP_FAILURE

    other_root = tmp_path / "other"
    other_root.mkdir(mode=0o700)
    other_target, other_repository = _revenue_fixture(other_root)
    other_step_up = _step_up_service(other_root)
    wrong_grant = _issue_revenue_grant(other_step_up, resource_id=PUBLICATION)
    cross_resource = _service(other_repository, step_up=other_step_up).evaluate_admin(
        session_id=session().session_id,
        command=_command(
            label="FIN-CROSS",
            operation_id="FIN-006",
            target=other_target,
            observed_at=NOW + timedelta(minutes=3),
            step_up_command_id=_step_command("CROSS-CONSUME"),
            step_up_grant_id=wrong_grant.grant_id,
        ),
    )
    assert cross_resource.decision.reason is AuthorizationDecisionReason.STEP_UP_FAILURE


def test_step_up_collaborator_exception_is_audited_as_closed_sanitized_denial(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    target, repository = _revenue_fixture(root)
    service = DurableAuthorizationService(
        session_service=authentication_service(session()),
        repository=repository,
        registry=CANONICAL_AUTHORIZATION_REGISTRY,
        step_up_consumer=_FailingStepUpConsumer(),
    )
    grant_id = BoundStepUpGrantId.from_bytes(_raw("FAILING-COLLABORATOR-GRANT"))
    result = service.evaluate_admin(
        session_id=session().session_id,
        command=_command(
            label="FIN-COLLABORATOR-FAILURE",
            operation_id="FIN-006",
            target=target,
            observed_at=NOW + timedelta(minutes=3),
            step_up_command_id=_step_command("FAILING-COLLABORATOR-CONSUME"),
            step_up_grant_id=grant_id,
        ),
    )
    assert result.decision.effect is DecisionEffect.DENY
    assert result.decision.reason is AuthorizationDecisionReason.STEP_UP_FAILURE
    assert result.step_up_receipt_fingerprint is None
    assert len(repository.audit_snapshot()) == 1
    rendered = f"{result!s} {result!r} {repository.audit_snapshot()!r}"
    assert "secret-private-collaborator-canary" not in rendered
    assert grant_id.reveal() not in rendered


@pytest.mark.parametrize(
    "phase",
    (
        "begin",
        "load_command",
        "load_policy",
        "load_entitlements",
        "record_decision",
        "commit",
    ),
)
def test_repository_collaborator_exceptions_are_sanitized_and_rolled_back(
    tmp_path: Path,
    phase: str,
) -> None:
    root = _private(tmp_path)
    repository = _repository(root, rule=_rule(), entitlements=_entitlements())
    failing = _FailingAuthorizationRepository(
        delegate=repository,
        phase=phase,
        rollback_raises=phase == "load_policy",
    )
    service = DurableAuthorizationService(
        session_service=authentication_service(session()),
        repository=failing,
        registry=CANONICAL_AUTHORIZATION_REGISTRY,
        step_up_consumer=None,
    )
    with pytest.raises(AuthorizationFailure) as caught:
        service.evaluate_admin(
            session_id=session().session_id,
            command=_command(label=f"COLLABORATOR-{phase}"),
        )
    rendered = f"{caught.value!s} {caught.value!r}"
    assert "secret-private-collaborator-canary" not in rendered
    assert "secret-private-rollback-canary" not in rendered
    assert failing.rollback_calls == (0 if phase == "begin" else 1)
    assert repository.audit_snapshot() == ()


def test_recovery_collaborator_exception_is_sanitized_without_state_change(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    repository = _repository(root, rule=_rule(), entitlements=_entitlements())
    command = _command(label="RECOVERY-COLLABORATOR")
    _service(repository).evaluate_admin(
        session_id=session().session_id,
        command=command,
    )
    failing = _FailingAuthorizationRepository(
        delegate=repository,
        phase="recover",
    )
    service = DurableAuthorizationService(
        session_service=authentication_service(session()),
        repository=failing,
        registry=CANONICAL_AUTHORIZATION_REGISTRY,
        step_up_consumer=None,
    )
    with pytest.raises(AuthorizationFailure) as caught:
        service.recover_admin(
            command_id=command.command_id,
            session_id=session().session_id,
            now=NOW,
        )
    rendered = f"{caught.value!s} {caught.value!r}"
    assert "secret-private-collaborator-canary" not in rendered
    assert len(repository.audit_snapshot()) == 1


def test_session_revoked_during_step_up_is_rechecked_before_decision_commit(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    target, repository = _revenue_fixture(root)
    step_up = _step_up_service(root)
    grant = _issue_revenue_grant(step_up, resource_id=REVENUE_IMPORT)
    authentication = authentication_service(session())
    service = DurableAuthorizationService(
        session_service=authentication,
        repository=repository,
        registry=CANONICAL_AUTHORIZATION_REGISTRY,
        step_up_consumer=_RevokingStepUpConsumer(
            delegate=step_up,
            authentication=authentication,
        ),
    )
    with pytest.raises(AuthorizationFailure):
        service.evaluate_admin(
            session_id=session().session_id,
            command=_command(
                label="FIN-REVOKED-DURING-STEP-UP",
                operation_id="FIN-006",
                target=target,
                observed_at=NOW + timedelta(minutes=3),
                step_up_command_id=_step_command("REVOKING-CONSUME"),
                step_up_grant_id=grant.grant_id,
            ),
        )
    assert repository.audit_snapshot() == ()


def test_sod_evidence_is_immutable_site_resource_bound_and_self_comparable(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    repository = _repository(root, rule=_rule(), entitlements=_entitlements())
    evidence = IndependentActorEvidence(
        evidence_id=UUID("018f3e90-7b00-7000-8000-000000000403"),
        actor_fingerprint=authorization_principal().fingerprint,
        action=MatrixAction.FINAL_APPROVE,
        operation_id=OperationId("PUBADM-005"),
        site_id=SITE_A,
        resource_id=ARTICLE_A,
        evidence_snapshot_sha256="1" * 64,
        recorded_at=NOW,
    )
    repository.append_independent_actor_evidence(evidence)
    repository.append_independent_actor_evidence(evidence)
    uow = repository.begin()
    loaded = uow.load_independent_actor_evidence(evidence.evidence_id)
    uow.rollback()
    assert loaded == evidence
    assert loaded is not None
    assert loaded.actor_fingerprint == authorization_principal().fingerprint
    final = _service(repository).evaluate_admin(
        session_id=session().session_id,
        command=_command(
            label="FINAL-BLOCKED",
            operation_id="PUBADM-005",
            target=_target(state="HUMAN_REVIEW"),
            evidence_id=evidence.evidence_id,
        ),
    )
    assert final.decision.reason is AuthorizationDecisionReason.OPERATION_BLOCKED


def test_revision_cas_snapshot_immutability_and_concurrent_writer_safety(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    repository = _repository(root, rule=_rule(), entitlements=_entitlements())
    second = recorded_authorization_policy_snapshot(
        revision=PolicyRevision("RECORDED:ST0403:POLICY:V2"), rules=(_rule(),)
    )
    repository.install_policy(expected_revision=POLICY_REVISION.value, snapshot=second)
    _repository_failure(
        AuthorizationRepositoryFailureCode.REVISION_CONFLICT,
        lambda: repository.install_policy(
            expected_revision=POLICY_REVISION.value,
            snapshot=recorded_authorization_policy_snapshot(
                revision=PolicyRevision("RECORDED:ST0403:POLICY:V3"),
                rules=(_rule(),),
            ),
        ),
    )
    with sqlite3.connect(root / "st0403-recorded-authorization.sqlite3") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM recorded_authorization_policy_snapshot"
        ).fetchone() == (3,)

    race_root = tmp_path / "race"
    race_root.mkdir(mode=0o700)
    race = _repository(race_root, rule=_rule(), entitlements=_entitlements())
    barrier = Barrier(2)
    outcomes: list[str] = []

    def writer(label: str) -> None:
        local = RecordedSqliteAuthorizationRepository(
            environment=RuntimeEnvironment.ENV_DEV, private_root=race_root
        )
        candidate = recorded_authorization_policy_snapshot(
            revision=PolicyRevision(f"RECORDED:ST0403:POLICY:{label}"),
            rules=(_rule(),),
        )
        barrier.wait()
        try:
            local.install_policy(
                expected_revision=POLICY_REVISION.value,
                snapshot=candidate,
            )
            outcomes.append("COMMITTED")
        except AuthorizationRepositoryFailure as error:
            outcomes.append(error.code.value)

    threads = [Thread(target=writer, args=(label,)) for label in ("RACEA", "RACEB")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count("COMMITTED") == 1
    assert len(outcomes) == 2
    assert set(outcomes) <= {
        "COMMITTED",
        AuthorizationRepositoryFailureCode.REVISION_CONFLICT.value,
        AuthorizationRepositoryFailureCode.STORAGE_FAILURE.value,
    }
    assert race.audit_snapshot() == ()


def test_before_and_after_commit_faults_are_recoverable_without_blind_retry(
    tmp_path: Path,
) -> None:
    before_root = tmp_path / "before"
    before_root.mkdir(mode=0o700)
    _repository(before_root, rule=_rule(), entitlements=_entitlements())
    before_repository = RecordedSqliteAuthorizationRepository(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=before_root,
        fault_once_at=RecordedAuthorizationCommitFault.BEFORE_COMMIT,
    )
    _repository_failure(
        AuthorizationRepositoryFailureCode.STORAGE_FAILURE,
        lambda: _service(before_repository).evaluate_admin(
            session_id=session().session_id, command=_command(label="BEFORE")
        ),
    )
    assert before_repository.audit_snapshot() == ()

    after_root = tmp_path / "after"
    after_root.mkdir(mode=0o700)
    _repository(after_root, rule=_rule(), entitlements=_entitlements())
    after_repository = RecordedSqliteAuthorizationRepository(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=after_root,
        fault_once_at=RecordedAuthorizationCommitFault.AFTER_COMMIT,
    )
    command = _command(label="AFTER")
    _repository_failure(
        AuthorizationRepositoryFailureCode.STORAGE_COMMIT_UNKNOWN,
        lambda: _service(after_repository).evaluate_admin(
            session_id=session().session_id, command=command
        ),
    )
    recovered = _service(after_repository).recover_admin(
        command_id=command.command_id,
        session_id=session().session_id,
        now=NOW,
    )
    assert recovered.decision.effect is DecisionEffect.ALLOW
    assert len(after_repository.audit_snapshot()) == 1


def test_tamper_and_cross_session_recovery_fail_closed(tmp_path: Path) -> None:
    root = _private(tmp_path)
    repository = _repository(root, rule=_rule(), entitlements=_entitlements())
    command = _command(label="TAMPER")
    _service(repository).evaluate_admin(
        session_id=session().session_id, command=command
    )
    with sqlite3.connect(root / "st0403-recorded-authorization.sqlite3") as connection:
        with pytest.raises(sqlite3.IntegrityError, match="ST0403_APPEND_ONLY"):
            connection.execute(
                "UPDATE recorded_authorization_audit SET digest=? WHERE sequence=1",
                ("f" * 64,),
            )
        connection.execute("DROP TRIGGER recorded_authorization_audit_no_update")
        connection.execute(
            "UPDATE recorded_authorization_audit SET digest=? WHERE sequence=1",
            ("f" * 64,),
        )
    _repository_failure(
        AuthorizationRepositoryFailureCode.TAMPER_DETECTED,
        lambda: RecordedSqliteAuthorizationRepository(
            environment=RuntimeEnvironment.ENV_DEV, private_root=root
        ),
    )

    clean_root = tmp_path / "clean"
    clean_root.mkdir(mode=0o700)
    clean = _repository(clean_root, rule=_rule(), entitlements=_entitlements())
    other_command = _command(label="CROSS-SESSION")
    _service(clean).evaluate_admin(
        session_id=session().session_id, command=other_command
    )
    other_session = session(index=9)
    with pytest.raises(AuthorizationFailure):
        DurableAuthorizationService(
            session_service=authentication_service(other_session),
            repository=clean,
            registry=CANONICAL_AUTHORIZATION_REGISTRY,
            step_up_consumer=None,
        ).recover_admin(
            command_id=other_command.command_id,
            session_id=other_session.session_id,
            now=NOW,
        )


def test_active_snapshot_pointer_tamper_fails_closed(tmp_path: Path) -> None:
    policy_root = tmp_path / "policy-pointer"
    policy_root.mkdir(mode=0o700)
    _repository(policy_root, rule=_rule(), entitlements=_entitlements())
    policy_database = policy_root / "st0403-recorded-authorization.sqlite3"
    with sqlite3.connect(policy_database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="ST0403_APPEND_ONLY"):
            connection.execute(
                "UPDATE recorded_authorization_active_policy SET revision=? "
                "WHERE activation_sequence=(SELECT MAX(activation_sequence) "
                "FROM recorded_authorization_active_policy)",
                ("TEST_ONLY:DISABLED",),
            )
        connection.execute(
            "DROP TRIGGER recorded_authorization_active_policy_no_update"
        )
        connection.execute(
            "UPDATE recorded_authorization_active_policy SET revision=? "
            "WHERE activation_sequence=(SELECT MAX(activation_sequence) "
            "FROM recorded_authorization_active_policy)",
            ("TEST_ONLY:DISABLED",),
        )
    _repository_failure(
        AuthorizationRepositoryFailureCode.TAMPER_DETECTED,
        lambda: RecordedSqliteAuthorizationRepository(
            environment=RuntimeEnvironment.ENV_DEV,
            private_root=policy_root,
        ),
    )

    entitlement_root = tmp_path / "entitlement-pointer"
    entitlement_root.mkdir(mode=0o700)
    _repository(entitlement_root, rule=_rule(), entitlements=_entitlements())
    entitlement_database = entitlement_root / "st0403-recorded-authorization.sqlite3"
    with sqlite3.connect(entitlement_database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="ST0403_APPEND_ONLY"):
            connection.execute(
                "UPDATE recorded_authorization_active_entitlement SET record_sha256=?",
                ("f" * 64,),
            )
        connection.execute(
            "DROP TRIGGER recorded_authorization_active_entitlement_no_update"
        )
        connection.execute(
            "UPDATE recorded_authorization_active_entitlement SET record_sha256=?",
            ("f" * 64,),
        )
    _repository_failure(
        AuthorizationRepositoryFailureCode.TAMPER_DETECTED,
        lambda: RecordedSqliteAuthorizationRepository(
            environment=RuntimeEnvironment.ENV_DEV,
            private_root=entitlement_root,
        ),
    )


def test_weakened_sqlite_constraint_schema_is_rejected_before_use(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    database = root / "st0403-recorded-authorization.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE recorded_authorization_metadata ("
            "singleton INTEGER PRIMARY KEY, schema_version TEXT NOT NULL)"
        )
    database.chmod(0o600)
    _repository_failure(
        AuthorizationRepositoryFailureCode.TAMPER_DETECTED,
        lambda: RecordedSqliteAuthorizationRepository(
            environment=RuntimeEnvironment.ENV_DEV,
            private_root=root,
        ),
    )


def test_preexisting_empty_partial_and_foreign_databases_are_never_initialized(
    tmp_path: Path,
) -> None:
    roots = tuple(tmp_path / name for name in ("empty", "partial", "foreign"))
    for root in roots:
        root.mkdir(mode=0o700)

    empty_database = roots[0] / "st0403-recorded-authorization.sqlite3"
    empty_database.touch(mode=0o600)
    empty_database.chmod(0o600)

    partial_database = roots[1] / "st0403-recorded-authorization.sqlite3"
    with sqlite3.connect(partial_database) as connection:
        connection.execute("CREATE TABLE partial_owner_table (value TEXT)")
    partial_database.chmod(0o600)

    foreign_database = roots[2] / "st0403-recorded-authorization.sqlite3"
    with sqlite3.connect(foreign_database) as connection:
        connection.execute("PRAGMA application_id = 20260825")
        connection.execute("PRAGMA user_version = 77")
        connection.execute("CREATE TABLE foreign_owner_table (value TEXT) STRICT")
    foreign_database.chmod(0o600)

    for root in roots:
        _repository_failure(
            AuthorizationRepositoryFailureCode.TAMPER_DETECTED,
            lambda: RecordedSqliteAuthorizationRepository(
                environment=RuntimeEnvironment.ENV_DEV,
                private_root=root,
            ),
        )
        with sqlite3.connect(
            root / "st0403-recorded-authorization.sqlite3"
        ) as connection:
            names = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert not any(name.startswith("recorded_authorization_") for name in names)


def test_schema_v2_is_strict_append_only_and_has_zero_external_actions(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    repository = _repository(root, rule=_rule(), entitlements=_entitlements())
    assert type(repository.external_action_count) is int
    assert repository.external_action_count == 0
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("PRAGMA application_id").fetchone() == (1380400302,)
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        strict = {
            str(row[1]): int(row[5])
            for row in connection.execute("PRAGMA table_list").fetchall()
            if str(row[1]).startswith("recorded_authorization_")
        }
        assert strict and set(strict.values()) == {1}
        append_only = {
            str(row[0])
            for row in connection.execute(
                "SELECT tbl_name FROM sqlite_master WHERE type='trigger' "
                "AND name LIKE '%_no_update'"
            ).fetchall()
        }
        assert append_only == set(strict) - {"recorded_authorization_metadata"}


def test_process_anchor_rejects_valid_prefix_rollback_and_file_replacement(
    tmp_path: Path,
) -> None:
    rollback_root = tmp_path / "rollback"
    rollback_root.mkdir(mode=0o700)
    rollback_repository = _repository(
        rollback_root, rule=_rule(), entitlements=_entitlements()
    )
    database = rollback_repository.database_path
    prefix = rollback_root / "valid-prefix.sqlite3"
    shutil.copyfile(database, prefix)
    _service(rollback_repository).evaluate_admin(
        session_id=session().session_id,
        command=_command(label="ROLLBACK-ANCHOR"),
    )
    assert len(rollback_repository.audit_snapshot()) == 1
    shutil.copyfile(prefix, database)
    _repository_failure(
        AuthorizationRepositoryFailureCode.TAMPER_DETECTED,
        rollback_repository.audit_snapshot,
    )

    replacement_root = tmp_path / "replacement"
    replacement_root.mkdir(mode=0o700)
    replacement_repository = _repository(
        replacement_root, rule=_rule(), entitlements=_entitlements()
    )
    replacement = replacement_root / "replacement.sqlite3"
    shutil.copyfile(replacement_repository.database_path, replacement)
    replacement.chmod(0o600)
    os.replace(replacement, replacement_repository.database_path)
    _repository_failure(
        AuthorizationRepositoryFailureCode.STORAGE_FAILURE,
        replacement_repository.audit_snapshot,
    )


def test_hostile_caller_and_result_mutation_are_detached_or_rejected(
    tmp_path: Path,
) -> None:
    caller_root = tmp_path / "caller"
    caller_root.mkdir(mode=0o700)
    caller_repository = _repository(
        caller_root, rule=_rule(), entitlements=_entitlements()
    )
    caller_command = _command(label="CALLER-MUTATION")
    caller_service = DurableAuthorizationService(
        session_service=authentication_service(session()),
        repository=_MutatingCallerRepository(
            delegate=caller_repository,
            caller_command=caller_command,
        ),
        registry=CANONICAL_AUTHORIZATION_REGISTRY,
        step_up_consumer=None,
    )
    caller_result = caller_service.evaluate_admin(
        session_id=session().session_id,
        command=caller_command,
    )
    assert caller_result.decision.effect is DecisionEffect.ALLOW
    assert caller_result.decision.target.scope.site_id == SITE_A
    assert caller_command.target.scope.site_id == SITE_B

    result_root = tmp_path / "result"
    result_root.mkdir(mode=0o700)
    result_repository = _repository(
        result_root, rule=_rule(), entitlements=_entitlements()
    )
    hostile_repository = _FailingAuthorizationRepository(
        delegate=result_repository,
        phase="mutate_result",
    )
    with pytest.raises(AuthorizationRepositoryFailure) as caught:
        DurableAuthorizationService(
            session_service=authentication_service(session()),
            repository=hostile_repository,
            registry=CANONICAL_AUTHORIZATION_REGISTRY,
            step_up_consumer=None,
        ).evaluate_admin(
            session_id=session().session_id,
            command=_command(label="HOSTILE-RESULT"),
        )
    assert caught.value.code is AuthorizationRepositoryFailureCode.TAMPER_DETECTED
    assert result_repository.audit_snapshot() == ()


def test_private_root_rejects_symlinked_ancestor_component(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir(mode=0o700)
    private = real_parent / "private"
    private.mkdir(mode=0o700)
    linked_parent = tmp_path / "linked-parent"
    os.symlink(real_parent, linked_parent)
    _repository_failure(
        AuthorizationRepositoryFailureCode.STORAGE_FAILURE,
        lambda: RecordedSqliteAuthorizationRepository(
            environment=RuntimeEnvironment.ENV_DEV,
            private_root=linked_parent / "private",
        ),
    )


@pytest.mark.parametrize(
    "environment",
    (
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ),
)
def test_recorded_repository_rejects_external_environments(
    tmp_path: Path, environment: RuntimeEnvironment
) -> None:
    root = _private(tmp_path)
    _repository_failure(
        AuthorizationRepositoryFailureCode.DEVELOPMENT_ONLY,
        lambda: RecordedSqliteAuthorizationRepository(
            environment=environment, private_root=root
        ),
    )
