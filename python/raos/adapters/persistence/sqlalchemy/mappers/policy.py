"""Explicit fail-closed scalar mappers for the POLICY ST-0308 slice."""

from __future__ import annotations

from decimal import Decimal

from raos.adapters.persistence.sqlalchemy.physical_constraints import (
    install_mapper_physical_constraint_guards,
)
from raos.domain.editorial.ids import (
    ArticleBlockId,
    ArticleVersionId,
)
from raos.domain.evidence.ids import (
    ClaimId,
    SourcePacketVersionId,
)
from raos.domain.iam.ids import (
    PrincipalId,
)
from raos.domain.ops.ids import (
    ObjectArtifactId,
)
from raos.domain.policy.aggregates import (
    BundleRuleBinding,
    FindingState,
    GateDecisionState,
    PolicyBundleState,
    QualityCheckRunState,
    QualityScore,
    RuleVersionState,
    WaiverState,
)
from raos.domain.policy.enums import (
    BundleRuleBindingMode,
    FindingEntityType,
    FindingSeverity,
    FindingStatus,
    GateDecisionGateCode,
    GateDecisionResult,
    GateDecisionScopeType,
    PolicyBundleStatus,
    QualityCheckRunStatus,
    QualityCheckRunTriggeredByActorType,
    RuleVersionImplementationType,
    RuleVersionRuleCategory,
    RuleVersionSeverity,
    RuleVersionStatus,
    WaiverScopeType,
    WaiverStatus,
)
from raos.domain.policy.ids import (
    FindingId,
    GateDecisionId,
    PolicyBundleId,
    QualityCheckRunId,
    QualityScoreId,
    RuleVersionId,
    WaiverId,
)
from raos.domain.policy.values import (
    FindingEvidenceJson,
    GateDecisionConditionsJson,
    QualityScoreComponentsJson,
    RuleVersionDefinitionJson,
)
from raos.domain.shared.identity import (
    EntityId,
    ScopeId,
    TriggeredByActorId,
)
from raos.domain.shared.persistence import (
    AwareUtcDateTime,
    Sha256Digest,
)
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


def _corrupt() -> PersistenceError:
    return PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION)


BundleRuleBindingScalars = tuple[
    PolicyBundleId,
    RuleVersionId,
    int,
    BundleRuleBindingMode,
    AwareUtcDateTime,
]


