"""Focused allowlist and hostile-path tests for ST-0403."""

from __future__ import annotations

from datetime import timedelta
import inspect
import pickle
from typing import cast
from uuid import UUID

import pytest

from .support import (
    ARTICLE_A,
    CATEGORY_A,
    NOW,
    SITE_A,
    SITE_B,
    assert_denied,
    authentication_service,
    authorization_principal,
    entitlements,
    guard,
    rule,
    scope,
    session,
    target,
)
from raos.adapters.development_authorization import (
    DevelopmentAuthorizationPolicySource,
    DevelopmentEntitlementSource,
    InMemoryAuthorizationDecisionSink,
)
from raos.application.iam.authorization import AuthorizationGuard
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import Session, SessionId
from raos.domain.iam.authorization import (
    ActionCode,
    AuthorizationDecision,
    AuthorizationDecisionReason,
    AuthorizationFailure,
    AuthorizationFailureCode,
    AuthorizationGrant,
    AuthorizationSurface,
    AuthorizationTarget,
    BusinessRole,
    CorrelationId,
    DecisionEffect,
    EntitlementSnapshot,
    EntitlementRevision,
    PermissionScope,
    PolicyMode,
    PolicyRevision,
    PolicySnapshot,
    PrincipalIdentity,
    PrincipalKind,
    ResourceScope,
    ResourceScopeKind,
    ResourceState,
    ScopedBusinessRole,
    ScopedPermission,
    ServicePrincipalName,
)
from raos.ports.authorization import (
    AuthorizationDecisionSink,
    AuthorizationPolicySource,
    EntitlementSource,
)


ACTION = ActionCode("TEST_ONLY:EDIT_ARTICLE")
CORRELATION = CorrelationId("TEST_ONLY:CORRELATION_1")


def _require(
    authorization_guard: AuthorizationGuard,
    *,
    active_session_id: SessionId | None = None,
    action: ActionCode = ACTION,
    requested_target: AuthorizationTarget | None = None,
) -> AuthorizationGrant:
    return authorization_guard.require_admin_user(
        session_id=session().session_id
        if active_session_id is None
        else active_session_id,
        now=NOW,
        action=action,
        target=target() if requested_target is None else requested_target,
        correlation_id=CORRELATION,
    )


def test_disabled_empty_default_denies_and_records_once_without_entitlements() -> None:
    authorization_guard, sink = guard(mode=PolicyMode.DISABLED)

    failure = assert_denied(lambda: _require(authorization_guard))

    assert failure.code is AuthorizationFailureCode.DENIED
    assert len(sink.decisions) == 1
    assert sink.decisions[0].effect is DecisionEffect.DENY
    assert sink.decisions[0].matched_rule_id is None


def test_exact_synthetic_match_records_then_returns_one_redacted_grant() -> None:
    exact_rule = rule()
    exact_entitlements = entitlements()
    authorization_guard, sink = guard(
        rules=(exact_rule,), snapshots=(exact_entitlements,)
    )

    grant = _require(authorization_guard)

    assert grant.matched_rule_id == exact_rule.rule_id
    assert len(sink.decisions) == 1
    decision = sink.decisions[0]
    assert decision.effect is DecisionEffect.ALLOW
    assert decision.matched_rule_id == exact_rule.rule_id
    assert decision.action == ACTION
    assert decision.target == target()
    assert "TEST_ONLY" not in repr(grant)
    with pytest.raises(TypeError, match="serialization is not supported"):
        pickle.dumps(grant)


def test_direct_grant_value_is_explicitly_in_process_tcb_and_never_an_executor() -> (
    None
):
    direct_decision = AuthorizationDecision(
        correlation_id=CORRELATION,
        effect=DecisionEffect.ALLOW,
        reason=AuthorizationDecisionReason.RULE_MATCH,
        policy_revision=PolicyRevision("TEST_ONLY:DIRECT_VALUE_POLICY"),
        policy_fingerprint="1" * 64,
        entitlement_revision=EntitlementRevision("TEST_ONLY:DIRECT_VALUE_ENTITLEMENT"),
        matched_rule_id=rule().rule_id,
        action=ACTION,
        target=target(),
    )
    direct_value = AuthorizationGrant(recorded_decision=direct_decision)
    assert direct_value.action == ACTION
    assert not callable(direct_value)
    assert not hasattr(direct_value, "execute")
    assert not hasattr(direct_value, "service_provenance")


