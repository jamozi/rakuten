"""Nominal IAM persistence identities selected by ST-0308."""

from raos.domain.shared.identity import EntityId


class CreatedByPrincipalId(EntityId):
    __slots__ = ()


class BreakGlassRecordId(EntityId):
    __slots__ = ()


class PermissionId(EntityId):
    __slots__ = ()


class PrincipalId(EntityId):
    __slots__ = ()


class PrincipalRoleAssignmentId(EntityId):
    __slots__ = ()


class RoleId(EntityId):
    __slots__ = ()


class SessionRevocationId(EntityId):
    __slots__ = ()


__all__ = [
    "BreakGlassRecordId",
    "CreatedByPrincipalId",
    "PermissionId",
    "PrincipalId",
    "PrincipalRoleAssignmentId",
    "RoleId",
    "SessionRevocationId",
]
