"""Fail-closed trust, vocabulary, purity, and scope boundaries for PR2."""

from __future__ import annotations

import builtins
import inspect
import os
from pathlib import Path
import pickle
import socket
import sqlite3
import time
from collections.abc import Callable
from typing import cast
import urllib.request
import uuid

import pytest

from .support import (
    ACTOR_ID,
    OTHER_REVIEWER_ID,
    REVIEWER_ID,
    adapter,
    create_request,
    create_step,
    identity,
    list_request,
    list_step,
    opaque_target,
    recorded_grant,
    service,
    uuid7,
)
from raos.adapters.recorded_review_assignment import (
    RecordedListReviewAssignmentsStep,
)
from raos.application.publishing.review_assignment import ReviewAssignmentService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authorization import (
    AuthorizationDecision,
    AuthorizationDecisionReason,
    AuthorizationGrant,
    CorrelationId,
    DecisionEffect,
    EntitlementRevision,
    PermissionScope,
    PolicyRevision,
)
from raos.domain.portfolio.workflow import EntityVersion, StrongEtag
from raos.domain.publishing import review_assignment_operations as operations
from raos.domain.publishing.review_assignment_operations import (
    CreateReviewAssignmentResult,
    ListReviewAssignmentsRequest,
    ListReviewAssignmentsResult,
    RecordedIdentityProjection,
    RecordedIdempotencyReceiptV1,
    RecordedReviewerAuthorizationV1,
    RecordedSha256,
    RecordedSubjectKind,
    RecordedSubjectStatus,
    ReviewAssignmentOperation,
    ReviewAssignmentOperationFailure,
    ReviewAssignmentOperationFailureCode,
    ReviewAssignmentRequest,
    ReviewAssignmentResult,
    UpdateReviewAssignmentRequest,
)
from raos.domain.publishing.review_workflow import ReviewAssignmentState


def _assert_sanitized(
    captured: pytest.ExceptionInfo[ReviewAssignmentOperationFailure],
    expected: ReviewAssignmentOperationFailureCode,
) -> None:
    error = captured.value
    assert error.code is expected
    assert error.args == (expected.value,)
    assert str(error) == expected.value
    assert repr(error) == f"ReviewAssignmentOperationFailure(code={expected.value})"
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.mark.parametrize(
    ("action", "permission"),
    (
        ("publishing:review:assign", "publishing:review:read"),
        ("publishing:review:read", "publishing:review:assign"),
    ),
)
def test_wrong_recorded_action_or_permission_rejected_before_exchange(
    action: str,
    permission: str,
) -> None:
    request = list_request()
    recorded = adapter(
        list_step(
            request=request,
            action=action,
            permission=permission,
        )
    )
    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        service(recorded).execute(request=request)
    _assert_sanitized(captured, ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED)
    assert object.__getattribute__(recorded, "_index") == 0


def test_wrong_opaque_target_or_correlation_rejected_before_exchange() -> None:
    request = list_request()
    wrong_target_step = RecordedListReviewAssignmentsStep(
        request=request,
        grant=recorded_grant(
            action="publishing:review:read",
            correlation_id=request.correlation_id,
            target=opaque_target(resource_id=uuid7(999)),
        ),
        permission_scope=PermissionScope("publishing:review:read"),
        actor=identity(ACTOR_ID),
        items=(),
    )
    wrong_target = adapter(wrong_target_step)
    with pytest.raises(ReviewAssignmentOperationFailure) as target_failure:
        service(wrong_target).execute(request=request)
    _assert_sanitized(
        target_failure,
        ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED,
    )
    assert object.__getattribute__(wrong_target, "_index") == 0

    wrong_correlation_step = RecordedListReviewAssignmentsStep(
        request=request,
        grant=recorded_grant(
            action="publishing:review:read",
            correlation_id=CorrelationId("ST0901_PR2_RECORDED_LOCAL_V1:WRONG"),
            target=request.target,
        ),
        permission_scope=PermissionScope("publishing:review:read"),
        actor=identity(ACTOR_ID),
        items=(),
    )
    wrong_correlation = adapter(wrong_correlation_step)
    with pytest.raises(ReviewAssignmentOperationFailure) as correlation_failure:
        service(wrong_correlation).execute(request=request)
    _assert_sanitized(
        correlation_failure,
        ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED,
    )
    assert object.__getattribute__(wrong_correlation, "_index") == 0


