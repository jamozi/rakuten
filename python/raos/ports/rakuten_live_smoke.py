"""Narrow inward and outward ports for the ST-0505 live smoke."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.catalog.rakuten_item_search_live_request_v1 import (
    RakutenItemSearchLiveRequestV1,
)
from raos.domain.catalog.rakuten_live_smoke import (
    RakutenLiveSmokeCredentials,
    RakutenLiveSmokeHttpResponse,
    RakutenLiveSmokeReport,
)


@runtime_checkable
class RakutenLiveSmokeCredentialReader(Protocol):
    """Read the one fixed owner-private credential record."""

    def read(self) -> RakutenLiveSmokeCredentials: ...


@runtime_checkable
class RakutenLiveSmokeTransport(Protocol):
    """Perform exactly one fixed direct Item Search request."""

    def execute(
        self,
        policy: RakutenItemSearchLiveRequestV1,
        credentials: RakutenLiveSmokeCredentials,
    ) -> RakutenLiveSmokeHttpResponse: ...


@runtime_checkable
class RakutenLiveSmokeReportWriter(Protocol):
    """Persist only a sanitized ST-0505 report."""

    def doctor_ready(self) -> None: ...

    def preflight(self) -> None: ...

    def write(self, report: RakutenLiveSmokeReport) -> None: ...


__all__ = [
    "RakutenLiveSmokeCredentialReader",
    "RakutenLiveSmokeReportWriter",
    "RakutenLiveSmokeTransport",
]
