from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from uuid import UUID

import pytest

from raos.adapters.recorded_final_approval import (
    RecordedFinalApprovalAdapter,
    RecordedFinalApprovalStep,
    load_recorded_final_approval_fixture,
)
from raos.application.publishing.final_approval import FinalApprovalService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.final_approval import (
    FinalApprovalFailure,
    FinalApprovalFailureCode,
    FinalApprovalId,
    FinalApprovalRequestV2,
    FinalApprovalResultV2,
    RecordedFinalApprovalAuthorizationV2,
)

from .conftest import request_with


def uuid7(suffix: int) -> UUID:
    return UUID(f"018f3e90-7b00-7000-8000-{suffix:012d}")


def service(
    step: RecordedFinalApprovalStep,
) -> tuple[FinalApprovalService, RecordedFinalApprovalAdapter]:
    adapter = RecordedFinalApprovalAdapter(
        environment=RuntimeEnvironment.CI,
        steps=(step,),
    )
    return (
        FinalApprovalService(
            environment=RuntimeEnvironment.CI,
            authorization_source=adapter,
            exchange=adapter,
        ),
        adapter,
    )


def test_service_executes_without_caller_actor_and_replays_exact_result(
    step: RecordedFinalApprovalStep,
) -> None:
    subject, adapter = service(step)
    first = subject.execute(request=step.request)
    second = subject.execute(request=step.request)

    assert first is second
    assert first.canonical_bytes() == second.canonical_bytes()
    assert adapter.consumed_steps == 1


def test_concurrent_same_request_consumes_one_step(
    step: RecordedFinalApprovalStep,
) -> None:
    subject, adapter = service(step)

    def execute_once(_index: int) -> FinalApprovalResultV2:
        return subject.execute(request=step.request)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = tuple(pool.map(execute_once, range(32)))
    assert len({id(item) for item in results}) == 1
    assert adapter.consumed_steps == 1


@pytest.mark.parametrize(
    "environment",
    [
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.PRODUCTION,
        RuntimeEnvironment.RECOVERY,
    ],
)
def test_nonlocal_runtime_is_rejected(
    step: RecordedFinalApprovalStep,
    environment: RuntimeEnvironment,
) -> None:
    class Source:
        def issue_authorization(
            self,
            request: FinalApprovalRequestV2,
        ) -> RecordedFinalApprovalAuthorizationV2:
            del request
            return step.authorization

    class Exchange:
        def exchange(
            self,
            authorization: RecordedFinalApprovalAuthorizationV2,
            request: FinalApprovalRequestV2,
        ) -> FinalApprovalResultV2:
            del authorization, request
            return step.result

    with pytest.raises(FinalApprovalFailure) as captured:
        RecordedFinalApprovalAdapter(environment=environment, steps=(step,))
    assert captured.value.code is FinalApprovalFailureCode.LOCAL_ENVIRONMENT_REQUIRED
    with pytest.raises(FinalApprovalFailure) as captured:
        FinalApprovalService(
            environment=environment,
            authorization_source=Source(),
            exchange=Exchange(),
        )
    assert captured.value.code is FinalApprovalFailureCode.LOCAL_ENVIRONMENT_REQUIRED


def test_same_idempotency_key_changed_request_fails_before_consumption(
    step: RecordedFinalApprovalStep,
) -> None:
    _subject, adapter = service(step)
    changed = request_with(
        step.request,
        approval_id=FinalApprovalId(uuid7(950)),
    )
    with pytest.raises(FinalApprovalFailure) as captured:
        adapter.issue_authorization(changed)
    assert captured.value.code is FinalApprovalFailureCode.IDEMPOTENCY_CONFLICT
    assert adapter.consumed_steps == 0


def test_service_refuses_wrong_authorization_before_exchange(
    step: RecordedFinalApprovalStep,
) -> None:
    authorization = RecordedFinalApprovalAuthorizationV2(
        request_sha256=step.request.request_sha256,
        actor=step.actor,
    )
    object.__setattr__(authorization, "external_authority", True)

    class Source:
        def issue_authorization(
            self,
            request: FinalApprovalRequestV2,
        ) -> RecordedFinalApprovalAuthorizationV2:
            del request
            return authorization

    class Exchange:
        called = False

        def exchange(
            self,
            authorization: RecordedFinalApprovalAuthorizationV2,
            request: FinalApprovalRequestV2,
        ) -> FinalApprovalResultV2:
            del authorization, request
            self.called = True
            return step.result

    exchange = Exchange()
    subject = FinalApprovalService(
        environment=RuntimeEnvironment.CI,
        authorization_source=Source(),
        exchange=exchange,
    )
    with pytest.raises(FinalApprovalFailure) as captured:
        subject.execute(request=step.request)
    assert captured.value.code is FinalApprovalFailureCode.AUTHORIZATION_INVALID
    assert exchange.called is False


