"""Synthetic builders for the isolated ST-0805 policy evaluator."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


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
    WaiverAttempt,
    WaiverAuthorityClaim,
    WaiverScopeType,
    ZeroToleranceAssessment,
    ZeroToleranceState,
)


ARTICLE_VERSION_ID = ReferenceId("ARTICLE-VERSION-0805")
EVALUATED_AT = UtcInstant(datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc))


def digest_for(label: str) -> Sha256Digest:
    return Sha256Digest(hashlib.sha256(label.encode("ascii")).hexdigest())


def bound(label: str) -> BoundReference:
    return BoundReference(ReferenceId(label), digest_for(label))


def contract_bindings() -> ContractBindings:
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


def predecessor(
    story: PredecessorStory,
    state: PredecessorState = PredecessorState.AVAILABLE,
) -> PredecessorAssessment:
    suffix = story.value.replace("-", "_")
    return PredecessorAssessment(
        story_id=story,
        article_version_id=ARTICLE_VERSION_ID,
        state=state,
        result=(
            bound(f"RESULT-{suffix}") if state is PredecessorState.AVAILABLE else None
        ),
        provenance=bound(f"PROVENANCE-{suffix}"),
    )


def policy_assessment(
    policy_id: str,
    result: PolicyRuleResult = PolicyRuleResult.PASS,
) -> PolicyAssessment:
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
        result=result,
        target=FindingTarget(FindingTargetType.ARTICLE_VERSION, ARTICLE_VERSION_ID),
        evidence=(bound(f"EVIDENCE-POLICY-{suffix}"),)
        if result is not PolicyRuleResult.NOT_EVALUATED
        else (),
        detector=bound(f"DETECTOR-POLICY-{suffix}"),
    )


def axis_assessment(
    axis_id: str,
    *,
    score: Decimal | None = None,
    state: AxisAssessmentState = AxisAssessmentState.EVALUATED,
) -> QualityAxisAssessment:
    definition = next(
        item for item in QUALITY_AXIS_DEFINITIONS if item.axis_id == axis_id
    )
    selected_score = definition.weight if score is None else score
    suffix = axis_id.removeprefix("QAX-")
    return QualityAxisAssessment(
        axis_id=axis_id,
        axis_code=definition.code,
        quality_model_version=VersionRef(QUALITY_MODEL_VERSION),
        quality_source_sha256=Sha256Digest(QUALITY_CATALOG_SHA256),
        article_version_id=ARTICLE_VERSION_ID,
        state=state,
        score=selected_score if state is AxisAssessmentState.EVALUATED else None,
        evidence=(bound(f"EVIDENCE-AXIS-{suffix}"),)
        if state is AxisAssessmentState.EVALUATED
        else (),
        evaluator=bound(f"EVALUATOR-AXIS-{suffix}"),
    )


def signal_assessment(
    label: str,
    state: ZeroToleranceState = ZeroToleranceState.CLEAR,
) -> ZeroToleranceAssessment:
    index = ZERO_TOLERANCE_LABELS.index(label) + 1
    suffix = f"{index:03d}"
    return ZeroToleranceAssessment(
        label=label,
        article_version_id=ARTICLE_VERSION_ID,
        state=state,
        evidence=(bound(f"EVIDENCE-SIGNAL-{suffix}"),)
        if state is not ZeroToleranceState.NOT_EVALUATED
        else (),
        detector=bound(f"DETECTOR-SIGNAL-{suffix}"),
    )


def gate_assessment(
    gate_id: str,
    state: GateAssessmentState = GateAssessmentState.PASS,
) -> QualityGateAssessment:
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
        state=state,
        failure_action=definition.failure_action,
        evidence=(bound(f"EVIDENCE-GATE-{suffix}"),)
        if state is not GateAssessmentState.NOT_EVALUATED
        else (),
        evaluator=bound(f"EVALUATOR-GATE-{suffix}"),
    )


def waiver_attempt(policy_id: str) -> WaiverAttempt:
    suffix = policy_id.removeprefix("POL-CONT-")
    return WaiverAttempt(
        policy_id=policy_id,
        policy_version=VersionRef(POLICY_CATALOG_VERSION),
        policy_source_sha256=Sha256Digest(POLICY_CATALOG_SHA256),
        article_version_id=ARTICLE_VERSION_ID,
        scope_type=WaiverScopeType.ARTICLE_VERSION,
        scope_ref=ARTICLE_VERSION_ID,
        reason=bound(f"REASON-REF-{suffix}"),
        evidence=(bound(f"WAIVER-EVIDENCE-{suffix}"),),
        expiry_at=UtcInstant(datetime(2026, 9, 30, 0, 0, tzinfo=timezone.utc)),
        compliance_approver=bound(f"COMPLIANCE-APPROVER-{suffix}"),
        audit_event=bound(f"AUDIT-EVENT-{suffix}"),
        authority_claim=WaiverAuthorityClaim.REQUESTED,
    )


def valid_policy_input() -> PolicyEvaluationInput:
    return PolicyEvaluationInput(
        article_version_id=ARTICLE_VERSION_ID,
        evaluated_at=EVALUATED_AT,
        contracts=contract_bindings(),
        predecessors=tuple(predecessor(story) for story in PredecessorStory),
        policy_assessments=tuple(
            policy_assessment(definition.policy_id) for definition in POLICY_DEFINITIONS
        ),
        axis_assessments=tuple(
            axis_assessment(definition.axis_id)
            for definition in QUALITY_AXIS_DEFINITIONS
        ),
        zero_tolerance_assessments=tuple(
            signal_assessment(label) for label in ZERO_TOLERANCE_LABELS
        ),
        gate_assessments=tuple(
            gate_assessment(definition.gate_id)
            for definition in QUALITY_GATE_DEFINITIONS
        ),
        waiver_attempts=(),
    )


def with_policy_result(
    value: PolicyEvaluationInput,
    policy_id: str,
    result: PolicyRuleResult,
) -> PolicyEvaluationInput:
    return replace(
        value,
        policy_assessments=tuple(
            policy_assessment(policy_id, result)
            if record.policy_id == policy_id
            else record
            for record in value.policy_assessments
        ),
    )


def with_axis_score(
    value: PolicyEvaluationInput,
    axis_id: str,
    score: Decimal,
) -> PolicyEvaluationInput:
    return replace(
        value,
        axis_assessments=tuple(
            axis_assessment(axis_id, score=score)
            if record.axis_id == axis_id
            else record
            for record in value.axis_assessments
        ),
    )


def with_total_score(total: Decimal) -> PolicyEvaluationInput:
    floor_total = sum(
        (definition.blocking_floor for definition in QUALITY_AXIS_DEFINITIONS),
        Decimal("0"),
    )
    if total < floor_total or total > Decimal("100"):
        raise ValueError("unsupported test total")
    remaining = total - floor_total
    scores: dict[str, Decimal] = {}
    for definition in QUALITY_AXIS_DEFINITIONS:
        capacity = definition.weight - definition.blocking_floor
        increment = min(capacity, remaining)
        scores[definition.axis_id] = definition.blocking_floor + increment
        remaining -= increment
    assert remaining == 0
    return replace(
        valid_policy_input(),
        axis_assessments=tuple(
            axis_assessment(definition.axis_id, score=scores[definition.axis_id])
            for definition in QUALITY_AXIS_DEFINITIONS
        ),
    )


def with_signal_state(
    value: PolicyEvaluationInput,
    label: str,
    state: ZeroToleranceState,
) -> PolicyEvaluationInput:
    return replace(
        value,
        zero_tolerance_assessments=tuple(
            signal_assessment(label, state) if record.label == label else record
            for record in value.zero_tolerance_assessments
        ),
    )


def with_gate_state(
    value: PolicyEvaluationInput,
    gate_id: str,
    state: GateAssessmentState,
) -> PolicyEvaluationInput:
    return replace(
        value,
        gate_assessments=tuple(
            gate_assessment(gate_id, state) if record.gate_id == gate_id else record
            for record in value.gate_assessments
        ),
    )


def with_predecessor_state(
    value: PolicyEvaluationInput,
    story: PredecessorStory,
    state: PredecessorState,
) -> PolicyEvaluationInput:
    return replace(
        value,
        predecessors=tuple(
            predecessor(story, state) if record.story_id is story else record
            for record in value.predecessors
        ),
    )


def with_waiver(
    value: PolicyEvaluationInput,
    policy_id: str,
) -> PolicyEvaluationInput:
    return replace(value, waiver_attempts=(waiver_attempt(policy_id),))


def reverse_collections(value: PolicyEvaluationInput) -> PolicyEvaluationInput:
    return replace(
        value,
        predecessors=tuple(reversed(value.predecessors)),
        policy_assessments=tuple(reversed(value.policy_assessments)),
        axis_assessments=tuple(reversed(value.axis_assessments)),
        zero_tolerance_assessments=tuple(reversed(value.zero_tolerance_assessments)),
        gate_assessments=tuple(reversed(value.gate_assessments)),
        waiver_attempts=tuple(reversed(value.waiver_attempts)),
    )