def test_action_scope_role_state_and_kind_mismatches_deny() -> None:
    exact_scope = scope()
    cases = (
        (
            (rule(),),
            (entitlements(),),
            ActionCode("TEST_ONLY:VIEW_ARTICLE"),
            target(),
        ),
        (
            (rule(),),
            (
                entitlements(
                    permissions=(
                        ScopedPermission(
                            permission_scope=PermissionScope("TEST_ONLY:ARTICLE_READ"),
                            scope=exact_scope,
                        ),
                    )
                ),
            ),
            ACTION,
            target(),
        ),
        (
            (rule(),),
            (
                entitlements(
                    roles=(
                        ScopedBusinessRole(
                            role=BusinessRole.REVIEWER, scope=exact_scope
                        ),
                    )
                ),
            ),
            ACTION,
            target(),
        ),
        (
            (rule(),),
            (entitlements(),),
            ACTION,
            target(state=ResourceState("TEST_ONLY:APPROVED")),
        ),
        (
            (rule(),),
            (entitlements(),),
            ACTION,
            target(
                resource_scope=scope(
                    kind=ResourceScopeKind.CATEGORY,
                    resource_id=CATEGORY_A,
                )
            ),
        ),
    )
    for rules, snapshots, action, requested_target in cases:
        authorization_guard, sink = guard(rules=rules, snapshots=snapshots)
        assert_denied(
            lambda authorization_guard=authorization_guard, action=action, requested_target=requested_target: (
                _require(
                    authorization_guard,
                    action=action,
                    requested_target=requested_target,
                )
            )
        )
        assert sink.decisions[-1].effect is DecisionEffect.DENY


def test_same_resource_uuid_in_another_site_is_horizontal_denial() -> None:
    requested_scope = scope(site_id=SITE_B, resource_id=ARTICLE_A)
    authorization_guard, sink = guard(rules=(rule(),), snapshots=(entitlements(),))

    assert_denied(
        lambda: _require(
            authorization_guard,
            requested_target=target(resource_scope=requested_scope),
        )
    )

    assert sink.decisions[0].effect is DecisionEffect.DENY


def test_site_scope_never_implies_article_scope_or_vertical_authority() -> None:
    site_scope = scope(
        kind=ResourceScopeKind.SITE,
        site_id=SITE_A,
        resource_id=SITE_A,
    )
    site_entitlements = entitlements(resource_scope=site_scope)
    authorization_guard, sink = guard(rules=(rule(),), snapshots=(site_entitlements,))

    assert_denied(lambda: _require(authorization_guard))

    assert sink.decisions[0].effect is DecisionEffect.DENY


def test_none_state_is_exact_stateless_not_any_state() -> None:
    stateless_rule = rule(resource_state=None)
    authorization_guard, _ = guard(rules=(stateless_rule,), snapshots=(entitlements(),))
    assert_denied(lambda: _require(authorization_guard))

    stateless_guard, _ = guard(rules=(stateless_rule,), snapshots=(entitlements(),))
    grant = _require(stateless_guard, requested_target=target(state=None))
    assert grant.matched_rule_id == stateless_rule.rule_id


def test_multiple_distinct_matching_rules_are_ambiguous_and_deny() -> None:
    exact_scope = scope()
    rules = tuple(
        sorted(
            (
                rule(role=BusinessRole.EDITOR, rule_id="TEST_ONLY:RULE_EDITOR"),
                rule(role=BusinessRole.REVIEWER, rule_id="TEST_ONLY:RULE_REVIEWER"),
            ),
            key=lambda value: value.canonical_key,
        )
    )
    snapshot = entitlements(
        roles=tuple(
            sorted(
                (
                    ScopedBusinessRole(role=BusinessRole.EDITOR, scope=exact_scope),
                    ScopedBusinessRole(role=BusinessRole.REVIEWER, scope=exact_scope),
                ),
                key=lambda value: value.canonical_key,
            )
        )
    )
    authorization_guard, sink = guard(rules=rules, snapshots=(snapshot,))

    assert_denied(lambda: _require(authorization_guard))

    assert sink.decisions[0].effect is DecisionEffect.DENY
    assert sink.decisions[0].matched_rule_id is None