def test_service_revalidates_separation_before_exchange(
    step: RecordedFinalApprovalStep,
) -> None:
    actor = replace(
        step.actor,
        principal_id=step.request.review_result.record.decided_by,
    )
    authorization = RecordedFinalApprovalAuthorizationV2(
        request_sha256=step.request.request_sha256,
        actor=actor,
    )

    class Source:
        def issue_authorization(
            self,
            request: FinalApprovalRequestV2,
        ) -> RecordedFinalApprovalAuthorizationV2:
            del request
            return authorization

    class Exchange:
        called = False

        def exchange(
            self,
            authorization: RecordedFinalApprovalAuthorizationV2,
            request: FinalApprovalRequestV2,
        ) -> FinalApprovalResultV2:
            del authorization, request
            self.called = True
            return step.result

    exchange = Exchange()
    subject = FinalApprovalService(
        environment=RuntimeEnvironment.CI,
        authorization_source=Source(),
        exchange=exchange,
    )
    with pytest.raises(FinalApprovalFailure) as captured:
        subject.execute(request=step.request)
    assert captured.value.code is FinalApprovalFailureCode.AUTHORIZATION_INVALID
    assert exchange.called is False


def test_service_refuses_forged_exchange_result(
    step: RecordedFinalApprovalStep,
) -> None:
    class Source:
        def issue_authorization(
            self,
            request: FinalApprovalRequestV2,
        ) -> RecordedFinalApprovalAuthorizationV2:
            del request
            return step.authorization

    class Exchange:
        def exchange(
            self,
            authorization: RecordedFinalApprovalAuthorizationV2,
            request: FinalApprovalRequestV2,
        ) -> FinalApprovalResultV2:
            del authorization, request
            object.__setattr__(step.result, "publication_authorized", True)
            return step.result

    subject = FinalApprovalService(
        environment=RuntimeEnvironment.CI,
        authorization_source=Source(),
        exchange=Exchange(),
    )
    with pytest.raises(FinalApprovalFailure) as captured:
        subject.execute(request=step.request)
    assert captured.value.code is FinalApprovalFailureCode.OUTCOME_MISMATCH


def test_fixture_refuses_duplicate_unknown_and_dependency_hash_tamper(
    fixture_bytes: bytes,
    policy_fixture: bytes,
    review_fixture: bytes,
) -> None:
    text = fixture_bytes.decode("utf-8")
    duplicate = text.replace(
        '"schema_version":2',
        '"schema_version":2,"schema_version":2',
        1,
    )
    unknown = text.replace(
        '"schema_version":2',
        '"unknown":0,"schema_version":2',
        1,
    )
    document = json.loads(text)
    document["bindings"]["review_fixture_sha256"] = "0" * 64
    tampered = json.dumps(document, separators=(",", ":")).encode()
    for candidate in (duplicate.encode(), unknown.encode(), tampered):
        with pytest.raises(FinalApprovalFailure) as captured:
            load_recorded_final_approval_fixture(
                candidate,
                policy_fixture=policy_fixture,
                review_fixture=review_fixture,
            )
        assert captured.value.code is FinalApprovalFailureCode.FIXTURE_INVALID


def test_fixture_refuses_authority_escalation_and_oversize(
    fixture_bytes: bytes,
    policy_fixture: bytes,
    review_fixture: bytes,
) -> None:
    document = json.loads(fixture_bytes)
    document["authority"]["publication_authorized"] = True
    escalated = json.dumps(document, separators=(",", ":")).encode()
    for candidate in (escalated, fixture_bytes + b" " * (512 * 1024)):
        with pytest.raises(FinalApprovalFailure) as captured:
            load_recorded_final_approval_fixture(
                candidate,
                policy_fixture=policy_fixture,
                review_fixture=review_fixture,
            )
        assert captured.value.code is FinalApprovalFailureCode.FIXTURE_INVALID
