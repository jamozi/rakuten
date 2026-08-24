"""Policy-bound, recorded-local human review completion for ST-0901.

This additive V2 seam closes the local gap between the immutable ST-0805
policy report/receipt and one immutable human review decision.  It may record
the review-level ``APPROVE`` token only when every checklist item is ``PASS``
and the exact policy report is locally clear.  The token is not the separate
ST-0902 final approval and grants no publication, release, or Production
authority.

All clocks, identifiers, identities, and idempotency material are supplied by
recorded synthetic callers.  The module has no filesystem, network, database,
provider, credential, or public-write capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Callable, Final, NoReturn, Protocol, SupportsIndex, TypeVar, cast
from uuid import RFC_4122, UUID

from raos.domain.editorial.ids import ArticleVersionId as EditorialArticleVersionId
from raos.domain.editorial.policy_engine_v2 import (
    PolicyEvaluationRecordReceiptV2,
    PolicyEvaluationReportV2,
    PolicyEvaluationStatusV2,
)
from raos.domain.portfolio.workflow import IdempotencyKey
from raos.domain.publishing.review_decision_operations import (
    RecordedIdentityProjection,
    RecordedSubjectKind,
    RecordedSubjectStatus,
)
from raos.domain.publishing.review_workflow import (
    HUMAN_REVIEW_CHECKLIST_IDS,
    HUMAN_REVIEW_CHECKLIST_SHA256,
    HUMAN_REVIEW_CHECKLIST_VERSION,
    ArticleVersionId,
    ChecklistItemId,
    ChecklistItemStatus,
    ChecklistResult,
    DecisionSummary,
    EvidenceId,
    EvidenceReference,
    HumanComment,
    PrincipalId,
    ReviewAssignment,
    ReviewAssignmentId,
    ReviewAssignmentState,
    ReviewDecisionDraft,
    ReviewDecisionId,
    ReviewDecisionKind,
    ReviewDecisionReference,
    ReviewType,
    Sha256Digest as ReviewSha256Digest,
    UtcTimestamp,
    transition_review_assignment,
)
from raos.domain.shared.persistence import Sha256Digest


PROFILE: Final = "ST0901_REVIEW_COMPLETION_RECORDED_LOCAL_V2"
OPERATION: Final = "PUBADM-004-COMPLETE"
ACTION: Final = "publishing:review:decide"
AUDIT_ACTION: Final = "review_decision_record_and_assignment_complete"
_MAX_CANONICAL_BYTES: Final = 4 * 1024 * 1024
_MAX_SEQUENCE: Final = (1 << 53) - 1
_UuidT = TypeVar("_UuidT")


class _HasUuidValue(Protocol):
    value: UUID


class ReviewCompletionFailureCode(str, Enum):
    """Closed, non-sensitive failure vocabulary for the V2 seam."""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    ASSIGNMENT_INVALID = "ASSIGNMENT_INVALID"
    DECISION_INVALID = "DECISION_INVALID"
    CHECKLIST_INVALID = "CHECKLIST_INVALID"
    CHECKLIST_APPLICABILITY_UNRESOLVED = "CHECKLIST_APPLICABILITY_UNRESOLVED"
    APPROVE_CHECKLIST_NOT_CLEAR = "APPROVE_CHECKLIST_NOT_CLEAR"
    POLICY_REPORT_INVALID = "POLICY_REPORT_INVALID"
    POLICY_RECEIPT_INVALID = "POLICY_RECEIPT_INVALID"
    POLICY_BINDING_MISMATCH = "POLICY_BINDING_MISMATCH"
    APPROVE_POLICY_NOT_CLEAR = "APPROVE_POLICY_NOT_CLEAR"
    REVIEWER_NOT_ACTIVE_HUMAN = "REVIEWER_NOT_ACTIVE_HUMAN"
    REVIEWER_ASSIGNMENT_MISMATCH = "REVIEWER_ASSIGNMENT_MISMATCH"
    AUTHORIZATION_INVALID = "AUTHORIZATION_INVALID"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    LOCAL_ENVIRONMENT_REQUIRED = "LOCAL_ENVIRONMENT_REQUIRED"
    LOCAL_EXCHANGE_UNAVAILABLE = "LOCAL_EXCHANGE_UNAVAILABLE"
    FIXTURE_INVALID = "FIXTURE_INVALID"


class ReviewCompletionFailure(RuntimeError):
    """Stable-code exception that never retains rejected caller material."""

    __slots__ = ("_code",)

    def __init__(self, code: ReviewCompletionFailureCode) -> None:
        if type(code) is not ReviewCompletionFailureCode:
            raise TypeError("invalid review completion failure code")
        self._code = code
        RuntimeError.__init__(self, code.value)

    @property
    def code(self) -> ReviewCompletionFailureCode:
        return self._code

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ReviewCompletionFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("review completion failure serialization is denied")


def fail_review_completion(
    code: ReviewCompletionFailureCode = ReviewCompletionFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise ReviewCompletionFailure(code) from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st0901-v2>)"

    def __str__(self) -> str:
        return "<redacted-st0901-v2>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("review completion value serialization is denied")


class ReviewCompletionExecution(str, Enum):
    RECORDED_ONLY = "RECORDED_ONLY"


class ReviewCompletionReadiness(str, Enum):
    NOT_READY = "NOT_READY"


class ExternalGateStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


def _canonical_bytes(payload: object) -> bytes:
    encoded: bytes | None = None
    try:
        encoded = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        pass
    if encoded is None or not encoded or len(encoded) > _MAX_CANONICAL_BYTES:
        fail_review_completion()
    return encoded


def _digest(payload: object) -> Sha256Digest:
    return Sha256Digest(hashlib.sha256(_canonical_bytes(payload)).hexdigest())


def _timestamp_text(value: UtcTimestamp) -> str:
    if type(value) is not UtcTimestamp:
        fail_review_completion()
    try:
        rebuilt = UtcTimestamp(value.value)
    except Exception:
        fail_review_completion()
    return rebuilt.value.isoformat().replace("+00:00", "Z")


def _uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_review_completion()
    return UUID(int=value.int)


def _clone_uuid_value(value: object, expected_type: type[_UuidT]) -> _UuidT:
    if type(value) is not expected_type:
        fail_review_completion()
    try:
        raw = cast(_HasUuidValue, value).value
    except Exception:
        fail_review_completion()
    constructor = cast(Callable[[UUID], _UuidT], expected_type)
    return constructor(_uuid7(raw))


def _clone_timestamp(value: object) -> UtcTimestamp:
    if type(value) is not UtcTimestamp:
        fail_review_completion()
    try:
        raw = value.value
        if type(raw) is not datetime or raw.tzinfo is not timezone.utc or raw.fold:
            fail_review_completion()
        return UtcTimestamp(
            datetime(
                raw.year,
                raw.month,
                raw.day,
                raw.hour,
                raw.minute,
                raw.second,
                raw.microsecond,
                tzinfo=timezone.utc,
            )
        )
    except ReviewCompletionFailure:
        raise
    except Exception:
        fail_review_completion()


def _clone_optional_timestamp(value: object) -> UtcTimestamp | None:
    if value is None:
        return None
    return _clone_timestamp(value)


def _clone_reference(value: object) -> ReviewDecisionReference | None:
    if value is None:
        return None
    if type(value) is not ReviewDecisionReference:
        fail_review_completion()
    return ReviewDecisionReference(
        decision_id=_clone_uuid_value(value.decision_id, ReviewDecisionId),
        review_assignment_id=_clone_uuid_value(
            value.review_assignment_id, ReviewAssignmentId
        ),
        article_version_id=_clone_uuid_value(
            value.article_version_id, ArticleVersionId
        ),
    )


def _clone_assignment(value: object) -> ReviewAssignment:
    if type(value) is not ReviewAssignment:
        fail_review_completion(ReviewCompletionFailureCode.ASSIGNMENT_INVALID)
    try:
        if (
            type(value.review_type) is not ReviewType
            or type(value.status) is not ReviewAssignmentState
        ):
            fail_review_completion(ReviewCompletionFailureCode.ASSIGNMENT_INVALID)
        rebuilt = ReviewAssignment(
            assignment_id=_clone_uuid_value(value.assignment_id, ReviewAssignmentId),
            article_version_id=_clone_uuid_value(
                value.article_version_id, ArticleVersionId
            ),
            review_type=value.review_type,
            assigned_by=_clone_uuid_value(value.assigned_by, PrincipalId),
            assigned_to=_clone_uuid_value(value.assigned_to, PrincipalId),
            priority=value.priority,
            status=value.status,
            started_at=_clone_optional_timestamp(value.started_at),
            completed_at=_clone_optional_timestamp(value.completed_at),
            cancelled_at=_clone_optional_timestamp(value.cancelled_at),
            created_at=_clone_timestamp(value.created_at),
            updated_at=_clone_timestamp(value.updated_at),
            lock_version=value.lock_version,
            completion_decision_reference=_clone_reference(
                value.completion_decision_reference
            ),
        )
    except ReviewCompletionFailure:
        raise
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.ASSIGNMENT_INVALID)
    if rebuilt != value:
        fail_review_completion(ReviewCompletionFailureCode.ASSIGNMENT_INVALID)
    return rebuilt


def _clone_evidence(value: object) -> EvidenceReference:
    if type(value) is not EvidenceReference:
        fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
    try:
        rebuilt = EvidenceReference(
            evidence_id=_clone_uuid_value(value.evidence_id, EvidenceId),
            sha256=ReviewSha256Digest(value.sha256.value),
            review_assignment_id=_clone_uuid_value(
                value.review_assignment_id, ReviewAssignmentId
            ),
            article_version_id=_clone_uuid_value(
                value.article_version_id, ArticleVersionId
            ),
        )
    except ReviewCompletionFailure:
        raise
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
    if rebuilt != value:
        fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
    return rebuilt


def _clone_checklist_result(value: object) -> ChecklistResult:
    if type(value) is not ChecklistResult:
        fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
    try:
        if (
            type(value.item_id) is not ChecklistItemId
            or type(value.status) is not ChecklistItemStatus
            or type(value.evidence) is not tuple
        ):
            fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
        comment = value.human_comment
        if comment is not None and type(comment) is not HumanComment:
            fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
        rebuilt = ChecklistResult(
            item_id=ChecklistItemId(value.item_id.value),
            status=value.status,
            evidence=tuple(_clone_evidence(item) for item in value.evidence),
            human_comment=None if comment is None else HumanComment(comment.value),
        )
    except ReviewCompletionFailure:
        raise
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
    if rebuilt != value:
        fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
    return rebuilt


def _clone_draft(value: object) -> ReviewDecisionDraft:
    if type(value) is not ReviewDecisionDraft:
        fail_review_completion(ReviewCompletionFailureCode.DECISION_INVALID)
    try:
        if (
            type(value.decision) is not ReviewDecisionKind
            or type(value.summary) is not DecisionSummary
            or type(value.checklist_results) is not tuple
        ):
            fail_review_completion(ReviewCompletionFailureCode.DECISION_INVALID)
        rebuilt = ReviewDecisionDraft(
            review_assignment_id=_clone_uuid_value(
                value.review_assignment_id, ReviewAssignmentId
            ),
            article_version_id=_clone_uuid_value(
                value.article_version_id, ArticleVersionId
            ),
            decision=value.decision,
            summary=DecisionSummary(value.summary.value),
            checklist_version=value.checklist_version,
            checklist_sha256=value.checklist_sha256,
            checklist_results=tuple(
                _clone_checklist_result(item) for item in value.checklist_results
            ),
        )
    except ReviewCompletionFailure:
        raise
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.DECISION_INVALID)
    if rebuilt != value:
        fail_review_completion(ReviewCompletionFailureCode.DECISION_INVALID)
    return rebuilt


def _assignment_payload(value: ReviewAssignment) -> dict[str, object]:
    assignment = _clone_assignment(value)
    reference = assignment.completion_decision_reference
    return {
        "article_version_id": str(assignment.article_version_id.value),
        "assigned_by": str(assignment.assigned_by.value),
        "assigned_to": str(assignment.assigned_to.value),
        "assignment_id": str(assignment.assignment_id.value),
        "cancelled_at": (
            None
            if assignment.cancelled_at is None
            else _timestamp_text(assignment.cancelled_at)
        ),
        "completed_at": (
            None
            if assignment.completed_at is None
            else _timestamp_text(assignment.completed_at)
        ),
        "completion_decision_reference": (
            None
            if reference is None
            else {
                "article_version_id": str(reference.article_version_id.value),
                "decision_id": str(reference.decision_id.value),
                "review_assignment_id": str(reference.review_assignment_id.value),
            }
        ),
        "created_at": _timestamp_text(assignment.created_at),
        "lock_version": assignment.lock_version,
        "priority": assignment.priority,
        "review_type": assignment.review_type.value,
        "started_at": (
            None
            if assignment.started_at is None
            else _timestamp_text(assignment.started_at)
        ),
        "status": assignment.status.value,
        "updated_at": _timestamp_text(assignment.updated_at),
    }


def assignment_sha256(value: ReviewAssignment) -> Sha256Digest:
    return _digest(_assignment_payload(value))


def _evidence_payload(value: EvidenceReference) -> dict[str, str]:
    reference = _clone_evidence(value)
    return {
        "article_version_id": str(reference.article_version_id.value),
        "evidence_id": str(reference.evidence_id.value),
        "review_assignment_id": str(reference.review_assignment_id.value),
        "sha256": reference.sha256.value,
    }


def _checklist_payload(value: ChecklistResult) -> dict[str, object]:
    result = _clone_checklist_result(value)
    return {
        "evidence": [_evidence_payload(item) for item in result.evidence],
        "human_comment": (
            None if result.human_comment is None else result.human_comment.value
        ),
        "item_id": result.item_id.value,
        "status": result.status.value,
    }


def policy_finding_snapshot_sha256(
    report: PolicyEvaluationReportV2,
) -> Sha256Digest:
    if type(report) is not PolicyEvaluationReportV2:
        fail_review_completion(ReviewCompletionFailureCode.POLICY_REPORT_INVALID)
    try:
        report.require_valid()
        return _digest(
            {
                "evaluation_findings": [item.value for item in report.findings],
                "policy_findings": [
                    {
                        "blocking": item.is_blocking,
                        "policy_id": item.policy_id,
                        "resolution": item.resolution.value,
                        "severity": item.severity.value,
                    }
                    for item in report.policy_findings
                ],
                "profile": "ST0901_ST0805_FINDING_SNAPSHOT_V2",
                "report_sha256": report.report_sha256.value,
                "waiver_evaluations": [
                    {
                        "disposition": item.disposition.value,
                        "effective": item.effective,
                        "policy_id": item.policy_id,
                    }
                    for item in report.waiver_evaluations
                ],
            }
        )
    except ReviewCompletionFailure:
        raise
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.POLICY_REPORT_INVALID)


def policy_receipt_sha256(
    receipt: PolicyEvaluationRecordReceiptV2,
) -> Sha256Digest:
    if type(receipt) is not PolicyEvaluationRecordReceiptV2:
        fail_review_completion(ReviewCompletionFailureCode.POLICY_RECEIPT_INVALID)
    try:
        receipt.require_valid()
        return _digest(
            {
                "apply_authorized": receipt.apply_authorized,
                "approval_authorized": receipt.approval_authorized,
                "profile": "ST0901_ST0805_POLICY_RECEIPT_V2",
                "publication_authorized": receipt.publication_authorized,
                "ranking_override_authorized": receipt.ranking_override_authorized,
                "report_sha256": receipt.report_sha256.value,
                "sequence": receipt.sequence,
            }
        )
    except ReviewCompletionFailure:
        raise
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.POLICY_RECEIPT_INVALID)


def _policy_binding(
    *,
    assignment: ReviewAssignment,
    report: PolicyEvaluationReportV2,
    receipt: PolicyEvaluationRecordReceiptV2,
) -> tuple[Sha256Digest, Sha256Digest, Sha256Digest]:
    if type(report) is not PolicyEvaluationReportV2:
        fail_review_completion(ReviewCompletionFailureCode.POLICY_REPORT_INVALID)
    if type(receipt) is not PolicyEvaluationRecordReceiptV2:
        fail_review_completion(ReviewCompletionFailureCode.POLICY_RECEIPT_INVALID)
    try:
        report.require_valid()
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.POLICY_REPORT_INVALID)
    try:
        receipt.require_valid()
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.POLICY_RECEIPT_INVALID)
    if receipt.report_sha256 != report.report_sha256:
        fail_review_completion(ReviewCompletionFailureCode.POLICY_BINDING_MISMATCH)
    article_version = report.article_version_id
    if (
        type(article_version) is not EditorialArticleVersionId
        or type(article_version.value) is not UUID
        or article_version.value != assignment.article_version_id.value
    ):
        fail_review_completion(ReviewCompletionFailureCode.POLICY_BINDING_MISMATCH)
    return (
        Sha256Digest(report.report_sha256.value),
        policy_receipt_sha256(receipt),
        policy_finding_snapshot_sha256(report),
    )


def _policy_clear_for_approve(report: PolicyEvaluationReportV2) -> bool:
    return (
        report.status is PolicyEvaluationStatusV2.LOCAL_EVALUATED
        and report.findings == ()
        and report.policy_findings == ()
        and report.waiver_evaluations == ()
        and report.local_eligibility is True
        and report.quality_threshold_met is True
        and report.quality_floors_met is True
        and report.policy_rules_passed is True
        and report.zero_tolerance_clear is True
        and report.quality_gates_passed is True
        and report.predecessors_available is True
        and report.approval_authorized is False
        and report.waiver_apply_authorized is False
        and report.merge_authorized is False
        and report.recommendation_override_authorized is False
        and report.ranking_override_authorized is False
        and report.publication_authorized is False
        and report.activation_authorized is False
        and report.production_eligible is False
    )


def _normalize_checklist(
    assignment: ReviewAssignment,
    draft: ReviewDecisionDraft,
) -> tuple[ChecklistResult, ...]:
    if (
        draft.checklist_version != HUMAN_REVIEW_CHECKLIST_VERSION
        or draft.checklist_sha256 != HUMAN_REVIEW_CHECKLIST_SHA256
        or len(draft.checklist_results) != len(HUMAN_REVIEW_CHECKLIST_IDS)
    ):
        fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
    by_id: dict[str, ChecklistResult] = {}
    for observed in draft.checklist_results:
        result = _clone_checklist_result(observed)
        item_id = result.item_id.value
        if item_id in by_id or item_id not in HUMAN_REVIEW_CHECKLIST_IDS:
            fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
        if result.status is ChecklistItemStatus.NOT_APPLICABLE_WITH_REASON:
            # Canonical checklist V0.1 has no blocker/applicability mapping.  A
            # V2 implementation must not invent one.
            fail_review_completion(
                ReviewCompletionFailureCode.CHECKLIST_APPLICABILITY_UNRESOLVED
            )
        for evidence in result.evidence:
            if evidence.review_assignment_id != assignment.assignment_id:
                fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
            if evidence.article_version_id != assignment.article_version_id:
                fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
        by_id[item_id] = result
    if set(by_id) != set(HUMAN_REVIEW_CHECKLIST_IDS):
        fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
    return tuple(by_id[item_id] for item_id in HUMAN_REVIEW_CHECKLIST_IDS)


@dataclass(frozen=True, slots=True, repr=False)
class PolicyBoundReviewDecisionV2(_Redacted):
    review_assignment_id: ReviewAssignmentId
    article_version_id: ArticleVersionId
    decision: ReviewDecisionKind
    summary: DecisionSummary
    checklist_version: str
    checklist_sha256: str
    checklist_results: tuple[ChecklistResult, ...]
    policy_report_sha256: Sha256Digest
    policy_receipt_sha256: Sha256Digest
    policy_receipt_sequence: int
    finding_snapshot_sha256: Sha256Digest
    decision_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.review_assignment_id) is not ReviewAssignmentId
            or type(self.article_version_id) is not ArticleVersionId
            or type(self.decision) is not ReviewDecisionKind
            or type(self.summary) is not DecisionSummary
            or type(self.checklist_version) is not str
            or self.checklist_version != HUMAN_REVIEW_CHECKLIST_VERSION
            or type(self.checklist_sha256) is not str
            or self.checklist_sha256 != HUMAN_REVIEW_CHECKLIST_SHA256
            or type(self.checklist_results) is not tuple
            or len(self.checklist_results) != len(HUMAN_REVIEW_CHECKLIST_IDS)
            or type(self.policy_report_sha256) is not Sha256Digest
            or type(self.policy_receipt_sha256) is not Sha256Digest
            or type(self.policy_receipt_sequence) is not int
            or not 1 <= self.policy_receipt_sequence <= _MAX_SEQUENCE
            or type(self.finding_snapshot_sha256) is not Sha256Digest
        ):
            fail_review_completion(ReviewCompletionFailureCode.DECISION_INVALID)
        _clone_uuid_value(self.review_assignment_id, ReviewAssignmentId)
        _clone_uuid_value(self.article_version_id, ArticleVersionId)
        try:
            summary = DecisionSummary(self.summary.value)
        except Exception:
            fail_review_completion(ReviewCompletionFailureCode.DECISION_INVALID)
        normalized = tuple(
            _clone_checklist_result(item) for item in self.checklist_results
        )
        if (
            tuple(item.item_id.value for item in normalized)
            != HUMAN_REVIEW_CHECKLIST_IDS
        ):
            fail_review_completion(ReviewCompletionFailureCode.CHECKLIST_INVALID)
        if any(
            item.status is ChecklistItemStatus.NOT_APPLICABLE_WITH_REASON
            for item in normalized
        ):
            fail_review_completion(
                ReviewCompletionFailureCode.CHECKLIST_APPLICABILITY_UNRESOLVED
            )
        if self.decision is ReviewDecisionKind.APPROVE and any(
            item.status is not ChecklistItemStatus.PASS for item in normalized
        ):
            fail_review_completion(
                ReviewCompletionFailureCode.APPROVE_CHECKLIST_NOT_CLEAR
            )
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "checklist_results", normalized)
        object.__setattr__(self, "decision_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "article_version_id": str(self.article_version_id.value),
            "checklist_results": [
                _checklist_payload(item) for item in self.checklist_results
            ],
            "checklist_sha256": self.checklist_sha256,
            "checklist_version": self.checklist_version,
            "decision": self.decision.value,
            "finding_snapshot_sha256": self.finding_snapshot_sha256.value,
            "policy_receipt_sequence": self.policy_receipt_sequence,
            "policy_receipt_sha256": self.policy_receipt_sha256.value,
            "policy_report_sha256": self.policy_report_sha256.value,
            "profile": PROFILE,
            "review_assignment_id": str(self.review_assignment_id.value),
            "summary": self.summary.value,
        }

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        payload = self._payload()
        payload["decision_sha256"] = self.decision_sha256.value
        return _canonical_bytes(payload)

    def require_valid(self) -> None:
        rebuilt = PolicyBoundReviewDecisionV2(
            review_assignment_id=self.review_assignment_id,
            article_version_id=self.article_version_id,
            decision=self.decision,
            summary=self.summary,
            checklist_version=self.checklist_version,
            checklist_sha256=self.checklist_sha256,
            checklist_results=self.checklist_results,
            policy_report_sha256=self.policy_report_sha256,
            policy_receipt_sha256=self.policy_receipt_sha256,
            policy_receipt_sequence=self.policy_receipt_sequence,
            finding_snapshot_sha256=self.finding_snapshot_sha256,
        )
        if rebuilt.decision_sha256 != self.decision_sha256:
            fail_review_completion(ReviewCompletionFailureCode.OUTCOME_MISMATCH)


def validate_review_decision_v2(
    *,
    assignment: ReviewAssignment,
    draft: ReviewDecisionDraft,
    policy_report: PolicyEvaluationReportV2,
    policy_receipt: PolicyEvaluationRecordReceiptV2,
) -> PolicyBoundReviewDecisionV2:
    current = _clone_assignment(assignment)
    candidate = _clone_draft(draft)
    if current.status is not ReviewAssignmentState.IN_PROGRESS:
        fail_review_completion(ReviewCompletionFailureCode.ASSIGNMENT_INVALID)
    if candidate.review_assignment_id != current.assignment_id:
        fail_review_completion(ReviewCompletionFailureCode.DECISION_INVALID)
    if candidate.article_version_id != current.article_version_id:
        fail_review_completion(ReviewCompletionFailureCode.DECISION_INVALID)
    checklist = _normalize_checklist(current, candidate)
    report_digest, receipt_digest, finding_digest = _policy_binding(
        assignment=current,
        report=policy_report,
        receipt=policy_receipt,
    )
    if candidate.decision is ReviewDecisionKind.APPROVE:
        if any(item.status is not ChecklistItemStatus.PASS for item in checklist):
            fail_review_completion(
                ReviewCompletionFailureCode.APPROVE_CHECKLIST_NOT_CLEAR
            )
        if not _policy_clear_for_approve(policy_report):
            fail_review_completion(ReviewCompletionFailureCode.APPROVE_POLICY_NOT_CLEAR)
    return PolicyBoundReviewDecisionV2(
        review_assignment_id=current.assignment_id,
        article_version_id=current.article_version_id,
        decision=candidate.decision,
        summary=candidate.summary,
        checklist_version=candidate.checklist_version,
        checklist_sha256=candidate.checklist_sha256,
        checklist_results=checklist,
        policy_report_sha256=report_digest,
        policy_receipt_sha256=receipt_digest,
        policy_receipt_sequence=policy_receipt.sequence,
        finding_snapshot_sha256=finding_digest,
    )


@dataclass(frozen=True, slots=True, repr=False)
class ReviewCompletionRequestV2(_Redacted):
    assignment: ReviewAssignment
    draft: ReviewDecisionDraft
    policy_report: PolicyEvaluationReportV2
    policy_receipt: PolicyEvaluationRecordReceiptV2
    decision_id: ReviewDecisionId
    decided_at: UtcTimestamp
    audit_event_id: UUID
    idempotency_key: IdempotencyKey
    assignment_sha256: Sha256Digest = field(init=False)
    decision_sha256: Sha256Digest = field(init=False)
    idempotency_key_sha256: Sha256Digest = field(init=False)
    request_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        assignment = _clone_assignment(self.assignment)
        draft = _clone_draft(self.draft)
        decision_id = _clone_uuid_value(self.decision_id, ReviewDecisionId)
        decided_at = _clone_timestamp(self.decided_at)
        audit_event_id = _uuid7(self.audit_event_id)
        if type(self.idempotency_key) is not IdempotencyKey:
            fail_review_completion()
        try:
            idempotency_key = IdempotencyKey(self.idempotency_key.value)
        except Exception:
            fail_review_completion()
        validated = validate_review_decision_v2(
            assignment=assignment,
            draft=draft,
            policy_report=self.policy_report,
            policy_receipt=self.policy_receipt,
        )
        if decided_at.value < assignment.updated_at.value:
            fail_review_completion(ReviewCompletionFailureCode.ASSIGNMENT_INVALID)
        object.__setattr__(self, "assignment", assignment)
        object.__setattr__(self, "draft", draft)
        object.__setattr__(self, "decision_id", decision_id)
        object.__setattr__(self, "decided_at", decided_at)
        object.__setattr__(self, "audit_event_id", audit_event_id)
        object.__setattr__(self, "idempotency_key", idempotency_key)
        object.__setattr__(self, "assignment_sha256", assignment_sha256(assignment))
        object.__setattr__(self, "decision_sha256", validated.decision_sha256)
        key_digest = Sha256Digest(
            hashlib.sha256(
                idempotency_key.value.encode("ascii", errors="strict")
            ).hexdigest()
        )
        object.__setattr__(self, "idempotency_key_sha256", key_digest)
        object.__setattr__(self, "request_sha256", _digest(self._payload(validated)))

    @property
    def validated_decision(self) -> PolicyBoundReviewDecisionV2:
        return validate_review_decision_v2(
            assignment=self.assignment,
            draft=self.draft,
            policy_report=self.policy_report,
            policy_receipt=self.policy_receipt,
        )

    def _payload(self, validated: PolicyBoundReviewDecisionV2) -> dict[str, object]:
        return {
            "article_version_id": str(self.assignment.article_version_id.value),
            "assignment_id": str(self.assignment.assignment_id.value),
            "assignment_sha256": self.assignment_sha256.value,
            "audit_event_id": str(self.audit_event_id),
            "decided_at": _timestamp_text(self.decided_at),
            "decision_id": str(self.decision_id.value),
            "decision_sha256": validated.decision_sha256.value,
            "finding_snapshot_sha256": validated.finding_snapshot_sha256.value,
            "operation": OPERATION,
            "policy_receipt_sha256": validated.policy_receipt_sha256.value,
            "policy_report_sha256": validated.policy_report_sha256.value,
            "profile": PROFILE,
        }

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        payload = self._payload(self.validated_decision)
        payload["request_sha256"] = self.request_sha256.value
        return _canonical_bytes(payload)

    def require_valid(self) -> None:
        validated = self.validated_decision
        expected_assignment = assignment_sha256(self.assignment)
        expected_key = Sha256Digest(
            hashlib.sha256(
                IdempotencyKey(self.idempotency_key.value).value.encode(
                    "ascii", errors="strict"
                )
            ).hexdigest()
        )
        expected_request = _digest(self._payload(validated))
        _clone_uuid_value(self.decision_id, ReviewDecisionId)
        _clone_timestamp(self.decided_at)
        _uuid7(self.audit_event_id)
        if (
            expected_assignment != self.assignment_sha256
            or validated.decision_sha256 != self.decision_sha256
            or expected_key != self.idempotency_key_sha256
            or expected_request != self.request_sha256
            or self.decided_at.value < self.assignment.updated_at.value
        ):
            fail_review_completion(ReviewCompletionFailureCode.OUTCOME_MISMATCH)


def _clone_identity(value: object) -> RecordedIdentityProjection:
    if type(value) is not RecordedIdentityProjection:
        fail_review_completion(ReviewCompletionFailureCode.AUTHORIZATION_INVALID)
    try:
        value.require_valid()
        return RecordedIdentityProjection(
            principal_id=_clone_uuid_value(value.principal_id, PrincipalId),
            subject_kind=value.subject_kind,
            subject_status=value.subject_status,
        )
    except ReviewCompletionFailure:
        raise
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.AUTHORIZATION_INVALID)


def _identity_payload(value: RecordedIdentityProjection) -> dict[str, str]:
    identity = _clone_identity(value)
    return {
        "principal_id": str(identity.principal_id.value),
        "subject_kind": identity.subject_kind.value,
        "subject_status": identity.subject_status.value,
    }


@dataclass(frozen=True, slots=True, repr=False)
class RecordedReviewCompletionAuthorizationV2(_Redacted):
    request_sha256: Sha256Digest
    actor: RecordedIdentityProjection
    action: str = ACTION
    permission: str = ACTION
    real_authentication_verified: bool = False
    durable_authorization_verified: bool = False
    external_authority: bool = False
    authorization_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.request_sha256) is not Sha256Digest
            or type(self.action) is not str
            or self.action != ACTION
            or type(self.permission) is not str
            or self.permission != ACTION
            or self.real_authentication_verified is not False
            or self.durable_authorization_verified is not False
            or self.external_authority is not False
        ):
            fail_review_completion(ReviewCompletionFailureCode.AUTHORIZATION_INVALID)
        actor = _clone_identity(self.actor)
        object.__setattr__(self, "actor", actor)
        object.__setattr__(self, "authorization_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "action": self.action,
            "actor": _identity_payload(self.actor),
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
        rebuilt = RecordedReviewCompletionAuthorizationV2(
            request_sha256=self.request_sha256,
            actor=self.actor,
            action=self.action,
            permission=self.permission,
            real_authentication_verified=self.real_authentication_verified,
            durable_authorization_verified=self.durable_authorization_verified,
            external_authority=self.external_authority,
        )
        if rebuilt.authorization_sha256 != self.authorization_sha256:
            fail_review_completion(ReviewCompletionFailureCode.AUTHORIZATION_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedCompletedReviewDecisionV2(_Redacted):
    decision_id: ReviewDecisionId
    decision: PolicyBoundReviewDecisionV2
    decided_by: PrincipalId
    decided_at: UtcTimestamp
    assignment_sha256: Sha256Digest
    record_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        decision_id = _clone_uuid_value(self.decision_id, ReviewDecisionId)
        if type(self.decision) is not PolicyBoundReviewDecisionV2:
            fail_review_completion(ReviewCompletionFailureCode.OUTCOME_MISMATCH)
        self.decision.require_valid()
        decided_by = _clone_uuid_value(self.decided_by, PrincipalId)
        decided_at = _clone_timestamp(self.decided_at)
        if type(self.assignment_sha256) is not Sha256Digest:
            fail_review_completion(ReviewCompletionFailureCode.OUTCOME_MISMATCH)
        object.__setattr__(self, "decision_id", decision_id)
        object.__setattr__(self, "decided_by", decided_by)
        object.__setattr__(self, "decided_at", decided_at)
        object.__setattr__(self, "record_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "assignment_sha256": self.assignment_sha256.value,
            "decided_at": _timestamp_text(self.decided_at),
            "decided_by": str(self.decided_by.value),
            "decision_id": str(self.decision_id.value),
            "decision_sha256": self.decision.decision_sha256.value,
            "finding_snapshot_sha256": self.decision.finding_snapshot_sha256.value,
            "policy_report_sha256": self.decision.policy_report_sha256.value,
            "profile": PROFILE,
        }

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        payload = self._payload()
        payload["record_sha256"] = self.record_sha256.value
        return _canonical_bytes(payload)

    def require_valid(self) -> None:
        rebuilt = RecordedCompletedReviewDecisionV2(
            decision_id=self.decision_id,
            decision=self.decision,
            decided_by=self.decided_by,
            decided_at=self.decided_at,
            assignment_sha256=self.assignment_sha256,
        )
        if rebuilt.record_sha256 != self.record_sha256:
            fail_review_completion(ReviewCompletionFailureCode.OUTCOME_MISMATCH)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedReviewCompletionAuditV2(_Redacted):
    event_id: UUID
    occurred_at: UtcTimestamp
    actor_id: PrincipalId
    assignment_id: ReviewAssignmentId
    article_version_id: ArticleVersionId
    decision_id: ReviewDecisionId
    request_sha256: Sha256Digest
    authorization_sha256: Sha256Digest
    record_sha256: Sha256Digest
    finding_snapshot_sha256: Sha256Digest
    audit_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        event_id = _uuid7(self.event_id)
        occurred_at = _clone_timestamp(self.occurred_at)
        actor_id = _clone_uuid_value(self.actor_id, PrincipalId)
        assignment_id = _clone_uuid_value(self.assignment_id, ReviewAssignmentId)
        article_version_id = _clone_uuid_value(
            self.article_version_id, ArticleVersionId
        )
        decision_id = _clone_uuid_value(self.decision_id, ReviewDecisionId)
        if any(
            type(item) is not Sha256Digest
            for item in (
                self.request_sha256,
                self.authorization_sha256,
                self.record_sha256,
                self.finding_snapshot_sha256,
            )
        ):
            fail_review_completion(ReviewCompletionFailureCode.OUTCOME_MISMATCH)
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "occurred_at", occurred_at)
        object.__setattr__(self, "actor_id", actor_id)
        object.__setattr__(self, "assignment_id", assignment_id)
        object.__setattr__(self, "article_version_id", article_version_id)
        object.__setattr__(self, "decision_id", decision_id)
        object.__setattr__(self, "audit_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "action": AUDIT_ACTION,
            "actor_id": str(self.actor_id.value),
            "article_version_id": str(self.article_version_id.value),
            "assignment_id": str(self.assignment_id.value),
            "authorization_sha256": self.authorization_sha256.value,
            "decision_id": str(self.decision_id.value),
            "event_id": str(self.event_id),
            "finding_snapshot_sha256": self.finding_snapshot_sha256.value,
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
        rebuilt = RecordedReviewCompletionAuditV2(
            event_id=self.event_id,
            occurred_at=self.occurred_at,
            actor_id=self.actor_id,
            assignment_id=self.assignment_id,
            article_version_id=self.article_version_id,
            decision_id=self.decision_id,
            request_sha256=self.request_sha256,
            authorization_sha256=self.authorization_sha256,
            record_sha256=self.record_sha256,
            finding_snapshot_sha256=self.finding_snapshot_sha256,
        )
        if rebuilt.audit_sha256 != self.audit_sha256:
            fail_review_completion(ReviewCompletionFailureCode.OUTCOME_MISMATCH)


@dataclass(frozen=True, slots=True, repr=False)
class ReviewCompletionResultV2(_Redacted):
    request_sha256: Sha256Digest
    authorization_sha256: Sha256Digest
    source_assignment_sha256: Sha256Digest
    record: RecordedCompletedReviewDecisionV2
    completed_assignment: ReviewAssignment
    audit: RecordedReviewCompletionAuditV2
    idempotency_key_sha256: Sha256Digest
    idempotency_receipt_sha256: Sha256Digest
    execution: ReviewCompletionExecution = ReviewCompletionExecution.RECORDED_ONLY
    readiness: ReviewCompletionReadiness = ReviewCompletionReadiness.NOT_READY
    review_decision_recorded: bool = True
    assignment_completed: bool = True
    final_approval_authorized: bool = False
    publication_snapshot_authorized: bool = False
    publication_authorized: bool = False
    release_authorized: bool = False
    production_authorized: bool = False
    formal_tst_011_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    formal_tst_012_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    formal_tst_020_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    live_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    staging_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    release_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    publication_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    production_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    result_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if any(
            type(item) is not Sha256Digest
            for item in (
                self.request_sha256,
                self.authorization_sha256,
                self.source_assignment_sha256,
                self.idempotency_key_sha256,
                self.idempotency_receipt_sha256,
            )
        ):
            fail_review_completion(ReviewCompletionFailureCode.OUTCOME_MISMATCH)
        if (
            type(self.record) is not RecordedCompletedReviewDecisionV2
            or type(self.completed_assignment) is not ReviewAssignment
            or type(self.audit) is not RecordedReviewCompletionAuditV2
        ):
            fail_review_completion(ReviewCompletionFailureCode.OUTCOME_MISMATCH)
        self.record.require_valid()
        completed = _clone_assignment(self.completed_assignment)
        self.audit.require_valid()
        reference = completed.completion_decision_reference
        if (
            completed.status is not ReviewAssignmentState.COMPLETED
            or reference is None
            or reference.decision_id != self.record.decision_id
            or reference.review_assignment_id
            != self.record.decision.review_assignment_id
            or reference.article_version_id != self.record.decision.article_version_id
            or self.record.assignment_sha256 != self.source_assignment_sha256
            or self.audit.request_sha256 != self.request_sha256
            or self.audit.authorization_sha256 != self.authorization_sha256
            or self.audit.record_sha256 != self.record.record_sha256
            or self.audit.finding_snapshot_sha256
            != self.record.decision.finding_snapshot_sha256
            or self.execution is not ReviewCompletionExecution.RECORDED_ONLY
            or self.readiness is not ReviewCompletionReadiness.NOT_READY
            or self.review_decision_recorded is not True
            or self.assignment_completed is not True
            or any(
                value is not False
                for value in (
                    self.final_approval_authorized,
                    self.publication_snapshot_authorized,
                    self.publication_authorized,
                    self.release_authorized,
                    self.production_authorized,
                )
            )
            or any(
                value is not ExternalGateStatus.NOT_EXECUTED
                for value in (
                    self.formal_tst_011_status,
                    self.formal_tst_012_status,
                    self.formal_tst_020_status,
                    self.live_status,
                    self.staging_status,
                    self.release_status,
                    self.publication_status,
                    self.production_status,
                )
            )
        ):
            fail_review_completion(ReviewCompletionFailureCode.OUTCOME_MISMATCH)
        object.__setattr__(self, "completed_assignment", completed)
        object.__setattr__(self, "result_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "assignment_completed": self.assignment_completed,
            "audit_sha256": self.audit.audit_sha256.value,
            "authorization_sha256": self.authorization_sha256.value,
            "completed_assignment_sha256": assignment_sha256(
                self.completed_assignment
            ).value,
            "execution": self.execution.value,
            "external_gates": {
                "formal_tst_011": self.formal_tst_011_status.value,
                "formal_tst_012": self.formal_tst_012_status.value,
                "formal_tst_020": self.formal_tst_020_status.value,
                "live": self.live_status.value,
                "production": self.production_status.value,
                "publication": self.publication_status.value,
                "release": self.release_status.value,
                "staging": self.staging_status.value,
            },
            "final_approval_authorized": self.final_approval_authorized,
            "idempotency_key_sha256": self.idempotency_key_sha256.value,
            "idempotency_receipt_sha256": self.idempotency_receipt_sha256.value,
            "profile": PROFILE,
            "production_authorized": self.production_authorized,
            "publication_authorized": self.publication_authorized,
            "publication_snapshot_authorized": self.publication_snapshot_authorized,
            "readiness": self.readiness.value,
            "record_sha256": self.record.record_sha256.value,
            "release_authorized": self.release_authorized,
            "request_sha256": self.request_sha256.value,
            "review_decision_recorded": self.review_decision_recorded,
            "source_assignment_sha256": self.source_assignment_sha256.value,
        }

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        payload = self._payload()
        payload["result_sha256"] = self.result_sha256.value
        return _canonical_bytes(payload)

    def require_valid(self) -> None:
        rebuilt = ReviewCompletionResultV2(
            request_sha256=self.request_sha256,
            authorization_sha256=self.authorization_sha256,
            source_assignment_sha256=self.source_assignment_sha256,
            record=self.record,
            completed_assignment=self.completed_assignment,
            audit=self.audit,
            idempotency_key_sha256=self.idempotency_key_sha256,
            idempotency_receipt_sha256=self.idempotency_receipt_sha256,
            execution=self.execution,
            readiness=self.readiness,
            review_decision_recorded=self.review_decision_recorded,
            assignment_completed=self.assignment_completed,
            final_approval_authorized=self.final_approval_authorized,
            publication_snapshot_authorized=self.publication_snapshot_authorized,
            publication_authorized=self.publication_authorized,
            release_authorized=self.release_authorized,
            production_authorized=self.production_authorized,
            formal_tst_011_status=self.formal_tst_011_status,
            formal_tst_012_status=self.formal_tst_012_status,
            formal_tst_020_status=self.formal_tst_020_status,
            live_status=self.live_status,
            staging_status=self.staging_status,
            release_status=self.release_status,
            publication_status=self.publication_status,
            production_status=self.production_status,
        )
        if rebuilt.result_sha256 != self.result_sha256:
            fail_review_completion(ReviewCompletionFailureCode.OUTCOME_MISMATCH)


def complete_review_workflow_v2(
    *,
    request: ReviewCompletionRequestV2,
    authorization: RecordedReviewCompletionAuthorizationV2,
) -> ReviewCompletionResultV2:
    if type(request) is not ReviewCompletionRequestV2:
        fail_review_completion()
    if type(authorization) is not RecordedReviewCompletionAuthorizationV2:
        fail_review_completion(ReviewCompletionFailureCode.AUTHORIZATION_INVALID)
    request.require_valid()
    authorization.require_valid()
    actor = authorization.actor
    if (
        authorization.request_sha256 != request.request_sha256
        or authorization.action != ACTION
        or authorization.permission != ACTION
    ):
        fail_review_completion(ReviewCompletionFailureCode.AUTHORIZATION_INVALID)
    if (
        actor.subject_kind is not RecordedSubjectKind.HUMAN
        or actor.subject_status is not RecordedSubjectStatus.ACTIVE
    ):
        fail_review_completion(ReviewCompletionFailureCode.REVIEWER_NOT_ACTIVE_HUMAN)
    if actor.principal_id != request.assignment.assigned_to:
        fail_review_completion(ReviewCompletionFailureCode.REVIEWER_ASSIGNMENT_MISMATCH)
    decision = request.validated_decision
    record = RecordedCompletedReviewDecisionV2(
        decision_id=request.decision_id,
        decision=decision,
        decided_by=actor.principal_id,
        decided_at=request.decided_at,
        assignment_sha256=request.assignment_sha256,
    )
    reference = ReviewDecisionReference(
        decision_id=request.decision_id,
        review_assignment_id=request.assignment.assignment_id,
        article_version_id=request.assignment.article_version_id,
    )
    try:
        completed = transition_review_assignment(
            request.assignment,
            ReviewAssignmentState.COMPLETED,
            request.decided_at,
            reference,
        )
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.ASSIGNMENT_INVALID)
    audit = RecordedReviewCompletionAuditV2(
        event_id=request.audit_event_id,
        occurred_at=request.decided_at,
        actor_id=actor.principal_id,
        assignment_id=request.assignment.assignment_id,
        article_version_id=request.assignment.article_version_id,
        decision_id=request.decision_id,
        request_sha256=request.request_sha256,
        authorization_sha256=authorization.authorization_sha256,
        record_sha256=record.record_sha256,
        finding_snapshot_sha256=decision.finding_snapshot_sha256,
    )
    receipt = _digest(
        {
            "idempotency_key_sha256": request.idempotency_key_sha256.value,
            "operation": OPERATION,
            "profile": PROFILE,
            "record_sha256": record.record_sha256.value,
            "request_sha256": request.request_sha256.value,
        }
    )
    return ReviewCompletionResultV2(
        request_sha256=request.request_sha256,
        authorization_sha256=authorization.authorization_sha256,
        source_assignment_sha256=request.assignment_sha256,
        record=record,
        completed_assignment=completed,
        audit=audit,
        idempotency_key_sha256=request.idempotency_key_sha256,
        idempotency_receipt_sha256=receipt,
    )


__all__ = (
    "ACTION",
    "AUDIT_ACTION",
    "ExternalGateStatus",
    "OPERATION",
    "PROFILE",
    "PolicyBoundReviewDecisionV2",
    "RecordedCompletedReviewDecisionV2",
    "RecordedReviewCompletionAuditV2",
    "RecordedReviewCompletionAuthorizationV2",
    "ReviewCompletionExecution",
    "ReviewCompletionFailure",
    "ReviewCompletionFailureCode",
    "ReviewCompletionReadiness",
    "ReviewCompletionRequestV2",
    "ReviewCompletionResultV2",
    "assignment_sha256",
    "complete_review_workflow_v2",
    "fail_review_completion",
    "policy_finding_snapshot_sha256",
    "policy_receipt_sha256",
    "validate_review_decision_v2",
)
