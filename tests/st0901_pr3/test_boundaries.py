"""Authorization, vocabulary, and public-surface boundaries for PR3."""

from __future__ import annotations

from dataclasses import replace
import inspect
from typing import Callable, cast

import pytest

from conftest import (
    DECIDED_AT,
    OTHER_REVIEWER_ID,
    adapter,
    empty_history,
    identity,
    opaque_target,
    recorded_grant,
    request,
    service,
    step,
    uuid7,
)
from raos.adapters.recorded_review_decision import RecordedReviewDecisionStep
from raos.application.publishing.review_decision import ReviewDecisionService
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
    RuleId,
)
from raos.domain.publishing import review_decision_operations as operations
from raos.domain.publishing.review_decision_operations import (
    RecordReviewDecisionRequest,
    RecordReviewDecisionResultV1,
    RecordedIdempotencyReceiptV1,
    RecordedIdentityProjection,
    RecordedReviewDecisionAuthorizationV1,
    RecordedSha256,
    RecordedSubjectKind,
    RecordedSubjectStatus,
    ReviewDecisionOperation,
    ReviewDecisionOperationFailure,
    ReviewDecisionOperationFailureCode,
)
from raos.domain.publishing.review_workflow import (
    ChecklistItemStatus,
    ChecklistResult,
    HumanComment,
    ReviewDecisionKind,
    ReviewWorkflowFailure,
    ReviewWorkflowFailureCode,
)


def _assert_sanitized(
    captured: pytest.ExceptionInfo[ReviewDecisionOperationFailure],
    code: ReviewDecisionOperationFailureCode,
) -> None:
    error = captured.value
    assert error.code is code
    assert str(error) == code.value
    assert repr(error) == f"ReviewDecisionOperationFailure(code={code.value})"
    assert error.args == (code.value,)
    assert error.__cause__ is None
    assert error.__context__ is None


class _CountingSource:
    def __init__(self, delegate: object, *, raises: bool = False) -> None:
        self.delegate = delegate
        self.raises = raises
        self.calls = 0

    def issue_authorization(
        self,
        value: RecordReviewDecisionRequest,
    ) -> RecordedReviewDecisionAuthorizationV1:
        self.calls += 1
        if self.raises:
            raise RuntimeError("untrusted source detail")
        method = getattr(self.delegate, "issue_authorization")
        return cast(RecordedReviewDecisionAuthorizationV1, method(value))


class _CountingExchange:
    def __init__(self, delegate: object | None = None) -> None:
        self.delegate = delegate
        self.calls = 0

    def exchange(
        self,
        authorization: RecordedReviewDecisionAuthorizationV1,
        value: RecordReviewDecisionRequest,
    ) -> RecordReviewDecisionResultV1:
        self.calls += 1
        if self.delegate is None:
            raise AssertionError("exchange must not be called")
        method = getattr(self.delegate, "exchange")
        return cast(RecordReviewDecisionResultV1, method(authorization, value))


class _StaticExchange:
    def __init__(self, result: RecordReviewDecisionResultV1) -> None:
        self.result = result

    def exchange(
        self,
        authorization: RecordedReviewDecisionAuthorizationV1,
        value: RecordReviewDecisionRequest,
    ) -> RecordReviewDecisionResultV1:
        del authorization, value
        return self.result


def test_approve_stable_pr1_gate_precedes_authorization() -> None:
    command = request()
    recorded = adapter(step(value=command))
    source = _CountingSource(recorded)
    exchange = _CountingExchange(recorded)
    application = ReviewDecisionService(
        environment=RuntimeEnvironment.ENV_DEV,
        authorization_source=source,
        exchange=exchange,
    )
    object.__setattr__(command.draft, "decision", ReviewDecisionKind.APPROVE)
    object.__setattr__(command, "operation", "ED-030")

    with pytest.raises(ReviewWorkflowFailure) as captured:
        application.execute(request=command)

    assert captured.value.code is ReviewWorkflowFailureCode.APPROVE_GATE_UNRESOLVED
    assert source.calls == 0
    assert exchange.calls == 0


def test_any_not_applicable_stable_pr1_gate_precedes_authorization() -> None:
    command = request()
    recorded = adapter(step(value=command))
    source = _CountingSource(recorded)
    exchange = _CountingExchange(recorded)
    results = command.draft.checklist_results
    not_applicable = ChecklistResult(
        item_id=results[-1].item_id,
        status=ChecklistItemStatus.NOT_APPLICABLE_WITH_REASON,
        evidence=(),
        human_comment=HumanComment("Applicability remains human-unresolved."),
    )
    object.__setattr__(
        command.draft,
        "checklist_results",
        (*results[:-1], not_applicable),
    )
    object.__setattr__(command, "operation", "PUBADM-005")
    application = ReviewDecisionService(
        environment=RuntimeEnvironment.ENV_DEV,
        authorization_source=source,
        exchange=exchange,
    )

    with pytest.raises(ReviewWorkflowFailure) as captured:
        application.execute(request=command)

    assert (
        captured.value.code
        is ReviewWorkflowFailureCode.CHECKLIST_APPLICABILITY_UNRESOLVED
    )
    assert source.calls == 0
    assert exchange.calls == 0


