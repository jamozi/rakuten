"""Provider-neutral, local-only ports for the ST-0904 V2 projector."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.publishing.public_projection_v2 import (
    PublicProjectionInputV2,
    PublicProjectionRequestV2,
    PublicProjectionResultV2,
)


@runtime_checkable
class RecordedPublicProjectionSource(Protocol):
    """Return one exact immutable ST-0903 projection input."""

    def load(self, request: PublicProjectionRequestV2) -> PublicProjectionInputV2: ...


@runtime_checkable
class PublicProjectionExchange(Protocol):
    """Build one process-local projection without persistence or transport."""

    def exchange(
        self,
        request: PublicProjectionRequestV2,
        source: PublicProjectionInputV2,
    ) -> PublicProjectionResultV2: ...


__all__ = ("PublicProjectionExchange", "RecordedPublicProjectionSource")
