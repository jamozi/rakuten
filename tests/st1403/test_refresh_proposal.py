"""Deterministic proposal, impact, priority, and reapproval behavior."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import pickle

import pytest

from raos.application.freshness.refresh_proposal import (
    bind_refresh_proposal_request,
)
from raos.domain.freshness.freshness import RecommendationOrderAction
from raos.domain.freshness.refresh_proposal import (
    MAX_REFRESH_PROPOSAL_DIFFS,
    RefreshActionStatus,
    RefreshActionType,
    RefreshApprovalRequirement,
    RefreshChangeType,
    RefreshChangedEntityType,
    RefreshDiff,
    RefreshDiffKind,
    RefreshExecutionStatus,
    RefreshImpactLevel,
    RefreshImpactSurface,
    RefreshProposal,
    RefreshProposalAuthority,
    RefreshProposalFailure,
    RefreshReapprovalArea,
    RefreshRequiredAction,
    build_refresh_proposal,
)

from .support import (
    freshness_request,
    freshness_result,
    hex_digest,
    policy_result,
    proposal_candidate,
    refresh_diff,
    valid_policy_input,
)


def _proposal(*diffs: RefreshDiff) -> RefreshProposal:
    recommendation_affected = any(
        RefreshImpactSurface.RECOMMENDATION in item.impact_surfaces for item in diffs
    )
    exact_freshness_request = freshness_request(
        recommendation_basis_affected=recommendation_affected
    )
    exact_policy_request = valid_policy_input()
    request = bind_refresh_proposal_request(
        candidate=proposal_candidate(diffs=diffs),
        freshness_request=exact_freshness_request,
        freshness_result=freshness_result(
            request=exact_freshness_request,
        ),
        policy_request=exact_policy_request,
        policy_result=policy_result(exact_policy_request),
    )
    return build_refresh_proposal(request)


def test_dynamic_projection_diff_does_not_invalidate_article_approval() -> None:
    diff = refresh_diff(
        change_type=RefreshChangeType.PRICE,
        changed_entity_type=RefreshChangedEntityType.OFFER,
        impact_level=RefreshImpactLevel.LOW,
        required_action=RefreshRequiredAction.NONE,
        impact_surfaces=(RefreshImpactSurface.DYNAMIC_PUBLIC_PROJECTION,),
        affected_claim_ids=(),
    )

    proposal = _proposal(diff)

    assert proposal.diffs == (diff,)
    assert proposal.impacts[0].reapproval_areas == ()
    assert proposal.reapproval_scope.areas == ()
    assert proposal.reapproval_scope.prior_article_approval_reusable is True
    assert proposal.required_actions == (RefreshRequiredAction.NONE,)
    assert proposal.overall_impact_level is RefreshImpactLevel.LOW


def test_substantive_diff_exposes_exact_article_reapproval_scope() -> None:
    diff = refresh_diff(
        impact_surfaces=(
            RefreshImpactSurface.ARTICLE_BODY,
            RefreshImpactSurface.RECOMMENDATION,
            RefreshImpactSurface.MAJOR_SPECIFICATION,
        ),
    )

    proposal = _proposal(diff)

    expected = (
        RefreshReapprovalArea.ARTICLE_VERSION,
        RefreshReapprovalArea.EDITORIAL_REVIEW,
        RefreshReapprovalArea.PUBLICATION_SNAPSHOT,
    )
    assert proposal.impacts[0].reapproval_areas == expected
    assert proposal.reapproval_scope.areas == expected
    assert proposal.reapproval_scope.prior_article_approval_reusable is False


def test_every_recommendation_rank_change_requires_human_approval() -> None:
    diff = refresh_diff(
        impact_surfaces=(RefreshImpactSurface.RECOMMENDATION,),
        recommendation_rank_change=True,
    )

    proposal = _proposal(diff)

    assert proposal.reapproval_scope.recommendation_rank_change is True
    assert proposal.reapproval_scope.approval_requirement is (
        RefreshApprovalRequirement.HUMAN_APPROVAL_REQUIRED
    )
    assert proposal.reapproval_scope.areas == (
        RefreshReapprovalArea.ARTICLE_VERSION,
        RefreshReapprovalArea.EDITORIAL_REVIEW,
        RefreshReapprovalArea.PUBLICATION_SNAPSHOT,
        RefreshReapprovalArea.RECOMMENDATION_ORDER,
    )
    assert all(
        item.approval_requirement is RefreshApprovalRequirement.HUMAN_APPROVAL_REQUIRED
        for item in proposal.action_candidates
    )
    assert proposal.recommendation_order_action is RecommendationOrderAction.FORBIDDEN
    assert proposal.automatic_reordering_authorized is False
    assert proposal.can_change_state is False


def test_action_priority_and_input_order_are_preserved_exactly() -> None:
    diffs = tuple(
        refresh_diff(
            ordinal=ordinal,
            kind=kind,
            action_type=action_type,
        )
        for ordinal, kind, action_type in (
            (1, RefreshDiffKind.ADDED, RefreshActionType.CREATE),
            (2, RefreshDiffKind.CHANGED, RefreshActionType.UPDATE),
            (3, RefreshDiffKind.CHANGED, RefreshActionType.MERGE),
            (4, RefreshDiffKind.REMOVED, RefreshActionType.DELETE),
        )
    )

    proposal = _proposal(*diffs)

    assert tuple(item.source_diff_id for item in proposal.action_candidates) == tuple(
        item.diff_id for item in diffs
    )
    assert tuple(
        item.deterministic_priority_rank for item in proposal.action_candidates
    ) == (1, 2, 3, 4)
    assert tuple(item.action_type for item in proposal.action_candidates) == tuple(
        item.action_type for item in diffs
    )
    assert all(
        item.status is RefreshActionStatus.PROPOSED
        and item.authority is RefreshProposalAuthority.UNAPPROVED_PROPOSAL
        and item.can_change_state is False
        and item.execution_status is RefreshExecutionStatus.NOT_EXECUTED
        for item in proposal.action_candidates
    )


def test_proposal_is_deterministic_and_hash_bound() -> None:
    diff = refresh_diff()

    first = _proposal(diff)
    second = _proposal(diff)

    assert first == second
    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64
    assert first.request_fingerprint == second.request_fingerprint


def test_overall_impact_and_required_actions_are_closed_unions() -> None:
    proposal = _proposal(
        refresh_diff(
            ordinal=1,
            impact_level=RefreshImpactLevel.LOW,
            required_action=RefreshRequiredAction.REVIEW,
        ),
        refresh_diff(
            ordinal=2,
            impact_level=RefreshImpactLevel.CRITICAL,
            required_action=RefreshRequiredAction.SUSPEND_PUBLICATION,
        ),
        refresh_diff(
            ordinal=3,
            impact_level=RefreshImpactLevel.MEDIUM,
            required_action=RefreshRequiredAction.REVIEW,
        ),
    )

    assert proposal.overall_impact_level is RefreshImpactLevel.CRITICAL
    assert proposal.required_actions == (
        RefreshRequiredAction.REVIEW,
        RefreshRequiredAction.SUSPEND_PUBLICATION,
    )


def test_became_stale_can_bind_unchanged_fact_bytes() -> None:
    digest = hex_digest("age-only-change")
    diff = replace(
        refresh_diff(kind=RefreshDiffKind.BECAME_STALE),
        before_sha256=digest,
        after_sha256=digest,
    )

    proposal = _proposal(diff)

    assert proposal.diffs[0].kind is RefreshDiffKind.BECAME_STALE
    assert proposal.diffs[0].before_sha256 == proposal.diffs[0].after_sha256


@pytest.mark.parametrize(
    ("kind", "before", "after"),
    (
        (RefreshDiffKind.ADDED, hex_digest("before"), hex_digest("after")),
        (RefreshDiffKind.REMOVED, hex_digest("before"), hex_digest("after")),
        (RefreshDiffKind.CHANGED, None, hex_digest("after")),
        (RefreshDiffKind.CHANGED, hex_digest("same"), hex_digest("same")),
        (RefreshDiffKind.RESOLVED_CONFLICT, hex_digest("same"), hex_digest("same")),
    ),
)
def test_invalid_diff_hash_shapes_fail_closed(
    kind: RefreshDiffKind,
    before: str | None,
    after: str | None,
) -> None:
    base = refresh_diff()

    with pytest.raises(RefreshProposalFailure) as caught:
        replace(base, kind=kind, before_sha256=before, after_sha256=after)

    assert caught.value.code == "INVALID_ARGUMENT"


def test_rank_change_without_recommendation_surface_fails_closed() -> None:
    with pytest.raises(RefreshProposalFailure) as caught:
        refresh_diff(recommendation_rank_change=True)

    assert caught.value.code == "INVALID_ARGUMENT"


def test_non_contiguous_or_reordered_priority_fails_closed() -> None:
    first = refresh_diff(ordinal=1)
    second = refresh_diff(ordinal=2)

    with pytest.raises(RefreshProposalFailure) as caught:
        proposal_candidate(diffs=(second, first))

    assert caught.value.code == "INVALID_ARGUMENT"


def test_diff_collections_require_exact_deterministic_order() -> None:
    with pytest.raises(RefreshProposalFailure):
        refresh_diff(affected_claim_ids=("CLAIM-Z", "CLAIM-A"))
    with pytest.raises(RefreshProposalFailure):
        refresh_diff(
            impact_surfaces=(
                RefreshImpactSurface.RECOMMENDATION,
                RefreshImpactSurface.ARTICLE_BODY,
            )
        )


def test_output_is_deeply_immutable_redacted_and_not_pickleable() -> None:
    proposal = _proposal(refresh_diff())

    with pytest.raises(FrozenInstanceError):
        proposal.can_change_state = True  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        proposal.impacts[0].required_action = RefreshRequiredAction.NONE  # type: ignore[misc]
    with pytest.raises(TypeError):
        pickle.dumps(proposal)
    assert "ARTICLE-VERSION" not in repr(proposal)
    assert "CLAIM-1403" not in repr(proposal.impacts[0])


def test_output_cannot_rebind_an_impact_or_reapproval_scope() -> None:
    proposal = _proposal(refresh_diff())

    with pytest.raises(RefreshProposalFailure):
        replace(
            proposal,
            impacts=(
                replace(
                    proposal.impacts[0],
                    required_action=RefreshRequiredAction.NONE,
                ),
            ),
        )
    with pytest.raises(RefreshProposalFailure):
        replace(
            proposal,
            reapproval_scope=replace(
                proposal.reapproval_scope,
                recommendation_rank_change=True,
            ),
        )


def test_candidate_deeply_owns_source_diffs() -> None:
    source_diff = refresh_diff()
    candidate = proposal_candidate(diffs=(source_diff,))
    candidate_fingerprint = candidate.fingerprint

    object.__setattr__(source_diff, "changed_entity_id", "ENTITY-MUTATED")

    assert candidate.diffs[0] is not source_diff
    assert candidate.diffs[0].changed_entity_id == "ENTITY-1403-001"
    assert candidate.fingerprint == candidate_fingerprint


def test_pure_builder_deeply_owns_candidate_diffs() -> None:
    exact_freshness_request = freshness_request()
    exact_policy_request = valid_policy_input()
    request = bind_refresh_proposal_request(
        candidate=proposal_candidate(),
        freshness_request=exact_freshness_request,
        freshness_result=freshness_result(request=exact_freshness_request),
        policy_request=exact_policy_request,
        policy_result=policy_result(exact_policy_request),
    )
    source_diff = request.candidate.diffs[0]
    request_fingerprint = request.fingerprint
    proposal = build_refresh_proposal(request)
    proposal_fingerprint = proposal.fingerprint

    assert request.candidate.diffs[0] is source_diff
    assert request.fingerprint == request_fingerprint
    object.__setattr__(source_diff, "changed_entity_id", "ENTITY-MUTATED")

    assert proposal.diffs[0] is not source_diff
    assert proposal.diffs[0].changed_entity_id == "ENTITY-1403-001"
    assert proposal.fingerprint == proposal_fingerprint


def test_candidate_capacity_is_exactly_bounded() -> None:
    diff = refresh_diff()

    with pytest.raises(RefreshProposalFailure) as caught:
        proposal_candidate(diffs=(diff,) * (MAX_REFRESH_PROPOSAL_DIFFS + 1))

    assert caught.value.code == "INVALID_ARGUMENT"


def test_direct_proposal_constructor_rejects_capacity_and_rank_bypasses() -> None:
    proposal = _proposal(refresh_diff())
    repeated = MAX_REFRESH_PROPOSAL_DIFFS + 1

    with pytest.raises(RefreshProposalFailure) as capacity:
        replace(
            proposal,
            diffs=proposal.diffs * repeated,
            impacts=proposal.impacts * repeated,
            action_candidates=proposal.action_candidates * repeated,
        )
    assert capacity.value.code == "INVALID_ARGUMENT"

    with pytest.raises(RefreshProposalFailure) as duplicate:
        replace(
            proposal,
            diffs=proposal.diffs * 2,
            impacts=proposal.impacts * 2,
            action_candidates=proposal.action_candidates * 2,
        )
    assert duplicate.value.code == "INVALID_ARGUMENT"

    second_with_duplicate_rank = _proposal(
        replace(refresh_diff(ordinal=2), deterministic_priority_rank=1)
    )
    with pytest.raises(RefreshProposalFailure) as rank:
        replace(
            proposal,
            diffs=proposal.diffs + second_with_duplicate_rank.diffs,
            impacts=proposal.impacts + second_with_duplicate_rank.impacts,
            action_candidates=(
                proposal.action_candidates
                + second_with_duplicate_rank.action_candidates
            ),
        )
    assert rank.value.code == "INVALID_ARGUMENT"

    second_with_duplicate_id = replace(
        refresh_diff(ordinal=2),
        diff_id=proposal.diffs[0].diff_id,
    )
    duplicate_id_impact = replace(
        proposal.impacts[0],
        changed_entity_id=second_with_duplicate_id.changed_entity_id,
    )
    duplicate_id_action = replace(
        proposal.action_candidates[0],
        deterministic_priority_rank=2,
    )
    with pytest.raises(RefreshProposalFailure) as duplicate_id:
        replace(
            proposal,
            diffs=proposal.diffs + (second_with_duplicate_id,),
            impacts=proposal.impacts + (duplicate_id_impact,),
            action_candidates=proposal.action_candidates + (duplicate_id_action,),
        )
    assert duplicate_id.value.code == "INVALID_ARGUMENT"


def test_direct_proposal_constructor_deeply_owns_nested_values() -> None:
    proposal = _proposal(refresh_diff())
    clone = replace(proposal)
    clone_fingerprint = clone.fingerprint

    assert clone.diffs[0] is not proposal.diffs[0]
    assert clone.impacts[0] is not proposal.impacts[0]
    assert clone.action_candidates[0] is not proposal.action_candidates[0]
    assert clone.reapproval_scope is not proposal.reapproval_scope

    object.__setattr__(proposal.diffs[0], "changed_entity_id", "ENTITY-MUTATED")
    object.__setattr__(proposal.impacts[0], "changed_entity_id", "ENTITY-MUTATED")
    object.__setattr__(proposal.action_candidates[0], "source_diff_id", "DIFF-MUTATED")
    object.__setattr__(proposal.reapproval_scope, "areas", ())

    assert clone.diffs[0].changed_entity_id == "ENTITY-1403-001"
    assert clone.impacts[0].changed_entity_id == "ENTITY-1403-001"
    assert clone.action_candidates[0].source_diff_id == "DIFF-1403-001"
    assert clone.reapproval_scope.areas == (
        RefreshReapprovalArea.ARTICLE_VERSION,
        RefreshReapprovalArea.EDITORIAL_REVIEW,
        RefreshReapprovalArea.PUBLICATION_SNAPSHOT,
    )
    assert clone.fingerprint == clone_fingerprint
