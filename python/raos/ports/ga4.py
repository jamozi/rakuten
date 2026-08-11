"""Single credential-free inward port for an exact recorded GA4 fixture."""

from __future__ import annotations

from typing import Protocol

from raos.domain.analytics.ga4 import (
    Ga4RecordedExchange,
    Ga4RecordedRequest,
    Ga4RecordingId,
)


class RecordedGa4ReportPort(Protocol):
    """Read one pre-bound recording without provider or persistence behavior."""

    def read(
        self,
        *,
        recording_id: Ga4RecordingId,
        request: Ga4RecordedRequest,
    ) -> Ga4RecordedExchange:
        """Return one immutable recorded exchange."""

        ...


__all__ = ["RecordedGa4ReportPort"]