def test_changed_request_hash_and_malformed_grant_are_not_consumed() -> None:
    request = list_request()
    hash_recorded = adapter(list_step(request=request))
    object.__setattr__(request, "request_sha256", RecordedSha256("0" * 64))
    with pytest.raises(ReviewAssignmentOperationFailure) as hash_failure:
        service(hash_recorded).execute(request=request)
    _assert_sanitized(
        hash_failure, ReviewAssignmentOperationFailureCode.INVALID_ARGUMENT
    )
    assert object.__getattribute__(hash_recorded, "_index") == 0

    valid_request = list_request(correlation="ST0901_PR2_RECORDED_LOCAL_V1:GRANT")
    malformed_recorded = adapter(list_step(request=valid_request))
    step = object.__getattribute__(malformed_recorded, "_scripts")[0]
    object.__setattr__(step.grant, "_decision", object())
    with pytest.raises(ReviewAssignmentOperationFailure) as grant_failure:
        service(malformed_recorded).execute(request=valid_request)
    _assert_sanitized(
        grant_failure,
        ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED,
    )
    assert object.__getattribute__(malformed_recorded, "_index") == 0


def _recorded_decision(grant: AuthorizationGrant) -> AuthorizationDecision:
    decision = object.__getattribute__(grant, "_decision")
    assert type(decision) is AuthorizationDecision
    return decision


def _tamper_grant_effect(grant: AuthorizationGrant) -> None:
    object.__setattr__(_recorded_decision(grant), "_effect", DecisionEffect.DENY)


def _tamper_grant_reason(grant: AuthorizationGrant) -> None:
    object.__setattr__(
        _recorded_decision(grant),
        "_reason",
        AuthorizationDecisionReason.NO_MATCH,
    )


def _tamper_grant_matched_rule(grant: AuthorizationGrant) -> None:
    object.__setattr__(_recorded_decision(grant), "_matched_rule_id", None)


def _tamper_decision_seal(grant: AuthorizationGrant) -> None:
    object.__setattr__(_recorded_decision(grant), "_sealed", False)


def _tamper_policy_revision(grant: AuthorizationGrant) -> None:
    object.__setattr__(
        _recorded_decision(grant),
        "_policy_revision",
        PolicyRevision("ST0901_PR2_RECORDED_LOCAL_V1:ALT_POLICY"),
    )


def _tamper_entitlement_revision(grant: AuthorizationGrant) -> None:
    object.__setattr__(
        _recorded_decision(grant),
        "_entitlement_revision",
        EntitlementRevision("ST0901_PR2_RECORDED_LOCAL_V1:ALT_ENTITLEMENTS"),
    )


def _tamper_policy_fingerprint(grant: AuthorizationGrant) -> None:
    object.__setattr__(_recorded_decision(grant), "_policy_fingerprint", "8" * 64)


@pytest.mark.parametrize(
    "tamper",
    (
        _tamper_grant_effect,
        _tamper_grant_reason,
        _tamper_grant_matched_rule,
        _tamper_decision_seal,
        _tamper_policy_revision,
        _tamper_entitlement_revision,
        _tamper_policy_fingerprint,
    ),
)
def test_tampered_full_grant_decision_never_reaches_exchange(
    tamper: Callable[[AuthorizationGrant], None],
) -> None:
    request = list_request()
    step = list_step(request=request)
    recorded = adapter(step)
    tamper(step.grant)

    class CountingExchange:
        calls = 0

        def exchange(
            self,
            authorization: RecordedReviewerAuthorizationV1,
            observed: ReviewAssignmentRequest,
        ) -> ReviewAssignmentResult:
            del authorization, observed
            self.calls += 1
            raise AssertionError("tampered grant must not reach exchange")

    exchange = CountingExchange()
    application = ReviewAssignmentService(
        environment=RuntimeEnvironment.ENV_DEV,
        authorization_source=recorded,
        exchange=exchange,
    )
    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        application.execute(request=request)

    _assert_sanitized(captured, ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED)
    assert exchange.calls == 0
    assert object.__getattribute__(recorded, "_index") == 0


@pytest.mark.parametrize(
    "actor",
    (
        identity(
            ACTOR_ID,
            status=RecordedSubjectStatus.INACTIVE,
        ),
        identity(
            ACTOR_ID,
            kind=RecordedSubjectKind.SERVICE,
        ),
    ),
)
def test_inactive_or_nonhuman_actor_is_not_authority(
    actor: RecordedIdentityProjection,
) -> None:
    request = list_request()
    recorded = adapter(list_step(request=request, actor=actor))
    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        service(recorded).execute(request=request)
    _assert_sanitized(captured, ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED)
    assert object.__getattribute__(recorded, "_index") == 0


@pytest.mark.parametrize(
    "reviewer",
    (
        identity(
            REVIEWER_ID,
            status=RecordedSubjectStatus.INACTIVE,
        ),
        identity(
            REVIEWER_ID,
            kind=RecordedSubjectKind.SERVICE,
        ),
        identity(OTHER_REVIEWER_ID),
    ),
)
def test_inactive_nonhuman_or_substitute_reviewer_is_rejected(
    reviewer: RecordedIdentityProjection,
) -> None:
    request = create_request()
    recorded = adapter(create_step(request=request, reviewer=reviewer))
    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        service(recorded).execute(request=request)
    _assert_sanitized(captured, ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED)
    assert object.__getattribute__(recorded, "_index") == 0


