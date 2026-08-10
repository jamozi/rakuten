"""One-call and sanitized-failure checks for the ST-0502 application seam."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from raos.application.catalog.rakuten_item_search import RakutenItemSearchService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search import (
    CanonicalItemSearchPage,
    ProviderCapabilities,
    ProviderFailure,
    ProviderFailureClass,
    ProviderHealth,
    RakutenItemSearchCommand,
    RakutenItemSearchFailure,
    RakutenItemSearchFailureCode,
    RateLimitMetadata,
    RawItemSearchResponse,
    RawResponseReceipt,
)

from conftest import (
    canonical_page,
    item_search_command,
    raw_response,
    receipt,
    recorded_adapter,
)


REJECTED_CANARY = "REJECTED_VALUE_CANARY_ST0502_DO_NOT_ECHO"


class _ProviderProbe:
    def __init__(self) -> None:
        self.delegate = recorded_adapter()
        self.capability_calls = 0
        self.health_calls = 0
        self.execute_calls = 0
        self.normalize_calls = 0
        self.classify_calls = 0
        self.rate_calls = 0
        self.execute_error: Exception | None = None
        self.normalize_error: Exception | None = None
        self.rate_error: Exception | None = None
        self.raw_override: RawItemSearchResponse | None = None
        self.page_override: CanonicalItemSearchPage | None = None
        self.capabilities_override: ProviderCapabilities | None = None
        self.classification_override: ProviderFailure | None = None

    def capabilities(self) -> ProviderCapabilities:
        self.capability_calls += 1
        return (
            self.delegate.capabilities()
            if self.capabilities_override is None
            else self.capabilities_override
        )

    def health(self) -> ProviderHealth:
        self.health_calls += 1
        return self.delegate.health()

    def execute(self, command: RakutenItemSearchCommand) -> RawItemSearchResponse:
        self.execute_calls += 1
        if self.execute_error is not None:
            raise self.execute_error
        return (
            self.delegate.execute(command)
            if self.raw_override is None
            else self.raw_override
        )

    def normalize(self, response: RawItemSearchResponse) -> CanonicalItemSearchPage:
        self.normalize_calls += 1
        if self.normalize_error is not None:
            raise self.normalize_error
        return (
            self.delegate.normalize(response)
            if self.page_override is None
            else self.page_override
        )

    def classify(self, error: Exception) -> ProviderFailure:
        self.classify_calls += 1
        return (
            self.delegate.classify(error)
            if self.classification_override is None
            else self.classification_override
        )

    def rate(self, response: RawItemSearchResponse) -> RateLimitMetadata:
        self.rate_calls += 1
        if self.rate_error is not None:
            raise self.rate_error
        return self.delegate.rate(response)


class _RecorderProbe:
    def __init__(self) -> None:
        self.calls = 0
        self.error: Exception | None = None
        self.override: RawResponseReceipt | None = None

    def record(self, response: RawItemSearchResponse) -> RawResponseReceipt:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return receipt() if self.override is None else self.override


def _service(
    provider: _ProviderProbe, recorder: _RecorderProbe
) -> RakutenItemSearchService:
    return RakutenItemSearchService(
        environment=RuntimeEnvironment.ENV_DEV,
        provider=provider,
        recorder=recorder,
    )


def test_success_calls_each_required_capability_once_and_never_health() -> None:
    provider = _ProviderProbe()
    recorder = _RecorderProbe()
    result = _service(provider, recorder).search(item_search_command())
    assert result.page.page == 1
    assert (
        provider.capability_calls,
        provider.execute_calls,
        recorder.calls,
        provider.normalize_calls,
        provider.rate_calls,
        provider.classify_calls,
        provider.health_calls,
    ) == (1, 1, 1, 1, 1, 0, 0)


@pytest.mark.parametrize(
    "failure_class",
    (ProviderFailureClass.TRANSIENT, ProviderFailureClass.PERMANENT),
)
def test_provider_failure_is_classified_once_without_retry_or_echo(
    failure_class: ProviderFailureClass,
) -> None:
    provider = _ProviderProbe()
    recorder = _RecorderProbe()
    provider.execute_error = RuntimeError(REJECTED_CANARY)
    provider.classification_override = ProviderFailure(
        failure_class=failure_class,
        code="TEST_ONLY_PROVIDER_FAILURE",
    )
    with pytest.raises(RakutenItemSearchFailure) as caught:
        _service(provider, recorder).search(item_search_command())
    assert caught.value.code is RakutenItemSearchFailureCode.PROVIDER_UNAVAILABLE
    assert provider.execute_calls == 1
    assert provider.classify_calls == 1
    assert recorder.calls == provider.normalize_calls == provider.rate_calls == 0
    assert REJECTED_CANARY not in f"{caught.value!s} {caught.value!r}"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_recorder_failure_stops_before_normalization_and_rate() -> None:
    provider = _ProviderProbe()
    recorder = _RecorderProbe()
    recorder.error = RuntimeError(REJECTED_CANARY)
    with pytest.raises(RakutenItemSearchFailure) as caught:
        _service(provider, recorder).search(item_search_command())
    assert caught.value.code is RakutenItemSearchFailureCode.RECORDING_UNAVAILABLE
    assert recorder.calls == 1
    assert provider.normalize_calls == provider.rate_calls == 0


def test_normalization_failure_stops_before_rate() -> None:
    provider = _ProviderProbe()
    recorder = _RecorderProbe()
    provider.normalize_error = RuntimeError(REJECTED_CANARY)
    with pytest.raises(RakutenItemSearchFailure) as caught:
        _service(provider, recorder).search(item_search_command())
    assert caught.value.code is RakutenItemSearchFailureCode.NORMALIZATION_UNAVAILABLE
    assert recorder.calls == provider.normalize_calls == 1
    assert provider.rate_calls == 0


def test_rate_failure_never_returns_a_partial_page() -> None:
    provider = _ProviderProbe()
    recorder = _RecorderProbe()
    provider.rate_error = RuntimeError(REJECTED_CANARY)
    with pytest.raises(RakutenItemSearchFailure) as caught:
        _service(provider, recorder).search(item_search_command())
    assert caught.value.code is RakutenItemSearchFailureCode.PROVIDER_UNAVAILABLE
    assert provider.execute_calls == recorder.calls == provider.normalize_calls == 1
    assert provider.rate_calls == 1


def test_raw_request_binding_drift_stops_before_recording() -> None:
    provider = _ProviderProbe()
    recorder = _RecorderProbe()
    provider.raw_override = raw_response(request_fingerprint="0" * 64)
    with pytest.raises(RakutenItemSearchFailure) as caught:
        _service(provider, recorder).search(item_search_command())
    assert caught.value.code is RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID
    assert recorder.calls == 0


def test_receipt_hash_drift_stops_before_normalization() -> None:
    provider = _ProviderProbe()
    recorder = _RecorderProbe()
    recorder.override = replace(receipt(), sha256="1" * 64)
    with pytest.raises(RakutenItemSearchFailure) as caught:
        _service(provider, recorder).search(item_search_command())
    assert caught.value.code is RakutenItemSearchFailureCode.OUTCOME_MISMATCH
    assert provider.normalize_calls == 0


def test_canonical_page_binding_drift_is_rejected() -> None:
    provider = _ProviderProbe()
    recorder = _RecorderProbe()
    drifted = canonical_page()
    object.__setattr__(drifted, "request_sha256", "2" * 64)
    provider.page_override = drifted
    with pytest.raises(RakutenItemSearchFailure) as caught:
        _service(provider, recorder).search(item_search_command())
    assert caught.value.code is RakutenItemSearchFailureCode.OUTCOME_MISMATCH


def test_malformed_classifier_output_remains_sanitized() -> None:
    provider = _ProviderProbe()
    recorder = _RecorderProbe()
    provider.execute_error = RuntimeError(REJECTED_CANARY)
    provider.classification_override = cast(ProviderFailure, object())
    with pytest.raises(RakutenItemSearchFailure) as caught:
        _service(provider, recorder).search(item_search_command())
    assert caught.value.code is RakutenItemSearchFailureCode.PROVIDER_UNAVAILABLE
    assert REJECTED_CANARY not in str(caught.value)
