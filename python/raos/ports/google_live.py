"""Outward ports for read-only Google analytics imports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from raos.domain.analytics.google_live import (
    AnalyticsSiteBinding,
    Ga4ImportBatch,
    Ga4LiveQuery,
    Ga4PropertyConfigSnapshot,
    GoogleImportCommitResult,
    GoogleImportExecutionContext,
    SearchConsoleImportBatch,
    SearchConsoleLiveQuery,
)


@dataclass(frozen=True, slots=True, repr=False)
class GoogleJsonResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    document: object


@runtime_checkable
class GoogleAuthorizedJsonTransport(Protocol):
    """Issue one authorized JSON request to an allowlisted Google origin."""

    def request(
        self,
        *,
        method: str,
        url: str,
        body: Mapping[str, object] | None,
    ) -> GoogleJsonResponse: ...


@runtime_checkable
class SearchConsoleProviderPort(Protocol):
    def query(self, query: SearchConsoleLiveQuery) -> SearchConsoleImportBatch: ...


@runtime_checkable
class Ga4DataProviderPort(Protocol):
    def run_report(
        self,
        query: Ga4LiveQuery,
        *,
        configuration: Ga4PropertyConfigSnapshot,
    ) -> Ga4ImportBatch: ...


@runtime_checkable
class Ga4AdminProviderPort(Protocol):
    def get_property_configuration(
        self,
        *,
        property_id: str,
        retrieved_at: datetime,
    ) -> Ga4PropertyConfigSnapshot: ...


@runtime_checkable
class AnalyticsSiteBindingPort(Protocol):
    def gsc(self) -> AnalyticsSiteBinding: ...

    def ga4(self) -> AnalyticsSiteBinding: ...


@runtime_checkable
class AnalyticsImportRepository(Protocol):
    """Atomic append/supersession boundary for normalized provider batches."""

    def commit_gsc(
        self,
        *,
        context: GoogleImportExecutionContext,
        batch: SearchConsoleImportBatch,
    ) -> GoogleImportCommitResult: ...

    def commit_ga4(
        self,
        *,
        context: GoogleImportExecutionContext,
        batch: Ga4ImportBatch,
    ) -> GoogleImportCommitResult: ...


@runtime_checkable
class GoogleImportClock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class GoogleRetrySleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


__all__ = [
    "AnalyticsImportRepository",
    "AnalyticsSiteBindingPort",
    "Ga4AdminProviderPort",
    "Ga4DataProviderPort",
    "GoogleAuthorizedJsonTransport",
    "GoogleImportClock",
    "GoogleJsonResponse",
    "GoogleRetrySleeper",
    "SearchConsoleProviderPort",
]
