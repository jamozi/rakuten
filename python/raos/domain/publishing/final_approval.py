"""Recorded-local human final-approval command for ST-0902.

The command binds the exact ST-0605 claim/evidence result, ST-0805 policy
result, ST-0901 completed human review, a complete Finding snapshot, and the
immutable Article Version hashes.  It records only a synthetic DEV/CI human
decision.  It never grants publication-snapshot, publication, release, or
Production authority and has no filesystem, network, database, provider, or
credential capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex
from uuid import RFC_4122, UUID

from raos.domain.editorial.policy_engine_v2 import (
    PolicyEvaluationRecordReceiptV2,
    PolicyEvaluationReportV2,
    PolicyEvaluationStatusV2,
    coverage_receipt_sha256 as policy_coverage_receipt_sha256,
)
from raos.domain.evidence.claim_evidence import (
    ClaimEvidenceCoverageReport,
    CoverageRecordReceipt,
    CoverageStatus,
)
from raos.domain.portfolio.workflow import IdempotencyKey
from raos.domain.publishing.review_completion_v2 import (
    ReviewCompletionResultV2,
    policy_finding_snapshot_sha256,
    policy_receipt_sha256,
)
from raos.domain.publishing.review_decision_operations import (
    RecordedSubjectKind,
    RecordedSubjectStatus,
)
from raos.domain.publishing.review_workflow import (
    ArticleVersionId,
    PrincipalId,
    ReviewDecisionKind,
    UtcTimestamp,
)
from raos.domain.shared.persistence import Sha256Digest


PROFILE: Final = "ST0902_FINAL_APPROVAL_RECORDED_LOCAL_V2"
OPERATION: Final = "PUBADM-005"
ACTION: Final = "publishing:approval:decide"
AUDIT_ACTION: Final = "final_approval_recorded_local"
MAX_STEP_UP_AGE_SECONDS: Final = 300
_MAX_EXACT_INTEGER: Final = (1 << 53) - 1
_MAX_CANONICAL_BYTES: Final = 4 * 1024 * 1024
_SAFE_REASON: Final = re.compile(r"[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+\Z")


class FinalApprovalFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DEPENDENCY_INVALID = "DEPENDENCY_INVALID"
    ARTICLE_BINDING_MISMATCH = "ARTICLE_BINDING_MISMATCH"
    REVIEW_NOT_APPROVED = "REVIEW_NOT_APPROVED"
    COVERAGE_NOT_CLEAR = "COVERAGE_NOT_CLEAR"
    POLICY_NOT_CLEAR = "POLICY_NOT_CLEAR"
    FINDING_SNAPSHOT_INVALID = "FINDING_SNAPSHOT_INVALID"
    BLOCKING_FINDING_PRESENT = "BLOCKING_FINDING_PRESENT"
    AUTHORIZATION_INVALID = "AUTHORIZATION_INVALID"
    APPROVER_NOT_ACTIVE_HUMAN = "APPROVER_NOT_ACTIVE_HUMAN"
    MANAGING_EDITOR_REQUIRED = "MANAGING_EDITOR_REQUIRED"
    MFA_REQUIRED = "MFA_REQUIRED"
    STEP_UP_REQUIRED = "STEP_UP_REQUIRED"
    STEP_UP_STALE = "STEP_UP_STALE"
    SITE_SCOPE_MISMATCH = "SITE_SCOPE_MISMATCH"
    SELF_APPROVAL_FORBIDDEN = "SELF_APPROVAL_FORBIDDEN"
    REVIEWER_APPROVER_SEPARATION_REQUIRED = "REVIEWER_APPROVER_SEPARATION_REQUIRED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    LOCAL_EXCHANGE_UNAVAILABLE = "LOCAL_EXCHANGE_UNAVAILABLE"
    LOCAL_ENVIRONMENT_REQUIRED = "LOCAL_ENVIRONMENT_REQUIRED"
    FIXTURE_INVALID = "FIXTURE_INVALID"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"


class FinalApprovalFailure(RuntimeError):
    __slots__ = ("_code",)

    def __init__(self, code: FinalApprovalFailureCode) -> None:
        if type(code) is not FinalApprovalFailureCode:
            raise TypeError("invalid final approval failure code") from None
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> FinalApprovalFailureCode:
        return self._code

    def __str__(self) -> str:
        return self._code.value

    def __repr__(self) -> str:
        return f"FinalApprovalFailure(code={self._code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("final approval failure serialization is forbidden")


def fail_final_approval(
    code: FinalApprovalFailureCode = FinalApprovalFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise FinalApprovalFailure(code) from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st0902-v2>)"

    def __str__(self) -> str:
        return "<redacted-st0902-v2>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("final approval serialization is forbidden")


class FinalApprovalRole(str, Enum):
    MANAGING_EDITOR = "MANAGING_EDITOR"


class RecordedMfaState(str, Enum):
    SATISFIED_RECORDED_SYNTHETIC = "SATISFIED_RECORDED_SYNTHETIC"


class RecordedStepUpState(str, Enum):
    SATISFIED_RECORDED_SYNTHETIC = "SATISFIED_RECORDED_SYNTHETIC"


class FinalApprovalExecution(str, Enum):
    RECORDED_SYNTHETIC_ONLY = "RECORDED_SYNTHETIC_ONLY"


class FinalApprovalReadiness(str, Enum):
    NOT_READY = "NOT_READY"


class ExternalGateStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


def _canonical_bytes(payload: object) -> bytes:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except Exception:
        fail_final_approval()
    if not encoded or len(encoded) > _MAX_CANONICAL_BYTES:
        fail_final_approval()
    return encoded


def _digest(payload: object) -> Sha256Digest:
    return Sha256Digest(hashlib.sha256(_canonical_bytes(payload)).hexdigest())


def _digest_bytes(payload: bytes) -> Sha256Digest:
    if type(payload) is not bytes or not payload:
        fail_final_approval()
    return Sha256Digest(hashlib.sha256(payload).hexdigest())


def _uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_final_approval()
    return value


def _principal(value: object) -> PrincipalId:
    if type(value) is not PrincipalId:
        fail_final_approval()
    try:
        return PrincipalId(_uuid7(value.value))
    except FinalApprovalFailure:
        raise
    except Exception:
        fail_final_approval()


def _article_version(value: object) -> ArticleVersionId:
    if type(value) is not ArticleVersionId:
        fail_final_approval()
    try:
        return ArticleVersionId(_uuid7(value.value))
    except FinalApprovalFailure:
        raise
    except Exception:
        fail_final_approval()


def _timestamp(value: object) -> UtcTimestamp:
    if type(value) is not UtcTimestamp:
        fail_final_approval()
    try:
        return UtcTimestamp(value.value)
    except Exception:
        fail_final_approval()


def _timestamp_text(value: UtcTimestamp) -> str:
    current = _timestamp(value).value
    return current.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha(value: object) -> Sha256Digest:
    if type(value) is not Sha256Digest:
        fail_final_approval()
    try:
        return Sha256Digest(value.value)
    except Exception:
        fail_final_approval()


@dataclass(frozen=True, slots=True, repr=False)
class FinalApprovalId(_Redacted):
    value: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _uuid7(self.value))


@dataclass(frozen=True, slots=True, repr=False)
class SiteId(_Redacted):
    value: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _uuid7(self.value))


@dataclass(frozen=True, slots=True, repr=False)
class FinalApprovalReason(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or not 10 <= len(self.value) <= 4000
            or self.value != self.value.strip()
            or _SAFE_REASON.fullmatch(self.value) is None
        ):
            fail_final_approval()


def _reason(value: object) -> FinalApprovalReason:
    if type(value) is not FinalApprovalReason:
        fail_final_approval()
    try:
        return FinalApprovalReason(value.value)
    except FinalApprovalFailure:
        raise
    except Exception:
        fail_final_approval()


@dataclass(frozen=True, slots=True, repr=False)
class FinalApprovalFindingSnapshotV2(_Redacted):
    article_version_id: ArticleVersionId
    policy_report_sha256: Sha256Digest
    policy_finding_snapshot_sha256: Sha256Digest
    captured_at: UtcTimestamp
    open_blocking_finding_ids: tuple[UUID, ...]
    complete: bool = True
    waiver_applied: bool = False
    snapshot_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        article_version_id = _article_version(self.article_version_id)
        policy_report_sha256 = _sha(self.policy_report_sha256)
        finding_sha256 = _sha(self.policy_finding_snapshot_sha256)
        captured_at = _timestamp(self.captured_at)
        if (
            type(self.open_blocking_finding_ids) is not tuple
            or len(self.open_blocking_finding_ids) > 4096
            or self.complete is not True
            or self.waiver_applied is not False
        ):
            fail_final_approval(FinalApprovalFailureCode.FINDING_SNAPSHOT_INVALID)
        findings = tuple(_uuid7(item) for item in self.open_blocking_finding_ids)
        if len(set(findings)) != len(findings) or findings != tuple(
            sorted(findings, key=str)
        ):
            fail_final_approval(FinalApprovalFailureCode.FINDING_SNAPSHOT_INVALID)
        object.__setattr__(self, "article_version_id", article_version_id)
        object.__setattr__(self, "policy_report_sha256", policy_report_sha256)
        object.__setattr__(self, "policy_finding_snapshot_sha256", finding_sha256)
        object.__setattr__(self, "captured_at", captured_at)
        object.__setattr__(self, "open_blocking_finding_ids", findings)
        object.__setattr__(self, "snapshot_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "article_version_id": str(self.article_version_id.value),
            "captured_at": _timestamp_text(self.captured_at),
            "complete": self.complete,
            "open_blocking_finding_ids": [
                str(item) for item in self.open_blocking_finding_ids
            ],
            "policy_finding_snapshot_sha256": (
                self.policy_finding_snapshot_sha256.value
            ),
            "policy_report_sha256": self.policy_report_sha256.value,
            "profile": PROFILE,
            "waiver_applied": self.waiver_applied,
        }

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        payload = self._payload()
        payload["snapshot_sha256"] = self.snapshot_sha256.value
        return _canonical_bytes(payload)

    def require_valid(self) -> None:
        rebuilt = FinalApprovalFindingSnapshotV2(
            article_version_id=self.article_version_id,
            policy_report_sha256=self.policy_report_sha256,
            policy_finding_snapshot_sha256=self.policy_finding_snapshot_sha256,
            captured_at=self.captured_at,
            open_blocking_finding_ids=self.open_blocking_finding_ids,
            complete=self.complete,
            waiver_applied=self.waiver_applied,
        )
        if rebuilt.snapshot_sha256 != self.snapshot_sha256:
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)


def coverage_receipt_sha256(value: CoverageRecordReceipt) -> Sha256Digest:
    if type(value) is not CoverageRecordReceipt:
        fail_final_approval(FinalApprovalFailureCode.DEPENDENCY_INVALID)
    try:
        value.require_valid()
    except Exception:
        fail_final_approval(FinalApprovalFailureCode.DEPENDENCY_INVALID)
    try:
        return policy_coverage_receipt_sha256(value)
    except Exception:
        fail_final_approval(FinalApprovalFailureCode.DEPENDENCY_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class FinalApprovalGateBundleV2(_Redacted):
    article_version_id: ArticleVersionId
    article_version_no: int
    article_body_sha256: Sha256Digest
    canonical_ast_sha256: Sha256Digest
    source_packet_version_id: str
    source_packet_content_sha256: Sha256Digest
    complete_claim_set_sha256: Sha256Digest
    coverage_input_sha256: Sha256Digest
    coverage_report_sha256: Sha256Digest
    coverage_receipt_sha256: Sha256Digest
    policy_result_sha256: Sha256Digest
    policy_evaluation_input_sha256: Sha256Digest
    policy_report_sha256: Sha256Digest
    policy_receipt_sha256: Sha256Digest
    policy_finding_snapshot_sha256: Sha256Digest
    methodology_sha256: Sha256Digest
    recommendation_report_sha256: Sha256Digest
    recommendation_receipt_sha256: Sha256Digest
    review_result_sha256: Sha256Digest
    review_record_sha256: Sha256Digest
    review_decision_sha256: Sha256Digest
    checklist_sha256: Sha256Digest
    finding_clearance_sha256: Sha256Digest
    gate_bundle_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        article = _article_version(self.article_version_id)
        if (
            type(self.article_version_no) is not int
            or not 1 <= self.article_version_no <= _MAX_EXACT_INTEGER
            or type(self.source_packet_version_id) is not str
            or not self.source_packet_version_id
            or self.source_packet_version_id != self.source_packet_version_id.strip()
        ):
            fail_final_approval(FinalApprovalFailureCode.DEPENDENCY_INVALID)
        digests = (
            "article_body_sha256",
            "canonical_ast_sha256",
            "source_packet_content_sha256",
            "complete_claim_set_sha256",
            "coverage_input_sha256",
            "coverage_report_sha256",
            "coverage_receipt_sha256",
            "policy_result_sha256",
            "policy_evaluation_input_sha256",
            "policy_report_sha256",
            "policy_receipt_sha256",
            "policy_finding_snapshot_sha256",
            "methodology_sha256",
            "recommendation_report_sha256",
            "recommendation_receipt_sha256",
            "review_result_sha256",
            "review_record_sha256",
            "review_decision_sha256",
            "checklist_sha256",
            "finding_clearance_sha256",
        )
        object.__setattr__(self, "article_version_id", article)
        for name in digests:
            object.__setattr__(self, name, _sha(getattr(self, name)))
        object.__setattr__(self, "gate_bundle_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "article_body_sha256": self.article_body_sha256.value,
            "article_version_id": str(self.article_version_id.value),
            "article_version_no": self.article_version_no,
            "canonical_ast_sha256": self.canonical_ast_sha256.value,
            "checklist_sha256": self.checklist_sha256.value,
            "complete_claim_set_sha256": self.complete_claim_set_sha256.value,
            "coverage_input_sha256": self.coverage_input_sha256.value,
            "coverage_receipt_sha256": self.coverage_receipt_sha256.value,
            "coverage_report_sha256": self.coverage_report_sha256.value,
            "finding_clearance_sha256": self.finding_clearance_sha256.value,
            "methodology_sha256": self.methodology_sha256.value,
            "policy_evaluation_input_sha256": (
                self.policy_evaluation_input_sha256.value
            ),
            "policy_finding_snapshot_sha256": (
                self.policy_finding_snapshot_sha256.value
            ),
            "policy_receipt_sha256": self.policy_receipt_sha256.value,
            "policy_report_sha256": self.policy_report_sha256.value,
            "policy_result_sha256": self.policy_result_sha256.value,
            "profile": PROFILE,
            "recommendation_receipt_sha256": (self.recommendation_receipt_sha256.value),
            "recommendation_report_sha256": (self.recommendation_report_sha256.value),
            "review_decision_sha256": self.review_decision_sha256.value,
            "review_record_sha256": self.review_record_sha256.value,
            "review_result_sha256": self.review_result_sha256.value,
            "source_packet_content_sha256": (self.source_packet_content_sha256.value),
            "source_packet_version_id": self.source_packet_version_id,
        }

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        payload = self._payload()
        payload["gate_bundle_sha256"] = self.gate_bundle_sha256.value
        return _canonical_bytes(payload)

    def require_valid(self) -> None:
        rebuilt = FinalApprovalGateBundleV2(
            article_version_id=self.article_version_id,
            article_version_no=self.article_version_no,
            article_body_sha256=self.article_body_sha256,
            canonical_ast_sha256=self.canonical_ast_sha256,
            source_packet_version_id=self.source_packet_version_id,
            source_packet_content_sha256=self.source_packet_content_sha256,
            complete_claim_set_sha256=self.complete_claim_set_sha256,
            coverage_input_sha256=self.coverage_input_sha256,
            coverage_report_sha256=self.coverage_report_sha256,
            coverage_receipt_sha256=self.coverage_receipt_sha256,
            policy_result_sha256=self.policy_result_sha256,
            policy_evaluation_input_sha256=self.policy_evaluation_input_sha256,
            policy_report_sha256=self.policy_report_sha256,
            policy_receipt_sha256=self.policy_receipt_sha256,
            policy_finding_snapshot_sha256=self.policy_finding_snapshot_sha256,
            methodology_sha256=self.methodology_sha256,
            recommendation_report_sha256=self.recommendation_report_sha256,
            recommendation_receipt_sha256=self.recommendation_receipt_sha256,
            review_result_sha256=self.review_result_sha256,
            review_record_sha256=self.review_record_sha256,
            review_decision_sha256=self.review_decision_sha256,
            checklist_sha256=self.checklist_sha256,
            finding_clearance_sha256=self.finding_clearance_sha256,
        )
        if rebuilt.gate_bundle_sha256 != self.gate_bundle_sha256:
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)


def _validate_dependencies(
    *,
    article_version_id: ArticleVersionId,
    article_version_no: int,
    article_body_sha256: Sha256Digest,
    canonical_ast_sha256: Sha256Digest,
    coverage_report: ClaimEvidenceCoverageReport,
    coverage_receipt: CoverageRecordReceipt,
    policy_report: PolicyEvaluationReportV2,
    policy_receipt: PolicyEvaluationRecordReceiptV2,
    review_result: ReviewCompletionResultV2,
    finding_snapshot: FinalApprovalFindingSnapshotV2,
    approved_at: UtcTimestamp,
) -> FinalApprovalGateBundleV2:
    try:
        coverage_report.require_valid()
        coverage_receipt.require_valid()
        policy_report.require_valid()
        policy_receipt.require_valid()
        review_result.require_valid()
        finding_snapshot.require_valid()
    except FinalApprovalFailure:
        raise
    except Exception:
        fail_final_approval(FinalApprovalFailureCode.DEPENDENCY_INVALID)

    if (
        coverage_receipt.report_sha256 != coverage_report.report_sha256
        or policy_receipt.report_sha256 != policy_report.report_sha256
    ):
        fail_final_approval(FinalApprovalFailureCode.DEPENDENCY_INVALID)
    if (
        coverage_report.status is not CoverageStatus.PASS
        or coverage_report.findings
        or coverage_report.major_requirement_satisfied is not True
        or coverage_report.all_verifiable_requirement_satisfied is not True
    ):
        fail_final_approval(FinalApprovalFailureCode.COVERAGE_NOT_CLEAR)
    if (
        policy_report.status is not PolicyEvaluationStatusV2.LOCAL_EVALUATED
        or policy_report.findings
        or policy_report.policy_findings
        or policy_report.waiver_evaluations
        or policy_report.local_eligibility is not True
        or policy_report.quality_threshold_met is not True
        or policy_report.quality_floors_met is not True
        or policy_report.policy_rules_passed is not True
        or policy_report.zero_tolerance_clear is not True
        or policy_report.quality_gates_passed is not True
        or policy_report.predecessors_available is not True
    ):
        fail_final_approval(FinalApprovalFailureCode.POLICY_NOT_CLEAR)
    decision = review_result.record.decision
    if decision.decision is not ReviewDecisionKind.APPROVE:
        fail_final_approval(FinalApprovalFailureCode.REVIEW_NOT_APPROVED)

    required_policy_values = (
        policy_report.article_version_id,
        policy_report.article_version_no,
        policy_report.article_body_sha256,
        policy_report.canonical_ast_sha256,
        policy_report.source_packet_version_id,
        policy_report.source_packet_content_sha256,
        policy_report.coverage_input_sha256,
        policy_report.coverage_report_sha256,
        policy_report.coverage_receipt_sha256,
        policy_report.complete_claim_set_sha256,
        policy_report.policy_result_sha256,
        policy_report.evaluation_input_sha256,
        policy_report.methodology_sha256,
        policy_report.recommendation_report_sha256,
        policy_report.recommendation_receipt_sha256,
    )
    if any(value is None for value in required_policy_values):
        fail_final_approval(FinalApprovalFailureCode.DEPENDENCY_INVALID)
    if (
        policy_report.article_version_id is None
        or coverage_report.article_version_id is None
        or policy_report.article_version_id.value != article_version_id.value
        or coverage_report.article_version_id.value != article_version_id.value
        or decision.article_version_id != article_version_id
        or policy_report.article_version_no != article_version_no
        or policy_report.article_body_sha256 != article_body_sha256
        or policy_report.canonical_ast_sha256 != canonical_ast_sha256
        or coverage_report.article_body_sha256 != article_body_sha256
        or coverage_report.source_packet_version_id is None
        or policy_report.source_packet_version_id
        != str(coverage_report.source_packet_version_id.value)
        or policy_report.source_packet_content_sha256
        != coverage_report.source_packet_content_sha256
        or policy_report.complete_claim_set_sha256
        != coverage_report.complete_claim_set_sha256
        or policy_report.coverage_input_sha256
        != coverage_report.evaluation_input_sha256
        or policy_report.coverage_report_sha256 != coverage_report.report_sha256
        or policy_report.coverage_receipt_sha256
        != coverage_receipt_sha256(coverage_receipt)
        or decision.policy_report_sha256.value != policy_report.report_sha256.value
        or decision.policy_receipt_sha256.value
        != policy_receipt_sha256(policy_receipt).value
    ):
        fail_final_approval(FinalApprovalFailureCode.ARTICLE_BINDING_MISMATCH)

    expected_finding_sha = policy_finding_snapshot_sha256(policy_report)
    if (
        finding_snapshot.article_version_id != article_version_id
        or finding_snapshot.policy_report_sha256 != policy_report.report_sha256
        or finding_snapshot.policy_finding_snapshot_sha256 != expected_finding_sha
        or decision.finding_snapshot_sha256.value != expected_finding_sha.value
    ):
        fail_final_approval(FinalApprovalFailureCode.FINDING_SNAPSHOT_INVALID)
    if finding_snapshot.open_blocking_finding_ids:
        fail_final_approval(FinalApprovalFailureCode.BLOCKING_FINDING_PRESENT)
    if (
        finding_snapshot.captured_at.value > approved_at.value
        or review_result.record.decided_at.value > approved_at.value
        or coverage_report.evaluated_at is None
        or coverage_report.evaluated_at.value > approved_at.value
    ):
        fail_final_approval(FinalApprovalFailureCode.DEPENDENCY_INVALID)
    if policy_report.source_packet_version_id is None:
        fail_final_approval(FinalApprovalFailureCode.DEPENDENCY_INVALID)

    return FinalApprovalGateBundleV2(
        article_version_id=article_version_id,
        article_version_no=article_version_no,
        article_body_sha256=article_body_sha256,
        canonical_ast_sha256=canonical_ast_sha256,
        source_packet_version_id=policy_report.source_packet_version_id,
        source_packet_content_sha256=_sha(policy_report.source_packet_content_sha256),
        complete_claim_set_sha256=_sha(policy_report.complete_claim_set_sha256),
        coverage_input_sha256=_sha(policy_report.coverage_input_sha256),
        coverage_report_sha256=_sha(policy_report.coverage_report_sha256),
        coverage_receipt_sha256=_sha(policy_report.coverage_receipt_sha256),
        policy_result_sha256=_sha(policy_report.policy_result_sha256),
        policy_evaluation_input_sha256=_sha(policy_report.evaluation_input_sha256),
        policy_report_sha256=_sha(policy_report.report_sha256),
        policy_receipt_sha256=policy_receipt_sha256(policy_receipt),
        policy_finding_snapshot_sha256=expected_finding_sha,
        methodology_sha256=_sha(policy_report.methodology_sha256),
        recommendation_report_sha256=_sha(policy_report.recommendation_report_sha256),
        recommendation_receipt_sha256=_sha(policy_report.recommendation_receipt_sha256),
        review_result_sha256=_sha(review_result.result_sha256),
        review_record_sha256=_sha(review_result.record.record_sha256),
        review_decision_sha256=_sha(decision.decision_sha256),
        checklist_sha256=Sha256Digest(decision.checklist_sha256),
        finding_clearance_sha256=_sha(finding_snapshot.snapshot_sha256),
    )


@dataclass(frozen=True, slots=True, repr=False)
class FinalApprovalRequestV2(_Redacted):
    approval_id: FinalApprovalId
    article_version_id: ArticleVersionId
    article_version_no: int
    article_body_sha256: Sha256Digest
    canonical_ast_sha256: Sha256Digest
    article_author_id: PrincipalId
    last_editor_id: PrincipalId
    site_id: SiteId
    coverage_report: ClaimEvidenceCoverageReport
    coverage_receipt: CoverageRecordReceipt
    policy_report: PolicyEvaluationReportV2
    policy_receipt: PolicyEvaluationRecordReceiptV2
    review_result: ReviewCompletionResultV2
    finding_snapshot: FinalApprovalFindingSnapshotV2
    approved_at: UtcTimestamp
    reason: FinalApprovalReason
    audit_event_id: UUID
    idempotency_key: IdempotencyKey
    gate_bundle: FinalApprovalGateBundleV2 = field(init=False)
    idempotency_key_sha256: Sha256Digest = field(init=False)
    request_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if type(self.approval_id) is not FinalApprovalId:
            fail_final_approval()
        approval_id = FinalApprovalId(self.approval_id.value)
        article_version_id = _article_version(self.article_version_id)
        article_body_sha256 = _sha(self.article_body_sha256)
        canonical_ast_sha256 = _sha(self.canonical_ast_sha256)
        author = _principal(self.article_author_id)
        editor = _principal(self.last_editor_id)
        if type(self.site_id) is not SiteId:
            fail_final_approval()
        site_id = SiteId(self.site_id.value)
        approved_at = _timestamp(self.approved_at)
        reason = _reason(self.reason)
        audit_event_id = _uuid7(self.audit_event_id)
        if type(self.idempotency_key) is not IdempotencyKey:
            fail_final_approval()
        try:
            idempotency_key = IdempotencyKey(self.idempotency_key.value)
        except Exception:
            fail_final_approval()
        gate_bundle = _validate_dependencies(
            article_version_id=article_version_id,
            article_version_no=self.article_version_no,
            article_body_sha256=article_body_sha256,
            canonical_ast_sha256=canonical_ast_sha256,
            coverage_report=self.coverage_report,
            coverage_receipt=self.coverage_receipt,
            policy_report=self.policy_report,
            policy_receipt=self.policy_receipt,
            review_result=self.review_result,
            finding_snapshot=self.finding_snapshot,
            approved_at=approved_at,
        )
        key_digest = _digest_bytes(idempotency_key.value.encode("utf-8"))
        object.__setattr__(self, "approval_id", approval_id)
        object.__setattr__(self, "article_version_id", article_version_id)
        object.__setattr__(self, "article_body_sha256", article_body_sha256)
        object.__setattr__(self, "canonical_ast_sha256", canonical_ast_sha256)
        object.__setattr__(self, "article_author_id", author)
        object.__setattr__(self, "last_editor_id", editor)
        object.__setattr__(self, "site_id", site_id)
        object.__setattr__(self, "approved_at", approved_at)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "audit_event_id", audit_event_id)
        object.__setattr__(self, "idempotency_key", idempotency_key)
        object.__setattr__(self, "gate_bundle", gate_bundle)
        object.__setattr__(self, "idempotency_key_sha256", key_digest)
        object.__setattr__(self, "request_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "approval_id": str(self.approval_id.value),
            "approved_at": _timestamp_text(self.approved_at),
            "article_author_id": str(self.article_author_id.value),
            "article_version_id": str(self.article_version_id.value),
            "audit_event_id": str(self.audit_event_id),
            "gate_bundle_sha256": self.gate_bundle.gate_bundle_sha256.value,
            "idempotency_key_sha256": self.idempotency_key_sha256.value,
            "last_editor_id": str(self.last_editor_id.value),
            "operation": OPERATION,
            "profile": PROFILE,
            "reason_sha256": _digest_bytes(self.reason.value.encode("utf-8")).value,
            "site_id": str(self.site_id.value),
        }

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        payload = self._payload()
        payload["request_sha256"] = self.request_sha256.value
        return _canonical_bytes(payload)

    def require_valid(self) -> None:
        rebuilt = FinalApprovalRequestV2(
            approval_id=self.approval_id,
            article_version_id=self.article_version_id,
            article_version_no=self.article_version_no,
            article_body_sha256=self.article_body_sha256,
            canonical_ast_sha256=self.canonical_ast_sha256,
            article_author_id=self.article_author_id,
            last_editor_id=self.last_editor_id,
            site_id=self.site_id,
            coverage_report=self.coverage_report,
            coverage_receipt=self.coverage_receipt,
            policy_report=self.policy_report,
            policy_receipt=self.policy_receipt,
            review_result=self.review_result,
            finding_snapshot=self.finding_snapshot,
            approved_at=self.approved_at,
            reason=self.reason,
            audit_event_id=self.audit_event_id,
            idempotency_key=self.idempotency_key,
        )
        if (
            rebuilt.gate_bundle.gate_bundle_sha256
            != self.gate_bundle.gate_bundle_sha256
            or rebuilt.idempotency_key_sha256 != self.idempotency_key_sha256
            or rebuilt.request_sha256 != self.request_sha256
        ):
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedFinalApproverV2(_Redacted):
    principal_id: PrincipalId
    site_id: SiteId
    subject_kind: RecordedSubjectKind
    subject_status: RecordedSubjectStatus
    role: FinalApprovalRole
    mfa_state: RecordedMfaState
    step_up_state: RecordedStepUpState
    reauthenticated_at: UtcTimestamp

    def __post_init__(self) -> None:
        principal = _principal(self.principal_id)
        if type(self.site_id) is not SiteId:
            fail_final_approval(FinalApprovalFailureCode.AUTHORIZATION_INVALID)
        site = SiteId(self.site_id.value)
        if (
            type(self.subject_kind) is not RecordedSubjectKind
            or type(self.subject_status) is not RecordedSubjectStatus
            or type(self.role) is not FinalApprovalRole
            or type(self.mfa_state) is not RecordedMfaState
            or type(self.step_up_state) is not RecordedStepUpState
        ):
            fail_final_approval(FinalApprovalFailureCode.AUTHORIZATION_INVALID)
        object.__setattr__(self, "principal_id", principal)
        object.__setattr__(self, "site_id", site)
        object.__setattr__(
            self, "reauthenticated_at", _timestamp(self.reauthenticated_at)
        )

    def canonical_projection(self) -> dict[str, str]:
        return {
            "mfa_state": self.mfa_state.value,
            "principal_id": str(self.principal_id.value),
            "reauthenticated_at": _timestamp_text(self.reauthenticated_at),
            "role": self.role.value,
            "site_id": str(self.site_id.value),
            "step_up_state": self.step_up_state.value,
            "subject_kind": self.subject_kind.value,
            "subject_status": self.subject_status.value,
        }

    def require_valid(self) -> None:
        rebuilt = RecordedFinalApproverV2(
            principal_id=self.principal_id,
            site_id=self.site_id,
            subject_kind=self.subject_kind,
            subject_status=self.subject_status,
            role=self.role,
            mfa_state=self.mfa_state,
            step_up_state=self.step_up_state,
            reauthenticated_at=self.reauthenticated_at,
        )
        if rebuilt.canonical_projection() != self.canonical_projection():
            fail_final_approval(FinalApprovalFailureCode.AUTHORIZATION_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedFinalApprovalAuthorizationV2(_Redacted):
    request_sha256: Sha256Digest
    actor: RecordedFinalApproverV2
    action: str = ACTION
    permission: str = ACTION
    real_authentication_verified: bool = False
    durable_authorization_verified: bool = False
    external_authority: bool = False
    authorization_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        request_sha256 = _sha(self.request_sha256)
        if type(self.actor) is not RecordedFinalApproverV2:
            fail_final_approval(FinalApprovalFailureCode.AUTHORIZATION_INVALID)
        self.actor.require_valid()
        if (
            self.action != ACTION
            or self.permission != ACTION
            or self.real_authentication_verified is not False
            or self.durable_authorization_verified is not False
            or self.external_authority is not False
        ):
            fail_final_approval(FinalApprovalFailureCode.AUTHORIZATION_INVALID)
        object.__setattr__(self, "request_sha256", request_sha256)
        object.__setattr__(self, "authorization_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "action": self.action,
            "actor": self.actor.canonical_projection(),
            "durable_authorization_verified": self.durable_authorization_verified,
            "external_authority": self.external_authority,
            "permission": self.permission,
            "profile": PROFILE,
            "real_authentication_verified": self.real_authentication_verified,
            "request_sha256": self.request_sha256.value,
        }

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        payload = self._payload()
        payload["authorization_sha256"] = self.authorization_sha256.value
        return _canonical_bytes(payload)

    def require_valid(self) -> None:
        rebuilt = RecordedFinalApprovalAuthorizationV2(
            request_sha256=self.request_sha256,
            actor=self.actor,
            action=self.action,
            permission=self.permission,
            real_authentication_verified=self.real_authentication_verified,
            durable_authorization_verified=self.durable_authorization_verified,
            external_authority=self.external_authority,
        )
        if rebuilt.authorization_sha256 != self.authorization_sha256:
            fail_final_approval(FinalApprovalFailureCode.AUTHORIZATION_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedFinalApprovalV2(_Redacted):
    approval_id: FinalApprovalId
    article_version_id: ArticleVersionId
    approved_by: PrincipalId
    approved_at: UtcTimestamp
    site_id: SiteId
    reason_sha256: Sha256Digest
    gate_bundle_sha256: Sha256Digest
    request_sha256: Sha256Digest
    authorization_sha256: Sha256Digest
    approval_type: str = "FINAL"
    decision: str = "APPROVED"
    record_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if type(self.approval_id) is not FinalApprovalId:
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)
        object.__setattr__(self, "approval_id", FinalApprovalId(self.approval_id.value))
        object.__setattr__(
            self, "article_version_id", _article_version(self.article_version_id)
        )
        object.__setattr__(self, "approved_by", _principal(self.approved_by))
        object.__setattr__(self, "approved_at", _timestamp(self.approved_at))
        if type(self.site_id) is not SiteId:
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)
        object.__setattr__(self, "site_id", SiteId(self.site_id.value))
        for name in (
            "reason_sha256",
            "gate_bundle_sha256",
            "request_sha256",
            "authorization_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name)))
        if self.approval_type != "FINAL" or self.decision != "APPROVED":
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)
        object.__setattr__(self, "record_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "approval_id": str(self.approval_id.value),
            "approval_type": self.approval_type,
            "approved_at": _timestamp_text(self.approved_at),
            "approved_by": str(self.approved_by.value),
            "article_version_id": str(self.article_version_id.value),
            "authorization_sha256": self.authorization_sha256.value,
            "decision": self.decision,
            "gate_bundle_sha256": self.gate_bundle_sha256.value,
            "profile": PROFILE,
            "reason_sha256": self.reason_sha256.value,
            "request_sha256": self.request_sha256.value,
            "site_id": str(self.site_id.value),
        }

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        payload = self._payload()
        payload["record_sha256"] = self.record_sha256.value
        return _canonical_bytes(payload)

    def require_valid(self) -> None:
        rebuilt = RecordedFinalApprovalV2(
            approval_id=self.approval_id,
            article_version_id=self.article_version_id,
            approved_by=self.approved_by,
            approved_at=self.approved_at,
            site_id=self.site_id,
            reason_sha256=self.reason_sha256,
            gate_bundle_sha256=self.gate_bundle_sha256,
            request_sha256=self.request_sha256,
            authorization_sha256=self.authorization_sha256,
            approval_type=self.approval_type,
            decision=self.decision,
        )
        if rebuilt.record_sha256 != self.record_sha256:
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedFinalApprovalAuditV2(_Redacted):
    event_id: UUID
    occurred_at: UtcTimestamp
    actor_id: PrincipalId
    approval_id: FinalApprovalId
    article_version_id: ArticleVersionId
    request_sha256: Sha256Digest
    authorization_sha256: Sha256Digest
    gate_bundle_sha256: Sha256Digest
    record_sha256: Sha256Digest
    audit_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _uuid7(self.event_id))
        object.__setattr__(self, "occurred_at", _timestamp(self.occurred_at))
        object.__setattr__(self, "actor_id", _principal(self.actor_id))
        if type(self.approval_id) is not FinalApprovalId:
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)
        object.__setattr__(self, "approval_id", FinalApprovalId(self.approval_id.value))
        object.__setattr__(
            self, "article_version_id", _article_version(self.article_version_id)
        )
        for name in (
            "request_sha256",
            "authorization_sha256",
            "gate_bundle_sha256",
            "record_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name)))
        object.__setattr__(self, "audit_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "action": AUDIT_ACTION,
            "actor_id": str(self.actor_id.value),
            "approval_id": str(self.approval_id.value),
            "article_version_id": str(self.article_version_id.value),
            "authorization_sha256": self.authorization_sha256.value,
            "event_id": str(self.event_id),
            "gate_bundle_sha256": self.gate_bundle_sha256.value,
            "occurred_at": _timestamp_text(self.occurred_at),
            "profile": PROFILE,
            "record_sha256": self.record_sha256.value,
            "request_sha256": self.request_sha256.value,
        }

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        payload = self._payload()
        payload["audit_sha256"] = self.audit_sha256.value
        return _canonical_bytes(payload)

    def require_valid(self) -> None:
        rebuilt = RecordedFinalApprovalAuditV2(
            event_id=self.event_id,
            occurred_at=self.occurred_at,
            actor_id=self.actor_id,
            approval_id=self.approval_id,
            article_version_id=self.article_version_id,
            request_sha256=self.request_sha256,
            authorization_sha256=self.authorization_sha256,
            gate_bundle_sha256=self.gate_bundle_sha256,
            record_sha256=self.record_sha256,
        )
        if rebuilt.audit_sha256 != self.audit_sha256:
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)


def _idempotency_receipt_sha256(
    *,
    idempotency_key_sha256: Sha256Digest,
    request_sha256: Sha256Digest,
    record_sha256: Sha256Digest,
) -> Sha256Digest:
    return _digest(
        {
            "idempotency_key_sha256": _sha(idempotency_key_sha256).value,
            "operation": OPERATION,
            "profile": PROFILE,
            "record_sha256": _sha(record_sha256).value,
            "request_sha256": _sha(request_sha256).value,
        }
    )


@dataclass(frozen=True, slots=True, repr=False)
class FinalApprovalResultV2(_Redacted):
    request_sha256: Sha256Digest
    authorization_sha256: Sha256Digest
    gate_bundle_sha256: Sha256Digest
    record: RecordedFinalApprovalV2
    audit: RecordedFinalApprovalAuditV2
    idempotency_key_sha256: Sha256Digest
    idempotency_receipt_sha256: Sha256Digest
    execution: FinalApprovalExecution = FinalApprovalExecution.RECORDED_SYNTHETIC_ONLY
    readiness: FinalApprovalReadiness = FinalApprovalReadiness.NOT_READY
    local_final_approval_recorded: bool = True
    real_final_approval_authorized: bool = False
    publication_snapshot_authorized: bool = False
    publication_authorized: bool = False
    release_authorized: bool = False
    production_authorized: bool = False
    durable_transaction: bool = False
    event_emitted: bool = False
    formal_tst_012_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    formal_tst_021_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    live_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    staging_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    release_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    publication_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    production_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    result_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "request_sha256",
            "authorization_sha256",
            "gate_bundle_sha256",
            "idempotency_key_sha256",
            "idempotency_receipt_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name)))
        if (
            type(self.record) is not RecordedFinalApprovalV2
            or type(self.audit) is not RecordedFinalApprovalAuditV2
        ):
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)
        self.record.require_valid()
        self.audit.require_valid()
        if (
            self.record.request_sha256 != self.request_sha256
            or self.record.authorization_sha256 != self.authorization_sha256
            or self.record.gate_bundle_sha256 != self.gate_bundle_sha256
            or self.audit.request_sha256 != self.request_sha256
            or self.audit.authorization_sha256 != self.authorization_sha256
            or self.audit.gate_bundle_sha256 != self.gate_bundle_sha256
            or self.audit.record_sha256 != self.record.record_sha256
            or self.audit.actor_id != self.record.approved_by
            or self.audit.approval_id != self.record.approval_id
            or self.audit.article_version_id != self.record.article_version_id
            or self.audit.occurred_at != self.record.approved_at
            or self.idempotency_receipt_sha256
            != _idempotency_receipt_sha256(
                idempotency_key_sha256=self.idempotency_key_sha256,
                request_sha256=self.request_sha256,
                record_sha256=self.record.record_sha256,
            )
            or self.execution is not FinalApprovalExecution.RECORDED_SYNTHETIC_ONLY
            or self.readiness is not FinalApprovalReadiness.NOT_READY
            or self.local_final_approval_recorded is not True
            or self.real_final_approval_authorized is not False
            or self.publication_snapshot_authorized is not False
            or self.publication_authorized is not False
            or self.release_authorized is not False
            or self.production_authorized is not False
            or self.durable_transaction is not False
            or self.event_emitted is not False
            or any(
                value is not ExternalGateStatus.NOT_EXECUTED
                for value in (
                    self.formal_tst_012_status,
                    self.formal_tst_021_status,
                    self.live_status,
                    self.staging_status,
                    self.release_status,
                    self.publication_status,
                    self.production_status,
                )
            )
        ):
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)
        object.__setattr__(self, "result_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "audit_sha256": self.audit.audit_sha256.value,
            "authorization_sha256": self.authorization_sha256.value,
            "durable_transaction": self.durable_transaction,
            "event_emitted": self.event_emitted,
            "execution": self.execution.value,
            "external_gates": {
                "formal_tst_012": self.formal_tst_012_status.value,
                "formal_tst_021": self.formal_tst_021_status.value,
                "live": self.live_status.value,
                "production": self.production_status.value,
                "publication": self.publication_status.value,
                "release": self.release_status.value,
                "staging": self.staging_status.value,
            },
            "gate_bundle_sha256": self.gate_bundle_sha256.value,
            "idempotency_key_sha256": self.idempotency_key_sha256.value,
            "idempotency_receipt_sha256": self.idempotency_receipt_sha256.value,
            "local_final_approval_recorded": self.local_final_approval_recorded,
            "production_authorized": self.production_authorized,
            "profile": PROFILE,
            "publication_authorized": self.publication_authorized,
            "publication_snapshot_authorized": (self.publication_snapshot_authorized),
            "readiness": self.readiness.value,
            "real_final_approval_authorized": (self.real_final_approval_authorized),
            "record_sha256": self.record.record_sha256.value,
            "release_authorized": self.release_authorized,
            "request_sha256": self.request_sha256.value,
        }

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        payload = self._payload()
        payload["result_sha256"] = self.result_sha256.value
        return _canonical_bytes(payload)

    def require_valid(self) -> None:
        rebuilt = FinalApprovalResultV2(
            request_sha256=self.request_sha256,
            authorization_sha256=self.authorization_sha256,
            gate_bundle_sha256=self.gate_bundle_sha256,
            record=self.record,
            audit=self.audit,
            idempotency_key_sha256=self.idempotency_key_sha256,
            idempotency_receipt_sha256=self.idempotency_receipt_sha256,
            execution=self.execution,
            readiness=self.readiness,
            local_final_approval_recorded=self.local_final_approval_recorded,
            real_final_approval_authorized=self.real_final_approval_authorized,
            publication_snapshot_authorized=self.publication_snapshot_authorized,
            publication_authorized=self.publication_authorized,
            release_authorized=self.release_authorized,
            production_authorized=self.production_authorized,
            durable_transaction=self.durable_transaction,
            event_emitted=self.event_emitted,
            formal_tst_012_status=self.formal_tst_012_status,
            formal_tst_021_status=self.formal_tst_021_status,
            live_status=self.live_status,
            staging_status=self.staging_status,
            release_status=self.release_status,
            publication_status=self.publication_status,
            production_status=self.production_status,
        )
        if rebuilt.result_sha256 != self.result_sha256:
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)


def grant_final_approval_v2(
    *,
    request: FinalApprovalRequestV2,
    authorization: RecordedFinalApprovalAuthorizationV2,
) -> FinalApprovalResultV2:
    if type(request) is not FinalApprovalRequestV2:
        fail_final_approval()
    if type(authorization) is not RecordedFinalApprovalAuthorizationV2:
        fail_final_approval(FinalApprovalFailureCode.AUTHORIZATION_INVALID)
    request.require_valid()
    authorization.require_valid()
    actor = authorization.actor
    if authorization.request_sha256 != request.request_sha256:
        fail_final_approval(FinalApprovalFailureCode.AUTHORIZATION_INVALID)
    if (
        actor.subject_kind is not RecordedSubjectKind.HUMAN
        or actor.subject_status is not RecordedSubjectStatus.ACTIVE
    ):
        fail_final_approval(FinalApprovalFailureCode.APPROVER_NOT_ACTIVE_HUMAN)
    if actor.role is not FinalApprovalRole.MANAGING_EDITOR:
        fail_final_approval(FinalApprovalFailureCode.MANAGING_EDITOR_REQUIRED)
    if actor.mfa_state is not RecordedMfaState.SATISFIED_RECORDED_SYNTHETIC:
        fail_final_approval(FinalApprovalFailureCode.MFA_REQUIRED)
    if actor.step_up_state is not RecordedStepUpState.SATISFIED_RECORDED_SYNTHETIC:
        fail_final_approval(FinalApprovalFailureCode.STEP_UP_REQUIRED)
    if actor.site_id != request.site_id:
        fail_final_approval(FinalApprovalFailureCode.SITE_SCOPE_MISMATCH)
    age = (request.approved_at.value - actor.reauthenticated_at.value).total_seconds()
    if age < 0 or age > MAX_STEP_UP_AGE_SECONDS:
        fail_final_approval(FinalApprovalFailureCode.STEP_UP_STALE)
    if actor.principal_id in {request.article_author_id, request.last_editor_id}:
        fail_final_approval(FinalApprovalFailureCode.SELF_APPROVAL_FORBIDDEN)
    if actor.principal_id == request.review_result.record.decided_by:
        fail_final_approval(
            FinalApprovalFailureCode.REVIEWER_APPROVER_SEPARATION_REQUIRED
        )

    reason_sha256 = _digest_bytes(request.reason.value.encode("utf-8"))
    record = RecordedFinalApprovalV2(
        approval_id=request.approval_id,
        article_version_id=request.article_version_id,
        approved_by=actor.principal_id,
        approved_at=request.approved_at,
        site_id=request.site_id,
        reason_sha256=reason_sha256,
        gate_bundle_sha256=request.gate_bundle.gate_bundle_sha256,
        request_sha256=request.request_sha256,
        authorization_sha256=authorization.authorization_sha256,
    )
    audit = RecordedFinalApprovalAuditV2(
        event_id=request.audit_event_id,
        occurred_at=request.approved_at,
        actor_id=actor.principal_id,
        approval_id=request.approval_id,
        article_version_id=request.article_version_id,
        request_sha256=request.request_sha256,
        authorization_sha256=authorization.authorization_sha256,
        gate_bundle_sha256=request.gate_bundle.gate_bundle_sha256,
        record_sha256=record.record_sha256,
    )
    receipt = _idempotency_receipt_sha256(
        idempotency_key_sha256=request.idempotency_key_sha256,
        request_sha256=request.request_sha256,
        record_sha256=record.record_sha256,
    )
    return FinalApprovalResultV2(
        request_sha256=request.request_sha256,
        authorization_sha256=authorization.authorization_sha256,
        gate_bundle_sha256=request.gate_bundle.gate_bundle_sha256,
        record=record,
        audit=audit,
        idempotency_key_sha256=request.idempotency_key_sha256,
        idempotency_receipt_sha256=receipt,
    )


__all__ = (
    "ACTION",
    "AUDIT_ACTION",
    "ExternalGateStatus",
    "FinalApprovalExecution",
    "FinalApprovalFailure",
    "FinalApprovalFailureCode",
    "FinalApprovalFindingSnapshotV2",
    "FinalApprovalGateBundleV2",
    "FinalApprovalId",
    "FinalApprovalReadiness",
    "FinalApprovalReason",
    "FinalApprovalRequestV2",
    "FinalApprovalResultV2",
    "FinalApprovalRole",
    "MAX_STEP_UP_AGE_SECONDS",
    "OPERATION",
    "PROFILE",
    "RecordedFinalApprovalAuditV2",
    "RecordedFinalApprovalAuthorizationV2",
    "RecordedFinalApprovalV2",
    "RecordedFinalApproverV2",
    "RecordedMfaState",
    "RecordedStepUpState",
    "SiteId",
    "coverage_receipt_sha256",
    "fail_final_approval",
    "grant_final_approval_v2",
)
