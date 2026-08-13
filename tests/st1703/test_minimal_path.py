"""Early executable path for the approved local market-learning pilot."""

from __future__ import annotations

from raos.application.editorial.market_learning_pilot import (
    MarketLearningPilotService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search import RakutenItemSearchResult
from raos.domain.editorial.market_learning_pilot import (
    DraftDisposition,
    DraftOperation,
    PilotAuthorizationStatus,
    PilotEconomics,
    PilotExecutionStatus,
    WordPressDraftIntent,
    WordPressDraftReceipt,
)
from raos.domain.editorial.policy_engine import PolicyEvaluationResult


ARTICLE_VERSION_ID = "ARTICLE-VERSION-1703"


class OneDraftPort:
    def apply(self, candidate: object) -> WordPressDraftReceipt:
        from raos.domain.editorial.market_learning_pilot import BoundWordPressDraft

        assert type(candidate) is BoundWordPressDraft
        return WordPressDraftReceipt(
            draft_id=1703,
            operation=candidate.intent.operation,
            disposition=DraftDisposition.CREATED,
            status="draft",
            content_binding_sha256=candidate.content_binding_sha256,
            operation_binding_sha256=candidate.operation_binding_sha256,
            logical_draft_sha256="c" * 64,
            network_status=PilotExecutionStatus.NOT_EXECUTED,
            publication_authorized=False,
            production_eligible=False,
        )


def test_local_recorded_create_path_keeps_all_external_authority_closed(
    eligible_policy_result: PolicyEvaluationResult,
    recorded_rakuten_result: RakutenItemSearchResult,
) -> None:
    service = MarketLearningPilotService(
        environment=RuntimeEnvironment.ENV_DEV,
        draft_port=OneDraftPort(),
    )

    result = service.execute(
        pilot=PilotEconomics(),
        intent=WordPressDraftIntent(
            operation=DraftOperation.CREATE_DRAFT,
            article_version_id=ARTICLE_VERSION_ID,
            title="Synthetic local draft",
            content="<p>Recorded-only content.</p>",
        ),
        policy_result=eligible_policy_result,
        rakuten_result=recorded_rakuten_result,
    )

    assert result.receipt.draft_id == 1703
    assert result.receipt.status == "draft"
    assert result.evidence.formal_test is PilotExecutionStatus.NOT_EXECUTED
    assert result.evidence.live_validation is PilotExecutionStatus.NOT_EXECUTED
    assert result.evidence.publication is PilotAuthorizationStatus.NOT_AUTHORIZED
    assert result.evidence.production is PilotExecutionStatus.NOT_EXECUTED