def map_policy_bundle_rule_from_row(
    *,
    policy_bundle_id: PolicyBundleId,
    rule_version_id: RuleVersionId,
    execution_order: int,
    mode: BundleRuleBindingMode,
    created_at: AwareUtcDateTime,
) -> BundleRuleBinding:
    try:
        return BundleRuleBinding(
            policy_bundle_id=policy_bundle_id,
            rule_version_id=rule_version_id,
            execution_order=execution_order,
            mode=mode,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_policy_bundle_rule_to_row(value: BundleRuleBinding) -> BundleRuleBindingScalars:
    if type(value) is not BundleRuleBinding:
        raise _corrupt() from None
    return (
        value.policy_bundle_id,
        value.rule_version_id,
        value.execution_order,
        value.mode,
        value.created_at,
    )


FindingStateScalars = tuple[
    FindingId,
    QualityCheckRunId,
    RuleVersionId,
    str,
    FindingSeverity,
    bool,
    FindingEntityType,
    EntityId | None,
    ArticleBlockId | None,
    ClaimId | None,
    str,
    FindingEvidenceJson,
    FindingStatus,
    AwareUtcDateTime | None,
    PrincipalId | None,
    AwareUtcDateTime,
]


def map_policy_finding_from_row(
    *,
    id: FindingId,
    quality_check_run_id: QualityCheckRunId,
    rule_version_id: RuleVersionId,
    finding_code: str,
    severity: FindingSeverity,
    is_blocking: bool,
    entity_type: FindingEntityType,
    entity_id: EntityId | None,
    article_block_id: ArticleBlockId | None,
    claim_id: ClaimId | None,
    message: str,
    evidence: FindingEvidenceJson,
    status: FindingStatus,
    resolved_at: AwareUtcDateTime | None,
    resolved_by_principal_id: PrincipalId | None,
    created_at: AwareUtcDateTime,
) -> FindingState:
    try:
        return FindingState(
            id=id,
            quality_check_run_id=quality_check_run_id,
            rule_version_id=rule_version_id,
            finding_code=finding_code,
            severity=severity,
            is_blocking=is_blocking,
            entity_type=entity_type,
            entity_id=entity_id,
            article_block_id=article_block_id,
            claim_id=claim_id,
            message=message,
            evidence=evidence,
            status=status,
            resolved_at=resolved_at,
            resolved_by_principal_id=resolved_by_principal_id,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_policy_finding_to_row(value: FindingState) -> FindingStateScalars:
    if type(value) is not FindingState:
        raise _corrupt() from None
    return (
        value.id,
        value.quality_check_run_id,
        value.rule_version_id,
        value.finding_code,
        value.severity,
        value.is_blocking,
        value.entity_type,
        value.entity_id,
        value.article_block_id,
        value.claim_id,
        value.message,
        value.evidence,
        value.status,
        value.resolved_at,
        value.resolved_by_principal_id,
        value.created_at,
    )


GateDecisionStateScalars = tuple[
    GateDecisionId,
    str,
    GateDecisionGateCode,
    GateDecisionScopeType,
    ScopeId,
    PolicyBundleId,
    GateDecisionResult,
    GateDecisionConditionsJson,
    ObjectArtifactId,
    PrincipalId,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_policy_gate_decision_from_row(
    *,
    id: GateDecisionId,
    display_id: str,
    gate_code: GateDecisionGateCode,
    scope_type: GateDecisionScopeType,
    scope_id: ScopeId,
    policy_bundle_id: PolicyBundleId,
    result: GateDecisionResult,
    conditions: GateDecisionConditionsJson,
    evidence_artifact_id: ObjectArtifactId,
    decided_by_principal_id: PrincipalId,
    decided_at: AwareUtcDateTime,
    expires_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> GateDecisionState:
    try:
        return GateDecisionState(
            id=id,
            display_id=display_id,
            gate_code=gate_code,
            scope_type=scope_type,
            scope_id=scope_id,
            policy_bundle_id=policy_bundle_id,
            result=result,
            conditions=conditions,
            evidence_artifact_id=evidence_artifact_id,
            decided_by_principal_id=decided_by_principal_id,
            decided_at=decided_at,
            expires_at=expires_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_policy_gate_decision_to_row(
    value: GateDecisionState,
) -> GateDecisionStateScalars:
    if type(value) is not GateDecisionState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.gate_code,
        value.scope_type,
        value.scope_id,
        value.policy_bundle_id,
        value.result,
        value.conditions,
        value.evidence_artifact_id,
        value.decided_by_principal_id,
        value.decided_at,
        value.expires_at,
        value.created_at,
    )


PolicyBundleStateScalars = tuple[
    PolicyBundleId,
    str,
    str,
    int,
    PolicyBundleStatus,
    str,
    Sha256Digest,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    PrincipalId | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_policy_policy_bundle_from_row(
    *,
    id: PolicyBundleId,
    display_id: str,
    bundle_code: str,
    version_no: int,
    status: PolicyBundleStatus,
    git_commit_sha: str,
    bundle_sha256: Sha256Digest,
    effective_from: AwareUtcDateTime | None,
    effective_to: AwareUtcDateTime | None,
    approved_by_principal_id: PrincipalId | None,
    approved_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> PolicyBundleState:
    try:
        return PolicyBundleState(
            id=id,
            display_id=display_id,
            bundle_code=bundle_code,
            version_no=version_no,
            status=status,
            git_commit_sha=git_commit_sha,
            bundle_sha256=bundle_sha256,
            effective_from=effective_from,
            effective_to=effective_to,
            approved_by_principal_id=approved_by_principal_id,
            approved_at=approved_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_policy_policy_bundle_to_row(
    value: PolicyBundleState,
) -> PolicyBundleStateScalars:
    if type(value) is not PolicyBundleState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.bundle_code,
        value.version_no,
        value.status,
        value.git_commit_sha,
        value.bundle_sha256,
        value.effective_from,
        value.effective_to,
        value.approved_by_principal_id,
        value.approved_at,
        value.created_at,
    )


QualityCheckRunStateScalars = tuple[
    QualityCheckRunId,
    str,
    ArticleVersionId,
    SourcePacketVersionId,
    PolicyBundleId,
    QualityCheckRunStatus,
    QualityCheckRunTriggeredByActorType,
    TriggeredByActorId | None,
    AwareUtcDateTime,
    AwareUtcDateTime | None,
    Decimal | None,
    int,
    ObjectArtifactId | None,
    AwareUtcDateTime,
]


def map_policy_quality_check_run_from_row(
    *,
    id: QualityCheckRunId,
    display_id: str,
    article_version_id: ArticleVersionId,
    source_packet_version_id: SourcePacketVersionId,
    policy_bundle_id: PolicyBundleId,
    status: QualityCheckRunStatus,
    triggered_by_actor_type: QualityCheckRunTriggeredByActorType,
    triggered_by_actor_id: TriggeredByActorId | None,
    started_at: AwareUtcDateTime,
    completed_at: AwareUtcDateTime | None,
    total_score: Decimal | None,
    blocking_finding_count: int,
    report_artifact_id: ObjectArtifactId | None,
    created_at: AwareUtcDateTime,
) -> QualityCheckRunState:
    try:
        return QualityCheckRunState(
            id=id,
            display_id=display_id,
            article_version_id=article_version_id,
            source_packet_version_id=source_packet_version_id,
            policy_bundle_id=policy_bundle_id,
            status=status,
            triggered_by_actor_type=triggered_by_actor_type,
            triggered_by_actor_id=triggered_by_actor_id,
            started_at=started_at,
            completed_at=completed_at,
            total_score=total_score,
            blocking_finding_count=blocking_finding_count,
            report_artifact_id=report_artifact_id,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_policy_quality_check_run_to_row(
    value: QualityCheckRunState,
) -> QualityCheckRunStateScalars:
    if type(value) is not QualityCheckRunState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.article_version_id,
        value.source_packet_version_id,
        value.policy_bundle_id,
        value.status,
        value.triggered_by_actor_type,
        value.triggered_by_actor_id,
        value.started_at,
        value.completed_at,
        value.total_score,
        value.blocking_finding_count,
        value.report_artifact_id,
        value.created_at,
    )


QualityScoreScalars = tuple[
    QualityScoreId,
    QualityCheckRunId,
    str,
    Decimal,
    Decimal,
    Decimal,
    Decimal,
    bool,
    QualityScoreComponentsJson,
    AwareUtcDateTime,
]


def map_policy_quality_score_from_row(
    *,
    id: QualityScoreId,
    quality_check_run_id: QualityCheckRunId,
    score_version: str,
    total_score: Decimal,
    pass_score: Decimal,
    factual_accuracy_score: Decimal,
    disclosure_policy_score: Decimal,
    passed: bool,
    components: QualityScoreComponentsJson,
    created_at: AwareUtcDateTime,
) -> QualityScore:
    try:
        return QualityScore(
            id=id,
            quality_check_run_id=quality_check_run_id,
            score_version=score_version,
            total_score=total_score,
            pass_score=pass_score,
            factual_accuracy_score=factual_accuracy_score,
            disclosure_policy_score=disclosure_policy_score,
            passed=passed,
            components=components,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_policy_quality_score_to_row(value: QualityScore) -> QualityScoreScalars:
    if type(value) is not QualityScore:
        raise _corrupt() from None
    return (
        value.id,
        value.quality_check_run_id,
        value.score_version,
        value.total_score,
        value.pass_score,
        value.factual_accuracy_score,
        value.disclosure_policy_score,
        value.passed,
        value.components,
        value.created_at,
    )


RuleVersionStateScalars = tuple[
    RuleVersionId,
    str,
    int,
    RuleVersionRuleCategory,
    RuleVersionSeverity,
    bool,
    RuleVersionImplementationType,
    RuleVersionDefinitionJson,
    Sha256Digest,
    RuleVersionStatus,
    PrincipalId,
    PrincipalId | None,
    AwareUtcDateTime,
]


def map_policy_rule_version_from_row(
    *,
    id: RuleVersionId,
    rule_code: str,
    version_no: int,
    rule_category: RuleVersionRuleCategory,
    severity: RuleVersionSeverity,
    is_blocking: bool,
    implementation_type: RuleVersionImplementationType,
    definition: RuleVersionDefinitionJson,
    definition_sha256: Sha256Digest,
    status: RuleVersionStatus,
    created_by_principal_id: PrincipalId,
    approved_by_principal_id: PrincipalId | None,
    created_at: AwareUtcDateTime,
) -> RuleVersionState:
    try:
        return RuleVersionState(
            id=id,
            rule_code=rule_code,
            version_no=version_no,
            rule_category=rule_category,
            severity=severity,
            is_blocking=is_blocking,
            implementation_type=implementation_type,
            definition=definition,
            definition_sha256=definition_sha256,
            status=status,
            created_by_principal_id=created_by_principal_id,
            approved_by_principal_id=approved_by_principal_id,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_policy_rule_version_to_row(value: RuleVersionState) -> RuleVersionStateScalars:
    if type(value) is not RuleVersionState:
        raise _corrupt() from None
    return (
        value.id,
        value.rule_code,
        value.version_no,
        value.rule_category,
        value.severity,
        value.is_blocking,
        value.implementation_type,
        value.definition,
        value.definition_sha256,
        value.status,
        value.created_by_principal_id,
        value.approved_by_principal_id,
        value.created_at,
    )


WaiverStateScalars = tuple[
    WaiverId,
    str,
    FindingId,
    WaiverScopeType,
    ScopeId,
    str,
    WaiverStatus,
    PrincipalId,
    AwareUtcDateTime,
    PrincipalId | None,
    AwareUtcDateTime | None,
    str | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime | None,
    AwareUtcDateTime,
]


def map_policy_waiver_from_row(
    *,
    id: WaiverId,
    display_id: str,
    finding_id: FindingId,
    scope_type: WaiverScopeType,
    scope_id: ScopeId,
    justification: str,
    status: WaiverStatus,
    requested_by_principal_id: PrincipalId,
    requested_at: AwareUtcDateTime,
    decided_by_principal_id: PrincipalId | None,
    decided_at: AwareUtcDateTime | None,
    decision_reason: str | None,
    expires_at: AwareUtcDateTime | None,
    revoked_at: AwareUtcDateTime | None,
    created_at: AwareUtcDateTime,
) -> WaiverState:
    try:
        return WaiverState(
            id=id,
            display_id=display_id,
            finding_id=finding_id,
            scope_type=scope_type,
            scope_id=scope_id,
            justification=justification,
            status=status,
            requested_by_principal_id=requested_by_principal_id,
            requested_at=requested_at,
            decided_by_principal_id=decided_by_principal_id,
            decided_at=decided_at,
            decision_reason=decision_reason,
            expires_at=expires_at,
            revoked_at=revoked_at,
            created_at=created_at,
        )
    except TypeError, ValueError:
        raise _corrupt() from None


def map_policy_waiver_to_row(value: WaiverState) -> WaiverStateScalars:
    if type(value) is not WaiverState:
        raise _corrupt() from None
    return (
        value.id,
        value.display_id,
        value.finding_id,
        value.scope_type,
        value.scope_id,
        value.justification,
        value.status,
        value.requested_by_principal_id,
        value.requested_at,
        value.decided_by_principal_id,
        value.decided_at,
        value.decision_reason,
        value.expires_at,
        value.revoked_at,
        value.created_at,
    )


__all__ = [
    "map_policy_bundle_rule_from_row",
    "map_policy_bundle_rule_to_row",
    "map_policy_finding_from_row",
    "map_policy_finding_to_row",
    "map_policy_gate_decision_from_row",
    "map_policy_gate_decision_to_row",
    "map_policy_policy_bundle_from_row",
    "map_policy_policy_bundle_to_row",
    "map_policy_quality_check_run_from_row",
    "map_policy_quality_check_run_to_row",
    "map_policy_quality_score_from_row",
    "map_policy_quality_score_to_row",
    "map_policy_rule_version_from_row",
    "map_policy_rule_version_to_row",
    "map_policy_waiver_from_row",
    "map_policy_waiver_to_row",
]

install_mapper_physical_constraint_guards(globals())
