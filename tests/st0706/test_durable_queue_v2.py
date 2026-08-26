"""Behavioral evidence for the versioned recorded durable ST-0706 seam."""

from __future__ import annotations

from datetime import timedelta
import json
from threading import Barrier, Thread
from uuid import UUID

import pytest

from .support import NOW, OUTPUT_ARTIFACT_ID, command_and_controls
from raos.adapters.recorded_durable_ai_job_queue_v2 import (
    RecordedDurableAiJobStateAdapterV2,
)
from raos.application.ai.durable_job_queue_v2 import (
    RecordedDurableAiJobQueueServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.durable_job_queue_v2 import (
    DurableDecisionCode,
    DurableJobStatus,
    DurableLeaseClaim,
    MAXIMUM_CUMULATIVE_RETRY_BACKOFF_SECONDS,
    POLICY_SHA256,
    DurableQueueFailure,
    DurableQueueFailureCode,
    RecordedAttemptKind,
    RecordedAttemptOutcome,
    RecordedDurableQueueActivation,
)
from raos.domain.ai.job_orchestration import (
    AiJobEventType,
    ProviderFailureClass,
    ValidationFailureClass,
    ValidationStatus,
)


QUEUE_ID = "queue.st0706.recorded-durable.v2"
WORKER_ID = "worker.st0706.recorded.v2"
LEASE_NONCE = "9" * 64


def _service(
    adapter: RecordedDurableAiJobStateAdapterV2,
) -> RecordedDurableAiJobQueueServiceV2:
    return RecordedDurableAiJobQueueServiceV2(
        activation=RecordedDurableQueueActivation(
            environment=RuntimeEnvironment.ENV_DEV,
            enabled=True,
        ),
        state=adapter,
    )


def _success(
    ai_job_id: UUID, *, attempt_number: int = 1, cost: int = 7
) -> RecordedAttemptOutcome:
    return RecordedAttemptOutcome(
        kind=RecordedAttemptKind.SUCCEEDED,
        ai_job_id=ai_job_id,
        attempt_number=attempt_number,
        provider_request_id=f"request.success.st0706.v2.{attempt_number}",
        actual_cost_jpy=cost,
        validation_status=ValidationStatus.PASS,
        output_artifact_id=OUTPUT_ARTIFACT_ID,
        output_artifact_sha256="6" * 64,
    )


def _retryable_failure(
    ai_job_id: UUID,
    *,
    attempt_number: int,
    cost: int | None = 2,
) -> RecordedAttemptOutcome:
    return RecordedAttemptOutcome(
        kind=RecordedAttemptKind.PROVIDER_FAILURE,
        ai_job_id=ai_job_id,
        attempt_number=attempt_number,
        provider_request_id=f"request.failure.st0706.v2.{attempt_number}",
        actual_cost_jpy=cost,
        provider_failure_class=ProviderFailureClass.TRANSIENT_ERROR,
        retryable=True,
    )


def test_disabled_is_the_default_and_ci_requires_explicit_activation() -> None:
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = RecordedDurableAiJobQueueServiceV2(
        activation=RecordedDurableQueueActivation(), state=adapter
    )
    command, _ = command_and_controls()
    with pytest.raises(DurableQueueFailure) as captured:
        service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    assert captured.value.code is DurableQueueFailureCode.DISABLED
    assert adapter.export_snapshot().revision == 0

    ci_service = RecordedDurableAiJobQueueServiceV2(
        activation=RecordedDurableQueueActivation(
            environment=RuntimeEnvironment.CI, enabled=True
        ),
        state=adapter,
    )
    assert (
        ci_service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW).status
        is DurableJobStatus.READY
    )


def test_enqueue_is_deterministically_idempotent_without_a_second_write_or_intent() -> (
    None
):
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)

    first = service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    before = adapter.export_snapshot()
    replay = service.enqueue(
        queue_id=QUEUE_ID,
        command=command,
        enqueued_at=NOW + timedelta(seconds=20),
    )
    after = adapter.export_snapshot()

    assert first.status is DurableJobStatus.READY
    assert replay.replayed is True
    assert replay.command_fingerprint_sha256 == first.command_fingerprint_sha256
    assert after.revision == before.revision == 1
    assert after.state_bytes == before.state_bytes
    assert len(service.outbox_intents(queue_id=QUEUE_ID)) == 1


