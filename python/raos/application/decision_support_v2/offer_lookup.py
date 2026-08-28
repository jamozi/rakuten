"""Fail-closed recorded offer lookup with no CTA fabrication."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from raos.adapters.decision_support_v2.errors import AdapterError, AdapterFailure
from raos.domain.decision_support_v2.models import OfferObservation
from raos.ports.decision_support_v2.protocols import RakutenSearchPort


class OfferLookupState(StrEnum):
    RECORDED = "RECORDED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class OfferLookupResult:
    state: OfferLookupState
    offers: tuple[OfferObservation, ...]
    failure: AdapterFailure | None


def lookup_recorded_offers(
    adapter: RakutenSearchPort, request: Mapping[str, object]
) -> OfferLookupResult:
    try:
        offers = adapter.search(request)
    except AdapterError as exc:
        return OfferLookupResult(OfferLookupState.UNKNOWN, (), exc.code)
    return OfferLookupResult(OfferLookupState.RECORDED, offers, None)


__all__ = ["OfferLookupResult", "OfferLookupState", "lookup_recorded_offers"]
