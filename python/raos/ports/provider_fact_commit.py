"""Provider-neutral inward ports for the ST-1302 recorded commit seam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.finance.provider_fact_commit import (
    ProviderFactCommitRequest,
    ProviderFactCommitResult,
    RecordedProviderFactCommitAuthorization,
    RecordedRevenueDryRunBundle,
)


@runtime_checkable
class RecordedProviderFactCommitAuthorizationSource(Protocol):
    def authorize(
        self,
        request: ProviderFactCommitRequest,
        bundle: RecordedRevenueDryRunBundle,
    ) -> RecordedProviderFactCommitAuthorization: ...


@runtime_checkable
class ProviderFactCommitStore(Protocol):
    def commit(
        self,
        request: ProviderFactCommitRequest,
        bundle: RecordedRevenueDryRunBundle,
        authorization: RecordedProviderFactCommitAuthorization,
    ) -> ProviderFactCommitResult: ...


__all__ = (
    "ProviderFactCommitStore",
    "RecordedProviderFactCommitAuthorizationSource",
)
