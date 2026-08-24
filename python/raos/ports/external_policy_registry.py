"""Read-only inward exchange for the ST-1407 recorded registry."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ops.external_policy_registry import (
    ExternalPolicyRegistryReport,
    ExternalPolicyRegistryRequest,
)


@runtime_checkable
class ExternalPolicyRegistryExchange(Protocol):
    def evaluate(
        self,
        request: ExternalPolicyRegistryRequest,
    ) -> ExternalPolicyRegistryReport: ...


__all__ = ["ExternalPolicyRegistryExchange"]
