"""Fail-closed one-page recorded-only Rakuten item-search service."""

from __future__ import annotations

from typing import final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search import (
    CanonicalItemSearchPage,
    ItemSearchOperation,
    PersistenceExecutionStatus,
    ProviderCapabilities,
    ProviderFailure,
    ProviderMode,
    RakutenItemSearchCommand,
    RakutenItemSearchFailureCode,
    RakutenItemSearchResult,
    RateLimitMetadata,
    RawItemSearchResponse,
    RawResponseReceipt,
    StorageExecutionStatus,
    fail_item_search,
)
from raos.ports.rakuten_item_search import (
    RakutenItemSearchProvider,
    RawResponseRecorder,
)


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


@final
class RakutenItemSearchService:
    """Execute exactly one fixture exchange and never retry or paginate."""

    __slots__ = ("_provider", "_recorder")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        provider: RakutenItemSearchProvider,
        recorder: RawResponseRecorder,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(provider, RakutenItemSearchProvider)
            or not _implements(recorder, RawResponseRecorder)
        ):
            fail_item_search()
        self._provider = provider
        self._recorder = recorder

    def search(self, command: RakutenItemSearchCommand) -> RakutenItemSearchResult:
        if type(command) is not RakutenItemSearchCommand or command.request.page != 1:
            fail_item_search()
        capabilities: object = None
        capability_failed = False
        try:
            capabilities = self._provider.capabilities()
        except Exception:
            capability_failed = True
        if capability_failed or type(capabilities) is not ProviderCapabilities:
            fail_item_search(RakutenItemSearchFailureCode.PROVIDER_UNAVAILABLE)
        if (
            capabilities.provider != "RAKUTEN_ICHIBA"
            or capabilities.mode is not ProviderMode.RECORDED_TEST_ONLY
            or capabilities.operations != (ItemSearchOperation.ITEM_SEARCH,)
            or capabilities.live_eligible
        ):
            fail_item_search(RakutenItemSearchFailureCode.OUTCOME_MISMATCH)

        raw: object = None
        provider_error: Exception | None = None
        try:
            raw = self._provider.execute(command)
        except Exception as error:
            provider_error = error
        if provider_error is not None:
            classification: object = None
            classification_failed = False
            try:
                classification = self._provider.classify(provider_error)
            except Exception:
                classification_failed = True
            if classification_failed or type(classification) is not ProviderFailure:
                fail_item_search(RakutenItemSearchFailureCode.PROVIDER_UNAVAILABLE)
            if classification.retryable != classification.failure_class.retryable:
                fail_item_search(RakutenItemSearchFailureCode.OUTCOME_MISMATCH)
            fail_item_search(RakutenItemSearchFailureCode.PROVIDER_UNAVAILABLE)
        if (
            type(raw) is not RawItemSearchResponse
            or raw.provider != "RAKUTEN_ICHIBA"
            or raw.api is not ItemSearchOperation.ITEM_SEARCH
            or raw.request_fingerprint != command.request.fingerprint
            or raw.http_status != 200
        ):
            fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)

        receipt: object = None
        record_failed = False
        try:
            receipt = self._recorder.record(raw)
        except Exception:
            record_failed = True
        if record_failed:
            fail_item_search(RakutenItemSearchFailureCode.RECORDING_UNAVAILABLE)
        if (
            type(receipt) is not RawResponseReceipt
            or receipt.sha256 != raw.body_sha256
            or receipt.byte_size != raw.body_size
            or receipt.uri is not None
            or receipt.storage_status is not StorageExecutionStatus.NOT_EXECUTED
        ):
            fail_item_search(RakutenItemSearchFailureCode.OUTCOME_MISMATCH)

        page: object = None
        normalization_failed = False
        try:
            page = self._provider.normalize(raw)
        except Exception:
            normalization_failed = True
        if normalization_failed or type(page) is not CanonicalItemSearchPage:
            fail_item_search(RakutenItemSearchFailureCode.NORMALIZATION_UNAVAILABLE)

        rate: object = None
        rate_failed = False
        try:
            rate = self._provider.rate(raw)
        except Exception:
            rate_failed = True
        if rate_failed or type(rate) is not RateLimitMetadata:
            fail_item_search(RakutenItemSearchFailureCode.PROVIDER_UNAVAILABLE)
        if (
            page.provider != raw.provider
            or page.api_version != command.request.api_version
            or page.request_sha256 != command.request.fingerprint
            or page.raw_artifact != receipt
            or page.observed_at != raw.received_at
            or page.page != 1
            or page.hits != command.request.hits
            or rate != raw.rate
            or page.provider_rate_limit != rate
        ):
            fail_item_search(RakutenItemSearchFailureCode.OUTCOME_MISMATCH)
        return RakutenItemSearchResult(
            provider_mode=ProviderMode.RECORDED_TEST_ONLY,
            page=page,
            rate=rate,
            storage_status=StorageExecutionStatus.NOT_EXECUTED,
            persistence_status=PersistenceExecutionStatus.NOT_EXECUTED,
            live_eligible=False,
        )


__all__ = ["RakutenItemSearchService"]