def test_success_round_trips_bytes_into_a_new_adapter_and_service_instance() -> None:
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    claim = service.claim(
        queue_id=QUEUE_ID,
        worker_id=WORKER_ID,
        lease_nonce_sha256=LEASE_NONCE,
        now=NOW + timedelta(seconds=1),
    )
    outcome = _success(command.ai_job_id)
    completed = service.complete(
        claim=claim, outcome=outcome, now=NOW + timedelta(seconds=2)
    )
    exported = adapter.export_snapshot()

    restarted_adapter = RecordedDurableAiJobStateAdapterV2.from_snapshot(
        snapshot=exported
    )
    restarted_service = _service(restarted_adapter)
    replay = restarted_service.complete(
        claim=claim, outcome=outcome, now=NOW + timedelta(seconds=3)
    )

    assert completed.status is DurableJobStatus.SUCCEEDED
    assert completed.accumulated_cost_jpy == 7
    assert replay.replayed is True
    assert replay.status is completed.status
    assert replay.accumulated_cost_jpy == completed.accumulated_cost_jpy
    assert restarted_adapter.export_snapshot().state_bytes == exported.state_bytes
    assert tuple(
        intent.event_type.value
        for intent in restarted_service.outbox_intents(queue_id=QUEUE_ID)
    ) == (
        "jp.raos.ai.job_requested.v1",
        "jp.raos.ai.job_succeeded.v1",
    )


def test_retry_backoff_is_persisted_data_and_exhaustion_dead_letters_without_redrive() -> (
    None
):
    command, _ = command_and_controls(max_attempts=2)
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    first_claim = service.claim(
        queue_id=QUEUE_ID,
        worker_id=WORKER_ID,
        lease_nonce_sha256=LEASE_NONCE,
        now=NOW + timedelta(seconds=1),
    )
    first = service.complete(
        claim=first_claim,
        outcome=_retryable_failure(command.ai_job_id, attempt_number=1),
        now=NOW + timedelta(seconds=2),
    )

    assert first.status is DurableJobStatus.RETRY_SCHEDULED
    assert first.attempt_number == 2
    assert first.available_at == NOW + timedelta(seconds=9)
    assert len(service.outbox_intents(queue_id=QUEUE_ID)) == 1
    with pytest.raises(DurableQueueFailure) as early:
        service.claim(
            queue_id=QUEUE_ID,
            worker_id=WORKER_ID,
            lease_nonce_sha256="8" * 64,
            now=NOW + timedelta(seconds=8),
        )
    assert early.value.code is DurableQueueFailureCode.JOB_NOT_CLAIMABLE

    second_claim = service.claim(
        queue_id=QUEUE_ID,
        worker_id=WORKER_ID,
        lease_nonce_sha256="8" * 64,
        now=NOW + timedelta(seconds=9),
    )
    terminal = service.complete(
        claim=second_claim,
        outcome=_retryable_failure(command.ai_job_id, attempt_number=2),
        now=NOW + timedelta(seconds=10),
    )
    assert second_claim.lease_epoch == 2
    assert terminal.status is DurableJobStatus.DEAD_LETTERED
    assert terminal.decision_code is DurableDecisionCode.RETRY_EXHAUSTED
    assert terminal.accumulated_cost_jpy == 4
    assert len(service.outbox_intents(queue_id=QUEUE_ID)) == 2
    with pytest.raises(DurableQueueFailure) as no_redrive:
        service.claim(
            queue_id=QUEUE_ID,
            worker_id=WORKER_ID,
            lease_nonce_sha256="7" * 64,
            now=NOW + timedelta(seconds=50),
        )
    assert no_redrive.value.code is DurableQueueFailureCode.JOB_NOT_CLAIMABLE


@pytest.mark.parametrize(
    ("outcome", "decision"),
    (
        (
            lambda ai_job_id: _retryable_failure(
                ai_job_id, attempt_number=1, cost=None
            ),
            DurableDecisionCode.UNKNOWN_COST,
        ),
        (
            lambda ai_job_id: _success(ai_job_id, cost=11),
            DurableDecisionCode.COST_OVERRUN,
        ),
        (
            lambda ai_job_id: RecordedAttemptOutcome(
                kind=RecordedAttemptKind.INDETERMINATE,
                ai_job_id=ai_job_id,
                attempt_number=1,
                provider_request_id="request.indeterminate.st0706.v2",
                actual_cost_jpy=1,
            ),
            DurableDecisionCode.INDETERMINATE_OUTCOME,
        ),
    ),
)
def test_unknown_cost_overrun_and_indeterminate_observation_quarantine(
    outcome: object, decision: DurableDecisionCode
) -> None:
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    claim = service.claim(
        queue_id=QUEUE_ID,
        worker_id=WORKER_ID,
        lease_nonce_sha256=LEASE_NONCE,
        now=NOW + timedelta(seconds=1),
    )
    assert callable(outcome)
    observed = outcome(command.ai_job_id)
    assert type(observed) is RecordedAttemptOutcome
    result = service.complete(
        claim=claim,
        outcome=observed,
        now=NOW + timedelta(seconds=2),
    )
    assert result.status is DurableJobStatus.QUARANTINED
    assert result.decision_code is decision
    assert result.accumulated_cost_jpy == (
        1 if decision is DurableDecisionCode.INDETERMINATE_OUTCOME else 0
    )


