"""Strict recorded-synthetic adapter for ST-0901 review completion V2."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from threading import RLock
from typing import Any, NoReturn, SupportsIndex, cast, final
import unicodedata
from uuid import RFC_4122, UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.policy_engine_v2 import (
    PolicyEvaluationRecordReceiptV2,
    evaluate_editorial_policy_v2,
)
from raos.domain.portfolio.workflow import IdempotencyKey
from raos.domain.publishing.review_completion_v2 import (
    OPERATION,
    PROFILE,
    RecordedReviewCompletionAuthorizationV2,
    ReviewCompletionFailure,
    ReviewCompletionFailureCode,
    ReviewCompletionRequestV2,
    ReviewCompletionResultV2,
    complete_review_workflow_v2,
    fail_review_completion,
    policy_finding_snapshot_sha256,
)
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
    PrincipalId,
    ReviewAssignmentId,
    ReviewAssignmentState,
    ReviewDecisionDraft,
    ReviewDecisionId,
    ReviewDecisionKind,
    ReviewType,
    UtcTimestamp,
    create_review_assignment,
    transition_review_assignment,
)
from raos.domain.shared.persistence import Sha256Digest
from raos.adapters.recorded_policy_engine import load_recorded_policy_fixture


_MAX_FIXTURE_BYTES = 128 * 1024
_MAX_JSON_NODES = 4096
_MAX_STEPS = 10_000
_ROOT_KEYS = (
    "schema_version",
    "profile",
    "local_status",
    "fixture_id",
    "assignment",
    "decision",
    "policy",
    "authority",
)
_ASSIGNMENT_KEYS = (
    "assignment_id",
    "article_version_id",
    "assigned_by",
    "assigned_to",
    "review_type",
    "priority",
    "created_at",
    "started_at",
)
_DECISION_KEYS = (
    "decision_id",
    "audit_event_id",
    "decided_at",
    "decision",
    "summary",
    "checklist_version",
    "checklist_sha256",
    "checklist_status",
    "idempotency_key",
)
_POLICY_KEYS = (
    "fixture_sha256",
    "report_sha256",
    "receipt_sequence",
    "finding_snapshot_sha256",
)
_AUTHORITY_KEYS = (
    "recorded_synthetic_only",
    "final_approval_authorized",
    "publication_snapshot_authorized",
    "publication_authorized",
    "release_authorized",
    "production_authorized",
)


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st0901-v2-adapter>)"

    def __str__(self) -> str:
        return "<redacted-st0901-v2-adapter>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded review completion serialization is denied")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or not key or len(key) > 96 or key in result:
            fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
        result[key] = value
    return result


def _mapping(value: object, keys: tuple[str, ...]) -> Mapping[str, object]:
    if type(value) is not dict:
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    observed = cast(dict[str, object], value)
    if tuple(observed) != keys:
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    return observed


def _bounded_tree(value: object) -> None:
    stack = [value]
    count = 0
    while stack:
        current = stack.pop()
        count += 1
        if count > _MAX_JSON_NODES:
            fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
        if type(current) is dict:
            stack.extend(cast(dict[str, object], current).values())
        elif type(current) is list:
            stack.extend(cast(list[object], current))
        elif type(current) not in {str, int, bool, type(None)}:
            fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)


def _string(value: object, *, maximum: int = 512) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or unicodedata.normalize("NFC", value) != value
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    return value


def _integer(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    return value


def _uuid7(value: object) -> UUID:
    text = _string(value, maximum=36)
    try:
        parsed = UUID(text)
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    if str(parsed) != text or parsed.version != 7 or parsed.variant != RFC_4122:
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    return parsed


def _sha(value: object) -> str:
    text = _string(value, maximum=64)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    return text


def _instant(value: object) -> UtcTimestamp:
    text = _string(value, maximum=32)
    if not text.endswith("Z"):
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    if (
        parsed.tzinfo is not timezone.utc
        or parsed.fold
        or parsed.isoformat().replace("+00:00", "Z") != text
    ):
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    return UtcTimestamp(parsed)


def _same_request(left: object, right: object) -> bool:
    if (
        type(left) is not ReviewCompletionRequestV2
        or type(right) is not ReviewCompletionRequestV2
    ):
        return False
    try:
        left.require_valid()
        right.require_valid()
        return (
            left.idempotency_key_sha256 == right.idempotency_key_sha256
            and left.canonical_bytes() == right.canonical_bytes()
        )
    except Exception:
        return False


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedReviewCompletionStep(_Redacted):
    """One exact local human decision and assignment-completion script step."""

    request: ReviewCompletionRequestV2
    actor: RecordedIdentityProjection
    authorization: RecordedReviewCompletionAuthorizationV2 = field(init=False)
    result: ReviewCompletionResultV2 = field(init=False)
    request_bytes: bytes = field(init=False, repr=False)
    authorization_bytes: bytes = field(init=False, repr=False)
    result_bytes: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.request) is not ReviewCompletionRequestV2
            or type(self.actor) is not RecordedIdentityProjection
        ):
            fail_review_completion()
        self.request.require_valid()
        try:
            self.actor.require_valid()
        except Exception:
            fail_review_completion(ReviewCompletionFailureCode.AUTHORIZATION_INVALID)
        authorization = RecordedReviewCompletionAuthorizationV2(
            request_sha256=self.request.request_sha256,
            actor=self.actor,
        )
        result = complete_review_workflow_v2(
            request=self.request,
            authorization=authorization,
        )
        object.__setattr__(self, "authorization", authorization)
        object.__setattr__(self, "result", result)
        object.__setattr__(self, "request_bytes", self.request.canonical_bytes())
        object.__setattr__(self, "authorization_bytes", authorization.canonical_bytes())
        object.__setattr__(self, "result_bytes", result.canonical_bytes())

    def require_valid(self) -> None:
        self.request.require_valid()
        self.authorization.require_valid()
        self.result.require_valid()
        expected_authorization = RecordedReviewCompletionAuthorizationV2(
            request_sha256=self.request.request_sha256,
            actor=self.actor,
        )
        expected_result = complete_review_workflow_v2(
            request=self.request,
            authorization=expected_authorization,
        )
        if (
            self.request.canonical_bytes() != self.request_bytes
            or expected_authorization.canonical_bytes() != self.authorization_bytes
            or self.authorization.canonical_bytes() != self.authorization_bytes
            or expected_result.canonical_bytes() != self.result_bytes
            or self.result.canonical_bytes() != self.result_bytes
        ):
            fail_review_completion(ReviewCompletionFailureCode.OUTCOME_MISMATCH)


@final
class RecordedReviewCompletionAdapter(_Redacted):
    """Process-local scripted authorization, idempotency, audit, and completion."""

    __slots__ = ("_steps", "_cursor", "_replays", "_lock")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        steps: tuple[RecordedReviewCompletionStep, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(steps) is not tuple
            or not 1 <= len(steps) <= _MAX_STEPS
            or any(type(step) is not RecordedReviewCompletionStep for step in steps)
        ):
            fail_review_completion(
                ReviewCompletionFailureCode.LOCAL_ENVIRONMENT_REQUIRED
            )
        seen: set[tuple[str, str]] = set()
        for step in steps:
            step.require_valid()
            identity = (OPERATION, step.request.idempotency_key_sha256.value)
            if identity in seen:
                fail_review_completion(ReviewCompletionFailureCode.IDEMPOTENCY_CONFLICT)
            seen.add(identity)
        self._steps = steps
        self._cursor = 0
        self._replays: dict[
            tuple[str, str],
            tuple[
                bytes,
                bytes,
                RecordedReviewCompletionAuthorizationV2,
                ReviewCompletionResultV2,
            ],
        ] = {}
        self._lock = RLock()

    def _identity(self, request: ReviewCompletionRequestV2) -> tuple[str, str]:
        request.require_valid()
        return OPERATION, request.idempotency_key_sha256.value

    def issue_authorization(
        self,
        request: ReviewCompletionRequestV2,
    ) -> RecordedReviewCompletionAuthorizationV2:
        if type(request) is not ReviewCompletionRequestV2:
            fail_review_completion()
        identity = self._identity(request)
        with self._lock:
            replay = self._replays.get(identity)
            if replay is not None:
                request_bytes, authorization_bytes, authorization, _result = replay
                if (
                    request.canonical_bytes() != request_bytes
                    or authorization.canonical_bytes() != authorization_bytes
                ):
                    fail_review_completion(
                        ReviewCompletionFailureCode.IDEMPOTENCY_CONFLICT
                    )
                return authorization
            if self._cursor >= len(self._steps):
                fail_review_completion(
                    ReviewCompletionFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            step = self._steps[self._cursor]
            step.require_valid()
            if identity == self._identity(step.request) and not _same_request(
                request, step.request
            ):
                fail_review_completion(ReviewCompletionFailureCode.IDEMPOTENCY_CONFLICT)
            if not _same_request(request, step.request):
                fail_review_completion(
                    ReviewCompletionFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            return step.authorization

    def exchange(
        self,
        authorization: RecordedReviewCompletionAuthorizationV2,
        request: ReviewCompletionRequestV2,
    ) -> ReviewCompletionResultV2:
        if (
            type(authorization) is not RecordedReviewCompletionAuthorizationV2
            or type(request) is not ReviewCompletionRequestV2
        ):
            fail_review_completion()
        identity = self._identity(request)
        with self._lock:
            replay = self._replays.get(identity)
            if replay is not None:
                request_bytes, authorization_bytes, retained_authorization, result = (
                    replay
                )
                if (
                    request.canonical_bytes() != request_bytes
                    or authorization.canonical_bytes() != authorization_bytes
                    or retained_authorization.canonical_bytes() != authorization_bytes
                ):
                    fail_review_completion(
                        ReviewCompletionFailureCode.IDEMPOTENCY_CONFLICT
                    )
                result.require_valid()
                return result
            if self._cursor >= len(self._steps):
                fail_review_completion(
                    ReviewCompletionFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            step = self._steps[self._cursor]
            step.require_valid()
            if not _same_request(request, step.request):
                fail_review_completion(
                    ReviewCompletionFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            if authorization.canonical_bytes() != step.authorization_bytes:
                fail_review_completion(
                    ReviewCompletionFailureCode.AUTHORIZATION_INVALID
                )
            self._replays[identity] = (
                step.request_bytes,
                step.authorization_bytes,
                step.authorization,
                step.result,
            )
            self._cursor += 1
            return step.result

    @property
    def consumed_steps(self) -> int:
        with self._lock:
            return self._cursor


def load_recorded_review_completion_fixture(
    payload: bytes,
    *,
    policy_fixture: bytes,
) -> RecordedReviewCompletionStep:
    """Decode one bounded fixture and bind its exact ST-0805 report/receipt."""

    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > _MAX_FIXTURE_BYTES
        or type(policy_fixture) is not bytes
        or not policy_fixture
    ):
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    try:
        document = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _value: fail_review_completion(
                ReviewCompletionFailureCode.FIXTURE_INVALID
            ),
        )
    except ReviewCompletionFailure:
        raise
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    _bounded_tree(document)
    root = _mapping(document, _ROOT_KEYS)
    if (
        _integer(root["schema_version"], minimum=2, maximum=2) != 2
        or _string(root["profile"]) != PROFILE
        or _string(root["local_status"]) != "LOCAL_IMPLEMENTATION_COMPLETE"
    ):
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    _uuid7(root["fixture_id"])
    assignment_seed = _mapping(root["assignment"], _ASSIGNMENT_KEYS)
    decision_seed = _mapping(root["decision"], _DECISION_KEYS)
    policy_seed = _mapping(root["policy"], _POLICY_KEYS)
    authority = _mapping(root["authority"], _AUTHORITY_KEYS)
    if _boolean(authority["recorded_synthetic_only"]) is not True or any(
        _boolean(authority[key]) is not False for key in _AUTHORITY_KEYS[1:]
    ):
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)

    expected_policy_sha = _sha(policy_seed["fixture_sha256"])
    if hashlib.sha256(policy_fixture).hexdigest() != expected_policy_sha:
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    try:
        envelope = load_recorded_policy_fixture(policy_fixture)
        report = evaluate_editorial_policy_v2(envelope)
        report.require_valid()
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    if report.report_sha256.value != _sha(policy_seed["report_sha256"]):
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    sequence = _integer(
        policy_seed["receipt_sequence"], minimum=1, maximum=(1 << 53) - 1
    )
    receipt = PolicyEvaluationRecordReceiptV2(
        sequence=sequence,
        report_sha256=Sha256Digest(report.report_sha256.value),
    )
    receipt.require_valid()
    if policy_finding_snapshot_sha256(report).value != _sha(
        policy_seed["finding_snapshot_sha256"]
    ):
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)

    created_at = _instant(assignment_seed["created_at"])
    started_at = _instant(assignment_seed["started_at"])
    try:
        review_type = ReviewType(_string(assignment_seed["review_type"]))
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    assigned = create_review_assignment(
        assignment_id=ReviewAssignmentId(_uuid7(assignment_seed["assignment_id"])),
        article_version_id=ArticleVersionId(
            _uuid7(assignment_seed["article_version_id"])
        ),
        review_type=review_type,
        assigned_by=PrincipalId(_uuid7(assignment_seed["assigned_by"])),
        assigned_to=PrincipalId(_uuid7(assignment_seed["assigned_to"])),
        priority=_integer(assignment_seed["priority"], minimum=0, maximum=100),
        created_at=created_at,
    )
    assignment = transition_review_assignment(
        assigned,
        ReviewAssignmentState.IN_PROGRESS,
        started_at,
        None,
    )
    if (
        _string(decision_seed["checklist_version"]) != HUMAN_REVIEW_CHECKLIST_VERSION
        or _sha(decision_seed["checklist_sha256"]) != HUMAN_REVIEW_CHECKLIST_SHA256
        or _string(decision_seed["checklist_status"]) != "ALL_PASS"
    ):
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    try:
        decision_kind = ReviewDecisionKind(_string(decision_seed["decision"]))
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)
    checklist = tuple(
        ChecklistResult(
            item_id=ChecklistItemId(item_id),
            status=ChecklistItemStatus.PASS,
            evidence=(),
            human_comment=None,
        )
        for item_id in HUMAN_REVIEW_CHECKLIST_IDS
    )
    draft = ReviewDecisionDraft(
        review_assignment_id=assignment.assignment_id,
        article_version_id=assignment.article_version_id,
        decision=decision_kind,
        summary=DecisionSummary(_string(decision_seed["summary"], maximum=8000)),
        checklist_version=HUMAN_REVIEW_CHECKLIST_VERSION,
        checklist_sha256=HUMAN_REVIEW_CHECKLIST_SHA256,
        checklist_results=checklist,
    )
    try:
        request = ReviewCompletionRequestV2(
            assignment=assignment,
            draft=draft,
            policy_report=report,
            policy_receipt=receipt,
            decision_id=ReviewDecisionId(_uuid7(decision_seed["decision_id"])),
            decided_at=_instant(decision_seed["decided_at"]),
            audit_event_id=_uuid7(decision_seed["audit_event_id"]),
            idempotency_key=IdempotencyKey(
                _string(decision_seed["idempotency_key"], maximum=200)
            ),
        )
        actor = RecordedIdentityProjection(
            principal_id=assignment.assigned_to,
            subject_kind=RecordedSubjectKind.HUMAN,
            subject_status=RecordedSubjectStatus.ACTIVE,
        )
        return RecordedReviewCompletionStep(request=request, actor=actor)
    except ReviewCompletionFailure:
        raise
    except Exception:
        fail_review_completion(ReviewCompletionFailureCode.FIXTURE_INVALID)


__all__ = (
    "RecordedReviewCompletionAdapter",
    "RecordedReviewCompletionStep",
    "load_recorded_review_completion_fixture",
)
