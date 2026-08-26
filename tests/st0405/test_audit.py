"""Hostile unit tests for the maximum-safe local ST-0405 seam."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
import inspect
import pickle
from typing import cast
from uuid import UUID

import pytest

from .support import (
    ACTOR_ID,
    ARTICLE_ID,
    CORRELATION_ID,
    EVENT_ID,
    OTHER_EVENT_ID,
    audit_context,
    audit_event,
    authorization_grant,
    service_bundle,
)
from raos.adapters.recorded_audit import RecordedAuditAdapter
from raos.application.ops.audit import (
    AuditCommitToken,
    AuditFailure,
    AuditFailureCode,
    AuditService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authorization import AuthorizationGrant, ResourceScopeKind
from raos.domain.ops.audit import (
    AuditAction,
    AuditActor,
    AuditActorType,
    AuditContext,
    AuditEvent,
    AuditEventId,
    AuditOutcome,
    AuditReasonCode,
    AuditRequestId,
    AuditSeverity,
    AuditTargetType,
)
from raos.ports.audit import AuditAppendOutcome, AuditAppendReceipt


class _FixedOffset(tzinfo):
    def utcoffset(self, value: datetime | None) -> timedelta:
        del value
        return timedelta(0)

    def dst(self, value: datetime | None) -> timedelta:
        del value
        return timedelta(0)

    def tzname(self, value: datetime | None) -> str:
        del value
        return "TEST_ZERO_OFFSET"


class _ExplodingReprError(Exception):
    def __repr__(self) -> str:
        raise AssertionError("repr must not be called")

    def __str__(self) -> str:
        raise AssertionError("str must not be called")


class _FatalAuditBoundary(BaseException):
    pass


def _record(service: AuditService, grant: AuthorizationGrant) -> AuditCommitToken:
    return service.require_authorized_record(
        grant=grant,
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.NOTICE,
        reason_code=AuditReasonCode("TEST_ONLY:AUTHORIZED_CHANGE"),
        before_hash="a" * 64,
        after_hash="b" * 64,
    )


def _assert_failed(call: object) -> AuditFailure:
    assert callable(call)
    with pytest.raises(AuditFailure) as caught:
        call()
    error = caught.value
    assert type(error) is AuditFailure
    assert error.code is AuditFailureCode.REQUIRED_RECORD_NOT_COMMITTED
    assert str(error) == "REQUIRED_RECORD_NOT_COMMITTED"
    assert repr(error) == "AuditFailure(REQUIRED_RECORD_NOT_COMMITTED)"
    assert error.__cause__ is None
    assert error.__context__ is None
    return error


def test_exact_record_binds_grant_fields_and_returns_validated_token() -> None:
    grant = authorization_grant()
    context = audit_context(grant)
    service, adapter = service_bundle(contexts=(context,), capacity=1)
    business_state = {"mutated": False}

    commit_token = _record(service, grant)

    assert type(commit_token) is AuditCommitToken
    assert commit_token.event_id == AuditEventId(EVENT_ID)
    assert len(commit_token.event_digest) == 64
    assert business_state == {"mutated": False}
    assert len(adapter.snapshot()) == 1
    event = adapter.snapshot()[0]
    assert event.event_id == commit_token.event_id
    assert event.digest == commit_token.event_digest
    assert event.actor_type is AuditActorType.USER
    assert event.actor_id == ACTOR_ID
    assert event.action == AuditAction("TEST_ONLY:AUDIT_CRITICAL")
    assert event.target_type == AuditTargetType("ARTICLE")
    assert event.target_id == ARTICLE_ID
    assert event.correlation_id == CORRELATION_ID
    assert event.outcome is AuditOutcome.SUCCESS
    assert event.severity is AuditSeverity.NOTICE
    assert event.reason_code == AuditReasonCode("TEST_ONLY:AUTHORIZED_CHANGE")
    assert event.before_hash == "a" * 64
    assert event.after_hash == "b" * 64


@pytest.mark.parametrize(
    "value",
    [
        "",
        "x" * 129,
        " leading",
        "trailing ",
        "line\nbreak",
        "fullwidth＿value",
        "a..",
        True,
        1,
        object(),
    ],
)
@pytest.mark.parametrize(
    "token_type", [AuditAction, AuditTargetType, AuditReasonCode, AuditRequestId]
)
def test_bounded_tokens_reject_raw_control_confusable_and_non_string_values(
    token_type: type[object], value: object
) -> None:
    with pytest.raises(ValueError, match="^invalid audit value$") as caught:
        token_type(value)  # type: ignore[call-arg]
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_uuid_and_utc_values_are_exact_and_non_nil() -> None:
    with pytest.raises(ValueError, match="^invalid audit value$"):
        AuditEventId("55555555-5555-4555-8555-555555555555")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="^invalid audit value$"):
        AuditEventId(UUID(int=0))

    grant = authorization_grant()
    for observed_at in (
        datetime(2026, 8, 10, 12, 0),
        datetime(2026, 8, 10, 12, 0, tzinfo=_FixedOffset()),
        datetime(2026, 8, 10, 12, 0, tzinfo=timezone(timedelta(hours=9))),
    ):
        with pytest.raises(ValueError, match="^invalid audit value$"):
            audit_context(grant, occurred_at=observed_at)


@pytest.mark.parametrize(
    ("actor_type", "actor_id", "accepted"),
    [
        (AuditActorType.USER, ACTOR_ID, True),
        (AuditActorType.SERVICE, ACTOR_ID, True),
        (AuditActorType.SCHEDULE, ACTOR_ID, True),
        (AuditActorType.SYSTEM, None, True),
        (AuditActorType.ANONYMOUS, None, True),
        (AuditActorType.USER, None, False),
        (AuditActorType.SERVICE, None, False),
        (AuditActorType.SCHEDULE, None, False),
        (AuditActorType.SYSTEM, ACTOR_ID, False),
        (AuditActorType.ANONYMOUS, ACTOR_ID, False),
    ],
)
def test_actor_identifier_rules_are_explicit(
    actor_type: AuditActorType, actor_id: UUID | None, accepted: bool
) -> None:
    if accepted:
        assert type(AuditActor(actor_type=actor_type, actor_id=actor_id)) is AuditActor
    else:
        with pytest.raises(ValueError, match="^invalid audit value$"):
            AuditActor(actor_type=actor_type, actor_id=actor_id)


@pytest.mark.parametrize(
    "bad_hash", ["A" * 64, "0" * 63, "0" * 65, True, "safe\nvalue"]
)
def test_hashes_are_exact_lowercase_sha256(bad_hash: object) -> None:
    grant = authorization_grant()
    service, _ = service_bundle(contexts=(audit_context(grant),), capacity=1)
    _assert_failed(
        lambda: service.require_authorized_record(
            grant=grant,
            outcome=AuditOutcome.SUCCESS,
            severity=AuditSeverity.INFO,
            reason_code=AuditReasonCode("TEST_ONLY:CHANGE"),
            before_hash=bad_hash,  # type: ignore[arg-type]
        )
    )


def test_context_fields_cannot_override_grant_action_target_or_correlation() -> None:
    grant = authorization_grant()
    other = authorization_grant(
        action="TEST_ONLY:OTHER_ACTION",
        resource_id=UUID("77777777-7777-4777-8777-777777777777"),
        correlation_id=UUID("88888888-8888-4888-8888-888888888888"),
        kind=ResourceScopeKind.CATEGORY,
    )
    forged_context = audit_context(other)

    class ContextSource:
        def issue(self, supplied_grant: AuthorizationGrant) -> AuditContext:
            assert supplied_grant is grant
            return forged_context

    class Appender:
        calls = 0

        def append(self, event: AuditEvent) -> AuditAppendReceipt:
            del event
            self.calls += 1
            raise AssertionError("must not append a mismatched context")

    appender = Appender()
    service = AuditService(context_source=ContextSource(), appender=appender)
    _assert_failed(lambda: _record(service, grant))
    assert appender.calls == 0
    assert set(inspect.signature(AuditContext).parameters) == {
        "grant",
        "event_id",
        "actor",
        "occurred_at",
        "request_id",
    }


@pytest.mark.parametrize("malformed", [None, object(), "RECORDED", True])
def test_malformed_appender_return_fails_once_without_retry(malformed: object) -> None:
    grant = authorization_grant()

    class ContextSource:
        calls = 0

        def issue(self, supplied_grant: AuthorizationGrant) -> AuditContext:
            self.calls += 1
            return audit_context(supplied_grant)

    class Appender:
        calls = 0

        def append(self, event: AuditEvent) -> object:
            assert type(event) is AuditEvent
            self.calls += 1
            return malformed

    source = ContextSource()
    appender = Appender()
    service = AuditService(context_source=source, appender=appender)  # type: ignore[arg-type]
    _assert_failed(lambda: _record(service, grant))
    assert source.calls == 1
    assert appender.calls == 1


def test_collaborator_exception_is_not_stringified_retained_or_retried() -> None:
    grant = authorization_grant()

    class ContextSource:
        calls = 0

        def issue(self, supplied_grant: AuthorizationGrant) -> AuditContext:
            del supplied_grant
            self.calls += 1
            raise _ExplodingReprError()

    class Appender:
        calls = 0

        def append(self, event: AuditEvent) -> AuditAppendReceipt:
            del event
            self.calls += 1
            raise AssertionError("must not append")

    source = ContextSource()
    appender = Appender()
    service = AuditService(context_source=source, appender=appender)
    _assert_failed(lambda: _record(service, grant))
    assert source.calls == 1
    assert appender.calls == 0


def test_base_exception_from_either_port_propagates() -> None:
    grant = authorization_grant()

    class FatalContextSource:
        def issue(self, supplied_grant: AuthorizationGrant) -> AuditContext:
            del supplied_grant
            raise _FatalAuditBoundary()

    class NeverAppender:
        def append(self, event: AuditEvent) -> AuditAppendReceipt:
            del event
            raise AssertionError("must not append")

    with pytest.raises(_FatalAuditBoundary):
        _record(
            AuditService(context_source=FatalContextSource(), appender=NeverAppender()),
            grant,
        )

    class ContextSource:
        def issue(self, supplied_grant: AuthorizationGrant) -> AuditContext:
            return audit_context(supplied_grant)

    class FatalAppender:
        def append(self, event: AuditEvent) -> AuditAppendReceipt:
            del event
            raise _FatalAuditBoundary()

    with pytest.raises(_FatalAuditBoundary):
        _record(
            AuditService(context_source=ContextSource(), appender=FatalAppender()),
            grant,
        )


def test_receipt_tampering_and_subclass_return_fail_closed() -> None:
    grant = authorization_grant()

    class ContextSource:
        def issue(self, supplied_grant: AuthorizationGrant) -> AuditContext:
            return audit_context(supplied_grant)

    class ReceiptAppender:
        def __init__(self, receipt_kind: str) -> None:
            self.receipt_kind = receipt_kind
            self.calls = 0

        def append(self, event: AuditEvent) -> AuditAppendReceipt:
            self.calls += 1
            if self.receipt_kind == "event":
                return AuditAppendReceipt(
                    event_id=AuditEventId(OTHER_EVENT_ID),
                    event_digest=event.digest,
                    outcome=AuditAppendOutcome.RECORDED,
                )
            if self.receipt_kind == "digest":
                return AuditAppendReceipt(
                    event_id=event.event_id,
                    event_digest="0" * 64,
                    outcome=AuditAppendOutcome.RECORDED,
                )

            receipt_subclass = type(
                "ReceiptSubclass",
                (AuditAppendReceipt,),
                {},
            )
            return cast(
                AuditAppendReceipt,
                receipt_subclass(
                    event_id=event.event_id,
                    event_digest=event.digest,
                    outcome=AuditAppendOutcome.RECORDED,
                ),
            )

    for receipt_kind in ("event", "digest", "subclass"):
        appender = ReceiptAppender(receipt_kind)
        service = AuditService(context_source=ContextSource(), appender=appender)
        _assert_failed(lambda: _record(service, grant))
        assert appender.calls == 1


def test_recorded_adapter_rejects_wrong_environment_capacity_and_script_shape() -> None:
    grant = authorization_grant()
    context = audit_context(grant)
    for environment in (
        RuntimeEnvironment.CI,
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.PRODUCTION,
    ):
        with pytest.raises(ValueError, match="^recorded audit operation failed$"):
            RecordedAuditAdapter(
                environment=environment,
                capacity=1,
                context_script=(context,),
            )
    for capacity in (0, -1, True, 10_001):
        with pytest.raises(ValueError, match="^recorded audit operation failed$"):
            RecordedAuditAdapter(
                environment=RuntimeEnvironment.ENV_DEV,
                capacity=capacity,
                context_script=(context,),
            )


def test_full_capacity_fails_without_eviction_or_mutation() -> None:
    first_grant = authorization_grant()
    second_grant = authorization_grant(
        correlation_id=UUID("99999999-9999-4999-8999-999999999999")
    )
    contexts = (
        audit_context(first_grant, event_id=EVENT_ID),
        audit_context(second_grant, event_id=OTHER_EVENT_ID),
    )
    service, adapter = service_bundle(contexts=contexts, capacity=1)
    first = _record(service, first_grant)
    snapshot = adapter.snapshot()

    _assert_failed(lambda: _record(service, second_grant))

    assert adapter.snapshot() is snapshot
    assert adapter.snapshot()[0].event_id == first.event_id


def test_duplicate_event_and_digest_tamper_fail_without_eviction() -> None:
    grant = authorization_grant()
    context = audit_context(grant)
    adapter = RecordedAuditAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        capacity=2,
        context_script=(context,),
    )
    event = audit_event(grant, context=context)
    receipt = adapter.append(event)
    snapshot = adapter.snapshot()
    assert receipt.event_digest == event.digest

    with pytest.raises(ValueError, match="^recorded audit operation failed$"):
        adapter.append(event)
    assert adapter.snapshot() is snapshot

    tampered = audit_event(
        grant,
        context=audit_context(grant, event_id=OTHER_EVENT_ID),
    )
    object.__setattr__(tampered, "_digest", "0" * 64)
    with pytest.raises(ValueError, match="^recorded audit operation failed$"):
        adapter.append(tampered)
    assert adapter.snapshot() is snapshot


def test_values_token_failure_receipt_and_snapshot_are_redacted_non_pickleable() -> (
    None
):
    grant = authorization_grant(action="CANARY_SAFE_ACTION")
    context = audit_context(
        grant,
        request_id=AuditRequestId("CANARY_SAFE_REQUEST"),
    )
    service, adapter = service_bundle(contexts=(context,), capacity=1)
    commit_token = service.require_authorized_record(
        grant=grant,
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.INFO,
        reason_code=AuditReasonCode("CANARY_SAFE_REASON"),
    )
    event = adapter.snapshot()[0]
    receipt = AuditAppendReceipt(
        event_id=event.event_id,
        event_digest=event.digest,
        outcome=AuditAppendOutcome.RECORDED,
    )
    values = (context.actor, context, event, commit_token, receipt, adapter)

    for value in values:
        rendered = repr(value)
        assert "CANARY_SAFE" not in rendered
        with pytest.raises(TypeError) as caught:
            pickle.dumps(value)
        assert "CANARY_SAFE" not in str(caught.value)
        assert "CANARY_SAFE" not in repr(caught.value)
    assert "CANARY_SAFE" not in repr(adapter.snapshot())


def test_domain_has_no_arbitrary_details_or_business_callback_surface() -> None:
    assert "details" not in inspect.signature(AuditEvent).parameters
    assert "details" not in AuditEvent.__slots__
    assert set(
        inspect.signature(AuditService.require_authorized_record).parameters
    ) == {
        "self",
        "grant",
        "outcome",
        "severity",
        "reason_code",
        "before_hash",
        "after_hash",
    }
    assert not any(
        name in inspect.signature(AuditService.require_authorized_record).parameters
        for name in ("callback", "operation", "mutation", "business_action")
    )


def test_enum_and_service_boundaries_reject_raw_strings_and_bool() -> None:
    grant = authorization_grant()
    service, adapter = service_bundle(contexts=(audit_context(grant),), capacity=1)
    for field, value in (
        ("outcome", "SUCCESS"),
        ("severity", "INFO"),
        ("reason_code", "TEST_ONLY:REASON"),
        ("outcome", True),
    ):
        arguments: dict[str, object] = {
            "grant": grant,
            "outcome": AuditOutcome.SUCCESS,
            "severity": AuditSeverity.INFO,
            "reason_code": AuditReasonCode("TEST_ONLY:REASON"),
        }
        arguments[field] = value
        _assert_failed(lambda args=arguments: service.require_authorized_record(**args))
    assert adapter.snapshot() == ()


def test_exhausted_context_script_fails_without_append() -> None:
    grant = authorization_grant()
    service, adapter = service_bundle(contexts=(), capacity=1)
    _assert_failed(lambda: _record(service, grant))
    assert adapter.snapshot() == ()
