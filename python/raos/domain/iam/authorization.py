"""Fail-closed authorization values for the ST-0403 local policy seam.

The module deliberately models only exact application authorization inputs.  It
does not encode a canonical business policy, resource hierarchy, database
grant, HTTP dependency, or service-authentication entrypoint.
"""

from __future__ import annotations

from enum import Enum
import hashlib
import re
from typing import ClassVar, NoReturn, SupportsIndex, final
from uuid import UUID

from raos.domain.iam.authentication import Issuer, Subject


_TOKEN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._:/-]{0,126}[A-Za-z0-9])?\Z", re.ASCII)
_SERVICE_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
_FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REDACTED = "<redacted-authorization-value>"


class PrincipalKind(str, Enum):
    """Closed principal taxonomy; it is never inferred from caller input."""

    USER = "USER"
    SERVICE = "SERVICE"


class AuthorizationSurface(str, Enum):
    """Closed server-side authorization surfaces."""

    ADMIN = "ADMIN"
    INTERNAL = "INTERNAL"


class ResourceScopeKind(str, Enum):
    """Exact resource kinds with no implied hierarchy."""

    GLOBAL = "GLOBAL"
    SITE = "SITE"
    CATEGORY = "CATEGORY"
    ARTICLE = "ARTICLE"


class PolicyMode(str, Enum):
    """Only disabled and local recorded policy modes exist in this slice."""

    DISABLED = "DISABLED"
    RECORDED_TEST = "RECORDED_TEST"


