"""Exact immutable IAM persistence domain values for ST-0308."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import NoReturn
import unicodedata

from raos.domain.iam.enums import (
    PermissionRiskLevel,
    PermissionStatus,
    PrincipalPrincipalType,
    PrincipalRoleAssignmentScopeType,
    PrincipalStatus,
    RoleStatus,
    ServicePrincipalAllowedEnvironment,
)
from raos.domain.iam.ids import (
    BreakGlassRecordId,
    PermissionId,
    PrincipalId,
    PrincipalRoleAssignmentId,
    RoleId,
    SessionRevocationId,
)
from raos.domain.iam.values import (
    BreakGlassRecordPermissionsJson,
)
from raos.domain.ops.ids import (
    IncidentId,
)
from raos.domain.shared.identity import (
    ScopeId,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    EmailAddress,
)
from raos.domain.shared.identity import EntityId

_MAX_BIGINT = (1 << 63) - 1


def _invalid() -> NoReturn:
    raise ValueError("INVALID_IAM_PERSISTENCE_VALUE") from None


def _text(value: object) -> None:
    if (
        type(value) is not str
        or not value
        or len(value) > 4096
        or value != value.strip()
        or unicodedata.normalize("NFC", value) != value
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        _invalid()


def _integer(value: object) -> None:
    if type(value) is not int or not 0 <= value <= _MAX_BIGINT:
        _invalid()


def _decimal(value: object) -> None:
    if type(value) is not Decimal or not value.is_finite():
        _invalid()


def _nominal(value: object, module: str, name: str) -> None:
    if (
        not isinstance(value, EntityId)
        or type(value).__module__ != module
        or type(value).__name__ != name
    ):
        _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class BreakGlassRecord:
    id: BreakGlassRecordId
    display_id: str
    principal_id: PrincipalId
    incident_id: IncidentId
    reason: str
    approved_by_principal_id: PrincipalId
    permissions: BreakGlassRecordPermissionsJson
    started_at: AwareUtcDateTime
    expires_at: AwareUtcDateTime
    ended_at: AwareUtcDateTime | None
    end_reason: str | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not BreakGlassRecordId:
            _invalid()
        _text(self.display_id)
        if type(self.principal_id) is not PrincipalId:
            _invalid()
        if type(self.incident_id) is not IncidentId:
            _invalid()
        _text(self.reason)
        if type(self.approved_by_principal_id) is not PrincipalId:
            _invalid()
        if type(self.permissions) is not BreakGlassRecordPermissionsJson:
            _invalid()
        if type(self.started_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.expires_at) is not AwareUtcDateTime:
            _invalid()
        if self.ended_at is not None:
            if type(self.ended_at) is not AwareUtcDateTime:
                _invalid()
        if self.end_reason is not None:
            _text(self.end_reason)
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "BreakGlassRecord(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Permission:
    id: PermissionId
    permission_code: str
    description: str
    risk_level: PermissionRiskLevel
    status: PermissionStatus
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not PermissionId:
            _invalid()
        _text(self.permission_code)
        _text(self.description)
        if type(self.risk_level) is not PermissionRiskLevel:
            _invalid()
        if type(self.status) is not PermissionStatus:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "Permission(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class PrincipalState:
    id: PrincipalId
    display_id: str
    principal_type: PrincipalPrincipalType
    status: PrincipalStatus
    display_name: str
    deactivated_at: AwareUtcDateTime | None
    deactivation_reason: str | None
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    lock_version: AggregateVersion

    def __post_init__(self) -> None:
        if type(self.id) is not PrincipalId:
            _invalid()
        _text(self.display_id)
        if type(self.principal_type) is not PrincipalPrincipalType:
            _invalid()
        if type(self.status) is not PrincipalStatus:
            _invalid()
        _text(self.display_name)
        if self.deactivated_at is not None:
            if type(self.deactivated_at) is not AwareUtcDateTime:
                _invalid()
        if self.deactivation_reason is not None:
            _text(self.deactivation_reason)
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.updated_at) is not AwareUtcDateTime:
            _invalid()
        if type(self.lock_version) is not AggregateVersion:
            _invalid()

    def __repr__(self) -> str:
        return "PrincipalState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class PrincipalRoleAssignmentRecord:
    id: PrincipalRoleAssignmentId
    principal_id: PrincipalId
    role_id: RoleId
    scope_type: PrincipalRoleAssignmentScopeType
    scope_id: ScopeId | None
    valid_from: AwareUtcDateTime
    valid_to: AwareUtcDateTime | None
    assigned_by_principal_id: PrincipalId
    assignment_reason: str
    revoked_at: AwareUtcDateTime | None
    revoked_by_principal_id: PrincipalId | None
    revocation_reason: str | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not PrincipalRoleAssignmentId:
            _invalid()
        if type(self.principal_id) is not PrincipalId:
            _invalid()
        if type(self.role_id) is not RoleId:
            _invalid()
        if type(self.scope_type) is not PrincipalRoleAssignmentScopeType:
            _invalid()
        if self.scope_id is not None:
            if type(self.scope_id) is not ScopeId:
                _invalid()
        if type(self.valid_from) is not AwareUtcDateTime:
            _invalid()
        if self.valid_to is not None:
            if type(self.valid_to) is not AwareUtcDateTime:
                _invalid()
        if type(self.assigned_by_principal_id) is not PrincipalId:
            _invalid()
        _text(self.assignment_reason)
        if self.revoked_at is not None:
            if type(self.revoked_at) is not AwareUtcDateTime:
                _invalid()
        if self.revoked_by_principal_id is not None:
            if type(self.revoked_by_principal_id) is not PrincipalId:
                _invalid()
        if self.revocation_reason is not None:
            _text(self.revocation_reason)
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "PrincipalRoleAssignmentRecord(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Role:
    id: RoleId
    role_code: str
    name: str
    description: str
    is_system_role: bool
    status: RoleStatus
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not RoleId:
            _invalid()
        _text(self.role_code)
        _text(self.name)
        _text(self.description)
        if type(self.is_system_role) is not bool:
            _invalid()
        if type(self.status) is not RoleStatus:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "Role(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RolePermissionBinding:
    role_id: RoleId
    permission_id: PermissionId
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.role_id) is not RoleId:
            _invalid()
        if type(self.permission_id) is not PermissionId:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "RolePermissionBinding(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ServicePrincipal:
    principal_id: PrincipalId
    service_code: str
    workload_identity: str
    allowed_environment: ServicePrincipalAllowedEnvironment
    credential_rotated_at: AwareUtcDateTime | None
    last_used_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.principal_id) is not PrincipalId:
            _invalid()
        _text(self.service_code)
        _text(self.workload_identity)
        if type(self.allowed_environment) is not ServicePrincipalAllowedEnvironment:
            _invalid()
        if self.credential_rotated_at is not None:
            if type(self.credential_rotated_at) is not AwareUtcDateTime:
                _invalid()
        if self.last_used_at is not None:
            if type(self.last_used_at) is not AwareUtcDateTime:
                _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "ServicePrincipal(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SessionRevocation:
    id: SessionRevocationId
    principal_id: PrincipalId
    oidc_issuer: str
    oidc_subject: str
    revoke_before: AwareUtcDateTime
    reason: str
    created_by_principal_id: PrincipalId
    expires_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not SessionRevocationId:
            _invalid()
        if type(self.principal_id) is not PrincipalId:
            _invalid()
        _text(self.oidc_issuer)
        _text(self.oidc_subject)
        if type(self.revoke_before) is not AwareUtcDateTime:
            _invalid()
        _text(self.reason)
        if type(self.created_by_principal_id) is not PrincipalId:
            _invalid()
        if self.expires_at is not None:
            if type(self.expires_at) is not AwareUtcDateTime:
                _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "SessionRevocation(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class UserAccount:
    principal_id: PrincipalId
    oidc_issuer: str
    oidc_subject: str
    email: EmailAddress | None
    email_verified: bool
    mfa_required: bool
    last_login_at: AwareUtcDateTime | None
    last_mfa_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.principal_id) is not PrincipalId:
            _invalid()
        _text(self.oidc_issuer)
        _text(self.oidc_subject)
        if self.email is not None:
            if type(self.email) is not EmailAddress:
                _invalid()
        if type(self.email_verified) is not bool:
            _invalid()
        if type(self.mfa_required) is not bool:
            _invalid()
        if self.last_login_at is not None:
            if type(self.last_login_at) is not AwareUtcDateTime:
                _invalid()
        if self.last_mfa_at is not None:
            if type(self.last_mfa_at) is not AwareUtcDateTime:
                _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "UserAccount(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Principal:
    state: PrincipalState
    user_account: UserAccount | None = None
    service_principal: ServicePrincipal | None = None

    def __post_init__(self) -> None:
        if type(self.state) is not PrincipalState:
            _invalid()
        if self.user_account is not None and type(self.user_account) is not UserAccount:
            _invalid()
        if (
            self.user_account is not None
            and self.user_account.principal_id.value != self.state.id.value
        ):
            _invalid()
        if (
            self.service_principal is not None
            and type(self.service_principal) is not ServicePrincipal
        ):
            _invalid()
        if (
            self.service_principal is not None
            and self.service_principal.principal_id.value != self.state.id.value
        ):
            _invalid()
        if self.state.principal_type is PrincipalPrincipalType.USER:
            if self.user_account is None or self.service_principal is not None:
                _invalid()
        elif self.service_principal is None or self.user_account is not None:
            _invalid()

    def __repr__(self) -> str:
        return "Principal(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class PrincipalRoleAssignment:
    state: PrincipalRoleAssignmentRecord

    def __post_init__(self) -> None:
        if type(self.state) is not PrincipalRoleAssignmentRecord:
            _invalid()

    def __repr__(self) -> str:
        return "PrincipalRoleAssignment(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RoleCatalog:
    role_rows: tuple[Role, ...] = ()
    permission_rows: tuple[Permission, ...] = ()
    role_permission_rows: tuple[RolePermissionBinding, ...] = ()

    def __post_init__(self) -> None:
        if type(self.role_rows) is not tuple or any(
            type(item) is not Role for item in self.role_rows
        ):
            _invalid()
        if type(self.permission_rows) is not tuple or any(
            type(item) is not Permission for item in self.permission_rows
        ):
            _invalid()
        if type(self.role_permission_rows) is not tuple or any(
            type(item) is not RolePermissionBinding
            for item in self.role_permission_rows
        ):
            _invalid()

    def __repr__(self) -> str:
        return "RoleCatalog(<redacted>)"


__all__ = [
    "BreakGlassRecord",
    "Permission",
    "Principal",
    "PrincipalRoleAssignment",
    "PrincipalRoleAssignmentRecord",
    "PrincipalState",
    "Role",
    "RoleCatalog",
    "RolePermissionBinding",
    "ServicePrincipal",
    "SessionRevocation",
    "UserAccount",
]
