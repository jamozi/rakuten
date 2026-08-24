"""Closed ST-0403 service-principal boundary with no runtime authority."""

from __future__ import annotations

from typing import NoReturn, final

from raos.domain.iam.authorization import (
    ServicePrincipalAuthorizationStatus,
    deny_authorization,
)


@final
class DisabledServicePrincipalAuthorizationAdapter:
    """Deny until an exact service-principal/workload-role map is Canonical."""

    __slots__ = ()

    def status(self) -> ServicePrincipalAuthorizationStatus:
        return ServicePrincipalAuthorizationStatus.DISABLED_MAPPING_UNRESOLVED

    def require_internal_service(self, service_name: object) -> NoReturn:
        del service_name
        deny_authorization()

    def __repr__(self) -> str:
        return (
            "DisabledServicePrincipalAuthorizationAdapter("
            "status='DISABLED_MAPPING_UNRESOLVED')"
        )


__all__ = ["DisabledServicePrincipalAuthorizationAdapter"]
