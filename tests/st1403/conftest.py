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
from raos.application.freshness.refresh_proposal import (  # noqa: E402
    RefreshProposalService,
    bind_refresh_proposal_request,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.editorial.policy_engine import (  # noqa: E402
    CONTENT_TEST_MATRIX_SHA256,
    POLICY_CATALOG_ID,
    POLICY_CATALOG_SHA256,
    POLICY_CATALOG_VERSION,
    POLICY_DEFINITIONS,
    QUALITY_AXIS_DEFINITIONS,
    QUALITY_CATALOG_ID,
    QUALITY_CATALOG_SHA256,
    QUALITY_CATALOG_VERSION,
    QUALITY_GATE_DEFINITIONS,
    QUALITY_MODEL_VERSION,
    REVIEW_CHECKLIST_ID,
    REVIEW_CHECKLIST_SHA256,
    REVIEW_CHECKLIST_VERSION,
    ZERO_TOLERANCE_LABELS,
    AxisAssessmentState,
    BoundReference,
    ContractBindings,
    FindingTarget,
    FindingTargetType,
    GateAssessmentState,
    PolicyAssessment,
    PolicyEvaluationInput,
    PolicyEvaluationResult,
    PolicyRuleResult,
    PredecessorAssessment,
    PredecessorState,
    PredecessorStory,
    QualityAxisAssessment,
    QualityGateAssessment,
    ReferenceId,
    Sha256Digest,
    UtcInstant,
    VersionRef,
    ZeroToleranceAssessment,
    ZeroToleranceState,
    evaluate_editorial_policy,
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
ARTICLE_VERSION_ID = ReferenceId("ARTICLE-VERSION-1403")
EVALUATED_AT = UtcInstant(datetime(2026, 8, 16, 3, 0, tzinfo=UTC))


def hex_digest(label: str) -> str:
    return hashlib.sha256(f"st1403:{label}".encode("ascii")).hexdigest()


def _digest_ref(label: str) -> Sha256Digest:
    return Sha256Digest(hex_digest(label))


def _bound(label: str) -> BoundReference:
    return BoundReference(ReferenceId(label), _digest_ref(label))


def _contracts() -> ContractBindings:
    return ContractBindings(
        policy_catalog_id=ReferenceId(POLICY_CATALOG_ID),
        policy_catalog_version=VersionRef(POLICY_CATALOG_VERSION),
        policy_catalog_sha256=Sha256Digest(POLICY_CATALOG_SHA256),
        quality_catalog_id=ReferenceId(QUALITY_CATALOG_ID),
        quality_catalog_version=VersionRef(QUALITY_CATALOG_VERSION),
        quality_model_version=VersionRef(QUALITY_MODEL_VERSION),
        quality_catalog_sha256=Sha256Digest(QUALITY_CATALOG_SHA256),
        review_checklist_id=ReferenceId(REVIEW_CHECKLIST_ID),
        review_checklist_version=VersionRef(REVIEW_CHECKLIST_VERSION),
        review_checklist_sha256=Sha256Digest(REVIEW_CHECKLIST_SHA256),
        content_test_matrix_sha256=Sha256Digest(CONTENT_TEST_MATRIX_SHA256),
    )


def _predecessor(story: PredecessorStory) -> PredecessorAssessment:
    suffix = story.value.replace("-", "_")
    return PredecessorAssessment(
        story_id=story,
        article_version_id=ARTICLE_VERSION_ID,
        state=PredecessorState.AVAILABLE,
        result=_bound(f"RESULT-{suffix}"),
        provenance=_bound(f"PROVENANCE-{suffix}"),
    )


def _policy_assessment(policy_id: str) -> PolicyAssessment:
    definition = next(
        item for item in POLICY_DEFINITIONS if item.policy_id == policy_id
    )
    suffix = policy_id.removeprefix("POL-CONT-")
    return PolicyAssessment(
        policy_id=policy_id,
        policy_version=VersionRef(POLICY_CATALOG_VERSION),
        policy_source_sha256=Sha256Digest(POLICY_CATALOG_SHA256),
        article_version_id=ARTICLE_VERSION_ID,
        stage=definition.stage,
        result=PolicyRuleResult.PASS,
        target=FindingTarget(FindingTargetType.ARTICLE_VERSION, ARTICLE_VERSION_ID),
        evidence=(_bound(f"EVIDENCE-POLICY-{suffix}"),),
        detector=_bound(f"DETECTOR-POLICY-{suffix}"),
    )


def _axis_assessment(axis_id: str) -> QualityAxisAssessment:
    definition = next(
        item for item in QUALITY_AXIS_DEFINITIONS if item.axis_id == axis_id
    )
    suffix = axis_id.removeprefix("QAX-")
    return QualityAxisAssessment(
        axis_id=axis_id,
        axis_code=definition.code,
        quality_model_version=VersionRef(QUALITY_MODEL_VERSION),
        quality_source_sha256=Sha256Digest(QUALITY_CATALOG_SHA256),
        article_version_id=ARTICLE_VERSION_ID,
        state=AxisAssessmentState.EVALUATED,
        score=definition.weight,
        evidence=(_bound(f"EVIDENCE-AXIS-{suffix}"),),
        evaluator=_bound(f"EVALUATOR-AXIS-{suffix}"),
    )


def _signal_assessment(label: str) -> ZeroToleranceAssessment:
    suffix = f"{ZERO_TOLERANCE_LABELS.index(label) + 1:03d}"
    return ZeroToleranceAssessment(
        label=label,
        article_version_id=ARTICLE_VERSION_ID,
        state=ZeroToleranceState.CLEAR,
        evidence=(_bound(f"EVIDENCE-SIGNAL-{suffix}"),),
        detector=_bound(f"DETECTOR-SIGNAL-{suffix}"),
    )


def _gate_assessment(gate_id: str) -> QualityGateAssessment:
    definition = next(
        item for item in QUALITY_GATE_DEFINITIONS if item.gate_id == gate_id
    )
    suffix = gate_id.removeprefix("QG-CONT-")
    return QualityGateAssessment(
        gate_id=gate_id,
        stage=definition.stage,
        quality_catalog_version=VersionRef(QUALITY_CATALOG_VERSION),
        quality_source_sha256=Sha256Digest(QUALITY_CATALOG_SHA256),
        article_version_id=ARTICLE_VERSION_ID,
        state=GateAssessmentState.PASS,
        failure_action=definition.failure_action,
        evidence=(_bound(f"EVIDENCE-GATE-{suffix}"),),
        evaluator=_bound(f"EVALUATOR-GATE-{suffix}"),
    )


def valid_policy_input() -> PolicyEvaluationInput:
    return PolicyEvaluationInput(
        article_version_id=ARTICLE_VERSION_ID,
        evaluated_at=EVALUATED_AT,
        contracts=_contracts(),
        predecessors=tuple(_predecessor(story) for story in PredecessorStory),
        policy_assessments=tuple(
            _policy_assessment(definition.policy_id)
            for definition in POLICY_DEFINITIONS
        ),
        axis_assessments=tuple(
            _axis_assessment(definition.axis_id)
            for definition in QUALITY_AXIS_DEFINITIONS
        ),
        zero_tolerance_assessments=tuple(
            _signal_assessment(label) for label in ZERO_TOLERANCE_LABELS
        ),
        gate_assessments=tuple(
            _gate_assessment(definition.gate_id)
            for definition in QUALITY_GATE_DEFINITIONS
        ),
        waiver_attempts=(),
    )


def policy_result(
    request: PolicyEvaluationInput | None = None,
) -> PolicyEvaluationResult:
    request_value = valid_policy_input() if request is None else request
    result = evaluate_editorial_policy(request_value)
    assert result.local_eligibility is True
    return result


def freshness_request(
    *,
    recommendation_basis_affected: bool = False,
    age: timedelta = timedelta(hours=1),
) -> FreshnessEvaluationRequest:
    evaluated_at = EVALUATED_AT.value
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
        article_version_id=ARTICLE_VERSION_ID.value,
        baseline_publication_snapshot_sha256=hex_digest("baseline-snapshot"),
        candidate_snapshot_sha256=hex_digest("candidate-snapshot"),
        diffs=(refresh_diff(),) if diffs is None else diffs,
    )


def recorded_adapter(
    *,
    candidate: RefreshProposalCandidate | None = None,
    freshness_request_value: FreshnessEvaluationRequest | None = None,
    freshness: FreshnessEvaluation | None = None,
    policy_request_value: PolicyEvaluationInput | None = None,
    policy: PolicyEvaluationResult | None = None,
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
    policy_request_value: PolicyEvaluationInput | None = None,
    policy: PolicyEvaluationResult | None = None,
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
