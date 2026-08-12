"""Bounded deterministic adapter for ST-0901 PR3 ENV-DEV/CI fixtures.

The adapter performs no identity lookup, authentication, database access,
transaction, event emission, durable audit append, assignment mutation,
publication, or runtime generation. Every ID, timestamp, grant, decision, and
prior history is explicit scripted input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from threading import RLock
from typing import NoReturn, SupportsIndex, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authorization import AuthorizationGrant, PermissionScope
from raos.domain.publishing.review_decision_operations import (
    RecordReviewDecisionRequest,
    RecordReviewDecisionResultV1,
    RecordedAuditAction,
    RecordedAuditArtifactV1,
    RecordedIdempotencyReceiptV1,
    RecordedIdentityProjection,
    RecordedReviewDecisionAuthorizationV1,
    RecordedReviewDecisionHistoryV1,
    RecordedReviewDecisionV1,
    RecordedSha256,
    ReviewDecisionOperation,
    ReviewDecisionOperationFailureCode,
    _build_recorded_review_decision_authorization,
    fail_review_decision_operation,
    recorded_decision_output_sha256,
)
from raos.domain.publishing.review_workflow import ReviewDecisionId, UtcTimestamp


_MAX_SCRIPT_CAPACITY = 100_000
_REDACTED = "<redacted-st0901-pr3-recorded-adapter>"


class _RedactedRecordedAdapterValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded review decision adapter serialization denied")


def _same_request(left: object, right: object) -> bool:
    try:
        return type(left) is type(right) and left == right
    except Exception:
        return False


def _idempotency_identity(
    request: RecordReviewDecisionRequest,
) -> tuple[ReviewDecisionOperation, str]:
    encoded = request.idempotency_key.value.encode("ascii", errors="strict")
    return request.operation, hashlib.sha256(encoded).hexdigest()


def _prior_record(
    *,
    request: RecordReviewDecisionRequest,
    history: RecordedReviewDecisionHistoryV1,
) -> RecordedReviewDecisionV1 | None:
    supersedes = request.supersedes_decision_id
    if supersedes is None:
        return None
    for record in history.records:
        if record.decision_id == supersedes:
            return record
    fail_review_decision_operation(ReviewDecisionOperationFailureCode.HISTORY_MISMATCH)


def _authorization_matches(
    observed: RecordedReviewDecisionAuthorizationV1,
    expected: RecordedReviewDecisionAuthorizationV1,
) -> bool:
    try:
        observed.require_valid()
        expected.require_valid()
        return (
            observed.authorization_sha256 == expected.authorization_sha256
            and observed.operation is expected.operation
            and observed.request_sha256 == expected.request_sha256
            and observed.correlation_id == expected.correlation_id
            and observed.target == expected.target
            and observed.permission_scope == expected.permission_scope
            and observed.actor == expected.actor
            and observed.assignment_id == expected.assignment_id
            and observed.article_version_id == expected.article_version_id
            and observed.assignment_sha256 == expected.assignment_sha256
            and observed.decision_sha256 == expected.decision_sha256
        )
    except Exception:
        return False


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedReviewDecisionStep(_RedactedRecordedAdapterValue):
    """One explicit negative-decision append and its exact prior history."""

    request: RecordReviewDecisionRequest
    grant: AuthorizationGrant
    permission_scope: PermissionScope
    actor: RecordedIdentityProjection
    prior_history: RecordedReviewDecisionHistoryV1
    decision_id: ReviewDecisionId
    decided_at: UtcTimestamp
    audit_event_id: UUID
    _authorization_sha256: RecordedSha256 = field(init=False, repr=False)
    _request_bytes: bytes = field(init=False, repr=False)
    _prior_history_bytes: bytes = field(init=False, repr=False)
    _result: RecordReviewDecisionResultV1 = field(init=False, repr=False)
    _result_bytes: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.request) is not RecordReviewDecisionRequest
            or type(self.grant) is not AuthorizationGrant
            or type(self.permission_scope) is not PermissionScope
            or type(self.actor) is not RecordedIdentityProjection
            or type(self.prior_history) is not RecordedReviewDecisionHistoryV1
            or type(self.decision_id) is not ReviewDecisionId
            or type(self.decided_at) is not UtcTimestamp
            or type(self.audit_event_id) is not UUID
        ):
            fail_review_decision_operation()
        self.request.require_valid()
        self.actor.require_valid()
        self.prior_history.require_valid()
        if (
            self.prior_history.assignment_id != self.request.assignment.assignment_id
            or self.prior_history.article_version_id
            != self.request.assignment.article_version_id
        ):
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.HISTORY_MISMATCH
            )
        authorization = _build_recorded_review_decision_authorization(
            request=self.request,
            grant=self.grant,
            permission_scope=self.permission_scope,
            actor=self.actor,
        )
        object.__setattr__(self, "grant", authorization.grant)
        object.__setattr__(self, "permission_scope", authorization.permission_scope)
        object.__setattr__(self, "actor", authorization.actor)
        object.__setattr__(
            self,
            "prior_history",
            RecordedReviewDecisionHistoryV1(
                assignment_id=self.prior_history.assignment_id,
                article_version_id=self.prior_history.article_version_id,
                records=self.prior_history.records,
            ),
        )
        authorization = _build_recorded_review_decision_authorization(
            request=self.request,
            grant=self.grant,
            permission_scope=self.permission_scope,
            actor=self.actor,
        )
        result = _build_result(step=self, authorization=authorization)
        object.__setattr__(
            self, "_authorization_sha256", authorization.authorization_sha256
        )
        object.__setattr__(self, "_request_bytes", self.request.canonical_bytes())
        object.__setattr__(
            self, "_prior_history_bytes", self.prior_history.canonical_bytes()
        )
        object.__setattr__(self, "_result", result)
        object.__setattr__(self, "_result_bytes", result.canonical_bytes())

    def require_valid(self) -> None:
        if (
            type(self.request) is not RecordReviewDecisionRequest
            or type(self.grant) is not AuthorizationGrant
            or type(self.permission_scope) is not PermissionScope
            or type(self.actor) is not RecordedIdentityProjection
            or type(self.prior_history) is not RecordedReviewDecisionHistoryV1
            or type(self.decision_id) is not ReviewDecisionId
            or type(self.decided_at) is not UtcTimestamp
            or type(self.audit_event_id) is not UUID
            or type(self._authorization_sha256) is not RecordedSha256
            or type(self._request_bytes) is not bytes
            or type(self._prior_history_bytes) is not bytes
            or type(self._result) is not RecordReviewDecisionResultV1
            or type(self._result_bytes) is not bytes
        ):
            fail_review_decision_operation()
        self.request.require_valid()
        self.actor.require_valid()
        self.prior_history.require_valid()
        authorization = _build_recorded_review_decision_authorization(
            request=self.request,
            grant=self.grant,
            permission_scope=self.permission_scope,
            actor=self.actor,
        )
        rebuilt = _build_result(step=self, authorization=authorization)
        self._result.require_valid()
        if (
            authorization.authorization_sha256 != self._authorization_sha256
            or self.request.canonical_bytes() != self._request_bytes
            or self.prior_history.canonical_bytes() != self._prior_history_bytes
            or rebuilt.canonical_bytes() != self._result_bytes
            or self._result.canonical_bytes() != self._result_bytes
        ):
            fail_review_decision_operation(
                ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
            )


def _step_authorization(
    step: RecordedReviewDecisionStep,
) -> RecordedReviewDecisionAuthorizationV1:
    step.require_valid()
    authorization = _build_recorded_review_decision_authorization(
        request=step.request,
        grant=step.grant,
        permission_scope=step.permission_scope,
        actor=step.actor,
    )
    if authorization.authorization_sha256 != step._authorization_sha256:
        fail_review_decision_operation(
            ReviewDecisionOperationFailureCode.NOT_AUTHORIZED
        )
    return authorization


def _build_result(
    *,
    step: RecordedReviewDecisionStep,
    authorization: RecordedReviewDecisionAuthorizationV1,
) -> RecordReviewDecisionResultV1:
    request = step.request
    request.require_valid()
    step.prior_history.require_valid()
    prior = _prior_record(request=request, history=step.prior_history)
    record = RecordedReviewDecisionV1(
        decision_id=step.decision_id,
        decision=request.validated_decision,
        decided_by=authorization.actor.principal_id,
        decided_at=step.decided_at,
        assignment_sha256=request.assignment_sha256,
        supersedes_decision_id=request.supersedes_decision_id,
        superseded_record_sha256=None if prior is None else prior.record_sha256,
    )
    history = RecordedReviewDecisionHistoryV1(
        assignment_id=request.assignment.assignment_id,
        article_version_id=request.assignment.article_version_id,
        records=(*step.prior_history.records, record),
    )
    audit = RecordedAuditArtifactV1(
        event_id=step.audit_event_id,
        action=RecordedAuditAction.DECISION_RECORD,
        occurred_at=step.decided_at,
        actor_id=authorization.actor.principal_id,
        assignment_id=request.assignment.assignment_id,
        article_version_id=request.assignment.article_version_id,
        decision_id=record.decision_id,
        correlation_id=request.correlation_id,
        authorization_sha256=authorization.authorization_sha256,
        request_sha256=request.request_sha256,
        record_sha256=record.record_sha256,
        supersedes_decision_id=record.supersedes_decision_id,
        superseded_record_sha256=record.superseded_record_sha256,
    )
    output_sha256 = recorded_decision_output_sha256(
        assignment_sha256=request.assignment_sha256,
        record_sha256=record.record_sha256,
        history_sha256=history.history_sha256,
        audit_sha256=audit.audit_sha256,
    )
    return RecordReviewDecisionResultV1(
        authorization_sha256=authorization.authorization_sha256,
        request_sha256=request.request_sha256,
        assignment=request.assignment,
        record=record,
        history=history,
        audit=audit,
        idempotency=RecordedIdempotencyReceiptV1.recorded_local(
            idempotency_key=request.idempotency_key,
            request_sha256=request.request_sha256,
            recorded_output_sha256=output_sha256,
        ),
    )


@dataclass(frozen=True, slots=True)
class _ReplayEntry:
    request: RecordReviewDecisionRequest
    request_sha256: RecordedSha256
    authorization: RecordedReviewDecisionAuthorizationV1
    result: RecordReviewDecisionResultV1
    canonical_bytes: bytes


@final
class RecordedReviewDecisionAdapter(_RedactedRecordedAdapterValue):
    """Consume exact scripts and retain append results for deterministic replay."""

    __slots__ = (
        "_history",
        "_history_bytes",
        "_index",
        "_lock",
        "_replays",
        "_scripts",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        script_capacity: int,
        scripts: tuple[RecordedReviewDecisionStep, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(script_capacity) is not int
            or not 0 < script_capacity <= _MAX_SCRIPT_CAPACITY
            or type(scripts) is not tuple
            or not scripts
            or len(scripts) > script_capacity
            or any(type(step) is not RecordedReviewDecisionStep for step in scripts)
            or any(
                _same_request(left.request, right.request)
                for index, left in enumerate(scripts)
                for right in scripts[index + 1 :]
            )
        ):
            fail_review_decision_operation()
        for step in scripts:
            step.require_valid()
        expected_prior = scripts[0].prior_history.canonical_bytes()
        for step in scripts:
            if step.prior_history.canonical_bytes() != expected_prior:
                fail_review_decision_operation(
                    ReviewDecisionOperationFailureCode.HISTORY_MISMATCH
                )
            expected_prior = step._result.history.canonical_bytes()
        initial = scripts[0].prior_history
        self._scripts = scripts
        self._index = 0
        self._history = RecordedReviewDecisionHistoryV1(
            assignment_id=initial.assignment_id,
            article_version_id=initial.article_version_id,
            records=initial.records,
        )
        self._history_bytes = self._history.canonical_bytes()
        self._replays: dict[tuple[ReviewDecisionOperation, str], _ReplayEntry] = {}
        self._lock = RLock()

    def _retained_history_matches_script(self) -> bool:
        """Bind current process state back to the exact consumed script prefix."""

        try:
            if (
                type(self._index) is not int
                or not 0 <= self._index <= len(self._scripts)
                or type(self._history) is not RecordedReviewDecisionHistoryV1
                or type(self._history_bytes) is not bytes
            ):
                return False
            self._history.require_valid()
            if self._index == 0:
                self._scripts[0].require_valid()
                expected = self._scripts[0].prior_history
            else:
                consumed = self._scripts[self._index - 1]
                consumed.require_valid()
                expected = consumed._result.history
            expected.require_valid()
            expected_bytes = expected.canonical_bytes()
            return (
                self._history.canonical_bytes() == expected_bytes
                and self._history_bytes == expected_bytes
            )
        except Exception:
            return False

    def issue_authorization(
        self,
        request: RecordReviewDecisionRequest,
    ) -> RecordedReviewDecisionAuthorizationV1:
        with self._lock:
            if type(request) is not RecordReviewDecisionRequest:
                fail_review_decision_operation(
                    ReviewDecisionOperationFailureCode.NOT_AUTHORIZED
                )
            request.require_valid()
            identity = _idempotency_identity(request)
            replay = self._replays.get(identity)
            if replay is not None:
                if not self._retained_history_matches_script():
                    fail_review_decision_operation(
                        ReviewDecisionOperationFailureCode.NOT_AUTHORIZED
                    )
                if replay.request_sha256 == request.request_sha256 and _same_request(
                    request, replay.request
                ):
                    return replay.authorization
                return _build_recorded_review_decision_authorization(
                    request=request,
                    grant=replay.authorization.grant,
                    permission_scope=replay.authorization.permission_scope,
                    actor=replay.authorization.actor,
                )
            if self._index >= len(self._scripts):
                fail_review_decision_operation(
                    ReviewDecisionOperationFailureCode.NOT_AUTHORIZED
                )
            step = self._scripts[self._index]
            if (
                not _same_request(request, step.request)
                or self._history_bytes != step._prior_history_bytes
            ):
                fail_review_decision_operation(
                    ReviewDecisionOperationFailureCode.NOT_AUTHORIZED
                )
            return _step_authorization(step)

    def exchange(
        self,
        authorization: RecordedReviewDecisionAuthorizationV1,
        request: RecordReviewDecisionRequest,
    ) -> RecordReviewDecisionResultV1:
        with self._lock:
            if (
                type(authorization) is not RecordedReviewDecisionAuthorizationV1
                or type(request) is not RecordReviewDecisionRequest
            ):
                fail_review_decision_operation(
                    ReviewDecisionOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            request.require_valid()
            identity = _idempotency_identity(request)
            replay = self._replays.get(identity)
            if replay is not None:
                if not self._retained_history_matches_script():
                    fail_review_decision_operation(
                        ReviewDecisionOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                    )
                if replay.request_sha256 != request.request_sha256:
                    fail_review_decision_operation(
                        ReviewDecisionOperationFailureCode.IDEMPOTENCY_MISMATCH
                    )
                if authorization is not replay.authorization or not _same_request(
                    request, replay.request
                ):
                    fail_review_decision_operation(
                        ReviewDecisionOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                    )
                replay.result.require_valid()
                if replay.result.canonical_bytes() != replay.canonical_bytes:
                    fail_review_decision_operation(
                        ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
                    )
                return replay.result

            if self._index >= len(self._scripts):
                fail_review_decision_operation(
                    ReviewDecisionOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            step = self._scripts[self._index]
            step.require_valid()
            if (
                not _same_request(request, step.request)
                or self._history_bytes != step._prior_history_bytes
                or self._history.canonical_bytes() != self._history_bytes
            ):
                fail_review_decision_operation(
                    ReviewDecisionOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            expected_authorization = _step_authorization(step)
            if not _authorization_matches(authorization, expected_authorization):
                fail_review_decision_operation(
                    ReviewDecisionOperationFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            result = step._result
            result.require_valid()
            canonical = result.canonical_bytes()
            if canonical != step._result_bytes:
                fail_review_decision_operation(
                    ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH
                )

            # Commit process-local state only after every scripted artifact has
            # been revalidated. No durable or cross-artifact atomicity is claimed.
            self._history = result.history
            self._history_bytes = result.history.canonical_bytes()
            self._replays[identity] = _ReplayEntry(
                request=request,
                request_sha256=request.request_sha256,
                authorization=authorization,
                result=result,
                canonical_bytes=canonical,
            )
            self._index += 1
            return result


__all__ = [
    "RecordedReviewDecisionAdapter",
    "RecordedReviewDecisionStep",
]
