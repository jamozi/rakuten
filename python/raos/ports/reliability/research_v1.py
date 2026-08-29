"""Narrow ports for the reliability-first product research context V1."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.reliability.contracts_v1 import (
    ArtifactRefV1,
    ProviderPageV1,
    ReviewThemeSetV1,
    SocialSignalSetV1,
    StrictContractV1,
)


@runtime_checkable
class ProductSearchPortV1(Protocol):
    """Read one bounded page from a pre-authorized product search source."""

    def fetch_page(
        self,
        *,
        source_id: str,
        query_index: int,
        query: str,
        page: int,
    ) -> ProviderPageV1: ...


@runtime_checkable
class ReviewThemePortV1(Protocol):
    """Return derived metadata only; review body text is not representable."""

    def derive_themes(self, *, product_id: str) -> ReviewThemeSetV1: ...


@runtime_checkable
class SocialSignalPortV1(Protocol):
    """Resolve discovery-only social WATCH signals with zero rank adjustment."""

    def discover(self) -> SocialSignalSetV1: ...


@runtime_checkable
class ResearchArtifactStoreV1(Protocol):
    """Persist canonical bytes and return an ObjectArtifact-compatible ref."""

    def put(self, artifact: StrictContractV1) -> ArtifactRefV1: ...

    def get(self, reference: ArtifactRefV1) -> bytes: ...


__all__ = [
    "ProductSearchPortV1",
    "ResearchArtifactStoreV1",
    "ReviewThemePortV1",
    "SocialSignalPortV1",
]
