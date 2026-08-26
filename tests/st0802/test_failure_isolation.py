"""Failure isolation and ordered-script hostility for ST-0802."""

from __future__ import annotations

from collections.abc import Callable
import pickle
from typing import cast

import pytest

from raos.adapters.recorded_article_lifecycle import (
    RecordedArticleLifecycleExchange,
    RecordedArticleLifecycleStep,
)
from raos.application.editorial.article_lifecycle import ArticleLifecycleService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.article_lifecycle import (
    ArticleLifecycleFailure,
    ArticleLifecycleFailureCode,
    ArticleLifecycleMode,
    ArticleLifecycleOperation,
    ArticleLifecycleOutcome,
    ArticleState,
    BodySha256,
    CreateVersionRequest,
)

from .support import (
    SITE_ID,
    create_outcome,
    create_request,
    grant_for,
    lifecycle_case,
    service_for,
)


REJECTED_CANARY = "REJECTED_VALUE_CANARY_ST0802_DO_NOT_ECHO"


class _ExchangeProbe:
    def __init__(self, outcome: object) -> None:
        self.calls = 0
        self.error: Exception | None = None
        self.outcome = outcome

    def exchange(self, request: object) -> ArticleLifecycleOutcome:
        del request
        self.calls += 1
        if self.error is not None:
            raise self.error
        return cast(ArticleLifecycleOutcome, self.outcome)


def _service(probe: _ExchangeProbe) -> ArticleLifecycleService:
    return ArticleLifecycleService(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=ArticleLifecycleMode.RECORDED_TEST_ONLY,
        exchange=probe,
    )


def test_exchange_exception_is_sanitized_without_retry_or_context() -> None:
    request = create_request()
    probe = _ExchangeProbe(create_outcome())
    probe.error = RuntimeError(REJECTED_CANARY)

    with pytest.raises(ArticleLifecycleFailure) as caught:
        _service(probe).execute(grant=grant_for(request), request=request)

    assert caught.value.code is ArticleLifecycleFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
    assert probe.calls == 1
    assert REJECTED_CANARY not in f"{caught.value!s} {caught.value!r}"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_malformed_exchange_output_fails_without_partial_result() -> None:
    request = create_request()
    probe = _ExchangeProbe(object())
    with pytest.raises(ArticleLifecycleFailure) as caught:
        _service(probe).execute(grant=grant_for(request), request=request)
    assert caught.value.code is ArticleLifecycleFailureCode.OUTCOME_MISMATCH
    assert probe.calls == 1


@pytest.mark.parametrize(
    "field_value",
    (
        ("site_id", SITE_ID),
        ("state", cast(ArticleState, "PUBLISHED")),
    ),
)
def test_mutated_outcome_fails_closed(field_value: tuple[str, object]) -> None:
    request = create_request()
    outcome = create_outcome()
    field, value = field_value
    if field == "site_id":
        value = type(SITE_ID)("018f3e90-7b00-7000-8000-000000000199")
    object.__setattr__(outcome.article, field, value)
    probe = _ExchangeProbe(outcome)
    with pytest.raises(ArticleLifecycleFailure) as caught:
        _service(probe).execute(grant=grant_for(request), request=request)
    assert caught.value.code is ArticleLifecycleFailureCode.OUTCOME_MISMATCH
    assert probe.calls == 1


def test_mutated_request_ast_hash_is_rejected_before_exchange() -> None:
    request, outcome = lifecycle_case(ArticleLifecycleOperation.CREATE_VERSION)
    assert isinstance(request, CreateVersionRequest)
    object.__setattr__(request.version, "body_sha256", BodySha256("0" * 64))
    probe = _ExchangeProbe(outcome)
    with pytest.raises(ArticleLifecycleFailure):
        _service(probe).execute(grant=grant_for(request), request=request)
    assert probe.calls == 0


def test_order_reorder_and_exhaustion_fail_closed() -> None:
    first_request, first_outcome = lifecycle_case(ArticleLifecycleOperation.GET_ARTICLE)
    second_request, second_outcome = lifecycle_case(
        ArticleLifecycleOperation.GET_VERSION
    )
    adapter = RecordedArticleLifecycleExchange(
        environment=RuntimeEnvironment.CI,
        mode=ArticleLifecycleMode.RECORDED_TEST_ONLY,
        script_capacity=2,
        scripts=(
            RecordedArticleLifecycleStep(first_request, first_outcome),
            RecordedArticleLifecycleStep(second_request, second_outcome),
        ),
    )
    with pytest.raises(ArticleLifecycleFailure):
        adapter.exchange(second_request)
    assert adapter.exchange(first_request) is first_outcome
    assert adapter.exchange(second_request) is second_outcome
    with pytest.raises(ArticleLifecycleFailure):
        adapter.exchange(second_request)


def test_duplicate_script_is_rejected() -> None:
    request, outcome = lifecycle_case(ArticleLifecycleOperation.CREATE_ARTICLE)
    step = RecordedArticleLifecycleStep(request, outcome)
    with pytest.raises(ArticleLifecycleFailure):
        RecordedArticleLifecycleExchange(
            environment=RuntimeEnvironment.ENV_DEV,
            mode=ArticleLifecycleMode.RECORDED_TEST_ONLY,
            script_capacity=2,
            scripts=(step, step),
        )


@pytest.mark.parametrize(
    "value",
    (create_request, create_outcome),
)
def test_sensitive_domain_values_are_not_pickleable(
    value: Callable[[], object],
) -> None:
    built = value()
    assert REJECTED_CANARY not in f"{built!s} {built!r}"
    with pytest.raises(TypeError):
        pickle.dumps(built)


def test_nonlocal_environment_or_mode_is_rejected() -> None:
    request, outcome = lifecycle_case(ArticleLifecycleOperation.GET_ARTICLE)
    _, adapter = service_for(request, outcome)
    with pytest.raises(ArticleLifecycleFailure):
        ArticleLifecycleService(
            environment=RuntimeEnvironment.PRODUCTION,
            mode=ArticleLifecycleMode.RECORDED_TEST_ONLY,
            exchange=adapter,
        )
