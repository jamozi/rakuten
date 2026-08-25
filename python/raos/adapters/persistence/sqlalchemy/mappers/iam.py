"""Explicit fail-closed scalar mappers for the ST-0308 IAM slice."""

from __future__ import annotations

from raos.adapters.persistence.sqlalchemy.physical_constraints import (
    install_mapper_physical_constraint_guards,
)
from raos.domain.iam.aggregates import (
    BreakGlassRecord,
    Permission,
    PrincipalRoleAssignmentRecord,
    PrincipalState,
    Role,
    RolePermissionBinding,
    ServicePrincipal,
    SessionRevocation,
    UserAccount,
)
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
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


def _corrupt() -> PersistenceError:
    return PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION)


BreakGlassRecordScalars = tuple[
    BreakGlassRecordId,
    str,
    PrincipalId,
    IncidentId,
    str,
    PrincipalId,
    BreakGlassRecordPermissionsJson,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    str | None,
    AwareUtcDateTime,
]


def map_iam_break_glass_record_from_row(
    *,
    id: BreakGlassRecordId,
    display_id: str,
    principal_id: PrincipalId,
    incident_id: IncidentId,
    reason: str,
    approved_by_principal_id: PrincipalId,
    permissions: BreakGlassRecordPermissionsJson,
    started_at: AwareUtcDateTime,
    expires_at: AwareUtcDateTime,
    ended_at: AwareUtcDateTime | None,
    end_reason: str | None,
    created_at: AwareUtcDateTime,
) -> BreakGlassRecord:
    try:
        return BreakGlassRecord(
            id=id,
            display_id=display_id,
            principal_id=principal_id,
            incident_id=incident_id,
            reason=reason,
            approved_by_principal_id=approved_by_principal_id,
            permissions=permissions,
            started_at=started_at,
            expires_at=expires_at,
            ended_at=ended_at,
            end_reason=end_reason,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_iam_break_glass_record_to_row(
    value: BreakGlassRecord,
) -> BreakGlassRecordScalars:
    if type(value) is not BreakGlassRecord:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.principal_id,
        value.incident_id,
        value.reason,
        value.approved_by_principal_id,
        value.permissions,
        value.started_at,
        value.expires_at,
        value.ended_at,
        value.end_reason,
        value.created_at,
    )


PermissionScalars = tuple[
    PermissionId,
    str,
    str,
    PermissionRiskLevel,
    PermissionStatus,
    AwareUtcDateTime,
]


