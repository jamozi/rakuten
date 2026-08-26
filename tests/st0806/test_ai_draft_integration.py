"""Focused successful ST-0806 behavior."""

from __future__ import annotations

from .support import (
    ARTICLE_ID,
    CATEGORY_ID,
    CLAIM_ID_1,
    FACT_ID_1,
    SITE_ID,
    VERSION_ID,
    request,
    service_and_adapter,
)
from raos.domain.editorial.ai_draft_integration import (
    AiDraftDisposition,
    AiDraftEnvironment,
    CoverageStatus,
    ExecutionStatus,
)
from raos.domain.editorial.article_lifecycle import ArticleState, ArticleVersionState


def test_success_binds_one_human_editable_recorded_candidate() -> None:
    service, adapter = service_and_adapter()

    result = service.integrate(request=request())

    assert adapter.call_count == 1
    assert result.disposition is AiDraftDisposition.HUMAN_EDITABLE_RECORDED_ONLY
    assert result.article_state is ArticleState.DRAFT
    assert result.version_state is ArticleVersionState.DRAFT
    assert result.coverage_status is CoverageStatus.UNEVALUABLE
    assert result.execution is ExecutionStatus.RECORDED_ONLY
    assert result.candidate.article_id == ARTICLE_ID
    assert result.candidate.article_version_id == VERSION_ID
    assert result.candidate.site_id == SITE_ID
    assert result.candidate.category_id == CATEGORY_ID
    assert result.candidate.diff.changed is True
    assert result.candidate.diff.changed_block_ids == ("BLK-FIX-002",)
    first = result.candidate.claim_fact_references[0]
    assert (first.ordinal, first.claim_id, first.fact_id) == (1, CLAIM_ID_1, FACT_ID_1)
    assert not any(
        (
            result.approval_permitted,
            result.publication_permitted,
            result.merge_performed,
            result.apply_performed,
            result.production_eligible,
        )
    )
    assert result.persistence is ExecutionStatus.NOT_EXECUTED
    assert result.event_emission is ExecutionStatus.NOT_EXECUTED
    assert result.release is ExecutionStatus.NOT_EXECUTED
    assert result.formal_validation is ExecutionStatus.NOT_EXECUTED


def test_ci_is_the_only_other_recorded_environment() -> None:
    service, adapter = service_and_adapter(environment=AiDraftEnvironment.CI)
    result = service.integrate(request=request(environment=AiDraftEnvironment.CI))
    assert adapter.call_count == 1
    assert result.request.environment is AiDraftEnvironment.CI
