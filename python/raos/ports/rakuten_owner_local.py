"""Narrow ports for the ST-0505 owner-local Rakuten read surface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.catalog.rakuten_owner_local import (
    RakutenOwnerLocalApiDefinition,
    RakutenOwnerLocalCredentials,
    RakutenOwnerLocalProviderResult,
    RakutenOwnerLocalRequest,
    RakutenOwnerLocalResultEnvelope,
)


@runtime_checkable
class RakutenOwnerLocalCredentialReader(Protocol):
    def read(self) -> RakutenOwnerLocalCredentials: ...


@runtime_checkable
class RakutenOwnerLocalTransport(Protocol):
    def execute(
        self,
        definition: RakutenOwnerLocalApiDefinition,
        request: RakutenOwnerLocalRequest,
        credentials: RakutenOwnerLocalCredentials,
    ) -> RakutenOwnerLocalProviderResult: ...


@runtime_checkable
class RakutenOwnerLocalResultWriter(Protocol):
    def preflight(self) -> None: ...

    def write(self, envelope: RakutenOwnerLocalResultEnvelope) -> None: ...


__all__ = [
    "RakutenOwnerLocalCredentialReader",
    "RakutenOwnerLocalResultWriter",
    "RakutenOwnerLocalTransport",
]
