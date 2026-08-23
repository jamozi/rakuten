"""Aggregate-specific inward IAM repository protocols for ST-0308."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.iam.aggregates import (
    BreakGlassRecord,
    Permission,
    Principal,
    PrincipalRoleAssignment,
    Role,
    SessionRevocation,
)
from raos.domain.iam.ids import (
    BreakGlassRecordId,
    PermissionId,
    PrincipalId,
    PrincipalRoleAssignmentId,
    RoleId,
    SessionRevocationId,
)
from raos.domain.shared.persistence import AggregateVersion, PersistedVersion


@runtime_checkable
class PrincipalRepository(Protocol):
    def get(self, principal_id: PrincipalId) -> Principal | None: ...
    def add(self, principal: Principal) -> PersistedVersion: ...
    def save(
        self, principal: Principal, expected_version: AggregateVersion
    ) -> PersistedVersion: ...


@runtime_checkable
class RoleCatalogRepository(Protocol):
    def get_role(self, role_id: RoleId) -> Role | None: ...
    def get_role_by_code(self, role_code: str) -> Role | None: ...
    def get_permission(self, permission_id: PermissionId) -> Permission | None: ...
    def get_permission_by_code(self, permission_code: str) -> Permission | None: ...
    def list_permissions_for_role(self, role_id: RoleId) -> tuple[Permission, ...]: ...


@runtime_checkable
class PrincipalRoleAssignmentRepository(Protocol):
    def get(
        self, assignment_id: PrincipalRoleAssignmentId
    ) -> PrincipalRoleAssignment | None: ...
    def append(self, assignment: PrincipalRoleAssignment) -> None: ...
    def revoke(
        self,
        assignment_id: PrincipalRoleAssignmentId,
        revocation: PrincipalRoleAssignment,
        expected_state: str,
    ) -> PrincipalRoleAssignment: ...


@runtime_checkable
class SessionRevocationRepository(Protocol):
    def get(self, revocation_id: SessionRevocationId) -> SessionRevocation | None: ...
    def append(self, revocation: SessionRevocation) -> None: ...


@runtime_checkable
class BreakGlassRecordRepository(Protocol):
    def get(self, record_id: BreakGlassRecordId) -> BreakGlassRecord | None: ...
    def append(self, record: BreakGlassRecord) -> None: ...


__all__ = [
    "BreakGlassRecordRepository",
    "PrincipalRepository",
    "PrincipalRoleAssignmentRepository",
    "RoleCatalogRepository",
    "SessionRevocationRepository",
]
