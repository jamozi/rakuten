"""Provider-neutral queue port contract tests for ST-0203."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from raos.adapters.queue_fake import QueueFake
from raos.ports.queue import (
    InvalidQueueMessage,
    QueueDelivery,
    QueueMessage,
    QueuePort,
)


NOW = datetime(2026, 8, 2, 15, 0, tzinfo=timezone.utc)


def message(**overrides: object) -> QueueMessage[dict[str, str]]:
    values: dict[str, object] = {
        "message_id": "job-0001",
        "queue_name": "ingestion",
        "idempotency_key": "catalog-request-0001",
        "payload": {"kind": "synthetic"},
        "available_at": NOW,
        "max_attempts": 3,
    }
    values.update(overrides)
    return QueueMessage(**values)  # type: ignore[arg-type]


def test_queue_fake_satisfies_runtime_port_protocol() -> None:
    queue: QueuePort[dict[str, str]] = QueueFake(start_at=NOW)
    assert isinstance(queue, QueuePort)


def test_queue_message_and_delivery_are_immutable() -> None:
    queued = message()
    delivery = QueueDelivery(
        message=queued,
        receipt_handle="receipt-0001",
        delivery_attempt=1,
        leased_until=NOW + timedelta(seconds=30),
    )

    with pytest.raises((AttributeError, TypeError)):
        queued.message_id = "changed"  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        delivery.delivery_attempt = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"message_id": ""}, "message_id"),
        ({"message_id": " leading"}, "message_id"),
        ({"queue_name": "bad queue"}, "queue_name"),
        ({"idempotency_key": "bad\nkey"}, "idempotency_key"),
        ({"available_at": datetime(2026, 8, 2)}, "timezone-aware"),
        ({"max_attempts": 0}, "between 1 and 50"),
        ({"max_attempts": 51}, "between 1 and 50"),
        ({"max_attempts": True}, "integer"),
    ],
)
def test_queue_message_rejects_invalid_boundary_values(
    overrides: dict[str, object], match: str
) -> None:
    with pytest.raises(InvalidQueueMessage, match=match):
        message(**overrides)


@pytest.mark.parametrize(
    ("attempt", "leased_until", "match"),
    [
        (0, NOW + timedelta(seconds=1), "positive integer"),
        (True, NOW + timedelta(seconds=1), "positive integer"),
        (1, datetime(2026, 8, 2), "timezone-aware"),
    ],
)
def test_delivery_rejects_invalid_lease_identity(
    attempt: object, leased_until: datetime, match: str
) -> None:
    with pytest.raises(InvalidQueueMessage, match=match):
        QueueDelivery(
            message=message(),
            receipt_handle="receipt-0001",
            delivery_attempt=attempt,  # type: ignore[arg-type]
            leased_until=leased_until,
        )


def test_delivery_rejects_non_message_runtime_value() -> None:
    with pytest.raises(InvalidQueueMessage, match="message must be a QueueMessage"):
        QueueDelivery(
            message="not-a-message",  # type: ignore[arg-type]
            receipt_handle="receipt-0001",
            delivery_attempt=1,
            leased_until=NOW + timedelta(seconds=30),
        )