@pytest.mark.parametrize(
    "token",
    (
        "pubadm-004",
        "PUBADM-004 ",
        "PUBADM-001",
        "PUBADM-002",
        "PUBADM-003",
        "PUBADM-005",
        "ED-030",
        "request_changes",
        "pause",
    ),
)
def test_unknown_lowercase_and_other_operation_vocabularies_are_closed(
    token: str,
) -> None:
    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        ReviewDecisionOperation(token)
    _assert_sanitized(captured, ReviewDecisionOperationFailureCode.INVALID_ARGUMENT)


@pytest.mark.parametrize("environment", tuple(RuntimeEnvironment))
def test_only_dev_and_ci_are_accepted(environment: RuntimeEnvironment) -> None:
    command = request()
    scripted = step(value=command)
    if environment in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}:
        recorded = adapter(scripted, environment=environment)
        assert (
            service(recorded, environment=environment)
            .execute(request=command)
            .record.decision.decision
            is ReviewDecisionKind.CHANGES_REQUESTED
        )
        return
    with pytest.raises(ReviewDecisionOperationFailure):
        adapter(scripted, environment=environment)


def test_authorization_and_exchange_are_called_exactly_once() -> None:
    command = request()
    recorded = adapter(step(value=command))
    source = _CountingSource(recorded)
    exchange = _CountingExchange(recorded)
    application = ReviewDecisionService(
        environment=RuntimeEnvironment.CI,
        authorization_source=source,
        exchange=exchange,
    )

    application.execute(request=command)

    assert source.calls == 1
    assert exchange.calls == 1


def test_authorization_source_failure_never_reaches_exchange() -> None:
    command = request()
    source = _CountingSource(object(), raises=True)
    exchange = _CountingExchange()
    application = ReviewDecisionService(
        environment=RuntimeEnvironment.ENV_DEV,
        authorization_source=source,
        exchange=exchange,
    )

    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        application.execute(request=command)

    _assert_sanitized(captured, ReviewDecisionOperationFailureCode.NOT_AUTHORIZED)
    assert source.calls == 1
    assert exchange.calls == 0


@pytest.mark.parametrize(
    ("action", "permission"),
    (
        ("publishing:review:assign", "publishing:review:decide"),
        ("publishing:review:decide", "publishing:review:read"),
    ),
)
def test_wrong_action_or_permission_fails_before_exchange(
    action: str,
    permission: str,
) -> None:
    command = request()
    recorded = adapter(step(value=command, action=action, permission=permission))
    exchange = _CountingExchange(recorded)
    application = ReviewDecisionService(
        environment=RuntimeEnvironment.ENV_DEV,
        authorization_source=recorded,
        exchange=exchange,
    )

    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        application.execute(request=command)

    _assert_sanitized(captured, ReviewDecisionOperationFailureCode.NOT_AUTHORIZED)
    assert exchange.calls == 0
    assert object.__getattribute__(recorded, "_index") == 0


def test_wrong_opaque_target_or_correlation_fails_before_exchange() -> None:
    command = request()
    cases = (
        recorded_grant(
            correlation_id=command.correlation_id,
            target=opaque_target(resource_id=uuid7(777)),
        ),
        recorded_grant(
            correlation_id=CorrelationId("ST0901_PR3_RECORDED_LOCAL_V1:WRONG"),
            target=command.target,
        ),
    )
    for grant in cases:
        scripted = RecordedReviewDecisionStep(
            request=command,
            grant=grant,
            permission_scope=PermissionScope("publishing:review:decide"),
            actor=identity(),
            prior_history=empty_history(command),
            decision_id=type(step(value=command).decision_id)(uuid7(778)),
            decided_at=DECIDED_AT,
            audit_event_id=uuid7(779),
        )
        recorded = adapter(scripted)
        exchange = _CountingExchange(recorded)
        application = ReviewDecisionService(
            environment=RuntimeEnvironment.ENV_DEV,
            authorization_source=recorded,
            exchange=exchange,
        )
        with pytest.raises(ReviewDecisionOperationFailure) as captured:
            application.execute(request=command)
        _assert_sanitized(
            captured,
            ReviewDecisionOperationFailureCode.NOT_AUTHORIZED,
        )
        assert exchange.calls == 0


