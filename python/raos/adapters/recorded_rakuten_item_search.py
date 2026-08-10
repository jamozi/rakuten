"""Immutable synthetic recorded ITEM_SEARCH adapter for ST-0502."""

from __future__ import annotations

from dataclasses import dataclass
from typing import final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search import (
    CanonicalItemSearchPage,
    ItemSearchOperation,
    ProviderCapabilities,
    ProviderFailure,
    ProviderFailureClass,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderMode,
    RakutenItemSearchCommand,
    RakutenItemSearchFailure,
    RakutenItemSearchFailureCode,
    RateLimitMetadata,
    RawItemSearchResponse,
    RawResponseReceipt,
    fail_item_search,
)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedItemSearchFixture:
    command: RakutenItemSearchCommand
    response: RawItemSearchResponse
    receipt: RawResponseReceipt
    page: CanonicalItemSearchPage

    def __post_init__(self) -> None:
        if (
            type(self.command) is not RakutenItemSearchCommand
            or type(self.response) is not RawItemSearchResponse
            or type(self.receipt) is not RawResponseReceipt
            or type(self.page) is not CanonicalItemSearchPage
            or self.command.request.page != 1
            or self.response.request_fingerprint != self.command.request.fingerprint
            or self.response.body_sha256 != self.receipt.sha256
            or self.response.body_size != self.receipt.byte_size
            or self.page.request_sha256 != self.command.request.fingerprint
            or self.page.raw_artifact != self.receipt
            or self.page.observed_at != self.response.received_at
        ):
            fail_item_search()

    def __repr__(self) -> str:
        return "RecordedItemSearchFixture(<redacted-rakuten-item-search>)"


@final
class RecordedRakutenItemSearchAdapter:
    """Pure lookup over an immutable, exact, duplicate-free fixture tuple."""

    __slots__ = ("_fixtures",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        fixture_capacity: int,
        fixtures: tuple[RecordedItemSearchFixture, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(fixture_capacity) is not int
            or not 0 < fixture_capacity <= 10_000
            or type(fixtures) is not tuple
            or not fixtures
            or len(fixtures) > fixture_capacity
            or any(
                type(fixture) is not RecordedItemSearchFixture for fixture in fixtures
            )
            or len({fixture.command.fingerprint for fixture in fixtures})
            != len(fixtures)
            or len({fixture.response.body_sha256 for fixture in fixtures})
            != len(fixtures)
        ):
            fail_item_search()
        self._fixtures = fixtures

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="RAKUTEN_ICHIBA",
            mode=ProviderMode.RECORDED_TEST_ONLY,
            operations=(ItemSearchOperation.ITEM_SEARCH,),
            live_eligible=False,
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(status=ProviderHealthStatus.NOT_EXECUTED)

    def _by_command(
        self, command: RakutenItemSearchCommand
    ) -> RecordedItemSearchFixture:
        if type(command) is not RakutenItemSearchCommand:
            fail_item_search()
        matches = tuple(
            fixture for fixture in self._fixtures if fixture.command == command
        )
        if len(matches) != 1:
            fail_item_search(RakutenItemSearchFailureCode.PROVIDER_UNAVAILABLE)
        return matches[0]

    def _by_response(
        self, response: RawItemSearchResponse
    ) -> RecordedItemSearchFixture:
        if type(response) is not RawItemSearchResponse:
            fail_item_search()
        matches = tuple(
            fixture
            for fixture in self._fixtures
            if fixture.response is response
            and fixture.response.body_sha256 == response.body_sha256
            and fixture.response.request_fingerprint == response.request_fingerprint
        )
        if len(matches) != 1:
            fail_item_search(RakutenItemSearchFailureCode.PROVIDER_UNAVAILABLE)
        return matches[0]

    def execute(self, command: RakutenItemSearchCommand) -> RawItemSearchResponse:
        return self._by_command(command).response

    def normalize(self, response: RawItemSearchResponse) -> CanonicalItemSearchPage:
        return self._by_response(response).page

    def classify(self, error: Exception) -> ProviderFailure:
        if type(error) is RakutenItemSearchFailure:
            failure_class = ProviderFailureClass.UNAVAILABLE
        else:
            failure_class = ProviderFailureClass.PERMANENT
        return ProviderFailure(
            failure_class=failure_class, code="RECORDED_PROVIDER_FAILURE"
        )

    def rate(self, response: RawItemSearchResponse) -> RateLimitMetadata:
        return self._by_response(response).response.rate

    def record(self, response: RawItemSearchResponse) -> RawResponseReceipt:
        fixture = self._by_response(response)
        if (
            fixture.receipt.sha256 != response.body_sha256
            or fixture.receipt.byte_size != response.body_size
        ):
            fail_item_search(RakutenItemSearchFailureCode.RECORDING_UNAVAILABLE)
        return fixture.receipt


__all__ = ["RecordedItemSearchFixture", "RecordedRakutenItemSearchAdapter"]
