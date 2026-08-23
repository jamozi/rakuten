"""Explicit POLICY relation states and aggregate compositions for ST-0308."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
import re
from typing import ClassVar, NoReturn
from uuid import UUID

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
from raos.domain.shared.events import DomainEvent
from raos.domain.shared.persistence import PendingEventBuffer


_MAX_BIGINT = (1 << 63) - 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_GIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)


def _invalid() -> NoReturn:
    raise ValueError("INVALID_POLICY_PERSISTENCE_VALUE") from None


def _order_value(value: object) -> object:
    if isinstance(value, EntityId):
        return value.value.int
    if isinstance(value, Enum):
        return value.value
    if type(value) is AwareUtcDateTime:
        return value.value
    return value


@dataclass(frozen=True, slots=True, repr=False)
class BundleRuleBinding:
    """Exact scalar state for relation policy.bundle_rule."""

    RELATION: ClassVar[str] = "policy.bundle_rule"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_policy_bundle_rule_mode",
        "ck_policy_bundle_rule_order",
    )
    policy_bundle_id: PolicyBundleId
    rule_version_id: RuleVersionId
    execution_order: int
    mode: BundleRuleBindingMode
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.policy_bundle_id) is not PolicyBundleId:
            _invalid()
        if type(self.rule_version_id) is not RuleVersionId:
            _invalid()
        if (
            type(self.execution_order) is not int
            or not -_MAX_BIGINT <= self.execution_order <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.mode) is not BundleRuleBindingMode:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.execution_order < 0:
            _invalid()

    def __repr__(self) -> str:
        return "BundleRuleBinding(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class FindingState:
    """Exact scalar state for relation policy.finding."""

    RELATION: ClassVar[str] = "policy.finding"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_policy_finding_entity",
        "ck_policy_finding_evidence",
        "ck_policy_finding_resolve_pair",
        "ck_policy_finding_severity",
        "ck_policy_finding_status",
    )
    id: FindingId
    quality_check_run_id: QualityCheckRunId
    rule_version_id: RuleVersionId
    finding_code: str
    severity: FindingSeverity
    is_blocking: bool
    entity_type: FindingEntityType
    entity_id: EntityId | None
    article_block_id: ArticleBlockId | None
    claim_id: ClaimId | None
    message: str
    evidence: FindingEvidenceJson
    status: FindingStatus
    resolved_at: AwareUtcDateTime | None
    resolved_by_principal_id: PrincipalId | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not FindingId:
            _invalid()
        if type(self.quality_check_run_id) is not QualityCheckRunId:
            _invalid()
        if type(self.rule_version_id) is not RuleVersionId:
            _invalid()
        if type(self.finding_code) is not str:
            _invalid()
        if type(self.severity) is not FindingSeverity:
            _invalid()
        if type(self.is_blocking) is not bool:
            _invalid()
        if type(self.entity_type) is not FindingEntityType:
            _invalid()
        if self.entity_id is not None and (type(self.entity_id) is not EntityId):
            _invalid()
        if self.article_block_id is not None and (
            type(self.article_block_id) is not ArticleBlockId
        ):
            _invalid()
        if self.claim_id is not None and (type(self.claim_id) is not ClaimId):
            _invalid()
        if type(self.message) is not str:
            _invalid()
        if type(self.evidence) is not FindingEvidenceJson:
            _invalid()
        if type(self.status) is not FindingStatus:
            _invalid()
        if self.resolved_at is not None and (
            type(self.resolved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.resolved_by_principal_id is not None and (
            type(self.resolved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if (self.resolved_at is None) != (self.resolved_by_principal_id is None):
            _invalid()

    def __repr__(self) -> str:
        return "FindingState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class GateDecisionState:
    """Exact scalar state for relation policy.gate_decision."""

    RELATION: ClassVar[str] = "policy.gate_decision"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_policy_gate_code",
        "ck_policy_gate_conditions",
        "ck_policy_gate_expiry",
        "ck_policy_gate_result",
        "ck_policy_gate_scope",
    )
    id: GateDecisionId
    display_id: str
    gate_code: GateDecisionGateCode
    scope_type: GateDecisionScopeType
    scope_id: ScopeId
    policy_bundle_id: PolicyBundleId
    result: GateDecisionResult
    conditions: GateDecisionConditionsJson
    evidence_artifact_id: ObjectArtifactId
    decided_by_principal_id: PrincipalId
    decided_at: AwareUtcDateTime
    expires_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not GateDecisionId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.gate_code) is not GateDecisionGateCode:
            _invalid()
        if type(self.scope_type) is not GateDecisionScopeType:
            _invalid()
        if type(self.scope_id) is not ScopeId:
            _invalid()
        if type(self.policy_bundle_id) is not PolicyBundleId:
            _invalid()
        if type(self.result) is not GateDecisionResult:
            _invalid()
        if type(self.conditions) is not GateDecisionConditionsJson:
            _invalid()
        if type(self.evidence_artifact_id) is not ObjectArtifactId:
            _invalid()
        if type(self.decided_by_principal_id) is not PrincipalId:
            _invalid()
        if type(self.decided_at) is not AwareUtcDateTime:
            _invalid()
        if self.expires_at is not None and (
            type(self.expires_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.expires_at is not None and (
            not self.expires_at.value > self.decided_at.value
        ):
            _invalid()

    def __repr__(self) -> str:
        return "GateDecisionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class PolicyBundleState:
    """Exact scalar state for relation policy.policy_bundle."""

    RELATION: ClassVar[str] = "policy.policy_bundle"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_policy_bundle_approval",
        "ck_policy_bundle_git",
        "ck_policy_bundle_hash",
        "ck_policy_bundle_status",
        "ck_policy_bundle_version",
        "ck_policy_bundle_window",
    )
    id: PolicyBundleId
    display_id: str
    bundle_code: str
    version_no: int
    status: PolicyBundleStatus
    git_commit_sha: str
    bundle_sha256: Sha256Digest
    effective_from: AwareUtcDateTime | None
    effective_to: AwareUtcDateTime | None
    approved_by_principal_id: PrincipalId | None
    approved_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not PolicyBundleId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.bundle_code) is not str:
            _invalid()
        if (
            type(self.version_no) is not int
            or not -_MAX_BIGINT <= self.version_no <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.status) is not PolicyBundleStatus:
            _invalid()
        if type(self.git_commit_sha) is not str:
            _invalid()
        if type(self.bundle_sha256) is not Sha256Digest:
            _invalid()
        if self.effective_from is not None and (
            type(self.effective_from) is not AwareUtcDateTime
        ):
            _invalid()
        if self.effective_to is not None and (
            type(self.effective_to) is not AwareUtcDateTime
        ):
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.approved_at is not None and (
            type(self.approved_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if _GIT.fullmatch(self.git_commit_sha) is None:
            _invalid()
        if (
            self.effective_to is not None
            and self.effective_from is not None
            and (not self.effective_to.value > self.effective_from.value)
        ):
            _invalid()

    def __repr__(self) -> str:
        return "PolicyBundleState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class QualityCheckRunState:
    """Exact scalar state for relation policy.quality_check_run."""

    RELATION: ClassVar[str] = "policy.quality_check_run"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_policy_check_actor",
        "ck_policy_check_blocking",
        "ck_policy_check_complete",
        "ck_policy_check_score",
        "ck_policy_check_status",
    )
    id: QualityCheckRunId
    display_id: str
    article_version_id: ArticleVersionId
    source_packet_version_id: SourcePacketVersionId
    policy_bundle_id: PolicyBundleId
    status: QualityCheckRunStatus
    triggered_by_actor_type: QualityCheckRunTriggeredByActorType
    triggered_by_actor_id: TriggeredByActorId | None
    started_at: AwareUtcDateTime
    completed_at: AwareUtcDateTime | None
    total_score: Decimal | None
    blocking_finding_count: int
    report_artifact_id: ObjectArtifactId | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not QualityCheckRunId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.article_version_id) is not ArticleVersionId:
            _invalid()
        if type(self.source_packet_version_id) is not SourcePacketVersionId:
            _invalid()
        if type(self.policy_bundle_id) is not PolicyBundleId:
            _invalid()
        if type(self.status) is not QualityCheckRunStatus:
            _invalid()
        if (
            type(self.triggered_by_actor_type)
            is not QualityCheckRunTriggeredByActorType
        ):
            _invalid()
        if self.triggered_by_actor_id is not None and (
            type(self.triggered_by_actor_id) is not TriggeredByActorId
        ):
            _invalid()
        if type(self.started_at) is not AwareUtcDateTime:
            _invalid()
        if self.completed_at is not None and (
            type(self.completed_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.total_score is not None and (
            type(self.total_score) is not Decimal or not self.total_score.is_finite()
        ):
            _invalid()
        if (
            type(self.blocking_finding_count) is not int
            or not -_MAX_BIGINT <= self.blocking_finding_count <= _MAX_BIGINT
        ):
            _invalid()
        if self.report_artifact_id is not None and (
            type(self.report_artifact_id) is not ObjectArtifactId
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.total_score is not None and self.total_score < 0:
            _invalid()
        if self.blocking_finding_count < 0:
            _invalid()

    def __repr__(self) -> str:
        return "QualityCheckRunState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class QualityScore:
    """Exact scalar state for relation policy.quality_score."""

    RELATION: ClassVar[str] = "policy.quality_score"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_policy_score_components",
        "ck_policy_score_disclosure",
        "ck_policy_score_factual",
        "ck_policy_score_pass",
        "ck_policy_score_pass_logic",
        "ck_policy_score_total",
    )
    id: QualityScoreId
    quality_check_run_id: QualityCheckRunId
    score_version: str
    total_score: Decimal
    pass_score: Decimal
    factual_accuracy_score: Decimal
    disclosure_policy_score: Decimal
    passed: bool
    components: QualityScoreComponentsJson
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not QualityScoreId:
            _invalid()
        if type(self.quality_check_run_id) is not QualityCheckRunId:
            _invalid()
        if type(self.score_version) is not str:
            _invalid()
        if type(self.total_score) is not Decimal or not self.total_score.is_finite():
            _invalid()
        if type(self.pass_score) is not Decimal or not self.pass_score.is_finite():
            _invalid()
        if (
            type(self.factual_accuracy_score) is not Decimal
            or not self.factual_accuracy_score.is_finite()
        ):
            _invalid()
        if (
            type(self.disclosure_policy_score) is not Decimal
            or not self.disclosure_policy_score.is_finite()
        ):
            _invalid()
        if type(self.passed) is not bool:
            _invalid()
        if type(self.components) is not QualityScoreComponentsJson:
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.total_score < 0:
            _invalid()
        if self.pass_score < 0:
            _invalid()
        if self.factual_accuracy_score < 0:
            _invalid()
        if self.disclosure_policy_score < 0:
            _invalid()

    def __repr__(self) -> str:
        return "QualityScore(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RuleVersionState:
    """Exact scalar state for relation policy.rule_version."""

    RELATION: ClassVar[str] = "policy.rule_version"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_policy_rule_category",
        "ck_policy_rule_definition",
        "ck_policy_rule_hash",
        "ck_policy_rule_impl",
        "ck_policy_rule_severity",
        "ck_policy_rule_status",
        "ck_policy_rule_version",
    )
    id: RuleVersionId
    rule_code: str
    version_no: int
    rule_category: RuleVersionRuleCategory
    severity: RuleVersionSeverity
    is_blocking: bool
    implementation_type: RuleVersionImplementationType
    definition: RuleVersionDefinitionJson
    definition_sha256: Sha256Digest
    status: RuleVersionStatus
    created_by_principal_id: PrincipalId
    approved_by_principal_id: PrincipalId | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not RuleVersionId:
            _invalid()
        if type(self.rule_code) is not str:
            _invalid()
        if (
            type(self.version_no) is not int
            or not -_MAX_BIGINT <= self.version_no <= _MAX_BIGINT
        ):
            _invalid()
        if type(self.rule_category) is not RuleVersionRuleCategory:
            _invalid()
        if type(self.severity) is not RuleVersionSeverity:
            _invalid()
        if type(self.is_blocking) is not bool:
            _invalid()
        if type(self.implementation_type) is not RuleVersionImplementationType:
            _invalid()
        if type(self.definition) is not RuleVersionDefinitionJson:
            _invalid()
        if type(self.definition_sha256) is not Sha256Digest:
            _invalid()
        if type(self.status) is not RuleVersionStatus:
            _invalid()
        if type(self.created_by_principal_id) is not PrincipalId:
            _invalid()
        if self.approved_by_principal_id is not None and (
            type(self.approved_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()

    def __repr__(self) -> str:
        return "RuleVersionState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class WaiverState:
    """Exact scalar state for relation policy.waiver."""

    RELATION: ClassVar[str] = "policy.waiver"
    PHYSICAL_CHECKS: ClassVar[tuple[str, ...]] = (
        "ck_policy_waiver_decision_pair",
        "ck_policy_waiver_expiry",
        "ck_policy_waiver_scope",
        "ck_policy_waiver_status",
    )
    id: WaiverId
    display_id: str
    finding_id: FindingId
    scope_type: WaiverScopeType
    scope_id: ScopeId
    justification: str
    status: WaiverStatus
    requested_by_principal_id: PrincipalId
    requested_at: AwareUtcDateTime
    decided_by_principal_id: PrincipalId | None
    decided_at: AwareUtcDateTime | None
    decision_reason: str | None
    expires_at: AwareUtcDateTime | None
    revoked_at: AwareUtcDateTime | None
    created_at: AwareUtcDateTime

    def __post_init__(self) -> None:
        if type(self.id) is not WaiverId:
            _invalid()
        if type(self.display_id) is not str:
            _invalid()
        if type(self.finding_id) is not FindingId:
            _invalid()
        if type(self.scope_type) is not WaiverScopeType:
            _invalid()
        if type(self.scope_id) is not ScopeId:
            _invalid()
        if type(self.justification) is not str:
            _invalid()
        if type(self.status) is not WaiverStatus:
            _invalid()
        if type(self.requested_by_principal_id) is not PrincipalId:
            _invalid()
        if type(self.requested_at) is not AwareUtcDateTime:
            _invalid()
        if self.decided_by_principal_id is not None and (
            type(self.decided_by_principal_id) is not PrincipalId
        ):
            _invalid()
        if self.decided_at is not None and (
            type(self.decided_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.decision_reason is not None and (type(self.decision_reason) is not str):
            _invalid()
        if self.expires_at is not None and (
            type(self.expires_at) is not AwareUtcDateTime
        ):
            _invalid()
        if self.revoked_at is not None and (
            type(self.revoked_at) is not AwareUtcDateTime
        ):
            _invalid()
        if type(self.created_at) is not AwareUtcDateTime:
            _invalid()
        if self.expires_at is not None and (
            not self.expires_at.value > self.requested_at.value
        ):
            _invalid()

    def __repr__(self) -> str:
        return "WaiverState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Finding:
    state: FindingState

    def __post_init__(self) -> None:
        if type(self.state) is not FindingState:
            _invalid()

    def __repr__(self) -> str:
        return "Finding(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class GateDecision:
    state: GateDecisionState

    def __post_init__(self) -> None:
        if type(self.state) is not GateDecisionState:
            _invalid()

    def __repr__(self) -> str:
        return "GateDecision(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class PolicyBundle:
    state: PolicyBundleState
    bundle_rule_rows: tuple[BundleRuleBinding, ...] = ()
    _events: PendingEventBuffer[DomainEvent] = field(
        default_factory=PendingEventBuffer, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if type(self.state) is not PolicyBundleState:
            _invalid()
        if type(self.bundle_rule_rows) is not tuple or any(
            type(item) is not BundleRuleBinding for item in self.bundle_rule_rows
        ):
            _invalid()
        if self.bundle_rule_rows != tuple(
            sorted(
                self.bundle_rule_rows,
                key=lambda item: (
                    _order_value(item.policy_bundle_id),
                    _order_value(item.rule_version_id),
                ),
            )
        ):
            _invalid()
        if type(self._events) is not PendingEventBuffer:
            _invalid()

    def pending_events(self) -> tuple[DomainEvent, ...]:
        return self._events.pending_events()

    def acknowledge_events(self, event_ids: tuple[UUID, ...]) -> None:
        self._events.acknowledge_events(event_ids)

    def _record_event(self, event: DomainEvent) -> None:
        self._events.record(event)

    def _restore_acknowledged_events(self) -> None:
        self._events._restore_acknowledged()

    def _finish_acknowledged_events(self) -> None:
        self._events._finish_acknowledged()

    def __repr__(self) -> str:
        return "PolicyBundle(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class QualityCheckRun:
    state: QualityCheckRunState
    quality_score_rows: tuple[QualityScore, ...] = ()

    def __post_init__(self) -> None:
        if type(self.state) is not QualityCheckRunState:
            _invalid()
        if type(self.quality_score_rows) is not tuple or any(
            type(item) is not QualityScore for item in self.quality_score_rows
        ):
            _invalid()
        if self.quality_score_rows != tuple(
            sorted(self.quality_score_rows, key=lambda item: (_order_value(item.id),))
        ):
            _invalid()

    def __repr__(self) -> str:
        return "QualityCheckRun(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RuleVersion:
    state: RuleVersionState

    def __post_init__(self) -> None:
        if type(self.state) is not RuleVersionState:
            _invalid()

    def __repr__(self) -> str:
        return "RuleVersion(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Waiver:
    state: WaiverState

    def __post_init__(self) -> None:
        if type(self.state) is not WaiverState:
            _invalid()

    def __repr__(self) -> str:
        return "Waiver(<redacted>)"


__all__ = [
    "BundleRuleBinding",
    "Finding",
    "FindingState",
    "GateDecision",
    "GateDecisionState",
    "PolicyBundle",
    "PolicyBundleState",
    "QualityCheckRun",
    "QualityCheckRunState",
    "QualityScore",
    "RuleVersion",
    "RuleVersionState",
    "Waiver",
    "WaiverState",
]
