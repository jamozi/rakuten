"""Hostile CAS, codec, idempotency, lease-fence, and crash cases for V2."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json

import pytest

from .support import NOW, command_and_controls
from raos.adapters.recorded_durable_ai_job_queue_v2 import (
    RecordedDurableAiJobStateAdapterV2,
)
from raos.application.ai.durable_job_queue_v2 import (
    RecordedDurableAiJobQueueServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.durable_job_queue_v2 import (
    DurableJobRecord,
    DurableJobStatus,
    DurableOutboxIntent,
    DurableQueueFailure,
    DurableQueueFailureCode,
    DurableQueueSnapshot,
    DurableQueueState,
    MAXIMUM_STATE_BYTES,
    RecordedAttemptKind,
    RecordedAttemptOutcome,
    RecordedDurableQueueActivation,
    decode_durable_queue_state,
    encode_durable_queue_state,
)
from raos.domain.ai.job_orchestration import AiJobEventType, ProviderFailureClass


QUEUE_ID = "queue.st0706.negative.v2"


def _service(
    adapter: RecordedDurableAiJobStateAdapterV2,
) -> RecordedDurableAiJobQueueServiceV2:
    return RecordedDurableAiJobQueueServiceV2(
        activation=RecordedDurableQueueActivation(
            environment=RuntimeEnvironment.ENV_DEV, enabled=True
        ),
        state=adapter,
    )


def _failure(ai_job_id: object, *, request_id: str) -> RecordedAttemptOutcome:
    from uuid import UUID

    assert type(ai_job_id) is UUID
    return RecordedAttemptOutcome(
        kind=RecordedAttemptKind.PROVIDER_FAILURE,
        ai_job_id=ai_job_id,
        attempt_number=1,
        provider_request_id=request_id,
        actual_cost_jpy=2,
        provider_failure_class=ProviderFailureClass.TRANSIENT_ERROR,
        retryable=True,
    )


def test_same_idempotency_key_with_different_fingerprint_fails_closed() -> None:
    command, _ = command_and_controls()
    conflicting, _ = command_and_controls(operation_id="operation.st0706.conflict.v2")
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    before = adapter.export_snapshot()

    with pytest.raises(DurableQueueFailure) as captured:
        service.enqueue(queue_id=QUEUE_ID, command=conflicting, enqueued_at=NOW)
    assert captured.value.code is DurableQueueFailureCode.IDEMPOTENCY_MISMATCH
    assert adapter.export_snapshot().state_bytes == before.state_bytes


def test_ai_and_ops_identity_conflicts_are_separately_rejected() -> None:
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)

    ai_conflict = replace(command, idempotency_key="idempotency.ai-conflict.v2")
    with pytest.raises(DurableQueueFailure) as ai_failure:
        service.enqueue(queue_id=QUEUE_ID, command=ai_conflict, enqueued_at=NOW)
    assert ai_failure.value.code is DurableQueueFailureCode.AI_JOB_ID_CONFLICT

    from uuid import UUID

    ops_conflict = replace(
        command,
        idempotency_key="idempotency.ops-conflict.v2",
        ai_job_id=UUID("00000000-0000-4000-8000-000000000799"),
    )
    with pytest.raises(DurableQueueFailure) as ops_failure:
        service.enqueue(queue_id=QUEUE_ID, command=ops_conflict, enqueued_at=NOW)
    assert ops_failure.value.code is DurableQueueFailureCode.OPS_JOB_ID_CONFLICT


def test_queue_capacity_is_exact_and_the_33rd_job_does_not_mutate_state() -> None:
    from uuid import UUID

    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    for index in range(32):
        command, _ = command_and_controls(
            operation_id=f"operation.capacity.st0706.v2.{index}",
            ai_job_id=UUID(f"00000000-0000-4000-8000-{index + 1:012d}"),
            ops_job_id=UUID(f"00000000-0000-4000-9000-{index + 1:012d}"),
        )
        command = replace(
            command, idempotency_key=f"idempotency.capacity.st0706.v2.{index}"
        )
        service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    full = adapter.export_snapshot()

    overflow, _ = command_and_controls(
        operation_id="operation.capacity.st0706.v2.overflow",
        ai_job_id=UUID("00000000-0000-4000-8000-000000000999"),
        ops_job_id=UUID("00000000-0000-4000-9000-000000000999"),
    )
    overflow = replace(
        overflow, idempotency_key="idempotency.capacity.st0706.v2.overflow"
    )
    with pytest.raises(DurableQueueFailure) as captured:
        service.enqueue(queue_id=QUEUE_ID, command=overflow, enqueued_at=NOW)
    assert captured.value.code is DurableQueueFailureCode.CAPACITY_EXCEEDED
    assert adapter.export_snapshot().revision == full.revision == 32
    assert adapter.export_snapshot().state_bytes == full.state_bytes


def test_outbox_capacity_rejects_the_129th_recorded_intent() -> None:
    command, _ = command_and_controls()
    job = DurableJobRecord(
        command=command,
        status=DurableJobStatus.READY,
        attempt_number=1,
        accumulated_cost_jpy=0,
        available_at=NOW,
    )
    intents = tuple(
        DurableOutboxIntent.create(
            event_type=AiJobEventType.REQUESTED,
            command=command,
            attempt_number=1,
            status=DurableJobStatus.READY,
            occurred_at=NOW + timedelta(seconds=index),
        )
        for index in range(129)
    )
    with pytest.raises(DurableQueueFailure) as captured:
        DurableQueueState(
            queue_id=QUEUE_ID, revision=0, jobs=(job,), outbox_intents=intents
        )
    assert captured.value.code is DurableQueueFailureCode.OUTBOX_CAPACITY_EXCEEDED


def test_stale_revision_and_hash_cannot_replace_newer_state() -> None:
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    stale = adapter.export_snapshot()
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)

    stale_replacement = encode_durable_queue_state(
        DurableQueueState(queue_id=QUEUE_ID, revision=1)
    )
    with pytest.raises(DurableQueueFailure) as revision_failure:
        adapter.compare_and_swap(
            queue_id=QUEUE_ID,
            expected_revision=stale.revision,
            expected_state_sha256=stale.state_sha256,
            replacement_state_bytes=stale_replacement,
        )
    assert revision_failure.value.code is DurableQueueFailureCode.CAS_CONFLICT

    current = adapter.export_snapshot()
    replacement = encode_durable_queue_state(
        DurableQueueState(queue_id=QUEUE_ID, revision=current.revision + 1)
    )
    with pytest.raises(DurableQueueFailure) as hash_failure:
        adapter.compare_and_swap(
            queue_id=QUEUE_ID,
            expected_revision=current.revision,
            expected_state_sha256="0" * 64,
            replacement_state_bytes=replacement,
        )
    assert hash_failure.value.code is DurableQueueFailureCode.CAS_CONFLICT


def test_commit_then_crash_reloads_and_idempotently_replays_without_a_new_intent() -> (
    None
):
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    adapter.arm_commit_uncertain_once()
    with pytest.raises(DurableQueueFailure) as uncertain:
        service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    assert uncertain.value.code is DurableQueueFailureCode.COMMIT_UNCERTAIN

    committed = adapter.export_snapshot()
    assert committed.revision == 1
    restarted_adapter = RecordedDurableAiJobStateAdapterV2.from_snapshot(
        snapshot=committed
    )
    replay = _service(restarted_adapter).enqueue(
        queue_id=QUEUE_ID,
        command=command,
        enqueued_at=NOW + timedelta(seconds=1),
    )
    assert replay.replayed is True
    assert restarted_adapter.export_snapshot().state_bytes == committed.state_bytes


def test_stale_token_epoch_worker_and_expired_lease_are_rejected_without_write() -> (
    None
):
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    claim = service.claim(
        queue_id=QUEUE_ID,
        worker_id="worker.st0706.v2",
        lease_nonce_sha256="1" * 64,
        now=NOW + timedelta(seconds=1),
    )
    before = adapter.export_snapshot()
    outcome = _failure(command.ai_job_id, request_id="request.stale.st0706.v2")
    hostile_claims = (
        replace(claim, lease_token_sha256="2" * 64),
        replace(claim, lease_epoch=claim.lease_epoch + 1),
        replace(claim, worker_id="worker.attacker.st0706.v2"),
    )
    for hostile in hostile_claims:
        with pytest.raises(DurableQueueFailure) as captured:
            service.complete(
                claim=hostile,
                outcome=outcome,
                now=NOW + timedelta(seconds=2),
            )
        assert captured.value.code is DurableQueueFailureCode.LEASE_MISMATCH
        assert adapter.export_snapshot().state_bytes == before.state_bytes

    with pytest.raises(DurableQueueFailure) as expired:
        service.complete(
            claim=claim,
            outcome=outcome,
            now=NOW + timedelta(seconds=31),
        )
    assert expired.value.code is DurableQueueFailureCode.LEASE_MISMATCH
    assert adapter.export_snapshot().state_bytes == before.state_bytes


def test_same_lease_with_a_different_outcome_cannot_replace_its_receipt() -> None:
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    claim = service.claim(
        queue_id=QUEUE_ID,
        worker_id="worker.st0706.v2",
        lease_nonce_sha256="1" * 64,
        now=NOW + timedelta(seconds=1),
    )
    first = _failure(command.ai_job_id, request_id="request.first.st0706.v2")
    service.complete(claim=claim, outcome=first, now=NOW + timedelta(seconds=2))
    before = adapter.export_snapshot()
    different = _failure(command.ai_job_id, request_id="request.other.st0706.v2")
    with pytest.raises(DurableQueueFailure) as captured:
        service.complete(claim=claim, outcome=different, now=NOW + timedelta(seconds=3))
    assert captured.value.code is DurableQueueFailureCode.COMPLETION_MISMATCH
    assert adapter.export_snapshot().state_bytes == before.state_bytes

    wrong_worker = replace(claim, worker_id="worker.wrong.st0706.v2")
    with pytest.raises(DurableQueueFailure) as fenced:
        service.complete(
            claim=wrong_worker, outcome=first, now=NOW + timedelta(seconds=3)
        )
    assert fenced.value.code is DurableQueueFailureCode.LEASE_MISMATCH
    assert adapter.export_snapshot().state_bytes == before.state_bytes


def test_completion_commit_uncertainty_rehydrates_and_replays_exact_result() -> None:
    from .support import OUTPUT_ARTIFACT_ID
    from raos.domain.ai.job_orchestration import ValidationStatus

    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    claim = service.claim(
        queue_id=QUEUE_ID,
        worker_id="worker.st0706.v2",
        lease_nonce_sha256="1" * 64,
        now=NOW + timedelta(seconds=1),
    )
    outcome = RecordedAttemptOutcome(
        kind=RecordedAttemptKind.SUCCEEDED,
        ai_job_id=command.ai_job_id,
        attempt_number=1,
        provider_request_id="request.crash.st0706.v2",
        actual_cost_jpy=0,
        validation_status=ValidationStatus.PASS,
        output_artifact_id=OUTPUT_ARTIFACT_ID,
        output_artifact_sha256="6" * 64,
    )
    adapter.arm_commit_uncertain_once()
    with pytest.raises(DurableQueueFailure) as uncertain:
        service.complete(claim=claim, outcome=outcome, now=NOW + timedelta(seconds=2))
    assert uncertain.value.code is DurableQueueFailureCode.COMMIT_UNCERTAIN

    exported = adapter.export_snapshot()
    assert b"request.crash.st0706.v2" not in exported.state_bytes
    hostile_data = json.loads(exported.state_bytes)
    hostile_data["jobs"][0]["completion_receipts"][0]["claim_sha256"] = "0" * 64
    hostile_bytes = (
        json.dumps(hostile_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    with pytest.raises(DurableQueueFailure) as hostile_receipt:
        decode_durable_queue_state(
            hostile_bytes,
            expected_queue_id=QUEUE_ID,
            expected_revision=exported.revision,
        )
    assert hostile_receipt.value.code is DurableQueueFailureCode.STATE_INVALID

    restarted = RecordedDurableAiJobStateAdapterV2.from_snapshot(snapshot=exported)
    replay = _service(restarted).complete(
        claim=claim, outcome=outcome, now=NOW + timedelta(seconds=3)
    )
    assert replay.replayed is True
    assert replay.status.value == "SUCCEEDED"
    assert replay.accumulated_cost_jpy == 0
    assert restarted.export_snapshot().state_bytes == exported.state_bytes
    assert restarted.export_snapshot().revision == exported.revision


@pytest.mark.parametrize(
    "mutator",
    (
        lambda data: {**data, "unknown": True},
        lambda data: {**data, "schema_version": 1},
        lambda data: {**data, "policy_id": "wrong.policy"},
        lambda data: {**data, "policy_sha256": "0" * 64},
        lambda data: {**data, "revision": 99},
        lambda data: {**data, "queue_id": "queue.other.v2"},
    ),
)
def test_state_codec_rejects_unknown_or_unbound_root_material(mutator: object) -> None:
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    snapshot = adapter.export_snapshot()
    data = json.loads(snapshot.state_bytes)
    assert callable(mutator)
    hostile = (
        json.dumps(mutator(data), sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    with pytest.raises(DurableQueueFailure) as captured:
        decode_durable_queue_state(
            hostile, expected_queue_id=QUEUE_ID, expected_revision=0
        )
    assert captured.value.code is DurableQueueFailureCode.STATE_INVALID


def test_state_codec_rejects_noncanonical_duplicate_trailing_and_oversized_bytes() -> (
    None
):
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    snapshot = adapter.export_snapshot()
    hostile_values = (
        snapshot.state_bytes[:-1],
        b" " + snapshot.state_bytes,
        snapshot.state_bytes + b"{}",
        b'{"schema_version":2,"schema_version":2}\n',
        b"x" * (MAXIMUM_STATE_BYTES + 1),
    )
    for hostile in hostile_values:
        with pytest.raises(DurableQueueFailure) as captured:
            decode_durable_queue_state(
                hostile, expected_queue_id=QUEUE_ID, expected_revision=0
            )
        assert captured.value.code is DurableQueueFailureCode.STATE_INVALID


@pytest.mark.parametrize(
    "mutation",
    (
        "command_unknown_field",
        "command_fingerprint",
        "outbox_metadata_hash",
        "duplicate_job",
        "orphan_outbox",
    ),
)
def test_state_codec_rejects_hostile_nested_binding_drift(mutation: str) -> None:
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    _service(adapter).enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    snapshot = adapter.export_snapshot()
    data = json.loads(snapshot.state_bytes)
    if mutation == "command_unknown_field":
        data["jobs"][0]["command"]["prompt"] = "forbidden"
    elif mutation == "command_fingerprint":
        data["jobs"][0]["command"]["fingerprint_sha256"] = "0" * 64
    elif mutation == "outbox_metadata_hash":
        data["outbox_intents"][0]["metadata_sha256"] = "0" * 64
    elif mutation == "duplicate_job":
        data["jobs"].append(data["jobs"][0])
    else:
        data["jobs"] = []
    hostile = (
        json.dumps(
            data,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    with pytest.raises(DurableQueueFailure) as captured:
        decode_durable_queue_state(
            hostile,
            expected_queue_id=QUEUE_ID,
            expected_revision=snapshot.revision,
        )
    assert captured.value.code is DurableQueueFailureCode.STATE_INVALID


def test_rehydrate_rejects_mismatched_revision_even_with_valid_snapshot_shape() -> None:
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    exported = adapter.export_snapshot()
    tampered = DurableQueueSnapshot(
        queue_id=QUEUE_ID,
        revision=1,
        state_bytes=exported.state_bytes,
    )
    with pytest.raises(DurableQueueFailure) as captured:
        RecordedDurableAiJobStateAdapterV2.from_snapshot(snapshot=tampered)
    assert captured.value.code is DurableQueueFailureCode.STATE_INVALID


def test_invalid_lease_nonce_is_rejected_before_state_mutation() -> None:
    command, _ = command_and_controls()
    adapter = RecordedDurableAiJobStateAdapterV2(queue_id=QUEUE_ID)
    service = _service(adapter)
    service.enqueue(queue_id=QUEUE_ID, command=command, enqueued_at=NOW)
    before = adapter.export_snapshot()
    for nonce in ("A" * 64, "0" * 63, "0" * 65, "🔐" * 64):
        with pytest.raises(DurableQueueFailure) as captured:
            service.claim(
                queue_id=QUEUE_ID,
                worker_id="worker.st0706.v2",
                lease_nonce_sha256=nonce,
                now=NOW + timedelta(seconds=1),
            )
        assert captured.value.code is DurableQueueFailureCode.INVALID_REQUEST
        assert adapter.export_snapshot().state_bytes == before.state_bytes
