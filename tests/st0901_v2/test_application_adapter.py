from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from uuid import UUID

import pytest

from raos.adapters.recorded_review_completion import (
    RecordedReviewCompletionAdapter,
    RecordedReviewCompletionStep,
    load_recorded_review_completion_fixture,
)
from raos.application.publishing.review_completion import ReviewCompletionService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.review_completion_v2 import (
    RecordedReviewCompletionAuthorizationV2,
    ReviewCompletionFailure,
    ReviewCompletionFailureCode,
    ReviewCompletionRequestV2,
    ReviewCompletionResultV2,
)
from raos.domain.publishing.review_decision_operations import (
    RecordedIdentityProjection,
    RecordedSubjectKind,
    RecordedSubjectStatus,
)
from raos.domain.publishing.review_workflow import PrincipalId, ReviewDecisionId

from .conftest import request_with


def uuid7(suffix: int) -> UUID:
    return UUID(f"018f3e90-7b00-7000-8000-{suffix:012d}")


def service(
    step: RecordedReviewCompletionStep,
) -> tuple[ReviewCompletionService, RecordedReviewCompletionAdapter]:
    adapter = RecordedReviewCompletionAdapter(
        environment=RuntimeEnvironment.CI,
        steps=(step,),
    )
    return (
        ReviewCompletionService(
            environment=RuntimeEnvironment.CI,
            authorization_source=adapter,
            exchange=adapter,
        ),
        adapter,
    )


def test_service_executes_without_caller_actor_and_replays_exact_result(
    step: RecordedReviewCompletionStep,
) -> None:
    subject, adapter = service(step)
    first = subject.execute(request=step.request)
    second = subject.execute(request=step.request)

    assert first is second
    assert first.canonical_bytes() == second.canonical_bytes()
    assert adapter.consumed_steps == 1


def test_concurrent_same_request_consumes_one_step(
    step: RecordedReviewCompletionStep,
) -> None:
    subject, adapter = service(step)

    def execute_once(_index: int) -> ReviewCompletionResultV2:
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
    step: RecordedReviewCompletionStep, environment: RuntimeEnvironment
) -> None:
    with pytest.raises(ReviewCompletionFailure) as captured:
        RecordedReviewCompletionAdapter(environment=environment, steps=(step,))
    assert captured.value.code is ReviewCompletionFailureCode.LOCAL_ENVIRONMENT_REQUIRED


def test_same_idempotency_key_changed_request_fails_before_consumption(
    step: RecordedReviewCompletionStep,
) -> None:
    _subject, adapter = service(step)
    changed = request_with(
        step.request,
        decision_id=ReviewDecisionId(uuid7(930)),
    )
    with pytest.raises(ReviewCompletionFailure) as captured:
        adapter.issue_authorization(changed)
    assert captured.value.code is ReviewCompletionFailureCode.IDEMPOTENCY_CONFLICT
    assert adapter.consumed_steps == 0


def test_wrong_recorded_actor_is_rejected_before_exchange(
    step: RecordedReviewCompletionStep,
) -> None:
    actor = RecordedIdentityProjection(
        principal_id=PrincipalId(uuid7(931)),
        subject_kind=RecordedSubjectKind.HUMAN,
        subject_status=RecordedSubjectStatus.ACTIVE,
    )
    authorization = RecordedReviewCompletionAuthorizationV2(
        request_sha256=step.request.request_sha256,
        actor=actor,
    )

    class Source:
        def issue_authorization(
            self,
            request: ReviewCompletionRequestV2,
        ) -> RecordedReviewCompletionAuthorizationV2:
            del request
            return authorization

    class Exchange:
        called = False

        def exchange(
            self,
            authorization: RecordedReviewCompletionAuthorizationV2,
            request: ReviewCompletionRequestV2,
        ) -> ReviewCompletionResultV2:
            del authorization, request
            self.called = True
            return step.result

    exchange = Exchange()
    subject = ReviewCompletionService(
        environment=RuntimeEnvironment.CI,
        authorization_source=Source(),
        exchange=exchange,
    )
    with pytest.raises(ReviewCompletionFailure) as captured:
        subject.execute(request=step.request)
    assert captured.value.code is ReviewCompletionFailureCode.AUTHORIZATION_INVALID
    assert exchange.called is False


def test_fixture_refuses_duplicate_unknown_and_policy_hash_tamper(
    fixture_bytes: bytes,
    policy_fixture: bytes,
) -> None:
    text = fixture_bytes.decode("utf-8")
    duplicate = text.replace(
        '"schema_version":2', '"schema_version":2,"schema_version":2', 1
    )
    unknown = text.replace('"schema_version":2', '"unknown":0,"schema_version":2', 1)
    document = json.loads(text)
    document["policy"]["fixture_sha256"] = "0" * 64
    tampered = json.dumps(document, separators=(",", ":")).encode()
    for candidate in (duplicate.encode(), unknown.encode(), tampered):
        with pytest.raises(ReviewCompletionFailure) as captured:
            load_recorded_review_completion_fixture(
                candidate,
                policy_fixture=policy_fixture,
            )
        assert captured.value.code is ReviewCompletionFailureCode.FIXTURE_INVALID


def test_fixture_refuses_oversize(fixture_bytes: bytes, policy_fixture: bytes) -> None:
    with pytest.raises(ReviewCompletionFailure) as captured:
        load_recorded_review_completion_fixture(
            fixture_bytes + b" " * (128 * 1024),
            policy_fixture=policy_fixture,
        )
    assert captured.value.code is ReviewCompletionFailureCode.FIXTURE_INVALID
