"""Closed physical enums for the ST-0308 IAM persistence slice."""

from enum import Enum


class PermissionRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PermissionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class PrincipalPrincipalType(str, Enum):
    USER = "USER"
    SERVICE = "SERVICE"


class PrincipalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEACTIVATED = "DEACTIVATED"


class PrincipalRoleAssignmentScopeType(str, Enum):
    GLOBAL = "GLOBAL"
    SITE = "SITE"
    CATEGORY = "CATEGORY"
    ARTICLE = "ARTICLE"


class RoleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class ServicePrincipalAllowedEnvironment(str, Enum):
    LOCAL = "LOCAL"
    CI = "CI"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


__all__ = [
    "PermissionRiskLevel",
    "PermissionStatus",
    "PrincipalPrincipalType",
    "PrincipalStatus",
    "PrincipalRoleAssignmentScopeType",
    "RoleStatus",
    "ServicePrincipalAllowedEnvironment",
]