def test_duplicate_semantics_duplicate_ids_and_reordered_rules_reject() -> None:
    duplicate_semantics = tuple(
        sorted(
            (
                rule(rule_id="TEST_ONLY:RULE_A"),
                rule(rule_id="TEST_ONLY:RULE_B"),
            ),
            key=lambda value: value.canonical_key,
        )
    )
    assert_denied(
        lambda: DevelopmentAuthorizationPolicySource(
            environment=RuntimeEnvironment.ENV_DEV,
            mode=PolicyMode.RECORDED_TEST,
            revision=PolicyRevision("TEST_ONLY:POLICY"),
            rules=duplicate_semantics,
        )
    )

    duplicate_id = tuple(
        sorted(
            (
                rule(rule_id="TEST_ONLY:SAME", role=BusinessRole.EDITOR),
                rule(rule_id="TEST_ONLY:SAME", role=BusinessRole.REVIEWER),
            ),
            key=lambda value: value.canonical_key,
        )
    )
    assert_denied(
        lambda: DevelopmentAuthorizationPolicySource(
            environment=RuntimeEnvironment.ENV_DEV,
            mode=PolicyMode.RECORDED_TEST,
            revision=PolicyRevision("TEST_ONLY:POLICY"),
            rules=duplicate_id,
        )
    )

    ordered = tuple(
        sorted(
            (
                rule(rule_id="TEST_ONLY:A", role=BusinessRole.EDITOR),
                rule(rule_id="TEST_ONLY:B", role=BusinessRole.REVIEWER),
            ),
            key=lambda value: value.canonical_key,
        )
    )
    assert_denied(
        lambda: DevelopmentAuthorizationPolicySource(
            environment=RuntimeEnvironment.ENV_DEV,
            mode=PolicyMode.RECORDED_TEST,
            revision=PolicyRevision("TEST_ONLY:POLICY"),
            rules=tuple(reversed(ordered)),
        )
    )


@pytest.mark.parametrize(
    "value",
    (
        "*",
        "TEST_ONLY:*",
        "TEST_ONLY:?",
        "TEST_ONLY:[ARTICLE]",
        "TEST_ONLY:\nACTION",
        "ＴＥＳＴ＿ＯＮＬＹ：ＡＣＴＩＯＮ",
        " TEST_ONLY:ACTION",
        "TEST_ONLY:ACTION ",
    ),
)
def test_wildcard_control_confusable_and_edge_padded_tokens_reject(value: str) -> None:
    assert_denied(lambda: ActionCode(value))
    assert_denied(lambda: PermissionScope(value))


def test_raw_string_and_subclassed_values_never_authorize() -> None:
    authorization_guard, sink = guard(rules=(rule(),), snapshots=(entitlements(),))
    assert_denied(
        lambda: authorization_guard.require_admin_user(
            session_id=session().session_id,
            now=NOW,
            action=cast(ActionCode, "TEST_ONLY:EDIT_ARTICLE"),
            target=target(),
            correlation_id=CORRELATION,
        )
    )
    assert sink.decisions == ()

    action_subclass = type("ActionSubclass", (ActionCode,), {})
    subclassed = cast(ActionCode, action_subclass("TEST_ONLY:EDIT_ARTICLE"))
    assert_denied(
        lambda: authorization_guard.require_admin_user(
            session_id=session().session_id,
            now=NOW,
            action=subclassed,
            target=target(),
            correlation_id=CORRELATION,
        )
    )


def test_user_admin_and_service_internal_are_the_only_principal_pairs() -> None:
    principal = authorization_principal()
    assert principal.kind is PrincipalKind.USER
    assert principal.surface is AuthorizationSurface.ADMIN
    assert_denied(
        lambda: PrincipalIdentity(
            kind=PrincipalKind.SERVICE,
            surface=AuthorizationSurface.ADMIN,
            service_name=ServicePrincipalName("test-only-service"),
        )
    )
    assert_denied(
        lambda: PrincipalIdentity(
            kind=PrincipalKind.USER,
            surface=AuthorizationSurface.INTERNAL,
            issuer=principal.issuer,
            subject=principal.subject,
        )
    )


