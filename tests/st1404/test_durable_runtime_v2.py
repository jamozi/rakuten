"""Behavioral checks for the transactional ST-1404 V2 runtime seam."""

from __future__ import annotations

from datetime import timedelta
from typing import cast
from uuid import UUID

from raos.adapters.queue_fake import QueueFake
from raos.domain.ops.durable_job_runtime import (
    DurableDispatchOutcome,
    DurableHandlerOutcome,
    DurableHandlerResult,
    DurableWorkOutcome,
    HandlerEffectIntent,
    HandlerEffectKind,
    QuarantineReleaseApproval,
    QuarantineReplayOutcome,
)
from raos.domain.ops.job_runtime import (
    Fingerprint,
    InboxIdentity,
    InboxState,
    JobState,
    OutboxState,
    RecordedJobMessage,
    RuntimeFailureCode,
)

from conftest import (
    CONSUMER_NAME,
    EVENT_ID,
    HANDLER_VERSION,
    JOB_ID,
    NOW,
    QUEUE_NAME,
    RESULT_FINGERPRINT,
    durable_context,
    durable_result,
    durable_service,
    durable_store,
)


def test_success_commits_job_attempt_inbox_and_effect_before_ack() -> None:
    effect_id = UUID("00000000-0000-0000-0000-000000004404")
    handler_result = DurableHandlerResult(
        outcome=DurableHandlerOutcome.SUCCEEDED,
        completed_at=NOW,
        result_fingerprint=RESULT_FINGERPRINT,
        effects=(
            HandlerEffectIntent(
                effect_id=effect_id,
                kind=HandlerEffectKind.DOMAIN_EVENT,
                fingerprint=Fingerprint("c" * 64),
            ),
        ),
    )
    store = durable_store()
    service, queue_port, handler = durable_service(
        store=store,
        handler_results=(handler_result,),
    )
    queue = cast(QueueFake[RecordedJobMessage], queue_port)

    dispatched = service.dispatch_once(context=durable_context(), now=NOW)
    worked = service.work_once(
        QUEUE_NAME,
        context=durable_context(suffix=1),
        now=NOW,
    )

    assert dispatched.outcome is DurableDispatchOutcome.PUBLISHED
    assert worked.outcome is DurableWorkOutcome.SUCCEEDED
    assert store.outbox(EVENT_ID).state is OutboxState.PUBLISHED
    assert store.job(JOB_ID).state is JobState.SUCCEEDED
    attempts = store.attempts_for(JOB_ID)
    assert len(attempts) == 1
    assert attempts[0].result_fingerprint == RESULT_FINGERPRINT
    identity = InboxIdentity(CONSUMER_NAME, HANDLER_VERSION, EVENT_ID)
    inbox = store.inbox(identity)
    assert inbox is not None and inbox.state is InboxState.PROCESSED
    assert tuple(effect.effect_id for effect in store.effects_for(JOB_ID)) == (
        effect_id,
    )
    assert len(handler.invocations()) == 1
    assert queue.inflight_count(QUEUE_NAME) == 0


def test_duplicate_broker_occurrences_are_acknowledged_without_handler_reexecution() -> (
    None
):
    store = durable_store()
    service, queue_port, handler = durable_service(store=store)
    queue = cast(QueueFake[RecordedJobMessage], queue_port)
    assert (
        service.dispatch_once(context=durable_context(), now=NOW).outcome
        is DurableDispatchOutcome.PUBLISHED
    )
    queue.inject_duplicate(str(EVENT_ID), copies=2)

    outcomes = tuple(
        service.work_once(
            QUEUE_NAME,
            context=durable_context(suffix=index + 1),
            now=NOW,
        ).outcome
        for index in range(3)
    )

    assert outcomes == (
        DurableWorkOutcome.SUCCEEDED,
        DurableWorkOutcome.DUPLICATE_ACKNOWLEDGED,
        DurableWorkOutcome.DUPLICATE_ACKNOWLEDGED,
    )
    assert len(handler.invocations()) == 1
    assert len(store.attempts_for(JOB_ID)) == 1
    assert queue.pending_message_ids(QUEUE_NAME) == ()