def _recorded_decision(grant: AuthorizationGrant) -> AuthorizationDecision:
    decision = object.__getattribute__(grant, "_decision")
    assert type(decision) is AuthorizationDecision
    return decision


def _tamper_effect(grant: AuthorizationGrant) -> None:
    object.__setattr__(_recorded_decision(grant), "_effect", DecisionEffect.DENY)


def _tamper_reason(grant: AuthorizationGrant) -> None:
    object.__setattr__(
        _recorded_decision(grant),
        "_reason",
        AuthorizationDecisionReason.NO_MATCH,
    )


def _tamper_rule(grant: AuthorizationGrant) -> None:
    object.__setattr__(_recorded_decision(grant), "_matched_rule_id", None)


def _tamper_seal(grant: AuthorizationGrant) -> None:
    object.__setattr__(_recorded_decision(grant), "_sealed", False)


def _tamper_policy(grant: AuthorizationGrant) -> None:
    object.__setattr__(
        _recorded_decision(grant),
        "_policy_revision",
        PolicyRevision("ST0901_PR3_RECORDED_LOCAL_V1:ALT_POLICY"),
    )


def _tamper_entitlement(grant: AuthorizationGrant) -> None:
    object.__setattr__(
        _recorded_decision(grant),
        "_entitlement_revision",
        EntitlementRevision("ST0901_PR3_RECORDED_LOCAL_V1:ALT_ENTITLEMENTS"),
    )


def _tamper_fingerprint(grant: AuthorizationGrant) -> None:
    object.__setattr__(_recorded_decision(grant), "_policy_fingerprint", "8" * 64)


def _tamper_valid_rule(grant: AuthorizationGrant) -> None:
    object.__setattr__(
        _recorded_decision(grant),
        "_matched_rule_id",
        RuleId("ST0901_PR3_RECORDED_LOCAL_V1:ALT_RULE"),
    )


@pytest.mark.parametrize(
    "tamper",
    (
        _tamper_effect,
        _tamper_reason,
        _tamper_rule,
        _tamper_seal,
        _tamper_policy,
        _tamper_entitlement,
        _tamper_fingerprint,
        _tamper_valid_rule,
    ),
)
def test_all_grant_decision_internals_are_revalidated_before_exchange(
    tamper: Callable[[AuthorizationGrant], None],
) -> None:
    command = request()
    scripted = step(value=command)
    recorded = adapter(scripted)
    tamper(scripted.grant)
    exchange = _CountingExchange(recorded)
    application = ReviewDecisionService(
        environment=RuntimeEnvironment.ENV_DEV,
        authorization_source=recorded,
        exchange=exchange,
    )

    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        application.execute(request=command)

    _assert_sanitized(captured, ReviewDecisionOperationFailureCode.NOT_AUTHORIZED)
    assert exchange.calls == 0
    assert object.__getattribute__(recorded, "_index") == 0


@pytest.mark.parametrize(
    "actor",
    (
        identity(status=RecordedSubjectStatus.INACTIVE),
        identity(kind=RecordedSubjectKind.SERVICE),
    ),
)
def test_inactive_or_nonhuman_recorded_actor_is_not_authority(
    actor: RecordedIdentityProjection,
) -> None:
    command = request()
    recorded = adapter(step(value=command, actor=actor))
    exchange = _CountingExchange(recorded)
    application = ReviewDecisionService(
        environment=RuntimeEnvironment.ENV_DEV,
        authorization_source=recorded,
        exchange=exchange,
    )

    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        application.execute(request=command)

    _assert_sanitized(captured, ReviewDecisionOperationFailureCode.NOT_AUTHORIZED)
    assert exchange.calls == 0


def test_substitute_actor_cannot_construct_a_recorded_outcome() -> None:
    command = request()
    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        step(value=command, actor=identity(OTHER_REVIEWER_ID))
    _assert_sanitized(captured, ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH)