def test_public_entrypoint_does_not_accept_principal_role_or_scope_injection() -> None:
    parameters = inspect.signature(AuthorizationGuard.require_admin_user).parameters
    assert set(parameters) == {
        "self",
        "session_id",
        "now",
        "action",
        "target",
        "correlation_id",
    }
    assert "principal" not in parameters
    assert "role" not in parameters
    assert "permission_scope" not in parameters


class _CountingPolicySource:
    def __init__(self, result: object) -> None:
        self.calls = 0
        self.result = result

    def load(self) -> PolicySnapshot:
        self.calls += 1
        return cast(PolicySnapshot, self.result)


class _CountingEntitlementSource:
    def __init__(self, result: object) -> None:
        self.calls = 0
        self.result = result

    def resolve(self, principal: PrincipalIdentity) -> EntitlementSnapshot:
        del principal
        self.calls += 1
        return cast(EntitlementSnapshot, self.result)


class _CountingSink:
    def __init__(self, *, explode: bool = False, mutate: bool = False) -> None:
        self.calls = 0
        self.explode = explode
        self.mutate = mutate

    def record(self, decision: AuthorizationDecision) -> None:
        self.calls += 1
        if self.mutate:
            object.__setattr__(
                decision, "_action", ActionCode("TEST_ONLY:MUTATED_ACTION")
            )
        if self.explode:
            raise RuntimeError("SYNTHETIC_PRIVATE_SINK_CANARY")


def _custom_guard(
    *,
    policy_source: AuthorizationPolicySource,
    entitlement_source: EntitlementSource,
    sink: AuthorizationDecisionSink,
    active: Session,
) -> AuthorizationGuard:
    return AuthorizationGuard(
        session_service=authentication_service(active),
        policy_source=policy_source,
        entitlement_source=entitlement_source,
        decision_sink=sink,
    )


@pytest.mark.parametrize(
    "inactive_session",
    (
        session(revoked_at=NOW - timedelta(seconds=1)),
        session(idle_expires_at=NOW),
        session(idle_expires_at=NOW, absolute_expires_at=NOW),
    ),
)
def test_inactive_session_causes_zero_policy_entitlement_and_sink_calls(
    inactive_session: Session,
) -> None:
    policy_source = _CountingPolicySource(object())
    entitlement_source = _CountingEntitlementSource(object())
    sink = _CountingSink()
    authorization_guard = _custom_guard(
        policy_source=policy_source,
        entitlement_source=entitlement_source,
        sink=sink,
        active=inactive_session,
    )

    assert_denied(
        lambda: _require(
            authorization_guard,
            active_session_id=inactive_session.session_id,
        )
    )

    assert (policy_source.calls, entitlement_source.calls, sink.calls) == (0, 0, 0)


def test_policy_and_entitlement_exceptions_wrong_types_and_mutation_deny() -> None:
    class ExplodingPolicy:
        def load(self) -> PolicySnapshot:
            raise RuntimeError("SYNTHETIC_PRIVATE_POLICY_CANARY")

    entitlement_source = _CountingEntitlementSource(entitlements())
    sink = _CountingSink()
    exploding_guard = _custom_guard(
        policy_source=ExplodingPolicy(),
        entitlement_source=entitlement_source,
        sink=sink,
        active=session(),
    )
    failure = assert_denied(lambda: _require(exploding_guard))
    assert "CANARY" not in f"{failure!s}{failure!r}{failure.args!r}"
    assert entitlement_source.calls == 0
    assert sink.calls == 1

    wrong_policy_guard = _custom_guard(
        policy_source=_CountingPolicySource(object()),
        entitlement_source=_CountingEntitlementSource(entitlements()),
        sink=_CountingSink(),
        active=session(),
    )
    assert_denied(lambda: _require(wrong_policy_guard))

    mutated = PolicySnapshot(
        revision=PolicyRevision("TEST_ONLY:DISABLED"),
        mode=PolicyMode.DISABLED,
        rules=(),
    )
    object.__setattr__(mutated, "_rules", (rule(),))
    mutated_guard = _custom_guard(
        policy_source=_CountingPolicySource(mutated),
        entitlement_source=_CountingEntitlementSource(entitlements()),
        sink=_CountingSink(),
        active=session(),
    )
    assert_denied(lambda: _require(mutated_guard))

    recorded_policy = DevelopmentAuthorizationPolicySource(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=PolicyMode.RECORDED_TEST,
        revision=PolicyRevision("TEST_ONLY:POLICY"),
        rules=(rule(),),
    ).load()
    wrong_entitlement_guard = _custom_guard(
        policy_source=_CountingPolicySource(recorded_policy),
        entitlement_source=_CountingEntitlementSource(object()),
        sink=_CountingSink(),
        active=session(),
    )
    assert_denied(lambda: _require(wrong_entitlement_guard))


