"""Recorded and always-disabled provider adapters for ST-0502 V2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    ItemSearchProviderObservationV2,
    ItemSearchRuntimeFailureCode,
    ItemSearchWireRequestV2,
    ProviderFailureClassV2,
    ProviderModeV2,
    ProviderObservationKindV2,
    RateLimitObservationV2,
    fail_item_search_runtime,
)


def _environment(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }:
        fail_item_search_runtime()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class RecordedItemSearchExchangeV2:
    request: ItemSearchWireRequestV2
    ordinal: int
    observation: ItemSearchProviderObservationV2

    def __post_init__(self) -> None:
        if (
            type(self.request) is not ItemSearchWireRequestV2
            or type(self.ordinal) is not int
            or self.ordinal < 1
            or type(self.observation) is not ItemSearchProviderObservationV2
            or self.observation.mode is not ProviderModeV2.RECORDED_SYNTHETIC
            or self.observation.request_fingerprint != self.request.request_fingerprint
            or self.observation.external_actions != 0
        ):
            fail_item_search_runtime()

    def __repr__(self) -> str:
        return "RecordedItemSearchExchangeV2(<redacted-rakuten-item-search-runtime-v2>)"


@final
class RecordedRakutenItemSearchPageProviderV2:
    """Return the next exact synthetic observation for one request fingerprint."""

    __slots__ = ("_counts", "_exchanges", "_lock", "_total_calls")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        exchanges: tuple[RecordedItemSearchExchangeV2, ...],
    ) -> None:
        _environment(environment)
        if (
            type(exchanges) is not tuple
            or not exchanges
            or len(exchanges) > 1000
            or any(
                type(value) is not RecordedItemSearchExchangeV2 for value in exchanges
            )
        ):
            fail_item_search_runtime()
        keys = tuple(
            (value.request.request_fingerprint, value.ordinal) for value in exchanges
        )
        if len(keys) != len(set(keys)):
            fail_item_search_runtime()
        grouped: dict[str, list[int]] = {}
        for fingerprint, ordinal in keys:
            grouped.setdefault(fingerprint, []).append(ordinal)
        if any(
            sorted(ordinals) != list(range(1, len(ordinals) + 1))
            for ordinals in grouped.values()
        ):
            fail_item_search_runtime()
        self._exchanges = exchanges
        self._counts: dict[str, int] = {}
        self._total_calls = 0
        self._lock = RLock()

    @property
    def mode(self) -> ProviderModeV2:
        return ProviderModeV2.RECORDED_SYNTHETIC

    @property
    def external_action_count(self) -> int:
        return 0

    @property
    def call_count(self) -> int:
        with self._lock:
            return self._total_calls

    def fetch_once(
        self,
        request: ItemSearchWireRequestV2,
        *,
        observed_at: datetime,
    ) -> ItemSearchProviderObservationV2:
        if type(request) is not ItemSearchWireRequestV2:
            fail_item_search_runtime()
        with self._lock:
            ordinal = self._counts.get(request.request_fingerprint, 0) + 1
            matches = tuple(
                value
                for value in self._exchanges
                if value.request == request and value.ordinal == ordinal
            )
            if len(matches) != 1:
                fail_item_search_runtime(
                    ItemSearchRuntimeFailureCode.PROVIDER_UNAVAILABLE
                )
            observation = matches[0].observation
            if observation.observed_at != observed_at:
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
            self._counts[request.request_fingerprint] = ordinal
            self._total_calls += 1
            return observation


@final
class DisabledRakutenItemSearchHttpActivationPortV2:
    """Future HTTP activation boundary that is permanently unavailable here.

    The adapter accepts no origin, credential reader, header map, environment
    lookup, request body, or HTTP client.  It performs and records zero
    external actions on every call.
    """

    __slots__ = ()

    def __init__(self, *, environment: RuntimeEnvironment) -> None:
        _environment(environment)

    @property
    def mode(self) -> ProviderModeV2:
        return ProviderModeV2.DISABLED

    @property
    def external_action_count(self) -> int:
        return 0

    def fetch_once(
        self,
        request: ItemSearchWireRequestV2,
        *,
        observed_at: datetime,
    ) -> ItemSearchProviderObservationV2:
        if type(request) is not ItemSearchWireRequestV2:
            fail_item_search_runtime()
        return ItemSearchProviderObservationV2(
            kind=ProviderObservationKindV2.DISABLED,
            mode=ProviderModeV2.DISABLED,
            request_fingerprint=request.request_fingerprint,
            observed_at=observed_at,
            http_status=None,
            request_id="DISABLED:ST0502:HTTP",
            raw_body=None,
            raw_sha256=None,
            rate=RateLimitObservationV2(limit=None, remaining=None, reset_at=None),
            retry_after_at=None,
            failure_class=ProviderFailureClassV2.UNAVAILABLE,
            external_actions=0,
        )


__all__ = [
    "DisabledRakutenItemSearchHttpActivationPortV2",
    "RecordedItemSearchExchangeV2",
    "RecordedRakutenItemSearchPageProviderV2",
]
