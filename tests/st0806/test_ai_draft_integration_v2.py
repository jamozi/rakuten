"""Successful and restart behavior for ST-0806 V2."""

from __future__ import annotations

import json

import pytest

from raos.adapters.recorded_durable_ai_job_queue_v2 import (
    RecordedDurableAiJobStateAdapterV2,
)
from raos.domain.editorial.ai_draft_integration_v2 import (
    BoundContentAstV2,
    DraftCoverageDecisionV2,
    DraftExecutionV2,
    DraftProposalDispositionV2,
    build_content_ast_diff_v2,
)
from raos.domain.editorial.content_ast import dump_content_ast_json, load_content_ast
from raos.domain.evidence.claim_evidence import CoverageStatus
from v2_support import (
    ARTICLE_ID,
    CATEGORY_ID,
    SITE_ID,
    SOURCE_PACKET_VERSION_ID,
    VERSION_ID,
    durable_success,
    request,
    service_and_adapter,
)


def test_exact_durable_success_creates_one_effect_free_human_proposal() -> None:
    bound = request()
    service, adapter = service_and_adapter(bound_request=bound)

    result = service.integrate(request=bound)

    assert adapter.call_count == 1
    assert result.coverage_decision is DraftCoverageDecisionV2.AVAILABLE
    assert result.coverage_status is CoverageStatus.PASS
    assert result.disposition is DraftProposalDispositionV2.HUMAN_EDITABLE_PROPOSAL_ONLY
    assert result.execution is DraftExecutionV2.RECORDED_ONLY
    assert result.proposal is not None
    assert result.adoption_intent is not None
    proposal = result.proposal
    assert proposal.article_id == ARTICLE_ID
    assert proposal.article_version_id == VERSION_ID
    assert proposal.source_packet_version_id == SOURCE_PACKET_VERSION_ID
    assert proposal.site_id == SITE_ID
    assert proposal.category_id == CATEGORY_ID
    assert proposal.human_editable is True
    assert proposal.diff.changed is True
    assert proposal.diff.operations
    assert proposal.coverage.major_evidenced == proposal.coverage.major_total
    assert (
        proposal.coverage.all_verifiable_evidenced * 100
        >= proposal.coverage.all_verifiable_total * 95
    )
    assert proposal.durable.st0706_contract_sha256 == (
        "eef608f77d99a37716541873cd91ecf18257ee4c7532848046aa3bdb1640ae7c"
    )
    assert proposal.durable.st0706_policy_sha256 == (
        "f4d7c6bacfbbc8c104d2e4cbd1700d87d946191b789c7967183a1c4b9186d5a8"
    )
    assert proposal.durable.input_artifact_sha256 == "5" * 64
    assert proposal.durable.output_artifact_sha256 == "6" * 64
    assert proposal.durable.validation_plan_sha256
    assert result.adoption_intent.effect == "PROPOSAL_ONLY"
    assert not any(
        (
            result.approval_permitted,
            result.apply_performed,
            result.merge_performed,
            result.publication_permitted,
            result.recommendation_order_changed,
            result.production_eligible,
        )
    )
    assert result.persistence is DraftExecutionV2.NOT_EXECUTED
    assert result.event_emission is DraftExecutionV2.NOT_EXECUTED
    assert result.formal_validation is DraftExecutionV2.NOT_EXECUTED
    assert result.live_validation is DraftExecutionV2.NOT_EXECUTED
    assert result.release is DraftExecutionV2.NOT_EXECUTED


def test_restart_rehydrates_exact_st0706_bytes_and_returns_identical_result() -> None:
    snapshot, outcome = durable_success()
    first_request = request(snapshot=snapshot, outcome=outcome)
    first_service, _ = service_and_adapter(bound_request=first_request)
    first = first_service.integrate(request=first_request)

    rehydrated_state = RecordedDurableAiJobStateAdapterV2.from_snapshot(
        snapshot=snapshot
    )
    restarted_snapshot = rehydrated_state.export_snapshot()
    restarted_request = request(snapshot=restarted_snapshot, outcome=outcome)
    restarted_service, _ = service_and_adapter(bound_request=restarted_request)
    restarted = restarted_service.integrate(request=restarted_request)

    assert restarted_snapshot.state_bytes == snapshot.state_bytes
    assert restarted_snapshot.revision == snapshot.revision
    assert restarted_snapshot.state_sha256 == snapshot.state_sha256
    assert restarted_request.binding_sha256 == first_request.binding_sha256
    assert restarted == first


def test_zero_cost_is_known_and_not_coerced_to_unknown_or_positive() -> None:
    zero_snapshot, zero_outcome = durable_success(cost=0)
    zero_request = request(snapshot=zero_snapshot, outcome=zero_outcome)
    zero_service, _ = service_and_adapter(bound_request=zero_request)
    zero = zero_service.integrate(request=zero_request)

    positive_request = request()
    positive_service, _ = service_and_adapter(bound_request=positive_request)
    positive = positive_service.integrate(request=positive_request)

    assert zero.durable_binding.actual_cost_jpy == 0
    assert zero.durable_binding.accumulated_cost_jpy == 0
    assert positive.durable_binding.actual_cost_jpy == 7
    assert (
        zero.durable_binding.binding_sha256 != positive.durable_binding.binding_sha256
    )


def test_ordered_diff_is_deterministic_and_contains_hashes_not_raw_values() -> None:
    result = service_and_adapter(bound_request=(bound := request()))[0].integrate(
        request=bound
    )
    assert result.proposal is not None
    first = result.proposal.diff
    second = build_content_ast_diff_v2(
        result.proposal.before_ast, result.proposal.after_ast
    )
    assert second == first
    assert tuple(item.ordinal for item in first.operations) == tuple(
        range(1, len(first.operations) + 1)
    )
    assert len({item.json_pointer for item in first.operations}) == len(
        first.operations
    )
    assert all(
        item.before_value_sha256 is not None or item.after_value_sha256 is not None
        for item in first.operations
    )
    rendered = repr(first)
    assert "合成" not in rendered
    assert "<redacted-ai-draft-integration-v2>" in rendered


@pytest.mark.parametrize("variant", range(12))
def test_diff_bounded_property_matrix_is_repeatable(variant: int) -> None:
    bound = request()
    before = BoundContentAstV2.from_content_ast(bound.source_version.content_ast)
    value = json.loads(before.canonical_bytes)
    value["blocks"][1]["content"][0]["text"] = f"deterministic variant {variant}"
    after = BoundContentAstV2(
        dump_content_ast_json(
            load_content_ast(json.dumps(value, ensure_ascii=False))
        ).encode()
    )

    first = build_content_ast_diff_v2(before, after)
    second = build_content_ast_diff_v2(before, after)

    assert first == second
    assert 1 <= len(first.operations) <= 4096
    assert tuple(item.ordinal for item in first.operations) == tuple(
        range(1, len(first.operations) + 1)
    )


def test_ci_is_the_only_other_explicit_local_environment() -> None:
    from raos.config.runtime import RuntimeEnvironment

    bound = request(environment=RuntimeEnvironment.CI)
    service, adapter = service_and_adapter(
        bound_request=bound,
        environment=RuntimeEnvironment.CI,
    )
    result = service.integrate(request=bound)
    assert adapter.call_count == 1
    assert result.coverage_decision is DraftCoverageDecisionV2.AVAILABLE
