"""Deterministic TST-013 behavior for the ST-0203 queue fake."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from raos.adapters.queue_fake import QueueFake
from raos.ports.queue import (
    InvalidQueueMessage,
    QueueMessage,
    StaleReceiptHandle,
    UnknownReceiptHandle,
)


NOW = datetime(2026, 8, 2, 15, 0, tzinfo=timezone.utc)
LEASE = timedelta(seconds=30)


def make_message(
    message_id: str,
    *,
    available_at: datetime = NOW,
    max_attempts: int = 3,
) -> QueueMessage[dict[str, str]]:
    return QueueMessage(
        message_id=message_id,
        queue_name="ingestion",
        idempotency_key=f"idempotency-{message_id}",
        payload={"message_id": message_id, "origin": "synthetic"},
        available_at=available_at,
        max_attempts=max_attempts,
    )


def receive_required(
    queue: QueueFake[dict[str, str]],
):
    delivery = queue.receive("ingestion", lease=LEASE)
    assert delivery is not None
    return delivery


def test_default_delivery_is_fifo_and_acknowledgement_is_final() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    for message_id in ("first", "second", "third"):
        queue.send(make_message(message_id))

    observed = []
    for _ in range(3):
        delivery = receive_required(queue)
        observed.append(delivery.message.message_id)
        queue.acknowledge(delivery.receipt_handle)

    assert observed == ["first", "second", "third"]
    assert queue.receive("ingestion", lease=LEASE) is None
    assert queue.inflight_count("ingestion") == 0


def test_delayed_message_is_invisible_until_virtual_time_advances() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("delayed", available_at=NOW + timedelta(minutes=5)))

    assert queue.receive("ingestion", lease=LEASE) is None
    queue.advance(timedelta(minutes=4, seconds=59))
    assert queue.receive("ingestion", lease=LEASE) is None
    queue.advance(timedelta(seconds=1))
    assert receive_required(queue).message.message_id == "delayed"


def test_duplicate_injection_preserves_logical_and_idempotency_identity() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    original = make_message("same-logical-message")
    queue.send(original)
    queue.inject_duplicate(original.message_id, copies=2)

    deliveries = [receive_required(queue) for _ in range(3)]

    assert [item.message.message_id for item in deliveries] == [
        original.message_id,
        original.message_id,
        original.message_id,
    ]
    assert {item.message.idempotency_key for item in deliveries} == {
        original.idempotency_key
    }
    assert len({item.receipt_handle for item in deliveries}) == 3
    assert queue.inflight_count("ingestion") == 3


def test_explicit_out_of_order_injection_is_exact_and_repeatable() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    for message_id in ("one", "two", "three"):
        queue.send(make_message(message_id))
    queue.inject_out_of_order("ingestion", message_ids=("three", "one", "two"))

    observed = []
    for _ in range(3):
        delivery = receive_required(queue)
        observed.append(delivery.message.message_id)
        queue.acknowledge(delivery.receipt_handle)

    assert observed == ["three", "one", "two"]


def test_explicit_order_wins_after_differently_delayed_messages_are_ready() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("later", available_at=NOW + timedelta(minutes=2)))
    queue.send(make_message("now"))
    queue.advance(timedelta(minutes=2))
    queue.inject_out_of_order("ingestion", message_ids=("later", "now"))

    assert receive_required(queue).message.message_id == "later"
    assert receive_required(queue).message.message_id == "now"


def test_out_of_order_injection_handles_duplicate_occurrences() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("one"))
    queue.send(make_message("two"))
    queue.inject_duplicate("one")
    queue.inject_out_of_order("ingestion", message_ids=("one", "two", "one"))

    assert queue.pending_message_ids("ingestion") == ("one", "two", "one")


def test_lease_expiry_redelivers_with_new_receipt_and_incremented_attempt() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("lease-expiry"))
    first = receive_required(queue)

    queue.advance(LEASE)
    second = receive_required(queue)

    assert second.message == first.message
    assert second.delivery_attempt == 2
    assert second.receipt_handle != first.receipt_handle
    with pytest.raises(StaleReceiptHandle):
        queue.acknowledge(first.receipt_handle)


def test_lease_extension_renews_from_current_virtual_time() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("heartbeat"))
    first = receive_required(queue)
    queue.advance(timedelta(seconds=20))

    renewed = queue.extend_lease(first.receipt_handle, lease=LEASE)
    assert renewed.leased_until == NOW + timedelta(seconds=50)
    queue.advance(timedelta(seconds=29))
    assert queue.inflight_count("ingestion") == 1
    queue.advance(timedelta(seconds=1))
    assert queue.inflight_count("ingestion") == 0
    assert receive_required(queue).delivery_attempt == 2


def test_retry_delay_and_max_attempts_move_occurrence_to_dlq() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("retry", max_attempts=2))
    first = receive_required(queue)
    queue.retry(first.receipt_handle, delay=timedelta(minutes=1))

    assert queue.receive("ingestion", lease=LEASE) is None
    queue.advance(timedelta(minutes=1))
    second = receive_required(queue)
    assert second.delivery_attempt == 2
    queue.retry(second.receipt_handle)

    assert queue.receive("ingestion", lease=LEASE) is None
    assert len(queue.dead_letters("ingestion")) == 1
    dead = queue.dead_letters("ingestion")[0]
    assert dead.message.message_id == "retry"
    assert dead.delivery_attempt == 2
    assert dead.reason == "MAX_ATTEMPTS_EXHAUSTED"


def test_last_attempt_lease_expiry_moves_occurrence_to_dlq() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("poison", max_attempts=1))
    first = receive_required(queue)

    queue.advance(LEASE)

    assert queue.receive("ingestion", lease=LEASE) is None
    assert queue.dead_letters("ingestion")[0].reason == ("LEASE_EXPIRED_MAX_ATTEMPTS")
    with pytest.raises(StaleReceiptHandle):
        queue.retry(first.receipt_handle)


def test_receipt_handles_fail_closed_after_every_terminal_operation() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("ack"))
    delivery = receive_required(queue)
    queue.acknowledge(delivery.receipt_handle)

    with pytest.raises(StaleReceiptHandle):
        queue.acknowledge(delivery.receipt_handle)
    with pytest.raises(UnknownReceiptHandle):
        queue.acknowledge("never-issued-receipt")


def test_receive_overflow_preserves_pending_occurrence() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("receive-overflow"))

    with pytest.raises(InvalidQueueMessage, match="supported datetime range"):
        queue.receive("ingestion", lease=timedelta.max)

    assert queue.pending_message_ids("ingestion") == ("receive-overflow",)
    assert receive_required(queue).delivery_attempt == 1


def test_retry_overflow_preserves_active_receipt() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("retry-overflow"))
    delivery = receive_required(queue)

    with pytest.raises(InvalidQueueMessage, match="supported datetime range"):
        queue.retry(delivery.receipt_handle, delay=timedelta.max)

    assert queue.inflight_count("ingestion") == 1
    queue.acknowledge(delivery.receipt_handle)
    assert queue.inflight_count("ingestion") == 0
    assert queue.dead_letters("ingestion") == ()


def test_extend_overflow_preserves_active_receipt() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("extend-overflow"))
    delivery = receive_required(queue)

    with pytest.raises(InvalidQueueMessage, match="supported datetime range"):
        queue.extend_lease(delivery.receipt_handle, lease=timedelta.max)

    assert queue.inflight_count("ingestion") == 1
    queue.acknowledge(delivery.receipt_handle)


def test_advance_overflow_preserves_clock_and_inflight_state() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("advance-overflow"))
    delivery = receive_required(queue)

    with pytest.raises(InvalidQueueMessage, match="supported datetime range"):
        queue.advance(timedelta.max)

    assert queue.now == NOW
    assert queue.inflight_count("ingestion") == 1
    queue.acknowledge(delivery.receipt_handle)


def test_same_message_id_cannot_alias_different_content() -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("collision"))

    changed = QueueMessage(
        message_id="collision",
        queue_name="ingestion",
        idempotency_key="different-idempotency-key",
        payload={"message_id": "collision", "origin": "changed"},
        available_at=NOW,
        max_attempts=3,
    )
    with pytest.raises(InvalidQueueMessage, match="different message content"):
        queue.send(changed)


@pytest.mark.parametrize(
    "operation",
    [
        lambda queue: queue.receive("ingestion", lease=timedelta(0)),
        lambda queue: queue.advance(timedelta(seconds=-1)),
        lambda queue: queue.inject_duplicate("unknown"),
        lambda queue: queue.inject_duplicate("known", copies=0),
        lambda queue: queue.inject_out_of_order(
            "ingestion", message_ids=("known", "missing")
        ),
    ],
)
def test_fake_rejects_invalid_or_ambiguous_injection(
    operation,
) -> None:
    queue: QueueFake[dict[str, str]] = QueueFake(start_at=NOW)
    queue.send(make_message("known"))

    with pytest.raises(InvalidQueueMessage):
        operation(queue)
