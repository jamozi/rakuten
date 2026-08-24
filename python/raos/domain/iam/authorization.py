"""Fail-closed authorization values for the ST-0403 local policy seam.

The module deliberately models only exact application authorization inputs.  It
does not encode a canonical business policy, resource hierarchy, database
grant, HTTP dependency, or service-authentication entrypoint.  These Python
values live inside the trusted process TCB: their constructors support internal
normalization and are not unforgeable capabilities or external-input parsers.
Only the application guard/service is an authorization enforcement entrypoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import re
from types import MappingProxyType
from typing import ClassVar, Mapping, NoReturn, SupportsIndex, final
from uuid import UUID

from raos.domain.iam.authentication import Issuer, Subject
from raos.domain.iam.step_up import (
    BoundStepUpGrantId,
    CriticalStepUpAction,
    StepUpCommandId,
    StepUpResourceType,
)


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
    ARTICLE_VERSION = "ARTICLE_VERSION"
    REVIEW_ASSIGNMENT = "REVIEW_ASSIGNMENT"
    PUBLICATION_CANDIDATE = "PUBLICATION_CANDIDATE"
    PUBLICATION = "PUBLICATION"
    PUBLICATION_SCOPE = "PUBLICATION_SCOPE"
    AFFILIATE_SCOPE = "AFFILIATE_SCOPE"
    REVENUE_IMPORT = "REVENUE_IMPORT"
    AI_RELEASE = "AI_RELEASE"
    PRODUCT = "PRODUCT"
    POLICY_BUNDLE = "POLICY_BUNDLE"
    AUDIT = "AUDIT"
    SECRET = "SECRET"
    BREAK_GLASS_ACCESS = "BREAK_GLASS_ACCESS"


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
    OPERATION_UNMAPPED = "OPERATION_UNMAPPED"
    OPERATION_BLOCKED = "OPERATION_BLOCKED"
    STALE_POLICY = "STALE_POLICY"
    STALE_ENTITLEMENTS = "STALE_ENTITLEMENTS"
    STEP_UP_REQUIRED = "STEP_UP_REQUIRED"
    STEP_UP_FAILURE = "STEP_UP_FAILURE"
    SEPARATION_OF_DUTIES_REQUIRED = "SEPARATION_OF_DUTIES_REQUIRED"
    SEPARATION_OF_DUTIES_SELF = "SEPARATION_OF_DUTIES_SELF"
    SEPARATION_OF_DUTIES_MISMATCH = "SEPARATION_OF_DUTIES_MISMATCH"


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

    @property
    def fingerprint(self) -> str:
        """Return a one-way stable key for owner-private entitlement lookup."""

        if self.kind is PrincipalKind.USER:
            if type(self.issuer) is not Issuer or type(self.subject) is not Subject:
                deny_authorization()
            issuer = self.issuer.reveal().encode("utf-8", errors="strict")
            subject = self.subject.reveal().encode("utf-8", errors="strict")
            material = (
                b"USER\x00"
                + len(issuer).to_bytes(4, "big")
                + issuer
                + len(subject).to_bytes(4, "big")
                + subject
            )
        else:
            if type(self.service_name) is not ServicePrincipalName:
                deny_authorization()
            value = self.service_name.value.encode("ascii", errors="strict")
            material = b"SERVICE\x00" + len(value).to_bytes(4, "big") + value
        return hashlib.sha256(material).hexdigest()

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
        deny_shape = (
            effect is DecisionEffect.DENY
            and reason is not AuthorizationDecisionReason.RULE_MATCH
            and matched_rule_id is None
        )
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

    @property
    def canonical_key(self) -> tuple[object, ...]:
        return (
            self.correlation_id.value,
            self.effect.value,
            self.reason.value,
            self.policy_revision.value,
            self.policy_fingerprint,
            self.entitlement_revision.value,
            None if self.matched_rule_id is None else self.matched_rule_id.value,
            self.action.value,
            self.target.canonical_key,
        )

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is AuthorizationDecision
            and self.canonical_key == other.canonical_key
        )

    def __hash__(self) -> int:
        return hash(self.canonical_key)


@final
class AuthorizationGrant(_RedactedValue):
    """Trusted in-process allow value; not service provenance or an executor."""

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


def require_authorization_utc(value: datetime) -> datetime:
    """Normalize an exact timezone-aware UTC instant."""

    if type(value) is not datetime or value.tzinfo is None:
        deny_authorization()
    try:
        normalized = value.astimezone(timezone.utc)
    except OverflowError, ValueError:
        deny_authorization()
    if normalized.utcoffset() is None:
        deny_authorization()
    return normalized


class MatrixAction(str, Enum):
    """The complete action vocabulary from RAOS-SEC-RBAC-001."""

    VIEW_PUBLIC = "view_public"
    EDIT_ARTICLE_DRAFT = "edit_article_draft"
    REVIEW_ARTICLE = "review_article"
    FINAL_APPROVE = "final_approve"
    PUBLISH = "publish"
    ROLLBACK = "rollback"
    ACTIVATE_PUBLICATION_KILL_SWITCH = "activate_publication_kill_switch"
    DEACTIVATE_PUBLICATION_KILL_SWITCH = "deactivate_publication_kill_switch"
    ACTIVATE_AFFILIATE_KILL_SWITCH = "activate_affiliate_kill_switch"
    DEACTIVATE_AFFILIATE_KILL_SWITCH = "deactivate_affiliate_kill_switch"
    MANAGE_PRODUCT_IDENTITY = "manage_product_identity"
    VIEW_FINANCE = "view_finance"
    COMMIT_REVENUE_IMPORT = "commit_revenue_import"
    VIEW_RAW_ARTIFACT = "view_raw_artifact"
    MANAGE_AI_RELEASE = "manage_ai_release"
    MANAGE_POLICY = "manage_policy"
    VIEW_AUDIT = "view_audit"
    MANAGE_SECRETS = "manage_secrets"
    BREAK_GLASS = "break_glass"


class AuthorizationDataClass(str, Enum):
    PUBLIC = "PUBLIC"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class AuthorizationBindingStatus(str, Enum):
    """Whether all evidence needed for one local binding is closed."""

    ACTIVE_RECORDED = "ACTIVE_RECORDED"
    BLOCKED = "BLOCKED"


class AuthorizationBindingBlockReason(str, Enum):
    """Closed reasons that prevent an operation from becoming authorizable."""

    UNMAPPED_OPERATION = "UNMAPPED_OPERATION"
    AMBIGUOUS_OPERATION = "AMBIGUOUS_OPERATION"
    RESOURCE_SCOPE_UNRESOLVED = "RESOURCE_SCOPE_UNRESOLVED"
    RESOURCE_STATE_UNRESOLVED = "RESOURCE_STATE_UNRESOLVED"
    CROSS_RESOURCE_BINDING_UNRESOLVED = "CROSS_RESOURCE_BINDING_UNRESOLVED"
    STEP_UP_RESOURCE_UNMAPPED = "STEP_UP_RESOURCE_UNMAPPED"
    OPERATION_VARIANT_UNRESOLVED = "OPERATION_VARIANT_UNRESOLVED"
    SITE_SCOPE_CONFLICT = "SITE_SCOPE_CONFLICT"
    SERVICE_PRINCIPAL_MAPPING_UNRESOLVED = "SERVICE_PRINCIPAL_MAPPING_UNRESOLVED"
    PUBLIC_SURFACE_NOT_ADMIN_AUTHORIZATION = "PUBLIC_SURFACE_NOT_ADMIN_AUTHORIZATION"


@final
class OperationId(_BoundedToken):
    """One exact API operation ID; hierarchy and wildcard syntax are absent."""

    __slots__ = ()


@final
class AuthorizationCommandId(_BoundedToken):
    """One idempotency key for a decision command journal entry."""

    __slots__ = ()


class AuthorizationRepositoryFailureCode(str, Enum):
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    COMMAND_UNKNOWN = "COMMAND_UNKNOWN"
    COMMAND_CONFLICT = "COMMAND_CONFLICT"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    STORAGE_COMMIT_UNKNOWN = "STORAGE_COMMIT_UNKNOWN"
    TAMPER_DETECTED = "TAMPER_DETECTED"


@final
class AuthorizationRepositoryFailure(RuntimeError):
    """Closed infrastructure failure carrying no rejected request material."""

    __slots__ = ("_code", "_sealed")

    _code: AuthorizationRepositoryFailureCode
    _sealed: bool

    def __init__(self, code: AuthorizationRepositoryFailureCode) -> None:
        if type(code) is not AuthorizationRepositoryFailureCode:
            raise TypeError("invalid authorization repository failure")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)
        object.__setattr__(self, "_sealed", True)

    @property
    def code(self) -> AuthorizationRepositoryFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("AuthorizationRepositoryFailure is immutable")

    def __repr__(self) -> str:
        return f"AuthorizationRepositoryFailure({self.code.value})"


def fail_authorization_repository(
    code: AuthorizationRepositoryFailureCode,
) -> NoReturn:
    raise AuthorizationRepositoryFailure(code) from None


@dataclass(frozen=True, slots=True, repr=False)
class MatrixPermissionDefinition:
    """One exact Canonical matrix row, independent of runtime assignments."""

    action: MatrixAction
    data_class: AuthorizationDataClass
    allowed_roles: tuple[BusinessRole, ...]
    mfa_required: bool
    step_up_required: bool
    separation_of_duties: bool
    blocked_reason: AuthorizationBindingBlockReason | None = None
    required_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        role_values = tuple(role.value for role in self.allowed_roles)
        if (
            type(self.action) is not MatrixAction
            or type(self.data_class) is not AuthorizationDataClass
            or type(self.allowed_roles) is not tuple
            or not self.allowed_roles
            or any(type(role) is not BusinessRole for role in self.allowed_roles)
            or role_values != tuple(sorted(role_values))
            or len(set(role_values)) != len(role_values)
            or type(self.mfa_required) is not bool
            or type(self.step_up_required) is not bool
            or type(self.separation_of_duties) is not bool
            or (
                self.blocked_reason is not None
                and type(self.blocked_reason) is not AuthorizationBindingBlockReason
            )
            or type(self.required_evidence) is not tuple
            or any(
                type(value) is not str
                or not value
                or len(value) > 160
                or value != value.strip()
                for value in self.required_evidence
            )
            or self.required_evidence != tuple(sorted(set(self.required_evidence)))
            or (self.blocked_reason is None) != (not self.required_evidence)
        ):
            deny_authorization()
        if self.step_up_required and not self.mfa_required:
            deny_authorization()

    def __repr__(self) -> str:
        return f"MatrixPermissionDefinition(action={self.action.value!r})"


@dataclass(frozen=True, slots=True, repr=False)
class OperationAuthorizationBinding:
    """Evidence-closed operation mapping or an explicit fail-closed gap."""

    operation_id: OperationId
    action: MatrixAction
    permission_scope: PermissionScope
    resource_kind: ResourceScopeKind
    allowed_states: tuple[ResourceState, ...]
    status: AuthorizationBindingStatus
    block_reason: AuthorizationBindingBlockReason | None = None
    required_evidence: tuple[str, ...] = ()
    step_up_action: CriticalStepUpAction | None = None
    step_up_resource_type: StepUpResourceType | None = None

    def __post_init__(self) -> None:
        state_values = tuple(state.value for state in self.allowed_states)
        blocked = self.status is AuthorizationBindingStatus.BLOCKED
        if (
            type(self.operation_id) is not OperationId
            or type(self.action) is not MatrixAction
            or type(self.permission_scope) is not PermissionScope
            or type(self.resource_kind) is not ResourceScopeKind
            or type(self.allowed_states) is not tuple
            or any(type(state) is not ResourceState for state in self.allowed_states)
            or state_values != tuple(sorted(state_values))
            or len(set(state_values)) != len(state_values)
            or type(self.status) is not AuthorizationBindingStatus
            or blocked != (type(self.block_reason) is AuthorizationBindingBlockReason)
            or type(self.required_evidence) is not tuple
            or any(
                type(value) is not str
                or not value
                or len(value) > 160
                or value != value.strip()
                for value in self.required_evidence
            )
            or self.required_evidence != tuple(sorted(set(self.required_evidence)))
            or blocked != bool(self.required_evidence)
            or (self.step_up_action is None) != (self.step_up_resource_type is None)
            or (
                self.step_up_action is not None
                and type(self.step_up_action) is not CriticalStepUpAction
            )
            or (
                self.step_up_resource_type is not None
                and type(self.step_up_resource_type) is not StepUpResourceType
            )
            or (
                self.step_up_action is not None
                and self.step_up_action.value != self.action.value
            )
        ):
            deny_authorization()

    @property
    def canonical_key(self) -> tuple[str, str]:
        return (self.operation_id.value, self.action.value)

    def accepts_state(self, state: ResourceState | None) -> bool:
        if not self.allowed_states:
            return state is None
        return type(state) is ResourceState and state in self.allowed_states

    def __repr__(self) -> str:
        return (
            "OperationAuthorizationBinding("
            f"operation_id={self.operation_id.value!r},status={self.status.value!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizationBindingResolution:
    operation_id: OperationId
    status: AuthorizationBindingStatus
    action: MatrixAction | None
    binding: OperationAuthorizationBinding | None
    block_reason: AuthorizationBindingBlockReason | None
    required_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        active = self.status is AuthorizationBindingStatus.ACTIVE_RECORDED
        binding = self.binding
        if (
            type(self.operation_id) is not OperationId
            or type(self.status) is not AuthorizationBindingStatus
            or (self.action is not None and type(self.action) is not MatrixAction)
            or active != (type(self.binding) is OperationAuthorizationBinding)
            or active == (type(self.block_reason) is AuthorizationBindingBlockReason)
            or type(self.required_evidence) is not tuple
            or any(
                type(value) is not str
                or not value
                or len(value) > 160
                or value != value.strip()
                for value in self.required_evidence
            )
            or self.required_evidence != tuple(sorted(set(self.required_evidence)))
            or active == bool(self.required_evidence)
            or (
                active
                and (
                    self.action is None
                    or type(binding) is not OperationAuthorizationBinding
                    or binding.status is not AuthorizationBindingStatus.ACTIVE_RECORDED
                    or binding.operation_id != self.operation_id
                    or binding.action is not self.action
                    or binding.block_reason is not None
                    or binding.required_evidence
                )
            )
        ):
            deny_authorization()

    def __repr__(self) -> str:
        return f"AuthorizationBindingResolution(status={self.status.value!r})"


@final
class CanonicalAuthorizationRegistry:
    """Closed role/action/operation registry; unknown or ambiguous means blocked."""

    __slots__ = ("_bindings", "_definitions", "_definitions_by_action")

    _bindings: tuple[OperationAuthorizationBinding, ...]
    _definitions: tuple[MatrixPermissionDefinition, ...]
    _definitions_by_action: Mapping[MatrixAction, MatrixPermissionDefinition]

    def __init__(
        self,
        *,
        definitions: tuple[MatrixPermissionDefinition, ...],
        bindings: tuple[OperationAuthorizationBinding, ...],
    ) -> None:
        definition_keys = tuple(value.action.value for value in definitions)
        binding_keys = tuple(value.canonical_key for value in bindings)
        if (
            type(definitions) is not tuple
            or len(definitions) != len(MatrixAction)
            or any(
                type(value) is not MatrixPermissionDefinition for value in definitions
            )
            or definition_keys != tuple(sorted(definition_keys))
            or set(definition_keys) != {action.value for action in MatrixAction}
            or type(bindings) is not tuple
            or any(
                type(value) is not OperationAuthorizationBinding for value in bindings
            )
            or binding_keys != tuple(sorted(binding_keys))
            or len(set(binding_keys)) != len(binding_keys)
        ):
            deny_authorization()
        by_action = {value.action: value for value in definitions}
        for binding in bindings:
            definition = by_action[binding.action]
            if definition.step_up_required or definition.mfa_required:
                if binding.status is AuthorizationBindingStatus.ACTIVE_RECORDED and (
                    binding.step_up_action is None
                    or binding.step_up_resource_type is None
                    or binding.step_up_action.value != binding.action.value
                    or binding.step_up_resource_type.value
                    != binding.resource_kind.value
                ):
                    deny_authorization()
            elif (
                binding.step_up_action is not None
                or binding.step_up_resource_type is not None
            ):
                deny_authorization()
            if definition.blocked_reason is not None and (
                binding.status is AuthorizationBindingStatus.ACTIVE_RECORDED
            ):
                deny_authorization()
        object.__setattr__(self, "_definitions", definitions)
        object.__setattr__(self, "_bindings", bindings)
        object.__setattr__(self, "_definitions_by_action", MappingProxyType(by_action))

    @property
    def definitions(self) -> tuple[MatrixPermissionDefinition, ...]:
        return self._definitions

    @property
    def bindings(self) -> tuple[OperationAuthorizationBinding, ...]:
        return self._bindings

    def definition(self, action: MatrixAction) -> MatrixPermissionDefinition:
        if type(action) is not MatrixAction:
            deny_authorization()
        return self._definitions_by_action[action]

    def resolve(self, operation_id: OperationId) -> AuthorizationBindingResolution:
        if type(operation_id) is not OperationId:
            deny_authorization()
        candidates = tuple(
            binding
            for binding in self._bindings
            if binding.operation_id == operation_id
        )
        if not candidates:
            return AuthorizationBindingResolution(
                operation_id=operation_id,
                status=AuthorizationBindingStatus.BLOCKED,
                action=None,
                binding=None,
                block_reason=AuthorizationBindingBlockReason.UNMAPPED_OPERATION,
                required_evidence=("exact_action_operation_resource_state_mapping",),
            )
        actions = {candidate.action for candidate in candidates}
        active = tuple(
            candidate
            for candidate in candidates
            if candidate.status is AuthorizationBindingStatus.ACTIVE_RECORDED
        )
        if len(candidates) != 1 or len(actions) != 1 or len(active) != 1:
            evidence = tuple(
                sorted(
                    {
                        item
                        for candidate in candidates
                        for item in candidate.required_evidence
                    }
                    or {"exact_operation_variant_discriminator"}
                )
            )
            return AuthorizationBindingResolution(
                operation_id=operation_id,
                status=AuthorizationBindingStatus.BLOCKED,
                action=next(iter(actions)) if len(actions) == 1 else None,
                binding=None,
                block_reason=(
                    AuthorizationBindingBlockReason.AMBIGUOUS_OPERATION
                    if len(candidates) != 1 or len(actions) != 1
                    else candidates[0].block_reason
                ),
                required_evidence=evidence,
            )
        selected = active[0]
        return AuthorizationBindingResolution(
            operation_id=operation_id,
            status=AuthorizationBindingStatus.ACTIVE_RECORDED,
            action=selected.action,
            binding=selected,
            block_reason=None,
            required_evidence=(),
        )

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("CanonicalAuthorizationRegistry is immutable")


@dataclass(frozen=True, slots=True, repr=False)
class IndependentActorEvidence:
    """Immutable server-recorded proof used only for a SoD comparison."""

    evidence_id: UUID
    actor_fingerprint: str = field(repr=False)
    action: MatrixAction
    operation_id: OperationId
    site_id: UUID
    resource_id: UUID
    evidence_snapshot_sha256: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.evidence_id) is not UUID
            or self.evidence_id.int == 0
            or type(self.actor_fingerprint) is not str
            or _FINGERPRINT.fullmatch(self.actor_fingerprint) is None
            or self.actor_fingerprint == "0" * 64
            or type(self.action) is not MatrixAction
            or type(self.operation_id) is not OperationId
            or type(self.site_id) is not UUID
            or self.site_id.int == 0
            or type(self.resource_id) is not UUID
            or self.resource_id.int == 0
            or type(self.evidence_snapshot_sha256) is not str
            or _FINGERPRINT.fullmatch(self.evidence_snapshot_sha256) is None
        ):
            deny_authorization()
        object.__setattr__(
            self, "recorded_at", require_authorization_utc(self.recorded_at)
        )

    @property
    def fingerprint(self) -> str:
        material = "|".join(
            (
                self.evidence_id.hex,
                self.actor_fingerprint,
                self.action.value,
                self.operation_id.value,
                self.site_id.hex,
                self.resource_id.hex,
                self.evidence_snapshot_sha256,
                self.recorded_at.isoformat(timespec="microseconds"),
            )
        )
        return hashlib.sha256(material.encode("ascii")).hexdigest()

    def __repr__(self) -> str:
        return "IndependentActorEvidence(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizationEvaluationCommand:
    """Caller-independent operation request for a recorded decision only."""

    command_id: AuthorizationCommandId
    operation_id: OperationId
    target: AuthorizationTarget
    correlation_id: CorrelationId
    expected_policy_revision: PolicyRevision
    expected_entitlement_revision: EntitlementRevision
    observed_at: datetime
    step_up_command_id: StepUpCommandId | None = field(default=None, repr=False)
    step_up_grant_id: BoundStepUpGrantId | None = field(default=None, repr=False)
    independent_actor_evidence_id: UUID | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.command_id) is not AuthorizationCommandId
            or type(self.operation_id) is not OperationId
            or type(self.target) is not AuthorizationTarget
            or type(self.correlation_id) is not CorrelationId
            or type(self.expected_policy_revision) is not PolicyRevision
            or type(self.expected_entitlement_revision) is not EntitlementRevision
            or (self.step_up_command_id is None) != (self.step_up_grant_id is None)
            or (
                self.step_up_command_id is not None
                and type(self.step_up_command_id) is not StepUpCommandId
            )
            or (
                self.step_up_grant_id is not None
                and type(self.step_up_grant_id) is not BoundStepUpGrantId
            )
            or (
                self.independent_actor_evidence_id is not None
                and (
                    type(self.independent_actor_evidence_id) is not UUID
                    or self.independent_actor_evidence_id.int == 0
                )
            )
        ):
            deny_authorization()
        object.__setattr__(
            self, "observed_at", require_authorization_utc(self.observed_at)
        )

    def request_digest(self, *, session_fingerprint: str) -> str:
        if (
            type(session_fingerprint) is not str
            or _FINGERPRINT.fullmatch(session_fingerprint) is None
        ):
            deny_authorization()
        material = "|".join(
            (
                self.operation_id.value,
                *self.target.canonical_key,
                self.correlation_id.value,
                self.expected_policy_revision.value,
                self.expected_entitlement_revision.value,
                self.observed_at.isoformat(timespec="microseconds"),
                session_fingerprint,
                ""
                if self.step_up_command_id is None
                else self.step_up_command_id.fingerprint(),
                ""
                if self.step_up_grant_id is None
                else self.step_up_grant_id.fingerprint(),
                ""
                if self.independent_actor_evidence_id is None
                else self.independent_actor_evidence_id.hex,
            )
        )
        return hashlib.sha256(material.encode("ascii")).hexdigest()

    def __repr__(self) -> str:
        return "AuthorizationEvaluationCommand(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizationAuditRecord:
    sequence: int
    command_fingerprint: str
    request_digest: str
    effect: DecisionEffect
    occurred_at: datetime
    previous_digest: str
    digest: str

    def __post_init__(self) -> None:
        if (
            type(self.sequence) is not int
            or self.sequence <= 0
            or type(self.command_fingerprint) is not str
            or _FINGERPRINT.fullmatch(self.command_fingerprint) is None
            or type(self.request_digest) is not str
            or _FINGERPRINT.fullmatch(self.request_digest) is None
            or type(self.effect) is not DecisionEffect
            or type(self.previous_digest) is not str
            or _FINGERPRINT.fullmatch(self.previous_digest) is None
            or type(self.digest) is not str
            or _FINGERPRINT.fullmatch(self.digest) is None
        ):
            fail_authorization_repository(
                AuthorizationRepositoryFailureCode.TAMPER_DETECTED
            )
        object.__setattr__(
            self, "occurred_at", require_authorization_utc(self.occurred_at)
        )

    def __repr__(self) -> str:
        return "AuthorizationAuditRecord(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizationCommandResult:
    command_id: AuthorizationCommandId
    request_digest: str
    session_fingerprint: str = field(repr=False)
    decision: AuthorizationDecision
    audit: AuthorizationAuditRecord
    step_up_receipt_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.command_id) is not AuthorizationCommandId
            or type(self.request_digest) is not str
            or _FINGERPRINT.fullmatch(self.request_digest) is None
            or type(self.session_fingerprint) is not str
            or _FINGERPRINT.fullmatch(self.session_fingerprint) is None
            or type(self.decision) is not AuthorizationDecision
            or type(self.audit) is not AuthorizationAuditRecord
            or self.audit.command_fingerprint != self.command_id_fingerprint
            or self.audit.request_digest != self.request_digest
            or self.audit.effect is not self.decision.effect
            or (
                self.step_up_receipt_fingerprint is not None
                and (
                    type(self.step_up_receipt_fingerprint) is not str
                    or _FINGERPRINT.fullmatch(self.step_up_receipt_fingerprint) is None
                )
            )
        ):
            fail_authorization_repository(
                AuthorizationRepositoryFailureCode.TAMPER_DETECTED
            )

    @property
    def command_id_fingerprint(self) -> str:
        return hashlib.sha256(self.command_id.value.encode("ascii")).hexdigest()

    def grant(self) -> AuthorizationGrant:
        """Normalize one recorded allow result inside the trusted process TCB."""

        if self.decision.effect is not DecisionEffect.ALLOW:
            deny_authorization()
        return AuthorizationGrant(recorded_decision=self.decision)

    def __repr__(self) -> str:
        return "AuthorizationCommandResult(<redacted>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("authorization command result serialization is not supported")


def snapshot_authorization_principal(value: object) -> PrincipalIdentity:
    """Detach one exact principal from an untrusted in-process collaborator."""

    if type(value) is not PrincipalIdentity:
        deny_authorization()
    if value.kind is PrincipalKind.USER:
        if type(value.issuer) is not Issuer or type(value.subject) is not Subject:
            deny_authorization()
        return PrincipalIdentity.admin_user(
            issuer=Issuer(value.issuer.reveal()),
            subject=Subject(value.subject.reveal()),
        )
    if type(value.service_name) is not ServicePrincipalName:
        deny_authorization()
    return PrincipalIdentity(
        kind=PrincipalKind.SERVICE,
        surface=AuthorizationSurface.INTERNAL,
        service_name=ServicePrincipalName(value.service_name.value),
    )


def snapshot_authorization_scope(value: object) -> ResourceScope:
    if type(value) is not ResourceScope:
        deny_authorization()
    return ResourceScope(
        kind=value.kind,
        site_id=UUID(str(value.site_id)),
        resource_id=UUID(str(value.resource_id)),
    )


def snapshot_authorization_target(value: object) -> AuthorizationTarget:
    if type(value) is not AuthorizationTarget:
        deny_authorization()
    return AuthorizationTarget(
        scope=snapshot_authorization_scope(value.scope),
        state=None if value.state is None else ResourceState(value.state.value),
    )


def snapshot_authorization_rule(value: object) -> AuthorizationRule:
    if type(value) is not AuthorizationRule:
        deny_authorization()
    return AuthorizationRule(
        rule_id=RuleId(value.rule_id.value),
        role=value.role,
        permission_scope=PermissionScope(value.permission_scope.value),
        action=ActionCode(value.action.value),
        resource_kind=value.resource_kind,
        resource_state=(
            None
            if value.resource_state is None
            else ResourceState(value.resource_state.value)
        ),
    )


def snapshot_policy_snapshot(value: object) -> PolicySnapshot:
    if type(value) is not PolicySnapshot:
        deny_authorization()
    value.require_valid()
    revision = PolicyRevision(value.revision.value)
    rules = tuple(snapshot_authorization_rule(rule) for rule in value.rules)
    if value.mode is PolicyMode.DISABLED:
        return PolicySnapshot(revision=revision, mode=PolicyMode.DISABLED, rules=rules)
    if value.mode is PolicyMode.RECORDED_TEST:
        return _recorded_test_policy_snapshot(revision=revision, rules=rules)
    deny_authorization()


def snapshot_entitlement_snapshot(value: object) -> EntitlementSnapshot:
    if type(value) is not EntitlementSnapshot:
        deny_authorization()
    value.require_valid()
    principal = snapshot_authorization_principal(value.principal)
    return EntitlementSnapshot(
        revision=EntitlementRevision(value.revision.value),
        principal=principal,
        roles=tuple(
            ScopedBusinessRole(
                role=role.role,
                scope=snapshot_authorization_scope(role.scope),
            )
            for role in value.roles
        ),
        permission_scopes=tuple(
            ScopedPermission(
                permission_scope=PermissionScope(permission.permission_scope.value),
                scope=snapshot_authorization_scope(permission.scope),
            )
            for permission in value.permission_scopes
        ),
    )


def snapshot_authorization_decision(value: object) -> AuthorizationDecision:
    if type(value) is not AuthorizationDecision:
        deny_authorization()
    return AuthorizationDecision(
        correlation_id=CorrelationId(value.correlation_id.value),
        effect=value.effect,
        reason=value.reason,
        policy_revision=PolicyRevision(value.policy_revision.value),
        policy_fingerprint=str(value.policy_fingerprint),
        entitlement_revision=EntitlementRevision(value.entitlement_revision.value),
        matched_rule_id=(
            None
            if value.matched_rule_id is None
            else RuleId(value.matched_rule_id.value)
        ),
        action=ActionCode(value.action.value),
        target=snapshot_authorization_target(value.target),
    )


def snapshot_independent_actor_evidence(
    value: object,
) -> IndependentActorEvidence:
    if type(value) is not IndependentActorEvidence:
        deny_authorization()
    return IndependentActorEvidence(
        evidence_id=UUID(str(value.evidence_id)),
        actor_fingerprint=str(value.actor_fingerprint),
        action=value.action,
        operation_id=OperationId(value.operation_id.value),
        site_id=UUID(str(value.site_id)),
        resource_id=UUID(str(value.resource_id)),
        evidence_snapshot_sha256=str(value.evidence_snapshot_sha256),
        recorded_at=value.recorded_at.replace(),
    )


def snapshot_authorization_evaluation_command(
    value: object,
) -> AuthorizationEvaluationCommand:
    if type(value) is not AuthorizationEvaluationCommand:
        deny_authorization()
    return AuthorizationEvaluationCommand(
        command_id=AuthorizationCommandId(value.command_id.value),
        operation_id=OperationId(value.operation_id.value),
        target=snapshot_authorization_target(value.target),
        correlation_id=CorrelationId(value.correlation_id.value),
        expected_policy_revision=PolicyRevision(value.expected_policy_revision.value),
        expected_entitlement_revision=EntitlementRevision(
            value.expected_entitlement_revision.value
        ),
        observed_at=value.observed_at.replace(),
        step_up_command_id=(
            None
            if value.step_up_command_id is None
            else StepUpCommandId(value.step_up_command_id.reveal())
        ),
        step_up_grant_id=(
            None
            if value.step_up_grant_id is None
            else BoundStepUpGrantId(value.step_up_grant_id.reveal())
        ),
        independent_actor_evidence_id=(
            None
            if value.independent_actor_evidence_id is None
            else UUID(str(value.independent_actor_evidence_id))
        ),
    )


def snapshot_authorization_audit(value: object) -> AuthorizationAuditRecord:
    if type(value) is not AuthorizationAuditRecord:
        fail_authorization_repository(
            AuthorizationRepositoryFailureCode.TAMPER_DETECTED
        )
    return AuthorizationAuditRecord(
        sequence=value.sequence,
        command_fingerprint=str(value.command_fingerprint),
        request_digest=str(value.request_digest),
        effect=value.effect,
        occurred_at=value.occurred_at.replace(),
        previous_digest=str(value.previous_digest),
        digest=str(value.digest),
    )


def snapshot_authorization_result(value: object) -> AuthorizationCommandResult:
    if type(value) is not AuthorizationCommandResult:
        fail_authorization_repository(
            AuthorizationRepositoryFailureCode.TAMPER_DETECTED
        )
    return AuthorizationCommandResult(
        command_id=AuthorizationCommandId(value.command_id.value),
        request_digest=str(value.request_digest),
        session_fingerprint=str(value.session_fingerprint),
        decision=snapshot_authorization_decision(value.decision),
        audit=snapshot_authorization_audit(value.audit),
        step_up_receipt_fingerprint=(
            None
            if value.step_up_receipt_fingerprint is None
            else str(value.step_up_receipt_fingerprint)
        ),
    )


class ServicePrincipalAuthorizationStatus(str, Enum):
    DISABLED_MAPPING_UNRESOLVED = "DISABLED_MAPPING_UNRESOLVED"


__all__ = [
    "ActionCode",
    "AuthorizationAuditRecord",
    "AuthorizationBindingBlockReason",
    "AuthorizationBindingResolution",
    "AuthorizationBindingStatus",
    "AuthorizationCommandId",
    "AuthorizationCommandResult",
    "AuthorizationDataClass",
    "AuthorizationDecision",
    "AuthorizationDecisionReason",
    "AuthorizationFailure",
    "AuthorizationFailureCode",
    "AuthorizationGrant",
    "AuthorizationEvaluationCommand",
    "AuthorizationRepositoryFailure",
    "AuthorizationRepositoryFailureCode",
    "AuthorizationRule",
    "AuthorizationSurface",
    "AuthorizationTarget",
    "BusinessRole",
    "CanonicalAuthorizationRegistry",
    "CorrelationId",
    "DecisionEffect",
    "EntitlementRevision",
    "EntitlementSnapshot",
    "IndependentActorEvidence",
    "MatrixAction",
    "MatrixPermissionDefinition",
    "OperationAuthorizationBinding",
    "OperationId",
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
    "ServicePrincipalAuthorizationStatus",
    "ServicePrincipalName",
    "deny_authorization",
    "disabled_policy_snapshot",
    "fail_authorization_repository",
    "require_authorization_utc",
    "snapshot_authorization_audit",
    "snapshot_authorization_decision",
    "snapshot_authorization_evaluation_command",
    "snapshot_authorization_principal",
    "snapshot_authorization_result",
    "snapshot_authorization_rule",
    "snapshot_authorization_scope",
    "snapshot_authorization_target",
    "snapshot_entitlement_snapshot",
    "snapshot_independent_actor_evidence",
    "snapshot_policy_snapshot",
]
