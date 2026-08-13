"""Deterministic create/replay/update behavior for the local draft adapter."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

import pytest

from raos.adapters.recorded_wordpress_draft import RecordedWordPressDraftAdapter
from raos.application.editorial.market_learning_pilot import (
    MarketLearningPilotService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search import RakutenItemSearchResult
from raos.domain.editorial.market_learning_pilot import (
    DraftDisposition,
    DraftOperation,
    MarketLearningPilotFailure,
    MarketLearningPilotFailureCode,
    PilotEconomics,
    WordPressDraftIntent,
)
from raos.domain.editorial.policy_engine import PolicyEvaluationResult


ARTICLE_VERSION_ID = "ARTICLE-VERSION-1703"


def _intent(
    *,
    operation: DraftOperation = DraftOperation.CREATE_DRAFT,
    content: str = "<p>First local content.</p>",
    existing_draft_id: int | None = None,
) -> WordPressDraftIntent:
    return WordPressDraftIntent(
        operation=operation,
        article_version_id=ARTICLE_VERSION_ID,
        title="Synthetic market-learning article",
        content=content,
        existing_draft_id=existing_draft_id,
    )


def _service(
    adapter: RecordedWordPressDraftAdapter,
) -> MarketLearningPilotService:
    return MarketLearningPilotService(
        environment=RuntimeEnvironment.ENV_DEV,
        draft_port=adapter,
    )


def _execute(
    *,
    service: MarketLearningPilotService,
    intent: WordPressDraftIntent,
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
):
    return service.execute(
        pilot=PilotEconomics(),
        intent=intent,
        policy_result=eligible_policy_result,
        rakuten_result=recorded_rakuten_result,
    )


def test_exact_create_replays_without_a_second_logical_draft(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    adapter = RecordedWordPressDraftAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        draft_capacity=2,
    )
    service = _service(adapter)
    intent = _intent()

    created = _execute(
        service=service,
        intent=intent,
        eligible_policy_result=eligible_policy_result,
        recorded_rakuten_result=recorded_rakuten_result,
    )
    replayed = _execute(
        service=service,
        intent=intent,
        eligible_policy_result=eligible_policy_result,
        recorded_rakuten_result=recorded_rakuten_result,
    )

    assert created.receipt.disposition is DraftDisposition.CREATED
    assert replayed.receipt.disposition is DraftDisposition.REPLAYED
    assert replayed.receipt.draft_id == created.receipt.draft_id
    assert (
        replayed.receipt.operation_binding_sha256
        == created.receipt.operation_binding_sha256
    )
    assert replayed.receipt.logical_draft_sha256 == created.receipt.logical_draft_sha256
    assert replayed.evidence.evidence_sha256 == created.evidence.evidence_sha256
    assert adapter.logical_draft_count == 1
    assert adapter.applied_operation_count == 1


def test_changed_content_requires_explicit_update_and_update_replays(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    adapter = RecordedWordPressDraftAdapter(
        environment=RuntimeEnvironment.CI,
        draft_capacity=1,
    )
    service = _service(adapter)
    created = _execute(
        service=service,
        intent=_intent(),
        eligible_policy_result=eligible_policy_result,
        recorded_rakuten_result=recorded_rakuten_result,
    )

    with pytest.raises(MarketLearningPilotFailure) as failure:
        _execute(
            service=service,
            intent=_intent(content="<p>Changed but still create.</p>"),
            eligible_policy_result=eligible_policy_result,
            recorded_rakuten_result=recorded_rakuten_result,
        )
    assert failure.value.code is MarketLearningPilotFailureCode.DRAFT_UPDATE_REQUIRED
    assert adapter.applied_operation_count == 1

    update_intent = _intent(
        operation=DraftOperation.UPDATE_DRAFT,
        content="<p>Explicitly updated local content.</p>",
        existing_draft_id=created.receipt.draft_id,
    )
    updated = _execute(
        service=service,
        intent=update_intent,
        eligible_policy_result=eligible_policy_result,
        recorded_rakuten_result=recorded_rakuten_result,
    )
    replayed = _execute(
        service=service,
        intent=update_intent,
        eligible_policy_result=eligible_policy_result,
        recorded_rakuten_result=recorded_rakuten_result,
    )

    assert updated.receipt.disposition is DraftDisposition.UPDATED
    assert replayed.receipt.disposition is DraftDisposition.REPLAYED
    assert updated.receipt.draft_id == created.receipt.draft_id
    assert updated.receipt.logical_draft_sha256 == created.receipt.logical_draft_sha256
    assert adapter.logical_draft_count == 1
    assert adapter.applied_operation_count == 2


def test_update_rejects_wrong_target_and_unchanged_content_without_state_change(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    adapter = RecordedWordPressDraftAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        draft_capacity=1,
    )
    service = _service(adapter)
    created = _execute(
        service=service,
        intent=_intent(),
        eligible_policy_result=eligible_policy_result,
        recorded_rakuten_result=recorded_rakuten_result,
    )

    with pytest.raises(MarketLearningPilotFailure) as wrong_target:
        _execute(
            service=service,
            intent=_intent(
                operation=DraftOperation.UPDATE_DRAFT,
                content="<p>Changed.</p>",
                existing_draft_id=created.receipt.draft_id + 1,
            ),
            eligible_policy_result=eligible_policy_result,
            recorded_rakuten_result=recorded_rakuten_result,
        )
    assert (
        wrong_target.value.code is MarketLearningPilotFailureCode.DRAFT_TARGET_MISMATCH
    )

    with pytest.raises(MarketLearningPilotFailure) as unchanged:
        _execute(
            service=service,
            intent=_intent(
                operation=DraftOperation.UPDATE_DRAFT,
                existing_draft_id=created.receipt.draft_id,
            ),
            eligible_policy_result=eligible_policy_result,
            recorded_rakuten_result=recorded_rakuten_result,
        )
    assert unchanged.value.code is MarketLearningPilotFailureCode.DRAFT_UPDATE_REQUIRED
    assert adapter.applied_operation_count == 1


def test_recorded_receipts_are_deterministic_and_immutable_across_adapters(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    receipts = []
    for _ in range(2):
        adapter = RecordedWordPressDraftAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            draft_capacity=1,
        )
        receipts.append(
            _execute(
                service=_service(adapter),
                intent=_intent(),
                eligible_policy_result=eligible_policy_result,
                recorded_rakuten_result=recorded_rakuten_result,
            ).receipt
        )

    assert receipts[0] == receipts[1]
    with pytest.raises(FrozenInstanceError):
        receipts[0].draft_id = 1  # type: ignore[misc]


def test_concurrent_exact_create_has_one_created_result_and_one_logical_draft(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    adapter = RecordedWordPressDraftAdapter(
        environment=RuntimeEnvironment.CI,
        draft_capacity=1,
    )
    service = _service(adapter)
    intent = _intent()

    def execute_once() -> DraftDisposition:
        return _execute(
            service=service,
            intent=intent,
            eligible_policy_result=eligible_policy_result,
            recorded_rakuten_result=recorded_rakuten_result,
        ).receipt.disposition

    with ThreadPoolExecutor(max_workers=8) as executor:
        dispositions = tuple(executor.map(lambda _: execute_once(), range(32)))

    assert dispositions.count(DraftDisposition.CREATED) == 1
    assert dispositions.count(DraftDisposition.REPLAYED) == 31
    assert adapter.logical_draft_count == 1
    assert adapter.applied_operation_count == 1


@pytest.mark.parametrize(
    "environment",
    [
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ],
)
def test_recorded_adapter_rejects_every_nonlocal_environment(
    environment: RuntimeEnvironment,
) -> None:
    with pytest.raises(MarketLearningPilotFailure) as failure:
        RecordedWordPressDraftAdapter(environment=environment, draft_capacity=1)

    assert failure.value.code is MarketLearningPilotFailureCode.ENVIRONMENT_DISABLED