def test_zero_cost_is_known_and_succeeds_while_negative_cost_is_invalid() -> None:
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    claim = service.claim(
        queue_id=QUEUE_ID,
        worker_id=WORKER_ID,
        lease_nonce_sha256=LEASE_NONCE,
        now=NOW + timedelta(seconds=1),
    )
    result = service.complete(
        claim=claim,
        outcome=_success(command.ai_job_id, cost=0),
        now=NOW + timedelta(seconds=2),
    )
    assert result.status is DurableJobStatus.SUCCEEDED
    assert result.accumulated_cost_jpy == 0

    with pytest.raises(DurableQueueFailure) as negative:
        _success(command.ai_job_id, cost=-1)
    assert negative.value.code is DurableQueueFailureCode.INVALID_REQUEST


def test_three_attempt_policy_has_strictly_increasing_bounded_retry_timestamps() -> (
    None
):
    command, _ = command_and_controls(max_attempts=3)
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    first_claim = service.claim(
        queue_id=QUEUE_ID,
        worker_id=WORKER_ID,
        lease_nonce_sha256="1" * 64,
        now=NOW + timedelta(seconds=1),
    )
    first_retry = service.complete(
        claim=first_claim,
        outcome=_retryable_failure(command.ai_job_id, attempt_number=1),
        now=NOW + timedelta(seconds=2),
    )
    second_claim = service.claim(
        queue_id=QUEUE_ID,
        worker_id=WORKER_ID,
        lease_nonce_sha256="2" * 64,
        now=first_retry.available_at,
    )
    second_completed_at = first_retry.available_at + timedelta(seconds=1)
    second_retry = service.complete(
        claim=second_claim,
        outcome=_retryable_failure(command.ai_job_id, attempt_number=2),
        now=second_completed_at,
    )

    assert first_retry.available_at - (NOW + timedelta(seconds=2)) == timedelta(
        seconds=7
    )
    assert second_retry.available_at - second_completed_at == timedelta(seconds=31)
    assert MAXIMUM_CUMULATIVE_RETRY_BACKOFF_SECONDS == 7 + 31
    assert second_retry.available_at > first_retry.available_at
    assert second_retry.available_at < command.deadline_at
    assert second_retry.attempt_number == 3

    third_claim = service.claim(
        queue_id=QUEUE_ID,
        worker_id=WORKER_ID,
        lease_nonce_sha256="3" * 64,
        now=second_retry.available_at,
    )
    exhausted = service.complete(
        claim=third_claim,
        outcome=_retryable_failure(command.ai_job_id, attempt_number=3),
        now=second_retry.available_at + timedelta(seconds=1),
    )
    assert exhausted.status is DurableJobStatus.DEAD_LETTERED
    assert exhausted.attempt_number == 3
    persisted = json.loads(adapter.export_snapshot().state_bytes)
    assert persisted["policy_sha256"] == POLICY_SHA256


def test_validation_failure_is_terminal_and_records_only_a_failed_intent() -> None:
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    claim = service.claim(
        queue_id=QUEUE_ID,
        worker_id=WORKER_ID,
        lease_nonce_sha256=LEASE_NONCE,
        now=NOW + timedelta(seconds=1),
    )
    outcome = RecordedAttemptOutcome(
        kind=RecordedAttemptKind.VALIDATION_FAILURE,
        ai_job_id=command.ai_job_id,
        attempt_number=1,
        provider_request_id="request.validation-failed.st0706.v2",
        actual_cost_jpy=3,
        validation_status=ValidationStatus.FAIL,
        validation_failure_class=ValidationFailureClass.SCHEMA,
        output_artifact_id=OUTPUT_ARTIFACT_ID,
        output_artifact_sha256="6" * 64,
    )
    result = service.complete(
        claim=claim, outcome=outcome, now=NOW + timedelta(seconds=2)
    )
    assert result.status is DurableJobStatus.FAILED_TERMINAL
    assert result.decision_code is DurableDecisionCode.VALIDATION_FAILED
    assert tuple(
        intent.event_type for intent in service.outbox_intents(queue_id=QUEUE_ID)
    ) == (
        AiJobEventType.REQUESTED,
        AiJobEventType.FAILED,
    )


