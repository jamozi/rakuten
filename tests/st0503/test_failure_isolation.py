"""Collaborator and recorded-fixture failure isolation for ST-0503."""

from __future__ import annotations

from dataclasses import replace
import pickle
from typing import cast

import pytest

from raos.adapters.recorded_catalog_normalization import (
    RecordedCatalogNormalizationAdapter,
    RecordedCatalogNormalizationFixture,
)
from raos.application.catalog.catalog_normalization import (
    CatalogNormalizationService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.catalog_normalization import (
    CatalogNormalizationBatch,
    CatalogNormalizationCommand,
    CatalogNormalizationFailure,
    CatalogNormalizationFailureCode,
)

from conftest import (
    SECOND_INGESTION_ID,
    expected_batch,
    normalization_command,
    recorded_adapter,
)


class _CountingExchange:
    def __init__(self, outcome: object) -> None:
        self.calls = 0
        self.outcome = outcome

    def normalize(
        self, command: CatalogNormalizationCommand
    ) -> CatalogNormalizationBatch:
        del command
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return cast(CatalogNormalizationBatch, self.outcome)


def _service(exchange: object) -> CatalogNormalizationService:
    return CatalogNormalizationService(
        environment=RuntimeEnvironment.ENV_DEV,
        exchange=cast(_CountingExchange, exchange),
    )


def test_service_calls_exchange_exactly_once_on_success() -> None:
    exchange = _CountingExchange(expected_batch())
    assert _service(exchange).normalize(normalization_command()) == expected_batch()
    assert exchange.calls == 1


def test_collaborator_exception_is_sanitized_without_echo_or_context() -> None:
    canary = "secret-canary-untrusted-normalizer-error"
    exchange = _CountingExchange(RuntimeError(canary))
    with pytest.raises(CatalogNormalizationFailure) as caught:
        _service(exchange).normalize(normalization_command())
    assert exchange.calls == 1
    assert caught.value.code is CatalogNormalizationFailureCode.NORMALIZER_UNAVAILABLE
    assert canary not in str(caught.value)
    assert canary not in repr(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_malformed_collaborator_outcome_is_rejected_without_partial_result() -> None:
    exchange = _CountingExchange(object())
    with pytest.raises(CatalogNormalizationFailure) as caught:
        _service(exchange).normalize(normalization_command())
    assert exchange.calls == 1
    assert caught.value.code is CatalogNormalizationFailureCode.OUTCOME_MISMATCH


@pytest.mark.parametrize(
    "outcome",
    (
        lambda: replace(expected_batch(), command_fingerprint="0" * 64),
        lambda: replace(
            expected_batch(),
            candidates=tuple(
                [
                    replace(
                        expected_batch().candidates[0],
                        display_name="Different inert name",
                        normalized_name="Different inert name",
                    ),
                    expected_batch().candidates[1],
                ]
            ),
        ),
        lambda: replace(
            expected_batch(),
            offers=(
                replace(
                    expected_batch().offers[0],
                    item_url="https://example.invalid/drifted-item",
                ),
                expected_batch().offers[1],
            ),
        ),
        lambda: replace(
            expected_batch(),
            prices=(
                replace(expected_batch().prices[0], amount_jpy=9999),
                expected_batch().prices[1],
            ),
        ),
        lambda: replace(
            expected_batch(),
            availabilities=(
                replace(expected_batch().availabilities[0], provider_value=False),
                expected_batch().availabilities[1],
            ),
        ),
        lambda: replace(
            expected_batch(),
            review_aggregates=(
                replace(expected_batch().review_aggregates[0], review_count=4),
                expected_batch().review_aggregates[1],
            ),
        ),
    ),
)
def test_valid_but_drifted_outcome_is_rejected(outcome: object) -> None:
    exchange = _CountingExchange(outcome())  # type: ignore[operator]
    with pytest.raises(CatalogNormalizationFailure) as caught:
        _service(exchange).normalize(normalization_command())
    assert exchange.calls == 1
    assert caught.value.code is CatalogNormalizationFailureCode.OUTCOME_MISMATCH


@pytest.mark.parametrize(
    "environment",
    (
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ),
)
def test_service_and_adapter_reject_non_dev_ci_environments(
    environment: RuntimeEnvironment,
) -> None:
    with pytest.raises(CatalogNormalizationFailure):
        CatalogNormalizationService(
            environment=environment, exchange=recorded_adapter()
        )
    fixture = RecordedCatalogNormalizationFixture(
        command=normalization_command(),
        batch=expected_batch(),
    )
    with pytest.raises(CatalogNormalizationFailure):
        RecordedCatalogNormalizationAdapter(
            environment=environment,
            fixture_capacity=1,
            fixtures=(fixture,),
        )


@pytest.mark.parametrize("capacity", (True, 0, -1, 10_001, 1.0, "1"))
def test_adapter_rejects_invalid_exact_capacity(capacity: object) -> None:
    fixture = RecordedCatalogNormalizationFixture(
        command=normalization_command(),
        batch=expected_batch(),
    )
    with pytest.raises(CatalogNormalizationFailure):
        RecordedCatalogNormalizationAdapter(
            environment=RuntimeEnvironment.CI,
            fixture_capacity=cast(int, capacity),
            fixtures=(fixture,),
        )


def test_adapter_rejects_duplicate_command_fingerprints() -> None:
    fixture = RecordedCatalogNormalizationFixture(
        command=normalization_command(),
        batch=expected_batch(),
    )
    with pytest.raises(CatalogNormalizationFailure):
        RecordedCatalogNormalizationAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            fixture_capacity=2,
            fixtures=(fixture, fixture),
        )


def test_adapter_rejects_exhausted_exact_lookup_without_fallback() -> None:
    with pytest.raises(CatalogNormalizationFailure) as caught:
        recorded_adapter().normalize(
            normalization_command(ingestion_request_id=SECOND_INGESTION_ID)
        )
    assert caught.value.code is CatalogNormalizationFailureCode.NORMALIZER_UNAVAILABLE


def test_fixture_rejects_batch_from_a_different_command() -> None:
    other_command = normalization_command(ingestion_request_id=SECOND_INGESTION_ID)
    with pytest.raises(CatalogNormalizationFailure):
        RecordedCatalogNormalizationFixture(
            command=other_command,
            batch=expected_batch(),
        )


def test_failure_and_fixture_do_not_pickle_or_echo_source_text() -> None:
    fixture = RecordedCatalogNormalizationFixture(
        command=normalization_command(),
        batch=expected_batch(),
    )
    assert "Model X" not in repr(fixture)
    failure = CatalogNormalizationFailure(
        CatalogNormalizationFailureCode.NORMALIZER_UNAVAILABLE
    )
    with pytest.raises(TypeError):
        pickle.dumps(failure)