def test_sealed_authorization_direct_construction_subclass_and_tamper_fail() -> None:
    command = request()
    scripted = step(value=command)
    recorded = adapter(scripted)
    authorization = recorded.issue_authorization(command)

    assert scripted.authorization_sha256 == authorization.authorization_sha256
    assert scripted.prior_history_bytes == scripted.prior_history.canonical_bytes()
    assert scripted.result_bytes == scripted.result.canonical_bytes()
    assert not hasattr(authorization.actor, "canonical_payload")
    for attribute, value in (
        ("authorization_sha256", RecordedSha256("0" * 64)),
        ("prior_history_bytes", b"tampered"),
        ("result", scripted.result),
        ("result_bytes", b"tampered"),
    ):
        with pytest.raises(AttributeError):
            setattr(scripted, attribute, value)

    with pytest.raises(ReviewDecisionOperationFailure) as direct:
        RecordedReviewDecisionAuthorizationV1(
            operation=authorization.operation,
            request_sha256=authorization.request_sha256,
            correlation_id=authorization.correlation_id,
            target=authorization.target,
            grant=authorization.grant,
            permission_scope=authorization.permission_scope,
            actor=authorization.actor,
            assignment_id=authorization.assignment_id,
            article_version_id=authorization.article_version_id,
            assignment_sha256=authorization.assignment_sha256,
            decision_sha256=authorization.decision_sha256,
            authorization_sha256=authorization.authorization_sha256,
        )
    _assert_sanitized(direct, ReviewDecisionOperationFailureCode.NOT_AUTHORIZED)

    class AuthorizationSubclass(  # type: ignore[misc]
        RecordedReviewDecisionAuthorizationV1
    ):
        pass

    with pytest.raises(ReviewDecisionOperationFailure) as subclass:
        AuthorizationSubclass(
            operation=authorization.operation,
            request_sha256=authorization.request_sha256,
            correlation_id=authorization.correlation_id,
            target=authorization.target,
            grant=authorization.grant,
            permission_scope=authorization.permission_scope,
            actor=authorization.actor,
            assignment_id=authorization.assignment_id,
            article_version_id=authorization.article_version_id,
            assignment_sha256=authorization.assignment_sha256,
            decision_sha256=authorization.decision_sha256,
            authorization_sha256=authorization.authorization_sha256,
        )
    _assert_sanitized(subclass, ReviewDecisionOperationFailureCode.NOT_AUTHORIZED)

    object.__setattr__(authorization, "_authorization_sha256", RecordedSha256("0" * 64))
    with pytest.raises(ReviewDecisionOperationFailure) as tampered:
        authorization.require_valid()
    _assert_sanitized(tampered, ReviewDecisionOperationFailureCode.NOT_AUTHORIZED)
    assert "_RECORDED_AUTHORIZATION_PERMIT" not in operations.__all__
    assert "_build_recorded_review_decision_authorization" not in operations.__all__
    assert "build_recorded_review_decision_authorization" not in operations.__all__


def test_public_service_has_no_second_trust_or_mutation_path() -> None:
    execute = inspect.signature(ReviewDecisionService.execute).parameters
    assert tuple(execute) == ("self", "request")
    assert execute["request"].kind is inspect.Parameter.KEYWORD_ONLY
    for forbidden in (
        "authorization",
        "grant",
        "actor",
        "reviewer",
        "principal",
        "finding",
        "effective",
        "complete",
    ):
        assert forbidden not in execute
    assert not hasattr(ReviewDecisionService, "approve")
    assert not hasattr(ReviewDecisionService, "complete_assignment")
    assert not hasattr(ReviewDecisionService, "resolve_finding")


def test_application_rebuilds_exact_raw_key_receipt() -> None:
    command = request()
    recorded = adapter(step(value=command))
    authorization = recorded.issue_authorization(command)
    observed = recorded.exchange(authorization, command)
    forged_receipt = RecordedIdempotencyReceiptV1(
        operation=observed.idempotency.operation,
        idempotency_key_sha256=RecordedSha256("0" * 64),
        request_sha256=observed.idempotency.request_sha256,
        recorded_output_sha256=observed.idempotency.recorded_output_sha256,
    )
    forged = replace(observed, idempotency=forged_receipt)
    application = ReviewDecisionService(
        environment=RuntimeEnvironment.CI,
        authorization_source=recorded,
        exchange=_StaticExchange(forged),
    )

    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        application.execute(request=command)

    _assert_sanitized(captured, ReviewDecisionOperationFailureCode.OUTCOME_MISMATCH)


def test_request_and_authorization_subclasses_are_rejected() -> None:
    class RequestSubclass(RecordReviewDecisionRequest):  # type: ignore[misc]
        pass

    exact = request()
    subclass = RequestSubclass(
        correlation_id=exact.correlation_id,
        target=exact.target,
        assignment=exact.assignment,
        draft=exact.draft,
        idempotency_key=exact.idempotency_key,
        supersedes_decision_id=None,
    )
    recorded = adapter(step(value=exact))

    with pytest.raises(ReviewDecisionOperationFailure) as captured:
        service(recorded).execute(request=subclass)

    _assert_sanitized(captured, ReviewDecisionOperationFailureCode.INVALID_ARGUMENT)
    assert object.__getattribute__(recorded, "_index") == 0
