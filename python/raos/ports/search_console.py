"""Credential-free inward port for one recorded Search Console fixture."""

from __future__ import annotations

from typing import Protocol

from raos.domain.analytics.search_console import (
    RecordedSearchConsolePage,
    SearchConsoleCommand,
)


class RecordedSearchConsoleExchange(Protocol):
    """Exchange one exact command for one bound recorded fixture page."""

    def exchange(self, command: SearchConsoleCommand) -> RecordedSearchConsolePage:
        """Return the single pre-bound page without provider or persistence I/O."""


__all__ = ["RecordedSearchConsoleExchange"]