def test_sealed_authorization_direct_construction_and_tamper_fail_closed() -> None:
    request = list_request()
    scripted = list_step(request=request)
    recorded = adapter(scripted)
    authorization = recorded.issue_authorization(request)

    assert scripted.authorization_sha256 == authorization.authorization_sha256
    assert not hasattr(authorization.actor, "canonical_payload")
    with pytest.raises(AttributeError):
        setattr(scripted, "authorization_sha256", RecordedSha256("0" * 64))

    with pytest.raises(ReviewAssignmentOperationFailure) as direct_failure:
        RecordedReviewerAuthorizationV1(
            operation=authorization.operation,
            request_sha256=authorization.request_sha256,
            correlation_id=authorization.correlation_id,
            target=authorization.target,
            grant=authorization.grant,
            permission_scope=authorization.permission_scope,
            actor=authorization.actor,
            reviewer=authorization.reviewer,
            assignment_id=authorization.assignment_id,
            article_version_id=authorization.article_version_id,
            authorization_sha256=authorization.authorization_sha256,
        )
    _assert_sanitized(
        direct_failure,
        ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED,
    )

    object.__setattr__(
        authorization,
        "_authorization_sha256",
        RecordedSha256("0" * 64),
    )
    with pytest.raises(ReviewAssignmentOperationFailure) as tamper_failure:
        authorization.require_valid()
    _assert_sanitized(
        tamper_failure,
        ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED,
    )
    assert "_RECORDED_AUTHORIZATION_PERMIT" not in operations.__all__
    assert "_build_recorded_reviewer_authorization" not in operations.__all__
    assert "build_recorded_reviewer_authorization" not in operations.__all__


def test_subclass_and_duplicate_trust_paths_are_structurally_rejected() -> None:
    class RequestSubclass(ListReviewAssignmentsRequest):  # type: ignore[misc]
        pass

    class AuthorizationSubclass(  # type: ignore[misc]
        RecordedReviewerAuthorizationV1
    ):
        pass

    exact = list_request()
    subclass_request = RequestSubclass(
        correlation_id=exact.correlation_id,
        target=exact.target,
    )
    recorded = adapter(list_step(request=exact))
    with pytest.raises(ReviewAssignmentOperationFailure) as request_failure:
        service(recorded).execute(request=subclass_request)
    _assert_sanitized(
        request_failure,
        ReviewAssignmentOperationFailureCode.INVALID_ARGUMENT,
    )
    assert object.__getattribute__(recorded, "_index") == 0

    malformed_authorization = object.__new__(AuthorizationSubclass)

    class SubclassSource:
        def issue_authorization(
            self, request: ReviewAssignmentRequest
        ) -> RecordedReviewerAuthorizationV1:
            del request
            return malformed_authorization

    class CountingExchange:
        calls = 0

        def exchange(
            self,
            authorization: RecordedReviewerAuthorizationV1,
            request: ReviewAssignmentRequest,
        ) -> ReviewAssignmentResult:
            del authorization, request
            self.calls += 1
            raise AssertionError("must not be called")

    exchange = CountingExchange()
    application = ReviewAssignmentService(
        environment=RuntimeEnvironment.ENV_DEV,
        authorization_source=SubclassSource(),
        exchange=exchange,
    )
    with pytest.raises(ReviewAssignmentOperationFailure) as auth_failure:
        application.execute(request=exact)
    _assert_sanitized(
        auth_failure,
        ReviewAssignmentOperationFailureCode.NOT_AUTHORIZED,
    )
    assert exchange.calls == 0

    parameters = inspect.signature(ReviewAssignmentService.execute).parameters
    assert tuple(parameters) == ("self", "request")
    assert parameters["request"].kind is inspect.Parameter.KEYWORD_ONLY
    for forbidden in ("grant", "authorization", "actor", "reviewer", "principal"):
        assert forbidden not in parameters


def test_runtime_subclass_nested_value_is_rejected() -> None:
    class StrongEtagSubclass(StrongEtag):
        pass

    request = create_request()
    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        UpdateReviewAssignmentRequest(
            correlation_id=request.correlation_id,
            target=request.target,
            assignment_id=request.assignment_id,
            article_version_id=request.article_version_id,
            target_state=ReviewAssignmentState.IN_PROGRESS,
            occurred_at=request.created_at,
            expected_lock_version=EntityVersion(0),
            if_match=StrongEtagSubclass('"ST0901-PR2-SUBCLASS"'),
            idempotency_key=request.idempotency_key,
        )
    _assert_sanitized(captured, ReviewAssignmentOperationFailureCode.INVALID_ARGUMENT)