def test_retry_backoff_is_exact_and_attempt_history_is_append_only() -> None:
    store = durable_store()
    service, queue_port, handler = durable_service(
        store=store,
        handler_results=(
            durable_result(DurableHandlerOutcome.RETRYABLE_FAILURE),
            durable_result(
                completed_at=NOW + timedelta(seconds=5),
            ),
        ),
        job_retry_schedule=(timedelta(seconds=5),),
    )
    queue = cast(QueueFake[RecordedJobMessage], queue_port)
    service.dispatch_once(context=durable_context(), now=NOW)

    first = service.work_once(
        QUEUE_NAME,
        context=durable_context(suffix=1),
        now=NOW,
    )
    before_due = service.work_once(
        QUEUE_NAME,
        context=durable_context(suffix=2),
        now=NOW,
    )
    queue.advance(timedelta(seconds=5))
    second = service.work_once(
        QUEUE_NAME,
        context=durable_context(NOW + timedelta(seconds=5), suffix=3),
        now=NOW + timedelta(seconds=5),
    )

    assert first.outcome is DurableWorkOutcome.RETRY_SCHEDULED
    assert before_due.outcome is DurableWorkOutcome.NO_DELIVERY
    assert second.outcome is DurableWorkOutcome.SUCCEEDED
    attempts = store.attempts_for(JOB_ID)
    assert tuple(item.attempt_number for item in attempts) == (1, 2)
    assert attempts[0].retry_after_at == NOW + timedelta(seconds=5)
    assert attempts[1].result_fingerprint == RESULT_FINGERPRINT
    assert len(handler.invocations()) == 2


def test_exhausted_retry_schedule_transitions_to_terminal_and_dead_letter() -> None:
    store = durable_store()
    service, _queue, _handler = durable_service(
        store=store,
        handler_results=(durable_result(DurableHandlerOutcome.RETRYABLE_FAILURE),),
        job_retry_schedule=(),
    )
    service.dispatch_once(context=durable_context(), now=NOW)

    result = service.work_once(
        QUEUE_NAME,
        context=durable_context(suffix=1),
        now=NOW,
    )

    assert result.outcome is DurableWorkOutcome.FAILED_TERMINAL
    assert result.failure_code is RuntimeFailureCode.RETRY_BUDGET_EXHAUSTED
    assert store.job(JOB_ID).state is JobState.FAILED_TERMINAL
    letters = store.dead_letters()
    assert len(letters) == 1
    assert letters[0].failure_code is RuntimeFailureCode.RETRY_BUDGET_EXHAUSTED


def test_quarantine_requires_hash_only_approval_and_two_phase_replay() -> None:
    store = durable_store()
    service, queue_port, handler = durable_service(
        store=store,
        handler_results=(
            durable_result(
                DurableHandlerOutcome.QUARANTINE,
                failure_code=RuntimeFailureCode.HANDLER_QUARANTINED,
            ),
            durable_result(completed_at=NOW + timedelta(seconds=1)),
        ),
    )
    queue = cast(QueueFake[RecordedJobMessage], queue_port)
    service.dispatch_once(context=durable_context(), now=NOW)
    quarantined = service.work_once(
        QUEUE_NAME,
        context=durable_context(suffix=1),
        now=NOW,
    )
    job = store.job(JOB_ID)
    approval = QuarantineReleaseApproval(
        approval_id=UUID("00000000-0000-0000-0000-000000005404"),
        job_id=JOB_ID,
        expected_job_version=job.version,
        reason_fingerprint=Fingerprint("d" * 64),
        approved_at=NOW,
    )
    queue.advance(timedelta(seconds=1))

    replay = service.release_quarantine_once(
        approval=approval,
        context=durable_context(NOW + timedelta(seconds=1), suffix=2),
        now=NOW + timedelta(seconds=1),
    )
    succeeded = service.work_once(
        QUEUE_NAME,
        context=durable_context(NOW + timedelta(seconds=1), suffix=3),
        now=NOW + timedelta(seconds=1),
    )

    assert quarantined.outcome is DurableWorkOutcome.QUARANTINED
    assert replay.outcome is QuarantineReplayOutcome.PREPARED_AND_SENT
    assert succeeded.outcome is DurableWorkOutcome.SUCCEEDED
    assert store.job(JOB_ID).completed_at == NOW + timedelta(seconds=1)
    assert len(store.dead_letters()) == 1
    releases = store.quarantine_releases()
    assert len(releases) == 1
    assert releases[0].approval == approval
    assert releases[0].finalized_at == NOW + timedelta(seconds=1)
    assert tuple(item.attempt_number for item in store.attempts_for(JOB_ID)) == (1, 2)
    assert len(handler.invocations()) == 2


def test_dispatch_is_deterministic_and_has_no_implicit_loop() -> None:
    store = durable_store()
    service, queue_port, _handler = durable_service(store=store)
    queue = cast(QueueFake[RecordedJobMessage], queue_port)

    first = service.dispatch_once(context=durable_context(), now=NOW)
    second = service.dispatch_once(context=durable_context(suffix=1), now=NOW)

    assert first.outcome is DurableDispatchOutcome.PUBLISHED
    assert second.outcome is DurableDispatchOutcome.NO_WORK
    assert queue.pending_message_ids(QUEUE_NAME) == (str(EVENT_ID),)