def test_sink_failure_denies_allow_and_deny_with_one_call_and_no_retry() -> None:
    recorded_policy = DevelopmentAuthorizationPolicySource(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=PolicyMode.RECORDED_TEST,
        revision=PolicyRevision("TEST_ONLY:POLICY"),
        rules=(rule(),),
    ).load()
    allow_sink = _CountingSink(explode=True)
    allow_guard = _custom_guard(
        policy_source=_CountingPolicySource(recorded_policy),
        entitlement_source=_CountingEntitlementSource(entitlements()),
        sink=allow_sink,
        active=session(),
    )
    assert_denied(lambda: _require(allow_guard))
    assert allow_sink.calls == 1

    deny_sink = _CountingSink(explode=True)
    disabled = PolicySnapshot(
        revision=PolicyRevision("TEST_ONLY:DISABLED"),
        mode=PolicyMode.DISABLED,
        rules=(),
    )
    deny_guard = _custom_guard(
        policy_source=_CountingPolicySource(disabled),
        entitlement_source=_CountingEntitlementSource(entitlements()),
        sink=deny_sink,
        active=session(),
    )
    assert_denied(lambda: _require(deny_guard))
    assert deny_sink.calls == 1


def test_sink_mutation_of_would_be_allow_denies_without_second_record() -> None:
    recorded_policy = DevelopmentAuthorizationPolicySource(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=PolicyMode.RECORDED_TEST,
        revision=PolicyRevision("TEST_ONLY:POLICY"),
        rules=(rule(),),
    ).load()
    sink = _CountingSink(mutate=True)
    authorization_guard = _custom_guard(
        policy_source=_CountingPolicySource(recorded_policy),
        entitlement_source=_CountingEntitlementSource(entitlements()),
        sink=sink,
        active=session(),
    )
    assert_denied(lambda: _require(authorization_guard))
    assert sink.calls == 1


def test_failure_decision_and_adapters_are_redacted_immutable_and_not_picklable() -> (
    None
):
    authorization_guard, sink = guard(rules=(rule(),), snapshots=(entitlements(),))
    _require(authorization_guard)
    decision = sink.decisions[0]
    forbidden_fields = {
        "issuer",
        "subject",
        "display_name",
        "credential",
        "token",
        "roles",
        "claims",
    }
    assert forbidden_fields.isdisjoint(dir(decision))
    assert "TEST_ONLY" not in repr(decision)
    with pytest.raises(TypeError, match="serialization is not supported"):
        pickle.dumps(decision)

    failure = AuthorizationFailure(AuthorizationFailureCode.DENIED)
    with pytest.raises(AttributeError, match="immutable"):
        failure.args = ("replacement",)
    with pytest.raises(TypeError, match="serialization is not supported"):
        pickle.dumps(failure)
    assert str(failure) == "DENIED"
    assert repr(failure) == "AuthorizationFailure(DENIED)"


@pytest.mark.parametrize(
    "environment",
    tuple(
        value for value in RuntimeEnvironment if value is not RuntimeEnvironment.ENV_DEV
    ),
)
def test_all_development_adapters_reject_non_dev_environment(
    environment: RuntimeEnvironment,
) -> None:
    assert_denied(lambda: DevelopmentAuthorizationPolicySource(environment=environment))
    assert_denied(
        lambda: DevelopmentEntitlementSource(environment=environment, snapshots=())
    )
    assert_denied(lambda: InMemoryAuthorizationDecisionSink(environment=environment))


def test_scope_requires_exact_non_nil_uuid_for_site_and_resource() -> None:
    assert_denied(
        lambda: ResourceScope(
            kind=ResourceScopeKind.GLOBAL,
            site_id=cast("UUID", str(SITE_A)),
            resource_id=ARTICLE_A,
        )
    )
    assert_denied(
        lambda: ResourceScope(
            kind=ResourceScopeKind.GLOBAL,
            site_id=SITE_A,
            resource_id=cast("UUID", "*"),
        )
    )
