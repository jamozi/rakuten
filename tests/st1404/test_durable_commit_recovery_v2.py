"""Crash ambiguity, restart, lease fencing, and recovery checks for ST-1404."""

from __future__ import annotations

from datetime import timedelta
from typing import cast
from uuid import UUID

import pytest

from raos.adapters.queue_fake import QueueFake
from raos.adapters.recorded_durable_job_runtime import (
    RecordedDurableJobRuntimeStore,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.durable_job_runtime import (
    CommitFault,
    DurableDispatchOutcome,
    DurableHandlerOutcome,
    DurableWorkOutcome,
    QuarantineReleaseApproval,
    QuarantineReplayOutcome,
    RecoveryKind,
)
from raos.domain.ops.job_runtime import (
    Fingerprint,
    JobRuntimeFailure,
    JobState,
    OutboxState,
    RecordedJobMessage,
    RuntimeFailureCode,
)

from conftest import (
    EVENT_ID,
    IDENTITY_NAMESPACE,
    JOB_ID,
    NOW,
    QUEUE_NAME,
    durable_context,
    durable_result,
    durable_service,
    durable_store,
)


@pytest.mark.parametrize(
    ("fault", "outcome"),
    (
        (
            CommitFault.KNOWN_BEFORE_COMMIT,
            DurableDispatchOutcome.CLAIM_COMMIT_KNOWN_ROLLBACK,
        ),
        (
            CommitFault.UNKNOWN_BEFORE_COMMIT,
            DurableDispatchOutcome.CLAIM_COMMIT_UNKNOWN,
        ),
        (
            CommitFault.UNKNOWN_AFTER_COMMIT,
            DurableDispatchOutcome.CLAIM_COMMIT_UNKNOWN,
        ),
    ),
)
def test_dispatch_claim_commit_ambiguity_never_sends_before_durable_claim(
    fault: CommitFault,
    outcome: DurableDispatchOutcome,
) -> None:
    store = durable_store(commit_faults=(fault,))
    service, queue_port, _handler = durable_service(store=store)
    queue = cast(QueueFake[RecordedJobMessage], queue_port)

    result = service.dispatch_once(context=durable_context(), now=NOW)

    assert result.outcome is outcome
    assert queue.pending_message_ids(QUEUE_NAME) == ()
    expected = (
        OutboxState.DISPATCHING
        if fault is CommitFault.UNKNOWN_AFTER_COMMIT
        else OutboxState.PENDING
    )
    assert store.outbox(EVENT_ID).state is expected
    assert store.job(JOB_ID).state is JobState.REQUESTED


def test_unknown_after_outbox_claim_survives_restart_and_is_fenced_on_takeover() -> (
    None
):
    store = durable_store(commit_faults=(CommitFault.UNKNOWN_AFTER_COMMIT,))
    service, queue_port, _handler = durable_service(
        store=store,
        job_retry_schedule=(timedelta(0),),
    )
    queue = cast(QueueFake[RecordedJobMessage], queue_port)
    result = service.dispatch_once(context=durable_context(), now=NOW)
    assert result.outcome is DurableDispatchOutcome.CLAIM_COMMIT_UNKNOWN
    before = store.snapshot()
    first_lease = before.outbox_leases[0]
    restarted = RecordedDurableJobRuntimeStore.from_snapshot(
        environment=RuntimeEnvironment.ENV_DEV,
        identity_namespace=IDENTITY_NAMESPACE,
        snapshot=before,
    )
    restarted_service, restarted_queue_port, _ = durable_service(
        store=restarted,
        queue=queue,
        outbox_retry_schedule=(timedelta(0),),
    )
    restarted_queue = cast(QueueFake[RecordedJobMessage], restarted_queue_port)
    recovery_at = NOW + timedelta(seconds=20)

    recovered = restarted_service.recover_once(
        context=durable_context(recovery_at, suffix=1),
        now=recovery_at,
    )
    dispatched = restarted_service.dispatch_once(
        context=durable_context(recovery_at, suffix=2),
        now=recovery_at,
    )

    assert recovered.kind is RecoveryKind.OUTBOX_RETRY_SCHEDULED
    assert dispatched.outcome is DurableDispatchOutcome.PUBLISHED
    after = restarted.snapshot()
    assert after.fence_counter > first_lease.fence
    assert after.outbox_leases == ()
    assert restarted_queue.pending_message_ids(QUEUE_NAME) == (str(EVENT_ID),)


def test_unknown_after_publish_commit_may_duplicate_but_does_not_regress_state() -> (
    None
):
    store = durable_store(
        commit_faults=(CommitFault.NONE, CommitFault.UNKNOWN_AFTER_COMMIT)
    )
    service, queue_port, handler = durable_service(store=store)
    queue = cast(QueueFake[RecordedJobMessage], queue_port)

    dispatch = service.dispatch_once(context=durable_context(), now=NOW)

    assert dispatch.outcome is DurableDispatchOutcome.FINALIZE_COMMIT_UNKNOWN
    assert store.outbox(EVENT_ID).state is OutboxState.PUBLISHED
    assert store.job(JOB_ID).state is JobState.QUEUED
    assert queue.pending_message_ids(QUEUE_NAME) == (str(EVENT_ID),)
    assert (
        service.dispatch_once(context=durable_context(suffix=1), now=NOW).outcome
        is DurableDispatchOutcome.NO_WORK
    )
    assert (
        service.work_once(
            QUEUE_NAME,
            context=durable_context(suffix=2),
            now=NOW,
        ).outcome
        is DurableWorkOutcome.SUCCEEDED
    )
    assert len(handler.invocations()) == 1


def test_unknown_after_work_claim_is_recovered_without_invoking_handler() -> None:
    store = durable_store(
        commit_faults=(
            CommitFault.NONE,
            CommitFault.NONE,
            CommitFault.UNKNOWN_AFTER_COMMIT,
        )
    )
    service, queue_port, handler = durable_service(
        store=store,
        handler_results=(durable_result(completed_at=NOW + timedelta(seconds=30)),),
        job_retry_schedule=(timedelta(0),),
    )
    queue = cast(QueueFake[RecordedJobMessage], queue_port)
    service.dispatch_once(context=durable_context(), now=NOW)

    ambiguous = service.work_once(
        QUEUE_NAME,
        context=durable_context(suffix=1),
        now=NOW,
    )

    assert ambiguous.outcome is DurableWorkOutcome.CLAIM_COMMIT_UNKNOWN
    assert store.job(JOB_ID).state is JobState.RUNNING
    assert len(handler.invocations()) == 0
    queue.advance(timedelta(seconds=30))
    recovery_at = NOW + timedelta(seconds=30)
    recovered = service.recover_once(
        context=durable_context(recovery_at, suffix=2),
        now=recovery_at,
    )
    retried = service.work_once(
        QUEUE_NAME,
        context=durable_context(recovery_at, suffix=3),
        now=recovery_at,
    )

    assert recovered.kind is RecoveryKind.WORK_RETRY_SCHEDULED
    assert retried.outcome is DurableWorkOutcome.SUCCEEDED
    assert len(handler.invocations()) == 1
    assert tuple(item.attempt_number for item in store.attempts_for(JOB_ID)) == (1, 2)


@pytest.mark.parametrize(
    ("completion_fault", "outcome", "committed"),
    (
        (
            CommitFault.KNOWN_BEFORE_COMMIT,
            DurableWorkOutcome.COMPLETE_COMMIT_KNOWN_ROLLBACK,
            False,
        ),
        (
            CommitFault.UNKNOWN_BEFORE_COMMIT,
            DurableWorkOutcome.COMPLETE_COMMIT_UNKNOWN,
            False,
        ),
        (
            CommitFault.UNKNOWN_AFTER_COMMIT,
            DurableWorkOutcome.COMPLETE_COMMIT_UNKNOWN,
            True,
        ),
    ),
)
def test_worker_completion_commit_ambiguity_is_resolved_by_durable_inbox(
    completion_fault: CommitFault,
    outcome: DurableWorkOutcome,
    committed: bool,
) -> None:
    store = durable_store(
        commit_faults=(
            CommitFault.NONE,
            CommitFault.NONE,
            CommitFault.NONE,
            completion_fault,
        )
    )
    service, queue_port, handler = durable_service(
        store=store,
        handler_results=(
            durable_result(),
            durable_result(completed_at=NOW + timedelta(seconds=30)),
        ),
        job_retry_schedule=(timedelta(0),),
    )
    queue = cast(QueueFake[RecordedJobMessage], queue_port)
    service.dispatch_once(context=durable_context(), now=NOW)

    ambiguous = service.work_once(
        QUEUE_NAME,
        context=durable_context(suffix=1),
        now=NOW,
    )

    assert ambiguous.outcome is outcome
    assert store.job(JOB_ID).state is (
        JobState.SUCCEEDED if committed else JobState.RUNNING
    )
    assert len(handler.invocations()) == 1
    queue.advance(timedelta(seconds=30))
    at = NOW + timedelta(seconds=30)
    if committed:
        duplicate = service.work_once(
            QUEUE_NAME,
            context=durable_context(at, suffix=2),
            now=at,
        )
        assert duplicate.outcome is DurableWorkOutcome.DUPLICATE_ACKNOWLEDGED
        assert len(handler.invocations()) == 1
    else:
        recovered = service.recover_once(
            context=durable_context(at, suffix=2),
            now=at,
        )
        assert recovered.kind is RecoveryKind.WORK_RETRY_SCHEDULED
        retried = service.work_once(
            QUEUE_NAME,
            context=durable_context(at, suffix=3),
            now=at,
        )
        assert retried.outcome is DurableWorkOutcome.SUCCEEDED
        assert len(handler.invocations()) == 2


def test_two_open_uows_use_compare_and_swap_and_reject_lost_update() -> None:
    store = durable_store()
    first = store.begin(durable_context())
    second = store.begin(durable_context(suffix=1))
    with first as first_uow, second as second_uow:
        first_claim = first_uow.repository.claim_due_outbox(
            now=NOW,
            owner="worker-a",
            leased_until=NOW + timedelta(seconds=20),
        )
        second_claim = second_uow.repository.claim_due_outbox(
            now=NOW,
            owner="worker-b",
            leased_until=NOW + timedelta(seconds=20),
        )
        assert first_claim is not None and second_claim is not None
        first_uow.commit()
        with pytest.raises(JobRuntimeFailure) as captured:
            second_uow.commit()
    assert captured.value.code is RuntimeFailureCode.CONCURRENCY_CONFLICT
    snapshot = store.snapshot()
    assert snapshot.revision == 1
    assert snapshot.outbox_leases[0].owner == "worker-a"


def test_clean_uow_exit_rolls_back_and_closed_repository_is_inaccessible() -> None:
    store = durable_store()
    uow = store.begin(durable_context())
    with uow:
        claim = uow.repository.claim_due_outbox(
            now=NOW,
            owner="worker-a",
            leased_until=NOW + timedelta(seconds=20),
        )
        assert claim is not None
    assert store.outbox(EVENT_ID).state is OutboxState.PENDING
    with pytest.raises(JobRuntimeFailure) as captured:
        _ = uow.repository
    assert captured.value.code is RuntimeFailureCode.STATE_CONFLICT


def _quarantine_approval(
    store: RecordedDurableJobRuntimeStore,
) -> QuarantineReleaseApproval:
    return QuarantineReleaseApproval(
        approval_id=UUID("00000000-0000-0000-0000-000000006404"),
        job_id=JOB_ID,
        expected_job_version=store.job(JOB_ID).version,
        reason_fingerprint=Fingerprint("e" * 64),
        approved_at=NOW,
    )


def test_unknown_after_quarantine_prepare_is_restartable_before_queue_send() -> None:
    store = durable_store(
        commit_faults=(
            CommitFault.NONE,
            CommitFault.NONE,
            CommitFault.NONE,
            CommitFault.NONE,
            CommitFault.UNKNOWN_AFTER_COMMIT,
        )
    )
    service, queue_port, _handler = durable_service(
        store=store,
        handler_results=(
            durable_result(
                DurableHandlerOutcome.QUARANTINE,
                failure_code=RuntimeFailureCode.HANDLER_QUARANTINED,
            ),
        ),
    )
    queue = cast(QueueFake[RecordedJobMessage], queue_port)
    service.dispatch_once(context=durable_context(), now=NOW)
    service.work_once(QUEUE_NAME, context=durable_context(suffix=1), now=NOW)
    approval = _quarantine_approval(store)
    queue.advance(timedelta(seconds=1))
    at = NOW + timedelta(seconds=1)

    ambiguous = service.release_quarantine_once(
        approval=approval,
        context=durable_context(at, suffix=2),
        now=at,
    )
    retried = service.release_quarantine_once(
        approval=approval,
        context=durable_context(at, suffix=3),
        now=at,
    )

    assert ambiguous.outcome is QuarantineReplayOutcome.PREPARE_COMMIT_UNKNOWN
    assert retried.outcome is QuarantineReplayOutcome.PREPARED_AND_SENT
    assert store.job(JOB_ID).state is JobState.QUEUED
    assert queue.pending_message_ids(QUEUE_NAME) == (str(EVENT_ID),)


@pytest.mark.parametrize(
    ("fault", "state_after_ambiguity"),
    (
        (CommitFault.UNKNOWN_BEFORE_COMMIT, JobState.QUARANTINED),
        (CommitFault.UNKNOWN_AFTER_COMMIT, JobState.QUEUED),
    ),
)
def test_quarantine_finalize_unknown_commit_is_resolved_from_durable_state(
    fault: CommitFault,
    state_after_ambiguity: JobState,
) -> None:
    store = durable_store(
        commit_faults=(
            CommitFault.NONE,
            CommitFault.NONE,
            CommitFault.NONE,
            CommitFault.NONE,
            CommitFault.NONE,
            fault,
        )
    )
    service, queue_port, _handler = durable_service(
        store=store,
        handler_results=(
            durable_result(
                DurableHandlerOutcome.QUARANTINE,
                failure_code=RuntimeFailureCode.HANDLER_QUARANTINED,
            ),
        ),
    )
    queue = cast(QueueFake[RecordedJobMessage], queue_port)
    service.dispatch_once(context=durable_context(), now=NOW)
    service.work_once(QUEUE_NAME, context=durable_context(suffix=1), now=NOW)
    approval = _quarantine_approval(store)
    queue.advance(timedelta(seconds=1))
    at = NOW + timedelta(seconds=1)

    ambiguous = service.release_quarantine_once(
        approval=approval,
        context=durable_context(at, suffix=2),
        now=at,
    )

    assert ambiguous.outcome is QuarantineReplayOutcome.FINALIZE_COMMIT_UNKNOWN
    assert store.job(JOB_ID).state is state_after_ambiguity
    if state_after_ambiguity is JobState.QUARANTINED:
        resolved = service.release_quarantine_once(
            approval=approval,
            context=durable_context(at, suffix=3),
            now=at,
        )
        assert resolved.outcome is QuarantineReplayOutcome.PREPARED_AND_SENT
        assert store.job(JOB_ID).state is JobState.QUEUED
        assert queue.pending_message_ids(QUEUE_NAME) == (
            str(EVENT_ID),
            str(EVENT_ID),
        )
    else:
        assert queue.pending_message_ids(QUEUE_NAME) == (str(EVENT_ID),)