def map_iam_permission_from_row(
    *,
    id: PermissionId,
    permission_code: str,
    description: str,
    risk_level: PermissionRiskLevel,
    status: PermissionStatus,
    created_at: AwareUtcDateTime,
) -> Permission:
    try:
        return Permission(
            id=id,
            permission_code=permission_code,
            description=description,
            risk_level=risk_level,
            status=status,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_iam_permission_to_row(value: Permission) -> PermissionScalars:
    if type(value) is not Permission:
        raise _corrupt() from None
    return (
        value.id,
        value.permission_code,
        value.description,
        value.risk_level,
        value.status,
        value.created_at,
    )


PrincipalStateScalars = tuple[
    PrincipalId,
    str,
    PrincipalPrincipalType,
    PrincipalStatus,
    str,
    AwareUtcDateTime | None,
    str | None,
    AwareUtcDateTime,
    AwareUtcDateTime,
    AggregateVersion,
]


def map_iam_principal_from_row(
    *,
    id: PrincipalId,
    display_id: str,
    principal_type: PrincipalPrincipalType,
    status: PrincipalStatus,
    display_name: str,
    deactivated_at: AwareUtcDateTime | None,
    deactivation_reason: str | None,
    created_at: AwareUtcDateTime,
    updated_at: AwareUtcDateTime,
    lock_version: AggregateVersion,
) -> PrincipalState:
    try:
        return PrincipalState(
            id=id,
            display_id=display_id,
            principal_type=principal_type,
            status=status,
            display_name=display_name,
            deactivated_at=deactivated_at,
            deactivation_reason=deactivation_reason,
            created_at=created_at,
            updated_at=updated_at,
            lock_version=lock_version,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_iam_principal_to_row(value: PrincipalState) -> PrincipalStateScalars:
    if type(value) is not PrincipalState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.principal_type,
        value.status,
        value.display_name,
        value.deactivated_at,
        value.deactivation_reason,
        value.created_at,
        value.updated_at,
        value.lock_version,
    )


PrincipalRoleAssignmentRecordScalars = tuple[
    PrincipalRoleAssignmentId,
    PrincipalId,
    RoleId,
    PrincipalRoleAssignmentScopeType,
    ScopeId | None,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    PrincipalId,
    str,
    AwareUtcDateTime | None,
    PrincipalId | None,
    str | None,
    AwareUtcDateTime,
]


def map_iam_principal_role_assignment_from_row(
    *,
    id: PrincipalRoleAssignmentId,
    principal_id: PrincipalId,
    role_id: RoleId,
    scope_type: PrincipalRoleAssignmentScopeType,
    scope_id: ScopeId | None,
    valid_from: AwareUtcDateTime,
    valid_to: AwareUtcDateTime | None,
    assigned_by_principal_id: PrincipalId,
    assignment_reason: str,
    revoked_at: AwareUtcDateTime | None,
    revoked_by_principal_id: PrincipalId | None,
    revocation_reason: str | None,
    created_at: AwareUtcDateTime,
) -> PrincipalRoleAssignmentRecord:
    try:
        return PrincipalRoleAssignmentRecord(
            id=id,
            principal_id=principal_id,
            role_id=role_id,
            scope_type=scope_type,
            scope_id=scope_id,
            valid_from=valid_from,
            valid_to=valid_to,
            assigned_by_principal_id=assigned_by_principal_id,
            assignment_reason=assignment_reason,
            revoked_at=revoked_at,
            revoked_by_principal_id=revoked_by_principal_id,
            revocation_reason=revocation_reason,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_iam_principal_role_assignment_to_row(
    value: PrincipalRoleAssignmentRecord,
) -> PrincipalRoleAssignmentRecordScalars:
    if type(value) is not PrincipalRoleAssignmentRecord:
        raise _corrupt() from None
    return (
        value.id,
        value.principal_id,
        value.role_id,
        value.scope_type,
        value.scope_id,
        value.valid_from,
        value.valid_to,
        value.assigned_by_principal_id,
        value.assignment_reason,
        value.revoked_at,
        value.revoked_by_principal_id,
        value.revocation_reason,
        value.created_at,
    )


RoleScalars = tuple[
    RoleId,
    str,
    str,
    str,
    bool,
    RoleStatus,
    AwareUtcDateTime,
]


def map_iam_role_from_row(
    *,
    id: RoleId,
    role_code: str,
    name: str,
    description: str,
    is_system_role: bool,
    status: RoleStatus,
    created_at: AwareUtcDateTime,
) -> Role:
    try:
        return Role(
            id=id,
            role_code=role_code,
            name=name,
            description=description,
            is_system_role=is_system_role,
            status=status,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_iam_role_to_row(value: Role) -> RoleScalars:
    if type(value) is not Role:
        raise _corrupt() from None
    return (
        value.id,
        value.role_code,
        value.name,
        value.description,
        value.is_system_role,
        value.status,
        value.created_at,
    )


RolePermissionBindingScalars = tuple[
    RoleId,
    PermissionId,
    AwareUtcDateTime,
]


def map_iam_role_permission_from_row(
    *,
    role_id: RoleId,
    permission_id: PermissionId,
    created_at: AwareUtcDateTime,
) -> RolePermissionBinding:
    try:
        return RolePermissionBinding(
            role_id=role_id,
            permission_id=permission_id,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_iam_role_permission_to_row(
    value: RolePermissionBinding,
) -> RolePermissionBindingScalars:
    if type(value) is not RolePermissionBinding:
        raise _corrupt() from None
    return (
        value.role_id,
        value.permission_id,
        value.created_at,
    )


ServicePrincipalScalars = tuple[
    PrincipalId,
    str,
    str,
    ServicePrincipalAllowedEnvironment,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_iam_service_principal_from_row(
    *,
    principal_id: PrincipalId,
    service_code: str,
    workload_identity: str,
    allowed_environment: ServicePrincipalAllowedEnvironment,
    credential_rotated_at: AwareUtcDateTime | None,
    last_used_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> ServicePrincipal:
    try:
        return ServicePrincipal(
            principal_id=principal_id,
            service_code=service_code,
            workload_identity=workload_identity,
            allowed_environment=allowed_environment,
            credential_rotated_at=credential_rotated_at,
            last_used_at=last_used_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_iam_service_principal_to_row(
    value: ServicePrincipal,
) -> ServicePrincipalScalars:
    if type(value) is not ServicePrincipal:
        raise _corrupt() from None
    return (
        value.principal_id,
        value.service_code,
        value.workload_identity,
        value.allowed_environment,
        value.credential_rotated_at,
        value.last_used_at,
        value.created_at,
    )


SessionRevocationScalars = tuple[
    SessionRevocationId,
    PrincipalId,
    str,
    str,
    AwareUtcDateTime,
    str,
    PrincipalId,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_iam_session_revocation_from_row(
    *,
    id: SessionRevocationId,
    principal_id: PrincipalId,
    oidc_issuer: str,
    oidc_subject: str,
    revoke_before: AwareUtcDateTime,
    reason: str,
    created_by_principal_id: PrincipalId,
    expires_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> SessionRevocation:
    try:
        return SessionRevocation(
            id=id,
            principal_id=principal_id,
            oidc_issuer=oidc_issuer,
            oidc_subject=oidc_subject,
            revoke_before=revoke_before,
            reason=reason,
            created_by_principal_id=created_by_principal_id,
            expires_at=expires_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_iam_session_revocation_to_row(
    value: SessionRevocation,
) -> SessionRevocationScalars:
    if type(value) is not SessionRevocation:
        raise _corrupt() from None
    return (
        value.id,
        value.principal_id,
        value.oidc_issuer,
        value.oidc_subject,
        value.revoke_before,
        value.reason,
        value.created_by_principal_id,
        value.expires_at,
        value.created_at,
    )


UserAccountScalars = tuple[
    PrincipalId,
    str,
    str,
    EmailAddress | None,
    bool,
    bool,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_iam_user_account_from_row(
    *,
    principal_id: PrincipalId,
    oidc_issuer: str,
    oidc_subject: str,
    email: EmailAddress | None,
    email_verified: bool,
    mfa_required: bool,
    last_login_at: AwareUtcDateTime | None,
    last_mfa_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> UserAccount:
    try:
        return UserAccount(
            principal_id=principal_id,
            oidc_issuer=oidc_issuer,
            oidc_subject=oidc_subject,
            email=email,
            email_verified=email_verified,
            mfa_required=mfa_required,
            last_login_at=last_login_at,
            last_mfa_at=last_mfa_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_iam_user_account_to_row(value: UserAccount) -> UserAccountScalars:
    if type(value) is not UserAccount:
        raise _corrupt() from None
    return (
        value.principal_id,
        value.oidc_issuer,
        value.oidc_subject,
        value.email,
        value.email_verified,
        value.mfa_required,
        value.last_login_at,
        value.last_mfa_at,
        value.created_at,
    )


__all__ = [
    "BreakGlassRecordScalars",
    "PermissionScalars",
    "PrincipalRoleAssignmentRecordScalars",
    "PrincipalStateScalars",
    "RolePermissionBindingScalars",
    "RoleScalars",
    "ServicePrincipalScalars",
    "SessionRevocationScalars",
    "UserAccountScalars",
    "map_iam_break_glass_record_from_row",
    "map_iam_break_glass_record_to_row",
    "map_iam_permission_from_row",
    "map_iam_permission_to_row",
    "map_iam_principal_from_row",
    "map_iam_principal_role_assignment_from_row",
    "map_iam_principal_role_assignment_to_row",
    "map_iam_principal_to_row",
    "map_iam_role_from_row",
    "map_iam_role_permission_from_row",
    "map_iam_role_permission_to_row",
    "map_iam_role_to_row",
    "map_iam_service_principal_from_row",
    "map_iam_service_principal_to_row",
    "map_iam_session_revocation_from_row",
    "map_iam_session_revocation_to_row",
    "map_iam_user_account_from_row",
    "map_iam_user_account_to_row",
]

install_mapper_physical_constraint_guards(globals())
