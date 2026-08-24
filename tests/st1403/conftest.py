"""Synthetic exact builders for isolated ST-1403 tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_refresh_proposal import (  # noqa: E402
    RecordedRefreshProposalAdapter,
    RecordedRefreshProposalFixture,
)
from raos.adapters.recorded_policy_engine import (  # noqa: E402
    load_recorded_policy_fixture,
)
from raos.application.freshness.refresh_proposal import (  # noqa: E402
    RefreshProposalService,
    bind_refresh_proposal_request,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.editorial.policy_engine_v2 import (  # noqa: E402
    PolicyEvaluationEnvelopeV2,
    PolicyEvaluationReportV2,
    evaluate_editorial_policy_v2,
)
from raos.domain.freshness.freshness import (  # noqa: E402
    FreshnessEvaluation,
    FreshnessEvaluationRequest,
    FreshnessObservationStatus,
    evaluate_freshness,
)
from raos.domain.freshness.refresh_proposal import (  # noqa: E402
    RefreshActionType,
    RefreshChangeType,
    RefreshChangedEntityType,
    RefreshDiff,
    RefreshDiffKind,
    RefreshImpactLevel,
    RefreshImpactSurface,
    RefreshProposalCandidate,
    RefreshRequiredAction,
    build_refresh_proposal,
)


UTC = timezone.utc
POLICY_FIXTURE_PATH = REPOSITORY_ROOT / "changes/st-0805/generated/policy-pass.v2.json"
ARTICLE_VERSION_ID = "018f3e90-7b00-7000-8000-000000000806"
EVALUATED_AT = datetime(2026, 8, 24, 1, 0, tzinfo=UTC)


def hex_digest(label: str) -> str:
    return hashlib.sha256(f"st1403:{label}".encode("ascii")).hexdigest()


def valid_policy_input() -> PolicyEvaluationEnvelopeV2:
    return load_recorded_policy_fixture(POLICY_FIXTURE_PATH.read_bytes())


def policy_result(
    request: PolicyEvaluationEnvelopeV2 | None = None,
) -> PolicyEvaluationReportV2:
    request_value = valid_policy_input() if request is None else request
    result = evaluate_editorial_policy_v2(request_value)
    assert result.locally_evaluated
    return result


def freshness_request(
    *,
    recommendation_basis_affected: bool = False,
    age: timedelta = timedelta(hours=1),
) -> FreshnessEvaluationRequest:
    evaluated_at = EVALUATED_AT
    return FreshnessEvaluationRequest(
        freshness_class_id="FRESH-001",
        observation_status=FreshnessObservationStatus.VALIDATED,
        observed_at=evaluated_at - age,
        evaluated_at=evaluated_at,
        recommendation_basis_affected=recommendation_basis_affected,
    )


def freshness_result(
    *,
    request: FreshnessEvaluationRequest | None = None,
    recommendation_basis_affected: bool = False,
    age: timedelta = timedelta(hours=1),
) -> FreshnessEvaluation:
    request_value = (
        freshness_request(
            recommendation_basis_affected=recommendation_basis_affected,
            age=age,
        )
        if request is None
        else request
    )
    return evaluate_freshness(request_value)


def refresh_diff(
    *,
    ordinal: int = 1,
    kind: RefreshDiffKind = RefreshDiffKind.CHANGED,
    change_type: RefreshChangeType = RefreshChangeType.PRODUCT_ATTRIBUTE,
    changed_entity_type: RefreshChangedEntityType = (RefreshChangedEntityType.FACT),
    impact_level: RefreshImpactLevel = RefreshImpactLevel.HIGH,
    required_action: RefreshRequiredAction = RefreshRequiredAction.REFRESH_DRAFT,
    impact_surfaces: tuple[RefreshImpactSurface, ...] = (
        RefreshImpactSurface.ARTICLE_BODY,
    ),
    action_type: RefreshActionType = RefreshActionType.UPDATE,
    recommendation_rank_change: bool = False,
    affected_claim_ids: tuple[str, ...] = ("CLAIM-1403-001",),
) -> RefreshDiff:
    before_sha256: str | None = hex_digest(f"before-{ordinal}")
    after_sha256: str | None = hex_digest(f"after-{ordinal}")
    if kind is RefreshDiffKind.ADDED:
        before_sha256 = None
    elif kind is RefreshDiffKind.REMOVED:
        after_sha256 = None
    return RefreshDiff(
        diff_id=f"DIFF-1403-{ordinal:03d}",
        kind=kind,
        change_type=change_type,
        changed_entity_type=changed_entity_type,
        changed_entity_id=f"ENTITY-1403-{ordinal:03d}",
        before_sha256=before_sha256,
        after_sha256=after_sha256,
        affected_claim_ids=affected_claim_ids,
        impact_level=impact_level,
        required_action=required_action,
        impact_surfaces=impact_surfaces,
        action_type=action_type,
        deterministic_priority_rank=ordinal,
        recommendation_rank_change=recommendation_rank_change,
    )


def proposal_candidate(
    *,
    diffs: tuple[RefreshDiff, ...] | None = None,
) -> RefreshProposalCandidate:
    return RefreshProposalCandidate(
        article_version_id=ARTICLE_VERSION_ID,
        baseline_publication_snapshot_sha256=hex_digest("baseline-snapshot"),
        candidate_snapshot_sha256=hex_digest("candidate-snapshot"),
        diffs=(refresh_diff(),) if diffs is None else diffs,
    )


def recorded_adapter(
    *,
    candidate: RefreshProposalCandidate | None = None,
    freshness_request_value: FreshnessEvaluationRequest | None = None,
    freshness: FreshnessEvaluation | None = None,
    policy_request_value: PolicyEvaluationEnvelopeV2 | None = None,
    policy: PolicyEvaluationReportV2 | None = None,
) -> RecordedRefreshProposalAdapter:
    candidate_value = proposal_candidate() if candidate is None else candidate
    exact_freshness_request = (
        freshness_request()
        if freshness_request_value is None
        else freshness_request_value
    )
    freshness_value = (
        freshness_result(request=exact_freshness_request)
        if freshness is None
        else freshness
    )
    exact_policy_request = (
        valid_policy_input() if policy_request_value is None else policy_request_value
    )
    policy_value = policy_result(exact_policy_request) if policy is None else policy
    request = bind_refresh_proposal_request(
        candidate=candidate_value,
        freshness_request=exact_freshness_request,
        freshness_result=freshness_value,
        policy_request=exact_policy_request,
        policy_result=policy_value,
    )
    proposal = build_refresh_proposal(request)
    return RecordedRefreshProposalAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        fixture_capacity=1,
        fixtures=(RecordedRefreshProposalFixture(request=request, proposal=proposal),),
    )


def refresh_service(
    *,
    candidate: RefreshProposalCandidate | None = None,
    freshness_request_value: FreshnessEvaluationRequest | None = None,
    freshness: FreshnessEvaluation | None = None,
    policy_request_value: PolicyEvaluationEnvelopeV2 | None = None,
    policy: PolicyEvaluationReportV2 | None = None,
) -> RefreshProposalService:
    return RefreshProposalService(
        environment=RuntimeEnvironment.ENV_DEV,
        exchange=recorded_adapter(
            candidate=candidate,
            freshness_request_value=freshness_request_value,
            freshness=freshness,
            policy_request_value=policy_request_value,
            policy=policy,
        ),
    )
