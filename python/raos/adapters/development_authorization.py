"""Deterministic, in-memory authorization adapters for exact ENV-DEV only."""

from __future__ import annotations

from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authorization import (
    AuthorizationDecision,
    AuthorizationRule,
    EntitlementSnapshot,
    PolicyMode,
    PolicyRevision,
    PolicySnapshot,
    PrincipalIdentity,
    _recorded_test_policy_snapshot,  # pyright: ignore[reportPrivateUsage]
    deny_authorization,
)


_TEST_ONLY_PREFIX = "TEST_ONLY:"


def _deny() -> NoReturn:
    deny_authorization()


def _require_development(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment is not RuntimeEnvironment.ENV_DEV
    ):
        _deny()
    return environment


def _is_test_only(value: str) -> bool:
    return value.startswith(_TEST_ONLY_PREFIX) and len(value) > len(_TEST_ONLY_PREFIX)


def _require_recorded_rules(rules: tuple[AuthorizationRule, ...]) -> None:
    if type(rules) is not tuple or any(
        type(rule) is not AuthorizationRule
        or not _is_test_only(rule.rule_id.value)
        or not _is_test_only(rule.permission_scope.value)
        or not _is_test_only(rule.action.value)
        or (
            rule.resource_state is not None
            and not _is_test_only(rule.resource_state.value)
        )
        for rule in rules
    ):
        _deny()


def _copy_policy(snapshot: PolicySnapshot) -> PolicySnapshot:
    snapshot.require_valid()
    if snapshot.mode is PolicyMode.DISABLED:
        return PolicySnapshot(
            revision=snapshot.revision,
            mode=PolicyMode.DISABLED,
            rules=(),
        )
    if snapshot.mode is PolicyMode.RECORDED_TEST:
        return _recorded_test_policy_snapshot(
            revision=snapshot.revision,
            rules=snapshot.rules,
        )
    _deny()


def _copy_entitlements(snapshot: EntitlementSnapshot) -> EntitlementSnapshot:
    snapshot.require_valid()
    return EntitlementSnapshot(
        revision=snapshot.revision,
        principal=snapshot.principal,
        roles=snapshot.roles,
        permission_scopes=snapshot.permission_scopes,
    )


def _copy_decision(decision: AuthorizationDecision) -> AuthorizationDecision:
    return AuthorizationDecision(
        correlation_id=decision.correlation_id,
        effect=decision.effect,
        reason=decision.reason,
        policy_revision=decision.policy_revision,
        policy_fingerprint=decision.policy_fingerprint,
        entitlement_revision=decision.entitlement_revision,
        matched_rule_id=decision.matched_rule_id,
        action=decision.action,
        target=decision.target,
    )


@final
class DevelopmentAuthorizationPolicySource:
    """Expose only disabled or explicit TEST_ONLY recorded policy snapshots."""

    __slots__ = ("_environment", "_snapshot")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        mode: PolicyMode = PolicyMode.DISABLED,
        revision: PolicyRevision = PolicyRevision("TEST_ONLY:DISABLED"),
        rules: tuple[AuthorizationRule, ...] = (),
    ) -> None:
        self._environment = _require_development(environment)
        if (
            type(mode) is not PolicyMode
            or type(revision) is not PolicyRevision
            or not _is_test_only(revision.value)
        ):
            _deny()
        if mode is PolicyMode.DISABLED:
            self._snapshot = PolicySnapshot(
                revision=revision,
                mode=PolicyMode.DISABLED,
                rules=rules,
            )
        elif mode is PolicyMode.RECORDED_TEST:
            _require_recorded_rules(rules)
            self._snapshot = _recorded_test_policy_snapshot(
                revision=revision,
                rules=rules,
            )
        else:
            _deny()

    def load(self) -> PolicySnapshot:
        self._guard()
        return _copy_policy(self._snapshot)

    def _guard(self) -> None:
        _require_development(self._environment)

    def __repr__(self) -> str:
        return "DevelopmentAuthorizationPolicySource(environment='ENV-DEV', policy=<redacted>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError(
            "development authorization source serialization is not supported"
        )


@final
class DevelopmentEntitlementSource:
    """Resolve pre-scripted synthetic entitlement snapshots in memory."""

    __slots__ = ("_environment", "_snapshots")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        snapshots: tuple[EntitlementSnapshot, ...],
    ) -> None:
        self._environment = _require_development(environment)
        if type(snapshots) is not tuple or any(
            type(snapshot) is not EntitlementSnapshot
            or not _is_test_only(snapshot.revision.value)
            or any(
                not _is_test_only(permission.permission_scope.value)
                for permission in snapshot.permission_scopes
            )
            for snapshot in snapshots
        ):
            _deny()
        for snapshot in snapshots:
            snapshot.require_valid()
        principals = tuple(snapshot.principal for snapshot in snapshots)
        if len(set(principals)) != len(principals):
            _deny()
        self._snapshots = snapshots

    def resolve(self, principal: PrincipalIdentity) -> EntitlementSnapshot:
        self._guard()
        if type(principal) is not PrincipalIdentity:
            _deny()
        for snapshot in self._snapshots:
            if snapshot.principal == principal:
                return _copy_entitlements(snapshot)
        _deny()

    def _guard(self) -> None:
        _require_development(self._environment)

    def __repr__(self) -> str:
        return "DevelopmentEntitlementSource(environment='ENV-DEV', entitlements=<redacted>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("development entitlement source serialization is not supported")


@final
class InMemoryAuthorizationDecisionSink:
    """Ephemeral decision recorder; it is explicitly not a durable audit log."""

    __slots__ = ("_decisions", "_environment")

    def __init__(self, *, environment: RuntimeEnvironment) -> None:
        self._environment = _require_development(environment)
        self._decisions: list[AuthorizationDecision] = []

    def record(self, decision: AuthorizationDecision) -> None:
        self._guard()
        if type(decision) is not AuthorizationDecision:
            _deny()
        self._decisions.append(_copy_decision(decision))

    @property
    def decisions(self) -> tuple[AuthorizationDecision, ...]:
        self._guard()
        return tuple(_copy_decision(decision) for decision in self._decisions)

    def _guard(self) -> None:
        _require_development(self._environment)

    def __repr__(self) -> str:
        return "InMemoryAuthorizationDecisionSink(environment='ENV-DEV', decisions=<redacted>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("development decision sink serialization is not supported")


__all__ = [
    "DevelopmentAuthorizationPolicySource",
    "DevelopmentEntitlementSource",
    "InMemoryAuthorizationDecisionSink",
]
