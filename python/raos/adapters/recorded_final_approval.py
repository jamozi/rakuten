"""Recorded-synthetic adapter for the ST-0902 final-approval command."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from threading import RLock
from typing import Any, Final, NoReturn, SupportsIndex, cast, final
from uuid import RFC_4122, UUID

from raos.adapters.recorded_policy_engine import load_recorded_policy_fixture
from raos.adapters.recorded_review_completion import (
    load_recorded_review_completion_fixture,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.policy_engine_v2 import (
    PolicyEvaluationRecordReceiptV2,
    evaluate_editorial_policy_v2,
)
from raos.domain.publishing.final_approval import (
    PROFILE,
    FinalApprovalFailure,
    FinalApprovalFailureCode,
    FinalApprovalFindingSnapshotV2,
    FinalApprovalId,
    FinalApprovalReason,
    FinalApprovalRequestV2,
    FinalApprovalResultV2,
    FinalApprovalRole,
    RecordedFinalApprovalAuthorizationV2,
    RecordedFinalApproverV2,
    RecordedMfaState,
    RecordedStepUpState,
    SiteId,
    coverage_receipt_sha256,
    fail_final_approval,
    grant_final_approval_v2,
)
from raos.domain.publishing.review_completion_v2 import (
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
    UtcTimestamp,
)
from raos.domain.shared.persistence import Sha256Digest
from raos.domain.portfolio.workflow import IdempotencyKey


_MAX_FIXTURE_BYTES: Final = 512 * 1024
_MAX_NODES: Final = 8192
_MAX_DEPTH: Final = 24
_MAX_STEPS: Final = 128
_ROOT_KEYS: Final = (
    "schema_version",
    "profile",
    "local_status",
    "fixture_id",
    "approval",
    "actor",
    "bindings",
    "authority",
)
_APPROVAL_KEYS: Final = (
    "approval_id",
    "audit_event_id",
    "approved_at",
    "reason",
    "idempotency_key",
    "article_author_id",
    "last_editor_id",
    "site_id",
    "finding_snapshot_captured_at",
    "open_blocking_finding_ids",
)
_ACTOR_KEYS: Final = (
    "principal_id",
    "site_id",
    "subject_kind",
    "subject_status",
    "role",
    "mfa_state",
    "step_up_state",
    "reauthenticated_at",
)
_BINDING_KEYS: Final = (
    "policy_fixture_sha256",
    "policy_report_sha256",
    "policy_receipt_sequence",
    "policy_receipt_sha256",
    "coverage_report_sha256",
    "coverage_receipt_sha256",
    "review_fixture_sha256",
    "review_result_sha256",
    "review_record_sha256",
    "review_decision_sha256",
    "policy_finding_snapshot_sha256",
    "finding_clearance_sha256",
    "article_version_id",
    "article_version_no",
    "article_body_sha256",
    "canonical_ast_sha256",
)
_AUTHORITY_KEYS: Final = (
    "recorded_synthetic_only",
    "real_final_approval_authorized",
    "publication_snapshot_authorized",
    "publication_authorized",
    "release_authorized",
    "production_authorized",
)


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st0902-adapter>)"

    def __str__(self) -> str:
        return "<redacted-st0902-adapter>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded final approval serialization is forbidden")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
        result[key] = value
    return result


def _mapping(value: object, keys: tuple[str, ...]) -> Mapping[str, object]:
    if type(value) is not dict:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    result = cast(dict[str, object], value)
    if tuple(result) != keys:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    return result


def _bounded_tree(value: object) -> None:
    remaining = _MAX_NODES

    def visit(current: object, depth: int) -> None:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > _MAX_DEPTH:
            fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
        if type(current) is dict:
            for key, child in cast(dict[object, object], current).items():
                if type(key) is not str:
                    fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
                visit(child, depth + 1)
        elif type(current) is list:
            for child in cast(list[object], current):
                visit(child, depth + 1)
        elif current is not None and type(current) not in {str, int, bool}:
            fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)

    visit(value, 0)


def _string(value: object, *, maximum: int = 4096) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    return value


def _integer(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    return value


def _uuid7(value: object) -> UUID:
    try:
        parsed = UUID(_string(value, maximum=36))
    except Exception:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    if parsed.version != 7 or parsed.variant != RFC_4122 or str(parsed) != value:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    return parsed


def _sha(value: object) -> str:
    observed = _string(value, maximum=64)
    if len(observed) != 64 or any(
        character not in "0123456789abcdef" for character in observed
    ):
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    return observed


def _instant(value: object) -> UtcTimestamp:
    text = _string(value, maximum=32)
    if not text.endswith("Z"):
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except Exception:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    if parsed.tzinfo is not timezone.utc or parsed.fold:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    try:
        return UtcTimestamp(parsed)
    except Exception:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)


def _uuid_list(value: object) -> tuple[UUID, ...]:
    if type(value) is not list:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    items = cast(list[object], value)
    if len(items) > 4096:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    result = tuple(_uuid7(item) for item in items)
    if len(set(result)) != len(result) or result != tuple(sorted(result, key=str)):
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    return result


def _same_request(left: object, right: object) -> bool:
    try:
        if (
            type(left) is not FinalApprovalRequestV2
            or type(right) is not FinalApprovalRequestV2
        ):
            return False
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
class RecordedFinalApprovalStep(_Redacted):
    request: FinalApprovalRequestV2
    actor: RecordedFinalApproverV2
    authorization: RecordedFinalApprovalAuthorizationV2 = field(init=False)
    result: FinalApprovalResultV2 = field(init=False)
    request_bytes: bytes = field(init=False, repr=False)
    authorization_bytes: bytes = field(init=False, repr=False)
    result_bytes: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.request) is not FinalApprovalRequestV2
            or type(self.actor) is not RecordedFinalApproverV2
        ):
            fail_final_approval()
        self.request.require_valid()
        self.actor.require_valid()
        authorization = RecordedFinalApprovalAuthorizationV2(
            request_sha256=self.request.request_sha256,
            actor=self.actor,
        )
        result = grant_final_approval_v2(
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
        self.actor.require_valid()
        expected_authorization = RecordedFinalApprovalAuthorizationV2(
            request_sha256=self.request.request_sha256,
            actor=self.actor,
        )
        expected_result = grant_final_approval_v2(
            request=self.request,
            authorization=expected_authorization,
        )
        if (
            self.request.canonical_bytes() != self.request_bytes
            or self.authorization.canonical_bytes() != self.authorization_bytes
            or expected_authorization.canonical_bytes() != self.authorization_bytes
            or self.result.canonical_bytes() != self.result_bytes
            or expected_result.canonical_bytes() != self.result_bytes
        ):
            fail_final_approval(FinalApprovalFailureCode.OUTCOME_MISMATCH)


@final
class RecordedFinalApprovalAdapter(_Redacted):
    """Process-local scripted authorization and idempotent approval exchange."""

    __slots__ = ("_steps", "_cursor", "_replays", "_lock")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        steps: tuple[RecordedFinalApprovalStep, ...],
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(steps) is not tuple
            or not 1 <= len(steps) <= _MAX_STEPS
            or any(type(step) is not RecordedFinalApprovalStep for step in steps)
        ):
            fail_final_approval(FinalApprovalFailureCode.LOCAL_ENVIRONMENT_REQUIRED)
        seen: set[str] = set()
        for step in steps:
            step.require_valid()
            identity = step.request.idempotency_key_sha256.value
            if identity in seen:
                fail_final_approval(FinalApprovalFailureCode.IDEMPOTENCY_CONFLICT)
            seen.add(identity)
        self._steps = steps
        self._cursor = 0
        self._replays: dict[
            str,
            tuple[
                bytes,
                bytes,
                RecordedFinalApprovalAuthorizationV2,
                FinalApprovalResultV2,
            ],
        ] = {}
        self._lock = RLock()

    def _identity(self, request: FinalApprovalRequestV2) -> str:
        request.require_valid()
        return request.idempotency_key_sha256.value

    def issue_authorization(
        self,
        request: FinalApprovalRequestV2,
    ) -> RecordedFinalApprovalAuthorizationV2:
        if type(request) is not FinalApprovalRequestV2:
            fail_final_approval()
        identity = self._identity(request)
        with self._lock:
            replay = self._replays.get(identity)
            if replay is not None:
                request_bytes, authorization_bytes, authorization, _result = replay
                if (
                    request.canonical_bytes() != request_bytes
                    or authorization.canonical_bytes() != authorization_bytes
                ):
                    fail_final_approval(FinalApprovalFailureCode.IDEMPOTENCY_CONFLICT)
                return authorization
            if self._cursor >= len(self._steps):
                fail_final_approval(FinalApprovalFailureCode.LOCAL_EXCHANGE_UNAVAILABLE)
            step = self._steps[self._cursor]
            step.require_valid()
            if identity == self._identity(step.request) and not _same_request(
                request, step.request
            ):
                fail_final_approval(FinalApprovalFailureCode.IDEMPOTENCY_CONFLICT)
            if not _same_request(request, step.request):
                fail_final_approval(FinalApprovalFailureCode.LOCAL_EXCHANGE_UNAVAILABLE)
            return step.authorization

    def exchange(
        self,
        authorization: RecordedFinalApprovalAuthorizationV2,
        request: FinalApprovalRequestV2,
    ) -> FinalApprovalResultV2:
        if (
            type(authorization) is not RecordedFinalApprovalAuthorizationV2
            or type(request) is not FinalApprovalRequestV2
        ):
            fail_final_approval()
        identity = self._identity(request)
        with self._lock:
            replay = self._replays.get(identity)
            if replay is not None:
                request_bytes, authorization_bytes, retained, result = replay
                if (
                    request.canonical_bytes() != request_bytes
                    or authorization.canonical_bytes() != authorization_bytes
                    or retained.canonical_bytes() != authorization_bytes
                ):
                    fail_final_approval(FinalApprovalFailureCode.IDEMPOTENCY_CONFLICT)
                result.require_valid()
                return result
            if self._cursor >= len(self._steps):
                fail_final_approval(FinalApprovalFailureCode.LOCAL_EXCHANGE_UNAVAILABLE)
            step = self._steps[self._cursor]
            step.require_valid()
            if not _same_request(request, step.request):
                fail_final_approval(FinalApprovalFailureCode.LOCAL_EXCHANGE_UNAVAILABLE)
            if authorization.canonical_bytes() != step.authorization_bytes:
                fail_final_approval(FinalApprovalFailureCode.AUTHORIZATION_INVALID)
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


def load_recorded_final_approval_fixture(
    payload: bytes,
    *,
    policy_fixture: bytes,
    review_fixture: bytes,
) -> RecordedFinalApprovalStep:
    """Decode one bounded fixture and independently rebuild every dependency."""

    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > _MAX_FIXTURE_BYTES
        or type(policy_fixture) is not bytes
        or not policy_fixture
        or type(review_fixture) is not bytes
        or not review_fixture
    ):
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    try:
        document = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _value: fail_final_approval(
                FinalApprovalFailureCode.FIXTURE_INVALID
            ),
        )
    except FinalApprovalFailure:
        raise
    except Exception:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    _bounded_tree(document)
    root = _mapping(document, _ROOT_KEYS)
    if (
        _integer(root["schema_version"], minimum=2, maximum=2) != 2
        or _string(root["profile"]) != PROFILE
        or _string(root["local_status"]) != "LOCAL_IMPLEMENTATION_COMPLETE"
    ):
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    _uuid7(root["fixture_id"])
    approval = _mapping(root["approval"], _APPROVAL_KEYS)
    actor_seed = _mapping(root["actor"], _ACTOR_KEYS)
    bindings = _mapping(root["bindings"], _BINDING_KEYS)
    authority = _mapping(root["authority"], _AUTHORITY_KEYS)
    if _boolean(authority["recorded_synthetic_only"]) is not True or any(
        _boolean(authority[key]) is not False for key in _AUTHORITY_KEYS[1:]
    ):
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)

    if hashlib.sha256(policy_fixture).hexdigest() != _sha(
        bindings["policy_fixture_sha256"]
    ) or hashlib.sha256(review_fixture).hexdigest() != _sha(
        bindings["review_fixture_sha256"]
    ):
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    try:
        envelope = load_recorded_policy_fixture(policy_fixture)
        policy_report = evaluate_editorial_policy_v2(envelope)
        policy_report.require_valid()
        policy_receipt = PolicyEvaluationRecordReceiptV2(
            sequence=_integer(
                bindings["policy_receipt_sequence"],
                minimum=1,
                maximum=(1 << 53) - 1,
            ),
            report_sha256=Sha256Digest(policy_report.report_sha256.value),
        )
        policy_receipt.require_valid()
        review_step = load_recorded_review_completion_fixture(
            review_fixture,
            policy_fixture=policy_fixture,
        )
        review_step.require_valid()
    except Exception:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)

    coverage_report = envelope.coverage_report
    coverage_receipt = envelope.coverage_receipt
    if (
        policy_report.article_version_id is None
        or policy_report.article_version_no is None
        or policy_report.article_body_sha256 is None
        or policy_report.canonical_ast_sha256 is None
        or policy_report.report_sha256.value != _sha(bindings["policy_report_sha256"])
        or policy_receipt_sha256(policy_receipt).value
        != _sha(bindings["policy_receipt_sha256"])
        or coverage_report.report_sha256.value
        != _sha(bindings["coverage_report_sha256"])
        or coverage_receipt_sha256(coverage_receipt).value
        != _sha(bindings["coverage_receipt_sha256"])
        or review_step.result.result_sha256.value
        != _sha(bindings["review_result_sha256"])
        or review_step.result.record.record_sha256.value
        != _sha(bindings["review_record_sha256"])
        or review_step.result.record.decision.decision_sha256.value
        != _sha(bindings["review_decision_sha256"])
        or policy_finding_snapshot_sha256(policy_report).value
        != _sha(bindings["policy_finding_snapshot_sha256"])
        or str(policy_report.article_version_id.value)
        != _string(bindings["article_version_id"], maximum=36)
        or policy_report.article_version_no
        != _integer(bindings["article_version_no"], minimum=1, maximum=(1 << 53) - 1)
        or policy_report.article_body_sha256.value
        != _sha(bindings["article_body_sha256"])
        or policy_report.canonical_ast_sha256.value
        != _sha(bindings["canonical_ast_sha256"])
    ):
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)

    article_version_id = ArticleVersionId(policy_report.article_version_id.value)
    finding_snapshot = FinalApprovalFindingSnapshotV2(
        article_version_id=article_version_id,
        policy_report_sha256=Sha256Digest(policy_report.report_sha256.value),
        policy_finding_snapshot_sha256=policy_finding_snapshot_sha256(policy_report),
        captured_at=_instant(approval["finding_snapshot_captured_at"]),
        open_blocking_finding_ids=_uuid_list(approval["open_blocking_finding_ids"]),
    )
    if finding_snapshot.snapshot_sha256.value != _sha(
        bindings["finding_clearance_sha256"]
    ):
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)
    site_id = SiteId(_uuid7(approval["site_id"]))
    request = FinalApprovalRequestV2(
        approval_id=FinalApprovalId(_uuid7(approval["approval_id"])),
        article_version_id=article_version_id,
        article_version_no=policy_report.article_version_no,
        article_body_sha256=Sha256Digest(policy_report.article_body_sha256.value),
        canonical_ast_sha256=Sha256Digest(policy_report.canonical_ast_sha256.value),
        article_author_id=PrincipalId(_uuid7(approval["article_author_id"])),
        last_editor_id=PrincipalId(_uuid7(approval["last_editor_id"])),
        site_id=site_id,
        coverage_report=coverage_report,
        coverage_receipt=coverage_receipt,
        policy_report=policy_report,
        policy_receipt=policy_receipt,
        review_result=review_step.result,
        finding_snapshot=finding_snapshot,
        approved_at=_instant(approval["approved_at"]),
        reason=FinalApprovalReason(_string(approval["reason"])),
        audit_event_id=_uuid7(approval["audit_event_id"]),
        idempotency_key=IdempotencyKey(_string(approval["idempotency_key"])),
    )
    actor_site = SiteId(_uuid7(actor_seed["site_id"]))
    try:
        actor = RecordedFinalApproverV2(
            principal_id=PrincipalId(_uuid7(actor_seed["principal_id"])),
            site_id=actor_site,
            subject_kind=RecordedSubjectKind(_string(actor_seed["subject_kind"])),
            subject_status=RecordedSubjectStatus(_string(actor_seed["subject_status"])),
            role=FinalApprovalRole(_string(actor_seed["role"])),
            mfa_state=RecordedMfaState(_string(actor_seed["mfa_state"])),
            step_up_state=RecordedStepUpState(_string(actor_seed["step_up_state"])),
            reauthenticated_at=_instant(actor_seed["reauthenticated_at"]),
        )
        return RecordedFinalApprovalStep(request=request, actor=actor)
    except Exception:
        fail_final_approval(FinalApprovalFailureCode.FIXTURE_INVALID)


__all__ = (
    "RecordedFinalApprovalAdapter",
    "RecordedFinalApprovalStep",
    "load_recorded_final_approval_fixture",
)