class DecisionEffect(str, Enum):
    """Closed internal decision effects."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class BusinessRole(str, Enum):
    """Canonical business-role names, without assigning them to anyone."""

    PRODUCT_OWNER = "PRODUCT_OWNER"
    MANAGING_EDITOR = "MANAGING_EDITOR"
    EDITOR = "EDITOR"
    REVIEWER = "REVIEWER"
    ANALYST = "ANALYST"
    OPERATOR = "OPERATOR"
    SECURITY_AUDITOR = "SECURITY_AUDITOR"
    READ_ONLY_AUDITOR = "READ_ONLY_AUDITOR"


class AuthorizationDecisionReason(str, Enum):
    """Closed, non-sensitive reasons retained only in the inward decision."""

    RULE_MATCH = "RULE_MATCH"
    POLICY_DISABLED = "POLICY_DISABLED"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    INVALID_INPUT = "INVALID_INPUT"
    POLICY_FAILURE = "POLICY_FAILURE"
    ENTITLEMENT_FAILURE = "ENTITLEMENT_FAILURE"


class AuthorizationFailureCode(str, Enum):
    """The sole classification visible to an external application caller."""

    DENIED = "DENIED"


@final
class AuthorizationFailure(RuntimeError):
    """Immutable sanitized failure that retains no rejected authorization data."""

    __slots__ = ("_code", "_sealed")
    _code: AuthorizationFailureCode
    _sealed: bool

    def __init__(self, code: AuthorizationFailureCode) -> None:
        if (
            type(code) is not AuthorizationFailureCode
            or code is not AuthorizationFailureCode.DENIED
        ):
            raise TypeError("code must be the exact DENIED AuthorizationFailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)
        object.__setattr__(self, "_sealed", True)

    @property
    def code(self) -> AuthorizationFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuthorizationFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AuthorizationFailure is immutable")

    def __repr__(self) -> str:
        return "AuthorizationFailure(DENIED)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("authorization failure serialization is not supported")


def deny_authorization() -> NoReturn:
    """Raise the sole external authorization failure without an exception chain."""

    raise AuthorizationFailure(AuthorizationFailureCode.DENIED) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("authorization value serialization is not supported")


class _BoundedToken(_RedactedValue):
    __slots__ = ("_value", "_sealed")
    _value: str
    _sealed: bool
    _maximum_length: ClassVar[int] = 128

    def __init__(self, value: str) -> None:
        if (
            type(value) is not str
            or not 1 <= len(value) <= self._maximum_length
            or _TOKEN.fullmatch(value) is None
        ):
            deny_authorization()
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "_sealed", True)

    @property
    def value(self) -> str:
        """Return the normalized non-secret token at an inward boundary."""

        return self._value

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and self._value == other._value

    def __hash__(self) -> int:
        return hash((type(self), self._value))


@final
class PolicyRevision(_BoundedToken):
    """One immutable policy revision identifier."""

    __slots__ = ()


@final
class EntitlementRevision(_BoundedToken):
    """One immutable entitlement snapshot revision identifier."""

    __slots__ = ()


@final
class RuleId(_BoundedToken):
    """One immutable authorization rule identifier."""

    __slots__ = ()


@final
class PermissionScope(_BoundedToken):
    """One exact OAuth permission scope; wildcards and Unicode are rejected."""

    __slots__ = ()


@final
class ActionCode(_BoundedToken):
    """One exact server-side action code."""

    __slots__ = ()


@final
class ResourceState(_BoundedToken):
    """One exact resource state.  Absence means stateless, never any state."""

    __slots__ = ()


@final
class CorrelationId(_BoundedToken):
    """One bounded caller-correlation value safe for an inward decision."""

    __slots__ = ()


@final
class ServicePrincipalName(_RedactedValue):
    """A bounded logical service name, not a workload credential or role."""

    __slots__ = ("_value", "_sealed")
    _value: str
    _sealed: bool

    def __init__(self, value: str) -> None:
        if (
            type(value) is not str
            or not 1 <= len(value) <= 63
            or _SERVICE_NAME.fullmatch(value) is None
        ):
            deny_authorization()
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "_sealed", True)

    @property
    def value(self) -> str:
        return self._value

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("ServicePrincipalName is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("ServicePrincipalName is immutable")

    def __eq__(self, other: object) -> bool:
        return type(other) is ServicePrincipalName and self._value == other._value

    def __hash__(self) -> int:
        return hash((ServicePrincipalName, self._value))


@final
class PrincipalIdentity(_RedactedValue):
    """Trusted principal identity paired to exactly one allowed surface.

    User identities preserve the strict ST-0401 issuer and subject values.
    Service identities are modeled for the closed domain taxonomy, but ST-0403
    intentionally exposes no application service entrypoint.
    """

    __slots__ = (
        "_issuer",
        "_kind",
        "_sealed",
        "_service_name",
        "_subject",
        "_surface",
    )
    _kind: PrincipalKind
    _surface: AuthorizationSurface
    _issuer: Issuer | None
    _subject: Subject | None
    _service_name: ServicePrincipalName | None
    _sealed: bool

    def __init__(
        self,
        *,
        kind: PrincipalKind,
        surface: AuthorizationSurface,
        issuer: Issuer | None = None,
        subject: Subject | None = None,
        service_name: ServicePrincipalName | None = None,
    ) -> None:
        user_pair = (
            kind is PrincipalKind.USER
            and surface is AuthorizationSurface.ADMIN
            and type(issuer) is Issuer
            and type(subject) is Subject
            and service_name is None
        )
        service_pair = (
            kind is PrincipalKind.SERVICE
            and surface is AuthorizationSurface.INTERNAL
            and issuer is None
            and subject is None
            and type(service_name) is ServicePrincipalName
        )
        if (
            type(kind) is not PrincipalKind
            or type(surface) is not AuthorizationSurface
            or not (user_pair or service_pair)
        ):
            deny_authorization()
        object.__setattr__(self, "_kind", kind)
        object.__setattr__(self, "_surface", surface)
        object.__setattr__(self, "_issuer", issuer)
        object.__setattr__(self, "_subject", subject)
        object.__setattr__(self, "_service_name", service_name)
        object.__setattr__(self, "_sealed", True)

    @classmethod
    def admin_user(cls, *, issuer: Issuer, subject: Subject) -> PrincipalIdentity:
        return cls(
            kind=PrincipalKind.USER,
            surface=AuthorizationSurface.ADMIN,
            issuer=issuer,
            subject=subject,
        )

    @property
    def kind(self) -> PrincipalKind:
        return self._kind

    @property
    def surface(self) -> AuthorizationSurface:
        return self._surface

    @property
    def issuer(self) -> Issuer | None:
        return self._issuer

    @property
    def subject(self) -> Subject | None:
        return self._subject

    @property
    def service_name(self) -> ServicePrincipalName | None:
        return self._service_name

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("PrincipalIdentity is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("PrincipalIdentity is immutable")

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is PrincipalIdentity
            and self.kind is other.kind
            and self.surface is other.surface
            and self.issuer == other.issuer
            and self.subject == other.subject
            and self.service_name == other.service_name
        )

    def __hash__(self) -> int:
        return hash(
            (self.kind, self.surface, self.issuer, self.subject, self.service_name)
        )


@final
class ResourceScope(_RedactedValue):
    """One exact site/resource scope with no ancestor or tenant inference."""

    __slots__ = ("_kind", "_resource_id", "_sealed", "_site_id")
    _kind: ResourceScopeKind
    _site_id: UUID
    _resource_id: UUID
    _sealed: bool

    def __init__(
        self,
        *,
        kind: ResourceScopeKind,
        site_id: UUID,
        resource_id: UUID,
    ) -> None:
        if (
            type(kind) is not ResourceScopeKind
            or type(site_id) is not UUID
            or type(resource_id) is not UUID
            or site_id.int == 0
            or resource_id.int == 0
        ):
            deny_authorization()
        object.__setattr__(self, "_kind", kind)
        object.__setattr__(self, "_site_id", site_id)
        object.__setattr__(self, "_resource_id", resource_id)
        object.__setattr__(self, "_sealed", True)

    @property
    def kind(self) -> ResourceScopeKind:
        return self._kind

    @property
    def site_id(self) -> UUID:
        return self._site_id

    @property
    def resource_id(self) -> UUID:
        return self._resource_id

    @property
    def canonical_key(self) -> tuple[str, str, str]:
        return (self.kind.value, self.site_id.hex, self.resource_id.hex)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("ResourceScope is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("ResourceScope is immutable")

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is ResourceScope
            and self.kind is other.kind
            and self.site_id == other.site_id
            and self.resource_id == other.resource_id
        )

    def __hash__(self) -> int:
        return hash((self.kind, self.site_id, self.resource_id))


@final
class AuthorizationTarget(_RedactedValue):
    """One normalized authorization target and optional exact state."""

    __slots__ = ("_scope", "_sealed", "_state")
    _scope: ResourceScope
    _state: ResourceState | None
    _sealed: bool

    def __init__(
        self, *, scope: ResourceScope, state: ResourceState | None = None
    ) -> None:
        if type(scope) is not ResourceScope or (
            state is not None and type(state) is not ResourceState
        ):
            deny_authorization()
        object.__setattr__(self, "_scope", scope)
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_sealed", True)

    @property
    def scope(self) -> ResourceScope:
        return self._scope

    @property
    def state(self) -> ResourceState | None:
        return self._state

    @property
    def canonical_key(self) -> tuple[str, str, str, str]:
        return (
            *self.scope.canonical_key,
            "" if self.state is None else self.state.value,
        )

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuthorizationTarget is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AuthorizationTarget is immutable")

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is AuthorizationTarget
            and self.scope == other.scope
            and self.state == other.state
        )

    def __hash__(self) -> int:
        return hash((self.scope, self.state))


@final
class ScopedBusinessRole(_RedactedValue):
    """One business role bound to one exact site/resource scope."""

    __slots__ = ("_role", "_scope", "_sealed")
    _role: BusinessRole
    _scope: ResourceScope
    _sealed: bool

    def __init__(self, *, role: BusinessRole, scope: ResourceScope) -> None:
        if type(role) is not BusinessRole or type(scope) is not ResourceScope:
            deny_authorization()
        object.__setattr__(self, "_role", role)
        object.__setattr__(self, "_scope", scope)
        object.__setattr__(self, "_sealed", True)

    @property
    def role(self) -> BusinessRole:
        return self._role

    @property
    def scope(self) -> ResourceScope:
        return self._scope

    @property
    def canonical_key(self) -> tuple[str, str, str, str]:
        return (*self.scope.canonical_key, self.role.value)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("ScopedBusinessRole is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("ScopedBusinessRole is immutable")

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is ScopedBusinessRole
            and self.role is other.role
            and self.scope == other.scope
        )

    def __hash__(self) -> int:
        return hash((self.role, self.scope))


@final
class ScopedPermission(_RedactedValue):
    """One OAuth permission scope bound to one exact site/resource scope."""

    __slots__ = ("_permission_scope", "_scope", "_sealed")
    _permission_scope: PermissionScope
    _scope: ResourceScope
    _sealed: bool

    def __init__(
        self, *, permission_scope: PermissionScope, scope: ResourceScope
    ) -> None:
        if (
            type(permission_scope) is not PermissionScope
            or type(scope) is not ResourceScope
        ):
            deny_authorization()
        object.__setattr__(self, "_permission_scope", permission_scope)
        object.__setattr__(self, "_scope", scope)
        object.__setattr__(self, "_sealed", True)

    @property
    def permission_scope(self) -> PermissionScope:
        return self._permission_scope

    @property
    def scope(self) -> ResourceScope:
        return self._scope

    @property
    def canonical_key(self) -> tuple[str, str, str, str]:
        return (*self.scope.canonical_key, self.permission_scope.value)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("ScopedPermission is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("ScopedPermission is immutable")

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is ScopedPermission
            and self.permission_scope == other.permission_scope
            and self.scope == other.scope
        )

    def __hash__(self) -> int:
        return hash((self.permission_scope, self.scope))


@final
class AuthorizationRule(_RedactedValue):
    """One exact allowlist rule.  There is intentionally no deny-rule type."""

    __slots__ = (
        "_action",
        "_permission_scope",
        "_resource_kind",
        "_resource_state",
        "_role",
        "_rule_id",
        "_sealed",
    )
    _rule_id: RuleId
    _role: BusinessRole
    _permission_scope: PermissionScope
    _action: ActionCode
    _resource_kind: ResourceScopeKind
    _resource_state: ResourceState | None
    _sealed: bool

    def __init__(
        self,
        *,
        rule_id: RuleId,
        role: BusinessRole,
        permission_scope: PermissionScope,
        action: ActionCode,
        resource_kind: ResourceScopeKind,
        resource_state: ResourceState | None = None,
    ) -> None:
        if (
            type(rule_id) is not RuleId
            or type(role) is not BusinessRole
            or type(permission_scope) is not PermissionScope
            or type(action) is not ActionCode
            or type(resource_kind) is not ResourceScopeKind
            or (
                resource_state is not None and type(resource_state) is not ResourceState
            )
        ):
            deny_authorization()
        object.__setattr__(self, "_rule_id", rule_id)
        object.__setattr__(self, "_role", role)
        object.__setattr__(self, "_permission_scope", permission_scope)
        object.__setattr__(self, "_action", action)
        object.__setattr__(self, "_resource_kind", resource_kind)
        object.__setattr__(self, "_resource_state", resource_state)
        object.__setattr__(self, "_sealed", True)

    @property
    def rule_id(self) -> RuleId:
        return self._rule_id

    @property
    def role(self) -> BusinessRole:
        return self._role

    @property
    def permission_scope(self) -> PermissionScope:
        return self._permission_scope

    @property
    def action(self) -> ActionCode:
        return self._action

    @property
    def resource_kind(self) -> ResourceScopeKind:
        return self._resource_kind

    @property
    def resource_state(self) -> ResourceState | None:
        return self._resource_state

    @property
    def semantic_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.role.value,
            self.permission_scope.value,
            self.action.value,
            self.resource_kind.value,
            "" if self.resource_state is None else self.resource_state.value,
        )

    @property
    def canonical_key(self) -> tuple[str, str, str, str, str, str]:
        return (*self.semantic_key, self.rule_id.value)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuthorizationRule is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AuthorizationRule is immutable")

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is AuthorizationRule
            and self.canonical_key == other.canonical_key
        )

    def __hash__(self) -> int:
        return hash(self.canonical_key)


class _RecordedTestPolicyPermit:
    __slots__ = ()


_RECORDED_TEST_POLICY_PERMIT = _RecordedTestPolicyPermit()


@final
class PolicySnapshot(_RedactedValue):
    """One canonical, immutable allowlist policy snapshot."""

    __slots__ = ("_fingerprint", "_mode", "_revision", "_rules", "_sealed")
    _revision: PolicyRevision
    _mode: PolicyMode
    _rules: tuple[AuthorizationRule, ...]
    _fingerprint: str
    _sealed: bool

    def __init__(
        self,
        *,
        revision: PolicyRevision,
        mode: PolicyMode,
        rules: tuple[AuthorizationRule, ...],
        _recorded_test_permit: object | None = None,
    ) -> None:
        self._validate_components(
            revision=revision,
            mode=mode,
            rules=rules,
            recorded_test_permit=_recorded_test_permit,
        )
        fingerprint = self._calculate_fingerprint(revision, mode, rules)
        object.__setattr__(self, "_revision", revision)
        object.__setattr__(self, "_mode", mode)
        object.__setattr__(self, "_rules", rules)
        object.__setattr__(self, "_fingerprint", fingerprint)
        object.__setattr__(self, "_sealed", True)

    @staticmethod
    def _validate_components(
        *,
        revision: PolicyRevision,
        mode: PolicyMode,
        rules: tuple[AuthorizationRule, ...],
        recorded_test_permit: object | None,
    ) -> None:
        if (
            type(revision) is not PolicyRevision
            or type(mode) is not PolicyMode
            or type(rules) is not tuple
            or any(type(rule) is not AuthorizationRule for rule in rules)
            or (mode is PolicyMode.DISABLED and rules)
            or (
                mode is PolicyMode.RECORDED_TEST
                and recorded_test_permit is not _RECORDED_TEST_POLICY_PERMIT
            )
        ):
            deny_authorization()
        canonical_keys = tuple(rule.canonical_key for rule in rules)
        semantic_keys = tuple(rule.semantic_key for rule in rules)
        rule_ids = tuple(rule.rule_id.value for rule in rules)
        if (
            canonical_keys != tuple(sorted(canonical_keys))
            or len(set(semantic_keys)) != len(semantic_keys)
            or len(set(rule_ids)) != len(rule_ids)
        ):
            deny_authorization()

    @staticmethod
    def _calculate_fingerprint(
        revision: PolicyRevision,
        mode: PolicyMode,
        rules: tuple[AuthorizationRule, ...],
    ) -> str:
        lines = [f"revision={revision.value}", f"mode={mode.value}"]
        lines.extend("|".join(rule.canonical_key) for rule in rules)
        return hashlib.sha256("\n".join(lines).encode("ascii")).hexdigest()

    @property
    def revision(self) -> PolicyRevision:
        return self._revision

    @property
    def mode(self) -> PolicyMode:
        return self._mode

    @property
    def rules(self) -> tuple[AuthorizationRule, ...]:
        return self._rules

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def require_valid(self) -> None:
        """Recheck exact runtime shape so mutated collaborator values fail closed."""

        self._validate_components(
            revision=self._revision,
            mode=self._mode,
            rules=self._rules,
            recorded_test_permit=(
                _RECORDED_TEST_POLICY_PERMIT
                if self._mode is PolicyMode.RECORDED_TEST
                else None
            ),
        )
        if self._fingerprint != self._calculate_fingerprint(
            self._revision, self._mode, self._rules
        ):
            deny_authorization()

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("PolicySnapshot is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("PolicySnapshot is immutable")


def disabled_policy_snapshot() -> PolicySnapshot:
    """Return the stable empty deny-default policy used outside recorded tests."""

    return PolicySnapshot(
        revision=PolicyRevision("TEST_ONLY:DISABLED"),
        mode=PolicyMode.DISABLED,
        rules=(),
    )


def _recorded_test_policy_snapshot(
    *, revision: PolicyRevision, rules: tuple[AuthorizationRule, ...]
) -> PolicySnapshot:
    """Construct a recorded policy for the exact ENV-DEV adapter only."""

    return PolicySnapshot(
        revision=revision,
        mode=PolicyMode.RECORDED_TEST,
        rules=rules,
        _recorded_test_permit=_RECORDED_TEST_POLICY_PERMIT,
    )


@final
class EntitlementSnapshot(_RedactedValue):
    """Versioned trusted server-side roles and OAuth scopes for one principal."""

    __slots__ = (
        "_permission_scopes",
        "_principal",
        "_revision",
        "_roles",
        "_sealed",
    )
    _revision: EntitlementRevision
    _principal: PrincipalIdentity
    _roles: tuple[ScopedBusinessRole, ...]
    _permission_scopes: tuple[ScopedPermission, ...]
    _sealed: bool

    def __init__(
        self,
        *,
        revision: EntitlementRevision,
        principal: PrincipalIdentity,
        roles: tuple[ScopedBusinessRole, ...],
        permission_scopes: tuple[ScopedPermission, ...],
    ) -> None:
        self._validate_components(
            revision=revision,
            principal=principal,
            roles=roles,
            permission_scopes=permission_scopes,
        )
        object.__setattr__(self, "_revision", revision)
        object.__setattr__(self, "_principal", principal)
        object.__setattr__(self, "_roles", roles)
        object.__setattr__(self, "_permission_scopes", permission_scopes)
        object.__setattr__(self, "_sealed", True)

    @staticmethod
    def _validate_components(
        *,
        revision: EntitlementRevision,
        principal: PrincipalIdentity,
        roles: tuple[ScopedBusinessRole, ...],
        permission_scopes: tuple[ScopedPermission, ...],
    ) -> None:
        if (
            type(revision) is not EntitlementRevision
            or type(principal) is not PrincipalIdentity
            or type(roles) is not tuple
            or type(permission_scopes) is not tuple
            or any(type(role) is not ScopedBusinessRole for role in roles)
            or any(
                type(permission) is not ScopedPermission
                for permission in permission_scopes
            )
        ):
            deny_authorization()
        role_keys = tuple(role.canonical_key for role in roles)
        permission_keys = tuple(
            permission.canonical_key for permission in permission_scopes
        )
        if (
            role_keys != tuple(sorted(role_keys))
            or permission_keys != tuple(sorted(permission_keys))
            or len(set(role_keys)) != len(role_keys)
            or len(set(permission_keys)) != len(permission_keys)
        ):
            deny_authorization()

    @property
    def revision(self) -> EntitlementRevision:
        return self._revision

    @property
    def principal(self) -> PrincipalIdentity:
        return self._principal

    @property
    def roles(self) -> tuple[ScopedBusinessRole, ...]:
        return self._roles

    @property
    def permission_scopes(self) -> tuple[ScopedPermission, ...]:
        return self._permission_scopes

    def require_valid(self) -> None:
        self._validate_components(
            revision=self._revision,
            principal=self._principal,
            roles=self._roles,
            permission_scopes=self._permission_scopes,
        )

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("EntitlementSnapshot is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("EntitlementSnapshot is immutable")


@final
class AuthorizationDecision(_RedactedValue):
    """Minimal immutable decision sent only to the inward recording sink."""

    __slots__ = (
        "_action",
        "_correlation_id",
        "_effect",
        "_entitlement_revision",
        "_matched_rule_id",
        "_policy_fingerprint",
        "_policy_revision",
        "_reason",
        "_sealed",
        "_target",
    )
    _correlation_id: CorrelationId
    _effect: DecisionEffect
    _reason: AuthorizationDecisionReason
    _policy_revision: PolicyRevision
    _policy_fingerprint: str
    _entitlement_revision: EntitlementRevision
    _matched_rule_id: RuleId | None
    _action: ActionCode
    _target: AuthorizationTarget
    _sealed: bool

    def __init__(
        self,
        *,
        correlation_id: CorrelationId,
        effect: DecisionEffect,
        reason: AuthorizationDecisionReason,
        policy_revision: PolicyRevision,
        policy_fingerprint: str,
        entitlement_revision: EntitlementRevision,
        matched_rule_id: RuleId | None,
        action: ActionCode,
        target: AuthorizationTarget,
    ) -> None:
        allow_shape = (
            effect is DecisionEffect.ALLOW
            and reason is AuthorizationDecisionReason.RULE_MATCH
            and type(matched_rule_id) is RuleId
        )
        deny_shape = effect is DecisionEffect.DENY and matched_rule_id is None
        if (
            type(correlation_id) is not CorrelationId
            or type(effect) is not DecisionEffect
            or type(reason) is not AuthorizationDecisionReason
            or type(policy_revision) is not PolicyRevision
            or type(policy_fingerprint) is not str
            or _FINGERPRINT.fullmatch(policy_fingerprint) is None
            or type(entitlement_revision) is not EntitlementRevision
            or type(action) is not ActionCode
            or type(target) is not AuthorizationTarget
            or not (allow_shape or deny_shape)
        ):
            deny_authorization()
        object.__setattr__(self, "_correlation_id", correlation_id)
        object.__setattr__(self, "_effect", effect)
        object.__setattr__(self, "_reason", reason)
        object.__setattr__(self, "_policy_revision", policy_revision)
        object.__setattr__(self, "_policy_fingerprint", policy_fingerprint)
        object.__setattr__(self, "_entitlement_revision", entitlement_revision)
        object.__setattr__(self, "_matched_rule_id", matched_rule_id)
        object.__setattr__(self, "_action", action)
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_sealed", True)

    @property
    def correlation_id(self) -> CorrelationId:
        return self._correlation_id

    @property
    def effect(self) -> DecisionEffect:
        return self._effect

    @property
    def reason(self) -> AuthorizationDecisionReason:
        return self._reason

    @property
    def policy_revision(self) -> PolicyRevision:
        return self._policy_revision

    @property
    def policy_fingerprint(self) -> str:
        return self._policy_fingerprint

    @property
    def entitlement_revision(self) -> EntitlementRevision:
        return self._entitlement_revision

    @property
    def matched_rule_id(self) -> RuleId | None:
        return self._matched_rule_id

    @property
    def action(self) -> ActionCode:
        return self._action

    @property
    def target(self) -> AuthorizationTarget:
        return self._target

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuthorizationDecision is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AuthorizationDecision is immutable")


@final
class AuthorizationGrant(_RedactedValue):
    """An allow grant constructible only from one recorded allow decision."""

    __slots__ = ("_decision", "_sealed")
    _decision: AuthorizationDecision
    _sealed: bool

    def __init__(self, *, recorded_decision: AuthorizationDecision) -> None:
        if (
            type(recorded_decision) is not AuthorizationDecision
            or recorded_decision.effect is not DecisionEffect.ALLOW
            or type(recorded_decision.matched_rule_id) is not RuleId
        ):
            deny_authorization()
        object.__setattr__(self, "_decision", recorded_decision)
        object.__setattr__(self, "_sealed", True)

    @property
    def correlation_id(self) -> CorrelationId:
        return self._decision.correlation_id

    @property
    def matched_rule_id(self) -> RuleId:
        rule_id = self._decision.matched_rule_id
        if type(rule_id) is not RuleId:
            deny_authorization()
        return rule_id

    @property
    def action(self) -> ActionCode:
        return self._decision.action

    @property
    def target(self) -> AuthorizationTarget:
        return self._decision.target

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuthorizationGrant is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AuthorizationGrant is immutable")


__all__ = [
    "ActionCode",
    "AuthorizationDecision",
    "AuthorizationDecisionReason",
    "AuthorizationFailure",
    "AuthorizationFailureCode",
    "AuthorizationGrant",
    "AuthorizationRule",
    "AuthorizationSurface",
    "AuthorizationTarget",
    "BusinessRole",
    "CorrelationId",
    "DecisionEffect",
    "EntitlementRevision",
    "EntitlementSnapshot",
    "PermissionScope",
    "PolicyMode",
    "PolicyRevision",
    "PolicySnapshot",
    "PrincipalIdentity",
    "PrincipalKind",
    "ResourceScope",
    "ResourceScopeKind",
    "ResourceState",
    "RuleId",
    "ScopedBusinessRole",
    "ScopedPermission",
    "ServicePrincipalName",
    "deny_authorization",
    "disabled_policy_snapshot",
]
