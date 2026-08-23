"""Exact aggregate-specific POLICY Repository Protocols for ST-0308."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.policy.aggregates import (
    BundleRuleBinding,
    Finding,
    GateDecision,
    PolicyBundle,
    QualityCheckRun,
    QualityScore,
    RuleVersion,
    Waiver,
)
from raos.domain.policy.enums import (
    FindingStatus,
    PolicyBundleStatus,
    QualityCheckRunStatus,
    RuleVersionStatus,
    WaiverStatus,
)
from raos.domain.policy.ids import (
    FindingId,
    GateDecisionId,
    PolicyBundleId,
    QualityCheckRunId,
    RuleVersionId,
    WaiverId,
)
from raos.domain.shared.persistence import (
    AwareUtcDateTime,
    PersistedVersion,
)


@runtime_checkable
class PolicyBundleRepository(Protocol):
    def get(self, bundle_id: PolicyBundleId) -> PolicyBundle | None: ...

    def get_active(self, bundle_code: str) -> PolicyBundle | None: ...

    def append_version(
        self,
        bundle: PolicyBundle,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def bind_rules(
        self,
        bundle_id: PolicyBundleId,
        bindings: tuple[BundleRuleBinding, ...],
        expected_status: PolicyBundleStatus,
    ) -> None: ...

    def transition(
        self,
        bundle_id: PolicyBundleId,
        transition: PolicyBundle,
        expected_status: PolicyBundleStatus,
    ) -> PolicyBundle: ...


@runtime_checkable
class RuleVersionRepository(Protocol):
    def get(self, rule_id: RuleVersionId) -> RuleVersion | None: ...

    def get_current(self, rule_code: str) -> RuleVersion | None: ...

    def append_version(
        self,
        rule: RuleVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion: ...

    def transition(
        self,
        rule_id: RuleVersionId,
        transition: RuleVersion,
        expected_status: RuleVersionStatus,
    ) -> RuleVersion: ...


@runtime_checkable
class QualityCheckRunRepository(Protocol):
    def get(self, run_id: QualityCheckRunId) -> QualityCheckRun | None: ...

    def add(self, run: QualityCheckRun) -> None: ...

    def transition(
        self,
        run_id: QualityCheckRunId,
        transition: QualityCheckRun,
        expected_status: QualityCheckRunStatus,
    ) -> QualityCheckRun: ...

    def append_score(
        self,
        run_id: QualityCheckRunId,
        score: QualityScore,
        expected_status: QualityCheckRunStatus,
    ) -> None: ...


@runtime_checkable
class FindingRepository(Protocol):
    def get(self, finding_id: FindingId) -> Finding | None: ...

    def append(self, finding: Finding) -> None: ...

    def resolve(
        self,
        finding_id: FindingId,
        resolution: Finding,
        expected_status: FindingStatus,
    ) -> Finding: ...


@runtime_checkable
class WaiverRepository(Protocol):
    def get(self, waiver_id: WaiverId) -> Waiver | None: ...

    def append_request(self, waiver: Waiver) -> None: ...

    def decide(
        self,
        waiver_id: WaiverId,
        decision: Waiver,
        expected_status: WaiverStatus,
    ) -> Waiver: ...

    def revoke(
        self,
        waiver_id: WaiverId,
        revocation: Waiver,
        expected_status: WaiverStatus,
    ) -> Waiver: ...

    def mark_expired(
        self,
        waiver_id: WaiverId,
        evaluated_at: AwareUtcDateTime,
        expected_status: WaiverStatus,
    ) -> Waiver: ...


@runtime_checkable
class GateDecisionRepository(Protocol):
    def get(self, decision_id: GateDecisionId) -> GateDecision | None: ...

    def append(self, decision: GateDecision) -> None: ...


__all__ = [
    "FindingRepository",
    "GateDecisionRepository",
    "PolicyBundleRepository",
    "QualityCheckRunRepository",
    "RuleVersionRepository",
    "WaiverRepository",
]