@pytest.mark.parametrize(
    "token",
    (
        "pubadm-001",
        "PUBADM-004",
        "ED-030",
        "review_assignment_decide",
        "APPROVE",
    ),
)
def test_unknown_downstream_or_case_varied_operation_vocabulary_is_closed(
    token: str,
) -> None:
    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        ReviewAssignmentOperation(token)
    _assert_sanitized(captured, ReviewAssignmentOperationFailureCode.INVALID_ARGUMENT)
    assert token not in str(captured.value)
    assert token not in repr(captured.value)


def test_idempotency_receipt_requires_exact_operation_enum_without_leak() -> None:
    digest = RecordedSha256("0" * 64)
    with pytest.raises(ReviewAssignmentOperationFailure) as captured:
        RecordedIdempotencyReceiptV1(
            operation=cast(ReviewAssignmentOperation, "PUBADM-002"),
            idempotency_key_sha256=digest,
            request_sha256=digest,
            recorded_output_sha256=digest,
        )
    _assert_sanitized(captured, ReviewAssignmentOperationFailureCode.INVALID_ARGUMENT)


def test_values_results_authorization_and_failures_deny_pickle() -> None:
    request = create_request(idempotency_key="ST0901-PR2-RAW-CANARY-KEY")
    recorded = adapter(create_step(request=request))
    authorization = recorded.issue_authorization(request)
    result = service(recorded).execute(request=request)
    assert type(result) is CreateReviewAssignmentResult
    assert b"ST0901-PR2-RAW-CANARY-KEY" not in result.canonical_bytes()
    for value in (
        request,
        request.request_sha256,
        authorization,
        result,
        result.audit,
        result.idempotency,
        ReviewAssignmentOperationFailure(
            ReviewAssignmentOperationFailureCode.INVALID_ARGUMENT
        ),
    ):
        assert "CANARY" not in repr(value)
        assert "CANARY" not in str(value)
        with pytest.raises(TypeError):
            pickle.dumps(value)


def test_execution_uses_no_clock_uuid_fs_env_network_or_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = create_request()
    recorded = adapter(create_step(request=request))
    application = service(recorded)

    def forbidden(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("nondeterministic or external API called")

    with monkeypatch.context() as isolated:
        isolated.setattr(time, "time", forbidden)
        isolated.setattr(uuid, "uuid4", forbidden)
        if hasattr(uuid, "uuid7"):
            isolated.setattr(uuid, "uuid7", forbidden)
        isolated.setattr(builtins, "open", forbidden)
        isolated.setattr(os, "getenv", forbidden)
        isolated.setattr(socket, "socket", forbidden)
        isolated.setattr(sqlite3, "connect", forbidden)
        isolated.setattr(urllib.request, "urlopen", forbidden)
        result = application.execute(request=request)

    assert type(result) is CreateReviewAssignmentResult
    assert result.events is operations.RecordedExecution.NOT_EXECUTED
    assert result.publication is operations.RecordedExecution.NOT_EXECUTED
    assert result.persistence is operations.RecordedExecution.NOT_EXECUTED


def test_only_recorded_local_ports_exist_and_broader_patch_is_absent() -> None:
    update_fields = inspect.signature(UpdateReviewAssignmentRequest).parameters
    assert tuple(update_fields) == (
        "correlation_id",
        "target",
        "assignment_id",
        "article_version_id",
        "target_state",
        "occurred_at",
        "expected_lock_version",
        "if_match",
        "idempotency_key",
        "completion_decision_reference",
    )
    for absent in (
        "priority",
        "due_at",
        "instructions",
        "assigned_by",
        "assigned_to",
        "review_type",
        "created_at",
        "decision",
        "finding",
    ):
        assert absent not in update_fields
        assert absent not in operations.__all__

    assert tuple(ReviewAssignmentOperation) == (
        ReviewAssignmentOperation.LIST,
        ReviewAssignmentOperation.CREATE,
        ReviewAssignmentOperation.UPDATE,
    )
    source_files = (
        Path(inspect.getsourcefile(operations) or ""),
        Path(inspect.getsourcefile(ReviewAssignmentService) or ""),
    )
    for source_file in source_files:
        text = source_file.read_text(encoding="utf-8")
        for forbidden_import in (
            "import sqlalchemy",
            "from sqlalchemy",
            "import fastapi",
            "from fastapi",
            "import requests",
            "import httpx",
            "import boto",
        ):
            assert forbidden_import not in text


def test_list_result_remains_exact_type_without_mutation_artifacts() -> None:
    request = list_request()
    result = service(adapter(list_step(request=request))).execute(request=request)
    assert type(result) is ListReviewAssignmentsResult
    listed = result
    assert not hasattr(listed, "audit")
    assert not hasattr(listed, "idempotency")