def test_expired_lease_is_quarantined_after_restart_and_old_lease_is_rejected() -> None:
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    claim = service.claim(
        queue_id=QUEUE_ID,
        worker_id=WORKER_ID,
        lease_nonce_sha256=LEASE_NONCE,
        now=NOW + timedelta(seconds=1),
    )
    restarted = _service(
        RecordedDurableAiJobStateAdapterV2.from_snapshot(
            snapshot=adapter.export_snapshot()
        )
    )
    recovered = restarted.recover_next(
        queue_id=QUEUE_ID, now=NOW + timedelta(seconds=31)
    )
    assert recovered is not None
    assert recovered.status is DurableJobStatus.QUARANTINED
    assert recovered.decision_code is DurableDecisionCode.LEASE_EXPIRED_AMBIGUOUS
    with pytest.raises(DurableQueueFailure) as stale:
        restarted.complete(
            claim=claim,
            outcome=_success(command.ai_job_id),
            now=NOW + timedelta(seconds=32),
        )
    assert stale.value.code is DurableQueueFailureCode.LEASE_MISMATCH


def test_cancellation_and_unclaimed_deadline_end_without_a_lease_or_retry() -> None:
    cancelled, _ = command_and_controls(
        cancellation_requested=True,
        cancel_requested_at=NOW,
    )
    cancelled_adapter = RecordedDurableAiJobStateAdapterV2(
        queue_id="queue.st0706.cancelled.v2"
    )
    cancelled_service = _service(cancelled_adapter)
    cancelled_view = cancelled_service.enqueue(
        queue_id="queue.st0706.cancelled.v2",
        command=cancelled,
        enqueued_at=NOW,
    )
    assert cancelled_view.status is DurableJobStatus.CANCELLED
    assert cancelled_view.decision_code is DurableDecisionCode.COMMAND_CANCELLED
    assert (
        len(cancelled_service.outbox_intents(queue_id="queue.st0706.cancelled.v2")) == 2
    )

    expiring, _ = command_and_controls(deadline_at=NOW + timedelta(seconds=5))
    expiring_adapter = RecordedDurableAiJobStateAdapterV2(
        queue_id="queue.st0706.expiring.v2"
    )
    expiring_service = _service(expiring_adapter)
    expiring_service.enqueue(
        queue_id="queue.st0706.expiring.v2", command=expiring, enqueued_at=NOW
    )
    expired = expiring_service.recover_next(
        queue_id="queue.st0706.expiring.v2",
        now=NOW + timedelta(seconds=5),
    )
    assert expired is not None
    assert expired.status is DurableJobStatus.EXPIRED
    assert expired.decision_code is DurableDecisionCode.DEADLINE_EXPIRED
    with pytest.raises(DurableQueueFailure) as unclaimable:
        expiring_service.claim(
            queue_id="queue.st0706.expiring.v2",
            worker_id=WORKER_ID,
            lease_nonce_sha256="4" * 64,
            now=NOW + timedelta(seconds=6),
        )
    assert unclaimable.value.code is DurableQueueFailureCode.JOB_NOT_CLAIMABLE


def test_two_concurrent_claimers_produce_exactly_one_lease() -> None:
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service_one = _service(adapter)
    service_two = _service(adapter)
    service_one.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    barrier = Barrier(3)
    claims: list[DurableLeaseClaim] = []
    failures: list[DurableQueueFailureCode] = []

    def claim(service: RecordedDurableAiJobQueueServiceV2, nonce: str) -> None:
        barrier.wait()
        try:
            claims.append(
                service.claim(
                    queue_id=QUEUE_ID,
                    worker_id=WORKER_ID,
                    lease_nonce_sha256=nonce,
                    now=NOW + timedelta(seconds=1),
                )
            )
        except DurableQueueFailure as failure:
            failures.append(failure.code)

    threads = (
        Thread(target=claim, args=(service_one, "1" * 64)),
        Thread(target=claim, args=(service_two, "2" * 64)),
    )
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert len(claims) == 1
    assert failures in (
        [DurableQueueFailureCode.CAS_CONFLICT],
        [DurableQueueFailureCode.JOB_NOT_CLAIMABLE],
    )
    assert (
        service_one.view(queue_id=QUEUE_ID, ai_job_id=command.ai_job_id).lease_epoch
        == 1
    )
