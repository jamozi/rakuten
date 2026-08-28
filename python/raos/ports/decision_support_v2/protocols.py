"""Narrow versioned port protocols. No protocol grants a live capability."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Protocol

from raos.domain.decision_support_v2.events import AnalyticsEvent
from raos.domain.decision_support_v2.models import (
    AirlineRuleSet,
    JourneySegment,
    OfferObservation,
    ProductModel,
)
from raos.domain.decision_support_v2.publication import PublicationPackage


class RuleRegistryPort(Protocol):
    def resolve(
        self, segment: JourneySegment, *, at: datetime
    ) -> tuple[AirlineRuleSet, ...]: ...


class ProductCatalogPort(Protocol):
    def get(self, product_id: str) -> ProductModel | None: ...


class RakutenSearchPort(Protocol):
    mode: str

    def search(self, request: Mapping[str, object]) -> tuple[OfferObservation, ...]: ...


class WordPressDraftPort(Protocol):
    mode: str

    def dry_run(self, package: PublicationPackage) -> Mapping[str, object]: ...


class EventCollectorPort(Protocol):
    mode: str

    def collect(self, event: AnalyticsEvent) -> str: ...


__all__ = [
    "EventCollectorPort",
    "ProductCatalogPort",
    "RakutenSearchPort",
    "RuleRegistryPort",
    "WordPressDraftPort",
]
