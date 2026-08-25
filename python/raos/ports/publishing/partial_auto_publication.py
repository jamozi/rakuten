"""Provider-neutral inward evidence port for Canonical ST-1903."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.publishing.partial_auto_publication import (
    PartialAutoPublicationCommand,
    RecordedPartialAutoPublicationBundle,
)


@runtime_checkable
class PartialAutoPublicationEvidenceSource(Protocol):
    """Consume one command-bound, caller-owned synthetic recording once."""

    def read(
        self, command: PartialAutoPublicationCommand
    ) -> RecordedPartialAutoPublicationBundle: ...


__all__ = ("PartialAutoPublicationEvidenceSource",)
